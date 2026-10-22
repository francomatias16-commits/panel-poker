import math
import unittest

from poker_analisis.cartas import Mazo
from poker_analisis.motor import jugar_mano
from poker_analisis.rangos import (
    ACCIONES,
    CLAVES,
    PRIOR,
    TOTAL_COMBOS,
    ModeloRangos,
    calibracion,
    observaciones,
)


def fijo(*acciones):
    pendientes = list(acciones)

    def decidir(v):
        return pendientes.pop(0) if pendientes else ("cc", None)

    return decidir


class TestPrior(unittest.TestCase):
    def test_169_claves_y_1326_combinaciones(self):
        self.assertEqual(len(CLAVES), 169)
        self.assertEqual(TOTAL_COMBOS, 1326)

    def test_prior_suma_uno(self):
        self.assertAlmostEqual(sum(PRIOR.values()), 1.0, places=12)


class TestObservaciones(unittest.TestCase):
    def test_contexto_cambia_tras_una_subida(self):
        # UTG sube, SB y BB se retiran: SB y BB actúan en contexto 'responde'.
        politicas = [fijo(("cbr", 6)), fijo(("f", None)), fijo(("f", None))]
        r = jugar_mano([100, 100, 100], 0, 1, 2, politicas, Mazo(semilla=4))
        obs = observaciones(r)
        self.assertEqual([(ctx, acc) for _, ctx, acc in obs[0]], [("abre", "raise")])
        self.assertEqual([(ctx, acc) for _, ctx, acc in obs[1]], [("responde", "fold")])


class TestPosterior(unittest.TestCase):
    def _modelo_solo_as_sube(self):
        """Modelo entrenado a mano: solo los ases suben en contexto 'abre'."""
        m = ModeloRangos(k=5.0)
        for c in CLAVES:
            if c == "AA":
                m._mano[("X", c, "abre")]["raise"] += 30
                m._perfil[("X", "abre")]["raise"] += 30
            else:
                m._mano[("X", c, "abre")]["fold"] += 20
                m._perfil[("X", "abre")]["fold"] += 20
        return m

    def test_posterior_se_concentra_en_los_ases(self):
        m = self._modelo_solo_as_sube()
        post = m.posterior("X", [("abre", "raise")])
        self.assertEqual(max(post, key=post.get), "AA")
        self.assertGreater(post["AA"], 0.3)
        self.assertAlmostEqual(sum(post.values()), 1.0, places=9)

    def test_sin_historia_queda_el_prior_del_perfil(self):
        m = self._modelo_solo_as_sube()
        post = m.posterior("X", [])
        for c in CLAVES:
            self.assertAlmostEqual(post[c], PRIOR[c], places=9)

    def test_prediccion_es_una_distribucion(self):
        m = self._modelo_solo_as_sube()
        pred = m.predecir("X", [("abre", "raise")], "responde")
        self.assertEqual(set(pred), set(ACCIONES))
        self.assertAlmostEqual(sum(pred.values()), 1.0, places=9)


class TestTemperatura(unittest.TestCase):
    def test_t_uno_no_cambia_la_distribucion(self):
        from poker_analisis.rangos import temperatura
        pred = {"fold": 0.1, "check": 0.2, "call": 0.3, "raise": 0.4}
        ajustada = temperatura(pred, 1.0)
        for a in pred:
            self.assertAlmostEqual(ajustada[a], pred[a], places=9)

    def test_modelo_subconfiado_recibe_t_mayor_que_uno(self):
        from poker_analisis.rangos import ajustar_temperatura
        # Dice 60 % y acierta 90 %: debe afilarse, es decir, T > 1.
        registros = []
        for i in range(100):
            acierta = i < 90
            pred = {"fold": 0.6, "check": 0.0, "call": 0.2, "raise": 0.2}
            accion = "fold" if acierta else "call"
            registros.append({"pred": pred, "accion": accion})
        self.assertGreater(ajustar_temperatura(registros), 1.0)


def _registro(confianza, acierta):
    pred = {"fold": confianza, "check": 1 - confianza, "call": 0.0, "raise": 0.0}
    return {"pred": pred, "accion": "fold" if acierta else "check"}


class TestCalibracion(unittest.TestCase):
    def test_predicciones_perfectas_tienen_ece_cero(self):
        registros = [_registro(1.0, True)] * 50 + [_registro(0.0 + 1e-9, False)] * 50
        _, ece = calibracion(registros)
        self.assertAlmostEqual(ece, 0.0, places=3)

    def test_sobreconfianza_se_detecta(self):
        # Dice 90 % y acierta 50 %: el error de calibración es 0,4.
        registros = [_registro(0.9, True)] * 50 + [_registro(0.9, False)] * 50
        _, ece = calibracion(registros)
        self.assertTrue(math.isclose(ece, 0.4, rel_tol=1e-9))


class TestIsotonica(unittest.TestCase):
    def test_salida_es_monotona(self):
        from poker_analisis.rangos import ajustar_isotonica
        pares = [(0.1, 0), (0.2, 1), (0.3, 0), (0.4, 1), (0.5, 1), (0.6, 0), (0.9, 1)]
        iso = ajustar_isotonica(pares)
        valores = [v for _, v in iso]
        self.assertEqual(valores, sorted(valores))

    def test_aprende_patron_no_monotono_con_promedio_por_bloque(self):
        from poker_analisis.rangos import ajustar_isotonica
        # Confianza 0,5 acierta 0 %; 0,6 acierta 100 %; los dos bloques quedan separados.
        pares = [(0.5, False)] * 20 + [(0.6, True)] * 20
        iso = ajustar_isotonica(pares)
        self.assertAlmostEqual(iso[0][1], 0.0)
        self.assertAlmostEqual(iso[-1][1], 1.0)

    def test_transformacion_sigue_siendo_distribucion(self):
        from poker_analisis.rangos import ajustar_isotonica, transformar_isotonica
        iso = ajustar_isotonica([(0.2, True), (0.5, False), (0.8, True)])
        f = transformar_isotonica(iso)
        p = f({"fold": 0.55, "check": 0.25, "call": 0.15, "raise": 0.05})
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)
        self.assertTrue(all(0 <= v <= 1 for v in p.values()))


if __name__ == "__main__":
    unittest.main()


class TestValidacionTemporal(unittest.TestCase):
    def _manos(self, n):
        from poker_analisis.bots import BotAleatorio

        return [
            jugar_mano([100, 100, 100], h % 3, 1, 2,
                       [BotAleatorio(semilla=h * 3 + i) for i in range(3)], Mazo(semilla=h))
            for h in range(n)
        ]

    def test_entrena_solo_con_el_pasado(self):
        from poker_analisis.rangos import validacion_temporal

        filas = validacion_temporal(self._manos(120), ["A", "B", "C"], pliegues=4)
        self.assertEqual([f["pliegue"] for f in filas], [1, 2, 3, 4])
        tam = 120 // 5
        for f in filas:
            self.assertEqual(f["manos_entrenamiento"], f["pliegue"] * tam)
        # El entrenamiento crece y nunca se superpone con la prueba.
        self.assertEqual(filas[-1]["manos_entrenamiento"] + filas[-1]["manos_prueba"], 120)
        for f in filas:
            self.assertTrue(math.isfinite(f["logloss"]) and math.isfinite(f["brier"]))
            self.assertTrue(0 <= f["ece"] <= 1)
            self.assertEqual(sum(c["n"] for c in f["curva"]), f["decisiones"])

    def test_recalibracion_no_usa_la_prueba_y_es_finita(self):
        from poker_analisis.rangos import validacion_temporal

        filas = validacion_temporal(self._manos(120), ["A", "B", "C"], pliegues=3, recalibrar=True)
        for f in filas:
            for clave in ("T", "logloss_nucleo", "ece_nucleo", "logloss_cal", "ece_cal"):
                self.assertTrue(math.isfinite(f[clave]), clave)
            self.assertTrue(0.2 <= f["T"] <= 3.2)
            self.assertTrue(0 <= f["ece_cal"] <= 1)
        # Sin recalibrar no se agregan las columnas extra.
        base = validacion_temporal(self._manos(120), ["A", "B", "C"], pliegues=3)
        self.assertNotIn("T", base[0])

    def test_rechaza_pliegues_invalidos(self):
        from poker_analisis.rangos import validacion_temporal

        with self.assertRaises(ValueError):
            validacion_temporal(self._manos(3), ["A", "B", "C"], pliegues=5)
        with self.assertRaises(ValueError):
            validacion_temporal(self._manos(10), ["A", "B", "C"], pliegues=0)
