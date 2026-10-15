# -*- coding: utf-8 -*-
"""Procesa el informe exógeno F&R de EMSA (Villavicencio) y guarda el informe
general del mes en la base de datos.

El archivo de EMSA trae en una sola hoja toda la información del impuesto de
alumbrado público por usuario: lo facturado, lo recaudado y la cartera. Desde él
se arman los dos archivos lógicos que entiende el sistema (facturación y recaudo)
y se genera el informe general con build_general().

Uso (desde la carpeta backend/):
    python scripts/cargar_informe_emisa.py <ruta_del_xlsx_emisa> [--mes 6] [--anio 2026]

Ejemplo:
    python scripts/cargar_informe_emisa.py "C:\\Users\\ASUS\\Documents\\ejemploEstrucInfo\\villavicencio\\202606 FyR EMSA (1).xlsx"
"""

import argparse
import os
import sys

import pandas as pd

# Permite importar los módulos del proyecto (app, models, core) desde backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  -> enciende la app y crea la BD
from core.core import (  # noqa: E402
    build_general,
    get_or_create_comerc,
    get_or_create_municipio,
    guardar_tarifas,
    save_report_to_db,
    upsert_analisis_general,
)
from core.emsa import (  # noqa: E402
    MUNICIPIO,
    COMERCIALIZADORA,
    TARIFAS_LCEE_2026,
    leer_exogena_emisa,
)
from core.utils import fmt_currency, json_safe  # noqa: E402


def main():
    # Evita errores de codificación al imprimir acentos en la consola de Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Carga el informe F&R de EMSA (Villavicencio)")
    parser.add_argument("archivo", help="Ruta del Excel exógeno de EMSA (.xlsx)")
    parser.add_argument("--mes", type=int, default=None, help="Mes del informe (por defecto se lee del archivo)")
    parser.add_argument("--anio", type=int, default=None, help="Año del informe (por defecto se lee del archivo)")
    args = parser.parse_args()

    path = args.archivo
    if not os.path.isfile(path):
        print("ERROR: no existe el archivo:", path)
        sys.exit(1)

    print("Leyendo el archivo exógeno de EMSA...")
    fact, rec, periodo_auto = leer_exogena_emisa(path)
    anio = args.anio or (periodo_auto[0] if periodo_auto else None)
    mes = args.mes or (periodo_auto[1] if periodo_auto else None)
    if not anio or not mes:
        print("ERROR: no se pudo determinar el periodo. Use --anio y --mes.")
        sys.exit(1)

    print(f"Filas de facturación: {len(fact):,}  |  Filas de recaudo: {len(rec):,}")
    print(f"Periodo: {mes}/{anio}  |  Municipio: {MUNICIPIO}  |  Comercializadora: {COMERCIALIZADORA}")

    with app.app_context():
        general = build_general(fact, rec, None, None, sin_depurar=True)

        m = get_or_create_municipio(MUNICIPIO)
        c = get_or_create_comerc(m.id, COMERCIALIZADORA)

        report = save_report_to_db(
            MUNICIPIO, COMERCIALIZADORA, anio, mes,
            json_safe(general), None,
            fact_path=os.path.abspath(path), rec_path=os.path.abspath(path),
        )

        upsert_analisis_general(
            c, anio, mes,
            consumo=general["f"]["total_consumo"],
            facturacion=general["f"]["total_imp"],
            recaudo=general["r"]["total_valor"],
        )

        # Las tarifas del Acuerdo 515 solo se guardan la primera vez
        if str(anio) not in (c.tarifas or {}):
            guardar_tarifas(c, anio, TARIFAS_LCEE_2026)

        print("\n--- RESUMEN FINANCIERO (base original -> depurada) ---")
        for concepto, orig, dep, dif in general["resumen_financiero"]:
            print(f"  {concepto}: {orig} -> {dep}  (dif {dif})")

        print("\n--- CONSOLIDADO POR CLASE ---")
        for fila in general["consolidado"]:
            clase, fv, rv, dif, ef = fila
            print(f"  {clase:<12} Fact: {fmt_currency(fv):>16}  Rec: {fmt_currency(rv):>16}  Efic: {ef*100:5.1f}%")

        print("\n--- ESTADÍSTICAS GENERALES ---")
        for k, v in general["estad_general"].items():
            print(f"  {k}: {v}")

        print(f"\nOK: reporte guardado - {MUNICIPIO} / {COMERCIALIZADORA} - "
              f"mes {mes}/{anio} (id {report.id})")


if __name__ == "__main__":
    main()
