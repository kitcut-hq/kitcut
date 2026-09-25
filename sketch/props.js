/* sketch/props.js -- a reusable cast and prop box for sketch films, drawn with sketch/engine.js.

   Every prop is drawn around its own origin and takes an options object; nothing here knows
   about a particular film. Seeds are fixed per prop so each one boils consistently.

   SK.P.face.eyes / SK.P.face.mouth   moods: open wow sad happy sleepy (+ blink)
   SK.P.ticket({...})                  a ticket/pass/coupon character with a face and two text lines
   SK.P.person({...}) + SK.P.POSE      seated doodle person (stick limbs, big head); poseAt() blends poses
   SK.P.plane, laptop, table, floor, lightbulb, rocket, padlock, coin, stamp, pokeHand,
   browser, thoughtBubble, confetti
*/
(function () {
  'use strict';
  const SK = window.SK;
  const { S, E, clamp, lerp, inv, TAU, mix, pop, mulberry, rnd } = SK;
  const ink = (...a) => SK.ink(...a), wash = (...a) => SK.wash(...a), txt = (...a) => SK.txt(...a);
  const C = () => SK.C;
  const P = (SK.P = {});

  /* ------------------------------------------------------------ faces */
  P.face = {
    eyes(x1, y1, x2, y2, mood, blink, sz = 1) {
      const ctx = SK.ctx(), r = 8.5 * sz;
      for (const [x, y, i] of [[x1, y1, 0], [x2, y2, 1]]) {
        if (mood === 'happy' || mood === 'cheer') ink(S.arc(x, y + 4 * sz, 11 * sz, Math.PI * 1.15, Math.PI * 1.85), { w: 5 * sz, seed: 60 + i, dbl: false });
        else if (mood === 'sleepy') ink(S.arc(x, y - 3 * sz, 10 * sz, Math.PI * .15, Math.PI * .85), { w: 4.5 * sz, seed: 62 + i, dbl: false });
        else if (blink > .5) ink(S.line(x - 10 * sz, y, x + 10 * sz, y), { w: 4.5 * sz, seed: 64 + i, dbl: false });
        else {
          const big = mood === 'wow' ? 1.45 : 1;
          wash(S.ellC(x, y, r * big, r * 1.12 * big), C().ink, { dx: 0, dy: 0, tex: false, jit: .5 });
          ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(x + 2.8 * sz * big, y - 3 * sz * big, 2.6 * sz * big, 0, TAU); ctx.fill();
          if (mood === 'wow') { ctx.beginPath(); ctx.arc(x - 3 * sz, y + 3.5 * sz, 1.6 * sz, 0, TAU); ctx.fill(); }
          // sad: inner ends of the brows raised (the other way round reads as angry)
          if (mood === 'sad') ink(S.line(x - 12 * sz, y - 15 * sz + (i ? -5 : 5) * sz, x + 12 * sz, y - 15 * sz - (i ? -5 : 5) * sz), { w: 4 * sz, seed: 66 + i, dbl: false });
        }
      }
    },
    mouth(x, y, kind, sz = 1) {
      if (kind === 'smile') ink(S.arc(x, y - 12 * sz, 17 * sz, Math.PI * .2, Math.PI * .8), { w: 4.8 * sz, seed: 70, dbl: false });
      else if (kind === 'frown') ink(S.arc(x, y + 12 * sz, 13 * sz, Math.PI * 1.25, Math.PI * 1.75), { w: 4.5 * sz, seed: 71, dbl: false });
      else if (kind === 'o') wash(S.ellC(x, y, 7 * sz, 9 * sz), C().ink, { dx: 0, dy: 0, tex: false, jit: .5 });
      else if (kind === 'big') {
        const pts = S.path([['M', x - 20 * sz, y - 6 * sz], ['Q', x, y - 2 * sz, x + 20 * sz, y - 6 * sz], ['Q', x + 16 * sz, y + 20 * sz, x, y + 20 * sz], ['Q', x - 16 * sz, y + 20 * sz, x - 20 * sz, y - 6 * sz]]);
        wash(pts, '#5a2a22', { dx: 0, dy: 0, tex: false, jit: .6 });
        wash(S.ellC(x + 1 * sz, y + 13 * sz, 9 * sz, 5 * sz), '#ef8a86', { dx: 0, dy: 0, tex: false, jit: .5 });
        ink(pts, { w: 4.2 * sz, seed: 72, dbl: false });
      } else if (kind === 'flat') ink(S.line(x - 12 * sz, y, x + 12 * sz, y + 1), { w: 4.5 * sz, seed: 73, dbl: false });
      else if (kind === 'wobble') ink(S.path([['M', x - 16 * sz, y + 3], ['Q', x - 8 * sz, y - 5, x, y + 2], ['Q', x + 8 * sz, y + 8, x + 16 * sz, y]]), { w: 4.2 * sz, seed: 74, dbl: false });
    },
  };

  /* ------------------------------------------------------------ the ticket character */
  function ticketPts(w = 340, h = 190, r = 22, n = 24) {
    const X = w / 2, Y = h / 2, out = [], add = (a) => { if (out.length) a.shift(); out.push(...a); };
    add(S.line(-X + r, -Y, X - r, -Y)); add(S.arc(X - r, -Y + r, r, -Math.PI / 2, 0));
    add(S.line(X, -Y + r, X, -n)); add(S.arc(X, 0, n, -Math.PI / 2, -Math.PI * 1.5));
    add(S.line(X, n, X, Y - r)); add(S.arc(X - r, Y - r, r, 0, Math.PI / 2));
    add(S.line(X - r, Y, -X + r, Y)); add(S.arc(-X + r, Y - r, r, Math.PI / 2, Math.PI));
    add(S.line(-X, Y - r, -X, n)); add(S.arc(-X, 0, n, Math.PI / 2, -Math.PI / 2));
    add(S.line(-X, -n, -X, -Y + r)); add(S.arc(-X + r, -Y + r, r, Math.PI, Math.PI * 1.5));
    return out;
  }
  const TICKET = ticketPts();
  P.TICKET = TICKET;
  /**
   * A ticket with a face: a pass, a coupon, an invite. Drawn 340x190 around its centre.
   * o: x, y, rot, s, p (draw-on), grey (0..1 drains the colour), fill, title, subtitle, mood,
   *    mouth, blink, look, arms [left, right] (radians, 0 = hanging), legs, legKick, sq (squash), tp, alpha, icon (true)
   */
  P.ticket = function (o) {
    const s = o.s ?? 1, p = o.p ?? 1; if (p <= 0 || s <= 0) return;
    const ctx = SK.ctx();
    ctx.save(); ctx.translate(o.x, o.y); ctx.rotate(o.rot ?? 0);
    const sq = o.sq ?? 0; ctx.scale(s * (1 + sq), s * (1 - sq));
    const grey = o.grey ?? 0, fillCol = mix(o.fill ?? '#f2a472', C().grey, grey), inkA = 1 - grey * .35;
    const base = ctx.globalAlpha; ctx.globalAlpha = base * (o.alpha ?? 1);
    if (o.legs !== false) {
      const lk = o.legKick ?? 0;
      for (const [lx, i] of [[-40, 0], [44, 1]]) {
        const fx = lx + (i ? lk : -lk) * 18;
        ink(S.line(lx, 92, fx, 136), { w: 5.5, seed: 80 + i, p: clamp(p * 2 - 1), alpha: inkA });
        wash(S.ellC(fx + 9, 139, 17, 9), C().ink, { dx: 0, dy: 0, tex: false, alpha: clamp(p * 2 - 1) * inkA });
      }
    }
    if (o.arms) {
      const [aL, aR] = o.arms;
      const arm = (sx, sy, dir, a, i) => {
        const L = 62, ex = sx + dir * Math.sin(a) * L * .55, ey = sy + Math.cos(a) * L * .55;
        const hx = sx + dir * Math.sin(a * 1.15) * L, hy = sy + Math.cos(a * 1.15) * L;
        ink(S.path([['M', sx, sy], ['Q', ex + dir * 8, ey, hx, hy]]), { w: 5.5, seed: 84 + i, p: clamp(p * 2 - 1), alpha: inkA });
        wash(S.ellC(hx, hy, 10, 10), mix(C().cream, C().grey, grey), { dx: 0, dy: 0, tex: false, alpha: clamp(p * 2 - 1) });
        ink(S.ell(hx, hy, 10, 10), { w: 4, seed: 86 + i, p: clamp(p * 2 - 1), dbl: false, alpha: inkA });
      };
      arm(-168, 30, -1, aL, 0); arm(168, 30, 1, aR, 1);
    }
    wash(TICKET, fillCol, { seed: 11, dx: 5, dy: 5, alpha: clamp((p - .35) / .4) });
    ink(TICKET, { w: 5.5, p, seed: 12, alpha: inkA });
    const pa = clamp((p - .5) / .3) * inkA;
    if (pa > 0) {
      for (let yy = -78; yy < 80; yy += 20) ink(S.line(-86, yy, -86, yy + 9), { w: 3.5, seed: 90 + yy, dbl: false, alpha: pa });
      if (o.icon !== false) SK.spark(-128, 0, 30, { col: mix(C().cream, '#f4efe6', grey), p: pa, w: 6.5 });
    }
    const tp = o.tp ?? clamp((p - .55) / .45), tx = 42, tcol = mix(C().ink, '#8f877c', grey);
    if (o.title) txt(o.title, tx, -58, { size: 31, font: SK.FONT_PRINT, wt: 400, p: tp, ls: 3.5, col: tcol, seed: 7 });
    if (o.subtitle) txt(o.subtitle, tx, 67, { size: 30, p: tp, col: tcol, seed: 8, wt: 700 });
    if (tp > 0) {
      const fa = ctx.globalAlpha; ctx.globalAlpha = fa * clamp(tp * 3) * inkA * .55;
      wash(S.ellC(tx - 46, 18, 13, 7), C().blush, { dx: 0, dy: 0, tex: false });
      wash(S.ellC(tx + 46, 18, 13, 7), C().blush, { dx: 0, dy: 0, tex: false });
      ctx.globalAlpha = fa * clamp(tp * 3) * inkA;
      const lx = (o.look ?? 0) * 5;
      P.face.eyes(tx - 26 + lx, 2, tx + 26 + lx, 2, o.mood ?? 'open', o.blink ?? 0);
      P.face.mouth(tx + lx * .6, 26, o.mouth ?? 'smile');
      ctx.globalAlpha = fa;
    }
    ctx.globalAlpha = base;
    ctx.restore();
  };

  /** A paper plane (nose along +x). o: flip (-1 mirrors), face (true), fill */
  P.plane = function (x, y, ang, s, o = {}) {
    SK.at(x, y, ang, [s, s * (o.flip ?? 1)], () => {
      const fill = o.fill ?? '#f2a472';
      const top = [[62, 0], [-48, -34], [-26, 2]], bot = [[62, 0], [-26, 2], [-44, 24]];
      wash(S.poly(bot, true), mix(fill, C().orangeDk, .35), { seed: 21, dx: 3, dy: 3, tex: false });
      wash(S.poly(top, true), fill, { seed: 22, dx: 3, dy: 3 });
      ink(S.poly(top, true), { w: 4.2, seed: 23 }); ink(S.poly(bot, true), { w: 4.2, seed: 24 });
      ink(S.line(62, 0, -36, 9), { w: 3, seed: 25, dbl: false });
      if (o.face !== false) {
        wash(S.ellC(-6, -10, 3.6, 4.4), C().ink, { dx: 0, dy: 0, tex: false, jit: .3 });
        wash(S.ellC(10, -8, 3.6, 4.4), C().ink, { dx: 0, dy: 0, tex: false, jit: .3 });
        ink(S.arc(3, -8, 7, Math.PI * .25, Math.PI * .75), { w: 2.6, seed: 26, dbl: false });
      }
    });
  };

  /* ------------------------------------------------------------ people */
  // Hand targets relative to the seat origin; arms are 2-bone strokes from the shoulders.
  P.POSE = {
    type: { F: [212, 22], B: [182, 26] }, typeS: { F: [204, 22], B: [172, 26] }, rest: { F: [70, 44], B: [-40, 50] },
    shrug: { F: [118, -86], B: [-112, -86] }, cheer: { F: [178, -236], B: [-152, -228] },
    hold: { F: [150, -48], B: [124, -36] }, wave: { F: [104, -236], B: [-40, 50] },
    chin: { F: [58, -92], B: [-40, 50] }, wow: { F: [150, -70], B: [-136, -66] },
  };
  /** keys: [[t, poseName], ...] -> {F, B}; each change springs over .32 s */
  P.poseAt = function (t, keys) {
    let a = keys[0];
    for (let i = 0; i < keys.length; i++) if (keys[i][0] <= t) a = keys[i];
    if (t < a[0]) return P.POSE[a[1]];
    const prev = keys[keys.indexOf(a) - 1];
    const from = prev ? P.POSE[prev[1]] : P.POSE[a[1]], to = P.POSE[a[1]];
    const u = E.back(clamp((t - a[0]) / .32));
    return { F: [lerp(from.F[0], to.F[0], u), lerp(from.F[1], to.F[1], u)], B: [lerp(from.B[0], to.B[0], u), lerp(from.B[1], to.B[1], u)] };
  };
  function limb(sx, sy, hx, hy, bend, seed, p, w = 6.5) {
    const mx = (sx + hx) / 2, my = (sy + hy) / 2, L = Math.hypot(hx - sx, hy - sy) || 1;
    const nx = -(hy - sy) / L, ny = (hx - sx) / L, k = Math.max(0, 150 - L) * .55 * bend;
    ink(S.path([['M', sx, sy], ['Q', mx + nx * k, my + ny * k, hx, hy]]), { w, seed, p });
  }
  /**
   * A seated doodle person facing +x; origin = seat centre, feet at +250.
   * o: x, y, s, hair ('spiky'|'bun'), hairCol, glasses, shirt, mood, mouth, blink, arms {F,B},
   *    p (draw-on), wave (phase; waves the front hand), headTilt, bounce, stool (true)
   */
  P.person = function (o) {
    const p = o.p ?? 1; if (p <= 0) return;
    const ctx = SK.ctx();
    ctx.save(); ctx.translate(o.x, o.y + (o.bounce ?? 0)); ctx.scale(o.s ?? 1, o.s ?? 1);
    const pp = (a, b) => clamp((p - a) / (b - a));
    if (o.stool !== false) {
      ink(S.line(-48, 82, -58, 250), { w: 5, seed: 101, p: pp(0, .3) });
      ink(S.line(48, 82, 60, 250), { w: 5, seed: 102, p: pp(0, .3) });
      ink(S.line(-52, 180, 54, 180), { w: 4, seed: 103, p: pp(.1, .35) });
      wash(S.ellC(0, 74, 80, 17), C().woodDk, { seed: 104, alpha: pp(.1, .3) });
      ink(S.ell(0, 74, 80, 17), { w: 4.5, seed: 105, p: pp(0, .3) });
    }
    for (const [hx, kx, fx, i] of [[10, 118, 122, 0], [-14, 96, 92, 1]]) {
      ink(S.path([['M', hx, 58], ['Q', kx - 30, 50 + i * 6, kx, 66 + i * 6], ['L', fx, 238]]), { w: 6.5, seed: 110 + i, p: pp(.1, .4) });
      wash(S.ellC(fx + 16, 243, 26, 12), C().ink, { dx: 0, dy: 0, tex: false, alpha: pp(.3, .45) });
    }
    const arms = o.arms ?? P.POSE.rest;
    const shB = [-40, -34], shF = [44, -34];
    if (p > .5) {
      limb(shB[0], shB[1], arms.B[0], arms.B[1], -1, 120, pp(.5, .8));
      wash(S.ellC(arms.B[0], arms.B[1], 14, 13), C().skin, { dx: 0, dy: 0, tex: false, alpha: pp(.7, .8) });
      ink(S.ell(arms.B[0], arms.B[1], 14, 13), { w: 4.5, seed: 121, p: pp(.7, .85), dbl: false });
    }
    const body = S.path([['M', -62, -44], ['Q', -84, 18, -72, 76], ['L', 72, 76], ['Q', 84, 18, 62, -44], ['Q', 0, -74, -62, -44]]);
    wash(body, o.shirt ?? C().shirtA, { seed: 130, alpha: pp(.25, .45) });
    ink(body, { w: 6, seed: 131, p: pp(.15, .45) });
    ctx.save(); ctx.translate(8, -146); ctx.rotate(o.headTilt ?? 0);
    wash(S.ellC(0, 0, 84, 80), C().skin, { seed: 140, alpha: pp(.35, .55), texCol: 'rgba(255,255,255,.25)' });
    ink(S.ell(0, 0, 84, 80, -2.2, .28), { w: 6, seed: 141, p: pp(.3, .55) });
    const ha = pp(.5, .65);
    if (ha > 0) {
      if (o.hair === 'bun') {
        const hc = o.hairCol ?? C().hairB;
        const cap = S.path([['M', -84, 4], ['Q', -96, -72, -10, -84], ['Q', 64, -88, 82, -26], ['Q', 30, -52, -14, -40], ['Q', -52, -28, -84, 4]]);
        wash(cap, hc, { seed: 150, alpha: ha }); ink(cap, { w: 5, seed: 151, p: ha });
        wash(S.ellC(-38, -98, 34, 30), hc, { seed: 152, alpha: ha }); ink(S.ell(-38, -98, 34, 30), { w: 5, seed: 153, p: ha });
        ink(S.arc(-38, -98, 18, 3.6, 5.4), { w: 3, seed: 154, p: ha, dbl: false, alpha: .6 });
      } else if (o.hair !== 'none') {
        const pts = [[-86, -40], [-70, -64], [-72, -96], [-44, -84], [-30, -118], [-6, -90], [18, -122], [30, -88], [58, -106], [58, -72], [86, -64], [72, -40]];
        const cmds = [['M', -80, -10], ...pts.map(q => ['L', q[0], q[1]]), ['Q', 20, -62, -30, -52], ['Q', -60, -40, -80, -10]];
        const hp = S.path(cmds); wash(hp, o.hairCol ?? C().hairA, { seed: 155, alpha: ha, texCol: 'rgba(255,255,255,.12)' }); ink(hp, { w: 5, seed: 156, p: ha });
      }
    }
    const fa = pp(.6, .8);
    if (fa > 0) {
      const b0 = ctx.globalAlpha; ctx.globalAlpha = b0 * fa * .5;
      wash(S.ellC(-20, 30, 14, 8), C().blush, { dx: 0, dy: 0, tex: false }); wash(S.ellC(66, 30, 13, 8), C().blush, { dx: 0, dy: 0, tex: false });
      ctx.globalAlpha = b0 * fa;
      P.face.eyes(4, 0, 50, 0, o.mood ?? 'open', o.blink ?? 0, 1.05);
      if (o.glasses) {
        ink(S.ell(4, 0, 22, 21), { w: 4, seed: 160, dbl: false }); ink(S.ell(52, 0, 22, 21), { w: 4, seed: 161, dbl: false });
        ink(S.line(26, -2, 30, -2), { w: 4, seed: 162, dbl: false }); ink(S.line(-18, -3, -52, -10), { w: 4, seed: 163, dbl: false });
      }
      ink(S.path([['M', 34, 14], ['Q', 40, 22, 30, 24]]), { w: 3.5, seed: 164, dbl: false, alpha: .7 });
      P.face.mouth(30, 44, o.mouth ?? 'smile', 1.05);
      ctx.globalAlpha = b0;
    }
    ctx.restore();
    if (p > .5) {
      let F = arms.F;
      if (o.wave) F = [F[0] + Math.sin(o.wave * TAU) * 26, F[1] + Math.abs(Math.cos(o.wave * TAU)) * -6];
      limb(shF[0], shF[1], F[0], F[1], 1, 122, pp(.5, .8));
      wash(S.ellC(F[0], F[1], 14, 13), C().skin, { dx: 0, dy: 0, tex: false, alpha: pp(.7, .8) });
      ink(S.ell(F[0], F[1], 14, 13), { w: 4.5, seed: 123, p: pp(.7, .85), dbl: false });
    }
    ctx.restore();
  };

  /* ------------------------------------------------------------ furniture & objects */
  /** laptop centred on its screen. Returns the inner screen rect {X, Y, w, h} for drawing on it. */
  P.laptop = function (x, y, o = {}) {
    const p = o.p ?? 1, sw = o.w ?? 340, sh = o.h ?? 260;
    const X = x - sw / 2, Y = y - sh / 2;
    const scr = S.rrect(X, Y, sw, sh, 16);
    wash(scr, '#bfb6a8', { seed: 200, dx: 5, dy: 5, alpha: clamp(p * 2 - .6), tex: false });
    const inner = S.rrect(X + 16, Y + 16, sw - 32, sh - 32, 8);
    const sc = o.screenCol ?? C().screenOff;
    wash(inner, sc, { seed: 201, dx: 0, dy: 0, alpha: clamp(p * 2 - .8), tex: sc !== C().screen });
    ink(scr, { w: 5.5, seed: 202, p });
    ink(inner, { w: 3.5, seed: 203, p: clamp(p * 1.5 - .3), dbl: false });
    const base = S.poly([[X - 22, y + sh / 2], [X + sw + 22, y + sh / 2], [X + sw + 44, y + sh / 2 + 30], [X - 44, y + sh / 2 + 30]], true);
    wash(base, '#d7cfc2', { seed: 204, alpha: clamp(p * 2 - .6) });
    ink(base, { w: 5, seed: 205, p: clamp(p * 1.4 - .2) });
    ink(S.line(X + 20, y + sh / 2 + 14, X + sw - 20, y + sh / 2 + 14), { w: 3, seed: 206, p: clamp(p * 1.4 - .4), dbl: false, alpha: .5 });
    return { X: X + 16, Y: Y + 16, w: sw - 32, h: sh - 32 };
  };
  P.table = function (x0, x1, y, floor, p = 1, seed = 300) {
    const top = S.poly([[x0, y], [x1, y], [x1 + 10, y + 26], [x0 - 10, y + 26]], true);
    wash(top, C().wood, { seed, alpha: clamp(p * 2 - .5) });
    ink(top, { w: 5.5, seed: seed + 1, p });
    ink(S.line(x0 + 20, y + 26, x0 + 26, floor), { w: 5.5, seed: seed + 2, p: clamp(p * 2 - .6) });
    ink(S.line(x1 - 20, y + 26, x1 - 26, floor), { w: 5.5, seed: seed + 3, p: clamp(p * 2 - .6) });
  };
  P.floor = function (x0, x1, y, p = 1, seed = 350) {
    ink(S.line(x0, y, x1, y, 3), { w: 4.5, seed, p, alpha: .75 });
    for (let i = 0; i < 6; i++) { const xx = lerp(x0 + 60, x1 - 60, i / 5 + (rnd(seed + i) - .5) * .1); ink(S.line(xx, y + 18 + rnd(i) * 10, xx + 50, y + 18 + rnd(i) * 10), { w: 3, seed: seed + 10 + i, p, alpha: .35, dbl: false }); }
  };
  P.lightbulb = function (x, y, s, glow = 0) {
    SK.at(x, y, 0, s, () => {
      if (glow > 0) for (let i = 0; i < 9; i++) { const a = -Math.PI / 2 + (i - 4) * .36; ink(S.line(Math.cos(a) * 62, Math.sin(a) * 62 - 6, Math.cos(a) * (84 + 10 * glow), Math.sin(a) * (84 + 10 * glow) - 6), { w: 5, col: C().orange, seed: 500 + i, alpha: glow, dbl: false }); }
      const g = S.path([['M', -14, 34], ['Q', -16, 16, -30, 2], ['C', -54, -28, -30, -64, 0, -64], ['C', 30, -64, 54, -28, 30, 2], ['Q', 16, 16, 14, 34], ['Z']]);
      wash(g, C().yellow, { seed: 510 }); ink(g, { w: 5, seed: 511 });
      SK.sketchRect(-15, 36, 30, 20, { w: 4, seed: 512, over: 2 });
      ink(S.path([['M', -8, 30], ['L', -8, 6], ['Q', 0, -6, 8, 6], ['L', 8, 30]]), { w: 3, seed: 513, dbl: false, alpha: .7 });
    });
  };
  /** o: rot, p (draw-on), flame (0..1) */
  P.rocket = function (x, y, s, o = {}) {
    SK.at(x, y, o.rot ?? 0, s, () => {
      const p = o.p ?? 1, flame = o.flame ?? 0;
      if (flame > 0) {
        const f = S.path([['M', -20, 70], ['Q', -28, 110 + 40 * flame, 0, 130 + 60 * flame * (0.8 + .2 * Math.sin(SK.T * 60))], ['Q', 28, 110 + 40 * flame, 20, 70], ['Z']]);
        wash(f, C().orange, { seed: 540, dx: 0, dy: 0 }); ink(f, { w: 4, seed: 541 });
        wash(S.path([['M', -9, 72], ['Q', -10, 96, 0, 102 + 25 * flame], ['Q', 10, 96, 9, 72], ['Z']]), C().yellow, { seed: 542, dx: 0, dy: 0, tex: false });
      }
      const body = S.path([['M', 0, -110], ['C', 42, -70, 44, 20, 32, 70], ['L', -32, 70], ['C', -44, 20, -42, -70, 0, -110]]);
      const finL = S.path([['M', -34, 20], ['Q', -70, 40, -64, 88], ['L', -30, 64]]), finR = S.path([['M', 34, 20], ['Q', 70, 40, 64, 88], ['L', 30, 64]]);
      const fa = clamp(p * 2 - .8);
      wash(finL, C().orange, { seed: 543, alpha: fa }); wash(finR, C().orange, { seed: 544, alpha: fa });
      ink(finL, { w: 5, seed: 545, p: clamp(p * 1.6 - .5) }); ink(finR, { w: 5, seed: 546, p: clamp(p * 1.6 - .5) });
      wash(body, C().cream, { seed: 547, alpha: fa, texCol: 'rgba(0,0,0,.05)' });
      ink(body, { w: 5.5, seed: 548, p: clamp(p * 1.3) });
      wash(S.ellC(0, -22, 20, 20), C().teal, { seed: 549, alpha: fa, dx: 2, dy: 2 });
      ink(S.ell(0, -22, 20, 20), { w: 5, seed: 550, p: clamp(p * 2 - .7) });
      ink(S.arc(0, -82, 22, Math.PI * .15, Math.PI * .85), { w: 4, seed: 551, p: clamp(p * 2 - .9), dbl: false });
    });
  };
  /** open: 0 locked .. 1 shackle sprung */
  P.padlock = function (x, y, s, open = 0) {
    SK.at(x, y, 0, s, () => {
      const ctx = SK.ctx();
      const sh = S.path([['M', -28, -6], ['L', -28, -38], ['C', -28, -76, 28, -76, 28, -38], ['L', 28, -6]]);
      ctx.save(); ctx.translate(28, -6 - open * 26); ctx.rotate(-open * .5); ctx.translate(-28, 6);
      ink(sh, { w: 9, seed: 560, col: C().inkSoft }); ctx.restore();
      const b = S.rrect(-46, -8, 92, 74, 10);
      wash(b, C().coin, { seed: 561 }); ink(b, { w: 5.5, seed: 562 });
      wash(S.ellC(0, 20, 9, 10), C().ink, { dx: 0, dy: 0, tex: false }); ink(S.line(0, 26, 0, 44), { w: 6, seed: 563, dbl: false });
    });
  };
  /** a coin that can spin (spin in radians; face shows when cos(spin) is large). o: label, rot */
  P.coin = function (x, y, r, spin = 0, o = {}) {
    const sx = Math.max(.08, Math.abs(Math.cos(spin)));
    SK.at(x, y, o.rot ?? 0, [sx, 1], () => {
      wash(S.ellC(-7, 5, r, r), '#d49a2a', { seed: 600, dx: 0, dy: 0, tex: false });
      wash(S.ellC(0, 0, r, r), C().coin, { seed: 601, dx: 0, dy: 0 });
      ink(S.ell(0, 0, r, r), { w: 5.5, seed: 602 });
      ink(S.ell(0, 0, r * .78, r * .78, 1, .1), { w: 3.2, seed: 603, dbl: false, alpha: .6 });
      if (sx > .45 && o.label) txt(o.label, 0, 3, { size: r * .78, wt: 700, col: C().ink, seed: 9, wob: .4 });
      ink(S.arc(-r * .35, -r * .35, r * .35, 3.5, 4.4), { w: 5, col: 'rgba(255,255,255,.85)', seed: 604, dbl: false });
    });
  };
  /** a rubber stamp / sticker. lines: [{t, y, size, font?, wt?, col?, ls?}]; o: w, h, fill, alpha */
  P.stamp = function (x, y, rot, s, lines, col, o = {}) {
    SK.at(x, y, rot, s, () => {
      const w = o.w ?? 440, h = o.h ?? 150;
      SK.alpha(o.alpha ?? 1, () => {
        if (o.fill) wash(S.rrect(-w / 2, -h / 2, w, h, 16), o.fill, { seed: 700, dx: 4, dy: 4 });
        ink(S.rrect(-w / 2, -h / 2, w, h, 16), { w: 7, col, seed: 701, jit: 2.5 });
        if (!o.fill) ink(S.rrect(-w / 2 + 12, -h / 2 + 12, w - 24, h - 24, 10), { w: 3.5, col, seed: 702, dbl: false });
        lines.forEach((l, i) => txt(l.t, l.x ?? 0, l.y, { size: l.size, font: l.font ?? SK.FONT_PRINT, wt: l.wt ?? 400, col: l.col ?? col, ls: l.ls ?? 2, seed: 20 + i, wob: .5 }));
      });
    });
  };
  /** a pointing hand coming down from above; the fingertip is at (x, y) */
  P.pokeHand = function (x, y, rot = 0, s = 1, sleeve) {
    SK.at(x, y, rot, s, () => {
      const sl = S.poly([[-60, -520], [60, -520], [54, -150], [-54, -150]], true);
      wash(sl, sleeve ?? C().shirtB, { seed: 800 }); ink(sl, { w: 6, seed: 801 });
      const palm = S.path([['M', -50, -150], ['Q', -62, -80, -40, -50], ['L', -12, -40], ['L', -12, 0], ['Q', 0, 14, 12, 0], ['L', 12, -46], ['Q', 50, -56, 48, -100], ['Q', 50, -130, 46, -150], ['Z']]);
      wash(palm, C().skin, { seed: 802 }); ink(palm, { w: 6, seed: 803 });
      ink(S.path([['M', 12, -70], ['Q', 34, -72, 36, -86]]), { w: 4, seed: 804, dbl: false });
      ink(S.path([['M', 10, -94], ['Q', 36, -96, 40, -112]]), { w: 4, seed: 805, dbl: false });
    });
  };
  /**
   * A browser window centred on (x, y). Returns the content rect {X, Y, w, h} below the bar.
   * o: w, h, p (draw-on), url, urlP (write-on of the URL), dotsAt (time the traffic lights pop), t
   */
  P.browser = function (x, y, o = {}) {
    const w = o.w ?? 1000, h = o.h ?? 640, X = x - w / 2, Y = y - h / 2, p = o.p ?? 1, t = o.t ?? SK.T;
    const win = S.rrect(X, Y, w, h, 26);
    wash(win, '#ffffff', { seed: 1500, dx: 8, dy: 8, alpha: clamp(p * 2 - .4), texCol: 'rgba(0,0,0,.025)' });
    ink(win, { w: 7, seed: 1501, p });
    ink(S.line(X, Y + 76, X + w, Y + 76), { w: 5, seed: 1502, p: clamp(p * 1.5 - .3) });
    [C().heart, C().yellow, C().green].forEach((c, i) => {
      const pp = o.dotsAt === undefined ? clamp(p * 2 - 1) : pop(t, o.dotsAt + i * .06, .3);
      if (pp > 0) { wash(S.ellC(X + 42 + i * 34, Y + 38, 10 * pp, 10 * pp), c, { dx: 0, dy: 0, tex: false }); ink(S.ell(X + 42 + i * 34, Y + 38, 10 * pp, 10 * pp), { w: 3, seed: 1510 + i, dbl: false }); }
    });
    const url = S.rrect(X + 160, Y + 16, w - 340, 46, 23);
    wash(url, '#f1ece2', { seed: 1503, dx: 0, dy: 0, alpha: clamp(p * 2 - .6), tex: false }); ink(url, { w: 4, seed: 1504, p: clamp(p * 1.5 - .4) });
    if (o.url) txt(o.url, X + 160 + (w - 340) / 2, Y + 40, { size: 36, font: SK.FONT_PRINT, wt: 400, p: o.urlP ?? 1, seed: 60, ls: 1 });
    return { X, Y: Y + 76, w, h: h - 76 };
  };
  /** a thought cloud centred on (x, y) with trailing bubbles toward (tx, ty). s scales, a fades. */
  P.thoughtBubble = function (x, y, rx, ry, s, o = {}) {
    if (s <= 0) return;
    const cloud = [];
    for (let i = 0; i < 9; i++) { const a = i / 9 * TAU; cloud.push([Math.cos(a) * rx, Math.sin(a) * ry]); }
    const cpts = [];
    for (let i = 0; i < 9; i++) { const q0 = cloud[i], q1 = cloud[(i + 1) % 9]; const m = [(q0[0] + q1[0]) / 2 * 1.22, (q0[1] + q1[1]) / 2 * 1.3]; cpts.push(...S.path([['M', q0[0], q0[1]], ['Q', m[0], m[1], q1[0], q1[1]]]).slice(i ? 1 : 0)); }
    SK.at(x, y, 0, s, () => {
      wash(cpts, '#ffffff', { seed: 1200, dx: 4, dy: 4, texCol: 'rgba(0,0,0,.03)' });
      ink(cpts, { w: 5, seed: 1201, p: clamp(s * 1.4) });
      if (o.inside) o.inside();
    });
    (o.trail || []).forEach(([bx, by, r], i) => { wash(S.ellC(bx, by, r, r), '#fff', { dx: 2, dy: 2, tex: false, alpha: clamp(s) }); ink(S.ell(bx, by, r * s, r * s), { w: 4, seed: 1220 + i }); });
  };
  /** a confetti burst from (x, y) that started at t0 (age = t - t0). n pieces, fades over life s. */
  P.confetti = function (x, y, age, o = {}) {
    if (age < 0) return;
    const ctx = SK.ctx(), n = o.n ?? 70, life = o.life ?? 1.8;
    const cols = o.cols ?? [C().orange, C().yellow, C().teal, C().heart, C().lilac, C().shirtA];
    for (let i = 0; i < n; i++) {
      const r = mulberry(i * 99 + (o.seed ?? 7)), ang = -Math.PI / 2 + (r() - .5) * (o.spread ?? 2.6), v = 900 + r() * 1100;
      const px = x + Math.cos(ang) * v * age * .9, py = y + Math.sin(ang) * v * age + 900 * age * age;
      const a = clamp(life - age); if (a <= 0) continue;
      ctx.save(); ctx.translate(px, py); ctx.rotate(age * (r() * 14 - 7)); ctx.globalAlpha *= a;
      ctx.fillStyle = cols[i % cols.length]; ctx.scale(1, Math.cos(age * 9 + i));
      if (i % 3 === 0) { ctx.beginPath(); ctx.arc(0, 0, 9, 0, TAU); ctx.fill(); } else ctx.fillRect(-12, -6, 24, 12);
      ctx.restore();
    }
  };
  /* ------------------------------------------------------------ architecture (real-estate films) */
  /**
   * An architectural elevation of a house, origin at the middle of its ground line, drawn in
   * order (walls, roof, windows, door, details) so p 0..1 reads as an architect's pen.
   * o: kind ('colonial'|'bungalow'|'modern'), w, p, col (line), lw, wall, roof, trim, lit (0..1
   *    warm windows), litCol, garage, chimney, trees, seed
   */
  P.house = function (x, y, o = {}) {
    // drawn at a 520-unit design width and scaled, so a thumbnail is the same house, smaller;
    // lw stays in screen units
    const W0 = 520, sc = (o.w ?? W0) / W0, w = W0;
    const kind = o.kind ?? 'colonial', p = o.p ?? 1, col = o.col ?? C().ink, lw = (o.lw ?? 3.4) / sc;
    const wall = o.wall ?? '#ffffff', roofC = o.roof ?? mix(col, '#ffffff', .78), lit = o.lit ?? 0, litCol = o.litCol ?? '#f3c46b';
    const seed = o.seed ?? 900;
    const L = (pts, a, b, extra = {}) => ink(pts, { w: lw, col, seed: seed + (extra.k ?? 0), p: clamp((p - a) / (b - a)), dbl: false, taper: false, ...extra });
    const fillA = clamp((p - .15) / .35);
    SK.at(x, y, 0, sc, () => {
      const hw = w / 2;
      const stories = kind === 'colonial' ? 2 : kind === 'modern' ? 2 : 1;
      const h = kind === 'bungalow' ? 190 : 330;
      // trees behind
      if (o.trees) for (const [tx, s, k] of [[-hw - 110, 1, 1], [hw + 120, .85, 2]]) {
        const cy = -150 * s - 60;
        wash(S.ellC(tx, cy, 95 * s, 110 * s), mix(col, '#ffffff', .88), { seed: seed + 40 + k, dx: 0, dy: 0, tex: false, alpha: fillA });
        L(S.ell(tx, cy, 95 * s, 110 * s, -1.2, .1), .05, .4, { k: 40 + k, w: lw * .8 });
        L(S.line(tx, cy + 60 * s, tx, 0), .1, .35, { k: 50 + k, w: lw * .9 });
      }
      // body + roof fills
      let roof;
      if (kind === 'modern') {
        wash(S.poly([[-hw, 0], [hw * .35, 0], [hw * .35, -h], [-hw, -h]], true), wall, { seed: seed + 1, dx: 0, dy: 0, tex: false, alpha: fillA });
        wash(S.poly([[hw * .35, 0], [hw, 0], [hw, -h * .58], [hw * .35, -h * .58]], true), mix(col, '#ffffff', .9), { seed: seed + 2, dx: 0, dy: 0, tex: false, alpha: fillA });
        roof = S.poly([[-hw - 24, -h], [hw * .35 + 24, -h], [hw * .35 + 24, -h - 22], [-hw - 24, -h - 22]], true);
      } else {
        const peak = kind === 'bungalow' ? 120 : 165;
        wash(S.poly([[-hw, 0], [hw, 0], [hw, -h], [-hw, -h]], true), wall, { seed: seed + 1, dx: 0, dy: 0, tex: false, alpha: fillA });
        roof = S.poly([[-hw - 30, -h], [0, -h - peak], [hw + 30, -h]], true);
      }
      wash(roof, roofC, { seed: seed + 3, dx: 0, dy: 0, tex: false, alpha: fillA });
      // garage wing
      const gw = o.garage ? 230 : 0;
      if (o.garage) {
        wash(S.poly([[hw, 0], [hw + gw, 0], [hw + gw, -150], [hw, -150]], true), wall, { seed: seed + 4, dx: 0, dy: 0, tex: false, alpha: fillA });
        L(S.poly([[hw, -150], [hw + gw, -150], [hw + gw, 0]]), .2, .45, { k: 4 });
        L(S.poly([[hw - 10, -150], [hw + gw / 2, -205], [hw + gw + 16, -150]]), .3, .5, { k: 5 });
        for (let i = 0; i < 5; i++) L(S.line(hw + 32, -110 + i * 22, hw + gw - 32, -110 + i * 22), .6, .8, { k: 6 + i, w: lw * .6 });
        L(S.poly([[hw + 32, 0], [hw + 32, -120], [hw + gw - 32, -120], [hw + gw - 32, 0]]), .55, .75, { k: 12 });
      }
      // walls + ground
      L(S.line(-hw - (o.trees ? 260 : 60), 0, hw + gw + (o.trees ? 260 : 60), 0), 0, .25, { k: 13 });
      if (kind === 'modern') L(S.poly([[-hw, 0], [-hw, -h], [hw * .35, -h], [hw * .35, -h * .58], [hw, -h * .58], [hw, 0]]), .05, .35, { k: 14 });
      else L(S.poly([[-hw, 0], [-hw, -h], [hw, -h], [hw, 0]]), .05, .35, { k: 14 });
      L(roof, .25, .5, { k: 15 });
      if (o.chimney && kind !== 'modern') {
        const cx = hw * .5;
        wash(S.poly([[cx, -h - 60], [cx + 44, -h - 60], [cx + 44, -h - 150], [cx, -h - 150]], true), roofC, { seed: seed + 16, dx: 0, dy: 0, tex: false, alpha: fillA });
        L(S.poly([[cx, -h - 64], [cx, -h - 150], [cx + 44, -h - 150], [cx + 44, -h - 42]]), .4, .55, { k: 16 });
      }
      // windows
      const win = (wx, wy, ww, wh, k, mull = true) => {
        wash(S.poly([[wx, wy], [wx + ww, wy], [wx + ww, wy + wh], [wx, wy + wh]], true), mix('#ffffff', litCol, lit), { seed: seed + 100 + k, dx: 0, dy: 0, tex: false, alpha: clamp((p - .45) / .3) });
        L(S.poly([[wx, wy], [wx + ww, wy], [wx + ww, wy + wh], [wx, wy + wh]], true), .45, .75, { k: 100 + k, w: lw * .85 });
        if (mull) { L(S.line(wx + ww / 2, wy, wx + ww / 2, wy + wh), .6, .85, { k: 200 + k, w: lw * .5 }); L(S.line(wx, wy + wh / 2, wx + ww, wy + wh / 2), .6, .85, { k: 300 + k, w: lw * .5 }); }
      };
      if (kind === 'modern') {
        win(-hw + 40, -h + 40, hw * 1.35 - 80, 110, 1, false);
        win(-hw + 40, -h * .5 + 10, 150, h * .5 - 50, 2, false);
        win(hw * .45, -h * .58 + 40, hw * .45, 90, 3, false);
      } else {
        if (kind === 'bungalow') { win(-hw + 50, -h + 45, 100, 90, 0); win(hw - 150, -h + 45, 100, 90, 1); }
        else { // colonial: five windows up, two either side of the portico down
          [-215, -125, -40, 45, 135].forEach((wx, k) => win(wx, -h + 40, 80, 105, k));
          [-220, 130].forEach((wx, k) => win(wx, -h / 2 + 30, 90, 110, 10 + k));
        }
      }
      // door (+ portico / porch)
      const dx0 = kind === 'modern' ? -hw * .15 : -38, dw = kind === 'modern' ? 70 : 76, dh = kind === 'bungalow' ? 120 : 140;
      wash(S.poly([[dx0, 0], [dx0 + dw, 0], [dx0 + dw, -dh], [dx0, -dh]], true), mix(col, '#ffffff', .35), { seed: seed + 30, dx: 0, dy: 0, tex: false, alpha: clamp((p - .6) / .3) });
      L(S.poly([[dx0, 0], [dx0, -dh], [dx0 + dw, -dh], [dx0 + dw, 0]]), .6, .85, { k: 30 });
      if (kind === 'colonial') { L(S.poly([[-80, -dh - 6], [0, -dh - 52], [80, -dh - 6]]), .7, .9, { k: 31 }); L(S.line(-66, -dh - 8, -66, 0), .75, .9, { k: 32 }); L(S.line(66, -dh - 8, 66, 0), .75, .9, { k: 33 }); }
      if (kind === 'bungalow') { L(S.line(-hw - 10, -dh - 20, hw + 10, -dh - 20), .65, .85, { k: 34 }); for (const px of [-hw + 10, -110, 110, hw - 10]) L(S.line(px, -dh - 20, px, 0), .7, .9, { k: 35 + px }); }
      SK.ctx().fillStyle = col; if (p > .9) { SK.ctx().beginPath(); SK.ctx().arc(dx0 + dw - 14, -dh / 2, 4, 0, TAU); SK.ctx().fill(); }
      if (o.garden) { // curb appeal: shrubs along the front and a walkway to the door
        const shrubA = clamp((p - .75) / .25), shrubCol = o.shrub ?? mix(col, '#ffffff', .82);
        for (const [bx, r] of [[-hw + 40, 34], [-hw + 105, 26], [hw - 105, 26], [hw - 40, 34]]) {
          if (kind === 'modern' && bx > 0) continue;
          wash(S.ellC(bx, -r * .8, r * 1.3, r), shrubCol, { seed: seed + 60 + bx, dx: 0, dy: 0, tex: false, alpha: shrubA });
          L(S.arc(bx, -r * .8, r * 1.3, Math.PI * 1.02, Math.PI * 1.98, r), .75, 1, { k: 60 + bx, w: lw * .8 });
        }
      }
    });
  };

  P.inv = inv; // re-export for film scripts that destructure from SK.P
})();
