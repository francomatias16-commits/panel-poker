import unittest
from fractions import Fraction

from poker_analisis.cartas import parsear_cartas
from poker_analisis.equity import equity, outs, probabilidad_alcanzar_categoria


class TestEquityDeterminista(unittest.TestCase):
    """Tableros completos y rivales fijos: no hay azar, el resultado es exacto."""

    def test_gana_con_mejor_par_en_river(self):
        r = equity(parsear_cartas("As Ad"), parsear_cartas("Kc 9d 7h 2s 3c"),
                   rivales_conocidos=[parsear_cartas("Kd Qh")], n_rivales_aleatorios=0,
                   iteraciones=10)
        self.assertEqual(r.equity, 1.0)

    def test_empate_reparte_en_partes_iguales(self):
        # Escalera real en el tablero: ambos jugadores empatan.
        r = equity(parsear_cartas("2c 3d"), parsear_cartas("As Ks Qs Js Ts"),
                   rivales_conocidos=[parsear_cartas("2h 3h")], n_rivales_aleatorios=0,
                   iteraciones=10)
        self.assertEqual(r.equity, 0.5)

    def test_pierde_en_river(self):
        r = equity(parsear_cartas("2c 3d"), parsear_cartas("Ks Qs Js 9d 8c"),
                   rivales_conocidos=[parsear_cartas("Ah Kd")], n_rivales_aleatorios=0,
                   iteraciones=10)
        self.assertEqual(r.equity, 0.0)

    def test_cartas_repetidas_se_rechazan(self):
        with self.assertRaises(ValueError):
            equity(parsear_cartas("As Ad"), parsear_cartas("As 9d 7h"), iteraciones=10)


class TestEquityMonteCarlo(unittest.TestCase):
    """Valores de referencia conocidos, con tolerancia estadística."""

    def test_ases_contra_mano_aleatoria(self):
        # Referencia publicada: pocket aces contra una mano al azar gana ~85 %.
        r = equity(parsear_cartas("As Ad"), iteraciones=20_000, semilla=7)
        self.assertAlmostEqual(r.equity, 0.852, delta=0.015)

    def test_ases_contra_reyes(self):
        # Referencia publicada: AA contra KK preflop gana ~82 %.
        r = equity(parsear_cartas("As Ad"), rivales_conocidos=[parsear_cartas("Kc Kh")],
                   n_rivales_aleatorios=0, iteraciones=20_000, semilla=7)
        self.assertAlmostEqual(r.equity, 0.82, delta=0.015)

    def test_reproducible_con_semilla(self):
        a = equity(parsear_cartas("Ah Kh"), iteraciones=2000, semilla=99)
        b = equity(parsear_cartas("Ah Kh"), iteraciones=2000, semilla=99)
        self.assertEqual(a.equity, b.equity)

    def test_intervalo_contiene_la_estimacion(self):
        r = equity(parsear_cartas("Qs Qd"), iteraciones=2000, semilla=5)
        lo, hi = r.intervalo_95
        self.assertLessEqual(lo, r.equity)
        self.assertGreaterEqual(hi, r.equity)


class TestProbabilidadExacta(unittest.TestCase):
    def test_proyecto_de_color_en_flop(self):
        # 4 corazones entre mano y flop: 9 outs. P(color o mejor, en turn o river)
        # = 1 - C(38,2)/C(47,2) = 378/1081.
        p = probabilidad_alcanzar_categoria(
            parsear_cartas("Ah Kh"), parsear_cartas("Qh 7h 2c"), categoria=5
        )
        self.assertAlmostEqual(p, float(Fraction(378, 1081)), places=10)

    def test_ya_tiene_la_categoria(self):
        p = probabilidad_alcanzar_categoria(
            parsear_cartas("As Ad"), parsear_cartas("Ac 7h 2s"), categoria=3
        )
        self.assertEqual(p, 1.0)


class TestOuts(unittest.TestCase):
    def test_outs_de_color_en_turn(self):
        # 4 corazones en turn: 9 cartas de corazón restantes son outs para color.
        restantes = outs(parsear_cartas("Ah Kh"), parsear_cartas("Qh 7h 2c 9d"), categoria=5)
        self.assertEqual(len(restantes), 9)
        self.assertTrue(all(c.palo == "h" for c in restantes))

    def test_sin_outs_si_ya_tiene_la_categoria(self):
        self.assertEqual(
            outs(parsear_cartas("As Ad"), parsear_cartas("Ac Ks 2h"), categoria=3), []
        )

    def test_flop_o_turn_obligatorio(self):
        with self.assertRaises(ValueError):
            probabilidad_alcanzar_categoria(parsear_cartas("As Ad"), [], categoria=1)


if __name__ == "__main__":
    unittest.main()
