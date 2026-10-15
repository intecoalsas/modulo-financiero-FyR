
# Guarda las cargas que quedaron a medio hacer (cuando al subir los archivos
# les falta algún dato como el municipio o una columna).

import json
from datetime import datetime, timedelta

from models import db, CargaPendiente, ahora_utc

# Días que dura la sesión pendiente antes de borrarse sola
_DIAS_VIGENCIA = 7


# Trae los datos guardados de una carga pendiente por su token
def get_pendiente(token):
    if not token:
        return None
    row = CargaPendiente.query.get(token)
    if not row:
        return None
    try:
        return json.loads(row.datos)
    except (TypeError, ValueError):
        return None


# Guarda los datos de una carga pendiente (y borra las que ya vencieron)
def set_pendiente(token, datos):
    row = CargaPendiente.query.get(token)
    payload = json.dumps(datos)
    if row:
        row.datos = payload
    else:
        db.session.add(CargaPendiente(token=token, datos=payload))
    limite = ahora_utc() - timedelta(days=_DIAS_VIGENCIA)
    CargaPendiente.query.filter(CargaPendiente.creado < limite).delete(synchronize_session=False)
    db.session.commit()


# Borra una carga pendiente (cuando el usuario ya completó los datos)
def del_pendiente(token):
    row = CargaPendiente.query.get(token) if token else None
    if row:
        db.session.delete(row)
        db.session.commit()
