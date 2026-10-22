"""Bots de referencia para la simulación.

Son perfiles simples, pensados para generar datos con estilos distintos, no
para competir a nivel profesional. Cada bot usa la misma interfaz: recibe una
Vista y devuelve una acción.
"""

from __future__ import annotations

import csv
import random
from typing import Dict, Tuple

from .cartas import Carta, RANGOS
from .equity import equity
from .motor import Accion, Vista, grupo_posicion


def clave_mano(cartas: Tuple[Carta, ...]) -> str:
    """Notación canónica de la mano: 'AA', 'AKs' o 'AKo'."""
    a, b = sorted(cartas, key=lambda c: c.valor, reverse=True)
    ra, rb = RANGOS[a.valor - 2], RANGOS[b.valor - 2]
    if a.valor == b.valor:
        return ra + rb
    return ra + rb + ("s" if a.palo == b.palo else "o")


def cargar_tabla_preflop(ruta: str) -> Dict[str, float]:
    """Lee la tabla de equity preflop generada por scripts/tabla_preflop.py."""
    with open(ruta, encoding="utf-8") as f:
        return {fila["mano"]: float(fila["equity"]) for fila in csv.DictReader(f)}


class _BotBase:
    def __init__(self, tabla: Dict[str, float], bb: int, iteraciones: int, semilla: int) -> None:
        self.tabla = tabla
        self.bb = bb
        self.iteraciones = iteraciones
        self._contador = semilla * 1_000_003

    def _equity(self, v: Vista) -> float:
        self._contador += 1
        return equity(
            v.cartas,
            v.tablero,
            n_rivales_aleatorios=max(1, len(v.activos) - 1),
            iteraciones=self.iteraciones,
            semilla=self._contador,
        ).equity


# Ajuste del umbral preflop según la posición: más amplio desde el botón, más cerrado desde temprana.
AJUSTE_POSICION = {"temprana": 0.05, "media": 0.0, "tardia": -0.03, "blinds": -0.02, "boton": -0.07}


class BotTAG(_BotBase):
    """Tight-agresivo: juega pocas manos fuertes según la posición y las apuesta con iniciativa."""

    def __init__(self, tabla, bb, umbral_preflop: float = 0.60, iteraciones: int = 60, semilla: int = 0):
        super().__init__(tabla, bb, iteraciones, semilla)
        self.umbral = umbral_preflop

    def __call__(self, v: Vista) -> Accion:
        if v.calle == "preflop":
            grupo = grupo_posicion(v.asiento, v.boton, len(v.stacks))
            umbral = self.umbral + AJUSTE_POSICION[grupo]
            if self.tabla[clave_mano(v.cartas)] >= umbral:
                if v.puede_subir:
                    return ("cbr", 3 * max(self.bb, v.apuesta_actual))
                return ("cc", None)
            return ("f", None) if v.pagar > 0 else ("cc", None)

        eq = self._equity(v)
        if eq >= 0.65 and v.puede_subir:
            return ("cbr", v.apuesta_actual + max(self.bb, int(v.bote * 0.66)))
        if eq >= 0.45 or v.pagar == 0:
            return ("cc", None)
        return ("f", None)


class BotPasivo(_BotBase):
    """Estación de llamadas: iguala casi todo y rara vez apuesta."""

    def __init__(self, tabla, bb, iteraciones: int = 60, semilla: int = 0):
        super().__init__(tabla, bb, iteraciones, semilla)

    def __call__(self, v: Vista) -> Accion:
        if v.calle == "preflop":
            if self.tabla[clave_mano(v.cartas)] >= 0.35 or v.pagar <= self.bb:
                return ("cc", None)
            return ("f", None)

        if v.pagar == 0:
            return ("cc", None)
        return ("cc", None) if self._equity(v) >= 0.3 else ("f", None)


class BotAleatorio:
    """Elige al azar entre las acciones legales. Útil para pruebas de estrés."""

    def __init__(self, semilla: int = 0) -> None:
        self.rng = random.Random(semilla)

    def __call__(self, v: Vista) -> Accion:
        r = self.rng.random()
        if v.pagar > 0 and r < 0.3:
            return ("f", None)
        if v.puede_subir and r > 0.75:
            lo = min(v.minimo_hasta, v.maximo_hasta)
            return ("cbr", self.rng.randint(lo, v.maximo_hasta))
        return ("cc", None)
