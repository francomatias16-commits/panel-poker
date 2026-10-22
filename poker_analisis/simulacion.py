"""Generación de manos simuladas en una mesa de bots, con stacks acotados.

Modelo de cash game: stack máximo de 100 BB. Lo que excede se retira y quien
queda por debajo de 2 BB recarga. El neto por mano no depende de las recargas.
"""

from __future__ import annotations

from typing import List

from .bots import BotAleatorio, BotPasivo, BotTAG
from .cartas import Mazo
from .motor import ResultadoMano, jugar_mano

BLIND_CHICO, BLIND_GRANDE = 1, 2
STACK_INICIAL = 200  # 100 big blinds
PERFILES = ["TAG-1", "TAG-2", "Pasivo-1", "TAG-3", "Pasivo-2", "Aleatorio"]


UMBRAL_TAG = 0.60  # recalibrado: con 0,55 los TAG jugaban cerca del 37 % de las manos (agresivos sueltos)


def crear_politicas(tabla, semilla: int, umbral_tag: float = UMBRAL_TAG) -> list:
    politicas = []
    for k, nombre in enumerate(PERFILES):
        s = semilla * 100 + k
        if nombre.startswith("TAG"):
            politicas.append(BotTAG(tabla, BLIND_GRANDE, umbral_preflop=umbral_tag, semilla=s))
        elif nombre.startswith("Pasivo"):
            politicas.append(BotPasivo(tabla, BLIND_GRANDE, semilla=s))
        else:
            politicas.append(BotAleatorio(semilla=s))
    return politicas


def simular_mesa(tabla, manos: int, semilla: int = 7, umbral_tag: float = UMBRAL_TAG) -> List[ResultadoMano]:
    """Juega `manos` manos consecutivas y devuelve sus resultados."""
    n = len(PERFILES)
    politicas = crear_politicas(tabla, semilla, umbral_tag)
    stacks = [STACK_INICIAL] * n
    resultados: List[ResultadoMano] = []

    for h in range(manos):
        for i in range(n):
            if stacks[i] > STACK_INICIAL:
                stacks[i] = STACK_INICIAL
            elif stacks[i] < 2 * BLIND_GRANDE:
                stacks[i] = STACK_INICIAL
        r = jugar_mano(
            stacks,
            boton=h % n,
            blind_chico=BLIND_CHICO,
            blind_grande=BLIND_GRANDE,
            politicas=politicas,
            mazo=Mazo(semilla=semilla * 1_000_000 + h),
        )
        resultados.append(r)
        stacks = r.stacks_finales
    return resultados
