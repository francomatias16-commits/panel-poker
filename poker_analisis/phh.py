"""Importador del formato PHH (Poker Hand History) para Texas Hold'em No Limit.

El formato es TOML con una lista de acciones en texto, por ejemplo:
    "d dh p1 AsKd"      reparto de cartas a un jugador
    "d db 7h8c2s"       reparto de cartas del tablero
    "p2 cbr 6"          apuesta o subida hasta un total
    "p2 cc"             pasa o iguala
    "p2 f"              se retira

Cada mano se valida al importarla. Las manos que no cumplen el formato no se
descartan en silencio: se devuelven con el motivo del rechazo (RNF / criterio
de éxito del parser).
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .cartas import Carta

VARIANTES_SOPORTADAS = ("NT",)  # No Limit Texas Hold'em
CALLES = ("preflop", "flop", "turn", "river")
TIPOS_ACCION = ("pb", "cc", "cbr", "f", "sm", "sd")


def clave_natural(nombre: str) -> list:
    """Clave de orden "natural": los números se comparan como números ('2.phh' < '10.phh').

    El orden alfabético puso '10.phh' antes de '2.phh' y rompía el orden cronológico que
    necesita la validación temporal.
    """
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", nombre) if t]


class ErrorPHH(ValueError):
    """Mano rechazada por no cumplir el formato o el alcance del proyecto."""


@dataclass(frozen=True)
class Evento:
    calle: str
    jugador: Optional[int]  # asiento 1-based; None para repartos de tablero
    tipo: str  # 'reparto_cartas', 'reparto_tablero', 'pb', 'cc', 'cbr', 'f', 'sm', 'sd'
    monto: Optional[int] = None
    cartas: Tuple[Optional[Carta], ...] = ()  # None = carta oculta


@dataclass
class Mano:
    variante: str
    antes: List[int]
    blinds: List[int]
    stacks_iniciales: List[int]
    eventos: List[Evento] = field(default_factory=list)
    cartas_jugadores: dict = field(default_factory=dict)  # asiento -> tuple de cartas
    tablero: List[Carta] = field(default_factory=list)
    metadatos: dict = field(default_factory=dict)


def _parsear_cartas(texto: str) -> Tuple[Optional[Carta], ...]:
    """Convierte '7h8c2s' o 'AsKd' en cartas; '??' es oculta y '-' se ignora."""
    texto = texto.replace("-", "")
    if len(texto) % 2 != 0:
        raise ErrorPHH(f"cadena de cartas con longitud impar: {texto!r}")
    cartas: List[Optional[Carta]] = []
    for i in range(0, len(texto), 2):
        par = texto[i : i + 2]
        if par == "??":
            cartas.append(None)
        else:
            try:
                cartas.append(Carta.desde_texto(par))
            except ValueError as e:
                raise ErrorPHH(f"carta inválida {par!r}") from e
    return tuple(cartas)


def _parsear_jugador(token: str) -> int:
    if not (token.startswith("p") and token[1:].isdigit()):
        raise ErrorPHH(f"identificador de jugador inválido: {token!r}")
    return int(token[1:])


def _parsear_accion(linea: str, calle: str, tablero_actual: List[Carta]) -> Optional[Evento]:
    sin_comentario = linea.split("#", 1)[0].strip()
    if not sin_comentario:
        return None
    partes = sin_comentario.split()

    if partes[0] == "d":
        if len(partes) < 3:
            raise ErrorPHH(f"reparto incompleto: {linea!r}")
        if partes[1] == "dh":
            if len(partes) != 4:
                raise ErrorPHH(f"reparto de cartas mal formado: {linea!r}")
            jugador = _parsear_jugador(partes[2])
            return Evento(calle, jugador, "reparto_cartas", cartas=_parsear_cartas(partes[3]))
        if partes[1] == "db":
            cartas = _parsear_cartas(partes[2])
            if any(c is None for c in cartas):
                raise ErrorPHH("el tablero no puede tener cartas ocultas")
            return Evento(calle, None, "reparto_tablero", cartas=cartas)
        raise ErrorPHH(f"tipo de reparto desconocido: {linea!r}")

    jugador = _parsear_jugador(partes[0])
    if len(partes) < 2 or partes[1] not in TIPOS_ACCION:
        raise ErrorPHH(f"acción desconocida: {linea!r}")
    tipo = partes[1]

    if tipo in ("cbr", "pb"):
        if tipo == "cbr":
            if len(partes) != 3:
                raise ErrorPHH(f"apuesta sin monto válido: {linea!r}")
            try:
                valor = float(partes[2])
            except ValueError as e:
                raise ErrorPHH(f"apuesta sin monto válido: {linea!r}") from e
            if valor <= 0:
                raise ErrorPHH(f"apuesta no positiva: {linea!r}")
            # Los datasets en dólares (HandHQ) usan montos decimales.
            return Evento(calle, jugador, tipo, monto=int(valor) if valor.is_integer() else valor)
        return Evento(calle, jugador, tipo)
    if tipo in ("sm", "sd"):
        cartas = _parsear_cartas(partes[2]) if len(partes) > 2 else ()
        return Evento(calle, jugador, tipo, cartas=cartas)
    return Evento(calle, jugador, tipo)


def parsear_mano(texto: str) -> Mano:
    """Parsea y valida una mano PHH desde su texto TOML."""
    try:
        datos = tomllib.loads(texto)
    except tomllib.TOMLDecodeError as e:
        raise ErrorPHH(f"TOML inválido: {e}") from e

    variante = datos.get("variant")
    if variante not in VARIANTES_SOPORTADAS:
        raise ErrorPHH(f"variante fuera de alcance: {variante!r}")

    antes = datos.get("antes", [])
    blinds = datos.get("blinds_or_straddles", [])
    stacks = datos.get("starting_stacks", [])
    if not (len(antes) == len(blinds) == len(stacks) >= 2):
        raise ErrorPHH("antes, blinds_or_straddles y starting_stacks deben tener un valor por jugador (mínimo 2)")
    # Los stacks pueden ser 'inf' (dataset HandHQ). Los finitos deben ser enteros positivos.
    if any(not isinstance(s, (int, float)) or s <= 0 for s in stacks):
        raise ErrorPHH("los stacks iniciales deben ser positivos")

    mano = Mano(variante=variante, antes=list(antes), blinds=list(blinds), stacks_iniciales=list(stacks))
    mano.metadatos = {k: v for k, v in datos.items() if k not in
                      ("variant", "antes", "blinds_or_straddles", "starting_stacks", "actions", "min_bet")}

    calle = "preflop"
    cartas_vistas: List[Carta] = []
    for linea in datos.get("actions", []):
        evento = _parsear_accion(linea, calle, mano.tablero)
        if evento is None:
            continue
        if evento.jugador is not None and not 1 <= evento.jugador <= len(stacks):
            raise ErrorPHH(f"jugador fuera de rango: p{evento.jugador}")

        if evento.tipo == "reparto_cartas":
            if evento.jugador in mano.cartas_jugadores:
                raise ErrorPHH(f"cartas repetidas para el jugador p{evento.jugador}")
            mano.cartas_jugadores[evento.jugador] = evento.cartas
            cartas_vistas.extend(c for c in evento.cartas if c is not None)

        elif evento.tipo == "reparto_tablero":
            mano.tablero.extend(evento.cartas)
            cartas_vistas.extend(evento.cartas)
            calle = {3: "flop", 4: "turn", 5: "river"}.get(len(mano.tablero))
            if calle is None:
                raise ErrorPHH(f"el tablero tiene {len(mano.tablero)} cartas, esperado 3, 4 o 5")

        mano.eventos.append(evento)

    if len(cartas_vistas) != len(set(cartas_vistas)):
        raise ErrorPHH("hay cartas repetidas entre jugadores y tablero")
    return mano


def importar_archivo(ruta: str) -> Tuple[List[Mano], List[Tuple[str, str]]]:
    """Importa un archivo con una o más manos (separadas por línea en blanco doble).

    Devuelve (manos_válidas, rechazos) donde cada rechazo es (identificador, motivo).
    """
    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read()

    manos: List[Mano] = []
    rechazos: List[Tuple[str, str]] = []
    for indice, bloque in enumerate(contenido.split("\n\n\n"), start=1):
        if not bloque.strip():
            continue
        try:
            manos.append(parsear_mano(bloque))
        except ErrorPHH as e:
            rechazos.append((f"{os.path.basename(ruta)}#{indice}", str(e)))
    return manos, rechazos
