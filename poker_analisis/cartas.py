"""Representación de cartas y mazo para Texas Hold'em."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Optional

RANGOS = "23456789TJQKA"
PALOS = "cdhs"  # clubs, diamonds, hearts, spades
VALOR_RANGO = {r: i + 2 for i, r in enumerate(RANGOS)}  # 2..14 (A = 14)


@dataclass(frozen=True, order=True)
class Carta:
    """Una carta con valor numérico (2..14) y palo (c, d, h, s)."""

    valor: int
    palo: str

    def __post_init__(self) -> None:
        if not 2 <= self.valor <= 14:
            raise ValueError(f"valor fuera de rango: {self.valor}")
        if self.palo not in PALOS:
            raise ValueError(f"palo inválido: {self.palo!r}")

    @classmethod
    def desde_texto(cls, texto: str) -> "Carta":
        """Crea una carta desde notación corta, por ejemplo 'As', 'Td', '7h'."""
        if len(texto) != 2:
            raise ValueError(f"notación inválida: {texto!r}")
        rango, palo = texto[0].upper(), texto[1].lower()
        if rango not in VALOR_RANGO:
            raise ValueError(f"rango inválido: {texto!r}")
        return cls(VALOR_RANGO[rango], palo)

    def __str__(self) -> str:
        return RANGOS[self.valor - 2] + self.palo


def parsear_cartas(texto: str) -> List[Carta]:
    """Parsea una lista separada por espacios, por ejemplo 'As Kd 7h'."""
    return [Carta.desde_texto(t) for t in texto.split()]


class Mazo:
    """Mazo de 52 cartas con barajado Fisher-Yates.

    Por defecto usa un generador criptográfico del sistema. Pasando una
    semilla se obtiene un barajado reproducible, útil para simulaciones
    con resultados verificables (RNF-01).
    """

    def __init__(self, semilla: Optional[int] = None, excluir: Iterable[Carta] = ()):
        self._rng: random.Random = (
            random.Random(semilla) if semilla is not None else random.SystemRandom()
        )
        excluidas = set(excluir)
        self._cartas: List[Carta] = [
            Carta(v, p) for p in PALOS for v in range(2, 15) if Carta(v, p) not in excluidas
        ]
        self.barajar()

    def barajar(self) -> None:
        # random.shuffle implementa Fisher-Yates.
        self._rng.shuffle(self._cartas)

    def repartir(self, cantidad: int = 1) -> List[Carta]:
        if cantidad > len(self._cartas):
            raise ValueError("no quedan suficientes cartas en el mazo")
        repartidas = self._cartas[:cantidad]
        del self._cartas[:cantidad]
        return repartidas

    def __len__(self) -> int:
        return len(self._cartas)
