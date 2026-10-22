"""Equity de una mano contra un rango estimado (RF-06).

El rango es una distribución sobre las 169 manos canónicas (por ejemplo, el posterior de
`ModeloRangos`). Cada iteración sortea una mano canónica según su peso, una combinación concreta
entre las que no chocan con las cartas conocidas, y completa el tablero al azar.

Corrección por cartas conocidas: el peso de cada mano canónica se multiplica por la fracción de
sus combinaciones que siguen disponibles (por ejemplo, con As en la mano del héroe quedan 3 de 4
combinaciones de AKs). Así el sorteo equivale a condicionar el rango a las cartas visibles.
"""

from __future__ import annotations

import math
import random
from itertools import combinations
from typing import Dict, List, Sequence, Tuple

from .cartas import Carta, PALOS, VALOR_RANGO
from .equity import ResultadoEquity, _mazo_restante, _validar_sin_repetidos
from .evaluador import evaluar_mejor
from .rangos import COMBOS, ModeloRangos


def combinaciones_de_clave(clave: str) -> List[Tuple[Carta, Carta]]:
    """Todas las combinaciones concretas de una mano canónica ('AA', 'AKs', 'AKo')."""
    if clave not in COMBOS:
        raise ValueError(f"mano canónica inválida: {clave!r}")
    alto, bajo = VALOR_RANGO[clave[0]], VALOR_RANGO[clave[1]]
    if len(clave) == 2:
        pares = list(combinations(PALOS, 2))
        return [(Carta(alto, a), Carta(alto, b)) for a, b in pares]
    if clave.endswith("s"):
        return [(Carta(alto, p), Carta(bajo, p)) for p in PALOS]
    return [(Carta(alto, a), Carta(bajo, b)) for a in PALOS for b in PALOS if a != b]


def equity_contra_rango(
    mano: Sequence[Carta],
    rango: Dict[str, float],
    tablero: Sequence[Carta] = (),
    iteraciones: int = 10_000,
    semilla: int | None = None,
) -> ResultadoEquity:
    """Equity de `mano` contra un rival cuya mano sale de `rango` (clave canónica -> peso).

    Los pesos no necesitan sumar 1. Los empates se reparten en partes iguales.
    Con una semilla fija el resultado es reproducible (RNF-01).
    """
    mano, tablero = list(mano), list(tablero)
    if len(mano) != 2:
        raise ValueError("la mano del héroe debe tener 2 cartas")
    if len(tablero) not in (0, 3, 4, 5):
        raise ValueError("el tablero debe tener 0, 3, 4 o 5 cartas")
    if iteraciones < 2:
        raise ValueError("se requieren al menos 2 iteraciones para el error estándar")
    _validar_sin_repetidos(mano + tablero)

    bloqueadas = set(mano + tablero)
    claves: List[str] = []
    pesos: List[float] = []
    disponibles: List[List[Tuple[Carta, Carta]]] = []
    for clave, peso in rango.items():
        if peso < 0:
            raise ValueError("los pesos del rango no pueden ser negativos")
        if peso == 0:
            continue
        libres = [c for c in combinaciones_de_clave(clave) if c[0] not in bloqueadas and c[1] not in bloqueadas]
        if not libres:
            continue
        claves.append(clave)
        pesos.append(peso * len(libres) / COMBOS[clave])
        disponibles.append(libres)
    if not claves:
        raise ValueError("el rango no tiene combinaciones compatibles con las cartas conocidas")

    faltan = 5 - len(tablero)
    base = _mazo_restante(mano + tablero)  # una sola vez: en cada iteración solo se quitan las 2 del rival
    rng = random.Random(semilla)
    reparto: List[float] = []
    for _ in range(iteraciones):
        i = rng.choices(range(len(claves)), weights=pesos)[0]
        rival = rng.choice(disponibles[i])
        mazo = [c for c in base if c not in rival]  # mismo orden que _mazo_restante: mismo sorteo
        tab = tablero + rng.sample(mazo, faltan)
        propio = evaluar_mejor(mano + tab)
        ajeno = evaluar_mejor(list(rival) + tab)
        reparto.append(1.0 if propio > ajeno else 0.5 if propio == ajeno else 0.0)

    n = len(reparto)
    media = sum(reparto) / n
    varianza = sum((x - media) ** 2 for x in reparto) / (n - 1)
    return ResultadoEquity(media, math.sqrt(varianza / n), n)


def equity_contra_modelo(
    modelo: ModeloRangos,
    perfil: str,
    historia: Sequence[Tuple[str, str]],
    mano: Sequence[Carta],
    tablero: Sequence[Carta] = (),
    iteraciones: int = 10_000,
    semilla: int | None = None,
) -> ResultadoEquity:
    """Equity contra el rango posterior del `perfil` dada su historia preflop (contexto, acción)."""
    return equity_contra_rango(mano, modelo.posterior(perfil, list(historia)), tablero, iteraciones, semilla)
