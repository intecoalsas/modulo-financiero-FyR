

from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

# Objeto que conecta la app con la base de datos (crea las tablas, consultas, etc.)
db = SQLAlchemy()

# Colombia es UTC-5 fijo (sin horario de verano).
# Las fechas se guardan en UTC y solo se convierten a America/Bogota al
# mostrar (filtro hora_col). Así funciona igual en SQLite y PostgreSQL.
ZONA_COLOMBIA = timedelta(hours=-5)


def ahora_utc():
    return datetime.utcnow()


def a_hora_colombia(dt):
    """Naive UTC -> naive America/Bogota (solo para mostrar)."""
    if not dt:
        return None
    return dt + ZONA_COLOMBIA


# Un municipio (San Pedro, Calima, Andalucía...)
class Municipio(db.Model):
    __tablename__ = "municipios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, unique=True)
    codigo = db.Column(db.String(20), nullable=True)

    # Un municipio puede tener varias comercializadoras
    comercializadoras = db.relationship(
        "Comercializadora", back_populates="municipio", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Municipio {self.nombre}>"


# La empresa que recauda el impuesto en un municipio
class Comercializadora(db.Model):
    __tablename__ = "comercializadoras"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    # Cada comercializadora pertenece a un municipio
    municipio_id = db.Column(
        db.Integer, db.ForeignKey("municipios.id", ondelete="CASCADE"), nullable=False
    )

    municipio = db.relationship("Municipio", back_populates="comercializadoras")
    reports = db.relationship("Report", back_populates="comercializadora", cascade="all, delete-orphan")

    # Datos guardados como json dentro de la misma tabla:
    # información de clientes especiales, análisis, tarifas, descripción y cartera
    info_especiales = db.Column(db.JSON, nullable=True)
    analisis_general = db.Column(db.JSON, nullable=True)
    tarifas = db.Column(db.JSON, nullable=True)
    descripcion = db.Column(db.JSON, nullable=True)
    cartera_acumulada = db.Column(db.JSON, nullable=True)

    # Una comercializadora no puede repetirse dos veces en el mismo municipio
    __table_args__ = (
        db.UniqueConstraint("municipio_id", "nombre", name="uq_comerc_municipio"),
    )

    def __repr__(self):
        return f"<Comercializadora {self.nombre}>"


# Recuerda cómo se llaman las columnas en los excel que ya se usaron antes
# Así cuando suben un archivo nuevo ya sabe cuál columna es cuál
class MapeoColumna(db.Model):

    __tablename__ = "mapeo_columnas"

    clave = db.Column(db.String(64), primary_key=True)
    columnas = db.Column(db.Text, nullable=False, default="[]")

    def __repr__(self):
        return f"<MapeoColumna {self.clave}: {self.columnas}>"


# Guarda la carga a medio hacer mientras el usuario llena los datos que faltan
# (por ejemplo, cuando un archivo no trae el municipio y se pide a mano)
class CargaPendiente(db.Model):

    __tablename__ = "cargas_pendientes"

    token = db.Column(db.String(64), primary_key=True)
    datos = db.Column(db.Text, nullable=False, default="{}")
    creado = db.Column(db.DateTime, default=ahora_utc)

    def __repr__(self):
        return f"<CargaPendiente {self.token}>"


# Un informe ya procesado y guardado (un municipio + comercializadora + mes/año)
class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    comercializadora_id = db.Column(
        db.Integer, db.ForeignKey("comercializadoras.id", ondelete="CASCADE"), nullable=False
    )
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)

    # Los datos del informe general y de especiales se guardan como json
    general_data = db.Column(db.JSON, nullable=True)
    especiales_data = db.Column(db.JSON, nullable=True)

    analisis_ejecutivo = db.Column(db.Text, nullable=True)
    novedades = db.Column(db.JSON, nullable=True)

    # Rutas de los archivos que se usaron y de los informes generados
    archivo_fact_path = db.Column(db.String(500), nullable=True)
    archivo_rec_path = db.Column(db.String(500), nullable=True)
    excel_gen_path = db.Column(db.String(500), nullable=True)
    word_gen_path = db.Column(db.String(500), nullable=True)

    status = db.Column(db.String(20), default="procesado")
    created_at = db.Column(db.DateTime, default=ahora_utc)
    updated_at = db.Column(db.DateTime, default=ahora_utc, onupdate=ahora_utc)

    comercializadora = db.relationship("Comercializadora", back_populates="reports")

    # No pueden haber dos informes iguales (misma comercializadora, año y mes)
    __table_args__ = (
        db.UniqueConstraint("comercializadora_id", "anio", "mes", name="uq_report_periodo"),
        db.Index("ix_report_period", "anio", "mes"),
    )

    # "7" -> "Julio", sirve para mostrar el mes con nombre en las plantillas
    @property
    def mes_nombre(self):
        meses = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        return meses[self.mes] if 1 <= self.mes <= 12 else str(self.mes)

    # Nombre del municipio del informe, sacándolo de la comercializadora
    @property
    def municipio_nombre(self):
        return self.comercializadora.municipio.nombre if self.comercializadora else ""

    @property
    def comercializadora_nombre(self):
        return self.comercializadora.nombre if self.comercializadora else ""

    def __repr__(self):
        return f"<Report {self.municipio_nombre}/{self.comercializadora_nombre} {self.mes}/{self.anio}>"


# Registro de auditoría: quién (IP) hizo qué y cuándo (sin login no hay
# usuario; cuando se agregue autenticación se suma usuario_id)
class Auditoria(db.Model):
    __tablename__ = "auditoria"

    id = db.Column(db.Integer, primary_key=True)
    accion = db.Column(db.String(60), nullable=False)
    detalle = db.Column(db.String(500), nullable=True)
    ip = db.Column(db.String(60), nullable=True)
    fecha = db.Column(db.DateTime, default=ahora_utc)

    def __repr__(self):
        return f"<Auditoria {self.accion} {self.fecha}>"


# Cliente especial editable desde la interfaz (reemplaza la lista hardcodeada)
class ClienteEspecial(db.Model):
    __tablename__ = "clientes_especiales"

    id = db.Column(db.Integer, primary_key=True)
    id_cuenta = db.Column(db.String(50), nullable=False, unique=True)
    nombre = db.Column(db.String(300), nullable=False)
    grupo = db.Column(db.String(100), nullable=False)
    tarifa_min = db.Column(db.Float, default=0.0)
    consumo = db.Column(db.Float, default=0.0)
    periodicidad = db.Column(db.String(50), default="Mensual")
    activo = db.Column(db.Boolean, default=True)

    def to_tuple(self):
        return (self.id_cuenta, self.nombre, self.grupo, self.tarifa_min,
                self.consumo, 0, 0, self.periodicidad)

    def __repr__(self):
        return f"<ClienteEspecial {self.id_cuenta} {self.nombre}>"
