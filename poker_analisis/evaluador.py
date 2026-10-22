"""Evaluador de manos de Texas Hold'em: 5 cartas y mejor 5 de 7.

Una mano se representa con una tupla comparable de forma lexicográfica.
El primer elemento es la categoría (0 = carta alta ... 8 = escalera de color),
seguido de los desempates necesarios para ordenar manos de la misma categoría.
Mayor tupla significa mano más fuerte.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import List, Sequence, Tuple

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


def evaluar_mejor_referencia(cartas: Sequence[Carta]) -> Puntaje:
    """Mejor puntaje probando todas las combinaciones de 5 cartas (5 a 7 cartas).

    Es la implementación lenta y simple. Se conserva como referencia para verificar
    `evaluar_mejor` en las pruebas.
    """
    if not 5 <= len(cartas) <= 7:
        raise ValueError("evaluar_mejor_referencia requiere entre 5 y 7 cartas")
    return max(evaluar_cinco(combo) for combo in combinations(cartas, 5))


def _escalera_en_mascara(mascara: int) -> int:
    """Carta más alta de la escalera contenida en una máscara de valores (bit v = valor v).

    El as también cuenta como 1 para la rueda (A-2-3-4-5). Devuelve 0 si no hay escalera.
    """
    if mascara & (1 << 14):
        mascara |= 1 << 1
    for alta in range(14, 4, -1):
        ventana = 0b11111 << (alta - 4)
        if mascara & ventana == ventana:
            return alta
    return 0


def evaluar_mejor(cartas: Sequence[Carta]) -> Puntaje:
    """Mejor puntaje de 5 a 7 cartas, sin enumerar combinaciones.

    Cuenta valores y palos una sola vez y decide la categoría directamente. Devuelve
    exactamente la misma tupla que `evaluar_mejor_referencia` (verificado en las pruebas
    con manos al azar y con manos sesgadas hacia escaleras, colores y fulls), pero es
    unas 20 veces más rápida, que es lo que importa en Monte Carlo y en la simulación.
    """
    if not 5 <= len(cartas) <= 7:
        raise ValueError("evaluar_mejor requiere entre 5 y 7 cartas")

    cuenta = [0] * 15
    mascara_palo: dict = {}
    cuenta_palo: dict = {}
    for c in cartas:
        v, p = c.valor, c.palo
        cuenta[v] += 1
        mascara_palo[p] = mascara_palo.get(p, 0) | (1 << v)
        cuenta_palo[p] = cuenta_palo.get(p, 0) + 1

    color = 0  # máscara de valores del palo con 5 o más cartas (en 7 cartas solo puede haber uno)
    for p, n in cuenta_palo.items():
        if n >= 5:
            color = mascara_palo[p]
    if color:
        alta = _escalera_en_mascara(color)
        if alta:
            return (8, alta)

    poker: List[int] = []
    trios: List[int] = []
    parejas: List[int] = []
    sueltas: List[int] = []
    for v in range(14, 1, -1):  # de mayor a menor, así cada lista queda ordenada
        n = cuenta[v]
        if n == 4:
            poker.append(v)
        elif n == 3:
            trios.append(v)
        elif n == 2:
            parejas.append(v)
        elif n == 1:
            sueltas.append(v)

    if poker:
        return (7, poker[0], max(trios + parejas + sueltas))
    if trios and (len(trios) > 1 or parejas):
        pareja = max(parejas[0] if parejas else 0, trios[1] if len(trios) > 1 else 0)
        return (6, trios[0], pareja)
    if color:
        valores = [v for v in range(14, 1, -1) if color >> v & 1]
        return (5,) + tuple(valores[:5])

    mascara = 0
    for v in range(2, 15):
        if cuenta[v]:
            mascara |= 1 << v
    alta = _escalera_en_mascara(mascara)
    if alta:
        return (4, alta)
    if trios:
        kickers = sorted(parejas + sueltas, reverse=True)[:2]
        return (3, trios[0]) + tuple(kickers)
    if len(parejas) >= 2:
        resto = parejas[2:] + sueltas  # la tercera pareja de 7 cartas también puede ser kicker
        return (2, parejas[0], parejas[1], max(resto) if resto else 0)
    if parejas:
        return (1, parejas[0]) + tuple(sueltas[:3])
    return (0,) + tuple(sueltas[:5])


def nombre_categoria(puntaje: Puntaje) -> str:
    return CATEGORIAS[puntaje[0]]
