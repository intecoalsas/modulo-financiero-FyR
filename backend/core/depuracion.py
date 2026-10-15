
import json

import numpy as np
import pandas as pd

from core.utils import detect_clase, detect_sector, leer_excel


# Texto en minúsculas; NaN/None como cadena vacía
def _txt(s):
    return s.astype(str).str.lower().replace(["nan", "none"], "", regex=False)


# Clase por prioridad residencial > comercial > industrial > oficial
def _v_clase(desc):
    s = _txt(desc)
    return np.select(
        [s.str.contains("residencial", na=False), s.str.contains("comercial", na=False),
         s.str.contains("industrial", na=False), s.str.contains("oficial", na=False)],
        ["Residencial", "Comercial", "Industrial", "Oficial"], default="Residencial")


# Sector por subcadena "urb"
def _v_sector(sector):
    return np.where(_txt(sector).str.contains("urb", na=False), "Urbanas", "Rurales")


# Id entero si es entero exacto, numérico si es decimal, texto intacto si no
def _v_id(col):
    base = col.astype(object)
    num = pd.to_numeric(col, errors="coerce")
    ok = num.notna()
    base[ok] = num[ok]
    entera = ok & (num % 1 == 0)
    base[entera] = num[entera].astype("int64").astype(object)
    return base


# Columna a número; lo no numérico a 0
def _v_num(col):
    return pd.to_numeric(col, errors="coerce").fillna(0.0)


# Filas con consumo en blanco (no aportan consumo ni kWh)
def _v_blank(df):
    return df["consumo_kwh"].isna() | df["monto_kwh"].isna()


# Serialización nativa única del resultado
def _a_registros(df):
    return json.loads(df.to_json(orient="records", double_precision=15))


# Convierte a DataFrame la entrada (puede ser una ruta de archivo o un DataFrame)
def _a_dataframe(source, **kwargs):
    if isinstance(source, pd.DataFrame):
        return source.copy()
    return leer_excel(source, **kwargs)


# Lee el archivo de facturación y lo "limpia": una sola fila por cuenta,
# sumando lo que se debe sumar y dejando por fuera los registros duplicados.
# Con sin_depurar=True (EMSA/Villavicencio: no hay duplicados) se toma cada
# fila tal cual, sin agrupar ni descartar (mucho más rápido en grande).
def depurar_facturacion(path, mapping=None, sin_depurar=False):
    df = _a_dataframe(path)
    if mapping:
        df = df.rename(columns=mapping)
    if sin_depurar:
        df = df.dropna(subset=["Id_cliente"])
        blank = _v_blank(df)
        out = pd.DataFrame({
            "Id_cliente": _v_id(df["Id_cliente"]),
            "Empresa": df["Empresa"],
            "Nombre": df["Nombre"],
            "Direccion": df["dirección"],
            "Clase": _v_clase(df["desc_clase"]),
            "Tipo": df["mercado"],
            "Estrato": df["estrato_socioeconomico"],
            "Sector": _v_sector(df["Sector"]),
            "Periodicidad": df["Periodicidad"],
            "ImpuestoAP": _v_num(df["monto_AP"]),
            "Consumo$": _v_num(df["monto_kwh"]).where(~blank, 0.0),
            "ConsumokWh": _v_num(df["consumo_kwh"]).where(~blank, 0.0),
        })
        registro = _a_registros(out)
        total_imp = float(out["ImpuestoAP"].sum())
        total_consumo = float(out["Consumo$"].sum())
        total_kwh = float(out["ConsumokWh"].sum())
        cuentas = len(out)
        flags = {
            "UNICA FACTURA": cuentas,
            "FACTURA DIFERENTE - SUMAR TODO": 0,
            "REFACTURACION - MISMA FACTURA": 0,
            "CONSUMO DUPLICADO - PRIMERA OCURR.": 0,
            "CONSUMO DUPLICADO - EXCLUIR CONSUMO": 0,
        }
        orig_imp = float(_v_num(df["monto_AP"]).sum())
        orig_cons = float(_v_num(df["monto_kwh"]).sum())
        orig_kwh = float(_v_num(df["consumo_kwh"]).sum())
        return {
            "registros": registro,
            "total_imp": total_imp,
            "total_consumo": total_consumo,
            "total_kwh": total_kwh,
            "flags": flags,
            "cuentas": cuentas,
            "orig_imp": orig_imp,
            "orig_cons": orig_cons,
            "orig_kwh": orig_kwh,
        }
    # Se descartan filas sin identificación o sin número de factura
    df = df.dropna(subset=["Id_cliente", "numero_factura"])

    registro = []
    # Contadores para saber cuántos casos hubo de cada situación
    flags = {
        "UNICA FACTURA": 0,
        "FACTURA DIFERENTE - SUMAR TODO": 0,
        "REFACTURACION - MISMA FACTURA": 0,
        "CONSUMO DUPLICADO - PRIMERA OCURR.": 0,
        "CONSUMO DUPLICADO - EXCLUIR CONSUMO": 0,
    }
    total_imp = total_consumo = total_kwh = 0.0
    cuentas = 0

    # Se agrupa por cuenta (Id_cliente) porque una cuenta puede tener varias filas
    for idc, g in df.groupby("Id_cliente", sort=False):
        rows = list(g.itertuples(index=False))
        base = rows[0]
        base_fact = str(base.numero_factura)
        base_blank = pd.isna(base.consumo_kwh) or pd.isna(base.monto_kwh)

        # Si la cuenta solo tiene una fila, todo se toma tal cual
        if len(rows) == 1:
            flags["UNICA FACTURA"] += 1
            imp_val = float(g["monto_AP"].sum())
            cons_val = float(base.monto_kwh) if not base_blank else 0.0
            kwh_val = float(base.consumo_kwh) if not base_blank else 0.0
        else:
            # Si tiene varias filas:
            # - el impuesto SIEMPRE se suma
            # - el consumo solo se suma si es de una factura distinta y no está repetido
            seen = set()
            imp_val = 0.0
            cons_val = 0.0
            kwh_val = 0.0

            if not base_blank:
                cons_val += base.monto_kwh
                kwh_val += base.consumo_kwh
                seen.add((base.consumo_kwh, base.monto_kwh))

            for r in rows[1:]:
                blank = pd.isna(r.consumo_kwh) or pd.isna(r.monto_kwh)
                if str(r.numero_factura) == base_fact:
                    flags["REFACTURACION - MISMA FACTURA"] += 1
                elif blank:
                    flags["FACTURA DIFERENTE - SUMAR TODO"] += 1
                elif (r.consumo_kwh, r.monto_kwh) in seen:
                    flags["CONSUMO DUPLICADO - EXCLUIR CONSUMO"] += 1
                else:
                    flags["FACTURA DIFERENTE - SUMAR TODO"] += 1
                    cons_val += r.monto_kwh
                    kwh_val += r.consumo_kwh
                    seen.add((r.consumo_kwh, r.monto_kwh))
            imp_val = float(g["monto_AP"].sum())

        total_imp += imp_val
        total_consumo += cons_val
        total_kwh += kwh_val
        cuentas += 1

        # Se guarda una fila limpia por cuenta
        r0 = g.iloc[0]
        registro.append({
            "Id_cliente": int(idc),
            "Empresa": r0["Empresa"],
            "Nombre": r0["Nombre"],
            "Direccion": r0["direcci\u00f3n"],
            "Clase": detect_clase(r0["desc_clase"]),
            "Tipo": r0["mercado"],
            "Estrato": r0["estrato_socioeconomico"],
            "Sector": detect_sector(r0["Sector"]),
            "Periodicidad": r0["Periodicidad"],
            "ImpuestoAP": imp_val,
            "Consumo$": cons_val,
            "ConsumokWh": kwh_val,
        })

    # Totales del archivo original tal como llegó (sin depurar), para comparar después
    orig_imp = float(df["monto_AP"].sum())
    orig_cons = float(df["monto_kwh"].fillna(0).sum())
    orig_kwh = float(df["consumo_kwh"].fillna(0).sum())

    return {
        "registros": registro,
        "total_imp": total_imp,
        "total_consumo": total_consumo,
        "total_kwh": total_kwh,
        "flags": flags,
        "cuentas": cuentas,
        "orig_imp": orig_imp,
        "orig_cons": orig_cons,
        "orig_kwh": orig_kwh,
    }


# Lee el archivo de recaudo y lo deja con una sola fila por cuenta,
# sumando el valor recaudado cuando aparecen repetidas.
# Con sin_depurar=True (EMSA) se toma cada fila tal cual.
def depurar_recaudo(path, mapping=None, sin_depurar=False):
    df = _a_dataframe(path, sheet_name=0)
    if mapping:
        df = df.rename(columns=mapping)
    df = df.dropna(subset=["Id_cliente"])
    if sin_depurar:
        out = pd.DataFrame({
            "Id_cliente": _v_id(df["Id_cliente"]),
            "Empresa": df["Empresa"],
            "Tipo": df["mercado"],
            "Nombre": df["nombre"],
            "Direccion": df["direccion"],
            "Clase": _v_clase(df["desc_clase"]),
            "Sector": _v_sector(df["Sector"]),
            "Estrato": df["estrato_socioeconomico"],
            "ValorAP": _v_num(df["valor_recaudado"]),
        })
        registros = _a_registros(out)
        total_valor = float(out["ValorAP"].sum())
        return {"registros": registros, "total_valor": total_valor,
                "flags": {"UNICO": len(out), "BASE": 0, "DUPLICADO": 0},
                "cuentas": len(out), "orig_total": total_valor}

    flags = {"UNICO": 0, "BASE": 0, "DUPLICADO": 0}
    total_valor = 0.0
    registros = []
    cuentas = 0

    # Se agrupa por cuenta y se suma todo el valor recaudado de esa cuenta
    for idc, g in df.groupby("Id_cliente", sort=False):
        valor = float(g["valor_recaudado"].sum())
        total_valor += valor
        r0 = g.iloc[0]
        registros.append({
            "Id_cliente": int(idc),
            "Empresa": r0["Empresa"],
            "Tipo": r0["mercado"],
            "Nombre": r0["nombre"],
            "Direccion": r0["direccion"],
            "Clase": detect_clase(r0["desc_clase"]),
            "Sector": detect_sector(r0["Sector"]),
            "Estrato": r0["estrato_socioeconomico"],
            "ValorAP": valor,
        })
        n = len(g)
        if n == 1:
            flags["UNICO"] += 1
        else:
            flags["BASE"] += 1
            flags["DUPLICADO"] += n - 1
        cuentas += 1

    orig_total = float(df["valor_recaudado"].sum())
    return {"registros": registros, "total_valor": total_valor, "flags": flags, "cuentas": cuentas, "orig_total": orig_total}
