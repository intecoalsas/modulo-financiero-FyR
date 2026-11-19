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


class TestCacheUnionCuentas:
    def test_informe_sin_bloques_responde_preparando(self, app, client, monkeypatch):
        """Informe viejo sin bloques: 202 y a la cola, sin cargar el blob."""
        from blueprints import routes
        from core import detalle_store
        r = _guardar("San Pedro", "Celsia", 2026, 7)
        detalle_store.borrar(r.id)
        db.session.commit()

        def prohibido(*a, **k):
            raise AssertionError("no debe cargar general_data")
        monkeypatch.setattr(routes, "_datos_detalle", prohibido)
        resp = client.get(f"/api/detalle/{r.id}?tipo=cuentas&pagina=1&por_pagina=50")
        assert resp.status_code == 202 and resp.get_json()["preparando"]
        assert client.get(f"/api/valores/{r.id}?tipo=cuentas&col=1").status_code == 202
        assert client.get(f"/api/detalle/excel/{r.id}?tipo=cuentas").status_code == 302
        assert r.id in detalle_store._mig_prioridad
        assert r.id in detalle_store._pendientes()
        # El hilo lo trocea (aquí se llama directo) y ya responde normal
        detalle_store.trocear_desde_bd(r.id)
        assert r.id not in detalle_store._pendientes()
        d = client.get(f"/api/detalle/{r.id}?tipo=cuentas&pagina=1&por_pagina=50").get_json()
        assert d["total"] == 1 and d["filas"][0]["ValorAP"] == 900
        detalle_store._mig_prioridad.clear()

    def test_invalidar_cache_limpia_la_union(self, app, client):
        from blueprints import routes
        r = _guardar("San Pedro", "Celsia", 2026, 7)
        client.get(f"/api/detalle/{r.id}?tipo=cuentas&pagina=1&por_pagina=50")
        routes._invalidar_cache()
        assert routes._detalle_cache["cuentas"] is None
        assert routes._detalle_cache["datos"] is None


# ---- Detalle troceado (detalle_bloques): nunca se carga el blob ----
def _gd_grande(n):
    fact = [{"Id_cliente": f"C{i}", "Nombre": f"Cliente {i}",
             "Clase": "Residencial" if i % 3 else "Comercial",
             "Sector": "Urbano" if i % 2 else "Rural",
             "ImpuestoAP": i, "Consumo$": 2 * i, "ConsumokWh": 0} for i in range(n)]
    # recaudo con una cuenta repetida y una que no está en facturación
    rec = [{"Id_cliente": "C1", "ValorAP": 5}, {"Id_cliente": "C1", "ValorAP": 7},
           {"Id_cliente": "ZZ", "Nombre": "Solo recaudo", "Clase": "Oficial",
            "ValorAP": 9}]
    gd = dict(GD)
    gd["facturacion"] = fact
    gd["recaudo"] = rec
    return gd


class TestDetalleTroceado:
    def _guardar_grande(self, n=2500):
        return save_report_to_db("San Pedro", "Celsia", 2026, 7, _gd_grande(n), dict(ESP))

    def _sin_blob(self, monkeypatch):
        from blueprints import routes

        def prohibido(*a, **k):
            raise AssertionError("no debe cargar general_data")
        monkeypatch.setattr(routes, "_datos_detalle", prohibido)

    def test_guardar_crea_bloques(self, app):
        from core import detalle_store
        r = self._guardar_grande()
        m = detalle_store.meta(r.id)
        assert m["total"] == 2501 and m["tam"] == detalle_store.TAM

    def test_mismo_resultado_que_camino_antiguo(self, app, client):
        from core import detalle_store
        from blueprints import routes
        r = self._guardar_grande()
        urls = [f"/api/detalle/{r.id}?tipo=cuentas&pagina=2&por_pagina=1000",
                f"/api/detalle/{r.id}?tipo=cuentas&pagina=3&por_pagina=1000",
                f"/api/detalle/{r.id}?tipo=cuentas&pagina=1&por_pagina=50&f=%7B%223%22%3A%22comer%22%7D",
                f"/api/detalle/{r.id}?tipo=cuentas&pagina=1&por_pagina=50&e=%7B%224%22%3A%5B%22Rural%22%5D%7D",
                f"/api/detalle/{r.id}?tipo=cuentas&e=%7B%224%22%3A%5B%5D%7D",
                f"/api/valores/{r.id}?tipo=cuentas&col=3",
                f"/api/valores/{r.id}?tipo=cuentas&col=2&q=client%2099"]
        nuevos = [client.get(u).get_json() for u in urls]
        # Referencia: el camino antiguo en memoria (/api/detalle sin id)
        # con los mismos datos tras un viaje por JSON (como en la BD)
        import json as _json
        routes.DATA["general"] = _json.loads(_json.dumps(_gd_grande(2500)))
        try:
            viejos = [client.get(u.replace(f"/{r.id}?", "?")).get_json() for u in urls]
        finally:
            routes.DATA.pop("general", None)
        assert nuevos == viejos
        assert nuevos[1]["filas"][-1]["Id_cliente"] == "ZZ"
        assert nuevos[4]["total"] == 0
        # Trocear leyendo el blob por partes da exactamente lo mismo
        detalle_store.trocear_desde_bd(r.id)
        assert [client.get(u).get_json() for u in urls] == nuevos

    def test_no_carga_el_blob(self, app, client, monkeypatch):
        r = self._guardar_grande()
        self._sin_blob(monkeypatch)
        d = client.get(f"/api/detalle/{r.id}?tipo=cuentas&pagina=1&por_pagina=1000").get_json()
        assert d["total"] == 2501 and len(d["filas"]) == 1000
        assert d["filas"][1]["ValorAP"] == 12
        assert client.get(f"/api/valores/{r.id}?tipo=cuentas&col=4").status_code == 200
        resp = client.get(f"/api/detalle/excel/{r.id}?tipo=cuentas")
        assert resp.status_code == 200 and resp.get_data()[:2] == b"PK"

    def test_eliminar_y_depurar_borran_bloques(self, app, client):
        from models import DetalleBloque
        r = self._guardar_grande(10)
        client.post(f"/reporte/{r.id}/eliminar")
        assert DetalleBloque.query.filter_by(report_id=r.id).count() == 0
        ids = [_guardar("San Pedro", "Celsia", 2026, mes).id for mes in range(1, 9)]
        depurados = [i for i in ids if Report.query.get(i).detalle_purged]
        assert depurados
        assert DetalleBloque.query.filter(DetalleBloque.report_id.in_(depurados)).count() == 0


def test_turso_executemany_agrupa_en_lotes(monkeypatch):
    from core import turso_dbapi
    conn = turso_dbapi.Connection(url="https://x.turso.io", auth_token="t")
    enviados = []

    def falso(reqs, baton=None):
        enviados.append(reqs)
        return {"results": [{"response": {"result": {"affected_row_count": 1}}}
                            for r in reqs if r["type"] == "execute"]}
    monkeypatch.setattr(conn, "_pipeline", falso)
    cur = conn.cursor().executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(60)])
    assert len(enviados) == 3                      # 25 + 25 + 10
    assert sum(1 for r in enviados[0] if r["type"] == "execute") == 25
    assert enviados[0][-1] == {"type": "close"}
    assert cur.rowcount == 60


# ---- Lector del blob por partes (sin cargar el JSON entero) ----
def _gz(obj):
    import gzip as _gzip
    import json as _json
    return _gzip.compress(_json.dumps(obj, ensure_ascii=False).encode("utf-8"))


class TestLectorPorPartes:
    def test_igual_que_unir_cuentas_con_textos_raros(self):
        from core import detalle_store as ds
        fact = [{"Id_cliente": i, "Nombre": 'Ñandú "x" ]}{[, \ ' + "á" * (i % 7),
                 "Clase": None if i % 5 == 0 else "Residencial", "Sector": "",
                 "ImpuestoAP": i * 1.5, "Consumo$": None, "ConsumokWh": 3}
                for i in range(3000)]
        rec = [{"Id_cliente": i % 3100, "Nombre": "R", "Clase": "Oficial",
                "Sector": "Rural", "ValorAP": 2} for i in range(0, 6200, 2)]
        gd = {"clase_orig": [["a", 1]], "f": {"registros": [{"x": "]"}] * 50},
              "vacia": [], "dic": {}, "num": -1.5e-3, "facturacion": fact,
              "recaudo": rec, "r": {"registros": [1, 2, 3]}}
        nombres = [c for c in ds.CAMPOS_CUENTAS if c]
        esperado = [[d.get(c) for c in nombres] for d in ds.unir_cuentas(fact, rec)]
        assert ds.unir_cuentas_desde_blob(_gz(gd)) == esperado

    def test_recaudo_antes_que_facturacion(self):
        from core import detalle_store as ds
        fact = [{"Id_cliente": "A", "Nombre": "", "ImpuestoAP": 1}]
        rec = [{"Id_cliente": "B", "Nombre": "Bee", "ValorAP": 1},
               {"Id_cliente": "A", "Nombre": "Aa", "ValorAP": 2}]
        nombres = [c for c in ds.CAMPOS_CUENTAS if c]
        esperado = [[d.get(c) for c in nombres] for d in ds.unir_cuentas(fact, rec)]
        assert ds.unir_cuentas_desde_blob(_gz({"recaudo": rec, "facturacion": fact})) == esperado

    def test_buffer_chico_obliga_a_leer_por_trozos(self, monkeypatch):
        """Con trozos de pocos bytes las filas quedan partidas entre lecturas."""
        import io
        import gzip as _gzip
        from core import detalle_store as ds
        fact = [{"Id_cliente": i, "Nombre": "n" * 40, "ImpuestoAP": 12345.678}
                for i in range(200)]
        original = ds._LectorJson._llenar

        def llenar_chico(self, minimo=1 << 20):
            # Solo el llenado "normal" es chico; los pedidos de más datos de
            # valor() (fila incompleta) se respetan, como en producción
            return original(self, 7 if minimo == 1 << 20 else minimo)
        monkeypatch.setattr(ds._LectorJson, "_llenar", llenar_chico)
        texto = io.TextIOWrapper(_gzip.GzipFile(fileobj=io.BytesIO(_gz({"facturacion": fact}))),
                                 encoding="utf-8")
        texto.read = (lambda f: (lambda n=-1: f(5)))(texto.read)
        lector = ds._LectorJson(texto)
        vistas = []
        lector.esperar("{")
        assert lector.valor() == "facturacion"
        lector.esperar(":")
        vistas = list(lector.elementos())
        assert vistas == fact
