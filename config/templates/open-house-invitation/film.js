// For: home shoppers who follow a builder or a local agent on social; bright, calm, upscale and inviting
(function () {
  'use strict';
  const { S, E, clamp, lerp, inv, tw } = SK;

  /* Every fact, colour and picture of the event: a remake changes this object alone. */
  const FACTS = SK.DATA.content;
  const K = FACTS.colors, FH = FACTS.fonts.head, FB = FACTS.fonts.body;
  SK.setStyle('clean');
  SK.setGround('sky', { paper: K.panel, text: K.ink, textSoft: K.soft, accent: K.blue, accentText: K.blue });

  const T = SK.cues({
    invite: [0, 'invited'], drift: [0, 'Driftwood'], pep: [0, 'Pepperwood'], sat: [1, 'Saturday'], noon: [1, 'noon'],
    bed: [2, 'bedrooms'], bath: [2, 'baths'], sqft: [2, 'thousand'], feet: [2, 'feet'],
    tour: [3, 'Tour'], find: [4, 'Find'], welcome: [4, 'Welcome'], helms: [4, 'Helmsman'],
    bring: [5, 'Bring'],
  });

  // layout from the frame: a picture area A and a text area B, side by side or stacked
  const W = SK.W, H = SK.H, U = Math.min(W, H) / 1080, wide = W / H > 1.25;
  const A = wide ? { cx: -W * .21, cy: 0, w: W * .46, h: H * .8 } : { cx: 0, cy: H * .17, w: W * .86, h: H * .5 };
  const B = wide ? { x: W * .02, cy: 0, w: W * .42 } : { x: -W * .43, cy: -H * .28, w: W * .86 };
  const rect = (cx, cy, w, h) => [cx - w / 2, cy - h / 2, w, h];
  const R1 = (() => { const w = wide ? W * .7 : W * .88, h = wide ? w / 2.3 : w / 1.25; return rect(0, -H * .07, w, h); })();
  const R2 = wide ? rect(A.cx, 0, A.w, A.w / 1.3) : rect(0, -H * .22, W * .88, H * .3);
  const PIN = wide ? [W * .1, H * .14] : [0, H * .16];
  const R4 = rect(PIN[0], PIN[1] - 370 * U, 380 * U, 220 * U);

  /* text: fitted to a width, wrapped onto two lines when shrinking would go too small */
  function fit(str, maxW, o) {
    const c = SK.ctx(); c.font = `${o.wt ?? 400} ${o.size}px "${o.font ?? FB}"`;
    const w = c.measureText(str).width + (o.ls ?? 0) * [...str].length;
    return w > maxW ? o.size * maxW / w : o.size;
  }
  function text(str, x, y, maxW, o) {
    let size = fit(str, maxW, o);
    if (size >= o.size * .72 || !str.includes(' ')) { SK.txt(str, x, y, { ...o, size }); return size; }
    const ws = str.split(' '); let best = 1, bd = 1e9;
    for (let i = 1; i < ws.length; i++) { const d = Math.abs(ws.slice(0, i).join(' ').length - ws.slice(i).join(' ').length); if (d < bd) { bd = d; best = i; } }
    const l1 = ws.slice(0, best).join(' '), l2 = ws.slice(best).join(' ');
    size = Math.min(fit(l1, maxW, o), fit(l2, maxW, o));
    SK.txt(l1, x, y - size * .55, { ...o, size }); SK.txt(l2, x, y + size * .55, { ...o, size });
    return size;
  }
  const ent = (t, t0, d = .5) => E.out(inv(t0, t0 + d, t));

  /* a picture cropped to cover a box (top-left x, y), pushed in by zoom toward fx */
  function photo(f, x, y, w, h, zoom, fx) {
    const im = SK.IMG[f.img]; if (!im) return;
    const [cx, cy, cw, ch] = f.crop || [0, 0, im.width, im.height];
    const k = Math.max(w / cw, h / ch) * zoom, sw = w / k, sh = h / k;
    const c = SK.ctx(); c.save(); if (f.lift) c.filter = `brightness(${f.lift}) contrast(1.06) saturate(1.1)`;
    c.drawImage(im, cx + (cw - sw) * (fx ?? .5), cy + (ch - sh) * .5, sw, sh, x, y, w, h); c.restore();
  }
  function frame(r, t, draw, a = 1) {
    SK.card(r[0], r[1], r[2], r[3], { r: 18 * U, fill: K.white, alpha: a, shadow: { blur: 40, y: 16, col: 'rgba(29,58,99,.18)' }, clip: draw });
  }
  const pill = (str, x, y, o = {}) => SK.pill(str, x, y, { size: 34 * U, font: FB, fill: o.fill ?? K.white, col: o.col ?? K.ink, r: 30 * U, padX: 26 * U, align: o.align ?? 'left', ...o });

  /* beat 1: the yard sign swings in on its hooks */
  function sign(t, a) {
    const pw = Math.min(A.w * .8, A.h * .62 / .9), ph = pw * .9, armY = A.cy - A.h * .42, top = armY + 34 * U;
    const px = A.cx - pw / 2 - 70 * U, bot = A.cy + A.h * .5;
    const swing = .34 * Math.exp(-1.3 * t) * Math.cos(4.2 * t) + .015 * Math.sin(t * 1.4);
    SK.alpha(a, () => {
      const c = SK.ctx(); c.fillStyle = K.navy;
      c.fillRect(px - 11 * U, armY - 30 * U, 22 * U, bot - armY + 30 * U);
      c.fillRect(px - 30 * U, armY - 9 * U, pw + 110 * U, 18 * U);
      SK.at(A.cx, armY, swing, 1, () => {
        c.strokeStyle = K.navy; c.lineWidth = 4 * U;
        for (const sx of [-.36, .36]) { c.beginPath(); c.moveTo(sx * pw, 0); c.lineTo(sx * pw, 34 * U); c.stroke(); }
        const y0 = 34 * U, x0 = -pw / 2;
        SK.card(x0, y0, pw, ph, { r: 10 * U, fill: K.white, shadow: { blur: 30, y: 18, col: 'rgba(29,58,99,.22)' } });
        SK.image(FACTS.logo, 0, y0 + ph * .13, pw * .66);
        c.fillStyle = K.blue; c.fillRect(x0, y0 + ph * .26, pw, ph * .24);
        text(FACTS.kicker.toUpperCase(), 0, y0 + ph * .38, pw * .86, { size: 46 * U, font: FB, wt: 700, col: K.white, ls: 3 * U });
        text(FACTS.day, 0, y0 + ph * .64, pw * .86, { size: 62 * U, font: FH, wt: 400, col: K.ink });
        text(FACTS.hours, 0, y0 + ph * .82, pw * .8, { size: 66 * U, font: FB, wt: 500, col: K.blue });
      });
    });
  }
  function headline(t, a) {
    const al = wide ? 'left' : 'center', x = wide ? B.x : 0, y = B.cy, mw = B.w;
    SK.alpha(a, () => {
      text(FACTS.invite.toUpperCase(), x, y - 190 * U, mw, { size: 36 * U, font: FB, wt: 700, col: K.blue, ls: 5 * U, align: al, p: clamp(.6 + .4 * ent(t, 0, .5)) });
      text(FACTS.home, x, y - 80 * U, mw, { size: 132 * U, font: FH, wt: 300, col: K.ink, align: al, p: ent(t, T.drift - .2, .6) });
      text(FACTS.homeSub, x, y + 30 * U, mw, { size: 60 * U, font: FH, wt: 300, col: K.ink, align: al, p: ent(t, T.pep - .5, .6) });
      const rl = mw * .3 * ent(t, T.pep, .6), rx = wide ? x : -rl / 2;
      const c = SK.ctx(); c.fillStyle = K.blue; c.fillRect(rx, y + 100 * U, rl, 4 * U);
      text(FACTS.city, x, y + 160 * U, mw, { size: 40 * U, font: FB, wt: 500, col: K.soft, align: al, p: ent(t, T.pep + .2, .5) });
    });
  }

  /* the one frame that carries the film: exterior, facts, rooms, then the pin's card */
  const RK = [[T.sat - .35, R1], [T.bed - .5, R1], [T.bed, R2], [T.tour - .45, R2], [T.tour, R1], [T.find - .5, R1], [T.welcome + .2, R4]];
  function frameRect(t) { return SK.kf(t, RK.map(([k, r]) => [k, r])); }
  function frameContent(t, r) {
    const n = FACTS.rooms.length, s0 = T.tour, s1 = Math.max(T.tour + .5, T.find - .6);
    const starts = FACTS.rooms.map((_, i) => lerp(s0, s1, i / n));
    const backAt = T.find - .5, hz = 1 + .12 * tw(t, T.sat - .35, T.tour, E.lin);
    photo(FACTS.hero, r[0], r[1], r[2], r[3], hz, lerp(FACTS.hero.fx[0], FACTS.hero.fx[1], tw(t, T.sat, T.tour, E.sine)));
    FACTS.rooms.forEach((m, i) => {
      const u = E.inOut(inv(starts[i], starts[i] + .45, t)), out = t > backAt ? 1 - E.inOut(inv(backAt, backAt + .4, t)) : 1;
      if (u <= 0 || out <= 0) return;
      const c = SK.ctx(); c.save(); c.beginPath(); c.rect(r[0] + r[2] * (1 - u), r[1], r[2] * u, r[3]); c.clip();
      SK.alpha(out, () => photo(m, r[0], r[1], r[2], r[3], 1 + .06 * inv(starts[i], starts[i] + 3, t), .5));
      c.restore();
    });
    return starts;
  }
  function photoScene(t) {
    if (t < T.sat - .35 || t > T.bring + .2) return;
    const r = frameRect(t), a = clamp(ent(t, T.sat - .35, .45)) * (1 - tw(t, T.bring - .3, T.bring + .2));
    SK.layer({ alpha: a }, () => {
      let starts = [];
      frame(r, t, () => { starts = frameContent(t, r); }, 1);
      // the day and hours ride on the exterior; the address is written under it
      const onR1 = 1 - tw(t, T.bed - .6, T.bed - .3);
      if (onR1 > 0) SK.alpha(onR1, () => {
        pill(`${FACTS.dayShort}  ·  ${FACTS.hours}`, r[0] + 30 * U, r[1] + 50 * U, { fill: K.blue, col: K.white, wt: 700, in: { t: T.sat, type: 'rise' } });
        text(`${FACTS.street}, ${FACTS.cityZip}`, 0, r[1] + r[3] + 70 * U, W * .86, { size: 44 * U, font: FB, wt: 500, col: K.ink, p: ent(t, T.sat + .3, 1.2) });
      });
      // room labels
      FACTS.rooms.forEach((m, i) => {
        const on = SK.win(t, starts[i] + .3, (FACTS.rooms[i + 1] ? starts[i + 1] + .2 : T.find - .5), .3, .25);
        if (on > 0) SK.alpha(on, () => pill(m.label, r[0] + 30 * U, r[1] + r[3] - 56 * U, { size: 40 * U, fill: K.white, col: K.ink, wt: 500 }));
      });
      // on the map the frame is the pin's card: the venue and the street under the picture
      const onMap = tw(t, T.welcome, T.welcome + .4);
      if (onMap > 0) SK.alpha(onMap, () => {
        SK.card(r[0], r[1] + r[3] - 8 * U, r[2], 120 * U, { r: 14 * U, fill: K.white, shadow: { blur: 24, y: 10, col: 'rgba(29,58,99,.16)' } });
        text(FACTS.venue, r[0] + r[2] / 2, r[1] + r[3] + 34 * U, r[2] * .9, { size: 34 * U, font: FB, wt: 700, col: K.ink });
        text(FACTS.street, r[0] + r[2] / 2, r[1] + r[3] + 78 * U, r[2] * .9, { size: 30 * U, font: FB, wt: 400, col: K.soft });
      });
    });
  }

  /* beat 3: the facts tick in beside the picture, one by one, for 1 to 4 of them */
  function factsList(t) {
    const L = FACTS.facts, n = L.length; if (!n) return;
    const keys = [T.bed, T.bath, T.sqft, T.feet + .45], a = SK.win(t, T.bed - .2, T.tour - .2, .3, .35);
    if (a <= 0) return;
    const cols = wide ? 1 : Math.min(2, n), rows = Math.ceil(n / cols);
    const bw = wide ? B.w : W * .86, bh = wide ? Math.min(190 * U * rows, H * .72) : H * .34, y0 = wide ? -bh / 2 : H * .02;
    const cw = bw / cols, rh = bh / rows, x0 = wide ? B.x : -bw / 2;
    SK.alpha(a, () => L.forEach((f, i) => {
      const t0 = keys[i] ?? keys[keys.length - 1] + .5 * (i - 3), u = ent(t, t0 - .15, .5); if (u <= 0) return;
      const cx = x0 + (i % cols) * cw + 20 * U, cy = y0 + Math.floor(i / cols) * rh + rh * .42;
      SK.check(cx + 26 * U, cy - 4 * U, 24 * U, inv(t0 - .15, t0 + .4, t), { fill: K.blue });
      SK.alpha(u, () => {
        text(f.value, cx + 72 * U, cy - 14 * U + (1 - u) * 30 * U, cw - 100 * U, { size: Math.min(96 * U, rh * .55), font: FH, wt: 400, col: K.ink, align: 'left' });
        text(f.label.toUpperCase(), cx + 74 * U, cy + Math.min(56 * U, rh * .34), cw - 100 * U, { size: 30 * U, font: FB, wt: 700, col: K.soft, ls: 3 * U, align: 'left' });
      });
    }));
  }

  /* beat 5: a simple drawn street map, the pin dropping on the host's street */
  function map(t) {
    const a = SK.win(t, T.find - .6, T.bring + .4, .5, .6); if (a <= 0) return;
    const v = SK.view, c = SK.ctx(), sy = PIN[1], g = 260 * U;
    SK.alpha(a, () => {
      c.fillStyle = '#e8eef5'; c.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0);
      c.fillStyle = K.green; c.beginPath(); c.ellipse(PIN[0] - W * .32, PIN[1] - H * .42, W * .22, H * .2, .3, 0, SK.TAU); c.fill();
      c.lineCap = 'round'; c.strokeStyle = K.white;
      for (let gx = Math.floor(v.x0 / g) * g; gx < v.x1; gx += g) { c.lineWidth = 18 * U; c.beginPath(); c.moveTo(gx + 40 * U, v.y0); c.lineTo(gx - 40 * U, v.y1); c.stroke(); }
      for (let gy = sy - 3 * g; gy < v.y1; gy += g) { if (Math.abs(gy - sy) < 1) continue; c.lineWidth = 18 * U; c.beginPath(); c.moveTo(v.x0, gy); c.lineTo(v.x1, gy); c.stroke(); }
      c.lineWidth = 34 * U; c.strokeStyle = '#d6dfea'; c.beginPath(); c.moveTo(v.x0, sy - g * 1.6); c.quadraticCurveTo(0, sy - g * 2.4, v.x1, sy - g * 1.2); c.stroke();
      const hl = ent(t, T.find - .2, .9), x0 = v.x0, x1 = lerp(v.x0, v.x1, hl);
      c.lineWidth = 26 * U; c.strokeStyle = K.blue; c.beginPath(); c.moveTo(x0, sy); c.lineTo(x1, sy); c.stroke();
      const lx = PIN[0] - (wide ? 470 : 260) * U;
      SK.alpha(ent(t, T.helms - .2, .5), () => pill(FACTS.mapStreet, lx, sy + 64 * U, { size: 36 * U, fill: K.navy, col: K.white, wt: 700, align: 'center' }));
      // the pin
      const d = SK.pop(t, T.welcome - .1, .55), py = PIN[1] - (1 - E.land(clamp((t - T.welcome + .1) / .5))) * 260 * U;
      if (t > T.welcome - .1) {
        SK.pulse(PIN[0], PIN[1], T.welcome + .35, { col: K.blue, r: 90 * U });
        SK.at(PIN[0], py, 0, U * clamp(d * 1.2), () => {
          c.fillStyle = 'rgba(29,58,99,.25)'; c.beginPath(); c.ellipse(0, 4, 22, 8, 0, 0, SK.TAU); c.fill();
          c.fillStyle = K.navy; c.beginPath(); c.moveTo(0, 0); c.bezierCurveTo(-14, -30, -42, -52, -42, -84); c.arc(0, -84, 42, Math.PI, 0); c.bezierCurveTo(42, -52, 14, -30, 0, 0); c.fill();
          c.fillStyle = K.white; c.beginPath(); c.arc(0, -84, 16, 0, SK.TAU); c.fill();
        });
      }
    });
  }

  /* beat 6: the end card */
  function endCard(t) {
    const a = ent(t, T.bring - .4, .6); if (a <= 0) return;
    const v = SK.view, c = SK.ctx(), mw = W * .84, s = (k) => H * k * (wide ? 1 : .62);
    SK.alpha(a * .94, () => { c.fillStyle = K.white; c.fillRect(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0); });
    const t0 = T.bring - .2, p = (i) => ent(t, t0 + i * .22, .55);
    SK.alpha(p(0), () => SK.image(FACTS.logo, 0, -s(.33), Math.min(W * .4, 520 * U)));
    text(FACTS.kicker.toUpperCase(), 0, -s(.2), mw, { size: 36 * U, font: FB, wt: 700, col: K.blue, ls: 5 * U, p: p(1) });
    text(FACTS.day, 0, -s(.08), mw, { size: 112 * U, font: FH, wt: 300, col: K.ink, p: p(2) });
    text(FACTS.hours, 0, s(.045), mw, { size: 72 * U, font: FB, wt: 500, col: K.blue, p: p(3) });
    c.fillStyle = K.line; const rl = Math.min(mw, 640 * U) * p(4); c.fillRect(-rl / 2, s(.12), rl, 2 * U);
    text(FACTS.venue, 0, s(.19), mw, { size: 44 * U, font: FB, wt: 700, col: K.ink, p: p(4) });
    text(`${FACTS.street}, ${FACTS.cityZip}`, 0, s(.25), mw, { size: 40 * U, font: FB, wt: 400, col: K.soft, p: p(5) });
    if (FACTS.contact) pill(FACTS.contact, 0, s(.35), { size: 40 * U, fill: K.blue, col: K.white, wt: 700, align: 'center', in: { t: t0 + 1.4, type: 'rise' } });
  }

  const camera = SK.breath(SK.camera([[0, [0, 0, 1.02]], [T.sat, [0, 0, 1]], [T.bring - .4, [0, 0, 1.01]], [30, [0, 0, 1.09], E.sine]]), { amp: 8, zoom: .015, period: 10 });
  SK.film({
    duration: 30,
    camera,
    fadeOut: .6,
    draw(t) {
      map(t);
      const out1 = 1 - tw(t, T.sat - .65, T.sat - .2);
      if (out1 > 0) SK.layer({ alpha: out1, y: -60 * U * (1 - out1) }, () => { sign(t, 1); headline(t, 1); });
      factsList(t);
      photoScene(t);
      endCard(t);
    },
  });
})();
