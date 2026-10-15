

import os
import unicodedata

from flask import Flask, request

# Ruta donde está este archivo (backend/) y de ahí sacamos la carpeta frontend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

# Carpetas donde se guardan los archivos subidos y los informes
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
ORIG_DIR = os.path.join(UPLOAD_DIR, "originales")
GEN_DIR = os.path.join(UPLOAD_DIR, "generados")
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(ORIG_DIR, exist_ok=True)
os.makedirs(GEN_DIR, exist_ok=True)

# Se crea la app de Flask indicándole dónde están las plantillas (html) y los estáticos (css, js)
app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "solo-desarrollo-cambiar-en-produccion")
# Producción (Postgres en la nube) o desarrollo (SQLite local).
# Render/Neon entregan postgres:// : se normaliza al esquema de SQLAlchemy.
_db_url = (os.environ.get("DATABASE_URL") or "").strip()
if _db_url.startswith("postgres://"):
    _db_url = "postgresql+psycopg://" + _db_url[len("postgres://"):]
if not _db_url:
    _db_url = "sqlite:///" + os.path.join(BASE_DIR, "instance", "informes.db")
# La base de datos es un solo archivo sqlite que vive en backend/instance
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Tamaño máximo de subida (MB) por variable de entorno (60 por Villavicencio)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "60")) * 1024 * 1024

# Filtro para mostrar fechas UTC en hora de Colombia (12h AM/PM)
@app.template_filter("hora_col")
def hora_col(dt, fmt="%d/%m/%Y %I:%M %p"):
    if not dt:
        return "—"
    from datetime import timedelta as _td
    return (dt + _td(hours=-5)).strftime(fmt)

# Límite de peticiones (anti-abuso en carga y descargas)
from core.context import limiter
limiter.init_app(app)

# Cabeceras de seguridad solo en producción (en local romperían el http)
if os.environ.get("FLASK_ENV") == "production":
    from flask_talisman import Talisman
    _csp = {
        "default-src": "'self'",
        "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "img-src": ["'self'", "data:"],
    }
    Talisman(app, force_https=True, frame_options="SAMEORIGIN",
             content_security_policy=_csp)

# Se conecta la base de datos con la app
from models import db
db.init_app(app)

# Se le pasan la app y la base de datos a core/context.py para que cualquiera pueda usarlas
from core.context import init_app
init_app(app, db)

# Se registran las rutas (páginas) que están en blueprints/routes.py
from blueprints.routes import bp as main_bp
app.register_blueprint(main_bp)

# Variable que se le manda a todas las plantillas para saber si hay usuarios de San Pedro cargados
def _contexto_global():
    try:
        from models import Comercializadora, Municipio
        sp = Municipio.query.filter_by(nombre="San Pedro").first()
        tiene_sp = bool(sp and Comercializadora.query.filter_by(municipio_id=sp.id).first())
    except Exception:
        tiene_sp = False
    return {"san_pedro_activo": tiene_sp}

app.context_processor(_contexto_global)

with app.app_context():
    db.create_all()

    from sqlalchemy import inspect as sa_inspect, text as sa_text
    from models import Municipio, Comercializadora

    # Por si se actualiza el programa, se agregan las columnas que falten en la tabla de reportes
    _cols = [c["name"] for c in sa_inspect(db.engine).get_columns("reports")]
    if "analisis_ejecutivo" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN analisis_ejecutivo TEXT"))
    if "novedades" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN novedades TEXT"))

    # Lo misme para las comercializadoras
    _cols_com = [c["name"] for c in sa_inspect(db.engine).get_columns("comercializadoras")]
    if "info_especiales" not in _cols_com:
        db.session.execute(sa_text("ALTER TABLE comercializadoras ADD COLUMN info_especiales TEXT"))
    if "analisis_general" not in _cols_com:
        db.session.execute(sa_text("ALTER TABLE comercializadoras ADD COLUMN analisis_general TEXT"))
    if "tarifas" not in _cols_com:
        db.session.execute(sa_text("ALTER TABLE comercializadoras ADD COLUMN tarifas TEXT"))
    if "descripcion" not in _cols_com:
        db.session.execute(sa_text("ALTER TABLE comercializadoras ADD COLUMN descripcion TEXT"))
    if "cartera_acumulada" not in _cols_com:
        db.session.execute(sa_text("ALTER TABLE comercializadoras ADD COLUMN cartera_acumulada TEXT"))
    db.session.commit()

    # Si las tarifas ya estaban guardadas dentro de info_especiales, se pasan a su propio campo
    for _c in Comercializadora.query.all():
        _src = _c.info_especiales or {}
        _dst = dict(_c.tarifas or {})
        changed = False
        if isinstance(_src, dict):
            for _y, _info in _src.items():
                _t = (_info or {}).get("tarifas") if isinstance(_info, dict) else None
                if _t and str(_y) not in _dst:
                    _dst[str(_y)] = _t
                    changed = True
        if changed:
            _c.tarifas = _dst

        # Igual con la descripción, se toma la más reciente si no existía
        if not _c.descripcion and isinstance(_src, dict):
            keys = sorted((int(k) for k in _src if str(k).isdigit()), reverse=True)
            for k in keys:
                _info = _src.get(str(k)) or {}
                _d = _info.get("descripcion") if isinstance(_info, dict) else None
                if _d:
                    _c.descripcion = _d
                    break
    db.session.commit()

    # Normaliza un nombre quitándole tildes y mayúsculas para comparar sin problemas
    def _norm_nombre(s):
        return (unicodedata.normalize("NFKD", s or "")
                .encode("ascii", "ignore").decode("ascii").strip().lower())

# Se aseguran de que existan los municipios y su comercializadora
    for nombre, com in (("San Pedro", "Celsia"), ("Calima El Dari\u00e9n", "Celsia"),
                        ("Andaluc\u00eda", "Celsia"), ("Villavicencio", "EMSA")):
        _m = next(
            (x for x in Municipio.query.all()
             if _norm_nombre(x.nombre) == _norm_nombre(nombre)),
            None,
        )
        if not _m:
            _m = Municipio(nombre=nombre)
            db.session.add(_m)
            db.session.flush()
        if not Comercializadora.query.filter_by(municipio_id=_m.id, nombre=com).first():
            db.session.add(Comercializadora(municipio_id=_m.id, nombre=com))
    db.session.commit()


# Al ejecutar python app.py se enciende el servidor
if __name__ == "__main__":
    app.run(debug=True)
