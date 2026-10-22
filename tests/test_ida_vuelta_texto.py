"""Ida y vuelta: manos jugadas por el motor -> historial en texto estilo PokerStars -> importador.

Cada mano exportada se lee con `desde_ggpoker` y se compara contra el resultado original del motor
(netos, stacks, botón y ciegas, tablero, acciones, showdown). Cubre all-ins, botes laterales, apuestas
sin igualar y rake, de 2 a 6 jugadores. No reemplaza la validación con historiales reales (Fase 0),
pero detecta cualquier error de aritmética o de orden en el importador.
"""
import random
import unittest
from datetime import datetime, timedelta

from poker_analisis.bots import BotAleatorio
from poker_analisis.cartas import Mazo
from poker_analisis.ggpoker import desde_ggpoker, separar_manos
from poker_analisis.motor import jugar_mano


def _d(centavos: int) -> str:
    return f"${centavos / 100:.2f}"


def exportar(r, ident: int, rake_pct: int = 0):
    """Escribe una mano del motor como historial de texto. Devuelve (texto, netos_esperados, cobraron).

    Las fichas del motor valen 1 centavo. El rake, si hay, se descuenta del primer ganador.
    """
    n = len(r.neto)
    nom = [f"P{i + 1}" for i in range(n)]
    fecha = datetime(2026, 3, 1, 20, 0, 0) + timedelta(seconds=30 * ident)
    # Ciegas: se infieren de lo que pagó cada uno; el motor no las trae como eventos.
    ciega_chica, ciega_grande = r.ciega_chica, r.ciega_grande
    out = [
        f"PokerStars Hand #{9000000 + ident}:  Hold'em No Limit ({_d(int(ciega_chica))}/{_d(ciega_grande)} USD) - {fecha:%Y/%m/%d %H:%M:%S} ET",
        f"Table 'Prueba' {n}-max Seat #{r.boton + 1} is the button",
    ]
    for i in range(n):
        out.append(f"Seat {i + 1}: {nom[i]} ({_d(r.stacks_iniciales[i])} in chips)")
    total = [0] * n
    calle_apuesta = [0] * n
    restante = list(r.stacks_iniciales)

    def poner(i, monto):
        monto = min(monto, restante[i])
        restante[i] -= monto
        total[i] += monto
        calle_apuesta[i] += monto
        return monto

    pb = poner(r.sb, int(ciega_chica))
    out.append(f"{nom[r.sb]}: posts small blind {_d(pb)}")
    pg = poner(r.bb, ciega_grande)
    out.append(f"{nom[r.bb]}: posts big blind {_d(pg)}")
    out.append("*** HOLE CARDS ***")
    if r.cartas[0]:
        out.append(f"Dealt to {nom[0]} [{' '.join(str(c) for c in r.cartas[0])}]")

    mayor = max(calle_apuesta)
    hubo_showdown = False
    calle = "preflop"
    for e in r.eventos:
        if e.tipo == "reparto_cartas":
            continue
        if e.tipo == "reparto_tablero":
            calle = e.calle
            calle_apuesta = [0] * n
            mayor = 0
            previo = list(r.tablero[:{"flop": 0, "turn": 3, "river": 4}[calle]])
            nuevas = " ".join(str(c) for c in e.cartas)
            if calle == "flop":
                out.append(f"*** FLOP *** [{nuevas}]")
            else:
                out.append(f"*** {calle.upper()} *** [{' '.join(str(c) for c in previo)}] [{nuevas}]")
            continue
        if e.tipo == "sm":
            if not hubo_showdown:
                out.append("*** SHOWDOWN ***")
                hubo_showdown = True
            out.append(f"{nom[e.jugador - 1]}: shows [{' '.join(str(c) for c in e.cartas)}]")
            continue
        i = e.jugador - 1
        if e.tipo == "f":
            out.append(f"{nom[i]}: folds")
        elif e.tipo == "cc":
            falta = mayor - calle_apuesta[i]
            if falta <= 0:
                out.append(f"{nom[i]}: checks")
            else:
                pagado = poner(i, falta)
                out.append(f"{nom[i]}: calls {_d(pagado)}" + (" and is all-in" if restante[i] == 0 else ""))
        else:  # cbr: el motor da el total de la calle
            objetivo = e.monto
            poner(i, objetivo - calle_apuesta[i])
            todo = " and is all-in" if restante[i] == 0 else ""
            if mayor == 0:
                out.append(f"{nom[i]}: bets {_d(objetivo)}{todo}")
            else:
                out.append(f"{nom[i]}: raises {_d(objetivo - mayor)} to {_d(objetivo)}{todo}")
            mayor = max(mayor, objetivo)

    # Apuesta sin igualar: lo que excede el segundo mayor aporte vuelve a quien más puso.
    orden = sorted(total, reverse=True)
    devuelto = [0] * n
    if orden[0] > orden[1]:
        tope = total.index(orden[0])
        devuelto[tope] = orden[0] - orden[1]
        out.append(f"Uncalled bet ({_d(devuelto[tope])}) returned to {nom[tope]}")
    bote = sum(total) - sum(devuelto)
    cobros = [r.neto[i] + total[i] - devuelto[i] for i in range(n)]
    rake = 0
    esperados = list(r.neto)
    ganadores = [i for i in range(n) if cobros[i] > 0]
    if rake_pct and ganadores and len(r.tablero) > 0:
        rake = bote * rake_pct // 100
        cobros[ganadores[0]] -= rake
        esperados[ganadores[0]] -= rake
    for i in ganadores:
        if cobros[i] > 0:
            out.append(f"{nom[i]} collected {_d(cobros[i])} from pot")
    out.append("*** SUMMARY ***")
    out.append(f"Total pot {_d(bote)} | Rake {_d(rake)}")
    return "\n".join(out), esperados, [i for i in range(n) if cobros[i] > 0]


class TestIdaYVuelta(unittest.TestCase):
    def _comparar(self, r, texto, esperados, cobraron):
        m = desde_ggpoker(texto)
        self.assertEqual(m.neto, esperados)
        self.assertEqual(m.boton, r.boton)
        self.assertEqual((m.sb, m.bb), (r.sb, r.bb))
        self.assertEqual(m.stacks_iniciales, r.stacks_iniciales)
        self.assertEqual(m.tablero, r.tablero)
        self.assertEqual(m.vieron_flop, r.vieron_flop)
        self.assertEqual(m.llegaron_showdown, r.llegaron_showdown)
        # El motor cuenta como ganador a quien recupera una apuesta sin igualar; el historial no lo cobra.
        self.assertEqual(m.ganadores_showdown, [g for g in r.ganadores_showdown if g in cobraron])
        acc_orig = [(e.calle, e.jugador, e.tipo) for e in r.eventos if e.tipo in ("f", "cc", "cbr")]
        acc_leidas = [(e.calle, e.jugador, e.tipo) for e in m.eventos if e.tipo in ("f", "cc", "cbr")]
        self.assertEqual(acc_leidas, acc_orig)
        self.assertLessEqual(sum(m.neto), 0)

    def test_manos_al_azar_de_2_a_6_jugadores_sin_rake(self):
        rng = random.Random(5)
        con_showdown = con_lateral = 0
        for k in range(600):
            n = rng.randint(2, 6)
            stacks = [rng.choice([40, 100, 200, 350]) for _ in range(n)]
            pol = [BotAleatorio(semilla=rng.randint(0, 10 ** 6)) for _ in range(n)]
            r = jugar_mano(stacks, rng.randrange(n), 1, 2, pol, Mazo(semilla=k))
            r.ciega_chica, r.ciega_grande = 1, 2
            texto, esperados, cobraron = exportar(r, k)
            self._comparar(r, texto, esperados, cobraron)
            con_showdown += bool(r.llegaron_showdown)
            con_lateral += len(set(stacks)) > 1 and any(s == 0 for s in r.stacks_finales)
        self.assertGreater(con_showdown, 100)  # la muestra realmente ejercita showdowns
        self.assertGreater(con_lateral, 5)  # y all-ins con stacks distintos

    def test_con_rake_el_neto_baja_y_el_bote_cierra(self):
        rng = random.Random(9)
        for k in range(200):
            n = rng.randint(2, 6)
            pol = [BotAleatorio(semilla=rng.randint(0, 10 ** 6)) for _ in range(n)]
            r = jugar_mano([200] * n, rng.randrange(n), 1, 2, pol, Mazo(semilla=1000 + k))
            r.ciega_chica, r.ciega_grande = 1, 2
            texto, esperados, _ = exportar(r, k, rake_pct=5)
            m = desde_ggpoker(texto)
            self.assertEqual(m.neto, esperados)

    def test_varias_manos_en_un_solo_texto(self):
        rng = random.Random(1)
        textos = []
        for k in range(20):
            pol = [BotAleatorio(semilla=k * 7 + j) for j in range(4)]
            r = jugar_mano([200] * 4, k % 4, 1, 2, pol, Mazo(semilla=k))
            r.ciega_chica, r.ciega_grande = 1, 2
            textos.append(exportar(r, k)[0])
        self.assertEqual(len(separar_manos("\n\n\n".join(textos))), 20)


if __name__ == "__main__":
    unittest.main()
