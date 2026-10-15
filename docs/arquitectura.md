# Arquitectura

## Componentes

- **Flask** (`backend/app.py`): crea la app, configura SQLite en
  `backend/instance/informes.db`, registra el blueprint y siembra los
  4 municipios con sus comercializadoras al arrancar.
- **Modelos** (`backend/models.py`): SQLAlchemy.
  - `Municipio` → `Comercializadora` → `Report`
  - `Report`: un informe por (`comercializadora_id`, `anio`, `mes`).
    Guarda `general_data` y `especiales_data` (JSON), rutas de archivos,
    análisis ejecutivo y novedades.
  - `Comercializadora`: guarda `cartera_acumulada`, `tarifas`,
    `analisis_general` y `descripcion` (JSON por año).
  - `MapeoColumna`: alias de columnas aprendidos de los archivos.
  - `CargaPendiente`: cargas a medio hacer (cuestionario/metadatos).
  - `Auditoria`: acción, detalle, IP y fecha (sin usuario: no hay login).
  - Fechas en **UTC** (`ahora_utc()`); solo al mostrar se convierten a
    America/Bogota con el filtro `hora_col` (UTC-5 fijo, formato 12h).
- **Rutas** (`backend/blueprints/routes.py`): páginas, APIs de combos,
  carga, descargas Excel/Word, cartera y referencia.
- **Núcleo** (`backend/core/`):
  - `depuracion.py`: limpieza de facturación y recaudo.
  - `core.py`: `build_general`, `build_especiales`,
    `build_especiales_desde_archivos`, cartera (`ensure_cartera_anio`,
    `actualizar_cartera_mes`), guardado y texto ejecutivo.
  - `columnas.py`: alias, etiquetas, ejemplos y resolución de columnas.
- **Reportes** (`backend/reports/`): `excel_engine.py`, `word_engine.py`,
  `info_especiales_reader.py` (lee el libro de referencia con cartera,
  tarifas y descripción).
- **Frontend** (`frontend/`): plantillas Jinja2 + `style.css` (tema claro
  oliva) + `filter_widget.js` (filtros tipo Excel en las tablas).

## Seguridad y configuración

- `SECRET_KEY`, `DATABASE_URL`, `MAX_UPLOAD_MB` (60), `FLASK_ENV` y
  `CONSERVAR_ORIGINALES` por variables de entorno (ver `.env.example`).
- Validación de cargas: solo `.xlsx`/`.xls`, tope de tamaño (error 413
  amable), nombres saneados con `secure_filename`.
- Rate limit en `/cargar` (Flask-Limiter, memoria local).
- Talisman (HTTPS + cabeceras) solo con `FLASK_ENV=production`.
- Lectura de Excel con motor calamine y respaldo a openpyxl
  (`core/utils.py::leer_excel`).

## Base de datos

SQLite de un solo archivo. Tablas: `municipios`, `comercializadoras`,
`reports`, `mapeo_columnas`, `cargas_pendientes`. Al arrancar, la app crea
tablas y columnas faltantes sola (migración ligera en `app.py`).

> La BD contiene datos sensibles y **no va a git** (ver `.gitignore`).
