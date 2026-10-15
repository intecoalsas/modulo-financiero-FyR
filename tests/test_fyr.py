import pytest

from core.fyr import fyr_agregar, fyr_clave, fyr_estrato


class TestFyr:
    def test_fyr_estrato_valido(self):
        assert fyr_estrato("1") == 1
        assert fyr_estrato("6") == 6

    def test_fyr_estrato_invalido(self):
        assert fyr_estrato("0") is None
        assert fyr_estrato("7") is None
        assert fyr_estrato("abc") is None

    def test_fyr_clave_residencial(self):
        assert fyr_clave("Residencial", "3") == "Residencial – Estrato 3"

    def test_fyr_clave_comercial(self):
        assert fyr_clave("Comercial", "") == "Comercial"

    def test_fyr_clave_otros(self):
        assert fyr_clave("Temporal", "") == "Otros"

    def test_fyr_agregar_totales(self):
        fact = [
            {"Clase": "Residencial", "Estrato": "1", "Sector": "Urbanas",
             "ImpuestoAP": 100.0, "Consumo$": 50.0, "ConsumokWh": 10.0},
            {"Clase": "Comercial", "Estrato": "", "Sector": "Rurales",
             "ImpuestoAP": 200.0, "Consumo$": 80.0, "ConsumokWh": 20.0},
        ]
        rec = [
            {"Clase": "Residencial", "Estrato": "1", "Sector": "Urbanas", "ValorAP": 90.0},
            {"Clase": "Comercial", "Estrato": "", "Sector": "Rurales", "ValorAP": 210.0},
        ]
        res = fyr_agregar(fact, rec)
        assert res["TOTAL"]["n"][2] == 2
        assert res["TOTAL"]["fact"][2] == 300.0
        assert res["TOTAL"]["rec"][2] == 300.0
