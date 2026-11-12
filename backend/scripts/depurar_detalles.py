# -*- coding: utf-8 -*-
"""Depura YA el detalle de cuentas de los informes que queden fuera de los
últimos 6 mensuales por comercializadora (CONSERVAR_DETALLES en .env).

El detalle de cuentas son las filas de facturación/recaudo de general_data.
Lo que se conserva siempre: page_data (resumen de la página), especiales_data,
resumen_mes, alertas, análisis ejecutivo y cartera.

Uso (desde backend/ o la raíz, con la misma DATABASE_URL de la app):
    py -3.12 scripts/depurar_detalles.py --dry    # solo informa
    py -3.12 scripts/depurar_detalles.py          # aplica

ADVERTENCIA: la información eliminada no se recupera; antes de aplicar,
descargue el Excel de detalle de cada informe que vaya a depurarse.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "DATABASE_URL" not in os.environ and os.path.isfile(
        os.path.join(os.path.dirname(sys.path[0]), ".env")):
    with open(os.path.join(os.path.dirname(sys.path[0]), ".env"),
              encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, _, valor = linea.partition("=")
                os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))

from app import app  # noqa: E402
from models import db, Comercializadora  # noqa: E402
from core.core import (depurar_detalles_antiguos, _conservar_detalles,  # noqa: E402
                       _report_con_detalle_ids)

if __name__ == "__main__":
    dry = "--dry" in sys.argv
    conservar = _conservar_detalles()
    with app.app_context():
        for com in Comercializadora.query.order_by(Comercializadora.nombre).all():
            ids = _report_con_detalle_ids(com)
            if len(ids) <= conservar:
                print(f"{com.nombre}: {len(ids)} informes con detalle "
                      f"(límite {conservar}) — nada por depurar.")
                continue
            print(f"{com.nombre}: {len(ids)} informes con detalle; se depurarían "
                  f"los ids {ids[conservar:]}.")
            if dry:
                continue
            depurados = depurar_detalles_antiguos(com)
            print(f"  -> depurados {len(depurados)}: {depurados}")
    print("Listo." if not dry else "Modo --dry: no se borró nada.")
