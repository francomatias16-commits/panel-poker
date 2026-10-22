"""Perfiles de juego (Fase 2): clasificación en los límites, estimación bayesiana con poca y mucha muestra,
ajustes con base en muestra suficiente y clasificación de los bots del proyecto."""
import json
import os
import sys
import unittest

RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "app"))

from poker_analisis import bots, perfiles as P, simulacion  # noqa: E402
from poker_analisis.estadisticas_completas import (  # noqa: E402
    Frecuencia, Razon, ReporteJugador, Resultado, calcular_completo,
)


def reporte(nombre="X", manos=1000, vpip=(250, 1000), pfr=(180, 1000), agr=(60, 40), extra=None):
    """Reporte armado a mano. `agr` = (agresiones, igualaciones) repartidas en las tres calles."""
    fr = {"vpip": Frecuencia(*vpip), "pfr": Frecuencia(*pfr)}
    fr.update(extra or {})
    a, i = agr
    ag = {"flop": Razon(a // 3, i // 3), "turn": Razon(a // 3, i // 3), "river": Razon(a - 2 * (a // 3), i - 2 * (i // 3))}
    return ReporteJugador(nombre, manos, fr, ag, Resultado(manos, 0.0, 0.0), {}, {}, 0.0)


class TestClasificar(unittest.TestCase):
    def test_cinco_perfiles(self):
        self.assertEqual(P.clasificar(0.18, 0.80), P.TIGHT_AGRESIVO)
        self.assertEqual(P.clasificar(0.15, 0.40), P.TIGHT_PASIVO)
        self.assertEqual(P.clasificar(0.35, 0.70), P.AGRESIVO_SUELTO)
        self.assertEqual(P.clasificar(0.40, 0.30), P.ESTACION)
        self.assertEqual(P.clasificar(0.60, 0.90), P.MANIATICO)

    def test_limites(self):
        self.assertEqual(P.clasificar(P.VPIP_SUELTO, 0.9), P.AGRESIVO_SUELTO)  # el límite pertenece al lado suelto
        self.assertEqual(P.clasificar(P.VPIP_SUELTO - 0.001, 0.9), P.TIGHT_AGRESIVO)
        self.assertEqual(P.clasificar(0.2, P.P_AGRESIVO), P.TIGHT_AGRESIVO)
        self.assertEqual(P.clasificar(0.2, P.P_AGRESIVO - 0.001), P.TIGHT_PASIVO)
        self.assertEqual(P.clasificar(P.VPIP_MANIATICO, P.P_MANIATICO), P.MANIATICO)
        self.assertEqual(P.clasificar(P.VPIP_MANIATICO, P.P_MANIATICO - 0.001), P.AGRESIVO_SUELTO)

    def test_af_y_proporcion_equivalen(self):
        self.assertAlmostEqual(P.P_AGRESIVO, 0.6)
        self.assertAlmostEqual(P.P_MANIATICO, 0.75)


class TestPerfilDeReporte(unittest.TestCase):
    def test_tag_con_mucha_muestra(self):
        pf = P.perfil_de(reporte(vpip=(200, 1000), agr=(150, 50)))  # VPIP 20 %, AF 3
        self.assertEqual(pf.perfil, P.TIGHT_AGRESIVO)
        self.assertFalse(pf.provisorio)
        self.assertGreater(pf.probabilidades[P.TIGHT_AGRESIVO], 0.99)

    def test_tight_pasivo(self):
        pf = P.perfil_de(reporte(vpip=(150, 1000), agr=(40, 160)))  # VPIP 15 %, AF 0,25
        self.assertEqual(pf.perfil, P.TIGHT_PASIVO)

    def test_estacion(self):
        pf = P.perfil_de(reporte(vpip=(450, 1000), agr=(30, 270)))
        self.assertEqual(pf.perfil, P.ESTACION)

    def test_lag_y_maniatico(self):
        self.assertEqual(P.perfil_de(reporte(vpip=(340, 1000), agr=(180, 90))).perfil, P.AGRESIVO_SUELTO)
        self.assertEqual(P.perfil_de(reporte(vpip=(600, 1000), agr=(450, 50))).perfil, P.MANIATICO)

    def test_probabilidades_suman_uno(self):
        pf = P.perfil_de(reporte(manos=60, vpip=(15, 60), agr=(10, 8)))
        self.assertAlmostEqual(sum(pf.probabilidades.values()), 1.0, places=9)

    def test_menos_de_30_manos_no_emite_perfil(self):
        pf = P.perfil_de(reporte(manos=25, vpip=(10, 25)))
        self.assertIsNone(pf.perfil)
        self.assertTrue(pf.provisorio)
        self.assertEqual(pf.ajustes, [])

    def test_pocas_manos_es_provisorio_y_las_mismas_proporciones_con_mas_manos_son_firmes(self):
        chico = P.perfil_de(reporte(manos=40, vpip=(8, 40), agr=(12, 4)))
        grande = P.perfil_de(reporte(manos=1000, vpip=(200, 1000), agr=(300, 100)))
        self.assertTrue(chico.provisorio)
        self.assertFalse(grande.provisorio)
        self.assertEqual(chico.perfil, grande.perfil)
        self.assertLess(chico.probabilidades[chico.perfil], grande.probabilidades[grande.perfil])

    def test_mas_evidencia_sube_la_probabilidad(self):
        prev = 0.0
        for k in (1, 3, 10, 30):
            pf = P.perfil_de(reporte(manos=100 * k, vpip=(25 * k, 100 * k), agr=(30 * k, 10 * k)))
            top = pf.probabilidades[P.TIGHT_AGRESIVO]
            self.assertGreaterEqual(top + 0.02, prev)  # tolerancia por el muestreo
            prev = top
        self.assertGreater(prev, 0.99)

    def test_posterior_se_encoge_hacia_la_previa(self):
        pf = P.perfil_de(reporte(manos=40, vpip=(40, 40)))  # 40 de 40
        self.assertLess(pf.vpip.media, 1.0)
        self.assertGreater(pf.vpip.media, 0.6)
        self.assertLess(pf.vpip.media, 40 / 40)
        self.assertLessEqual(pf.vpip.inf, pf.vpip.media)
        self.assertGreaterEqual(pf.vpip.sup, pf.vpip.media)

    def test_sin_acciones_postflop_queda_provisorio_y_en_la_previa(self):
        pf = P.perfil_de(reporte(manos=1000, vpip=(100, 1000), agr=(0, 0)))
        self.assertTrue(pf.provisorio)
        self.assertIn("postflop", pf.motivo)
        self.assertIsNone(pf.af_observado)
        self.assertAlmostEqual(pf.agresion.media, P.PREVIA_AGRESION, places=9)

    def test_nunca_iguala(self):
        pf = P.perfil_de(reporte(manos=1000, vpip=(300, 1000), agr=(120, 0)))
        self.assertIsNone(pf.af_observado)  # AF infinito: no se informa un número inventado
        self.assertGreater(pf.af_estimado, 3)

    def test_determinista(self):
        a = P.perfil_de(reporte(manos=80, vpip=(25, 80), agr=(10, 9)))
        b = P.perfil_de(reporte(manos=80, vpip=(25, 80), agr=(10, 9)))
        self.assertEqual(a.probabilidades, b.probabilidades)
        self.assertEqual(a.vpip.inf, b.vpip.inf)


class TestAjustes(unittest.TestCase):
    def test_todos_traen_base(self):
        for v, a in (((150, 1000), (40, 160)), ((200, 1000), (150, 50)), ((340, 1000), (180, 90)),
                     ((450, 1000), (30, 270)), ((600, 1000), (450, 50))):
            pf = P.perfil_de(reporte(vpip=v, agr=a))
            self.assertTrue(pf.ajustes)
            for aj in pf.ajustes:
                self.assertTrue(aj.texto and aj.base)

    def test_ajuste_puntual_solo_con_muestra_aceptable(self):
        poca = reporte(extra={"fold_cbet_flop": Frecuencia(9, 10)})
        mucha = reporte(extra={"fold_cbet_flop": Frecuencia(90, 100)})
        self.assertFalse(any("c-bet" in a.texto for a in P.perfil_de(poca).ajustes))
        con = [a for a in P.perfil_de(mucha).ajustes if "c-bet" in a.texto]
        self.assertEqual(len(con), 1)
        self.assertIn("100 oportunidades", con[0].base)

    def test_ajuste_puntual_cambia_de_signo_con_el_dato(self):
        alto = reporte(extra={"fold_3bet": Frecuencia(80, 100)})
        bajo = reporte(extra={"fold_3bet": Frecuencia(30, 100)})
        medio = reporte(extra={"fold_3bet": Frecuencia(52, 100)})
        self.assertTrue(any("de farol" in a.texto for a in P.perfil_de(alto).ajustes))
        self.assertTrue(any("solo por valor" in a.texto for a in P.perfil_de(bajo).ajustes))
        self.assertFalse(any("3-beteale" in a.texto for a in P.perfil_de(medio).ajustes))

    def test_limp_frecuente(self):
        pf = P.perfil_de(reporte(vpip=(400, 1000), pfr=(60, 1000), agr=(10, 90)))
        self.assertTrue(any("limp" in a.texto for a in pf.ajustes))


class TestFormato(unittest.TestCase):
    def test_informe(self):
        txt = P.formatear(P.perfil_de(reporte(nombre="Rival", vpip=(200, 1000), agr=(150, 50))))
        for parte in ("# Rival", "Perfil: tight agresivo", "Qué lo define", "Probabilidad por perfil", "Cómo explotarlo"):
            self.assertIn(parte, txt)

    def test_provisorio_avisa(self):
        txt = P.formatear(P.perfil_de(reporte(manos=40, vpip=(8, 40), agr=(12, 4))))
        self.assertIn("(provisorio)", txt)
        self.assertIn("cautela", txt)

    def test_sin_perfil(self):
        txt = P.formatear(P.perfil_de(reporte(manos=10, vpip=(4, 10))))
        self.assertIn("no alcanza", txt)


class TestBotsDelProyecto(unittest.TestCase):
    """Criterio de aceptación del plan: los bots se clasifican según lo que hacen con muestra suficiente."""

    @classmethod
    def setUpClass(cls):
        tabla = bots.cargar_tabla_preflop(os.path.join(RAIZ, "resultados", "preflop_equity.csv"))
        cls.manos = simulacion.simular_mesa(tabla, 2000, 7)
        cls.perf = P.perfiles(calcular_completo(cls.manos, 2, simulacion.PERFILES))

    def test_pasivos_son_estaciones_de_llamadas(self):
        for n in ("Pasivo-1", "Pasivo-2"):
            self.assertEqual(self.perf[n].perfil, P.ESTACION)
            self.assertFalse(self.perf[n].provisorio)

    def test_aleatorio_es_maniatico(self):
        self.assertEqual(self.perf["Aleatorio"].perfil, P.MANIATICO)
        self.assertFalse(self.perf["Aleatorio"].provisorio)

    def test_los_tag_son_tight_agresivos(self):
        # Con el umbral preflop recalibrado (0,60) los bots TAG juegan cerca del 21 % de las manos y suben casi todas.
        for n in ("TAG-1", "TAG-2", "TAG-3"):
            pf = self.perf[n]
            self.assertTrue(0.15 <= pf.vpip.media < P.VPIP_SUELTO, pf.vpip.media)
            self.assertEqual(pf.perfil, P.TIGHT_AGRESIVO)
            self.assertFalse(pf.provisorio)

    def test_el_umbral_anterior_se_puede_reproducir(self):
        # Con 0,55 (el valor de antes) los TAG vuelven a ser agresivos sueltos: sirve para reproducir resultados viejos.
        tabla = bots.cargar_tabla_preflop(os.path.join(RAIZ, "resultados", "preflop_equity.csv"))
        rep = calcular_completo(simulacion.simular_mesa(tabla, 1500, 7, umbral_tag=0.55), 2, simulacion.PERFILES)
        self.assertEqual(P.perfil_de(rep["TAG-1"]).perfil, P.AGRESIVO_SUELTO)

    def test_con_pocas_manos_todos_son_provisorios(self):
        rep = calcular_completo(self.manos[:40], 2, simulacion.PERFILES)
        for pf in P.perfiles(rep).values():
            self.assertTrue(pf.provisorio)


class TestPanelWeb(unittest.TestCase):
    def test_detalle_del_jugador_trae_el_perfil(self):
        import web
        a = web.Almacen()
        a.demo(300)
        d = a.jugador({"jugador": "Pasivo-1", "stake": None})
        perfil = d["completo"]["perfil"]
        json.dumps(d, allow_nan=False)
        self.assertEqual(perfil["perfil"], P.ESTACION)
        self.assertIn("Cómo explotarlo", perfil["texto"])
        self.assertTrue(perfil["ajustes"])


if __name__ == "__main__":
    unittest.main()
