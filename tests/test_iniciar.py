import os
import subprocess
import sys
import unittest

import iniciar


class TestIniciar(unittest.TestCase):
    def test_version_vieja_se_rechaza_con_mensaje(self):
        with self.assertRaises(SystemExit) as c:
            iniciar.verificar_python((3, 9))
        self.assertIn("Python 3.11", str(c.exception))

    def test_version_actual_se_acepta(self):
        iniciar.verificar_python()

    def test_ayuda_desde_otro_directorio(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run([sys.executable, os.path.join(raiz, "iniciar.py"), "--help"], cwd="/", capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--demo", r.stdout)


if __name__ == "__main__":
    unittest.main()
