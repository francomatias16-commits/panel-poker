"""Verificación exhaustiva: todas las manos de 5 cartas contra frecuencias combinatorias.

Es una prueba lenta (≈2,6 millones de manos). Se ejecuta con:
    python -m unittest tests.test_frecuencias
"""

import unittest
from collections import Counter
from itertools import combinations

from poker_analisis.cartas import Carta, PALOS, RANGOS
from poker_analisis.evaluador import evaluar_cinco, nombre_categoria

# Conteos teóricos de manos de 5 cartas (Hold'em estándar, sin comodines).
FRECUENCIAS_ESPERADAS = {
    "Escalera de color": 40,
    "Póker": 624,
    "Full": 3744,
    "Color": 5108,
    "Escalera": 10200,
    "Trío": 54912,
    "Doble par": 123552,
    "Par": 1098240,
    "Carta alta": 1302540,
}


class TestFrecuenciasExhaustivas(unittest.TestCase):
    def test_todas_las_manos_de_cinco_cartas(self):
        mazo = [Carta(v, p) for p in PALOS for v in range(2, 15)]
        conteo = Counter()
        total = 0
        for combo in combinations(mazo, 5):
            conteo[nombre_categoria(evaluar_cinco(combo))] += 1
            total += 1

        self.assertEqual(total, 2_598_960)
        self.assertEqual(dict(conteo), FRECUENCIAS_ESPERADAS)


if __name__ == "__main__":
    unittest.main()
