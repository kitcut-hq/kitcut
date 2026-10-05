// For: the people who follow a conference on LinkedIn, X and YouTube, and its sponsors -- the organiser's featured-sponsor post; crisp, premium, celebratory
/* One sponsor of one conference in 26 s, no narration: the music carries it. A template: every word, colour,
   logo and metal is in content.json (SK.DATA.content); nothing of the event or the sponsor is in this code.
   The frame is the manifest's (1080 x 1080 first; 1920 x 1080 and 1080 x 1920 hold too): layouts read W, H.
     1 the blank (0-4)    a blank slides onto the anvil; the press's die carries the sponsor's logo; the tier
     2 the strike (4-8)   the die comes down on the bar, sparks, it lifts: the logo stands in relief
     3 the flip (8-12)    tossed, it spins in 3D and lands on its other face: the event's logo
     4 who (12-20)        the coin stands beside (or above) the name, their line and where to find them
     5 the tray (20-26)   it rolls along a tray of blank slots, drops into the first; the event signs off
   The coin is one component (two faces, a reeded edge with thickness, a metal), reused small in the tray.
   Logos are drawn as their files draw them, never recoloured: dark ink on the bright metal, a white logo
   on an enamel field of the ground colour. The clock below is the one home of the timing; the sound
   (SK.film({sound})) is worked out from it. */
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, TAU = SK.TAU, rnd = SK.rnd, PI = Math.PI;
const CX = W / 2, CY = H / 2, WIDE = W / H > 1.3, U = Math.min(W, H) / 1080, VS = clamp(H / W, 1, 1.5);
const D = SK.DATA.content, SP = D.sponsor || {}, EV = D.event || {};

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
function contrast(a, b) {
  const lum = (hex) => { const [r, g2, b2] = rgbOf(hex).map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * r + .7152 * g2 + .0722 * b2; };
  const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
function palette(p) {
  const light = p.light ?? '#FFFFFF', L = (hex) => hslOf(hex)[2];
  let ground = p.ground ?? '#113E82';
  while (contrast(ground, light) < 7 && L(ground) > .04) ground = withL(ground, L(ground) - .02);
  const g0 = L(ground);
  const d = { light, accent: p.accent, second: p.second, dark: p.dark ?? '#212326', enamel: ground, enamelLt: withL(ground, Math.min(.55, g0 * 1.5)),
    groundDk: withL(ground, g0 * .5), groundLt: withL(ground, Math.min(.6, g0 * 1.42)), soft: withL(ground, .86, .4),
    steelHi: withL(ground, .9, .12), steelLt: withL(ground, .72, .12), steel: withL(ground, .52, .13), steelDk: withL(ground, .32, .16), steelDeep: withL(ground, .17, .2) };
  d.shadow = rgbOf(withL(ground, g0 * .3)).join(',');
  return { ...d, ...p, ground };
}
const C = palette(D.palette || {});
SK.setStyle('clean', { grain: .4, vignette: .25, handheld: 0, vignetteRGB: C.shadow });
Object.assign(SK.C, { paper: C.ground, text: C.light, textSoft: C.soft, accent: C.accent, accentText: C.accent, ink: C.ground });
const FONTS = { head: 'Sofia Sans', body: 'Sofia Sans', ...(D.fonts || {}) }, FH = `"${FONTS.head}"`, FB = `"${FONTS.body}"`;

/* ------------------------------------------------------------------ the words, the metal, the logos */
const TIER = String(SP.tier ?? '').trim();
const VARS = { ...EV, tier: TIER, sponsor: SP.name ?? '' };
const words = (s) => String(s ?? '').replace(/\{(\w+)\}/g, (_, k) => VARS[k] ?? '').trim();
const COPY = Object.fromEntries(Object.entries(D.copy || {}).map(([k, v]) => [k, words(v)]));
const TIER_LINE = TIER ? COPY.tier : (COPY.featured || ''), COIN_LINE = TIER ? COPY.coin : '';
const FIND = String(SP.find || SP.link || '').trim();
function metalOf() {
  const M = D.metal || {}, name = TIER ? (M.tiers || {})[TIER.toUpperCase()] : null;
  if (name && Array.isArray(M[name])) return M[name];
  const b = SP.color || C.accent; // no tier: the sponsor's own colour
  return [withL(b, .88), withL(b, .68), withL(b, .48), withL(b, .28)];
}
const METAL = metalOf();
const SPL = SP.logo || {}, EVL = EV.logo || {};
const IMG = (k) => (k ? SK.IMG[k] : null);

/* ------------------------------------------------------------------ the clock (120 bpm: a beat .5 s, a bar 2 s) */
const HIT = 4.0, TOSS = 8.0, LAND = 10.0, STAND = 12.0, OUT = 19.55, ROLL = [20.25, 21.7], SETTLE = 22.0, LAST = 24.0;

/* ------------------------------------------------------------------ small helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (t) => { const c3 = k + 1; return 1 + c3 * Math.pow(t - 1, 3) + k * Math.pow(t - 1, 2); };
const outBack = back(1.5), outBackSoft = back(.9);
const font = (size, wt = 800, fam = FH) => `${wt} ${size}px ${fam}, "Sofia Sans", sans-serif`; // the second face carries the scripts the first lacks
function text(str, x, y, o = {}) {
  const c = g(); c.save(); c.font = font(o.size ?? 60, o.wt ?? 800, o.fam ?? FH);
  c.textAlign = o.align ?? 'left'; c.textBaseline = 'alphabetic'; c.letterSpacing = (o.ls ?? 0) + 'px';
  c.globalAlpha *= o.alpha ?? 1; c.fillStyle = o.col ?? C.light; c.fillText(str, x, y); c.restore();
}
function measure(str, o = {}) { const c = g(); c.save(); c.font = font(o.size ?? 60, o.wt ?? 800, o.fam ?? FH); c.letterSpacing = (o.ls ?? 0) + 'px'; const w = c.measureText(str).width; c.restore(); return w; }
const fit = (str, width, max, o = {}) => Math.min(max, max * width / Math.max(1, measure(str, { ...o, size: max })));
function wrap(str, width, o) {
  const out = []; let line = '';
  for (const w of String(str).split(/\s+/).filter(Boolean)) { const n = line ? line + ' ' + w : w; if (line && measure(n, o) > width) { out.push(line); line = w; } else line = n; }
  if (line) out.push(line); return out;
}
/** shrink, then wrap: the largest size from max to min at which str takes at most maxLines lines */
function fitBlock(str, width, max, min, maxLines, o = {}) {
  for (let s = max; s >= min; s -= 2) { const lines = wrap(str, width, { ...o, size: s }); if (lines.length <= maxLines && lines.every((l) => measure(l, { ...o, size: s }) <= width)) return { size: s, lines }; }
  const lines = wrap(str, width, { ...o, size: min }); return { size: Math.min(min, ...lines.map((l) => fit(l, width, min, o))), lines };
}
/** the same number of lines, evened: the narrowest width that still wraps str into n lines */
function balance(b, str, width, o = {}) {
  const n = b.lines.length; if (n < 2 || /…$/.test(b.lines[n - 1])) return b;
  let lo = width / n * .8, hi = width, best = b.lines;
  for (let i = 0; i < 12; i++) { const mid = (lo + hi) / 2, ls = wrap(str, mid, { ...o, size: b.size }); if (ls.length <= n && ls.every((l) => measure(l, { ...o, size: b.size }) <= width)) { best = ls; hi = mid; } else lo = mid; }
  return { size: b.size, lines: best };
}
/** a block of at most maxLines lines: shrink to min, then one more line at a smaller size, then cut with an ellipsis */
function clampBlock(str, width, max, min, maxLines, o = {}) {
  let b = fitBlock(str, width, max, min, maxLines, o);
  if (b.lines.length <= maxLines) return b;
  b = fitBlock(str, width, min, min * .8, maxLines + 1, o);
  if (b.lines.length <= maxLines + 1) return b;
  const lines = b.lines.slice(0, maxLines + 1); let last = lines[maxLines];
  while (last && measure(last + '…', { ...o, size: b.size }) > width) last = last.replace(/\s*\S+$/, '');
  lines[maxLines] = last.replace(/[\s,;:.]+$/, '') + '…';
  return { size: b.size, lines };
}
/** an address as people type it; when it cannot be read at `min`, its path is cut back, segment by segment */
function shortUrl(url, width, size, min, o = {}) {
  let u = String(url || '').trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/[/?#]+$/, '');
  while (fit(u, width, size, o) < min && /[/?#]/.test(u)) u = u.replace(/[/?#][^/?#]*$/, '');
  return u;
}
function rrect(x, y, w, h, r, fill) { const c = g(); SK.rrPath(x, y, w, h, r); c.fillStyle = fill; c.fill(); }
function disc(c, x, y, r, fill) { c.beginPath(); c.arc(x, y, r, 0, TAU); c.fillStyle = fill; c.fill(); }
const v3 = { sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2], k: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  n: (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; } };
const TOL = v3.n([-.45, -.8, -.45]); // towards the light: top left, in front
/** a logo's size inside a circle of radius rho, k of the way to its edge */
function logoFit(im, rho, k = .86) { const a = im.width / im.height, w = k * 2 * rho / Math.sqrt(1 + 1 / (a * a)); return { w, h: w / a }; }
/** a pill: text on a rounded bar; anchor x is its middle (or its left with o.left) */
function pill(str, x, y, o = {}) {
  const size = o.size ?? 28 * U, ls = o.ls ?? 2 * U, w = Math.min(o.max ?? W, measure(str, { size, wt: 700, ls }) + 2 * (o.pad ?? 26 * U)), h = o.h ?? size * 2;
  const sz = fit(str, w - 2 * (o.pad ?? 26 * U), size, { wt: 700, ls }), x0 = o.left ? x : x - w / 2;
  rrect(x0, y - h / 2, w, h, o.r ?? 6 * U, o.fill ?? C.accent);
  text(str, x0 + w / 2, y + sz * .36, { size: sz, wt: 700, ls, col: o.col ?? C.light, align: 'center' });
  return w;
}

/* ------------------------------------------------------------------ the coin: one drawn component */
const FS = 512; // a face is drawn on a FS x FS sheet and laid onto its disc in 3D
function metalFill(c, r, M, flip = false, soft = false) {
  const a = flip ? -1 : 1, gr = c.createLinearGradient(-r * .75 * a, -r * .75 * a, r * .75 * a, r * .75 * a);
  if (soft) { gr.addColorStop(0, M[0]); gr.addColorStop(.55, M[1]); gr.addColorStop(1, M[2]); }
  else { gr.addColorStop(0, M[1]); gr.addColorStop(.28, M[0]); gr.addColorStop(.62, M[2]); gr.addColorStop(1, M[3]); }
  return gr;
}
/** the image raised from the face: a lit edge above it, a shadow below -- its own colours untouched */
function relief(c, im, x, y, w, h, d, lit) {
  const k = c.getTransform().a; c.save();
  if (lit) { c.shadowColor = 'rgba(255,255,255,.85)'; c.shadowOffsetX = -d * .6 * k; c.shadowOffsetY = -d * .6 * k; c.shadowBlur = d * .4 * k; c.drawImage(im, x, y, w, h); }
  c.shadowColor = 'rgba(0,0,0,.45)'; c.shadowOffsetX = d * .7 * k; c.shadowOffsetY = d * k; c.shadowBlur = d * 1.1 * k; c.drawImage(im, x, y, w, h);
  c.restore();
}
/** a face: 'obv' (the sponsor's, blank until struck) or 'rev' (the event's). o: struck, sheen (-1..1 sweeps a glint) */
function coinFace(side, o = {}) {
  return (c, w) => {
    const r = w / 2, M = METAL, L = side === 'obv' ? SPL : EVL, enamel = L.ink === 'light', fr = r * .855;
    c.save(); c.translate(r, r);
    disc(c, 0, 0, r, metalFill(c, r, M));
    disc(c, 0, 0, r * .885, metalFill(c, r, M, true));
    if (enamel) { const eg = c.createRadialGradient(-r * .3, -r * .35, 0, 0, 0, fr); eg.addColorStop(0, C.enamelLt); eg.addColorStop(1, C.enamel); disc(c, 0, 0, fr, eg); }
    else disc(c, 0, 0, fr, metalFill(c, r, M, false, true));
    if (side === 'rev' || o.struck) {
      for (let i = 0; i < 84; i++) { const a = i / 84 * TAU, x = Math.cos(a) * r * .943, y = Math.sin(a) * r * .943; disc(c, x + r * .004, y + r * .006, r * .013, M[3]); disc(c, x - r * .003, y - r * .004, r * .009, M[0]); }
      const im = IMG(L.image), label = side === 'obv' ? COIN_LINE : COPY.coin_reverse, lift = label ? r * .08 : 0;
      if (im) { const s = logoFit(im, fr, label ? .84 : .9); relief(c, im, -s.w / 2, -s.h / 2 - lift, s.w, s.h, r * .016, !enamel); }
      else { // no logo file: the name stands on the face in type
        const nm = side === 'obv' ? String(SP.name || '') : [EV.name, EV.year].filter(Boolean).join(' '), col = enamel ? C.light : SK.mix(M[3], '#000000', .45);
        const b = balance(fitBlock(nm, fr * 1.42, r * .3, r * .1, 3, { wt: 800 }), nm, fr * 1.42, { wt: 800 });
        c.save(); c.shadowColor = enamel ? 'rgba(0,0,0,.4)' : 'rgba(255,255,255,.8)'; c.shadowOffsetX = c.shadowOffsetY = (enamel ? 2 : -1.5) * c.getTransform().a;
        b.lines.forEach((l, i) => text(l, 0, -lift + b.size * (.34 + (i - (b.lines.length - 1) / 2) * 1.04), { size: b.size, wt: 800, col, align: 'center' })); c.restore();
      }
      if (label) {
        const size = fit(label, fr * 1.2, r * .1, { wt: 800, ls: r * .02 });
        c.save(); c.shadowColor = enamel ? 'rgba(0,0,0,.4)' : 'rgba(255,255,255,.8)'; c.shadowOffsetX = c.shadowOffsetY = (enamel ? 2 : -1.5) * c.getTransform().a;
        text(label, 0, fr * .64, { size, wt: 800, ls: r * .02, col: enamel ? C.light : SK.mix(M[3], '#000000', .4), align: 'center' }); c.restore();
      }
    }
    const s = o.sheen ?? -9;
    if (s > -1.3 && s < 1.3) {
      c.globalCompositeOperation = 'source-atop';
      const gr = c.createLinearGradient(-r, -r * .6, r, r * .6), p = (s + 1) / 2;
      gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      for (const [u, a] of [[p - .13, 0], [p, .6], [p + .13, 0]]) if (u >= 0 && u <= 1) gr.addColorStop(u, `rgba(255,255,255,${a})`);
      c.fillStyle = gr; c.fillRect(-r, -r, 2 * r, 2 * r);
    }
    c.restore();
  };
}
/** the coin at x, y (radius R) turned rx, ry, rz: the edge strips that face the camera, then the face that does */
function coin(o) {
  const R = o.R, T = R * .17, d = 1800, pose = { x: o.x, y: o.y, z: 0, rx: o.rx, ry: o.ry ?? 0, rz: o.rz ?? 0 };
  SK.view3({ x: o.x, y: o.y, z: 0, sx: o.x, sy: o.y, d });
  const P = (p) => SK.pose3(p, pose), O = P([0, 0, 0]), cam = [o.x, o.y, -d], dir = (p) => v3.n(v3.sub(P(p), O)), c = g(), M = METAL;
  const N = 72;
  for (let i = 0; i < N; i++) {
    const a0 = i / N * TAU, a1 = (i + 1) / N * TAU, am = (a0 + a1) / 2, n = dir([Math.cos(am), Math.sin(am), 0]);
    if (v3.dot(n, v3.sub(P([R * Math.cos(am), R * Math.sin(am), 0]), cam)) >= 0) continue;
    const Q = [[a0, -T / 2], [a1, -T / 2], [a1, T / 2], [a0, T / 2]].map(([a, z]) => SK.proj3(P([R * Math.cos(a), R * Math.sin(a), z])));
    if (Q.some((q) => !q)) continue;
    let col = SK.mix(M[3], M[0], .12 + .88 * clamp(v3.dot(n, TOL))); if (i % 2) col = SK.mix(col, M[3], .2);
    c.beginPath(); Q.forEach((q, k) => (k ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]))); c.closePath();
    c.fillStyle = col; c.fill(); c.strokeStyle = col; c.lineWidth = 1.2; c.stroke();
  }
  const nF = dir([0, 0, -1]), front = v3.dot(nF, v3.sub(P([0, 0, -T / 2]), cam)) < 0;
  const corners = front ? [[-R, -R, -T / 2], [R, -R, -T / 2], [R, R, -T / 2], [-R, R, -T / 2]] : [[-R, R, T / 2], [R, R, T / 2], [R, -R, T / 2], [-R, -R, T / 2]];
  // (no shade: face3 lays it over the whole square sheet, and the coin is round)
  SK.face3(corners.map(P), FS, FS, front ? o.front : o.back, { cull: false, key: (o.key || 'coin') + (front ? 'F' : 'B') });
}

/* ------------------------------------------------------------------ 1-3: the press */
const FLAT = -.70, K = Math.cos(FLAT); // a coin lying flat, seen from above: its disc reads K as tall as wide
const ST = { x: CX, y: CY + 150 * U * VS, R: 230 * U, anvil: 290 * U, die: 248 * U, dieH: 190 * U, col: 410 * U, open: 440 * U };
const contactY = ST.y - 14 * U;
function dieY(t) {
  const top = ST.y - ST.open, low = top + 150 * U, up = low - 95 * U; // it creeps down, draws back, then slams
  if (t < .9) return top;
  if (t < 3.2) return lerp(top, low, E.inOut((t - .9) / 2.3)) + 2.5 * U * Math.sin(t * 46) * clamp((t - .9) * 2);
  if (t < 3.72) return lerp(low, up, E.out((t - 3.2) / .52));
  if (t < HIT) return lerp(up, contactY, E.in((t - 3.72) / .28));
  if (t < 4.22) return contactY;
  return lerp(contactY, ST.y - 1500 * U * VS, E.inOut(clamp((t - 4.22) / 1.5)));
}
function cylinder(x, yTop, yBot, r, top) { // a steel cylinder standing upright, seen from a little above
  const c = g(), ry = r * K, gr = c.createLinearGradient(x - r, 0, x + r, 0);
  [[0, C.steelDk], [.16, C.steel], [.34, C.steelHi], [.56, C.steelLt], [.86, C.steel], [1, C.steelDeep]].forEach(([u, col]) => gr.addColorStop(u, col));
  c.beginPath(); c.moveTo(x - r, yTop); c.lineTo(x - r, yBot); c.ellipse(x, yBot, r, ry, 0, PI, 0, true); c.lineTo(x + r, yTop); c.closePath(); c.fillStyle = gr; c.fill();
  if (top) { const tg = c.createLinearGradient(x - r, yTop - ry, x + r, yTop + ry); tg.addColorStop(0, C.steelHi); tg.addColorStop(1, C.steel); c.beginPath(); c.ellipse(x, yTop, r, ry, 0, 0, TAU); c.fillStyle = tg; c.fill(); }
}
function pressStage(t) { // the columns, the feed rail, the anvil and the tier on its front
  const c = g(), yA = ST.y + 16 * U, drop = 1400 * U * VS * E.in(clamp((t - STAND) / .6));
  c.save(); c.translate(0, drop);
  for (const sd of [-1, 1]) {
    const x = ST.x + sd * ST.col, cg = c.createLinearGradient(x - 33 * U, 0, x + 33 * U, 0);
    cg.addColorStop(0, C.steelDk); cg.addColorStop(.4, C.steelLt); cg.addColorStop(1, C.steelDeep);
    c.fillStyle = cg; c.fillRect(x - 33 * U, -2000 * U, 66 * U, yA + 2600 * U);
    rrect(x - 46 * U, yA - 40 * U, 92 * U, 60 * U, 8 * U, C.steelDk);
  }
  const hw = ST.R * 1.08 * K; // the feed rail the blank slides in on
  c.fillStyle = C.steel; c.fillRect(-200 * U, yA - hw, ST.x - ST.anvil * .6 + 200 * U, 2 * hw);
  c.fillStyle = C.steelLt; c.fillRect(-200 * U, yA - hw, ST.x - ST.anvil * .6 + 200 * U, 10 * U);
  c.fillStyle = C.steelDk; c.fillRect(-200 * U, yA + hw, ST.x - ST.anvil * .6 + 200 * U, 34 * U);
  cylinder(ST.x, yA, yA + 1400 * U, ST.anvil, true);
  c.strokeStyle = `rgba(${C.shadow},.35)`; c.lineWidth = 3 * U; c.beginPath(); c.ellipse(ST.x, yA, ST.anvil * .9, ST.anvil * .9 * K, 0, 0, TAU); c.stroke();
  const a = ease(t, 1.2, 1.65, outBack);
  if (TIER_LINE && a > 0) SK.at(ST.x, yA + ST.anvil * K + 92 * U, 0, a, () => pill(TIER_LINE, 0, 0, { size: 40 * U, ls: 5 * U, h: 84 * U, max: W - 120 * U }));
  c.restore();
}
function dieAndSparks(t) {
  const c = g(), yd = dieY(t), gap = Math.max(0, contactY - yd);
  if (gap < 320 * U) { c.fillStyle = `rgba(${C.shadow},${.5 * (1 - gap / (320 * U))})`; c.beginPath(); c.ellipse(ST.x, ST.y + 6 * U, ST.die, ST.die * K, 0, 0, TAU); c.fill(); }
  const yk = yd - ST.dieH - 36 * U, yg = c.createLinearGradient(0, yk - 60 * U, 0, yk + 60 * U); // the yoke rides the columns with the ram
  yg.addColorStop(0, C.steelLt); yg.addColorStop(.5, C.steel); yg.addColorStop(1, C.steelDeep);
  c.save(); c.shadowColor = `rgba(${C.shadow},.45)`; c.shadowBlur = 18 * U; c.shadowOffsetY = 10 * U; rrect(ST.x - ST.col - 60 * U, yk - 60 * U, 2 * ST.col + 120 * U, 120 * U, 16 * U, yg); c.restore();
  c.fillStyle = C.steelHi; c.globalAlpha = .55; c.fillRect(ST.x - ST.col - 44 * U, yk - 52 * U, 2 * ST.col + 88 * U, 5 * U); c.globalAlpha = 1;
  for (const sd of [-1, 1]) { rrect(ST.x + sd * ST.col - 50 * U, yk - 78 * U, 100 * U, 156 * U, 12 * U, C.steelDk); rrect(ST.x + sd * ST.col - 50 * U, yk - 78 * U, 100 * U, 10 * U, 5 * U, C.steelLt);
    for (const by of [-44, 44]) disc(c, ST.x + sd * (ST.col - 110 * U), yk + by * U * .5, 7 * U, C.steelDeep); }
  cylinder(ST.x, -3000 * U, yd - ST.dieH + 20 * U, 92 * U, false); // the ram
  cylinder(ST.x, yd - ST.dieH, yd, ST.die, false); // the die
  const gl = (t - 1.5) / 1.3; // a light runs across the die as it comes down
  if (gl > 0 && gl < 1) { c.save(); c.beginPath(); c.rect(ST.x - ST.die, yd - ST.dieH, 2 * ST.die, ST.dieH + ST.die * K); c.clip();
    const gx = ST.x - ST.die * 1.4 + gl * ST.die * 2.8, gg = c.createLinearGradient(gx - 70 * U, 0, gx + 70 * U, 0); gg.addColorStop(0, 'rgba(255,255,255,0)'); gg.addColorStop(.5, `rgba(255,255,255,${.55 * Math.sin(gl * PI)})`); gg.addColorStop(1, 'rgba(255,255,255,0)');
    c.transform(1, 0, -.35, 1, 0, 0); c.fillStyle = gg; c.fillRect(gx - 70 * U + .35 * yd, yd - ST.dieH - 40 * U, 140 * U, ST.dieH + ST.die); c.restore(); }
  c.fillStyle = `rgba(${C.shadow},.35)`; c.beginPath(); c.ellipse(ST.x, yd, ST.die, ST.die * K, 0, 0, PI); c.ellipse(ST.x, yd - 22 * U, ST.die, ST.die * K, 0, PI, 0, true); c.fill();
  // the sponsor's logo on a plate on the die, as its file draws it
  const pw = 360 * U, ph = 104 * U, py = yd - ST.dieH * .55, im = IMG(SPL.image);
  const pg = c.createLinearGradient(0, py - ph / 2, 0, py + ph / 2); pg.addColorStop(0, '#FFFFFF'); pg.addColorStop(1, '#E4E8EE');
  c.save(); c.shadowColor = `rgba(${C.shadow},.5)`; c.shadowBlur = 12 * U; c.shadowOffsetY = 5 * U; rrect(ST.x - pw / 2, py - ph / 2, pw, ph, 10 * U, SPL.ink === 'light' ? C.enamel : pg); c.restore();
  for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) disc(c, ST.x + sx * (pw / 2 - 13 * U), py + sy * (ph / 2 - 13 * U), 4.5 * U, C.steel);
  if (im) { const s = Math.min((pw - 70 * U) / im.width, (ph - 34 * U) / im.height); c.drawImage(im, ST.x - im.width * s / 2, py - im.height * s / 2, im.width * s, im.height * s); }
  const age = t - HIT; if (age < 0 || age > .95) return;
  c.save(); c.lineCap = 'round';
  const f = 1 - clamp(age / .3);
  if (f > 0) { c.globalAlpha = .55 * f; c.fillStyle = '#FFFFFF'; c.beginPath(); c.ellipse(ST.x, ST.y, ST.die * (1 + age * 2.5), ST.die * K * (1 + age * 2.5), 0, 0, TAU); c.fill(); }
  const rg = clamp(age / .55); // the ring the blow sends across the anvil
  if (rg < 1) { c.globalAlpha = .7 * (1 - rg); c.strokeStyle = '#FFFFFF'; c.lineWidth = (14 - 10 * rg) * U; c.beginPath(); c.ellipse(ST.x, ST.y, ST.die * (1 + 1.6 * E.out(rg)), ST.die * K * (1 + 1.6 * E.out(rg)), 0, 0, TAU); c.stroke(); }
  for (let i = 0; i < 72; i++) {
    const a = rnd(i * 7 + 1) * TAU, v = (650 + rnd(i * 13 + 2) * 950) * U, up = (250 + rnd(i * 17 + 3) * 600) * U, life = .4 + rnd(i * 5 + 4) * .5;
    if (age > life) continue;
    const x0 = ST.x + Math.cos(a) * ST.die, y0 = ST.y + Math.sin(a) * ST.die * K;
    const px = (q) => x0 + Math.cos(a) * v * q, py2 = (q) => y0 + Math.sin(a) * v * K * q - up * q + 1500 * U * q * q, q0 = Math.max(0, age - .04);
    c.globalAlpha = 1 - age / life; c.strokeStyle = [C.second, '#FFFFFF', C.second, C.accent][i % 4]; c.lineWidth = (3 + rnd(i + 9) * 3) * U;
    c.beginPath(); c.moveTo(px(q0), py2(q0)); c.lineTo(px(age), py2(age)); c.stroke();
  }
  c.restore();
}

/* ------------------------------------------------------------------ 4: who they are */
const INFO_OUT = OUT - .5; // the words are gone before the tray comes up
let _lay = null;
/** the scene's layout, worked out once type can be measured: the coin large, the words beside it (wide) or under it */
function LAY() {
  if (_lay) return _lay;
  const L = WIDE ? { x: W * .5, w: W * .44, align: 'left' } : { x: CX, w: W - 130 * U, align: 'center' };
  const blocks = (k) => { // the words at scale k
    const B = [];
    if (TIER_LINE) B.push({ k: 'tier', h: 60 * U * k, t0: 12.55 });
    const nm = balance(fitBlock(SP.name || '', L.w, (WIDE ? 136 : 108) * U * k, 48 * U, 2, { wt: 800 }), SP.name || '', L.w, { wt: 800 });
    B.push({ k: 'name', h: nm.lines.length * nm.size * 1.02, nm, t0: 12.7 });
    if (SP.line) { const o = { wt: 600, fam: FB }, ln = balance(clampBlock(SP.line, L.w, (WIDE ? 46 : 42) * U * k, (WIDE ? 36 : 34) * U * Math.min(k, 1.15), 3, o), SP.line, L.w, o); B.push({ k: 'line', h: ln.lines.length * ln.size * 1.3, ln, t0: 12.9 }); }
    if (FIND) B.push({ k: 'find', h: 78 * U * k, t0: 13.3 });
    return { B, gap: 26 * U * k, total: B.reduce((a, b) => a + b.h, 0) + 26 * U * k * (B.length - 1) };
  };
  // the largest type the frame has room for, the coin never smaller than it should be
  const TALL = VS > 1.2, Rmin = (WIDE ? 300 : TALL ? 300 : 215) * U, room = (k) => (WIDE ? H - 240 * U : H - 110 * U - 2 * Rmin - 80 * U * k);
  let k = WIDE ? 1.35 : TALL ? 1.6 : 1.3, G = blocks(k);
  while (k > 1 && G.total > room(k)) { k = +(k - .05).toFixed(2); G = blocks(k); }
  if (WIDE) { // the coin and the words are one pair, centred
    let tw = 0; for (const b of G.B) { if (b.k === 'name') for (const l of b.nm.lines) tw = Math.max(tw, measure(l, { size: b.nm.size, wt: 800 })); if (b.k === 'line') for (const l of b.ln.lines) tw = Math.max(tw, measure(l, { size: b.ln.size, wt: 600, fam: FB })); }
    tw = clamp(tw, 420 * U, L.w); L.R = 310 * U; const x0 = (W - (2 * L.R + 110 * U + tw)) / 2;
    L.cx = x0 + L.R; L.x = x0 + 2 * L.R + 110 * U; L.cy = CY; L.top = CY - G.total / 2; }
  else { // the coin and the words are one group, centred in the frame
    L.R = clamp((H - 110 * U - G.total - 80 * U * k) / 2, 150 * U, (TALL ? 330 : 240) * U);
    const y0 = (H - (2 * L.R + 80 * U * k + G.total)) / 2; L.cx = CX; L.cy = y0 + L.R; L.top = L.cy + L.R + 80 * U * k;
  }
  let y = L.top; for (const b of G.B) { b.y = y; y += b.h + G.gap; }
  L.B = G.B; L.TS = k; return (_lay = L);
}
function info(t) {
  const L = LAY(), TS = L.TS, left = L.align === 'left', out = ease(t, INFO_OUT, INFO_OUT + .3, E.in);
  for (const b of L.B) {
    const a = ease(t, b.t0, b.t0 + .45, E.out) * (1 - out); if (a <= 0) continue;
    SK.at(-out * 50 * U, (1 - a) * 34 * U, 0, 1, () => SK.alpha(a, () => {
      if (b.k === 'tier') pill(TIER_LINE, L.x, b.y + b.h / 2, { size: 28 * U * TS, ls: 4 * U, h: b.h, left, max: L.w });
      if (b.k === 'name') b.nm.lines.forEach((l, i) => text(l, L.x, b.y + b.nm.size * (.78 + i * 1.02), { size: b.nm.size, wt: 800, align: L.align }));
      if (b.k === 'line') b.ln.lines.forEach((l, i) => SK.alpha(ease(t, b.t0 + i * .08, b.t0 + i * .08 + .4), () => text(l, L.x, b.y + b.ln.size * (.92 + i * 1.3), { size: b.ln.size, wt: 600, fam: FB, col: C.soft, align: L.align })));
      if (b.k === 'find') pill(`${FIND}  ${COPY.arrow ?? ''}`.trim(), L.x, b.y + b.h / 2, { size: 38 * U * TS, ls: 1 * U, h: b.h, pad: 34 * U, r: 10 * U, fill: C.second, col: C.dark, left, max: L.w });
    }));
  }
}

/* ------------------------------------------------------------------ 5: the tray and the sign-off */
const Y5 = (y) => CY + (y - 540) * U * VS;
// wide: the tray on the left, the event's sign-off on the right; otherwise one centred column
const SG = WIDE ? { x: W * .25, y: CY - 30 * U, cx: W * .735, w: W * .45, logo: CY - 215 * U, dates: CY + 8 * U, venue: CY + 62 * U, url: CY + 190 * U, more: CY + 395 * U, mw: W * .46 }
  : { x: CX, y: Y5(628), cx: CX, w: W - 120 * U, logo: Y5(172), dates: Y5(330), venue: Y5(380), url: Y5(1004), more: Y5(925), mw: W - 120 * U };
const TR = { x: SG.x, y: SG.y, w: WIDE ? 760 * U : Math.min(W - 200 * U, 900 * U), d: 500 * U, th: 50 * U, cols: 3, rows: 2 };
TR.rs = Math.min(TR.w / TR.cols, TR.d / TR.rows) * .41;
const trayY = (t) => lerp(TR.y + 1100 * U * VS, TR.y, outBackSoft(ease(t, 19.6, 20.3, E.lin)));
function trayProj(p, y = TR.y) { SK.view3({ x: TR.x, y, z: 0, sx: TR.x, sy: y, d: 1800 }); return SK.proj3(SK.pose3(p, { x: TR.x, y, z: 0, rx: FLAT })); }
const slotLocal = (i) => [-TR.w / 2 + TR.w / TR.cols * (i % TR.cols + .5), -TR.d / 2 + TR.d / TR.rows * (Math.floor(i / TR.cols) + .5), 0];
function rollGeom() {
  const qb = trayProj([0, -TR.d / 2, 0]), R = TR.rs * .86 * 1800 / qb[2], q0 = trayProj(slotLocal(0));
  return { R, y: qb[1] - R - 3 * U, xs: trayProj([TR.w / 2, -TR.d / 2, 0])[0] - R * 1.2, xe: q0[0], sx: q0[0], sy: q0[1], Rs: TR.rs * .86 * 1800 / q0[2] };
}
function trayTop(c, w, d, t) {
  const m = 22 * U, sg = c.createLinearGradient(0, 0, 0, d); sg.addColorStop(0, C.steelLt); sg.addColorStop(1, C.steel);
  SK.rrPath(0, 0, w, d, 26 * U); c.fillStyle = sg; c.fill();
  SK.rrPath(m, m, w - 2 * m, d - 2 * m, 14 * U); c.fillStyle = C.groundDk; c.fill();
  for (let i = 0; i < TR.cols * TR.rows; i++) {
    const [lx, ly] = slotLocal(i), x = lx + w / 2, y = ly + d / 2, r = TR.rs;
    const rg = c.createLinearGradient(0, y - r, 0, y + r); rg.addColorStop(0, '#050B1C'); rg.addColorStop(1, C.ground);
    disc(c, x, y, r, rg);
    c.strokeStyle = 'rgba(255,255,255,.18)'; c.lineWidth = 3 * U; c.beginPath(); c.arc(x, y, r, .15 * PI, .85 * PI); c.stroke();
    if (i === 0) continue;
    c.strokeStyle = 'rgba(255,255,255,.22)'; c.lineWidth = 4 * U; c.lineCap = 'round'; c.beginPath(); c.moveTo(x - r * .22, y); c.lineTo(x + r * .22, y); c.moveTo(x, y - r * .22); c.lineTo(x, y + r * .22); c.stroke();
    const p = Math.pow(Math.max(0, Math.sin((t - 20.6) * 2.4 - i * .55)), 6) * clamp((t - 20.6) * 2);
    if (p > .01) { c.strokeStyle = C.second; c.globalAlpha = p * .8; c.lineWidth = 4 * U; c.beginPath(); c.arc(x, y, r * 1.12, 0, TAU); c.stroke(); c.globalAlpha = 1; }
  }
}
function tray(t) {
  const y = trayY(t), w = TR.w, d = TR.d;
  SK.view3({ x: TR.x, y, z: 0, sx: TR.x, sy: y, d: 1800 });
  const P = (p) => SK.pose3(p, { x: TR.x, y, z: 0, rx: FLAT });
  SK.poly3([P([-w / 2, d / 2, 0]), P([w / 2, d / 2, 0]), P([w / 2, d / 2, TR.th]), P([-w / 2, d / 2, TR.th])], C.steelDk, { light: false });
  SK.face3([P([-w / 2, -d / 2, 0]), P([w / 2, -d / 2, 0]), P([w / 2, d / 2, 0]), P([-w / 2, d / 2, 0])], w, d, (c) => trayTop(c, w, d, t), { cull: false, key: 'tray' });
}
function signoff(t) {
  const c = g();
  if (COPY.more) { const sz = fit(COPY.more, SG.mw, 40 * U, { wt: 800, ls: 6 * U }), full = measure(COPY.more, { size: sz, wt: 800, ls: 6 * U }), n = Math.ceil(clamp((t - 20.35) / .6) * COPY.more.length);
    text(COPY.more.slice(0, n), SG.x - full / 2, SG.more, { size: sz, wt: 800, ls: 6 * U, col: C.second }); }
  const im = IMG(EVL.image), la = ease(t, 22.3, 22.8, outBackSoft);
  if (im && la > 0) {
    const w = Math.min(580 * U, SG.w, 196 * U * im.width / im.height), h = w * im.height / im.width;
    SK.alpha(clamp(la), () => { if (EVL.ink === 'dark') rrect(SG.cx - w / 2 - 24 * U, SG.logo - h / 2 - 20 * U, w + 48 * U, h + 40 * U, 14 * U, C.light); c.drawImage(im, SG.cx - w / 2, SG.logo - h / 2 + (1 - la) * 30 * U, w, h); });
  } else if (!im && EV.name && la > 0) SK.alpha(clamp(la), () => { const nm = fitBlock([EV.name, EV.year].filter(Boolean).join(' '), SG.w, 84 * U, 40 * U, 2, { wt: 800 }); nm.lines.forEach((l, i) => text(l, SG.cx, SG.logo + nm.size * (.36 + (i - (nm.lines.length - 1) / 2) * 1.04), { size: nm.size, wt: 800, align: 'center' })); });
  const line = [EV.dates, EV.city].filter(Boolean).join('  ·  ');
  if (line) SK.alpha(ease(t, 22.5, 22.9), () => text(line, SG.cx, SG.dates, { size: fit(line, SG.w, 46 * U, { wt: 800, ls: 2 * U }), wt: 800, ls: 2 * U, align: 'center' }));
  if (EV.venue) SK.alpha(ease(t, 22.62, 23.0), () => text(EV.venue, SG.cx, SG.venue, { size: fit(EV.venue, SG.w, 30 * U, { wt: 600, ls: 4 * U }), wt: 600, ls: 4 * U, col: C.soft, align: 'center' }));
  const pa = ease(t, 22.85, 23.25, outBack) * (1 + .06 * Math.exp(-Math.max(0, t - LAST) * 6) * (t > LAST));
  if (EV.url && pa > 0) { const u = shortUrl(EV.url, SG.w - 80 * U, 34 * U, 25 * U, { wt: 700, ls: 1 * U }); SK.at(SG.cx, SG.url, 0, pa, () => pill(u, 0, 0, { size: 34 * U, ls: 1 * U, h: 76 * U, pad: 40 * U, r: 10 * U, max: SG.w })); }
}

/* ------------------------------------------------------------------ the coin's path through the film */
function standPose(t) {
  const s = clamp((t - 12.8) / .6), q = t - 12.8;
  const L = LAY(); return { x: L.cx, y: L.cy + Math.sin(q * 1.6) * 7 * U * s, R: L.R, rx: -4 * PI + .06 * Math.sin(q * 1.3) * s, ry: .5 * Math.sin(q * .9) * s, rz: 0 };
}
function coinAt(t) {
  const R0 = ST.R;
  if (t < TOSS) return { x: lerp(ST.x - CX - ST.R * 2 - 200 * U, ST.x, outBackSoft(clamp((t - .1) / 1.05))), y: ST.y, R: R0, rx: FLAT, ry: 0, rz: 0 };
  if (t < LAND) { const u = (t - TOSS) / (LAND - TOSS); return { x: ST.x, y: ST.y - 400 * U * 4 * u * (1 - u), R: R0, rx: FLAT - 3 * PI * (.4 * u + .6 * E.sine(u)), ry: 0, rz: .2 * Math.sin(u * PI), h: 4 * u * (1 - u) }; }
  if (t < STAND) { const b = t - LAND; return { x: ST.x, y: ST.y - 26 * U * Math.abs(Math.sin(b * 10)) * Math.exp(-b * 7), R: R0, rx: FLAT - 3 * PI + .1 * Math.sin(b * 16) * Math.exp(-b * 6), ry: 0, rz: 0 }; }
  if (t < OUT) { const u = E.inOut(clamp((t - STAND) / .8)), S = standPose(t); return { x: lerp(ST.x, S.x, u), y: lerp(ST.y, S.y, u) - 140 * U * Math.sin(PI * u), R: lerp(R0, S.R, u), rx: lerp(FLAT - 3 * PI, S.rx, u), ry: S.ry * u, rz: 0 }; }
  const S0 = standPose(OUT), G = rollGeom();
  if (t < ROLL[0]) { const u = E.inOut(clamp((t - OUT) / (ROLL[0] - OUT))); return { x: lerp(S0.x, G.xs, u), y: lerp(S0.y, G.y, u) - 70 * U * Math.sin(PI * u), R: lerp(S0.R, G.R, u), rx: lerp(S0.rx, -4 * PI, u), ry: lerp(S0.ry, 0, u), rz: 0 }; }
  if (t < ROLL[1]) { const x = lerp(G.xs, G.xe, E.sine((t - ROLL[0]) / (ROLL[1] - ROLL[0]))); return { x, y: G.y, R: G.R, rx: -4 * PI, ry: 0, rz: (x - G.xs) / G.R }; }
  const rzE = (G.xe - G.xs) / G.R, rzT = Math.round(rzE / TAU) * TAU;
  if (t < SETTLE) { const v = clamp((t - ROLL[1]) / (SETTLE - ROLL[1])), u = E.in(v); return { x: G.xe, y: lerp(G.y, G.sy, u), R: lerp(G.R, G.Rs, u), rx: -4 * PI + FLAT * u, ry: 0, rz: lerp(rzE, rzT, E.inOut(v)) }; }
  const b = t - SETTLE; return { x: G.sx, y: G.sy - 8 * U * Math.abs(Math.sin(b * 12)) * Math.exp(-b * 9), R: G.Rs, rx: -4 * PI + FLAT, ry: 0, rz: rzT };
}
const sweep = (t, wins) => { for (const [a, b] of wins) if (t >= a && t <= b) return lerp(-1.3, 1.3, (t - a) / (b - a)); return -9; };
function drawCoin(t) {
  const s = coinAt(t), c = g();
  if (s.h !== undefined) { c.fillStyle = `rgba(${C.shadow},${.45 * (1 - .6 * s.h)})`; c.beginPath(); c.ellipse(ST.x, ST.y + 10 * U, ST.R * (1 - .35 * s.h), ST.R * K * (1 - .35 * s.h), 0, 0, TAU); c.fill(); }
  const sa = ease(t, 12.3, 12.8) * (1 - ease(t, OUT, OUT + .4));
  if (sa > 0) SK.alpha(sa, () => { const r = c.createRadialGradient(s.x, s.y + s.R * 1.18, 0, s.x, s.y + s.R * 1.18, s.R * .8); r.addColorStop(0, `rgba(${C.shadow},.55)`); r.addColorStop(1, `rgba(${C.shadow},0)`); c.fillStyle = r; c.save(); c.translate(s.x, s.y + s.R * 1.18); c.scale(1, .14); c.translate(-s.x, -s.y - s.R * 1.18); c.beginPath(); c.arc(s.x, s.y + s.R * 1.18, s.R * .8, 0, TAU); c.fill(); c.restore(); });
  coin({ ...s, key: 'hero', front: coinFace('obv', { struck: t >= HIT, sheen: sweep(t, [[1.3, 2.2], [4.9, 5.8], [6.6, 7.5], [13.0, 13.9], [15.4, 16.3], [17.6, 18.5], [LAST, LAST + .8]]) }), back: coinFace('rev', { sheen: sweep(t, [[10.15, 11.0]]) }) });
}

/* ------------------------------------------------------------------ the camera and the film */
const PRESS = (() => { // the whole press in the frame at the start: from the yoke to the tier line
  const top = ST.y - ST.open - ST.dieH - 130 * U, bot = ST.y + 16 * U + ST.anvil * K + 92 * U + (TIER_LINE ? 70 : -40) * U;
  return [ST.x, (top + bot) / 2, Math.min(1, H * .95 / (bot - top), W * .95 / (2 * ST.col + 200 * U))];
})();
function camera(t) { // [x, y, zoom]: the stage point at the frame's middle
  const P = PRESS, A = (q) => SK.kf(q, [[0, [P[0], P[1] - 30 * U, P[2] * .94]], [3.7, [P[0], P[1] + 20 * U, P[2] * 1.04]], [4.6, [ST.x, ST.y - 60 * U, 1.12]], [7.7, [ST.x, ST.y + 44 * U, 1.4]], [8.35, [ST.x, ST.y - 190 * U, 1.08]], [9.6, [ST.x, ST.y - 100 * U, 1.12]], [10.2, [ST.x, ST.y - 20 * U, 1.3]], [11.95, [ST.x, ST.y + 62 * U, 1.5]]]);
  let v;
  if (t < STAND) v = A(t);
  else if (t < 12.8) { const u = E.inOut((t - STAND) / .8), a = A(STAND); v = [lerp(a[0], CX, u), lerp(a[1], CY, u), lerp(a[2], 1, u)]; }
  else v = [CX, CY, 1 + .035 * E.sine(clamp((t - SETTLE) / 4))];
  if (t > HIT && t < HIT + 1) v = [v[0], v[1], v[2] * (1 + .09 * Math.exp(-(t - HIT) / .11))]; // the blow kicks the camera in
  return v;
}
function shake(t) {
  let x = 0, y = 0;
  for (const [h, a, w] of [[HIT, 30, .16], [LAND, 8, .1], [SETTLE, 5, .08]]) if (t > h) { const k = a * U * Math.exp(-(t - h) / w); x += k * Math.sin((t - h) * 83); y += k * .8 * Math.cos((t - h) * 71); }
  return [x, y];
}
function backdrop(t) {
  const c = g(), gr = c.createRadialGradient(CX, CY * .9, 0, CX, CY, Math.hypot(W, H) * .62);
  gr.addColorStop(0, C.groundLt); gr.addColorStop(.55, C.ground); gr.addColorStop(1, C.groundDk);
  c.fillStyle = gr; c.fillRect(0, 0, W, H);
  const st = 48 * U, ox = (t * 9 * U) % st, oy = (t * 5 * U) % st; c.fillStyle = 'rgba(255,255,255,.07)';
  for (let y = -st + oy; y < H + st; y += st) for (let x = -st + ox; x < W + st; x += st) c.fillRect(x, y, 2.4 * U, 2.4 * U);
}
function draw(t) {
  const c = g(), [fx, fy, z] = camera(t), [sx, sy] = shake(t);
  backdrop(t);
  c.save(); c.translate(CX + sx, CY + sy); c.scale(z, z); c.translate(-fx, -fy);
  if (t < 12.8) pressStage(t);
  if (t >= OUT) { tray(t); signoff(t); }
  drawCoin(t);
  if (t < 6.4) dieAndSparks(t);
  c.restore();
  if (t >= HIT && t < HIT + .4) { c.save(); c.globalAlpha = .6 * Math.exp(-(t - HIT) / .08); c.fillStyle = '#FFFFFF'; c.fillRect(0, 0, W, H); c.restore(); } // the flash of the blow
  if (t >= 12.4 && t < INFO_OUT + .32) info(t);
}

/* ------------------------------------------------------------------ the sound, from the clock and the content
   A 120 bpm groove in F minor: a build into the strike, a stab on every hit, the groove holding its breath
   for the toss, a roll into the tray and a last chord at LAST. */
const BPM = 120, beat = (t) => t * BPM / 60, gf = (x) => String(+x.toPrecision(6));
function scoreData() {
  const CHART = [['F1', 'F2', 'Ab3+C4+F4', 'F3+Ab3+C4+Eb4'], ['Db2', 'Db3', 'Ab3+Db4+F4', 'Db3+F3+Ab3+C4'], ['Ab1', 'Ab2', 'Ab3+C4+Eb4', 'Ab3+C4+Eb4+G4'], ['Eb2', 'Eb3', 'G3+Bb3+Eb4', 'Eb3+G3+Bb3+Db4']];
  const BARS = Math.round(SK._film.duration / (240 / BPM)), HITS = [HIT, LAND, STAND, SETTLE].map(beat), FINAL = beat(LAST);
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', openhat: '..x...x...x...x.', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
  const FULL = { ...GROOVE, rim: '...o..o....o..o.' };
  const DRUMS = [
    { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.' }, // 0: the blank slides in
    { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.', snare: '........ooxxxxXX' }, // 1: the press winds down, a roll into the strike
    { ...GROOVE, kick: 'X...x...x...x...' }, GROOVE, // 2-3: the strike and the reveal
    { hat: 'oooooooooooooooo', snare: '............oxxX' }, // 4: the toss, held breath
    { ...FULL, kick: 'X...x...x...x...' }, FULL, FULL, FULL, // 5-8: the landing; who they are
    { ...FULL, snare: '............oxxX' }, // 9: into the tray
    { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o', snare: '..........ooxxxX' }, // 10: the roll
    { ...GROOVE, kick: 'X...x...x...x...', snare: '............oxxX' }, // 11: in the slot, the sign-off
    { kick: 'X...............', openhat: 'x...............' }, // 12: the last chord
  ];
  const KIT_GAINS = { kick: 1.15, snare: .42, clap: .42, hat: .26, openhat: .16, shaker: .2, rim: .45 };
  const QUIET = { 4: [1, 4] };
  const bass = [], sub = [], pad = [], keys = [], brass = [];
  for (let bar = 0; bar < BARS - 1; bar++) {
    const [root, octv, stab, chord] = CHART[bar % 4], b0 = bar * 4, q = QUIET[bar];
    for (let k = 0; k < 8; k++) { const b = k * .5; if (q && q[0] <= b && b < q[1]) continue; bass.push(`${gf(b0 + b)} ${k % 2 ? octv : root} .42 ${(k % 2 ? .52 : .62).toFixed(2)}`); if (k % 2) sub.push(`${gf(b0 + b - .02)} ${root} .4 .8`); }
    if (bar >= 2) for (const k of [.5, 1.5, 2.5, 3.5]) { if (q && q[0] <= k && k < q[1]) continue; keys.push(`${gf(b0 + k)} ${stab} .3 ${(k === 1.5 || k === 3.5 ? .34 : .26).toFixed(2)}`); }
    pad.push(`${gf(b0)} ${chord} 4 ${bar < 2 ? .22 : .3}`);
  }
  for (const b of HITS) brass.push(`${gf(b)} ${CHART[Math.floor(b / 4) % 4][2]} .9 .62`);
  bass.push(`${gf(FINAL)} F1 4 .7`); sub.push(`${gf(FINAL)} F1 4 .9`); pad.push(`${gf(FINAL)} F3+Ab3+C4+F4+C5 4 .5`); keys.push(`${gf(FINAL)} F3+Ab3+C4+F4 3 .5`); brass.push(`${gf(FINAL)} F4+Ab4+C5 2 .7`);
  const run = (t0) => 'F5 Ab5 C6 Eb6 F6 Ab6 C7'.split(' ').map((n, i) => `${gf(beat(t0) + i * .18)} ${n} .6 ${(.3 + i * .03).toFixed(2)}`).join('; ');
  const events = [
    { inst: 'synth_bass_1', vel: .9, notes: bass.join('; '), humanize: false },
    { inst: 'sub_bass', vel: 1.0, notes: sub.join('; '), humanize: false },
    { inst: 'electric_piano_1', vel: .8, notes: keys.join('; ') },
    { inst: 'pad_3_polysynth', vel: .6, notes: pad.join('; ') },
    { inst: 'synth_brass_1', vel: .8, notes: brass.join('; ') },
    { inst: 'glockenspiel', vel: .5, notes: [run(4.95), run(10.15), run(LAST + .1)].join('; ') },
  ];
  DRUMS.forEach((kit, bar) => events.push({ type: 'drums', from: bar * 4, bars: 1, steps: 16, vel: .85, kit, gains: KIT_GAINS }));
  return { bpm: BPM, drum_gain: .62, instruments: {
    synth_bass_1: { g: .62, pan: 0, send: .04, rel: .12 }, sub_bass: { g: .5, pan: 0, send: 0, rel: .05 },
    electric_piano_1: { g: .26, pan: -.22, send: .3, rel: .25 }, pad_3_polysynth: { g: .17, pan: 0, send: .5, rel: .8, soft_attack: true },
    synth_brass_1: { g: .22, pan: .12, send: .35, rel: .35 }, glockenspiel: { g: .16, pan: .3, send: .45, rel: 1.0 } }, events };
}
function sfxData() {
  const cues = [], r = (x, n) => +x.toFixed(n);
  const add = (t, fx, db, args = {}, o = {}) => { const c = { t: r(t, 3), fx, db }; if (o.pan) c.pan = r(o.pan, 2); if (o.send !== undefined) c.send = o.send; if (o.times) c.times = o.times.map((x) => r(x, 3)); if (Object.keys(args).length) c.args = args; cues.push(c); };
  // 1. the blank slides in and stops; the tier; the press winds down
  add(.12, 'swoosh_soft', -20, { sec: .7 }, { pan: -.4 });
  add(1.1, 'clink', -20, { sec: .6, tau: .14 });
  if (TIER_LINE) add(1.22, 'pop', -20, { f0: 620, f1: 220, sec: .09 });
  add(.9, 'rumble', -26, { sec: 2.3 });
  add(1.5, 'shimmer', -30, { sec: 1.0 });
  add(3.2, 'swoosh_soft', -22, { sec: .5 });
  add(3.72, 'whoosh', -14, { sec: .28, f0: 900, f1: 200, peak: .8 });
  // 2. the strike
  add(HIT, 'boom', -10, { sec: 1.1 }); add(HIT, 'crash', -22, { sec: 1.8 }, { send: .3 }); add(HIT, 'clink', -14, { sec: 1.0, tau: .3 });
  add(HIT + .02, 'crinkle', -20, { sec: .5, dens: 420 });
  add(4.3, 'whoosh', -20, { sec: .9, f0: 200, f1: 1600, peak: .5 });
  add(4.95, 'shimmer', -22, { sec: 1.0, f0: 800, f1: 5000 });
  // 3. the toss, the spin, the landing
  add(TOSS, 'whoosh', -15, { sec: .5, f0: 300, f1: 3200, peak: .7 });
  add(TOSS + .15, 'tick', -28, {}, { times: Array.from({ length: 9 }, (_, i) => TOSS + .15 + i * .2) });
  add(LAND, 'clink', -13, { sec: .9, tau: .25 }); add(LAND, 'thunk', -18, { sec: .3 });
  add(10.15, 'shimmer', -24, { sec: .9, f0: 700, f1: 4200 });
  // 4. it stands; the words arrive
  add(STAND, 'whoosh', -16, { sec: .8, f0: 250, f1: 2800, peak: .6 });
  if (TIER_LINE) add(12.55, 'pop', -22, { f0: 700, f1: 260, sec: .08 });
  add(12.7, 'zip', -22, { sec: .3, f0: 500, f1: 2600 });
  if (SP.line) add(12.9, 'keys', -32, { sec: .5, rate: 16 });
  if (FIND) { add(13.3, 'pop', -19, { f0: 520, f1: 180, sec: .1 }); add(13.32, 'blip', -27, { f: 1320, sec: .08 }); }
  add(13.0, 'shimmer', -28, { sec: .8 }); add(15.4, 'shimmer', -31, { sec: .8 }); add(17.6, 'shimmer', -31, { sec: .8 });
  // 5. the tray, the roll, the slot, the sign-off
  add(INFO_OUT, 'swoosh_soft', -24, { sec: .4 });
  add(OUT, 'whoosh', -17, { sec: .6, f0: 400, f1: 2400, peak: .5 });
  add(19.7, 'swoosh_soft', -20, { sec: .5 }); add(20.25, 'thunk', -20, { sec: .3 });
  add(ROLL[0], 'rumble', -28, { sec: ROLL[1] - ROLL[0] + .1 });
  if (COPY.more) add(20.4, 'tick', -29, {}, { times: Array.from({ length: Math.min(18, COPY.more.length) }, (_, i) => 20.4 + i * .6 / Math.min(18, COPY.more.length)) });
  add(21.75, 'clink', -20, { sec: .5, tau: .12 }); add(SETTLE, 'thunk', -14, { sec: .4 }); add(SETTLE + .02, 'clink', -20, { sec: .7, tau: .2 });
  add(22.3, 'swoosh_soft', -22, { sec: .5 }); add(22.5, 'pop', -24, { f0: 600, f1: 220, sec: .08 });
  add(22.85, 'pop', -18, { f0: 500, f1: 160, sec: .12 }); add(22.87, 'blip', -26, { f: 988, sec: .1 });
  add(LAST, 'crash', -21, { sec: 2.2 }, { send: .4 }); add(LAST, 'chime', -22, {}, { send: .35 });
  return cues.sort((a, b) => a.t - b.t);
}

SK.film({ duration: 26.0, camera: SK.camera([[0, [W / 2, H / 2, 1]]]), handheld: false, speedLines: false, fadeOut: 0, draw, sound: { score: scoreData, sfx: sfxData } });
