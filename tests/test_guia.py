"""Pruebas de la guía de estudio y del servidor web local."""

import http.client
import json
import os
import threading
import unittest
from dataclasses import replace
from http.server import ThreadingHTTPServer

from poker_analisis import guia, parsear_cartas
from poker_analisis.real import desde_phh

RAIZ = os.path.dirname(os.path.dirname(__file__))
FIXTURE = os.path.join(RAIZ, "tests", "fixtures", "pluribus_ejemplo.phh")


def mano_ejemplo():
    with open(FIXTURE, encoding="utf-8") as f:
        return desde_phh(f.read())


class TestRangos(unittest.TestCase):
    def test_top_pct_suma_combinaciones(self):
        total = sum(guia.COMBOS[c] * p for c, p in guia.rango_top(20))
        self.assertAlmostEqual(total, 1326 * 0.20, places=6)

    def test_percentil_ordena_manos(self):
        self.assertLess(guia.percentil("AA"), guia.percentil("AKs"))
        self.assertLess(guia.percentil("AKs"), guia.percentil("72o"))

    def test_posiciones_6max(self):
        m = mano_ejemplo()
        self.assertEqual([guia.posicion(m, i) for i in range(6)], ["SB", "BB", "UTG", "HJ", "CO", "BTN"])
        self.assertEqual(guia.posiciones_mesa(6), ["SB", "BB", "UTG", "HJ", "CO", "BTN"])


class TestDecision(unittest.TestCase):
    def test_equity_multiway_aa_gana_a_un_rango_amplio(self):
        eq = guia.equity_multiway(parsear_cartas("As Ah"), [dict(guia.rango_top(50))], iteraciones=800, semilla=3)
        self.assertGreater(eq.equity, 0.75)

    def test_situacion_obvia_igualar_con_buen_precio(self):
        a = guia.analisis_puntual(parsear_cartas("As Kd"), [], 3, 2, 2, [{"top": 15}], pos="BTN", subidas_preflop=1)
        self.assertEqual(a["accion"], "call")
        self.assertAlmostEqual(a["pot_odds"], 0.4)

    def test_fold_si_la_equity_no_alcanza(self):
        a = guia.analisis_puntual(parsear_cartas("7c 2d"), parsear_cartas("Ks Qs Jh"), 10, 10, 1, [{"claves": ["AA", "KK", "AKs"]}])
        self.assertEqual(a["accion"], "fold")

    def test_abrir_desde_utg_solo_con_manos_fuertes(self):
        fuerte = guia.analisis_puntual(parsear_cartas("As Ah"), [], 1.5, 1, 1, [{"top": 60}] * 5, pos="UTG")
        floja = guia.analisis_puntual(parsear_cartas("7c 2d"), [], 1.5, 1, 1, [{"top": 60}] * 5, pos="UTG")
        self.assertEqual(fuerte["accion"], "raise")
        self.assertEqual(floja["accion"], "fold")

    def test_comparar_familias(self):
        s = {"accion": "call", "equity": 0.5, "pot_odds": 0.2}
        self.assertEqual(guia.comparar("check", s)["veredicto"], "coincide")
        self.assertEqual(guia.comparar("fold", s)["veredicto"], "desvio")


class TestRepaso(unittest.TestCase):
    def test_pasos_y_conservacion(self):
        m = mano_ejemplo()
        r = guia.reproducir(m, 0, iteraciones=200)
        self.assertEqual(r["resumen"]["decisiones"], 4)
        calles = [p["calle"] for p in r["pasos"]]
        self.assertEqual(calles[0], "preflop")
        self.assertIn("flop", calles)
        self.assertEqual(calles[-1], "river")
        final = r["pasos"][-1]
        self.assertAlmostEqual(sum(final["neto"]), 0.0)
        # El bote final es lo que pusieron todos
        self.assertEqual(final["bote"], sum(final["invertido"]))

    def test_no_usa_las_cartas_de_los_rivales(self):
        m = mano_ejemplo()
        otras = [parsear_cartas("2c 3c") if i == 1 else c for i, c in enumerate(m.cartas)]
        m2 = replace(m, cartas=[tuple(c) for c in otras])
        a = guia.reproducir(m, 0, iteraciones=200)
        b = guia.reproducir(m2, 0, iteraciones=200)
        eq_a = [p["analisis"]["equity"] for p in a["pasos"] if p.get("analisis")]
        eq_b = [p["analisis"]["equity"] for p in b["pasos"] if p.get("analisis")]
        self.assertEqual(eq_a, eq_b)

    def test_reproducible_con_semilla(self):
        m = mano_ejemplo()
        a = guia.reproducir(m, 0, iteraciones=200, semilla=5)
        b = guia.reproducir(m, 0, iteraciones=200, semilla=5)
        self.assertEqual(a["pasos"], b["pasos"])

    def test_cartas_de_rivales_solo_tras_showdown(self):
        r = guia.reproducir(mano_ejemplo(), 0, iteraciones=200)
        hasta_showdown = [p for p in r["pasos"] if p["tipo"] != "muestra" and p["tipo"] != "resultado"]
        self.assertTrue(all(set(p["reveladas"]) <= set() for p in hasta_showdown))
        self.assertTrue(r["pasos"][-1]["reveladas"])

    def test_sin_cartas_visibles_no_analiza(self):
        m = mano_ejemplo()
        m2 = replace(m, cartas=[() for _ in m.cartas])
        r = guia.reproducir(m2, 0, iteraciones=200)
        self.assertFalse(r["resumen"]["con_analisis"])
        self.assertTrue(all("analisis" not in p for p in r["pasos"]))


class TestServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(RAIZ, "app"))
        import web
        cls.web = web
        web.ALMACEN.demo(40, semilla=3)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), web.Manejador)
        cls.puerto = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=60)
        h = {"Content-Type": "application/json"} if cuerpo is not None else {}
        h.update(cabeceras or {})
        c.request(metodo, ruta, body=json.dumps(cuerpo) if cuerpo is not None else None, headers=h)
        r = c.getresponse()
        datos = r.read()
        c.close()
        return r.status, json.loads(datos) if r.getheader("Content-Type", "").startswith("application/json") else datos

    def test_flujo_basico(self):
        st, e = self.pedir("GET", "/api/estado")
        self.assertEqual((st, e["manos"]), (200, 40))
        st, p = self.pedir("POST", "/api/panel", {"min_manos": 10})
        self.assertEqual(st, 200)
        self.assertEqual(len(p["filas"]), 6)
        st, d = self.pedir("POST", "/api/jugador", {"jugador": "TAG-1", "posiciones": ["BTN"]})
        self.assertEqual(st, 200)
        self.assertGreater(d["manos"], 0)
        st, lista = self.pedir("POST", "/api/manos", {"jugador": "TAG-1", "limite": 5})
        self.assertEqual(len(lista["filas"]), 5)
        st, r = self.pedir("GET", f"/api/mano?id={lista['filas'][0]['id']}&jugador=TAG-1")
        self.assertEqual(st, 200)
        self.assertEqual(r["heroe"]["nombre"], "TAG-1")

    def test_analisis_puntual_y_errores(self):
        cuerpo = {"cartas": "As Kd", "tablero": "Qs 7h 2c", "bote": 20, "a_pagar": 10, "bb": 2, "rivales": [{"top": 20}]}
        st, r = self.pedir("POST", "/api/analisis", cuerpo)
        self.assertEqual(st, 200)
        self.assertIn(r["accion"], ("call", "fold", "raise"))
        st, r = self.pedir("POST", "/api/analisis", {**cuerpo, "cartas": "As As"})
        self.assertEqual(st, 400)
        st, r = self.pedir("GET", "/api/mano?id=99999")
        self.assertEqual(st, 404)

    def test_seguridad(self):
        self.assertEqual(self.pedir("GET", "/api/estado", cabeceras={"Host": "evil.example"})[0], 403)
        c = http.client.HTTPConnection("127.0.0.1", self.puerto)
        c.request("POST", "/api/panel", body="{}", headers={"Content-Type": "text/plain"})
        self.assertEqual(c.getresponse().status, 415)
        self.assertEqual(self.pedir("GET", "/static/../web.py")[0], 404)

    def test_json_sin_infinitos(self):
        self.assertIsNone(self.web._limpiar(float("inf")))
        self.assertEqual(self.web._limpiar({"a": [1.5, float("nan")]}), {"a": [1.5, None]})


if __name__ == "__main__":
    unittest.main()
