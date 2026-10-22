"""Carga de manos a la base (schema `poker`, ver db/schema.sql).

Hay dos caminos con el mismo resultado e idempotencia:
- `cargar`: una sentencia por tipo y `executemany` por lote. Simple, pero una sentencia por fila.
- `cargar_copy`: COPY de cada lote a tablas temporales y luego inserciones por conjuntos.
  Es el recomendado para volúmenes grandes (ver CHANGELOG, v2.0, para las mediciones).

Todas las sentencias son idempotentes (clave: fuente + referencia de mano, o mano + asiento/orden),
así que repetir una carga no duplica nada. No hacen commit: lo decide quien llama.
Acepta cualquier iterable de manos (un generador no se guarda entero: solo un lote en memoria).
"""

from __future__ import annotations

import math
from datetime import datetime
from itertools import islice
from typing import Dict, Iterable, Iterator, List, Sequence

from .almacen import filas_de_mano
from .motor import ResultadoMano

SQL = {
    "fuente": (
        "insert into poker.fuentes (nombre, licencia, formato) values (%s, %s, %s) "
        "on conflict (nombre) do nothing"
    ),
    "jugador": (
        "insert into poker.jugadores (fuente_id, seudonimo) "
        "select id, %s from poker.fuentes where nombre = %s "
        "on conflict (fuente_id, seudonimo) do nothing"
    ),
    "mano": (
        "insert into poker.manos (fuente_id, mano_ref, archivo, jugada_en, n_jugadores, blind_chico, "
        "blind_grande, boton, tablero) "
        "select id, %s, %s, %s, %s, %s, %s, %s, %s from poker.fuentes where nombre = %s "
        "on conflict (fuente_id, mano_ref) do nothing"
    ),
    "asiento": (
        "insert into poker.asientos (mano_id, asiento, jugador_id, stack_inicial, neto, cartas, "
        "vio_flop, llego_showdown, gano_showdown) "
        "select m.id, %s, j.id, %s, %s, %s, %s, %s, %s "
        "from poker.manos m join poker.fuentes f on f.id = m.fuente_id "
        "left join poker.jugadores j on j.fuente_id = f.id and j.seudonimo = %s "
        "where f.nombre = %s and m.mano_ref = %s "
        "on conflict (mano_id, asiento) do nothing"
    ),
    "accion": (
        "insert into poker.acciones (mano_id, orden, calle, asiento, tipo, monto) "
        "select m.id, %s, %s, %s, %s, %s "
        "from poker.manos m join poker.fuentes f on f.id = m.fuente_id "
        "where f.nombre = %s and m.mano_ref = %s "
        "on conflict (mano_id, orden) do nothing"
    ),
}
ORDEN = ["jugador", "mano", "asiento", "accion"]  # respeta las claves foráneas


def parametros(res: ResultadoMano, fuente: str, sal: str) -> Dict[str, List[tuple]]:
    """Parámetros de cada sentencia para una mano."""
    if res.referencia is None or res.ciega_chica is None or res.ciega_grande is None:
        raise ValueError("la mano no trae referencia o ciegas: no se puede cargar")
    f = filas_de_mano(res, res.referencia, sal, res.ciega_chica, res.ciega_grande, res.archivo)
    m = f["mano"]
    ref = m["mano_ref"]
    salida: Dict[str, List[tuple]] = {k: [] for k in ORDEN}
    vistos = set()
    for a in f["asientos"]:
        if a["seudonimo"] is not None and a["seudonimo"] not in vistos:
            vistos.add(a["seudonimo"])
            salida["jugador"].append((a["seudonimo"], fuente))
    salida["mano"].append((ref, m["archivo"], m["jugada_en"], m["n_jugadores"], m["blind_chico"],
                           m["blind_grande"], m["boton"], m["tablero"], fuente))
    for a in f["asientos"]:
        salida["asiento"].append((a["asiento"], a["stack_inicial"], a["neto"], a["cartas"],
                                  a["vio_flop"], a["llego_showdown"], a["gano_showdown"],
                                  a["seudonimo"], fuente, ref))
    for x in f["acciones"]:
        salida["accion"].append((x["orden"], x["calle"], x["asiento"], x["tipo"], x["monto"], fuente, ref))
    return salida


def lote(manos: Iterable[ResultadoMano], fuente: str, sal: str) -> Dict[str, List[tuple]]:
    """Junta los parámetros de varias manos, sentencia por sentencia."""
    total: Dict[str, List[tuple]] = {k: [] for k in ORDEN}
    jugadores_vistos: set = set()
    for m in manos:
        for k, v in parametros(m, fuente, sal).items():
            if k == "jugador":  # un insert por jugador distinto del lote, no uno por asiento y mano
                v = [j for j in v if j not in jugadores_vistos]
                jugadores_vistos.update(v)
            total[k].extend(v)
    return total


def _paquetes(manos: Iterable[ResultadoMano], tamano: int) -> Iterator[List[ResultadoMano]]:
    """Agrupa un iterable de manos en listas de hasta `tamano`, sin materializarlo entero."""
    it = iter(manos)
    while True:
        paquete = list(islice(it, tamano))
        if not paquete:
            return
        yield paquete


def cargar(cur, manos: Iterable[ResultadoMano], fuente: str, licencia: str, formato: str, sal: str,
           tamano_lote: int = 500) -> int:
    """Carga con `executemany` usando un cursor DB-API (psycopg). Devuelve las manos enviadas."""
    cur.execute(SQL["fuente"], (fuente, licencia, formato))
    enviadas = 0
    for paquete in _paquetes(manos, tamano_lote):
        lote_sql = lote(paquete, fuente, sal)
        for k in ORDEN:
            if lote_sql[k]:
                cur.executemany(SQL[k], lote_sql[k])
        enviadas += len(paquete)
    return enviadas


# ---------------------------------------------------------------------------
# Carga con COPY: cada lote va a tablas temporales y se inserta por conjuntos.
# ---------------------------------------------------------------------------

STAGING = {
    "jugador": ("stg_jugadores", ["seudonimo"], "seudonimo text"),
    "mano": (
        "stg_manos",
        ["mano_ref", "archivo", "jugada_en", "n_jugadores", "blind_chico", "blind_grande", "boton", "tablero"],
        "mano_ref text, archivo text, jugada_en timestamptz, n_jugadores smallint, blind_chico numeric, "
        "blind_grande numeric, boton smallint, tablero text",
    ),
    "asiento": (
        "stg_asientos",
        ["mano_ref", "asiento", "seudonimo", "stack_inicial", "neto", "cartas", "vio_flop", "llego_showdown",
         "gano_showdown"],
        "mano_ref text, asiento smallint, seudonimo text, stack_inicial numeric, neto numeric, cartas text, "
        "vio_flop boolean, llego_showdown boolean, gano_showdown boolean",
    ),
    "accion": (
        "stg_acciones",
        ["mano_ref", "orden", "calle", "asiento", "tipo", "monto"],
        "mano_ref text, orden integer, calle text, asiento smallint, tipo text, monto numeric",
    ),
}

SQL_COPY = {
    "jugador": (
        "insert into poker.jugadores (fuente_id, seudonimo) "
        "select f.id, s.seudonimo from (select distinct seudonimo from stg_jugadores) s "
        "cross join poker.fuentes f where f.nombre = %s "
        "on conflict (fuente_id, seudonimo) do nothing"
    ),
    "mano": (
        "insert into poker.manos (fuente_id, mano_ref, archivo, jugada_en, n_jugadores, blind_chico, "
        "blind_grande, boton, tablero) "
        "select f.id, s.mano_ref, s.archivo, s.jugada_en, s.n_jugadores, s.blind_chico, s.blind_grande, "
        "s.boton, s.tablero from stg_manos s cross join poker.fuentes f where f.nombre = %s "
        "on conflict (fuente_id, mano_ref) do nothing"
    ),
    "asiento": (
        "insert into poker.asientos (mano_id, asiento, jugador_id, stack_inicial, neto, cartas, vio_flop, "
        "llego_showdown, gano_showdown) "
        "select m.id, s.asiento, j.id, s.stack_inicial, s.neto, s.cartas, s.vio_flop, s.llego_showdown, "
        "s.gano_showdown from stg_asientos s "
        "join poker.fuentes f on f.nombre = %s "
        "join poker.manos m on m.fuente_id = f.id and m.mano_ref = s.mano_ref "
        "left join poker.jugadores j on j.fuente_id = f.id and j.seudonimo = s.seudonimo "
        "on conflict (mano_id, asiento) do nothing"
    ),
    "accion": (
        "insert into poker.acciones (mano_id, orden, calle, asiento, tipo, monto) "
        "select m.id, s.orden, s.calle, s.asiento, s.tipo, s.monto from stg_acciones s "
        "join poker.fuentes f on f.nombre = %s "
        "join poker.manos m on m.fuente_id = f.id and m.mano_ref = s.mano_ref "
        "on conflict (mano_id, orden) do nothing"
    ),
}


def filas_copy(manos: Iterable[ResultadoMano], sal: str) -> Dict[str, List[tuple]]:
    """Filas de un lote para las tablas de paso (sin la fuente), con un solo registro por jugador distinto."""
    total: Dict[str, List[tuple]] = {k: [] for k in ORDEN}
    vistos: set = set()
    for res in manos:
        if res.referencia is None or res.ciega_chica is None or res.ciega_grande is None:
            raise ValueError("la mano no trae referencia o ciegas: no se puede cargar")
        f = filas_de_mano(res, res.referencia, sal, res.ciega_chica, res.ciega_grande, res.archivo)
        m, ref = f["mano"], f["mano"]["mano_ref"]
        total["mano"].append((ref, m["archivo"], m["jugada_en"], m["n_jugadores"], m["blind_chico"],
                              m["blind_grande"], m["boton"], m["tablero"]))
        for a in f["asientos"]:
            if a["seudonimo"] is not None and a["seudonimo"] not in vistos:
                vistos.add(a["seudonimo"])
                total["jugador"].append((a["seudonimo"],))
            total["asiento"].append((ref, a["asiento"], a["seudonimo"], a["stack_inicial"], a["neto"], a["cartas"],
                                     a["vio_flop"], a["llego_showdown"], a["gano_showdown"]))
        for x in f["acciones"]:
            total["accion"].append((ref, x["orden"], x["calle"], x["asiento"], x["tipo"], x["monto"]))
    return total


def cargar_copy(cur, manos: Iterable[ResultadoMano], fuente: str, licencia: str, formato: str, sal: str,
                tamano_lote: int = 5000) -> int:
    """Igual que `cargar`, pero con COPY (psycopg 3) a tablas temporales e inserción por conjuntos.

    Las tablas temporales viven solo dentro de la transacción (`on commit drop`).
    Devuelve las manos enviadas.
    """
    cur.execute(SQL["fuente"], (fuente, licencia, formato))
    for tabla, _, definicion in STAGING.values():
        cur.execute(f"create temp table if not exists {tabla} ({definicion}) on commit drop")
    enviadas = 0
    for paquete in _paquetes(manos, tamano_lote):
        filas = filas_copy(paquete, sal)
        for tabla, _, _ in STAGING.values():
            cur.execute(f"truncate {tabla}")
        for k in ORDEN:
            tabla, columnas, _ = STAGING[k]
            if not filas[k]:
                continue
            with cur.copy(f"copy {tabla} ({', '.join(columnas)}) from stdin") as cp:
                for fila in filas[k]:
                    cp.write_row(fila)
        for k in ORDEN:
            cur.execute(SQL_COPY[k], (fuente,))
        enviadas += len(paquete)
    return enviadas


def literalizar(sql: str, params: Sequence[object]) -> str:
    """Reemplaza cada %s por su literal SQL. Solo para pruebas y cargas pequeñas sin driver."""
    def lit(v: object) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, datetime):
            return "'" + v.isoformat() + "'"
        if isinstance(v, float) and not math.isfinite(v):
            # Los stacks infinitos de HandHQ: 'inf' no es SQL válido; numeric acepta 'Infinity' (PostgreSQL 14+).
            return "'NaN'" if math.isnan(v) else ("'Infinity'" if v > 0 else "'-Infinity'")
        if isinstance(v, (int, float)):
            return repr(v)
        return "'" + str(v).replace("'", "''") + "'"
    partes = sql.split("%s")
    if len(partes) - 1 != len(params):
        raise ValueError("la cantidad de parámetros no coincide")
    return "".join(p + (lit(params[i]) if i < len(params) else "") for i, p in enumerate(partes))


def a_script_sql(manos: Sequence[ResultadoMano], fuente: str, licencia: str, formato: str, sal: str) -> str:
    """Script SQL completo, en una transacción, para cargar pocas manos sin driver."""
    sentencias = [literalizar(SQL["fuente"], (fuente, licencia, formato))]
    paquete = lote(manos, fuente, sal)
    for k in ORDEN:
        sentencias.extend(literalizar(SQL[k], p) for p in paquete[k])
    return "begin;\n" + ";\n".join(sentencias) + ";\ncommit;\n"
