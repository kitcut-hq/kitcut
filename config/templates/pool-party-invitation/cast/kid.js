/* cast/kid.js -- the birthday child, drawn from their photo. A front-facing doodle kid: here a
   fluffy blond mop with bangs, big yellow pixel sunglasses, a coral tee with the age on it in white,
   blue shorts, white sneakers -- redraw the hair, skin, glasses and clothes (COL and the head) from
   the photo of the child a film is for. Origin between the feet; about 440 units tall at s = 1.
   SK.cast.kid.draw(x, y, { s, t, arms, mouth, lean, jump, sq, walk, wave, slimed, tilt, age })
     arms: {F:[x,y], B:[x,y]} hand targets (F = the viewer's right), or a pose name (POSE);
     mouth: 'smile' | 'big' | 'o' | 'flat'; lean: radians; jump: units up; slimed: 0..1 green goo
     on the head and shoulders; age: the number on the tee (a string; fitted to the tee).
     Returns the hands in world units: { handF, handB }.
   SK.cast.kid.poseAt(t, [[t, pose], ...]) springs from pose to pose. */
(function () {
  'use strict';
  const SK = window.SK;
  const { S, E, clamp, lerp, TAU } = SK;
  SK.cast = SK.cast || {};
  const COL = {
    skin: '#f9d8c0', cheek: '#f4a09a', hair: '#f3d68e', hairDk: '#c99f45', tee: '#f26d64', shorts: '#4d74b6',
    shoe: '#ffffff', frame: '#e8e05a', frameLt: '#fbf7cc', frameDk: '#b9ae2c', lens: '#2b2a31', goo: '#8fe05a',
  };
  const POSE = {
    rest: { F: [66, -150], B: [-66, -150] }, wave: { F: [128, -380], B: [-66, -150] },
    cheer: { F: [128, -392], B: [-128, -392] }, hold: { F: [112, -250], B: [-112, -250] },
    point: { F: [205, -330], B: [-66, -150] }, slide: { F: [190, -300], B: [-185, -250] },
    wide: { F: [175, -250], B: [-175, -250] }, uhoh: { F: [62, -305], B: [-62, -305] },
    cake: { F: [96, -150], B: [-96, -150] },
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
  // a filled limb: a dark edge with the colour inside
  function limb(pts, w, col, seed) {
    ink(pts, { w: w + 7, seed, jit: 1, taper: false, dbl: false });
    ink(pts, { w, col, seed, jit: 1, taper: false, dbl: false });
  }
  // a pixel-art box with both lower corners stepped
  const stepBox = (x0, y0, x1, y1, q) => S.poly([[x0, y0], [x1, y0], [x1, y1 - 2 * q], [x1 - q, y1 - 2 * q], [x1 - q, y1 - q], [x1 - 2 * q, y1 - q],
    [x1 - 2 * q, y1], [x0 + 2 * q, y1], [x0 + 2 * q, y1 - q], [x0 + q, y1 - q], [x0 + q, y1 - 2 * q], [x0, y1 - 2 * q]], true);
  // a drippy lower edge from x0 to x1 (left to right): drips [[x, length, radius]]
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
  function glasses(ctx) {
    for (const sd of [-1, 1]) {
      const x0 = sd > 0 ? 7 : -79, x1 = sd > 0 ? 79 : -7;
      const fr = stepBox(x0, -30, x1, 26, 8);
      wash(fr, COL.frame, { seed: 3100 + sd, dx: 0, dy: 0, tex: false });
      for (let i = 0; x0 + i * 9 + 9 <= x1; i++) { ctx.fillStyle = i % 2 ? COL.frameLt : COL.frameDk; ctx.fillRect(x0 + i * 9, -29, 9, 8); }
      wash(stepBox(x0 + 10, -20, x1 - 10, 16, 6), COL.lens, { seed: 3104 + sd, dx: 0, dy: 0, tex: false });
      ink(fr, { w: 4, seed: 3106 + sd, dbl: false });
      ink(S.line(x0 + 18, -6, x0 + 30, -14), { w: 4, col: 'rgba(255,255,255,.7)', seed: 3108 + sd, dbl: false });
    }
    const br = S.poly([[-9, -26], [9, -26], [9, -12], [-9, -12]], true);
    wash(br, COL.frame, { seed: 3110, dx: 0, dy: 0, tex: false }); ink(br, { w: 3.5, seed: 3111, dbl: false });
  }
  function goo(g, tt) { // green goo on the head, in head coordinates
    const base = (x) => -44 + 34 * (x / 104) ** 2;
    const drips = [[-72, 50 * g + 4 * Math.sin(tt * 2), 13], [-24, 16 * g, 10], [30, 36 * g + 3 * Math.sin(tt * 2.6), 12], [76, 62 * g, 11]];
    const cap = [...drippy(-104, 104, base, drips), ...S.arc(0, -10, 104, 0, -Math.PI, lerp(80, 118, g)).slice(1)];
    wash(cap, COL.goo, { seed: 3130, dx: 0, dy: 0 }); ink(cap, { w: 5, seed: 3131 });
    ink(S.arc(-34, -66, 40, Math.PI * 1.1, Math.PI * 1.45), { w: 6, col: 'rgba(255,255,255,.75)', seed: 3132, dbl: false });
  }
  function draw(x, y, o = {}) {
    const ctx = SK.ctx(), s = o.s ?? 1; if (s <= 0) return null;
    const sq = o.sq ?? 0, lean = o.lean ?? 0, jump = o.jump ?? 0, g = clamp(o.slimed ?? 0), tt = o.t ?? SK.T;
    let arms = typeof o.arms === 'string' ? POSE[o.arms] : (o.arms ?? POSE.rest);
    if (o.wave !== undefined) arms = { F: [arms.F[0] + Math.sin(o.wave * TAU) * 24, arms.F[1] - Math.abs(Math.cos(o.wave * TAU)) * 8], B: arms.B };
    const ph = (o.walk ?? 0) * TAU, walking = !!o.walk;
    SK.alpha(.16, () => wash(S.ellC(x, y + 4, 80 * s / (1 + jump / 300), 13 * s), SK.C.ink, { dx: 0, dy: 0, tex: false }));
    ctx.save(); ctx.translate(x, y - jump); ctx.rotate(lean); ctx.scale(s * (1 + sq), s * (1 - sq));
    const bob = walking ? -Math.abs(Math.sin(ph)) * 8 : 0;
    ctx.translate(0, bob);
    // legs and sneakers
    for (const [sd, i] of [[-1, 0], [1, 1]]) {
      const sw = walking ? Math.sin(ph + i * Math.PI) : 0, fx = sd * 28 + sw * 16, fy = walking ? -Math.max(0, sw) * 14 : 0;
      limb(S.line(sd * 22, -112, fx, fy - 12), 15, COL.skin, 3000 + i);
      const shoe = S.ellC(fx + sd * 6, fy - 8, 26, 13);
      wash(shoe, COL.shoe, { seed: 3002 + i, dx: 0, dy: 0, tex: false }); ink(shoe, { w: 4.5, seed: 3004 + i, dbl: false });
    }
    const shorts = S.poly([[-58, -170], [58, -170], [62, -104], [6, -104], [0, -122], [-6, -104], [-62, -104]], true);
    wash(shorts, COL.shorts, { seed: 3010 }); ink(shorts, { w: 5, seed: 3011 });
    const tee = S.path([['M', -50, -268], ['Q', -70, -206, -62, -150], ['L', 62, -150], ['Q', 70, -206, 50, -268], ['Q', 0, -286, -50, -268]]);
    wash(tee, COL.tee, { seed: 3012 }); ink(tee, { w: 5.5, seed: 3013 });
    const age = String(o.age ?? '');
    if (age) { // the age on the tee, narrowed to fit it
      const f0 = ctx.font; ctx.font = '700 70px "Balsamiq Sans"';
      const aw = [...age].reduce((a, ch) => a + ctx.measureText(ch).width, 0); ctx.font = f0;
      SK.txt(age, 0, -202, { size: aw > 96 ? 70 * 96 / aw : 70, font: 'Balsamiq Sans', wt: 700, col: '#ffffff', seed: 3014, wob: .4 });
    }
    if (g > 0) SK.alpha(clamp(g * 3), () => {
      const sh = [...drippy(-62, 62, (xx) => -256 + 8 * (xx / 62) ** 2, [[-30, 30 * g, 9], [26, 46 * g, 10]]), ...S.arc(0, -252, 62, 0, -Math.PI, 20).slice(1)];
      wash(sh, COL.goo, { seed: 3016, dx: 0, dy: 0 }); ink(sh, { w: 4.5, seed: 3017 });
    });
    // head
    ctx.save(); ctx.translate(0, -350); ctx.rotate(o.tilt ?? 0);
    const back = S.path([['M', -92, 12], ['Q', -106, -88, -6, -100], ['Q', 98, -102, 94, 6], ['Q', 80, -30, 0, -40], ['Q', -80, -30, -92, 12]]);
    wash(back, COL.hair, { seed: 3020 }); ink(back, { w: 4.5, seed: 3021 });
    for (const sd of [-1, 1]) { const ear = S.ellC(sd * 80, 8, 15, 21); wash(ear, COL.skin, { seed: 3022 + sd, dx: 0, dy: 0, tex: false }); ink(ear, { w: 4.5, seed: 3024 + sd, dbl: false }); }
    wash(S.ellC(0, 0, 80, 76), COL.skin, { seed: 3026, texCol: 'rgba(255,255,255,.25)' });
    ink(S.ell(0, 0, 80, 76, -2.2, .28), { w: 5.5, seed: 3027 });
    const bangs = S.path([['M', -86, -2], ['Q', -98, -86, -8, -96], ['Q', 90, -100, 88, -6], ['L', 76, -26], ['L', 62, -42], ['L', 50, -22], ['L', 34, -46], ['L', 18, -24],
      ['L', 2, -48], ['L', -14, -24], ['L', -30, -46], ['L', -46, -24], ['L', -62, -42], ['L', -76, -20], ['Z']]);
    wash(bangs, COL.hair, { seed: 3028, texCol: 'rgba(255,255,255,.3)' }); ink(bangs, { w: 4.5, seed: 3029 });
    for (const [a, b, c, d, i] of [[-44, -84, -32, -52, 0], [6, -90, 2, -56, 1], [48, -80, 38, -50, 2]]) ink(S.path([['M', a, b], ['Q', (a + c) / 2 + 8, (b + d) / 2, c, d]]), { w: 3, col: COL.hairDk, seed: 3030 + i, dbl: false });
    ink(S.path([['M', 4, -94], ['Q', 18, -126, 34, -108]]), { w: 4, seed: 3034, dbl: false });
    glasses(ctx);
    SK.alpha(.55, () => { wash(S.ellC(-54, 38, 13, 8), COL.cheek, { dx: 0, dy: 0, tex: false }); wash(S.ellC(54, 38, 13, 8), COL.cheek, { dx: 0, dy: 0, tex: false }); });
    ink(S.arc(0, 30, 7, .3, Math.PI - .3), { w: 3.5, seed: 3036, dbl: false });
    SK.P.face.mouth(0, 57, o.mouth ?? 'smile', .9);
    if (g > 0) SK.alpha(clamp(g * 3), () => goo(g, tt));
    ctx.restore();
    // arms, in front
    const arm = (sd, H, seed) => {
      const sx = sd * 46, sy = -254, mx = (sx + H[0]) / 2 + sd * 18, my = (sy + H[1]) / 2 + 10;
      limb(S.path([['M', sx, sy], ['Q', mx, my, H[0], H[1]]]), 14, COL.skin, seed);
      limb(S.line(sx, sy, lerp(sx, mx, .5), lerp(sy, my, .5)), 26, COL.tee, seed + 1);
      wash(S.ellC(H[0], H[1], 16, 15), COL.skin, { dx: 0, dy: 0, tex: false }); ink(S.ell(H[0], H[1], 16, 15), { w: 4.5, seed: seed + 2, dbl: false });
    };
    arm(-1, arms.B, 3040); arm(1, arms.F, 3044);
    ctx.restore();
    const c = Math.cos(lean), sn = Math.sin(lean);
    const tr = ([hx, hy]) => { const X = hx * s * (1 + sq), Y = (hy + bob) * s * (1 - sq); return [x + X * c - Y * sn, y - jump + X * sn + Y * c]; };
    return { handF: tr(arms.F), handB: tr(arms.B) };
  }
  SK.cast.kid = {
    about: 'the birthday child, a front-facing doodle kid drawn from their photo (here a fluffy blond mop and bangs, big yellow pixel sunglasses, a coral tee with the age on it in white, blue shorts and white sneakers)',
    POSE, poseAt, draw, COL,
  };
})();
