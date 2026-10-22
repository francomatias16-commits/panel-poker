"""Riesgo y bankroll con la incertidumbre del winrate propagada (Fase 4 del plan).

`riesgo.py` toma el winrate medido como si fuera el verdadero. Con pocas manos eso engaña: en 20.000 manos el winrate
tiene un intervalo de cientos de bb/100. Este módulo hace lo mismo pero sorteando, en cada escenario, un winrate y
un desvío plausibles dados los datos:

    winrate real  ~ Normal(media observada, error estándar)           (previa plana, aproximación normal)
    varianza real ~ varianza observada · (n - 1) / chi-cuadrado(n - 1)  (posterior habitual de la varianza)

Cada resultado es entonces una cifra predictiva (promediada sobre lo que no se sabe), acompañada del rango que
resulta de tomar un winrate bajo o alto del intervalo de confianza.

Modelo: las manos son independientes y el resultado acumulado es un movimiento browniano con deriva. Es la misma
aproximación de `riesgo.py`; no contempla rachas, cambios de nivel de juego ni de rake. Para simular se agrupan las
manos en bloques y dentro de cada bloque se corrige con el puente browniano (mínimo y máximo exactos para el
modelo), de modo que la ruina no depende del tamaño del bloque. El drawdown simulado es una cota inferior muy
cercana: ignora las caídas que empiezan y terminan dentro de un mismo bloque.

Decisiones de este módulo (constantes abajo): riesgo de ruina objetivo de 5 %, límite para bajar de stake de 15 %,
muestra mínima de 30 manos. Son convenciones habituales de gestión de bankroll, no resultados medidos.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

RUINA_OBJETIVO = 0.05  # riesgo de ruina con el que se considera cómodo un bankroll
RUINA_BAJAR = 0.15  # por encima de este riesgo se recomienda bajar de stake
MANOS_MINIMAS = 30
BUYIN_BB = 100  # una entrada completa son 100 big blinds
BLOQUE = 100  # manos por paso de simulación
Z95 = 1.959964


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass
class Muestra:
    """Estadísticos de una serie de resultados por mano (en bb)."""

    n: int
    media: float  # bb por mano
    desvio: float  # bb por mano

    @property
    def error(self) -> float:
        return self.desvio / math.sqrt(self.n)

    @property
    def winrate_bb100(self) -> float:
        return 100 * self.media

    @property
    def desvio_bb100(self) -> float:
        return 10 * self.desvio

    @property
    def ic95_bb100(self) -> Tuple[float, float]:
        m = 100 * Z95 * self.error
        return self.winrate_bb100 - m, self.winrate_bb100 + m

    @property
    def prob_winrate_positivo(self) -> float:
        return _phi(self.media / self.error) if self.error > 0 else (1.0 if self.media > 0 else 0.0)


def muestra(netos: Sequence[float]) -> Muestra:
    if len(netos) < MANOS_MINIMAS:
        raise ValueError(f"se necesitan al menos {MANOS_MINIMAS} manos para estimar el riesgo")
    sd = statistics.stdev(netos)
    if sd <= 0:
        raise ValueError("la serie no varía: no se puede estimar el riesgo")
    return Muestra(len(netos), statistics.fmean(netos), sd)


def sortear_parametros(m: Muestra, k: int, rng: random.Random) -> List[Tuple[float, float]]:
    """k pares (media por mano, desvío por mano) plausibles dados los datos."""
    out = []
    for _ in range(k):
        chi2 = 2 * rng.gammavariate((m.n - 1) / 2, 1.0)
        sd = m.desvio * math.sqrt((m.n - 1) / chi2)
        out.append((rng.gauss(m.media, sd / math.sqrt(m.n)), sd))
    return out


# ---------------------------------------------------------------------------------------------------------------
# Ruina
# ---------------------------------------------------------------------------------------------------------------

def ruina_dado(media: float, desvio: float, bankroll_bb: float) -> float:
    """Ruina en horizonte infinito con parámetros conocidos: exp(-2·mu·B / sigma²); 1 si el winrate no es positivo."""
    if bankroll_bb <= 0 or media <= 0:
        return 1.0
    return math.exp(-2 * media * bankroll_bb / desvio ** 2)


@dataclass
class Ruina:
    bankroll_bb: float
    predictiva: float  # promedio sobre la incertidumbre del winrate y del desvío
    con_winrate_bajo: float  # fijando el winrate en el extremo inferior del IC95 %
    con_winrate_alto: float  # y en el superior
    con_estimado: float  # tomando el winrate observado como verdadero (lo que hace riesgo.py)

    @property
    def buyins(self) -> float:
        return self.bankroll_bb / BUYIN_BB


def ruina(netos: Sequence[float], bankroll_bb: float, sorteos: int = 4000, semilla: int = 1) -> Ruina:
    """Riesgo de ruina en horizonte infinito (cota superior del riesgo en un horizonte finito)."""
    m = muestra(netos)
    rng = random.Random(semilla)
    pred = statistics.fmean(ruina_dado(mu, sd, bankroll_bb) for mu, sd in sortear_parametros(m, sorteos, rng))
    lo, hi = m.ic95_bb100
    return Ruina(bankroll_bb, pred, ruina_dado(lo / 100, m.desvio, bankroll_bb),
                 ruina_dado(hi / 100, m.desvio, bankroll_bb), ruina_dado(m.media, m.desvio, bankroll_bb))


def bankroll_requerido(netos: Sequence[float], objetivo: float = RUINA_OBJETIVO, sorteos: int = 4000,
                       semilla: int = 1) -> Optional[float]:
    """Bankroll (bb) con el que la ruina predictiva baja del objetivo; None si ninguno alcanza.

    La ruina predictiva nunca baja de la probabilidad de que el winrate real sea negativo. Si esa probabilidad ya
    supera el objetivo, la muestra no permite asegurar un winrate positivo y no hay bankroll que alcance."""
    if not 0 < objetivo < 1:
        raise ValueError("el objetivo debe estar en (0, 1)")
    m = muestra(netos)
    rng = random.Random(semilla)
    pars = sortear_parametros(m, sorteos, rng)

    def pred(b: float) -> float:
        return statistics.fmean(ruina_dado(mu, sd, b) for mu, sd in pars)

    if pred(1e12) > objetivo:
        return None
    lo, hi = 0.0, 1.0
    while pred(hi) > objetivo:
        hi *= 2
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pred(mid) > objetivo else (lo, mid)
    return hi


# ---------------------------------------------------------------------------------------------------------------
# Simulación con puente browniano: drawdown y ruina en horizonte finito
# ---------------------------------------------------------------------------------------------------------------

def _min_max_puente(x0: float, x1: float, var: float, rng: random.Random) -> Tuple[float, float]:
    """Mínimo y máximo de un puente browniano de x0 a x1 con varianza total `var`."""
    base = (x1 - x0) ** 2
    u1, u2 = rng.random() or 1e-300, rng.random() or 1e-300
    return (0.5 * ((x0 + x1) - math.sqrt(base - 2 * var * math.log(u1))),
            0.5 * ((x0 + x1) + math.sqrt(base - 2 * var * math.log(u2))))


@dataclass
class Simulacion:
    horizonte: int
    trayectorias: int
    drawdown_percentiles: Dict[int, float]  # bb, percentiles 50, 90, 95 y 99 del mayor drawdown
    resultado_percentiles: Dict[int, float]  # bb acumulados al final del horizonte
    prob_ruina: Optional[float]  # None si no se indicó bankroll
    prob_perder_al_final: float
    drawdown_medio: float = 0.0
    con_incertidumbre: bool = True

    def drawdown_buyins(self) -> Dict[int, float]:
        return {p: v / BUYIN_BB for p, v in self.drawdown_percentiles.items()}


def _percentil(orden: Sequence[float], p: int) -> float:
    return orden[min(len(orden) - 1, int(p / 100 * len(orden)))]


def simular(netos: Sequence[float], horizonte: int, trayectorias: int = 1000, bankroll_bb: Optional[float] = None,
            incertidumbre: bool = True, semilla: int = 1, bloque: int = BLOQUE) -> Simulacion:
    """Simula `trayectorias` caminos de `horizonte` manos. Con `incertidumbre`, cada camino tiene su propio winrate y
    desvío sorteados de lo que dicen los datos; sin ella, todos usan los valores observados."""
    if horizonte < 1 or trayectorias < 1:
        raise ValueError("horizonte y trayectorias deben ser positivos")
    m = muestra(netos)
    rng = random.Random(semilla)
    pars = sortear_parametros(m, trayectorias, rng) if incertidumbre else [(m.media, m.desvio)] * trayectorias
    pasos, resto = divmod(horizonte, bloque)
    tamanos = [bloque] * pasos + ([resto] if resto else [])
    drawdowns: List[float] = []
    finales: List[float] = []
    ruinas = 0
    for mu, sd in pars:
        x = pico = peor = 0.0
        arruinado = False
        for b in tamanos:
            x1 = x + rng.gauss(mu * b, sd * math.sqrt(b))
            mn, mx = _min_max_puente(x, x1, sd * sd * b, rng)
            peor = max(peor, pico - mn)
            pico = max(pico, mx, x1)
            if bankroll_bb is not None and not arruinado and bankroll_bb + mn <= 0:
                arruinado = True
            x = x1
        drawdowns.append(peor)
        finales.append(x)
        ruinas += arruinado
    dd, fin = sorted(drawdowns), sorted(finales)
    return Simulacion(
        horizonte, trayectorias, {p: _percentil(dd, p) for p in (50, 90, 95, 99)},
        {p: _percentil(fin, p) for p in (5, 25, 50, 75, 95)},
        ruinas / trayectorias if bankroll_bb is not None else None,
        sum(f < 0 for f in finales) / trayectorias, statistics.fmean(drawdowns), incertidumbre)


# ---------------------------------------------------------------------------------------------------------------
# Kelly y cambio de stake
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class KellyInforme:
    completo_bb: Optional[float]  # bankroll de Kelly completo con el winrate observado
    fraccion_bb: Optional[float]  # con la fracción pedida
    conservador_bb: Optional[float]  # Kelly completo con el límite inferior del IC95 % del winrate; None si es <= 0
    fraccion: float


def kelly(netos: Sequence[float], fraccion: float = 0.5) -> KellyInforme:
    """Bankroll de Kelly: B = sigma² / mu (en bb). Kelly completo es agresivo; se suele usar la mitad o menos."""
    if not 0 < fraccion <= 1:
        raise ValueError("la fracción de Kelly debe estar en (0, 1]")
    m = muestra(netos)
    var100 = m.desvio_bb100 ** 2
    wr = m.winrate_bb100
    lo = m.ic95_bb100[0]
    return KellyInforme(var100 / wr if wr > 0 else None, var100 / wr / fraccion if wr > 0 else None,
                        var100 / lo if lo > 0 else None, fraccion)


@dataclass
class Decision:
    accion: str  # "subir", "mantener" o "bajar"
    ruina_actual: float
    bankroll_requerido_bb: Optional[float]
    bankroll_para_subir_bb: Optional[float]
    motivos: List[str] = field(default_factory=list)


def decidir_stake(netos: Sequence[float], bankroll_bb: float, factor_stake_superior: float = 2.0,
                  objetivo: float = RUINA_OBJETIVO, limite_bajar: float = RUINA_BAJAR, semilla: int = 1) -> Decision:
    """Regla de cambio de stake con el riesgo de ruina predictivo.

    - Bajar: la ruina predictiva con el bankroll actual supera `limite_bajar`.
    - Subir: el bankroll alcanza, expresado en bb del stake actual, para el requerido por `objetivo` multiplicado
      por `factor_stake_superior` (cuánto vale el bb del stake superior respecto del actual; 2 de NL50 a NL100).
      Supone el mismo winrate y desvío en bb/100 en el stake superior, lo que casi nunca se cumple del todo.
    - Mantener: en cualquier otro caso."""
    r = ruina(netos, bankroll_bb, semilla=semilla)
    req = bankroll_requerido(netos, objetivo, semilla=semilla)
    d = Decision("mantener", r.predictiva, req, None if req is None else req * factor_stake_superior)
    if r.predictiva > limite_bajar:
        d.accion = "bajar"
        d.motivos.append(f"La ruina predictiva con este bankroll es {100 * r.predictiva:.0f} %, por encima del límite de {100 * limite_bajar:.0f} %.")
    elif req is None:
        d.motivos.append("La muestra no permite asegurar un winrate positivo: ningún bankroll lleva la ruina al objetivo todavía. Se mantiene el stake y se junta muestra.")
    elif bankroll_bb >= req * factor_stake_superior:
        d.accion = "subir"
        d.motivos.append(f"El bankroll cubre {req * factor_stake_superior / BUYIN_BB:.0f} entradas, lo requerido para el stake superior con ruina de {100 * objetivo:.0f} % o menos.")
    else:
        d.motivos.append(f"Para subir hacen falta {req * factor_stake_superior / BUYIN_BB:.0f} entradas del stake actual; hay {bankroll_bb / BUYIN_BB:.0f}.")
        if r.predictiva > objetivo:
            d.motivos.append(f"La ruina actual ({100 * r.predictiva:.0f} %) todavía supera el objetivo de {100 * objetivo:.0f} %.")
    return d


# ---------------------------------------------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------------------------------------------

def formatear(netos: Sequence[float], bankroll_bb: float, horizonte: int = 100_000, trayectorias: int = 1000,
              fraccion_kelly: float = 0.5, factor_stake_superior: float = 2.0,
              sim: Optional[Simulacion] = None, sim_fija: Optional[Simulacion] = None) -> str:
    """Informe de riesgo en texto plano para un jugador y un stake. `sim` y `sim_fija` (con y sin incertidumbre) se
    pueden pasar ya calculadas para no repetir la simulación."""
    m = muestra(netos)
    lo, hi = m.ic95_bb100
    L = ["# Riesgo y bankroll", ""]
    L.append(f"Muestra: {m.n} manos. Winrate observado {m.winrate_bb100:+.1f} bb/100 (IC95 % de {lo:+.1f} a {hi:+.1f}), "
             f"desvío {m.desvio_bb100:.0f} bb/100. Probabilidad de que el winrate real sea positivo: {100 * m.prob_winrate_positivo:.0f} %.")
    L.append("Todas las cifras propagan esa incertidumbre; entre paréntesis va lo que daría tomar el winrate observado como verdadero.")
    r = ruina(netos, bankroll_bb)
    L += ["", "## Riesgo de ruina", "",
          f"Con {r.buyins:.0f} entradas ({bankroll_bb:.0f} bb), horizonte infinito: {100 * r.predictiva:.1f} % "
          f"({100 * r.con_estimado:.1f} % con el winrate observado). Con el winrate en el extremo bajo del IC95 %: "
          f"{100 * r.con_winrate_bajo:.0f} %; en el alto: {100 * r.con_winrate_alto:.1f} %."]
    req = bankroll_requerido(netos)
    L.append(f"Bankroll para ruina de {100 * RUINA_OBJETIVO:.0f} % o menos: " + (
        f"{req / BUYIN_BB:.0f} entradas ({req:.0f} bb)." if req is not None else
        "ninguno alcanza con esta muestra (no se puede asegurar que el winrate sea positivo)."))
    s = sim or simular(netos, horizonte, trayectorias, bankroll_bb)
    sf = sim_fija or simular(netos, horizonte, trayectorias, bankroll_bb, incertidumbre=False)
    L += ["", f"## Simulación a {horizonte:,} manos".replace(",", "."), "",
          f"- Ruina dentro del horizonte: {100 * s.prob_ruina:.1f} % ({100 * sf.prob_ruina:.1f} %).",
          f"- Probabilidad de terminar en pérdida: {100 * s.prob_perder_al_final:.0f} % ({100 * sf.prob_perder_al_final:.0f} %).",
          "- Mayor drawdown, en entradas (50 / 90 / 95 / 99 por ciento de los casos): "
          + " / ".join(f"{s.drawdown_percentiles[p] / BUYIN_BB:.0f}" for p in (50, 90, 95, 99))
          + " (" + " / ".join(f"{sf.drawdown_percentiles[p] / BUYIN_BB:.0f}" for p in (50, 90, 95, 99)) + ")."]
    k = kelly(netos, fraccion_kelly)
    L += ["", "## Kelly", ""]
    if k.completo_bb is None:
        L.append("El winrate observado no es positivo: no hay bankroll de Kelly.")
    else:
        L.append(f"Kelly completo: {k.completo_bb / BUYIN_BB:.0f} entradas; fracción {fraccion_kelly:g}: {k.fraccion_bb / BUYIN_BB:.0f} entradas. "
                 + (f"Con el límite inferior del IC95 %: {k.conservador_bb / BUYIN_BB:.0f} entradas."
                    if k.conservador_bb else "Con el límite inferior del IC95 % el winrate no es positivo: no hay Kelly conservador."))
    d = decidir_stake(netos, bankroll_bb, factor_stake_superior)
    L += ["", "## Cambio de stake", "", f"Recomendación: {d.accion}."] + [f"- {x}" for x in d.motivos]
    L.append("- Supone que el winrate en bb/100 se mantiene en el stake superior y que las manos son independientes.")
    return "\n".join(L) + "\n"
