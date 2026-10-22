"""Textura del tablero y tamaño de apuesta sugerido.

La textura se calcula con reglas deterministas (palos, conexión y pares del tablero). Los tamaños por textura
son CONVENCIONES de estudio habituales (seco: apuesta chica; mojado: apuesta grande), no resultados de un solver:
las constantes están al inicio para poder cambiarlas o calibrarlas contra salidas de un solver.
"""

from __future__ import annotations

from typing import Dict, Sequence

from .cartas import Carta

# Fracción del bote que se sugiere apostar por valor, según la humedad del tablero.
FRACCION_POR_HUMEDAD = {"seca": 0.33, "media": 0.50, "mojada": 0.75}
EXTRA_TURN_RIVER_MOJADA = 0.10  # en turn y river los tableros mojados piden algo más
LIMITE_MEDIA, LIMITE_MOJADA = 2, 4  # puntaje de humedad desde el que un tablero es media / mojada


def _conexion(valores: Sequence[int]) -> int:
    """Máximo de cartas distintas del tablero que caben en una ventana de 5 rangos (el as cuenta alto y bajo)."""
    vs = set(valores)
    if 14 in vs:
        vs.add(1)
    return max(len(vs & set(range(b, b + 5))) for b in range(1, 11))


def _compacta(valores: Sequence[int]) -> bool:
    """¿Hay 3 cartas distintas dentro de una ventana de 4 rangos?"""
    vs = set(valores)
    if 14 in vs:
        vs.add(1)
    return any(len(vs & set(range(b, b + 4))) >= 3 for b in range(1, 12))


def textura(tablero: Sequence[Carta]) -> Dict[str, object]:
    """Describe un tablero de 3 a 5 cartas."""
    if not 3 <= len(tablero) <= 5:
        raise ValueError("la textura se define con 3 a 5 cartas de tablero")
    valores = [c.valor for c in tablero]
    por_palo: Dict[str, int] = {}
    for c in tablero:
        por_palo[c.palo] = por_palo.get(c.palo, 0) + 1
    palos_max = max(por_palo.values())
    repetidas = len(valores) - len(set(valores))
    conex = _conexion(valores)

    puntaje = 0
    puntaje += {1: 0, 2: 1}.get(palos_max, 2 if palos_max == 3 else 3)  # color hecho o proyecto
    if conex >= 4:
        puntaje += 3  # escalera hecha o proyecto abierto fuerte
    elif conex == 3:
        puntaje += 1 + (1 if _compacta(valores) else 0)  # tres cartas muy juntas dan proyectos abiertos
    puntaje -= 1 if repetidas else 0  # un par en el tablero reduce las combinaciones fuertes del rival
    puntaje = max(puntaje, 0)
    humedad = "mojada" if puntaje >= LIMITE_MOJADA else "media" if puntaje >= LIMITE_MEDIA else "seca"
    return {
        "humedad": humedad, "puntaje": puntaje, "pareado": repetidas > 0,
        "palos_max": palos_max, "monocolor": palos_max >= 3, "conexion": conex,
        "carta_alta": max(valores),
    }


def tamano_sugerido(tablero: Sequence[Carta]) -> Dict[str, object]:
    """Fracción del bote a apostar por valor y una explicación breve."""
    t = textura(tablero)
    f = FRACCION_POR_HUMEDAD[t["humedad"]]
    if t["humedad"] == "mojada" and len(tablero) >= 4:
        f += EXTRA_TURN_RIVER_MOJADA
    motivos = []
    if t["monocolor"]:
        motivos.append("hay tres o más cartas de un palo")
    if t["conexion"] >= 3:
        motivos.append("las cartas están conectadas")
    if t["pareado"]:
        motivos.append("el tablero está pareado")
    if not motivos:
        motivos.append("sin colores ni conexiones relevantes")
    return {"fraccion": f, "textura": t,
            "texto": f"Tablero {t['humedad']} ({'; '.join(motivos)}): apuesta de ~{round(f * 100)}% del bote."}
