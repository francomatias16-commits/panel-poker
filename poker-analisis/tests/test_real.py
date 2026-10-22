import os
import unittest

from poker_analisis.real import desde_phh

RUTA = os.path.join(os.path.dirname(__file__), "fixtures", "pluribus_ejemplo.phh")


def cargar():
    with open(RUTA, encoding="utf-8") as f:
        return desde_phh(f.read())


class TestManoRealPluribus(unittest.TestCase):
    """Mano real del dataset PHH de Pluribus (jugadores profesionales humanos y Pluribus)."""

    def setUp(self):
        self.mano = cargar()

    def test_asientos_y_boton_se_derivan_de_las_ciegas(self):
        self.assertEqual((self.mano.sb, self.mano.bb), (0, 1))
        self.assertEqual(self.mano.boton, 5)  # el botón está justo antes del small blind

    def test_nombres_vienen_del_archivo(self):
        self.assertEqual(self.mano.nombres[0], "Bill")
        self.assertEqual(self.mano.nombres[5], "MrOrange")

    def test_netos_conservan_fichas(self):
        self.assertEqual(sum(self.mano.neto), 0)
        self.assertEqual(self.mano.neto[0], -100)  # Bill pierde el small blind de 50 más un call
        self.assertEqual(self.mano.neto[1], 100)  # MrBlue gana

    def test_call_de_small_blind_tiene_monto_y_check_de_big_blind_no(self):
        preflop = [e for e in self.mano.eventos if e.calle == "preflop" and e.jugador is not None]
        limp_sb = next(e for e in preflop if e.jugador == 1 and e.tipo == "cc")
        check_bb = next(e for e in preflop if e.jugador == 2 and e.tipo == "cc")
        self.assertEqual(limp_sb.monto, 50)  # el SB iguala 50 para completar la apuesta
        self.assertIsNone(check_bb.monto)  # el BB no paga nada: es un check

    def test_cartas_de_todos_los_jugadores_son_conocidas(self):
        self.assertTrue(all(None not in self.mano.cartas[s] for s in range(6)))
        self.assertEqual(len(self.mano.cartas[0]), 2)

    def test_tablero_completo_y_showdown(self):
        self.assertEqual(len(self.mano.tablero), 5)
        self.assertGreaterEqual(len(self.mano.llegaron_showdown), 2)


if __name__ == "__main__":
    unittest.main()
