"""Estadísticas de acciones sobre una muestra del dataset HandHQ (online, julio de 2009).

Uso (desde la raíz del proyecto):
    python3 scripts/analizar_handhq.py [ruta_handhq] [archivos_por_nivel]

Fuente: dataset PHH público (Juho Kim, Universidad de Toronto), CC BY 4.0.
Los jugadores están seudonimizados y la mayoría de las cartas aparecen ocultas, así que
solo se calculan métricas de acciones y de resultado, no evaluación de rangos.
Los netos se expresan en big blinds de cada mano, porque los niveles mezclan blinds de
0,5 a 500 dólares. El dataset no incluye rake: la suma de netos por mano queda negativa.
"""

import csv
import os
import random
import re
import sys
from collections import defaultdict
import statistics
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.estadisticas import calcular  # noqa: E402
from poker_analisis.phh import ErrorPHH  # noqa: E402
from poker_analisis.real import cargar_multimano, desde_phh  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..")
RUTA = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/uoftcprg/phh-dataset/data/handhq"
POR_NIVEL = int(sys.argv[2]) if len(sys.argv) > 2 else 25
SALIDA = os.path.join(RAIZ, "resultados", "estadisticas_handhq_muestra.csv")
SEMILLA = 1
JUGADOR = "jugador"  # pooled: no se distingue entre jugadores seudonimizados


def archivos_por_nivel():
    grupos = defaultdict(list)
    for dirpath, _, archivos in os.walk(RUTA):
        m = re.search(r"_(\d+)NLH", dirpath)
        if not m:
            continue
        for nombre in archivos:
            if nombre.endswith(".phhs"):
                grupos[int(m.group(1))].append(os.path.join(dirpath, nombre))
    return grupos


def big_blind(texto: str) -> float:
    """El blind grande de la mano, leído del propio texto PHH."""
    m = re.search(r"blinds_or_straddles = \[([^\]]*)\]", texto)
    valores = [float(x) for x in m.group(1).split(",") if float(x) > 0]
    return max(valores)


def main():
    rng = random.Random(SEMILLA)
    grupos = archivos_por_nivel()
    print(f"Muestra: {POR_NIVEL} archivos por nivel (semilla {SEMILLA}).\n")

    filas = []
    for nivel in sorted(grupos, reverse=True):
        elegidos = rng.sample(grupos[nivel], min(POR_NIVEL, len(grupos[nivel])))
        manos = []
        rechazadas = 0
        conocidas = 0
        for camino in elegidos:
            with open(camino, encoding="utf-8") as f:
                texto = f.read()
            for bloque in cargar_multimano(texto):
                try:
                    m = desde_phh(bloque)
                    bb = big_blind(bloque)
                except (ErrorPHH, ValueError, IndexError, AttributeError):
                    rechazadas += 1
                    continue
                if all(len(c) == 2 and None not in c for c in m.cartas):
                    conocidas += 1
                # Netos en big blinds de la mano; grupo único de jugadores para la estadística agregada.
                manos.append(replace(m, neto=[x / bb for x in m.neto], nombres=None))

        if not manos:
            continue
        stats = calcular(manos, nombres=[JUGADOR] * 20, bb=1)[0]
        sumas = [sum(m.neto) for m in manos]
        neto_medio = sum(sumas) / len(manos)
        neto_mediana = statistics.median(sumas)
        print(f"Nivel {nivel} NL: {len(manos)} manos ({rechazadas} rechazadas), "
              f"suma neta por mano: media {neto_medio:+.2f} bb, mediana {neto_mediana:+.2f} bb (negativa = rake implícito)")
        filas.append({
            "nivel_nl": nivel, "manos": len(manos), "rechazadas": rechazadas,
            "vpip": round(stats.vpip, 4), "pfr": round(stats.pfr, 4),
            "tres_bet": "" if stats.tres_bet is None else round(stats.tres_bet, 4),
            "af": "" if stats.af is None else round(stats.af, 4),
            "wtsd": "" if stats.wtsd is None else round(stats.wtsd, 4),
            "wsd": "" if stats.wsd is None else round(stats.wsd, 4),
            "bb100": round(stats.bb100, 3), "ic95": round(stats.bb100_ic95, 3),
            "neto_medio_bb_por_mano": round(neto_medio, 4),
            "neto_mediana_bb_por_mano": round(neto_mediana, 4),
            "manos_con_cartas_conocidas": conocidas,
        })

    print()
    for f in filas:
        print(f"{f['nivel_nl']:>5} NL  manos={f['manos']:>7}  VPIP={100 * f['vpip']:5.1f}%  "
              f"PFR={100 * f['pfr']:5.1f}%  3bet={'-' if f['tres_bet'] == '' else f'{100 * f['tres_bet']:5.1f}%'}  "
              f"AF={'-' if f['af'] == '' else f'{f['af']:.2f}'}  WTSD={100 * f['wtsd']:5.1f}%  "
              f"cartas conocidas={f['manos_con_cartas_conocidas']}")

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0].keys()))
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"\nGuardado en {os.path.abspath(SALIDA)}")


if __name__ == "__main__":
    main()
