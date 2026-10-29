# -*- coding: utf-8 -*-
"""Detección automática de anomalías y alertas del informe (idea #2).

Filosofía (ver docs/ideas-ia.md): TODAS las reglas se calculan aquí en
Python sobre cifras ya existentes. La IA, si se usa después, solo redacta
el texto; nunca decide qué es una anomalía ni calcula porcentajes.

Reglas implementadas
--------------------
Período
  1. Cobertura de recaudo (<95% de lo facturado = alerta).
  2. Sobrepago agregado (recaudo > facturado).
  3. Cartera del período (brecha facturado - recaudado).
Por clasificación / estrato (comparado con el mes anterior)
  4. Caída de recaudo >10% con facturación estable (±5%).
  5. Clasificación con mayor brecha (facturado sin recaudar).
  6. Sobrepago por clasificación (recaudo > facturado).
A nivel de cuentas (una pasada por las filas detalle)
  7. Cuentas con facturación $0 en el período.
  8. Consumos negativos (energía o valor).
  9. Id_cliente duplicados en la base de facturación.
 10. Saltos de facturación >500% vs el mes anterior (misma cuenta).
 11. IAP dejado de facturar / no percibido (si el informe lo trae).

Los niveles son: "alta" (rojo), "media" (ámbar), "baja" (azul/informativa).
"""
from collections import Counter, defaultdict

from models import db

# Umbrales configurables
UMBRAL_COBERTURA_BAJA = 95.0   # % mínimo de recaudo sobre facturado
UMBRAL_CAIDA_RECAUDO = -10.0   # % de caída de recaudo vs mes anterior
UMBRAL_FACT_ESTABLE = 5.0      # % máximo de variación para "fact estable"
UMBRAL_SALTO_CUENTA = 500.0    # % de salto de facturación entre meses


def _fmt_peso(valor):
    try:
        return "$" + format(int(round(float(valor))), ",").replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def _fmt_num(valor):
    try:
        return format(int(round(float(valor))), ",").replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def _pct(actual, anterior):
    """Variación porcentual de `anterior` a `actual`; None si no hay base."""
    try:
        anterior = float(anterior or 0)
        actual = float(actual or 0)
    except (TypeError, ValueError):
        return None
    if not anterior:
        return None
    return (actual - anterior) / anterior * 100.0


def _agregar(nivel, titulo, detalle, valor=""):
    return {"nivel": nivel, "titulo": titulo, "detalle": detalle,
            "valor": valor}


def _alertas_periodo(fact, rec, alertas):
    """Reglas 1-3: cobertura de recaudo, sobrepago y cartera."""
    if not fact and not rec:
        return
    cobertura = (rec / fact * 100.0) if fact else None
    brecha = fact - rec

    if cobertura is not None and cobertura < UMBRAL_COBERTURA_BAJA:
        alertas.append(_agregar(
            "alta", "Recaudo por debajo de lo facturado",
            f"Solo se recaudó el {cobertura:.1f}% de lo facturado "
            f"(mínimo esperado {UMBRAL_COBERTURA_BAJA:.0f}%). "
            f"Queda un descuadre de {_fmt_peso(brecha)} de este período.",
            _fmt_peso(brecha)))
    elif cobertura is not None and cobertura > 100.0:
        alertas.append(_agregar(
            "media", "Recaudo superior a lo facturado",
            f"Se recaudó el {cobertura:.1f}% de lo facturado: hay "
            f"{_fmt_peso(-brecha)} por encima de lo cobrado este período "
            f"(posibles anticipos, reconvenciones o pagos de otros meses).",
            _fmt_peso(-brecha)))

    if brecha > 0 and (cobertura is None or cobertura >= UMBRAL_COBERTURA_BAJA):
        nivel = "alta" if (fact and brecha / fact * 100.0 > 10) else "media"
        alertas.append(_agregar(
            nivel, "Cartera generada en el período",
            f"Se facturó {_fmt_peso(fact)} y se recaudó {_fmt_peso(rec)}; "
            f"la diferencia de este mes es {_fmt_peso(brecha)}.",
            _fmt_peso(brecha)))


def _fyr_valores(datos):
    """Saca fact/rec de una entrada de la tabla FYR sin lanzar error."""
    try:
        fact = float((datos.get("fact") or [0, 0, 0])[2] or 0)
        rec = float((datos.get("rec") or [0, 0, 0])[2] or 0)
    except (TypeError, ValueError, IndexError):
        fact = rec = 0.0
    return fact, rec


def _alertas_por_estrato(fyr, fyr_orden, fyr_prev, alertas):
    """Reglas 4-6: caídas, brechas y sobrepagos por clasificación."""
    if not fyr or not fyr_orden:
        return
    caidas, brechas, sobrepagos = [], [], []

    for clave in fyr_orden:
        fact, rec = _fyr_valores(fyr.get(clave) or {})
        etiqueta = (clave.replace("Residencial – ", "")
                         .replace("Residencial - ", ""))

        if fyr_prev:
            pf, pr = _fyr_valores(fyr_prev.get(clave) or {})
            if pr:
                v_rec = _pct(rec, pr)
                v_fact = _pct(fact, pf)
                # Regla 4: recaudo cae >10% y la facturación se mantiene
                if v_rec is not None and v_rec <= UMBRAL_CAIDA_RECAUDO:
                    estable = v_fact is None or abs(v_fact) <= UMBRAL_FACT_ESTABLE
                    if estable:
                        caidas.append((etiqueta, v_rec, v_fact, pr - rec))

        # Regla 5: facturado sin recaudar
        if fact - rec > 0:
            brechas.append((etiqueta, fact - rec))
        # Regla 6: recaudado por encima de lo facturado
        elif rec - fact > 0:
            sobrepagos.append((etiqueta, rec - fact))

    for etiqueta, v_rec, v_fact, perdido in sorted(caidas,
                                                   key=lambda x: x[1])[:4]:
        detalle = (f"El recaudo cayó {abs(v_rec):.1f}% frente al mes anterior "
                   f"mientras la facturación "
                   f"{'se mantuvo estable' if v_fact is None else f'varió {v_fact:+.1f}%'}"
                   f": {_fmt_peso(perdido)} menos recaudado que el mes previo.")
        alertas.append(_agregar("alta", f"{etiqueta}: caída de recaudo",
                                detalle, f"{v_rec:+.1f}%".replace(".", ",")))

    if brechas:
        etiqueta, monto = max(brechas, key=lambda x: x[1])
        alertas.append(_agregar(
            "media", f"{etiqueta}: mayor brecha del período",
            f"Es la clasificación con más facturado sin recaudar: "
            f"{_fmt_peso(monto)} de este período.",
            _fmt_peso(monto)))

    for etiqueta, monto in sorted(sobrepagos, key=lambda x: -x[1])[:2]:
        alertas.append(_agregar(
            "baja", f"{etiqueta}: sobrepago",
            f"Se recaudó {_fmt_peso(monto)} por encima de lo facturado "
            f"en esta clasificación.", _fmt_peso(monto)))


def _alertas_cuentas(fact_registros, rec_registros, fact_prev, alertas):
    """Reglas 7-10: una sola pasada por las filas de cuentas."""
    if not fact_registros:
        return

    sin_facturar = 0
    consumos_neg = 0
    vistos = Counter()
    fact_por_cuenta = defaultdict(float)

    for fila in fact_registros:
        cid = fila.get("Id_cliente")
        if cid is not None:
            vistos[str(cid).strip()] += 1
        try:
            imp = float(fila.get("ImpuestoAP") or 0)
            cons = float(fila.get("Consumo$") or 0)
            kwh = float(fila.get("ConsumokWh") or 0)
        except (TypeError, ValueError):
            imp = cons = kwh = 0.0
        if imp == 0:
            sin_facturar += 1
        if cons < 0 or kwh < 0:
            consumos_neg += 1
        if cid is not None:
            fact_por_cuenta[str(cid).strip()] += imp

    # Regla 7
    if sin_facturar:
        alertas.append(_agregar(
            "media", "Cuentas sin facturar en el período",
            f"{_fmt_num(sin_facturar)} cuentas quedaron con facturación $0 "
            f"en este período.", _fmt_num(sin_facturar)))

    # Regla 8
    if consumos_neg:
        alertas.append(_agregar(
            "alta", "Consumos negativos",
            f"{_fmt_num(consumos_neg)} cuentas registran consumo o valor "
            f"negativo: posible error en la base cargada.",
            _fmt_num(consumos_neg)))

    # Regla 9 (solo si hay duplicados reales)
    duplicados = sum(n - 1 for n in vistos.values() if n > 1)
    if duplicados:
        alertas.append(_agregar(
            "media", "Cuentas duplicadas en la base",
            f"{_fmt_num(duplicados)} registros repiten el mismo Id_cliente "
            f"en la facturación: los totales pueden estar inflados.",
            _fmt_num(duplicados)))

    # Regla 10: saltos >500% contra el mes anterior
    if fact_prev:
        fact_prev_cuenta = defaultdict(float)
        for fila in fact_prev:
            cid = fila.get("Id_cliente")
            if cid is None:
                continue
            try:
                imp = float(fila.get("ImpuestoAP") or 0)
            except (TypeError, ValueError):
                imp = 0.0
            fact_prev_cuenta[str(cid).strip()] += imp

        saltos = 0
        ejemplo = None
        for cid, actual in fact_por_cuenta.items():
            previo = fact_prev_cuenta.get(cid)
            if not previo or actual <= 0:
                continue
            salto = (actual - previo) / previo * 100.0
            if salto >= UMBRAL_SALTO_CUENTA:
                saltos += 1
                if ejemplo is None:
                    ejemplo = (cid, previo, actual, salto)
        if saltos:
            det = (f"{_fmt_num(saltos)} cuentas aumentaron su facturación "
                   f"más de {UMBRAL_SALTO_CUENTA:.0f}% frente al mes anterior.")
            if ejemplo:
                det += (f" Ej.: cuenta {ejemplo[0]} pasó de "
                        f"{_fmt_peso(ejemplo[1])} a {_fmt_peso(ejemplo[2])} "
                        f"({ejemplo[3]:.0f}%).")
            alertas.append(_agregar("media", "Saltos extremos de facturación",
                                    det, _fmt_num(saltos)))


def _alertas_iap(analisis, alertas):
    """Regla 11: IAP dejado de facturar / no percibido por el municipio."""
    if not isinstance(analisis, dict):
        return
    dejado = analisis.get("iap_dejado_facturar") or 0
    no_percibido = analisis.get("iap_no_percibido_municipio") or 0
    try:
        dejado, no_percibido = float(dejado), float(no_percibido)
    except (TypeError, ValueError):
        return
    if dejado > 0:
        alertas.append(_agregar(
            "media", "IAP que se dejó de facturar",
            "Hay impuesto de alumbrado público que no se facturó por "
            "tarifas o topes aplicados en el período.",
            _fmt_peso(dejado)))
    if no_percibido > 0:
        alertas.append(_agregar(
            "alta", "IAP no percibido por el municipio",
            "Diferencia entre el impuesto facturado y el recaudo real "
            "del impuesto de alumbrado público.",
            _fmt_peso(no_percibido)))


def detectar_alertas(report, fyr=None, fyr_orden=None, fyr_prev=None,
                     fact_prev=None, con_detalle=True):
    """Devuelve el dict de alertas de un reporte.

    fact_prev = filas de facturación del mes anterior (para la regla de
    saltos); si no viene, se busca solo si fyr_prev indica que hay mes
    anterior (evita descomprimir un informe grande dos veces).
    con_detalle=False evita recorrer las ~235 mil filas (modos rápidos).
    """
    datos = report.general_data or {}
    alertas = []

    f = datos.get("f") or {}
    r = datos.get("r") or {}
    fact = float(f.get("total_imp") or 0)
    rec = float(r.get("total_valor") or 0)

    _alertas_periodo(fact, rec, alertas)
    _alertas_por_estrato(fyr, fyr_orden, fyr_prev, alertas)

    if con_detalle:
        if fact_prev is None and fyr_prev is not None:
            prev = _mes_anterior(report)
            if prev is not None and prev.general_data:
                fact_prev = (prev.general_data or {}).get("facturacion")
        _alertas_cuentas(datos.get("facturacion") or [],
                         datos.get("recaudo") or [], fact_prev, alertas)

    _alertas_iap(datos.get("analisis"), alertas)

    orden = {"alta": 0, "media": 1, "baja": 2}
    alertas.sort(key=lambda a: orden.get(a["nivel"], 3))
    return {
        "total": len(alertas),
        "alta": sum(1 for a in alertas if a["nivel"] == "alta"),
        "media": sum(1 for a in alertas if a["nivel"] == "media"),
        "baja": sum(1 for a in alertas if a["nivel"] == "baja"),
        "alertas": alertas,
    }


def _mes_anterior(report):
    from models import Report
    anio, mes = report.anio, report.mes
    if mes == 1:
        mes, anio = 12, anio - 1
    else:
        mes -= 1
    return (Report.query
            .filter(Report.comercializadora_id == report.comercializadora_id,
                    Report.anio == anio, Report.mes == mes)
            .first())


def _es_fyr(report):
    """Solo EMSA/Villavicencio maneja la tabla por estrato y clasificación."""
    return ((report.comercializadora_nombre or "").strip().lower() == "emsa"
            or (report.municipio_nombre or "").strip().lower() == "villavicencio")


def calcular_alertas(report):
    """Calcula las alertas del reporte (usa los datos ya en memoria si están)."""
    from core.fyr import FYR_ORDEN, fyr_agregar
    datos = report.general_data or {}
    fyr = fyr_prev = fyr_orden = fact_prev = None

    if _es_fyr(report):
        fyr = fyr_agregar(datos.get("facturacion"), datos.get("recaudo"))
        fyr_orden = list(FYR_ORDEN)
        prev = _mes_anterior(report)
        if prev is not None and prev.general_data:
            fyr_prev = fyr_agregar((prev.general_data or {}).get("facturacion"),
                                   (prev.general_data or {}).get("recaudo"))
            fact_prev = (prev.general_data or {}).get("facturacion")

    return detectar_alertas(report, fyr=fyr, fyr_orden=fyr_orden,
                            fyr_prev=fyr_prev, fact_prev=fact_prev)


def guardar_alertas(report):
    """Calcula las alertas y las persiste en `alertas_reporte`.
    Devuelve None si algo falla (nunca debe romper la carga de informes)."""
    import json
    from datetime import datetime as _dt
    from models import AlertaReporte
    try:
        # Solo aquí se toca general_data (fallback de informes antiguos):
        # si no tiene datos, no hay nada que analizar.
        if report.general_data is None:
            return None
        datos = calcular_alertas(report)
        if datos is None:
            return None
        fila = AlertaReporte.query.get(report.id)
        texto = json.dumps(datos, ensure_ascii=False, default=str)
        if fila is None:
            fila = AlertaReporte(report_id=report.id, datos=texto)
            db.session.add(fila)
        else:
            fila.datos = texto
            fila.actualizado = _dt.utcnow()
        db.session.commit()
        return datos
    except Exception:
        db.session.rollback()
        return None


def obtener_alertas(report):
    """Devuelve las alertas: primero las precalculadas; si no existen,
    las calcula ahora y las guarda (para informes antiguos)."""
    import json
    from models import AlertaReporte
    fila = AlertaReporte.query.get(report.id)
    if fila is not None and fila.datos:
        try:
            datos = json.loads(fila.datos)
            if isinstance(datos, dict) and datos.get("alertas") is not None:
                return datos
        except (ValueError, TypeError):
            pass
    return guardar_alertas(report)
