"""Estadísticas de jugadores a partir de resultados de manos.

Métricas (las definiciones siguen la práctica habitual de trackers):
- VPIP: porcentaje de manos en que el jugador puso fichas voluntarias en preflop
  (subir, igualar o completar). Un check de big blind no cuenta.
- PFR: porcentaje de manos con subida preflop.
- 3-bet: re-subida sobre una subida previa, sobre las oportunidades de hacerla.
- AF (factor de agresión): (apuestas + subidas) / igualaciones, postflop.
- WTSD: porcentaje de flops vistos que llegan a showdown.
- W$SD: porcentaje de showdowns en que el jugador gana fichas.
- C-bet: apuesta en el flop del último agresor preflop, sobre las veces que le toca actuar primero
  (nadie apostó antes en el flop).
- Fold to c-bet: retiros ante una c-bet, sobre las veces que el jugador la enfrenta antes de que
  alguien suba. Cada mano cuenta una sola oportunidad por jugador.
- bb/100: ganancia en big blinds cada 100 manos, con intervalo de confianza del 95 %.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from .motor import ResultadoMano


@dataclass
class EstadisticasJugador:
    nombre: str
    manos: int
    vpip: float
    pfr: float
    tres_bet: Optional[float]
    af: Optional[float]
    wtsd: Optional[float]
    wsd: Optional[float]
    bb100: float
    bb100_ic95: float
    cbet: Optional[float] = None
    fold_cbet: Optional[float] = None


@dataclass
class _Acumulador:
    manos: int = 0
    voluntarias: int = 0
    pfr: int = 0
    oportunidades_3bet: int = 0
    tres_bet: int = 0
    agresiones: int = 0
    igualaciones: int = 0
    flops_vistos: int = 0
    showdowns: int = 0
    showdowns_ganados: int = 0
    oportunidades_cbet: int = 0
    cbets: int = 0
    oportunidades_fold_cbet: int = 0
    folds_cbet: int = 0
    netos_bb: array = None  # netos por mano en big blinds; array('d') ocupa 8 bytes por mano

    def __post_init__(self) -> None:
        if self.netos_bb is None:
            self.netos_bb = array("d")


@dataclass
class _EstadoPreflop:
    actuo: bool = False
    oportunidad: bool = False
    voluntaria: bool = False
    subio: bool = False
    tres_bet: bool = False


class CalculadorEstadisticas:
    """Calcula las estadísticas de a una mano por vez, sin retener las manos.

    `agregar(mano, nombres)` suma una mano a los contadores y a la serie de netos por jugador;
    `resultados()` arma la tabla. Guarda 8 bytes por mano y jugador (los netos en big blinds),
    así que un directorio entero se procesa en streaming sin cargar todas las manos.
    `series` da, por jugador, sus netos en big blinds en el orden en que se agregaron las manos.
    """

    def __init__(self, bb: float) -> None:
        self.bb = bb
        self._acumulados: Dict[str, _Acumulador] = {}

    @property
    def series(self) -> Dict[str, array]:
        return {nombre: a.netos_bb for nombre, a in self._acumulados.items()}

    def agregar(self, mano: ResultadoMano, nombres: Sequence[str] = ()) -> None:
        """Suma una mano. `nombres[i]` es el perfil del asiento i, salvo que la mano traiga sus propios nombres."""
        n = len(mano.neto)
        nombres_mano = mano.nombres or nombres  # las manos reales traen su propio orden de asientos
        estado = [_EstadoPreflop() for _ in range(n)]
        agresiones = [0] * n
        igualaciones = [0] * n
        subidas_previas = 0
        agresor = None  # último que subió preflop
        apostador_flop = None  # quien abrió las apuestas en el flop
        agresor_actuo = False
        ventana_cbet = False  # abierta mientras nadie suba la c-bet
        opor_cbet = [False] * n
        hizo_cbet = [False] * n
        opor_fcb = [False] * n
        hizo_fcb = [False] * n

        for e in mano.eventos:
            if e.jugador is None:
                continue
            s = e.jugador - 1
            if e.calle == "preflop":
                if e.tipo not in ("cbr", "cc", "f"):
                    continue
                st = estado[s]
                if not st.actuo:
                    st.actuo = True
                    st.oportunidad = subidas_previas == 1
                if e.tipo == "cbr":
                    st.voluntaria = True
                    st.subio = True
                    if subidas_previas == 1 and not st.tres_bet and st.oportunidad:
                        st.tres_bet = True
                    subidas_previas += 1
                    agresor = s
                elif e.tipo == "cc" and e.monto is not None:
                    st.voluntaria = True
            else:
                if e.calle == "flop" and e.tipo in ("cbr", "cc", "f"):
                    if s == agresor and not agresor_actuo:
                        agresor_actuo = True
                        if apostador_flop is None:
                            opor_cbet[s] = True
                            if e.tipo == "cbr":
                                hizo_cbet[s] = True
                                ventana_cbet = True
                    elif ventana_cbet and s != agresor and not opor_fcb[s]:
                        opor_fcb[s] = True
                        hizo_fcb[s] = e.tipo == "f"
                    if e.tipo == "cbr":
                        if apostador_flop is None:
                            apostador_flop = s
                        elif s != agresor:
                            ventana_cbet = False
                        elif ventana_cbet:
                            ventana_cbet = False  # re-subida del agresor tras una subida rival
                if e.tipo == "cbr":
                    agresiones[s] += 1
                elif e.tipo == "cc" and e.monto is not None:
                    igualaciones[s] += 1

        for s in range(n):
            st = estado[s]
            acum = self._acumulados.setdefault(nombres_mano[s], _Acumulador())
            acum.manos += 1
            acum.voluntarias += st.voluntaria
            acum.pfr += st.subio
            if st.oportunidad:
                acum.oportunidades_3bet += 1
                acum.tres_bet += st.tres_bet
            acum.agresiones += agresiones[s]
            acum.oportunidades_cbet += opor_cbet[s]
            acum.cbets += hizo_cbet[s]
            acum.oportunidades_fold_cbet += opor_fcb[s]
            acum.folds_cbet += hizo_fcb[s]
            acum.igualaciones += igualaciones[s]
            if s in mano.vieron_flop:
                acum.flops_vistos += 1
            if s in mano.llegaron_showdown:
                acum.showdowns += 1
                acum.showdowns_ganados += s in mano.ganadores_showdown
            acum.netos_bb.append(mano.neto[s] / self.bb)

    def resultados(self) -> List[EstadisticasJugador]:
        resultados = []
        for nombre, a in self._acumulados.items():
            m = a.manos
            netos = a.netos_bb
            media = sum(netos) / m
            if m > 1:
                desvio = math.sqrt(sum((x - media) ** 2 for x in netos) / (m - 1))
                error = 100 * desvio / math.sqrt(m)
            else:
                error = float("nan")
            resultados.append(
                EstadisticasJugador(
                    nombre=nombre,
                    manos=m,
                    vpip=a.voluntarias / m,
                    pfr=a.pfr / m,
                    tres_bet=a.tres_bet / a.oportunidades_3bet if a.oportunidades_3bet else None,
                    af=a.agresiones / a.igualaciones if a.igualaciones else None,
                    wtsd=a.showdowns / a.flops_vistos if a.flops_vistos else None,
                    wsd=a.showdowns_ganados / a.showdowns if a.showdowns else None,
                    bb100=100 * media,
                    bb100_ic95=1.96 * error,
                    cbet=a.cbets / a.oportunidades_cbet if a.oportunidades_cbet else None,
                    fold_cbet=a.folds_cbet / a.oportunidades_fold_cbet if a.oportunidades_fold_cbet else None,
                )
            )
        return resultados


def calcular(manos: Iterable[ResultadoMano], nombres: Sequence[str], bb: float) -> List[EstadisticasJugador]:
    """Calcula estadísticas por jugador. `nombres[i]` es el perfil del asiento i. Acepta cualquier iterable."""
    calc = CalculadorEstadisticas(bb)
    for mano in manos:
        calc.agregar(mano, nombres)
    return calc.resultados()


def _pct(x: Optional[float]) -> str:
    return "  -  " if x is None else f"{100 * x:5.1f}"


def formatear(stats: Sequence[EstadisticasJugador]) -> str:
    """Tabla de texto con las estadísticas."""
    encabezado = (
        f"{'perfil':<12}{'manos':>7}{'VPIP%':>8}{'PFR%':>8}{'3bet%':>8}"
        f"{'AF':>7}{'WTSD%':>8}{'W$SD%':>8}{'CB%':>7}{'FCB%':>7}{'bb/100':>9}{'  ±IC95':>10}"
    )
    lineas = [encabezado, "-" * len(encabezado)]
    for s in stats:
        af = "  -  " if s.af is None else f"{s.af:5.2f}"
        lineas.append(
            f"{s.nombre:<12}{s.manos:>7}{_pct(s.vpip):>8}{_pct(s.pfr):>8}{_pct(s.tres_bet):>8}"
            f"{af:>7}{_pct(s.wtsd):>8}{_pct(s.wsd):>8}{_pct(s.cbet):>7}{_pct(s.fold_cbet):>7}{s.bb100:>9.2f}{s.bb100_ic95:>10.2f}"
        )
    return "\n".join(lineas)
