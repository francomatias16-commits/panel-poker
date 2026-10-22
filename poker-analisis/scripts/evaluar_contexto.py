"""Compara variantes del modelo de rangos: base, con posición y con posición y rivales.

Uso (desde la raíz del proyecto):
    python3 scripts/evaluar_contexto.py [manos] [semilla]

Todas las variantes se entrenan y prueban sobre las mismas manos (60 % y 25 %).
Se reporta logloss y ECE sin calibración adicional, para aislar el efecto del contexto.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.bots import cargar_tabla_preflop  # noqa: E402
from poker_analisis.rangos import ModeloRangos, calibracion, recolectar, resumen  # noqa: E402
from poker_analisis.simulacion import PERFILES, simular_mesa  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..")
TABLA = os.path.join(RAIZ, "resultados", "preflop_equity.csv")


def main():
    manos = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    semilla = int(sys.argv[2]) if len(sys.argv) > 2 else 11

    print(f"Simulando {manos} manos (semilla {semilla})...")
    tabla = cargar_tabla_preflop(TABLA)
    resultados = simular_mesa(tabla, manos, semilla)
    entrenamiento = resultados[: int(manos * 0.60)]
    prueba = resultados[int(manos * 0.75):]

    variantes = [
        ("base", False, False),
        ("posicion", True, False),
        ("posicion+rivales", True, True),
    ]

    print(f"\n{'variante':<20}{'perfil':<12}{'decis.':>8}{'logloss':>9}{'base':>8}{'mejora%':>9}{'ECE':>8}")
    print("-" * 74)
    for nombre, con_pos, con_riv in variantes:
        modelo = ModeloRangos(k=5.0, con_posicion=con_pos, con_rivales=con_riv)
        modelo.entrenar(entrenamiento, PERFILES)
        registros = recolectar(modelo, prueba, PERFILES)
        filas = resumen(registros, PERFILES)
        _, ece = calibracion(registros)
        for f in filas:
            ece_txt = f"{ece:8.4f}" if f is filas[0] else ""
            print(f"{nombre:<20}{f['perfil']:<12}{f['decisiones']:>8}{f['logloss']:>9.3f}"
                  f"{f['logloss_base']:>8.3f}{f['mejora_logloss_%']:>9.1f}{ece_txt}")
        print()


if __name__ == "__main__":
    main()
