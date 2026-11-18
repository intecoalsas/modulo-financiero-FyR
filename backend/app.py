

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
# Carga backend/.env en las variables de entorno (sin depender de dotenv).
# Así `python app.py` y `flask run` usan la misma configuración (Turso, IA, etc.).
def _cargar_env():
    ruta = os.path.join(BASE_DIR, ".env")
    try:
        with open(ruta, "r", encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, _, valor = linea.partition("=")
                clave = clave.strip()
                valor = valor.strip().strip('"').strip("'")
                if clave and clave not in os.environ:
                    os.environ[clave] = valor
    except OSError:
        pass


_cargar_env()

# Producción (Turso/Postgres en la nube) o desarrollo (SQLite local).
# DATABASE_URL tiene prioridad (las pruebas lo usan para apuntar a SQLite).
_db_url = (os.environ.get("DATABASE_URL") or "").strip()
if _db_url.startswith("postgres://"):
    _db_url = "postgresql+psycopg://" + _db_url[len("postgres://"):]
# Turso (libSQL): esquema libsql:// o TURSO_DATABASE_URL cuando no hay DATABASE_URL
_turso_url = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
if _db_url:
    if _db_url.startswith("libsql://") or "turso.io" in _db_url:
        os.environ.setdefault("TURSO_DATABASE_URL", _db_url)
        _db_url = "turso:///"
elif _turso_url:
    _db_url = "turso:///"
if not _db_url:
    _db_url = "sqlite:///" + os.path.join(BASE_DIR, "instance", "informes.db")
# Candado: las pruebas NUNCA deben tocar la base real (Turso).
if os.environ.get("INFORMES_TEST") and _db_url == "turso:///":
    raise RuntimeError(
        "Las pruebas no pueden usar Turso. Defina DATABASE_URL a una SQLite "
        "de prueba antes de importar la app.")
# La base de datos es un solo archivo sqlite que vive en backend/instance
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Turso va por HTTP: sin pooling (cada operación con conexión propia)
if _db_url == "turso:///":
    from sqlalchemy.pool import NullPool
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"poolclass": NullPool}
# Tamaño máximo de subida (MB) por variable de entorno (80 para Villavicencio)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "80")) * 1024 * 1024

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

# Los estáticos (style.css, filter_widget.js) viajan en cada página: sin
# caché el navegador los re-descarga en cada pestaña. Los templates ya los
# versionan con ?v=... (base.html, cartera/especiales.html), así que 1 día
# de caché no sirve archivos viejos: al cambiar el archivo se sube la ?v=.
@app.after_request
def _cache_estaticos(respuesta):
    if request.path.startswith(app.static_url_path + "/"):
        respuesta.headers["Cache-Control"] = "public, max-age=86400"
    return respuesta

# Se registra el dialecto de Turso si se va a usar
if _db_url == "turso:///":
    from core.turso_dialect import register as _reg_turso
    _reg_turso()

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
_san_pedro_cache = {"valor": None, "ts": 0}

def _contexto_global():
    try:
        import time as _t
        if _san_pedro_cache["valor"] is None or (_t.time() - _san_pedro_cache["ts"]) > 300:
            from models import Comercializadora, Municipio
            sp = Municipio.query.filter_by(nombre="San Pedro").first()
            _san_pedro_cache["valor"] = bool(sp and Comercializadora.query.filter_by(municipio_id=sp.id).first())
            _san_pedro_cache["ts"] = _t.time()
        tiene_sp = _san_pedro_cache["valor"]
    except Exception:
        tiene_sp = False
    return {"san_pedro_activo": tiene_sp}

app.context_processor(_contexto_global)

# Copia de seguridad automática de la BD SQLite al arrancar:
# a lo sumo una por día, solo si hay informes guardados, y conserva los últimos 15.
def _respaldo_inicio():
    if os.environ.get("INFORMES_TEST"):
        return
    if not _db_url.startswith("sqlite:///"):
        return
    db_path = _db_url[len("sqlite:///"):]
    if not os.path.isfile(db_path):
        return
    import glob as _glob
    import shutil as _shutil
    import sqlite3 as _sqlite3
    from datetime import datetime as _dt

    def _n_informes(p):
        try:
            c = _sqlite3.connect(p)
            n = c.execute("SELECT count(*) FROM reports").fetchone()[0]
            c.close()
            return n
        except Exception:
            return 0

    resp_dir = os.path.join(BASE_DIR, "respaldos")
    os.makedirs(resp_dir, exist_ok=True)
    existentes = sorted(_glob.glob(os.path.join(resp_dir, "informes_*.db")))
    n = _n_informes(db_path)
    if n == 0:
        # Nunca respaldar una BD vacía (no pisar los buenos respaldos)
        if any(_n_informes(p) > 0 for p in existentes):
            print("¡ALERTA! La base de datos no tiene informes guardados."
                  " Restaura con: python scripts/restaurar.py")
        return
    hoy = _dt.now().strftime("%Y%m%d")
    if any(os.path.basename(p).startswith("informes_" + hoy) for p in existentes):
        return
    destino = os.path.join(resp_dir,
                           "informes_" + _dt.now().strftime("%Y%m%d_%H%M%S") + ".db")
    _shutil.copy2(db_path, destino)
    print("Respaldo automático creado:", destino)
    for viejo in sorted(_glob.glob(os.path.join(resp_dir, "informes_*.db")))[:-15]:
        try:
            os.remove(viejo)
        except OSError:
            pass


with app.app_context():
    _respaldo_inicio()
    db.create_all()

    from sqlalchemy import inspect as sa_inspect, text as sa_text
    from models import Municipio, Comercializadora

    # Por si se actualiza el programa, se agregan las columnas que falten en la tabla de reportes
    _cols = [c["name"] for c in sa_inspect(db.engine).get_columns("reports")]
    if "analisis_ejecutivo" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN analisis_ejecutivo TEXT"))
    if "novedades" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN novedades TEXT"))
    if "conclusiones_ia" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN conclusiones_ia TEXT"))
    if "explicaciones_ia" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN explicaciones_ia TEXT"))
    if "page_data" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN page_data TEXT"))
    if "detalle_purged" not in _cols:
        db.session.execute(sa_text("ALTER TABLE reports ADD COLUMN detalle_purged BOOLEAN"))

    # Índice para /general y /especiales (orden por updated_at)
    try:
        db.session.execute(sa_text(
            "CREATE INDEX IF NOT EXISTS ix_report_updated_at ON reports (updated_at)"))
    except Exception:
        pass

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

    # La tabla resumen_mes es nueva; si ya existía sin la columna de
    # estratos (creada antes de la idea #3), se agrega.
    try:
        _cols_res = [c["name"] for c in sa_inspect(db.engine).get_columns("resumen_mes")]
        if "por_estrato" not in _cols_res:
            db.session.execute(sa_text("ALTER TABLE resumen_mes ADD COLUMN por_estrato TEXT"))
    except Exception:
        pass
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


# ---------------------------------------------------------------------------
# Precalentamiento al arrancar (solo con Turso). Con Turso cada consulta
# cuesta ~0,13 s + una petición HTTP, y la primera además paga el TLS del
# keep-alive: la primera visita de la mañana puede pasar de 1 s. Aquí se
# abren la conexión y los cachés ANTES de que llegue el primer usuario:
#   - SELECT 1: establece la conexión HTTP (httpx keep-alive)
#   - municipios (_municipios_cache, TTL 5 min)
#   - municipio más reciente e historial sin filtros (_hist_cache, TTL 5 min)
#   - san_pedro_activo (contexto de todas las plantillas)
# Corre en un hilo daemon: no bloquea el arranque del servidor. Se omite
# en pruebas (INFORMES_TEST) y en SQLite local (no hay nada que calentar).
# OJO: no se precarga el blob de /api/detalle (_detalle_cache): son 33 MB
# que no se deben descargar si nadie abre esa pestaña.
# ---------------------------------------------------------------------------
_precalentar_flag = {"iniciado": False}


def _precalentar():
    if _precalentar_flag["iniciado"]:
        return
    _precalentar_flag["iniciado"] = True

    import threading as _threading
    import time as _time

    def _trabajo():
        inicio = _time.time()
        try:
            with app.app_context():
                from sqlalchemy import text as _sa_text
                from services.report_service import get_municipios
                from blueprints.routes import _datos_historial, _muni_ultimo
                # Conexión (TLS + keep-alive de Turso) con la consulta más barata
                db.session.execute(_sa_text("SELECT 1"))
                _contexto_global()               # caché de San Pedro
                get_municipios()                 # municipios para los desplegables
                _muni_ultimo()                   # municipio del último informe
                _datos_historial(None, None, None)  # historial sin filtros
                _precargar_cartera_sp()          # cartera de San Pedro si está vacía
            print(f"Precalentamiento listo en {_time.time() - inicio:.1f} s "
                  f"(conexión, municipios e historial).")
        except Exception as _exc:
            print("Precalentamiento omitido (la app funciona igual):", _exc)
        finally:
            try:
                db.session.remove()
            except Exception:
                pass

    _threading.Thread(target=_trabajo, daemon=True, name="precalentar").start()


# ---------------------------------------------------------------------------
# Precarga de la cartera de San Pedro: si la cartera acumulada está vacía
# (ambiente nuevo o BD restaurada sin cartera) y existe el libro de
# referencia "Clientes Especiales SP 2026.xlsx", se carga sola al arrancar
# y no hace falta subirla a mano por /cartera. La ruta se indica con
# CARTERA_REFERENCIA en .env; si no, se toma el .xlsx más nuevo dentro de
# backend/uploads/referencia/. NUNCA toca una cartera que ya tiene años
# cargados; si algo falla, la app arranca igual (queda el camino manual).
# ---------------------------------------------------------------------------
def _precargar_cartera_sp():
    """Abre su propio app_context si no hay uno (el arranque a nivel de
    módulo corre fuera de contexto; el precalentamiento ya trae el suyo)."""
    if os.environ.get("INFORMES_TEST"):
        return
    from flask import has_app_context
    if has_app_context():
        return _precargar_cartera_trabajo()
    with app.app_context():
        return _precargar_cartera_trabajo()


def _precargar_cartera_trabajo():
    try:
        from models import Comercializadora, Municipio
        from core.core import (cargar_cartera_desde_referencia,
                               carteras_anios, ANIO_BASE_CARTERA)
        sp = Municipio.query.filter(Municipio.nombre.ilike("San Pedro")).first()
        if not sp:
            return
        com = Comercializadora.query.filter_by(municipio_id=sp.id).first()
        if not com or carteras_anios(com):
            return  # ya tiene cartera cargada: no se toca nada

        ruta = (os.environ.get("CARTERA_REFERENCIA") or "").strip().strip('"')
        if not ruta:
            carpeta = os.path.join(UPLOAD_DIR, "referencia")
            if os.path.isdir(carpeta):
                candidatos = sorted(
                    (os.path.join(carpeta, f) for f in os.listdir(carpeta)
                     if f.lower().endswith((".xlsx", ".xls"))),
                    key=os.path.getmtime, reverse=True)
                ruta = candidatos[0] if candidatos else ""
        if not ruta or not os.path.isfile(ruta):
            print("Cartera SP vacía y sin libro de referencia "
                  "(CARTERA_REFERENCIA en .env o backend/uploads/referencia/). "
                  "Se puede cargar a mano en /cartera.")
            return
        cargar_cartera_desde_referencia(com, ruta, ANIO_BASE_CARTERA)
        print("Cartera de San Pedro precargada desde:", os.path.basename(ruta))
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        print("Precarga de cartera omitida (se puede cargar a mano en /cartera):", exc)


if _db_url == "turso:///" and not os.environ.get("INFORMES_TEST"):
    _precalentar()
elif _db_url.startswith("sqlite") and not os.environ.get("INFORMES_TEST"):
    # En SQLite local no hace falta precalentar nada, pero la cartera de
    # San Pedro vacía sí se auto-carga (retorna al instante si ya existe).
    _precargar_cartera_sp()


# ---------------------------------------------------------------------------
# Keep-alive anti "cold start": en el plan gratuito de Render la app se apaga
# tras ~15 min sin tráfico y la siguiente visita espera ~1 min. Este hilo
# visita /salud (200 al instante, SIN tocar la base de datos) cada 14 min
# SOLO dentro de una ventana horaria: la app duerme de noche y no consume
# horas extra del plan. Las horas se interpretan en hora de Colombia
# (Render corre en UTC, se restan las 5 horas de la diferencia).
# Configuración en .env (todo opcional):
#   KEEP_ALIVE_URL   URL pública de la app. Por defecto toma la variable
#                    RENDER_EXTERNAL_URL que Render define solo. Vacío u
#                    "off" desactiva el hilo (en local no hay URL y no corre).
#   KEEP_ALIVE_HORAS Ventana despierta: "6-20" = 6:00 a 19:59 (Colombia).
#   KEEP_ALIVE_DIAS  Días de la semana: 1=lunes ... 7=domingo. "1-6" =
#                    lunes a sábado (por defecto).
# OJO: si la app ya está dormida al empezar la ventana, nadie la despierta
# (el hilo vive dentro de la app). Solo afecta a la primera visita de la
# jornada; para arrancarla a una hora fija sirve un ping externo a /salud.
# ---------------------------------------------------------------------------
def _keep_alive():
    url = (os.environ.get("KEEP_ALIVE_URL")
           or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not url or url.lower() == "off" or os.environ.get("INFORMES_TEST"):
        return

    import threading as _threading
    import time as _time
    import urllib.request as _urllib_req

    def _rango(txt, lo, hi):
        a, _, b = (txt or "").partition("-")
        try:
            ini = max(lo, int(a))
        except ValueError:
            ini = lo
        try:
            fin = min(hi, int(b))
        except ValueError:
            fin = hi
        return ini, fin

    h_ini, h_fin = _rango(os.environ.get("KEEP_ALIVE_HORAS", "6-20"), 0, 24)
    d_ini, d_fin = _rango(os.environ.get("KEEP_ALIVE_DIAS", "1-6"), 1, 7)

    def _trabajo():
        while True:
            try:
                # Hora de Colombia = UTC - 5; tm_wday: 0=lunes -> 1..7
                ahora = _time.gmtime()
                hora_col = (ahora.tm_hour - 5) % 24
                dia = ahora.tm_wday + 1
                if d_ini <= dia <= d_fin and h_ini <= hora_col < h_fin:
                    _urllib_req.urlopen(url + "/salud", timeout=30).read()
            except Exception as _exc:
                print("Keep-alive: ping falló:", _exc)
            _time.sleep(14 * 60)

    _threading.Thread(target=_trabajo, daemon=True, name="keep-alive").start()
    print(f"Keep-alive activo ({url}/salud, {h_ini}-{h_fin} h Colombia).")


_keep_alive()


# Al ejecutar python app.py se enciende el servidor
if __name__ == "__main__":
    app.run(debug=True)
