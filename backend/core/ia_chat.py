# -*- coding: utf-8 -*-
"""Chat con los datos del sistema ("Pregúntale a la IA") — idea #3.

Dos piezas:

1. `guardar_resumen(report)` — saca los totales del informe y los guarda en
   la tabla `resumen_mes` (pocos bytes). Sin esto el chat tendría que
   descomprimir 33 MB (≈10 s y ~850 MB de RAM) por cada pregunta.

2. `responder(pregunta, historial, report_id)` — arma el contexto:
      * la tabla de TODOS los meses cargados (desde `resumen_mes`, barato)
      * los KPIs y el detalle por estrato del mes en pantalla
   y le pregunta a la IA (Gemini, tier gratis).

El historial de la conversación vive en el navegador y viaja completo en
cada petición (es corto); no se guarda en la base de datos.
"""
import json

from models import db


def guardar_resumen(report, fyr=None, fyr_orden=None):
    """Guarda/actualiza los totales del informe en `resumen_mes`.
    fyr/fyr_orden (tabla por estrato) son opcionales: si no vienen y el
    informe es EMSA, se calculan aquí (costa ~1,5 s, solo al guardar).
    Devuelve None si algo falla (nunca debe romper la carga)."""
    try:
        from datetime import datetime as _dt
        from models import ResumenMes
        datos = report.general_data
        if not datos:
            return None
        f = datos.get("f") or {}
        r = datos.get("r") or {}
        por_estrato = None

        if (fyr is None or fyr_orden is None) and _es_fyr(report):
            from core.fyr import FYR_ORDEN, fyr_agregar
            fyr = fyr_agregar(datos.get("facturacion"), datos.get("recaudo"))
            fyr_orden = list(FYR_ORDEN)
        if fyr and fyr_orden:
            filas = []
            for clave in fyr_orden:
                d = fyr.get(clave) or {}
                try:
                    filas.append({
                        "clasificacion": (clave.replace("Residencial – ", "")
                                          .replace("Residencial - ", "")),
                        "facturacion": float((d.get("fact") or [0, 0, 0])[2] or 0),
                        "recaudo": float((d.get("rec") or [0, 0, 0])[2] or 0),
                        "usuarios": float((d.get("n") or [0, 0, 0])[2] or 0),
                    })
                except (TypeError, ValueError, IndexError):
                    continue
            if filas:
                por_estrato = json.dumps(filas, ensure_ascii=False)

        fila = ResumenMes.query.get(report.id)
        valores = dict(
            municipio=report.municipio_nombre,
            comercializadora=report.comercializadora_nombre,
            anio=report.anio,
            mes=report.mes,
            facturacion=float(f.get("total_imp") or 0),
            recaudo=float(r.get("total_valor") or 0),
            valor_consumo=float(f.get("total_consumo") or 0),
            kwh=float(f.get("total_kwh") or 0),
            cuentas=float(f.get("cuentas") or r.get("cuentas") or 0),
            por_estrato=por_estrato,
        )
        if fila is None:
            db.session.add(ResumenMes(report_id=report.id, **valores))
        else:
            for clave, valor in valores.items():
                setattr(fila, clave, valor)
            fila.creado = _dt.utcnow()
        db.session.commit()
        return valores
    except Exception:
        db.session.rollback()
        return None


def _es_fyr(report):
    """Solo EMSA/Villavicencio maneja la tabla por estrato y clasificación."""
    return ((report.comercializadora_nombre or "").strip().lower() == "emsa"
            or (report.municipio_nombre or "").strip().lower() == "villavicencio")


def _tabla_meses(report_id):
    """Tabla de todos los meses cargados (mismo municipio/comercializadora)."""
    from models import Report, ResumenMes
    actual = Report.query.with_entities(
        Report.comercializadora_id).filter(Report.id == report_id).scalar()
    filas = (ResumenMes.query
             .join(Report, Report.id == ResumenMes.report_id)
             .filter(Report.comercializadora_id == actual)
             .order_by(ResumenMes.anio, ResumenMes.mes)
             .all())
    if not filas:
        return ""
    lineas = ["| Período | Facturación | Recaudo | % Recaudado | Cuentas |",
              "|---|---:|---:|---:|---:|"]
    for f in filas:
        fact = f.facturacion or 0
        rec = f.recaudo or 0
        pct = f"{rec / fact * 100:.1f}%".replace(".", ",") if fact else "n/d"
        lineas.append(f"| {f.mes}/{f.anio} | {_peso(fact)} | {_peso(rec)} | "
                      f"{pct} | {_num(f.cuentas)} |")
    return "\n".join(lineas)


def _peso(valor):
    try:
        return "$" + format(int(round(float(valor))), ",").replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def _num(valor):
    try:
        return format(int(round(float(valor))), ",").replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def contexto_chat(report):
    """Junta los datos con los que la IA puede responder preguntas.

    OJO: NO se toca report.general_data (850 MB y ~10 s). Todo sale de
    `resumen_mes`, que son unos pocos bytes por mes cargado.
    """
    bloques = []
    bloques.append("CONTEXTO DEL SISTEMA")
    bloques.append(f"Municipio en pantalla: {report.municipio_nombre}")
    bloques.append(f"Comercializadora: {report.comercializadora_nombre}")
    bloques.append(f"Período en pantalla: {report.mes_nombre} {report.anio}")

    tabla = _tabla_meses(report.id)
    if tabla:
        bloques.append("\nHISTORIAL DE MESES CARGADOS (este municipio y "
                       "comercializadora)\n" + tabla)
    else:
        bloques.append("\nNo hay resúmenes mensuales cargados todavía.")

    por_estrato = _tabla_estrato(report.id)
    if por_estrato:
        bloques.append("\nDESGLOSE DEL PERÍODO EN PANTALLA POR CLASIFICACIÓN "
                       "Y ESTRATO\n" + por_estrato)

    bloques.append("\nNOTA: los meses listados arriba son todos los "
                   "disponibles en el sistema. Si el usuario pregunta por "
                   "un mes o municipio que no aparece, responde que no hay "
                   "dato cargado (no estimes ni extrapolés).")
    return "\n".join(bloques)


def _tabla_estrato(report_id):
    """Desglose por estrato/clasificación del mes (JSON guardado)."""
    from models import ResumenMes
    fila = ResumenMes.query.get(report_id)
    if not fila or not fila.por_estrato:
        return ""
    try:
        filas = json.loads(fila.por_estrato)
    except (ValueError, TypeError):
        return ""
    if not filas:
        return ""
    lineas = ["| Clasificación | Facturación | Recaudo | Diferencia | "
              "Usuarios |", "|---|---:|---:|---:|---:|"]
    for e in filas:
        lineas.append(f"| {e.get('clasificacion')} | "
                      f"{_peso(e.get('facturacion'))} | "
                      f"{_peso(e.get('recaudo'))} | "
                      f"{_peso((e.get('recaudo') or 0) - (e.get('facturacion') or 0))} | "
                      f"{_num(e.get('usuarios'))} |")
    return "\n".join(lineas)


def armar_historial(historial, limite=8):
    """Convierte el historial del navegador en texto para el prompt."""
    partes = []
    for msg in (historial or [])[-limite:]:
        rol = "USUARIO" if msg.get("rol") == "usuario" else "ANALISTA"
        texto = str(msg.get("texto") or "").strip()[:500]
        if texto:
            partes.append(f"{rol}: {texto}")
    return "\n".join(partes)


def responder(pregunta, historial, contexto):
    """Devuelve (respuesta, modelo_usado)."""
    from core.ia_analisis import _INSTRUCCIONES_CHAT, llamar_ia
    bloques = []
    hist = armar_historial(historial)
    if hist:
        bloques.append("CONVERSACIÓN HASTA AHORA:\n" + hist)
    bloques.append("DATOS DISPONIBLES:\n" + contexto)
    bloques.append(f"PREGUNTA ACTUAL DEL USUARIO:\n{pregunta.strip()[:800]}")
    return llamar_ia("\n\n".join(bloques), instrucciones=_INSTRUCCIONES_CHAT)


def resumen_json():
    """Todos los resúmenes cargados, para usarlos como contexto o en tablas."""
    from models import ResumenMes
    return [{"municipio": f.municipio, "comercializadora": f.comercializadora,
             "anio": f.anio, "mes": f.mes, "facturacion": f.facturacion,
             "recaudo": f.recaudo, "cuentas": f.cuentas}
            for f in ResumenMes.query.order_by(ResumenMes.anio,
                                               ResumenMes.mes).all()]
