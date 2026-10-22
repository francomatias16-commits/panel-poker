import random
import unittest

from poker_analisis.cartas import Mazo
from poker_analisis.motor import construir_botes, jugar_mano
from poker_analisis.bots import BotAleatorio


def politica_fija(*acciones):
    """Política que devuelve una acción por turno y luego hace check/call."""
    pendientes = list(acciones)

    def decidir(v):
        if pendientes:
            return pendientes.pop(0)
        return ("cc", None)

    return decidir


class TestBotes(unittest.TestCase):
    def test_bote_principal_y_laterales(self):
        # Tres jugadores con aportes 100, 50 y 200, nadie retirado.
        botes = construir_botes([100, 50, 200], [False, False, False])
        self.assertEqual(botes, [(150, [0, 1, 2]), (100, [0, 2]), (100, [2])])
        self.assertEqual(sum(m for m, _ in botes), 350)

    def test_retirado_aporta_pero_no_gana(self):
        botes = construir_botes([50, 50, 10], [False, False, True])
        # Los niveles 10 y 50 tienen los mismos elegibles: el total es 110 y nadie retirado gana.
        self.assertEqual(sum(m for m, _ in botes), 110)
        self.assertTrue(all(e == [0, 1] for _, e in botes))


class TestMotorDeterminista(unittest.TestCase):
    def test_todos_se_retiran_y_gana_el_que_apuesta(self):
        # 3 jugadores, botón en 0: UTG = 0, SB = 1, BB = 2.
        politicas = [
            politica_fija(("cbr", 10)),  # UTG sube a 10
            politica_fija(("f", None)),  # SB se retira
            politica_fija(("f", None)),  # BB se retira
        ]
        r = jugar_mano([100, 100, 100], 0, 1, 2, politicas, Mazo(semilla=1))
        self.assertEqual(r.neto, [3, -1, -2])
        self.assertEqual(r.stacks_finales, [103, 99, 98])
        self.assertEqual(r.llegaron_showdown, [])

    def test_todos_igualan_llega_a_showdown_con_tablero_completo(self):
        politicas = [politica_fija() for _ in range(3)]
        r = jugar_mano([100, 100, 100], 0, 1, 2, politicas, Mazo(semilla=2))
        self.assertEqual(len(r.tablero), 5)
        self.assertEqual(len(r.llegaron_showdown), 3)
        self.assertEqual(sum(r.neto), 0)

    def test_posicion_heads_up(self):
        r = jugar_mano([100, 100], 0, 1, 2, [politica_fija(), politica_fija()], Mazo(semilla=3))
        self.assertEqual((r.sb, r.bb), (0, 1))

    def test_stacks_invalidos(self):
        with self.assertRaises(ValueError):
            jugar_mano([100, 0], 0, 1, 2, [politica_fija(), politica_fija()], Mazo(semilla=1))


class TestConservacionDeFichas(unittest.TestCase):
    def test_estres_con_politicas_aleatorias(self):
        """Miles de manos con apuestas, all-in y empates: las fichas nunca se crean ni se pierden."""
        rng = random.Random(2024)
        manos = 2000
        for h in range(manos):
            n = rng.randint(2, 6)
            stacks = [rng.randint(10, 300) for _ in range(n)]
            politicas = [BotAleatorio(semilla=h * 10 + i) for i in range(n)]
            r = jugar_mano(stacks, rng.randrange(n), 1, 2, politicas, Mazo(semilla=h))
            self.assertEqual(sum(r.stacks_finales), sum(stacks))
            self.assertTrue(all(s >= 0 for s in r.stacks_finales))
            if len(r.llegaron_showdown) >= 2:
                self.assertEqual(len(r.tablero), 5)

    def test_todos_igualan_no_generan_ni_pierden_fichas(self):
        rng = random.Random(7)
        for h in range(300):
            n = rng.randint(2, 6)
            stacks = [rng.randint(20, 200) for _ in range(n)]
            r = jugar_mano(stacks, h % n, 1, 2, [politica_fija() for _ in range(n)], Mazo(semilla=h))
            self.assertEqual(sum(r.neto), 0)


if __name__ == "__main__":
    unittest.main()
