"""Pruebas de la conversión a filas y del esquema de base de datos."""
import os
import re
import unittest

from poker_analisis.almacen import filas_de_mano, seudonimo
from poker_analisis.real import desde_phh

MANO = """variant = 'NT'
antes = [0, 0]
blinds_or_straddles = [5, 10]
starting_stacks = [1920, 1920]
actions = ['d dh p1 ????', 'd dh p2 AsKd', 'p2 cc', 'p1 f']
players = ['Ana', 'Beto']
winnings = [0, 15]
"""
RUTA = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


class TestFilas(unittest.TestCase):
    def setUp(self):
        self.filas = filas_de_mano(desde_phh(MANO), "h1", "sal", 5, 10, archivo="a.phhs")

    def test_mano_guarda_ciegas_y_archivo(self):
        m = self.filas["mano"]
        self.assertEqual((m["blind_chico"], m["blind_grande"], m["archivo"]), (5, 10, "a.phhs"))

    def test_no_aparece_el_nombre_real(self):
        texto = str(self.filas)
        self.assertNotIn("Ana", texto)
        self.assertNotIn("Beto", texto)

    def test_seudonimo_estable_y_depende_de_la_sal(self):
        self.assertEqual(seudonimo("Ana", "s"), seudonimo("Ana", "s"))
        self.assertNotEqual(seudonimo("Ana", "s"), seudonimo("Ana", "t"))

    def test_cartas_ocultas_son_nulas_y_conocidas_no(self):
        a = self.filas["asientos"]
        self.assertIsNone(a[0]["cartas"])
        self.assertEqual(a[1]["cartas"], "As Kd")

    def test_netos_suman_cero_y_acciones_ordenadas(self):
        self.assertEqual(sum(a["neto"] for a in self.filas["asientos"]), 0)
        self.assertEqual([x["orden"] for x in self.filas["acciones"]], list(range(len(self.filas["acciones"]))))


class TestEsquema(unittest.TestCase):
    def setUp(self):
        with open(RUTA, encoding="utf-8") as f:
            self.sql = f.read()

    def test_todas_las_tablas_tienen_rls(self):
        tablas = re.findall(r"create table if not exists poker\.(\w+)", self.sql)
        self.assertEqual(len(tablas), 5)
        for t in tablas:
            self.assertRegex(self.sql, rf"alter table poker\.{t}\s+enable row level security")

    def test_parentesis_balanceados(self):
        self.assertEqual(self.sql.count("("), self.sql.count(")"))

    def test_ninguna_tabla_queda_sin_schema(self):
        self.assertNotRegex(self.sql, r"create table if not exists (?!poker\.)")
        self.assertNotRegex(self.sql, r"references (?!poker\.)")
        self.assertNotIn("search_path", self.sql)


if __name__ == "__main__":
    unittest.main()
