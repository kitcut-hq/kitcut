// For: people who follow tech and tech conferences on YouTube and social media -- a conference's speaker promo
/* A conference's speakers in 26 s, with no narration: the music carries it. This film is a template:
   every word, colour, logo and person is in content.json (SK.DATA.content) and nothing of the event is
   in the code, so another conference is another content.json and its pictures. The frame is the
   manifest's: 1920 x 1080 for YouTube, 1080 x 1080 for a feed; every layout below reads W and H.

   The story is a trip: the logo on a ground of tiles cut from peaks, a split-flap departures board with
   the city, the dates and the venue, a paper plane that takes off from it and stays for the speakers,
   the featured speakers on a carousel with a name block that turns to each new name, the plane turning
   into a boarding pass, and the poster.

   The clock below (S1..S6, TURN, IRIS) is the one home of its timing: the score and every sound cue are
   worked out from it and from the content at the bottom of this file (SK.film({sound})), so
   `sketch-render.py --sound-data` writes a score.json and sfx.json that fit whatever the content is.
   World units are screen pixels: the 2D camera sits still on the middle of the frame, and the 3D
   pieces (sketch/space.js) look at it too.
*/
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, inv = SK.inv, TAU = SK.TAU;
const rnd = SK.rnd;
const CX = W / 2, CY = H / 2, WIDE = W / H > 1.3, DX = CX - 540; // DX: how far a square layout moves right
const D = SK.DATA.content;

/* ------------------------------------------------------------------ the palette
   Three brand colours are enough -- ground (the dark one the type sits on), accent and second; every
   shade the film uses is worked out from them unless content.json names it. */
function rgbOf(hex) { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
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
function mixHex(a, b, u) { // from colour a to colour b, u 0..1
  const x = rgbOf(a), y = rgbOf(b);
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * u).toString(16).padStart(2, '0')).join('');
}
function contrast(a, b) {
  const lum = (hex) => { const [r, g2, b2] = rgbOf(hex).map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * r + .7152 * g2 + .0722 * b2; };
  const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
function palette(p) {
  const light = p.light ?? '#F4F1EC', L = (hex) => hslOf(hex)[2];
  // light type sits on the ground everywhere: a ground too light for it is darkened until it reads
  let ground = p.ground;
  while (contrast(ground, light) < 7 && L(ground) > .04) ground = withL(ground, L(ground) - .02);
  const g0 = L(ground), a = p.accent, a0 = L(a), s2 = p.second, s0 = L(s2);
  const d = {
    accent: a, second: s2, light, paper: '#FBF8F2', keel: '#DCD5C8',
    groundDk: withL(ground, g0 * .65), groundMid: withL(ground, g0 * 1.63), groundLt: withL(ground, g0 * 2.3),
    accentDk: withL(a, a0 * .75), accentLt: withL(a, Math.min(.85, a0 * 1.55)),
    secondDk: withL(s2, s0 * .73), secondLt: withL(s2, Math.min(.85, s0 * 1.9)),
    soft: withL(ground, .72, .3), cell: withL(ground, g0 * 1.55), board: withL(ground, g0 * 1.05),
    edge: withL(ground, g0 * .6), peaks: withL(ground, g0 * 1.4),
  };
  d.shadow = rgbOf(withL(ground, g0 * .3)).join(',');
  d.wallShadow = `rgba(${rgbOf(withL(a, .12)).join(',')},.45)`;
  d.dim = `rgba(${rgbOf(d.groundDk).join(',')},.35)`;
  const out = { ...d, ...p, ground };
  out.ink = out.ground;
  out.groundRGB = rgbOf(out.ground).join(',');
  return out;
}
const C = palette(D.palette);
SK.setStyle('clean', { grain: .5, vignette: .22, handheld: 0, vignetteRGB: C.shadow });
Object.assign(SK.C, { paper: C.ground, text: C.light, textSoft: C.soft, accent: C.accent, accentText: C.accent, ink: C.ink });
const FONT = { cond: '"Sofia Sans Condensed"', wide: '"Sofia Sans"', ui: '"Inter"', ...(D.fonts || {}) };

/* ------------------------------------------------------------------ the words */
const EV = D.event;
const words = (str) => String(str ?? '').replace(/\{(\w+)\}/g, (_, k) => EV[k] ?? '');
const COPY = Object.fromEntries(Object.entries(D.copy).map(([k, v]) => [k, words(v)]));
const EVENT = {
  name: EV.name, year: EV.year, city: EV.city, code: EV.city_code, dates: EV.dates, datesLong: EV.dates_long,
  venue: EV.venue, venueShort: EV.venue_short || EV.venue, tagline: EV.tagline, cta: EV.cta, url: EV.url,
  line2: `${EV.city} · ${EV.dates_long}`,
  ticker: EV.ticker || `${EV.name} ${EV.year}  ✦  ${EV.city}  ✦  ${EV.dates_long}  ✦  ${EV.venue}  ✦  `,
};

/* ------------------------------------------------------------------ the people
   The featured are the speakers with a name, in order; they come to the front of the ring in turn and
   everyone else fills it. The carousel always makes STOPS stops -- so the clock and the sound never
   change with the content: fewer featured come round again, and a short line-up repeats round the ring. */
const PEOPLE = D.speakers;
const STOPS = 5;
const FEAT = PEOPLE.filter((p) => p.name).slice(0, STOPS), F = FEAT.length;
const SPEAKERS = [...Array.from({ length: STOPS }, (_, k) => FEAT[k % F]), ...PEOPLE.filter((p) => !FEAT.includes(p))];
while (SPEAKERS.length < 12) SPEAKERS.push(PEOPLE[SPEAKERS.length % PEOPLE.length]);

/* ------------------------------------------------------------------ the clock (120 bpm: a beat is .5 s) */
const S1 = [0, 2.8];        // the mark on the tiles
const S2 = [2.62, 6.45];    // the departures board
const S4 = [6.3, 15.3];    // the speakers
const TURN = [8.5, 10.0, 11.5, 13.0]; // the carousel turns to speaker 1..4 on these beats
const S5 = [15.3, 19.55];   // the boarding pass
const S6 = [19.3, 26.0];    // the poster
const IRIS = [19.12, 19.5]; // ... which opens out of the pass's button
const LAND = 6.5, PASS_IN = 15.5, LAST = 24; // the speakers land, the pass comes up, the last chord

/* ------------------------------------------------------------------ small helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (t) => { const c3 = k + 1; return 1 + c3 * Math.pow(t - 1, 3) + k * Math.pow(t - 1, 2); };
const outBack = back(1.5), outBackSoft = back(.9);
function font(size, wt = 900, fam = FONT.cond) { return `${wt} ${size}px ${fam}`; }
/** text at x, y (alphabetic baseline). o: size, wt, fam, col, align, ls (px), alpha */
function text(str, x, y, o = {}) {
  const c = g(); c.save();
  c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? FONT.cond);
  c.textAlign = o.align ?? 'left'; c.textBaseline = o.base ?? 'alphabetic';
  c.letterSpacing = (o.ls ?? 0) + 'px';
  c.globalAlpha *= o.alpha ?? 1; c.fillStyle = o.col ?? C.light;
  c.fillText(str, x, y); c.restore();
}
function measure(str, o = {}) {
  const c = g(); c.save(); c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? FONT.cond); c.letterSpacing = (o.ls ?? 0) + 'px';
  const w = c.measureText(str).width; c.restore(); return w;
}
/** the largest size up to max at which str fits in width */
function fit(str, width, max, o = {}) { return Math.min(max, max * width / Math.max(1, measure(str, { ...o, size: max }))); }
function clipRect(x, y, w, h, fn) { const c = g(); c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); fn(); c.restore(); }
function rrect(x, y, w, h, r, fill) { const c = g(); SK.rrPath(x, y, w, h, r); c.fillStyle = fill; c.fill(); }
function poly(pts, fill) { const c = g(); c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); for (const p of pts.slice(1)) c.lineTo(p[0], p[1]); c.closePath(); c.fillStyle = fill; c.fill(); }
function withT(x, y, rot, s, fn) { SK.at(x, y, rot, s, fn); }

/* the logo (content.logo): an image, a light version of it for dark grounds, and optionally what was
   measured off it -- its symbol as two polygons ("mark": a and b on one baseline, drawn in code so they
   can rise and be dived into) and its letters' column spans ("letters", so they rise one by one).
   Without them the whole image is revealed by a wipe and the film dives into a disc of the accent. */
const LG = D.logo || {};
const MARK = LG.mark ? { a: LG.mark.a, b: LG.mark.b, cx: LG.mark.cx, base: LG.mark.base, dive: LG.mark.dive } : null;
const LETTERS = LG.letters || null;
const logoImg = (light) => SK.IMG[(light && LG.light) || LG.image];
/** the scale at which the logo fits a box w x h */
const logoScale = (w, h, light) => { const im = logoImg(light); return im ? Math.min(w / im.width, h / im.height) : 0; };
/** drawn about its base centre; grow = [a, b] 0..1 rises each from it */
function mark(x, y, s, grow = [1, 1], cols = [C.second, C.accent]) {
  if (!MARK) return;
  for (const [k, pts] of [[0, MARK.a], [1, MARK.b]]) {
    const k2 = grow[k]; if (k2 <= 0) continue;
    poly(pts.map(([px, py]) => [x + (px - MARK.cx) * s, y + (py - MARK.base) * s * k2]), cols[k]);
  }
}
/* the logo image, letter by letter where its letters were measured, else wiped on left to right */
function wordmark(light, x, y, s, t0, t, o = {}) { // x, y: its top-left; letters rise from under a mask, one after another
  const im = logoImg(light); if (!im) return;
  const c = g(), step = o.step ?? .045, d = o.d ?? .42;
  if (!LETTERS) {
    const u = outBackSoft(clamp((t - t0) / (d + 8 * step))); if (u <= 0) return;
    c.save(); c.beginPath(); c.rect(x - 4, y - 4, (im.width * s + 8) * Math.min(1, u), im.height * s + 8); c.clip();
    c.drawImage(im, x, y, im.width * s, im.height * s); c.restore();
    return;
  }
  LETTERS.forEach(([a, b], i) => {
    const u = clamp((t - t0 - i * step) / d); if (u <= 0) return;
    const dy = (1 - outBackSoft(u)) * im.height * 1.1;
    c.save(); c.beginPath(); c.rect(x + (a - 2) * s, y - 4, (b - a + 4) * s, im.height * s + 8); c.clip();
    c.drawImage(im, a - 2, 0, b - a + 4, im.height, x + (a - 2) * s, y + dy * s, (b - a + 4) * s, im.height * s);
    c.restore();
  });
}

/* ------------------------------------------------------------------ tiles: azulejos cut from peaks
   Each tile is split on its diagonals into four peaks; they turn a quarter at a time in a wave
   that starts in the middle, so the pattern keeps re-forming. cols: [ground, peak A, peak B] */
function tiles(t, o = {}) {
  const S = o.size ?? 180, cols = o.cols ?? [C.groundDk, C.accent, C.ground], c = g();
  const z = o.zoom ?? 1, cx = o.cx ?? W / 2, cy = o.cy ?? H / 2, spin = o.spin ?? 0;
  c.save(); c.translate(cx, cy); c.rotate(spin); c.scale(z, z);
  c.fillStyle = cols[0]; c.fillRect(-W, -H, W * 2 / z + W, H * 2 / z + H);
  const n = Math.ceil((Math.max(W, H) * .75) / (S * z)) + 1;
  for (let j = -n; j <= n; j++) {
    for (let i = -n; i <= n; i++) {
      const x = i * S, y = j * S, dist = Math.hypot(i, j);
      // a quarter turn every beat, arriving later the further out the tile is
      const beat = (t - (o.t0 ?? 0)) * 2 - dist * .35;
      const k = Math.floor(beat), f = beat - k;
      const a = ((i + j) & 1 ? -1 : 1) * (k + outBack(clamp(f / .55))) * Math.PI / 2;
      c.save(); c.translate(x, y); c.beginPath(); c.rect(-S / 2 + 3, -S / 2 + 3, S - 6, S - 6); c.clip();
      c.rotate(a);
      const h = S / 2 + 2;
      c.fillStyle = cols[1];
      c.beginPath(); c.moveTo(-h, -h); c.lineTo(h, -h); c.lineTo(0, 0); c.closePath(); c.fill();
      c.beginPath(); c.moveTo(-h, h); c.lineTo(h, h); c.lineTo(0, 0); c.closePath(); c.fill();
      c.fillStyle = cols[2];
      c.beginPath(); c.moveTo(-h, -h); c.lineTo(-h, h); c.lineTo(0, 0); c.closePath(); c.fill();
      c.beginPath(); c.moveTo(h, -h); c.lineTo(h, h); c.lineTo(0, 0); c.closePath(); c.fill();
      if (o.dot) { c.fillStyle = o.dot; c.beginPath(); c.arc(0, 0, S * .075, 0, TAU); c.fill(); }
      c.restore();
    }
  }
  c.restore();
}

/* ------------------------------------------------------------------ S1: the mark on the tiles */
const LOGO = { s: 1.3, base: 547, wordY: 591, word: .82, line2: 762, card: 740 };
// the dive: into the symbol's accent peak where there is one, else into the middle of the card
const S1_ZOOM_AT = MARK ? [CX + (MARK.dive[0] - MARK.cx) * LOGO.s, LOGO.base + (MARK.dive[1] - MARK.base) * LOGO.s] : [CX, CY];
function scene1(t) {
  const c = g();
  // the dive into the peak: a log-space zoom that ends with the peak's accent over the whole frame.
  // With no symbol to dive into, the card itself turns the accent as the logo on it fades, and the
  // camera dives into the card (a disc of the accent opening over the logo read as a stray blot)
  const dive = ease(t, 2.3, 2.8, E.in);
  const turn = MARK ? 0 : E.inOut(clamp((t - 2.0) / .45)), fade = 1 - clamp((t - 1.95) / .3);
  const zoom = Math.exp(Math.log(40) * dive);
  c.fillStyle = C.groundDk; c.fillRect(0, 0, W, H);
  c.save();
  c.translate(S1_ZOOM_AT[0], S1_ZOOM_AT[1]); c.scale(zoom, zoom); c.translate(-S1_ZOOM_AT[0], -S1_ZOOM_AT[1]);
  tiles(t, { zoom: 1.04 + t * .035, spin: -.05 + t * .02 });
  // the card: a tile of paper that turns square as it grows
  // it starts at -.14 s, so frame 0 already shows a small card rather than bare tiles
  const p = ease(t, -.14, .5, outBack), side = LOGO.card * p, rot = (1 - ease(t, 0, .6, outBackSoft)) * Math.PI / 4;
  if (side > 1) {
    withT(CX, CY, rot, 1, () => {
      c.save(); c.shadowColor = `rgba(${C.shadow},.55)`; c.shadowBlur = 50; c.shadowOffsetY = 18;
      rrect(-side / 2, -side / 2, side, side, 56 * p, turn ? mixHex(C.paper, C.accent, turn) : C.paper); c.restore();
    });
  }
  // the symbol: its first shape, then the peak, rising from one baseline
  mark(CX, LOGO.base, LOGO.s, [ease(t, .04, .42, outBack), ease(t, .12, .56, outBack)]);
  // the wordmark, a letter at a time (under the symbol, or the whole logo on the card); then the line under it
  if (MARK) {
    const ws = logoScale(827 * LOGO.word, 150), wx = CX - logoImg().width * ws / 2;
    wordmark(false, wx, LOGO.wordY, ws, .52, t);
  } else {
    const ws = logoScale(600, 380), im = logoImg(); // centred between the card's top and the line under it
    if (im && fade > 0) SK.alpha(fade, () => wordmark(false, CX - im.width * ws / 2, 455 - im.height * ws / 2, ws, .12, t, { d: .6 }));
  }
  const lp = ease(t, 1.1, 1.6, E.out);
  if (lp > 0 && (MARK || fade > 0)) SK.alpha(MARK ? 1 : fade, () => {
    const str = EVENT.line2, size = 34, w = measure(str, { size, wt: 800, fam: FONT.wide, ls: 3 });
    const y = LOGO.line2;
    clipRect(CX - w / 2 - 4, y - 40, (w + 8) * lp, 60, () => text(str, CX, y, { size, wt: 800, fam: FONT.wide, ls: 3, col: C.ground, align: 'center' }));
    if (lp < 1) { c.fillStyle = C.accent; c.fillRect(CX - w / 2 + (w + 8) * lp - 4, y - 32, 5, 40); }
  });
  c.restore();
}

/* ------------------------------------------------------------------ S2: the departures board */
const BOARD = { w: 1200, h: 830, cw: 104, ch: 150, gap: 10, x0: 35 };
const ROWS = [
  { label: COPY.destination, str: EVENT.city, t0: 2.95 },
  { label: COPY.dates, str: EVENT.dates.replace('–', '-'), t0: 3.45 },
  { label: COPY.gate, str: EVENT.venueShort, t0: 3.95 },
];
const FLAP_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
const FLIP = .052;
/** one split-flap cell at x, y showing where its flips have got to at time t */
function flapCell(x, y, target, seed, t0, t) {
  const w = BOARD.cw, h = BOARD.ch, c = g(), mid = y + h / 2;
  const nf = target === ' ' ? 0 : 5 + Math.floor(rnd(seed) * 6);
  const seq = [' ']; for (let k = 1; k < nf; k++) seq.push(FLAP_CHARS[Math.floor(rnd(seed * 13 + k) * FLAP_CHARS.length)]); seq.push(target);
  const pos = (t - t0) / FLIP, k = clamp(Math.floor(pos), 0, seq.length - 1), f = pos - Math.floor(pos);
  const from = seq[k], to = seq[Math.min(seq.length - 1, k + 1)], flipping = pos >= 0 && k < seq.length - 1;
  const half = (ch, top, sy = 1, shade = 0) => {
    c.save(); c.beginPath(); c.rect(x, top ? y : mid, w, h / 2); c.clip();
    if (sy !== 1) { c.translate(0, mid); c.scale(1, sy); c.translate(0, -mid); }
    rrect(x, y, w, h, 10, C.cell);
    if (ch !== ' ') text(ch, x + w / 2, mid + 43, { size: 124, wt: 800, col: C.light, align: 'center' });
    if (shade > 0) { c.fillStyle = `rgba(0,0,0,${shade})`; c.fillRect(x, y, w, h); }
    c.restore();
  };
  if (!flipping) { half(from, true); half(from, false); }
  else {
    half(to, true); half(from, false); // behind the falling flap: the new top, the old bottom
    if (f < .5) half(from, true, Math.cos(f * Math.PI), f * .9); // the old top falls towards the hinge
    else half(to, false, -Math.cos(f * Math.PI), (1 - f) * .7); // the new bottom lands
  }
  c.fillStyle = C.groundDk; c.fillRect(x, mid - 2.5, w, 5); // the hinge
}
function boardFace(t) {
  return (c, w, h) => {
    rrect(0, 0, w, h, 34, C.board);
    // header
    SK.rrPath(0, 0, w, h, 34); c.save(); c.clip(); c.fillStyle = C.second; c.fillRect(0, 0, w, 116); c.restore();
    text(COPY.departures, 44, 84, { size: 78, wt: 900, col: C.ground });
    const bw = measure(COPY.boarding, { size: 30, wt: 800, fam: FONT.ui, ls: 4 }) + 44, blink = t > 4.55 ? (Math.floor((t - 4.55) * 4) % 2 === 0 ? 1 : .35) : ease(t, 4.3, 4.55);
    SK.alpha(blink, () => { rrect(w - 44 - bw, 30, bw, 56, 28, C.accent); text(COPY.boarding, w - 44 - bw / 2 + 2, 69, { size: 30, wt: 800, fam: FONT.ui, ls: 4, align: 'center', col: C.light }); });
    ROWS.forEach((r, ri) => {
      const top = 150 + ri * 222;
      text(r.label, BOARD.x0 + 4, top + 22, { size: 22, wt: 700, fam: FONT.ui, ls: 5, col: C.secondLt });
      for (let i = 0; i < 10; i++) {
        const ch = (r.str[i] ?? ' ').toUpperCase();
        flapCell(BOARD.x0 + i * (BOARD.cw + BOARD.gap), top + 40, ch, ri * 31 + i * 7 + 3, r.t0 + i * .045, t);
      }
    });
  };
}
function scene2(t) {
  const c = g(), lt = t - S2[0];
  c.fillStyle = C.accent; c.fillRect(0, 0, W, H);
  // a faint ground of peaks on the accent, drifting
  c.save(); c.globalAlpha = .16; c.fillStyle = C.accentDk;
  for (let j = -1; j < 8; j++) for (let i = -1; i < W / 150 + 1; i++) {
    const x = i * 150 + (j & 1) * 75 - (lt * 40) % 150, y = j * 150 + 40;
    c.beginPath(); c.moveTo(x, y + 60); c.lineTo(x + 40, y - 10); c.lineTo(x + 80, y + 60); c.closePath(); c.fill();
  }
  c.restore();
  // the camera travels down the rows as they flip, then pulls back to the whole board
  const tx = DX + SK.kf(t, [[2.62, 330], [3.2, 360], [3.75, 460], [4.3, 520], [4.95, 540], [6.45, 540]]);
  const ty = SK.kf(t, [[2.62, 250], [3.2, 300], [3.75, 480], [4.3, 690], [4.95, 560], [6.45, 540]]);
  const zoom = SK.kf(t, WIDE ? [[2.62, 1.6], [3.2, 1.4], [4.3, 1.26], [4.95, .98], [6.45, .9]] : [[2.62, 1.5], [3.2, 1.3], [4.3, 1.18], [4.95, .8], [6.45, .74]]);
  const yaw = SK.kf(t, [[2.62, -.55], [3.3, -.36], [4.3, -.2], [4.95, -.16], [6.45, -.1]]);
  const pitch = SK.kf(t, [[2.62, .16], [4.3, .06], [6.45, .1]]);
  const roll = SK.kf(t, [[2.62, -.06], [4.95, .015], [6.45, .03]]);
  SK.view3({ x: tx, y: ty, z: 0, yaw, pitch, roll, d: 1500, zoom });
  // the board swings in from the right on the cut
  const sw = ease(t, 2.62, 3.05, outBackSoft);
  const ry = lerp(.9, 0, sw), bx = lerp(900, 0, sw);
  const pose = { x: CX + bx, y: CY, z: 0, ry };
  const P = [[-600, -415, 0], [600, -415, 0], [600, 415, 0], [-600, 415, 0]].map((p) => SK.pose3(p, pose));
  // its shadow on the wall behind
  const Sh = [[-600, -415, 90], [600, -415, 90], [600, 415, 90], [-600, 415, 90]].map((p) => SK.proj3(SK.pose3([p[0] + 40, p[1] + 50, p[2]], pose)));
  if (Sh.every(Boolean)) { c.save(); c.filter = 'blur(22px)'; poly(Sh, C.wallShadow); c.restore(); }
  SK.face3(P, BOARD.w, BOARD.h, boardFace(t), { key: 'board', cull: false });
  // thickness: the board's edge on the right
  const E1 = [[600, -415, 0], [600, -415, 34], [600, 415, 34], [600, 415, 0]].map((p) => SK.pose3(p, pose));
  SK.poly3(E1, C.edge, { light: false });
}

/* ------------------------------------------------------------------ the paper plane (3D) */
const PLANE = { N: [120, 0, 0], T: [-95, 0, 0], L: [-100, -8, -70], R: [-100, -8, 70], K: [-80, 30, 0] };
function catmull3(keys, t) { // keys: [[t, [x, y, z]], ...] -> position at t (Catmull-Rom through them)
  if (t <= keys[0][0]) return keys[0][1];
  if (t >= keys[keys.length - 1][0]) return keys[keys.length - 1][1];
  let i = 0; while (t > keys[i + 1][0]) i++;
  const p0 = keys[Math.max(0, i - 1)][1], p1 = keys[i][1], p2 = keys[i + 1][1], p3 = keys[Math.min(keys.length - 1, i + 2)][1];
  const u = (t - keys[i][0]) / (keys[i + 1][0] - keys[i][0]), u2 = u * u, u3 = u2 * u;
  return [0, 1, 2].map((k) => .5 * (2 * p1[k] + (-p0[k] + p2[k]) * u + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * u2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * u3));
}
const v3 = { sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]], k: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2], cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  n: (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; } };
/** the plane's pose on a path: position, and axes from its velocity, banked into its turns */
function flyPose(path, t, o = {}) {
  const dt = .03, p = catmull3(path, t), a = catmull3(path, t - dt), b = catmull3(path, t + dt);
  let fwd = v3.n(v3.sub(b, a));
  if (o.fwd) fwd = v3.n(o.fwd);
  const acc = v3.k(v3.add(v3.sub(b, p), v3.sub(a, p)), 1 / (dt * dt));
  const up0 = [0, -1, 0];
  let right = v3.n(v3.cross(up0, fwd)); if (!isFinite(right[0])) right = [0, 0, 1];
  let up = v3.cross(fwd, right);
  const lat = v3.dot(acc, right), bank = clamp(Math.atan2(lat, 2600) * 1.3, -1.1, 1.1) + (o.roll ?? 0);
  const cb = Math.cos(bank), sb = Math.sin(bank);
  const r2 = v3.add(v3.k(right, cb), v3.k(up, sb)), u2 = v3.add(v3.k(up, cb), v3.k(right, -sb));
  return { p, fwd, right: r2, up: u2 };
}
function drawPlane(pose, s = 1, o = {}) {
  const P = (q) => v3.add(pose.p, v3.add(v3.k(pose.fwd, q[0] * s), v3.add(v3.k(pose.up, -q[1] * s), v3.k(pose.right, q[2] * s))));
  const N = P(PLANE.N), T = P(PLANE.T), L = P(PLANE.L), R = P(PLANE.R), K = P(PLANE.K);
  const faces = [
    { pts: [N, L, T], col: C.paper }, { pts: [N, T, R], col: C.paper },
    { pts: [N, T, K], col: C.keel },
    // an accent stripe near each wing's trailing edge, a tip in the second colour
    { pts: [lerpP(N, L, .7), L, lerpP(T, L, .7)], col: C.accent }, { pts: [lerpP(N, R, .7), lerpP(T, R, .7), R], col: C.accent },
    { pts: [lerpP(N, L, .9), L, lerpP(T, L, .9)], col: C.second }, { pts: [lerpP(N, R, .9), lerpP(T, R, .9), R], col: C.second },
  ];
  const depth = (f) => f.pts.reduce((s2, q) => { const r = SK.proj3(q); return s2 + (r ? r[2] : 1e9); }, 0) / f.pts.length;
  faces.sort((a, b) => depth(b) - depth(a));
  for (const f of faces) SK.poly3(f.pts, f.col, { light: [-.3, -1, -.4], ambient: .62, alpha: o.alpha ?? 1 });
  return { N, T, K };
}
const lerpP = (a, b, u) => [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)];
function trail(path, t, span, o = {}) { // a dashed line behind the plane: where it has been
  const c = g(), pts = [];
  for (let k = 0; k <= 60; k++) { const tt = t - span * (k / 60); if (tt < path[0][0]) break; const q = SK.proj3(catmull3(path, tt)); if (q) pts.push(q); }
  if (pts.length < 2) return;
  c.save(); c.setLineDash([16, 14]); c.lineDashOffset = t * 60; c.lineCap = 'round';
  for (let k = 1; k < pts.length; k++) {
    c.globalAlpha = (o.alpha ?? 1) * (1 - k / pts.length) * .9;
    c.strokeStyle = o.col ?? C.second; c.lineWidth = (o.w ?? 7) * 1400 / pts[k][2];
    c.beginPath(); c.moveTo(pts[k - 1][0], pts[k - 1][1]); c.lineTo(pts[k][0], pts[k][1]); c.stroke();
  }
  c.restore();
}
// S2: it takes off in front of the board, loops, and comes at the camera
const FLIGHT_A = [[5.05, [WIDE ? -300 : -260, 980, -200]], [5.45, [250 + DX, 760, -300]], [5.8, [760 + DX * 1.4, 560, -420]], [6.05, [700 + DX, 330, -640]], [6.25, [560 + DX, 470, -1000]], [6.45, [520 + DX, 560, -1330]]];

/* ------------------------------------------------------------------ S4: the speakers */
const RING = WIDE ? { cx: CX, cy: 430, rx: 720, ry: 250, frontY: 568, r0: 54, r1: 212, width: .34 }
  : { cx: CX, cy: 440, rx: 470, ry: 230, frontY: 568, r0: 44, r1: 208, width: .3 };
const RING_IN = 6.12; // the circles pop out from the front while the whip is still moving
function ringTurn(t) { // how far the ring has turned, in slots (a smooth step at each TURN)
  let k = 0;
  for (const b of TURN) k += outBackSoft(clamp((t - (b - .22)) / .62));
  return k;
}
function speakerCircle(sp, i, x, y, r, front, t) {
  const c = g(), im = SK.IMG[sp.image];
  const fill = i % 2 ? C.second : C.accent;
  c.save();
  c.beginPath(); c.arc(x, y, r, 0, TAU); c.fillStyle = fill; c.fill(); c.clip();
  if (im) { const s = 2 * r / .74; c.drawImage(im, x - s / 2, y - s * .47, s, s); }
  if (front < .999) { c.fillStyle = C.ground; c.globalAlpha = .64 * Math.pow(1 - front, .8); c.fillRect(x - r, y - r, 2 * r, 2 * r); }
  c.restore();
  if (front > .6) { c.save(); c.globalAlpha = clamp((front - .6) / .4); c.lineWidth = 6; c.strokeStyle = C.light; c.beginPath(); c.arc(x, y, r + 1, 0, TAU); c.stroke(); c.restore(); }
}
function chevrons(t, yMax) { // the ground: zigzag peaks, rising slowly
  const c = g(), step = 54, amp = 15, wl = 64;
  c.save(); c.beginPath(); c.rect(0, 0, W, yMax); c.clip();
  c.strokeStyle = C.groundMid; c.lineWidth = 9; c.lineJoin = 'miter';
  const off = (t * 22) % step;
  for (let y = -step; y < yMax + step; y += step) {
    c.beginPath();
    for (let x = -wl, k = 0; x <= W + wl; x += wl / 2, k++) c.lineTo(x, y - off + (k & 1 ? -amp : amp));
    c.stroke();
  }
  c.restore();
}
function nameFaces(t) {
  // which speaker the block is on, and how far through a turn it is
  let k = 0, u = 0;
  TURN.forEach((b, i) => { const p = clamp((t - (b - .22)) / .62); if (p >= 1) k = i + 1; else if (p > 0) { k = i; u = p; } });
  const face = (j) => (c, w, h) => {
    const at = ((j - k) % 4 + 4) % 4; // 0: front now, 1: coming to the front, 2: coming in on the side
    const who = at === 0 ? k : at === 1 ? (u > 0 ? k + 1 : k) : at === 2 ? k + 1 : -1;
    if (who < 0 || who >= STOPS) return;
    const sp = SPEAKERS[who];
    const nameIn = at === 0 ? (k === 0 ? ease(t, 7.05, 7.5, E.out) : 1) : clamp((u - .42) / .5);
    if (at === 0 || (at === 1 && u > 0)) {
      if (at === 1 && u < .38) { roleFace(c, w, h, SPEAKERS[k], 1 - u / .26); return; }
      const size = fit(sp.name, w - 90, 120, { wt: 900 });
      clipRect(0, 0, 40 + (w - 40) * nameIn, h, () => text(sp.name, 42, h / 2 + size * .36, { size, wt: 900, col: C.ground }));
      c.fillStyle = C.accent; c.fillRect(0, 0, 14, h);
    } else if (at === 1) roleFace(c, w, h, sp, k === 0 ? ease(t, 7.3, 7.7, E.out) : 1);
    else if (at === 2) roleFace(c, w, h, sp, clamp((u - .35) / .5));
  };
  return { k, u, faces: { front: { draw: face(0) }, right: { draw: face(1) }, back: { draw: face(2) }, left: { draw: face(3) } } };
}
const SIDE_STRETCH = 1.55; // the side face is seen at a slant: its type is drawn wide so it reads as normal
function roleFace(c, w, h, sp, a) {
  if (a <= 0) return;
  SK.alpha(a, () => {
    const role = sp.role, org = sp.org, k = SIDE_STRETCH;
    c.save(); c.scale(k, 1);
    const rs = fit(role, (w - 240) / k, 34, { wt: 800, fam: FONT.ui, ls: 3 });
    text(role, 60 / k, 56, { size: rs, wt: 800, fam: FONT.ui, ls: 3, col: C.accent });
    const size = fit(org, (w - 250) / k, 92, { wt: 900 });
    text(org, 56 / k, 60 + 16 + size * .76, { size, wt: 900, col: C.ground });
    c.restore();
    // the arrow
    const ax = w - 100, ay = h / 2 + 8; c.strokeStyle = C.second; c.lineWidth = 12; c.lineCap = 'round'; c.lineJoin = 'round';
    c.beginPath(); c.moveTo(ax - 40, ay); c.lineTo(ax + 34, ay); c.moveTo(ax + 6, ay - 28); c.lineTo(ax + 36, ay); c.lineTo(ax + 6, ay + 28); c.stroke();
  });
}
// the plane in S4: flies in from the left, hovers beside the front speaker, leaves at the camera
const HOVER = WIDE ? [W - 250, 690, 0] : [880, 330, 0];
const FLIGHT_B = WIDE ? [[6.3, [-300, 640, -300]], [6.7, [520, 250, -80]], [7.15, [W - 420, 380, 0]], [7.5, HOVER]]
  : [[6.3, [-300, 640, -300]], [6.7, [240, 250, -80]], [7.15, [760, 250, 0]], [7.5, HOVER]];
const FLIGHT_C = [[14.55, HOVER], [14.8, [HOVER[0] - 60, HOVER[1] + 30, -150]], [15.05, [CX + 100, 520, -700]], [15.3, [CX + 20, 560, -1300]]];
function planeS4(t) {
  if (t < FLIGHT_B[0][0] || t > FLIGHT_C[FLIGHT_C.length - 1][0]) return;
  SK.view3({ d: 1400 });
  let pose;
  if (t < 7.5) pose = flyPose(FLIGHT_B, t);
  else if (t < 14.55) { // the hover: a slow bob, nose towards the speaker
    const b = Math.sin((t - 7.5) * 2.6), b2 = Math.sin((t - 7.5) * 1.7 + 1);
    const p = [HOVER[0] + b2 * 6, HOVER[1] + b * 9, 0];
    const blend = clamp((t - 7.5) / .5);
    const fwd = v3.n([lerp(1, -1, E.inOut(blend)), .08 * b, lerp(0, .35, blend)]);
    pose = flyPose([[0, p], [1, p]], .5, { fwd, roll: -.5 * blend + .1 * b2 });
    pose.p = p;
  } else pose = flyPose(FLIGHT_C, t);
  if (t < 7.6) trail(FLIGHT_B, t, .9, { col: C.second });
  const k = drawPlane(pose, 1.05);
  // the boarding-pass tag it carries, on a thread from its keel
  const q = SK.proj3(k.K); if (!q || t > 14.9) return;
  const sw = Math.sin(t * 3.1) * .12 + (t < 7.6 ? .5 * Math.sin(t * 9) * (7.6 - t) : 0);
  withT(q[0], q[1], sw, 1400 / q[2], () => {
    const c = g(); c.strokeStyle = C.light; c.lineWidth = 3; c.beginPath(); c.moveTo(0, 0); c.lineTo(0, 44); c.stroke();
    tag(-62, 44, 124, 62);
  });
}
function tag(x, y, w, h) { // a small boarding pass
  const c = g();
  c.save(); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 12; c.shadowOffsetY = 5; rrect(x, y, w, h, 8, C.paper); c.restore();
  c.save(); SK.rrPath(x, y, w, h, 8); c.clip(); c.fillStyle = C.accent; c.fillRect(x, y, w, 16); c.restore();
  text(COPY.tag, x + 10, y + 46, { size: 24, wt: 900, col: C.ground });
  c.strokeStyle = C.ground; c.setLineDash([3, 3]); c.lineWidth = 2; c.beginPath(); c.moveTo(x + w - 22, y + 18); c.lineTo(x + w - 22, y + h - 4); c.stroke(); c.setLineDash([]);
}
function scene4(t) {
  const c = g();
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  chevrons(t, 780);
  // the frame's furniture
  const f = ease(t, 6.5, 7.0, E.out);
  SK.alpha(f, () => {
    rrect(48, 46, 18, 18, 3, C.second);
    text(COPY.speakers, 78, 64, { size: 22, wt: 800, fam: FONT.ui, ls: 4, col: C.light });
    text(`${EVENT.city} · ${EVENT.dates}`, W - 48, 64, { size: 22, wt: 800, fam: FONT.ui, ls: 4, col: C.light, align: 'right' });
  });
  // the camera: a slow push through the whole section, and a kick on each turn's landing
  const kick = TURN.reduce((s, b) => s + (t >= b + .2 ? .018 * Math.pow(Math.max(0, 1 - (t - b - .2) / .55), 2) : 0), 0);
  const push = 1 + .05 * E.sine(clamp((t - 6.4) / 8.9)) + kick;
  c.save(); c.translate(CX, 600); c.scale(push, push); c.translate(-CX, -600);
  // the ring: every speaker on one ellipse; the one at the front grows into the big circle
  const turn = ringTurn(t), N = SPEAKERS.length;
  const items = SPEAKERS.map((sp, i) => {
    let d = ((i - turn) / N) * TAU; d = Math.atan2(Math.sin(d), Math.cos(d)); // angle from the front
    const bump = Math.exp(-Math.pow(d / RING.width, 2));
    const ex = RING.cx + RING.rx * Math.sin(d), ey = RING.cy + RING.ry * Math.cos(d);
    const y = lerp(ey, RING.frontY, bump), r = RING.r0 + (RING.r1 - RING.r0) * bump;
    // they arrive one after another from the middle out
    const pop = outBack(clamp((t - RING_IN - Math.abs(d) * .12) / .42));
    return { sp, i, x: ex, y, r: r * pop, bump };
  }).filter((o) => o.r > .5);
  items.sort((a, b) => a.r - b.r);
  for (const o of items) speakerCircle(o.sp, o.i, o.x, o.y, o.r, o.bump, t);
  // the name block: a paper box that turns a quarter to each new speaker, with the ring
  const nf = nameFaces(t);
  const rise = ease(t, 6.55, 7.05, outBackSoft);
  SK.view3({ x: CX, y: 812, z: 0, sx: CX, sy: 812, d: 2600 });
  const turnB = (nf.k + outBackSoft(nf.u)) * Math.PI / 2;
  const L = 720;
  SK.box3({
    x: CX, y: lerp(1180, 872, rise), z: L / 2 + 20, w: L, h: 150, d: L,
    rx: 0, ry: .52 + turnB, fill: C.paper,
    light: [-.35, -1, -.5], ambient: .72, shadeK: .9, key: 'nameblock',
    faces: { ...nf.faces, top: { fill: '#FFFFFF' }, bottom: false },
  });
  if (WIDE) counter(t, nf);
  planeS4(t);
  c.restore();
}
/** which featured speaker this is, 01 / 05, left of the name block where a wide frame has room; the
    number rolls up to the next as the block turns (and round again when fewer than STOPS are featured) */
function counter(t, nf) {
  const a = ease(t, 6.9, 7.3, E.out); if (a <= 0) return;
  const x = 120, y = 918, size = 170, u = nf.u > 0 ? outBackSoft(nf.u) : 0;
  SK.alpha(a, () => {
    text(COPY.speaker, x + 4, y - 150, { size: 22, wt: 800, fam: FONT.ui, ls: 5, col: C.secondLt });
    clipRect(x - 10, y - size * .78, 240, size * .86, () => {
      const n = (k) => String(k % F + 1).padStart(2, '0');
      text(n(nf.k), x, y - u * size * .9 + (1 - a) * 60, { size, wt: 900, col: C.light });
      if (u > 0) text(n(nf.k + 1), x, y + (1 - u) * size * .9, { size, wt: 900, col: C.light });
    });
    text('/ ' + String(F).padStart(2, '0'), x + measure('00', { size, wt: 900 }) + 14, y, { size: 56, wt: 900, col: C.accent });
  });
}

/* ------------------------------------------------------------------ S5: the boarding pass */
const PASS = { w: 900, h: 440, stub: 680 };
function passFace(t) {
  return (c, w, h) => {
    rrect(0, 0, w, h, 30, C.paper);
    // header band
    c.save(); SK.rrPath(0, 0, w, h, 30); c.clip();
    c.fillStyle = C.accent; c.fillRect(0, 0, w, 96);
    c.fillStyle = C.secondDk; c.fillRect(PASS.stub, 0, w - PASS.stub, 96);
    c.restore();
    mark(78, 76, .27, [1, 1], [C.second, C.light]);
    const nx = MARK ? 122 : 44;
    text(EVENT.name, nx, 68, { size: fit(EVENT.name, PASS.stub - 300 - nx, 46, { wt: 900 }), wt: 900, col: C.light });
    text(COPY.boarding_pass, PASS.stub - 36, 62, { size: 20, wt: 800, fam: FONT.ui, ls: 5, col: C.light, align: 'right' });
    text(EVENT.year, PASS.stub + (w - PASS.stub) / 2, 68, { size: 46, wt: 900, col: C.light, align: 'center' });
    // perforation
    c.fillStyle = C.ground; c.beginPath(); c.arc(PASS.stub, 0, 20, 0, TAU); c.arc(PASS.stub, h, 20, 0, TAU); c.fill();
    c.strokeStyle = `rgba(${C.groundRGB},.35)`; c.lineWidth = 3; c.setLineDash([9, 9]); c.beginPath(); c.moveTo(PASS.stub, 110); c.lineTo(PASS.stub, h - 26); c.stroke(); c.setLineDash([]);
    // from / to
    const lab = (s, x, y) => text(s, x, y, { size: 17, wt: 700, fam: FONT.ui, ls: 4, col: `rgba(${C.groundRGB},.55)` });
    const reveal = (a, b) => ease(t, a, b, E.out);
    lab(COPY.from, 44, 140); lab(COPY.to, 400, 140);
    SK.alpha(reveal(15.75, 16.0), () => text(COPY.you, 40, 262, { size: 150, wt: 900, col: C.ground }));
    SK.alpha(reveal(15.9, 16.15), () => text(EVENT.code, 396, 262, { size: 150, wt: 900, col: C.ground }));
    lab(COPY.anywhere, 44, 296); lab(EVENT.city, 400, 296);
    // a little plane between them
    SK.alpha(reveal(15.82, 16.1), () => { withT(330 + (1 - reveal(15.82, 16.2)) * -40, 208, 0, 1, () => { poly([[-36, -14], [36, 0], [-36, 14], [-24, 0]], C.accent); }); });
    // the fields
    const fields = [[COPY.date, EVENT.dates], [COPY.gate, EVENT.venueShort], [COPY.boarding, COPY.boarding_now]];
    fields.forEach(([k2, v], i) => {
      const x = 44 + i * 210; lab(k2, x, 350);
      const r = reveal(16.1 + i * .12, 16.35 + i * .12);
      clipRect(x - 4, 356, 220 * r, 60, () => text(v, x, 400, { size: fit(v, 200, 42, { wt: 900 }), wt: 900, col: C.ground }));
    });
    // the stub: a barcode and the gate
    for (let i = 0; i < 38; i++) {
      const bw = 2 + Math.floor(rnd(i * 7 + 3) * 3) * 2;
      c.fillStyle = C.ground; c.fillRect(PASS.stub + 42 + i * 4.4, 150, rnd(i * 5 + 1) > .35 ? bw * .8 : 1.5, 150);
    }
    text(EVENT.code, PASS.stub + (w - PASS.stub) / 2, 380, { size: 72, wt: 900, col: C.ground, align: 'center' });
    // the stamp lands
    const st = t - 17.0;
    if (st > 0) {
      const s = 1 + 1.4 * Math.pow(1 - clamp(st / .16), 2), a = clamp(st / .06);
      withT(790, 290, -.24, s * .72, () => SK.alpha(a * .9, () => stamp(0, 0)));
    }
  };
}
function stamp(x, y) {
  const c = g(), w = 300, h = 118, col = C.second;
  c.save(); c.translate(x, y);
  c.strokeStyle = col; c.lineWidth = 7; SK.rrPath(-w / 2, -h / 2, w, h, 16); c.stroke();
  c.lineWidth = 3; SK.rrPath(-w / 2 + 11, -h / 2 + 11, w - 22, h - 22, 10); c.stroke();
  text(COPY.stamp, 0, -8, { size: 30, wt: 800, fam: FONT.ui, ls: 4, col, align: 'center' });
  text(EVENT.city, 0, 38, { size: fit(EVENT.city, w - 40, 50, { wt: 900, ls: 6 }), wt: 900, col, align: 'center', ls: 6 });
  // ink that did not take: a few holes, from a fixed seed
  c.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 70; i++) { c.globalAlpha = .5 + rnd(i * 3) * .5; c.beginPath(); c.arc((rnd(i * 5 + 1) - .5) * w, (rnd(i * 7 + 2) - .5) * h, 1 + rnd(i * 11) * 3.2, 0, TAU); c.fill(); }
  c.restore();
}
function scene5(t) {
  const c = g();
  tiles(t, { size: 216, cols: [C.groundDk, C.secondDk, C.ground], zoom: 1.0 + (t - S5[0]) * .02, spin: .08, t0: S5[0] });
  c.fillStyle = C.dim; c.fillRect(0, 0, W, H);
  // the headline over it
  const h1 = ease(t, 15.45, 15.9, E.out);
  clipRect(0, 90, W, 120, () => text(COPY.headline, CX, 186 + (1 - h1) * 110, { size: fit(COPY.headline, W - 160, 92, { wt: 900 }), wt: 900, col: C.light, align: 'center' }));
  // the pass rises in 3D and settles, then drifts
  const up = ease(t, 15.28, 16.05, outBackSoft), drift = t - 16.05;
  SK.view3({ d: 1600 });
  const pose = {
    x: CX, y: lerp(1300, WIDE ? 548 : 552, up) + Math.sin(drift * 1.6) * 5 * (drift > 0),
    z: 0, rx: lerp(1.1, .16, up) + Math.sin(drift * 1.1) * .03 * (drift > 0), ry: lerp(-.5, -.12, up) + Math.sin(drift * .9) * .05 * (drift > 0), rz: lerp(.35, -.05, up),
    s: WIDE ? 1.14 : 1,
  };
  // the exit: it flips away on the last beat
  const out = ease(t, 18.95, 19.4, E.in);
  pose.ry += out * 1.9; pose.y -= out * 60; pose.z += out * 600;
  const P = [[-PASS.w / 2, -PASS.h / 2, 0], [PASS.w / 2, -PASS.h / 2, 0], [PASS.w / 2, PASS.h / 2, 0], [-PASS.w / 2, PASS.h / 2, 0]].map((p) => SK.pose3(p, pose));
  const Sh = P.map((p) => SK.proj3([p[0] + 30, p[1] + 60, p[2] + 60]));
  if (Sh.every(Boolean)) { c.save(); c.filter = 'blur(26px)'; poly(Sh, 'rgba(0,0,10,.5)'); c.restore(); }
  SK.face3(P, PASS.w, PASS.h, passFace(t), { key: 'pass', cull: false, shade: (1 - SK.lit3(P, { light: [-.3, -1, -.6], ambient: .8 })) });
  // the button and the address
  const b = ease(t, 16.5, 16.95, outBack);
  if (b > 0) {
    withT(CX, 880, 0, b, () => {
      const bw = 480, bh = 96;
      rrect(-bw / 2, -bh / 2 + 8, bw, bh, bh / 2, C.accentDk);
      rrect(-bw / 2, -bh / 2, bw, bh, bh / 2, C.accent);
      text(EVENT.cta, -26, 20, { size: 54, wt: 900, col: C.light, align: 'center' });
      const ax = 170 + Math.sin(t * 6) * 5; const cc = g(); cc.strokeStyle = C.light; cc.lineWidth = 9; cc.lineCap = 'round'; cc.lineJoin = 'round';
      cc.beginPath(); cc.moveTo(ax - 28, 0); cc.lineTo(ax + 24, 0); cc.moveTo(ax + 4, -20); cc.lineTo(ax + 26, 0); cc.lineTo(ax + 4, 20); cc.stroke();
    });
  }
  SK.alpha(ease(t, 16.8, 17.2), () => text(EVENT.url, CX, 990, { size: 34, wt: 700, fam: FONT.ui, ls: 2, col: C.light, align: 'center' }));
}

/* ------------------------------------------------------------------ S6: the poster */
function ticker(t, o) { // one band of the running border
  const c = g();
  c.save(); c.beginPath(); c.rect(o.x, o.y, o.w, o.h); c.clip();
  c.fillStyle = C.accent; c.fillRect(o.x, o.y, o.w, o.h);
  c.translate(o.x + o.w / 2, o.y + o.h / 2); c.rotate(o.rot);
  const len = o.rot ? o.h : o.w, str = EVENT.ticker.repeat(4), tw2 = measure(EVENT.ticker, { size: 20, wt: 800, fam: FONT.ui, ls: 3 });
  const off = ((t * 70 * (o.dir ?? 1)) % tw2 + tw2) % tw2;
  text(str, -len / 2 - off, 7, { size: 20, wt: 800, fam: FONT.ui, ls: 3, col: C.light });
  c.restore();
}
// the poster's layout: a square feed frame, or a wide YouTube one with the headline down its left
const POSTER = WIDE
  ? { x: 116, logoY: 172, headW: 1060, headMax: 210, headTop: 236, avY: 790, avR: 50, barY: 930, bar: [100, 420, 360, 320], peaks: [W - 420, H + 60, 4.9] }
  : { x: 88, logoY: 168, headW: 900, headMax: 190, headTop: 250, avY: 718, avR: 44, barY: 905, bar: [90, 292, 252, 246], peaks: [860, H + 40, 3.3] };
// where a wide frame has room, the featured five as a cluster on the right: [x, y, r] each
const CLUSTER = [[W - 450, 395, 165], [W - 200, 245, 102], [W - 190, 545, 118], [W - 655, 650, 118], [W - 395, 710, 106]]; // the first F
function scene6(t) {
  const c = g(), lt = t - S6[0], L = POSTER;
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  // the peaks, big and quiet behind everything, rising a little as the poster holds
  const pk = ease(t, 19.2, 19.95, outBackSoft), drift = E.sine(clamp((t - 20.2) / 5.8));
  if (MARK) SK.alpha(.9, () => mark(L.peaks[0] - drift * 30, L.peaks[1] - drift * 26, L.peaks[2], [pk, pk * .98], [C.groundMid, C.peaks]));
  else SK.alpha(.5 * pk, () => { c.fillStyle = C.groundMid; c.beginPath(); c.arc(L.peaks[0] - drift * 30, L.peaks[1] - drift * 26, 90 * L.peaks[2], 0, TAU); c.fill(); });
  // the border
  const B = 46, bi = ease(t, 19.25, 19.65, E.out);
  ticker(t, { x: 0, y: -B + B * bi, w: W, h: B, rot: 0 });
  ticker(t, { x: 0, y: H - B * bi, w: W, h: B, rot: 0, dir: -1 });
  ticker(t, { x: -B + B * bi, y: 0, w: B, h: H, rot: -Math.PI / 2 });
  ticker(t, { x: W - B * bi, y: 0, w: B, h: H, rot: Math.PI / 2 });
  const push = 1 + .035 * drift;
  c.save(); c.translate(CX, 560); c.scale(push, push); c.translate(-CX, -560);
  // the logo
  const lg = ease(t, 19.34, 19.79, outBack);
  mark(L.x + 40, L.logoY, .42, [lg, ease(t, 19.42, 19.87, outBack)]);
  if (MARK) wordmark(true, L.x + 118, L.logoY - 64, logoScale(413.5, 64, true), 19.44, t, { step: .035, d: .36 });
  else { const s0 = logoScale(WIDE ? 560 : 480, 130, true), im = logoImg(true); if (im) wordmark(true, L.x, L.logoY + 16 - im.height * s0, s0, 19.34, t, { d: .5 }); }
  // the headline
  const hs = Math.min(...EVENT.tagline.map((l) => fit(l, L.headW, L.headMax, { wt: 900 }))), lead = hs * .9;
  EVENT.tagline.forEach((line, i) => {
    const a = ease(t, 19.5 + i * .1, 19.98 + i * .1, outBackSoft), y = L.headTop + hs * .72 + i * lead;
    clipRect(L.x - 8, y - hs * .8, L.headW + 60, hs * .95, () => {
      const parts = line.split(' '), dy = (1 - a) * hs;
      if (i === EVENT.tagline.length - 1) { // the last word in accent
        const head = parts.length > 1 ? parts.slice(0, -1).join(' ') + ' ' : '', w0 = measure(head, { size: hs, wt: 900 });
        text(head, L.x, y + dy, { size: hs, wt: 900, col: C.light });
        text(parts[parts.length - 1], L.x + w0, y + dy, { size: hs, wt: 900, col: C.accent });
      } else text(line, L.x, y + dy, { size: hs, wt: 900, col: C.light });
    });
  });
  // the featured speakers: a cluster where there is room, else a row under the headline
  if (WIDE) {
    FEAT.forEach((sp, i) => {
      const [x0, y0, r] = CLUSTER[i], p = ease(t, 19.75 + i * .09, 20.25 + i * .09, outBack);
      if (p <= 0) return;
      const bob = Math.sin(lt * 1.3 + i * 1.7) * 6 * drift;
      withT(x0, y0 + bob, 0, p, () => {
        const cc = g(); cc.beginPath(); cc.arc(0, 0, r + 9, 0, TAU); cc.fillStyle = C.ground; cc.fill();
        speakerCircle(sp, i, 0, 0, r, 1, t);
      });
    });
    SK.alpha(ease(t, 20.3, 20.65), () => text(COPY.meet + '  →', L.x, L.avY + 10, { size: 30, wt: 800, fam: FONT.ui, ls: 3, col: C.secondLt }));
  }
  const step = L.avR * 1.6;
  if (!WIDE) FEAT.forEach((sp, i) => {
    const p = ease(t, 20.0 + i * .06, 20.45 + i * .06, outBack), x0 = L.x + L.avR + 2 + i * step;
    if (p <= 0) return;
    withT(x0, L.avY, 0, p, () => {
      const cc = g(); cc.beginPath(); cc.arc(0, 0, L.avR + 6, 0, TAU); cc.fillStyle = C.ground; cc.fill();
      speakerCircle(sp, i, 0, 0, L.avR, 1, t);
    });
  });
  if (!WIDE) SK.alpha(ease(t, 20.3, 20.65), () => text(COPY.meet, L.x + L.avR * 2 + (F - 1) * step + 34, L.avY + 10, { size: 26, wt: 800, fam: FONT.ui, ls: 3, col: C.light }));
  // the information bar
  const cells = [
    { fill: C.second, draw: (x, y, w) => { const cc = g(); cc.strokeStyle = C.ground; cc.lineWidth = 9; cc.lineCap = 'round'; cc.lineJoin = 'round'; const ax = x + w / 2 + Math.max(0, Math.sin(lt * 5)) * 6; cc.beginPath(); cc.moveTo(ax - 22, y); cc.lineTo(ax + 20, y); cc.moveTo(ax + 2, y - 18); cc.lineTo(ax + 22, y); cc.lineTo(ax + 2, y + 18); cc.stroke(); } },
    { fill: C.groundLt, label: EVENT.datesLong },
    { fill: C.groundLt, label: `${EVENT.venue}, ${EVENT.city}` },
    { fill: C.accent, label: EVENT.url },
  ];
  let x = L.x; const y = L.barY, bh = WIDE ? 100 : 90, fs = WIDE ? 30 : 24;
  cells.forEach((cl, i) => {
    const w = L.bar[i], a = ease(t, 19.85 + i * .08, 20.2 + i * .08, E.out);
    clipRect(x, y - bh / 2, w * a, bh, () => {
      rrect(x, y - bh / 2, w, bh, 8, cl.fill);
      if (cl.draw) cl.draw(x, y, w);
      if (cl.label) text(cl.label, x + w / 2, y + fs * .38, { size: fit(cl.label, w - 40, fs, { wt: 800, fam: FONT.ui, ls: 1 }), wt: 800, fam: FONT.ui, ls: 1, col: C.light, align: 'center' });
    });
    x += w + 8;
  });
  c.restore();
}

/* ------------------------------------------------------------------ the transitions and the film */
function whip(t, t0, t1, a, b, dir = -1) { // a whip pan from scene a to scene b between t0 and t1
  const u = clamp((t - t0) / (t1 - t0));
  const e = E.inOut(u), smear = Math.sin(u * Math.PI) * 180;
  if (u < 1) SK.fx(() => a(t), { key: 'wa', dx: dir * e * W, smear, angle: 0 });
  if (u > 0) SK.fx(() => b(t), { key: 'wb', dx: dir * (e - 1) * W, smear, angle: 0 });
}
function planeA(t) { // S2's plane: takes off in front of the board and comes at the camera
  if (t < FLIGHT_A[0][0]) return;
  SK.view3({ d: 1400 }); trail(FLIGHT_A, t, .7, { col: C.light }); drawPlane(flyPose(FLIGHT_A, t), 1.3);
}
function draw(t) {
  if (t < S1[1] - .02) scene1(t);
  if (t >= S1[1] - .02 && t < 6.2) { scene2(Math.max(t, S2[0])); planeA(t); }
  if (t >= 6.2 && t < 6.62) whip(t, 6.2, 6.62, (tt) => { scene2(tt); planeA(tt); }, (tt) => scene4(tt), -1);
  if (t >= 6.62 && t < S4[1]) scene4(t);
  if (t >= S4[1] && t < 15.6) {
    // the plane's accent has filled the frame; the pass comes up out of it
    const u = clamp((t - S4[1]) / .3);
    scene5(t);
    SK.alpha(1 - E.out(u), () => { g().fillStyle = C.accent; g().fillRect(0, 0, W, H); });
  }
  if (t >= 15.6 && t < IRIS[0]) scene5(t);
  if (t >= IRIS[0]) { // the poster opens out of the button, as if it had been pressed
    const u = clamp((t - IRIS[0]) / (IRIS[1] - IRIS[0])), r = Math.hypot(CX, 880) * 1.05 * E.in(u) + 40 * u, c = g();
    if (u < 1) scene5(t);
    c.save(); c.beginPath(); c.arc(CX, 880, r, 0, TAU); c.clip(); scene6(t); c.restore();
    if (u < 1) { c.save(); c.lineWidth = 26 * (1 - u) + 6; c.strokeStyle = C.accent; c.beginPath(); c.arc(CX, 880, r, 0, TAU); c.stroke(); c.restore(); }
  }
}

/* ------------------------------------------------------------------ the sound
   Worked out from the clock above and from the content, so a new city brings its own flap clicks and a
   new line-up its own pops: `sketch-render.py --sound-data` writes score.json and sfx.json from these.
   The music is a 120 bpm groove in F minor from a chord chart: four-on-the-floor from the first frame,
   a roll into the dive, the groove dropping out for the take-off and landing again with the speakers,
   a synth-brass stab on every turn, a roll into the pass and into the poster, a last chord at LAST. */
const BPM = 120, beat = (t) => t * BPM / 60;
const gf = (x) => String(+x.toPrecision(6)); // a number as Python's %g writes it
function scoreData() {
  const CHART = [ // per bar: bass root, its octave, the stab chord, the pad chord
    ['F1', 'F2', 'Ab3+C4+F4', 'F3+Ab3+C4+Eb4'], // Fm7
    ['Db2', 'Db3', 'Ab3+Db4+F4', 'Db3+F3+Ab3+C4'], // Dbmaj7
    ['Ab1', 'Ab2', 'Ab3+C4+Eb4', 'Ab3+C4+Eb4+G4'], // Abmaj7
    ['Eb2', 'Eb3', 'G3+Bb3+Eb4', 'Eb3+G3+Bb3+Db4'], // Eb7
  ];
  const BARS = Math.round(SK._film.duration / (240 / BPM)); // the last bar is the ring-out
  const HITS = [LAND, ...TURN, PASS_IN, IRIS[1]].map(beat); // the stab plays the bar's chord on each
  const FINAL = beat(LAST);
  // drum bars, 16 steps each. x hit, X accent, o soft, . rest
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', openhat: '..x...x...x...x.', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
  const FULL = { ...GROOVE, rim: '...o..o....o..o.' };
  const DRUMS = [
    { ...GROOVE, hat: 'oooooooooooooooo' }, // 0: the logo, straight in
    { snare: 'ooxxxxX.........', kick: '......X.x...x...', clap: '............x...', openhat: '..........x...x.', hat: '........o.o.o.o.' }, // 1: a roll into the dive, the drop
    GROOVE, // 2: the board
    { kick: '....X...x...x...', clap: '............x...', snare: 'oooo............', openhat: '......x...x...x.', hat: '....o.o.o.o.o.o.', shaker: '.....o.o.o.o.o.o' }, // 3: the take-off; the speakers land
    FULL, FULL, FULL, // 4-6: the carousel
    { ...FULL, kick: 'x...x.......X...', snare: '........oxxX....', clap: '....x...........' }, // 7: the plane leaves, a roll into the pass
    GROOVE, // 8: the pass
    { ...GROOVE, snare: '........ooxxX...', kick: 'x...x.......X...' }, // 9: into the poster
    FULL, // 10: the poster
    { ...FULL, snare: '............oxxX' }, // 11: a fill into the last chord
    { kick: 'X...............', openhat: 'x...............' }, // 12: the button
  ];
  // the synthesised hats and shaker are high-passed white noise: at full level the mix measured 7-20 dB
  // brighter than a reference track above 1.6 kHz and thin below 630 Hz, so the cymbals sit well back
  const KIT_GAINS = { kick: 1.15, snare: .42, clap: .42, hat: .26, openhat: .16, shaker: .2, rim: .45 };
  const QUIET_BASS = { 1: [0, 1.5], 3: [0, 2], 7: [2.5, 3.5] }; // bar -> beats with no bass or stabs
  const bass = [], sub = [], pad = [], keys = [], brass = [];
  for (let bar = 0; bar < BARS - 1; bar++) {
    const [root, octv, stab, chord] = CHART[bar % 4], b0 = bar * 4, quiet = QUIET_BASS[bar];
    for (let k = 0; k < 8; k++) { // eighths: the root, then its octave on the off-beats
      const b = k * .5;
      if (quiet && quiet[0] <= b && b < quiet[1]) continue;
      bass.push(`${gf(b0 + b)} ${k % 2 ? octv : root} .42 ${(k % 2 ? .52 : .62).toFixed(2)}`);
      if (k % 2) sub.push(`${gf(b0 + b - .02)} ${root} .4 .8`); // the sub fills the off-beats, between the kicks
    }
    for (const k of [.5, 1.5, 2.5, 3.5]) { // house stabs on the and of every beat
      if (quiet && quiet[0] <= k && k < quiet[1]) continue;
      keys.push(`${gf(b0 + k)} ${stab} .3 ${(k === 1.5 || k === 3.5 ? .34 : .26).toFixed(2)}`);
    }
    if (bar >= 3) pad.push(`${gf(b0)} ${chord} 4 .3`); // the pad joins with the speakers
  }
  for (const b of HITS) brass.push(`${gf(b)} ${CHART[Math.floor(b / 4) % 4][2]} .9 .62`);
  bass.push(`${gf(FINAL)} F1 4 .7`); sub.push(`${gf(FINAL)} F1 4 .9`);
  pad.push(`${gf(FINAL)} F3+Ab3+C4+F4+C5 4 .5`); keys.push(`${gf(FINAL)} F3+Ab3+C4+F4 3 .5`);
  brass.push(`${gf(FINAL)} F4+Ab4+C5 2 .7`);
  // the wordmark's letters: a run up the chord
  const sparkle = 'F5 Ab5 C6 Eb6 F6 Ab6 C7 Eb7 F7'.split(' ').map((n, i) => `${(1.04 + i * .09).toFixed(3)} ${n} .6 ${(.3 + i * .03).toFixed(2)}`).join('; ');
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
      synth_bass_1: { g: .62, pan: 0, send: .04, rel: .12 },
      sub_bass: { g: .5, pan: 0, send: 0, rel: .05 },
      electric_piano_1: { g: .26, pan: -.22, send: .3, rel: .25 },
      pad_3_polysynth: { g: .17, pan: 0, send: .5, rel: .8, soft_attack: true },
      synth_brass_1: { g: .22, pan: .12, send: .35, rel: .35 },
      glockenspiel: { g: .16, pan: .3, send: .45, rel: 1.0 },
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
    cues.push(c);
    return c;
  };
  const many = new Map(); // one cue holds every time a sound repeats with the same loudness and pan
  const again = (key, t, fx, db, args, pan) => {
    let c = many.get(key);
    if (!c) { c = add(t, fx, db, args, { pan }); c.times = []; many.set(key, c); }
    c.times.push(r(t, 3));
  };
  const impact = (t, db = -12) => { add(t, 'boom', db, { sec: 1.1 }); add(t, 'crash', db - 14, { sec: 1.8 }, { send: .3 }); };

  // 1. the logo: the card pops, the symbol rises, the letters click in, the line types
  add(0, 'boom', -14, { sec: .9 });
  add(.02, 'swoosh_soft', -22, { sec: .45 });
  add(.1, 'pop', -22, { f0: 520, f1: 180, sec: .09 });
  add(.2, 'pop', -21, { f0: 700, f1: 240, sec: .09 });
  const nLetters = LETTERS ? LETTERS.length : 9;
  for (let i = 0; i < nLetters; i++) add(.56 + i * .045, 'tick', -28 + (i % 3), {}, { pan: -.4 + i * .1 });
  add(1.1, 'keys', -31, { sec: .5, rate: 18 });
  add(2.2, 'whoosh', -14, { sec: .6, f0: 250, f1: 5200, peak: .9, curve: 1.6 }); // the dive
  impact(2.75, -13);
  add(2.64, 'swoosh_soft', -20, { sec: .45 }, { pan: .4 }); // the board swings in

  // 2. the board: every flap that falls, as the film's own flapCell draws it
  ROWS.forEach((row, ri) => {
    for (let i = 0; i < 10; i++) {
      const ch = (row.str[i] ?? ' ').toUpperCase(); if (ch === ' ') continue;
      const nf = 5 + Math.floor(rnd(ri * 31 + i * 7 + 3) * 6), t0 = row.t0 + i * .045, pan = -.5 + i * .1;
      for (let k = 0; k < nf; k++) {
        const db = -20 - (k % 3) - (k < nf - 1 ? 4 : 0);
        again(`click ${i} ${db}`, t0 + (k + .9) * FLIP, 'click', db, { sec: .008, lo: 1500, hi: 6500 }, pan);
      }
      again(`tick ${i}`, t0 + nf * FLIP, 'tick', -22, {}, pan); // the last one, settling
    }
  });
  add(4.32, 'sample', -14, { inst: 'vibraphone', notes: ['G5', 'E5'], every: .28, sec: 1.4 }, { send: .35 }); // BOARDING lights up
  add(5.02, 'whoosh', -19, { sec: .8, f0: 400, f1: 2400, peak: .5 }, { pan: -.5 }); // the plane takes off
  add(5.7, 'whoosh', -17, { sec: .7, f0: 300, f1: 3000, peak: .6 }, { pan: .3 }); // ... and comes at the camera

  // 3. the whip into the speakers; the circles pop out from the front
  add(6.12, 'whoosh', -12, { sec: .55, f0: 200, f1: 4500, peak: .55, curve: 1.2 });
  impact(LAND, -13);
  const N = SPEAKERS.length;
  for (let i = 0; i < N; i++) {
    const d = Math.abs(Math.atan2(Math.sin(i / N * TAU), Math.cos(i / N * TAU)));
    add(RING_IN + d * .12 + .12, 'pop', -30 + (i === 0 ? 4 : 0), { f0: 900 + (i % 5) * 120, f1: 300, sec: .07 }, { pan: Math.sin(i / N * TAU) * .7 });
  }
  add(6.55, 'swoosh_soft', -22, { sec: .4 }); // the name block slides up
  add(7.0, 'thunk', -20, { sec: .3 });
  add(7.05, 'zip', -24, { sec: .3, f0: 500, f1: 2600 }); // the first name wipes on
  add(7.32, 'blip', -28, { f: 1320, sec: .08 });
  for (const b of TURN) { // the ring and the block turn together
    add(b - .24, 'whoosh', -14, { sec: .55, f0: 500, f1: 3400, peak: .45 });
    add(b + .28, 'thunk', -13, { sec: .28 });
    add(b + .1, 'zip', -20, { sec: .28, f0: 600, f1: 2800 });
  }
  add(14.55, 'whoosh', -13, { sec: .8, f0: 250, f1: 4000, peak: .85, curve: 1.5 }); // the plane leaves, at the camera
  impact(S4[1], -12);

  // 4. the boarding pass
  add(15.3, 'swoosh_soft', -19, { sec: .6 });
  add(15.95, 'thunk', -22, { sec: .25 });
  add(15.78, 'pop', -24, { f0: 620, f1: 200, sec: .08 });
  add(15.92, 'pop', -24, { f0: 820, f1: 260, sec: .08 });
  add(15.86, 'zip', -27, { sec: .22, f0: 900, f1: 3000 }); // the little plane between them
  for (let i = 0; i < 3; i++) add(16.12 + i * .12, 'keys', -30, { sec: .22, rate: 22 });
  add(16.5, 'pop', -18, { f0: 500, f1: 160, sec: .12 }); // the button
  add(16.52, 'blip', -26, { f: 988, sec: .1 });
  add(17.0, 'thunk', -12, { sec: .4 }); // the stamp
  add(17.0, 'click', -20, { sec: .01, lo: 900, hi: 3000 });
  add(18.92, 'whoosh', -18, { sec: .5, f0: 300, f1: 2600, peak: .7 }); // the pass flips away

  // 5. the poster opens out of the button
  add(IRIS[0], 'whoosh', -15, { sec: IRIS[1] - IRIS[0] + .1, f0: 300, f1: 4200, peak: .9, curve: 1.4 });
  impact(IRIS[1], -13);
  add(19.3, 'swoosh_soft', -24, { sec: .5 }); // the border runs in
  add(19.38, 'pop', -23, { f0: 520, f1: 180, sec: .09 });
  for (let i = 0; i < 3; i++) add(19.62 + i * .1, 'thunk', -24 + i, { sec: .2 }); // the headline's lines
  for (let i = 0; i < 4; i++) add(19.9 + i * .08, 'tick', -27, {}, { pan: -.5 + i * .33 }); // the information bar
  for (let i = 0; i < F; i++) add(20.1 + i * .06, 'pop', -28, { f0: 800 + i * 90, f1: 300, sec: .07 }, { pan: -.6 + i * .1 }); // the faces
  add(LAST, 'crash', -21, { sec: 2.2 }, { send: .4 }); // the last chord
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
