/* sketch/collage.js -- paper collage and mixed-media motion design on the sketch engine.

   A module: a film opts in with "modules": ["collage"] in its manifest, and sketch-render
   loads it after engine.js and props.js (the film's own copy first; film.js may override any
   piece). Like the engine it is brand-free and scene-free: it adds
   the pieces a collage is built from, each with an entrance and an exit --

     SK.cutout    a picture with a transparent background (a cut-out made by sketch-paint.py),
                  with the shadow a piece of paper casts on the one below
     SK.sheet     a sheet of paper with torn, deckled or cut edges and its white torn rim
     SK.tape      a strip of paper or tape carrying words (a label, a banner, a caption)
     SK.headline  display type, optionally distressed like letterpress
     SK.stamp     a rubber stamp: a ring with curved words, or a box, printed in ink
     SK.burst     a starburst badge
     SK.halftone  a field of printed dots that fade across it
     SK.ransom    words made of letters cut from different pages
     SK.mark / SK.arrow   a marker line drawn on: arrows, circles, underlines
     SK.maskingTape       a translucent strip of masking tape
     SK.newsprint a newspaper page behind everything (columns of small type)
     SK.layer     a group that enters, leaves and moves together (a sheet and what is on it)

   and the motion they share (SK.motion): `in` / `out` specs {t, type, d, from, dist, spin}
   with types pop, grow, drop, slap, thump, slide, wipe, rise, fade, none. Under
   SK.setStyle('collage') every element also gets the stop-motion nudge -- a pixel or so of
   offset and a hair of turn that changes SK.NUDGE_FPS (12) times a second -- and entrances
   are stepped on twos (style.steps), the way paper animated under a camera moves.

   Every frame is still a pure function of t. The caches below hold pixels derived only from
   the arguments (a sticker with its shadow, a sheet, a stamp); nothing depends on the frames
   drawn before.
*/
(function () {
  'use strict';
  const SK = window.SK;
  const { clamp, lerp, E, mulberry, TAU } = SK;

  SK.STYLES.collage = {
    boil: false, jit: .5, dbl: false, taper: true, misreg: 0, fillTex: false, paper: 'paper',
    grain: .55, vignette: .22, handheld: 0, textWob: 0, textMode: 'rise', grid: null,
    nudge: 1, steps: 12, grainFps: 12,
  };

  /* ------------------------------------------------------------ time on twos, and the nudge */
  SK.NUDGE_FPS = 12;
  /** t held to the last step of a clock ticking fps times a second (After Effects' Posterize Time) */
  SK.step = (t, fps = SK.NUDGE_FPS) => Math.floor(t * fps + 1e-4) / fps;
  /** [dx, dy, rot]: a small offset that changes NUDGE_FPS times a second (0 unless the style nudges) */
  SK.nudge = function (seed, amp = 1) {
    amp *= SK.style.nudge ?? 0;
    if (!amp) return [0, 0, 0];
    const f = Math.floor(SK.T * SK.NUDGE_FPS + 1e-4), r = mulberry((seed * 9973 + f * 7919 + 17) | 0);
    return [(r() - .5) * 2.2 * amp, (r() - .5) * 2.2 * amp, (r() - .5) * .006 * amp];
  };
  const hash = (s) => { let h = 2166136261; s = String(s); for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return (h >>> 0) % 100000; };

  /* ------------------------------------------------------------ entrances and exits */
  const DUR = { pop: .42, grow: .45, drop: .5, slap: .28, thump: .16, slide: .65, wipe: .5, rise: .45, fade: .35, none: 0 };
  const SIDE = { l: [-1, 0], r: [1, 0], t: [0, -1], b: [0, 1] };
  // a soft overshoot for things that land (a sheet sliding home, a picture dropped)
  const land = (t) => { const c1 = 1.1, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
  SK.E.land = land;
  function apply(st, spec, u, leaving) {
    const ty = spec.type || (leaving ? 'fade' : 'pop');
    const dir = SIDE[spec.from] || SIDE[leaving ? 'r' : 'l'];
    switch (ty) {
      case 'pop': st.s *= E.back(u); st.r += (1 - u) * (spec.spin ?? -.22); st.a *= clamp(u * 4); break;
      case 'grow': st.s *= E.out(u); st.a *= clamp(u * 3); break;
      case 'drop': { const d = spec.dist ?? 170; st.dy -= (1 - land(u)) * d; st.s *= 1 + .07 * (1 - u); st.r += (1 - u) * (spec.spin ?? .08); st.a *= clamp(u * 5); break; }
      case 'slap': st.s *= lerp(spec.from0 ?? 1.28, 1, E.out(u)); st.r += (1 - E.out(u)) * (spec.spin ?? .1); st.a *= clamp(u * 6); break;
      case 'thump': st.s *= lerp(spec.from0 ?? 1.7, 1, E.in(u)); st.a *= clamp(u * 1.4); break;
      // a sheet slides home fast and settles without overshoot: a bounce would bare the page under it
      case 'slide': { const d = spec.dist ?? 1500, k = leaving ? E.in(u) : 1 - Math.pow(1 - u, 4); st.dx += dir[0] * (1 - k) * d; st.dy += dir[1] * (1 - k) * d; st.r += (1 - k) * (spec.spin ?? 0); break; }
      case 'wipe': st.wipe = Math.min(st.wipe, leaving ? u : E.inOut(u)); st.wipeFrom = spec.from || 'l'; break;
      case 'rise': st.dy += (1 - E.out(u)) * (spec.dist ?? 40); st.a *= E.out(u); break;
      case 'fade': st.a *= leaving ? u : E.out(u); break;
      default: break; // 'none'
    }
  }
  /**
   * Where an element is at time t, from its `in` and `out` specs ({t, type, d, from, dist, spin}):
   * {a, dx, dy, s, r, wipe, wipeFrom, u}. `steps` (default: the style's) holds the entrance on a
   * clock of that many ticks a second.
   */
  SK.motion = function (o, t = SK.T) {
    const st = { a: 1, dx: 0, dy: 0, s: 1, r: 0, wipe: 1, wipeFrom: 'l', u: 1 };
    const steps = o.steps ?? SK.style.steps, tq = steps ? SK.step(t, steps) : t;
    const I = o.in, O = o.out;
    if (I) {
      if (tq < I.t) { st.a = 0; st.u = 0; return st; }
      const d = I.d ?? DUR[I.type || 'pop'] ?? .4;
      st.u = d > 0 ? clamp((tq - I.t) / d) : 1;
      apply(st, I, st.u, false);
    }
    if (O && tq >= O.t) {
      const d = O.d ?? DUR[O.type || 'fade'] ?? .35;
      apply(st, O, 1 - (d > 0 ? clamp((tq - O.t) / d) : 1), true);
    }
    return st;
  };

  /**
   * Draw fn(ctx, state) in an element's own frame, centred on (o.x, o.y): turned (o.rot), scaled
   * (o.s, o.flip), entered and left (o.in, o.out), nudged (o.nudge: amplitude, 0 for none), faded
   * (o.alpha), blended (o.blend). w, h: the element's size, for a wipe. Returns false when unseen.
   */
  function place(o, w, h, fn) {
    const st = SK.motion(o);
    if (st.a <= 0 || st.s <= 0 || (o.alpha ?? 1) <= 0) return false;
    const c = SK.ctx();
    const nz = o.nudge === 0 || o.nudge === false ? [0, 0, 0] : SK.nudge(o.seed ?? hash([o.x, o.y, w, h].join()), o.nudge ?? 1);
    c.save();
    c.translate((o.x ?? 0) + st.dx + nz[0], (o.y ?? 0) + st.dy + nz[1]);
    const r = (o.rot ?? 0) + st.r + nz[2];
    if (r) c.rotate(r);
    const s = (o.s ?? 1) * st.s;
    if (s !== 1 || o.flip) c.scale(o.flip ? -s : s, s);
    c.globalAlpha *= st.a * (o.alpha ?? 1);
    if (st.wipe < 1) {
      const p = 30, W = w + 2 * p, H = h + 2 * p, x0 = -w / 2 - p, y0 = -h / 2 - p, f = st.wipeFrom;
      c.beginPath();
      if (f === 'r') c.rect(x0 + W * (1 - st.wipe), y0, W * st.wipe, H);
      else if (f === 't') c.rect(x0, y0, W, H * st.wipe);
      else if (f === 'b') c.rect(x0, y0 + H * (1 - st.wipe), W, H * st.wipe);
      else c.rect(x0, y0, W * st.wipe, H);
      c.clip();
    }
    if (o.blend) c.globalCompositeOperation = o.blend;
    try { fn(c, st); } finally { c.restore(); }
    return true;
  }
  SK.place = place;
  /** everything fn draws enters, leaves and moves together: a sheet and what is pinned to it.
   *  o: x, y (the group's origin, default 0, 0), rot, s, in, out, alpha, nudge (default 0), w, h */
  SK.layer = function (o, fn) { return place({ nudge: 0, ...o }, o.w ?? 1920, o.h ?? 1080, fn); };

  /* ------------------------------------------------------------ caches: pixels derived from arguments */
  // least recently used first out, past ~480 MB of pixels: a long film played in one page (the
  // HTML player) would otherwise keep every page it ever showed
  const CACHE = new Map(), CACHE_PX = 120e6;
  let cachePx = 0;
  const pxOf = (v) => (v && v.cv ? v.cv.width * v.cv.height : 1024 * 1024);
  function cached(key, make) {
    let v = CACHE.get(key);
    if (v) { CACHE.delete(key); CACHE.set(key, v); return v; }
    v = make(); CACHE.set(key, v); cachePx += pxOf(v);
    for (const [k, old] of CACHE) {
      if (cachePx <= CACHE_PX || k === key) break;
      CACHE.delete(k); cachePx -= pxOf(old);
    }
    return v;
  }
  function mkCanvas(w, h) { const cv = document.createElement('canvas'); cv.width = Math.max(1, Math.ceil(w)); cv.height = Math.max(1, Math.ceil(h)); return cv; }
  const shadowOf = (o, def) => (o.shadow === false ? null : { ...def, ...(o.shadow || {}) });
  function rgb(hex) { const n = parseInt(String(hex).replace('#', '').slice(0, 6), 16); return [n >> 16, n >> 8 & 255, n & 255]; }
  const lum = (hex) => { const [r, g, b] = rgb(hex); return (.299 * r + .587 * g + .114 * b) / 255; };
  /** dark on a light colour, light on a dark one */
  SK.inkOn = (col, dark = '#1d1a17', light = '#fbf7ee') => (lum(col) > .55 ? dark : light);
  /** the paper's grain in a colour of its own: a pattern made once per colour */
  SK.paperPattern = function (col, strength = 1) {
    return cached('paper|' + col + '|' + strength, () => {
      const [r, g, b] = rgb(col), d = (k) => [Math.round(r * k), Math.round(g * k), Math.round(b * k)].join(',');
      // construction paper: specks and fibres strong enough to read at 1080p, mottling kept soft
      const T = { mottle: d(.55), speck: d(.3), fibre: d(.42), light: '255,255,255', dk: 1.9 * strength, lk: 1.1 * strength, fk: 3.0 * strength };
      return SK.ctx().createPattern(SK.paperCanvas(col, T), 'repeat');
    });
  };

  /* ------------------------------------------------------------ cut-out pictures */
  /**
   * A cut-out: an image with a transparent background (sketch-paint.py "cutout", which may give
   * it a white paper border), w wide, centred on (x, y), casting a paper shadow. o: shadow
   * ({blur, x, y} as fractions of the picture's long side, col; false for none), rot, s, flip,
   * in, out, nudge, alpha. Returns {w, h}.
   */
  SK.cutout = function (name, x, y, w, o = {}) {
    const im = SK.IMG[name];
    if (!im) return { w, h: w };
    const h = w * im.height / im.width;
    const sh = shadowOf(o, { blur: .028, x: .004, y: .014, col: 'rgba(28,18,8,.42)' });
    const S = cached('cut|' + name + '|' + JSON.stringify(sh), () => {
      const L = Math.max(im.width, im.height);
      const pad = sh ? Math.ceil(L * (sh.blur * 1.6 + Math.max(Math.abs(sh.x), Math.abs(sh.y)))) + 4 : 2;
      const cv = mkCanvas(im.width + 2 * pad, im.height + 2 * pad), g = cv.getContext('2d');
      if (sh) { g.shadowColor = sh.col; g.shadowBlur = sh.blur * L; g.shadowOffsetX = sh.x * L; g.shadowOffsetY = sh.y * L; }
      g.drawImage(im, pad, pad);
      return { cv, pad, iw: im.width };
    });
    const k = w / S.iw;
    place({ seed: hash(name), ...o, x, y }, w, h, (c) => c.drawImage(S.cv, -w / 2 - S.pad * k, -h / 2 - S.pad * k, S.cv.width * k, S.cv.height * k));
    return { w, h };
  };

  /* ------------------------------------------------------------ paper sheets with torn edges */
  // offsets along one edge: a slow wander, a medium ripple and a jagged tear
  function tear(len, amp, seed, step) {
    const r = mulberry(seed * 131 + 7), n = Math.max(2, Math.round(len / step)), out = [];
    const p1 = r() * TAU, p2 = r() * TAU, f1 = (1.2 + r() * 1.6) * TAU / len, f2 = (5 + r() * 6) * TAU / len;
    let jag = 0;
    for (let i = 0; i <= n; i++) {
      jag = jag * .5 + (r() - .5);
      out.push(amp * (.5 * Math.sin(i * step * f1 + p1) + .3 * Math.sin(i * step * f2 + p2) + .8 * jag));
    }
    return out;
  }
  // the outline of a w x h sheet (centred on 0, 0) whose `edges` sides are torn: outward offsets
  // of `grow` plus the tear; `inset(s)` pulls a torn side in by a varying rim
  function outline(w, h, edges, amp, seed, grow, inset) {
    const pts = [], step = 5;
    const sides = [ // [x0, y0, x1, y1, normal x, normal y, letter]
      [-w / 2, -h / 2, w / 2, -h / 2, 0, -1, 't'], [w / 2, -h / 2, w / 2, h / 2, 1, 0, 'r'],
      [w / 2, h / 2, -w / 2, h / 2, 0, 1, 'b'], [-w / 2, h / 2, -w / 2, -h / 2, -1, 0, 'l'],
    ];
    sides.forEach(([x0, y0, x1, y1, nx, ny, L], k) => {
      const len = Math.hypot(x1 - x0, y1 - y0), torn = edges.includes(L);
      const off = torn ? tear(len, amp, seed + k * 17, step) : null, n = torn ? off.length - 1 : 1;
      const ins = torn && inset ? tear(len, 1, seed + k * 17 + 500, step * 3) : null;
      for (let i = 0; i < n; i++) {
        const u = i / n, x = lerp(x0, x1, u), y = lerp(y0, y1, u);
        let d = torn ? grow + off[i] : 0;
        if (ins) d -= inset * (.25 + .75 * clamp(.5 + ins[Math.min(ins.length - 1, Math.floor(i / 3))] * .6));
        pts.push([x + nx * d, y + ny * d]);
      }
    });
    return pts;
  }
  const trace = (g, pts) => { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); g.closePath(); };
  /**
   * A sheet of paper, w x h, centred on (x, y). o: col, edges (which sides are torn: any of
   * 'tblr', default all; '' for a cut sheet), amp (how rough the tear, 7), rim (the white torn
   * rim, 6), rimCol, tex (grain strength, 1), light (a soft light across it, .06), seed, shadow
   * ({blur, x, y, col} in px; false), rot, in, out, nudge (default 0: sheets are heavy).
   */
  SK.sheet = function (x, y, w, h, o = {}) {
    const col = o.col ?? '#e8dcc2', edges = o.edges ?? 'tblr', amp = o.amp ?? 7, rim = o.rim ?? 6, seed = o.seed ?? 1;
    const sh = shadowOf(o, { blur: 24, x: 0, y: 9, col: 'rgba(40,25,10,.34)' });
    const key = ['sheet', w, h, col, edges, amp, rim, o.rimCol, o.tex, o.light, seed, JSON.stringify(sh)].join('|');
    const S = cached(key, () => {
      const pad = Math.ceil(amp * 2.5 + (sh ? sh.blur * 1.3 + Math.abs(sh.y) + Math.abs(sh.x) : 0)) + 6;
      const cv = mkCanvas(w + 2 * pad, h + 2 * pad), g = cv.getContext('2d');
      g.translate(w / 2 + pad, h / 2 + pad);
      const outer = outline(w, h, edges, amp, seed, amp * .6, 0), inner = outline(w, h, edges, amp, seed, amp * .6, rim);
      if (sh) { g.save(); g.shadowColor = sh.col; g.shadowBlur = sh.blur; g.shadowOffsetX = sh.x; g.shadowOffsetY = sh.y; }
      trace(g, outer); g.fillStyle = o.rimCol ?? '#f6f1e6'; g.fill();
      if (sh) g.restore();
      g.save(); trace(g, inner); g.clip();
      g.fillStyle = col; g.fillRect(-w, -h, 2 * w, 2 * h);
      if ((o.tex ?? 1) > 0) { g.fillStyle = SK.paperPattern(col, o.tex ?? 1); g.fillRect(-w, -h, 2 * w, 2 * h); }
      const lt = o.light ?? .06;
      if (lt) { const gr = g.createLinearGradient(-w / 2, -h / 2, w / 2, h / 2); gr.addColorStop(0, `rgba(255,255,255,${lt})`); gr.addColorStop(1, `rgba(0,0,0,${lt * .8})`); g.fillStyle = gr; g.fillRect(-w, -h, 2 * w, 2 * h); }
      g.restore();
      return { cv, pad };
    });
    place({ nudge: 0, seed, ...o, x, y }, w, h, (c) => c.drawImage(S.cv, -w / 2 - S.pad, -h / 2 - S.pad));
    return { w, h };
  };

  /* ------------------------------------------------------------ type */
  const fontOf = (o, def) => `${o.italic ? 'italic ' : ''}${o.wt ?? def.wt} ${o.size ?? def.size}px "${o.font ?? def.font}"`;
  // speckle holes and faint mottling in whatever is already drawn on g (ink that did not take)
  function distress(g, w, h, amount, seed) {
    if (!(amount > 0)) return;
    const r = mulberry(seed * 53 + 11);
    g.save();
    g.globalCompositeOperation = 'destination-out';
    const n = Math.round(w * h / 90 * amount);
    for (let i = 0; i < n; i++) {
      const x = r() * w, y = r() * h, s = .6 + r() * r() * 2.6;
      g.globalAlpha = .35 + r() * .65; g.fillRect(x, y, s, s * (.6 + r() * .8));
    }
    for (let i = 0; i < n / 160; i++) { // a few scuffs
      const x = r() * w, y = r() * h, L = 6 + r() * 26, a = r() * TAU;
      g.globalAlpha = .25 + r() * .4; g.lineWidth = .8 + r() * 1.6; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * L, y + Math.sin(a) * L); g.stroke();
    }
    g.globalCompositeOperation = 'source-atop';
    for (let i = 0; i < 18 * amount; i++) {
      const x = r() * w, y = r() * h, rad = 20 + r() * 90, gr = g.createRadialGradient(x, y, 0, x, y, rad);
      gr.addColorStop(0, `rgba(255,255,255,${.12 * amount})`); gr.addColorStop(1, 'rgba(255,255,255,0)');
      g.globalAlpha = 1; g.fillStyle = gr; g.fillRect(x - rad, y - rad, 2 * rad, 2 * rad);
    }
    g.restore();
  }
  let MEASURE = null;
  const MEASURED = new Map();
  function measureLines(font, lines, ls) {
    const key = font + '|' + ls + '|' + lines.join('\u0001');
    let v = MEASURED.get(key);
    if (!v) {
      MEASURE = MEASURE || mkCanvas(4, 4).getContext('2d');
      MEASURE.font = font; MEASURE.letterSpacing = ls + 'px';
      v = lines.map((s) => MEASURE.measureText(s).width);
      if (MEASURED.size > 5000) MEASURED.clear();
      MEASURED.set(key, v);
    }
    return v;
  }
  /**
   * Display type as one piece: a title, a date, a masthead. Anchored at (x, y) by o.align
   * ('center' | 'left' | 'right') and vertically centred. o: font, size, wt, italic, col, ls
   * (letter spacing px), lh (line height, x size), distress (0..1: letterpress ink), stroke
   * ({w, col}: an outline under the fill), maxW (shrink to fit), rot, in, out, nudge, alpha.
   * Returns {w, h}.
   */
  SK.headline = function (text, x, y, o = {}) {
    const lines = String(text).split('\n');
    let size = o.size ?? 90;
    const ls = o.ls ?? 0;
    if (o.maxW) { const w0 = Math.max(...measureLines(fontOf({ ...o, size }, { wt: 400, size, font: 'Abril Fatface' }), lines, ls)); if (w0 > o.maxW) size *= o.maxW / w0; }
    const font = fontOf({ ...o, size }, { wt: 400, size, font: 'Abril Fatface' });
    const key = ['head', text, font, ls, o.col, o.lh, o.distress, o.align, JSON.stringify(o.stroke || 0), o.seed].join('|');
    const S = cached(key, () => {
      const ws = measureLines(font, lines, ls), lh = (o.lh ?? 1.05) * size;
      const w = Math.max(...ws), h = lh * (lines.length - 1) + size * 1.25, pad = Math.ceil(size * .25 + (o.stroke ? o.stroke.w : 0));
      const cv = mkCanvas(w + 2 * pad, h + 2 * pad), g = cv.getContext('2d');
      g.font = font; g.letterSpacing = ls + 'px'; g.textBaseline = 'middle'; g.textAlign = 'center';
      lines.forEach((s, i) => {
        const tx = o.align === 'left' ? pad + ws[i] / 2 : o.align === 'right' ? pad + w - ws[i] / 2 : pad + w / 2, ty = pad + size * .62 + i * lh;
        if (o.stroke) { g.lineJoin = 'round'; g.lineWidth = o.stroke.w; g.strokeStyle = o.stroke.col ?? '#fff'; g.strokeText(s, tx + ls / 2, ty); }
        g.fillStyle = o.col ?? '#1d1a17'; g.fillText(s, tx + ls / 2, ty);
      });
      distress(g, cv.width, cv.height, o.distress ?? 0, o.seed ?? hash(text));
      return { cv, w, h, pad };
    });
    const cx = o.align === 'left' ? x + S.w / 2 : o.align === 'right' ? x - S.w / 2 : x;
    place({ seed: hash(text), ...o, x: cx, y }, S.w, S.h, (c) => c.drawImage(S.cv, -S.w / 2 - S.pad, -S.h / 2 - S.pad));
    return { w: S.w, h: S.h };
  };

  /* ------------------------------------------------------------ tape strips carrying words */
  function stripPath(g, w, h, ends, seed) {
    const r = mulberry(seed * 29 + 5), j = () => (r() - .5) * 3;
    g.beginPath();
    if (ends === 'zig' || ends === 'torn') {
      const n = Math.max(4, Math.round(h / (ends === 'zig' ? 9 : 5)));
      g.moveTo(-w / 2 + j(), -h / 2);
      g.lineTo(w / 2 + j(), -h / 2);
      for (let i = 1; i <= n; i++) g.lineTo(w / 2 + (ends === 'zig' ? (i % 2 ? 5 : -1) : (r() - .5) * 7), -h / 2 + h * i / n);
      g.lineTo(-w / 2 + j(), h / 2);
      for (let i = n - 1; i >= 0; i--) g.lineTo(-w / 2 + (ends === 'zig' ? (i % 2 ? -5 : 1) : (r() - .5) * 7), -h / 2 + h * i / n);
    } else { g.moveTo(-w / 2 + j(), -h / 2 + j()); g.lineTo(w / 2 + j(), -h / 2 + j()); g.lineTo(w / 2 + j(), h / 2 + j()); g.lineTo(-w / 2 + j(), h / 2 + j()); }
    g.closePath();
  }
  /**
   * A strip of paper or tape with words on it, centred on (x, y). o: font ('Oswald'), wt (600),
   * size (36), italic, ls, lh, col (the strip), ink (the words; default reads on col), padX,
   * padY, ends ('cut' | 'torn' | 'zig'), tex (grain), distress, align (of the lines), shadow
   * ({blur, x, y, col}; false), rot (default a slight seeded tilt), in, out, nudge. '\n' breaks
   * lines. Returns {w, h}.
   */
  SK.tape = function (text, x, y, o = {}) {
    const size = o.size ?? 36, col = o.col ?? '#f3ce4f', seed = o.seed ?? hash(text + col);
    const font = fontOf(o, { wt: 600, size, font: 'Oswald' }), ls = o.ls ?? size * .03;
    const sh = shadowOf(o, { blur: 7, x: 1, y: 3, col: 'rgba(30,20,10,.32)' });
    const key = ['tape', text, font, ls, col, o.ink, o.padX, o.padY, o.lh, o.ends, o.tex, o.distress, o.align, seed, JSON.stringify(sh)].join('|');
    const S = cached(key, () => {
      const lines = String(text).split('\n'), ws = measureLines(font, lines, ls), lh = (o.lh ?? 1.08) * size;
      const padX = o.padX ?? size * .42, padY = o.padY ?? size * .2;
      const w = Math.max(...ws) + 2 * padX, h = lh * (lines.length - 1) + size * .98 + 2 * padY;
      const pad = Math.ceil((sh ? sh.blur * 1.4 + Math.abs(sh.y) + Math.abs(sh.x) : 0) + 8);
      const cv = mkCanvas(w + 2 * pad, h + 2 * pad), g = cv.getContext('2d');
      g.translate(w / 2 + pad, h / 2 + pad);
      if (sh) { g.save(); g.shadowColor = sh.col; g.shadowBlur = sh.blur; g.shadowOffsetX = sh.x; g.shadowOffsetY = sh.y; }
      stripPath(g, w, h, o.ends ?? 'cut', seed); g.fillStyle = col; g.fill();
      if (sh) g.restore();
      if ((o.tex ?? .7) > 0) { g.save(); stripPath(g, w, h, o.ends ?? 'cut', seed); g.clip(); g.fillStyle = SK.paperPattern(col, o.tex ?? .7); g.fillRect(-w, -h, 2 * w, 2 * h); g.restore(); }
      g.font = font; g.letterSpacing = ls + 'px'; g.textBaseline = 'middle'; g.textAlign = 'center';
      const ink = o.ink ?? SK.inkOn(col);
      const txt = mkCanvas(w + 2 * pad, h + 2 * pad), tg = txt.getContext('2d');
      tg.font = font; tg.letterSpacing = ls + 'px'; tg.textBaseline = 'middle'; tg.textAlign = 'center'; tg.fillStyle = ink;
      lines.forEach((s, i) => {
        const tx = o.align === 'left' ? pad + padX + ws[i] / 2 : o.align === 'right' ? pad + w - padX - ws[i] / 2 : pad + w / 2;
        tg.fillText(s, tx + ls / 2, pad + padY + size * .52 + i * lh);
      });
      distress(tg, txt.width, txt.height, o.distress ?? .25, seed);
      g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(txt, 0, 0);
      return { cv, w, h, pad };
    });
    const rot = o.rot ?? (mulberry(seed)() - .5) * .07;
    place({ seed, ...o, rot, x, y }, S.w, S.h, (c) => c.drawImage(S.cv, -S.w / 2 - S.pad, -S.h / 2 - S.pad));
    return { w: S.w, h: S.h };
  };
  /** words made of letters cut from different pages, each on its own scrap and landing in turn.
   *  o: size (70), fonts ([[family, weight], ...]), cols (scrap colours), gap, stagger (.06 s),
   *  in ({t, type: 'slap'}), align, seed, rot. Returns the width. */
  SK.ransom = function (text, x, y, o = {}) {
    const size = o.size ?? 70, seed = o.seed ?? hash(text), gap = o.gap ?? size * .1;
    const fonts = o.fonts ?? [['Abril Fatface', 400], ['Oswald', 700], ['Courier Prime', 700], ['Old Standard TT', 700], ['Playfair Display', 900], ['Anton', 400]];
    const cols = o.cols ?? ['#f3ce4f', '#f7f3ea', '#1d1a17', '#e8577e', '#7fcfb4', '#fbfbf7'];
    const chars = [...String(text)], pick = [];
    let total = 0;
    chars.forEach((ch, i) => {
      const r = mulberry(seed * 97 + i * 31);
      if (ch === ' ') { pick.push(null); total += size * .45; return; }
      const f = fonts[Math.floor(r() * fonts.length)], col = cols[Math.floor(r() * cols.length)], sz = size * (.88 + r() * .26);
      const w = measureLines(`${f[1]} ${sz}px "${f[0]}"`, [ch], 0)[0] + sz * .36;
      pick.push({ ch, f, col, sz, w, dy: (r() - .5) * size * .16, rot: (r() - .5) * .22 });
      total += w + gap;
    });
    total -= gap;
    let cx = o.align === 'left' ? x : o.align === 'right' ? x - total : x - total / 2;
    const I = o.in ?? null;
    let k = 0;
    pick.forEach((p) => {
      if (!p) { cx += size * .45; return; }
      SK.tape(p.ch, cx + p.w / 2, y + p.dy, { font: p.f[0], wt: p.f[1], size: p.sz, col: p.col, padX: p.sz * .18, padY: p.sz * .1, rot: p.rot + (o.rot ?? 0), ls: 0, tex: .6, distress: .15, in: I ? { type: 'slap', ...I, t: I.t + k * (o.stagger ?? .06) } : undefined, out: o.out, seed: seed + k });
      cx += p.w + gap; k++;
    });
    return total;
  };

  /* ------------------------------------------------------------ stamps */
  function arcText(g, s, r, center, bottom, size) {
    const chars = [...s], ws = chars.map((c) => g.measureText(c).width), tot = ws.reduce((a, b) => a + b, 0), ang = tot / r;
    let a = center - (bottom ? -ang / 2 : ang / 2);
    chars.forEach((c, i) => {
      const da = ws[i] / r, mid = bottom ? a - da / 2 : a + da / 2;
      g.save(); g.translate(Math.cos(mid) * r, Math.sin(mid) * r); g.rotate(bottom ? mid - Math.PI / 2 : mid + Math.PI / 2); g.fillText(c, 0, 0); g.restore();
      a = bottom ? a - da : a + da;
    });
    return size;
  }
  /**
   * A rubber stamp, centred on (x, y), printed in ink (multiply). o: shape ('circle' | 'rect'),
   * r (circle radius, 110), w/h (rect), text (the big middle), top / bottom (words round the ring,
   * or above / below in a box), col ('#c63a32'), font ('Abril Fatface'), ringFont ('Oswald'),
   * distress (.55), rot (default -.16), alpha (.9), in (default thump at o.t), out, nudge.
   */
  SK.stamp = function (x, y, o = {}) {
    const shape = o.shape ?? 'circle', col = o.col ?? '#c63a32', seed = o.seed ?? hash(JSON.stringify([o.text, o.top, o.bottom]));
    const key = ['stamp', shape, o.r, o.w, o.h, o.text, o.top, o.bottom, col, o.font, o.ringFont, o.distress, seed].join('|');
    const S = cached(key, () => {
      const r = o.r ?? 110, W = shape === 'rect' ? o.w ?? 300 : 2 * r, H = shape === 'rect' ? o.h ?? 130 : 2 * r, pad = 10;
      const cv = mkCanvas(W + 2 * pad, H + 2 * pad), g = cv.getContext('2d');
      g.translate(W / 2 + pad, H / 2 + pad); g.fillStyle = col; g.strokeStyle = col; g.textAlign = 'center'; g.textBaseline = 'middle';
      const fitFont = (s, fam, wt, maxW, maxS) => { let sz = maxS; g.font = `${wt} ${sz}px "${fam}"`; const mw = g.measureText(s).width; if (mw > maxW) sz *= maxW / mw; g.font = `${wt} ${sz}px "${fam}"`; return sz; };
      if (shape === 'rect') {
        g.lineWidth = Math.max(4, H * .05); g.strokeRect(-W / 2 + g.lineWidth, -H / 2 + g.lineWidth, W - 2 * g.lineWidth, H - 2 * g.lineWidth);
        g.lineWidth = Math.max(2, H * .018); g.strokeRect(-W / 2 + H * .11, -H / 2 + H * .11, W - H * .22, H - H * .22);
        const hasTB = o.top || o.bottom;
        if (o.text) fitFont(o.text, o.font ?? 'Abril Fatface', 400, W * .8, H * (hasTB ? .45 : .6)), g.fillText(o.text, 0, hasTB ? H * .02 : H * .04);
        if (o.top) { fitFont(o.top, o.ringFont ?? 'Oswald', 600, W * .7, H * .16); g.fillText(o.top, 0, -H * .3); }
        if (o.bottom) { fitFont(o.bottom, o.ringFont ?? 'Oswald', 600, W * .7, H * .16); g.fillText(o.bottom, 0, H * .31); }
      } else {
        g.lineWidth = r * .055; g.beginPath(); g.arc(0, 0, r * .95, 0, TAU); g.stroke();
        const ring = o.top || o.bottom;
        if (ring) { g.lineWidth = r * .022; g.beginPath(); g.arc(0, 0, r * .66, 0, TAU); g.stroke(); }
        g.font = `600 ${r * .15}px "${o.ringFont ?? 'Oswald'}"`; g.letterSpacing = r * .02 + 'px';
        if (o.top) arcText(g, o.top, r * .8, -Math.PI / 2, false);
        if (o.bottom) arcText(g, o.bottom, r * .8, Math.PI / 2, true);
        g.letterSpacing = '0px';
        if (o.text) { const lines = String(o.text).split('\n'); lines.forEach((s, i) => { const sz = fitFont(s, o.font ?? 'Abril Fatface', 400, r * (ring ? 1.12 : 1.5), r * (ring ? .5 : .62) / Math.max(1, lines.length * .8)); g.fillText(s, 0, (i - (lines.length - 1) / 2) * sz * 1.02 + sz * .04); }); }
      }
      distress(g, cv.width, cv.height, o.distress ?? .55, seed);
      // uneven pressure: one side prints lighter
      g.setTransform(1, 0, 0, 1, 0, 0); g.globalCompositeOperation = 'destination-out';
      const a = mulberry(seed)() * TAU, gr = g.createLinearGradient(cv.width / 2 - Math.cos(a) * W / 2, cv.height / 2 - Math.sin(a) * H / 2, cv.width / 2 + Math.cos(a) * W / 2, cv.height / 2 + Math.sin(a) * H / 2);
      gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(0,0,0,.38)'); g.fillStyle = gr; g.fillRect(0, 0, cv.width, cv.height);
      return { cv, W, H, pad };
    });
    const I = o.in ?? (o.t !== undefined ? { t: o.t, type: 'thump' } : undefined);
    place({ seed, rot: -.16, alpha: .9, blend: 'multiply', ...o, in: I, x, y }, S.W, S.H, (c) => c.drawImage(S.cv, -S.W / 2 - S.pad, -S.H / 2 - S.pad));
    return { w: S.W, h: S.H };
  };

  /* ------------------------------------------------------------ badges and printed dots */
  /** a starburst, radius r, centred on (x, y). o: spikes (24), inner (.8 of r), col, tex, shadow
   *  (px; false), rot, spin (radians a second, stepped), in, out, nudge, seed */
  SK.burst = function (x, y, r, o = {}) {
    const n = o.spikes ?? 24, inner = o.inner ?? .8, col = o.col ?? '#ea5a82', seed = o.seed ?? 3;
    const sh = shadowOf(o, { blur: 16, x: 0, y: 7, col: 'rgba(40,20,10,.3)' });
    const S = cached(['burst', r, n, inner, col, o.tex, seed, JSON.stringify(sh)].join('|'), () => {
      const pad = Math.ceil(sh ? sh.blur * 1.4 + Math.abs(sh.y) : 0) + 4, cv = mkCanvas(2 * (r + pad), 2 * (r + pad)), g = cv.getContext('2d'), rr = mulberry(seed * 7);
      g.translate(r + pad, r + pad);
      const pts = [];
      for (let i = 0; i < 2 * n; i++) { const a = i / (2 * n) * TAU, k = i % 2 ? inner * (.97 + rr() * .06) : .94 + rr() * .06; pts.push([Math.cos(a) * r * k, Math.sin(a) * r * k]); }
      if (sh) { g.save(); g.shadowColor = sh.col; g.shadowBlur = sh.blur; g.shadowOffsetY = sh.y; }
      trace(g, pts); g.fillStyle = col; g.fill();
      if (sh) g.restore();
      if ((o.tex ?? 1) > 0) { g.save(); trace(g, pts); g.clip(); g.fillStyle = SK.paperPattern(col, o.tex ?? 1); g.fillRect(-r, -r, 2 * r, 2 * r); g.restore(); }
      return { cv, pad };
    });
    const tq = SK.style.steps ? SK.step(SK.T) : SK.T;
    place({ seed, ...o, rot: (o.rot ?? 0) + (o.spin ?? 0) * tq, x, y }, 2 * r, 2 * r, (c) => c.drawImage(S.cv, -r - S.pad, -r - S.pad));
  };
  /** a paper circle cut by hand (a sun, a spotlight behind a picture): SK.burst with no points to speak of */
  SK.disc = (x, y, r, o = {}) => SK.burst(x, y, r, { spikes: 90, inner: .992, ...o });
  /**
   * A field of printed dots, w x h, centred on (x, y), largest at `from` and fading away from it.
   * o: col, step (grid pitch, 16), max (largest dot radius, .45 of step), from ('tl' | 'tr' |
   * 'bl' | 'br' | 'l' | 'r' | 't' | 'b' | 'c'), pow (the fall-off, 1.3), angle (the screen, .26),
   * alpha, in, out
   */
  SK.halftone = function (x, y, w, h, o = {}) {
    const step = o.step ?? 16, col = o.col ?? '#e8577e', from = o.from ?? 'tl', max = o.max ?? step * .45, pow = o.pow ?? 1.3, ang = o.angle ?? .26;
    const S = cached(['dots', w, h, step, col, from, max, pow, ang].join('|'), () => {
      const cv = mkCanvas(w, h), g = cv.getContext('2d');
      g.fillStyle = col;
      const src = { tl: [0, 0], tr: [1, 0], bl: [0, 1], br: [1, 1], l: [0, null], r: [1, null], t: [null, 0], b: [null, 1], c: [.5, .5] }[from] || [0, 0];
      const R = Math.hypot(w, h), ca = Math.cos(ang), sa = Math.sin(ang);
      for (let i = -R / step; i < R / step; i++) for (let j = -R / step; j < R / step; j++) {
        const gx = i * step, gy = j * step, px = w / 2 + gx * ca - gy * sa, py = h / 2 + gx * sa + gy * ca;
        if (px < -step || py < -step || px > w + step || py > h + step) continue;
        const u = src[0] === null ? 0 : (px / w - src[0]), v = src[1] === null ? 0 : (py / h - src[1]);
        const d = from === 'c' ? Math.hypot(u, v) * 2 : Math.hypot(u, v) / (src[0] !== null && src[1] !== null ? Math.SQRT2 * .75 : 1);
        const rad = max * Math.pow(clamp(1 - d), pow);
        if (rad > .4) { g.beginPath(); g.arc(px, py, rad, 0, TAU); g.fill(); }
      }
      return { cv };
    });
    place({ nudge: 0, ...o, x, y }, w, h, (c) => c.drawImage(S.cv, -w / 2, -h / 2));
  };

  /* ------------------------------------------------------------ marker marks drawn on */
  /**
   * A marker line along pts (SK.S.line / ell / path), drawn on over in.d seconds (or at o.p).
   * o: col ('#c8322d'), w (6), in ({t, d: .45}), out, p, head (arrowhead size px; 0), seed, jit, alpha
   */
  SK.mark = function (pts, o = {}) {
    if (!pts || pts.length < 2) return;
    const tq = SK.style.steps ? SK.step(SK.T) : SK.T, I = o.in, d = I ? I.d ?? .45 : 0;
    let p = o.p ?? (I ? E.inOut(clamp((tq - I.t) / d)) : 1);
    if (p <= 0) return;
    const col = o.col ?? '#c8322d', w = o.w ?? 6, seed = o.seed ?? hash(pts.length + ':' + pts[0].join());
    place({ nudge: 1, seed, ...o, in: undefined, x: 0, y: 0 }, 1920, 1080, () => {
      SK.ink(pts, { w, col, p, seed, jit: o.jit ?? .7, taper: true, dbl: false });
      const hd = o.head ?? 0;
      if (hd > 0) {
        const hp = I ? clamp((tq - I.t - d) / .12) : 1;
        if (hp > 0) {
          const n = pts.length - 1, a = pts[n], b = pts[Math.max(0, n - 4)], ang = Math.atan2(a[1] - b[1], a[0] - b[0]);
          for (const s of [-1, 1]) SK.ink(SK.S.line(a[0], a[1], a[0] - Math.cos(ang + s * .55) * hd, a[1] - Math.sin(ang + s * .55) * hd), { w: w * .95, col, p: hp, seed: seed + s + 5, jit: .4, dbl: false });
        }
      }
    });
  };
  /** a marker arrow from (x1, y1) to (x2, y2), bowed by o.bow (40); o as SK.mark, head default 24 */
  SK.arrow = function (x1, y1, x2, y2, o = {}) { SK.mark(SK.S.line(x1, y1, x2, y2, o.bow ?? 40), { head: 24, ...o }); };

  /** a strip of masking tape, w long, centred on (x, y): translucent, with torn ends. o: col, h, rot, alpha, in, out */
  SK.maskingTape = function (x, y, w, o = {}) {
    const h = o.h ?? 38, col = o.col ?? 'rgba(236,224,196,.78)', seed = o.seed ?? 9;
    const S = cached(['mtape', w, h, col, seed].join('|'), () => {
      const cv = mkCanvas(w + 16, h + 16), g = cv.getContext('2d'); g.translate(w / 2 + 8, h / 2 + 8);
      stripPath(g, w, h, 'torn', seed); g.fillStyle = col; g.fill();
      g.save(); g.clip(); g.globalAlpha = .5; g.fillStyle = SK.paperPattern('#e8dcc0', .6); g.fillRect(-w, -h, 2 * w, 2 * h); g.restore();
      return { cv };
    });
    place({ seed, rot: -.3, ...o, x, y }, w, h, (c) => c.drawImage(S.cv, -w / 2 - 8, -h / 2 - 8));
  };

  /* ------------------------------------------------------------ the newspaper under it all */
  /**
   * A newspaper page, w x h (2400 x 1400) in world units centred on (x, y) (0, 0): columns of
   * small type under section heads, column rules, a paper colour. Call first in draw(). o: col
   * ('#ebe3d1'), ink ('rgba(52,40,28,.27)'), text (body copy, repeated), heads (section heads),
   * headEvery (how often a line becomes a head, .045), cols (7), size (18), font ('Old Standard
   * TT'), headFont ('Abril Fatface'), seed, alpha
   */
  SK.newsprint = function (o = {}) {
    const W = o.w ?? 2400, H = o.h ?? 1400, col = o.col ?? '#ebe3d1', ink = o.ink ?? 'rgba(52,40,28,.27)', size = o.size ?? 18;
    const text = o.text ?? 'The correspondent reports that the city has never seen a season like it. Crowds gathered at every corner, and the merchants of the old quarter could not keep pace with the demand, which had grown beyond anything recorded in the ledgers of the previous century.';
    const heads = o.heads ?? ['LOCAL NEWS', 'TRADE & COMMERCE', 'NOTICES', 'LETTERS'];
    const key = ['news', W, H, col, ink, size, text, heads.join(','), o.cols, o.font, o.headFont, o.headEvery, o.seed].join('|');
    const S = cached(key, () => {
      const cv = mkCanvas(W, H), g = cv.getContext('2d'), r = mulberry((o.seed ?? 5) * 17);
      g.fillStyle = col; g.fillRect(0, 0, W, H); g.fillStyle = SK.paperPattern(col, .8); g.fillRect(0, 0, W, H);
      const cols = o.cols ?? 7, gut = 34, cw = (W - 80 - gut * (cols - 1)) / cols, words = text.split(/\s+/);
      g.fillStyle = ink; g.strokeStyle = ink; g.textBaseline = 'alphabetic';
      let wi = 0;
      for (let c = 0; c < cols; c++) {
        const x0 = 40 + c * (cw + gut);
        let y = 40 + r() * 40;
        if (c) { g.lineWidth = 1; g.beginPath(); g.moveTo(x0 - gut / 2, 30); g.lineTo(x0 - gut / 2, H - 30); g.stroke(); }
        while (y < H - 30) {
          if (r() < (o.headEvery ?? .045)) { // now and then a section head over the column
            g.font = `400 ${size * 2}px "${o.headFont ?? 'Abril Fatface'}"`; g.letterSpacing = '1px';
            y += size * 2.2; g.fillText(heads[Math.floor(r() * heads.length)], x0, y, cw); g.letterSpacing = '0px';
            y += size * .6; g.fillRect(x0, y, cw, 1.5); y += size * .9;
          }
          g.font = `400 ${size}px "${o.font ?? 'Old Standard TT'}"`;
          let line = '';
          while (true) { const nw = words[wi % words.length]; const test = line ? line + ' ' + nw : nw; if (g.measureText(test).width > cw && line) break; line = test; wi++; }
          y += size * 1.28; g.fillText(line, x0, y);
          if (r() < .04) y += size * 1.2; // paragraph break
        }
      }
      return { cv };
    });
    const c = SK.ctx(), b = c.globalAlpha; c.globalAlpha = b * (o.alpha ?? 1);
    c.drawImage(S.cv, (o.x ?? 0) - W / 2, (o.y ?? 0) - H / 2);
    c.globalAlpha = b;
  };
  /** a newspaper's double rule from x0 to x1 at y (thick over thin). o: col, w (4), gap (6) */
  SK.rules = function (x0, x1, y, o = {}) {
    const c = SK.ctx(), w = o.w ?? 4;
    c.save(); c.fillStyle = o.col ?? '#1d1a17'; c.globalAlpha *= o.alpha ?? 1;
    c.fillRect(x0, y - w / 2, x1 - x0, w); c.fillRect(x0, y + w / 2 + (o.gap ?? 6), x1 - x0, Math.max(1.2, w * .35));
    c.restore();
  };
})();
