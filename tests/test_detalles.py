import io

import pytest

from core.core import save_report_to_db, depurar_detalles_antiguos
from models import db, AlertaReporte, Report, ResumenMes


GD = {"f": {"total_imp": 1000, "total_consumo": 400, "total_kwh": 10, "cuentas": 2},
      "r": {"total_valor": 900, "cuentas": 2},
      "facturacion": [{"Id_cliente": "C1", "Nombre": "Uno", "ImpuestoAP": 1000,
                       "Consumo$": 400, "ConsumokWh": 10}],
      "recaudo": [{"Id_cliente": "C1", "Nombre": "Uno", "ValorAP": 900}],
      "estad_general": {"Total registros base original": 10,
                        "Usuarios únicos (ID de cuenta)": 2},
      "estad_recaudo": {"Total registros base original": 10,
                        "Usuarios únicos (ID de cuenta)": 2},
      "consolidado": {}, "clase_tabla": [], "sector_tabla": [],
      "banderas": {}, "resumen_financiero": {}, "resumen_recaudo": {}}
ESP = {"filas": [{"id": "C1", "nombre": "Uno", "clase": "Residencial",
                  "tarifa_minima": 3500, "consumo": 400, "facturacion": 1000,
                  "recaudo": 900, "verificado": "SI", "periodo": "Mensual",
                  "calc_iap": 1000, "saldo_fl": -100, "pct_cee": 0.9,
                  "val_rec": -100, "val_tarifa_pct": "Residencial",
                  "val_tarifa_min": "Residencial"}],
       "grupos": ["Residencial"],
       "por_clase": {"Residencial": {"n": 1, "fact": 1000, "rec": 900,
                                     "consumo": 400}},
       "totales": {"saldo_neg": -100}}


def _guardar(municipio, comerc, anio, mes):
    return save_report_to_db(municipio, comerc, anio, mes, dict(GD), dict(ESP))


class TestDepuracionDetalles:
    def test_al_siente_solo_los_6_mas_recientes(self, app):
        ids = []
        # 7 informes del mismo municipio: el más antiguo (junio) queda fuera
        for mes in range(6, 13):
            r = _guardar("San Pedro", "Celsia", 2026, mes)
            ids.append(r.id)
        primero = db.session.get(Report, ids[0])
        ultimo = db.session.get(Report, ids[-1])
        assert primero.detalle_purged is True
        assert primero.general_data is None
        # El resumen del informe depurado sigue guardado
        assert primero.page_data
        assert primero.especiales_data
        assert AlertaReporte.query.get(primero.id) is not None
        assert ResumenMes.query.get(primero.id) is not None
        # Los últimos 6 conservan el detalle
        assert ultimo.detalle_purged in (False, None)
        assert ultimo.general_data is not None
        conservados = [db.session.get(Report, i) for i in ids[-6:]]
        assert all(r.general_data is not None for r in conservados)

    def test_otra_comercializadora_no_se_toca(self, app):
        _guardar("Villavicencio", "EMSA", 2026, 1)
        for mes in range(2, 9):
            _guardar("San Pedro", "Celsia", 2026, mes)
        villavo = (Report.query.join(Report.comercializadora)
                   .filter(Report.comercializadora.has(nombre="EMSA")).first())
        assert villavo.general_data is not None
        assert villavo.detalle_purged in (False, None)

    def test_conservar_detalles_configurable(self, app):
        import core.core as core
        original = core._conservar_detalles
        try:
            os_val = __import__("os").environ
            os_val["CONSERVAR_DETALLES"] = "2"
            ids = [_guardar("San Pedro", "Celsia", 2026, m).id
                   for m in range(1, 4)]
            assert db.session.get(Report, ids[0]).detalle_purged is True
            assert db.session.get(Report, ids[1]).detalle_purged in (False, None)
        finally:
            os_val.pop("CONSERVAR_DETALLES", None)
            core._conservar_detalles = original


class TestDescargaDetalleExcel:
    def test_descarga_con_datos(self, app, client):
        r = _guardar("San Pedro", "Celsia", 2026, 7)
        resp = client.get(f"/api/detalle/excel/{r.id}")
        assert resp.status_code == 200
        cuerpo = resp.get_data()
        assert cuerpo[:2] == b"PK"  # xlsx real
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(cuerpo), read_only=True)
        ws = wb.active
        filas = list(ws.iter_rows(values_only=True))
        assert filas[0][:3] == ("#", "ID", "Nombre")
        assert filas[1][1] == "C1"
        assert len(filas) == 2

    def test_descarga_informe_depurado_redirige(self, app, client):
        for mes in range(1, 9):
            _guardar("San Pedro", "Celsia", 2026, mes)
        primero = (Report.query.order_by(Report.anio, Report.mes)
                   .filter(Report.detalle_purged.is_(True)).first())
        resp = client.get(f"/api/detalle/excel/{primero.id}")
        assert resp.status_code == 302  # flash + redirige a la página

    def test_api_detalle_410_si_depurado(self, app, client):
        for mes in range(1, 9):
            _guardar("San Pedro", "Celsia", 2026, mes)
        primero = (Report.query.order_by(Report.anio, Report.mes)
                   .filter(Report.detalle_purged.is_(True)).first())
        resp = client.get(f"/api/detalle/{primero.id}")
        assert resp.status_code == 410

    def test_descarga_excel_profesional_guardia(self, app, client):
        for mes in range(1, 9):
            _guardar("San Pedro", "Celsia", 2026, mes)
        primero = (Report.query.order_by(Report.anio, Report.mes)
                   .filter(Report.detalle_purged.is_(True)).first())
        resp = client.get(f"/descargar/excel/{primero.id}")
        assert resp.status_code == 302

    def test_exportar_especiales_por_report_id(self, app, client):
        r = _guardar("San Pedro", "Celsia", 2026, 7)
        resp = client.get(f"/exportar/especiales/{r.id}")
        assert resp.status_code == 200
        assert resp.get_data()[:2] == b"PK"


class TestPaginaGeneralDepurada:
    def test_general_id_muestra_aviso(self, app, client):
        for mes in range(1, 9):
            _guardar("San Pedro", "Celsia", 2026, mes)
        primero = (Report.query.order_by(Report.anio, Report.mes)
                   .filter(Report.detalle_purged.is_(True)).first())
        resp = client.get(f"/general/{primero.id}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Detalle depurado" in html or "detalle fue depurado" in html
