# Columnas y mapeo

## Dónde se define (`backend/core/columnas.py`)

- `ALIASES_DEFAULT`: nombres conocidos por dato (ID, factura, impuesto,
  consumos, empresa, nombre, dirección, clase, mercado, estrato, sector,
  periodicidad, recaudo, municipio, fecha).
- `ETIQUETAS_CLAVE`: texto que ve el usuario por cada dato.
- `EJEMPLOS_CLAVE`: ejemplo corto por dato (precios en COP con `$` y
  puntos: `$437.726`). Se muestra en el cuestionario y en metadatos.
- `FACT_CLAVES` / `REC_CLAVES`: datos que busca cada archivo.

## Aprendizaje

Tabla `mapeo_columnas` (`clave` → lista de nombres vistos). Cada respuesta
del cuestionario o de metadatos se guarda con `_guardar_alias_columna()`:
la próxima vez un archivo con ese nombre se reconoce solo.

## Notas

- La comparación ignora tildes, mayúsculas y símbolos; luego intenta por
  palabras sueltas (ej. `VALOR IMPUESTO DEL ALUMBRADO PUBLICO` → `monto_AP`).
- Cada columna del archivo solo puede mapear un dato (se excluyen usadas).
- Si el archivo **no trae** un dato necesario, hay que elegir igual una
  columna o cancelar: sin esas columnas el informe no se puede armar.
