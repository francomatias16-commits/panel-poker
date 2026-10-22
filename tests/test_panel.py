import csv
import os
import tempfile
import unittest

from poker_analisis.panel import a_csv, analizar_directorio

MANO = """variant = 'NT'
antes = [0, 0]
blinds_or_straddles = [5, 10]
starting_stacks = [1000, 1000]
actions = ['d dh p1 ????', 'd dh p2 ????', 'p2 cbr 30', 'p1 f']
players = ['Ana', 'Beto']
winnings = [0, 15]
"""


class TestPanel(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        for i in range(3):
            with open(os.path.join(self.dir.name, f"{i}.phh"), "w", encoding="utf-8") as f:
                f.write(MANO)
        with open(os.path.join(self.dir.name, "mala.phh"), "w", encoding="utf-8") as f:
            f.write("esto no es una mano")

    def tearDown(self):
        self.dir.cleanup()

    def test_cuenta_validas_y_rechazos(self):
        p = analizar_directorio(self.dir.name, 10)
        self.assertEqual(p.manos_validas, 3)
        self.assertEqual(len(p.rechazos), 1)
        self.assertEqual({f.nombre for f in p.filas}, {"Ana", "Beto"})

    def test_umbral_marca_muestra_insuficiente(self):
        p = analizar_directorio(self.dir.name, 10, umbral_manos=100)
        self.assertTrue(all(not f.muestra_suficiente for f in p.filas))
        p = analizar_directorio(self.dir.name, 10, umbral_manos=3)
        self.assertTrue(all(f.muestra_suficiente for f in p.filas))

    def test_exporta_csv_con_todas_las_filas(self):
        p = analizar_directorio(self.dir.name, 10)
        ruta = os.path.join(self.dir.name, "s.csv")
        a_csv(p, ruta)
        with open(ruta, encoding="utf-8") as f:
            filas = list(csv.reader(f))
        self.assertEqual(len(filas), 1 + len(p.filas))


if __name__ == "__main__":
    unittest.main()


class TestPanelGGPoker(unittest.TestCase):
    def test_agrupa_por_stake_y_umbral_completa(self):
        from tests.test_ggpoker import SIN_SHOWDOWN
        otro = SIN_SHOWDOWN.replace("$0.25/$0.50", "$0.50/$1")  # otro stake; solo cambia la cabecera
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.txt"), "w", encoding="utf-8") as f:
                f.write(SIN_SHOWDOWN + "\n\n" + otro)
            p = analizar_directorio(d, formato="ggpoker")
        self.assertEqual({f.stake for f in p.filas}, {50, 100})
        self.assertTrue(all(f.muestra_suficiente for f in p.filas))  # todos jugaron todas las manos del stake
        self.assertEqual(p.manos_validas, 2)

    def test_phh_tambien_agrupa_por_stake_automaticamente(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "0.phh"), "w", encoding="utf-8") as f:
                f.write(MANO)
            p = analizar_directorio(d)
        self.assertEqual({f.stake for f in p.filas}, {10})

    def test_mano_sin_big_blind_exige_bb(self):
        from poker_analisis.panel import analizar_manos
        from poker_analisis.real import desde_phh
        m = desde_phh(MANO)
        m.ciega_grande = None
        with self.assertRaises(ValueError):
            analizar_manos([m])
