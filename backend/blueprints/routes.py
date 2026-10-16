
import os
from datetime import datetime as _dt

import pandas as pd
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_from_directory, send_file, jsonify)

# Se importan las funciones de los demás archivos del proyecto
from core.context import app, db, limiter
from core.utils import MESES, json_safe, leer_excel
from core.columnas import (ALIASES_DEFAULT, ETIQUETAS_CLAVE, EJEMPLOS_CLAVE, FACT_CLAVES, REC_CLAVES,
                           resolver_columnas, _guardar_alias_columna, _resolver_una)
from core.core import (build_general, build_especiales,
                       detectar_metadatos, save_report_to_db,
                       texto_ejecutivo, variacion_saldo_neg,
                       upsert_analisis_general, get_analisis_general_folders,
                       crear_carpeta_anio, eliminar_carpeta_anio,
                       get_tarifas, tarifas_anios, guardar_tarifas,
                       crear_anio_tarifas, eliminar_anio_tarifas,
                       get_descripcion, get_info_especiales,
                       get_cartera, carteras_anios, save_cartera,
                       get_or_create_municipio, get_or_create_comerc,
                       cargar_cartera_desde_referencia, actualizar_cartera_mes,
                       ensure_cartera_anio,
                       exportar_general, exportar_especiales)
from services.pendientes import get_pendiente, set_pendiente, del_pendiente
from services.report_service import get_municipios, get_comercializadoras, get_all_reports

from models import Municipio, Comercializadora, Report

# "Blueprint" = forma de organizar las rutas. Aquí viven todas las páginas de la web
bp = Blueprint('main', __name__)

# Carpetas donde están los archivos subidos y los informes generados
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
ORIG_DIR = os.path.join(UPLOAD_DIR, "originales")
EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")

# Aquí se guarda en memoria lo último que se cargó (para mostrarlo en las pestañas)
DATA = {"general": None, "especiales": None, "mes": None}
CARGADO = False

# Extensiones permitidas y tamaño máximo (MB) para los archivos subidos
EXT_PERMITIDAS = {".xlsx", ".xls"}
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", "60"))


def _auditar(accion, detalle=""):
    """Guarda quién (IP) hizo qué y cuándo. Nunca interrumpe el flujo."""
    try:
        from models import Auditoria
        db.session.add(Auditoria(accion=accion, detalle=(detalle or "")[:500],
                                 ip=(request.remote_addr or "")[:60]))
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


@bp.app_errorhandler(413)
def _archivo_muy_grande(e):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"error": f"Archivo muy grande (máximo {MAX_MB} MB)."}), 413
    flash(f"Archivo muy grande (máximo {MAX_MB} MB).", "danger")
    return redirect(url_for("main.index"))


# Procesa el archivo único exógeno de EMSA (Villavicencio): lo divide en
# facturación/recaudo, genera solo el informe general y lo guarda
def _finalizar_carga_emsa(exogena_path):
    global CARGADO
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    from core.emsa import (leer_exogena_emisa, MUNICIPIO, COMERCIALIZADORA,
                           TARIFAS_LCEE_2026)

    try:
        fact, rec, periodo_auto = leer_exogena_emisa(exogena_path)
        anio = periodo_auto[0] if periodo_auto else None
        mes = periodo_auto[1] if periodo_auto else None
        if not anio or not mes:
            flash("No se pudo determinar el periodo del archivo exógeno.", "danger")
            dest = url_for("main.index")
            return jsonify({"redirect": dest}) if is_ajax else redirect(dest)
        general_data = build_general(fact, rec, None, None, sin_depurar=True)
        m_obj = get_or_create_municipio(MUNICIPIO)
        c_obj = get_or_create_comerc(m_obj.id, COMERCIALIZADORA)
        report = save_report_to_db(
            MUNICIPIO, COMERCIALIZADORA, anio, mes,
            json_safe(general_data), None,
            fact_path=os.path.abspath(exogena_path),
            rec_path=os.path.abspath(exogena_path),
        )
        upsert_analisis_general(
            c_obj, anio, mes,
            consumo=general_data["f"]["total_consumo"],
            facturacion=general_data["f"]["total_imp"],
            recaudo=general_data["r"]["total_valor"],
        )
        if str(anio) not in (c_obj.tarifas or {}):
            guardar_tarifas(c_obj, anio, TARIFAS_LCEE_2026)
        report_id = report.id
    except Exception as exc:
        flash(f"Error al procesar el archivo exógeno: {exc}", "danger")
        dest = url_for("main.index")
        return jsonify({"redirect": dest}) if is_ajax else redirect(dest)

    DATA["general"] = general_data
    DATA["especiales"] = None
    DATA["mes"] = mes
    DATA["anio"] = anio
    DATA["municipio"] = MUNICIPIO
    DATA["comercializadora"] = COMERCIALIZADORA
    CARGADO = True

    flash(f"Reporte guardado: {MUNICIPIO} / {COMERCIALIZADORA} \u2014 {MESES[mes]} {anio}", "success")
    _auditar("carga_informe", f"{MUNICIPIO} / {COMERCIALIZADORA} — {MESES[mes]} {anio} (reporte #{report_id})")
    if os.environ.get("CONSERVAR_ORIGINALES", "0") != "1":
        try:
            if os.path.isfile(exogena_path):
                os.remove(exogena_path)
        except OSError:
            pass
    dest = url_for("main.general_id", report_id=report_id)
    return jsonify({"redirect": dest}) if is_ajax else redirect(dest)


# Después de tener todos los datos (municipio, año, mes, columnas), arma los
# informes, los guarda en la base de datos y manda al usuario a la página General
def _finalizar_carga(municipio, comercializadora, anio, mes, fact_path, rec_path,
                     mapping_fact=None, mapping_rec=None):
    global CARGADO
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    try:
        general_data = build_general(fact_path, rec_path, mapping_fact, mapping_rec)
        m_obj = get_or_create_municipio(municipio)
        c_obj = get_or_create_comerc(m_obj.id, comercializadora)
        if municipio.strip().lower() == "san pedro":
            # Si es un año nuevo (ej. enero 2027), se crea la columna del año
            # en cartera antes de armar el informe del mes
            ensure_cartera_anio(c_obj, anio)
        especiales_data = build_especiales(mes=mes, comercializadora=c_obj,
                                           anio=anio, fact_path=fact_path,
                                           rec_path=rec_path)
    except Exception as exc:
        flash(f"Error al procesar: {exc}", "danger")
        dest = url_for("main.index")
        return jsonify({"redirect": dest}) if is_ajax else redirect(dest)

    try:
        # Se arma el texto del análisis ejecutivo y se guarda todo en la base de datos
        analisis = texto_ejecutivo(
            municipio=municipio, comercializadora=comercializadora,
            anio=anio, mes=mes, data=especiales_data, variacion=None)
        report = save_report_to_db(
            municipio, comercializadora, anio, mes,
            json_safe(general_data), json_safe(especiales_data), fact_path, rec_path,
            analisis_ejecutivo=analisis,
        )
        report_id = report.id
    except Exception as exc:
        flash(f"Error al guardar en BD: {exc}", "danger")
        dest = url_for("main.index")
        return jsonify({"redirect": dest}) if is_ajax else redirect(dest)

    try:
        # Se guardan los datos en el análisis general de la comercializadora,
        # y si es San Pedro también se acumula la cartera del mes
        upsert_analisis_general(
            report.comercializadora, anio, mes,
            consumo=general_data["f"]["total_consumo"],
            facturacion=general_data["f"]["total_imp"],
            recaudo=general_data["r"]["total_valor"],
        )
        if municipio.strip().lower() == "san pedro":
            try:
                actualizar_cartera_mes(report.comercializadora, anio, mes,
                                       especiales_filas=(especiales_data or {}).get("filas"))
            except Exception as exc:
                flash(f"Aviso: no se pudo acumular la cartera del mes: {exc}", "warning")
    except Exception as exc:
        flash(f"Aviso: no se pudo actualizar el An\u00e1lisis General del mes: {exc}", "warning")

    # Se deja lo cargado en memoria para las pestañas de general y especiales
    DATA["general"] = general_data
    DATA["especiales"] = especiales_data
    DATA["mes"] = mes
    DATA["anio"] = anio
    DATA["municipio"] = municipio
    DATA["comercializadora"] = comercializadora
    CARGADO = True

    flash(f"Reporte guardado: {municipio} / {comercializadora} \u2014 {MESES[mes]} {anio}", "success")
    _auditar("carga_informe", f"{municipio} / {comercializadora} — {MESES[mes]} {anio} (reporte #{report_id})")
    # Política de originales: los Excel subidos ya están guardados en otro
    # lugar, así que por defecto se eliminan al terminar (no ocupan espacio
    # innecesario). Lo que se conserva es la BD (informes en página) y las
    # descargas se regeneran solas desde la BD. Con
    # CONSERVAR_ORIGINALES=1 se conservan (reconstrucciones/auditoría).
    if os.environ.get("CONSERVAR_ORIGINALES", "0") != "1":
        for _p in (fact_path, rec_path):
            try:
                if _p and os.path.isfile(_p):
                    os.remove(_p)
            except OSError:
                pass
    dest = url_for("main.general_id", report_id=report_id)
    return jsonify({"redirect": dest}) if is_ajax else redirect(dest)


# Página de inicio: muestra el formulario para subir los archivos
@bp.route("/")
def index():
    municipios = get_municipios()
    # Municipio del último informe procesado (para adaptar los botones:
    # Villavicencio/EMSA no tiene clientes especiales)
    ultimo = Report.query.order_by(Report.updated_at.desc()).first()
    muni_ultimo = (ultimo.comercializadora.municipio.nombre
                   if ultimo and ultimo.comercializadora else "")
    return render_template("index.html", cargado=CARGADO, municipios=municipios,
                           muni_ultimo=muni_ultimo)


# Las siguientes rutas /api/ entregan datos en formato json para que
# los combos (selects) de la página se llenen solos
@bp.route("/api/municipios")
def api_municipios():
    return jsonify([{"id": m.id, "nombre": m.nombre} for m in get_municipios()])


@bp.route("/api/comerc/<int:municipio_id>")
def api_comerc(municipio_id):
    comercs = get_comercializadoras(municipio_id)
    return jsonify([{"id": c.id, "nombre": c.nombre} for c in comercs])


# Detalle paginado de cuentas para las tablas grandes del informe general.
# Así se pueden recorrer TODAS las filas (ej. 235 mil de Villavicencio)
# sin congelar el navegador: el servidor envía de a 1.000 por página y
# filtra por columna cuando se escribe en los buscadores.
_CAMPOS_DETALLE = {
    "facturacion": [None, "Id_cliente", "Nombre", "Clase", "Sector",
                    "Periodicidad", "ImpuestoAP", "Consumo$", "ConsumokWh"],
    "recaudo": [None, "Id_cliente", "Nombre", "Clase", "Sector",
                "Estrato", "ValorAP"],
    "cuentas": [None, "Id_cliente", "Nombre", "Clase", "Sector",
                "ImpuestoAP", "Consumo$", "ConsumokWh", "ValorAP"],
}


# Une facturación y recaudo en una sola fila por cuenta (listado único)
def _unir_cuentas(facturacion, recaudo):
    base = {}
    orden = []
    for r in facturacion or []:
        k = str(r.get("Id_cliente"))
        if k not in base:
            base[k] = {"Id_cliente": r.get("Id_cliente"), "Nombre": r.get("Nombre"),
                       "Clase": r.get("Clase"), "Sector": r.get("Sector"),
                       "ImpuestoAP": 0.0, "Consumo$": 0.0, "ConsumokWh": 0.0,
                       "ValorAP": 0.0}
            orden.append(k)
        b = base[k]
        b["ImpuestoAP"] = float(b["ImpuestoAP"] or 0) + float(r.get("ImpuestoAP") or 0)
        b["Consumo$"] = float(b["Consumo$"] or 0) + float(r.get("Consumo$") or 0)
        b["ConsumokWh"] = float(b["ConsumokWh"] or 0) + float(r.get("ConsumokWh") or 0)
    for r in recaudo or []:
        k = str(r.get("Id_cliente"))
        if k not in base:
            base[k] = {"Id_cliente": r.get("Id_cliente"), "Nombre": r.get("Nombre"),
                       "Clase": r.get("Clase"), "Sector": r.get("Sector"),
                       "ImpuestoAP": 0.0, "Consumo$": 0.0, "ConsumokWh": 0.0,
                       "ValorAP": 0.0}
            orden.append(k)
        b = base[k]
        if not b["Nombre"]:
            b["Nombre"] = r.get("Nombre")
        if not b["Clase"]:
            b["Clase"] = r.get("Clase")
        if not b["Sector"]:
            b["Sector"] = r.get("Sector")
        b["ValorAP"] = float(b["ValorAP"] or 0) + float(r.get("ValorAP") or 0)
    return [base[k] for k in orden]


def _filas_detalle(general_data, tipo):
    if tipo == "cuentas":
        return _unir_cuentas((general_data or {}).get("facturacion"),
                             (general_data or {}).get("recaudo"))
    return (general_data or {}).get(tipo) or []


@bp.route("/api/detalle")
@bp.route("/api/detalle/<int:report_id>")
def api_detalle(report_id=None):
    import json as _json
    tipo = request.args.get("tipo", "facturacion")
    if tipo not in _CAMPOS_DETALLE:
        tipo = "facturacion"
    try:
        pagina = max(1, int(request.args.get("pagina", 1) or 1))
    except (TypeError, ValueError):
        pagina = 1
    try:
        por_pagina = int(request.args.get("por_pagina", 1000) or 1000)
    except (TypeError, ValueError):
        por_pagina = 1000
    por_pagina = min(10000, max(50, por_pagina))
    try:
        filtros = _json.loads(request.args.get("f", "") or "{}")
    except (TypeError, ValueError):
        filtros = {}
    if not isinstance(filtros, dict):
        filtros = {}

    if report_id:
        report = Report.query.get_or_404(report_id)
        general_data = report.general_data or {}
    else:
        general_data = DATA.get("general") or {}
    filas = _filas_detalle(general_data, tipo)
    campos = _CAMPOS_DETALLE[tipo]

    # Filtro por columna: el texto debe estar contenido en el valor
    activos = {int(k): str(v).strip().lower() for k, v in filtros.items()
               if str(v).strip() and k.lstrip("-").isdigit()
               and 0 <= int(k) < len(campos) and campos[int(k)]}
    # Filtro exacto (chulos del panel Excel): la fila debe tener uno de
    # los valores elegidos; lista vacía = ninguno (no pasa ninguna fila)
    try:
        exactos = _json.loads(request.args.get("e", "") or "{}")
    except (TypeError, ValueError):
        exactos = {}
    if not isinstance(exactos, dict):
        exactos = {}
    exactos = {int(k): ([str(x) for x in v] if isinstance(v, list) else [str(v)])
               for k, v in exactos.items()
               if k.lstrip("-").isdigit() and 0 <= int(k) < len(campos) and campos[int(k)]}

    if activos or exactos:
        sel = []
        for r in filas:
            if activos:
                ok = True
                for col, txt in activos.items():
                    if txt not in str(r.get(campos[col], "") or "").lower():
                        ok = False
                        break
                if not ok:
                    continue
            if exactos:
                ok = True
                for col, vals in exactos.items():
                    if str(r.get(campos[col], "") or "") not in vals:
                        ok = False
                        break
                if not ok:
                    continue
            sel.append(r)
        filas = sel

    total = len(filas)
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(pagina, paginas)
    ini = (pagina - 1) * por_pagina
    return jsonify({"total": total, "paginas": paginas, "pagina": pagina,
                    "por_pagina": por_pagina,
                    "filas": filas[ini:ini + por_pagina]})


# Valores distintos de una columna para el panel de filtros tipo Excel.
# Busca en TODAS las filas (q = texto a contener) y devuelve los primeros
# con sus conteos, para que el panel funcione con reportes gigantes.
@bp.route("/api/valores")
@bp.route("/api/valores/<int:report_id>")
def api_valores(report_id=None):
    tipo = request.args.get("tipo", "facturacion")
    if tipo not in _CAMPOS_DETALLE:
        tipo = "facturacion"
    try:
        col = int(request.args.get("col", -1))
    except (TypeError, ValueError):
        col = -1
    q = (request.args.get("q", "") or "").strip().lower()
    try:
        limite = int(request.args.get("limite", 200) or 200)
    except (TypeError, ValueError):
        limite = 200
    limite = min(500, max(20, limite))
    campos = _CAMPOS_DETALLE[tipo]
    if not (0 <= col < len(campos)) or not campos[col]:
        return jsonify({"valores": [], "total": 0})

    if report_id:
        report = Report.query.get_or_404(report_id)
        general_data = report.general_data or {}
    else:
        general_data = DATA.get("general") or {}
    filas = _filas_detalle(general_data, tipo)
    campo = campos[col]

    from collections import Counter
    conteo = Counter()
    for r in filas:
        v = str(r.get(campo, "") or "")
        if q and q not in v.lower():
            continue
        conteo[v] += 1
    top = sorted(conteo.items(), key=lambda x: (-x[1], x[0]))[:limite]
    return jsonify({"valores": [{"v": v, "n": n} for v, n in top],
                    "total": len(conteo)})


# Recibe los archivos que se suben desde la página. Normalmente son dos
# (facturación y recaudo); para Villavicencio/EMSA basta el archivo exógeno.
@bp.route("/cargar", methods=["POST"])
@limiter.limit("30 per minute")
def cargar():
    global CARGADO
    if "facturacion" not in request.files:
        flash("Debe adjuntar el archivo de facturación.", "danger")
        return redirect(url_for("main.index"))
    f_fact = request.files["facturacion"]
    f_rec = request.files.get("recaudo")
    if not f_fact.filename:
        flash("Debe seleccionar el archivo de facturación.", "danger")
        return redirect(url_for("main.index"))
    # Solo Excel (.xlsx/.xls) y dentro del tamaño permitido
    for f in (f_fact, f_rec):
        if f and f.filename and os.path.splitext(f.filename or "")[1].lower() not in EXT_PERMITIDAS:
            flash(f"Archivo no permitido: {(f.filename or '')[:60]} (solo .xlsx o .xls).", "danger")
            return redirect(url_for("main.index"))

    # Se guardan con un nombre que incluya la fecha y hora para no repetirse
    ts = _dt.now().strftime("%Y%m%d%H%M%S")
    fact_path = os.path.join(ORIG_DIR, f"facturacion_{ts}.xlsx")
    f_fact.save(fact_path)

    # ¿Viene solo un archivo? Si es el exógeno de EMSA (Villavicencio),
    # se procesa por esa vía; si no, se piden los dos archivos
    if not f_rec or not f_rec.filename:
        from core.emsa import es_archivo_emsa
        if es_archivo_emsa(fact_path):
            return _finalizar_carga_emsa(fact_path)
        try:
            os.remove(fact_path)
        except OSError:
            pass
        flash("Debe adjuntar también el archivo de recaudo (para Villavicencio/EMSA basta el archivo exógeno).", "danger")
        return redirect(url_for("main.index"))

    rec_path = os.path.join(ORIG_DIR, f"recaudo_{ts}.xlsx")
    f_rec.save(rec_path)

    try:
        # Se leen los nombres de las columnas de cada archivo
        headers_f = [str(c) for c in leer_excel(fact_path, nrows=0).columns]
        headers_r = [str(c) for c in leer_excel(rec_path, nrows=0).columns]
    except Exception as exc:
        flash(f"Error al leer los archivos: {exc}", "danger")
        return redirect(url_for("main.index"))

    # Muestra de valores por columna (para que el cuestionario enseñe ejemplos)
    def _muestras(path, headers, n=3):
        try:
            df = leer_excel(path, nrows=8)
            col_por_nombre = {str(c): c for c in df.columns}
        except Exception:
            return {}
        out = {}
        for h in headers:
            if h not in col_por_nombre:
                continue
            vals = df[col_por_nombre[h]].dropna().astype(str).str.strip()
            vistos = []
            for v in vals:
                if v and v not in ("nan", "NaT", "None") and v not in vistos:
                    vistos.append(v[:28])
                if len(vistos) >= n:
                    break
            out[h] = ", ".join(vistos)
        return out

    muestras_f = _muestras(fact_path, headers_f)
    muestras_r = _muestras(rec_path, headers_r)

    # Se comparan las columnas del archivo con las que el sistema necesita
    map_f, falt_f = resolver_columnas(FACT_CLAVES, headers_f)
    map_r, falt_r = resolver_columnas(REC_CLAVES, headers_r)

    mun_col = _resolver_una("municipio", headers_f + headers_r)
    if mun_col:
        (map_f if mun_col in headers_f else map_r)[mun_col] = "municipio"
    fec_col = _resolver_una("fecha", headers_f + headers_r)
    if fec_col:
        (map_f if fec_col in headers_f else map_r)[fec_col] = "fecha_generacion"

    try:
        # Se intenta adivinar municipio, comercializadora, año y mes desde los archivos
        municipio, comercializadora, anio, mes = detectar_metadatos(
            fact_path, rec_path, map_f, map_r)
    except Exception as exc:
        flash(f"Error al leer metadatos de los archivos: {exc}", "danger")
        return redirect(url_for("main.index"))

    # Qué datos hacen falta para poder procesar
    faltantes = []
    if not municipio:
        faltantes.append("municipio")
    if not comercializadora:
        faltantes.append("comercializadora")
    if not anio:
        faltantes.append("anio")
    if not mes:
        faltantes.append("mes")

    # Si falta algo (columnas o datos), se manda al usuario a llenarlo a mano
    if falt_f or falt_r or faltantes:
        set_pendiente(ts, {
            "fact_path": fact_path, "rec_path": rec_path,
            "municipio": municipio, "comercializadora": comercializadora,
            "anio": anio, "mes": mes,
            "falt_f": falt_f, "falt_r": falt_r, "faltantes": faltantes,
            "map_f": map_f, "map_r": map_r,
            "headers_f": headers_f, "headers_r": headers_r,
            "muestras_f": muestras_f, "muestras_r": muestras_r,
            "hay_fecha": fec_col is not None,
        })
        # Si viene por ajax (página de carga), se devuelve el cuestionario
        # emergente: una pregunta por cada columna no reconocida, con las
        # columnas encontradas en el archivo como opciones
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            preguntas = (
                [{"archivo": "facturación", "clave": c,
                  "etiqueta": ETIQUETAS_CLAVE.get(c, c),
                  "ejemplo": EJEMPLOS_CLAVE.get(c, ""),
                  "opciones": headers_f, "muestras": muestras_f}
                 for c in falt_f]
                + [{"archivo": "recaudo", "clave": c,
                    "etiqueta": ETIQUETAS_CLAVE.get(c, c),
                    "ejemplo": EJEMPLOS_CLAVE.get(c, ""),
                    "opciones": headers_r, "muestras": muestras_r}
                   for c in falt_r]
            )
            return jsonify({"cuestionario": True, "t": ts,
                            "preguntas": preguntas,
                            "faltantes": faltantes,
                            "metadatos_url": url_for("main.completar_metadatos", t=ts)})
        return redirect(url_for("main.completar_metadatos", t=ts))

    return _finalizar_carga(municipio, comercializadora, anio, mes,
                            fact_path, rec_path, map_f, map_r)


# Muestra el formulario para llenar a mano lo que faltó (metadatos)
@bp.route("/cargar/metadatos")
def completar_metadatos():
    t = request.args.get("t", "")
    p = get_pendiente(t)
    if not p:
        flash("La sesi\u00f3n de datos incompletos expir\u00f3 o ya no est\u00e1 disponible. Vuelva a cargar los archivos.", "warning")
        return redirect(url_for("main.index"))
    municipios = sorted({m.nombre for m in get_municipios()})
    comercializadoras = sorted({c.nombre for c in get_comercializadoras()})
    return render_template("metadatos.html", t=t, p=p, municipios=municipios,
                           comercializadoras=comercializadoras,
                           MESES=MESES, ETIQUETAS=ETIQUETAS_CLAVE, EJEMPLOS=EJEMPLOS_CLAVE)


# Recibe lo que el usuario llenó en el formulario de metadatos
@bp.route("/cargar/metadatos/<t>", methods=["POST"])
def procesar_metadatos(t):
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    p = get_pendiente(t)
    if not p:
        flash("La sesi\u00f3n de datos incompletos expir\u00f3 o ya no est\u00e1 disponible. Vuelva a cargar los archivos.", "warning")
        dest = url_for("main.index")
        return jsonify({"redirect": dest}) if is_ajax else redirect(dest)

    map_f = dict(p.get("map_f", {}))
    map_r = dict(p.get("map_r", {}))
    headers_f = p.get("headers_f", [])
    headers_r = p.get("headers_r", [])

    # Para cada columna que faltaba, se guarda cuál eligió el usuario. Se
    # recorren TODAS las claves (no solo las que faltaban en la ronda anterior):
    # si una columna se reasigna, la clave que la tenía antes queda sin mapeo
    # y hay que volver a pedirla, no dar por bueno el mapa viejo
    for clave in FACT_CLAVES:
        sel = request.form.get(f"col_fact_{clave}")
        if sel and sel in headers_f:
            map_f[sel] = clave
            _guardar_alias_columna(clave, sel)
    for clave in REC_CLAVES:
        sel = request.form.get(f"col_rec_{clave}")
        if sel and sel in headers_r:
            map_r[sel] = clave
            _guardar_alias_columna(clave, sel)

    fec_col = request.form.get("fecha_col")
    if fec_col and fec_col != "__ninguna__":
        if fec_col in headers_f:
            map_f[fec_col] = "fecha_generacion"
        elif fec_col in headers_r:
            map_r[fec_col] = "fecha_generacion"
        _guardar_alias_columna("fecha", fec_col)

    mun_col = request.form.get("municipio_col")
    if mun_col and mun_col != "__manual__":
        if mun_col in headers_f:
            map_f[mun_col] = "municipio"
        elif mun_col in headers_r:
            map_r[mun_col] = "municipio"
        _guardar_alias_columna("municipio", mun_col)

    # Se toman los datos escritos a mano (o los que ya se habían detectado)
    municipio = (request.form.get("municipio") or "").strip() or p.get("municipio")
    comercializadora = (request.form.get("comercializadora") or "").strip() or p.get("comercializadora")
    anio_s = (request.form.get("anio") or "").strip() or p.get("anio")
    mes_s = (request.form.get("mes") or "").strip() or p.get("mes")
    try:
        anio = int(anio_s) if anio_s else None
    except (TypeError, ValueError):
        anio = None
    try:
        mes = int(mes_s) if mes_s else None
    except (TypeError, ValueError):
        mes = None

    # Si el usuario eligió columna de municipio o fecha, se vuelve a intentar detectar
    try:
        if any(v in ("municipio", "fecha_generacion")
               for v in list(map_f.values()) + list(map_r.values())):
            d_muni, d_com, d_anio, d_mes = detectar_metadatos(
                p["fact_path"], p["rec_path"], map_f, map_r)
            if not municipio:
                municipio = d_muni
            if not comercializadora:
                comercializadora = d_com
            if not anio:
                anio = d_anio
            if not mes:
                mes = d_mes
    except Exception:
        pass

    # Se revisa qué sigue faltando. Se compara contra TODAS las claves, no
    # contra la lista guardada: si una columna se reasignó, la clave anterior
    # quedó sin mapeo y debe volver a pedirse
    falt_f = [c for c in FACT_CLAVES if c not in map_f.values()]
    falt_r = [c for c in REC_CLAVES if c not in map_r.values()]

    faltantes = []
    if falt_f or falt_r:
        faltantes.append("columnas")
    if not municipio:
        faltantes.append("municipio")
    if not comercializadora:
        faltantes.append("comercializadora")
    if not anio:
        faltantes.append("anio")
    if not mes:
        faltantes.append("mes")

    # Si aún falta algo, se vuelve a mostrar el formulario con lo avanzado
    if faltantes:
        flash("Complete los campos solicitados para poder continuar.", "danger")
        nv = dict(p)
        nv.update(municipio=municipio or p.get("municipio"),
                  comercializadora=comercializadora or p.get("comercializadora"),
                  anio=anio, mes=mes, map_f=map_f, map_r=map_r,
                  falt_f=falt_f, falt_r=falt_r, faltantes=faltantes)
        set_pendiente(t, nv)
        municipios = sorted({m.nombre for m in get_municipios()})
        comercializadoras = sorted({c.nombre for c in get_comercializadoras()})
        if is_ajax:
            return jsonify({"redirect": url_for("main.completar_metadatos", t=t)})
        return render_template("metadatos.html", t=t, p=nv, municipios=municipios,
                               comercializadoras=comercializadoras,
                               MESES=MESES, ETIQUETAS=ETIQUETAS_CLAVE, EJEMPLOS=EJEMPLOS_CLAVE)

    # Si ya está todo, se borra la sesión pendiente y se termina de procesar
    del_pendiente(t)
    return _finalizar_carga(municipio, comercializadora, anio, mes,
                            p["fact_path"], p["rec_path"], map_f, map_r)


# Muestra el historial de reportes guardados, con filtros opcionales
@bp.route("/historial")
def historial():
    filtro_municipio = request.args.get("municipio", "")
    filtro_comerc = request.args.get("comercializadora", "")
    filtro_mes = request.args.get("mes", "")

    reports = get_all_reports(
        filtro_municipio=filtro_municipio or None,
        filtro_comerc=filtro_comerc or None,
        filtro_mes=int(filtro_mes) if filtro_mes else None,
    )
    # Ids con informe de especiales (consulta liviana, sin traer los JSON):
    # los municipios sin especiales (ej. Villavicencio/EMSA) no muestran
    # esas acciones en el historial. Se excluyen NULL y textos vacíos
    # ('null', '{}', ...) que equivalen a no tener especiales.
    con_especiales = {r_id for (r_id,) in
                      db.session.query(Report.id)
                      .filter(Report.especiales_data.isnot(None),
                              ~Report.especiales_data.in_(['null', '{}', '[]', ''])).all()}
    municipios = get_municipios()
    # Color distinto y notorio por municipio (estable aunque se filtre):
    # clases propias (badge-muni-*) que ningún override del tema apaga
    paleta_muni = [f"badge-muni-{i}" for i in range(7)]
    colores_municipio = {m.nombre: paleta_muni[i % len(paleta_muni)]
                         for i, m in enumerate(sorted(municipios, key=lambda x: x.nombre))}
    return render_template("historial.html", reports=reports, municipios=municipios,
                           filtro_municipio=filtro_municipio,
                           filtro_comerc=filtro_comerc,
                           filtro_mes=filtro_mes,
                           con_especiales=con_especiales,
                           colores_municipio=colores_municipio,
                           meses=MESES)


# Villavicencio/EMSA usa el formato de la hoja Informe FyR (tablas y
# gráficas propias), distinto al del resto de municipios
def _contexto_fyr(municipio, comercializadora, general_data):
    from core.fyr import FYR_ORDEN, fyr_agregar
    es_emsa = ((comercializadora or "").strip().lower() == "emsa"
               or (municipio or "").strip().lower() == "villavicencio")
    if not es_emsa:
        return False, None, None
    fyr = fyr_agregar((general_data or {}).get("facturacion"),
                      (general_data or {}).get("recaudo"))
    return True, fyr, list(FYR_ORDEN)


# Página del informe general (usa el último reporte guardado en BD)
@bp.route("/general")
def general():
    ultimo = Report.query.order_by(Report.updated_at.desc()).first()
    if not ultimo or ultimo.general_data is None:
        flash("Primero debe cargar los archivos.", "warning")
        return redirect(url_for("main.index"))
    return redirect(url_for("main.general_id", report_id=ultimo.id))


# Página del informe general de un reporte guardado (desde el historial)
@bp.route("/general/<int:report_id>")
def general_id(report_id):
    report = Report.query.get_or_404(report_id)
    general_data = report.general_data
    if general_data is None:
        flash("Este reporte no tiene datos procesados.", "warning")
        return redirect(url_for("main.historial"))
    DATA["general"] = general_data
    es_emsa, fyr, fyr_orden = _contexto_fyr(
        report.municipio_nombre, report.comercializadora_nombre, general_data)
    # Saldo a favor de la cartera del año del informe (tarjeta inicial "Cartera")
    saldo_favor = None
    if report.comercializadora:
        cartera_rep = get_cartera(report.comercializadora, report.anio)
        if cartera_rep:
            saldo_favor = (cartera_rep.get("total_favor") or {}).get(str(report.anio))
            if saldo_favor is None:
                saldo_favor = (cartera_rep.get("total_favor") or {}).get("total")
    return render_template("general.html", data=general_data, report_id=report_id,
                           municipio=report.municipio_nombre,
                           comercializadora=report.comercializadora_nombre,
                           periodo=f"{report.mes_nombre} {report.anio}",
                           es_emsa=es_emsa, fyr=fyr, fyr_orden=fyr_orden,
                           saldo_favor=saldo_favor)


# Página del informe de especiales (usando el último reporte guardado)
@bp.route("/especiales")
def especiales():
    ultimo = Report.query.order_by(Report.updated_at.desc()).first()
    if not ultimo or ultimo.general_data is None:
        flash("Primero debe cargar los archivos.", "warning")
        return redirect(url_for("main.index"))
    return redirect(url_for("main.especiales_id", report_id=ultimo.id))


# Página del informe de especiales de un reporte guardado
@bp.route("/especiales/<int:report_id>")
def especiales_id(report_id):
    report = Report.query.get_or_404(report_id)
    especiales_data = report.especiales_data
    if especiales_data is None:
        flash("Este reporte no tiene datos de especiales.", "warning")
        return redirect(url_for("main.historial"))
    c_obj = report.comercializadora
    # Si el reporte guardado tiene los archivos originales, se recalculan los
    # especiales con la cartera más reciente (por si cambió)
    if (c_obj and report.archivo_fact_path and report.archivo_rec_path
            and os.path.isfile(report.archivo_fact_path)
            and os.path.isfile(report.archivo_rec_path)):
        needs_rebuild = "analisis" not in especiales_data
        if not needs_rebuild:
            cartera = get_cartera(c_obj, report.anio)
            if cartera:
                cartera_ids = {str(c["id"]).strip() for c in cartera.get("clientes", []) if (c.get("tarifa_min") or 0) > 0}
                esp_ids = {str(f["id"]).strip() for f in especiales_data.get("filas", [])}
                if cartera_ids and cartera_ids != esp_ids:
                    needs_rebuild = True
        if needs_rebuild:
            try:
                rebuilt = build_especiales(
                    mes=report.mes, comercializadora=c_obj, anio=report.anio,
                    fact_path=report.archivo_fact_path, rec_path=report.archivo_rec_path)
                if rebuilt and "analisis" in rebuilt:
                    especiales_data = rebuilt
                    report.especiales_data = rebuilt
                    db.session.commit()
            except Exception:
                pass
    if especiales_data is None:
        flash("Este reporte no tiene datos de especiales.", "warning")
        return redirect(url_for("main.historial"))
    # Reportes viejos que no tienen análisis: se les agrega con la lista fija
    if "analisis" not in especiales_data:
        extra = build_especiales(mes=report.mes)
        esp = dict(especiales_data)
        esp["filas"] = extra["filas"]
        esp["analisis"] = extra["analisis"]
        esp["por_clase"] = extra["por_clase"]
        esp["grupos"] = extra["grupos"]
        especiales_data = esp
        report.especiales_data = esp
        db.session.commit()
    DATA["especiales"] = especiales_data
    variacion = variacion_saldo_neg(report)
    if not report.analisis_ejecutivo:
        analisis = texto_ejecutivo(
            municipio=report.municipio_nombre,
            comercializadora=report.comercializadora_nombre,
            anio=report.anio, mes=report.mes,
            data=especiales_data, variacion=variacion)
    else:
        analisis = report.analisis_ejecutivo
    return render_template("especiales.html", data=especiales_data, report_id=report_id,
                           municipio=report.municipio_nombre,
                           comercializadora=report.comercializadora_nombre,
                           periodo=f"{report.mes_nombre} {report.anio}",
                           analisis_ejecutivo=analisis,
                           novedades=report.novedades or {},
                           variacion=variacion)


# Guarda el análisis ejecutivo y las novedades que edite el usuario en la página
@bp.route("/reporte/<int:report_id>/analisis", methods=["POST"])
def guardar_analisis(report_id):
    report = Report.query.get_or_404(report_id)
    body = request.get_json(silent=True) or {}
    if "analisis_ejecutivo" in body:
        report.analisis_ejecutivo = str(body.get("analisis_ejecutivo", "") or "")
    if isinstance(body.get("novedades"), dict):
        nov = {str(k): str(v) for k, v in body["novedades"].items() if str(v).strip()}
        report.novedades = nov
    db.session.commit()
    return jsonify({"ok": True, "guardado": True})


# Preparar los datos de la página "Información de referencia" (análisis general,
# tarifas y descripción por comercializadora y año)
def _render_informacion_referencia(comercializadora=None, anio=None, tanio=None):
    combos = Comercializadora.query.all()
    if not combos:
        flash("Primero debe cargar informes para ver la Informaci\u00f3n de Referencia por municipio.", "warning")
        return redirect(url_for("main.historial"))

    if comercializadora is None:
        comercializadora = combos[0]

    folders = get_analisis_general_folders(comercializadora)
    anios = sorted((int(k) for k in folders if str(k).isdigit()), reverse=True)
    if anio is None:
        for a in anios:
            if folders.get(str(a)):
                anio = a
                break
        if anio is None and anios:
            anio = anios[0]
    if anio is not None and str(anio) not in folders:
        anio = anios[0] if anios else None

    meses_year = dict(folders.get(str(anio), {}) or {}) if anio else {}

    if tanio is not None and str(tanio) not in (comercializadora.tarifas or {}):
        tanio = None
    tarifas_year, tarifas_anios_list = get_tarifas(comercializadora, tanio)
    if tanio is None and tarifas_anios_list:
        tanio = tarifas_anios_list[0]

    info_ref = get_info_especiales(comercializadora)
    desc_grupos = (get_descripcion(comercializadora).get("grupos")
                   or (info_ref or {}).get("descripcion", {}).get("grupos"))

    return render_template(
        "informacion_referencia.html",
        com=comercializadora,
        combos=combos,
        anio=anio,
        anios=anios,
        meses_year=meses_year,
        info_ref=info_ref,
        tanio=tanio,
        tarifas_anios=tarifas_anios_list,
        tarifas_year=tarifas_year,
        desc_grupos=desc_grupos,
        municipio=comercializadora.municipio.nombre if comercializadora.municipio else "",
    )


# Página de información de referencia (recibe la comercializadora por la url)
@bp.route("/informacion-referencia")
def informacion_referencia():
    com_id = request.args.get("com", type=int)
    anio = request.args.get("anio", type=int)
    tanio = request.args.get("tanio", type=int)
    com = Comercializadora.query.get(com_id) if com_id else None
    return _render_informacion_referencia(com, anio, tanio)


# Crea una carpeta (año) en el análisis general
@bp.route("/informacion-referencia/crear-anio", methods=["POST"])
@bp.route("/analisis-general/crear-anio", methods=["POST"])
def informacion_referencia_crear_anio():
    com_id = request.form.get("com", type=int)
    anio = request.form.get("anio", type=int)
    com = Comercializadora.query.get_or_404(com_id) if com_id else None
    if not com:
        flash("No se identific\u00f3 la comercializadora.", "danger")
        return redirect(url_for("main.informacion_referencia"))
    if not anio or not (1900 <= anio <= 2100):
        flash("A\u00f1o inv\u00e1lido.", "danger")
        return redirect(url_for("main.informacion_referencia", com=com.id))
    crear_carpeta_anio(com, anio)
    flash(f"Carpeta del a\u00f1o {anio} creada.", "success")
    return redirect(url_for("main.informacion_referencia", com=com.id, anio=anio))


# Ruta vieja de análisis general: manda a información de referencia
@bp.route("/analisis-general")
def analisis_general():
    return redirect(url_for("main.informacion_referencia"))


# Borra una carpeta (año) del análisis general
@bp.route("/informacion-referencia/eliminar-anio", methods=["POST"])
def informacion_referencia_eliminar_anio():
    com_id = request.form.get("com", type=int)
    anio = request.form.get("anio", type=int)
    com = Comercializadora.query.get_or_404(com_id) if com_id else None
    if not com:
        flash("No se identific\u00f3 la comercializadora.", "danger")
        return redirect(url_for("main.informacion_referencia"))
    if not anio or not (1900 <= anio <= 2100):
        flash("A\u00f1o inv\u00e1lido.", "danger")
        return redirect(url_for("main.informacion_referencia", com=com.id))
    if eliminar_carpeta_anio(com, anio):
        flash(f"Carpeta de an\u00e1lisis del a\u00f1o {anio} eliminada.", "success")
    else:
        flash(f"No existe carpeta de an\u00e1lisis para el a\u00f1o {anio}.", "warning")
    return redirect(url_for("main.informacion_referencia", com=com.id))


# Guarda las tarifas de un año (las manda la página desde un botón "Guardar")
@bp.route("/informacion-referencia/tarifas/guardar", methods=["POST"])
def tarifas_guardar():
    payload = request.get_json(silent=True) or {}
    com_id = payload.get("com")
    anio = payload.get("anio")
    tarifas = payload.get("tarifas")
    com = Comercializadora.query.get(int(com_id)) if com_id else None
    if not com:
        flash("No se identific\u00f3 la comercializadora.", "danger")
        return jsonify({"ok": False, "error": "comercializadora"})
    try:
        anio = int(anio)
    except (TypeError, ValueError):
        anio = None
    if not anio or not (1900 <= anio <= 2100):
        flash("A\u00f1o inv\u00e1lido.", "danger")
        return jsonify({"ok": False, "error": "anio"})
    if not isinstance(tarifas, dict):
        flash("Informaci\u00f3n de tarifas inv\u00e1lida.", "danger")
        return jsonify({"ok": False, "error": "tarifas"})

    # Solo se guardan las filas que sean diccionarios (por seguridad)
    def _clean_list(lst):
        out = []
        for row in (lst or []):
            if not isinstance(row, dict):
                continue
            out.append(row)
        return out

    clean = {
        "residenciales": _clean_list(tarifas.get("residenciales")),
        "no_residenciales": _clean_list(tarifas.get("no_residenciales")),
        "autogeneradores": _clean_list(tarifas.get("autogeneradores")),
        "actividades": _clean_list(tarifas.get("actividades")),
        "techo": tarifas.get("techo") if isinstance(tarifas.get("techo"), dict) else {},
    }
    # Esquema porcentual sobre LCEE (usado por municipios como Villavicencio)
    if tarifas.get("esquema"):
        clean["esquema"] = str(tarifas["esquema"])
    if isinstance(tarifas.get("lcee"), dict):
        lcee = tarifas["lcee"]
        clean["lcee"] = {
            "fuente": lcee.get("fuente"),
            "base_gravable": lcee.get("base_gravable"),
            "residenciales": _clean_list(lcee.get("residenciales")),
            "sectores": _clean_list(lcee.get("sectores")),
            "predios_sin_servicio": lcee.get("predios_sin_servicio")
            if isinstance(lcee.get("predios_sin_servicio"), dict) else {},
            "notas": [str(n) for n in (lcee.get("notas") or []) if str(n).strip()],
        }
    guardar_tarifas(com, anio, clean)
    flash(f"Tarifas del a\u00f1o {anio} actualizadas.", "success")
    return jsonify({"ok": True})


# Crea un nuevo año de tarifas
@bp.route("/informacion-referencia/tarifas/crear-anio", methods=["POST"])
@bp.route("/analisis-general/crear-anio-tarifas", methods=["POST"])
def tarifas_crear_anio():
    com_id = request.form.get("com", type=int)
    anio = request.form.get("anio", type=int)
    com = Comercializadora.query.get_or_404(com_id) if com_id else None
    if not com:
        flash("No se identific\u00f3 la comercializadora.", "danger")
        return redirect(url_for("main.informacion_referencia"))
    if not anio or not (1900 <= anio <= 2100):
        flash("A\u00f1o inv\u00e1lido.", "danger")
        return redirect(url_for("main.informacion_referencia", com=com.id))
    crear_anio_tarifas(com, anio)
    flash(f"Carpeta de tarifas del a\u00f1o {anio} creada.", "success")
    return redirect(url_for("main.informacion_referencia", com=com.id, tanio=anio))


# Borra las tarifas de un año
@bp.route("/informacion-referencia/tarifas/eliminar-anio", methods=["POST"])
def tarifas_eliminar_anio():
    com_id = request.form.get("com", type=int)
    anio = request.form.get("anio", type=int)
    com = Comercializadora.query.get_or_404(com_id) if com_id else None
    if not com:
        flash("No se identific\u00f3 la comercializadora.", "danger")
        return redirect(url_for("main.informacion_referencia"))
    if not anio or not (1900 <= anio <= 2100):
        flash("A\u00f1o inv\u00e1lido.", "danger")
        return redirect(url_for("main.informacion_referencia", com=com.id))
    if eliminar_anio_tarifas(com, anio):
        flash(f"Carpeta de tarifas del a\u00f1o {anio} eliminada.", "success")
    else:
        flash(f"No existe carpeta de tarifas para el a\u00f1o {anio}.", "warning")
    return redirect(url_for("main.informacion_referencia", com=com.id))


# Guarda la descripción de un grupo (residencial, comercial, etc.)
@bp.route("/informacion-referencia/descripcion/guardar", methods=["POST"])
def descripcion_guardar():
    payload = request.get_json(silent=True) or {}
    com = Comercializadora.query.get(int(payload.get("com"))) if payload.get("com") else None
    grupo = (payload.get("grupo") or "").strip()
    items = payload.get("items")
    if not com:
        return jsonify({"ok": False, "error": "comercializadora"})
    if not grupo:
        return jsonify({"ok": False, "error": "grupo"})
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "items"})
    texto_items = [str(i).strip() for i in items if str(i).strip()]
    desc = dict(com.descripcion) if isinstance(com.descripcion, dict) else {}
    grupos = dict(desc.get("grupos") or {})
    grupos[grupo] = texto_items
    desc["grupos"] = grupos
    com.descripcion = desc
    db.session.commit()
    flash(f"Descripci\u00f3n del {grupo} actualizada.", "success")
    return jsonify({"ok": True})


# Siempre devuelve la comercializadora de San Pedro si existe,
# si no la que se pide por id, y si no cualquiera
def _cartera_comercializadora(com_id=None):
    sp = Municipio.query.filter(Municipio.nombre.ilike("San Pedro")).first()
    if com_id:
        c = Comercializadora.query.get(com_id)
        if c:
            return c
    if sp:
        c = Comercializadora.query.filter_by(municipio_id=sp.id).first()
        if c:
            return c
    return Comercializadora.query.first()


# Página de la cartera acumulada (los saldos por cuenta).
# Solo San Pedro tiene cartera. El año en vista se elige con ?anio= (por
# defecto el más reciente); los meses mostrados son los del año en vista y
# los años cerrados con meses guardados salen colapsables debajo.
@bp.route("/cartera")
def cartera():
    com = _cartera_comercializadora(None)
    if not com:
        flash("Primero debe cargar informes para ver la Cartera Acumulada.", "warning")
        return redirect(url_for("main.historial"))

    anios_con_datos = carteras_anios(com)
    anio_max = anios_con_datos[0] if anios_con_datos else 2026
    vista = request.args.get("anio", type=int)
    if vista not in anios_con_datos:
        vista = anio_max
    cartera_data = get_cartera(com, vista)
    if not cartera_data:
        cartera_data = get_cartera(com)

    clientes = (cartera_data or {}).get("clientes", [])
    # Meses del año en vista para la tabla principal (los "meses" planos son 2026)
    for c in clientes:
        ma = c.get("meses_anios") or {}
        mv = ma.get(str(vista))
        if mv is None and vista == 2026 and isinstance(c.get("meses"), dict):
            mv = c["meses"]
        c["meses"] = dict(mv or {})

    anios_cols = list(range(2019, vista + 1))

    # Años cerrados con meses guardados -> bloques colapsables con sus meses
    hist = []
    otros = sorted({str(k) for c in clientes for k in (c.get("meses_anios") or {})
                    if str(k).isdigit() and int(k) != vista}, key=int, reverse=True)
    for y in otros:
        filas = []
        fav = {m: 0.0 for m in range(1, 13)}
        pag = {m: 0.0 for m in range(1, 13)}
        for c in clientes:
            mm = dict(((c.get("meses_anios") or {}).get(y)) or {})
            if any(float(mm.get(str(m)) or 0) for m in range(1, 13)):
                filas.append({"id": c.get("id"), "nombre": c.get("nombre"), "meses": mm})
                for m in range(1, 13):
                    v = float(mm.get(str(m)) or 0)
                    if v > 0:
                        fav[m] += v
                    elif v < 0:
                        pag[m] += v
        if filas:
            hist.append({"anio": int(y), "filas": filas, "fav": fav, "pag": pag})

    # Totales por mes del año en vista: cuánto hay a favor y a pagar (SUMIF)
    total_mes_favor = {}
    total_mes_pagar = {}
    for m in range(1, 13):
        fav = pag = 0.0
        for c in clientes:
            v = float(((c.get("meses") or {}).get(str(m)) or 0))
            if v > 0:
                fav += v
            elif v < 0:
                pag += v
        total_mes_favor[m] = fav
        total_mes_pagar[m] = pag

    flt_labels = (["#", "ID Cuenta", "Nombre"] + [str(a) for a in anios_cols]
                  + ["VALOR TOTAL", "Notificación", "Saldo"]
                  + [MESES[m] for m in range(1, 13)])

    return render_template(
        "cartera.html",
        com=com,
        anio=vista,
        anio_max=anio_max,
        anios_disponibles=anios_con_datos,
        anios_cols=anios_cols,
        cartera=cartera_data,
        municipio=com.municipio.nombre if com.municipio else "",
        total_mes_favor=total_mes_favor,
        total_mes_pagar=total_mes_pagar,
        hist=hist,
        flt_cols=len(flt_labels),
        flt_labels=flt_labels,
        MESES=MESES,
    )


# Recibe el archivo de referencia (Clientes Especiales) para armar la cartera
@bp.route("/cartera/cargar-referencia", methods=["POST"])
def cartera_cargar_referencia():
    com_id = request.form.get("com", type=int)
    anio = request.form.get("anio", type=int)
    com = _cartera_comercializadora(com_id)
    if not com:
        flash("No se identific\u00f3 la comercializadora.", "danger")
        return redirect(url_for("main.cartera"))

    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Debe seleccionar el archivo de referencia (Clientes Especiales).", "danger")
        return redirect(url_for("main.cartera", com=com.id))
    from werkzeug.utils import secure_filename
    nombre = secure_filename(os.path.basename(archivo.filename or ""))
    if not nombre or os.path.splitext(nombre)[1].lower() not in EXT_PERMITIDAS:
        flash("Archivo no permitido (solo .xlsx o .xls).", "danger")
        return redirect(url_for("main.cartera", com=com.id))

    if not anio or not (1900 <= anio <= 2100):
        anio = 2026

    destino = os.path.join(UPLOAD_DIR, "referencia_" + _dt.now().strftime("%Y%m%d%H%M%S") + "_" + nombre)
    archivo.save(destino)

    try:
        cartera_data = cargar_cartera_desde_referencia(com, destino, anio)
    except Exception as exc:
        flash(f"Error al procesar el archivo de referencia: {exc}", "danger")
        try:
            os.remove(destino)
        except OSError:
            pass
        return redirect(url_for("main.cartera", com=com.id))

    if not cartera_data:
        flash("El archivo de referencia no contiene la hoja CARTERA 5 A\u00d1OS.", "warning")
        return redirect(url_for("main.cartera", com=com.id))

    flash(f"Cartera acumulada del a\u00f1o {anio} cargada correctamente.", "success")
    _auditar("carga_referencia", f"{com.municipio.nombre if com.municipio else ''} / {com.nombre} — año {anio}")
    # El libro de referencia también está guardado en otro lugar: se elimina
    # la copia salvo que se pida conservarla
    if os.environ.get("CONSERVAR_ORIGINALES", "0") != "1":
        try:
            if os.path.isfile(destino):
                os.remove(destino)
        except OSError:
            pass
    return redirect(url_for("main.cartera", com=com.id, anio=anio))


# Descarga el Excel del informe (general o especiales) que está en memoria
@bp.route("/exportar/<tipo>")
def exportar(tipo):
    if tipo == "general":
        if DATA["general"] is None:
            return redirect(url_for("main.index"))
        path = exportar_general(DATA["general"], "informe_general.xlsx")
    elif tipo == "especiales":
        if DATA["especiales"] is None:
            DATA["especiales"] = build_especiales(mes=DATA.get("mes", 7))
        path = exportar_especiales(DATA["especiales"], "informe_especiales.xlsx")
    else:
        return redirect(url_for("main.index"))
    return send_from_directory(EXPORT_DIR, os.path.basename(path), as_attachment=True)


# Descarga el Excel completo de un reporte (guardado o el que está en memoria)
@bp.route("/descargar/excel")
@bp.route("/descargar/excel/<int:report_id>")
def descargar_excel(report_id=None):
    if report_id:
        report = Report.query.get_or_404(report_id)
        general_data = report.general_data
        especiales_data = report.especiales_data
        analisis_ejecutivo = report.analisis_ejecutivo
        novedades = report.novedades or {}
        variacion = variacion_saldo_neg(report)
        fname = f"Informe_FyR_{report.municipio_nombre}_{report.comercializadora_nombre}_{report.anio}_{report.mes}.xlsx"
    else:
        if DATA["general"] is None:
            flash("Primero debe cargar los archivos.", "warning")
            return redirect(url_for("main.index"))
        general_data = DATA["general"]
        especiales_data = DATA["especiales"] or build_especiales(mes=DATA.get("mes", 7))
        fname = "Informe_FyR_Celsia.xlsx"

    from reports.excel_engine import generar_excel_general
    buf = generar_excel_general(general_data, especiales_data, analisis_ejecutivo, novedades, variacion)
    _auditar("descarga_excel", fname)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=fname)


# Descarga el Word del informe general o de especiales
# (se elige con ?tipo=general o ?tipo=especiales en la url)
@bp.route("/descargar/word")
@bp.route("/descargar/word/<int:report_id>")
def descargar_word(report_id=None):
    tipo = (request.args.get("tipo") or "general").lower()

    # Datos del reporte guardado (si viene el id) o de lo que está en memoria
    if report_id:
        report = Report.query.get_or_404(report_id)
        general_data = report.general_data
        especiales_data = report.especiales_data
        analisis_ejecutivo = report.analisis_ejecutivo
        municipio = report.municipio_nombre
        comercializadora = report.comercializadora_nombre
        anio = report.anio
        mes = report.mes
    else:
        if DATA["general"] is None:
            flash("Primero debe cargar los archivos.", "warning")
            return redirect(url_for("main.index"))
        general_data = DATA["general"]
        especiales_data = DATA["especiales"] or build_especiales(mes=DATA.get("mes", 7))
        analisis_ejecutivo = None
        municipio = DATA.get("municipio") or ""
        comercializadora = DATA.get("comercializadora") or ""
        anio = DATA.get("anio")
        mes = DATA.get("mes")

    if tipo == "especiales":
        if especiales_data is None:
            flash("Este reporte no tiene datos de clientes especiales.", "warning")
            return redirect(url_for("main.historial"))
        # Cartera acumulada para el Word (existe solo en San Pedro)
        cartera_data = None
        acumulado = None
        try:
            _com_obj = None
            if report_id and report.comercializadora:
                _com_obj = report.comercializadora
                cartera_data = get_cartera(_com_obj, anio)
            elif municipio and comercializadora and anio:
                _m = Municipio.query.filter(Municipio.nombre.ilike(municipio)).first()
                if _m:
                    _c = Comercializadora.query.filter_by(municipio_id=_m.id).filter(
                        Comercializadora.nombre.ilike(comercializadora)).first()
                    if _c:
                        _com_obj = _c
                        cartera_data = get_cartera(_c, anio)
            if _com_obj is not None and anio:
                _ag = _com_obj.analisis_general or {}
                if isinstance(_ag, dict):
                    acumulado = _ag.get(str(anio))
        except Exception:
            cartera_data = None
            acumulado = None
        from reports.word_engine import generar_word_especiales
        buf = generar_word_especiales(especiales_data, municipio=municipio, anio=anio, mes=mes,
                                      comercializadora=comercializadora,
                                      cartera_data=cartera_data, acumulado=acumulado)
        fname = f"Informe_Especiales_{municipio}_{comercializadora}_{anio}_{mes}.docx"
    else:
        from reports.word_engine import generar_word_general
        buf = generar_word_general(general_data, analisis_ejecutivo, municipio=municipio, anio=anio,
                                   mes=mes, comercializadora=comercializadora)
        fname = f"Analisis_IAP_{municipio}_{comercializadora}_{anio}_{mes}.docx"

    _auditar("descarga_word", f"{fname} (reporte #{report_id})")
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     as_attachment=True, download_name=fname)


# Borra un reporte del historial
@bp.route("/reporte/<int:report_id>/eliminar", methods=["POST"])
def eliminar_reporte(report_id):
    report = Report.query.get_or_404(report_id)
    _auditar("eliminar_reporte",
             f"{report.municipio_nombre} / {report.comercializadora_nombre} — {report.mes_nombre} {report.anio} (reporte #{report_id})")
    db.session.delete(report)
    db.session.commit()
    flash("Reporte eliminado correctamente.", "success")
    return redirect(url_for("main.historial"))


# ---- Clientes Especiales (gestión desde BD) ----

@bp.route("/clientes-especiales")
def clientes_especiales():
    from models import ClienteEspecial
    clientes = ClienteEspecial.query.filter_by(activo=True).order_by(
        ClienteEspecial.grupo, ClienteEspecial.nombre).all()
    return render_template("clientes_especiales.html", clientes=clientes)


@bp.route("/clientes-especiales/guardar", methods=["POST"])
def clientes_especiales_guardar():
    from models import ClienteEspecial
    id_cuenta = request.form.get("id_cuenta", "").strip()
    if not id_cuenta:
        flash("El ID de cuenta es obligatorio.", "danger")
        return redirect(url_for("main.clientes_especiales"))
    existente = ClienteEspecial.query.filter_by(id_cuenta=id_cuenta).first()
    if existente:
        existente.nombre = request.form.get("nombre", "").strip()
        existente.grupo = request.form.get("grupo", "").strip()
        existente.tarifa_min = float(request.form.get("tarifa_min") or 0)
        existente.consumo = float(request.form.get("consumo") or 0)
        existente.periodicidad = request.form.get("periodicidad", "Mensual")
        existente.activo = request.form.get("activo") == "1"
        flash("Cliente especial actualizado.", "success")
    else:
        nuevo = ClienteEspecial(
            id_cuenta=id_cuenta,
            nombre=request.form.get("nombre", "").strip(),
            grupo=request.form.get("grupo", "").strip(),
            tarifa_min=float(request.form.get("tarifa_min") or 0),
            consumo=float(request.form.get("consumo") or 0),
            periodicidad=request.form.get("periodicidad", "Mensual"),
            activo=True,
        )
        db.session.add(nuevo)
        flash("Cliente especial creado.", "success")
    db.session.commit()
    _auditar("guardar_cliente_especial", id_cuenta)
    return redirect(url_for("main.clientes_especiales"))


@bp.route("/clientes-especiales/eliminar/<int:cliente_id>", methods=["POST"])
def clientes_especiales_eliminar(cliente_id):
    from models import ClienteEspecial
    cliente = ClienteEspecial.query.get_or_404(cliente_id)
    db.session.delete(cliente)
    db.session.commit()
    _auditar("eliminar_cliente_especial", cliente.id_cuenta)
    flash("Cliente especial eliminado.", "success")
    return redirect(url_for("main.clientes_especiales"))


@bp.route("/clientes-especiales/seed", methods=["POST"])
def clientes_especiales_seed():
    """Carga la lista hardcodeada inicial si la tabla está vacía."""
    from models import ClienteEspecial
    if ClienteEspecial.query.count() > 0:
        flash("Ya existen clientes especiales en la base de datos.", "warning")
        return redirect(url_for("main.clientes_especiales"))
    from core.core import ESPECIALES
    for idc, nombre, grupo, tarifa, consumo, _fact, _rec, periodo in ESPECIALES:
        db.session.add(ClienteEspecial(
            id_cuenta=idc, nombre=nombre, grupo=grupo,
            tarifa_min=tarifa, consumo=consumo, periodicidad=periodo, activo=True,
        ))
    db.session.commit()
    _auditar("seed_clientes_especiales", f"{len(ESPECIALES)} clientes cargados")
    flash(f"{len(ESPECIALES)} clientes especiales cargados desde la lista inicial.", "success")
    return redirect(url_for("main.clientes_especiales"))
