"""Estadísticas y evaluación del modelo de rangos sobre manos reales (dataset PHH).

Uso (desde la raíz del proyecto), con el dataset clonado en la ruta indicada:
    python3 scripts/analizar_real.py [ruta_pluribus]

Fuente: dataset PHH público (Juho Kim, Universidad de Toronto), licencia CC BY 4.0.
Las manos de Pluribus se jugaron contra jugadores profesionales humanos. Tienen las
cartas de todos los jugadores, así que la predicción se contrasta con la realidad.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.estadisticas import calcular, formatear  # noqa: E402
from poker_analisis.rangos import ModeloRangos, calibracion, recolectar, resumen  # noqa: E402
from poker_analisis.real import cargar_directorio  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..")
RUTA = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/uoftcprg/phh-dataset/data/pluribus"
SALIDA_STATS = os.path.join(RAIZ, "resultados", "estadisticas_real_pluribus.csv")
SALIDA_RANGOS = os.path.join(RAIZ, "resultados", "rangos_real_pluribus.csv")
BB = 100  # blind grande del dataset: 50/100


def main():
    manos, rechazos = cargar_directorio(RUTA)
    print(f"Manos válidas: {len(manos)}. Rechazadas: {len(rechazos)}.")
    print(f"Suma de netos igual a cero en {sum(1 for m in manos if sum(m.neto) == 0)} de {len(manos)} manos.\n")

    nombres = sorted({n for m in manos for n in m.nombres})
    stats = calcular(manos, nombres=[], bb=BB)
    stats.sort(key=lambda s: s.manos, reverse=True)
    print("Estadísticas por jugador (bb = 100 fichas):\n")
    print(formatear(stats))

    corte = int(len(manos) * 0.75)
    entrenamiento, prueba = manos[:corte], manos[corte:]
    modelo = ModeloRangos(k=5.0, con_posicion=True, con_rivales=False)
    modelo.entrenar(entrenamiento, nombres=[])
    registros = recolectar(modelo, prueba, nombres=[])
    filas = resumen(registros, nombres)
    _, ece = calibracion(registros)

    print(f"\nRangos preflop con posición. Entrenamiento: {len(entrenamiento)} manos. "
          f"Prueba: {len(prueba)}. ECE sin calibrar: {ece:.4f}\n")
    cabecera = f"{'jugador':<14}{'decis.':>8}{'logloss':>9}{'base':>8}{'mejora%':>9}{'acierto':>9}"
    print(cabecera)
    print("-" * len(cabecera))
    for f in filas:
        print(f"{f['perfil']:<14}{f['decisiones']:>8}{f['logloss']:>9.3f}{f['logloss_base']:>8.3f}"
              f"{f['mejora_logloss_%']:>9.1f}{100 * f['acierto_top1']:>8.1f}%")

    os.makedirs(os.path.dirname(SALIDA_STATS), exist_ok=True)
    with open(SALIDA_STATS, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["jugador", "manos", "vpip", "pfr", "tres_bet", "af", "wtsd", "wsd", "cbet", "fold_cbet", "bb100", "ic95"])
        for s in stats:
            escritor.writerow([
                s.nombre, s.manos, round(s.vpip, 4), round(s.pfr, 4),
                "" if s.tres_bet is None else round(s.tres_bet, 4),
                "" if s.af is None else round(s.af, 4),
                "" if s.wtsd is None else round(s.wtsd, 4),
                "" if s.wsd is None else round(s.wsd, 4),
                "" if s.cbet is None else round(s.cbet, 4),
                "" if s.fold_cbet is None else round(s.fold_cbet, 4),
                round(s.bb100, 3), round(s.bb100_ic95, 3),
            ])
    with open(SALIDA_RANGOS, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0].keys()))
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"\nGuardado en {os.path.abspath(SALIDA_STATS)} y {os.path.abspath(SALIDA_RANGOS)}")


if __name__ == "__main__":
    main()
