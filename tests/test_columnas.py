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


class TestFuzzyColumnas:
    def test_nombres_cambiados_o_con_errata(self, app):
        # "Impuesto de Alumbrado" no entra ni exacta ni por tokens
        # (añade "de", le falta "Público"); "Estatro" es errata de "Estrato".
        headers = ["Id_cliente", "Nombre", "Impuesto de Alumbrado",
                   "Estatro Socioeconomico"]
        mapping, faltantes = resolver_columnas(
            ["monto_AP", "estrato_socioeconomico"], headers)
        assert mapping.get("Impuesto de Alumbrado") == "monto_AP"
        assert mapping.get("Estatro Socioeconomico") == "estrato_socioeconomico"
        assert faltantes == []

    def test_no_adivina_entre_dos_similares(self, app):
        # Dos candidatas casi iguales: mejor preguntar que mapear mal.
        headers = ["Impuesto de Alumbrado A", "Impuesto de Alumbrado B"]
        mapping, faltantes = resolver_columnas(["monto_AP"], headers)
        assert faltantes == ["monto_AP"]
        assert mapping == {}

    def test_nada_parecido_no_resuelve(self, app):
        headers = ["Observaciones", "Comentarios varios"]
        mapping, faltantes = resolver_columnas(["monto_AP"], headers)
        assert faltantes == ["monto_AP"]

    def test_fuzzy_aprende_el_alias(self, app):
        from core.columnas import _aliases_columna
        headers = ["Impuesto de Alumbrado"]
        resolver_columnas(["monto_AP"], headers)
        aprendidos = _aliases_columna("monto_AP")
        assert any(_n(a) == _n("Impuesto de Alumbrado") for a in aprendidos)

    def test_alias_aprendido_resuelve_exacto_despues(self, app):
        headers = ["Impuesto de Alumbrado"]
        resolver_columnas(["monto_AP"], headers)  # aprende
        mapping, faltantes = resolver_columnas(["monto_AP"], headers)
        assert mapping.get("Impuesto de Alumbrado") == "monto_AP"
        assert faltantes == []


def _n(s):
    from core.columnas import _norm_col
    return _norm_col(s)
