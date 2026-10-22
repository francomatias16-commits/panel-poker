import json
import os
import sys
import unittest

from poker_analisis import practica as P
from poker_analisis.simulacion import STACK_INICIAL


def jugar_hasta_el_final(ses, politica="cc", tope=60):
    e = ses.estado()
    for _ in range(tope):
        if e["terminada"]:
            return e
        e = ses.actuar("cc") if politica == "cc" else ses.actuar("f")
    raise AssertionError("la mano no terminó")


class TestPractica(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tabla = P._tabla_defecto()

    def sesion(self, semilla=5, guia=True):
        return P.Sesion(tabla=self.tabla, semilla=semilla, guia_activa=guia)

    def test_reconstruccion_determinista(self):
        a, b = self.sesion(9, False), self.sesion(9, False)
        ea, eb = jugar_hasta_el_final(a), jugar_hasta_el_final(b)
        self.assertEqual(ea["log"], eb["log"])
        self.assertEqual(ea["resultado"]["netos_bb"], eb["resultado"]["netos_bb"])

    def test_estado_es_estable_entre_llamadas(self):
        s = self.sesion(3, False)
        self.assertEqual(s.estado(), s.estado())

    def test_conserva_las_fichas(self):
        s = self.sesion(11, False)
        for _ in range(4):
            e = jugar_hasta_el_final(s, "cc")
            self.assertAlmostEqual(sum(e["resultado"]["netos_bb"]), 0.0, places=6)
            s.siguiente()

    def test_no_filtra_cartas_de_rivales_antes_del_showdown(self):
        s = self.sesion(4, False)
        e = s.estado()
        self.assertFalse(e["terminada"])
        texto = json.dumps(e)
        mano, _, _ = s._reconstruir()
        for i in range(1, 6):
            for c in mano.cartas[i]:
                self.assertNotIn(f'"{c}"', texto)
        self.assertNotIn("resultado", e)

    def test_al_terminar_solo_muestra_a_quien_llego_al_showdown(self):
        s = self.sesion(21, False)
        e = jugar_hasta_el_final(s, "f")
        mano, res, _ = s._reconstruir()
        self.assertEqual(set(e["resultado"]["showdown"]), {str(i) for i in res.llegaron_showdown})

    def test_la_guia_responde_en_la_decision_pendiente(self):
        e = self.sesion(5, True).estado()
        self.assertIn(e["guia"]["accion"], ("fold", "check", "call", "bet", "raise"))
        self.assertTrue(0 <= e["guia"]["equity"] <= 1)
        json.dumps(e, allow_nan=False)

    def test_sin_guia_no_la_calcula(self):
        self.assertNotIn("guia", self.sesion(5, False).estado())

    def test_guia_no_depende_de_cartas_ajenas(self):
        s = self.sesion(5, True)
        mano, _, vista = s._reconstruir()
        a = P.sugerencia(mano, vista)
        # cambiar las cartas de un rival no puede cambiar la sugerencia
        mano.cartas[3], mano.cartas[4] = mano.cartas[4], mano.cartas[3]
        self.assertEqual(a, P.sugerencia(mano, vista))

    def test_acciones_invalidas(self):
        s = self.sesion(5, False)
        with self.assertRaises(ValueError):
            s.actuar("x")
        with self.assertRaises(ValueError):
            s.actuar("cbr", 3)  # menos que el mínimo y no es all-in
        with self.assertRaises(ValueError):
            s.actuar("cbr", None)
        with self.assertRaises(ValueError):
            s.siguiente()  # la mano no terminó

    def test_no_se_puede_actuar_con_la_mano_terminada(self):
        s = self.sesion(21, False)
        jugar_hasta_el_final(s, "f")
        with self.assertRaises(ValueError):
            s.actuar("cc")

    def test_acumulado_y_stacks_entre_manos(self):
        s = self.sesion(8, False)
        total = 0.0
        for k in range(3):
            e = jugar_hasta_el_final(s, "cc")
            total += e["resultado"]["neto_bb"]
            self.assertEqual(e["acumulado"]["manos"], k + 1)  # ya cuenta la mano recién terminada
            e = s.siguiente()
            self.assertEqual(e["acumulado"]["manos"], k + 1)  # y no se duplica al cerrarla
            self.assertTrue(all(2 * 2 <= j["stack"] <= STACK_INICIAL for j in e["jugadores"]))
        self.assertAlmostEqual(e["acumulado"]["neto_bb"], round(total, 2), places=1)

    def test_el_boton_rota(self):
        s = self.sesion(2, False)
        botones = []
        for _ in range(3):
            botones.append(s.estado()["boton"])
            jugar_hasta_el_final(s, "f")
            s.siguiente()
        self.assertEqual(botones, [0, 1, 2])

    def test_subir_y_all_in(self):
        s = self.sesion(5, False)
        p = s.estado()["pendiente"]
        e = s.actuar("cbr", p["minimo_hasta"])
        self.assertTrue(any(l.get("heroe") and "sube" in l["texto"] for l in e["log"]))
        s2 = self.sesion(5, False)
        p = s2.estado()["pendiente"]
        e = s2.actuar("cbr", p["maximo_hasta"])
        self.assertTrue(any(l.get("heroe") and "sube a 100" in l["texto"] for l in e["log"]))


class TestPracticaWeb(unittest.TestCase):
    def test_flujo_por_la_funcion_web(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
        import web
        with self.assertRaises(ValueError):
            web._SESION = None
            web.practica({"accion": "actuar", "tipo": "cc"})
        e = web.practica({"accion": "nueva", "semilla": 5, "guia": False})
        json.dumps(e, allow_nan=False)
        self.assertFalse(e["terminada"])
        e = web.practica({"accion": "guia", "activa": True})
        self.assertIn("guia", e)
        e = web.practica({"accion": "actuar", "tipo": "f"})
        self.assertEqual(web.practica({"accion": "estado"})["mano"], e["mano"])
        with self.assertRaises(ValueError):
            web.practica({"accion": "volar"})


if __name__ == "__main__":
    unittest.main()
