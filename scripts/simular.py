"""Simula una mesa de Texas Hold'em con bots de perfiles distintos y reporta estadísticas.

Uso (desde la raíz del proyecto):
    python3 scripts/simular.py [manos] [semilla]

Requiere haber generado la tabla preflop con scripts/tabla_preflop.py.
Los resultados se guardan en resultados/estadisticas_simulacion.csv.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.bots import cargar_tabla_preflop  # noqa: E402
from poker_analisis.estadisticas import calcular, formatear  # noqa: E402
from poker_analisis.simulacion import BLIND_GRANDE, PERFILES, simular_mesa  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..")
TABLA = os.path.join(RAIZ, "resultados", "preflop_equity.csv")
SALIDA = os.path.join(RAIZ, "resultados", "estadisticas_simulacion.csv")


def main():
    manos = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    semilla = int(sys.argv[2]) if len(sys.argv) > 2 else 7

    tabla = cargar_tabla_preflop(TABLA)
    resultados = simular_mesa(tabla, manos, semilla)

    stats = calcular(resultados, PERFILES, BLIND_GRANDE)
    stats.sort(key=lambda s: s.bb100, reverse=True)
    print(f"{manos} manos, semilla {semilla}, blinds 1/{BLIND_GRANDE}\n")
    print(formatear(stats))

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["perfil", "manos", "vpip", "pfr", "tres_bet", "af", "wtsd", "wsd", "cbet", "fold_cbet", "bb100", "ic95"])
        for s in stats:
            escritor.writerow([
                s.nombre, s.manos, round(s.vpip, 4), round(s.pfr, 4),
                "" if s.tres_bet is None else round(s.tres_bet, 4),
                "" if s.af is None else round(s.af, 4),
                "" if s.wtsd is None else round(s.wtsd, 4),
                "" if s.wsd is None else round(s.wsd, 4),
                "" if s.cbet is None else round(s.cbet, 4),
                "" if s.fold_cbet is None else round(s.fold_cbet, 4),
                round(s.bb100, 3), round(s.bb100_ic95, 3),
            ])
    print(f"\nResultados guardados en {os.path.abspath(SALIDA)}")


if __name__ == "__main__":
    main()
