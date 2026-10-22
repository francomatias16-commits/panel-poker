import unittest

from poker_analisis.cartas import Carta, Mazo, parsear_cartas


class TestCarta(unittest.TestCase):
    def test_parseo_y_representacion(self):
        self.assertEqual(Carta.desde_texto("As"), Carta(14, "s"))
        self.assertEqual(str(Carta.desde_texto("Td")), "Td")

    def test_notacion_invalida(self):
        for texto in ["Xs", "Ax", "A", "AsK"]:
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                Carta.desde_texto(texto)

    def test_parsear_lista(self):
        self.assertEqual(len(parsear_cartas("As Kd 7h")), 3)


class TestMazo(unittest.TestCase):
    def test_mazo_completo_sin_repetidos(self):
        mazo = Mazo(semilla=1)
        cartas = mazo.repartir(52)
        self.assertEqual(len(set(cartas)), 52)
        self.assertEqual(len(mazo), 0)

    def test_semilla_reproducible(self):
        self.assertEqual(Mazo(semilla=42).repartir(7), Mazo(semilla=42).repartir(7))

    def test_exclusion(self):
        excluir = parsear_cartas("As Ks")
        mazo = Mazo(semilla=3, excluir=excluir)
        self.assertEqual(len(mazo), 50)
        restantes = mazo.repartir(50)
        self.assertFalse(set(excluir) & set(restantes))

    def test_repartir_mas_de_lo_disponible(self):
        with self.assertRaises(ValueError):
            Mazo(semilla=1).repartir(53)


if __name__ == "__main__":
    unittest.main()
