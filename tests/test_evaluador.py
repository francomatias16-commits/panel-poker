import unittest

from poker_analisis.cartas import parsear_cartas
from poker_analisis.evaluador import evaluar_cinco, evaluar_mejor, nombre_categoria


def cinco(texto):
    return evaluar_cinco(parsear_cartas(texto))


class TestCategorias(unittest.TestCase):
    def test_categorias_basicas(self):
        casos = {
            "As Kd 9c 5h 2s": "Carta alta",
            "As Ad 9c 5h 2s": "Par",
            "As Ad 9c 9h 2s": "Doble par",
            "As Ad Ac 5h 2s": "Trío",
            "5s 4d 3c 2h As": "Escalera",
            "As Ks 9s 5s 2s": "Color",
            "As Ad Ac 5h 5s": "Full",
            "As Ad Ac Ah 2s": "Póker",
            "9s 8s 7s 6s 5s": "Escalera de color",
        }
        for texto, esperado in casos.items():
            with self.subTest(mano=texto):
                self.assertEqual(nombre_categoria(cinco(texto)), esperado)

    def test_escalera_real_es_escalera_de_color(self):
        self.assertEqual(cinco("As Ks Qs Js Ts"), (8, 14))


class TestDesempates(unittest.TestCase):
    def test_rueda_vale_como_carta_alta_cinco(self):
        self.assertEqual(cinco("As 2d 3c 4h 5s"), (4, 5))
        self.assertLess(cinco("As 2d 3c 4h 5s"), cinco("2s 3d 4c 5h 6s"))

    def test_escalera_de_color_rueda_es_la_mas_baja_de_su_tipo(self):
        self.assertEqual(cinco("As 2s 3s 4s 5s"), (8, 5))

    def test_par_con_kickers(self):
        mejor = cinco("Ah Ad Kc 7h 2s")
        peor = cinco("Ah Ad Qc 7h 2s")
        self.assertGreater(mejor, peor)

    def test_doble_par_desempata_por_kicker(self):
        self.assertGreater(cinco("Ah Ad Kc Kh 2s"), cinco("Ah Ad Qc Qh 2s"))

    def test_full_mas_alto_gana(self):
        self.assertGreater(cinco("Ks Kd Kc 2h 2s"), cinco("Qs Qd Qc Ah Ad"))

    def test_color_compara_todas_las_cartas(self):
        self.assertGreater(cinco("As 9s 7s 5s 3s"), cinco("Ks Qs Js 9s 8s"))

    def test_empate_exacto(self):
        self.assertEqual(cinco("As Kd Qc Jh 9s"), cinco("Ah Ks Qd Jc 9d"))


class TestMejorDeSiete(unittest.TestCase):
    def test_elige_la_mejor_combinacion(self):
        # Mesa con escalera; la mano del jugador no la mejora, pero debe detectarla.
        puntaje = evaluar_mejor(parsear_cartas("5s 6d 7c 8h 9s Ac Kd"))
        self.assertEqual(nombre_categoria(puntaje), "Escalera")

    def test_full_sobre_color(self):
        puntaje = evaluar_mejor(parsear_cartas("Ah Ad Ac Ks Kd 2s 3s"))
        self.assertEqual(nombre_categoria(puntaje), "Full")

    def test_mesa_que_iguala_la_mano(self):
        # Ambos jugadores llegan a la misma escalera con la mesa: empate.
        mesa = "Ts Jd Qc Kh Ah"
        a = evaluar_mejor(parsear_cartas(mesa + " 2c 3d"))
        b = evaluar_mejor(parsear_cartas(mesa + " 2h 3c"))
        self.assertEqual(a, b)

    def test_rango_de_cartas_invalido(self):
        with self.assertRaises(ValueError):
            evaluar_mejor(parsear_cartas("As Ks Qs Js"))
        with self.assertRaises(ValueError):
            evaluar_cinco(parsear_cartas("As Ks Qs Js Ts 9s"))


if __name__ == "__main__":
    unittest.main()


class TestEvaluarMejorRapido(unittest.TestCase):
    """`evaluar_mejor` (directo) debe coincidir siempre con la enumeración de combinaciones."""

    def _comparar(self, mazo, cantidad, muestras, semilla):
        import random

        from poker_analisis.evaluador import evaluar_mejor_referencia

        rng = random.Random(semilla)
        categorias = set()
        for _ in range(muestras):
            mano = rng.sample(mazo, cantidad)
            esperado = evaluar_mejor_referencia(mano)
            self.assertEqual(evaluar_mejor(mano), esperado, [str(c) for c in mano])
            categorias.add(esperado[0])
        return categorias

    def test_mazo_completo_5_6_y_7_cartas(self):
        from poker_analisis.cartas import Mazo

        mazo = Mazo(1).repartir(52)
        for cantidad in (5, 6, 7):
            self._comparar(mazo, cantidad, 3000, semilla=cantidad)

    def test_manos_sesgadas_cubren_todas_las_categorias(self):
        from poker_analisis.cartas import Carta

        categorias = set()
        configuraciones = [
            ([14, 2, 3, 4, 5, 6, 7], "cd"),  # ruedas y escaleras bajas
            ([9, 10, 11, 12, 13, 14], "cd"),  # broadway
            ([2, 3, 4, 5], "cdhs"),           # parejas, tríos y pókers
            ([14, 13, 12, 11, 10, 9], "cdh"),
        ]
        for i, (valores, palos) in enumerate(configuraciones):
            mazo = [Carta(v, p) for v in valores for p in palos]
            categorias |= self._comparar(mazo, 7 if len(mazo) >= 7 else len(mazo), 2500, semilla=10 + i)
        self.assertEqual(categorias, {1, 2, 3, 4, 5, 6, 7, 8})

    def test_casos_conocidos(self):
        casos = {
            "As 2s 3s 4s 5s Kd Kh": (8, 5),  # escalera de color rueda
            "Ah Ad Ac Kd Kh Ks 2c": (6, 14, 13),  # dos tríos: full de ases y reyes
            "9h 9d 5c 5d 2h 2s Ac": (2, 9, 5, 14),  # tres parejas: kicker es el as
            "9h 9d 5c 5d 4h 4s 3c": (2, 9, 5, 4),  # la tercera pareja es el kicker
        }
        for texto, esperado in casos.items():
            self.assertEqual(evaluar_mejor(parsear_cartas(texto)), esperado, texto)
