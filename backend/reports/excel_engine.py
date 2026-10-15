from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.utils import get_column_letter
from datetime import datetime


# Colores corporativos INTECOAL en todos los libros
HEADER_FILL = PatternFill("solid", fgColor="0D0D0D")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

ALT_ROW_FILL = PatternFill("solid", fgColor="F2F2F2")
BORDER_COLOR = Side(style="thin", color="BFBFBF")
THIN_BORDER = Border(left=BORDER_COLOR, right=BORDER_COLOR,
                     top=BORDER_COLOR, bottom=BORDER_COLOR)

TITLE_FONT = Font(name="Calibri", size=18, bold=True, color="0D0D0D")
SUBTITLE_FONT = Font(name="Calibri", size=14, bold=True, color="0D0D0D")
KPI_FONT = Font(name="Calibri", size=22, bold=True, color="0D0D0D")
KPI_LABEL = Font(name="Calibri", size=10, color="666666")

GREEN_FONT = Font(name="Calibri", size=11, color="1E7A1E")
RED_FONT = Font(name="Calibri", size=11, color="A93226")
GREEN_FILL = PatternFill("solid", fgColor="D4EDDA")
RED_FILL = PatternFill("solid", fgColor="F8D7DA")

TOTAL_FILL = PatternFill("solid", fgColor="D9CF43")
TOTAL_FONT = Font(name="Calibri", size=11, bold=True, color="0D0D0D")

SECTION_FILL = PatternFill("solid", fgColor="D9CF43")
SECTION_FONT = Font(name="Calibri", size=12, bold=True, color="0D0D0D")

MONEDA_FMT = '$#,##0'
MONEDA_DEC = '$#,##0.00'
PORC_FMT = '0.00%'
NUM_FMT = '#,##0'
FECHA_FMT = 'DD/MM/YYYY HH:MM'


# Pinta las series de un gráfico con colores corporativos INTECOAL
def _colorear_series(chart, colores):
    try:
        from openpyxl.chart.shapes import GraphicalProperties
        for ser, color in zip(chart.series, colores):
            ser.graphicalProperties = GraphicalProperties(solidFill=color)
    except Exception:
        pass


# Convierte un valor a número (si no se puede, devuelve 0)
def _fmtCurrency(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# Pinta una fila de encabezados con el fondo y letra del tema
def _style_header_row(ws, row, max_col):
    for col in range(1, max_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER


# Pone bordes a las filas de datos y pintura intercalada (filas zebra)
def _style_data_rows(ws, start_row, end_row, max_col):
    for r in range(start_row, end_row + 1):
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = THIN_BORDER
            if (r - start_row) % 2 == 1:
                cell.fill = ALT_ROW_FILL


# Calcula el ancho de cada columna según el texto más largo que tenga
def _auto_width(ws, max_col, min_width=10, max_width=40):
    for col in range(1, max_col + 1):
        max_len = 0
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=col, max_col=col):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(col)].width = min(max(max_len + 3, min_width), max_width)


# Agrega una franja de título de sección (con fondo amarillo)
def _add_section_title(ws, row, title, max_col):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=max_col)
    cell = ws.cell(row=row, column=1, value=title)
    cell.font = SECTION_FONT
    cell.fill = SECTION_FILL
    cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row].height = 28
    for c in range(1, max_col + 1):
        ws.cell(row=row, column=c).border = THIN_BORDER


# Agrega un número grande (KPI) con su etiqueta encima
def _add_kpi(ws, row, col, label, value, fmt=MONEDA_FMT):
    ws.cell(row=row, column=col, value=label).font = KPI_LABEL
    ws.cell(row=row, column=col).alignment = Alignment(horizontal="center")
    cell = ws.cell(row=row + 1, column=col, value=_fmtCurrency(value))
    cell.font = KPI_FONT
    cell.number_format = fmt
    cell.alignment = Alignment(horizontal="center")


# HOJA 1: PORTADA
# Armado del libro de informe general: creación de cada hoja
def _hoja_portada(wb, general_data, especiales_data):
    ws = wb.active
    ws.title = "PORTADA"
    ws.sheet_properties.tabColor = "FFF8DC"

    max_col = 8

    # Logo placeholder
    ws.merge_cells("A1:H1")
    logo_cell = ws.cell(row=1, column=1, value="CELSIA")
    logo_cell.font = Font(name="Calibri", size=36, bold=True, color="0D0D0D")
    logo_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 50

    # Título
    ws.merge_cells("A3:H3")
    title = ws.cell(row=3, column=1, value="INFORME FACTURACIÓN Y RECAUDO")
    title.font = TITLE_FONT
    title.alignment = Alignment(horizontal="center")

    ws.merge_cells("A4:H4")
    sub = ws.cell(row=4, column=1, value="Impuesto Alumbrado Público — Municipio de Calima")
    sub.font = SUBTITLE_FONT
    sub.alignment = Alignment(horizontal="center")

    # Fecha
    ws.merge_cells("A6:H6")
    fecha = ws.cell(row=6, column=1, value=f"Generado: {datetime.now().strftime('%d de %B de %Y — %H:%M')}")
    fecha.font = Font(name="Calibri", size=11, color="666666")
    fecha.alignment = Alignment(horizontal="center")

    # KPIs principales
    f = general_data["f"]
    r_data = general_data["r"]
    esp = (especiales_data or {}).get("totales") if especiales_data else None

    row = 8
    _add_section_title(ws, row, "RESUMEN EJECUTIVO", max_col)

    row = 10
    headers = ["", "Imp. Alumbrado P\u00fablico", "Consumo Energ\u00eda", "Consumo (kWh)", "Recaudo A.P.", "", "", ""]
    for i, h in enumerate(headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    row = 11
    _add_kpi(ws, row, 2, "VALOR", f["total_imp"])
    _add_kpi(ws, row, 3, "VALOR", f["total_consumo"])
    cell = ws.cell(row=row, column=4, value=f["total_kwh"])
    cell.font = KPI_FONT
    cell.number_format = NUM_FMT
    cell.alignment = Alignment(horizontal="center")
    _add_kpi(ws, row, 5, "VALOR", r_data["total_valor"])

    # Labels
    for c in [2, 3, 5]:
        ws.cell(row=row + 2, column=c, value="Base Depurada").font = KPI_LABEL
        ws.cell(row=row + 2, column=c).alignment = Alignment(horizontal="center")

    row = 14
    for c, val in [(2, f["total_imp"]), (3, f["total_consumo"]), (5, r_data["total_valor"])]:
        cell = ws.cell(row=row, column=c, value=_fmtCurrency(val))
        cell.font = Font(name="Calibri", size=11, bold=True)
        cell.number_format = MONEDA_FMT
        cell.alignment = Alignment(horizontal="center")

    # Especiales (si el municipio trae informe de clientes especiales)
    if esp:
        row = 17
        _add_section_title(ws, row, "CLIENTES ESPECIALES", max_col)
        row = 19
        espec_headers = ["", "Cuentas", "Facturaci\u00f3n", "Recaudo", "Saldo F-L", "Saldo +", "Saldo -"]
        for i, h in enumerate(espec_headers, 1):
            ws.cell(row=row, column=i, value=h)
        _style_header_row(ws, row, 7)

        row = 20
        ws.cell(row=row, column=2, value=esp["cuentas"]).font = KPI_FONT
        ws.cell(row=row, column=2).alignment = Alignment(horizontal="center")
        for c, val in [(3, esp["fact"]), (4, esp["rec"]), (5, esp["total_saldo_fl"]),
                       (6, esp["saldo_pos"]), (7, esp["saldo_neg"])]:
            cell = ws.cell(row=row, column=c, value=_fmtCurrency(val))
            cell.font = Font(name="Calibri", size=14, bold=True, color="0D0D0D")
            cell.number_format = MONEDA_FMT
            cell.alignment = Alignment(horizontal="center")

    ws.freeze_panes = "A2"
    _auto_width(ws, max_col)
    return ws


# HOJA 2: RESUMEN FINANCIERO
def _hoja_resumen(wb, general_data):
    ws = wb.create_sheet("RESUMEN FINANCIERO")
    ws.sheet_properties.tabColor = "FFF8DC"
    max_col = 6

    ws.merge_cells("A1:F1")
    ws.cell(row=1, column=1, value="RESUMEN FINANCIERO — DEPURACIÓN FACTURACIÓN").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    # Estadísticas generales
    row = 3
    _add_section_title(ws, row, "ESTADÍSTICAS GENERALES — FACTURACIÓN", max_col)
    row = 4
    ws.cell(row=row, column=1, value="INDICADOR").font = HEADER_FONT
    ws.cell(row=row, column=1).fill = HEADER_FILL
    ws.cell(row=row, column=1).border = THIN_BORDER
    ws.cell(row=row, column=2, value="VALOR").font = HEADER_FONT
    ws.cell(row=row, column=2).fill = HEADER_FILL
    ws.cell(row=row, column=2).border = THIN_BORDER
    ws.cell(row=row, column=2).alignment = Alignment(horizontal="center")

    for i, (k, v) in enumerate(general_data["estad_general"].items(), 5):
        ws.cell(row=i, column=1, value=k).border = THIN_BORDER
        ws.cell(row=i, column=2, value=v).border = THIN_BORDER
        ws.cell(row=i, column=2).alignment = Alignment(horizontal="center")
        if (i - 5) % 2 == 1:
            ws.cell(row=i, column=1).fill = ALT_ROW_FILL
            ws.cell(row=i, column=2).fill = ALT_ROW_FILL

    # Resumen financiero
    row = 5 + len(general_data["estad_general"]) + 1
    _add_section_title(ws, row, "RESUMEN FINANCIERO", max_col)
    row += 1
    fin_headers = ["CONCEPTO", "BASE ORIGINAL", "BASE DEPURADA", "DIFERENCIA", "", ""]
    for i, h in enumerate(fin_headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    for j, (concepto, orig, dep, dif) in enumerate(general_data["resumen_financiero"], row + 1):
        ws.cell(row=j, column=1, value=concepto).border = THIN_BORDER
        for c, val in [(2, orig), (3, dep), (4, dif)]:
            cell = ws.cell(row=j, column=c, value=val)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")
    _style_data_rows(ws, row + 1, row + len(general_data["resumen_financiero"]), 4)

    # Banderas
    row = row + len(general_data["resumen_financiero"]) + 2
    _add_section_title(ws, row, "BANDERAS DE DEPURACIÓN", max_col)
    row += 1
    flag_headers = ["BANDERA", "CANTIDAD", "IMP.", "CONS.", "DESCRIPCIÓN", ""]
    for i, h in enumerate(flag_headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    for j, (bandera, cant, imp_f, cons_f, desc) in enumerate(general_data["banderas"], row + 1):
        ws.cell(row=j, column=1, value=bandera).border = THIN_BORDER
        ws.cell(row=j, column=2, value=cant).border = THIN_BORDER
        ws.cell(row=j, column=2).alignment = Alignment(horizontal="center")
        ws.cell(row=j, column=3, value=imp_f).border = THIN_BORDER
        ws.cell(row=j, column=3).alignment = Alignment(horizontal="center")
        ws.cell(row=j, column=4, value=cons_f).border = THIN_BORDER
        ws.cell(row=j, column=4).alignment = Alignment(horizontal="center")
        ws.cell(row=j, column=5, value=desc).border = THIN_BORDER
        if imp_f == "NO" or cons_f == "NO":
            ws.cell(row=j, column=3).font = RED_FONT
            ws.cell(row=j, column=4).font = RED_FONT
    _style_data_rows(ws, row + 1, row + len(general_data["banderas"]), 5)

    # Estadísticas recaudo
    row = row + len(general_data["banderas"]) + 2
    _add_section_title(ws, row, "ESTADÍSTICAS GENERALES — RECAUDO", max_col)
    row += 1
    ws.cell(row=row, column=1, value="INDICADOR").font = HEADER_FONT
    ws.cell(row=row, column=1).fill = HEADER_FILL
    ws.cell(row=row, column=1).border = THIN_BORDER
    ws.cell(row=row, column=2, value="VALOR").font = HEADER_FONT
    ws.cell(row=row, column=2).fill = HEADER_FILL
    ws.cell(row=row, column=2).border = THIN_BORDER
    ws.cell(row=row, column=2).alignment = Alignment(horizontal="center")

    for i, (k, v) in enumerate(general_data["estad_recaudo"].items(), row + 1):
        ws.cell(row=i, column=1, value=k).border = THIN_BORDER
        ws.cell(row=i, column=2, value=v).border = THIN_BORDER
        ws.cell(row=i, column=2).alignment = Alignment(horizontal="center")
        if (i - row - 1) % 2 == 1:
            ws.cell(row=i, column=1).fill = ALT_ROW_FILL
            ws.cell(row=i, column=2).fill = ALT_ROW_FILL

    # Resumen recaudo
    row = row + len(general_data["estad_recaudo"]) + 2
    ws.cell(row=row, column=1, value="CONCEPTO").font = HEADER_FONT
    ws.cell(row=row, column=1).fill = HEADER_FILL
    ws.cell(row=row, column=1).border = THIN_BORDER
    ws.cell(row=row, column=2, value="BASE ORIGINAL").font = HEADER_FONT
    ws.cell(row=row, column=2).fill = HEADER_FILL
    ws.cell(row=row, column=2).border = THIN_BORDER
    ws.cell(row=row, column=3, value="BASE DEPURADA").font = HEADER_FONT
    ws.cell(row=row, column=3).fill = HEADER_FILL
    ws.cell(row=row, column=3).border = THIN_BORDER
    ws.cell(row=row, column=4, value="DIFERENCIA").font = HEADER_FONT
    ws.cell(row=row, column=4).fill = HEADER_FILL
    ws.cell(row=row, column=4).border = THIN_BORDER

    for j, (concepto, orig, dep, dif) in enumerate(general_data["resumen_recaudo"], row + 1):
        ws.cell(row=j, column=1, value=concepto).border = THIN_BORDER
        ws.cell(row=j, column=2, value=orig).border = THIN_BORDER
        ws.cell(row=j, column=3, value=dep).border = THIN_BORDER
        ws.cell(row=j, column=4, value=dif).border = THIN_BORDER

    ws.freeze_panes = "A2"
    _auto_width(ws, max_col, max_width=60)
    return ws


# HOJA 3: CONSOLIDADO POR CLASIFICACIÓN
# Autorresumen facturado vs recaudado por cada clase de cliente
def _hoja_consolidado(wb, general_data):
    ws = wb.create_sheet("CONSOLIDADO")
    ws.sheet_properties.tabColor = "FFF8DC"
    max_col = 5

    ws.merge_cells("A1:E1")
    ws.cell(row=1, column=1, value="CONSOLIDADO FACTURACIÓN vs RECAUDO").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    row = 3
    headers = ["CLASIFICACIÓN", "FACTURACIÓN", "RECAUDO", "DIFERENCIA", "EFICACIA %"]
    for i, h in enumerate(headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    consolidado = general_data["consolidado"]
    for j, (clasif, fact, rec, dif, efic) in enumerate(consolidado, row + 1):
        ws.cell(row=j, column=1, value=clasif).border = THIN_BORDER
        ws.cell(row=j, column=1).font = Font(name="Calibri", size=11, bold=(clasif == "TOTAL"))

        for c, val, fmt in [(2, fact, MONEDA_FMT), (3, rec, MONEDA_FMT),
                             (4, dif, MONEDA_FMT), (5, efic, PORC_FMT)]:
            cell = ws.cell(row=j, column=c, value=_fmtCurrency(val) if c < 5 else val)
            cell.number_format = fmt
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")

        # Colores en eficacia
        if clasif != "TOTAL":
            if efic >= 1:
                ws.cell(row=j, column=5).font = GREEN_FONT
            elif efic < 0.8:
                ws.cell(row=j, column=5).font = RED_FONT

        # Colores en diferencia
        if dif < 0:
            ws.cell(row=j, column=4).font = RED_FONT
        elif dif > 0:
            ws.cell(row=j, column=4).font = GREEN_FONT

        if clasif == "TOTAL":
            for c in range(1, max_col + 1):
                ws.cell(row=j, column=c).fill = TOTAL_FILL
                ws.cell(row=j, column=c).font = TOTAL_FONT

    end_row = row + len(consolidado)
    _style_data_rows(ws, row + 1, end_row - 1, max_col)

    # Gráfico
    chart = BarChart()
    chart.type = "col"
    chart.title = "Facturación vs Recaudo por Clasificación"
    chart.y_axis.title = "Valor ($)"
    chart.style = 10
    chart.width = 22
    chart.height = 14

    data = Reference(ws, min_col=2, min_row=row, max_col=3, max_row=end_row - 1)
    cats = Reference(ws, min_col=1, min_row=row + 1, max_row=end_row - 1)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    _colorear_series(chart, ["D9CF43", "0D0D0D"])
    ws.add_chart(chart, "A" + str(end_row + 2))

    ws.freeze_panes = "A4"
    _auto_width(ws, max_col)
    return ws


# HOJA 4: DETALLE FACTURACIÓN
# Todas las cuentas de la facturación ya depurada
def _hoja_detalle_fact(wb, general_data):
    ws = wb.create_sheet("DETALLE FACTURACIÓN")
    ws.sheet_properties.tabColor = "FFF8DC"

    headers = ["ID", "EMPRESA", "NOMBRE", "DIRECCIÓN", "CLASE", "TIPO",
               "ESTRATO", "SECTOR", "PERIODICIDAD", "IMP AP ($)", "CONSUMO ($)", "KWH"]
    max_col = len(headers)

    ws.merge_cells("A1:L1")
    ws.cell(row=1, column=1, value="DETALLE CUENTAS — FACTURACIÓN DEPURADA").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    row = 3
    for i, h in enumerate(headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    registros = general_data["facturacion"]
    for j, rec in enumerate(registros, row + 1):
        ws.cell(row=j, column=1, value=rec["Id_cliente"]).border = THIN_BORDER
        ws.cell(row=j, column=2, value=rec["Empresa"]).border = THIN_BORDER
        ws.cell(row=j, column=3, value=rec["Nombre"]).border = THIN_BORDER
        ws.cell(row=j, column=4, value=rec["Direccion"]).border = THIN_BORDER
        ws.cell(row=j, column=5, value=rec["Clase"]).border = THIN_BORDER
        ws.cell(row=j, column=6, value=rec["Tipo"]).border = THIN_BORDER
        ws.cell(row=j, column=7, value=rec["Estrato"]).border = THIN_BORDER
        ws.cell(row=j, column=8, value=rec["Sector"]).border = THIN_BORDER
        ws.cell(row=j, column=9, value=rec["Periodicidad"]).border = THIN_BORDER
        for c, key in [(10, "ImpuestoAP"), (11, "Consumo$"), (12, "ConsumokWh")]:
            cell = ws.cell(row=j, column=c, value=_fmtCurrency(rec[key]))
            cell.number_format = MONEDA_FMT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")

    end_row = row + len(registros)
    _style_data_rows(ws, row + 1, end_row, max_col)

    # Fila total
    ws.cell(row=end_row + 1, column=1, value="TOTAL").font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=1).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=1).border = THIN_BORDER
    ws.cell(row=end_row + 1, column=10, value=general_data["f"]["total_imp"]).number_format = MONEDA_FMT
    ws.cell(row=end_row + 1, column=10).font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=10).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=10).border = THIN_BORDER
    ws.cell(row=end_row + 1, column=11, value=general_data["f"]["total_consumo"]).number_format = MONEDA_FMT
    ws.cell(row=end_row + 1, column=11).font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=11).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=11).border = THIN_BORDER
    ws.cell(row=end_row + 1, column=12, value=general_data["f"]["total_kwh"]).number_format = NUM_FMT
    ws.cell(row=end_row + 1, column=12).font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=12).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=12).border = THIN_BORDER

    ws.auto_filter.ref = f"A3:L{end_row}"
    ws.freeze_panes = "A4"
    _auto_width(ws, max_col, max_width=35)
    return ws


# HOJA 5: DETALLE RECAUDO
# Todas las cuentas del recaudo ya depurado
def _hoja_detalle_rec(wb, general_data):
    ws = wb.create_sheet("DETALLE RECAUDO")
    ws.sheet_properties.tabColor = "FFF8DC"

    headers = ["ID", "EMPRESA", "TIPO", "NOMBRE", "DIRECCIÓN", "CLASE",
               "SECTOR", "ESTRATO", "VALOR AP DEP ($)"]
    max_col = len(headers)

    ws.merge_cells("A1:I1")
    ws.cell(row=1, column=1, value="DETALLE CUENTAS — RECAUDO DEPURADO").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    row = 3
    for i, h in enumerate(headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    registros = general_data["recaudo"]
    for j, rec in enumerate(registros, row + 1):
        ws.cell(row=j, column=1, value=rec["Id_cliente"]).border = THIN_BORDER
        ws.cell(row=j, column=2, value=rec["Empresa"]).border = THIN_BORDER
        ws.cell(row=j, column=3, value=rec["Tipo"]).border = THIN_BORDER
        ws.cell(row=j, column=4, value=rec["Nombre"]).border = THIN_BORDER
        ws.cell(row=j, column=5, value=rec["Direccion"]).border = THIN_BORDER
        ws.cell(row=j, column=6, value=rec["Clase"]).border = THIN_BORDER
        ws.cell(row=j, column=7, value=rec["Sector"]).border = THIN_BORDER
        ws.cell(row=j, column=8, value=rec["Estrato"]).border = THIN_BORDER
        cell = ws.cell(row=j, column=9, value=_fmtCurrency(rec["ValorAP"]))
        cell.number_format = MONEDA_FMT
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="right")

    end_row = row + len(registros)
    _style_data_rows(ws, row + 1, end_row, max_col)

    # Fila total
    ws.cell(row=end_row + 1, column=1, value="TOTAL").font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=1).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=1).border = THIN_BORDER
    ws.cell(row=end_row + 1, column=9, value=general_data["r"]["total_valor"]).number_format = MONEDA_FMT
    ws.cell(row=end_row + 1, column=9).font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=9).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=9).border = THIN_BORDER

    ws.auto_filter.ref = f"A3:I{end_row}"
    ws.freeze_panes = "A4"
    _auto_width(ws, max_col, max_width=35)
    return ws


# HOJA 6: ESPECIALES - DASHBOARD
# Resumen por grupo de los clientes especiales
def _hoja_esp_dashboard(wb, especiales_data):
    ws = wb.create_sheet("ESPECIALES DASHBOARD")
    ws.sheet_properties.tabColor = "FFF8DC"
    max_col = 8

    ws.merge_cells("A1:H1")
    ws.cell(row=1, column=1, value="CLIENTES ESPECIALES — CONSOLIDADO POR GRUPO").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    row = 3
    headers = ["GRUPO", "CUENTAS", "FACTURACIÓN", "RECAUDO", "CONSUMO",
               "SUMA SALDOS F-L", "SALDO NEGATIVO", "SALDO POSITIVO"]
    for i, h in enumerate(headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    grupos = especiales_data["grupos"]
    for j, g in enumerate(grupos, row + 1):
        d = especiales_data["por_clase"][g]
        ws.cell(row=j, column=1, value=g).border = THIN_BORDER
        ws.cell(row=j, column=1).font = Font(name="Calibri", size=11, bold=True)
        ws.cell(row=j, column=2, value=d["n"]).border = THIN_BORDER
        ws.cell(row=j, column=2).alignment = Alignment(horizontal="center")

        for c, key in [(3, "fact"), (4, "rec"), (5, "consumo"),
                       (6, "saldo_fl"), (7, "saldo_neg"), (8, "saldo_pos")]:
            cell = ws.cell(row=j, column=c, value=_fmtCurrency(d[key]))
            cell.number_format = MONEDA_FMT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")

        # Colores saldo
        if d["saldo_fl"] < 0:
            ws.cell(row=j, column=6).font = RED_FONT
        else:
            ws.cell(row=j, column=6).font = GREEN_FONT

    # Total
    end_row = row + len(grupos)
    tot = especiales_data["totales"]
    ws.cell(row=end_row + 1, column=1, value="TOTAL").font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=1).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=1).border = THIN_BORDER
    ws.cell(row=end_row + 1, column=2, value=tot["cuentas"]).font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=2).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=2).border = THIN_BORDER
    ws.cell(row=end_row + 1, column=2).alignment = Alignment(horizontal="center")

    for c, key in [(3, "fact"), (4, "rec"), (5, "consumo"),
                   (6, "total_saldo_fl"), (7, "saldo_neg"), (8, "saldo_pos")]:
        cell = ws.cell(row=end_row + 1, column=c, value=_fmtCurrency(tot[key]))
        cell.number_format = MONEDA_FMT
        cell.font = TOTAL_FONT
        cell.fill = TOTAL_FILL
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="right")

    _style_data_rows(ws, row + 1, end_row, max_col)

    # Gráfico
    chart = BarChart()
    chart.type = "col"
    chart.title = "Facturación vs Recaudo vs Diferencia por Grupo"
    chart.y_axis.title = "Valor ($)"
    chart.style = 10
    chart.width = 24
    chart.height = 14

    data_ref = Reference(ws, min_col=3, min_row=row, max_col=4, max_row=end_row)
    cats = Reference(ws, min_col=1, min_row=row + 1, max_row=end_row)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats)
    _colorear_series(chart, ["D9CF43", "0D0D0D"])
    ws.add_chart(chart, "A" + str(end_row + 3))

    ws.freeze_panes = "A4"
    _auto_width(ws, max_col, max_width=25)
    return ws


# HOJA 7: ESPECIALES - DETALLE
# Cuenta por cuenta de los clientes especiales con sus cálculos
def _hoja_esp_detalle(wb, especiales_data, novedades=None):
    ws = wb.create_sheet("ESPECIALES DETALLE")
    ws.sheet_properties.tabColor = "FFF8DC"

    headers = ["ID CUENTA", "NOMBRE", "GRUPO", "TARIFA MÍNIMA", "CONSUMO",
               "FACTURACIÓN", "RECAUDO", "VERIF. FACTURADO", "PERIODO",
               "CÁLCULO IAP", "SALDOS F-L", "% CEE", "VAL. RECAUDA.",
               "VAL. %", "VAL. MÍNIMA", "NOVEDAD / OBSERVACIÓN"]
    max_col = len(headers)

    ws.merge_cells("A1:P1")
    ws.cell(row=1, column=1, value="DETALLE CLIENTES ESPECIALES").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    row = 3
    for i, h in enumerate(headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    filas = especiales_data["filas"]
    for j, e in enumerate(filas, row + 1):
        ws.cell(row=j, column=1, value=e["id"]).border = THIN_BORDER
        ws.cell(row=j, column=2, value=e["nombre"]).border = THIN_BORDER
        ws.cell(row=j, column=3, value=e["clase"]).border = THIN_BORDER

        for c, key, fmt in [(4, "tarifa_minima", MONEDA_FMT), (5, "consumo", MONEDA_FMT),
                             (6, "facturacion", MONEDA_FMT), (7, "recaudo", MONEDA_FMT)]:
            cell = ws.cell(row=j, column=c, value=_fmtCurrency(e[key]))
            cell.number_format = fmt
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")

        ws.cell(row=j, column=8, value=e["verificado"]).border = THIN_BORDER
        ws.cell(row=j, column=8).alignment = Alignment(horizontal="center")
        if e["verificado"] == "NO":
            ws.cell(row=j, column=8).font = RED_FONT

        ws.cell(row=j, column=9, value=e["periodo"]).border = THIN_BORDER

        for c, key, fmt in [(10, "calc_iap", MONEDA_FMT), (11, "saldo_fl", MONEDA_FMT),
                             (12, "pct_cee", PORC_FMT), (13, "val_rec", MONEDA_FMT)]:
            cell = ws.cell(row=j, column=c, value=e[key] if key != "pct_cee" else e[key])
            cell.number_format = fmt
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")

        ws.cell(row=j, column=14, value=e["val_tarifa_pct"]).border = THIN_BORDER
        ws.cell(row=j, column=14).alignment = Alignment(horizontal="center")
        ws.cell(row=j, column=15, value=e["val_tarifa_min"]).border = THIN_BORDER
        ws.cell(row=j, column=15).alignment = Alignment(horizontal="center")

        nov = (novedades or {}).get(str(e["id"]), (novedades or {}).get(e["id"], ""))
        if nov:
            cell = ws.cell(row=j, column=16, value=nov)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="left", wrap_text=True)
            cell.fill = ALT_ROW_FILL

        # Colores
        if e["saldo_fl"] < 0:
            ws.cell(row=j, column=11).font = RED_FONT
        else:
            ws.cell(row=j, column=11).font = GREEN_FONT

        if e["val_rec"] < 0:
            ws.cell(row=j, column=13).font = RED_FONT
        else:
            ws.cell(row=j, column=13).font = GREEN_FONT

        if e["val_tarifa_pct"] == "Especial":
            ws.cell(row=j, column=14).fill = GREEN_FILL
        elif e["val_tarifa_pct"] == "Residencial":
            ws.cell(row=j, column=14).fill = PatternFill("solid", fgColor="D1ECF1")

        if e["val_tarifa_min"] == "Tarifa Especial":
            ws.cell(row=j, column=15).fill = GREEN_FILL

    end_row = row + len(filas)
    _style_data_rows(ws, row + 1, end_row, max_col)

    # Total
    tot = especiales_data["totales"]
    ws.cell(row=end_row + 1, column=1, value="TOTAL").font = TOTAL_FONT
    ws.cell(row=end_row + 1, column=1).fill = TOTAL_FILL
    ws.cell(row=end_row + 1, column=1).border = THIN_BORDER
    for c, key in [(5, "consumo"), (6, "fact"), (7, "rec")]:
        cell = ws.cell(row=end_row + 1, column=c, value=_fmtCurrency(tot[key]))
        cell.number_format = MONEDA_FMT
        cell.font = TOTAL_FONT
        cell.fill = TOTAL_FILL
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="right")

    ws.auto_filter.ref = f"A3:P{end_row}"
    ws.freeze_panes = "A4"
    _auto_width(ws, max_col, max_width=30)
    return ws


# HOJA: ANÁLISIS DEL PERIODO (ESPECIALES)
# Hoja extra que resume los hallazgos del periodo para clientes especiales
def _hoja_analisis_especiales(wb, especiales_data, analisis_ejecutivo=None, variacion=None):
    ws = wb.create_sheet("ANÁLISIS ESPECIALES")
    ws.sheet_properties.tabColor = "FFF8DC"
    max_col = 6

    ws.merge_cells("A1:F1")
    ws.cell(row=1, column=1, value="ANÁLISIS DEL PERIODO — CUENTAS ESPECIALES").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    anal = especiales_data.get("analisis") or {}
    if not anal:
        ws.merge_cells("A3:F3")
        ws.cell(row=3, column=1, value="Sin análisis disponible para este reporte.").font = Font(name="Calibri", size=11, color="666666")
        ws.freeze_panes = "A2"
        _auto_width(ws, max_col)
        return ws

    row = 3
    _add_section_title(ws, row, "INDICADORES DEL PERIODO", max_col)
    row += 1
    kpi_headers = ["CONCEPTO", "VALOR", "", "", "", ""]
    for i, h in enumerate(kpi_headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    indicadores = [
        ("IAP dejado de facturar por el agente", anal.get("iap_dejado_facturar", 0), MONEDA_FMT),
        ("IAP no percibido por el Municipio", anal.get("iap_no_percibido_municipio", 0), MONEDA_FMT),
        ("Cuentas sin facturación", anal.get("cuentas_sin_facturar", 0), NUM_FMT),
        ("Cuentas con tarifa diferente a la especial", anal.get("cuentas_otras_tarifas", 0), NUM_FMT),
        ("Cuentas bimestrales", anal.get("cuentas_bimestrales", 0), NUM_FMT),
        ("Variación saldo negativo vs anterior", (variacion if variacion is not None else "n/d"), "0.00%"),
    ]
    for j, (k, v, fmt) in enumerate(indicadores, row + 1):
        ws.cell(row=j, column=1, value=k).border = THIN_BORDER
        if isinstance(v, str):
            cell = ws.cell(row=j, column=2, value=v)
        elif variacion is not None and k.startswith("Variación"):
            cell = ws.cell(row=j, column=2, value=(v if v >= 0 else v) / 100)
            cell.number_format = PORC_FMT
        else:
            cell = ws.cell(row=j, column=2, value=_fmtCurrency(v) if fmt == MONEDA_FMT else v)
            cell.number_format = fmt
        cell.border = THIN_BORDER
        cell.alignment = Alignment(horizontal="right")
    _style_data_rows(ws, row + 1, row + len(indicadores), 2)

    if analisis_ejecutivo:
        row = row + len(indicadores) + 2
        _add_section_title(ws, row, "RESUMEN EJECUTIVO", max_col)
        ws.merge_cells(start_row=row + 1, start_column=1, end_row=row + 6, end_column=max_col)
        cell = ws.cell(row=row + 1, column=1, value=analisis_ejecutivo)
        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        cell.border = THIN_BORDER

    ws.freeze_panes = "A4"
    _auto_width(ws, max_col, max_width=50)
    return ws


# FUNCIÓN PRINCIPAL DEL INFORME GENERAL
# Crea el libro completo con las 8 hojas y lo devuelve en memoria
def generar_excel_general(general_data, especiales_data, analisis_ejecutivo=None, novedades=None, variacion=None):
    wb = Workbook()
    _hoja_portada(wb, general_data, especiales_data)
    _hoja_resumen(wb, general_data)
    _hoja_consolidado(wb, general_data)
    _hoja_detalle_fact(wb, general_data)
    _hoja_detalle_rec(wb, general_data)
    # Las hojas de clientes especiales solo se agregan si el municipio trae esa información
    if especiales_data:
        _hoja_esp_dashboard(wb, especiales_data)
        _hoja_esp_detalle(wb, especiales_data, novedades)
        _hoja_analisis_especiales(wb, especiales_data, analisis_ejecutivo, variacion)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# Informe de clientes especiales: solo dos hojas (detalle y dashboard)
def generar_excel_especiales(especiales_data):
    wb = Workbook()
    ws = wb.active
    ws.title = "ESPECIALES"
    ws.sheet_properties.tabColor = "FFF8DC"

    max_col = 15
    headers = ["ID CUENTA", "NOMBRE", "GRUPO", "TARIFA MÍNIMA", "CONSUMO",
               "FACTURACIÓN", "RECAUDO", "VERIF. FACTURADO", "PERIODO",
               "CÁLCULO IAP", "SALDOS F-L", "% CEE", "VAL. RECAUDA.",
               "VAL. %", "VAL. MÍNIMA"]

    ws.merge_cells("A1:O1")
    ws.cell(row=1, column=1, value="CLIENTES ESPECIALES").font = TITLE_FONT
    ws.row_dimensions[1].height = 35

    row = 3
    for i, h in enumerate(headers, 1):
        ws.cell(row=row, column=i, value=h)
    _style_header_row(ws, row, max_col)

    filas = especiales_data["filas"]
    for j, e in enumerate(filas, row + 1):
        ws.cell(row=j, column=1, value=e["id"]).border = THIN_BORDER
        ws.cell(row=j, column=2, value=e["nombre"]).border = THIN_BORDER
        ws.cell(row=j, column=3, value=e["clase"]).border = THIN_BORDER

        for c, key, fmt in [(4, "tarifa_minima", MONEDA_FMT), (5, "consumo", MONEDA_FMT),
                             (6, "facturacion", MONEDA_FMT), (7, "recaudo", MONEDA_FMT)]:
            cell = ws.cell(row=j, column=c, value=_fmtCurrency(e[key]))
            cell.number_format = fmt
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")

        ws.cell(row=j, column=8, value=e["verificado"]).border = THIN_BORDER
        ws.cell(row=j, column=8).alignment = Alignment(horizontal="center")
        ws.cell(row=j, column=9, value=e["periodo"]).border = THIN_BORDER

        for c, key, fmt in [(10, "calc_iap", MONEDA_FMT), (11, "saldo_fl", MONEDA_FMT),
                             (12, "pct_cee", PORC_FMT), (13, "val_rec", MONEDA_FMT)]:
            cell = ws.cell(row=j, column=c, value=e[key])
            cell.number_format = fmt
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="right")

        ws.cell(row=j, column=14, value=e["val_tarifa_pct"]).border = THIN_BORDER
        ws.cell(row=j, column=14).alignment = Alignment(horizontal="center")
        ws.cell(row=j, column=15, value=e["val_tarifa_min"]).border = THIN_BORDER
        ws.cell(row=j, column=15).alignment = Alignment(horizontal="center")

    end_row = row + len(filas)
    _style_data_rows(ws, row + 1, end_row, max_col)

    # Dashboard sheet
    ws2 = wb.create_sheet("DASHBOARD")
    ws2.sheet_properties.tabColor = "FFF8DC"
    dash_headers = ["GRUPO", "CUENTAS", "FACTURACIÓN", "RECAUDO", "CONSUMO",
                    "SALDOS F-L", "SALDO NEGATIVO", "SALDO POSITIVO"]
    max_col2 = len(dash_headers)
    ws2.merge_cells("A1:H1")
    ws2.cell(row=1, column=1, value="CONSOLIDADO POR GRUPO").font = TITLE_FONT

    row2 = 3
    for i, h in enumerate(dash_headers, 1):
        ws2.cell(row=row2, column=i, value=h)
    _style_header_row(ws2, row2, max_col2)

    for j, g in enumerate(especiales_data["grupos"], row2 + 1):
        d = especiales_data["por_clase"][g]
        ws2.cell(row=j, column=1, value=g).border = THIN_BORDER
        ws2.cell(row=j, column=2, value=d["n"]).border = THIN_BORDER
        for c, key in [(3, "fact"), (4, "rec"), (5, "consumo"),
                       (6, "saldo_fl"), (7, "saldo_neg"), (8, "saldo_pos")]:
            cell = ws2.cell(row=j, column=c, value=_fmtCurrency(d[key]))
            cell.number_format = MONEDA_FMT
            cell.border = THIN_BORDER

    end_row2 = row2 + len(especiales_data["grupos"])
    tot = especiales_data["totales"]
    ws2.cell(row=end_row2 + 1, column=1, value="TOTAL").font = TOTAL_FONT
    ws2.cell(row=end_row2 + 1, column=1).fill = TOTAL_FILL
    ws2.cell(row=end_row2 + 1, column=1).border = THIN_BORDER
    for c, key in [(2, "cuentas"), (3, "fact"), (4, "rec"), (5, "consumo"),
                   (6, "total_saldo_fl"), (7, "saldo_neg"), (8, "saldo_pos")]:
        val = tot[key]
        cell = ws2.cell(row=end_row2 + 1, column=c, value=_fmtCurrency(val) if c > 2 else val)
        cell.number_format = MONEDA_FMT if c > 2 else NUM_FMT
        cell.font = TOTAL_FONT
        cell.fill = TOTAL_FILL
        cell.border = THIN_BORDER

    _style_data_rows(ws2, row2 + 1, end_row2, max_col2)
    _auto_width(ws2, max_col2, max_width=25)

    ws.freeze_panes = "A4"
    _auto_width(ws, max_col, max_width=30)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
