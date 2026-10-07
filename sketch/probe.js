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

   report: { step, w, h, keys: ["duchess.sit", ...], frames: [ { t, cam: [scale, tx, ty] | null,
     s: [ [key index, x0, y0, x1, y1, ops, anMax, anMin, cut, clipped, alpha, overlay, parent], ... ] } ],
     ms, cut_short? }
   x0..y1: the box of everything the call drew, in thousandths of the frame (it may run outside 0..1000);
   anMax / anMin: the largest and smallest squash among its draw calls (1 = undistorted, 0 = flat:
   the ratio of the transform's two scales; anMax small means the WHOLE thing is squashed, not a part
   of it such as a door turning on its hinge); cut: the share of what it drew that lay outside the clip
   that was in force when it was called (0..1: the opening of a box it is inside; clips made during the call,
   the engine's own, do not count); clipped: 1 when it was called inside a clip; alpha: the most opaque it was
   drawn; overlay: 1 when drawn in the film's overlay (screen space: a meter, a caption); parent: the
   key index of the cast call it was made inside, or -1. */
(function () {
  'use strict';
  const SK = window.SK;
  if (!SK || typeof CanvasRenderingContext2D === 'undefined') return;
  const CFG = window.__PROBE__ || {};
  const STEP = CFG.step > 0 ? CFG.step : 0.1, DEADLINE = CFG.deadline_ms || 30000;
  const P = CanvasRenderingContext2D.prototype;

  let on = false, main = null, W = 1, H = 1, inOverlay = false, frame = null;
  const stack = [], keys = [], keyIx = new Map();
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
          try { return fn.apply(this, a); } finally {
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
    if (c !== main || !box || !stack.length) return;
    const a = c.globalAlpha;
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
    fill() { count(this, st(this).path); },
    stroke() { count(this, st(this).path); },
    fillRect(x, y, w, h) { count(this, boxOf(this, () => corners(this, x, y, w, h))); },
    strokeRect(x, y, w, h) { count(this, boxOf(this, () => corners(this, x, y, w, h))); },
    clearRect() {},
    putImageData() {},
    drawImage(im, ...a) {
      let x, y, w, h;
      if (a.length >= 8) [, , , , x, y, w, h] = a; else [x, y, w, h] = a;
      if (w === undefined) { w = im.width || 0; h = im.height || 0; }
      count(this, boxOf(this, () => corners(this, x, y, w, h)));
    },
    fillText(t, x, y) { const w = NAT.measureText.call(this, String(t)).width; count(this, boxOf(this, () => corners(this, x - w / 2, y - 20, w * 1.5, 30))); },
    strokeText(t, x, y) { const w = NAT.measureText.call(this, String(t)).width; count(this, boxOf(this, () => corners(this, x - w / 2, y - 20, w * 1.5, 30))); },
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
    F.draw = function (...a) { const m = NAT.getTransform.call(main); cam = [r3(Math.hypot(m.a, m.b)), Math.round(m.e), Math.round(m.f)]; return draw.apply(this, a); };
    if (overlay) F.overlay = function (...a) { inOverlay = true; try { return overlay.apply(this, a); } finally { inOverlay = false; } };
    wrapCast(); // whatever the film added to the cast itself
    install(); on = true;
    try {
      const one = (t) => {
        frame = []; cam = null; stack.length = 0;
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
          part.push([i, { t, cam, s: frame.map((s) => {
            const b = s.box;
            return [s.k, Math.round(b[0] / W * 1000), Math.round(b[1] / H * 1000), Math.round(b[2] / W * 1000), Math.round(b[3] / H * 1000),
              s.ops, r3(s.anMax), r3(s.anMin), s.area > 0 ? r3(s.cutA / s.area) : 0, s.clip0 ? 1 : 0, r3(s.alpha), s.ov, s.parent];
          }) }]);
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
      on = false; remove(); F.draw = draw; if (overlay) F.overlay = overlay; frame = null;
    }
    out.ms = Math.round(performance.now() - t0);
    return out;
  }
  SK.REPORT = function () { try { return { probe: run() }; } catch (e) { on = false; try { remove(); } catch (e2) { /* nothing */ } return { probe: { error: String(e && e.stack || e) } }; } };
})();
