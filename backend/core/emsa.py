# -*- coding: utf-8 -*-
"""Informe exógeno de EMSA (Villavicencio): un solo archivo con todo.

La hoja "Exogena" trae por usuario lo facturado, lo recaudado y la cartera.
Desde ella se arman los dos archivos lógicos (facturación y recaudo) que
entiende el sistema, para Villavicencio se sube SOLO este archivo.
"""

import pandas as pd

MUNICIPIO = "Villavicencio"
COMERCIALIZADORA = "EMSA"
EMPRESA_NOMBRE = "ELECTRIFICADORA DEL META S.A. (EMSA)"

# Índices (0‑based) de las columnas del informe exógeno de EMSA
COL_ID = 12          # NUMERO DE IDENTIFICACION USUARIO
COL_MERCADO = 14     # MERCADO (REGULADO O NO REGULADO)
COL_SECTOR = 15      # SECTOR (URBANO - RURAL)
COL_DESTINO = 16     # DESTINO ECONOMICO DEL PREDIO
COL_ESTRATO = 17     # ESTRATO SOCIOECONOMICO
COL_FACTURA = 18     # NUMERO DE FACTURA
COL_PERIODO = 21     # PERIODO / MES  (ej. 2026/6)
COL_KWH = 24         # CONSUMO DE KILOVATIOS (KW/H)
COL_CONS_VALOR = 26  # VALOR CONSUMO DE ENERGIA (BASE PARA FACTURACION)
COL_IMP_FACT = 27    # VALOR IMPUESTO DE ALUMBRADO PUBLICO FACTURADO
COL_IMP_REC = 28     # VALOR IMPUESTO DE ALUMBRADO PUBLICO RECAUDADO
COL_APELLIDO1 = 3
COL_APELLIDO2 = 4
COL_NOMBRE1 = 5
COL_NOMBRE2 = 6
COL_RAZON = 7        # RAZON SOCIAL
COL_DIRECCION = 8    # DIRECCION DE SUMINISTRO DEL SERVICIO

# Tarifas del Acuerdo 515 de 12/04/2021 (Art. 242): % sobre la LCEE
TARIFAS_LCEE_2026 = {
    "esquema": "lcee",
    "lcee": {
        "fuente": ("Acuerdo No. 515 de 12/04/2021 - Concejo Municipal de "
                   "Villavicencio (Capitulo XVI, Impuesto de Alumbrado Publico)"),
        "base_gravable": ("Liquidacion del Consumo de Energia Electrica (LCEE) "
                          "antes de contribuciones o subsidios (prepago o pospago); "
                          "el avaluo catastral en los casos pertinentes."),
        "residenciales": [
            {"estrato": 1, "porcentaje": 1},
            {"estrato": 2, "porcentaje": 2},
            {"estrato": 3, "porcentaje": 3},
            {"estrato": 4, "porcentaje": 8},
            {"estrato": 5, "porcentaje": 12},
            {"estrato": 6, "porcentaje": 12},
        ],
        "sectores": [
            {"sector": "Comercial", "porcentaje": 15},
            {"sector": "Industrial", "porcentaje": 15},
            {"sector": "Oficial", "porcentaje": 15},
            {"sector": "Temporales", "porcentaje": 15},
            {"sector": "Autogeneradores", "porcentaje": 15},
        ],
        "predios_sin_servicio": {
            "por_mil": 1,
            "base": "avaluo que sirve de base para liquidar el impuesto predial",
        },
        "notas": [
            "Art. 235: autorizacion legal (Ley 97 de 1913, Ley 84 de 1915 y Ley 1819 de 2016).",
            "Art. 240: base gravable = LCEE antes de contribucion o subsidios; incluye "
            "energia alternativa, cogenerada y autogenerada.",
            "Art. 241: el impuesto se causa mensualmente.",
            "Art. 242 (Parag. 2): contribuyentes no clasificados (predios y/o lotes sin "
            "servicio) pagan 1 por mil sobre el avaluo.",
            "Art. 243: los autogeneradores pagan segun la LCEE; si ademas son usuarios, "
            "se suma el consumo facturado mas la energia autogenerada.",
            "Art. 246: responsables del recaudo son las empresas prestadoras, "
            "distribuidores y comercializadores de energia; el impuesto se recauda "
            "conjuntamente con el servicio e incorporado en la factura.",
            "Art. 249: destinacion exclusiva a la prestacion, mejora, modernizacion y "
            "ampliacion del alumbrado publico.",
        ],
    },
}


def _str(v):
    """Convierte una celda a texto limpio ('' si está vacía)."""
    if v is None:
        return ""
    if isinstance(v, float) and (pd.isna(v) or v != v):
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    return s


def _num(v):
    """Convierte una celda a número (None si no es numérica)."""
    s = _str(v).replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _id(v):
    """Identificación del usuario en número entero cuando sea posible."""
    n = _num(v)
    if n is None:
        return None
    return int(n) if float(n).is_integer() else n


def _nombre(nombre1, nombre2, apellido1, apellido2, razon):
    """Arma el nombre del contribuyente: razón social o nombres + apellidos."""
    if razon:
        return razon
    partes = [p for p in (apellido1, apellido2, nombre1, nombre2) if p]
    return " ".join(partes)


def es_archivo_emsa(path):
    """Dice si el Excel es el exógeno de EMSA (tiene hoja Exogena)."""
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            return any((s or "").strip().lower() == "exogena" for s in wb.sheetnames)
        finally:
            wb.close()
    except Exception:
        return False


def leer_exogena_emisa(path):
    """Lee el archivo exógeno de EMSA y devuelve los DataFrames de
    facturación y recaudo en el formato interno que espera el sistema."""
    # Las 3 primeras filas son metadatos (Nit, nombre, periodo); la fila 4 es el encabezado
    from core.utils import leer_excel
    raw = leer_excel(path, sheet_name="Exogena", header=3, dtype=str)

    ids = raw.iloc[:, COL_ID].map(_id)
    mercado = raw.iloc[:, COL_MERCADO].map(_str)
    sector = raw.iloc[:, COL_SECTOR].map(_str)
    destino = raw.iloc[:, COL_DESTINO].map(_str)
    estrato = raw.iloc[:, COL_ESTRATO].map(_str)
    direccion = raw.iloc[:, COL_DIRECCION].map(_str)

    nombres = []
    for t in raw.itertuples(index=False, name=None):
        nombres.append(_nombre(
            t[COL_NOMBRE1], t[COL_NOMBRE2], t[COL_APELLIDO1], t[COL_APELLIDO2], t[COL_RAZON],
        ))

    fact = pd.DataFrame({
        "Id_cliente": ids,
        "numero_factura": raw.iloc[:, COL_FACTURA].map(_str),
        "monto_AP": raw.iloc[:, COL_IMP_FACT].map(lambda v: _num(v) or 0.0),
        "monto_kwh": raw.iloc[:, COL_CONS_VALOR].map(_num),
        "consumo_kwh": raw.iloc[:, COL_KWH].map(_num),
        "Empresa": EMPRESA_NOMBRE,
        "Nombre": nombres,
        "dirección": direccion,
        "desc_clase": destino,
        "mercado": mercado,
        "estrato_socioeconomico": estrato,
        "Sector": sector,
        "Periodicidad": "Mensual",
    })

    rec = pd.DataFrame({
        "Id_cliente": ids,
        "valor_recaudado": raw.iloc[:, COL_IMP_REC].map(lambda v: _num(v) or 0.0),
        "Empresa": EMPRESA_NOMBRE,
        "mercado": mercado,
        "nombre": nombres,
        "direccion": direccion,
        "desc_clase": destino,
        "Sector": sector,
        "estrato_socioeconomico": estrato,
    })

    # Se descartan las filas sin identificación de usuario
    fact = fact[fact["Id_cliente"].notna()].copy()
    rec = rec[rec["Id_cliente"].notna()].copy()

    # Se intenta sacar el periodo desde la columna "PERIODO / MES" (ej. "2026/6")
    periodos = [_str(v) for v in raw.iloc[:, COL_PERIODO].tolist()]
    periodos = [p for p in periodos if "/" in p]
    periodo = None
    if periodos:
        try:
            from collections import Counter
            cand = Counter(periodos).most_common(1)[0][0]
            anio, mes = cand.split("/")
            periodo = (int(anio), int(mes))
        except (ValueError, TypeError):
            periodo = None

    return fact, rec, periodo
