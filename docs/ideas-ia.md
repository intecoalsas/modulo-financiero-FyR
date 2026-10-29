# Ideas de IA para el Sistema de Informes F&R

> **Cómo usar este documento**
> Este archivo es la **cola de pendientes de IA**. Cada idea se implementa
> **una por una**, y al terminar se **elimina de este archivo** (y se anota
> en el historial al final). Si el chat cambia o la sesión se pierde, basta
> con leer este documento para saber qué queda pendiente y cómo implementarlo.
>
> Regla: **no borrar ideas sin implementar**; solo moverlas a "Historial"
> cuando estén terminadas.

---

## Decisión técnica (aplicar a TODAS las ideas)

- **Proveedor**: Google Gemini (tier gratis, sin tarjeta).
  - **Modelos que SÍ funcionan en el tier gratis (verificado 29/10/2026)**:
    `gemini-flash-lite-latest` (primero en la lista), `gemini-3.6-flash`,
    `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`.
  - **Modelos YA RETIRADOS**: `gemini-2.0-flash`, `gemini-2.5-flash`,
    `gemini-2.5-flash-lite` → devuelven HTTP 404 "no longer available".
  - **Saturación**: `gemini-3.6-flash` a veces responde 503 "high demand";
    por eso hay 4 modelos en la lista y el módulo recuerda cuál funcionó
    (`_modelo_activo`) para ir directo al que sirve.
  - Si el tier gratis cambia: **Groq** (`openai/gpt-oss-120b`), mismo esquema
    de código, solo cambia la URL y la key. Otra alternativa: OpenRouter
    con modelos `:free`.
- **Configuración de la API** (importante, aprendido a la fuerza):
  - `maxOutputTokens: 4000` — con 900 el texto salía **cortado a media
    respuesta** (`finishReason: MAX_TOKENS`): los modelos "piensan" antes
    de responder y se comen los tokens de salida.
  - `thinkingConfig: {thinkingBudget: 0}` — responde sin razonamiento
    interno: más rápido (27 s → 7 s) y más barato. Si un modelo no lo
    acepta, el módulo reintenta sin esa opción.
  - Tiempos reales: primera llamada 20-30 s, siguientes ~7 s.
- **Key**: se guarda en `backend/.env` como `GEMINI_API_KEY=...`
  (archivo en `.gitignore`; **nunca** subir la key a GitHub).
- **Cliente HTTP**: `google-genai` (SDK oficial) o `requests` directo.
- **Prompt base** (común a todas):
  > "Eres analista senior de interventoría de alumbrado público en Colombia.
  >  Responde en español formal, con cifras exactas tomadas SOLO de los datos
  >  entregados. NO inventes ni recalcules números. No uses emojis."
- **Límites gratis (oct 2026)**: Gemini ~15 req/min y ~1M tokens/día.
  Sobra para un solo usuario. Groq: 30 req/min, 1.000 req/día.
- **Privacidad**: solo enviar **totales, porcentajes y KPIs precalculados**
  por la app. **NUNCA** enviar las ~235.000 filas de detalle de cuentas.
- **Mitigación de alucinaciones**: la app arma el prompt con cifras ya
  calculadas por Python; a la IA se le prohíbe hacer cálculos propios.
- **Si la API falla**: mostrar mensaje amable ("IA no disponible, intente
  más tarde"), jamás romper la página.

---

## Cola de pendientes (implementar en este orden sugerido)

### 3. Chat con los datos ("Pregúntale a la IA")
- **Dónde**: barra de chat flotante en informe general / información de
  referencia.
- **Capacidades**: preguntas tipo *"¿Cuánto se recaudó en Villavicencio en
  el último semestre?"*, *"¿Qué estrato debe más?"*, *"Compárame abril vs
  junio"*.
- **Implementación**: la app arma un **contexto con los agregados** (tablas
  resumidas por mes/estrato/clasificación) y la IA responde sobre eso.
  Si necesita datos que no están en el contexto, responde "no tengo ese dato".
- **Esfuerzo**: ~2-3 horas.
- **Riesgo**: que el usuario pida datos de meses sin detalle guardado →
  el contexto solo llevará resúmenes (que sí se conservan siempre).

### 4. Conclusiones automáticas en el Word
- **Dónde**: al generar `descargar_word` del informe general.
- **Flujo**: mismo prompt base + KPIs → párrafo de **conclusiones y
  recomendaciones** en lenguaje formal de interventoría → se inserta en el
  documento (sección final).
- **Esfuerzo**: ~1 hora.

### 5. Explicación de cifras en lenguaje llano (ayuda en KPIs)
- **Dónde**: ícono "?" junto a cada tarjeta KPI (facturación, recaudo,
  diferencia, IAP).
- **Flujo**: clic → prompt corto con la cifra y su contexto → la IA explica
  (ej. *"de cada $100 facturados, $95 se recaudaron"*).
- **Mejora posible**: pre-generar los textos una sola vez y **cachearlos**
  (no repetir la llamada en cada visita).
- **Esfuerzo**: ~45 min.

### 6. Proyección y metas de recaudo
- **Dónde**: sección de comportamiento anual (información de referencia).
- **Contenido**: proyección al cierre del año con el ritmo actual
  (*"al ritmo actual, el estrato 4 alcanzará $X en diciembre"*), avance
  contra meta anual si existe.
- **Cálculo**: la proyección se calcula en Python (regresión simple);
  la IA solo la redacta.
- **Esfuerzo**: ~1.5 horas.

### 7. Auditoría asistida de calidad de datos
- **Dónde**: después de subir un archivo, antes de confirmar la carga, o
  sección aparte de auditoría.
- **Chequeos en Python**:
  - Filas con consumos negativos o nulos.
  - Duplicados (mismo id_cliente en el mismo período).
  - Saltos >500% de un mes a otro.
  - Fechas fuera del período declarado.
  - Totales que no cuadran entre facturación y recaudo.
- **IA**: redacta el veredicto ("la base está en buen estado" / "corrija
  estos puntos").
- **Esfuerzo**: ~1.5 horas.

### 8. Ayuda en errores de carga de archivos
- **Dónde**: cuando falla o sale "pendiente" una carga (mensaje de error
  de columnas, formato, tamaño).
- **Flujo**: la app envía el mensaje técnico + columnas encontradas/faltantes
  → la IA explica **en español llano** qué tiene mal el archivo y cómo
  corregirlo.
- **Esfuerzo**: ~45 min.

### 9. Comparador de municipios y ranking
- **Dónde**: página o tarjeta que compare los 5 municipios.
- **Contenido**: ranking de facturación/recaudo, municipio que empeoró más,
  comparación de IAP.
- **IA**: solo redacta el "quién empeoró y por qué probablemente".
- **Esfuerzo**: ~1.5 horas.

### 10. Búsqueda semántica histórica
- **Dónde**: buscador general del sistema.
- **Capacidad**: entender frases como *"meses donde el recaudo fue peor que
  la facturación en más de 10%"* → la app traduce la intención a consulta
  sobre los resúmenes históricos (que se conservan siempre) y devuelve
  resultados.
- **Esfuerzo**: ~2 horas.

---

## Historial de ideas implementadas

*(Aquí se va moviendo cada idea al terminarla, con fecha y commit.)*

- **1. Análisis IA del informe** — 29 oct 2026 (implementado `6835d4a`,
  validado con key real).
  - Botón "Análisis IA" en `general.html` + endpoint `POST /api/analisis-ia`
    (rate limit 10/min) + módulo `backend/core/ia_analisis.py` con `urllib`
    (cero dependencias nuevas).
  - Envía **solo KPIs precalculados** (facturación, recaudo, % recaudado,
    consumo, kWh, cuentas, comparación vs mes anterior y la tabla por
    estrato/clasificación). **Nunca** las 235 mil filas de cuentas.
  - Responde con los 4 encabezados: RESUMEN EJECUTIVO / HALLAZGOS /
    ALERTAS / RECOMENDACIONES.
  - Validado con informe real de Villavicencio (julio 2026): cifras
    correctas, sin inventos, ~7 s en llamadas siguientes.
  - API key en `backend/.env` (`GEMINI_API_KEY=`), archivo en `.gitignore`.
- **2. Detección automática de anomalías y alertas** — 29 oct 2026.
  - Módulo `backend/core/alertas.py` con **11 reglas** en Python (sin IA):
    cobertura de recaudo <95%, sobrepago, cartera del período, caída de
    recaudo >10% con facturación estable, mayor brecha por clasificación,
    sobrepago por clasificación, cuentas con facturación $0, consumos
    negativos, `Id_cliente` duplicados, saltos >500% vs mes anterior, IAP
    dejado de facturar / no percibido.
  - Endpoint `GET /api/alertas/<report_id>` + tarjeta "Alertas del período"
    en `general.html` (se llena al abrir la página).
  - **Precalculación**: se guardan en la tabla nueva `alertas_reporte` al
    guardar el informe (`save_report_to_db`), y backfill con
    `backend/scripts/precalcular_alertas.py`.
  - **Rendimiento**: de 29 s → **0,02 s** por consulta. Hallazgos clave:
    un `general_data` parseado ocupa **~850 MB de RAM** (imposible cachear
    en memoria) y `json.loads` de 359 MB cuesta 5,3 s. Por eso se
    precalcula y se usa `load_only` en el endpoint para no leer el blob.
  - Tests: 36/36 OK, JS validado con `node --check`.
