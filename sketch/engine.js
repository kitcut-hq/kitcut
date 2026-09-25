/* sketch/engine.js -- the hand-drawn film engine (vanilla JS, Canvas 2D, no libraries).

   Everything here is brand-free and scene-free. A film (projects/<id>/film.js) calls
   SK.film({...}) with a camera, a duration and a draw(t, vis) function built from the
   primitives below; sketch/player.html plays it live against its audio and exports it
   frame by frame for scripts/sketch-render.py.

   The one rule that makes both possible: every frame is a pure function of t. Nothing may
   keep state between frames (no physics integration, no Math.random) -- randomness comes
   from SK.rnd(seed) / SK.mulberry(seed), motion from t.

   The look:
     * lines are re-jittered ("boil") BOIL_FPS times a second, like a traced cel;
     * each stroke has a pressure taper and a faint second pencil pass;
     * fills sit a few px off their outline (cel mis-registration) with crayon grain;
     * paper and film grain are screen-space, so a wide shot never balloons the texture.
*/
(function () {
  'use strict';
  const SK = (window.SK = window.SK || {});
  const W = (SK.W = 1920), H = (SK.H = 1080);
  let ctx = null;
  SK.BOIL_FPS = 8;
  SK.T = 0; SK.BOIL = 0;

  /* ------------------------------------------------------------ style: one engine, several looks
     'crayon' is the whimsical hand-drawn look; 'clean' is crisp editorial line art (no boil, no
     pencil pass, exact fills, flat ground). A film picks one with SK.setStyle(name, overrides). */
  SK.STYLES = {
    crayon: { boil: true, jit: 1, dbl: true, taper: true, misreg: 1, fillTex: true, paper: 'paper', grain: 1, vignette: .2, handheld: 1, textWob: 1, textMode: 'pop', grid: null },
    clean: { boil: false, jit: 0, dbl: false, taper: false, misreg: 0, fillTex: false, paper: 'flat', grain: .45, vignette: .1, handheld: .35, textWob: 0, textMode: 'rise', grid: null },
  };
  SK.style = { ...SK.STYLES.crayon };
  SK.setStyle = function (name, over = {}) { SK.style = { ...(SK.STYLES[name] || SK.STYLES.crayon), ...over }; };

  /* ------------------------------------------------------------ palette (a film may Object.assign over it) */
  SK.C = {
    paper: '#f7f2e7', ink: '#2a2521', inkSoft: '#6b635a',
    orange: '#d9733f', orangeDk: '#c2592a', grey: '#d8d1c5',
    wood: '#e8cda2', woodDk: '#cfa36c', woodIn: '#b98a55',
    skin: '#f8d8bd', blush: '#f2a19a', cream: '#fff8ec',
    shirtA: '#8db5de', shirtB: '#a9cb92', hairA: '#4a3528', hairB: '#a4532b',
    yellow: '#f6cd4b', coin: '#f3c24a', screenOff: '#e9e3d6', screen: '#2e2a26',
    heart: '#e8665a', pink: '#f4b3b0', teal: '#7cc4b8', lilac: '#b9a6dd', green: '#6fae6b',
  };
  SK.FONT_HAND = 'Caveat';
  SK.FONT_PRINT = 'Patrick Hand';

  /* ------------------------------------------------------------ math */
  const TAU = (SK.TAU = Math.PI * 2);
  const clamp = (SK.clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x)));
  const lerp = (SK.lerp = (a, b, t) => a + (b - a) * t);
  const inv = (SK.inv = (a, b, x) => clamp((x - a) / (b - a)));
  const E = (SK.E = {
    lin: t => t,
    inOut: t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
    out: t => 1 - Math.pow(1 - t, 3),
    in: t => t * t * t,
    sine: t => -(Math.cos(Math.PI * t) - 1) / 2,
    back: t => { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
    elastic: t => t <= 0 ? 0 : t >= 1 ? 1 : Math.pow(2, -9 * t) * Math.sin((t * 9 - .75) * TAU / 3) + 1,
    quint: t => t < .5 ? 16 * t ** 5 : 1 - Math.pow(-2 * t + 2, 5) / 2,
  });
  const tw = (SK.tw = (t, a, b, e = E.inOut) => e(inv(a, b, t)));
  /** keyframes [[t, v, ease?], ...]; v may be a number or an array */
  SK.kf = function (t, keys, e = E.inOut) {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      if (t <= keys[i][0]) {
        const [t0, v0] = keys[i - 1], [t1, v1, ee] = keys[i];
        const u = (ee || e)((t - t0) / (t1 - t0));
        return Array.isArray(v0) ? v0.map((v, j) => lerp(v, v1[j], u)) : lerp(v0, v1, u);
      }
    }
    return keys[keys.length - 1][1];
  };
  /** 0 before t0, then an overshooting pop to 1 over d seconds */
  const pop = (SK.pop = (t, t0, d = .45) => t < t0 ? 0 : E.back(inv(t0, t0 + d, t)));
  const mulberry = (SK.mulberry = function (a) {
    return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  });
  const rnd = (SK.rnd = s => mulberry(s)());
  const mix = (SK.mix = function (c1, c2, t) {
    const a = parseInt(c1.slice(1), 16), b = parseInt(c2.slice(1), 16);
    const r = Math.round(lerp(a >> 16, b >> 16, t)), g = Math.round(lerp(a >> 8 & 255, b >> 8 & 255, t)), bl = Math.round(lerp(a & 255, b & 255, t));
    return '#' + ((1 << 24) | (r << 16) | (g << 8) | bl).toString(16).slice(1);
  });

  /* ------------------------------------------------------------ strokes */
  function jitter(pts, seed, amp) {
    amp *= SK.style.jit;
    if (amp === 0) return pts;
    const r = mulberry((seed * 7919 + (SK.style.boil ? SK.BOIL : 0) * 104729 + 13) | 0);
    const f1 = .010 + r() * .010, f2 = .028 + r() * .022, p1 = r() * TAU, p2 = r() * TAU;
    const ox = (r() - .5) * amp, oy = (r() - .5) * amp;
    const out = new Array(pts.length); let s = 0;
    for (let i = 0; i < pts.length; i++) {
      if (i) s += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
      let nx = -(b[1] - a[1]), ny = b[0] - a[0]; const nl = Math.hypot(nx, ny) || 1; nx /= nl; ny /= nl;
      const d = amp * (.65 * Math.sin(s * f1 + p1) + .35 * Math.sin(s * f2 + p2));
      out[i] = [pts[i][0] + nx * d + ox, pts[i][1] + ny * d + oy];
    }
    return out;
  }
  SK.jitter = jitter;

  /** Ink stroke. o: w, col, p (draw-on 0..1), seed, jit, alpha, taper (default true), dbl (second pencil pass) */
  SK.ink = function (pts, o = {}) {
    const p = o.p ?? 1; if (p <= 0 || !pts || pts.length < 2) return;
    const w = o.w ?? 5, seed = o.seed ?? 1, amp = o.jit ?? 1.8, col = o.col ?? SK.C.ink;
    const q = jitter(pts, seed, amp);
    const last = (q.length - 1) * Math.min(1, p);
    const n = Math.floor(last);
    const pt = (i) => i <= n ? q[i] : [lerp(q[n][0], q[n + 1][0], last - n), lerp(q[n][1], q[n + 1][1], last - n)];
    const base = ctx.globalAlpha; ctx.globalAlpha = base * (o.alpha ?? 1);
    ctx.strokeStyle = col; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const CH = 3, L = q.length - 1;
    for (let i = 0; i < last; i += CH) {
      const j = Math.min(last, i + CH);
      const u = (i + j) / 2 / L;
      let ww = w;
      if (o.taper !== false && SK.style.taper) ww *= .5 + .5 * Math.min(1, Math.min(u, 1 - u) * 7);
      if (SK.style.taper) ww *= .88 + .24 * (.5 + .5 * Math.sin(u * 11 + seed));
      ctx.lineWidth = ww; ctx.beginPath();
      const a = pt(i); ctx.moveTo(a[0], a[1]);
      for (let k = Math.floor(i) + 1; k < j; k++) ctx.lineTo(q[k][0], q[k][1]);
      const b = pt(j); ctx.lineTo(b[0], b[1]); ctx.stroke();
    }
    if (o.dbl !== false && SK.style.dbl && w > 2.6) {
      const q2 = jitter(pts, seed + 71, amp * 1.25);
      ctx.globalAlpha = base * (o.alpha ?? 1) * .38; ctx.lineWidth = w * .42;
      ctx.beginPath(); ctx.moveTo(q2[0][0], q2[0][1]);
      const m = Math.max(1, Math.floor(last * .97));
      for (let k = 1; k <= m; k++) ctx.lineTo(q2[k][0], q2[k][1]);
      ctx.stroke();
    }
    ctx.globalAlpha = base;
  };

  /** Flat fill, mis-registered from its outline, with crayon grain. o: seed, dx, dy, alpha, tex, texCol, gap, jit */
  SK.wash = function (pts, col, o = {}) {
    if (!pts || pts.length < 3) return;
    const a = o.alpha ?? 1; if (a <= 0) return;
    const q = jitter(pts, (o.seed ?? 1) + 500, o.jit ?? 2.2);
    const dx = (o.dx ?? 5) * SK.style.misreg, dy = (o.dy ?? 4) * SK.style.misreg;
    const base = ctx.globalAlpha; ctx.globalAlpha = base * a;
    ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(q[0][0] + dx, q[0][1] + dy);
    for (let i = 1; i < q.length; i++) ctx.lineTo(q[i][0] + dx, q[i][1] + dy);
    ctx.closePath(); ctx.fill();
    if (o.tex !== false && SK.style.fillTex) {
      ctx.save(); ctx.clip();
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
      for (const [x, y] of q) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
      const gap = o.gap ?? 11, r = mulberry((o.seed ?? 1) * 31 + SK.BOIL * 17);
      ctx.strokeStyle = o.texCol ?? 'rgba(255,255,255,0.22)'; ctx.lineWidth = o.texW ?? 3.2; ctx.lineCap = 'round';
      ctx.beginPath();
      const span = (x1 - x0) + (y1 - y0);
      for (let s = -span; s < span; s += gap) {
        const j = (r() - .5) * gap * .6;
        ctx.moveTo(x0 + s + j, y1 + 4); ctx.lineTo(x0 + s + (y1 - y0) * .55 + j + 8, y0 - 4);
      }
      ctx.stroke(); ctx.restore();
    }
    ctx.globalAlpha = base;
  };

  /** Diagonal hatching for shadows. o: seed, gap, col, alpha, w */
  SK.hatch = function (pts, o = {}) {
    const q = jitter(pts, (o.seed ?? 1) + 900, 2);
    ctx.save(); ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]);
    for (const p of q) ctx.lineTo(p[0], p[1]); ctx.closePath(); ctx.clip();
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const [x, y] of q) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    const gap = o.gap ?? 16, r = mulberry((o.seed ?? 1) * 13 + SK.BOIL * 7);
    ctx.strokeStyle = o.col ?? SK.C.ink; ctx.globalAlpha *= o.alpha ?? .35; ctx.lineWidth = o.w ?? 2.4; ctx.lineCap = 'round';
    ctx.beginPath();
    const hgt = y1 - y0;
    for (let s = x0 - hgt; s < x1; s += gap) {
      const j = (r() - .5) * 4;
      ctx.moveTo(s + j, y1); ctx.lineTo(s + hgt + j + (r() - .5) * 6, y0);
    }
    ctx.stroke(); ctx.restore();
  };

  /* ------------------------------------------------------------ shapes: dense point lists */
  const S = (SK.S = {
    line(x1, y1, x2, y2, bow = 0) {
      const L = Math.hypot(x2 - x1, y2 - y1) || 1, n = Math.max(2, Math.ceil(L / 7));
      const nx = -(y2 - y1) / L, ny = (x2 - x1) / L, out = [];
      for (let i = 0; i <= n; i++) { const u = i / n, b = bow * Math.sin(Math.PI * u); out.push([x1 + (x2 - x1) * u + nx * b, y1 + (y2 - y1) * u + ny * b]); }
      return out;
    },
    /** open ellipse that overshoots its start, like a real hand-drawn circle */
    ell(cx, cy, rx, ry, a0 = -2.3, over = .32, rot = 0) {
      const n = Math.max(14, Math.ceil(Math.PI * (rx + ry) / 7)), out = [];
      const tot = TAU + over, cr = Math.cos(rot), sr = Math.sin(rot);
      for (let i = 0; i <= n * (tot / TAU); i++) {
        const a = a0 + i / n * TAU, k = 1 + .025 * Math.sin(i / n * TAU * 2 + a0);
        const x = Math.cos(a) * rx * k, y = Math.sin(a) * ry * k;
        out.push([cx + x * cr - y * sr, cy + x * sr + y * cr]);
      }
      return out;
    },
    /** closed ellipse, for fills */
    ellC(cx, cy, rx, ry, rot = 0) {
      const n = Math.max(14, Math.ceil(Math.PI * (rx + ry) / 7)), out = [], cr = Math.cos(rot), sr = Math.sin(rot);
      for (let i = 0; i < n; i++) { const a = i / n * TAU, x = Math.cos(a) * rx, y = Math.sin(a) * ry; out.push([cx + x * cr - y * sr, cy + x * sr + y * cr]); }
      return out;
    },
    arc(cx, cy, r, a0, a1, ry) {
      ry = ry ?? r; const n = Math.max(4, Math.ceil(Math.abs(a1 - a0) * Math.max(r, ry) / 7)), out = [];
      for (let i = 0; i <= n; i++) { const a = a0 + (a1 - a0) * i / n; out.push([cx + Math.cos(a) * r, cy + Math.sin(a) * ry]); }
      return out;
    },
    poly(arr, closed = false) {
      const out = []; const P = closed ? [...arr, arr[0]] : arr;
      for (let i = 1; i < P.length; i++) { const seg = S.line(P[i - 1][0], P[i - 1][1], P[i][0], P[i][1]); if (i > 1) seg.shift(); out.push(...seg); }
      return out;
    },
    rrect(x, y, w, h, r) {
      const out = [], add = (a) => { if (out.length) a.shift(); out.push(...a); };
      add(S.line(x + r, y, x + w - r, y)); add(S.arc(x + w - r, y + r, r, -Math.PI / 2, 0));
      add(S.line(x + w, y + r, x + w, y + h - r)); add(S.arc(x + w - r, y + h - r, r, 0, Math.PI / 2));
      add(S.line(x + w - r, y + h, x + r, y + h)); add(S.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI));
      add(S.line(x, y + h - r, x, y + r)); add(S.arc(x + r, y + r, r, Math.PI, Math.PI * 1.5));
      return out;
    },
    /** SVG-ish path: [['M',x,y],['L',x,y],['Q',cx,cy,x,y],['C',c1x,c1y,c2x,c2y,x,y],['Z']] */
    path(cmds) {
      const out = []; let cx = 0, cy = 0, sx = 0, sy = 0;
      for (const c of cmds) {
        if (c[0] === 'M') { cx = sx = c[1]; cy = sy = c[2]; out.push([cx, cy]); }
        else if (c[0] === 'L' || c[0] === 'Z') {
          const x = c[0] === 'Z' ? sx : c[1], y = c[0] === 'Z' ? sy : c[2];
          const s = S.line(cx, cy, x, y); s.shift(); out.push(...s); cx = x; cy = y;
        } else if (c[0] === 'Q') {
          const L = Math.hypot(c[1] - cx, c[2] - cy) + Math.hypot(c[3] - c[1], c[4] - c[2]), n = Math.max(4, Math.ceil(L / 7));
          for (let i = 1; i <= n; i++) { const u = i / n, v = 1 - u; out.push([v * v * cx + 2 * v * u * c[1] + u * u * c[3], v * v * cy + 2 * v * u * c[2] + u * u * c[4]]); }
          cx = c[3]; cy = c[4];
        } else if (c[0] === 'C') {
          const L = Math.hypot(c[1] - cx, c[2] - cy) + Math.hypot(c[3] - c[1], c[4] - c[2]) + Math.hypot(c[5] - c[3], c[6] - c[4]), n = Math.max(5, Math.ceil(L / 7));
          for (let i = 1; i <= n; i++) {
            const u = i / n, v = 1 - u;
            out.push([v * v * v * cx + 3 * v * v * u * c[1] + 3 * v * u * u * c[3] + u * u * u * c[5], v * v * v * cy + 3 * v * v * u * c[2] + 3 * v * u * u * c[4] + u * u * u * c[6]]);
          }
          cx = c[5]; cy = c[6];
        }
      }
      return out;
    },
  });

  /** sketchy box: four strokes that overshoot the corners */
  SK.sketchRect = function (x, y, w, h, o = {}) {
    const e = o.over ?? 7, s = o.seed ?? 1, p = o.p ?? 1;
    const seg = [[x - e, y, x + w + e, y], [x + w, y - e, x + w, y + h + e], [x + w + e, y + h, x - e, y + h], [x, y + h + e, x, y - e]];
    seg.forEach((g, i) => SK.ink(S.line(...g, (rnd(s * 9 + i) - .5) * 4), { ...o, seed: s + i, p: clamp(p * 4 - i) }));
  };

  /* ------------------------------------------------------------ text: per-character write-on with boil */
  /**
   * o: size, font, wt, col, p (write-on 0..1), align (center|left|right), ls, seed, wob, stroke, strokeCol,
   *    mode: 'pop' (hand-written overshoot), 'rise' (each letter fades up), 'type' (typewriter; caret: true)
   */
  SK.txt = function (str, x, y, o = {}) {
    const size = o.size ?? 60, font = o.font ?? SK.FONT_HAND, wt = o.wt ?? 700, p = o.p ?? 1;
    if (p <= 0) return 0;
    ctx.font = `${wt} ${size}px "${font}"`;
    ctx.textBaseline = 'middle';
    const chars = [...str], ls = o.ls ?? 0;
    const ws = chars.map(c => ctx.measureText(c).width + ls);
    const total = ws.reduce((a, b) => a + b, 0) - ls;
    let cx = o.align === 'left' ? x : o.align === 'right' ? x - total : x - total / 2;
    const n = chars.length, k = p * (n + 1.5), seed = o.seed ?? 3, wob = (o.wob ?? 1) * SK.style.textWob;
    const base = ctx.globalAlpha;
    ctx.fillStyle = o.col ?? SK.C.ink;
    const mode = o.mode ?? SK.style.textMode;
    let caretX = null;
    for (let i = 0; i < n; i++) {
      const ri = mode === 'type' ? (k - 1.5 > i ? 1 : 0) : clamp((k - i) / 1.5);
      if (ri > 0) caretX = cx + ws[i];
      if (ri > 0 && chars[i] !== ' ') {
        const r = mulberry(seed * 31 + i * 17 + (SK.style.boil ? SK.BOIL : 0) * 7);
        let rot = (r() - .5) * .07 * wob, dy = (r() - .5) * 3.2 * wob, sc = .45 + .55 * E.back(ri), al = clamp(ri * 2);
        if (mode === 'rise') { sc = 1; dy += (1 - E.out(ri)) * size * .32; al = E.out(ri); }
        else if (mode === 'type') { sc = 1; al = 1; }
        ctx.save(); ctx.translate(cx + ws[i] / 2, y + dy); ctx.rotate(rot); ctx.scale(sc, sc);
        ctx.globalAlpha = base * al;
        if (o.stroke) { ctx.lineWidth = o.stroke; ctx.strokeStyle = o.strokeCol ?? SK.C.ink; ctx.lineJoin = 'round'; ctx.strokeText(chars[i], -ws[i] / 2 + ls / 2, 0); }
        ctx.fillText(chars[i], -ws[i] / 2 + ls / 2, 0);
        ctx.restore();
      }
      cx += ws[i];
    }
    if (mode === 'type' && o.caret && p < 1.02 && Math.floor(SK.T * 2.4) % 2 === 0) {
      ctx.fillStyle = o.caretCol ?? o.col ?? SK.C.ink;
      const x0 = caretX ?? (o.align === 'left' ? x : o.align === 'right' ? x - total : x - total / 2);
      ctx.fillRect(x0 + 2, y - size * .42, Math.max(2, size * .06), size * .84);
    }
    ctx.globalAlpha = base;
    return total;
  };

  /* ------------------------------------------------------------ crisp UI pieces for the clean style */
  function rrPath(x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  SK.rrPath = (x, y, w, h, r) => rrPath(x, y, w, h, r);
  /**
   * A rounded card with a soft drop shadow (x, y = top-left). o: r, fill, stroke, strokeW, shadow
   * ({blur, y, col} or false), alpha, clip (fn drawn clipped to the card)
   */
  SK.card = function (x, y, w, h, o = {}) {
    const a = o.alpha ?? 1; if (a <= 0 || w <= 0 || h <= 0) return;
    const r = o.r ?? 18, sh = o.shadow === false ? null : { blur: 34, y: 14, col: 'rgba(16,23,32,.13)', ...(o.shadow || {}) };
    ctx.save(); ctx.globalAlpha *= a;
    if (sh) { ctx.shadowColor = sh.col; ctx.shadowBlur = sh.blur; ctx.shadowOffsetY = sh.y; }
    rrPath(x, y, w, h, r); ctx.fillStyle = o.fill ?? '#ffffff'; ctx.fill();
    ctx.shadowColor = 'transparent';
    if (o.stroke) { ctx.lineWidth = o.strokeW ?? 2; ctx.strokeStyle = o.stroke; ctx.stroke(); }
    if (o.clip) { rrPath(x, y, w, h, r); ctx.clip(); o.clip(); }
    ctx.restore();
  };
  /** a filled circle with a check that draws itself (p 0..1) */
  SK.check = function (x, y, r, p = 1, o = {}) {
    if (p <= 0) return;
    const s = E.back(clamp(p * 1.6));
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.fillStyle = o.fill ?? SK.C.green; ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.fill();
    const q = clamp(p * 1.6 - .5);
    if (q > 0) {
      ctx.strokeStyle = o.col ?? '#fff'; ctx.lineWidth = r * .22; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      const pts = [[-r * .42, r * .02], [-r * .12, r * .32], [r * .45, -r * .3]];
      const L1 = Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]), L2 = Math.hypot(pts[2][0] - pts[1][0], pts[2][1] - pts[1][1]);
      const d = q * (L1 + L2);
      ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]);
      if (d <= L1) ctx.lineTo(lerp(pts[0][0], pts[1][0], d / L1), lerp(pts[0][1], pts[1][1], d / L1));
      else { ctx.lineTo(pts[1][0], pts[1][1]); const u = (d - L1) / L2; ctx.lineTo(lerp(pts[1][0], pts[2][0], u), lerp(pts[1][1], pts[2][1], u)); }
      ctx.stroke();
    }
    ctx.restore();
  };

  /* ------------------------------------------------------------ small marks every film uses */
  /** an 8-ray starburst (a generic "spark"); o: col, p, rot, w */
  SK.spark = function (x, y, r, o = {}) {
    const n = o.rays ?? 8, col = o.col ?? SK.C.orange, p = o.p ?? 1, rot = o.rot ?? 0;
    for (let i = 0; i < n; i++) {
      const a = rot + i / n * TAU + (rnd(i + 5) - .5) * .18, L = r * (.72 + .28 * rnd(i * 3 + 1));
      SK.ink(S.line(x + Math.cos(a) * r * .12, y + Math.sin(a) * r * .12, x + Math.cos(a) * L, y + Math.sin(a) * L), { w: o.w ?? r * .2, col, seed: 400 + i, p: clamp(p * 1.6 - i * .08), dbl: false, taper: false, jit: .8 });
    }
  };
  SK.heart = function (x, y, s, o = {}) {
    const pts = S.path([['M', 0, 30], ['C', -10, 20, -52, -2, -48, -28], ['C', -44, -54, -10, -54, 0, -26], ['C', 10, -54, 44, -54, 48, -28], ['C', 52, -2, 10, 20, 0, 30]]);
    ctx.save(); ctx.translate(x, y); ctx.rotate(o.rot ?? 0); ctx.scale(s, s);
    const base = ctx.globalAlpha; ctx.globalAlpha = base * (o.alpha ?? 1);
    SK.wash(pts, o.col ?? SK.C.heart, { seed: o.seed ?? 5, dx: 3, dy: 3 });
    SK.ink(pts, { w: 4.5 / Math.max(.4, s) * .9, seed: (o.seed ?? 5) + 1, p: o.p ?? 1 });
    SK.ink(S.arc(-24, -26, 13, 3.6, 4.6), { w: 3 / Math.max(.4, s), col: 'rgba(255,255,255,.8)', dbl: false });
    ctx.globalAlpha = base; ctx.restore();
  };
  /** a cartoon cloud of smoke / poof, alpha a */
  SK.puff = function (x, y, r, a, seed = 1, col = '#ffffff') {
    if (a <= 0) return;
    const base = ctx.globalAlpha; ctx.globalAlpha = base * a;
    for (let i = 0; i < 5; i++) {
      const ang = i / 5 * TAU + seed, rr = r * (.55 + .25 * rnd(seed * 7 + i));
      const px = x + Math.cos(ang) * r * .45, py = y + Math.sin(ang) * r * .35;
      SK.wash(S.ellC(px, py, rr, rr * .9), col, { seed: seed + i, dx: 0, dy: 0, tex: false });
      SK.ink(S.ell(px, py, rr, rr * .9, ang + 1, .1), { w: 3.2, seed: seed * 3 + i, alpha: .8 });
    }
    ctx.globalAlpha = base;
  };
  SK.sparkle = function (x, y, r, a = 1, seed = 1, col) {
    if (a <= 0 || r <= 0) return;
    col = col ?? SK.C.orange;
    const base = ctx.globalAlpha; ctx.globalAlpha = base * a;
    SK.ink(S.line(x - r, y, x + r, y), { w: 4, col, seed, dbl: false });
    SK.ink(S.line(x, y - r, x, y + r), { w: 4, col, seed: seed + 1, dbl: false });
    ctx.globalAlpha = base;
  };
  /** dashed line along a point list; o: on, off (in points), w, col, alpha */
  SK.dashes = function (pts, o = {}) {
    const on = o.on ?? 4, off = o.off ?? 4;
    for (let i = 0; i + on < pts.length; i += on + off) SK.ink(pts.slice(i, i + on + 1), { w: o.w ?? 4, col: o.col ?? SK.C.ink, seed: i + (o.seed ?? 0), dbl: false, alpha: o.alpha ?? 1, taper: false });
  };
  /** run fn with the context faded by a */
  SK.alpha = function (a, fn) { if (a <= 0) return; const b = ctx.globalAlpha; ctx.globalAlpha = b * a; try { fn(); } finally { ctx.globalAlpha = b; } };
  /** run fn in a local frame: translate, rotate, scale (s or [sx, sy]) */
  SK.at = function (x, y, rot, s, fn) {
    ctx.save(); ctx.translate(x, y); if (rot) ctx.rotate(rot);
    if (s !== undefined && s !== 1) Array.isArray(s) ? ctx.scale(s[0], s[1]) : ctx.scale(s, s);
    try { fn(); } finally { ctx.restore(); }
  };
  SK.ctx = () => ctx;
  /* ------------------------------------------------------------ the voice-over clock (sketch-vo's timeline, injected by the bundler)
     Cue visuals to words, not to hand-copied seconds, so a re-recorded line moves its visuals with it. */
  SK.VO = SK.VO || { lines: [] };
  const norm = s => String(s).toLowerCase().replace(/[^a-z0-9$]/g, '');
  /** start (or end, with edge 'e') of word `w` (index or text; n-th match) in VO line `li` */
  SK.w = function (li, w, fallback = 0, edge = 's', n = 0) {
    const L = SK.VO.lines[li]; if (!L) return fallback;
    if (typeof w === 'number') return L.words[w] ? L.words[w][edge] : fallback;
    const hits = L.words.filter(x => norm(x.text) === norm(w));
    return hits[n] ? hits[n][edge] : fallback;
  };
  SK.line = (li) => SK.VO.lines[li] || { start: 0, end: 0, words: [] };
  /** images the manifest inlines ("images": {"logo": "assets/logo.png"}); loaded by the player */
  SK.IMG = SK.IMG || {};
  /** draw a loaded image; w or h may be omitted to keep the aspect. o: alpha, align ('center'|'left') */
  SK.image = function (name, x, y, w, h, o = {}) {
    const im = SK.IMG[name]; if (!im) return;
    if (!h) h = w * im.height / im.width; if (!w) w = h * im.width / im.height;
    const a = o.alpha ?? 1; if (a <= 0) return;
    const b = ctx.globalAlpha; ctx.globalAlpha = b * a;
    ctx.drawImage(im, o.align === 'left' ? x : x - w / 2, y - h / 2, w, h);
    ctx.globalAlpha = b;
  };

  /* ------------------------------------------------------------ paths: Catmull-Rom through timed waypoints */
  function cr(p0, p1, p2, p3, u) {
    const u2 = u * u, u3 = u2 * u;
    return [.5 * (2 * p1[0] + (-p0[0] + p2[0]) * u + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * u2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * u3),
    .5 * (2 * p1[1] + (-p0[1] + p2[1]) * u + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * u2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * u3)];
  }
  /**
   * SK.flightPath(points, sections) -> { ts, pos(t), angle(t), pts(t0, t1, step) }
   * sections: [[firstIndex, lastIndex, tStart, tEnd], ...] -- inside a section the waypoints
   * are timed by chord length, so speed is even; sections let a path slow down (e.g. through
   * a window) without hand-timing every point.
   */
  SK.flightPath = function (P, sections) {
    const seg = []; for (let i = 1; i < P.length; i++) seg.push(Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]));
    const ts = new Array(P.length).fill(0);
    for (const [a, b, t0, t1] of sections) {
      let tot = 0; for (let i = a; i < b; i++) tot += seg[i];
      let acc = 0; ts[a] = t0;
      for (let i = a; i < b; i++) { acc += seg[i]; ts[i + 1] = t0 + (t1 - t0) * acc / tot; }
    }
    const pos = (t) => {
      t = clamp(t, ts[0], ts[ts.length - 1]);
      let i = 0; while (i < ts.length - 2 && t > ts[i + 1]) i++;
      const u = (t - ts[i]) / (ts[i + 1] - ts[i]);
      return cr(P[Math.max(0, i - 1)], P[i], P[i + 1], P[Math.min(P.length - 1, i + 2)], u);
    };
    const angle = (t) => { const a = pos(t), b = pos(Math.min(ts[ts.length - 1], t + .02)); return Math.atan2(b[1] - a[1], b[0] - a[0]); };
    const pts = (t0, t1, step = .012) => { const out = []; for (let t = t0; t <= t1; t += step) out.push(pos(t)); return out; };
    return { ts, pos, angle, pts, t0: ts[0], t1: ts[ts.length - 1] };
  };

  /* ------------------------------------------------------------ camera */
  /**
   * SK.camera(keys, shakes) -- keys: [[t, [x, y, zoom], ease?], ...] in world units;
   * zoom interpolates in log space so pushes and pulls feel even.
   * shakes: [{t, w, amp, from?}] gaussian bumps (a stamp, a launch).
   */
  SK.camera = function (keys, shakes = []) {
    const at = (t) => {
      if (t <= keys[0][0]) return keys[0][1].slice();
      for (let i = 1; i < keys.length; i++) {
        if (t <= keys[i][0]) {
          const [t0, a] = keys[i - 1], [t1, b, e] = keys[i];
          const u = (e || E.inOut)((t - t0) / (t1 - t0));
          const z = Math.exp(lerp(Math.log(a[2]), Math.log(b[2]), u));
          const wa = 1 / a[2], wb = 1 / b[2];
          const uu = Math.abs(wb - wa) < 1e-6 ? u : clamp((lerp(wa, wb, u) - wa) / (wb - wa));
          return [lerp(a[0], b[0], uu), lerp(a[1], b[1], uu), z];
        }
      }
      return keys[keys.length - 1][1].slice();
    };
    const shake = (t) => shakes.reduce((s, k) => s + (k.from !== undefined && t < k.from ? 0 : Math.exp(-Math.pow((t - k.t) / k.w, 2)) * k.amp), 0);
    return { at, shake, keys };
  };

  /* ------------------------------------------------------------ paper, grain, speed lines */
  let PAPER = null; const GRAIN = [];
  SK.makeTextures = function () {
    const pc = document.createElement('canvas'); pc.width = pc.height = 1024;
    const g = pc.getContext('2d');
    g.fillStyle = SK.C.paper; g.fillRect(0, 0, 1024, 1024);
    const r = mulberry(42);
    for (let i = 0; i < 70; i++) { // soft mottling, kept faint: it reads as dirt when strong
      const x = r() * 1024, y = r() * 1024, rad = 80 + r() * 160;
      const gr = g.createRadialGradient(x, y, 0, x, y, rad);
      const dark = r() < .5;
      gr.addColorStop(0, dark ? 'rgba(160,130,90,0.016)' : 'rgba(255,255,255,0.05)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = gr;
      for (const dx of [-1024, 0, 1024]) for (const dy of [-1024, 0, 1024]) { g.save(); g.translate(dx, dy); g.fillRect(x - rad, y - rad, rad * 2, rad * 2); g.restore(); }
    }
    for (let i = 0; i < 26000; i++) { const x = r() * 1024, y = r() * 1024; g.fillStyle = r() < .5 ? `rgba(90,70,40,${.03 + r() * .05})` : `rgba(255,255,255,${.05 + r() * .08})`; g.fillRect(x, y, 1 + r() * 1.5, 1 + r() * 1.5); }
    g.lineCap = 'round';
    for (let i = 0; i < 260; i++) {
      const x = r() * 1024, y = r() * 1024, a = r() * TAU, l = 6 + r() * 22;
      g.strokeStyle = `rgba(120,95,60,${.05 + r() * .06})`; g.lineWidth = .8; g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x + Math.cos(a + .5) * l * .5, y + Math.sin(a + .5) * l * .5, x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke();
    }
    PAPER = ctx.createPattern(pc, 'repeat');
    GRAIN.length = 0;
    for (let k = 0; k < 4; k++) {
      const gc = document.createElement('canvas'); gc.width = gc.height = 256; const gg = gc.getContext('2d');
      const img = gg.createImageData(256, 256), rr = mulberry(1000 + k);
      for (let i = 0; i < img.data.length; i += 4) { const v = rr() * 255; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 12; }
      gg.putImageData(img, 0, 0); GRAIN.push(ctx.createPattern(gc, 'repeat'));
    }
  };
  function speedLines(cam, t) {
    const a = cam.at(t), b = cam.at(t - 1 / 60);
    const vx = (a[0] - b[0]) * a[2] * 60, vy = (a[1] - b[1]) * a[2] * 60, vz = Math.abs(Math.log(a[2] / b[2])) * 60;
    const sp = Math.hypot(vx, vy) + vz * 900;
    const k = clamp((sp - 2600) / 6000);
    if (k <= 0) return;
    const ang = Math.atan2(vy, vx) + (vz * 900 > Math.hypot(vx, vy) ? Math.PI / 2 : 0);
    ctx.save(); ctx.globalAlpha = k * .55;
    const r = mulberry(SK.BOIL * 3 + 5);
    for (let i = 0; i < 14; i++) {
      const cx = r() * W, cy = r() * H, L = 180 + r() * 380;
      SK.ink(S.line(cx - Math.cos(ang) * L / 2, cy - Math.sin(ang) * L / 2, cx + Math.cos(ang) * L / 2, cy + Math.sin(ang) * L / 2), { w: 3 + r() * 3, col: SK.C.inkSoft, seed: 2000 + i, dbl: false });
    }
    ctx.restore();
  }

  /* ------------------------------------------------------------ the film */
  /**
   * SK.film({ duration, camera, draw(t, vis), fadeIn = 0, fadeOut = .45, speedLines = true,
   *           handheld = true, automation: { name: { t0, t1, pos(t) } } })
   * draw() runs in world space; vis(x0, y0, x1, y1) says whether a box is on screen.
   */
  SK.film = function (def) { SK._film = def; };
  SK.init = function (canvas) { canvas.width = W; canvas.height = H; ctx = canvas.getContext('2d'); };

  SK.render = function (t) {
    const F = SK._film;
    SK.T = t; SK.BOIL = Math.floor(t * SK.BOIL_FPS);
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
    const [cx, cy, z] = F.camera.at(t);
    const sh = F.camera.shake(t), hh = F.handheld === false ? 0 : SK.style.handheld;
    const hx = hh * (Math.sin(t * .7) * 4 + Math.sin(t * 1.9) * 2) + (rnd(SK.BOIL * 5 + 1) - .5) * sh * 2;
    const hy = hh * (Math.cos(t * .6) * 3 + Math.sin(t * 2.3) * 1.5) + (rnd(SK.BOIL * 5 + 2) - .5) * sh * 2;
    const rot = hh * Math.sin(t * .45) * .0025;
    // paper: screen space so a wide shot never balloons its grain, but it slides with the camera
    const ox = ((-(cx * z) + hx) % 1024 + 1024) % 1024, oy = ((-(cy * z) + hy) % 1024 + 1024) % 1024;
    if (SK.style.paper === 'flat') { ctx.fillStyle = SK.C.paper; ctx.fillRect(0, 0, W, H); }
    else { PAPER.setTransform(new DOMMatrix([1, 0, 0, 1, ox, oy])); ctx.fillStyle = PAPER; ctx.fillRect(0, 0, W, H); }
    ctx.translate(W / 2 + hx, H / 2 + hy); ctx.rotate(rot); ctx.scale(z, z); ctx.translate(-cx, -cy);
    const vw = W / z + 200, vh = H / z + 200;
    const view = { x0: cx - vw / 2, x1: cx + vw / 2, y0: cy - vh / 2, y1: cy + vh / 2 };
    const vis = (x0, y0, x1, y1) => x1 > view.x0 && x0 < view.x1 && y1 > view.y0 && y0 < view.y1;
    const G = SK.style.grid;
    if (G) { // a faint drafting grid in world space
      const st = G.step ?? 80; ctx.save(); ctx.strokeStyle = G.col ?? 'rgba(26,86,219,.07)'; ctx.lineWidth = (G.w ?? 1.2) / z; ctx.beginPath();
      for (let gx = Math.floor(view.x0 / st) * st; gx < view.x1; gx += st) { ctx.moveTo(gx, view.y0); ctx.lineTo(gx, view.y1); }
      for (let gy = Math.floor(view.y0 / st) * st; gy < view.y1; gy += st) { ctx.moveTo(view.x0, gy); ctx.lineTo(view.x1, gy); }
      ctx.stroke(); ctx.restore();
    }
    F.draw(t, vis);
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
    if (F.speedLines !== false) speedLines(F.camera, t);
    if (F.overlay) F.overlay(t);
    const gb = Math.floor(t * 8);
    if (SK.style.grain > 0) { ctx.globalAlpha = SK.style.grain; ctx.fillStyle = GRAIN[gb % 4]; ctx.save(); ctx.translate((gb * 37) % 256, (gb * 71) % 256); ctx.fillRect(-256, -256, W + 512, H + 512); ctx.restore(); ctx.globalAlpha = 1; }
    const vg = ctx.createRadialGradient(W / 2, H / 2, H * .45, W / 2, H / 2, H * 1.05);
    vg.addColorStop(0, 'rgba(60,40,20,0)'); vg.addColorStop(1, `rgba(${SK.style.vignetteRGB ?? '60,40,20'},${SK.style.vignette})`);
    ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
    // no fade-in by default: a fade from blank paper reads as empty frames at the head of the film
    const fin = F.fadeIn ? 1 - tw(t, 0, F.fadeIn) : 0, fout = tw(t, F.duration - (F.fadeOut ?? .45), F.duration);
    if (fin > 0 || fout > 0) { ctx.fillStyle = SK.C.paper; ctx.globalAlpha = Math.max(fin, fout); ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
  };

  /** Per-track motion for the sound design: speed (screen px/s) and pan (-1..1) of a moving thing. */
  SK.automation = function (step = .01) {
    const F = SK._film, out = {};
    for (const [name, tr] of Object.entries(F.automation || {})) {
      const t = [], speed = [], pan = [];
      for (let x = tr.t0; x <= tr.t1; x += step) {
        const a = tr.pos(x), b = tr.pos(Math.min(tr.t1, x + step)), c = F.camera.at(x);
        t.push(+x.toFixed(4)); speed.push(Math.hypot(b[0] - a[0], b[1] - a[1]) / step * c[2] + 1); pan.push(clamp(((a[0] - c[0]) * c[2]) / (W / 2), -1, 1));
      }
      out[name] = { t, speed, pan };
    }
    return out;
  };
})();
