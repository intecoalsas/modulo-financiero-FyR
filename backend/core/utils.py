
import json
import numpy as np
import pandas as pd

# Nombres de los meses, sirven para mostrar el periodo con palabras (Ejemplo: "Enero 2026")
MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


# Lee un Excel prefiriendo el motor calamine (mucho más rápido y liviano en
# RAM, clave para archivos grandes como Villavicencio/EMSA); si algo falla
# usa el motor por defecto de pandas
def leer_excel(path, **kwargs):
    try:
        return pd.read_excel(path, engine="calamine", **kwargs)
    except Exception:
        return pd.read_excel(path, **kwargs)


# Convierte un número en formato de dinero colombiano (Ejemplo: 1234567 -> $1.234.567)
def fmt_currency(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "$0"
    return "${:,.0f}".format(v).replace(",", ".")


# Convierte los valores de numpy (que es lo que sale de pandas) a tipo normal de Python
# para poder guardarlos en json o en la base de datos sin errores
def json_safe(obj):
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    return obj


# Según la descripción que viene en el archivo, le asigna la clase del cliente
# (residencial, comercial, etc). Si no encuentra nada, asume Residencial
def detect_clase(desc_clase):
    s = str(desc_clase).lower()
    if "residencial" in s:
        return "Residencial"
    if "comercial" in s:
        return "Comercial"
    if "industrial" in s:
        return "Industrial"
    if "oficial" in s:
        return "Oficial"
    return "Residencial"


# Dice si el sector es urbano o rural según lo que venga en el texto
def detect_sector(sector):
    s = str(sector).lower()
    return "Urbanas" if "urb" in s else "Rurales"
