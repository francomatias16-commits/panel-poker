"""Panel web local de estudio de manos: filtros, estadísticas, repaso acción por acción con la guía,
análisis de una situación escrita a mano y video sincronizado con el historial.

Uso:
    python3 app/web.py                     # abre http://127.0.0.1:8799
    python3 app/web.py --demo              # arranca con manos simuladas por los bots del proyecto
    python3 app/web.py --carpeta RUTA --formato phh

Solo escucha en 127.0.0.1 y valida el encabezado Host y el tipo de contenido de los POST, para que
otra página abierta en el navegador no pueda manejarlo. El video no sale de tu navegador: se reproduce
desde el archivo local y las marcas se guardan en el propio navegador.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import dataclasses
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis import bots, guia, simulacion  # noqa: E402
from poker_analisis.cartas import parsear_cartas  # noqa: E402
from poker_analisis.estadisticas import CalculadorEstadisticas  # noqa: E402
from poker_analisis import bloques as _bloques  # noqa: E402
from poker_analisis import bankroll as _bankroll  # noqa: E402
from poker_analisis import perfiles as _perfiles  # noqa: E402
from poker_analisis import practica as _practica  # noqa: E402
from poker_analisis.estadisticas_completas import CalculadorCompleto  # noqa: E402
from poker_analisis.ggpoker import iterar_directorio as iterar_texto  # noqa: E402
from poker_analisis.motor import ResultadoMano  # noqa: E402
from poker_analisis.real import iterar_directorio as iterar_phh  # noqa: E402
from poker_analisis.riesgo import max_drawdown, prob_ruina_analitica, resumen  # noqa: E402

ESTATICOS = os.path.join(os.path.dirname(__file__), "static")
TIPOS = {"index.html": "text/html; charset=utf-8", "estilo.css": "text/css; charset=utf-8",
         "app.js": "text/javascript; charset=utf-8"}
MAX_CUERPO = 1_000_000
MAX_PUNTOS = 1200


def _limpiar(x):
    """JSON no admite inf ni NaN: se convierten en null (los stacks infinitos de HandHQ, por ejemplo)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _limpiar(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpiar(v) for v in x]
    return x


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _fecha(txt: Optional[str], fin: bool = False) -> Optional[datetime]:
    if not txt:
        return None
    d = datetime.fromisoformat(txt)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    if fin and len(txt) <= 10:
        d += timedelta(days=1) - timedelta(microseconds=1)
    return d


def _completo(completos: dict, nombre: str) -> Optional[dict]:
    """Estadísticas completas del jugador (un solo stake): cada una con éxitos, oportunidades, intervalo y alerta."""
    rep = next(iter(completos.values())).reporte().get(nombre)
    if rep is None:
        return None
    perfil = _perfiles.perfil_de(rep)
    return {
        "perfil": dataclasses.asdict(perfil) | {"af_estimado": perfil.af_estimado, "texto": _perfiles.formatear(perfil)},
        "frecuencias": rep.filas(),
        "resultado": {"manos": rep.resultado.manos, "bb100": rep.resultado.bb100, "ic95": rep.resultado.ic95},
        "por_stack": [{"clave": k, "manos": v.manos, "bb100": v.bb100, "ic95": v.ic95} for k, v in sorted(rep.por_stack.items())],
        "por_rivales": [{"clave": k, "manos": v.manos, "bb100": v.bb100, "ic95": v.ic95} for k, v in sorted(rep.por_rivales.items())],
        "rake_bb100": rep.rake_bb100,
    }


class Almacen:
    """Manos cargadas y consultas sobre ellas. Las manos no cambian tras la carga: se cachea con tranquilidad."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.manos: List[ResultadoMano] = []
        self.rechazos: List = []
        self.ruta = ""
        self.formato = ""
        self.cargando = False
        self.error: Optional[str] = None
        self._cache: Dict = {}
        self._repasos: "OrderedDict" = OrderedDict()
        self._bloques: Dict = {}  # (jugador, stake) -> estado del informe por bloques
        self._generacion = 0  # cambia con cada carga: un informe viejo no pisa a uno nuevo

    # --- carga -----------------------------------------------------------
    def _fijar(self, manos, rechazos, ruta, formato) -> None:
        with self.lock:
            self.manos, self.rechazos, self.ruta, self.formato = manos, rechazos, ruta, formato
            self._cache.clear()
            self._repasos.clear()
            self._bloques.clear()
            self._generacion += 1
        # El informe por bloques del jugador principal se genera solo al cargar las manos.
        principal = _bloques.detectar_jugador_principal(manos)
        if principal:
            self.bloques(principal[0], principal[1])

    def demo(self, cantidad: int = 600, semilla: int = 7) -> None:
        """Manos simuladas por los bots del proyecto: sirven para probar el panel y para practicar."""
        tabla = bots.cargar_tabla_preflop(os.path.join(os.path.dirname(__file__), "..", "resultados", "preflop_equity.csv"))
        inicio = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
        manos = simulacion.simular_mesa(tabla, max(10, min(cantidad, 5000)), semilla)
        for k, m in enumerate(manos):
            m.nombres = list(simulacion.PERFILES)
            m.ciega_chica, m.ciega_grande = simulacion.BLIND_CHICO, simulacion.BLIND_GRANDE
            m.fecha = inicio + timedelta(seconds=45 * k)
            m.archivo = "simulacion"
        self._fijar(manos, [], f"demo ({len(manos)} manos)", "demo")

    def cargar(self, ruta: str, formato: str) -> None:
        if formato == "demo":
            self.demo(int(ruta) if ruta.isdigit() else 600)
            return
        if not os.path.isdir(ruta):
            raise ValueError("la carpeta no existe")
        rechazos: List = []
        if formato == "phh":
            manos = list(iterar_phh(ruta, rechazos))
        elif formato in ("texto", "ggpoker", "pokerstars"):
            manos = list(iterar_texto(ruta, rechazos))
        else:
            raise ValueError("formato desconocido (phh, texto o demo)")
        if not manos:
            raise ValueError(f"no se encontró ninguna mano válida ({len(rechazos)} archivos rechazados)")
        for m in manos:
            if m.ciega_grande is None:
                raise ValueError("las manos no traen el big blind")
        self._fijar(manos, rechazos, os.path.abspath(ruta), formato)

    def cargar_en_segundo_plano(self, ruta: str, formato: str) -> None:
        def tarea():
            try:
                self.cargar(ruta, formato)
                self.error = None
            except Exception as e:  # noqa: BLE001 - se informa a la interfaz
                self.error = str(e)
            finally:
                self.cargando = False
        self.cargando = True
        self.error = None
        threading.Thread(target=tarea, daemon=True).start()

    # --- informe por bloques ---------------------------------------------
    def bloques(self, jugador: str, stake: Optional[int] = None) -> dict:
        """Estado del informe por bloques de 1000 manos. Se calcula en segundo plano y se guarda."""
        with self.lock:
            manos, gen = self.manos, self._generacion
            if stake is None:
                stakes = {m.ciega_grande for m in manos if m.nombres and jugador in m.nombres}
                if not stakes:
                    raise ValueError("no hay manos de ese jugador")
                if len(stakes) != 1:
                    raise ValueError("el jugador tiene manos en varios stakes: elegí uno")
                stake = next(iter(stakes))
            clave = (jugador, stake)
            if clave not in self._bloques:
                self._bloques[clave] = {"estado": "calculando", "hechos": 0, "total": 0, "jugador": jugador, "stake": stake}
                threading.Thread(target=self._calcular_bloques, args=(manos, gen, jugador, stake), daemon=True).start()
            return self._bloques_json(self._bloques[clave])

    def _bloques_json(self, est: dict) -> dict:
        out = {k: v for k, v in est.items() if k != "informes"}
        if est.get("informes") is not None:
            inf = est["informes"]
            out["informes"] = [dataclasses.asdict(i) | {"pct_proceso": i.pct_proceso} for i in inf]
            out["evolucion"] = _bloques.evolucion(inf)
            out["texto"] = _bloques.formatear(inf, est["jugador"])
        return _limpiar(out)

    def _calcular_bloques(self, manos, gen: int, jugador: str, stake: int) -> None:
        clave = (jugador, stake)

        def avance(hechos: int, total: int) -> None:
            with self.lock:
                if gen == self._generacion and clave in self._bloques:
                    self._bloques[clave].update(hechos=hechos, total=total)

        try:
            informes = _bloques.informes_por_bloque(manos, jugador, stake, progreso=avance)
            resultado = {"estado": "listo", "informes": informes, "jugador": jugador, "stake": stake,
                         "hechos": len(informes), "total": len(informes)}
        except Exception as e:  # noqa: BLE001 - se informa a la interfaz
            resultado = {"estado": "error", "error": str(e), "jugador": jugador, "stake": stake, "hechos": 0, "total": 0}
        with self.lock:
            if gen == self._generacion:
                self._bloques[clave] = resultado

    # --- riesgo y bankroll -----------------------------------------------
    def riesgo(self, f: dict) -> dict:
        """Riesgo de ruina, drawdown, Kelly y regla de cambio de stake de un jugador, con el winrate incierto propagado."""
        jugador = f.get("jugador")
        if not jugador:
            raise ValueError("elegí un jugador")
        entradas = float(f.get("bankroll_entradas") or 0)
        if not 0 < entradas <= 100_000:
            raise ValueError("el bankroll debe ser un número de entradas mayor que 0")
        horizonte = int(f.get("horizonte") or 100_000)
        if not 1_000 <= horizonte <= 1_000_000:
            raise ValueError("el horizonte debe estar entre 1.000 y 1.000.000 de manos")
        factor = float(f.get("factor_stake_superior") or 2.0)
        if not 0 < factor <= 100:
            raise ValueError("el factor del stake superior debe ser mayor que 0")
        with self.lock:
            manos = self.manos
        stake = f.get("stake")
        stakes = {m.ciega_grande for m in manos if m.nombres and jugador in m.nombres}
        if not stakes:
            raise ValueError("no hay manos de ese jugador")
        if stake is None:
            if len(stakes) != 1:
                raise ValueError("el jugador tiene manos en varios stakes: elegí uno")
            stake = next(iter(stakes))
        netos = [m.neto[a] / m.ciega_grande for m, a in _bloques.serie_del_jugador(manos, jugador, int(stake))]
        bank = entradas * _bankroll.BUYIN_BB
        mu = _bankroll.muestra(netos)  # ValueError con menos de 30 manos
        r = _bankroll.ruina(netos, bank)
        req = _bankroll.bankroll_requerido(netos)
        sim = _bankroll.simular(netos, horizonte, 1000, bank)
        sin = _bankroll.simular(netos, horizonte, 1000, bank, incertidumbre=False)
        dec = _bankroll.decidir_stake(netos, bank, factor)
        return _limpiar({
            "jugador": jugador, "stake": int(stake), "manos": mu.n, "bankroll_entradas": entradas, "horizonte": horizonte,
            "winrate_bb100": mu.winrate_bb100, "ic95_bb100": list(mu.ic95_bb100), "desvio_bb100": mu.desvio_bb100,
            "prob_winrate_positivo": mu.prob_winrate_positivo,
            "ruina": dataclasses.asdict(r), "requerido_entradas": None if req is None else req / _bankroll.BUYIN_BB,
            "simulacion": dataclasses.asdict(sim), "simulacion_sin_incertidumbre": dataclasses.asdict(sin),
            "kelly": dataclasses.asdict(_bankroll.kelly(netos)), "decision": dataclasses.asdict(dec),
            "texto": _bankroll.formatear(netos, bank, horizonte, 1000, factor_stake_superior=factor, sim=sim, sim_fija=sin),
        })

    # --- alinear el video con las horas del historial --------------------------
    def alinear(self, f: dict) -> dict:
        """Marcas automáticas (una por mano, en su primer paso) a partir de la hora de cada mano.

        La hora de inicio del video se da directamente (`inicio`, la misma hora que muestra el historial) o se deduce de
        una mano ya marcada a mano (`ancla`: {mano, t} con t en segundos del video).
        """
        jugador = f.get("jugador")
        if not jugador:
            raise ValueError("elegí un jugador")
        with self.lock:
            manos = self.manos
        stake = f.get("stake")
        filas = [(i, m) for i, m in enumerate(manos)
                 if m.nombres and jugador in m.nombres and (stake is None or m.ciega_grande == stake)]
        if not filas:
            raise ValueError("no hay manos de ese jugador")
        con_fecha = [(i, m) for i, m in filas if m.fecha is not None]
        if not con_fecha:
            raise ValueError("las manos de este jugador no traen fecha y hora: no se puede alinear por hora")
        ancla = f.get("ancla")
        if ancla:
            ident, t = int(ancla["mano"]), float(ancla["t"])
            if not 0 <= ident < len(manos) or manos[ident].fecha is None:
                raise ValueError("la mano de referencia no tiene fecha y hora")
            if t < 0:
                raise ValueError("el tiempo de la marca no puede ser negativo")
            inicio = manos[ident].fecha - timedelta(seconds=t)
        elif f.get("inicio"):
            inicio = _fecha(str(f["inicio"]))
        else:
            raise ValueError("indicá la hora de inicio del video o una mano de referencia")
        duracion = float(f["duracion"]) if f.get("duracion") is not None else None
        if duracion is not None and duracion <= 0:
            raise ValueError("la duración del video debe ser mayor que 0")
        marcas, fuera = [], 0
        for i, m in con_fecha:
            t = (m.fecha - inicio).total_seconds()
            if t < 0 or (duracion is not None and t > duracion):
                fuera += 1
                continue
            marcas.append({"mano": i, "paso": 0, "t": round(t, 2)})
        marcas.sort(key=lambda x: x["t"])
        return {"marcas": marcas, "fuera_del_video": fuera, "sin_fecha": len(filas) - len(con_fecha),
                "inicio": _iso(inicio)}

    # --- consultas -------------------------------------------------------
    def estado(self) -> dict:
        with self.lock:
            manos = self.manos
            conteo: Dict[str, int] = {}
            stakes = set()
            for m in manos:
                stakes.add(m.ciega_grande)
                for nombre in m.nombres or ():
                    conteo[nombre] = conteo.get(nombre, 0) + 1
            fechas = [m.fecha for m in manos if m.fecha]
            return _limpiar({
                "cargando": self.cargando, "error": self.error, "manos": len(manos), "rechazos": len(self.rechazos),
                "ruta": self.ruta, "formato": self.formato, "stakes": sorted(stakes),
                "jugadores": [{"nombre": n, "manos": c} for n, c in sorted(conteo.items(), key=lambda t: -t[1])],
                "fecha_min": _iso(min(fechas)) if fechas else None, "fecha_max": _iso(max(fechas)) if fechas else None,
                "con_fecha": bool(manos) and len(fechas) == len(manos),
                "jugador_principal": (lambda p: p[0] if p else None)(_bloques.detectar_jugador_principal(manos)),
                "posiciones": list(dict.fromkeys(p for n in sorted({len(m.stacks_iniciales) for m in manos}) for p in guia.posiciones_mesa(n))),
            })

    def _filtrar(self, f: dict, jugador: Optional[str] = None, posiciones=()) -> List[tuple]:
        """Manos (id, mano, asiento) que cumplen los filtros. Con `jugador`, solo las que jugó él."""
        stake = f.get("stake")
        desde, hasta = _fecha(f.get("desde")), _fecha(f.get("hasta"), fin=True)
        salida = []
        for i, m in enumerate(self.manos):
            if stake is not None and m.ciega_grande != stake:
                continue
            if (desde or hasta) and m.fecha is None:
                continue
            if desde and m.fecha < desde or hasta and m.fecha > hasta:
                continue
            asiento = None
            if jugador is not None:
                if not m.nombres or jugador not in m.nombres:
                    continue
                asiento = m.nombres.index(jugador)
                if posiciones and guia.posicion(m, asiento) not in posiciones:
                    continue
            salida.append((i, m, asiento))
        return salida

    def panel(self, f: dict) -> dict:
        clave = ("panel", f.get("stake"), f.get("desde"), f.get("hasta"))
        with self.lock:
            if clave in self._cache:
                base = self._cache[clave]
            else:
                base = None
        if base is None:
            calculadores: Dict[int, CalculadorEstadisticas] = {}
            for _, m, _a in self._filtrar(f):
                calculadores.setdefault(m.ciega_grande, CalculadorEstadisticas(m.ciega_grande)).agregar(m)
            filas = []
            for stake, calc in sorted(calculadores.items()):
                for s in calc.resultados():
                    serie = list(calc.series[s.nombre])
                    dd = max_drawdown(serie) if serie else None
                    desvio = ruina = None
                    if len(serie) >= 2:
                        r = resumen(serie)
                        desvio = r["desvio_bb100"]
                        ruina = prob_ruina_analitica(r["winrate_bb100"], desvio, 100 * 100)
                    filas.append({
                        "jugador": s.nombre, "stake": stake, "manos": s.manos, "vpip": s.vpip, "pfr": s.pfr,
                        "tres_bet": s.tres_bet, "af": s.af, "wtsd": s.wtsd, "wsd": s.wsd, "cbet": s.cbet,
                        "fold_cbet": s.fold_cbet, "bb100": s.bb100, "ic95": s.bb100_ic95, "desvio": desvio,
                        "drawdown": dd, "ruina": ruina,
                    })
            base = {"filas": filas}
            with self.lock:
                self._cache[clave] = base
        minimo = int(f.get("min_manos") or 0)
        filas = [r for r in base["filas"] if r["manos"] >= minimo]
        metrica = f.get("metrica") or "manos"
        if metrica in ("vpip", "pfr", "tres_bet", "af", "wtsd", "wsd", "cbet", "fold_cbet", "bb100", "manos", "drawdown"):
            filas.sort(key=lambda r: (r[metrica] is None, -(r[metrica] or 0)))
        return _limpiar({"filas": filas})

    def jugador(self, f: dict) -> dict:
        """Detalle de un jugador con los filtros (incluida la posición): curva, estadísticas y desglose por posición."""
        nombre = f.get("jugador")
        if not nombre:
            raise ValueError("elegí un jugador")
        posiciones = set(f.get("posiciones") or ())
        sel = self._filtrar(f, nombre, posiciones)
        if not sel:
            return {"manos": 0}
        por_stake: Dict[int, CalculadorEstadisticas] = {}
        por_pos: Dict[str, CalculadorEstadisticas] = {}
        completos: Dict[int, CalculadorCompleto] = {}
        netos: List[float] = []
        for _, m, a in sel:
            bb = m.ciega_grande
            completos.setdefault(bb, CalculadorCompleto(bb)).agregar(m)
            por_stake.setdefault(bb, CalculadorEstadisticas(bb)).agregar(m)
            pos = guia.posicion(m, a)
            por_pos.setdefault(pos, CalculadorEstadisticas(bb)).agregar(m)
            netos.append(m.neto[a] / bb)

        def fila(calc: CalculadorEstadisticas) -> Optional[dict]:
            for s in calc.resultados():
                if s.nombre == nombre:
                    return {"manos": s.manos, "vpip": s.vpip, "pfr": s.pfr, "tres_bet": s.tres_bet, "af": s.af,
                            "wtsd": s.wtsd, "wsd": s.wsd, "cbet": s.cbet, "fold_cbet": s.fold_cbet,
                            "bb100": s.bb100, "ic95": s.bb100_ic95}
            return None

        # La curva mezcla stakes solo en bb: es comparable porque cada mano se pasa a big blinds.
        acum, pico, dd = [], 0.0, []
        total = 0.0
        for x in netos:
            total += x
            pico = max(pico, total)
            acum.append(total)
            dd.append(pico - total)
        paso = max(1, math.ceil(len(netos) / MAX_PUNTOS))
        idx = list(range(0, len(netos), paso))
        if idx[-1] != len(netos) - 1:
            idx.append(len(netos) - 1)
        orden = ["UTG", "UTG+1", "UTG+2", "MP", "HJ", "CO", "BTN", "BTN/SB", "SB", "BB"]
        posiciones_out = []
        for pos in sorted(por_pos, key=lambda p: orden.index(p) if p in orden else 99):
            fp = fila(por_pos[pos])
            if fp:
                fp["posicion"] = pos
                posiciones_out.append(fp)
        r = resumen(netos) if len(netos) >= 2 else None
        return _limpiar({
            "manos": len(netos), "total_bb": total, "drawdown_bb": max(dd) if dd else 0.0,
            "desvio_bb100": r["desvio_bb100"] if r else None,
            "stats": fila(por_stake[next(iter(por_stake))]) if len(por_stake) == 1 else None,
            "multi_stake": len(por_stake) > 1,
            "completo": _completo(completos, nombre) if len(completos) == 1 else None,
            "curva": {"n": [i + 1 for i in idx], "ids": [sel[i][0] for i in idx], "acum": [round(acum[i], 2) for i in idx], "dd": [round(dd[i], 2) for i in idx]},
            "posiciones": posiciones_out,
        })

    def lista(self, f: dict) -> dict:
        nombre = f.get("jugador")
        if not nombre:
            raise ValueError("elegí un jugador")
        sel = self._filtrar(f, nombre, set(f.get("posiciones") or ()))
        filas = []
        solo_sd = bool(f.get("solo_showdown"))
        for i, m, a in sel:
            sd = a in m.llegaron_showdown
            if solo_sd and not sd:
                continue
            bb = m.ciega_grande
            filas.append({
                "id": i, "n": i + 1, "fecha": _iso(m.fecha), "stake": bb, "posicion": guia.posicion(m, a),
                "neto_bb": round(m.neto[a] / bb, 2), "cartas": [str(c) for c in m.cartas[a]] if m.cartas[a] else [],
                "showdown": sd, "vio_flop": a in m.vieron_flop, "tablero": [str(c) for c in m.tablero],
            })
        orden = f.get("orden") or "cronologico"
        if orden == "ganancia":
            filas.sort(key=lambda r: -r["neto_bb"])
        elif orden == "perdida":
            filas.sort(key=lambda r: r["neto_bb"])
        total = len(filas)
        desde = max(0, int(f.get("offset") or 0))
        limite = max(1, min(int(f.get("limite") or 100), 500))
        return {"total": total, "filas": filas[desde:desde + limite]}

    def repaso(self, ident: int, jugador: Optional[str]) -> dict:
        if not 0 <= ident < len(self.manos):
            raise KeyError("mano inexistente")
        m = self.manos[ident]
        asiento = None
        if jugador and m.nombres and jugador in m.nombres:
            asiento = m.nombres.index(jugador)
        if asiento is None:
            asiento = next((s for s in range(len(m.cartas)) if m.cartas[s]), 0)
        clave = (ident, asiento)
        with self.lock:
            if clave in self._repasos:
                self._repasos.move_to_end(clave)
                return self._repasos[clave]
        r = _limpiar(guia.reproducir(m, asiento))
        r["id"] = ident
        r["n"] = ident + 1
        r["fecha"] = _iso(m.fecha)
        with self.lock:
            self._repasos[clave] = r
            while len(self._repasos) > 200:
                self._repasos.popitem(last=False)
        return r


ALMACEN = Almacen()
_SESION: Optional[_practica.Sesion] = None
_LOCK_SESION = threading.Lock()


def practica(d: dict) -> dict:
    """Modo práctica contra bots. Acciones: nueva, estado, actuar (f, cc, cbr), siguiente, guia."""
    global _SESION
    accion = str(d.get("accion") or "estado")
    with _LOCK_SESION:
        if _SESION is None and accion not in ("nueva", "estado"):
            raise ValueError("no hay una sesión de práctica: empezá una")
        if accion == "nueva" or _SESION is None:
            semilla = d.get("semilla")
            _SESION = _practica.Sesion(semilla=int(semilla) if semilla not in (None, "") else None,
                                       guia_activa=bool(d.get("guia", True)))
            if accion in ("nueva", "estado"):
                return _limpiar(_SESION.estado())
        ses = _SESION
    if accion == "estado":
        return _limpiar(ses.estado())
    if accion == "actuar":
        tipo = str(d.get("tipo") or "")
        hasta = d.get("hasta")
        return _limpiar(ses.actuar(tipo, int(hasta) if hasta is not None else None))
    if accion == "siguiente":
        return _limpiar(ses.siguiente())
    if accion == "guia":
        return _limpiar(ses.configurar(bool(d.get("activa"))))
    raise ValueError("acción desconocida")


def analizar_situacion(d: dict) -> dict:
    cartas = parsear_cartas(str(d.get("cartas", "")))
    tablero = parsear_cartas(str(d.get("tablero", "")))
    if len(cartas) != 2:
        raise ValueError("tu mano tiene que tener 2 cartas, por ejemplo: As Kd")
    if len(tablero) not in (0, 3, 4, 5):
        raise ValueError("el tablero tiene 0, 3, 4 o 5 cartas")
    bb = float(d.get("bb") or 2)
    bote, a_pagar = float(d.get("bote") or 0), float(d.get("a_pagar") or 0)
    if min(bb, bote, a_pagar) < 0 or bb == 0:
        raise ValueError("los montos no pueden ser negativos y el big blind no puede ser 0")
    rivales = d.get("rivales") or []
    if not 1 <= len(rivales) <= 5:
        raise ValueError("entre 1 y 5 rivales")
    clean = []
    for r in rivales:
        if r.get("claves"):
            clean.append({"claves": [str(c) for c in r["claves"]][:169]})
        else:
            top = float(r.get("top") or 100)
            if not 0 < top <= 100:
                raise ValueError("el rango va de 1 a 100 %")
            clean.append({"top": top})
    r = guia.analisis_puntual(
        cartas, tablero, bote, a_pagar, bb, clean, pos=str(d.get("posicion") or "BTN"),
        subidas_preflop=int(d.get("subidas") or 0), limpers=int(d.get("limpers") or 0),
        iteraciones=max(200, min(int(d.get("iteraciones") or 1500), 6000)),
    )
    return _limpiar(r)


class Manejador(BaseHTTPRequestHandler):
    server_version = "PanelPoker/1.0"

    def log_message(self, fmt, *args):  # silencioso: no ensucia la consola
        pass

    # --- seguridad -------------------------------------------------------
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        puerto = self.server.server_address[1]
        return host in (f"127.0.0.1:{puerto}", f"localhost:{puerto}")

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; media-src 'self' blob:; img-src 'self' data:; style-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, datos, codigo: int = 200) -> None:
        self._responder(codigo, json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, codigo: int, texto: str) -> None:
        self._json({"error": texto}, codigo)

    # --- rutas -----------------------------------------------------------
    def do_GET(self) -> None:
        if not self._host_ok():
            return self._error(403, "host no permitido")
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                return self._estatico("index.html")
            if url.path.startswith("/static/"):
                return self._estatico(url.path[len("/static/"):])
            if url.path == "/api/estado":
                return self._json(ALMACEN.estado())
            if url.path == "/api/mano":
                q = parse_qs(url.query)
                ident = int(q.get("id", [""])[0])
                jugador = q.get("jugador", [None])[0]
                return self._json(ALMACEN.repaso(ident, jugador))
        except KeyError as e:
            return self._error(404, str(e).strip("'\""))
        except (ValueError, TypeError) as e:
            return self._error(400, str(e))
        self._error(404, "no encontrado")

    def do_POST(self) -> None:
        if not self._host_ok():
            return self._error(403, "host no permitido")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self._error(415, "se espera JSON")
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "Content-Length inválido")
        if largo > MAX_CUERPO:
            return self._error(413, "cuerpo demasiado grande")
        try:
            d = json.loads(self.rfile.read(largo) or b"{}")
            if not isinstance(d, dict):
                raise ValueError("se espera un objeto JSON")
            ruta = urlparse(self.path).path
            if ruta == "/api/cargar":
                if ALMACEN.cargando:
                    return self._error(409, "ya hay una carga en curso")
                ALMACEN.cargar_en_segundo_plano(str(d.get("ruta", "")), str(d.get("formato", "phh")))
                return self._json({"ok": True})
            if ruta == "/api/panel":
                return self._json(ALMACEN.panel(d))
            if ruta == "/api/jugador":
                return self._json(ALMACEN.jugador(d))
            if ruta == "/api/bloques":
                return self._json(ALMACEN.bloques(str(d.get("jugador") or ""), int(d["stake"]) if d.get("stake") else None))
            if ruta == "/api/riesgo":
                return self._json(ALMACEN.riesgo(d))
            if ruta == "/api/alinear":
                return self._json(ALMACEN.alinear(d))
            if ruta == "/api/practica":
                return self._json(practica(d))
            if ruta == "/api/manos":
                return self._json(ALMACEN.lista(d))
            if ruta == "/api/analisis":
                return self._json(analizar_situacion(d))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            return self._error(400, str(e).strip("'\""))
        self._error(404, "no encontrado")

    def _estatico(self, nombre: str) -> None:
        if nombre not in TIPOS:
            return self._error(404, "no encontrado")
        with open(os.path.join(ESTATICOS, nombre), "rb") as f:
            self._responder(200, f.read(), TIPOS[nombre])


def main() -> None:
    ap = argparse.ArgumentParser(description="Panel web local de estudio de manos")
    ap.add_argument("--puerto", type=int, default=8799)
    ap.add_argument("--demo", action="store_true", help="arrancar con manos simuladas")
    ap.add_argument("--manos", type=int, default=600, help="cantidad de manos de la demo")
    ap.add_argument("--carpeta")
    ap.add_argument("--formato", default="phh")
    ap.add_argument("--no-abrir", action="store_true")
    a = ap.parse_args()
    if a.demo:
        ALMACEN.demo(a.manos)
        print(f"Cargadas {len(ALMACEN.manos)} manos simuladas.")
    elif a.carpeta:
        ALMACEN.cargar(a.carpeta, a.formato)
        print(f"Cargadas {len(ALMACEN.manos)} manos ({len(ALMACEN.rechazos)} rechazadas).")
    srv = ThreadingHTTPServer(("127.0.0.1", a.puerto), Manejador)
    url = f"http://127.0.0.1:{a.puerto}"
    print(f"Panel en {url}  (Ctrl+C para cerrar)")
    if not a.no_abrir:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
