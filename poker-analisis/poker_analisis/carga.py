"""Carga de manos a la base (schema `poker`, ver db/schema.sql).

Separa la preparación de las sentencias (pura, probable sin red) de su ejecución. Todas las
sentencias son idempotentes: repetir una carga no duplica nada (clave: fuente + referencia de
mano). Las filas se enlazan por subconsultas, no por ids devueltos, así que se pueden ejecutar
por lotes con `executemany`.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple

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
        "insert into poker.manos (fuente_id, mano_ref, archivo, n_jugadores, blind_chico, "
        "blind_grande, boton, tablero) "
        "select id, %s, %s, %s, %s, %s, %s, %s from poker.fuentes where nombre = %s "
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
    salida["mano"].append((ref, m["archivo"], m["n_jugadores"], m["blind_chico"], m["blind_grande"],
                           m["boton"], m["tablero"], fuente))
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
    for m in manos:
        for k, v in parametros(m, fuente, sal).items():
            total[k].extend(v)
    return total


def cargar(cur, manos: Sequence[ResultadoMano], fuente: str, licencia: str, formato: str, sal: str,
           tamano_lote: int = 500) -> int:
    """Ejecuta la carga con un cursor DB-API (psycopg). Devuelve las manos enviadas.

    No hace commit: lo decide quien llama (así una carga fallida se puede revertir).
    """
    cur.execute(SQL["fuente"], (fuente, licencia, formato))
    for i in range(0, len(manos), tamano_lote):
        paquete = lote(manos[i:i + tamano_lote], fuente, sal)
        for k in ORDEN:
            if paquete[k]:
                cur.executemany(SQL[k], paquete[k])
    return len(manos)


def literalizar(sql: str, params: Sequence[object]) -> str:
    """Reemplaza cada %s por su literal SQL. Solo para pruebas y cargas pequeñas sin driver."""
    def lit(v: object) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
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
