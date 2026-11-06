/* V2X Slicing Dashboard: replays recordings (dashboard/recordings/*.json) or polls
 * a running testbed (/api/live), and shows experiment results (results.json). */
'use strict';

const SLICES = [
  { key: 'urllc', label: 'URLLC', port: 'UDP 5000', what: 'Safety messages to the RSU edge (MEC) server', band: 'Top' },
  { key: 'platoon', label: 'Platoon', port: 'UDP 9000', what: 'Cooperative driving between vehicles (V2V)', band: 'Top' },
  { key: 'embb', label: 'eMBB', port: 'TCP 8080', what: 'Infotainment streaming from the central server', band: 'Bottom' },
  { key: 'mmtc', label: 'mMTC', port: 'UDP 1883', what: 'Vehicle telemetry to the central server', band: 'Middle' },
  { key: 'best_effort', label: 'Best effort', port: 'anything else', what: 'Unclassified traffic, including the 1 s beacons', band: 'Bottom' },
];
const SLICE = Object.fromEntries(SLICES.map(s => [s.key, s]));
const SETUPS = [
  { key: 'best_effort', label: 'Best effort', desc: 'No meters, no priority, no loop' },
  { key: 'meters_only', label: 'Meters only', desc: 'Slice meters' },
  { key: 'meters_loop', label: 'Meters + loop', desc: 'Slice meters and the threshold loop' },
  { key: 'static', label: 'Static slicing', desc: 'Slice meters and priority queues' },
  { key: 'orchestrated', label: 'Orchestrated', desc: 'Meters, priority queues and the threshold loop' },
];
const SETUP_LABEL = Object.fromEntries(SETUPS.map(s => [s.key, s.label]));
const SCENARIOS = {
  congestion: 'Parked vehicles, eMBB flood, light critical traffic',
  heavy: 'Parked vehicles, eMBB flood, critical slices near their budgets',
  handover: 'Scripted intersecting paths, traffic while the vehicles move',
  random: 'Random waypoint mobility, eMBB flood, light critical traffic',
};
const FLOW_INFO = {
  urllc_edge: 'URLLC edge', urllc_far: 'URLLC far', urllc_veh1: 'URLLC veh1 to MEC 1',
  urllc_veh4: 'URLLC veh4 to MEC 2', platoon: 'Platoon', mmtc: 'mMTC', embb: 'eMBB',
};
const flowSlice = f => (f.startsWith('urllc') ? 'urllc' : f);
const flowLabel = f => FLOW_INFO[f] || f;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const color = s => css('--s-' + s);
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function html(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}
const fmtMs = v => (v == null ? '-' : v >= 100 ? v.toFixed(0) + ' ms' : v >= 10 ? v.toFixed(1) + ' ms' : v.toFixed(2) + ' ms');
const fmtKbps = v => (v == null ? '-' : v >= 1000 ? (v / 1000).toFixed(1) + ' Mb/s' : v.toFixed(0) + ' kb/s');

/* ------------------------------------------------------------------ state */
const state = {
  rec: null, cmp: null, t: 0, playing: false, speed: 2, live: false, liveTimer: null,
  sw: 's1', lastIdx: -1, lastCmpIdx: -1, results: null,
};

/* ------------------------------------------------------------- data access */
function frameIndex(rec, t) {
  const f = rec.frames;
  let lo = 0, hi = f.length - 1;
  if (!f.length) return -1;
  if (t <= f[0].t) return 0;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (f[mid].t <= t) lo = mid; else hi = mid - 1; }
  return lo;
}
function duration(rec) { return rec && rec.frames.length ? rec.frames[rec.frames.length - 1].t : 0; }
function allEvents(rec) {
  const out = [];
  for (const fr of rec.frames) for (const e of fr.events || []) out.push(Object.assign({ rt: fr.t }, e));
  return out;
}
function flowsOf(rec) {
  const set = new Set();
  for (const fr of rec.frames) Object.keys(fr.probes || {}).forEach(k => set.add(k));
  return [...set].sort();
}
function interpPos(rec, t, name) {
  const i = frameIndex(rec, t);
  const a = rec.frames[i], b = rec.frames[Math.min(i + 1, rec.frames.length - 1)];
  const pa = a.vehicles[name] && a.vehicles[name].pos, pb = b.vehicles[name] && b.vehicles[name].pos;
  if (!pa) return null;
  if (!pb || b.t === a.t) return pa;
  const k = Math.max(0, Math.min(1, (t - a.t) / (b.t - a.t)));
  return [pa[0] + (pb[0] - pa[0]) * k, pa[1] + (pb[1] - pa[1]) * k];
}

/* ------------------------------------------------------------------- map */
const MAP = { k: 6.5, ox: 40, oy: 110, w: 70, h: 60 };
const CX = 40 + 35 * 6.5;   // x of s1, centred over the field
const mx = x => MAP.ox + x * MAP.k;
const my = y => MAP.oy + (MAP.h - y) * MAP.k;

function buildMap(rec) {
  const svg = $('map');
  svg.textContent = '';
  const meta = rec.meta || {};
  const rsus = meta.rsus || { rsu1: { pos: [15, 30] }, rsu2: { pos: [55, 30] } };
  const range = meta.rsu_range || 30;
  el('rect', { x: mx(0), y: my(MAP.h), width: MAP.w * MAP.k, height: MAP.h * MAP.k, rx: 8, fill: css('--field') }, svg);
  const g = el('g', {}, svg);
  if (rec.scenario === 'random' || meta.mobility === 'random') {
    el('rect', { x: mx(5), y: my(45), width: 60 * MAP.k, height: 30 * MAP.k, fill: 'none', stroke: css('--road'),
      'stroke-width': 2, 'stroke-dasharray': '6 5' }, g);
    el('text', { x: mx(5) + 4, y: my(45) - 6, class: 'lbl', fill: css('--muted'), 'font-size': 11 }, g).textContent = 'Random waypoint area';
  } else {
    for (const y of [30, 40]) el('line', { x1: mx(8), x2: mx(62), y1: my(y), y2: my(y), stroke: css('--road'), 'stroke-width': 16, 'stroke-linecap': 'round' }, g);
    for (const x of [15, 55]) el('line', { x1: mx(x), x2: mx(x), y1: my(8), y2: my(52), stroke: css('--road'), 'stroke-width': 16, 'stroke-linecap': 'round' }, g);
  }
  for (const [name, r] of Object.entries(rsus)) {
    el('circle', { cx: mx(r.pos[0]), cy: my(r.pos[1]), r: range * MAP.k, fill: css('--range'), stroke: css('--range-line'), 'stroke-dasharray': '4 4' }, g);
  }
  // core: s1 and the central servers, drawn above the field
  const core = el('g', {}, svg);
  const box = (x, y, w, label, sub) => {
    el('rect', { x: x - w / 2, y: y - 17, width: w, height: 34, rx: 6, fill: css('--surface'), stroke: css('--axis') }, core);
    el('text', { x, y: y - 2, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600, fill: css('--ink') }, core).textContent = label;
    el('text', { x, y: y + 12, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, core).textContent = sub;
  };
  el('line', { x1: CX - 140, y1: 30, x2: CX + 140, y2: 30, stroke: css('--axis'), 'stroke-width': 2 }, core);
  box(CX - 160, 30, 110, 'infotain', 'eMBB server, 15 ms');
  box(CX + 160, 30, 110, 'telemetry', 'mMTC server, 15 ms');
  box(CX, 30, 70, 's1', 'aggregation');
  el('g', { id: 'backhaul' }, svg);
  for (const [name, r] of Object.entries(rsus)) {
    const x = mx(r.pos[0]), y = my(r.pos[1]);
    const mecX = x + (name === 'rsu1' ? -26 : 26);
    el('line', { x1: x, y1: y, x2: mecX, y2: y + 36, stroke: css('--axis'), 'stroke-width': 2 }, svg);
    el('rect', { x: mecX - 22, y: y + 36, width: 44, height: 20, rx: 4, fill: css('--surface'), stroke: css('--axis') }, svg);
    el('text', { x: mecX, y: y + 50, 'text-anchor': 'middle', 'font-size': 10, fill: css('--ink-2') }, svg).textContent = 'MEC ' + name.slice(-1);
    el('path', { d: `M${x - 9},${y + 10} L${x},${y - 14} L${x + 9},${y + 10} Z`, fill: css('--ink'), opacity: 0.85 }, svg);
    el('text', { x, y: y - 20, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600, fill: css('--ink') }, svg).textContent = name;
  }
  el('g', { id: 'links' }, svg);
  el('g', { id: 'trails' }, svg);
  el('g', { id: 'cars' }, svg);
  el('text', { x: mx(0), y: my(0) + 18, 'font-size': 10, fill: css('--muted') }, svg).textContent = '0 m';
  el('text', { x: mx(70), y: my(0) + 18, 'font-size': 10, fill: css('--muted'), 'text-anchor': 'end' }, svg).textContent = '70 m';
}

function drawMap(rec, t) {
  const i = frameIndex(rec, t);
  if (i < 0) return;
  const fr = rec.frames[i];
  const meta = rec.meta || {};
  const rsus = meta.rsus || { rsu1: { pos: [15, 30] }, rsu2: { pos: [55, 30] } };
  // backhaul utilisation labels
  const bh = $('backhaul'); bh.textContent = '';
  for (const [name, r] of Object.entries(rsus)) {
    const x = mx(r.pos[0]), y = my(r.pos[1]);
    const sw = fr.switches[name];
    const total = sw ? Object.values(sw.measured || {}).reduce((a, b) => a + b, 0) : 0;
    el('line', { x1: x, y1: y - 14, x2: CX, y2: 47, stroke: css('--axis'), 'stroke-width': 3 }, bh);
    const lx = (x + CX) / 2 + (name === 'rsu1' ? -14 : 14), ly = (y - 14 + 47) / 2;
    const tag = el('g', {}, bh);
    el('rect', { x: lx - 52, y: ly - 11, width: 104, height: 20, rx: 10, fill: css('--surface'), stroke: css('--border') }, tag);
    el('text', { x: lx, y: ly + 4, 'text-anchor': 'middle', 'font-size': 11, fill: css('--ink-2') }, tag).textContent = fmtKbps(total) + ' at ' + name;
    tag.addEventListener('pointermove', ev => showTip(ev, [[null, 'All slice traffic arriving at ' + name + "'s meters,"], [null, 'both directions, including its MEC traffic']]));
    tag.addEventListener('pointerleave', hideTip);
  }
  const links = $('links'); links.textContent = '';
  const trails = $('trails'); trails.textContent = '';
  const cars = $('cars'); cars.textContent = '';
  for (const name of Object.keys(fr.vehicles).sort()) {
    const p = interpPos(rec, t, name);
    if (!p) continue;
    const v = fr.vehicles[name];
    // trail of the last 8 s
    const pts = [];
    for (let j = Math.max(0, i - 16); j <= i; j++) {
      const q = rec.frames[j].vehicles[name] && rec.frames[j].vehicles[name].pos;
      if (q) pts.push(mx(q[0]) + ',' + my(q[1]));
    }
    pts.push(mx(p[0]) + ',' + my(p[1]));
    el('polyline', { points: pts.join(' '), fill: 'none', stroke: css('--muted'), 'stroke-width': 2, opacity: 0.35, 'stroke-linecap': 'round' }, trails);
    if (v.rsu && rsus[v.rsu]) {
      const r = rsus[v.rsu].pos;
      el('line', { x1: mx(p[0]), y1: my(p[1]), x2: mx(r[0]), y2: my(r[1]), stroke: css('--ink-2'), 'stroke-width': 1.5, 'stroke-dasharray': '3 4', opacity: 0.6 }, links);
    }
    // handover ring: association changed within the last 2 s
    let changed = false;
    for (let j = Math.max(1, i - 4); j <= i; j++) {
      const a = rec.frames[j - 1].vehicles[name], b = rec.frames[j].vehicles[name];
      if (a && b && a.rsu && b.rsu && a.rsu !== b.rsu) changed = true;
    }
    if (changed) el('circle', { cx: mx(p[0]), cy: my(p[1]), r: 17, fill: 'none', stroke: css('--warning'), 'stroke-width': 3 }, cars);
    const g = el('g', { tabindex: 0 }, cars);
    el('circle', { cx: mx(p[0]), cy: my(p[1]), r: 11, fill: css('--ink'), stroke: css('--surface'), 'stroke-width': 2 }, g);
    el('text', { x: mx(p[0]), y: my(p[1]) + 4, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 700, fill: css('--surface') }, g).textContent = name.replace('veh', '');
    const tip = `${name}: (${p[0].toFixed(1)}, ${p[1].toFixed(1)}) m, connected to ${v.rsu || 'none'}`;
    g.addEventListener('pointermove', ev => showTip(ev, [[null, tip]]));
    g.addEventListener('pointerleave', hideTip);
  }
}

/* ---------------------------------------------------------------- tooltip */
function showTip(ev, rows, head) {
  const tt = $('tooltip');
  tt.textContent = '';
  if (head) tt.appendChild(html('div', { class: 'tt-head' }, head));
  for (const [c, label, value, dash] of rows) {
    const row = html('div', { class: 'tt-row' });
    if (c) { const i = html('i'); i.style.background = c; if (dash) i.style.opacity = 0.6; row.appendChild(i); }
    row.appendChild(document.createTextNode(label));
    if (value !== undefined) row.appendChild(html('b', {}, value));
    tt.appendChild(row);
  }
  tt.hidden = false;
  const x = Math.min(ev.clientX + 14, window.innerWidth - tt.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, window.innerHeight - tt.offsetHeight - 8);
  tt.style.left = x + 'px'; tt.style.top = y + 'px';
}
function hideTip() { $('tooltip').hidden = true; }

/* ------------------------------------------------------------- line chart */
/* series: [{key, label, color, dash, pts: [[t, v|null]]}]; opts: {x0, x1, log, yMin, yMax, fmt, now, marks} */
function lineChart(svg, series, opts) {
  svg.textContent = '';
  const W = 640, H = 260, L = 56, R = 14, T = 10, B = 26;
  const pw = W - L - R, ph = H - T - B;
  const vals = series.flatMap(s => s.pts.map(p => p[1])).filter(v => v != null && isFinite(v));
  let yMin = opts.yMin != null ? opts.yMin : 0, yMax = opts.yMax != null ? opts.yMax : Math.max(1, ...vals) * 1.1;
  if (opts.log) { yMin = opts.yMin || 0.5; yMax = Math.max(yMax, yMin * 10); }
  const ys = v => {
    if (opts.log) { const a = Math.log10(yMin), b = Math.log10(yMax); return T + ph - (Math.log10(Math.max(v, yMin)) - a) / (b - a) * ph; }
    return T + ph - (v - yMin) / (yMax - yMin) * ph;
  };
  const xs = t => L + (t - opts.x0) / Math.max(1e-6, opts.x1 - opts.x0) * pw;
  // grid + y ticks
  let ticks = [];
  if (opts.log) { for (let d = Math.pow(10, Math.floor(Math.log10(yMin))); d <= yMax * 1.0001; d *= 10) for (const m of [1, 3]) { const v = d * m; if (v >= yMin && v <= yMax) ticks.push(v); } }
  else { const step = niceStep((yMax - yMin) / 4); for (let v = yMin; v <= yMax + 1e-9; v += step) ticks.push(v); }
  for (const v of ticks) {
    el('line', { x1: L, x2: W - R, y1: ys(v), y2: ys(v), stroke: css('--grid'), 'stroke-width': 1 }, svg);
    el('text', { x: L - 6, y: ys(v) + 4, 'text-anchor': 'end' }, svg).textContent = opts.fmt(v);
  }
  el('line', { x1: L, x2: W - R, y1: T + ph, y2: T + ph, stroke: css('--axis') }, svg);
  const xstep = niceStep((opts.x1 - opts.x0) / 6);
  for (let t = Math.ceil(opts.x0 / xstep) * xstep; t <= opts.x1; t += xstep) {
    el('text', { x: xs(t), y: H - 8, 'text-anchor': 'middle' }, svg).textContent = t.toFixed(0) + ' s';
  }
  for (const m of opts.marks || []) {
    if (m.t < opts.x0 || m.t > opts.x1) continue;
    el('line', { x1: xs(m.t), x2: xs(m.t), y1: T, y2: T + ph, stroke: m.color || css('--axis'), 'stroke-width': 1, 'stroke-dasharray': '2 3', opacity: 0.8 }, svg);
  }
  for (const s of series) {
    let d = '', pen = false;
    for (const [t, v] of s.pts) {
      if (v == null || !isFinite(v)) { pen = false; continue; }
      d += (pen ? 'L' : 'M') + xs(t).toFixed(1) + ',' + ys(v).toFixed(1); pen = true;
    }
    if (d) el('path', { d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2, 'stroke-dasharray': s.dash || '', 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
  }
  if (opts.now != null && opts.now <= opts.x1) {
    el('line', { x1: xs(opts.now), x2: xs(opts.now), y1: T, y2: T + ph, stroke: css('--ink-2'), 'stroke-width': 1 }, svg);
  }
  // hover layer: crosshair + one tooltip listing every series at that time
  const cross = el('line', { y1: T, y2: T + ph, stroke: css('--ink-2'), 'stroke-width': 1, visibility: 'hidden' }, svg);
  const hit = el('rect', { x: L, y: T, width: pw, height: ph, fill: 'transparent' }, svg);
  hit.addEventListener('pointermove', ev => {
    const box = svg.getBoundingClientRect();
    const t = opts.x0 + ((ev.clientX - box.left) / box.width * W - L) / pw * (opts.x1 - opts.x0);
    const rows = [];
    let snapT = t;
    for (const s of series) {
      let best = null;
      for (const p of s.pts) if (best == null || Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p;
      if (best) { snapT = best[0]; rows.push([s.color, s.label, best[1] == null ? 'no data' : opts.fmt(best[1], true), s.dash]); }
    }
    cross.setAttribute('x1', xs(snapT)); cross.setAttribute('x2', xs(snapT)); cross.setAttribute('visibility', 'visible');
    showTip(ev, rows, 't = ' + snapT.toFixed(1) + ' s');
  });
  hit.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
}
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1e-9))));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}
function legend(div, items) {
  div.textContent = '';
  for (const it of items) {
    const span = html('span');
    const s = el('svg', { viewBox: '0 0 22 8' });
    el('line', { x1: 1, x2: 21, y1: 4, y2: 4, stroke: it.color, 'stroke-width': 2.5, 'stroke-dasharray': it.dash || '' }, s);
    span.appendChild(s); span.appendChild(document.createTextNode(it.label));
    div.appendChild(span);
  }
}

/* -------------------------------------------------------------- run view */
function rttSeries(rec, upto) {
  return flowsOf(rec).map((f, n, all) => {
    const sl = flowSlice(f);
    const sameSlice = all.filter(x => flowSlice(x) === sl);
    return {
      key: f, label: flowLabel(f), color: color(sl), dash: sameSlice.indexOf(f) > 0 ? '6 4' : '',
      pts: rec.frames.filter(fr => fr.t <= upto).map(fr => [fr.t, fr.probes[f] ? fr.probes[f].rtt_p95 : null]),
    };
  });
}
function renderRun(force) {
  const rec = state.rec;
  if (!rec || !rec.frames.length) return;
  const t = state.t;
  const i = frameIndex(rec, t);
  drawMap(rec, t);
  $('clock').textContent = t.toFixed(1) + ' s';
  if (!state.live) $('scrub').value = t;
  if (i === state.lastIdx && !force) return;
  state.lastIdx = i;
  const fr = rec.frames[i];
  const dur = state.live ? Math.max(60, t) : duration(rec);
  const x0 = state.live ? Math.max(0, t - 120) : 0;
  const marks = allEvents(rec).filter(e => e.rt <= t && /PROTECT|ADJUST|HANDOVER/.test(e.event))
    .map(e => ({ t: e.rt, color: e.event === 'HANDOVER' ? css('--muted') : css('--warning') }));

  // config chips
  const cfg = fr.config || {};
  const chips = $('config'); chips.textContent = '';
  const chip = (k, v) => { const c = html('span', { class: 'chip' }); c.appendChild(document.createTextNode(k + ': ')); c.appendChild(html('b', {}, v)); chips.appendChild(c); };
  chip('Setup', SETUP_LABEL[rec.setup] || rec.setup || 'live');
  chip('Mobility', rec.scenario || (rec.meta && rec.meta.mobility) || '-');
  chip('Slice meters', cfg.slicing_enabled ? 'on' : 'off');
  chip('Priority queues', cfg.priority_enabled ? 'on' : 'off');
  chip('Threshold loop', cfg.dynamic_enabled ? 'on (' + cfg.policy + ' policy)' : 'off');

  // KPIs
  const urllc = Object.entries(fr.probes || {}).filter(([k]) => k.startsWith('urllc'));
  const worst = urllc.reduce((m, [, p]) => (p.rtt_p95 != null && (m == null || p.rtt_p95 > m) ? p.rtt_p95 : m), null);
  setKpi('kpi-urllc', fmtMs(worst), urllc.length + ' URLLC flows');
  const pl = (fr.probes || {}).platoon;
  setKpi('kpi-platoon', pl && pl.loss_pct != null ? pl.loss_pct.toFixed(1) + '%' : '-', pl ? 'RTT p95 ' + fmtMs(pl.rtt_p95) : '');
  const s1 = fr.switches.s1 || {};
  const embb = (s1.measured || {}).embb;
  const lim = (s1.installed || {}).embb;
  setKpi('kpi-embb', fmtKbps(embb), cfg.slicing_enabled ? 'meter limit ' + fmtKbps(lim) + ', excess is dropped' : 'no limit (best effort)');
  const prot = Object.entries(fr.switches).filter(([, s]) => s.protecting).map(([n]) => n);
  const ko = $('kpi-orch').querySelector('.kpi-value');
  ko.textContent = '';
  const st = html('span', { class: 'status' }); const dot = html('i');
  dot.style.background = prot.length ? css('--warning') : css('--good');
  st.appendChild(dot); st.appendChild(document.createTextNode(prot.length ? 'Protecting' : 'Normal'));
  ko.appendChild(st);
  $('kpi-orch').querySelector('.kpi-sub').textContent = prot.length ? 'eMBB cut on ' + prot.join(', ') : (cfg.dynamic_enabled ? 'All slices at their budgets' : 'Threshold loop off');

  // events
  const list = $('events'); list.textContent = '';
  for (const e of allEvents(rec).reverse()) {
    if (e.event === 'START') continue;
    const li = html('li', e.rt > t ? { class: 'future' } : {});
    li.appendChild(html('span', { class: 't' }, e.rt.toFixed(1) + ' s'));
    li.appendChild(html('span', { class: 'k' }, e.event));
    li.appendChild(html('span', { class: 'd' }, describe(e)));
    li.addEventListener('click', () => { if (!state.live) { state.t = e.rt; state.playing = false; $('play').textContent = 'Play'; renderRun(true); } });
    list.appendChild(li);
  }

  // RTT chart(s), sharing one y-scale when comparing
  const series = rttSeries(rec, t);
  let yMax = Math.max(10, ...series.flatMap(s => s.pts.map(p => p[1] || 0)));
  let cmpSeries = null;
  if (state.cmp) {
    cmpSeries = rttSeries(state.cmp, t);
    yMax = Math.max(yMax, ...cmpSeries.flatMap(s => s.pts.map(p => p[1] || 0)));
  }
  yMax = Math.pow(10, Math.ceil(Math.log10(yMax * 1.2)));
  legend($('rtt-legend'), series);
  const rttOpts = { x0, x1: dur, log: true, yMin: 0.3, yMax, fmt: v => fmtMs(v), now: t, marks };
  lineChart($('rtt'), series, rttOpts);
  $('rtt-compare-wrap').hidden = !state.cmp;
  if (state.cmp) {
    $('rtt-compare-title').textContent = 'Same moment in "' + (state.cmp.title || SETUP_LABEL[state.cmp.setup]) + '" (same scale)';
    const cm = allEvents(state.cmp).filter(e => e.rt <= t && /PROTECT|ADJUST|HANDOVER/.test(e.event))
      .map(e => ({ t: e.rt, color: e.event === 'HANDOVER' ? css('--muted') : css('--warning') }));
    lineChart($('rtt-compare'), cmpSeries, Object.assign({}, rttOpts, { x1: Math.max(dur, duration(state.cmp)), marks: cm }));
  }

  // throughput chart for the selected switch
  $('sw-name').textContent = state.sw;
  const tput = SLICES.map(s => ({
    key: s.key, label: s.label, color: color(s.key),
    pts: rec.frames.filter(f => f.t <= t).map(f => [f.t, f.switches[state.sw] ? (f.switches[state.sw].measured || {})[s.key] ?? null : null]),
  }));
  const limit = { key: 'limit', label: 'eMBB limit', color: color('embb'), dash: '5 4', width: 1.5,
    pts: rec.frames.filter(f => f.t <= t).map(f => [f.t, f.switches[state.sw] ? (f.switches[state.sw].installed || {}).embb ?? null : null]) };
  const tSeries = cfg.slicing_enabled ? tput.concat([limit]) : tput;
  legend($('tput-legend'), tSeries);
  if (!cfg.slicing_enabled) {
    $('tput-legend').textContent = 'Best effort installs no slice meters, so the controller has no per-slice counters to show here. The round-trip times on the left still come from the probes.';
  }
  lineChart($('tput'), tSeries, { x0, x1: dur, yMin: 0, yMax: Math.max(4000, ...tSeries.flatMap(s => s.pts.map(p => p[1] || 0))) * 1.08, fmt: v => fmtKbps(v), now: t, marks });

  // bullets: measured vs installed limit, now
  const bl = $('bullets'); bl.textContent = '';
  const sw = fr.switches[state.sw] || { measured: {}, installed: {} };
  const scaleMax = Math.max(14000, ...SLICES.map(s => Math.max((sw.measured || {})[s.key] || 0, (sw.installed || {})[s.key] || 0)));
  for (const s of SLICES) {
    const m = (sw.measured || {})[s.key] || 0, lim2 = (sw.installed || {})[s.key];
    const row = html('div', { class: 'bullet' });
    const name = html('span', { class: 'name' }); const sq = html('i'); sq.style.background = color(s.key);
    name.appendChild(sq); name.appendChild(document.createTextNode(s.label)); row.appendChild(name);
    const svg = el('svg', { viewBox: '0 0 300 18', preserveAspectRatio: 'none' });
    el('rect', { x: 0, y: 3, width: 300, height: 12, rx: 3, fill: css('--surface-2') }, svg);
    el('rect', { x: 0, y: 3, width: Math.max(0, Math.min(300, m / scaleMax * 300)), height: 12, rx: 3, fill: color(s.key) }, svg);
    if (lim2 != null) el('rect', { x: Math.min(298, lim2 / scaleMax * 300) - 1, y: 0, width: 2.5, height: 18, fill: css('--ink') }, svg);
    row.appendChild(svg);
    row.appendChild(html('span', { class: 'val' }, fmtKbps(m) + (lim2 != null ? ' of ' + fmtKbps(lim2) : ' (no limit)')));
    bl.appendChild(row);
  }

  // table view
  const tb = html('table');
  const hr = html('tr'); ['Flow', 'RTT p50', 'RTT p95', 'Loss', 'Rate'].forEach((h, k) => hr.appendChild(html('th', k ? { class: 'n' } : {}, h)));
  tb.appendChild(hr);
  for (const [f, p] of Object.entries(fr.probes || {}).sort()) {
    const tr = html('tr');
    [flowLabel(f), fmtMs(p.rtt_p50), fmtMs(p.rtt_p95), p.loss_pct == null ? '-' : p.loss_pct.toFixed(1) + '%', fmtKbps(p.kbps)]
      .forEach((v, k) => tr.appendChild(html('td', k ? { class: 'n' } : {}, v)));
    tb.appendChild(tr);
  }
  const tb2 = html('table');
  const hr2 = html('tr'); ['Switch', ...SLICES.map(s => s.label)].forEach((h, k) => hr2.appendChild(html('th', k ? { class: 'n' } : {}, h)));
  tb2.appendChild(hr2);
  for (const [n, s] of Object.entries(fr.switches).sort()) {
    const tr = html('tr'); tr.appendChild(html('td', {}, n));
    SLICES.forEach(sl => tr.appendChild(html('td', { class: 'n' }, fmtKbps((s.measured || {})[sl.key]) + ((s.installed || {})[sl.key] != null ? ' / ' + fmtKbps(s.installed[sl.key]) : ''))));
    tb2.appendChild(tr);
  }
  const nt = $('now-table'); nt.textContent = ''; nt.appendChild(tb); nt.appendChild(tb2);
}
function describe(e) {
  let d = e.detail.replace(/dpid 1152921504606846977/g, 'rsu1').replace(/dpid 1152921504606846978/g, 'rsu2').replace(/dpid 1\b/g, 's1');
  const m = d.match(/^00:00:00:00:00:0(\d) (\w+) port (\d+) -> (\d+)/);
  if (e.event === 'HANDOVER' && m) return `veh${m[1]} now reached through a different port of ${m[2]}: old flows deleted on every switch`;
  return d.replace(/00:00:00:00:00:0(\d)/g, 'veh$1');
}
function setKpi(id, value, sub) {
  $(id).querySelector('.kpi-value').textContent = value;
  $(id).querySelector('.kpi-sub').textContent = sub || '';
}

/* ------------------------------------------------------------ playback */
let lastTick = null;
function tick(ts) {
  if (state.playing && !state.live && state.rec) {
    if (lastTick != null) state.t = Math.min(duration(state.rec), state.t + (ts - lastTick) / 1000 * state.speed);
    if (state.t >= duration(state.rec)) { state.playing = false; $('play').textContent = 'Replay'; }
    renderRun();
  }
  lastTick = ts;
  requestAnimationFrame(tick);
}
async function loadRecording(file) {
  const r = await fetch(file);
  const rec = await r.json();
  rec.frames = rec.frames.filter(f => f.t >= 0);
  return rec;
}
async function selectSource(value) {
  stopLive();
  if (value === '__live') return startLive();
  state.rec = await loadRecording(value);
  state.t = 0; state.lastIdx = -1;
  $('scrub').max = duration(state.rec);
  $('scrub').disabled = false;
  buildMap(state.rec);
  renderRun(true);
}
function startLive() {
  state.live = true;
  state.rec = { title: 'Live', setup: '', scenario: '', meta: {}, frames: [] };
  $('scrub').disabled = true;
  let t0 = null, built = false;
  const poll = async () => {
    try {
      const fr = await (await fetch('/api/live', { cache: 'no-store' })).json();
      if (t0 == null) t0 = fr.t;
      fr.t = fr.t - t0;
      state.rec.meta = fr.meta || {};
      state.rec.scenario = (fr.meta || {}).mobility || '';
      state.rec.frames.push(fr);
      if (state.rec.frames.length > 600) state.rec.frames.shift();
      if (!built && Object.keys(state.rec.meta).length) { buildMap(state.rec); built = true; }
      state.t = fr.t;
      if (built) renderRun(true);
    } catch (e) { /* testbed not running yet */ }
  };
  poll();
  state.liveTimer = setInterval(poll, 1000);
}
function stopLive() { state.live = false; if (state.liveTimer) clearInterval(state.liveTimer); state.liveTimer = null; }

/* ---------------------------------------------------------- results view */
const METRICS = [
  { key: 'rtt_p95', label: 'RTT, 95th percentile', unit: 'ms', log: true },
  { key: 'rtt_mean', label: 'RTT, mean', unit: 'ms', log: true },
  { key: 'rtt_p99', label: 'RTT, 99th percentile', unit: 'ms', log: true },
  { key: 'jitter_ms', label: 'Jitter', unit: 'ms', log: false },
  { key: 'loss_pct', label: 'Loss', unit: '%', log: false },
  { key: 'outage_ms', label: 'Longest delivery gap', unit: 'ms', log: false },
  { key: 'kbps', label: 'Throughput', unit: 'kb/s', log: false },
];
function setupResults() {
  const res = state.results;
  const sc = $('r-scenario'), wi = $('r-window'), me = $('r-metric');
  const scen = [...new Set(res.groups.map(g => g.scenario))];
  sc.textContent = '';
  for (const s of ['congestion', 'heavy', 'handover', 'random'].filter(x => scen.includes(x))) sc.appendChild(html('option', { value: s }, s + ': ' + SCENARIOS[s]));
  me.textContent = '';
  for (const m of METRICS) me.appendChild(html('option', { value: m.key }, m.label));
  const fillWindows = () => {
    const ws = [...new Set(res.groups.filter(g => g.scenario === sc.value && g.flow !== 'embb').map(g => g.window))];
    wi.textContent = '';
    for (const w of ['load', 'idle', 'moving'].filter(x => ws.includes(x))) wi.appendChild(html('option', { value: w }, { load: 'During the eMBB flood', idle: 'Before the flood', moving: 'While moving' }[w]));
  };
  sc.onchange = () => { fillWindows(); renderResults(); };
  wi.onchange = me.onchange = renderResults;
  fillWindows();
  renderResults();
}
function renderResults() {
  const res = state.results, scen = $('r-scenario').value, win = $('r-window').value;
  const metric = METRICS.find(m => m.key === $('r-metric').value);
  $('r-note').textContent = `${res.reps} ${res.reps === 1 ? 'repeat' : 'repeats'} per setup. Bars show the mean across repeats; whiskers show one standard deviation. ` +
    (metric.log ? 'Log scale, because best effort is often 10 to 100 times slower. ' : '') +
    'eMBB throughput is measured during the flood in every window choice.';
  const box = $('r-charts'); box.textContent = '';
  const flows = [...new Set(res.groups.filter(g => g.scenario === scen && (g.window === win || g.flow === 'embb')).map(g => g.flow))];
  const order = ['urllc_edge', 'urllc_far', 'platoon', 'mmtc', 'embb'];
  flows.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  for (const flow of flows) {
    const m = flow === 'embb' ? METRICS.find(x => x.key === 'kbps') : metric;
    const rows = SETUPS.map(s => res.groups.find(g => g.scenario === scen && g.flow === flow && g.setup === s.key && (g.window === win || flow === 'embb')))
      .filter(Boolean).map(g => ({ setup: g.setup, mean: g[m.key] && g[m.key].mean, sd: g[m.key] && g[m.key].sd, n: g.n }))
      .filter(r => r.mean != null);
    if (!rows.length) continue;
    const card = html('div', { class: 'card' });
    card.appendChild(html('h3', {}, flowLabel(flow) + ': ' + m.label + (flow === 'embb' ? ' (during the flood)' : '')));
    card.appendChild(barChart(rows, m, color(flowSlice(flow))));
    box.appendChild(card);
  }
  // table
  const tb = html('table');
  const head = ['Flow', 'Setup', 'n', 'RTT mean', 'RTT p95', 'RTT p99', 'Jitter', 'Loss', 'Longest gap', 'Throughput'];
  const hr = html('tr'); head.forEach((h, k) => hr.appendChild(html('th', k > 1 ? { class: 'n' } : {}, h))); tb.appendChild(hr);
  const ms = o => (o && o.mean != null ? fmtMs(o.mean) + (o.sd ? ' ± ' + o.sd.toFixed(o.sd < 10 ? 1 : 0) : '') : '-');
  for (const flow of flows) for (const s of SETUPS) {
    const g = res.groups.find(x => x.scenario === scen && x.flow === flow && x.setup === s.key && (x.window === win || flow === 'embb'));
    if (!g) continue;
    const tr = html('tr');
    [flowLabel(flow), s.label, String(g.n), ms(g.rtt_mean), ms(g.rtt_p95), ms(g.rtt_p99), ms(g.jitter_ms),
     g.loss_pct && g.loss_pct.mean != null ? g.loss_pct.mean.toFixed(2) + '%' : '-', ms(g.outage_ms), g.kbps && g.kbps.mean != null ? fmtKbps(g.kbps.mean) : '-']
      .forEach((v, k) => tr.appendChild(html('td', k > 1 ? { class: 'n' } : {}, v)));
    tb.appendChild(tr);
  }
  const rt = $('r-table'); rt.textContent = ''; rt.appendChild(tb);
}
function barChart(rows, m, fill) {
  const W = 420, rowH = 30, L = 118, R = 70, T = 6;
  const H = T + rows.length * rowH + 22;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart' });
  const vmax = Math.max(...rows.map(r => r.mean + (r.sd || 0)));
  const vmin = m.log ? Math.max(0.1, Math.min(...rows.map(r => r.mean)) / 2) : 0;
  const log = m.log && vmax / Math.max(vmin, 1e-6) > 20;
  const top = log ? Math.pow(10, Math.ceil(Math.log10(vmax))) : niceStep(vmax / 4) * 4 || 1;
  const xs = v => L + (log ? (Math.log10(Math.max(v, vmin)) - Math.log10(vmin)) / (Math.log10(top) - Math.log10(vmin)) : v / top) * (W - L - R);
  el('line', { x1: L, x2: L, y1: T, y2: T + rows.length * rowH, stroke: css('--axis') }, svg);
  const fmt = v => (m.unit === 'ms' ? fmtMs(v) : m.unit === '%' ? v.toFixed(v < 10 ? 2 : 1) + '%' : fmtKbps(v));
  rows.forEach((r, k) => {
    const y = T + k * rowH + 6;
    el('text', { x: L - 8, y: y + 13, 'text-anchor': 'end', class: 'lbl' }, svg).textContent = SETUP_LABEL[r.setup];
    const w = Math.max(2, xs(r.mean) - L);
    const bar = el('rect', { x: L, y, width: w, height: 18, rx: 4, fill }, svg);
    if (r.sd) {
      const a = xs(Math.max(log ? vmin : 0, r.mean - r.sd)), b = xs(r.mean + r.sd);
      el('line', { x1: a, x2: b, y1: y + 9, y2: y + 9, stroke: css('--ink'), 'stroke-width': 1.5 }, svg);
      el('line', { x1: b, x2: b, y1: y + 4, y2: y + 14, stroke: css('--ink'), 'stroke-width': 1.5 }, svg);
    }
    el('text', { x: Math.max(xs(r.mean), xs(r.mean + (r.sd || 0))) + 6, y: y + 13, class: 'lbl' }, svg).textContent = fmt(r.mean);
    bar.addEventListener('pointermove', ev => showTip(ev, [[fill, SETUP_LABEL[r.setup], fmt(r.mean) + (r.sd ? ' ± ' + fmt(r.sd) : '')], [null, r.n + ' repeats']], m.label));
    bar.addEventListener('pointerleave', hideTip);
  });
  el('text', { x: W - R, y: H - 4, 'text-anchor': 'end' }, svg).textContent = log ? 'log scale' : '';
  return svg;
}

/* ---------------------------------------------------------- explain view */
function buildExplain() {
  const st = html('table');
  const hr = html('tr'); ['Slice', 'Traffic', 'Matched by', 'Budget per switch', 'Queue band'].forEach(h => hr.appendChild(html('th', {}, h))); st.appendChild(hr);
  const budgets = { urllc: '5 Mb/s', platoon: '4 Mb/s', embb: '12 Mb/s (loop may lower it)', mmtc: '1 Mb/s', best_effort: '2 Mb/s' };
  for (const s of SLICES) {
    const tr = html('tr');
    const td = html('td'); const sq = html('i'); sq.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;background:${color(s.key)}`;
    td.appendChild(sq); td.appendChild(document.createTextNode(s.label)); tr.appendChild(td);
    [s.what, s.port, budgets[s.key], s.band].forEach(v => tr.appendChild(html('td', {}, v)));
    st.appendChild(tr);
  }
  const box = $('slice-table'); box.textContent = ''; box.appendChild(st);
  const su = html('table');
  const h2 = html('tr'); ['Setup', 'What is switched on'].forEach(h => h2.appendChild(html('th', {}, h))); su.appendChild(h2);
  for (const s of SETUPS) { const tr = html('tr'); tr.appendChild(html('td', {}, s.label)); tr.appendChild(html('td', {}, s.desc)); su.appendChild(tr); }
  const b2 = $('setup-table'); b2.textContent = ''; b2.appendChild(su);
  // architecture diagram
  const svg = $('arch'); svg.textContent = '';
  const node = (x, y, w, h, title, sub, strong) => {
    el('rect', { x, y, width: w, height: h, rx: 8, fill: strong ? css('--surface-2') : css('--surface'), stroke: css('--axis'), 'stroke-width': strong ? 2 : 1 }, svg);
    el('text', { x: x + w / 2, y: y + h / 2 - 2, 'text-anchor': 'middle', 'font-weight': 600 }, svg).textContent = title;
    el('text', { x: x + w / 2, y: y + h / 2 + 14, 'text-anchor': 'middle', class: 'sub' }, svg).textContent = sub;
  };
  const wire = (x1, y1, x2, y2, label, dash) => {
    el('line', { x1, y1, x2, y2, stroke: css('--ink-2'), 'stroke-width': 1.5, 'stroke-dasharray': dash || '' }, svg);
    if (label) el('text', { x: (x1 + x2) / 2 + 6, y: (y1 + y2) / 2 - 4, class: 'sub' }, svg).textContent = label;
  };
  node(330, 6, 240, 50, 'RYU orchestrator', 'slices, meters, loop, REST :8081', true);
  node(380, 110, 140, 46, 's1', 'aggregation switch');
  node(120, 190, 140, 46, 'rsu1', 'OVS access point');
  node(640, 190, 140, 46, 'rsu2', 'OVS access point');
  node(700, 100, 180, 46, 'infotain + telemetry', 'central servers');
  node(10, 250, 100, 40, 'MEC 1', 'edge server');
  node(790, 250, 100, 40, 'MEC 2', 'edge server');
  node(300, 252, 300, 40, '6 vehicles (Wi-Fi stations)', 'scripted paths or random waypoint');
  wire(450, 56, 450, 110, 'OpenFlow 1.3', '4 3');
  wire(380, 50, 190, 190, '', '4 3'); wire(520, 50, 710, 190, '', '4 3');
  wire(390, 150, 250, 196, '20 Mb/s, 5 ms'); wire(510, 150, 650, 196, '20 Mb/s, 5 ms');
  wire(520, 133, 700, 123, '100 Mb/s, 15 ms');
  wire(150, 236, 70, 250, '0.5 ms'); wire(750, 236, 830, 250, '0.5 ms');
  wire(220, 236, 330, 252, 'Wi-Fi', '2 3'); wire(680, 236, 570, 252, 'Wi-Fi', '2 3');
}

/* ------------------------------------------------------------------ init */
async function init() {
  const saved = (() => { try { return localStorage.getItem('v2x-theme'); } catch (e) { return null; } })();
  if (saved) document.documentElement.dataset.theme = saved;
  $('theme').onclick = () => {
    const dark = getComputedStyle(document.documentElement).getPropertyValue('color-scheme').trim() === 'dark';
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('v2x-theme', document.documentElement.dataset.theme); } catch (e) { /* ignore */ }
    if (state.rec) { buildMap(state.rec); renderRun(true); }
    buildExplain(); if (state.results) renderResults();
  };
  document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => {
    document.querySelectorAll('.tabs button').forEach(x => x.setAttribute('aria-selected', x === b));
    document.querySelectorAll('.view').forEach(v => v.hidden = v.id !== 'view-' + b.dataset.view);
  });
  $('play').onclick = () => {
    if (state.live) return;
    if (state.t >= duration(state.rec)) state.t = 0;
    state.playing = !state.playing;
    $('play').textContent = state.playing ? 'Pause' : 'Play';
  };
  $('speed').onchange = e => { state.speed = +e.target.value; };
  $('scrub').oninput = e => { state.t = +e.target.value; renderRun(true); };
  document.querySelectorAll('#sw-pick button').forEach(b => b.onclick = () => {
    document.querySelectorAll('#sw-pick button').forEach(x => x.setAttribute('aria-pressed', x === b));
    state.sw = b.dataset.sw; renderRun(true);
  });
  buildExplain();

  let recs = [];
  try { recs = await (await fetch('/api/recordings')).json(); }
  catch (e) { try { recs = await (await fetch('recordings/index.json')).json(); } catch (e2) { recs = []; } }
  const src = $('source'), cmp = $('compare');
  const rank = r => (r.scenario === 'scripted' ? 0 : 2) + (r.setup === 'orchestrated' ? 0 : 1);
  recs.sort((a, b) => rank(a) - rank(b));
  for (const r of recs) {
    const mob = r.scenario === 'random' ? 'random waypoint vehicles' : 'scripted intersecting paths';
    const label = (SETUP_LABEL[r.setup] || r.setup) + ', ' + mob;
    src.appendChild(html('option', { value: r.file }, label));
    cmp.appendChild(html('option', { value: r.file }, label));
  }
  src.appendChild(html('option', { value: '__live' }, 'Live testbed (needs the live demo running)'));
  src.onchange = () => selectSource(src.value);
  cmp.onchange = async () => { state.cmp = cmp.value ? await loadRecording(cmp.value) : null; renderRun(true); };
  // Deep links, e.g. ?rec=random_best_effort&cmp=random_orchestrated&t=55 or ?view=results&scenario=heavy
  const q = new URLSearchParams(location.search);
  const recFile = name => { const r = recs.find(x => x.file.endsWith('/' + name + '.json') || x.file === name); return r && r.file; };
  const first = (q.get('rec') && recFile(q.get('rec'))) || (recs.length && recs[0].file);
  if (first) { src.value = first; await selectSource(first); }
  if (q.get('cmp') && recFile(q.get('cmp'))) { cmp.value = recFile(q.get('cmp')); state.cmp = await loadRecording(cmp.value); }
  if (q.get('t') && state.rec) { state.t = Math.min(+q.get('t'), duration(state.rec)); renderRun(true); }

  try {
    state.results = await (await fetch('results.json', { cache: 'no-store' })).json();
    setupResults();
    for (const [k, id] of [['scenario', 'r-scenario'], ['window', 'r-window'], ['metric', 'r-metric']]) {
      if (q.get(k)) { $(id).value = q.get(k); $(id).dispatchEvent(new Event('change')); }
    }
  } catch (e) {
    $('r-note').textContent = 'No results.json yet. Run experiments/analyze.py after the experiments finish.';
  }
  if (q.get('view')) { const b = document.querySelector(`.tabs button[data-view="${q.get('view')}"]`); if (b) b.click(); }
  requestAnimationFrame(tick);
}
init();
