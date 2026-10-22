"""Carga manos (texto estilo PokerStars, GGPoker o PHH) a la base de Supabase, en el schema `poker`.

Uso:
    export DATABASE_URL='postgresql://postgres:<clave>@db.<proyecto>.supabase.co:5432/postgres'
    export POKER_SAL='<texto secreto y estable>'
    python3 scripts/cargar_supabase.py --formato texto --ruta /ruta/historiales \\
        --fuente historiales-propios --licencia propio
    python3 scripts/cargar_supabase.py ... --simular        # solo analiza, no toca la base

Requiere `pip install "psycopg[binary]"`. Las credenciales van en variables de entorno, nunca en
el código ni en el chat. POKER_SAL debe ser siempre la misma: con otra sal, los mismos jugadores
tendrían seudónimos distintos. Guardala en un gestor de contraseñas: si se pierde, no se puede
volver a vincular los seudónimos. La carga es idempotente: repetirla no duplica manos.
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis import carga, ggpoker, real  # noqa: E402

_TEXTO = (ggpoker.cargar_directorio, "texto-pokerstars")
FORMATOS = {"texto": _TEXTO, "ggpoker": _TEXTO, "pokerstars": _TEXTO, "phh": (real.cargar_directorio, "phh")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--formato", choices=FORMATOS, required=True)
    ap.add_argument("--ruta", required=True)
    ap.add_argument("--fuente", required=True, help="nombre de la fuente, p. ej. historiales-propios")
    ap.add_argument("--licencia", required=True, help="p. ej. propio o 'CC BY 4.0'")
    ap.add_argument("--simular", action="store_true", help="analiza y cuenta, sin conectarse")
    ap.add_argument("--lote", type=int, default=500)
    a = ap.parse_args()

    cargador, nombre_formato = FORMATOS[a.formato]
    manos, rechazos = cargador(a.ruta)
    print(f"Manos válidas: {len(manos)}. Rechazadas: {len(rechazos)}.")
    for motivo, n in collections.Counter(m for _, m in rechazos).most_common(8):
        print(f"  {n:>6}  {motivo}")
    sin_datos = [m for m in manos if m.referencia is None or m.ciega_chica is None]
    if sin_datos:
        sys.exit(f"{len(sin_datos)} manos no traen referencia o ciegas: no se pueden cargar.")
    if a.simular or not manos:
        print("Simulación: no se escribió nada." if a.simular else "Nada que cargar.")
        return

    sal = os.environ.get("POKER_SAL")
    url = os.environ.get("DATABASE_URL")
    if not sal or not url:
        sys.exit("Faltan las variables de entorno POKER_SAL y DATABASE_URL.")
    try:
        import psycopg
    except ImportError:
        sys.exit('Falta el driver: pip install "psycopg[binary]"')

    with psycopg.connect(url) as conn:  # confirma al salir sin error; revierte si falla
        with conn.cursor() as cur:
            n = carga.cargar(cur, manos, a.fuente, a.licencia, nombre_formato, sal, a.lote)
            cur.execute("select count(*) from poker.manos m join poker.fuentes f on f.id = m.fuente_id "
                        "where f.nombre = %s", (a.fuente,))
            total = cur.fetchone()[0]
    print(f"Enviadas {n} manos. La fuente '{a.fuente}' tiene ahora {total} manos en la base.")


if __name__ == "__main__":
    main()
