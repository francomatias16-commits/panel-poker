"""Modo práctica: jugar manos contra los bots del proyecto con la guía activa.

Es la forma legítima de que la guía responda a cada jugada en el momento: se juega sin dinero ni terceros.
Vos ocupás el asiento 0 y los demás son bots (TAG, pasivos y uno aleatorio).

Diseño sin estado de partida a medias: cada mano se reconstruye desde cero con la misma semilla y la lista de
acciones que ya tomaste. Los bots son deterministas dadas la semilla y la mano, así que la reconstrucción
reproduce exactamente lo ya jugado y se detiene en tu próxima decisión (excepción interna `_Pausa`).

La guía solo ve lo que verías vos: tus cartas, el tablero y las acciones previas. Las cartas de los rivales no
salen del servidor hasta el showdown.
"""

from __future__ import annotations

import os
import random
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import guia
from .bots import BotAleatorio, BotPasivo, BotTAG, cargar_tabla_preflop
from .cartas import Mazo
from .motor import ResultadoMano, Vista, _Mano
from .phh import Evento
from .simulacion import BLIND_CHICO, BLIND_GRANDE, STACK_INICIAL, UMBRAL_TAG

NOMBRES = ["Vos", "TAG-1", "Pasivo-1", "TAG-2", "Pasivo-2", "Aleatorio"]
HEROE = 0
ITER_GUIA = 300
ITER_REVISION = 400
_RUTA_TABLA = os.path.join(os.path.dirname(__file__), "..", "resultados", "preflop_equity.csv")


class _Pausa(Exception):
    """El motor llegó a una decisión tuya y no hay acción cargada."""

    def __init__(self, vista: Vista) -> None:
        super().__init__("decisión pendiente")
        self.vista = vista


def _bots(tabla, semilla: int) -> list:
    """Políticas de los asientos 1 a 5 (el 0 es del jugador)."""
    pol = [None]
    for k, nombre in enumerate(NOMBRES[1:], start=1):
        s = semilla * 10 + k
        if nombre.startswith("TAG"):
            pol.append(BotTAG(tabla, BLIND_GRANDE, umbral_preflop=UMBRAL_TAG, semilla=s))
        elif nombre.startswith("Pasivo"):
            pol.append(BotPasivo(tabla, BLIND_GRANDE, semilla=s))
        else:
            pol.append(BotAleatorio(semilla=s))
    return pol


def _tabla_defecto():
    return cargar_tabla_preflop(_RUTA_TABLA)


def jugar(tabla, semilla_mano: int, boton: int, stacks: Sequence[int],
          acciones: Sequence[Tuple[str, Optional[int]]]) -> Tuple[_Mano, Optional[ResultadoMano], Optional[Vista]]:
    """Reconstruye la mano con las acciones del jugador. Devuelve (mano, resultado, decisión pendiente).

    Con `resultado` None la mano sigue y `vista` es tu decisión. Con resultado, la mano terminó.
    """
    pendientes = list(acciones)
    pol = _bots(tabla, semilla_mano)

    def humano(v: Vista):
        if not pendientes:
            raise _Pausa(v)
        return pendientes.pop(0)

    pol[HEROE] = humano
    mano = _Mano(list(stacks), boton, BLIND_CHICO, BLIND_GRANDE, pol, Mazo(semilla=semilla_mano))
    try:
        return mano, mano.run(), None
    except _Pausa as p:
        return mano, None, p.vista


def _parcial(mano: _Mano, extra: Sequence[Evento] = ()) -> ResultadoMano:
    """Mano a medias como ResultadoMano, para reutilizar la guía sin duplicar su lógica."""
    n = mano.n
    return ResultadoMano(
        boton=mano.boton, sb=mano.sb, bb=mano.bb, stacks_iniciales=list(mano.inicial), stacks_finales=list(mano.stack),
        neto=[0] * n, cartas=list(mano.cartas), tablero=list(mano.tablero), eventos=list(mano.eventos) + list(extra),
        vieron_flop=[], llegaron_showdown=[], ganadores_showdown=[], nombres=list(NOMBRES),
        ciega_grande=BLIND_GRANDE, ciega_chica=BLIND_CHICO,
    )


def sugerencia(mano: _Mano, vista: Vista, iteraciones: int = ITER_GUIA) -> dict:
    """Línea sugerida por la guía para tu decisión pendiente (usa solo lo que ves)."""
    falso = Evento(vista.calle, HEROE + 1, "cc", monto=vista.pagar or None)  # acción ficticia: la guía analiza antes de aplicarla
    rep = guia.reproducir(_parcial(mano, [falso]), HEROE, iteraciones=iteraciones)
    pasos = [p for p in rep["pasos"] if p.get("analisis")]
    if not pasos:
        raise ValueError("la guía no tiene rivales que analizar")
    return pasos[-1]["analisis"]


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

@dataclass
class _Acumulado:
    manos: int = 0
    neto_bb: float = 0.0
    decisiones: int = 0
    coinciden: int = 0


class Sesion:
    """Una sesión de práctica: stacks que persisten entre manos y acumulado de resultado y desvíos."""

    def __init__(self, tabla=None, semilla: Optional[int] = None, guia_activa: bool = True) -> None:
        self.tabla = tabla if tabla is not None else _tabla_defecto()
        self.semilla = random.randrange(1, 10**6) if semilla is None else int(semilla)
        self.guia_activa = guia_activa
        self.lock = threading.RLock()
        self.n_mano = 0
        self.stacks = [STACK_INICIAL] * len(NOMBRES)
        self.acciones: List[Tuple[str, Optional[int]]] = []
        self.acum = _Acumulado()
        self.historial: List[dict] = []
        self._sugerencias: Dict[int, dict] = {}
        self._rev: Optional[dict] = None
        self._cerrada = False  # la mano actual ya se contó en el acumulado
        self._preparar_mano()

    # --- control -----------------------------------------------------------
    def _preparar_mano(self) -> None:
        self.n_mano += 1
        for i, s in enumerate(self.stacks):
            if s > STACK_INICIAL:
                self.stacks[i] = STACK_INICIAL
            elif s < 2 * BLIND_GRANDE:
                self.stacks[i] = STACK_INICIAL
        self.stacks_mano = list(self.stacks)
        self.acciones = []
        self._sugerencias = {}
        self._rev = None
        self._cerrada = False

    def _semilla_mano(self) -> int:
        return self.semilla * 100_000 + self.n_mano

    def _boton(self) -> int:
        return (self.n_mano - 1) % len(NOMBRES)

    def _reconstruir(self):
        return jugar(self.tabla, self._semilla_mano(), self._boton(), self.stacks_mano, self.acciones)

    def actuar(self, tipo: str, hasta: Optional[int] = None) -> dict:
        with self.lock:
            mano, res, vista = self._reconstruir()
            if res is not None:
                raise ValueError("la mano ya terminó: pasá a la siguiente")
            if tipo not in ("f", "cc", "cbr"):
                raise ValueError("acción inválida")
            if tipo == "cbr":
                if not vista.puede_subir:
                    raise ValueError("no podés subir en esta situación")
                if hasta is None or not vista.minimo_hasta <= int(hasta) <= vista.maximo_hasta:
                    # Subir menos que el mínimo solo es legal yendo all-in.
                    if not (hasta is not None and int(hasta) == vista.maximo_hasta):
                        raise ValueError(f"la subida va de {vista.minimo_hasta} a {vista.maximo_hasta} fichas")
            self.acciones.append((tipo, int(hasta) if tipo == "cbr" else None))
            return self.estado()

    def siguiente(self) -> dict:
        with self.lock:
            _, res, _ = self._reconstruir()
            if res is None:
                raise ValueError("la mano todavía no terminó")
            self._cerrar(res)
            self.stacks = list(res.stacks_finales)
            self._preparar_mano()
            return self.estado()

    def configurar(self, guia_activa: bool) -> dict:
        with self.lock:
            self.guia_activa = bool(guia_activa)
            return self.estado()

    # --- cierre y acumulado ---------------------------------------------------
    def _revision(self, res: ResultadoMano) -> dict:
        if self._rev is None:
            self._rev = self._calcular_revision(res)
        return self._rev

    def _calcular_revision(self, res: ResultadoMano) -> dict:
        rep = guia.reproducir(res, HEROE, iteraciones=ITER_REVISION)
        desvios = []
        for i in rep["resumen"]["pasos_con_desvio"]:
            p = rep["pasos"][i]
            a, c = p["analisis"], p["comparacion"]
            desvios.append({"calle": p["calle"], "jugada": p["jugada"], "sugerida": a["accion"], "gravedad": c["gravedad"],
                            "detalle": c["detalle"], "equity": a["equity"], "pot_odds": a["pot_odds"]})
        r = rep["resumen"]
        return {"decisiones": r["decisiones"], "coincide": r["coincide"], "desvios": desvios}

    def _cerrar(self, res: ResultadoMano) -> None:
        if self._cerrada:
            return
        rev = self._revision(res)
        neto = round(res.neto[HEROE] / BLIND_GRANDE, 2)
        self.acum.manos += 1
        self.acum.neto_bb += neto
        self.acum.decisiones += rev["decisiones"]
        self.acum.coinciden += rev["coincide"]
        self.historial.append({"n": self.n_mano, "neto_bb": neto, "decisiones": rev["decisiones"],
                               "coincide": rev["coincide"], "desvios": rev["desvios"]})
        self._cerrada = True

    # --- estado serializable -------------------------------------------------
    def _linea(self, e: Evento) -> Optional[dict]:
        bb = BLIND_GRANDE
        fmt = lambda x: f"{x / bb:.1f}".rstrip("0").rstrip(".") + " bb"  # noqa: E731
        if e.tipo == "reparto_tablero":
            return {"calle": e.calle, "texto": "Tablero: " + " ".join(str(c) for c in e.cartas), "tablero": True}
        if e.jugador is None or e.tipo not in ("f", "cc", "cbr"):
            return None
        nombre = NOMBRES[e.jugador - 1]
        if e.tipo == "f":
            texto = f"{nombre} se retira"
        elif e.tipo == "cc":
            texto = f"{nombre} iguala {fmt(e.monto)}" if e.monto else f"{nombre} pasa"
        else:
            texto = f"{nombre} sube a {fmt(e.monto)}"
        return {"calle": e.calle, "texto": texto, "heroe": e.jugador - 1 == HEROE}

    def estado(self) -> dict:
        with self.lock:
            mano, res, vista = self._reconstruir()
            n = len(NOMBRES)
            parcial = _parcial(mano)
            terminada = res is not None
            fuente = res if terminada else parcial
            bb = BLIND_GRANDE
            e = {
                "mano": self.n_mano, "semilla": self.semilla, "guia_activa": self.guia_activa, "terminada": terminada,
                "ciega_grande": bb, "boton": mano.boton,
                "jugadores": [{"asiento": i, "nombre": NOMBRES[i], "posicion": guia.posicion(parcial, i),
                               "stack": mano.stack[i], "apuesta": mano.apuesta[i], "retirado": mano.folded[i],
                               "all_in": mano.allin[i]} for i in range(n)],
                "cartas": [str(c) for c in mano.cartas[HEROE]],
                "tablero": [str(c) for c in mano.tablero],
                "bote": sum(mano.contrib),
                "log": [l for l in (self._linea(ev) for ev in fuente.eventos) if l],
                "acumulado": self._resumen_acum(incluir_actual=terminada and not self._cerrada, res=res),
            }
            if not terminada:
                e["pendiente"] = {"calle": vista.calle, "pagar": vista.pagar, "puede_subir": vista.puede_subir,
                                  "minimo_hasta": vista.minimo_hasta, "maximo_hasta": vista.maximo_hasta,
                                  "apuesta_actual": vista.apuesta_actual, "stack": vista.stack}
                if self.guia_activa:
                    k = len(self.acciones)
                    if k not in self._sugerencias:
                        self._sugerencias[k] = sugerencia(mano, vista)
                    e["guia"] = self._sugerencias[k]
            else:
                rev = self._revision(res)
                revelados = {str(i): [str(c) for c in res.cartas[i]] for i in res.llegaron_showdown}
                e["resultado"] = {"neto_bb": round(res.neto[HEROE] / bb, 2), "showdown": revelados,
                                  "ganadores": res.ganadores_showdown,
                                  "netos_bb": [round(x / bb, 2) for x in res.neto], "revision": rev}
                e["jugadores"] = [dict(j, stack=res.stacks_finales[j["asiento"]]) for j in e["jugadores"]]
            return e

    def _resumen_acum(self, incluir_actual: bool = False, res: Optional[ResultadoMano] = None) -> dict:
        manos, neto = self.acum.manos, self.acum.neto_bb
        dec, coin = self.acum.decisiones, self.acum.coinciden
        if incluir_actual and res is not None:  # mostrar la mano recién terminada sin cerrarla todavía
            rev = self._revision(res)
            manos += 1
            neto += res.neto[HEROE] / BLIND_GRANDE
            dec += rev["decisiones"]
            coin += rev["coincide"]
        return {"manos": manos, "neto_bb": round(neto, 2), "bb100": round(neto / manos * 100, 1) if manos else None,
                "decisiones": dec, "coinciden": coin, "pct_guia": round(coin / dec, 3) if dec else None}
