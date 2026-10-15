# -*- coding: utf-8 -*-
# Funciones para consultar los municipios, comercializadoras y reportes
# guardados en la base de datos.

from sqlalchemy.orm import load_only
from models import db, Municipio, Comercializadora, Report


MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


# Todos los municipios, ordenados por nombre
def get_municipios():
    return Municipio.query.order_by(Municipio.nombre).all()


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
        )
    ).join(Comercializadora).join(Municipio)
    if filtro_municipio:
        q = q.filter(Municipio.nombre == filtro_municipio)
    if filtro_comerc:
        q = q.filter(Comercializadora.nombre == filtro_comerc)
    if filtro_mes:
        q = q.filter(Report.mes == filtro_mes)
    return q.order_by(Report.anio.desc(), Report.mes.desc()).all()


# Busca un reporte por su id, y si no existe da error 404
def get_report(report_id):
    return Report.query.get_or_404(report_id)


# Borra un reporte de la base de datos
def delete_report(report_id):
    report = Report.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()


# Nombre del municipio de un reporte (para mostrar en los títulos)
def get_municipio_nombre(report_id):
    r = Report.query.get(report_id)
    if r and r.comercializadora:
        return r.comercializadora.municipio.nombre
    return ""


# Nombre de la comercializadora de un reporte
def get_comerc_nombre(report_id):
    r = Report.query.get(report_id)
    if r and r.comercializadora:
        return r.comercializadora.nombre
    return ""
