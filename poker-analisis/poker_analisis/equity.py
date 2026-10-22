"""Equity y probabilidades de mejora para Texas Hold'em.

- equity(): Monte Carlo sobre runouts y manos de rivales, con error estándar.
- probabilidad_alcanzar_categoria(): cálculo exacto por enumeración del tablero
  pendiente (flop o turn).
- outs(): cartas que, en la próxima calle, llevan la mano a una categoría dada.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, List, Sequence, Tuple

from .cartas import Carta, PALOS
from .evaluador import evaluar_mejor

Mano = Sequence[Carta]


def _mazo_restante(excluir: Iterable[Carta]) -> List[Carta]:
    excluidas = set(excluir)
    return [Carta(v, p) for p in PALOS for v in range(2, 15) if Carta(v, p) not in excluidas]


def _validar_sin_repetidos(cartas: Sequence[Carta]) -> None:
    if len(set(cartas)) != len(cartas):
        raise ValueError("hay cartas repetidas entre mano, tablero y rivales")


@dataclass(frozen=True)
class ResultadoEquity:
    equity: float
    error_estandar: float
    iteraciones: int

    @property
    def intervalo_95(self) -> Tuple[float, float]:
        margen = 1.96 * self.error_estandar
        return max(0.0, self.equity - margen), min(1.0, self.equity + margen)


def equity(
    mano: Mano,
    tablero: Sequence[Carta] = (),
    rivales_conocidos: Sequence[Mano] = (),
    n_rivales_aleatorios: int = 1,
    iteraciones: int = 10_000,
    semilla: int | None = None,
) -> ResultadoEquity:
    """Equity de `mano` por Monte Carlo.

    Los empates se reparten en partes iguales. Los rivales conocidos tienen
    mano fija; los aleatorios reciben dos cartas al azar del mazo restante.
    Con una semilla fija el resultado es reproducible.
    """
    mano = list(mano)
    tablero = list(tablero)
    if len(mano) != 2:
        raise ValueError("la mano del héroe debe tener 2 cartas")
    if len(tablero) not in (0, 3, 4, 5):
        raise ValueError("el tablero debe tener 0, 3, 4 o 5 cartas")
    if n_rivales_aleatorios < 0 or len(rivales_conocidos) + n_rivales_aleatorios < 1:
        raise ValueError("se necesita al menos un rival")
    if iteraciones < 2:
        raise ValueError("se requieren al menos 2 iteraciones para el error estándar")

    fijas = mano + tablero + [c for r in rivales_conocidos for c in r]
    _validar_sin_repetidos(fijas)

    faltan_tablero = 5 - len(tablero)
    necesarias = faltan_tablero + 2 * n_rivales_aleatorios
    base = _mazo_restante(fijas)
    if necesarias > len(base):
        raise ValueError("no hay cartas suficientes para completar la simulación")

    rng = random.Random(semilla)
    reparto: List[float] = []
    for _ in range(iteraciones):
        muestra = rng.sample(base, necesarias)
        tab = tablero + muestra[:faltan_tablero]
        resto = muestra[faltan_tablero:]
        manos = [mano] + [list(r) for r in rivales_conocidos]
        manos += [resto[2 * i : 2 * i + 2] for i in range(n_rivales_aleatorios)]

        puntajes = [evaluar_mejor(h + tab) for h in manos]
        mejor = max(puntajes)
        if puntajes[0] == mejor:
            reparto.append(1.0 / puntajes.count(mejor))
        else:
            reparto.append(0.0)

    n = len(reparto)
    media = sum(reparto) / n
    varianza = sum((x - media) ** 2 for x in reparto) / (n - 1)
    return ResultadoEquity(media, math.sqrt(varianza / n), n)


def probabilidad_alcanzar_categoria(mano: Mano, tablero: Sequence[Carta], categoria: int) -> float:
    """Probabilidad exacta de que la mejor mano final alcance `categoria` o superior.

    Enumera todas las cartas que faltan para completar el tablero.
    Requiere flop (3 cartas) o turn (4 cartas).
    """
    mano, tablero = list(mano), list(tablero)
    if len(tablero) not in (3, 4):
        raise ValueError("requiere flop o turn; en preflop la enumeración es demasiado grande")
    _validar_sin_repetidos(mano + tablero)

    base = _mazo_restante(mano + tablero)
    faltan = 5 - len(tablero)
    total = 0
    exitos = 0
    for extra in combinations(base, faltan):
        total += 1
        if evaluar_mejor(mano + tablero + list(extra))[0] >= categoria:
            exitos += 1
    return exitos / total


def outs(mano: Mano, tablero: Sequence[Carta], categoria: int) -> List[Carta]:
    """Cartas que, en la próxima calle, llevan la mano a `categoria` o superior.

    Solo tiene sentido en flop o turn, y solo cuenta las cartas que no mejoran
    ya a la categoría actual.
    """
    mano, tablero = list(mano), list(tablero)
    if len(tablero) not in (3, 4):
        raise ValueError("requiere flop o turn")
    _validar_sin_repetidos(mano + tablero)

    actual = evaluar_mejor(mano + tablero)[0]
    if actual >= categoria:
        return []
    return [
        c
        for c in _mazo_restante(mano + tablero)
        if evaluar_mejor(mano + tablero + [c])[0] >= categoria
    ]
