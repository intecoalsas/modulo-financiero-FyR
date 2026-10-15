import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# ANTES de importar app: los tests usan su propia BD, nunca informes.db.
# (el config.update después de importar no cambia el motor de SQLAlchemy,
#  por eso los tests estaban borrando la BD real con drop_all)
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_test_informes.db")
os.environ["INFORMES_TEST"] = "1"

import pytest
from app import app as flask_app
from models import db as _db


@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "MAX_CONTENT_LENGTH": 1024 * 1024,
        "WTF_CSRF_ENABLED": False,
    })
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
