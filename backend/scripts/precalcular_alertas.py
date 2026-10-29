# -*- coding: utf-8 -*-
"""Precalcula alertas (idea #2) y resúmenes mensuales (ideas #3, #6, #9)
de los informes que ya existen en la BD.

Se corre UNA vez después de implementar estas ideas (los informes nuevos ya
se precalcular solos al guardarse):

    cd backend
    python scripts/precalcular_alertas.py

Las alertas viven en `alertas_reporte` y los totales en `resumen_mes`
(JSON/tabla chicos), así que la página y el chat responden al instante en
vez de descomprimir 33 MB (≈10 s y ~850 MB de RAM) por consulta.

OJO: un general_data parseado ocupa ~850 MB de RAM, así que los informes
se procesan DE UNO EN UNO y se libera la memoria antes de pasar al siguiete.
"""
import gc
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from app import app  # noqa: E402
from models import AlertaReporte, Report, ResumenMes, db  # noqa: E402
from core.alertas import guardar_alertas  # noqa: E402
from core.ia_chat import guardar_resumen  # noqa: E402
from core.fyr import FYR_ORDEN, fyr_agregar  # noqa: E402


def main():
    with app.app_context():
        # Solo los IDs: cargar todos los reportes a la vez explotaría la RAM
        ids = [r[0] for r in db.session.query(Report.id)
               .order_by(Report.id).all()]
        print(f"Reportes en la BD: {len(ids)}")
        ok_a = ok_r = fallos = omitidos = 0
        for i, rid in enumerate(ids, 1):
            rep = Report.query.get(rid)
            etiqueta = (f"[{i}/{len(ids)}] id={rid} "
                        f"{rep.municipio_nombre}/{rep.comercializadora_nombre} "
                        f"{rep.mes_nombre} {rep.anio}")
            if rep.general_data is None:
                print(f"  {etiqueta}: sin datos, se omite")
                omitidos += 1
                db.session.expunge(rep)
                continue

            # Se calcula la tabla por estrato UNA vez si es EMSA y hace falta
            fyr = orden = None
            es_fyr = ((rep.comercializadora_nombre or "").strip().lower()
                      == "emsa"
                      or (rep.municipio_nombre or "").strip().lower()
                      == "villavicencio")
            if es_fyr:
                fyr = fyr_agregar((rep.general_data or {}).get("facturacion"),
                                  (rep.general_data or {}).get("recaudo"))
                orden = list(FYR_ORDEN)

            t0 = time.time()
            hay_alertas = AlertaReporte.query.get(rid) is not None
            hay_resumen = ResumenMes.query.get(rid) is not None

            if not hay_alertas:
                salida = guardar_alertas(rep)
                if salida is None:
                    print(f"  {etiqueta}: ERROR en alertas")
                    fallos += 1
                else:
                    ok_a += 1
                    etiqueta += (f" | alertas: {salida['total']} "
                                 f"(alta={salida['alta']})")
            if not hay_resumen:
                if guardar_resumen(rep, fyr=fyr, fyr_orden=orden) is None:
                    print(f"  {etiqueta}: ERROR en resumen")
                    fallos += 1
                else:
                    ok_r += 1
            print(f"  {etiqueta} en {time.time()-t0:.1f}s")

            # Libera los ~850 MB del informe antes de cargar el siguiente
            db.session.expunge(rep)
            gc.collect()
        print(f"\nListo: {ok_a} alertas nuevas, {ok_r} resúmenes nuevos, "
              f"{omitidos} ya listos/sin datos, {fallos} con error")


if __name__ == "__main__":
    main()
