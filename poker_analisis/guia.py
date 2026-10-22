"""Guía de estudio: reproduce una mano acción por acción y compara cada decisión del jugador
con una línea sugerida.

Es una herramienta de REPASO (manos ya jugadas) y de práctica contra bots. No está pensada para
usarse en vivo en un sitio con dinero: casi todas las salas prohíben la asistencia en tiempo real.

Qué sabe la guía en cada decisión (solo lo que el jugador veía):
- sus dos cartas, el tablero, el bote, lo que debe igualar y las acciones previas de los rivales;
- NO usa las cartas de los rivales, aunque el historial las traiga (se muestran en el repaso
  únicamente cuando se revelan en el showdown).

Método (simple y explicable, no un solver):
1. Estima un rango por rival a partir de sus acciones preflop (abrió, igualó, subió, 3-bet...)
   y lo estrecha según su actitud postflop (apostó, subió, igualó) y el tablero.
2. Calcula la equity de la mano contra esos rangos con Monte Carlo (multiway).
3. Compara con las pot odds y con umbrales de valor según cuántos rivales quedan.
   Preflop, para abrir usa el porcentaje de manos típico de cada posición.
"""

from __future__ import annotations

import math
import os
import random
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from .bots import cargar_tabla_preflop, clave_mano
from .cartas import Carta, PALOS, RANGOS, VALOR_RANGO
from .equity import ResultadoEquity, _mazo_restante, outs as _outs
from .equity_rangos import combinaciones_de_clave
from .evaluador import CATEGORIAS, evaluar_mejor
from .motor import ResultadoMano
from .rangos import CLAVES, COMBOS, TOTAL_COMBOS
from .texturas import tamano_sugerido

Rango = Dict[str, float]

_RUTA_TABLA = os.path.join(os.path.dirname(__file__), "..", "resultados", "preflop_equity.csv")

# Nombres de los asientos entre el BB y el botón, según cuántos hay (6-max: UTG, HJ, CO).
_POSICIONES = {
    1: ["CO"], 2: ["HJ", "CO"], 3: ["UTG", "HJ", "CO"], 4: ["UTG", "UTG+1", "HJ", "CO"],
    5: ["UTG", "UTG+1", "MP", "HJ", "CO"], 6: ["UTG", "UTG+1", "UTG+2", "MP", "HJ", "CO"],
}

# Porcentaje de manos (por combinaciones) que se juega según el rol preflop.
PCT_ABRIR = {"UTG": 16, "UTG+1": 18, "UTG+2": 20, "MP": 22, "HJ": 24, "CO": 30, "BTN": 42, "SB": 38, "BB": 30}
PCT_NIVEL = {"limp": 50, "call": 22, "defiende": 35, "3bet": 8, "4bet": 3.5, "bbcheck": 80, "sin_info": 60}
# Cuántas manos suben/pagan según cuántos rivales quedan: umbral de equity para apostar por valor.
UMBRAL_VALOR = {1: 0.64, 2: 0.52, 3: 0.44, 4: 0.38, 5: 0.34}
MARGEN_IGUALAR = 0.03  # equity por encima de las pot odds para igualar con comodidad
MARGEN_PREFLOP = 0.04  # preflop se exige algo más (se juega fuera de posición con frecuencia)

# Realización de equity: parte de la equity bruta que se convierte en fichas cuando quedan calles por jugar.
# Convención de estudio (no medida): se pierde un poco por cada calle restante, más fuera de posición y con más rivales.
PERDIDA_POR_CALLE = {"posicion": 0.01, "neutral": 0.03, "blinds": 0.05}
PERDIDA_EXTRA_POR_RIVAL = 0.01
_POS_EN_POSICION = {"BTN", "CO", "BTN/SB"}
_POS_BLINDS = {"SB", "BB"}
_CALLES_RESTANTES = {"preflop": 3, "flop": 2, "turn": 1, "river": 0}


def realizacion(calle: str, pos: str, rivales: int) -> float:
    """Factor (<= 1) que multiplica la equity bruta para estimar el EV de igualar con calles por delante."""
    grupo = "posicion" if pos in _POS_EN_POSICION else "blinds" if pos in _POS_BLINDS else "neutral"
    restantes = _CALLES_RESTANTES.get(calle, 0)
    perdida = restantes * (PERDIDA_POR_CALLE[grupo] + PERDIDA_EXTRA_POR_RIVAL * max(0, rivales - 1))
    return max(0.5, 1.0 - perdida)


_NIVEL_ACTITUD = {"pasivo": 0, "igual": 1, "apuesta": 2, "sube": 3}
_ACTITUDES = list(_NIVEL_ACTITUD)


def posiciones_mesa(n: int) -> List[str]:
    """Nombres de las posiciones de una mesa de `n` jugadores, en orden de acción preflop."""
    if n == 2:
        return ["BTN/SB", "BB"]
    return ["SB", "BB"] + _POSICIONES.get(n - 3, [f"P{k}" for k in range(1, n - 2)]) + ["BTN"]


def posicion(m: ResultadoMano, asiento: int) -> str:
    """Posición del asiento en la mano: SB, BB, UTG..., CO, BTN (con 2 jugadores: BTN/SB y BB)."""
    n = len(m.stacks_iniciales)
    if n == 2:
        return "BTN/SB" if asiento == m.boton else "BB"
    d = (asiento - m.boton) % n
    if d == 0:
        return "BTN"
    if d == 1:
        return "SB"
    if d == 2:
        return "BB"
    nombres = _POSICIONES.get(n - 3)
    return nombres[d - 3] if nombres else f"P{d - 2}"


# ---------------------------------------------------------------------------
# Rangos
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _ranking() -> Tuple[str, ...]:
    """Las 169 manos canónicas de mejor a peor según su equity preflop."""
    tabla = cargar_tabla_preflop(_RUTA_TABLA)
    return tuple(sorted(CLAVES, key=lambda c: -tabla[c]))


@lru_cache(maxsize=None)
def rango_top(pct: float) -> Tuple[Tuple[str, float], ...]:
    """Mejor `pct`% de las manos (por combinaciones). La mano del borde entra con peso parcial."""
    objetivo = TOTAL_COMBOS * min(max(pct, 0.1), 100.0) / 100.0
    acum = 0.0
    salida: List[Tuple[str, float]] = []
    for c in _ranking():
        if acum >= objetivo:
            break
        peso = min(1.0, (objetivo - acum) / COMBOS[c])
        salida.append((c, peso))
        acum += COMBOS[c]
    return tuple(salida)


def percentil(clave: str) -> float:
    """Posición de la mano en el ranking, en % de combinaciones (0 = la mejor, 100 = la peor)."""
    acum = 0.0
    for c in _ranking():
        if c == clave:
            return 100.0 * (acum + COMBOS[c] / 2) / TOTAL_COMBOS
        acum += COMBOS[c]
    raise ValueError(clave)


def _proyecto(cartas: Sequence[Carta], tablero: Sequence[Carta]) -> bool:
    """¿Tiene proyecto de color o de escalera que use alguna carta propia?"""
    todas = list(cartas) + list(tablero)
    for p in PALOS:
        if sum(1 for c in todas if c.palo == p) == 4 and any(c.palo == p for c in cartas):
            return True
    valores = {c.valor for c in todas}
    if 14 in valores:
        valores.add(1)
    propios = {c.valor for c in cartas} | ({1} if any(c.valor == 14 for c in cartas) else set())
    for base in range(1, 11):
        ventana = set(range(base, base + 5))
        presentes = ventana & valores
        if len(presentes) == 4 and presentes & propios:
            return True
    return False


def _fuerza(cartas: Sequence[Carta], tablero: Sequence[Carta]) -> Tuple[int, bool, bool]:
    """(categoría, par fuerte con carta propia, proyecto) de la mano en el tablero."""
    cat = evaluar_mejor(list(cartas) + list(tablero))[0]
    valores_tab = sorted((c.valor for c in tablero), reverse=True)
    par_fuerte = False
    if cat == 1:
        medio = valores_tab[len(valores_tab) // 2 - 1] if len(valores_tab) > 1 else valores_tab[0]
        par_fuerte = any(c.valor in valores_tab and c.valor >= medio for c in cartas) or cartas[0].valor == cartas[1].valor
    return cat, par_fuerte, _proyecto(cartas, tablero)


def _factor_postflop(actitud: str, cat: int, par_fuerte: bool, proyecto: bool) -> float:
    if actitud == "pasivo":
        return 1.0
    hecha = cat >= 2
    par = cat == 1
    if actitud == "igual":
        return 1.0 if (hecha or par or proyecto) else 0.25
    if actitud == "apuesta":
        if hecha:
            return 1.0
        if par:
            return 1.0 if par_fuerte else 0.5
        return 0.7 if proyecto else 0.12
    # sube
    if hecha:
        return 1.0
    if par:
        return 0.35 if par_fuerte else 0.1
    return 0.4 if proyecto else 0.05


def restringir_por_tablero(rango: Rango, tablero: Sequence[Carta], actitud: str, bloqueadas=()) -> Rango:
    """Pondera el rango según lo que hizo el rival postflop. Devuelve {} si no queda nada."""
    if not tablero or actitud == "pasivo":
        return dict(rango)
    bloq = set(bloqueadas) | set(tablero)
    salida: Rango = {}
    for clave, peso in rango.items():
        libres = [c for c in combinaciones_de_clave(clave) if c[0] not in bloq and c[1] not in bloq]
        if not libres:
            continue
        cat, fuerte, proy = _fuerza(libres[0], tablero)
        w = peso * _factor_postflop(actitud, cat, fuerte, proy)
        if w > 0:
            salida[clave] = w
    return salida


# ---------------------------------------------------------------------------
# Equity multiway contra rangos
# ---------------------------------------------------------------------------

def equity_multiway(
    mano: Sequence[Carta], rangos: Sequence[Rango], tablero: Sequence[Carta] = (),
    iteraciones: int = 600, semilla: Optional[int] = 1,
) -> ResultadoEquity:
    """Equity de `mano` contra varios rivales, cada uno con su rango. Los empates se reparten."""
    mano, tablero = list(mano), list(tablero)
    if len(mano) != 2 or len(tablero) not in (0, 3, 4, 5):
        raise ValueError("mano de 2 cartas y tablero de 0, 3, 4 o 5")
    if len(set(mano + tablero)) != len(mano + tablero):
        raise ValueError("hay cartas repetidas")
    bloq = set(mano + tablero)
    prep = []
    for r in rangos:
        claves, pesos, libres = [], [], []
        for clave, peso in r.items():
            if peso <= 0:
                continue
            combos = [c for c in combinaciones_de_clave(clave) if c[0] not in bloq and c[1] not in bloq]
            if combos:
                claves.append(clave)
                pesos.append(peso * len(combos) / COMBOS[clave])
                libres.append(combos)
        if not claves:
            raise ValueError("un rango no tiene combinaciones compatibles")
        prep.append((pesos, libres))

    faltan = 5 - len(tablero)
    base = _mazo_restante(mano + tablero)
    rng = random.Random(semilla)
    reparto: List[float] = []
    for _ in range(iteraciones):
        usadas = set()
        rivales = []
        ok = True
        for pesos, libres in prep:
            for _intento in range(25):
                combo = rng.choice(libres[rng.choices(range(len(pesos)), weights=pesos)[0]])
                if combo[0] not in usadas and combo[1] not in usadas:
                    usadas.update(combo)
                    rivales.append(combo)
                    break
            else:
                ok = False
                break
        if not ok:
            continue
        mazo = [c for c in base if c not in usadas]
        tab = tablero + rng.sample(mazo, faltan)
        propio = evaluar_mejor(mano + tab)
        mejor_rival = max(evaluar_mejor(list(r) + tab) for r in rivales)
        if propio > mejor_rival:
            reparto.append(1.0)
        elif propio == mejor_rival:
            reparto.append(1.0 / (1 + sum(1 for r in rivales if evaluar_mejor(list(r) + tab) == propio)))
        else:
            reparto.append(0.0)
    n = len(reparto)
    if n < 2:
        raise ValueError("no se pudo muestrear: rangos incompatibles entre sí")
    media = sum(reparto) / n
    var = sum((x - media) ** 2 for x in reparto) / (n - 1)
    return ResultadoEquity(media, math.sqrt(var / n), n)


# ---------------------------------------------------------------------------
# Decisión sugerida
# ---------------------------------------------------------------------------

def _familia(accion: str) -> str:
    return {"fold": "F", "check": "C", "call": "C", "bet": "R", "raise": "R"}[accion]


def _redondear(x: float, bb: float) -> float:
    paso = max(bb / 2, 1e-9)
    return round(x / paso) * paso


def decidir(
    *, calle: str, cartas: Sequence[Carta], tablero: Sequence[Carta], bote: float, a_pagar: float,
    apuesta_actual: float, stack: float, bb: float, rangos: Sequence[Rango], pos: str,
    subidas_preflop: int = 0, limpers: int = 0, iteraciones: int = 600, semilla: int = 1,
) -> dict:
    """Línea sugerida para una decisión. Devuelve equity, pot odds, acción, tamaño y razones.

    `bote` es el bote antes de actuar; `apuesta_actual` es la mayor apuesta de la calle (en total);
    `a_pagar` es lo que falta para igualar; `stack` es lo que le queda al jugador.
    """
    a_pagar = min(a_pagar, stack)
    eq = equity_multiway(cartas, rangos, tablero, iteraciones, semilla)
    nr = len(rangos)
    odds = a_pagar / (bote + a_pagar) if a_pagar > 0 else 0.0
    valor = UMBRAL_VALOR.get(nr, 0.34)
    razones: List[str] = []
    clave = clave_mano(tuple(cartas))
    pct = percentil(clave)
    puede_subir = stack > a_pagar

    ev_igualar = eq.equity * (bote + a_pagar) - a_pagar if a_pagar > 0 else None
    real = realizacion(calle, pos, nr)
    ev_realizado = eq.equity * real * (bote + a_pagar) - a_pagar if a_pagar > 0 else None
    accion, hasta = "check", None

    if calle == "preflop" and subidas_preflop == 0:
        limite = PCT_ABRIR.get(pos, 25) if pos != "BTN/SB" else 60
        razones.append(f"{clave} está en el top {pct:.0f}% de manos; desde {pos} se abre con el top {limite:.0f}%.")
        if pct <= limite and puede_subir:
            accion = "raise"
            hasta = _redondear((2.5 + limpers) * bb, bb)
            razones.append("Entra con subida" + (f" (+1 BB por cada limper: {limpers})." if limpers else "."))
        elif a_pagar == 0:
            accion = "check"
            razones.append("Mano fuera del rango de apertura, pero ver el flop es gratis.")
        elif eq.equity >= odds + MARGEN_PREFLOP:
            accion = "call"
            razones.append(f"Fuera del rango de apertura, pero el precio ({odds * 100:.0f}% de pot odds) "
                           f"es menor que la equity ({eq.equity * 100:.0f}%): completar es rentable.")
        else:
            accion = "fold"
            razones.append("Fuera del rango de apertura y el precio no compensa.")
    elif a_pagar > 0:
        margen = MARGEN_PREFLOP if calle == "preflop" else MARGEN_IGUALAR
        razones.append(f"Equity {eq.equity * 100:.0f}% contra el rango estimado de {nr} rival{'es' if nr > 1 else ''}.")
        razones.append(f"Pot odds: hay que acertar {odds * 100:.0f}% para que igualar sea rentable.")
        subir_thr = 0.62 if calle == "preflop" else valor + 0.08
        if eq.equity >= subir_thr and puede_subir:
            accion = "raise"
            hasta = min(stack + (apuesta_actual - a_pagar), _redondear(3 * apuesta_actual, bb))
            razones.append("Equity claramente superior: subir por valor y negar equity.")
        elif eq.equity >= odds + margen:
            accion = "call"
            razones.append("La equity supera las pot odds con margen.")
        else:
            accion = "fold"
            razones.append("La equity no alcanza las pot odds: igualar pierde fichas a largo plazo.")
    else:
        razones.append(f"Equity {eq.equity * 100:.0f}% contra el rango estimado de {nr} rival{'es' if nr > 1 else ''}.")
        if eq.equity >= valor and puede_subir:
            accion = "bet"
            if calle != "preflop" and len(tablero) >= 3:
                tam = tamano_sugerido(tablero)
                hasta = min(stack, _redondear(bote * tam["fraccion"], bb))
                razones.append(f"Supera el umbral de valor ({valor * 100:.0f}% con {nr} rival{'es' if nr > 1 else ''}).")
                razones.append(tam["texto"])
            else:
                hasta = _redondear(3 * bb, bb)
                razones.append(f"Supera el umbral de valor ({valor * 100:.0f}% con {nr} rival{'es' if nr > 1 else ''}).")
        else:
            accion = "check"
            razones.append("Sin ventaja suficiente para apostar por valor: ver la siguiente carta gratis.")

    info = {
        "equity": round(eq.equity, 4),
        "error_estandar": round(eq.error_estandar, 4),
        "pot_odds": round(odds, 4) if a_pagar > 0 else None,
        "ev_igualar": round(ev_igualar, 2) if ev_igualar is not None else None,
        "realizacion": round(real, 3),
        "ev_igualar_realizado": round(ev_realizado, 2) if ev_realizado is not None else None,
        "accion": accion,
        "hasta": round(hasta, 2) if hasta is not None else None,
        "razones": razones,
        "rivales": nr,
        "percentil_mano": round(pct, 1),
    }
    if len(tablero) in (3, 4):
        cat = evaluar_mejor(list(cartas) + list(tablero))[0]
        info["categoria"] = CATEGORIAS[cat]
        if cat < 8:
            mejoran = _outs(list(cartas), list(tablero), cat + 1)
            info["outs"] = [str(c) for c in mejoran]
    elif len(tablero) == 5:
        info["categoria"] = CATEGORIAS[evaluar_mejor(list(cartas) + list(tablero))[0]]
    return info


def comparar(jugada: str, sugerida: dict) -> dict:
    """Compara lo jugado con lo sugerido. Familias: retirarse, pasar/igualar, apostar/subir."""
    s = sugerida["accion"]
    if _familia(jugada) == _familia(s):
        return {"veredicto": "coincide", "detalle": ""}
    eq, odds = sugerida["equity"], sugerida.get("pot_odds")
    gravedad = "clara"
    if odds is not None and abs(eq - odds) < 0.05:
        gravedad = "leve"
    if _familia(jugada) == "R" and _familia(s) == "C" or _familia(jugada) == "C" and _familia(s) == "R":
        gravedad = "leve"
    textos = {
        ("F", "C"): "Te retiraste donde la guía igualaría o pasaría.",
        ("F", "R"): "Te retiraste donde la guía apostaría o subiría.",
        ("C", "F"): "Igualaste donde la guía se retiraría.",
        ("C", "R"): "Igualaste o pasaste donde la guía apostaría o subiría por valor.",
        ("R", "F"): "Apostaste o subiste donde la guía se retiraría.",
        ("R", "C"): "Apostaste o subiste donde la guía igualaría o pasaría.",
    }
    return {"veredicto": "desvio", "gravedad": gravedad, "detalle": textos[(_familia(jugada), _familia(s))]}


# ---------------------------------------------------------------------------
# Reproducción de una mano
# ---------------------------------------------------------------------------

def _cartas_txt(cartas) -> List[str]:
    return [str(c) for c in cartas]


def _rango_rival(m: ResultadoMano, s: int, nivel: Dict[int, str], actitud: Dict[int, str],
                 tablero: Sequence[Carta], bloq) -> Tuple[Rango, str]:
    """Rango estimado del rival `s` y una descripción corta."""
    lv = nivel.get(s, "sin_info")
    if lv == "open":
        pct = PCT_ABRIR.get(posicion(m, s), 25)
        etiqueta = f"abrió (top {pct:.0f}%)"
    else:
        pct = PCT_NIVEL[lv]
        etiqueta = {"limp": "limp", "call": "igualó una subida", "defiende": "defiende el BB", "3bet": "3-bet",
                    "4bet": "4-bet o más", "bbcheck": "BB sin subida", "sin_info": "aún sin actuar"}[lv] + f" (top {pct:g}%)"
    rango = dict(rango_top(pct))
    rango = {c: p for c, p in rango.items()}
    if tablero:
        act = actitud.get(s, "pasivo")
        estrecho = restringir_por_tablero(rango, tablero, act, bloq)
        if estrecho:
            rango = estrecho
        if act != "pasivo":
            etiqueta += f", {act}"
    return rango, etiqueta


def reproducir(m: ResultadoMano, asiento: int, iteraciones: int = 500, semilla: int = 11) -> dict:
    """Pasos de la mano con el estado de la mesa y, en las decisiones de `asiento`, el análisis."""
    n = len(m.stacks_iniciales)
    nombres = m.nombres or [f"Asiento {i + 1}" for i in range(n)]
    bb = float(m.ciega_grande or 2)
    sb = float(m.ciega_chica if m.ciega_chica is not None else bb / 2)
    cartas_h = list(m.cartas[asiento]) if m.cartas[asiento] else []
    conoce = len(cartas_h) == 2 and all(cartas_h)

    apuesta = [0.0] * n
    invertido = [0.0] * n
    folded = [False] * n
    reveladas: Dict[int, List[str]] = {}
    tablero: List[Carta] = []
    nivel: Dict[int, str] = {}
    actitud: Dict[int, str] = {s: "pasivo" for s in range(n)}
    subidas = 0
    limpers = 0
    calle = "preflop"

    def poner(s: int, monto: float) -> None:
        monto = min(monto, m.stacks_iniciales[s] - invertido[s])
        apuesta[s] += monto
        invertido[s] += monto

    poner(m.sb, sb)
    poner(m.bb, bb)

    def estado(i: int, tipo: str, etiqueta: str, seat: Optional[int], monto: Optional[float], **extra) -> dict:
        d = {
            "i": i, "calle": calle, "tipo": tipo, "etiqueta": etiqueta, "asiento": seat,
            "jugador": nombres[seat] if seat is not None else None, "monto": monto,
            "tablero": _cartas_txt(tablero), "bote": round(sum(invertido), 2),
            "apuestas": [round(x, 2) for x in apuesta], "invertido": [round(x, 2) for x in invertido],
            "retirados": list(folded),
            "stacks": [round(m.stacks_iniciales[k] - invertido[k], 2) for k in range(n)],
            "reveladas": {str(k): v for k, v in reveladas.items()},
        }
        d.update(extra)
        return d

    pasos = [estado(0, "ciegas", "Ciegas", None, None)]
    desvios = coinciden = 0
    detalle_desvios: List[int] = []

    def rivales_vivos() -> List[int]:
        return [k for k in range(n) if k != asiento and not folded[k]]

    def analizar(tipo_juego: Optional[str] = None) -> Optional[dict]:
        if not conoce or folded[asiento]:
            return None
        vivos = rivales_vivos()
        if not vivos:
            return None
        bloq = set(cartas_h) | set(tablero)
        rangos = [_rango_rival(m, k, nivel, actitud, tablero, bloq) for k in vivos]
        amax = max(apuesta)
        a_pagar = max(0.0, amax - apuesta[asiento])
        info = decidir(
            calle=calle, cartas=cartas_h, tablero=tablero, bote=sum(invertido), a_pagar=a_pagar,
            apuesta_actual=amax, stack=m.stacks_iniciales[asiento] - invertido[asiento] + 0.0, bb=bb,
            rangos=[r for r, _ in rangos], pos=posicion(m, asiento), subidas_preflop=subidas,
            limpers=limpers, iteraciones=iteraciones, semilla=semilla + len(pasos),
        )
        info["a_pagar"] = round(a_pagar, 2)
        info["rangos_rivales"] = [{"asiento": k, "jugador": nombres[k], "supuesto": txt} for k, (_, txt) in zip(vivos, rangos)]
        return info

    for e in m.eventos:
        t = e.tipo
        if t in ("reparto_cartas", "pb", "sd"):
            continue
        if t == "reparto_tablero":
            tablero.extend(e.cartas)
            calle = {3: "flop", 4: "turn", 5: "river"}.get(len(tablero), e.calle)  # e.calle trae la calle previa
            apuesta = [0.0] * n
            # La actitud de la calle anterior pesa menos en la siguiente.
            for k in actitud:
                actitud[k] = _ACTITUDES[max(0, _NIVEL_ACTITUD[actitud[k]] - 1)]
            info = None
            if conoce and not folded[asiento] and len(rivales_vivos()) >= 1:
                vivos = rivales_vivos()
                bloq = set(cartas_h) | set(tablero)
                rg = [_rango_rival(m, k, nivel, actitud, tablero, bloq)[0] for k in vivos]
                try:
                    eq = equity_multiway(cartas_h, rg, tablero, iteraciones, semilla + len(pasos))
                    info = {"equity": round(eq.equity, 4)}
                    if len(tablero) in (3, 4, 5):
                        info["categoria"] = CATEGORIAS[evaluar_mejor(cartas_h + tablero)[0]]
                except ValueError:
                    info = None
            pasos.append(estado(len(pasos), "tablero", {"flop": "Flop", "turn": "Turn", "river": "River"}.get(calle, calle),
                                None, None, nueva_calle=calle, equity_tablero=info))
            continue
        if t == "sm":
            if e.jugador is not None and e.cartas and all(e.cartas):
                reveladas[e.jugador - 1] = _cartas_txt(e.cartas)
                pasos.append(estado(len(pasos), "muestra", "Muestra", e.jugador - 1, None))
            continue
        if e.jugador is None or t not in ("f", "cc", "cbr"):
            continue

        s = e.jugador - 1
        amax = max(apuesta)
        es_heroe = s == asiento
        analisis = analizar() if es_heroe else None

        if t == "f":
            etiqueta, jugada = "Fold", "fold"
            monto = None
            folded[s] = True
            nivel.pop(s, None)
        elif t == "cc":
            pagar = amax - apuesta[s]
            monto = float(e.monto) if e.monto else 0.0
            if pagar > 0 or monto > 0:
                jugada, etiqueta = "call", "Call"
                poner(s, monto)
                if calle == "preflop":
                    if subidas == 0:
                        nivel[s] = "limp"
                        limpers += 1
                    else:
                        nivel[s] = "defiende" if s == m.bb else "call"
                else:
                    actitud[s] = max(actitud[s], "igual", key=_NIVEL_ACTITUD.get)
            else:
                jugada, etiqueta, monto = "check", "Check", None
                if calle == "preflop" and s == m.bb and subidas == 0:
                    nivel[s] = "bbcheck"
        else:
            hasta = float(e.monto)
            anadido = hasta - apuesta[s]
            jugada = "raise" if amax > 0 else "bet"
            etiqueta = "Raise" if jugada == "raise" else "Bet"
            poner(s, anadido)
            monto = round(anadido, 2)
            if calle == "preflop":
                subidas += 1
                nivel[s] = "open" if subidas == 1 else "3bet" if subidas == 2 else "4bet"
            else:
                actitud[s] = "sube" if jugada == "raise" else "apuesta"

        extra = {"es_heroe": es_heroe, "jugada": jugada, "hasta": round(apuesta[s], 2)}
        if analisis is not None:
            cmp = comparar(jugada, analisis)
            extra["analisis"] = analisis
            extra["comparacion"] = cmp
            if cmp["veredicto"] == "coincide":
                coinciden += 1
            else:
                desvios += 1
                detalle_desvios.append(len(pasos))
        pasos.append(estado(len(pasos), jugada, etiqueta, s, monto, **extra))

    ganancia = [round(x, 2) for x in m.neto]
    pasos.append(estado(len(pasos), "resultado", "Resultado", None, None, neto=ganancia,
                        neto_bb=[round(x / bb, 2) for x in m.neto]))
    return {
        "heroe": {"asiento": asiento, "nombre": nombres[asiento], "cartas": _cartas_txt(cartas_h) if conoce else [],
                  "posicion": posicion(m, asiento)},
        "mesa": {"jugadores": [{"asiento": k, "nombre": nombres[k], "posicion": posicion(m, k),
                                "stack": m.stacks_iniciales[k]} for k in range(n)],
                 "boton": m.boton, "sb": m.sb, "bb": m.bb, "ciega_grande": bb, "ciega_chica": sb},
        "pasos": pasos,
        "resumen": {"decisiones": coinciden + desvios, "coincide": coinciden, "desvios": desvios,
                    "pasos_con_desvio": detalle_desvios, "con_analisis": conoce,
                    "neto_bb": round(m.neto[asiento] / bb, 2)},
    }


def analisis_puntual(
    cartas: Sequence[Carta], tablero: Sequence[Carta], bote: float, a_pagar: float, bb: float,
    rivales: Sequence[dict], pos: str = "BTN", stack: float = 1e9, calle: Optional[str] = None,
    subidas_preflop: int = 0, limpers: int = 0, iteraciones: int = 1500, semilla: int = 1,
) -> dict:
    """Análisis de una situación escrita a mano. Cada rival es {"top": 20} o {"claves": ["AA", "AKs"]}."""
    if not rivales:
        raise ValueError("indicá al menos un rival")
    if len(set(list(cartas) + list(tablero))) != len(cartas) + len(tablero):
        raise ValueError("hay cartas repetidas")
    rangos: List[Rango] = []
    for r in rivales:
        if "claves" in r and r["claves"]:
            claves = [c for c in r["claves"] if c in COMBOS]
            if not claves:
                raise ValueError("rango sin manos válidas")
            rangos.append({c: 1.0 for c in claves})
        else:
            rangos.append(dict(rango_top(float(r.get("top", 100)))))
    calle = calle or {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(tablero)]
    return decidir(
        calle=calle, cartas=cartas, tablero=tablero, bote=bote, a_pagar=a_pagar,
        apuesta_actual=a_pagar, stack=stack, bb=bb, rangos=rangos, pos=pos,
        subidas_preflop=subidas_preflop, limpers=limpers, iteraciones=iteraciones, semilla=semilla,
    )
