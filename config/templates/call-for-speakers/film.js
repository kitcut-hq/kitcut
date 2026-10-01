// For: developers and practitioners who follow tech conferences -- an event's call for speakers; anticipation, then an open invitation
/* A call for speakers in 90 s, with no narration: the music carries it. This film is a template: every
   word, date, colour and logo is in content.json (SK.DATA.content) and nothing of the event is in the
   code, so another event is another content.json and its logo. 16:9, 1920 x 1080.

   The story is the empty stage waiting for you: a dark stage where a spotlight finds an empty microphone
   and a marquee sign lights up with the call; a speaker's badge swinging on its lanyard, the name field
   typing YOU; the tracks as slides on the big screen, then all of them at once; the formats as stage
   timers that start to run; a backstage pass with the perks stamped beside it; the key dates printed on a
   run-of-show sheet taped to the floor, today and the deadline marked on it in marker; the days left,
   counted down on the screen; and the stage again, the sign now asking for your talk.

   The clock (T, in bars of the 120 bpm score) is the one home of its timing: the score and every sound
   cue are worked out from it and from the content at the bottom of this file (SK.film({sound})), so
   `sketch-render.py --sound-data` writes a score.json and sfx.json that fit whatever the content is.
   The content never moves the clock: more topics, formats or dates fill the same bars.
*/
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, TAU = SK.TAU, rnd = SK.rnd;
const CX = W / 2, CY = H / 2;
const D = SK.DATA.content;
const LANG = D.lang || 'en';
const up = (s) => String(s ?? '').toLocaleUpperCase(LANG);
const pad2 = (n) => String(n).padStart(2, '0');

/* ------------------------------------------------------------------ the palette
   Three brand colours are enough -- ground (the dark the stage is made of), accent and second; every
   shade is worked out from them unless content.json names it. What sits on what is chosen by contrast,
   so a light accent (type on it is the ground) and a dark one (type on it is light) both read. */
function rgbOf(hex) { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function hslOf(hex) {
  const [r, g2, b] = rgbOf(hex).map((v) => v / 255), mx = Math.max(r, g2, b), mn = Math.min(r, g2, b), l = (mx + mn) / 2;
  if (mx === mn) return [0, 0, l];
  const d = mx - mn, s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
  const h = mx === r ? (g2 - b) / d + (g2 < b ? 6 : 0) : mx === g2 ? (b - r) / d + 2 : (r - g2) / d + 4;
  return [h / 6, s, l];
}
const L = (hex) => hslOf(hex)[2];
function withL(hex, l, sk = 1) { // the colour at lightness l (0..1), its saturation times sk
  const [h, s0] = hslOf(hex), s = clamp(s0 * sk), LL = clamp(l);
  const q = LL < .5 ? LL * (1 + s) : LL + s - LL * s, p = 2 * LL - q;
  const ch = (x) => { x = (x + 1) % 1; return x < 1 / 6 ? p + (q - p) * 6 * x : x < .5 ? q : x < 2 / 3 ? p + (q - p) * (2 / 3 - x) * 6 : p; };
  return '#' + [ch(h + 1 / 3), ch(h), ch(h - 1 / 3)].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
}
function mixHex(a, b, u) {
  const x = rgbOf(a), y = rgbOf(b);
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * u).toString(16).padStart(2, '0')).join('');
}
function contrast(a, b) {
  const lum = (hex) => { const [r, g2, b2] = rgbOf(hex).map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * r + .7152 * g2 + .0722 * b2; };
  const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
const rgba = (hex, a) => `rgba(${rgbOf(hex).join(',')},${a})`;
const C = (() => {
  const p = D.palette || {};
  const light = p.light ?? '#F4F1EC', paper = p.paper ?? '#FBF8F2';
  let ground = p.ground ?? '#151A33';
  // light type sits on the ground everywhere: a ground too light for it is darkened until it reads
  while (contrast(ground, light) < 10 && L(ground) > .03) ground = withL(ground, L(ground) - .02);
  const g0 = L(ground), accent = p.accent ?? '#F2B33D', second = p.second ?? accent;
  const d = {
    light, paper, accent, second,
    groundDk: withL(ground, g0 * .55), groundMid: withL(ground, g0 + .07), groundLt: withL(ground, g0 + .16),
    groundHi: withL(ground, g0 + .3, .7), soft: withL(ground, .76, .35),
    accentDk: withL(accent, L(accent) * .72),
    inkSoft: mixHex(ground, paper, .42),
  };
  // a colour that glows on the dark: the accent where it reads on the ground, else a lighter accent
  d.glow = contrast(accent, ground) >= 3 ? accent : withL(accent, Math.max(.7, L(accent)));
  d.glow2 = contrast(second, ground) >= 3 ? second : withL(second, Math.max(.68, L(second)));
  d.onAccent = contrast(accent, ground) >= contrast(accent, light) ? ground : light;
  d.onSecond = contrast(second, ground) >= contrast(second, light) ? ground : light;
  // a marker on paper: the accent where it reads on paper, else the second colour, else the ground
  d.marker = [accent, second].find((x) => contrast(x, paper) >= 3) ?? ground;
  d.beam = mixHex(light, d.glow, .28);
  d.metal = mixHex(light, ground, .5);
  d.dark = withL(ground, Math.min(.07, g0 * .5));
  return { ...d, ...p, ground };
})();
SK.setStyle('clean', { grain: .35, vignette: .3, handheld: 0, vignetteRGB: rgbOf(C.groundDk).join(',') });
Object.assign(SK.C, { paper: C.ground, text: C.light, textSoft: C.soft, accent: C.accent, accentText: C.accent, ink: C.ground });
const F = { cond: '"Sofia Sans Condensed"', sans: '"Sofia Sans"', mono: '"IBM Plex Mono"', hand: '"Caveat"', ...(D.fonts || {}) };

/* ------------------------------------------------------------------ the words */
const EV = D.event || {}, CFP = D.cfp || {}, COPY = D.copy || {};
const TOPICS = (D.topics || []).map((x) => (typeof x === 'string' ? { name: x } : x)).filter((x) => x && x.name).slice(0, 15);
const FORMATS = (D.formats || []).filter((x) => x && x.name).slice(0, 5);
const PERKS = (D.perks || []).filter(Boolean);
// the stamps: the event's own perks, and where it states fewer than three, the reasons every speaker has
const STAMPS = [...PERKS, ...(COPY.reasons || [])].slice(0, Math.min(5, Math.max(3, PERKS.length)));
const DATES = (D.timeline || []).filter((x) => x && (x.label || x.date)).slice(0, 6);
const PLACE = [EV.city, EV.country].filter(Boolean).join(', ');
const EVLINE = [EV.dates, PLACE].filter(Boolean).join('  ·  ');

/* the days left: from the content's own "today" (cfp.as_of) to the deadline, both yyyy-mm-dd. Over 99
   days it counts weeks; on the day itself it says so; with no dates, or past them, it shows the date. */
const dayN = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / 864e5 : null; };
const TODAY = dayN(CFP.as_of), DUE = dayN(CFP.deadline);
const DAYS = TODAY !== null && DUE !== null ? DUE - TODAY : null;
const plural = (forms, n) => {
  if (typeof forms === 'string') return forms;
  let k = 'other'; try { k = new Intl.PluralRules(LANG).select(n); } catch (e) { /* an unknown language: other */ }
  return forms?.[k] ?? forms?.other ?? '';
};
const COUNT = DAYS === null || DAYS < 0 ? null
  : DAYS === 0 ? { n: 0, unit: COPY.last_day || '' }
    : DAYS > 99 ? { n: Math.floor(DAYS / 7), unit: plural(COPY.weeks_left, Math.floor(DAYS / 7)) }
      : { n: DAYS, unit: plural(COPY.left, DAYS) };

/* ------------------------------------------------------------------ the clock (120 bpm: a beat .5 s, a bar 2 s) */
const BPM = 120, BEAT = 60 / BPM, BAR = 4 * BEAT;
const bar = (b, k = 0) => (b * 4 + k) * BEAT;
const T = {
  land: bar(1),               // 2.0  the spotlight finds the microphone
  screen: bar(1, 2),          // 3.0  the big screen comes on
  sign: bar(2),               // 4.0  the marquee lands (it flies in for half a second before)
  flash: bar(4),              // 8.0  white: the badge drops
  type: bar(5),               // 10.0 the name field types
  s3: bar(8),                 // 16.0 the slides: what they want to hear
  slides: bar(9),             // 18.0 the first topic's slide; one a bar, up to four
  s4: bar(16),                // 32.0 stage time
  timers: bar(16, 1),         // 32.5 the first timer lands; one a beat
  run: bar(18),               // 36.0 the timers start to run
  curtain: bar(21),           // 42.0 the curtain: backstage
  stamps: bar(22),            // 44.0 the first stamp; one a bar
  s6: bar(27),                // 54.0 the key dates
  rows: bar(27, 1),           // 54.5 the first row; one a beat
  marks: bar(29),             // 58.0 the marker: past dates struck, today, the deadline circled
  push: bar(30),              // 60.0 the camera starts to push into the deadline
  s7: bar(34),                // 68.0 the days left
  count: bar(36),             // 72.0 ... counted down to here
  s8: bar(38),                // 76.0 the stage again
  sign2: bar(38, 2),          // 77.0 the sign lands again, asking for the talk
  lip: bar(39, 2),            // 79.0 the deadline lights along the stage's edge
  last: bar(43),              // 86.0 the last chord
};
const DUR = 90;
const KS = Math.min(4, TOPICS.length);   // the topics that get a slide of their own
const WALL = T.slides + KS * BAR;         // then every topic at once

/* ------------------------------------------------------------------ small helpers */
const g = () => SK.ctx();
const ease = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
const back = (k) => (u) => { const c3 = k + 1; return 1 + c3 * Math.pow(u - 1, 3) + k * Math.pow(u - 1, 2); };
const outBack = back(1.6), outSoft = back(.8);
function font(size, wt = 900, fam = F.cond) { return `${wt} ${size}px ${fam}`; }
/** text at x, y (alphabetic baseline). o: size, wt, fam, col, align, ls (px) */
function text(str, x, y, o = {}) {
  const c = g(); c.save();
  c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? F.cond);
  c.textAlign = o.align ?? 'left'; c.textBaseline = 'alphabetic';
  c.letterSpacing = (o.ls ?? 0) + 'px';
  c.fillStyle = o.col ?? C.light;
  if (o.glow) { c.shadowColor = o.glow; c.shadowBlur = o.blur ?? 24; }
  c.fillText(str, x, y); c.restore();
}
function measure(str, o = {}) {
  const c = g(); c.save(); c.font = font(o.size ?? 60, o.wt ?? 900, o.fam ?? F.cond); c.letterSpacing = (o.ls ?? 0) + 'px';
  const w = c.measureText(str).width; c.restore(); return w;
}
/** the largest size up to max at which str fits in width */
function fit(str, width, max, o = {}) { return Math.min(max, max * width / Math.max(1, measure(str, { ...o, size: max }))); }
/** str in at most n lines that fit width (and height h, if given, at lh x size a line), at the largest
    size up to max; two lines are split as evenly as they fit. {lines, size} */
function wrapFit(str, width, max, n = 2, o = {}) {
  const words = String(str ?? '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return { lines: [], size: max };
  const ls = o.ls ?? 0, base = { ...o, size: 100, ls: 0 }, lh = o.lh ?? 1;
  const ww = words.map((w) => measure(w, base) / 100), sp = measure(' ', base) / 100, cnt = words.map((w) => [...w].length);
  const lineW = (i, j, s) => { let w = 0, ch = 0; for (let k = i; k < j; k++) { w += ww[k] * s; ch += cnt[k]; if (k > i) { w += sp * s; ch++; } } return w + ls * ch; };
  for (let s = max; s >= 6; s *= .97) {
    const lines = []; let i = 0;
    while (i < words.length) { let j = i + 1; while (j < words.length && lineW(i, j + 1, s) <= width) j++; lines.push([i, j]); i = j; }
    if (lines.length > n || lines.some(([a, b]) => lineW(a, b, s) > width)) continue;
    if (o.h && lines.length * s * lh > o.h) continue;
    let out = lines;
    if (lines.length === 2) {
      let bi = lines[0][1], bw = Infinity;
      for (let k = 1; k < words.length; k++) { const m = Math.max(lineW(0, k, s), lineW(k, words.length, s)); if (m <= width && m < bw - .5) { bw = m; bi = k; } }
      out = [[0, bi], [bi, words.length]];
    }
    return { lines: out.map(([a, b]) => words.slice(a, b).join(' ')), size: s };
  }
  const all = words.join(' ');
  return { lines: [all], size: fit(all, width, max, o) };
}
function clipRect(x, y, w, h, fn) { const c = g(); c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); fn(); c.restore(); }
function rrect(x, y, w, h, r, fill) { const c = g(); SK.rrPath(x, y, w, h, r); c.fillStyle = fill; c.fill(); }
function poly(pts, fill) { const c = g(); c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); for (const p of pts.slice(1)) c.lineTo(p[0], p[1]); c.closePath(); c.fillStyle = fill; c.fill(); }
const withT = (x, y, rot, s, fn) => SK.at(x, y, rot, s, fn);
/** a line of type that rises into place from under its own baseline (a mask), at t0 over d */
function rise(str, x, y, o, t, t0, d = .42) {
  const u = ease(t, t0, t0 + d, E.out); if (u <= 0) return;
  const s = o.size ?? 60, w = measure(str, o) + 40, x0 = (o.align === 'center' ? x - w / 2 : o.align === 'right' ? x - w : x) - 20;
  clipRect(x0, y - s * 1.05, w + 40, s * 1.32, () => text(str, x, y + (1 - u) * s * 1.1, o));
}

/* the logo (content.logo): "image" reads on light grounds, "light" on dark ones; either may stand in for
   the other. Without a logo the event's name is set in type instead. */
const LG = D.logo || {};
const logoImg = (light) => SK.IMG[(light ? LG.light : LG.image) || LG.image || LG.light];
function logo(light, cx, cy, w, h, o = {}) {
  const im = logoImg(light);
  if (!im) {
    const r = wrapFit(up(EV.name), w, Math.min(h * .45, 120), 2, { wt: 900 });
    r.lines.forEach((ln, i) => text(ln, cx, cy - (r.lines.length - 1) * r.size * .5 + i * r.size + r.size * .35, { size: r.size, wt: 900, col: o.col ?? (light ? C.light : C.ground), align: 'center' }));
    return;
  }
  const s = Math.min(w / im.width, h / im.height);
  g().drawImage(im, cx - im.width * s / 2, cy - im.height * s / 2, im.width * s, im.height * s);
}

/* ------------------------------------------------------------------ sprites (made once; every frame is still a function of t) */
const SPR = {};
function sprite(key, w, h, fn) {
  if (SPR[key]) return SPR[key];
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h; fn(cv.getContext('2d'), w, h);
  return (SPR[key] = cv);
}
const bulb = (col) => sprite('bulb' + col, 64, 64, (x) => {
  const gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, '#FFFFFF'); gr.addColorStop(.2, col); gr.addColorStop(.45, rgba(col, .38)); gr.addColorStop(1, rgba(col, 0));
  x.fillStyle = gr; x.fillRect(0, 0, 64, 64);
});
const led = () => sprite('led', 6, 6, (x) => { x.fillStyle = 'rgba(0,0,0,.55)'; x.fillRect(5, 0, 1, 6); x.fillRect(0, 5, 6, 1); });

/* ------------------------------------------------------------------ the stage
   World units are the pixels of the wide shot; the camera (stageCam) moves over it. */
const SCR = { x: 360, y: 80, w: 1200, h: 600 };     // the big screen at the back
const FL = { back: 700, lip: 1000 };                  // the floor, from the back wall to the front edge
const MIC = { x: CX, base: 984, head: 830 };          // the empty microphone, front and centre
const SIGN = { cx: CX, cy: 615, w: 1120, h: 240 };    // the marquee, flown in on two cables
const SPOT = [1250, 58], SPOTL = [330, 58], SPOTR = [1590, 58]; // fixtures on the truss
function stageCam(cam, fn) { const c = g(); c.save(); c.translate(CX, CY); c.scale(cam[2], cam[2]); c.translate(-cam[0], -cam[1]); fn(); c.restore(); }

function backWall() {
  const c = g(), gr = c.createLinearGradient(0, -100, 0, FL.back);
  gr.addColorStop(0, C.groundDk); gr.addColorStop(1, C.ground);
  c.fillStyle = gr; c.fillRect(-200, -200, W + 400, FL.back + 200);
  c.strokeStyle = rgba(C.groundMid, .55); c.lineWidth = 2; c.beginPath();
  for (let x = -40; x < W + 200; x += 160) { c.moveTo(x, -200); c.lineTo(x, FL.back); }
  c.stroke();
}
function drapes() {
  const c = g(), col = mixHex(C.groundDk, C.second, .12), l0 = L(col);
  const dk = withL(col, l0 * .5), lt = withL(col, Math.min(.3, l0 * 1.7 + .02));
  for (const x0 of [-60, W - 250]) {
    for (let i = 0; i < 9; i++) {
      const x = x0 + i * 34, gr = c.createLinearGradient(x, 0, x + 35, 0);
      gr.addColorStop(0, dk); gr.addColorStop(.5, lt); gr.addColorStop(1, dk);
      c.fillStyle = gr; c.fillRect(x, -200, 35, FL.lip + 200);
    }
  }
}
function floorBoards() {
  const c = g(), gr = c.createLinearGradient(0, FL.back, 0, FL.lip);
  gr.addColorStop(0, withL(C.ground, L(C.ground) * .75)); gr.addColorStop(1, C.groundMid);
  c.fillStyle = gr; c.fillRect(-200, FL.back, W + 400, FL.lip - FL.back);
  c.strokeStyle = rgba(C.groundDk, .6); c.lineWidth = 2; c.beginPath();
  const vy = 120, u = (FL.back - vy) / (FL.lip - vy);
  for (let k = -18; k <= 18; k++) { const xl = CX + k * 110; c.moveTo(CX + (xl - CX) * u, FL.back); c.lineTo(xl, FL.lip); }
  for (let j = 1; j < 6; j++) { const y = FL.back + (FL.lip - FL.back) * Math.pow(j / 6, 1.5); c.moveTo(-200, y); c.lineTo(W + 200, y); }
  c.stroke();
}
function lipFace() { // the stage's front edge, its fascia a strip of LEDs
  const c = g();
  c.fillStyle = C.dark; c.fillRect(-200, FL.lip, W + 400, 300);
  c.fillStyle = rgba(C.metal, .55); c.fillRect(-200, FL.lip, W + 400, 4);
}
function truss() {
  const c = g();
  c.save(); c.strokeStyle = withL(C.ground, Math.min(.42, L(C.ground) + .2), .4); c.lineWidth = 6;
  c.beginPath(); for (const y of [12, 50]) { c.moveTo(-200, y); c.lineTo(W + 200, y); } c.stroke();
  c.lineWidth = 3; c.beginPath();
  for (let x = -200, k = 0; x < W + 200; x += 38, k++) { c.moveTo(x, k % 2 ? 12 : 50); c.lineTo(x + 38, k % 2 ? 50 : 12); }
  c.stroke(); c.restore();
}
/** a fixture hanging from the truss at x, turned towards its target; returns its lens */
function fixture(P, aim, on) {
  const c = g(), a = Math.atan2(aim[1] - P[1], aim[0] - P[0]) - Math.PI / 2;
  withT(P[0], P[1], a, 1, () => {
    rrect(-19, -4, 38, 50, 9, C.dark);
    c.fillStyle = rgba(C.metal, .35); c.fillRect(-19, -4, 3, 50);
    c.beginPath(); c.ellipse(0, 46, 15, 6, 0, 0, TAU); c.fillStyle = on > 0 ? mixHex(C.groundLt, '#FFFFFF', clamp(on)) : C.groundLt; c.fill();
  });
  return [P[0] - Math.sin(a) * 46, P[1] + Math.cos(a) * 46];
}
/** a beam from a lens to a pool of light of radius r at T, with haze drifting through it */
function beam(P, Tg, r, a, col = C.beam, seed = 1, t = 0) {
  if (a <= 0) return;
  const c = g();
  c.save(); c.globalCompositeOperation = 'screen';
  // the cone: faint where it crosses the screen, so the light never washes out its words
  for (const inScreen of [false, true]) {
    c.save(); c.beginPath(); c.rect(SCR.x, SCR.y, SCR.w, SCR.h);
    if (!inScreen) { c.rect(-400, -400, W + 800, H + 800); c.clip('evenodd'); } else c.clip();
    const af = a * (inScreen ? .3 : 1);
    for (const [k, al] of [[1.25, .07], [1, .16]]) {
      const gr = c.createLinearGradient(P[0], P[1], Tg[0], Tg[1]);
      gr.addColorStop(0, rgba(col, Math.min(1, al * 2.6 * af))); gr.addColorStop(.3, rgba(col, al * 1.2 * af)); gr.addColorStop(1, rgba(col, al * af));
      c.fillStyle = gr; c.beginPath();
      c.moveTo(P[0] - 10 * k, P[1]); c.lineTo(P[0] + 10 * k, P[1]); c.lineTo(Tg[0] + r * k, Tg[1]);
      c.ellipse(Tg[0], Tg[1], r * k, r * k * .26, 0, 0, Math.PI); c.lineTo(Tg[0] - r * k, Tg[1]); c.closePath(); c.fill();
    }
    c.restore();
  }
  // the pool on the floor
  c.save(); c.translate(Tg[0], Tg[1]); c.scale(1, .27);
  const pg = c.createRadialGradient(0, 0, 0, 0, 0, r * 1.25);
  pg.addColorStop(0, rgba(col, .6 * a)); pg.addColorStop(.7, rgba(col, .3 * a)); pg.addColorStop(1, rgba(col, 0));
  c.fillStyle = pg; c.beginPath(); c.arc(0, 0, r * 1.25, 0, TAU); c.fill(); c.restore();
  // haze: motes drifting in the cone
  c.fillStyle = rgba('#FFFFFF', .5 * a);
  for (let i = 0; i < 46; i++) {
    const u = (rnd(seed * 97 + i) + t * (.012 + rnd(seed * 31 + i) * .02)) % 1;
    const v = (rnd(seed * 53 + i * 3) * 2 - 1) * .92 + Math.sin(t * .7 + i) * .04;
    const x = lerp(P[0], Tg[0], u) + v * lerp(10, r, u), y = lerp(P[1], Tg[1], u) + Math.sin(t * .9 + i * 2) * 6;
    if (x > SCR.x && x < SCR.x + SCR.w && y > SCR.y && y < SCR.y + SCR.h) continue;
    const s = .9 + rnd(seed * 7 + i) * 1.8, tw = .4 + .6 * Math.abs(Math.sin(t * 1.3 + i * 1.7));
    c.globalAlpha = tw * a * .8; c.beginPath(); c.arc(x, y, s, 0, TAU); c.fill();
  }
  c.restore();
}
function micStand(lit) {
  const c = g(), x = MIC.x, b = MIC.base, h = MIC.head, dark = C.dark, rim = rgba(C.beam, .2 + .75 * lit);
  // the round base
  c.beginPath(); c.ellipse(x, b, 66, 13, 0, 0, TAU); c.fillStyle = dark; c.fill();
  c.strokeStyle = rim; c.lineWidth = 3; c.beginPath(); c.ellipse(x, b - 2, 62, 10, 0, Math.PI * 1.05, Math.PI * 1.95); c.stroke();
  // the pole and its clutch
  c.fillStyle = dark; c.fillRect(x - 5, h + 40, 10, b - h - 40);
  rrect(x - 9, h + 120, 18, 26, 4, dark);
  c.fillStyle = rim; c.fillRect(x + 3, h + 40, 2.5, b - h - 46);
  // the microphone in its clip, turned a little towards the house
  withT(x, h + 44, -.2, 1, () => {
    rrect(-8, -18, 16, 26, 4, dark);
    poly([[-12, -18], [12, -18], [8, -104], [-8, -104]], dark);
    c.fillStyle = rim; c.fillRect(6, -100, 3, 80);
    c.beginPath(); c.ellipse(0, -124, 22, 27, 0, 0, TAU); c.fillStyle = withL(C.ground, .1); c.fill();
    c.save(); c.clip();
    c.strokeStyle = rgba(C.metal, .35); c.lineWidth = 1.5; c.beginPath();
    for (let k = -30; k <= 30; k += 7) { c.moveTo(k - 30, -160); c.lineTo(k + 30, -90); c.moveTo(k + 30, -160); c.lineTo(k - 30, -90); }
    c.stroke(); c.restore();
    c.strokeStyle = rim; c.lineWidth = 3.5; c.beginPath(); c.ellipse(0, -124, 22, 27, 0, -1.3, .7); c.stroke();
    if (lit > 0) { c.fillStyle = rgba('#FFFFFF', .55 * lit); c.beginPath(); c.ellipse(8, -136, 6, 8, -.5, 0, TAU); c.fill(); }
  });
}

/* the marquee: a panel on two cables, bulbs round its edge that chase, its words lit a letter at a time */
function signLayout(str) { return wrapFit(up(str), SIGN.w - 170, 150, 2, { wt: 900, ls: 4, h: SIGN.h - 96, lh: .98 }); }
function signLetters(str) { return [...up(str)].filter((ch) => ch.trim()).length; }
const LETTER = (n) => Math.min(.12, 1.6 / Math.max(1, n)); // seconds between letters lighting
function signBulbs() {
  const w = SIGN.w, h = SIGN.h, m = 22, pts = [];
  const nx = Math.round((w - 2 * m) / 40), ny = Math.round((h - 2 * m) / 40);
  for (let i = 0; i < nx; i++) pts.push([-w / 2 + m + i * (w - 2 * m) / nx, -h / 2 + m]);
  for (let i = 0; i < ny; i++) pts.push([w / 2 - m, -h / 2 + m + i * (h - 2 * m) / ny]);
  for (let i = 0; i < nx; i++) pts.push([w / 2 - m - i * (w - 2 * m) / nx, h / 2 - m]);
  for (let i = 0; i < ny; i++) pts.push([-w / 2 + m, h / 2 - m - i * (h - 2 * m) / ny]);
  return pts;
}
const BULBS = signBulbs();
/** o: str, land (it lands then; flies in for .5 s before), lit (letters start), house (0..1), flash (0..1) */
function marquee(t, o) {
  const fly = ease(t, o.land - .5, o.land, outSoft); if (fly <= 0) return;
  const c = g(), tl = t - o.land, sway = tl > 0 ? .025 * Math.exp(-tl * 2.4) * Math.sin(tl * 8) : 0;
  const y = SIGN.cy + lerp(-720, 0, fly), w = SIGN.w, h = SIGN.h;
  // the cables
  c.strokeStyle = rgba(C.metal, .38); c.lineWidth = 2; c.beginPath();
  for (const k of [-1, 1]) {
    const lx = k * w * .36, ly = -h / 2;
    c.moveTo(SIGN.cx + lx, -200); c.lineTo(SIGN.cx + lx * Math.cos(sway) - ly * Math.sin(sway), y + lx * Math.sin(sway) + ly * Math.cos(sway));
  }
  c.stroke();
  const r = signLayout(o.str), n = signLetters(o.str), step = LETTER(n), allOn = o.lit + n * step + .1;
  withT(SIGN.cx, y, sway, 1, () => {
    c.save(); c.shadowColor = 'rgba(0,0,0,.55)'; c.shadowBlur = 40; c.shadowOffsetY = 20;
    rrect(-w / 2, -h / 2, w, h, 26, mixHex(C.metal, C.dark, .45)); c.restore();
    rrect(-w / 2 + 6, -h / 2 + 6, w - 12, h - 12, 22, C.dark);
    rrect(-w / 2 + 44, -h / 2 + 44, w - 88, h - 88, 12, withL(C.ground, L(C.ground) * .6));
    // the bulbs
    const on = t >= allOn, fl = o.flash ?? 0;
    const spr = bulb(mixHex(C.light, C.glow, .45));
    BULBS.forEach(([bx, by], i) => {
      c.fillStyle = C.groundMid; c.beginPath(); c.arc(bx, by, 7, 0, TAU); c.fill();
      if (!on && fl <= 0) return;
      const chase = ((i + Math.floor(t * 9)) % 3 === 0) ? 1 : .38, b = Math.max(on ? chase : 0, fl);
      c.globalAlpha = b; c.drawImage(spr, bx - 26, by - 26, 52, 52); c.globalAlpha = 1;
    });
    // the words, a letter at a time: a flicker, then on
    const s = r.size, lh = s * .98, y0 = -(r.lines.length - 1) * lh / 2 + s * .36;
    let k = 0;
    r.lines.forEach((line, li) => {
      const chars = [...line], lw = measure(line, { size: s, wt: 900, ls: 4 }), x0 = -lw / 2 + 2;
      chars.forEach((ch, ci) => {
        if (!ch.trim()) return;
        const x = x0 + measure(chars.slice(0, ci).join(''), { size: s, wt: 900, ls: 4 });
        const tt = t - (o.lit + k * step); k++;
        const lit = Math.max(fl, tt < 0 ? 0 : tt < .05 ? 1 : tt < .09 ? .2 : 1);
        text(ch, x, y0 + li * lh, { size: s, wt: 900, col: rgba(C.groundHi, .45), ls: 4 });
        if (lit > 0) SK.alpha(lit, () => text(ch, x, y0 + li * lh, { size: s, wt: 900, col: C.light, ls: 4, glow: C.glow, blur: 30 }));
      });
    });
  });
}
/** the whole stage at time t. o: house (0..1 the room's light), screen (fn(c, w, h)), on (0..1 the
    screen powering on), spots [[lens, target, r, a]], mic (0..1 lit), sign (marquee's o), lip (fn) */
function stage(t, o) {
  const c = g();
  backWall(); drapes(); floorBoards(); truss();
  const aims = o.spots || [];
  const lenses = aims.map((s) => fixture(s[0], s[1], s[3]));
  for (const P of [SPOTL, SPOT, SPOTR]) if (!aims.some((s) => s[0] === P)) fixture(P, [P[0] + (CX - P[0]) * .3, FL.lip], 0);
  // the screen
  rrect(SCR.x - 16, SCR.y - 16, SCR.w + 32, SCR.h + 32, 10, C.dark);
  c.save(); c.beginPath(); c.rect(SCR.x, SCR.y, SCR.w, SCR.h); c.clip();
  c.fillStyle = withL(C.ground, L(C.ground) * .55); c.fillRect(SCR.x, SCR.y, SCR.w, SCR.h);
  const on = o.on ?? 0;
  if (on > 0 && o.screen) {
    const k = E.out(clamp(on / .6)), hh = SCR.h * k; // a CRT's line opening to the full height
    c.save(); c.beginPath(); c.rect(SCR.x, SCR.y + (SCR.h - hh) / 2, SCR.w, hh); c.clip();
    c.translate(SCR.x, SCR.y); o.screen(c, SCR.w, SCR.h); c.restore();
    if (k < 1) { c.fillStyle = rgba('#FFFFFF', .9 * (1 - k)); c.fillRect(SCR.x, SCR.y + SCR.h / 2 - 3 - hh / 2, SCR.w, 6); }
  }
  c.fillStyle = c.createPattern(led(), 'repeat'); c.globalAlpha = .2; c.fillRect(SCR.x, SCR.y, SCR.w, SCR.h);
  c.restore();
  // the room is dark: what is not lit sinks into it (the screen is a light, it stays)
  const house = o.house ?? 1;
  if (house < 1) {
    c.save(); c.fillStyle = rgba(C.groundDk, .78 * (1 - house));
    c.beginPath(); c.rect(-400, -400, W + 800, H + 800); c.rect(SCR.x, SCR.y, SCR.w, SCR.h); c.fill('evenodd'); c.restore();
  }
  // the screen lights the floor in front of it
  if (on > 0) {
    c.save(); c.globalCompositeOperation = 'screen'; c.translate(CX, FL.back + 40); c.scale(1, .18);
    const rg = c.createRadialGradient(0, 0, 0, 0, 0, 760); rg.addColorStop(0, rgba(C.glow, .22 * clamp(on))); rg.addColorStop(1, rgba(C.glow, 0));
    c.fillStyle = rg; c.beginPath(); c.arc(0, 0, 760, 0, TAU); c.fill(); c.restore();
  }
  aims.forEach((s, i) => beam(lenses[i], s[1], s[2], s[3], s[4] ?? C.beam, i + 1, t));
  lipFace();
  // the sign hangs upstage; the microphone stands downstage, in front of it
  if (o.sign) marquee(t, { ...o.sign, house });
  if ((o.mic ?? 0) >= 0) micStand(o.mic ?? 0);
}

/* ------------------------------------------------------------------ the screen's pages (drawn in its own units, 1200 x 600) */
function screenBg(c, w, h, t) {
  const gr = c.createLinearGradient(0, 0, w, h);
  gr.addColorStop(0, C.groundMid); gr.addColorStop(1, withL(C.ground, L(C.ground) * .8));
  c.fillStyle = gr; c.fillRect(0, 0, w, h);
  // light that slowly crosses the screen, a band of the accent
  c.save(); c.globalCompositeOperation = 'screen'; c.globalAlpha = .07;
  const x = ((t * 60) % (w + 900)) - 450;
  const lg = c.createLinearGradient(x, 0, x + 450, 0); lg.addColorStop(0, rgba(C.glow, 0)); lg.addColorStop(.5, C.glow); lg.addColorStop(1, rgba(C.glow, 0));
  c.fillStyle = lg; c.fillRect(0, 0, w, h); c.restore();
}
function kicker(str, x, y, o = {}) { text(str, x, y, { size: o.size ?? 24, wt: 800, fam: F.sans, ls: 6, col: o.col ?? C.glow, align: o.align ?? 'left' }); }
/** S1: the logo, and the event's dates and place under it */
function pageOpen(t) {
  return (c, w, h) => {
    screenBg(c, w, h, t);
    const a = ease(t, T.screen + .2, T.screen + .7, E.out);
    SK.alpha(a, () => withT(w / 2, 170, 0, 1.05 - .05 * a, () => logo(true, 0, 0, 820, 230)));
    const tw = ease(t, T.screen + .55, T.screen + 1.1, E.lin);
    const s = fit(up(EVLINE), w - 160, 40, { wt: 800, fam: F.sans, ls: 4 }), lw = measure(up(EVLINE), { size: s, wt: 800, fam: F.sans, ls: 4 });
    clipRect(w / 2 - lw / 2 - 6, 318, (lw + 12) * tw, 70, () => text(up(EVLINE), w / 2, 370, { size: s, wt: 800, fam: F.sans, ls: 4, col: C.light, align: 'center' }));
  };
}
/** S3: the title, a slide per topic, then the wall of every topic */
function slideAt(t) { if (t < T.slides) return -1; if (t < WALL) return Math.floor((t - T.slides) / BAR); return KS; }
function pageSlides(t) {
  return (c, w, h) => {
    screenBg(c, w, h, t);
    const k = slideAt(t + .12), tc = k < 0 ? T.s3 : k < KS ? T.slides + k * BAR : WALL;
    const u = E.inOut(clamp((t - (tc - .12)) / .3));
    if (k >= 0 && u < 1) { c.save(); c.translate(-w * u, 0); slide(c, w, h, t, k - 1, tc - .12); c.restore(); }
    c.save(); if (k >= 0) c.translate(w * (1 - u), 0); slide(c, w, h, t, k, tc); c.restore();
  };
}
function slide(c, w, h, t, j, t0) {
  if (j < 0) { // the title
    kicker(up(EV.name), 80, 112);
    const r = wrapFit(up(COPY.topics), w - 220, 150, 2, { wt: 900 });
    r.lines.forEach((ln, i) => rise(ln, 80, 170 + r.size * .78 + i * r.size * .92, { size: r.size, wt: 900, col: C.light }, t, T.s3 + .08 + i * .12));
    const bw = 140 * ease(t, T.s3 + .35, T.s3 + .8, E.out);
    rrect(82, 200 + r.size * .92 * r.lines.length + 10, bw, 12, 6, C.glow);
    return;
  }
  if (j >= KS) return wall(c, w, h, t);
  const tp = TOPICS[j];
  // the number, large and quiet behind
  c.save(); c.font = font(430, 900); c.textAlign = 'right'; c.lineWidth = 3; c.strokeStyle = rgba(C.groundHi, .45);
  c.strokeText(pad2(j + 1), w - 50, h - 40); c.restore();
  kicker(`${up(COPY.track)} ${pad2(j + 1)} / ${pad2(TOPICS.length)}`, 80, 112);
  const r = wrapFit(up(tp.name), w - 200, 132, 3, { wt: 900, h: 330, lh: .94 });
  const y0 = 160 + r.size * .78;
  r.lines.forEach((ln, i) => rise(ln, 80, y0 + i * r.size * .94, { size: r.size, wt: 900, col: C.light }, t, t0 - .2 + i * .06));
  if (tp.detail) {
    const ds = fit(tp.detail, w - 200, 36, { wt: 600, fam: F.sans });
    rise(tp.detail, 82, y0 + (r.lines.length - 1) * r.size * .94 + 78, { size: ds, wt: 600, fam: F.sans, col: C.soft }, t, t0);
  }
  // the progress along the bottom: a mark per topic, this one lit
  const n = TOPICS.length, mw = Math.min(46, (w - 160 - (n - 1) * 8) / n);
  for (let i = 0; i < n; i++) rrect(80 + i * (mw + 8), h - 62, mw, 8, 4, i === j ? C.glow : rgba(C.groundHi, .5));
}
function wallGrid(n) {
  const cols = n <= 3 ? n : n === 4 ? 2 : n <= 6 ? 3 : n <= 8 ? 4 : n <= 12 ? 4 : 5, rows = Math.ceil(n / cols);
  const gx = 16, gy = 16, X0 = 60, Y0 = 130, AW = 1080, AH = 420;
  const cw = (AW - (cols - 1) * gx) / cols, ch = Math.min(n <= 3 ? 240 : 200, (AH - (rows - 1) * gy) / rows);
  const y0 = Y0 + (AH - (rows * ch + (rows - 1) * gy)) / 2;
  return { cols, rows, cw, ch, gx, gy, X0, y0 };
}
function wall(c, w, h, t) {
  kicker(up(COPY.all_topics), 60, 92);
  kicker(up(EV.name), w - 60, 92, { col: C.soft, align: 'right', size: 20 });
  const n = TOPICS.length, G = wallGrid(n), land = WALL + .3;
  // one size for most cards: no name larger than the middle one fits at; a long name takes less
  const fits = TOPICS.map((tp) => wrapFit(up(tp.name), G.cw - 40, 40, 3, { wt: 900, h: G.ch - 58, lh: 1 }).size).sort((a, b) => a - b);
  const one = fits[Math.floor(fits.length / 2)];
  const hot = t > land + n * .125 + .3 ? Math.floor((t - WALL) / BEAT) % n : -1;
  TOPICS.forEach((tp, i) => {
    const col = i % G.cols, row = Math.floor(i / G.cols), lastRow = row === G.rows - 1;
    const inRow = lastRow ? n - row * G.cols : G.cols, off = (G.cols - inRow) * (G.cw + G.gx) / 2;
    const x = G.X0 + off + col * (G.cw + G.gx), y = G.y0 + row * (G.ch + G.gy);
    const p = ease(t, land + i * .125, land + i * .125 + .35, outBack); if (p <= 0) return;
    withT(x + G.cw / 2, y + G.ch / 2, 0, .7 + .3 * p, () => SK.alpha(clamp(p * 1.4), () => {
      const isHot = i === hot;
      rrect(-G.cw / 2, -G.ch / 2, G.cw, G.ch, 10, isHot ? C.glow : C.groundMid);
      rrect(-G.cw / 2, -G.ch / 2, 6, G.ch, 3, isHot ? C.onAccent : C.glow);
      text(pad2(i + 1), -G.cw / 2 + 22, -G.ch / 2 + 34, { size: 22, wt: 800, fam: F.sans, ls: 3, col: isHot ? C.onAccent : C.glow });
      const r = wrapFit(up(tp.name), G.cw - 40, one, 3, { wt: 900, h: G.ch - 58, lh: 1 });
      r.lines.forEach((ln, li) => text(ln, -G.cw / 2 + 22, -G.ch / 2 + 50 + r.size * .82 + li * r.size, { size: r.size, wt: 900, col: isHot ? C.onAccent : C.light }));
    }));
  });
}
/** S7: the days left, rolling down to the number */
function pageCount(t) {
  return (c, w, h) => {
    screenBg(c, w, h, t);
    const dl = COUNT ? `${up(COPY.deadline)}  ·  ${up(CFP.deadline_text)}` : up(COPY.deadline);
    rise(dl, w / 2, 96, { size: fit(dl, w - 160, 30, { wt: 800, fam: F.sans, ls: 5 }), wt: 800, fam: F.sans, ls: 5, col: C.glow, align: 'center' }, t, T.s7 + .1);
    if (!COUNT || COUNT.n === 0) { // the last day, or no count: the words, large
      const str = up(COUNT ? COUNT.unit : CFP.deadline_text), r = wrapFit(str, w - 160, 230, 2, { wt: 900, h: 400, lh: .92 });
      r.lines.forEach((ln, i) => rise(ln, w / 2, 330 - (r.lines.length - 1) * r.size * .46 + i * r.size * .92 + r.size * .36, { size: r.size, wt: 900, col: C.light, align: 'center', glow: rgba(C.glow, .6) }, t, T.s7 + .3 + i * .1));
      return;
    }
    const n = COUNT.n, digits = String(n).length, n0 = Math.min(Math.pow(10, digits) - 1, n + 20);
    const f = lerp(n0, n, E.out(clamp((t - (T.s7 + .4)) / (T.count - T.s7 - .4)))); // continuous, n0 -> n
    const size = 330, dw = measure('0', { size, wt: 900 }) * 1.02, x0 = w / 2 - digits * dw / 2, yb = 410;
    const land = ease(t, T.count, T.count + .25, outBack), throb = t > T.count ? Math.exp(-((t - T.count) % BEAT) * 7) : 0;
    c.save(); c.beginPath(); c.rect(0, yb - size * .82, w, size * .92); c.clip();
    for (let p = 0; p < digits; p++) { // each column rolls like an odometer's
      // each step holds, then rolls
      const b = Math.pow(10, digits - 1 - p), hi = Math.floor(f / b), r = E.inOut(clamp((f - hi * b - (b - 1) - .3) / .7));
      const x = x0 + p * dw + dw / 2;
      for (const [v, dy] of [[hi % 10, -r * size * .9], [(hi + 1) % 10, (1 - r) * size * .9]]) {
        if (Math.abs(dy) > size) continue;
        if (p === 0 && v === 0 && digits > 1) continue;
        text(String(v), x, yb + dy, { size, wt: 900, col: C.light, align: 'center', glow: rgba(C.glow, Math.min(1, .45 + .4 * (1 - land) + .35 * throb)), blur: 40 + 30 * throb });
      }
    }
    c.restore();
    const us = fit(up(COUNT.unit), w - 240, 84, { wt: 900, ls: 6 });
    rise(up(COUNT.unit), w / 2, 520, { size: us, wt: 900, ls: 6, col: C.glow, align: 'center' }, t, T.count + .05, .35);
  };
}
/** S8: the logo, when and where, and the address to submit at */
function pageEnd(t) {
  return (c, w, h) => {
    screenBg(c, w, h, t);
    const a = ease(t, T.s8 - .3, T.s8 + .2, E.out);
    SK.alpha(a, () => withT(w / 2, 96, 0, 1.05 - .05 * a, () => logo(true, 0, 0, 640, 140)));
    rise(up(EVLINE), w / 2, 226, { size: fit(up(EVLINE), w - 160, 36, { wt: 800, fam: F.sans, ls: 4 }), wt: 800, fam: F.sans, ls: 4, col: C.light, align: 'center' }, t, T.s8 - .15);
    const url = CFP.url || EV.url || '';
    rise(url, w / 2, 314, { size: fit(url, w - 80, 60, { wt: 800, fam: F.sans }), wt: 800, fam: F.sans, col: C.glow, align: 'center' }, t, T.s8);
    const dl = [`${up(COPY.deadline)}  ${up(CFP.deadline_text)}`, COUNT && COUNT.n > 0 ? `${COUNT.n} ${up(COUNT.unit)}` : ''].filter(Boolean).join('   ·   ');
    rise(dl, w / 2, 382, { size: fit(dl, w - 140, 30, { wt: 800, fam: F.sans, ls: 4 }), wt: 800, fam: F.sans, ls: 4, col: C.soft, align: 'center' }, t, T.lip);
  };
}

/* ------------------------------------------------------------------ the audience: heads between us and the screen */
function audience(t, dy = 0) {
  const c = g(), col = withL(C.ground, Math.min(.045, L(C.ground) * .3));
  for (let i = 0; i < 11; i++) {
    const x = -40 + i * 196 + rnd(i * 3 + 1) * 60, s = .82 + rnd(i * 5 + 2) * .4, y = 1040 + rnd(i * 7 + 3) * 40 + dy;
    const bob = Math.sin(t * 1.1 + i * 2.1) * 3;
    c.fillStyle = col;
    c.beginPath(); c.ellipse(x, y + 120 * s + bob, 130 * s, 90 * s, 0, Math.PI, TAU); c.fill();
    c.beginPath(); c.ellipse(x, y + bob, 48 * s, 60 * s, 0, 0, TAU); c.fill();
    c.strokeStyle = rgba(C.glow, .22); c.lineWidth = 2.5; c.beginPath(); c.ellipse(x, y + bob, 48 * s, 60 * s, 0, Math.PI * 1.15, Math.PI * 1.85); c.stroke();
  }
}

/* ------------------------------------------------------------------ S1: the stage, the spotlight, the call */
function scene1(t) {
  const spotX = SK.kf(t, [[-.3, 300], [T.land, MIC.x, E.out]]);
  const pulse = t > T.land ? 1 + .6 * Math.exp(-(t - T.land) * 5) : .75;
  const cam = SK.kf(t, [[0, [960, 650, 1.22]], [T.land, [960, 640, 1.2]], [T.land + 1.4, [960, 540, 1], E.inOut], [8, [960, 556, 1.04], E.sine]]);
  // two side lights cross the stage while the sign lights up
  const side = ease(t, T.sign + .6, T.sign + 1.1);
  const sw = Math.sin((t - T.sign) * 1.6);
  const spots = [[SPOT, [spotX, MIC.base - 4], t < T.land ? 150 : 120, pulse]];
  if (side > 0) {
    spots.push([SPOTL, [CX - 320 + sw * 260, FL.back + 150], 120, .7 * side, C.glow]);
    spots.push([SPOTR, [CX + 320 - sw * 260, FL.back + 150], 120, .7 * side, C.glow2]);
  }
  stageCam(cam, () => stage(t, {
    house: SK.kf(t, [[0, .55], [T.land, .55], [T.screen + .5, .66]]),
    screen: pageOpen(t), on: t - T.screen, spots, mic: t < T.land ? 0 : 1,
    sign: { str: COPY.title, land: T.sign, lit: T.sign + .25, flash: t > 7.6 ? ease(t, 7.6, 7.9) : 0 },
  }));
}
/* ------------------------------------------------------------------ S2: the badge -- this could be you */
const BADGE = { px: 1350, py: -110, len: 330, w: 500, h: 690 };
function badgeAngle(t) {
  const tl = t - (T.flash + .55);
  return tl < 0 ? .06 : .2 * Math.exp(-1.05 * tl) * Math.sin(4.3 * tl + .3) + .012 * Math.sin(t * 1.3);
}
function scene2(t) {
  const c = g(), zz = 1 + .045 * E.sine(clamp((t - T.flash) / (T.s3 - T.flash)));
  c.save(); c.translate(CX, CY); c.scale(zz, zz); c.translate(-CX, -CY);
  c.fillStyle = C.accent; c.fillRect(0, 0, W, H);
  // the lanyard's weave, faint and drifting
  c.save(); c.globalAlpha = .08; c.fillStyle = C.accentDk;
  const off = ((t - T.flash) * 40) % 140;
  for (let i = -8; i < 24; i++) { const x = i * 140 + off; poly([[x, 0], [x + 56, 0], [x + 56 - 520, H], [x - 520, H]], C.accentDk); }
  c.restore();
  const rg = c.createRadialGradient(BADGE.px, 600, 0, BADGE.px, 600, 820);
  rg.addColorStop(0, rgba('#FFFFFF', .35)); rg.addColorStop(1, rgba('#FFFFFF', 0));
  c.fillStyle = rg; c.fillRect(0, 0, W, H);
  // the headline: two lines that rise on the beat, the last word underlined
  const r = wrapFit(up(COPY.could), 860, 210, 2, { wt: 900, h: 470, lh: .92 }), y0 = 250 + r.size * .8;
  r.lines.forEach((ln, i) => rise(ln, 136, y0 + i * r.size * .92, { size: r.size, wt: 900, col: C.onAccent }, t, T.flash + .5 + i * .5));
  const last = r.lines[r.lines.length - 1] || '', lw = measure(last.split(' ').pop(), { size: r.size, wt: 900 });
  const lx = 140 + measure(last.slice(0, last.length - last.split(' ').pop().length), { size: r.size, wt: 900 });
  const ul = ease(t, T.flash + 1.5, T.flash + 1.85, E.out), uy = y0 + (r.lines.length - 1) * r.size * .92 + 26;
  const ulCol = contrast(C.second, C.accent) >= 2.2 ? C.second : C.onAccent;
  if (ul > 0) rrect(lx, uy, lw * ul, 16, 8, ulCol);
  // who and where
  const nr = wrapFit(up(EV.name), 860, 62, 2, { wt: 800 }), ny = 800;
  nr.lines.forEach((ln, i) => rise(ln, 136, ny + i * nr.size * .95, { size: nr.size, wt: 800, col: C.onAccent }, t, T.flash + 3 + i * .12));
  const sub = up(EVLINE);
  rise(sub, 138, ny + (nr.lines.length - 1) * nr.size * .95 + 58, { size: fit(sub, 860, 34, { wt: 700, fam: F.sans, ls: 3 }), wt: 700, fam: F.sans, ls: 3, col: C.onAccent }, t, T.flash + 3.3);
  badge(t);
  // press flashes, here and there
  for (const [tf, x, y] of [[12.0, 1820, 260], [12.75, 120, 940], [13.5, 1750, 900], [14.5, 980, 80]]) {
    const u = t - tf; if (u < 0 || u > .35) continue;
    const a = Math.exp(-u * 12), fg = c.createRadialGradient(x, y, 0, x, y, 520);
    fg.addColorStop(0, rgba('#FFFFFF', .95 * a)); fg.addColorStop(.2, rgba('#FFFFFF', .4 * a)); fg.addColorStop(1, rgba('#FFFFFF', 0));
    c.fillStyle = fg; c.fillRect(-W, -H, 3 * W, 3 * H);
  }
  c.restore();
}
function badge(t) {
  const c = g(), B = BADGE, drop = ease(t, T.flash, T.flash + .55, outSoft), th = badgeAngle(t);
  withT(B.px, B.py + (1 - drop) * -980, th, 1, () => {
    // the lanyard: two straps, the event's name woven along them
    for (const k of [-1, 1]) {
      const a0 = [k * 92, -260], a1 = [k * 18, B.len - 6], ang = Math.atan2(a1[1] - a0[1], a1[0] - a0[0]);
      const nx = -Math.sin(ang) * 23, ny = Math.cos(ang) * 23;
      const q = [[a0[0] - nx, a0[1] - ny], [a0[0] + nx, a0[1] + ny], [a1[0] + nx * .7, a1[1] + ny * .7], [a1[0] - nx * .7, a1[1] - ny * .7]];
      poly(q, C.second);
      c.save(); c.beginPath(); c.moveTo(q[0][0], q[0][1]); for (const p of q.slice(1)) c.lineTo(p[0], p[1]); c.closePath(); c.clip();
      withT(a0[0], a0[1], ang, 1, () => text((up(EV.name) + '   ·   ').repeat(6), -40, 7, { size: 19, wt: 800, fam: F.sans, ls: 3, col: C.onSecond }));
      c.restore();
    }
    // the clip
    rrect(-20, B.len - 30, 40, 44, 8, C.metal); rrect(-12, B.len - 22, 24, 20, 5, mixHex(C.metal, C.dark, .4));
    withT(-B.w / 2, B.len, 0, 1, () => badgeCard(t));
  });
}
function badgeCard(t) {
  const c = g(), w = BADGE.w, h = BADGE.h;
  c.save(); c.shadowColor = rgba(C.ground, .38); c.shadowBlur = 50; c.shadowOffsetY = 28; rrect(0, 0, w, h, 30, C.paper); c.restore();
  c.save(); SK.rrPath(0, 0, w, h, 30); c.clip();
  c.fillStyle = C.ground; c.fillRect(0, 0, w, 210);
  logo(true, w / 2, 118, 400, 120);
  rrect(w / 2 - 50, 18, 100, 16, 8, rgba('#000000', .45));
  // the role
  const ps = 30, pw = measure(up(COPY.speaker), { size: ps, wt: 800, fam: F.sans, ls: 8 }) + 70;
  rrect(w / 2 - pw / 2, 238, pw, 60, 30, C.accent);
  text(up(COPY.speaker), w / 2 + 4, 279, { size: ps, wt: 800, fam: F.sans, ls: 8, col: C.onAccent, align: 'center' });
  // the name field, typed
  const name = up(COPY.you), chars = [...name], ns = fit(name, w - 110, 170, { wt: 700, fam: F.mono });
  const k = clamp(Math.floor((t - T.type) / .25) + 1, 0, chars.length), shown = chars.slice(0, k).join('');
  const sw = measure(shown, { size: ns, wt: 700, fam: F.mono }), full = measure(name, { size: ns, wt: 700, fam: F.mono });
  const nx = w / 2 - full / 2, ny = 470;
  text(shown, nx, ny, { size: ns, wt: 700, fam: F.mono, col: C.ground });
  if (t > T.type - .6 && Math.floor(t * 2.6) % 2 === 0) rrect(nx + sw + 8, ny - ns * .74, ns * .5, ns * .8, 4, C.marker);
  c.strokeStyle = rgba(C.ground, .3); c.lineWidth = 3; c.setLineDash([10, 9]); c.beginPath(); c.moveTo(56, 505); c.lineTo(w - 56, 505); c.stroke(); c.setLineDash([]);
  text(up(COPY.your_talk), w / 2, 552, { size: fit(up(COPY.your_talk), w - 120, 24, { wt: 700, fam: F.sans, ls: 6 }), wt: 700, fam: F.sans, ls: 6, col: C.inkSoft, align: 'center' });
  c.fillStyle = C.second; c.fillRect(0, h - 92, w, 92);
  text(up(EVLINE), w / 2, h - 36, { size: fit(up(EVLINE), w - 70, 28, { wt: 800, fam: F.sans, ls: 2 }), wt: 800, fam: F.sans, ls: 2, col: C.onSecond, align: 'center' });
  // a camera flash glints across it
  for (const tf of [12.0, 13.5]) {
    const u = (t - tf) / .45; if (u < 0 || u > 1) continue;
    const x = lerp(-300, w + 300, u), lg = c.createLinearGradient(x - 120, 0, x + 120, 0);
    lg.addColorStop(0, rgba('#FFFFFF', 0)); lg.addColorStop(.5, rgba('#FFFFFF', .5)); lg.addColorStop(1, rgba('#FFFFFF', 0));
    c.save(); c.transform(1, 0, -.4, 1, 0, 0); c.fillStyle = lg; c.fillRect(-400, 0, w + 800, h); c.restore();
  }
  c.restore();
}
/* ------------------------------------------------------------------ S3: what they want to hear, on the big screen */
const ZOOM_SCR = [960, 380, 1.55];
function scene3(t) {
  const z = ZOOM_SCR[2] + .05 * E.sine(clamp((t - T.s3) / (T.s4 - T.s3)));
  stageCam([ZOOM_SCR[0], ZOOM_SCR[1], z], () => stage(t, { house: .45, screen: pageSlides(t), on: 9, mic: -1 }));
  audience(t);
}
/* ------------------------------------------------------------------ S4: stage time -- the formats as stage timers */
const SEG = ['abcdef', 'bc', 'abdeg', 'abcdg', 'bcfg', 'acdfg', 'acdefg', 'abc', 'abcdefg', 'abcdfg'];
/** a seven-segment digit or a colon at x (left), y (top), dw x dh; on: the lit path, off: the unlit */
function seg7(on, off, ch, x, y, dw, dh) {
  const s = dw * .2, m = s * .55, h2 = dh / 2;
  const hz = (cy) => { const a = x + m, b = x + dw - m; return [[a, cy], [a + s / 2, cy - s / 2], [b - s / 2, cy - s / 2], [b, cy], [b - s / 2, cy + s / 2], [a + s / 2, cy + s / 2]]; };
  const vt = (cx, y0, y1) => { const a = y0 + m, b = y1 - m; return [[cx, a], [cx + s / 2, a + s / 2], [cx + s / 2, b - s / 2], [cx, b], [cx - s / 2, b - s / 2], [cx - s / 2, a + s / 2]]; };
  const P = { a: hz(y + s / 2), g: hz(y + h2), d: hz(y + dh - s / 2), f: vt(x + s / 2, y + s / 2, y + h2), b: vt(x + dw - s / 2, y + s / 2, y + h2), e: vt(x + s / 2, y + h2, y + dh - s / 2), c: vt(x + dw - s / 2, y + h2, y + dh - s / 2) };
  const lit = SEG[+ch] || '';
  for (const k of 'abcdefg') { const p = lit.includes(k) ? on : off; p.moveTo(P[k][0][0], P[k][0][1]); for (const q of P[k].slice(1)) p.lineTo(q[0], q[1]); p.closePath(); }
}
function timerText(min, secsGone) {
  const total = Math.max(0, Math.round(min * 60) - secsGone), hh = Math.floor(total / 3600), mm = Math.floor(total / 60) % 60, ss = total % 60;
  return min >= 100 ? `${hh}:${pad2(mm)}:${pad2(ss)}` : `${pad2(Math.floor(total / 60))}:${pad2(ss)}`;
}
function timerLayout(n) { const gap = 44, w = Math.min(540, (W - 220 - gap * (n - 1)) / n); return { w, h: Math.min(320, w * .6), gap, x0: CX - (n * w + (n - 1) * gap) / 2, y: 440 }; }
function scene4(t) {
  const c = g(), zz = 1 + .05 * E.sine(clamp((t - T.s4) / (T.curtain - T.s4)));
  c.save(); c.translate(CX, CY * 1.1); c.scale(zz, zz); c.translate(-CX, -CY * 1.1);
  const gr = c.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, C.groundDk); gr.addColorStop(.62, C.ground); gr.addColorStop(.62, C.groundMid); gr.addColorStop(1, withL(C.ground, L(C.ground) * .8));
  c.fillStyle = gr; c.fillRect(0, 0, W, H);
  c.strokeStyle = rgba(C.groundDk, .6); c.lineWidth = 2; c.beginPath();
  for (let k = -14; k <= 14; k++) { const xb = CX + k * 120 * .45, xl = CX + k * 120 * 1.6; c.moveTo(xb, H * .62); c.lineTo(xl, H + 10); }
  c.stroke();
  // a wash of light from above onto the timers
  const lg = c.createRadialGradient(CX, 360, 0, CX, 360, 900); lg.addColorStop(0, rgba(C.beam, .14)); lg.addColorStop(1, rgba(C.beam, 0));
  c.fillStyle = lg; c.fillRect(0, 0, W, H);
  rise(up(COPY.formats), 120, 262, { size: fit(up(COPY.formats), 1200, 118, { wt: 900 }), wt: 900, col: C.light }, t, T.s4 - .2);
  rise(up(COPY.formats_sub), 124, 328,{ size: fit(up(COPY.formats_sub), 1100, 32, { wt: 800, fam: F.sans, ls: 7 }), wt: 800, fam: F.sans, ls: 7, col: C.glow }, t, T.s4 + .1);
  const n = FORMATS.length, Lt = timerLayout(Math.max(1, n));
  const gone = t < T.run ? 0 : Math.floor((t - T.run) / BEAT) + 1;
  FORMATS.forEach((fm, i) => {
    const t0 = T.timers + i * BEAT, drop = ease(t, t0 - .3, t0, outSoft); if (drop <= 0) return;
    const x = Lt.x0 + i * (Lt.w + Lt.gap), y = Lt.y + (1 - drop) * -700, w = Lt.w, h = Lt.h;
    // the box, its top seen a little from above
    poly([[x + 10, y], [x + w - 10, y], [x + w - 26, y - 22], [x + 26, y - 22]], mixHex(C.dark, C.metal, .3));
    c.save(); c.shadowColor = 'rgba(0,0,0,.5)'; c.shadowBlur = 34; c.shadowOffsetY = 24; rrect(x, y, w, h, 16, C.dark); c.restore();
    c.fillStyle = rgba(C.metal, .3); c.fillRect(x + 16, y + 2, w - 32, 2);
    const sx = x + 18, sy = y + 18, sw = w - 36, sh = h - 58;
    rrect(sx, sy, sw, sh, 8, '#05060A');
    const ledOn = t - t0 > .08 ? (t - t0 < .16 ? .3 : 1) : 0;
    const label = fm.label ? up(fm.label) : null, str = label ?? timerText(+fm.minutes || 0, gone);
    if (label) {
      const ls = fit(label, sw - 40, sh * .6, { wt: 800 });
      SK.alpha(ledOn, () => text(label, sx + sw / 2, sy + sh / 2 + ls * .36, { size: ls, wt: 800, col: C.glow, align: 'center', glow: C.glow, blur: 20 }));
    } else {
      const nd = str.replace(/:/g, '').length, nc = str.length - nd;
      const dh = sh * .68, dw0 = dh * .52, cw0 = dh * .22, sc = Math.min(1, (sw - 36) / (nd * dw0 * 1.12 + nc * cw0));
      const dw = dw0 * sc, cw = cw0 * sc, dhh = dh * sc, tw = nd * dw * 1.12 + nc * cw;
      let cx = sx + sw / 2 - tw / 2; const cy = sy + sh / 2 - dhh / 2;
      const on = new Path2D(), off = new Path2D(), dots = [];
      for (const ch of str) {
        if (ch === ':') { dots.push([cx + cw / 2, cy + dhh * .3], [cx + cw / 2, cy + dhh * .7]); cx += cw; continue; }
        seg7(on, off, ch, cx + dw * .06, cy, dw, dhh); cx += dw * 1.12;
      }
      c.fillStyle = rgba(C.glow, .07); c.fill(off);
      if (ledOn > 0) SK.alpha(ledOn, () => {
        c.save(); c.fillStyle = C.glow; c.shadowColor = C.glow; c.shadowBlur = 18; c.fill(on);
        const blink = gone === 0 || (t - T.run) % BEAT < BEAT * .6;
        if (blink) for (const [dx, dy] of dots) { c.beginPath(); c.arc(dx, dy, dw * .1, 0, TAU); c.fill(); }
        c.restore();
      });
    }
    // the tally light
    c.fillStyle = ledOn > 0 ? C.glow2 : C.groundLt; c.beginPath(); c.arc(x + w - 30, y + h - 20, 6, 0, TAU); c.fill();
    // what it is
    const nm = wrapFit(up(fm.name), w + 10, 60, 2, { wt: 800 });
    nm.lines.forEach((ln, li) => rise(ln, x + w / 2, y + h + 84 + li * nm.size, { size: nm.size, wt: 800, col: C.light, align: 'center' }, t, t0 + .1));
    const minTxt = label ? '' : `${Math.round(+fm.minutes || 0)} ${up(COPY.min)}`;
    // the display's light on the floor in front of it
    if (ledOn > 0) { const sg = c.createRadialGradient(x + w / 2, y + h + 30, 0, x + w / 2, y + h + 30, w * .7); sg.addColorStop(0, rgba(C.glow, .16 * ledOn)); sg.addColorStop(1, rgba(C.glow, 0)); c.save(); c.globalCompositeOperation = 'screen'; c.fillStyle = sg; c.fillRect(x - w * .3, y + h - 10, w * 1.6, w * .7); c.restore(); }
    if (minTxt) rise(minTxt, x + w / 2, y + h + 84 + (nm.lines.length - 1) * nm.size + 58, { size: 30, wt: 700, fam: F.sans, ls: 5, col: C.glow, align: 'center' }, t, t0 + .2);
  });
  c.restore();
}
/* ------------------------------------------------------------------ S5: why speak -- the pass, and the perks stamped by it */
const CASE = { x: 830, y: 246, w: 990, h: 770 };
function stampSlots(n) {
  const big = n <= 3, w = big ? 800 : 440, h = big ? 196 : 170;
  const S = {
    1: [[1325, 630, -.05]],
    2: [[1310, 500, -.05], [1340, 765, .04]],
    3: [[1305, 398, -.045], [1345, 632, .035], [1310, 866, -.03]],
    4: [[1090, 490, -.06], [1558, 500, .05], [1100, 775, .04], [1562, 785, -.05]],
    5: [[1090, 410, -.05], [1558, 425, .06], [1325, 630, -.03], [1090, 840, .04], [1558, 850, -.06]],
  };
  return { w, h, at: S[Math.max(1, Math.min(5, n))] };
}
function stamp(str, w, h, ink, ground) {
  const c = g();
  c.strokeStyle = ink; c.lineWidth = 7; SK.rrPath(-w / 2, -h / 2, w, h, 16); c.stroke();
  c.lineWidth = 2.5; SK.rrPath(-w / 2 + 13, -h / 2 + 13, w - 26, h - 26, 9); c.stroke();
  const r = wrapFit(up(str), w - 90, 76, 2, { wt: 900, h: h - 56, lh: .98, ls: 2 });
  r.lines.forEach((ln, i) => text(ln, 0, -(r.lines.length - 1) * r.size * .49 + i * r.size * .98 + r.size * .36, { size: r.size, wt: 900, col: ink, align: 'center', ls: 2 }));
  // ink that did not take: the ground showing through, from a fixed seed
  c.fillStyle = ground;
  for (let i = 0; i < 90; i++) { c.globalAlpha = .45 + rnd(i * 3 + 7) * .55; c.beginPath(); c.arc((rnd(i * 5 + 1) - .5) * w, (rnd(i * 7 + 2) - .5) * h, .8 + rnd(i * 11) * 3, 0, TAU); c.fill(); }
  c.globalAlpha = 1;
}
function pass(t) {
  const c = g(), swing = ease(t, T.curtain + .25, T.curtain + .8, outSoft), tl = t - (T.curtain + .8);
  const th = tl < 0 ? .12 * (1 - swing) : .09 * Math.exp(-tl * 1.2) * Math.sin(tl * 3.8) + .012 * Math.sin(t * 1.1);
  withT(450, -70 + (1 - swing) * -900, th, 1.1, () => {
    for (const k of [-1, 1]) poly([[k * 70 - 22, -300], [k * 70 + 22, -300], [k * 14 + 12, 300], [k * 14 - 12, 300]], C.second);
    rrect(-18, 280, 36, 48, 8, C.metal);
    withT(-210, 318, 0, 1, () => {
      const w = 420, h = 600;
      c.save(); c.shadowColor = 'rgba(0,0,0,.5)'; c.shadowBlur = 44; c.shadowOffsetY = 26; rrect(0, 0, w, h, 26, C.paper); c.restore();
      c.save(); SK.rrPath(0, 0, w, h, 26); c.clip();
      // the holographic band
      const hue = (t * 40) % 360, hg = c.createLinearGradient(0, 40, w, 150);
      for (let k = 0; k <= 4; k++) hg.addColorStop(k / 4, `hsl(${(hue + k * 70) % 360},70%,${78 - k % 2 * 8}%)`);
      c.fillStyle = hg; c.fillRect(0, 40, w, 112);
      c.fillStyle = rgba('#FFFFFF', .25); c.fillRect(0, 40, w, 8);
      const ps = fit(up(COPY.pass), w - 60, 66, { wt: 900, ls: 3 });
      text(up(COPY.pass), w / 2, 96 + ps * .36, { size: ps, wt: 900, ls: 3, col: C.ground, align: 'center' });
      rrect(w / 2 - 46, 14, 92, 14, 7, rgba('#000000', .4));
      logo(false, w / 2, 222, 330, 96);
      // the photo: whoever you are
      rrect(36, 290, 150, 170, 10, C.groundMid);
      c.save(); SK.rrPath(36, 290, 150, 170, 10); c.clip(); c.fillStyle = C.groundLt;
      c.beginPath(); c.ellipse(111, 360, 34, 40, 0, 0, TAU); c.fill(); c.beginPath(); c.ellipse(111, 470, 70, 62, 0, Math.PI, TAU); c.fill(); c.restore();
      const ys = fit(up(COPY.you), w - 240, 96, { wt: 900 });
      text(up(COPY.you), 210, 400 + ys * .36, { size: ys, wt: 900, col: C.ground });
      c.fillStyle = C.ground; c.fillRect(0, h - 120, w, 120);
      const ss = fit(up(COPY.speaker), w - 70, 76, { wt: 900, ls: 4 });
      text(up(COPY.speaker), w / 2, h - 60 + ss * .36, { size: ss, wt: 900, ls: 4, col: C.light, align: 'center' });
      c.restore();
    });
  });
}
function scene5(t) {
  const c = g(), zz = 1 + .05 * E.sine(clamp((t - T.curtain) / (T.s6 - T.curtain)));
  c.save(); c.translate(CX * 1.2, CY); c.scale(zz, zz); c.translate(-CX * 1.2, -CY);
  const gr = c.createLinearGradient(0, 0, W, H); gr.addColorStop(0, C.groundMid); gr.addColorStop(1, C.groundDk);
  c.fillStyle = gr; c.fillRect(0, 0, W, H);
  // a work light from the top left
  const lg = c.createRadialGradient(300, -100, 0, 300, -100, 1300); lg.addColorStop(0, rgba(C.beam, .18)); lg.addColorStop(1, rgba(C.beam, 0));
  c.fillStyle = lg; c.fillRect(0, 0, W, H);
  // the road case, its lid the place the perks are stamped
  const n = STAMPS.length, sl = stampSlots(n);
  const k = STAMPS.reduce((s, _, i) => s + (t >= T.stamps + i * BAR ? 1 : 0), 0), lastT = T.stamps + (k - 1) * BAR;
  const shake = k > 0 && t - lastT < .3 ? Math.sin((t - lastT) * 70) * 7 * (1 - (t - lastT) / .3) : 0;
  const cin = ease(t, T.curtain + .1, T.curtain + .6, outSoft);
  withT(0, shake * .6 + (1 - cin) * 300, 0, 1, () => {
    const K = CASE, caseCol = withL(C.ground, L(C.ground) + .05, .8);
    c.save(); c.shadowColor = 'rgba(0,0,0,.55)'; c.shadowBlur = 50; c.shadowOffsetY = 30; rrect(K.x, K.y, K.w, K.h, 18, C.metal); c.restore();
    rrect(K.x + 22, K.y + 22, K.w - 44, K.h - 44, 8, caseCol);
    c.strokeStyle = rgba(C.groundHi, .35); c.lineWidth = 2; SK.rrPath(K.x + 34, K.y + 34, K.w - 68, K.h - 68, 6); c.stroke();
    for (const [qx, qy] of [[K.x, K.y], [K.x + K.w, K.y], [K.x, K.y + K.h], [K.x + K.w, K.y + K.h]]) {
      c.beginPath(); c.arc(qx, qy, 30, 0, TAU); c.fillStyle = mixHex(C.metal, '#FFFFFF', .15); c.fill();
      c.beginPath(); c.arc(qx - 6, qy - 6, 10, 0, TAU); c.fillStyle = rgba('#FFFFFF', .35); c.fill();
    }
    rrect(K.x + K.w / 2 - 70, K.y + K.h - 8, 140, 30, 8, C.metal);
    const ink = contrast(C.glow, caseCol) >= 3 ? C.glow : C.light;
    STAMPS.forEach((str, i) => {
      const st = t - (T.stamps + i * BAR); if (st < 0) return;
      const [x, y, rot] = sl.at[i], s = 1 + 1.5 * Math.pow(1 - clamp(st / .14), 2), a = clamp(st / .05);
      withT(x, y, rot, s, () => SK.alpha(a * .94, () => stamp(str, sl.w, sl.h, ink, caseCol)));
    });
  });
  rise(up(COPY.why), CASE.x + 4, 196, { size: fit(up(COPY.why), CASE.w, 118, { wt: 900 }), wt: 900, col: C.light }, t, T.curtain + .5);
  withT(0, shake * .3, 0, 1, () => pass(t));
  c.restore();
}
/* ------------------------------------------------------------------ S6: the key dates, taped to the floor */
const PAPER = { cx: CX, cy: 545, w: 1360, h: 930, rot: -.022 };
function dateRows() {
  // where today falls among the dates: after the last one already past
  const past = DATES.map((d) => TODAY !== null && dayN(d.iso) !== null && dayN(d.iso) < TODAY);
  const lastPast = past.lastIndexOf(true), todayAt = TODAY !== null && DATES.some((d) => dayN(d.iso) !== null) ? lastPast + 1 : -1;
  const n = DATES.length, slots = n + (todayAt >= 0 ? .62 : 0), rh = Math.min(118, 610 / Math.max(1, slots));
  const rows = []; let y = 196;
  DATES.forEach((d, i) => {
    if (i === todayAt) { rows.push({ today: true, y, h: rh * .62 }); y += rh * .62; }
    rows.push({ d, i, y, h: rh, past: past[i] }); y += rh;
  });
  if (todayAt === n) rows.push({ today: true, y, h: rh * .62 });
  return { rows, rh };
}
function marker(pts, p, w = 7) { // a hand-drawn stroke through pts, drawn on to fraction p
  if (p <= 0) return;
  const c = g(); let len = 0; const seg = [];
  for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(l); len += l; }
  let left = len * p;
  c.save(); c.strokeStyle = C.marker; c.lineWidth = w; c.lineCap = 'round'; c.lineJoin = 'round'; c.globalAlpha *= .92;
  c.beginPath(); c.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length && left > 0; i++) {
    const u = Math.min(1, left / seg[i - 1]); c.lineTo(lerp(pts[i - 1][0], pts[i][0], u), lerp(pts[i - 1][1], pts[i][1], u)); left -= seg[i - 1];
  }
  c.stroke(); c.restore();
}
const wobble = (x0, y0, x1, y1, seed, amp = 3, n = 14) => Array.from({ length: n + 1 }, (_, i) => [lerp(x0, x1, i / n), lerp(y0, y1, i / n) + Math.sin(i * 1.7 + seed) * amp * (rnd(seed + i) - .3)]);
function paperSheet(t) {
  const c = g(), P = PAPER, w = P.w, h = P.h;
  c.save(); c.shadowColor = 'rgba(0,0,0,.5)'; c.shadowBlur = 40; c.shadowOffsetY = 18; rrect(0, 0, w, h, 6, C.paper); c.restore();
  // the header
  const hs = fit(up(COPY.dates), 720, 86, { wt: 900 });
  rise(up(COPY.dates), 80, 128, { size: hs, wt: 900, col: C.ground }, t, T.s6 - .2);
  const en = up(EV.name), es = fit(en, 430, 26, { wt: 800, fam: F.sans, ls: 3 });
  text(en, w - 80, 118, { size: es, wt: 800, fam: F.sans, ls: 3, col: C.inkSoft, align: 'right' });
  c.fillStyle = C.ground; c.fillRect(80, 162, (w - 160) * ease(t, T.s6 - .1, T.s6 + .4, E.out), 5);
  const { rows, rh } = dateRows();
  const ds = Math.min(62, rh * .52), ls = Math.min(44, rh * .4);
  let ri = 0;
  const marks = [];
  rows.forEach((r) => {
    if (r.today) { marks.push({ today: r }); return; }
    const t0 = T.rows + ri * BEAT; ri++;
    const by = r.y + r.h * .5 + ds * .36, dl = up(r.d.date || ''), lb = up(r.d.label || '');
    const dsz = fit(dl, 350, ds, { wt: 800 }), lsz = fit(lb, w - 560, ls, { wt: r.d.deadline ? 800 : 700, fam: F.sans });
    const tw = ease(t, t0, t0 + .32, E.out);
    clipRect(70, r.y, (w - 140) * tw, r.h, () => {
      text(dl, 80, by, { size: dsz, wt: 800, col: C.ground });
      text(lb, 470, by - (ds - lsz) * .1, { size: lsz, wt: r.d.deadline ? 800 : 700, fam: F.sans, col: C.ground });
    });
    c.fillStyle = rgba(C.ground, .14 * tw); c.fillRect(80, r.y + r.h - 2, w - 160, 2);
    marks.push({ r, by, dw: measure(dl, { size: dsz, wt: 800 }), lw: measure(lb, { size: lsz, wt: 700, fam: F.sans }), ds: dsz });
  });
  // the marker: past dates struck through, today drawn in, the deadline circled
  let pi = 0;
  for (const m of marks) {
    if (m.today) {
      const y = m.today.y + m.today.h * .55, p = ease(t, T.marks + .5, T.marks + 1.0, E.out);
      marker(wobble(76, y, w - 80, y, 7, 2, 18), p, 5);
      if (p > 0) {
        const hs2 = Math.min(46, m.today.h * .8), str = up(COPY.today);
        clipRect(70, y - hs2 - 10, (w - 140) * p + 10, hs2 + 14, () => text(str, w - 90, y - 10, { size: fit(str, 520, hs2, { wt: 700, fam: F.hand }), wt: 700, fam: F.hand, col: C.marker, align: 'right' }));
        poly([[76, y], [100, y - 12], [100, y + 12]], C.marker);
      }
      continue;
    }
    if (m.r.past) {
      const p = ease(t, T.marks + pi * .2, T.marks + pi * .2 + .3, E.out); pi++;
      const y = m.by - m.ds * .32;
      marker(wobble(68, y, 470 + m.lw + 16, y + 3, m.r.i * 5 + 1, 2.5, 20), p, 6);
    }
    if (m.r.d.deadline) {
      const p = ease(t, T.marks + 1.0, T.marks + 1.8, E.inOut), cx = 80 + m.dw / 2, cy = m.by - m.ds * .34, rx = m.dw / 2 + 34, ry = m.ds * .78;
      const pts = Array.from({ length: 48 }, (_, i) => { const a = -2.4 + (i / 47) * (TAU + .7), k = 1 + .05 * Math.sin(i * .9); return [cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k]; });
      marker(pts, p, 7);
      const ul = ease(t, T.marks + 1.6, T.marks + 2.0, E.out);
      marker(wobble(470, m.by + 14, 470 + m.lw, m.by + 16, 3, 2, 14), ul, 6);
    }
  }
}
function deadlineSpot() { // where the circled date is on the frame (for the push in), from the same layout
  const { rows, rh } = dateRows(), ds = Math.min(62, rh * .52);
  const r = rows.find((x) => x.d && x.d.deadline); if (!r) return [CX, CY];
  const dl = up(r.d.date || ''), dsz = fit(dl, 350, ds, { wt: 800 }), dw = measure(dl, { size: dsz, wt: 800 });
  const px = 80 + dw / 2 - PAPER.w / 2, py = r.y + r.h * .5 + ds * .36 - dsz * .34 - PAPER.h / 2;
  const cs = Math.cos(PAPER.rot), sn = Math.sin(PAPER.rot);
  return [PAPER.cx + px * cs - py * sn, PAPER.cy + px * sn + py * cs];
}
function scene6(t) {
  const c = g();
  const push = ease(t, T.push, T.s7, E.in), [fx, fy] = deadlineSpot();
  const z = 1 + 2.6 * push, cx = lerp(CX, fx, Math.min(1, push * 1.4)), cy = lerp(CY, fy, Math.min(1, push * 1.4));
  c.save(); c.translate(CX, CY); c.scale(z, z); c.translate(-cx, -cy);
  // the floor, seen from above: boards, and spike tape where things stand
  c.fillStyle = withL(C.ground, L(C.ground) * .85); c.fillRect(-200, -200, W + 400, H + 400);
  for (let j = -2; j < 18; j++) {
    const y = j * 76;
    c.fillStyle = j % 2 ? rgba(C.groundMid, .5) : rgba(C.groundDk, .35); c.fillRect(-200, y, W + 400, 74);
    c.fillStyle = rgba(C.groundDk, .8); c.fillRect(-200, y + 74, W + 400, 2);
    const jx = rnd(j * 13 + 5) * W; c.fillRect(jx, y, 2, 74);
  }
  for (let i = 0; i < 6; i++) {
    const x = 120 + rnd(i * 17 + 3) * (W - 240), y = 60 + rnd(i * 29 + 1) * (H - 120), col = i % 2 ? C.glow : C.glow2;
    if (Math.abs(x - CX) < 700 && Math.abs(y - CY) < 470) continue;
    withT(x, y, rnd(i * 7) * 2, 1, () => { c.fillStyle = col; c.fillRect(-34, -7, 68, 14); c.fillRect(-7, -34, 14, 68); });
  }
  const P = PAPER, inn = ease(t, T.s6 - .1, T.s6 + .45, outSoft);
  withT(P.cx, P.cy + (1 - inn) * 900, P.rot, 1, () => withT(-P.w / 2, -P.h / 2, 0, 1, () => {
    paperSheet(t);
    // gaffer tape on its corners
    for (const [x, y, r] of [[30, 20, -.7], [P.w - 30, 22, .7], [26, P.h - 22, .7], [P.w - 28, P.h - 20, -.7]]) {
      withT(x, y, r, 1, () => { rrect(-70, -20, 140, 40, 3, rgba(withL(C.ground, .14, .3), .92)); c.fillStyle = rgba('#FFFFFF', .07); c.fillRect(-70, -20, 140, 6); });
    }
  }));
  c.restore();
}
/* ------------------------------------------------------------------ S7 and S8: the days left; the stage again */
function scene7(t) {
  const z = SK.kf(t, [[T.s7, 1.85], [T.s7 + .7, ZOOM_SCR[2], E.out], [T.s8, ZOOM_SCR[2] + .06, E.sine]]);
  stageCam([ZOOM_SCR[0], ZOOM_SCR[1], z], () => stage(t, { house: .45, screen: pageCount(t), on: 9, mic: -1 }));
  audience(t);
}
function scene8(t) {
  // out from the screen to the whole stage for the sign and the light, then in on the screen and the sign
  const pull = ease(t, T.s8, T.s8 + 1.6, E.inOut);
  const cam = SK.kf(t, [[T.s8, ZOOM_SCR], [T.s8 + 1.6, [960, 540, 1]], [T.lip + .4, [960, 540, 1]], [T.lip + 3.4, [960, 452, 1.15], E.inOut], [DUR, [960, 446, 1.18], E.sine]]);
  const spotX = SK.kf(t, [[T.s8, 1520], [T.sign2, MIC.x, E.inOut]]);
  const pulse = t > T.sign2 ? 1 + .5 * Math.exp(-(t - T.sign2) * 5) : .9;
  const sw = Math.sin((t - T.s8) * 1.3);
  const spots = [[SPOT, [spotX, MIC.base - 4], 125, pulse],
    [SPOTL, [CX - 360 + sw * 200, FL.back + 160], 120, .55, C.glow], [SPOTR, [CX + 360 - sw * 200, FL.back + 160], 120, .55, C.glow2]];
  stageCam(cam, () => stage(t, {
    house: .5, screen: pageEnd(t), on: 9, spots, mic: 1,
    sign: { str: COPY.cta, land: T.sign2, lit: T.sign2 + .25, flash: t > T.last ? Math.exp(-(t - T.last) * 3) : 0 },
  }));
  if (pull < 1) audience(t, pull * 260);
}

/* ------------------------------------------------------------------ the transitions and the film */
function whip(t, t0, t1, a, b, ang = 0) { // a whip pan from scene a to scene b between t0 and t1
  const u = clamp((t - t0) / (t1 - t0)), e = E.inOut(u), smear = Math.sin(u * Math.PI) * 200;
  const dx = Math.cos(ang), dy = Math.sin(ang), span = Math.abs(dx) > .5 ? W : H;
  if (u < 1) SK.fx(() => a(t), { key: 'wa', dx: -dx * e * span, dy: -dy * e * span, smear, angle: ang });
  if (u > 0) SK.fx(() => b(t), { key: 'wb', dx: dx * (1 - e) * span, dy: dy * (1 - e) * span, smear, angle: ang });
}
function curtains(t, t0, t1, t2) { // the house curtains close from both sides, then open
  const k = t < t1 ? ease(t, t0, t1, E.inOut) : 1 - ease(t, t1, t2, E.inOut); if (k <= 0) return;
  const c = g(), col = mixHex(C.groundDk, C.second, .14), l0 = L(col);
  for (const side of [-1, 1]) {
    const edge = CX + side * (1 - k) * (CX + 60);
    for (let i = 0; i < 14; i++) {
      const x = side < 0 ? edge - (i + 1) * 72 : edge + i * 72, gr = c.createLinearGradient(x, 0, x + 73, 0);
      gr.addColorStop(0, withL(col, l0 * .5)); gr.addColorStop(.5, withL(col, Math.min(.32, l0 * 1.9 + .03))); gr.addColorStop(1, withL(col, l0 * .5));
      c.fillStyle = gr; c.fillRect(x, 0, 73, H);
    }
  }
}
function whiteout(a) { if (a <= 0) return; const c = g(); c.fillStyle = rgba(C.light, a); c.fillRect(0, 0, W, H); }
function draw(t) {
  if (t < T.flash) { scene1(t); whiteout(ease(t, 7.72, T.flash, E.in)); }
  else if (t < 15.75) { scene2(t); whiteout(1 - ease(t, T.flash, T.flash + .4, E.out)); }
  else if (t < 16.25) whip(t, 15.75, 16.25, scene2, scene3, 0);
  else if (t < 31.75) scene3(t);
  else if (t < 32.25) whip(t, 31.75, 32.25, scene3, scene4, Math.PI / 2);
  else if (t < T.curtain) { scene4(t); curtains(t, 41.45, T.curtain, T.curtain + .5); }
  else if (t < 53.75) { scene5(t); curtains(t, 41.45, T.curtain, T.curtain + .5); }
  else if (t < 54.25) whip(t, 53.75, 54.25, scene5, scene6, Math.PI / 2);
  else if (t < T.s7) { scene6(t); whiteout(ease(t, T.s7 - .25, T.s7, E.in) * .9); }
  else if (t < T.s8) { scene7(t); whiteout(.9 * (1 - ease(t, T.s7, T.s7 + .3, E.out))); }
  else scene8(t);
}

/* ------------------------------------------------------------------ the sound
   Worked out from the clock above and from the content, so another call brings its own letters, slides,
   timers, stamps and dates to go with it: `sketch-render.py --sound-data` writes score.json and sfx.json.
   The music is a 120 bpm piece in B minor / D major from a chord chart: a dark pulse while the light
   looks for the microphone, the groove landing with the badge, a stab on every slide, half time and a
   ticking rim for the timers, heavy hits for the stamps, a breakdown for the dates, a roll and a timpani
   swell into the count, and the full groove for the call, ending on a held chord at T.last. */
const beat = (t) => t / BEAT;
const gf = (x) => String(+x.toPrecision(6)); // a number as Python's %g writes it
function scoreData() {
  const CHART = [ // per bar: bass root, its octave, the stab chord, the pad chord
    ['B1', 'B2', 'B3+D4+Gb4', 'B2+Gb3+A3+D4'], // Bm7
    ['G1', 'G2', 'B3+D4+G4', 'G2+D3+Gb3+B3'], // Gmaj7
    ['D2', 'D3', 'A3+D4+Gb4', 'D3+A3+D4+Gb4'], // D
    ['A1', 'A2', 'A3+Db4+E4', 'A2+E3+A3+Db4'], // A
  ];
  const BARS = Math.round(DUR / BAR);
  const at = (b) => CHART[b % 4];
  // what each bar is for (see the clock)
  const part = (b) => b < 1 ? 'dark' : b < 3 ? 'rise' : b < 4 ? 'build' : b < 8 ? 'groove' : b < 13 ? 'slides' : b < 16 ? 'wall'
    : b < 21 ? 'half' : b < 27 ? 'stamps' : b < 34 ? 'dates' : b < 36 ? 'count' : b < 38 ? 'build2' : b < 43 ? 'final' : 'end';
  const GROOVE = { kick: 'x...x...x...x...', clap: '....x.......x...', hat: '..x...x...x...x.', shaker: 'o.o.o.o.o.o.o.o.' };
  const DRUMS = {
    dark: { kick: 'o.......o.......' },
    rise: { kick: 'x.......x.......', hat: '..o...o...o...o.' },
    build: { kick: 'x...x...x...x...', snare: 'o...o...o.o.oooo', hat: 'oooooooooooooooo' },
    groove: GROOVE,
    slides: { ...GROOVE, openhat: '..x...x...x...x.' },
    wall: { ...GROOVE, openhat: '..x...x...x...x.', rim: '...o..o....o..o.' },
    half: { kick: 'x.......x.......', rim: 'x...x...x...x...', snare: '........x.......', hat: 'o.o.o.o.o.o.o.o.' },
    stamps: { ...GROOVE, kick: 'X...x...x...x...', openhat: '..x...x...x...x.' },
    dates: { kick: 'o.......o.......', hat: '..o...o...o...o.', shaker: 'o.o.o.o.o.o.o.o.' },
    count: { kick: 'x...x...x...x...', snare: 'o...o...o...o.o.', hat: 'o.o.o.o.o.o.o.o.' },
    build2: { kick: 'x...x...x...x...', snare: 'o.o.o.o.oooooooo', hat: 'oooooooooooooooo' },
    final: { ...GROOVE, openhat: '..x...x...x...x.', rim: '...o..o....o..o.' },
    end: { kick: 'X...............' },
  };
  const KIT_GAINS = { kick: 1.15, snare: .4, clap: .42, hat: .24, openhat: .15, shaker: .2, rim: .42 };
  const bass = [], sub = [], pad = [], keys = [], brass = [], arp = [];
  for (let b = 0; b < BARS - 1; b++) {
    const [root, octv, stab, chord] = at(b), b0 = b * 4, p = part(b);
    if (p === 'end') break;
    // the bass: a pulse in the dark, eighths in the groove, half notes in half time, held under the dates
    if (p === 'dark' || p === 'rise') for (let k = 0; k < 8; k++) bass.push(`${gf(b0 + k * .5)} ${root} .4 ${(p === 'dark' ? .34 : .46).toFixed(2)}`);
    else if (p === 'half') for (const k of [0, 2]) bass.push(`${gf(b0 + k)} ${root} 1.8 .6`);
    else if (p === 'dates') bass.push(`${gf(b0)} ${root} 3.8 .5`);
    else for (let k = 0; k < 8; k++) bass.push(`${gf(b0 + k * .5)} ${k % 2 ? octv : root} .42 ${(k % 2 ? .52 : .62).toFixed(2)}`);
    sub.push(`${gf(b0)} ${root} ${p === 'dates' || p === 'half' ? 3.8 : 1.8} .7`);
    if (p !== 'dates' && p !== 'half') sub.push(`${gf(b0 + 2)} ${root} 1.8 .7`);
    pad.push(`${gf(b0)} ${chord} 4 ${p === 'dark' ? .32 : p === 'dates' ? .42 : .3}`);
    // keys: off-beat stabs in the groove, chords on one and three under the dates
    if (['groove', 'slides', 'wall', 'half', 'stamps', 'count', 'build2', 'final'].includes(p)) for (const k of [.5, 1.5, 2.5, 3.5]) keys.push(`${gf(b0 + k)} ${stab} .3 ${(k === 1.5 || k === 3.5 ? .34 : .26).toFixed(2)}`);
    if (p === 'dates') for (const k of [0, 2]) keys.push(`${gf(b0 + k)} ${chord} 1.9 .3`);
    // an arpeggio of the chord in sixteenths where the screen fills and for the call
    if (p === 'wall' || p === 'final' || p === 'count' || p === 'build2') {
      const notes = chord.split('+').map((x) => x.replace(/(\d)$/, (d) => String(+d + 1)));
      for (let k = 0; k < 16; k++) arp.push(`${gf(b0 + k * .25)} ${notes[[0, 1, 2, 3, 2, 1][k % 6] % notes.length]} .22 ${(.22 + (k % 4 === 0 ? .1 : 0)).toFixed(2)}`);
    }
  }
  // the stabs: the light finding the microphone, the sign, the badge, each slide, the wall, each stamp, the count and the call
  const HITS = [T.land, T.sign, T.flash, T.s3, ...TOPICS.slice(0, KS).map((_, i) => T.slides + i * BAR), WALL, T.s4,
    ...STAMPS.map((_, i) => T.stamps + i * BAR), T.count, T.s8, T.sign2];
  for (const h of HITS) brass.push(`${gf(beat(h))} ${at(Math.floor(beat(h) / 4))[2]} .9 .6`);
  const FIN = beat(T.last);
  bass.push(`${gf(FIN)} B1 4 .7`); sub.push(`${gf(FIN)} B1 4 .9`);
  pad.push(`${gf(FIN)} B2+Gb3+B3+D4+Gb4 4 .5`); keys.push(`${gf(FIN)} B3+D4+Gb4+A4 3 .45`); brass.push(`${gf(FIN)} D4+Gb4+B4 2.5 .7`);
  const events = [
    { inst: 'synth_bass_1', vel: .9, notes: bass.join('; '), humanize: false },
    { inst: 'sub_bass', vel: 1.0, notes: sub.join('; '), humanize: false },
    { inst: 'electric_piano_1', vel: .8, notes: keys.join('; ') },
    { inst: 'pad_7_halo', vel: .7, notes: pad.join('; ') },
    { inst: 'synth_brass_1', vel: .8, notes: brass.join('; ') },
    { inst: 'celesta', vel: .55, notes: arp.join('; '), humanize: false },
    { type: 'roll', inst: 'timpani', note: 'B1', from: beat(bar(36)), to: beat(T.s8) - .1, step: .125, v0: .1, v1: .62 },
    { type: 'roll', inst: 'timpani', note: 'Gb1', from: beat(bar(3)), to: beat(T.flash) - .1, step: .125, v0: .08, v1: .5 },
  ];
  for (let b = 0; b < BARS; b++) events.push({ type: 'drums', from: b * 4, bars: 1, steps: 16, vel: .85, kit: DRUMS[part(b)], gains: KIT_GAINS });
  return {
    bpm: BPM, drum_gain: .6,
    instruments: {
      synth_bass_1: { g: .6, pan: 0, send: .04, rel: .12 },
      sub_bass: { g: .48, pan: 0, send: 0, rel: .05 },
      electric_piano_1: { g: .3, pan: -.22, send: .3, rel: .25 },
      pad_7_halo: { g: .26, pan: 0, send: .55, rel: .9, soft_attack: true },
      synth_brass_1: { g: .22, pan: .12, send: .35, rel: .35 },
      celesta: { g: .14, pan: .3, send: .4, rel: .4 },
      timpani: { g: .42, pan: 0, send: .4, rel: 1.0 },
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
  const many = new Map(); // one cue holds every time a sound repeats with the same loudness and pan
  const again = (key, t, fx, db, args, pan) => {
    let c = many.get(key);
    if (!c) { c = add(t, fx, db, args, { pan }); c.times = []; many.set(key, c); }
    c.times.push(r(t, 3));
  };
  const impact = (t, db = -12) => { add(t, 'boom', db, { sec: 1.1 }); add(t, 'crash', db - 13, { sec: 1.8 }, { send: .3 }); };
  const PENT = 'D5 E5 Gb5 A5 B5 D6 E6 Gb6 A6 B6 D7 E7 Gb7 A7 B7'.split(' ');
  const signSound = (land, str) => { // the sign flies in, lands; its letters light, a bell each, up the scale
    add(land - .5, 'whoosh', -17, { sec: .55, f0: 260, f1: 2400, peak: .7 });
    add(land, 'thunk', -13, { sec: .4 }); add(land + .02, 'clink', -27, { sec: .5 }, { pan: .3 });
    const n = signLetters(str), step = LETTER(n);
    add(land + .25, 'sample', -17, { inst: 'glockenspiel', notes: Array.from({ length: Math.min(32, n) }, (_, i) => PENT[i % PENT.length]), every: r(step, 4), sec: 1.2 }, { send: .35 });
    for (let i = 0; i < Math.min(n, 30); i++) again('relay ' + (i % 3), land + .25 + i * step, 'click', -29 + (i % 3), { sec: .006, lo: 1200, hi: 5000 }, -.5 + (i % 3) * .5);
  };

  // 1. the stage in the dark: the light looks for the microphone and finds it; the screen; the sign
  add(0, 'rumble', -24, { sec: 2.2 });
  add(.05, 'whoosh', -26, { sec: 1.9, f0: 120, f1: 900, peak: .8, curve: 1.4 }, { pan: -.3 });
  add(T.land, 'thunk', -10, { sec: .5 }); impact(T.land, -15);
  add(T.screen, 'blip', -24, { f: 1760, sec: .08 }); add(T.screen + .02, 'shimmer', -24, { sec: .8, f0: 600, f1: 5200 });
  add(T.screen + .55, 'keys', -32, { sec: .55, rate: 22 });
  signSound(T.sign, COPY.title);
  add(T.sign + .6, 'swoosh_soft', -24, { sec: .8 }, { pan: -.4 }); // the side lights cross
  add(7.2, 'whoosh', -15, { sec: .8, f0: 300, f1: 6000, peak: .95, curve: 1.8 }); // into the white
  impact(T.flash, -12);

  // 2. the badge: it drops on its lanyard, the headline rises, the name types, the press flashes
  add(T.flash + .02, 'whoosh', -16, { sec: .5, f0: 400, f1: 2000, peak: .4 });
  add(T.flash + .5, 'clink', -24, { sec: .6 }, { pan: .4 }); add(T.flash + .52, 'thunk', -19, { sec: .3 });
  add(T.flash + .5, 'swoosh_soft', -26, { sec: .4 }, { pan: -.4 }); add(T.flash + 1.0, 'swoosh_soft', -26, { sec: .4 }, { pan: -.4 });
  add(T.flash + 1.5, 'zip', -26, { sec: .3, f0: 700, f1: 2400 }, { pan: -.3 });
  const you = [...up(COPY.you)].length;
  for (let i = 0; i < Math.min(12, you); i++) again('type', T.type + i * .25, 'click', -18, { sec: .012, lo: 900, hi: 4200 }, .35);
  add(T.flash + 3, 'swoosh_soft', -27, { sec: .45 }, { pan: -.4 });
  for (const tf of [12.0, 12.75, 13.5, 14.5]) { again('shutter', tf, 'click', -20, { sec: .02, lo: 600, hi: 3000 }, 0); again('flash', tf + .01, 'shimmer', -30, { sec: .3, f0: 2000, f1: 7000 }, 0); }
  add(15.7, 'whoosh', -13, { sec: .6, f0: 250, f1: 4500, peak: .55, curve: 1.2 });

  // 3. the slides: a clicker for each, and every topic onto the wall
  add(T.s3 + .1, 'thunk', -20, { sec: .3 });
  for (let i = 0; i < KS; i++) { const tc = T.slides + i * BAR; again('clicker', tc - .14, 'click', -16, { sec: .015, lo: 700, hi: 3500 }, .2); again('push', tc - .12, 'swoosh_soft', -22, { sec: .35 }, 0); }
  again('clicker', WALL - .14, 'click', -16, { sec: .015, lo: 700, hi: 3500 }, .2); again('push', WALL - .12, 'swoosh_soft', -22, { sec: .35 }, 0);
  TOPICS.forEach((_, i) => add(WALL + .3 + i * .125 + .05, 'pop', -26, { f0: 700 + (i % 6) * 110, f1: 260, sec: .07 }, { pan: -.5 + (i % 5) * .25 }));
  const hot0 = WALL + .3 + TOPICS.length * .125 + .3;
  for (let b = Math.ceil((hot0 - WALL) / BEAT); WALL + b * BEAT < T.s4 - .3; b++) again('hot', WALL + b * BEAT, 'blip', -33, { f: 1320, sec: .06 }, .2);
  add(31.7, 'whoosh', -14, { sec: .6, f0: 200, f1: 3800, peak: .5, curve: 1.2 });

  // 4. stage time: the timers land and light; then they run, a tick a beat
  add(T.s4 - .15, 'thunk', -20, { sec: .3 });
  FORMATS.forEach((_, i) => { const t0 = T.timers + i * BEAT; again('timer', t0, 'thunk', -15, { sec: .35 }, -.5 + i * .25); again('led', t0 + .08, 'blip', -26, { f: 2093, sec: .06 }, -.5 + i * .25); });
  for (let b = 0; T.run + b * BEAT < T.curtain - .6; b++) again('tick', T.run + b * BEAT, 'tick', -21 + (b % 2) * 3, {}, b % 2 ? .25 : -.25);
  add(T.curtain - .55, 'swoosh_soft', -14, { sec: .6 }); add(T.curtain + .02, 'swoosh_soft', -16, { sec: .6 }); // the curtains

  // 5. backstage: the pass swings in; each perk is stamped
  add(T.curtain + .3, 'whoosh', -20, { sec: .5, f0: 300, f1: 1800, peak: .4 }, { pan: -.5 });
  add(T.curtain + .78, 'clink', -24, { sec: .6 }, { pan: -.5 });
  add(T.curtain + .5, 'thunk', -22, { sec: .3 });
  STAMPS.forEach((_, i) => { const ts = T.stamps + i * BAR; again('stamp', ts, 'thunk', -9, { sec: .45 }, .3); again('stampboom', ts, 'boom', -19, { sec: .7 }, 0); again('stampclick', ts, 'click', -20, { sec: .01, lo: 900, hi: 3000 }, .3); });
  add(53.7, 'whoosh', -14, { sec: .6, f0: 200, f1: 3800, peak: .5, curve: 1.2 });

  // 6. the key dates: rows typed, the marker strikes, draws today, circles the deadline; the push
  add(T.s6 + .1, 'crinkle', -20, { sec: .35 });
  DATES.forEach((_, i) => again('row', T.rows + i * BEAT, 'keys', -27, { sec: .3, rate: 24 }, 0));
  const pastN = DATES.filter((d) => TODAY !== null && dayN(d.iso) !== null && dayN(d.iso) < TODAY).length;
  for (let i = 0; i < pastN; i++) add(T.marks + i * .2, 'scribble', -22, { sec: .3, seed: i + 1, dens: 1.2 });
  if (TODAY !== null) add(T.marks + .5, 'scribble', -22, { sec: .5, seed: 9, dens: 1 });
  if (DATES.some((d) => d.deadline)) { add(T.marks + 1.0, 'scribble', -19, { sec: .8, seed: 4, dens: 1.4 }); add(T.marks + 1.6, 'scribble', -23, { sec: .4, seed: 6 }); }
  add(T.s7 - 3.5, 'whoosh', -16, { sec: 3.6, f0: 120, f1: 5000, peak: .95, curve: 2.2 });

  // 7. the count: the number rolls down a tick a step and lands
  impact(T.s7, -14);
  if (COUNT && COUNT.n > 0) {
    const n = COUNT.n, digits = String(n).length, n0 = Math.min(Math.pow(10, digits) - 1, n + 20);
    let prev = n0, k = 0;
    for (let tt = T.s7 + .4; tt <= T.count && k < 60; tt += 1 / 120) {
      const v = Math.round(lerp(n0, n, E.out(clamp((tt - (T.s7 + .4)) / (T.count - T.s7 - .4)))));
      if (v !== prev) { again('roll', tt, 'tick', -19, {}, 0); prev = v; k++; }
    }
  }
  impact(T.count, -11);
  add(T.count + .02, 'shimmer', -24, { sec: 1.2, f0: 500, f1: 4000 });
  add(T.s8 - 1.6, 'whoosh', -16, { sec: 1.7, f0: 150, f1: 5000, peak: .95, curve: 2 });

  // 8. the stage again: the call on the sign, the deadline along the edge, the last chord
  impact(T.s8, -11);
  add(T.s8 + .2, 'swoosh_soft', -20, { sec: 1.2 }, { pan: .5 }); // the light swings back
  signSound(T.sign2, COPY.cta);
  add(T.lip, 'keys', -26, { sec: .9, rate: 26 });
  add(T.last, 'crash', -18, { sec: 2.6 }, { send: .4 }); add(T.last, 'shimmer', -24, { sec: 2.0, f0: 400, f1: 6000 });
  return cues.sort((a, b) => a.t - b.t);
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
