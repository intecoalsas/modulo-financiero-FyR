import pandas as pd
import pytest

from core.depuracion import depurar_facturacion, depurar_recaudo


def _fact_df():
    return pd.DataFrame({
        "Id_cliente": [1, 2, 3],
        "numero_factura": ["F1", "F2", "F3"],
        "monto_AP": [100.0, 200.0, 300.0],
        "monto_kwh": [50.0, 60.0, 70.0],
        "consumo_kwh": [10.0, 12.0, 14.0],
        "Empresa": ["Celsia"] * 3,
        "Nombre": ["A", "B", "C"],
        "dirección": ["Dir1", "Dir2", "Dir3"],
        "desc_clase": ["Residencial", "Comercial", "Industrial"],
        "mercado": ["REGULADO"] * 3,
        "estrato_socioeconomico": [1, 2, 3],
        "Sector": ["Urbano", "Rural", "Urbano"],
        "Periodicidad": ["Mensual"] * 3,
    })


def _rec_df():
    return pd.DataFrame({
        "Id_cliente": [1, 2, 3],
        "valor_recaudado": [90.0, 210.0, 280.0],
        "Empresa": ["Celsia"] * 3,
        "mercado": ["REGULADO"] * 3,
        "nombre": ["A", "B", "C"],
        "direccion": ["Dir1", "Dir2", "Dir3"],
        "desc_clase": ["Residencial", "Comercial", "Industrial"],
        "Sector": ["Urbano", "Rural", "Urbano"],
        "estrato_socioeconomico": [1, 2, 3],
    })


class TestDepurarFacturacion:
    def test_cuenta_unica_suma_todo(self):
        df = _fact_df()
        r = depurar_facturacion(df)
        assert r["cuentas"] == 3
        assert r["total_imp"] == 600.0
        assert r["total_consumo"] == 180.0
        assert r["total_kwh"] == 36.0

    def test_misma_factura_no_duplica_consumo(self):
        df = pd.DataFrame({
            "Id_cliente": [1, 1],
            "numero_factura": ["F1", "F1"],
            "monto_AP": [100.0, 100.0],
            "monto_kwh": [50.0, 50.0],
            "consumo_kwh": [10.0, 10.0],
            "Empresa": ["Celsia", "Celsia"],
            "Nombre": ["A", "A"],
            "dirección": ["D", "D"],
            "desc_clase": ["Residencial", "Residencial"],
            "mercado": ["REGULADO", "REGULADO"],
            "estrato_socioeconomico": [1, 1],
            "Sector": ["Urbano", "Urbano"],
            "Periodicidad": ["Mensual", "Mensual"],
        })
        r = depurar_facturacion(df)
        assert r["cuentas"] == 1
        assert r["total_imp"] == 200.0
        assert r["total_consumo"] == 50.0
        assert r["total_kwh"] == 10.0
        assert r["flags"]["REFACTURACION - MISMA FACTURA"] == 1

    def test_consumo_duplicado_excluye_consumo(self):
        df = pd.DataFrame({
            "Id_cliente": [1, 1],
            "numero_factura": ["F1", "F2"],
            "monto_AP": [100.0, 100.0],
            "monto_kwh": [50.0, 50.0],
            "consumo_kwh": [10.0, 10.0],
            "Empresa": ["Celsia", "Celsia"],
            "Nombre": ["A", "A"],
            "dirección": ["D", "D"],
            "desc_clase": ["Residencial", "Residencial"],
            "mercado": ["REGULADO", "REGULADO"],
            "estrato_socioeconomico": [1, 1],
            "Sector": ["Urbano", "Urbano"],
            "Periodicidad": ["Mensual", "Mensual"],
        })
        r = depurar_facturacion(df)
        assert r["total_consumo"] == 50.0
        assert r["flags"]["CONSUMO DUPLICADO - EXCLUIR CONSUMO"] == 1


class TestDepurarRecaudo:
    def test_suma_por_cuenta(self):
        df = _rec_df()
        r = depurar_recaudo(df)
        assert r["cuentas"] == 3
        assert r["total_valor"] == 580.0

    def test_duplicados_sumados(self):
        df = pd.DataFrame({
            "Id_cliente": [1, 1, 2],
            "valor_recaudado": [50.0, 30.0, 100.0],
            "Empresa": ["C"] * 3,
            "mercado": ["R"] * 3,
            "nombre": ["A", "A", "B"],
            "direccion": ["D", "D", "D"],
            "desc_clase": ["Residencial", "Residencial", "Comercial"],
            "Sector": ["U", "U", "R"],
            "estrato_socioeconomico": [1, 1, 2],
        })
        r = depurar_recaudo(df)
        assert r["cuentas"] == 2
        assert r["total_valor"] == 180.0
