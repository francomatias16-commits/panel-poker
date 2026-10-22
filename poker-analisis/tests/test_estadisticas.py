import math
import unittest

from poker_analisis.cartas import Mazo
from poker_analisis.estadisticas import calcular, formatear
from poker_analisis.motor import jugar_mano


def fijo(*acciones):
    pendientes = list(acciones)

    def decidir(v):
        return pendientes.pop(0) if pendientes else ("cc", None)

    return decidir


class TestEstadisticasEscenarioConocido(unittest.TestCase):
    def setUp(self):
        # Botón 0: UTG (seat 0) sube a 6, SB (seat 1) re-sube a 18, BB (seat 2) se retira,
        # seat 0 se retira ante la re-subida. Gana seat 1 sin showdown.
        def utg(v):
            return ("cbr", 6) if v.apuesta_actual <= 2 else ("f", None)

        def sb(v):
            return ("cbr", 18) if v.apuesta_actual == 6 else ("f", None)

        self.politicas = [utg, sb, fijo(("f", None))]
        self.resultado = jugar_mano([200, 200, 200], 0, 1, 2, self.politicas, Mazo(semilla=5))
        self.stats = {s.nombre: s for s in calcular([self.resultado], ["UTG", "SB", "BB"], bb=2)}

    def test_vpip_y_pfr(self):
        self.assertEqual(self.stats["UTG"].vpip, 1.0)
        self.assertEqual(self.stats["UTG"].pfr, 1.0)
        self.assertEqual(self.stats["BB"].vpip, 0.0)

    def test_3bet_del_jugador_que_re_sube(self):
        self.assertEqual(self.stats["SB"].tres_bet, 1.0)

    def test_bb100_del_ganador(self):
        # El SB gana el bote y su neto sale del motor; la métrica debe ser neto / bb * 100.
        neto_sb = self.resultado.neto[1]
        self.assertAlmostEqual(self.stats["SB"].bb100, 100 * neto_sb / 2)

    def test_bb100_sin_error_con_una_sola_mano(self):
        self.assertTrue(math.isnan(self.stats["SB"].bb100_ic95))

    def test_tabla_se_formatea(self):
        texto = formatear(list(self.stats.values()))
        self.assertIn("UTG", texto)
        self.assertIn("bb/100", texto)


class TestEstadisticasVolumen(unittest.TestCase):
    def test_muchas_manos_producen_metricas_finitas(self):
        from poker_analisis.bots import BotAleatorio

        resultados = []
        for h in range(200):
            politicas = [BotAleatorio(semilla=h * 3 + i) for i in range(3)]
            resultados.append(jugar_mano([100, 100, 100], h % 3, 1, 2, politicas, Mazo(semilla=h)))
        stats = calcular(resultados, ["A", "B", "C"], bb=2)
        for s in stats:
            self.assertEqual(s.manos, 200)
            self.assertTrue(0 <= s.vpip <= 1)
            self.assertTrue(0 <= s.pfr <= s.vpip)
            self.assertTrue(math.isfinite(s.bb100))
            self.assertTrue(s.bb100_ic95 > 0)


if __name__ == "__main__":
    unittest.main()
