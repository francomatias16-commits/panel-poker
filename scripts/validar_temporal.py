"""Validación cruzada temporal del modelo de rangos preflop (plan, sección 7).

Uso (desde la raíz del proyecto):
    python3 scripts/validar_temporal.py [ruta_phh] [pliegues] [--recalibrar]

Sin ruta, simula una mesa con bots (requiere resultados/preflop_equity.csv).
Las manos se toman en orden de nombre de archivo, que se asume cronológico.
Escribe resultados/validacion_temporal.csv.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.rangos import validacion_temporal  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..")
SALIDA = os.path.join(RAIZ, "resultados", "validacion_temporal.csv")
SALIDA_CURVAS = os.path.join(RAIZ, "resultados", "validacion_temporal_calibracion.csv")


def main():
    args = [a for a in sys.argv[1:] if a != "--recalibrar"]
    recalibrar = "--recalibrar" in sys.argv
    ruta = args[0] if args else None
    pliegues = int(args[1]) if len(args) > 1 else 5
    if ruta:
        from poker_analisis.real import cargar_directorio

        manos, rechazos = cargar_directorio(ruta)
        nombres = []
        print(f"Manos válidas: {len(manos)}. Rechazadas: {len(rechazos)}.")
    else:
        from poker_analisis.bots import cargar_tabla_preflop
        from poker_analisis.simulacion import PERFILES, simular_mesa

        manos = simular_mesa(cargar_tabla_preflop(os.path.join(RAIZ, "resultados", "preflop_equity.csv")), 3000, 7)
        nombres = PERFILES
        print(f"Manos simuladas: {len(manos)}.")

    filas = validacion_temporal(manos, nombres, pliegues=pliegues, recalibrar=recalibrar, k=5.0, con_posicion=True)
    cab = f"{'pliegue':>8}{'entren.':>9}{'prueba':>8}{'decis.':>8}{'logloss':>9}{'base':>8}{'brier':>8}{'base':>8}{'ECE':>8}"
    print(cab)
    print("-" * len(cab))
    for f in filas:
        print(f"{f['pliegue']:>8}{f['manos_entrenamiento']:>9}{f['manos_prueba']:>8}{f['decisiones']:>8}"
              f"{f['logloss']:>9.3f}{f['logloss_base']:>8.3f}{f['brier']:>8.3f}{f['brier_base']:>8.3f}{f['ece']:>8.3f}")
    if recalibrar:
        print("\nRecalibración por temperatura (ajustada con el 20 % final del entrenamiento):")
        print(f"{'pliegue':>8}{'T':>7}{'logloss':>9}{'cal':>8}{'ECE':>8}{'cal':>8}")
        for f in filas:
            if "T" in f:
                print(f"{f['pliegue']:>8}{f['T']:>7.2f}{f['logloss_nucleo']:>9.3f}{f['logloss_cal']:>8.3f}"
                      f"{f['ece_nucleo']:>8.3f}{f['ece_cal']:>8.3f}")
        print()
    mejora = sum(f["logloss"] < f["logloss_base"] for f in filas)
    print(f"\nEl modelo supera al base en logloss en {mejora} de {len(filas)} pliegues.")

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    campos = sorted({k for fila in filas for k in fila if k != "curva"}, key=lambda k: list(filas[0]).index(k) if k in filas[0] else 99)
    with open(SALIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows({k: fila.get(k, "") for k in campos} for fila in filas)
    with open(SALIDA_CURVAS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pliegue", "intervalo", "n", "confianza_media", "acierto_real"])
        for fila in filas:
            for c in fila["curva"]:
                w.writerow([fila["pliegue"], c["intervalo"], c["n"],
                            round(c["confianza_media"], 4), round(c["acierto_real"], 4)])
    print(f"Guardado en {os.path.abspath(SALIDA)} y {os.path.abspath(SALIDA_CURVAS)}")


if __name__ == "__main__":
    main()
