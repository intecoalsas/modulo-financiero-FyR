# Aquí se guardan la app y la base de datos para que cualquier archivo del
# proyecto pueda usarlas sin líos de "import circular".
# app.py las llena al inicio con init_app(), aquí solo son variables vacías.

app = None
db = None

# Límite de peticiones (se activa en app.py); las rutas lo usan como decorador
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
limiter = Limiter(get_remote_address, default_limits=[])


def init_app(flask_app, sqlalchemy_db):
    global app, db
    app = flask_app
    db = sqlalchemy_db
