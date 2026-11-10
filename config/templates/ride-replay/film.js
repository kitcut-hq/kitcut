// For: an event's riders, runners or hikers and the people who might join them -- a ride on its real route
/* Ride replay: a group ride (or run, or hike) invited in 45 s of collage, its heart a replay of the real
   route on the real map, the way a cycling app replays a ride. Music only. This film is a template:
   every word, colour and picture is in content.json (SK.DATA.content) and the route and its map are
   in route.json (SK.DATA.route, written by the route tool), so another ride is another content.json,
   another route and its pictures.

   The story, on a 120 bpm clock (a bar is 2 s), every time in T below:
     0-7.3    the hook: the day and the time slam in over the place it starts, the event's mark taped on,
              its name, and a stamp when it is back again
     7.3-11   who it is for: a photograph of the route, the lead line and three words, the host's card,
              riders rolling through
     11-31    the replay: the paper map, the line growing behind the dot by the route's own clock (fast
              to the climb, slow up it, a breath at the top, fast home), the panel's numbers and
              profile, labels taped to their places, a stamp at the top, then the whole route as the
              finish card with its three numbers
     31-36    what to bring, pasted in like a packing list
     36-45    the last screen, held still: name, date, place, host, the call to act and its QR code
   The captions (content.lines) read in the slots a narration would have had. */
SK.setStyle('collage');
const C = SK.DATA.content, R = SK.DATA.route;
const P0 = C.palette || {};
const INK = P0.ink || '#1b2430', CREAM = P0.cream || '#f7f1e3', SKY = P0.sky || '#bfe0ef', SEA = P0.sea || '#2f74a8',
  SAND = P0.sand || '#ead8b4', SAGE = P0.sage || '#c3d0ac', SUN = P0.sun || '#f6c445', OR = P0.route || '#FC5200',
  GO = P0.go || '#2e9b57', SOFT = P0.soft || '#6b7380', RED = P0.red || '#b8322a', BLUE = P0.blue || '#1f4e8c',
  TABLE = P0.table || '#d9cba9';
SK.setGround('paper', { paper: P0.paper || '#e6d7b8', text: INK, textSoft: '#5b6573', accent: OR, accentText: '#c43f00' });
const { clamp, lerp, E, TAU } = SK;
const DUR = 45, HEAD = 'Anton';
// the type the panel, captions and small words are set in: Inter, or Sofia Sans when the words need
// Cyrillic or Greek letters (Inter here carries Latin only; Anton carries both)
const UI = /[Ͱ-ϿЀ-ӿ]/.test(JSON.stringify(C)) ? 'Sofia Sans' : 'Inter';

/* ---------------------------------------------------------------- the clock (seconds) */
const T = {
  sunday: .7, eight: 1.92, santa: 3.06, pedal: 4.67, back: 6.41, l2: 7.62, ride: 8.16, founders: 8.74, builders: 9.88,
  vcs: 10.44, l3: 11.54, sullivan: 13.04, dirt: 21.07, mul: 21.41, take: 21.98, then: 24.06, pier7: 25.86,
  miles: 26.64, milesE: 28.06, about: 29.18, l9: 31.13, jersey: 31.43, bibs: 32.29, gels: 33.73, bars: 34.65,
  bottles: 35.57, l10: 36.64,
};
const SLOTS = [.5, 4.59, 7.62, 11.54, 14.69, 16.95, 21.05, 24.06, 26.64, 31.13, 36.64]; // the captions' starts

/* ---------------------------------------------------------------- the route, as the route tool wrote it */
const RIDE = R.rows, N = RIDE.length, MW = R.w, MH = R.h; // map units: the map picture's own pixels
const RX = RIDE.map((r) => r[0] * MW), RY = RIDE.map((r) => r[1] * MH);
const GAIN = [0];
for (let i = 1; i < N; i++) GAIN.push(GAIN[i - 1] + Math.max(0, RIDE[i][2] - RIDE[i - 1][2]));
const STATS = R.stats, UNIT = { ...R.units, ...((C.map || {}).units || {}) }, MARK = R.marks; // units as the content writes them ('км')
const GK = GAIN[N - 1] > 0 ? STATS.gain / GAIN[N - 1] : 1, MI_END = RIDE[N - 1][3], CLK_END = Math.max(1, RIDE[N - 1][4]);
const merc = (lat) => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
function uvOf(lab) { // a label's place in map pixels: u/v, a [lat, lon], a row, or a mark
  if (lab.u != null) return [lab.u * MW, lab.v * MH];
  if (lab.lat != null) {
    const [w, s, e, n] = R.bounds;
    return [(lab.lon - w) / (e - w) * MW, (merc(n) - merc(lab.lat)) / (merc(n) - merc(s)) * MH];
  }
  const i = clamp(lab.row ?? MARK[lab.mark || 'top'] ?? 0, 0, N - 1);
  return [RX[i], RY[i]];
}
function rideAt(c) { // the dot and its numbers at route clock c, straight between rows
  if (c <= 0) return { i: 0, x: RX[0], y: RY[0], ele: RIDE[0][2], mi: 0, gain: 0 };
  if (c >= CLK_END) return { i: N - 1, x: RX[N - 1], y: RY[N - 1], ele: RIDE[N - 1][2], mi: MI_END, gain: STATS.gain };
  let lo = 0, hi = N - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (RIDE[m][4] <= c) lo = m; else hi = m; }
  const a = RIDE[lo], b = RIDE[hi], f = b[4] > a[4] ? (c - a[4]) / (b[4] - a[4]) : 1;
  return { i: lo, x: lerp(RX[lo], RX[hi], f), y: lerp(RY[lo], RY[hi], f), ele: lerp(a[2], b[2], f), mi: lerp(a[3], b[3], f), gain: lerp(GAIN[lo], GAIN[hi], f) * GK };
}
// the replay clock: to the climb fast, the climb slow, a breath at the top, home fast. A route with no climb
// to speak of (under 60 m / 200 ft) runs straight through at one speed.
const R0 = T.l3 + .3, RG = T.sullivan + 1.0, RT = T.mul, RD = T.then, RF = T.pier7 + .15;
const CLIMB_C = RIDE[MARK.climb][4], TOP_C = RIDE[MARK.top][4];
const climbs = STATS.climb_gain >= (R.units.ele === 'ft' ? 200 : 60) && MARK.top > MARK.climb;
const CRAWL = Math.min(CLK_END, TOP_C + .025 * CLK_END); // at the top the dot creeps on: a breath, not a stop
const CLK = climbs ? [[R0, 0], [RG, CLIMB_C], [RT, TOP_C], [RD, CRAWL], [RF, CLK_END]] : [[R0, 0], [RF, CLK_END]];
const clockAt = (t) => SK.kf(t, CLK, E.lin);
// the camera: zoom from the route's own size (what the frame shows, as a share of the route), never so far
// out that the frame shows past the map, never past 1.25x the map's pixels
let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
for (let i = 0; i < N; i++) { x0 = Math.min(x0, RX[i]); x1 = Math.max(x1, RX[i]); y0 = Math.min(y0, RY[i]); y1 = Math.max(y1, RY[i]); }
const SPAN = Math.max(x1 - x0, (y1 - y0) * 1.2, 1600 / R.m_per_px), ZMIN = Math.max(1920 / MW, 1080 / MH) * 1.03;
const zFor = (share) => clamp(1920 / (share * SPAN), ZMIN, 1.25);
const ZK = [[R0 - .8, zFor(.68)], [RG - .4, zFor(.62)], [RG + 1.2, zFor(.48)], [RT - .8, zFor(.48)], [RT + .2, zFor(.4)], [RD - .2, zFor(.4)], [RD + .9, zFor(.62)], [RF, zFor(.62)]];
const FIN0 = RF - .3, FIN1 = RF + 1.4;
const FC = { x: MW / 2, y: MH / 2, z: Math.min(1060 / MH, 680 / MW), sx: -60, sy: -30 }; // the whole map, as a card
function mapCam(t) { // follows the dot from a little ahead (a window average: smooth, a pure function of t), the frame always full of map
  const z = SK.kf(t, ZK), sx = -200, sy = -20;
  let x = 0, y = 0;
  for (let k = 0; k <= 10; k++) { const p = rideAt(clockAt(t + .12 + (k / 10 - .5) * .8)); x += p.x / 11; y += p.y / 11; }
  x = clamp(x, (960 + sx) / z, MW - (960 - sx) / z); y = clamp(y, (540 + sy) / z, MH - (540 - sy) / z);
  const w = E.inOut(clamp((t - FIN0) / (FIN1 - FIN0)));
  return { x: lerp(x, FC.x, w), y: lerp(y, FC.y, w), z: Math.exp(lerp(Math.log(z), Math.log(FC.z), w)), sx: lerp(sx, FC.sx, w), sy: lerp(sy, FC.sy, w), w };
}

/* ---------------------------------------------------------------- shared pieces */
const TP = { font: HEAD, wt: 400, ls: 2, ends: 'torn', tex: .8, distress: .15 };
const MEASURE = document.createElement('canvas').getContext('2d');
function fit(s, size, maxW, font = HEAD, wt = 400) { // the size s fits maxW px at, never above size
  MEASURE.font = `${wt} ${size}px "${font}"`;
  const w = Math.max(...String(s).split('\n').map((ln) => MEASURE.measureText(ln).width + ln.length * 2));
  return w > maxW ? Math.floor(size * maxW / w) : size;
}
const tape = (s, x, y, o) => s && SK.tape(s, x, y, { ...TP, ...o, size: o.max ? fit(s, o.size, o.max, o.font || HEAD) : o.size });
function twoLines(s) { // a name on two lines, split where the longer line is shortest (a \n the content gives wins)
  if (s.includes('\n') || !s.includes(' ')) return s;
  const words = s.split(' ');
  let best = s, worst = Infinity;
  for (let k = 1; k < words.length; k++) {
    const a = words.slice(0, k).join(' '), b = words.slice(k).join(' '), w = Math.max(a.length, b.length);
    if (w < worst) { worst = w; best = a + '\n' + b; }
  }
  return best;
}
function text(s, x, y, o = {}) {
  const c = SK.ctx(); c.save(); c.font = `${o.wt ?? 600} ${o.size ?? 24}px "${o.font ?? UI}"`; c.letterSpacing = (o.ls ?? 0) + 'px';
  c.fillStyle = o.col ?? INK; c.textAlign = o.align ?? 'center'; c.textBaseline = o.base ?? 'middle'; c.fillText(s, x, y); c.restore();
}
function tnum(s, x, y, size, col = INK) { // tabular figures: every digit in a cell of one width, so nothing jitters
  const c = SK.ctx(); c.save(); c.font = `800 ${size}px "${UI}"`; c.fillStyle = col; c.textAlign = 'center'; c.textBaseline = 'alphabetic';
  let cx = x;
  for (const ch of s) { const w = /\d/.test(ch) ? size * .66 : size * .3; c.fillText(ch, cx + w / 2, y); cx += w; }
  c.restore(); return cx - x;
}
const LOCALE = C.lang || 'en-US';
const fmt = (n) => Math.round(n).toLocaleString(LOCALE);
const page = (col, seed) => SK.sheet(0, 0, 2010, 1130, { col, edges: 'lr', amp: 9, rim: 7, seed, tex: 1.2, shadow: { blur: 30, x: -6, y: 0, col: 'rgba(40,25,10,.3)' } });
const aspect = (name) => { const im = SK.IMG[name]; return im && im.width ? im.height / im.width : 1; };
function framed(name, x, y, w, o) { // a print or a mark on white card, pasted on; its height from its own shape
  if (!name || !SK.IMG[name]) return;
  const h = Math.round(w * aspect(name));
  SK.layer({ x, y, nudge: 1, w: w + 24, h: h + 24, ...o }, () => {
    SK.sheet(0, 0, w + 24, h + 24, { col: '#fbf9f3', edges: '', tex: .3, shadow: { blur: 14, y: 6 }, seed: 31 });
    SK.image(name, 0, 0, w);
  });
}
const card = (x, y, w, h) => SK.card(x, y, w, h, { r: 22, fill: '#ffffff', shadow: { blur: 30, y: 12, col: 'rgba(30,20,10,.25)' } });
function hosted(x, y, w, rot, o = {}) { // "Hosted by": the host's own logo on a white card
  const H = C.host;
  if (!H || !H.logo || !SK.IMG[H.logo]) return;
  const lw = Math.min(w - 80, 70 / aspect(H.logo));
  SK.layer({ x, y, rot, nudge: 1, w, h: 150, ...o }, () => {
    SK.sheet(0, 0, w, 150, { col: '#ffffff', edges: '', tex: .2, shadow: { blur: 10, y: 4 }, seed: 9 });
    text(H.label || 'HOSTED BY', 0, -50, { size: 17, ls: 4, col: SOFT });
    SK.image(H.logo, 0, 2, lw);
    if (H.name) text(H.name, 0, 52, { size: 18, wt: 600, col: SOFT });
  });
}
const STYLE = { cream: { col: CREAM, ink: INK }, sun: { col: SUN, ink: INK }, water: { col: '#e3f0f7', ink: BLUE, size: 34 } };
const WHEN = { start: R0 - .5, climb: T.sullivan, top: T.dirt - .2, finish: RF - .5 };

/* ---------------------------------------------------------------- the replay: map, route, dot, stats */
function replay(t) {
  const c = SK.ctx(), cam = mapCam(t), P = (mx, my) => [cam.sx + (mx - cam.x) * cam.z, cam.sy + (my - cam.y) * cam.z];
  const [ax, ay] = P(0, 0), bw = MW * cam.z, bh = MH * cam.z;
  c.save(); // the map: one sheet of paper, one camera
  c.shadowColor = 'rgba(40,25,10,.35)'; c.shadowBlur = 26; c.shadowOffsetY = 8;
  c.fillStyle = '#fbf8f0'; c.fillRect(ax - 14, ay - 14, bw + 28, bh + 28);
  c.shadowColor = 'transparent'; c.imageSmoothingQuality = 'high';
  if (SK.IMG[R.image]) c.drawImage(SK.IMG[R.image], ax, ay, bw, bh);
  c.restore();
  const clk = clockAt(t), r = rideAt(clk), pts = RX.map((x, i) => P(x, RY[i])), head = P(r.x, r.y);
  c.save(); c.lineJoin = 'round'; c.lineCap = 'round';
  c.setLineDash([11, 8]); c.strokeStyle = 'rgba(252,82,0,.5)'; c.lineWidth = 3.5; // the way ahead, faint
  c.beginPath(); pts.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.stroke(); c.setLineDash([]);
  const done = () => { c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i <= r.i; i++) c.lineTo(pts[i][0], pts[i][1]); c.lineTo(head[0], head[1]); };
  if (clk > 0) { c.strokeStyle = '#fff'; c.lineWidth = 11; done(); c.stroke(); c.strokeStyle = OR; c.lineWidth = 7; done(); c.stroke(); }
  const pin = ([px, py], col) => { // a map pin, its point on the place
    c.shadowColor = 'rgba(0,0,0,.3)'; c.shadowBlur = 6; c.shadowOffsetY = 2; c.fillStyle = col;
    c.beginPath(); c.moveTo(px, py); c.bezierCurveTo(px - 5, py - 12, px - 19, py - 24, px - 19, py - 40); c.arc(px, py - 40, 19, Math.PI, 0); c.bezierCurveTo(px + 19, py - 24, px + 5, py - 12, px, py); c.fill();
    c.shadowColor = 'transparent'; c.fillStyle = '#fff'; c.beginPath(); c.arc(px, py - 40, 7, 0, TAU); c.fill();
  };
  if (!R.loop) pin(pts[N - 1], INK);
  pin(pts[0], GO);
  const ph = (t * 1.1) % 1; // the dot: white ring, orange core, a soft pulse
  c.fillStyle = `rgba(252,82,0,${.35 * (1 - ph)})`; c.beginPath(); c.arc(head[0], head[1], 14 + 24 * ph, 0, TAU); c.fill();
  c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 8; c.shadowOffsetY = 2; c.fillStyle = '#fff'; c.beginPath(); c.arc(head[0], head[1], 13, 0, TAU); c.fill();
  c.shadowColor = 'transparent'; c.fillStyle = OR; c.beginPath(); c.arc(head[0], head[1], 8, 0, TAU); c.fill();
  c.restore();
  const M = C.map || {};
  // the pins' tags, then the places, taped to the map
  tape(R.loop ? M.pin : M.pin_start || M.pin, pts[0][0] + 110, pts[0][1] - 42, { size: 22, col: GO, ink: '#fff', ends: 'cut', rot: -.02 });
  if (!R.loop) tape(M.pin_finish, pts[N - 1][0] + 110, pts[N - 1][1] - 42, { size: 22, col: INK, ink: '#fff', ends: 'cut', rot: -.02 });
  SK.alpha(1 - clamp(cam.w * 2.5), () => {
    (M.labels || []).forEach((lab, k) => {
      const [mx, my] = uvOf(lab), [x, y] = P(mx, my), st = STYLE[lab.style || 'cream'] || STYLE.cream;
      tape(lab.text, x + (lab.dx || 0), y + (lab.dy || 0), { size: st.size || 30, col: st.col, ink: st.ink, rot: lab.rot ?? (k % 2 ? .02 : -.04), in: { t: WHEN[lab.when || 'start'] ?? R0, type: 'slap' }, max: 620 });
    });
    if (M.stamp) {
      const [sx, sy] = P(...uvOf(M.stamp_at || { mark: 'top' }));
      SK.stamp(sx + 110, sy - 150, { shape: 'rect', w: Math.max(360, Math.min(720, M.stamp.length * 24 + 60)), h: 120, text: M.stamp, col: BLUE, font: HEAD, t: T.take, rot: -.06 });
    }
  });
  // the app's panel: the numbers, read off the rows at the dot
  const PL = M.panel || {}, X = 470, Y = -410, W = 440, H = 700;
  card(X, Y, W, H);
  text(PL.title || 'RIDE REPLAY', X + 28, Y + 43, { size: 18, ls: 3, col: SOFT, align: 'left' });
  const sp = (clockAt(t + .25) - clockAt(t - .25)) / .5, fin = t > RF + .15, q = sp > 200 ? 10 : 5;
  const pillTxt = fin ? (PL.finished || 'FINISHED') : sp < 1 ? (PL.ready || 'READY') : Math.max(1, Math.round(sp / q) * q) + 'x';
  c.save(); c.font = `800 24px "${UI}"`; const pw = c.measureText(pillTxt).width + 36;
  SK.rrPath(X + W - 28 - pw, Y + 22, pw, 42, 21); c.fillStyle = fin ? GO : OR; c.fill(); c.restore();
  text(pillTxt, X + W - 28 - pw / 2, Y + 44, { size: 24, wt: 800, col: '#fff' });
  [[PL.distance || 'DISTANCE', r.mi.toFixed(1), UNIT.dist], [PL.elevation || 'ELEVATION', fmt(r.ele), UNIT.ele], [PL.climb || 'CLIMB', fmt(r.gain), UNIT.ele]].forEach(([L, v, u], k) => {
    const y = Y + 118 + k * 122;
    c.fillStyle = '#e8e3da'; c.fillRect(X + 28, y - 30, W - 56, 2);
    text(L, X + 28, y, { size: 18, ls: 3, col: SOFT, align: 'left' });
    const w = tnum(v, X + 26, y + 70, 62);
    text(u, X + 36 + w, y + 70, { size: 26, col: SOFT, align: 'left', base: 'alphabetic' });
  });
  let e0 = Infinity, e1 = -Infinity;
  for (const row of RIDE) { e0 = Math.min(e0, row[2]); e1 = Math.max(e1, row[2]); }
  const lo = Math.min(0, e0 - .08 * (e1 - e0)), hi = e1 + .04 * (e1 - lo) + 1;
  const px0 = X + 28, pwid = W - 56, py1 = Y + 655, phh = 120, PX = (mi) => px0 + mi / MI_END * pwid, PY = (e) => py1 - (e - lo) / (hi - lo) * phh;
  text(PL.profile || 'ELEVATION PROFILE', X + 28, Y + 492, { size: 16, ls: 3, col: SOFT, align: 'left' });
  const prof = () => { c.beginPath(); c.moveTo(px0, py1); RIDE.forEach((row) => c.lineTo(PX(row[3]), PY(row[2]))); c.lineTo(px0 + pwid, py1); c.closePath(); };
  c.save(); prof(); c.fillStyle = SAND; c.fill(); c.fillStyle = SK.paperPattern(SAND, 1.2); c.fill();
  c.clip(); c.fillStyle = 'rgba(252,82,0,.55)'; c.fillRect(px0, py1 - phh - 10, PX(r.mi) - px0, phh + 10); c.restore();
  c.save(); c.strokeStyle = INK; c.lineWidth = 2; c.beginPath(); c.moveTo(PX(r.mi), py1 - phh - 8); c.lineTo(PX(r.mi), py1); c.stroke();
  c.fillStyle = '#fff'; c.beginPath(); c.arc(PX(r.mi), PY(r.ele), 8, 0, TAU); c.fill(); c.fillStyle = OR; c.beginPath(); c.arc(PX(r.mi), PY(r.ele), 5, 0, TAU); c.fill(); c.restore();
  text('0 ' + UNIT.dist, px0, py1 + 20, { size: 15, col: SOFT, align: 'left' });
  text(MI_END.toFixed(1) + ' ' + UNIT.dist, px0 + pwid, py1 + 20, { size: 15, col: SOFT, align: 'right' });
  // the finish card: the route's three numbers
  const F = C.finish || [];
  tape(F[0], -690, -250, { size: 104, col: INK, ink: CREAM, rot: -.03, in: { t: T.miles, type: 'slap' }, max: 560 });
  tape(F[1], -690, -70, { size: 104, col: CREAM, ink: INK, rot: .02, in: { t: T.milesE + .3, type: 'slap' }, max: 560 });
  tape(F[2], -690, 95, { size: 58, col: SUN, ink: INK, rot: -.02, in: { t: T.about, type: 'slap' }, max: 560 });
  const credit = M.credit || 'Map data © OpenStreetMap contributors';
  c.save(); c.font = `500 16px "${UI}"`; const cw = c.measureText(credit).width;
  c.fillStyle = 'rgba(255,255,255,.82)'; c.fillRect(-944, 498, cw + 20, 28); c.restore();
  text(credit, -934, 512, { size: 16, wt: 500, col: '#3b4452', align: 'left' });
}

/* ---------------------------------------------------------------- the pages */
const EV = C.event || {}, WHO = C.who || {}, PIC = C.pictures || {}, KIT = C.kit || {}, CTA = C.cta || {};
const SC = [];
const scene = (t0, from, draw) => SC.push({ t0, from, draw });
const tP2 = T.l2 - .35, tP3 = T.l3 - .45, tP4 = T.l9 - .35, tP5 = T.l10 - .45;

scene(0, null, (t) => { // the hook: the place it starts, the day and the time
  page(SKY, 2);
  SK.burst(-780, -385, 180, { col: '#f9dc8a', spikes: 30, inner: .8, spin: .12, shadow: false });
  SK.disc(-780, -385, 120, { col: SUN, seed: 4 });
  SK.sheet(0, 360, 2020, 420, { col: SEA, edges: 't', amp: 12, seed: 6, shadow: { blur: 18, y: -4 } });
  if (PIC.decor && SK.IMG[PIC.decor]) SK.cutout(PIC.decor, -835, 60, 250, { rot: .025 * Math.sin(t * 1.4) });
  if (PIC.hero && SK.IMG[PIC.hero]) SK.cutout(PIC.hero, 150 + 6 * t, 255, 1150);
  tape(EV.day, -470, -400, { size: 124, col: INK, ink: CREAM, rot: -.035, in: { t: T.sunday - .1, type: 'slap' }, max: 560 });
  tape(EV.time, 60, -405, { size: 124, col: SUN, ink: INK, rot: .03, in: { t: T.eight - .05, type: 'slap' }, max: 470 });
  tape(EV.where, -260, -262, { size: 86, col: CREAM, ink: INK, rot: -.015, in: { t: T.santa - .05, type: 'slap' }, max: 1150 });
  framed(EV.badge, 690, -335, 286, { rot: .05, in: { t: T.sunday + .5, type: 'drop' } });
  if (EV.badge && SK.IMG[EV.badge]) SK.maskingTape(690, -335 - 286 * aspect(EV.badge) / 2 - 10, 140, { rot: .06, in: { t: T.sunday + .65, type: 'fade' } });
  const nm = (EV.name || '').replace(/\n/g, ' ');
  SK.headline(nm, -170, -100, { font: HEAD, size: fit(nm, 158, 1500), col: INK, ls: 2, distress: .12, in: { t: T.pedal - .05, type: 'slap' } });
  if (EV.again) SK.stamp(600, 30, { shape: 'rect', w: Math.max(300, Math.min(520, EV.again.length * 18 + 60)), h: 112, text: EV.again, col: RED, font: HEAD, t: T.back, rot: -.1 });
});

scene(tP2, 'r', (t) => { // who it is for
  page(SAND, 3);
  if (PIC.vista && SK.IMG[PIC.vista]) {
    const h = Math.min(600, Math.round(844 * aspect(PIC.vista)) + 36);
    SK.layer({ x: -440, y: -80, rot: -.025, nudge: 1, w: 880, h }, () => {
      SK.sheet(0, 0, 880, h, { col: '#fbf8f0', edges: '', tex: .3, shadow: { blur: 16, y: 6 }, seed: 8 });
      SK.image(PIC.vista, 0, 0, 844);
    });
    SK.maskingTape(-850, -80 - h / 2 + 20, 130, { rot: -.6 }); SK.maskingTape(-30, -80 - h / 2, 130, { rot: .55 });
  }
  tape(WHO.lead, 420, -400, { size: 44, col: INK, ink: CREAM, in: { t: T.ride - .2, type: 'slap' }, max: 760 });
  const words = (WHO.words || []).slice(0, 3), cols = [INK, INK, SEA];
  [T.founders, T.builders, T.vcs].forEach((t0, k) => {
    if (words[k]) SK.headline(words[k], 170, -265 + k * 135, { font: HEAD, size: fit(words[k], 132, 760), col: cols[k], align: 'left', distress: .1, in: { t: t0 - .05, type: 'slap' } });
  });
  hosted(600, 168, 420, .02, { in: { t: tP2 + .9, type: 'drop' } });
  const u = clamp((t - tP2) / (tP3 + .6 - tP2));
  if (PIC.riders && SK.IMG[PIC.riders]) SK.cutout(PIC.riders, lerp(-1350, 1350, u), 338, 560, { rot: -.01 });
});

scene(tP3, 'r', (t) => { page(TABLE, 4); replay(t); });

scene(tP4, 'r', (t) => { // the kit, pasted in like a packing list
  page(SAGE, 5);
  SK.headline(KIT.title || '', -880, -380, { font: HEAD, size: fit(KIT.title || '', 112, 860), col: INK, align: 'left', distress: .1 });
  if (KIT.stamp) SK.stamp(720, -330, { top: KIT.stamp.top || '', text: KIT.stamp.text || '', bottom: KIT.stamp.bottom || '', r: 118, col: BLUE, font: HEAD, t: tP4 + .6, rot: .12 });
  const main = KIT.main || {};
  if (main.image && SK.IMG[main.image]) SK.cutout(main.image, -470, -10 + 3 * Math.sin(t * 2), 660, { rot: -.02 });
  tape(main.label, -470, 235, { size: 44, col: INK, ink: CREAM, max: 640 });
  const SLOT = [[60, -150, 300, 45, T.jersey], [330, -130, 170, 80, T.bibs], [85, 215, 230, 385, T.gels], [320, 215, 150, 380, T.bars], [565, 190, 220, 400, T.bottles - .2]];
  (KIT.items || []).slice(0, 5).forEach((it, k) => {
    const [x, y, w, ly, t0] = SLOT[k];
    if (it.image && SK.IMG[it.image]) SK.cutout(it.image, x, y, w, { rot: (SK.rnd(w) - .5) * .12, in: { t: t0 - .15, type: 'drop' } });
    tape(it.label, x, ly, { size: 30, col: CREAM, ink: INK, in: { t: t0, type: 'slap' }, max: 260 });
  });
});

scene(tP5, 'r', (t) => { // the last screen: everything to act on, held still
  page(CREAM, 6);
  if (EV.badge && SK.IMG[EV.badge]) {
    SK.burst(-60, -250, 185, { col: SUN, spikes: 28, inner: .86, spin: .22, shadow: false, seed: 12 });
    framed(EV.badge, -60, -250, 250, { rot: -.04 });
    SK.maskingTape(-60, -250 - 250 * aspect(EV.badge) / 2 - 12, 120, { rot: -.05 });
  }
  tape(EV.tag, -755, -478, { font: UI, wt: 800, size: 30, col: SEA, ink: '#fff', ends: 'cut', max: 700 });
  const lines = twoLines(EV.name || '');
  SK.headline(lines, -880, -225, { font: HEAD, size: fit(lines, 150, 760), lh: .95, col: INK, align: 'left', distress: .08 });
  tape(EV.date_line, -605, 30, { size: 56, col: INK, ink: CREAM, rot: -.015, max: 820 });
  tape(EV.where, -640, 125, { size: 56, col: SAND, ink: INK, rot: .015, max: 820 });
  hosted(-670, 285, 400, -.015);
  if (PIC.riders && SK.IMG[PIC.riders]) SK.cutout(PIC.riders, -160 + 26 * (t - tP5), 300, 500);
  card(330, -415, 460, 665); // the call to act, and its QR: flat, square, unrotated, on white
  text(CTA.title || '', 560, -362, { size: fit(CTA.title || '', 38, 420, UI, 800), wt: 800 });
  if (CTA.qr && SK.IMG[CTA.qr]) SK.image(CTA.qr, 560, -115, 380);
  if (CTA.url) text(CTA.url, 560, 112, { size: fit(CTA.url, 28, 420, UI, 700), wt: 700, col: BLUE });
  if (CTA.note) text(CTA.note, 560, 160, { size: 20, wt: 500, col: SOFT });
});

function caption(t) { // the lines, each in its slot
  const L = C.lines || [];
  for (let i = 0; i < Math.min(L.length, SLOTS.length); i++) {
    const s = SLOTS[i] - .1, e = i + 1 < SLOTS.length ? SLOTS[i + 1] - .1 : DUR + 1;
    if (L[i] && t >= s && t < e) SK.tape(L[i], 0, 486, { font: UI, wt: 600, size: fit(L[i], 29, 1500, UI, 600), col: INK, ink: CREAM, ends: 'cut', rot: 0, tex: .25, distress: 0, ls: 0, padX: 24, padY: 9, in: { t: s, type: 'fade', d: .2 }, seed: 80 + i });
  }
}

/* ---------------------------------------------------------------- the sound
   On the one clock above, so it is the same for every ride: a 120 bpm groove in D (I-V-vi-IV), drums in on
   the replay, a timpani roll and the strings rising up the climb to the top's hit at 22 s, the descent's
   drive, a quiet bar for the kit and the last chord on the last screen; a slap, a pop or a whoosh on every
   piece pasted in. */
function scoreData() {
  return {"bpm":120,"drum_gain":.16,"events":[
    {"inst":"synth_bass_1","vel":.24,"notes":"0 D2 1; 1.5 D2 .5; 2 D2 1.5; 3.5 D2 .5; 4 A1 1; 5.5 A1 .5; 6 A1 1.5; 7.5 A1 .5; 8 B1 1; 9.5 B1 .5; 10 B1 1.5; 11.5 B1 .5; 12 G1 1; 13.5 G1 .5; 14 G1 1.5; 15.5 G1 .5; 16 D2 1; 17.5 D2 .5; 18 D2 1.5; 19.5 D2 .5; 20 A1 1; 21.5 A1 .5; 22 A1 1.5; 23.5 A1 .5; 24 B1 1; 25.5 B1 .5; 26 B1 1.5; 27.5 B1 .5; 28 G1 1; 29.5 G1 .5; 30 G1 1.5; 31.5 G1 .5; 32 B1 1; 33.5 B1 .5; 34 B1 1.5; 35.5 B1 .5; 36 G1 1; 37.5 G1 .5; 38 G1 1.5; 39.5 G1 .5; 40 A1 .5; 40.5 A1 .5; 41 A1 .5; 41.5 A1 .5; 42 A1 .5; 42.5 A1 .5; 43 A1 .5; 43.5 A1 .5; 44 D2 4; 48 A1 .5; 48.5 A1 .5; 49 A1 .5; 49.5 A1 .5; 50 A1 .5; 50.5 A1 .5; 51 A1 .5; 51.5 A1 .5; 52 D2 1; 53.5 D2 .5; 54 D2 1.5; 55.5 D2 .5; 56 A1 1; 57.5 A1 .5; 58 A1 1.5; 59.5 A1 .5; 60 B1 1; 61.5 B1 .5; 62 B1 1.5; 63.5 B1 .5; 64 G1 1; 65.5 G1 .5; 66 G1 1.5; 67.5 G1 .5; 68 A1 1; 69.5 A1 .5; 70 A1 1.5; 71.5 A1 .5; 72 D2 1; 73.5 D2 .5; 74 D2 1.5; 75.5 D2 .5; 76 A1 1; 77.5 A1 .5; 78 A1 1.5; 79.5 A1 .5; 80 B1 1; 81.5 B1 .5; 82 B1 1.5; 83.5 B1 .5; 84 G1 1; 85 A1 1; 86 D2 4"},
    {"inst":"pad_3_polysynth","vel":.11,"notes":"0 D3+F#3+A3+D4 4; 4 C#3+E3+A3+C#4 4; 8 D3+F#3+B3+D4 4; 12 D3+G3+B3+D4 4; 16 D3+F#3+A3+D4 4; 20 C#3+E3+A3+C#4 4; 24 D3+F#3+B3+D4 4; 28 D3+G3+B3+D4 4; 32 D3+F#3+B3+D4 4; 36 D3+G3+B3+D4 4; 40 C#3+E3+A3+C#4 4; 44 D3+F#3+A3+D4 4; 48 C#3+E3+A3+C#4 4; 52 D3+F#3+A3+D4 4; 56 C#3+E3+A3+C#4 4; 60 D3+F#3+B3+D4 4; 64 D3+G3+B3+D4 4; 68 C#3+E3+A3+C#4 4; 72 D3+F#3+A3+D4 4; 76 C#3+E3+A3+C#4 4; 80 D3+F#3+B3+D4 4; 84 D3+G3+B3+D4 1; 85 C#3+E3+A3+C#4 1; 86 D3+F#3+A3+D4 4"},
    {"type":"strum","at":0,"chord":"D3+A3+D4+F#4","vel":.24,"pattern":"bar"},{"type":"strum","at":4,"chord":"E3+A3+C#4+E4","vel":.24,"pattern":"bar"},
    {"type":"strum","at":8,"chord":"F#3+B3+D4+F#4","vel":.24,"pattern":"bar"},{"type":"strum","at":12,"chord":"D3+G3+B3+D4","vel":.24,"pattern":"bar"},
    {"type":"strum","at":16,"chord":"D3+A3+D4+F#4","vel":.25,"pattern":"bar"},{"type":"strum","at":20,"chord":"E3+A3+C#4+E4","vel":.25,"pattern":"bar"},
    {"type":"strum","at":24,"chord":"F#3+B3+D4+F#4","vel":.26,"pattern":"bar"},{"type":"strum","at":28,"chord":"D3+G3+B3+D4","vel":.27,"pattern":"bar"},
    {"type":"strum","at":32,"chord":"F#3+B3+D4+F#4","vel":.28,"pattern":"bar"},{"type":"strum","at":36,"chord":"D3+G3+B3+D4","vel":.29,"pattern":"bar"},
    {"type":"strum","at":40,"chord":"E3+A3+C#4+E4","vel":.31,"pattern":"bar"},{"type":"strum","at":44,"chord":"D3+A3+D4+F#4+A4","vel":.2,"pattern":"once"},
    {"type":"strum","at":48,"chord":"E3+A3+C#4+E4","vel":.28,"pattern":"bar"},{"type":"strum","at":52,"chord":"D3+A3+D4+F#4","vel":.26,"pattern":"bar"},
    {"type":"strum","at":56,"chord":"E3+A3+C#4+E4","vel":.24,"pattern":"bar"},{"type":"strum","at":60,"chord":"F#3+B3+D4+F#4","vel":.24,"pattern":"bar"},
    {"type":"strum","at":64,"chord":"D3+G3+B3+D4","vel":.24,"pattern":"bar"},{"type":"strum","at":68,"chord":"E3+A3+C#4+E4","vel":.24,"pattern":"bar"},
    {"type":"strum","at":72,"chord":"D3+A3+D4+F#4","vel":.24,"pattern":"bar"},{"type":"strum","at":76,"chord":"E3+A3+C#4+E4","vel":.23,"pattern":"bar"},
    {"type":"strum","at":80,"chord":"F#3+B3+D4+F#4","vel":.23,"pattern":"bar"},{"type":"strum","at":86,"chord":"D3+A3+D4+F#4+A4","vel":.3,"pattern":"once"},
    {"inst":"string_ensemble_1","vel":.08,"swell":[.3,1],"notes":"28 D4+G4+B4 4 .5; 32 D4+F#4+B4 4 .6; 36 D4+G4+B4 4 .75; 40 E4+A4+C#5 4 .8; 44 D4+F#4+A4+D5 4 .55"},
    {"type":"roll","inst":"timpani","note":"A1","from":40,"to":44,"v0":.06,"v1":.3},
    {"inst":"timpani","vel":.26,"notes":"44 D2 2; 52 D2 1"},
    {"inst":"electric_piano_1","vel":.15,"notes":"44.5 A5 .5; 45 D6 .5; 45.5 F#6 1; 47 E6 .5; 47.5 D6 .5; 52.5 A5 .5; 53 D6 .5; 53.5 F#6 1.5; 84.5 A5 .5; 85 D6 .5; 86 F#6+A6+D7 4"},
    {"type":"drums","from":0,"bars":4,"kit":{"kick":"x...x...x...x...","hat":"..x...x...x...x."},"vel":.55},
    {"type":"drums","from":16,"bars":3,"kit":{"kick":"x...x...x...x...","snare":"....x.......x...","hat":"x.x.x.x.x.x.x.x."},"vel":.58},
    {"type":"drums","from":28,"bars":3,"kit":{"kick":"x...x...x...x.x.","snare":"....x.......x...","hat":"xoxoxoxoxoxoxoxo"},"vel":.55},
    {"type":"drums","from":40,"bars":1,"kit":{"kick":"x...x...x...x...","snare":"....x...x.x.xxxx","hat":"xoxoxoxoxoxoxoxo"},"vel":.62},
    {"type":"drums","from":44,"bars":1,"kit":{"kick":"X..............."},"vel":.55},
    {"type":"drums","from":48,"bars":1,"kit":{"kick":"x.x.x.x.x.x.x.x.","hat":"xxxxxxxxxxxxxxxx"},"vel":.5},
    {"type":"drums","from":52,"bars":5,"kit":{"kick":"x...x...x...x...","snare":"....x.......x...","hat":"x.x.x.x.x.x.x.x."},"vel":.5},
    {"type":"drums","from":72,"bars":3,"kit":{"kick":"x.......x.......","hat":"..x...x...x...x."},"vel":.45}
  ]};
}
function sfxData() {
  const cues = [
    [.6, 'thunk', -26, -.3, { sec: .3 }], [1.2, 'crinkle', -30, .5, { sec: .25 }], [1.87, 'thunk', -27, .1, { sec: .3 }],
    [3.01, 'thunk', -27, -.2, { sec: .3 }], [4.62, 'thunk', -24, 0, { sec: .4 }], [6.41, 'thunk', -26, .5, { sec: .35 }],
    [7.27, 'swoosh_soft', -26, 0, { sec: .6 }], [8.69, 'thunk', -29, .3, { sec: .3 }], [9.83, 'thunk', -29, .3, { sec: .3 }],
    [10.39, 'thunk', -29, .3, { sec: .3 }], [11.09, 'whoosh', -27, 0, { sec: .7, f0: 300, f1: 2400 }], [11.84, 'blip', -30, .1, { f: 1320, sec: .09 }],
    [13.04, 'crinkle', -31, .2, { sec: .25 }], [20.87, 'crinkle', -31, -.3, { sec: .25 }], [21.98, 'thunk', -22, -.1, { sec: .5 }],
    [22.0, 'crash', -28, 0, { sec: 2.2 }], [24.0, 'whoosh', -28, 0, { sec: 2.0, f0: 500, f1: 3200, peak: .7 }],
    [26.64, 'thunk', -28, -.5, { sec: .3 }], [28.36, 'thunk', -28, -.5, { sec: .3 }], [29.18, 'thunk', -28, -.5, { sec: .3 }],
    [30.78, 'swoosh_soft', -26, 0, { sec: .6 }], [31.38, 'thunk', -28, .6, { sec: .3 }], [36.19, 'swoosh_soft', -26, 0, { sec: .6 }],
  ].map(([t, fx, db, pan, args]) => ({ t, fx, db, ...(pan ? { pan } : {}), args }));
  cues.push({ t: 26.16, fx: 'chime', db: -26, send: .3 }, { t: 36.9, fx: 'chime', db: -28, send: .35 });
  // a pop for each piece of kit pasted in
  const SLOT_T = [T.jersey, T.bibs, T.gels, T.bars, T.bottles - .2];
  (KIT.items || []).slice(0, 5).forEach((_, k) => cues.push({ t: +(SLOT_T[k] - .15).toFixed(2), fx: 'pop', db: -28, pan: [-.1, .3, .1, .3, .5][k], args: { f0: 700, f1: 280, sec: .08 } }));
  return cues.sort((a, b) => a.t - b.t);
}

SK.film({
  duration: DUR,
  camera: SK.camera([[0, [0, 0, 1]]]),
  fadeOut: .5,
  handheld: false,
  draw(t) {
    SC.forEach((sc, i) => {
      const nx = SC[i + 1];
      if (t < sc.t0 || (nx && t > nx.t0 + .9)) return;
      if (!sc.from) return sc.draw(t);
      SK.layer({ in: { t: sc.t0, type: 'slide', from: sc.from, dist: 2100, d: .7 }, steps: 0, nudge: 0 }, () => sc.draw(t));
    });
    caption(t);
  },
  sound: { score: scoreData, sfx: sfxData },
});
