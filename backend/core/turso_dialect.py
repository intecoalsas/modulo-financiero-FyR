# -*- coding: utf-8 -*-
"""Dialecto SQLAlchemy para Turso (libSQL) sobre HTTP.

Se registra con el prefijo "turso://" para que Flask-SQLAlchemy pueda crear
el engine a partir de app.config["SQLALCHEMY_DATABASE_URI"].
"""
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite as SQLiteDialect

from core import turso_dbapi


class TursoDialect(SQLiteDialect):
    supports_statement_cache = True
    @classmethod
    def import_dbapi(cls):
        return turso_dbapi

    def create_connect_args(self, url):
        # La URL real y el token vienen de variables de entorno/configuración,
        # no de la URI de SQLAlchemy.
        import os
        turso_url = os.environ.get("TURSO_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
        if turso_url.startswith("libsql://"):
            turso_url = "https://" + turso_url[len("libsql://"):]
        token = os.environ.get("TURSO_AUTH_TOKEN", "")
        if not turso_url or not token:
            raise RuntimeError(
                "Faltan TURSO_DATABASE_URL y/o TURSO_AUTH_TOKEN en el entorno."
            )
        return [], {"database": turso_url, "auth_token": token, "url": turso_url, "token": token}

    def _get_server_version_info(self, connection):
        # Evita llamar a PRAGMA que Turso no soporta.
        return (3, 40)


def register():
    from sqlalchemy.dialects import registry as _reg
    try:
        _reg.register("turso", "core.turso_dialect", "TursoDialect")
    except Exception:
        pass
