"""Fechas de las manos, streaming del panel y el calculador incremental de estadísticas."""

import dataclasses
import datetime as dt
import os
import unittest

from poker_analisis import carga
from poker_analisis.estadisticas import CalculadorEstadisticas, calcular
from poker_analisis.panel import analizar_manos
from poker_analisis.real import desde_phh
from poker_analisis.riesgo import max_drawdown, serie_neta

RUTA = os.path.join(os.path.dirname(__file__), "fixtures", "pluribus_ejemplo.phh")
UTC = dt.timezone.utc


def base():
    with open(RUTA, encoding="utf-8") as f:
        return f.read()


def con_fecha(texto, anio, mes, dia, hora=None):
    extra = f"year = {anio}\nmonth = {mes}\nday = {dia}\n"
    if hora is not None:
        extra += f"time = {hora}\n"
    return desde_phh(texto.replace("hand = 63", extra + "hand = 63"))


class TestFechaDeLaMano(unittest.TestCase):
    def test_fecha_con_hora_tomal(self):
        m = con_fecha(base(), 2019, 7, 1, "13:45:30")
        self.assertEqual(m.fecha, dt.datetime(2019, 7, 1, 13, 45, 30, tzinfo=UTC))

    def test_fecha_sin_hora_es_medianoche_utc(self):
        m = con_fecha(base(), 2019, 7, 2)
        self.assertEqual(m.fecha, dt.datetime(2019, 7, 2, 0, 0, tzinfo=UTC))

    def test_sin_fecha_es_none(self):
        self.assertIsNone(desde_phh(base()).fecha)

    def test_fecha_invalida_se_rechaza(self):
        with self.assertRaises(ValueError):
            con_fecha(base(), 2019, 13, 1)

    def test_jugada_en_llega_a_la_fila_de_la_mano(self):
        m = con_fecha(base(), 2019, 7, 1, "10:00:00")
        t = carga.lote([m], "f", "sal")
        self.assertEqual(t["mano"][0][2], m.fecha)


class TestPanelEnStreaming(unittest.TestCase):
    def setUp(self):
        self.base = desde_phh(base())
        # Tres manos del mismo stake, llegadas fuera de orden cronológico.
        self.netos = [[300, -300, 0, 0, 0, 0], [-500, 500, 0, 0, 0, 0], [200, -200, 0, 0, 0, 0]]
        dias = [3, 1, 2]
        self.manos = [
            dataclasses.replace(self.base, neto=n, fecha=dt.datetime(2019, 7, d, tzinfo=UTC))
            for n, d in zip(self.netos, dias)
        ]

    def _drawdown(self, filas, nombre):
        return next(f.drawdown_bb for f in filas if f.nombre == nombre)

    def test_drawdown_sigue_el_orden_cronologico(self):
        filas = analizar_manos(self.manos, bb=100)
        # En orden de fecha: +200 (día 1), +200 (día 2)... netos en bb: 1 día1=-5, día2=+2, día3=+3
        cronologico = sorted(self.manos, key=lambda m: m.fecha)
        esperado = max_drawdown(serie_neta(cronologico, "Bill", 100))
        self.assertAlmostEqual(self._drawdown(filas, "Bill"), esperado)

    def test_sin_fecha_cuenta_el_orden_de_llegada(self):
        sin = [dataclasses.replace(m, fecha=None) for m in self.manos]
        filas = analizar_manos(sin, bb=100)
        esperado = max_drawdown(serie_neta(sin, "Bill", 100))
        self.assertAlmostEqual(self._drawdown(filas, "Bill"), esperado)

    def test_generador_da_la_misma_tabla_que_la_lista(self):
        self.assertEqual(analizar_manos(iter(self.manos), bb=100), analizar_manos(self.manos, bb=100))


class TestCalculadorIncremental(unittest.TestCase):
    def test_agregar_de_a_una_iguala_a_calcular(self):
        manos = [dataclasses.replace(desde_phh(base()), neto=[100 * i, -100 * i, 0, 0, 0, 0]) for i in range(1, 6)]
        calc = CalculadorEstadisticas(2)
        for m in manos:
            calc.agregar(m)
        self.assertEqual(calc.resultados(), calcular(manos, [], 2))

    def test_series_en_orden_de_llegada(self):
        m = desde_phh(base())
        calc = CalculadorEstadisticas(2)
        calc.agregar(m)
        calc.agregar(dataclasses.replace(m, neto=[-200, 200, 0, 0, 0, 0]))
        self.assertEqual(list(calc.series["Bill"]), [-50.0, -100.0])


class TestFilasCopy(unittest.TestCase):
    def test_copy_tiene_las_mismas_filas_que_el_lote(self):
        m1 = con_fecha(base(), 2019, 7, 1, "10:00:00")
        m2 = dataclasses.replace(m1, referencia="otra")
        por_lote = carga.lote([m1, m2], "f", "sal")
        copy = carga.filas_copy([m1, m2], "sal")
        # Mismas columnas, en el orden de las tablas de paso: `lote` pone la ref al final y `filas_copy` al principio.
        # lote asiento: (asiento, stack, neto, cartas, vio, llego, gano, seudonimo, fuente, ref)
        asientos = [(a[9], a[0], a[7], a[1], a[2], a[3], a[4], a[5], a[6]) for a in por_lote["asiento"]]
        # lote accion: (orden, calle, asiento, tipo, monto, fuente, ref)
        acciones = [(a[6], a[0], a[1], a[2], a[3], a[4]) for a in por_lote["accion"]]
        self.assertEqual(sorted(map(repr, copy["asiento"])), sorted(map(repr, asientos)))
        self.assertEqual(sorted(map(repr, copy["accion"])), sorted(map(repr, acciones)))
        self.assertEqual(len(copy["mano"]), 2)
        self.assertEqual(len(copy["jugador"]), len(por_lote["jugador"]))


if __name__ == "__main__":
    unittest.main()
