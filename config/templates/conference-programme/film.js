// For: the people who follow a conference -- its programme as a metro map, for the event's own channels
/* A conference's programme in 90 s, with no narration: the music carries it. This film is a template:
   every word, time, colour, logo and person is in content.json (SK.DATA.content) and nothing of the
   event is in the code, so another conference is another content.json and its pictures.

   The story is a transit map. Each track is a coloured line; the highlighted sessions are stations;
   a keynote is an interchange, where every line meets; each day is a row of the network, joined to
   the next by a bend. The film opens on the logo while the legend draws its lines and the lines race
   out across the map; dives to the terminus, where a departure board shows the first day; rides a
   cab from stop to stop, an enamel sign at each one (time, title, speaker, room); rounds a bend into
   every new day under its own board; pulls back to the whole network as night falls, with the
   evening's stops on a night board; and turns into the poster: the map, the dates, the place, the
   address and the button.

   The clock below (B, SCHED) is the one home of its timing, at 112 bpm. The ride's slots are worked
   out from how many stops and days the content has, always on the beat and always inside the same
   bars, so the film is the same length for any programme; the score and every sound cue are worked
   out from that clock and the content at the bottom of this file (SK.film({sound})), so
   `sketch-render.py --sound-data` writes a score.json and sfx.json that fit whatever the programme is.
   World units are the poster's pixels: the camera at zoom 1 on the middle of the frame is the poster.
*/
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, TAU = SK.TAU, rnd = SK.rnd;
const CX = W / 2, CY = H / 2;
const D = SK.DATA.content;

/* ------------------------------------------------------------------ the palette
   paper (the map), ink (its type), ground (the enamel of the signs), accent (the button, the LED
   boards, the night stops) and light; every shade the film draws is worked out from them. */
function rgbOf(hex) { const n = parseInt(String(hex).slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function hslOf(hex) {
  const [r, g2, b] = rgbOf(hex).map((v) => v / 255), mx = Math.max(r, g2, b), mn = Math.min(r, g2, b), l = (mx + mn) / 2;
  if (mx === mn) return [0, 0, l];
  const d = mx - mn, s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
  const h = mx === r ? (g2 - b) / d + (g2 < b ? 6 : 0) : mx === g2 ? (b - r) / d + 2 : (r - g2) / d + 4;
  return [h / 6, s, l];
}
function withL(hex, l, sk = 1) { // the colour at lightness l (0..1), its saturation times sk
  const [h, s0] = hslOf(hex), s = clamp(s0 * sk), L = clamp(l);
  const q = L < .5 ? L * (1 + s) : L + s - L * s, p = 2 * L - q;
  const ch = (x) => { x = (x + 1) % 1; return x < 1 / 6 ? p + (q - p) * 6 * x : x < .5 ? q : x < 2 / 3 ? p + (q - p) * (2 / 3 - x) * 6 : p; };
  return '#' + [ch(h + 1 / 3), ch(h), ch(h - 1 / 3)].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
}
function mixHex(a, b, u) {
  const x = rgbOf(a), y = rgbOf(b);
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * u).toString(16).padStart(2, '0')).join('');
}
function lum(hex) { const [r, g2, b] = rgbOf(hex).map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * r + .7152 * g2 + .0722 * b; }
function contrast(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); }
const Lof = (hex) => hslOf(hex)[2];
function palette(p) {
  const light = p.light ?? '#FFFFFF', paper = p.paper ?? '#F4F3EF';
  let ink = p.ink ?? '#1E2024';
  while (contrast(ink, paper) < 9 && Lof(ink) > .04) ink = withL(ink, Lof(ink) - .03);
  // the signs' enamel: light type on it must read at 6:1 or better
  let ground = p.ground ?? ink;
  while (contrast(ground, light) < 6 && Lof(ground) > .04) ground = withL(ground, Lof(ground) - .02);
  const accent = p.accent ?? '#E8A317', g0 = Lof(ground);
  // the LED boards light up in the accent, bright enough to glow on black
  const led = withL(accent, Math.max(Lof(accent), .6), 1.1);
  return {
    paper, light, ink, ground, accent, led,
    paperDk: mixHex(paper, ink, .045), // the band of every other day
    hair: mixHex(paper, ink, .18), // hairlines and ticks on the paper
    inkSoft: mixHex(ink, paper, .42),
    groundDk: withL(ground, g0 * .6), groundLt: withL(ground, Math.min(.62, g0 * 1.45 + .05)),
    soft: mixHex(light, ground, .32), // quieter type on the enamel
    night: withL(ground, .07, .85), nightBand: withL(ground, .095, .85), nightType: mixHex(light, ground, .2),
    accentDk: withL(accent, Lof(accent) * .72),
    onAccent: contrast(accent, '#FFFFFF') >= 2.6 ? '#FFFFFF' : ink,
    shadow: rgbOf(withL(ground, .06)).join(','),
  };
}
const C = palette(D.palette || {});
SK.setStyle('clean', { grain: .3, vignette: .1, handheld: 0, vignetteRGB: C.shadow });
Object.assign(SK.C, { paper: C.paper, text: C.ink, textSoft: C.inkSoft, accent: C.accent, accentText: C.accent, ink: C.ink });
const FONT = { cond: '"Sofia Sans Condensed"', wide: '"Sofia Sans"', mono: '"IBM Plex Mono"', ...(D.fonts || {}) };
const onColour = (col) => (contrast(col, '#FFFFFF') >= 3 ? '#FFFFFF' : C.ink);

/* ------------------------------------------------------------------ the words */
const EV = D.event || {};
const CP = D.copy || {};
const fillIn = (str, extra = {}) => String(str ?? '').replace(/\{(\w+)\}/g, (_, k) => String(extra[k] ?? EV[k] ?? ''));
const KINDS = CP.kinds || {};
const EVENT = {
  name: String(EV.name ?? ''), year: EV.year ? String(EV.year) : '', full: String(EV.full_name ?? ''),
  city: String(EV.city ?? ''), country: String(EV.country ?? ''), venue: String(EV.venue ?? ''),
  dates: String(EV.dates ?? ''), url: String(EV.url ?? ''), cta: String(EV.cta ?? ''),
};
// the name with its year, unless the name already says it
EVENT.title = EVENT.year && !EVENT.name.includes(EVENT.year) ? `${EVENT.name} ${EVENT.year}` : EVENT.name;
EVENT.place = [EVENT.venue, EVENT.city].filter(Boolean).join(' · ');
const DAYS = (D.days && D.days.length ? D.days : [{}]).slice(0, 6).map((d, i) => ({
  n: i + 1, name: fillIn(CP.day ?? '{n}', { n: i + 1 }), when: [d.label, d.date].filter(Boolean).join(' '),
}));
const ND = DAYS.length;
const dayLine = (d) => [DAYS[d].name, DAYS[d].when].filter(Boolean).join(' · ');

/* ------------------------------------------------------------------ the lines and the stops */
const SPARE = ['#E4572E', '#2E86AB', '#3BB273', '#7768AE', '#F2A541', '#C0367A'];
const TRACKS = (D.tracks || []).slice(0, 6).map((tr, k) => ({ id: tr.id ?? String(k), name: String(tr.name ?? ''), col: tr.colour || tr.color || SPARE[k % 6], k }));
if (!TRACKS.length) TRACKS.push({ id: '0', name: '', col: C.ground, k: 0 });
const NT = TRACKS.length;
const TIX = Object.fromEntries(TRACKS.map((tr) => [tr.id, tr.k]));
/** a time as the schedule prints it (09:25, 9.25, 9:25 AM, 14h00, 2 PM) -> minutes after midnight */
function minutes(s) {
  const m = String(s ?? '').trim().match(/^(\d{1,2})(?:[:.h](\d{2}))?\s*(?:([ap])\.?\s*m\.?)?/i);
  if (!m) return null;
  let h = +m[1]; const mm = +(m[2] || 0);
  if (m[3]) { const pm = m[3].toLowerCase() === 'p'; h = h % 12 + (pm ? 12 : 0); }
  return h * 60 + mm;
}
const ALL = (D.stops || []).map((s, i) => ({
  ...s, i, d: clamp(Math.round(+s.day || 1) - 1, 0, ND - 1), min: minutes(s.time), kind: s.kind || 'talk',
  k: TIX[s.track] ?? null, title: String(s.title ?? ''), time: String(s.time ?? ''),
}));
const byTime = (a, b) => a.d - b.d || (a.min ?? 0) - (b.min ?? 0) || a.i - b.i;
const RIDE = ALL.filter((s) => s.kind !== 'social').sort(byTime).slice(0, 12);
const NIGHT = ALL.filter((s) => s.kind === 'social').sort(byTime).slice(0, 3);
// a keynote is an interchange: every line meets there (and so does a stop on no line)
for (const s of RIDE) s.ic = s.kind === 'keynote' || s.k === null;
for (const s of NIGHT) s.ic = true;
const lineOf = (s) => (s.k === null ? null : TRACKS[s.k]);
const CYRILLIC = /[Ѐ-ӿ]/.test(JSON.stringify([D.event, D.copy, D.days, D.tracks, D.stops]));
/* Sofia Sans draws Bulgarian letterforms by default (a lowercase te like an m) and keeps the standard
   Cyrillic ones behind its RUS localised forms; Cyrillic in any language but Bulgarian (content.lang
   "bg") is shaped with that tag. A shaping tag on the canvas only: nothing of it is shown. */
function standardCyrillic(ctx) {
  if (!CYRILLIC || D.lang === 'bg') return;
  ctx.canvas.setAttribute('lang', 'ru');
  if ('lang' in ctx) ctx.lang = 'ru';
}

/* ------------------------------------------------------------------ the map: one row a day, a snake
   The poster's map fills MAP; each day is a row (left to right, then right to left, ...), joined to
   the next by a half-circle bend (a one-day event takes two rows, morning and afternoon, so its map is
   a snake too). The bundle of lines runs along a centre line; line k sits at a fixed lateral offset
   from it, so the bends come out concentric. Near an interchange the bundle pinches. */
const MAP = { x0: 700, x1: 1852, y0: 92, y1: 1000 };
const STOPS = [...RIDE, ...NIGHT].sort(byTime);
const ROWS = ND > 1 || STOPS.length < 4 ? DAYS.map((_, d) => ({ d, first: true })) : [{ d: 0, first: true }, { d: 0, first: false }];
if (ROWS.length === 2 && ND === 1) STOPS.forEach((s, i) => { s.r = i < Math.ceil(STOPS.length / 2) ? 0 : 1; });
else STOPS.forEach((s) => { s.r = s.d; });
const NR = ROWS.length;
const ROWH = (MAP.y1 - MAP.y0) / NR;
const SP = Math.min(clamp(ROWH * .085, 10, 28), ROWH * .4 / Math.max(1, NT - 1)); // line spacing
const LW = SP * .6; // line width
const HALF = (NT - 1) / 2 * SP;
const BR = ROWH / 2; // the bend's radius (the centre line)
const PADX = NR > 1 ? BR + HALF + LW * 2 : 70;
const rowY = (r) => MAP.y0 + ROWH * (r + .5);
const SEG = [];
let STOTAL = 0;
for (let r = 0; r < NR; r++) {
  const y = rowY(r), xa = MAP.x0 + PADX, xb = MAP.x1 - PADX, right = r % 2 === 0;
  const a = right ? [xa, y] : [xb, y], b = right ? [xb, y] : [xa, y];
  SEG.push({ type: 'line', a, b, dir: right ? 1 : -1, s0: STOTAL, len: xb - xa, row: r });
  STOTAL += xb - xa;
  if (r < NR - 1) {
    SEG.push({ type: 'arc', c: [b[0], y + BR], th0: -Math.PI / 2, dth: right ? Math.PI : -Math.PI, s0: STOTAL, len: Math.PI * BR, row: r });
    STOTAL += Math.PI * BR;
  }
}
const ROWSEG = SEG.filter((q) => q.type === 'line');
/** the centre line at arc length s: point, direction, normal */
function pathAt(s) {
  s = clamp(s, 0, STOTAL);
  let g = SEG[SEG.length - 1];
  for (const q of SEG) if (s <= q.s0 + q.len) { g = q; break; }
  const u = s - g.s0;
  if (g.type === 'line') return { p: [g.a[0] + g.dir * u, g.a[1]], d: [g.dir, 0], n: [0, g.dir] };
  const th = g.th0 + g.dth * (u / g.len), sg = Math.sign(g.dth);
  const d = [-Math.sin(th) * sg, Math.cos(th) * sg];
  return { p: [g.c[0] + BR * Math.cos(th), g.c[1] + BR * Math.sin(th)], d, n: [-d[1], d[0]] };
}
// the stops along their day's row, by time, kept apart
(function place() {
  for (let r = 0; r < NR; r++) {
    const g = ROWSEG[r], here = STOPS.filter((s) => s.r === r), n = here.length;
    if (!n) continue;
    const lo = g.s0 + g.len * .1, hi = g.s0 + g.len * .9, ts = here.map((s) => s.min ?? 0);
    const t0 = Math.min(...ts) - 50, t1 = Math.max(...ts) + 50;
    const pos = here.map((s) => (n === 1 ? (lo + hi) / 2 : lerp(lo, hi, ((s.min ?? 0) - t0) / (t1 - t0))));
    const gap = Math.min((hi - lo) / Math.max(1, n - 1), Math.max(LW * 9, g.len * .12));
    for (let i = 1; i < n; i++) pos[i] = Math.max(pos[i], pos[i - 1] + gap);
    pos[n - 1] = Math.min(pos[n - 1], hi);
    for (let i = n - 2; i >= 0; i--) pos[i] = Math.min(pos[i], pos[i + 1] - gap);
    here.forEach((s, i) => { s.s = Math.max(lo, pos[i]); s.side = (i + (ROWS[r].first ? 0 : 1)) % 2 ? -1 : 1; }); // a day's first below: its name is above
  }
  for (const s of STOPS) if (s.s === undefined) s.s = ROWSEG[s.r].s0 + ROWSEG[s.r].len / 2;
})();
const PINCH = .45;
const PINCHES = [...RIDE, ...NIGHT].filter((s) => s.ic).map((s) => s.s);
const PW1 = LW * 1.8, PW2 = PW1 + HALF * (1 - PINCH) * 1.5 + 1;
function squeeze(s) {
  let b = 0;
  for (const x of PINCHES) { const d = Math.abs(s - x); b = Math.max(b, d <= PW1 ? 1 : d >= PW2 ? 0 : E.inOut(1 - (d - PW1) / (PW2 - PW1))); }
  return 1 - (1 - PINCH) * b;
}
const laneOf = (k) => (k - (NT - 1) / 2) * SP;
function at(s, lane) { const q = pathAt(s), o = lane * squeeze(s); return [q.p[0] + q.n[0] * o, q.p[1] + q.n[1] * o]; }
// every line's points, once
const STEP = 5;
const LINES = TRACKS.map((tr) => { const pts = []; for (let s = 0; s <= STOTAL + .1; s += STEP) pts.push(at(Math.min(s, STOTAL), laneOf(tr.k))); return pts; });
const stopXY = (s) => (s.ic ? at(s.s, 0) : at(s.s, laneOf(s.k)));
// quiet stations on the outer lines, between the highlights: the rest of the programme
const TICKS = [];
for (const g of ROWSEG) {
  for (let s = g.s0 + 40; s < g.s0 + g.len - 30; s += 36 + rnd(Math.floor(s)) * 54) {
    if ([...RIDE, ...NIGHT].some((x) => Math.abs(x.s - s) < LW * 5 + PW2)) continue;
    TICKS.push({ s, k: rnd(Math.floor(s) * 7 + 3) < .5 ? 0 : NT - 1 });
  }
}

/* ------------------------------------------------------------------ the clock (112 bpm: a beat is .536 s, a bar 2.14 s)
   Beats: the logo and the legend 0-13, the dive 13-16, the first day's board 16-24, the ride 24-136
   (its stops, its changes of day and the run to the end of the line), the night 136-150, the poster
   150-168 with its last chord on 160. */
const BPM = 112, BEAT = 60 / BPM, bt = (b) => b * BEAT;
const B_DIVE = 13;
const B = { legend: 3.5, dive: 13, depart: 16, ride: 24, rideEnd: 136, dawn: 150, poster: 152, last: 160, end: 168 };
const DURATION = bt(B.end); // 90 s: 42 bars
const TRAVEL = 2, CHANGE = 8; // beats a cab takes between two stops; beats a change of day takes
const SCHED = [];
let SLOT = 0;
(function schedule() {
  const changes = RIDE.reduce((n, s, i) => n + (i && s.d !== RIDE[i - 1].d ? 1 : 0), 0);
  const avail = B.rideEnd - B.ride - CHANGE * changes - 4; // 4 beats at least for the run to the end of the line
  SLOT = clamp(Math.floor(avail / Math.max(1, RIDE.length)), 4, 16);
  let b = B.ride;
  RIDE.forEach((s, i) => {
    if (i && s.d !== RIDE[i - 1].d) { SCHED.push({ type: 'change', b0: b, b1: b + CHANGE, from: RIDE[i - 1], to: s }); b += CHANGE; }
    const far = i && s.r !== RIDE[i - 1].r && s.d === RIDE[i - 1].d; // round a bend within a day
    const it = { type: 'stop', b0: b, arrive: b + TRAVEL + (far && SLOT >= 8 ? 1 : 0), b1: b + SLOT, stop: s, i };
    SCHED.push(it); s.slot = it; b += SLOT;
  });
  SCHED.push({ type: 'end', b0: Math.min(b, B.rideEnd - 4), b1: B.rideEnd });
})();
const END = SCHED[SCHED.length - 1];

/* the cab: where it is on the map, as arc length and lane, at any moment */
const RUNS = [];
(function runs() {
  let s = LW * 3, lane = RIDE.length && !RIDE[0].ic ? laneOf(RIDE[0].k) : 0;
  for (const it of SCHED) {
    if (it.type === 'stop') {
      const L1 = it.stop.ic ? 0 : laneOf(it.stop.k);
      RUNS.push({ t0: bt(it.b0), t1: bt(it.arrive), s0: s, s1: it.stop.s, L0: lane, L1 });
      s = it.stop.s; lane = L1;
    } else if (it.type === 'change') { // to the start of the next day's row, round the bend, and wait there
      const g = ROWSEG[it.to.r], s1 = g.s0 + Math.min(g.len * .06, 40), L1 = it.to.ic ? 0 : laneOf(it.to.k);
      RUNS.push({ t0: bt(it.b0) + .05, t1: bt(it.b0 + 5.5), s0: s, s1, L0: lane, L1 });
      s = s1; lane = L1;
    } else {
      RUNS.push({ t0: bt(it.b0), t1: bt(it.b0) + Math.max(1.2, Math.min(2.6, bt(it.b1 - it.b0) * .6)), s0: s, s1: STOTAL, L0: lane, L1: 0 });
    }
  }
})();
const START_LANE = RUNS.length ? RUNS[0].L0 : 0;
function cab(t) {
  let s = LW * 3, L = START_LANE, u = 0, run = null;
  for (const r of RUNS) {
    if (t < r.t0) break;
    run = r; u = clamp((t - r.t0) / (r.t1 - r.t0));
    s = lerp(r.s0, r.s1, E.inOut(u)); L = lerp(r.L0, r.L1, E.inOut(clamp((u - .25) / .75)));
  }
  const q = pathAt(s), o = L * squeeze(s);
  return { s, L, p: [q.p[0] + q.n[0] * o, q.p[1] + q.n[1] * o], d: q.d, moving: run && u > 0 && u < 1, run, u };
}

/* ------------------------------------------------------------------ the camera
   The poster's view is zoom 1 on the middle of the frame. The film opens on its left column, dives to
   the terminus, rides with the cab (which sits low in the frame, its sign above it), pulls back a
   little round each bend, and comes back out to the poster for the night and the end. */
const ZR = clamp(54 / SP, 1.7, 4.4); // the ride's zoom: the lines a steady width on screen, whatever the map
const OFFY = 255; // the cab sits this far below the middle of the frame
const COL = { x: 92, w: 540 }; // the poster's left column
// the open: close on the column while the name and the title arrive, then out to the whole map drawing itself
const OPEN_KEYS = [[0, [COL.x + COL.w / 2 + 170, 372, 1.42]], [bt(3.2), [COL.x + COL.w / 2 + 150, 380, 1.36]], [bt(8), [CX, CY, 1]], [bt(B_DIVE), [CX - 14, CY, 1.03]]];
const NIGHT_CAM = [CX, CY, 1];
const POSTER_PUSH = (t) => 1 + .028 * E.sine(clamp((t - bt(B.rideEnd)) / bt(B.end - B.rideEnd)));
function mixCam(a, b, u) { // from one view to another, evenly on screen (as SK.camera does)
  if (u <= 0) return a; if (u >= 1) return b;
  const z = Math.exp(lerp(Math.log(a[2]), Math.log(b[2]), u)), wa = 1 / a[2], wb = 1 / b[2];
  const uu = Math.abs(wb - wa) < 1e-6 ? u : clamp((1 / z - wa) / (wb - wa));
  return [lerp(a[0], b[0], uu), lerp(a[1], b[1], uu), z];
}
function rideCam(t) {
  const c = cab(t);
  let z = ZR * lerp(.92, 1, E.inOut(clamp((t - bt(B.depart)) / bt(B.ride - B.depart + 1))));
  for (const it of SCHED) if (it.type === 'change') { const u = clamp((t - bt(it.b0)) / bt(CHANGE - 1)); z *= 1 - .36 * Math.sin(Math.PI * u); }
  // at the terminus the cab sits left of the middle, so the lines run out ahead of it
  const lead = (CX - 600) * (1 - E.inOut(clamp((t - bt(B.ride)) / bt(TRAVEL + 1))));
  return [c.p[0] + lead / z, c.p[1] - OFFY / z, z];
}
function camAt(t) {
  if (t < bt(B.dive)) {
    let i = 0; while (i < OPEN_KEYS.length - 2 && t > OPEN_KEYS[i + 1][0]) i++;
    const [t0, a] = OPEN_KEYS[i], [t1, b] = OPEN_KEYS[i + 1];
    return mixCam(a, b, (i === 1 ? E.inOut : E.sine)(clamp((t - t0) / (t1 - t0))));
  }
  if (t < bt(B.depart)) {
    const u = E.inOut(clamp((t - bt(B.dive)) / bt(B.depart - B.dive)));
    return mixCam(OPEN_KEYS[OPEN_KEYS.length - 1][1], rideCam(t), u);
  }
  if (t < bt(END.b0)) return rideCam(t);
  // the run to the end of the line, and out to the whole network as night falls
  const u = E.inOut(clamp((t - bt(END.b0) - .35) / Math.max(1.6, bt(B.rideEnd - END.b0) - .2)));
  const v = mixCam(rideCam(t), NIGHT_CAM, u);
  return [v[0] - 10 * (POSTER_PUSH(t) - 1) / .028, v[1], v[2] * POSTER_PUSH(t)];
}

/* ------------------------------------------------------------------ small helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (t) => { const c3 = k + 1; return 1 + c3 * Math.pow(t - 1, 3) + k * Math.pow(t - 1, 2); };
const outBack = back(1.5), outBackSoft = back(.8);
function font(size, wt = 800, fam = FONT.cond) { return `${wt} ${size}px ${fam}`; }
/** text at x, y (alphabetic baseline). o: size, wt, fam, col, align, ls (px), alpha */
function text(str, x, y, o = {}) {
  const c = g(); c.save();
  c.font = font(o.size ?? 40, o.wt ?? 800, o.fam ?? FONT.cond);
  c.textAlign = o.align ?? 'left'; c.textBaseline = 'alphabetic';
  c.letterSpacing = (o.ls ?? 0) + 'px';
  c.globalAlpha *= o.alpha ?? 1; c.fillStyle = o.col ?? C.ink;
  if (o.glow) { c.shadowColor = o.glow; c.shadowBlur = o.blur ?? 14; }
  c.fillText(str, x, y); c.restore();
}
function measure(str, o = {}) {
  const c = g(); c.save(); c.font = font(o.size ?? 40, o.wt ?? 800, o.fam ?? FONT.cond); c.letterSpacing = (o.ls ?? 0) + 'px';
  const w = c.measureText(str).width; c.restore(); return w;
}
/** the largest size up to max at which str fits in width */
function fit(str, width, max, o = {}) { return Math.min(max, max * width / Math.max(1, measure(str, { ...o, size: max }))); }
/** str in lines no wider than width at size (words kept whole unless one alone is too wide) */
function wrap(str, width, o) {
  const words = String(str).split(/\s+/).filter(Boolean), lines = [];
  let cur = '';
  for (const w0 of words) {
    let w = w0;
    while (measure(w, o) > width) { // a word wider than the line: break it
      let k = w.length - 1; while (k > 1 && measure(w.slice(0, k) + '-', o) > width) k--;
      if (cur) { lines.push(cur); cur = ''; }
      lines.push(w.slice(0, k) + '-'); w = w.slice(k);
    }
    const tryIt = cur ? cur + ' ' + w : w;
    if (measure(tryIt, o) <= width) cur = tryIt; else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  return lines;
}
/** a title in at most maxLines lines of width: the size it fits at (max down to min), its lines; cut with an ellipsis if even min will not do */
function fitBlock(str, width, maxLines, max, min, o = {}) {
  for (let size = max; size >= min; size -= 2) {
    const lines = wrap(str, width, { ...o, size });
    if (lines.length <= maxLines) return { size, lines };
  }
  const lines = wrap(str, width, { ...o, size: min }).slice(0, maxLines);
  let last = lines[maxLines - 1];
  while (last.length > 1 && measure(last + '…', { ...o, size: min }) > width) last = last.slice(0, -1);
  lines[maxLines - 1] = last.replace(/[\s,.:;–-]+$/, '') + '…';
  return { size: min, lines };
}
function rrect(x, y, w, h, r, fill) { const c = g(); SK.rrPath(x, y, w, h, r); c.fillStyle = fill; c.fill(); }
function clipRect(x, y, w, h, fn) { const c = g(); c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); fn(); c.restore(); }
function withT(x, y, rot, s, fn) { SK.at(x, y, rot, s, fn); }
const LG = D.logo || {};
const logoImg = (light) => SK.IMG[(light && LG.light) || LG.image] || SK.IMG[LG.image];
/** the logo fitted into a w x h box whose top-left is x, y; returns the size drawn */
function logo(x, y, w, h, o = {}) {
  const im = logoImg(o.light); if (!im) return [0, 0];
  const s = Math.min(w / im.width, h / im.height), dw = im.width * s, dh = im.height * s;
  const dx = o.align === 'center' ? x + (w - dw) / 2 : x, dy = o.valign === 'center' ? y + (h - dh) / 2 : y;
  const c = g(); c.save(); c.globalAlpha *= o.alpha ?? 1; c.drawImage(im, dx, dy, dw, dh); c.restore();
  return [dw, dh];
}

/* ------------------------------------------------------------------ the map, drawn (world units) */
// how much of each line has been drawn: they race out of the terminus one after another as the legend lists them
const LEGEND_AT = (k) => bt(B.legend + k * Math.min(1, 5 / NT));
const drawn = (k, t) => STOTAL * Math.pow(clamp((t - LEGEND_AT(k) - .1) / 3.4), 1.5);
function polyline(pts, n, col, w) {
  if (n < 2) return;
  const c = g(); c.beginPath(); c.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < n; i++) c.lineTo(pts[i][0], pts[i][1]);
  c.strokeStyle = col; c.lineWidth = w; c.lineCap = 'round'; c.lineJoin = 'round'; c.stroke();
}
function bands(night) { // the ground, and a faint band behind every other day's row (night: 0..1)
  const c = g();
  c.fillStyle = mixHex(C.paper, C.night, night); c.fillRect(-4000, -4000, 12000, 12000);
  for (let r = 1; r < NR; r += 2) {
    c.fillStyle = mixHex(C.paperDk, C.nightBand, night);
    c.fillRect(MAP.x0 - 60, MAP.y0 + ROWH * r, 12000, ROWH);
  }
}
/** an interchange: a white capsule across the pinched bundle at s */
function capsule(s, o = {}) {
  const q = pathAt(s), p = q.p, half = HALF * PINCH + LW * .95, wd = LW * 2.1, c = g();
  const ang = Math.atan2(q.n[1], q.n[0]);
  withT(p[0], p[1], ang, o.k ?? 1, () => {
    if (o.glow) { c.save(); c.shadowColor = o.glow; c.shadowBlur = LW * 3; SK.rrPath(-half, -wd / 2, half * 2, wd, wd / 2); c.fillStyle = o.fill ?? '#FFFFFF'; c.fill(); c.restore(); }
    SK.rrPath(-half, -wd / 2, half * 2, wd, wd / 2); c.fillStyle = o.fill ?? '#FFFFFF'; c.fill();
    c.lineWidth = LW * .42; c.strokeStyle = o.stroke ?? C.ink; c.stroke();
  });
}
function station(s, k, o = {}) { // a highlighted station on line k: a white ring in the line's colour
  const p = at(s, laneOf(k)), c = g(), r = LW * .98 * (o.k ?? 1);
  if (r <= .1) return;
  c.beginPath(); c.arc(p[0], p[1], r, 0, TAU); c.fillStyle = '#FFFFFF'; c.fill();
  c.lineWidth = LW * .46 * (o.k ?? 1); c.strokeStyle = o.stroke ?? TRACKS[k].col; c.stroke();
}
function mapLayer(t, o = {}) {
  const c = g(), night = o.night ?? 0;
  // the lines
  TRACKS.forEach((tr, k) => {
    const n = Math.min(LINES[k].length, Math.floor(drawn(k, t) / STEP) + 1);
    if (night > 0) { c.save(); c.shadowColor = tr.col; c.shadowBlur = LW * 2.2 * night; polyline(LINES[k], n, tr.col, LW); c.restore(); }
    else polyline(LINES[k], n, tr.col, LW);
  });
  // the quiet stations: ticks on the outer lines
  c.save(); c.lineCap = 'butt';
  for (const tk of TICKS) {
    if (drawn(tk.k, t) < tk.s) continue;
    const q = pathAt(tk.s), o2 = laneOf(tk.k) * squeeze(tk.s), out = Math.sign(laneOf(tk.k)) || -1;
    const a = [q.p[0] + q.n[0] * o2, q.p[1] + q.n[1] * o2], b = [a[0] + q.n[0] * out * LW * 1.15, a[1] + q.n[1] * out * LW * 1.15];
    c.strokeStyle = TRACKS[tk.k].col; c.lineWidth = LW * .7; c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke();
  }
  c.restore();
  // the termini
  const reach = Math.min(...TRACKS.map((tr) => drawn(tr.k, t)));
  for (const s of [0, STOTAL]) {
    const k = s > 0 ? (reach < STOTAL ? 0 : 1) : outBack(clamp((t - LEGEND_AT(0)) / .3));
    if (k <= 0) continue;
    const q = pathAt(s), half = (HALF + LW * 1.3) * k, ang = Math.atan2(q.n[1], q.n[0]);
    withT(q.p[0], q.p[1], ang, 1, () => { rrect(-half, -LW * .55, half * 2, LW * 1.1, LW * .3, night > .5 ? C.nightType : C.ink); });
  }
  // the stations: each pops as its line reaches it
  for (const s of RIDE) {
    const k = s.ic ? null : s.k, got = k === null ? Math.max(...TRACKS.map((tr) => drawn(tr.k, t))) : drawn(k, t);
    const pop = outBack(clamp((t - (LEGEND_AT(k ?? 0) + .1 + 3.4 * Math.pow(clamp(s.s / STOTAL), 1 / 1.5))) / .35));
    if (got < s.s || pop <= 0) continue;
    const hot = s.slot && t >= bt(s.slot.arrive) - .05 && t < bt(s.slot.b1) ? 1 : 0;
    const kk = pop * (1 + .25 * hot + .45 * passed(t, s.s));
    if (s.ic) capsule(s.s, { k: kk, glow: night > 0 ? '#FFFFFF' : null });
    else station(s.s, k, { k: kk });
  }
  for (const s of NIGHT) {
    if (reach < s.s) continue;
    const pop = outBack(clamp((t - bt(B.legend) - 3.6) / .35));
    capsule(s.s, { k: pop, fill: night > .2 ? C.led : '#FFFFFF', stroke: night > .2 ? C.accentDk : C.accent, glow: night > .2 ? C.led : null });
  }
}
/** at night a lit car runs along every line, each with a short trail */
function nightLights(t) {
  const c = g(), t0 = bt(B.rideEnd - 3);
  if (t < t0) return;
  TRACKS.forEach((tr, k) => {
    const sp = STOTAL / 5.5, head = ((t - t0) * sp + (k / NT) * STOTAL * .6 + rnd(k + 9) * 300) % STOTAL;
    const pts = LINES[k], i1 = Math.floor(head / STEP), i0 = Math.max(0, i1 - Math.round(LW * 14 / STEP));
    c.save(); c.lineCap = 'round'; c.shadowColor = '#FFFFFF'; c.shadowBlur = LW * 2;
    for (let i = i0 + 1; i <= i1; i++) {
      c.globalAlpha = Math.pow((i - i0) / (i1 - i0 + 1), 2) * .9;
      c.strokeStyle = '#FFFFFF'; c.lineWidth = LW * .5; c.beginPath(); c.moveTo(pts[i - 1][0], pts[i - 1][1]); c.lineTo(pts[i][0], pts[i][1]); c.stroke();
    }
    c.globalAlpha = 1; c.fillStyle = '#FFFFFF'; c.beginPath(); c.arc(pts[i1][0], pts[i1][1], LW * .5, 0, TAU); c.fill();
    c.restore();
  });
}
/* the overview's words: each day's name at the start of its row, and each station's time and short
   name. They are placed once, greedily, so none sits on another or on the lines: a station's label
   goes on its own side, else the other, else a step further out (with a hairline back to it). */
const LS = clamp(SP * 1.15, 15, 26); // their size (world units: the poster's pixels)
let LABELS = null;
function layoutLabels() {
  const boxes = [], out = [], pad = 7, maxW = clamp(SP * 12, 160, 250);
  const hit = (b) => boxes.some((o) => b.x0 < o.x1 + pad && b.x1 > o.x0 - pad && b.y0 < o.y1 + pad && b.y1 > o.y0 - pad);
  // the lines themselves are taken: every straight part's bundle
  for (const g2 of ROWSEG) {
    const xa = Math.min(g2.a[0], g2.b[0]), xb = Math.max(g2.a[0], g2.b[0]);
    boxes.push({ x0: xa - LW * 2, x1: xb + LW * 2, y0: g2.a[1] - HALF - LW, y1: g2.a[1] + HALF + LW });
  }
  for (const g2 of SEG) { // and the bends
    if (g2.type !== 'arc') continue;
    const out = BR + HALF + LW * 2, right = g2.dth > 0;
    boxes.push({ x0: right ? g2.c[0] : g2.c[0] - out, x1: right ? g2.c[0] + out : g2.c[0], y0: g2.c[1] - out, y1: g2.c[1] + out });
  }
  ROWSEG.forEach((g2, r) => {
    if (!ROWS[r].first) return;
    const str = dayLine(ROWS[r].d).toUpperCase(), size = LS * .82, w = measure(str, { size, wt: 800, fam: FONT.wide, ls: 2 });
    const right = g2.dir > 0, x = right ? g2.a[0] - 6 : g2.a[0] + 6 - w, y = g2.a[1] - HALF - LW * 1.6 - LS * .55;
    const box = { x0: x, x1: x + w, y0: y - size, y1: y + size * .25 };
    boxes.push(box); out.push({ day: true, str, x, y, size });
  });
  for (const s of [...RIDE, ...NIGHT]) {
    const p = pathAt(s.s).p, half = HALF + LW * 1.6;
    // a name too long for its place is cut, not shrunk to nothing
    const sz = LS * .95;
    let name = String(s.short || s.title);
    if (measure(name, { size: sz, wt: 700 }) > maxW) { while (name.length > 2 && measure(name + '…', { size: sz, wt: 700 }) > maxW) name = name.slice(0, -1); name = name.replace(/[\s,.:;–-]+$/, '') + '…'; }
    const tw = measure(s.time + '  ', { size: LS * .8, wt: 700, fam: FONT.mono });
    let w = tw + measure(name, { size: sz, wt: 700 });
    let best = null;
    const place = () => { for (const tier of [0, 1]) {
      for (const side of [s.side, -s.side]) {
        const yb = side > 0 ? p[1] + half + LS * (1.0 + tier * 1.3) : p[1] - half - LS * (.35 + tier * 1.3);
        for (const dx of [0, -.32, .32, -.6, .6]) {
          const x0 = clamp(p[0] - w / 2 + dx * w, MAP.x0 - 30, MAP.x1 + 40 - w);
          const box = { x0, x1: x0 + w, y0: yb - LS * .9, y1: yb + LS * .28 };
          if (!hit(box)) { best = { box, x0, yb, side, tier }; break; }
        }
        if (best) break;
      }
      if (best) break;
    } };
    place();
    if (!best) { name = ''; w = tw; place(); } // no room for the name: the time alone
    if (!best) continue; // no room at all: the station stands unlabelled
    boxes.push(best.box);
    out.push({ s, x: best.x0, y: best.yb, tw, name, sz, lead: best.tier > 0 ? [p, best.side] : null });
  }
  return out;
}
function mapLabels(t, a, night) {
  if (a <= 0 || !LABELS) return;
  const col = night ? C.nightType : C.ink, soft = night ? mixHex(C.nightType, C.night, .35) : C.inkSoft;
  SK.alpha(a, () => {
    for (const L of LABELS) {
      if (L.day) { text(L.str, L.x, L.y, { size: L.size, wt: 800, fam: FONT.wide, ls: 2, col: soft }); continue; }
      if (L.lead) { // a hairline from the station out to a label set further away
        const [p, side] = L.lead, c = g(), y1 = L.y + (side > 0 ? -LS * .95 : LS * .35);
        c.save(); c.strokeStyle = soft; c.lineWidth = 1.5; c.beginPath(); c.moveTo(p[0], p[1] + side * (HALF + LW * 1.2)); c.lineTo(p[0], y1); c.stroke(); c.restore();
      }
      text(L.s.time, L.x, L.y, { size: LS * .8, wt: 700, fam: FONT.mono, col: NIGHT.includes(L.s) ? C.accent : soft });
      text(L.name, L.x + L.tw, L.y, { size: L.sz, wt: 700, col });
    }
  });
}
function drawMap(t, cam, o = {}) {
  const c = g();
  c.save();
  c.translate(CX, CY); c.scale(cam[2], cam[2]); c.translate(-cam[0], -cam[1]);
  bands(o.night ?? 0);
  if (o.ghost > 0) SK.alpha(o.ghost, () => LINES.forEach((pts) => polyline(pts, pts.length, C.hair, LW * .22)));
  if (o.column) o.column(c);
  mapLayer(t, o);
  if (o.night >= 1) nightLights(t);
  mapLabels(t, o.labels ?? 0, o.night > .5);
  if (o.cab) drawCab(t);
  if (o.replay && t > REPLAY[0] && t < REPLAY[1] + .3) {
    const s = replayS(t), q = pathAt(s);
    SK.alpha(ease(t, REPLAY[0], REPLAY[0] + .3) * (1 - ease(t, REPLAY[1], REPLAY[1] + .3)), () => drawCab(t, { p: q.p, d: q.d, L: 0, moving: true }));
  }
  c.restore();
}

/* ------------------------------------------------------------------ the cab */
// over the poster it runs the whole network once more, and each highlight lights as it passes
const REPLAY = [bt(B.poster), bt(B.poster + 13)];
const replayS = (t) => STOTAL * E.inOut(clamp((t - REPLAY[0]) / (REPLAY[1] - REPLAY[0])));
const passed = (t, s) => (t > REPLAY[0] && t < REPLAY[1] + .6 ? Math.exp(-Math.pow((replayS(t) - s) / (LW * 5), 2)) : 0);
function drawCab(t, pose) {
  const q = pose || cab(t), c = g();
  const ang = Math.atan2(q.d[1], q.d[0]), len = LW * 4.6, wd = LW * 1.9;
  const col = (() => { // the colour of the line it is on, or the ink between lines
    const near = TRACKS.reduce((b, tr) => (Math.abs(laneOf(tr.k) - q.L) < Math.abs(laneOf(b.k) - q.L) ? tr : b), TRACKS[0]);
    return Math.abs(laneOf(near.k) - q.L) < SP * .3 ? near.col : C.ink;
  })();
  // a pulse round it while it waits
  if (!q.moving && !pose) {
    const ph = ((t * 112 / 60) % 1), r = LW * (1.8 + 2.6 * ph);
    c.save(); c.globalAlpha = .35 * (1 - ph); c.strokeStyle = col; c.lineWidth = LW * .35; c.beginPath(); c.arc(q.p[0], q.p[1], r, 0, TAU); c.stroke(); c.restore();
  }
  withT(q.p[0], q.p[1], ang, 1, () => {
    c.save(); c.shadowColor = `rgba(${C.shadow},.45)`; c.shadowBlur = LW * 1.2; c.shadowOffsetY = LW * .3;
    SK.rrPath(-len / 2, -wd / 2, len, wd, wd * .42); c.fillStyle = '#FFFFFF'; c.fill(); c.restore();
    SK.rrPath(-len / 2 + LW * .22, -wd / 2 + LW * .22, len - LW * .44, wd - LW * .44, wd * .34); c.fillStyle = col; c.fill();
    // the windscreen at the front, and a stripe
    SK.rrPath(len / 2 - LW * 1.3, -wd / 2 + LW * .5, LW * .8, wd - LW, LW * .25); c.fillStyle = 'rgba(255,255,255,.88)'; c.fill();
    c.fillStyle = 'rgba(255,255,255,.55)'; c.fillRect(-len / 2 + LW * .7, -LW * .1, len - LW * 2.4, LW * .2);
  });
}

/* ------------------------------------------------------------------ the poster's left column
   The logo, the name, THE PROGRAMME and the legend open the film; the dates, the place, the address
   and the button join them at the end. */
const COLY = { logo: 92, logoH: 168, name: 0, legend: 0 };
function columnLayout() {
  const L = {};
  L.logoW = COL.w * .62;
  L.nameSize = fit(EVENT.title, COL.w, 88, { wt: 900 });
  L.nameY = COLY.logo + COLY.logoH + 30 + L.nameSize * .78;
  L.fullY = L.nameY + 40;
  L.titleSize = fit(fillIn(CP.title), COL.w, 74, { wt: 900 });
  L.titleY = (EVENT.full ? L.fullY + 22 : L.nameY + 10) + L.titleSize * .9;
  L.legendY = L.titleY + 56;
  L.row = clamp(250 / NT, 34, 50);
  L.infoY = L.legendY + 30 + L.row * NT + 34;
  return L;
}
let CL = null; // laid out at the first frame, once the fonts are in (measuring needs the canvas)
function legendRow(k, y, t, a) { // the line's chip draws, then its name types
  const tr = TRACKS[k], t0 = LEGEND_AT(k), u = ease(t, t0, t0 + .45, E.out), x = COL.x;
  if (u <= 0) return;
  const len = 74;
  polyline([[x, y], [x + len * u, y]], 2, tr.col, Math.min(16, CL.row * .34));
  if (u > .6) { const c = g(); c.beginPath(); c.arc(x + len * .55, y, Math.min(9, CL.row * .19), 0, TAU); c.fillStyle = '#FFFFFF'; c.fill(); c.lineWidth = 4; c.strokeStyle = tr.col; c.stroke(); }
  const v = ease(t, t0 + .15, t0 + .6, E.out), size = Math.min(CL.row * .62, fit(tr.name, COL.w - len - 30, 30, { wt: 800, fam: FONT.wide }));
  clipRect(x + len + 18, y - size, (COL.w - len) * v, size * 1.6, () => text(tr.name, x + len + 22, y + size * .36, { size, wt: 800, fam: FONT.wide, col: C.ink, alpha: a }));
}
function column(t, a, info) {
  if (a <= 0) return;
  SK.alpha(a, () => {
    const c = g();
    // the logo: it grows out of a pop from the first frame
    const lp = outBack(clamp((t + .12) / .55)), [lw] = [COL.w * .62];
    if (lp > 0) withT(COL.x + lw / 2, COLY.logo + COLY.logoH / 2, 0, lp, () => logo(-lw / 2, -COLY.logoH / 2, lw, COLY.logoH, { valign: 'center' }));
    // the name, the full name, the title on its bar
    const n = ease(t, bt(.75), bt(.75) + .45, E.out);
    clipRect(COL.x - 10, CL.nameY - CL.nameSize, COL.w + 40, CL.nameSize * 1.12, () => text(EVENT.title, COL.x, CL.nameY + (1 - n) * CL.nameSize, { size: CL.nameSize, wt: 900, col: C.ground }));
    if (EVENT.full) SK.alpha(ease(t, bt(1.25), bt(1.25) + .4), () => text(EVENT.full.toUpperCase(), COL.x + 2, CL.fullY, { size: fit(EVENT.full.toUpperCase(), COL.w, 22, { wt: 800, fam: FONT.wide, ls: 2 }), wt: 800, fam: FONT.wide, ls: 2, col: C.inkSoft }));
    const tb = ease(t, bt(2), bt(2) + .5, E.out), ttl = fillIn(CP.title);
    if (tb > 0) {
      const tw = measure(ttl, { size: CL.titleSize, wt: 900 });
      rrect(COL.x - 14, CL.titleY - CL.titleSize * .86, (tw + 30) * tb, CL.titleSize * 1.04, 8, C.accent);
      clipRect(COL.x - 14, CL.titleY - CL.titleSize, (tw + 30) * tb, CL.titleSize * 1.3, () => text(ttl, COL.x + 2, CL.titleY, { size: CL.titleSize, wt: 900, col: C.onAccent }));
    }
    // the legend
    SK.alpha(ease(t, bt(3), bt(3) + .4), () => text(fillIn(CP.lines).toUpperCase(), COL.x, CL.legendY, { size: 20, wt: 800, fam: FONT.wide, ls: 5, col: C.inkSoft }));
    TRACKS.forEach((tr, k) => legendRow(k, CL.legendY + 30 + CL.row * (k + .5), t, 1));
    info(c);
  });
}
function posterInfo(t) { // the dates and the place from the open; the button and the address at the end
  return () => {
    const y = CL.infoY, u = (i) => ease(t, bt(9.5 + i), bt(9.5 + i) + .45, E.out);
    const w = COL.w;
    SK.alpha(u(0), () => {
      const s = fit(EVENT.dates.toUpperCase(), w, 40, { wt: 900 });
      text(EVENT.dates.toUpperCase(), COL.x, y + 14 + (1 - u(0)) * 20, { size: s, wt: 900, col: C.ink });
    });
    SK.alpha(u(1), () => {
      const str = [EVENT.venue, [EVENT.city, EVENT.country].filter(Boolean).join(', ')].filter(Boolean).join(' · ');
      text(str, COL.x, y + 52, { size: fit(str, w, 26, { wt: 700, fam: FONT.wide }), wt: 700, fam: FONT.wide, col: C.inkSoft });
    });
    // the button and the address under it
    const b = outBack(clamp((t - bt(B.dawn + 4)) / .5));
    if (b > 0) {
      const bh = 76, by = Math.min(H - 140, y + 90), cta = EVENT.cta;
      const size = fit(cta, w - 120, 34, { wt: 900 }), bw = Math.min(w, measure(cta, { size, wt: 900 }) + 120);
      withT(COL.x + bw / 2, by + bh / 2, 0, b, () => {
        rrect(-bw / 2, -bh / 2 + 6, bw, bh, bh / 2, C.accentDk);
        rrect(-bw / 2, -bh / 2, bw, bh, bh / 2, C.accent);
        text(cta, -bw / 2 + 34, size * .36, { size, wt: 900, col: C.onAccent });
        const ax = bw / 2 - 46 + Math.max(0, Math.sin(t * 6)) * 6, c = g();
        c.strokeStyle = C.onAccent; c.lineWidth = 7; c.lineCap = 'round'; c.lineJoin = 'round';
        c.beginPath(); c.moveTo(ax - 20, 0); c.lineTo(ax + 16, 0); c.moveTo(ax + 1, -15); c.lineTo(ax + 17, 0); c.lineTo(ax + 1, 15); c.stroke();
      });
      SK.alpha(ease(t, bt(B.dawn + 5), bt(B.dawn + 5) + .4), () => text(EVENT.url, COL.x + 4, by + bh + 46, { size: fit(EVENT.url, w, 30, { wt: 700, fam: FONT.mono }), wt: 700, fam: FONT.mono, col: C.ground }));
    }
  };
}

/* ------------------------------------------------------------------ the enamel sign at a stop (screen space) */
const SIGN = { w: 960, band: 66, pad: 36 };
function signLayout(s) {
  const L = { w: s.ic ? 1040 : SIGN.w };
  L.timeSize = 84; L.timeW = Math.max(measure('00:00', { size: L.timeSize, wt: 700, fam: FONT.mono }), measure(s.time, { size: L.timeSize, wt: 700, fam: FONT.mono }));
  if (L.timeW > 300) { L.timeSize *= 300 / L.timeW; L.timeW = 300; }
  L.pic = s.image && SK.IMG[s.image] ? 150 : 0;
  L.textX = SIGN.pad + L.timeW + 46;
  L.textW = L.w - L.textX - SIGN.pad - (L.pic ? L.pic + 20 : 0);
  L.title = fitBlock(s.title, L.textW, 3, s.ic ? 66 : 58, 34, { wt: 800 });
  L.lead = L.title.size * 1.02;
  L.who = [s.speaker, s.org].filter(Boolean);
  L.whoSize = 30;
  const whoStr = s.speaker && s.org ? `${s.speaker} · ${s.org}` : L.who.join('');
  L.whoLines = whoStr ? fitBlock(whoStr, L.textW, 2, 30, 22, { wt: 700, fam: FONT.wide }) : null;
  L.h = SIGN.band + 34 + L.title.lines.length * L.lead + (L.whoLines ? 16 + L.whoLines.lines.length * L.whoLines.size * 1.15 : 0) + (s.room ? 54 : 6) + 30;
  L.h = Math.max(L.h, SIGN.band + 34 + L.timeSize + 70 + 30, L.pic ? SIGN.band + L.pic + 60 : 0);
  return L;
}
function pin(x, y, r, col) { // a map pin
  const c = g(); c.save(); c.translate(x, y); c.fillStyle = col;
  c.beginPath(); c.arc(0, -r * 1.1, r, Math.PI * .85, Math.PI * 2.15); c.lineTo(0, r * .9); c.closePath(); c.fill();
  c.beginPath(); c.arc(0, -r * 1.1, r * .42, 0, TAU); c.fillStyle = C.ground; c.fill(); c.restore();
}
function bullets(x, y, r) { // every line's colour in a row: an interchange
  TRACKS.forEach((tr, k) => { const c = g(); c.beginPath(); c.arc(x + k * r * 2.5, y, r, 0, TAU); c.fillStyle = tr.col; c.fill(); c.lineWidth = 3; c.strokeStyle = '#FFFFFF'; c.stroke(); });
  return TRACKS.length * r * 2.5;
}
function sign(s, sx, sy, t) {
  const it = s.slot, L = s.L, c = g();
  const t0 = bt(it.arrive) - .06, t1 = bt(it.b1) - .2;
  const open = outBackSoft(clamp((t - t0) / .34)), close = E.in(clamp((t - (t1 - .26)) / .26));
  const k = open * (1 - close);
  if (k <= .01) return;
  const w = L.w, h = L.h, gap = (s.ic ? HALF * PINCH : HALF) * camNow[2] + LW * camNow[2] + 46;
  const x = clamp(sx - w / 2, 70, W - 70 - w), y = sy - gap - h;
  const tr = lineOf(s), band = s.ic ? C.ink : tr.col, onBand = onColour(band);
  // it unfolds up from the station
  c.save(); c.translate(0, sy - gap); c.scale(1, k); c.translate(0, -(sy - gap));
  // the post down to the station
  c.fillStyle = C.ink; c.beginPath(); c.moveTo(clamp(sx, x + 40, x + w - 40) - 14, y + h - 2); c.lineTo(clamp(sx, x + 40, x + w - 40) + 14, y + h - 2); c.lineTo(sx, sy - gap + 30); c.closePath(); c.fill();
  c.save(); c.shadowColor = `rgba(${C.shadow},.38)`; c.shadowBlur = 34; c.shadowOffsetY = 16; rrect(x, y, w, h, 24, C.ground); c.restore();
  // enamel: a light rim inset, and a soft gloss over the top
  c.save(); SK.rrPath(x + 9, y + 9, w - 18, h - 18, 17); c.lineWidth = 3.5; c.strokeStyle = 'rgba(255,255,255,.85)'; c.stroke(); c.restore();
  c.save(); SK.rrPath(x + 9, y + 9, w - 18, h - 18, 17); c.clip();
  c.fillStyle = band; c.fillRect(x, y, w, SIGN.band + 9);
  const gl = c.createLinearGradient(x, y, x + w * .5, y + h); gl.addColorStop(0, 'rgba(255,255,255,.13)'); gl.addColorStop(.45, 'rgba(255,255,255,0)');
  c.fillStyle = gl; c.fillRect(x, y, w, h);
  c.restore();
  // the band: the line (or every line), and what kind of session it is
  const by = y + 9 + SIGN.band / 2 + 2, kind = String(KINDS[s.kind] ?? s.kind).toUpperCase();
  const reveal = (a, d = .3) => E.out(clamp((t - t0 - a) / d));
  SK.alpha(reveal(.12), () => {
    let bx = x + SIGN.pad;
    if (s.ic) { bx += bullets(bx + 13, by, 13) + 10; }
    else { c.beginPath(); c.arc(bx + 15, by, 15, 0, TAU); c.fillStyle = onBand; c.fill(); c.beginPath(); c.arc(bx + 15, by, 7, 0, TAU); c.fillStyle = band; c.fill(); bx += 44; }
    const label = s.ic ? fillIn(CP.interchange) : tr.name.toUpperCase();
    const kw = measure(kind, { size: 22, wt: 800, fam: FONT.wide, ls: 3 }) + 34;
    text(label, bx, by + 11, { size: fit(label, w - (bx - x) - kw - 70, 30, { wt: 800, fam: FONT.wide, ls: 3 }), wt: 800, fam: FONT.wide, ls: 3, col: onBand });
    c.save(); SK.rrPath(x + w - SIGN.pad - kw, by - 19, kw, 38, 19); c.lineWidth = 3; c.strokeStyle = onBand; c.stroke(); c.restore();
    text(kind, x + w - SIGN.pad - kw / 2 + 2, by + 8, { size: 22, wt: 800, fam: FONT.wide, ls: 3, col: onBand, align: 'center' });
  });
  // the time, rolled up digit by digit, and the day under it
  const ty = y + 9 + SIGN.band + 34 + L.timeSize * .74;
  clipRect(x + SIGN.pad - 6, ty - L.timeSize * .82, L.timeW + 14, L.timeSize * .98, () => {
    let tx = x + SIGN.pad;
    [...s.time].forEach((ch, i) => {
      const u = E.out(clamp((t - t0 - .14 - i * .05) / .3));
      text(ch, tx, ty + (1 - u) * L.timeSize, { size: L.timeSize, wt: 700, fam: FONT.mono, col: C.light });
      tx += measure(ch, { size: L.timeSize, wt: 700, fam: FONT.mono });
    });
  });
  SK.alpha(reveal(.3), () => text(DAYS[s.d].when.toUpperCase() || DAYS[s.d].name, x + SIGN.pad + 2, ty + 44, { size: 24, wt: 800, fam: FONT.wide, ls: 2, col: C.soft }));
  // the rule between them
  const ry0 = y + 9 + SIGN.band + 30, ry1 = y + h - 34;
  c.fillStyle = 'rgba(255,255,255,.22)'; c.fillRect(x + L.textX - 24, ry0, 3, (ry1 - ry0) * reveal(.1, .4));
  // the title, line by line; who; where
  let yy = y + 9 + SIGN.band + 30;
  L.title.lines.forEach((ln, i) => {
    const u = E.out(clamp((t - t0 - .2 - i * .07) / .38));
    yy += L.lead;
    clipRect(x + L.textX - 4, yy - L.title.size * .95, L.textW + 10, L.title.size * 1.2, () => text(ln, x + L.textX, yy - L.title.size * .12 + (1 - u) * L.title.size, { size: L.title.size, wt: 800, col: C.light }));
  });
  if (L.whoLines) {
    yy += 14;
    L.whoLines.lines.forEach((ln, i) => {
      yy += L.whoLines.size * 1.15;
      const u = reveal(.42 + i * .06, .4);
      clipRect(x + L.textX - 4, yy - L.whoLines.size * 1.1, (L.textW + 10) * u, L.whoLines.size * 1.5, () => {
        // the name in light, the company after it softer
        const nm = s.speaker && ln.startsWith(s.speaker) ? s.speaker : null;
        if (nm) { text(nm, x + L.textX, yy, { size: L.whoLines.size, wt: 700, fam: FONT.wide, col: C.light }); text(ln.slice(nm.length), x + L.textX + measure(nm, { size: L.whoLines.size, wt: 700, fam: FONT.wide }), yy, { size: L.whoLines.size, wt: 600, fam: FONT.wide, col: C.soft }); }
        else text(ln, x + L.textX, yy, { size: L.whoLines.size, wt: 600, fam: FONT.wide, col: i === 0 && s.speaker ? C.light : C.soft });
      });
    });
  }
  if (s.room) {
    const u = outBack(clamp((t - t0 - .55) / .35));
    if (u > 0) {
      const ry = yy + 46, rs = fit(String(s.room).toUpperCase(), L.textW - 50, 26, { wt: 800, fam: FONT.wide, ls: 2 });
      withT(x + L.textX + 12, ry - 9, 0, u, () => pin(0, 0, 11, C.accent));
      SK.alpha(clamp(u), () => text(String(s.room).toUpperCase(), x + L.textX + 34, ry, { size: rs, wt: 800, fam: FONT.wide, ls: 2, col: C.accent }));
    }
  }
  // a keynote's speaker, when the content has their picture: a cut-out in a circle on the right
  if (L.pic) {
    const u = outBack(clamp((t - t0 - .3) / .45)), r = L.pic / 2, px = x + w - SIGN.pad - r, py = y + 9 + SIGN.band + 26 + r;
    if (u > 0) withT(px, py, 0, u, () => {
      c.save(); c.beginPath(); c.arc(0, 0, r, 0, TAU); c.fillStyle = C.accent; c.fill(); c.clip();
      const im = SK.IMG[s.image], sc = 2 * r / .74; c.drawImage(im, -sc / 2, -sc * .47, sc, sc); c.restore();
      c.beginPath(); c.arc(0, 0, r + 2, 0, TAU); c.lineWidth = 5; c.strokeStyle = C.light; c.stroke();
    });
  }
  c.restore();
}

/* ------------------------------------------------------------------ the LED boards (screen space)
   A departure board for each day, and the night board; lit in the accent, each letter a grid of dots. */
let LEDC = null, DOTS = null, DIM = null;
function ledCanvas() {
  if (!LEDC) {
    LEDC = document.createElement('canvas'); LEDC.width = W; LEDC.height = 600;
    const p = document.createElement('canvas'); p.width = p.height = 6; const q = p.getContext('2d');
    q.fillStyle = '#fff'; q.beginPath(); q.arc(3, 3, 2.35, 0, TAU); q.fill(); DOTS = LEDC.getContext('2d').createPattern(p, 'repeat');
    const p2 = document.createElement('canvas'); p2.width = p2.height = 6; const q2 = p2.getContext('2d');
    q2.fillStyle = 'rgba(255,255,255,.07)'; q2.beginPath(); q2.arc(3, 3, 2.2, 0, TAU); q2.fill(); DIM = g().createPattern(p2, 'repeat');
  }
  return LEDC;
}
/** rows: [{str, size, x (from the board's left), y (baseline from its top), col?, n (letters lit so far)}] */
function ledBoard(x, y, w, h, rows, a = 1) {
  if (a <= 0) return;
  const c = g(), lc = ledCanvas(), q = lc.getContext('2d');
  standardCyrillic(q);
  SK.alpha(a, () => {
    c.save(); c.shadowColor = `rgba(${C.shadow},.45)`; c.shadowBlur = 30; c.shadowOffsetY = 14; rrect(x, y, w, h, 18, '#2A2C31'); c.restore();
    rrect(x + 8, y + 8, w - 16, h - 16, 12, '#0A0B0D');
    c.save(); SK.rrPath(x + 8, y + 8, w - 16, h - 16, 12); c.clip(); c.translate(x, y); c.fillStyle = DIM; c.fillRect(0, 0, w, h); c.restore();
    // the lit letters: drawn, then cut into dots, then laid on with a glow
    q.setTransform(1, 0, 0, 1, 0, 0); q.globalCompositeOperation = 'source-over'; q.clearRect(0, 0, lc.width, lc.height);
    SK.drawInto(q, () => {
      for (const r of rows) {
        const str = [...r.str].slice(0, Math.max(0, Math.floor(r.n ?? 1e9))).join('');
        text(str, r.x, r.y, { size: r.size, wt: r.wt ?? 800, fam: r.fam ?? FONT.wide, col: r.col ?? C.led, ls: r.ls ?? 1, align: r.align });
      }
    });
    q.globalCompositeOperation = 'destination-in'; q.fillStyle = DOTS; q.fillRect(0, 0, lc.width, lc.height); q.globalCompositeOperation = 'source-over';
    c.save(); c.shadowColor = C.led; c.shadowBlur = 16; c.drawImage(lc, 0, 0, w, h, x, y, w, h); c.restore();
    c.drawImage(lc, 0, 0, w, h, x, y, w, h);
  });
}
function dayBoard(d, first, t0, t1, t) { // the day and its date; under them the first stop, its time and its line
  const a = ease(t, t0, t0 + .25) * (1 - ease(t, t1 - .25, t1));
  if (a <= 0) return;
  const w = 880, h = 214, x = CX - w / 2, y = 168 + (1 - outBackSoft(clamp((t - t0) / .4))) * -60;
  const lit = (t - t0 - .15) / .028, day = DAYS[d];
  const r2 = [fillIn(CP.first), first ? first.time : ''].filter(Boolean).join('  ') + (first && lineOf(first) ? '   ' + lineOf(first).name.toUpperCase() : '');
  const s1 = fit(day.name.toUpperCase(), 260, 74, { wt: 900, fam: FONT.cond });
  ledBoard(x, y, w, h, [
    { str: day.name.toUpperCase(), size: s1, x: 40, y: 104, fam: FONT.cond, wt: 900, n: lit },
    { str: day.when.toUpperCase(), size: fit(day.when.toUpperCase(), w - 360, 60, { wt: 800, fam: FONT.wide, ls: 2 }), x: w - 40, y: 100, align: 'right', ls: 2, n: lit - 4 },
    { str: r2.toUpperCase(), size: fit(r2.toUpperCase(), w - 80, 34, { wt: 800, fam: FONT.wide, ls: 2 }), x: 40, y: 168, ls: 2, n: lit - 10, col: '#FFFFFF' },
  ], a);
}
function nightBoard(t) { // the evening's stops, or (with none) the days of the event
  const t0 = bt(B.rideEnd - 1), t1 = bt(B.dawn + .5);
  const a = ease(t, t0, t0 + .3) * (1 - ease(t, t1 - .3, t1));
  if (a <= 0) return;
  const rows = NIGHT.length ? NIGHT : DAYS.map((d, i) => ({ time: d.name, title: d.when, room: '', d: i }));
  const w = 600, rh = 118, h = 120 + rows.length * rh, x = 76, y = CY - h / 2 + 30;
  const lit = (t - t0 - .05) / .03, R = [];
  // the times' column: as wide as the widest (9:30 PM is wider than 21:30), within reason
  let ts = 34, tw = Math.max(...rows.map((r) => measure(String(r.time), { size: ts, wt: 700, fam: FONT.mono })), measure('00:00', { size: ts, wt: 700, fam: FONT.mono }));
  if (tw > 190) { ts *= 190 / tw; tw = 190; }
  const head = fillIn(NIGHT.length ? CP.night : CP.title).toUpperCase();
  R.push({ str: head, size: fit(head, w - 80, 46, { wt: 900, fam: FONT.cond, ls: 3 }), x: 40, y: 76, fam: FONT.cond, wt: 900, ls: 3, n: lit });
  rows.forEach((r, i) => {
    const y0 = 120 + i * rh, ttl = String(r.title).toUpperCase(), sub = [NIGHT.length ? DAYS[r.d].when : '', r.room].filter(Boolean).join(' · ').toUpperCase();
    R.push({ str: r.time, size: ts, x: 40, y: y0 + 44, fam: FONT.mono, wt: 700, n: lit - 8 - i * 10, col: '#FFFFFF' });
    const tx = 40 + tw + 26;
    R.push({ str: ttl, size: fit(ttl, w - tx - 40, 40, { wt: 800, fam: FONT.cond, ls: 1 }), x: tx, y: y0 + 44, fam: FONT.cond, wt: 800, n: lit - 10 - i * 10 });
    if (sub) R.push({ str: sub, size: fit(sub, w - tx - 40, 24, { wt: 700, fam: FONT.wide, ls: 2 }), x: tx, y: y0 + 82, wt: 700, ls: 2, n: lit - 14 - i * 10, col: C.nightType });
  });
  ledBoard(x, y, w, h, R, a);
}

/* ------------------------------------------------------------------ the strip map over the ride (screen space)
   Like the line diagram over a carriage's doors: every stop of the ride as a dot, the days marked, the
   cab moving along it. */
function strip(t, a) {
  if (a <= 0 || !RIDE.length) return;
  SK.alpha(a, () => {
    const c = g(), x0 = 1040, x1 = W - 96, y = 92, n = RIDE.length;
    const card = (x, y, w, h) => { c.save(); c.shadowColor = `rgba(${C.shadow},.2)`; c.shadowBlur = 26; c.shadowOffsetY = 8; rrect(x, y, w, h, 20, C.paper); c.restore(); };
    card(x0 - 52, 22, x1 - x0 + 104, 104);
    const xs = RIDE.map((_, i) => lerp(x0, x1, n === 1 ? .5 : i / (n - 1)));
    c.strokeStyle = C.ink; c.lineWidth = 7; c.lineCap = 'round'; c.beginPath(); c.moveTo(x0 - 18, y); c.lineTo(x1 + 18, y); c.stroke();
    // the days, over the strip
    RIDE.forEach((s, i) => {
      if (i && s.d === RIDE[i - 1].d) return;
      text(DAYS[s.d].name.toUpperCase(), xs[i] - 10, y - 26, { size: 19, wt: 800, fam: FONT.wide, ls: 2, col: C.inkSoft });
      if (i) { c.fillStyle = C.paper; c.fillRect((xs[i] + xs[i - 1]) / 2 - 3, y - 8, 6, 16); }
    });
    // where the cab is: between the stops it is between, by arc length
    const q = cab(t);
    let px = x0;
    if (q.s <= RIDE[0].s) px = lerp(x0 - 16, x0, clamp(q.s / Math.max(1, RIDE[0].s)));
    else {
      px = x1;
      for (let i = 1; i < n; i++) if (q.s <= RIDE[i].s) { px = lerp(xs[i - 1], xs[i], (q.s - RIDE[i - 1].s) / Math.max(1, RIDE[i].s - RIDE[i - 1].s)); break; }
      if (q.s > RIDE[n - 1].s) px = lerp(x1, x1 + 16, clamp((q.s - RIDE[n - 1].s) / Math.max(1, STOTAL - RIDE[n - 1].s)));
    }
    RIDE.forEach((s, i) => {
      const past = q.s >= s.s - 1, hot = s.slot && t >= bt(s.slot.arrive) - .05 && t < bt(s.slot.b1);
      const r = (hot ? 14 : 10) * outBack(clamp((t - bt(B.depart + 1.5 + i * 6 / n)) / .3));
      if (r <= .5) return;
      c.beginPath(); c.arc(xs[i], y, r, 0, TAU); c.fillStyle = s.ic ? '#FFFFFF' : past ? lineOf(s).col : '#FFFFFF'; c.fill();
      c.lineWidth = 5; c.strokeStyle = s.ic ? C.ink : lineOf(s).col; c.stroke();
    });
    c.beginPath(); c.arc(px, y, 8, 0, TAU); c.fillStyle = C.accent; c.fill(); c.lineWidth = 3; c.strokeStyle = '#FFFFFF'; c.stroke();
    // the logo, the title and today, on the left
    const ttl = fillIn(CP.title), dd = DAYS[(RIDE.find((s) => s.s >= q.s - 1) || RIDE[n - 1]).d];
    const day = [dd.name, dd.when].filter(Boolean).join(' · ').toUpperCase();
    const im = logoImg(), lw = im ? Math.min(110, 76 * im.width / im.height) : 0, lx = 76 + (lw ? lw + 20 : 0);
    const tw = Math.max(measure(ttl, { size: 36, wt: 900 }), measure(day, { size: 21, wt: 800, fam: FONT.wide, ls: 2 }));
    card(44, 22, lx - 44 + tw + 34, 104);
    logo(70, 36, lw, 76, { valign: 'center' });
    text(ttl, lx, 72, { size: 36, wt: 900, col: C.ground });
    text(day, lx + 2, 104, { size: 21, wt: 800, fam: FONT.wide, ls: 2, col: C.inkSoft });
  });
}

/* ------------------------------------------------------------------ the film */
let camNow = [CX, CY, 1];
function draw(t) {
  const c = g();
  if (!CL) {
    standardCyrillic(c);
    CL = columnLayout(); for (const s of RIDE) s.L = signLayout(s);
    LABELS = layoutLabels();
  }
  const cam = (camNow = camAt(t));
  c.setTransform(1, 0, 0, 1, 0, 0);
  // night falls from the top of the frame as the camera pulls back from the end of the line; the day
  // comes back the same way and brings the poster
  const dusk = lerp(-180, H + 180, ease(t, bt(B.rideEnd - 3), bt(B.rideEnd - .2)));
  const dawn = lerp(-180, H + 180, ease(t, bt(B.dawn - .6), bt(B.dawn + 1.4)));
  const colA = t < bt(B.depart) ? 1 - ease(t, bt(B.dive) + .3, bt(B.dive + 2)) : t > bt(B.dawn - 1) ? 1 : 0;
  const labels = t > bt(END.b0) ? clamp((2.0 - cam[2]) / .7) : 0;
  const ghost = .6 * (1 - ease(t, bt(B.dive), bt(B.depart)));
  const cabOn = t >= bt(B.dive) && t < bt(B.rideEnd + 2);
  drawMap(t, cam, { night: 0, labels, ghost, cab: cabOn, replay: true, column: () => column(t, colA, posterInfo(t)) });
  if (dusk > dawn) { // the night between the two edges
    c.save(); c.beginPath(); c.rect(0, dawn, W, dusk - dawn); c.clip();
    drawMap(t, cam, { night: 1, labels, cab: cabOn });
    c.restore();
    const edge = (y, dir) => { // a soft dusk on the day side of an edge
      const gr = c.createLinearGradient(0, y, 0, y + dir * 160); gr.addColorStop(0, `rgba(${rgbOf(C.night).join(',')},.45)`); gr.addColorStop(1, `rgba(${rgbOf(C.night).join(',')},0)`);
      c.fillStyle = gr; c.fillRect(0, Math.min(y, y + dir * 160), W, 160);
    };
    if (dusk < H + 170) edge(dusk, 1);
    if (dawn > -170) edge(dawn, -1);
  }
  // the boards, the signs and the strip are on the screen, over the map
  const toScreen = (p) => [(p[0] - cam[0]) * cam[2] + CX, (p[1] - cam[1]) * cam[2] + CY];
  if (RIDE.length) dayBoard(RIDE[0].d, RIDE[0], bt(B.depart) + .1, bt(B.ride) + .35, t);
  for (const it of SCHED) if (it.type === 'change') dayBoard(it.to.d, it.to, bt(it.b0 + 3), bt(it.b1) + .3, t);
  for (const s of RIDE) if (t >= bt(s.slot.arrive) - .1 && t < bt(s.slot.b1)) { const p = toScreen(stopXY(s)); sign(s, p[0], p[1], t); }
  strip(t, ease(t, bt(B.depart), bt(B.depart + 1.5)) * (1 - ease(t, bt(END.b0 + 1), bt(END.b0 + 2.5))));
  nightBoard(t);
}

/* ------------------------------------------------------------------ the sound
   Worked out from the clock above and from the content, so another programme brings its own chimes,
   clacks and board blips: `sketch-render.py --sound-data` writes score.json and sfx.json from these.
   The music is a 112 bpm groove in D from a chord chart: the logo and the legend over keys and a pad,
   a roll into the dive, a half-time bar under the first board, the full groove as the cab leaves, a
   chime on every arrival (a bigger one at an interchange), a fill and a hit at each change of day, the
   groove thinning out for the night and landing again for the poster, a last chord on beat 160. */
const gf = (x) => String(+x.toPrecision(6)); // a number as Python's %g writes it
function scoreData() {
  const CHART = [ // per bar: bass root, its octave, the keys' chord, the pad's chord, the arpeggio
    ['D2', 'D3', 'F#3+A3+C#4+E4', 'D3+F#3+A3+C#4', 'D5 A5 F#5 A5'], // Dmaj9
    ['B1', 'B2', 'D3+F#3+A3+C#4', 'B2+D3+F#3+A3', 'B4 F#5 D5 F#5'], // Bm9
    ['G1', 'G2', 'B3+D4+F#4+A4', 'G2+B2+D3+F#3', 'G4 D5 B4 D5'], // Gmaj7
    ['A1', 'A2', 'C#4+E4+G4+B4', 'A2+C#3+E3+G3', 'A4 E5 C#5 E5'], // A9
  ];
  const BARS = 42, bar = (b) => Math.floor(b / 4), chord = (b) => CHART[bar(b) % 4];
  const NIGHT_BARS = [B.rideEnd / 4, Math.floor(B.dawn / 4)]; // bars 34-36: the night
  const isNight = (br) => br >= NIGHT_BARS[0] && br < NIGHT_BARS[1];
  const changeBars = new Set(SCHED.filter((it) => it.type === 'change').map((it) => bar(it.b0 + 3) - 1));
  const rideBar = (br) => br >= B.ride / 4 && br < NIGHT_BARS[0];
  const bass = [], sub = [], keys = [], pad = [], chimes = [], brass = [], pluck = [], arp = [];
  for (let br = 0; br < BARS - 2; br++) {
    const [root, octv, ch, pd, ar] = CHART[br % 4], b0 = br * 4, night = isNight(br);
    if (br >= 1) for (let k = 0; k < 8; k++) { // eighths: the root, its octave on the off-beats
      if (br < 4 && k % 2) continue; // the open: quarter notes
      if (night && k % 4) continue; // the night: half notes
      if (br === 5 && k >= 4) continue; // a gap before the cab leaves
      bass.push(`${gf(b0 + k * .5)} ${k % 2 ? octv : root} ${night ? 1.6 : .42} ${(k % 2 ? .5 : .6).toFixed(2)}`);
      if (k % 2 === 0) sub.push(`${gf(b0 + k * .5)} ${root} ${night ? 1.8 : .45} .7`);
    }
    // the keys: a chord a bar in the open and the night, stabs on the off-beats from the ride on
    if (br < 6 || night) keys.push(`${gf(b0)} ${ch} ${night ? 3.5 : 3} .32`);
    else for (const k of [.5, 1.5, 2.5, 3.5]) keys.push(`${gf(b0 + k)} ${ch} .3 ${(k === 1.5 || k === 3.5 ? .34 : .26).toFixed(2)}`);
    pad.push(`${gf(b0)} ${pd} 4 ${night ? .42 : br < 6 ? .38 : .3}`);
    // the second half of the ride and the poster: a marimba running sixteenths, like rails
    if ((br >= 14 && rideBar(br) && !changeBars.has(br)) || br >= NIGHT_BARS[1] + 1) {
      ar.split(' ').forEach((n, i) => { for (let r = 0; r < 4; r++) arp.push(`${gf(b0 + r + i * .25)} ${n} .22 ${(i === 0 ? .42 : .3).toFixed(2)}`); });
    }
  }
  // the legend: a plucked note up the chord for every line as it draws; the logo's three notes
  const up = ['D5', 'F#5', 'A5', 'C#6', 'E6', 'F#6'];
  TRACKS.forEach((tr, k) => pluck.push(`${gf(LEGEND_AT(k) / BEAT)} ${up[k]} .9 .5`));
  pluck.push(`${gf(0)} A5 .8 .4; ${gf(.5)} D6 .8 .45; ${gf(1)} F#6 1.2 .5`);
  // a station chime on every arrival: three falling notes; an interchange gets the brass under it
  for (const it of SCHED) {
    if (it.type === 'stop') {
      const b = it.arrive;
      chimes.push(`${gf(b)} A5 .5 .5; ${gf(b + .25)} F#5 .5 .45; ${gf(b + .5)} D5 1 .45`);
      if (it.stop.ic) brass.push(`${gf(b)} ${chord(b)[2]} 1.4 .62`);
    } else if (it.type === 'change') brass.push(`${gf(it.b0 + 3)} ${chord(it.b0 + 3)[2]} 1.6 .66`);
  }
  brass.push(`${gf(B.depart)} ${chord(B.depart)[2]} 1.4 .55`); // the terminus
  brass.push(`${gf(B.dawn + .5)} ${chord(B.dawn)[2]} 1.5 .6`); // the dawn
  const FIN = B.last; // the last chord
  bass.push(`${gf(FIN)} D2 4 .7`); sub.push(`${gf(FIN)} D2 4 .9`);
  pad.push(`${gf(FIN)} D3+F#3+A3+C#4+E4 6 .5`); keys.push(`${gf(FIN)} D4+F#4+A4+C#5 4 .45`);
  brass.push(`${gf(FIN)} F#4+A4+D5 2.5 .7`); chimes.push(`${gf(FIN)} A5 .5 .45; ${gf(FIN + .25)} F#5 .5 .45; ${gf(FIN + .5)} D6 2 .5`);
  // the drums, 16 steps a bar. x hit, X accent, o soft, . rest; the rim is the rails' clack
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', hat: 'o.o.o.o.o.o.o.o.', openhat: '..x...x...x...x.', shaker: '.o.o.o.o.o.o.o.o', rim: 'x.x.....x.x.....' };
  const LIGHT = { kick: 'x...x...x...x...', clap: '....x.......x...', hat: 'o.o.o.o.o.o.o.o.', rim: 'x.x.....x.x.....' }; // the first half of the ride
  const events = [
    { inst: 'synth_bass_1', vel: .88, notes: bass.join('; '), humanize: false },
    { inst: 'sub_bass', vel: 1.0, notes: sub.join('; '), humanize: false },
    { inst: 'electric_piano_1', vel: .8, notes: keys.join('; ') },
    { inst: 'pad_3_polysynth', vel: .6, notes: pad.join('; ') },
    { inst: 'vibraphone', vel: .75, notes: chimes.join('; ') },
    { inst: 'synth_brass_1', vel: .8, notes: brass.join('; ') },
    { inst: 'marimba', vel: .7, notes: pluck.join('; ') },
  ];
  if (arp.length) events.push({ inst: 'marimba', vel: .5, notes: arp.join('; '), humanize: false });
  for (let br = 0; br < BARS - 2; br++) {
    let kit;
    if (br === 0) kit = { kick: 'X...............', hat: '..o...o...o...o.', shaker: 'o.o.o.o.o.o.o.o.' };
    else if (br === 1) kit = { kick: 'x.......x.......', hat: '..o...o...o...o.', shaker: 'o.o.o.o.o.o.o.o.' };
    else if (br === 2) kit = { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
    else if (br === 3) kit = { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.', snare: '........oooxxxXX' }; // into the dive
    else if (br === 4) kit = { kick: 'X.......x.......', clap: '........x.......', hat: 'o...o...o...o...' }; // the first board: half time
    else if (br === 5) kit = { kick: 'x.......x.......', clap: '........x.......', rim: 'x.x.....x.x.....', snare: '........ooxxxxXX' }; // the cab gets ready
    else if (isNight(br)) kit = { kick: 'x.........x.....', rim: 'x.x.....x.x.....', hat: '....o.......o...' }; // the night
    else if (br === NIGHT_BARS[1]) kit = { kick: 'x...x...x...x...', hat: 'o.o.o.o.o.o.o.o.', snare: '........ooxxxXX.' }; // into the dawn
    else if (changeBars.has(br)) kit = { ...GROOVE, snare: '............oxxX' }; // a fill into the bend
    else kit = br < 14 ? LIGHT : GROOVE;
    if (br === 6) kit = { ...kit, kick: 'X...x...x...x...' };
    events.push({ type: 'drums', from: br * 4, bars: 1, steps: 16, vel: .85, kit, gains: { kick: 1.1, snare: .4, clap: .42, hat: .24, openhat: .14, shaker: .18, rim: .34 } });
  }
  events.push({ type: 'drums', from: FIN, bars: 1, steps: 16, vel: .9, kit: { kick: 'X...............', openhat: 'x...............' } });
  return {
    bpm: BPM, drum_gain: .6,
    instruments: {
      synth_bass_1: { g: .6, pan: 0, send: .04, rel: .12 },
      sub_bass: { g: .48, pan: 0, send: 0, rel: .06 },
      electric_piano_1: { g: .24, pan: -.22, send: .32, rel: .3 },
      pad_3_polysynth: { g: .16, pan: 0, send: .5, rel: .9, soft_attack: true },
      vibraphone: { g: .3, pan: .18, send: .45, rel: 1.2 },
      synth_brass_1: { g: .2, pan: .12, send: .35, rel: .35 },
      marimba: { g: .26, pan: .3, send: .3, rel: .5 },
    },
    events,
  };
}
function sfxData() {
  const cues = [], r = (x, n) => +x.toFixed(n);
  const add = (t, fx, db, args = {}, o = {}) => {
    const c = { t: r(t, 3), fx, db };
    if (o.pan) c.pan = r(o.pan, 2);
    if (o.send !== undefined) c.send = o.send;
    if (fx === 'sample') Object.assign(c, args); else if (Object.keys(args).length) c.args = args;
    cues.push(c); return c;
  };
  const many = new Map(); // one cue holds every time a sound repeats at one level and pan
  const again = (key, t, fx, db, args, pan) => {
    let c = many.get(key);
    if (!c) { c = add(t, fx, db, args, { pan }); c.times = []; many.set(key, c); }
    c.times.push(r(t, 3));
  };
  const impact = (t, db = -13) => { add(t, 'boom', db, { sec: 1.0 }); add(t, 'crash', db - 15, { sec: 1.8 }, { send: .3 }); };
  // 1. the logo, the name, the title, the legend; the lines racing out
  add(0, 'boom', -16, { sec: .8 });
  add(.02, 'pop', -20, { f0: 640, f1: 200, sec: .09 });
  add(bt(1), 'swoosh_soft', -24, { sec: .4 });
  add(bt(3), 'zip', -22, { sec: .3, f0: 500, f1: 2600 });
  add(bt(5), 'tick', -26);
  TRACKS.forEach((tr, k) => {
    again('legend-zip', LEGEND_AT(k), 'zip', -24, { sec: .22, f0: 700, f1: 3200 }, -.3);
    again('legend-pop', LEGEND_AT(k) + .3, 'pop', -26, { f0: 900, f1: 320, sec: .06 }, -.3);
    add(LEGEND_AT(k) + .15, 'whoosh', -26 - k, { sec: 1.2, f0: 300, f1: 2200, peak: .4 }, { pan: .4 });
  });
  // 2. the dive to the terminus, the first board
  add(bt(B.dive) - .1, 'whoosh', -15, { sec: bt(3) + .2, f0: 250, f1: 4200, peak: .85, curve: 1.5 });
  impact(bt(B.depart), -15);
  const blips = (t0, n, key) => { for (let i = 0; i < n; i++) again(key, t0 + i * .056, 'click', -27, { sec: .006, lo: 2000, hi: 7000 }, -.1 + (i % 5) * .05); };
  blips(bt(B.depart) + .25, 14, 'board-0');
  // 3. the ride
  for (const it of SCHED) {
    const t0 = bt(it.b0);
    if (it.type === 'stop') {
      const ta = bt(it.arrive);
      again('depart', t0, 'swoosh_soft', -21, { sec: .5 }, 0);
      for (let k = 0; k < 4; k++) again('clack', t0 + .18 + k * .2, 'click', -24 - (k % 2) * 2, { sec: .01, lo: 900, hi: 3200 }, 0); // the rails
      again('brake', ta - .3, 'whoosh', -22, { sec: .4, f0: 2400, f1: 500, peak: .2 }, 0);
      again('sign', ta + .02, 'thunk', -18, { sec: .28 }, 0);
      again('sign-pop', ta + .05, 'pop', -24, { f0: 520, f1: 190, sec: .08 }, 0);
      again('time', ta + .16, 'keys', -31, { sec: .3, rate: 20 }, -.2);
      again('room', ta + .58, 'blip', -29, { f: 1175, sec: .08 }, .2);
      if (it.stop.ic) { impact(ta, -16); add(ta, 'shimmer', -26, { sec: 1.2, f0: 600, f1: 5000 }); }
    } else if (it.type === 'change') {
      add(t0 + .1, 'whoosh', -14, { sec: bt(5.5), f0: 220, f1: 3600, peak: .7, curve: 1.3 });
      for (let k = 0; k < 8; k++) again('clack', t0 + .2 + k * .2, 'click', -24 - (k % 2) * 2, { sec: .01, lo: 900, hi: 3200 }, 0);
      impact(bt(it.b0 + 3), -15);
      blips(bt(it.b0 + 3) + .2, 14, 'board-n');
      again('arrive-day', bt(it.b0 + 5.5), 'thunk', -20, { sec: .3 }, 0);
    } else {
      add(t0, 'whoosh', -15, { sec: 2.4, f0: 200, f1: 3000, peak: .8, curve: 1.2 });
      add(t0 + 1.4, 'thunk', -18, { sec: .4 }); // the buffer stop
    }
  }
  // 4. the night: it falls, the board lights row by row
  add(bt(B.rideEnd - 3), 'shimmer', -24, { sec: 2.5, f0: 300, f1: 2400 });
  impact(bt(B.rideEnd), -17);
  blips(bt(B.rideEnd - 1) + .2, 18, 'board-night');
  add(bt(B.rideEnd + 1), 'sample', -18, { inst: 'vibraphone', notes: ['D5', 'A5', 'F#5'], every: .27, sec: 1.4 }, { send: .45 });
  // 5. the dawn and the poster
  add(bt(B.dawn - .5), 'whoosh', -17, { sec: 1.2, f0: 300, f1: 4200, peak: .8 });
  impact(bt(B.dawn + .5), -14);
  for (let i = 0; i < 3; i++) add(bt(B.dawn + 1.5 + i), 'tick', -25, {}, { pan: -.5 });
  add(bt(B.dawn + 4), 'pop', -17, { f0: 520, f1: 170, sec: .12 }, { pan: -.4 }); // the button
  add(bt(B.dawn + 4) + .03, 'blip', -25, { f: 988, sec: .1 }, { pan: -.4 });
  add(bt(B.dawn + 5), 'keys', -29, { sec: .4, rate: 22 }, { pan: -.4 }); // the address
  add(bt(B.last), 'crash', -20, { sec: 2.6 }, { send: .4 });
  return cues.sort((a, b) => a.t - b.t);
}

SK.film({
  duration: DURATION,
  camera: SK.camera([[0, [W / 2, H / 2, 1]]]),
  handheld: false,
  speedLines: false,
  fadeOut: 0,
  draw,
  sound: { score: scoreData, sfx: sfxData },
});
