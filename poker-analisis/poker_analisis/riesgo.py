"""Métricas de riesgo sobre series de resultados por mano (en big blinds).

Supuestos: las manos son independientes e idénticamente distribuidas y el winrate medido
es el verdadero. Con pocas manos el winrate tiene un intervalo muy ancho (ver estadisticas.py),
así que estas cifras son escenarios condicionales, no pronósticos.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import List, Optional, Sequence

from .motor import ResultadoMano


def serie_neta(manos: Sequence[ResultadoMano], jugador: str, bb: float) -> List[float]:
    """Resultado de `jugador` en cada mano que jugó, en big blinds, en orden."""
    serie: List[float] = []
    for m in manos:
        if m.nombres and jugador in m.nombres:
            serie.append(m.neto[m.nombres.index(jugador)] / bb)
    return serie


def resumen(netos: Sequence[float]) -> dict:
    """Winrate y desvío en bb/100 manos."""
    n = len(netos)
    if n < 2:
        raise ValueError("se necesitan al menos 2 manos")
    media = statistics.fmean(netos)
    desvio = statistics.stdev(netos)
    return {
        "manos": n,
        "winrate_bb100": media * 100,
        "desvio_bb100": desvio * 10,  # sqrt(100) * desvío por mano
        "winrate_bb_mano": media,
        "desvio_bb_mano": desvio,
    }


def max_drawdown(netos: Sequence[float]) -> float:
    """Mayor caída (en bb) desde un máximo acumulado hasta un mínimo posterior."""
    acum = pico = peor = 0.0
    for x in netos:
        acum += x
        pico = max(pico, acum)
        peor = max(peor, pico - acum)
    return peor


def prob_ruina_analitica(winrate_bb100: float, desvio_bb100: float, bankroll_bb: float) -> float:
    """Probabilidad de ruina en horizonte infinito, aproximación de movimiento browniano:
    exp(-2·mu·B / sigma²). Con winrate no positivo la ruina es segura."""
    if bankroll_bb <= 0:
        return 1.0
    if winrate_bb100 <= 0:
        return 1.0
    if desvio_bb100 <= 0:
        return 0.0
    return math.exp(-2 * winrate_bb100 * bankroll_bb / desvio_bb100 ** 2)


def prob_ruina_simulada(
    netos: Sequence[float], bankroll_bb: float, horizonte: int, trayectorias: int = 2000,
    semilla: Optional[int] = 0,
) -> float:
    """Fracción de trayectorias (remuestreo con reposición de los netos observados) que
    tocan cero dentro del horizonte. Reproducible con la semilla."""
    if not netos:
        raise ValueError("serie vacía")
    rng = random.Random(semilla)
    ruinas = 0
    for _ in range(trayectorias):
        saldo = bankroll_bb
        for _ in range(horizonte):
            saldo += netos[rng.randrange(len(netos))]
            if saldo <= 0:
                ruinas += 1
                break
    return ruinas / trayectorias


def bankroll_kelly(winrate_bb100: float, desvio_bb100: float, fraccion: float = 1.0) -> Optional[float]:
    """Bankroll (en bb) para el que jugar este límite equivale a la fracción de Kelly indicada.

    Con retornos aproximadamente normales, Kelly completo arriesga f = mu/sigma² del bankroll
    por unidad, es decir B = sigma²/mu (en bb, con mu y sigma por 100 manos). Kelly fraccionado
    (por ejemplo 0,5) exige un bankroll 1/fraccion veces mayor. Sin winrate positivo no hay Kelly.
    """
    if not 0 < fraccion <= 1:
        raise ValueError("la fracción de Kelly debe estar en (0, 1]")
    if winrate_bb100 <= 0:
        return None
    return desvio_bb100 ** 2 / winrate_bb100 / fraccion
