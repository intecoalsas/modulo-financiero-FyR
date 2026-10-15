# -*- coding: utf-8 -*-
"""Comprime en el lugar los general_data ya guardados en la BD (una sola vez).

Los JSON de texto plano pasan a gzip+base64 (10-20x más pequeños). El modelo
JsonComprimido los descomprime solo al leer, así que la app no cambia.

Uso (desde backend/, con la app detenida):
    python scripts/comprimir_informes.py
"""
import base64
import gzip
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BD = os.path.join(BASE, "instance", "informes.db")


def main():
    if not os.path.isfile(BD):
        print("No existe la BD:", BD)
        return False
    con = sqlite3.connect(BD)
    filas = con.execute(
        "SELECT id, anio, mes, length(general_data) FROM reports "
        "WHERE general_data IS NOT NULL ORDER BY id").fetchall()
    total_antes = total_despues = 0
    for rid, anio, mes, largo in filas:
        (texto,) = con.execute(
            "SELECT general_data FROM reports WHERE id=?", (rid,)).fetchone()
        if texto is None:
            continue
        try:
            gzip.decompress(base64.b64decode(texto))
            print(f"  report {rid} ({anio}-{mes}): ya estaba comprimido")
            total_antes += len(texto)
            total_despues += len(texto)
            continue
        except Exception:
            pass
        comprimido = base64.b64encode(
            gzip.compress(texto.encode("utf-8"), 6)).decode("ascii")
        con.execute("UPDATE reports SET general_data=? WHERE id=?",
                    (comprimido, rid))
        total_antes += len(texto)
        total_despues += len(comprimido)
        print(f"  report {rid} ({anio}-{mes}): "
              f"{len(texto)/1e6:.1f} MB -> {len(comprimido)/1e6:.1f} MB")
    con.commit()
    con.close()
    print(f"Total: {total_antes/1e6:.1f} MB -> {total_despues/1e6:.1f} MB")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
