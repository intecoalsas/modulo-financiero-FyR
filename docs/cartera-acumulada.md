# Cartera Acumulada SP (solo San Pedro)

Réplica en sistema del libro `Clientes Especiales SP 2026.xlsx`.

## Reglas

1. **Solo San Pedro**: la acumulación corre únicamente para ese municipio.
2. **2019–2025 congelados**: vienen del archivo de referencia y el código
   nunca los escribe (años `< 2026` se rechazan).
3. **El mes trae R-L**: cada mes de cartera es el `R-L (recaudo −
   liquidación)` del informe especial mensual ya hecho, buscado por ID
   de cuenta (equivale al `VLOOKUP` del Excel). No es F-L.
4. **La columna del año suma sus meses**: `saldos[año] = Σ meses 1–12`.
5. **Totales estilo SUMIF** (filas 60–61 del Excel):
   - Por año: suma de saldos positivos (favor) / negativos (pagar).
   - Total general: `SUMIF` sobre el total de cada cliente.
   - `total_cartera` por cliente = suma de sus años sin 2019 (columna L).
6. **Identidad**: el nombre se sincroniza del archivo mensual; grupo,
   tarifa y periodo se mantienen desde la cartera (cambio manual).
7. **Reprocesable**: re-subir un mes sobrescribe su valor (como el
   VLOOKUP, que siempre refleja la hoja mensual).

## Año nuevo automático

Al subir el primer archivo de un año inexistente (ej. enero 2027),
`ensure_cartera_anio()` clona el año más reciente como base: saldos del
año nuevo en cero y meses vacíos. En la página (`/cartera?anio=`):

- Columnas de años 2019 → año en vista + 12 meses del año en vista.
- Selector para cambiar de año.
- Los meses de años cerrados quedan en bloques colapsables junto a su
  año, con sus totales de favor/pagar.

## Carga inicial

Desde la página de cartera se sube el libro de referencia
(`cargar_cartera_desde_referencia`): lee `CARTERA 5 AÑOS`, tarifas y
descripción, y re-acumula los meses de los informes ya guardados con la
regla R-L.
