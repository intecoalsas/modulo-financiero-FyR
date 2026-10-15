# -*- coding: utf-8 -*-
"""Restaura informes.db desde el respaldo más reciente que tenga informes.

Uso (CON LA APP DETENIDA, desde backend/):
    python scripts/restaurar.py        # pregunta confirmación
    python scripts/restaurar.py --si   # sin preguntar
"""
import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEN = os.path.join(BASE, "instance", "informes.db")
RESPALDOS = os.path.join(BASE, "respaldos")


# Cuenta informes de una BD sin tocarla; 0 si no existe o está dañada
def contar_informes(ruta):
    try:
        c = sqlite3.connect(ruta)
        n = c.execute("SELECT count(*) FROM reports").fetchone()[0]
        c.close()
        return n
    except Exception:
        return 0


def main():
    candidatos = [(p, contar_informes(p))
                  for p in glob.glob(os.path.join(RESPALDOS, "informes_*.db"))]
    candidatos = sorted(x for x in candidatos if x[1] > 0)
    if not candidatos:
        print("No hay respaldos con informes en:", RESPALDOS)
        return False
    ultimo, n = candidatos[-1]
    print("Respaldos con informes:", len(candidatos))
    print("Se restaurará el más reciente:", ultimo, f"({n} informes)")
    if "--si" not in sys.argv:
        if input("¿Continuar? (s/N): ").strip().lower() != "s":
            print("Cancelado.")
            return False

    # Si la BD actual tiene datos, se guarda una copia antes de pisarla
    if os.path.isfile(ORIGEN) and contar_informes(ORIGEN) > 0:
        copia = ORIGEN.replace(
            ".db", "_previo_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db")
        shutil.copy2(ORIGEN, copia)
        print("Copia de la BD actual guardada en:", copia)

    shutil.copy2(ultimo, ORIGEN)
    print("Restauración completada. Reinicia la app para verificar.")
    return True


if __name__ == "__main__":
    main()
