"""Entrena, calibra y evalúa el modelo de rangos preflop con verdad de terreno.

Uso (desde la raíz del proyecto):
    python3 scripts/evaluar_rangos.py [manos] [semilla]

Partición cronológica:
- entrenamiento 60 %: aprende las probabilidades de acción por mano y perfil.
- validación 15 %: ajusta los calibradores (temperatura e isotónica). No se usa para evaluar.
- prueba 25 %: solo para reportar, con cada versión ya ajustada.

Como en la simulación se conocen las cartas de todos, cada predicción se contrasta
con lo que realmente ocurrió. Resultados en resultados/evaluacion_rangos.csv.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.bots import cargar_tabla_preflop  # noqa: E402
from poker_analisis.rangos import (  # noqa: E402
    ModeloRangos,
    ajustar_isotonica,
    ajustar_lambda_isotonica,
    ajustar_temperatura,
    calibracion,
    recolectar,
    resumen,
    temperatura,
    transformar_isotonica,
)
from poker_analisis.simulacion import PERFILES, simular_mesa  # noqa: E402

RAIZ = os.path.join(os.path.dirname(__file__), "..")
TABLA = os.path.join(RAIZ, "resultados", "preflop_equity.csv")
SALIDA = os.path.join(RAIZ, "resultados", "evaluacion_rangos.csv")


def imprimir_resumen(titulo, filas):
    print(titulo)
    cabecera = (f"{'perfil':<12}{'decis.':>8}{'logloss':>9}{'base':>8}{'mejora%':>9}"
                f"{'brier':>8}{'acierto':>9}{'ganancia':>10}")
    print(cabecera)
    print("-" * len(cabecera))
    for f in filas:
        print(f"{f['perfil']:<12}{f['decisiones']:>8}{f['logloss']:>9.3f}{f['logloss_base']:>8.3f}"
              f"{f['mejora_logloss_%']:>9.1f}{f['brier']:>8.3f}{100 * f['acierto_top1']:>8.1f}%"
              f"{f['ganancia_bits']:>9.3f}")
    print()


def imprimir_calibracion(titulo, tabla, ece):
    print(f"{titulo} (ECE = {ece:.4f})")
    print(f"{'intervalo':<12}{'n':>8}{'confianza':>12}{'acierto real':>14}")
    for c in tabla:
        print(f"{c['intervalo']:<12}{c['n']:>8}{c['confianza_media']:>12.3f}{c['acierto_real']:>14.3f}")
    print()


def pares_confianza(registros, transformar=None):
    """(confianza de la clase principal, acierto) por decisión."""
    pares = []
    for r in registros:
        p = transformar(r["pred"]) if transformar else r["pred"]
        top = max(p, key=p.get)
        pares.append((p[top], top == r["accion"]))
    return pares


def main():
    manos = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    semilla = int(sys.argv[2]) if len(sys.argv) > 2 else 11

    print(f"Simulando {manos} manos (semilla {semilla})...")
    tabla = cargar_tabla_preflop(TABLA)
    resultados = simular_mesa(tabla, manos, semilla)
    corte_train = int(manos * 0.60)
    corte_val = int(manos * 0.75)
    entrenamiento = resultados[:corte_train]
    validacion = resultados[corte_train:corte_val]
    prueba = resultados[corte_val:]

    modelo = ModeloRangos(k=5.0)
    modelo.entrenar(entrenamiento, PERFILES)

    reg_val = recolectar(modelo, validacion, PERFILES)
    reg_prueba = recolectar(modelo, prueba, PERFILES)

    T = ajustar_temperatura(reg_val)
    f_temp = lambda p: temperatura(p, T)  # noqa: E731
    iso = ajustar_isotonica(pares_confianza(reg_val))
    lam = ajustar_lambda_isotonica(reg_val, iso)
    f_iso = transformar_isotonica(iso, lam)

    versiones = [
        ("sin_calibrar", None),
        (f"temperatura_T{T:.2f}", f_temp),
        (f"isotonica_lam{lam:.2f}", f_iso),
    ]

    print(f"Entrenamiento: {len(entrenamiento)} manos. Validación: {len(validacion)}. "
          f"Prueba: {len(prueba)}.\n")

    filas_por_version = {}
    for nombre, f in versiones:
        filas_por_version[nombre] = resumen(reg_prueba, PERFILES, transformar=f)
        cal, ece = calibracion(reg_prueba, transformar=f)
        imprimir_resumen(f"Versión: {nombre}", filas_por_version[nombre])
        imprimir_calibracion(f"Calibración ({nombre})", cal, ece)
    print("'ganancia' = bits de información sobre la mano real que aporta el posterior frente al prior.")

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["version", "perfil", "decisiones", "logloss", "logloss_base",
                           "mejora_logloss_pct", "brier", "acierto_top1", "ganancia_bits"])
        for version, filas in filas_por_version.items():
            for fila in filas:
                escritor.writerow([version, fila["perfil"], fila["decisiones"],
                                   round(fila["logloss"], 4), round(fila["logloss_base"], 4),
                                   round(fila["mejora_logloss_%"], 2), round(fila["brier"], 4),
                                   round(fila["acierto_top1"], 4), round(fila["ganancia_bits"], 4)])
    print(f"Resultados guardados en {os.path.abspath(SALIDA)}")


if __name__ == "__main__":
    main()
