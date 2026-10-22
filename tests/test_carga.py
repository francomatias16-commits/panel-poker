import unittest

from poker_analisis import carga
from poker_analisis.ggpoker import desde_ggpoker
from tests.test_ggpoker import CON_SHOWDOWN, SIN_SHOWDOWN


class CursorFalso:
    def __init__(self):
        self.llamadas = []

    def execute(self, sql, params=None):
        self.llamadas.append(("execute", sql, [params]))

    def executemany(self, sql, params):
        self.llamadas.append(("executemany", sql, list(params)))


class TestCarga(unittest.TestCase):
    def setUp(self):
        self.manos = [desde_ggpoker(SIN_SHOWDOWN), desde_ggpoker(CON_SHOWDOWN)]

    def test_parametros_coinciden_con_los_marcadores(self):
        for m in self.manos:
            for tipo, filas in carga.parametros(m, "f", "sal").items():
                for p in filas:
                    self.assertEqual(carga.SQL[tipo].count("%s"), len(p), tipo)

    def test_no_hay_nombres_reales_en_los_parametros(self):
        texto = str(carga.lote(self.manos, "f", "sal"))
        for nombre in ("aaaa1111", "Hero", "cccc3333"):
            self.assertNotIn(nombre, texto)

    def test_conteos_por_lote(self):
        t = carga.lote(self.manos, "f", "sal")
        self.assertEqual(len(t["mano"]), 2)
        self.assertEqual(len(t["asiento"]), 5)  # 3 + 2 asientos
        self.assertEqual(len(t["jugador"]), 4)  # Hero aparece en las dos manos: se envía una sola vez
        self.assertEqual(len({j[0] for j in t["jugador"]}), 4)  # 4 jugadores distintos
        self.assertEqual(t["mano"][0][0], "HD100001")
        self.assertEqual(t["mano"][0][4:6], (25, 50))

    def test_cargar_ejecuta_en_orden_y_sin_commit(self):
        cur = CursorFalso()
        n = carga.cargar(cur, self.manos, "f", "propio", "ggpoker-txt", "sal", tamano_lote=1)
        self.assertEqual(n, 2)
        self.assertEqual(cur.llamadas[0][0], "execute")
        self.assertFalse(hasattr(cur, "commit"))
        orden = [c[1] for c in cur.llamadas[1:]]
        # dentro de cada lote: jugadores, manos, asientos, acciones
        self.assertTrue(orden[0].startswith("insert into poker.jugadores"))
        self.assertTrue(orden[1].startswith("insert into poker.manos"))
        self.assertTrue(orden[2].startswith("insert into poker.asientos"))

    def test_literalizar_valores_infinitos_son_sql_valido(self):
        sql = carga.literalizar("values (%s, %s, %s)", (float("inf"), float("-inf"), float("nan")))
        self.assertEqual(sql, "values ('Infinity', '-Infinity', 'NaN')")

    def test_todas_las_sentencias_son_idempotentes_y_con_schema(self):
        for sql in carga.SQL.values():
            self.assertIn("on conflict", sql)
            self.assertIn("poker.", sql)

    def test_literalizar_escapa_comillas_y_tipos(self):
        s = carga.literalizar("values (%s, %s, %s, %s)", ("O'Hara", None, True, 1.5))
        self.assertEqual(s, "values ('O''Hara', null, true, 1.5)")
        with self.assertRaises(ValueError):
            carga.literalizar("%s %s", (1,))

    def test_mano_sin_referencia_se_rechaza(self):
        m = self.manos[0]
        m.referencia = None
        with self.assertRaises(ValueError):
            carga.parametros(m, "f", "sal")


if __name__ == "__main__":
    unittest.main()
