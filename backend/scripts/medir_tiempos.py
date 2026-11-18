"""Medición de tiempos de carga de las pestañas (para reuniones/avances).

Dos modos:

1. Local (por defecto): abre la app con el cliente de pruebas de Flask
   contra la SQLite local (backend/instance/informes.db, solo lecturas GET)
   y mide el tiempo de cada pestaña Y el número de consultas a la base de
   datos. El número de consultas es lo importante: con Turso cada consulta
   es una petición HTTP (~0,13 s), así que menos consultas = página rápida.

2. --url https://mi-app.onrender.com: mide el tiempo REAL de respuesta de
   la app desplegada (produce peticiones HTTP GET contra producción).

Cada pestaña se mide dos veces y se reporta la segunda (caliente), que es
la experiencia real del usuario que ya abrió la app hoy. La tabla sale en
Markdown, lista para pegar en un documento de avances.

Uso:
    py -3.12 scripts/medir_tiempos.py
    py -3.12 scripts/medir_tiempos.py --url https://informes-fyr.onrender.com
"""
import argparse
import os
import statistics
import sys
import time

# Rutas GET de lectura (nada de formularios ni descargas de blob)
PAGINAS = [
    ("/", "Inicio (cargar archivos)"),
    ("/historial", "Historial"),
    ("/general", "Informe General (menú)"),
    ("/especiales", "Informe Especiales (menu)"),
    ("/cartera", "Cartera Acumulada SP"),
    ("/informacion-referencia", "Informacion de Referencia"),
]

REPETICIONES = 2  # 1.ª calienta cachés, se reporta la 2.ª


def _tabla(filas, encabezados):
    ancho = [max(len(str(f[i])) for f in [encabezados] + filas)
             for i in range(len(encabezados))]
    sep = "|" + "|".join("-" * (a + 2) for a in ancho) + "|"
    lineas = ["|" + "|".join(f" {str(h).ljust(a)} " for h, a in zip(encabezados, ancho)) + "|",
              sep]
    for f in filas:
        lineas.append("|" + "|".join(f" {str(c).ljust(a)} " for c, a in zip(f, ancho)) + "|")
    return "\n".join(lineas)


def medir_local():
    """Cliente de pruebas contra la SQLite local: tiempo + nº de consultas."""
    # app.py y sus módulos viven en backend/ (scripts/ está DENTRO de backend)
    _backend = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))
    sys.path.insert(0, _backend)
    # MEDIR SOLO LO LOCAL: se fuerza la SQLite del instance y se sacan las
    # variables de Turso ANTES de importar app (backend/.env no pisa valores
    # ya presentes en el entorno). Nada de este script debe tocar Turso.
    ruta_db = os.path.join(_backend, "instance", "informes.db")
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.abspath(ruta_db)
    os.environ.pop("TURSO_DATABASE_URL", None)
    os.environ.pop("TURSO_AUTH_TOKEN", None)
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    # Contador global de consultas SQL (antes de importar la app)
    contador = {"n": 0}

    def _cuenta(*_a, **_k):
        contador["n"] += 1

    event.listen(Engine, "before_cursor_execute", _cuenta)

    from app import app  # noqa: E402  (usa DATABASE_URL vacía -> SQLite local)
    cliente = app.test_client()

    filas = []
    total_consultas = 0
    print("Midiendo pestañas contra la SQLite local (2 pasadas)...\n")
    for ruta, nombre in PAGINAS:
        tiempos, consultas = [], []
        estado = "?"
        for pasada in range(REPETICIONES):
            contador["n"] = 0
            t0 = time.perf_counter()
            r = cliente.get(ruta, follow_redirects=True)
            tiempos.append(time.perf_counter() - t0)
            consultas.append(contador["n"])
            estado = r.status_code
        calido_t = tiempos[-1]
        calido_c = consultas[-1]
        total_consultas += calido_c
        filas.append((nombre, ruta, estado,
                      f"{calido_t:.2f}", f"{max(tiempos):.2f}", calido_c))

    print(_tabla(filas, ["Pestaña", "Ruta", "Estado", "Tiempo tibio (s)",
                         "Peor (s)", "Consultas BD"]))
    print(f"\nTotal consultas al recorrer las 6 pestañas (tibio): {total_consultas}")
    print("(En producción cada consulta cuesta ~0,13 s por HTTP a Turso; los "
          "tiempos locales de SQLite no son los de Render.")
    print("  Para tiempos reales: py -3.12 scripts/medir_tiempos.py --url <URL>)")


def medir_url(base, repeticiones):
    """Tiempos de respuesta reales contra la app desplegada (Render)."""
    try:
        import httpx
    except ImportError:
        sys.exit("Falta httpx: pip install httpx")
    if not base.startswith("http"):
        base = "https://" + base
    base = base.rstrip("/")
    print(f"Midiendo {base} ({repeticiones + 1} visitas por pestaña)...\n")

    filas = []
    with httpx.Client(follow_redirects=True, timeout=180) as c:
        for ruta, nombre in PAGINAS:
            tiempos, estados = [], []
            for _ in range(repeticiones + 1):  # la 1.ª despierta/calienta
                try:
                    t0 = time.perf_counter()
                    r = c.get(base + ruta)
                    tiempos.append(time.perf_counter() - t0)
                    estados.append(r.status_code)
                except Exception as exc:
                    filas.append((nombre, ruta, "ERROR", "-", "-", str(exc)[:40]))
                    tiempos = None
                    break
            if tiempos:
                calidos = tiempos[1:]
                filas.append((nombre, ruta, estados[-1],
                              f"{statistics.median(calidos):.2f}",
                              f"{max(calidos):.2f}", len(calidos)))

    print(_tabla(filas, ["Pestaña", "Ruta", "Estado",
                         "Mediana (s)", "Peor (s)", "Visitas"]))
    print("\nConsejo: si la 1.ª visita de la mañana tarda ~1 min es el cold "
          "start de Render (el keep-alive interno evita el resto de apagones).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="URL de producción (ej: https://mi-app.onrender.com)")
    parser.add_argument("--visitas", type=int, default=2,
                        help="visitas extra por pestaña en modo URL (defecto 2)")
    args = parser.parse_args()
    if args.url:
        medir_url(args.url, args.visitas)
    else:
        medir_local()
