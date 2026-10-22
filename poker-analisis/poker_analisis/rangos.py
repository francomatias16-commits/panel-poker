"""Inferencia de rangos y predicción de acciones preflop.

Modelo:
- Prior: distribución sobre las 169 manos canónicas, ponderada por el número de
  combinaciones de cada una (pareja 6, suited 4, offsuit 12). Es la distribución
  de una mano repartida al azar.
- Verosimilitud: P(acción | mano, perfil, contexto). Se estima con un
  suavizado jerárquico: la distribución de la mano concreta se contrae hacia la
  distribución del perfil con una fuerza k (una especie de prior Dirichlet).
- Contexto: 'abre' si nadie subió antes en preflop, 'responde' si alguien ya subió.
- Posterior: P(mano | historia) ∝ prior × Π P(acción_i | mano, perfil, contexto_i),
  usando solo las acciones propias del jugador en la mano.
- Predicción: P(próxima acción | historia) = Σ_mano P(mano | historia) P(acción | mano, ...).
- Calibración: escalado de temperatura, p_i ∝ p_i^T, con T ajustado por
  máxima verosimilitud sobre una partición de validación distinta de la de prueba.

Limitaciones deliberadas: no usa posición ni las acciones de los otros jugadores,
y el suavizado asume que todas las manos de un perfil comparten un comportamiento base.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .bots import clave_mano
from .cartas import RANGOS
from .motor import ResultadoMano, grupo_posicion

ACCIONES = ("fold", "check", "call", "raise")
CONTEXTOS = ("abre", "responde")
Historia = List[Tuple[str, str]]  # (contexto, acción)


def claves_canonicas() -> List[str]:
    rangos = RANGOS[::-1]
    claves = []
    for i, alto in enumerate(rangos):
        for bajo in rangos[i:]:
            if alto == bajo:
                claves.append(alto + bajo)
            else:
                claves.append(alto + bajo + "s")
                claves.append(alto + bajo + "o")
    return claves


CLAVES = claves_canonicas()
COMBOS = {c: (6 if len(c) == 2 else 4 if c.endswith("s") else 12) for c in CLAVES}
TOTAL_COMBOS = sum(COMBOS.values())
PRIOR = {c: COMBOS[c] / TOTAL_COMBOS for c in CLAVES}


def observaciones(
    mano: ResultadoMano, con_posicion: bool = False, con_rivales: bool = False
) -> Dict[int, List[Tuple[str, str, str]]]:
    """Acciones preflop de cada asiento: (clave_real, contexto, acción).

    El contexto siempre incluye si alguien subió antes. Opcionalmente agrega:
    - `con_posicion`: grupo de posición del jugador respecto del botón.
    - `con_rivales`: cuántos rivales ya habían entrado al bote (0, 1 o 2 o más).
    """
    obs: Dict[int, List[Tuple[str, str, str]]] = defaultdict(list)
    n = len(mano.neto)
    subidas = 0
    entraron: set = set()  # asientos que ya pusieron fichas voluntarias en preflop
    for e in mano.eventos:
        if e.calle != "preflop" or e.jugador is None or e.tipo not in ("cbr", "cc", "f"):
            continue
        s = e.jugador - 1
        contexto = "abre" if subidas == 0 else "responde"
        if con_posicion:
            contexto += "|" + grupo_posicion(s, mano.boton, n)
        if con_rivales:
            contexto += f"|r{min(len(entraron - {s}), 2)}"
        if e.tipo == "f":
            accion = "fold"
        elif e.tipo == "cc":
            accion = "check" if e.monto is None else "call"
        else:
            accion = "raise"
        # Sin las dos cartas del jugador no hay verdad de terreno: esas decisiones no se usan.
        if len(mano.cartas[s]) == 2 and all(c is not None for c in mano.cartas[s]):
            obs[s].append((clave_mano(mano.cartas[s]), contexto, accion))
        if e.tipo == "cbr":
            subidas += 1
        if e.tipo == "cbr" or (e.tipo == "cc" and e.monto is not None):
            entraron.add(s)
    return obs


class ModeloRangos:
    def __init__(self, k: float = 5.0, con_posicion: bool = False, con_rivales: bool = False) -> None:
        self.k = k
        self.con_posicion = con_posicion
        self.con_rivales = con_rivales
        self._perfil: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
        self._mano: Dict[Tuple[str, str, str], Counter] = defaultdict(Counter)
        self._matrices: Dict[Tuple[str, str], List[List[float]]] = {}

    def entrenar(self, manos: Iterable[ResultadoMano], nombres: Sequence[str]) -> None:
        for mano in manos:
            for s, lista in observaciones(mano, self.con_posicion, self.con_rivales).items():
                perfil = (mano.nombres or nombres)[s]
                for clave, contexto, accion in lista:
                    self._perfil[(perfil, contexto)][accion] += 1
                    self._mano[(perfil, clave, contexto)][accion] += 1
        self._matrices = {}  # el caché depende de los conteos

    def base(self, perfil: str, contexto: str) -> Dict[str, float]:
        """Distribución de acciones del perfil, sin información de la mano."""
        cuenta = self._perfil[(perfil, contexto)]
        total = sum(cuenta.values()) + len(ACCIONES)
        return {a: (cuenta[a] + 1) / total for a in ACCIONES}

    def p_accion(self, perfil: str, clave: str, contexto: str) -> Dict[str, float]:
        base = self.base(perfil, contexto)
        cuenta = self._mano[(perfil, clave, contexto)]
        n = sum(cuenta.values())
        return {a: (cuenta[a] + self.k * base[a]) / (n + self.k) for a in ACCIONES}

    def _matriz(self, perfil: str, contexto: str) -> List[List[float]]:
        """Probabilidades P(acción | clave) para todas las claves, en orden de ACCIONES."""
        clave_cache = (perfil, contexto)
        if clave_cache not in self._matrices:
            self._matrices[clave_cache] = [
                [self.p_accion(perfil, c, contexto)[a] for a in ACCIONES] for c in CLAVES
            ]
        return self._matrices[clave_cache]

    def posterior(self, perfil: str, historia: Historia) -> Dict[str, float]:
        pesos = [PRIOR[c] for c in CLAVES]
        for contexto, accion in historia:
            j = ACCIONES.index(accion)
            filas = self._matriz(perfil, contexto)
            pesos = [p * fila[j] for p, fila in zip(pesos, filas)]
        total = sum(pesos)
        return {c: p / total for c, p in zip(CLAVES, pesos)}

    def predecir(self, perfil: str, historia: Historia, contexto: str) -> Dict[str, float]:
        post = self.posterior(perfil, historia)  # una sola vez, no una por clave
        pesos = [post[c] for c in CLAVES]
        filas = self._matriz(perfil, contexto)
        return {a: sum(p * fila[j] for p, fila in zip(pesos, filas)) for j, a in enumerate(ACCIONES)}


# ---------------------------------------------------------------------------
# Evaluación y calibración
# ---------------------------------------------------------------------------

def recolectar(modelo: ModeloRangos, manos: Sequence[ResultadoMano], nombres: Sequence[str]) -> List[dict]:
    """Una fila por decisión preflop: predicción, base, acción real y ganancia de información."""
    registros = []
    for mano in manos:
        for s, lista in observaciones(mano, modelo.con_posicion, modelo.con_rivales).items():
            perfil = (mano.nombres or nombres)[s]
            for k, (clave, contexto, accion) in enumerate(lista):
                historia = [(ctx, acc) for (_, ctx, acc) in lista[:k]]
                ganancia = None
                if k > 0:
                    post = modelo.posterior(perfil, historia)
                    ganancia = math.log2(post[clave] / PRIOR[clave])
                registros.append({
                    "perfil": perfil,
                    "pred": modelo.predecir(perfil, historia, contexto),
                    "base": modelo.base(perfil, contexto),
                    "accion": accion,
                    "ganancia": ganancia,
                })
    return registros


def temperatura(pred: Dict[str, float], T: float) -> Dict[str, float]:
    """Escalado de temperatura: p_i ∝ p_i^T. T=1 no cambia la distribución."""
    q = {a: max(p, 1e-12) ** T for a, p in pred.items()}
    total = sum(q.values())
    return {a: v / total for a, v in q.items()}


def ajustar_isotonica(pares: Sequence[Tuple[float, bool]]) -> List[Tuple[float, float]]:
    """Regresión isotónica (pool adjacent violators) de acierto frente a confianza.

    Devuelve bloques (confianza_máxima, acierto_medio), en orden creciente.
    La función resultante es monótona no decreciente.
    """
    bloques: List[list] = []  # [suma, n, x_max]
    for x, y in sorted(pares, key=lambda p: p[0]):
        bloques.append([float(y), 1, x])
        while len(bloques) > 1 and bloques[-2][0] / bloques[-2][1] > bloques[-1][0] / bloques[-1][1]:
            s, n, xm = bloques.pop()
            bloques[-1][0] += s
            bloques[-1][1] += n
            bloques[-1][2] = xm
    return [(xm, s / n) for s, n, xm in bloques]


def transformar_isotonica(iso: Sequence[Tuple[float, float]], lam: float = 1.0):
    """Función pred -> pred que recalibra la confianza de la clase principal.

    La confianza final mezcla la isotónica con la original: q = λ·iso + (1-λ)·p.
    Con λ < 1 se evita que un tramo de la isotónica con pocos datos lleve la
    confianza a cero. La masa restante se reparte entre las otras clases en
    proporción a sus probabilidades originales, así la salida sigue siendo una distribución.
    """
    def aplicar(pred: Dict[str, float]) -> Dict[str, float]:
        top = max(pred, key=pred.get)
        p = pred[top]
        if p >= 1 - 1e-9:
            return dict(pred)
        q_iso = iso[-1][1]
        for xm, v in iso:
            if p <= xm:
                q_iso = v
                break
        q = lam * q_iso + (1 - lam) * p
        q = min(max(q, 1e-6), 1 - 1e-6)
        return {a: (q if a == top else pred[a] * (1 - q) / (1 - p)) for a in pred}

    return aplicar


def ajustar_lambda_isotonica(registros: Sequence[dict], iso: Sequence[Tuple[float, float]],
                             grilla: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.0)) -> float:
    """λ de la mezcla que minimiza el logloss sobre los registros de validación."""
    mejor_lam, mejor_nll = 1.0, float("inf")
    for lam in grilla:
        f = transformar_isotonica(iso, lam)
        nll = sum(-math.log(max(f(r["pred"])[r["accion"]], 1e-12)) for r in registros) / len(registros)
        if nll < mejor_nll:
            mejor_lam, mejor_nll = lam, nll
    return mejor_lam


def ajustar_temperatura(registros: Sequence[dict], grilla: Optional[Sequence[float]] = None) -> float:
    """T que minimiza el logloss medio sobre los registros de validación."""
    grilla = grilla or [round(0.2 + 0.05 * i, 2) for i in range(61)]  # 0,2 a 3,2
    mejor_T, mejor_nll = 1.0, float("inf")
    for T in grilla:
        nll = sum(-math.log(max(temperatura(r["pred"], T)[r["accion"]], 1e-12)) for r in registros)
        nll /= len(registros)
        if nll < mejor_nll:
            mejor_T, mejor_nll = T, nll
    return mejor_T


def resumen(registros: Sequence[dict], nombres: Sequence[str], transformar=None) -> List[dict]:
    """Métricas por perfil, con el modelo base como referencia.

    `transformar` es una función opcional pred -> pred (por ejemplo, calibración).
    """
    por_perfil: Dict[str, List[dict]] = defaultdict(list)
    for r in registros:
        por_perfil[r["perfil"]].append(r)

    filas = []
    for perfil in dict.fromkeys(nombres):
        rs = por_perfil.get(perfil)
        if not rs:
            continue
        n = len(rs)
        ll = ll_base = br = br_base = acierto = 0.0
        ganancias = []
        for r in rs:
            p = transformar(r["pred"]) if transformar else r["pred"]
            a = r["accion"]
            ll += -math.log(max(p[a], 1e-12))
            ll_base += -math.log(max(r["base"][a], 1e-12))
            br += sum((p[x] - (x == a)) ** 2 for x in ACCIONES)
            br_base += sum((r["base"][x] - (x == a)) ** 2 for x in ACCIONES)
            acierto += max(p, key=p.get) == a
            if r["ganancia"] is not None:
                ganancias.append(r["ganancia"])
        filas.append({
            "perfil": perfil,
            "decisiones": n,
            "logloss": ll / n,
            "logloss_base": ll_base / n,
            "mejora_logloss_%": 100 * (1 - ll / ll_base),
            "brier": br / n,
            "brier_base": br_base / n,
            "acierto_top1": acierto / n,
            "ganancia_bits": sum(ganancias) / len(ganancias) if ganancias else float("nan"),
        })
    return filas


def calibracion(registros: Sequence[dict], transformar=None, bins: int = 10) -> Tuple[List[dict], float]:
    """Confianza media frente a acierto real por intervalo, y error de calibración esperado (ECE)."""
    pares = []
    for r in registros:
        p = transformar(r["pred"]) if transformar else r["pred"]
        top = max(p, key=p.get)
        pares.append((p[top], top == r["accion"]))

    cubetas: List[list] = [[] for _ in range(bins)]
    for conf, acierto in pares:
        cubetas[min(int(conf * bins), bins - 1)].append((conf, acierto))

    total = len(pares)
    salida = []
    ece = 0.0
    for i, c in enumerate(cubetas):
        if not c:
            continue
        conf = sum(x for x, _ in c) / len(c)
        acc = sum(y for _, y in c) / len(c)
        ece += len(c) / total * abs(acc - conf)
        salida.append({
            "intervalo": f"{i / bins:.1f}-{(i + 1) / bins:.1f}",
            "n": len(c),
            "confianza_media": conf,
            "acierto_real": acc,
        })
    return salida, ece


# ---------------------------------------------------------------------------
# Validación cruzada temporal (plan, sección 7)
# ---------------------------------------------------------------------------

def validacion_temporal(
    manos: Sequence[ResultadoMano],
    nombres: Sequence[str],
    pliegues: int = 5,
    recalibrar: bool = False,
    **opciones_modelo,
) -> List[dict]:
    """Validación de origen móvil: entrena con el pasado y evalúa en el bloque siguiente.

    Las manos se toman en el orden recibido, que debe ser el cronológico. Se dividen en
    `pliegues + 1` bloques; en el pliegue i se entrena con los bloques 0..i-1 y se evalúa
    en el bloque i. Nunca se entrena con manos posteriores a las evaluadas, así no hay
    fuga de información del futuro al pasado. `opciones_modelo` se pasa a `ModeloRangos`.

    Devuelve una fila por pliegue con logloss, Brier y error de calibración esperado (ECE) del modelo,
    más logloss y Brier del modelo base. La clave `curva` trae la curva de calibración del pliegue
    (ver `calibracion`).

    Con `recalibrar=True`, en cada pliegue el entrenamiento se parte en orden cronológico: el 80 %
    inicial entrena el modelo y el 20 % final (el pasado más cercano a la prueba) ajusta la
    temperatura de calibración. La prueba nunca interviene en el ajuste. Agrega `T`,
    `logloss_nucleo` y `ece_nucleo` (mismo modelo, sin recalibrar) y `logloss_cal` y `ece_cal`
    (recalibrado), para comparar en igualdad de condiciones.
    """
    if pliegues < 1:
        raise ValueError("pliegues debe ser al menos 1")
    n = len(manos)
    if n < pliegues + 1:
        raise ValueError("no hay manos suficientes para esa cantidad de pliegues")
    tam = n // (pliegues + 1)
    filas = []
    for i in range(1, pliegues + 1):
        fin_entrenamiento = i * tam
        fin_prueba = (i + 1) * tam if i < pliegues else n
        entrenamiento, prueba = manos[:fin_entrenamiento], manos[fin_entrenamiento:fin_prueba]
        modelo = ModeloRangos(**opciones_modelo)
        modelo.entrenar(entrenamiento, nombres=nombres)
        registros = recolectar(modelo, prueba, nombres=nombres)
        if not registros:
            continue
        d = len(registros)
        ll = ll_base = br = br_base = 0.0
        for r in registros:
            a = r["accion"]
            ll += -math.log(max(r["pred"][a], 1e-12))
            ll_base += -math.log(max(r["base"][a], 1e-12))
            br += sum((r["pred"][x] - (x == a)) ** 2 for x in ACCIONES)
            br_base += sum((r["base"][x] - (x == a)) ** 2 for x in ACCIONES)
        curva, ece = calibracion(registros)
        extra = {}
        if recalibrar:
            corte = int(len(entrenamiento) * 0.8)
            nucleo, ajuste = entrenamiento[:corte], entrenamiento[corte:]
            if nucleo and ajuste:
                m2 = ModeloRangos(**opciones_modelo)
                m2.entrenar(nucleo, nombres=nombres)
                reg_ajuste = recolectar(m2, ajuste, nombres=nombres)
                reg_prueba = recolectar(m2, prueba, nombres=nombres)
                if reg_ajuste and reg_prueba:
                    T = ajustar_temperatura(reg_ajuste)
                    f = lambda pred, T=T: temperatura(pred, T)  # noqa: E731
                    ll_n = sum(-math.log(max(r["pred"][r["accion"]], 1e-12)) for r in reg_prueba) / len(reg_prueba)
                    ll_c = sum(-math.log(max(f(r["pred"])[r["accion"]], 1e-12)) for r in reg_prueba) / len(reg_prueba)
                    extra = {
                        "T": T,
                        "logloss_nucleo": ll_n,
                        "ece_nucleo": calibracion(reg_prueba)[1],
                        "logloss_cal": ll_c,
                        "ece_cal": calibracion(reg_prueba, f)[1],
                    }
        filas.append({
            "pliegue": i,
            "manos_entrenamiento": len(entrenamiento),
            "manos_prueba": len(prueba),
            "decisiones": d,
            "logloss": ll / d,
            "logloss_base": ll_base / d,
            "brier": br / d,
            "brier_base": br_base / d,
            "ece": ece,
            "curva": curva,
            **extra,
        })
    return filas
