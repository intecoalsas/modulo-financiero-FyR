# -*- coding: utf-8 -*-
"""Precalcula las alertas de los informes que ya existen en la BD.

Se corre UNA vez después de implementar la idea #2 (los informes nuevos ya
se precalcular solos al guardarse):

    cd backend
    python scripts/precalcular_alertas.py

Las alertas viven en la tabla `alertas_reporte` (JSON chico), así que la
página las muestra al instante en vez de recorrer 235 mil filas cada vez.

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
from models import AlertaReporte, Report, db  # noqa: E402
from core.alertas import guardar_alertas  # noqa: E402


def main():
    with app.app_context():
        # Solo los IDs: cargar todos los reportes a la vez explotaría la RAM
        ids = [r[0] for r in db.session.query(Report.id)
               .order_by(Report.id).all()]
        print(f"Reportes en la BD: {len(ids)}")
        ok = fallos = omitidos = 0
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
            if AlertaReporte.query.get(rid) is not None:
                print(f"  {etiqueta}: ya tiene alertas precalculadas")
                omitidos += 1
                db.session.expunge(rep)
                continue
            t0 = time.time()
            salida = guardar_alertas(rep)
            if salida is None:
                print(f"  {etiqueta}: ERROR al calcular")
                fallos += 1
            else:
                print(f"  {etiqueta}: {salida['total']} alertas "
                      f"(alta={salida['alta']}) en {time.time()-t0:.1f}s")
                ok += 1
            # Libera los ~850 MB del informe antes de cargar el siguiente
            db.session.expunge(rep)
            gc.collect()
        print(f"\nListo: {ok} precalculadas, {omitidos} omitidas, "
              f"{fallos} con error")


if __name__ == "__main__":
    main()
