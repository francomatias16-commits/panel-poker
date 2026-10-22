"""Completa `jugada_en` en manos PHH ya cargadas, que quedaron con la fecha nula.

La carga normal no actualiza manos existentes (`on conflict do nothing`). Este script lee de nuevo la carpeta
de PHH y, por cada mano con fecha, hace `update ... where jugada_en is null`. Solo toca esa columna y es repetible.

Uso:
    export DATABASE_URL='postgresql://...'
    python3 scripts/completar_jugada_en.py --ruta /ruta/phh --fuente pluribus [--simular]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis import real  # noqa: E402

SQL = (
    "update poker.manos m set jugada_en = %s from poker.fuentes f "
    "where f.id = m.fuente_id and f.nombre = %s and m.mano_ref = %s and m.jugada_en is null"
)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ruta", required=True)
    ap.add_argument("--fuente", required=True)
    ap.add_argument("--simular", action="store_true", help="cuenta las manos con fecha, sin conectarse")
    ap.add_argument("--lote", type=int, default=5000)
    a = ap.parse_args()

    rechazos = []
    filas = ((m.fecha, a.fuente, m.referencia) for m in real.iterar_directorio(a.ruta, rechazos) if m.fecha)
    if a.simular:
        print(f"Manos con fecha: {sum(1 for _ in filas)}. Rechazadas: {len(rechazos)}. No se escribió nada.")
        return
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Falta la variable de entorno DATABASE_URL.")
    import psycopg
    from itertools import islice
    actualizadas = 0
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            while True:
                paquete = list(islice(filas, a.lote))
                if not paquete:
                    break
                cur.executemany(SQL, paquete)
                actualizadas += cur.rowcount if cur.rowcount > 0 else 0
    print(f"Manos actualizadas: {actualizadas}. Rechazadas al leer: {len(rechazos)}.")


if __name__ == "__main__":
    main()
