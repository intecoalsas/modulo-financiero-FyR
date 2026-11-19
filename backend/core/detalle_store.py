# -*- coding: utf-8 -*-
"""Detalle de cuentas precalculado y troceado en la base de datos.

Problema que resuelve: la tabla "Detalle de cuentas" del informe general
necesitaba el blob general_data completo (~35 MB comprimido, ~235 mil
filas en EMSA). Cargarlo costaba ~1 GB de RAM y varios segundos de CPU por
petición: en Render (512 MB, CPU compartida) el proceso se reiniciaba o se
bloqueaba y TODA la interfaz se volvía lenta.

Ahora, al guardar un informe, la unión facturación+recaudo se hace UNA vez
y se guarda en la tabla detalle_bloques:

* bloques de TAM filas (lista de listas): una página = 1 o 2 bloques chicos.
* una columna completa por campo, ya como texto: filtros y panel tipo Excel
  solo cargan las columnas que filtran (unos cientos de KB), nunca todo.

Así ninguna petición de la página toca general_data.
"""
import base64
import gzip
import io
import itertools
import json
import os
import re
import sys
import threading
import time
import zlib
from collections import OrderedDict

TAM = 1000  # filas por bloque (= tamaño de página por defecto del frontend)

CAMPOS_CUENTAS = [None, "Id_cliente", "Nombre", "Clase", "Sector",
                  "ImpuestoAP", "Consumo$", "ConsumokWh", "ValorAP"]


# --------------------------------------------------------------------------- #
# Unión facturación + recaudo (una fila por cuenta)
# --------------------------------------------------------------------------- #
def unir_cuentas(facturacion, recaudo):
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


def texto_filtro(v):
    """Texto con el que se compara un valor en filtros y conteos (el mismo
    criterio que se usaba sobre las filas: str(valor or ""))."""
    return str(v or "")


def _comprimir(obj):
    texto = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    return base64.b64encode(gzip.compress(texto.encode("utf-8"), 6)).decode("ascii")


def _descomprimir(texto):
    return json.loads(gzip.decompress(base64.b64decode(texto)).decode("utf-8"))


# --------------------------------------------------------------------------- #
# Cachés chicas en memoria (1 proceso). Columnas: ~1-20 MB cada una en RAM.
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_meta_cache = {}                 # (report_id, tipo) -> meta | False
_col_cache = OrderedDict()       # (report_id, tipo, idx) -> [str]
_idx_cache = OrderedDict()       # (report_id, tipo, clave_filtro) -> [int]
_MAX_COLS = 6
_MAX_IDX = 12


def invalidar(report_id=None):
    with _lock:
        if report_id is None:
            _meta_cache.clear()
            _col_cache.clear()
            _idx_cache.clear()
            return
        for cache in (_meta_cache, _col_cache, _idx_cache):
            for k in [k for k in cache if k[0] == report_id]:
                cache.pop(k, None)


def _lru_put(cache, clave, valor, maximo):
    cache[clave] = valor
    cache.move_to_end(clave)
    while len(cache) > maximo:
        cache.popitem(last=False)


# --------------------------------------------------------------------------- #
# Escritura
# --------------------------------------------------------------------------- #
def borrar(report_ids, tipo=None):
    """Borra los bloques de uno o varios informes (sin commit)."""
    from models import db, DetalleBloque
    if not isinstance(report_ids, (list, tuple, set)):
        report_ids = [report_ids]
    report_ids = list(report_ids)
    if not report_ids:
        return
    q = DetalleBloque.query.filter(DetalleBloque.report_id.in_(report_ids))
    if tipo:
        q = q.filter(DetalleBloque.tipo == tipo)
    q.delete(synchronize_session=False)
    for rid in report_ids:
        invalidar(rid)


def guardar_cuentas(report_id, facturacion, recaudo):
    """Une facturación+recaudo (ya en memoria, al cargar un informe) y guarda
    el detalle troceado. Hace commit. Devuelve el total de cuentas."""
    filas = unir_cuentas(facturacion, recaudo)
    nombres = [c for c in CAMPOS_CUENTAS if c]
    return guardar_filas(report_id, "cuentas",
                         ([r.get(c) for c in nombres] for r in filas),
                         CAMPOS_CUENTAS)


class _ColumnaGz:
    """Columna de textos comprimida a medida que llega (gzip en streaming):
    nunca se tienen las 235 mil cadenas juntas en memoria."""

    def __init__(self):
        self._z = zlib.compressobj(6, zlib.DEFLATED, 31)  # 31 = formato gzip
        self._partes = []
        self._vacia = True

    def agregar(self, textos):
        if not textos:
            return
        cuerpo = json.dumps(textos, ensure_ascii=False, separators=(",", ":"))[1:-1]
        cuerpo = ("[" if self._vacia else ",") + cuerpo
        self._vacia = False
        self._partes.append(self._z.compress(cuerpo.encode("utf-8")))

    def cerrar(self):
        fin = b"[]" if self._vacia else b"]"
        self._partes.append(self._z.compress(fin))
        self._partes.append(self._z.flush())
        return base64.b64encode(b"".join(self._partes)).decode("ascii")


def guardar_filas(report_id, tipo, filas, campos):
    """Guarda filas (iterable de listas en el orden de los campos útiles)
    en bloques + columnas. Memoria acotada: procesa de a TAM filas."""
    from models import db, DetalleBloque
    utiles = [i for i, c in enumerate(campos) if c]
    tabla = DetalleBloque.__table__

    borrar(report_id, tipo)
    db.session.commit()

    columnas = {i: _ColumnaGz() for i in utiles}
    lote = []
    total = 0
    n = 0
    it = iter(filas)
    while True:
        trozo = list(itertools.islice(it, TAM))
        if not trozo:
            break
        # Valores tal como quedan tras un viaje por JSON (lo mismo que se
        # veía al leer general_data de la BD): fechas/numpy -> str, etc.
        trozo = json.loads(json.dumps(trozo, ensure_ascii=False, default=str))
        for pos, i in enumerate(utiles):
            columnas[i].agregar([texto_filtro(f[pos]) for f in trozo])
        total += len(trozo)
        lote.append({"report_id": report_id, "tipo": tipo, "parte": "fila",
                     "n": n, "datos": _comprimir(trozo)})
        n += 1
        if len(lote) >= 25:
            db.session.execute(tabla.insert(), lote)
            lote = []
    if lote:
        db.session.execute(tabla.insert(), lote)
    for i, col in columnas.items():
        db.session.execute(tabla.insert(), [{
            "report_id": report_id, "tipo": tipo, "parte": "col", "n": i,
            "datos": col.cerrar()}])
    # La meta va al final: si algo falla a mitad, el informe sigue marcado
    # como pendiente (no queda un detalle a medias "válido").
    db.session.execute(tabla.insert(), [{
        "report_id": report_id, "tipo": tipo, "parte": "meta", "n": 0,
        "datos": json.dumps({"total": total, "tam": TAM, "campos": list(campos)})}])
    db.session.commit()
    invalidar(report_id)
    return total


# --------------------------------------------------------------------------- #
# Troceado de informes YA guardados, leyendo el blob por partes
# --------------------------------------------------------------------------- #
# json.loads del blob completo de EMSA (~360 MB de texto) necesita ~1 GB de
# RAM: imposible en Render. Aquí el texto se descomprime de a 1 MB y solo se
# decodifica una fila de facturación/recaudo a la vez (raw_decode, en C).
_WS = re.compile(r"[ \t\n\r]*")


class _LectorJson:
    def __init__(self, archivo_texto):
        self._f = archivo_texto
        self.buf = ""
        self.pos = 0
        self.eof = False
        self._dec = json.JSONDecoder()

    def _llenar(self, minimo=1 << 20):
        while not self.eof and len(self.buf) - self.pos < minimo:
            if self.pos > (4 << 20):
                self.buf = self.buf[self.pos:]
                self.pos = 0
            trozo = self._f.read(1 << 20)
            if not trozo:
                self.eof = True
            else:
                self.buf += trozo

    def ver(self):
        self._llenar()
        self.pos = _WS.match(self.buf, self.pos).end()
        if self.pos >= len(self.buf):
            raise ValueError("JSON incompleto")
        return self.buf[self.pos]

    def esperar(self, ch):
        if self.ver() != ch:
            raise ValueError(f"se esperaba {ch!r} en el JSON")
        self.pos += 1

    def valor(self):
        self.ver()
        extra = 1 << 20
        while True:
            try:
                v, fin = self._dec.raw_decode(self.buf, self.pos)
                self.pos = fin
                return v
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self._llenar(len(self.buf) - self.pos + extra)
                extra *= 2

    def elementos(self):
        """Recorre una lista elemento por elemento."""
        self.esperar("[")
        if self.ver() == "]":
            self.pos += 1
            return
        while True:
            yield self.valor()
            c = self.ver()
            self.pos += 1
            if c == "]":
                return
            if c != ",":
                raise ValueError("lista JSON mal formada")

    def saltar(self):
        """Salta un valor sin construirlo entero (listas y dicts por partes)."""
        c = self.ver()
        if c == "[":
            for _ in self.elementos():
                pass
        elif c == "{":
            self.pos += 1
            if self.ver() == "}":
                self.pos += 1
                return
            while True:
                self.valor()
                self.esperar(":")
                self.saltar()
                c = self.ver()
                self.pos += 1
                if c == "}":
                    return
        else:
            self.valor()


def _recorrer_listas(gz_bytes, quiero):
    """Llama quiero[clave](fila) por cada fila de las listas de primer nivel
    pedidas, en el orden en que aparecen. Devuelve las claves vistas. Deja
    de leer en cuanto ya vio todas (no descomprime el resto)."""
    texto = io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(gz_bytes)),
                             encoding="utf-8")
    lector = _LectorJson(texto)
    vistas = []
    lector.esperar("{")
    if lector.ver() == "}":
        return vistas
    while True:
        clave = lector.valor()
        lector.esperar(":")
        if clave in quiero and lector.ver() == "[":
            fn = quiero[clave]
            for fila in lector.elementos():
                if isinstance(fila, dict):
                    fn(fila)
            vistas.append(clave)
            if len(vistas) == len(quiero):
                return vistas
        else:
            lector.saltar()
        c = lector.ver()
        lector.pos += 1
        if c == "}":
            return vistas


def unir_cuentas_desde_blob(gz_bytes):
    """Lo mismo que unir_cuentas(general_data["facturacion"], ["recaudo"])
    pero leyendo el blob gzip por partes. Devuelve listas en el orden de
    CAMPOS_CUENTAS (sin el None)."""
    base = {}
    intern = sys.intern

    def _txt(v):
        return intern(v) if isinstance(v, str) else v

    def fact(r):
        k = str(r.get("Id_cliente"))
        b = base.get(k)
        if b is None:
            b = base[k] = [r.get("Id_cliente"), r.get("Nombre"), _txt(r.get("Clase")),
                           _txt(r.get("Sector")), 0.0, 0.0, 0.0, 0.0]
        b[4] = float(b[4] or 0) + float(r.get("ImpuestoAP") or 0)
        b[5] = float(b[5] or 0) + float(r.get("Consumo$") or 0)
        b[6] = float(b[6] or 0) + float(r.get("ConsumokWh") or 0)

    def rec(r):
        k = str(r.get("Id_cliente"))
        b = base.get(k)
        if b is None:
            b = base[k] = [r.get("Id_cliente"), r.get("Nombre"), _txt(r.get("Clase")),
                           _txt(r.get("Sector")), 0.0, 0.0, 0.0, 0.0]
        if not b[1]:
            b[1] = r.get("Nombre")
        if not b[2]:
            b[2] = _txt(r.get("Clase"))
        if not b[3]:
            b[3] = _txt(r.get("Sector"))
        b[7] = float(b[7] or 0) + float(r.get("ValorAP") or 0)

    vistas = _recorrer_listas(gz_bytes, {"facturacion": fact, "recaudo": rec})
    if vistas and vistas[0] == "recaudo" and "facturacion" in vistas:
        # Orden raro (recaudo antes): se repite en el orden correcto para
        # que el resultado sea idéntico a unir_cuentas
        base.clear()
        _recorrer_listas(gz_bytes, {"facturacion": fact})
        _recorrer_listas(gz_bytes, {"recaudo": rec})
    return list(base.values())


def _blob_gzip(report_id):
    """Bytes gzip del general_data tal como está en la BD (sin pasar por
    JsonComprimido, que haría json.loads de todo)."""
    from sqlalchemy import text
    from models import db
    fila = db.session.execute(
        text("SELECT general_data FROM reports WHERE id = :i"), {"i": report_id}
    ).first()
    crudo = fila[0] if fila else None
    if not crudo:
        return None
    if isinstance(crudo, bytes):
        crudo = crudo.decode("ascii", "replace")
    try:
        datos = base64.b64decode(crudo, validate=True)
        if datos[:2] == b"\x1f\x8b":
            return datos
    except Exception:
        pass
    # Datos antiguos guardados sin comprimir: se comprimen para leerlos igual
    return gzip.compress(crudo.encode("utf-8"), 1)


def trocear_desde_bd(report_id):
    """Genera el detalle troceado de un informe ya guardado. Devuelve el
    total de cuentas, o None si el informe no tiene detalle."""
    gz = _blob_gzip(report_id)
    if gz is None:
        return None
    filas = unir_cuentas_desde_blob(gz)
    del gz
    return guardar_filas(report_id, "cuentas", filas, CAMPOS_CUENTAS)


# --------------------------------------------------------------------------- #
# Migración automática en segundo plano (en el propio servidor, sin PC)
# --------------------------------------------------------------------------- #
_mig_lock = threading.Lock()
_mig_evento = threading.Event()
_mig_prioridad = []      # ids pedidos por la página: van primero
_mig_fallidos = {}       # id -> mensaje de error (no se reintenta en bucle)
_mig_en_curso = {"id": None}
_mig_hilo = {"t": None}


def estado_pendiente(report_id):
    """'preparando' o 'error' para un informe sin bloques."""
    if report_id in _mig_fallidos:
        return "error"
    return "preparando"


def pedir(report_id):
    """La página pidió un informe sin bloques: pasa al frente de la cola."""
    with _mig_lock:
        if report_id not in _mig_prioridad and report_id != _mig_en_curso["id"]:
            _mig_prioridad.insert(0, report_id)
    _mig_evento.set()


def _pendientes():
    from sqlalchemy import text
    from models import db
    filas = db.session.execute(text(
        "SELECT id FROM reports WHERE general_data IS NOT NULL "
        "AND (detalle_purged IS NULL OR detalle_purged = 0) "
        "AND id NOT IN (SELECT report_id FROM detalle_bloques "
        "               WHERE tipo = 'cuentas' AND parte = 'meta') "
        "ORDER BY updated_at DESC")).all()
    return [f[0] for f in filas]


def _siguiente(pendientes):
    with _mig_lock:
        while _mig_prioridad:
            rid = _mig_prioridad.pop(0)
            if rid in pendientes:
                return rid
    for rid in pendientes:
        if rid not in _mig_fallidos:
            return rid
    return None


def _trabajo(app, espera_inicial):
    import gc
    from models import db
    time.sleep(espera_inicial)
    while True:
        rid = None
        try:
            with app.app_context():
                pendientes = _pendientes()
                rid = _siguiente(pendientes)
                if rid is None:
                    db.session.remove()
                    _mig_evento.clear()
                    _mig_evento.wait(30 * 60)  # revisa cada 30 min o al pedirlo
                    continue
                _mig_en_curso["id"] = rid
                t0 = time.time()
                total = trocear_desde_bd(rid)
                print(f"Detalle troceado: informe {rid}, {total} cuentas "
                      f"en {time.time() - t0:.0f}s")
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            if rid is not None:
                _mig_fallidos[rid] = str(exc)[:300]
            print(f"Detalle troceado: falló el informe {rid}: {exc}")
            try:
                with app.app_context():
                    db.session.rollback()
                    db.session.remove()
            except Exception:
                pass
        finally:
            _mig_en_curso["id"] = None
            gc.collect()
        time.sleep(1)


def iniciar_migracion(app, espera_inicial=20):
    """Arranca (una vez) el hilo que trocea los informes viejos. Se puede
    apagar con DETALLE_MIGRAR_AUTO=0."""
    if os.environ.get("INFORMES_TEST") or os.environ.get("DETALLE_MIGRAR_AUTO", "1") == "0":
        return False
    with _mig_lock:
        if _mig_hilo["t"] is not None:
            return True
        t = threading.Thread(target=_trabajo, args=(app, espera_inicial),
                             daemon=True, name="detalle-troceado")
        _mig_hilo["t"] = t
    t.start()
    print("Troceado automático del detalle de cuentas activo.")
    return True


# --------------------------------------------------------------------------- #
# Lectura
# --------------------------------------------------------------------------- #
def meta(report_id, tipo="cuentas"):
    """{"total", "tam", "campos"} si el informe tiene el detalle troceado."""
    from models import DetalleBloque
    clave = (report_id, tipo)
    with _lock:
        if clave in _meta_cache:
            return _meta_cache[clave] or None
    fila = (DetalleBloque.query
            .with_entities(DetalleBloque.datos)
            .filter_by(report_id=report_id, tipo=tipo, parte="meta", n=0)
            .first())
    valor = None
    if fila and fila[0]:
        try:
            valor = json.loads(fila[0])
        except Exception:
            valor = None
    with _lock:
        _meta_cache[clave] = valor or False
    return valor


def _bloques(report_id, tipo, numeros):
    from models import DetalleBloque
    numeros = sorted(set(numeros))
    if not numeros:
        return {}
    filas = (DetalleBloque.query
             .with_entities(DetalleBloque.n, DetalleBloque.datos)
             .filter(DetalleBloque.report_id == report_id,
                     DetalleBloque.tipo == tipo,
                     DetalleBloque.parte == "fila",
                     DetalleBloque.n.in_(numeros))
             .all())
    return {n: _descomprimir(d) for n, d in filas}


def _a_dict(fila, campos):
    nombres = [c for c in campos if c]
    return dict(zip(nombres, fila))


def filas_por_indices(report_id, tipo, indices, m=None):
    """Filas (dicts) en las posiciones pedidas, en ese orden."""
    m = m or meta(report_id, tipo)
    if not m or not indices:
        return []
    tam = m["tam"]
    bloques = _bloques(report_id, tipo, [i // tam for i in indices])
    salida = []
    for i in indices:
        b = bloques.get(i // tam)
        if b is not None and (i % tam) < len(b):
            salida.append(_a_dict(b[i % tam], m["campos"]))
    return salida


def rango(report_id, tipo, ini, cuantos, m=None):
    m = m or meta(report_id, tipo)
    if not m:
        return []
    fin = min(m["total"], ini + cuantos)
    return filas_por_indices(report_id, tipo, list(range(ini, fin)), m)


def iterar(report_id, tipo="cuentas", por_consulta=20):
    """Recorre todas las filas sin tenerlas todas en memoria (para Excel)."""
    m = meta(report_id, tipo)
    if not m:
        return
    nb = (m["total"] + m["tam"] - 1) // m["tam"]
    for k in range(0, nb, por_consulta):
        bloques = _bloques(report_id, tipo, range(k, min(nb, k + por_consulta)))
        for n in sorted(bloques):
            for fila in bloques[n]:
                yield _a_dict(fila, m["campos"])


def columna(report_id, tipo, idx):
    """Columna completa (lista de textos) con caché LRU."""
    from models import DetalleBloque
    clave = (report_id, tipo, idx)
    with _lock:
        if clave in _col_cache:
            _col_cache.move_to_end(clave)
            return _col_cache[clave]
    fila = (DetalleBloque.query
            .with_entities(DetalleBloque.datos)
            .filter_by(report_id=report_id, tipo=tipo, parte="col", n=idx)
            .first())
    valores = _descomprimir(fila[0]) if fila and fila[0] else []
    with _lock:
        _lru_put(_col_cache, clave, valores, _MAX_COLS)
    return valores


def indices_filtrados(report_id, tipo, activos, exactos):
    """Posiciones que cumplen los filtros.

    activos: {idx: texto en minúscula que debe estar contenido}
    exactos: {idx: [valores permitidos]} (lista vacía = ninguno)
    Devuelve None si no hay filtros (= todas las filas)."""
    if not activos and not exactos:
        return None
    clave = (report_id, tipo, json.dumps(
        [sorted(activos.items()), sorted((k, sorted(v)) for k, v in exactos.items())],
        ensure_ascii=False))
    with _lock:
        if clave in _idx_cache:
            _idx_cache.move_to_end(clave)
            return _idx_cache[clave]
    m = meta(report_id, tipo)
    total = m["total"] if m else 0
    sel = None  # None = todas
    for idx, txt in activos.items():
        col = columna(report_id, tipo, idx)
        candidatos = range(total) if sel is None else sel
        sel = [i for i in candidatos if txt in col[i].lower()]
    for idx, vals in exactos.items():
        col = columna(report_id, tipo, idx)
        permitidos = set(vals)
        candidatos = range(total) if sel is None else sel
        sel = [i for i in candidatos if col[i] in permitidos]
    sel = list(sel or [])
    with _lock:
        _lru_put(_idx_cache, clave, sel, _MAX_IDX)
    return sel
