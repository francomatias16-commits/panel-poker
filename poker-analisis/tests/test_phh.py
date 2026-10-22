import os
import tempfile
import unittest

from poker_analisis.cartas import Carta
from poker_analisis.phh import ErrorPHH, importar_archivo, parsear_mano

# Mano sintética de prueba, escrita a mano para validar el parser.
# NO es un dato de ningún jugador real ni de ningún dataset.
MANO_VALIDA = """
variant = "NT"
antes = [0, 0]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [200, 200]
actions = [
  "d dh p1 AsKd",
  "d dh p2 QcQh",
  "p1 cbr 6",
  "p2 cc",
  "d db 7h8c2s",
  "p2 cc",
  "p1 cbr 10",
  "p2 f",
]
"""


class TestParseoValido(unittest.TestCase):
    def test_mano_basica(self):
        m = parsear_mano(MANO_VALIDA)
        self.assertEqual(m.variante, "NT")
        self.assertEqual(m.stacks_iniciales, [200, 200])
        self.assertEqual(m.cartas_jugadores[1], (Carta.desde_texto("As"), Carta.desde_texto("Kd")))
        self.assertEqual(len(m.tablero), 3)

    def test_calles_se_asignan_correctamente(self):
        m = parsear_mano(MANO_VALIDA)
        calles = {e.calle for e in m.eventos}
        self.assertEqual(calles, {"preflop", "flop"})

    def test_apuesta_guarda_monto(self):
        m = parsear_mano(MANO_VALIDA)
        apuestas = [e for e in m.eventos if e.tipo == "cbr"]
        self.assertEqual([e.monto for e in apuestas], [6, 10])

    def test_comentarios_se_ignoran(self):
        texto = MANO_VALIDA.replace('"p2 cc",\n  "d db', '"# comentario",\n  "p2 cc",\n  "d db', 1)
        m = parsear_mano(texto)
        self.assertEqual(len(m.tablero), 3)

    def test_cartas_ocultas_en_reparto(self):
        texto = MANO_VALIDA.replace("AsKd", "????")  # cada '??' es una carta oculta
        m = parsear_mano(texto)
        self.assertEqual(m.cartas_jugadores[1], (None, None))


class TestRechazos(unittest.TestCase):
    def test_variante_fuera_de_alcance(self):
        with self.assertRaises(ErrorPHH):
            parsear_mano(MANO_VALIDA.replace('"NT"', '"F7S"'))

    def test_longitudes_inconsistentes(self):
        with self.assertRaises(ErrorPHH):
            parsear_mano(MANO_VALIDA.replace("antes = [0, 0]", "antes = [0, 0, 0]"))

    def test_carta_repetida_entre_jugadores(self):
        texto = MANO_VALIDA.replace("QcQh", "AsQh")
        with self.assertRaises(ErrorPHH):
            parsear_mano(texto)

    def test_carta_invalida(self):
        with self.assertRaises(ErrorPHH):
            parsear_mano(MANO_VALIDA.replace("AsKd", "XsKd"))

    def test_toml_invalido(self):
        with self.assertRaises(ErrorPHH):
            parsear_mano("variant = ")

    def test_accion_desconocida(self):
        with self.assertRaises(ErrorPHH):
            parsear_mano(MANO_VALIDA.replace('"p2 cc",\n  "d db', '"p2 xyz",\n  "d db', 1))


class TestImportacionArchivo(unittest.TestCase):
    def test_archivo_con_manos_validas_y_rechazadas(self):
        contenido = MANO_VALIDA + "\n\n\n" + MANO_VALIDA.replace('"NT"', '"F7S"') + "\n\n\n" + MANO_VALIDA
        with tempfile.NamedTemporaryFile("w", suffix=".phh", delete=False, encoding="utf-8") as f:
            f.write(contenido)
            ruta = f.name
        try:
            manos, rechazos = importar_archivo(ruta)
        finally:
            os.remove(ruta)
        self.assertEqual(len(manos), 2)
        self.assertEqual(len(rechazos), 1)
        self.assertIn("variante fuera de alcance", rechazos[0][1])


if __name__ == "__main__":
    unittest.main()
