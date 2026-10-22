import unittest

from poker_analisis.cartas import parsear_cartas
from poker_analisis.equity_rangos import combinaciones_de_clave, equity_contra_modelo, equity_contra_rango
from poker_analisis.rangos import CLAVES, PRIOR, ModeloRangos


class TestCombinaciones(unittest.TestCase):
    def test_cantidad_por_tipo_y_total(self):
        self.assertEqual(len(combinaciones_de_clave("AA")), 6)
        self.assertEqual(len(combinaciones_de_clave("AKs")), 4)
        self.assertEqual(len(combinaciones_de_clave("AKo")), 12)
        self.assertEqual(sum(len(combinaciones_de_clave(c)) for c in CLAVES), 1326)

    def test_suited_comparte_palo_y_offsuit_no(self):
        self.assertTrue(all(a.palo == b.palo for a, b in combinaciones_de_clave("T9s")))
        self.assertTrue(all(a.palo != b.palo for a, b in combinaciones_de_clave("T9o")))

    def test_clave_invalida(self):
        with self.assertRaises(ValueError):
            combinaciones_de_clave("XX")


class TestEquityContraRango(unittest.TestCase):
    def test_reyes_contra_ases(self):
        # Referencia publicada: KK contra AA gana ~18 %.
        r = equity_contra_rango(parsear_cartas("Kh Kd"), {"AA": 1.0}, iteraciones=8000, semilla=3)
        self.assertAlmostEqual(r.equity, 0.18, delta=0.03)

    def test_ases_contra_reyes(self):
        r = equity_contra_rango(parsear_cartas("Ah Ad"), {"KK": 1.0}, iteraciones=8000, semilla=3)
        self.assertAlmostEqual(r.equity, 0.82, delta=0.03)

    def test_rango_completo_equivale_a_mano_aleatoria(self):
        # Con el prior (todas las manos según sus combinaciones), AA gana ~85 %.
        r = equity_contra_rango(parsear_cartas("As Ad"), PRIOR, iteraciones=8000, semilla=3)
        self.assertAlmostEqual(r.equity, 0.85, delta=0.03)

    def test_cartas_conocidas_bloquean_combinaciones(self):
        # Con As Ad en la mano solo queda AhAc: un único rival posible, equity cerca de 50 %.
        r = equity_contra_rango(parsear_cartas("As Ad"), {"AA": 1.0}, iteraciones=4000, semilla=3)
        self.assertAlmostEqual(r.equity, 0.5, delta=0.04)

    def test_rango_sin_combinaciones_compatibles(self):
        with self.assertRaises(ValueError):
            equity_contra_rango(parsear_cartas("As Ad"), {"AA": 1.0}, parsear_cartas("Ah Ac 2d"), iteraciones=10)

    def test_peso_negativo_y_pesos_cero(self):
        with self.assertRaises(ValueError):
            equity_contra_rango(parsear_cartas("As Ad"), {"KK": -1.0}, iteraciones=10)
        with self.assertRaises(ValueError):
            equity_contra_rango(parsear_cartas("As Ad"), {"KK": 0.0}, iteraciones=10)

    def test_reproducible_con_semilla(self):
        args = (parsear_cartas("Qs Jd"), {"AKs": 2.0, "TT": 1.0})
        a = equity_contra_rango(*args, iteraciones=500, semilla=11)
        b = equity_contra_rango(*args, iteraciones=500, semilla=11)
        self.assertEqual(a.equity, b.equity)

    def test_tablero_completo_es_determinista(self):
        # Escalera real en el tablero: empate contra cualquier mano.
        r = equity_contra_rango(parsear_cartas("2c 3d"), {"22": 1.0}, parsear_cartas("As Ks Qs Js Ts"), iteraciones=50)
        self.assertEqual(r.equity, 0.5)


class TestEquityContraModelo(unittest.TestCase):
    def test_posterior_concentrado_en_ases_baja_la_equity(self):
        m = ModeloRangos(k=5.0)
        for c in CLAVES:
            if c == "AA":
                m._mano[("X", c, "abre")]["raise"] += 30
                m._perfil[("X", "abre")]["raise"] += 30
            else:
                m._mano[("X", c, "abre")]["fold"] += 20
                m._perfil[("X", "abre")]["fold"] += 20
        mano = parsear_cartas("Kh Kd")
        contra_ases = equity_contra_modelo(m, "X", [("abre", "raise")], mano, iteraciones=3000, semilla=5)
        sin_info = equity_contra_modelo(m, "X", [], mano, iteraciones=3000, semilla=5)
        self.assertLess(contra_ases.equity, sin_info.equity - 0.2)


if __name__ == "__main__":
    unittest.main()
