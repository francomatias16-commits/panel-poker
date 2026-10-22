'use strict';
/* Sala de repaso. Todo el texto que viene de los archivos se inserta con textContent (nunca innerHTML). */

// ---------------------------------------------------------------- utilidades
const $ = (id) => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';

function h(tag, attrs, ...hijos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  agregar(el, hijos);
  return el;
}
function sv(tag, attrs, ...hijos) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  agregar(el, hijos);
  return el;
}
function agregar(el, hijos) {
  for (const c of hijos.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
}
const vaciar = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
const pct = (v, d = 0) => (v === null || v === undefined ? '–' : (100 * v).toFixed(d) + '%');
const num = (v, d = 1) => (v === null || v === undefined ? '–' : Number(v).toFixed(d));
const signo = (v, d = 1) => (v > 0 ? '+' : '') + Number(v).toFixed(d);
const clasePN = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

function aviso(texto) {
  const a = $('aviso');
  a.textContent = texto; a.hidden = false;
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => { a.hidden = true; }, 5000);
}

async function api(ruta, cuerpo) {
  const r = await fetch(ruta, cuerpo === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo),
  });
  const d = await r.json().catch(() => ({ error: 'respuesta inválida' }));
  if (!r.ok) throw new Error(d.error || `error ${r.status}`);
  return d;
}

const ROJOS = new Set(['h', 'd']);
const PALOS = { c: '♣', d: '♦', h: '♥', s: '♠' };
function carta(txt, extra) {
  const rango = txt[0] === 'T' ? '10' : txt[0];
  return h('div', { class: 'carta' + (ROJOS.has(txt[1]) ? ' r' : '') + (extra ? ' ' + extra : ''), 'aria-label': txt }, rango,
    h('span', { class: 'palo' }, PALOS[txt[1]]));
}
const dorso = (extra) => h('div', { class: 'carta dorso' + (extra ? ' ' + extra : ''), 'aria-hidden': 'true' });
function miniCarta(txt) {
  return h('span', { class: 'mini' + (ROJOS.has(txt[1]) ? ' r' : '') }, (txt[0] === 'T' ? '10' : txt[0]) + PALOS[txt[1]]);
}

// ---------------------------------------------------------------- estado
const S = {
  estado: null, tab: 'panel', lista: { total: 0, filas: [] }, jugador: null, mano: null, paso: 0,
  tokenRefresco: 0, tokenMano: 0, auto: null,
};
const V = { el: null, url: null, nombre: '', clave: '', marcas: [], sync: true, avanzar: true, ultima: -1, timer: null };

function filtros() {
  const stake = $('f-stake').value;
  return {
    jugador: $('f-jugador').value || null,
    stake: stake === '' ? null : Number(stake),
    desde: $('f-desde').value || null,
    hasta: $('f-hasta').value || null,
    posiciones: [...document.querySelectorAll('#f-posiciones .chip[aria-pressed="true"]')].map((b) => b.dataset.pos),
    min_manos: Number($('f-min').value) || 0,
    metrica: $('f-metrica').value,
    solo_showdown: $('f-sd').checked,
    orden: $('f-orden').value,
  };
}

// ---------------------------------------------------------------- carga e inicio
async function iniciar() {
  try { S.estado = await api('/api/estado'); } catch (e) { aviso(e.message); return; }
  if (S.estado.cargando) return esperarCarga();
  poblarFiltros();
  if (S.estado.manos) refrescar(); else renderPanelVacio();
}

function textoFuente() {
  const e = S.estado;
  if (!e || !e.manos) return 'Sin manos cargadas';
  const rech = e.rechazos ? ` (${e.rechazos} archivos rechazados)` : '';
  return `${e.manos.toLocaleString('es')} manos de ${e.formato === 'demo' ? 'simulación' : e.ruta}${rech}`;
}

function poblarFiltros() {
  const e = S.estado;
  $('fuente-txt').textContent = textoFuente();
  const sj = vaciar($('f-jugador'));
  for (const j of e.jugadores) sj.append(h('option', { value: j.nombre }, `${j.nombre} (${j.manos})`));
  const ss = vaciar($('f-stake'));
  ss.append(h('option', { value: '' }, 'Todos'));
  for (const s of e.stakes) ss.append(h('option', { value: s }, String(s)));
  if (e.fecha_min) { $('f-desde').min = $('f-hasta').min = e.fecha_min.slice(0, 10); }
  if (e.fecha_max) { $('f-desde').max = $('f-hasta').max = e.fecha_max.slice(0, 10); }
  $('f-desde').disabled = $('f-hasta').disabled = !e.con_fecha;
  const cp = vaciar($('f-posiciones'));
  for (const p of e.posiciones || []) cp.append(h('button', { class: 'chip', type: 'button', 'aria-pressed': 'false', 'data-pos': p }, p));
}

function limpiarFiltros() {
  $('f-stake').value = ''; $('f-desde').value = ''; $('f-hasta').value = ''; $('f-min').value = 0;
  $('f-metrica').value = 'manos'; $('f-orden').value = 'cronologico'; $('f-sd').checked = false;
  document.querySelectorAll('#f-posiciones .chip').forEach((b) => b.setAttribute('aria-pressed', 'false'));
  refrescar();
}

async function esperarCarga() {
  $('fuente-txt').textContent = 'Cargando manos…';
  for (;;) {
    await new Promise((r) => setTimeout(r, 700));
    try { S.estado = await api('/api/estado'); } catch (e) { aviso(e.message); return; }
    if (!S.estado.cargando) break;
  }
  if (S.estado.error) { aviso(S.estado.error); $('fuente-txt').textContent = textoFuente(); return; }
  S.mano = null; S.jugador = null;
  poblarFiltros();
  cerrarVideoMarcas();
  refrescar();
}

let temporizador = null;
function refrescarPronto() { clearTimeout(temporizador); temporizador = setTimeout(refrescar, 180); }

async function refrescar() {
  if (!S.estado || !S.estado.manos) return;
  const token = ++S.tokenRefresco;
  const f = filtros();
  try {
    const [tabla, det, lista] = await Promise.all([
      api('/api/panel', f), api('/api/jugador', f), api('/api/manos', { ...f, limite: 200 }),
    ]);
    if (token !== S.tokenRefresco) return;
    S.tabla = tabla.filas; S.jugador = det; S.lista = lista;
    renderPanel();
    renderLista();
  } catch (e) { aviso(e.message); }
}

// ---------------------------------------------------------------- panel
function renderPanelVacio() {
  vaciar($('vista-panel')).append(h('div', { class: 'vacio-grande' },
    h('h2', {}, 'Todavía no hay manos'),
    h('p', {}, 'Cargá una carpeta con tus historiales, o probá con manos simuladas por los bots del proyecto.'),
    h('button', { class: 'btn primario', onclick: () => $('btn-cargar').click() }, 'Cargar manos')));
}

function renderPanel() {
  const cont = vaciar($('vista-panel'));
  const d = S.jugador;
  const f = filtros();
  if (!d || !d.manos) {
    cont.append(h('div', { class: 'vacio-grande' }, h('h2', {}, 'Sin manos con estos filtros'),
      h('p', {}, 'Ampliá las fechas, el stake o las posiciones.')));
    cont.append(bloqueTabla());
    return;
  }
  const st = d.stats;
  const dato = (valor, rotulo, cls) => h('div', { class: 'dato' }, h('span', { class: 'valor ' + (cls || '') }, valor), h('span', { class: 'rotulo' }, rotulo));
  const resumen = h('div', { class: 'resumen' },
    h('h2', {}, f.jugador),
    dato(d.manos.toLocaleString('es'), 'manos'),
    st ? dato(signo(st.bb100, 1), `bb/100 (±${num(st.ic95, 1)})`, clasePN(st.bb100)) : dato('–', 'bb/100 (hay varios stakes)'),
    dato(signo(d.total_bb, 1), 'bb en total', clasePN(d.total_bb)),
    dato(num(d.drawdown_bb, 1), 'bb de drawdown máximo'),
    st ? dato(pct(st.vpip), 'VPIP') : null, st ? dato(pct(st.pfr), 'PFR') : null,
    st ? dato(st.af === null ? '–' : num(st.af, 1), 'agresión') : null);
  cont.append(resumen);

  cont.append(bloqueCurva(d));
  cont.append(bloquePosiciones(d));
  cont.append(bloqueCompleto(d));
  cont.append(bloqueTabla());
}

let modoCurva = 'acum';
function bloqueCurva(d) {
  const caja = h('div', { class: 'bloque' });
  const botones = h('div', { class: 'der' },
    ...[['acum', 'Ganancia acumulada'], ['dd', 'Drawdown']].map(([k, t]) =>
      h('button', { class: 'chip', type: 'button', 'aria-pressed': String(modoCurva === k), onclick: () => { modoCurva = k; renderPanel(); } }, t)));
  caja.append(h('header', {}, h('h3', {}, modoCurva === 'acum' ? 'Cómo fue sumando en big blinds' : 'Cuánto cayó desde su máximo'), botones));
  caja.append(graficoCurva(d.curva));
  caja.append(h('p', { class: 'nota' }, 'Tocá un punto para abrir esa mano en el repaso.'));
  return caja;
}

function graficoCurva(c) {
  const W = 760, H = 240, m = { l: 48, r: 12, t: 10, b: 24 };
  const ys = modoCurva === 'acum' ? c.acum : c.dd.map((v) => -v);
  const lo = Math.min(0, ...ys), hi = Math.max(0, ...ys);
  const span = hi - lo || 1;
  const X = (i) => m.l + (c.n.length === 1 ? 0 : (i / (c.n.length - 1)) * (W - m.l - m.r));
  const Y = (v) => m.t + (1 - (v - lo) / span) * (H - m.t - m.b);
  const svg = sv('svg', { class: 'grafico', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Curva de resultados' });
  for (const v of marcasEje(lo, hi)) {
    const y = Y(v);
    svg.append(sv('line', { class: 'eje', x1: m.l, x2: W - m.r, y1: y, y2: y }),
      sv('text', { x: m.l - 6, y: y + 4, 'text-anchor': 'end' }, Math.round(v)));
  }
  const pts = ys.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`);
  const base = Y(0).toFixed(1);
  svg.append(sv('path', { class: modoCurva === 'acum' ? 'area' : 'caida', d: `M${X(0)},${base} L${pts.join(' L')} L${X(ys.length - 1)},${base} Z` }));
  svg.append(sv('line', { class: 'cero', x1: m.l, x2: W - m.r, y1: base, y2: base }));
  svg.append(sv('polyline', { class: 'linea', points: pts.join(' '), style: modoCurva === 'dd' ? 'stroke:var(--mal)' : '' }));
  svg.append(sv('text', { x: m.l, y: H - 6 }, 'mano 1'), sv('text', { x: W - m.r, y: H - 6, 'text-anchor': 'end' }, `mano ${c.n[c.n.length - 1]}`));
  const guia = sv('line', { x1: 0, x2: 0, y1: m.t, y2: H - m.b, stroke: 'var(--suave)', 'stroke-width': 1, visibility: 'hidden' });
  const etiqueta = sv('text', { x: 0, y: m.t + 10, 'text-anchor': 'middle', visibility: 'hidden', style: 'fill:var(--texto)' });
  svg.append(guia, etiqueta);
  const indice = (ev) => {
    const r = svg.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * W;
    return Math.max(0, Math.min(ys.length - 1, Math.round(((x - m.l) / (W - m.l - m.r)) * (ys.length - 1))));
  };
  svg.addEventListener('pointermove', (ev) => {
    const i = indice(ev), x = X(i);
    guia.setAttribute('x1', x); guia.setAttribute('x2', x); guia.setAttribute('visibility', 'visible');
    etiqueta.setAttribute('x', Math.min(Math.max(x, m.l + 50), W - 50)); etiqueta.setAttribute('visibility', 'visible');
    etiqueta.textContent = `mano ${c.n[i]}: ${signo(ys[i], 1)} bb`;
  });
  svg.addEventListener('pointerleave', () => { guia.setAttribute('visibility', 'hidden'); etiqueta.setAttribute('visibility', 'hidden'); });
  svg.addEventListener('click', (ev) => { irARepaso(c.ids[indice(ev)]); });
  svg.style.cursor = 'pointer';
  return svg;
}

const ETQ_STAT = {
  vpip: 'VPIP', pfr: 'PFR', '3bet': '3-bet', '4bet': '4-bet', fold_3bet: 'Fold a 3-bet (el que abrió)', robo: 'Robo de ciegas (CO, BTN, SB)',
  bb_robo_fold: 'BB ante robo: se retira', bb_robo_call: 'BB ante robo: iguala', bb_robo_3bet: 'BB ante robo: 3-bet',
  cbet_flop: 'C-bet en el flop', barril_turn: 'Segunda apuesta (turn)', barril_river: 'Tercera apuesta (river)',
  fold_cbet_flop: 'Fold a c-bet (flop)', fold_barril_turn: 'Fold a la apuesta del turn', fold_barril_river: 'Fold a la apuesta del river',
  checkraise_flop: 'Check-raise (flop)', checkraise_turn: 'Check-raise (turn)', checkraise_river: 'Check-raise (river)',
  donk_flop: 'Donk bet (flop)', wtsd: 'WTSD (llega al showdown)', wsd: 'W$SD (gana en el showdown)',
  farol_river_visible: 'Apuesta de river que pierde en el showdown',
};
const GRUPOS_STAT = [
  ['Preflop', ['vpip', 'pfr', '3bet', '4bet', 'fold_3bet', 'robo', 'bb_robo_fold', 'bb_robo_call', 'bb_robo_3bet']],
  ['Postflop', ['cbet_flop', 'barril_turn', 'barril_river', 'fold_cbet_flop', 'fold_barril_turn', 'fold_barril_river',
    'checkraise_flop', 'checkraise_turn', 'checkraise_river', 'donk_flop']],
  ['Showdown', ['wtsd', 'wsd', 'farol_river_visible']],
];

function bloquePerfil(pf) {
  if (!pf) return h('div');
  const caja = h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, 'Perfil de juego'),
    h('span', { class: 'nota' }, pf.perfil ? (pf.provisorio ? 'Provisorio' : 'Firme') : 'Sin perfil')));
  if (!pf.perfil) { caja.append(h('p', { class: 'nota' }, pf.motivo)); return caja; }
  const probs = Object.entries(pf.probabilidades).sort((a, b) => b[1] - a[1]).filter(([, p]) => p >= 0.005);
  const est = (e) => (e ? `${pct(e.media, 0)} (${pct(e.inf, 0)} a ${pct(e.sup, 0)})` : '–');
  caja.append(h('p', {}, h('strong', {}, pf.perfil), ' — ', pf.motivo),
    h('div', { class: 'resumen' },
      h('div', { class: 'dato' }, h('span', { class: 'valor' }, est(pf.vpip)), h('span', { class: 'rotulo' }, 'VPIP estimado (intervalo creíble 95 %)')),
      h('div', { class: 'dato' }, h('span', { class: 'valor' }, est(pf.pfr)), h('span', { class: 'rotulo' }, 'PFR estimado')),
      h('div', { class: 'dato' }, h('span', { class: 'valor' }, pf.af_observado === null ? '–' : num(pf.af_observado, 1)), h('span', { class: 'rotulo' }, 'AF observado postflop'))),
    h('p', { class: 'nota' }, 'Probabilidad por perfil: ' + probs.map(([n, p]) => `${n} ${pct(p, 0)}`).join('; ') + '.'),
    h('h4', {}, 'Cómo explotarlo'),
    h('ul', {}, ...pf.ajustes.map((a) => h('li', {}, a.texto + ' ', h('span', { class: 'nota' }, `(base: ${a.base})`)))),
    h('p', { class: 'nota' }, 'Umbrales de 6-max (VPIP suelto desde 28 %, agresivo desde AF 1,5, maniático desde VPIP 45 % y AF 3) y previas débiles: son convenciones del proyecto, no resultados medidos. Con pocas manos el perfil es provisorio.'));
  return caja;
}

function bloqueRiesgo(d) {
  const caja = h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, 'Riesgo y bankroll'), h('span', { class: 'nota' }, 'Propaga la incertidumbre del winrate')));
  const salida = h('div', {});
  const entrada = h('input', { type: 'number', min: '1', step: '1', value: '30', id: 'riesgo-entradas', 'aria-label': 'Bankroll en entradas de 100 big blinds', style: { width: '90px' } });
  const boton = h('button', { class: 'btn', type: 'button' }, 'Calcular');
  const calcular = async () => {
    const f = filtros();
    vaciar(salida).append(h('p', { class: 'nota' }, 'Calculando…'));
    boton.disabled = true;
    try {
      const r = await api('/api/riesgo', { jugador: f.jugador, stake: f.stake || null, bankroll_entradas: Number(entrada.value) });
      vaciar(salida);
      renderRiesgo(salida, r);
    } catch (e) { vaciar(salida).append(h('p', { class: 'neg' }, e.message)); }
    boton.disabled = false;
  };
  boton.addEventListener('click', calcular);
  caja.append(h('div', { class: 'resumen' }, h('label', {}, 'Bankroll (entradas de 100 bb): ', entrada), boton), salida);
  return caja;
}

function renderRiesgo(cont, r) {
  const dato = (v, t) => h('div', { class: 'dato' }, h('span', { class: 'valor' }, v), h('span', { class: 'rotulo' }, t));
  const dd = r.simulacion.drawdown_percentiles, ddf = r.simulacion_sin_incertidumbre.drawdown_percentiles;
  const acc = { subir: 'Subir de stake', mantener: 'Mantener el stake', bajar: 'Bajar de stake' }[r.decision.accion];
  cont.append(
    h('p', { class: 'nota' }, `${r.manos} manos: winrate ${signo(r.winrate_bb100, 1)} bb/100 (IC95 % de ${signo(r.ic95_bb100[0], 1)} a ${signo(r.ic95_bb100[1], 1)}); probabilidad de que el real sea positivo: ${pct(r.prob_winrate_positivo, 0)}. Entre paréntesis, lo que daría tomar el winrate observado como verdadero.`),
    h('div', { class: 'resumen' },
      dato(`${pct(r.ruina.predictiva, 1)} (${pct(r.ruina.con_estimado, 1)})`, `ruina con ${num(r.bankroll_entradas, 0)} entradas, horizonte infinito`),
      dato(`${pct(r.simulacion.prob_ruina, 1)} (${pct(r.simulacion_sin_incertidumbre.prob_ruina, 1)})`, `ruina dentro de ${r.horizonte.toLocaleString('es-AR')} manos`),
      dato(r.requerido_entradas === null ? 'ninguno alcanza' : num(r.requerido_entradas, 0) + ' entradas', 'bankroll para ruina de 5 % o menos')),
    h('div', { class: 'resumen' },
      dato([50, 90, 95, 99].map((p) => num(dd[p] / 100, 0)).join(' / '), `mayor drawdown en entradas (percentiles 50/90/95/99)`),
      dato(`(${[50, 90, 95, 99].map((p) => num(ddf[p] / 100, 0)).join(' / ')})`, 'con el winrate observado'),
      dato(pct(r.simulacion.prob_perder_al_final, 0), 'probabilidad de terminar en pérdida')),
    h('p', {}, r.kelly.completo_bb === null ? 'El winrate observado no es positivo: no hay bankroll de Kelly.'
      : `Kelly completo: ${num(r.kelly.completo_bb / 100, 0)} entradas; fracción ${r.kelly.fraccion}: ${num(r.kelly.fraccion_bb / 100, 0)}` + (r.kelly.conservador_bb ? `; con el límite inferior del IC95 %: ${num(r.kelly.conservador_bb / 100, 0)}.` : '; con el límite inferior del IC95 % el winrate no es positivo, así que no hay Kelly conservador.')),
    h('p', {}, h('strong', {}, acc + '. '), ...r.decision.motivos.map((m) => m + ' ')),
    h('p', { class: 'nota' }, 'Modelo browniano con manos independientes: no contempla rachas, cambios de nivel ni de rake. La regla de cambio de stake supone el mismo winrate en bb/100 en el stake superior. Con una muestra chica manda la incertidumbre: no tomes estas cifras como pronóstico.'));
}

function bloqueCompleto(d) {
  const c = d.completo;
  if (!c) return h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, 'Estadísticas completas')),
    h('p', { class: 'nota' }, 'Elegí un solo stake para ver las estadísticas completas.'));
  const por = {};
  for (const f of c.frecuencias) por[f.estadistica] = f;
  const filaStat = (clave, etiqueta) => {
    const f = por[clave];
    if (!f) return h('tr', {}, h('td', {}, etiqueta), h('td', { colspan: 4, class: 'nota' }, 'Sin oportunidades'));
    const ic = f.ic_inf === null ? '–' : `${pct(f.ic_inf)} a ${pct(f.ic_sup)}`;
    return h('tr', { class: f.muestra === 'insuficiente' ? 'muestra-poca' : '' }, h('td', {}, etiqueta), h('td', {}, pct(f.valor, 1)),
      h('td', {}, `${f.exitos} de ${f.n}`), h('td', {}, ic), h('td', {}, f.muestra === 'insuficiente' ? 'Muestra insuficiente' : f.muestra === 'baja' ? 'Muestra baja' : 'Muestra aceptable'));
  };
  const cabeza = h('thead', {}, h('tr', {}, ...['Estadística', 'Valor', 'Veces', 'Intervalo 95 %', 'Muestra'].map((t) => h('th', {}, t))));
  const tablas = GRUPOS_STAT.map(([titulo, claves]) => h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, titulo)),
    h('div', { class: 'tabla-scroll' }, h('table', {}, cabeza.cloneNode(true), h('tbody', {}, ...claves.map((k) => filaStat(k, ETQ_STAT[k])))))));
  const ag = c.frecuencias.filter((f) => f.estadistica.startsWith('af@'));
  const filasAf = ['flop', 'turn', 'river'].map((calle) => {
    const f = ag.find((x) => x.estadistica === 'af@' + calle);
    return h('tr', {}, h('td', {}, calle), h('td', {}, f && f.valor !== null ? num(f.valor, 2) : '–'), h('td', {}, f ? `${f.exitos} apuestas o subidas, ${f.n} igualaciones` : 'Sin datos'),
      h('td', {}, f ? (f.muestra === 'insuficiente' ? 'Muestra insuficiente' : f.muestra === 'baja' ? 'Muestra baja' : 'Muestra aceptable') : ''));
  });
  const tablaRes = (titulo, filas) => h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, titulo)),
    h('div', { class: 'tabla-scroll' }, h('table', {}, h('thead', {}, h('tr', {}, ...['Grupo', 'Manos', 'bb/100', '±IC95'].map((t) => h('th', {}, t)))),
      h('tbody', {}, ...filas.map((x) => h('tr', {}, h('td', {}, x.clave), h('td', {}, x.manos), h('td', { class: clasePN(x.bb100) }, signo(x.bb100, 1)), h('td', {}, x.ic95 === null ? '–' : num(x.ic95, 0))))))));
  return h('div', {}, bloquePerfil(c.perfil), bloqueRiesgo(d), h('h3', {}, 'Estadísticas completas'), ...tablas,
    h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, 'Agresión por calle (apuestas y subidas sobre igualaciones)')),
      h('div', { class: 'tabla-scroll' }, h('table', {}, h('thead', {}, h('tr', {}, ...['Calle', 'Factor', 'Detalle', 'Muestra'].map((t) => h('th', {}, t)))), h('tbody', {}, ...filasAf)))),
    tablaRes('Resultado por profundidad de stack', c.por_stack), tablaRes('Resultado por rivales en el flop', c.por_rivales),
    h('p', { class: 'nota' }, `Rake atribuido a las manos que ganó: ${num(c.rake_bb100, 2)} bb/100. Con menos de 30 oportunidades la estadística no es confiable; entre 30 y 100 es orientativa. Todavía no hay rangos de referencia: se calibran con fuentes confiables antes de usarlos como criterio.`));
}

function bloquePosiciones(d) {
  if (!d.posiciones || !d.posiciones.length) return h('div');
  const maxAbs = Math.max(1, ...d.posiciones.map((p) => Math.abs(p.bb100)));
  const filas = d.posiciones.map((p) => h('tr', {},
    h('td', {}, p.posicion), h('td', {}, p.manos),
    h('td', { class: clasePN(p.bb100) }, h('span', { class: 'barra-valor', style: { width: `${Math.round((Math.abs(p.bb100) / maxAbs) * 70)}px`, background: p.bb100 >= 0 ? 'var(--bien)' : 'var(--mal)' } }), signo(p.bb100, 1)),
    h('td', {}, pct(p.vpip)), h('td', {}, pct(p.pfr)), h('td', {}, pct(p.tres_bet))));
  return h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, 'Resultado por posición')),
    h('div', { class: 'tabla-scroll' }, h('table', {},
      h('thead', {}, h('tr', {}, ...['Posición', 'Manos', 'bb/100', 'VPIP', 'PFR', '3-bet'].map((t) => h('th', {}, t)))),
      h('tbody', {}, filas))),
    h('p', { class: 'nota' }, 'Con pocas manos por posición, los bb/100 varían muchísimo: mirá el tamaño de la muestra antes de sacar conclusiones.'));
}

const COLS = [['jugador', 'Jugador'], ['manos', 'Manos'], ['vpip', 'VPIP'], ['pfr', 'PFR'], ['tres_bet', '3-bet'], ['af', 'AF'],
  ['wtsd', 'WTSD'], ['wsd', 'W$SD'], ['cbet', 'C-bet'], ['bb100', 'bb/100'], ['drawdown', 'Drawdown']];
function bloqueTabla() {
  const f = filtros();
  const fmt = (k, v) => (['vpip', 'pfr', 'tres_bet', 'wtsd', 'wsd', 'cbet'].includes(k) ? pct(v) : k === 'af' ? num(v, 1) : k === 'bb100' ? signo(v, 1) : k === 'drawdown' ? num(v, 0) : v);
  const cabeza = h('tr', {}, ...COLS.map(([k, t]) => h('th', {}, k === 'jugador' ? t : h('button', {
    type: 'button', 'aria-pressed': String(f.metrica === k), onclick: () => { $('f-metrica').value = k; refrescar(); } }, t))));
  const filas = (S.tabla || []).map((r) => h('tr', { class: 'clic', 'data-sel': r.jugador === f.jugador ? '1' : null, tabindex: 0,
    onclick: () => { $('f-jugador').value = r.jugador; refrescar(); },
    onkeydown: (e) => { if (e.key === 'Enter') { $('f-jugador').value = r.jugador; refrescar(); } } },
  ...COLS.map(([k]) => h('td', { class: k === 'bb100' ? clasePN(r.bb100) : '' }, k === 'jugador' ? `${r.jugador}${S.estado.stakes.length > 1 ? ` (${r.stake})` : ''}` : fmt(k, r[k])))));
  return h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, 'Todos los jugadores')),
    h('div', { class: 'tabla-scroll' }, h('table', {}, h('thead', {}, cabeza), h('tbody', {}, filas.length ? filas : h('tr', {}, h('td', { colspan: COLS.length }, 'Sin jugadores con estos filtros'))))));
}

// ---------------------------------------------------------------- lista de manos
function renderLista() {
  const cont = vaciar($('lista-manos'));
  const L = S.lista;
  if (!L.filas.length) { cont.append(h('p', { class: 'vacio', style: { padding: '12px' } }, 'No hay manos con estos filtros.')); return; }
  cont.append(h('p', { class: 'nota', style: { padding: '8px 12px' } }, `${L.total.toLocaleString('es')} manos`));
  const ul = h('ul', {});
  for (const m of L.filas) {
    ul.append(h('li', {}, h('button', { class: 'mano-fila', 'aria-current': S.mano && S.mano.id === m.id ? 'true' : null, onclick: () => cargarMano(m.id, 0, true) },
      h('span', { class: 'n' }, `#${m.n}`),
      h('span', {}, h('span', { class: 'mini-cartas' }, ...m.cartas.map(miniCarta)), ' ', h('span', { class: 'n' }, m.posicion), m.showdown ? h('span', { class: 'sd' }, ' showdown') : null),
      h('span', { class: clasePN(m.neto_bb) }, signo(m.neto_bb, 1)))));
  }
  cont.append(ul);
  if (L.filas.length < L.total) cont.append(h('button', { class: 'btn chico', style: { margin: '10px 12px' }, onclick: masManos }, 'Mostrar más'));
}

async function masManos() {
  try {
    const mas = await api('/api/manos', { ...filtros(), limite: 200, offset: S.lista.filas.length });
    S.lista.filas.push(...mas.filas); renderLista();
  } catch (e) { aviso(e.message); }
}

// ---------------------------------------------------------------- repaso
// ---------------------------------------------------------------- bloques de 1000 manos
let temporizadorBloques = null;
async function cargarBloques() {
  clearTimeout(temporizadorBloques);
  const cont = vaciar($('vista-bloques'));
  const f = filtros();
  const jugador = f.jugador || (S.estado && S.estado.jugador_principal) || null;
  if (!jugador) { cont.append(h('div', { class: 'vacio-grande' }, h('h2', {}, 'Elegí un jugador'), h('p', {}, 'Elegilo en los filtros para ver sus bloques de 1000 manos.'))); return; }
  let d;
  try { d = await api('/api/bloques', { jugador, stake: f.stake || null }); }
  catch (e) { if (S.tab === 'bloques') cont.append(h('p', { class: 'vacio' }, e.message)); return; }
  if (S.tab !== 'bloques') return;
  vaciar(cont);
  if (d.estado === 'calculando') {
    cont.append(h('div', { class: 'vacio-grande' }, h('h2', {}, 'Calculando el informe de ' + jugador),
      h('p', {}, d.total ? `Bloque ${d.hechos} de ${d.total}. Compara cada decisión con la guía; tarda unos segundos por cada 100 manos.` : 'Empezando…')));
    temporizadorBloques = setTimeout(cargarBloques, 2000);
    return;
  }
  if (d.estado === 'error') { cont.append(h('p', { class: 'vacio' }, d.error)); return; }
  renderBloques(cont, d);
}

function renderBloques(cont, d) {
  cont.append(h('div', { class: 'resumen-bloques' }, h('h2', {}, `Bloques de ${d.jugador}`),
    h('p', { class: 'nota' }, 'En 1000 manos manda la varianza: el resultado es una pista; el proceso es lo que se puede mejorar.')));
  const dato = (v, r, cls) => h('div', { class: 'dato' }, h('span', { class: 'valor ' + (cls || '') }, v), h('span', { class: 'rotulo' }, r));
  for (const i of d.informes) {
    const ic = i.ic95 === null ? '–' : '±' + num(i.ic95, 0);
    const caja = h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, `Bloque ${i.numero}: ${i.manos} manos${i.completo ? '' : ' (incompleto)'}`),
      h('span', { class: 'nota' }, i.fecha_desde ? `${i.fecha_desde} al ${i.fecha_hasta}` : '')));
    caja.append(h('h4', {}, '1. Resultado'),
      h('div', { class: 'resumen' },
        dato(signo(i.bb100, 1), `bb/100 (${ic})`, clasePN(i.bb100)),
        dato(i.bb100_ev === null ? '–' : signo(i.bb100_ev, 1), i.bb100_ev === null ? 'bb/100 por EV (sin all-ins ajustables)' : `bb/100 por EV (${i.manos_ajustadas_ev} manos)`, i.bb100_ev === null ? '' : clasePN(i.bb100_ev)),
        dato(pct(i.prob_winrate_positivo, 0), 'probabilidad de winrate positivo')));
    caja.append(h('h4', {}, '2. Proceso'));
    if (i.decisiones) {
      caja.append(h('div', { class: 'resumen' },
        dato(pct(i.pct_proceso, 0), `decisiones que coinciden con la guía (${i.coinciden} de ${i.decisiones})`),
        dato(`${i.desvios_claros} / ${i.desvios_leves}`, 'desvíos claros / leves'),
        dato(num(i.perdida_bb, 1), `bb perdidas estimadas (${num(i.perdida_bb100, 1)} bb/100)`)),
        h('p', { class: 'nota' }, `${i.desvios_sin_valorar} desvíos no se pudieron valorar en bb. ` + Object.entries(i.por_calle).map(([c, v]) => `${c}: ${v[0]} desvíos, ${num(v[1], 1)} bb`).join('; ') + '.'));
    } else caja.append(h('p', { class: 'nota' }, 'No hubo decisiones con tus cartas visibles: la guía no pudo evaluar el proceso.'));
    caja.append(h('h4', {}, '3. Leaks de mayor costo'));
    if (i.leaks.length) {
      caja.append(h('ol', {}, ...i.leaks.map((lk) => h('li', {},
        `${lk.descripcion} — ${lk.casos} casos, ${num(lk.perdida_bb, 1)} bb` + (lk.sin_valorar ? ` (${lk.sin_valorar} sin valorar)` : '') + '. Para repasar: ',
        ...lk.ejemplos.flatMap(([n, ref, id], k) => [k ? ', ' : '', id === null ? `mano ${n}` : h('button', { class: 'enlace', type: 'button', onclick: () => irARepaso(id) }, `mano ${n}`)])))));
    } else caja.append(h('p', { class: 'nota' }, 'Sin desvíos registrados.'));
    caja.append(h('h4', {}, '5. Proyección'),
      h('p', {}, i.prob_ganar_proximo === null ? 'Muestra insuficiente para proyectar.' : `Probabilidad de ganar las próximas 1000 manos con lo observado hasta acá: ${pct(i.prob_ganar_proximo, 0)}.`),
      h('h4', {}, '6. Objetivo de proceso para el próximo bloque'), h('p', {}, i.objetivo));
    cont.append(caja);
  }
  if (d.evolucion.length > 1) {
    const fila = (e) => h('tr', {}, h('td', {}, e.bloque), h('td', {}, e.manos), h('td', { class: clasePN(e.bb100) }, signo(e.bb100, 1)),
      h('td', {}, e.bb100_ev === null ? '–' : signo(e.bb100_ev, 1)), h('td', {}, pct(e.pct_proceso, 0)), h('td', {}, num(e.perdida_bb100, 1)),
      h('td', {}, e.delta_pct_proceso === undefined || e.delta_pct_proceso === null ? '' : signo(100 * e.delta_pct_proceso, 1) + ' pts'),
      h('td', {}, e.delta_perdida_bb100 === undefined ? '' : signo(e.delta_perdida_bb100, 1)));
    cont.append(h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, '4. Evolución entre bloques')),
      h('div', { class: 'tabla-scroll' }, h('table', {}, h('thead', {}, h('tr', {}, ...['Bloque', 'Manos', 'bb/100', 'bb/100 EV', 'Proceso', 'Pérdida bb/100', 'Cambio proceso', 'Cambio pérdida'].map((t) => h('th', {}, t)))), h('tbody', {}, ...d.evolucion.map(fila))))));
  }
  cont.append(h('p', { class: 'nota' }, 'Las bb perdidas son una estimación con la guía heurística del proyecto y solo valoran los desvíos donde calcula el EV de igualar. El ajuste por EV cubre solo all-ins de dos jugadores con las cartas de ambos a la vista.'));
  cont.append(h('button', { class: 'btn', type: 'button', onclick: () => {
    const ok = () => aviso('Informe copiado como texto');
    if (navigator.clipboard) navigator.clipboard.writeText(d.texto).then(ok, () => aviso('No se pudo copiar'));
    else aviso('No se pudo copiar');
  } }, 'Copiar informe como texto'));
}

function irARepaso(id) { cambiarTab('repaso'); cargarMano(id, 0, true); }

async function cargarMano(id, paso = 0, usuario = false) {
  const token = ++S.tokenMano;
  try {
    const j = encodeURIComponent($('f-jugador').value || '');
    const m = await api(`/api/mano?id=${id}&jugador=${j}`);
    if (token !== S.tokenMano) return false;
    detenerAuto();
    S.mano = m;
    S.paso = Math.min(paso, m.pasos.length - 1);
    renderRepaso();
    renderLista();
    if (usuario) buscarVideo(id, S.paso);
    return true;
  } catch (e) { aviso(e.message); return false; }
}

function irPaso(i, usuario = true) {
  const m = S.mano; if (!m) return;
  S.paso = Math.max(0, Math.min(m.pasos.length - 1, i));
  renderPaso();
  if (usuario) buscarVideo(m.id, S.paso);
}

function renderRepaso() {
  const m = S.mano;
  if (!m) return;
  $('r-paso').max = m.pasos.length - 1;
  renderPaso();
  renderVideo();
}

function renderPaso() {
  const m = S.mano; if (!m) return;
  $('r-paso').value = S.paso;
  const p = m.pasos[S.paso];
  $('etq-paso').textContent = `Paso ${S.paso + 1} de ${m.pasos.length}`;
  renderMesa(m, p);
  renderCinta(m);
  renderGuia(m, p);
  renderMarcas();
}

const bbTxt = (x, bb) => (x === null || x === undefined ? '∞' : `${(x / bb).toFixed(1).replace(/\.0$/, '')} bb`);

function posAsiento(k, n, heroe, f) {
  const ang = Math.PI / 2 + (((k - heroe + n) % n) * 2 * Math.PI) / n;
  return [50 + 42 * f * Math.cos(ang), 50 + 37 * f * Math.sin(ang)];
}

function etiquetaAccion(p, bb) {
  const t = { fold: 'Fold', check: 'Check', call: 'Call ' + bbTxt(p.monto, bb), bet: 'Bet ' + bbTxt(p.hasta, bb), raise: 'Raise a ' + bbTxt(p.hasta, bb) }[p.tipo];
  return t ? h('div', { class: 'accion-asiento' }, t) : null;
}

// Marcas redondas para el eje: 1, 2 o 5 por una potencia de diez.
function marcasEje(lo, hi, cuantas = 4) {
  const paso0 = (hi - lo) / cuantas || 1, pot = Math.pow(10, Math.floor(Math.log10(paso0)));
  const paso = [1, 2, 5, 10].map((k) => k * pot).find((s) => s >= paso0);
  const out = [];
  for (let v = Math.ceil(lo / paso) * paso; v <= hi + 1e-9; v += paso) out.push(v);
  return out;
}

function renderMesa(m, p) {
  const mesa = vaciar($('mesa'));
  const n = m.mesa.jugadores.length, bb = m.mesa.ciega_grande, her = m.heroe.asiento;
  mesa.append(h('div', { class: 'fieltro' }));
  const tab = p.tablero;
  mesa.append(h('div', { class: 'centro-mesa' },
    h('div', { class: 'bote' }, `Bote ${bbTxt(p.bote, bb)}`),
    h('div', { class: 'tablero' }, ...[0, 1, 2, 3, 4].map((i) => (tab[i] ? carta(tab[i]) : h('div', { class: 'carta vacia' }))))));
  for (const j of m.mesa.jugadores) {
    const k = j.asiento, [x, y] = posAsiento(k, n, her, 1);
    const fuera = p.retirados[k];
    const rev = p.reveladas[String(k)];
    let cartas;
    if (k === her && m.heroe.cartas.length) cartas = m.heroe.cartas.map((c) => carta(c, 'chica'));
    else if (rev) cartas = rev.map((c) => carta(c, 'chica'));
    else cartas = fuera ? [] : [dorso('chica'), dorso('chica')];
    mesa.append(h('div', { class: 'asiento' + (k === her ? ' heroe' : '') + (fuera ? ' fuera' : '') + (p.asiento === k ? ' activo' : ''), style: { left: x + '%', top: y + '%' } },
      h('div', { class: 'nombre' }, j.nombre, k === m.mesa.boton ? h('span', { class: 'boton-d', title: 'Botón' }, 'D') : null),
      h('div', { class: 'sub' }, `${j.posicion} · ${bbTxt(p.stacks[k], bb)}`),
      p.asiento === k ? etiquetaAccion(p, bb) : null,
      h('div', { class: 'cartas' }, ...cartas)));
    if (p.apuestas[k] > 0 && !fuera) {
      const [bx, by] = posAsiento(k, n, her, k === her ? 0.36 : 0.46);
      mesa.append(h('div', { class: 'apuesta', style: { left: bx + '%', top: by + '%' } }, bbTxt(p.apuestas[k], bb)));
    }
  }
  if (p.tipo === 'resultado') {
    mesa.append(h('div', { class: 'centro-mesa', style: { top: '70%' } },
      h('div', { class: 'bote ' + clasePN(p.neto_bb[her]) }, `${m.heroe.nombre}: ${signo(p.neto_bb[her], 1)} bb`)));
  }
}

// Cinta: equity del jugador a lo largo de la mano, con sus decisiones y las marcas del video.
function renderCinta(m) {
  const cont = vaciar($('cinta'));
  const W = 700, H = 120, mg = { l: 30, r: 10, t: 16, b: 22 };
  const n = m.pasos.length;
  const X = (i) => mg.l + (n === 1 ? 0 : (i / (n - 1)) * (W - mg.l - mg.r));
  const Y = (e) => mg.t + (1 - e) * (H - mg.t - mg.b);
  const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Equity del jugador durante la mano' });
  // bandas por calle
  const calles = [];
  m.pasos.forEach((p, i) => { if (!calles.length || calles[calles.length - 1].c !== p.calle) calles.push({ c: p.calle, i }); });
  calles.forEach((c, k) => {
    const x0 = k === 0 ? mg.l : X(c.i - 0.5), x1 = k === calles.length - 1 ? W - mg.r : X(calles[k + 1].i - 0.5);
    if (k % 2 === 0) svg.append(sv('rect', { class: 'banda', x: x0, y: mg.t, width: x1 - x0, height: H - mg.t - mg.b }));
    svg.append(sv('text', { x: (x0 + x1) / 2, y: H - 7, 'text-anchor': 'middle' }, c.c));
  });
  for (const e of [0, 0.5, 1]) {
    svg.append(sv('line', { class: 'grilla', x1: mg.l, x2: W - mg.r, y1: Y(e), y2: Y(e) }), sv('text', { x: mg.l - 4, y: Y(e) + 3, 'text-anchor': 'end' }, `${e * 100}`));
  }
  const pts = [];
  m.pasos.forEach((p, i) => {
    const eq = p.analisis ? p.analisis.equity : p.equity_tablero ? p.equity_tablero.equity : null;
    if (eq !== null) pts.push({ i, eq, p });
  });
  if (pts.length > 1) svg.append(sv('polyline', { class: 'eq', points: pts.map((q) => `${X(q.i)},${Y(q.eq)}`).join(' ') }));
  for (const q of pts) {
    const decision = q.p.analisis;
    const cls = decision ? (q.p.comparacion.veredicto === 'coincide' ? 'p-bien' : 'p-mal') : 'p-calle';
    const c = sv('circle', { class: cls, cx: X(q.i), cy: Y(q.eq), r: decision ? 5 : 4 });
    c.append(sv('title', {}, `${q.p.etiqueta}${q.p.jugador ? ' de ' + q.p.jugador : ''}: equity ${pct(q.eq)}`));
    svg.append(c);
  }
  for (const mk of V.marcas.filter((x) => x.mano === m.id)) {
    svg.append(sv('line', { class: 'marca', x1: X(mk.paso), x2: X(mk.paso), y1: H - mg.b, y2: H - mg.b - 12 }));
  }
  svg.append(sv('line', { class: 'cursor', x1: X(S.paso), x2: X(S.paso), y1: mg.t - 6, y2: H - mg.b }));
  svg.addEventListener('click', (ev) => {
    const r = svg.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * W;
    irPaso(Math.round(((x - mg.l) / (W - mg.l - mg.r)) * (n - 1)));
  });
  cont.append(h('header', { style: { marginBottom: '6px' } }, h('h3', {}, 'Tu equity durante la mano')), svg,
    h('div', { class: 'leyenda' },
      h('span', {}, h('i', { style: { background: 'var(--bien)' } }), 'jugaste lo sugerido'),
      h('span', {}, h('i', { style: { background: 'var(--alerta)' } }), 'te desviaste'),
      h('span', {}, h('i', { style: { border: '1.5px solid var(--equity)' } }), 'nueva calle'),
      h('span', {}, h('i', { style: { background: '#c9a5ff', borderRadius: '2px' } }), 'marca del video')));
}

function textoAccion(a, bb) {
  return { fold: 'Fold', check: 'Check', call: a.a_pagar !== undefined ? `Call ${bbTxt(a.a_pagar, bb)}` : 'Call',
    bet: `Bet ${bbTxt(a.hasta, bb)}`, raise: `Raise a ${bbTxt(a.hasta, bb)}` }[a.accion];
}

function tarjetaSugerencia(a, bb) {
  const f = Math.max(0, Math.min(1, a.equity));
  const cont = h('div', {});
  const medidor = h('div', { class: 'medidor', role: 'img', 'aria-label': `Equity ${pct(a.equity)}` },
    h('div', { class: 'relleno', style: { width: `${f * 100}%` } }));
  if (a.pot_odds !== null && a.pot_odds !== undefined) {
    medidor.append(h('div', { class: 'tick', style: { left: `${a.pot_odds * 100}%` } }, h('span', {}, `pot odds ${pct(a.pot_odds)}`)));
  }
  cont.append(h('div', {}, h('strong', {}, `Equity ${pct(a.equity)}`), h('span', { class: 'nota' }, ` ± ${num(a.error_estandar * 196, 1)} pts · ${a.rivales} rival${a.rivales > 1 ? 'es' : ''}`)), medidor);
  if (a.categoria) cont.append(h('p', { class: 'nota' }, `Tu mano ahora: ${a.categoria}.`));
  if (a.outs && a.outs.length) cont.append(h('p', { class: 'nota' }, `Cartas que mejoran tu categoría (${a.outs.length}): `, ...a.outs.slice(0, 14).map((c) => [miniCarta(c), ' '])));
  if (a.ev_igualar !== null && a.ev_igualar !== undefined) {
    cont.append(h('p', { class: 'nota' }, 'Igualar rinde ', h('strong', { class: clasePN(a.ev_igualar) }, `${signo(a.ev_igualar / bb, 1)} bb`), ' de media (equity × bote final − costo; no cuenta las calles siguientes).'));
  }
  if (a.ev_igualar_realizado !== null && a.ev_igualar_realizado !== undefined && a.realizacion < 1) {
    cont.append(h('p', { class: 'nota' }, 'Contando las calles que faltan (se realiza ', h('strong', {}, pct(a.realizacion, 0)), ' de la equity), igualar rinde ', h('strong', { class: clasePN(a.ev_igualar_realizado) }, `${signo(a.ev_igualar_realizado / bb, 1)} bb`), '. El factor es una convención de estudio.'));
  }
  cont.append(h('ul', { class: 'razones' }, ...a.razones.map((r) => h('li', {}, r))));
  if (a.rangos_rivales && a.rangos_rivales.length) {
    cont.append(h('p', { class: 'nota', style: { marginTop: '10px' } }, 'Rango que se supone para cada rival:'),
      h('ul', { class: 'rivales' }, ...a.rangos_rivales.map((r) => h('li', {}, `${r.jugador}: ${r.supuesto}`))));
  }
  return cont;
}

function renderGuia(m, p) {
  const cont = vaciar($('guia'));
  const bb = m.mesa.ciega_grande;
  const her = m.heroe;
  cont.append(h('header', {}, h('h3', {}, `Mano #${m.n}`),
    h('div', { class: 'der' }, h('span', { class: 'mini-cartas' }, ...her.cartas.map(miniCarta)), h('span', { class: 'nota' }, `${her.nombre} · ${her.posicion}`))));
  if (!m.resumen.con_analisis) {
    cont.append(h('p', { class: 'vacio' }, 'No hay cartas visibles de este jugador en el historial: se muestran las acciones, pero la guía no puede evaluar sus decisiones.'));
  }
  if (p.analisis) {
    const cmp = p.comparacion, a = p.analisis;
    const jugado = { fold: 'Fold', check: 'Check', call: `Call ${bbTxt(p.monto, bb)}`, bet: `Bet ${bbTxt(p.hasta, bb)}`, raise: `Raise a ${bbTxt(p.hasta, bb)}` }[p.jugada];
    const v = h('div', { class: 'veredicto ' + cmp.veredicto },
      h('div', { class: 'linea-vs' },
        h('div', {}, h('div', { class: 'rot' }, 'Jugaste'), h('div', { class: 'accion' }, jugado)),
        h('div', {}, h('div', { class: 'rot' }, 'La guía sugiere'), h('div', { class: 'accion' }, textoAccion(a, bb)))),
      h('p', {}, cmp.veredicto === 'coincide' ? 'Coincide con la línea sugerida.' : `${cmp.detalle} Diferencia ${cmp.gravedad === 'leve' ? 'leve: es un punto discutible.' : 'clara: vale la pena revisarla.'}`));
    cont.append(v, tarjetaSugerencia(a, bb));
  } else if (p.equity_tablero) {
    cont.append(h('p', {}, `Con ${p.etiqueta.toLowerCase()} en la mesa tu equity estimada es `, h('strong', {}, pct(p.equity_tablero.equity)), p.equity_tablero.categoria ? ` y tenés ${p.equity_tablero.categoria.toLowerCase()}.` : '.'),
      h('p', { class: 'nota' }, 'Es una estimación contra los rangos que se suponen para los rivales que siguen en la mano.'));
  } else if (p.tipo === 'resultado') {
    cont.append(h('p', {}, 'Resultado de ', h('strong', {}, her.nombre), ': ', h('strong', { class: clasePN(m.resumen.neto_bb) }, `${signo(m.resumen.neto_bb, 1)} bb`), '.'));
  } else {
    cont.append(h('p', { class: 'vacio' }, p.asiento !== null && p.asiento !== undefined ? `${p.jugador}: ${p.etiqueta}${p.monto ? ' ' + bbTxt(p.monto, bb) : ''}. Seguí con el paso siguiente.` : 'Avanzá hasta una decisión del jugador para ver la guía.'));
  }
  const r = m.resumen;
  if (r.con_analisis) {
    cont.append(h('div', {}, h('p', { class: 'nota' }, `En esta mano: ${r.coincide} de ${r.decisiones} decisiones coinciden con la guía.`),
      r.pasos_con_desvio.length ? h('div', { class: 'desvios' }, ...r.pasos_con_desvio.map((i) => h('button', { class: 'btn chico', onclick: () => irPaso(i) }, `Ver desvío en ${m.pasos[i].calle}`))) : null));
  }
}

// reproducción automática de pasos
function detenerAuto() { if (S.auto) { clearInterval(S.auto); S.auto = null; } $('b-play').textContent = 'Reproducir'; }
function alternarAuto() {
  if (S.auto) return detenerAuto();
  if (!S.mano) return;
  if (S.paso >= S.mano.pasos.length - 1) S.paso = 0;
  $('b-play').textContent = 'Pausar';
  S.auto = setInterval(() => {
    if (S.paso >= S.mano.pasos.length - 1) return detenerAuto();
    irPaso(S.paso + 1, false);
  }, 1300);
}

// ---------------------------------------------------------------- video y marcas
function renderVideo() {
  const dock = vaciar($('video-dock'));
  dock.append(h('header', {}, h('h3', {}, 'Video de la sesión')));
  const entrada = h('input', { type: 'file', accept: 'video/*', id: 'v-archivo', 'aria-label': 'Elegir video', onchange: (e) => elegirVideo(e.target.files[0]) });
  if (!V.el) {
    dock.append(h('p', { class: 'nota' }, 'Elegí el video de la sesión (se reproduce desde tu computadora, no se sube a ningún lado). Después marcá en qué momento ocurre cada paso y el panel seguirá el video solo.'), entrada);
    return;
  }
  dock.append(V.el);
  dock.append(h('div', { class: 'controles' },
    h('button', { class: 'btn primario', onclick: marcar, title: 'Atajo: M' }, 'Marcar este paso aquí'),
    h('button', { class: 'btn', onclick: quitarMarca }, 'Quitar marca')),
  h('label', { class: 'check', style: { display: 'flex', gap: '8px' } }, h('input', { type: 'checkbox', checked: V.avanzar, onchange: (e) => { V.avanzar = e.target.checked; } }), 'Pasar al paso siguiente al marcar'),
  h('label', { class: 'check', style: { display: 'flex', gap: '8px' } }, h('input', { type: 'checkbox', checked: V.sync, onchange: (e) => { V.sync = e.target.checked; } }), 'Seguir el video con el panel y viceversa'),
  h('div', { class: 'controles' },
    h('button', { class: 'btn chico', onclick: () => alinear('ancla'), title: 'Marcá a mano el inicio de una mano y el resto se ubica por su hora' }, 'Alinear por esta marca'),
    h('input', { type: 'text', id: 'v-inicio', placeholder: 'Hora de inicio: 2026-10-21 20:00:00', 'aria-label': 'Hora de inicio del video', style: { width: '210px' } }),
    h('button', { class: 'btn chico', onclick: () => alinear('inicio') }, 'Alinear por hora')),
  h('div', { class: 'marcas', id: 'marcas' }),
  h('div', { class: 'controles' },
    h('button', { class: 'btn chico', onclick: exportarMarcas }, 'Exportar marcas'),
    h('label', { class: 'btn chico' }, 'Importar marcas', h('input', { type: 'file', accept: 'application/json', hidden: true, onchange: (e) => importarMarcas(e.target.files[0]) })),
    h('button', { class: 'btn chico', onclick: cambiarVideo }, 'Cambiar video')),
  h('p', { class: 'nota' }, 'Cómo marcar: reproducí el video, pausalo cuando ocurra la acción del paso que ves en la mesa y tocá Marcar (o M). El panel avanza al paso siguiente.'));
  renderMarcas();
}

function elegirVideo(archivo) {
  if (!archivo) return;
  if (V.url) URL.revokeObjectURL(V.url);
  V.url = URL.createObjectURL(archivo);
  V.nombre = archivo.name;
  const e = S.estado;
  V.clave = `marcas|${archivo.name}|${archivo.size}|${e.ruta}|${e.manos}`;
  V.el = h('video', { controls: true, src: V.url, 'aria-label': 'Video de la sesión' });
  V.el.addEventListener('play', () => { clearInterval(V.timer); V.timer = setInterval(sincronizar, 150); });
  V.el.addEventListener('pause', () => { clearInterval(V.timer); sincronizar(); });
  V.el.addEventListener('seeked', sincronizar);
  V.ultima = -1;
  try { V.marcas = JSON.parse(localStorage.getItem(V.clave) || '[]').filter((x) => Number.isFinite(x.t)); } catch (_) { V.marcas = []; }
  renderVideo();
  if (S.mano) renderCinta(S.mano);
}

function cambiarVideo() {
  clearInterval(V.timer);
  if (V.el) V.el.pause();
  if (V.url) URL.revokeObjectURL(V.url);
  V.el = null; V.url = null; V.marcas = [];
  renderVideo();
  if (S.mano) renderCinta(S.mano);
}
function cerrarVideoMarcas() { if (V.el) cambiarVideo(); }

function guardarMarcas() { try { localStorage.setItem(V.clave, JSON.stringify(V.marcas)); } catch (_) { /* sin almacenamiento: las marcas viven en esta pestaña */ } }

function marcar() {
  if (!V.el || !S.mano) return aviso('Elegí primero el video.');
  const t = Math.round(V.el.currentTime * 10) / 10;
  V.marcas = V.marcas.filter((x) => !(x.mano === S.mano.id && x.paso === S.paso));
  V.marcas.push({ t, mano: S.mano.id, paso: S.paso });
  V.marcas.sort((a, b) => a.t - b.t);
  guardarMarcas();
  V.ultima = V.marcas.findIndex((x) => x.mano === S.mano.id && x.paso === S.paso);
  if (V.avanzar) {
    if (S.paso < S.mano.pasos.length - 1) irPaso(S.paso + 1, false);
    else siguienteMano();
  } else { renderMarcas(); renderCinta(S.mano); }
}

function quitarMarca() {
  if (!S.mano) return;
  V.marcas = V.marcas.filter((x) => !(x.mano === S.mano.id && x.paso === S.paso));
  guardarMarcas(); renderMarcas(); renderCinta(S.mano);
}

function renderMarcas() {
  const cont = $('marcas');
  if (!cont || !S.mano) return;
  vaciar(cont);
  const mias = V.marcas.filter((x) => x.mano === S.mano.id);
  cont.append(h('p', { class: 'nota' }, `${V.marcas.length} marcas en total, ${mias.length} en esta mano.`));
  cont.append(h('ul', {}, ...mias.map((x) => h('li', {}, h('button', { onclick: () => { V.el.currentTime = x.t; irPaso(x.paso, false); } }, mmss(x.t)),
    `${S.mano.pasos[x.paso].etiqueta}${S.mano.pasos[x.paso].jugador ? ' de ' + S.mano.pasos[x.paso].jugador : ''}`))));
}

// Al tocar un paso o una mano, el video salta a su marca.
function buscarVideo(id, paso) {
  if (!V.el || !V.sync) return;
  const mk = V.marcas.find((x) => x.mano === id && x.paso === paso) || (paso === 0 ? V.marcas.find((x) => x.mano === id) : null);
  if (mk && Math.abs(V.el.currentTime - mk.t) > 0.3) { V.ultima = V.marcas.indexOf(mk); V.el.currentTime = mk.t; }
}

// Mientras corre el video, el panel muestra el paso de la última marca ya pasada.
async function sincronizar() {
  if (!V.el || !V.sync || !V.marcas.length) return;
  const t = V.el.currentTime;
  let i = -1;
  for (let k = 0; k < V.marcas.length; k++) { if (V.marcas[k].t <= t + 0.05) i = k; else break; }
  if (i === V.ultima) return;
  V.ultima = i;
  if (i < 0) return;
  const mk = V.marcas[i];
  if (!S.mano || S.mano.id !== mk.mano) { if (!(await cargarMano(mk.mano, mk.paso, false))) return; } else irPaso(mk.paso, false);
}

// Alinea el video con las horas del historial: una marca por mano en su primer paso (las marcas manuales se respetan).
async function alinear(modo) {
  const f = filtros();
  const jugador = f.jugador || (S.estado && S.estado.jugador_principal);
  if (!jugador) { aviso('Elegí un jugador en los filtros.'); return; }
  const cuerpo = { jugador, stake: f.stake || null, duracion: V.el && Number.isFinite(V.el.duration) ? V.el.duration : null };
  if (modo === 'ancla') {
    const mk = S.mano && V.marcas.find((x) => x.mano === S.mano.id && x.paso === 0) || (S.mano && V.marcas.find((x) => x.mano === S.mano.id));
    if (!mk) { aviso('Primero marcá a mano el primer paso de una mano en el video.'); return; }
    cuerpo.ancla = { mano: mk.mano, t: mk.t };
  } else {
    const txt = $('v-inicio').value.trim().replace(' ', 'T');
    if (!txt) { aviso('Escribí la hora de inicio del video, igual que figura en el historial.'); return; }
    cuerpo.inicio = txt;
  }
  try {
    const r = await api('/api/alinear', cuerpo);
    const propias = new Set(V.marcas.map((x) => x.mano));
    const nuevas = r.marcas.filter((x) => !propias.has(x.mano));
    V.marcas = V.marcas.concat(nuevas).sort((a, b) => a.t - b.t);
    guardarMarcas(); renderMarcas();
    if (S.mano) renderCinta(S.mano);
    aviso(`Se agregaron ${nuevas.length} marcas por hora (${r.fuera_del_video} manos quedaron fuera del video${r.sin_fecha ? `, ${r.sin_fecha} sin fecha` : ''}). Revisá algunas: el reloj de la sala y el del video pueden diferir unos segundos.`);
  } catch (e) { aviso(e.message); }
}

function exportarMarcas() {
  const blob = new Blob([JSON.stringify({ video: V.nombre, dataset: S.estado.ruta, manos: S.estado.manos, marcas: V.marcas }, null, 1)], { type: 'application/json' });
  const a = h('a', { href: URL.createObjectURL(blob), download: `marcas-${V.nombre || 'sesion'}.json` });
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
async function importarMarcas(archivo) {
  if (!archivo) return;
  try {
    const d = JSON.parse(await archivo.text());
    const ok = (d.marcas || []).filter((x) => Number.isFinite(x.t) && Number.isInteger(x.mano) && Number.isInteger(x.paso));
    V.marcas = ok.sort((a, b) => a.t - b.t); guardarMarcas(); renderMarcas();
    if (S.mano) renderCinta(S.mano);
    aviso(`Se importaron ${ok.length} marcas.`);
  } catch (_) { aviso('El archivo de marcas no es válido.'); }
}

function siguienteMano(delta = 1) {
  const filas = S.lista.filas;
  if (!S.mano || !filas.length) return;
  const k = filas.findIndex((x) => x.id === S.mano.id);
  const dest = filas[Math.max(0, Math.min(filas.length - 1, (k < 0 ? 0 : k) + delta))];
  if (dest && dest.id !== S.mano.id) cargarMano(dest.id, 0, true);
}

// ---------------------------------------------------------------- situación
function agregarRival() {
  const cont = $('s-rivales');
  if (cont.children.length >= 5) return aviso('Hasta 5 rivales.');
  const rango = h('input', { type: 'range', min: 2, max: 100, value: 20, 'aria-label': 'Porcentaje de manos del rival' });
  const txt = h('output', {}, '20%');
  rango.addEventListener('input', () => { txt.textContent = rango.value + '%'; });
  const manos = h('input', { type: 'text', placeholder: 'o manos exactas: AA KK AKs', 'aria-label': 'Manos exactas del rival' });
  const fila = h('div', { class: 'rival' },
    h('div', { class: 'fila' }, h('strong', {}, `Rival ${cont.children.length + 1}`), h('span', { class: 'nota' }, 'juega el mejor'), rango, txt,
      cont.children.length ? h('button', { type: 'button', class: 'btn chico', onclick: () => { fila.remove(); } }, 'Quitar') : null),
    h('div', { style: { marginTop: '6px' } }, manos));
  fila._rango = rango; fila._manos = manos;
  cont.append(fila);
}

async function analizarSituacion(ev) {
  ev.preventDefault();
  const rivales = [...$('s-rivales').children].map((f) => {
    const claves = f._manos.value.split(/[\s,]+/).filter(Boolean);
    return claves.length ? { claves } : { top: Number(f._rango.value) };
  });
  const cuerpo = {
    cartas: $('s-cartas').value, tablero: $('s-tablero').value, posicion: $('s-pos').value, bote: Number($('s-bote').value),
    a_pagar: Number($('s-pagar').value), bb: Number($('s-bb').value), subidas: Number($('s-subidas').value),
    limpers: Number($('s-limpers').value), rivales,
  };
  const res = vaciar($('s-resultado'));
  res.append(h('p', { class: 'vacio' }, 'Calculando…'));
  try {
    const a = await api('/api/analisis', cuerpo);
    a.a_pagar = cuerpo.a_pagar;
    vaciar(res);
    res.append(h('header', {}, h('h2', {}, 'La guía sugiere')),
      h('div', { class: 'veredicto coincide' }, h('div', { class: 'accion' }, textoAccion(a, cuerpo.bb))), tarjetaSugerencia(a, cuerpo.bb));
  } catch (e) { vaciar(res).append(h('p', { class: 'neg' }, e.message)); }
}

// ---------------------------------------------------------------- pestañas, teclado, diálogo
// ---------------------------------------------------------------- práctica contra bots
const P = { e: null, ocupado: false };

async function practica(cuerpo) {
  if (P.ocupado) return;
  P.ocupado = true;
  try { P.e = await api('/api/practica', cuerpo); }
  catch (err) { aviso(err.message); }
  P.ocupado = false;
  renderPractica();
}

function renderPractica() {
  const cont = vaciar($('vista-practica'));
  const e = P.e;
  if (!e) {
    cont.append(h('div', { class: 'vacio-grande' }, h('h2', {}, 'Práctica contra bots'),
      h('p', {}, 'Jugás en una mesa de 6 contra bots (tight agresivos, pasivos y uno aleatorio), sin dinero. La guía te sugiere una línea en cada decisión y al terminar cada mano te muestra dónde te desviaste. Es para estudiar, no para usar en una sala real.'),
      h('button', { class: 'btn primario', onclick: () => practica({ accion: 'nueva' }) }, 'Empezar')));
    return;
  }
  const bb = e.ciega_grande;
  const ac = e.acumulado;
  const resumen = h('div', { class: 'resumen' },
    h('div', { class: 'dato' }, h('span', { class: 'valor' }, `#${e.mano}`), h('span', { class: 'rotulo' }, 'mano')),
    h('div', { class: 'dato' }, h('span', { class: 'valor ' + clasePN(ac.neto_bb) }, ac.manos ? `${signo(ac.neto_bb, 1)} bb` : '–'), h('span', { class: 'rotulo' }, `resultado en ${ac.manos} manos${ac.manos >= 30 ? ` (${signo(ac.bb100, 0)} bb/100; con pocas manos manda la varianza)` : ''}`)),
    h('div', { class: 'dato' }, h('span', { class: 'valor' }, ac.pct_guia === null ? '–' : pct(ac.pct_guia, 0)), h('span', { class: 'rotulo' }, `decisiones que coinciden con la guía (${ac.coinciden} de ${ac.decisiones})`)));

  const asientos = h('div', { class: 'pr-asientos' }, ...e.jugadores.map((j) => h('div', { class: 'pr-asiento' + (j.asiento === 0 ? ' heroe' : '') + (j.retirado ? ' retirado' : '') },
    h('div', { class: 'nom' }, j.nombre, e.boton === j.asiento ? ' (D)' : ''),
    h('div', { class: 'sub' }, `${j.posicion} · ${bbTxt(j.stack, bb)}`),
    h('div', { class: 'sub' }, j.retirado ? 'retirado' : j.all_in ? 'all-in' : j.apuesta ? `apuesta ${bbTxt(j.apuesta, bb)}` : ''))));

  const tapete = h('div', { class: 'tapete' },
    h('div', {}, h('div', { class: 'nota' }, 'Tus cartas'), h('div', { class: 'grupo' }, ...e.cartas.map((c) => carta(c)))),
    h('div', {}, h('div', { class: 'nota' }, `Tablero · bote ${bbTxt(e.bote, bb)}`),
      h('div', { class: 'grupo' }, ...(e.tablero.length ? e.tablero.map((c) => carta(c)) : [h('span', { class: 'vacio' }, 'sin cartas todavía')]))));

  const log = h('ol', { class: 'log-practica' }, ...e.log.map((l) => h('li', { class: l.heroe ? 'pos' : '' }, `${l.calle}: ${l.texto}`)));

  const izq = h('div', { class: 'bloque' }, h('header', {}, h('h3', {}, 'Mesa'), h('div', { class: 'der' },
    h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: e.guia_activa, onchange: (ev) => practica({ accion: 'guia', activa: ev.target.checked }) }), ' Guía activa'),
    h('button', { class: 'btn chico', onclick: () => practica({ accion: 'nueva' }) }, 'Reiniciar sesión'))),
    resumen, asientos, tapete, log);

  const der = h('div', { class: 'bloque' });
  if (!e.terminada) {
    const p = e.pendiente;
    const slider = h('input', { type: 'number', min: p.minimo_hasta, max: p.maximo_hasta, step: 1, value: Math.min(p.maximo_hasta, Math.max(p.minimo_hasta, 3 * p.apuesta_actual || 3 * bb)), id: 'p-hasta', 'aria-label': 'Subir hasta (fichas)' });
    const fija = (txt, v) => h('button', { class: 'btn chico', type: 'button', onclick: () => { slider.value = Math.max(p.minimo_hasta, Math.min(p.maximo_hasta, Math.round(v))); } }, txt);
    const potTotal = e.bote + p.pagar;
    der.append(h('header', {}, h('h3', {}, 'Tu decisión'), h('span', { class: 'nota' }, `${p.calle} · ${p.pagar ? 'pagar ' + bbTxt(p.pagar, bb) : 'sin apuesta que igualar'}`)),
      h('div', { class: 'acciones-practica' },
        h('button', { class: 'btn', onclick: () => practica({ accion: 'actuar', tipo: 'f' }) }, p.pagar ? 'Fold' : 'Fold (equivale a check)'),
        h('button', { class: 'btn primario', onclick: () => practica({ accion: 'actuar', tipo: 'cc' }) }, p.pagar ? `Call ${bbTxt(p.pagar, bb)}` : 'Check')),
      p.puede_subir ? h('div', { class: 'acciones-practica', style: { marginTop: '10px' } },
        h('button', { class: 'btn', onclick: () => practica({ accion: 'actuar', tipo: 'cbr', hasta: Number(slider.value) }) }, p.apuesta_actual ? 'Subir a' : 'Apostar'),
        slider, h('span', { class: 'nota' }, 'fichas (1 bb = ' + bb + ')'),
        fija('mín', p.minimo_hasta), fija('2/3 bote', p.apuesta_actual + 0.66 * potTotal), fija('bote', p.apuesta_actual + potTotal), fija('all-in', p.maximo_hasta)) : h('p', { class: 'nota' }, 'No podés subir en esta situación.'));
    if (e.guia) {
      der.append(h('p', {}, h('strong', {}, 'La guía sugiere: '), textoAccion(e.guia, bb)), tarjetaSugerencia(e.guia, bb));
    } else {
      der.append(h('p', { class: 'nota' }, 'Guía desactivada: decidí vos y mirá la revisión al terminar la mano.'));
    }
  } else {
    const r = e.resultado;
    der.append(h('header', {}, h('h3', {}, 'Fin de la mano'), h('strong', { class: clasePN(r.neto_bb) }, `${signo(r.neto_bb, 1)} bb`)));
    const sd = Object.entries(r.showdown);
    if (sd.length) der.append(h('p', {}, 'Showdown: ', ...sd.flatMap(([a, cs]) => [h('strong', {}, e.jugadores[a].nombre), ' ', ...cs.map(miniCarta), '  '])));
    else der.append(h('p', { class: 'nota' }, 'No hubo showdown.'));
    const rev = r.revision;
    der.append(h('p', {}, rev.decisiones ? `${rev.coincide} de ${rev.decisiones} decisiones coinciden con la guía.` : 'No tomaste decisiones con rivales vivos.'));
    if (rev.desvios.length) {
      der.append(h('ul', { class: 'razones' }, ...rev.desvios.map((d) => h('li', {}, `${d.calle}: jugaste ${d.jugada}, la guía sugería ${d.sugerida} (equity ${pct(d.equity)}${d.pot_odds !== null ? `, pot odds ${pct(d.pot_odds)}` : ''}). ${d.detalle} Diferencia ${d.gravedad}.`))));
    }
    der.append(h('p', { class: 'nota' }, 'El desvío es contra una guía heurística, no contra un solver: un desvío leve es discutible.'),
      h('button', { class: 'btn primario', onclick: () => practica({ accion: 'siguiente' }) }, 'Siguiente mano'));
  }
  cont.append(h('div', { class: 'practica' }, izq, der));
}

function cambiarTab(t) {
  S.tab = t;
  if (t !== 'bloques') clearTimeout(temporizadorBloques);
  for (const k of ['panel', 'bloques', 'repaso', 'practica', 'situacion']) {
    $('vista-' + k).hidden = k !== t;
    $('tab-' + k).setAttribute('aria-selected', String(k === t));
  }
  if (t === 'repaso' && !S.mano && S.lista.filas.length) cargarMano(S.lista.filas[0].id, 0, true);
  if (t === 'repaso') renderVideo();
  if (t === 'bloques') cargarBloques();
  if (t === 'practica') { if (!P.e) practica({ accion: 'estado' }); else renderPractica(); }
}

document.addEventListener('keydown', (e) => {
  if (S.tab !== 'repaso' || e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target.tagName;
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(t) || (t === 'VIDEO' && e.key === ' ')) return;
  const k = e.key;
  if (k === 'ArrowRight') irPaso(S.paso + 1);
  else if (k === 'ArrowLeft') irPaso(S.paso - 1);
  else if (k === 'ArrowDown') siguienteMano(1);
  else if (k === 'ArrowUp') siguienteMano(-1);
  else if (k === 'Home') irPaso(0);
  else if (k === 'End' && S.mano) irPaso(S.mano.pasos.length - 1);
  else if (k === 'm' || k === 'M') marcar();
  else if (k === ' ') { if (V.el) { V.el.paused ? V.el.play() : V.el.pause(); } else alternarAuto(); }
  else return;
  e.preventDefault();
});

function conectar() {
  for (const k of ['panel', 'bloques', 'repaso', 'practica', 'situacion']) $('tab-' + k).addEventListener('click', () => cambiarTab(k));
  for (const id of ['f-jugador', 'f-stake', 'f-desde', 'f-hasta', 'f-min', 'f-metrica', 'f-orden', 'f-sd']) $(id).addEventListener('change', refrescarPronto);
  $('f-posiciones').addEventListener('click', (e) => {
    const b = e.target.closest('.chip'); if (!b) return;
    b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true')); refrescarPronto();
  });
  $('btn-limpiar').addEventListener('click', limpiarFiltros);
  $('btn-filtros').addEventListener('click', () => { const a = $('filtros'); const abierto = a.classList.toggle('abierto'); $('btn-filtros').setAttribute('aria-expanded', String(abierto)); });
  $('b-ini').addEventListener('click', () => irPaso(0));
  $('b-ant').addEventListener('click', () => irPaso(S.paso - 1));
  $('b-sig').addEventListener('click', () => irPaso(S.paso + 1));
  $('b-fin').addEventListener('click', () => S.mano && irPaso(S.mano.pasos.length - 1));
  $('b-play').addEventListener('click', alternarAuto);
  $('r-paso').addEventListener('input', (e) => irPaso(Number(e.target.value)));
  $('form-situacion').addEventListener('submit', analizarSituacion);
  $('s-mas').addEventListener('click', agregarRival);
  agregarRival();

  const dlg = $('dlg-cargar');
  $('btn-cargar').addEventListener('click', () => dlg.showModal());
  $('c-cancelar').addEventListener('click', () => dlg.close());
  const lanzar = async (cuerpo) => {
    try { await api('/api/cargar', cuerpo); dlg.close(); S.estado.cargando = true; esperarCarga(); } catch (e) { aviso(e.message); }
  };
  $('c-demo').addEventListener('click', () => lanzar({ ruta: '600', formato: 'demo' }));
  $('form-cargar').addEventListener('submit', (e) => { e.preventDefault(); lanzar({ ruta: $('c-ruta').value.trim(), formato: $('c-formato').value }); });
}

conectar();
iniciar();
