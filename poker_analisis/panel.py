"""Lógica del panel de escritorio, sin interfaz gráfica (así se puede probar).

Decisiones del proyecto (docs/02_decisiones.md):
- Los jugadores se analizan por stake, nunca mezclando niveles. Si no se indica `bb`, las manos
  se agrupan por el monto de su big blind (requiere que la mano lo traiga, como GGPoker).
- Umbral de muestra = muestra completa: un perfil se considera suficiente solo si el jugador
  participó en todas las manos del stake. Con `umbral_manos` entero se usa ese mínimo.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .estadisticas import CalculadorEstadisticas
from .ggpoker import iterar_directorio as iterar_ggpoker
from .motor import ResultadoMano
from .real import iterar_directorio
from .riesgo import max_drawdown, prob_ruina_analitica, resumen


@dataclass
class FilaJugador:
    nombre: str
    stake: int  # big blind en las unidades de la fuente (centavos en GGPoker)
    manos: int
    vpip: float
    pfr: float
    tres_bet: Optional[float]
    af: Optional[float]
    wtsd: Optional[float]
    wsd: Optional[float]
    cbet: Optional[float]
    fold_cbet: Optional[float]
    bb100: float
    ic95: float
    desvio_bb100: Optional[float]
    drawdown_bb: Optional[float]
    ruina_100bi: Optional[float]  # probabilidad de ruina con 100 buy-ins de 100 bb
    muestra_suficiente: bool


@dataclass
class Panel:
    filas: List[FilaJugador]
    manos_validas: int
    rechazos: List[Tuple[str, str]]


class _Stake:
    """Acumula, de a una mano, las estadísticas de un stake y la serie de netos de cada jugador.

    Guarda por jugador dos arreglos de doubles (netos en bb e instante de la mano), así que el
    costo de memoria es de 16 bytes por mano y jugador, sin retener las manos.
    """

    def __init__(self, stake: int) -> None:
        self.stake = stake
        self.calc = CalculadorEstadisticas(stake)
        self.manos = 0
        self.todas_con_fecha = True
        self.instantes: Dict[str, array] = {}

    def agregar(self, mano: ResultadoMano) -> None:
        self.manos += 1
        self.todas_con_fecha = self.todas_con_fecha and mano.fecha is not None
        instante = mano.fecha.timestamp() if mano.fecha is not None else math.nan
        self.calc.agregar(mano)
        for nombre in mano.nombres or ():
            self.instantes.setdefault(nombre, array("d")).append(instante)

    def serie(self, jugador: str) -> List[float]:
        """Netos en bb del jugador. Si todas las manos traen fecha, en orden cronológico;
        si no, en el orden en que llegaron (las fechas parciales no se pueden usar)."""
        netos = list(self.calc.series[jugador])
        if not self.todas_con_fecha:
            return netos
        instantes = self.instantes[jugador]
        orden = sorted(range(len(netos)), key=instantes.__getitem__)  # estable: empates en orden de llegada
        return [netos[i] for i in orden]


def _analizar(
    manos: Iterable[ResultadoMano], bb: Optional[int], umbral_manos: Optional[int]
) -> Tuple[List[FilaJugador], int]:
    """Procesa las manos en una sola pasada, sin guardarlas. Devuelve (filas, manos_procesadas)."""
    stakes: Dict[int, _Stake] = {}
    total = 0
    for m in manos:
        stake = bb if bb is not None else m.ciega_grande
        if stake is None:
            raise ValueError("las manos no traen el big blind: indicá `bb`")
        stakes.setdefault(stake, _Stake(stake)).agregar(m)
        total += 1

    filas: List[FilaJugador] = []
    for stake, grupo in sorted(stakes.items()):
        stats = {s.nombre: s for s in grupo.calc.resultados()}
        for nombre in sorted(grupo.instantes):
            s = stats[nombre]
            serie = grupo.serie(nombre)
            desvio = drawdown = ruina = None
            if len(serie) >= 2:
                r = resumen(serie)
                desvio = r["desvio_bb100"]
                drawdown = max_drawdown(serie)
                ruina = prob_ruina_analitica(r["winrate_bb100"], desvio, 100 * 100)
            minimo = grupo.manos if umbral_manos is None else umbral_manos
            filas.append(FilaJugador(
                nombre, stake, s.manos, s.vpip, s.pfr, s.tres_bet, s.af, s.wtsd, s.wsd,
                s.cbet, s.fold_cbet, s.bb100, s.bb100_ic95, desvio, drawdown, ruina, s.manos >= minimo,
            ))
    filas.sort(key=lambda f: (f.stake, -f.manos))
    return filas, total


def analizar_manos(
    manos: Iterable[ResultadoMano], bb: Optional[int] = None, umbral_manos: Optional[int] = None
) -> List[FilaJugador]:
    """Tabla del panel para un iterable de manos (puede ser un generador: no se guardan todas)."""
    return _analizar(manos, bb, umbral_manos)[0]


def analizar_directorio(
    ruta: str, bb: Optional[int] = None, umbral_manos: Optional[int] = None, formato: str = "phh"
) -> Panel:
    rechazos: List[Tuple[str, str]] = []
    if formato in ("texto", "ggpoker", "pokerstars"):
        manos = iterar_ggpoker(ruta, rechazos)  # en streaming: las manos no se acumulan en memoria
    elif formato == "phh":
        manos = iterar_directorio(ruta, rechazos)
    else:
        raise ValueError(f"formato desconocido: {formato}")
    filas, total = _analizar(manos, bb, umbral_manos)
    return Panel(filas, total, rechazos)


def a_csv(panel: Panel, ruta: str) -> None:
    """Exporta la tabla (RF-09). Escribe todas las filas e indica si la muestra alcanza."""
    import csv
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["jugador", "stake", "manos", "vpip", "pfr", "3bet", "af", "wtsd", "wsd", "cbet", "fold_cbet", "bb100",
                    "ic95", "desvio_bb100", "drawdown_bb", "ruina_100bi", "muestra_suficiente"])
        for x in panel.filas:
            w.writerow([x.nombre, x.stake, x.manos, x.vpip, x.pfr, x.tres_bet, x.af, x.wtsd, x.wsd, x.cbet, x.fold_cbet,
                        x.bb100, x.ic95, x.desvio_bb100, x.drawdown_bb, x.ruina_100bi,
                        x.muestra_suficiente])
