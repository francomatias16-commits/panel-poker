"""Informe por bloque de manos (Fase 5 del plan).

Un bloque son 1000 manos consecutivas de un jugador en un solo stake. En 1000 manos manda la varianza, así que
el informe separa lo que se puede medir bien (el proceso) de lo que no (el resultado):

1. Resultado: bb/100 con su intervalo de confianza, bb/100 ajustado por el EV de los all-ins y la probabilidad de
   que el winrate real sea positivo.
2. Proceso: porcentaje de decisiones que coinciden con la guía y bb perdidas estimadas por los desvíos.
3. Leaks: los 3 desvíos más costosos, con manos de ejemplo para repasar.
4. Evolución entre bloques.
5. Proyección: probabilidad de ganar los próximos 1000 manos.
6. Objetivo de proceso para el próximo bloque.

Límites que el informe declara:
- La probabilidad de winrate positivo usa una previa plana y aproximación normal: es la probabilidad que da el
  resultado observado, no una garantía.
- El ajuste por EV de all-in solo cubre manos de dos jugadores que llegan al showdown con las cartas de ambos a la
  vista. Las demás quedan con su resultado real y el informe dice cuántas fueron.
- Las bb perdidas por desvío son una estimación con la guía heurística del proyecto (ver guia.py): solo se cuantifican
  los desvíos donde la guía calcula el EV de igualar. Los demás se cuentan pero no se valoran.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

from . import guia
from .cartas import Carta
from .equity import _mazo_restante, equity as _equity_mc
from .evaluador import evaluar_mejor
from .motor import ResultadoMano

TAM_BLOQUE = 1000
REDUCCION_OBJETIVO = 1 / 3  # el objetivo por defecto es bajar un tercio el leak principal


def _bb(m: ResultadoMano) -> float:
    return float(m.ciega_grande or 2)  # mismo valor por defecto que guia.reproducir


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ---------------------------------------------------------------------------------------------------------------
# All-in EV
# ---------------------------------------------------------------------------------------------------------------

def equity_conocida(a: Sequence[Carta], b: Sequence[Carta], tablero: Sequence[Carta], iteraciones: int = 4000,
                    semilla: int = 1) -> float:
    """Equity de `a` contra `b` con el tablero dado. Exacta si faltan 2 cartas o menos; si no, Monte Carlo."""
    faltan = 5 - len(tablero)
    if faltan > 2:
        return _equity_mc(list(a), list(tablero), [list(b)], 0, iteraciones, semilla).equity
    base = _mazo_restante(list(a) + list(b) + list(tablero))
    total = 0.0
    n = 0
    for resto in combinations(base, faltan):
        tab = list(tablero) + list(resto)
        pa, pb = evaluar_mejor(list(a) + tab), evaluar_mejor(list(b) + tab)
        total += 1.0 if pa > pb else 0.5 if pa == pb else 0.0
        n += 1
    return total / n


def ev_allin(m: ResultadoMano, asiento: int, iteraciones: int = 4000, semilla: int = 1) -> Optional[Tuple[float, float]]:
    """(neto real, neto esperado) del jugador en big blinds, si la mano tuvo un all-in de dos jugadores con showdown
    y las cartas de ambos a la vista. Devuelve None cuando no se puede ajustar.

    El bote disputado entre los dos es 2c, con c = el menor de los dos stacks (el corto está all-in). El resto del
    resultado (dinero de quienes se retiraron, menos el rake) es D = neto_a + neto_b y no depende de la suerte:
        EV_a = equity_a * (2c + D) - c        (con equity_a incluyendo la mitad de los empates)
    """
    if asiento not in m.llegaron_showdown or len(m.llegaron_showdown) != 2:
        return None
    b = next(s for s in m.llegaron_showdown if s != asiento)
    ca, cb = m.cartas[asiento], m.cartas[b]
    if len(ca) != 2 or len(cb) != 2 or not all(ca) or not all(cb):
        return None
    ultima = max((i for i, e in enumerate(m.eventos) if e.tipo in ("f", "cc", "cbr")), default=None)
    if ultima is None:
        return None
    despues = sum(len(e.cartas) for e in m.eventos[ultima + 1:] if e.tipo == "reparto_tablero")
    if despues == 0 or len(m.tablero) != 5:
        return None  # no hubo cartas por salir: no hay suerte que ajustar
    tablero = list(m.tablero[: 5 - despues])
    bb = _bb(m)
    c = min(m.stacks_iniciales[asiento], m.stacks_iniciales[b])
    d = m.neto[asiento] + m.neto[b]
    eq = equity_conocida(ca, cb, tablero, iteraciones, semilla)
    ev = eq * (2 * c + d) - c
    return m.neto[asiento] / bb, ev / bb


# ---------------------------------------------------------------------------------------------------------------
# Proceso: desvíos respecto de la guía
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class Desvio:
    indice: int  # posición de la mano en la serie del jugador (1 = primera)
    referencia: Optional[str]
    id_global: Optional[int]  # posición de la mano en la lista cargada (para abrirla en el repaso)
    calle: str
    jugada: str
    sugerida: str
    gravedad: str
    detalle: str
    perdida_bb: Optional[float]  # None = no se puede valorar


def _perdida(jugada: str, sugerida: dict, bb: float) -> Optional[float]:
    """Pérdida estimada, en bb, de un desvío. Solo cuando la guía calcula el EV de igualar."""
    ev = sugerida.get("ev_igualar")
    if ev is None:
        return None
    fj, fs = guia._familia(jugada), guia._familia(sugerida["accion"])
    if fj == "F" and fs in ("C", "R"):
        return max(0.0, ev) / bb  # se retiró donde igualar tenía EV positivo
    if fj in ("C", "R") and fs == "F":
        return max(0.0, -ev) / bb  # pagó donde igualar tenía EV negativo
    return None  # apostar o igualar en vez del otro: depende del tamaño y no se valora


@dataclass
class Proceso:
    decisiones: int = 0
    coinciden: int = 0
    desvios: List[Desvio] = field(default_factory=list)
    manos_sin_cartas: int = 0


def analizar_proceso(m: ResultadoMano, asiento: int, indice: int, iteraciones: int = 150, semilla: int = 11,
                     id_global: Optional[int] = None) -> Proceso:
    """Decisiones de una mano comparadas con la guía."""
    p = Proceso()
    rep = guia.reproducir(m, asiento, iteraciones, semilla)
    if not rep["resumen"]["con_analisis"]:
        p.manos_sin_cartas = 1
        return p
    bb = _bb(m)
    for paso in rep["pasos"]:
        a = paso.get("analisis")
        if a is None:
            continue
        p.decisiones += 1
        cmp = paso["comparacion"]
        if cmp["veredicto"] == "coincide":
            p.coinciden += 1
            continue
        p.desvios.append(Desvio(
            indice=indice, referencia=m.referencia, id_global=id_global, calle=paso["calle"], jugada=paso["jugada"], sugerida=a["accion"],
            gravedad=cmp["gravedad"], detalle=cmp["detalle"], perdida_bb=_perdida(paso["jugada"], a, bb)))
    return p


# ---------------------------------------------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class Leak:
    descripcion: str
    casos: int
    perdida_bb: float
    perdida_bb100: float
    sin_valorar: int  # casos del leak que no se pudieron valorar
    ejemplos: List[Tuple[int, Optional[str], Optional[int]]]  # (número en la serie, referencia, id para el repaso)


@dataclass
class InformeBloque:
    numero: int
    manos: int
    completo: bool
    fecha_desde: Optional[str]
    fecha_hasta: Optional[str]
    # resultado
    bb100: float
    ic95: Optional[float]
    desvio_bb100: Optional[float]
    prob_winrate_positivo: Optional[float]
    bb100_ev: Optional[float]
    manos_ajustadas_ev: int
    suerte_allin_bb: float  # real menos esperado en las manos ajustadas
    # proceso
    decisiones: int
    coinciden: int
    manos_sin_cartas: int
    desvios_claros: int
    desvios_leves: int
    perdida_bb: float
    perdida_bb100: float
    desvios_sin_valorar: int
    por_calle: Dict[str, Tuple[int, float]]
    leaks: List[Leak]
    # proyección y objetivo
    prob_ganar_proximo: Optional[float]
    objetivo: str

    @property
    def pct_proceso(self) -> Optional[float]:
        return self.coinciden / self.decisiones if self.decisiones else None


def proyeccion_proximo_bloque(netos_bb: Sequence[float], manos_bloque: int = TAM_BLOQUE) -> Optional[float]:
    """Probabilidad de terminar con ganancia las próximas `manos_bloque` manos, dados los netos observados.

    Combina dos fuentes de incertidumbre: la del winrate real (error estándar de la media observada, previa plana) y
    la de la varianza propia de las manos que vienen. P = Φ( n·μ / sqrt( (n·se)² + n·σ² ) ), con μ y σ por mano.
    """
    n = len(netos_bb)
    if n < 30:
        return None
    mu = sum(netos_bb) / n
    var = sum((x - mu) ** 2 for x in netos_bb) / (n - 1)
    if var <= 0:
        return None
    se = math.sqrt(var / n)
    k = manos_bloque
    return _phi(k * mu / math.sqrt((k * se) ** 2 + k * var))


def _objetivo(leaks: Sequence[Leak], pct: Optional[float], reduccion: float) -> str:
    if not leaks:
        if pct is None:
            return "No hubo decisiones con cartas visibles para evaluar el proceso. Cargá historiales con tus cartas."
        return f"Sin leaks claros en este bloque. Objetivo: mantener el {100 * pct:.0f} % de decisiones que coinciden con la guía."
    L = leaks[0]
    meta = max(0, math.floor(L.casos * (1 - reduccion)))
    ganancia = L.perdida_bb100 * reduccion
    texto = (f"Bajar «{L.descripcion}» de {L.casos} casos a {meta} o menos ({100 * reduccion:.0f} % menos)")
    if L.perdida_bb100 > 0:
        texto += f"; si el costo por caso se mantiene, eso recupera unos {ganancia:.1f} bb/100."
    else:
        texto += "; la guía no pudo valorar el costo de este leak en bb."
    return texto


def informe_bloque(
    numero: int, manos: Sequence[Tuple[ResultadoMano, int]], previos_bb: Sequence[float] = (), tam: int = TAM_BLOQUE,
    iteraciones: int = 150, semilla: int = 11, inicio: int = 0, reduccion: float = REDUCCION_OBJETIVO,
    ids: Optional[Sequence[int]] = None,
) -> InformeBloque:
    """Informe de un bloque. `manos` son pares (mano, asiento del jugador); `previos_bb` son los netos de bloques
    anteriores (para la proyección, que usa todo el historial hasta este bloque); `inicio` es el número de la
    primera mano del bloque en la serie del jugador, menos uno."""
    netos = [m.neto[a] / _bb(m) for m, a in manos]
    n = len(netos)
    media = sum(netos) / n
    if n >= 2:
        var = sum((x - media) ** 2 for x in netos) / (n - 1)
        sd100 = 10 * math.sqrt(var)
        ic = 196 * math.sqrt(var / n)
        prob = _phi(media / math.sqrt(var / n)) if var > 0 else (1.0 if media > 0 else 0.0)
    else:
        sd100 = ic = prob = None

    # EV de all-ins
    ajustadas = 0
    delta = 0.0  # real - esperado, en bb, en las manos ajustadas
    for m, a in manos:
        r = ev_allin(m, a)
        if r is not None:
            ajustadas += 1
            delta += r[0] - r[1]
    bb100_ev = 100 * (sum(netos) - delta) / n if ajustadas else None

    # proceso
    proc = Proceso()
    for k, (m, a) in enumerate(manos):
        p = analizar_proceso(m, a, inicio + k + 1, iteraciones, semilla, ids[k] if ids is not None else None)
        proc.decisiones += p.decisiones
        proc.coinciden += p.coinciden
        proc.manos_sin_cartas += p.manos_sin_cartas
        proc.desvios.extend(p.desvios)

    por_calle: Dict[str, List[float]] = defaultdict(lambda: [0, 0.0])
    grupos: Dict[str, List[Desvio]] = defaultdict(list)
    for d in proc.desvios:
        por_calle[d.calle][0] += 1
        por_calle[d.calle][1] += d.perdida_bb or 0.0
        grupos[f"{d.calle}: {d.detalle}"].append(d)
    leaks = []
    for desc, ds in grupos.items():
        perdida = sum(d.perdida_bb or 0.0 for d in ds)
        mejores = sorted(ds, key=lambda d: -(d.perdida_bb or 0.0))[:3]
        leaks.append(Leak(
            descripcion=desc, casos=len(ds), perdida_bb=perdida, perdida_bb100=100 * perdida / n,
            sin_valorar=sum(d.perdida_bb is None for d in ds), ejemplos=[(d.indice, d.referencia, d.id_global) for d in mejores]))
    leaks.sort(key=lambda l: (-l.perdida_bb, -l.casos))
    leaks = leaks[:3]
    perdida_total = sum(d.perdida_bb or 0.0 for d in proc.desvios)

    fechas = [m.fecha for m, _ in manos if m.fecha is not None]
    pct = proc.coinciden / proc.decisiones if proc.decisiones else None
    return InformeBloque(
        numero=numero, manos=n, completo=n >= tam,
        fecha_desde=min(fechas).strftime("%Y-%m-%d") if fechas else None,
        fecha_hasta=max(fechas).strftime("%Y-%m-%d") if fechas else None,
        bb100=100 * media, ic95=ic, desvio_bb100=sd100, prob_winrate_positivo=prob,
        bb100_ev=bb100_ev, manos_ajustadas_ev=ajustadas, suerte_allin_bb=delta,
        decisiones=proc.decisiones, coinciden=proc.coinciden, manos_sin_cartas=proc.manos_sin_cartas,
        desvios_claros=sum(d.gravedad == "clara" for d in proc.desvios),
        desvios_leves=sum(d.gravedad == "leve" for d in proc.desvios),
        perdida_bb=perdida_total, perdida_bb100=100 * perdida_total / n,
        desvios_sin_valorar=sum(d.perdida_bb is None for d in proc.desvios),
        por_calle={k: (int(v[0]), v[1]) for k, v in por_calle.items()},
        leaks=leaks, prob_ganar_proximo=proyeccion_proximo_bloque(list(previos_bb) + netos, tam),
        objetivo=_objetivo(leaks, pct, reduccion),
    )


def detectar_jugador_principal(manos: Sequence[ResultadoMano]) -> Optional[Tuple[str, int]]:
    """(nombre, stake) del jugador del que más manos traen las cartas: en un historial propio, es quien lo exportó."""
    cuenta: Dict[str, int] = defaultdict(int)
    stakes: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for m in manos:
        for a, nombre in enumerate(m.nombres or ()):
            if len(m.cartas[a]) == 2:
                cuenta[nombre] += 1
                stakes[nombre][m.ciega_grande] += 1
    if not cuenta:
        return None
    nombre = max(cuenta, key=cuenta.get)
    return nombre, max(stakes[nombre], key=stakes[nombre].get)


def serie_del_jugador(manos: Sequence[ResultadoMano], jugador: str, bb: Optional[int] = None) -> List[Tuple[ResultadoMano, int]]:
    """Manos del jugador (mano, asiento) de un solo stake, en orden cronológico si todas traen fecha."""
    propias = [(m, m.nombres.index(jugador)) for m in manos if m.nombres and jugador in m.nombres]
    stakes = {m.ciega_grande for m, _ in propias}
    if bb is None:
        if len(stakes) > 1:
            raise ValueError(f"el jugador tiene manos en varios stakes {sorted(s for s in stakes if s)}: indicá `bb`")
    else:
        propias = [(m, a) for m, a in propias if m.ciega_grande == bb]
    if propias and all(m.fecha is not None for m, _ in propias):
        propias.sort(key=lambda x: x[0].fecha)  # estable: empates en orden de llegada
    return propias


def informes_por_bloque(
    manos: Sequence[ResultadoMano], jugador: str, bb: Optional[int] = None, tam: int = TAM_BLOQUE,
    iteraciones: int = 150, semilla: int = 11, progreso=None,
) -> List[InformeBloque]:
    serie = serie_del_jugador(manos, jugador, bb)
    posicion = {id(m): i for i, m in enumerate(manos)}
    out: List[InformeBloque] = []
    previos: List[float] = []
    for k in range(0, len(serie), tam):
        bloque = serie[k: k + tam]
        inf = informe_bloque(k // tam + 1, bloque, previos, tam, iteraciones, semilla, inicio=k,
                             ids=[posicion[id(m)] for m, _ in bloque])
        out.append(inf)
        previos += [m.neto[a] / _bb(m) for m, a in bloque]
        if progreso:
            progreso(len(out), (len(serie) + tam - 1) // tam)
    return out


def evolucion(informes: Sequence[InformeBloque]) -> List[dict]:
    """Una fila por bloque con las cifras principales y su cambio respecto del bloque anterior."""
    filas = []
    previo: Optional[InformeBloque] = None
    for i in informes:
        fila = {"bloque": i.numero, "manos": i.manos, "completo": i.completo, "bb100": i.bb100, "ic95": i.ic95,
                "bb100_ev": i.bb100_ev, "pct_proceso": i.pct_proceso, "perdida_bb100": i.perdida_bb100,
                "prob_winrate_positivo": i.prob_winrate_positivo}
        if previo is not None:
            fila["delta_pct_proceso"] = (None if i.pct_proceso is None or previo.pct_proceso is None
                                         else i.pct_proceso - previo.pct_proceso)
            fila["delta_perdida_bb100"] = i.perdida_bb100 - previo.perdida_bb100
        filas.append(fila)
        previo = i
    return filas


def _pct(x: Optional[float], d: int = 0) -> str:
    return "–" if x is None else f"{100 * x:.{d}f} %"


def formatear(informes: Sequence[InformeBloque], jugador: str = "") -> str:
    """Informe en texto plano (Markdown simple)."""
    L: List[str] = [f"# Informe por bloques{' de ' + jugador if jugador else ''}", ""]
    L.append("En 1000 manos manda la varianza: el resultado es una pista, el proceso es lo que se puede mejorar.")
    for i in informes:
        L += ["", f"## Bloque {i.numero} ({i.manos} manos{'' if i.completo else ', incompleto'})"]
        if i.fecha_desde:
            L.append(f"Del {i.fecha_desde} al {i.fecha_hasta}.")
        L += ["", "### 1. Resultado"]
        ic = "–" if i.ic95 is None else f"±{i.ic95:.0f}"
        L.append(f"- bb/100: {i.bb100:+.1f} ({ic} con 95 % de confianza).")
        if i.bb100_ev is not None:
            L.append(f"- bb/100 ajustado por EV de los all-ins: {i.bb100_ev:+.1f} "
                     f"({i.manos_ajustadas_ev} manos ajustadas; la suerte en all-ins fue {i.suerte_allin_bb:+.1f} bb).")
        else:
            L.append("- bb/100 ajustado por EV: sin all-ins ajustables en este bloque.")
        if i.prob_winrate_positivo is not None:
            L.append(f"- Probabilidad de que el winrate real sea positivo: {_pct(i.prob_winrate_positivo)} "
                     "(aproximación normal con previa plana).")
        L += ["", "### 2. Proceso"]
        if i.decisiones:
            L.append(f"- Decisiones que coinciden con la guía: {_pct(i.pct_proceso)} ({i.coinciden} de {i.decisiones}).")
            L.append(f"- Desvíos: {i.desvios_claros} claros y {i.desvios_leves} leves.")
            L.append(f"- bb perdidas estimadas por desvíos: {i.perdida_bb:.1f} ({i.perdida_bb100:.1f} bb/100); "
                     f"{i.desvios_sin_valorar} desvíos no se pudieron valorar.")
            for calle, (n, p) in sorted(i.por_calle.items()):
                L.append(f"  - {calle}: {n} desvíos, {p:.1f} bb.")
        else:
            L.append("- No hubo decisiones con cartas visibles: la guía no pudo evaluar el proceso.")
        if i.manos_sin_cartas:
            L.append(f"- {i.manos_sin_cartas} manos sin tus cartas en el historial.")
        L += ["", "### 3. Leaks (los de mayor costo)"]
        if i.leaks:
            for k, lk in enumerate(i.leaks, 1):
                ej = ", ".join(f"mano {n}" + (f" (#{r})" if r else "") for n, r, _ in lk.ejemplos)
                L.append(f"{k}. {lk.descripcion} — {lk.casos} casos, {lk.perdida_bb:.1f} bb ({lk.perdida_bb100:.1f} bb/100)"
                         + (f"; {lk.sin_valorar} sin valorar" if lk.sin_valorar else "") + f". Para repasar: {ej}.")
        else:
            L.append("Sin desvíos registrados.")
        L += ["", "### 5. Proyección"]
        if i.prob_ganar_proximo is not None:
            L.append(f"- Probabilidad de ganar las próximas 1000 manos con lo observado hasta acá: {_pct(i.prob_ganar_proximo)}.")
        else:
            L.append("- Muestra insuficiente para proyectar.")
        L += ["", "### 6. Objetivo de proceso para el próximo bloque", i.objetivo]
    if len(informes) > 1:
        L += ["", "## 4. Evolución entre bloques", "", "| Bloque | Manos | bb/100 | bb/100 EV | Proceso | Pérdida bb/100 | Cambio proceso | Cambio pérdida |",
              "|---|---|---|---|---|---|---|---|"]
        for f in evolucion(informes):
            ev = "–" if f["bb100_ev"] is None else f"{f['bb100_ev']:+.1f}"
            dp = "" if "delta_pct_proceso" not in f or f["delta_pct_proceso"] is None else f"{100 * f['delta_pct_proceso']:+.1f} pts"
            dl = "" if "delta_perdida_bb100" not in f else f"{f['delta_perdida_bb100']:+.1f}"
            L.append(f"| {f['bloque']} | {f['manos']} | {f['bb100']:+.1f} | {ev} | {_pct(f['pct_proceso'])} | {f['perdida_bb100']:.1f} | {dp} | {dl} |")
    return "\n".join(L) + "\n"
