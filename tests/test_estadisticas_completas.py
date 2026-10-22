"""Estadísticas completas: manos construidas a mano con resultado conocido y contraste con el calculador anterior."""
import unittest

from poker_analisis.cartas import Mazo
from poker_analisis.estadisticas import calcular
from poker_analisis.estadisticas_completas import (
    CalculadorCompleto, Frecuencia, calcular_completo, clasificar_posicion,
)
from poker_analisis.motor import jugar_mano

F, C = ("f", None), ("cc", None)
NOMBRES = ["BTN", "SB", "BB", "UTG", "MP", "CO"]  # boton = 0: asiento 1 = SB, 2 = BB, 3 = UTG, 4 = MP, 5 = CO


def mano(acciones, semilla=1, stacks=None):
    """`acciones[asiento]` = lista de acciones que ese asiento hace, en orden. Lo que falte es check/call."""
    pend = {a: list(v) for a, v in acciones.items()}

    def politica(a):
        def decidir(v):
            return pend[a].pop(0) if pend.get(a) else C
        return decidir

    r = jugar_mano(stacks or [200] * 6, 0, 1, 2, [politica(a) for a in range(6)], Mazo(semilla=semilla))
    r.ciega_grande, r.ciega_chica = 2, 1
    return r


def rep(r):
    return calcular_completo([r], 2, NOMBRES)


def fr(reporte, jugador, clave):
    f = reporte[jugador].frecuencias.get(clave)
    return (f.exitos, f.n) if f else None


class TestPosiciones(unittest.TestCase):
    def test_seis_jugadores(self):
        pos = [clasificar_posicion(s, 0, 6, 1, 2) for s in range(6)]
        self.assertEqual(pos, ["BTN", "SB", "BB", "UTG", "MP", "CO"])

    def test_heads_up_el_boton_es_la_ciega_chica(self):
        self.assertEqual(clasificar_posicion(0, 0, 2, 0, 1), "SB")
        self.assertEqual(clasificar_posicion(1, 0, 2, 0, 1), "BB")


class TestRoboYCbet(unittest.TestCase):
    def setUp(self):
        # UTG y MP se retiran, CO roba a 6, BTN y SB se retiran, BB iguala.
        # Flop: BB pasa, CO apuesta 8, BB se retira.
        self.r = mano({3: [F], 4: [F], 5: [("cbr", 6), ("cbr", 8)], 0: [F], 1: [F], 2: [C, C, F]})
        self.rep = rep(self.r)

    def test_robo_y_defensa_de_ciega(self):
        self.assertEqual(fr(self.rep, "CO", "robo"), (1, 1))
        self.assertEqual(fr(self.rep, "BTN", "robo"), None)  # actuó después de la subida: no hay oportunidad
        self.assertEqual(fr(self.rep, "BB", "bb_robo_call"), (1, 1))
        self.assertEqual(fr(self.rep, "BB", "bb_robo_fold"), (0, 1))
        self.assertEqual(fr(self.rep, "BB", "bb_robo_3bet"), (0, 1))
        self.assertEqual(fr(self.rep, "SB", "bb_robo_fold"), None)  # solo cuenta la ciega grande

    def test_cbet_y_fold_a_cbet(self):
        self.assertEqual(fr(self.rep, "CO", "cbet_flop"), (1, 1))
        self.assertEqual(fr(self.rep, "BB", "fold_cbet_flop"), (1, 1))
        self.assertEqual(fr(self.rep, "BB", "donk_flop"), (0, 1))

    def test_vpip_pfr_por_posicion(self):
        self.assertEqual(fr(self.rep, "CO", "vpip@CO"), (1, 1))
        self.assertEqual(fr(self.rep, "CO", "pfr@CO"), (1, 1))
        self.assertEqual(fr(self.rep, "UTG", "vpip@UTG"), (0, 1))
        self.assertEqual(fr(self.rep, "BB", "vpip@BB"), (1, 1))
        self.assertEqual(fr(self.rep, "BB", "pfr@BB"), (0, 1))

    def test_factor_de_agresion_por_calle(self):
        agr = self.rep["CO"].agresion["flop"]
        self.assertEqual((agr.agresiones, agr.igualaciones), (1, 0))
        self.assertIsNone(agr.valor)  # sin igualaciones el cociente no está definido

    def test_el_ganador_cobra_el_bote(self):
        res = self.rep["CO"].resultado
        self.assertEqual(res.manos, 1)
        self.assertAlmostEqual(res.bb100, 100 * self.r.neto[5] / 2)


class TestTresBetCuatroBet(unittest.TestCase):
    def test_3bet_4bet_y_checkraise(self):
        # UTG abre a 6, todos se retiran hasta SB que re-sube a 20; BB se retira; UTG sube a 50; SB iguala.
        # Flop: SB pasa, UTG apuesta 30, SB sube a 100 (check-raise), UTG se retira.
        r = mano({3: [("cbr", 6), ("cbr", 50), ("cbr", 30), F], 4: [F], 5: [F], 0: [F],
                  1: [("cbr", 20), C, C, ("cbr", 100)], 2: [F]})
        x = rep(r)
        self.assertEqual(fr(x, "SB", "3bet"), (1, 1))
        self.assertEqual(fr(x, "UTG", "4bet"), (1, 1))
        self.assertEqual(fr(x, "UTG", "fold_3bet"), (0, 1))
        self.assertEqual(fr(x, "SB", "4bet"), None)
        self.assertEqual(fr(x, "UTG", "cbet_flop"), (1, 1))
        self.assertEqual(fr(x, "SB", "checkraise_flop"), (1, 1))
        self.assertEqual(fr(x, "UTG", "robo"), None)  # UTG no es posición de robo

    def test_fold_a_3bet(self):
        r = mano({3: [("cbr", 6), F], 4: [F], 5: [F], 0: [F], 1: [("cbr", 20)], 2: [F]})
        x = rep(r)
        self.assertEqual(fr(x, "UTG", "fold_3bet"), (1, 1))
        self.assertEqual(fr(x, "UTG", "4bet"), (0, 1))
        self.assertEqual(fr(x, "MP", "3bet"), (0, 1))


class TestDonkYBarril(unittest.TestCase):
    def test_donk_bet_y_el_agresor_no_tiene_oportunidad_de_cbet(self):
        r = mano({3: [F], 4: [F], 5: [("cbr", 6), F], 0: [F], 1: [F], 2: [C, ("cbr", 4)]})
        x = rep(r)
        self.assertEqual(fr(x, "BB", "donk_flop"), (1, 1))
        self.assertEqual(fr(x, "CO", "cbet_flop"), None)
        self.assertEqual(fr(x, "CO", "fold_cbet_flop"), None)  # no enfrentó una c-bet sino una apuesta del rival

    def test_barril_en_el_turn_y_fold_al_barril(self):
        r = mano({3: [F], 4: [F], 5: [("cbr", 6), ("cbr", 8), ("cbr", 20)], 0: [F], 1: [F], 2: [C, C, C, C, F]})
        x = rep(r)
        # Flop: BB pasa, CO apuesta 8, BB iguala. Turn: BB pasa, CO apuesta 20, BB se retira.
        self.assertEqual(fr(x, "CO", "cbet_flop"), (1, 1))
        self.assertEqual(fr(x, "CO", "barril_turn"), (1, 1))
        self.assertEqual(fr(x, "BB", "fold_cbet_flop"), (0, 1))
        self.assertEqual(fr(x, "BB", "fold_barril_turn"), (1, 1))
        self.assertEqual(fr(x, "CO", "barril_river"), None)  # la mano terminó en el turn
        agr = x["BB"].agresion["flop"]
        self.assertEqual((agr.agresiones, agr.igualaciones), (0, 1))


class TestShowdownYRiver(unittest.TestCase):
    def test_farol_visible_wtsd_y_wsd(self):
        # CO abre, BB iguala, pasan flop y turn; en el river CO apuesta 10 y BB iguala.
        r = mano({3: [F], 4: [F], 5: [("cbr", 6), C, C, ("cbr", 10)], 0: [F], 1: [F], 2: [C, C, C, C, C]}, semilla=3)
        self.assertEqual(sorted(r.llegaron_showdown), [2, 5])
        x = rep(r)
        perdio = 5 not in r.ganadores_showdown
        self.assertEqual(fr(x, "CO", "farol_river_visible"), (int(perdio), 1))
        self.assertEqual(fr(x, "CO", "wtsd"), (1, 1))
        self.assertEqual(fr(x, "CO", "wsd"), (int(not perdio), 1))
        self.assertEqual(fr(x, "BB", "farol_river_visible"), None)  # BB no apostó en el river


class TestResultadoYRake(unittest.TestCase):
    def test_rake_se_atribuye_al_ganador(self):
        r = mano({3: [F], 4: [F], 5: [("cbr", 6), ("cbr", 8)], 0: [F], 1: [F], 2: [C, C, F]})
        r.neto[5] -= 1  # 1 ficha de rake (media ciega grande)
        x = rep(r)
        self.assertAlmostEqual(x["CO"].rake_bb, 0.5)
        self.assertAlmostEqual(x["CO"].rake_bb100, 50.0)
        self.assertEqual(x["BB"].rake_bb, 0.0)

    def test_resultado_por_profundidad_y_por_rivales(self):
        r = mano({3: [F], 4: [F], 5: [("cbr", 6), ("cbr", 8)], 0: [F], 1: [F], 2: [C, C, F]},
                 stacks=[200, 200, 60, 200, 200, 200])
        x = rep(r)
        self.assertIn("80-150 bb", x["CO"].por_stack)  # 200 fichas con bb = 2 son 100 bb
        self.assertIn("<40 bb", x["BB"].por_stack)  # 60 fichas son 30 bb
        self.assertIn("1 rival", x["CO"].por_rivales)
        self.assertIn("no vio el flop", x["UTG"].por_rivales)


class TestFrecuencia(unittest.TestCase):
    def test_wilson_con_valores_de_referencia(self):
        lo, hi = Frecuencia(50, 100).ic95
        self.assertAlmostEqual(lo, 0.4038, places=3)
        self.assertAlmostEqual(hi, 0.5962, places=3)
        lo, hi = Frecuencia(0, 10).ic95
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=3)

    def test_alerta_de_muestra(self):
        self.assertEqual(Frecuencia(3, 10).muestra, "insuficiente")
        self.assertEqual(Frecuencia(30, 60).muestra, "baja")
        self.assertEqual(Frecuencia(60, 300).muestra, "aceptable")
        self.assertIsNone(Frecuencia(0, 0).valor)
        self.assertIsNone(Frecuencia(0, 0).ic95)


class TestContrasteConCalculadorAnterior(unittest.TestCase):
    """Con 3.000 manos simuladas, las estadísticas que ya existían tienen que dar exactamente lo mismo."""

    @classmethod
    def setUpClass(cls):
        from poker_analisis.bots import cargar_tabla_preflop
        from poker_analisis.simulacion import BLIND_GRANDE, PERFILES, simular_mesa
        import os

        tabla = cargar_tabla_preflop(os.path.join(os.path.dirname(__file__), "..", "resultados", "preflop_equity.csv"))
        cls.manos = simular_mesa(tabla, 3000, 7)
        cls.nuevo = calcular_completo(cls.manos, BLIND_GRANDE, PERFILES)
        cls.viejo = {s.nombre: s for s in calcular(cls.manos, PERFILES, BLIND_GRANDE)}

    def test_coinciden_las_estadisticas_existentes(self):
        pares = [("vpip", "vpip"), ("pfr", "pfr"), ("3bet", "tres_bet"), ("cbet_flop", "cbet"),
                 ("fold_cbet_flop", "fold_cbet"), ("wtsd", "wtsd"), ("wsd", "wsd")]
        for nombre, v in self.viejo.items():
            n = self.nuevo[nombre]
            for clave_n, clave_v in pares:
                esperado = getattr(v, clave_v)
                f = n.frecuencias.get(clave_n)
                obtenido = f.valor if f else None
                if esperado is None:
                    self.assertIsNone(obtenido, (nombre, clave_n))
                else:
                    self.assertAlmostEqual(obtenido, esperado, places=12, msg=(nombre, clave_n))
            self.assertAlmostEqual(n.resultado.bb100, v.bb100, places=9)
            self.assertAlmostEqual(n.resultado.ic95, v.bb100_ic95, places=6)

    def test_invariantes(self):
        for nombre, n in self.nuevo.items():
            self.assertEqual(n.frecuencias["vpip"].n, n.manos)
            self.assertLessEqual(n.frecuencias["pfr"].exitos, n.frecuencias["vpip"].exitos)
            self.assertEqual(sum(r.manos for r in n.por_stack.values()), n.manos)
            self.assertEqual(sum(r.manos for r in n.por_rivales.values()), n.manos)
            suma_pos = sum(f.n for k, f in n.frecuencias.items() if k.startswith("vpip@"))
            self.assertEqual(suma_pos, n.manos)
            for f in n.frecuencias.values():
                self.assertLessEqual(f.exitos, f.n)
            bb = n.frecuencias.get("bb_robo_fold")
            if bb:  # las tres respuestas de la defensa de la ciega suman las oportunidades
                tot = sum(n.frecuencias[k].exitos for k in ("bb_robo_fold", "bb_robo_call", "bb_robo_3bet"))
                self.assertEqual(tot, bb.n)

    def test_suma_de_bb100_cero_sin_rake(self):
        self.assertAlmostEqual(sum(n.resultado.bb100 * n.manos for n in self.nuevo.values()), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
