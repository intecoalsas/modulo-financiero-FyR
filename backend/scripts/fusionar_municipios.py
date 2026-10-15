# -*- coding: utf-8 -*-
"""Fusiona municipios duplicados por tildes/mayúsculas (ej. Andalucia ->
Andalucía). Se conserva el que tiene tilde; sus comercializadoras,
reportes y datos por año se mueven al conservado. Ante un periodo
repetido en ambos, se aborta ese par para no perder datos.

Uso (desde backend/): python scripts/fusionar_municipios.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from models import db, Municipio, Comercializadora, Report  # noqa: E402
from core.core import _norm_nombre  # noqa: E402


def _tiene_tilde(s):
    try:
        return any(ord(c) > 127 for c in str(s or ""))
    except Exception:
        return False


def main():
    with app.app_context():
        grupos = {}
        for m in Municipio.query.all():
            grupos.setdefault(_norm_nombre(m.nombre), []).append(m)
        for norma, ms in sorted(grupos.items()):
            if len(ms) < 2:
                continue
            ms = sorted(ms, key=lambda x: x.id)
            keep = next((m for m in ms if _tiene_tilde(m.nombre)), ms[0])
            print(f"Duplicado '{norma}': conservo id={keep.id} '{keep.nombre}'")
            for dup in ms:
                if dup.id == keep.id:
                    continue
                print(f"  fusionando id={dup.id} '{dup.nombre}' ...")
                for c in list(Comercializadora.query.filter_by(municipio_id=dup.id).all()):
                    dest = None
                    for cand in Comercializadora.query.filter_by(municipio_id=keep.id).all():
                        if _norm_nombre(cand.nombre) == _norm_nombre(c.nombre):
                            dest = cand
                            break
                    if dest is None:
                        c.municipio_id = keep.id
                        db.session.flush()
                        dest = c
                        print(f"    comercializadora '{c.nombre}' movida")
                    else:
                        for rep in Report.query.filter_by(comercializadora_id=c.id).all():
                            existe = Report.query.filter_by(
                                comercializadora_id=dest.id, anio=rep.anio, mes=rep.mes).first()
                            if existe:
                                print(f"    ABORTO: periodo {rep.mes}/{rep.anio} ya existe en destino")
                                db.session.rollback()
                                return
                            rep.comercializadora_id = dest.id
                        for campo in ("tarifas", "analisis_general", "info_especiales",
                                      "descripcion", "cartera_acumulada"):
                            d_val = getattr(dest, campo, None)
                            c_val = getattr(c, campo, None)
                            if isinstance(c_val, dict):
                                nuevo = dict(d_val) if isinstance(d_val, dict) else {}
                                for k, v in c_val.items():
                                    if k not in nuevo:
                                        nuevo[k] = v
                                setattr(dest, campo, nuevo)
                        db.session.delete(c)
                        print(f"    comercializadora '{c.nombre}' fusionada en id={dest.id}")
                db.session.delete(dup)
                db.session.commit()
                print(f"  municipio id={dup.id} eliminado")
        print("OK")
        print("municipios:", [(m.id, m.nombre) for m in Municipio.query.order_by(Municipio.id).all()])


if __name__ == "__main__":
    main()
