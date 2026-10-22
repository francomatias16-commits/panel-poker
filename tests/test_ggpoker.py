"""Pruebas con manos sintéticas escritas según el formato de texto de GGPoker.
No provienen de un archivo real: ver el aviso en poker_analisis/ggpoker.py."""
import unittest

from poker_analisis.estadisticas import calcular
from poker_analisis.ggpoker import desde_ggpoker, separar_manos
from poker_analisis.phh import ErrorPHH

SIN_SHOWDOWN = """Poker Hand #HD100001: Hold'em No Limit ($0.25/$0.50) - 2026/01/10 20:15:30
Table 'NLHBadger1' 3-max Seat #1 is the button
Seat 1: aaaa1111 ($50 in chips)
Seat 2: bbbb2222 ($50 in chips)
Seat 3: Hero ($50 in chips)
bbbb2222: posts small blind $0.25
Hero: posts big blind $0.50
*** HOLE CARDS ***
Dealt to Hero [Ks Qd]
aaaa1111: raises $1 to $1.50
bbbb2222: folds
Hero: calls $1
*** FLOP *** [2c 7d Th]
Hero: checks
aaaa1111: bets $2
Hero: folds
Uncalled bet ($2) returned to aaaa1111
aaaa1111 collected $3.00 from pot
*** SUMMARY ***
Total pot $3.25 | Rake $0.25
"""

CON_SHOWDOWN = """Poker Hand #HD100002: Hold'em No Limit ($0.25/$0.50) - 2026/01/10 20:16:30
Table 'NLHBadger1' 2-max Seat #1 is the button
Seat 1: Hero ($50 in chips)
Seat 2: cccc3333 ($10 in chips)
Hero: posts small blind $0.25
cccc3333: posts big blind $0.50
*** HOLE CARDS ***
Dealt to Hero [As Ah]
Hero: raises $1 to $1.50
cccc3333: calls $1
*** FLOP *** [2c 7d Th]
cccc3333: checks
Hero: bets $2
cccc3333: calls $2
*** TURN *** [2c 7d Th] [4s]
cccc3333: checks
Hero: checks
*** RIVER *** [2c 7d Th 4s] [9d]
cccc3333: checks
Hero: checks
*** SHOWDOWN ***
cccc3333: shows [Kd Qd]
Hero: shows [As Ah]
Hero collected $6.80 from pot
*** SUMMARY ***
"""

POKERSTARS = """PokerStars Hand #250000000001:  Hold'em No Limit (€0.05/€0.10 EUR) - 2026/01/10 20:15:30 CET
Table 'Alpha IV' 2-max Seat #1 is the button
Seat 1: Hero (€10 in chips)
Seat 2: Villano (€10 in chips)
Hero: posts small blind €0.05
Villano: posts big blind €0.10
*** HOLE CARDS ***
Dealt to Hero [As Ah]
Hero: raises €0.20 to €0.30
Villano: calls €0.20
*** FLOP *** [2c 7d Th]
Villano: checks
Hero: bets €0.40
Villano: folds
Uncalled bet (€0.40) returned to Hero
Hero collected €0.58 from pot
Hero: doesn't show hand
*** SUMMARY ***
"""


class TestGGPoker(unittest.TestCase):
    def test_neto_sin_showdown(self):
        m = desde_ggpoker(SIN_SHOWDOWN)
        self.assertEqual(m.nombres, ["aaaa1111", "bbbb2222", "Hero"])
        self.assertEqual(m.neto, [150, -25, -150])  # centavos; la suma es el rake (-25)
        self.assertEqual(m.ciega_grande, 50)
        self.assertEqual((m.boton, m.sb, m.bb), (0, 1, 2))
        self.assertEqual(m.vieron_flop, [0, 2])
        self.assertEqual(m.llegaron_showdown, [])
        self.assertEqual(str(m.cartas[2][0]), "Ks")
        self.assertEqual(m.cartas[0], ())

    def test_showdown_y_cartas_mostradas(self):
        m = desde_ggpoker(CON_SHOWDOWN)
        self.assertEqual(m.llegaron_showdown, [0, 1])
        self.assertEqual(m.ganadores_showdown, [0])
        self.assertEqual(len(m.tablero), 5)
        self.assertEqual(len(m.cartas[1]), 2)
        self.assertEqual(m.neto, [330, -350])  # bote 7,00 menos 0,20 de rake
        self.assertLessEqual(sum(m.neto), 0)

    def test_estadisticas_con_mano_ggpoker(self):
        s = {x.nombre: x for x in calcular([desde_ggpoker(SIN_SHOWDOWN)], [], 50)}
        self.assertEqual(s["aaaa1111"].pfr, 1.0)
        self.assertEqual(s["bbbb2222"].vpip, 0.0)

    def test_rechaza_omaha_torneo_y_registro_inconsistente(self):
        with self.assertRaises(ErrorPHH):
            desde_ggpoker(SIN_SHOWDOWN.replace("Hold'em No Limit", "PLO"))
        with self.assertRaises(ErrorPHH):
            desde_ggpoker(SIN_SHOWDOWN.replace("Poker Hand #HD100001", "Poker Hand #TM100001 Tournament"))
        with self.assertRaises(ErrorPHH):
            desde_ggpoker(SIN_SHOWDOWN.replace("collected $3.00", "collected $9.00"))
        with self.assertRaises(ErrorPHH):
            desde_ggpoker("basura")

    def test_formato_pokerstars_con_euros(self):
        m = desde_ggpoker(POKERSTARS)
        self.assertEqual(m.referencia, "250000000001")
        self.assertEqual((m.ciega_chica, m.ciega_grande), (5, 10))
        self.assertEqual(m.neto, [28, -30])  # el bote era 0,60 y el rake 0,02
        self.assertEqual(len(separar_manos(POKERSTARS + "\n\n" + SIN_SHOWDOWN)), 2)

    def test_torneo_pokerstars_se_rechaza_con_motivo(self):
        torneo = "PokerStars Hand #1: Tournament #99, $1+$0.10 USD Hold'em No Limit - Level I (10/20) - 2026/01/10"
        with self.assertRaisesRegex(ErrorPHH, "torneo"):
            desde_ggpoker(torneo)

    def test_separa_varias_manos(self):
        self.assertEqual(len(separar_manos(SIN_SHOWDOWN + "\n\n" + CON_SHOWDOWN)), 2)


AUSENTE = SIN_SHOWDOWN.replace("Seat 3: Hero ($50 in chips)", "Seat 3: Hero ($50 in chips)\nSeat 4: Dormido ($20 in chips) is sitting out")
TRES_BOTES = SIN_SHOWDOWN.replace("Total pot $3.25 | Rake $0.25", "Total pot $9.00 | Rake $0.25")


class TestEndurecimiento(unittest.TestCase):
    def test_jugador_ausente_no_cuenta_como_que_vio_el_flop(self):
        m = desde_ggpoker(AUSENTE)
        self.assertEqual(m.nombres, ["aaaa1111", "bbbb2222", "Hero"])
        self.assertEqual(m.vieron_flop, [0, 2])

    def test_fecha_de_la_cabecera(self):
        from datetime import datetime
        self.assertEqual(desde_ggpoker(SIN_SHOWDOWN).fecha, datetime(2026, 1, 10, 20, 15, 30))
        self.assertEqual(desde_ggpoker(POKERSTARS).fecha, datetime(2026, 1, 10, 20, 15, 30))

    def test_bote_que_no_cierra_se_rechaza_con_motivo(self):
        with self.assertRaisesRegex(ErrorPHH, "bote no cierra"):
            desde_ggpoker(TRES_BOTES)

    def test_bote_cierra_en_manos_validas(self):
        desde_ggpoker(SIN_SHOWDOWN)  # Total pot 3,25 = lo reconstruido; cobros 3,00 + rake 0,25

    def test_archivo_con_bom_y_saltos_de_linea_windows(self):
        import os
        import shutil
        import tempfile

        from poker_analisis.ggpoker import cargar_directorio

        raiz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, raiz, True)
        contenido = (SIN_SHOWDOWN + "\n\n" + CON_SHOWDOWN).replace("\n", "\r\n")
        with open(os.path.join(raiz, "a.txt"), "w", encoding="utf-8-sig", newline="") as f:
            f.write(contenido)
        manos, rechazos = cargar_directorio(raiz)
        self.assertEqual(len(manos), 2)
        self.assertEqual(rechazos, [])

    def test_error_inesperado_no_tumba_la_carga(self):
        import os
        import shutil
        import tempfile

        from poker_analisis.ggpoker import cargar_directorio

        raiz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, raiz, True)
        roto = SIN_SHOWDOWN.replace("[Ks Qd]", "[Zz Qd]")
        with open(os.path.join(raiz, "a.txt"), "w", encoding="utf-8") as f:
            f.write(roto + "\n\n" + CON_SHOWDOWN)
        manos, rechazos = cargar_directorio(raiz)
        self.assertEqual(len(manos), 1)
        self.assertEqual(len(rechazos), 1)


class TestOrdenDirectorio(unittest.TestCase):
    def test_directorio_en_orden_numerico(self):
        import os
        import shutil
        import tempfile

        from poker_analisis.ggpoker import cargar_directorio

        raiz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, raiz, True)
        for n in (10, 2, 1):
            with open(os.path.join(raiz, f"{n}.txt"), "w", encoding="utf-8") as f:
                f.write(SIN_SHOWDOWN)
        manos, _ = cargar_directorio(raiz)
        self.assertEqual([m.archivo for m in manos], ["1.txt", "2.txt", "10.txt"])


if __name__ == "__main__":
    unittest.main()
