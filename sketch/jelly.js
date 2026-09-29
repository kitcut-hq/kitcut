/* sketch/jelly.js -- soft-body jelly for sketch films (vanilla JS + WebGL2, no libraries).

   A specimen is a gummy object -- today a watermelon slice -- that a scripted hand grabs,
   stretches, twists, pokes, lifts and drops, rendered as translucent candy in a studio. A film
   loads this module by listing "modules": ["jelly"] in its sketch.json and calls

       const melon = SK.jelly.specimen({ actions: [...], camera: {...} });
       SK.film({ ..., draw(t) { melon.draw(t); } });

   The engine's one rule -- every frame is a pure function of t -- holds by BAKING: the simulation
   runs forward from t = 0 in fixed steps (same inputs, same numbers, every run) and keeps one
   snapshot per frame; draw(t) only reads snapshots. A still at 9 s bakes up to 9 s first; an
   export reads them in order. Nothing here calls Math.random or reads the clock.

   Physics -- XPBD on a tetrahedral mesh cut from a grid (Macklin, Mueller et al.): one distance
   constraint per tet edge and one volume constraint per tet, `substeps` fixed substeps per frame,
   damping that removes only the non-rigid part of the motion (so a falling slice still falls),
   ground contact with friction. The rind's edges are stiffer than the flesh's. The volume
   constraint is signed, so an inverted tet is pushed back through, not left inside out.

   What you see is a finer surface extracted from the shape's distance field (surface nets) and
   carried by the tets through barycentric coordinates -- as are the seeds and the air bubbles,
   so they move, turn and stretch with the flesh instead of floating in place.

   Light -- the floor (lit pool, contact shadow, a tinted cast shadow) and the inclusions render
   first; the jelly then reads that picture THROUGH itself: thickness from its own back faces,
   Beer-Lambert absorption per channel (thin edges glow, thick flesh goes deep red), a refracted
   lookup, scattering that clouds it with depth, Fresnel reflection of a studio (a key softbox and
   a strip light), and key light leaking through thin parts. The flesh, the pale layer and the
   striped skin each have their own response.

   LIVE (the player's ?live=1): the same simulation stepped from the wall clock instead of baked --
   start the movement and the physics follows, as in a three.js page. Only the latest frame is
   kept, at most two frames are simulated per drawn frame (a slow machine gets slow motion, not
   catch-up bursts), and the pointer is a hand: press on the slice, drag, let go. The scripted
   `actions` play until the first touch, then the hand is yours. sketch-render.py --live N runs
   it headless for N seconds, records it and reports whether the physics kept real time.

   The physics half runs without a DOM (scripts/check-sketch.py bakes a specimen under Node and
   checks volume, inversion, settling, determinism and floor contact).
*/
(function () {
  'use strict';
  const root = typeof window !== 'undefined' ? window : globalThis;
  const SK = (root.SK = root.SK || {});
  const J = (SK.jelly = {});

  const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
  const EASE = {
    lin: (x) => x,
    inOut: (x) => x * x * (3 - 2 * x),
    in: (x) => x * x,
    out: (x) => 1 - (1 - x) * (1 - x),
    sine: (x) => 0.5 - 0.5 * Math.cos(Math.PI * x),
  };
  function mulberry(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* ------------------------------------------------------------ looks
     Colours are LINEAR RGB. absorb: Beer-Lambert per unit length (what the flesh takes out of
     light passing through -- red survives in 'crimson'); body: the colour light scatters back
     with; cloud: how quickly scattering hides what is behind. pale* is the layer under the rind. */
  J.PRESETS = {
    crimson: {
      absorb: [0.8, 10, 8], body: [0.62, 0.008, 0.022], cloud: 2.6,
      paleAbsorb: [0.4, 0.6, 1.8], paleBody: [0.8, 0.8, 0.52], paleCloud: 9,
      skin: [0.045, 0.15, 0.03], stripe: [0.01, 0.045, 0.01], seed: [0.018, 0.011, 0.008],
      shadow: [0.62, 0.36, 0.36],
    },
    golden: {
      absorb: [0.45, 2.2, 11], body: [0.85, 0.3, 0.012], cloud: 2.6,
      paleAbsorb: [0.4, 0.6, 1.8], paleBody: [0.8, 0.8, 0.52], paleCloud: 9,
      skin: [0.045, 0.15, 0.03], stripe: [0.01, 0.045, 0.01], seed: [0.03, 0.017, 0.01],
      shadow: [0.66, 0.5, 0.34],
    },
    rose: {
      absorb: [0.5, 5.5, 3.6], body: [0.75, 0.09, 0.16], cloud: 3,
      paleAbsorb: [0.4, 0.6, 1.8], paleBody: [0.8, 0.8, 0.55], paleCloud: 9,
      skin: [0.07, 0.2, 0.05], stripe: [0.02, 0.07, 0.02], seed: [0.02, 0.012, 0.01],
      shadow: [0.64, 0.42, 0.46],
    },
  };

  const DEFAULTS = {
    wedge: { radius: 1, angle: 58, thickness: 0.3, round: 0.075, corner: 0.09 },
    rind: { skin: 0.045, pale: 0.065 },
    preset: 'crimson',
    firmness: 0.4, // 0..1, the reference panel's "firmness"
    damping: 0.45, // 0..1, its "internal damping"
    rindFirmness: 2.5, // the rind's edges are this many times stiffer than the flesh's
    bulk: 25, // volume stiffness as a multiple of the elastic one (high locks the coarse mesh up)
    cell: 0.05, // tet grid spacing (world units; the slice's radius is 1)
    surfaceCell: 0.0125, // render-surface grid spacing
    fps: 60, substeps: 10, gravity: 30, friction: 0.55,
    seeds: { rows: [0.4, 0.54, 0.68], spacing: 0.085, size: [0.062, 0.034, 0.017], depth: 0.045, both: true, seed: 7 },
    bubbles: { n: 16, seed: 3 },
    pose: { at: [0, 0.3, 0], yaw: 35 }, // at: where the slice's centre sits, [x, height of its underside, z]
    actions: [],
    // follow: how much of the slice's wandering the camera takes up (0 = locked off), lag: seconds
    camera: { target: null, dist: 3.0, elev: 36, azim: 0, fov: 28, orbit: 0, shift: [0, 0], follow: 0.6, lag: 0.8 },
    light: { key: [-0.55, 1.0, -0.45], fill: [0.95, 0.35, 0.75], floor: [0.72, 0.7, 0.66] },
    scale: { cm: 6, gcc: 1.3 }, // readouts only: 1 world unit = cm, gummy density g/cm3
    ss: null, // supersampling; default 2 when rendering a file, 1 when playing live
    cursor: true,
    // a live page (?live=1) swaps these in: measured best-of-3 on the laptop, a simulated frame
    // costs 9.5 ms at cell .05 x 10 substeps and 6.6 ms at .06 x 8, with the same ~5 Hz wobble
    live: { cell: 0.06, substeps: 8, catchUp: 2 },
  };
  const LIVE_PAGE = typeof location !== 'undefined' && /[?&]live=/.test(location.search);
  function merge(a, b) {
    const o = { ...a };
    for (const k of Object.keys(b || {})) {
      o[k] = b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object' && !Array.isArray(a[k]) ? merge(a[k], b[k]) : b[k];
    }
    return o;
  }

  /* ------------------------------------------------------------ the shape: a distance field
     Rest-local space: the tip at the origin, the slice opening along +z, y up, the rind at
     radius R. iq's pie, its corners rounded by `corner`, extruded to `thickness` with the top and
     bottom edges rounded by `round`. */
  function wedgeSDF(w) {
    const R = w.radius, ha = (w.angle * Math.PI) / 360, T = w.thickness, b = w.round, rc = w.corner;
    const cx = Math.sin(ha), cz = Math.cos(ha), r2 = R - rc;
    return function (x, y, z) {
      const px = Math.abs(x), pz = z;
      const l = Math.hypot(px, pz) - r2;
      const d = clamp(px * cx + pz * cz, 0, r2);
      const m = Math.hypot(px - cx * d, pz - cz * d);
      const d2 = Math.max(l, m * Math.sign(cz * px - cx * pz)) - rc;
      const wx = d2 + b, wy = Math.abs(y) - (T / 2 - b);
      return Math.min(Math.max(wx, wy), 0) + Math.hypot(Math.max(wx, 0), Math.max(wy, 0)) - b;
    };
  }

  /* ------------------------------------------------------------ surface nets
     A smooth closed triangle mesh of {sdf < 0}: one vertex per grid cell the surface crosses
     (the mean of its edge crossings, then projected onto the surface), one quad per crossed
     grid edge. Winding is checked against the field's gradient. */
  function surfaceNets(sdf, lo, hi, hs) {
    const nx = Math.ceil((hi[0] - lo[0]) / hs) + 1, ny = Math.ceil((hi[1] - lo[1]) / hs) + 1, nz = Math.ceil((hi[2] - lo[2]) / hs) + 1;
    const val = new Float64Array(nx * ny * nz);
    const I = (i, j, k) => i + nx * (j + ny * k);
    for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) val[I(i, j, k)] = sdf(lo[0] + i * hs, lo[1] + j * hs, lo[2] + k * hs);
    const cx = nx - 1, cy = ny - 1, cz = nz - 1;
    const C = (i, j, k) => i + cx * (j + cy * k);
    const vid = new Int32Array(cx * cy * cz).fill(-1);
    const pos = [];
    const E = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]];
    const eps = hs * 0.05;
    const grad = (x, y, z) => [sdf(x + eps, y, z) - sdf(x - eps, y, z), sdf(x, y + eps, z) - sdf(x, y - eps, z), sdf(x, y, z + eps) - sdf(x, y, z - eps)];
    const cv = new Float64Array(8);
    for (let k = 0; k < cz; k++) for (let j = 0; j < cy; j++) for (let i = 0; i < cx; i++) {
      let mask = 0;
      for (let b = 0; b < 8; b++) { cv[b] = val[I(i + (b & 1), j + ((b >> 1) & 1), k + ((b >> 2) & 1))]; if (cv[b] < 0) mask |= 1 << b; }
      if (mask === 0 || mask === 255) continue;
      let sx = 0, sy = 0, sz = 0, n = 0;
      for (const [a, b] of E) {
        if ((cv[a] < 0) === (cv[b] < 0)) continue;
        const t = cv[a] / (cv[a] - cv[b]);
        const ax = a & 1, ay = (a >> 1) & 1, az = (a >> 2) & 1, bx = b & 1, by = (b >> 1) & 1, bz = (b >> 2) & 1;
        sx += ax + (bx - ax) * t; sy += ay + (by - ay) * t; sz += az + (bz - az) * t; n++;
      }
      let x = lo[0] + (i + sx / n) * hs, y = lo[1] + (j + sy / n) * hs, z = lo[2] + (k + sz / n) * hs;
      for (let it = 0; it < 3; it++) { // onto the surface
        const d = sdf(x, y, z), g = grad(x, y, z), gg = g[0] * g[0] + g[1] * g[1] + g[2] * g[2];
        if (gg < 1e-12) break;
        const s = (d * 2 * eps) / gg;
        x -= g[0] * s; y -= g[1] * s; z -= g[2] * s;
      }
      vid[C(i, j, k)] = pos.length / 3;
      pos.push(x, y, z);
    }
    const tri = [];
    const quad = (a, b, c, d) => {
      if (a < 0 || b < 0 || c < 0 || d < 0) return;
      const P = (v) => [pos[v * 3], pos[v * 3 + 1], pos[v * 3 + 2]];
      const pa = P(a), pb = P(b), pc = P(c), pd = P(d);
      // outward winding: compare the quad's normal with the field's gradient at its centre
      const n = cross(sub(pc, pa), sub(pd, pb));
      const m = [(pa[0] + pc[0]) / 2, (pa[1] + pc[1]) / 2, (pa[2] + pc[2]) / 2];
      const g = grad(m[0], m[1], m[2]);
      const flip = n[0] * g[0] + n[1] * g[1] + n[2] * g[2] < 0;
      const q = flip ? [a, d, c, b] : [a, b, c, d];
      // split along the shorter diagonal
      if (dist2(P(q[0]), P(q[2])) < dist2(P(q[1]), P(q[3]))) tri.push(q[0], q[1], q[2], q[0], q[2], q[3]);
      else tri.push(q[0], q[1], q[3], q[1], q[2], q[3]);
    };
    for (let k = 1; k < cz; k++) for (let j = 1; j < cy; j++) for (let i = 0; i < cx; i++) // x edges
      if ((val[I(i, j, k)] < 0) !== (val[I(i + 1, j, k)] < 0)) quad(vid[C(i, j - 1, k - 1)], vid[C(i, j, k - 1)], vid[C(i, j, k)], vid[C(i, j - 1, k)]);
    for (let k = 1; k < cz; k++) for (let j = 0; j < cy; j++) for (let i = 1; i < cx; i++) // y edges
      if ((val[I(i, j, k)] < 0) !== (val[I(i, j + 1, k)] < 0)) quad(vid[C(i - 1, j, k - 1)], vid[C(i, j, k - 1)], vid[C(i, j, k)], vid[C(i - 1, j, k)]);
    for (let k = 0; k < cz; k++) for (let j = 1; j < cy; j++) for (let i = 1; i < cx; i++) // z edges
      if ((val[I(i, j, k)] < 0) !== (val[I(i, j, k + 1)] < 0)) quad(vid[C(i - 1, j - 1, k)], vid[C(i, j - 1, k)], vid[C(i, j, k)], vid[C(i - 1, j, k)]);
    return { pos: new Float64Array(pos), tri: new Uint32Array(tri) };
  }
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dist2 = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

  /* ------------------------------------------------------------ inclusions: seeds and bubbles
     Each is a small closed mesh in rest-local space; `kind` 0 is a seed, 1 a bubble. */
  function ellipsoid(out, c, ax, ay, az, sx, sy, sz, taper, rings, segs, kind) {
    const base = out.pos.length / 3;
    for (let r = 0; r <= rings; r++) {
      const u = -1 + (2 * r) / rings, rad = Math.sqrt(Math.max(0, 1 - u * u)) * (1 - taper * (u + 1) * 0.5);
      for (let s = 0; s < segs; s++) {
        const a = (s / segs) * Math.PI * 2, cw = Math.cos(a) * rad, sw = Math.sin(a) * rad;
        const lx = u * sx, ly = sw * sy, lz = cw * sz; // along ax (length), ay (up), az (width)
        out.pos.push(c[0] + ax[0] * lx + ay[0] * ly + az[0] * lz, c[1] + ax[1] * lx + ay[1] * ly + az[1] * lz, c[2] + ax[2] * lx + ay[2] * ly + az[2] * lz);
        out.kind.push(kind);
      }
    }
    for (let r = 0; r < rings; r++) for (let s = 0; s < segs; s++) {
      const a = base + r * segs + s, b = base + r * segs + ((s + 1) % segs), c2 = a + segs, d = b + segs;
      out.tri.push(a, c2, b, b, c2, d);
    }
  }
  function inclusions(o) {
    const w = o.wedge, R = w.radius, T = w.thickness, ha = (w.angle * Math.PI) / 360;
    const out = { pos: [], tri: [], kind: [] };
    const S = o.seeds;
    if (S) {
      const rnd = mulberry(S.seed * 7919 + 13);
      const [len, wid, th] = S.size;
      for (const side of S.both ? [1, -1] : [1]) {
        S.rows.forEach((rf, ri) => {
          const r = rf * R, margin = 0.075 + wid * 0.5, span = 2 * (r * ha) - 2 * margin; // arc length inside the cut faces
          if (span <= 0) return;
          const n = Math.max(1, Math.round(span / S.spacing));
          for (let q = 0; q < n; q++) {
            const along = n === 1 ? 0 : -span / 2 + (span * (q + 0.5 + (ri % 2) * 0.35)) / n;
            const a = along / r + (rnd() - 0.5) * 0.04, rr = r + (rnd() - 0.5) * 0.035;
            const cxz = [Math.sin(a) * rr, Math.cos(a) * rr];
            const y = side * (T / 2 - S.depth) + (rnd() - 0.5) * 0.006;
            // long axis points at the tip, tilted a little into the flesh; flat side faces out
            const tilt = side * (0.18 + rnd() * 0.12), yaw = (rnd() - 0.5) * 0.35;
            const dir = [-Math.sin(a + yaw), 0, -Math.cos(a + yaw)];
            const ax = [dir[0] * Math.cos(tilt), Math.sin(tilt), dir[2] * Math.cos(tilt)];
            const az = cross(ax, [0, 1, 0]); const zl = Math.hypot(...az); az[0] /= zl; az[1] /= zl; az[2] /= zl;
            const ay = cross(az, ax);
            const k = 0.85 + rnd() * 0.3;
            ellipsoid(out, [cxz[0], y, cxz[1]], ax, ay, az, (len / 2) * k, (th / 2) * k, (wid / 2) * k, 0.45, 8, 12, 0);
          }
        });
      }
    }
    const B = o.bubbles;
    if (B && B.n > 0) {
      const rnd = mulberry(B.seed * 104729 + 7);
      for (let q = 0; q < B.n; q++) {
        const a = (rnd() - 0.5) * 2 * ha * 0.75, rr = (0.18 + rnd() * 0.6) * R, y = (rnd() - 0.5) * (T - 0.1);
        const s = 0.004 + rnd() * rnd() * 0.009;
        ellipsoid(out, [Math.sin(a) * rr, y, Math.cos(a) * rr], [1, 0, 0], [0, 1, 0], [0, 0, 1], s, s, s, 0, 5, 8, 1);
      }
    }
    return { pos: new Float64Array(out.pos), tri: new Uint32Array(out.tri), kind: new Float32Array(out.kind) };
  }

  /* ------------------------------------------------------------ the tet mesh
     Grid cells whose centre lies inside (or within 0.45 cell of) the shape, six Kuhn tets each
     (all cubes split along the same diagonal, so neighbouring faces agree). y is gridded so a
     node plane lies exactly on the top and on the bottom face: the underside touches the floor. */
  const PERMS = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
  function tetMesh(o, sdf) {
    const w = o.wedge, R = w.radius, T = w.thickness, ha = (w.angle * Math.PI) / 360;
    const h = o.cell, ny = Math.max(2, Math.round(T / h)), hy = T / ny;
    const xmax = R * Math.sin(ha) + w.corner, zmin = -w.corner - h, zmax = R + h;
    const nx = Math.ceil((2 * xmax) / h) + 1, nz = Math.ceil((zmax - zmin) / h) + 1;
    const ox = (-nx * h) / 2, oy = -T / 2, oz = zmin;
    const NX = nx + 1, NY = ny + 1;
    const nodeId = new Map(), rest = [], tets = [];
    const cellTet = new Int32Array(nx * ny * nz).fill(-1);
    const node = (i, j, k) => {
      const key = i + NX * (j + NY * k);
      let id = nodeId.get(key);
      if (id === undefined) { id = rest.length / 3; nodeId.set(key, id); rest.push(ox + i * h, oy + j * hy, oz + k * h); }
      return id;
    };
    for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      if (sdf(ox + (i + 0.5) * h, oy + (j + 0.5) * hy, oz + (k + 0.5) * h) > 0.45 * h) continue;
      const c = [];
      for (let b = 0; b < 8; b++) c.push(node(i + (b & 1), j + ((b >> 1) & 1), k + ((b >> 2) & 1)));
      cellTet[i + nx * (j + ny * k)] = tets.length / 4;
      for (const p of PERMS) { const v1 = 1 << p[0], v2 = v1 | (1 << p[1]); tets.push(c[0], c[v1], c[v2], c[7]); }
    }
    const X = new Float64Array(rest), TT = new Int32Array(tets), m = TT.length / 4;
    for (let t = 0; t < m; t++) if (tetVol(X, TT, t) < 0) { const a = TT[t * 4 + 2]; TT[t * 4 + 2] = TT[t * 4 + 3]; TT[t * 4 + 3] = a; }
    return { rest: X, tets: TT, grid: { h, hy, nx, ny, nz, ox, oy, oz, cellTet } };
  }
  function tetVol(X, T, t) {
    const a = T[t * 4] * 3, b = T[t * 4 + 1] * 3, c = T[t * 4 + 2] * 3, d = T[t * 4 + 3] * 3;
    const e1x = X[b] - X[a], e1y = X[b + 1] - X[a + 1], e1z = X[b + 2] - X[a + 2];
    const e2x = X[c] - X[a], e2y = X[c + 1] - X[a + 1], e2z = X[c + 2] - X[a + 2];
    const e3x = X[d] - X[a], e3y = X[d + 1] - X[a + 1], e3z = X[d + 2] - X[a + 2];
    return ((e1y * e2z - e1z * e2y) * e3x + (e1z * e2x - e1x * e2z) * e3y + (e1x * e2y - e1y * e2x) * e3z) / 6;
  }

  /* barycentric embedding: each render vertex rides the tet that contains it (or, just outside
     the tet mesh, the one it is least outside of, extrapolated) */
  function embedder(mesh) {
    const { rest: X, tets: T, grid: g } = mesh, m = T.length / 4;
    const inv = new Float64Array(m * 9);
    for (let t = 0; t < m; t++) {
      const a = T[t * 4] * 3;
      const cols = [1, 2, 3].map((q) => { const b = T[t * 4 + q] * 3; return [X[b] - X[a], X[b + 1] - X[a + 1], X[b + 2] - X[a + 2]]; });
      const [c0, c1, c2] = cols;
      // inverse of the 3x3 matrix whose columns are c0 c1 c2: rows are the cross products / det
      const r0 = cross(c1, c2), r1 = cross(c2, c0), r2 = cross(c0, c1);
      const det = c0[0] * r0[0] + c0[1] * r0[1] + c0[2] * r0[2];
      for (let q = 0; q < 3; q++) { inv[t * 9 + q] = r0[q] / det; inv[t * 9 + 3 + q] = r1[q] / det; inv[t * 9 + 6 + q] = r2[q] / det; }
    }
    const bary = (t, p, out) => {
      const a = T[t * 4] * 3, dx = p[0] - X[a], dy = p[1] - X[a + 1], dz = p[2] - X[a + 2], o = t * 9;
      out[1] = inv[o] * dx + inv[o + 1] * dy + inv[o + 2] * dz;
      out[2] = inv[o + 3] * dx + inv[o + 4] * dy + inv[o + 5] * dz;
      out[3] = inv[o + 6] * dx + inv[o + 7] * dy + inv[o + 8] * dz;
      out[0] = 1 - out[1] - out[2] - out[3];
      return Math.min(out[0], out[1], out[2], out[3]);
    };
    return function embed(P) {
      const n = P.length / 3, tet = new Int32Array(n), w = new Float32Array(n * 4), tmp = [0, 0, 0, 0];
      for (let v = 0; v < n; v++) {
        const p = [P[v * 3], P[v * 3 + 1], P[v * 3 + 2]];
        const ci = Math.floor((p[0] - g.ox) / g.h), cj = Math.floor((p[1] - g.oy) / g.hy), ck = Math.floor((p[2] - g.oz) / g.h);
        let best = -1, bestMin = -Infinity;
        const bw = [0, 0, 0, 0];
        for (let r = 0; r <= 3 && (best < 0 || bestMin < -1e-6); r++) {
          for (let dk = -r; dk <= r; dk++) for (let dj = -r; dj <= r; dj++) for (let di = -r; di <= r; di++) {
            if (Math.max(Math.abs(di), Math.abs(dj), Math.abs(dk)) !== r) continue;
            const i = ci + di, j = cj + dj, k = ck + dk;
            if (i < 0 || j < 0 || k < 0 || i >= g.nx || j >= g.ny || k >= g.nz) continue;
            const t0 = g.cellTet[i + g.nx * (j + g.ny * k)];
            if (t0 < 0) continue;
            for (let t = t0; t < t0 + 6; t++) {
              const mn = bary(t, p, tmp);
              if (mn > bestMin) { bestMin = mn; best = t; bw[0] = tmp[0]; bw[1] = tmp[1]; bw[2] = tmp[2]; bw[3] = tmp[3]; }
            }
          }
        }
        tet[v] = best; w.set(bw, v * 4);
      }
      return { tet, w };
    };
  }

  /* ------------------------------------------------------------ the specimen */
  J.specimen = function (spec = {}) {
    const o = merge(DEFAULTS, spec);
    if (LIVE_PAGE) Object.assign(o, o.live);
    const P = typeof o.preset === 'string' ? { ...(J.PRESETS[o.preset] || J.PRESETS.crimson) } : { ...J.PRESETS.crimson, ...o.preset };
    const w = o.wedge, R = w.radius, T = w.thickness;
    const sdf = wedgeSDF(w);
    const mesh = tetMesh(o, sdf);
    const n = mesh.rest.length / 3, TT = mesh.tets, m = TT.length / 4;

    // ---- rest -> world: yaw about y, the centroid moved to pose.at
    let vol0 = 0, cz = 0;
    const restVol = new Float64Array(m);
    for (let t = 0; t < m; t++) {
      const v = tetVol(mesh.rest, TT, t); restVol[t] = v; vol0 += v;
      for (let q = 0; q < 4; q++) cz += (mesh.rest[TT[t * 4 + q] * 3 + 2] * v) / 4;
    }
    cz /= vol0;
    const yaw = (o.pose.yaw * Math.PI) / 180, cy = Math.cos(yaw), sy = Math.sin(yaw);
    const at = o.pose.at;
    const toWorld = (x, y, z) => { const lz = z - cz; return [x * cy + lz * sy + at[0], y + T / 2 + at[1], -x * sy + lz * cy + at[2]]; };

    // ---- particles
    const X = new Float64Array(n * 3), Pv = new Float64Array(n * 3), V = new Float64Array(n * 3), Wm = new Float64Array(n), M = new Float64Array(n);
    for (let i = 0; i < n; i++) X.set(toWorld(mesh.rest[i * 3], mesh.rest[i * 3 + 1], mesh.rest[i * 3 + 2]), i * 3);
    // "Young's modulus" in sim units: firmness .4 wobbles at ~4.5 Hz, the frequency gummy candy has
    const E = 7.5 * Math.pow(60, clamp(o.firmness));
    const K = o.bulk * E; // bulk modulus: how hard each tet holds its volume
    const rindAt = R - o.rind.skin - o.rind.pale * 0.5;
    const volAlpha = new Float64Array(m);
    for (let t = 0; t < m; t++) {
      for (let q = 0; q < 4; q++) M[TT[t * 4 + q]] += restVol[t] / 4;
      volAlpha[t] = restVol[t] / K;
    }
    for (let i = 0; i < n; i++) Wm[i] = M[i] > 0 ? 1 / M[i] : 0;
    const eset = new Map(), ed = [];
    for (let t = 0; t < m; t++) for (let a = 0; a < 4; a++) for (let b = a + 1; b < 4; b++) {
      let i = TT[t * 4 + a], j = TT[t * 4 + b]; if (i > j) [i, j] = [j, i];
      const key = i * n + j; if (!eset.has(key)) { eset.set(key, 1); ed.push(i, j); }
    }
    const EI = new Int32Array(ed), ne = EI.length / 2, L0 = new Float64Array(ne), edgeAlpha = new Float64Array(ne);
    for (let e = 0; e < ne; e++) {
      const i = EI[e * 2] * 3, j = EI[e * 2 + 1] * 3;
      L0[e] = Math.hypot(X[j] - X[i], X[j + 1] - X[i + 1], X[j + 2] - X[i + 2]);
      const mx = (mesh.rest[i] + mesh.rest[j]) / 2, mz = (mesh.rest[i + 2] + mesh.rest[j + 2]) / 2;
      const stiff = Math.hypot(mx, mz) > rindAt ? o.rindFirmness : 1;
      edgeAlpha[e] = 1 / (E * stiff * L0[e]);
    }

    // ---- what is drawn, embedded in the tets
    const embed = embedder(mesh);
    const ha = (w.angle * Math.PI) / 360, pad = o.surfaceCell * 2;
    const surf = surfaceNets(sdf, [-R * Math.sin(ha) - w.corner - pad, -T / 2 - pad, -w.corner - pad], [R * Math.sin(ha) + w.corner + pad, T / 2 + pad, R + pad], o.surfaceCell);
    const incl = inclusions(o);
    const surfE = embed(surf.pos), inclE = embed(incl.pos);

    // ---- the hand: grabs, pokes, nudges -- all in sim time
    const named = {
      tip: [0, T * 0.15, 0.1], flesh: [0, T / 2, 0.55 * R], centre: [0, 0, 0.6 * R], center: [0, 0, 0.6 * R],
      rind: [0, 0, R - 0.05], 'corner-left': [-Math.sin(ha) * (R - 0.12), 0, Math.cos(ha) * (R - 0.12)],
      'corner-right': [Math.sin(ha) * (R - 0.12), 0, Math.cos(ha) * (R - 0.12)],
    };
    const restPoint = (p) => (typeof p === 'string' ? named[p] : p) || named.flesh;
    const keyed = (keys, u, dim) => { // keys [[dt, value, ease?], ...] with an implied [0, zero]
      const ks = [[0, dim ? [0, 0, 0] : 0], ...keys];
      if (u <= 0) return ks[0][1];
      for (let q = 1; q < ks.length; q++) {
        if (u <= ks[q][0]) {
          const a = ks[q - 1], b = ks[q], f = (EASE[b[2] || 'inOut'] || EASE.inOut)((u - a[0]) / Math.max(1e-9, b[0] - a[0]));
          return dim ? [0, 1, 2].map((c) => a[1][c] + (b[1][c] - a[1][c]) * f) : a[1] + (b[1] - a[1]) * f;
        }
      }
      return ks[ks.length - 1][1];
    };
    const acts = o.actions.map((a, idx) => {
      const kind = a.grab !== undefined ? 'grab' : a.poke !== undefined ? 'poke' : a.nudge !== undefined ? 'nudge' : null;
      if (!kind) throw new Error('jelly action ' + idx + ': needs grab, poke or nudge');
      const path = a.path || [], twist = a.twist || [];
      const dur = kind === 'grab' ? Math.max(...path.map((k) => k[0]), ...twist.map((k) => k[0]), 0.05) : kind === 'poke' ? a.dur || 0.6 : 0;
      return { ...a, kind, dur, st: null };
    });

    function startGrab(a) {
      const rp = restPoint(a.grab), rad = a.radius || 0.17;
      const sel = [], wt = [];
      let sw = 0, c = [0, 0, 0];
      for (let i = 0; i < n; i++) {
        const d = Math.hypot(mesh.rest[i * 3] - rp[0], mesh.rest[i * 3 + 1] - rp[1], mesh.rest[i * 3 + 2] - rp[2]);
        if (d >= rad) continue;
        const f = 1 - clamp((d - rad * 0.35) / (rad * 0.65)); const k = f * f * (3 - 2 * f);
        sel.push(i); wt.push(k); sw += k;
        c[0] += X[i * 3] * k; c[1] += X[i * 3 + 1] * k; c[2] += X[i * 3 + 2] * k;
      }
      if (!sel.length) throw new Error('jelly grab ' + JSON.stringify(a.grab) + ' caught nothing: move the point inside the slice');
      c = c.map((v) => v / sw);
      const anchor = new Float64Array(sel.length * 3);
      sel.forEach((i, q) => anchor.set([X[i * 3] - c[0], X[i * 3 + 1] - c[1], X[i * 3 + 2] - c[2]], q * 3));
      // the cursor sits on top of the grabbed spot
      let top = -Infinity; for (const i of sel) top = Math.max(top, X[i * 3 + 1]);
      a.st = { sel, wt, c, anchor, lift: top - c[1] };
    }
    function applyGrab(a, u) {
      const s = a.st, D = keyed(a.path || [], u, true), th = ((keyed(a.twist || [], u, false) || 0) * Math.PI) / 180;
      const ax = a.axis || [0, 1, 0], al = Math.hypot(...ax), k = [ax[0] / al, ax[1] / al, ax[2] / al];
      const ct = Math.cos(th), st = Math.sin(th);
      const gain = a.grip ?? 0.6;
      for (let q = 0; q < s.sel.length; q++) {
        const i = s.sel[q], r = [s.anchor[q * 3], s.anchor[q * 3 + 1], s.anchor[q * 3 + 2]];
        // Rodrigues: r rotated by th about k
        const kr = cross(k, r), kd = k[0] * r[0] + k[1] * r[1] + k[2] * r[2];
        const rr = [0, 1, 2].map((c) => r[c] * ct + kr[c] * st + k[c] * kd * (1 - ct));
        const tx = s.c[0] + D[0] + rr[0], ty = Math.max(0, s.c[1] + D[1] + rr[1]), tz = s.c[2] + D[2] + rr[2];
        const f = s.wt[q] * gain;
        X[i * 3] += (tx - X[i * 3]) * f; X[i * 3 + 1] += (ty - X[i * 3 + 1]) * f; X[i * 3 + 2] += (tz - X[i * 3 + 2]) * f;
      }
      return [s.c[0] + D[0], s.c[1] + D[1] + s.lift, s.c[2] + D[2]];
    }
    function startPoke(a) {
      const rp = restPoint(a.poke);
      let best = 0, bd = Infinity;
      for (let i = 0; i < n; i++) {
        const d = Math.hypot(mesh.rest[i * 3] - rp[0], mesh.rest[i * 3 + 1] - rp[1], mesh.rest[i * 3 + 2] - rp[2]);
        if (d < bd) { bd = d; best = i; }
      }
      a.st = { p: [X[best * 3], X[best * 3 + 1], X[best * 3 + 2]], r: a.radius || 0.09 };
    }
    function applyPoke(a, u) {
      const s = a.st, press = Math.sin(Math.PI * clamp(u / a.dur)) ** 2;
      const cyf = s.p[1] + s.r + 0.2 * (1 - press) - (a.depth ?? 0.1) * press;
      for (let i = 0; i < n; i++) {
        const dx = X[i * 3] - s.p[0], dy = X[i * 3 + 1] - cyf, dz = X[i * 3 + 2] - s.p[2], d = Math.hypot(dx, dy, dz);
        if (d >= s.r || d < 1e-9) continue;
        const k = (s.r - d) / d;
        X[i * 3] += dx * k; X[i * 3 + 1] += dy * k; X[i * 3 + 2] += dz * k;
      }
      return [s.p[0], cyf + s.r, s.p[2], press];
    }
    function nudge(a) {
      const amp = a.nudge === true ? 1 : +a.nudge || 1, hop = a.hop ?? 1;
      let cx = 0, cyy = 0, cz2 = 0, mt = 0;
      for (let i = 0; i < n; i++) { cx += X[i * 3] * M[i]; cyy += X[i * 3 + 1] * M[i]; cz2 += X[i * 3 + 2] * M[i]; mt += M[i]; }
      cx /= mt; cyy /= mt; cz2 /= mt;
      for (let i = 0; i < n; i++) { // a hop, a shear and a twist: every low mode gets some
        const rx = X[i * 3] - cx, ry = X[i * 3 + 1] - cyy, rz = X[i * 3 + 2] - cz2;
        V[i * 3] += amp * (ry * 6 - rz * 1.5);
        V[i * 3 + 1] += amp * hop * (1.6 + rx * 1.2);
        V[i * 3 + 2] += amp * (rx * 1.5 + ry * 3);
      }
    }

    // ---- the solver
    const dt = 1 / (o.fps * o.substeps), g = o.gravity, mu = o.friction;
    const dampRate = 3.2 * clamp(o.damping), kd = 1 - Math.exp(-dampRate * dt); // per second, on top of the solver's own
    let step = 0, impact = 0;
    // live: the pointer's hand (touching the slice ends the script), and a nudge asked for
    let user = null, touched = false, pendingNudge = 0;
    const X0 = new Float64Array(X);
    function applyUser() {
      const s = user, D = s.D;
      for (let q = 0; q < s.sel.length; q++) {
        const i = s.sel[q], f = s.wt[q] * 0.6;
        const tx = s.c[0] + D[0] + s.anchor[q * 3], ty = Math.max(0, s.c[1] + D[1] + s.anchor[q * 3 + 1]), tz = s.c[2] + D[2] + s.anchor[q * 3 + 2];
        X[i * 3] += (tx - X[i * 3]) * f; X[i * 3 + 1] += (ty - X[i * 3 + 1]) * f; X[i * 3 + 2] += (tz - X[i * 3 + 2]) * f;
      }
      return { p: [s.c[0] + D[0], s.c[1] + D[1] + s.lift, s.c[2] + D[2]], press: 1, kind: 'grab', u: step * dt - s.t0, dur: Infinity };
    }
    function substep() {
      const tau = step * dt;
      if (pendingNudge) { nudge({ nudge: pendingNudge }); pendingNudge = 0; }
      if (!touched) for (const a of acts) if (a.kind === 'nudge' && !a.st && tau >= a.t) { a.st = 1; nudge(a); } // a kick is a velocity: before the positions move
      for (let i = 0; i < n; i++) {
        const b = i * 3;
        V[b + 1] -= g * dt;
        Pv[b] = X[b]; Pv[b + 1] = X[b + 1]; Pv[b + 2] = X[b + 2];
        X[b] += V[b] * dt; X[b + 1] += V[b + 1] * dt; X[b + 2] += V[b + 2] * dt;
      }
      let hand = null;
      if (!touched) for (const a of acts) {
        if (tau < a.t) continue;
        if (a.kind === 'nudge') continue;
        const u = tau - a.t;
        if (u > a.dur) continue;
        if (!a.st) a.kind === 'grab' ? startGrab(a) : startPoke(a);
        if (a.kind === 'grab') hand = { p: applyGrab(a, u), press: 1, kind: 'grab', u, dur: a.dur };
        else { const r = applyPoke(a, u); hand = { p: r.slice(0, 3), press: r[3], kind: 'poke', u, dur: a.dur }; }
      }
      if (user) hand = applyUser();
      // edges
      const dt2 = dt * dt;
      for (let e = 0; e < ne; e++) {
        const i = EI[e * 2], j = EI[e * 2 + 1], wsum = Wm[i] + Wm[j];
        if (wsum === 0) continue;
        const a = i * 3, b = j * 3;
        const dx = X[b] - X[a], dy = X[b + 1] - X[a + 1], dz = X[b + 2] - X[a + 2], len = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (len < 1e-12) continue;
        const s = (len - L0[e]) / (wsum + edgeAlpha[e] / dt2) / len;
        X[a] += dx * s * Wm[i]; X[a + 1] += dy * s * Wm[i]; X[a + 2] += dz * s * Wm[i];
        X[b] -= dx * s * Wm[j]; X[b + 1] -= dy * s * Wm[j]; X[b + 2] -= dz * s * Wm[j];
      }
      // volumes (gradients in Mueller's 10-minute-physics order), unrolled: this loop is the bake
      for (let t = 0; t < m; t++) {
        const i0 = TT[t * 4], i1 = TT[t * 4 + 1], i2 = TT[t * 4 + 2], i3 = TT[t * 4 + 3];
        const w0 = Wm[i0], w1 = Wm[i1], w2 = Wm[i2], w3 = Wm[i3];
        const a = i0 * 3, b = i1 * 3, c = i2 * 3, d = i3 * 3;
        const x0 = X[a], y0 = X[a + 1], z0 = X[a + 2], x1 = X[b], y1 = X[b + 1], z1 = X[b + 2];
        const x2 = X[c], y2 = X[c + 1], z2 = X[c + 2], x3 = X[d], y3 = X[d + 1], z3 = X[d + 2];
        // grad0 = (p3-p1)x(p2-p1), grad1 = (p2-p0)x(p3-p0), grad2 = (p3-p0)x(p1-p0), grad3 = (p1-p0)x(p2-p0); all /6
        let ux = x3 - x1, uy = y3 - y1, uz = z3 - z1, vx = x2 - x1, vy = y2 - y1, vz = z2 - z1;
        const g0x = (uy * vz - uz * vy) / 6, g0y = (uz * vx - ux * vz) / 6, g0z = (ux * vy - uy * vx) / 6;
        const ax = x1 - x0, ay = y1 - y0, az = z1 - z0, bx = x2 - x0, by = y2 - y0, bz = z2 - z0, cx = x3 - x0, cy = y3 - y0, cz = z3 - z0;
        const g1x = (by * cz - bz * cy) / 6, g1y = (bz * cx - bx * cz) / 6, g1z = (bx * cy - by * cx) / 6;
        const g2x = (cy * az - cz * ay) / 6, g2y = (cz * ax - cx * az) / 6, g2z = (cx * ay - cy * ax) / 6;
        const g3x = (ay * bz - az * by) / 6, g3y = (az * bx - ax * bz) / 6, g3z = (ax * by - ay * bx) / 6;
        const wsum = w0 * (g0x * g0x + g0y * g0y + g0z * g0z) + w1 * (g1x * g1x + g1y * g1y + g1z * g1z) + w2 * (g2x * g2x + g2y * g2y + g2z * g2z) + w3 * (g3x * g3x + g3y * g3y + g3z * g3z);
        if (wsum === 0) continue;
        const vol = g3x * cx + g3y * cy + g3z * cz;
        const s = -(vol - restVol[t]) / (wsum + volAlpha[t] / dt2);
        let k = s * w0; X[a] += g0x * k; X[a + 1] += g0y * k; X[a + 2] += g0z * k;
        k = s * w1; X[b] += g1x * k; X[b + 1] += g1y * k; X[b + 2] += g1z * k;
        k = s * w2; X[c] += g2x * k; X[c + 1] += g2y * k; X[c + 2] += g2z * k;
        k = s * w3; X[d] += g3x * k; X[d + 1] += g3y * k; X[d + 2] += g3z * k;
      }
      // the floor, with friction; what it stops dead is the landing's energy (the sound's cue)
      for (let i = 0; i < n; i++) {
        const b = i * 3;
        if (X[b + 1] >= 0) continue;
        const pen = -X[b + 1], vy = (X[b + 1] - Pv[b + 1]) / dt; X[b + 1] = 0;
        if (vy < 0) impact += 0.5 * M[i] * vy * vy;
        const dx = X[b] - Pv[b], dz = X[b + 2] - Pv[b + 2], d = Math.hypot(dx, dz);
        if (d < mu * pen * 1.2) { X[b] = Pv[b]; X[b + 2] = Pv[b + 2]; } else if (d > 0) { const k = Math.min(1, (mu * pen) / d); X[b] -= dx * k; X[b + 2] -= dz * k; }
      }
      for (let i = 0; i < n * 3; i++) V[i] = (X[i] - Pv[i]) / dt;
      damp();
      step++;
      return hand;
    }
    // damping that leaves the rigid motion alone (Mueller et al. 2007, "Position Based Dynamics" 3.5)
    function damp() {
      let mt = 0, xc0 = 0, xc1 = 0, xc2 = 0, vc0 = 0, vc1 = 0, vc2 = 0;
      for (let i = 0; i < n; i++) {
        const mi = M[i], b = i * 3; mt += mi;
        xc0 += X[b] * mi; xc1 += X[b + 1] * mi; xc2 += X[b + 2] * mi; vc0 += V[b] * mi; vc1 += V[b + 1] * mi; vc2 += V[b + 2] * mi;
      }
      xc0 /= mt; xc1 /= mt; xc2 /= mt; vc0 /= mt; vc1 /= mt; vc2 /= mt;
      let L0_ = 0, L1 = 0, L2 = 0, I00 = 0, I01 = 0, I02 = 0, I11 = 0, I12 = 0, I22 = 0;
      for (let i = 0; i < n; i++) {
        const mi = M[i], b = i * 3, rx = X[b] - xc0, ry = X[b + 1] - xc1, rz = X[b + 2] - xc2, vx = V[b], vy = V[b + 1], vz = V[b + 2];
        L0_ += (ry * vz - rz * vy) * mi; L1 += (rz * vx - rx * vz) * mi; L2 += (rx * vy - ry * vx) * mi;
        I00 += (ry * ry + rz * rz) * mi; I11 += (rx * rx + rz * rz) * mi; I22 += (rx * rx + ry * ry) * mi;
        I01 -= rx * ry * mi; I02 -= rx * rz * mi; I12 -= ry * rz * mi;
      }
      const [w0, w1, w2] = solve3([I00, I01, I02, I01, I11, I12, I02, I12, I22], [L0_, L1, L2]);
      for (let i = 0; i < n; i++) {
        const b = i * 3, rx = X[b] - xc0, ry = X[b + 1] - xc1, rz = X[b + 2] - xc2;
        V[b] += kd * (vc0 + w1 * rz - w2 * ry - V[b]);
        V[b + 1] += kd * (vc1 + w2 * rx - w0 * rz - V[b + 1]);
        V[b + 2] += kd * (vc2 + w0 * ry - w1 * rx - V[b + 2]);
      }
    }

    // ---- baking: one snapshot per frame, forward only. frames[k] is frame base + k: a film keeps
    // them all (base stays 0); live keeps the latest two
    const frames = [], stats = [], hands = [], follow = [];
    let ema = null, base = 0, live = null;
    const kEma = 1 - Math.exp(-1 / (o.fps * Math.max(1e-3, o.camera.lag || 0.8)));
    const snap = (hand) => {
      frames.push(new Float32Array(X));
      // the camera's idea of where the slice is: its centroid, smoothed forward in time
      let gx = 0, gz = 0;
      for (let i = 0; i < n; i++) { gx += X[i * 3] * M[i]; gz += X[i * 3 + 2] * M[i]; }
      gx /= vol0; gz /= vol0;
      ema = ema ? [ema[0] + (gx - ema[0]) * kEma, ema[1] + (gz - ema[1]) * kEma] : [gx, gz];
      follow.push(ema);
      let v = 0, minr = Infinity;
      for (let t = 0; t < m; t++) { const tv = tetVol(X, TT, t); v += tv; minr = Math.min(minr, tv / restVol[t]); }
      let ke = 0, pen = 0;
      for (let i = 0; i < n; i++) { ke += 0.5 * M[i] * (V[i * 3] ** 2 + V[i * 3 + 1] ** 2 + V[i * 3 + 2] ** 2); pen = Math.max(pen, -X[i * 3 + 1]); }
      stats.push({ volume: v / vol0, ke, minTet: minr, pen, impact: impact / vol0 });
      impact = 0;
      hands.push(hand);
      while (live && frames.length > 2) { frames.shift(); stats.shift(); hands.shift(); follow.shift(); base++; }
    };
    snap(null);
    const clock = typeof performance !== 'undefined' ? () => performance.now() : () => Date.now();
    function bakeTo(t) {
      const want = Math.min(Math.ceil(t * o.fps + 1e-6) + (live ? 0 : 1), 1e6);
      let budget = live ? live.catchUp : Infinity;
      const t0 = clock();
      while (base + frames.length <= want && budget-- > 0) {
        let hand = null;
        for (let s = 0; s < o.substeps; s++) hand = substep() || hand;
        snap(hand);
        J.perf.simFrames++;
      }
      J.perf.physMs += clock() - t0;
    }
    const at_ = (t) => {
      // live: the latest frame, always -- only draw() moves the clock on (advance), so the
      // readouts a film draws beside it cannot spend the frame's physics budget twice
      if (live) return { i: base + frames.length - 1, a: 0 };
      bakeTo(t);
      const f = Math.max(0, t * o.fps), i = Math.floor(f + 1e-6);
      return { i, a: f - i < 1e-6 ? 0 : f - i };
    };
    function positions(t, out) {
      const { i, a } = at_(t), A = frames[i - base], B = frames[i + 1 - base] || A;
      if (!out) out = new Float64Array(n * 3);
      for (let k = 0; k < n * 3; k++) out[k] = A[k] + (B[k] - A[k]) * a;
      return out;
    }

    // ---- readouts, in illustrative units
    const cm = o.scale.cm, massG = vol0 * cm ** 3 * o.scale.gcc;
    const spec_ = {
      o, preset: P, n, tets: m, edges: ne, surfaceVerts: surf.pos.length / 3, seeds: incl.kind.filter((k) => k === 0).length / (9 * 12),
      bakeTo,
      positions,
      stats(t) {
        const { i } = at_(t), s = stats[i - base];
        // KE: sim mass fraction x real mass (kg), sim velocity x cm/100 (m/s) -> microjoules
        return { mass: massG, volume: s.volume, kinetic: (s.ke / vol0) * (massG / 1000) * (cm / 100) ** 2 * 1e6, minTet: s.minTet, pen: s.pen, keSim: s.ke };
      },
      hand(t) { const { i } = at_(t); return hands[i - base]; },
      /** where the camera looks, x and z: the smoothed centroid (pure function of t) */
      follow(t) { const { i, a } = at_(t), A = follow[i - base], B = follow[i + 1 - base] || A; return [A[0] + (B[0] - A[0]) * a, A[1] + (B[1] - A[1]) * a]; },
      frameCount: () => base + frames.length,
      /* ---- live */
      /** step from the wall clock from now on (SK.LIVE.now()), keeping only the latest frame;
       *  at most `catchUp` frames are simulated per drawn frame */
      /** live: simulate toward t, at most catchUp frames */
      advance: (t) => bakeTo(t),
      goLive(opt = {}) {
        live = { catchUp: opt.catchUp || o.live.catchUp || 2 };
        const k = frames.length - 1;
        for (const arr of [frames, stats, hands, follow]) arr.splice(0, k);
        base += k;
      },
      isLive: () => !!live,
      touched: () => touched,
      simTime: () => step * dt,
      /** take hold where a ray (o, d: world, d unit) meets the slice: the particle nearest the eye
       *  within 0.1 of the ray, and everything within `radius` of it. false when it misses. */
      grab(o3, d3, radius = 0.17) {
        let best = -1, bestT = Infinity;
        for (let i = 0; i < n; i++) {
          const px = X[i * 3] - o3[0], py = X[i * 3 + 1] - o3[1], pz = X[i * 3 + 2] - o3[2];
          const tt = px * d3[0] + py * d3[1] + pz * d3[2];
          if (tt <= 0) continue;
          const qx = px - d3[0] * tt, qy = py - d3[1] * tt, qz = pz - d3[2] * tt;
          if (qx * qx + qy * qy + qz * qz < 0.01 && tt < bestT) { bestT = tt; best = i; }
        }
        if (best < 0) return false;
        const gp = [X[best * 3], X[best * 3 + 1], X[best * 3 + 2]], sel = [], wt = [];
        let sw = 0, c = [0, 0, 0], top = -Infinity;
        for (let i = 0; i < n; i++) {
          const d = Math.hypot(X[i * 3] - gp[0], X[i * 3 + 1] - gp[1], X[i * 3 + 2] - gp[2]);
          if (d >= radius) continue;
          const f = 1 - clamp((d - radius * 0.35) / (radius * 0.65)), k = f * f * (3 - 2 * f);
          sel.push(i); wt.push(k); sw += k;
          c[0] += X[i * 3] * k; c[1] += X[i * 3 + 1] * k; c[2] += X[i * 3 + 2] * k;
          top = Math.max(top, X[i * 3 + 1]);
        }
        c = c.map((v) => v / sw);
        const anchor = new Float64Array(sel.length * 3);
        sel.forEach((i, q) => anchor.set([X[i * 3] - c[0], X[i * 3 + 1] - c[1], X[i * 3 + 2] - c[2]], q * 3));
        const hit0 = [o3[0] + d3[0] * bestT, o3[1] + d3[1] * bestT, o3[2] + d3[2] * bestT];
        user = { sel, wt, c, anchor, D: [0, 0, 0], hit0, nrm: d3.slice(), t0: step * dt, lift: top - c[1] };
        touched = true;
        return true;
      },
      /** move the hand to where a ray meets the plane it took hold in (facing the eye) */
      drag(o3, d3) {
        if (!user) return;
        const u = user, den = d3[0] * u.nrm[0] + d3[1] * u.nrm[1] + d3[2] * u.nrm[2];
        if (Math.abs(den) < 1e-6) return;
        const k = ((u.hit0[0] - o3[0]) * u.nrm[0] + (u.hit0[1] - o3[1]) * u.nrm[1] + (u.hit0[2] - o3[2]) * u.nrm[2]) / den;
        u.D = [o3[0] + d3[0] * k - u.hit0[0], Math.max(-u.c[1], o3[1] + d3[1] * k - u.hit0[1]), o3[2] + d3[2] * k - u.hit0[2]];
      },
      release() { user = null; },
      holding: () => !!user,
      nudgeNow(amount = 1) { pendingNudge += amount; },
      /** back to the first frame: the slice drops again (the script stays off once touched) */
      reset() {
        X.set(X0); V.fill(0); step = 0; impact = 0; ema = null; user = null;
        for (const a of acts) a.st = null;
        for (const arr of [frames, stats, hands, follow]) arr.length = 0;
        base = 0;
        snap(null);
      },
      /** where a named point of the slice is now (the particle nearest it at rest), world */
      pointNow(name) {
        const rp = restPoint(name);
        let best = 0, bd = Infinity;
        for (let i = 0; i < n; i++) {
          const d = Math.hypot(mesh.rest[i * 3] - rp[0], mesh.rest[i * 3 + 1] - rp[1], mesh.rest[i * 3 + 2] - rp[2]);
          if (d < bd) { bd = d; best = i; }
        }
        return [X[best * 3], X[best * 3 + 1], X[best * 3 + 2]];
      },
      /** what happened, for the sound: grab / release / poke from the script, land from the
       *  simulation (a frame where the floor stopped a lot of downward motion, a local peak at
       *  least 0.18 s after the last). Bakes to `until` (default: the film's duration). */
      events(until) {
        if (live) return []; // a live run has no history to listen to
        const end = until ?? ((SK._film && SK._film.duration) || 10);
        bakeTo(end);
        const ev = [];
        for (const a of acts) {
          if (a.t > end) continue;
          if (a.kind === 'grab') ev.push({ t: a.t, kind: 'grab', at: a.grab }, { t: a.t + a.dur, kind: 'release', at: a.grab });
          else if (a.kind === 'poke') ev.push({ t: a.t, kind: 'poke', at: a.poke, dur: a.dur });
          else ev.push({ t: a.t, kind: 'nudge' });
        }
        // a slice at rest still presses on the floor every step, so a landing is a peak well over
        // the quietest frame of the last 0.3 s -- and none while the hand holds or presses it
        const nf = Math.floor(end * o.fps), thr = o.landing ?? 0.1, win = Math.round(0.3 * o.fps);
        const held = (t) => acts.some((a) => a.kind !== 'nudge' && t >= a.t && t <= a.t + a.dur + 0.05);
        let last = -1;
        for (let i = 1; i < nf; i++) {
          const e = stats[i].impact;
          if (e < stats[i - 1].impact || e < (stats[i + 1] ? stats[i + 1].impact : 0)) continue;
          let base = e;
          for (let k = Math.max(0, i - win); k < i; k++) base = Math.min(base, stats[k].impact);
          const t = i / o.fps, x = e - base;
          if (x < thr || e < base * 1.8 || held(t) || (last >= 0 && t - last < 0.18)) continue;
          ev.push({ t, kind: 'land', energy: x }); last = t;
        }
        return ev.sort((a, b) => a.t - b.t);
      },
      /** the events as sketch-audio cues (a film returns them from SK.film({ sounds })): a plop
       *  per landing, louder the harder it hit, a squish when the hand takes hold or presses,
       *  a rising one when it lets go. Panned to where it happens on screen. */
      sounds(opt = {}) {
        const cues = [], P = typeof document !== 'undefined' ? painterOf(spec_) : null;
        const panAt = (t) => {
          if (!P || !P.ok) return 0;
          const f = spec_.follow(t), x = P.project([f[0], 0.1, f[1]], t)[0];
          return Math.max(-0.6, Math.min(0.6, (x / SK.W) * 2 - 1)) * 0.8;
        };
        for (const e of spec_.events(opt.until)) {
          const t = +e.t.toFixed(3), pan = +panAt(e.t).toFixed(2);
          if (e.kind === 'land') {
            const db = Math.max(-36, Math.min(-14, -22 + 7 * Math.log10(e.energy / 0.3)));
            cues.push({ t, fx: 'plop', db: +db.toFixed(1), pan, args: { f0: 230, f1: 80, sec: 0.4 } });
          } else if (e.kind === 'grab') cues.push({ t, fx: 'squish', db: -25, pan, args: { sec: 0.32, f0: 850, f1: 260 } });
          else if (e.kind === 'release') cues.push({ t, fx: 'squish', db: -24, pan, args: { sec: 0.26, f0: 320, f1: 1250 } });
          else if (e.kind === 'poke') cues.push({ t: +(e.t + e.dur * 0.3).toFixed(3), fx: 'squish', db: -24, pan, args: { sec: 0.4, f0: 700, f1: 200, q: 6 } });
        }
        return cues;
      },
      restPoint,
      _mesh: { mesh, surf, incl, surfE, inclE, toWorld, R, T },
    };
    spec_.draw = function (t) { return draw(spec_, t); };
    spec_.project = function (p) { return painterOf(spec_).project(p, t_last(spec_)); };
    return spec_;
  };
    function solve3(A, b) {
    const [a, b1, c, d, e, f, g, h, i] = A;
    const det = a * (e * i - f * h) - b1 * (d * i - f * g) + c * (d * h - e * g);
    if (Math.abs(det) < 1e-18) return [0, 0, 0];
    const inv = [e * i - f * h, c * h - b1 * i, b1 * f - c * e, f * g - d * i, a * i - c * g, c * d - a * f, d * h - e * g, b1 * g - a * h, a * e - b1 * d];
    return [0, 1, 2].map((r) => (inv[r * 3] * b[0] + inv[r * 3 + 1] * b[1] + inv[r * 3 + 2] * b[2]) / det);
  }

  /** what the live test reports: milliseconds spent simulating and drawing, frames simulated */
  J.perf = { physMs: 0, drawMs: 0, simFrames: 0 };

  /* ================================================================ drawing (browser only) */
  const RENDERING = typeof location !== 'undefined' && /[?&](render|export|encode|stills)=/.test(location.search);
  const painters = new WeakMap();
  const lastT = new WeakMap();
  const t_last = (s) => lastT.get(s) || 0;
  function painterOf(s) {
    let p = painters.get(s);
    if (!p) { p = new Painter(s); painters.set(s, p); }
    return p;
  }
  function draw(s, t) {
    if (SK.LIVE && !s.isLive()) goLive(s);
    const t0 = performance.now();
    if (s.isLive()) { t = SK.LIVE.now(); s.advance(t); } // the physics runs on the wall clock, whatever the film's type shows
    lastT.set(s, t);
    const ctx = SK.ctx(), W = SK.W, H = SK.H;
    const p = painterOf(s);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (!p.ok) {
      ctx.fillStyle = '#e8e4dd'; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#2a2521'; ctx.font = '600 40px system-ui, sans-serif'; ctx.textAlign = 'center';
      ctx.fillText('This film draws its jelly with WebGL2, which this browser did not provide.', W / 2, H / 2);
      ctx.restore(); return;
    }
    p.render(t);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(p.canvas, 0, 0, W, H);
    if (s.o.cursor) cursor(ctx, s, p, t);
    ctx.restore();
    J.perf.drawMs += performance.now() - t0;
  }
  /* live: the pointer is a hand. The player hands every module in SK.pointers its pointer events
     in film pixels ('down' returns whether it took hold), and SK.liveControls its buttons. */
  function goLive(s) {
    s.goLive(SK.LIVE.catchUp ? { catchUp: SK.LIVE.catchUp } : {});
    const p = painterOf(s), now = () => SK.LIVE.now();
    (SK.pointers = SK.pointers || []).push((kind, x, y) => {
      if (kind === 'down') { const r = p.ray(x, y, now()); return s.grab(r.o, r.d); }
      if (kind === 'move') { if (s.holding()) { const r = p.ray(x, y, now()); s.drag(r.o, r.d); } return s.holding(); }
      if (kind === 'up') s.release();
      return false;
    });
    SK.liveControls = {
      nudge: () => s.nudgeNow(1.1),
      reset: () => s.reset(),
      simTime: () => s.simTime(),
      /** where to press to take hold of a named point: film pixels */
      handle: (name) => p.project(s.pointNow(name), now()),
      size: () => [p.W, p.H],
      fps: () => s.o.fps,
    };
  }
  /* a touch indicator where the hand is: a soft white disc that tightens while it holds */
  function cursor(ctx, s, p, t) {
    const h = s.hand(t);
    if (!h) return;
    const [x, y] = p.project(h.p, t);
    const inA = clamp(h.u / 0.12), outA = clamp((h.dur - h.u) / 0.12), a = Math.min(inA, outA);
    const r = 17 - 4 * (h.kind === 'grab' ? inA : h.press);
    ctx.save();
    ctx.globalAlpha = 0.9 * a;
    ctx.shadowColor = 'rgba(40,20,10,.35)'; ctx.shadowBlur = 14; ctx.shadowOffsetY = 4;
    ctx.fillStyle = 'rgba(255,255,255,.92)';
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    ctx.shadowColor = 'transparent';
    ctx.lineWidth = 2; ctx.strokeStyle = 'rgba(42,37,33,.55)'; ctx.stroke();
    ctx.restore();
  }

  /* ------------------------------------------------------------ WebGL2 */
  const GLSL_COMMON = `#version 300 es
precision highp float;
uniform vec3 uCam, uKey, uFill, uKeyCol, uFillCol, uAmb, uFloor;
vec3 envMap(vec3 d) {
  // the studio: a warm grey room, a big softbox (the key) and a tall strip (the fill)
  // (dark walls and ceiling -- the black flags a product photographer hangs -- so a reflection
  // is the softbox's window and not a milky veil over the colour)
  vec3 room = mix(uFloor * 0.45, vec3(0.3, 0.3, 0.29), smoothstep(-0.2, 0.25, d.y));
  room = mix(room, vec3(0.22, 0.22, 0.215), smoothstep(0.3, 1.0, d.y));
  vec3 kx = normalize(cross(uKey, vec3(0.0, 1.0, 0.0))), ky = cross(kx, uKey);
  float c = dot(d, uKey);
  if (c > 0.0) {
    vec2 q = vec2(dot(d, kx), dot(d, ky)) / c;
    float box = 1.0 - smoothstep(0.0, 0.05, max(abs(q.x) - 0.5, abs(q.y) - 0.32));
    room += uKeyCol * box * 9.0;
  }
  vec3 fx = normalize(cross(uFill, vec3(0.0, 1.0, 0.0))), fy = cross(fx, uFill);
  float cf = dot(d, uFill);
  if (cf > 0.0) {
    vec2 q = vec2(dot(d, fx), dot(d, fy)) / cf;
    float strip = 1.0 - smoothstep(0.0, 0.04, max(abs(q.x) - 0.08, abs(q.y) - 0.7));
    room += uFillCol * strip * 4.0;
  }
  return room;
}
vec3 tone(vec3 c) { // mid-tones exact, highlights rolled off
  vec3 k = vec3(0.78);
  vec3 hi = k + (1.0 - k) * (1.0 - exp(-(c - k) / (1.0 - k)));
  c = mix(c, hi, step(k, c));
  return pow(clamp(c, 0.0, 1.0), vec3(1.0 / 2.2));
}
float hash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vnoise(vec3 x) {
  vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x), mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x), mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float fbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s; }
`;

  const VS_MESH = `#version 300 es
in vec3 aPos; in vec3 aNrm; in vec3 aRest;
uniform mat4 uVP;
out vec3 vW; out vec3 vN; out vec3 vR;
void main() { vW = aPos; vN = aNrm; vR = aRest; gl_Position = uVP * vec4(aPos, 1.0); }`;

  const FS_DEPTH = `#version 300 es
precision highp float;
void main() {}`;

  const VS_SHADOW = `#version 300 es
in vec3 aPos;
uniform vec4 uRect; uniform vec3 uDir;
out float vH;
void main() {
  vec2 q = aPos.xz - uDir.xz * (aPos.y / uDir.y);
  vec2 uv = (q - uRect.xy) * uRect.zw;
  vH = aPos.y;
  gl_Position = vec4(uv * 2.0 - 1.0, 0.0, 1.0);
}`;
  const FS_SHADOW = `#version 300 es
precision highp float;
in float vH; uniform float uFall; out vec4 o;
void main() { float v = exp(-max(vH, 0.0) * uFall); o = vec4(v, v, v, 1.0); }`;

  const VS_QUAD = `#version 300 es
out vec2 vUv;
void main() { vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); vUv = p; gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }`;
  const FS_BLUR = `#version 300 es
precision highp float;
in vec2 vUv; uniform sampler2D uTex; uniform vec2 uStep; out vec4 o;
void main() {
  float w[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  vec4 s = texture(uTex, vUv) * w[0];
  for (int i = 1; i < 5; i++) { s += texture(uTex, vUv + uStep * float(i)) * w[i]; s += texture(uTex, vUv - uStep * float(i)) * w[i]; }
  o = s;
}`;
  const FS_COPY = GLSL_COMMON + `
in vec2 vUv; uniform sampler2D uTex; out vec4 o;
void main() { o = vec4(tone(texture(uTex, vUv).rgb), 1.0); }`;

  const VS_FLOOR = `#version 300 es
uniform mat4 uVP; uniform vec2 uC;
out vec3 vW;
void main() { vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2) * 2.0 - 1.0; vW = vec3(uC.x + p.x * 40.0, 0.0, uC.y + p.y * 40.0); gl_Position = uVP * vec4(vW, 1.0); }`;
  const FS_FLOOR = GLSL_COMMON + `
in vec3 vW;
uniform sampler2D uContact, uCast; uniform vec4 uCRect, uSRect; uniform vec3 uPool, uTint;
out vec4 o;
float sampleRect(sampler2D t, vec4 r, vec2 p) { vec2 uv = (p - r.xy) * r.zw; if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) return 0.0; return texture(t, uv).r; }
void main() {
  float d = length(vW.xz - uPool.xy);
  float pool = mix(0.84, 1.06, exp(-d * d * uPool.z));
  float ao = sampleRect(uContact, uCRect, vW.xz);
  float sh = sampleRect(uCast, uSRect, vW.xz);
  vec3 c = uFloor * pool;
  c *= 1.0 - 0.72 * ao;
  c *= mix(vec3(1.0), uTint, clamp(sh, 0.0, 1.0) * 0.8);
  o = vec4(c, 1.0);
}`;

  const VS_INCL = `#version 300 es
in vec3 aPos; in vec3 aNrm; in float aKind;
uniform mat4 uVP;
out vec3 vW; out vec3 vN; out float vK;
void main() { vW = aPos; vN = aNrm; vK = aKind; gl_Position = uVP * vec4(aPos, 1.0); }`;
  const FS_INCL = GLSL_COMMON + `
in vec3 vW; in vec3 vN; in float vK;
uniform vec3 uSeed;
out vec4 o;
void main() {
  vec3 N = normalize(vN), V = normalize(uCam - vW);
  if (dot(N, V) < 0.0) N = -N;
  float F = 0.04 + 0.96 * pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 5.0);
  vec3 R = reflect(-V, N);
  if (vK < 0.5) {
    vec3 c = uSeed * (0.35 + 0.9 * max(dot(N, uKey), 0.0)) + envMap(R) * F * 0.18;
    o = vec4(c, 1.0);
  } else { // a bubble: bright, with a darker rim
    float rim = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 1.5);
    o = vec4(mix(vec3(0.95), vec3(0.4), rim) + envMap(R) * 0.2, 1.0);
  }
}`;

  const FS_JELLY = GLSL_COMMON + `
in vec3 vW; in vec3 vN; in vec3 vR;
uniform sampler2D uScene, uSceneDepth, uBackDepth;
uniform mat4 uVP; uniform vec2 uRes; uniform float uNear, uFar;
uniform float uR, uSkinT, uPaleT, uT, uLod;
uniform vec3 uAbsorb, uBody, uPaleAbsorb, uPaleBody, uSkin, uStripe;
uniform float uCloud, uPaleCloud;
out vec4 o;
float lin(float z) { return uNear * uFar / (uFar - z * (uFar - uNear)); }
void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec3 N = normalize(vN), V = normalize(uCam - vW);
  float NdV = dot(N, V);
  if (NdV < 0.02) { N = normalize(N + V * (0.02 - NdV)); NdV = 0.02; }
  float zF = lin(gl_FragCoord.z), zB = lin(texture(uBackDepth, uv).r);
  float dj = clamp(zB - zF, 0.0, uT * 2.5); // the jelly's own depth here

  // which layer this point of the slice was cut from (rest space, so it deforms with it)
  float rr = length(vR.xz);
  float skin = smoothstep(uR - uSkinT - 0.005, uR - uSkinT + 0.005, rr);
  float pale = smoothstep(uR - uSkinT - uPaleT - 0.02, uR - uSkinT - uPaleT + 0.01, rr) * (1.0 - skin);
  float flesh = clamp(1.0 - skin - pale, 0.0, 1.0);

  // jelly: what is behind, refracted and absorbed, plus light scattered back out
  // the flesh is not glass: a little granular density, like the cells of the fruit
  float grain = fbm(vR * 11.0) * 0.6 + fbm(vR * 46.0) * 0.4;
  vec3 sigA = (flesh * uAbsorb + pale * uPaleAbsorb) * (0.72 + 0.56 * grain);
  // the pale layer runs pink-white by the flesh to green-white by the skin
  float pg = smoothstep(uR - uSkinT - uPaleT, uR - uSkinT, rr);
  vec3 paleBody = mix(uPaleBody * vec3(1.0, 0.93, 0.9), uPaleBody * vec3(0.82, 0.95, 0.6), pg);
  vec3 body = flesh * uBody + pale * paleBody;
  float cloud = flesh * uCloud + pale * uPaleCloud;
  vec3 Rr = refract(-V, N, 1.0 / 1.36);
  vec4 cp = uVP * vec4(vW + Rr * dj * 0.9, 1.0);
  vec2 ruv = clamp(cp.xy / cp.w * 0.5 + 0.5, vec2(0.001), vec2(0.999));
  // the path length to whatever is SEEN there -- a seed, or the floor through the whole slice.
  // Measured where the colour is read, or a seed's edge shows the floor through no jelly at all
  float d = clamp(min(zB, lin(texture(uSceneDepth, ruv).r)) - zF, 0.0, uT * 2.5);
  // what is behind blurs with depth: a seed just under the skin is sharp, one deep inside is soft
  vec3 bg = textureLod(uScene, ruv, clamp(d * uLod, 0.0, 6.0)).rgb;
  vec3 Tr = exp(-sigA * d);
  vec3 seen = bg * Tr * exp(-cloud * d);
  float wrap = clamp(dot(N, uKey) * 0.5 + 0.5, 0.0, 1.0);
  vec3 lightIn = uAmb + uKeyCol * wrap * 0.9 + uFillCol * clamp(dot(N, uFill) * 0.5 + 0.5, 0.0, 1.0) * 0.25;
  // light scattered back out by the body, itself reddened by the path it took
  vec3 scat = body * (1.0 - exp(-cloud * d)) * mix(vec3(1.0), Tr, 0.5) * lightIn * 1.25;
  // key light leaking through the thin parts toward the eye
  float thin = exp(-d * 11.0);
  vec3 through = mix(body, vec3(body.r, body.r * 0.45, body.r * 0.4), 0.5) * uKeyCol * thin * pow(clamp(dot(-N, uKey) * 0.5 + 0.6, 0.0, 1.0), 2.0) * 1.2;
  vec3 jel = seen + scat + through;

  // the skin: opaque, striped, glossy
  float ang = atan(vR.x, vR.z);
  float sn = ang * 34.0 + (fbm(vec3(ang * 7.0, vR.y * 5.0, 3.1)) - 0.5) * 6.0 + sin(vR.y * 22.0 + ang * 9.0) * 0.45;
  float edge = (fbm(vec3(ang * 60.0, vR.y * 40.0, 7.7)) - 0.5) * 0.9; // feathered, torn edges
  float st = smoothstep(0.5, 0.6, 0.5 + 0.5 * sin(sn) + edge);
  vec3 skinAlb = mix(uSkin, uStripe, st) * (0.85 + 0.3 * fbm(vR * 90.0));
  skinAlb = mix(skinAlb, uSkin * 2.6 + vec3(0.04, 0.07, 0.0), (1.0 - smoothstep(uR - uSkinT, uR - uSkinT + 0.01, rr)) * 0.75);
  vec3 skinCol = skinAlb * (uAmb * 1.1 + uKeyCol * max(dot(N, uKey), 0.0) * 1.1 + uFillCol * max(dot(N, uFill), 0.0) * 0.35);

  // gloss over everything: the studio in Fresnel, plus a sharp key sparkle
  float F = 0.035 + 0.965 * pow(1.0 - NdV, 5.0);
  vec3 R = reflect(-V, N);
  vec3 spec = envMap(R) * F;
  vec3 H = normalize(uKey + V);
  float a2 = 0.0036, nh = max(dot(N, H), 0.0), den = nh * nh * (a2 - 1.0) + 1.0;
  spec += uKeyCol * (a2 / (3.14159 * den * den)) * F * max(dot(N, uKey), 0.0) * 0.06;
  vec3 c = mix(jel, skinCol, skin) * (1.0 - F) + spec;
  o = vec4(tone(c), 1.0);
}`;

  function Painter(s) {
    this.s = s;
    const ss = (SK.LIVE && SK.LIVE.ss) || s.o.ss || (RENDERING ? 2 : 1);
    const W = Math.round(SK.W * ss), H = Math.round(SK.H * ss);
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const gl = cv.getContext('webgl2', { antialias: true, alpha: false, premultipliedAlpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    this.canvas = cv; this.gl = gl; this.W = W; this.H = H; this.ok = !!gl;
    if (!gl) return;
    const half = gl.getExtension('EXT_color_buffer_float') ? gl.RGBA16F : gl.RGBA8;
    const prog = (vs, fs) => {
      const p = gl.createProgram();
      for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
        const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh);
        if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error('jelly shader: ' + gl.getShaderInfoLog(sh));
        gl.attachShader(p, sh);
      }
      gl.bindAttribLocation(p, 0, 'aPos'); gl.bindAttribLocation(p, 1, 'aNrm'); gl.bindAttribLocation(p, 2, 'aRest'); gl.bindAttribLocation(p, 2, 'aKind');
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error('jelly program: ' + gl.getProgramInfoLog(p));
      const u = {}, nu = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
      for (let i = 0; i < nu; i++) { const info = gl.getActiveUniform(p, i); u[info.name.replace(/\[0\]$/, '')] = gl.getUniformLocation(p, info.name); }
      return { p, u };
    };
    this.P = {
      depth: prog(VS_MESH, FS_DEPTH), jelly: prog(VS_MESH, FS_JELLY), shadow: prog(VS_SHADOW, FS_SHADOW),
      blur: prog(VS_QUAD, FS_BLUR), copy: prog(VS_QUAD, FS_COPY), floor: prog(VS_FLOOR, FS_FLOOR), incl: prog(VS_INCL, FS_INCL),
    };
    const tex = (w, h, ifmt, fmt, type, filter) => {
      const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texImage2D(gl.TEXTURE_2D, 0, ifmt, w, h, 0, fmt, type, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      return t;
    };
    const fbo = (color, depth) => {
      const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f);
      if (color) gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, color, 0);
      if (depth) gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, depth, 0);
      gl.drawBuffers(color ? [gl.COLOR_ATTACHMENT0] : [gl.NONE]); gl.readBuffer(gl.NONE);
      return f;
    };
    const fp = half === gl.RGBA16F ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE;
    this.sceneTex = tex(W, H, half, gl.RGBA, fp, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.generateMipmap(gl.TEXTURE_2D);
    this.sceneDepth = tex(W, H, gl.DEPTH_COMPONENT24, gl.DEPTH_COMPONENT, gl.UNSIGNED_INT, gl.NEAREST);
    this.sceneFbo = fbo(this.sceneTex, this.sceneDepth);
    this.backDepth = tex(W, H, gl.DEPTH_COMPONENT24, gl.DEPTH_COMPONENT, gl.UNSIGNED_INT, gl.NEAREST);
    this.backFbo = fbo(null, this.backDepth);
    this.sh = {};
    for (const [k, size] of [['contact', 512], ['cast', 256]]) {
      const a = tex(size, size, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, gl.LINEAR), b = tex(size, size, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, gl.LINEAR);
      this.sh[k] = { size, a, b, fa: fbo(a, null), fb: fbo(b, null) };
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);

    // geometry
    const M = s._mesh;
    const buf = (data, target = gl.ARRAY_BUFFER, usage = gl.STATIC_DRAW) => { const b = gl.createBuffer(); gl.bindBuffer(target, b); gl.bufferData(target, data, usage); return b; };
    const restF = (P) => new Float32Array(P);
    this.surf = { n: M.surf.pos.length / 3, tri: M.surf.tri, E: M.surfE, pos: new Float32Array(M.surf.pos.length), nrm: new Float32Array(M.surf.pos.length) };
    this.incl = { n: M.incl.pos.length / 3, tri: M.incl.tri, E: M.inclE, pos: new Float32Array(M.incl.pos.length), nrm: new Float32Array(M.incl.pos.length) };
    for (const [g, extra] of [[this.surf, restF(M.surf.pos)], [this.incl, M.incl.kind]]) {
      g.vao = gl.createVertexArray(); gl.bindVertexArray(g.vao);
      g.bp = buf(g.pos, gl.ARRAY_BUFFER, gl.DYNAMIC_DRAW); gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
      g.bn = buf(g.nrm, gl.ARRAY_BUFFER, gl.DYNAMIC_DRAW); gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
      buf(extra); gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, g === this.surf ? 3 : 1, gl.FLOAT, false, 0, 0);
      buf(g.tri, gl.ELEMENT_ARRAY_BUFFER); g.count = g.tri.length;
    }
    gl.bindVertexArray(null);
    this.empty = gl.createVertexArray();
    this.X = new Float64Array(s.n * 3);
    this.cam = null;
  }
  Painter.prototype.camera = function (t) {
    const s = this.s, c = s.o.camera, T = s._mesh.T;
    const dur = (SK._film && SK._film.duration) || 10;
    const az = ((c.azim + (c.orbit || 0) * Math.min(1, t / dur)) * Math.PI) / 180, el = (c.elev * Math.PI) / 180;
    const base = c.target || [s.o.pose.at[0], T * 0.4, s.o.pose.at[2]], f0 = s.follow(0), ft = s.follow(t), k = c.follow ?? 0;
    const tg = [base[0] + (ft[0] - f0[0]) * k, base[1], base[2] + (ft[1] - f0[1]) * k];
    const eye = [tg[0] + Math.sin(az) * Math.cos(el) * c.dist, tg[1] + Math.sin(el) * c.dist, tg[2] + Math.cos(az) * Math.cos(el) * c.dist];
    const near = 0.1, far = 60, aspect = SK.W / SK.H, f = 1 / Math.tan(((c.fov * Math.PI) / 180) / 2);
    const V = lookAt(eye, tg, [0, 1, 0]);
    const Pm = [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, (2 * far * near) / (near - far), 0];
    // lens shift: slide the picture without changing the perspective
    Pm[8] = -(c.shift?.[0] || 0) * 1; Pm[9] = -(c.shift?.[1] || 0) * 1;
    return { eye, VP: mul4(Pm, V), near, far };
  };
  /** the ray through a film pixel: origin at the eye, unit direction, world */
  Painter.prototype.ray = function (px, py, t) {
    const { VP } = this.camera(t), inv = invert4(VP);
    const nx = (px / SK.W) * 2 - 1, ny = 1 - (py / SK.H) * 2;
    const un = (z) => {
      const x = inv[0] * nx + inv[4] * ny + inv[8] * z + inv[12], y = inv[1] * nx + inv[5] * ny + inv[9] * z + inv[13];
      const zz = inv[2] * nx + inv[6] * ny + inv[10] * z + inv[14], w = inv[3] * nx + inv[7] * ny + inv[11] * z + inv[15];
      return [x / w, y / w, zz / w];
    };
    const a = un(-1), b = un(1), d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], l = Math.hypot(...d);
    return { o: a, d: d.map((v) => v / l) };
  };
  Painter.prototype.project = function (p, t) {
    const { VP } = this.camera(t);
    const x = VP[0] * p[0] + VP[4] * p[1] + VP[8] * p[2] + VP[12], y = VP[1] * p[0] + VP[5] * p[1] + VP[9] * p[2] + VP[13], w = VP[3] * p[0] + VP[7] * p[1] + VP[11] * p[2] + VP[15];
    return [((x / w) * 0.5 + 0.5) * SK.W, (1 - ((y / w) * 0.5 + 0.5)) * SK.H];
  };
  function deform(g, X) {
    const { E, pos, nrm, tri, n } = g, T = g.tetIdx;
    for (let v = 0; v < n; v++) {
      const t = E.tet[v], w0 = E.w[v * 4], w1 = E.w[v * 4 + 1], w2 = E.w[v * 4 + 2], w3 = E.w[v * 4 + 3];
      const a = T[t * 4] * 3, b = T[t * 4 + 1] * 3, c = T[t * 4 + 2] * 3, d = T[t * 4 + 3] * 3;
      pos[v * 3] = w0 * X[a] + w1 * X[b] + w2 * X[c] + w3 * X[d];
      pos[v * 3 + 1] = Math.max(0, w0 * X[a + 1] + w1 * X[b + 1] + w2 * X[c + 1] + w3 * X[d + 1]);
      pos[v * 3 + 2] = w0 * X[a + 2] + w1 * X[b + 2] + w2 * X[c + 2] + w3 * X[d + 2];
    }
    nrm.fill(0);
    for (let q = 0; q < tri.length; q += 3) {
      const a = tri[q] * 3, b = tri[q + 1] * 3, c = tri[q + 2] * 3;
      const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
      const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      for (const k of [a, b, c]) { nrm[k] += nx; nrm[k + 1] += ny; nrm[k + 2] += nz; }
    }
    for (let v = 0; v < n * 3; v += 3) { const l = Math.hypot(nrm[v], nrm[v + 1], nrm[v + 2]) || 1; nrm[v] /= l; nrm[v + 1] /= l; nrm[v + 2] /= l; }
  }
  Painter.prototype.render = function (t) {
    const gl = this.gl, s = this.s, P = this.P, pr = s.preset, lt = s.o.light;
    s.positions(t, this.X);
    this.surf.tetIdx = this.incl.tetIdx = s._mesh.mesh.tets;
    for (const g of [this.surf, this.incl]) {
      if (!g.n) continue;
      deform(g, this.X);
      gl.bindBuffer(gl.ARRAY_BUFFER, g.bp); gl.bufferSubData(gl.ARRAY_BUFFER, 0, g.pos);
      gl.bindBuffer(gl.ARRAY_BUFFER, g.bn); gl.bufferSubData(gl.ARRAY_BUFFER, 0, g.nrm);
    }
    const cam = this.camera(t);
    const nrm = (v) => { const l = Math.hypot(...v); return v.map((x) => x / l); };
    // the light moves with the camera's orbit, as a studio's would be fixed to the set: it is not
    const key = nrm(lt.key), fill = nrm(lt.fill);
    // centre of the shadow maps: the slice's centroid
    let cx = 0, cz = 0; const n = s.n;
    for (let i = 0; i < n; i++) { cx += this.X[i * 3]; cz += this.X[i * 3 + 2]; }
    cx /= n; cz /= n;
    const setCommon = (u) => {
      gl.uniform3fv(u.uCam, cam.eye); gl.uniform3fv(u.uKey, key); gl.uniform3fv(u.uFill, fill);
      gl.uniform3fv(u.uKeyCol, [1.0, 0.97, 0.93]); gl.uniform3fv(u.uFillCol, [0.9, 0.93, 1.0]); gl.uniform3fv(u.uAmb, [0.34, 0.33, 0.32]);
      gl.uniform3fv(u.uFloor, lt.floor);
    };
    const vp = new Float32Array(cam.VP);

    // 1. shadows: straight down (contact) and along the key (cast), max-blended then blurred
    gl.disable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE); gl.enable(gl.BLEND); gl.blendEquation(gl.MAX); gl.blendFunc(gl.ONE, gl.ONE);
    const rects = { contact: [cx - 1.6, cz - 1.6, 1 / 3.2, 1 / 3.2], cast: [cx - 2.6, cz - 2.6, 1 / 5.2, 1 / 5.2] };
    for (const [k, dir, fall] of [['contact', [0, 1, 0], 1 / 0.07], ['cast', key, 1 / 1.6]]) {
      const S = this.sh[k];
      gl.bindFramebuffer(gl.FRAMEBUFFER, S.fa); gl.viewport(0, 0, S.size, S.size); gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(P.shadow.p);
      const r = rects[k];
      gl.uniform4f(P.shadow.u.uRect, r[0], r[1], r[2], r[3]); gl.uniform3fv(P.shadow.u.uDir, dir); gl.uniform1f(P.shadow.u.uFall, fall);
      gl.bindVertexArray(this.surf.vao); gl.drawElements(gl.TRIANGLES, this.surf.count, gl.UNSIGNED_INT, 0);
    }
    gl.disable(gl.BLEND); gl.blendEquation(gl.FUNC_ADD);
    gl.useProgram(P.blur.p); gl.bindVertexArray(this.empty); gl.activeTexture(gl.TEXTURE0); gl.uniform1i(P.blur.u.uTex, 0);
    for (const [k, px, iters] of [['contact', 1.6, 2], ['cast', 2.2, 3]]) {
      const S = this.sh[k];
      gl.viewport(0, 0, S.size, S.size);
      for (let i = 0; i < iters; i++) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, S.fb); gl.bindTexture(gl.TEXTURE_2D, S.a); gl.uniform2f(P.blur.u.uStep, px / S.size, 0); gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.bindFramebuffer(gl.FRAMEBUFFER, S.fa); gl.bindTexture(gl.TEXTURE_2D, S.b); gl.uniform2f(P.blur.u.uStep, 0, px / S.size); gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
    }

    // 2. the scene behind the jelly: floor, then seeds and bubbles
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.sceneFbo); gl.viewport(0, 0, this.W, this.H);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true);
    gl.clearColor(0, 0, 0, 1); gl.clearDepth(1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(P.floor.p); setCommon(P.floor.u);
    gl.uniformMatrix4fv(P.floor.u.uVP, false, vp); gl.uniform2f(P.floor.u.uC, cx, cz);
    gl.uniform4fv(P.floor.u.uCRect, rects.contact); gl.uniform4fv(P.floor.u.uSRect, rects.cast);
    gl.uniform3fv(P.floor.u.uPool, [cx - 0.35, cz - 0.25, 0.28]); gl.uniform3fv(P.floor.u.uTint, pr.shadow);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.sh.contact.a); gl.uniform1i(P.floor.u.uContact, 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.sh.cast.a); gl.uniform1i(P.floor.u.uCast, 1);
    gl.bindVertexArray(this.empty); gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (this.incl.n) {
      gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK);
      gl.useProgram(P.incl.p); setCommon(P.incl.u); gl.uniformMatrix4fv(P.incl.u.uVP, false, vp); gl.uniform3fv(P.incl.u.uSeed, pr.seed);
      gl.bindVertexArray(this.incl.vao); gl.drawElements(gl.TRIANGLES, this.incl.count, gl.UNSIGNED_INT, 0);
      gl.disable(gl.CULL_FACE);
    }

    gl.bindTexture(gl.TEXTURE_2D, this.sceneTex); gl.generateMipmap(gl.TEXTURE_2D); gl.bindTexture(gl.TEXTURE_2D, null);

    // 3. the jelly's back faces: how deep it is at every pixel
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.backFbo); gl.clear(gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.CULL_FACE); gl.cullFace(gl.FRONT);
    gl.useProgram(P.depth.p); gl.uniformMatrix4fv(P.depth.u.uVP, false, vp);
    gl.bindVertexArray(this.surf.vao); gl.drawElements(gl.TRIANGLES, this.surf.count, gl.UNSIGNED_INT, 0);

    // 4. the frame: the scene, then the jelly reading it through itself
    gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, this.W, this.H);
    gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE);
    gl.useProgram(P.copy.p); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.sceneTex); gl.uniform1i(P.copy.u.uTex, 0);
    gl.bindVertexArray(this.empty); gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.enable(gl.DEPTH_TEST); gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK);
    if (s.o.debug === 'scene') return; // what the jelly reads through itself, and nothing else
    const J_ = P.jelly, u = J_.u;
    gl.useProgram(J_.p); setCommon(u);
    gl.uniformMatrix4fv(u.uVP, false, vp); gl.uniform2f(u.uRes, this.W, this.H); gl.uniform1f(u.uNear, cam.near); gl.uniform1f(u.uFar, cam.far);
    const M = s._mesh, rind = s.o.rind;
    gl.uniform1f(u.uLod, 12 * (this.W / 1920)); gl.uniform1f(u.uR, M.R); gl.uniform1f(u.uSkinT, rind.skin); gl.uniform1f(u.uPaleT, rind.pale); gl.uniform1f(u.uT, M.T);
    gl.uniform3fv(u.uAbsorb, pr.absorb); gl.uniform3fv(u.uBody, pr.body); gl.uniform1f(u.uCloud, pr.cloud);
    gl.uniform3fv(u.uPaleAbsorb, pr.paleAbsorb); gl.uniform3fv(u.uPaleBody, pr.paleBody); gl.uniform1f(u.uPaleCloud, pr.paleCloud);
    gl.uniform3fv(u.uSkin, pr.skin); gl.uniform3fv(u.uStripe, pr.stripe);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.sceneTex); gl.uniform1i(u.uScene, 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.sceneDepth); gl.uniform1i(u.uSceneDepth, 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, this.backDepth); gl.uniform1i(u.uBackDepth, 2);
    gl.bindVertexArray(this.surf.vao); gl.drawElements(gl.TRIANGLES, this.surf.count, gl.UNSIGNED_INT, 0);
    gl.bindVertexArray(null);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, null);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, null);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, null);
  };
  function lookAt(e, c, up) {
    let z = [e[0] - c[0], e[1] - c[1], e[2] - c[2]]; let l = Math.hypot(...z); z = z.map((v) => v / l);
    let x = cross(up, z); l = Math.hypot(...x); x = x.map((v) => v / l);
    const y = cross(z, x);
    return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
      -(x[0] * e[0] + x[1] * e[1] + x[2] * e[2]), -(y[0] * e[0] + y[1] * e[1] + y[2] * e[2]), -(z[0] * e[0] + z[1] * e[1] + z[2] * e[2]), 1];
  }
  function invert4(m) { // column-major 4x4 inverse (cofactors)
    const [a00, a01, a02, a03, a10, a11, a12, a13, a20, a21, a22, a23, a30, a31, a32, a33] = m;
    const b00 = a00 * a11 - a01 * a10, b01 = a00 * a12 - a02 * a10, b02 = a00 * a13 - a03 * a10, b03 = a01 * a12 - a02 * a11;
    const b04 = a01 * a13 - a03 * a11, b05 = a02 * a13 - a03 * a12, b06 = a20 * a31 - a21 * a30, b07 = a20 * a32 - a22 * a30;
    const b08 = a20 * a33 - a23 * a30, b09 = a21 * a32 - a22 * a31, b10 = a21 * a33 - a23 * a31, b11 = a22 * a33 - a23 * a32;
    const det = 1 / (b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06);
    return [
      (a11 * b11 - a12 * b10 + a13 * b09) * det, (a02 * b10 - a01 * b11 - a03 * b09) * det, (a31 * b05 - a32 * b04 + a33 * b03) * det, (a22 * b04 - a21 * b05 - a23 * b03) * det,
      (a12 * b08 - a10 * b11 - a13 * b07) * det, (a00 * b11 - a02 * b08 + a03 * b07) * det, (a32 * b02 - a30 * b05 - a33 * b01) * det, (a20 * b05 - a22 * b02 + a23 * b01) * det,
      (a10 * b10 - a11 * b08 + a13 * b06) * det, (a01 * b08 - a00 * b10 - a03 * b06) * det, (a30 * b04 - a31 * b02 + a33 * b00) * det, (a21 * b02 - a20 * b04 - a23 * b00) * det,
      (a11 * b07 - a10 * b09 - a12 * b06) * det, (a00 * b09 - a01 * b07 + a02 * b06) * det, (a31 * b01 - a30 * b03 - a32 * b00) * det, (a20 * b03 - a21 * b01 + a22 * b00) * det,
    ];
  }
  function mul4(a, b) { // column-major a*b
    const o = new Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    return o;
  }
})();
