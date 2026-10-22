"""Conversión de una mano a filas para la base relacional (db/schema.sql).

Los nombres de jugadores se reemplazan por un seudónimo (hash con sal) antes de salir de
este módulo. Los ids los asigna la base; las filas se enlazan por asiento y por orden.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from .motor import ResultadoMano

_TIPOS_ACCION = {"f", "cc", "cbr"}
_CALLES = {"preflop", "flop", "turn", "river"}


def seudonimo(nombre: str, sal: str) -> str:
    """Hash estable con sal. Mismo nombre y misma sal dan el mismo seudónimo."""
    return hashlib.sha256(f"{sal}:{nombre}".encode("utf-8")).hexdigest()[:16]


def _texto_cartas(cartas) -> Optional[str]:
    if not cartas or any(c is None for c in cartas):
        return None
    return " ".join(str(c) for c in cartas)


def filas_de_mano(
    res: ResultadoMano, mano_ref: str, sal: str, blind_chico: float, blind_grande: float,
    archivo: Optional[str] = None,
) -> Dict[str, object]:
    """Filas de una mano: {'mano', 'asientos', 'acciones'}.

    Los montos de las ciegas se pasan aparte: ResultadoMano solo guarda sus asientos.
    """
    n = len(res.neto)
    mano = {
        "mano_ref": mano_ref,
        "archivo": archivo,
        "jugada_en": res.fecha,
        "n_jugadores": n,
        "blind_chico": blind_chico,
        "blind_grande": blind_grande,
        "boton": res.boton,
        "tablero": " ".join(str(c) for c in res.tablero),
    }
    asientos: List[Dict[str, object]] = []
    for i in range(n):
        asientos.append({
            "asiento": i,
            "seudonimo": seudonimo(res.nombres[i], sal) if res.nombres else None,
            "stack_inicial": res.stacks_iniciales[i],
            "neto": res.neto[i],
            "cartas": _texto_cartas(res.cartas[i]) if i < len(res.cartas) else None,
            "vio_flop": i in res.vieron_flop,
            "llego_showdown": i in res.llegaron_showdown,
            "gano_showdown": i in res.ganadores_showdown,
        })
    acciones: List[Dict[str, object]] = []
    for e in res.eventos:
        if e.tipo in _TIPOS_ACCION and e.jugador is not None and e.calle in _CALLES:
            acciones.append({
                "orden": len(acciones),
                "calle": e.calle,
                "asiento": e.jugador - 1,  # los eventos usan asientos 1-based
                "tipo": e.tipo,
                "monto": e.monto,
            })
    return {"mano": mano, "asientos": asientos, "acciones": acciones}
