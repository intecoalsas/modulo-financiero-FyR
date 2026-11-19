# -*- coding: utf-8 -*-
"""Trocea a mano el detalle de cuentas (tabla detalle_bloques) de informes
ya guardados.

NO hace falta en el uso normal: el servidor desplegado (Render) trocea solo,
en segundo plano, los informes viejos que no tienen bloques (ver
core/detalle_store.iniciar_migracion), y los informes nuevos se trocean al
guardarse. Este script queda como herramienta de mantenimiento, por ejemplo
para rehacer un informe concreto con --forzar.

    cd backend
    py -3.12 scripts/precalcular_detalle.py --local    # solo la SQLite local
    py -3.12 scripts/precalcular_detalle.py --ids 18 --forzar
"""
import argparse
import gc
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--local", action="store_true",
                    help="usar backend/instance/informes.db (ignora Turso)")
    ap.add_argument("--ids", type=int, nargs="*", help="solo estos informes")
    ap.add_argument("--forzar", action="store_true",
                    help="rehacer aunque ya tenga bloques")
    args = ap.parse_args()

    os.environ["DETALLE_MIGRAR_AUTO"] = "0"  # sin el hilo automático aquí
    if args.local:
        ruta = os.path.join(BASE, "instance", "informes.db")
        os.environ["DATABASE_URL"] = "sqlite:///" + os.path.abspath(ruta)
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_AUTH_TOKEN", None)

    from app import app  # noqa: E402
    from models import Report, db
    from core import detalle_store

    with app.app_context():
        print("BD:", db.engine.url)
        q = db.session.query(Report.id).filter(Report.general_data.isnot(None))
        if args.ids:
            q = q.filter(Report.id.in_(args.ids))
        ids = [r[0] for r in q.order_by(Report.updated_at.desc()).all()]
        print(f"Informes con detalle: {len(ids)}")
        ok = omitidos = fallos = 0
        for i, rid in enumerate(ids, 1):
            etiqueta = f"[{i}/{len(ids)}] informe {rid}"
            if not args.forzar and detalle_store.meta(rid):
                print(f"  {etiqueta}: ya tiene bloques, se omite")
                omitidos += 1
                continue
            t0 = time.time()
            try:
                total = detalle_store.trocear_desde_bd(rid)
                ok += 1
                print(f"  {etiqueta}: {total} cuentas en {time.time() - t0:.1f}s")
            except Exception as exc:
                db.session.rollback()
                fallos += 1
                print(f"  {etiqueta}: ERROR {exc}")
            gc.collect()
        print(f"\nListo: {ok} troceados, {omitidos} omitidos, {fallos} con error")


if __name__ == "__main__":
    main()
