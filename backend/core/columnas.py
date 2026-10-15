"""Resolución de columnas: encuentra en los archivos subidos la columna que
corresponde a cada dato (cliente, factura, consumo, recaudo, etc.).
Usa aliases predefinidos y otros que se van aprendiendo de los archivos."""

import json
import re
import unicodedata

from models import MapeoColumna, db


# Alias por defecto: para cada dato se listan los posibles nombres de columna
# que pueden aparecer en los archivos subidos
ALIASES_DEFAULT = {
    "Id_cliente": ["Id_cliente", "ID Cliente", "Id Cliente", "Codigo", "C\u00f3digo", "Identificaci\u00f3n"],
    "numero_factura": ["numero_factura", "No. Factura", "No Factura", "Factura", "Nro Factura", "N\u00famero de Factura"],
    "monto_AP": ["monto_AP", "Monto AP", "Impuesto Alumbrado P\u00fablico", "Impuesto Alumbrado Publico", "IAP", "Valor AP", "Imp AP"],
    "monto_kwh": ["monto_kwh", "Valor Consumo", "Valor Consumo ($)", "Consumo $", "Valor Energ\u00eda", "Valor Energia"],
    "consumo_kwh": ["consumo_kwh", "Consumo", "Consumo kWh", "Kwh", "kWh", "Consumo (kWh)"],
    "Empresa": ["Empresa", "EMPRESA"],
    "Nombre": ["Nombre", "Nombre Cliente", "nombre"],
    "direcci\u00f3n": ["direcci\u00f3n", "direccion", "Direccion", "Direcci\u00f3n", "Direcci\u00f3n Cliente"],
    "direccion": ["direccion", "Direccion", "Direcci\u00f3n", "direcci\u00f3n"],
    "desc_clase": ["desc_clase", "Desc Clase", "Desc. Clase", "Clase", "Descripci\u00f3n de la Clase", "Descripcion Clase"],
    "mercado": ["mercado", "Mercado", "Tipo Mercado"],
    "estrato_socioeconomico": ["estrato_socioeconomico", "Estrato", "Estrato Socioeconomico", "Estrato Socioecon\u00f3mico"],
    "Sector": ["Sector", "sector", "Sector Urbano/Rural"],
    "Periodicidad": ["Periodicidad", "periodicidad"],
    "valor_recaudado": ["valor_recaudado", "Valor Recaudado", "Recaudo", "Valor Recaudo", "Valor AP Rec"],
    "municipio": ["municipio", "Municipio"],
    "fecha": ["fecha_generacion", "fecha_vencimiento", "fecha_aplicacion", "fecha_pago",
              "Fecha", "Fecha Generaci\u00f3n", "Fecha Vencimiento", "Fecha Aplicaci\u00f3n", "Fecha Pago"],
}

ETIQUETAS_CLAVE = {
    "Id_cliente": "Identificaci\u00f3n del cliente (ID)",
    "numero_factura": "N\u00famero de factura",
    "monto_AP": "Valor del impuesto de alumbrado p\u00fablico ($)",
    "monto_kwh": "Valor del consumo ($)",
    "consumo_kwh": "Consumo (kWh)",
    "Empresa": "Empresa / raz\u00f3n social",
    "Nombre": "Nombre del cliente",
    "direcci\u00f3n": "Direcci\u00f3n (facturaci\u00f3n)",
    "direccion": "Direcci\u00f3n (recaudo)",
    "desc_clase": "Clase o descripci\u00f3n de la clase (residencial, comercial\u2026)",
    "mercado": "Mercado (tipo de usuario)",
    "estrato_socioeconomico": "Estrato socioecon\u00f3mico",
    "Sector": "Sector (urbano/rural)",
    "Periodicidad": "Periodicidad (mensual/bimestral)",
    "valor_recaudado": "Valor recaudado del impuesto de alumbrado p\u00fablico",
    "municipio": "Municipio",
    "fecha": "Fecha del periodo",
}

# Ejemplo corto de cada dato: se muestra en el cuestionario emergente para
# que se sepa qué se está preguntando
EJEMPLOS_CLAVE = {
    "Id_cliente": "5298140000",
    "numero_factura": "CTCV1768543",
    "monto_AP": "$437.726",
    "monto_kwh": "$1.909.224",
    "consumo_kwh": "2160",
    "Empresa": "Celsia",
    "Nombre": "AGROINVERSIONES CARNEL SAS",
    "direcci\u00f3n": "VIA PRINCIPAL VEREDA BELEN",
    "direccion": "VIA PRINCIPAL VEREDA BELEN",
    "desc_clase": "Industrial",
    "mercado": "REGULADO",
    "estrato_socioeconomico": "0",
    "Sector": "Rurales",
    "Periodicidad": "MENSUAL",
    "valor_recaudado": "$877.507",
    "municipio": "San Pedro",
    "fecha": "2026-08-15",
}

# Datos que busca el informe de facturación
FACT_CLAVES = ["Id_cliente", "numero_factura", "monto_AP", "monto_kwh", "consumo_kwh",
               "Empresa", "Nombre", "direcci\u00f3n", "desc_clase", "mercado",
               "estrato_socioeconomico", "Sector", "Periodicidad"]
# Datos que busca el informe de recaudo
REC_CLAVES = ["Id_cliente", "valor_recaudado", "Empresa", "mercado", "nombre",
              "direccion", "desc_clase", "Sector", "estrato_socioeconomico"]


# Normaliza un texto: quita tildes, símbolos y espacios para comparar fácil
def _norm_col(s):
    if s is None:
        return ""
    t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return "".join(ch for ch in t if ch.isalnum()).lower()


# Devuelve los alias guardados en la base de datos para una clave
def _aliases_columna(clave):
    row = MapeoColumna.query.filter_by(clave=clave).first()
    if row and row.columnas:
        try:
            return json.loads(row.columnas)
        except (TypeError, ValueError):
            return []
    return []


# Guarda un alias nuevo para una clave (aprende de los archivos que se suben)
def _guardar_alias_columna(clave, columna):
    if not clave or not columna:
        return
    aliases = _aliases_columna(clave)
    if not any(_norm_col(a) == _norm_col(columna) for a in aliases):
        aliases.append(columna)
    row = MapeoColumna.query.filter_by(clave=clave).first()
    if not row:
        db.session.add(MapeoColumna(clave=clave, columnas=json.dumps(aliases)))
    else:
        row.columnas = json.dumps(aliases)
    db.session.commit()


_ALIASES_NORM = {_norm_col(k): v for k, v in ALIASES_DEFAULT.items()}


# Separa un texto en "tokens" (palabras sueltas) para comparar por partes
def _tokens(s):
    if s is None:
        return set()
    partes = re.split(r"[^a-zA-Z0-9\u00e0-\u00ff]+", str(s))
    return {_norm_col(p) for p in partes if _norm_col(p)}


# Busca cuál columna real del archivo corresponde a una clave.
# Primero compara el texto completo y luego por palabras sueltas.
def _resolver_una(clave, columnas_reales, excluidas=None):
    excluidas = excluidas or set()
    reales = [c for c in columnas_reales if c not in excluidas]
    norm_reales = {_norm_col(c): c for c in reales}

    aliases = _ALIASES_NORM.get(_norm_col(clave), []) + _aliases_columna(clave)
    vistos = []
    for alias in aliases:
        norm_alias = _norm_col(alias)
        if norm_alias in vistos:
            continue
        vistos.append(norm_alias)
        if not norm_alias:
            continue

        coinciden = {norm_reales[nr] for nr, real in norm_reales.items()
                     if nr == norm_alias}
        if len(coinciden) == 1:
            return coinciden.pop()

    vistos.clear()
    for alias in aliases:
        tokens_alias = _tokens(alias)
        if not tokens_alias:
            continue
        marca = tuple(sorted(tokens_alias))
        if marca in vistos:
            continue
        vistos.append(marca)
        coinciden = set()
        for real in reales:
            if tokens_alias <= _tokens(real):
                coinciden.add(real)
        if len(coinciden) == 1:
            return coinciden.pop()
    return None


# Resuelve todas las claves que se buscan: devuelve el mapeo
# columna_real -> clave y la lista de claves que no se encontraron
def resolver_columnas(claves, columnas_reales):
    mapping = {}
    faltantes = []
    usadas = set()
    for clave in claves:
        real = _resolver_una(clave, columnas_reales, excluidas=usadas)
        if real:
            mapping[real] = clave
            usadas.add(real)
        else:
            faltantes.append(clave)
    return mapping, faltantes
