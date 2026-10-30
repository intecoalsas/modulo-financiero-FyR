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

### 3. Chat con los datos ("Pregúntale a la IA") — implementado, ver historial

### 4. Conclusiones automáticas en el Word — implementado, ver historial

### 5. Explicación de cifras en lenguaje llano (ayuda en KPIs) — implementado, ver historial

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
- **3. Chat con los datos ("Pregúntale a la IA")** — 29 oct 2026.
  - Panel flotante en `general.html` (`#chatCard` + botón `#chatBtn`) con
    historial de la conversación en el navegador (máx. 12 mensajes, no se
    guarda en la BD). Endpoint `POST /api/chat-ia` (20/min).
  - Módulo `backend/core/ia_chat.py`: el contexto sale de la tabla nueva
    `resumen_mes` (totales por mes + desglose por estrato/clasificación),
    **sin descomprimir el informe completo** (~850 MB en RAM). Se precalcula
    en `save_report_to_db` y se hizo backfill con
    `backend/scripts/precalcular_alertas.py` (17 resúmenes, ~0,6 s c/u).
  - Validado con preguntas reales: cifras exactas, identifica el estrato
    que debe más, cuenta los meses cargados y responde "no tengo ese dato"
    cuando se le pregunta fuera del contexto. ~7-9 s por respuesta.
  - Reglas anti-alucinación en `_INSTRUCCIONES_CHAT` (solo datos entregados,
    formato colombiano, sin emojis).
  - `resumen_mes` agregada a `TABLAS` en `scripts/migrar_a_postgres.py`.
- **4. Conclusiones automáticas en el Word** — 29 oct 2026.
  - Al descargar `descargar/word/<id>?tipo=general`, si el reporte no tiene
    conclusiones se generan con la IA (`generar_conclusiones` con
    `_INSTRUCCIONES_CONCLUSIONES`: 2 párrafos, ≤220 palabras, texto plano
    para Word) y se guardan en la columna nueva `reports.conclusiones_ia`
    (ALTER defensivo en `app.py`).
  - La sección "CONCLUSIONES Y RECOMENDACIONES" se inserta antes de la
    firma en `generar_word_general` (limpiando **, # y viñetas de la IA).
  - **Solo la primera descarga llama a la IA** (~40 s); las siguientes
    usan las guardadas. `?actualizar_ia=1` fuerza regenerarlas.
  - Si la IA falla, el Word se descarga igual sin la sección (nunca rompe).
  - Validado con informe real de Villavicencio: cifras exactas, sin marcas
    de markdown, 36/36 tests OK.
- **5. Explicación de cifras en lenguaje llano (ayuda en KPIs)** —
  30 oct 2026.
  - Botón "?" en las 4 tarjetas KPI (Facturación, Recaudo, Valor Consumo,
    Cartera). Al pulsarlo se explica la cifra en 2-3 frases (≤70 palabras)
    con ejemplo proporcional ("de cada $100 facturados…") y una valoración
    de si el resultado es bueno, normal o preocupante.
  - Endpoint `POST /api/explicar-kpi` (15/min) + `explicar_kpi` en
    `core/ia_chat.py`; el contexto sale de `resumen_mes` (sin descomprimir
    el informe) e incluye el historial de meses para comparar.
  - **Caché en `reports.explicaciones_ia`** (JSON por KPI, columna nueva
    con ALTER defensivo): primera consulta ~3-7 s, siguientes 0,00 s.
  - Si la IA falla, la tarjeta muestra el error y la página sigue normal.
  - Validado con datos reales (San Pedro agosto 2026): "de cada $100
    facturados se recaudaron $87,5… la cifra más baja de los últimos
    meses", coherente con el historial. 36/36 tests OK.
