// For: developers scrolling LinkedIn and X during a tech week or a conference; calm, precise, exclusive -- the hosts' own developer-tools look (black, light type, two accents), read with the sound off
/* A tech meetup announcement -- 30 s with no narration: every fact is type, and every fact
   comes from FACTS. One page throughout: hairline rules frame it, the series label and the hosts'
   logos settle into its header and come back for the close; a fine dot field lights the hosts' "x"
   and the date. Scenes sit on a 112 bpm grid (a bar 2.14 s; 14 bars = 30 s). */
(function () {
  'use strict';
  const { E, clamp, lerp } = SK;

  /* ================================================================ the event: every fact lives here */
  const FACTS = SK.DATA.content;

  /* ================================================================ look: the hosts' own */
  const K = { bg: '#030303', text: '#f5f5f5', soft: '#8a8a8a', rule: '#262626', dot: '#222222', onPill: '#050505' };
  SK.setStyle('clean', { grain: 0, vignette: 0, handheld: 0 });
  SK.setGround('night', { paper: K.bg, text: K.text, textSoft: K.soft, accent: FACTS.hosts[0].col, accentText: FACTS.hosts[0].col, vignette: '0,0,0' });
  SK.KIT.font = 'Inter'; SK.KIT.mono = 'IBM Plex Mono';
  const ACC = FACTS.hosts.map((h) => h.col), acc = (i) => ACC[i % ACC.length];
  const ctx = () => SK.ctx();
  const sans = (size, wt = 300) => ({ font: 'Inter', wt, size, ls: -size * .035 });
  const mono = (size) => ({ font: 'IBM Plex Mono', wt: 400, size, ls: size * .2, col: K.soft });
  const rule = (pts, p = 1, a = 1) => SK.KIT.line(pts, { col: K.rule, w: 1.5, p, alpha: a, crisp: true, cap: 'butt' });
  const dot = (x, y, r, col) => { const c = ctx(); c.fillStyle = col; c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill(); };
  const X0 = -760, FX = 840, FY = 400; // the text column; the frame's rules

  /* ================================================================ time: scenes in bars */
  const BPM = 112, B = 60 / BPM, BAR = 4 * B, DUR = 30;
  const PLAN = [['open', 2, true], ['name', 2, true], ['who', 2, !!FACTS.audience],
    ['offer', 3, !!FACTS.not || FACTS.beats.length > 0], ['facts', 3, true], ['end', 2, true]].filter((s) => s[2]);
  const SC = {}; let bars = 0;
  PLAN.forEach(([id, n], i) => { SC[id] = { i, t0: bars * BAR, t1: i === PLAN.length - 1 ? DUR : (bars + n) * BAR }; bars += n; });
  const outA = (s, t) => 1 - E.inOut(clamp((t - s.t1 + .4) / .3));
  const live = (s, t) => s && t >= s.t0 - .15 && t <= s.t1;

  /* ================================================================ type */
  /** text slides up into view from under a mask at tin, and up out of it, gone by tout */
  function rise(t, tin, tout, x, y, w, h, fn) {
    const u = E.out(clamp((t - tin) / .6)), v = E.inOut(clamp((t - tout + .4) / .3));
    if (u <= 0 || v >= 1) return;
    const c = ctx(); c.save(); c.beginPath(); c.rect(x - 30, y - h / 2, w + 60, h); c.clip();
    c.translate(0, (1 - u - v) * h * .8); c.globalAlpha *= clamp(u * 1.4) * (1 - v); fn(); c.restore();
  }
  /** a line of words left-aligned at x; the first word matching `accent` in col */
  function words(str, x, y, f, accent, col, base = K.text) {
    const key = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
    let xx = x, lit = false;
    for (const w of str.split(' ')) {
      const on = !lit && !!accent && key(w) === key(accent); if (on) lit = true;
      SK.label(w, xx, y, { ...f, align: 'left', col: on ? col : base });
      xx += SK.measure(w + ' ', f);
    }
  }
  /** a mono label typing on from t0 (left-aligned), with a block caret until o.caret */
  function typeMono(str, x, y, f, t0, t, o = {}) {
    if (!str) return;
    const p = clamp((o.p0 ?? 0) + (t - t0) * (o.cps ?? 30) / str.length), a = o.alpha ?? 1;
    if (p <= 0 || a <= 0) return;
    const s = str.slice(0, Math.ceil(p * str.length));
    SK.label(s, x, y, { ...f, align: 'left', alpha: a });
    if (o.caret && t < o.caret && (p < 1 || Math.floor(t * 2.6) % 2 === 0)) {
      const c = ctx(); c.save(); c.globalAlpha *= a; c.fillStyle = K.soft;
      c.fillRect(x + SK.measure(s, f) + 4, y - f.size * .45, f.size * .55, f.size * .9); c.restore();
    }
  }

  /* ================================================================ the dot field */
  /** the hosts' "x": a 7 x 7 field of fine dots whose diagonals light from the centre out at t0 */
  function dotX(cx, cy, s, t, t0) {
    const n = 7, p = 2 * s / (n - 1), fa = clamp((t - t0 + .35) / .4);
    if (fa <= 0) return;
    SK.alpha(fa, () => {
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        const l = i === j || i + j === n - 1 ? E.out(clamp((t - t0 - Math.abs(i - 3) * .06) / .3)) : 0;
        dot(cx + (i - 3) * p, cy + (j - 3) * p, p * (.12 + .2 * l), l > 0 ? SK.mix(K.dot, '#e6e6e6', l) : K.dot);
      }
    });
  }
  const GLYPH = {
    0: '01110 10001 10001 10001 10001 10001 01110', 1: '00100 01100 00100 00100 00100 00100 01110',
    2: '01110 10001 00001 00010 00100 01000 11111', 3: '11111 00010 00100 00010 00001 10001 01110',
    4: '00010 00110 01010 10010 11111 00010 00010', 5: '11111 10000 11110 00001 00001 10001 01110',
    6: '00110 01000 10000 11110 10001 10001 01110', 7: '11111 00001 00010 00100 01000 01000 01000',
    8: '01110 10001 10001 01110 10001 10001 01110', 9: '01110 10001 10001 01111 00001 00010 01100',
    '.': '00 00 00 00 00 11 11', ':': '00 11 11 00 11 11 00', '-': '0000 0000 0000 1111 0000 0000 0000',
    '/': '00001 00010 00010 00100 01000 01000 10000', ' ': '000 000 000 000 000 000 000',
  };
  /** str in a field of dots fitted to maxW: the field fades in from tf, the glyphs light left to right from tl */
  function matrix(str, cx, cy, maxW, t, tf, tl, col) {
    const gl = [...str].map((ch) => (GLYPH[ch] || GLYPH[' ']).split(' ')), m = 2;
    const cols = gl.reduce((a, g) => a + g[0].length + 1, -1) + 2 * m, rows = 7 + 2 * m;
    const p = Math.min(26, maxW / cols), x0 = cx - (cols - 1) * p / 2, y0 = cy - (rows - 1) * p / 2;
    const lit = new Set(); let cc = m;
    gl.forEach((g) => { g.forEach((row, r) => [...row].forEach((b, k) => { if (b === '1') lit.add(`${cc + k},${r + m}`); })); cc += g[0].length + 1; });
    for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
      const fa = clamp((t - tf - i * .012) / .35); if (fa <= 0) continue;
      const l = lit.has(`${i},${j}`) ? E.out(clamp((t - tl - i * .03 - SK.rnd(i * 31 + j) * .1) / .25)) : 0;
      SK.alpha(fa, () => dot(x0 + i * p, y0 + j * p, p * (.11 + .25 * l), l > 0 ? SK.mix(K.dot, col, l) : K.dot));
    }
  }

  /* ================================================================ the page: rules, header, footer */
  function grid(t) {
    const p = clamp(.3 + .7 * E.out(t / 1.5));
    for (const y of [-FY, FY]) rule([[-1100 * p, y], [1100 * p, y]]);
    for (const x of [-FX, FX]) rule([[x, -700 * p], [x, 700 * p]]);
  }
  /** the hosts' logos in a row (any number), the dotted x between; o.tin: when they land; o.measure */
  function logos(cx, cy, h, t, o = {}) {
    const hs = FACTS.hosts, gap = h * 1.9; // the "x" with air on both sides (1.2 crowded the first logo)
    const ws = hs.map((hh) => { const im = SK.IMG[hh.logo]; return h * (hh.k ?? 1) * (im ? im.width / im.height : 4); });
    const total = ws.reduce((a, b) => a + b, 0) + gap * (hs.length - 1);
    if (o.measure) return total;
    let x = cx - total / 2;
    hs.forEach((hh, i) => {
      const u = E.out(clamp((t - o.tin - i * 2 * B) / .7));
      if (u > 0) SK.image(hh.logo, x + ws[i] / 2, cy + (1 - u) * h * .5, ws[i], 0, { alpha: u });
      x += ws[i];
      if (i < hs.length - 1) { dotX(x + gap / 2, cy, h * .3, t, o.tin + (2 * i + 1) * B); x += gap; }
    });
    return total;
  }
  /** scene 1's label and logos, which settle into the header and come back for the close */
  function header(t) {
    const L = FACTS.series.toUpperCase(), k = E.inOut(clamp((t - SC.name.t0 + .7) / .75));
    const w0 = SK.measure(L, mono(34));
    typeMono(L, lerp(-w0 / 2, -FX, k), lerp(-140, -455, k), mono(lerp(34, 24, k)), 0, t, { p0: .3, cps: 20, caret: 2.6 });
    const fit = (h, maxW) => Math.min(h, h * maxW / logos(0, 0, h, t, { measure: true }));
    const hA = fit(96, 1500), hB = fit(34, 640), hC = fit(96, 1500), wB = logos(0, 0, hB, t, { measure: true });
    const k2 = E.inOut(clamp((t - SC.end.t0 + .2) / .8));
    logos(lerp(lerp(0, FX - wB / 2, k), 0, k2), lerp(lerp(30, -455, k), -190, k2), lerp(lerp(hA, hB, k), hC, k2), t, { tin: -B / 2 });
  }
  function footer(t) {
    const a = Math.min(E.out(clamp((t - SC.name.t0 - .2) / .5)), 1 - E.inOut(clamp((t - SC.end.t0 + .3) / .4)));
    if (a <= 0) return;
    const cur = Math.max(0, PLAN.findIndex(([id]) => t < SC[id].t1)), pad = (n) => String(n).padStart(2, '0');
    SK.label(`${pad(cur + 1)} / ${pad(PLAN.length)}`, -FX, 455, { ...mono(24), align: 'left', alpha: a });
    SK.label(FACTS.hashtag, FX, 455, { ...mono(24), ls: 2, align: 'right', alpha: a });
  }

  /* ================================================================ the scenes */
  /** the name on one line when it sets big enough, else in two balanced lines -> {lines, size} */
  function fitName(str, maxW, max = 220) {
    const one = SK.fit(str, maxW, sans(max)), ws = str.split(' ');
    if (one >= 200 || ws.length < 2) return { lines: [str], size: Math.min(max, one) };
    let best = null;
    for (let i = 1; i < ws.length; i++) {
      const a = ws.slice(0, i).join(' '), b = ws.slice(i).join(' '), w = Math.max(SK.measure(a, sans(max)), SK.measure(b, sans(max)));
      if (!best || w < best.w) best = { lines: [a, b], w };
    }
    return { lines: best.lines, size: Math.min(max, max * maxW / best.w) };
  }
  function sceneName(t) {
    const s = SC.name; if (!live(s, t)) return;
    const { lines, size } = fitName(FACTS.name, 1560), lh = size * 1.04, top = -100 - (lines.length - 1) * lh / 2;
    lines.forEach((ln, i) => rise(t, s.t0 + i * .12, s.t1, X0, top + i * lh, 1600, size * 1.3,
      () => words(ln, X0, top + i * lh, sans(size), FACTS.nameAccent, acc(0))));
    typeMono(FACTS.format.toUpperCase(), X0 + 6, top + (lines.length - 1) * lh + size * .5 + 95, mono(36), s.t0 + .9, t, { alpha: outA(s, t) });
  }
  function sceneWho(t) {
    const s = SC.who; if (!live(s, t)) return;
    let size = 132, lines;
    for (;;) { lines = SK.KIT.wrap(FACTS.audience, 1560, sans(size)); if (lines.length <= 3 || size <= 60) break; size -= 8; }
    const lh = size * 1.1, top = 40 - (lines.length - 1) * lh / 2;
    typeMono(FACTS.labels.who.toUpperCase(), X0 + 4, top - size * .5 - 80, mono(28), s.t0 - .1, t, { alpha: outA(s, t) });
    lines.forEach((ln, i) => rise(t, s.t0 - .05 + i * .14, s.t1, X0, top + i * lh, 1600, size * 1.3,
      () => words(ln, X0, top + i * lh, sans(size), FACTS.audienceAccent, acc(1))));
  }
  function sceneOffer(t) {
    const s = SC.offer; if (!live(s, t)) return;
    const items = FACTS.beats, n = items.length, hasNot = !!FACTS.not, notSize = n ? 64 : 130, out = outA(s, t);
    const pitch = n ? Math.min(165, (hasNot ? 560 : 720) / n) : 0;
    let size = Math.min(112, pitch * .66);
    items.forEach((it) => { size = Math.min(size, SK.fit(it, 1360, sans(size))); });
    let y = -((hasNot ? notSize * 1.2 + (n ? 70 : 0) : 0) + n * pitch) / 2 + 10;
    if (hasNot) {
      const ny = y + notSize * .6, ns = Math.min(notSize, SK.fit(FACTS.not, 1560, sans(notSize)));
      rise(t, s.t0 - .05, s.t1, X0, ny, 1600, notSize * 1.3, () => SK.label(FACTS.not, X0, ny, { ...sans(ns), align: 'left', col: K.soft }));
      y += notSize * 1.2 + (n ? 70 : 0);
    }
    items.forEach((it, i) => {
      const ti = s.t0 + (hasNot ? 2 * B : .1) + i * 2 * B, cy = y + pitch * (i + .5), last = it.split(' ').pop();
      rule([[-FX, y + pitch * i], [FX, y + pitch * i]], E.inOut(clamp((t - ti + .15) / .6)), out);
      if (i === n - 1) rule([[-FX, y + pitch * n], [FX, y + pitch * n]], E.inOut(clamp((t - ti) / .6)), out);
      rise(t, ti, s.t1, X0, cy, 1600, size * 1.3, () => {
        SK.label(String(i + 1).padStart(2, '0'), X0 + 4, cy, { ...mono(28), align: 'left' });
        words(it, X0 + 120, cy, sans(size), last, acc(i));
      });
    });
  }
  function sceneFacts(t) {
    const s = SC.facts; if (!live(s, t)) return;
    const D = FACTS.date, out = outA(s, t), RX = 40, vx = -520, pitch = 150;
    const rows = [[FACTS.labels.date, D ? `${D.weekday}, ${D.month} ${D.day}` : ''], [FACTS.labels.time, FACTS.time], [FACTS.labels.place, FACTS.place]].filter((r) => r[1]);
    const n = rows.length, top = -pitch * n / 2 + 30, vs = Math.min(78, ...rows.map((r) => SK.fit(r[1], RX - vx - 50, sans(78))));
    typeMono(FACTS.labels.details.toUpperCase(), X0 + 4, top - 70, mono(28), s.t0 - .1, t, { alpha: out });
    rows.forEach(([lab, val], i) => {
      const ti = s.t0 - .05 + i * 2 * B, y = top + pitch * (i + .5);
      rule([[-FX, top + pitch * i], [FX, top + pitch * i]], E.inOut(clamp((t - ti + .15) / .6)), out);
      rise(t, ti, s.t1, X0, y, 1600, vs * 1.3, () => {
        SK.label(lab.toUpperCase(), X0 + 4, y, { ...mono(28), align: 'left' });
        SK.label(val, vx, y, { ...sans(vs), align: 'left' });
      });
    });
    rule([[-FX, top + pitch * n], [FX, top + pitch * n]], E.inOut(clamp((t - s.t0 + .05 - (n - 1) * 2 * B) / .6)), out);
    rule([[RX, top], [RX, top + pitch * n]], E.inOut(clamp((t - s.t0 - .1) / .8)), out);
    if (D) SK.alpha(out, () => matrix(`${D.monthNum}.${D.day}`, (RX + FX) / 2, top + pitch * n / 2, 640, t, s.t0 + .2, s.t0 + 6 * B, acc(0)));
  }
  function sceneEnd(t) {
    const s = SC.end; if (t < s.t0) return;
    const ps = SK.fit(FACTS.cta, 1100, { font: 'Inter', wt: 500, size: 54 }), ls = SK.fit(FACTS.link, 1400, sans(72));
    SK.pill(FACTS.cta, 0, 30, { font: 'Inter', wt: 500, size: ps, ls: -.5, fill: K.text, col: K.onPill, padX: 52, padY: 26, in: { t: s.t0 + .55, type: 'rise', d: .6 } });
    SK.label(FACTS.link, 0, 180, { ...sans(ls), col: K.text, in: { t: s.t0 + .85, type: 'rise', d: .6 } });
    SK.label(FACTS.hashtag, 0, 280, { ...mono(34), ls: 4, in: { t: s.t0 + 1.1, type: 'rise', d: .6 } });
  }

  /* ================================================================ the film */
  SK.film({
    duration: DUR,
    camera: SK.camera([[0, [0, 0, 1]], [DUR, [0, 0, 1.04], E.lin]]),
    handheld: false, speedLines: false, fadeOut: .5,
    draw(t) {
      ctx().imageSmoothingQuality = 'high';
      grid(t);
      sceneName(t); sceneWho(t); sceneOffer(t); sceneFacts(t); sceneEnd(t);
      header(t); footer(t);
    },
  });
})();
