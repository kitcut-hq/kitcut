// For: people who follow the event on social -- the organiser's countdown post of the last weeks; urgent, crisp, on the beat
/* A conference countdown in 26 s with no narration: the music carries it. This film is a template:
   every word, colour and the logo are in content.json (SK.DATA.content) and nothing of the event is in
   the code. The frame is the manifest's (1080 x 1080 first; 1920 x 1080 and 1080 x 1920 hold too):
   every layout below reads W, H and U (a unit: the frame's short side / 1080).

   The story is one tear-off calendar: it drops onto its nail (today's page), its pages rip off and fly
   past the camera faster and faster (quarters, eighths, sixteenths) and land on the count; the count
   page itself tears off at the camera and leaves the published facts pinned on the wall; a ticket
   slides in and its price tag flips to the next price; the month's grid circles the first day.

   The clock below is the one home of its timing: the score and every sound cue are worked out from it
   and from the content (SK.film({sound})), so another event brings its own clicks and pins. */
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, TAU = SK.TAU, rnd = SK.rnd;
const CX = W / 2, CY = H / 2, U = Math.min(W, H) / 1080, WIDE = W / H > 1.3, TALL = H / W > 1.3;
const D = SK.DATA.content;

/* ------------------------------------------------------------------ palette and type */
function rgbOf(hex) { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function mixHex(a, b, u) { const x = rgbOf(a), y = rgbOf(b); return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * u).toString(16).padStart(2, '0')).join(''); }
const P0 = D.palette;
const C = { light: '#FFFFFF', paper: '#FFFFFF', ...P0 };
C.ink = C.ink ?? C.ground; C.black = C.black ?? mixHex(C.ground, '#000000', .6); C.deep = C.deep ?? mixHex(C.accent, '#000000', .2);
C.second = C.second ?? mixHex(C.accent, '#FFFFFF', .4); C.soft = C.soft ?? mixHex(C.ground, '#FFFFFF', .7);
C.paperBack = C.paperBack ?? mixHex(C.paper, C.ground, .12); C.paperEdge = C.paperEdge ?? mixHex(C.paper, C.ground, .25);
C.inkSoft = C.inkSoft ?? mixHex(C.ink, C.paper, .35); C.dot = C.dot ?? mixHex(C.ground, '#FFFFFF', .1); C.groundLt = C.groundLt ?? mixHex(C.ground, '#FFFFFF', .06);
C.shadow = rgbOf(C.black).join(',');
SK.setStyle('clean', { grain: .35, vignette: .28, handheld: 0, vignetteRGB: C.shadow });
Object.assign(SK.C, { paper: C.ground, text: C.light, textSoft: C.soft, accent: C.accent, accentText: C.accent, ink: C.ink });
const FONT = { display: 'sans-serif', ui: 'sans-serif', ...(D.fonts || {}) }; // the event's own faces (content.fonts)

/* ------------------------------------------------------------------ the words and the dates */
const EV = D.event;
const words = (s) => String(s ?? '').replace(/\{(\w+)\}/g, (_, k) => EV[k] ?? '');
const COPY = Object.fromEntries(Object.entries(D.copy).map(([k, v]) => [k, typeof v === 'string' ? words(v) : v]));
const COUNT = { ...(D.count || {}) }, FACTS = (D.facts || []).filter((f) => f && f.value).slice(0, 3), TICKET = D.ticket || {};
if (!COUNT.note && !FACTS.length) COUNT.note = [EV.dates_long || EV.dates, EV.city].filter(Boolean).join(' · '); // the count holds longer: it says when and where
const iso = (s) => { const [y, m, d] = String(s).split('-').map(Number); return { y, m: m - 1, d }; };
const FIRST = iso(EV.first_day), LASTD = EV.last_day ? iso(EV.last_day) : FIRST, TODAY = COUNT.today ? iso(COUNT.today) : null;
const dow = (o) => new Date(Date.UTC(o.y, o.m, o.d)).getUTCDay();
const WS = COPY.week_start ?? 0;
const MONTH = { lead: (dow({ y: FIRST.y, m: FIRST.m, d: 1 }) - WS + 7) % 7, days: new Date(Date.UTC(FIRST.y, FIRST.m + 1, 0)).getUTCDate() };
MONTH.rows = Math.ceil((MONTH.lead + MONTH.days) / 7);
const sameMonth = (o) => o && o.y === FIRST.y && o.m === FIRST.m;

/* ------------------------------------------------------------------ the clock (120 bpm: a beat is .5 s, a bar 2 s) */
const TEARS = [4.0, 5.0, 5.5, 6.0, 6.5, 6.75, 7.0, 7.25, 7.5, 7.625, 7.75, 7.875]; // quarters, eighths, sixteenths
const LAND = 8.0;                                   // the count lands on the bar line
const S2_END = FACTS.length ? 10 : 14;              // the count page tears off at the camera...
const COVER = [S2_END - .3, S2_END];                // ... and covers the cut
const PIN = [10.5, 11.5, 12.5];                     // the facts are pinned, a beat apart
const SWAP = [15.8, 16.2];                          // facts -> ticket (a whip)
const TICKET_IN = FACTS.length ? 16.0 : 14.0, FLIP = 18.0, DEAD = 18.25;  // the ticket, its tag's flip, the deadline
const END = [20.75, 21.1], END_IN = 21.0, CIRCLE = 22.0, BUTTON = 22.25, LAST = 24.0;
const NUM = parseInt(COUNT.number, 10);
/* the torn sheets count down to the count: from its number; with no number (a word, a deadline), from
   count.days (the days until what is counted to) or the days from today to the first day; with none
   of them the sheets carry the band alone */
const daysTo = (a, b) => Math.round((Date.UTC(b.y, b.m, b.d) - Date.UTC(a.y, a.m, a.d)) / 864e5);
const BASE = isFinite(NUM) ? NUM : isFinite(parseInt(COUNT.days, 10)) ? parseInt(COUNT.days, 10) : TODAY ? Math.max(0, daysTo(TODAY, FIRST)) : null;
const tickSub = (n) => (n === 1 && COPY.day_label) || COPY.days_label || (isFinite(NUM) ? COUNT.label : '') || '';
const PAGES = [{ kind: TODAY ? 'date' : 'tick', n: BASE != null ? BASE + TEARS.length : null },
  ...TEARS.slice(1).map((_, i) => ({ kind: 'tick', n: BASE != null ? BASE + TEARS.length - 1 - i : null })), { kind: 'count' }];
PAGES.forEach((p, i) => { p.i = i; });
const FLY = (i) => (i === 0 ? .9 : Math.max(.42, .75 - i * .03)); // how long a torn page takes to leave

/* ------------------------------------------------------------------ helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (t) => { const c3 = k + 1; return 1 + c3 * Math.pow(t - 1, 3) + k * Math.pow(t - 1, 2); };
const outBack = back(1.5), outBackSoft = back(.9);
function font(size, wt = 900, fam = FONT.display) { return `${wt} ${size}px ${fam}, "Sofia Sans", sans-serif`; } // the fallback has Cyrillic and Greek
function text(str, x, y, o = {}) {
  const c = g(); c.save();
  c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? FONT.display);
  c.textAlign = o.align ?? 'left'; c.textBaseline = 'alphabetic'; c.letterSpacing = (o.ls ?? 0) + 'px';
  c.globalAlpha *= o.alpha ?? 1; c.fillStyle = o.col ?? C.light; c.fillText(str, x, y); c.restore();
}
function measure(str, o = {}) {
  const c = g(); c.save(); c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? FONT.display); c.letterSpacing = (o.ls ?? 0) + 'px';
  const w = c.measureText(str).width; c.restore(); return w;
}
function fit(str, width, max, o = {}) { return Math.min(max, max * width / Math.max(1, measure(str, { ...o, size: max }))); }
/** shrink, then wrap: the size and lines at which str fits width in up to n lines */
function wrap(str, width, max, o = {}, n = 3) {
  const one = fit(str, width, max, o);
  if (one >= max * .8 || !String(str).includes(' ')) return { size: one, lines: [str] };
  const ws = String(str).split(' ');
  for (let size = max; size > 6; size *= .95) {
    const lines = []; let cur = '';
    for (const w of ws) { const s = cur ? cur + ' ' + w : w; if (!cur || measure(s, { ...o, size }) <= width) cur = s; else { lines.push(cur); cur = w; } }
    lines.push(cur);
    if (lines.length <= n && lines.every((l) => measure(l, { ...o, size }) <= width)) return { size, lines };
  }
  return { size: one, lines: [str] };
}
function clipRect(x, y, w, h, fn) { const c = g(); c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); fn(); c.restore(); }
function rrect(x, y, w, h, r, fill) { const c = g(); SK.rrPath(x, y, w, h, r); c.fillStyle = fill; c.fill(); }
function poly(pts, fill) { const c = g(); c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); for (const p of pts.slice(1)) c.lineTo(p[0], p[1]); c.closePath(); c.fillStyle = fill; c.fill(); }
const withT = (x, y, rot, s, fn) => SK.at(x, y, rot, s, fn);
function arrow(x, y, s, col, w = 9) {
  const c = g(); c.save(); c.strokeStyle = col; c.lineWidth = w * s; c.lineCap = 'round'; c.lineJoin = 'round';
  c.beginPath(); c.moveTo(x - 24 * s, y); c.lineTo(x + 22 * s, y); c.moveTo(x + 2 * s, y - 20 * s); c.lineTo(x + 24 * s, y); c.lineTo(x + 2 * s, y + 20 * s); c.stroke(); c.restore();
}

/* the logo: its own shapes as its file draws them (event.logo.shapes in its viewBox, event.logo.box),
   each rising from under a mask; without shapes, the image (its light version on the dark ground) */
const LG = EV.logo || {};
const logoImg = () => SK.IMG[LG.light || LG.image] || SK.IMG[LG.image];
const logoW = (h) => (LG.shapes && LG.box ? LG.box[0] * h / LG.box[1] : logoImg() ? logoImg().width * h / logoImg().height : 0);
function logo(x, y, h, grow = [1, 1, 1], col) { // x, y: top-left
  const c = g();
  if (LG.shapes && LG.box) {
    const s = h / LG.box[1];
    c.save(); c.beginPath(); c.rect(x - 2, y - 2, LG.box[0] * s + 4, h + 4); c.clip();
    LG.shapes.forEach((pts, i) => { const k = grow[i] ?? grow[grow.length - 1]; if (k > 0) poly(pts.map(([px, py]) => [x + px * s, y + py * s + (1 - k) * h * 1.1]), col ?? LG.col ?? C.accent); });
    c.restore(); return;
  }
  const im = logoImg(); if (im) SK.alpha(Math.min(...grow), () => c.drawImage(im, x, y, logoW(h), h));
}
/** the logo and the event's word beside it, as its own lockup sets them: on one line, or on two
    when the word is long (the logo then a little taller). Returns { h, lines, size, w } */
function lockupPlan(hMax, maxW) {
  const word = String(EV.lockup || ''), ms = (str, size) => measure(str, { size, wt: 900 });
  const one = (h) => logoW(h) + (word ? h * .42 + ms(word, h * 1.37) : 0);
  const h1 = Math.min(hMax, hMax * maxW / Math.max(1, one(hMax))), p1 = { h: h1, lines: word ? [word] : [], size: h1 * 1.37, w: one(h1) };
  if (!word || h1 >= hMax * .72 || !word.includes(' ')) return p1;
  const ws = word.split(' '); let best = null;
  for (let i = 1; i < ws.length; i++) { const l = [ws.slice(0, i).join(' '), ws.slice(i).join(' ')], m = Math.max(ms(l[0], 100), ms(l[1], 100)); if (!best || m < best.m) best = { m, lines: l }; }
  const two = (h) => logoW(h) + h * .42 + best.m / 100 * h * .64, hb = hMax * 1.3, h2 = Math.min(hb, hb * maxW / two(hb));
  return h2 * .64 > h1 * 1.37 ? { h: h2, lines: best.lines, size: h2 * .64, w: two(h2) } : p1;
}
function lockup(x, y, hMax, t0, t, o = {}) { // x: left, y: the top of a logo hMax tall; o.maxW: the room it has
  const pl = lockupPlan(hMax, o.maxW ?? 1e9), h = pl.h, y0 = y - (h - hMax) / 2;
  const k = (d) => ease(t, t0 + d, t0 + d + .38, outBack);
  logo(x, y0, h, [k(0), k(.08), k(.16)], o.col);
  const lx = x + logoW(h) + h * .42, u = ease(t, t0 + .15, t0 + .55, E.out);
  if (u > 0) pl.lines.forEach((ln, i) => {
    const base = pl.lines.length === 1 ? y0 + h : y0 + h * (i ? 1 : .47), w = measure(ln, { size: pl.size, wt: 900 });
    clipRect(lx - 4, base - pl.size, (w + 10) * u, pl.size * 1.3, () => text(ln, lx, base, { size: pl.size, wt: 900, col: o.word ?? C.light }));
  });
  return pl;
}

/* the wall: the site's dark ground with its dotted grid; in world units (scaled with the camera) or on screen */
function wall(x0, y0, x1, y1, step, r, drift = 0) {
  const c = g(); c.fillStyle = C.ground; c.fillRect(x0 - 10, y0 - 10, x1 - x0 + 20, y1 - y0 + 20);
  c.fillStyle = C.dot;
  const ox = drift % step;
  for (let y = Math.floor(y0 / step) * step; y < y1 + step; y += step) for (let x = Math.floor(x0 / step) * step - ox; x < x1 + step; x += step) c.fillRect(x - r, y - r, r * 2, r * 2);
}
function screenWall(t) { wall(0, 0, W, H, 40 * U, 2.4 * U, t * 9 * U); }
function glow(x, y, r, a) { // a soft pool of the accent behind a piece
  const c = g(), gr = c.createRadialGradient(x, y, 0, x, y, r);
  gr.addColorStop(0, `rgba(${rgbOf(C.accent).join(',')},${a})`); gr.addColorStop(1, `rgba(${rgbOf(C.accent).join(',')},0)`);
  c.fillStyle = gr; c.fillRect(x - r, y - r, r * 2, r * 2);
}

/* ------------------------------------------------------------------ S1 + S2: the calendar and the tear */
const CAL = { w: 680, top: -380, head: 170, pw: 640, ph: 620, py: -210, nail: -440 };
const Z0 = Math.min(W * .8 / CAL.w, H * .82 / 880), ZC = Math.min(H * .98 / CAL.ph, W * 1.04 / CAL.pw);
function cam12(t) {
  const y = SK.kf(t, [[0, -10], [3.9, -2, E.sine], [LAND, CAL.py + CAL.ph / 2, E.in], [S2_END, CAL.py + CAL.ph / 2 + 6, E.sine]]);
  let z = SK.kf(t, [[0, Z0], [3.9, Z0 * 1.05, E.sine], [LAND, ZC, E.in], [S2_END, ZC * 1.045, E.sine]]);
  if (t > LAND) z *= 1 + .05 * (1 - Math.exp(-(t - LAND) * 40)) * Math.exp(-(t - LAND) * 5); // the hit
  if (t > LAND + 1) z *= 1 + .012 * Math.exp(-((t * 2) % 2) * 3); // ... and a breath on every bar's first beat while it holds
  return { y, z };
}
function tornPath(c, w, h, seed) {
  c.beginPath(); c.moveTo(0, 6);
  for (let x = 0, k = 0; x <= w; x += 14, k++) c.lineTo(x, 3 + rnd(seed * 31 + k) * 10);
  c.lineTo(w, h); c.lineTo(0, h); c.closePath();
}
/** one sheet of the pad, drawn in its own 640 x 620 frame. rv: band, num, sub, note, tag (0..1 reveals) */
function pageFace(pg, rv = {}, torn = false) {
  return (c, w, h) => {
    const count = pg.kind === 'count', bh = 64;
    c.save();
    if (torn) { tornPath(c, w, h, pg.i + 3); c.clip(); }
    c.fillStyle = count ? C.accent : C.paper; c.fillRect(0, 0, w, h);
    c.fillStyle = count ? C.deep : C.accent; c.fillRect(0, 0, w, bh);
    c.fillStyle = count ? C.accent : C.deep; for (let x = 22; x < w; x += 26) c.fillRect(x, 8, 6, 6); // the perforation
    const band = pg.kind === 'date' ? `${COPY.months[TODAY.m]} ${TODAY.y}` : `${EV.lockup || EV.name} ${EV.year}`;
    SK.alpha(rv.band ?? 1, () => text(band, w / 2, bh / 2 + 18, { size: fit(band, w - 80, 34, { wt: 800, ls: 6 }), wt: 800, ls: 6, col: C.light, align: 'center' }));
    const num = pg.kind === 'date' ? String(TODAY.d) : pg.kind === 'tick' ? (pg.n != null ? String(pg.n) : '') : String(COUNT.number ?? '');
    const sub = pg.kind === 'date' ? COPY.weekday_names[dow(TODAY)] : pg.kind === 'tick' ? (pg.n != null ? tickSub(pg.n) : '') : (COUNT.label ?? '');
    const ink = count ? C.light : C.ink, subCol = count ? C.light : C.deep;
    if (num) {
      const size = fit(num, w - 70, 548, { wt: 900, ls: -10 }), cy = 288, k = rv.num ?? 1;
      if (k > 0) withT(w / 2, cy, 0, k, () => text(num, 0, size * .365, { size, wt: 900, ls: -10, col: ink, align: 'center' }));
      if (sub) { const ss = fit(sub, w - 80, 52, { wt: 900, ls: 3 }); clipRect(0, 490, w * (rv.sub ?? 1), 80, () => text(sub, w / 2, 550, { size: ss, wt: 900, ls: 3, col: subCol, align: 'center' })); }
    } else if (sub) { // a count with no number ("TOMORROW"): the word is the big piece
      const wr = wrap(sub, w - 80, String(sub).includes(' ') ? 150 : 210, { wt: 900 }, 3), k = rv.num ?? 1, lh = wr.size * 1.0;
      if (k > 0) withT(w / 2, 304, 0, k, () => wr.lines.forEach((l, i) => text(l, 0, (i - (wr.lines.length - 1) / 2) * lh + wr.size * .365, { size: wr.size, wt: 900, col: ink, align: 'center' })));
    }
    if (count && COUNT.note && (rv.note ?? 1) > 0) SK.alpha(rv.note ?? 1, () => {
      const ns = fit(COUNT.note, w - 120, 23, { wt: 800, fam: FONT.ui, ls: 2 }), nw = measure(COUNT.note, { size: ns, wt: 800, fam: FONT.ui, ls: 2 }) + 44;
      rrect(w / 2 - nw / 2, 568, nw, 40, 20, C.black); text(COUNT.note, w / 2 + 1, 568 + 20 + ns * .36, { size: ns, wt: 800, fam: FONT.ui, ls: 2, col: C.second, align: 'center' });
    });
    if (pg.kind === 'date' && (rv.tag ?? 0) > 0) withT(w - 92, 116, -.08, outBack(rv.tag), () => {
      const tw = measure(COPY.today, { size: 22, wt: 800, fam: FONT.ui, ls: 3 }) + 34;
      rrect(-tw / 2, -20, tw, 40, 20, C.black); text(COPY.today, 1, 8, { size: 22, wt: 800, fam: FONT.ui, ls: 3, col: C.second, align: 'center' });
    });
    c.restore();
  };
}
function backFace(pg, torn) {
  return (c, w, h) => { c.save(); if (torn) { tornPath(c, w, h, pg.i + 3); c.clip(); } c.fillStyle = pg.kind === 'count' ? C.accent : C.paperBack; c.fillRect(0, 0, w, h); c.restore(); };
}
/** a sheet in 3D, hung from its top-middle at pose (x, y, z, rx, rz); its back when it has turned over */
function sheet3(pg, pose, rv, torn, key) {
  const w = CAL.pw, h = CAL.ph;
  const L = [[-w / 2, 0, 0], [w / 2, 0, 0], [w / 2, h, 0], [-w / 2, h, 0]].map((p) => SK.pose3(p, pose));
  const Q = L.map(SK.proj3); if (Q.some((q) => !q)) return;
  const area = (Q[1][0] - Q[0][0]) * (Q[3][1] - Q[0][1]) - (Q[3][0] - Q[0][0]) * (Q[1][1] - Q[0][1]);
  const shade = .5 * (1 - SK.lit3(area > 0 ? L : [L[1], L[0], L[3], L[2]], { light: [-.3, -1, -.7], ambient: .7 }));
  if (area > 0) SK.face3(L, w, h, pageFace(pg, rv, torn), { key, cull: false, shade });
  else SK.face3([L[1], L[0], L[3], L[2]], w, h, backFace(pg, torn), { key, cull: false, shade });
}
function flyPose(i, t) { // a torn page: it peels from the top, then flies up and past the camera, side to side
  const t0 = i === 0 ? TEARS[0] : TEARS[i], u = (t - t0) / FLY(i), side = i % 2 ? 1 : -1, j = rnd(i * 17 + 5);
  const pre = i === 0 ? E.inOut(clamp((t - 3.3) / .7)) : 0;
  const a = E.inOut(clamp(u / .3)), b = E.in(clamp((u - .15) / .85));
  return { x: side * (40 * a + (760 + 300 * j) * b), y: CAL.py - 50 * a - (280 + 220 * j) * b, z: -(12 * pre + 120 * a + 1460 * b), rx: -(.1 * pre + 1.0 * a + .9 * b), rz: side * (.03 * pre + .08 * a + (.5 + .4 * j) * b) };
}
function revealAt(pg, t) {
  if (pg.kind === 'date') return { band: ease(t, -.3, .1), num: ease(t, -.12, .3, outBack), sub: ease(t, .2, .5, E.out), tag: clamp((t - 2.0) / .4) };
  if (pg.kind === 'count') return { num: t < S2_END - .5 ? ease(t, 7.88, 8.3, outBack) * .4 + .6 * ease(t, 7.88, 8.12, E.out) : 1, sub: ease(t, 8.12, 8.45, E.out), note: ease(t, 8.5, 8.85, E.out) };
  return {};
}
function scene12(t) {
  const c = g(), cam = cam12(t), z = cam.z;
  c.save(); c.translate(CX, CY); c.scale(z, z); c.translate(0, -cam.y);
  const hw = CX / z, hh = CY / z;
  wall(-hw, cam.y - hh, hw, cam.y + hh, 40, 2.4);
  // the block drops onto its nail and swings to rest
  const drop = (1 - ease(t, -.45, .5, outBackSoft)) * -900,sw = t > .3 ? .045 * Math.sin((t - .3) * 5.5) * Math.exp(-(t - .3) * 1.1) : 0;
  c.translate(0, drop); c.translate(0, CAL.nail); c.rotate(sw); c.translate(0, -CAL.nail);
  c.strokeStyle = C.soft; c.lineWidth = 3; c.beginPath(); c.moveTo(-200, CAL.top + 10); c.lineTo(0, CAL.nail); c.lineTo(200, CAL.top + 10); c.stroke();
  c.fillStyle = C.soft; c.beginPath(); c.arc(0, CAL.nail, 10, 0, TAU); c.fill();
  c.save(); c.shadowColor = `rgba(${C.shadow},.6)`; c.shadowBlur = 44; c.shadowOffsetY = 26; rrect(-CAL.w / 2, CAL.top, CAL.w, CAL.head + CAL.ph + 16, 16, C.black); c.restore();
  // the pad: the sheets under the top one show at its foot
  for (let k = 3; k >= 1; k--) rrect(-CAL.pw / 2, CAL.py, CAL.pw, CAL.ph + k * 5, 4, k % 2 ? C.paperEdge : C.paperBack);
  // the header: the logo and the year
  SK.rrPath(-CAL.w / 2, CAL.top, CAL.w, CAL.head + 8, 16); c.fillStyle = C.black; c.fill();
  const lh = 58, lx = -CAL.w / 2 + 40;
  lockup(lx, CAL.top + (CAL.head - lh) / 2, lh, -.1, t, { maxW: CAL.w - 240 });
  SK.alpha(ease(t, .2, .5), () => text(EV.year, CAL.w / 2 - 40, CAL.top + CAL.head / 2 + 22, { size: 60, wt: 900, col: C.second, align: 'right' }));
  // the top sheet still on the pad, and the one under a sheet that is lifting
  const airborne = (i) => t >= (i === 0 ? 3.3 : i === PAGES.length - 1 ? COVER[0] : TEARS[i]);
  let top = 0; while (top < PAGES.length && airborne(top)) top++;
  if (top < PAGES.length) withT(-CAL.pw / 2, CAL.py, 0, 1, () => pageFace(PAGES[top], revealAt(PAGES[top], t))(c, CAL.pw, CAL.ph));
  else rrect(-CAL.pw / 2 - 20, CAL.py, CAL.pw + 40, CAL.ph + 30, 4, C.accent); // the pad's board, in the colour the cut opens on
  // the lifting sheet's shadow on the one under it
  const lift = PAGES.reduce((m, p) => { const t0 = p.i === 0 ? 3.3 : p.i === PAGES.length - 1 ? COVER[0] : TEARS[p.i]; const u = (t - t0) / (p.i === 0 ? 1.2 : FLY(p.i)); return u > 0 && u < 1 ? Math.max(m, Math.sin(u * Math.PI)) : m; }, 0);
  if (lift > 0) { const gr = c.createLinearGradient(0, CAL.py, 0, CAL.py + 260); gr.addColorStop(0, `rgba(${C.shadow},${.45 * lift})`); gr.addColorStop(1, `rgba(${C.shadow},0)`); c.fillStyle = gr; c.fillRect(-CAL.pw / 2, CAL.py, CAL.pw, 260); }
  c.restore();
  // the torn sheets, in 3D, the earliest (nearest the camera) last
  SK.view3({ x: 0, y: cam.y + drop, z: 0, d: 1600, zoom: z });
  for (let i = PAGES.length - 2; i >= 0; i--) {
    const t0 = i === 0 ? 3.3 : TEARS[i], t1 = (i === 0 ? TEARS[0] : TEARS[i]) + FLY(i);
    if (t >= t0 && t < t1) sheet3(PAGES[i], flyPose(i, t), revealAt(PAGES[i], t), t >= TEARS[i], 'sheet' + (i % 5));
  }
  // the count page tears off last and comes at the camera, turning over: its back covers the cut
  if (t >= COVER[0]) {
    const v = clamp((t - COVER[0]) / (COVER[1] - COVER[0]));
    sheet3(PAGES[PAGES.length - 1], { x: 0, y: CAL.py - 40 * v, z: -1500 * v * v * v, rx: -.3 * v, ry: Math.PI * E.inOut(v), rz: .1 * v }, revealAt(PAGES[PAGES.length - 1], t), true, 'cover');
  }
}

/* ------------------------------------------------------------------ S3: what is waiting -- the facts, pinned */
function factsLayout() { // 1, 2 or 3 torn pages that fill the wall under the title: a row when wide, a column when not
  const n = FACTS.length, top = (TALL ? 330 : 230) * U, rots = [-.03, .025, -.02];
  if (WIDE || (!TALL && n < 3)) {
    const gap = (WIDE ? 30 : 22) * U, pw = Math.min((WIDE ? 540 : n === 1 ? 660 : 480) * U, (W - (WIDE ? 130 : 80) * U - (n - 1) * gap) / n), ph = Math.min(pw * (WIDE ? 1.05 : n === 1 ? .86 : 1.22), H - top - 80 * U);
    const x0 = CX - ((n - 1) * (pw + gap)) / 2, y = top + (H - top - 10 * U) / 2;
    return FACTS.map((f, i) => ({ f, x: x0 + i * (pw + gap), y: y + (n > 1 ? (i % 2 ? 12 : -8) : 0) * U, w: pw, h: ph, rot: rots[i] }));
  }
  const gap = (TALL ? 46 : 26) * U, pw = Math.min((TALL ? 840 : 800) * U, W - 130 * U), ph = Math.min(pw * .6, (H - top - (TALL ? 140 : 60) * U - (n - 1) * gap) / n);
  const y0 = top + (H - top - (TALL ? 40 : 6) * U - (n * ph + (n - 1) * gap)) / 2 + ph / 2;
  return FACTS.map((f, i) => ({ f, x: CX + (n > 1 ? [-22, 22, -6][i] : 0) * U, y: y0 + i * (ph + gap), w: pw, h: ph, rot: rots[i] * (TALL ? 1 : .6) }));
}
function countUp(val, k) { // the value's number rolls up from nothing; its prefix and suffix stay
  const m = String(val).match(/[\d][\d,]*(\.\d+)?/); if (!m || /\d/.test(String(val).slice(m.index + m[0].length))) return val; // "2 500+", "24/7": as written
  const n = parseFloat(m[0].replace(/,/g, '')), dec = m[1] ? m[1].length - 1 : 0, v = n * k;
  let s = v.toFixed(dec); if (m[0].includes(',')) s = Number(s).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
  return val.slice(0, m.index) + s + val.slice(m.index + m[0].length);
}
function factCard(o, i, t) {
  const c = g(), pt = PIN[i], land = ease(t, pt - .34, pt, E.in);
  if (land <= 0) return;
  const after = t - pt, bounce = after > 0 ? .035 * Math.sin(after * 26) * Math.exp(-after * 9) : 0;
  const s = lerp(2.5, 1, land) * (1 - bounce), rot = o.rot * lerp(5, 1, land) + .012 * Math.sin(t * 1.3 + i * 2) * clamp(after);
  const { w, h } = o, lift = s - 1;
  SK.alpha(clamp(land * 2.5), () => withT(o.x, o.y - lift * 60 * U, rot, s, () => {
    c.save(); c.shadowColor = `rgba(${C.shadow},.55)`; c.shadowBlur = (24 + lift * 60) * U; c.shadowOffsetY = (14 + lift * 70) * U;
    c.translate(-w / 2, -h / 2); tornPath(c, w, h, 40 + i); c.fillStyle = C.paper; c.fill(); c.restore();
    c.save(); c.translate(-w / 2, -h / 2); tornPath(c, w, h, 40 + i); c.clip(); c.fillStyle = C.accent; c.fillRect(0, 0, w, h * .07); c.restore();
    const flat = h < w * .8, vmax = flat ? h * .46 : Math.min(w * .34, h * .27), vs = fit(o.f.value, w * .86, vmax, { wt: 900, ls: -2 });
    const vy = flat ? h * .07 : -h * .02;
    text(countUp(o.f.value, after > 0 ? E.out(clamp(after / .9)) : 0), 0, vy, { size: vs, wt: 900, ls: -2, col: C.ink, align: 'center' });
    rrect(-w * (flat ? .07 : .11), vy + h * (flat ? .09 : .07), w * (flat ? .14 : .22), (flat ? 8 : 10) * U, 3 * U, C.accent);
    if (o.f.label) {
      const lb = wrap(o.f.label, w * .86, flat ? Math.min(w * .05, h * .125, 34 * U) : Math.min(w * .1, h * .08, 36 * U), { wt: 800, fam: FONT.ui, ls: 1.5 }, flat ? 2 : 3);
      lb.lines.forEach((l, k) => text(l, 0, vy + h * (flat ? .27 : .2) + k * lb.size * 1.22, { size: lb.size, wt: 800, fam: FONT.ui, ls: 1.5, col: C.inkSoft, align: 'center' }));
    }
    // the pin
    const pk = outBack(clamp((t - pt) / .25)); if (pk > 0) withT(flat ? -w / 2 + 44 * U : 0, -h / 2 + (flat ? 40 : 30) * U, 0, pk, () => {
      c.save(); c.shadowColor = 'rgba(0,0,0,.4)'; c.shadowBlur = 8 * U; c.shadowOffsetY = 5 * U;
      c.fillStyle = C.deep; c.beginPath(); c.arc(0, 0, 17 * U, 0, TAU); c.fill(); c.restore();
      c.fillStyle = C.accent; c.beginPath(); c.arc(-2 * U, -2 * U, 13 * U, 0, TAU); c.fill();
      c.fillStyle = 'rgba(255,255,255,.7)'; c.beginPath(); c.arc(-6 * U, -6 * U, 4 * U, 0, TAU); c.fill();
    });
  }));
}
function scene3(t) {
  const c = g();
  screenWall(t);
  const push = 1 + .04 * E.sine(clamp((t - 10.2) / 5.8));
  c.save(); c.translate(CX, CY); c.scale(push, push); c.translate(-CX, -CY);
  const L = factsLayout();
  glow(CX, L.length ? L[0].y : CY, Math.max(W, H) * .55, .14);
  const title = COPY.facts_title, ts = fit(title, W - 140 * U, (TALL ? 76 : 62) * U, { wt: 900 }), ty = (TALL ? 230 : 150) * U, u = ease(t, S2_END - .05, S2_END + .3, E.out);
  clipRect(0, ty - ts, W, ts * 1.25, () => text(title, CX, ty + (1 - u) * ts * 1.1, { size: ts, wt: 900, col: C.light, align: 'center' }));
  rrect(CX - 50 * U * u, ty + 22 * U, 100 * U * u, 8 * U, 3 * U, C.accent);
  L.forEach((o, i) => factCard(o, i, t));
  c.restore();
}

/* ------------------------------------------------------------------ S4: the ticket and its price tag */
const TK = { w: 860, h: 400, stub: 610, hole: [735, 40], tagTop: 72 };
const TS = Math.min(W * .84 / TK.w, H * .46 / TK.h);
function ticketFace(t) {
  return (c, w, h) => {
    rrect(0, 0, w, h, 26, C.paper);
    c.save(); SK.rrPath(0, 0, w, h, 26); c.clip();
    c.fillStyle = C.black; c.fillRect(0, 0, TK.stub, 84);
    c.fillStyle = C.deep; c.fillRect(TK.stub, 0, w - TK.stub, 84);
    const strip = TICKET.badge || EV.url;
    c.fillStyle = C.accent; c.fillRect(0, 316, TK.stub, h - 316);
    c.restore();
    lockup(30, 24, 36, -99, t, { maxW: TK.stub - 190 });
    text(EV.year, TK.stub - 30, 60, { size: 40, wt: 900, col: C.second, align: 'right' });
    const fields = [[COPY.dates_label, EV.dates_long || EV.dates], [COPY.city_label, EV.city], [COPY.venue_label, EV.venue]].filter((f) => f[1]);
    if (fields.length > 2 && fields.reduce((n, f) => n + String(f[1]).length, 0) > 44) fields.splice(1, 1); // a long venue: the city is on the end card
    const rows = fields.reduce((n, f) => n + String(f[1]).length, 0) > 36 && fields.length > 1; // long values: a row each, its label before it
    if (TICKET.name) text(TICKET.name, 30, rows ? 152 : 172, { size: fit(TICKET.name, TK.stub - 60, rows ? 60 : 76, { wt: 900 }), wt: 900, col: C.ink });
    const reveal = (i) => ease(t, TICKET_IN + .45 + i * .12, TICKET_IN + .75 + i * .12, E.out);
    if (rows) {
      const lw = Math.max(...fields.map((f) => (f[0] ? measure(f[0], { size: 17, wt: 800, fam: FONT.ui, ls: 3 }) : 0))) + 22;
      fields.slice(0, 2).forEach(([k, v], i) => {
        const y = 222 + i * 52, r = reveal(i), vs = fit(v, TK.stub - 60 - lw, 34, { wt: 800 });
        if (k) SK.alpha(r, () => text(k, 30, y - 2, { size: 17, wt: 800, fam: FONT.ui, ls: 3, col: C.inkSoft }));
        clipRect(30 + lw - 4, y - 40, (TK.stub - 60 - lw + 4) * r, 54, () => text(v, 30 + lw, y, { size: vs, wt: 800, col: C.ink }));
      });
    } else {
      const wsum = fields.reduce((n, f) => n + Math.max(8, String(f[1]).length), 0), cws = fields.map((f) => (TK.stub - 60) * Math.max(8, String(f[1]).length) / wsum);
      const xs = cws.map((_, i) => 30 + cws.slice(0, i).reduce((a, b) => a + b, 0));
      fields.forEach(([k, v], i) => {
        const x = xs[i], cw = cws[i], r = reveal(i);
        if (k) SK.alpha(r, () => text(k, x, 226, { size: fit(k, cw - 18, 19, { wt: 800, fam: FONT.ui, ls: 3 }), wt: 800, fam: FONT.ui, ls: 3, col: C.inkSoft }));
        clipRect(x - 4, 236, (cw + 4) * r, 50, () => text(v, x, 272, { size: fit(v, cw - 18, 36, { wt: 800 }), wt: 800, col: C.ink }));
      });
    }
    if (strip) text(strip, 30, 372, { size: fit(strip, TK.stub - 60, 40, { wt: 900 }), wt: 900, col: C.light });
    // the perforation, the notches, the punched hole, the barcode
    c.save(); c.globalCompositeOperation = 'destination-out';
    c.beginPath(); c.arc(TK.stub, 0, 20, 0, TAU); c.arc(TK.stub, h, 20, 0, TAU); c.fill();
    c.beginPath(); c.arc(TK.hole[0], TK.hole[1], 9, 0, TAU); c.fill(); c.restore();
    c.strokeStyle = `rgba(${rgbOf(C.ink).join(',')},.35)`; c.lineWidth = 3; c.setLineDash([9, 9]); c.beginPath(); c.moveTo(TK.stub, 100); c.lineTo(TK.stub, h - 26); c.stroke(); c.setLineDash([]);
    for (let i = 0; i < 40; i++) { const bw = 2 + Math.floor(rnd(i * 7 + 3) * 3) * 2; c.fillStyle = C.ink; c.fillRect(TK.stub + 30 + i * 4.8, 326, rnd(i * 5 + 1) > .35 ? bw * .8 : 1.6, 52); }
    c.strokeStyle = C.inkSoft; c.lineWidth = 2.5; c.beginPath(); c.moveTo(TK.hole[0], TK.hole[1]); c.lineTo(TK.hole[0] + Math.sin(t * 2.4) * 4, TK.tagTop + 10); c.stroke();
  };
}
function tagFace(front) {
  return (c, w, h) => {
    c.save(); SK.rrPath(0, 0, w, h, 16); c.clip();
    c.fillStyle = front ? C.paper : C.black; c.fillRect(0, 0, w, h);
    c.fillStyle = front ? C.accent : C.second; c.fillRect(0, h - 40, w, 40);
    c.restore();
    c.strokeStyle = front ? C.paperEdge : C.groundLt; c.lineWidth = 3; SK.rrPath(1.5, 1.5, w - 3, h - 3, 15); c.stroke();
    c.save(); c.globalCompositeOperation = 'destination-out'; c.beginPath(); c.arc(w / 2, 22, 10, 0, TAU); c.fill(); c.restore();
    const lab = front ? COPY.today : COPY.next_label, price = front ? TICKET.price_now : TICKET.price_next;
    if (lab) text(lab, w / 2, 84, { size: fit(lab, w - 30, 22, { wt: 800, fam: FONT.ui, ls: 3 }), wt: 800, fam: FONT.ui, ls: 3, col: front ? C.deep : C.soft, align: 'center' });
    const ps = fit(price, w - 26, 104, { wt: 900, ls: -2 });
    text(price, w / 2, 150 + ps * .36, { size: ps, wt: 900, ls: -2, col: front ? C.ink : C.light, align: 'center' });
  };
}
function scene4(t) {
  const c = g();
  screenWall(t);
  const tyc = CY + (TICKET.deadline ? 10 : 46) * U, hh = TK.h * TS / 2;
  const flipK = TICKET.price_now && TICKET.price_next ? ease(t, FLIP - .3, FLIP + .25, E.inOut) : 0, zoom = 1 + .045 * flipK; // the flip is the event here: a push toward the tag
  glow(CX, tyc, Math.max(W, H) * .5, .16);
  const title = COPY.ticket_title, ts = fit(title, W - 140 * U, (TALL ? 74 : 60) * U, { wt: 900 }), ty = tyc - hh - 64 * U, u = ease(t, TICKET_IN + .25, TICKET_IN + .6, E.out);
  if (title) clipRect(0, ty - ts, W, ts * 1.25, () => text(title, CX, ty + (1 - u) * ts * 1.1, { size: ts, wt: 900, col: C.light, align: 'center' }));
  // the ticket turns in, then drifts
  const up = ease(t, TICKET_IN - .05, TICKET_IN + .7, outBackSoft), dr = Math.max(0, t - TICKET_IN - .7);
  SK.view3({ d: 1700 });
  const pose = { x: CX, y: tyc + Math.sin(dr * 1.5) * 5 * U, z: 0, rx: lerp(.5, .1, up) + .03 * Math.sin(dr * 1.1), ry: lerp(-.9, -.08, up) + .05 * Math.sin(dr * .8), rz: lerp(.14, -.03, up), s: TS * zoom };
  const L = (x, y, z = 0) => SK.pose3([x - TK.w / 2, y - TK.h / 2, z], pose);
  const P = [L(0, 0), L(TK.w, 0), L(TK.w, TK.h), L(0, TK.h)];
  const Sh = P.map((p) => SK.proj3([p[0] + 30 * U, p[1] + 56 * U, p[2] + 60]));
  if (Sh.every(Boolean)) { c.save(); c.filter = `blur(${26 * U}px)`; poly(Sh, `rgba(${C.shadow},.6)`); c.restore(); }
  SK.face3(P, TK.w, TK.h, ticketFace(t), { key: 'ticket', cull: false, shade: .6 * (1 - SK.lit3(P, { light: [-.3, -1, -.6], ambient: .82 })) });
  // the price tag hangs from the stub, swings, and flips to the next price
  if (TICKET.price_now) {
    const tw = 232, th = 292, f = TICKET.price_next ? Math.PI * ease(t, FLIP - .15, FLIP + .25, outBackSoft) : 0;
    const sw = .05 * Math.sin(t * 2.4) + (t > FLIP ? .12 * Math.sin((t - FLIP) * 9) * Math.exp(-(t - FLIP) * 3) : 0);
    const tagIn = ease(t, TICKET_IN + .75, TICKET_IN + 1.1, outBack) * (1 + .12 * flipK);
    const corner = (lx, ly) => {
      const x = lx * Math.cos(sw) - ly * Math.sin(sw), y = lx * Math.sin(sw) + ly * Math.cos(sw);
      return L(TK.hole[0] + x * Math.cos(f) * tagIn, TK.tagTop + y * tagIn - 22, -10 - x * Math.sin(f) * tagIn);
    };
    const front = [corner(-tw / 2, 0), corner(tw / 2, 0), corner(tw / 2, th), corner(-tw / 2, th)];
    const isFront = Math.cos(f) >= 0, Q = isFront ? front : [front[1], front[0], front[3], front[2]];
    if (tagIn > .02) SK.face3(Q, tw, th, tagFace(isFront), { key: 'tag', cull: false, shade: .45 * Math.abs(Math.sin(f)) });
  }
  // the deadline, big, under it
  if (TICKET.deadline) {
    const ds = fit(TICKET.deadline, W - 140 * U, (TALL ? 92 : 74) * U, { wt: 900 }), dy = tyc + hh + 64 * U + ds * .72, k = ease(t, DEAD, DEAD + .3, outBack);
    if (k > 0) withT(CX, dy - ds * .36, -.025, lerp(1.7, 1, k), () => SK.alpha(clamp(k * 3), () => text(TICKET.deadline, 0, ds * .36, { size: ds, wt: 900, col: C.second, align: 'center' })));
  }
}

/* ------------------------------------------------------------------ S5: the end -- the month, the first day circled */
const GRID = { w: 600, band: 64, wk: 124, row: 56 };
GRID.h = GRID.wk + MONTH.rows * GRID.row + 16;
function endLayout() {
  if (WIDE) {
    const cw = Math.min(W * .4, (H - 160 * U) * GRID.w / GRID.h), cs = cw / GRID.w, rx = W * .7, colW = W * .42;
    return { card: [W * .29 - cw / 2, CY - GRID.h * cs / 2, cs], lock: [rx, CY - 250 * U, 64 * U], dates: [rx, CY - 70 * U, 64 * U, colW], city: [rx, CY - 8 * U, 32 * U], btn: [rx, CY + 140 * U, 100 * U], link: [rx, CY + 262 * U, 30 * U] };
  }
  const k = TALL ? 1.3 : 1, place = EV.venue || EV.city;
  const list = (cw) => [['lock', 62 * k], ['gap', 40 * k], ['card', GRID.h * cw / GRID.w / U], ['gap', 62 * k], ['dates', 52 * k], ...(place ? [['gap', 20 * k], ['city', 30 * k]] : []),
    ...(COPY.cta ? [['gap', 50 * k], ['btn', 96 * k]] : []), ...(EV.url ? [['gap', 40 * k], ['link', 28 * k]] : [])];
  let cw = Math.min(W - 150 * U, (TALL ? 900 : 700) * U); const tot = (w) => list(w).reduce((s, it) => s + it[1] * U, 0);
  while (tot(cw) > H - 130 * U && cw > 300 * U) cw *= .97;
  const cs = cw / GRID.w, items = list(cw);
  let y = (H - items.reduce((s, it) => s + it[1] * U, 0)) / 2; const pos = {};
  for (const [n, hgt] of items) { pos[n] = [y, hgt * U]; y += hgt * U; }
  for (const n of ['city', 'btn', 'link']) pos[n] = pos[n] || [0, 0];
  return { card: [CX - cw / 2, pos.card[0], cs], lock: [CX, pos.lock[0], pos.lock[1]], dates: [CX, pos.dates[0] + pos.dates[1], 56 * k * U, W - 140 * U], city: [CX, pos.city[0] + pos.city[1], 32 * k * U], btn: [CX, pos.btn[0] + pos.btn[1] / 2, pos.btn[1]], link: [CX, pos.link[0] + pos.link[1], 30 * k * U] };
}
function monthCard(x, y, s, t) {
  const c = g(), w = GRID.w, cw = w / 7;
  withT(x, y, 0, s, () => {
    c.save(); c.shadowColor = `rgba(${C.shadow},.6)`; c.shadowBlur = 40; c.shadowOffsetY = 20; rrect(0, 0, w, GRID.h, 14, C.paper); c.restore();
    c.save(); SK.rrPath(0, 0, w, GRID.h, 14); c.clip(); c.fillStyle = C.accent; c.fillRect(0, 0, w, GRID.band); c.restore();
    const mh = `${COPY.months[FIRST.m]} ${FIRST.y}`;
    text(mh, w / 2, 45, { size: fit(mh, w - 60, 32, { wt: 800, ls: 6 }), wt: 800, ls: 6, col: C.light, align: 'center' });
    for (let k = 0; k < 7; k++) text(COPY.weekdays[(k + WS) % 7], (k + .5) * cw, 104, { size: 20, wt: 800, fam: FONT.ui, col: C.inkSoft, align: 'center' });
    const cell = (d) => { const n = MONTH.lead + d - 1; return [(n % 7 + .5) * cw, GRID.wk + Math.floor(n / 7) * GRID.row + GRID.row / 2]; };
    // the event's days after the first, a band of the bright green behind them
    const hl = ease(t, CIRCLE + .3, CIRCLE + .65, E.out);
    if (hl > 0 && sameMonth(LASTD)) for (let d = FIRST.d + 1; d <= LASTD.d; d++) {
      const [cx, cy] = cell(d), u = clamp(hl * (LASTD.d - FIRST.d) - (d - FIRST.d - 1));
      if (u > 0) rrect(cx - cw / 2 - 2, cy - 22, (cw + 4) * u, 44, 8, C.second);
    }
    for (let d = 1; d <= MONTH.days; d++) {
      const [cx, cy] = cell(d), k = ease(t, 20.95 + d * .014, 21.25 + d * .014, outBack); if (k <= 0) continue;
      const past = sameMonth(TODAY) && d < TODAY.d, first = d === FIRST.d;
      withT(cx, cy, 0, k, () => {
        if (sameMonth(TODAY) && d === TODAY.d) { c.strokeStyle = C.ink; c.lineWidth = 2.5; SK.rrPath(-26, -22, 52, 44, 8); c.stroke(); }
        text(String(d), 0, 11, { size: 30, wt: first ? 900 : 700, col: first ? C.deep : C.ink, align: 'center', alpha: past ? .3 : 1 });
      });
    }
    // the first day, circled by hand: an overshooting loop that draws itself, pulsing on the last chord
    const cp = ease(t, CIRCLE, CIRCLE + .45, E.inOut);
    if (cp > 0) {
      const [cx, cy] = cell(FIRST.d), pulse = t > LAST ? 1 + .08 * Math.sin((t - LAST) * 14) * Math.exp(-(t - LAST) * 4) : 1;
      c.save(); c.translate(cx, cy); c.scale(pulse, pulse); c.strokeStyle = C.accent; c.lineWidth = 6.5; c.lineCap = 'round'; c.beginPath();
      const a0 = -2.2, span = (TAU + .5) * cp;
      for (let k = 0; k <= 60; k++) { const a = a0 + span * k / 60, r = 1 + .06 * Math.sin(a * 2 + 1); c.lineTo(Math.cos(a) * 40 * r, Math.sin(a) * 31 * r - 1); }
      c.stroke(); c.restore();
    }
  });
}
function button(x, y, h, t) {
  const k = ease(t, BUTTON, BUTTON + .4, outBack); if (k <= 0 || !COPY.cta) return;
  const fs = h * .46, bw = Math.max(h * 4.4, measure(COPY.cta, { size: fs, wt: 900 }) + h * 1.9), pulse = 1 + .015 * Math.sin((t - BUTTON) * 4.4);
  withT(x, y, 0, k * pulse, () => {
    rrect(-bw / 2, -h / 2 + h * .08, bw, h, h / 2, C.deep);
    rrect(-bw / 2, -h / 2, bw, h, h / 2, C.accent);
    text(COPY.cta, -h * .3, fs * .36, { size: fs, wt: 900, col: C.light, align: 'center' });
    arrow(bw / 2 - h * .62 + Math.max(0, Math.sin(t * 5)) * h * .06, 0, h / 100, C.light);
    const sh = (t - LAST) / .5; // a glint on the last chord
    if (sh > 0 && sh < 1) { // a soft band of light, never a hard shape over the words
      const c = g(); c.save(); SK.rrPath(-bw / 2, -h / 2, bw, h, h / 2); c.clip(); const gx = -bw / 2 + sh * (bw + h * 3) - h * 1.5, gr = c.createLinearGradient(gx - h * .9, 0, gx + h * .9, 0);
      gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.5, `rgba(255,255,255,${.22 * Math.sin(sh * Math.PI)})`); gr.addColorStop(1, 'rgba(255,255,255,0)');
      c.fillStyle = gr; c.fillRect(-bw / 2, -h, bw, h * 2); c.restore();
    }
  });
}
function scene5(t) {
  const c = g(), L = endLayout();
  screenWall(t);
  const push = 1 + .03 * E.sine(clamp((t - 21) / 5));
  c.save(); c.translate(CX, CY); c.scale(push, push); c.translate(-CX, -CY);
  glow(L.card[0] + GRID.w * L.card[2] / 2, L.card[1] + GRID.h * L.card[2] / 2, Math.max(W, H) * .45, .12);
  const [lx, ly, lh] = L.lock, lmax = W * (WIDE ? .4 : .8);
  lockup(lx - lockupPlan(lh, lmax).w / 2, ly, lh, 21.05, t, { maxW: lmax });
  monthCard(L.card[0], L.card[1], L.card[2], t);
  const [dx, dy, dmax, dwid] = L.dates, ds = fit(EV.dates_long || EV.dates, dwid, dmax, { wt: 900 }), du = ease(t, 21.3, 21.65, E.out);
  clipRect(0, dy - ds, W, ds * 1.25, () => text(EV.dates_long || EV.dates, dx, dy + (1 - du) * ds * 1.1, { size: ds, wt: 900, col: C.light, align: 'center' }));
  const place = [EV.venue, EV.city].filter(Boolean).join(' · '), [cx2, cy2, cmax] = L.city, cs = fit(place, dwid, cmax, { wt: 800, fam: FONT.ui, ls: 5 });
  if (place) SK.alpha(ease(t, 21.45, 21.8), () => text(place, cx2, cy2, { size: cs, wt: 800, fam: FONT.ui, ls: 5, col: C.second, align: 'center' }));
  button(L.btn[0], L.btn[1], L.btn[2], t);
  if (EV.url) {
    const [kx, ky, ksz] = L.link, lsz = fit(EV.url, dwid, ksz, { wt: 600, fam: FONT.ui, ls: 1 });
    SK.alpha(ease(t, 22.4, 22.7), () => text(EV.url, kx, ky, { size: lsz, wt: 600, fam: FONT.ui, ls: 1, col: C.soft, align: 'center' }));
  }
  c.restore();
}

/* ------------------------------------------------------------------ the cuts and the film */
function whip(t, t0, t1, a, b, axis = 'x') { // a whip pan from scene a to scene b
  const u = clamp((t - t0) / (t1 - t0)), e = E.inOut(u), smear = Math.sin(u * Math.PI) * 200 * U, X = axis === 'x';
  if (u < 1) SK.fx(() => a(t), { key: 'wa', dx: X ? -e * W : 0, dy: X ? 0 : -e * H, smear, angle: X ? 0 : Math.PI / 2 });
  if (u > 0) SK.fx(() => b(t), { key: 'wb', dx: X ? (1 - e) * W : 0, dy: X ? 0 : (1 - e) * H, smear, angle: X ? 0 : Math.PI / 2 });
}
function draw(t) {
  const c = g();
  const next = FACTS.length ? scene3 : scene4;
  const CUT = S2_END - .12; // the count page's back has filled the frame by now
  if (t < CUT) scene12(t);
  else if (t < SWAP[0] || (!FACTS.length && t < END[0])) {
    next(t);
    // the count page's back fills the frame for a blink, then flies on up past the camera: the next scene is under it
    const u = clamp((t - CUT) / .27);
    if (u < 1) {
      const e = u * (.5 + .5 * u), D2 = Math.hypot(W, H);
      c.save(); c.translate(CX, CY - e * (H + D2 * .2)); c.rotate(-.1 * e);
      c.shadowColor = `rgba(${C.shadow},.55)`; c.shadowBlur = 60 * U; c.shadowOffsetY = 30 * U;
      c.fillStyle = C.accent; c.beginPath(); c.moveTo(-D2, -D2 * 2); c.lineTo(D2, -D2 * 2); c.lineTo(D2, H * .505);
      for (let x = D2, k = 0; x >= -D2; x -= 22 * U, k++) c.lineTo(x, H * .505 + (rnd(k * 13 + 2) - .5) * 16 * U); // its torn edge
      c.closePath(); c.fill(); c.restore();
    }
  } else if (t < SWAP[1] && FACTS.length) whip(t, SWAP[0], SWAP[1], scene3, scene4);
  else if (t < END[0]) scene4(t);
  else if (t < END[1]) whip(t, END[0], END[1], scene4, scene5, 'y');
  else scene5(t);
}

/* ------------------------------------------------------------------ the sound
   Worked out from the clock above and from the content: a 120 bpm groove in F minor from a chord chart,
   four-on-the-floor from the first frame; it builds under the tears (quarters, eighths, sixteenths)
   into the count on the bar line, fills into the facts, the ticket and the end; a synth-brass stab on
   every hit, and a last chord at LAST. */
const BPM = 120, beat = (t) => t * BPM / 60;
const gf = (x) => String(+x.toPrecision(6));
function scoreData() {
  const CHART = [
    ['F1', 'F2', 'Ab3+C4+F4', 'F3+Ab3+C4+Eb4'], ['Db2', 'Db3', 'Ab3+Db4+F4', 'Db3+F3+Ab3+C4'],
    ['Ab1', 'Ab2', 'Ab3+C4+Eb4', 'Ab3+C4+Eb4+G4'], ['Eb2', 'Eb3', 'G3+Bb3+Eb4', 'Eb3+G3+Bb3+Db4'],
  ];
  const BARS = Math.round(SK._film.duration / (240 / BPM));
  const HITS = [...new Set([TEARS[0], LAND, S2_END, TICKET_IN, ...(TICKET.price_now && TICKET.price_next ? [FLIP] : []), END_IN, CIRCLE])].map(beat);
  const FINAL = beat(LAST);
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', openhat: '..x...x...x...x.', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
  const FULL = { ...GROOVE, rim: '...o..o....o..o.' };
  const DRUMS = [
    { ...GROOVE, hat: 'oooooooooooooooo' },                                                    // 0: the calendar drops in
    { ...GROOVE, snare: '..........ooxxxX', openhat: '..x...x...x.....' },                       // 1: today; a roll into the first tear
    { ...GROOVE, kick: 'X...x...x...x...' },                                                   // 2: the tears, a quarter apart
    { kick: 'x...x...x...x...', hat: 'oooooooooooooooo', snare: 'o.o.o.o.ooooxxXX', clap: '....x.......' }, // 3: eighths, sixteenths
    { ...FULL, kick: 'X...x...x...x...', snare: '............oxxX' },                          // 4: the count; a fill into the facts
    FULL, FULL,                                                                                // 5-6: the pins
    { ...FULL, snare: '............oxxX' },                                                    // 7: into the ticket
    GROOVE,                                                                                    // 8: the ticket
    { ...GROOVE, kick: 'X...x...x...x...' },                                                   // 9: the flip
    { ...GROOVE, kick: 'x.......X...x...', snare: '....oxxX........' },                         // 10: into the end
    { ...FULL, snare: '............oxxX' },                                                    // 11: the circle; a fill into the last chord
    { kick: 'X...............', openhat: 'x...............' },                                 // 12: the last chord
  ];
  const KIT_GAINS = { kick: 1.15, snare: .42, clap: .42, hat: .26, openhat: .16, shaker: .2, rim: .45 };
  const QUIET = { 1: [3.5, 4], 3: [3.5, 4] }; // bar -> beats with no bass or stabs: a breath before the tear and the count
  const bass = [], sub = [], pad = [], keys = [], brass = [];
  for (let bar = 0; bar < BARS - 1; bar++) {
    const [root, octv, stab, chord] = CHART[bar % 4], b0 = bar * 4, quiet = QUIET[bar];
    for (let k = 0; k < 8; k++) {
      const b = k * .5; if (quiet && quiet[0] <= b && b < quiet[1]) continue;
      bass.push(`${gf(b0 + b)} ${k % 2 ? octv : root} .42 ${(k % 2 ? .52 : .62).toFixed(2)}`);
      if (k % 2) sub.push(`${gf(b0 + b - .02)} ${root} .4 .8`);
    }
    for (const k of [.5, 1.5, 2.5, 3.5]) { if (quiet && quiet[0] <= k && k < quiet[1]) continue; keys.push(`${gf(b0 + k)} ${stab} .3 ${(k === 1.5 || k === 3.5 ? .34 : .26).toFixed(2)}`); }
    if (bar >= 2) pad.push(`${gf(b0)} ${chord} 4 .3`);
  }
  for (const b of HITS) brass.push(`${gf(b)} ${CHART[Math.floor(b / 4) % 4][2]} .9 .62`);
  bass.push(`${gf(FINAL)} F1 4 .7`); sub.push(`${gf(FINAL)} F1 4 .9`);
  pad.push(`${gf(FINAL)} F3+Ab3+C4+F4+C5 4 .5`); keys.push(`${gf(FINAL)} F3+Ab3+C4+F4 3 .5`); brass.push(`${gf(FINAL)} F4+Ab4+C5 2 .7`);
  const run = (b0) => 'F5 Ab5 C6 Eb6 F6 Ab6 C7 Eb7 F7'.split(' ').map((n, i) => `${(b0 + i * .09).toFixed(3)} ${n} .6 ${(.3 + i * .03).toFixed(2)}`).join('; ');
  const events = [
    { inst: 'synth_bass_1', vel: .9, notes: bass.join('; '), humanize: false },
    { inst: 'sub_bass', vel: 1.0, notes: sub.join('; '), humanize: false },
    { inst: 'electric_piano_1', vel: .8, notes: keys.join('; ') },
    { inst: 'pad_3_polysynth', vel: .6, notes: pad.join('; ') },
    { inst: 'synth_brass_1', vel: .8, notes: brass.join('; ') },
    { inst: 'glockenspiel', vel: .5, notes: run(beat(.48)) + '; ' + run(beat(CIRCLE)) },
  ];
  DRUMS.forEach((kit, bar) => events.push({ type: 'drums', from: bar * 4, bars: 1, steps: 16, vel: .85, kit, gains: KIT_GAINS }));
  return {
    bpm: BPM, drum_gain: .62,
    instruments: {
      synth_bass_1: { g: .62, pan: 0, send: .04, rel: .12 }, sub_bass: { g: .5, pan: 0, send: 0, rel: .05 },
      electric_piano_1: { g: .26, pan: -.22, send: .3, rel: .25 }, pad_3_polysynth: { g: .17, pan: 0, send: .5, rel: .8, soft_attack: true },
      synth_brass_1: { g: .22, pan: .12, send: .35, rel: .35 }, glockenspiel: { g: .16, pan: .3, send: .45, rel: 1.0 },
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
  const impact = (t, db = -12) => { add(t, 'boom', db, { sec: 1.1 }); add(t, 'crash', db - 14, { sec: 1.8 }, { send: .3 }); };
  // 1. the calendar drops onto its nail; the logo, the date, TODAY
  add(0, 'boom', -15, { sec: .9 }); add(0, 'swoosh_soft', -21, { sec: .5 }); add(.42, 'thunk', -19, { sec: .3 });
  for (let i = 0; i < 3; i++) add(.05 + i * .08, 'pop', -24, { f0: 600 + i * 150, f1: 220, sec: .08 }, { pan: -.3 + i * .1 });
  add(.1, 'zip', -28, { sec: .3, f0: 600, f1: 2600 });
  add(.02, 'pop', -17, { f0: 700, f1: 200, sec: .11 }); add(.22, 'keys', -30, { sec: .3, rate: 20 });
  add(2.0, 'pop', -22, { f0: 900, f1: 300, sec: .08 }, { pan: .4 });
  add(3.3, 'crinkle', -29, { sec: .65, dens: 120, seed: 3 });
  // 2. the tears: a rip and a pass-by each, quieter as they come faster
  TEARS.forEach((tt, i) => {
    const side = i % 2 ? .45 : -.45, k = Math.min(9, i * .8);
    add(tt, 'crinkle', -15 - k, { sec: i ? .18 : .32, dens: 320, seed: 5 + i }, { pan: side * .4 });
    add(tt + .06, 'whoosh', -19 - k, { sec: .45, f0: 300, f1: 3400, peak: .6 }, { pan: side });
  });
  impact(LAND, -11);
  add(LAND + .12, 'zip', -24, { sec: .3, f0: 500, f1: 2600 }); add(LAND + .5, 'blip', -27, { f: 1175, sec: .09 });
  // the count page tears off at the camera
  add(COVER[0] - .05, 'crinkle', -15, { sec: .3, dens: 300, seed: 21 });
  add(COVER[0], 'whoosh', -11, { sec: .5, f0: 200, f1: 4200, peak: .85, curve: 1.4 });
  impact(S2_END, -14);
  // 3. the facts, pinned; their numbers roll up
  if (FACTS.length) {
    add(10.12, 'swoosh_soft', -22, { sec: .4 });
    FACTS.forEach((f, i) => {
      const pan = (i - (FACTS.length - 1) / 2) * .4;
      add(PIN[i] - .3, 'whoosh', -22, { sec: .35, f0: 500, f1: 2000, peak: .5 }, { pan });
      add(PIN[i], 'thunk', -13, { sec: .3 }, { pan }); add(PIN[i] + .02, 'click', -18, { sec: .012, lo: 900, hi: 3500 }, { pan });
      const c = add(PIN[i] + .08, 'tick', -33, {}, { pan }); c.times = Array.from({ length: 13 }, (_, k) => r(PIN[i] + .08 + k * .065, 3));
    });
    add(SWAP[0] - .05, 'whoosh', -12, { sec: .5, f0: 200, f1: 4500, peak: .55, curve: 1.2 });
  }
  // 4. the ticket and its tag
  add(TICKET_IN, 'thunk', -18, { sec: .3 }); add(TICKET_IN + .25, 'swoosh_soft', -24, { sec: .35 });
  for (let i = 0; i < 3; i++) add(TICKET_IN + .45 + i * .12, 'keys', -31, { sec: .2, rate: 22 });
  if (TICKET.price_now) add(TICKET_IN + .8, 'pop', -22, { f0: 640, f1: 220, sec: .09 }, { pan: .3 });
  if (TICKET.price_next) { add(FLIP - .15, 'whoosh', -19, { sec: .35, f0: 600, f1: 3000, peak: .5 }, { pan: .3 }); add(FLIP + .05, 'zip', -21, { sec: .25, f0: 700, f1: 2800 }, { pan: .3 }); }
  if (TICKET.deadline) { add(DEAD, 'thunk', -12, { sec: .4 }); add(DEAD, 'boom', -20, { sec: .6 }); }
  // 5. the end: the month, the circle, the button
  add(END[0] - .05, 'whoosh', -13, { sec: .45, f0: 250, f1: 4200, peak: .7 });
  impact(END_IN, -15);
  const dc = add(21.0, 'tick', -32); dc.times = Array.from({ length: 10 }, (_, k) => r(21.0 + k * .045, 3));
  add(21.3, 'keys', -30, { sec: .3, rate: 20 });
  add(CIRCLE, 'scribble', -19, { sec: .45, seed: 4, dens: 1.2 });
  add(CIRCLE + .3, 'zip', -25, { sec: .3, f0: 700, f1: 2400 });
  add(BUTTON, 'pop', -17, { f0: 500, f1: 160, sec: .12 }); add(BUTTON + .02, 'blip', -25, { f: 988, sec: .1 });
  add(LAST, 'crash', -21, { sec: 2.2 }, { send: .4 }); add(LAST + .05, 'shimmer', -27, { sec: .6, f0: 1500, f1: 5000 });
  return cues.sort((a, b) => a.t - b.t);
}

SK.film({
  duration: 26.0,
  camera: SK.camera([[0, [W / 2, H / 2, 1]]]),
  handheld: false,
  speedLines: false,
  fadeOut: 0,
  draw,
  sound: { score: scoreData, sfx: sfxData },
});
