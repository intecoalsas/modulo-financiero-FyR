# -*- coding: utf-8 -*-
"""Corrige el caso 5298140000 (AGROINVERSIONES, antes INCOLTRIPLEX) en San Pedro:
1. Actualiza identidad en cartera 2026 (nombre del archivo, GRUPO 2, tarifa 437726).
2. Reconstruye especiales de julio (rep 1) y agosto (rep 5) con archivos originales.
3. Acumula meses 7 y 8 en cartera desde los informes rehechos (VLOOKUP).
4. Ajusta total_cartera del cliente por el delta.

Uso (desde backend/): python scripts/corregir_incol_agro.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from models import db, Report  # noqa: E402
from core.core import (  # noqa: E402
    actualizar_cartera_mes,
    build_especiales_desde_archivos,
    get_cartera,
    save_cartera,
)
from core.utils import json_safe  # noqa: E402

COM_ID = 2
ANIO = 2026
CID = "5298140000"


def main():
    with app.app_context():
        from models import Comercializadora
        com = Comercializadora.query.get(COM_ID)

        # --- 1. Identidad en cartera (los archivos mandan en el nombre;
        # GRUPO 2 / tarifa 437726 según hoja JULIO-AGOSTO del Excel manual)
        cartera = get_cartera(com, ANIO)
        cli = next(c for c in cartera["clientes"] if str(c["id"]).strip() == CID)
        print("ANTES identidad:", cli["nombre"], "|", cli["grupo"], "|", cli["tarifa_min"])
        print("ANTES meses:", cli["meses"], "| saldos2026:", cli["saldos"].get("2026"),
              "| total_cartera:", cli.get("total_cartera"))
        old_2026 = float(cli["saldos"].get("2026") or 0)
        cli["nombre"] = "AGROINVERSIONES CARNEL SAS"
        cli["grupo"] = "GRUPO 2"
        cli["tarifa_min"] = 437726.0
        save_cartera(com, ANIO, cartera)
        # recargar objeto fresco para rebuild
        com = Comercializadora.query.get(COM_ID)

        # --- 2 y 3. Reproceso julio y agosto + acumulación VLOOKUP
        for rid, mes in ((1, 7), (5, 8)):
            rep = Report.query.get(rid)
            assert rep and rep.anio == ANIO and rep.mes == mes, rid
            print(f"--- reprocesando rep {rid} ({ANIO}-{mes})")
            print("    archivos:", os.path.exists(rep.archivo_fact_path or ""),
                  os.path.exists(rep.archivo_rec_path or ""))
            result = build_especiales_desde_archivos(
                mes, ANIO, com, rep.archivo_fact_path, rep.archivo_rec_path)
            assert result is not None
            fila = next(f for f in result["filas"] if str(f["id"]) == CID)
            print("    fila 5298140000:", fila["nombre"], fila["clase"],
                  fila["tarifa_minima"], "fact:", fila["facturacion"],
                  "calc:", fila["calc_iap"], "saldo_fl:", fila["saldo_fl"])
            print("    totales nuevos: saldo_neg:",
                  result["totales"]["saldo_neg"], "| total_saldo_fl:",
                  result["totales"]["total_saldo_fl"])
            rep.especiales_data = json_safe(result)
            db.session.commit()
            ok = actualizar_cartera_mes(com, ANIO, mes,
                                        especiales_filas=result["filas"])
            print("    cartera acumulada:", ok)
            com = Comercializadora.query.get(COM_ID)

        # --- 4. Ajuste total_cartera por el delta del 2026
        cartera = get_cartera(com, ANIO)
        cli = next(c for c in cartera["clientes"] if str(c["id"]).strip() == CID)
        new_2026 = float(cli["saldos"].get("2026") or 0)
        delta = new_2026 - old_2026
        print("DESPUES meses:", cli["meses"], "| saldos2026:", new_2026,
              "| delta:", delta)
        cli["total_cartera"] = float(cli.get("total_cartera") or 0) + delta
        print("DESPUES total_cartera:", cli["total_cartera"])
        print("DESPUES identidad:", cli["nombre"], "|", cli["grupo"], "|", cli["tarifa_min"])
        print("total_pagar 2026:", cartera["total_pagar"].get("2026"),
              "| total:", cartera["total_pagar"].get("total"))
        save_cartera(com, ANIO, cartera)
        print("OK")


if __name__ == "__main__":
    main()
