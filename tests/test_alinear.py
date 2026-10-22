import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import web  # noqa: E402


def almacen_con_fechas():
    a = web.Almacen()
    a.demo(40)
    base = datetime(2026, 10, 21, 20, 0, 0, tzinfo=timezone.utc)
    for k, m in enumerate(a.manos):
        m.fecha = base + timedelta(seconds=90 * k)  # una mano cada 90 s
    return a, base


class TestAlinear(unittest.TestCase):
    def test_por_hora_de_inicio(self):
        a, base = almacen_con_fechas()
        r = a.alinear({"jugador": "TAG-1", "inicio": (base - timedelta(seconds=30)).isoformat()})
        n = sum(1 for m in a.manos if "TAG-1" in m.nombres)
        self.assertEqual(len(r["marcas"]), n)
        self.assertEqual(r["marcas"][0]["t"] - 0, r["marcas"][0]["t"])
        for mk in r["marcas"]:
            self.assertEqual(mk["t"], 30 + 90 * mk["mano"])
            self.assertEqual(mk["paso"], 0)
        self.assertEqual([x["t"] for x in r["marcas"]], sorted(x["t"] for x in r["marcas"]))

    def test_por_ancla(self):
        a, base = almacen_con_fechas()
        ident = next(i for i, m in enumerate(a.manos) if "TAG-1" in m.nombres)
        r = a.alinear({"jugador": "TAG-1", "ancla": {"mano": ident, "t": 100.0}})
        mk = next(x for x in r["marcas"] if x["mano"] == ident)
        self.assertEqual(mk["t"], 100.0)
        otro = r["marcas"][-1]
        self.assertAlmostEqual(otro["t"] - 100.0, 90 * (otro["mano"] - ident), places=2)

    def test_duracion_y_fuera_del_video(self):
        a, base = almacen_con_fechas()
        r = a.alinear({"jugador": "TAG-1", "inicio": base.isoformat(), "duracion": 900})
        self.assertTrue(all(0 <= x["t"] <= 900 for x in r["marcas"]))
        self.assertGreater(r["fuera_del_video"], 0)
        r2 = a.alinear({"jugador": "TAG-1", "inicio": (base + timedelta(seconds=300)).isoformat()})
        self.assertTrue(all(x["t"] >= 0 for x in r2["marcas"]))  # las manos anteriores al video no entran

    def test_errores(self):
        a, base = almacen_con_fechas()
        for f in ({}, {"jugador": "nadie", "inicio": "2026-10-21T20:00:00"}, {"jugador": "TAG-1"},
                  {"jugador": "TAG-1", "ancla": {"mano": 9999, "t": 1}},
                  {"jugador": "TAG-1", "ancla": {"mano": 0, "t": -5}},
                  {"jugador": "TAG-1", "inicio": "2026-10-21T20:00:00", "duracion": 0}):
            with self.assertRaises((ValueError, KeyError)):
                a.alinear(f)

    def test_sin_fecha(self):
        a = web.Almacen()
        a.demo(20)
        for m in a.manos:
            m.fecha = None
        with self.assertRaises(ValueError):
            a.alinear({"jugador": "TAG-1", "inicio": "2026-10-21T20:00:00"})

    def test_hora_sin_zona_se_lee_como_la_del_historial(self):
        a, base = almacen_con_fechas()
        r = a.alinear({"jugador": "TAG-1", "inicio": "2026-10-21 20:00:00".replace(" ", "T")})
        self.assertEqual(next(x for x in r["marcas"])["t"], 90 * next(x for x in r["marcas"])["mano"])


if __name__ == "__main__":
    unittest.main()
