# -*- coding: utf-8 -*-
"""Respaldа el desglose FYR por mes en analisis_general para los
reportes de Villavicencio/EMSA ya guardados en la BD (meses que se
cargaron antes de que el sistema empezara a guardar fyr por mes)."""
import os
import sys

BASE = r"C:\Users\ASUS\Documents\sistemas_informes_FyR\backend"
sys.path.insert(0, BASE)
os.chdir(BASE)

from app import app
from models import db, Report, Comercializadora
from core.fyr import fyr_agregar, fyr_totales
from core.core import upsert_analisis_general

with app.app_context():
    reps = (Report.query
            .join(Comercializadora)
            .filter(Report.anio == 2026)
            .all())
    actualizados = 0
    for r in reps:
        c = r.comercializadora
        if not c:
            continue
        muni = (c.municipio.nombre if c.municipio else "").strip().lower()
        com = (c.nombre or "").strip().lower()
        if muni != "villavicencio" and com != "emsa":
            continue
        gd = r.general_data or {}
        fact = gd.get("facturacion") or []
        rec = gd.get("recaudo") or []
        if not fact:
            print(f"reporte {r.id} ({r.mes}/{r.anio}): sin registros de facturación, se omite")
            continue
        tot = fyr_totales(fyr_agregar(fact, rec))
        consumo = (gd.get("f") or {}).get("total_consumo")
        facturacion = (gd.get("f") or {}).get("total_imp")
        recaudo = (gd.get("r") or {}).get("total_valor")
        upsert_analisis_general(c, r.anio, r.mes,
                                consumo=consumo, facturacion=facturacion,
                                recaudo=recaudo, fyr_data=tot, commit=False)
        e1 = tot.get("Residencial – Estrato 1", {})
        print(f"reporte {r.id} ({r.mes}/{r.anio}): fyr guardado "
              f"E1 fact={e1.get('fact'):.0f} rec={e1.get('rec'):.0f} "
              f"(total claves: {len(tot)})")
        actualizados += 1
    db.session.commit()
    print(f"Listo: {actualizados} meses respaldados en analisis_general")
