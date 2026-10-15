import pytest

from core.columnas import (
    ALIASES_DEFAULT, ETIQUETAS_CLAVE, EJEMPLOS_CLAVE,
    FACT_CLAVES, REC_CLAVES, resolver_columnas, _resolver_una,
)


class TestResolverColumnas:
    def test_resuelve_alias_exactos(self, app):
        headers = ["Id_cliente", "Nombre", "Valor AP", "Impuesto Alumbrado Público"]
        mapping, faltantes = resolver_columnas(["Id_cliente", "monto_AP"], headers)
        assert "Id_cliente" in mapping.values()
        assert "monto_AP" in mapping.values()

    def test_resuelve_sin_tildes(self, app):
        headers = ["Identificación", "Dirección"]
        mapping, faltantes = resolver_columnas(["Id_cliente", "dirección"], headers)
        assert mapping.get("Identificación") == "Id_cliente"

    def test_faltantes_vacios_si_todo_resuelve(self, app):
        headers = ["Id_cliente", "numero_factura", "monto_AP", "monto_kwh", "consumo_kwh",
                   "Empresa", "Nombre", "dirección", "desc_clase", "mercado",
                   "estrato_socioeconomico", "Sector", "Periodicidad"]
        mapping, faltantes = resolver_columnas(FACT_CLAVES, headers)
        assert faltantes == []

    def test_no_duplica_columnas(self, app):
        headers = ["Id_cliente", "Nombre"]
        mapping, faltantes = resolver_columnas(["Id_cliente", "Nombre"], headers)
        assert len(set(mapping.keys())) == 2
