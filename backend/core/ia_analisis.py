# -*- coding: utf-8 -*-
"""Análisis asistido por IA (Gemini gratis, Groq gratis como respaldo,
Claude pago solo si se habilita explícitamente).

Cadena de proveedores: Gemini -> Groq -> (Claude si CLAUDE_AS_FALLBACK=1).
Cada proveedor prueba varios modelos en orden y recuerda cuál funcionó.

Cómo funciona:
  1. `armar_contexto(report)` recoge SOLO cifras ya calculadas por la app
     (KPIs, totales por estrato y clasificación, variación vs mes anterior).
  2. `generar_analisis(contexto)` envía esas cifras a la cadena y devuelve el
     texto con Resumen / Hallazgos / Alertas / Recomendaciones.

Reglas de seguridad (ver docs/ideas-ia.md):
  * NUNCA se envían las filas detalle de cuentas (~235 mil), solo totales.
  * A la IA se le prohíbe inventar o recalcular cifras.
  * Las API keys viven en .env y jamás se suben a git.
  * Si todos los proveedores fallan, se devuelve un mensaje claro y la
    página NO se rompe.
"""
import json
import os
import urllib.error
import urllib.request

# Carpeta del proyecto (backend/) para leer el .env
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Modelos de Gemini en orden de preferencia. Si el primero falla (retirado,
# saturado, timeout), se prueba el siguiente. El nombre se puede sobreescribir
# con GEMINI_MODEL en el .env. Lista verificada contra la API el 29/10/2026:
#   - gemini-2.5-flash / 2.5-flash-lite ya NO existen para usuarios nuevos.
#   - 3.6-flash y flash-lite-latest responden bien en el tier gratis.
_MODELOS_GEMINI = [
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

# Modelos de Groq (tier gratis, OpenAI-compatible). Se usan como respaldo
# automático si Gemini falla por cuota o error. llama-3.3-70b es el de
# mejor calidad; el 8b es el más rápido.
_MODELOS_GROQ = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
]

# El último modelo que respondió bien por proveedor se intenta primero en la
# siguiente llamada (evita esperar timeouts de modelos que ya sabemos que fallan).
_modelo_gemini_activo = None
_modelo_groq_activo = None

_URL_PLANTILLA = ("https://generativelanguage.googleapis.com/v1beta/models/"
                  "{modelo}:generateContent")

_INSTRUCCIONES = (
    "Eres analista senior de interventoría de alumbrado público en Colombia.\n"
    "Redacta en español formal, sin emojis, orientado a un interventor.\n"
    "REGLAS ESTRICTAS:\n"
    "1. Usa EXCLUSIVAMENTE las cifras entregadas en los datos. NO inventes "
    "números ni hagas cálculos propios que no estén dados.\n"
    "2. Si un dato falta, indícalo como 'no disponible'.\n"
    "3. Cita los valores con su cifra exacta y el signo $ cuando aplique.\n"
    "4. Máximo 350 palabras.\n"
    "Devuelve SOLO el texto del análisis, sin preámbulo ni saludo, con "
    "estos cuatro encabezados en mayúsculas:\n"
    "RESUMEN EJECUTIVO\nHALLAZGOS\nALERTAS\nRECOMENDACIONES\n"
)


def _cargar_clave(nombre):
    """Lee una API key (NOMBRE) desde variables de entorno o desde backend/.env."""
    valor = (os.environ.get(nombre) or "").strip()
    if valor:
        return valor
    ruta = os.path.join(_BASE, ".env")
    try:
        with open(ruta, "r", encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, _, valor = linea.partition("=")
                if clave.strip() == nombre:
                    return valor.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def cargar_clave():
    """Compatibilidad: devuelve la key de Gemini."""
    return _cargar_clave("GEMINI_API_KEY")


def _modelo_elegido():
    return (os.environ.get("GEMINI_MODEL") or "").strip()


def _modelo_groq_elegido():
    return (os.environ.get("GROQ_MODEL") or "").strip()


def _llamar_groq(prompt, clave, timeout=45):
    """Llama a la API de Groq (OpenAI-compatible, tier gratis)."""
    global _modelo_groq_activo
    modelos = ([_modelo_groq_elegido()] if _modelo_groq_elegido() else [])
    if _modelo_groq_activo:
        modelos.append(_modelo_groq_activo)
    modelos += _MODELOS_GROQ
    vistos, ultimo_error = set(), None
    url = "https://api.groq.com/openai/v1/chat/completions"
    for modelo in modelos:
        if not modelo or modelo in vistos:
            continue
        vistos.add(modelo)
        cuerpo = json.dumps({
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 4000,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=cuerpo, method="POST",
            headers={"Content-Type": "application/json",
                    "Authorization": "Bearer " + clave})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                salida = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            ultimo_error = f"HTTP {exc.code}"
            try:
                detalle = json.loads(exc.read().decode("utf-8"))
                ultimo_error = (detalle.get("error", {}) or {}).get(
                    "message", ultimo_error)
            except Exception:
                pass
            # 429 (cuota) o 404 (modelo retirado): se prueba el siguiente
            continue
        except Exception as exc:
            ultimo_error = str(exc)
            continue
        try:
            texto = salida["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            ultimo_error = "Respuesta inesperada de la API"
            continue
        if texto and texto.strip():
            _modelo_groq_activo = modelo
            return texto.strip(), modelo
        ultimo_error = "Respuesta vacía"
    raise RuntimeError(ultimo_error or "sin respuesta de Groq")


def _llamar_claude(prompt, clave, timeout=45):
    """Llama a la API de Anthropic (Claude Haiku, pago). Uso opt-in."""
    modelo = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5").strip()
    cuerpo = json.dumps({
        "model": modelo,
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    url = "https://api.anthropic.com/v1/messages"
    req = urllib.request.Request(
        url, data=cuerpo, method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": clave,
            "anthropic-version": "2023-06-01",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            salida = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        msg = f"HTTP {exc.code}"
        try:
            detalle = json.loads(exc.read().decode("utf-8"))
            msg = (detalle.get("error", {}) or {}).get("message", msg)
        except Exception:
            pass
        raise RuntimeError(msg)
    except Exception as exc:
        raise RuntimeError(str(exc))
    try:
        bloques = salida.get("content") or []
        texto = "".join(b.get("text", "") for b in bloques if b.get("type") == "text")
    except (KeyError, TypeError):
        raise RuntimeError("Respuesta inesperada de la API")
    if not texto.strip():
        raise RuntimeError("Respuesta vacía")
    return texto.strip(), modelo


def _llamar_con_cadena(prompt, timeout=45):
    """Cadena de proveedores: Gemini (gratis) -> Groq (gratis) -> Claude
    (solo si CLAUDE_AS_FALLBACK=1 y hay key). Lanza RuntimeError si todos
    fallan o no hay ninguno configurado."""
    errores = []
    # 1. Gemini
    clave_g = _cargar_clave("GEMINI_API_KEY")
    if clave_g:
        try:
            return _llamar_gemini(prompt, clave_g, timeout)
        except RuntimeError as exc:
            errores.append(f"Gemini: {exc}")
    # 2. Groq (respaldo gratuito)
    clave_q = _cargar_clave("GROQ_API_KEY")
    if clave_q:
        try:
            return _llamar_groq(prompt, clave_q, timeout)
        except RuntimeError as exc:
            errores.append(f"Groq: {exc}")
    # 3. Claude (solo si se habilita explícitamente como respaldo)
    if os.environ.get("CLAUDE_AS_FALLBACK", "").strip().lower() in ("1", "true", "yes", "si", "sí"):
        clave_c = _cargar_clave("ANTHROPIC_API_KEY")
        if clave_c:
            try:
                return _llamar_claude(prompt, clave_c, timeout)
            except RuntimeError as exc:
                errores.append(f"Claude: {exc}")
    if not errores:
        raise RuntimeError(
            "Ningún proveedor de IA configurado. Añada GEMINI_API_KEY o "
            "GROQ_API_KEY en backend/.env (ver docs/ideas-ia.md).")
    raise RuntimeError(" | ".join(errores))


def _fmt(valor):
    """Cifra grande en formato colombiano: $1.245.000.000."""
    try:
        return "$" + format(int(round(float(valor))), ",").replace(",", ".")
    except (TypeError, ValueError):
        return "no disponible"


def _fmt_n(valor):
    """Número entero con separador de miles."""
    try:
        return format(int(round(float(valor))), ",").replace(",", ".")
    except (TypeError, ValueError):
        return "no disponible"


def _fmt_pct(valor):
    try:
        return f"{float(valor):+.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "no disponible"


def _mes_anterior(report):
    """Devuelve el reporte del mes inmediatamente anterior (misma comerc.)."""
    from models import Report
    anio, mes = report.anio, report.mes
    if mes == 1:
        mes, anio = 12, anio - 1
    else:
        mes -= 1
    return (Report.query
            .filter(Report.comercializadora_id == report.comercializadora_id,
                    Report.anio == anio, Report.mes == mes)
            .first())


def _tabla_fyr(fyr, fyr_orden):
    """Totales por estrato y clasificación (solo si hay contexto FYR)."""
    if not fyr or not fyr_orden:
        return ""
    lineas = ["| Clasificación | Facturación | Recaudo | Diferencia | Usuarios |",
              "|---|---:|---:|---:|---:|"]
    for clave in fyr_orden:
        datos = fyr.get(clave) or {}
        try:
            fact = float((datos.get("fact") or [0, 0, 0])[2] or 0)
            rec = float((datos.get("rec") or [0, 0, 0])[2] or 0)
            n = float((datos.get("n") or [0, 0, 0])[2] or 0)
        except (TypeError, ValueError, IndexError):
            continue
        etiqueta = (clave.replace("Residencial – ", "")
                   .replace("Residencial - ", ""))
        lineas.append(f"| {etiqueta} | {_fmt(fact)} | {_fmt(rec)} | "
                      f"{_fmt(rec - fact)} | {_fmt_n(n)} |")
    return "\n".join(lineas)


def armar_contexto(report, fyr=None, fyr_orden=None):
    """Junta las cifras del informe para enviarlas a la IA."""
    datos = report.general_data or {}
    f = datos.get("f") or {}
    r = datos.get("r") or {}
    prev = _mes_anterior(report)

    fact = f.get("total_imp") or 0
    rec = r.get("total_valor") or 0
    cons = f.get("total_consumo") or 0
    kwh = f.get("total_kwh") or 0
    cuentas = f.get("cuentas") or r.get("cuentas") or 0

    bloques = []
    bloques.append("CONTEXTO DEL INFORME")
    bloques.append(f"Municipio: {report.municipio_nombre}")
    bloques.append(f"Comercializadora: {report.comercializadora_nombre}")
    bloques.append(f"Período: {report.mes_nombre} de {report.anio}")

    bloques.append("\nKPIs DEL PERÍODO")
    bloques.append(f"- Facturación impuesto de alumbrado público: {_fmt(fact)}")
    bloques.append(f"- Recaudo: {_fmt(rec)}")
    bloques.append(f"- Diferencia (facturado - recaudado): {_fmt(fact - rec)}")
    bloques.append(f"- % Recaudado sobre facturado: "
                   f"{_fmt_pct(100.0 * rec / fact) if fact else 'no disponible'}")
    bloques.append(f"- Valor consumo de energía: {_fmt(cons)}")
    bloques.append(f"- Energía facturada: {_fmt_n(kwh)} kWh")
    bloques.append(f"- Cuentas / usuarios: {_fmt_n(cuentas)}")

    # Comparación con el mes anterior (si existe reporte previo)
    if prev is not None and prev.general_data:
        pf = (prev.general_data.get("f") or {}).get("total_imp") or 0
        pr = (prev.general_data.get("r") or {}).get("total_valor") or 0
        if pf or pr:
            bloques.append(f"\nCOMPARACIÓN VS MES ANTERIOR "
                           f"({prev.mes_nombre} {prev.anio})")
            bloques.append(f"- Facturación: {_fmt(pf)} "
                           f"({_fmt_pct(100.0 * (fact - pf) / pf) if pf else 'n/d'})")
            bloques.append(f"- Recaudo: {_fmt(pr)} "
                           f"({_fmt_pct(100.0 * (rec - pr) / pr) if pr else 'n/d'})")

    # Estadísticas generales de la base (calidad/dimensiones)
    est = datos.get("estad_general") or {}
    if est:
        bloques.append("\nDIMENSIÓN DE LA BASE")
        for clave in ("Total registros base original", "Usuarios únicos (ID de cuenta)"):
            if clave in est:
                bloques.append(f"- {clave}: {_fmt_n(est[clave])}")

    tabla = _tabla_fyr(fyr, fyr_orden)
    if tabla:
        bloques.append("\nTOTALES POR CLASIFICACIÓN Y ESTRATO")
        bloques.append(tabla)

    return "\n".join(bloques)


def _llamar_gemini(prompt, clave, timeout=45):
    """Llama a la API de Gemini con urllib (sin dependencias externas)."""
    global _modelo_gemini_activo
    modelos = ([_modelo_elegido()] if _modelo_elegido() else [])
    if _modelo_gemini_activo:
        modelos.append(_modelo_gemini_activo)
    modelos += _MODELOS_GEMINI
    vistos, ultimo_error = set(), None
    # maxOutputTokens alto: los modelos "piensan" antes de responder y se
    # comen los tokens de salida (con 900 el texto salía cortado a media
    # respuesta, finishReason=MAX_TOKENS). thinkingBudget 0 = respuesta
    # directa, más rápida y más barata en el tier gratis.
    cuerpo_con_pensamiento = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4000,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode("utf-8")
    cuerpo_sin_pensamiento = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4000},
    }).encode("utf-8")

    for modelo in modelos:
        if not modelo or modelo in vistos:
            continue
        vistos.add(modelo)
        url = _URL_PLANTILLA.format(modelo=modelo) + f"?key={clave}"
        # Se intenta primero sin "pensar"; si el modelo no lo acepta (400),
        # se reintenta el mismo modelo con la configuración completa.
        for cuerpo in (cuerpo_con_pensamiento, cuerpo_sin_pensamiento):
            req = urllib.request.Request(
                url, data=cuerpo, method="POST",
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    salida = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                ultimo_error = f"HTTP {exc.code}"
                try:
                    detalle = json.loads(exc.read().decode("utf-8"))
                    ultimo_error = (detalle.get("error", {}) or {}).get(
                        "message", ultimo_error)
                except Exception:
                    pass
                # 400 por la configuración de "pensamiento": se reintenta
                # el mismo modelo sin ella. Cualquier otro error: el siguiete.
                if not (exc.code == 400 and "thinking" in ultimo_error.lower()):
                    break
                continue
            except Exception as exc:  # red, timeout, etc.
                ultimo_error = str(exc)
                break

            try:
                partes = salida["candidates"][0]["content"]["parts"]
                texto = "".join((p.get("text") or "") for p in partes)
            except (KeyError, IndexError, TypeError):
                ultimo_error = "Respuesta inesperada de la API"
                break
            if texto.strip():
                _modelo_gemini_activo = modelo  # se intentará primero la próxima vez
                return texto.strip(), modelo
            ultimo_error = "Respuesta vacía"
            break

    raise RuntimeError(ultimo_error or "sin respuesta")


def generar_analisis(contexto):
    """Devuelve (texto, modelo_usado). Lanza RuntimeError si ningún
    proveedor responde."""
    prompt = f"{_INSTRUCCIONES}\n---\nDATOS DEL INFORME:\n{contexto}"
    return _llamar_con_cadena(prompt)


# Instrucciones para las conclusiones que se insertan en el Word (idea #4)
_INSTRUCCIONES_CONCLUSIONES = (
    "Eres analista senior de interventoría de alumbrado público en Colombia.\n"
    "Redacta las CONCLUSIONES Y RECOMENDACIONES del informe mensual, en "
    "español formal de interventoría, sin emojis, en 2 párrafos cortos "
    "(máximo 220 palabras en total).\n"
    "REGLAS ESTRICTAS:\n"
    "1. Usa EXCLUSIVAMENTE las cifras entregadas. NO inventes números ni "
    "hagas cálculos propios.\n"
    "2. Cierra siempre con cifras exactas y el signo $ cuando aplique.\n"
    "3. Termina con una recomendación concreta y accionable.\n"
    "Devuelve SOLO el texto plano (sin encabezados, sin astericos, sin "
    "numeración), listo para insertarse como párrafo de un documento Word.\n"
)


def generar_conclusiones(contexto):
    """Conclusiones para el Word. Devuelve (texto, modelo_usado)."""
    prompt = f"{_INSTRUCCIONES_CONCLUSIONES}\n---\nDATOS DEL INFORME:\n{contexto}"
    return _llamar_con_cadena(prompt)


# Instrucciones para explicar una cifra en lenguaje llano (idea #5)
_INSTRUCCIONES_KPI = (
    "Eres analista de interventoría de alumbrado público en Colombia y "
    "explicas cifras a personas sin formación contable.\n"
    "Explica la CIFRA A EXPLICAR en lenguaje sencillo y cotidiano, en "
    "máximo 70 palabras (2 o 3 frases), sin emojis y sin tecnicismos.\n"
    "REGLAS ESTRICTAS:\n"
    "1. Usa SOLO las cifras entregadas; no inventes ni recalcules otras.\n"
    "2. Da un ejemplo proporcional cuando ayude (por ejemplo: 'de cada "
    "$100 facturados, $95 se recaudaron').\n"
    "3. Di en una frase si el resultado es bueno, normal o preocupante y "
    "por qué.\n"
    "4. Devuelve SOLO el texto plano, sin encabezados ni viñetas.\n"
)


# Instrucciones para el chat con los datos (idea #3)
_INSTRUCCIONES_CHAT = (
    "Eres el analista de datos del Sistema de Informes F&R de interventoría "
    "de alumbrado público en Colombia.\n"
    "Respondes en español formal, sin emojis, de forma breve (máximo 150 "
    "palabras) y con las cifras exactas de los datos entregados.\n"
    "REGLAS ESTRICTAS:\n"
    "1. Usa EXCLUSIVAMENTE los datos entregados. NO inventes cifras ni hagas "
    "cálculos que no se puedan deducir de ellos.\n"
    "2. Si el dato pedido no está en los datos, responde exactamente: "
    "'No tengo ese dato disponible. Solo puedo responder con la información "
    "del período y los meses cargados en el sistema.'\n"
    "3. Cuando cierres una cifra, usa el signo $ y el formato colombiano.\n"
    "4. Si te preguntan por meses o municipios que no aparecen, dilo "
    "claramente en vez de estimar.\n"
)


def llamar_ia(contexto, instrucciones=None):
    """Llamada genérica a la IA. Devuelve (texto, modelo_usado)."""
    prompt = f"{instrucciones or _INSTRUCCIONES}\n---\nDATOS:\n{contexto}"
    return _llamar_con_cadena(prompt)
