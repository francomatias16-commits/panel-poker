"""Equity de una mano contra un rango, desde la línea de comandos (RF-06).

Uso (desde la raíz del proyecto):
    python3 scripts/equity_rango.py --mano "Kh Kd" --rango "AA,KK:0.5,AKs" [--tablero "2c 7d 9h"] [--iter 20000]

El rango es una lista de manos canónicas separadas por comas, con peso opcional (AA:2).
Sin peso, cada mano vale 1 (se corrige solo por la cantidad de combinaciones disponibles).
Es una herramienta de análisis sobre manos ya jugadas o hipotéticas; no opera sobre mesas reales.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.cartas import parsear_cartas  # noqa: E402
from poker_analisis.equity_rangos import equity_contra_rango  # noqa: E402


def parsear_rango(texto):
    rango = {}
    for parte in texto.split(","):
        clave, _, peso = parte.strip().partition(":")
        rango[clave] = float(peso) if peso else 1.0
    return rango


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mano", required=True)
    ap.add_argument("--rango", required=True)
    ap.add_argument("--tablero", default="")
    ap.add_argument("--iter", type=int, default=20_000)
    ap.add_argument("--semilla", type=int, default=7)
    a = ap.parse_args()
    r = equity_contra_rango(parsear_cartas(a.mano), parsear_rango(a.rango), parsear_cartas(a.tablero),
                            a.iter, a.semilla)
    bajo, alto = r.intervalo_95
    print(f"Equity: {100 * r.equity:.1f} %  (IC95 {100 * bajo:.1f} a {100 * alto:.1f} %, {r.iteraciones} iteraciones)")


if __name__ == "__main__":
    main()
