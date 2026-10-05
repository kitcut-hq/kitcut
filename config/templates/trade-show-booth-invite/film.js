// For: visitors heading to a trade show; a polished, warm, brand-led invitation to the exhibitor's stand
(function () {
  'use strict';
  const { E, clamp, lerp, tw, mix } = SK;
  SK.setStyle('clean');

  // ---------------------------------------------------------------- every fact, colour and picture name
  const FACTS = SK.DATA.content;

  const Cl = FACTS.colors, ST = FACTS.stand;
  SK.setGround('white', { text: Cl.ink, textSoft: Cl.soft, accent: Cl.blue, accentText: Cl.navy });
  SK.KIT.font = FACTS.font;
  const W = SK.W, H = SK.H, U = Math.min(W, H) / 1080, WIDE = W / H > 1.3;
  const T = SK.cues({
    rp: [0, 'Radiology'], mosaic: [0, 'Mosaic'], rsna: [0, 'RSNA'], year: [0, 'twenty'],
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
  function quad(P, fill, stroke, lw) {
    const c = SK.ctx(); c.beginPath(); P.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.closePath();
    if (fill) { c.fillStyle = fill; c.fill(); }
    if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw; c.lineJoin = 'round'; c.stroke(); }
  }
  function brandBar(x0, y0, w, h) { // the gradient strip of their RSNA banner
    const c = SK.ctx(), g = c.createLinearGradient(x0, 0, x0 + w, 0);
    g.addColorStop(0, Cl.royal); g.addColorStop(.55, Cl.blue); g.addColorStop(1, Cl.green);
    c.fillStyle = g; c.fillRect(x0, y0, w, h);
  }
  const imgW = (l, h) => { const im = SK.IMG[l.img]; return im ? h * im.width / im.height : 0; };
  function logoRow(cx, cy, maxW, hgt, times, tout) { // 1..n logos in a row, divided
    const L = FACTS.logos.filter((l) => SK.IMG[l.img]); if (!L.length) return;
    const gap = 60 * U, ws = L.map((l) => imgW(l, l.h / 66 * hgt)), tot = ws.reduce((a, b) => a + b, 0) + gap * (L.length - 1), k = Math.min(1, maxW / tot);
    let x = cx - tot * k / 2;
    L.forEach((l, i) => {
      const w = ws[i] * k, ti = times[Math.min(i, times.length - 1)];
      if (i) show(x - gap * k / 2, cy, ti, tout, () => quad([[-1, -hgt * .45 * k], [1, -hgt * .45 * k], [1, hgt * .45 * k], [-1, hgt * .45 * k]], Cl.line), 'fade');
      show(x + w / 2, cy, ti, tout, () => SK.image(l.img, 0, 0, w));
      x += w + gap * k;
    });
  }

  // ---------------------------------------------------------------- the hall: a generic grid of stands
  const SW = 100, SH = 80, PX = 260, PY = 220, NI = 5, NJ = 3, MI = 2, MJ = -1;
  const stands = [];
  for (let j = -NJ; j <= NJ; j++) for (let i = -NI; i <= NI; i++) for (let b = 0; b < 2; b++) for (let a = 0; a < 2; a++)
    stands.push({ x: i * PX - SW + a * SW, y: j * PY - SH + b * SH, me: i === MI && j === MJ && a === 0 && b === 1 });
  stands.sort((p, q) => p.y - q.y || p.x - q.x);
  const ME = stands.find((s) => s.me), MX = ME.x + SW / 2, MY = ME.y + SH / 2;
  const PAV = { x0: (MI - 1) * PX - SW - 40, x1: (MI + 1) * PX + SW + 40, y0: (MJ - 1) * PY - SH - 40, y1: MJ * PY + SH + 40 };
  const HALL = { x0: -NI * PX - SW - 90, x1: NI * PX + SW + 90, y0: -NJ * PY - SH - 90, y1: NJ * PY + SH + 90 };

  // the plan's camera: focus (x, y, height) lands at screen (ox, oy); k tilts the floor (1 = from above)
  const z0 = .93 * Math.min(W / (HALL.x1 - HALL.x0), H / (HALL.y1 - HALL.y0)), zF = 1.25 * U;
  const zB = .62 * (WIDE ? Math.min(W, H) : Math.min(W, H * .6)) / SW, kB = .52, WALL = 54;
  const standAt = WIDE ? [-.2 * W, .05 * H] : [0, -.16 * H];
  const boothAt = WIDE ? [-.22 * W, .03 * H] : [0, -H / 2 + 165 * U + 48 * zB];
  const zone = WIDE ? { cx: .25 * W, cy: .03 * H, w: .42 * W } : { cx: 0, w: Math.min(.88 * W, 820 * U), top: boothAt[1] + 48 * zB + 60 * U };
  if (!WIDE) zone.cy = (zone.top + H / 2 - 50 * U) / 2;
  const tagAt = WIDE ? [.25 * W, 0] : [0, (standAt[1] + 70 * U + H / 2) / 2];
  const CAM = [
    [0, [0, 0, 0, Math.log(z0), 1, 0, 0]],
    [T.find - .2, [170, -100, 0, Math.log(z0 * 1.16), 1, 0, 0]],
    [T.booth + .1, [MX, MY, 0, Math.log(zF), 1, ...standAt]],
    [T.meet - .3, [MX, MY, 0, Math.log(zF * 1.1), 1, ...standAt]],
    [T.meet + .9, [MX, ME.y, 6, Math.log(zB), kB, ...boothAt]],
    [T.end, [MX, ME.y, 6, Math.log(zB * 1.06), kB, ...boothAt]],
    [30, [MX, ME.y, 6, Math.log(zB * 1.1), kB, ...boothAt]],
  ];
  const view = (t) => { const v = SK.kf(t, CAM); return { fx: v[0], fy: v[1], fh: v[2], z: Math.exp(v[3]), k: v[4], ox: v[5], oy: v[6] }; };
  const pr = (v, x, y, h = 0) => [v.ox + (x - v.fx) * v.z, v.oy + ((y - v.fy) * v.k - (h - v.fh)) * v.z];

  function standBox(v, x0, y0, x1, y1, h, top, front, lw) {
    if (h > .3) quad([pr(v, x0, y1, h), pr(v, x1, y1, h), pr(v, x1, y1, 0), pr(v, x0, y1, 0)], front, Cl.line, lw);
    quad([pr(v, x0, y0, h), pr(v, x1, y0, h), pr(v, x1, y1, h), pr(v, x0, y1, h)], top, Cl.line, lw);
  }
  function booth(v, t, lw) {
    const r = E.out(tw(t, T.meet - .25, T.meet + .9, E.lin)), lit = tw(t, T.booth - .1, T.booth + .35);
    standBox(v, ME.x, ME.y, ME.x + SW, ME.y + SH, 0, mix(Cl.floor, Cl.blue, lit), null, lw);
    if (r <= 0) { // the number on the lit stand, seen from above
      const [cx, cy] = pr(v, MX, MY);
      SK.alpha(lit, () => textFit(BIG, cx, cy, { size: SW * v.z * .27, maxW: SW * v.z * .86, wt: 800, col: '#ffffff' }));
      for (let i = 0; i < 3; i++) { // rings as it lights
        const age = t - T.booth - i * .3; if (age < 0 || age > 1.3) continue;
        const c = SK.ctx(); c.save(); c.globalAlpha *= .55 * (1 - age / 1.3); c.strokeStyle = Cl.blue; c.lineWidth = 4 * U;
        c.beginPath(); c.arc(cx, cy, (70 + age * 190) * U, 0, Math.PI * 2); c.stroke(); c.restore();
      }
      return;
    }
    const hw = WALL * r, x0 = ME.x + 3, x1 = ME.x + SW - 3, y0 = ME.y + 3, d = 16;
    for (const x of [x0, x1]) quad([pr(v, x, y0, 0), pr(v, x, y0 + d, 0), pr(v, x, y0 + d, hw * .8), pr(v, x, y0, hw)], Cl.side, Cl.navy, lw);
    const A = pr(v, x0, y0, 0), B = pr(v, x1, y0, 0), Cc = pr(v, x1, y0, hw), D = pr(v, x0, y0, hw);
    quad([A, B, Cc, D], '#ffffff', Cl.navy, lw);
    const ww = B[0] - A[0], wh = A[1] - D[1], band = Math.min(wh, 9 * v.z);
    quad([D, Cc, [Cc[0], Cc[1] + band], [D[0], D[1] + band]], Cl.navy);
    brandBar(D[0], D[1] + band, ww, Math.min(wh - band, 1.6 * v.z));
    if (r > .55) { // the logos on the wall, stacked
      const L = FACTS.logos.filter((l) => SK.IMG[l.img]), a = clamp((r - .55) / .4);
      const y0s = D[1] + band + 4 * v.z, room = A[1] - y0s;
      L.forEach((l, i) => {
        const hh = Math.min(room / (L.length + .6) * l.h / 70, 999), w = Math.min(imgW(l, hh), ww * .8);
        SK.image(l.img, (A[0] + B[0]) / 2, y0s + room * (i + .65) / (L.length + .3), w, null, { alpha: a });
      });
    }
    const cx0 = MX - 24, cx1 = MX + 24, cy0 = ME.y + SH - 30, cy1 = ME.y + SH - 18, ch = 15 * r; // the counter
    quad([pr(v, cx0, cy1, ch), pr(v, cx1, cy1, ch), pr(v, cx1, cy1, 0), pr(v, cx0, cy1, 0)], Cl.navy, Cl.navy, lw);
    quad([pr(v, cx0, cy0, ch), pr(v, cx1, cy0, ch), pr(v, cx1, cy1, ch), pr(v, cx0, cy1, ch)], '#ffffff', Cl.navy, lw);
    const s0 = pr(v, cx0, cy1, ch), s1 = pr(v, cx1, cy1, ch);
    brandBar(s0[0], s0[1] + 2, s1[0] - s0[0], Math.max(2, 1.4 * v.z));
  }
  function plan(t, a) {
    const v = view(t), lw = clamp(.45 * v.z, 1.1, 3.2) * U, kh = 9 * (1 - v.k) / (1 - kB);
    SK.alpha(a, () => {
      quad([pr(v, HALL.x0, HALL.y0), pr(v, HALL.x1, HALL.y0), pr(v, HALL.x1, HALL.y1), pr(v, HALL.x0, HALL.y1)], Cl.hall, Cl.navy, lw * 2);
      const pa = tw(t, T.ai - .3, T.ai + .3);
      SK.alpha(pa, () => {
        const c = SK.ctx(); c.save(); c.setLineDash([10 * U, 8 * U]);
        quad([pr(v, PAV.x0, PAV.y0), pr(v, PAV.x1, PAV.y0), pr(v, PAV.x1, PAV.y1), pr(v, PAV.x0, PAV.y1)], 'rgba(0,167,225,.10)', Cl.blue, lw * 1.4);
        c.restore();
      });
      let done = false;
      for (const s of stands) {
        if (!done && s.y > ME.y) { booth(v, t, lw); done = true; }
        if (s.me) continue;
        const [sx, sy] = pr(v, s.x + SW / 2, s.y + SH / 2);
        if (Math.abs(sx) > W / 2 + SW * v.z || Math.abs(sy) > H / 2 + SH * v.z + 60 * v.z) continue;
        standBox(v, s.x, s.y, s.x + SW, s.y + SH, kh, Cl.floor, Cl.side, lw);
      }
      if (!done) booth(v, t, lw);
      if (pa > 0 && v.k > .99) { const p = pr(v, PAV.x0, PAV.y0); SK.pill(ST.area, p[0] + 14 * U, p[1] + 36 * U, { size: 28 * U, align: 'left', fill: Cl.blue, col: '#ffffff', wt: 700, in: { t: T.ai - .2, type: 'pop' }, out: { t: T.meet - .4, type: 'fade' } }); }
    });
  }

  // ---------------------------------------------------------------- scenes
  function title(t) { // 1. we're exhibiting: the show, its dates and city, the logos
    const out = T.find - .45, cy = -15 * U, mw = .86 * W;
    show(0, cy - 255 * U, -.3, out, () => SK.pill(FACTS.kicker.toUpperCase(), 0, 0, { size: 30 * U, fill: Cl.navy, col: '#ffffff', ls: 3 * U, wt: 700 }));
    show(0, cy - 110 * U, -.25, out, () => lab(FACTS.show.name, 0, 0, { size: 190 * U, maxW: mw, wt: 800, col: Cl.navy }));
    show(0, cy + 2 * U, .1, out, () => { const w = 240 * U * clamp(.2 + .8 * E.out(tw(t, .1, .9, E.lin))); brandBar(-w / 2, -5 * U, w, 10 * U); }, 'fade');
    show(0, cy + 78 * U, T.rsna, out, () => textFit(FACTS.show.dates, 0, 0, { size: 56 * U, maxW: mw, wt: 700, col: Cl.ink }));
    show(0, cy + 148 * U, T.year, out, () => textFit([FACTS.show.venue, FACTS.show.city].filter(Boolean).join(', '), 0, 0, { size: 40 * U, maxW: mw, wt: 500, col: Cl.soft }));
    logoRow(0, cy + 280 * U, mw, 66 * U, [T.rp, T.mosaic], out);
  }
  function tag(t) { // 2. the stand's hall and number, beside it
    if (t < T.booth - .2 || t > T.meet + .2) return;
    show(tagAt[0], tagAt[1], T.booth - .1, T.meet - .35, () => {
      const bw = Math.min(WIDE ? .38 * W : .8 * W, 640 * U), bh = 290 * U;
      SK.card(-bw / 2, -bh / 2, bw, bh, { r: 22 * U, fill: '#ffffff', shadow: { blur: 40 * U, y: 14 * U, col: 'rgba(11,56,90,.18)' } });
      brandBar(-bw / 2 + 22 * U, -bh / 2, bw - 44 * U, 6 * U);
      textFit([ST.hall, ST.booth ? ST.word : ''].filter(Boolean).join(' · ').toUpperCase(), 0, -80 * U, { size: 32 * U, maxW: bw * .86, wt: 700, col: Cl.soft, ls: 3 * U });
      textFit(BIG, 0, 20 * U, { size: 130 * U, maxW: bw * .86, wt: 800, col: Cl.navy });
    }, 'pop');
  }
  function header(t) { // the stand's line over the booth
    const s = [ST.hall, ST.booth ? `${ST.word} ${ST.booth}` : '', ST.area].filter(Boolean).join('  ·  ');
    const x = 0, y = -H / 2 + 78 * U;
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
    const L = FACTS.see.slice(0, 4); if (!L.length) return;
    const ch = 118 * U, cw = zone.w, P = rowsOrColumn(L.length, ch, 22 * U, cw);
    L.forEach((it, i) => show(P[i][0], P[i][1], SEE_T[i], T.hours - .45, () => {
      SK.card(-cw / 2, -ch / 2, cw, ch, { r: 20 * U, fill: '#ffffff', stroke: Cl.line, strokeW: 2 * U, shadow: { blur: 30 * U, y: 10 * U, col: 'rgba(11,56,90,.14)' } });
      const ix = -cw / 2 + 64 * U, c = SK.ctx();
      c.fillStyle = Cl.navy; c.beginPath(); c.arc(ix, 0, 36 * U, 0, Math.PI * 2); c.fill();
      SK.icon(it.icon, ix, 0, 19 * U, { col: '#ffffff', w: 4 * U });
      textFit(it.text, ix + 60 * U + (cw - 160 * U) / 2, 2 * U, { size: 42 * U, maxW: cw - 160 * U, wt: 700, col: Cl.ink });
    }));
  }
  function hours(t) { // 4a. when the hall is open
    const Hs = FACTS.hours, D = Hs.days.slice(0, 4), n = D.length, gap = 16 * U;
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
  function endCard(t) { // 4b. the booth number large, the dates, the logos and the link
    const u = E.out(tw(t, T.end - .45, T.end + .35, E.lin)); if (u <= 0) return;
    const y0 = -H / 2 + (1 - u) * H, c = SK.ctx();
    c.fillStyle = '#ffffff'; c.fillRect(-W / 2 - 20, y0, W + 40, H + 40); brandBar(-W / 2 - 20, y0, W + 40, 12 * U);
    const t0 = T.end - .35, mw = .86 * W, cy = 0, br = 1 + .015 * Math.sin(Math.max(0, t - T.end) * 1.4);
    SK.at(0, (1 - u) * H, 0, 1 + .045 * E.sine(tw(t, T.end, 30, E.lin)), () => endBody(t, t0, mw, cy, br));
  }
  function endBody(t, t0, mw, cy, br) {
    show(0, cy - 300 * U, t0, 0, () => textFit(`${FACTS.findUs} ${FACTS.show.name}`.toUpperCase(), 0, 0, { size: 34 * U, maxW: mw, wt: 700, col: Cl.royal, ls: 4 * U }));
    show(0, cy - 240 * U, t0 + .1, 0, () => textFit([ST.hall, ST.booth ? ST.word : ''].filter(Boolean).join(' · ').toUpperCase(), 0, 0, { size: 36 * U, maxW: mw, wt: 700, col: Cl.soft, ls: 3 * U }));
    show(0, cy - 105 * U, t0 + .15, 0, () => SK.at(0, 0, 0, br, () => textFit(BIG, 0, 0, { size: 230 * U, maxW: mw, wt: 800, col: Cl.navy })), 'pop');
    if (ST.area) show(0, cy + 40 * U, t0 + .35, 0, () => SK.pill(ST.area, 0, 0, { size: 34 * U, fill: Cl.blue, col: '#ffffff', wt: 700 }), 'pop');
    show(0, cy + 125 * U, t0 + .5, 0, () => textFit([FACTS.show.dates, [FACTS.show.venue, FACTS.show.city].filter(Boolean).join(', ')].filter(Boolean).join('  ·  '), 0, 0, { size: 40 * U, maxW: mw, wt: 600, col: Cl.ink }));
    logoRow(0, cy + 235 * U, mw * .9, 62 * U, [t0 + .7, t0 + .8], 0);
    if (FACTS.link) show(0, cy + 330 * U, t0 + 1, 0, () => textFit(FACTS.link, 0, 0, { size: 32 * U, maxW: mw, wt: 600, col: Cl.navy }));
  }

  SK.film({
    duration: 30,
    camera: SK.camera([[0, [0, 0, 1]]]),
    draw(t) {
      plan(t, lerp(.13, 1, tw(t, T.find - .5, T.find + .4)));
      if (t < T.find + .2) SK.at(0, 0, 0, 1 + .06 * E.sine(tw(t, 0, T.find, E.lin)), () => title(t));
      tag(t);
      if (t > T.meet - .5 && t < T.end + .5) { header(t); signs(t); hours(t); }
      endCard(t);
      brandBar(-W / 2 - 20, -H / 2 - 20, W + 40, 30 + 10 * U); // their banner's strip, along the top
    },
  });
})();
