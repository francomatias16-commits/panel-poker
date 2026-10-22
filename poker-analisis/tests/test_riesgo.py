import unittest

from poker_analisis.riesgo import (
    bankroll_kelly, max_drawdown, prob_ruina_analitica, prob_ruina_simulada, resumen,
)


class TestRiesgo(unittest.TestCase):
    def test_resumen_en_bb_por_100(self):
        r = resumen([1.0, -1.0, 1.0, -1.0])
        self.assertAlmostEqual(r["winrate_bb100"], 0.0)
        self.assertGreater(r["desvio_bb100"], 0)

    def test_max_drawdown(self):
        self.assertEqual(max_drawdown([5, -3, -4, 10, -2]), 7)
        self.assertEqual(max_drawdown([1, 1, 1]), 0)

    def test_ruina_analitica_casos_limite(self):
        self.assertEqual(prob_ruina_analitica(-1, 50, 1000), 1.0)
        self.assertEqual(prob_ruina_analitica(5, 50, 0), 1.0)
        chica = prob_ruina_analitica(5, 80, 2000)
        grande = prob_ruina_analitica(5, 80, 4000)
        self.assertLess(grande, chica)

    def test_ruina_simulada_reproducible_y_monotona(self):
        netos = [2, -1, -1, 3, -2, 1, -1, 2] * 10
        a = prob_ruina_simulada(netos, 20, 300, 300, semilla=1)
        self.assertEqual(a, prob_ruina_simulada(netos, 20, 300, 300, semilla=1))
        self.assertLessEqual(prob_ruina_simulada(netos, 200, 300, 300, semilla=1), a)

    def test_kelly(self):
        self.assertIsNone(bankroll_kelly(-2, 80))
        k = bankroll_kelly(5, 80)
        self.assertAlmostEqual(k, 80 ** 2 / 5)
        self.assertAlmostEqual(bankroll_kelly(5, 80, 0.5), 2 * k)
        with self.assertRaises(ValueError):
            bankroll_kelly(5, 80, 0)


if __name__ == "__main__":
    unittest.main()
