// For: the people who follow a conference on LinkedIn, X and YouTube, and its sponsors -- the organiser's thank-you post for one sponsor; flat, brand-led, typographic
/* One sponsor of one conference in 26 s, no narration: the music carries it. A template: every word, colour,
   logo and picture is in content.json (SK.DATA.content); nothing of the event or the sponsor is in this code.
   The frame is the manifest's (1080 x 1080 first; 1920 x 1080 and 1080 x 1920 hold too): layouts read W, H.
   The look is the EVENT's own: its ground colour, its type, its key art along the bottom, its buttons.
   The sponsor's logo is only ever flat and whole on a solid panel with clear space round it. It fades in and
   it rides its panel (one size, one move, together); it is never turned, squashed, shaded, lit, cut inside
   the frame or laid on the art.
     1 the event's world (0-4)   the ground, the key art drifting along the bottom, the lockup; the thanks and the tier, large
     2 the reveal (4-8)          the art drops away, a line opens into a panel and the sponsor's logo is there, still; the art comes back quiet
     3 who they are (8-16)       the panel, the tier over a rule, their line (their name when the logo does not spell it) and where to find them: one block, balanced above the art
     4 the wall (16-20)          the panel grows into the event's sponsor wall: the tier over its rule, the logo large
     5 the sign-off (20-26)      the wall drops away; the lockup, the dates and the city as the event sets them, the link
   The clock below is the one home of the timing; the sound (SK.film({sound})) is worked out from it. */
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp;
const WIDE = W / H > 1.3, TALL = H / W > 1.3, U = Math.min(W, H) / 1080, M = Math.round((WIDE ? 112 : 80) * U);
const D = SK.DATA.content, SP = D.sponsor || {}, EV = D.event || {}, SPL = SP.logo || {}, EVL = EV.logo || {}, ART = EV.art || {};

/* ------------------------------------------------------------------ the palette: the event's, flat */
function rgbOf(hex) { const n = parseInt(String(hex).slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function contrast(a, b) {
  const lum = (hex) => { const [r, g2, b2] = rgbOf(hex).map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * r + .7152 * g2 + .0722 * b2; };
  const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
const C = { ground: '#16234A', accent: '#D8457F', second: '#FFE680', light: '#FFFFFF', dark: '#1D1F24', ...(D.palette || {}) };
/** the ink that reads on a flat colour */
const inkOn = (bg) => (contrast(bg, C.light) >= 3 ? C.light : contrast(bg, C.ground) >= 4.5 ? C.ground : C.dark);
SK.setStyle('clean', { grain: 0, vignette: 0, handheld: 0 }); // flat: nothing is laid over a logo, not even grain
Object.assign(SK.C, { paper: C.ground, text: C.light, textSoft: C.light, accent: C.accent, accentText: C.accent, ink: C.ground });
const FONTS = { head: 'Sofia Sans', body: 'Sofia Sans', ...(D.fonts || {}) };
const WT = { bold: 800, mid: 600, light: 400, ...(FONTS.weights || {}) };

/* ------------------------------------------------------------------ the words and the pictures */
const TIER = String(SP.tier ?? '').trim();
const VARS = { ...Object.fromEntries(Object.entries(EV).filter(([, v]) => typeof v === 'string')), tier: TIER, sponsor: SP.name ?? '' };
const words = (s) => String(s ?? '').replace(/\{(\w+)\}/g, (_, k) => VARS[k] ?? '').replace(/\s+/g, ' ').trim();
const COPY = Object.fromEntries(Object.entries(D.copy || {}).map(([k, v]) => [k, words(v)]));
const TIER_LINE = TIER ? (COPY.tier || TIER) : (COPY.featured || '');
const WALL_LINE = TIER ? (COPY.wall || TIER_LINE) : (COPY.featured || '');
const NAME = String(SP.name ?? '').trim(), LINE = String(SP.line ?? '').trim(), FIND = String(SP.find ?? '').trim(), LINK = String(SP.link ?? '').trim();
const ARROW = COPY.arrow ? ' ' + COPY.arrow : '';
const IMG = (k) => (k ? SK.IMG[k] : null);
const PANEL = SPL.ink === 'light' ? (SP.color || C.dark) : C.light, PANEL_INK = SPL.ink === 'light' ? C.light : C.dark;

/* ------------------------------------------------------------------ the clock (120 bpm: a beat .5 s, a bar 2 s) */
const REVEAL = 4.0, WHO = 8.0, WALL = 16.0, SIGN = 20.0, LAST = 24.0;

/* ------------------------------------------------------------------ small helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (t) => { const c3 = k + 1; return 1 + c3 * Math.pow(t - 1, 3) + k * Math.pow(t - 1, 2); };
const outBack = back(1.4), outBackSoft = back(.7);
const font = (size, wt = WT.bold, fam = FONTS.head) => `${wt} ${size}px "${fam}", "Sofia Sans", sans-serif`; // the second face carries the scripts the first lacks
function text(str, x, y, o = {}) {
  const a = o.alpha ?? 1; if (a <= 0 || !str) return;
  const c = g(), ls = o.ls ?? 0; c.save(); c.font = font(o.size ?? 60, o.wt ?? WT.bold, o.fam ?? FONTS.head);
  c.textAlign = o.align ?? 'left'; c.textBaseline = 'alphabetic'; c.letterSpacing = ls + 'px';
  c.globalAlpha *= a; c.fillStyle = o.col ?? C.light;
  c.fillText(str, x + (o.align === 'center' ? ls / 2 : o.align === 'right' ? ls : 0), y); c.restore();
}
function measure(str, o = {}) { const c = g(), ls = o.ls ?? 0; c.save(); c.font = font(o.size ?? 60, o.wt ?? WT.bold, o.fam ?? FONTS.head); c.letterSpacing = ls + 'px'; const w = c.measureText(str).width - (str ? ls : 0); c.restore(); return w; }
const fit = (str, width, max, o = {}) => Math.min(max, max * width / Math.max(1, measure(str, { ...o, size: max, ls: o.em ? o.em * max : o.ls })));
function wrap(str, width, o) {
  const out = []; let line = '';
  for (const w of String(str).split(/\s+/).filter(Boolean)) { const n = line ? line + ' ' + w : w; if (line && measure(n, o) > width) { out.push(line); line = w; } else line = n; }
  if (line) out.push(line); return out;
}
/** the largest type at which str sets in at most maxLines lines of `width` inside `height`; one line counts `one` times its size */
function fitType(str, width, height, max, min, maxLines, o = {}, lead = 1.04, one = 1) {
  let best = null;
  for (let n = 1; n <= maxLines; n++) for (let s = max; s >= min; s -= 2) {
    const lines = wrap(str, width, { ...o, size: s });
    if (lines.length > n || lines.some((l) => measure(l, { ...o, size: s }) > width) || s * (.74 + (lines.length - 1) * lead) > height) continue;
    const score = s * (lines.length === 1 ? one : 1); if (!best || score > best.score) best = { size: s, lines, score };
    break;
  }
  if (best) return best;
  const lines = wrap(str, width, { ...o, size: min }).slice(0, maxLines);
  return { size: Math.min(min, ...lines.map((l) => fit(l, width, min, o))), lines };
}
/** the same number of lines, evened: the narrowest width that still wraps str into n lines */
function balance(b, str, width, o = {}) {
  const n = b.lines.length; if (n < 2 || /…$/.test(b.lines[n - 1])) return b;
  let lo = width / n * .8, hi = width, best = b.lines;
  for (let i = 0; i < 12; i++) { const mid = (lo + hi) / 2, ls = wrap(str, mid, { ...o, size: b.size }); if (ls.length <= n && ls.every((l) => measure(l, { ...o, size: b.size }) <= width)) { best = ls; hi = mid; } else lo = mid; }
  return { ...b, lines: best };
}
/** a paragraph of at most maxLines lines: the largest type that sets it without a lone short word at its end; under min, cut with an ellipsis */
function clampBlock(str, width, max, min, maxLines, o = {}) {
  let best = null;
  for (let n = 1; n <= maxLines; n++) for (let s = max; s >= min; s -= 2) {
    const q = { ...o, size: s }, lines = wrap(str, width, q); if (lines.length > n || lines.some((l) => measure(l, q) > width)) continue;
    const b = balance({ size: s, lines }, str, width, o), last = b.lines[b.lines.length - 1], widest = Math.max(...b.lines.map((l) => measure(l, q)));
    const lone = b.lines.length > 1 && !/\s/.test(last) && measure(last, q) < widest * .5, score = s * (lone ? .72 : 1) * Math.pow(.94, b.lines.length - 1);
    if (!best || score > best.score) best = { ...b, score };
    break;
  }
  if (best) return best;
  const all = wrap(str, width, { ...o, size: min }), lines = all.slice(0, maxLines); let last = lines[maxLines - 1] || '';
  if (all.length > maxLines) { while (last && measure(last + '…', { ...o, size: min }) > width) last = last.replace(/\s*\S+$/, ''); lines[maxLines - 1] = last.replace(/[\s,;:.]+$/, '') + '…'; }
  return { size: Math.min(min, ...lines.map((l) => fit(l, width, min, o))), lines };
}
/** an address as people type it; when it cannot be read at `min`, its path is cut back, segment by segment */
function shortUrl(url, width, size, min, o = {}) {
  let u = String(url || '').trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/[/?#]+$/, '');
  while (fit(u, width, size, o) < min && /[/?#]/.test(u)) u = u.replace(/[/?#][^/?#]*$/, '');
  return u;
}
function rr(x, y, w, h, r, fill, corners = [1, 1, 1, 1]) { // corners: top-left, top-right, bottom-right, bottom-left
  if (w <= 0 || h <= 0) return; const c = g(), q = corners.map((k) => k * Math.max(0, Math.min(r, w / 2, h / 2)));
  c.beginPath(); c.moveTo(x + q[0], y); c.arcTo(x + w, y, x + w, y + h, q[1]); c.arcTo(x + w, y + h, x, y + h, q[2]); c.arcTo(x, y + h, x, y, q[3]); c.arcTo(x, y, x + w, y, q[0]); c.closePath();
  c.fillStyle = fill; c.fill();
}
/** a picture as its file draws it: whole, its own proportions, nothing on it */
function pic(im, x, y, w, h, a = 1) { if (!im || a <= 0) return; const c = g(); c.save(); c.globalAlpha *= a; c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high'; c.drawImage(im, x, y, w, h); c.restore(); }
/** a line of type rising into (p) and out of (q) its own mask */
function rise(str, x, base, o, p, q = 0) {
  if (p <= 0 || q >= 1 || !str) return;
  const c = g(), s = o.size, w = measure(str, o) + Math.abs(o.ls ?? 0) + s * .2, x0 = o.align === 'center' ? x - w / 2 : o.align === 'right' ? x - w : x - s * .1;
  c.save(); c.beginPath(); c.rect(x0, base - s * .98, w, s * 1.3); c.clip();
  text(str, x, base + (1 - E.out(clamp(p))) * s * 1.2 - E.in(clamp(q)) * s * 1.2, o);
  c.restore();
}
/** tracked capitals: the tracking settles as they fade in */
function track(str, x, base, o, p, q = 0) {
  const u = E.out(clamp(p)), a = u * (1 - clamp(q)); if (a <= 0 || !str) return;
  text(str, x, base, { ...o, ls: (o.ls ?? 0) * (1 + .8 * (1 - u)), alpha: (o.alpha ?? 1) * a });
}
/** a button as the event's site draws them: a flat block, bold capitals */
const chipBox = (str, size) => [measure(str, { size, wt: WT.bold, ls: size * .04 }) + size * 1.9, size * 2.15];
function chip(str, x, cy, size, bg, s = 1, a = 1) { // x: its left edge; cy: its middle; s: its pop, about its middle
  if (a <= 0 || s <= 0 || !str) return; const [w, h] = chipBox(str, size), c = g();
  c.save(); c.globalAlpha *= a; c.translate(x + w / 2, cy); c.scale(s, s);
  rr(-w / 2, -h / 2, w, h, 9 * U, bg); text(str, 0, size * .36, { size, wt: WT.bold, align: 'center', col: inkOn(bg), ls: size * .04 });
  c.restore();
}
const pulse = (t, at) => (t > at && t < at + .5 ? .05 * Math.sin(Math.PI * (t - at) / .5) : 0);

/* ------------------------------------------------------------------ the layout, from the frame and the pictures' own sizes */
let LAY = null, LAYKEY = '';
function layout() {
  const sim = IMG(SPL.image), eim = IMG(EVL.image), key = [!!sim, !!eim, !!IMG(ART.image), !!IMG(ART.bright)].join();
  if (LAY && key === LAYKEY) return LAY;
  const L = (LAY = {}), tw = W - 2 * M; LAYKEY = key;

  // the event's lockup: a masthead, top right, where its own card puts it
  if (eim) { const a = eim.width / eim.height; L.lkH = Math.min((WIDE ? 150 : TALL ? 162 : 128) * U, (WIDE ? 390 : TALL ? 430 : 330) * U / a); L.lkW = L.lkH * a; }
  else { const s = [EV.name, EV.year].filter(Boolean).join(' ') || ' ', b = fitType(s, tw * (WIDE ? .46 : .56), 1e9, (WIDE ? 46 : 40) * U, 26 * U, 3, { wt: WT.bold }, 1.12, 1.2); L.lkName = b; L.lkW = Math.max(...b.lines.map((l) => measure(l, { size: b.size, wt: WT.bold }))); L.lkH = b.size * (.8 + (b.lines.length - 1) * 1.12); }
  L.lkX = W - M - L.lkW; L.lkY = Math.round(M * .78); L.lkB = L.lkY + L.lkH;

  // the key art, along the bottom: the event's own picture in full colour (bright) for the opening and the sign-off,
  // and as it runs behind a page of its site (image) while the sponsor is on; either serves for all three.
  // `top` leaves out a picture's empty sky.
  const artPic = (k, top) => { const im = IMG(k); if (!im) return null; const ct = clamp(+top || 0, 0, .7), sh = im.height * (1 - ct), sc = Math.max(H * FULL / sh, W * 1.1 / im.width); return { im, sy: im.height * ct, sh, w: im.width * sc, h: sh * sc }; };
  const FULL = WIDE ? .56 : .46, SHOW = WIDE ? [.44, .26, .56] : TALL ? [.42, .33, .46] : [.4, .29, .46]; // of the frame's height: the picture, and how much of it shows in scene 1, scenes 2-3 and scene 5
  const dim = artPic(ART.image, ART.top), bright = artPic(ART.bright, ART.bright_top);
  if (dim || bright) L.art = { pics: [bright || dim, dim || bright, bright || dim], top: SHOW.map((f) => H - H * f) };
  const artTop = (i) => (L.art ? L.art.top[i] : H - M * .7), sky = L.art ? 26 * U : 0; // the picture's top edge melts into the ground: type may touch it

  { // 1. the thanks and the tier, large, in the space above the art
    const top = L.lkB + 34 * U, bot = artTop(0) + sky, ts = COPY.thanks ? (WIDE ? 40 : TALL ? 42 : 34) * U : 0, lead = 1.03;
    const big = fitType(TIER_LINE, tw, bot - top - ts * 2.1, (WIDE ? 196 : TALL ? 200 : 160) * U, 56 * U, WIDE ? 2 : 3, { wt: WT.bold }, lead, WIDE ? 1.45 : 1);
    const bh = ts * .74 + (ts ? big.size * .36 : 0) + big.size * (.74 + (big.lines.length - 1) * lead), y0 = top + Math.max(0, (bot - top - bh) * (L.art ? .5 : .42));
    L.s1 = { ts, thanksY: y0 + ts * .74, big, bigY: y0 + ts * .74 + (ts ? big.size * .36 : 0) + big.size * .74, lead };
  }

  { // 2. the panel and the logo on it: clear space k of the logo's height on every side, never under a quarter
    const a = sim ? sim.width / sim.height : null, k = Math.max(.25, +SPL.clear || (a && a < 2 ? .36 : WIDE ? .42 : .5));
    const rs = (WIDE ? 32 : TALL ? 34 : 29) * U, rowH = (COPY.thanks || TIER_LINE) ? rs * 3.4 : 0;
    const top = L.lkB + 26 * U + rowH, bot = artTop(1) - (L.art ? 30 * U : M * .5); // clear of the art: the panel sits on the flat ground
    const maxW = Math.min(tw, (WIDE ? 1180 : 2000) * U), maxH = Math.min(bot - top, maxW * (TALL ? .7 : .6));
    let lw, lh, nm = null;
    if (a) { lh = Math.min(maxH / (1 + 2 * k), maxW / (a + 2 * k)); lw = a * lh; }
    else { /* no logo file: the name in type, never a drawn or guessed logo */ nm = fitType(NAME || ' ', maxW * .8, maxH * .62, 150 * U, 40 * U, 3, { wt: WT.bold }); lh = nm.size * (.74 + (nm.lines.length - 1) * 1.04); lw = Math.max(...nm.lines.map((l) => measure(l, { size: nm.size, wt: WT.bold }))); }
    let pw = Math.min(maxW, lw + 2 * k * lh); const ph = Math.min(maxH, Math.max(lh * (1 + 2 * k), pw * (TALL ? .6 : .44)));
    pw = Math.min(maxW, Math.max(pw, ph * 1.3));
    const cy = top + (bot - top) / 2;
    L.p2 = { x: W / 2 - pw / 2, y: cy - ph / 2, w: pw, h: ph }; L.logo = { w: lw, h: lh, nm }; L.r = 26 * U;
    // the row over the panel: the thanks, then the tier as a button
    let f = 1; const rowW = () => (COPY.thanks ? measure(COPY.thanks, { size: rs * f, wt: WT.mid, ls: rs * f * .16 }) + rs * f * .9 : 0) + (TIER_LINE ? chipBox(TIER_LINE, rs * f * .94)[0] : 0);
    const over = rowW() > pw; while (over && rowW() > tw && f > .7) f -= .04; // wider than its panel: centred on the frame instead
    L.row = { size: rs * f, y: L.p2.y - rs * 1.75, x: over ? W / 2 - Math.min(rowW(), tw) / 2 : L.p2.x, stack: rowW() > tw };
  }

  { // 3. who they are: the panel, the tier over its rule, their line and where to find them -- ONE block, balanced in the space above the art
    const P2 = L.p2, kc = Math.max(.3, +SPL.clear || 0), plate = eim && EVL.ink === 'dark' ? 22 * U : 0, lkBot = L.lkB + plate; // plate: a dark-ink lockup's white plate reaches under it
    const beside = tw - L.lkW - 44 * U - plate; // the width a panel has in the lockup's own band
    const hmin = (pw) => L.logo.h * (pw / P2.w) * (1 + 2 * kc); // the panel is never closer to its logo than this
    const named = !!NAME && !!sim && (SPL.named === false || !LINE); // the name in type only beside a logo that does not spell it, or when nothing else is said
    L.hold = !named && !LINE && !FIND && !LINK; // nothing to say beside it: the panel holds its place, the thanks over it, until the wall
    const words = (cw, f, maxLines) => { // the words in a column cw wide, at f of the largest size the column allows
      const hs = (WIDE ? 40 : TALL ? 46 : 36) * U * Math.max(f, .86), q = { hs, w: cw }, o = { wt: named ? WT.mid : WT.bold };
      const mx = named ? (WIDE ? 46 : TALL ? 52 : 42) * U : (WIDE ? 104 : TALL ? 110 : 100) * U, mn = named ? (WIDE ? 34 : TALL ? 36 : 31) * U : (WIDE ? 46 : TALL ? 50 : 42) * U;
      if (named) { const s0 = fitType(NAME, cw, 1e9, (WIDE ? 96 : TALL ? 108 : 84) * U, 44 * U, 2, { wt: WT.bold }, 1.04, 1.5).size; q.name = fitType(NAME, cw, 1e9, Math.max(44 * U, s0 * f), 44 * U, 2, { wt: WT.bold }, 1.04, 1.5); }
      q.lineWt = o.wt; q.lead = named ? 1.34 : 1.14;
      if (LINE) { const s0 = clampBlock(LINE, cw, mx, mn, maxLines, o).size; q.line = clampBlock(LINE, cw, Math.max(mn, s0 * f), mn, maxLines, o); }
      const url = LINK ? shortUrl(LINK, cw * .8, 44 * U, 34 * U, { wt: WT.bold }) : '';
      q.chip = FIND ? FIND + ARROW : url ? url + ARROW : ''; q.link = FIND && url ? url : '';
      q.cs = q.line && !named ? clamp(q.line.size * .56, 30 * U, 58 * U) : (WIDE ? 40 : TALL ? 46 : 38) * U * Math.max(f, .8); // the button follows the line
      if (q.chip && chipBox(q.chip, q.cs)[0] > cw) q.cs = Math.max(18 * U, q.cs * cw / chipBox(q.chip, q.cs)[0]);
      const cb = q.chip ? chipBox(q.chip, q.cs) : [0, 0]; q.ls = q.link ? Math.min(q.cs, fit(q.link, cw, q.cs, { wt: WT.bold })) : 0;
      q.linkBelow = !!q.link && cb[0] + q.cs * .8 + measure(q.link, { size: q.cs, wt: WT.bold }) > cw;
      let y = 0; q.headY = hs * .74; q.ruleY = TIER_LINE ? q.headY + hs * .8 : 0; y = TIER_LINE ? q.ruleY + hs * .62 : 0;
      if (q.name) { y += q.name.size * (TIER_LINE ? .3 : 0); q.nameY = y + q.name.size * .74; y = q.nameY + (q.name.lines.length - 1) * q.name.size * 1.04; }
      if (q.line) { y += q.line.size * (q.name ? .95 : TIER_LINE ? .28 : 0); q.lineY = y + q.line.size * .74; y = q.lineY + (q.line.lines.length - 1) * q.line.size * q.lead + q.line.size * .14; }
      if (q.chip) { y += cb[1] * (y ? .62 : 0); q.chipY = y + cb[1] / 2; y += cb[1]; if (q.linkBelow) { q.linkY = y + q.ls * 1.5; y = q.linkY + q.ls * .2; } }
      q.h = y; return q;
    };
    // the space above the art ends in the picture's own melting edge; the words keep a size a phone can read:
    // they shrink a little, then the art sinks, then the line loses its third row
    const room = () => artTop(1) + (L.art ? L.art.pics[1].h * .05 : -M * .3), maxSink = L.art ? Math.max(0, H * .9 - L.art.top[1]) : 0, FS = [1, .94, .88, .82, .76];
    let T = null, p3 = null;
    if (L.hold) { T = {}; p3 = { ...P2 }; }
    else if (WIDE) { // the panel left, the words right: one pair of one height, centred between the lockup and the art
      const pw = Math.min(P2.w, W * .34), x0 = M + pw + 64 * U, cw = W - M - x0, R0 = lkBot + 30 * U;
      for (const f of FS) { T = words(cw, f, 3); if (R0 + T.h <= room()) break; }
      if (R0 + T.h > room() + maxSink) T = words(cw, .76, 2);
      if (L.art) L.art.top[1] += clamp(R0 + T.h - room(), 0, maxSink);
      const R1 = Math.max(room(), R0 + T.h), cy = (R0 + R1) / 2, ph = clamp(Math.max(T.h, P2.h * pw / P2.w), hmin(pw), Math.max(hmin(pw), R1 - R0));
      p3 = { x: M, y: Math.max(L.lkY, cy - ph / 2), w: pw, h: ph }; T.x = x0; T.top = cy - T.h / 2;
    } else { // stacked: the panel as large as the words leave it room for, the words under it
      const stack = (R0, wmax, R1, scMin, fs, maxLines, tight) => {
        for (const f of fs) {
          const q = words(tw, f, maxLines), gap = (TALL ? 72 : 54) * U * Math.max(f, .86), avail = R1 - R0 - gap - q.h;
          let pw = Math.min(P2.w, wmax); if (hmin(pw) > avail) pw *= avail / hmin(pw);
          if (!(pw >= P2.w * scMin)) continue;
          return { q, pw, gap, R0, ph: tight ? hmin(pw) : clamp(avail, hmin(pw), P2.h * pw / P2.w * 1.15) };
        }
        return null;
      };
      // square: under the lockup when little is said, else beside it, in its band; vertical: under it
      const under = lkBot + (TALL ? 110 : 24) * U, sm = TALL ? .5 : .42, wide = beside >= P2.w * sm, ext = room() + maxSink;
      const S = (!TALL && stack(under, tw, room(), .6, [1], 3)) || (!TALL && wide && stack(L.lkY, beside, room(), sm, FS, 3)) || stack(under, tw, room(), sm, FS, 3)
        || (!TALL && wide && stack(L.lkY, beside, ext, sm, FS, 3, true)) || stack(under, tw, ext, sm, FS, 3, true) || stack(under, tw, ext, sm * .7, [.76], 2, true)
        || { q: words(tw, .76, 2), pw: Math.min(P2.w, tw) * sm, gap: 40 * U, R0: under, ph: hmin(Math.min(P2.w, tw) * sm) };
      const bh = S.ph + S.gap + S.q.h; if (L.art) L.art.top[1] += clamp(S.R0 + bh - room(), 0, maxSink);
      const y0 = S.R0 + Math.max(0, (room() - S.R0 - bh) / 2);
      p3 = { x: M, y: y0, w: S.pw, h: S.ph }; T = S.q; T.x = M; T.top = y0 + S.ph + S.gap;
    }
    L.p3 = p3; L.who = T;
  }

  { // 4. the wall: the tier over its rule and the logo, large and alone, as the event's sponsor page sets them
    const tab = { x: L.lkX - 40 * U, h: L.lkB + 34 * U }, top = tab.h, y1 = H - M * .7; // the lockup keeps a corner of its own ground
    const hs = fit(WALL_LINE || ' ', tw * .86, (WIDE ? 48 : TALL ? 52 : 42) * U, { wt: WT.light, em: .46 });
    const a = sim ? sim.width / sim.height : L.logo.w / L.logo.h, lh = Math.min((y1 - top) * (TALL ? .26 : .4), tw * (WIDE ? .56 : .84) / a);
    const head = WALL_LINE ? hs * 1.62 : 0, gap = WALL_LINE ? Math.max(lh * .62, 84 * U) : 0, gy = top + (y1 - top - head - gap - lh) * .42;
    L.wall = { tab, hs, headY: gy + hs * .74, ruleY: gy + head, logo: { w: a * lh, h: lh, cx: W / 2, cy: gy + head + gap + lh / 2, k: lh / L.logo.h } };
  }

  { // 5. the sign-off: the dates and the city in bold capitals as the event's card sets them, the link
    const cw = WIDE ? tw - L.lkW - 70 * U : tw, big = [EV.dates, EV.city].filter(Boolean);
    const top = WIDE ? L.lkY + 4 * U : L.lkB + 36 * U, bot = artTop(2) + sky * (WIDE ? 1.3 : 1);
    const url = EV.url ? shortUrl(EV.url, cw * .8, 36 * U, 31 * U, { wt: WT.bold }) : '';
    let T = null;
    for (const f of (L.art ? [] : [1.6, 1.45, 1.3, 1.15]).concat([1, .92, .84, .76, .68, .6])) { // with no art the words have the frame
      const bs = Math.min((WIDE ? 90 : TALL ? 88 : 74) * U * f, ...big.map((s) => fit(s, cw, 400 * U, { wt: WT.bold }))), ss = (WIDE ? 42 : TALL ? 44 : 36) * U * clamp(f, .8, 1.25);
      const q = { bs, ss, rows: [] }; let y = 0;
      big.forEach((s, i) => { y += i ? bs * 1.1 : bs * .74; q.rows.push({ s, y, size: bs, wt: WT.bold }); });
      for (const [str, wt, soft] of [[EV.venue, WT.mid, true], [EV.tags, WT.light, false]]) {
        if (!str) continue; const b = clampBlock(str, cw, ss, ss * .78, 2, { wt });
        b.lines.forEach((l, i) => { y += i ? b.size * 1.3 : q.rows.length ? (q.rows[q.rows.length - 1].wt === WT.bold ? bs * .3 + ss * 1.25 : ss * 1.42) : ss * .74; q.rows.push({ s: l, y, size: b.size, wt, soft }); });
      }
      q.cs = (WIDE ? 36 : TALL ? 40 : 32) * U * clamp(f, .8, 1.25); q.chip = url ? url + ARROW : '';
      if (q.chip && chipBox(q.chip, q.cs)[0] > cw) q.cs *= cw / chipBox(q.chip, q.cs)[0];
      if (q.chip) { const cb = chipBox(q.chip, q.cs); y += q.rows.length ? cb[1] * .62 : 0; q.chipY = y + cb[1] / 2; y += cb[1]; }
      if (COPY.more) { y += ss * 1.5; q.moreY = y; }
      q.h = y; T = q;
      if (top + q.h <= bot) break;
    }
    L.sign = { ...T, x: M, w: cw, top: WIDE && L.art ? top : top + Math.max(0, (bot - top - T.h) * (L.art ? .3 : .42)) };
  }
  return L;
}

/* ------------------------------------------------------------------ the pieces */
function art(t) { // the event's own picture, whole, drifting: it opens the film, clears the stage for the sponsor, comes back quiet, and closes the film
  const A = LAY.art; if (!A) return;
  const i = t >= WALL + 1 ? 2 : t < REVEAL ? 0 : 1, P = A.pics[i], c = g();
  const y = i === 0 ? A.top[0] + (1 - E.out(clamp(t / 1.0))) * 90 * U + (H - A.top[0] + 4) * ease(t, REVEAL - .55, REVEAL - .04, E.in)
    : i === 1 ? lerp(H + 4, A.top[1], ease(t, REVEAL + .3, REVEAL + 1.2, E.out)) : A.top[2];
  if (y >= H) return;
  const travel = Math.min(P.w - W, 22 * U * 26), x = -(P.w - W) / 2 + travel * (.5 - t / 26);
  c.save(); c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high'; c.drawImage(P.im, 0, P.sy, P.im.width, P.sh, x, y, P.w, P.h); c.restore();
  const m = P.h * .09, f = c.createLinearGradient(0, y - 1, 0, y + m), [r, g2, b] = rgbOf(C.ground); // its top edge melts into the ground
  f.addColorStop(0, `rgba(${r},${g2},${b},1)`); f.addColorStop(1, `rgba(${r},${g2},${b},0)`); c.fillStyle = f; c.fillRect(0, y - 2, W, m + 2);
}
function lockup() {
  const L = LAY, im = IMG(EVL.image);
  if (im) { if (EVL.ink === 'dark') rr(L.lkX - 22 * U, L.lkY - 18 * U, L.lkW + 44 * U, L.lkH + 36 * U, 16 * U, C.light); pic(im, L.lkX, L.lkY, L.lkW, L.lkH); }
  else if (L.lkName) L.lkName.lines.forEach((l, i) => text(l, W - M, L.lkY + L.lkName.size * (.78 + i * 1.12), { size: L.lkName.size, wt: WT.bold, align: 'right' }));
}
/** the sponsor's logo on its panel: as its file draws it, centred, k times the size it has on the first panel */
function logo(cx, cy, k, a) {
  const L = LAY.logo, im = IMG(SPL.image); if (a <= 0) return;
  if (im) return pic(im, cx - L.w * k / 2, cy - L.h * k / 2, L.w * k, L.h * k, a);
  if (!L.nm) return;
  const s = L.nm.size * k, n = L.nm.lines.length, y0 = cy - s * (.74 + (n - 1) * 1.04) / 2 + s * .74;
  L.nm.lines.forEach((l, i) => text(l, cx, y0 + i * s * 1.04, { size: s, wt: WT.bold, align: 'center', col: PANEL_INK, alpha: a }));
}

function opening(t) { // 1. the thanks, small and tracked; the tier, large
  if (t > REVEAL + .1) return;
  const S = LAY.s1, o = { size: S.big.size, wt: WT.bold };
  track(COPY.thanks, M, S.thanksY, { size: S.ts, wt: WT.mid, ls: S.ts * .2 }, (t - .35) / .6, (t - (REVEAL - .55)) / .3);
  S.big.lines.forEach((l, i) => rise(l, M - S.big.size * .04, S.bigY + i * S.big.size * S.lead, o, (t - (.8 + i * .22)) / .6, (t - (REVEAL - .5 + i * .06)) / .36));
}
function panelRect(t) { // the panel: a line, then open; it settles; it grows into the wall; the wall drops away
  const L = LAY, a = L.p2, b = L.p3;
  if (t < REVEAL - .22) return null;
  if (t < WHO - .25) { const l = ease(t, REVEAL - .22, REVEAL, E.in), v = outBackSoft(clamp((t - REVEAL) / .5)), w = a.w * l, h = Math.max(6 * U, a.h * v); return { x: W / 2 - w / 2, y: a.y + a.h / 2 - h / 2, w, h, r: L.r, k: 1 }; }
  const m = ease(t, WHO - .25, WHO + .32), n = ease(t, WHO - .05, WHO + .55), p = { x: lerp(a.x, b.x, WIDE ? n : m), y: lerp(a.y, b.y, n), w: lerp(a.w, b.w, m), h: lerp(a.h, b.h, m) }; // it narrows, then it travels: it never crosses the lockup
  if (t < WALL - .22) return { ...p, r: L.r * lerp(1, b.w / a.w, m), k: p.w / a.w };
  const gw = ease(t, WALL - .22, WALL + .42), dy = (H + 4) * ease(t, SIGN - .52, SIGN + .06, E.in); // the wall drops away as one sheet
  return { x: lerp(b.x, 0, gw), y: lerp(b.y, 0, gw) + dy, w: lerp(b.w, W, gw), h: lerp(b.h, H, gw), r: L.r * (b.w / a.w) * (1 - gw), k: b.w / a.w, grow: gw, dy };
}
function panel(t) { // 2. the panel opens and the logo is there; it rides its panel, whole
  const P = panelRect(t); if (!P || P.h <= 0 || P.y >= H) return;
  rr(P.x, P.y, P.w, P.h, P.r, PANEL);
  if (P.grow === undefined) logo(P.x + P.w / 2, P.y + P.h / 2, P.k, ease(t, REVEAL + .22, REVEAL + .6, E.out));
}
function row(t) { // the thanks and the tier over the panel
  const end = LAY.hold ? WALL : WHO; if (t < REVEAL + .3 || t > end) return;
  const R = LAY.row, q = (t - (end - .5)) / .25; let x = R.x;
  if (COPY.thanks && !R.stack) { const o = { size: R.size, wt: WT.mid, ls: R.size * .16 }; track(COPY.thanks, x, R.y + R.size * .36, o, (t - (REVEAL + .5)) / .5, q); x += measure(COPY.thanks, o) + R.size * .9; }
  if (TIER_LINE) { const p = clamp((t - (REVEAL + .8)) / .35); chip(TIER_LINE, x, R.y, R.size * .94, C.accent, outBack(p) * (1 + pulse(t, 6)), clamp(p * 3) * (1 - clamp(q))); }
}
function who(t) { // 3. the tier over a rule, their line (and their name when the logo does not spell it), where to find them
  if (t < WHO + .2 || t > WALL || LAY.hold) return;
  const L = LAY.who, c = g(), x = L.x, y = L.top, out = (i) => (t - (WALL - .58 + i * .03)) / .28;
  if (TIER_LINE) {
    const hs = Math.min(L.hs, fit(TIER_LINE, L.w, L.hs, { wt: WT.light, em: .34 }));
    track(TIER_LINE, x, y + L.headY, { size: hs, wt: WT.light, ls: hs * .34 }, (t - (WHO + .45)) / .5, out(4));
    const rw = L.w * ease(t, WHO + .55, WHO + 1.05, E.out) * (1 - ease(t, WALL - .5, WALL - .25));
    c.save(); c.globalAlpha *= .75; c.fillStyle = C.light; c.fillRect(x, y + L.ruleY, rw, 2 * U); c.restore();
  }
  if (L.name) L.name.lines.forEach((l, i) => rise(l, x - L.name.size * .03, y + L.nameY + i * L.name.size * 1.04, { size: L.name.size, wt: WT.bold }, (t - (WHO + .85 + i * .12)) / .5, out(3)));
  const l0 = WHO + (L.name ? 1.3 : .85);
  if (L.line) L.line.lines.forEach((l, i) => rise(l, x - (L.name ? 0 : L.line.size * .03), y + L.lineY + i * L.line.size * L.lead, { size: L.line.size, wt: L.lineWt, alpha: L.name ? .94 : 1 }, (t - (l0 + i * .16)) / .55, out(2)));
  if (L.chip) {
    const p = clamp((t - (WHO + 2.5)) / .35), a = clamp(p * 3) * (1 - clamp(out(1)));
    chip(L.chip, x, y + L.chipY, L.cs, C.second, outBack(p) * (1 + pulse(t, 12) + pulse(t, 14)), a);
    if (L.link) { const la = ease(t, WHO + 2.9, WHO + 3.3) * (1 - clamp(out(0))); if (L.linkBelow) text(L.link, x, y + L.linkY, { size: L.ls, wt: WT.bold, alpha: la }); else text(L.link, x + chipBox(L.chip, L.cs)[0] + L.cs * .8, y + L.chipY + L.cs * .36, { size: L.cs, wt: WT.bold, alpha: la }); }
  }
}
function wall(t) { // 4. the sponsor wall: nothing on it but the tier, its rule and the logo
  const P = panelRect(t); if (!P || P.grow === undefined || P.y >= H) return;
  const L = LAY.wall, b = LAY.p3, c = g(), gw = P.grow;
  c.save(); c.translate(0, P.dy);
  logo(lerp(b.x + b.w / 2, L.logo.cx, gw), lerp(b.y + b.h / 2, L.logo.cy, gw), lerp(P.k, L.logo.k, gw), 1);
  if (WALL_LINE && gw >= 1) {
    track(WALL_LINE, W / 2, L.headY, { size: L.hs, wt: WT.light, ls: L.hs * .46, align: 'center', col: PANEL_INK }, (t - (WALL + .45)) / .55);
    const rw = (W - 2 * M) * ease(t, WALL + .5, WALL + 1.05, E.out); c.save(); c.globalAlpha *= .8; c.fillStyle = PANEL_INK; c.fillRect(W / 2 - rw / 2, L.ruleY, rw, 2 * U); c.restore();
  }
  c.restore();
  rr(L.tab.x, -2, W - L.tab.x + 2, L.tab.h + 2, 34 * U, C.ground, [0, 0, 0, 1]); // the lockup keeps a corner of its own ground, as on the event's site
}
function signoff(t) { // 5. the dates and the city as the event sets them; the link
  if (t < SIGN - .1) return;
  const L = LAY.sign, x = L.x, y = L.top;
  L.rows.forEach((r, i) => {
    const o = { size: r.size, wt: r.wt, alpha: r.soft ? .86 : 1 }, at = SIGN + .12 + i * .2;
    if (r.wt === WT.bold) rise(r.s, x - r.size * .03, y + r.y, o, (t - at) / .55); else text(r.s, x, y + r.y + (1 - ease(t, at, at + .5, E.out)) * 14 * U, { ...o, alpha: o.alpha * ease(t, at, at + .45) });
  });
  if (L.chip) { const p = clamp((t - (SIGN + 2)) / .35); chip(L.chip, x, y + L.chipY, L.cs, C.accent, outBack(p) * (1 + pulse(t, LAST)), clamp(p * 3)); }
  if (COPY.more) track(COPY.more, x, y + L.moreY, { size: L.ss * .7, wt: WT.mid, ls: L.ss * .14, alpha: .85 }, (t - (SIGN + 2.6)) / .6);
}

function draw(t) {
  layout();
  art(t);
  opening(t);
  row(t);
  if (t < WALL - .22) { panel(t); who(t); } else { who(t); panel(t); wall(t); }
  lockup();
  signoff(t);
}

/* ------------------------------------------------------------------ the sound, from the clock and the content
   A 120 bpm groove in F minor: light under the opening, a lift into the reveal, the full groove while the
   words are read, held back for the wall, back for the sign-off and a last chord at LAST. */
const BPM = 120, beat = (t) => t * BPM / 60, gf = (x) => String(+x.toPrecision(6));
function scoreData() {
  const CHART = [['F1', 'F2', 'Ab3+C4+F4', 'F3+Ab3+C4+Eb4'], ['Db2', 'Db3', 'Ab3+Db4+F4', 'Db3+F3+Ab3+C4'], ['Ab1', 'Ab2', 'Ab3+C4+Eb4', 'Ab3+C4+Eb4+G4'], ['Eb2', 'Eb3', 'G3+Bb3+Eb4', 'Eb3+G3+Bb3+Db4']];
  const BARS = Math.round(SK._film.duration / (240 / BPM)), HITS = [REVEAL, WHO, SIGN].map(beat), FINAL = beat(LAST);
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', openhat: '..x...x...x...x.', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
  const FULL = { ...GROOVE, rim: '...o..o....o..o.' };
  const DRUMS = [
    { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.' }, // 0: the event's world
    { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.', snare: '..........ooxxxX' }, // 1: a lift into the reveal
    { ...GROOVE, kick: 'X...x...x...x...' }, GROOVE, // 2-3: the panel opens; the logo holds
    { ...FULL, kick: 'X...x...x...x...' }, FULL, FULL, { ...FULL, snare: '............oxxX' }, // 4-7: who they are
    { kick: 'X.......x.......', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' }, // 8: the wall, held back
    { kick: 'x.......x.......', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o', snare: '..........ooxxxX' }, // 9: into the sign-off
    { ...FULL, kick: 'X...x...x...x...' }, { ...FULL, snare: '............oxxX' }, // 10-11: the sign-off
    { kick: 'X...............', openhat: 'x...............' }, // 12: the last chord
  ];
  const KIT_GAINS = { kick: 1.1, snare: .4, clap: .4, hat: .26, openhat: .16, shaker: .2, rim: .45 };
  const QUIET = { 8: [0, 4], 9: [0, 4] }; // the wall: the bass sits out, the pad holds
  const bass = [], sub = [], pad = [], keys = [], brass = [];
  for (let bar = 0; bar < BARS - 1; bar++) {
    const [root, octv, stab, chord] = CHART[bar % 4], b0 = bar * 4, q = QUIET[bar];
    for (let k = 0; k < 8; k++) { const b = k * .5; if (q && q[0] <= b && b < q[1]) continue; bass.push(`${gf(b0 + b)} ${k % 2 ? octv : root} .42 ${(k % 2 ? .52 : .62).toFixed(2)}`); if (k % 2) sub.push(`${gf(b0 + b - .02)} ${root} .4 .8`); }
    if (q) sub.push(`${gf(b0)} ${root} 3.8 .7`);
    if (bar >= 2) for (const k of [.5, 1.5, 2.5, 3.5]) keys.push(`${gf(b0 + k)} ${stab} .3 ${(q ? .2 : k === 1.5 || k === 3.5 ? .34 : .26).toFixed(2)}`);
    pad.push(`${gf(b0)} ${chord} 4 ${bar < 2 ? .22 : q ? .36 : .3}`);
  }
  for (const b of HITS) brass.push(`${gf(b)} ${CHART[Math.floor(b / 4) % 4][2]} .9 .56`);
  bass.push(`${gf(FINAL)} F1 4 .7`); sub.push(`${gf(FINAL)} F1 4 .9`); pad.push(`${gf(FINAL)} F3+Ab3+C4+F4+C5 4 .5`); keys.push(`${gf(FINAL)} F3+Ab3+C4+F4 3 .5`); brass.push(`${gf(FINAL)} F4+Ab4+C5 2 .66`);
  const run = (t0) => 'F5 Ab5 C6 Eb6 F6 Ab6 C7'.split(' ').map((n, i) => `${gf(beat(t0) + i * .18)} ${n} .6 ${(.3 + i * .03).toFixed(2)}`).join('; ');
  const events = [
    { inst: 'synth_bass_1', vel: .9, notes: bass.join('; '), humanize: false },
    { inst: 'sub_bass', vel: 1.0, notes: sub.join('; '), humanize: false },
    { inst: 'electric_piano_1', vel: .8, notes: keys.join('; ') },
    { inst: 'pad_3_polysynth', vel: .6, notes: pad.join('; ') },
    { inst: 'synth_brass_1', vel: .8, notes: brass.join('; ') },
    { inst: 'glockenspiel', vel: .5, notes: [run(REVEAL + .3), run(WALL + .5), run(LAST + .1)].join('; ') },
  ];
  DRUMS.forEach((kit, bar) => events.push({ type: 'drums', from: bar * 4, bars: 1, steps: 16, vel: .85, kit, gains: KIT_GAINS }));
  return { bpm: BPM, drum_gain: .6, instruments: {
    synth_bass_1: { g: .6, pan: 0, send: .04, rel: .12 }, sub_bass: { g: .5, pan: 0, send: 0, rel: .05 },
    electric_piano_1: { g: .26, pan: -.22, send: .3, rel: .25 }, pad_3_polysynth: { g: .18, pan: 0, send: .5, rel: .8, soft_attack: true },
    synth_brass_1: { g: .2, pan: .12, send: .35, rel: .35 }, glockenspiel: { g: .16, pan: .3, send: .45, rel: 1.0 } }, events };
}
function sfxData() {
  const cues = [], r = (x, n) => +x.toFixed(n), n1 = Math.min(3, Math.max(1, Math.ceil((TIER_LINE || '').length / 9)));
  const add = (t, fx, db, args = {}, o = {}) => { const c = { t: r(t, 3), fx, db }; if (o.pan) c.pan = r(o.pan, 2); if (o.send !== undefined) c.send = o.send; if (o.times) c.times = o.times.map((x) => r(x, 3)); if (Object.keys(args).length) c.args = args; cues.push(c); };
  // 1. the art rises; the thanks; the tier, line by line
  add(.05, 'swoosh_soft', -22, { sec: .9 }, { pan: -.3 });
  if (COPY.thanks) add(.4, 'shimmer', -31, { sec: .7 });
  if (TIER_LINE) for (let i = 0; i < n1 && i < 3; i++) add(.82 + i * .22, 'swoosh_soft', -23, { sec: .35 }, { pan: -.25 });
  add(REVEAL - .5, 'swoosh_soft', -24, { sec: .4 });
  if (ART.image || ART.bright) add(REVEAL + .4, 'swoosh_soft', -27, { sec: .7 }, { pan: .2 }); // the art comes back, quiet
  // 2. the panel: a line, then it opens; the logo
  add(REVEAL - .24, 'zip', -24, { sec: .22, f0: 500, f1: 2400 });
  add(REVEAL, 'whoosh', -15, { sec: .55, f0: 260, f1: 2600, peak: .6 }); add(REVEAL, 'thunk', -19, { sec: .3 });
  add(REVEAL + .3, 'chime', -24, {}, { send: .35 });
  if (TIER_LINE) { add(REVEAL + .82, 'pop', -20, { f0: 620, f1: 220, sec: .09 }); add(6, 'blip', -30, { f: 1320, sec: .07 }); }
  // 3. the panel settles; the words
  add(WHO - .25, 'whoosh', -18, { sec: .7, f0: 300, f1: 2000, peak: .5 });
  if (WALL_LINE) add(WHO + .5, 'tick', -29, {}, { times: Array.from({ length: Math.min(14, WALL_LINE.length) }, (_, i) => WHO + .5 + i * .45 / Math.min(14, WALL_LINE.length)) });
  if (NAME) add(WHO + .86, 'swoosh_soft', -22, { sec: .4 }, { pan: WIDE ? .3 : 0 });
  if (LINE) add(WHO + 1.3, 'keys', -32, { sec: .55, rate: 16 });
  if (FIND || LINK) { add(WHO + 2.5, 'pop', -19, { f0: 520, f1: 180, sec: .1 }); add(WHO + 2.52, 'blip', -27, { f: 1320, sec: .08 }); add(12, 'blip', -31, { f: 988, sec: .07 }); add(14, 'blip', -31, { f: 988, sec: .07 }); }
  add(WALL - .58, 'swoosh_soft', -24, { sec: .4 });
  // 4. the wall
  add(WALL - .22, 'whoosh', -15, { sec: .7, f0: 200, f1: 2400, peak: .6 }); add(WALL + .2, 'boom', -19, { sec: .9 });
  add(WALL + .5, 'shimmer', -24, { sec: 1.1, f0: 800, f1: 5000 });
  // 5. the wall drops away; the sign-off
  add(SIGN - .5, 'whoosh', -17, { sec: .6, f0: 2200, f1: 300, peak: .5 });
  const big = [EV.dates, EV.city].filter(Boolean).length;
  for (let i = 0; i < big; i++) add(SIGN + .14 + i * .2, 'swoosh_soft', -23, { sec: .35 }, { pan: -.25 });
  if (EV.url) { add(SIGN + 2, 'pop', -18, { f0: 500, f1: 160, sec: .12 }); add(SIGN + 2.02, 'blip', -26, { f: 988, sec: .1 }); }
  add(LAST, 'crash', -22, { sec: 2.2 }, { send: .4 }); add(LAST, 'chime', -22, {}, { send: .35 });
  return cues.sort((a, b) => a.t - b.t);
}

SK.film({ duration: 26.0, camera: SK.camera([[0, [W / 2, H / 2, 1]]]), handheld: false, speedLines: false, fadeOut: 0, draw, sound: { score: scoreData, sfx: sfxData } });
