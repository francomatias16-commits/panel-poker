"""Motor de partida de Texas Hold'em No Limit (cash game, simulado).

Implementa:
- Blinds, reparto, rondas de apuestas (fold, check, call, bet, raise, all-in).
- Reglas de subida mínima y de reapertura de la apuesta tras un all-in corto.
- Botes principales y laterales, con empates repartidos desde el botón.
- Invariante de conservación de fichas, verificada al final de cada mano.

Las decisiones las toma una política por asiento: una función que recibe una
Vista del estado y devuelve una acción ('f', 'cc' o 'cbr' con el total objetivo).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Sequence, Tuple

from .cartas import Carta, Mazo
from .evaluador import evaluar_mejor
from .phh import Evento

Accion = Tuple[str, Optional[int]]


@dataclass(frozen=True)
class Vista:
    """Información que ve un jugador al decidir."""

    asiento: int
    cartas: Tuple[Carta, ...]
    tablero: Tuple[Carta, ...]
    calle: str
    bote: int  # fichas totales en el bote de la mano
    apuesta_actual: int  # mayor apuesta de la calle
    apuesta_propia: int  # lo que el jugador ya puso en la calle
    pagar: int  # fichas necesarias para igualar
    stack: int
    minimo_hasta: int  # total mínimo para subir
    maximo_hasta: int  # total máximo (all-in)
    puede_subir: bool
    activos: Tuple[int, ...]  # asientos que siguen en la mano
    stacks: Tuple[int, ...]
    boton: int = 0  # asiento del botón, para calcular la posición


Politica = Callable[[Vista], Accion]


@dataclass
class ResultadoMano:
    boton: int
    sb: int
    bb: int
    stacks_iniciales: List[int]
    stacks_finales: List[int]
    neto: List[int]
    cartas: List[Tuple[Carta, ...]]
    tablero: List[Carta]
    eventos: List[Evento]
    vieron_flop: List[int]
    llegaron_showdown: List[int]
    ganadores_showdown: List[int]
    nombres: Optional[List[str]] = None  # nombre de cada asiento, para manos reales
    ciega_grande: Optional[int] = None  # monto del big blind (en las unidades de los stacks), si se conoce
    ciega_chica: Optional[float] = None  # monto del small blind, si se conoce
    referencia: Optional[str] = None  # id de la mano en su fuente (para cargarla sin duplicar)
    archivo: Optional[str] = None  # archivo de origen, relativo a la carpeta cargada (trazabilidad)
    fecha: Optional[datetime] = None  # fecha y hora de la mano, si la fuente la trae (orden cronológico)


def construir_botes(contrib: Sequence[int], folded: Sequence[bool]) -> List[Tuple[int, List[int]]]:
    """Divide las fichas en botes principal y laterales.

    Devuelve (monto, elegibles) por bote. Un jugador retirado aporta fichas al
    bote pero no puede ganarlo. La suma de montos es igual a la suma de aportes.
    """
    n = len(contrib)
    botes: List[Tuple[int, List[int]]] = []
    previo = 0
    arrastre = 0
    for nivel in sorted({c for c in contrib if c > 0}):
        monto = sum(min(c, nivel) - min(c, previo) for c in contrib) + arrastre
        elegibles = [i for i in range(n) if contrib[i] >= nivel and not folded[i]]
        previo = nivel
        if not elegibles:
            arrastre = monto
            continue
        botes.append((monto, elegibles))
        arrastre = 0
    if arrastre and botes:
        monto, elegibles = botes[-1]
        botes[-1] = (monto + arrastre, elegibles)
    return botes


def _orden_desde(inicio: int, n: int) -> List[int]:
    return [(inicio + k) % n for k in range(n)]


def grupo_posicion(asiento: int, boton: int, n: int) -> str:
    """Grupo de posición preflop: 'boton', 'blinds', 'temprana', 'media' o 'tardia'.

    Los asientos después de las ciegas se dividen en tercios: temprana (primeros
    en actuar), media y tardía (los que actúan por último antes del botón).
    """
    o = (asiento - boton) % n
    if o == 0:
        return "boton"
    if o in (1, 2):
        return "blinds"
    restantes = n - 3
    r = o - 3
    if r < restantes / 3:
        return "temprana"
    if r < 2 * restantes / 3:
        return "media"
    return "tardia"


class _Mano:
    def __init__(
        self,
        stacks: Sequence[int],
        boton: int,
        blind_chico: int,
        blind_grande: int,
        politicas: Sequence[Politica],
        mazo: Mazo,
    ) -> None:
        self.n = len(stacks)
        if self.n < 2:
            raise ValueError("se necesitan al menos 2 jugadores")
        if any(s <= 0 for s in stacks):
            raise ValueError("todos los stacks deben ser positivos")
        if len(politicas) != self.n:
            raise ValueError("se necesita una política por jugador")

        n = self.n
        self.boton = boton % n
        if n == 2:
            self.sb = self.boton
            self.bb = (self.boton + 1) % 2
            self.primero_pre = self.sb
        else:
            self.sb = (self.boton + 1) % n
            self.bb = (self.boton + 2) % n
            self.primero_pre = (self.bb + 1) % n
        self.primero_post = (self.boton + 1) % n

        self.blind_chico = blind_chico
        self.blind_grande = blind_grande
        self.politicas = politicas
        self.mazo = mazo

        self.inicial = list(stacks)
        self.stack = list(stacks)
        self.contrib = [0] * n
        self.apuesta = [0] * n
        self.folded = [False] * n
        self.allin = [False] * n
        self.puede = [True] * n
        self.min_inc = blind_grande
        self.cartas: List[Tuple[Carta, ...]] = [() for _ in range(n)]
        self.tablero: List[Carta] = []
        self.eventos: List[Evento] = []

    def quedan(self) -> int:
        return sum(1 for f in self.folded if not f)

    def apuesta_max(self) -> int:
        return max(self.apuesta)

    def poner(self, i: int, monto: int) -> int:
        m = min(monto, self.stack[i])
        if m <= 0:
            return 0
        self.stack[i] -= m
        self.apuesta[i] += m
        self.contrib[i] += m
        if self.stack[i] == 0:
            self.allin[i] = True
        return m

    def vista(self, i: int, calle: str) -> Vista:
        amax = self.apuesta_max()
        pagar = amax - self.apuesta[i]
        return Vista(
            asiento=i,
            cartas=self.cartas[i],
            tablero=tuple(self.tablero),
            calle=calle,
            bote=sum(self.contrib),
            apuesta_actual=amax,
            apuesta_propia=self.apuesta[i],
            pagar=pagar,
            stack=self.stack[i],
            minimo_hasta=amax + self.min_inc,
            maximo_hasta=self.apuesta[i] + self.stack[i],
            puede_subir=self.puede[i] and self.stack[i] > pagar,
            activos=tuple(j for j in range(self.n) if not self.folded[j]),
            stacks=tuple(self.stack),
            boton=self.boton,
        )

    @staticmethod
    def _validar(accion: Accion, v: Vista) -> Accion:
        """Convierte la acción pedida en una acción legal."""
        tipo, total = accion
        if tipo == "f":
            return ("f", None) if v.pagar > 0 else ("cc", None)
        if tipo != "cbr" or not v.puede_subir:
            return ("cc", None)
        objetivo = v.minimo_hasta if total is None else int(total)
        if objetivo > v.maximo_hasta:
            objetivo = v.maximo_hasta
        if objetivo < v.minimo_hasta:
            objetivo = min(v.minimo_hasta, v.maximo_hasta)
        if objetivo <= v.apuesta_actual:
            return ("cc", None)
        return ("cbr", objetivo)

    def ronda(self, calle: str, primero: int) -> None:
        n = self.n
        cola = deque(j for j in _orden_desde(primero, n) if not self.folded[j] and not self.allin[j])
        en_cola = set(cola)
        while cola:
            i = cola.popleft()
            en_cola.discard(i)
            if self.folded[i] or self.allin[i] or self.quedan() <= 1:
                continue

            v = self.vista(i, calle)
            tipo, total = self._validar(self.politicas[i](v), v)

            if tipo == "f":
                self.folded[i] = True
                self.eventos.append(Evento(calle, i + 1, "f"))
                continue

            if tipo == "cc":
                if v.pagar == 0:
                    self.eventos.append(Evento(calle, i + 1, "cc"))
                else:
                    m = self.poner(i, v.pagar)
                    self.eventos.append(Evento(calle, i + 1, "cc", monto=m))
                self.puede[i] = False
                continue

            # Apuesta o subida hasta `total`.
            amax = self.apuesta_max()
            self.poner(i, total - self.apuesta[i])
            real = self.apuesta[i]
            subida = real - amax
            reabre = subida >= self.min_inc
            if reabre:
                self.min_inc = subida
            self.eventos.append(Evento(calle, i + 1, "cbr", monto=real))
            self.puede[i] = False

            for j in _orden_desde(i + 1, n):
                if j == i or self.folded[j] or self.allin[j] or self.apuesta[j] >= real:
                    continue
                if reabre:
                    self.puede[j] = True
                if j not in en_cola:
                    cola.append(j)
                    en_cola.add(j)

    def run(self) -> ResultadoMano:
        n = self.n
        for seat in range(n):
            self.cartas[seat] = tuple(self.mazo.repartir(2))
            self.eventos.append(Evento("preflop", seat + 1, "reparto_cartas", cartas=self.cartas[seat]))

        self.poner(self.sb, self.blind_chico)
        self.poner(self.bb, self.blind_grande)
        self.ronda("preflop", self.primero_pre)
        vieron_flop = [i for i in range(n) if not self.folded[i]]

        for calle, cantidad in (("flop", 3), ("turn", 1), ("river", 1)):
            if self.quedan() <= 1:
                break
            cartas = self.mazo.repartir(cantidad)
            self.tablero.extend(cartas)
            self.eventos.append(Evento(calle, None, "reparto_tablero", cartas=tuple(cartas)))
            self.apuesta = [0] * n
            self.min_inc = self.blind_grande
            self.puede = [True] * n  # cada calle empieza con derecho a apostar
            if sum(1 for j in range(n) if not self.folded[j] and not self.allin[j]) >= 2:
                self.ronda(calle, self.primero_post)

        llegaron: List[int] = []
        ganadores: set = set()
        if self.quedan() >= 2:
            if len(self.tablero) != 5:
                raise RuntimeError("showdown sin tablero completo")
            llegaron = [i for i in range(n) if not self.folded[i]]
            for i in llegaron:
                self.eventos.append(Evento("river", i + 1, "sm", cartas=self.cartas[i]))
            orden = _orden_desde(self.primero_post, n)
            for monto, elegibles in construir_botes(self.contrib, self.folded):
                puntajes = {i: evaluar_mejor(list(self.cartas[i]) + self.tablero) for i in elegibles}
                mejor = max(puntajes.values())
                ganadores_bote = sorted(
                    (i for i in elegibles if puntajes[i] == mejor), key=orden.index
                )
                parte, resto = divmod(monto, len(ganadores_bote))
                for k, i in enumerate(ganadores_bote):
                    cuota = parte + (1 if k < resto else 0)
                    self.stack[i] += cuota
                    if cuota > 0:
                        ganadores.add(i)
        else:
            ganador = next(i for i in range(n) if not self.folded[i])
            self.stack[ganador] += sum(self.contrib)

        if sum(self.stack) != sum(self.inicial):
            raise RuntimeError("violación de conservación de fichas")

        return ResultadoMano(
            boton=self.boton,
            sb=self.sb,
            bb=self.bb,
            stacks_iniciales=list(self.inicial),
            stacks_finales=list(self.stack),
            neto=[f - i for f, i in zip(self.stack, self.inicial)],
            cartas=list(self.cartas),
            tablero=list(self.tablero),
            eventos=self.eventos,
            vieron_flop=vieron_flop,
            llegaron_showdown=llegaron,
            ganadores_showdown=sorted(ganadores),
        )


def jugar_mano(
    stacks: Sequence[int],
    boton: int,
    blind_chico: int,
    blind_grande: int,
    politicas: Sequence[Politica],
    mazo: Mazo,
) -> ResultadoMano:
    """Juega una mano completa y devuelve su resultado."""
    return _Mano(stacks, boton, blind_chico, blind_grande, politicas, mazo).run()
