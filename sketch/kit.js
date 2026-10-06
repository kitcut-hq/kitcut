/* sketch/kit.js -- the pieces films kept building by hand, for every look.

   A module every studio film loads ("modules": ["kit", ...]) after engine.js and props.js. Each
   piece below was written from scratch, film after film, in the films of 2026-09-28..30 (studio/
   harvest.py read 1,476 hand-built components in 69 of them): use these instead of drawing your own.
   They draw crisp on the clean and collage looks and with the pen on crayon, in the ground's colours
   (C.text, C.accent...) unless told otherwise, and every one is a pure function of t. Positions are
   world units; (x, y) is the piece's anchor (centre unless it says top-left). Text defaults to
   Inter (crisp looks) or Balsamiq Sans (crayon); SK.KIT.font / SK.KIT.mono change that for a film.

   Times and cues
     SK.cues({name: [line, 'word', n?, 'e'?] | seconds})  every cue at once -> {name: seconds};
                                      a word it cannot find warns (SK.KIT.warn) and falls back to its
                                      line's start: no hand-copied fallback seconds
     SK.win(t, t0, t1, fin=.3, fout=.3)   0..1: in over fin from t0, out over fout up to t1
     SK.bump(t, t0, w=.25)            a soft pulse peaking at t0 (a press, a flash, a beat)
     SK.typed(t, t0, n, cps=18)       0..1 typing progress of n characters (for SK.txt's p)
     SK.shake(t, hits, amp=14, d=.5)  [dx, dy] of a jolt dying away after each hit time

   Entrances (moved here from collage.js, so every look has them)
     SK.motion(o) / SK.place(o, w, h, fn) / SK.layer(o, fn)   o.in / o.out = {t, type, d, from,
                                      dist, spin}; types pop grow drop slap thump slide wipe rise
                                      fade none. Every kit piece takes in/out too.
     SK.step(t) / SK.nudge(seed)      time on twos, the stop-motion nudge (collage only)
     SK.mark(pts, o) / SK.arrow(x1, y1, x2, y2, o)   a marker line drawn on (o.in or o.p), o.head
     SK.circle(x, y, rx, ry, o) / SK.underline(x0, x1, y, o) / SK.strike(x0, x1, y, o)
     SK.dimension(x1, y1, x2, y2, label, o)   a measured span: arrowheads both ends, end ticks

   Scenes and camera
     SK.pages([{t, from?, type?, draw(t, local)}], {type: 'slide', d: .7})  -> show(t): each page
                                      comes in over the one before (slide push wipe iris whip fade
                                      cut); a slide/push page paints its own backing (o.bg / page.bg)
     SK.shots([{img, t, cam: [[t, [x, y, zoom]], ...], fade: .8, marks(t)}], {w: 2080})  -> show(t):
                                      paintings one after another, each under its own slow camera,
                                      kept inside the painting (no edge shows)
     SK.breath(camera, {amp: 26, zoom: .035, period: 11})   the camera, never quite still: holds
                                      keep moving (the motion check's 4 s rule) without a hand key
     SK.screen(fn)                    draw fn in screen space (origin at the frame's centre), over the
                                      camera: a HUD, a tracker, a lower third
     SK.safe(kind='16:9')             {x0, y0, x1, y1, w, h} of the title-safe box, or '9:16' -- the
                                      centre column a vertical short is cropped to

   Text
     SK.label(str, x, y, o)           static crisp text -> {w, h}. o: size, font, wt, col, align,
                                      maxW (shrinks to fit), ls, italic, stroke, strokeCol, alpha, in/out
     SK.measure(str, o) -> width      SK.fit(str, maxW, o) -> the size that fits
     SK.para(text, x, y, o)           wrapped lines in o.w, top-left at x, y; p write-on, mode 'rise' |
                                      'type'; -> height
     SK.title(text, x, y, o)          a headline (maxW-fitted) with kicker above, sub below, a rule that
                                      draws on, accent: 'word' in o.accentCol; o.t enters it
     SK.pill(text, x, y, o)           an auto-sized chip -> {w, h}. o: size, fill, col, stroke, icon,
                                      r, padX, align ('center' | 'left'), in/out
     SK.counter(x, y, o)              a number counting from..to over t0..t1. o: fmt ('int' | 'money' |
                                      'mm:ss' | 'pct' | fn), dec, pre, post, size, col
     SK.fmt(v, o)                     the same formatting on its own (thousands separated)
     SK.checklist(items, x, y, o)     rows [{text, t, mark: 'check' | 'cross' | 'dot' | n}] appearing on
                                      their times, marked .35 s later; top-left at x, y; -> height
     SK.cross(x, y, r, p, o)          SK.check's counterpart: a disc with an X drawing on
     SK.callout(text, ax, ay, lx, ly, o)   a dot at the anchor, a leader line that draws on, then the
                                      label at (lx, ly); o.t, ring (circle the anchor), pill, bow
     SK.quote(text, by, x, y, o)      a pull-quote card with its attribution; o.w, t
     SK.lowerThird(name, role, o)     a name card that slides in at o.t (and out at o.until),
                                      screen-space bottom-left unless o.x/o.y

   Data
     SK.bars(data, x, y, o)           [{label, value, col, t}] or numbers, in a w x h box (top-left);
                                      o: dir 'v' | 'h', max, t, stagger, d, values (counting labels),
                                      fmt, highlight, axis
     SK.chart(values, x, y, o)        a line (area: true) drawing on through a w x h box; o: min, max, t,
                                      d, p, col, dot (the moving head), grid, labels, smooth
     SK.donut(data, x, y, r, o)       [{value, col, label}] segments growing in turn; o.thick, centre
     SK.units(n, of, x, y, o)         an icon array: n of `of` filled; o: cols, size, gap, icon, col,
                                      off, t, stagger
     SK.meter(p, x, y, w, o)          a progress bar (top-left); o: h, col, track, label, value
     SK.ring(p, x, y, r, o)           a circular progress arc with its head; o: w, col, track, text
     SK.steps(items, x, y, o)         a stepper / chapter tracker: [{label, t}] dots on a line, the
                                      current one lit, the done ones ticked; o: w, size, numbered
     SK.timeline(events, x, y, o)     an axis with dated milestones [{at, label, sub, t}]; o: w, min,
                                      max, ticks
     SK.flow(nodes, edges, o)         nodes [{id, x, y, label, t, icon}] joined by arrows [[from, to,
                                      {t, bow}]]; o.dots: packets travelling along the links
     SK.stat(x, y, o)                 a card: kicker, a value (counts up when numeric), a caption, icon

   Screens
     SK.window(x, y, w, h, o)         app / browser chrome (top-left): o.title, url, dark, r, content(x0,
                                      y0, w, h) drawn clipped inside
     SK.phone(x, y, o)                a phone (centre), o.s scale, o.screen(x0, y0, w, h) clipped;
                                      o.dark, notch, status (the time shown)
     SK.chat(msgs, x, y, o)           a thread [{who: 'me' | 'them', text, t}] in o.w (top-left):
                                      bubbles, a typing indicator before each 'them', scrolls in o.h
     SK.cursor(x, y, o)               a pointer (o.hand: a hand); o.click: a time or times to press
     SK.cursorPath(keys)              [[t, x, y], ...] -> pos(t), eased between keys
     SK.ripple(x, y, t0, o)           rings spreading from a tap or a click
     SK.button(text, x, y, o)         a button; o.press (a time): it dips and darkens
     SK.field(text, x, y, w, o)       a text field typing text from o.t (cps), caret, o.label above
     SK.toast(title, body, x, y, o)   a notification sliding in at o.t (out at o.until); o.icon
     SK.code(lines, x, y, o)          a code / terminal panel typing its lines from o.t; o.w, prompt
     SK.icon(kind, x, y, r, o)        a line icon (o.fill: solid; o.bg: a disc behind it). kinds:
                                      check cross plus minus arrow play pause mail doc folder image chat
                                      bell user users calendar clock search lock cart card chart gear
                                      globe phone mic heart star home bolt cloud link download upload
                                      money warning info pin flag eye send

   Brand
     SK.logo(name, x, y, o)           a picture from the manifest (an attached logo) fitted in o.w x o.h,
                                      aspect kept; o.plate (a colour, or 'circle'), pad, shadow, in/out
     SK.endCard(o)                    the closing card, screen-space: o.logo, title, tagline, url, cta,
                                      bg, col, accent, t; each piece enters in turn
     SK.palette(brand, o)             brand colours -> {bg, ink, soft, accent, accentInk, on(col)} with
                                      text that reads (contrast 4.5:1); SK.contrast(a, b), SK.readable(bg)

   Places (the map tool's real street map of a real address: never draw a stand-in map)
     SK.map(x, y, o) -> m             the map picture with the address's own spot at (x, y). o: s (scale,
                                      1 = a picture pixel a unit; m.cover is the least that fills the
                                      frame from here), alpha, names (how many real street names to
                                      letter along their streets: 8; 0 for none), nameSize, nameCol,
                                      halo, font, namesT (they fade in), clear: [[x, y, w, h], ...]
                                      (boxes no name is lettered under: a card, a title), own: {col,
                                      w, p} (the address's own street lit, p draws it out), credit
                                      ('bl' | 'br' | 'tl' | 'tr': where '© OpenStreetMap' is lettered --
                                      it must show; false only if you letter it yourself), place (the
                                      data, SK.DATA.place). m.at(u, v) and m.ll(lat, lon) -> [x, y];
                                      m.street -> {x, y, a, name} where the own street's name can go
     SK.mapPin(x, y, o)               a pin whose tip lands on (x, y) at o.t: col, dot, s, drop, pulse

   Light and particles
     SK.glow(x, y, r, col, o)         a soft radial glow (o.alpha, o.blend: 'lighter' | 'screen')
     SK.particles(o)                  a pure-function emitter: x, y (or fn(t)), t0, t1, rate, life,
                                      speed, angle, spread, gravity, size, col (or a list), shape ('dot' |
                                      'square' | 'line' | 'confetti' | 'star' | fn), seed
     SK.pulse(x, y, t0, o)            rings spreading and fading (a status dot, an arrival)
     SK.flash(t, t0, o) / SK.dim(a, col) / SK.spotlight(x, y, r, a)   whole-frame light changes

   Paths: S.len(pts), S.at(pts, u) -> [x, y, angle], S.cut(pts, u0, u1)
*/
// studio: cut -- the code, in the film's engine/kit.js: the header above is the studio's reference
(function () {
  'use strict';
  const SK = window.SK;
  const { clamp, lerp, inv, E, TAU, mulberry, S } = SK;
  const ctx = () => SK.ctx();
  const KIT = (SK.KIT = SK.KIT || { font: null, mono: null, warn: [] });
  const hand = () => !!SK.style.boil; // the crayon look: lines drawn with the pen
  const fam = (o = {}) => o.font ?? KIT.font ?? (hand() ? 'Balsamiq Sans' : 'Inter');
  const monoFam = (o = {}) => o.mono ?? KIT.mono ?? 'IBM Plex Mono';
  const C = () => SK.C;
  const hash = (s) => { let h = 2166136261; s = String(s); for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return (h >>> 0) % 100000; };
  const warn = (msg) => { if (!KIT.warn.includes(msg)) { KIT.warn.push(msg); if (typeof console !== 'undefined') console.warn('kit: ' + msg); } };

  /* ================================================================ time on twos, entrances
     (from collage.js, unchanged: SK.motion, SK.place and SK.layer are what every piece enters by) */
  SK.NUDGE_FPS = SK.NUDGE_FPS ?? 12;
  /** A clock of about `want` ticks a second that divides the frame rate being rendered (SK.FPS) */
  SK.stepFps = function (want = SK.NUDGE_FPS) {
    const f = SK.FPS;
    if (!f || f % want === 0) return want;
    const fits = [8, 9, 10, 11, 12, 13, 14, 15].filter((d) => f % d === 0);
    return fits.length ? fits.reduce((a, d) => (Math.abs(d - want) < Math.abs(a - want) ? d : a)) : want;
  };
  /** t held to the last step of a clock ticking fps times a second (After Effects' Posterize Time) */
  SK.step = (t, fps = SK.NUDGE_FPS) => { const k = SK.stepFps(fps); return Math.floor(t * k + 1e-4) / k; };
  /** [dx, dy, rot]: a small offset that changes NUDGE_FPS times a second (0 unless the style nudges) */
  SK.nudge = function (seed, amp = 1) {
    amp *= SK.style.nudge ?? 0;
    if (!amp) return [0, 0, 0];
    const f = Math.floor(SK.T * SK.stepFps() + 1e-4), r = mulberry((seed * 9973 + f * 7919 + 17) | 0);
    return [(r() - .5) * 2.2 * amp, (r() - .5) * 2.2 * amp, (r() - .5) * .006 * amp];
  };
  const DUR = { pop: .42, grow: .45, drop: .5, slap: .28, thump: .16, slide: .65, wipe: .5, rise: .45, fade: .35, none: 0 };
  const SIDE = { l: [-1, 0], r: [1, 0], t: [0, -1], b: [0, 1] };
  // a soft overshoot for things that land (a sheet sliding home, a picture dropped)
  const land = (t) => { const c1 = 1.1, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
  E.land = land;
  function apply(st, spec, u, leaving) {
    const ty = spec.type || (leaving ? 'fade' : 'pop');
    const dir = SIDE[spec.from] || SIDE[leaving ? 'r' : 'l'];
    switch (ty) {
      case 'pop': st.s *= E.back(u); st.r += (1 - u) * (spec.spin ?? -.22); st.a *= clamp(u * 4); break;
      case 'grow': st.s *= E.out(u); st.a *= clamp(u * 3); break;
      case 'drop': { const d = spec.dist ?? 170; st.dy -= (1 - land(u)) * d; st.s *= 1 + .07 * (1 - u); st.r += (1 - u) * (spec.spin ?? .08); st.a *= clamp(u * 5); break; }
      case 'slap': st.s *= lerp(spec.from0 ?? 1.28, 1, E.out(u)); st.r += (1 - E.out(u)) * (spec.spin ?? .1); st.a *= clamp(u * 6); break;
      case 'thump': st.s *= lerp(spec.from0 ?? 1.7, 1, E.in(u)); st.a *= clamp(u * 1.4); break;
      // slides home fast and settles without overshoot: a bounce would bare the page under it
      case 'slide': { const d = spec.dist ?? 1500, k = leaving ? E.in(u) : 1 - Math.pow(1 - u, 4); st.dx += dir[0] * (1 - k) * d; st.dy += dir[1] * (1 - k) * d; st.r += (1 - k) * (spec.spin ?? 0); break; }
      case 'wipe': st.wipe = Math.min(st.wipe, leaving ? u : E.inOut(u)); st.wipeFrom = spec.from || 'l'; break;
      case 'rise': st.dy += (1 - E.out(u)) * (spec.dist ?? 40); st.a *= E.out(u); break;
      case 'fade': st.a *= leaving ? u : E.out(u); break;
      default: break; // 'none'
    }
  }
  /** Where an element is at time t from its `in` and `out` specs: {a, dx, dy, s, r, wipe, wipeFrom, u} */
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
  /** Draw fn(ctx, state) in an element's own frame centred on (o.x, o.y): turned (o.rot), scaled
   *  (o.s, o.flip), entered and left (o.in, o.out), nudged (o.nudge), faded (o.alpha), blended
   *  (o.blend). w, h: the element's size, for a wipe. Returns false when unseen. */
  function place(o, w, h, fn) {
    const st = SK.motion(o);
    if (st.a <= 0 || st.s <= 0 || (o.alpha ?? 1) <= 0) return false;
    const c = ctx();
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
  /** everything fn draws enters, leaves and moves together. o: x, y, rot, s, in, out, alpha, w, h */
  SK.layer = function (o, fn) { return place({ nudge: 0, ...o }, o.w ?? SK.W, o.h ?? SK.H, fn); };
  // a kit piece at (x, y) with its entrance; w, h its box around (x, y) for a wipe
  const at = (o, x, y, w, h, fn) => place({ nudge: 0, ...o, x, y }, w, h, fn);

  /* ================================================================ drawing: crisp, or the pen */
  function rgb(hex) { const n = parseInt(String(hex).replace('#', '').slice(0, 6), 16); return [n >> 16, n >> 8 & 255, n & 255]; }
  const isHex = (c) => typeof c === 'string' && /^#[0-9a-f]{6}$/i.test(c);
  const lumOf = (hex) => { const [r, g, b] = rgb(hex); return (.299 * r + .587 * g + .114 * b) / 255; };
  /** dark on a light colour, light on a dark one */
  SK.inkOn = SK.inkOn || ((col, dark = '#1d1a17', light = '#fbf7ee') => (lumOf(col) > .55 ? dark : light));
  const alphaOf = (col, a) => { if (!isHex(col)) return col; const [r, g, b] = rgb(col); return `rgba(${r},${g},${b},${a})`; };
  /** a rounded box, top-left at x, y: fill, stroke, w (line), r, shadow ({blur, y, col} | true),
   *  alpha, p (outline draw-on 0..1), seed -- with the pen on crayon */
  function box(x, y, w, h, o = {}) {
    const r = Math.min(o.r ?? 14, w / 2, h / 2), a = o.alpha ?? 1;
    if (a <= 0 || w <= 0 || h <= 0) return;
    const c = ctx();
    if (hand()) {
      const pts = S.rrect(x, y, w, h, Math.max(r, 2));
      SK.alpha(a, () => {
        if (o.fill) SK.wash(pts, o.fill, { seed: o.seed ?? 3, tex: o.tex ?? false, dx: 0, dy: 0, jit: .8 });
        if (o.stroke !== false && (o.stroke || !o.fill)) SK.ink(pts, { w: o.w ?? 4, col: o.stroke || C().ink, seed: (o.seed ?? 3) + 1, p: o.p ?? 1, jit: .9 });
      });
      return;
    }
    c.save(); c.globalAlpha *= a;
    const sh = o.shadow === true ? { blur: 24, y: 10, col: 'rgba(16,23,32,.16)' } : o.shadow;
    if (sh) { c.shadowColor = sh.col ?? 'rgba(16,23,32,.16)'; c.shadowBlur = sh.blur ?? 24; c.shadowOffsetY = sh.y ?? 10; }
    SK.rrPath(x, y, w, h, r);
    if (o.fill) { c.fillStyle = o.fill; c.fill(); }
    c.shadowColor = 'transparent';
    if (o.stroke) {
      c.lineWidth = o.w ?? 2; c.strokeStyle = o.stroke;
      if ((o.p ?? 1) < 1) { const per = 2 * (w + h); c.setLineDash([per * clamp(o.p), per]); }
      c.stroke();
    }
    c.restore();
  }
  KIT.box = box;
  /** a disc: fill, stroke, w, alpha */
  function disc(x, y, r, o = {}) {
    if (r <= 0 || (o.alpha ?? 1) <= 0) return;
    if (hand()) {
      SK.alpha(o.alpha ?? 1, () => {
        if (o.fill) SK.wash(S.ellC(x, y, r, r), o.fill, { seed: o.seed ?? 5, tex: false, dx: 0, dy: 0, jit: .6 });
        if (o.stroke) SK.ink(S.ell(x, y, r, r), { w: o.w ?? 3.5, col: o.stroke, seed: (o.seed ?? 5) + 1, jit: .6 });
      });
      return;
    }
    const c = ctx(); c.save(); c.globalAlpha *= o.alpha ?? 1;
    c.beginPath(); c.arc(x, y, r, 0, TAU);
    if (o.fill) { c.fillStyle = o.fill; c.fill(); }
    if (o.stroke) { c.lineWidth = o.w ?? 2; c.strokeStyle = o.stroke; c.stroke(); }
    c.restore();
  }
  KIT.disc = disc;
  /** a stroked polyline: col, w, p (draw-on), alpha, dash ([on, off]), cap -- the pen on crayon */
  function line(pts, o = {}) {
    if (!pts || pts.length < 2) return;
    const p = o.p ?? 1; if (p <= 0) return;
    if (hand() && !o.crisp) { SK.ink(pts, { w: o.w ?? 4, col: o.col ?? C().text, p, seed: o.seed ?? 7, taper: false, dbl: false, alpha: o.alpha ?? 1, jit: .9 }); return; }
    const q = p < 1 ? S.cut(pts, 0, p) : pts;
    const c = ctx(); c.save(); c.globalAlpha *= o.alpha ?? 1;
    c.strokeStyle = o.col ?? C().text; c.lineWidth = o.w ?? 4; c.lineCap = o.cap ?? 'round'; c.lineJoin = 'round';
    if (o.dash) c.setLineDash(o.dash);
    c.beginPath(); c.moveTo(q[0][0], q[0][1]);
    for (let i = 1; i < q.length; i++) c.lineTo(q[i][0], q[i][1]);
    c.stroke(); c.restore();
  }
  KIT.line = line;
  /** a filled polygon */
  function fillPoly(pts, col, o = {}) {
    if (hand()) { SK.wash(pts, col, { seed: o.seed ?? 9, tex: false, dx: 0, dy: 0, jit: .6, alpha: o.alpha ?? 1 }); return; }
    const c = ctx(); c.save(); c.globalAlpha *= o.alpha ?? 1; c.fillStyle = col;
    c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) c.lineTo(pts[i][0], pts[i][1]); c.closePath(); c.fill(); c.restore();
  }
  /** an arrowhead at the end of pts */
  function head(pts, size, o = {}) {
    const n = pts.length - 1, a = pts[n], b = pts[Math.max(0, n - 3)], ang = Math.atan2(a[1] - b[1], a[0] - b[0]);
    const L = [a[0] - Math.cos(ang - .5) * size, a[1] - Math.sin(ang - .5) * size], R = [a[0] - Math.cos(ang + .5) * size, a[1] - Math.sin(ang + .5) * size];
    if (o.solid) fillPoly([a, L, R], o.col ?? C().text, o);
    else { line([L, a], o); line([R, a], o); }
  }

  /* ================================================================ paths */
  S.len = function (pts) { let s = 0; for (let i = 1; i < pts.length; i++) s += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return s; };
  /** the point u (0..1) of the way along pts by length, and the direction there: [x, y, angle] */
  S.at = function (pts, u) {
    const L = S.len(pts), want = clamp(u) * L; let s = 0;
    for (let i = 1; i < pts.length; i++) {
      const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      if (s + d >= want || i === pts.length - 1) {
        const k = d ? clamp((want - s) / d) : 0;
        return [lerp(pts[i - 1][0], pts[i][0], k), lerp(pts[i - 1][1], pts[i][1], k), Math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])];
      }
      s += d;
    }
    return [pts[0][0], pts[0][1], 0];
  };
  /** the part of pts from u0 to u1 of the way along (by length) */
  S.cut = function (pts, u0, u1) {
    const L = S.len(pts), a = clamp(u0) * L, b = clamp(u1) * L, out = []; let s = 0;
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i - 1], q = pts[i], d = Math.hypot(q[0] - p[0], q[1] - p[1]);
      if (s + d >= a && s <= b) {
        if (!out.length) { const k = d ? clamp((a - s) / d) : 0; out.push([lerp(p[0], q[0], k), lerp(p[1], q[1], k)]); }
        if (s + d <= b) out.push(q);
        else { const k = d ? clamp((b - s) / d) : 0; out.push([lerp(p[0], q[0], k), lerp(p[1], q[1], k)]); break; }
      }
      s += d;
    }
    return out.length > 1 ? out : [pts[0], pts[0]];
  };

  /* ================================================================ times and cues */
  /** {name: [line, 'word', n?, 'e'?] | [line] | seconds} -> {name: seconds}. A word not found warns
   *  and takes its line's start (its end, with 'e'); a line not recorded yet takes `o.fallback`
   *  (default: 0) -- so a film plays before its narration exists and never hides a miss. */
  SK.cues = function (map, o = {}) {
    const out = {};
    for (const [name, v] of Object.entries(map)) {
      if (typeof v === 'number') { out[name] = v; continue; }
      const [li, word, n = 0, edge = 's'] = Array.isArray(v) ? v : [v];
      const L = SK.VO.lines[li];
      if (!L) { out[name] = typeof o.fallback === 'object' ? o.fallback[name] ?? 0 : o.fallback ?? 0; if (SK.VO.lines.length) warn(`cue ${name}: there is no line ${li}`); continue; }
      if (word === undefined || word === null) { out[name] = edge === 'e' ? L.end : L.start; continue; }
      const NaNmark = -1e9, got = SK.w(li, word, NaNmark, edge, n);
      if (got === NaNmark) { warn(`cue ${name}: '${word}' (${n}) is not in line ${li}`); out[name] = edge === 'e' ? L.end : L.start; }
      else out[name] = got;
    }
    return out;
  };
  /** 0..1 visibility: up over fin from t0, down over fout until t1 */
  SK.win = (t, t0, t1, fin = .3, fout = .3) => Math.min(fin > 0 ? E.out(inv(t0, t0 + fin, t)) : (t >= t0 ? 1 : 0), fout > 0 ? 1 - E.in(inv(t1 - fout, t1, t)) : (t <= t1 ? 1 : 0));
  /** a soft pulse 0..1 peaking at t0 */
  SK.bump = (t, t0, w = .25) => Math.exp(-Math.pow((t - t0) / w, 2));
  /** typing progress 0..1 of n characters from t0 at cps characters a second */
  SK.typed = (t, t0, n, cps = 18) => clamp(((SK.style.steps ? SK.step(t) : t) - t0) * cps / Math.max(1, n));
  /** [dx, dy] of a jolt that dies away after each hit (seconds) */
  SK.shake = function (t, hits, amp = 14, d = .5) {
    let dx = 0, dy = 0;
    for (const h of [].concat(hits)) {
      if (t < h || t > h + d) continue;
      const k = Math.exp(-(t - h) * 6 / d) * amp, f = Math.floor(t * 48);
      dx += (SK.rnd(f * 3 + 1) - .5) * 2 * k; dy += (SK.rnd(f * 3 + 2) - .5) * 2 * k;
    }
    return [dx, dy];
  };

  /* ================================================================ marks drawn on (from collage.js) */
  /** A marker line along pts drawn on over in.d seconds (or at o.p). o: col, w (6), in ({t, d}),
   *  out, p, head (arrowhead size; 0), heads (both ends), seed, jit, alpha */
  SK.mark = function (pts, o = {}) {
    if (!pts || pts.length < 2) return;
    const tq = SK.style.steps ? SK.step(SK.T) : SK.T, I = o.in, d = I ? I.d ?? .45 : 0;
    const p = o.p ?? (I ? E.inOut(clamp((tq - I.t) / d)) : 1);
    if (p <= 0) return;
    const col = o.col ?? '#c8322d', w = o.w ?? 6, seed = o.seed ?? hash(pts.length + ':' + pts[0].join());
    place({ nudge: 1, seed, ...o, in: undefined, x: 0, y: 0 }, SK.W, SK.H, () => {
      SK.ink(pts, { w, col, p, seed, jit: o.jit ?? .7, taper: true, dbl: false });
      const hd = o.head ?? 0;
      if (hd > 0) {
        const hp = I ? clamp((tq - I.t - d) / .12) : p >= 1 ? 1 : 0;
        if (hp > 0) {
          for (const end of o.heads ? [pts, pts.slice().reverse()] : [pts]) {
            const n = end.length - 1, a = end[n], b = end[Math.max(0, n - 4)], ang = Math.atan2(a[1] - b[1], a[0] - b[0]);
            for (const s of [-1, 1]) SK.ink(S.line(a[0], a[1], a[0] - Math.cos(ang + s * .55) * hd, a[1] - Math.sin(ang + s * .55) * hd), { w: w * .95, col, p: hp, seed: seed + s + 5, jit: .4, dbl: false });
          }
        }
      }
    });
  };
  /** a marker arrow from (x1, y1) to (x2, y2), bowed by o.bow (40); o as SK.mark, head default 24 */
  SK.arrow = function (x1, y1, x2, y2, o = {}) { SK.mark(S.line(x1, y1, x2, y2, o.bow ?? 40), { head: 24, ...o }); };
  /** a marker ring drawn round (x, y) */
  SK.circle = (x, y, rx, ry, o = {}) => SK.mark(S.ell(x, y, rx, ry ?? rx * .8, -2.4, .35, o.tilt ?? -.06), { w: 6, ...o });
  /** a marker line under a word, from x0 to x1 at y */
  SK.underline = (x0, x1, y, o = {}) => SK.mark(S.line(x0, y, x1, y + (o.slope ?? -3), o.bow ?? 4), { w: 7, ...o });
  /** a marker line through a word */
  SK.strike = (x0, x1, y, o = {}) => SK.mark(S.line(x0 - 6, y + 3, x1 + 6, y - 5, 2), { w: 6, ...o });
  /** a measured span with arrowheads at both ends, end ticks and a label in the middle.
   *  o: col, w, t (draws on from t), off (the ticks' length), size, font, side (+1 | -1) */
  SK.dimension = function (x1, y1, x2, y2, label, o = {}) {
    const t = SK.T, t0 = o.t ?? -1, p = o.p ?? clamp((t - t0) / .5);
    if (p <= 0) return;
    const col = o.col ?? C().text, w = o.w ?? 3, ang = Math.atan2(y2 - y1, x2 - x1), nx = -Math.sin(ang), ny = Math.cos(ang), k = o.off ?? 14;
    line([[x1 - nx * k, y1 - ny * k], [x1 + nx * k, y1 + ny * k]], { col, w, p, crisp: !hand() });
    line([[x2 - nx * k, y2 - ny * k], [x2 + nx * k, y2 + ny * k]], { col, w, p, crisp: !hand() });
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    const half = (a, b) => S.line(a[0], a[1], b[0], b[1]);
    const seg1 = half([mx, my], [x1, y1]), seg2 = half([mx, my], [x2, y2]);
    line(seg1, { col, w, p }); line(seg2, { col, w, p });
    if (p >= 1) { head(seg1, 16, { col, w }); head(seg2, 16, { col, w }); }
    if (label) {
      const side = o.side ?? -1, lx = mx + nx * side * (o.gap ?? 30), ly = my + ny * side * (o.gap ?? 30);
      SK.label(label, lx, ly, { size: o.size ?? 30, col, font: o.font, wt: 700, alpha: clamp(p * 2 - 1), rot: Math.abs(ang) > Math.PI / 2 ? ang + Math.PI : ang });
    }
  };

  /* ================================================================ text */
  // a face without a script falls back to one that has it: Inter has no Cyrillic, Sofia Sans has
  function fontStr(size, wt, f, italic) { return `${italic ? 'italic ' : ''}${wt} ${size}px "${f}", "Sofia Sans", "Balsamiq Sans", sans-serif`; }
  /** the width of str in o's face (size, font, wt, ls, italic) */
  SK.measure = function (str, o = {}) {
    const c = ctx(); c.save(); c.font = fontStr(o.size ?? 40, o.wt ?? 600, fam(o), o.italic);
    if ('letterSpacing' in c) c.letterSpacing = (o.ls ?? 0) + 'px';
    const w = c.measureText(String(str)).width; c.restore();
    return w;
  };
  /** the size (<= o.size) at which str fits maxW */
  SK.fit = function (str, maxW, o = {}) {
    const size = o.size ?? 40, w = SK.measure(str, { ...o, size });
    return w <= maxW ? size : Math.max(o.min ?? 8, Math.floor(size * maxW / w));
  };
  /** Static crisp text: no per-letter animation (SK.txt is the written-on kind). -> {w, h, size}.
   *  o: size, font, wt, col, align ('center' | 'left' | 'right'), base ('middle' | 'alphabetic'),
   *  maxW (shrinks to fit), ls, italic, stroke (outline width), strokeCol, alpha, rot, shadow, in/out */
  SK.label = function (str, x, y, o = {}) {
    str = String(str ?? '');
    const size = o.maxW ? SK.fit(str, o.maxW, o) : o.size ?? 40, wt = o.wt ?? 600;
    const w = SK.measure(str, { ...o, size }), h = size * 1.2;
    const draw = (c) => {
      c.font = fontStr(size, wt, fam(o), o.italic);
      if ('letterSpacing' in c) c.letterSpacing = (o.ls ?? 0) + 'px';
      c.textAlign = o.align === 'left' ? 'left' : o.align === 'right' ? 'right' : 'center';
      c.textBaseline = o.base ?? 'middle';
      if (o.shadow) { c.shadowColor = o.shadow.col ?? 'rgba(0,0,0,.35)'; c.shadowBlur = o.shadow.blur ?? 12; c.shadowOffsetY = o.shadow.y ?? 4; }
      if (o.stroke) { c.lineWidth = o.stroke; c.strokeStyle = o.strokeCol ?? C().ink; c.lineJoin = 'round'; c.strokeText(str, 0, 0); c.shadowColor = 'transparent'; }
      c.fillStyle = o.col ?? C().text; c.fillText(str, 0, 0);
    };
    const bx = o.align === 'left' ? w / 2 : o.align === 'right' ? -w / 2 : 0;
    if (o.in || o.out) at({ ...o, rot: o.rot }, x + bx, y, w, h, (c) => { c.translate(-bx, 0); draw(c); });
    else { const c = ctx(); c.save(); c.globalAlpha *= o.alpha ?? 1; c.translate(x, y); if (o.rot) c.rotate(o.rot); draw(c); c.restore(); }
    return { w, h, size };
  };
  /** lines of text broken to fit w */
  function wrap(text, w, o) {
    const out = [];
    for (const para of String(text).split('\n')) {
      let cur = '';
      for (const word of para.split(/\s+/).filter(Boolean)) {
        const test = cur ? cur + ' ' + word : word;
        if (cur && SK.measure(test, o) > w) { out.push(cur); cur = word; } else cur = test;
      }
      out.push(cur);
    }
    return out;
  }
  KIT.wrap = wrap;
  /** Wrapped text in o.w (top-left at x, y) -> its height. o: size, lh (1.3), font, wt, col, align,
   *  p (0..1 written on across every line), mode ('rise' | 'type'), t + cps (typing from t) */
  SK.para = function (text, x, y, o = {}) {
    const size = o.size ?? 36, lh = size * (o.lh ?? 1.3), w = o.w ?? 900, f = { ...o, size, wt: o.wt ?? 500 };
    const lines = wrap(text, w, f), total = lines.reduce((s, l) => s + l.length, 0);
    const p = o.p ?? (o.t !== undefined ? SK.typed(SK.T, o.t, total, o.cps ?? 30) : 1);
    let done = 0;
    lines.forEach((ln, i) => {
      const q = clamp((p * total - done) / Math.max(1, ln.length)); done += ln.length;
      if (q <= 0) return;
      const ax = o.align === 'center' ? x + w / 2 : o.align === 'right' ? x + w : x, yy = y + lh * (i + .5);
      if (q >= 1 || (o.mode ?? 'type') !== 'type') {
        if (q >= 1) SK.label(ln, ax, yy, { ...f, align: o.align ?? 'left', alpha: o.alpha });
        else SK.label(ln, ax, yy + (1 - E.out(q)) * size * .3, { ...f, align: o.align ?? 'left', alpha: E.out(q) * (o.alpha ?? 1) });
      } else SK.label(ln.slice(0, Math.round(q * ln.length)), ax, yy, { ...f, align: o.align ?? 'left', alpha: o.alpha });
    });
    return lines.length * lh;
  };
  /** A headline with a kicker above, a sub below and a rule that draws on; `accent` names a word set
   *  in accentCol. o: size (96), maxW, font, wt (800), col, kicker, sub, rule (true), accent,
   *  accentCol, align ('left' | 'center'), t (enters from t; else shown), d. -> its height */
  SK.title = function (text, x, y, o = {}) {
    const t = SK.T, t0 = o.t ?? -10, d = o.d ?? .6, align = o.align ?? 'left';
    const size = o.maxW ? SK.fit(text, o.maxW, { ...o, size: o.size ?? 96, wt: o.wt ?? 800 }) : o.size ?? 96;
    const f = { font: o.font, wt: o.wt ?? 800, size };
    let yy = y, h = 0;
    if (o.kicker) {
      const ks = Math.round(size * .3);
      SK.label(String(o.kicker).toUpperCase(), x, yy, { size: ks, wt: 700, ls: ks * .14, col: o.kickerCol ?? C().accentText, align, font: o.font, alpha: SK.win(t, t0, 1e9, d * .6, 0) });
      yy += ks * 1.6; h += ks * 1.6;
    }
    const u = E.out(clamp((t - t0) / d)), ty = yy + size * .5 + (1 - u) * size * .3;
    if (u > 0) {
      if (o.accent && String(text).includes(o.accent)) {
        const [a, b] = String(text).split(o.accent), wa = SK.measure(a, f), wb = SK.measure(o.accent, f), wc = SK.measure(b, f), all = wa + wb + wc;
        const x0 = align === 'center' ? x - all / 2 : x;
        SK.label(a, x0, ty, { ...f, align: 'left', col: o.col, alpha: u });
        SK.label(o.accent, x0 + wa, ty, { ...f, align: 'left', col: o.accentCol ?? C().accentText, alpha: u });
        SK.label(b, x0 + wa + wb, ty, { ...f, align: 'left', col: o.col, alpha: u });
      } else SK.label(text, x, ty, { ...f, align, col: o.col, alpha: u });
    }
    yy += size * 1.05; h += size * 1.05;
    if (o.rule !== false) {
      const wT = SK.measure(text, f), rw = Math.min(wT, o.ruleW ?? wT * .35 + 60), rx = align === 'center' ? x - rw / 2 : x;
      line([[rx, yy + 8], [rx + rw, yy + 8]], { col: o.ruleCol ?? C().accent, w: o.ruleW2 ?? Math.max(4, size * .07), p: E.inOut(clamp((t - t0 - d * .5) / d)), crisp: true });
      yy += 30; h += 30;
    }
    if (o.sub) {
      const ss = o.subSize ?? Math.round(size * .42);
      const hh = SK.para(o.sub, align === 'center' ? x - (o.subW ?? 1100) / 2 : x, yy, { size: ss, w: o.subW ?? 1100, col: o.subCol ?? C().textSoft, align, wt: 500, font: o.font, p: 1, alpha: SK.win(t, t0 + d * .7, 1e9, d, 0) });
      h += hh;
    }
    return h;
  };
  /** An auto-sized chip (centred on x, y unless align 'left') -> {w, h}. o: size (30), font, wt, fill
   *  (C.accent), col (text; reads on fill), stroke, icon (SK.icon kind), r, padX, padY, in/out */
  SK.pill = function (text, x, y, o = {}) {
    const size = o.size ?? 30, padX = o.padX ?? size * .7, padY = o.padY ?? size * .38, f = { size, wt: o.wt ?? 700, font: o.font, ls: o.ls ?? 0 };
    const iw = o.icon ? size * 1.15 : 0, tw0 = text ? SK.measure(text, f) : 0, w = tw0 + iw + 2 * padX - (text ? 0 : padX * .6), h = size + 2 * padY;
    const fill = o.fill ?? C().accent, col = o.col ?? (isHex(fill) ? SK.inkOn(fill) : C().text);
    const cx = o.align === 'left' ? x + w / 2 : x;
    at(o, cx, y, w, h, () => {
      box(-w / 2, -h / 2, w, h, { r: o.r ?? h / 2, fill: o.fill === null ? null : fill, stroke: o.stroke, w: o.strokeW ?? 3, shadow: o.shadow, seed: hash(text) });
      if (o.icon) SK.icon(o.icon, -w / 2 + padX + iw * .4, 0, size * .5, { col, w: Math.max(2.5, size * .1) });
      if (text) SK.label(text, -w / 2 + padX + iw, 1, { ...f, col, align: 'left' });
    });
    return { w, h };
  };
  /** number formatting: o.fmt 'int' | 'money' | 'pct' | 'mm:ss' | 'x' | fn, dec, pre, post, sep (',') */
  SK.fmt = function (v, o = {}) {
    if (typeof o.fmt === 'function') return o.fmt(v);
    const dec = o.dec ?? (o.fmt === 'pct' || o.fmt === 'x' ? 0 : 0), sep = o.sep ?? ',';
    if (o.fmt === 'mm:ss') { const s = Math.max(0, v), m = Math.floor(s / 60), r = s - m * 60; return `${m}:${(dec ? r.toFixed(dec) : Math.floor(r).toString()).padStart(dec ? 3 + dec : 2, '0')}`; }
    const neg = v < 0, a = Math.abs(v), fixed = a.toFixed(dec), [ip, fp] = fixed.split('.');
    const body = ip.replace(/\B(?=(\d{3})+(?!\d))/g, sep) + (fp ? '.' + fp : '');
    const pre = o.pre ?? (o.fmt === 'money' ? '$' : ''), post = o.post ?? (o.fmt === 'pct' ? '%' : o.fmt === 'x' ? '×' : '');
    return (neg ? '−' : '') + pre + body + post;
  };
  /** A number counting from o.from to o.to over o.t0..o.t1 (eased), drawn as a label -> the string */
  SK.counter = function (x, y, o = {}) {
    const t = SK.style.steps ? SK.step(SK.T) : SK.T, u = (o.ease ?? E.out)(inv(o.t0 ?? 0, o.t1 ?? 1, t));
    const v = lerp(o.from ?? 0, o.to ?? 100, u), s = SK.fmt(o.dec ? v : Math.round(v), o);
    if (t >= (o.t0 ?? 0) - (o.lead ?? 0) || o.show) SK.label(s, x, y, { size: o.size ?? 120, wt: o.wt ?? 800, col: o.col, align: o.align, font: o.font, alpha: o.alpha, ls: o.ls, stroke: o.stroke, strokeCol: o.strokeCol, in: o.in });
    return s;
  };
  /** a disc with an X drawing on (p 0..1): the fail mark beside SK.check */
  SK.cross = function (x, y, r, p = 1, o = {}) {
    if (p <= 0) return;
    const s = E.back(clamp(p * 1.6)), c = ctx();
    c.save(); c.translate(x, y); c.scale(s, s);
    disc(0, 0, r, { fill: o.fill ?? '#d64545' });
    const q = clamp(p * 1.6 - .5), k = r * .38, col = o.col ?? '#fff', w = r * .2;
    line([[-k, -k], [k, k]], { col, w, p: clamp(q * 2), crisp: true });
    line([[k, -k], [-k, k]], { col, w, p: clamp(q * 2 - 1), crisp: true });
    c.restore();
  };
  /** Rows [{text, t, mark}] top-left at x, y, each appearing at its t and marked .35 s later; mark
   *  'check' | 'cross' | 'dot' | 'none' | a number. o: w, size (40), gap, col, markCol, sub (a second,
   *  quieter line under each: item.sub), font -> the list's height */
  SK.checklist = function (items, x, y, o = {}) {
    const size = o.size ?? 40, gap = o.gap ?? size * .55, t = SK.T;
    let yy = y;
    items.forEach((it0, i) => {
      const it = typeof it0 === 'string' ? { text: it0, t: (o.t ?? 0) + i * (o.stagger ?? .5) } : it0;
      const t0 = it.t ?? (o.t ?? 0) + i * (o.stagger ?? .5), a = SK.win(t, t0, 1e9, .35, 0), rowH = size * 1.25 + (it.sub ? size * .9 : 0);
      if (a > 0) {
        const mx = x + size * .55, my = yy + size * .62, mark = it.mark ?? o.mark ?? 'check', mp = clamp((t - t0 - (o.markDelay ?? .35)) / .45);
        if (mark === 'check') { if (mp > 0) SK.check(mx, my, size * .5, mp, { fill: it.markCol ?? o.markCol ?? '#2f9e5b' }); else disc(mx, my, size * .46, { stroke: o.ringCol ?? alphaOf(C().textSoft, .6), w: 3, alpha: a }); }
        else if (mark === 'cross') { if (mp > 0) SK.cross(mx, my, size * .5, mp, { fill: it.markCol ?? o.markCol }); else disc(mx, my, size * .46, { stroke: alphaOf(C().textSoft, .6), w: 3, alpha: a }); }
        else if (mark === 'dot') disc(mx, my, size * .16, { fill: it.markCol ?? o.markCol ?? C().accent, alpha: a });
        else if (typeof mark === 'number' || /^\d+$/.test(mark)) { disc(mx, my, size * .5, { fill: it.markCol ?? o.markCol ?? C().accent, alpha: a }); SK.label(String(mark), mx, my + 1, { size: size * .55, wt: 800, col: SK.inkOn(it.markCol ?? o.markCol ?? (isHex(C().accent) ? C().accent : '#d9733f')), alpha: a, font: o.font }); }
        const tx = x + size * 1.45;
        SK.label(it.text, tx + (1 - a) * 20, my, { size, wt: o.wt ?? 600, col: it.col ?? o.col, align: 'left', alpha: a * (it.done === false ? .55 : 1), font: o.font, maxW: o.w ? o.w - size * 1.45 : undefined });
        if (it.sub) SK.label(it.sub, tx + (1 - a) * 20, my + size * .95, { size: size * .62, wt: 500, col: o.subCol ?? C().textSoft, align: 'left', alpha: a, font: o.font, maxW: o.w ? o.w - size * 1.45 : undefined });
      }
      yy += rowH + gap;
    });
    return yy - y - gap;
  };
  /** A dot at the anchor (ax, ay), a leader line drawing on to (lx, ly), then the label there.
   *  o: t (start), col, line ('#'), w, ring (circle the anchor: its radius), pill (label on a chip),
   *  size, bow, side ('auto' | 'left' | 'right': which side of lx the text sits) */
  SK.callout = function (text, ax, ay, lx, ly, o = {}) {
    const t = SK.T, t0 = o.t ?? 0, col = o.col ?? C().text, lc = o.line ?? col;
    if (t < t0) return;
    const p1 = clamp((t - t0) / .35), p2 = clamp((t - t0 - .3) / .45), p3 = clamp((t - t0 - .65) / .35);
    if (o.ring) SK.mark(S.ell(ax, ay, o.ring, o.ring * .85, -2.4, .35), { col: lc, w: 5, p: p1 });
    else disc(ax, ay, o.dot ?? 7, { fill: lc, alpha: p1 });
    const sx = ax + (o.ring ? Math.sign(lx - ax) * o.ring * .9 : 0), pts = S.line(sx, ay, lx, ly, o.bow ?? 0);
    line(pts, { col: lc, w: o.w ?? 3, p: p2, dash: o.dash });
    if (p3 <= 0) return;
    const side = o.side === 'left' || (o.side !== 'right' && lx < ax) ? 'right' : 'left', pad = 12;
    if (o.pill) SK.pill(text, side === 'left' ? lx + pad : lx - pad - SK.measure(text, { size: o.size ?? 30, wt: 700 }) - 2 * (o.size ?? 30) * .7, ly, { size: o.size ?? 30, align: 'left', fill: o.fill ?? C().accent, alpha: p3 });
    else SK.label(text, side === 'left' ? lx + pad : lx - pad, ly, { size: o.size ?? 32, wt: o.wt ?? 700, col, align: side, alpha: p3, font: o.font });
  };
  /** A pull-quote card centred on (x, y): big quote marks, the words wrapped in o.w, the attribution.
   *  o: w (1100), size (54), fill, col, accent, t */
  SK.quote = function (text, by, x, y, o = {}) {
    const w = o.w ?? 1100, size = o.size ?? 54, f = { size, wt: o.wt ?? 600, font: o.font };
    const lines = wrap(text, w - 140, f), h = lines.length * size * 1.28 + (by ? size * 1.4 : 0) + 110;
    at({ in: o.t !== undefined ? { t: o.t, type: o.type ?? 'rise' } : undefined, ...o }, x, y, w, h, () => {
      if (o.fill !== null) box(-w / 2, -h / 2, w, h, { r: o.r ?? 26, fill: o.fill ?? (hand() ? '#fffaf0' : '#ffffff'), shadow: true, stroke: hand() ? C().ink : null });
      SK.label('“', -w / 2 + 70, -h / 2 + 64, { size: size * 2.4, wt: 800, col: o.accent ?? C().accent, font: o.font ?? 'Georgia' });
      SK.para(lines.join('\n'), -w / 2 + 80, -h / 2 + 55, { ...f, w: w - 140, col: o.col ?? '#1d2330', p: 1 });
      if (by) SK.label('— ' + by, -w / 2 + 80, h / 2 - 50, { size: size * .55, wt: 600, col: o.byCol ?? '#5d6677', align: 'left', font: o.font });
    });
  };
  /** A name card: slides in from the left at o.t (out at o.until), screen-space bottom-left unless
   *  o.x / o.y (world). o: fill, col, accent, size (44) */
  SK.lowerThird = function (name, role, o = {}) {
    const t = SK.T, t0 = o.t ?? 0, t1 = o.until ?? 1e9, size = o.size ?? 44;
    const u = E.out(clamp((t - t0) / .55)), v = t > t1 ? 1 - E.in(clamp((t - t1) / .4)) : 1;
    if (u <= 0 || v <= 0) return;
    const draw = () => {
      const wN = SK.measure(name, { size, wt: 800, font: o.font }), wR = role ? SK.measure(role, { size: size * .58, wt: 500, font: o.font }) : 0;
      const w = Math.max(wN, wR) + 80, h = role ? size * 2.25 : size * 1.5, x = o.x ?? -SK.W / 2 + 90, y = o.y ?? SK.H / 2 - 110 - h;
      SK.alpha(v, () => {
        const c = ctx(); c.save(); c.beginPath(); c.rect(x - 20, y - 20, (w + 40) * u, h + 40); c.clip();
        box(x, y, w, h, { r: o.r ?? 10, fill: o.fill ?? 'rgba(17,21,30,.86)', shadow: false });
        box(x, y, 10, h, { r: 4, fill: o.accent ?? (isHex(C().accent) ? C().accent : '#d9733f') });
        SK.label(name, x + 38, y + size * .82, { size, wt: 800, col: o.col ?? '#ffffff', align: 'left', font: o.font });
        if (role) SK.label(role, x + 38, y + size * 1.7, { size: size * .58, wt: 500, col: o.roleCol ?? 'rgba(255,255,255,.78)', align: 'left', font: o.font });
        c.restore();
      });
    };
    if (o.x !== undefined) draw(); else SK.screen(draw);
  };

  /* ================================================================ scenes and camera */
  /** draw fn in screen space: origin at the frame's centre, 1 unit = 1 frame pixel, over the camera */
  SK.screen = function (fn) {
    const c = ctx(); c.save(); c.setTransform(1, 0, 0, 1, SK.W / 2, SK.H / 2);
    try { fn(c); } finally { c.restore(); }
  };
  /** the title-safe box ('16:9': 90% of the frame) or '9:16' (the centre column a vertical short is
   *  cropped to), in screen space centred on 0, 0 */
  SK.safe = function (kind = '16:9') {
    let w = SK.W * .9, h = SK.H * .9;
    if (kind === '9:16') { h = SK.H * .92; w = Math.min(SK.W, SK.H * 9 / 16) * .9; }
    return { x0: -w / 2, y0: -h / 2, x1: w / 2, y1: h / 2, w, h };
  };
  /** Pages one after another, each coming in over the one before: [{t, draw(t, local), from, type,
   *  bg, d}] -> show(t). o: type ('slide' | 'push' | 'wipe' | 'iris' | 'whip' | 'fade' | 'cut'), d (.7),
   *  bg (a colour each slide/push/wipe page is painted on, covering the frame) */
  SK.pages = function (list, o = {}) {
    const pages = list.map((p, i) => ({ i, ...p })).sort((a, b) => a.t - b.t);
    const full = (bg) => { if (!bg) return; const v = SK.view; const c = ctx(); c.save(); c.fillStyle = bg; if (v) c.fillRect(v.x0 - 50, v.y0 - 50, v.x1 - v.x0 + 100, v.y1 - v.y0 + 100); else c.fillRect(-SK.W, -SK.H, 2 * SK.W, 2 * SK.H); c.restore(); };
    return function show(t) {
      let k = -1;
      for (let i = 0; i < pages.length; i++) if (t >= pages[i].t) k = i;
      if (k < 0) return;
      const cur = pages[k], prev = pages[k - 1], type = cur.type ?? o.type ?? 'slide', d = cur.d ?? o.d ?? .7;
      const u = prev ? clamp((t - cur.t) / d) : 1, bg = cur.bg ?? o.bg;
      const drawPage = (p) => { full(p.bg ?? o.bg); p.draw(t, t - p.t); };
      if (u >= 1 || type === 'cut') { drawPage(cur); return; }
      const v = SK.view || { x0: -SK.W / 2, x1: SK.W / 2, y0: -SK.H / 2, y1: SK.H / 2 }, W = v.x1 - v.x0, H = v.y1 - v.y0;
      const dir = SIDE[cur.from ?? o.from ?? 'r'] || SIDE.r, c = ctx();
      if (type === 'fade') { drawPage(prev); SK.alpha(E.inOut(u), () => drawPage(cur)); return; }
      if (type === 'slide' || type === 'push' || type === 'whip') {
        const k2 = type === 'whip' ? E.inOut(u) : 1 - Math.pow(1 - u, 4), dx = dir[0] * (1 - k2) * W, dy = dir[1] * (1 - k2) * H;
        if (type === 'slide') drawPage(prev);
        else SK.at(-dir[0] * k2 * W, -dir[1] * k2 * H, 0, 1, () => drawPage(prev));
        SK.at(dx, dy, 0, 1, () => { if (!(cur.bg ?? o.bg) && type === 'slide') full(C().paper); drawPage(cur); });
        if (type === 'whip') { // the smear of a fast pan
          const a = Math.sin(Math.PI * u) * .55; if (a > .02) SK.screen(() => { const g = ctx(); g.save(); g.globalAlpha = a; for (let i = 0; i < 18; i++) { const y = (SK.rnd(i * 7 + 3) - .5) * SK.H, L = 300 + SK.rnd(i * 3) * 700; g.fillStyle = alphaOf(isHex(C().paper) ? C().paper : '#ffffff', .8); g.fillRect(-SK.W / 2 + SK.rnd(i * 11) * SK.W - L / 2, y, L, 3 + SK.rnd(i) * 10); } g.restore(); });
        }
        return;
      }
      if (type === 'wipe' || type === 'iris') {
        drawPage(prev);
        c.save(); c.beginPath();
        if (type === 'wipe') { const f = cur.from ?? o.from ?? 'l'; const e = E.inOut(u); if (f === 'r') c.rect(v.x1 - W * e, v.y0, W * e, H); else if (f === 't') c.rect(v.x0, v.y0, W, H * e); else if (f === 'b') c.rect(v.x0, v.y1 - H * e, W, H * e); else c.rect(v.x0, v.y0, W * e, H); }
        else { const [ix, iy] = cur.at ?? o.at ?? [(v.x0 + v.x1) / 2, (v.y0 + v.y1) / 2]; c.arc(ix, iy, Math.hypot(W, H) * E.in(u) * .75 + 1, 0, TAU); }
        c.clip(); full(bg ?? C().paper); cur.draw(t, t - cur.t); c.restore();
        return;
      }
      drawPage(cur);
    };
  };
  /** Paintings one after another, each under its own slow camera inside the painting (drawn o.w wide,
   *  default 2080, centred on 0, 0): [{img, t, cam: [[t, [x, y, zoom]], ...] | {from, to}, fade, marks(t)}]
   *  -> show(t). A shot's camera keys are on the film clock; x, y are in the painting's own units
   *  (0, 0 its centre). o.keep (true) holds every shot inside its painting: no edge shows. */
  SK.shots = function (list, o = {}) {
    const IW = o.w ?? 2080, shots = list.slice().sort((a, b) => a.t - b.t);
    const camOf = (s) => {
      if (Array.isArray(s.cam)) return SK.camera(s.cam);
      const nxt = shots[shots.indexOf(s) + 1], t1 = nxt ? nxt.t + (nxt.fade ?? o.fade ?? .8) : (SK._film ? SK._film.duration : s.t + 8);
      const a = (s.cam && s.cam.from) || [0, 0, 1.05], b = (s.cam && s.cam.to) || [0, 0, 1.15];
      return SK.camera([[s.t, a], [t1, b, E.lin]]);
    };
    shots.forEach((s) => { s._cam = camOf(s); });
    const drawShot = (s, t, a) => {
      const im = SK.IMG[s.img], IH = im ? IW * im.height / im.width : IW * 9 / 16;
      let [x, y, z] = s._cam.at(t);
      if (o.keep !== false) { // keep the frame inside the painting
        z = Math.max(z, SK.W / IW * 1.001, SK.H / IH * 1.001);
        const mx = Math.max(0, IW / 2 - SK.W / 2 / z), my = Math.max(0, IH / 2 - SK.H / 2 / z);
        x = clamp(x, -mx, mx); y = clamp(y, -my, my);
      }
      SK.alpha(a, () => SK.screen(() => SK.at(0, 0, 0, z, () => SK.at(-x, -y, 0, 1, () => {
        if (im) SK.image(s.img, 0, 0, IW, IH); else box(-IW / 2, -IH / 2, IW, IH, { fill: '#777', r: 0 });
        if (s.marks) s.marks(t);
      }))));
    };
    return function show(t) {
      let k = -1;
      for (let i = 0; i < shots.length; i++) if (t >= shots[i].t) k = i;
      if (k < 0) return;
      const cur = shots[k], prev = shots[k - 1], fade = cur.fade ?? o.fade ?? .8, u = prev && fade > 0 ? clamp((t - cur.t) / fade) : 1;
      if (u < 1) drawShot(prev, t, 1);
      drawShot(cur, t, u < 1 ? E.inOut(u) : 1);
    };
  };
  /** The camera, never quite still: a slow drift (amp world units) and a slow push (zoom, a fraction)
   *  laid over its own keys, so a hold keeps moving without a hand key. o: amp (26), zoom (.035),
   *  period (11 s), seed */
  SK.breath = function (cam, o = {}) {
    const A = o.amp ?? 26, Z = o.zoom ?? .035, P = o.period ?? 11, ph = (o.seed ?? 1) * 1.7;
    return {
      ...cam,
      at: (t) => {
        const [x, y, z] = cam.at(t), w = TAU / P;
        return [x + A * Math.sin(t * w + ph) / z, y + A * .6 * Math.sin(t * w * .77 + ph * 2) / z, z * (1 + Z * (.5 - .5 * Math.cos(t * w * .5 + ph)))];
      },
    };
  };

  /* ================================================================ data */
  const pal = () => [C().accent, '#2f6fdb', '#2f9e5b', '#e0a32e', '#8e5bd6', '#d64545', '#1aa3a3', '#6b7a8f'];
  const colOf = (d, i, o) => d.col ?? (o.cols ?? pal())[i % (o.cols ?? pal()).length];
  /** Bars in a w x h box, top-left at x, y. data: [{label, value, col, t}] or numbers. o: dir ('v' |
   *  'h'), max, t (first bar), stagger (.25), d (.8), values (true: counting labels), fmt, dec, highlight
   *  (index), axis (true), size (labels), gap (.35 of a slot), font, track (a faint full-length bar) */
  SK.bars = function (data, x, y, o = {}) {
    const rows = data.map((d) => (typeof d === 'number' ? { value: d } : d)), n = rows.length, t = SK.T;
    const w = o.w ?? 900, h = o.h ?? 520, vert = (o.dir ?? 'v') === 'v', max = o.max ?? Math.max(...rows.map((r) => r.value)) * 1.08, size = o.size ?? 30;
    const slot = (vert ? w : h) / n, thick = slot * (1 - (o.gap ?? .35));
    if (o.axis !== false) line(vert ? [[x, y + h], [x + w, y + h]] : [[x, y], [x, y + h]], { col: alphaOf(C().textSoft, .8), w: 3, crisp: true });
    rows.forEach((r, i) => {
      const t0 = r.t ?? (o.t ?? 0) + i * (o.stagger ?? .25), u = (o.ease ?? E.out)(clamp((t - t0) / (o.d ?? .8)));
      const col = colOf(r, i, o), hi = o.highlight === undefined || o.highlight === i ? 1 : .45, L = (vert ? h : w) * clamp(r.value / max) * u;
      if (vert) {
        const bx = x + slot * i + (slot - thick) / 2;
        if (o.track) box(bx, y, thick, h, { r: Math.min(10, thick / 4), fill: alphaOf(C().textSoft, .12) });
        if (L > 0) box(bx, y + h - L, thick, L, { r: Math.min(10, thick / 4, L / 2), fill: col, alpha: hi, seed: i + 11 });
        if (r.label) SK.label(r.label, bx + thick / 2, y + h + size * .9, { size, wt: 600, col: o.labelCol ?? C().text, maxW: slot * .98, font: o.font, alpha: SK.win(t, t0 - .2, 1e9, .3, 0) });
        if (o.values !== false && u > 0) SK.label(SK.fmt(r.value * u, { ...o, dec: o.dec ?? (r.value % 1 ? 1 : 0) }), bx + thick / 2, y + h - L - size * .8, { size: size * 1.1, wt: 800, col: o.valueCol ?? C().text, font: o.font, alpha: clamp(u * 3) * hi });
      } else {
        const by = y + slot * i + (slot - thick) / 2;
        if (o.track) box(x, by, w, thick, { r: Math.min(10, thick / 4), fill: alphaOf(C().textSoft, .12) });
        if (L > 0) box(x, by, L, thick, { r: Math.min(10, thick / 4, L / 2), fill: col, alpha: hi, seed: i + 11 });
        if (r.label) SK.label(r.label, x - 16, by + thick / 2, { size, wt: 600, col: o.labelCol ?? C().text, align: 'right', font: o.font, alpha: SK.win(t, t0 - .2, 1e9, .3, 0) });
        if (o.values !== false && u > 0) SK.label(SK.fmt(r.value * u, { ...o, dec: o.dec ?? (r.value % 1 ? 1 : 0) }), x + L + 14, by + thick / 2, { size: size * 1.05, wt: 800, col: o.valueCol ?? C().text, align: 'left', font: o.font, alpha: clamp(u * 3) * hi });
      }
    });
  };
  /** A line drawing on through a w x h box (top-left at x, y). values: numbers (evenly spaced) or
   *  [[x, v], ...]. o: min, max, t, d (1.6), p, col, w (6), area (true: filled under), dot (true: the
   *  moving head), grid (n lines), labels ([first, last] under the axis), smooth (true), end (a label
   *  at the head when done) */
  SK.chart = function (values, x, y, o = {}) {
    const w = o.w ?? 900, h = o.h ?? 480, pts0 = values.map((v, i) => (Array.isArray(v) ? v : [i, v]));
    const xs = pts0.map((p) => p[0]), vs = pts0.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), lo = o.min ?? Math.min(...vs), hi = o.max ?? Math.max(...vs), span = hi - lo || 1;
    const P = pts0.map(([a, v]) => [x + (a - x0) / ((x1 - x0) || 1) * w, y + h - (v - lo) / span * h]);
    let pts = P;
    if (o.smooth !== false && P.length > 2) { pts = []; for (let i = 0; i < P.length - 1; i++) { const a = P[Math.max(0, i - 1)], b = P[i], c2 = P[i + 1], d = P[Math.min(P.length - 1, i + 2)]; for (let k = 0; k < 8; k++) { const u = k / 8, u2 = u * u, u3 = u2 * u; pts.push([.5 * (2 * b[0] + (-a[0] + c2[0]) * u + (2 * a[0] - 5 * b[0] + 4 * c2[0] - d[0]) * u2 + (-a[0] + 3 * b[0] - 3 * c2[0] + d[0]) * u3), .5 * (2 * b[1] + (-a[1] + c2[1]) * u + (2 * a[1] - 5 * b[1] + 4 * c2[1] - d[1]) * u2 + (-a[1] + 3 * b[1] - 3 * c2[1] + d[1]) * u3)]); } } pts.push(P[P.length - 1]); }
    const p = o.p ?? (o.t !== undefined ? E.inOut(clamp((SK.T - o.t) / (o.d ?? 1.6))) : 1), col = o.col ?? C().accent;
    for (let g = 0; g <= (o.grid ?? 3); g++) { if (!o.grid && g) break; const gy = y + h * g / Math.max(1, o.grid ?? 3); line([[x, gy], [x + w, gy]], { col: alphaOf(C().textSoft, g === (o.grid ?? 3) ? .7 : .22), w: 2, crisp: true }); }
    if (p <= 0) return;
    const part = S.cut(pts, 0, p);
    if (o.area !== false) { const c = ctx(); c.save(); const g = c.createLinearGradient(0, y, 0, y + h); g.addColorStop(0, alphaOf(isHex(col) ? col : '#2f6fdb', .32)); g.addColorStop(1, alphaOf(isHex(col) ? col : '#2f6fdb', 0)); c.fillStyle = g; c.beginPath(); c.moveTo(part[0][0], y + h); part.forEach((q) => c.lineTo(q[0], q[1])); c.lineTo(part[part.length - 1][0], y + h); c.closePath(); c.fill(); c.restore(); }
    line(part, { col, w: o.lw ?? 6, crisp: !hand() });
    const tip = part[part.length - 1];
    if (o.dot !== false) { disc(tip[0], tip[1], 11, { fill: col }); SK.pulse(tip[0], tip[1], (o.t ?? 0) + (o.d ?? 1.6), { col, r1: 40, n: 1, every: 1.4 }); }
    if (o.end && p >= 1) SK.pill(o.end, tip[0] + 20, tip[1] - 46, { size: 28, align: 'left', fill: col, in: { t: (o.t ?? 0) + (o.d ?? 1.6), type: 'pop' } });
    if (o.labels) { SK.label(o.labels[0], x, y + h + 34, { size: 26, wt: 600, col: C().textSoft, align: 'left' }); SK.label(o.labels[1], x + w, y + h + 34, { size: 26, wt: 600, col: C().textSoft, align: 'right' }); }
  };
  /** A donut of segments [{value, col, label}] growing in turn, centred on (x, y). o: thick (.32 of r),
   *  t, stagger (.35), d (.6), centre (text in the hole), legend (true: labels outside), gap (radians) */
  SK.donut = function (data, x, y, r, o = {}) {
    const rows = data.map((d) => (typeof d === 'number' ? { value: d } : d)), tot = rows.reduce((s, d) => s + d.value, 0) || 1, th = r * (o.thick ?? .32), t = SK.T;
    let a0 = -Math.PI / 2;
    const c = ctx();
    rows.forEach((d, i) => {
      const t0 = d.t ?? (o.t ?? 0) + i * (o.stagger ?? .35), u = E.out(clamp((t - t0) / (o.d ?? .6))), sweep = d.value / tot * TAU, gap = o.gap ?? .025;
      if (u > 0) {
        c.save(); c.strokeStyle = colOf(d, i, o); c.lineWidth = th; c.lineCap = 'butt';
        c.beginPath(); c.arc(x, y, r - th / 2, a0 + gap / 2, a0 + gap / 2 + Math.max(0, sweep - gap) * u); c.stroke(); c.restore();
        if (d.label && o.legend !== false && u >= 1) {
          const am = a0 + sweep / 2, lx = x + Math.cos(am) * (r + 46), ly = y + Math.sin(am) * (r + 36);
          SK.label(d.label, lx, ly, { size: o.size ?? 28, wt: 700, col: colOf(d, i, o), align: Math.cos(am) > .2 ? 'left' : Math.cos(am) < -.2 ? 'right' : 'center', alpha: clamp((t - t0 - (o.d ?? .6)) / .3), font: o.font });
        }
      }
      a0 += sweep;
    });
    if (o.centre !== undefined) SK.label(o.centre, x, y, { size: o.centreSize ?? r * .42, maxW: (r - th) * 1.7, wt: 800, col: o.centreCol ?? C().text, font: o.font, alpha: SK.win(t, o.t ?? 0, 1e9, .4, 0) });
  };
  /** An icon array: n of `of` units filled, in o.cols columns, top-left at x, y. o: size (44), gap,
   *  icon ('dot' | an SK.icon kind | fn(x, y, s, on)), col, off (the empty units' colour), t, stagger */
  SK.units = function (n, of, x, y, o = {}) {
    const cols = o.cols ?? 10, s = o.size ?? 44, g = o.gap ?? s * .3, t = SK.T, col = o.col ?? C().accent, off = o.off ?? alphaOf(C().textSoft, .25);
    for (let i = 0; i < of; i++) {
      const cx = x + (i % cols) * (s + g) + s / 2, cy = y + Math.floor(i / cols) * (s + g) + s / 2, on = i < n;
      const t0 = (o.t ?? 0) + (on ? i : n) * (o.stagger ?? .04), k = on ? E.back(clamp((t - t0) / .35)) : clamp((t - (o.t ?? 0)) / .3);
      if (k <= 0) continue;
      SK.at(cx, cy, 0, on ? k : 1, () => {
        if (typeof o.icon === 'function') o.icon(0, 0, s, on);
        else if (o.icon && o.icon !== 'dot') SK.icon(o.icon, 0, 0, s * .5, { col: on ? col : off, fill: true });
        else disc(0, 0, s * .45, { fill: on ? col : off, alpha: on ? 1 : k });
      });
    }
  };
  /** A progress bar, top-left at x, y. p: 0..1. o: h (26), col, track, r, label (left above), value
   *  (true: the percentage at the right above; a string: that), t + d (animate p from 0) */
  SK.meter = function (p, x, y, w, o = {}) {
    const h = o.h ?? 26, u = o.t !== undefined ? E.inOut(clamp((SK.T - o.t) / (o.d ?? 1.2))) : 1, q = clamp(p) * u;
    box(x, y, w, h, { r: o.r ?? h / 2, fill: o.track ?? alphaOf(isHex(C().textSoft) ? C().textSoft : '#888888', .2) });
    if (q > 0) box(x, y, Math.max(h, w * q), h, { r: o.r ?? h / 2, fill: o.col ?? C().accent, alpha: q * w < h ? q * w / h : 1 });
    if (o.label) SK.label(o.label, x, y - h * .9 - 8, { size: o.size ?? 28, wt: 600, col: o.labelCol ?? C().text, align: 'left', font: o.font });
    if (o.value) SK.label(o.value === true ? SK.fmt(q * 100, { fmt: 'pct' }) : o.value, x + w, y - h * .9 - 8, { size: o.size ?? 28, wt: 800, col: o.labelCol ?? C().text, align: 'right', font: o.font });
  };
  /** A circular progress arc with its head, centred on (x, y). o: w (r * .16), col, track, text (in
   *  the middle; true: the percentage), t + d (animate), size */
  SK.ring = function (p, x, y, r, o = {}) {
    const u = o.t !== undefined ? E.inOut(clamp((SK.T - o.t) / (o.d ?? 1.2))) : 1, q = clamp(p) * u, lw = o.w ?? r * .16, c = ctx();
    c.save(); c.lineCap = 'round'; c.lineWidth = lw;
    c.strokeStyle = o.track ?? alphaOf(isHex(C().textSoft) ? C().textSoft : '#888888', .2); c.beginPath(); c.arc(x, y, r, 0, TAU); c.stroke();
    if (q > 0) { c.strokeStyle = o.col ?? C().accent; c.beginPath(); c.arc(x, y, r, -Math.PI / 2, -Math.PI / 2 + TAU * q); c.stroke(); }
    c.restore();
    if (q > 0 && o.head !== false) disc(x + Math.cos(-Math.PI / 2 + TAU * q) * r, y + Math.sin(-Math.PI / 2 + TAU * q) * r, lw * .75, { fill: '#ffffff', stroke: o.col ?? C().accent, w: 3 });
    if (o.text !== undefined) SK.label(o.text === true ? SK.fmt(q * 100, { fmt: 'pct' }) : o.text, x, y, { size: o.size ?? r * .5, wt: 800, col: o.textCol ?? C().text, font: o.font });
  };
  /** A stepper / chapter tracker: items [{label, t}] (or strings with o.times) as dots on a line from
   *  x, y (left), o.w long; a step is current from its t, done when the next starts. o: size (30),
   *  numbered (true), col (accent), done ('check'), labels (true), dir ('h' | 'v') */
  SK.steps = function (items, x, y, o = {}) {
    const rows = items.map((it, i) => (typeof it === 'string' ? { label: it, t: (o.times || [])[i] ?? (o.t ?? 0) + i * 2 } : it)), n = rows.length, t = SK.T;
    const w = o.w ?? 1200, vert = o.dir === 'v', r = (o.size ?? 30) * .75, col = o.col ?? C().accent, dim = o.dim ?? alphaOf(isHex(C().textSoft) ? C().textSoft : '#888888', .45);
    const pos = (i) => (vert ? [x, y + (n > 1 ? i * w / (n - 1) : 0)] : [x + (n > 1 ? i * w / (n - 1) : 0), y]);
    let cur = -1; rows.forEach((s, i) => { if (t >= s.t) cur = i; });
    line([pos(0), pos(n - 1)], { col: dim, w: 5, crisp: true });
    if (cur > 0) { const a = pos(0), b = pos(cur), prog = clamp((t - rows[cur].t) / .5), bb = [lerp(pos(cur - 1)[0], b[0], prog), lerp(pos(cur - 1)[1], b[1], prog)]; line([a, bb], { col, w: 5, crisp: true }); }
    rows.forEach((s, i) => {
      const [px, py] = pos(i), state = i < cur ? 'done' : i === cur ? 'now' : 'next', k = i === cur ? E.back(clamp((t - s.t) / .4)) : 1;
      SK.at(px, py, 0, state === 'now' ? lerp(1, 1.25, k) : 1, () => {
        disc(0, 0, r, { fill: state === 'next' ? (hand() ? '#fffaf0' : '#ffffff') : col, stroke: state === 'next' ? dim : null, w: 4 });
        if (state === 'done' && o.done !== 'number') SK.icon('check', 0, 0, r * .55, { col: SK.inkOn(isHex(col) ? col : '#d9733f'), w: r * .22 });
        else if (o.numbered !== false) SK.label(String(i + 1), 0, 1, { size: r * 1.05, wt: 800, col: state === 'next' ? dim : SK.inkOn(isHex(col) ? col : '#d9733f'), font: o.font });
      });
      if (o.labels !== false && s.label) SK.label(s.label, px + (vert ? r + 20 : 0), py + (vert ? 0 : r + (o.size ?? 30) * .95), { size: o.size ?? 30, wt: state === 'now' ? 800 : 600, col: state === 'next' ? dim : C().text, align: vert ? 'left' : 'center', font: o.font, maxW: vert ? undefined : w / Math.max(1, n - 1) * .95 });
    });
    return cur;
  };
  /** An axis from x, y (left), o.w long, with milestones [{at, label, sub, t}] placed by value between
   *  o.min and o.max; each pops in on its t with a stem and a card above (alternating below with
   *  o.alt). o: ticks (values to mark), fmt, col, size */
  SK.timeline = function (events, x, y, o = {}) {
    const w = o.w ?? 1500, vals = events.map((e) => e.at), lo = o.min ?? Math.min(...vals), hi = o.max ?? Math.max(...vals), t = SK.T, col = o.col ?? C().accent, size = o.size ?? 30;
    const X = (v) => x + (v - lo) / ((hi - lo) || 1) * w, ax = o.t !== undefined ? E.inOut(clamp((t - o.t) / .8)) : 1;
    line([[x, y], [x + w * ax, y]], { col: C().text, w: 5, crisp: !hand() });
    (o.ticks || []).forEach((v) => { line([[X(v), y - 10], [X(v), y + 10]], { col: C().text, w: 3, crisp: true, alpha: ax }); SK.label(SK.fmt(v, { fmt: o.fmt ?? ((q) => String(q)) }), X(v), y + 36, { size: size * .8, wt: 600, col: C().textSoft, alpha: ax, font: o.font }); });
    events.forEach((e, i) => {
      const k = E.back(clamp((t - (e.t ?? (o.t ?? 0) + i * .5)) / .45)); if (k <= 0) return;
      const ex = X(e.at), up = o.alt && i % 2 ? 1 : -1, stem = o.stem ?? 90;
      disc(ex, y, 12 * k, { fill: e.col ?? col });
      line([[ex, y + up * 14], [ex, y + up * stem * k]], { col: e.col ?? col, w: 3, crisp: true });
      if (k > .5) {
        SK.label(e.label, ex, y + up * (stem + size * (up < 0 ? .9 : .9)), { size, wt: 800, col: C().text, alpha: clamp(k * 2 - 1), font: o.font });
        if (e.sub) SK.label(e.sub, ex, y + up * (stem + size * 2.05), { size: size * .7, wt: 500, col: C().textSoft, alpha: clamp(k * 2 - 1), font: o.font, maxW: o.subW ?? 300 });
      }
    });
  };
  /** Nodes [{id, x, y, label, t, icon, fill, w}] joined by arrows [[from, to, {t, bow, label}]]
   *  drawing on. o: size (30), fill, col, dots (n packets per link travelling along it, after it is
   *  drawn), dotCol, shape ('pill' | 'card' | 'circle') */
  SK.flow = function (nodes, edges, o = {}) {
    const by = Object.fromEntries(nodes.map((n) => [n.id, n])), t = SK.T, size = o.size ?? 30;
    const half = (n) => { const w = (n.w ?? SK.measure(n.label ?? '', { size, wt: 700, font: o.font }) + size * 1.6 + (n.icon ? size : 0)) / 2; return [w, size * .95]; };
    (edges || []).forEach(([a, b, e = {}], i) => {
      const A = by[a], B = by[b]; if (!A || !B) return;
      const t0 = e.t ?? Math.max(A.t ?? 0, B.t ?? 0) + .3, p = E.inOut(clamp((t - t0) / (e.d ?? .5))); if (p <= 0) return;
      const ang = Math.atan2(B.y - A.y, B.x - A.x), [aw, ah] = half(A), [bw, bh] = half(B);
      const off = (w2, h2) => Math.min(Math.abs(w2 / (Math.cos(ang) || 1e-6)), Math.abs(h2 / (Math.sin(ang) || 1e-6))) + 10;
      const oa = off(aw, ah), ob = off(bw, bh), x1 = A.x + Math.cos(ang) * oa, y1 = A.y + Math.sin(ang) * oa, x2 = B.x - Math.cos(ang) * ob, y2 = B.y - Math.sin(ang) * ob;
      const pts = S.line(x1, y1, x2, y2, e.bow ?? 0), col = e.col ?? o.lineCol ?? C().textSoft;
      line(pts, { col, w: 4, p, dash: e.dash });
      if (p >= 1) head(pts, 16, { col, w: 4, solid: true });
      if (e.label && p >= 1) { const [mx, my] = S.at(pts, .5); SK.pill(e.label, mx, my - 26, { size: size * .7, fill: hand() ? '#fffaf0' : '#ffffff', col: C().text, stroke: alphaOf(C().textSoft, .4) }); }
      if (o.dots && p >= 1) for (let k = 0; k < o.dots; k++) { const u = ((t - t0) * (o.speed ?? .45) + k / o.dots) % 1; const [dx, dy] = S.at(pts, u); disc(dx, dy, 7, { fill: o.dotCol ?? C().accent, alpha: Math.sin(Math.PI * u) }); }
    });
    nodes.forEach((n, i) => {
      const t0 = n.t ?? (o.t ?? 0) + i * .3; if (t < t0) return;
      const [hw, hh] = half(n), shape = n.shape ?? o.shape ?? 'pill', fill = n.fill ?? o.fill ?? (hand() ? '#fffaf0' : '#ffffff'), col = n.col ?? o.col ?? (isHex(fill) ? SK.inkOn(fill) : C().text);
      at({ in: { t: t0, type: 'pop' } }, n.x, n.y, hw * 2, hh * 2, () => {
        if (shape === 'circle') disc(0, 0, Math.max(hw, hh), { fill, stroke: n.stroke ?? o.stroke ?? alphaOf(C().textSoft, .5), w: 3 });
        else box(-hw, -hh, hw * 2, hh * 2, { r: shape === 'card' ? 14 : hh, fill, stroke: n.stroke ?? o.stroke ?? (hand() ? C().ink : alphaOf(C().textSoft, .35)), w: 3, shadow: !hand() && shape === 'card' });
        if (n.icon) SK.icon(n.icon, -hw + size * .95, 0, size * .42, { col: n.iconCol ?? C().accent });
        if (n.label) SK.label(n.label, n.icon ? size * .45 : 0, 1, { size, wt: 700, col, font: o.font });
      });
    });
  };
  /** A stat card centred on (x, y): kicker, a value (counts up from 0 when numeric), a caption, an
   *  icon. o: w (420), value, kicker, caption, icon, t, d (count time), fmt, dec, pre, post, fill, col, accent */
  SK.stat = function (x, y, o = {}) {
    const w = o.w ?? 420, t0 = o.t ?? 0, h = o.h ?? (o.caption ? 280 : 220), fill = o.fill ?? (hand() ? '#fffaf0' : '#ffffff'), col = o.col ?? (isHex(fill) ? SK.inkOn(fill) : C().text);
    at({ in: { t: t0, type: o.type ?? 'rise' }, out: o.out }, x, y, w, h, () => {
      box(-w / 2, -h / 2, w, h, { r: o.r ?? 22, fill, shadow: true, stroke: hand() ? C().ink : null });
      let yy = -h / 2 + 50;
      if (o.icon) SK.icon(o.icon, -w / 2 + 52, yy + 2, 20, { col: o.accent ?? C().accent, bg: alphaOf(isHex(o.accent ?? C().accent) ? o.accent ?? C().accent : '#d9733f', .14) });
      if (o.kicker) SK.label(String(o.kicker).toUpperCase(), -w / 2 + (o.icon ? 92 : 36), yy, { size: 24, wt: 700, ls: 2.5, col: o.kickerCol ?? alphaOf(col, .65) === col ? '#6b7280' : o.kickerCol ?? '#6b7280', align: 'left', font: o.font, maxW: w - 120 });
      yy += 92;
      if (typeof o.value === 'number') SK.counter(-w / 2 + 36, yy, { from: o.from ?? 0, to: o.value, t0: t0 + .2, t1: t0 + .2 + (o.d ?? 1.4), fmt: o.fmt, dec: o.dec, pre: o.pre, post: o.post, size: o.size ?? 96, col: o.accent ?? col, align: 'left', font: o.font, show: true });
      else if (o.value !== undefined) SK.label(o.value, -w / 2 + 36, yy, { size: o.size ?? 96, wt: 800, col: o.accent ?? col, align: 'left', font: o.font, maxW: w - 72 });
      if (o.caption) SK.para(o.caption, -w / 2 + 36, yy + 52, { size: 26, w: w - 72, col: alphaOf(col, .8) === col ? '#5d6677' : '#5d6677', wt: 500, font: o.font });
    });
  };

  /* ================================================================ screens */
  /** App / browser chrome, top-left at x, y: o.title, url (an address bar), dark, r, fill, bar, shadow,
   *  content(x0, y0, w, h) drawn clipped inside (top-left of the content area), in/out */
  SK.window = function (x, y, w, h, o = {}) {
    const dark = !!o.dark, barH = o.url ? 76 : 52, r = o.r ?? 18, fill = o.fill ?? (dark ? '#161a22' : '#ffffff');
    at(o, x + w / 2, y + h / 2, w, h, () => {
      const X = -w / 2, Y = -h / 2;
      box(X, Y, w, h, { r, fill, shadow: o.shadow ?? (hand() ? false : { blur: 40, y: 18, col: 'rgba(16,23,32,.22)' }), stroke: hand() ? C().ink : o.stroke });
      const c = ctx(); c.save(); SK.rrPath(X, Y, w, h, r); c.clip();
      c.fillStyle = o.bar ?? (dark ? '#232834' : '#f1f3f6'); c.fillRect(X, Y, w, barH);
      ['#ff5f57', '#febc2e', '#28c840'].forEach((col2, i) => disc(X + 28 + i * 26, Y + 26, 8, { fill: col2 }));
      if (o.title) SK.label(o.title, X + w / 2, Y + 26, { size: 22, wt: 600, col: dark ? '#c9ced8' : '#4b5563', font: o.font, maxW: w - 200 });
      if (o.url) { box(X + 110, Y + 38, w - 140, 30, { r: 15, fill: dark ? '#141821' : '#ffffff', stroke: dark ? null : '#e2e5ea', w: 1.5 }); SK.icon('lock', X + 130, Y + 53, 7, { col: '#8b93a1', w: 2 }); SK.label(o.url, X + 146, Y + 53, { size: 18, wt: 500, col: dark ? '#aab1bd' : '#4b5563', align: 'left', font: o.font, maxW: w - 200 }); }
      if (o.content) { c.save(); c.beginPath(); c.rect(X, Y + barH, w, h - barH); c.clip(); o.content(X, Y + barH, w, h - barH); c.restore(); }
      c.restore();
    });
  };
  /** A phone centred on (x, y), 360 x 740 at o.s = 1: o.screen(x0, y0, w, h) drawn clipped on the
   *  screen (top-left of the screen), dark (a dark screen), body (its colour), status (the time shown,
   *  '9:41'; false: none), notch (true), rot, in/out */
  SK.phone = function (x, y, o = {}) {
    const W = 360, H = 740, s = o.s ?? 1, body = o.body ?? '#16181d', scr = o.dark ? '#0f1115' : (o.screenCol ?? '#ffffff');
    at({ ...o, s: s * (o.s2 ?? 1) }, x, y, W, H, () => {
      box(-W / 2, -H / 2, W, H, { r: 58, fill: body, shadow: o.shadow ?? (hand() ? false : { blur: 50, y: 24, col: 'rgba(16,23,32,.28)' }), stroke: hand() ? C().ink : null, w: 5 });
      const sx = -W / 2 + 14, sy = -H / 2 + 14, sw = W - 28, sh = H - 28, c = ctx();
      c.save(); SK.rrPath(sx, sy, sw, sh, 46); c.clip();
      c.fillStyle = scr; c.fillRect(sx, sy, sw, sh);
      if (o.screen) { c.save(); o.screen(sx, sy, sw, sh); c.restore(); }
      if (o.status !== false) { const tc = o.dark ? '#ffffff' : '#111111'; SK.label(o.status ?? '9:41', sx + 52, sy + 26, { size: 19, wt: 700, col: tc, font: o.font }); box(sx + sw - 64, sy + 19, 32, 14, { r: 4, stroke: tc, w: 1.6 }); box(sx + sw - 61, sy + 22, 22, 8, { r: 2, fill: tc }); }
      c.restore();
      if (o.notch !== false) box(-55, -H / 2 + 24, 110, 32, { r: 16, fill: '#000000' });
    });
  };
  /** A thread [{who: 'me' | 'them', text, t}] in a column o.w wide, top-left at x, y: bubbles wrap
   *  their text, 'them' shows a typing indicator for o.typing (.9) s first, and the thread scrolls up
   *  inside o.h. o: size (30), me / them (bubble colours), names, font -> the visible height */
  SK.chat = function (msgs, x, y, o = {}) {
    const w = o.w ?? 640, size = o.size ?? 30, t = SK.T, maxW = w * .78, pad = size * .6, gap = size * .45;
    const items = [];
    for (const m of msgs) {
      const shown = t >= m.t, typing = m.who !== 'me' && t >= m.t - (o.typing ?? .9) && t < m.t;
      if (!shown && !typing) continue;
      const lines = typing ? ['…'] : wrap(m.text, maxW - 2 * pad, { size, wt: 500, font: o.font });
      const bw = typing ? size * 3 : Math.min(maxW, Math.max(...lines.map((l) => SK.measure(l, { size, wt: 500, font: o.font }))) + 2 * pad), bh = lines.length * size * 1.25 + pad * 1.2;
      items.push({ m, lines, bw, bh, typing, k: E.back(clamp((t - (typing ? m.t - (o.typing ?? .9) : m.t)) / .3)) });
    }
    const total = items.reduce((s, it) => s + it.bh + gap, 0), H = o.h ?? 1e9, scroll = Math.max(0, total - H);
    const c = ctx(); c.save(); if (o.h) { c.beginPath(); c.rect(x - 20, y - 10, w + 40, H + 20); c.clip(); }
    let yy = y - scroll;
    for (const it of items) {
      const me = it.m.who === 'me', bx = me ? x + w - it.bw : x, fill = me ? o.me ?? C().accent : o.them ?? (hand() ? '#fffaf0' : '#eef0f4'), col = isHex(fill) ? SK.inkOn(fill, '#1d2330', '#ffffff') : C().text;
      SK.at(bx + (me ? it.bw : 0), yy + it.bh / 2, 0, it.k, () => {
        const ox = me ? -it.bw : 0;
        box(ox, -it.bh / 2, it.bw, it.bh, { r: size * .75, fill, stroke: hand() ? C().ink : null, w: 3 });
        if (it.typing) [0, 1, 2].forEach((k) => disc(ox + it.bw / 2 + (k - 1) * size * .55, 0, size * .13, { fill: col, alpha: .4 + .6 * SK.bump((t * 2.4) % 1, k * .25 + .15, .18) }));
        else it.lines.forEach((ln, i) => SK.label(ln, ox + pad, -it.bh / 2 + pad * .6 + size * (.62 + i * 1.25), { size, wt: 500, col, align: 'left', font: o.font }));
      });
      yy += it.bh + gap;
    }
    c.restore();
    return Math.min(total, H);
  };
  /** the eased position of a pointer through [[t, x, y], ...] -> pos(t) = [x, y] */
  SK.cursorPath = (keys) => (t) => SK.kf(t, keys.map(([tk, kx, ky]) => [tk, [kx, ky]]), E.inOut);
  /** A pointer whose tip is at (x, y). o: s (1), hand (a pointing hand), click (a time or [times]: it
   *  presses and a ripple spreads), col, ripple (true) */
  SK.cursor = function (x, y, o = {}) {
    const t = SK.T, clicks = [].concat(o.click ?? []), press = clicks.reduce((m, ck) => Math.max(m, SK.bump(t, ck, .09)), 0), s = (o.s ?? 1) * (1 - .14 * press);
    if (o.ripple !== false) clicks.forEach((ck) => SK.ripple(x, y, ck, { col: o.rippleCol ?? C().accent }));
    SK.at(x, y, 0, s, () => {
      const c = ctx(); c.save();
      c.shadowColor = 'rgba(0,0,0,.28)'; c.shadowBlur = 8; c.shadowOffsetY = 3;
      const P = o.hand
        ? [[0, 0], [8, -2], [10, 20], [26, 16], [42, 22], [46, 46], [38, 66], [14, 70], [-4, 50], [-14, 34], [-8, 28], [2, 36]]
        : [[0, 0], [0, 46], [11, 35], [19, 54], [27, 50], [19, 32], [34, 32]];
      c.beginPath(); c.moveTo(P[0][0], P[0][1]); for (const p2 of P.slice(1)) c.lineTo(p2[0], p2[1]); c.closePath();
      c.fillStyle = o.col ?? '#ffffff'; c.fill(); c.shadowColor = 'transparent'; c.lineWidth = 3; c.lineJoin = 'round'; c.strokeStyle = o.edge ?? '#111111'; c.stroke();
      c.restore();
    });
  };
  /** rings spreading from (x, y) after t0: a tap, a click. o: col, r1 (60), d (.6), n (2) */
  SK.ripple = function (x, y, t0, o = {}) {
    const t = SK.T, n = o.n ?? 2, d = o.d ?? .6;
    for (let k = 0; k < n; k++) {
      const u = (t - t0 - k * .12) / d; if (u <= 0 || u >= 1) continue;
      disc(x, y, (o.r0 ?? 6) + (o.r1 ?? 60) * E.out(u), { stroke: o.col ?? C().accent, w: (o.w ?? 5) * (1 - u), alpha: 1 - u });
    }
  };
  /** A button centred on (x, y): o.press (a time) dips and darkens it; size (32), fill, col, icon, r,
   *  w (fixed width), in/out -> {w, h} */
  SK.button = function (text, x, y, o = {}) {
    const t = SK.T, size = o.size ?? 32, f = { size, wt: 700, font: o.font }, iw = o.icon ? size * 1.2 : 0;
    const w = o.w ?? SK.measure(text, f) + iw + size * 1.8, h = size * 2.1, press = o.press !== undefined ? SK.bump(t, o.press, .1) : 0;
    const fill0 = o.fill ?? C().accent, fill = isHex(fill0) && press > 0 ? SK.mix(fill0, '#000000', .18 * press) : fill0, col = o.col ?? (isHex(fill0) ? SK.inkOn(fill0) : '#ffffff');
    at({ ...o, s: (o.s ?? 1) * (1 - .06 * press) }, x, y, w, h, () => {
      box(-w / 2, -h / 2, w, h, { r: o.r ?? h / 2, fill, shadow: o.shadow ?? (hand() ? false : { blur: 18 * (1 - press), y: 8 * (1 - press), col: 'rgba(16,23,32,.2)' }), stroke: hand() ? C().ink : o.stroke, w: 3 });
      if (o.icon) SK.icon(o.icon, -w / 2 + size * .9 + iw * .2, 0, size * .4, { col, w: size * .1 });
      SK.label(text, iw / 2, 1, { ...f, col });
    });
    return { w, h };
  };
  /** A text field, top-left at x, y, w wide, typing `text` from o.t at o.cps (22) with a caret.
   *  o: label (above), placeholder, size (30), focus (true: the accent ring while typing), font */
  SK.field = function (text, x, y, w, o = {}) {
    const t = SK.T, size = o.size ?? 30, h = size * 2, t0 = o.t ?? 0, n = String(text).length, p = SK.typed(t, t0, n, o.cps ?? 22), typing = t >= t0 - .3 && p < 1;
    if (o.label) SK.label(o.label, x, y - size * .75, { size: size * .72, wt: 600, col: C().textSoft, align: 'left', font: o.font });
    box(x, y, w, h, { r: o.r ?? 12, fill: o.fill ?? (hand() ? '#fffaf0' : '#ffffff'), stroke: typing && o.focus !== false ? C().accent : o.stroke ?? (hand() ? C().ink : '#d4d8df'), w: typing ? 3.5 : 2 });
    const shown = String(text).slice(0, Math.round(p * n));
    if (!shown && o.placeholder) SK.label(o.placeholder, x + size * .6, y + h / 2, { size, wt: 500, col: '#9aa1ad', align: 'left', font: o.font });
    const tw2 = SK.label(shown, x + size * .6, y + h / 2, { size, wt: 500, col: o.col ?? '#1d2330', align: 'left', font: o.font, maxW: w - size * 1.2 }).w;
    if ((typing || (t >= t0 + n / (o.cps ?? 22) && t < t0 + n / (o.cps ?? 22) + (o.hold ?? 1.2))) && Math.floor(t * 2.2) % 2 === 0) box(x + size * .6 + Math.min(tw2, w - size * 1.2) + 3, y + h * .22, 3, h * .56, { r: 1, fill: C().accent });
  };
  /** A notification sliding in at o.t (and out at o.until), centred on (x, y). o: icon, w (620), fill,
   *  app (a small grey line over the title), from ('t' | 'r') */
  SK.toast = function (title, body, x, y, o = {}) {
    const w = o.w ?? 620, h = body ? 150 : 104, fill = o.fill ?? (hand() ? '#fffaf0' : 'rgba(255,255,255,.96)');
    at({ in: { t: o.t ?? 0, type: 'slide', from: o.from ?? 't', dist: 260, d: .55 }, out: o.until !== undefined ? { t: o.until, type: 'slide', from: o.from ?? 't', dist: 260, d: .45 } : undefined }, x, y, w, h, () => {
      box(-w / 2, -h / 2, w, h, { r: 26, fill, shadow: { blur: 34, y: 14, col: 'rgba(16,23,32,.22)' }, stroke: hand() ? C().ink : null });
      SK.icon(o.icon ?? 'bell', -w / 2 + 62, -h / 2 + 62, 22, { col: '#ffffff', bg: o.accent ?? (isHex(C().accent) ? C().accent : '#2f6fdb'), fill: false });
      if (o.app) SK.label(o.app, -w / 2 + 112, -h / 2 + 34, { size: 20, wt: 600, col: '#8b93a1', align: 'left', font: o.font });
      SK.label(title, -w / 2 + 112, -h / 2 + (o.app ? 66 : 54), { size: 30, wt: 700, col: '#1d2330', align: 'left', font: o.font, maxW: w - 140 });
      if (body) SK.label(body, -w / 2 + 112, -h / 2 + (o.app ? 106 : 96), { size: 25, wt: 500, col: '#4b5563', align: 'left', font: o.font, maxW: w - 140 });
    });
  };
  /** A code or terminal panel, top-left at x, y: lines typed one after another from o.t at o.cps (32);
   *  a line starting with '$ ' or '> ' is a command, '# ' / '// ' a comment. o: w (900), size (26),
   *  title, dark (true), lh, out (lines shown whole, no typing: [indexes]) -> its height */
  SK.code = function (lines, x, y, o = {}) {
    const t = SK.T, size = o.size ?? 26, lh = size * (o.lh ?? 1.55), w = o.w ?? 900, h = o.h ?? lines.length * lh + 92, dark = o.dark !== false, cps = o.cps ?? 32;
    SK.window(x, y, w, h, { dark, title: o.title, r: 16, shadow: o.shadow, content: (x0, y0) => {
      let tt = o.t ?? 0;
      lines.forEach((ln, i) => {
        const isCmd = /^(\$|>) /.test(ln), isCom = /^(#|\/\/) /.test(ln), n = ln.length, whole = (o.whole || []).includes(i) || (!isCmd && o.typeOutput === false);
        const p = whole ? (t >= tt ? 1 : 0) : SK.typed(t, tt, n, cps);
        if (p > 0) {
          const col = isCom ? '#7f8a9a' : isCmd ? (o.cmdCol ?? '#7ee2a8') : (dark ? '#e6e9ef' : '#1d2330');
          const shown = ln.slice(0, Math.round(p * n)), ly = y0 + 34 + i * lh;
          const wS = SK.label(shown, x0 + 30, ly, { size, wt: isCmd ? 700 : 400, col, align: 'left', font: monoFam(o) }).w;
          if (p < 1 && Math.floor(t * 2.4) % 2 === 0) box(x0 + 32 + wS, ly - size * .5, size * .55, size, { r: 0, fill: col });
        }
        tt += whole ? (o.pause ?? .25) : n / cps + (o.pause ?? .25);
      });
    } });
    return h;
  };
  // the line icons: each draws in a 2r box around 0, 0 with lines of width w
  const ICONS = {
    check: (r) => [[[-r * .7, 0], [-r * .2, r * .5], [r * .75, -r * .55]]],
    cross: (r) => [[[-r * .6, -r * .6], [r * .6, r * .6]], [[r * .6, -r * .6], [-r * .6, r * .6]]],
    plus: (r) => [[[-r * .7, 0], [r * .7, 0]], [[0, -r * .7], [0, r * .7]]],
    minus: (r) => [[[-r * .7, 0], [r * .7, 0]]],
    arrow: (r) => [[[-r * .75, 0], [r * .75, 0]], [[r * .25, -r * .5], [r * .75, 0], [r * .25, r * .5]]],
    play: (r, f) => (f ? { fill: [[-r * .45, -r * .65], [r * .7, 0], [-r * .45, r * .65]] } : [[[-r * .45, -r * .65], [r * .7, 0], [-r * .45, r * .65], [-r * .45, -r * .65]]]),
    pause: (r) => [[[-r * .35, -r * .6], [-r * .35, r * .6]], [[r * .35, -r * .6], [r * .35, r * .6]]],
    mail: (r) => [S.rrect(-r * .85, -r * .6, r * 1.7, r * 1.2, r * .12), [[-r * .8, -r * .5], [0, r * .1], [r * .8, -r * .5]]],
    doc: (r) => [[[-r * .55, -r * .85], [r * .2, -r * .85], [r * .6, -r * .45], [r * .6, r * .85], [-r * .55, r * .85], [-r * .55, -r * .85]], [[r * .2, -r * .85], [r * .2, -r * .45], [r * .6, -r * .45]], [[-r * .3, 0], [r * .35, 0]], [[-r * .3, r * .35], [r * .35, r * .35]]],
    folder: (r) => [[[-r * .85, -r * .55], [-r * .25, -r * .55], [-r * .1, -r * .35], [r * .85, -r * .35], [r * .85, r * .65], [-r * .85, r * .65], [-r * .85, -r * .55]]],
    image: (r) => [S.rrect(-r * .85, -r * .65, r * 1.7, r * 1.3, r * .12), [[-r * .7, r * .5], [-r * .2, -r * .05], [r * .15, r * .3], [r * .4, r * .05], [r * .75, r * .45]], S.ellC(r * .35, -r * .3, r * .14, r * .14).concat([[r * .49, -r * .3]])],
    chat: (r) => [[[-r * .8, -r * .55], [r * .8, -r * .55], [r * .8, r * .35], [-r * .1, r * .35], [-r * .5, r * .75], [-r * .45, r * .35], [-r * .8, r * .35], [-r * .8, -r * .55]]],
    bell: (r) => [[[-r * .6, r * .4], [-r * .5, -r * .15], [-r * .3, -r * .55], [0, -r * .7], [r * .3, -r * .55], [r * .5, -r * .15], [r * .6, r * .4], [-r * .6, r * .4]], [[-r * .2, r * .6], [r * .2, r * .6]]],
    user: (r) => [S.ellC(0, -r * .35, r * .32, r * .32).concat([[r * .32, -r * .35]]), [[-r * .7, r * .8], [-r * .55, r * .3], [0, r * .12], [r * .55, r * .3], [r * .7, r * .8]]],
    users: (r) => [S.ellC(-r * .3, -r * .3, r * .26, r * .26).concat([[-r * .04, -r * .3]]), [[-r * .85, r * .75], [-r * .75, r * .25], [-r * .3, r * .08], [r * .15, r * .25], [r * .25, r * .75]], S.arc(r * .4, -r * .38, r * .24, -2.6, 1.6), [[r * .45, r * .1], [r * .8, r * .3], [r * .9, r * .75]]],
    calendar: (r) => [S.rrect(-r * .8, -r * .6, r * 1.6, r * 1.4, r * .12), [[-r * .8, -r * .2], [r * .8, -r * .2]], [[-r * .4, -r * .8], [-r * .4, -r * .45]], [[r * .4, -r * .8], [r * .4, -r * .45]]],
    clock: (r) => [S.ellC(0, 0, r * .8, r * .8).concat([[r * .8, 0]]), [[0, -r * .45], [0, 0], [r * .35, r * .2]]],
    search: (r) => [S.ellC(-r * .15, -r * .15, r * .5, r * .5).concat([[r * .35, -r * .15]]), [[r * .22, r * .22], [r * .75, r * .75]]],
    lock: (r) => [S.rrect(-r * .65, -r * .1, r * 1.3, r * .95, r * .12), S.arc(0, -r * .1, r * .42, Math.PI, TAU)],
    cart: (r) => [[[-r * .9, -r * .65], [-r * .6, -r * .65], [-r * .35, r * .35], [r * .6, r * .35], [r * .8, -r * .35], [-r * .5, -r * .35]], S.ellC(-r * .25, r * .65, r * .1, r * .1).concat([[-r * .15, r * .65]]), S.ellC(r * .5, r * .65, r * .1, r * .1).concat([[r * .6, r * .65]])],
    card: (r) => [S.rrect(-r * .9, -r * .6, r * 1.8, r * 1.2, r * .14), [[-r * .9, -r * .25], [r * .9, -r * .25]], [[-r * .6, r * .3], [-r * .15, r * .3]]],
    chart: (r) => [[[-r * .8, -r * .8], [-r * .8, r * .75], [r * .85, r * .75]], [[-r * .5, r * .3], [-r * .15, -r * .1], [r * .15, r * .15], [r * .65, -r * .5]]],
    gear: (r) => { const out = [], n = 8, P = []; for (let i = 0; i <= n * 4; i++) { const a = i / (n * 4) * TAU, k = (i % 4 < 2) ? .82 : .62; P.push([Math.cos(a) * r * k, Math.sin(a) * r * k]); } out.push(P, S.ellC(0, 0, r * .25, r * .25).concat([[r * .25, 0]])); return out; },
    globe: (r) => [S.ellC(0, 0, r * .8, r * .8).concat([[r * .8, 0]]), S.ellC(0, 0, r * .35, r * .8).concat([[r * .35, 0]]), [[-r * .8, 0], [r * .8, 0]]],
    phone: (r) => [S.rrect(-r * .45, -r * .85, r * .9, r * 1.7, r * .16), [[-r * .12, r * .6], [r * .12, r * .6]]],
    mic: (r) => [S.rrect(-r * .25, -r * .85, r * .5, r * 1.05, r * .25), S.arc(0, -r * .1, r * .5, 0, Math.PI), [[0, r * .4], [0, r * .8]]],
    heart: (r, f) => { const P = S.path([['M', 0, r * .7], ['C', -r * .2, r * .5, -r * .95, r * .05, -r * .85, -r * .35], ['C', -r * .75, -r * .85, -r * .15, -r * .8, 0, -r * .35], ['C', r * .15, -r * .8, r * .75, -r * .85, r * .85, -r * .35], ['C', r * .95, r * .05, r * .2, r * .5, 0, r * .7]]); return f ? { fill: P } : [P]; },
    star: (r, f) => { const P = []; for (let i = 0; i <= 10; i++) { const a = -Math.PI / 2 + i / 10 * TAU, k = i % 2 ? .42 : .9; P.push([Math.cos(a) * r * k, Math.sin(a) * r * k]); } return f ? { fill: P } : [P]; },
    home: (r) => [[[-r * .85, -r * .05], [0, -r * .8], [r * .85, -r * .05]], [[-r * .6, -r * .25], [-r * .6, r * .75], [r * .6, r * .75], [r * .6, -r * .25]], [[-r * .15, r * .75], [-r * .15, r * .3], [r * .15, r * .3], [r * .15, r * .75]]],
    bolt: (r, f) => { const P = [[r * .15, -r * .9], [-r * .55, r * .1], [-r * .05, r * .1], [-r * .2, r * .9], [r * .55, -r * .15], [r * .05, -r * .15], [r * .15, -r * .9]]; return f ? { fill: P } : [P]; },
    cloud: (r) => [S.path([['M', -r * .55, r * .45], ['C', -r * 1.05, r * .45, -r * .95, -r * .2, -r * .5, -r * .15], ['C', -r * .45, -r * .7, r * .3, -r * .75, r * .35, -r * .25], ['C', r * .95, -r * .3, r * 1.0, r * .45, r * .5, r * .45], ['L', -r * .55, r * .45]])],
    link: (r) => [S.rrect(-r * .9, -r * .28, r * 1.05, r * .56, r * .28), S.rrect(-r * .15, -r * .28, r * 1.05, r * .56, r * .28)],
    download: (r) => [[[0, -r * .8], [0, r * .3]], [[-r * .45, -r * .1], [0, r * .35], [r * .45, -r * .1]], [[-r * .75, r * .75], [r * .75, r * .75]]],
    upload: (r) => [[[0, r * .35], [0, -r * .75]], [[-r * .45, -r * .3], [0, -r * .78], [r * .45, -r * .3]], [[-r * .75, r * .75], [r * .75, r * .75]]],
    money: (r) => [S.rrect(-r * .9, -r * .55, r * 1.8, r * 1.1, r * .12), S.ellC(0, 0, r * .3, r * .3).concat([[r * .3, 0]])],
    warning: (r) => [[[0, -r * .85], [r * .9, r * .75], [-r * .9, r * .75], [0, -r * .85]], [[0, -r * .3], [0, r * .2]], [[0, r * .48], [0, r * .5]]],
    info: (r) => [S.ellC(0, 0, r * .85, r * .85).concat([[r * .85, 0]]), [[0, -r * .1], [0, r * .45]], [[0, -r * .42], [0, -r * .4]]],
    pin: (r) => [S.path([['M', 0, r * .9], ['C', -r * .2, r * .45, -r * .65, r * .1, -r * .65, -r * .25], ['C', -r * .65, -r * .65, -r * .35, -r * .9, 0, -r * .9], ['C', r * .35, -r * .9, r * .65, -r * .65, r * .65, -r * .25], ['C', r * .65, r * .1, r * .2, r * .45, 0, r * .9]]), S.ellC(0, -r * .27, r * .2, r * .2).concat([[r * .2, -r * .27]])],
    flag: (r) => [[[-r * .6, r * .9], [-r * .6, -r * .85]], [[-r * .6, -r * .8], [r * .7, -r * .8], [r * .35, -r * .45], [r * .7, -r * .1], [-r * .6, -r * .1]]],
    eye: (r) => [S.path([['M', -r * .9, 0], ['Q', 0, -r * .8, r * .9, 0], ['Q', 0, r * .8, -r * .9, 0]]), S.ellC(0, 0, r * .25, r * .25).concat([[r * .25, 0]])],
    send: (r) => [[[-r * .8, -r * .7], [r * .85, 0], [-r * .8, r * .7], [-r * .5, 0], [-r * .8, -r * .7]], [[-r * .5, 0], [r * .2, 0]]],
  };
  SK.ICONS = Object.keys(ICONS);
  /** A line icon centred on (x, y), r its half-size. o: col, w (line width, r * .16), fill (solid where
   *  the icon has a solid form), bg (a disc behind it, this colour), in/out */
  SK.icon = function (kind, x, y, r, o = {}) {
    const make = ICONS[kind];
    if (!make) { warn(`icon '${kind}' is not one of: ${SK.ICONS.join(' ')}`); return; }
    const draw = () => {
      if (o.bg) disc(0, 0, r * 1.45, { fill: o.bg });
      const col = o.col ?? C().text, got = make(r, o.fill);
      if (!Array.isArray(got)) { fillPoly(got.fill, col); return; }
      for (const pts of got) line(pts, { col, w: o.w ?? Math.max(2, r * .16), crisp: !hand(), seed: 40 });
    };
    if (o.in || o.out) at(o, x, y, 2 * r, 2 * r, draw); else SK.at(x, y, o.rot ?? 0, o.s ?? 1, draw);
  };

  /* ================================================================ brand */
  /** A picture from the manifest (an attached logo: SK.IMG[name]) fitted inside o.w x o.h (aspect
   *  kept) and centred on (x, y). o: w (360), h (160), plate (a colour: a rounded plate behind it;
   *  'circle': a round one), pad (.18 of the size), shadow, r, in/out. Missing picture: warns, draws
   *  nothing. -> {w, h} as drawn */
  SK.logo = function (name, x, y, o = {}) {
    const im = SK.IMG[name];
    if (!im) { warn(`logo '${name}' is not among the film's pictures`); return { w: 0, h: 0 }; }
    const W = o.w ?? 360, H = o.h ?? 160, k = Math.min(W / im.width, H / im.height), w = im.width * k, h = im.height * k;
    const pad = (o.pad ?? .18) * Math.max(w, h);
    at(o, x, y, w + 2 * pad, h + 2 * pad, () => {
      if (o.plate === 'circle') disc(0, 0, Math.hypot(w, h) / 2 + pad * .6, { fill: o.plateCol ?? '#ffffff' });
      else if (o.plate) box(-w / 2 - pad, -h / 2 - pad, w + 2 * pad, h + 2 * pad, { r: o.r ?? Math.min(28, pad * 1.4), fill: o.plate === true ? '#ffffff' : o.plate, shadow: o.shadow ?? true });
      SK.image(name, 0, 0, w, h);
    });
    return { w, h };
  };
  /** The closing card in screen space: o.logo (a picture name), title, tagline, url (a pill), cta (a
   *  button), bg (a colour over the whole frame; null: none), col, accent, t (when it starts: each piece
   *  enters in turn), layout ('centre' | 'left') */
  SK.endCard = function (o = {}) {
    const t = SK.T, t0 = o.t ?? 0; if (t < t0) return;
    SK.screen(() => {
      if (o.bg !== null) { const c = ctx(); c.save(); c.globalAlpha *= E.out(clamp((t - t0) / .45)); c.fillStyle = o.bg ?? C().paper; c.fillRect(-SK.W / 2 - 4, -SK.H / 2 - 4, SK.W + 8, SK.H + 8); c.restore(); }
      const left = o.layout === 'left', x = left ? -SK.W / 2 + 160 : 0, align = left ? 'left' : 'center', col = o.col ?? (o.bg && isHex(o.bg) ? SK.inkOn(o.bg, '#14171f', '#ffffff') : C().text), acc = o.accent ?? C().accent;
      let y = o.title || o.tagline ? -150 : -40;
      if (o.logo) { const lw = o.logoW ?? 420, lh = o.logoH ?? 170; SK.logo(o.logo, left ? x + lw / 2 : x, y - (o.title ? 60 : 0), { w: lw, h: lh, plate: o.plate, in: { t: t0 + .15, type: 'pop' } }); y += (o.title ? 110 : 150); }
      if (o.title) { SK.label(o.title, x, y, { size: o.size ?? 84, wt: 800, col, align, font: o.font, maxW: SK.W * .8, in: { t: t0 + .35, type: 'rise' } }); y += 84; }
      if (o.tagline) { SK.label(o.tagline, x, y, { size: (o.size ?? 84) * .44, wt: 500, col: o.taglineCol ?? col, align, font: o.font, maxW: SK.W * .75, alpha: .85, in: { t: t0 + .55, type: 'rise' } }); y += 80; }
      if (o.url || o.cta) {
        const items = [];
        if (o.cta) items.push(['cta', SK.measure(o.cta, { size: 34, wt: 700, font: o.font }) + 34 * 1.8]);
        if (o.url) items.push(['url', SK.measure(o.url, { size: 32, wt: 700, font: o.font }) + 32 * 1.4]);
        const gapX = 30, tot = items.reduce((s, it) => s + it[1], 0) + gapX * (items.length - 1);
        let xx = left ? x : -tot / 2;
        items.forEach(([kind, w], i) => {
          if (kind === 'cta') SK.button(o.cta, xx + w / 2, y + 12, { size: 34, fill: acc, font: o.font, in: { t: t0 + .8 + i * .15, type: 'pop' }, press: o.press });
          else SK.pill(o.url, xx + w / 2, y + 12, { size: 32, fill: o.urlFill ?? (isHex(o.bg ?? '') ? SK.mix(o.bg, SK.inkOn(o.bg, '#000000', '#ffffff'), .12) : 'rgba(127,127,127,.15)'), col, font: o.font, in: { t: t0 + .8 + i * .15, type: 'pop' } });
          xx += w + gapX;
        });
      }
    });
  };
  /** relative luminance (WCAG) and the contrast ratio of two colours */
  const relLum = (hex) => { const v = rgb(hex).map((c) => { c /= 255; return c <= .03928 ? c / 12.92 : Math.pow((c + .055) / 1.055, 2.4); }); return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]; };
  SK.contrast = (a, b) => { const A = relLum(a), B = relLum(b); return (Math.max(A, B) + .05) / (Math.min(A, B) + .05); };
  /** the colour of [dark, light] (or the darkest/lightest of a list) that reads best on bg */
  SK.readable = (bg, cands = ['#14171f', '#ffffff']) => cands.reduce((best, c) => (SK.contrast(bg, c) > SK.contrast(bg, best) ? c : best), cands[0]);
  /** Brand colours -> a palette that reads: {bg, ink, soft, accent, accentInk, on(col)}. brand: a hex
   *  (the accent) or {accent, bg?, ink?}; o.min (4.5) the contrast every text colour keeps on bg */
  SK.palette = function (brand, o = {}) {
    const b = typeof brand === 'string' ? { accent: brand } : brand, min = o.min ?? 4.5;
    const bg = b.bg ?? '#fbfaf7', accent = b.accent ?? '#2f6fdb';
    let ink = b.ink ?? SK.readable(bg, ['#14171f', '#ffffff']);
    if (SK.contrast(bg, ink) < min) ink = SK.readable(bg, ['#000000', '#ffffff']);
    let accentInk = accent;
    for (let k = 0; k < 12 && SK.contrast(bg, accentInk) < min; k++) accentInk = SK.mix(accentInk, lumOf(bg) > .5 ? '#000000' : '#ffffff', .12);
    return { bg, ink, soft: SK.mix(ink, bg, .38), accent, accentInk, on: (col) => SK.readable(col, [ink, bg, '#14171f', '#ffffff']) };
  };

  /* ================================================================ light and particles */
  /** a soft radial glow. o: alpha (1), blend ('lighter' | 'screen' | ...), inner (0..1: a solid core) */
  SK.glow = function (x, y, r, col, o = {}) {
    if (r <= 0 || (o.alpha ?? 1) <= 0) return;
    const c = ctx(), g = c.createRadialGradient(x, y, r * (o.inner ?? 0), x, y, r), base = isHex(col) ? col : '#ffd76a';
    g.addColorStop(0, alphaOf(base, 1)); g.addColorStop(.35, alphaOf(base, .45)); g.addColorStop(1, alphaOf(base, 0));
    c.save(); c.globalAlpha *= o.alpha ?? 1; if (o.blend) c.globalCompositeOperation = o.blend;
    c.fillStyle = g; c.fillRect(x - r, y - r, 2 * r, 2 * r); c.restore();
  };
  /** A pure-function emitter: every particle's place is worked out from t. o: x, y (or fn(t) -> [x, y]),
   *  t0 (0), t1 (when it stops emitting), rate (/s, 40), life (1.2 s), speed ([min, max] or one, 240),
   *  angle (-PI/2: up), spread (.6 rad), gravity (300), drag (0..1, .2), size ([min, max], [4, 9]),
   *  col (a colour or a list), shape ('dot' | 'square' | 'line' | 'confetti' | 'star' | fn(x, y, s, a, i)),
   *  fade (true), spin, seed, burst (n: all at t0 instead of a stream) */
  SK.particles = function (o = {}) {
    const t = SK.T, t0 = o.t0 ?? 0, t1 = o.t1 ?? 1e9, rate = o.rate ?? 40, life = o.life ?? 1.2, seed = o.seed ?? 7;
    const sp = [].concat(o.speed ?? 240), sz = [].concat(o.size ?? [4, 9]), cols = [].concat(o.col ?? C().accent), g = o.gravity ?? 300, drag = o.drag ?? .2;
    const n0 = o.burst ? 0 : Math.max(0, Math.floor((t - life - t0) * rate)), n1 = o.burst ? o.burst : Math.floor((Math.min(t, t1) - t0) * rate);
    const c = ctx();
    for (let i = n0; i <= n1; i++) {
      const born = o.burst ? t0 + SK.rnd(seed * 31 + i) * (o.jitter ?? 0) : t0 + i / rate, age = t - born;
      if (age < 0 || age > life) continue;
      const r = mulberry(seed * 977 + i * 131), ang = (o.angle ?? -Math.PI / 2) + (r() - .5) * 2 * (o.spread ?? .6), v = sp.length > 1 ? lerp(sp[0], sp[1], r()) : sp[0] * (.7 + .6 * r());
      const [ox, oy] = typeof o.x === 'function' ? o.x(born) : [o.x ?? 0, o.y ?? 0];
      const k = drag > 0 ? (1 - Math.exp(-drag * 3 * age)) / (drag * 3) : age;
      const px = ox + Math.cos(ang) * v * k, py = oy + Math.sin(ang) * v * k + .5 * g * age * age;
      const s = sz.length > 1 ? lerp(sz[0], sz[1], r()) : sz[0], a = o.fade === false ? 1 : 1 - Math.pow(age / life, 2), col = cols[Math.floor(r() * cols.length)];
      const shape = o.shape ?? 'dot', rot = (o.spin ?? 6) * age * (r() - .5) * 2 + r() * TAU;
      c.save(); c.globalAlpha *= a; c.fillStyle = col; c.strokeStyle = col;
      if (typeof shape === 'function') shape(px, py, s, a, i);
      else if (shape === 'square' || shape === 'confetti') { c.translate(px, py); c.rotate(rot); c.scale(1, shape === 'confetti' ? Math.abs(Math.cos(rot * 1.7)) * .9 + .1 : 1); c.fillRect(-s, -s * (shape === 'confetti' ? .6 : 1), 2 * s, s * (shape === 'confetti' ? 1.2 : 2)); }
      else if (shape === 'line') { c.lineWidth = Math.max(1.5, s * .4); c.lineCap = 'round'; c.beginPath(); c.moveTo(px, py); c.lineTo(px - Math.cos(ang) * s * 3, py - Math.sin(ang) * s * 3 - g * age * .02); c.stroke(); }
      else if (shape === 'star') { c.translate(px, py); c.rotate(rot); c.beginPath(); for (let j = 0; j < 10; j++) { const aa = j / 10 * TAU, kk = j % 2 ? s * .45 : s; c.lineTo(Math.cos(aa) * kk, Math.sin(aa) * kk); } c.closePath(); c.fill(); }
      else { c.beginPath(); c.arc(px, py, s, 0, TAU); c.fill(); }
      c.restore();
    }
  };
  /** rings spreading and fading from (x, y), from t0 (every `every` s if set). o: col, r0, r1 (70), d (1),
   *  n (2), w (4), every */
  SK.pulse = function (x, y, t0, o = {}) {
    const t = SK.T; if (t < t0) return;
    const d = o.d ?? 1, every = o.every, n = o.n ?? 2;
    const since = every ? (t - t0) % every : t - t0;
    for (let k = 0; k < n; k++) {
      const u = (since - k * d * .35) / d; if (u <= 0 || u >= 1) continue;
      disc(x, y, (o.r0 ?? 10) + (o.r1 ?? 70) * E.out(u), { stroke: o.col ?? C().accent, w: (o.w ?? 4) * (1 - u * .6), alpha: (1 - u) * (o.alpha ?? 1) });
    }
  };
  /* ================================================================ places: the real map of a real address
     The map tool (scripts/place-map.py) makes the picture and SK.DATA.place: where the address is on
     it (pin.u, pin.v), its own street as lines, and a spot on a straight stretch of each street
     where its name can be lettered. The picture carries no lettering and no pin: these draw both. */
  /** The map with the address's own spot at (x, y) -> {at(u, v), ll(lat, lon), s, cover, pin, street,
   *  place}, or null (and a warning) while the film has no map. */
  SK.map = function (x, y, o = {}) {
    const P = o.place ?? (SK.DATA || {}).place, im = P && SK.IMG[P.image];
    if (!P || !im || !P.pin) { warn('SK.map: no map yet -- the map tool makes it (SK.DATA.place)'); return null; }
    const v = SK.view || { x0: -SK.W / 2, x1: SK.W / 2, y0: -SK.H / 2, y1: SK.H / 2 };
    const W = P.w, H = P.h, pu = P.pin.u, pv = P.pin.v;
    const cover = Math.max((x - v.x0) / (pu * W), (v.x1 - x) / ((1 - pu) * W), (y - v.y0) / (pv * H), (v.y1 - y) / ((1 - pv) * H)); // the view has a margin past the frame: room for the camera to breathe
    const s = o.s ?? 1, t = SK.T, c = ctx();
    if (s < cover * .98) warn('SK.map: at this scale the map does not fill the frame (m.cover is the least that does)');
    const at = (u, vv) => [x + (u - pu) * W * s, y + (vv - pv) * H * s];
    const my = (lat) => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)), [bw, bs, be, bn] = P.bounds;
    const ll = (lat, lon) => at((lon - bw) / (be - bw), (my(bn) - my(lat)) / (my(bn) - my(bs)));
    const ink = o.nameCol ?? P.ink ?? '#4a5563', halo = o.halo ?? (P.look || {}).land ?? '#ffffff';
    const ownSpot = (P.streets || []).find((r) => r.own), street = ownSpot ? { x: at(ownSpot.u, ownSpot.v)[0], y: at(ownSpot.u, ownSpot.v)[1], a: ownSpot.a, name: ownSpot.short || ownSpot.name, len: ownSpot.len * s } : null;
    c.save(); c.globalAlpha *= o.alpha ?? 1;
    c.drawImage(im, x - pu * W * s, y - pv * H * s, W * s, H * s);
    if (o.own && (P.pin.lines || []).length) { // the address's own street, drawn out from the address
      const p = clamp(o.own.p ?? 1); c.lineCap = 'round'; c.lineJoin = 'round'; c.strokeStyle = o.own.col ?? C().accent; c.lineWidth = o.own.w ?? 14;
      P.pin.lines.forEach((ln, i) => {
        const pts = ln.map(([u, vv]) => at(u, vv)); if (pts.length < 2 || p <= 0) return;
        let u0 = 0;
        if (!i && P.pin.on) { const q = at(P.pin.on[0], P.pin.on[1]); let best = 1e18; for (let k = 0; k <= 60; k++) { const r = S.at(pts, k / 60), d = Math.hypot(r[0] - q[0], r[1] - q[1]); if (d < best) { best = d; u0 = k / 60; } } }
        const cut = S.cut(pts, u0 - p * u0, u0 + p * (1 - u0)); if (cut.length < 2) return;
        c.beginPath(); cut.forEach((q, k) => (k ? c.lineTo(q[0], q[1]) : c.moveTo(q[0], q[1]))); c.stroke();
      });
    }
    const n = o.names ?? 8, size0 = o.nameSize ?? 26, keep = o.clear || [], placed = [];
    (P.streets || []).filter((r) => !r.own || o.ownName !== false).slice(0, n).forEach((r, i) => {
      let left = o.namesT == null ? 1 : clamp((t - o.namesT - i * .06) / .35); if (left <= 0) return;
      const str = o.full ? r.name : r.short || r.name, f = { size: size0, font: o.font, wt: r.own ? 800 : o.nameWt ?? 600, ls: size0 * .02 };
      // its spot, or the next of its spare ones when that is off the frame, under a kept-clear box (a
      // name half under a card reads as a mistake) or on another name; one nearing the frame's edge
      // fades as the next comes up (the view runs 100 past each edge)
      for (const [cu, cv, ca, clen] of [[r.u, r.v, r.a, r.len], ...(r.alt || [])]) {
        const size = SK.fit(str, clen * s * .92, f); if (size < size0 * .62) continue; // the stretch is too short for it
        const [lx, ly] = at(cu, cv), hw = SK.measure(str, { ...f, size }) / 2, dx = Math.cos(ca) * hw, dy = Math.sin(ca) * hw;
        const pts = [[lx - dx, ly - dy], [lx, ly], [lx + dx, ly + dy]];
        if (keep.some(([bx, by, bw, bh]) => pts.some(([qx, qy]) => qx > bx - size && qx < bx + bw + size && qy > by - size && qy < by + bh + size))) continue;
        if (placed.some(([qx, qy]) => pts.some(([px, py]) => Math.hypot(px - qx, py - qy) < size * 1.7))) continue;
        const e = clamp(Math.min(...pts.map(([qx, qy]) => Math.min(qx - v.x0, v.x1 - qx, qy - v.y0, v.y1 - qy) - 100 - size * .5)) / 60 * 2 - .5); if (e <= 0) continue; // nothing, then all of it: no ghost of a name left behind
        SK.label(str, lx, ly, { ...f, size, rot: ca, col: r.own && o.own ? o.own.nameCol ?? ink : ink, stroke: size * .28, strokeCol: halo, alpha: left * e });
        placed.push(...pts); left *= 1 - e; if (left <= .02) break;
      }
    });
    if (o.credit !== false) { // on the frame itself, whatever the camera does: it has to show
      const k = o.credit ?? 'bl', m = 28, right = k[1] === 'r', top = k[0] === 't';
      SK.screen(() => SK.label(P.credit || '© OpenStreetMap', (right ? 1 : -1) * (SK.W / 2 - m), (top ? -1 : 1) * (SK.H / 2 - m), { size: o.creditSize ?? 20, font: o.font, wt: 500, col: ink, stroke: 5, strokeCol: halo, align: right ? 'right' : 'left', alpha: .85 }));
    }
    c.restore();
    return { at, ll, s, cover, pin: [x, y], street, place: P };
  };
  /** A map pin whose tip lands on (x, y) at o.t (always there without it). o: col, dot (the eye's
   *  colour), s, drop (how far it falls), pulse (false, or SK.pulse's options for its rings) */
  SK.mapPin = function (x, y, o = {}) {
    const t = SK.T, t0 = o.t ?? -1e6, col = o.col ?? C().accent, s = o.s ?? 1;
    if (t < t0 - .1) return;
    const k = clamp(E.back(clamp((t - t0 + .1) / .55)) * 1.2), py = y - (1 - land(clamp((t - t0 + .1) / .5))) * (o.drop ?? 260) * s;
    if (o.pulse !== false) SK.pulse(x, y, t0 + .35, { col, r1: 100 * s, ...(typeof o.pulse === 'object' ? o.pulse : {}) });
    const c = ctx(); c.save(); c.translate(x, py); c.scale(s * k, s * k);
    c.fillStyle = 'rgba(0,0,0,.22)'; c.beginPath(); c.ellipse(0, 4, 22, 8, 0, 0, TAU); c.fill();
    c.fillStyle = col; c.beginPath(); c.moveTo(0, 0); c.bezierCurveTo(-14, -30, -42, -52, -42, -84); c.arc(0, -84, 42, Math.PI, 0); c.bezierCurveTo(42, -52, 14, -30, 0, 0); c.fill();
    c.fillStyle = o.dot ?? '#ffffff'; c.beginPath(); c.arc(0, -84, 16, 0, TAU); c.fill();
    c.restore();
  };
  /** a white (o.col) flash over the frame at t0, fading over o.d (.4) */
  SK.flash = function (t, t0, o = {}) { const a = t >= t0 ? 1 - clamp((t - t0) / (o.d ?? .4)) : 0; if (a <= 0) return; SK.screen((c) => { c.fillStyle = o.col ?? '#ffffff'; c.globalAlpha *= a * (o.alpha ?? .85); c.fillRect(-SK.W / 2, -SK.H / 2, SK.W, SK.H); }); };
  /** the whole frame darkened by a (0..1) */
  SK.dim = function (a, col = '#000000') { if (a <= 0) return; SK.screen((c) => { c.fillStyle = col; c.globalAlpha *= a; c.fillRect(-SK.W / 2, -SK.H / 2, SK.W, SK.H); }); };
  /** everything but a circle (x, y, r in world units) darkened by a */
  SK.spotlight = function (x, y, r, a = .6, o = {}) {
    if (a <= 0) return;
    const c = ctx(), v = SK.view || { x0: -SK.W, x1: SK.W, y0: -SK.H, y1: SK.H };
    c.save(); c.globalAlpha *= a; c.fillStyle = o.col ?? '#000000';
    c.beginPath(); c.rect(v.x0 - 50, v.y0 - 50, v.x1 - v.x0 + 100, v.y1 - v.y0 + 100); c.arc(x, y, r, 0, TAU, true); c.fill('evenodd'); c.restore();
  };
})();
// studio: end cut
