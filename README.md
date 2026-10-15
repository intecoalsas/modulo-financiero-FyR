# Sistema de Informes F&R

Aplicación web para la interventoría del impuesto de alumbrado público.
Procesa archivos de facturación y recaudo de las comercializadoras y genera
informes generales, de clientes especiales y cartera acumulada, con descarga
en Excel y Word.

## Municipios y comercializadoras

| Municipio | Comercializadora | Informes |
|---|---|---|
| San Pedro | Celsia | General + Especiales + Cartera acumulada |
| Calima El Darién | Celsia | General + Especiales |
| Andalucía | Celsia | General + Especiales |
| Villavicencio | EMSA | Solo General (tarifas % sobre LCEE, Acuerdo 515) |

## Requisitos

- Python 3.10+ (probado en 3.14)
- pip

## Instalación y ejecución local

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Abrir en el navegador: `http://127.0.0.1:5000`

La base de datos SQLite se crea sola en `backend/instance/informes.db`
al primer arranque (no se sube a git, ver `.gitignore`).

## Uso básico

1. **Cargar Archivos**: subir `facturación.xlsx` y `recaudo.xlsx`.
   Para **Villavicencio (EMSA)** basta el archivo exógeno (se detecta
   solo por su hoja `Exogena` y genera únicamente el informe general).
   Si alguna columna no coincide con los nombres conocidos, aparece un
   cuestionario emergente para indicar cómo se llama en el archivo
   (la respuesta se aprende para futuras cargas).
2. **Historial**: ver, filtrar, descargar o eliminar informes guardados.
   Un informe por comercializadora + año + mes: re-subir actualiza.
3. **Informe General / Especiales**: dashboards con KPIs, tablas y gráficas.
4. **Cartera Acumulada SP** (solo San Pedro): saldos por cuenta 2019 en
   adelante; el año en curso se llena mes a mes con los archivos subidos.
5. **Información de Referencia**: tarifas, análisis general y grupos por
   comercializadora.

## Estructura

```
sistemas_informes_FyR/
├── backend/
│   ├── app.py              # App Flask, BD, seed de municipios
│   ├── models.py           # Modelos SQLAlchemy (fechas en hora Colombia)
│   ├── blueprints/routes.py# Todas las páginas y APIs
│   ├── core/               # Lógica: depuración, informes, cartera, columnas
│   ├── reports/            # Generadores Excel/Word + lector de referencia
│   ├── services/           # Consultas de reportes, cargas pendientes
│   ├── scripts/            # Scripts de carga/corrección (EMSA, backfills)
│   ├── instance/           # BD local (NO va a git)
│   ├── uploads/            # Excel subidos (NO van a git)
│   └── exports/            # Archivos generados (NO van a git)
├── frontend/
│   ├── templates/          # Páginas Jinja2
│   └── static/             # CSS, JS (filtros de tabla)
└── docs/                   # Documentación detallada
```

## Documentación

- `docs/arquitectura.md` — componentes y base de datos
- `docs/flujo-carga.md` — carga, cuestionario de columnas y metadatos
- `docs/informes.md` — general, especiales y variación del saldo negativo
- `docs/cartera-acumulada.md` — reglas de la cartera SP (meses R-L, totales, años)
- `docs/columnas-mapeo.md` — resolución de columnas y alias aprendidos
- `docs/despliegue.md` — GitHub y hosting con base de datos gratis en la nube

## Notas importantes

- Las fechas se guardan en **UTC** y se muestran en hora de Colombia
  (UTC-5) en formato 12h AM/PM.
- Configuración por variables de entorno (ver `.env.example`):
  `SECRET_KEY`, `DATABASE_URL`, `FLASK_ENV`, `MAX_UPLOAD_MB`,
  `CONSERVAR_ORIGINALES`.
- Los hostings gratuitos borran el SQLite al reiniciar: para producción
  usar Postgres gratis (Neon/Supabase). Ver `docs/despliegue.md`.
- Respaldo local: `python backend/scripts/respaldo.py`.
