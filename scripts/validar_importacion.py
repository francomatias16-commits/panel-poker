"""Fase 0: validación del importador de historiales de texto (PokerStars/GGPoker).

Uso:
    python3 scripts/validar_importacion.py RUTA [--muestra 30] [--semilla 1] [--salida resultados]

Genera en la carpeta de salida:
  - validacion_rechazos.csv     una fila por mano rechazada: archivo, id de mano, motivo
  - validacion_resumen.txt      totales, rechazos por motivo y por archivo, controles de integridad
  - validacion_muestra.md       manos al azar con el texto original y lo que el importador entendió,
                                para revisar a mano (criterio de aceptación: cero manos mal leídas)

Controles de integridad sobre cada mano válida: suma de netos = -rake (nunca positiva), stacks finales
no negativos, y el bote contra el resumen del historial (lo hace el importador y rechaza si no cierra).
"""
from __future__ import annotations

import argparse
import collections
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poker_analisis.ggpoker import _ID, desde_ggpoker, separar_manos  # noqa: E402
from poker_analisis.phh import ErrorPHH, clave_natural  # noqa: E402

_ACCION = {"f": "se retira", "cc": "iguala/pasa", "cbr": "apuesta/sube a"}


def describir(m) -> str:
    """Resumen legible de lo que el importador entendió de una mano."""
    cent = lambda x: f"{x / 100:.2f}"  # noqa: E731
    nombres = m.nombres or [f"asiento {i + 1}" for i in range(len(m.neto))]
    lin = [f"Botón: {nombres[m.boton]} | SB: {nombres[m.sb]} | BB: {nombres[m.bb]} | ciegas {cent(m.ciega_chica)}/{cent(m.ciega_grande)}"]
    if m.fecha:
        lin.append(f"Fecha: {m.fecha:%Y-%m-%d %H:%M:%S}")
    for i, nom in enumerate(nombres):
        cartas = " ".join(str(c) for c in m.cartas[i]) or "-"
        lin.append(f"  {nom}: stack {cent(m.stacks_iniciales[i])}, cartas {cartas}, neto {cent(m.neto[i])}")
    calle = None
    for e in m.eventos:
        if e.calle != calle:
            calle = e.calle
            lin.append(f"[{calle}]")
        if e.tipo == "reparto_tablero":
            lin.append("  tablero: " + " ".join(str(c) for c in e.cartas))
        else:
            monto = f" {cent(e.monto)}" if e.monto is not None else ""
            lin.append(f"  {nombres[e.jugador - 1]} {_ACCION.get(e.tipo, e.tipo)}{monto}")
    lin.append(f"Llegaron al showdown: {[nombres[i] for i in m.llegaron_showdown]}; ganan: {[nombres[i] for i in m.ganadores_showdown]}")
    lin.append(f"Suma de netos (= -rake): {cent(sum(m.neto))}")
    return "\n".join(lin)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ruta")
    ap.add_argument("--extension", default=".txt")
    ap.add_argument("--muestra", type=int, default=30)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--salida", default="resultados")
    a = ap.parse_args()
    if not os.path.exists(a.ruta):
        sys.exit(f"No existe la carpeta: {a.ruta}\nPoné la ruta real de la carpeta con tus historiales (entre comillas si tiene espacios).")
    if not os.path.isdir(a.ruta):
        sys.exit(f"{a.ruta} es un archivo: indicá la carpeta que lo contiene.")
    archivos_ok, otras = [], collections.Counter()
    for dp, _, nombres in os.walk(a.ruta):
        for n in nombres:
            if n.endswith(a.extension):
                archivos_ok.append(os.path.join(dp, n))
            else:
                otras[os.path.splitext(n)[1].lower() or "(sin extensión)"] += 1
    if not archivos_ok:
        hallado = ", ".join(f"{e}: {c}" for e, c in otras.most_common(8)) or "la carpeta está vacía"
        sys.exit(f"No encontré archivos {a.extension} en {a.ruta} (ni en sus subcarpetas). Encontré: {hallado}.\n"
                 f"Si tus historiales tienen otra extensión, agregá --extension .ext")
    print(f"Archivos {a.extension} encontrados: {len(archivos_ok)}")
    os.makedirs(a.salida, exist_ok=True)

    validas = 0
    rechazos = []  # (archivo, id, motivo)
    por_archivo = collections.defaultdict(lambda: [0, 0])  # archivo -> [válidas, rechazadas]
    problemas = []
    reservorio = []  # muestreo uniforme sin guardar todo en memoria
    rng = random.Random(a.semilla)

    for dirpath, subdirs, archivos in os.walk(a.ruta):
        subdirs.sort(key=clave_natural)
        for nombre in sorted(archivos, key=clave_natural):
            if not nombre.endswith(a.extension):
                continue
            camino = os.path.join(dirpath, nombre)
            rel = os.path.relpath(camino, a.ruta)
            with open(camino, encoding="utf-8-sig", errors="replace") as f:
                bloques = separar_manos(f.read())
            for bloque in bloques:
                ident = _ID.search(bloque.split("\n", 1)[0]).group(1)
                try:
                    m = desde_ggpoker(bloque)
                except ErrorPHH as e:
                    rechazos.append((rel, ident, str(e)))
                    por_archivo[rel][1] += 1
                    continue
                except Exception as e:  # noqa: BLE001  cualquier error inesperado también se informa
                    rechazos.append((rel, ident, f"error de lectura ({type(e).__name__}): {e}"))
                    por_archivo[rel][1] += 1
                    continue
                validas += 1
                por_archivo[rel][0] += 1
                if sum(m.neto) > 0:
                    problemas.append((rel, ident, "la suma de netos es positiva"))
                if any(s < 0 for s in m.stacks_finales):
                    problemas.append((rel, ident, "stack final negativo"))
                if validas <= a.muestra:
                    reservorio.append((rel, bloque, m))
                else:
                    j = rng.randint(1, validas)
                    if j <= a.muestra:
                        reservorio[j - 1] = (rel, bloque, m)

    total = validas + len(rechazos)
    with open(os.path.join(a.salida, "validacion_rechazos.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "mano", "motivo"])
        w.writerows(rechazos)

    # Agrupar motivos sin los números, para que "bote no cierra: 3.00 contra 3.25" cuente como uno solo
    def tipo(motivo: str) -> str:
        return motivo.split(":")[0].split("(")[0].strip()

    lineas = [f"Manos leídas: {total}", f"Válidas: {validas}", f"Rechazadas: {len(rechazos)}"]
    if total:
        lineas.append(f"Tasa de rechazo: {100 * len(rechazos) / total:.1f} %")
    lineas.append("\nRechazos por motivo:")
    for mot, n in collections.Counter(tipo(r[2]) for r in rechazos).most_common():
        lineas.append(f"  {n:6d}  {mot}")
    lineas.append("\nArchivos con más rechazos (válidas / rechazadas):")
    peores = sorted(por_archivo.items(), key=lambda kv: -kv[1][1])[:10]
    for arch, (v, r) in peores:
        if r:
            lineas.append(f"  {arch}: {v} / {r}")
    lineas.append(f"\nControles de integridad fallidos: {len(problemas)}")
    for rel, ident, mot in problemas[:20]:
        lineas.append(f"  {rel} #{ident}: {mot}")
    texto = "\n".join(lineas)
    print(texto)
    with open(os.path.join(a.salida, "validacion_resumen.txt"), "w", encoding="utf-8") as f:
        f.write(texto + "\n")

    with open(os.path.join(a.salida, "validacion_muestra.md"), "w", encoding="utf-8") as f:
        f.write(f"# Muestra para revisar a mano ({len(reservorio)} manos al azar, semilla {a.semilla})\n\n")
        f.write("Para cada mano: compará el texto original con lo que entendió el importador. "
                "Marcá con una X las que estén bien. Aceptación: todas.\n\n")
        for n, (rel, bloque, m) in enumerate(reservorio, 1):
            f.write(f"## {n}. {rel} — mano #{m.referencia}  [ ] bien\n\n")
            f.write("**Original**\n\n```\n" + bloque + "\n```\n\n")
            f.write("**Lo que entendió el importador**\n\n```\n" + describir(m) + "\n```\n\n")
    print(f"\nArchivos escritos en {a.salida}: validacion_rechazos.csv, validacion_resumen.txt, validacion_muestra.md")


if __name__ == "__main__":
    main()
