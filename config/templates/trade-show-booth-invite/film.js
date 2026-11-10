// For: visitors heading to a trade show; a polished, warm, brand-led invitation to the exhibitor's stand
(function () {
  'use strict';
  const { E, clamp, lerp, tw, mix, S } = SK;
  SK.setStyle('clean');

  // ---------------------------------------------------------------- every fact, colour and picture name
  const FACTS = SK.DATA.content;

  const Cl = FACTS.colors, ST = FACTS.stand;
  SK.setGround('white', { text: Cl.ink, textSoft: Cl.soft, accent: Cl.blue, accentText: Cl.navy });
  SK.KIT.font = FACTS.font;
  const W = SK.W, H = SK.H, U = Math.min(W, H) / 1080, WIDE = W / H > 1.3;
  const T = SK.cues({
    rp: [0, 'Radiology'], mosaic: [0, 'Mosaic'], kick: [0, 'exhibiting'], rsna: [0, 'RSNA'],
    find: [1, null], south: [1, 'South'], booth: [1, 'booth'], ai: [1, 'AI'],
    meet: [2, 'Meet'], see: [2, 'see'], join: [2, 'join'],
    hours: [3, 'exhibit'], sunday: [3, 'Sunday'], wed: [3, 'Wednesday'], ten: [3, 'ten'],
    end: [4, null],
  });
  const SEE_T = [T.meet, T.see, T.join, T.join + .7];
  const BIG = ST.booth || FACTS.show.name; // no booth number published: the show's name holds its place

  // ---------------------------------------------------------------- helpers
  const show = (x, y, tin, tout, fn, type = 'rise') => SK.layer({ x, y, in: { t: tin, type, dist: 34 * U }, out: tout ? { t: tout, type: 'fade', d: .4 } : undefined }, fn);
  const lab = (s, x, y, o) => SK.label(s, x, y, { font: FACTS.font, ...o });
  function textFit(str, x, y, o) { // shrink, then wrap
    if (!str) return 0;
    const s = SK.fit(str, o.maxW, { font: FACTS.font, ...o });
    if (s >= o.size * .72 || !/\s/.test(str)) { lab(str, x, y, { ...o, size: s, maxW: undefined }); return s * 1.25; }
    const sz = o.size * .74, lines = SK.KIT.wrap(str, o.maxW, { font: FACTS.font, ...o, size: sz });
    lines.forEach((ln, i) => lab(ln, x, y + (i - (lines.length - 1) / 2) * sz * 1.2, { ...o, size: Math.min(sz, SK.fit(ln, o.maxW, { font: FACTS.font, ...o, size: sz })), maxW: undefined }));
    return lines.length * sz * 1.2;
  }
  function block(str, maxW, size, maxLines, o) { // a headline: one line if it nearly fits, else wrapped as large as the lines allow
    const oo = { font: FACTS.font, ...o };
    if (!str) return { lines: [], size, h: 0 };
    const s1 = SK.fit(str, maxW, { ...oo, size });
    if (s1 >= size * .7 || !/\s/.test(str) || maxLines < 2) return { lines: [str], size: s1, h: s1 };
    for (const f of [.85, .74, .64, .55, .47, .4, .34, .28]) {
      const sz = size * f, L = SK.KIT.wrap(str, maxW, { ...oo, size: sz });
      if (sz <= s1) break;
      if (L.length <= maxLines && L.every((l) => SK.measure(l, { ...oo, size: sz }) <= maxW)) return { lines: L, size: sz, h: sz * (1 + (L.length - 1) * 1.12) };
    }
    return { lines: [str], size: s1, h: s1 };
  }
  const drawBlock = (b, x, y, o) => b.lines.forEach((ln, i) => lab(ln, x, y + (i - (b.lines.length - 1) / 2) * b.size * 1.12, { ...o, size: b.size }));
  function stack(rows, cy) { // rows [key, height, gap after] -> {key: centre y}, the column centred on cy
    const tot = rows.reduce((a, r, i) => a + r[1] + (i < rows.length - 1 ? r[2] : 0), 0), Y = {};
    let y = cy - tot / 2;
    rows.forEach((r) => { Y[r[0]] = y + r[1] / 2; y += r[1] + r[2]; });
    return Y;
  }
  function quad(P, fill, stroke, lw) {
    const c = SK.ctx(); c.beginPath(); P.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.closePath();
    if (fill) { c.fillStyle = fill; c.fill(); }
    if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw; c.lineJoin = 'round'; c.stroke(); }
  }
  function line(P, col, lw, dash) {
    const c = SK.ctx(); c.save(); c.beginPath(); P.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1])));
    c.strokeStyle = col; c.lineWidth = lw; c.lineCap = 'round'; c.lineJoin = 'round'; if (dash) c.setLineDash(dash); c.stroke(); c.restore();
  }
  function disc(x, y, r, fill, stroke, lw) {
    const c = SK.ctx(); c.beginPath(); c.arc(x, y, Math.max(0, r), 0, Math.PI * 2);
    if (fill) { c.fillStyle = fill; c.fill(); }
    if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw; c.stroke(); }
  }
  function brandBar(x0, y0, w, h) { // the gradient strip of their banner
    const c = SK.ctx(), g = c.createLinearGradient(x0, 0, x0 + w, 0);
    g.addColorStop(0, Cl.royal); g.addColorStop(.55, Cl.blue); g.addColorStop(1, Cl.green);
    c.fillStyle = g; c.fillRect(x0, y0, w, h);
  }
  const LOGOS = () => FACTS.logos.filter((l) => SK.IMG[l.img]);
  const imgW = (l, h) => { const im = SK.IMG[l.img]; return im ? h * im.width / im.height : 0; };
  function logoRow(t, cx, cy, maxW, hgt, times, tout) { // 1..n logos in a row, divided; the row re-centres as each arrives
    const L = LOGOS(); if (!L.length) return;
    const gap = .9 * hgt, ws = L.map((l) => imgW(l, l.h / 66 * hgt)), tot = ws.reduce((a, b) => a + b, 0) + gap * (L.length - 1), k = Math.min(1, maxW / tot);
    const tin = (i) => times[Math.min(i, times.length - 1)];
    const now = L.reduce((a, l, i) => a + (i ? tw(t, tin(i) - .3, tin(i) + .3) * (gap + ws[i]) : ws[0]), 0);
    let x = cx - now * k / 2;
    L.forEach((l, i) => {
      const w = ws[i] * k;
      if (i) show(x - gap * k / 2, cy, tin(i), tout, () => quad([[-1, -hgt * .45 * k], [1, -hgt * .45 * k], [1, hgt * .45 * k], [-1, hgt * .45 * k]], Cl.line), 'fade');
      show(x + w / 2, cy, tin(i), tout, () => SK.image(l.img, 0, 0, w));
      x += w + gap * k;
    });
  }

  // ---------------------------------------------------------------- the hall: a generic plan of islands of stands
  const SW = 100, SH = 80, PX = 260, PY = 220, NI = 5, NJ = 3, MI = 2, MJ = -1;
  const rnd = (i, j) => { const s = Math.sin(i * 127.1 + j * 311.7) * 43758.5453; return s - Math.floor(s); };
  const TINTS = [Cl.blue, Cl.green, Cl.royal];
  const stands = [];
  for (let j = -NJ; j <= NJ; j++) for (let i = -NI; i <= NI; i++) {
    const mine = i === MI && j === MJ, k = mine ? 0 : rnd(i, j), x = i * PX - SW, y = j * PY - SH;
    const cells = k < .5 ? [[0, 0, 1, 1], [1, 0, 1, 1], [0, 1, 1, 1], [1, 1, 1, 1]] // four stands
      : k < .72 ? [[0, 0, 2, 1], [0, 1, 2, 1]] // two long ones
        : k < .86 ? [[0, 0, 1, 2], [1, 0, 1, 1], [1, 1, 1, 1]] // a deep one and two
          : [[0, 0, 2, 2]]; // one island stand
    cells.forEach(([a, b, w, h], n) => {
      const q = rnd(i * 7 + a + 3, j * 5 + b + n);
      stands.push({ x: x + a * SW, y: y + b * SH, w: w * SW, h: h * SH, c: (i - MI) * 2 + a, r: (j - MJ) * 2 + b - 1, me: mine && a === 0 && b === 1, tint: !mine && q > .8 ? TINTS[Math.floor(q * 97) % 3] : null });
    });
  }
  stands.sort((p, q) => p.y - q.y || p.x - q.x);
  const ME = stands.find((s) => s.me), MX = ME.x + SW / 2, MY = ME.y + SH / 2;
  const PAV = { x0: (MI - 1) * PX - SW - 40, x1: (MI + 1) * PX + SW + 40, y0: (MJ - 1) * PY - SH - 40, y1: MJ * PY + SH + 40 };
  const HALL = { x0: -NI * PX - SW - 90, x1: NI * PX + SW + 90, y0: -NJ * PY - SH - 90, y1: NJ * PY + SH + 90 };
  const EX = -PX / 2, AY = (MJ + .5) * PY; // the entrance, in the wall nearest us; the aisle that passes the stand
  const ROUTE = [[EX, HALL.y1], [EX, AY], [MX, AY], [MX, ME.y + SH + 6]];

  // the plan's own numbering, counted out from the stand's number (none when it has no number): never a real plan
  const NUM = (() => { const m = /^([A-Za-z]?)(\d{1,5})$/.exec(String(ST.booth || '').trim()); return m ? { pre: m[1], n: +m[2], len: m[2].length } : null; })();
  function letter(c) { const a = NUM.pre.charCodeAt(0), lo = a >= 97 ? 97 : 65, code = a + c; return code < lo || code > lo + 25 ? '' : String.fromCharCode(code); }
  function standNo(c, r) {
    if (!NUM) return '';
    const n = NUM.pre ? NUM.n - r * 2 : NUM.n + c * 100 - r * 2, p = NUM.pre ? letter(c) : '';
    return n < 1 || (NUM.pre && !p) ? '' : p + String(n).padStart(NUM.len, '0');
  }
  function aisleNo(c) {
    if (!NUM) return '';
    if (NUM.pre) return letter(c);
    const n = Math.floor((NUM.n + c * 100) / 100) * 100; return NUM.n < 100 || n < 100 ? '' : String(n);
  }

  // the plan's camera: focus (x, y, height) lands at screen (ox, oy); k tilts the floor (1 = from above)
  const z0 = .93 * (WIDE ? Math.min(W / (HALL.x1 - HALL.x0), H / (HALL.y1 - HALL.y0)) : Math.min(1, H / (HALL.y1 - HALL.y0))), zF = 1.25 * U;
  const zB = .62 * (WIDE ? Math.min(W, H) : Math.min(W, H * .6)) / SW, kB = .52, WALL = 54;
  const standAt = WIDE ? [-.2 * W, .05 * H] : [0, -.16 * H];
  const boothAt = WIDE ? [-.22 * W, .03 * H] : [0, -H / 2 + 165 * U + 48 * zB];
  const zone = WIDE ? { cx: .25 * W, cy: .03 * H, w: .42 * W } : { cx: 0, w: Math.min(.88 * W, 820 * U), top: boothAt[1] + 48 * zB + 60 * U };
  if (!WIDE) zone.cy = (zone.top + H / 2 - 50 * U) / 2;
  const tagAt = WIDE ? [.25 * W, 0] : [0, (standAt[1] + 70 * U + H / 2) / 2];
  const CAM = [
    [0, [WIDE ? 0 : (EX + MX) / 2, 0, 0, Math.log(z0), 1, 0, 0]],
    [T.find - .2, [WIDE ? 40 : (EX + MX) / 2, 150, 0, Math.log(z0 * 1.14), 1, 0, 0]],
    [T.south + .1, [(EX + MX) / 2, AY + 150, 0, Math.log(Math.max(z0 * 1.1, Math.min(zF * .8, z0 * 1.9))), 1, 0, 0]],
    [T.booth + .1, [MX, MY, 0, Math.log(zF), 1, ...standAt]],
    [T.meet - .3, [MX, MY, 0, Math.log(zF * 1.1), 1, ...standAt]],
    [T.meet + .9, [MX, ME.y, 6, Math.log(zB), kB, ...boothAt]],
    [T.end, [MX, ME.y, 6, Math.log(zB * 1.06), kB, ...boothAt]],
    [30, [MX, ME.y, 6, Math.log(zB * 1.1), kB, ...boothAt]],
  ];
  const view = (t) => { const v = SK.kf(t, CAM); return { fx: v[0], fy: v[1], fh: v[2], z: Math.exp(v[3]), k: v[4], ox: v[5], oy: v[6] }; };
  const pr = (v, x, y, h = 0) => [v.ox + (x - v.fx) * v.z, v.oy + ((y - v.fy) * v.k - (h - v.fh)) * v.z];

  function box(v, x0, y0, x1, y1, h0, h1, top, front, edge, lw) { // a block standing on the floor, seen from the front
    if (h1 - h0 > .3) quad([pr(v, x0, y1, h1), pr(v, x1, y1, h1), pr(v, x1, y1, h0), pr(v, x0, y1, h0)], front, edge, lw);
    quad([pr(v, x0, y0, h1), pr(v, x1, y0, h1), pr(v, x1, y1, h1), pr(v, x0, y1, h1)], top, edge, lw);
  }
  function person(v, x, y, hgt, col, a) { // a neutral figure: a rounded body and a head
    const [bx, by] = pr(v, x, y), z = v.z, w = 10.5 * z, bh = hgt * .74 * z, c = SK.ctx();
    SK.alpha(a, () => {
      c.fillStyle = 'rgba(11,30,50,.13)'; c.beginPath(); c.ellipse(bx, by, w * .8, w * .3, 0, 0, Math.PI * 2); c.fill();
      c.fillStyle = col; c.beginPath(); c.moveTo(bx - w / 2, by); c.lineTo(bx - w / 2, by - bh + w / 2); c.arc(bx, by - bh + w / 2, w / 2, Math.PI, 0); c.lineTo(bx + w / 2, by); c.closePath(); c.fill();
      disc(bx, by - hgt * .88 * z, 4.3 * z, col);
    });
  }
  function booth(v, t, lw) {
    const r = E.out(tw(t, T.meet - .25, T.meet + .9, E.lin)), lit = tw(t, T.booth - .1, T.booth + .35);
    const x0 = ME.x, x1 = ME.x + SW, y0 = ME.y, y1 = ME.y + SH, carpet = mix('#ffffff', Cl.blue, .16);
    quad([pr(v, x0, y0), pr(v, x1, y0), pr(v, x1, y1), pr(v, x0, y1)], mix(mix(Cl.floor, Cl.blue, lit), carpet, clamp(r * 1.6)), r > 0 ? mix(Cl.line, Cl.blue, .5) : Cl.line, lw);
    if (r < .34) { // the number on the lit stand, seen from above
      const [cx, cy] = pr(v, MX, MY);
      SK.alpha(lit * (1 - r * 3), () => (ST.booth ? textFit(ST.booth, cx, cy, { size: SW * v.z * .27, maxW: SW * v.z * .86, wt: 800, col: '#ffffff' }) : disc(cx, cy, SW * v.z * .13, '#ffffff')));
      for (let i = 0; i < 3; i++) { // rings as it lights
        const age = t - T.booth - i * .3; if (age < 0 || age > 1.3) continue;
        SK.alpha(.55 * (1 - age / 1.3), () => disc(cx, cy, (70 + age * 190) * U, null, Cl.blue, 4 * U));
      }
    }
    if (r <= 0) return;
    const a2 = tw(t, T.meet + .55, T.meet + 1.05), hw = WALL * r;
    if (r > .5) SK.alpha(clamp((r - .5) * 2), () => quad([pr(v, x0 + 9, y0 + 16), pr(v, x1 - 9, y0 + 16), pr(v, x1 - 9, y1 - 7), pr(v, x0 + 9, y1 - 7)], null, '#ffffff', lw * 1.6)); // the carpet's border
    // the back wall with its fascia, and the two returns
    const wx0 = x0 + 3, wx1 = x1 - 3, wy = y0 + 3, d = 16;
    for (const x of [wx0, wx1]) quad([pr(v, x, wy, 0), pr(v, x, wy + d, 0), pr(v, x, wy + d, hw * .8), pr(v, x, wy, hw)], Cl.side, Cl.navy, lw);
    const A = pr(v, wx0, wy, 0), B = pr(v, wx1, wy, 0), Cc = pr(v, wx1, wy, hw), D = pr(v, wx0, wy, hw);
    quad([A, B, Cc, D], '#ffffff', Cl.navy, lw);
    const ww = B[0] - A[0], wh = A[1] - D[1], band = Math.min(wh, 9 * v.z);
    quad([D, Cc, [Cc[0], Cc[1] + band], [D[0], D[1] + band]], Cl.navy);
    brandBar(D[0], D[1] + band, ww, Math.min(wh - band, 1.6 * v.z));
    if (r > .55) { // the logos on the wall, stacked
      const L = LOGOS(), a = clamp((r - .55) / .4), top = D[1] + band + 5 * v.z, room = A[1] - 15 * v.z - top;
      L.forEach((l, i) => {
        const hh = room / (L.length + .5) * l.h / 70, w = Math.min(imgW(l, hh), ww * .72);
        SK.image(l.img, (A[0] + B[0]) / 2, top + room * (i + .5) / L.length, w, null, { alpha: a });
      });
    }
    // a plant by the right return
    const px = x1 - 8, py = y0 + 36, g1 = mix(Cl.green, Cl.navy, .25);
    SK.alpha(a2, () => {
      box(v, px - 4, py - 4, px + 4, py + 4, 0, 7, Cl.side, mix(Cl.side, Cl.navy, .3), null, 0);
      [[-3.5, 12, 4.6, g1], [3.5, 13.5, 4.9, Cl.green], [0, 18, 5.3, mix(Cl.green, '#ffffff', .18)], [-1, 10.5, 4, Cl.green]].forEach(([dx, h, rr, col]) => { const p = pr(v, px + dx, py, h * r); disc(p[0], p[1], rr * v.z, col); });
    });
    // a screen on a stand, playing
    const sx0 = x0 + 13, sx1 = x0 + 43, sy = y0 + 57, sh0 = 12, sh1 = 12 + 18 * r;
    SK.alpha(a2, () => {
      line([pr(v, (sx0 + sx1) / 2, sy, 0), pr(v, (sx0 + sx1) / 2, sy, sh0)], Cl.navy, 2.2 * v.z);
      line([pr(v, (sx0 + sx1) / 2 - 6, sy, 0), pr(v, (sx0 + sx1) / 2 + 6, sy, 0)], Cl.navy, 2.2 * v.z);
      quad([pr(v, sx0, sy, sh0), pr(v, sx1, sy, sh0), pr(v, sx1, sy, sh1), pr(v, sx0, sy, sh1)], Cl.navy, Cl.navy, lw);
      quad([pr(v, sx0 + 1.5, sy, sh0 + 1.5), pr(v, sx1 - 1.5, sy, sh0 + 1.5), pr(v, sx1 - 1.5, sy, sh1 - 1.5), pr(v, sx0 + 1.5, sy, sh1 - 1.5)], mix(Cl.blue, Cl.navy, .25));
      const m = pr(v, (sx0 + sx1) / 2, sy, (sh0 + sh1) / 2), pu = 1 + .08 * Math.sin(t * 2.2);
      disc(m[0], m[1], 5.2 * v.z * pu, 'rgba(255,255,255,.2)'); SK.icon('play', m[0] + .4 * v.z, m[1], 3 * v.z, { col: '#ffffff', fill: true, w: 1 * v.z });
    });
    // someone of the team behind the counter, the counter, and a visitor
    person(v, x1 - 27, y1 - 26, 29, mix(Cl.navy, '#ffffff', .12), a2);
    const cx0 = x1 - 46, cx1 = x1 - 9, cy0 = y1 - 23, cy1 = y1 - 11, ch = 15 * r;
    box(v, cx0, cy0, cx1, cy1, 0, ch, '#ffffff', Cl.navy, Cl.navy, lw);
    const s0 = pr(v, cx0, cy1, ch), s1 = pr(v, cx1, cy1, ch);
    brandBar(s0[0], s0[1] + 2, s1[0] - s0[0], Math.max(2, 1.4 * v.z));
    person(v, x0 + 4 + 1.5 * Math.sin(t * .9), y1 + 12, 31, mix(Cl.soft, '#ffffff', .25), tw(t, T.meet + .8, T.meet + 1.3));
  }
  function route(v, t) { // from the entrance to the stand, drawn as the camera travels
    const a = tw(t, T.find, T.find + .3) * (1 - tw(t, T.meet - .55, T.meet - .15)); if (a <= 0) return;
    const p = tw(t, T.find + .15, T.booth - .05), lw = clamp(6.5 * v.z, 4.5 * U, 10 * U);
    const P = S.cut(ROUTE, 0, Math.max(.001, p)).map((q) => pr(v, q[0], q[1]));
    SK.alpha(a, () => {
      line(P, Cl.blue, lw, [lw * .1, lw * 2.1]);
      const s = pr(v, ROUTE[0][0], ROUTE[0][1]), e = P[P.length - 1];
      disc(s[0], s[1], lw * 1.5, '#ffffff', Cl.blue, lw * .7);
      disc(e[0], e[1], lw * 1.7, Cl.blue, '#ffffff', lw * .6);
    });
  }
  function plan(t, a) {
    const v = view(t), lw = clamp(.45 * v.z, 1.1, 3.2) * U, kh = 9 * (1 - v.k) / (1 - kB), flat = clamp((v.k - .9) / .1), c = SK.ctx();
    SK.alpha(a, () => {
      quad([pr(v, HALL.x0, HALL.y0), pr(v, HALL.x1, HALL.y0), pr(v, HALL.x1, HALL.y1), pr(v, HALL.x0, HALL.y1)], Cl.hall, Cl.navy, lw * 2);
      // the entrance: a gap in the wall, its two doors open
      line([pr(v, EX - 80, HALL.y1), pr(v, EX + 80, HALL.y1)], Cl.hall, lw * 5);
      for (const s of [-1, 1]) line([pr(v, EX + s * 80, HALL.y1), pr(v, EX + s * 80 - s * 34, HALL.y1 - 34)], Cl.navy, lw * 2);
      const es = 19 * v.z;
      if (FACTS.entrance && es >= 9 * U) lab(FACTS.entrance.toUpperCase(), ...pr(v, EX + 110, HALL.y1 - 38), { size: es, align: 'left', wt: 700, col: Cl.soft, ls: es * .12, alpha: flat });
      const pa = tw(t, T.ai - .3, T.ai + .3) * (1 - tw(t, T.meet - .45, T.meet + .15));
      if (ST.area) SK.alpha(pa, () => {
        c.save(); c.setLineDash([10 * U, 8 * U]);
        quad([pr(v, PAV.x0, PAV.y0), pr(v, PAV.x1, PAV.y0), pr(v, PAV.x1, PAV.y1), pr(v, PAV.x0, PAV.y1)], 'rgba(0,167,225,.10)', Cl.blue, lw * 1.4);
        c.restore();
      });
      const ns = 15 * v.z, na = flat * clamp((ns - 8 * U) / (3 * U)) * .8;
      for (const s of stands) {
        if (s.me) continue;
        const [sx, sy] = pr(v, s.x + s.w / 2, s.y + s.h / 2);
        if (Math.abs(sx) > W / 2 + s.w * v.z || Math.abs(sy) > H / 2 + s.h * v.z + 60 * v.z) continue;
        box(v, s.x, s.y, s.x + s.w, s.y + s.h, 0, kh, s.tint ? mix(Cl.floor, s.tint, .24) : Cl.floor, Cl.side, Cl.line, lw);
        const no = na > 0 ? standNo(s.c, s.r) : '';
        if (no) lab(no, sx, sy, { size: ns, wt: 700, col: s.tint ? mix(Cl.soft, s.tint, .45) : Cl.soft, alpha: na });
      }
      const as = 15 * v.z; // the aisle signs, where aisles cross
      const sa = flat * clamp((as - 9.2 * U) / U) * .9;
      if (NUM && sa > 0) for (let j = -NJ + 1; j < NJ; j += 2) for (let i = -NI; i < NI; i++) {
        const no = aisleNo((i + 1 - MI) * 2), [sx, sy] = pr(v, (i + .5) * PX, (j + .5) * PY);
        if (!no || (i === -1 && j > MJ) || Math.abs(sx) > W / 2 + 80 * v.z || Math.abs(sy) > H / 2 + 40 * v.z) continue;
        SK.alpha(sa, () => SK.pill(no, sx, sy, { size: as, fill: Cl.navy, col: '#ffffff', wt: 700, padX: as * .55 }));
      }
      route(v, t);
      if (ST.area && pa > 0 && v.k > .99) { const p = pr(v, PAV.x0, PAV.y0); SK.pill(ST.area, p[0] + 14 * U, p[1] + 36 * U, { size: 28 * U, align: 'left', fill: Cl.blue, col: '#ffffff', wt: 700, in: { t: T.ai - .2, type: 'pop' }, out: { t: T.meet - .4, type: 'fade' } }); }
      const wash = tw(t, T.meet - .1, T.meet + .8); // the hall goes quiet behind the stand
      if (wash > 0) { c.save(); c.globalAlpha *= .8 * wash; c.fillStyle = Cl.hall; c.fillRect(-W / 2 - 20, -H / 2 - 20, W + 40, H + 40); c.restore(); }
      booth(v, t, lw);
    });
  }

  // ---------------------------------------------------------------- scenes
  function title(t) { // 1. who is exhibiting (the logos, large), then the show, its dates and its city under them
    const out = T.find - .4, mw = .86 * W, n = LOGOS().length, hA = (WIDE ? 128 : 112) * U, hB = 82 * U;
    const nm = block(FACTS.show.name, mw, 190 * U, WIDE ? 2 : 3, { wt: 800 });
    const place = [FACTS.show.venue, FACTS.show.city].filter(Boolean).join(', ');
    const Y = stack([n && ['logos', hB * 1.1, 56 * U], FACTS.kicker && ['kick', 58 * U, 30 * U], ['name', nm.h, 38 * U], ['rule', 10 * U, 46 * U], FACTS.show.dates && ['dates', 56 * U, 22 * U], place && ['place', 42 * U, 0]].filter(Boolean), 14 * U);
    const g = tw(t, T.kick - .5, T.kick + .25), t0 = n ? T.kick : 0;
    if (n) SK.at(0, lerp(0, Y.logos, g), 0, lerp(1, hB / hA, g), () => logoRow(t, 0, 0, mw, hA, [Math.max(.05, T.rp - .7), T.mosaic], out));
    if (FACTS.kicker) show(0, Y.kick, t0 - .15, out, () => SK.pill(FACTS.kicker.toUpperCase(), 0, 0, { size: 30 * U, fill: Cl.navy, col: '#ffffff', ls: 3 * U, wt: 700 }), 'pop');
    show(0, Y.name, t0 + .12, out, () => drawBlock(nm, 0, 0, { wt: 800, col: Cl.navy }));
    show(0, Y.rule, t0 + .3, out, () => { const w = 240 * U * clamp(.15 + .85 * E.out(tw(t, t0 + .3, t0 + 1.1, E.lin))); brandBar(-w / 2, -5 * U, w, 10 * U); }, 'fade');
    if (FACTS.show.dates) show(0, Y.dates, Math.max(T.rsna - .1, t0 + .45), out, () => textFit(FACTS.show.dates, 0, 0, { size: 56 * U, maxW: mw, wt: 700, col: Cl.ink }));
    if (place) show(0, Y.place, Math.max(T.rsna + .25, t0 + .7), out, () => textFit(place, 0, 0, { size: 40 * U, maxW: mw, wt: 500, col: Cl.soft }));
  }
  function tag(t) { // 2. the stand's hall and number, beside it
    if (t < T.booth - .2 || t > T.meet + .2) return;
    show(tagAt[0], tagAt[1], T.booth - .1, T.meet - .35, () => {
      const bw = Math.min(WIDE ? .38 * W : .8 * W, 640 * U), top = [ST.hall, ST.booth ? ST.word : ''].filter(Boolean).join(' · ').toUpperCase();
      const big = block(BIG, bw * .86, 130 * U, 3, { wt: 800 }), bh = big.h + (top ? 150 : 96) * U, y0 = -bh / 2;
      SK.card(-bw / 2, y0, bw, bh, { r: 22 * U, fill: '#ffffff', shadow: { blur: 40 * U, y: 14 * U, col: 'rgba(11,56,90,.18)' } });
      brandBar(-bw / 2 + 22 * U, y0, bw - 44 * U, 6 * U);
      if (top) textFit(top, 0, y0 + 64 * U, { size: 32 * U, maxW: bw * .86, wt: 700, col: Cl.soft, ls: 3 * U });
      drawBlock(big, 0, y0 + (top ? 102 : 48) * U + big.h / 2, { wt: 800, col: Cl.navy });
    }, 'pop');
  }
  function header(t) { // the stand's line over the booth
    const s = [ST.hall, ST.booth ? `${ST.word} ${ST.booth}` : '', ST.area].filter(Boolean).join('  ·  ');
    const x = 0, y = -H / 2 + 78 * U; if (!s) return;
    show(x, y, T.meet + .3, T.end - .4, () => {
      const size = SK.fit(s, .86 * W - 60 * U, { font: FACTS.font, size: 34 * U, wt: 700 });
      SK.pill(s, 0, 0, { size, fill: '#ffffff', col: Cl.navy, stroke: Cl.line, strokeW: 2 * U, wt: 700, shadow: { blur: 24 * U, y: 8 * U, col: 'rgba(11,56,90,.14)' } });
    });
  }
  function rowsOrColumn(n, cardH, gap, maxW) { // centres for n cards in the panel zone
    if (WIDE) { const tot = n * cardH + (n - 1) * gap; return [...Array(n)].map((_, i) => [zone.cx, zone.cy - tot / 2 + cardH / 2 + i * (cardH + gap)]); }
    const tot = n * cardH + (n - 1) * gap;
    return [...Array(n)].map((_, i) => [zone.cx, zone.cy - tot / 2 + cardH / 2 + i * (cardH + gap)]);
  }
  function signs(t) { // 3. up to four things to see at the stand
    const L = FACTS.see.slice(0, 4);
    if (!L.length) { // nothing published to see: the show and its dates hold the place
      const nm = block(FACTS.show.name, zone.w, 84 * U, 3, { wt: 800 });
      show(zone.cx, zone.cy, T.meet + .3, T.hours - .45, () => {
        if (FACTS.findUs) textFit(FACTS.findUs.toUpperCase(), 0, -nm.h / 2 - 44 * U, { size: 30 * U, maxW: zone.w, wt: 700, col: Cl.royal, ls: 4 * U });
        drawBlock(nm, 0, 0, { wt: 800, col: Cl.navy });
        textFit(FACTS.show.dates, 0, nm.h / 2 + 52 * U, { size: 40 * U, maxW: zone.w, wt: 600, col: Cl.ink });
      });
      return;
    }
    const ch = 118 * U, cw = zone.w, P = rowsOrColumn(L.length, ch, 22 * U, cw);
    L.forEach((it, i) => show(P[i][0], P[i][1], SEE_T[i], T.hours - .45, () => {
      SK.card(-cw / 2, -ch / 2, cw, ch, { r: 20 * U, fill: '#ffffff', stroke: Cl.line, strokeW: 2 * U, shadow: { blur: 30 * U, y: 10 * U, col: 'rgba(11,56,90,.14)' } });
      const ix = -cw / 2 + 64 * U, c = SK.ctx();
      c.fillStyle = Cl.navy; c.beginPath(); c.arc(ix, 0, 36 * U, 0, Math.PI * 2); c.fill();
      SK.icon(it.icon, ix, 0, 19 * U, { col: '#ffffff', w: 4 * U });
      textFit(it.text, ix + 62 * U, 2 * U, { size: 42 * U, maxW: cw - 160 * U, wt: 700, col: Cl.ink, align: 'left' });
    }));
  }
  function hours(t) { // 4a. when the hall is open
    const Hs = FACTS.hours, D = Hs.days.slice(0, 5), n = D.length, gap = 16 * U;
    const cw = Math.min(250 * U, (zone.w - (n - 1) * gap) / Math.max(1, n)), ch = 150 * U, top = zone.cy - 175 * U;
    if (Hs.title) show(zone.cx, top, T.hours, T.end - .4, () => textFit(Hs.title, 0, 0, { size: 44 * U, maxW: zone.w, wt: 800, col: Cl.navy }));
    const x0 = zone.cx - (n * cw + (n - 1) * gap) / 2 + cw / 2, dt = n > 1 ? (T.wed - T.sunday) / (n - 1) : 0;
    D.forEach((d, i) => show(x0 + i * (cw + gap), top + 140 * U, T.sunday + i * dt, T.end - .4, () => {
      SK.card(-cw / 2, -ch / 2, cw, ch, { r: 18 * U, fill: '#ffffff', stroke: Cl.line, strokeW: 2 * U, shadow: { blur: 26 * U, y: 8 * U, col: 'rgba(11,56,90,.13)' } });
      brandBar(-cw / 2 + 18 * U, -ch / 2, cw - 36 * U, 5 * U);
      textFit(d.d.toUpperCase(), 0, -30 * U, { size: 30 * U, maxW: cw * .84, wt: 700, col: Cl.soft, ls: 2 * U });
      textFit(d.date, 0, 26 * U, { size: 46 * U, maxW: cw * .86, wt: 800, col: Cl.navy });
    }, 'pop'));
    if (Hs.time) show(zone.cx, top + 290 * U, T.ten - .1, T.end - .4, () => SK.pill(Hs.time, 0, 0, { size: 40 * U, fill: Cl.blue, col: '#ffffff', wt: 700, icon: 'clock' }), 'pop');
  }
  function endCard(t) { // 5. the booth number large, the dates, the logos and the link
    const u = E.out(tw(t, T.end - .45, T.end + .35, E.lin)); if (u <= 0) return;
    const y0 = -H / 2 + (1 - u) * H, c = SK.ctx();
    c.fillStyle = '#ffffff'; c.fillRect(-W / 2 - 20, y0, W + 40, H + 40); brandBar(-W / 2 - 20, y0, W + 40, 12 * U);
    const br = 1 + .015 * Math.sin(Math.max(0, t - T.end) * 1.4);
    SK.at(0, (1 - u) * H, 0, 1 + .045 * E.sine(tw(t, T.end, 30, E.lin)), () => endBody(t, T.end - .35, .86 * W, br));
  }
  function endBody(t, t0, mw, br) {
    const find = (ST.booth ? `${FACTS.findUs} ${FACTS.show.name}` : FACTS.findUs || '').toUpperCase();
    const where = [ST.hall, ST.booth ? ST.word : ''].filter(Boolean).join(' · ').toUpperCase();
    const big = block(BIG, mw, 230 * U, WIDE ? 2 : 3, { wt: 800 });
    const when = block([FACTS.show.dates, [FACTS.show.venue, FACTS.show.city].filter(Boolean).join(', ')].filter(Boolean).join('  ·  '), mw, 40 * U, 2, { wt: 600 });
    const n = LOGOS().length;
    const Y = stack([find && ['find', 34 * U, 22 * U], where && ['where', 36 * U, 26 * U], ['big', big.h * (big.lines.length > 1 ? 1.04 : .86), 44 * U], ST.area && ['area', 60 * U, 34 * U], when.h && ['when', when.h, 50 * U], n && ['logos', 72 * U, 40 * U], FACTS.link && ['link', 34 * U, 0]].filter(Boolean), 10 * U);
    if (find) show(0, Y.find, t0, 0, () => textFit(find, 0, 0, { size: 34 * U, maxW: mw, wt: 700, col: Cl.royal, ls: 4 * U }));
    if (where) show(0, Y.where, t0 + .1, 0, () => textFit(where, 0, 0, { size: 36 * U, maxW: mw, wt: 700, col: Cl.soft, ls: 3 * U }));
    show(0, Y.big, t0 + .15, 0, () => SK.at(0, 0, 0, br, () => drawBlock(big, 0, 0, { wt: 800, col: Cl.navy })), 'pop');
    if (ST.area) show(0, Y.area, t0 + .35, 0, () => SK.pill(ST.area, 0, 0, { size: 34 * U, fill: Cl.blue, col: '#ffffff', wt: 700 }), 'pop');
    if (when.h) show(0, Y.when, t0 + .5, 0, () => drawBlock(when, 0, 0, { wt: 600, col: Cl.ink }));
    if (n) logoRow(t, 0, Y.logos, mw * .9, 66 * U, [t0 + .7, t0 + .8], 0);
    if (FACTS.link) show(0, Y.link, t0 + 1, 0, () => textFit(FACTS.link, 0, 0, { size: 32 * U, maxW: mw, wt: 600, col: Cl.navy }));
  }

  SK.film({
    duration: 30,
    camera: SK.camera([[0, [0, 0, 1]]]),
    draw(t) {
      plan(t, lerp(.16, 1, tw(t, T.find - .5, T.find + .4)));
      if (t < T.find + .2) SK.at(0, 0, 0, 1 + .05 * E.sine(tw(t, 0, T.find, E.lin)), () => title(t));
      tag(t);
      if (t > T.meet - .5 && t < T.end + .5) { header(t); signs(t); hours(t); }
      endCard(t);
      brandBar(-W / 2 - 20, -H / 2 - 20, W + 40, 30 + 10 * U); // their banner's strip, along the top
    },
  });
})();
