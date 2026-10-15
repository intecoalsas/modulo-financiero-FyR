# -*- coding: utf-8 -*-
"""Copia de seguridad local: guarda informes.db con fecha y hora en backend/respaldos/.
Uso (desde backend/): python scripts/respaldo.py
En producción (Postgres/Neon) usar pg_dump programado (ver docs/despliegue.md).
"""
import os
import shutil
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEN = os.path.join(BASE, "instance", "informes.db")
DESTINO_DIR = os.path.join(BASE, "respaldos")


def main():
    if not os.path.isfile(ORIGEN):
        print("No hay base de datos para respaldar:", ORIGEN)
        return False
    os.makedirs(DESTINO_DIR, exist_ok=True)
    nombre = "informes_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db"
    destino = os.path.join(DESTINO_DIR, nombre)
    shutil.copy2(ORIGEN, destino)
    print("Respaldo creado:", destino)
    return True


if __name__ == "__main__":
    main()
