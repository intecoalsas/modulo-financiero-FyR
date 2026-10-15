import pytest

from core.core import build_especiales, texto_ejecutivo, variacion_saldo_neg


class TestBuildEspeciales:
    def test_construye_desde_lista_fija(self):
        data = build_especiales(mes=7)
        assert "filas" in data
        assert len(data["filas"]) > 0
        assert "totales" in data
        assert "analisis" in data
        assert data["totales"]["cuentas"] == len(data["filas"])

    def test_calcula_saldo_fl(self):
        data = build_especiales(mes=7)
        for fila in data["filas"]:
            assert fila["saldo_fl"] == fila["facturacion"] - fila["calc_iap"]

    def test_cuentas_sin_facturar(self):
        data = build_especiales(mes=7)
        sin_facturar = [f for f in data["filas"] if f["facturacion"] == 0]
        assert len(sin_facturar) > 0
        assert all(f["verificado"] == "NO" for f in sin_facturar)


class TestTextoEjecutivo:
    def test_genera_texto_con_datos(self):
        data = build_especiales(mes=7)
        texto = texto_ejecutivo(
            municipio="San Pedro", comercializadora="Celsia",
            anio=2026, mes=7, data=data, variacion=None)
        assert isinstance(texto, str)
        assert len(texto) > 50
        assert "San Pedro" in texto

    def test_con_variacion_positiva(self):
        data = build_especiales(mes=7)
        texto = texto_ejecutivo(
            municipio="San Pedro", comercializadora="Celsia",
            anio=2026, mes=7, data=data, variacion=15.5)
        assert "disminuyó" in texto

    def test_con_variacion_negativa(self):
        data = build_especiales(mes=7)
        texto = texto_ejecutivo(
            municipio="San Pedro", comercializadora="Celsia",
            anio=2026, mes=7, data=data, variacion=-10.0)
        assert "incrementó" in texto
