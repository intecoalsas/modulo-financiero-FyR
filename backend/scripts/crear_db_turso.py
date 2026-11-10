# -*- coding: utf-8 -*-
"""Crea la base de datos en Turso y genera un token usando la Platform API.

Uso:
    set TURSO_API_TOKEN=eyJ...   (token de la cuenta, de turso.tech/app -> Settings -> API tokens)
    python scripts/crear_db_turso.py [nombre_bd]

Imprime TURSO_DATABASE_URL y TURSO_AUTH_TOKEN listos para el .env.
"""
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = (os.environ.get("TURSO_API_TOKEN") or "").strip()
if not TOKEN:
    print("Falta TURSO_API_TOKEN en el entorno.")
    sys.exit(1)

NOMBRE = sys.argv[1] if len(sys.argv) > 1 else "informes-fyr"
BASE = "https://api.turso.tech/v1"


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} en {method} {path}: {msg}")


# 1. Organizaciones del usuario
orgs = api("GET", "/organizations")
if not orgs.get("organizations"):
    raise SystemExit("No se encontraron organizaciones en la cuenta.")
org = orgs["organizations"][0]["name"] if isinstance(orgs["organizations"][0], dict) else orgs["organizations"][0]
print(f"Organización: {org}")

# 2. Crear la base (si ya existe, se ignora el error)
try:
    api("POST", f"/organizations/{org}/databases", {"name": NOMBRE, "group": "default"})
    print(f"Base '{NOMBRE}' creada.")
except SystemExit as e:
    if "already exists" in str(e).lower() or "conflict" in str(e).lower():
        print(f"La base '{NOMBRE}' ya existía, se reutiliza.")
    else:
        raise

# 3. Obtener el hostname
info = api("GET", f"/organizations/{org}/databases/{NOMBRE}")
db = info.get("database", info)
hostname = db.get("hostname") or db.get("Hostname")
print(f"Hostname: {hostname}")

# 4. Crear un token de acceso a la base
tok_resp = api("POST", f"/organizations/{org}/databases/{NOMBRE}/auth/tokens", {})
token = (tok_resp.get("jwt") or tok_resp.get("token")
         or tok_resp.get("Jwt") or tok_resp.get("Token"))
if not token:
    # Algunas versiones devuelven el token en otra clave
    print("Respuesta del token:", json.dumps(tok_resp, indent=2))
    raise SystemExit("No se pudo extraer el token de la respuesta.")

print()
print("Agregue estas líneas a backend/.env:")
print(f"TURSO_DATABASE_URL=libsql://{hostname}")
print(f"TURSO_AUTH_TOKEN={token}")
