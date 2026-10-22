"""Lógica del panel de escritorio, sin interfaz gráfica (así se puede probar).

Decisiones del proyecto (docs/02_decisiones.md):
- Los jugadores se analizan por stake, nunca mezclando niveles. Si no se indica `bb`, las manos
  se agrupan por el monto de su big blind (requiere que la mano lo traiga, como GGPoker).
- Umbral de muestra = muestra completa: un perfil se considera suficiente solo si el jugador
  participó en todas las manos del stake. Con `umbral_manos` entero se usa ese mínimo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .estadisticas import calcular
from .ggpoker import cargar_directorio as cargar_ggpoker
from .motor import ResultadoMano
from .real import cargar_directorio
from .riesgo import max_drawdown, prob_ruina_analitica, resumen, serie_neta


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


def analizar_manos(
    manos: Sequence[ResultadoMano], bb: Optional[int] = None, umbral_manos: Optional[int] = None
) -> List[FilaJugador]:
    grupos: Dict[int, List[ResultadoMano]] = {}
    for m in manos:
        stake = bb if bb is not None else m.ciega_grande
        if stake is None:
            raise ValueError("las manos no traen el big blind: indicá `bb`")
        grupos.setdefault(stake, []).append(m)
    filas: List[FilaJugador] = []
    for stake, grupo in sorted(grupos.items()):
        stats = {s.nombre: s for s in calcular(grupo, nombres=[], bb=stake)}
        for nombre in sorted({n for m in grupo if m.nombres for n in m.nombres}):
            s = stats.get(nombre)
            if s is None:
                continue
            serie = serie_neta(grupo, nombre, stake)
            desvio = drawdown = ruina = None
            if len(serie) >= 2:
                r = resumen(serie)
                desvio = r["desvio_bb100"]
                drawdown = max_drawdown(serie)
                ruina = prob_ruina_analitica(r["winrate_bb100"], desvio, 100 * 100)
            minimo = len(grupo) if umbral_manos is None else umbral_manos
            filas.append(FilaJugador(
                nombre, stake, s.manos, s.vpip, s.pfr, s.tres_bet, s.af, s.wtsd, s.wsd,
                s.cbet, s.fold_cbet, s.bb100, s.bb100_ic95, desvio, drawdown, ruina, s.manos >= minimo,
            ))
    filas.sort(key=lambda f: (f.stake, -f.manos))
    return filas


def analizar_directorio(
    ruta: str, bb: Optional[int] = None, umbral_manos: Optional[int] = None, formato: str = "phh"
) -> Panel:
    if formato in ("texto", "ggpoker", "pokerstars"):
        manos, rechazos = cargar_ggpoker(ruta)
    elif formato == "phh":
        manos, rechazos = cargar_directorio(ruta)
    else:
        raise ValueError(f"formato desconocido: {formato}")
    return Panel(analizar_manos(manos, bb, umbral_manos), len(manos), rechazos)


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
