/* sketch/space.js -- a little 3D for motion design (a film opts in: "modules": ["space"]).

   Perspective planes, boxes and flat polygons whose faces are drawn with the ordinary 2D engine,
   so a board of flipping letters, a card, a name block that turns to the next name or a paper
   plane can move in depth while everything printed on them is still SK.txt, SK.card or plain
   canvas calls. Canvas 2D has no projective transform: a face is drawn into an offscreen canvas
   and laid onto its screen quad as a grid of small affine triangles, each clipped a hair wider
   than itself so no seam shows between them.

   Space: x right, y down, z away from the viewer, in the film's world units. The camera
   (SK.view3) looks along +z at a target point, which lands on the middle of the frame; the plane
   through the target facing the camera is drawn at scale 1, so a face at z = 0 with no turn is
   exactly where a 2D drawing of it would be. yaw turns the camera about the vertical, pitch tilts
   it, roll leans it; d is its distance (smaller: stronger perspective).

     SK.view3({ x, y, z, yaw, pitch, roll, d,     the camera for what follows (defaults: the frame's
                zoom, sx, sy })                   middle, no turn, d 1400, zoom 1); the target lands
                                                  on screen at (sx, sy), the frame's middle unless set
     SK.pose3(p, { x, y, z, rx, ry, rz, s })      a local point placed in the world (turned about Z,
                                                  then X, then Y; then moved)
     SK.proj3(p) -> [sx, sy, depth] | null        a world point on screen (null: behind the camera)
     SK.face3(corners, w, h, draw, o)             a w x h face drawn by draw(g, w, h) onto four world
                                                  corners (top-left, top-right, bottom-right,
                                                  bottom-left); false when it faces away.
                                                  o: fill, shade (0..1 dark over it), res, grid,
                                                  cull (true), key
     SK.box3(o)                                   a box: o.x/y/z centre, w/h/d, rx/ry/rz, faces
                                                  {front, back, left, right, top, bottom}: each
                                                  {fill, draw(g, w, h), shade}; o.light, o.ambient
     SK.poly3(points, fill, o)                    a flat polygon, lit like a box face; o.cull, o.light
     SK.fx(fn, { blur, alpha, dx, dy, smear })    fn drawn on its own layer, then laid down blurred
                                                  or smeared along (dx, dy): transitions and depth
     SK.scratch(key, w, h)                        a reusable offscreen canvas

   Every frame is still a pure function of t: the offscreen canvases are scratch paper, cleared
   and redrawn each time they are used.
*/
(function () {
  'use strict';
  const SK = window.SK;
  const clamp = SK.clamp, lerp = SK.lerp;

  const SCRATCH = new Map();
  SK.scratch = function (key, w, h) {
    let c = SCRATCH.get(key);
    if (!c) { c = document.createElement('canvas'); SCRATCH.set(key, c); }
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    return c;
  };

  /* ------------------------------------------------------------ camera */
  const DEF = () => ({ x: SK.W / 2, y: SK.H / 2, z: 0, yaw: 0, pitch: 0, roll: 0, d: 1400, zoom: 1, sx: SK.W / 2, sy: SK.H / 2 });
  let V = DEF(), M = null;
  function rotM(rx, ry, rz) { // R = Ry * Rx * Rz, row-major 3x3
    const cx = Math.cos(rx), sx = Math.sin(rx), cy = Math.cos(ry), sy = Math.sin(ry), cz = Math.cos(rz), sz = Math.sin(rz);
    return [
      cy * cz + sy * sx * sz, -cy * sz + sy * sx * cz, sy * cx,
      cx * sz, cx * cz, -sx,
      -sy * cz + cy * sx * sz, sy * sz + cy * sx * cz, cy * cx,
    ];
  }
  const mul = (R, p) => [R[0] * p[0] + R[1] * p[1] + R[2] * p[2], R[3] * p[0] + R[4] * p[1] + R[5] * p[2], R[6] * p[0] + R[7] * p[1] + R[8] * p[2]];
  const mulT = (R, p) => [R[0] * p[0] + R[3] * p[1] + R[6] * p[2], R[1] * p[0] + R[4] * p[1] + R[7] * p[2], R[2] * p[0] + R[5] * p[1] + R[8] * p[2]];
  SK.view3 = function (o = {}) { V = { ...DEF(), ...o }; M = rotM(V.pitch, V.yaw, V.roll); return V; };
  SK.view3();
  SK.proj3 = function (p) {
    const r = mulT(M, [p[0] - V.x, p[1] - V.y, p[2] - V.z]);
    const zc = r[2] + V.d;
    if (zc < 1) return null;
    const k = V.zoom * V.d / zc;
    return [V.sx + r[0] * k, V.sy + r[1] * k, zc];
  };
  SK.pose3 = function (p, o = {}) {
    const s = o.s ?? 1, R = rotM(o.rx ?? 0, o.ry ?? 0, o.rz ?? 0);
    const q = mul(R, [p[0] * s, p[1] * s, p[2] * s]);
    return [q[0] + (o.x ?? 0), q[1] + (o.y ?? 0), q[2] + (o.z ?? 0)];
  };
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
  const lerp3 = (a, b, u) => [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)];
  /** how lit a face with these corners is (0..1): Lambert against o.light, over o.ambient */
  function lit(P, o) {
    const n = norm(cross(sub(P[2], P[0]), sub(P[1], P[0]))); // outward for a face wound tl, tr, br
    const L = norm(o.light ?? [-0.45, -0.75, -0.55]);
    const amb = o.ambient ?? 0.55;
    return amb + (1 - amb) * clamp(n[0] * L[0] + n[1] * L[1] + n[2] * L[2]);
  }
  SK.lit3 = lit;

  /* ------------------------------------------------------------ a textured face */
  /** the affine map (a, b, c, d, e, f) taking source points s0, s1, s2 to screen points d0, d1, d2 */
  function affine(s0, s1, s2, d0, d1, d2) {
    const ux = s1[0] - s0[0], uy = s1[1] - s0[1], vx = s2[0] - s0[0], vy = s2[1] - s0[1];
    const det = ux * vy - vx * uy; if (Math.abs(det) < 1e-9) return null;
    const ax = d1[0] - d0[0], ay = d1[1] - d0[1], bx = d2[0] - d0[0], by = d2[1] - d0[1];
    const a = (ax * vy - bx * uy) / det, b = (ay * vy - by * uy) / det;
    const c = (bx * ux - ax * vx) / det, d = (by * ux - ay * vx) / det;
    return [a, b, c, d, d0[0] - a * s0[0] - c * s0[1], d0[1] - b * s0[0] - d * s0[1]];
  }
  /* One grid cell of a face: its source rectangle, drawn with the mean of the two triangles'
     affine maps and a margin past its edges, unclipped. Neighbours overlap by the margin, so no
     anti-aliased edge ever meets another over the ground -- clipping each triangle left a faint
     line of the ground along every diagonal (a cream name block showed a hatch of them) -- and
     the mean map splits the cell's perspective error between its corners. */
  const MARGIN = 1.5;
  function cell(ctx, base, img, s00, s11, p00, p10, p01, p11) {
    const s10 = [s11[0], s00[1]], s01 = [s00[0], s11[1]];
    const A = affine(s00, s10, s01, p00, p10, p01), B = affine(s11, s01, s10, p11, p01, p10);
    if (!A || !B) return;
    const M = A.map((v, k) => (v + B[k]) / 2);
    const x0 = Math.max(0, s00[0] - MARGIN), y0 = Math.max(0, s00[1] - MARGIN);
    const x1 = Math.min(img.width, s11[0] + MARGIN), y1 = Math.min(img.height, s11[1] + MARGIN);
    if (x1 <= x0 || y1 <= y0) return;
    ctx.setTransform(base.multiply(new DOMMatrix(M)));
    ctx.drawImage(img, x0, y0, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0);
  }

  SK.face3 = function (P, w, h, draw, o = {}) {
    const Q = P.map(SK.proj3);
    if (Q.some((q) => !q)) return false;
    const area = (Q[1][0] - Q[0][0]) * (Q[3][1] - Q[0][1]) - (Q[3][0] - Q[0][0]) * (Q[1][1] - Q[0][1]);
    if (o.cull !== false && area <= 0) return false;
    const ctx = SK.ctx(), alpha = o.alpha ?? 1;
    if (alpha <= 0) return true;
    // the face's own pixels: as fine as it is drawn on screen, at most twice its size
    const edge = Math.max(Math.hypot(Q[1][0] - Q[0][0], Q[1][1] - Q[0][1]), Math.hypot(Q[2][0] - Q[3][0], Q[2][1] - Q[3][1])) / w;
    // in eighths, so a face whose size changes a little each frame keeps its offscreen canvas
    const res = o.res ?? Math.ceil(clamp(edge * 1.15, 0.2, 2) * 8) / 8;
    const cw = Math.max(1, Math.ceil(w * res)), ch = Math.max(1, Math.ceil(h * res));
    const cv = SK.scratch(o.key ?? ('face' + cw + 'x' + ch), cw, ch), g = cv.getContext('2d');
    g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cw, ch); g.globalAlpha = 1; g.filter = 'none';
    g.setTransform(res, 0, 0, res, 0, 0);
    if (o.fill) { g.fillStyle = o.fill; g.fillRect(0, 0, w, h); }
    if (draw) SK.drawInto(g, () => draw(g, w, h));
    // a grid fine enough that the affine error inside one cell stays under a pixel
    const zs = Q.map((q) => q[2]), persp = Math.max(...zs) / Math.min(...zs);
    const span = Math.max(...Q.map((q) => q[0])) - Math.min(...Q.map((q) => q[0])) + Math.max(...Q.map((q) => q[1])) - Math.min(...Q.map((q) => q[1]));
    const n = o.grid ?? (persp < 1.004 ? 1 : clamp(Math.ceil(span / 90 * Math.min(4, (persp - 1) * 40)), 2, 16));
    const pts = [];
    for (let j = 0; j <= n; j++) {
      for (let i = 0; i <= n; i++) {
        const top = lerp3(P[0], P[1], i / n), bot = lerp3(P[3], P[2], i / n);
        pts.push(SK.proj3(lerp3(top, bot, j / n)));
      }
    }
    const base = ctx.getTransform();
    const at = (i, j) => pts[j * (n + 1) + i], S = (i, j) => [i / n * cw, j / n * ch];
    const lay = () => {
      const c2 = SK.ctx(), b2 = c2.getTransform();
      c2.save();
      for (let j = 0; j < n; j++) {
        for (let i = 0; i < n; i++) {
          const p00 = at(i, j), p10 = at(i + 1, j), p01 = at(i, j + 1), p11 = at(i + 1, j + 1);
          if (p00 && p10 && p01 && p11) cell(c2, b2, cv, S(i, j), S(i + 1, j + 1), p00, p10, p01, p11);
        }
      }
      c2.restore();
    };
    // the cells overlap, so a see-through face is laid down whole and faded as one
    if (alpha < 1) SK.fx(lay, { alpha, key: 'face3' }); else lay();
    ctx.save(); ctx.globalAlpha *= alpha;
    const sh = o.shade ?? 0;
    if (sh > 0.002) {
      ctx.setTransform(base);
      ctx.beginPath(); ctx.moveTo(Q[0][0], Q[0][1]); for (let k = 1; k < 4; k++) ctx.lineTo(Q[k][0], Q[k][1]); ctx.closePath();
      ctx.fillStyle = o.shadeCol ?? `rgba(0,0,0,${sh})`; if (o.shadeCol) ctx.globalAlpha *= sh; ctx.fill();
    }
    ctx.restore();
    return true;
  };

  /* ------------------------------------------------------------ boxes and polygons */
  SK.box3 = function (o) {
    const hw = o.w / 2, hh = o.h / 2, hd = o.d / 2, F = o.faces || {};
    const L = (x, y, z) => SK.pose3([x, y, z], o);
    const faces = {
      front: [[-hw, -hh, -hd], [hw, -hh, -hd], [hw, hh, -hd], [-hw, hh, -hd], o.w, o.h],
      back: [[hw, -hh, hd], [-hw, -hh, hd], [-hw, hh, hd], [hw, hh, hd], o.w, o.h],
      right: [[hw, -hh, -hd], [hw, -hh, hd], [hw, hh, hd], [hw, hh, -hd], o.d, o.h],
      left: [[-hw, -hh, hd], [-hw, -hh, -hd], [-hw, hh, -hd], [-hw, hh, hd], o.d, o.h],
      top: [[-hw, -hh, hd], [hw, -hh, hd], [hw, -hh, -hd], [-hw, -hh, -hd], o.w, o.d],
      bottom: [[-hw, hh, -hd], [hw, hh, -hd], [hw, hh, hd], [-hw, hh, hd], o.w, o.d],
    };
    const drawn = [];
    for (const [name, f] of Object.entries(faces)) {
      const spec = F[name] ?? {};
      if (spec === false) continue;
      const P = f.slice(0, 4).map((p) => L(...p));
      const k = lit(P, o), dark = (1 - k) * (o.shadeK ?? 1) + (spec.shade ?? 0);
      if (SK.face3(P, f[4], f[5], spec.draw, { fill: spec.fill ?? o.fill ?? '#888', shade: dark, key: (o.key ?? 'box') + ':' + name, res: spec.res ?? o.res, grid: spec.grid })) drawn.push(name);
    }
    return drawn;
  };

  SK.poly3 = function (pts, fill, o = {}) {
    const Q = pts.map(SK.proj3);
    if (Q.some((q) => !q)) return false;
    let area = 0;
    for (let i = 0; i < Q.length; i++) { const a = Q[i], b = Q[(i + 1) % Q.length]; area += a[0] * b[1] - b[0] * a[1]; }
    if (o.cull && area <= 0) return false;
    const ctx = SK.ctx();
    ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
    ctx.beginPath(); ctx.moveTo(Q[0][0], Q[0][1]); for (let i = 1; i < Q.length; i++) ctx.lineTo(Q[i][0], Q[i][1]); ctx.closePath();
    ctx.fillStyle = fill; ctx.fill();
    if (o.light !== false) {
      const P = area >= 0 ? pts : [...pts].reverse(); // light the side we see
      const k = lit([P[0], P[1], P[2]], o);
      if (k < 1) { ctx.fillStyle = `rgba(0,0,0,${(1 - k) * (o.shadeK ?? 1)})`; ctx.fill(); }
    }
    if (o.stroke) { ctx.lineJoin = 'round'; ctx.lineWidth = o.strokeW ?? 2; ctx.strokeStyle = o.stroke; ctx.stroke(); }
    ctx.restore();
    return true;
  };

  /* ------------------------------------------------------------ layers: blur and smear */
  SK.fx = function (fn, o = {}) {
    const ctx = SK.ctx(), a = o.alpha ?? 1;
    if (a <= 0) return;
    const blur = o.blur ?? 0, smear = o.smear ?? 0, dx = o.dx ?? 0, dy = o.dy ?? 0;
    if (blur < 0.3 && smear < 0.5 && !dx && !dy && a >= 1) { fn(); return; }
    const cv = SK.scratch('fx:' + (o.key ?? 0), SK.W, SK.H), g = cv.getContext('2d');
    g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, SK.W, SK.H); g.globalAlpha = 1; g.filter = 'none';
    g.setTransform(ctx.getTransform());
    SK.drawInto(g, fn);
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha *= a;
    if (blur >= 0.3) ctx.filter = `blur(${blur.toFixed(1)}px)`;
    if (smear >= 0.5) { // a directional smear: copies along (ux, uy), the middle one strongest
      const n = Math.min(14, Math.max(3, Math.round(smear / 6))), ang = o.angle ?? 0, ux = Math.cos(ang), uy = Math.sin(ang);
      const base = ctx.globalAlpha;
      for (let i = 0; i < n; i++) {
        const u = i / (n - 1) - .5;
        ctx.globalAlpha = base * (i === 0 ? 1 : 1 / (i + 1));
        ctx.drawImage(cv, dx + ux * smear * u, dy + uy * smear * u);
      }
    } else ctx.drawImage(cv, dx, dy);
    ctx.restore();
  };
})();
