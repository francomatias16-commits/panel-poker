"""Importador de historiales de texto estilo PokerStars (PokerStars, GGPoker y sitios similares).

AVISO: el formato se implementó según su estructura conocida y se prueba con manos sintéticas
(incluida una ida y vuelta desde el motor), pero SIN validarlo contra un archivo real de ninguna sala.
Correr scripts/validar_importacion.py con historiales propios antes de confiar en los resultados. Soporta solo Hold'em No Limit de cash. Rechaza con motivo: torneos, otras variantes,
bote que no cierra con el resumen, antes, ciegas "small & big", manos con varios tableros y registros que no conservan fichas.

Los montos se convierten a centavos enteros para evitar errores de coma flotante.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Dict, Iterator, List, Tuple

from .cartas import Carta
from .motor import ResultadoMano
from .phh import ErrorPHH, Evento, clave_natural

_CABECERA = re.compile(
    r"Hand #[^:\s]+:\s+(?P<juego>.+?)\s+\([$€£]?(?P<sb>[\d.,]+)/[$€£]?(?P<bb>[\d.,]+)(?:\s+\w+)?\)"
)
_ID = re.compile(r"Hand #([^:\s]+):")
_INICIO = re.compile(r"(?m)^(?=(?:Poker|PokerStars)[A-Za-z ]* Hand #)")
_BOTON = re.compile(r"Seat #(\d+) is the button")
_ASIENTO = re.compile(r"^Seat (\d+): (.+?) \([$€£]?([\d.,]+) in chips\)")
_POSTEO = re.compile(r"^(.+?): posts (small blind|big blind|[^$]*?) [$€£]?([\d.,]+)")
_ACCION = re.compile(r"^(?P<n>.+?): (?P<a>folds|checks|calls|bets|raises)\b(?P<r>.*)$")
_MONTO = re.compile(r"[$€£]?([\d,]*\.?\d+)")
_COBRO = re.compile(r"^(.+?) collected [$€£]?([\d.,]+) from")
_DEVUELTA = re.compile(r"^Uncalled bet \([$€£]?([\d.,]+)\) returned to (.+)$")
_REPARTO = re.compile(r"^Dealt to (.+?) \[([^\]]+)\]")
_MUESTRA = re.compile(r"^(.+?): shows \[([^\]]+)\]")
_CALLE = {"FLOP": "flop", "TURN": "turn", "RIVER": "river"}
_FECHA = re.compile(r"(\d{4})[/-](\d{2})[/-](\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})")
_AUSENTE = re.compile(r"\)\s+(?:is sitting out|out of hand)", re.I)
_BOTE = re.compile(r"Total pot [$€£]?([\d.,]+)")
_RAKE = re.compile(r"\bRake [$€£]?([\d.,]+)")


def _cent(texto: str) -> int:
    return int(round(float(texto.replace(",", "")) * 100))


def _fecha(linea: str):
    """Primera fecha y hora de la cabecera (PokerStars trae la hora local y la de ET: se usa la primera)."""
    m = _FECHA.search(linea)
    if not m:
        return None
    try:
        return datetime(*(int(x) for x in m.groups()))
    except ValueError:
        return None


def _cartas(texto: str) -> Tuple[Carta, ...]:
    return tuple(Carta.desde_texto(t) for t in texto.split())


def _verificar_bote(lineas: List[str], bote_calculado: int, cobrado: int) -> None:
    """Contrasta el bote reconstruido con el "Total pot" y el "Rake" del resumen, si existen.

    Es la prueba de que los montos inferidos cuadran con lo que informó la sala. Tolera 1 centavo.
    """
    resumen = next((l for l in lineas if l.startswith("Total pot")), None)
    if resumen is None:
        return
    m = _BOTE.search(resumen)
    if not m:
        return
    informado = _cent(m.group(1))
    if abs(informado - bote_calculado) > 1:
        raise ErrorPHH(f"el bote no cierra: reconstruido {bote_calculado / 100:.2f}, informado {informado / 100:.2f}")
    r = _RAKE.search(resumen)
    if r and abs(cobrado + _cent(r.group(1)) - informado) > 1:
        # Con jackpot o bonos la sala resta otros cargos: se avisa como rechazo explicado, no se adivina.
        raise ErrorPHH(f"cobros más rake no igualan el bote ({(cobrado + _cent(r.group(1))) / 100:.2f} contra {informado / 100:.2f})")


def separar_manos(texto: str) -> List[str]:
    """Separa un archivo con varias manos en textos de una mano."""
    partes = _INICIO.split(texto)
    return [p.strip() for p in partes if _ID.search(p.strip().split("\n", 1)[0])]


def desde_ggpoker(texto: str) -> ResultadoMano:
    lineas = [l.strip() for l in texto.strip().splitlines() if l.strip()]
    if lineas and re.search(r"tournament|\bTN\d", lineas[0], re.I):
        raise ErrorPHH("torneo no soportado")
    cab = _CABECERA.search(lineas[0]) if lineas else None
    if not cab:
        raise ErrorPHH("cabecera no reconocida")
    if "hold" not in cab.group("juego").lower() or "no limit" not in cab.group("juego").lower():
        raise ErrorPHH(f"variante no soportada: {cab.group('juego')}")
    if any(l.startswith("***") and re.search(r"second|first", l, re.I) for l in lineas):
        raise ErrorPHH("varios tableros no soportado")

    boton_n = _BOTON.search(" ".join(lineas[:3]))
    if not boton_n:
        raise ErrorPHH("falta el botón")
    asientos: List[Tuple[int, str, int]] = []
    ausentes: List[Tuple[int, str]] = []
    for l in lineas:
        m = _ASIENTO.match(l)
        if m:
            if _AUSENTE.search(l):
                ausentes.append((int(m.group(1)), m.group(2)))
            else:
                asientos.append((int(m.group(1)), m.group(2), _cent(m.group(3))))
    # Un jugador "sitting out" no recibe cartas ni actúa: contarlo inflaría "vieron el flop".
    # Si aun así postea o actúa, se lo reincorpora para no perder información.
    activos = {l.split(":", 1)[0] for l in lineas if re.match(r"^.+?: (?:posts|folds|checks|calls|bets|raises)\b", l)}
    for num, nombre in ausentes:
        if nombre in activos:
            m = next(_ASIENTO.match(l) for l in lineas if _ASIENTO.match(l) and _ASIENTO.match(l).group(1) == str(num))
            asientos.append((num, nombre, _cent(m.group(3))))
    asientos.sort()
    n = len(asientos)
    if not 2 <= n <= 10:
        raise ErrorPHH("número de jugadores fuera de rango")
    nombres = [a[1] for a in asientos]
    indice = {nombre: i for i, nombre in enumerate(nombres)}
    stacks = [a[2] for a in asientos]
    numeros = [a[0] for a in asientos]
    if int(boton_n.group(1)) not in numeros:
        raise ErrorPHH("el botón no está entre los asientos")
    boton = numeros.index(int(boton_n.group(1)))

    apuesta = [0] * n  # lo puesto en la calle actual
    total = [0] * n  # lo puesto en toda la mano
    sb = bb = None
    eventos: List[Evento] = []
    tablero: List[Carta] = []
    cartas: Dict[int, Tuple[Carta, ...]] = {}
    cobros = [0] * n
    devuelto = [0] * n
    retirados: set = set()
    retirados_antes_flop: set = set()
    calle = "preflop"
    hubo_showdown = False

    for l in lineas[1:]:
        if l.startswith("*** SUMMARY"):
            break
        if l.startswith("***"):
            palabra = re.match(r"\*\*\*\s+(\S+(?: \S+)?)\s+\*\*\*", l)
            clave = palabra.group(1).replace(" ", "").upper() if palabra else ""
            if clave in _CALLE:
                if clave == "FLOP":
                    retirados_antes_flop = set(retirados)
                calle = _CALLE[clave]
                nuevas = _cartas(re.findall(r"\[([^\]]+)\]", l)[-1])
                tablero.extend(nuevas)
                apuesta = [0] * n
                eventos.append(Evento(calle, None, "reparto_tablero", None, nuevas))
            elif clave == "SHOWDOWN":
                hubo_showdown = True
            continue
        m = _REPARTO.match(l)
        if m and m.group(1) in indice:
            cartas[indice[m.group(1)]] = _cartas(m.group(2))
            continue
        m = _MUESTRA.match(l)
        if m and m.group(1) in indice:
            cartas[indice[m.group(1)]] = _cartas(m.group(2))
            continue
        m = _COBRO.match(l)
        if m and m.group(1) in indice:
            cobros[indice[m.group(1)]] += _cent(m.group(2))
            continue
        m = _DEVUELTA.match(l)
        if m and m.group(2) in indice:
            devuelto[indice[m.group(2)]] += _cent(m.group(1))
            continue
        if "posts" in l and calle == "preflop" and not tablero:
            m = _POSTEO.match(l)
            if not m or m.group(1) not in indice:
                raise ErrorPHH("posteo no reconocido")
            tipo, i, monto = m.group(2), indice[m.group(1)], _cent(m.group(3))
            if tipo == "small blind":
                sb = i
            elif tipo == "big blind":
                bb = i
            else:
                raise ErrorPHH(f"posteo no soportado: {tipo}")
            apuesta[i] += monto
            total[i] += monto
            continue
        m = _ACCION.match(l)
        if not m or m.group("n") not in indice:
            continue
        i, accion, resto = indice[m.group("n")], m.group("a"), m.group("r")
        montos = [_cent(x) for x in _MONTO.findall(resto)]
        if accion == "folds":
            retirados.add(i)
            eventos.append(Evento(calle, i + 1, "f"))
        elif accion == "checks":
            eventos.append(Evento(calle, i + 1, "cc", None))
        elif accion == "calls":
            if not montos:
                raise ErrorPHH("call sin monto")
            apuesta[i] += montos[0]
            total[i] += montos[0]
            eventos.append(Evento(calle, i + 1, "cc", montos[0]))
        else:  # bets / raises: el monto de la jugada es el total de la calle
            if not montos:
                raise ErrorPHH("apuesta sin monto")
            objetivo = montos[-1] if accion == "raises" else montos[0]
            total[i] += objetivo - apuesta[i]
            apuesta[i] = objetivo
            eventos.append(Evento(calle, i + 1, "cbr", objetivo))

    if sb is None or bb is None:
        raise ErrorPHH("faltan las ciegas")
    neto = [cobros[i] + devuelto[i] - total[i] for i in range(n)]
    if sum(neto) > 0:
        raise ErrorPHH("cobros superan lo invertido en el bote (registro inconsistente)")
    _verificar_bote(lineas, sum(total) - sum(devuelto), sum(cobros))

    vieron_flop = [i for i in range(n) if i not in (retirados_antes_flop if tablero else retirados)]
    llegaron: List[int] = []
    if hubo_showdown and len(tablero) == 5:
        llegaron = [i for i in range(n) if i not in retirados]
    return ResultadoMano(
        boton=boton, sb=sb, bb=bb,
        stacks_iniciales=list(stacks),
        stacks_finales=[stacks[i] + neto[i] for i in range(n)],
        neto=neto,
        cartas=[cartas.get(i, ()) for i in range(n)],
        tablero=tablero, eventos=eventos,
        vieron_flop=vieron_flop, llegaron_showdown=llegaron,
        ganadores_showdown=[i for i in llegaron if cobros[i] > 0],
        nombres=nombres, ciega_grande=_cent(cab.group("bb")), ciega_chica=_cent(cab.group("sb")),
        referencia=_ID.search(lineas[0]).group(1), fecha=_fecha(lineas[0]),
    )


def iterar_directorio(ruta: str, rechazos: List[Tuple[str, str]], extension: str = ".txt") -> Iterator[ResultadoMano]:
    """Genera las manos de los archivos de un directorio de a una (solo se guarda un archivo en memoria).

    Los rechazos se agregan a `rechazos` como (archivo, motivo).
    """
    for dirpath, subdirs, archivos in os.walk(ruta):
        subdirs.sort(key=clave_natural)
        for nombre in sorted(archivos, key=clave_natural):
            if not nombre.endswith(extension):
                continue
            camino = os.path.join(dirpath, nombre)
            with open(camino, encoding="utf-8-sig", errors="replace") as f:
                bloques = separar_manos(f.read())
            for bloque in bloques:
                try:
                    m = desde_ggpoker(bloque)
                except ErrorPHH as e:
                    rechazos.append((camino, str(e)))
                    continue
                except (ValueError, IndexError, KeyError, AttributeError, TypeError, StopIteration) as e:
                    # Un formato inesperado no debe tumbar toda la carga: se rechaza esa mano con motivo.
                    rechazos.append((camino, f"error de lectura ({type(e).__name__}): {e}"))
                    continue
                m.archivo = os.path.relpath(camino, ruta)
                yield m


def cargar_directorio(ruta: str, extension: str = ".txt") -> Tuple[List[ResultadoMano], List[Tuple[str, str]]]:
    """Carga todas las manos de los archivos de un directorio. Devuelve (válidas, rechazos)."""
    rechazos: List[Tuple[str, str]] = []
    manos = list(iterar_directorio(ruta, rechazos, extension))
    return manos, rechazos
