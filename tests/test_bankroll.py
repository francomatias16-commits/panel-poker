"""Riesgo y bankroll con incertidumbre propagada (Fase 4): contraste con fórmulas exactas del movimiento browniano,
propiedades de monotonía, casos límite y la regla de cambio de stake."""
import math
import statistics
import unittest

from poker_analisis import bankroll as K
from poker_analisis.riesgo import bankroll_kelly, prob_ruina_analitica


def serie(media, desvio=1.0, n=1000):
    """Serie determinista con la media y el desvío (de muestra) indicados, en bb por mano."""
    base = [media + desvio, media - desvio] * (n // 2)
    f = desvio / statistics.stdev(base)
    return [media + (x - media) * f for x in base]


class TestMuestra(unittest.TestCase):
    def test_estadisticos(self):
        m = K.muestra(serie(0.05, 1.0, 1000))
        self.assertAlmostEqual(m.media, 0.05)
        self.assertAlmostEqual(m.desvio, 1.0)
        self.assertAlmostEqual(m.winrate_bb100, 5.0)
        self.assertAlmostEqual(m.desvio_bb100, 10.0)
        lo, hi = m.ic95_bb100
        self.assertAlmostEqual(hi - 5.0, 5.0 - lo)
        self.assertAlmostEqual(hi - lo, 2 * 1.959964 * 100 / math.sqrt(1000), places=6)

    def test_pocas_manos(self):
        with self.assertRaises(ValueError):
            K.muestra([1.0, -1.0] * 14)

    def test_sin_variacion(self):
        with self.assertRaises(ValueError):
            K.muestra([0.5] * 100)

    def test_probabilidad_de_winrate_positivo(self):
        self.assertAlmostEqual(K.muestra(serie(0.0)).prob_winrate_positivo, 0.5, places=9)
        self.assertGreater(K.muestra(serie(0.2)).prob_winrate_positivo, 0.999)


class TestParametros(unittest.TestCase):
    def test_los_sorteos_se_centran_en_lo_observado(self):
        import random
        m = K.muestra(serie(0.05, 1.0, 1000))
        pars = K.sortear_parametros(m, 6000, random.Random(3))
        self.assertAlmostEqual(statistics.fmean(p[0] for p in pars), 0.05, delta=0.003)
        self.assertAlmostEqual(statistics.stdev(p[0] for p in pars), m.error, delta=0.003)
        self.assertAlmostEqual(statistics.fmean(p[1] for p in pars), 1.0, delta=0.01)

    def test_mas_manos_menos_incertidumbre(self):
        import random
        chica = K.sortear_parametros(K.muestra(serie(0.05, 1.0, 100)), 3000, random.Random(1))
        grande = K.sortear_parametros(K.muestra(serie(0.05, 1.0, 10000)), 3000, random.Random(1))
        self.assertGreater(statistics.stdev(p[0] for p in chica), 5 * statistics.stdev(p[0] for p in grande))


class TestRuina(unittest.TestCase):
    def test_formula_exacta(self):
        self.assertAlmostEqual(K.ruina_dado(0.05, 1.0, 10), math.exp(-1.0))
        self.assertEqual(K.ruina_dado(-0.01, 1.0, 100), 1.0)
        self.assertEqual(K.ruina_dado(0.05, 1.0, 0), 1.0)

    def test_coincide_con_riesgo_py(self):
        self.assertAlmostEqual(K.ruina_dado(0.05, 0.8, 300), prob_ruina_analitica(5.0, 8.0, 300))

    def test_con_estimado_es_lo_que_calcula_riesgo_py(self):
        s = serie(0.05, 1.0, 1000)
        m = K.muestra(s)
        r = K.ruina(s, 80)
        self.assertAlmostEqual(r.con_estimado, prob_ruina_analitica(m.winrate_bb100, m.desvio_bb100, 80))

    def test_extremos_ordenados_y_predictiva_en_rango(self):
        r = K.ruina(serie(0.1, 1.0, 1000), 50)
        self.assertLess(r.con_winrate_alto, r.con_estimado)
        self.assertLess(r.con_estimado, r.con_winrate_bajo)
        self.assertGreater(r.predictiva, r.con_winrate_alto)
        self.assertLessEqual(r.predictiva, 1.0)

    def test_la_predictiva_supera_a_la_cuenta_con_el_winrate_observado_cuando_hay_dudas(self):
        # Winrate observado de 5 bb/100 con solo 1000 manos: el IC95 % llega a valores negativos.
        r = K.ruina(serie(0.05, 1.0, 1000), 100)
        self.assertGreater(r.predictiva, 10 * r.con_estimado)

    def test_nunca_baja_de_la_probabilidad_de_winrate_negativo(self):
        s = serie(0.05, 1.0, 1000)
        piso = 1 - K.muestra(s).prob_winrate_positivo
        self.assertGreaterEqual(K.ruina(s, 1e9).predictiva, piso - 0.02)

    def test_monotona_en_el_bankroll(self):
        s = serie(0.1, 1.0, 1000)
        r = [K.ruina(s, b).predictiva for b in (10, 50, 200, 1000)]
        self.assertEqual(r, sorted(r, reverse=True))

    def test_reproducible(self):
        s = serie(0.1, 1.0, 400)
        self.assertEqual(K.ruina(s, 60, semilla=5).predictiva, K.ruina(s, 60, semilla=5).predictiva)


class TestBankrollRequerido(unittest.TestCase):
    def test_alcanza_el_objetivo(self):
        s = serie(0.2, 1.0, 2000)
        b = K.bankroll_requerido(s, 0.05)
        self.assertIsNotNone(b)
        self.assertAlmostEqual(K.ruina(s, b).predictiva, 0.05, delta=0.002)

    def test_objetivo_mas_exigente_pide_mas(self):
        s = serie(0.2, 1.0, 2000)
        self.assertGreater(K.bankroll_requerido(s, 0.01), K.bankroll_requerido(s, 0.05))

    def test_muestra_chica_no_alcanza(self):
        # 1 bb/100 con 200 manos: la probabilidad de winrate negativo ronda el 44 %.
        self.assertIsNone(K.bankroll_requerido(serie(0.01, 1.0, 200), 0.05))

    def test_objetivo_invalido(self):
        with self.assertRaises(ValueError):
            K.bankroll_requerido(serie(0.1), 0.0)


class TestSimulacion(unittest.TestCase):
    def test_drawdown_medio_sin_deriva_coincide_con_la_formula_exacta(self):
        # Para un movimiento browniano sin deriva: E[mayor drawdown] = sqrt(pi/2) * sigma * sqrt(T).
        s = K.simular(serie(0.0, 1.0, 1000), 10_000, 2000, incertidumbre=False)
        teorico = math.sqrt(math.pi / 2) * 1.0 * math.sqrt(10_000)
        self.assertAlmostEqual(s.drawdown_medio / teorico, 1.0, delta=0.06)

    def test_ruina_finita_coincide_con_la_analitica_y_no_depende_del_bloque(self):
        s = serie(0.05, 1.0, 1000)
        m = K.muestra(s)
        analitica = K.ruina_dado(m.media, m.desvio, 10)
        for bloque in (50, 100, 1000):
            sim = K.simular(s, 20_000, 2000, bankroll_bb=10, incertidumbre=False, bloque=bloque)
            self.assertAlmostEqual(sim.prob_ruina, analitica, delta=0.05)
            self.assertLessEqual(sim.prob_ruina, analitica + 0.05)  # un horizonte finito no supera al infinito

    def test_ruina_crece_con_el_horizonte(self):
        s = serie(0.0, 1.0, 1000)
        r = [K.simular(s, h, 1500, bankroll_bb=20, incertidumbre=False).prob_ruina for h in (500, 5000, 50_000)]
        self.assertLess(r[0], r[1])
        self.assertLess(r[1], r[2])

    def test_percentiles_ordenados(self):
        s = K.simular(serie(0.05, 1.0, 1000), 20_000, 500)
        d = s.drawdown_percentiles
        self.assertTrue(d[50] <= d[90] <= d[95] <= d[99])
        f = s.resultado_percentiles
        self.assertTrue(f[5] <= f[25] <= f[50] <= f[75] <= f[95])
        self.assertTrue(all(v >= 0 for v in d.values()))

    def test_reproducible(self):
        s = serie(0.05, 1.0, 1000)
        self.assertEqual(K.simular(s, 5000, 200, 30, semilla=4).drawdown_percentiles,
                         K.simular(s, 5000, 200, 30, semilla=4).drawdown_percentiles)

    def test_la_incertidumbre_ensancha_el_abanico_de_resultados(self):
        s = serie(0.05, 1.0, 1000)
        con = K.simular(s, 20_000, 1000, incertidumbre=True).resultado_percentiles
        sin = K.simular(s, 20_000, 1000, incertidumbre=False).resultado_percentiles
        self.assertGreater(con[95] - con[5], 1.3 * (sin[95] - sin[5]))

    def test_sin_bankroll_no_hay_ruina(self):
        self.assertIsNone(K.simular(serie(0.05), 1000, 50).prob_ruina)

    def test_horizonte_que_no_es_multiplo_del_bloque(self):
        s = K.simular(serie(0.05), 1050, 50)
        self.assertEqual(s.horizonte, 1050)

    def test_parametros_invalidos(self):
        with self.assertRaises(ValueError):
            K.simular(serie(0.05), 0, 10)


class TestKelly(unittest.TestCase):
    def test_coincide_con_riesgo_py(self):
        s = serie(0.05, 1.0, 1000)
        m = K.muestra(s)
        k = K.kelly(s, 1.0)
        self.assertAlmostEqual(k.completo_bb, bankroll_kelly(m.winrate_bb100, m.desvio_bb100))
        self.assertAlmostEqual(K.kelly(s, 0.5).fraccion_bb, 2 * k.completo_bb)

    def test_conservador_usa_el_limite_inferior(self):
        s = serie(0.2, 1.0, 2000)
        k = K.kelly(s)
        self.assertGreater(k.conservador_bb, k.completo_bb)  # el límite inferior del winrate es menor: más bankroll

    def test_sin_winrate_positivo(self):
        k = K.kelly(serie(-0.05))
        self.assertIsNone(k.completo_bb)
        self.assertIsNone(k.conservador_bb)

    def test_ic_que_cruza_cero_no_da_kelly_conservador(self):
        self.assertIsNone(K.kelly(serie(0.02, 1.0, 1000)).conservador_bb)

    def test_fraccion_invalida(self):
        for f in (0, 1.5):
            with self.assertRaises(ValueError):
                K.kelly(serie(0.1), f)


class TestDecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Escala realista: 8 bb/100 de winrate, 90 bb/100 de desvío, 50.000 manos.
        cls.ganador = serie(0.08, 9.0, 50_000)
        cls.req = K.bankroll_requerido(cls.ganador)

    def test_el_requerido_es_razonable(self):
        self.assertIsNotNone(self.req)
        self.assertTrue(1000 < self.req < 6000, self.req)  # entre 10 y 60 entradas

    def test_sube_con_bankroll_de_sobra(self):
        d = K.decidir_stake(self.ganador, self.req * 2.2)
        self.assertEqual(d.accion, "subir")
        self.assertGreaterEqual(self.req * 2.2, d.bankroll_para_subir_bb)

    def test_baja_si_la_ruina_supera_el_limite(self):
        d = K.decidir_stake(self.ganador, 300)  # 3 entradas
        self.assertEqual(d.accion, "bajar")
        self.assertGreater(d.ruina_actual, K.RUINA_BAJAR)

    def test_mantiene_en_el_medio(self):
        d = K.decidir_stake(self.ganador, self.req * 1.2)  # cómodo en este stake, no alcanza para el doble
        self.assertEqual(d.accion, "mantener")
        self.assertLessEqual(d.ruina_actual, K.RUINA_OBJETIVO)

    def test_factor_de_stake_cambia_la_exigencia(self):
        self.assertEqual(K.decidir_stake(self.ganador, self.req * 1.5, factor_stake_superior=1.0).accion, "subir")
        self.assertEqual(K.decidir_stake(self.ganador, self.req * 1.5, factor_stake_superior=2.0).accion, "mantener")

    def test_muestra_dudosa_no_asegura_winrate(self):
        dudosa = serie(0.01, 9.0, 200)
        d = K.decidir_stake(dudosa, 100_000)
        self.assertIsNone(d.bankroll_requerido_bb)
        self.assertEqual(d.accion, "bajar" if d.ruina_actual > K.RUINA_BAJAR else "mantener")
        self.assertTrue(d.motivos)

    def test_nunca_sube_sin_poder_asegurar_el_winrate(self):
        for b in (1000, 100_000, 10_000_000):
            self.assertNotEqual(K.decidir_stake(serie(0.01, 9.0, 200), b).accion, "subir")

    def test_perdedor_baja(self):
        self.assertEqual(K.decidir_stake(serie(-0.1, 9.0, 1000), 3000).accion, "bajar")


class TestInforme(unittest.TestCase):
    def test_secciones(self):
        txt = K.formatear(serie(0.1, 1.0, 1000), 3000, horizonte=20_000, trayectorias=200)
        for parte in ("# Riesgo y bankroll", "## Riesgo de ruina", "## Simulación a 20.000 manos", "## Kelly", "## Cambio de stake"):
            self.assertIn(parte, txt)
        self.assertIn("propagan esa incertidumbre", txt)

    def test_usa_las_simulaciones_ya_hechas(self):
        s = serie(0.1, 1.0, 1000)
        sim = K.simular(s, 20_000, 200, 3000)
        sin = K.simular(s, 20_000, 200, 3000, incertidumbre=False)
        self.assertEqual(K.formatear(s, 3000, 20_000, 200, sim=sim, sim_fija=sin), K.formatear(s, 3000, 20_000, 200))

    def test_perdedor_no_tiene_kelly(self):
        txt = K.formatear(serie(-0.05, 1.0, 1000), 3000, horizonte=5000, trayectorias=100)
        self.assertIn("no hay bankroll de Kelly", txt)
        self.assertIn("ninguno alcanza", txt)


class TestPanelWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
        import web
        cls.almacen = web.Almacen()
        cls.almacen.demo(600)

    def test_respuesta_completa_y_serializable(self):
        import json
        r = self.almacen.riesgo({"jugador": "TAG-1", "bankroll_entradas": 30, "horizonte": 20_000})
        json.dumps(r, allow_nan=False)
        self.assertEqual(r["manos"], 600)
        self.assertIn(r["decision"]["accion"], ("subir", "mantener", "bajar"))
        self.assertIn("## Kelly", r["texto"])
        self.assertTrue(0 <= r["ruina"]["predictiva"] <= 1)

    def test_coincide_con_el_modulo(self):
        from poker_analisis import bloques
        netos = [m.neto[a] / m.ciega_grande for m, a in bloques.serie_del_jugador(self.almacen.manos, "TAG-1", 2)]
        r = self.almacen.riesgo({"jugador": "TAG-1", "bankroll_entradas": 30, "horizonte": 20_000})
        self.assertAlmostEqual(r["ruina"]["predictiva"], K.ruina(netos, 3000).predictiva, places=12)
        self.assertAlmostEqual(r["winrate_bb100"], K.muestra(netos).winrate_bb100, places=9)

    def test_datos_invalidos(self):
        for f in ({}, {"jugador": "TAG-1"}, {"jugador": "TAG-1", "bankroll_entradas": -3},
                  {"jugador": "nadie", "bankroll_entradas": 30},
                  {"jugador": "TAG-1", "bankroll_entradas": 30, "horizonte": 5}):
            with self.assertRaises(ValueError):
                self.almacen.riesgo(f)


if __name__ == "__main__":
    unittest.main()
