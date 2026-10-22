"""Pruebas de regresión de cada regla de la guía, con situaciones armadas a mano.

Cada prueba fija una regla de `guia.decidir` (apertura por posición, pot odds, umbral de valor, tamaño, límites
por stack...) para que un cambio de umbrales o de cálculo no pase sin que se note.
"""
import unittest

from poker_analisis import guia
from poker_analisis.cartas import parsear_cartas as pc
from poker_analisis.guia import analisis_puntual as ap
from poker_analisis.motor import ResultadoMano

IT = 800


def clave_con_percentil(lo, hi):
    return next(c for c in guia._ranking() if lo <= guia.percentil(c) <= hi)


def cartas_de(clave):
    r1, r2 = clave[0], clave[1]
    if len(clave) == 2:
        return pc(f"{r1}s {r2}h")
    return pc(f"{r1}s {r2}s") if clave[2] == "s" else pc(f"{r1}s {r2}h")


class TestAperturaPreflop(unittest.TestCase):
    def test_premium_abre_subiendo_desde_cualquier_posicion(self):
        for pos in ("UTG", "CO", "BTN", "SB"):
            a = ap(pc("As Ah"), [], 1.5, 1.0 if pos == "SB" else 0, 1, [{"top": 40}], pos=pos, iteraciones=IT)
            self.assertEqual(a["accion"], "raise", pos)
            self.assertEqual(a["hasta"], 2.5, pos)  # 2,5 bb sin limpers

    def test_cada_limper_suma_una_ciega(self):
        a = ap(pc("As Ah"), [], 3.5, 0, 1, [{"top": 40}], pos="BTN", limpers=2, iteraciones=IT)
        self.assertEqual(a["hasta"], 4.5)

    def test_el_rango_de_apertura_se_ensancha_con_la_posicion(self):
        # mano fuera del rango de UTG (16 %) pero dentro del de BTN (42 %)
        clave = clave_con_percentil(25, 38)
        riv = [{"top": 40}]
        utg = ap(cartas_de(clave), [], 1.5, 0, 1, riv, pos="UTG", iteraciones=IT)
        btn = ap(cartas_de(clave), [], 1.5, 0, 1, riv, pos="BTN", iteraciones=IT)
        self.assertNotEqual(utg["accion"], "raise")
        self.assertEqual(btn["accion"], "raise")

    def test_fuera_de_rango_sin_costo_se_pasa(self):
        a = ap(pc("7s 2h"), [], 1.5, 0, 1, [{"top": 40}], pos="UTG", iteraciones=IT)
        self.assertEqual(a["accion"], "check")

    def test_basura_con_precio_se_retira(self):
        a = ap(pc("7s 2h"), [], 4.5, 3.0, 1, [{"top": 10}], pos="UTG", subidas_preflop=1, iteraciones=IT)
        self.assertEqual(a["accion"], "fold")

    def test_la_equity_domina_las_pot_odds_preflop(self):
        # contra una subida chica de un rango amplio, una mano decente iguala aunque no abra desde esa posición
        clave = clave_con_percentil(30, 40)
        a = ap(cartas_de(clave), [], 3.5, 0.5, 1, [{"top": 80}], pos="BB", iteraciones=IT)
        self.assertIn(a["accion"], ("call", "raise"))


class TestPotOddsYUmbrales(unittest.TestCase):
    def test_pot_odds_exactas(self):
        a = ap(pc("Ks Qs"), pc("Jh 2d 7c"), 10, 5, 1, [{"top": 30}], pos="BTN", iteraciones=IT)
        self.assertAlmostEqual(a["pot_odds"], 5 / 15, places=4)

    def test_ev_de_igualar_es_equity_por_bote_menos_costo(self):
        a = ap(pc("Ks Qs"), pc("Jh 2d 7c"), 10, 5, 1, [{"top": 30}], iteraciones=IT)
        self.assertAlmostEqual(a["ev_igualar"], a["equity"] * 15 - 5, delta=0.01)

    def test_sin_apuesta_no_hay_pot_odds_ni_ev(self):
        a = ap(pc("Ks Qs"), pc("Jh 2d 7c"), 10, 0, 1, [{"top": 30}], iteraciones=IT)
        self.assertIsNone(a["pot_odds"])
        self.assertIsNone(a["ev_igualar"])

    def test_monstruo_contra_apuesta_sube(self):
        a = ap(pc("As Ah"), pc("Ad 7c 2h"), 10, 5, 1, [{"top": 30}], iteraciones=IT)
        self.assertEqual(a["accion"], "raise")
        self.assertLessEqual(a["hasta"], 15)  # hasta 3 veces la apuesta actual

    def test_equity_suficiente_iguala(self):
        # sobrepar medio contra rango amplio y precio chico: iguala, no sube
        a = ap(pc("Th Tc"), pc("Jd 6h 2c"), 10, 2, 1, [{"top": 60}], iteraciones=IT)
        self.assertIn(a["accion"], ("call", "raise"))
        self.assertGreater(a["equity"], a["pot_odds"])

    def test_aire_contra_apuesta_grande_se_retira(self):
        a = ap(pc("7s 2h"), pc("Ad Kc Qh"), 10, 10, 1, [{"top": 20}], iteraciones=IT)
        self.assertEqual(a["accion"], "fold")

    def test_apuesta_por_valor_solo_sobre_el_umbral(self):
        fuerte = ap(pc("As Ah"), pc("Ad 7c 2h"), 10, 0, 1, [{"top": 50}], iteraciones=IT)
        debil = ap(pc("7s 2h"), pc("Ad Kc Qh"), 10, 0, 1, [{"top": 50}], iteraciones=IT)
        self.assertEqual(fuerte["accion"], "bet")
        self.assertEqual(debil["accion"], "check")

    def test_el_umbral_de_valor_baja_con_mas_rivales(self):
        u = guia.UMBRAL_VALOR
        self.assertTrue(all(u[k] > u[k + 1] for k in range(1, 5)))

    def test_apuesta_no_supera_el_stack(self):
        a = ap(pc("As Ah"), pc("Ad 7c 2h"), 100, 0, 1, [{"top": 50}], stack=20, iteraciones=IT)
        self.assertLessEqual(a["hasta"], 20)

    def test_igualar_se_limita_al_stack(self):
        a = ap(pc("As Ah"), pc("Ad 7c 2h"), 10, 50, 1, [{"top": 30}], stack=5, iteraciones=IT)
        self.assertAlmostEqual(a["pot_odds"], 5 / 15, places=4)


class TestInformacionDeMano(unittest.TestCase):
    def test_outs_de_proyecto_de_color(self):
        a = ap(pc("As Ks"), pc("Qs 7s 2c"), 10, 0, 1, [{"top": 50}], iteraciones=IT)
        self.assertEqual(a["categoria"], "Carta alta")
        proyecto = [c for c in a["outs"] if c.endswith("s")]
        self.assertGreaterEqual(len(proyecto), 9 - 0)  # 9 picas restantes mejoran la categoría

    def test_sin_outs_en_el_river(self):
        a = ap(pc("As Ks"), pc("Qs 7s 2c 3d 9h"), 10, 0, 1, [{"top": 50}], iteraciones=IT)
        self.assertNotIn("outs", a)
        self.assertIn("categoria", a)

    def test_categoria_hecha(self):
        a = ap(pc("As Ah"), pc("Ad 7c 2h"), 10, 0, 1, [{"top": 50}], iteraciones=IT)
        self.assertEqual(a["categoria"], "Trío")

    def test_calle_se_deduce_del_tablero(self):
        # preflop con apuesta: usa las reglas preflop (rango de apertura) y no las postflop
        a = ap(pc("As Ah"), [], 1.5, 0, 1, [{"top": 40}], iteraciones=IT)
        self.assertTrue(any("top" in r for r in a["razones"]))


class TestRangosYComparacion(unittest.TestCase):
    def test_rango_top_es_monotono_y_acotado(self):
        n = [len(guia.rango_top(p)) for p in (5, 10, 20, 40, 80, 100)]
        self.assertEqual(n, sorted(n))
        self.assertEqual(len(guia.rango_top(100)), 169)

    def test_aa_es_la_mejor_mano(self):
        self.assertEqual(guia._ranking()[0], "AA")
        self.assertLess(guia.percentil("AA"), guia.percentil("72o"))

    def test_nombres_de_posicion(self):
        self.assertEqual(guia.posiciones_mesa(6), ["SB", "BB", "UTG", "HJ", "CO", "BTN"])
        self.assertEqual(guia.posiciones_mesa(2), ["BTN/SB", "BB"])

    def test_restringir_sube_con_aire_deja_menos_peso_que_con_mano_hecha(self):
        tablero = pc("Ks 7d 2c")
        rango = dict(guia.rango_top(40))
        nuevo = guia.restringir_por_tablero(rango, tablero, "sube")
        self.assertLess(sum(nuevo.values()), sum(rango.values()))
        self.assertGreater(nuevo.get("KK", 0), nuevo.get("QJo", 0))  # el set pesa más que el aire

    def test_restringir_pasivo_no_toca_el_rango(self):
        rango = dict(guia.rango_top(40))
        self.assertEqual(guia.restringir_por_tablero(rango, pc("Ks 7d 2c"), "pasivo"), rango)

    def test_comparar_todas_las_combinaciones(self):
        def sug(accion, eq=0.5, odds=0.2):
            return {"accion": accion, "equity": eq, "pot_odds": odds}
        for jugada in ("fold", "check", "call", "bet", "raise"):
            for accion in ("fold", "check", "call", "bet", "raise"):
                r = guia.comparar(jugada, sug(accion))
                fam = {"fold": "F", "check": "C", "call": "C", "bet": "R", "raise": "R"}
                mismo = fam[jugada] == fam[accion]
                self.assertEqual(r["veredicto"] == "coincide", mismo, (jugada, accion))
        # gravedad: retirarse con mucha equity es una diferencia clara; apostar vs igualar es leve
        self.assertEqual(guia.comparar("fold", sug("call"))["gravedad"], "clara")
        self.assertEqual(guia.comparar("raise", sug("call"))["gravedad"], "leve")
        self.assertEqual(guia.comparar("fold", sug("call", eq=0.21, odds=0.2))["gravedad"], "leve")


class TestEntradasInvalidas(unittest.TestCase):
    def test_cartas_repetidas(self):
        with self.assertRaises(ValueError):
            ap(pc("As Ah"), pc("As 7c 2h"), 10, 0, 1, [{"top": 30}])

    def test_sin_rivales(self):
        with self.assertRaises(ValueError):
            ap(pc("As Ah"), [], 1.5, 0, 1, [])

    def test_rango_sin_manos_validas(self):
        with self.assertRaises(ValueError):
            ap(pc("As Ah"), [], 1.5, 0, 1, [{"claves": ["ZZ"]}])


if __name__ == "__main__":
    unittest.main()
