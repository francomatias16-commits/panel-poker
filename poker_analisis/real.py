"""Conversión de manos reales en formato PHH al modelo de resultados del proyecto.

El formato PHH no registra cuánto iguala un `cc`. Aquí se infiere a partir de las
apuestas de cada calle: si el jugador debe fichas, es un call con ese monto; si no,
es un check. Los asientos y el botón se derivan de las ciegas.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import replace
from datetime import datetime, time as dtime, timezone
from typing import Iterator, List, Optional, Sequence, Tuple

from .motor import ResultadoMano
from .phh import ErrorPHH, Evento, Mano, clave_natural, parsear_mano


def _posiciones_ciegas(blinds: Sequence[int]) -> Tuple[int, int]:
    """Asientos (0-based) del small blind y del big blind."""
    con_ciega = [i for i, b in enumerate(blinds) if b > 0]
    if len(con_ciega) < 2:
        raise ErrorPHH("se requieren al menos dos ciegas")
    return con_ciega[0], con_ciega[1]


def _inferir_montos(
    eventos: Sequence[Evento], apuesta_inicial: List[int], maximo_inicial: int, stacks: Sequence[float]
) -> List[Evento]:
    """Asigna a cada `cc` el monto que iguala, acotado por el stack restante, o None si es un check.

    Si el jugador iguala un all-in con menos fichas de las que debe, solo pone lo que tiene.
    Con stacks infinitos (HandHQ) no hay cota y se usa el monto completo.
    """
    n = len(apuesta_inicial)
    apuesta = list(apuesta_inicial)
    total = list(apuesta_inicial)
    maximo = maximo_inicial
    salida: List[Evento] = []
    for e in eventos:
        if e.tipo == "reparto_tablero":
            apuesta = [0] * n
            maximo = 0
            salida.append(e)
            continue
        if e.jugador is None or e.tipo not in ("cc", "cbr", "f"):
            salida.append(e)
            continue
        s = e.jugador - 1
        if e.tipo == "cc":
            pagar = maximo - apuesta[s]
            if pagar > 0:
                restante = stacks[s] - total[s]
                efectivo = min(pagar, restante)
                apuesta[s] += efectivo
                total[s] += efectivo
                salida.append(replace(e, monto=efectivo))
            else:
                salida.append(replace(e, monto=None))
        elif e.tipo == "cbr":
            total[s] += e.monto - apuesta[s]
            apuesta[s] = e.monto
            maximo = max(maximo, e.monto)
            salida.append(e)
        else:
            salida.append(e)
    return salida


def _invertido(eventos: Sequence[Evento], apuesta_inicial: List[int]) -> List[float]:
    """Fichas que cada jugador puso en el bote a lo largo de la mano, incluidas las ciegas."""
    n = len(apuesta_inicial)
    apuesta = list(apuesta_inicial)
    total = list(apuesta_inicial)
    for e in eventos:
        if e.tipo == "reparto_tablero":
            apuesta = [0] * n
            continue
        if e.jugador is None:
            continue
        s = e.jugador - 1
        if e.tipo == "cc" and e.monto is not None:
            apuesta[s] += e.monto
            total[s] += e.monto
        elif e.tipo == "cbr":
            total[s] += e.monto - apuesta[s]
            apuesta[s] = e.monto
    return total


def _fecha(meta: dict) -> Optional[datetime]:
    """Fecha y hora de la mano con year, month, day y time del PHH. None si falta la fecha.

    Una hora sin zona se toma como UTC, porque el PHH no indica otra cosa.
    """
    anio, mes, dia = meta.get("year"), meta.get("month"), meta.get("day")
    if anio is None or mes is None or dia is None:
        return None
    hora = meta.get("time")
    if hora is None:
        h = dtime(0)
    elif isinstance(hora, dtime):
        h = hora
    elif isinstance(hora, str):
        h = dtime.fromisoformat(hora)
    else:
        raise ErrorPHH("time no es una hora válida")
    return datetime(anio, mes, dia, h.hour, h.minute, h.second, h.microsecond, tzinfo=timezone.utc)


def desde_phh(texto: str) -> ResultadoMano:
    """Convierte una mano PHH real en un ResultadoMano listo para estadísticas y rangos.

    Si el archivo trae `finishing_stacks`, el neto sale de ahí. Si trae solo `winnings`
    (HandHQ, stacks infinitos), el neto sale de `winnings` y los stacks finales quedan en inf.
    """
    mano: Mano = parsear_mano(texto)
    n = len(mano.stacks_iniciales)
    finales = mano.metadatos.get("finishing_stacks")
    ganancias = mano.metadatos.get("winnings")
    if finales is None and ganancias is None:
        raise ErrorPHH("falta finishing_stacks o winnings")
    if finales is not None and len(finales) != n:
        raise ErrorPHH("finishing_stacks no coincide con el número de jugadores")
    if finales is None:
        if len(ganancias) != n:
            raise ErrorPHH("winnings no coincide con el número de jugadores")
        finales = [i + g for i, g in zip(mano.stacks_iniciales, ganancias)]
    nombres = mano.metadatos.get("players")
    if nombres is not None and len(nombres) != n:
        raise ErrorPHH("players no coincide con el número de jugadores")

    sb, bb = _posiciones_ciegas(mano.blinds)
    boton = sb if n == 2 else (sb - 1) % n

    apuesta_inicial = [0] * n
    apuesta_inicial[sb] = mano.blinds[sb]
    apuesta_inicial[bb] = mano.blinds[bb]
    eventos = _inferir_montos(mano.eventos, apuesta_inicial, max(mano.blinds), mano.stacks_iniciales)

    cartas = [tuple(mano.cartas_jugadores.get(s + 1, ())) for s in range(n)]

    # Quién vio el flop: no se retiró antes de que se reparte la primera carta del tablero.
    retirados: set = set()
    for e in eventos:
        if e.tipo == "reparto_tablero":
            break
        if e.tipo == "f" and e.jugador is not None:
            retirados.add(e.jugador - 1)
    vieron_flop = [s for s in range(n) if s not in retirados]

    # Quién llegó a showdown: queda más de un jugador al final y el tablero está completo.
    retirados_final = {e.jugador - 1 for e in eventos if e.tipo == "f" and e.jugador is not None}
    llegaron: List[int] = []
    if len(mano.tablero) == 5 and n - len(retirados_final) >= 2:
        llegaron = [s for s in range(n) if s not in retirados_final]

    if ganancias is not None:
        # `winnings` es lo que cada jugador cobró del bote; el neto resta lo que puso.
        invertido = _invertido(eventos, apuesta_inicial)
        neto = [g - inv for g, inv in zip(ganancias, invertido)]
        # El rake hace que la suma sea negativa. Una suma positiva significa que el registro
        # reparte más fichas de las que se pusieron en el bote: el registro es inconsistente.
        if sum(neto) > 1e-6:
            raise ErrorPHH("winnings superan lo invertido en el bote (registro inconsistente)")
    else:
        neto = [f - i for f, i in zip(finales, mano.stacks_iniciales)]
    ganadores = [s for s in llegaron if neto[s] > 0]

    return ResultadoMano(
        boton=boton,
        sb=sb,
        bb=bb,
        stacks_iniciales=list(mano.stacks_iniciales),
        stacks_finales=list(finales),
        neto=neto,
        cartas=cartas,
        tablero=list(mano.tablero),
        eventos=eventos,
        vieron_flop=vieron_flop,
        llegaron_showdown=llegaron,
        ganadores_showdown=ganadores,
        nombres=list(nombres) if nombres is not None else None,
        ciega_grande=mano.blinds[bb],
        ciega_chica=mano.blinds[sb],
        referencia=hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16],
        fecha=_fecha(mano.metadatos),
    )


def iterar_directorio(ruta: str, rechazos: List[Tuple[str, str]], extension: str = ".phh") -> Iterator[ResultadoMano]:
    """Genera las manos de un directorio de a una, en orden natural de carpetas y archivos.

    El orden es numérico donde los nombres tienen números ('2.phh' antes que '10.phh') y se
    mantiene entre subcarpetas. Los archivos rechazados se agregan a `rechazos` como (archivo, motivo).
    """
    for dirpath, subdirs, archivos in os.walk(ruta):
        subdirs.sort(key=clave_natural)  # os.walk respeta el orden de esta lista
        for nombre in sorted(archivos, key=clave_natural):
            if not nombre.endswith(extension):
                continue
            camino = os.path.join(dirpath, nombre)
            try:
                with open(camino, encoding="utf-8") as f:
                    m = desde_phh(f.read())
            except (ErrorPHH, ValueError, IndexError) as e:
                rechazos.append((camino, str(e)))
                continue
            m.archivo = os.path.relpath(camino, ruta)
            yield m


def cargar_directorio(ruta: str, extension: str = ".phh") -> Tuple[List[ResultadoMano], List[Tuple[str, str]]]:
    """Carga todas las manos de un directorio (ver `iterar_directorio`). Devuelve (manos_válidas, rechazos).

    La validación temporal necesita las manos en orden cronológico; por eso el orden es natural.
    Para datasets grandes conviene `iterar_directorio`, que no guarda todas las manos.
    """
    rechazos: List[Tuple[str, str]] = []
    manos = list(iterar_directorio(ruta, rechazos, extension))
    return manos, rechazos


def cargar_multimano(texto: str) -> List[str]:
    """Separa un archivo .phhs (varias manos con encabezados '[n]') en textos de una mano."""
    partes = re.split(r"^\[\d+\]\s*$", texto, flags=re.MULTILINE)
    return [p.strip() + "\n" for p in partes if p.strip()]
