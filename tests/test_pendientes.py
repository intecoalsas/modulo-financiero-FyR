import json
import pytest

from services.pendientes import get_pendiente, set_pendiente, del_pendiente


class TestPendientes:
    def test_guardar_y_recuperar(self, app):
        with app.app_context():
            set_pendiente("test-token", {"municipio": "San Pedro", "anio": 2026})
            datos = get_pendiente("test-token")
            assert datos["municipio"] == "San Pedro"

    def test_del_pendiente(self, app):
        with app.app_context():
            set_pendiente("test-token-2", {"municipio": "Calima"})
            del_pendiente("test-token-2")
            assert get_pendiente("test-token-2") is None

    def test_get_inexistente(self, app):
        with app.app_context():
            assert get_pendiente("no-existe") is None

    def test_del_vacio_no_falla(self, app):
        with app.app_context():
            del_pendiente("no-existe")
