/* sketch/drink.js -- a drink made on camera: a glass, a pour, ice and garnish (needs gl3d.js).

   "modules": ["gl3d", "drink"], then in film.js:

       const glass = SK.drink.glass({ pour: {...}, drops: [...], rimLime: {...} });
       SK.film({ ..., draw(t) { glass.draw(t); }, sounds: () => glass.sounds() });

   Defaults are the KitCut mojito: a hurricane glass, a pale lime-green pour, ice, mint, lime,
   two paper straws and a lime wheel on the rim.

   What is simulated (baked forward from t = 0 in fixed steps, one snapshot a frame, so every
   frame is a pure function of t -- the rule sketch films keep):
     * the LEVEL -- exactly the volume poured plus what the floating things displace, read off
       the glass's own inner profile (a hurricane glass fills fast at the belly, slow at the waist);
     * the SURFACE -- a wave equation on a grid over the glass's cross-section, reflecting off the
       wall, disturbed by the stream landing and by everything that goes in or bobs;
     * the POUR -- a ballistic stream of blobs, drawn as one tube that thins as it speeds up;
     * ICE, MINT, LIME, STRAWS -- rigid bodies as clusters of spheres held by shape matching
       (Mueller 2005), colliding with the glass's inner and outer walls, its rim and each other,
       buoyed per sphere by how far under the surface it is (ice at 0.92 floats high, lime at 1.04
       sinks, a leaf lies on top);
     * SPLASH DROPLETS thrown when something enters fast, and SODA BUBBLES rising from the
       bottom and off the ice.
   The lime wheel on the rim is placed, not simulated (a slit fitting a rim is a hand's job).

   Light: floor and shadows; the far wall of the glass; the ice (refracting the floor) and the
   other inclusions; the liquid, which reads all of that THROUGH itself (thickness from its own
   back faces, absorption, a little haze); then the near wall of the glass reading the liquid
   through ITS thickness -- thin walls barely bend the picture, the stem and foot bend it a lot.
*/
(function () {
  'use strict';
  const root = typeof window !== 'undefined' ? window : globalThis;
  const SK = (root.SK = root.SK || {});
  const D = (SK.drink = {});
  const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
  const smooth = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };
  function mulberry(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const qmul = (a, b) => [
    a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1], a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
    a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3], a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
  const qnorm = (q) => { const l = Math.hypot(q[0], q[1], q[2], q[3]) || 1; return [q[0] / l, q[1] / l, q[2] / l, q[3] / l]; };
  const qaxis = (ax, ang) => { const l = Math.hypot(...ax) || 1, s = Math.sin(ang / 2); return [(ax[0] / l) * s, (ax[1] / l) * s, (ax[2] / l) * s, Math.cos(ang / 2)]; };
  const qrot = (q, v) => { // v rotated by q
    const [x, y, z, w] = q, ix = w * v[0] + y * v[2] - z * v[1], iy = w * v[1] + z * v[0] - x * v[2], iz = w * v[2] + x * v[1] - y * v[0], iw = -x * v[0] - y * v[1] - z * v[2];
    return [ix * w + iw * -x + iy * -z - iz * -y, iy * w + iw * -y + iz * -x - ix * -z, iz * w + iw * -z + ix * -y - iy * -x];
  };
  const qmat3 = (q) => { const [x, y, z, w] = q; return [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y), 2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x), 2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]; };

  /* ------------------------------------------------------------ the glass: a hurricane, by profile
     [r, y] control points (world units: 1 = 10 cm; the floor is y = 0), splined. */
  D.GLASSES = {
    hurricane: {
      foot: [[0, 0], [0.4, 0], [0.425, 0.012], [0.42, 0.03], [0.3, 0.046], [0.13, 0.085], [0.068, 0.13]],
      outer: [[0.068, 0.13], [0.056, 0.2], [0.066, 0.27], [0.055, 0.34], [0.06, 0.4], [0.09, 0.45], [0.17, 0.51], [0.27, 0.6], [0.34, 0.72], [0.372, 0.86], [0.362, 1.0], [0.322, 1.16], [0.3, 1.3], [0.315, 1.45], [0.355, 1.6], [0.4, 1.745]],
      inner: [[0, 0.555], [0.08, 0.561], [0.16, 0.588], [0.245, 0.64], [0.316, 0.72], [0.357, 0.86], [0.348, 1.0], [0.308, 1.16], [0.286, 1.3], [0.301, 1.45], [0.341, 1.6], [0.386, 1.745]],
    },
  };
  function catmull(pts, per) {
    const out = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
      for (let k = 0; k < per; k++) {
        const t = k / per, t2 = t * t, t3 = t2 * t;
        out.push([0, 1].map((c) => 0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2 + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3)));
      }
    }
    out.push(pts[pts.length - 1].slice());
    return out;
  }
  function buildGlass(def) {
    const outer = catmull(def.outer, 10), inner = catmull(def.inner, 10);
    const rimY = outer[outer.length - 1][1], ro = outer[outer.length - 1][0], ri = inner[inner.length - 1][0];
    const rimR = (ro + ri) / 2, rimT = (ro - ri) / 2;
    const rim = [];
    for (let k = 1; k < 8; k++) { const a = (k / 8) * Math.PI; rim.push([rimR + Math.cos(a) * rimT, rimY + Math.sin(a) * rimT]); }
    // the solid, walked so its outside is on the right: along the underside, up the foot and stem,
    // up the outer wall, over the rim, down the inner wall, along the cavity floor to the axis
    const solid = [...catmull(def.foot, 4), ...outer.slice(1), ...rim, ...inner.slice().reverse()];
    const yb = inner[0][1];
    // the cavity: r_in(y) and the volume below y, tabulated
    const rIn = (y) => {
      if (y <= yb) return 0;
      for (let i = 1; i < inner.length; i++) if (inner[i][1] >= y) { const a = inner[i - 1], b = inner[i], u = (y - a[1]) / Math.max(1e-9, b[1] - a[1]); return a[0] + (b[0] - a[0]) * u; }
      return ri;
    };
    const dy = 0.001, vol = [0];
    for (let y = yb; y < rimY; y += dy) vol.push(vol[vol.length - 1] + Math.PI * rIn(y + dy / 2) ** 2 * dy);
    const volumeAt = (y) => { const f = (y - yb) / dy; if (f <= 0) return 0; const i = Math.min(vol.length - 2, Math.floor(f)); return vol[i] + (vol[i + 1] - vol[i]) * (f - i); };
    const levelOf = (V) => {
      if (V <= 0) return yb;
      let lo = 0, hi = vol.length - 1;
      if (V >= vol[hi]) return rimY;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (vol[mid] < V) lo = mid; else hi = mid; }
      return yb + (lo + (V - vol[lo]) / Math.max(1e-12, vol[hi] - vol[lo])) * dy;
    };
    // arc length along the inner profile, for resampling the liquid's side
    const s = [0];
    for (let i = 1; i < inner.length; i++) s.push(s[i - 1] + Math.hypot(inner[i][0] - inner[i - 1][0], inner[i][1] - inner[i - 1][1]));
    return { outer, inner, solid, rim: { y: rimY, r: rimR, t: rimT }, yb, rIn, volumeAt, levelOf, innerS: s, wall: ro - ri, rMax: Math.max(...inner.map((p) => p[0])) };
  }
  /** closest point on a 2D polyline: [distance, nx, ny] with n pointing from the line to p */
  function nearest(poly, pr, py) {
    let best = Infinity, bx = 0, by = 0;
    for (let i = 0; i < poly.length - 1; i++) {
      const ax = poly[i][0], ay = poly[i][1], ex = poly[i + 1][0] - ax, ey = poly[i + 1][1] - ay;
      const u = clamp(((pr - ax) * ex + (py - ay) * ey) / Math.max(1e-12, ex * ex + ey * ey));
      const qx = ax + ex * u, qy = ay + ey * u, d = (pr - qx) ** 2 + (py - qy) ** 2;
      if (d < best) { best = d; bx = qx; by = qy; }
    }
    const d = Math.sqrt(best);
    return [d, d > 1e-9 ? (pr - bx) / d : 0, d > 1e-9 ? (py - by) / d : 1];
  }

  /* ------------------------------------------------------------ what goes in: meshes + sphere clusters
     Each kind gives a mesh around its centre of mass, its spheres ([x, y, z] rest offsets, one
     radius), a density (water = 1) and a volume. aAttr carries a material hint per vertex. */
  function roundedCube(size, round, n, rnd) {
    const a = size / 2, pos = [], tri = [], attr = [];
    const faces = [[0, 1, 2, 1], [0, 1, 2, -1], [1, 2, 0, 1], [1, 2, 0, -1], [2, 0, 1, 1], [2, 0, 1, -1]];
    const jitter = [rnd() * 6, rnd() * 6, rnd() * 6];
    for (const [ax, u, v, sgn] of faces) {
      const base = pos.length / 3;
      for (let i = 0; i <= n; i++) for (let j = 0; j <= n; j++) {
        const p = [0, 0, 0];
        p[ax] = a * sgn; p[u] = -a + (2 * a * i) / n; p[v] = -a + (2 * a * j) / n;
        const c = p.map((x) => clamp(x, -(a - round), a - round)), d = p.map((x, k) => x - c[k]), l = Math.hypot(...d) || 1;
        const w = 1 + 0.035 * Math.sin(p[0] * 31 + jitter[0]) * Math.sin(p[1] * 27 + jitter[1]) + 0.025 * Math.sin(p[2] * 43 + jitter[2]);
        pos.push(...c.map((x, k) => (x + (d[k] / l) * round) * w));
        attr.push(0);
      }
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        const q = base + i * (n + 1) + j;
        if (sgn > 0) tri.push(q, q + n + 1, q + 1, q + 1, q + n + 1, q + n + 2);
        else tri.push(q, q + 1, q + n + 1, q + 1, q + n + 2, q + n + 1);
      }
    }
    return orient({ pos: new Float32Array(pos), tri: new Uint32Array(tri), attr: new Float32Array(attr) });
  }
  function leaf(len, wid) {
    const pos = [], tri = [], attr = [], NU = 18, NV = 6;
    for (let i = 0; i <= NU; i++) {
      const u = i / NU, w = wid * Math.pow(Math.sin(Math.PI * Math.pow(u, 0.8)), 0.9) * (1 + 0.07 * Math.sin(u * 44));
      for (let j = 0; j <= NV; j++) {
        const v = (j / NV) * 2 - 1;
        const x = (u - 0.5) * len, z = v * w, y = Math.abs(v) * w * 0.35 + Math.sin(Math.PI * u) * len * 0.12;
        pos.push(x, y, z); attr.push(Math.abs(v));
      }
    }
    for (let i = 0; i < NU; i++) for (let j = 0; j < NV; j++) { const q = i * (NV + 1) + j; tri.push(q, q + NV + 1, q + 1, q + 1, q + NV + 1, q + NV + 2); }
    return { pos: new Float32Array(pos), tri: new Uint32Array(tri), attr: new Float32Array(attr), twoSided: true };
  }
  /** a disc (a lime wheel), axis along y; attr: 0 on the cut faces, 1 on the rind. slit: a gap in radians */
  function wheel(r, th, slit = 0) {
    const pos = [], tri = [], attr = [], S = 48, R = 8;
    const a0 = slit / 2, span = Math.PI * 2 - slit;
    const ang = (s) => a0 + (span * s) / S;
    for (const side of [1, -1]) { // the two cut faces
      const base = pos.length / 3;
      for (let k = 0; k <= R; k++) for (let s = 0; s <= S; s++) { const rr = (r * k) / R, a = ang(s); pos.push(Math.cos(a) * rr, (side * th) / 2, Math.sin(a) * rr); attr.push(0); }
      for (let k = 0; k < R; k++) for (let s = 0; s < S; s++) {
        const q = base + k * (S + 1) + s;
        if (side > 0) tri.push(q, q + 1, q + S + 1, q + 1, q + S + 2, q + S + 1); else tri.push(q, q + S + 1, q + 1, q + 1, q + S + 1, q + S + 2);
      }
    }
    const base = pos.length / 3; // the rind
    for (let s = 0; s <= S; s++) for (const y of [th / 2, -th / 2]) { const a = ang(s); pos.push(Math.cos(a) * r, y, Math.sin(a) * r); attr.push(1); }
    for (let s = 0; s < S; s++) { const q = base + s * 2; tri.push(q, q + 2, q + 1, q + 1, q + 2, q + 3); }
    return orient({ pos: new Float32Array(pos), tri: new Uint32Array(tri), attr: new Float32Array(attr), twoSided: slit > 0 });
  }
  /** a straw along y, centred; attr: 0 the paper, 1 the dark inside at the ends */
  function straw(r, len) {
    const pos = [], tri = [], attr = [], S = 16, L = 40;
    for (let i = 0; i <= L; i++) for (let s = 0; s <= S; s++) { const a = (s / S) * Math.PI * 2, y = -len / 2 + (len * i) / L; pos.push(Math.cos(a) * r, y, Math.sin(a) * r); attr.push(0); }
    for (let i = 0; i < L; i++) for (let s = 0; s < S; s++) { const q = i * (S + 1) + s; tri.push(q, q + 1, q + S + 1, q + 1, q + S + 2, q + S + 1); }
    for (const end of [1, -1]) { // dark discs just inside each end: the hollow
      const c = pos.length / 3; pos.push(0, (end * len) / 2 - end * 0.004, 0); attr.push(1);
      for (let s = 0; s <= S; s++) { const a = (s / S) * Math.PI * 2; pos.push(Math.cos(a) * r * 0.85, (end * len) / 2 - end * 0.004, Math.sin(a) * r * 0.85); attr.push(1); }
      for (let s = 0; s < S; s++) end > 0 ? tri.push(c, c + s + 2, c + s + 1) : tri.push(c, c + s + 1, c + s + 2);
    }
    return orient({ pos: new Float32Array(pos), tri: new Uint32Array(tri), attr: new Float32Array(attr) });
  }
  /** make a closed mesh's triangles face out (checked on its biggest triangle against its centre) */
  function orient(m) {
    let best = 0, bi = 0;
    const c = [0, 0, 0], n = m.pos.length / 3;
    for (let i = 0; i < n; i++) { c[0] += m.pos[i * 3] / n; c[1] += m.pos[i * 3 + 1] / n; c[2] += m.pos[i * 3 + 2] / n; }
    for (let q = 0; q < m.tri.length; q += 3) {
      const a = m.tri[q] * 3, b = m.tri[q + 1] * 3, cc = m.tri[q + 2] * 3;
      const u = [m.pos[b] - m.pos[a], m.pos[b + 1] - m.pos[a + 1], m.pos[b + 2] - m.pos[a + 2]], v = [m.pos[cc] - m.pos[a], m.pos[cc + 1] - m.pos[a + 1], m.pos[cc + 2] - m.pos[a + 2]];
      const ar = Math.hypot(...cross(u, v));
      if (ar > best) { best = ar; bi = q; }
    }
    const a = m.tri[bi] * 3, b = m.tri[bi + 1] * 3, cc = m.tri[bi + 2] * 3;
    const nn = cross([m.pos[b] - m.pos[a], m.pos[b + 1] - m.pos[a + 1], m.pos[b + 2] - m.pos[a + 2]], [m.pos[cc] - m.pos[a], m.pos[cc + 1] - m.pos[a + 1], m.pos[cc + 2] - m.pos[a + 2]]);
    const out = [m.pos[a] - c[0], m.pos[a + 1] - c[1], m.pos[a + 2] - c[2]];
    if (nn[0] * out[0] + nn[1] * out[1] + nn[2] * out[2] < 0) for (let q = 0; q < m.tri.length; q += 3) { const t = m.tri[q + 1]; m.tri[q + 1] = m.tri[q + 2]; m.tri[q + 2] = t; }
    return m;
  }
  const KINDS = {
    ice(rnd, o) {
      const s = (o.size || 0.15) * (0.9 + rnd() * 0.2), mesh = roundedCube(s, s * 0.17, 7, rnd), sp = [];
      for (const x of [-1, 0, 1]) for (const y of [-1, 0, 1]) for (const z of [-1, 0, 1]) sp.push([(x * s) / 3, (y * s) / 3, (z * s) / 3]);
      return { mesh, spheres: sp, rp: s * 0.2, density: 0.92, volume: s ** 3 * 0.95, id: 0 };
    },
    mint(rnd, o) {
      const len = (o.size || 0.17) * (0.85 + rnd() * 0.3), mesh = leaf(len, len * 0.27), sp = [];
      for (let k = 0; k < 5; k++) sp.push([(k / 4 - 0.5) * len * 0.8, len * 0.05, 0]);
      sp.push([0, len * 0.05, len * 0.13], [0, len * 0.05, -len * 0.13]);
      return { mesh, spheres: sp, rp: len * 0.1, density: 0.7, volume: len * len * 0.27 * 0.01, id: 1 };
    },
    lime(rnd, o) {
      const r = o.size || 0.11, th = r * 0.25, mesh = wheel(r, th), sp = [[0, 0, 0]];
      for (let k = 0; k < 8; k++) { const a = (k / 8) * Math.PI * 2; sp.push([Math.cos(a) * r * 0.62, 0, Math.sin(a) * r * 0.62]); }
      return { mesh, spheres: sp, rp: th * 0.9, density: 1.04, volume: Math.PI * r * r * th, id: 2 };
    },
    straw(rnd, o) {
      const len = o.length || 1.55, r = o.radius || 0.021, mesh = straw(r, len), sp = [];
      const n = Math.round(len / (r * 2.2));
      for (let k = 0; k < n; k++) sp.push([0, -len / 2 + r + ((len - 2 * r) * k) / (n - 1), 0]);
      return { mesh, spheres: sp, rp: r * 1.05, density: 1.15, volume: Math.PI * r * r * len * 0.3, id: 3 }; // a soaked paper straw sinks
    },
  };

  /* ------------------------------------------------------------ the scene */
  D.DEFAULTS = {
    glass: 'hurricane',
    liquid: { absorb: [0.55, 0.2, 1.45], body: [0.62, 0.78, 0.3], cloud: 0.55 },
    fps: 60, substeps: 8, gravity: 45,
    // the stream leaves `from` and is aimed so it passes through `aim` (vel is solved; vy0 its start)
    pour: { t0: 0.5, t1: 4.0, from: [-0.62, 3.4, 0.08], aim: [0.03, 1.0, 0.0], vy0: -0.3, radius: 0.058, fill: 1.26, rate: 240, wobble: 0.06 },
    drops: [],
    rimLime: null, // { t, angle (deg around the glass), size }
    bubbles: { rate: 26, onIce: 6, max: 260 },
    // couple: how much of what a body displaces goes into the waves at once (the rest is the level)
    waves: { speed: 1.05, damping: 2.0, grid: 72, couple: 0.35, cap: 0.05 },
    drag: [8, 7], // water on a body: linear (1/s) and quadratic (1/unit) -- ice dips and bobs back
    camera: { target: [0, 1.0, 0], dist: 6.2, elev: 17, azim: -8, fov: 28, orbit: 12, push: -0.35, shift: [0, 0.1] }, // high enough to see what floats
    light: { key: [-0.55, 1.0, -0.45], fill: [0.95, 0.35, 0.75], floor: [0.78, 0.78, 0.75], room: [0.86, 0.92] }, // a light tent: glass on white
    seed: 5,
  };
  function merge(a, b) {
    const o = { ...a };
    for (const k of Object.keys(b || {})) o[k] = b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object' && !Array.isArray(a[k]) ? merge(a[k], b[k]) : b[k];
    return o;
  }

  D.glass = function (spec = {}) {
    const o = merge(D.DEFAULTS, spec);
    const GL = buildGlass(typeof o.glass === 'string' ? D.GLASSES[o.glass] : o.glass);
    const g = o.gravity, dt = 1 / (o.fps * o.substeps), rnd = mulberry(o.seed * 7919 + 1);

    // ---- bodies: every drop becomes a body, asleep until its time
    const bodies = [], pos = [], prev = [], vel = [], r0 = [], owner = [], sub = [], side = [];
    o.drops.forEach((d, bi) => {
      const k = KINDS[d.kind](mulberry((o.seed + 1) * 104729 + bi * 31), d);
      // shape matching holds the spheres' mean fixed: centre spheres and mesh on it, or every
      // correction shoves the body by the offset (a leaf flew off at 100 units/s)
      const mc = [0, 1, 2].map((c) => k.spheres.reduce((a, sp) => a + sp[c], 0) / k.spheres.length);
      k.spheres = k.spheres.map((sp) => [sp[0] - mc[0], sp[1] - mc[1], sp[2] - mc[2]]);
      for (let v = 0; v < k.mesh.pos.length; v += 3) { k.mesh.pos[v] -= mc[0]; k.mesh.pos[v + 1] -= mc[1]; k.mesh.pos[v + 2] -= mc[2]; }
      const first = pos.length / 3;
      for (const s of k.spheres) { r0.push(...s); pos.push(0, -10, 0); prev.push(0, -10, 0); vel.push(0, 0, 0); owner.push(bi); sub.push(0); side.push(1); }
      bodies.push({ d, kind: d.kind, ...k, first, count: k.spheres.length, awake: false, q: [0, 0, 0, 1], c: [0, -10, 0], hitT: -1, wet: false });
    });
    const NP = pos.length / 3;
    const X = new Float64Array(pos), Xp = new Float64Array(prev), Vv = new Float64Array(vel), R0 = new Float64Array(r0), Fsub = new Float64Array(sub);
    const Side = new Int8Array(side);
    const events = [];

    function wake(b, t) {
      const d = b.d, br = mulberry(b.first * 97 + 13);
      const tilt = d.tilt !== undefined ? (d.tilt * Math.PI) / 180 : null;
      let q;
      if (b.kind === 'straw') q = qmul(qaxis([Math.cos(d.yaw || 0.6), 0, Math.sin(d.yaw || 0.6)], tilt ?? 0.35), [0, 0, 0, 1]);
      else q = qnorm([br() - 0.5, br() - 0.5, br() - 0.5, br() + 0.3]);
      const at = d.at || [0, 0];
      const c = [at[0], GL.rim.y + (d.height ?? 0.32) + (b.kind === 'straw' ? 0.8 : 0), at[1]];
      const w = [(br() - 0.5) * (d.spin ?? 6), (br() - 0.5) * (d.spin ?? 6), (br() - 0.5) * (d.spin ?? 6)];
      const v0 = d.vel || [0, -0.6, 0];
      for (let i = b.first; i < b.first + b.count; i++) {
        const off = qrot(q, [R0[i * 3], R0[i * 3 + 1], R0[i * 3 + 2]]), wr = cross(w, off);
        for (let k = 0; k < 3; k++) { X[i * 3 + k] = c[k] + off[k]; Xp[i * 3 + k] = X[i * 3 + k]; Vv[i * 3 + k] = v0[k] + wr[k]; }
        Side[i] = 1;
      }
      b.q = q; b.c = c; b.awake = true; b.born = t;
    }

    // ---- the liquid: poured volume, level, the wave grid
    const N = o.waves.grid, Rh = GL.rMax + 0.01, dx = (2 * Rh) / N;
    const H = new Float64Array(N * N), HV = new Float64Array(N * N), mask = new Uint8Array(N * N);
    let Vliq = 0, level = GL.yb;
    const cellOf = (x, z) => [Math.floor((x + Rh) / dx), Math.floor((z + Rh) / dx)];
    const hAt = (x, z) => { // bilinear, 0 outside
      const fx = (x + Rh) / dx - 0.5, fz = (z + Rh) / dx - 0.5, i = Math.floor(fx), j = Math.floor(fz), u = fx - i, v = fz - j;
      const at = (a, b) => (a >= 0 && b >= 0 && a < N && b < N ? H[b * N + a] : 0);
      return at(i, j) * (1 - u) * (1 - v) + at(i + 1, j) * u * (1 - v) + at(i, j + 1) * (1 - u) * v + at(i + 1, j + 1) * u * v;
    };
    const surfaceY = (x, z) => level + hAt(x, z);
    const inCavity = (x, y, z) => y > GL.yb && y < GL.rim.y && Math.hypot(x, z) < GL.rIn(y);
    /** disturb the surface around (x, z): into its velocity (an impact: momentum), or into its
     *  height (a body displacing volume). A displacement put into the velocity keeps pushing every
     *  step until damped -- that was a runaway that sank the ice. Weights sum to 1. */
    function poke(x, z, amount, spread = 1, height = false) {
      const [ci, cj] = cellOf(x, z), A = height ? H : HV;
      const norm = spread ? 1 + 4 / 2 + 4 / 3 : 1;
      for (let dj = -spread; dj <= spread; dj++) for (let di = -spread; di <= spread; di++) {
        const i = ci + di, j = cj + dj;
        if (i < 0 || j < 0 || i >= N || j >= N || !mask[j * N + i]) continue;
        A[j * N + i] += amount / (1 + di * di + dj * dj) / norm;
      }
    }
    function waves(h) {
      const r = GL.rIn(level) - 0.004, c2 = o.waves.speed ** 2, damp = o.waves.damping;
      for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
        const x = -Rh + (i + 0.5) * dx, z = -Rh + (j + 0.5) * dx, on = level > GL.yb + 0.004 && x * x + z * z < r * r ? 1 : 0;
        if (on && !mask[j * N + i]) { H[j * N + i] = 0; HV[j * N + i] = 0; }
        mask[j * N + i] = on;
      }
      let sum = 0, cnt = 0;
      for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
        const k = j * N + i;
        if (!mask[k]) continue;
        const hc = H[k];
        const nb = (a, b) => (a >= 0 && b >= 0 && a < N && b < N && mask[b * N + a] ? H[b * N + a] : hc);
        const lap = (nb(i - 1, j) + nb(i + 1, j) + nb(i, j - 1) + nb(i, j + 1) - 4 * hc) / (dx * dx);
        HV[k] += (c2 * lap - damp * HV[k]) * h;
      }
      for (let k = 0; k < N * N; k++) if (mask[k]) { H[k] += HV[k] * h; sum += H[k]; cnt++; }
      if (cnt) { const m = sum / cnt, cap = o.waves.cap; for (let k = 0; k < N * N; k++) if (mask[k]) H[k] = clamp(H[k] - m, -cap, cap); }
    }

    // ---- the pour, the droplets, the bubbles (plain arrays: they come and go)
    const P = o.pour;
    if (!P.vel) { // solve the launch so the stream passes through `aim`: fall time from the height, then the reach
      const h = P.from[1] - P.aim[1], vy = P.vy0 ?? 0, tf = (vy + Math.sqrt(vy * vy + 2 * g * h)) / g;
      P.vel = [(P.aim[0] - P.from[0]) / tf, vy, (P.aim[2] - P.from[2]) / tf];
    }
    const pourVolume = GL.volumeAt(P.fill) || 0;
    const nEmit = Math.max(1, Math.round((P.t1 - P.t0) * P.rate)), blob = pourVolume / nEmit;
    let emitted = 0;
    const stream = [], drops = [], bubbles = [];
    const prng = mulberry(o.seed * 31 + 7);
    function splash(x, y, z, speed, n) {
      for (let k = 0; k < n; k++) {
        const a = prng() * Math.PI * 2, up = 0.5 + prng() * 0.9, out = 0.25 + prng() * 0.5, s = speed * (0.25 + prng() * 0.35);
        drops.push({ x: [x, y + 0.01, z], v: [Math.cos(a) * out * s, up * s, Math.sin(a) * out * s], r: 0.006 + prng() * 0.01 });
      }
    }
    function bubble(x, y, z, r) { if (bubbles.length < o.bubbles.max) bubbles.push({ x: [x, y, z], r: r || 0.004 + prng() * prng() * 0.008, ph: prng() * 6.28, sp: 0.16 + prng() * 0.14 }); }

    // ---- one substep
    let step = 0;
    const iters = 4;
    function substep() {
      const t = step * dt;
      for (const b of bodies) if (!b.awake && t >= b.d.t) wake(b, t);
      // pour: emit, fly, land
      if (t >= P.t0 && emitted < nEmit && t - P.t0 >= emitted / P.rate) {
        const wob = Math.sin(t * 7.3) * P.wobble, wob2 = Math.cos(t * 5.1) * P.wobble * 0.6;
        stream.push({ x: P.from.slice(), v: [P.vel[0] + wob, P.vel[1], P.vel[2] + wob2], id: emitted++ });
      }
      for (let k = stream.length - 1; k >= 0; k--) {
        const s = stream[k];
        s.v[1] -= g * dt;
        for (let c = 0; c < 3; c++) s.x[c] += s.v[c] * dt;
        const [x, y, z] = s.x;
        const under = inCavity(x, y, z) && y < surfaceY(x, z);
        const floorHit = y <= GL.yb + 0.004 || (y < GL.rim.y && Math.hypot(x, z) > GL.rIn(y) - 0.004 && Math.hypot(x, z) < GL.rIn(y) + GL.wall);
        if (under || floorHit || y < 0) {
          stream.splice(k, 1);
          if (!inCavity(x, y + 0.02, z) && !under) continue; // missed the glass: lost on the table
          Vliq += blob;
          const sp = -s.v[1];
          poke(x, z, -sp * 0.012, 1);
          if (prng() < 0.35) bubble(x + (prng() - 0.5) * 0.05, Math.max(GL.yb + 0.01, level - 0.03 - prng() * 0.2), z + (prng() - 0.5) * 0.05);
          if (prng() < 0.05) splash(x, surfaceY(x, z), z, sp * 0.5, 1);
        }
      }
      // bodies: forces, then predict
      for (let i = 0; i < NP; i++) {
        const b = bodies[owner[i]];
        if (!b.awake) continue;
        const x = X[i * 3], y = X[i * 3 + 1], z = X[i * 3 + 2], rp = b.rp;
        const f = inCavity(x, y, z) ? clamp((surfaceY(x, z) - (y - rp)) / (2 * rp)) : 0;
        const df = f - Fsub[i];
        if (Math.abs(df) > 1e-6) { // what goes under pushes the surface down (and back up as it rises)
          poke(x, z, -((df * b.volume) / b.count / (dx * dx)) * o.waves.couple, 1, true);
          if (df > 0.08 && Vv[i * 3 + 1] < -0.9) splash(x, surfaceY(x, z), z, -Vv[i * 3 + 1], 1 + Math.floor(prng() * 3));
          if (df > 0.02 && Vv[i * 3 + 1] < -0.5 && prng() < 0.4) bubble(x, y - rp, z, 0.006 + prng() * 0.006);
        }
        Fsub[i] = f;
        Vv[i * 3 + 1] += (-g + g * (1 / b.density) * f) * dt;
        // water drag, linear and with speed: a dropped cube dips and pops back, it does not sink
        const sp = Math.hypot(Vv[i * 3], Vv[i * 3 + 1], Vv[i * 3 + 2]);
        const drag = Math.exp(-o.drag[0] * f * dt) / (1 + o.drag[1] * sp * f * dt);
        for (let k = 0; k < 3; k++) Vv[i * 3 + k] *= drag;
        for (let k = 0; k < 3; k++) { Xp[i * 3 + k] = X[i * 3 + k]; X[i * 3 + k] += Vv[i * 3 + k] * dt; }
      }
      const contact = new Uint8Array(NP);
      for (let it = 0; it < iters; it++) {
        // the glass: inside the cavity, outside the walls, the rim, the floor
        for (let i = 0; i < NP; i++) {
          const b = bodies[owner[i]];
          if (!b.awake) continue;
          const rp = b.rp;
          let x = X[i * 3], y = X[i * 3 + 1], z = X[i * 3 + 2];
          let rho = Math.hypot(x, z);
          const ux = rho > 1e-9 ? x / rho : 1, uz = rho > 1e-9 ? z / rho : 0;
          // inside or outside is the BODY's, decided by its centre while it is above the rim: sphere by
          // sphere, a straw falling across the rim was split -- half its spheres slid down the outside
          if (b.c[1] > GL.rim.y + 0.05) Side[i] = Math.hypot(b.c[0], b.c[2]) < GL.rim.r ? 1 : 0;
          if (Side[i] && y < GL.rim.y + rp) {
            const [d, nr, ny] = nearest(GL.inner, rho, y), inside = y > GL.yb && rho < GL.rIn(y) + 1e-6;
            // a sphere already well outside is outside: yanking it through the wall launched a straw
            if (!inside && d > 2 * rp) Side[i] = 0;
          }
          if (Side[i] && y < GL.rim.y + rp) {
            const [d, nr, ny] = nearest(GL.inner, rho, y), inside = y > GL.yb && rho < GL.rIn(y) + 1e-6;
            const sd = inside ? d : -d, n2 = inside ? [nr, ny] : [-nr, -ny];
            if (sd < rp) { rho += n2[0] * (rp - sd); y += n2[1] * (rp - sd); contact[i] = 1; }
          } else if (!Side[i] && y < GL.rim.y + rp) {
            const poly = GL.outer, [d, nr, ny] = nearest(poly, rho, y), outside = rho > 0.0 && d > 0 && (rho > GL.rIn(y) + GL.wall * 0.5 || y < GL.yb);
            const sd = outside ? d : -d, n2 = outside ? [nr, ny] : [-nr, -ny];
            if (sd < rp) { rho += n2[0] * (rp - sd); y += n2[1] * (rp - sd); contact[i] = 1; }
          }
          const qr = rho - GL.rim.r, qy = y - GL.rim.y, dq = Math.hypot(qr, qy);
          if (dq < GL.rim.t + rp && dq > 1e-9) { const k = (GL.rim.t + rp - dq) / dq; rho += qr * k; y += qy * k; contact[i] = 1; }
          if (y < rp) { y = rp; contact[i] = 1; }
          X[i * 3] = ux * rho; X[i * 3 + 1] = y; X[i * 3 + 2] = uz * rho;
        }
        // each other
        for (let i = 0; i < NP; i++) {
          const bi = owner[i], B = bodies[bi];
          if (!B.awake) continue;
          for (let j = i + 1; j < NP; j++) {
            const bj = owner[j];
            if (bj === bi || !bodies[bj].awake) continue;
            const r = B.rp + bodies[bj].rp;
            const ddx = X[j * 3] - X[i * 3], ddy = X[j * 3 + 1] - X[i * 3 + 1], ddz = X[j * 3 + 2] - X[i * 3 + 2];
            const dd = ddx * ddx + ddy * ddy + ddz * ddz;
            if (dd >= r * r || dd < 1e-12) continue;
            const d = Math.sqrt(dd), wi = 1 / (B.density * B.volume / B.count), wj = 1 / (bodies[bj].density * bodies[bj].volume / bodies[bj].count);
            const k = (r - d) / d / (wi + wj);
            X[i * 3] -= ddx * k * wi; X[i * 3 + 1] -= ddy * k * wi; X[i * 3 + 2] -= ddz * k * wi;
            X[j * 3] += ddx * k * wj; X[j * 3 + 1] += ddy * k * wj; X[j * 3 + 2] += ddz * k * wj;
            contact[i] = contact[j] = 2;
          }
        }
        // shape matching: each body back to its own shape, rotated and moved as its spheres say
        for (const b of bodies) {
          if (!b.awake) continue;
          let cx = 0, cy = 0, cz = 0;
          for (let i = b.first; i < b.first + b.count; i++) { cx += X[i * 3]; cy += X[i * 3 + 1]; cz += X[i * 3 + 2]; }
          cx /= b.count; cy /= b.count; cz /= b.count;
          const A = [0, 0, 0, 0, 0, 0, 0, 0, 0]; // column-major: A = sum (x - c) r0^T
          for (let i = b.first; i < b.first + b.count; i++) {
            const px = X[i * 3] - cx, py = X[i * 3 + 1] - cy, pz = X[i * 3 + 2] - cz, rx = R0[i * 3], ry = R0[i * 3 + 1], rz = R0[i * 3 + 2];
            A[0] += px * rx; A[1] += py * rx; A[2] += pz * rx; A[3] += px * ry; A[4] += py * ry; A[5] += pz * ry; A[6] += px * rz; A[7] += py * rz; A[8] += pz * rz;
          }
          b.q = extractRotation(A, b.q);
          const Rm = qmat3(b.q);
          for (let i = b.first; i < b.first + b.count; i++) {
            const rx = R0[i * 3], ry = R0[i * 3 + 1], rz = R0[i * 3 + 2];
            X[i * 3] = cx + Rm[0] * rx + Rm[3] * ry + Rm[6] * rz;
            X[i * 3 + 1] = cy + Rm[1] * rx + Rm[4] * ry + Rm[7] * rz;
            X[i * 3 + 2] = cz + Rm[2] * rx + Rm[5] * ry + Rm[8] * rz;
          }
          b.c = [cx, cy, cz];
        }
      }
      // velocities, friction where it touches, and what the contacts sound like
      for (const b of bodies) {
        if (!b.awake) continue;
        let hitGlass = 0, hitBody = 0;
        for (let i = b.first; i < b.first + b.count; i++) {
          for (let k = 0; k < 3; k++) {
            const v = (X[i * 3 + k] - Xp[i * 3 + k]) / dt;
            if (contact[i]) {
              const dv = v - Vv[i * 3 + k]; // the velocity change the contact made: its impact
              if (contact[i] === 1) hitGlass = Math.max(hitGlass, Math.abs(dv)); else hitBody = Math.max(hitBody, Math.abs(dv));
            }
            Vv[i * 3 + k] = v * (contact[i] ? 0.96 : 1);
          }
          const sp = Math.hypot(Vv[i * 3], Vv[i * 3 + 1], Vv[i * 3 + 2]); // a conflict between constraints is not a launch
          if (sp > 9) for (let k = 0; k < 3; k++) Vv[i * 3 + k] *= 9 / sp;
        }
        const t2 = step * dt, hit = Math.max(hitGlass, hitBody);
        if (hit > 0.55 && t2 - b.hitT > 0.12 && b.kind !== 'mint') {
          events.push({ t: t2, kind: hitGlass >= hitBody ? 'glass' : 'clink', body: b.kind, speed: hit, x: b.c[0] });
          b.hitT = t2;
        }
        let fb = 0;
        for (let i = b.first; i < b.first + b.count; i++) fb += Fsub[i];
        if (!b.wet && fb / b.count > 0.2) { b.wet = true; events.push({ t: t2, kind: 'enter', body: b.kind, speed: Math.abs(Math.min(0, avgVy(b))), x: b.c[0] }); }
      }
      // droplets: fly, and land in the drink or die on the glass or the floor
      for (let k = drops.length - 1; k >= 0; k--) {
        const d = drops[k];
        d.v[1] -= g * dt;
        for (let c = 0; c < 3; c++) d.x[c] += d.v[c] * dt;
        const [x, y, z] = d.x, rho = Math.hypot(x, z);
        if (inCavity(x, y, z) && y < surfaceY(x, z)) { drops.splice(k, 1); poke(x, z, -0.02, 0); continue; }
        if (y < 0 || (y < GL.rim.y + 0.01 && Math.abs(rho - GL.rim.r) < GL.wall + d.r) || (y < GL.rim.y && rho > GL.rIn(y) - d.r && rho < GL.rIn(y) + GL.wall + 0.02)) drops.splice(k, 1);
      }
      // bubbles: born at the bottom and on the ice, rise with a wobble, pop at the surface
      if (level - GL.yb > 0.06 && t > P.t0 + 0.4) {
        if (prng() < o.bubbles.rate * dt) {
          const yy = GL.yb + 0.01 + prng() * Math.min(0.5, level - GL.yb - 0.05), rr = GL.rIn(yy) * 0.85 * Math.sqrt(prng()), a = prng() * 6.28;
          bubble(Math.cos(a) * rr, yy, Math.sin(a) * rr);
        }
        for (const b of bodies) if (b.awake && b.kind === 'ice' && prng() < o.bubbles.onIce * dt) {
          const i = b.first + Math.floor(prng() * b.count);
          if (Fsub[i] > 0.9) bubble(X[i * 3], X[i * 3 + 1] - b.rp, X[i * 3 + 2], 0.003 + prng() * 0.004);
        }
      }
      for (let k = bubbles.length - 1; k >= 0; k--) {
        const u = bubbles[k];
        u.x[1] += u.sp * dt;
        u.x[0] += Math.sin(u.ph + t * 9) * 0.03 * dt; u.x[2] += Math.cos(u.ph * 1.3 + t * 8) * 0.03 * dt;
        const rr = Math.hypot(u.x[0], u.x[2]), lim = GL.rIn(u.x[1]) - u.r - 0.004;
        if (rr > lim && rr > 1e-9) { u.x[0] *= lim / rr; u.x[2] *= lim / rr; }
        if (u.x[1] + u.r > surfaceY(u.x[0], u.x[2]) || !inCavity(u.x[0], u.x[1], u.x[2])) bubbles.splice(k, 1);
      }
      // the level: what was poured, plus what floats in it
      let disp = 0;
      for (const b of bodies) if (b.awake) for (let i = b.first; i < b.first + b.count; i++) disp += (Fsub[i] * b.volume) / b.count;
      level = GL.levelOf(Vliq + disp);
      waves(dt);
      step++;
    }
    function avgVy(b) { let s = 0; for (let i = b.first; i < b.first + b.count; i++) s += Vv[i * 3 + 1]; return s / b.count; }

    // ---- baking: a snapshot a frame
    const frames = [];
    const snap = () => {
      frames.push({
        level, H: new Float32Array(H),
        bodies: bodies.map((b) => (b.awake ? [b.c[0], b.c[1], b.c[2], ...b.q] : null)),
        stream: Float32Array.from(stream.flatMap((s) => [s.x[0], s.x[1], s.x[2], Math.hypot(...s.v), s.id])),
        drops: Float32Array.from(drops.flatMap((d) => [d.x[0], d.x[1], d.x[2], d.r])),
        bubbles: Float32Array.from(bubbles.flatMap((u) => [u.x[0], u.x[1], u.x[2], u.r])),
        vliq: Vliq,
      });
    };
    snap();
    function bakeTo(t) {
      const want = Math.ceil(t * o.fps + 1e-6);
      while (frames.length <= want) { for (let s = 0; s < o.substeps; s++) substep(); snap(); }
    }
    const frameAt = (t) => { bakeTo(t); return frames[Math.max(0, Math.round(t * o.fps - 1e-6))]; };

    const scene = {
      o, GL, bodies, N, Rh, dx, pourVolume,
      bakeTo, frameAt,
      /** the drink's state at t: level, volume poured, how many things are in, how many bubbles */
      stats(t) { const f = frameAt(t); return { level: f.level, poured: f.vliq, fill: (f.level - GL.yb) / (GL.rim.y - GL.yb), bodies: f.bodies.filter(Boolean).length, bubbles: f.bubbles.length / 4, stream: f.stream.length / 5 }; },
      /** what the sound hears, to `until`: the pour, things entering, clinks on glass and on ice */
      events(until) {
        const end = until ?? ((SK._film && SK._film.duration) || 10);
        bakeTo(end);
        const ev = events.filter((e) => e.t <= end).slice();
        // the pour sounds from its first landing to its last, its pitch rising as the air column shortens
        const land = frames.findIndex((f) => f.vliq > 0), lastIn = frames.findIndex((f, i) => i > land && f.vliq >= pourVolume - 1e-9);
        if (land > 0) {
          const t0 = land / o.fps, t1 = (lastIn > 0 ? lastIn : frames.length - 1) / o.fps, lv0 = frames[land].level, lv1 = frames[lastIn > 0 ? lastIn : frames.length - 1].level;
          const f = (lv) => 343 / (4 * Math.max(0.03, (GL.rim.y - lv) * 0.1)); // a quarter-wave tube, 1 unit = 10 cm
          ev.push({ t: t0, kind: 'pour', dur: t1 - t0, f0: f(lv0), f1: f(lv1) });
        }
        return ev.sort((a, b) => a.t - b.t);
      },
      /** the events as sketch-audio cues */
      sounds(opt = {}) {
        const cues = [], W = SK.W || 1920;
        const pan = (x) => +clamp(x * 0.9, -0.6, 0.6).toFixed(2);
        const end = opt.until ?? ((SK._film && SK._film.duration) || 10);
        for (const e of scene.events(end)) {
          const t = +e.t.toFixed(3);
          if (e.kind === 'pour') {
            cues.push({ t, fx: 'pour', db: -17, args: { sec: +(e.dur + 0.35).toFixed(2), f0: Math.round(e.f0), f1: Math.round(e.f1) } });
            cues.push({ t: +(t + 0.8).toFixed(3), fx: 'fizz', db: -30, args: { sec: +Math.max(1, end - t - 0.8).toFixed(2) } });
          } else if (e.kind === 'enter') {
            const big = e.body === 'straw' ? 0.5 : 1;
            cues.push({ t, fx: 'bloop', db: +clamp(-26 + 6 * Math.log10(1 + e.speed) * big, -34, -16).toFixed(1), pan: pan(e.x), args: { f0: e.body === 'ice' ? 520 : 700, f1: e.body === 'ice' ? 1300 : 1600 } });
          } else if (e.kind === 'glass' || e.kind === 'clink') {
            if (e.body === 'straw') continue;
            const db = clamp(-30 + 8 * Math.log10(e.speed), -40, -18);
            cues.push({ t, fx: 'clink', db: +db.toFixed(1), pan: pan(e.x), args: e.kind === 'glass' ? { tau: 0.22 } : { freqs: [3150, 4700, 6300], tau: 0.07, sec: 0.35 } });
          }
        }
        void W;
        return cues;
      },
    };
    scene.draw = function (t) { return draw(scene, t); };
    return scene;
  };

  /* Mueller et al. 2016, "A Robust Method to Extract the Rotational Part of Deformations":
     rotate q toward A a few times; warm-started from last step's q, so it stays continuous */
  function extractRotation(A, q) {
    for (let it = 0; it < 12; it++) {
      const R = qmat3(q);
      const c0 = [R[0], R[1], R[2]], c1 = [R[3], R[4], R[5]], c2 = [R[6], R[7], R[8]];
      const a0 = [A[0], A[1], A[2]], a1 = [A[3], A[4], A[5]], a2 = [A[6], A[7], A[8]];
      const x0 = cross(c0, a0), x1 = cross(c1, a1), x2 = cross(c2, a2);
      const den = Math.abs(c0[0] * a0[0] + c0[1] * a0[1] + c0[2] * a0[2] + c1[0] * a1[0] + c1[1] * a1[1] + c1[2] * a1[2] + c2[0] * a2[0] + c2[1] * a2[1] + c2[2] * a2[2]) + 1e-9;
      const w = [(x0[0] + x1[0] + x2[0]) / den, (x0[1] + x1[1] + x2[1]) / den, (x0[2] + x1[2] + x2[2]) / den];
      const ang = Math.hypot(...w);
      if (ang < 1e-9) break;
      q = qnorm(qmul(qaxis(w, ang), q));
    }
    return q;
  }

  /* ================================================================ drawing (browser only) */
  const painters = new WeakMap();
  function draw(s, t) {
    let p = painters.get(s);
    if (!p) { p = new Painter(s); painters.set(s, p); }
    if (!p.st.ok) {
      const ctx = SK.ctx(); ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = '#e8e4dd'; ctx.fillRect(0, 0, SK.W, SK.H); ctx.fillStyle = '#2a2521'; ctx.font = '600 40px system-ui'; ctx.textAlign = 'center';
      ctx.fillText('This film draws its glass with WebGL2, which this browser did not provide.', SK.W / 2, SK.H / 2); ctx.restore(); return;
    }
    p.render(t);
  }

  const VS_MESH = `#version 300 es
in vec3 aPos; in vec3 aNrm; in float aAttr;
uniform mat4 uVP, uM;
out vec3 vW; out vec3 vN; out vec3 vL; out float vA;
void main() { vec4 w = uM * vec4(aPos, 1.0); vW = w.xyz; vN = mat3(uM) * aNrm; vL = aPos; vA = aAttr; gl_Position = uVP * w; }`;
  const VS_INST = `#version 300 es
in vec3 aPos; in vec4 aInst;
uniform mat4 uVP;
out vec3 vW; out vec3 vN; out vec3 vL; out float vA;
void main() { vW = aInst.xyz + aPos * aInst.w; vN = aPos; vL = aPos; vA = aInst.w; gl_Position = uVP * vec4(vW, 1.0); }`;
  const FS_DEPTH = `#version 300 es
precision highp float;
void main() {}`;
  const HEAD = () => SK.gl3d.COMMON + `
in vec3 vW; in vec3 vN; in vec3 vL; in float vA;
uniform vec2 uRes; uniform float uNear, uFar;
out vec4 o;
float lin(float z) { return uNear * uFar / (uFar - z * (uFar - uNear)); }
`;
  // the far wall of the glass: only its reflection, premultiplied, composited behind everything inside
  const FS_GLASS_FAR = () => HEAD() + `
void main() {
  vec3 N = normalize(vN), V = normalize(uCam - vW);
  float NdV = abs(dot(N, V)), F = 0.04 + 0.96 * pow(1.0 - NdV, 5.0);
  vec3 c = envMap(reflect(-V, N)) * F + uKeyCol * spec(N, V, uKey, 0.0009) * F * 0.05;
  o = vec4(c * 0.85, F * 0.85);
}`;
  const FS_BODY = () => HEAD() + `
uniform int uKind; uniform sampler2D uBg; uniform float uSize;
void main() {
  vec3 N = normalize(vN), V = normalize(uCam - vW);
  if (dot(N, V) < 0.0) N = -N; // leaves are two-sided
  float NdV = clamp(dot(N, V), 0.0, 1.0), F = 0.03 + 0.97 * pow(1.0 - NdV, 5.0);
  vec3 R = reflect(-V, N), L = uKey;
  float wrap = clamp(dot(N, L) * 0.5 + 0.5, 0.0, 1.0), dif = max(dot(N, L), 0.0);
  vec3 light = uAmb + uKeyCol * dif * 0.9 + uFillCol * max(dot(N, uFill), 0.0) * 0.3;
  vec3 c;
  if (uKind == 0) { // ice: the floor bent through it, a frosted core, bright edges
    vec2 uv = gl_FragCoord.xy / uRes + refract(-V, N, 0.76).xy * 0.05;
    vec3 bg = texture(uBg, clamp(uv, 0.001, 0.999)).rgb;
    float frost = smoothstep(0.35, 0.75, fbm(vL * 22.0 + 3.0)) * 0.6 + smoothstep(0.55, 0.9, fbm(vL * 60.0)) * 0.25;
    c = bg * vec3(0.9, 0.96, 1.0) * (0.72 - 0.3 * frost) + vec3(0.62, 0.7, 0.74) * light * (0.18 + 0.5 * frost);
    c += envMap(R) * F * 1.3 + uKeyCol * spec(N, V, L, 0.002) * 0.08;
  } else if (uKind == 1) { // mint: green, lighter veins, light coming through
    float vein = 1.0 - smoothstep(0.02, 0.09, vA) + 0.35 * (1.0 - smoothstep(0.0, 0.05, abs(fract(vL.x * 28.0 + vA * 6.0) - 0.5) - 0.42));
    vec3 alb = mix(vec3(0.04, 0.2, 0.025), vec3(0.2, 0.42, 0.08), clamp(vein, 0.0, 1.0) * 0.6);
    c = alb * (uAmb + uKeyCol * wrap) + vec3(0.08, 0.22, 0.02) * uKeyCol * max(0.0, -dot(N, L)) * 0.9 + envMap(R) * F * 0.5;
  } else if (uKind == 2) { // lime: cut faces with segments and pith, a glossy rind
    float r = length(vL.xz) / uSize, a = atan(vL.z, vL.x);
    vec3 alb;
    if (vA > 0.5 || r > 0.93) alb = vec3(0.06, 0.26, 0.02) * (0.8 + 0.4 * vnoise(vL * 180.0));
    else if (r > 0.84) alb = vec3(0.8, 0.84, 0.6);
    else {
      float seg = abs(fract(a / 6.2832 * 10.0) - 0.5), mem = smoothstep(0.44, 0.49, seg) + (1.0 - smoothstep(0.08, 0.14, r));
      float cells = smoothstep(0.3, 0.8, fbm(vec3(vL.xz * 90.0, 1.0)));
      alb = mix(vec3(0.5, 0.68, 0.08) * (0.85 + 0.3 * cells), vec3(0.82, 0.86, 0.55), clamp(mem, 0.0, 1.0));
    }
    c = alb * (uAmb + uKeyCol * wrap * 0.95) + envMap(R) * F * (vA > 0.5 ? 1.0 : 0.6) + uKeyCol * spec(N, V, L, 0.006) * 0.05;
  } else { // a paper straw: spiral stripes, matte; dark in its hollow ends
    float a = atan(vL.z, vL.x) / 6.2832, u = fract(a * 2.0 + vL.y * 5.5);
    vec3 alb = mix(vec3(0.62, 0.2, 0.04), vec3(0.86, 0.72, 0.48), smoothstep(0.47, 0.53, u) * (1.0 - smoothstep(0.97, 1.0, u)));
    if (vA > 0.5) alb = vec3(0.05, 0.03, 0.02);
    c = alb * light + envMap(R) * F * 0.35 + uKeyCol * spec(N, V, L, 0.04) * 0.02;
  }
  o = vec4(c, 1.0);
}`;
  const FS_BUBBLE = () => HEAD() + `
void main() {
  vec3 N = normalize(vN), V = normalize(uCam - vW);
  float rim = pow(1.0 - clamp(abs(dot(N, V)), 0.0, 1.0), 1.4);
  o = vec4(mix(vec3(1.05, 1.08, 1.0), vec3(0.4, 0.46, 0.3), rim) + envMap(reflect(-V, N)) * 0.25, 1.0);
}`;
  // the liquid: what is behind it (and inside it) seen through it, bent, tinted, a little hazy
  const FS_LIQUID = () => HEAD() + `
uniform sampler2D uScene, uSceneDepth, uBackDepth; uniform mat4 uVP2;
uniform vec3 uAbsorb, uBody; uniform float uCloud, uThin, uLod;
void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec3 N = normalize(vN), V = normalize(uCam - vW);
  float NdV = dot(N, V);
  if (NdV < 0.02) { N = normalize(N + V * (0.02 - NdV)); NdV = 0.02; }
  float zF = lin(gl_FragCoord.z);
  float dj = uThin > 0.5 ? 2.0 * vA * NdV : clamp(lin(texture(uBackDepth, uv).r) - zF, 0.0, 1.0);
  vec3 Rr = refract(-V, N, 1.0 / 1.33);
  vec4 cp = uVP2 * vec4(vW + Rr * dj * 0.9, 1.0);
  vec2 ruv = clamp(cp.xy / cp.w * 0.5 + 0.5, vec2(0.001), vec2(0.999));
  float d = uThin > 0.5 ? dj : clamp(min(lin(texture(uBackDepth, uv).r), lin(texture(uSceneDepth, ruv).r)) - zF, 0.0, 1.0);
  vec3 bg = textureLod(uScene, ruv, clamp(d * uLod, 0.0, 5.0)).rgb;
  vec3 Tr = exp(-uAbsorb * d);
  float wrap = clamp(dot(N, uKey) * 0.5 + 0.5, 0.0, 1.0);
  vec3 lightIn = uAmb + uKeyCol * wrap * 0.8;
  vec3 c = bg * Tr * exp(-uCloud * d) + uBody * (1.0 - exp(-uCloud * d)) * mix(vec3(1.0), Tr, 0.5) * lightIn;
  float F = 0.02 + 0.98 * pow(1.0 - NdV, 5.0);
  c = c * (1.0 - F) + envMap(reflect(-V, N)) * F + uKeyCol * spec(N, V, uKey, 0.0016) * F * 0.08;
  o = vec4(c, 1.0);
}`;
  // the near wall of the glass: the whole drink seen through it, bent by its thickness
  const FS_GLASS = () => HEAD() + `
uniform sampler2D uScene, uSceneDepth, uBackDepth; uniform mat4 uVP2;
void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec3 N = normalize(vN), V = normalize(uCam - vW);
  float NdV = dot(N, V);
  if (NdV < 0.02) { N = normalize(N + V * (0.02 - NdV)); NdV = 0.02; }
  float zF = lin(gl_FragCoord.z);
  float d = clamp(min(lin(texture(uBackDepth, uv).r), lin(texture(uSceneDepth, uv).r)) - zF, 0.0, 0.5);
  vec3 Rr = refract(-V, N, 1.0 / 1.5);
  vec4 cp = uVP2 * vec4(vW + Rr * d * 1.1, 1.0);
  vec2 ruv = clamp(cp.xy / cp.w * 0.5 + 0.5, vec2(0.001), vec2(0.999));
  vec3 bg = textureLod(uScene, ruv, clamp(d * 10.0, 0.0, 3.0)).rgb * exp(-vec3(0.18, 0.06, 0.14) * d * 2.0);
  float F = 0.04 + 0.96 * pow(1.0 - NdV, 5.0);
  vec3 c = bg * (1.0 - F) + envMap(reflect(-V, N)) * F + uKeyCol * spec(N, V, uKey, 0.0006) * 0.06;
  o = vec4(c, 1.0);
}`;

  function Painter(s) {
    const G3 = SK.gl3d;
    if (!G3) throw new Error('SK.drink needs gl3d.js: "modules": ["gl3d", "drink"]');
    const st = (this.st = new G3.Stage({ ss: s.o.ss, light: s.o.light }));
    this.s = s;
    if (!st.ok) return;
    const gl = st.gl;
    this.P = {
      depth: st.prog(VS_MESH, FS_DEPTH), far: st.prog(VS_MESH, FS_GLASS_FAR()), body: st.prog(VS_MESH, FS_BODY()),
      bubble: st.prog(VS_INST, FS_BUBBLE()), liquid: st.prog(VS_MESH, FS_LIQUID()), liquidI: st.prog(VS_INST, FS_LIQUID()),
      glass: st.prog(VS_MESH, FS_GLASS()),
    };
    // targets: one depth shared by the passes that see each other, and the layers' colours
    this.depth = st.depthTarget(); this.depthCopy = st.depthTarget();
    this.farDepth = st.depthTarget(); this.liqBack = st.depthTarget(); this.glassBack = st.depthTarget();
    this.F = st.colorTarget(); this.GF = st.colorTarget(); this.A = st.colorTarget(true); this.B = st.colorTarget(true); this.C = st.colorTarget();
    this.fF = st.fbo(this.F, this.depth); this.fGF = st.fbo(this.GF, this.farDepth); this.fA = st.fbo(this.A, this.depth);
    this.fB = st.fbo(this.B, this.depth); this.fC = st.fbo(this.C, this.depth); this.fCopy = st.fbo(null, this.depthCopy);
    this.fLB = st.fbo(null, this.liqBack); this.fGB = st.fbo(null, this.glassBack);
    // meshes
    const mk = (m, dynamic) => {
      const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
      const nrm = m.nrm || G3.normals(m.pos, m.tri);
      const bp = st.buf(m.pos, gl.ARRAY_BUFFER, dynamic ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW); gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
      const bn = st.buf(nrm, gl.ARRAY_BUFFER, dynamic ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW); gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
      st.buf(m.attr || new Float32Array(m.pos.length / 3)); gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 0, 0);
      st.buf(m.tri, gl.ELEMENT_ARRAY_BUFFER);
      gl.bindVertexArray(null);
      return { vao, bp, bn, count: m.tri.length, two: m.twoSided };
    };
    const GL = s.GL;
    this.glass = mk(G3.lathe(GL.solid, 128));
    this.bodies = s.bodies.map((b) => ({ ...mk(b.mesh), kind: KIND_ID[b.kind], size: b.kind === 'lime' ? b.d.size || 0.11 : 0 }));
    const rl = s.o.rimLime;
    if (rl) this.rim = { ...mk(wheel(rl.size || 0.19, (rl.size || 0.19) * 0.22, 0.22)), size: rl.size || 0.19 };
    // the liquid: fixed topology, positions rewritten every frame
    this.KW = 40; this.KC = 22; this.SEG = 96;
    const rows = this.KW + 1 + this.KC, lq = { pos: new Float32Array(rows * (this.SEG + 1) * 3), tri: [] };
    for (let sg = 0; sg < this.SEG; sg++) for (let k = 0; k < rows - 1; k++) { const a = sg * rows + k, b = (sg + 1) * rows + k; lq.tri.push(a, a + 1, b, b, a + 1, b + 1); } // outward, as the lathe
    lq.tri = new Uint32Array(lq.tri);
    this.lq = lq; this.liquid = mk(lq, true); this.lqNrm = new Float32Array(lq.pos.length);
    // the stream: a tube, rebuilt every frame
    this.TS = 12; this.streamMax = 400;
    const sPos = new Float32Array(this.streamMax * this.TS * 3), sTri = [];
    for (let k = 0; k < this.streamMax - 1; k++) for (let j = 0; j < this.TS; j++) { const a = k * this.TS + j, b = k * this.TS + ((j + 1) % this.TS); sTri.push(a, b, a + this.TS, b, b + this.TS, a + this.TS); }
    this.sm = { pos: sPos, tri: new Uint32Array(sTri), attr: new Float32Array(this.streamMax * this.TS) };
    this.stream = mk(this.sm, true);
    this.sAttrBuf = null;
    gl.bindVertexArray(this.stream.vao);
    this.sAttrBuf = st.buf(this.sm.attr, gl.ARRAY_BUFFER, gl.DYNAMIC_DRAW); gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
    // droplets and bubbles: one sphere, instanced
    const sph = G3.sphere(8, 12), mkInst = () => {
      const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
      st.buf(sph.pos); gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
      st.buf(sph.nrm); gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
      const ib = st.buf(new Float32Array(4 * 600), gl.ARRAY_BUFFER, gl.DYNAMIC_DRAW); gl.enableVertexAttribArray(3); gl.vertexAttribPointer(3, 4, gl.FLOAT, false, 0, 0); gl.vertexAttribDivisor(3, 1);
      st.buf(sph.tri, gl.ELEMENT_ARRAY_BUFFER); gl.bindVertexArray(null);
      return { vao, ib, count: sph.tri.length, n: 0 };
    };
    this.bub = mkInst(); this.drp = mkInst();
  }
  const KIND_ID = { ice: 0, mint: 1, lime: 2, straw: 3 };

  Painter.prototype.updateLiquid = function (f) {
    const s = this.s, GL = s.GL, KW = this.KW, KC = this.KC, SEG = this.SEG, rows = KW + 1 + KC, P = this.lq.pos;
    const hAt = (x, z) => {
      const fx = (x + s.Rh) / s.dx - 0.5, fz = (z + s.Rh) / s.dx - 0.5, i = Math.floor(fx), j = Math.floor(fz), u = fx - i, v = fz - j, N = s.N, H = f.H;
      const at = (a, b) => (a >= 0 && b >= 0 && a < N && b < N ? H[b * N + a] : 0);
      return at(i, j) * (1 - u) * (1 - v) + at(i + 1, j) * u * (1 - v) + at(i, j + 1) * (1 - u) * v + at(i + 1, j + 1) * u * v;
    };
    // the side: the glass's inner profile from the bottom centre up to the level, by arc length
    const inner = GL.inner, S = GL.innerS, lv = f.level;
    let sLv = S[S.length - 1];
    for (let i = 1; i < inner.length; i++) if (inner[i][1] >= lv) { const a = inner[i - 1], b = inner[i]; sLv = S[i - 1] + (S[i] - S[i - 1]) * ((lv - a[1]) / Math.max(1e-9, b[1] - a[1])); break; }
    const along = (sv) => { for (let i = 1; i < S.length; i++) if (S[i] >= sv) { const u = (sv - S[i - 1]) / Math.max(1e-9, S[i] - S[i - 1]); return [inner[i - 1][0] + (inner[i][0] - inner[i - 1][0]) * u, inner[i - 1][1] + (inner[i][1] - inner[i - 1][1]) * u]; } return inner[inner.length - 1]; };
    const prof = [];
    for (let k = 0; k <= KW; k++) { const [r, y] = along((sLv * k) / KW); prof.push([Math.max(0, r - 0.0025), k === KW ? lv : y, k === KW]); }
    const rTop = prof[KW][0];
    for (let c = 1; c <= KC; c++) prof.push([rTop * (1 - c / KC), lv, true]);
    for (let sg = 0; sg <= SEG; sg++) {
      const a = (sg / SEG) * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a);
      for (let k = 0; k < rows; k++) {
        const [r, y, top] = prof[k], x = r * ca, z = r * sa, o = (sg * rows + k) * 3;
        P[o] = x; P[o + 1] = top ? y + hAt(x, z) : y; P[o + 2] = z;
      }
    }
    const gl = this.st.gl;
    G3N(this.lq.pos, this.lq.tri, this.lqNrm);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.liquid.bp); gl.bufferSubData(gl.ARRAY_BUFFER, 0, P);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.liquid.bn); gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.lqNrm);
  };
  const G3N = (p, t, o) => SK.gl3d.normals(p, t, o);
  /** the pour as one tube through its blobs in the order they left: thinner as they speed up
   *  (what continuity does to a falling stream), rounded off at the head and the tail */
  Painter.prototype.updateStream = function (f) {
    const s = this.s, P0 = s.o.pour, TS = this.TS, pos = this.sm.pos, at = this.sm.attr, st = f.stream, n = Math.min(this.streamMax, st.length / 5);
    this.streamCount = n > 1 ? (n - 1) * TS * 6 : 0;
    if (!this.streamCount) return;
    const v0 = Math.hypot(...P0.vel), idx = [];
    for (let k = 0; k < n; k++) idx.push(k);
    idx.sort((a, b) => st[a * 5 + 4] - st[b * 5 + 4]);
    for (let q = 0; q < n; q++) {
      const k = idx[q], c = [st[k * 5], st[k * 5 + 1], st[k * 5 + 2]];
      const kp = idx[Math.max(0, q - 1)], kn = idx[Math.min(n - 1, q + 1)];
      let tn = [st[kn * 5] - st[kp * 5], st[kn * 5 + 1] - st[kp * 5 + 1], st[kn * 5 + 2] - st[kp * 5 + 2]];
      const tl = Math.hypot(...tn) || 1; tn = tn.map((v) => v / tl);
      let u = cross(tn, Math.abs(tn[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]); const ul = Math.hypot(...u) || 1; u = u.map((v) => v / ul);
      const w = cross(tn, u), end = Math.min(q, n - 1 - q);
      const r = P0.radius * Math.sqrt(v0 / Math.max(v0, st[k * 5 + 3])) * (end === 0 ? 0.35 : end === 1 ? 0.8 : 1);
      for (let j = 0; j < TS; j++) {
        const a = (j / TS) * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a), o = (q * TS + j) * 3;
        pos[o] = c[0] + (u[0] * ca + w[0] * sa) * r; pos[o + 1] = c[1] + (u[1] * ca + w[1] * sa) * r; pos[o + 2] = c[2] + (u[2] * ca + w[2] * sa) * r;
        at[q * TS + j] = r;
      }
    }
    const gl = this.st.gl, nrm = G3N(pos.subarray(0, n * TS * 3), this.sm.tri.subarray(0, this.streamCount));
    gl.bindBuffer(gl.ARRAY_BUFFER, this.stream.bp); gl.bufferSubData(gl.ARRAY_BUFFER, 0, pos.subarray(0, n * TS * 3));
    gl.bindBuffer(gl.ARRAY_BUFFER, this.stream.bn); gl.bufferSubData(gl.ARRAY_BUFFER, 0, nrm);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.sAttrBuf); gl.bufferSubData(gl.ARRAY_BUFFER, 0, at.subarray(0, n * TS));
  };
  Painter.prototype.inst = function (I, data) {
    const gl = this.st.gl, n = Math.min(600, data.length / 4);
    I.n = n;
    if (!n) return;
    gl.bindBuffer(gl.ARRAY_BUFFER, I.ib); gl.bufferSubData(gl.ARRAY_BUFFER, 0, data.subarray(0, n * 4));
  };
  /** the lime wheel on the rim: placed, with a slide and a settle */
  Painter.prototype.rimMatrix = function (t) {
    const rl = this.s.o.rimLime, GL = this.s.GL;
    if (!rl || t < rl.t) return null;
    const u = clamp((t - rl.t) / 0.45), e = 1 - Math.pow(1 - u, 3), a = ((rl.angle ?? 35) * Math.PI) / 180;
    const dir = [Math.cos(a), 0, Math.sin(a)], tan = [-Math.sin(a), 0, Math.cos(a)];
    const size = this.rim.size, c = [dir[0] * GL.rim.r, GL.rim.y + size * 0.12, dir[2] * GL.rim.r]; // centre just over the rim
    const from = [c[0] + dir[0] * 0.25, c[1] + 0.55, c[2] + dir[2] * 0.25];
    const p = [0, 1, 2].map((k) => from[k] + (c[k] - from[k]) * e);
    const settle = (t - rl.t) > 0.45 ? 0.2 * Math.exp(-6 * (t - rl.t - 0.45)) * Math.sin(20 * (t - rl.t - 0.45)) : 0;
    // the wheel's slit (its local +x) points down over the rim, its face looks along the rim
    // axes, not a quaternion: the wheel's slit (its local +x) points down over the rim, its face
    // (local y) looks along the rim, local z goes out from the glass; then a tilt about the radius
    const ang = ((rl.tilt ?? 10) * Math.PI) / 180 + settle, rot = (v) => { // Rodrigues about dir
      const c = Math.cos(ang), sn = Math.sin(ang), k = dir, kv = cross(k, v), kd = k[0] * v[0] + k[1] * v[1] + k[2] * v[2];
      return [0, 1, 2].map((i) => v[i] * c + kv[i] * sn + k[i] * kd * (1 - c));
    };
    const X = rot([0, -1, 0]), Y = rot(tan), Z = rot(dir);
    return [X[0], X[1], X[2], 0, Y[0], Y[1], Y[2], 0, Z[0], Z[1], Z[2], 0, p[0], p[1], p[2], 1];
  };
  Painter.prototype.render = function (t) {
    const s = this.s, st = this.st, gl = st.gl, P = this.P, G3 = SK.gl3d, o = s.o;
    const f = s.frameAt(t);
    const cam = G3.camera(o.camera, t, (SK._film && SK._film.duration) || 10);
    const VP = new Float32Array(cam.VP), I = new Float32Array(G3.IDENT);
    this.updateLiquid(f); this.updateStream(f);
    this.inst(this.bub, f.bubbles); this.inst(this.drp, f.drops);
    const bodyM = f.bodies.map((b) => (b ? G3.quatMat([b[3], b[4], b[5], b[6]], [b[0], b[1], b[2]]) : null));
    const rimM = this.rim ? this.rimMatrix(t) : null;
    const hasLiquid = f.level > s.GL.yb + 0.003;
    const common = (u) => { st.setCommon(u, cam); if (u.uRes) gl.uniform2f(u.uRes, st.W, st.H); if (u.uNear) { gl.uniform1f(u.uNear, cam.near); gl.uniform1f(u.uFar, cam.far); } if (u.uM) gl.uniformMatrix4fv(u.uM, false, I); };
    const drawMesh = (m) => { gl.bindVertexArray(m.vao); gl.drawElements(gl.TRIANGLES, m.count, gl.UNSIGNED_INT, 0); };

    // 1. shadows: the glass throws a pale one, the drink a tinted one, the rest their own
    const lqTint = o.liquid.body.map((v) => 0.55 + v * 0.45);
    const draws = [{ vao: this.glass.vao, count: this.glass.count, tint: [0.8, 0.82, 0.82] }];
    if (hasLiquid) draws.push({ vao: this.liquid.vao, count: this.liquid.count, tint: lqTint, noContact: true });
    this.bodies.forEach((b, i) => { if (bodyM[i]) draws.push({ vao: b.vao, count: b.count, M: bodyM[i], tint: b.kind === 0 ? [0.75, 0.8, 0.8] : [0.45, 0.5, 0.4], noContact: true }); });
    if (rimM) draws.push({ vao: this.rim.vao, count: this.rim.count, M: rimM, tint: [0.5, 0.6, 0.3], noContact: true });
    st.shadows(draws, [0, 0], { contact: 1.2, cast: 3.0, castFall: 2.5 });

    // 2. the floor, then the glass's far wall over it
    st.floor(this.fF, cam, [0, 0], { ao: 0.3, castK: 0.5, pool: [-0.3, -0.2, 0.2] });
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fGF); gl.viewport(0, 0, st.W, st.H);
    gl.clearColor(0, 0, 0, 0); gl.clearDepth(0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.clearDepth(1);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.GREATER); gl.depthMask(true); gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK); gl.disable(gl.BLEND);
    gl.useProgram(P.far.p); common(P.far.u); drawMesh(this.glass);
    gl.depthFunc(gl.LESS);
    st.over(this.GF, this.fF);

    // 3. what is in the glass: ice (the floor bent through it), leaves, lime, straws, bubbles
    st.copy(this.F, this.fA, false);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fA); gl.viewport(0, 0, st.W, st.H);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true);
    gl.useProgram(P.body.p); common(P.body.u);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.F); gl.uniform1i(P.body.u.uBg, 0);
    const drawBody = (m, M, kind, size) => {
      if (m.two) gl.disable(gl.CULL_FACE); else { gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK); }
      gl.uniformMatrix4fv(P.body.u.uM, false, new Float32Array(M)); gl.uniform1i(P.body.u.uKind, kind); gl.uniform1f(P.body.u.uSize, size || 1);
      drawMesh(m);
    };
    this.bodies.forEach((b, i) => { if (bodyM[i]) drawBody(b, bodyM[i], b.kind, b.size); });
    if (rimM) drawBody(this.rim, rimM, 2, this.rim.size);
    if (this.bub.n) {
      gl.enable(gl.CULL_FACE); gl.useProgram(P.bubble.p); common(P.bubble.u);
      gl.bindVertexArray(this.bub.vao); gl.drawElementsInstanced(gl.TRIANGLES, this.bub.count, gl.UNSIGNED_INT, 0, this.bub.n);
    }
    st.mips(this.A);

    // 4. the drink: its own depth, then everything above read through it
    const blitDepth = (from) => { gl.bindFramebuffer(gl.READ_FRAMEBUFFER, from); gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, this.fCopy); gl.blitFramebuffer(0, 0, st.W, st.H, 0, 0, st.W, st.H, gl.DEPTH_BUFFER_BIT, gl.NEAREST); gl.bindFramebuffer(gl.READ_FRAMEBUFFER, null); gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, null); };
    st.copy(this.A, this.fB, false);
    if (hasLiquid || this.streamCount || this.drp.n) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fLB); gl.viewport(0, 0, st.W, st.H); gl.clearDepth(1); gl.clear(gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true); gl.enable(gl.CULL_FACE); gl.cullFace(gl.FRONT);
      gl.useProgram(P.depth.p); common(P.depth.u);
      if (hasLiquid) drawMesh(this.liquid);
      blitDepth(this.fA);
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fB); gl.viewport(0, 0, st.W, st.H);
      gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true); gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK);
      const lq = (p, thin) => {
        gl.useProgram(p.p); common(p.u);
        gl.uniformMatrix4fv(p.u.uVP2, false, VP);
        gl.uniform3fv(p.u.uAbsorb, o.liquid.absorb); gl.uniform3fv(p.u.uBody, o.liquid.body); gl.uniform1f(p.u.uCloud, o.liquid.cloud);
        gl.uniform1f(p.u.uThin, thin); gl.uniform1f(p.u.uLod, 6 * st.ss);
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.A); gl.uniform1i(p.u.uScene, 0);
        gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.depthCopy); gl.uniform1i(p.u.uSceneDepth, 1);
        gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, this.liqBack); gl.uniform1i(p.u.uBackDepth, 2);
      };
      if (hasLiquid) { lq(P.liquid, 0); drawMesh(this.liquid); }
      if (this.streamCount) { lq(P.liquid, 1); gl.bindVertexArray(this.stream.vao); gl.drawElements(gl.TRIANGLES, this.streamCount, gl.UNSIGNED_INT, 0); }
      if (this.drp.n) { lq(P.liquidI, 1); gl.bindVertexArray(this.drp.vao); gl.drawElementsInstanced(gl.TRIANGLES, this.drp.count, gl.UNSIGNED_INT, 0, this.drp.n); }
      for (const u of [2, 1, 0]) { gl.activeTexture(gl.TEXTURE0 + u); gl.bindTexture(gl.TEXTURE_2D, null); }
    }
    st.mips(this.B);

    // 5. the glass's near wall, reading the whole drink through its own thickness
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fGB); gl.viewport(0, 0, st.W, st.H); gl.clearDepth(1); gl.clear(gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true); gl.enable(gl.CULL_FACE); gl.cullFace(gl.FRONT);
    gl.useProgram(P.depth.p); common(P.depth.u); drawMesh(this.glass);
    blitDepth(this.fB);
    st.copy(this.B, this.fC, false);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fC); gl.viewport(0, 0, st.W, st.H);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true); gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK);
    gl.useProgram(P.glass.p); common(P.glass.u); gl.uniformMatrix4fv(P.glass.u.uVP2, false, VP);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.B); gl.uniform1i(P.glass.u.uScene, 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.depthCopy); gl.uniform1i(P.glass.u.uSceneDepth, 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, this.glassBack); gl.uniform1i(P.glass.u.uBackDepth, 2);
    drawMesh(this.glass);
    for (const u of [2, 1, 0]) { gl.activeTexture(gl.TEXTURE0 + u); gl.bindTexture(gl.TEXTURE_2D, null); }
    gl.bindVertexArray(null); gl.disable(gl.CULL_FACE);

    st.present(this.C);
    this.cam = cam;
  };
  /** film pixels of a world point at t (for type placed against the glass) */
  D.project = (scene, p, t) => SK.gl3d.project(SK.gl3d.camera(scene.o.camera, t, (SK._film && SK._film.duration) || 10).VP, p);
})();
