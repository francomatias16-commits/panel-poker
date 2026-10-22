"""Inicia el panel de estudio. Uso: python iniciar.py [--demo] [--carpeta RUTA --formato phh|texto] [--puerto N]

No necesita instalar nada: el proyecto usa solo la biblioteca estándar de Python (3.11 o más nuevo).
Todo corre en tu computadora y no envía manos ni video a ningún servicio.
"""

import os
import runpy
import sys

MINIMO = (3, 11)


def verificar_python(version=None) -> None:
    v = tuple(version or sys.version_info[:2])
    if v < MINIMO:
        raise SystemExit(f"Hace falta Python {MINIMO[0]}.{MINIMO[1]} o más nuevo (este es {v[0]}.{v[1]}). "
                         "Descargalo de https://www.python.org/downloads/")


def main() -> None:
    verificar_python()
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    sys.argv[0] = os.path.join(raiz, "app", "web.py")
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
