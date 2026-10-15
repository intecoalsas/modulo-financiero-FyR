# -*- coding: utf-8 -*-
"""Copia todos los datos de la BD local (SQLite) a una BD Postgres en la nube.

Uso (desde backend/, con la app detenida y la BD destino recién creada):
    python scripts/migrar_a_postgres.py "postgresql+psycopg://user:pass@host/db?sslmode=require"

La BD destino se vacía y se recrea con los datos de la local. Después solo
hay que poner DATABASE_URL con esa misma cadena y arrancar la app.
"""
import os
import sys

from sqlalchemy import MetaData, Table, create_engine, inspect, text

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE = "sqlite:///" + os.path.join(BASE, "instance", "informes.db")

# Orden en que se copian (municipio -> comercializadora -> informes)
TABLAS = ["municipios", "comercializadoras", "mapeo_columnas",
          "cargas_pendientes", "auditoria", "clientes_especiales", "reports"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return False
    destino_url = sys.argv[1]
    origen = create_engine(SQLITE)
    destino = create_engine(destino_url)
    meta_origen = MetaData()
    insp_origen = inspect(origen)
    disponibles = insp_origen.get_table_names()

    with destino.connect() as c_dest:
        for tabla in TABLAS:
            if tabla not in disponibles:
                print(f"  {tabla}: no existe en la BD local, se omite")
                continue
            # Se recrea la tabla en destino con la misma forma y sin datos
            c_dest.execute(text(f'DROP TABLE IF EXISTS "{tabla}" CASCADE'))
            tabla_ref = Table(tabla, meta_origen, autoload_with=origen)
            tabla_ref.create(c_dest, checkfirst=True)

            with origen.connect() as c_orig:
                filas = c_orig.execute(
                    text(f'SELECT * FROM "{tabla}"')).mappings().all()
            if not filas:
                print(f"  {tabla}: 0 filas")
                continue
            cols = list(filas[0].keys())
            marcadores = ", ".join(f":{c}" for c in cols)
            nombres = ", ".join(f'"{c}"' for c in cols)
            insert = text(f'INSERT INTO "{tabla}" ({nombres}) VALUES ({marcadores})')
            for fila in filas:
                c_dest.execute(insert, dict(fila))

            # Sigue la secuencia de los id para los próximos registros
            pk = (insp_origen.get_pk_constraint(tabla)
                  .get("constrained_columns") or [])
            if pk:
                seq = c_dest.execute(text(
                    "SELECT pg_get_serial_sequence(:t, :c)"),
                    {"t": tabla, "c": pk[0]}).scalar()
                if seq:
                    c_dest.execute(text(
                        f'SELECT setval(:s, COALESCE((SELECT MAX("{pk[0]}") '
                        f'FROM "{tabla}"), 1))'), {"s": seq})
            print(f"  {tabla}: {len(filas)} filas copiadas")
        c_dest.commit()

    destino.dispose()
    origen.dispose()
    print("Migración terminada. Ahora pon DATABASE_URL con esa misma cadena "
          "y arranca la app.")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
