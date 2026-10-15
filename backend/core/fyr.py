# -*- coding: utf-8 -*-
"""Agregación estilo Informe FyR (hoja de Villavicencio/EMSA).

Agrupa los registros depurados por clasificación × estrato × zona para las
tablas del informe: Residencial E1–E6, Subtotal, Comercial, Oficial,
Industrial, Otros (complemento del total) y TOTAL, cada uno con
[urbana, rural, total]. La usa el Word general y la página del informe
general de EMSA/Villavicencio.
"""

# Filas en el orden de la hoja de referencia
FYR_ORDEN = (["Residencial – Estrato %d" % i for i in range(1, 7)]
             + ["Subtotal Residencial", "Comercial", "Oficial",
                "Industrial", "Otros", "TOTAL"])


def fyr_estrato(v):
    try:
        i = int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None
    return i if 1 <= i <= 6 else None


def fyr_clave(clase, estrato):
    if (clase or "") == "Residencial" and fyr_estrato(estrato):
        return "Residencial – Estrato %d" % fyr_estrato(estrato)
    if clase in ("Comercial", "Oficial", "Industrial"):
        return clase
    return "Otros"


def _fyr_cero():
    return {"n": [0, 0], "fact": [0.0, 0.0], "rec": [0.0, 0.0],
            "base": [0.0, 0.0], "kwh": [0.0, 0.0]}


def fyr_agregar(facturacion, recaudo):
    """Devuelve {grupo: {n, fact, rec, base, kwh}} con listas
    [urbana, rural, total]. "Subtotal", "Otros" y "TOTAL" salen por
    suma/complemento, igual que la hoja de referencia."""
    det = ["Residencial – Estrato %d" % i for i in range(1, 7)] + ["Comercial", "Oficial", "Industrial"]
    acc = {k: _fyr_cero() for k in det + ["Otros"]}
    for r in facturacion or []:
        k = fyr_clave(r.get("Clase"), r.get("Estrato"))
        z = 0 if (r.get("Sector") or "") == "Urbanas" else 1
        a = acc[k]
        a["n"][z] += 1
        a["fact"][z] += float(r.get("ImpuestoAP") or 0)
        a["base"][z] += float(r.get("Consumo$") or 0)
        a["kwh"][z] += float(r.get("ConsumokWh") or 0)
    for r in recaudo or []:
        k = fyr_clave(r.get("Clase"), r.get("Estrato"))
        z = 0 if (r.get("Sector") or "") == "Urbanas" else 1
        acc[k]["rec"][z] += float(r.get("ValorAP") or 0)

    def _sum(keys, met):
        return [sum(acc[k][met][z] for k in keys) for z in (0, 1)]

    res = {}
    for k in det:
        a = acc[k]
        res[k] = {m: [a[m][0], a[m][1], a[m][0] + a[m][1]] for m in ("n", "fact", "rec", "base", "kwh")}
    sub = {m: [_sum(det[:6], m)[0], _sum(det[:6], m)[1], 0.0] for m in ("n", "fact", "rec", "base", "kwh")}
    for m in sub:
        sub[m][2] = sub[m][0] + sub[m][1]
    res["Subtotal Residencial"] = sub
    tot = {}
    for m in ("n", "fact", "rec", "base", "kwh"):
        tu = sum(acc[k][m][0] for k in acc)
        tr = sum(acc[k][m][1] for k in acc)
        tot[m] = [tu, tr, tu + tr]
    res["TOTAL"] = tot
    otros = {}
    conocidos = det[:6] + det[6:]
    for m in ("n", "fact", "rec", "base", "kwh"):
        cu = tot[m][0] - sum(res[k][m][0] for k in conocidos)
        cr = tot[m][1] - sum(res[k][m][1] for k in conocidos)
        otros[m] = [cu, cr, cu + cr]
    res["Otros"] = otros
    return res
