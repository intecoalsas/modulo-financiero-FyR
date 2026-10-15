# Informes General y Especiales

## Informe General (formato hoja Informe FyR)

Espejo de la hoja "Informe FyR" del archivo de Villavicencio/EMSA, para
todos los municipios (título, agente, resumen, tablas 1–5, notas y
gráficas; sin secciones de prosa):

Depuración (`core/depuracion.py`):

- **Resumen ejecutivo**: cuentas, kWh, base gravable, impuesto facturado
  y recaudado, % recaudo y tarifa efectiva.
- **1. Cuentas**, **2. Facturados ($)**, **3. Recaudados ($)**: filas
  Residencial E1–E6, Subtotal, Comercial, Oficial, Industrial, Otros
  (complemento del total) y TOTAL, en columnas Urbana/Rural/Total.
- **4. Consumo**: base gravable vs impuesto facturado (%), kWh.
- **5. Recaudo vs facturación**: diferencia y % recaudo.
- **Notas** (fuente, base gravable, definición de Otros, rec>fact) y las
  3 gráficas de la página a color.

La clasificación sale de los registros depurados (estrato 1–6 para
residencial; resto a su clase u Otros). Todo Arial Narrow 12/8 en negro,
tablas con encabezado negro como en la página.

## Regla INTECOAL (solo Word)

Tablas y gráficas de **todos** los Word generados llevan los colores de
la empresa (`#D9CF43` amarillo, `#4E3629` marrón, grises `#F2F2F2` /
`#BFBFBF`); lo único negro son las letras y números. La página y el
Excel no cambian.

La agregación vive en `core/fyr.py` (`FYR_ORDEN`, `fyr_agregar`) y la
reutilizan el Word y la página. En la página, Villavicencio/EMSA muestra
este mismo formato (resumen + tablas 1–5 + notas + 5 gráficas: pie por
clasificación, barras por estrato, barras facturado vs recaudado, pie
urbana/rural y barras % recaudo); los demás municipios conservan el
informe general clásico con tablas de detalle paginadas.

## Informe Especiales (clientes especiales)

Desde archivos (`build_especiales_desde_archivos`, San Pedro):

- **Nombre**: manda el archivo subido del mes.
- **Grupo/tarifa/periodo**: de la cartera (edición manual, como el
  "cambiar de grupo" del Excel).
- `calc_iap (L) = MIN(MAX(tarifa, consumo × 10%), TEC=35.018.100)`
- `saldo_fl (F-L) = facturación − L`
- `val_rec (R-L) = recaudo − L`
- Clasificación de tarifa (Especial/Otra/Residencial) y estado de
  facturación según periodicidad y mes.

Sin archivos/cartera se usa la lista fija de referencia.

## Variación del saldo negativo

Compara el mes actual con el anterior (misma comercializadora):

```
variación = (saldo anterior − saldo actual) / saldo anterior × 100
```

- **Positiva** (verde): el saldo negativo bajó → mejora.
- **Negativa** (roja): el saldo negativo subió → desmejora.
- El texto ejecutivo lo explica en palabras automáticamente.

## Encabezado

Ambos informes muestran al inicio la insignia
`Municipio · Comercializadora · Mes Año`, tanto recién procesados como
abiertos desde el historial.
