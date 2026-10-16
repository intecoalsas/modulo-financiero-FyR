

from io import BytesIO

from docx import Document
from docx.shared import Pt, RGBColor, Emu, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import nsdecls, qn
from docx.oxml import parse_xml, OxmlElement

# Fuente que se usa en todo el documento
ARIAL = "Arial Narrow"

# REGLA INTECOAL (solo Word): tablas y gráficas con los colores de la
# empresa (amarillo D9CF43, marrón 4E3629, grises); lo único negro son
# las letras y números: todo el texto va en FONT_DARK.
FONT_DARK = "171717"
FONT_WHITE = "FFFFFF"
FONT_RED = "A93226"
FONT_OK = "50C878"
FONT_WARN = "9C6500"
FONT_GRAY = "7F7F7F"

# Fondos de tablas con colores de la empresa: encabezado amarillo,
# cebra gris claro y totales en amarillo con texto negro
HDR = "D9CF43"
ZEBRA = "F2F2F2"
LBL = "F2EDC9"
GRID = "BFBFBF"
DARK = HDR
MID = HDR
LIGHT = LBL
LIGHT2 = ZEBRA

# Tamaños: 12 texto, 8 tablas amplias (>=6 columnas), 10 tablas angostas
SZ_TXT = 12
SZ_WIDE = 8
SZ_NARROW = 10
SZ_TITLE = 14

# Paleta INTECOAL para todas las gráficas generadas (matplotlib).
PAL_WORD = ["#D9CF43", "#4E3629", "#BFBA6B", "#BFBFBF", "#8C8C8C", "#E8E4C8"]
PAL_EXCEL = list(PAL_WORD)

# Relleno amarillo empresa para filas TOTAL (texto negro)
TOT = "D9CF43"

# Normativa por municipio, tal cual cada informe de referencia
import unicodedata as _ud


def _norm_mun(municipio):
    return _ud.normalize("NFKD", str(municipio or "")).encode("ascii", "ignore").decode().strip().lower()


ACUERDO_ESP = {
    "san pedro": ("Acuerdo Municipal No. 002 del 2022", None),
    "andalucia": ("Acuerdo Municipal No. 030 del 2024",
                  "Acuerdo Modificatorio No. 004 de 2025"),
    "calima el darien": ("Acuerdo Municipal No. 031 de 2022", None),
    "villavicencio": ("Acuerdo Municipal No. 515 de 2021", None),
}

MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# Pasa de texto ("left", "center"...) a la constante que entiende python-docx
_ALIGN_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


# Número sin decimales, con separador de miles en formato colombiano (1.234.567)
def _th(v):
    try:
        return "{:,.0f}".format(round(float(v))).replace(",", ".")
    except (TypeError, ValueError):
        return "0"


# Número en formato de dinero, con signo $ y negativo cuando haga falta
def _usd(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "$ 0"
    if f == 0:
        return "$ 0"
    s = _th(abs(f))
    return "$ " + s if f > 0 else "-$ " + s


# Número redondeado sin decimales (para contar cuentas, etc.)
def _n(v):
    try:
        return str(int(round(float(v))))
    except (TypeError, ValueError):
        return "0"


# Convierte el número del mes (7) en su nombre ("Julio")
def _mes_label(mes):
    try:
        return MESES[int(mes)]
    except (TypeError, ValueError, IndexError):
        return ""


# Le pone estilo a un texto dentro del documento (tamaño, negrita, color, fuente)
def _set_run(run, size=None, bold=False, color=FONT_DARK, font=ARIAL):
    if size is not None:
        run.font.size = Pt(size)
    run.bold = bold
    run.font.name = font
    run.font.color.rgb = RGBColor.from_string(color)
    if font != ARIAL:
        run.font.name = font


# Pinta una celda de la tabla (texto, color, tamaño, negrita, fondo)
def _fill(cell, color):
    shading = parse_xml('<w:shd {} w:fill="{}" w:val="clear"/>'.format(nsdecls("w"), color))
    cell._tc.get_or_add_tcPr().append(shading)


def _para(doc, align=None, size=None, bold=False, color=FONT_DARK, space_before=None):
    p = doc.add_paragraph()
    if align:
        p.alignment = align
    if space_before is not None:
        p.paragraph_format.space_before = Pt(space_before)
    if size is not None:
        for r in p.runs:
            _set_run(r, size=size, bold=bold, color=color)
    return p


def _cell(cell, text="", size=SZ_NARROW, bold=False, color=FONT_DARK, fill=None,
          align="left", font=ARIAL):
    p = cell.paragraphs[0]
    p.alignment = _ALIGN_MAP.get(align, WD_ALIGN_PARAGRAPH.LEFT)
    p.paragraph_format.space_after = Pt(0)
    if text is None:
        text = ""
    for i, seg in enumerate(str(text).split("\n")):
        if i > 0:
            br = p.add_run()
            _set_run(br, size=size, bold=bold, color=color, font=font)
            br.add_break()
        if seg:
            run = p.add_run(seg)
            _set_run(run, size=size, bold=bold, color=color, font=font)
    if fill:
        _fill(cell, fill)


def _set_grid(t, widths_twips):
    grid = t._tbl.tblGrid
    for el, w in zip(grid.findall(qn('w:gridCol')), widths_twips):
        el.set(qn('w:w'), str(int(w)))
    for row in t.rows:
        for i, w in enumerate(widths_twips):
            row.cells[i].width = Emu(int(w) * 635)


def _table(doc, rows, cols, widths=None):
    t = doc.add_table(rows=rows, cols=cols)
    if widths:
        _set_grid(t, widths)
    return t


# Le pone bordes finos y claros a la tabla
def _inside_borders(t, table_border="single", inner_h="single", inner_v="single"):
    tbl = t._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for tag, val in (("top", table_border), ("left", table_border),
                     ("bottom", table_border), ("insideH", inner_h), ("insideV", inner_v)):
        el = OxmlElement('w:%s' % tag)
        el.set(qn('w:val'), val)
        el.set(qn('w:sz'), '4')
        el.set(qn('w:color'), GRID)
        borders.append(el)
    tblPr.append(borders)


# Configura la hoja: orientación (vertical/horizontal), márgenes y la fuente base
def _config(doc, orientation):
    sec = doc.sections[0]
    if orientation == "landscape":
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width = Emu(10058400)
        sec.page_height = Emu(7772400)
    else:
        sec.orientation = WD_ORIENT.PORTRAIT
        sec.page_width = Emu(7772400)
        sec.page_height = Emu(10058400)
    sec.top_margin = Emu(720000)
    sec.bottom_margin = Emu(720000)
    sec.left_margin = Emu(720000)
    sec.right_margin = Emu(720000)
    style = doc.styles["Normal"]
    style.font.name = ARIAL
    style.font.size = Pt(SZ_TXT)
    style.font.color.rgb = RGBColor.from_string(FONT_DARK)


# Agrega el número de página al pie, centrado
def _footer_pagenum(doc):
    sec = doc.sections[0]
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run("P\u00e1gina ")
    _set_run(run, size=9, color=FONT_DARK)
    run = p.add_run()
    run._r.append(OxmlElement('w:fldChar'))
    run._r[-1].set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = 'PAGE'
    run._r.append(instr)
    run._r.append(OxmlElement('w:fldChar'))
    run._r[-1].set(qn('w:fldCharType'), 'end')
    _set_run(run, size=9, color=FONT_DARK)


# Título de sección numerado, en negro y sin líneas intermedias
def _heading(doc, num, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(("%s. %s" % (num, text)).upper() if num else text.upper())
    _set_run(run, size=SZ_TXT, bold=True, color=FONT_DARK)
    return p


# Una viñeta (punto) de lista
def _bullet(doc, text, size=SZ_TXT):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Pt(18)
    p.paragraph_format.space_after = Pt(3)
    r0 = p.add_run("\u2022  ")
    _set_run(r0, size=size, color=FONT_DARK)
    r1 = p.add_run(text)
    _set_run(r1, size=size)
    return p


# Eficacia: todo el texto va en negro (regla INTECOAL)
def _efic_color(ef):
    return FONT_DARK


# Orden fijo de los sectores como en los informes de referencia
# Agente de recaudo según la comercializadora
def _agente(comercializadora):
    if "emsa" in _norm_mun(comercializadora):
        return "Electrificadora del Meta S.A. (EMSA)"
    return "Celsia Colombia S.A. E.S.P."


# Convierte una fracción (0.35) en porcentaje ("35%")
def _pct(v):
    try:
        return "{:.0f}%".format(float(v) * 100)
    except (TypeError, ValueError):
        return "0%"


# Valor corto en millones para las etiquetas de las gráficas ($12.4M)
def _fmt_corto(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return ""
    a = abs(f)
    if a >= 1_000_000:
        s = "%.1fM" % (f / 1_000_000)
    elif a >= 1_000:
        s = "%sk" % _th(f / 1000)
    else:
        s = _th(f)
    return ("$" + s) if f >= 0 else ("-$" + s[1:])


def _fig_png(fig):
    import matplotlib.pyplot as plt
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# Quita el marco negro de la gráfica (ejes sin caja)
def _sin_marco(ax):
    for _s in ax.spines.values():
        _s.set_visible(False)


# Barras agrupadas Facturación vs Recaudo vs Diferencia por clase (como la página)
def _chart_consolidado(consolidado):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    filas = [c for c in (consolidado or []) if c[0] != "TOTAL"]
    if not filas:
        return None
    labs = [c[0] for c in filas]
    fv = [float(c[1] or 0) / 1e6 for c in filas]
    rv = [float(c[2] or 0) / 1e6 for c in filas]
    dv = [float(c[3] or 0) / 1e6 for c in filas]
    x = np.arange(len(labs))
    w = 0.24
    fig, ax = plt.subplots(figsize=(7, 3.6))
    _sin_marco(ax)
    b1 = ax.bar(x - w, fv, w, label="Facturación ($M)", color=PAL_EXCEL[0])
    b2 = ax.bar(x, rv, w, label="Recaudo ($M)", color=PAL_EXCEL[1])
    b3 = ax.bar(x + w, dv, w, label="Diferencia ($M)", color=PAL_EXCEL[2])
    ax.set_xticks(x)
    ax.set_xticklabels(labs, fontsize=9)
    ax.set_ylabel("Millones ($)", fontsize=9)
    ax.set_title("Facturación vs Recaudo por clasificación", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.tick_params(labelsize=8)
    for bars, vals in ((b1, fv), (b2, rv), (b3, dv)):
        for rect, v in zip(bars, vals):
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(),
                     _fmt_corto(v * 1e6), ha="center", va="bottom", fontsize=7)
    return _fig_png(fig)


# Barras Facturación vs Recaudo vs Diferencia por grupo (especiales)
def _chart_grupos(por_clase, grupos):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    grupos = [g for g in (grupos or []) if (por_clase or {}).get(g)]
    if not grupos:
        return None
    fv = [float(por_clase[g].get("fact", 0) or 0) / 1e6 for g in grupos]
    rv = [float(por_clase[g].get("rec", 0) or 0) / 1e6 for g in grupos]
    dv = [(float(por_clase[g].get("rec", 0) or 0) - float(por_clase[g].get("fact", 0) or 0)) / 1e6
          for g in grupos]
    x = np.arange(len(grupos))
    w = 0.24
    fig, ax = plt.subplots(figsize=(9, 3.8))
    _sin_marco(ax)
    b1 = ax.bar(x - w, fv, w, label="Facturación ($M)", color=PAL_EXCEL[0])
    b2 = ax.bar(x, rv, w, label="Recaudo ($M)", color=PAL_EXCEL[1])
    b3 = ax.bar(x + w, dv, w, label="Diferencia ($M)", color=PAL_EXCEL[2])
    ax.set_xticks(x)
    ax.set_xticklabels(grupos, fontsize=8, rotation=15)
    ax.set_ylabel("Millones ($)", fontsize=9)
    ax.set_title("Facturación, Recaudo y Diferencia por grupo", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.tick_params(labelsize=8)
    for bars, vals in ((b1, fv), (b2, rv), (b3, dv)):
        for rect, v in zip(bars, vals):
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(),
                     _fmt_corto(v * 1e6), ha="center", va="bottom", fontsize=7)
    return _fig_png(fig)


# Dona genérica por conteos (sin facturar por periodicidad, otras tarifas por grupo)
def _chart_dona(titulo, pares, total_label="cuentas"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pares = [(str(k), int(v)) for k, v in (pares or []) if int(v or 0) > 0]
    if not pares:
        return None
    labs = ["%s (%s)" % (k, _th(v)) for k, v in pares]
    vals = [v for _, v in pares]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.pie(vals, wedgeprops=dict(width=0.45), colors=PAL_EXCEL[:len(vals)],
           startangle=90)
    ax.legend(labs, loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8)
    ax.text(0, 0, _th(sum(vals)), ha="center", va="center", fontsize=14,
            fontweight="bold")
    ax.text(0, -0.18, total_label, ha="center", va="center", fontsize=9)
    ax.set_title(titulo, fontsize=11, fontweight="bold")
    return _fig_png(fig)


# Tabla de cartera acumulada como en el informe de referencia (San Pedro):
# ITEM, ID, nombre, 2019..año y total, con filas de favor/pagar
def _tabla_cartera(doc, cartera):
    clientes = cartera.get("clientes") or []
    if not clientes:
        return
    fav = cartera.get("total_favor") or {}
    pag = cartera.get("total_pagar") or {}
    anios = sorted({int(k) for d in ([c.get("saldos") or {} for c in clientes] + [fav, pag])
                    for k in d if str(k).isdigit()})
    if not anios:
        return
    headers = ["ITEM", "ID", "NOMBRE USUARIO ESPECIAL"] + \
        [("%s (Prescrito)" % a if a in (2019, 2020) else str(a)) for a in anios] + \
        ["VALOR TOTAL CARTERA"]
    ncol = len(headers)
    fills_h = ["D9CF43", "D9CF43", "D9CF43"] + \
        [("D9D9D9" if a in (2019, 2020) else "F7F5D9") for a in anios] + ["D9CF43"]
    primo = max(300, int(9200 / max(ncol - 3, 1)))
    widths = [350, 750, 2500] + [primo] * len(anios) + [1150]
    t = _table(doc, 1 + len(clientes), ncol, widths=widths)
    _inside_borders(t)
    for i, h in enumerate(headers):
        _cell(t.rows[0].cells[i], h, size=SZ_WIDE, bold=True, color=FONT_DARK,
              fill=fills_h[i], align="center")
    for ri, c in enumerate(clientes, start=1):
        saldos = c.get("saldos") or {}
        _cell(t.rows[ri].cells[0], _n(c.get("item") or ri), size=SZ_WIDE,
              align="center")
        _cell(t.rows[ri].cells[1], str(c.get("id") or ""), size=SZ_WIDE,
              fill="FCFBEF" if ri % 2 == 1 else "F2F2F2", align="right")
        _cell(t.rows[ri].cells[2], c.get("nombre") or "", size=SZ_WIDE)
        for ci, a in enumerate(anios, start=3):
            v = float(saldos.get(str(a)) or 0)
            _cell(t.rows[ri].cells[ci], _usd(v), size=SZ_WIDE, align="right",
                  color=FONT_DARK,
                  fill="D9D9D9" if a in (2019, 2020) else None)
        tc = float(c.get("total_cartera") or 0)
        _cell(t.rows[ri].cells[ncol - 1], _usd(tc), size=SZ_WIDE, align="right",
              bold=True, color=FONT_DARK)
    # Filas de totales favor/pagar por año (SUMIF por columna)
    for lab, tot, _fl in (("TOTAL SALDO A FAVOR CLIENTES ESPECIALES", fav, "F2EDC9"),
                           ("TOTAL SALDO POR PAGAR CLIENTES ESPECIALES", pag, "E7DCC3")):
        row = t.add_row()
        row.cells[0].merge(row.cells[2])
        _cell(row.cells[0], lab, size=SZ_WIDE, bold=True, fill=_fl)
        for ci, a in enumerate(anios, start=3):
            _cell(row.cells[ci], _usd(tot.get(str(a)) or 0), size=SZ_WIDE,
                  bold=True, fill=_fl, align="right")
        _cell(row.cells[ncol - 1], _usd(tot.get("total") or 0), size=SZ_WIDE,
              bold=True, fill=_fl, align="right")


# Dona de distribución de cuentas por clase (como la página)
def _chart_clases(clase_tabla):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    filas = [c for c in (clase_tabla or []) if c[0] != "TOTAL" and float(c[1] or 0) > 0]
    if not filas:
        return None
    labs = ["%s (%s)" % (c[0], _th(c[1])) for c in filas]
    vals = [float(c[1]) for c in filas]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.pie(vals, wedgeprops=dict(width=0.45), colors=PAL_EXCEL[:len(vals)],
           startangle=90)
    ax.legend(labs, loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8)
    ax.text(0, 0, _th(sum(vals)), ha="center", va="center", fontsize=14,
            fontweight="bold")
    ax.text(0, -0.18, "cuentas", ha="center", va="center", fontsize=9)
    ax.set_title("Distribución de cuentas por clase", fontsize=11, fontweight="bold")
    return _fig_png(fig)


# Barras de cuentas por sector urbano/rural (como la página)
def _chart_sector(sector_tabla):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    filas = [s for s in (sector_tabla or []) if s[0] != "TOTAL"]
    if not filas:
        return None
    labs = [s[0] for s in filas]
    vals = [float(s[1] or 0) for s in filas]
    imps = [float(s[2] or 0) for s in filas]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    _sin_marco(ax)
    bars = ax.bar(labs, vals, color=PAL_EXCEL[:len(labs)])
    ax.set_ylabel("Cuentas", fontsize=9)
    ax.set_title("Cuentas por sector", fontsize=11, fontweight="bold")
    ax.tick_params(labelsize=9)
    for rect, v, imp in zip(bars, vals, imps):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(),
                 "%s\n%s" % (_th(v), _fmt_corto(imp)),
                 ha="center", va="bottom", fontsize=8)
    return _fig_png(fig)


# Estado resumido en 1-2 palabras para que quepa en la tabla (para el Word)
def _estado_short(est):
    if not est:
        return "FACTURADO"
    if "FACTURADO" in est:
        return "FACTURADO"
    if "NO CORRESPONDE" in est:
        return "NO CORRESPONDE\nBIMESTRAL"
    if "SIN FACTURACION" in est or "SIN FACTURAR" in est:
        return "SIN FACTURAR\nREVISAR"
    return est


# Filas de las tablas estilo Informe FyR (hoja de Villavicencio/EMSA).
# La agregación vive en core/fyr.py y se reutiliza en la página.
from core.fyr import FYR_ORDEN, fyr_agregar


def _fyr_orden():
    return list(FYR_ORDEN)


def _fyr_agregar(facturacion, recaudo):
    return fyr_agregar(facturacion, recaudo)


# Escribe una tabla FyR de 4 columnas (Clasificación, Urbana, Rural, Total)
def _fyr_tabla_zona(doc, titulo, filas):
    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=8)
    _set_run(p.add_run(titulo), size=SZ_TXT, bold=True, color=FONT_DARK)
    t = _table(doc, 1 + len(filas), 4, widths=[3200, 1400, 1400, 1400])
    _inside_borders(t)
    for i, h in enumerate(["Clasificación", "Urbana", "Rural", "Total"]):
        _cell(t.rows[0].cells[i], h, size=SZ_WIDE, bold=True, color=FONT_DARK,
              fill=DARK, align="center")
    for ri, (lab, vals, fmt, negras, relleno) in enumerate(filas, start=1):
        if relleno == "TOTAL":
            fill, tx, nb = TOT, FONT_DARK, True
        elif relleno == "SUB":
            fill, tx, nb = LIGHT, FONT_DARK, True
        else:
            fill, tx, nb = (LIGHT2 if ri % 2 == 0 else "FFFFFF"), FONT_DARK, False
        _cell(t.rows[ri].cells[0], lab, size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="left")
        for ci, v in enumerate(vals, start=1):
            color = tx
            if negras == "rojo_verde" and ci == 3:
                color = FONT_DARK
            _cell(t.rows[ri].cells[ci], fmt(v), size=SZ_WIDE, bold=nb, color=color,
                  fill=fill, align="center" if fmt == _th else "right")


# Genera el documento Word del informe general
def generar_word_general(general_data, analisis_ejecutivo=None, municipio="", anio=None,
                         mes=None, comercializadora=""):
    doc = Document()
    _config(doc, "portrait")
    _footer_pagenum(doc)

    mes_n = _mes_label(mes)
    anio_t = str(anio) if anio is not None else ""
    mun = (municipio or "Andaluc\u00eda").title()
    agente = _agente(comercializadora)

    # Título como en los informes de referencia (sin periodo)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(0)
    r1 = p.add_run("AN\u00c1LISIS FACTURACI\u00d3N Y RECAUDO IMPUESTO DE ALUMBRADO P\u00daBLICO")
    _set_run(r1, size=SZ_TITLE, bold=True, color=FONT_DARK)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    r2 = p.add_run("Agente de Recaudo: %s" % agente)
    _set_run(r2, size=SZ_TXT, bold=True, color=FONT_DARK)

    _orden = _fyr_orden()
    _acc = _fyr_agregar(general_data.get("facturacion"), general_data.get("recaudo"))
    _tot = _acc["TOTAL"]
    _n_tot = int(_tot["n"][2])
    _kwh_tot = _tot["kwh"][2]
    _base_tot = _tot["base"][2]
    _fact_tot = _tot["fact"][2]
    _rec_tot = _tot["rec"][2]
    clase_dep = general_data.get("clase_tabla") or []
    consolidado = general_data.get("consolidado") or []

    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=4)
    _set_run(p.add_run("RESUMEN EJECUTIVO"), size=SZ_TXT, bold=True, color=FONT_DARK)
    _res = [
        ("Total de cuentas / usuarios", _th(_n_tot)),
        ("Consumo de energía facturado (kWh)", _th(_kwh_tot)),
        ("Base gravable – valor consumo de energía ($)", _usd(_base_tot)),
        ("Impuesto de alumbrado público facturado ($)", _usd(_fact_tot)),
        ("Impuesto de alumbrado público recaudado ($)", _usd(_rec_tot)),
        ("% Recaudo / Facturación", _pct(_rec_tot / _fact_tot) if _fact_tot else "0%"),
        ("% Facturación / Base gravable (tarifa efectiva)",
         _pct(_fact_tot / _base_tot) if _base_tot else "0%"),
    ]
    _rt = _table(doc, len(_res), 2, widths=[6000, 2400])
    _inside_borders(_rt)
    for _ri, (_lab, _val) in enumerate(_res):
        _cell(_rt.rows[_ri].cells[0], _lab, size=SZ_NARROW, bold=True, fill=LIGHT)
        _cell(_rt.rows[_ri].cells[1], _val, size=SZ_NARROW, bold=True, align="right",
              fill=LIGHT if _ri % 2 == 0 else "FFFFFF")

    def _filas_zona(met, fmt, negras=None):
        _fl = []
        for _i in range(1, 7):
            _k = "Residencial – Estrato %d" % _i
            _fl.append((_k, _acc[_k][met], fmt, negras, ""))
        _fl.append(("Subtotal Residencial", _acc["Subtotal Residencial"][met], fmt, negras, "SUB"))
        for _k in ("Comercial", "Oficial", "Industrial", "Otros"):
            _fl.append((_k, _acc[_k][met], fmt, negras, ""))
        _fl.append(("TOTAL", _acc["TOTAL"][met], fmt, negras, "TOTAL"))
        return _fl

    _fyr_tabla_zona(doc, "1. CANTIDAD DE CUENTAS / USUARIOS POR CLASIFICACIÓN Y ZONA",
                    _filas_zona("n", _th))
    _fyr_tabla_zona(doc, "2. VALORES FACTURADOS ($) POR CLASIFICACIÓN Y ZONA",
                    _filas_zona("fact", _usd))
    _fyr_tabla_zona(doc, "3. VALORES RECAUDADOS ($) POR CLASIFICACIÓN Y ZONA",
                    _filas_zona("rec", _usd))

    def _fila_fyr(ri, lab, col0, col1, col2, col3, rel):
        if rel == "TOTAL":
            _fl, _tx, _nb = MID, FONT_DARK, True
        elif rel == "SUB":
            _fl, _tx, _nb = LIGHT, FONT_DARK, True
        else:
            _fl, _tx, _nb = (LIGHT2 if ri % 2 == 0 else "FFFFFF"), FONT_DARK, False
        return _fl, _tx, _nb

    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=8)
    _set_run(p.add_run("4. CONSUMO DE ENERGÍA: BASE GRAVABLE vs FACTURACIÓN"), size=SZ_TXT, bold=True, color=FONT_DARK)
    t = _table(doc, 1 + len(_orden), 5, widths=[2600, 1500, 1500, 1100, 1300])
    _inside_borders(t)
    for i, h in enumerate(["Clasificación", "Base gravable – consumo energía ($)",
                           "Impuesto facturado ($)", "Impuesto / Base (%)", "Consumo (kWh)"]):
        _cell(t.rows[0].cells[i], h, size=SZ_WIDE, bold=True, color=FONT_DARK, fill=DARK, align="center")
    for ri, k in enumerate(_orden, start=1):
        rel = "TOTAL" if k == "TOTAL" else ("SUB" if k == "Subtotal Residencial" else "")
        fill, tx, nb = _fila_fyr(ri, k, 0, 0, 0, 0, rel)
        _bt, _ft, _kt = _acc[k]["base"][2], _acc[k]["fact"][2], _acc[k]["kwh"][2]
        _cell(t.rows[ri].cells[0], k, size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="left")
        _cell(t.rows[ri].cells[1], _usd(_bt), size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="right")
        _cell(t.rows[ri].cells[2], _usd(_ft), size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="right")
        _cell(t.rows[ri].cells[3], _pct(_ft / _bt) if _bt else "0%", size=SZ_WIDE, bold=nb,
              color=tx, fill=fill, align="center")
        _cell(t.rows[ri].cells[4], _th(_kt), size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="right")

    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=8)
    _set_run(p.add_run("5. RECAUDO vs FACTURACIÓN (por clasificación)"), size=SZ_TXT, bold=True, color=FONT_DARK)
    t = _table(doc, 1 + len(_orden), 5, widths=[2600, 1500, 1500, 1600, 1100])
    _inside_borders(t)
    for i, h in enumerate(["Clasificación", "Impuesto facturado ($)", "Impuesto recaudado ($)",
                           "Diferencia recaudo-factura ($)", "% Recaudo"]):
        _cell(t.rows[0].cells[i], h, size=SZ_WIDE, bold=True, color=FONT_DARK, fill=DARK, align="center")
    for ri, k in enumerate(_orden, start=1):
        rel = "TOTAL" if k == "TOTAL" else ("SUB" if k == "Subtotal Residencial" else "")
        fill, tx, nb = _fila_fyr(ri, k, 0, 0, 0, 0, rel)
        _ft, _rt = _acc[k]["fact"][2], _acc[k]["rec"][2]
        _df = _rt - _ft
        _cell(t.rows[ri].cells[0], k, size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="left")
        _cell(t.rows[ri].cells[1], _usd(_ft), size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="right")
        _cell(t.rows[ri].cells[2], _usd(_rt), size=SZ_WIDE, bold=nb, color=tx, fill=fill, align="right")
        _cell(t.rows[ri].cells[3], _usd(_df), size=SZ_WIDE, bold=True,
              color=FONT_DARK,
              fill=fill, align="right")
        _ef = _rt / _ft if _ft else 0
        _cell(t.rows[ri].cells[4], _pct(_ef), size=SZ_WIDE, bold=nb,
              color=FONT_DARK, fill=fill, align="center")

    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=8)
    _set_run(p.add_run("Notas:"), size=SZ_TXT, bold=True, color=FONT_DARK)
    _bullet(doc, "Fuente: archivos de facturación y recaudo del periodo %s %s (%s cuentas procesadas)."
            % (mes_n.lower(), anio_t, _th(_n_tot)))
    _bullet(doc, "Base gravable = valor del consumo de energía de cada cuenta.")
    _bullet(doc, "\"Otros\" agrupa las cuentas que no clasifican como Residencial, Comercial, "
            "Oficial o Industrial.")
    if _rec_tot > _fact_tot:
        _bullet(doc, "El recaudo total (%s) supera la facturación (%s) por pagos de periodos "
                "anteriores u otros conceptos." % (_usd(_rec_tot), _usd(_fact_tot)))

    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=8)
    _set_run(p.add_run("GR\u00c1FICAS DEL PERIODO"), size=SZ_TXT, bold=True, color=FONT_DARK)

    # Las mismas gráficas del informe en página, a color
    consolidado = general_data.get("consolidado") or []
    try:
        graficas = [_chart_consolidado(consolidado),
                    _chart_clases(clase_dep),
                    _chart_sector(general_data.get("sector_tabla") or [])]
        for _buf in graficas:
            if not _buf:
                continue
            _pg = doc.add_paragraph()
            _pg.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _pg.paragraph_format.space_before = Pt(4)
            _pg.paragraph_format.space_after = Pt(4)
            _pg.add_run().add_picture(_buf, width=Inches(6.0))
    except Exception:
        pass

    # Firma al final del documento
    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=12)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_run(p.add_run("Elabor\u00f3:  Interventor\u00eda de Alumbrado P\u00fablico"), size=SZ_TXT, bold=True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_run(p.add_run("%s %s" % (mes_n, anio_t)), size=SZ_TXT, color=FONT_DARK)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# Construye las conclusiones del informe general como lista de textos
# Genera el documento Word del informe de clientes especiales
def generar_word_especiales(especiales_data, municipio="", anio=None, mes=None,
                            comercializadora="", cartera_data=None, acumulado=None):
    doc = Document()
    # Este informe va en hoja horizontal porque la tabla de clientes es muy ancha
    _config(doc, "landscape")
    _footer_pagenum(doc)

    mes_n = _mes_label(mes)
    anio_t = str(anio) if anio is not None else ""
    mun = (municipio or "Andaluc\u00eda").title()
    agente = _agente(comercializadora)
    acuerdo_1, acuerdo_2 = ACUERDO_ESP.get(_norm_mun(municipio),
                                          ("Acuerdo Municipal", None))

    _heading(doc, 1, "Objetivo y alcance")
    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, size=SZ_TXT)
    _set_run(p.add_run(
        "Verificar la correcta aplicaci\u00f3n de las tarifas especiales del impuesto de alumbrado "
        "p\u00fablico a los contribuyentes que, en su raz\u00f3n social, tienen inscrita alguna de las "
        "actividades econ\u00f3micas especificadas en el "), size=SZ_TXT)
    _set_run(p.add_run(acuerdo_1), size=SZ_TXT, bold=True)
    if acuerdo_2:
        _set_run(p.add_run(" y "), size=SZ_TXT)
        _set_run(p.add_run(acuerdo_2), size=SZ_TXT, bold=True)
    _set_run(p.add_run(
        ". Para cada cuenta se compara la tarifa m\u00ednima especial y el porcentaje aplicado al consumo "
        "con los valores efectivamente facturados y recaudados por el agente de recaudo, calculando el "
        "impuesto liquidado (L) y el saldo resultante frente a la facturaci\u00f3n."), size=SZ_TXT)

    _heading(doc, 2, "Relaci\u00f3n de clientes especiales")

    filas = sorted(especiales_data.get("filas") or [],
                   key=lambda e: (e.get("clase") or "", str(e.get("nombre") or "")))
    tot = especiales_data.get("totales") or {}
    iap_total = sum(float(e.get("calc_iap") or 0.0) for e in filas)

    headers = ["N\u00b0", "ID_CUENTA", "NOMBRE_USUARIO", "CLASIFICACI\u00d3N", "PERIODICIDAD",
               "TARIFA MIN ($)", "CONSUMO ($)", "% CEE", "FACTURACI\u00d3N ($)", "RECAUDO ($)",
               "IAP (L) ($)", "SALDO (F-L) ($)", "ESTADO"]
    nrows = 1 + len(filas) + 3
    t = _table(doc, nrows, 13,
               widths=[350, 800, 2700, 1000, 900, 1050, 1000, 600, 900, 900, 900, 906, 1000])
    _inside_borders(t)
    for i, h in enumerate(headers):
        _cell(t.rows[0].cells[i], h, size=8, bold=True, color=FONT_DARK, fill=DARK, align="center")

    aligns = ["center", "right", "left", "center", "center", "right", "right", "center",
              "right", "right", "right", "right", "center"]
    for ri, e in enumerate(filas, start=1):
        saldo = float(e.get("saldo_fl") or 0.0)
        vals = [
            _n(ri),
            str(e.get("id") or ""),
            e.get("nombre") or "",
            str(e.get("clase") or "").title(),
            str(e.get("periodo") or ""),
            _usd(e.get("tarifa_minima") or 0),
            _usd(e.get("consumo") or 0),
            _pct(e.get("pct_cee") or 0),
            _usd(e.get("facturacion") or 0),
            _usd(e.get("recaudo") or 0),
            _usd(e.get("calc_iap") or 0),
            _usd(saldo),
            _estado_short(e.get("estado_fact")),
        ]
        fill = LIGHT2 if ri % 2 == 0 else "FFFFFF"
        for ci, v in enumerate(vals):
            color = FONT_DARK
            if ci == 11:
                color = FONT_DARK
            elif ci == 12 and "SIN FACTURAR" in str(e.get("estado_fact")):
                color = FONT_DARK
            _cell(t.rows[ri].cells[ci], v, size=8, color=color, fill=fill, align=aligns[ci])

    ri = 1 + len(filas)
    saldo_total = float(tot.get("total_saldo_fl") or 0.0)
    vals = ["", "TOTAL GENERAL", "", "", "", _usd(tot.get("tarifa") or 0),
            _usd(tot.get("consumo") or 0), "", _usd(tot.get("fact") or 0),
            _usd(tot.get("rec") or 0), _usd(iap_total), _usd(saldo_total), ""]
    for ci, v in enumerate(vals):
        _cell(t.rows[ri].cells[ci], v, size=8, bold=True, color=FONT_DARK, fill=TOT,
              align="center" if ci in (1, 3, 4, 7, 12) else "right")

    ri += 1
    t.rows[ri].cells[0].merge(t.rows[ri].cells[10])
    _cell(t.rows[ri].cells[0], "SALDOS POSITIVOS (recuperar)", size=8, bold=True,
          color=FONT_DARK, fill=LIGHT, align="left")
    _cell(t.rows[ri].cells[11], _usd(tot.get("saldo_pos") or 0), size=8, bold=True,
          color=FONT_DARK, fill=LIGHT, align="right")
    _cell(t.rows[ri].cells[12], "", size=8, fill=LIGHT)

    ri += 1
    t.rows[ri].cells[0].merge(t.rows[ri].cells[10])
    _cell(t.rows[ri].cells[0], "SALDOS NEGATIVOS (pendiente de liquidar)", size=8, bold=True,
          color=FONT_DARK, fill=LIGHT, align="left")
    _cell(t.rows[ri].cells[11], _usd(tot.get("saldo_neg") or 0), size=8, bold=True,
          color=FONT_DARK, fill=LIGHT, align="right")
    _cell(t.rows[ri].cells[12], "", size=8, fill=LIGHT)

    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=8)
    _set_run(p.add_run("GLOSARIO DE COLUMNAS"), size=SZ_TXT, bold=True, color=FONT_DARK)
    glos = [
        ("FACTURACI\u00d3N:", "Valores tomados del archivo informe de Facturaci\u00f3n."),
        ("RECAUDO (R):", "Valores tomados del archivo informe de Recaudo."),
        ("CONSUMO ENERG\u00cdA:", "Valores tomados del archivo informe de Facturaci\u00f3n."),
        ("CALCULO IAP (L):", "C\u00e1lculo del impuesto aplicando la tarifa especial al consumo."),
        ("SALDOS (F-L):", "Comparaci\u00f3n entre lo facturado y el impuesto liquidado."),
        ("SALDOS (R-L):", "Comparaci\u00f3n entre lo recaudado y el impuesto liquidado."),
    ]
    gt = _table(doc, len(glos), 2, widths=[2200, 7600])
    _inside_borders(gt)
    for gi, (lab, val) in enumerate(glos):
        _cell(gt.rows[gi].cells[0], lab, size=SZ_NARROW, bold=True, fill=LIGHT)
        _cell(gt.rows[gi].cells[1], val, size=SZ_NARROW,
              fill=LIGHT if gi % 2 == 0 else "FFFFFF")

    _heading(doc, 3, "Consolidado por clasificaci\u00f3n")
    por_clase = especiales_data.get("por_clase") or {}
    iap_clase = {}
    for e in filas:
        iap_clase[e.get("clase")] = iap_clase.get(e.get("clase"), 0.0) + float(e.get("calc_iap") or 0.0)
    clases = especiales_data.get("grupos") or sorted(por_clase.keys())
    if not clases and por_clase:
        clases = sorted(por_clase.keys())

    t = _table(doc, 1 + len(clases) + (1 if por_clase else 0), 7,
               widths=[2000, 800, 1900, 1900, 1900, 1900, 1900])
    _inside_borders(t)
    for i, h in enumerate(["CLASIFICACI\u00d3N", "CUENTAS", "CONSUMO ($)", "FACTURACI\u00d3N ($)",
                           "RECAUDO ($)", "IAP (L) ($)", "SALDO (F-L) ($)"]):
        _cell(t.rows[0].cells[i], h, size=SZ_WIDE, bold=True, color=FONT_DARK, fill=DARK, align="center")
    for ri, cl in enumerate(clases, start=1):
        data = por_clase.get(cl, {})
        _cell(t.rows[ri].cells[0], str(cl).title(), size=SZ_WIDE, fill=LIGHT2)
        _cell(t.rows[ri].cells[1], _n(data.get("n", 0)), size=SZ_WIDE, fill=LIGHT2, align="center")
        _cell(t.rows[ri].cells[2], _usd(data.get("consumo", 0)), size=SZ_WIDE, fill=LIGHT2, align="right")
        _cell(t.rows[ri].cells[3], _usd(data.get("fact", 0)), size=SZ_WIDE, fill=LIGHT2, align="right")
        _cell(t.rows[ri].cells[4], _usd(data.get("rec", 0)), size=SZ_WIDE, fill=LIGHT2, align="right")
        _cell(t.rows[ri].cells[5], _usd(iap_clase.get(cl, 0)), size=SZ_WIDE, fill=LIGHT2, align="right")
        sal = float(data.get("saldo_fl", 0) or 0)
        _cell(t.rows[ri].cells[6], _usd(sal), size=SZ_WIDE, fill=LIGHT2, align="right",
              color=FONT_DARK)
    if por_clase:
        ri = 1 + len(clases)
        tf = sum(float(data.get("fact", 0) or 0) for data in por_clase.values())
        tr = sum(float(data.get("rec", 0) or 0) for data in por_clase.values())
        tc = sum(float(data.get("consumo", 0) or 0) for data in por_clase.values())
        ts = sum(float(data.get("saldo_fl", 0) or 0) for data in por_clase.values())
        _cell(t.rows[ri].cells[0], "TOTAL", size=SZ_WIDE, bold=True, color=FONT_DARK, fill=TOT)
        _cell(t.rows[ri].cells[1], _n(len(filas)), size=SZ_WIDE, bold=True, color=FONT_DARK, fill=TOT, align="center")
        _cell(t.rows[ri].cells[2], _usd(tc), size=SZ_WIDE, bold=True, color=FONT_DARK, fill=TOT, align="right")
        _cell(t.rows[ri].cells[3], _usd(tf), size=SZ_WIDE, bold=True, color=FONT_DARK, fill=TOT, align="right")
        _cell(t.rows[ri].cells[4], _usd(tr), size=SZ_WIDE, bold=True, color=FONT_DARK, fill=TOT, align="right")
        _cell(t.rows[ri].cells[5], _usd(iap_total), size=SZ_WIDE, bold=True, color=FONT_DARK, fill=TOT, align="right")
        _cell(t.rows[ri].cells[6], _usd(ts), size=SZ_WIDE, bold=True, color=FONT_DARK, fill=TOT, align="right")

    _sec = 4
    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=8)
    _set_run(p.add_run("GR\u00c1FICAS"), size=SZ_TXT, bold=True, color=FONT_DARK)
    # Las mismas gráficas de la página, con la paleta de los informes
    try:
        _por_per = {}
        for _e in filas:
            if not float(_e.get("facturacion") or 0):
                _k = _e.get("periodo") or "Sin dato"
                _por_per[_k] = _por_per.get(_k, 0) + 1
        _por_cl = {}
        for _e in filas:
            if _e.get("val_tarifa_min") == "Otra Tarifa":
                _k = _e.get("clase") or "Sin grupo"
                _por_cl[_k] = _por_cl.get(_k, 0) + 1
        _gs = [_chart_grupos(por_clase, clases),
               _chart_dona("Cuentas sin facturaci\u00f3n por periodicidad",
                           sorted(_por_per.items())),
               _chart_dona("Cuentas con tarifa diferente por grupo",
                           sorted(_por_cl.items()))]
        for _buf, _w in zip(_gs, (9.0, 5.0, 5.0)):
            if not _buf:
                continue
            _pg = doc.add_paragraph()
            _pg.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _pg.paragraph_format.space_before = Pt(4)
            _pg.paragraph_format.space_after = Pt(4)
            _pg.add_run().add_picture(_buf, width=Inches(_w))
    except Exception:
        pass

    # Cartera acumulada como en el informe de referencia (San Pedro)
    if cartera_data and cartera_data.get("clientes"):
        _heading(doc, _sec, "Cartera acumulada cuentas usuarios especiales")
        _tabla_cartera(doc, cartera_data)
        _sec += 1

    _heading(doc, _sec, "Resumen de hallazgos")
    _sec += 1
    analisis = especiales_data.get("analisis") or {}
    iap_uf = float(analisis.get("iap_dejado_facturar") or 0.0)
    iap_np = float(analisis.get("iap_no_percibido_municipio") or 0.0)
    hallazgos = [
        ("Cuentas especiales analizadas", _n(tot.get("cuentas") or len(filas))),
        ("Cuentas sin facturar en el periodo", _n(analisis.get("cuentas_sin_facturar", 0))),
        ("Cuentas con periodicidad bimestral", _n(analisis.get("cuentas_bimestrales", 0))),
        ("Cuentas facturadas con tarifa diferente a la especial", _n(analisis.get("cuentas_otras_tarifas", 0))),
        ("IAP dejado de facturar", _usd(iap_uf)),
        ("IAP no percibido por el municipio", _usd(iap_np)),
        ("Eficacia de recaudo del periodo", _pct(tot.get("eficacia") or 0)),
        ("Saldo total frente a la liquidaci\u00f3n (F-L)", _usd(tot.get("total_saldo_fl") or 0)),
    ]
    t = _table(doc, len(hallazgos), 2, widths=[6000, 1300])
    _inside_borders(t)
    for ri, (lab, val) in enumerate(hallazgos):
        _cell(t.rows[ri].cells[0], lab, size=SZ_NARROW, fill=LIGHT2)
        _cell(t.rows[ri].cells[1], val, size=SZ_NARROW, fill=LIGHT2, align="right", bold=True)

    _heading(doc, _sec, "Conclusiones y recomendaciones")
    # Párrafo acumulado enero-mes como en las referencias
    _meses_ac = sorted((int(m) for m in (acumulado or {})
                        if str(m).isdigit() and 1 <= int(m) <= int(mes or 12)),
                       reverse=False) if acumulado and mes else []
    if _meses_ac:
        _f_ac = sum(float((acumulado.get(str(m)) or {}).get("facturacion") or 0) for m in _meses_ac)
        _r_ac = sum(float((acumulado.get(str(m)) or {}).get("recaudo") or 0) for m in _meses_ac)
        _d_ac = _f_ac - _r_ac
        p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, size=SZ_TXT)
        _set_run(p.add_run(
            "Durante el periodo de enero a %s de %s, %s, en calidad de agente de recaudo del "
            "Impuesto de Alumbrado Público, registra una facturación acumulada de %s y un recaudo "
            "acumulado de %s. La diferencia acumulada entre lo facturado y lo recaudado asciende "
            "a %s.%s" % (
                _mes_label(mes).lower(), anio_t, agente, _usd(_f_ac), _usd(_r_ac), _usd(_d_ac),
                " El recaudo representa aproximadamente el %d %% del valor facturado acumulado."
                % round(100.0 * _r_ac / _f_ac) if _f_ac else "")), size=SZ_TXT)
        # Tabla por periodo + promedio como en las referencias
        _ta = _table(doc, 2 + len(_meses_ac), 4, widths=[2600, 2200, 2200, 2200])
        _inside_borders(_ta)
        for _i, _h in enumerate(["PERIODO", "CONSUMO ENERGÍA", "FACTURACIÓN", "RECAUDO"]):
            _cell(_ta.rows[0].cells[_i], _h, size=SZ_NARROW, bold=True, color=FONT_DARK,
                  fill=DARK, align="center")
        for _ri, _m in enumerate(_meses_ac, start=1):
            _dm = acumulado.get(str(_m)) or {}
            _cell(_ta.rows[_ri].cells[0], "%s" % MESES[int(_m)], size=SZ_NARROW, align="left")
            _cell(_ta.rows[_ri].cells[1], _usd(_dm.get("consumo") or 0), size=SZ_NARROW, align="right")
            _cell(_ta.rows[_ri].cells[2], _usd(_dm.get("facturacion") or 0), size=SZ_NARROW, align="right")
            _cell(_ta.rows[_ri].cells[3], _usd(_dm.get("recaudo") or 0), size=SZ_NARROW, align="right")
        _cell(_ta.rows[1 + len(_meses_ac)].cells[0], "PROMEDIO", size=SZ_NARROW, bold=True,
              color=FONT_DARK, fill=TOT, align="left")
        for _ci, _k in enumerate(("consumo", "facturacion", "recaudo"), start=1):
            _tot = sum(float((acumulado.get(str(_m)) or {}).get(_k) or 0) for _m in _meses_ac)
            _cell(_ta.rows[1 + len(_meses_ac)].cells[_ci],
                  _usd(_tot / len(_meses_ac)), size=SZ_NARROW, bold=True,
                  color=FONT_DARK, fill=TOT, align="right")
    for txt in _conclusiones_especiales(analisis, tot, iap_uf, iap_np, mun, mes_n, anio_t):
        p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, size=SZ_TXT)
        _set_run(p.add_run(txt), size=SZ_TXT)

    p = _para(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=12)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_run(p.add_run("Elabor\u00f3:  Interventor\u00eda de Alumbrado P\u00fablico"), size=SZ_TXT, bold=True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_run(p.add_run("%s %s" % (mes_n, anio_t)), size=SZ_TXT, color=FONT_DARK)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# Recomendaciones breves del informe de clientes especiales
def _conclusiones_especiales(analisis, tot, iap_uf, iap_np, mun, mes_n, anio_t):
    txt = []
    n_sf = int(analisis.get("cuentas_sin_facturar", 0) or 0)
    n_ot = int(analisis.get("cuentas_otras_tarifas", 0) or 0)
    if n_sf:
        txt.append("Se recomienda emitir las comunicaciones de seguimiento a los contribuyentes "
                   "con saldos pendientes (%s cuentas sin facturación en el periodo) y mantener "
                   "el control periódico sobre la aplicación de las tarifas especiales del "
                   "impuesto de alumbrado público en el municipio de %s." % (_n(n_sf), mun))
    if n_ot:
        txt.append("Para las %s cuentas en las que la tarifa aplicada difiere de la tarifa "
                   "especial, se recomienda verificar la clasificación registrada del usuario y, "
                   "de ser procedente, solicitar el ajuste y el cobro retroactivo de la "
                   "diferencia." % _n(n_ot))
    if iap_np:
        txt.append("Se recomienda requerir al agente de recaudo la facturación, cobro y traslado "
                   "de los %s no percibidos por el municipio." % _usd(iap_np))
    if not txt:
        txt.append("El periodo no presenta novedades relevantes; se recomienda mantener el "
                   "control periódico sobre la aplicación de las tarifas especiales en el "
                   "municipio de %s." % mun)
    return txt
