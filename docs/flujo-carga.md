# Flujo de carga de informes

## 0. Archivo único de Villavicencio/EMSA

Si se sube **solo el archivo exógeno** (se detecta por su hoja `Exogena`),
se procesa por la vía EMSA (`core/emsa.py`): se divide en facturación y
recaudo, genera **solo el informe general** de Villavicencio/EMSA (periodo
leído del archivo) y guarda tarifas LCEE si es año nuevo. Todo lo demás
requiere los dos archivos.

## 1. Subida (`POST /cargar`)

Se reciben `facturación.xlsx` y `recaudo.xlsx`, se guardan en
`uploads/originales/` con marca de tiempo y se leen sus encabezados.

## 2. Resolución de columnas

`resolver_columnas()` compara cada dato necesario contra los encabezados:

1. Nombre exacto normalizado (sin tildes/mayúsculas).
2. Alias por defecto (`ALIASES_DEFAULT`) + alias aprendidos en BD.
3. Coincidencia por palabras (tokens).

Faltantes de facturación (`FACT_CLAVES`): ID, factura, impuesto AP,
consumo $, kWh, empresa, nombre, dirección, clase, mercado, estrato,
sector, periodicidad. Faltantes de recaudo (`REC_CLAVES`): ID, valor
recaudado, empresa, mercado, nombre, dirección, clase, sector, estrato.

## 3. Cuestionario emergente (ajax)

Si faltan columnas, `/cargar` responde JSON con una **pregunta por cada
columna necesaria no reconocida**: etiqueta del dato, ejemplo del valor
buscado (`$437.726`) y la lista de columnas del archivo, cada una con
muestra de sus valores. El modal pregunta una por una, con botón
**Atrás** y **Aceptar**; al terminar envía las respuestas a
`/cargar/metadatos/<t>` y el proceso sigue solo al informe.

Sin JavaScript, se usa la página `/cargar/metadatos` (mismo formulario).

## 4. Metadatos

Municipio, comercializadora, año y mes: se detectan del contenido
(municipio, "CELSIA" en nombres, fechas) y **son editables** aunque se
hayan detectado. Si sigue faltando algo, la página lo pide.

## 5. Finalización (`_finalizar_carga`)

1. `build_general` + `build_especiales` (en San Pedro se asegura el año
   de cartera antes).
2. Texto ejecutivo + guardado (`save_report_to_db`: crea o **actualiza**
   el informe del mismo comercializadora+año+mes).
3. Análisis general mensual + acumulación del mes en cartera (San Pedro).
