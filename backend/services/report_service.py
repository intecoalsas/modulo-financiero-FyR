# -*- coding: utf-8 -*-
# Funciones para consultar los municipios, comercializadoras y reportes
# guardados en la base de datos.

from sqlalchemy.orm import load_only, joinedload
from models import db, Municipio, Comercializadora, Report

import time as _time
from types import SimpleNamespace

# Los municipios cambian muy poco: se cachean 5 minutos para no consultar
# la BD en cada página (en Turso cada consulta cuesta ~0,5-1 s de ida y vuelta).
_municipios_cache = {"valor": None, "ts": 0}


MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


# Todos los municipios, ordenados por nombre
def get_municipios():
    if (_municipios_cache["valor"] is not None
            and (_time.time() - _municipios_cache["ts"]) < 300):
        return _municipios_cache["valor"]
    filas = Municipio.query.order_by(Municipio.nombre).all()
    datos = [SimpleNamespace(id=m.id, nombre=m.nombre) for m in filas]
    _municipios_cache["valor"] = datos
    _municipios_cache["ts"] = _time.time()
    return datos


# Comercializadoras de un municipio (o todas si no se pasa ninguno)
def get_comercializadoras(municipio_id=None):
    q = Comercializadora.query
    if municipio_id:
        q = q.filter_by(municipio_id=municipio_id)
    return q.order_by(Comercializadora.nombre).all()


# Todos los reportes, con filtros opcionales de municipio, comercializadora y mes.
# Solo carga las columnas necesarias para el historial (sin JSON pesados).
def get_all_reports(filtro_municipio=None, filtro_comerc=None, filtro_mes=None):
    q = Report.query.options(
        load_only(
            Report.id,
            Report.comercializadora_id,
            Report.anio,
            Report.mes,
            Report.status,
            Report.created_at,
        ),
        # Evita N+1: trae la comercializadora y su municipio en la misma consulta
        joinedload(Report.comercializadora).joinedload(Comercializadora.municipio),
    ).join(Comercializadora).join(Municipio)
    if filtro_municipio:
        q = q.filter(Municipio.nombre == filtro_municipio)
    if filtro_comerc:
        q = q.filter(Comercializadora.nombre == filtro_comerc)
    if filtro_mes:
        q = q.filter(Report.mes == filtro_mes)
    return q.order_by(Report.anio.desc(), Report.mes.desc()).all()


# Borra un reporte de la base de datos
def delete_report(report_id):
    report = Report.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()


# Nombre del municipio de un reporte (para mostrar en los títulos).
# Consulta por JOIN y devuelve solo el nombre: no carga el reporte ni su blob.
def get_municipio_nombre(report_id):
    return (db.session.query(Municipio.nombre)
            .join(Comercializadora, Comercializadora.municipio_id == Municipio.id)
            .join(Report, Report.comercializadora_id == Comercializadora.id)
            .filter(Report.id == report_id)
            .scalar() or "")


# Nombre de la comercializadora de un reporte (igual: solo el nombre)
def get_comerc_nombre(report_id):
    return (db.session.query(Comercializadora.nombre)
            .join(Report, Report.comercializadora_id == Comercializadora.id)
            .filter(Report.id == report_id)
            .scalar() or "")
