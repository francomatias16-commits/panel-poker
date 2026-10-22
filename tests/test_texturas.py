import unittest

from poker_analisis.cartas import parsear_cartas as pc
from poker_analisis.texturas import tamano_sugerido, textura


class TestTexturas(unittest.TestCase):
    def test_tableros_conocidos(self):
        self.assertEqual(textura(pc("Ks 7d 2c"))["humedad"], "seca")
        self.assertEqual(textura(pc("Jh Th 9s"))["humedad"], "media")  # conectado pero de dos palos
        self.assertEqual(textura(pc("Jh Th 9h"))["humedad"], "mojada")
        self.assertEqual(textura(pc("8h 7h 6h"))["humedad"], "mojada")
        self.assertEqual(textura(pc("Qs Qd 4c"))["humedad"], "seca")
        self.assertEqual(textura(pc("Ah 8h 3c"))["humedad"], "seca")
        self.assertEqual(textura(pc("9h 8d 3c"))["humedad"], "seca")
        self.assertEqual(textura(pc("9h 8d 6c"))["humedad"], "media")

    def test_rasgos(self):
        t = textura(pc("Ks Kd 2c"))
        self.assertTrue(t["pareado"])
        self.assertFalse(t["monocolor"])
        self.assertTrue(textura(pc("2h 9h Kh"))["monocolor"])
        self.assertEqual(textura(pc("As 2d 3c"))["conexion"], 3)  # el as cuenta como bajo

    def test_tamano_crece_con_la_humedad(self):
        seca = tamano_sugerido(pc("Ks 7d 2c"))["fraccion"]
        media = tamano_sugerido(pc("9h 8d 6c"))["fraccion"]
        mojada = tamano_sugerido(pc("8h 7h 6h"))["fraccion"]
        self.assertLess(seca, media)
        self.assertLess(media, mojada)
        self.assertGreater(tamano_sugerido(pc("8h 7h 6h 2c"))["fraccion"], mojada)

    def test_tablero_invalido(self):
        with self.assertRaises(ValueError):
            textura(pc("Ks 7d"))


if __name__ == "__main__":
    unittest.main()


class TestGuiaUsaTextura(unittest.TestCase):
    def test_apuesta_mas_chica_en_tablero_seco_que_en_mojado(self):
        from poker_analisis.guia import analisis_puntual
        riv = [{"top": 100}]
        seco = analisis_puntual(pc("As Ad"), pc("Ks 7d 2c"), 10, 0, 1, riv, iteraciones=400)
        moj = analisis_puntual(pc("As Ad"), pc("8h 7h 6c"), 10, 0, 1, riv, iteraciones=400)
        self.assertEqual(seco["accion"], "bet")
        self.assertEqual(moj["accion"], "bet")
        self.assertLess(seco["hasta"], moj["hasta"])
        self.assertTrue(any("Tablero" in r for r in seco["razones"]))


class TestRealizacion(unittest.TestCase):
    def test_factor(self):
        from poker_analisis.guia import realizacion
        self.assertEqual(realizacion("river", "BB", 3), 1.0)  # no quedan calles
        self.assertGreater(realizacion("flop", "BTN", 1), realizacion("flop", "BB", 1))
        self.assertGreater(realizacion("flop", "BB", 1), realizacion("flop", "BB", 4))
        self.assertGreater(realizacion("turn", "BB", 1), realizacion("flop", "BB", 1))
        self.assertGreaterEqual(realizacion("preflop", "BB", 5), 0.5)

    def test_ev_realizado_en_la_guia(self):
        from poker_analisis.guia import analisis_puntual
        a = analisis_puntual(pc("Ks Qs"), pc("Jh 2d 7c"), 10, 5, 1, [{"top": 30}], pos="BB", iteraciones=400)
        self.assertLess(a["ev_igualar_realizado"], a["ev_igualar"])
        r = analisis_puntual(pc("Ks Qs"), pc("Jh 2d 7c 3s 9d"), 10, 5, 1, [{"top": 30}], pos="BB", iteraciones=400)
        self.assertEqual(r["ev_igualar_realizado"], r["ev_igualar"])
        self.assertIsNone(analisis_puntual(pc("Ks Qs"), pc("Jh 2d 7c"), 10, 0, 1, [{"top": 30}], iteraciones=200)["ev_igualar_realizado"])
