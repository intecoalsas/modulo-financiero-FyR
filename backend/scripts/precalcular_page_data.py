# -*- coding: utf-8 -*-
"""Precalcula page_data (versión liviana del informe) para los reportes
que ya existen en la BD.

Se corre UNA vez después de implementar esta optimización (los informes
nuevos ya se precalculan solos al guardarse):

    cd backend
    python scripts/precalcular_page_data.py

page_data es un JSON chico (KPIs + tablas agregadas + fyr precalculado)
que permite renderizar la página al instante sin descargar los 33 MB del
blob general_data.
"""
import gc
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from app import app  # noqa: E402
from models import Report, db  # noqa: E402
from core.fyr import FYR_ORDEN, fyr_agregar  # noqa: E402


def _page_data_de(general_data, municipio, comercializadora):
    if not general_data:
        return None
    pd_copy = dict(general_data)
    pd_copy.pop("facturacion", None)
    pd_copy.pop("recaudo", None)
    for k in ("f", "r"):
        if isinstance(pd_copy.get(k), dict):
            pd_copy[k] = {kk: vv for kk, vv in pd_copy[k].items()
                          if kk != "registros"}
    es_emsa = ((comercializadora or "").strip().lower() == "emsa"
               or (municipio or "").strip().lower() == "villavicencio")
    if es_emsa:
        pd_copy["fyr"] = fyr_agregar(general_data.get("facturacion"),
                                     general_data.get("recaudo"))
        pd_copy["fyr_orden"] = list(FYR_ORDEN)
    return json.dumps(pd_copy, ensure_ascii=False, default=str)


def main():
    with app.app_context():
        ids = [r[0] for r in db.session.query(Report.id).order_by(Report.id).all()]
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
            if getattr(rep, "page_data", None):
                print(f"  {etiqueta}: ya tiene page_data, se omite")
                omitidos += 1
                db.session.expunge(rep)
                continue
            t0 = __import__("time").time()
            try:
                pd = _page_data_de(rep.general_data, rep.municipio_nombre,
                                   rep.comercializadora_nombre)
                rep.page_data = pd
                db.session.commit()
                ok += 1
                print(f"  {etiqueta}: {len(pd)/1024:.1f} KB en "
                      f"{__import__('time').time()-t0:.1f}s")
            except Exception as exc:
                db.session.rollback()
                fallos += 1
                print(f"  {etiqueta}: ERROR {exc}")
            db.session.expunge(rep)
            gc.collect()
        print(f"\nListo: {ok} page_data nuevos, {omitidos} omitidos, {fallos} con error")


if __name__ == "__main__":
    main()
