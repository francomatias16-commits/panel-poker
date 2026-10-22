"""Estadísticas completas por jugador (Fase 1 del plan).

Cada estadística se guarda como (éxitos, oportunidades): el porcentaje sale de ahí y viene con su intervalo de
Wilson al 95 % y una alerta de muestra. Una estadística con pocas oportunidades no es confiable aunque el
porcentaje parezca claro.

Definiciones (una oportunidad cuenta una vez por jugador y mano):

Preflop
- vpip / pfr: sobre todas las manos, también desglosadas por posición ("vpip@BTN").
- 3bet: primera acción del jugador frente a una sola subida. 4bet: frente a una re-subida.
- fold_3bet: el que abrió la subida y enfrenta una re-subida (antes de cualquier 4-bet): se retira.
- robo: abrir con subida desde CO, BTN o SB cuando todos los anteriores se retiraron (sin limpers).
- bb_robo_fold / bb_robo_call / bb_robo_3bet: defensa de la ciega grande ante un robo sin igualaciones intermedias.

Postflop
- cbet_flop: el último agresor preflop apuesta primero en el flop. barril_turn / barril_river: sigue apostando en
  la calle siguiente después de haber apostado en la anterior.
- fold_cbet_flop / fold_barril_turn / fold_barril_river: retiro ante esa apuesta, antes de que alguien suba.
- checkraise_<calle>: el jugador pasó y, al enfrentar una apuesta en la misma calle, sube.
- donk_flop: apuesta en el flop un jugador distinto del último agresor preflop, antes de que este actúe.
- agr@<calle>: (apuestas + subidas, igualaciones). El factor de agresión es el cociente.
- wtsd: llega al showdown dado que vio el flop. wsd: gana dado que llegó al showdown.
- farol_river_visible: apuesta o sube en el river, dado que llegó al showdown y su mano se conoce; éxito = perdió.
  Solo ve los faroles que se pagaron: subestima la frecuencia real de faroles.

Resultado: bb/100 con intervalo, por profundidad de stack y por cantidad de rivales; rake atribuido a las manos
que el jugador ganó (en proporción a su neto positivo).

No hay rangos de referencia: se calibran con fuentes confiables antes de usarse como criterio (ver el plan).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .motor import ResultadoMano

MUESTRA_INSUFICIENTE = 30  # menos oportunidades que esto: no usar la estadística
MUESTRA_BAJA = 100  # entre ambos umbrales: orientativa
POSICIONES = ("UTG", "MP", "CO", "BTN", "SB", "BB")
_ROBO = ("CO", "BTN", "SB")
CALLES = ("flop", "turn", "river")


@dataclass(frozen=True)
class Frecuencia:
    exitos: int
    n: int

    @property
    def valor(self) -> Optional[float]:
        return self.exitos / self.n if self.n else None

    @property
    def ic95(self) -> Optional[Tuple[float, float]]:
        """Intervalo de Wilson al 95 %."""
        if not self.n:
            return None
        z, p, n = 1.96, self.exitos / self.n, self.n
        centro = (p + z * z / (2 * n)) / (1 + z * z / n)
        medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return max(0.0, centro - medio), min(1.0, centro + medio)

    @property
    def muestra(self) -> str:
        if self.n < MUESTRA_INSUFICIENTE:
            return "insuficiente"
        return "baja" if self.n < MUESTRA_BAJA else "aceptable"


@dataclass(frozen=True)
class Razon:
    """Cociente agresiones / igualaciones (factor de agresión de una calle)."""

    agresiones: int
    igualaciones: int

    @property
    def valor(self) -> Optional[float]:
        return self.agresiones / self.igualaciones if self.igualaciones else None

    @property
    def n(self) -> int:
        return self.agresiones + self.igualaciones

    @property
    def muestra(self) -> str:
        return Frecuencia(0, self.n).muestra


@dataclass(frozen=True)
class Resultado:
    manos: int
    bb100: float
    ic95: Optional[float]  # semiancho del intervalo de confianza en bb/100; None con menos de 2 manos


def clasificar_posicion(asiento: int, boton: int, n: int, sb: int, bb: int) -> str:
    """UTG, MP, CO, BTN, SB o BB. Con 2 jugadores el botón es la ciega chica ('SB')."""
    if asiento == sb:
        return "SB"
    if asiento == bb:
        return "BB"
    if asiento == boton:
        return "BTN"
    o = (asiento - boton) % n
    if o == n - 1:
        return "CO"
    return "UTG" if o == 3 else "MP"


def _bucket_stack(bb_stack: float) -> str:
    if bb_stack < 40:
        return "<40 bb"
    if bb_stack < 80:
        return "40-80 bb"
    if bb_stack < 150:
        return "80-150 bb"
    return ">150 bb"


def _bucket_rivales(mano: ResultadoMano, s: int) -> str:
    if s not in mano.vieron_flop:
        return "no vio el flop"
    rivales = len(mano.vieron_flop) - 1
    return {1: "1 rival", 2: "2 rivales"}.get(rivales, "3+ rivales")


@dataclass
class _Suma:
    n: int = 0
    s: float = 0.0
    ss: float = 0.0

    def agregar(self, x: float) -> None:
        self.n += 1
        self.s += x
        self.ss += x * x

    def resultado(self) -> Resultado:
        if not self.n:
            return Resultado(0, 0.0, None)
        media = self.s / self.n
        if self.n < 2:
            return Resultado(self.n, 100 * media, None)
        var = max(0.0, (self.ss - self.n * media * media) / (self.n - 1))
        return Resultado(self.n, 100 * media, 196 * math.sqrt(var / self.n))  # 1,96 * 100 * desvío / raíz(n)


class _Jugador:
    def __init__(self) -> None:
        self.cont: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
        self.por_stack: Dict[str, _Suma] = defaultdict(_Suma)
        self.por_rivales: Dict[str, _Suma] = defaultdict(_Suma)
        self.total = _Suma()
        self.rake_bb = 0.0


@dataclass
class ReporteJugador:
    nombre: str
    manos: int
    frecuencias: Dict[str, Frecuencia]
    agresion: Dict[str, Razon]
    resultado: Resultado
    por_stack: Dict[str, Resultado]
    por_rivales: Dict[str, Resultado]
    rake_bb: float

    @property
    def rake_bb100(self) -> float:
        return 100 * self.rake_bb / self.manos if self.manos else 0.0

    def filas(self) -> List[dict]:
        """Filas planas (estadística, éxitos, oportunidades, valor, intervalo, alerta) para tablas o CSV."""
        out = []
        for clave, f in sorted(self.frecuencias.items()):
            ic = f.ic95
            out.append({"jugador": self.nombre, "estadistica": clave, "exitos": f.exitos, "n": f.n,
                        "valor": f.valor, "ic_inf": ic[0] if ic else None, "ic_sup": ic[1] if ic else None,
                        "muestra": f.muestra})
        for clave, r in sorted(self.agresion.items()):
            out.append({"jugador": self.nombre, "estadistica": f"af@{clave}", "exitos": r.agresiones,
                        "n": r.igualaciones, "valor": r.valor, "ic_inf": None, "ic_sup": None, "muestra": r.muestra})
        return out


class CalculadorCompleto:
    """Suma manos de a una (streaming) y arma el reporte por jugador."""

    def __init__(self, bb: float) -> None:
        self.bb = bb
        self._jugadores: Dict[str, _Jugador] = {}

    def agregar(self, mano: ResultadoMano, nombres: Sequence[str] = ()) -> None:
        n = len(mano.neto)
        nom = mano.nombres or nombres
        pos = [clasificar_posicion(s, mano.boton, n, mano.sb, mano.bb) for s in range(n)]
        reg: List[Dict[str, List[int]]] = [defaultdict(lambda: [0, 0]) for _ in range(n)]

        def anotar(s: int, clave: str, exito: bool) -> None:
            r = reg[s][clave]
            r[0] += bool(exito)
            r[1] += 1

        ultimo_agresor = self._preflop(mano, n, pos, anotar)
        self._postflop(mano, n, ultimo_agresor, reg, anotar)

        total_pos = sum(x for x in mano.neto if x > 0)
        rake = max(0, -sum(mano.neto))
        for s in range(n):
            j = self._jugadores.setdefault(nom[s], _Jugador())
            for clave, (e, o) in reg[s].items():
                j.cont[clave][0] += e
                j.cont[clave][1] += o
            if s in mano.vieron_flop:
                j.cont["wtsd"][1] += 1
                j.cont["wtsd"][0] += s in mano.llegaron_showdown
            if s in mano.llegaron_showdown:
                j.cont["wsd"][1] += 1
                j.cont["wsd"][0] += s in mano.ganadores_showdown
            neto_bb = mano.neto[s] / self.bb
            j.total.agregar(neto_bb)
            j.por_stack[_bucket_stack(mano.stacks_iniciales[s] / self.bb)].agregar(neto_bb)
            j.por_rivales[_bucket_rivales(mano, s)].agregar(neto_bb)
            if rake and mano.neto[s] > 0 and total_pos:
                j.rake_bb += rake * mano.neto[s] / total_pos / self.bb

    # ---- preflop -------------------------------------------------------------------------------------------
    def _preflop(self, mano, n, pos, anotar) -> Optional[int]:
        subidas = 0
        agresor: Optional[int] = None
        opener: Optional[int] = None
        opener_robo = False
        limp = False
        iguales_tras_subida = 0
        actuo = [False] * n
        voluntaria = [False] * n
        subio = [False] * n
        opor_4bet = [False] * n
        respondio_3bet = False

        for e in mano.eventos:
            if e.jugador is None or e.calle != "preflop" or e.tipo not in ("cbr", "cc", "f"):
                continue
            s = e.jugador - 1
            primera = not actuo[s]
            actuo[s] = True
            if primera:
                if subidas == 0 and not limp and pos[s] in _ROBO:
                    anotar(s, "robo", e.tipo == "cbr")
                if subidas == 1:
                    anotar(s, "3bet", e.tipo == "cbr")
                    if pos[s] == "BB" and opener_robo and iguales_tras_subida == 0:
                        anotar(s, "bb_robo_fold", e.tipo == "f")
                        anotar(s, "bb_robo_call", e.tipo == "cc")
                        anotar(s, "bb_robo_3bet", e.tipo == "cbr")
            if subidas == 2 and not opor_4bet[s]:
                opor_4bet[s] = True
                anotar(s, "4bet", e.tipo == "cbr")
            if subidas == 2 and s == opener and not respondio_3bet:
                respondio_3bet = True
                anotar(s, "fold_3bet", e.tipo == "f")
            if e.tipo == "cbr":
                voluntaria[s] = subio[s] = True
                subidas += 1
                if subidas == 1:
                    opener = s
                    opener_robo = pos[s] in _ROBO and not limp
                agresor = s
                iguales_tras_subida = 0
            elif e.tipo == "cc" and e.monto is not None:
                voluntaria[s] = True
                if subidas == 0:
                    limp = True
                else:
                    iguales_tras_subida += 1

        for s in range(n):
            anotar(s, "vpip", voluntaria[s])
            anotar(s, "pfr", subio[s])
            anotar(s, f"vpip@{pos[s]}", voluntaria[s])
            anotar(s, f"pfr@{pos[s]}", subio[s])
        return agresor

    # ---- postflop ------------------------------------------------------------------------------------------
    def _postflop(self, mano, n, agresor, reg, anotar) -> None:
        iniciativa = agresor
        for calle in CALLES:
            eventos = [e for e in mano.eventos if e.calle == calle and e.jugador is not None and e.tipo in ("cbr", "cc", "f")]
            if not eventos:
                break
            nombre_cbet = {"flop": "cbet_flop", "turn": "barril_turn", "river": "barril_river"}[calle]
            nombre_fold = {"flop": "fold_cbet_flop", "turn": "fold_barril_turn", "river": "fold_barril_river"}[calle]
            apuestas = 0
            inic_actuo = False
            inic_aposto = False
            ventana = False
            en_ventana = [False] * n
            paso = [False] * n
            opor_cr = [False] * n
            opor_farol = [False] * n
            for e in eventos:
                s = e.jugador - 1
                if apuestas == 0:
                    if iniciativa is not None and s == iniciativa and not inic_actuo:
                        anotar(s, nombre_cbet, e.tipo == "cbr")
                        if e.tipo == "cbr":
                            inic_aposto = True
                            ventana = True
                    elif calle == "flop" and iniciativa is not None and s != iniciativa and not inic_actuo:
                        anotar(s, "donk_flop", e.tipo == "cbr")
                elif ventana and s != iniciativa and not en_ventana[s]:
                    en_ventana[s] = True
                    anotar(s, nombre_fold, e.tipo == "f")
                if paso[s] and apuestas >= 1 and not opor_cr[s]:
                    opor_cr[s] = True
                    anotar(s, f"checkraise_{calle}", e.tipo == "cbr")
                if e.tipo == "cc" and e.monto is None:
                    paso[s] = True
                if e.tipo == "cbr":
                    if apuestas >= 1 and ventana:
                        ventana = False  # alguien subió la apuesta de continuación
                    apuestas += 1
                    reg[s][f"agr@{calle}"][0] += 1
                    if calle == "river" and not opor_farol[s] and s in mano.llegaron_showdown:
                        opor_farol[s] = True
                        anotar(s, "farol_river_visible", s not in mano.ganadores_showdown)
                elif e.tipo == "cc" and e.monto is not None:
                    reg[s][f"agr@{calle}"][1] += 1
                if s == iniciativa:
                    inic_actuo = True
            iniciativa = iniciativa if inic_aposto else None

    # ---- reporte -------------------------------------------------------------------------------------------
    def reporte(self) -> Dict[str, ReporteJugador]:
        out = {}
        for nombre, j in self._jugadores.items():
            frec, agr = {}, {}
            for clave, (e, o) in j.cont.items():
                if clave.startswith("agr@"):
                    agr[clave[4:]] = Razon(e, o)
                else:
                    frec[clave] = Frecuencia(e, o)
            out[nombre] = ReporteJugador(
                nombre=nombre, manos=j.total.n, frecuencias=frec, agresion=agr, resultado=j.total.resultado(),
                por_stack={k: v.resultado() for k, v in j.por_stack.items()},
                por_rivales={k: v.resultado() for k, v in j.por_rivales.items()}, rake_bb=j.rake_bb,
            )
        return out


def calcular_completo(manos: Iterable[ResultadoMano], bb: float, nombres: Sequence[str] = ()) -> Dict[str, ReporteJugador]:
    calc = CalculadorCompleto(bb)
    for m in manos:
        calc.agregar(m, nombres)
    return calc.reporte()
