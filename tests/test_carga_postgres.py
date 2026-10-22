"""Prueba de integración contra PostgreSQL real. Se omite salvo que se indique una base de prueba.

Uso:
    POKER_DSN_PRUEBA='postgresql://postgres@localhost:5432/pruebas' python3 -m unittest tests.test_carga_postgres

ATENCIÓN: borra el schema `poker` de esa base antes de correr. No usar con la base de datos real.
"""

import datetime as dt
import os
import random
import unittest

from poker_analisis import carga
from poker_analisis.real import desde_phh

DSN = os.environ.get("POKER_DSN_PRUEBA")
RAIZ = os.path.join(os.path.dirname(__file__), "..")
TXT = open(os.path.join(os.path.dirname(__file__), "fixtures", "pluribus_ejemplo.phh"), encoding="utf-8").read()


def sinteticas(n, jugadores=40):
    """Manos del fixture con nombres, fechas y netos distintos, para simular un lote real."""
    rng = random.Random(3)
    pool = [f"Jug{i}" for i in range(jugadores)]
    manos = []
    for i in range(n):
        t = TXT.replace("hand = 63", f"hand = {i}\nyear = 2019\nmonth = 7\nday = {1 + i // 400}\n"
                        f"time = '{(i % 400) // 20:02d}:{i % 20:02d}:00'")
        t = t.replace("['Bill', 'MrBlue', 'Pluribus', 'MrWhite', 'Budd', 'MrOrange']", str(rng.sample(pool, 6)))
        m = desde_phh(t)
        m.archivo = f"{i // 100}/{i}.phh"
        manos.append(m)
    return manos


@unittest.skipUnless(DSN, "definir POKER_DSN_PRUEBA para correr la prueba contra PostgreSQL")
class TestCargaContraPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with open(os.path.join(RAIZ, "db", "schema.sql"), encoding="utf-8") as f:
            cls.schema = f.read()

    def reiniciar(self):
        with self.psycopg.connect(DSN, autocommit=True) as c:
            c.execute("drop schema if exists poker cascade")
            for rol in ("anon", "authenticated"):  # roles que Supabase trae y el schema referencia
                c.execute(f"do $$ begin if not exists (select from pg_roles where rolname='{rol}') "
                          f"then create role {rol}; end if; end $$")
            c.execute(self.schema)

    def volcado(self):
        q = {
            "manos": "select m.mano_ref, m.archivo, m.jugada_en, m.n_jugadores, m.blind_chico, m.blind_grande, "
                     "m.boton, m.tablero from poker.manos m order by m.mano_ref",
            "asientos": "select m.mano_ref, a.asiento, j.seudonimo, a.stack_inicial, a.neto, a.cartas, a.vio_flop, "
                        "a.llego_showdown, a.gano_showdown from poker.asientos a join poker.manos m on m.id=a.mano_id "
                        "left join poker.jugadores j on j.id=a.jugador_id order by 1,2",
            "acciones": "select m.mano_ref, x.orden, x.calle, x.asiento, x.tipo, x.monto from poker.acciones x "
                        "join poker.manos m on m.id=x.mano_id order by 1,2",
            "jugadores": "select seudonimo from poker.jugadores order by 1",
        }
        with self.psycopg.connect(DSN) as c:
            return {k: c.execute(v).fetchall() for k, v in q.items()}

    def test_copy_y_filas_dan_el_mismo_contenido_y_son_idempotentes(self):
        manos = sinteticas(300)
        sal = "sal-de-prueba"

        def correr(fn, lista, **kw):
            with self.psycopg.connect(DSN) as conn:
                with conn.cursor() as cur:
                    fn(cur, lista, "pluribus", "CC BY 4.0", "phh", sal, **kw)

        self.reiniciar()
        correr(carga.cargar, manos, tamano_lote=500)
        por_filas = self.volcado()

        self.reiniciar()
        correr(carga.cargar_copy, iter(manos), tamano_lote=70)  # generador y lotes que no dividen exacto
        por_copy = self.volcado()
        self.assertEqual(por_copy, por_filas)
        self.assertEqual(len(por_copy["manos"]), 300)
        self.assertIsNotNone(por_copy["manos"][0][2])  # jugada_en cargada

        correr(carga.cargar_copy, manos, tamano_lote=5000)  # repetir no duplica
        self.assertEqual(self.volcado(), por_copy)

    def test_fecha_se_guarda_en_utc(self):
        self.reiniciar()
        manos = sinteticas(5)
        with self.psycopg.connect(DSN) as conn:
            with conn.cursor() as cur:
                carga.cargar_copy(cur, manos, "pluribus", "CC BY 4.0", "phh", "sal")
        guardadas = sorted(r[2] for r in self.volcado()["manos"])  # el volcado va por mano_ref, no por fecha
        self.assertEqual(guardadas, sorted(m.fecha for m in manos))
        self.assertEqual(guardadas[0], dt.datetime(2019, 7, 1, 0, 0, tzinfo=dt.timezone.utc))


if __name__ == "__main__":
    unittest.main()
