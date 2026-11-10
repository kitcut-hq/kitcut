/* cast/mascot.js -- the venue's mascot, drawn from a photo of the venue: a fuzzy sky-blue blob
   with two huge target eyes (pink rim, yellow ring, dark pupil), a small round mouth, stubby
   yellow arms and feet, and a yellow stalk carrying a pink-and-yellow swirl on top. Redraw it
   for another venue's mascot (or give the film content.star 'kid'). Same calling convention as
   cast/kid.js, so the film swaps one for the other. Origin between the feet; about 450 units
   tall at s = 1.
   SK.cast.mascot.draw(x, y, { s, t, arms, mouth, lean, jump, sq, wave, slimed, tilt })
     arms: {F:[x,y], B:[x,y]} hand targets (F = the viewer's right), or a pose name (POSE);
     mouth: 'smile' | 'big' | 'o' | 'flat'; slimed: 0..1 green goo over his top.
     Returns the hands in world units: { handF, handB }.
   SK.cast.mascot.poseAt(t, [[t, pose], ...]) springs from pose to pose. */
(function () {
  'use strict';
  const SK = window.SK;
  const { S, E, clamp, lerp, TAU } = SK;
  SK.cast = SK.cast || {};
  const COL = {
    body: '#4fb3ea', bodyLt: '#8fd3f5', fuzz: '#2f8fcc', limb: '#ffd23f', limbDk: '#e0a91c',
    rim: '#f0467e', ring: '#ffe25a', pupil: '#2b2a3a', swirl: '#ff4fa3', swirlLt: '#ffc2dd', goo: '#8fe05a',
  };
  const POSE = {
    rest: { F: [150, -120], B: [-150, -120] }, wave: { F: [175, -390], B: [-150, -120] },
    cheer: { F: [180, -390], B: [-180, -390] }, hold: { F: [150, -250], B: [-150, -250] },
    point: { F: [240, -320], B: [-150, -120] }, slide: { F: [230, -300], B: [-225, -250] },
    wide: { F: [235, -250], B: [-235, -250] }, uhoh: { F: [110, -330], B: [-110, -330] },
    cake: { F: [74, -40], B: [-74, -40] },
  };
  function poseAt(t, keys) {
    let k = 0;
    for (let i = 0; i < keys.length; i++) if (keys[i][0] <= t) k = i;
    const get = (v) => (typeof v === 'string' ? POSE[v] : v) || POSE.rest;
    const to = get(keys[k][1]);
    if (t < keys[0][0] || k === 0) return to;
    const from = get(keys[k - 1][1]), u = E.back(clamp((t - keys[k][0]) / .3));
    return { F: [lerp(from.F[0], to.F[0], u), lerp(from.F[1], to.F[1], u)], B: [lerp(from.B[0], to.B[0], u), lerp(from.B[1], to.B[1], u)] };
  }
  const ink = (p, o) => SK.ink(p, o), wash = (p, c, o) => SK.wash(p, c, o);
  function limb(pts, w, col, seed) {
    ink(pts, { w: w + 7, seed, jit: 1, taper: false, dbl: false });
    ink(pts, { w, col, seed, jit: 1, taper: false, dbl: false });
  }
  function drippy(x0, x1, base, drips) {
    const out = []; let x = x0;
    for (const [dx, L, r] of drips) {
      for (; x < dx - r; x += 10) out.push([x, base(x)]);
      const b = base(dx);
      out.push(...S.line(dx - r * .7, b, dx - r, b + L), ...S.arc(dx, b + L, r, Math.PI, 0).slice(1), ...S.line(dx + r, b + L, dx + r * .7, b).slice(1));
      x = dx + r + 4;
    }
    for (; x < x1; x += 10) out.push([x, base(x)]);
    out.push([x1, base(x1)]);
    return out;
  }
  // the fuzzy body outline: a squat egg whose edge is ruffled into little tufts
  const BX = 150, BY = 165, BC = -178;
  function bodyPts(tt) {
    const out = [];
    for (let i = 0; i < 120; i++) {
      const a = i / 120 * TAU, tuft = 1 + .035 * Math.sin(a * 23) + .012 * Math.sin(a * 41 + tt * 3);
      const ry = BY * (Math.sin(a) > 0 ? .96 : 1.04); // flatter underneath, rounder on top
      out.push([Math.cos(a) * BX * tuft, BC + Math.sin(a) * ry * tuft]);
    }
    return out;
  }
  function eye(cx, cy, r, look, seed) {
    const rim = S.ellC(cx, cy, r, r * 1.02);
    wash(rim, COL.rim, { seed, dx: 0, dy: 0, tex: false }); ink(S.ell(cx, cy, r, r * 1.02), { w: 4.5, seed: seed + 1, dbl: false });
    wash(S.ellC(cx, cy, r * .78, r * .8), COL.ring, { seed: seed + 2, dx: 0, dy: 0, tex: false });
    const px = cx + look[0] * r * .12, py = cy + look[1] * r * .12;
    wash(S.ellC(px, py, r * .42, r * .44), COL.pupil, { seed: seed + 3, dx: 0, dy: 0, tex: false });
    wash(S.ellC(px - r * .14, py - r * .16, r * .12, r * .1), '#ffffff', { seed: seed + 4, dx: 0, dy: 0, tex: false });
  }
  function topknot(tt, g) { // the yellow stalk and the pink-and-yellow swirl, swaying
    const sw = .09 * Math.sin(tt * 2.1);
    const base = [0, BC - BY + 12], top = [Math.sin(sw) * 70, BC - BY - 70];
    const stalk = S.path([['M', base[0], base[1]], ['Q', 18, (base[1] + top[1]) / 2, top[0], top[1]]]);
    limb(stalk, 26, COL.limb, 3230);
    const cx = top[0] + 4, cy = top[1] - 38;
    const ball = S.ellC(cx, cy, 58, 46, sw * .6);
    wash(ball, COL.swirl, { seed: 3232 }); ink(S.ell(cx, cy, 58, 46, -2.2, .3, sw * .6), { w: 5, seed: 3233 });
    // the swirl: a yellow ribbon wound once round the pink, and a pale highlight
    const sp = [];
    for (let i = 0; i <= 40; i++) { const u = i / 40, a = -Math.PI * .1 + u * Math.PI * 1.7, rr = lerp(46, 14, u); sp.push([cx + Math.cos(a) * rr * 1.1, cy + Math.sin(a) * rr * .8]); }
    ink(sp, { w: 14, col: COL.limb, seed: 3234, taper: false, dbl: false });
    ink(S.arc(cx - 16, cy - 16, 22, Math.PI * 1.05, Math.PI * 1.5), { w: 6, col: COL.swirlLt, seed: 3235, dbl: false });
    if (g > 0) SK.alpha(clamp(g * 3), () => {
      const d = [...drippy(cx - 58, cx + 58, (xx) => cy - 8 + 18 * ((xx - cx) / 58) ** 2, [[cx - 28, 26 * g, 9], [cx + 24, 40 * g, 10]]), ...S.arc(cx, cy - 6, 58, 0, -Math.PI, 46).slice(1)];
      wash(d, COL.goo, { seed: 3236, dx: 0, dy: 0 }); ink(d, { w: 4.5, seed: 3237 });
    });
  }
  function draw(x, y, o = {}) {
    const ctx = SK.ctx(), s = o.s ?? 1; if (s <= 0) return null;
    const sq = o.sq ?? 0, lean = o.lean ?? 0, jump = o.jump ?? 0, g = clamp(o.slimed ?? 0), tt = o.t ?? SK.T;
    let arms = typeof o.arms === 'string' ? POSE[o.arms] : (o.arms ?? POSE.rest);
    if (o.wave !== undefined) arms = { F: [arms.F[0] + Math.sin(o.wave * TAU) * 24, arms.F[1] - Math.abs(Math.cos(o.wave * TAU)) * 8], B: arms.B };
    // a jelly squash that follows the jump: stretched going up, squashed on landing
    const jig = sq + .05 * Math.sin(tt * 3.1) * .4;
    SK.alpha(.16, () => wash(S.ellC(x, y + 4, 130 * s / (1 + jump / 300), 16 * s), SK.C.ink, { dx: 0, dy: 0, tex: false }));
    ctx.save(); ctx.translate(x, y - jump); ctx.rotate(lean); ctx.scale(s * (1 + jig), s * (1 - jig));
    // feet
    for (const sd of [-1, 1]) {
      const ft = S.ellC(sd * 62, -10, 44, 20);
      wash(ft, COL.limb, { seed: 3200 + sd, dx: 0, dy: 0, tex: false }); ink(S.ell(sd * 62, -10, 44, 20), { w: 4.5, seed: 3202 + sd, dbl: false });
    }
    ctx.save(); ctx.rotate(o.tilt ?? 0);
    topknot(tt, g);
    // the body: blue fuzz with a lighter belly and a few darker tufts
    const bp = bodyPts(tt);
    wash(bp, COL.body, { seed: 3210, texCol: 'rgba(255,255,255,.28)' }); ink([...bp, bp[0]], { w: 5.5, seed: 3211 });
    SK.alpha(.55, () => wash(S.ellC(0, BC + 60, BX * .62, BY * .5), COL.bodyLt, { seed: 3212, dx: 0, dy: 0 }));
    for (let i = 0; i < 9; i++) { // fur strokes
      const a = -Math.PI * .9 + i * .23, r0 = .7 + .08 * Math.sin(i * 3.3);
      const px = Math.cos(a) * BX * r0, py = BC + Math.sin(a) * BY * r0;
      ink(S.line(px, py, px + Math.cos(a) * 16, py + Math.sin(a) * 16), { w: 3, col: COL.fuzz, seed: 3213 + i, dbl: false });
    }
    // a dark freckle or two, like the plush
    for (const [fx, fy] of [[-96, -150], [104, -120], [-70, -60]]) wash(S.ellC(fx, fy, 5, 5), COL.fuzz, { dx: 0, dy: 0, tex: false });
    const look = o.look ?? [Math.sin(tt * .7) * .5, .2];
    eye(-64, BC - 42, 56, look, 3240); eye(64, BC - 42, 56, look, 3250);
    SK.P.face.mouth(0, BC + 42, o.mouth ?? 'smile', 1.1);
    if (g > 0) SK.alpha(clamp(g * 3), () => { // green goo over his crown
      const base = (xx) => BC - BY * .78 + 30 * (xx / (BX * .9)) ** 2;
      const cap = [...drippy(-BX * .9, BX * .9, base, [[-92, 56 * g + 4 * Math.sin(tt * 2), 13], [-20, 22 * g, 10], [46, 44 * g, 12], [104, 60 * g, 11]]), ...S.arc(0, BC - 30, BX * .92, 0, -Math.PI, lerp(110, BY * 1.02, g)).slice(1)];
      wash(cap, COL.goo, { seed: 3260, dx: 0, dy: 0 }); ink(cap, { w: 5, seed: 3261 });
      ink(S.arc(-50, BC - 120, 40, Math.PI * 1.1, Math.PI * 1.45), { w: 6, col: 'rgba(255,255,255,.75)', seed: 3262, dbl: false });
    });
    ctx.restore();
    // stubby yellow arms, in front, from the sides of the body
    const arm = (sd, H, seed) => {
      const sx = sd * (BX - 22), sy = BC + 10, mx = (sx + H[0]) / 2 + sd * 14, my = (sy + H[1]) / 2 + 12;
      limb(S.path([['M', sx, sy], ['Q', mx, my, H[0], H[1]]]), 22, COL.limb, seed);
      const hand = S.ellC(H[0], H[1], 22, 20);
      wash(hand, COL.limb, { dx: 0, dy: 0, tex: false }); ink(S.ell(H[0], H[1], 22, 20), { w: 4.5, seed: seed + 2, dbl: false });
      ink(S.arc(H[0] + sd * 6, H[1] - 4, 10, Math.PI * .1, Math.PI * .6), { w: 3, col: COL.limbDk, seed: seed + 3, dbl: false });
    };
    arm(-1, arms.B, 3270); arm(1, arms.F, 3274);
    ctx.restore();
    const c = Math.cos(lean), sn = Math.sin(lean);
    const tr = ([hx, hy]) => { const X = hx * s * (1 + jig), Y = hy * s * (1 - jig); return [x + X * c - Y * sn, y - jump + X * sn + Y * c]; };
    return { handF: tr(arms.F), handB: tr(arms.B) };
  }
  SK.cast.mascot = {
    about: 'the venue mascot: a fuzzy sky-blue blob with huge pink-rimmed yellow target eyes, a small round mouth, stubby yellow arms and feet, and a yellow stalk topped by a pink-and-yellow swirl',
    POSE, poseAt, draw, COL,
  };
})();
