"""Genera la tabla de equity preflop de las 169 manos iniciales de Hold'em.

Cada mano canónica (pares, suited, offsuit) se evalúa heads-up contra una mano
aleatoria. La semilla es fija por mano, así el resultado es reproducible.

Uso (desde la raíz del proyecto):
    python3 scripts/tabla_preflop.py [iteraciones]
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.cartas import Carta, RANGOS, VALOR_RANGO  # noqa: E402
from poker_analisis.equity import equity  # noqa: E402

ITERACIONES = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
SALIDA = os.path.join(os.path.dirname(__file__), "..", "resultados", "preflop_equity.csv")


def manos_canonicas():
    """Yield (etiqueta, tipo, cartas) para las 169 manos iniciales."""
    rangos = RANGOS[::-1]  # A primero
    for i, alto in enumerate(rangos):
        for bajo in rangos[i:]:
            va, vb = VALOR_RANGO[alto], VALOR_RANGO[bajo]
            if alto == bajo:
                yield alto + bajo, "pareja", [Carta(va, "c"), Carta(vb, "d")]
            else:
                yield alto + bajo + "s", "suited", [Carta(va, "c"), Carta(vb, "c")]
                yield alto + bajo + "o", "offsuit", [Carta(va, "c"), Carta(vb, "d")]


def main():
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    filas = []
    for semilla, (etiqueta, tipo, cartas) in enumerate(manos_canonicas()):
        r = equity(cartas, n_rivales_aleatorios=1, iteraciones=ITERACIONES, semilla=semilla)
        lo, hi = r.intervalo_95
        filas.append({
            "mano": etiqueta,
            "tipo": tipo,
            "equity": round(r.equity, 4),
            "error_estandar": round(r.error_estandar, 4),
            "ic95_inf": round(lo, 4),
            "ic95_sup": round(hi, 4),
        })
    filas.sort(key=lambda f: f["equity"], reverse=True)

    with open(SALIDA, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        escritor.writeheader()
        escritor.writerows(filas)

    print(f"{len(filas)} manos escritas en {SALIDA} ({ITERACIONES} iteraciones por mano)")
    print("Top 5:", [(f["mano"], f["equity"]) for f in filas[:5]])
    print("Bottom 5:", [(f["mano"], f["equity"]) for f in filas[-5:]])


if __name__ == "__main__":
    main()
