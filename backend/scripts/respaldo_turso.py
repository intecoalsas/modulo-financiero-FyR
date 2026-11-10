# -*- coding: utf-8 -*-
"""Respaldo de Turso: descarga un dump SQL completo a backend/respaldos/.

Se puede correr a mano o programarlo en el Programador de tareas de Windows
para que corra cada noche, igual que scripts/auto_commit.ps1:

    cd backend
    python scripts/respaldo_turso.py

Conserva los últimos 15 respaldos. El dump es SQL estándar, restaurable en
SQLite local o en cualquier otra base compatible.
"""
import os
import sys
import glob
import gzip
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from dotenv import *  # noqa: F401,F403  (no-op si no está instalado)

url = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
token = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()
if not url or not token:
    # Intentar leer del .env
    env_path = os.path.join(BASE, ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                k, v = linea.split("=", 1)
                if k.strip() == "TURSO_DATABASE_URL":
                    url = v.strip()
                elif k.strip() == "TURSO_AUTH_TOKEN":
                    token = v.strip()
if not url or not token:
    print("Faltan TURSO_DATABASE_URL y TURSO_AUTH_TOKEN.")
    sys.exit(1)

http_url = url.replace("libsql://", "https://").rstrip("/")
import urllib.request
req = urllib.request.Request(http_url + "/dump", headers={"Authorization": "Bearer " + token})
print("Descargando dump de Turso...")
with urllib.request.urlopen(req, timeout=600) as resp:
    data = resp.read()
print(f"Descargado: {len(data)/1024/1024:.1f} MB")

resp_dir = os.path.join(BASE, "respaldos")
os.makedirs(resp_dir, exist_ok=True)
hoy = datetime.now().strftime("%Y%m%d_%H%M%S")
destino = os.path.join(resp_dir, f"turso_{hoy}.sql.gz")
with gzip.open(destino, "wb") as fh:
    fh.write(data)
print("Guardado:", destino)

# Conservar los últimos 15
existentes = sorted(glob.glob(os.path.join(resp_dir, "turso_*.sql.gz")))
for viejo in existentes[:-15]:
    os.remove(viejo)
    print("Eliminado respaldo antiguo:", os.path.basename(viejo))
print("Listo.")
