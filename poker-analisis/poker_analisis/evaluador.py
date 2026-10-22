"""Evaluador de manos de Texas Hold'em: 5 cartas y mejor 5 de 7.

Una mano se representa con una tupla comparable de forma lexicográfica.
El primer elemento es la categoría (0 = carta alta ... 8 = escalera de color),
seguido de los desempates necesarios para ordenar manos de la misma categoría.
Mayor tupla significa mano más fuerte.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Sequence, Tuple

from .cartas import Carta

Puntaje = Tuple[int, ...]

CATEGORIAS = (
    "Carta alta",
    "Par",
    "Doble par",
    "Trío",
    "Escalera",
    "Color",
    "Full",
    "Póker",
    "Escalera de color",
)


def _escalera_alta(valores_desc: Sequence[int]) -> int | None:
    """Devuelve el valor más alto de la escalera, o None si no hay escalera.

    La escalera A-5 (la 'rueda') vale 5 como carta más alta.
    """
    if len(set(valores_desc)) != 5:
        return None
    if valores_desc[0] - valores_desc[-1] == 4:
        return valores_desc[0]
    if valores_desc == (14, 5, 4, 3, 2):
        return 5
    return None


def evaluar_cinco(cartas: Sequence[Carta]) -> Puntaje:
    """Puntaje de exactamente 5 cartas."""
    if len(cartas) != 5:
        raise ValueError("evaluar_cinco requiere exactamente 5 cartas")

    valores = tuple(sorted((c.valor for c in cartas), reverse=True))
    color = len({c.palo for c in cartas}) == 1
    # Grupos por (cantidad, valor) descendente: primero los más frecuentes.
    grupos = sorted(Counter(valores).items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    patron = [n for _, n in grupos]
    escalera = _escalera_alta(valores)

    if escalera and color:
        return (8, escalera)
    if patron == [4, 1]:
        return (7, grupos[0][0], grupos[1][0])
    if patron == [3, 2]:
        return (6, grupos[0][0], grupos[1][0])
    if color:
        return (5,) + valores
    if escalera:
        return (4, escalera)
    if patron == [3, 1, 1]:
        return (3, grupos[0][0]) + tuple(v for v, _ in grupos[1:])
    if patron == [2, 2, 1]:
        return (2, grupos[0][0], grupos[1][0], grupos[2][0])
    if patron == [2, 1, 1, 1]:
        return (1, grupos[0][0]) + tuple(v for v, _ in grupos[1:])
    return (0,) + valores


def evaluar_mejor(cartas: Sequence[Carta]) -> Puntaje:
    """Mejor puntaje entre todas las combinaciones de 5 cartas (5 a 7 cartas)."""
    if not 5 <= len(cartas) <= 7:
        raise ValueError("evaluar_mejor requiere entre 5 y 7 cartas")
    return max(evaluar_cinco(combo) for combo in combinations(cartas, 5))


def nombre_categoria(puntaje: Puntaje) -> str:
    return CATEGORIAS[puntaje[0]]
