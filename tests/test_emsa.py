import pandas as pd
import pytest

from core.emsa import (
    MUNICIPIO, COMERCIALIZADORA, TARIFAS_LCEE_2026,
    _str, _num, _id, _nombre,
)


class TestEmsaUtils:
    def test_str_vacio_si_none(self):
        assert _str(None) == ""

    def test_str_limpia_espacios(self):
        assert _str("  hola  ") == "hola"

    def test_num_parsea_coma(self):
        assert _num("1,234") == 1234.0

    def test_num_none_si_no_numerico(self):
        assert _num("abc") is None

    def test_id_entero(self):
        assert _id(123.0) == 123

    def test_id_decimal(self):
        assert _id(123.45) == 123.45

    def test_nombre_con_razon(self):
        assert _nombre("A", "B", "C", "D", "RAZON") == "RAZON"

    def test_nombre_sin_razon(self):
        assert _nombre("A", "B", "C", "D", "") == "C D A B"


class TestEmsaConfig:
    def test_municipio_constante(self):
        assert MUNICIPIO == "Villavicencio"

    def test_comercializadora_constante(self):
        assert COMERCIALIZADORA == "EMSA"

    def test_tarifas_lcee_tiene_residenciales(self):
        assert "residenciales" in TARIFAS_LCEE_2026["lcee"]
        assert len(TARIFAS_LCEE_2026["lcee"]["residenciales"]) == 6
