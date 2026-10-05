// For: public-health professionals (CPH holders, health educators, outreach staff) seeing a host's post; calm, credible, brand-led invitation
(function () {
  'use strict';
  const { E, clamp, lerp, inv, mix } = SK;

  // every fact, colour, font and picture of the event, from the webinar's own page and its registration page
  const FACTS = SK.DATA.content;

  SK.setStyle('clean');
  const COL = { ...FACTS.colors, navyDk: mix(FACTS.colors.navy, '#000000', .38), greenLt: mix(FACTS.colors.green, '#ffffff', .5), soft: mix('#ffffff', FACTS.colors.navy, .22) };
  SK.setGround('night', { paper: COL.navy, text: COL.white, textSoft: COL.soft, accent: COL.green, accentText: COL.greenLt });
  SK.KIT.font = FACTS.fonts.body;
  const W = SK.W, H = SK.H, u = Math.min(W, H) / 1080, cw = W * .86, K = SK.KIT;
  const HF = (size, o = {}) => ({ font: FACTS.fonts.head, wt: 700, size, ...o });
  const BF = (size, o = {}) => ({ font: FACTS.fonts.body, wt: 600, size, ...o });

  const T = SK.cues({
    live: [0, 'live'], series: [0, 'Webinar'], host: [0, 'National'], title: [1, null],
    sp: [2, null], name: [2, 'Olivia'], org: [2, 'Epilepsy'], learn: [3, null], l0: [3, 'signs'], l1: [3, 'what'], l2: [3, 'how'],
    when: [4, null], date: [4, 'Wednesday'], time: [4, 'three'], length: [4, 'One'], free: [4, 'free'], end: [5, null], save: [5, 'Save'],
  });
  const learnAt = [T.l0, T.l1, T.l2];
  const rise = (t, t0, d = .5) => [E.out(clamp((t - t0) / d)), (1 - E.out(clamp((t - t0) / d))) * 36 * u];
  // a page of content: in over .45 s from t0, out (rising away) over .35 s up to t1
  function page(t, t0, t1, fn) {
    const a = SK.win(t, t0, t1, .45, .35); if (a <= 0) return;
    const dy = (1 - E.out(inv(t0, t0 + .5, t))) * 50 * u - E.in(inv(t1 - .35, t1, t)) * 50 * u;
    SK.alpha(a, () => SK.at(0, dy, 0, 1, fn));
  }
  // the longest text set as large as its box allows, wrapped into balanced lines
  function fitLines(text, maxW, maxH, f, maxSize, lh = 1.12) {
    let size = maxSize, lines = [text];
    for (; size > 16 * u; size *= .95) {
      lines = K.wrap(text, maxW, { ...f, size });
      if (lines.length * size * lh <= maxH && lines.every((l) => SK.measure(l, { ...f, size }) <= maxW)) break;
    }
    let w = maxW; const n = lines.length;
    while (n > 1 && K.wrap(text, w * .96, { ...f, size }).length === n) w *= .96;
    return { size, lines: K.wrap(text, w, { ...f, size }), lh: size * lh };
  }

  function backdrop(t) {
    SK.sky(COL.navyDk, COL.navy, { mid: mix(COL.navy, COL.navyDk, .4) });
    const R = SK.mulberry(19), M = Math.max(W, H);
    for (let i = 0; i < 8; i++) {
      const cx = (R() - .5) * W * 1.2, cy = (R() - .5) * H * 1.2, r = (.18 + R() * .3) * M, a0 = R() * SK.TAU, sp = (R() - .5) * .05, col = i % 3 ? '#ffffff' : COL.green;
      const pts = [0, 1, 2].map((k) => { const a = a0 + t * sp + k * SK.TAU / 3 + (R() - .5) * .7; return [cx + Math.cos(a) * r + Math.sin(t * .15 + i) * 30 * u, cy + Math.sin(a) * r]; });
      SK.wash(pts, col, { alpha: i % 3 ? .035 : .08, tex: false, dx: 0, dy: 0 });
    }
    K.box(-W / 2 - 20, H / 2 - 10 * u, 20 + W * clamp(t / 29.5), 30 * u, { r: 0, fill: COL.green }); // the film's progress, along the foot
  }
  const logo = (x, y, r) => { K.disc(x, y, r, { fill: '#ffffff' }); SK.image(FACTS.logo, x, y, r * 2); };
  const tagW = (s) => SK.measure(FACTS.tag, HF(s)) + FACTS.tag.length * s * .12 + s * 2.6;
  function tag(x, y, s, t) {
    const w = tagW(s), h = s * 1.9, dx = x - w / 2 + s * .95, ph = (t * .8) % 1;
    K.box(x - w / 2, y - h / 2, w, h, { r: h / 2, fill: COL.green });
    K.disc(dx, y, s * .22 * (1 + ph * 1.6), { fill: '#ffffff', alpha: .5 * (1 - ph) });
    K.disc(dx, y, s * .22, { fill: '#ffffff' });
    SK.label(FACTS.tag, dx + s * .45, y + s * .04, { ...HF(s), ls: s * .12, col: '#ffffff', align: 'left' });
  }
  // where the logo and the tag sit: the opening card, the header bar, the end card
  const headY = -H / 2 + 100 * u;
  function header() {
    const lr = 62 * u, ts = 32 * u, ds = 44 * u, g = 30 * u, dw = SK.measure(FACTS.dateShort, HF(ds, { wt: 400 })), tot = 2 * lr + g + tagW(ts) + g + dw, x0 = -tot / 2;
    return { logo: [x0 + lr, headY, lr], tag: [x0 + 2 * lr + g + tagW(ts) / 2, headY, ts], date: [x0 + 2 * lr + 2 * g + tagW(ts), headY, ds] };
  }
  const HERO = { logo: [0, -250 * u, 150 * u], tag: [0, -40 * u, 40 * u] };
  const ENDY = -300 * u;

  function chrome(t) {
    const hd = header(), k1 = E.inOut(inv(T.title - .6, T.title + .05, t)), kL = E.inOut(inv(T.title - .95, T.title - .3, t)), k2 = E.inOut(inv(T.end - .15, T.end + .5, t));
    const mixP = (a, b, k) => a.map((v, i) => lerp(v, b[i], k));
    const L = mixP(mixP(HERO.logo, hd.logo, kL), [0, ENDY, 120 * u], k2);
    const la = clamp(.6 + .4 * E.out(inv(0, .7, t)));
    SK.alpha(la, () => logo(L[0], L[1], L[2] * (.8 + .2 * E.back(inv(0, .7, t)))));
    const tp = E.back(inv(T.live - .2, T.live + .25, t)), Tg = mixP(HERO.tag, hd.tag, k1);
    if (tp > 0) SK.alpha(1 - inv(T.end - .2, T.end + .05, t), () => SK.alpha(clamp(tp * 3), () => SK.at(Tg[0], Tg[1], 0, tp, () => tag(0, 0, Tg[2], t))));
    SK.label(FACTS.dateShort, hd.date[0], hd.date[1] + 2 * u, { ...HF(hd.date[2], { wt: 400 }), ls: 2 * u, col: COL.greenLt, align: 'left', alpha: k1 * (1 - inv(T.end - .25, T.end, t)) });
    // the opening card's words, gone as the header forms
    SK.alpha(1 - k1, () => {
      let [a, dy] = rise(t, T.series - .1);
      SK.label(FACTS.series, 0, 90 * u + dy, { ...HF(118 * u), maxW: cw, alpha: a });
      K.line([[-170 * u, 172 * u], [170 * u, 172 * u]], { col: COL.green, w: 6 * u, p: E.inOut(inv(T.series + .3, T.series + 1, t)), crisp: true });
      [a, dy] = rise(t, T.series + .6);
      SK.label(FACTS.dateLong.toUpperCase(), 0, 236 * u + dy, { ...HF(50 * u, { wt: 400 }), ls: 3 * u, maxW: cw, col: COL.greenLt, alpha: a });
      [a, dy] = rise(t, T.host - .1);
      SK.label(FACTS.host, 0, 318 * u + dy, { ...BF(36 * u), maxW: cw, col: COL.soft, alpha: a });
    });
  }

  const top = headY + 80 * u, bot = H / 2 - 70 * u, mid = (top + bot) / 2;
  function titlePage(t) {
    const f = HF(1), L = fitLines(FACTS.title, cw, (bot - top) * .78, f, 150 * u), words = SK.line(1).words;
    let wi = 0; const y0 = mid - L.lines.length * L.lh / 2;
    L.lines.forEach((ln, i) => {
      const t0 = words[wi] ? words[wi].s - .1 : T.title + i * .7; wi += ln.split(/\s+/).length;
      const [a, dy] = rise(t, t0, .55);
      SK.label(ln, 0, y0 + (i + .5) * L.lh + dy, { ...f, size: L.size, alpha: a });
    });
    const lw = Math.min(cw * .3, 260 * u);
    K.line([[-lw / 2, y0 + L.lines.length * L.lh + 30 * u], [lw / 2, y0 + L.lines.length * L.lh + 30 * u]], { col: COL.green, w: 7 * u, p: E.inOut(inv(T.title + 2.4, T.title + 3.2, t)), crisp: true });
  }

  function speakerPage(t) {
    const sp = FACTS.speakers.slice(0, 3), n = sp.length, cols = W >= H ? n : 1, rows = Math.ceil(n / cols);
    const bw = cw / cols - 40 * u, ph = sp.some((s) => s.photo) ? 260 * u : 0, ns = (n === 1 ? 136 : 84) * u;
    const blockH = ph + (ph ? 40 * u : 0) + ns * 1.2 + 190 * u, totH = 70 * u + rows * blockH + (rows - 1) * 50 * u;
    let [a, dy] = rise(t, T.sp - .1);
    SK.label(FACTS.words.presented, 0, mid - totH / 2 + 20 * u + dy, { ...HF(34 * u, { wt: 400 }), ls: 6 * u, col: COL.greenLt, alpha: a });
    sp.forEach((s, i) => {
      const cx = cols > 1 ? -cw / 2 + (i % cols + .5) * cw / cols : 0, by = mid - totH / 2 + 70 * u + Math.floor(i / cols) * (blockH + 50 * u);
      const t0 = (i ? T.name + i * .6 : T.name) - .15; let y = by;
      [a, dy] = rise(t, t0);
      if (s.photo) SK.alpha(a, () => { const r = ph / 2; K.disc(cx, y + r + dy, r + 6 * u, { fill: '#ffffff' }); const c = SK.ctx(); c.save(); c.beginPath(); c.arc(cx, y + r + dy, r, 0, SK.TAU); c.clip(); SK.image(s.photo, cx, y + r + dy, ph); c.restore(); });
      if (ph) y += ph + 40 * u;
      const nm = SK.label(s.name, cx, y + ns * .6 + dy, { ...HF(ns), maxW: bw, alpha: a });
      y += ns * 1.2;
      K.line([[cx - 60 * u, y + 10 * u], [cx + 60 * u, y + 10 * u]], { col: COL.green, w: 6 * u, p: E.inOut(inv(t0 + .4, t0 + 1, t)), crisp: true });
      y += 50 * u;
      const sub = [s.creds, s.role].filter(Boolean).join(' · ');
      if (sub) { SK.label(sub, cx, y + dy, { ...BF(40 * u, { wt: 400 }), maxW: bw, col: COL.soft, alpha: a }); y += 66 * u; }
      [a, dy] = rise(t, T.org - .15);
      if (s.org) SK.label(s.org, cx, y + dy, { ...BF(46 * u, { wt: 700 }), maxW: bw, col: COL.greenLt, alpha: a });
      return nm;
    });
  }

  function learnPage(t) {
    const items = FACTS.learn.slice(0, 4), lw = Math.min(cw, 1300 * u), size = (items.length > 3 ? 50 : 60) * u, tw = lw - 100 * u, f = BF(size);
    const hs = items.map((it) => K.wrap(it, tw, f).length * size * 1.3), totH = 90 * u + hs.reduce((s, h) => s + h, 0) + (items.length - 1) * 36 * u;
    let y = mid - totH / 2, [a, dy] = rise(t, T.learn - .1);
    SK.label(FACTS.words.learn, -lw / 2, y + 20 * u + dy, { ...HF(40 * u, { wt: 400 }), ls: 6 * u, col: COL.greenLt, align: 'left', alpha: a });
    y += 90 * u;
    items.forEach((it, i) => {
      const t0 = Math.min((learnAt[i] ?? T.learn + .8 * i) - .2, i ? 99 : T.learn + .2);
      [a, dy] = rise(t, t0);
      SK.check(-lw / 2 + 30 * u, y + size * .65, 28 * u, clamp((t - t0 - .1) / .6), { fill: COL.green });
      SK.para(it, -lw / 2 + 100 * u, y + dy, { ...f, w: tw, col: '#ffffff', p: 1, alpha: a });
      y += hs[i] + 36 * u;
    });
  }

  function detailsPage(t) {
    const rowsH = 400 * u, y0 = mid - rowsH / 2;
    const iconRow = (icon, str, alt, y, s, t0) => {
      const [a, dy] = rise(t, t0), f = HF(s), w0 = SK.measure(str, f), fa = HF(s * .62, { wt: 400 }), wa = alt ? SK.measure(alt, fa) + 30 * u : 0;
      const k = Math.min(1, (cw - 110 * u) / (w0 + wa)), tot = 110 * u + (w0 + wa) * k, x0 = -tot / 2;
      SK.alpha(a, () => SK.icon(icon, x0 + 40 * u, y + dy, 40 * u, { col: COL.greenLt, w: 5 * u }));
      SK.label(str, x0 + 110 * u, y + dy, { ...f, size: s * k, align: 'left', alpha: a });
      if (alt) SK.label(alt, x0 + 110 * u + (w0 + 30 * u) * k, y + dy + s * k * .1, { ...fa, size: s * .62 * k, col: COL.soft, align: 'left', alpha: a });
    };
    iconRow('calendar', FACTS.dateLong, null, y0 + 60 * u, 112 * u, Math.min(T.date - .15, T.when));
    if (FACTS.time) iconRow('clock', FACTS.time, FACTS.timeAlt, y0 + 210 * u, 96 * u, T.time - .15);
    const chips = [[FACTS.length, T.length, null], [FACTS.price, T.free, COL.green]].filter((c) => c[0]);
    const cf = HF(56 * u), cws = chips.map((c) => SK.measure(c[0], cf) + 70 * u), gap = 30 * u, cwT = cws.reduce((s, w) => s + w, 0) + gap * (chips.length - 1);
    let x = -cwT / 2;
    chips.forEach((c, i) => {
      SK.pill(c[0], x + cws[i] / 2, y0 + 350 * u, { ...cf, padX: 35 * u, fill: c[2] ?? 'rgba(255,255,255,0.08)', stroke: c[2] ? null : '#ffffff', strokeW: 3 * u, col: '#ffffff', in: { t: c[1] - .15, type: 'pop' } });
      x += cws[i] + gap;
    });
  }

  function endPage(t) {
    const L = fitLines(FACTS.title, Math.min(cw, 1400 * u), 150 * u, HF(1), 66 * u);
    let y = ENDY + 120 * u + 60 * u;
    L.lines.forEach((ln, i) => { const [a, dy] = rise(t, T.end + .1 + i * .12); SK.label(ln, 0, y + (i + .5) * L.lh + dy, { ...HF(L.size), alpha: a }); });
    y += L.lines.length * L.lh + 90 * u;
    const press = 1 + .06 * SK.bump(t, T.save + .9, .2);
    SK.at(0, y, 0, press, () => SK.pill(FACTS.cta, 0, 0, { ...HF(64 * u), ls: 2 * u, padX: 70 * u, padY: 26 * u, fill: COL.green, col: '#ffffff', in: { t: T.save - .1, type: 'grow' } }));
    y += 120 * u;
    const [a, dy] = rise(t, T.save + .35);
    SK.label(FACTS.link, 0, y + dy, { ...BF(34 * u), maxW: cw, col: COL.soft, alpha: a });
  }

  SK.film({
    duration: 30,
    camera: SK.camera([[0, [0, 0, 1]]]),
    draw(t) {
      backdrop(t);
      page(t, T.title - .35, T.sp - .1, () => titlePage(t));
      page(t, T.sp - .1, T.learn - .1, () => speakerPage(t));
      page(t, T.learn - .1, T.when - .1, () => learnPage(t));
      page(t, T.when - .1, T.end - .1, () => detailsPage(t));
      page(t, T.end - .1, 99, () => endPage(t));
      chrome(t);
    },
  });
})();
