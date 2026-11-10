/* The pool frame, moving: thirteen seconds, two shots. Wide (0-9.85): the rabbits on the deck wave
   hello, the pigs in the water wave back, the rabbits jump in one after another -- the small one,
   the smallest, the big one -- and everybody bobs in the wash. Then the camera leans in, a splash
   covers the lens, and as the water runs off it we are close on the four children (10-13),
   throwing water at each other: the pigs on the left, the rabbits on the right.

   The drawing is film-replica.js's (every figure drawn where it stands in the still); what is new
   is that each figure takes a pose, and the pose is a pure function of t:
     * an arm is a group swung about its shoulder (`swing`), and a wave is that angle over time;
     * a jump (`leap`) is a crouch, an arc under constant gravity to a spot in the pool, and a plunge
       that settles into a bob; the figure is the still's figure, slid, leant and squashed (`moved`);
     * the water line of a swimmer never moves -- the figure does, so a plunge shows more of it
       tinted -- and a rabbit is drawn through the same `inWater` from the start (on the deck it
       stands above its water line, so nothing is tinted until its feet go in);
     * a splash is rings on the surface (under the swimmers), a crown and drops (over them).
   Each figure resets the pen's seed, so one figure's pose never changes another's wobble.

   The camera is the film's own (CAM, set every frame from t), not the engine's: `inWater` lays a
   layer down in screen pixels, so the view has to be applied inside that layer too. The close shot
   is the same pool at 2.2x on its back wall, with the children moved to places of their own. */
(function () {
  'use strict';
  const { S, TAU, E, clamp, inv, tw, lerp } = SK;
  // the clean look, with the pen's wobble back on (still: nothing boils)
  SK.setStyle('clean', { grain: 0, vignette: 0, handheld: 0, jit: 1 });
  const C = {
    sky: '#97c5f7', fence: '#d7e7fc', lawn: '#89d080', lawnDk: '#6da469', tuft: '#72b869', petal: '#f8ee0c',
    deck: '#e7e99e', deckDk: '#b7b87f',
    tile: '#7be4e1', grout: '#c7edf9', rim: '#5b9c99',
    water: '#4ab4c2', floor: '#43adbb', deep: '#3c9fae', floorLine: '#3aa2b0', sunk: '#66c2cf', shade: '#3398aa',
    over: '#419eb4', // what the water lays over anything standing in it, at OVER
    rail: '#1f4b73', trunk: '#65584f', leaf: '#68a945', leafMid: '#5b9c38', leafDk: '#4a8c2b',
    pig: '#ffb8e3', pigEdge: '#ea98c9', limb: '#f3c3ea', cheek: '#fc9dd7', nostril: '#d57fae', lilac: '#d1a2e1',
    smile: '#d14a8e', smileKid: '#cf5b97', smileSoft: '#bb6c9b',
    suit: '#ff9f73', suitDk: '#ea854c', red: '#ec6873', redDk: '#d8485a', band: '#feac1a', bandDk: '#f39709',
    trunks: '#5ca1dd', trunksDk: '#3f7fc0',
    rabbit: '#fffbdd', rabbitEdge: '#d5d0b9', paw: '#fffbe0', nose: '#faa8d8', noseSoft: '#fdaca8', blush: '#fee5d1',
    yellow: '#fbf756', yellowDk: '#cbcc09', indigo: '#6265b2', indigoDk: '#4e4e8c', stripe: '#ef7b7b', stripeDk: '#c1645f',
    button: '#beb899', lid: '#cfc8ae', ink: '#141210',
    foam: '#e3f8fb', foamEdge: '#a8dfe8', ring: '#a5e6ee',
  };
  const OVER = .71;
  SK.setGround('sky', { paper: C.sky });

  /* ---- the pen: flat fills and even lines; hand() gives a line the wobble of a drawn one, and one
     wobble serves a shape's fill and its outline, so they never part */
  let SEED = 0;
  const hand = (pts, amp = 1.2) => SK.jitter(pts, ++SEED, amp);
  const fill = (pts, col) => SK.wash(pts, col, { tex: false, jit: 0 });
  const line = (pts, col, w = 4.5) => SK.ink(pts, { w, col, taper: false, dbl: false, jit: 0 });
  const closed = (pts, amp) => hand([...pts, pts[0]], amp);
  const paint = (q, col, edge, w) => { if (col) fill(q, col); if (edge) line(q, edge, w); return q; };
  const shape = (pts, col, edge, w) => paint(closed(pts), col, edge, w);
  const ell = (x, y, rx, ry, col, edge, w, rot = 0) => shape(S.ellC(x, y, rx, ry, rot), col, edge, w);
  const dot = (x, y, r, col) => fill(S.ellC(x, y, r, r), col);
  const poly = (arr, col) => fill(S.poly(arr, true), col);
  /** a smooth line through points (Catmull-Rom); round = back round to the first */
  function curve(P, round = false) {
    const n = P.length, out = [];
    const at = (i) => (round ? P[(i + n) % n] : P[Math.max(0, Math.min(n - 1, i))]);
    for (let i = 0; i < (round ? n : n - 1); i++) {
      const a = at(i - 1), b = at(i), c = at(i + 1), d = at(i + 2);
      const m = Math.max(2, Math.ceil(Math.hypot(c[0] - b[0], c[1] - b[1]) / 5));
      for (let k = 0; k < m; k++) {
        const u = k / m, f = (j) => .5 * (2 * b[j] + (c[j] - a[j]) * u + (2 * a[j] - 5 * b[j] + 4 * c[j] - d[j]) * u * u + (3 * b[j] - a[j] - 3 * c[j] + d[j]) * u * u * u);
        out.push([f(0), f(1)]);
      }
    }
    if (!round) out.push(P[n - 1]);
    return out;
  }
  const blob = (P, col, edge, w) => shape(curve(P, true), col, edge, w);
  const stroke = (P, col, w) => line(hand(curve(P), .8), col, w);
  const fan = (x, y, tips, col, w) => { for (const [tx, ty] of tips) line(S.line(x, y, tx, ty), col, w); };
  const trace = (c, pts) => { c.beginPath(); pts.forEach(([x, y], i) => (i ? c.lineTo(x, y) : c.moveTo(x, y))); c.closePath(); };
  const clipTo = (path, fn) => { const c = SK.ctx(); c.save(); path(c); c.clip(); try { fn(); } finally { c.restore(); } };
  const clipPoly = (pts, fn) => clipTo((c) => trace(c, pts), fn);
  const clipRows = (rows, fn) => clipTo((c) => { c.beginPath(); for (const [y0, y1] of rows) c.rect(-10, y0, 1940, y1 - y0); }, fn);

  /* anything standing in the pool: drawn whole on a layer of its own, then the water laid over the
     part of it under the surface (`under`, a polygon), so the water tints it and nothing around it */
  // the view: world point (fx, fy) sits at screen (cx, cy), magnified s. Set every frame, from t.
  let CAM = { s: 1, fx: 0, fy: 0, cx: 0, cy: 0 };
  const cam = (fn) => SK.at(CAM.cx, CAM.cy, 0, CAM.s, () => SK.at(-CAM.fx, -CAM.fy, 0, 1, fn));
  const onScreen = ([x, y]) => [(x - CAM.fx) * CAM.s + CAM.cx, (y - CAM.fy) * CAM.s + CAM.cy];
  function inWater(under, fn) {
    const off = document.createElement('canvas'); off.width = SK.W; off.height = SK.H;
    const c2 = off.getContext('2d');
    SK.drawInto(c2, () => cam(fn));
    c2.globalCompositeOperation = 'source-atop'; c2.globalAlpha = OVER; c2.fillStyle = C.over;
    trace(c2, under.map(onScreen)); c2.fill();
    const c = SK.ctx(); c.save(); c.setTransform(1, 0, 0, 1, 0, 0); c.drawImage(off, 0, 0); c.restore();
  }
  const below = (y) => [[-2000, y], [4000, y], [4000, 3000], [-2000, 3000]];
  // a group turned (and stretched by s) about a point of the still: an arm about its shoulder
  const swing = (px, py, a, fn, s = 1) => SK.at(px, py, a, s, () => SK.at(-px, -py, 0, 1, fn));
  // a figure of the still slid by (x, y), leant by rot and squashed by (sx, sy) about (px, py)
  const moved = (px, py, m, fn) => SK.at(px + (m.x || 0), py + (m.y || 0), m.rot || 0, [m.sx || 1, m.sy || 1], () => SK.at(-px, -py, 0, 1, fn));
  const blend = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k)];
  const at = (t, times, d = .13) => times.some((b) => t >= b && t < b + d);

  /* ---- time: waves, jumps, splashes */
  // an arm's angle: up in a third of a second, wagging, down again
  const wave = (t, t0, t1, top = 1.15, wag = .3) => tw(t, t0, t0 + .32, E.out) * (1 - tw(t, t1 - .32, t1, E.inOut)) * (top + wag * Math.sin((t - t0) * TAU * 2.4));
  /* an arm throwing water at time L: it dips into the water, whips up, comes back. The value is how
     far the arm is raised (negative: dipped), for `swing` */
  function fling(t, L) {
    const d = t - L;
    if (d < -.36 || d > .52) return 0;
    if (d < -.06) return -.42 * E.inOut(inv(-.36, -.06, d));
    if (d < .08) return lerp(-.42, 1.05, E.out(inv(-.06, .08, d)));
    return 1.05 * (1 - E.inOut(inv(.08, .52, d)));
  }
  const flings = (t, times) => times.reduce((a, L) => a + fling(t, L), 0);
  /* the water thrown at L from `from` at `to`: drops on their own arcs (each lands near `to`, a
     little early or late), a lick of foam where the hand left the water, a burst where they land */
  function spray(t, L, from, to, seed, n = 15) {
    const d = t - L; if (d < -.02 || d > .9) return;
    const r = SK.mulberry(seed), g = 1100;
    const drop = (x, y, sz) => { fill(S.ellC(x, y, sz, sz * 1.15), C.foam); line(S.arc(x, y, sz, .4, 2.6, sz * 1.15), C.foamEdge, 1.3); };
    const up = Math.sin(Math.PI * clamp((d + .02) / .3));
    if (up > .05) for (const i of [-2, 2, -1, 1, 0]) { const q = S.ellC(from[0] + i * 10, from[1] - 15 * up, 8, (24 - 5 * Math.abs(i)) * up, i * .22); fill(q, C.foam); line([...q, q[0]], C.foamEdge, 1.3); }
    for (let i = 0; i < n; i++) {
      const F = .38 + .14 * r(), tx = to[0] + (r() - .5) * 56, ty = to[1] + (r() - .5) * 48, sz = 4.5 + 5.5 * r(), lag = .07 * r();
      const e = d - lag;
      if (e <= 0) continue;
      if (e < F) drop(from[0] + (tx - from[0]) * e / F, from[1] + ((ty - from[1]) / F - g * F / 2) * e + g * e * e / 2, sz);
      else if (e < F + .2) { // it lands: two smaller drops fly off
        const k = (e - F) / .2;
        for (const sgn of [-1, 1]) drop(tx + sgn * (7 + 30 * k), ty - 24 * k + 60 * k * k, sz * .6 * (1 - k * .5));
      }
    }
  }
  /* a jump off the deck into the pool. j: t0 (take-off), air (seconds in it), dx dy (to the spot in
     the water, from where the figure stands), h (how hard it jumps), dip (how deep the plunge),
     lean. Returns where the figure is, its squash, and `up`, how far its arms are thrown up */
  function leap(t, j) {
    const u = inv(j.t0, j.t0 + j.air, t), tau = t - j.t0 - j.air, air = u > 0 && u < 1;
    const squat = t < j.t0 ? E.inOut(inv(j.t0 - .42, j.t0 - .1, t)) * (1 - E.in(inv(j.t0 - .1, j.t0, t))) : 0;
    const spring = air ? Math.sin(Math.PI * clamp(u / .35)) : 0;
    const y = tau > 0 ? j.dy + j.dip * Math.exp(-2.4 * tau) * Math.sin(6 * tau) + 3 * Math.sin(2.6 * tau) : 4 * j.h * u * u + (j.dy - 4 * j.h) * u;
    return {
      x: j.dx * u, y, rot: air ? j.lean * Math.sin(Math.PI * u) : 0,
      sx: 1 + .1 * squat - .05 * spring, sy: 1 - .14 * squat + .08 * spring,
      up: tau > 0 ? 1 - E.inOut(clamp(tau / .5)) : E.out(clamp(u / .25)), wet: tau > 0 ? clamp(tau / .4) : 0, gone: clamp(u / .3),
    };
  }
  const J = {
    rebecca: { t0: 3.6, air: .85, dx: -300, dy: 349, h: 210, dip: 46, lean: -.28, px: 1126, py: 665, yw: 945, x: 1120, k: 1, seed: 11 },
    richard: { t0: 4.4, air: .9, dx: -702, dy: 394, h: 235, dip: 40, lean: -.34, px: 1317, py: 667, yw: 1030, x: 1312, k: .9, seed: 23 },
    mummy: { t0: 5.5, air: .95, dx: -435, dy: 535, h: 250, dip: 70, lean: -.2, px: 1512, py: 667, yw: 1035, x: 1520, k: 1.7, seed: 37 },
  };
  const SURFACE = [[-10, 716], [865, 716], [1283, 1080], [-10, 1080]];
  // rings spreading on the surface from where a figure went in
  function rings(t, j) {
    const tau = t - j.t0 - j.air; if (tau <= 0 || tau > 1.6) return;
    clipPoly(SURFACE, () => {
      for (let i = 0; i < 3; i++) {
        const a = tau - i * .17; if (a <= 0) continue;
        const r = j.k * (40 + 240 * a), e = S.ellC(j.x + j.dx, j.yw, r, r * .2);
        SK.alpha(clamp(1 - a / 1.15) * .9, () => line([...e, e[0]], C.ring, 3.6));
      }
    });
  }
  // the water thrown up: a crown that rises and falls back, and drops on their own arcs
  function crown(t, j) {
    const tau = t - j.t0 - j.air; if (tau <= 0 || tau > 1.3) return;
    const x = j.x + j.dx, y = j.yw, k = j.k, up = Math.sin(Math.PI * clamp(tau / .6)), r = SK.mulberry(j.seed);
    for (let i = 0; i < Math.round(9 + 6 * k); i++) {
      const a = -Math.PI * (.13 + .74 * r()), v = Math.sqrt(k) * (420 + 400 * r()), sz = (4.5 + 5.5 * r()) * Math.sqrt(k);
      const dx = Math.cos(a) * v * tau, dy = Math.sin(a) * v * tau + 820 * tau * tau;
      if (dy > 4) continue; // back in the water
      fill(S.ellC(x + dx, y + dy, sz, sz * 1.15), C.foam); line(S.arc(x + dx, y + dy, sz, .4, 2.6, sz * 1.15), C.foamEdge, 2.2);
    }
    if (up < .06) return;
    for (const i of [-2, 2, -1, 1, 0]) {
      const hgt = (30 + 13 * (2 - Math.abs(i))) * k * up, q = S.ellC(x + i * 25 * k, y - hgt * .8, 16 * k, hgt, i * .2);
      fill(q, C.foam); line([...q, q[0]], C.foamEdge, 2.6);
    }
  }

  /* ---- the setting */
  function backdrop() {
    clipTo((c) => { c.beginPath(); c.rect(-10, 176, 1940, 116); }, () => {
      for (let x = 52 - 65.6 * 2; x < 2020; x += 65.6) { // period, slope and phase fitted to the frame
        line(hand(S.line(x, 181, x + 83, 290), .9), C.fence, 6.4);
        line(hand(S.line(x, 181, x - 83, 290), .9), C.fence, 6.4);
      }
    });
    line(hand(S.line(-10, 181, 1930, 181), .8), C.fence, 9);
    poly([[-10, 290], [1930, 290], [1930, 1090], [-10, 1090]], C.lawn);
  }
  const TUFTS = [[882, 315], [601, 330], [1304, 332], [445, 349], [560, 350], [1100, 350], [825, 358], [694, 361], [1844, 371], [1028, 373], [1260, 407], [1368, 437], [1658, 482], [1195, 491], [1277, 494], [1859, 497], [1361, 499], [1674, 552], [1410, 607], [1753, 614], [1692, 690], [1870, 689], [1908, 738], [1731, 763], [1598, 778], [1775, 807], [1907, 870], [1746, 888], [1904, 955]];
  const YELLOW = [[358, 308], [1070, 312], [59, 315], [589, 316], [1352, 366], [1832, 442], [1204, 451], [1374, 588], [1617, 771], [1877, 771], [1782, 774], [1733, 846], [1713, 858]];
  const WHITE = [[1646, 302], [919, 317], [110, 325], [1301, 401], [1737, 484], [1585, 699], [1793, 842], [1817, 961], [1494, 657]];
  function lawnBits() {
    for (const [x, y] of TUFTS) {
      line(S.line(x - 8, y + 8, x - 12, y - 6), C.tuft, 4.2);
      line(S.line(x, y + 8, x - 1, y - 8), C.tuft, 4.2);
      line(S.line(x + 8, y + 8, x + 11, y - 7), C.tuft, 4.2);
    }
    for (const [x, y] of YELLOW) {
      line(S.line(x, y + 5, x, y + 15), C.tuft, 3.6);
      line(S.line(x - 4, y - 4, x + 4, y + 4), C.petal, 4.6); line(S.line(x - 4, y + 4, x + 4, y - 4), C.petal, 4.6);
    }
    for (const [x, y] of WHITE) {
      line(S.line(x + 1, y + 6, x + 1, y + 20), C.tuft, 3.6);
      line(S.line(x - 5, y - 4, x + 5, y + 4), '#ffffff', 3.8); line(S.line(x - 4, y + 5, x + 5, y - 4), '#ffffff', 3.8);
      dot(x, y, 2.6, C.petal);
    }
  }
  // a leaf drawn on the foliage: a darker outline, and one half of it filled a shade deeper
  function leaf(P) {
    const q = closed(curve(P, true), .8);
    clipTo((c) => { c.beginPath(); c.rect(0, -20, (P[0][0] + P[3][0]) / 2, 200); }, () => fill(q, C.leafMid));
    line(q, C.leafDk, 3.2);
  }
  function tree() {
    ell(1172, 343, 47, 5.5, C.lawnDk);
    blob([[977, 58], [982, 28], [995, 5], [1015, -10], [1040, -8], [1060, 12], [1083, 43], [1103, 83], [1113, 100], [1100, 115], [1057, 121], [1017, 112], [990, 93]], C.leaf);
    blob([[1183, -8], [1200, 8], [1223, 20], [1273, 23], [1323, 14], [1348, 4], [1364, -8]], C.leaf);
    ell(1930, 10, 36, 31, C.leaf);
    leaf([[1000, 20], [1007, 8], [1022, 10], [1028, 27], [1025, 45], [1012, 42], [1002, 32]]);
    leaf([[1035, 18], [1053, 15], [1070, 25], [1075, 40], [1063, 50], [1047, 43], [1037, 30]]);
    leaf([[1003, 90], [1013, 82], [1030, 78], [1039, 87], [1035, 100], [1020, 105], [1007, 100]]);
    leaf([[1238, -6], [1252, -10], [1270, -4], [1274, 9], [1262, 17], [1247, 14], [1239, 5]]);
    blob([[1296, -8], [1310, -12], [1322, -2], [1323, 14], [1313, 27], [1302, 21], [1297, 6]], C.leafDk);
    leaf([[1330, -10], [1345, -12], [1356, -4], [1354, 10], [1344, 20], [1334, 14], [1330, 2]]);
    line(S.arc(1922, 14, 14, 1.2, 3.6, 12), C.leafDk, 3.2);
    stroke([[1087, 82], [1077, 53], [1057, 33]], C.trunk, 4.6);
    stroke([[1047, 75], [1022, 93]], C.trunk, 4.6);
    fill(curve([[1117, 127], [1100, 108], [1073, 88], [1040, 72], [1001, 63], [995, 57], [1002, 51], [1020, 53], [1050, 62], [1083, 80], [1115, 102]]), C.trunk);
    fill(closed(curve([[1110, -6], [1113, 50], [1117, 127], [1122, 173], [1128, 250], [1132, 300], [1131, 338], [1139, 345], [1150, 347], [1160, 345], [1166, 338], [1167, 300], [1163, 250], [1157, 173], [1150, 100], [1148, 33], [1150, -6]])), C.trunk);
    poly([[1147, 16], [1162, -6], [1184, -6], [1151, 38], [1147, 42]], C.trunk);
    poly([[1100, -6], [1113, -6], [1114, 16]], C.trunk);
  }
  const deckEdge = (y) => 985 + 1.3154 * (y - 390);
  const DECK = [[-10, 383], [985, 390], [1905, 1090], [-10, 1090]];
  // the pool's side wall runs away from us: its rim and its waterline, as heights at x
  const rimY = (x) => 610 + (x - 865) * .892, waterY = (x) => 716 + (x - 865) * .871, floorY = (x) => 880 + (x - 865) / 1.125;
  function pool() {
    poly(DECK, C.deck);
    // tiled walls above the water
    poly([[-10, 605], [865, 610], [865, 716], [-10, 716]], C.tile);
    poly([[865, 610], [1392, 1080], [1283, 1080], [865, 716]], C.tile);
    line(hand(S.line(-10, 660, 865, 663), 1.6), C.grout, 3.8);
    for (let x = 48; x < 865; x += 62) line(hand(S.line(x, 607, x, 716), 1.6), C.grout, 3.8);
    line(hand(S.line(865, 663, 1338, 1080), 1.6), C.grout, 3.8);
    for (let x = 909; x < 1392; x += 44) line(hand(S.line(x, rimY(x), x, Math.min(1080, waterY(x))), 1.6), C.grout, 3.8);
    // the water, the walls seen through it, the floor
    poly([[-10, 716], [865, 716], [1283, 1080], [-10, 1080]], C.water);
    poly([[-10, 880], [865, 880], [1090, 1080], [-10, 1080]], C.floor);
    SK.alpha(.5, () => {
      for (let x = 48; x < 865; x += 62) line(hand(S.line(x, 720, x, 880), 1.6), C.sunk, 3);
      line(hand(S.line(-10, 798, 865, 798), 1.6), C.sunk, 3);
      for (let x = 909; x < 1300; x += 44) line(hand(S.line(x, waterY(x) + 4, x, Math.min(1080, floorY(x))), 1.6), C.sunk, 3);
      line(hand(S.line(865, 798, 1190, 1080), 1.6), C.sunk, 3);
    });
    for (let x = 865 - 62 * 15; x < 865; x += 62) line(S.line(x, 880, x + 225, 1080), C.floorLine, 4);
    for (const y of [935, 1000, 1062]) line(S.line(-10, y, 865 + (y - 880) * 1.125, y), C.floorLine, 4);
    line(S.poly([[-10, 880], [865, 880], [1090, 1080]]), C.deep, 5);
    line(S.line(865, 716, 865, 880), C.deep, 5);
    line(S.line(865, 612, 865, 716), C.rim, 4);
    line(hand(S.poly([[-10, 605], [865, 610], [1392, 1080]]), .8), C.rim, 6);
  }
  function ladder() {
    const back = [...S.line(974, 638, 975, 630), ...S.arc(939.5, 630, 35.5, 0, -Math.PI), ...S.line(904, 630, 899, 767), ...S.line(899, 767, 899, 933)];
    const front = [...S.line(1056, 712, 1057, 696), ...S.arc(1022, 696, 35, 0, -Math.PI), ...S.line(987, 696, 984, 835), ...S.line(984, 835, 984, 1002)];
    inWater([[820, 704], [1040, 883], [1040, 1080], [820, 1080]], () => {
      for (const y of [685, 775, 863]) line(S.line(899, y, 984, y + (y < 700 ? 85 : 78), -3), C.rail, 9.5);
      line(back, C.rail, 10.5); line(front, C.rail, 10.5);
    });
  }
  // a shadow on the ground: olive on the deck, green on the lawn
  function shadow(x, y, rx, ry) {
    clipPoly(DECK, () => ell(x, y, rx, ry, C.deckDk));
    clipPoly([[985, 390], [1930, 390], [1930, 1090], [1905, 1090]], () => ell(x, y, rx, ry, C.lawnDk));
  }

  /* ---- faces */
  // an eye: a ring, the white, the pupil off-centre by where it is looking, lashes as short strokes
  function eye(x, y, o) {
    const [rx, ry] = o.ring, [wx, wy] = o.white;
    fill(S.ellC(x, y, rx, ry), o.col);
    if (o.shut) line(S.arc(x, y - wy * .15, wx * .95, .2, Math.PI - .2, wy * .6), C.ink, 2.6);
    else { fill(S.ellC(x, y, wx, wy), '#ffffff'); dot(x + o.look[0], y + o.look[1], o.pupil, C.ink); }
    for (const [x0, y0, x1, y1] of o.lashes || []) line(S.line(x0, y0, x1, y1), C.ink, o.lash || 2.5);
  }
  /* a pig's head in three-quarter view: the head and the snout's tube are one outline (`head`, from
     the top of the snout's end, back along the top, round the head, to the notch under the snout,
     then `chin`, the bottom of the snout's end); the snout's end is an ellipse laid on top */
  function pigHead(o) {
    const w = o.w;
    for (const [x, y, rx, ry, rot] of o.ears) ell(x, y, rx, ry, C.pig, C.pigEdge, w, rot);
    paint(closed([...curve(o.head), o.chin]), C.pig, C.pigEdge, w);
    const n = o.head.length; // the little tick where the snout meets the cheek
    line(S.line(o.head[n - 1][0], o.head[n - 1][1], o.head[n - 1][0] - 2.2 * w, o.head[n - 1][1] + .6 * w), C.pigEdge, w * .8);
    ell(o.tip[0], o.tip[1], o.tip[2], o.tip[3], C.pig, C.pigEdge, w, o.tip[4]);
    for (const [x, y] of o.nostrils) dot(x, y, o.nostril, C.nostril);
    dot(o.cheek[0], o.cheek[1], o.cheek[2], C.cheek);
    for (const e of o.eyes) eye(e[0], e[1], { ...o.eye, look: e[2], lashes: e[3], shut: o.shut });
    stroke(o.mouth, o.smile, o.mouthW);
  }
  // an arm band: an orange cushion with one fold in it
  function armband(P) {
    const q = closed(curve(P, true), .8), xs = P.map((p) => p[0]), d = (Math.max(...xs) - Math.min(...xs)) * .2;
    clipPoly(q, () => { fill(q, C.bandDk); fill(q.map(([x, y]) => [x + d, y + 1]), C.band); });
    line(q, C.bandDk, 2.6);
  }

  /* ---- the pigs, in the water */
  function mummyPig(p) {
    SEED = 1000;
    for (const [x, y0, fx] of [[146, 916, 176], [242, 937, 273]]) line(hand(S.poly([[x, y0], [x, 973], [fx, 975]]), .8), C.limb, 6);
    stroke([[78, 892], [64, 899], [53, 896], [50, 887], [43, 881], [35, 886], [37, 896], [30, 903], [24, 905]], C.limb, 4.6);
    line(S.poly([[298, 783], [323, 804], [348, 822]]), C.limb, 5.6);
    fan(348, 822, [[366, 812], [372, 826], [358, 836]], C.limb, 5);
    const B = closed(curve([[112, 750], [94, 777], [81, 800], [75, 826], [73, 849], [79, 883], [94, 909], [123, 931], [177, 944], [229, 939], [271, 920], [300, 891], [313, 860], [314, 834], [309, 809], [297, 783], [272, 745]]));
    fill(B, C.pig);
    clipPoly(B, () => {
      poly([[60, 788.5], [330, 788.5], [330, 829], [60, 829]], C.suit);
      poly([[60, 881], [330, 881], [330, 960], [60, 960]], C.suit);
      for (const y of [788.5, 829.5, 881]) line(hand(S.line(60, y, 330, y, -1.5), .8), C.suitDk, 3.2);
    });
    line(B, C.pigEdge, 5);
    clipRows([[788.5, 829.5], [881, 960]], () => line(B, C.suitDk, 5));
    dot(199, 869, 3.2, C.pigEdge);
    pigHead({
      w: 5, shut: p.shut,
      ears: [[125, 594, 13, 21, -.55], [177, 577, 14.5, 20.5, .05]],
      head: [[289, 568], [250, 574], [192, 582], [150, 596], [130, 609], [120, 617], [102, 645], [95, 675], [94, 700], [102, 730], [120, 754], [145, 770], [175, 777], [210, 776], [245, 765], [267, 747], [280, 725], [286, 700], [284, 680], [274, 658], [267, 648]],
      chin: [305, 624], tip: [298, 596.5, 22, 28.5, -.3],
      nostrils: [[289, 597], [306, 594.5]], nostril: 5.4, cheek: [164, 698, 19],
      eye: { ring: [15, 16], white: [11.3, 11.8], pupil: 4.8, col: C.lilac, lash: 2.8 },
      eyes: [
        [175.5, 635.5, blend([5.5, 1], [6, 3.5], p.look), [[157, 620.5, 162.5, 626], [170, 614, 172, 622.5], [182, 614.5, 180, 623], [174, 649, 175, 654], [183, 648, 185, 652.5], [189, 644, 193, 647]]],
        [221, 611, blend([6, 1], [6.5, 3.5], p.look), [[204.5, 593, 210.5, 600], [216, 588, 217.5, 596], [229, 588, 226, 597], [219, 625, 220, 629.5], [229, 624, 231, 628], [235, 618, 239, 621]]],
      ],
      mouth: [[204.5, 708], [214, 716], [229, 719.5], [245, 713], [254, 702], [256, 695.5]], smile: C.smile, mouthW: 5.6,
    });
  }
  function peppa(p) {
    SEED = 2000;
    for (const [x, y0, fx] of [[420, 838, 436], [462, 842, 478]]) line(S.poly([[x, y0], [x, 866], [fx, 867]]), C.limb, 4.5);
    poly([[404, 748], [500, 748], [503, 762], [478, 771], [450, 774], [425, 770], [400, 759]], C.pig);
    const D = closed([...curve([[400, 757], [425, 768], [450, 772.5], [478, 769], [502.5, 760]]), ...curve([[502.5, 760], [511, 785], [512.5, 808], [508, 820], [495, 832], [475, 841], [450, 845], [425, 841], [400, 830], [392, 822], [386, 805], [392, 780]])]);
    paint(D, C.red, C.redDk, 4);
    for (let x = 403; x < 505; x += 23.5) line(S.arc(x, 810, 11, .2, Math.PI - .2, 5.5), C.redDk, 2.8);
    swing(508, 775, -(p.armR || 0), () => { fan(543, 786, [[557.5, 784], [556, 790], [551, 793]], C.limb, 4.4); armband([[505.5, 770], [512.5, 757], [526, 754.5], [542.5, 760], [549.5, 772.5], [547.5, 790], [537.5, 804], [515, 805], [507.5, 792.5]]); });
    swing(406, 776, p.arm || 0, () => { fan(364, 786, [[349, 784], [351, 790], [356, 793]], C.limb, 4.4); armband([[359, 770], [367.5, 757], [386, 754], [401, 757.5], [408, 772.5], [407.5, 792.5], [402.5, 802.5], [375, 805], [364, 795], [358, 782.5]]); });
    pigHead({
      w: 4, shut: p.shut,
      ears: [[406, 652.5, 12, 17, -.45], [437.5, 634, 12, 16, -.15]],
      head: [[502, 631.5], [475, 637.5], [450, 644], [422.5, 655], [406, 669], [396, 685], [392, 707.5], [395, 730], [406, 750], [425, 762.5], [450, 766], [475, 762.5], [496, 751], [504, 737.5], [506, 720], [500, 702], [494, 695]],
      chin: [526, 672], tip: [515.5, 651, 19, 23, -.6],
      nostrils: [[509, 654], [520.5, 651]], nostril: 3.5, cheek: [420.5, 710.5, 15.5],
      eye: { ring: [11, 11], white: [8.6, 8.6], pupil: 4, col: C.pigEdge },
      eyes: [[444.5, 669, blend([4.5, 1], [4.5, 3], p.look)], [471, 656, blend([4, 1], [4.5, 3], p.look)]],
      mouth: [[446, 724], [453, 731], [465, 734.5], [478, 730], [487, 721], [489.5, 712.5]], smile: C.smileKid, mouthW: 4.6,
    });
  }
  function george(p) {
    SEED = 3000;
    for (const [x, y0, fx] of [[640, 828, 652], [668, 832, 680]]) line(S.poly([[x, y0], [x, 849], [fx, 850]]), C.limb, 4);
    const B = closed(curve([[622, 775], [614, 795], [611, 810], [615, 822], [630, 831], [657, 835], [685, 831], [698, 822], [702, 808], [704, 790], [702, 775]]));
    fill(B, C.pig);
    clipPoly(B, () => { poly([[600, 807], [710, 807], [710, 840], [600, 840]], C.trunks); line(S.line(600, 807, 710, 807), C.trunksDk, 3); });
    line(B, C.pigEdge, 4);
    clipRows([[807, 840]], () => line(B, C.trunksDk, 4));
    dot(661, 803, 2.5, C.pigEdge);
    swing(707, 788, -(p.armR || 0), () => { fan(736, 795, [[750, 792], [749, 798], [744, 801]], C.limb, 4.2); armband([[704, 780], [710, 770], [725, 767.5], [740, 772.5], [746, 787.5], [744, 805], [735, 816], [712.5, 816], [705.5, 802.5]]); });
    swing(619, 789, p.arm || 0, () => { fan(584, 795, [[570, 792], [572, 798], [577, 801]], C.limb, 4.2); armband([[574, 780], [581, 770], [600, 767.5], [615, 772.5], [621, 787.5], [620, 805], [612.5, 816], [587.5, 817.5], [579, 805], [574, 792.5]]); });
    pigHead({
      w: 4, shut: p.shut,
      ears: [[632.5, 701, 9, 13, -.5], [657, 694, 8.5, 12, -.05]],
      head: [[714, 692.5], [690, 695], [662.5, 699], [640, 704], [625, 715], [615, 730], [612.5, 750], [619, 770], [635, 787.5], [660, 794], [685, 790], [699, 780], [704, 767], [703, 757], [700, 751]],
      chin: [731, 739], tip: [723, 716, 18, 25, -.35],
      nostrils: [[718, 717], [729.5, 714.5]], nostril: 3.5, cheek: [639, 756, 14],
      eye: { ring: [11, 11], white: [8.6, 8.6], pupil: 4, col: C.pigEdge },
      eyes: [[657, 723, blend([1.5, 0], [4, 2.5], p.look)], [680, 712, blend([2.5, .5], [4.5, 2.5], p.look)]],
      mouth: [[669, 764], [674, 769], [681, 771], [688, 768], [694, 760]], smile: C.smileSoft, mouthW: 4.2,
    });
  }
  // the pigs ride the water: a slow bob each, bigger for a while after every splash
  function swimmers(t) {
    let wash = 0;
    for (const j of Object.values(J)) { const tau = t - j.t0 - j.air; if (tau > 0) wash += 7 * j.k * Math.exp(-1.5 * tau); }
    const bob = (i) => ({ y: (2.5 + wash) * Math.sin(TAU * .5 * t + i * 1.9) });
    const look = tw(t, 4.2, 4.8);
    ell(201, 977, 111, 13, C.shade);
    const m = bob(0);
    inWater([...curve([[0, 799], [81, 803], [140, 808], [200, 811], [260, 809], [309, 807], [400, 803]]), [400, 1080], [0, 1080]], () => moved(190, 800, m, () => mummyPig({ look, shut: at(t, [2.2, 6.95]) })));
    // her near arm lies on the water, out of it; it is the one she waves
    const a = wave(t, 1.5, 3.4, 1.25);
    moved(190, 800, m, () => swing(86, 791, a, () => { line(S.line(86, 791, 50, 821), C.limb, 5.6); fan(50, 821, [[27, 813], [28, 828], [43, 838.5]], C.limb, 5); }, 1 + .12 * a));
    inWater(below(796), () => moved(450, 796, bob(1), () => peppa({ look, arm: wave(t, 1.65, 3.45, 1) + wave(t, 6.75, 8.3, 1), armR: fling(t, 9.3), shut: at(t, [2.85, 7.5]) })));
    inWater(below(806), () => moved(660, 806, bob(2), () => george({ look, arm: wave(t, 1.8, 3.5, 1) + wave(t, 6.9, 8.4, 1), shut: at(t, [3.9, 8.7]) })));
  }

  /* ---- the rabbits, on the deck: heads in profile, facing the pool */
  // an ear: round at the top, widest a third of the way down, a little narrower where it meets the
  // head, and left open there (the head is drawn over its foot)
  function rabbitEar(x, y, rx, ry, rot, w) {
    const len = 2 * ry + 8, cap = 1.35 * rx, side = [], top = [];
    const wide = (d) => rx * (1 - .16 * Math.max(0, d / len - .35) / .65); // half its width, d from the tip
    for (let d = len; d > cap; d -= 6) side.push([wide(d), -ry + d]);
    for (let a = 0; a <= 16; a++) top.push([-Math.cos(a / 16 * Math.PI) * wide(cap), -ry + cap - Math.sin(a / 16 * Math.PI) * cap]);
    const pts = [...side.map(([k, v]) => [-k, v]), ...top, ...side.reverse()];
    SK.at(x, y, rot, 1, () => { const q = hand(pts, .9); fill(q, C.rabbit); line(q, C.rabbitEdge, w); });
  }
  function rabbitHead(o) {
    const w = o.w;
    for (const e of o.ears) rabbitEar(...e, w);
    blob(o.head, C.rabbit, C.rabbitEdge, w);
    for (const [x, y, rx, ry, rot] of o.ears) { // the ears' sides run a few pixels on into the head
      const b = [x - Math.sin(rot) * ry, y + Math.cos(rot) * ry];
      for (const k of [-1, 1]) line(S.line(b[0] + k * rx * .95, b[1] - 9, b[0] + k * rx * .95, b[1] + 4), C.rabbitEdge, w * .8);
    }
    dot(o.nose[0], o.nose[1], o.nose[2], o.noseCol || C.nose);
    dot(o.cheek[0], o.cheek[1], o.cheek[2], C.blush);
    for (const e of o.eyes || []) eye(e[0], e[1], { ...o.eye, look: e[2], lashes: e[3], shut: o.blink });
    for (const P of o.shut || []) stroke(P, C.lid, 3);
    stroke(o.mouth, o.smile, o.mouthW);
  }
  const legs = (L, w) => { for (const [x, y0, y1, fx] of L) line(S.poly([[x, y0], [x, y1], [fx, y1 + .5]]), C.paw, w); };
  function rebecca(p) {
    SEED = 4000;
    ell(1197.5, 606, 10.5, 10.5, C.rabbit, C.rabbitEdge, 4);
    poly([[1072, 556], [1100, 548], [1150, 540], [1160, 531], [1172.5, 555], [1150, 569], [1120, 574], [1085, 570], [1069, 562]], C.rabbit);
    line(S.line(1160, 531, 1172.5, 555), C.rabbitEdge, 4.5);
    const D = closed([...curve([[1069, 562], [1085, 569], [1120, 573], [1150, 568], [1172.5, 556]]), ...curve([[1172.5, 556], [1180, 580], [1186, 603], [1185, 611], [1170, 628], [1150, 637], [1120, 640], [1090, 636], [1072, 624], [1064, 612], [1064, 590]])]);
    paint(D, C.yellow, C.yellowDk, 4.5);
    clipPoly(D, () => { // the frill: a seam, and a row of pale scallops under it
      for (const [x0, x1] of [[1066, 1084], [1084, 1106], [1106, 1130], [1130, 1154], [1154, 1184]]) {
        const a = S.arc((x0 + x1) / 2, 604.5, (x1 - x0) / 2, 0, Math.PI, 8);
        fill(a, C.rabbit); line(a, C.yellowDk, 3.4);
      }
      line(S.line(1060, 603.5, 1190, 603), C.yellowDk, 3.4);
    });
    line(D, C.yellowDk, 4.5);
    legs([[1099, 639, 665, 1077.5], [1156, 622.5, 664, 1135]], 5.5);
    swing(1066, 566, p.armL, () => { line(S.line(1037.5, 590, 1027.5, 591), C.paw, 5); fan(1027.5, 591, [[1019, 588], [1024, 599], [1029, 584]], C.paw, 4.4); armband([[1025, 571], [1051, 553], [1069, 560], [1066, 590], [1061, 602.5], [1047.5, 604.5], [1036, 594]]); });
    swing(1172, 564, -p.armR, () => { line(S.line(1206, 590, 1213, 588), C.paw, 5); fan(1213, 588, [[1222.5, 582.5], [1220, 592.5], [1211, 597.5]], C.paw, 4.4); armband([[1165, 580], [1172.5, 557.5], [1185, 550.5], [1207.5, 555], [1217, 567.5], [1215, 580], [1207.5, 592.5], [1192.5, 600], [1175, 597.5]]); });
    rabbitHead({
      w: 4.5, blink: p.blink,
      ears: [[1088.5, 410, 12, 48, -.17], [1129, 408, 11.5, 49, -.075]],
      head: [[1019.5, 510], [1032.5, 490], [1057.5, 470], [1082.5, 457.5], [1105, 452.5], [1130, 454], [1147.5, 462.5], [1160, 480], [1164, 500], [1160, 522.5], [1147.5, 542.5], [1125, 557.5], [1100, 562.5], [1072.5, 557.5], [1047.5, 545], [1027.5, 527.5]],
      nose: [1037.5, 509, 11], cheek: [1136, 512.5, 15],
      eye: { ring: [12, 12], white: [9.2, 9.2], pupil: 4.4, col: C.rabbitEdge },
      eyes: [[1092.5, 476, blend([-2.5, 1], [-3.5, -1], p.look)], [1121, 479, blend([-2.5, 1.5], [-3.5, -1], p.look)]],
      mouth: [[1073, 528], [1080, 537], [1094, 543], [1108, 538], [1115, 531], [1117.5, 525.5]], smile: '#c8548d', mouthW: 4.6,
    });
  }
  function richard(p) {
    SEED = 5000;
    legs([[1299, 652.5, 666, 1281], [1336, 644, 665, 1320]], 5);
    const B = closed(curve([[1272, 606], [1268, 620], [1268, 635], [1275, 646], [1290, 653], [1312.5, 656], [1335, 653], [1350, 646], [1358, 634], [1356, 615], [1350, 600]]));
    fill(B, C.rabbit);
    clipPoly(B, () => { poly([[1250, 634.5], [1370, 633.5], [1370, 670], [1250, 670]], C.indigo); line(S.line(1250, 634.5, 1370, 633.5), C.indigoDk, 3); });
    line(B, C.rabbitEdge, 4.2);
    clipRows([[634, 670]], () => line(B, C.indigoDk, 4.2));
    dot(1312, 628, 2.6, C.button);
    swing(1268, 613, p.armL, () => { line(S.line(1238, 632, 1231, 632), C.paw, 4.6); fan(1231, 632, [[1224, 629], [1226, 635.5], [1231, 640]], C.paw, 4); armband([[1226, 612.5], [1234, 600], [1247.5, 595], [1265, 602.5], [1271, 635], [1250, 645], [1236, 637.5], [1229, 622.5]]); });
    swing(1353, 611, -p.armR, () => { line(S.line(1390, 622, 1396, 623), C.paw, 4.6); fan(1396, 623, [[1402.5, 627.5], [1401, 619], [1396, 632]], C.paw, 4); armband([[1350, 615], [1355, 600], [1370, 591], [1390, 595], [1399.5, 607.5], [1397.5, 622.5], [1390, 635], [1375, 642.5], [1357.5, 637.5]]); });
    rabbitHead({
      w: 4.2,
      ears: [[1301, 479, 11, 48, 0], [1339, 487.5, 10.5, 49, .14]],
      head: [[1231, 550], [1240, 535], [1260, 526], [1287.5, 524], [1315, 526], [1337.5, 537.5], [1351, 555], [1355, 575], [1349, 592.5], [1332.5, 605], [1305, 611], [1277.5, 607.5], [1252.5, 592.5], [1236, 572.5]],
      nose: [1250, 552.5, 11], noseCol: C.noseSoft, cheek: [1330, 572.5, 14.5],
      shut: [[[1274, 540], [1281, 544], [1290, 545], [1296, 542]], [[1300, 546], [1310, 550], [1322.5, 551]]],
      mouth: [[1276, 588], [1281, 594], [1289, 597.5], [1297, 594], [1303, 588]], smile: '#b56d8b', mouthW: 4,
    });
  }
  function mummyRabbit(p) {
    SEED = 6000;
    ell(1654, 577.5, 16, 16, C.rabbit, C.rabbitEdge, 4.5);
    const B = closed(curve([[1435, 454], [1417.5, 475], [1405, 505], [1401, 535], [1407.5, 570], [1427.5, 600], [1462.5, 622.5], [1500, 632.5], [1530, 634], [1570, 627.5], [1605, 610], [1627.5, 587.5], [1640, 560], [1642.5, 535], [1637.5, 505], [1625, 480], [1605, 452.5], [1587.5, 435]]));
    fill(B, C.rabbit);
    clipPoly(B, () => {
      fill([...S.line(1390, 479, 1655, 479, 2), [1655, 519], ...S.line(1655, 519, 1390, 518, -1.5), [1390, 479]], C.stripe);
      fill([...S.line(1390, 571, 1655, 572, 2.5), [1655, 650], [1390, 650]], C.stripe);
      line(S.line(1390, 479, 1655, 479, 2), C.stripeDk, 3.4); line(S.line(1390, 518, 1655, 519, 1.5), C.stripeDk, 3.4);
      line(S.line(1390, 571, 1655, 572, 2.5), C.stripeDk, 3.4);
    });
    line(B, C.rabbitEdge, 5);
    clipRows([[479, 519], [572, 650]], () => line(B, C.stripeDk, 5));
    dot(1516, 559.5, 3.3, C.button);
    legs([[1472.5, 625, 666, 1442.5], [1569, 606, 666, 1540]], 6.5);
    swing(1403, 528, p.armL, () => fan(1400, 528, [[1374, 531], [1381, 543], [1398, 547]], C.paw, 5.2));
    swing(1620, 482, -p.armR, () => { line(S.line(1619, 480, 1647.5, 526), C.paw, 5.6); fan(1647.5, 526, [[1672.5, 525], [1666, 539], [1648, 546]], C.paw, 5.2); }, 1 + .14 * Math.min(1, p.armR));
    rabbitHead({
      w: 5, blink: p.blink,
      ears: [[1482, 206, 14, 82, -.15], [1544, 208, 15.5, 87, -.055]],
      head: [[1360, 367], [1368.5, 348.5], [1397, 323], [1431.5, 301.5], [1466, 288.5], [1506, 283], [1540, 284], [1568.5, 294], [1588.5, 314], [1601.5, 343], [1605, 371.5], [1601.5, 400], [1588.5, 428.5], [1563, 451.5], [1526, 463], [1488.5, 464], [1448.5, 454], [1411.5, 434], [1380, 406], [1364, 386]],
      nose: [1386, 368.5, 15.7], cheek: [1546, 381.5, 17.7],
      eye: { ring: [13.5, 15], white: [10.6, 12], pupil: 4.9, col: C.rabbitEdge, lash: 3 },
      eyes: [
        [1476, 326, blend([-5, 2], [-5.5, -.5], p.look), [[1459.5, 307, 1466, 314], [1471, 302, 1473, 311], [1484, 303, 1481.5, 311.5], [1463, 340.5, 1465, 337], [1473.5, 345, 1473.5, 341], [1484, 341.5, 1481.5, 338]]],
        [1527, 331.5, blend([-4, 2], [-5, -.5], p.look), [[1512, 313.5, 1519, 321.5], [1524, 308.5, 1526, 317], [1538.5, 310.5, 1536, 319], [1515, 348, 1518, 344], [1524, 351, 1524.5, 346], [1535, 348, 1533, 343.5]]],
      ],
      mouth: [[1463.5, 418], [1472, 427.5], [1488.5, 433], [1505, 428], [1515, 420], [1518.5, 414]], smile: '#c7398a', mouthW: 5.6,
    });
  }

  // the three on the deck: each waves, then leaps; its shadow stays behind and fades as it leaves the ground
  function rabbits(t) {
    const cheer = (t0) => wave(t, t0, t0 + 1.7, .9, .25);
    const R = leap(t, J.rebecca), r = leap(t, J.richard), M = leap(t, J.mummy);
    SK.alpha(1 - R.gone, () => shadow(1126, 665, 71, 9.5));
    SK.alpha(1 - r.gone, () => shadow(1317.5, 667.5, 49, 7.5));
    SK.alpha(1 - M.gone, () => shadow(1512.5, 667.5, 110, 12.5));
    for (const j of Object.values(J)) rings(t, j);
    inWater(below(J.rebecca.yw), () => moved(J.rebecca.px, J.rebecca.py, R, () => rebecca({
      armR: wave(t, .65, 2.95) + R.up + cheer(7.7), armL: R.up + cheer(7.7) + fling(t, WIPE.t0), look: R.wet, blink: at(t, [1.9, 8.1]),
    })));
    inWater(below(J.richard.yw), () => moved(J.richard.px, J.richard.py, r, () => richard({
      armL: wave(t, .8, 3, .95) + r.up * .9 + cheer(7.85), armR: r.up + cheer(7.85),
    })));
    inWater(below(J.mummy.yw), () => moved(J.mummy.px, J.mummy.py, M, () => mummyRabbit({
      armR: wave(t, .5, 2.9, 1.9, .28) + M.up * 1.9, armL: M.up * .9, look: M.wet, blink: at(t, [3.1, 7.3]),
    })));
    for (const j of Object.values(J)) crown(t, j);
  }

  /* ---- the two shots, and the water between them */
  const CUT = 9.8, END = 13;
  // the splash over the lens: thrown at t0 from `at` (screen), it covers the frame by t1; the picture
  // under it changes at CUT; from t2 the water runs down off the glass, clear by t3
  const WIPE = { t0: 9.42, t1: 9.76, t2: 9.82, t3: 10.24, at: [735, 940], water: '#8fdde8', lit: '#bdeef4' };
  function wide(t) {
    const k = E.in(inv(9.0, CUT, t)); // the camera leans in on the children before the splash
    CAM = { s: 1 + .22 * k, fx: 700, fy: 900, cx: 700, cy: 900 };
    cam(() => { backdrop(); lawnBits(); tree(); pool(); swimmers(t); ladder(); rabbits(t); });
  }
  /* close on the four children. Each is the wide shot's figure, moved to a place of its own in the
     same pool (x, y from where it was drawn; wl its water line), and each throws at the one across
     from it: T the times, from/to in the pool's own units */
  const KIDS = {
    peppa: { px: 450, py: 796, x: -320, y: 94, wl: 890, T: [10.08, 10.98, 11.88, 12.78], from: [242, 866], to: [668, 822], seed: 51 },
    rebecca: { px: 1126, py: 665, x: -390, y: 304, wl: 900, T: [10.62, 11.52, 12.42], from: [626, 880], to: [186, 786], seed: 62 },
    george: { px: 660, py: 806, x: -370, y: 149, wl: 955, T: [10.32, 11.22, 12.12], from: [386, 930], to: [506, 902], seed: 73 },
    richard: { px: 1317, py: 667, x: -752, y: 344, wl: 980, T: [10.78, 11.68, 12.58], from: [468, 962], to: [336, 886], seed: 84 },
  };
  function close(t) {
    CAM = { s: 2.2 + .09 * tw(t, CUT, END, E.sine), fx: 428, fy: 834, cx: SK.W / 2, cy: SK.H / 2 };
    const K = KIDS, hit = (who) => at(t, who.T.map((L) => L + .38), .3); // eyes shut as the water lands
    const bob = (i) => 3 * Math.sin(TAU * .55 * t + i * 1.7);
    const put = (k, i, fn) => inWater(below(k.wl), () => moved(k.px, k.py, { x: k.x, y: k.y + bob(i) }, fn));
    cam(() => {
      SEED = 0; pool();
      put(K.peppa, 0, () => peppa({ look: .35, armR: flings(t, K.peppa.T), shut: hit(K.rebecca) }));
      put(K.rebecca, 1, () => rebecca({ armL: flings(t, K.rebecca.T), armR: .25 + .2 * Math.sin(t * 5), look: .6, blink: hit(K.peppa) }));
      put(K.george, 2, () => george({ look: .35, armR: flings(t, K.george.T), shut: hit(K.richard) }));
      put(K.richard, 3, () => richard({ armL: flings(t, K.richard.T), armR: .2 + .2 * Math.sin(t * 5 + 2) }));
      for (const k of Object.values(K)) k.T.forEach((L, i) => spray(t, L, k.from, k.to, k.seed + i * 7));
    });
  }
  function wipe(t) {
    const W = WIPE, [x, y] = W.at;
    if (t < W.t0 || t > W.t3 + .5) return;
    // bubbles in the water over the glass, so the frames it fills are water and not a flat card
    const bubbles = (inside) => { const b = SK.mulberry(21); for (let i = 0; i < 16; i++) { const bx = 60 + b() * (SK.W - 120), by = 40 + b() * (SK.H - 80) - (t - W.t0) * (90 + 160 * b()), z = 9 + 22 * b(); if (inside(bx, by, z)) { fill(S.ellC(bx, by, z, z), W.lit); fill(S.ellC(bx - z * .3, by - z * .3, z * .28, z * .28), C.foam); } } };
    if (t < W.t2) { // thrown: a ball of water with a foam rim, growing until it is the whole frame
      const R = 1780 * Math.pow(inv(W.t0, W.t1, t), 1.7), r = SK.mulberry(5);
      for (let i = 0; i < 16; i++) { const a = i / 16 * TAU + r() * .2, q = S.ellC(x + Math.cos(a) * R, y + Math.sin(a) * R, R * (.2 + .1 * r()), R * (.2 + .1 * r())); fill(q, C.foam); line([...q, q[0]], C.foamEdge, 4); }
      fill(S.ellC(x, y, R, R), C.foam); fill(S.ellC(x, y, R * .9, R * .9), W.lit); fill(S.ellC(x, y, R * .74, R * .74), W.water);
      for (let i = 0; i < 14; i++) { const a = r() * TAU, d = R * (1.28 + .35 * r()), z = 5 + R * .022 * (1 + r()); fill(S.ellC(x + Math.cos(a) * d, y + Math.sin(a) * d, z, z * 1.15), C.foam); }
      bubbles((bx, by, z) => Math.hypot(bx - x, by - y) + z < R * .72);
      return;
    }
    // running off: a sheet with a wavy foam lip sliding down the glass, and a few slow drops after it
    const k = Math.pow(inv(W.t2, W.t3, t), 1.45), top = -90 + (SK.H + 190) * k, lip = [];
    for (let px = -20; px <= SK.W + 20; px += 24) lip.push([px, top + 34 * Math.sin(px / 150 + 1) + 18 * Math.sin(px / 61 + t * 9)]);
    if (k < 1) {
      fill([...lip, [SK.W + 20, SK.H + 40], [-20, SK.H + 40]], W.water);
      line(lip, C.foam, 26); line(lip.map(([px, py]) => [px, py + 20]), W.lit, 14);
      bubbles((bx, by, z) => by - z > top + 70);
    }
    const r = SK.mulberry(9);
    for (let i = 0; i < 9; i++) {
      const dx = 90 + r() * (SK.W - 180), v = 620 + 520 * r(), z = 7 + 8 * r(), dy = -60 + (t - W.t2) * v * (1 + (t - W.t2) * 1.6);
      if (dy < top - 30 && dy < SK.H + 40) { fill(S.ellC(dx, dy, z, z * 1.5), W.lit); fill(S.ellC(dx - z * .2, dy - z * .3, z * .35, z * .5), C.foam); }
    }
  }

  SK.film({
    duration: END,
    camera: SK.camera([[0, [SK.W / 2, SK.H / 2, 1]]]),
    speedLines: false,
    handheld: false,
    fadeOut: .001, // hold the last frame
    draw(t) {
      SEED = 0;
      if (t < CUT) wide(t); else close(t);
      wipe(t);
    },
    // the sound comes off the same clock as the picture: a boing at each take-off, a swish through
    // the air, and at each landing a splash (a falling hiss over a thump) with drops after it
    sound: {
      score: () => ({
        bpm: 120, drum_gain: .35,
        events: [
          { inst: 'pizzicato_strings', vel: .5, notes: '0 C3 .5; 1 G2 .5; 2 C3 .5; 3 G2 .5; 4 F2 .5; 5 C3 .5; 6 F2 .5; 7 C3 .5; 8 C3 .5; 9 G2 .5; 10 A2 .5; 11 E2 .5; 12 F2 .5; 13 C3 .5; 14 G2 .5; 15 G2 .5; 16 C3 .5; 17 G2 .5; 18 A2 .5; 19 E2 .5; 20 F2 .5; 21 C3 .5; 22 G2 .5; 23 G2 .5; 24 C3 1' },
          { type: 'strum', at: 0, chord: 'C3+G3+C4+E4', vel: .4, pattern: 'bar' },
          { type: 'strum', at: 4, chord: 'F3+A3+C4+F4', vel: .4, pattern: 'bar' },
          { type: 'strum', at: 8, chord: 'C3+G3+C4+E4', vel: .4, pattern: 'half' },
          { type: 'strum', at: 10, chord: 'A2+E3+A3+C4', vel: .4, pattern: 'half' },
          { type: 'strum', at: 12, chord: 'F3+A3+C4+F4', vel: .42, pattern: 'half' },
          { type: 'strum', at: 14, chord: 'G3+B3+D4+G4', vel: .42, pattern: 'half' },
          { type: 'strum', at: 16, chord: 'C3+G3+C4+E4', vel: .45, pattern: 'half' },
          { type: 'strum', at: 18, chord: 'A2+E3+A3+C4', vel: .45, pattern: 'half' },
          { type: 'strum', at: 20, chord: 'F3+A3+C4+F4', vel: .46, pattern: 'half' },
          { type: 'strum', at: 22, chord: 'G3+B3+D4+G4', vel: .46, pattern: 'half' },
          { type: 'strum', at: 24, chord: 'C3+G3+C4+E4+G4', vel: .48, pattern: 'once' },
          { inst: 'glockenspiel', vel: .38, notes: '0 E5 .5; .5 G5 .5; 1 C6 1; 2 E5 .5; 2.5 G5 .5; 3 C6 1; 4 F5 .5; 4.5 A5 .5; 5 C6 1; 6 A5 .5; 6.5 G5 .5; 7 F5 1; 8 E5 .5; 8.5 G5 .5; 9 C6 1; 10 E6 .5; 10.5 D6 .5; 11 C6 1; 12 A5 .5; 12.5 C6 .5; 13 D6 1; 14 B5 .5; 14.5 D6 .5; 15 G6 1; 16 C6 .5; 16.5 E6 .5; 17 G6 1; 18 E6 .5; 18.5 C6 .5; 19 A5 1; 20 F5 .5; 20.5 A5 .5; 21 C6 .5; 21.5 A5 .5; 22 B5 .5; 22.5 D6 .5; 23 G6 1; 24 C7 2' },
          { type: 'drums', from: 0, bars: 6, kit: { shaker: 'o.o.o.o.o.o.o.o.' }, vel: .5 },
        ],
      }),
      sfx: () => {
        const cues = [], r3 = (x) => +x.toFixed(3);
        for (const j of Object.values(J)) {
          const T = j.t0 + j.air, pan = r3(clamp((j.x + j.dx - 960) / 960, -1, 1) * .7), big = j.k > 1.2;
          cues.push({ t: r3(j.t0 - .04), fx: 'boing', db: big ? -19 : -21, pan: r3((j.x - 960) / 960 * .7), args: { f0: big ? 170 : 260, f1: big ? 380 : 560, sec: .36 } });
          cues.push({ t: r3(j.t0 + .12), fx: 'swoosh_soft', db: -27, pan: 0, args: { sec: r3(j.air * .7) } });
          cues.push({ t: r3(T - .02), fx: 'whoosh', db: big ? -11 : -15, pan, send: .3, args: { sec: big ? .9 : .6, f0: 3400, f1: big ? 380 : 600, peak: .1, q: .8 } });
          cues.push({ t: r3(T), fx: 'thunk', db: big ? -13 : -18, pan, args: { sec: big ? .55 : .4 } });
          for (const [dt, f] of [[.27, 1500], [.4, 1900], [.53, 1300], [.68, 1700]]) cues.push({ t: r3(T + dt * (big ? 1.25 : 1)), fx: 'pop', db: -27, pan, args: { f0: f, f1: f * .55, sec: .05 } });
        }
        // the splash over the lens: a hiss that swells as it comes at us, a thump as it lands, drips as it clears
        cues.push({ t: r3(WIPE.t0 - .02), fx: 'whoosh', db: -11, pan: 0, send: .3, args: { sec: r3(WIPE.t1 - WIPE.t0 + .1), f0: 500, f1: 3600, peak: .85, q: .8 } });
        cues.push({ t: r3(WIPE.t1 - .02), fx: 'thunk', db: -14, pan: 0, args: { sec: .5 } });
        cues.push({ t: r3(WIPE.t2), fx: 'whoosh', db: -19, pan: 0, args: { sec: r3(WIPE.t3 - WIPE.t2 + .15), f0: 2600, f1: 500, peak: .2, q: .9 } });
        for (const [dt, f] of [[.12, 1700], [.3, 1400], [.46, 2000]]) cues.push({ t: r3(WIPE.t3 + dt - .2), fx: 'pop', db: -27, pan: 0, args: { f0: f, f1: f * .55, sec: .05 } });
        // each throw in the close shot: a short hiss off the hand, two drops landing across the frame
        for (const k of Object.values(KIDS)) for (const L of k.T) {
          const a = r3((k.from[0] - 428) / 436 * .6), b = r3((k.to[0] - 428) / 436 * .6);
          cues.push({ t: r3(L - .04), fx: 'whoosh', db: -21, pan: a, args: { sec: .3, f0: 2800, f1: 900, peak: .15, q: .9 } });
          cues.push({ t: r3(L + .4), fx: 'pop', db: -25, pan: b, args: { f0: 1600, f1: 800, sec: .05 } });
          cues.push({ t: r3(L + .47), fx: 'pop', db: -28, pan: b, args: { f0: 2100, f1: 1100, sec: .04 } });
        }
        return cues.filter((c) => c.t < END - .05).sort((a, b) => a.t - b.t);
      },
    },
  });
})();
