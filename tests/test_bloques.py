"""Informe por bloques (Fase 5): EV del all-in con casos de resultado conocido, proyección, partición en bloques,
ejemplos que abren la mano correcta y coincidencia de cifras con el panel."""
import math
import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "app"))

from poker_analisis import bloques as B, bots, simulacion  # noqa: E402
from poker_analisis.cartas import Mazo, parsear_cartas  # noqa: E402
from poker_analisis.motor import jugar_mano  # noqa: E402

CC = ("cc", None)


class MazoFijo(Mazo):
    """Mazo con el orden dado: primero las cartas del asiento 0, luego las del 1, luego el tablero."""

    def __init__(self, orden: str):
        super().__init__(semilla=1)
        usadas = orden.split()
        resto = [f"{v}{p}" for v in "23456789TJQKA" for p in "cdhs" if f"{v}{p}" not in usadas]
        self._cartas = parsear_cartas(orden + " " + " ".join(resto))

    def barajar(self):
        pass


def _politica(acciones):
    cola = list(acciones)
    return lambda v: cola.pop(0) if cola else CC


def mano_allin_turn(orden="Kd Kc As Ah 2c 7d 9h Ts 3s"):
    """Heads-up, 100 de stack, ciegas 1/2. Limp, check, check y all-in en el turn: solo falta el river."""
    r = jugar_mano([100, 100], 0, 1, 2, [_politica([CC, CC, CC]), _politica([CC, CC, ("cbr", 98)])], MazoFijo(orden))
    r.ciega_grande, r.ciega_chica = 2, 1
    return r


class TestEquityConocida(unittest.TestCase):
    def test_river_completo(self):
        a, b = parsear_cartas("As Ah"), parsear_cartas("Kd Kc")
        self.assertEqual(B.equity_conocida(a, b, parsear_cartas("2c 7d 9h Ts 3s")), 1.0)
        self.assertEqual(B.equity_conocida(b, a, parsear_cartas("2c 7d 9h Ts 3s")), 0.0)

    def test_empate_exacto(self):
        a, b = parsear_cartas("As Kd"), parsear_cartas("Ah Kc")
        self.assertEqual(B.equity_conocida(a, b, parsear_cartas("2c 7d 9h Ts 3s")), 0.5)

    def test_turn_exacta(self):
        # AA contra KK con 2c 7d 9h Ts: solo los dos reyes que quedan le dan el bote a KK (42 de 44 salidas).
        a, b = parsear_cartas("As Ah"), parsear_cartas("Kd Kc")
        self.assertAlmostEqual(B.equity_conocida(a, b, parsear_cartas("2c 7d 9h Ts")), 42 / 44, places=12)

    def test_preflop_monte_carlo(self):
        a, b = parsear_cartas("As Ah"), parsear_cartas("Kd Kc")
        self.assertAlmostEqual(B.equity_conocida(a, b, [], 6000, 3), 0.82, delta=0.03)


class TestEvAllin(unittest.TestCase):
    def test_favorito_que_gana(self):
        r = mano_allin_turn()
        self.assertEqual(r.neto, [-100, 100])
        real, ev = B.ev_allin(r, 1)
        self.assertAlmostEqual(real, 50.0)  # 100 fichas = 50 bb
        self.assertAlmostEqual(ev, (42 / 44 * 200 - 100) / 2, places=9)

    def test_el_otro_lado_es_simetrico(self):
        r = mano_allin_turn()
        real, ev = B.ev_allin(r, 0)
        self.assertAlmostEqual(real, -50.0)
        self.assertAlmostEqual(ev, (2 / 44 * 200 - 100) / 2, places=9)

    def test_los_evs_de_los_dos_suman_cero(self):
        r = mano_allin_turn()
        self.assertAlmostEqual(B.ev_allin(r, 0)[1] + B.ev_allin(r, 1)[1], 0.0, places=9)

    def test_sin_cartas_por_salir_no_hay_ajuste(self):
        # All-in en el river: no queda suerte que ajustar.
        r = jugar_mano([100, 100], 0, 1, 2, [_politica([CC, CC, CC, CC]), _politica([CC, CC, CC, ("cbr", 98)])],
                       MazoFijo("Kd Kc As Ah 2c 7d 9h Ts 3s"))
        r.ciega_grande, r.ciega_chica = 2, 1
        self.assertIsNone(B.ev_allin(r, 1))

    def test_sin_showdown_no_hay_ajuste(self):
        r = jugar_mano([100, 100], 0, 1, 2, [_politica([("f", None)]), _politica([])], MazoFijo("Kd Kc As Ah 2c 7d 9h Ts 3s"))
        r.ciega_grande, r.ciega_chica = 2, 1
        self.assertIsNone(B.ev_allin(r, 0))

    def test_cartas_del_rival_ocultas(self):
        r = mano_allin_turn()
        r.cartas[0] = ()
        self.assertIsNone(B.ev_allin(r, 1))


class TestProyeccion(unittest.TestCase):
    def test_muestra_chica(self):
        self.assertIsNone(B.proyeccion_proximo_bloque([1.0] * 29))

    def test_sin_varianza(self):
        self.assertIsNone(B.proyeccion_proximo_bloque([1.0] * 100))

    def test_media_cero_da_un_medio(self):
        serie = [5.0, -5.0] * 50
        self.assertAlmostEqual(B.proyeccion_proximo_bloque(serie), 0.5, places=9)

    def test_signo_y_monotonia(self):
        base = [4.0, -3.0, 1.0, -2.0, 0.5] * 40
        p0 = B.proyeccion_proximo_bloque(base)
        p1 = B.proyeccion_proximo_bloque([x + 0.5 for x in base])
        p2 = B.proyeccion_proximo_bloque([x - 0.5 for x in base])
        self.assertGreater(p1, p0)
        self.assertLess(p2, p0)

    def test_valor_calculado_a_mano(self):
        serie = [1.0, -1.0, 2.0, 0.0] * 25
        n, mu = len(serie), sum(serie) / len(serie)
        var = sum((x - mu) ** 2 for x in serie) / (n - 1)
        se2 = var / n
        z = 1000 * mu / math.sqrt(1000 ** 2 * se2 + 1000 * var)
        esperado = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        self.assertAlmostEqual(B.proyeccion_proximo_bloque(serie), esperado, places=12)

    def test_incertidumbre_del_winrate_le_resta_certeza(self):
        # Mismo winrate observado: con más manos de historia hay menos incertidumbre sobre el winrate real
        # y la probabilidad de ganar el próximo bloque sube, sin llegar nunca al límite que fija la varianza propia.
        corta = [1.0, -0.6, 0.2, -0.1] * 10
        larga = corta * 100
        pc, pl = B.proyeccion_proximo_bloque(corta), B.proyeccion_proximo_bloque(larga)
        self.assertLess(pc, pl)
        self.assertLess(pl, 1.0)


class TestObjetivo(unittest.TestCase):
    def test_sin_leaks_y_sin_decisiones(self):
        self.assertIn("Cargá historiales", B._objetivo([], None, 1 / 3))

    def test_sin_leaks_mantiene_porcentaje(self):
        self.assertIn("80 %", B._objetivo([], 0.8, 1 / 3))

    def test_con_leak_baja_un_tercio(self):
        lk = B.Leak("preflop: X", 30, 60.0, 6.0, 0, [])
        txt = B._objetivo([lk], 0.7, 1 / 3)
        self.assertIn("de 30 casos a 20 o menos", txt)
        self.assertIn("2.0 bb/100", txt)


def _manos_demo(n, semilla=7):
    tabla = bots.cargar_tabla_preflop(os.path.join(RAIZ, "resultados", "preflop_equity.csv"))
    manos = simulacion.simular_mesa(tabla, n, semilla)
    inicio = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
    for k, m in enumerate(manos):
        m.nombres = list(simulacion.PERFILES)
        m.ciega_chica, m.ciega_grande = simulacion.BLIND_CHICO, simulacion.BLIND_GRANDE
        m.fecha = inicio + timedelta(seconds=45 * k)
        m.referencia = f"H{k}"
    return manos


class TestSerieEInformes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manos = _manos_demo(130)
        cls.jugador = simulacion.PERFILES[0]
        t = time.time()
        cls.informes = B.informes_por_bloque(cls.manos, cls.jugador, None, tam=50, iteraciones=20)
        cls.seg = time.time() - t

    def test_particion_en_bloques(self):
        self.assertEqual([i.manos for i in self.informes], [50, 50, 30])
        self.assertEqual([i.completo for i in self.informes], [True, True, False])
        self.assertEqual([i.numero for i in self.informes], [1, 2, 3])

    def test_serie_en_orden_cronologico_aunque_lleguen_desordenadas(self):
        revueltas = list(reversed(self.manos))
        serie = B.serie_del_jugador(revueltas, self.jugador)
        fechas = [m.fecha for m, _ in serie]
        self.assertEqual(fechas, sorted(fechas))

    def test_stakes_mezclados_exigen_elegir(self):
        manos = _manos_demo(10)
        manos[0].ciega_grande = 4
        with self.assertRaises(ValueError):
            B.serie_del_jugador(manos, self.jugador)
        self.assertEqual(len(B.serie_del_jugador(manos, self.jugador, 4)), 1)

    def test_bb100_del_bloque_coincide_con_la_cuenta_directa(self):
        i = self.informes[0]
        serie = B.serie_del_jugador(self.manos, self.jugador)[:50]
        directo = 100 * sum(m.neto[a] / m.ciega_grande for m, a in serie) / 50
        self.assertAlmostEqual(i.bb100, directo, places=9)

    def test_decisiones_y_coincidencias_son_consistentes(self):
        for i in self.informes:
            self.assertLessEqual(i.coinciden, i.decisiones)
            self.assertEqual(i.desvios_claros + i.desvios_leves, i.decisiones - i.coinciden)
            self.assertLessEqual(len(i.leaks), 3)
            costos = [lk.perdida_bb for lk in i.leaks]
            self.assertEqual(costos, sorted(costos, reverse=True))

    def test_los_ejemplos_abren_la_mano_del_jugador(self):
        vistos = 0
        for i in self.informes:
            for lk in i.leaks:
                for n, ref, ident in lk.ejemplos:
                    vistos += 1
                    m = self.manos[ident]
                    self.assertIn(self.jugador, m.nombres)
                    self.assertEqual(m.referencia, ref)
                    self.assertEqual(B.serie_del_jugador(self.manos, self.jugador)[n - 1][0], m)
        self.assertGreater(vistos, 0)

    def test_probabilidades_en_rango(self):
        for i in self.informes:
            for p in (i.prob_winrate_positivo, i.prob_ganar_proximo):
                if p is not None:
                    self.assertTrue(0.0 <= p <= 1.0)

    def test_evolucion(self):
        ev = B.evolucion(self.informes)
        self.assertEqual(len(ev), 3)
        self.assertNotIn("delta_perdida_bb100", ev[0])
        self.assertAlmostEqual(ev[1]["delta_perdida_bb100"], self.informes[1].perdida_bb100 - self.informes[0].perdida_bb100)
        self.assertAlmostEqual(ev[2]["delta_pct_proceso"], self.informes[2].pct_proceso - self.informes[1].pct_proceso)

    def test_texto_trae_las_seis_secciones(self):
        txt = B.formatear(self.informes, self.jugador)
        for seccion in ("1. Resultado", "2. Proceso", "3. Leaks", "4. Evolución", "5. Proyección", "6. Objetivo"):
            self.assertIn(seccion, txt)

    def test_progreso(self):
        avances = []
        B.informes_por_bloque(self.manos[:60], self.jugador, None, tam=30, iteraciones=10, progreso=lambda h, t: avances.append((h, t)))
        self.assertEqual(avances[-1][0], avances[-1][1])
        self.assertEqual([h for h, _ in avances], list(range(1, len(avances) + 1)))


class TestJugadorPrincipal(unittest.TestCase):
    def test_es_quien_tiene_cartas_en_mas_manos(self):
        manos = _manos_demo(20)
        for m in manos:  # solo el jugador 2 trae sus cartas, como en un historial propio
            m.cartas = [c if a == 2 else () for a, c in enumerate(m.cartas)]
        nombre, stake = B.detectar_jugador_principal(manos)
        self.assertEqual(nombre, simulacion.PERFILES[2])
        self.assertEqual(stake, simulacion.BLIND_GRANDE)

    def test_sin_cartas_visibles(self):
        manos = _manos_demo(5)
        for m in manos:
            m.cartas = [() for _ in m.cartas]
        self.assertIsNone(B.detectar_jugador_principal(manos))


class TestPanelWeb(unittest.TestCase):
    """Criterio de aceptación del plan: el informe se genera solo al cargar y sus cifras coinciden con las del panel."""

    @classmethod
    def setUpClass(cls):
        import web
        cls.web = web
        cls.almacen = web.Almacen()
        cls.almacen.demo(150)
        cls.jugador = cls.almacen.estado()["jugador_principal"]

    def _esperar(self, stake=None, limite=120):
        t = time.time()
        while time.time() - t < limite:
            d = self.almacen.bloques(self.jugador, stake)
            if d["estado"] != "calculando":
                return d
            time.sleep(0.5)
        self.fail("el informe no terminó")

    def test_se_genera_solo_al_cargar(self):
        self.assertIsNotNone(self.jugador)
        self.assertTrue(self.almacen._bloques)  # ya hay un cálculo en marcha o terminado sin que nadie lo pida

    def test_cifras_iguales_a_las_del_panel(self):
        d = self._esperar()
        self.assertEqual(d["estado"], "listo")
        panel = self.almacen.jugador({"jugador": self.jugador, "stake": None})["stats"]
        inf = d["informes"][0]
        self.assertEqual(inf["manos"], panel["manos"])
        self.assertAlmostEqual(inf["bb100"], panel["bb100"], places=9)
        self.assertAlmostEqual(inf["ic95"], panel["ic95"], places=9)

    def test_json_serializable(self):
        import json
        d = self._esperar()
        json.dumps(d, allow_nan=False)
        self.assertIn("texto", d)
        self.assertIn("evolucion", d)

    def test_una_carga_nueva_descarta_el_informe_viejo(self):
        a = self.web.Almacen()
        a.demo(60, semilla=1)
        gen = a._generacion
        viejas = set(a._bloques)
        a.demo(60, semilla=2)
        self.assertEqual(a._generacion, gen + 1)
        # tras la recarga solo existe el cálculo nuevo, en estado "calculando" o ya terminado
        self.assertEqual(set(a._bloques), viejas)
        self.assertIn(next(iter(a._bloques.values()))["estado"], ("calculando", "listo"))
        # un hilo viejo que termina tarde no pisa el estado: lo prueba la guarda por generación
        a._calcular_bloques(a.manos, gen, *next(iter(viejas)))
        self.assertIn(next(iter(a._bloques.values()))["estado"], ("calculando", "listo"))
        self.assertNotEqual(a._generacion, gen)

    def test_jugador_inexistente(self):
        with self.assertRaises(ValueError):
            self.almacen.bloques("nadie", None)


if __name__ == "__main__":
    unittest.main()
