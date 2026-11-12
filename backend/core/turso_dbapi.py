# -*- coding: utf-8 -*-
"""Adaptador DB-API 2.0 para Turso (libSQL) sobre su API HTTP.

Permite que SQLAlchemy use Turso como si fuera SQLite, sin compilar
extensiones de Rust. Se apoya únicamente en urllib (stdlib) y en la API
HTTP documentada de Turso (/v2/pipeline).

Uso:
    from core import turso_dbapi
    turso_dbapi.configure("https://mi-db-miorg.turso.io", "eyJhbGci...")
    conn = turso_dbapi.connect()
"""
import base64
import json
import urllib.error
import urllib.request
from datetime import date, datetime


# --------------------------------------------------------------------------- #
# Configuración global
# --------------------------------------------------------------------------- #
_URL = None
_TOKEN = None

# Cliente HTTP compartido con keep-alive: evita pagar el handshake TLS en
# cada consulta (la diferencia es de ~1 s por query contra Turso).
_http_client = None


def _cliente_http():
    global _http_client
    if _http_client is None:
        try:
            import httpx
            _http_client = httpx.Client(
                timeout=300.0,
                limits=httpx.Limits(max_keepalive_connections=20,
                                    max_connections=50),
                headers={"User-Agent": "informes-fyr/1.0"},
            )
        except Exception:
            _http_client = False
    return _http_client


def configure(url, token):
    global _URL, _TOKEN
    _URL = (url or "").rstrip("/")
    if _URL.startswith("libsql://"):
        _URL = "https://" + _URL[len("libsql://"):]
    _TOKEN = token or ""


# --------------------------------------------------------------------------- #
# Excepciones DB-API 2.0
# --------------------------------------------------------------------------- #
class Error(Exception):
    pass


class DatabaseError(Error):
    pass


class OperationalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class DataError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


apilevel = "2.0"
threadsafety = 1
paramstyle = "qmark"
sqlite_version_info = (3, 40, 0)


# --------------------------------------------------------------------------- #
# Conversión de valores Python <-> formato Turso
# --------------------------------------------------------------------------- #
def _to_turso_arg(p):
    if p is None:
        return {"type": "null"}
    if isinstance(p, bool):
        return {"type": "integer", "value": "1" if p else "0"}
    if isinstance(p, int):
        return {"type": "integer", "value": str(p)}
    if isinstance(p, float):
        return {"type": "float", "value": p}
    if isinstance(p, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(p)).decode("ascii")}
    if isinstance(p, (datetime, date)):
        return {"type": "text", "value": p.isoformat()}
    return {"type": "text", "value": str(p)}


def _from_turso_value(v):
    if v is None:
        return None
    t = v.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(v["value"])
    if t == "float":
        return float(v["value"])
    if t == "text":
        return v["value"]
    if t == "blob":
        return base64.b64decode(v["base64"])
    return v.get("value")


# --------------------------------------------------------------------------- #
# Conexión
# --------------------------------------------------------------------------- #
class Connection:
    def __init__(self, url=None, auth_token=None):
        self.url = (url or _URL or "").rstrip("/")
        if self.url.startswith("libsql://"):
            self.url = "https://" + self.url[len("libsql://"):]
        self.token = auth_token if auth_token is not None else (_TOKEN or "")
        self._baton = None
        self._closed = False

    def close(self):
        if self._closed:
            return
        if self._baton is not None:
            try:
                self._pipeline([{"type": "close"}], self._baton)
            except Exception:
                pass
        self._baton = None
        self._closed = True

    def create_function(self, *a, **kw):
        return None

    def create_aggregate(self, *a, **kw):
        return None

    def set_authorizer(self, *a, **kw):
        return None

    def commit(self):
        if self._baton is not None:
            try:
                self._pipeline([{"type": "execute",
                                 "stmt": {"sql": "COMMIT"}}], self._baton)
            except Exception:
                pass
            self._baton = None

    def rollback(self):
        if self._baton is not None:
            try:
                self._pipeline([{"type": "execute",
                                 "stmt": {"sql": "ROLLBACK"}}], self._baton)
            except Exception:
                pass
            self._baton = None

    def cursor(self):
        return Cursor(self)

    def _pipeline(self, requests, baton=None):
        body = {"requests": requests}
        if baton is not None:
            body["baton"] = baton
        data = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
        }
        cliente = _cliente_http()
        if cliente:
            try:
                resp = cliente.post(self.url + "/v2/pipeline",
                                    content=data, headers=headers)
            except Exception as exc:
                raise OperationalError(str(exc)) from exc
            if resp.status_code >= 400:
                raise OperationalError(
                    f"HTTP {resp.status_code}: {resp.text[:300]}")
            raw = resp.content
        else:
            req = urllib.request.Request(
                self.url + "/v2/pipeline", data=data, method="POST",
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    raw = resp.read()
            except urllib.error.HTTPError as exc:
                msg = exc.read().decode("utf-8", "replace")
                raise OperationalError(f"HTTP {exc.code}: {msg}") from exc
            except Exception as exc:
                raise OperationalError(str(exc)) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise OperationalError(f"Respuesta inválida: {exc}") from exc

        # Comprobar errores en los resultados
        for r in payload.get("results", []):
            if r.get("type") == "error":
                msg = r.get("error", {}).get("message", "error de Turso")
                raise OperationalError(msg)
            resp_obj = r.get("response", {})
            if resp_obj.get("type") == "error":
                msg = resp_obj.get("error", {}).get("message", "error de Turso")
                raise OperationalError(msg)
        return payload

    def _execute(self, sql, params=None):
        sql = sql.strip() if isinstance(sql, str) else sql
        upper = (sql or "").upper().lstrip()
        is_begin = upper.startswith("BEGIN")
        is_commit = upper == "COMMIT" or upper.startswith("COMMIT ")
        is_rollback = upper == "ROLLBACK" or upper.startswith("ROLLBACK ")
        is_close = upper == "CLOSE"

        stmt = {"sql": sql}
        if params is not None:
            if isinstance(params, dict):
                named = []
                for k, v in params.items():
                    named.append({"name": k, "value": _to_turso_arg(v)})
                stmt["named_args"] = named
            else:
                seq = params if not isinstance(params, (str, bytes)) else [params]
                stmt["args"] = [_to_turso_arg(p) for p in seq]

        # Transacción ya abierta
        if self._baton is not None and not is_begin:
            reqs = [{"type": "execute", "stmt": stmt}]
            if is_commit or is_rollback:
                reqs.append({"type": "close"})
            data = self._pipeline(reqs, self._baton)
            if is_commit or is_rollback or is_begin is False and False:
                pass
            if is_commit or is_rollback:
                self._baton = None
            else:
                self._baton = data.get("baton")
            res = (data.get("results") or [{}])[0].get("response", {}).get("result", {})
            return res

        # Nueva conexión / transacción
        reqs = [{"type": "execute", "stmt": stmt}]
        if is_begin:
            data = self._pipeline(reqs)  # sin baton: nueva conexión
            self._baton = data.get("baton")
        else:
            reqs.append({"type": "close"})
            data = self._pipeline(reqs)
            self._baton = None
        res = (data.get("results") or [{}])[0].get("response", {}).get("result", {})
        return res


class Cursor:
    def __init__(self, conn):
        self.connection = conn
        self.description = None
        self.rowcount = -1
        self.lastrowid = None
        self.arraysize = 1
        self._rows = []
        self._idx = 0

    def execute(self, sql, params=None):
        res = self.connection._execute(sql, params)
        cols = res.get("cols") or []
        self.description = [(c.get("name"), None, None, None, None, None, None)
                            for c in cols] if cols else None
        self.rowcount = res.get("affected_row_count", 0) or 0
        self.lastrowid = res.get("last_insert_rowid")
        raw_rows = res.get("rows") or []
        self._rows = []
        for r in raw_rows:
            self._rows.append(tuple(_from_turso_value(c) for c in r))
        self._idx = 0
        return self

    def executemany(self, sql, seq):
        for params in seq:
            self.execute(sql, params)
        return self

    def fetchone(self):
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self):
        out = self._rows[self._idx:]
        self._idx = len(self._rows)
        return out

    def fetchmany(self, size=None):
        size = size or self.arraysize
        out = []
        for _ in range(size):
            r = self.fetchone()
            if r is None:
                break
            out.append(r)
        return out

    def close(self):
        pass

    @property
    def rowcount_prop(self):
        return self.rowcount


def connect(database=None, auth_token=None, url=None, token=None, **kwargs):
    u = url or database or _URL
    t = token if token is not None else (auth_token if auth_token is not None else _TOKEN)
    return Connection(u, t)
