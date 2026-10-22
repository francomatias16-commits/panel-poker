import unittest

from poker_analisis.cartas import Mazo
from poker_analisis.estadisticas import calcular
from poker_analisis.motor import jugar_mano

CHECK = ("cc", None)
FOLD = ("f", None)


def politica(preflop, flop):
    """Política por calle: `preflop` y `flop` son listas de acciones que se consumen en orden."""
    colas = {"preflop": list(preflop), "flop": list(flop)}

    def decidir(v):
        cola = colas.get(v.calle)
        if cola:
            return cola.pop(0)
        return CHECK

    return decidir


def stats(politicas, bb=2):
    r = jugar_mano([200, 200, 200], 0, 1, 2, politicas, Mazo(semilla=7))
    return {s.nombre: s for s in calcular([r], ["BTN", "SB", "BB"], bb=bb)}


class TestCbet(unittest.TestCase):
    def test_cbet_y_fold_to_cbet(self):
        # BTN sube, SB se retira, BB iguala. En el flop BB chequea, BTN apuesta y BB se retira.
        s = stats([
            politica([("cbr", 6)], [("cbr", 8)]),
            politica([FOLD], []),
            politica([CHECK], [CHECK, FOLD]),
        ])
        self.assertEqual(s["BTN"].cbet, 1.0)
        self.assertEqual(s["BB"].fold_cbet, 1.0)
        self.assertIsNone(s["SB"].cbet)
        self.assertIsNone(s["SB"].fold_cbet)

    def test_agresor_que_chequea_no_hace_cbet(self):
        s = stats([
            politica([("cbr", 6)], [CHECK]),
            politica([FOLD], []),
            politica([CHECK], [CHECK]),
        ])
        self.assertEqual(s["BTN"].cbet, 0.0)
        self.assertIsNone(s["BB"].fold_cbet)

    def test_apuesta_previa_del_rival_quita_la_oportunidad(self):
        # BB apuesta primero (donk): BTN ya no tiene oportunidad de c-bet.
        s = stats([
            politica([("cbr", 6)], [FOLD]),
            politica([FOLD], []),
            politica([CHECK], [("cbr", 4)]),
        ])
        self.assertIsNone(s["BTN"].cbet)
        self.assertIsNone(s["BB"].fold_cbet)

    def test_call_ante_cbet_cuenta_oportunidad_sin_fold(self):
        s = stats([
            politica([("cbr", 6)], [("cbr", 8)]),
            politica([FOLD], []),
            politica([CHECK], [CHECK, CHECK]),
        ])
        self.assertEqual(s["BB"].fold_cbet, 0.0)

    def test_subida_sobre_la_cbet_cierra_la_ventana(self):
        # SB y BB igualan preflop. Flop: SB chequea, BB chequea, BTN apuesta, SB sube,
        # BB enfrenta una subida (no una c-bet) y no cuenta como oportunidad.
        s = stats([
            politica([("cbr", 6)], [("cbr", 8)]),
            politica([CHECK], [CHECK, ("cbr", 24)]),
            politica([CHECK], [CHECK, FOLD]),
        ])
        self.assertEqual(s["BTN"].cbet, 1.0)
        self.assertEqual(s["SB"].fold_cbet, 0.0)
        self.assertIsNone(s["BB"].fold_cbet)

    def test_quien_no_vio_el_flop_no_tiene_oportunidad(self):
        s = stats([
            politica([("cbr", 6)], []),
            politica([FOLD], []),
            politica([FOLD], []),
        ])
        self.assertIsNone(s["BTN"].cbet)


if __name__ == "__main__":
    unittest.main()
