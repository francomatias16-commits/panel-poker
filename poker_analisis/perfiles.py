"""Perfiles de juego (Fase 2 del plan).

Clasifica a cada jugador en uno de cinco perfiles a partir de dos ejes medidos en sus manos:

- Soltura: VPIP (porcentaje de manos que juega voluntariamente).
- Agresión: proporción de agresiones sobre agresiones + igualaciones en flop, turn y river. Equivale al factor de
  agresión AF = p / (1 - p); se trabaja con p para no dividir por cero cuando el jugador nunca iguala.

Perfiles (tight pasivo, tight agresivo, agresivo suelto, estación de llamadas, maniático):

    VPIP < VPIP_SUELTO,  AF < AF_AGRESIVO   -> tight pasivo
    VPIP < VPIP_SUELTO,  AF >= AF_AGRESIVO  -> tight agresivo
    VPIP >= VPIP_SUELTO, AF < AF_AGRESIVO   -> estación de llamadas
    VPIP >= VPIP_SUELTO, AF >= AF_AGRESIVO  -> agresivo suelto
    VPIP >= VPIP_MANIATICO y AF >= AF_MANIATICO -> maniático

Estimación bayesiana: cada eje es una proporción con previa Beta centrada en un jugador típico de 6-max y de peso
débil (PESO_PREVIA observaciones). Se muestrea el posterior y se cuenta qué fracción de las muestras cae en cada
perfil: eso da una probabilidad por perfil, no solo una etiqueta. Con pocas manos el posterior es ancho, las
probabilidades se reparten y el perfil queda marcado como provisorio.

Todos los umbrales y las previas son decisiones de este módulo (convenciones habituales de 6-max, no resultados
medidos) y se cambian en las constantes de abajo. Los ajustes sugeridos son orientativos: cada uno nombra la
estadística que lo motiva y su tamaño de muestra.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .estadisticas_completas import MUESTRA_BAJA, MUESTRA_INSUFICIENTE, Frecuencia, ReporteJugador

# Umbrales de clasificación
VPIP_SUELTO = 0.28
VPIP_MANIATICO = 0.45
AF_AGRESIVO = 1.5
AF_MANIATICO = 3.0

# Previas (jugador típico de 6-max) y su peso en observaciones equivalentes
PREVIA_VPIP, PESO_VPIP = 0.25, 20.0
PREVIA_PFR, PESO_PFR = 0.18, 20.0
PREVIA_AGRESION, PESO_AGRESION = 0.55, 10.0  # p = 0,55 equivale a un AF de 1,2

# Criterio de perfil firme
PROB_FIRME = 0.80  # probabilidad mínima del perfil más probable
MANOS_FIRME = MUESTRA_BAJA  # manos mínimas para dejar de marcarlo provisorio
MANOS_MINIMAS = MUESTRA_INSUFICIENTE  # por debajo de esto no se emite perfil

MUESTRAS = 4000
SEMILLA = 2024

TIGHT_PASIVO = "tight pasivo"
TIGHT_AGRESIVO = "tight agresivo"
AGRESIVO_SUELTO = "agresivo suelto"
ESTACION = "estación de llamadas"
MANIATICO = "maniático"
PERFILES = (TIGHT_PASIVO, TIGHT_AGRESIVO, AGRESIVO_SUELTO, ESTACION, MANIATICO)

P_AGRESIVO = AF_AGRESIVO / (1 + AF_AGRESIVO)  # AF >= 1,5  <=>  p >= 0,6
P_MANIATICO = AF_MANIATICO / (1 + AF_MANIATICO)  # AF >= 3  <=>  p >= 0,75


def clasificar(vpip: float, p_agresion: float) -> str:
    """Perfil de un par (VPIP, proporción de agresión) ya conocido."""
    if vpip >= VPIP_MANIATICO and p_agresion >= P_MANIATICO:
        return MANIATICO
    suelto, agresivo = vpip >= VPIP_SUELTO, p_agresion >= P_AGRESIVO
    if suelto:
        return AGRESIVO_SUELTO if agresivo else ESTACION
    return TIGHT_AGRESIVO if agresivo else TIGHT_PASIVO


@dataclass
class Estimacion:
    """Proporción con su posterior Beta: media y intervalo creíble al 95 %."""

    exitos: int
    n: int
    media: float
    inf: float
    sup: float


def _beta(exitos: int, n: int, previa: float, peso: float, rng: random.Random) -> Tuple[Estimacion, List[float]]:
    a, b = previa * peso + exitos, (1 - previa) * peso + (n - exitos)
    muestras = sorted(rng.betavariate(a, b) for _ in range(MUESTRAS))
    est = Estimacion(exitos, n, a / (a + b), muestras[int(0.025 * MUESTRAS)], muestras[int(0.975 * MUESTRAS) - 1])
    return est, muestras


@dataclass
class Ajuste:
    texto: str
    base: str  # estadística que lo motiva, con su valor y su muestra


@dataclass
class PerfilJugador:
    nombre: str
    manos: int
    perfil: Optional[str]  # None si hay menos de MANOS_MINIMAS manos
    provisorio: bool
    motivo: str
    probabilidades: Dict[str, float]
    vpip: Optional[Estimacion]
    pfr: Optional[Estimacion]
    agresion: Optional[Estimacion]  # proporción p; AF = p / (1 - p)
    af_observado: Optional[float]  # agresiones / igualaciones sin suavizar (None si nunca igualó)
    ajustes: List[Ajuste] = field(default_factory=list)

    @property
    def af_estimado(self) -> Optional[float]:
        """AF del posterior (a partir de la media de p); None sin datos postflop."""
        if self.agresion is None:
            return None
        return self.agresion.media / (1 - self.agresion.media)


def _frec(rep: ReporteJugador, clave: str) -> Optional[Frecuencia]:
    f = rep.frecuencias.get(clave)
    return f if f is not None and f.n else None


def _agresion_total(rep: ReporteJugador) -> Tuple[int, int]:
    return (sum(r.agresiones for r in rep.agresion.values()), sum(r.igualaciones for r in rep.agresion.values()))


def _etiqueta(f: Frecuencia, nombre: str) -> str:
    return f"{nombre} {100 * f.valor:.0f} % en {f.n} oportunidades ({f.muestra})"


def _ajustes(perfil: str, rep: ReporteJugador, pfr: Optional[Estimacion], vpip: Optional[Estimacion]) -> List[Ajuste]:
    """Ajustes por perfil, más ajustes puntuales que salen de estadísticas con muestra suficiente."""
    out: List[Ajuste] = []
    base_vpip = f"VPIP {100 * vpip.media:.0f} % (estimado, {vpip.n} manos)" if vpip else ""
    af = _agresion_total(rep)
    base_af = f"agresión {af[0]} / {af[1]} (agresiones / igualaciones)"

    if perfil == TIGHT_PASIVO:
        out += [Ajuste("Robale las ciegas con frecuencia: se retira mucho.", base_vpip),
                Ajuste("Cuando apuesta o sube con fuerza, respetalo: su rango es fuerte y casi sin faroles.", base_af),
                Ajuste("No le pagues apuestas grandes con manos marginales.", base_af)]
    elif perfil == TIGHT_AGRESIVO:
        out += [Ajuste("Evitá enfrentarlo sin posición con manos marginales: su rango es fuerte y apuesta con iniciativa.", base_af),
                Ajuste("Sus robos de ciegas son selectivos: defendé con manos con buena jugabilidad, no con cualquier mano.", base_vpip),
                Ajuste("Contra sus c-bets, subí o igualá con manos que conecten; retirarte siempre lo hace rentable.", base_af)]
    elif perfil == AGRESIVO_SUELTO:
        out += [Ajuste("Ampliá tu rango de pago contra sus apuestas: juega muchas manos y farolea con frecuencia.", base_vpip),
                Ajuste("Preferí 3-betear por valor y dejarlo farolear, antes que farolear contra su rango amplio.", base_vpip),
                Ajuste("Con manos medias, controlá el bote igualando en vez de inflarlo.", base_af)]
    elif perfil == ESTACION:
        out += [Ajuste("Apostá por valor fino en las tres calles: iguala con manos débiles.", base_vpip),
                Ajuste("No farolees en su contra: rara vez se retira.", base_vpip),
                Ajuste("Cuando por fin apuesta o sube, tomalo como una mano fuerte.", base_af)]
    elif perfil == MANIATICO:
        out += [Ajuste("Pagale más ligero con manos de fuerza media: su rango de apuesta incluye muchos faroles.", base_af),
                Ajuste("Dejalo apostar y pagale con manos que le ganan a un rango amplio, en vez de subir de más.", base_af),
                Ajuste("Esperá manos buenas y dejá que se pase de rosca; evitá farolear a quien nunca se retira.", base_vpip)]

    # Ajustes puntuales: solo con muestra aceptable de esa estadística, para no sacar consejos de ruido.
    f = _frec(rep, "fold_cbet_flop")
    if f and f.n >= MUESTRA_BAJA:
        if f.valor >= 0.60:
            out.append(Ajuste("Hacé c-bet en el flop con más frecuencia, incluso con aire: se retira seguido.", _etiqueta(f, "retiro ante c-bet")))
        elif f.valor <= 0.35:
            out.append(Ajuste("Reducí los c-bets de farol en el flop: casi no se retira. Apostá más por valor.", _etiqueta(f, "retiro ante c-bet")))
    f = _frec(rep, "fold_3bet")
    if f and f.n >= MUESTRA_BAJA:
        if f.valor >= 0.65:
            out.append(Ajuste("3-beteale de farol con manos que bloquean: se retira ante el 3-bet.", _etiqueta(f, "retiro ante 3-bet")))
        elif f.valor <= 0.40:
            out.append(Ajuste("3-beteale solo por valor: rara vez se retira ante el 3-bet.", _etiqueta(f, "retiro ante 3-bet")))
    f = _frec(rep, "wtsd")
    if f and f.n >= MUESTRA_BAJA:
        if f.valor >= 0.33:
            out.append(Ajuste("Llega mucho al showdown: apostá más por valor y farolea menos en el river.", _etiqueta(f, "WTSD")))
        elif f.valor <= 0.20:
            out.append(Ajuste("Llega poco al showdown: los faroles del turn y del river funcionan mejor.", _etiqueta(f, "WTSD")))
    f = _frec(rep, "bb_robo_fold")
    if f and f.n >= MUESTRA_BAJA and f.valor >= 0.70:
        out.append(Ajuste("Robale la ciega grande más seguido: se retira ante los robos.", _etiqueta(f, "retiro de la ciega grande ante robos")))
    if pfr is not None and vpip is not None and vpip.media - pfr.media >= 0.15 and vpip.n >= MUESTRA_BAJA:
        out.append(Ajuste("Entra de limp o iguala preflop con frecuencia: aislalo subiendo con manos de valor y con posición.",
                          f"VPIP {100 * vpip.media:.0f} % contra PFR {100 * pfr.media:.0f} % (estimados, {vpip.n} manos)"))
    return out


def perfil_de(rep: ReporteJugador) -> PerfilJugador:
    """Perfil de un jugador a partir de su reporte de estadísticas completas."""
    rng = random.Random(f"{SEMILLA}:{rep.nombre}")
    fv, fp = _frec(rep, "vpip"), _frec(rep, "pfr")
    ag, ig = _agresion_total(rep)
    vpip = pfr = agresion = None
    mv: List[float] = []
    ma: List[float] = []
    if fv:
        vpip, mv = _beta(fv.exitos, fv.n, PREVIA_VPIP, PESO_VPIP, rng)
    if fp:
        pfr, _ = _beta(fp.exitos, fp.n, PREVIA_PFR, PESO_PFR, rng)
    # Sin acciones postflop el eje de agresión queda en la previa: el posterior es tan ancho como la previa.
    agresion, ma = _beta(ag, ag + ig, PREVIA_AGRESION, PESO_AGRESION, rng)
    af_obs = ag / ig if ig else None

    if rep.manos < MANOS_MINIMAS or vpip is None:
        return PerfilJugador(rep.nombre, rep.manos, None, True,
                             f"Menos de {MANOS_MINIMAS} manos: no alcanza para emitir un perfil.", {}, vpip, pfr, agresion, af_obs)

    cuenta = {p: 0 for p in PERFILES}
    for v, a in zip(mv, ma):
        cuenta[clasificar(v, a)] += 1
    probs = {p: c / MUESTRAS for p, c in cuenta.items()}
    perfil = max(probs, key=probs.get)

    razones = []
    if probs[perfil] < PROB_FIRME:
        razones.append(f"el perfil más probable tiene {100 * probs[perfil]:.0f} % (se pide {100 * PROB_FIRME:.0f} %)")
    if rep.manos < MANOS_FIRME:
        razones.append(f"solo {rep.manos} manos (se piden {MANOS_FIRME})")
    if ag + ig < MUESTRA_INSUFICIENTE:
        razones.append(f"solo {ag + ig} acciones postflop para medir la agresión")
    provisorio = bool(razones)
    motivo = ("Provisorio: " + "; ".join(razones) + ".") if provisorio else "Firme: muestra y probabilidad suficientes."

    return PerfilJugador(rep.nombre, rep.manos, perfil, provisorio, motivo, probs, vpip, pfr, agresion, af_obs,
                         _ajustes(perfil, rep, pfr, vpip))


def perfiles(reportes: Dict[str, ReporteJugador]) -> Dict[str, PerfilJugador]:
    return {n: perfil_de(r) for n, r in reportes.items()}


def formatear(p: PerfilJugador) -> str:
    """Informe de un rival en texto plano: perfil, qué lo define y cómo explotarlo."""
    L = [f"# {p.nombre}", ""]
    if p.perfil is None:
        return "\n".join(L + [p.motivo]) + "\n"
    L.append(f"Perfil: {p.perfil}{' (provisorio)' if p.provisorio else ''}. {p.motivo}")
    L += ["", "Qué lo define:"]
    v, a = p.vpip, p.agresion
    L.append(f"- VPIP {100 * v.media:.0f} % (intervalo creíble {100 * v.inf:.0f} a {100 * v.sup:.0f} %, {v.n} manos).")
    if p.pfr:
        L.append(f"- PFR {100 * p.pfr.media:.0f} % (intervalo creíble {100 * p.pfr.inf:.0f} a {100 * p.pfr.sup:.0f} %).")
    if a.n:
        obs = f"AF observado {p.af_observado:.1f}" if p.af_observado is not None else "nunca igualó postflop"
        L.append(f"- Agresión postflop: {a.exitos} agresiones en {a.n} acciones ({obs}); intervalo creíble de la proporción "
                 f"{100 * a.inf:.0f} a {100 * a.sup:.0f} %.")
    else:
        L.append("- Agresión postflop: sin acciones postflop registradas; el eje queda en la previa.")
    L += ["", "Probabilidad por perfil:"]
    for nombre, pr in sorted(p.probabilidades.items(), key=lambda t: -t[1]):
        if pr >= 0.005:
            L.append(f"- {nombre}: {100 * pr:.0f} %")
    L += ["", "Cómo explotarlo:"]
    for aj in p.ajustes:
        L.append(f"- {aj.texto} (base: {aj.base})")
    if p.provisorio:
        L.append("- Tomá estos ajustes con cautela: el perfil todavía puede cambiar con más manos.")
    return "\n".join(L) + "\n"
