"""Aplicación de escritorio (Tkinter). Elige una carpeta de manos y muestra el panel.

Uso: python3 app/ventana.py
Necesita Tkinter (en Linux: paquete python3-tk). No hay pruebas automáticas de esta ventana;
la lógica está en poker_analisis/panel.py y sí tiene pruebas.
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poker_analisis.panel import a_csv, analizar_directorio  # noqa: E402

COLUMNAS = [
    ("nombre", "Jugador", 110), ("stake", "Stake (BB)", 80), ("manos", "Manos", 70), ("vpip", "VPIP %", 70),
    ("pfr", "PFR %", 70), ("tres_bet", "3-bet %", 70), ("af", "AF", 60),
    ("wtsd", "WTSD %", 70), ("wsd", "W$SD %", 70), ("cbet", "C-bet %", 70),
    ("fold_cbet", "Fold c-bet %", 90), ("bb100", "bb/100", 80),
    ("ic95", "±IC95", 70), ("drawdown_bb", "Drawdown bb", 100), ("ruina_100bi", "Ruina 100 BI", 100),
]
PORCENTAJES = {"vpip", "pfr", "tres_bet", "wtsd", "wsd", "cbet", "fold_cbet", "ruina_100bi"}


def formato(campo, valor):
    if valor is None:
        return "-"
    if campo in PORCENTAJES:
        return f"{100 * valor:.1f}"
    if isinstance(valor, float):
        return f"{valor:.2f}"
    return str(valor)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Análisis de poker")
        self.geometry("1100x520")
        self.panel = None
        self._resultados: queue.Queue = queue.Queue()  # el hilo de análisis deja aquí su resultado
        barra = ttk.Frame(self, padding=8)
        barra.pack(fill="x")
        ttk.Button(barra, text="Abrir carpeta…", command=self.abrir).pack(side="left")
        ttk.Button(barra, text="Exportar CSV…", command=self.exportar).pack(side="left", padx=6)
        ttk.Label(barra, text="Formato:").pack(side="left", padx=(16, 2))
        self.formato = tk.StringVar(value="texto")
        ttk.Combobox(barra, textvariable=self.formato, values=["texto", "phh"], width=8,
                     state="readonly").pack(side="left")
        ttk.Label(barra, text="Big blind (auto o fichas):").pack(side="left", padx=(16, 2))
        self.bb = tk.StringVar(value="auto")
        ttk.Entry(barra, textvariable=self.bb, width=7).pack(side="left")
        ttk.Label(barra, text="Mín. manos (completa o número):").pack(side="left", padx=(16, 2))
        self.umbral = tk.StringVar(value="completa")
        ttk.Entry(barra, textvariable=self.umbral, width=7).pack(side="left")
        self.tabla = ttk.Treeview(self, columns=[c[0] for c in COLUMNAS], show="headings")
        for campo, titulo, ancho in COLUMNAS:
            self.tabla.heading(campo, text=titulo)
            self.tabla.column(campo, width=ancho, anchor="e" if campo != "nombre" else "w")
        self.tabla.tag_configure("poca", foreground="#888888")
        self.tabla.pack(fill="both", expand=True, padx=8)
        self.estado = ttk.Label(self, text="Elegí una carpeta con historiales (.txt estilo PokerStars/GGPoker o .phh)", padding=8)
        self.estado.pack(fill="x")

    def abrir(self):
        ruta = filedialog.askdirectory()
        if not ruta:
            return
        try:
            bb = None if self.bb.get().strip().lower() == "auto" else int(self.bb.get())
            umbral = None if self.umbral.get().strip().lower() == "completa" else int(self.umbral.get())
        except ValueError:
            messagebox.showerror("Datos inválidos", "Revisá big blind y mínimo de manos.")
            return
        # El análisis corre en un hilo: con carpetas grandes la ventana sigue respondiendo.
        self.estado.config(text="Analizando… esto puede tardar con carpetas grandes.")
        threading.Thread(target=self._analizar, args=(ruta, bb, umbral, self.formato.get()), daemon=True).start()
        self.after(100, self._esperar)

    def _analizar(self, ruta, bb, umbral, formato):
        try:
            self._resultados.put(("ok", analizar_directorio(ruta, bb, umbral, formato)))
        except ValueError as e:
            self._resultados.put(("error", str(e) or "Revisá big blind y mínimo de manos."))

    def _esperar(self):
        try:
            estado, valor = self._resultados.get_nowait()
        except queue.Empty:
            self.after(100, self._esperar)
            return
        if estado == "error":
            messagebox.showerror("Datos inválidos", valor)
            self.estado.config(text="No se pudo analizar la carpeta.")
            return
        self._mostrar(valor)

    def _mostrar(self, panel):
        self.panel = panel
        self.tabla.delete(*self.tabla.get_children())
        for f in self.panel.filas:
            valores = [formato(c, getattr(f, c)) for c, _, _ in COLUMNAS]
            self.tabla.insert("", "end", values=valores, tags=() if f.muestra_suficiente else ("poca",))
        self.estado.config(
            text=f"{self.panel.manos_validas} manos válidas, {len(self.panel.rechazos)} rechazadas. "
                 "En gris: muestra menor al mínimo. Con pocas manos el IC95 es muy ancho."
        )

    def exportar(self):
        if not self.panel:
            messagebox.showinfo("Sin datos", "Primero abrí una carpeta.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv")
        if ruta:
            a_csv(self.panel, ruta)


if __name__ == "__main__":
    App().mainloop()
