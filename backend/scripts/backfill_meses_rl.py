# -*- coding: utf-8 -*-
"""Backfill: los meses 6,7,8 de 2026 de San Pedro/Celsia quedaron guardados
como F-L; el Excel manda R-L (val_rec del informe mensual ya hecho).
- Junio (rep 2, archivos originales perdidos): usa las filas guardadas,
  parchando el nombre desde general_data (facturación del mes).
- Julio (rep 1) y agosto (rep 5): usan sus filas ya reconstruidas.
Uso (desde backend/): python scripts/backfill_meses_rl.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from models import db, Report, Comercializadora  # noqa: E402
from core.core import actualizar_cartera_mes, get_cartera  # noqa: E402

COM_ID = 2
ANIO = 2026


def _nombres_archivo(facturacion):
    mapa = {}
    for r in facturacion or []:
        clave = str(r.get("Id_cliente") or "").strip()
        nom = str(r.get("Nombre") or "").strip()
        if clave and nom:
            mapa.setdefault(clave, []).append(nom)
    from collections import Counter
    return {k: Counter(v).most_common(1)[0][0] for k, v in mapa.items()}


def main():
    with app.app_context():
        com = Comercializadora.query.get(COM_ID)
        for rid, mes in ((2, 6), (1, 7), (5, 8)):
            rep = Report.query.get(rid)
            filas = list((rep.especiales_data or {}).get("filas") or [])
            print(f"--- rep {rid} mes {mes}: {len(filas)} filas")
            if rid == 2:
                # Parche junio: nombre del archivo (general_data) para el caso bandera
                noms = _nombres_archivo((rep.general_data or {}).get("facturacion"))
                print("    nombre archivo 5298140000:", noms.get("5298140000"))
                difs = 0
                for f in filas:
                    cid = str(f.get("id"))
                    if cid == "5298140000" and noms.get(cid):
                        print(f"    parche nombre: {f['nombre']} -> {noms[cid]}")
                        f["nombre"] = noms[cid]
                    if noms.get(cid) and noms[cid] != f.get("nombre"):
                        difs += 1
                print(f"    otras diferencias nombre cartera/archivo en junio: {difs}")
                rep.especiales_data["filas"] = filas
                db.session.commit()
            antes = {k: v for k, v in
                     next(c for c in get_cartera(com, ANIO)["clientes"]
                          if str(c["id"]).strip() == "5298140000")["meses"].items()}
            ok = actualizar_cartera_mes(com, ANIO, mes, especiales_filas=filas)
            com = Comercializadora.query.get(COM_ID)
            cli = next(c for c in get_cartera(com, ANIO)["clientes"]
                       if str(c["id"]).strip() == "5298140000")
            print(f"    acumulado: {ok} | meses 6,7,8: "
                  f"{cli['meses'].get('6')}, {cli['meses'].get('7')}, {cli['meses'].get('8')} "
                  f"| saldos2026: {cli['saldos'].get('2026')} | total: {cli.get('total_cartera')}")
        cart = get_cartera(com, ANIO)
        print("total_favor 2026:", cart["total_favor"].get("2026"),
              "| total:", cart["total_favor"].get("total"))
        print("total_pagar 2026:", cart["total_pagar"].get("2026"),
              "| total:", cart["total_pagar"].get("total"))
        print("OK")


if __name__ == "__main__":
    main()
