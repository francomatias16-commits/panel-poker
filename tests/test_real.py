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


class TestOrdenDeCarga(unittest.TestCase):
    """La validación temporal necesita las manos en orden cronológico."""

    def _carpeta(self, estructura):
        import tempfile

        raiz = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, raiz, True)
        with open(RUTA, encoding="utf-8") as f:
            base = f.read()
        for ruta_rel, n_mano in estructura:
            destino = os.path.join(raiz, ruta_rel)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "w", encoding="utf-8") as g:
                g.write(base.replace("hand = 63", f"hand = {n_mano}"))
        return raiz

    def test_archivos_numerados_se_cargan_en_orden_numerico(self):
        from poker_analisis.real import cargar_directorio

        raiz = self._carpeta([(f"{n}.phh", n) for n in (1, 2, 3, 10, 11, 20, 100)])
        manos, rechazos = cargar_directorio(raiz)
        self.assertEqual(rechazos, [])
        self.assertEqual([m.archivo for m in manos],
                         ["1.phh", "2.phh", "3.phh", "10.phh", "11.phh", "20.phh", "100.phh"])

    def test_subcarpetas_se_recorren_en_orden_numerico(self):
        from poker_analisis.real import cargar_directorio

        raiz = self._carpeta([(os.path.join(d, f"{n}.phh"), n) for d in ("2", "10", "1") for n in (1, 10, 2)])
        manos, _ = cargar_directorio(raiz)
        esperado = [os.path.join(d, f"{n}.phh") for d in ("1", "2", "10") for n in (1, 2, 10)]
        self.assertEqual([m.archivo for m in manos], esperado)

    def test_clave_natural(self):
        from poker_analisis.phh import clave_natural

        nombres = ["10.phh", "2.phh", "1.phh", "a10.phh", "a9.phh", "100.phh"]
        self.assertEqual(sorted(nombres, key=clave_natural),
                         ["1.phh", "2.phh", "10.phh", "100.phh", "a9.phh", "a10.phh"])


if __name__ == "__main__":
    unittest.main()
