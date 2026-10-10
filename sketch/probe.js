/* sketch/probe.js -- what a film draws, read from its drawing code as it runs.

   Put ahead of a film's code by `sketch-render.py --stills ... --probe` (the studio's motion check and
   its review, never a film's own files). After the stills are drawn the page calls SK.REPORT(), and
   this plays the whole film once more, every `step` seconds, WITHOUT painting anything: every canvas
   call that would put pixels down is counted instead. What comes back (saved as report.json beside
   the stills) says, for each sampled frame, which cast member's functions drew, where on the frame,
   under what transform and through what clip. studio/motion.py (events) turns that into sentences:
   the same character on screen twice for a moment, one that jumps across the frame, a body squashed
   through a sliver, a character cut by the edge of the thing it is inside, a character going into
   or out of something. Those are where a film breaks between two review stills.

   What it can see: calls made THROUGH a cast object (SK.cast.duchess.sit(...), or D.sit after
   `const D = SK.cast.duchess`). Every function of every cast member is wrapped here, before the
   film's code takes them. What a film draws with its own local functions has no name and is not
   reported. No convention is asked of a film: which functions are a character's poses is worked out
   afterwards from how they come and go.

   report: { step, w, h, keys: ["duchess.sit", ...], frames: [ { t, cam: [scale, tx, ty] | null, v,
     s: [ [key index, x0, y0, x1, y1, ops, anMax, anMin, cut, clipped, alpha, overlay, parent], ... ] } ],
     ms, cut_short? }
   x0..y1: the box of everything the call drew, in thousandths of the frame (it may run outside 0..1000);
   anMax / anMin: the largest and smallest squash among its draw calls (1 = undistorted, 0 = flat:
   the ratio of the transform's two scales; anMax small means the WHOLE thing is squashed, not a part
   of it such as a door turning on its hinge); cut: the share of what it drew that lay outside the clip
   that was in force when it was called (0..1: the opening of a box it is inside; clips made during the call,
   the engine's own, do not count); clipped: 1 when it was called inside a clip; alpha: the most opaque it was
   drawn; overlay: 1 when drawn in the film's overlay (screen space: a meter, a caption); parent: the
   key index of the cast call it was made inside, or -1. v: how much colour the film laid over the whole
   frame in that frame (the opacities of its translucent or blended fills that cover the frame, added up:
   a textured background gives the same figure all film long; an evening tint fading in makes it climb).

   Two more things are measured, for faults a frame a second shows and nobody was looking for:
   g: figures drawn in two pieces -- [x0, y0, x1, y1, gap, key index | -1] per figure, in thousandths of
   the frame (gap: of the figure's height). A figure is what one cast call draws (not a place), or one
   SK.at(...) group in the film's own code: upright, and split by a band of nothing into an upper and a
   lower piece that sit one above the other, each a real part of it (a head and cap floating over the
   shoulders they belong to: Leo episode 11 drew a boy from behind that way for 17 s).
   x: words on screen -- [x0, y0, x1, y1, height, text] per piece of text smaller than SMALL_TEXT of the
   frame's height (height in thousandths of it): what the type size comes to on the finished frame,
   under the camera's zoom. */
(function () {
  'use strict';
  const SK = window.SK;
  if (!SK || typeof CanvasRenderingContext2D === 'undefined') return;
  const CFG = window.__PROBE__ || {};
  const STEP = CFG.step > 0 ? CFG.step : 0.1, DEADLINE = CFG.deadline_ms || 30000;
  const P = CanvasRenderingContext2D.prototype;

  let on = false, main = null, W = 1, H = 1, inOverlay = false, inFilm = false, veiled = 0, frame = null;
  const stack = [], keys = [], keyIx = new Map();
  // figures: every open cast call (not a place) and SK.at group, each collecting the boxes of what is
  // drawn inside it; `split` and `texts` are what this frame found
  const figs = [], PARTS = 400, FIG_DEPTH = 8, SMALL_TEXT = 0.055;
  let split = null, texts = null, inText = false;
  function openFig(k) { const f = { k, parts: [], over: false, skip: figs.length >= FIG_DEPTH }; if (!f.skip) figs.push(f); return f; }
  function closeFig(f) {
    if (f.skip) return;
    const i = figs.lastIndexOf(f); if (i >= 0) figs.splice(i, 1);
    if (!split || f.over) return;
    const g = pieces(f.parts);
    if (g && split.length < 24) split.push([g[0], g[1], g[2], g[3], g[4], f.k]);
  }
  /* An upright figure whose boxes fall into an upper and a lower piece with a band of nothing between:
     [x0, y0, x1, y1, gap] in canvas pixels (gap: of its height), or null. Boxes are of whole paths, so
     they overlap more readily than the shapes do: what this finds is apart for certain, and it misses
     near things. */
  function pieces(p) {
    const n = p.length / 4; if (n < 5) return null;
    let X0 = Infinity, Y0 = Infinity, X1 = -Infinity, Y1 = -Infinity;
    for (let i = 0; i < p.length; i += 4) { if (p[i] < X0) X0 = p[i]; if (p[i + 1] < Y0) Y0 = p[i + 1]; if (p[i + 2] > X1) X1 = p[i + 2]; if (p[i + 3] > Y1) Y1 = p[i + 3]; }
    const h = Y1 - Y0, w = X1 - X0;
    if (h < 0.06 * H || h > 0.8 * H || w > 0.95 * h) return null; // a figure: upright, neither a speck nor a set
    if (X1 < 0 || X0 > W || Y1 < 0 || Y0 > H) return null;
    const ix = []; for (let i = 0; i < n; i++) ix.push(i);
    ix.sort((a, b) => p[a * 4 + 1] - p[b * 4 + 1]);
    const tol = Math.max(3, 0.012 * h);
    let end = p[ix[0] * 4 + 3];
    const bands = []; // every band of nothing across it, widest first
    for (let j = 1; j < n; j++) {
      const y0 = p[ix[j] * 4 + 1], y1 = p[ix[j] * 4 + 3];
      if (y0 - end > tol) bands.push([y0 - end, end, y0]);
      if (y1 > end) end = y1;
    }
    bands.sort((u, v) => v[0] - u[0]);
    for (const [best, a, b] of bands.slice(0, 4)) { const g = halves(p, h, best, a, b); if (g) return [X0, Y0, X1, Y1, g]; }
    return null;
  }
  function halves(p, h, best, a, b) { // the two pieces a band leaves: both real, one above the other -> the gap
    let ux0 = Infinity, ux1 = -Infinity, uy0 = Infinity, un = 0, lx0 = Infinity, lx1 = -Infinity, ly1 = -Infinity, ln = 0;
    for (let i = 0; i < p.length; i += 4) {
      if (p[i + 3] <= a + 0.5) { un++; if (p[i] < ux0) ux0 = p[i]; if (p[i + 2] > ux1) ux1 = p[i + 2]; if (p[i + 1] < uy0) uy0 = p[i + 1]; }
      else if (p[i + 1] >= b - 0.5) { ln++; if (p[i] < lx0) lx0 = p[i]; if (p[i + 2] > lx1) lx1 = p[i + 2]; if (p[i + 3] > ly1) ly1 = p[i + 3]; }
    }
    if (un < 4 || ln < 4) return null; // each piece is a thing of several marks (a sun's top rays are not)
    if (a - uy0 < 0.12 * h || ly1 - b < 0.12 * h) return null; // ... and a real part of the figure, not a spark over it
    const meetX = Math.min(ux1, lx1) - Math.max(ux0, lx0);
    if (meetX < 0.5 * Math.min(ux1 - ux0, lx1 - lx0)) return null; // one above the other
    return best / h;
  }
  const ix = (k) => { let i = keyIx.get(k); if (i === undefined) { i = keys.length; keys.push(k); keyIx.set(k, i); } return i; };

  /* ---------------------------------------------------------------- the cast: every function a named scope */
  function wrapCast() {
    for (const [name, m] of Object.entries(SK.cast || {})) {
      if (!m || typeof m !== 'object') continue;
      for (const k of Object.keys(m)) {
        const fn = m[k];
        if (typeof fn !== 'function' || fn.__probe) continue;
        const key = name + '.' + k;
        const w = function (...a) {
          if (!on) return fn.apply(this, a);
          // clip0: the clip in force when the call was made (the opening of the box she is inside). Clips set
          // during the call are the engine's own (a wash clips its texture to its shape) and do not count.
          const c0 = main ? st(main).clip : null;
          const s = { k: ix(key), box: null, ops: 0, anMax: 0, anMin: 1, area: 0, cutA: 0, clip0: c0 ? c0.slice() : null, alpha: 0, ov: inOverlay ? 1 : 0, parent: stack.length ? stack[stack.length - 1].k : -1 };
          stack.push(s);
          const fig = m.kind === 'place' || inOverlay ? null : openFig(s.k);
          try { return fn.apply(this, a); } finally {
            if (fig) closeFig(fig);
            stack.pop();
            if (s.ops && frame) frame.push(s);
          }
        };
        w.__probe = true;
        try { m[k] = w; } catch (e) { /* a frozen cast object: left as it is */ }
      }
    }
  }
  wrapCast(); // now: the film's code comes next and may take these into locals
  // ... and SK.at, the group a film's own code draws a figure in (a character no cast member has)
  if (typeof SK.at === 'function' && !SK.at.__probe) {
    const at0 = SK.at;
    const at1 = function (...a) {
      if (!on || inOverlay) return at0.apply(this, a);
      const fig = openFig(-1);
      try { return at0.apply(this, a); } finally { closeFig(fig); }
    };
    at1.__probe = true;
    try { SK.at = at1; } catch (e) { /* a frozen SK: left as it is */ }
  }

  /* ---------------------------------------------------------------- the canvas, counted instead of painted */
  const states = new WeakMap();
  const st = (c) => { let s = states.get(c); if (!s) { s = { m: null, path: null, clip: null, saved: [] }; states.set(c, s); } return s; };
  const NAT = {};
  const mat = (c, s) => s.m || (s.m = NAT.getTransform.call(c));
  function pt(c, x, y) {
    const s = st(c), m = mat(c, s), X = m.a * x + m.c * y + m.e, Y = m.b * x + m.d * y + m.f;
    const p = s.path;
    if (!p) s.path = [X, Y, X, Y];
    else { if (X < p[0]) p[0] = X; if (Y < p[1]) p[1] = Y; if (X > p[2]) p[2] = X; if (Y > p[3]) p[3] = Y; }
  }
  const corners = (c, x, y, w, h) => { pt(c, x, y); pt(c, x + w, y); pt(c, x, y + h); pt(c, x + w, y + h); };
  const area = (b) => (b ? Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]) : 0);
  const meet = (a, b) => (!a ? b : !b ? a : [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])]);
  const onFrame = (b) => [Math.max(0, b[0]), Math.max(0, b[1]), Math.min(W, b[2]), Math.min(H, b[3])];
  function squash(m) { // the ratio of the transform's two scales: 1 undistorted, 0 flat
    const E = (m.a * m.a + m.b * m.b + m.c * m.c + m.d * m.d) / 2, G = (m.a * m.a + m.b * m.b - m.c * m.c - m.d * m.d) / 2, K = m.a * m.c + m.b * m.d;
    const F = Math.sqrt(G * G + K * K), s1 = Math.sqrt(E + F), s2 = Math.sqrt(Math.max(0, E - F));
    return s1 > 0 ? s2 / s1 : 1;
  }
  function count(c, box) { // one draw call's box, given to the cast call it was made inside
    if (c !== main || !box) return;
    const a = c.globalAlpha;
    // ... and to every figure it is part of: solid marks only (a shadow, a glow and words are not the body)
    if (figs.length && a >= 0.6 && !inText) {
      // what shows of it: a wash lays its texture across a wider box, clipped to its own shape
      const cb = st(c).clip, v = cb ? meet(box, cb) : box;
      if (v[2] - v[0] > 1 || v[3] - v[1] > 1) { // a mark, in either direction: a straight leg has no width
        for (const f of figs) { if (f.parts.length >= PARTS * 4) f.over = true; else f.parts.push(v[0], v[1], v[2], v[3]); }
      }
    }
    if (!stack.length) return;
    if (!(a > 0.08)) return;
    const s = stack[stack.length - 1], S = st(c);
    const b = s.box;
    if (!b) s.box = box.slice();
    else { if (box[0] < b[0]) b[0] = box[0]; if (box[1] < b[1]) b[1] = box[1]; if (box[2] > b[2]) b[2] = box[2]; if (box[3] > b[3]) b[3] = box[3]; }
    s.ops++;
    if (a > s.alpha) s.alpha = a;
    const q = squash(mat(c, S));
    if (q > s.anMax) s.anMax = q;
    if (q < s.anMin) s.anMin = q;
    const vis = onFrame(box), va = area(vis);
    s.area += va;
    if (s.clip0) s.cutA += va - area(meet(vis, s.clip0));
  }
  // a colour laid over the whole frame by the film itself (not the engine's grain, vignette or fades,
  // which come after the film's own drawing): a fill that covers the frame and lets it show through
  function veil(c, box) {
    if (c !== main || !inFilm || !box) return;
    const a = c.globalAlpha, op = c.globalCompositeOperation;
    if (!(a > 0.02) || (a >= 0.9 && op === 'source-over')) return;
    if (area(onFrame(box)) < 0.9 * W * H) return;
    veiled += a;
  }
  // words drawn small: the type size as it lands on the frame (its px size under the transform in force)
  let saying = null; // the SK.txt call being drawn: { str, hgt, box, alpha }
  function words(c, t, box) {
    if (c !== main || !texts || !box) return;
    const px = parseFloat((/(\d+(?:\.\d+)?)px/.exec(c.font) || [0, 0])[1]);
    if (!px) return;
    const m = mat(c, st(c)), k = Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
    const hgt = px * k / H, a = c.globalAlpha;
    if (saying) { // one character of it: the string's size is its smallest, its box all of them
      if (hgt < saying.hgt) saying.hgt = hgt;
      if (a > saying.alpha) saying.alpha = a;
      const b = saying.box;
      if (!b) saying.box = box.slice();
      else { if (box[0] < b[0]) b[0] = box[0]; if (box[1] < b[1]) b[1] = box[1]; if (box[2] > b[2]) b[2] = box[2]; if (box[3] > b[3]) b[3] = box[3]; }
      return;
    }
    said(String(t), hgt, box, a);
  }
  function said(str, hgt, box, a) {
    str = str.trim();
    if (!texts || texts.length >= 40 || !box || !(a >= 0.5) || !(hgt < SMALL_TEXT)) return;
    if (str.replace(/[^\p{L}\p{N}]/gu, '').length < 2) return;
    if (area(onFrame(box)) < 0.5 * area(box)) return; // mostly off the frame: nobody is asked to read it
    texts.push([Math.round(box[0] / W * 1000), Math.round(box[1] / H * 1000), Math.round(box[2] / W * 1000), Math.round(box[3] / H * 1000), Math.round(hgt * 1000), str.slice(0, 48)]);
  }
  if (typeof SK.txt === 'function' && !SK.txt.__probe) {
    const txt0 = SK.txt;
    const txt1 = function (str, ...a) {
      if (!on || inOverlay || saying) return txt0.call(this, str, ...a);
      saying = { str: String(str), hgt: Infinity, box: null, alpha: 0 };
      try { return txt0.call(this, str, ...a); } finally { const w = saying; saying = null; if (w.box) said(w.str, w.hgt, w.box, w.alpha); }
    };
    txt1.__probe = true;
    try { SK.txt = txt1; } catch (e) { /* a frozen SK: left as it is */ }
  }
  const boxOf = (c, fn) => { const S = st(c), keep = S.path; S.path = null; fn(); const b = S.path; S.path = keep; return b; };
  const HOOK = {
    save() { NAT.save.call(this); const s = st(this); s.saved.push(s.clip); },
    restore() { NAT.restore.call(this); const s = st(this); if (s.saved.length) s.clip = s.saved.pop(); s.m = null; },
    translate(...a) { NAT.translate.apply(this, a); st(this).m = null; },
    rotate(...a) { NAT.rotate.apply(this, a); st(this).m = null; },
    scale(...a) { NAT.scale.apply(this, a); st(this).m = null; },
    transform(...a) { NAT.transform.apply(this, a); st(this).m = null; },
    setTransform(...a) { NAT.setTransform.apply(this, a); st(this).m = null; },
    resetTransform() { NAT.resetTransform.call(this); st(this).m = null; },
    beginPath() { st(this).path = null; },
    closePath() {},
    moveTo(x, y) { pt(this, x, y); },
    lineTo(x, y) { pt(this, x, y); },
    quadraticCurveTo(a, b, x, y) { pt(this, a, b); pt(this, x, y); },
    bezierCurveTo(a, b, c, d, x, y) { pt(this, a, b); pt(this, c, d); pt(this, x, y); },
    arcTo(a, b, x, y) { pt(this, a, b); pt(this, x, y); },
    arc(x, y, r) { corners(this, x - r, y - r, 2 * r, 2 * r); },
    ellipse(x, y, rx, ry) { const r = Math.max(rx, ry); corners(this, x - r, y - r, 2 * r, 2 * r); },
    rect(x, y, w, h) { corners(this, x, y, w, h); },
    roundRect(x, y, w, h) { corners(this, x, y, w, h); },
    clip() { const s = st(this); if (s.path) s.clip = meet(s.clip, s.path.slice()); },
    fill() { const b = st(this).path; veil(this, b); count(this, b); },
    stroke() { count(this, st(this).path); },
    fillRect(x, y, w, h) { const b = boxOf(this, () => corners(this, x, y, w, h)); veil(this, b); count(this, b); },
    strokeRect(x, y, w, h) { count(this, boxOf(this, () => corners(this, x, y, w, h))); },
    clearRect() {},
    putImageData() {},
    drawImage(im, ...a) {
      let x, y, w, h;
      if (a.length >= 8) [, , , , x, y, w, h] = a; else [x, y, w, h] = a;
      if (w === undefined) { w = im.width || 0; h = im.height || 0; }
      count(this, boxOf(this, () => corners(this, x, y, w, h)));
    },
    fillText(t, x, y) { const w = NAT.measureText.call(this, String(t)).width; const b = boxOf(this, () => corners(this, x - w / 2, y - 20, w * 1.5, 30)); words(this, t, b); inText = true; try { count(this, b); } finally { inText = false; } },
    strokeText(t, x, y) { const w = NAT.measureText.call(this, String(t)).width; const b = boxOf(this, () => corners(this, x - w / 2, y - 20, w * 1.5, 30)); inText = true; try { count(this, b); } finally { inText = false; } },
  };
  for (const k of [...Object.keys(HOOK), 'getTransform', 'measureText']) NAT[k] = P[k];
  const install = () => { for (const k of Object.keys(HOOK)) if (typeof NAT[k] === 'function') P[k] = HOOK[k]; };
  const remove = () => { for (const k of Object.keys(HOOK)) if (typeof NAT[k] === 'function') P[k] = NAT[k]; };

  /* ---------------------------------------------------------------- the pass */
  const r3 = (v) => Math.round(v * 1000) / 1000;
  function run() {
    const F = SK._film, D = F.duration, t0 = performance.now();
    const out = { step: STEP, w: 0, h: 0, keys, frames: [] };
    main = SK.ctx(); W = main.canvas.width; H = main.canvas.height; out.w = W; out.h = H;
    const draw = F.draw, overlay = F.overlay;
    let cam = null;
    F.draw = function (...a) { const m = NAT.getTransform.call(main); cam = [r3(Math.hypot(m.a, m.b)), Math.round(m.e), Math.round(m.f)]; inFilm = true; try { return draw.apply(this, a); } finally { inFilm = false; } };
    if (overlay) F.overlay = function (...a) { inOverlay = true; inFilm = true; try { return overlay.apply(this, a); } finally { inOverlay = false; inFilm = false; } };
    wrapCast(); // whatever the film added to the cast itself
    install(); on = true;
    try {
      const one = (t) => {
        frame = []; cam = null; stack.length = 0; veiled = 0; figs.length = 0; split = []; texts = [];
        states.delete(main); // a frame starts from a clean state (SK.render sets the transform itself)
        try { SK.render(t); } catch (e) { if (!out.error) out.error = t + ': ' + String(e && e.message || e); }
      };
      // The whole film must fit the time allowed, so it is read coarse to fine: every 4 steps
      // first, then the frames between, then the rest. A heavy film on a busy machine comes back
      // whole at a coarser step rather than only as far as it got (one cut short at 0:49 said
      // nothing of its second minute). A pass that cannot finish in time is not started.
      const got = new Map(), n = Math.ceil((D - 1e-6) / STEP);
      let done = 0, spent = 0, stride = 0;
      for (const [every, from] of [[4, 0], [4, 2], [2, 1]]) {
        const todo = []; for (let i = from; i < n; i += every) todo.push(i);
        if (done && spent / done * todo.length > DEADLINE - (performance.now() - t0)) break;
        const p0 = performance.now(), part = [];
        let whole = true;
        for (const i of todo) {
          if (performance.now() - t0 > DEADLINE * 1.25) { whole = false; break; }
          const t = Math.round(i * STEP * 1000) / 1000;
          one(t);
          const row = { t, cam, v: r3(veiled), s: frame.map((s) => {
            const b = s.box;
            return [s.k, Math.round(b[0] / W * 1000), Math.round(b[1] / H * 1000), Math.round(b[2] / W * 1000), Math.round(b[3] / H * 1000),
              s.ops, r3(s.anMax), r3(s.anMin), s.area > 0 ? r3(s.cutA / s.area) : 0, s.clip0 ? 1 : 0, r3(s.alpha), s.ov, s.parent];
          }) };
          if (split.length) row.g = split.map((g) => [Math.round(g[0] / W * 1000), Math.round(g[1] / H * 1000), Math.round(g[2] / W * 1000), Math.round(g[3] / H * 1000), Math.round(g[4] * 1000), g[5]]);
          if (texts.length) row.x = texts;
          part.push([i, row]);
        }
        spent += performance.now() - p0; done += part.length;
        if (!whole) { if (!stride) { for (const [i, f] of part) got.set(i, f); out.cut_short = part.length ? part[part.length - 1][1].t : 0; stride = 4; } break; }
        for (const [i, f] of part) got.set(i, f);
        stride = every === 4 && from === 0 ? 4 : every === 4 ? 2 : 1;
      }
      out.step = Math.round(STEP * (stride || 4) * 1000) / 1000;
      out.frame_ms = done ? r3(spent / done) : 0;
      out.frames = [...got.keys()].sort((a, b) => a - b).map((i) => got.get(i));
    } finally {
      on = false; remove(); F.draw = draw; if (overlay) F.overlay = overlay; frame = null; split = null; texts = null; figs.length = 0;
    }
    out.ms = Math.round(performance.now() - t0);
    return out;
  }
  SK.REPORT = function () { try { return { probe: run() }; } catch (e) { on = false; try { remove(); } catch (e2) { /* nothing */ } return { probe: { error: String(e && e.stack || e) } }; } };
})();
