// For: people who follow a conference on social feeds -- one of its speakers as a collectible trading card; bold, bright, punchy
/* A speaker trading card in 26 s, with no narration: the music carries it. This film is a template: every
   word, colour, logo and person is in content.json (SK.DATA.content), nothing of the event or the speaker
   is in the code. The frame is the manifest's: 1080 x 1080 for a feed (the card fills it, and the camera
   reads it in two stops), 1920 x 1080 for YouTube (the card on the left, the talk set large on the right).

   Beats: a foil booster pack wobbles and tears open; the card shoots out face down, spins in 3D and lands
   face up under a holographic shine; the card is read; it tilts in 3D with sparks; it drops into the middle
   slot of a binder page of face-down cards, then the event's own logo, line and address.
   The clock below is the one home of the timing: the score and every sound cue are worked out from it
   (SK.film({sound})). The 3D card is sketch/space.js: SK.face3 lays the 2D card onto its four corners. */
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, TAU = SK.TAU, rnd = SK.rnd;
const CX = W / 2, CY = H / 2, WIDE = W / H > 1.3, TALL = H / W > 1.3;
const D = SK.DATA.content;

/* ------------------------------------------------------------------ the palette */
function rgbOf(hex) { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function hslOf(hex) {
  const [r, g2, b] = rgbOf(hex).map((v) => v / 255), mx = Math.max(r, g2, b), mn = Math.min(r, g2, b), l = (mx + mn) / 2;
  if (mx === mn) return [0, 0, l];
  const d = mx - mn, s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
  const h = mx === r ? (g2 - b) / d + (g2 < b ? 6 : 0) : mx === g2 ? (b - r) / d + 2 : (r - g2) / d + 4;
  return [h / 6, s, l];
}
function withL(hex, l, sk = 1) {
  const [h, s0] = hslOf(hex), s = clamp(s0 * sk), L = clamp(l);
  const q = L < .5 ? L * (1 + s) : L + s - L * s, p = 2 * L - q;
  const ch = (x) => { x = (x + 1) % 1; return x < 1 / 6 ? p + (q - p) * 6 * x : x < .5 ? q : x < 2 / 3 ? p + (q - p) * (2 / 3 - x) * 6 : p; };
  return '#' + [ch(h + 1 / 3), ch(h), ch(h - 1 / 3)].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
}
function palette(p) {
  const ground = p.ground, g0 = hslOf(ground)[2], a = p.accent, a0 = hslOf(a)[2], s2 = p.second, s0 = hslOf(s2)[2];
  const d = {
    light: '#F4F1EC', paper: '#FBF8F2',
    groundDk: withL(ground, g0 * .65), groundMid: withL(ground, g0 * 1.63), groundLt: withL(ground, g0 * 2.3),
    accentDk: withL(a, a0 * .75), accentLt: withL(a, Math.min(.85, a0 * 1.55)),
    secondDk: withL(s2, s0 * .73), secondLt: withL(s2, Math.min(.85, s0 * 1.9)), soft: withL(ground, .72, .3),
  };
  d.shadow = rgbOf(withL(ground, g0 * .3)).join(',');
  const out = { ...d, ...p };
  out.ink = out.ground; out.groundRGB = rgbOf(out.ground).join(',');
  return out;
}
const C = palette(D.palette);
SK.setStyle('clean', { grain: .5, vignette: .22, handheld: 0, vignetteRGB: C.shadow });
Object.assign(SK.C, { paper: C.ground, text: C.light, textSoft: C.soft, accent: C.accent, accentText: C.accent, ink: C.ink });
const FONT = { cond: '"Sofia Sans Condensed"', wide: '"Sofia Sans"', ui: '"Inter", "Sofia Sans"', ...(D.fonts || {}) }; // the second face carries the scripts the first lacks

/* ------------------------------------------------------------------ the words */
const EV = D.event || {};
const words = (str) => String(str ?? '').replace(/\{(\w+)\}/g, (_, k) => EV[k] ?? '');
const COPY = Object.fromEntries(Object.entries(D.copy || {}).map(([k, v]) => [k, words(v)]));
const UP = (s) => String(s ?? '').toUpperCase();
const SP = D.speaker || {}, TALK = D.talk || {}, TRACK = D.track && D.track.name ? D.track : null, RAR = D.rarity || {};
const GOLD = RAR.border || ['#F8E39A', '#D9AE48', '#A87A24'];
const INITIALS = String(SP.name ?? '').replace(/^(dr|prof|mr|mrs|ms)\.?\s+/i, '').split(/[\s]+/).filter(Boolean).map((w) => w[0]).filter((ch, i, a) => i === 0 || i === a.length - 1).join('').toUpperCase();
const NAME = UP(SP.name), ROLE = UP([SP.role, SP.org].filter(Boolean).join(', '));
const DAY = UP([TALK.day, TALK.date].filter(Boolean).join(' '));
const STATS = [DAY, UP(TALK.start), UP(TALK.stage)].filter(Boolean);        // the card's stats line
const WHEN = TALK.start ? UP(TALK.end ? `${TALK.start} – ${TALK.end}` : TALK.start) : '';
const CHIPS = [DAY, WHEN, UP(TALK.stage)].filter(Boolean);                     // the wide frame's talk details
const EMBLEM = SP.emblem && (SP.emblem.image || SP.emblem.light), LOGOTYPE = SP.logo && (SP.logo.light || SP.logo.image);

/* ------------------------------------------------------------------ the clock (120 bpm: a beat .5 s, a bar 2 s) */
const TEAR = [2.85, 3.3], OUT = 4.0, LANDT = 6.0, STOPS = [10.0, 12.0, 14.0], SPARK = 18.0;
const TILT = [17.0, 20.8], SLOT = [20.8, 22.0], RECEDE = [23.2, 23.9], LAST = 24;
const SHINES = [6.15, 12.0, 16.0];

/* ------------------------------------------------------------------ small helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (t) => { const c3 = k + 1; return 1 + c3 * Math.pow(t - 1, 3) + k * Math.pow(t - 1, 2); };
const outBack = back(1.5), outBackSoft = back(.9);
function font(size, wt = 900, fam = FONT.cond) { return `${wt} ${size}px ${fam}`; }
function text(str, x, y, o = {}) {
  const c = g(); c.save();
  c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? FONT.cond);
  c.textAlign = o.align ?? 'left'; c.textBaseline = 'alphabetic'; c.letterSpacing = (o.ls ?? 0) + 'px';
  c.globalAlpha *= o.alpha ?? 1; c.fillStyle = o.col ?? C.light;
  c.fillText(str, x, y); c.restore();
}
function measure(str, o = {}) {
  const c = g(); c.save(); c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? FONT.cond); c.letterSpacing = (o.ls ?? 0) + 'px';
  const w = c.measureText(str).width; c.restore(); return w;
}
function fit(str, width, max, o = {}) { return Math.min(max, max * width / Math.max(1, measure(str, { ...o, size: max }))); }
/** shrink, then wrap: one line while it can stay at `keep` of max, else the largest size at which it wraps
    into at most o.lines lines. -> { size, lines } */
function wrapFit(str, width, max, o = {}) {
  const one = fit(str, width, max, o), maxL = o.lines ?? 2;
  if (one >= max * (o.keep ?? .74) || maxL < 2) return { size: one, lines: [str] };
  const ws = String(str).split(/\s+/);
  for (let s = Math.round(max); s >= max * .4; s -= 1) {
    const lines = []; let cur = '';
    for (const w of ws) { const tr = cur ? cur + ' ' + w : w; if (cur && measure(tr, { ...o, size: s }) > width) { lines.push(cur); cur = w; } else cur = tr; }
    if (cur) lines.push(cur);
    if (lines.length <= maxL && lines.every((l) => measure(l, { ...o, size: s }) <= width)) return { size: s, lines };
  }
  return { size: one, lines: [str] };
}
function clipRect(x, y, w, h, fn) { const c = g(); c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); fn(); c.restore(); }
function rrect(x, y, w, h, r, fill) { const c = g(); SK.rrPath(x, y, w, h, r); c.fillStyle = fill; c.fill(); }
function poly(pts, fill) { const c = g(); c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); for (const p of pts.slice(1)) c.lineTo(p[0], p[1]); c.closePath(); c.fillStyle = fill; c.fill(); }
const withT = (x, y, rot, s, fn) => SK.at(x, y, rot, s, fn);
function star4(x, y, r, col, rot = 0) {
  if (r <= 0) return;
  const pts = []; for (let i = 0; i < 8; i++) { const a = rot + i * Math.PI / 4, rr = i % 2 ? r * .28 : r; pts.push([x + Math.cos(a) * rr, y + Math.sin(a) * rr]); }
  poly(pts, col);
}
function goldGrad(c, x0, y0, x1, y1) {
  const gr = c.createLinearGradient(x0, y0, x1, y1);
  [[0, GOLD[0]], [.3, GOLD[1]], [.52, GOLD[0]], [.78, GOLD[2]], [1, GOLD[1]]].forEach(([k, col]) => gr.addColorStop(k, col));
  return gr;
}
/** the track's small icon, white on its colour */
function icon(kind, x, y, r, col) {
  const c = g(); c.save(); c.translate(x, y); c.strokeStyle = col; c.fillStyle = col; c.lineWidth = r * .16; c.lineCap = 'round';
  if (kind === 'chip') {
    const s = r * .5; SK.rrPath(-s, -s, 2 * s, 2 * s, s * .3); c.stroke(); c.fillRect(-s * .42, -s * .42, s * .84, s * .84);
    c.beginPath();
    for (const k of [-.5, 0, .5]) { c.moveTo(k * s, -s); c.lineTo(k * s, -s * 1.5); c.moveTo(k * s, s); c.lineTo(k * s, s * 1.5); c.moveTo(-s, k * s); c.lineTo(-s * 1.5, k * s); c.moveTo(s, k * s); c.lineTo(s * 1.5, k * s); }
    c.stroke();
  } else star4(0, 0, r * .75, col);
  c.restore();
}

/* the event's logo (content.logo): an image, a light version for dark grounds, and what was measured off
   it -- its symbol as two polygons (mark) and its letters' column spans (letters) */
const LG = D.logo || {};
const MARK = LG.mark ? { a: LG.mark.a, b: LG.mark.b, cx: LG.mark.cx, base: LG.mark.base } : null;
const LETTERS = LG.letters || null;
const logoImg = (light) => SK.IMG[(light && LG.light) || LG.image];
const logoScale = (w, h, light) => { const im = logoImg(light); return im ? Math.min(w / im.width, h / im.height) : 0; };
function mark(x, y, s, grow = [1, 1], cols = [C.second, C.accent]) {
  if (!MARK) return;
  for (const [k, pts] of [[0, MARK.a], [1, MARK.b]]) {
    const k2 = grow[k]; if (k2 <= 0) continue;
    poly(pts.map(([px, py]) => [x + (px - MARK.cx) * s, y + (py - MARK.base) * s * k2]), cols[k]);
  }
}
function wordmark(light, x, y, s, t0, t, o = {}) { // x, y: top-left; letters rise one after another
  const im = logoImg(light); if (!im) return;
  const c = g(), step = o.step ?? .045, d = o.d ?? .42;
  if (!LETTERS) {
    const u = outBackSoft(clamp((t - t0) / (d + 8 * step))); if (u <= 0) return;
    c.save(); c.beginPath(); c.rect(x - 4, y - 4, (im.width * s + 8) * Math.min(1, u), im.height * s + 8); c.clip();
    c.drawImage(im, x, y, im.width * s, im.height * s); c.restore(); return;
  }
  LETTERS.forEach(([a, b], i) => {
    const u = clamp((t - t0 - i * step) / d); if (u <= 0) return;
    const dy = (1 - outBackSoft(u)) * im.height * 1.1;
    c.save(); c.beginPath(); c.rect(x + (a - 2) * s, y - 4, (b - a + 4) * s, im.height * s + 8); c.clip();
    c.drawImage(im, a - 2, 0, b - a + 4, im.height, x + (a - 2) * s, y + dy * s, (b - a + 4) * s, im.height * s);
    c.restore();
  });
}
/** the logo in one line, centred on cx, sitting on base; it builds from t0 */
function lockup(cx, base, k, t0, t) {
  withT(cx, base, 0, k, () => {
    if (MARK) {
      mark(-185, 0, .42, [ease(t, t0, t0 + .4, outBack), ease(t, t0 + .08, t0 + .48, outBack)]);
      wordmark(true, -107, -64, logoScale(413.5, 64, true), t0 + .12, t, { step: .035, d: .36 });
    } else { const s = logoScale(480, 110, true), im = logoImg(true); if (im) wordmark(true, -im.width * s / 2, -im.height * s, s, t0, t, { d: .5 }); }
  });
}

/* ------------------------------------------------------------------ the ground: tiles cut from peaks, quietly turning */
function tiles(t, o = {}) {
  const S = o.size ?? 200, cols = o.cols ?? [C.groundDk, C.ground, C.groundDk], c = g();
  c.save(); c.translate(CX, CY); c.rotate(o.spin ?? 0);
  c.fillStyle = cols[0]; c.fillRect(-W, -H, W * 2, H * 2);
  const n = Math.ceil(Math.max(W, H) * .75 / S) + 1;
  for (let j = -n; j <= n; j++) for (let i = -n; i <= n; i++) {
    const beat = t * 2 * .5 - Math.hypot(i, j) * .35, k = Math.floor(beat), f = beat - k;
    const a = ((i + j) & 1 ? -1 : 1) * (k + outBack(clamp(f / .55))) * Math.PI / 2, h = S / 2 + 2;
    c.save(); c.translate(i * S, j * S); c.beginPath(); c.rect(-S / 2 + 3, -S / 2 + 3, S - 6, S - 6); c.clip(); c.rotate(a);
    c.fillStyle = cols[1];
    c.beginPath(); c.moveTo(-h, -h); c.lineTo(h, -h); c.lineTo(0, 0); c.closePath(); c.fill();
    c.beginPath(); c.moveTo(-h, h); c.lineTo(h, h); c.lineTo(0, 0); c.closePath(); c.fill();
    c.restore();
  }
  c.restore();
}
function ground(t, gx, gy, glow = 1) {
  const c = g();
  tiles(t, { spin: -.06 + t * .006 });
  const rg = c.createRadialGradient(gx, gy, 40, gx, gy, Math.max(W, H) * .6);
  rg.addColorStop(0, `rgba(${rgbOf(C.accent).join(',')},${.34 * glow})`); rg.addColorStop(.5, `rgba(${rgbOf(C.accentDk).join(',')},${.12 * glow})`); rg.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = rg; c.fillRect(0, 0, W, H);
}

/* ------------------------------------------------------------------ the card: one drawn component, 600 x 840 */
const CARD = { w: 600, h: 840, r: 30, b: 16 };
const CS = Math.min((WIDE ? H * .74 : H * .8) / CARD.h, W * .88 / CARD.w); // its scale when it is the subject: never wider than the frame
const CARDX = WIDE ? Math.round(W * .27) : CX, CARDY = CY;
function cardFront(t) {
  const c = g(), w = CARD.w, h = CARD.h, b = CARD.b, X0 = 36, IW = w - 72;
  SK.rrPath(0, 0, w, h, CARD.r); c.fillStyle = goldGrad(c, 0, 0, w, h); c.fill();   // the gold border: the rarest card
  rrect(b, b, w - 2 * b, h - 2 * b, CARD.r - 12, C.ground);
  // the rarity line, and the event's mark as the set symbol
  if (RAR.label) {
    star4(X0 + 12, 53, 13, GOLD[0]);
    text(UP(RAR.label), X0 + 34, 62, { size: fit(UP(RAR.label), IW - 130, 22, { wt: 800, fam: FONT.ui, ls: 3 }), wt: 800, fam: FONT.ui, ls: 3, col: GOLD[0] });
  }
  mark(w - X0 - 30, 66, .2);
  // the name, set large
  const nm = wrapFit(NAME, IW, 70, { wt: 900, lines: 2 });
  nm.lines.forEach((l, i) => text(l, X0, 84 + nm.size * (.8 + i * .92), { size: nm.size, wt: 900, col: C.light }));
  const winTop = 84 + nm.size * nm.lines.length * .92 + 10;
  // from the bottom up: the stats line, the move, the role
  let bottom = h - b - 14;
  if (STATS.length) { statsBand(X0, bottom - 46, IW, 46); bottom -= 58; }
  if (TALK.title) {
    const tw = wrapFit(TALK.title, IW - 52, 40, { wt: 800, fam: FONT.wide, lines: 3, keep: .9 });
    const bh = 44 + tw.lines.length * tw.size * 1.08 + 12, top = bottom - bh;
    rrect(X0, top, IW, bh, 14, C.groundMid);
    c.save(); SK.rrPath(X0, top, IW, bh, 14); c.clip(); c.fillStyle = C.accent; c.fillRect(X0, top, 9, bh); c.restore();
    if (COPY.move) text(COPY.move, X0 + 28, top + 31, { size: 17, wt: 800, fam: FONT.ui, ls: 4, col: C.accentLt });
    tw.lines.forEach((l, i) => text(l, X0 + 28, top + 44 + tw.size * (.82 + i * 1.08), { size: tw.size, wt: 800, fam: FONT.wide, col: C.light }));
    bottom = top - 10;
  }
  let winBot = bottom - 30;
  if (ROLE) {
    const ro = { wt: 800, fam: FONT.wide, ls: 1 }, rw = wrapFit(ROLE, IW, 28, { ...ro, lines: 2, keep: .8 }), rs = rw.size, n = rw.lines.length;
    rw.lines.forEach((l, i) => text(l, X0, bottom - 8 - (n - 1 - i) * rs * 1.15, { ...ro, size: rs, col: C.secondLt }));
    winBot = bottom - 8 - rs - (n - 1) * rs * 1.15 - 34;
  }
  artWindow(X0, winTop, IW, winBot - winTop);
  if (TRACK) trackPill(X0 + 14, winBot, 42, IW * .7);
  if (EMBLEM) emblem(w - X0 - 52, winTop + 52, 40);
}
function artWindow(x, y, w, h) { // the photo over the event's colours
  const c = g(), im = SK.IMG[SP.image];
  c.save(); SK.rrPath(x, y, w, h, 14); c.clip();
  const gr = c.createLinearGradient(0, y, 0, y + h); gr.addColorStop(0, C.accentLt); gr.addColorStop(.45, C.accent); gr.addColorStop(1, C.accentDk);
  c.fillStyle = gr; c.fillRect(x, y, w, h);
  mark(x + w * .6, y + h + 6, w * 1.02 / 291, [1, 1], [C.second, C.accentDk]);
  const rg = c.createRadialGradient(x + w / 2, y + h * .4, 10, x + w / 2, y + h * .4, h * .7);
  rg.addColorStop(0, 'rgba(255,255,255,.3)'); rg.addColorStop(1, 'rgba(255,255,255,0)'); c.fillStyle = rg; c.fillRect(x, y, w, h);
  if (im) { const d = h * 1.3; c.drawImage(im, x + w / 2 - d / 2, y - d * .056, d, d); }
  else if (INITIALS) text(INITIALS, x + w / 2, y + h * .5 + h * .17, { size: Math.min(h * .5, fit(INITIALS, w * .7, h * .5)), align: 'center', col: C.light, alpha: .92 }); // no photo: their initials stand in
  const sh = c.createLinearGradient(0, y + h * .72, 0, y + h); sh.addColorStop(0, `rgba(${C.groundRGB},0)`); sh.addColorStop(1, `rgba(${C.groundRGB},.5)`);
  c.fillStyle = sh; c.fillRect(x, y, w, h);
  c.restore();
  c.lineWidth = 4; c.strokeStyle = GOLD[0]; SK.rrPath(x, y, w, h, 14); c.stroke();
}
function trackPill(x, yc, hh, maxW) { // the card's type: the track's colour and its icon
  const c = g(), label = UP(TRACK.name), col = TRACK.color || C.second, o = { wt: 800, fam: FONT.ui, ls: 1.5 };
  const fs = fit(label, maxW - hh - 28, hh * .45, o), pw = hh + 10 + measure(label, { ...o, size: fs }) + 20;
  c.save(); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 10; c.shadowOffsetY = 3; rrect(x, yc - hh / 2, pw, hh, hh / 2, col); c.restore();
  c.beginPath(); c.arc(x + hh / 2, yc, hh / 2 - 4, 0, TAU); c.fillStyle = '#FFFFFF'; c.fill();
  icon(TRACK.icon, x + hh / 2, yc, hh / 2 - 4, col);
  text(label, x + hh + 8, yc + fs * .36, { ...o, size: fs, col: C.ground });
  return pw;
}
function emblem(x, y, r) { // the company's logo, exactly as given, on a white seal
  const c = g(), im = SK.IMG[EMBLEM];
  c.save(); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 12; c.shadowOffsetY = 4;
  c.beginPath(); c.arc(x, y, r + 5, 0, TAU); c.fillStyle = goldGrad(c, x - r, y - r, x + r, y + r); c.fill(); c.restore();
  c.beginPath(); c.arc(x, y, r, 0, TAU); c.fillStyle = '#FFFFFF'; c.fill();
  if (im) { const s = Math.min(r * 1.3 / im.width, r * 1.0 / im.height); c.drawImage(im, x - im.width * s / 2, y - im.height * s / 2, im.width * s, im.height * s); }
}
function statsBand(x, y, w, h) {
  const c = g(), o = { wt: 800, fam: FONT.wide, ls: 1 };
  rrect(x, y, w, h, 10, C.groundDk);
  const fs = fit(STATS.join('   '), w - 36, 25, o), sep = fs * 1.1;
  const ws = STATS.map((s) => measure(s, { ...o, size: fs })), tot = ws.reduce((a, b) => a + b, 0) + sep * (STATS.length - 1);
  let px = x + w / 2 - tot / 2;
  STATS.forEach((s, i) => {
    text(s, px, y + h / 2 + fs * .36, { ...o, size: fs, col: GOLD[0] }); px += ws[i];
    if (i < STATS.length - 1) { c.beginPath(); c.arc(px + sep / 2, y + h / 2, fs * .12, 0, TAU); c.fillStyle = C.accentLt; c.fill(); px += sep; }
  });
}
function cardBack() { // the back: a pattern of the event's mark
  const c = g(), w = CARD.w, h = CARD.h, b = CARD.b;
  SK.rrPath(0, 0, w, h, CARD.r); c.fillStyle = C.accent; c.fill();
  rrect(b, b, w - 2 * b, h - 2 * b, CARD.r - 12, C.ground);
  c.save(); SK.rrPath(b, b, w - 2 * b, h - 2 * b, CARD.r - 12); c.clip();
  for (let j = 0; j < 12; j++) for (let i = -1; i < 7; i++) mark(i * 100 + (j & 1) * 50 + 40, j * 76 + 60, .2, [1, 1], [C.groundMid, C.groundLt]);
  c.restore();
  c.lineWidth = 3; c.strokeStyle = C.second; SK.rrPath(34, 34, w - 68, h - 68, 16); c.stroke();
  c.beginPath(); c.arc(w / 2, h / 2, 160, 0, TAU); c.fillStyle = C.ground; c.fill(); c.lineWidth = 6; c.strokeStyle = C.second; c.stroke();
  mark(w / 2, h / 2 + 22, .6);
  const im = logoImg(true); if (im) { const s = logoScale(220, 44, true); c.drawImage(im, w / 2 - im.width * s / 2, h / 2 + 44, im.width * s, im.height * s); }
}
/** the holographic shine: a rainbow band across the card at u (0..1 crosses it) */
function shine(u, a = 1) {
  if (a <= 0 || u < -.2 || u > 1.2) return;
  const c = g(), w = CARD.w, h = CARD.h, x = lerp(-w * .9, w * 1.6, u);
  c.save(); SK.rrPath(0, 0, w, h, CARD.r); c.clip(); c.globalCompositeOperation = 'screen'; c.globalAlpha *= a;
  const gr = c.createLinearGradient(x - 280, 0, x + 120, h * .5);
  [[0, 'rgba(0,0,0,0)'], [.3, `rgba(${rgbOf(C.accent).join(',')},.35)`], [.45, 'rgba(255,236,170,.55)'], [.52, 'rgba(255,255,255,.85)'], [.6, 'rgba(255,236,170,.5)'], [.75, `rgba(${rgbOf(C.second).join(',')},.4)`], [1, 'rgba(0,0,0,0)']].forEach(([k, col]) => gr.addColorStop(k, col));
  c.fillStyle = gr; c.fillRect(0, 0, w, h); c.restore();
}
/** the card in 3D: pose {x, y, z, rx, ry, rz, s}; the face that looks at the camera is drawn */
function card3(pose, t, o = {}) {
  const c = g(), hw = CARD.w / 2, hh = CARD.h / 2;
  const at = (z) => [[-hw, -hh, z], [hw, -hh, z], [hw, hh, z], [-hw, hh, z]].map((p) => SK.pose3(p, pose));
  const F = at(-3), B = at(3);
  const Sh = F.map((p) => SK.proj3([p[0] + 40, p[1] + 60, p[2] + 120]));
  if (Sh.every(Boolean)) { c.save(); c.filter = 'blur(26px)'; poly(Sh, `rgba(${C.shadow},.55)`); c.restore(); }
  for (let i = 0; i < 4; i++) { const j = (i + 1) % 4; SK.poly3([F[i], F[j], B[j], B[i]], GOLD[2], { light: [-.3, -1, -.5], ambient: .6 }); }
  const L = { light: [-.3, -.8, -1], ambient: .84 };
  const front = SK.face3(F, CARD.w, CARD.h, () => { cardFront(t); if (o.shine) shine(o.shine.u, o.shine.a); }, { key: 'cardF', res: o.res, shade: 1 - SK.lit3(F, L) });
  if (!front) { const Bm = [B[1], B[0], B[3], B[2]]; SK.face3(Bm, CARD.w, CARD.h, () => cardBack(), { key: 'cardB', res: o.res, shade: 1 - SK.lit3(Bm, L) }); }
}
/* the speakers already announced (content.announced): at most eight, the latest kept; each sits open in the
   binder as a small card -- their photo or initials, their name -- around the new one */
const initialsOf = (name) => String(name ?? '').replace(/^(dr|prof|mr|mrs|ms)\.?\s+/i, '').split(/[\s]+/).filter(Boolean).map((w) => w[0]).filter((ch, i, a2) => i === 0 || i === a2.length - 1).join('').toUpperCase();
const ANN = (Array.isArray(D.announced) ? D.announced : []).filter((p) => p && p.name).slice(-8);
const ANN_SLOTS = [0, 1, 2, 3, 5, 6, 7, 8];                 // reading order around the middle, the new card's
function cardMini(p) {
  const c = g(), w = CARD.w, h = CARD.h, b = CARD.b, X0 = 36, IW = w - 72, gold = p.border || (p.featured ? GOLD : null);
  SK.rrPath(0, 0, w, h, CARD.r);
  if (gold) { const gr = c.createLinearGradient(0, 0, w, h); [[0, gold[0]], [.5, gold[1]], [1, gold[2] || gold[1]]].forEach(([k, col]) => gr.addColorStop(k, col)); c.fillStyle = gr; } else c.fillStyle = C.second;
  c.fill();
  rrect(b, b, w - 2 * b, h - 2 * b, CARD.r - 12, C.ground);
  const sub = UP([p.role, p.org].filter(Boolean).join(', '));
  const subH = sub ? 62 : 0, nmax = 104;
  const nm = wrapFit(UP(p.name), IW, nmax, { wt: 900, lines: 2, keep: .8 }), nh = nm.lines.length * nm.size * .92;
  const y1 = h - b - 22 - subH, top = y1 - nh, wy = b + 22, wh = top - 26 - wy;
  // the window: their photo over the event's colours, or their initials
  const im = p.image && SK.IMG[p.image];
  c.save(); SK.rrPath(X0, wy, IW, wh, 14); c.clip();
  const gr = c.createLinearGradient(0, wy, 0, wy + wh); gr.addColorStop(0, C.accentLt); gr.addColorStop(.45, C.accent); gr.addColorStop(1, C.accentDk);
  c.fillStyle = gr; c.fillRect(X0, wy, IW, wh);
  mark(X0 + IW * .6, wy + wh + 6, IW * 1.02 / 291, [1, 1], [C.second, C.accentDk]);
  if (im) { const k = Math.max(IW / im.width, wh / im.height) * 1.08, dw = im.width * k, dh = im.height * k; c.drawImage(im, X0 + IW / 2 - dw / 2, wy + wh - dh + dh * .04, dw, dh); }
  else { const ini = initialsOf(p.name); if (ini) text(ini, X0 + IW / 2, wy + wh * .5 + wh * .15, { size: Math.min(wh * .46, fit(ini, IW * .7, wh * .46)), align: 'center', col: C.light, alpha: .92 }); }
  const sh = c.createLinearGradient(0, wy + wh * .72, 0, wy + wh); sh.addColorStop(0, `rgba(${C.groundRGB},0)`); sh.addColorStop(1, `rgba(${C.groundRGB},.5)`);
  c.fillStyle = sh; c.fillRect(X0, wy, IW, wh);
  c.restore();
  c.lineWidth = 4; c.strokeStyle = gold ? gold[0] : C.secondLt; SK.rrPath(X0, wy, IW, wh, 14); c.stroke();
  nm.lines.forEach((l, i) => text(l, w / 2, top + nm.size * (.8 + i * .92), { size: nm.size, wt: 900, col: C.light, align: 'center' }));
  if (sub) { const o = { wt: 800, fam: FONT.wide, ls: 1 }, fs = fit(sub, IW, 40, o); text(sub, w / 2, h - b - 30, { ...o, size: fs, col: C.secondLt, align: 'center' }); }
}
/** the card flat, centred on x, y at scale s (the binder) */
function card2(x, y, s, front, t) { withT(x, y, 0, s, () => { g().translate(-CARD.w / 2, -CARD.h / 2); front ? cardFront(t) : cardBack(); }); }

/* ------------------------------------------------------------------ 1. the pack */
const PK = { w: Math.round(Math.min(500, W * .46)), h: Math.round(Math.min(720, H * .66)), x: CX, y: Math.round(H * .56), crimp: 46 };
const PKS = TALL ? 1.4 : 1;                               // a tall frame has the room for a bigger pack
const PS = PK.w * .84 / CARD.w;                          // the card's scale inside it
const TEAR_Y = -PK.h / 2 + PK.crimp + 22;
const peekY = (t) => TEAR_Y + CARD.h * PS / 2 + 40 - ease(t, 3.35, 3.95, outBackSoft) * 175;
function packPose(t) {
  const calm = 1 - ease(t, 3.3, 3.9), env = ease(t, .3, 2.6) * calm;
  const rot = env * (.05 * Math.sin(t * 11) + .025 * Math.sin(t * 23)) + .02 * Math.sin(t * 1.3) * calm;
  const pulse = t < 3.3 ? Math.pow(Math.max(0, 1 - ((t * 2) % 1) / .35), 2) : 0;
  const fall = ease(t, OUT, OUT + .7, E.in);
  return { x: PK.x, y: PK.y + fall * H * .95, rot: rot + fall * .35, s: PKS * ease(t, -.25, .5, outBack) * (1 + .018 * pulse) };
}
function packPath(c, w, h) {
  const hw = w / 2, hh = h / 2, n = Math.round(w / 14);
  c.beginPath(); c.moveTo(-hw, -hh + 8);
  for (let i = 0; i <= n; i++) c.lineTo(-hw + i * w / n, -hh + (i % 2 ? 0 : 8));
  c.lineTo(hw, hh - 8);
  for (let i = n; i >= 0; i--) c.lineTo(-hw + i * w / n, hh - (i % 2 ? 0 : 8));
  c.closePath();
}
function packBody(t) {
  const c = g(), w = PK.w, h = PK.h, hw = w / 2, hh = h / 2;
  c.save(); c.shadowColor = `rgba(${C.shadow},.6)`; c.shadowBlur = 40; c.shadowOffsetY = 20;
  packPath(c, w, h); const gr = c.createLinearGradient(-hw, -hh, hw, hh);
  gr.addColorStop(0, C.accentLt); gr.addColorStop(.35, C.accent); gr.addColorStop(.72, C.accentDk); gr.addColorStop(1, C.groundMid);
  c.fillStyle = gr; c.fill(); c.restore();
  c.save(); packPath(c, w, h); c.clip();
  c.globalAlpha = .1; c.strokeStyle = '#fff'; c.lineWidth = 2;
  for (let i = 0; i < 14; i++) { const x = -hw + i * w / 13; c.beginPath(); c.moveTo(x - 70, -hh); c.lineTo(x + 70, hh); c.stroke(); }
  c.globalAlpha = 1;
  for (const [y0, y1] of [[-hh, -hh + PK.crimp], [hh - PK.crimp, hh]]) { // the crimped seals
    c.fillStyle = 'rgba(255,255,255,.17)'; c.fillRect(-hw, y0, w, y1 - y0);
    c.strokeStyle = 'rgba(0,0,0,.2)'; c.lineWidth = 2; c.beginPath();
    for (let x = -hw + 6; x < hw; x += 9) { c.moveTo(x, y0 + 7); c.lineTo(x, y1 - 7); }
    c.stroke();
  }
  // the event's logo on a panel of its ground, the pack's name under it
  const pTop = -hh + PK.crimp + 50, s = w * .4 / 291, im = logoImg(true), ws = im ? logoScale(w * .62, 70, true) : 0, wh = im ? im.height * ws : 0;
  const mh = 184 * s, pH = 36 + mh + 22 + wh + 36;
  rrect(-hw + 34, pTop, w - 68, pH, 22, C.ground);
  mark(0, pTop + 36 + mh, s);
  if (im) c.drawImage(im, -im.width * ws / 2, pTop + 36 + mh + 22, im.width * ws, wh);
  const ly = pTop + pH + 74;
  if (COPY.pack) text(COPY.pack, 0, ly, { size: fit(COPY.pack, w - 80, 74), align: 'center', col: C.light });
  if (COPY.pack_sub) text(COPY.pack_sub, 0, ly + 46, { size: 26, wt: 800, fam: FONT.ui, ls: 7, col: C.light, align: 'center' });
  for (let i = -1; i <= 1; i++) star4(i * 44, ly + 112, 13, GOLD[0]);
  // the foil's sheen, sweeping
  const sx = lerp(-w * 1.3, w * 1.3, ((t + .5) % 1.6) / 1.6), sg = c.createLinearGradient(sx - 160, -hh, sx + 160, -hh + 200);
  sg.addColorStop(0, 'rgba(255,255,255,0)'); sg.addColorStop(.5, 'rgba(255,255,255,.3)'); sg.addColorStop(1, 'rgba(255,255,255,0)');
  c.fillStyle = sg; c.fillRect(-hw, -hh, w, h);
  c.restore();
}
function scenePack(t) {
  const c = g(), P = packPose(t), hw = PK.w / 2;
  const jag = []; for (let x = -hw - 2; x <= hw + 2.1; x += 14) jag.push([x, TEAR_Y + (rnd(Math.round(x) + 999) - .5) * 14]);
  const tp = ease(t, TEAR[0], TEAR[1]), fly = ease(t, TEAR[1], TEAR[1] + .7, E.in);
  withT(P.x, P.y, P.rot, P.s, () => {
    const op = ease(t, 3.0, 3.6); // the light out of the opening, and the card rising in it
    if (op > 0) {
      const rg = c.createRadialGradient(0, TEAR_Y, 10, 0, TEAR_Y, 360); rg.addColorStop(0, `rgba(255,236,170,${.7 * op})`); rg.addColorStop(1, 'rgba(255,236,170,0)');
      c.fillStyle = rg; c.fillRect(-400, TEAR_Y - 380, 800, 520);
      c.save(); c.globalAlpha *= .22 * op; c.fillStyle = GOLD[0];
      for (let i = 0; i < 9; i++) { const a = -Math.PI / 2 + (i - 4) * .26 + Math.sin(t * 1.5) * .05; c.beginPath(); c.moveTo(0, TEAR_Y); c.lineTo(Math.cos(a - .05) * 700, TEAR_Y + Math.sin(a - .05) * 700); c.lineTo(Math.cos(a + .05) * 700, TEAR_Y + Math.sin(a + .05) * 700); c.closePath(); c.fill(); }
      c.restore();
      if (t < OUT) card2(0, peekY(t), PS, false, t);
    }
    c.save(); c.beginPath(); c.moveTo(-hw - 60, PK.h); for (const p of jag) c.lineTo(p[0], p[1]); c.lineTo(hw + 60, PK.h); c.closePath(); c.clip();
    packBody(t); c.restore();
    if (fly < 1) withT(hw + fly * W * .6, TEAR_Y - fly * H * .5, -tp * .22 - fly * 1.6, 1, () => { // the strip tears off and flies
      c.translate(-hw, -TEAR_Y);
      c.save(); c.beginPath(); c.moveTo(-hw - 60, -PK.h); for (const p of jag) c.lineTo(p[0], p[1]); c.lineTo(hw + 60, -PK.h); c.closePath(); c.clip();
      packBody(t); c.restore();
    });
  });
  // above it, the rarity
  const ta = ease(t, -.3, .45, E.out), out = ease(t, OUT, OUT + .4, E.in), label = UP(RAR.label);
  if (label && out < 1) {
    const size = fit(label, W - 140, 112), y = Math.round(PK.y - PK.h * PKS / 2 - 84) - out * 300;
    clipRect(0, y - size, W * ta + 4, size * 1.2, () => text(label, CX, y, { size, align: 'center', col: C.light }));
    c.save(); c.globalAlpha = ta * (1 - out); c.fillStyle = goldGrad(c, CX - 200, 0, CX + 200, 0); c.fillRect(CX - 160 * ta, y + 18, 320 * ta, 7); c.restore();
  }
}

/* ------------------------------------------------------------------ 2-4. the flip, the card, the tilt */
function cardPose(t) {
  if (t < LANDT) {
    const u = clamp((t - OUT) / (LANDT - OUT)), P0 = packPose(OUT);
    return {
      x: SK.kf(t, [[OUT, P0.x], [OUT + .55, lerp(P0.x, CARDX, .35), E.out], [LANDT, CARDX]]),
      y: SK.kf(t, [[OUT, P0.y + peekY(OUT) * PKS], [OUT + .55, CARDY - H * .1, E.out], [LANDT, CARDY]]),
      z: SK.kf(t, [[OUT, 0], [OUT + .55, -420, E.out], [LANDT, 0, E.in]]),
      s: SK.kf(t, [[OUT, PS * PKS], [OUT + .45, CS, E.out]]),
      ry: Math.PI + 3 * Math.PI * (1 - Math.pow(1 - u, 2.2)),
      rx: .7 * Math.sin(u * Math.PI * 1.5) * (1 - u), rz: -.3 * (1 - E.out(u)),
    };
  }
  const f = ease(t, LANDT, LANDT + 1), lt = t - LANDT, settle = Math.exp(-lt * 5) * Math.sin(lt * 18);
  const tilt = (keys) => SK.kf(t, keys, E.inOut);
  const ry = .07 * Math.sin(lt * .7) * f + tilt([[TILT[0], 0], [17.8, .5], [19.0, -.46], [20.0, .12], [TILT[1], 0]]) * (t > TILT[0] ? 1 : 0);
  const rx = .05 * Math.sin(lt * .9) * f + .05 * settle + tilt([[TILT[0], 0], [17.8, -.13], [19.0, .1], [TILT[1], 0]]) * (t > TILT[0] ? 1 : 0);
  const calm = 1 - ease(t, 20.2, TILT[1]);
  return { x: CARDX, y: CARDY + 6 * Math.sin(lt * 1.3) * f * calm, z: 0, s: CS, rx: rx * calm, ry: ry * (t > 20 ? calm : 1), rz: 0 };
}
function shineAt(t, pose) {
  for (const s0 of SHINES) if (t > s0 && t < s0 + 1) return { u: E.inOut((t - s0) / 1), a: 1 };
  if (t > TILT[0] + .3 && t < TILT[1]) return { u: (pose.ry + .5) / 1, a: ease(t, TILT[0] + .3, TILT[0] + .7) * (1 - ease(t, 20.2, TILT[1])) };
  return null;
}
// the feed's two reading stops (the card's top, then its bottom): [x, y in card units, zoom]
const ZK = clamp((W * .97 / (CARD.w * CS) - 1) / .62, 0, 1), tz = (y, z) => [0, y * ZK, 1 + (z - 1) * ZK]; // how far a stop may go in
const TOUR = [[8.9, [0, 0, 1]], [STOPS[0], tz(-150, 1.62)], [11.4, tz(-132, 1.67), E.sine], [STOPS[1], tz(170, 1.62)], [13.3, tz(188, 1.67), E.sine], [STOPS[2], [0, 0, 1]]];
function sparks(t, pose) {
  if (t < SPARK - .05 || t > 20.9) return;
  for (let i = 0; i < 22; i++) {
    const age = t - SPARK - (i % 7) * .045, life = 1.5; if (age < 0 || age > life) continue;
    const side = i % 4, u = rnd(i * 7 + 1) - .5;
    const lp = side === 0 ? [u * CARD.w, -CARD.h / 2] : side === 1 ? [CARD.w / 2, u * CARD.h] : side === 2 ? [u * CARD.w, CARD.h / 2] : [-CARD.w / 2, u * CARD.h];
    const q = SK.proj3(SK.pose3([lp[0], lp[1], 0], pose)); if (!q) continue;
    const dir = [[0, -1], [1, 0], [0, 1], [-1, 0]][side], sp = (rnd(i * 17) - .5) * 1.4, v = 120 + rnd(i * 13) * 240;
    const e = 1 - Math.pow(1 - age / life, 3), dx = dir[0] + (dir[1] ? sp : 0), dy = dir[1] + (dir[0] ? sp : 0);
    star4(q[0] + dx * v * e, q[1] + dy * v * e, (12 + rnd(i * 5) * 18) * Math.sin(Math.PI * age / life), i % 3 ? GOLD[0] : '#FFFFFF', age * 2);
  }
  for (let i = 0; i < 7; i++) { // twinkles that stay round the card while it tilts
    const a = i / 7 * TAU + .4, rx = CARD.w * CS * .68, ry = CARD.h * CS * .58, ph = (t - SPARK - .3) * 2.2 + i * .9;
    if (ph < 0) continue;
    star4(pose.x + Math.cos(a) * rx, pose.y + Math.sin(a) * ry, 16 * Math.max(0, Math.sin(ph)) * (1 - ease(t, 20.2, 20.8)), GOLD[0]);
  }
}
function panel(t) { // the wide frame: the talk, set large, right of the card
  if (!WIDE) return;
  const out = ease(t, SLOT[0], SLOT[0] + .45, E.in); if (out >= 1) return;
  const c = g(), x0 = Math.round(W * .475), PW = W - 110 - x0;
  const nm = wrapFit(NAME, PW, 124, { wt: 900, lines: 2 });
  const rw = ROLE ? wrapFit(ROLE, PW, 38, { wt: 800, fam: FONT.wide, ls: 1, lines: 2, keep: .8 }) : null, rs = rw ? rw.size : 0;
  const lim = LOGOTYPE && SK.IMG[LOGOTYPE], lh = 46;
  const tt = TALK.title ? wrapFit(TALK.title, PW - 70, 60, { wt: 800, fam: FONT.wide, lines: 3, keep: .85 }) : null;
  const blocks = [['kick', 64], ['name', nm.lines.length * nm.size * .92 + 18]];
  if (rs) blocks.push(['role', rs + (rw.lines.length - 1) * rs * 1.15 + 16]);
  if (lim) blocks.push(['logo', lh + 40]);
  if (tt) blocks.push(['talk', 66 + tt.lines.length * tt.size * 1.1 + 52]);
  if (CHIPS.length) blocks.push(['stats', 70]);
  let y = (H - blocks.reduce((s, b) => s + b[1], 0)) / 2;
  c.save(); c.translate(out * 200, 0); c.globalAlpha *= 1 - out;
  for (const [k, bh] of blocks) {
    if (k === 'kick') {
      const a = ease(t, 8.8, 9.3, E.out), o = { wt: 800, fam: FONT.ui, ls: 5 }, label = UP(RAR.label);
      clipRect(x0 - 10, y - 10, (PW + 20) * a, bh + 10, () => {
        let x = x0;
        if (label) { star4(x + 14, y + 25, 15, GOLD[0]); text(label, x + 40, y + 36, { ...o, size: 28, col: GOLD[0] }); x += 40 + measure(label, { ...o, size: 28 }) + 28; }
        if (TRACK) trackPill(x, y + 25, 48, x0 + PW - x);
      });
    } else if (k === 'name') {
      nm.lines.forEach((l, i) => {
        const a = ease(t, STOPS[0] - .5 + i * .1, STOPS[0] + i * .1, outBackSoft), by = y + nm.size * (.8 + i * .92);
        clipRect(x0 - 10, by - nm.size * .85, PW + 40, nm.size * 1.02, () => text(l, x0, by + (1 - a) * nm.size, { size: nm.size, col: C.light }));
      });
    } else if (k === 'role') {
      const a = ease(t, 10.3, 10.7, E.out);
      clipRect(x0 - 4, y - 4, (PW + 8) * a, bh + 8, () => rw.lines.forEach((l, i) => text(l, x0, y + rs * (.8 + i * 1.15), { size: rs, wt: 800, fam: FONT.wide, ls: 1, col: C.secondLt })));
    } else if (k === 'logo') {
      const a = ease(t, 10.5, 10.9, E.out), lw = lim.width * lh / lim.height;
      clipRect(x0 - 4, y, (lw + 8) * a, bh, () => c.drawImage(lim, x0, y + 14, lw, lh));
    } else if (k === 'talk') {
      const a = ease(t, STOPS[1] - .35, STOPS[1] + .1, outBackSoft), bx = bh - 30;
      if (a > 0) {
        c.save(); SK.rrPath(x0, y + 6, PW * a, bx, 18); c.fillStyle = C.groundMid; c.fill(); c.clip(); c.fillStyle = C.accent; c.fillRect(x0, y + 6, 12, bx); c.restore();
        if (COPY.move) text(COPY.move, x0 + 40, y + 50, { size: 22, wt: 800, fam: FONT.ui, ls: 6, col: C.accentLt, alpha: ease(t, STOPS[1] - .1, STOPS[1] + .2) });
        tt.lines.forEach((l, i) => {
          const b2 = ease(t, STOPS[1] - .15 + i * .1, STOPS[1] + .3 + i * .1, outBackSoft), by = y + 72 + tt.size * (.82 + i * 1.1);
          clipRect(x0 + 30, by - tt.size * .9, PW - 40, tt.size * 1.15, () => text(l, x0 + 40, by + (1 - b2) * tt.size, { size: tt.size, wt: 800, fam: FONT.wide, col: C.light }));
        });
      }
    } else if (k === 'stats') {
      const o = { wt: 800, fam: FONT.wide, ls: 1 }, pad = 26, gap = 14;
      let fs = 32; const wsum = (s) => CHIPS.reduce((a, ch) => a + measure(ch, { ...o, size: s }) + pad * 2, 0) + gap * (CHIPS.length - 1);
      if (wsum(fs) > PW) fs *= (PW - (pad * 2 + gap) * CHIPS.length) / (wsum(fs) - (pad * 2 + gap) * CHIPS.length);
      let x = x0;
      CHIPS.forEach((ch, i) => {
        const cw = measure(ch, { ...o, size: fs }) + pad * 2, p = ease(t, STOPS[2] - .3 + i * .15, STOPS[2] + .15 + i * .15, outBack), last = i === CHIPS.length - 1 && TALK.stage;
        if (p > 0) withT(x + cw / 2, y + 30, 0, p, () => {
          rrect(-cw / 2, -30, cw, 60, 30, last ? goldGrad(c, -cw / 2, 0, cw / 2, 0) : C.groundLt);
          text(ch, 0, fs * .36, { ...o, size: fs, col: last ? C.ground : C.light, align: 'center' });
        });
        x += cw + gap;
      });
    }
    y += bh;
  }
  c.restore();
}
function sceneCard(t) {
  const c = g(), pose = cardPose(t);
  const kick = t > LANDT ? .03 * Math.exp(-(t - LANDT) * 6) : 0, push = 1 + kick + (t > TILT[0] ? .04 * E.sine(ease(t, TILT[0], TILT[1])) : 0);
  const [fx, fy, z] = WIDE ? [0, 0, 1] : SK.kf(t, TOUR);
  const sx = WIDE ? CX : CARDX + fx * CS, sy = CARDY + fy * CS; // the wide frame's camera stays put: the card is on its left
  c.save(); c.translate(CX, CY); c.scale(z * push, z * push); c.translate(-sx, -sy);
  if (t < OUT + .8) scenePack(t);
  const ra = t - LANDT; // the landing: a ring of gold
  if (ra > 0 && ra < .7) {
    const k = 1 + .45 * E.out(ra / .7), w = CARD.w * CS * k, h = CARD.h * CS * k;
    c.save(); c.globalAlpha = .7 * (1 - ra / .7); c.lineWidth = 10; c.strokeStyle = GOLD[0]; SK.rrPath(CARDX - w / 2, CARDY - h / 2, w, h, 30 * k); c.stroke(); c.restore();
  }
  SK.view3({ d: 2200 });
  card3(pose, t, { shine: shineAt(t, pose), res: z * CS > 1.25 ? 2 : undefined });
  sparks(t, pose);
  c.restore();
  panel(t);
}

/* ------------------------------------------------------------------ 5. the binder, and the end */
const BIND = (() => {
  const pad = 30, gap = 18, shW = ((W * .9 - 34 - 2 * pad - 2 * gap) / 3) * CARD.h / CARD.w;
  const sh = Math.min((H * (WIDE ? .84 : .76) - 2 * pad - 2 * gap) / 3, shW), sw = sh * CARD.w / CARD.h, ph = 3 * sh + 2 * pad + 2 * gap;
  const px = WIDE ? CARDX : CX, py = WIDE ? CY : CY + 50, k = sw * .92 / CARD.w;
  return { ph, pw: 3 * sw + 2 * gap + 2 * pad + 34, pad, gap, sh, sw, px, py, k, z0: CS / k };
})();
function binder(t) {
  const c = g(), B = BIND, gx = B.px - 1.5 * B.sw - B.gap, gy = B.py - 1.5 * B.sh - B.gap;
  const x0 = gx - B.pad - 34, y0 = gy - B.pad;
  c.save(); c.shadowColor = `rgba(${C.shadow},.6)`; c.shadowBlur = 50; c.shadowOffsetY = 20; rrect(x0, y0, B.pw, B.ph, 22, C.groundMid); c.restore();
  for (let i = 0; i < 3; i++) { c.beginPath(); c.arc(x0 + 20, y0 + B.ph * (.2 + i * .3), 8, 0, TAU); c.fillStyle = C.groundDk; c.fill(); }
  const sweep = ((t - 22.3) / 1.6);
  for (let j = 0; j < 3; j++) for (let i = 0; i < 3; i++) {
    const x = gx + i * (B.sw + B.gap), y = gy + j * (B.sh + B.gap), mid = i === 1 && j === 1;
    rrect(x, y, B.sw, B.sh, 12, `rgba(${C.groundRGB},.55)`);
    const who = mid ? null : ANN[ANN_SLOTS.indexOf(j * 3 + i)];
    if (who) { // already announced: open, a touch quieter than the new one
      withT(x + B.sw / 2, y + B.sh / 2 + 2, 0, B.k, () => { c.translate(-CARD.w / 2, -CARD.h / 2); cardMini(who); });
      c.save(); SK.rrPath(x, y, B.sw, B.sh, 12); c.clip(); c.fillStyle = `rgba(${C.groundRGB},.16)`; c.fillRect(x, y, B.sw, B.sh); c.restore();
    } else card2(x + B.sw / 2, y + B.sh / 2 + 2, B.k, mid, t);
    if (mid && ANN.length) { // the new card among the others: a halo as it lands
      const pu = ease(t, SLOT[1] - .05, SLOT[1] + .9, E.out), pa = (1 - pu) * clamp((t - SLOT[1] + .05) / .1);
      if (pa > 0) { c.save(); c.globalAlpha *= pa; c.lineWidth = 6 + 10 * (1 - pu); c.strokeStyle = GOLD[0]; SK.rrPath(x - 10 - pu * 26, y - 10 - pu * 26, B.sw + 20 + pu * 52, B.sh + 20 + pu * 52, 16 + pu * 16); c.stroke(); c.restore(); }
    }
    c.save(); SK.rrPath(x, y, B.sw, B.sh, 12); c.clip(); // the sleeve: a clear pocket with a glint
    c.fillStyle = 'rgba(255,255,255,.06)'; c.fillRect(x, y, B.sw, B.sh);
    const gl = x - B.sw + (sweep - (i + j) * .08) * B.pw * 1.6, gr = c.createLinearGradient(gl, y, gl + B.sw * .6, y + B.sh * .3);
    gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.5, 'rgba(255,255,255,.22)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    c.fillStyle = gr; c.fillRect(x, y, B.sw, B.sh); c.restore();
    c.lineWidth = 2; c.strokeStyle = 'rgba(255,255,255,.22)'; SK.rrPath(x, y, B.sw, B.sh, 12); c.stroke();
  }
  return y0;
}
function sceneEnd(t) {
  const c = g(), B = BIND, u = E.inOut(ease(t, SLOT[0], SLOT[1])), Z = Math.exp(lerp(Math.log(B.z0), 0, u));
  const rc = WIDE ? 0 : ease(t, RECEDE[0], RECEDE[1]), drift = 1 + .025 * E.sine(ease(t, 22, 26));
  c.save();
  c.translate(CX, CY); c.scale(drift, drift); c.translate(-CX, -CY);
  c.save();
  const ry = TALL ? H * .34 : H * 330 / 1080, rs = TALL ? .66 : .52;
  c.translate(B.px, lerp(B.py, ry, rc)); c.scale(lerp(1, rs, rc), lerp(1, rs, rc)); c.translate(-B.px, -B.py);
  c.translate(lerp(CARDX, B.px, u), lerp(CARDY, B.py, u)); c.scale(Z, Z); c.translate(-B.px, -B.py);
  const top = binder(t);
  const ha = ease(t, SLOT[1] - .1, SLOT[1] + .35, outBackSoft);
  if (!WIDE && COPY.binder && ha > 0) {
    const size = fit(COPY.binder, B.pw + 140, 68), by = top - 40;
    clipRect(0, by - size, W, size * 1.1, () => text(COPY.binder, CX, by + (1 - ha) * size, { size, align: 'center', col: C.light }));
  }
  c.restore();
  // the right of a wide frame, or the bottom of the feed's: more to come, then the event
  const xr = WIDE ? Math.round(W * .735) : CX;
  if (WIDE && COPY.binder && ha > 0) {
    const bw = 2 * (W - xr) - 150, hb = wrapFit(COPY.binder, bw, 130, { lines: 2 });
    hb.size = Math.min(hb.size, ...hb.lines.map((l) => fit(l, bw, hb.size)));
    hb.lines.forEach((l, i) => { const by = 190 + hb.size * (.8 + i * .92); clipRect(xr - 500, by - hb.size * .85, 1000, hb.size, () => text(l, xr, by + (1 - ha) * hb.size, { size: hb.size, align: 'center', col: i === hb.lines.length - 1 ? C.accent : C.light })); });
  }
  const base = WIDE ? 640 : TALL ? Math.round(H * .72) : 712, L0 = RECEDE[0] + .45;
  lockup(xr, base, WIDE ? 1.15 : 1.1, L0, t);
  const lp = ease(t, L0 + .45, L0 + .95, E.out), line = COPY.line;
  if (line && lp > 0) {
    const o = { wt: 800, fam: FONT.wide, ls: 3 }, size = fit(line, WIDE ? 760 : W - 140, 38, o), w = measure(line, { ...o, size }), y = base + 92;
    clipRect(xr - w / 2 - 4, y - size, (w + 8) * lp, size * 1.4, () => text(line, xr, y, { ...o, size, col: C.light, align: 'center' }));
    if (lp < 1) { c.fillStyle = C.accent; c.fillRect(xr - w / 2 + (w + 8) * lp - 4, y - size * .85, 5, size * 1.1); }
  }
  const up = ease(t, L0 + .8, L0 + 1.2, outBack);
  if (EV.url && up > 0) withT(xr, base + 172, 0, up, () => {
    const o = { wt: 700, fam: FONT.ui, ls: 1 }, fs = fit(EV.url, (WIDE ? 2 * (W - xr) - 140 : W - 140) - 72, 34, o), bw = measure(EV.url, { ...o, size: fs }) + 72;
    rrect(-bw / 2, -32 + 6, bw, 64, 32, C.accentDk); rrect(-bw / 2, -32, bw, 64, 32, C.accent);
    text(EV.url, 0, fs * .36, { ...o, size: fs, col: C.light, align: 'center' });
  });
  c.restore();
}

/* ------------------------------------------------------------------ the film */
function draw(t) {
  const cam = t < SLOT[0] ? cardPose(Math.max(t, OUT)) : { x: BIND.px, y: BIND.py };
  ground(t, t < OUT ? PK.x : cam.x, t < OUT ? PK.y : cam.y, t < OUT ? .8 + .4 * ease(t, 2.9, 3.6) : 1);
  if (t < OUT) scenePack(t);
  else if (t < SLOT[0]) sceneCard(t);
  else { sceneEnd(t); panel(t); } // the wide frame's talk details slide off as the binder opens
}

/* ------------------------------------------------------------------ the sound
   A 120 bpm groove in F minor from a chord chart, worked out from the clock above: the pack wobbles on the
   beat, a roll into the tear and the shot, the card lands on a bar line, a stab on each reading stop, a
   glockenspiel run with the shines and the sparks, a roll into the binder and the last chord at LAST. */
const BPM = 120, beat = (t) => t * BPM / 60;
const gf = (x) => String(+x.toPrecision(6));
function scoreData() {
  const CHART = [['F1', 'F2', 'Ab3+C4+F4', 'F3+Ab3+C4+Eb4'], ['Db2', 'Db3', 'Ab3+Db4+F4', 'Db3+F3+Ab3+C4'], ['Ab1', 'Ab2', 'Ab3+C4+Eb4', 'Ab3+C4+Eb4+G4'], ['Eb2', 'Eb3', 'G3+Bb3+Eb4', 'Eb3+G3+Bb3+Db4']];
  const BARS = Math.round(SK._film.duration / (240 / BPM));
  const HITS = [OUT, LANDT, ...STOPS, SPARK, SLOT[1]].map(beat), FINAL = beat(LAST);
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', openhat: '..x...x...x...x.', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
  const FULL = { ...GROOVE, rim: '...o..o....o..o.' };
  const DRUMS = [
    { ...GROOVE, hat: 'oooooooooooooooo' },                                                               // 0: the pack wobbles
    { kick: 'x...x...x.......', clap: '....x...........', hat: 'o.o.o.o.o.o.....', snare: '........ooxxxxX.' }, // 1: the tear, a roll into the shot
    { kick: 'X...........x...', openhat: '..x...x...x.....', shaker: '.o.o.o.o.o.o.o.o', snare: '............oxxX' }, // 2: the spin
    { ...GROOVE, kick: 'X...x...x...x...' },                                                              // 3: it lands
    GROOVE, FULL, FULL, FULL,                                                                              // 4-7: the card
    { ...GROOVE, snare: '............oxxX' },                                                              // 8: into the tilt's sparks
    FULL,                                                                                                  // 9: the tilt
    { ...GROOVE, kick: 'x...x...x.......', snare: '........ooxxxxX.' },                                   // 10: into the binder
    { ...FULL, snare: '............oxxX' },                                                                // 11: a fill into the last chord
    { kick: 'X...............', openhat: 'x...............' },                                            // 12: the address
  ];
  const KIT_GAINS = { kick: 1.15, snare: .42, clap: .42, hat: .26, openhat: .16, shaker: .2, rim: .45 };
  const QUIET_BASS = { 2: [1, 3] };
  const bass = [], sub = [], pad = [], keys = [], brass = [];
  for (let bar = 0; bar < BARS - 1; bar++) {
    const [root, octv, stab, chord] = CHART[bar % 4], b0 = bar * 4, quiet = QUIET_BASS[bar];
    for (let k = 0; k < 8; k++) {
      const b = k * .5; if (quiet && quiet[0] <= b && b < quiet[1]) continue;
      bass.push(`${gf(b0 + b)} ${k % 2 ? octv : root} .42 ${(k % 2 ? .52 : .62).toFixed(2)}`);
      if (k % 2) sub.push(`${gf(b0 + b - .02)} ${root} .4 .8`);
    }
    for (const k of [.5, 1.5, 2.5, 3.5]) { if (quiet && quiet[0] <= k && k < quiet[1]) continue; keys.push(`${gf(b0 + k)} ${stab} .3 ${(k === 1.5 || k === 3.5 ? .34 : .26).toFixed(2)}`); }
    if (bar >= 3) pad.push(`${gf(b0)} ${chord} 4 .3`);
  }
  for (const b of HITS) brass.push(`${gf(b)} ${CHART[Math.floor(b / 4) % 4][2]} .9 .62`);
  bass.push(`${gf(FINAL)} F1 4 .7`); sub.push(`${gf(FINAL)} F1 4 .9`);
  pad.push(`${gf(FINAL)} F3+Ab3+C4+F4+C5 4 .5`); keys.push(`${gf(FINAL)} F3+Ab3+C4+F4 3 .5`); brass.push(`${gf(FINAL)} F4+Ab4+C5 2 .7`);
  const run = (b0) => 'F5 Ab5 C6 Eb6 F6 Ab6 C7 Eb7 F7'.split(' ').map((n, i) => `${gf(b0 + i * .12)} ${n} .6 ${(.3 + i * .03).toFixed(2)}`);
  const sparkle = [...run(beat(SHINES[0]) + .1), ...run(beat(SPARK)), ...run(beat(SHINES[2]))].join('; ');
  const events = [
    { inst: 'synth_bass_1', vel: .9, notes: bass.join('; '), humanize: false },
    { inst: 'sub_bass', vel: 1.0, notes: sub.join('; '), humanize: false },
    { inst: 'electric_piano_1', vel: .8, notes: keys.join('; ') },
    { inst: 'pad_3_polysynth', vel: .6, notes: pad.join('; ') },
    { inst: 'synth_brass_1', vel: .8, notes: brass.join('; ') },
    { inst: 'glockenspiel', vel: .5, notes: sparkle },
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
  // 1. the pack: it pops up, its foil crinkles on the beat, it tears, the strip flies, the light comes out
  add(0, 'boom', -16, { sec: .8 });
  add(.02, 'swoosh_soft', -22, { sec: .45 });
  add(.12, 'pop', -22, { f0: 520, f1: 180, sec: .09 });
  add(.15, 'zip', -26, { sec: .3, f0: 600, f1: 2400 }); // the rarity wipes on
  for (const b of [1.0, 1.5, 2.0, 2.5]) add(b, 'crinkle', -27, { sec: .2, dens: 300, seed: Math.round(b * 4) }, { pan: (b % 1 ? .25 : -.25) });
  add(TEAR[0], 'crinkle', -15, { sec: TEAR[1] - TEAR[0] + .1, dens: 520, seed: 9 });
  add(TEAR[0] + .05, 'zip', -20, { sec: .4, f0: 2200, f1: 500 });
  add(TEAR[1] + .05, 'swoosh_soft', -21, { sec: .5 }, { pan: .5 });
  add(3.05, 'shimmer', -24, { sec: .9, f0: 500, f1: 3600 }, { send: .4 });
  // 2. the shot, the spin, the landing, the shine
  add(OUT - .05, 'whoosh', -12, { sec: .6, f0: 250, f1: 4600, peak: .7, curve: 1.3 });
  add(OUT, 'boom', -17, { sec: .6 });
  add(OUT + .15, 'whoosh', -24, { sec: .6, f0: 400, f1: 150 }, { pan: -.2 }); // the pack falls away
  for (const k of [.55, 1.05, 1.5]) add(OUT + k, 'swoosh_soft', -20 - k * 2, { sec: .35 });
  impact(LANDT, -13); add(LANDT, 'thunk', -15, { sec: .3 });
  add(SHINES[0], 'shimmer', -20, { sec: 1.0, f0: 800, f1: 5200 }, { send: .45 });
  add(SHINES[0] + .1, 'chime', -27, {}, { send: .4 });
  // 3. the card is read: a move and a landing for each stop (the feed's camera, the wide frame's lines)
  for (const s of STOPS) { add(s - .65, 'swoosh_soft', -22, { sec: .55 }); add(s, 'thunk', -20, { sec: .25 }); }
  add(STOPS[0] - .45, 'zip', -26, { sec: .3, f0: 500, f1: 2600 });
  for (let i = 0; i < 3; i++) add(STOPS[2] - .25 + i * .15, 'pop', -26, { f0: 700 + i * 140, f1: 260, sec: .08 }, { pan: -.3 + i * .3 });
  add(SHINES[1], 'shimmer', -25, { sec: .9, f0: 900, f1: 5000 }, { send: .4 });
  add(SHINES[2], 'shimmer', -23, { sec: .9, f0: 900, f1: 5000 }, { send: .4 });
  // 4. the tilt and its sparks
  add(TILT[0], 'swoosh_soft', -21, { sec: .7 }, { pan: .3 });
  add(SPARK - .05, 'shimmer', -17, { sec: 1.3, f0: 1200, f1: 6000 }, { send: .5 });
  add(SPARK, 'clink', -24, {}, { send: .4 });
  add(SPARK, 'sample', -20, { inst: 'celesta', notes: ['C6', 'F6', 'Ab6', 'C7'], every: .09, sec: 1.4 }, { send: .4 });
  add(19.0, 'swoosh_soft', -22, { sec: .6 }, { pan: -.3 });
  // 5. into the binder, then the event
  add(SLOT[0], 'whoosh', -15, { sec: SLOT[1] - SLOT[0], f0: 3200, f1: 300, peak: .6 });
  add(SLOT[1], 'thunk', -13, { sec: .35 }); add(SLOT[1], 'click', -20, { sec: .01, lo: 900, hi: 3000 });
  add(SLOT[1] + .05, 'zip', -24, { sec: .3, f0: 500, f1: 2600 });
  add(22.4, 'shimmer', -28, { sec: 1.2, f0: 600, f1: 3000 }, { send: .4 });
  const L0 = RECEDE[0] + .45;
  add(RECEDE[0], 'swoosh_soft', -22, { sec: .6 });
  add(L0 + .05, 'pop', -21, { f0: 520, f1: 180, sec: .09 });
  for (let i = 0; i < (LETTERS ? LETTERS.length : 9); i++) add(L0 + .14 + i * .035, 'tick', -28 + (i % 3), {}, { pan: -.4 + i * .1 });
  add(L0 + .45, 'keys', -31, { sec: .5, rate: 18 });
  add(LAST, 'crash', -21, { sec: 2.2 }, { send: .4 });
  add(L0 + .82, 'pop', -19, { f0: 500, f1: 160, sec: .12 }); add(L0 + .84, 'blip', -26, { f: 988, sec: .1 });
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
