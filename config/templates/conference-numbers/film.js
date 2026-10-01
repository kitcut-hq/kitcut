// For: an event's organisers and the people who follow it -- a conference told in its own numbers
/* The conference in numbers: why come, told in the event's own numbers -- before the event as hype,
   after it as a recap. 88 s, 1920 x 1080, music only. This film is a template: every word, number,
   colour, logo and place is in content.json (SK.DATA.content) and nothing of the event is in the
   code, so another conference is another content.json and its logo.

   The story, on a 120 bpm clock (a bar is 2 s):
     0-8    the logo assembles out of digits, which turn to pixels and then to the logo itself;
            the headline rolls in under it, then the tagline
     8-12   a calendar page swings down and marks the event's days
     12-16  a pin drops on a dot map of the world, on the venue
     16-64  one chapter per number (3 to 7 share these 48 s): it rolls up like an odometer over a
            picture of what it counts, chosen by its kind -- a crowd of dots (people), arcs flying
            in to the host city (countries), a city of blocks (companies), a network (investors),
            a wall of tiles (speakers), a clock (sessions), a timeline (years), flashes (media) or
            the number alone, giant (type)
     64-76  the topics as a wall of words; a quote, when there is one, takes the last 6 s
     76-88  the poster: dates, city, venue, three of the numbers, the button and the address
   The clock below is the one home of its timing: the score and every sound cue are worked out from
   it and from the content (SK.film({sound}) at the bottom), so `sketch-render.py --sound-data`
   writes a score.json and sfx.json that fit whatever the content is. The length never changes. */
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, TAU = SK.TAU, rnd = SK.rnd;
const CX = W / 2, CY = H / 2;
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
  const light = p.light ?? '#F4F1EC', paper = p.paper ?? '#F3F0EA', L = (hex) => hslOf(hex)[2];
  // light type sits on the ground everywhere: a ground too light for it is darkened until it reads
  let ground = p.ground ?? '#101828';
  while (contrast(ground, light) < 7 && L(ground) > .04) ground = withL(ground, L(ground) - .02);
  const g0 = Math.max(.07, L(ground)), a = p.accent ?? '#E5484D', s2 = p.second ?? withL(a, .45), a0 = L(a), s0 = L(s2);
  const d = {
    light, paper, card: '#FFFFFF',
    groundDk: withL(ground, g0 * .62), groundMid: withL(ground, Math.min(.42, g0 * 1.6)), groundLt: withL(ground, Math.min(.5, g0 * 2.3)),
    accentDk: withL(a, a0 * .74), accentLt: withL(a, Math.min(.86, a0 * 1.45)),
    secondDk: withL(s2, s0 * .74), secondLt: withL(s2, Math.min(.86, s0 * 1.6)),
    soft: withL(ground, .74, .3), inkSoft: withL(ground, .45, .5),
  };
  const out = { ...d, ...p, ground, accent: a, second: s2 };
  // a colour that reads as type on each ground, and the type that reads on each colour
  out.accentOnGround = contrast(a, ground) >= 3 ? a : out.accentLt;
  out.secondOnGround = contrast(s2, ground) >= 3 ? s2 : out.secondLt;
  out.accentOnPaper = contrast(a, paper) >= 3 ? a : contrast(out.accentDk, paper) >= 3 ? out.accentDk : ground;
  out.inkOnAccent = contrast(light, a) >= contrast(ground, a) ? light : ground;
  out.inkOnSecond = contrast(light, s2) >= contrast(ground, s2) ? light : ground;
  out.shadow = rgbOf(withL(ground, g0 * .3)).join(',');
  out.groundRGB = rgbOf(ground).join(',');
  out.lightRGB = rgbOf(light).join(',');
  return out;
}
const C = palette(D.palette || {});
SK.setStyle('clean', { grain: .45, vignette: .28, handheld: 0, vignetteRGB: C.shadow });
Object.assign(SK.C, { paper: C.ground, text: C.light, textSoft: C.soft, accent: C.accent, accentText: C.accentOnGround, ink: C.ground });
const FONT = { cond: '"Sofia Sans Condensed"', wide: '"Sofia Sans"', mono: '"IBM Plex Mono"', ...(D.fonts || {}) };

/* ------------------------------------------------------------------ the words */
const EV = D.event || {};
const fillIn = (str) => String(str ?? '').replace(/\{(\w+)\}/g, (_, k) => EV[k] ?? '');
const COPY = {};
for (const [k, v] of Object.entries(D.copy || {})) COPY[k] = Array.isArray(v) ? v.map(fillIn) : fillIn(v);
const WEEKDAYS = Array.isArray(COPY.weekdays) && COPY.weekdays.length === 7 ? COPY.weekdays : null;

/* the numbers: 3 to 7 (more are left out), each a picture by its kind. A kind the film does not know
   is drawn as giant type. */
const KIND = {
  people: 'people', attendees: 'people', visitors: 'people', participants: 'people', delegates: 'people', guests: 'people', members: 'people', community: 'people',
  countries: 'countries', nations: 'countries', cities: 'countries', world: 'countries',
  companies: 'companies', startups: 'companies', exhibitors: 'companies', partners: 'companies', brands: 'companies', booths: 'companies', sponsors: 'companies',
  network: 'network', investors: 'network', funds: 'network', meetings: 'network', connections: 'network', deals: 'network', matches: 'network',
  speakers: 'speakers', lineup: 'speakers', hosts: 'speakers', mentors: 'speakers', artists: 'speakers',
  sessions: 'sessions', talks: 'sessions', hours: 'sessions', stages: 'sessions', workshops: 'sessions', tracks: 'sessions', meetups: 'sessions', days: 'sessions',
  years: 'years', editions: 'years', timeline: 'years', anniversary: 'years',
  media: 'media', press: 'media', journalists: 'media', photos: 'media', views: 'media', reach: 'media',
  type: 'type', other: 'type',
};
let STATS = (D.stats || []).filter((s) => s && /\d/.test(String(s.value ?? ''))).slice(0, 7).map((s, i) => ({
  ...s, i, value: String(s.value), prefix: String(s.prefix ?? ''), suffix: String(s.suffix ?? ''), label: String(s.label ?? ''),
  note: String(s.note ?? ''), kind: KIND[String(s.kind ?? '').toLowerCase()] ?? 'type',
}));
if (!STATS.length) STATS = [{ i: 0, value: String(EV.year ?? '1'), prefix: '', suffix: '', label: String(EV.name ?? ''), note: '', kind: 'type' }];
const N = STATS.length;
const TOPICS = (D.topics || []).map((x) => String(x).trim()).filter(Boolean);
const QUOTE = D.quote && String(D.quote.text ?? '').trim() ? { text: String(D.quote.text).trim(), by: String(D.quote.by ?? '') } : null;
const POSTER_STATS = (STATS.some((s) => s.poster) ? STATS.filter((s) => s.poster) : STATS).slice(0, 3);
const LAT = Number.isFinite(+EV.lat) ? +EV.lat : 0, LON = Number.isFinite(+EV.lon) ? +EV.lon : 0, HAS_GEO = Number.isFinite(+EV.lat) && EV.lat !== undefined && EV.lat !== '';

/* ------------------------------------------------------------------ the clock (120 bpm: a beat is .5 s, a bar 2 s) */
const BPM = 120, BEAT = 60 / BPM, BAR = 4 * BEAT;
const T_WHEN = 8, T_WHERE = 12, T_NUMS = 16, T_WORDS = 64, T_POSTER = 76, DUR = 88, LAST = 84;
const LOCK = 2.0, HEAD_T = 4.0, TAG_T = 5.0, PIN_T = 13.0;
// the numbers share 48 s in whole seconds (half bars), so every chapter starts on a beat
const CHAPTERS = STATS.map((s, i) => {
  const a = T_NUMS + Math.round(i * 48 / N), b = T_NUMS + Math.round((i + 1) * 48 / N);
  const side = s.kind === 'type' ? 'center' : i % 2 ? 'right' : 'left'; // where its number sits
  return { s, i, a, b, side, focus: [side === 'left' ? W * .70 : side === 'right' ? W * .30 : CX, H * .52], t0: a + .3 };
});
const T_QUOTE = QUOTE ? (TOPICS.length ? 70 : T_WORDS) : null;

/* ------------------------------------------------------------------ small helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (u) => { const c3 = k + 1; return 1 + c3 * Math.pow(u - 1, 3) + k * Math.pow(u - 1, 2); };
const outBack = back(1.6), outSoft = back(.8);
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
/** str broken into lines no wider than width at this size (a word too long for a line keeps a line of its own) */
function wrap(str, width, o) {
  const words = String(str).split(/\s+/).filter(Boolean), lines = [];
  for (const w of words) {
    const tryL = lines.length ? lines[lines.length - 1] + ' ' + w : w;
    if (lines.length && measure(tryL, o) <= width) lines[lines.length - 1] = tryL; else lines.push(w);
  }
  return lines.length ? lines : [''];
}
/** the largest size up to max at which str fits width in at most n lines: {size, lines} */
function fitWrap(str, width, max, n, o = {}) {
  let size = max;
  for (let k = 0; k < 40; k++) {
    const lines = wrap(str, width, { ...o, size });
    if (lines.length <= n && lines.every((l) => measure(l, { ...o, size }) <= width)) return { size, lines };
    size *= .95;
  }
  const lines = wrap(str, width, { ...o, size });
  return { size: Math.min(size, ...lines.map((l) => fit(l, width, size, o))), lines };
}
function clipRect(x, y, w, h, fn) { const c = g(); c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); fn(); c.restore(); }
function rrect(x, y, w, h, r, fill) { const c = g(); SK.rrPath(x, y, w, h, Math.min(r, w / 2, h / 2)); c.fillStyle = fill; c.fill(); }
function disc(x, y, r, fill) { if (r <= 0) return; const c = g(); c.beginPath(); c.arc(x, y, r, 0, TAU); c.fillStyle = fill; c.fill(); }
function ring(x, y, r, w, col) { if (r <= 0) return; const c = g(); c.beginPath(); c.arc(x, y, r, 0, TAU); c.lineWidth = w; c.strokeStyle = col; c.stroke(); }
const rgba = (hex, a) => `rgba(${rgbOf(hex).join(',')},${a})`;
const pad2 = (n) => String(n).padStart(2, '0');
/** a scrim: the ground fading in from one side, so type reads over a picture */
function scrim(side, a = .92, reach = .55) {
  if (side === 'center') return;
  const c = g(), x0 = side === 'left' ? 0 : W, x1 = side === 'left' ? W * reach : W * (1 - reach);
  const gr = c.createLinearGradient(x0, 0, x1, 0);
  gr.addColorStop(0, `rgba(${C.groundRGB},${a})`); gr.addColorStop(.55, `rgba(${C.groundRGB},${a * .75})`); gr.addColorStop(1, `rgba(${C.groundRGB},0)`);
  c.fillStyle = gr; c.fillRect(0, 0, W, H);
}

/** the ground of a data page: a faint grid of dots, drifting a little */
function groundGrid(t, a = 1) {
  const c = g(), st = 48, ox = (t * 6) % st;
  c.save(); c.fillStyle = rgba(C.light, .05 * a);
  for (let y = st / 2; y < H; y += st) for (let x = st / 2 - ox; x < W + st; x += st) c.fillRect(x - 1.5, y - 1.5, 3, 3);
  c.restore();
}

/* ------------------------------------------------------------------ the logo
   content.logo: image (for a light ground) and light (for a dark one). Without either, the event's
   name set in the film's type stands in -- in the opening's mosaic too. */
const LG = D.logo || {};
const NAMES = new Map();
function nameImage(onDark) { // the event's name as a picture, once its face has loaded
  const key = onDark ? 'd' : 'l'; if (NAMES.has(key)) return NAMES.get(key);
  const f = font(220, 900, FONT.cond);
  const cv = document.createElement('canvas'), c2 = cv.getContext('2d'); c2.font = f;
  const w = Math.ceil(c2.measureText(String(EV.name ?? '')).width) + 24; cv.width = Math.max(2, w); cv.height = 250;
  c2.font = f; c2.fillStyle = onDark ? C.light : C.ground; c2.fillText(String(EV.name ?? ''), 12, 205);
  if (document.fonts && document.fonts.check(f)) NAMES.set(key, cv);
  return cv;
}
function logoSrc(onDark) {
  const k = onDark ? (LG.light || LG.image) : (LG.image || LG.light);
  return (k && SK.IMG[k]) || nameImage(onDark);
}
/** the logo fitted into a bw x bh box: align 'left' (x is its left) or 'center'; y is its middle. Returns its width. */
function drawLogo(onDark, x, y, bw, bh, align = 'left', reveal = 1) {
  const im = logoSrc(onDark); if (!im || reveal <= 0) return 0;
  const s = Math.min(bw / im.width, bh / im.height), w = im.width * s, h = im.height * s, x0 = align === 'center' ? x - w / 2 : x;
  const c = g(); c.save(); c.beginPath(); c.rect(x0 - 4, y - h / 2 - 4, (w + 8) * reveal, h + 8); c.clip();
  c.drawImage(im, x0, y - h / 2, w, h); c.restore();
  return w;
}

/* ------------------------------------------------------------------ the odometer
   str set at x, y (alphabetic baseline) with each digit rolling up into place on its own wheel: the
   k-th digit stops at t0 + d + k * step, the later wheels spinning more turns. Other characters
   (separators, a suffix, words) rise in one after another. o: size, wt, fam, align, colOf(ch, i) */
function odoStops(str, t0, o = {}) { // when each digit's wheel stops (the sound reads these)
  const d = o.d ?? .85, step = o.step ?? .07, out = []; let k = 0;
  for (const ch of str) if (/\d/.test(ch)) { out.push(t0 + k * step + d); k++; }
  return out;
}
function odometer(str, x, y, t0, t, o = {}) {
  const c = g(), size = o.size ?? 200, d = o.d ?? .85, step = o.step ?? .07;
  if (t < t0) return 0;
  c.save(); c.font = font(size, o.wt ?? 900, o.fam ?? FONT.cond); c.letterSpacing = '0px'; c.textAlign = 'left'; c.textBaseline = 'alphabetic';
  const chars = [...str], widths = chars.map((ch) => c.measureText(ch).width), total = widths.reduce((s, w) => s + w, 0);
  let cx = o.align === 'center' ? x - total / 2 : o.align === 'right' ? x - total : x;
  const nd = chars.filter((ch) => /\d/.test(ch)).length, top = y - size * .86, hh = size * 1.02, lh = size * .9;
  const base = c.globalAlpha * (o.alpha ?? 1);
  let k = 0;
  chars.forEach((ch, idx) => {
    const w = widths[idx]; c.fillStyle = o.colOf ? o.colOf(ch, idx) : (o.col ?? C.light);
    if (/\d/.test(ch)) {
      const u = clamp((t - t0 - k * step) / d), spins = 1 + Math.min(4, nd - k);
      const pos = +ch - 10 * spins * (1 - E.out(u)), n0 = Math.floor(pos), f = pos - n0;
      const dg = (n) => String(((n % 10) + 10) % 10), speed = 30 * spins * Math.pow(1 - u, 2) / d;
      c.globalAlpha = base * clamp((t - t0 - k * step) / .1);
      if (u >= 1) c.fillText(ch, cx, y);
      else {
        c.save(); c.beginPath(); c.rect(cx - size * .1, top, w + size * .2, hh); c.clip();
        const dy = -f * lh;
        c.fillText(dg(n0), cx, y + dy); c.fillText(dg(n0 + 1), cx, y + dy + lh);
        if (speed > 10) { // a little motion blur on a fast wheel
          c.globalAlpha *= .3; c.fillText(dg(n0), cx, y + dy + lh * .3); c.fillText(dg(n0 + 1), cx, y + dy + lh * .7);
        }
        c.restore();
      }
      k++;
    } else {
      const u = clamp((t - t0 - .12 - idx * .028) / .3);
      c.globalAlpha = base * u;
      if (u > 0) { c.save(); c.beginPath(); c.rect(cx - size * .1, top, w + size * .2, hh); c.clip(); c.fillText(ch, cx, y + (1 - E.out(u)) * size * .6); c.restore(); }
    }
    cx += w;
  });
  c.restore();
  return total;
}

/* ------------------------------------------------------------------ the number block: number, rule, label, note */
function blockLayout(s, w, o = {}) {
  const str = s.prefix + s.value + s.suffix;
  const size = Math.round(fit(str, w, o.max ?? 300, { wt: 900 }));
  const lab = fitWrap(s.label, w, o.labMax ?? Math.min(96, size * .42), 2, { wt: 900, ls: 2 });
  const note = s.note ? fitWrap(s.note, w, o.noteMax ?? 28, 3, { wt: 700, fam: FONT.mono, ls: 1 }) : null;
  const capH = size * .72, labH = lab.lines.length * lab.size * .96, noteH = note ? 30 + note.lines.length * note.size * 1.45 : 0;
  return { str, size, lab, note, capH, h: capH + size * .2 + 44 + labH + noteH };
}
function numberBlock(s, x, yMid, w, t0, t, o = {}) {
  const L = blockLayout(s, w, o), top = yMid - L.h / 2, base = top + L.capH, al = o.align ?? 'left';
  const ax = al === 'center' ? x + w / 2 : x, preN = [...s.prefix].length, valN = [...s.value].length;
  odometer(L.str, ax, base, t0, t, { size: L.size, align: al, colOf: (ch, i) => (i < preN || i >= preN + valN ? C.accentOnGround : C.light) });
  // the rule: an accent bar that draws out under the number
  const r = ease(t, t0 + .45, t0 + .9, E.out), rw = 120 * r;
  if (rw > 0) rrect(al === 'center' ? ax - rw / 2 : ax, base + L.size * .2, rw, 10, 5, C.accent);
  // the label, a line at a time out of a mask
  let y = base + L.size * .2 + 44 + L.lab.size * .74;
  L.lab.lines.forEach((ln, i) => {
    const u = ease(t, t0 + .55 + i * .08, t0 + .95 + i * .08, E.out);
    if (u > 0) clipRect(0, y - L.lab.size * .82, W, L.lab.size * .98, () => text(ln, ax, y + (1 - u) * L.lab.size, { size: L.lab.size, wt: 900, ls: 2, align: al, col: C.light }));
    y += L.lab.size * .96;
  });
  // the note, typed
  if (L.note) {
    y += 30 - L.lab.size * .2 + L.note.size * .2;
    let shown = Math.floor((t - t0 - 1.05) * 40);
    L.note.lines.forEach((ln) => {
      const n = clamp(shown, 0, ln.length); shown -= ln.length;
      if (n > 0) text(ln.slice(0, n), ax, y + L.note.size, { size: L.note.size, wt: 700, fam: FONT.mono, ls: 1, align: al, col: C.soft });
      y += L.note.size * 1.45;
    });
  }
  return { top, h: L.h, size: L.size };
}

/* ------------------------------------------------------------------ the dot map
   The world's land at 1.5 degrees (Natural Earth 1:110m, rasterised), 240 x 96 cells from 84 N to
   60 S, as a base64 bitset. Places come in as [lat, lon]. */
const MAP = { step: 1.5, lat0: 84, cols: 240, rows: 96, bits: 'AAAAAAAAAAA//AA//4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB///////74AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP//3/////gAAD/AAYAAAAfgAAAAAAAAAAAAAAAEO3/9/////+AAAfwAAAAAAAH8AAAAAAAAAAAAAAHkAcfwf////+AAAHAAAAAAAAAeAAAAAAAAAAAAAAE/zv/gAf///+AAAAAAAAP4AA//8AAfAAAAAAAAAAfMAP/gAD///+AAAAAAAA4AAH//4AACAAAAAAAAAA//z+/4AB///4AAAAAAABwDh/////wHwAAAgAGAAAd/58//gB///4AAAADgABwH/////////AABAB//4/8/8+P/4B///wAAAA/8AADH//////////8+wH//////8/vH8A///AAAAD//5n//v////////////D/////////B/g//wAQAAH//////////////////fP////////+P/Af8AP4AAf7+f///////////////AA////////vB+Af4AHgAA//////////////////+AH///////+CPMAPwAAAAH/P////////////////+AH///////4APwADwAAAAH/P//////////////z/gAA/QH////4APzAAAAAAAH/D//////////////jgAAAPAA////+AP/gAAAAAOAeH////////////8APgAAA4AAf////wP/wAAAAAOB+P////////////wAPgAABAAAP////+f/8AAAAA3B5/////////////gAfAAAAAAAT/////f/+AAAAA3n///////////////AOAAAAAAAB///////+AAAAAnv///////////////AIAAAAAAAB///////2AAAAAO///////////////9AAAAAAAAAA//////+HgAAAAH////////////////AAAAAAAAAAf/////+HgAAAAD///////////////7AAAAAAAAAAf//////wAAAAAB///zfx/////////wAAAAAAAAAAf/////7AAAAAAB/7/ifj/////////jgAAAAAAAAAf/////gAAAAAA/wd/gHx////////+HAAAAAAAAAAf/////gAAAAAA/xvf//4////////4EAAAAAAAAAAf////+AAAAAAA/Bjd//5///////3wGAAAAAAAAAAP////8AAAAAAA/AGM//4///////hwEAAAAAAAAAAP////8AAAAAAA+fkI//////////84cAAAAAAAAAAH////8AAAAAAAP/gAC/////////wz8AAAAAAAAAAB////wAAAAAAA//gAB/////////4HgAAAAAAAAAAA////gAAAAAAA//8cB/////////4MAAAAAAAAAAAA////AAAAAAAB//////////////4AAAAAAAAAAAAAX/5DAAAAAAAB//////3///////8AAAAAAAAAAAAAb/wBgAAAAAAH//////7///////4AAAAAAAAAAAAAN/gBgAAAAAAP////+/8P//////wAAAAAAAAAAAAAE/gAAAAAAAAP/////f+wP/////oAAAAAAAAAAAAACfgBgAAAAAAf/////P/8H/////IAAAAAAAAAAAAAAfgQ4AAAAAAf/////v/8D//f/4AAAAAAAAACAAAAAfxwMgAAAAAf/////v/4A/8P+QAAAAAAAAAAAAAAAP7wJ0AAAAAf/////n/wA/4P+wAAAAAAAAAAAAAAAD/gAAAAAAAf/////z/gAfgH/AMAAAAAAAAAAAAAAAX8AAAAAAAf/////7+AAfAF/gIAAAAAAAAAAAAAAAD+AAAAAAA///////4AAfAB/gMAAAAAAAAAAAAAAAAeAAAAAAAf//////AAAPAB/gKAAAAAAAAAAAAAAAAMD4AAAAAf/////+cAAOABvgHAAAAAAAAAAAAAAAAGX/wAAAAP//////8AAHABCACAAAAAAAAAAAAAAAAD//4AAAAH//////8AAFgBgADgAAAAAAAAAAAAAAAAP/8AAAAD//////4AABgAwADAAAAAAAAAAAAAAAAAP//gAAAB/H////4AAAAGYDgAAAAAAAAAAAAAAAAAP//wAAAAAA////wAAAADYHgAAAAAAAAAAAAAAAAAf//4AAAAAA////gAAAAB8PgAAAAAAAAAAAAAAAAAf//4AAAAAA////AAAAAA4/uQAAAAAAAAAAAAAAAA///+AAAAAA///8AAAAAAYfcGAAAAAAAAAAAAAAAA////wAAAAA///8AAAAAAcfcDcAAAAAAAAAAAAAAA////+AAAAAf//4AAAAAAODcr/hAAAAAAAAAAAAAA/////gAAAAP//wAAAAAAGAUAf3AAAAAAAAAAAAAA/////gAAAAP//wAAAAAAD4AAP4AAAAAAAAAAAAAAf////gAAAAP//wAAAAAAAeogPYAAAAAAAAAAAAAAf////AAAAAP//4AAAAAAAADAAMBAAAAAAAAAAAAAP///+AAAAAH//4AAAAAAAAACAAAAAAAAAAAAAAAAH///+AAAAAP//4IAAAAAAAAHjAAAAAAAAAAAAAAAH///8AAAAAP//4MAAAAAAAAvjgAAAAAAAAAAAAAAD///8AAAAAP//48AAAAAAAB/zgAEAAAAAAAAAAAAA///8AAAAAP//x4AAAAAAAH//wAACAAAAAAAAAAAAf//8AAAAAP//B4AAAAAAAH//wAAAAAAAAAAAAAAAf//4AAAAAP/+B4AAAAAAA///4AAAAAAAAAAAAAAAf//4AAAAAH//BwAAAAAAD///8AIAAAAAAAAAAAAAf//wAAAAAH//BwAAAAAAD///+AAAAAAAAAAAAAAAf/+AAAAAAH/+BwAAAAAAD////AAAAAAAAAAAAAAAf/8AAAAAAD/8AAAAAAAAD////AAAAAAAAAAAAAAA//8AAAAAAD/8AAAAAAAAD////gAAAAAAAAAAAAAA//4AAAAAAB/4AAAAAAAAD////AAAAAAAAAAAAAAA//4AAAAAAA/4AAAAAAAAB////AAAAAAAAAAAAAAA//gAAAAAAA/wAAAAAAAAB/z//AAAAAAAAAAAAAAA//gAAAAAAA/AAAAAAAAAB+A/+AAAAAAAAAAAAAAB/8AAAAAAAAAAAAAAAAAAAgAP+AAQAAAAAAAAAAAB/8AAAAAAAAAAAAAAAAAAAAAH8AAIAAAAAAAAAAAB/8AAAAAAAAAAAAAAAAAAAAAD4AAOAAAAAAAAAAAB/gAAAAAAAAAAAAAAAAAAAAAAAAAMAAAAAAAAAAAD/AAAAAAAAAAAAAAAAAAAAAAA4AA8AAAAAAAAAAAD+AAAAAAAAAAAAAAAAAAAAAAAYAAwAAAAAAAAAAAD+AAAAAAAAAAAAAAAAAAAAAAAAADgAAAAAAAAAAAD4AAAAAAAAAAAAAAAAAAAAAAAAAHAAAAAAAAAAAAD8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH8AAAAAAAAAAAAAACAAAAAAAAAAAAAAAAAAAAAAAD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADwIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' };
let LANDS = null;
function lands() { // [lon, lat] of every land cell's centre
  if (LANDS) return LANDS;
  const raw = atob(MAP.bits), out = [];
  for (let i = 0; i < MAP.cols * MAP.rows; i++) {
    if ((raw.charCodeAt(i >> 3) >> (7 - (i & 7))) & 1) out.push([-180 + (i % MAP.cols + .5) * MAP.step, MAP.lat0 - (Math.floor(i / MAP.cols) + .5) * MAP.step]);
  }
  return (LANDS = out);
}
const wrap180 = (d) => ((d + 180) % 360 + 360) % 360 - 180;
// where the arcs come from when the content names no origins: a spread of the world's big hubs
const HUBS = [[40.7, -74], [-23.5, -46.6], [19.4, -99.1], [43.7, -79.4], [37.8, -122.4], [4.7, -74.1], [-34.6, -58.4], [6.5, 3.4],
  [-1.3, 36.8], [-33.9, 18.4], [30, 31.2], [25.2, 55.3], [19.1, 72.9], [1.35, 103.8], [-6.2, 106.8], [35.7, 139.7], [37.6, 127],
  [-33.9, 151.2], [52.5, 13.4], [59.3, 18.1], [51.5, -.1], [50.45, 30.5], [41, 29], [-36.8, 174.8], [-12, -77], [49.3, -123.1],
  [5.6, -.2], [60.2, 24.9], [14.6, 121], [-4.3, 15.3]];
const ORIGINS = ((Array.isArray(D.origins) && D.origins.length ? D.origins : HUBS)
  .map((p) => (Array.isArray(p) ? p : [p.lat, p.lon])).filter((p) => Number.isFinite(+p[0]) && Number.isFinite(+p[1]))
  .filter((p) => Math.hypot(p[0] - LAT, wrap180(p[1] - LON)) > 7)).slice(0, 24);
function mapPin(x, y, s, a = 1) { // the pin's tip at x, y
  const c = g();
  SK.alpha(a, () => {
    c.save(); c.translate(x, y); c.scale(s, s);
    c.beginPath(); c.moveTo(0, 0); c.bezierCurveTo(-14, -30, -40, -52, -40, -86); c.arc(0, -86, 40, Math.PI, 0); c.bezierCurveTo(40, -52, 14, -30, 0, 0); c.closePath();
    c.fillStyle = C.accent; c.fill();
    c.lineWidth = 5; c.strokeStyle = C.light; c.stroke();
    disc(0, -86, 15, C.light);
    c.restore();
  });
}

/* ------------------------------------------------------------------ the opening: digits -> pixels -> the logo */
const LOGO_Y = 410;
let MOS = null;
function mosaic() { // the logo (for a dark ground) sampled onto a grid of cells: its colour where it covers a cell
  if (MOS) return MOS;
  const src = logoSrc(true); if (!src || !src.width) return null;
  const s = Math.min(1240 / src.width, 290 / src.height), bw = src.width * s, bh = src.height * s;
  const cs = clamp(bh / 9, 13, 30), cols = Math.ceil(bw / cs) + 1, rows = Math.ceil(bh / cs) + 1, k = 4;
  const cv = document.createElement('canvas'); cv.width = cols * k; cv.height = rows * k;
  const c2 = cv.getContext('2d'), sc = k / cs;
  c2.drawImage(src, (cols * cs - bw) / 2 * sc, (rows * cs - bh) / 2 * sc, bw * sc, bh * sc);
  const px = c2.getImageData(0, 0, cv.width, cv.height).data, cells = [];
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
    let r = 0, gg = 0, b = 0, a = 0;
    for (let y = 0; y < k; y++) for (let x = 0; x < k; x++) {
      const o = ((j * k + y) * cv.width + i * k + x) * 4, al = px[o + 3];
      r += px[o] * al; gg += px[o + 1] * al; b += px[o + 2] * al; a += al;
    }
    if (a / (k * k * 255) > .3) cells.push({ i, j, col: `rgb(${Math.round(r / a)},${Math.round(gg / a)},${Math.round(b / a)})` });
  }
  const out = { src, bw, bh, cs, cols, rows, cells, x0: CX - cols * cs / 2, y0: LOGO_Y - rows * cs / 2, lx: CX - bw / 2, ly: LOGO_Y - bh / 2 };
  if (src !== nameImage(true) || NAMES.has('d')) MOS = out;
  return out;
}
const cellIn = (m, M) => -.55 + (m.i / M.cols) * 1.95 + rnd(m.i * 53 + m.j * 7 + 1) * .18; // when a cell's digit lights up
/** a wall of digits, each turning over at its own rate, drifting up; a bright scan passes over it */
function digitWall(t, a, o = {}) {
  if (a <= 0) return;
  const av = o.avoid; // a box [x0, y0, x1, y1] where the wall goes quiet
  const c = g(), cw = 64, chh = 72, cols = Math.ceil(W / cw) + 1, rows = Math.ceil(H / chh) + 2;
  const dy = -((t * (o.drift ?? 14)) % chh) - chh / 2;
  const scan = o.scan ? lerp(-300, W + 300, clamp((t - o.scan[0]) / (o.scan[1] - o.scan[0]))) : -1e9;
  c.save(); c.font = font(30, 700, FONT.mono); c.textAlign = 'center'; c.textBaseline = 'middle';
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
    const s = j * 211 + i * 17 + 3, x = i * cw + cw / 2, y = j * chh + dy;
    const dg = Math.floor(rnd(s + 1) * 10 + t * (1.2 + rnd(s) * 5)) % 10;
    const near = Math.max(0, 1 - Math.abs(x - scan) / 240), quiet = av && x > av[0] && x < av[2] && y > av[1] && y < av[3] ? .15 : 1;
    c.globalAlpha = Math.min(1, (.22 + rnd(s + 2) * .36) * a + near * .6 * a) * quiet;
    c.fillStyle = near > .45 ? (rnd(s + 5) < .3 ? C.accentOnGround : C.light) : C.groundLt;
    c.fillText(String(dg), x, y);
  }
  c.restore();
}
function openScene(t) {
  const c = g();
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  const push = 1 + .06 * E.sine(clamp(t / 8));
  c.save(); c.translate(CX, 520); c.scale(push, push); c.translate(-CX, -520);
  const M = mosaic();
  digitWall(t, 1 - .55 * ease(t, LOCK, 3.2), { scan: [-.55, 1.6], avoid: M ? [M.x0 - 30, M.y0 - 30, M.x0 + M.cols * M.cs + 30, M.y0 + M.rows * M.cs + 30] : null });
  if (M) {
    const cs = M.cs;
    // the lock: a flash of the accent behind the logo
    const flash = t >= LOCK ? Math.max(0, 1 - (t - LOCK) / .5) : 0;
    if (flash > 0) {
      const gr = c.createRadialGradient(CX, LOGO_Y, 10, CX, LOGO_Y, M.bw * .7);
      gr.addColorStop(0, rgba(C.accent, .5 * flash)); gr.addColorStop(1, rgba(C.accent, 0));
      c.fillStyle = gr; c.fillRect(0, 0, W, H);
    }
    c.save(); c.font = font(cs * .9, 700, FONT.mono); c.textAlign = 'center'; c.textBaseline = 'middle';
    for (const m of M.cells) {
      const x = M.x0 + (m.i + .5) * cs, y = M.y0 + (m.j + .5) * cs, r1 = rnd(m.i * 7 + m.j * 31 + 2);
      const p = clamp((t - cellIn(m, M)) / .16); if (p <= 0) continue;
      const sq = ease(t, 2.2 + r1 * .4, 2.5 + r1 * .4);               // the digit turns into a pixel
      const gone = ease(t, 3.0 + r1 * .35, 3.2 + r1 * .35, E.in);      // ... which gives way to the logo
      if (gone >= 1) continue;
      c.fillStyle = flash > .4 ? C.light : m.col;
      if (sq < 1) {
        const seed = m.i * 17 + m.j * 3, dg = t >= LOCK ? Math.floor(rnd(seed) * 10) : Math.floor(rnd(seed) * 10 + t * (12 + rnd(seed + 1) * 12)) % 10;
        c.globalAlpha = p * (1 - sq) * (t >= LOCK ? 1 : .8);
        c.fillText(String(dg), x, y + cs * .05);
      }
      if (sq > 0) { const z = cs * .88 * sq * (1 - gone); c.globalAlpha = p; c.fillRect(x - z / 2, y - z / 2, z, z); }
    }
    c.restore();
    const crisp = ease(t, 3.0, 3.55);
    if (crisp > 0) SK.alpha(crisp, () => c.drawImage(M.src, M.lx, M.ly, M.bw, M.bh));
  }
  // the headline: its digits roll, its words rise
  const bh = M ? M.bh : 200, head = COPY.headline || '';
  const hs = fit(head, W - 420, 150, { wt: 900 }), hy = LOGO_Y + bh / 2 + 70 + hs * .72;
  odometer(head, CX, hy, HEAD_T, t, { size: hs, align: 'center', d: .7, colOf: (ch) => (/\d/.test(ch) ? C.accentOnGround : C.light) });
  const hw = measure(head, { size: hs, wt: 900 }), rl = ease(t, HEAD_T + .5, HEAD_T + 1.1, E.out);
  if (rl > 0) rrect(CX - hw / 2 * rl, hy + 34, hw * rl, 6, 3, C.accent);
  // the tagline opens from the middle
  const tag = String(EV.tagline ?? '');
  if (tag) {
    const tg = fitWrap(tag, W - 520, 40, 2, { wt: 800, fam: FONT.wide, ls: 6 }), op = ease(t, TAG_T, TAG_T + .7, E.out);
    tg.lines.forEach((ln, i) => {
      const y = hy + 112 + i * tg.size * 1.4, w = measure(ln, { size: tg.size, wt: 800, fam: FONT.wide, ls: 6 }) + 20;
      if (op > 0) clipRect(CX - w / 2 * op, y - tg.size, w * op, tg.size * 1.4, () => text(ln, CX + 3, y, { size: tg.size, wt: 800, fam: FONT.wide, ls: 6, align: 'center', col: C.soft }));
    });
  }
  c.restore();
  ticker(t, TICK_T);
}
/** the numbers to come, running along the foot of the frame like a market ticker */
const TICK_T = 5.5;
function ticker(t, t0) {
  const u = ease(t, t0, t0 + .5, outSoft); if (u <= 0) return;
  const c = g(), y = H - 70 + (1 - u) * 120, size = 26, f = { size, wt: 700, fam: FONT.mono, ls: 2 };
  c.save(); c.fillStyle = rgba(C.groundDk, .85); c.fillRect(0, y - 44, W, 70); c.fillStyle = C.accent; c.fillRect(0, y - 44, W * u, 3); c.restore();
  const items = STATS.map((s) => [s.prefix + s.value + s.suffix, s.label]);
  const ws = items.map(([n, l]) => measure(n + ' ', f) + measure(l, f) + 90), total = ws.reduce((p, q) => p + q, 0);
  if (!total) return;
  let x = -(((t - t0) * 90) % total);
  while (x < W) {
    items.forEach(([n, l], i) => {
      if (x < W && x + ws[i] > 0) {
        text(n, x, y, { ...f, col: C.accentOnGround });
        text(l, x + measure(n + ' ', f), y, { ...f, col: C.light });
        disc(x + ws[i] - 45, y - 9, 5, C.secondOnGround);
      }
      x += ws[i];
    });
  }
}

/* ------------------------------------------------------------------ when: a calendar page marks the days */
const ISO = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s ?? '')); return m ? [+m[1], +m[2], +m[3]] : null; };
const CAL = (() => {
  const a = ISO(EV.start), b = ISO(EV.end) || a; if (!a) return null;
  const [y, mo, d0] = a, days = new Date(Date.UTC(y, mo, 0)).getUTCDate();
  const off = (new Date(Date.UTC(y, mo - 1, 1)).getUTCDay() + 6) % 7; // weeks start on Monday
  const span = Math.max(1, Math.round((Date.UTC(b[0], b[1] - 1, b[2]) - Date.UTC(y, mo - 1, d0)) / 864e5) + 1);
  const d1 = Math.min(days, d0 + span - 1), marked = d1 - d0 + 1;
  const gap = Math.min(BEAT, 2.0 / Math.max(1, marked));
  return { y, mo, d0, d1, days, off, span, rows: Math.ceil((off + days) / 7), markT: (d) => 9.0 + (d - d0) * gap };
})();
const PAGE = { w: 720, h: 740, x: 1390, top: 170 };
function calendarFace(t) {
  return (c, w, h) => {
    rrect(0, 0, w, h, 28, C.card);
    c.save(); SK.rrPath(0, 0, w, h, 28); c.clip(); c.fillStyle = C.accent; c.fillRect(0, 0, w, 150); c.restore();
    const month = String(EV.month ?? '');
    text(month, 40, 108, { size: fit(month, w - 260, 92), wt: 900, col: C.inkOnAccent });
    text(String(EV.year ?? CAL.y), w - 40, 104, { size: 40, wt: 700, fam: FONT.mono, col: C.inkOnAccent, align: 'right' });
    for (let k = 0; k < 7; k++) disc(70 + k * (w - 140) / 6, 0, 11, C.groundDk); // the binding
    const cw = (w - 60) / 7, top = 214, rh = Math.min(92, (h - top - 26) / CAL.rows);
    if (WEEKDAYS) WEEKDAYS.forEach((d, k) => text(d, 30 + cw * (k + .5), 192, { size: fit(d, cw - 10, 22, { wt: 700, fam: FONT.mono }), wt: 700, fam: FONT.mono, col: k > 4 ? C.accentOnPaper : C.inkSoft, align: 'center' }));
    for (let d = 1; d <= CAL.days; d++) {
      const idx = CAL.off + d - 1, col = idx % 7, row = Math.floor(idx / 7), x = 30 + cw * (col + .5), y = top + rh * (row + .5);
      const a = ease(t, 8.3 + idx * .012, 8.55 + idx * .012);
      if (a <= 0) continue;
      const on = d >= CAL.d0 && d <= CAL.d1, m = on ? outBack(clamp((t - CAL.markT(d)) / .3)) : 0;
      if (on && m > 0) {
        // the band joining it to the day before, in the same week
        if (d > CAL.d0 && col > 0) { const b = clamp((t - CAL.markT(d)) / .2); c.fillStyle = rgba(C.accent, .28); c.fillRect(x - cw * b, y - rh * .3, cw * b, rh * .6); }
        rrect(x - rh * .42 * m, y - rh * .42 * m, rh * .84 * m, rh * .84 * m, 14 * m, C.accent);
      }
      text(String(d), x, y + rh * .19, { size: rh * .52, wt: 800, col: m > .5 ? C.inkOnAccent : col > 4 ? C.inkSoft : C.ground, align: 'center', alpha: a });
    }
  };
}
function whenScene(t) {
  const c = g();
  c.fillStyle = C.paper; c.fillRect(0, 0, W, H);
  // graph paper
  c.save(); c.fillStyle = rgba(C.ground, .07);
  for (let y = 40; y < H; y += 40) for (let x = 40 - ((t * 10) % 40); x < W; x += 40) c.fillRect(x - 1.5, y - 1.5, 3, 3);
  c.restore();
  const lx = 120, colW = CAL ? 790 : W - 240, al = CAL ? 'left' : 'center', ax = CAL ? lx : CX;
  // the kicker, the dates, the dates in full, how many days
  const k = ease(t, 8.2, 8.5, E.out);
  if (k > 0) SK.alpha(k, () => {
    if (CAL) rrect(lx, 302, 22, 22, 4, C.accentOnPaper);
    text(COPY.when ?? '', CAL ? lx + 38 : CX, 322, { size: 28, wt: 700, fam: FONT.mono, ls: 6, col: C.accentOnPaper, align: al });
  });
  const ds = String(EV.dates ?? ''), dz = fit(ds, colW, 230), du = ease(t, 8.35, 8.9, outSoft);
  clipRect(0, 330, W, dz * 1.0, () => text(ds, ax, 340 + dz * .78 + (1 - du) * dz, { size: dz, wt: 900, col: C.ground, align: al }));
  const dl = String(EV.dates_long ?? ''), dlz = fit(dl, colW, 44, { wt: 800, fam: FONT.wide, ls: 2 }), dlu = ease(t, 9.0, 9.4, E.out);
  if (dlu > 0) clipRect(0, 360 + dz, W, 70, () => text(dl, ax, 360 + dz + 52 + (1 - dlu) * 60, { size: dlz, wt: 800, fam: FONT.wide, ls: 2, col: C.inkSoft, align: al }));
  if (CAL && COPY.days) {
    const n = String(CAL.span), y = 360 + dz + 52 + 165;
    const w0 = odometer(n, ax, y, 9.5, t, { size: 120, colOf: () => C.accentOnPaper, d: .6 });
    if (t > 9.6) text(COPY.days, ax + w0 + 22, y, { size: 56, wt: 900, ls: 2, col: C.ground, alpha: ease(t, 9.7, 10.0) });
  }
  if (!CAL) return;
  // the page: it swings down from its binding, settles, and sways a little
  SK.view3({ d: 1700 });
  const sw = ease(t, 8.0, 8.75, outSoft), th = lerp(-1.45, 0, sw) + Math.sin((t - 8.75) * 1.7) * .025 * (t > 8.75);
  const pose = { x: PAGE.x, y: PAGE.top, z: 0, rx: th, ry: -.16 + .05 * Math.sin(t * .6), rz: .02 };
  const P = [[-PAGE.w / 2, 0, 0], [PAGE.w / 2, 0, 0], [PAGE.w / 2, PAGE.h, 0], [-PAGE.w / 2, PAGE.h, 0]].map((p) => SK.pose3(p, pose));
  const Sh = P.map((p) => SK.proj3([p[0] + 26, p[1] + 34, p[2] + 40]));
  if (Sh.every(Boolean)) { c.save(); c.filter = 'blur(24px)'; c.beginPath(); Sh.forEach((q, i) => (i ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]))); c.closePath(); c.fillStyle = rgba(C.ground, .28); c.fill(); c.restore(); }
  SK.face3(P, PAGE.w, PAGE.h, calendarFace(t), { key: 'calendar', cull: false });
}

/* ------------------------------------------------------------------ where: a pin drops on the dot map */
function whereScene(t) {
  const c = g();
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  groundGrid(t);
  const span = lerp(86, 60, ease(t, T_WHERE - .3, T_WHERE + 4, E.out)), cs = W / (span / MAP.step), r = cs * .3;
  const hx = W * .62, hy = H * .43;
  const paths = [new Path2D(), new Path2D(), new Path2D()];
  for (const [lo, la] of HAS_GEO ? lands() : []) { // no coordinates: the pin lands on the bare grid
    const x = hx + wrap180(lo - LON) / MAP.step * cs, y = hy - (la - LAT) / MAP.step * cs;
    if (x < -cs || x > W + cs || y < -cs || y > H + cs) continue;
    const d = Math.hypot(x - hx, y - hy) / cs, k = d < 2.5 ? 2 : d < 5 ? 1 : 0;
    paths[k].moveTo(x + r, y); paths[k].arc(x, y, r, 0, TAU);
  }
  [C.groundLt, mixHex(C.groundLt, C.accent, .45), mixHex(C.groundLt, C.accent, .8)].forEach((col, i) => { c.fillStyle = col; c.fill(paths[i]); });
  // ripples on every beat after the pin lands
  for (let b = PIN_T; b < T_NUMS; b += BEAT) {
    const u = (t - b) / 1.4; if (u <= 0 || u >= 1) continue;
    ring(hx, hy, 14 + 190 * E.out(u), 5 * (1 - u) + 1, rgba(C.accent, .8 * (1 - u)));
  }
  // the pin falls, lands on the beat, squashes and settles
  const fall = clamp((t - (PIN_T - .45)) / .45);
  if (fall > 0) {
    const y = hy - 380 * (1 - E.in(fall)), land = t - PIN_T, sq = land > 0 ? Math.exp(-land * 7) * Math.sin(land * 26) * .16 : 0;
    c.save(); c.globalAlpha = .45 * fall; c.fillStyle = C.groundDk; c.beginPath(); c.ellipse(hx, hy + 4, 30 * (.5 + .5 * fall), 9, 0, 0, TAU); c.fill(); c.restore();
    c.save(); c.translate(hx, y); c.scale(1 + sq, 1 - sq); mapPin(0, 0, 1.15); c.restore();
  }
  // the place: kicker, city, venue, its coordinates
  scrim('left', .9, .5);
  const lx = 120, k = ease(t, PIN_T - .2, PIN_T + .1, E.out);
  const kick = [COPY.where, EV.country].filter(Boolean).join('  ·  ');
  if (k > 0) SK.alpha(k, () => { rrect(lx, 596, 22, 22, 4, C.accentOnGround); text(kick, lx + 38, 616, { size: fit(kick, 760, 28, { wt: 700, fam: FONT.mono, ls: 6 }), wt: 700, fam: FONT.mono, ls: 6, col: C.accentOnGround }); });
  const city = String(EV.city ?? ''), cz = fit(city, 860, 210), cu = ease(t, PIN_T + .1, PIN_T + .6, outSoft);
  clipRect(0, 640, W, cz * .98, () => text(city, lx - 4, 640 + cz * .76 + (1 - cu) * cz, { size: cz, wt: 900, col: C.light }));
  const ven = String(EV.venue ?? ''), vz = fit(ven, 860, 46, { wt: 800, fam: FONT.wide, ls: 2 }), vu = ease(t, PIN_T + .4, PIN_T + .8, E.out);
  if (vu > 0) clipRect(0, 660 + cz, W, 70, () => text(ven, lx, 660 + cz + 50 + (1 - vu) * 60, { size: vz, wt: 800, fam: FONT.wide, ls: 2, col: C.light }));
  if (HAS_GEO) {
    const geo = `${LAT.toFixed(4)}°, ${LON.toFixed(4)}°`.replace(/-/g, '−'), n = Math.floor((t - PIN_T - .7) * 30);
    if (n > 0) text(geo.slice(0, n), lx, 660 + cz + 112, { size: 26, wt: 700, fam: FONT.mono, ls: 2, col: C.soft });
  }
}

/* ------------------------------------------------------------------ the numbers' pictures (one per kind) */
// people: a crowd of dots that fills the frame, in a wave from the picture's side
function crowd(ch, t) {
  const c = g(), a = ch.a, sp = 30, R = 8.6, [fx, fy] = ch.focus, rows = Math.ceil(H / (sp * .866)) + 2, cols = Math.ceil(W / sp) + 2;
  const cl = [C.groundLt, C.soft, C.accent, C.second], paths = cl.map(() => new Path2D());
  for (let j = 0; j < rows; j++) for (let k = 0; k < cols; k++) {
    const x = k * sp + (j & 1) * sp / 2 - sp / 2, y = j * sp * .866 - sp / 2, d = Math.hypot(x - fx, y - fy);
    const ta = a + .15 + d / 1500 * 1.6 + rnd(j * 977 + k * 13) * .2, p = clamp((t - ta) / .3); if (p <= 0) continue;
    const r = R * outBack(p) * (1 + .16 * Math.sin((t - a) * 4 - d / 110));
    const q = rnd(j * 131 + k * 7 + 5), ci = q < .07 ? 2 : q < .13 ? 3 : q < .32 ? 1 : 0;
    paths[ci].moveTo(x + r, y); paths[ci].arc(x, y, r, 0, TAU);
  }
  c.save(); cl.forEach((col, i) => { c.globalAlpha = i === 1 ? .55 : 1; c.fillStyle = col; c.fill(paths[i]); }); c.restore();
}
// countries: the world in dots, the host city on the picture's side, arcs flying in to it
function worldView(ch) { // the whole world, turned so the host city sits on the picture's side; the arcs that start on screen
  const cs = W / MAP.cols, top = (H - MAP.rows * cs) / 2 + 30;
  const hx = ch.side === 'right' ? W * .3 : W * .7, hy = top + (MAP.lat0 - LAT) / MAP.step * cs, lo0 = -hx / cs * MAP.step;
  const X = (lon) => hx + ((((lon - LON) - lo0) % 360 + 360) % 360 + lo0) / MAP.step * cs, Y = (lat) => top + (MAP.lat0 - lat) / MAP.step * cs;
  const arcs = ORIGINS.filter(([la, lo]) => X(lo) > 40 && X(lo) < W - 40 && Y(la) > 120 && Y(la) < H - 120);
  return { cs, top, hx, hy, X, Y, arcs, arcT: (i) => ch.a + .6 + i * (1.8 / Math.max(1, arcs.length)) };
}
function world(ch, t) {
  const c = g(), a = ch.a, V = worldView(ch), { cs, hx, hy, X, Y } = V;
  const paths = [new Path2D(), new Path2D()], r = cs * .34;
  for (const [lo, la] of lands()) {
    const x = X(lo), y = Y(la), d = Math.hypot(x - hx, y - hy), p = clamp((t - a - .05 - d / 2200 * .8) / .25);
    if (p <= 0) continue;
    const k = d < cs * 4 ? 1 : 0;
    paths[k].moveTo(x + r * p, y); paths[k].arc(x, y, r * p, 0, TAU);
  }
  c.fillStyle = mixHex(C.groundLt, C.soft, .22); c.fill(paths[0]); c.fillStyle = C.accentOnGround; c.fill(paths[1]);
  // the arcs
  V.arcs.forEach(([la, lo], i) => {
    const t0 = V.arcT(i), dur = .85, u = clamp((t - t0) / dur); if (u <= 0) return;
    const p0 = [X(lo), Y(la)], dist = Math.hypot(hx - p0[0], hy - p0[1]), m = [(p0[0] + hx) / 2, (p0[1] + hy) / 2 - dist * .38];
    const q = (s) => [(1 - s) * (1 - s) * p0[0] + 2 * (1 - s) * s * m[0] + s * s * hx, (1 - s) * (1 - s) * p0[1] + 2 * (1 - s) * s * m[1] + s * s * hy];
    const e = E.inOut(u), col = i % 3 === 0 ? C.accentOnGround : C.secondOnGround;
    disc(p0[0], p0[1], 5 * clamp(u * 4), col);
    c.save(); c.beginPath(); for (let s = 0; s <= 30; s++) { const pt = q(e * s / 30); s ? c.lineTo(pt[0], pt[1]) : c.moveTo(pt[0], pt[1]); }
    c.lineWidth = 3; c.lineCap = 'round'; c.strokeStyle = col; c.globalAlpha = u < 1 ? .9 : .9 - .5 * clamp((t - t0 - dur) / .8); c.stroke(); c.restore();
    if (u < 1) { const h = q(e); disc(h[0], h[1], 7, C.light); }
  });
  // the host: rings on every arrival, a dot that glows
  for (let b = a + .6 + .85; b < ch.b; b += BEAT) { const u = (t - b) / 1.2; if (u > 0 && u < 1) ring(hx, hy, 12 + 120 * E.out(u), 4 * (1 - u) + 1, rgba(C.accent, .8 * (1 - u))); }
  disc(hx, hy, 13 * outBack(clamp((t - a - .3) / .4)), C.accent); disc(hx, hy, 5, C.light);
}
// companies: a city of blocks rising on the picture's side
function city(ch, t) {
  const c = g(), a = ch.a, [fx, fy] = ch.focus, n = 7, tw = 54, th = 31, k = .8;
  const ox = fx, oy = fy + 30 - (n - 1) * th;
  const list = [];
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) list.push([i, j]);
  list.sort((p, q) => p[0] + p[1] - (q[0] + q[1]) || p[0] - q[0]);
  // the ground they stand on
  const gu = ease(t, a + .05, a + .4, E.out);
  if (gu > 0) {
    const e = n * tw * gu, f = n * th * gu, gx = ox, gy = oy + (n - 1) * th;
    c.beginPath(); c.moveTo(gx, gy - f); c.lineTo(gx + e, gy); c.lineTo(gx, gy + f); c.lineTo(gx - e, gy); c.closePath(); c.fillStyle = C.groundMid; c.fill();
  }
  const schemes = [[C.light, C.accent, C.accentDk], [C.light, C.second, C.secondDk], [C.soft, C.groundLt, C.groundMid]];
  for (const [i, j] of list) {
    const s = i * 31 + j * 7 + 3, q = rnd(s);
    if (q < .1) continue; // a square
    const h = 26 + Math.pow(rnd(s + 1), 1.7) * 280, ta = a + .3 + (i + j) * .07 + rnd(s + 2) * .06, p = clamp((t - ta) / .5);
    if (p <= 0) continue;
    const hh = h * outBack(p), gx = ox + (i - j) * tw, gy = oy + (i + j) * th, sc = schemes[q < .45 ? 0 : q < .7 ? 1 : 2];
    const Nn = [gx, gy - th * k], Ee = [gx + tw * k, gy], Ss = [gx, gy + th * k], Ww = [gx - tw * k, gy], up = (p2) => [p2[0], p2[1] - hh];
    const face = (pts, col) => { c.beginPath(); pts.forEach((p2, m) => (m ? c.lineTo(p2[0], p2[1]) : c.moveTo(p2[0], p2[1]))); c.closePath(); c.fillStyle = col; c.fill(); };
    face([Ww, Ss, up(Ss), up(Ww)], sc[1]); face([Ss, Ee, up(Ee), up(Ss)], sc[2]); face([up(Nn), up(Ee), up(Ss), up(Ww)], sc[0]);
    // lit windows, floor by floor, some of them switching on and off
    c.fillStyle = rgba(C.light, .55);
    for (let fl = 18; fl < hh - 10; fl += 22) {
      const on = rnd(s * 3 + fl + Math.floor((t - a) * 1.5)) > .55; if (!on) continue;
      const wx = Ss[0] + tw * k * .5, wy = Ss[1] - fl - th * k * .5 + 6;
      c.beginPath(); c.moveTo(wx - 7, wy - 3); c.lineTo(wx + 7, wy - 11); c.lineTo(wx + 7, wy - 3); c.lineTo(wx - 7, wy + 5); c.closePath(); c.fill();
    }
  }
}
// investors: a network that grows outwards, with deals running along it
const NETS = new Map();
function netOf(fx, fy) {
  const key = fx + ',' + fy; if (NETS.has(key)) return NETS.get(key);
  const nodes = [];
  for (let j = 0; j < 6; j++) for (let i = 0; i < 7; i++) {
    const s = j * 17 + i * 5 + 11;
    nodes.push({ x: fx - 400 + i * 133 + (rnd(s) - .5) * 90, y: fy - 340 + j * 136 + (rnd(s + 1) - .5) * 90, s, deg: 0 });
  }
  const edges = [], seen = new Set();
  nodes.forEach((p, i) => {
    nodes.map((q, j) => [Math.hypot(p.x - q.x, p.y - q.y), j]).filter(([, j]) => j !== i).sort((u, v) => u[0] - v[0]).slice(0, 2 + (rnd(p.s + 3) > .6 ? 1 : 0))
      .forEach(([, j]) => { const k = Math.min(i, j) + ':' + Math.max(i, j); if (!seen.has(k)) { seen.add(k); edges.push([i, j]); nodes[i].deg++; nodes[j].deg++; } });
  });
  const net = { nodes, edges };
  NETS.set(key, net);
  return net;
}
function network(ch, t) {
  const c = g(), a = ch.a, [fx, fy] = ch.focus, net = netOf(fx, fy);
  const ti = (p) => a + .3 + Math.hypot(p.x - fx, p.y - fy) / 520 * 1.1;
  c.save(); c.lineCap = 'round';
  for (const [i, j] of net.edges) {
    const p = net.nodes[i], q = net.nodes[j], u = clamp((t - Math.max(ti(p), ti(q)) + .1) / .35); if (u <= 0) continue;
    const [s0, s1] = ti(p) < ti(q) ? [p, q] : [q, p];
    c.beginPath(); c.moveTo(s0.x, s0.y); c.lineTo(lerp(s0.x, s1.x, E.out(u)), lerp(s0.y, s1.y, E.out(u)));
    c.lineWidth = 3; c.strokeStyle = rgba(C.light, .28); c.stroke();
    // a deal running along it
    if (u >= 1 && rnd(i * 7 + j * 13) < .45) {
      const ph = ((t - a) * (.5 + rnd(i + j * 3) * .5) + rnd(i * 3 + j)) % 1, x = lerp(s0.x, s1.x, ph), y = lerp(s0.y, s1.y, ph);
      disc(x, y, 5, (i + j) % 2 ? C.secondOnGround : C.accentOnGround);
    }
  }
  c.restore();
  net.nodes.forEach((p, i) => {
    const u = clamp((t - ti(p)) / .35); if (u <= 0) return;
    const hub = p.deg >= 5, r = (hub ? 22 : 9 + rnd(p.s + 7) * 6) * outBack(u);
    if (hub) { const b = ((t - a) % BEAT) / BEAT; ring(p.x, p.y, r + 8 + 24 * b, 3, rgba(C.accent, .7 * (1 - b))); }
    disc(p.x, p.y, r, hub ? C.accent : i % 3 ? C.light : C.second);
  });
}
// speakers: a wall of tiles that turn over; the content's pictures on them when it gives them
function speakerWall(ch, t) {
  const c = g(), a = ch.a, [fx, fy] = ch.focus, cols = 6, rows = 4, tw = 134, th = 166, gp = 14;
  const x0 = fx - (cols * (tw + gp) - gp) / 2, y0 = fy - (rows * (th + gp) - gp) / 2;
  const pics = (Array.isArray(ch.s.images) ? ch.s.images : []).filter((k) => SK.IMG[k]);
  const fills = [C.accent, C.second, C.groundLt, C.accentDk, C.secondDk, C.groundMid];
  const live = Math.floor((t - a - 2.2) / BEAT); // a tile is "on stage" for a beat at a time
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
    const s = j * cols + i, ta = a + .3 + (i + j) * .07 + rnd(s + 9) * .05, p = clamp((t - ta) / .42); if (p <= 0) continue;
    const sx = Math.abs(Math.cos((1 - E.out(p)) * Math.PI / 2)), x = x0 + i * (tw + gp), y = y0 + j * (th + gp), col = fills[Math.floor(rnd(s + 1) * fills.length)];
    c.save(); c.translate(x + tw / 2, y + th / 2); c.scale(sx, 1); c.translate(-tw / 2, -th / 2);
    rrect(0, 0, tw, th, 14, col);
    const im = pics.length ? SK.IMG[pics[s % pics.length]] : null;
    if (im) {
      c.save(); SK.rrPath(0, 0, tw, th, 14); c.clip();
      const k = Math.max(tw / im.width, th / im.height); c.drawImage(im, (tw - im.width * k) / 2, (th - im.height * k) / 2, im.width * k, im.height * k); c.restore();
    } else { // a bust
      const sh = mixHex(col, C.ground, .45);
      disc(tw / 2, th * .4, tw * .19, sh);
      c.save(); SK.rrPath(0, 0, tw, th, 14); c.clip(); c.beginPath(); c.ellipse(tw / 2, th * 1.02, tw * .38, th * .34, 0, Math.PI, TAU); c.fillStyle = sh; c.fill(); c.restore();
    }
    c.restore();
    if (live >= 0 && t < ch.b - .2 && Math.floor(rnd(live * 7 + 3) * cols * rows) === s) {
      const b = clamp((t - a - 2.2 - live * BEAT) / BEAT);
      c.save(); c.lineWidth = 6; c.strokeStyle = rgba(C.light, 1 - b * .7); SK.rrPath(x - 7, y - 7, tw + 14, th + 14, 18); c.stroke(); c.restore();
    }
  }
}
// sessions: a clock -- its ring of hours fills, its hand turns once a bar
function clock(ch, t) {
  const c = g(), a = ch.a, [fx, fy] = ch.focus, R = 320, Wd = 62, nS = 24;
  const ru = ease(t, a + .1, a + .5, outSoft);
  ring(fx, fy, (R + 14) * ru, 3, rgba(C.light, .25));
  for (let k = 0; k < nS; k++) {
    const u = clamp((t - a - .35 - k * .065) / .3); if (u <= 0) continue;
    const a0 = -Math.PI / 2 + k * TAU / nS + .02, a1 = a0 + TAU / nS - .04, ro = R - Wd + Wd * E.out(u);
    c.beginPath(); c.arc(fx, fy, ro, a0, a1); c.arc(fx, fy, R - Wd, a1, a0, true); c.closePath();
    c.fillStyle = [C.accent, C.second, C.light][k % 3]; c.globalAlpha = k % 3 === 2 ? .85 : 1; c.fill(); c.globalAlpha = 1;
  }
  for (let k = 0; k < 60; k++) {
    const u = clamp((t - a - .2 - k * .012) / .2); if (u <= 0) continue;
    const an = k * TAU / 60, r0 = R - Wd - 26, r1 = r0 - (k % 5 ? 14 : 32);
    c.beginPath(); c.moveTo(fx + Math.cos(an) * r0, fy + Math.sin(an) * r0); c.lineTo(fx + Math.cos(an) * lerp(r0, r1, u), fy + Math.sin(an) * lerp(r0, r1, u));
    c.lineWidth = k % 5 ? 3 : 7; c.strokeStyle = rgba(C.light, k % 5 ? .4 : .9); c.stroke();
  }
  // the sweep behind the hand, and the hand: a turn every bar
  const hu = ease(t, a + .3, a + .7, E.out), an = -Math.PI / 2 + ((t - a - .3) / BAR) * TAU, hl = (R - Wd - 50) * hu;
  if (hu > 0) {
    c.save(); c.beginPath(); c.moveTo(fx, fy); c.arc(fx, fy, hl, an - .9, an); c.closePath();
    const gr = c.createRadialGradient(fx, fy, 0, fx, fy, hl); gr.addColorStop(0, rgba(C.accent, 0)); gr.addColorStop(1, rgba(C.accent, .28));
    c.fillStyle = gr; c.fill(); c.restore();
    c.save(); c.lineCap = 'round'; c.lineWidth = 12; c.strokeStyle = C.light; c.beginPath(); c.moveTo(fx - Math.cos(an) * 40, fy - Math.sin(an) * 40); c.lineTo(fx + Math.cos(an) * hl, fy + Math.sin(an) * hl); c.stroke(); c.restore();
    const an2 = an / 12 - Math.PI / 3;
    c.save(); c.lineCap = 'round'; c.lineWidth = 16; c.strokeStyle = C.soft; c.beginPath(); c.moveTo(fx, fy); c.lineTo(fx + Math.cos(an2) * hl * .6, fy + Math.sin(an2) * hl * .6); c.stroke(); c.restore();
    disc(fx, fy, 22, C.accent); disc(fx, fy, 8, C.light);
  }
}
// years: a timeline, a tick for each one, the last one lit
function timeline(ch, t) {
  const c = g(), a = ch.a, s = ch.s, y = 830, x0 = 130, x1 = W - 130;
  const v = parseInt(s.value.replace(/\D/g, ''), 10), n = clamp(Number.isFinite(v) && v >= 2 && v <= 60 ? v : 12, 2, 60);
  const lu = ease(t, a + .2, a + 1.8, E.inOut);
  c.save(); c.lineCap = 'round'; c.lineWidth = 5; c.strokeStyle = rgba(C.light, .35); c.beginPath(); c.moveTo(x0, y); c.lineTo(lerp(x0, x1, lu), y); c.stroke(); c.restore();
  const hi = ((t - a - 2.2) * 6) % (n + 6);
  for (let i = 0; i < n; i++) {
    const x = lerp(x0, x1, i / (n - 1)), u = clamp((t - a - .3 - i * (1.6 / n)) / .3); if (u <= 0) continue;
    const last = i === n - 1, glow = Math.max(0, 1 - Math.abs(i - hi) / 2);
    c.save(); c.lineWidth = 4; c.strokeStyle = rgba(C.light, .5 + .5 * glow); c.beginPath(); c.moveTo(x, y - 26 * E.out(u)); c.lineTo(x, y + 26 * E.out(u)); c.stroke(); c.restore();
    disc(x, y, (last ? 20 : 8 + 4 * glow) * outBack(u), last ? C.accent : glow > .5 ? C.accentOnGround : C.light);
    if (last) { const b = ((t - a) % BEAT) / BEAT; ring(x, y, 28 + 30 * b, 3, rgba(C.accent, .8 * (1 - b))); }
  }
  const lab = (str, x, al, col, size) => text(String(str), x, y + 86, { size, wt: 700, fam: FONT.mono, ls: 2, col, align: al, alpha: ease(t, a + 1.2, a + 1.6) });
  if (s.from) lab(s.from, x0, 'left', C.light, 30);
  if (s.to) lab(s.to, x1, 'right', C.accentOnGround, 30);
}
// media: camera flashes going off, and the soft light they leave
function flashes(ch, t) {
  const c = g(), a = ch.a, L = ch.b - ch.a, [fx] = ch.focus;
  c.save(); c.globalCompositeOperation = 'lighter';
  for (let f = 0; f < 46; f++) {
    const tf = a + .25 + Math.pow(rnd(f * 3 + 1), 1.5) * (L - .7), u = (t - tf) / .5;
    const x = fx + (rnd(f * 5 + 2) - .5) * 980, y = 150 + rnd(f * 7 + 3) * 780, s = 30 + rnd(f * 11 + 4) * 60;
    if (u > 0) { // the bokeh it leaves
      const bu = clamp(u / 6), br = s * (1.4 + bu * 1.2);
      c.globalAlpha = .1 * (1 - bu); c.fillStyle = f % 2 ? C.accent : C.second; c.beginPath(); c.arc(x, y + bu * 40, br, 0, TAU); c.fill();
    }
    if (u <= 0 || u >= 1) continue;
    const k = Math.pow(1 - u, 2);
    const gr = c.createRadialGradient(x, y, 0, x, y, s * 2.6); gr.addColorStop(0, `rgba(${C.lightRGB},${.9 * k})`); gr.addColorStop(.25, `rgba(${C.lightRGB},${.35 * k})`); gr.addColorStop(1, `rgba(${C.lightRGB},0)`);
    c.globalAlpha = 1; c.fillStyle = gr; c.beginPath(); c.arc(x, y, s * 2.6, 0, TAU); c.fill();
    c.fillStyle = `rgba(${C.lightRGB},${k})`;
    for (const [rx, ry, rot] of [[s * 3 * (1 - u * .4), 3, 0], [3, s * 2 * (1 - u * .4), 0], [s * 1.2, 2, Math.PI / 4], [s * 1.2, 2, -Math.PI / 4]]) { c.beginPath(); c.ellipse(x, y, rx, ry, rot, 0, TAU); c.fill(); }
  }
  c.restore();
}
// type: the number alone, giant, over its own digits drifting in outline
function giant(ch, t) {
  const c = g(), a = ch.a, digits = ch.s.value.replace(/\D/g, '') || '0';
  c.save(); c.font = font(760, 900); c.textAlign = 'center'; c.lineWidth = 3; c.strokeStyle = rgba(C.light, .1 * ease(t, a, a + .5));
  for (let k = 0; k < 3; k++) { const y = 700 + k * 620 - ((t - a) * 60 + k * 207) % 1860; c.strokeText(digits, CX + (k - 1) * 380, y); }
  c.restore();
}
const PICTURE = { people: crowd, countries: world, companies: city, network, speakers: speakerWall, sessions: clock, years: timeline, media: flashes, type: giant };

function chapterScene(ch, t) {
  const c = g(), s = ch.s, a = ch.a, L = ch.b - ch.a;
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  if (s.kind !== 'people') groundGrid(t);
  // the camera: a punch-in on the cut, then a slow push towards the picture
  const kick = .05 * Math.pow(1 - clamp((t - a) / .6), 2), push = 1 + .035 * E.sine(clamp((t - a) / L)) + kick;
  c.save(); c.translate(ch.focus[0], CY); c.scale(push, push); c.translate(-ch.focus[0], -CY);
  PICTURE[s.kind](ch, t);
  c.restore();
  // the number: over a scrim on its side (or a panel, over the crowd)
  const bw = 760, bx = ch.side === 'left' ? 120 : ch.side === 'right' ? W - 120 - bw : CX - 820;
  const yMid = s.kind === 'years' ? 440 : CY + 10, al = ch.side === 'center' ? 'center' : 'left', w = ch.side === 'center' ? 1640 : bw;
  if (s.kind === 'people') {
    const Lb = blockLayout(s, w), pu = ease(t, a + .15, a + .5, outSoft);
    c.save(); c.shadowColor = `rgba(${C.shadow},.6)`; c.shadowBlur = 60; c.shadowOffsetY = 20;
    rrect(bx - 56, yMid - Lb.h / 2 - 56 + (1 - pu) * 40, (bw + 112) * pu, Lb.h + 112, 28, C.ground); c.restore();
  } else if (['countries', 'media', 'network', 'years'].includes(s.kind)) scrim(ch.side === 'center' ? 'left' : ch.side, .94, .55);
  numberBlock(s, bx, yMid, w, ch.t0, t, { align: al, max: ch.side === 'center' ? 440 : 300 });
}

/* ------------------------------------------------------------------ the frame's furniture over the numbers */
function furniture(t) {
  const a = ease(t, T_NUMS - .2, T_NUMS + .4) * (1 - ease(t, T_WORDS - .35, T_WORDS - .05));
  if (a <= 0) return;
  let k = 0; while (k < N - 1 && t >= CHAPTERS[k + 1].a) k++;
  const ch = CHAPTERS[k];
  SK.alpha(a, () => {
    const c = g();
    for (const [y0, y1] of [[0, 170], [H, H - 150]]) {
      const gr = c.createLinearGradient(0, y0, 0, y1); gr.addColorStop(0, `rgba(${C.groundRGB},.9)`); gr.addColorStop(1, `rgba(${C.groundRGB},0)`);
      c.fillStyle = gr; c.fillRect(0, Math.min(y0, y1), W, Math.abs(y1 - y0));
    }
    const lw = drawLogo(true, 120, 74, 240, 36);
    text(COPY.in_numbers ?? '', 120 + lw + (lw ? 26 : 0), 84, { size: 22, wt: 700, fam: FONT.mono, ls: 5, col: C.soft });
    // which number this is: 03 / 06, the count rolling on each cut
    const tot = ' / ' + pad2(N), tw = measure(tot, { size: 26, wt: 700, fam: FONT.mono });
    text(tot, W - 120, 86, { size: 26, wt: 700, fam: FONT.mono, col: C.soft, align: 'right' });
    odometer(pad2(k + 1), W - 120 - tw, 86, ch.a - .1, t, { size: 26, wt: 700, fam: FONT.mono, align: 'right', d: .35, step: .05, colOf: () => C.light });
    // the progress: a segment per number
    const y = H - 70, gap = 12, sw = (W - 240 - gap * (N - 1)) / N;
    CHAPTERS.forEach((c2, i) => {
      const x = 120 + i * (sw + gap), u = clamp((t - c2.a) / (c2.b - c2.a));
      rrect(x, y, sw, 5, 2.5, rgba(C.light, .16));
      if (u > 0) rrect(x, y, sw * u, 5, 2.5, i === k ? C.accent : rgba(C.light, .55));
    });
  });
}

/* ------------------------------------------------------------------ the topics: a wall of words
   Five rows of the topics, each in an order of its own, sliding in turn left and right; on every beat
   one topic lights up -- the copy of it nearest the middle of the frame at that beat, on whichever
   row has one nearest -- and rides on with its row. */
const TW = { size: 118, sep: 70, rows: 5 };
let TROWS = null;
function topicRows() {
  if (TROWS) return TROWS;
  const n = TOPICS.length, widths = TOPICS.map((w) => measure(w, { size: TW.size, wt: 900, ls: 1 }));
  const rows = Array.from({ length: TW.rows }, (_, r) => {
    const order = TOPICS.map((_, i) => i).sort((p, q) => rnd(p * 13 + r * 101 + 7) - rnd(q * 13 + r * 101 + 7));
    const off = []; let x = 0;
    for (const i of order) { off[i] = x; x += widths[i] + TW.sep; }
    return { order, off, total: x, dir: r % 2 ? 1 : -1, speed: 46 + r * 11, y: 300 + r * 162, solid: r % 2 === 1 };
  });
  const xOf = (row, tt) => (row.dir < 0 ? 0 : -row.total) + row.dir * (tt - T_WORDS) * row.speed;
  const end = QUOTE ? T_QUOTE : T_POSTER, hl = [];
  for (let k = 0; T_WORDS + .5 + k * BEAT < end - .5 && k < 24 && n; k++) {
    const ht = T_WORDS + .5 + k * BEAT, i = k % n, w = widths[i];
    let best = null;
    const last = hl.slice(-2).map((h) => h.row);
    rows.forEach((row, r) => {
      const x0 = xOf(row, ht) + row.off[i], m = Math.round((CX - w / 2 - x0) / row.total), x = x0 + m * row.total;
      const d = Math.abs(x + w / 2 - CX) + (last.includes(r) ? 700 : 0);
      if (!best || d < best.d) best = { d, r, x };
    });
    hl.push({ t: ht, topic: i, row: best.r, x: best.x });
  }
  const out = { rows, widths, xOf, hl };
  if (!document.fonts || document.fonts.check(font(TW.size, 900))) TROWS = out;
  return out;
}
function topicsScene(t) {
  const c = g(), t0 = T_WORDS, size = TW.size;
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  groundGrid(t);
  const title = String(D.topics_title || COPY.topics || ''), tz = fit(title, W - 240, 64, { wt: 900, ls: 2 }), tu = ease(t, t0 + .1, t0 + .5, E.out);
  clipRect(0, 70, W, 90, () => text(title, 120, 136 + (1 - tu) * 80, { size: tz, wt: 900, ls: 2, col: C.light }));
  if (!TOPICS.length) return;
  const TR = topicRows();
  TR.rows.forEach((row, r) => {
    const enter = (1 - ease(t, t0 + r * .06, t0 + .55 + r * .06, outSoft)) * row.dir * -W * .6;
    const base = TR.xOf(row, t) + enter, start = ((base % row.total) + row.total) % row.total - row.total;
    c.save(); c.font = font(size, 900); c.letterSpacing = '1px'; c.lineWidth = 2.2; c.textBaseline = 'alphabetic';
    for (let x0 = start; x0 < W; x0 += row.total) {
      for (const i of row.order) {
        const x = x0 + row.off[i], w = TR.widths[i]; if (x > W) break;
        if (x + w + TW.sep > 0) disc(x + w + TW.sep / 2, row.y - size * .34, 6, C.accentOnGround);
        if (x + w < 0) continue;
        let lit = 0;
        for (const h of TR.hl) {
          if (h.row !== r || h.topic !== i || t < h.t) continue;
          if (Math.abs(x - enter - (h.x + TR.xOf(row, t) - TR.xOf(row, h.t))) < 2) lit = Math.max(lit, clamp((h.t + 2.0 - t) / .5) * outBack(clamp((t - h.t) / .25)));
        }
        if (lit < 1) {
          if (row.solid) { c.fillStyle = C.groundLt; c.fillText(TOPICS[i], x, row.y); } else { c.strokeStyle = rgba(C.light, .34); c.strokeText(TOPICS[i], x, row.y); }
        }
        if (lit > 0) {
          c.save(); c.translate(x + w / 2, row.y - size * .36); c.scale(1 + .06 * lit, 1 + .06 * lit); c.translate(-(x + w / 2), -(row.y - size * .36));
          c.globalAlpha = clamp(lit * 1.6); c.fillStyle = C.accent; c.fillRect(x - 18, row.y - size * .8, w + 36, size * .96);
          c.fillStyle = C.inkOnAccent; c.fillText(TOPICS[i], x, row.y); c.restore();
        }
      }
    }
    c.restore();
  });
}

/* ------------------------------------------------------------------ the quote */
function quoteScene(t) {
  const c = g(), t0 = T_QUOTE;
  c.fillStyle = C.paper; c.fillRect(0, 0, W, H);
  c.save(); c.fillStyle = rgba(C.ground, .07);
  for (let y = 40; y < H; y += 40) for (let x = 40 - ((t * 10) % 40); x < W; x += 40) c.fillRect(x - 1.5, y - 1.5, 3, 3);
  c.restore();
  const push = 1 + .035 * E.sine(clamp((t - t0) / (T_POSTER - t0)));
  c.save(); c.translate(CX, CY); c.scale(push, push); c.translate(-CX, -CY);
  const qm = ease(t, t0 + .05, t0 + .45, outBack);
  if (qm > 0) SK.at(270, 640, 0, qm, () => text('“', 0, 0, { size: 620, wt: 900, col: C.accentOnPaper, align: 'center' }));
  const Q = fitWrap(QUOTE.text, 1320, 180, 3, { wt: 900 }), lh = Q.size * .98, y0 = 520 - (Q.lines.length * lh) / 2 + Q.size * .72;
  let wi = 0;
  Q.lines.forEach((ln, li) => {
    let x = 470; const y = y0 + li * lh;
    for (const w of ln.split(' ')) {
      const u = ease(t, t0 + .3 + wi * .07, t0 + .65 + wi * .07, outSoft), ww = measure(w + ' ', { size: Q.size, wt: 900 });
      if (u > 0) clipRect(x - 10, y - Q.size * .86, ww + 20, Q.size * 1.04, () => text(w, x, y + (1 - u) * Q.size, { size: Q.size, wt: 900, col: C.ground }));
      x += ww; wi++;
    }
  });
  if (QUOTE.by) {
    const by = '— ' + QUOTE.by, u = ease(t, t0 + .5 + wi * .07, t0 + .9 + wi * .07, E.out), y = y0 + (Q.lines.length - 1) * lh + 110;
    rrect(470, y - 34, 70 * u, 8, 4, C.accentOnPaper);
    if (u > 0) text(by, 560, y - 4 + (1 - u) * 20, { size: fit(by, 1200, 36, { wt: 700, fam: FONT.mono, ls: 3 }), wt: 700, fam: FONT.mono, ls: 3, col: C.inkSoft, alpha: u });
  }
  c.restore();
}

/* ------------------------------------------------------------------ no topics and no quote: every number at once */
function recapScene(t) {
  const c = g(), t0 = T_WORDS;
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  digitWall(t, .4);
  const cols = Math.min(4, Math.ceil(N / 2)), rows = Math.ceil(N / cols), cw = (W - 240) / cols, rh = 330;
  STATS.forEach((s, i) => {
    const x = 120 + (i % cols) * cw, y = CY - rows * rh / 2 + Math.floor(i / cols) * rh + rh / 2;
    numberBlock(s, x, y, cw - 60, t0 + .3 + i * .15, t, { max: 170, labMax: 44, noteMax: 0 });
  });
}

/* ------------------------------------------------------------------ the poster */
function posterScene(t) {
  const c = g(), t0 = T_POSTER;
  c.fillStyle = C.ground; c.fillRect(0, 0, W, H);
  digitWall(t, .45, { drift: 9 });
  const push = 1 + .025 * E.sine(clamp((t - t0 - 1) / 11));
  c.save(); c.translate(CX, CY); c.scale(push, push); c.translate(-CX, -CY);
  const lx = 120, colW = 980;
  drawLogo(true, lx, 170, 560, 110, 'left', ease(t, t0 + .1, t0 + .6, E.inOut));
  const kick = COPY.join ?? '', ku = ease(t, t0 + .3, t0 + .6, E.out);
  if (ku > 0 && kick) SK.alpha(ku, () => { rrect(lx, 284, 22, 22, 4, C.accentOnGround); text(kick, lx + 38, 304, { size: fit(kick, colW - 40, 28, { wt: 700, fam: FONT.mono, ls: 6 }), wt: 700, fam: FONT.mono, ls: 6, col: C.accentOnGround }); });
  const ds = String(EV.dates ?? ''), dz = fit(ds, colW, 205), cty = String(EV.city ?? ''), cz = fit(cty, colW, 205);
  const du = ease(t, t0 + .35, t0 + .85, outSoft), cu = ease(t, t0 + .55, t0 + 1.05, outSoft), y0 = 326;
  clipRect(0, y0, W, dz * .98, () => text(ds, lx - 6, y0 + dz * .76 + (1 - du) * dz, { size: dz, wt: 900, col: C.light }));
  const cy0 = y0 + dz + 8;
  clipRect(0, cy0, W, cz * .98, () => text(cty, lx - 6, cy0 + cz * .76 + (1 - cu) * cz, { size: cz, wt: 900, col: C.accentOnGround }));
  const ven = String(EV.venue ?? ''), vu = ease(t, t0 + .75, t0 + 1.15, E.out);
  if (vu > 0) clipRect(0, cy0 + cz + 4, W, 70, () => text(ven, lx, cy0 + cz + 50 + (1 - vu) * 60, { size: fit(ven, colW, 42, { wt: 800, fam: FONT.wide, ls: 2 }), wt: 800, fam: FONT.wide, ls: 2, col: C.soft }));
  // three of the numbers, a row each, ruled like a table
  const rx = 1230, rw = W - 120 - rx, rh = 186, ry = 236;
  POSTER_STATS.forEach((s, i) => {
    const y = ry + i * rh, u = ease(t, t0 + 1.0 + i * .25, t0 + 1.5 + i * .25, E.out);
    rrect(rx, y, rw * u, 3, 1.5, rgba(C.light, .3));
    const str = s.prefix + s.value + s.suffix, z = fit(str, rw, 118), preN = [...s.prefix].length, valN = [...s.value].length;
    odometer(str, rx, y + 22 + z * .72, t0 + 1.0 + i * .25, t, { size: z, d: .6, step: .05, colOf: (ch, k) => (k < preN || k >= preN + valN ? C.accentOnGround : C.light) });
    const lab = fitWrap(s.label, rw, 28, 2, { wt: 800, fam: FONT.wide, ls: 3 }), la = ease(t, t0 + 1.4 + i * .25, t0 + 1.7 + i * .25);
    lab.lines.forEach((ln, k) => text(ln, rx, y + 22 + z * .72 + 46 + k * lab.size * 1.25, { size: lab.size, wt: 800, fam: FONT.wide, ls: 3, col: C.soft, alpha: la }));
  });
  if (POSTER_STATS.length) rrect(rx, ry + POSTER_STATS.length * rh, rw * ease(t, t0 + 1.6, t0 + 2.0, E.out), 3, 1.5, rgba(C.light, .3));
  // the button and the address
  const cta = String(EV.cta ?? ''), bz = fit(cta, 560, 54), bwid = measure(cta, { size: bz, wt: 900, ls: 1 }) + 150, bh = 104, by = 912;
  const b = ease(t, t0 + 2.0, t0 + 2.45, outBack);
  if (b > 0 && cta) {
    SK.at(lx + bwid / 2, by, 0, b, () => {
      rrect(-bwid / 2, -bh / 2 + 8, bwid, bh, bh / 2, C.accentDk);
      rrect(-bwid / 2, -bh / 2, bwid, bh, bh / 2, C.accent);
      // a sheen across it every two bars
      const sh = ((t - t0 - 3) % BAR) / .7;
      if (t > t0 + 3 && sh < 1) { c.save(); SK.rrPath(-bwid / 2, -bh / 2, bwid, bh, bh / 2); c.clip(); const sx = lerp(-bwid / 2 - 80, bwid / 2 + 80, sh); c.fillStyle = rgba(C.light, .22); c.beginPath(); c.moveTo(sx - 30, -bh / 2); c.lineTo(sx + 30, -bh / 2); c.lineTo(sx - 10, bh / 2); c.lineTo(sx - 70, bh / 2); c.closePath(); c.fill(); c.restore(); }
      text(cta, -bwid / 2 + 52, bz * .36, { size: bz, wt: 900, ls: 1, col: C.inkOnAccent });
      const ax = bwid / 2 - 62 + Math.max(0, Math.sin((t - t0) * Math.PI * 2)) * 6, cc = g();
      cc.strokeStyle = C.inkOnAccent; cc.lineWidth = 9; cc.lineCap = 'round'; cc.lineJoin = 'round';
      cc.beginPath(); cc.moveTo(ax - 26, 0); cc.lineTo(ax + 22, 0); cc.moveTo(ax + 2, -20); cc.lineTo(ax + 24, 0); cc.lineTo(ax + 2, 20); cc.stroke();
    });
  }
  const url = String(EV.url ?? ''), un = Math.floor((t - t0 - 2.3) * 36);
  if (un > 0) text(url.slice(0, un), lx + (cta ? bwid + 44 : 0), by + 12, { size: fit(url, W - lx - bwid - 200, 36, { wt: 700, fam: FONT.mono, ls: 2 }), wt: 700, fam: FONT.mono, ls: 2, col: C.light });
  c.restore();
}

/* ------------------------------------------------------------------ the scenes and the cuts between them */
const SCENES = [
  { t0: 0, draw: openScene },
  { t0: T_WHEN, draw: whenScene, cut: 'slab', dir: 1 },
  { t0: T_WHERE, draw: whereScene, cut: 'whip', dir: -1 },
  ...CHAPTERS.map((ch) => ({ t0: ch.a, draw: (t) => chapterScene(ch, t), cut: 'slab', dir: ch.i % 2 ? -1 : 1 })),
  TOPICS.length ? { t0: T_WORDS, draw: topicsScene, cut: 'slab', dir: 1 } : QUOTE ? null : { t0: T_WORDS, draw: recapScene, cut: 'slab', dir: 1 },
  QUOTE ? { t0: T_QUOTE, draw: quoteScene, cut: 'slab', dir: -1 } : null,
  { t0: T_POSTER, draw: posterScene, cut: 'slab', dir: 1 },
].filter(Boolean);
const PRE = .3, POST = .22; // a cut runs from .3 s before its scene starts to .22 s after
function cut(t, a, b) {
  const c = g(), u = clamp((t - (b.t0 - PRE)) / (PRE + POST)), dir = b.dir ?? 1;
  if (b.cut === 'whip') {
    const e = E.inOut(u), smear = Math.sin(u * Math.PI) * 200;
    if (u < 1) SK.fx(() => a.draw(t), { key: 'wa', dx: dir * e * W, smear, angle: 0 });
    if (u > 0) SK.fx(() => b.draw(t), { key: 'wb', dx: dir * (e - 1) * W, smear, angle: 0 });
    return;
  }
  // a slab: a band of the accent and a thin one of the second sweep across; the next scene is behind them
  const B1 = W * .3, B2 = W * .05, edge = lerp(-(B1 + B2), W, E.inOut(u)) + (B1 + B2) * E.inOut(u); // the leading edge
  const lead = dir > 0 ? edge : W - edge, tail = dir > 0 ? lead - B1 - B2 : lead + B1 + B2;
  const rect = (x0, x1) => [Math.min(x0, x1), Math.max(x0, x1)];
  const [ax0, ax1] = dir > 0 ? rect(lead, W) : rect(0, lead), [bx0, bx1] = dir > 0 ? rect(0, tail) : rect(tail, W);
  if (ax1 - ax0 > 0) clipRect(ax0, 0, ax1 - ax0, H, () => a.draw(t));
  if (bx1 - bx0 > 0) clipRect(bx0, 0, bx1 - bx0, H, () => b.draw(t));
  const m = dir > 0 ? lead - B1 : lead + B1;
  c.fillStyle = C.accent; c.fillRect(Math.min(lead, m), 0, B1, H);
  c.fillStyle = C.second; c.fillRect(Math.min(m, tail), 0, B2, H);
}
function draw(t) {
  let i = SCENES.length - 1; while (i > 0 && SCENES[i].t0 > t) i--;
  const cur = SCENES[i], nx = SCENES[i + 1];
  if (nx && t > nx.t0 - PRE) cut(t, cur, nx);
  else if (i > 0 && t < cur.t0 + POST) cut(t, SCENES[i - 1], cur);
  else cur.draw(t);
  furniture(t);
}

/* ------------------------------------------------------------------ the sound
   Worked out from the clock above and from the content, so another set of numbers brings its own
   odometer ticks, another city its own arcs: `sketch-render.py --sound-data` writes score.json and
   sfx.json from these. The music is a 120 bpm groove in D minor (i-VI-III-VII): a counting
   arpeggio from the first frame, the drums in on the logo's lock, a brass stab on every cut, a
   one-beat fill into every number, a breakdown for the topics, the groove back for the poster and a
   last chord at LAST. */
const beatOf = (t) => t * BPM / 60;
const gf = (x) => String(+x.toPrecision(6)); // a number as Python's %g writes it
function scoreData() {
  const CHART = [ // per bar: bass root, its octave, the stab chord, the pad chord, the arpeggio's four notes
    ['D2', 'D3', 'D4+F4+A4', 'D3+F3+A3+C4', ['D5', 'F5', 'A5', 'C6']],
    ['Bb1', 'Bb2', 'D4+F4+Bb4', 'Bb2+D3+F3+A3', ['D5', 'F5', 'Bb5', 'A5']],
    ['F2', 'F3', 'C4+F4+A4', 'F3+A3+C4+E4', ['C5', 'F5', 'A5', 'E5']],
    ['C2', 'C3', 'C4+E4+G4', 'C3+E3+G3+D4', ['C5', 'E5', 'G5', 'D5']],
  ];
  const BARS = Math.round(DUR / BAR), FINAL = beatOf(LAST), lastBar = Math.floor(FINAL / 4);
  const breakdown = (bar) => bar >= T_WORDS / BAR && bar < T_WORDS / BAR + 3;
  const HITS = [LOCK, ...SCENES.slice(1).map((s) => s.t0), PIN_T].map(beatOf);
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', openhat: '..x...x...x...x.', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
  const FULL = { ...GROOVE, rim: '...o..o....o..o.' };
  const DRUMS = [];
  for (let bar = 0; bar < BARS; bar++) {
    const t = bar * BAR;
    let k;
    if (bar === 0) k = { kick: 'x...............', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
    else if (bar === 1) k = { kick: 'X...x...x...x...', clap: '....x.......x...', hat: 'o.o.o.o.o.o.o.o.' };
    else if (bar < T_WHEN / BAR) k = { ...GROOVE };
    else if (breakdown(bar)) k = { clap: '....x.......x...', hat: 'o.o.o.o.o.o.o.o.', shaker: '.o.o.o.o.o.o.o.o' };
    else if (bar === T_WORDS / BAR + 3) k = { kick: 'x.......x.......', clap: '....x.......x...', hat: 'o.o.o.o.o.o.o.o.' };
    else if (bar === T_WORDS / BAR + 4) k = { ...GROOVE };
    else if (bar === T_WORDS / BAR + 5) k = { ...GROOVE, snare: '....o.o.ooooxxxX' };
    else if (bar === lastBar) k = { kick: 'X...............', openhat: 'x...............' };
    else if (bar > lastBar) k = null;
    else k = { ...FULL };
    if (k) DRUMS.push([bar, k]);
  }
  // a one-beat fill into every cut that is not already rolled into
  const byBar = new Map(DRUMS);
  for (const s of SCENES.slice(1)) {
    const b = beatOf(s.t0) - 1, bar = Math.floor(b / 4), st = Math.round((b - bar * 4) * 4), k = byBar.get(bar);
    if (!k || k.snare) continue;
    const sn = '................'.split(''); sn[st] = 'o'; sn[st + 1] = 'x'; sn[st + 2] = 'x'; sn[st + 3] = 'X';
    k.snare = sn.join('');
  }
  const KIT_GAINS = { kick: 1.15, snare: .42, clap: .4, hat: .24, openhat: .15, shaker: .18, rim: .4 };
  const bass = [], sub = [], pad = [], keys = [], brass = [], arp = [];
  for (let bar = 0; bar < BARS; bar++) {
    if (bar >= lastBar) break;
    const [root, octv, stab, chord, tones] = CHART[bar % 4], b0 = bar * 4, bd = breakdown(bar);
    pad.push(`${gf(b0)} ${chord} 4 ${bar < 2 ? '.22' : '.3'}`);
    for (let k = 0; k < 16; k++) { // the counting arpeggio, sixteenths
      const n = tones[[0, 2, 1, 3, 2, 1, 3, 2][k % 8]];
      arp.push(`${gf(b0 + k / 4)} ${n} .22 ${(k % 4 === 0 ? .62 : k % 2 ? .38 : .48).toFixed(2)}`);
    }
    if (bar < 2) { sub.push(`${gf(b0)} ${root} 4 .6`); continue; }
    if (bd) { bass.push(`${gf(b0)} ${root} 4 .5`); sub.push(`${gf(b0)} ${root} 4 .7`); continue; }
    for (let k = 0; k < 8; k++) {
      const b = k * .5;
      bass.push(`${gf(b0 + b)} ${k % 2 ? octv : root} .42 ${(k % 2 ? .5 : .6).toFixed(2)}`);
      if (k % 2) sub.push(`${gf(b0 + b - .02)} ${root} .4 .8`);
    }
    if (bar >= T_WHEN / BAR) for (const k of [.5, 1.5, 2.5, 3.5]) keys.push(`${gf(b0 + k)} ${stab} .3 ${(k === 1.5 || k === 3.5 ? .32 : .24).toFixed(2)}`);
  }
  for (const b of HITS) brass.push(`${gf(b)} ${CHART[Math.floor(b / 4) % 4][2]} .9 .6`);
  bass.push(`${gf(FINAL)} D2 4 .7`); sub.push(`${gf(FINAL)} D2 4 .9`);
  pad.push(`${gf(FINAL)} D3+F3+A3+D4+A4 6 .5`); keys.push(`${gf(FINAL)} D4+F4+A4+D5 4 .45`);
  brass.push(`${gf(FINAL)} D4+F4+A4 3 .7`); arp.push(`${gf(FINAL)} D6 2 .5`);
  const events = [
    { inst: 'synth_bass_1', vel: .9, notes: bass.join('; '), humanize: false },
    { inst: 'sub_bass', vel: 1.0, notes: sub.join('; '), humanize: false },
    { inst: 'electric_piano_1', vel: .8, notes: keys.join('; ') },
    { inst: 'pad_3_polysynth', vel: .6, notes: pad.join('; ') },
    { inst: 'synth_brass_1', vel: .8, notes: brass.join('; ') },
    { inst: 'celesta', vel: .6, notes: arp.join('; '), humanize: false },
  ];
  DRUMS.forEach(([bar, kit]) => events.push({ type: 'drums', from: bar * 4, bars: 1, steps: 16, vel: .85, kit, gains: KIT_GAINS }));
  return {
    bpm: BPM, drum_gain: .62,
    instruments: {
      synth_bass_1: { g: .6, pan: 0, send: .04, rel: .12 },
      sub_bass: { g: .5, pan: 0, send: 0, rel: .05 },
      electric_piano_1: { g: .22, pan: -.22, send: .3, rel: .25 },
      pad_3_polysynth: { g: .16, pan: 0, send: .5, rel: .8, soft_attack: true },
      synth_brass_1: { g: .2, pan: .12, send: .35, rel: .35 },
      celesta: { g: .13, pan: .28, send: .35, rel: .2 },
    },
    events,
  };
}
function sfxData() {
  const cues = [], r = (x, n) => +x.toFixed(n);
  const add = (t, fx, db, args = {}, o = {}) => {
    const c = { t: r(Math.max(0, t), 3), fx, db };
    if (o.pan) c.pan = r(o.pan, 2);
    if (o.send !== undefined) c.send = o.send;
    if (fx === 'sample') Object.assign(c, args); else if (Object.keys(args).length) c.args = args;
    cues.push(c);
    return c;
  };
  const many = new Map(); // one cue holds every time a sound repeats with the same loudness and pan
  const again = (key, t, fx, db, args, pan = 0) => {
    if (t < 0 || t > DUR) return;
    let c = many.get(key);
    if (!c) { c = add(t, fx, db, args, { pan }); c.times = []; many.set(key, c); }
    c.times.push(r(t, 3));
  };
  const impact = (t, db = -14) => { add(t, 'boom', db, { sec: 1.0 }); add(t, 'crash', db - 14, { sec: 1.8 }, { send: .3 }); };
  // a number rolling up: the wheels' whirr, a tick as each one stops
  const odo = (str, t0, o = {}) => {
    const stops = odoStops(str, t0, o); if (!stops.length) return;
    add(t0, 'keys', o.db ?? -30, { sec: r(stops[stops.length - 1] - t0, 3), rate: 26 });
    for (const s of stops) again('settle' + (o.key ?? ''), s, 'tick', o.tick ?? -24, {});
  };

  // 1. the opening: the digits sweep in, lock, turn to pixels, give way to the logo; the headline
  add(0, 'boom', -16, { sec: .9 });
  add(0, 'shimmer', -27, { sec: 1.9, f0: 900, f1: 6500 });
  const M = mosaic(), cols = M ? M.cols : 50;
  for (let i = 0; i < cols; i += 2) { const p = Math.round((-.8 + 1.6 * i / cols) * 2) / 2; again('mos' + p, -.3 + i / cols * 1.7 + .1, 'click', -31, { sec: .006, lo: 2500, hi: 7500 }, p); }
  impact(LOCK, -12);
  add(LOCK + .2, 'crinkle', -27, { sec: .8, dens: 220 });
  add(3.0, 'shimmer', -22, { sec: .7, f0: 1500, f1: 7000 });
  add(3.05, 'pop', -22, { f0: 640, f1: 220, sec: .09 });
  odo(COPY.headline || '', HEAD_T, { d: .7 });
  add(HEAD_T, 'thunk', -18, { sec: .3 });
  add(TAG_T, 'swoosh_soft', -25, { sec: .7 });

  // the cuts: a whoosh into each, a hit on it
  for (const s of SCENES.slice(1)) {
    add(s.t0 - PRE - .05, 'whoosh', -15, { sec: PRE + POST + .1, f0: 300, f1: 4200, peak: .7, curve: 1.3 }, { pan: (s.dir ?? 1) * -.3 });
    add(s.t0, 'thunk', -17, { sec: .3 });
  }
  // 2. the calendar
  add(8.65, 'thunk', -19, { sec: .3 });
  add(8.0, 'swoosh_soft', -23, { sec: .6 });
  if (CAL) {
    for (let d = 1; d <= CAL.days; d += 3) again('day', 8.3 + (CAL.off + d - 1) * .012, 'tick', -33, {});
    for (let d = CAL.d0; d <= CAL.d1; d++) again('mark', CAL.markT(d), 'pop', -19, { f0: 760, f1: 260, sec: .09 });
    odo(String(CAL.span), 9.5, { d: .6 });
  }
  add(9.0, 'zip', -27, { sec: .3, f0: 600, f1: 2800 });
  // 3. the map: the pin falls and lands, the ripples, the place types out
  add(PIN_T - .45, 'zip', -22, { sec: .45, f0: 2600, f1: 400 });
  impact(PIN_T, -15);
  add(PIN_T, 'thunk', -13, { sec: .35 });
  for (let b = PIN_T + BEAT; b < T_NUMS - .3; b += BEAT) again('ripple', b, 'blip', -30, { f: 880, sec: .1 });
  add(PIN_T + .1, 'zip', -24, { sec: .35, f0: 500, f1: 2600 });
  if (HAS_GEO) add(PIN_T + .7, 'keys', -31, { sec: .6, rate: 30 });

  // 4. the numbers
  for (const ch of CHAPTERS) {
    const s = ch.s, a = ch.a, L = ch.b - a;
    impact(a, -16);
    odo(s.prefix + s.value + s.suffix, ch.t0);
    add(ch.t0 + .55, 'zip', -25, { sec: .3, f0: 600, f1: 3000 });
    if (s.note) add(ch.t0 + 1.05, 'keys', -31, { sec: r(Math.min(1.6, s.note.length / 40), 2), rate: 30 });
    if (s.kind === 'people') { add(a + .15, 'crinkle', -21, { sec: 1.8, dens: 420 }); add(a + .3, 'shimmer', -27, { sec: 1.6, f0: 600, f1: 5000 }); }
    else if (s.kind === 'countries') { const V = worldView(ch); V.arcs.forEach((_, i) => { const t0 = V.arcT(i); again('arc', t0, 'zip', -32, { sec: .5, f0: 900, f1: 3200 }, i % 2 ? .3 : -.3); again('land', t0 + .85, 'blip', -30, { f: 1320, sec: .07 }); }); }
    else if (s.kind === 'companies') for (let k = 0; k <= 12; k += 2) again('rise', a + .3 + k * .07, 'thunk', -25, { sec: .25 });
    else if (s.kind === 'network') for (let k = 0; k < 10; k++) again('node', a + .3 + k * .12, 'pop', -29, { f0: 900, f1: 320, sec: .06 }, (k % 5 - 2) * .2);
    else if (s.kind === 'speakers') for (let k = 0; k < 9; k++) again('flip', a + .3 + k * .07, 'click', -23, { sec: .01, lo: 1200, hi: 5000 }, (k / 8 - .5) * .8);
    else if (s.kind === 'sessions') { for (let k = 0; k < 24; k += 3) again('seg', a + .35 + k * .065, 'tick', -26, {}); for (let b = a + .3 + BAR; b < ch.b - .3; b += BAR) again('round', b, 'clink', -30, { sec: .5 }); }
    else if (s.kind === 'years') { for (let k = 0; k < 8; k++) again('year', a + .3 + k * .2, 'tick', -25, {}); add(a + 1.9, 'chime', -24, { sec: 1.2 }); }
    else if (s.kind === 'media') for (let f = 0; f < 46; f += 2) again('flash', a + .25 + Math.pow(rnd(f * 3 + 1), 1.5) * (L - .7), 'click', -22, { sec: .012, lo: 2500, hi: 9000 }, ((rnd(f * 5 + 2) - .5) * 1.2));
    else add(a, 'boom', -15, { sec: 1.2 });
  }
  // 5. the topics, the quote
  if (TOPICS.length) {
    const end = QUOTE ? T_QUOTE : T_POSTER;
    for (let k = 0; T_WORDS + .5 + k * BEAT < end - .5 && k < 24; k++) again('topic', T_WORDS + .5 + k * BEAT, 'pop', -24, { f0: 700, f1: 240, sec: .08 });
  }
  if (QUOTE) { add(T_QUOTE + .05, 'thunk', -17, { sec: .35 }); add(T_QUOTE + .3, 'swoosh_soft', -24, { sec: .6 }); }
  // 6. the poster
  impact(T_POSTER, -13);
  add(T_POSTER + .1, 'shimmer', -25, { sec: .6, f0: 1200, f1: 6000 });
  for (let k = 0; k < 3; k++) again('line', T_POSTER + .35 + k * .2, 'thunk', -23, { sec: .22 });
  POSTER_STATS.forEach((s, i) => odo(s.prefix + s.value + s.suffix, T_POSTER + 1.0 + i * .25, { d: .6, step: .05, db: -33, tick: -28, key: 'p' }));
  add(T_POSTER + 2.0, 'pop', -17, { f0: 520, f1: 170, sec: .12 });
  add(T_POSTER + 2.05, 'blip', -25, { f: 988, sec: .1 });
  add(T_POSTER + 2.3, 'keys', -30, { sec: .5, rate: 30 });
  add(LAST, 'crash', -20, { sec: 2.6 }, { send: .4 });
  add(LAST, 'boom', -17, { sec: 1.4 });
  return cues.sort((p, q) => p.t - q.t);
}

SK.film({
  duration: DUR,
  camera: SK.camera([[0, [W / 2, H / 2, 1]]]),
  handheld: false,
  speedLines: false,
  fadeOut: 0,
  draw,
  sound: { score: scoreData, sfx: sfxData },
});
