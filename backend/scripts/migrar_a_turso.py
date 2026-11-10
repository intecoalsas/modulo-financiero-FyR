# -*- coding: utf-8 -*-
"""Migra la base SQLite local a Turso (libSQL) por HTTP.

Uso:
    cd backend
    set TURSO_DATABASE_URL=https://mi-db-miorg.turso.io
    set TURSO_AUTH_TOKEN=eyJ...
    python scripts/migrar_a_turso.py

Copia todas las tablas en orden de dependencias. Los blobs grandes
(general_data de Villavicencio, ~33 MB) se envían en una sola petición
por informe; si Turso rechaza el tamaño, el script se detiene y hay que
trocearlos (avise).
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.chdir(BASE)

from sqlalchemy import create_engine, text, inspect as sa_inspect

from core.turso_dialect import register as _reg_turso
_reg_turso()

from core.turso_dbapi import configure as _cfg_turso

TURSO_URL = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
TURSO_TOKEN = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()
if not TURSO_URL or not TURSO_TOKEN:
    print("Faltan TURSO_DATABASE_URL y/o TURSO_AUTH_TOKEN en el entorno.")
    sys.exit(1)

_cfg_turso(TURSO_URL, TURSO_TOKEN)

SQLITE_URL = "sqlite:///" + os.path.join(BASE, "instance", "informes.db")
src = create_engine(SQLITE_URL)
dst = create_engine("turso:///")

# Orden de dependencias
TABLAS = ["municipios", "comercializadoras", "mapeo_columnas",
          "cargas_pendientes", "auditoria", "clientes_especiales", "reports",
          "alertas_reporte", "resumen_mes"]

# Crea el esquema en Turso si no existe
from models import db as _db
from flask import Flask as _Flask
_app = _Flask(__name__)
_app.config["SQLALCHEMY_DATABASE_URI"] = "turso:///"
_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
from sqlalchemy.pool import NullPool
_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"poolclass": NullPool}
_db.init_app(_app)
with _app.app_context():
    _db.create_all()
print("Esquema creado en Turso.")

src_conn = src.connect()
dst_conn = dst.connect()
src_ins = sa_inspect(src)
for tabla in TABLAS:
    if tabla not in src_ins.get_table_names():
        print(f"  {tabla}: no existe en origen, se omite")
        continue
    cols = [c["name"] for c in src_ins.get_columns(tabla)]
    col_sql = ", ".join('"' + c + '"' for c in cols)
    placeholders = ", ".join(":" + c for c in cols)
    filas = src_conn.execute(text(f"SELECT {col_sql} FROM {tabla}")).fetchall()
    if not filas:
        print(f"  {tabla}: 0 filas")
        continue
    try:
        dst_conn.execute(text(f"DELETE FROM {tabla}"))
        dst_conn.commit()
    except Exception:
        dst_conn.rollback()
    n = 0
    for row in filas:
        params = {c: row[i] for i, c in enumerate(cols)}
        dst_conn.execute(text(f"INSERT INTO {tabla} ({col_sql}) VALUES ({placeholders})"), params)
        n += 1
        if tabla == "reports":
            print(f"    reports: {n}/{len(filas)} migrado", end="\r")
    dst_conn.commit()
    print(f"  {tabla}: {n} filas migradas")

print("Migración terminada.")
src_conn.close()
dst_conn.close()
src.dispose()
dst.dispose()
