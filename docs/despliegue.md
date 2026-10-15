# Despliegue: GitHub y hosting

## GitHub (solo código, sin datos)

El `.gitignore` ya excluye lo sensible:

- `backend/instance/` (la BD con usuarios), `backend/respaldos/`
- `backend/uploads/` (Excel originales), `backend/exports/`
- `.env`, `__pycache__/`, `.venv/`

```bash
git init
git add .
git status      # verificar que NO aparezcan instance/, uploads/ ni respaldos/
git commit -m "Sistema de informes F&R"
git branch -M main
git remote add origin <URL-del-repo-privado>
git push -u origin main
```

Usar **repositorio privado**. Subir no borra nada local. Respalda
`informes.db` y `uploads/` aparte (ver `scripts/respaldo.py`).

## Dónde alojar (todo gratuito)

| Opción | Ventajas | Límites |
|---|---|---|
| **Render** (recomendado para empezar) | Despliegue desde Git, HTTPS, variables | ~512 MB RAM: el XLSX de 50 MB se procesa con calamine pero **probar antes**; se duerme sin uso; disco efímero |
| **Hugging Face Spaces** (Docker, privado) | ~16 GB RAM: ideal para archivos grandes | Se duerme tras días sin uso; disco efímero; no pensado para producción crítica |
| Oracle Cloud Always Free (respaldo) | RAM y disco persistente | Exige tarjeta, hay que administrar el servidor |
| PythonAnywhere | Fácil para Flask, disco persistente | CPU limitada, un solo sitio |

El frontend (Jinja) y el backend van juntos en un solo servicio: sin CORS,
más simple y más barato. Arranque: `gunicorn app:app --workers 1
--timeout 120 --chdir backend` (ver `render.yaml`).

## Base de datos en la nube (Neon, gratis)

Render y similares **borran el SQLite al reiniciar**: la BD va en
Postgres (**Neon**, plan gratuito con copias de punto anterior). No usar
el Postgres gratuito de Render para producción (temporal y expira).
Alternativa: Supabase (solo como Postgres).

La app ya acepta `DATABASE_URL` (normaliza `postgres://`) con respaldo a
SQLite local; las columnas JSON funcionan en ambos; la restricción
`UNIQUE(comercializadora, año, mes)` ya existe en el modelo.

Pasos:

1. Crear proyecto en Neon y copiar la cadena (`?sslmode=require`).
2. `pip install -r backend/requirements.txt` (incluye `psycopg[binary]`).
3. Poner `DATABASE_URL` en el hosting. Las tablas se crean solas.
4. Migrar datos una vez (exportar SQLite → importar a Postgres, validar
   conteos) y **conservar el .db original fuera del repo**.
5. Probar: subir un mes real, verificar informes y cartera; reiniciar el
   servicio y confirmar que los datos persisten.

## Variables de entorno

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave larga aleatoria (obligatoria en producción) |
| `DATABASE_URL` | Postgres (Neon) con `sslmode=require`; vacía = SQLite local |
| `FLASK_ENV` | `production` activa HTTPS y cabeceras de seguridad |
| `MAX_UPLOAD_MB` | Tope de subida, 60 por Villavicencio/EMSA |
| `CONSERVAR_ORIGINALES` | `0` borra los Excel subidos al procesar (ya están en otro lado); `1` los conserva |
| `TZ_DISPLAY` | `America/Bogota` (las fechas se guardan UTC y se muestran −5) |

Ver `.env.example`. (`ADMIN_EMAIL` del spec no aplica: sin login/usuarios.)

## Copias de seguridad

- Local: `python backend/scripts/respaldo.py` (copia fechada en
  `backend/respaldos/`, excluido de git).
- Neon: restauración a punto anterior (ventana corta en plan gratis).
- Adicional: GitHub Action semanal con `pg_dump` cifrado como artefacto
  privado. **Probar la restauración al menos una vez.**

## Datos personales (Ley 1581 de 2012)

Los archivos traen nombre, documento y dirección. Medidas tomadas:
extensiones y tamaño validados, nombres saneados, originales conservados
solo localmente (en producción pueden borrarse con
`CONSERVAR_ORIGINALES=0`), auditoría sin datos personales, y repositorio
privado. Falta: aviso de privacidad y definir responsable/encargado del
tratamiento con INTECOAL.

## Dominio

Suficiente el subdominio gratis (`nombre.onrender.com`) enlazado desde el
portal; dominio propio opcional.
