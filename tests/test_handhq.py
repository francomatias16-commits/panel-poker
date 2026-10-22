"""Pruebas del soporte de HandHQ: netos con winnings, registros inconsistentes, decimales y multimano."""
import unittest

from poker_analisis.phh import ErrorPHH, parsear_mano
from poker_analisis.real import cargar_multimano, desde_phh

# Mano heads-up: el SB (5) se retira, el BB (10) cobra el bote de 15.
MANO_CONSISTENTE = """variant = 'NT'
antes = [0, 0]
blinds_or_straddles = [5, 10]
starting_stacks = [1920, 3660.75]
actions = ['d dh p1 ????', 'd dh p2 ????', 'p2 cc', 'p1 f']
winnings = [0, 15]
"""

# Igual, pero el registro reparte 20 de un bote de 15: inconsistente.
MANO_INCONSISTENTE = MANO_CONSISTENTE.replace("winnings = [0, 15]", "winnings = [0, 20]")

# Apuesta con decimales, como en los datasets en dólares.
MANO_DECIMAL = """variant = 'NT'
antes = [0, 0]
blinds_or_straddles = [0.5, 1]
starting_stacks = [100.5, inf]
actions = ['d dh p1 AsKd', 'd dh p2 ????', 'p1 cbr 3.5', 'p2 f']
winnings = [4.5, 0]
"""


class TestNetoHandHQ(unittest.TestCase):
    def test_neto_es_winnings_menos_lo_invertido(self):
        m = desde_phh(MANO_CONSISTENTE)
        self.assertEqual(m.neto, [-5, 5])
        self.assertEqual(sum(m.neto), 0)

    def test_registro_inconsistente_se_rechaza(self):
        with self.assertRaisesRegex(ErrorPHH, "inconsistente"):
            desde_phh(MANO_INCONSISTENTE)

    def test_stacks_infinitos_y_decimales(self):
        p = parsear_mano(MANO_DECIMAL)
        self.assertEqual(p.stacks_iniciales[1], float("inf"))
        apuesta = [e for e in p.eventos if e.tipo == "cbr"][0]
        self.assertEqual(apuesta.monto, 3.5)

    def test_cbr_entero_queda_como_int(self):
        p = parsear_mano(MANO_CONSISTENTE.replace("p2 cc", "p2 cbr 20"))
        self.assertEqual([e for e in p.eventos if e.tipo == "cbr"][0].monto, 20)
        self.assertIsInstance([e for e in p.eventos if e.tipo == "cbr"][0].monto, int)


class TestCargarMultimano(unittest.TestCase):
    def test_separa_manos_por_encabezado(self):
        texto = "[1]\n" + MANO_CONSISTENTE + "\n[2]\n" + MANO_DECIMAL
        manos = cargar_multimano(texto)
        self.assertEqual(len(manos), 2)
        self.assertEqual(desde_phh(manos[0]).neto, [-5, 5])
        self.assertEqual(parsear_mano(manos[1]).variante, "NT")


if __name__ == "__main__":
    unittest.main()
