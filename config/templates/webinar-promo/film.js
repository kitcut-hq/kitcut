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
  // text set as large as its box allows, in balanced lines: the breaks that even the line lengths,
  // never a lone short word, and no line left hanging on a small word when another split is as good
  const SMALL = /^(a|an|and|the|of|for|to|in|on|at|by|with|from|or|&|–|—|-)$/i;
  function setType(text, maxW, maxH, f, maxSize, lh = 1.12, maxLines = 5, prefer = 1.04) {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean), n = words.length, m = (s) => SK.measure(s, { ...f, size: 100 });
    if (!n) return { size: maxSize, lines: [], lh: maxSize * lh };
    const wid = (i, j) => m(words.slice(i, j).join(' '));
    let best = null;
    for (let k = 1; k <= Math.min(maxLines, n); k++) {
      // dp[c][j]: the least "widest line" when the first j words are set in c lines
      const dp = [...Array(k + 1)].map(() => Array(n + 1).fill(Infinity)), cut = [...Array(k + 1)].map(() => Array(n + 1).fill(0));
      dp[0][0] = 0;
      for (let c = 1; c <= k; c++) for (let j = c; j <= n; j++) for (let i = c - 1; i < j; i++) {
        if (dp[c - 1][i] === Infinity) continue;
        let w = wid(i, j);
        if (j < n && SMALL.test(words[j - 1])) w *= 1.18;
        if (k > 1 && j - i === 1 && words[i].length < 6) w *= 3;
        if (i > 0 && SMALL.test(words[i])) w *= .95;
        const v = Math.max(dp[c - 1][i], w);
        if (v < dp[c][j]) { dp[c][j] = v; cut[c][j] = i; }
      }
      const lines = []; for (let c = k, j = n; c > 0; c--) { const i = cut[c][j]; lines.unshift(words.slice(i, j).join(' ')); j = i; }
      const widest = Math.max(...lines.map(m)), size = Math.min(maxSize, maxW / widest * 100, maxH / (k * lh));
      if (!best || size > best.size * prefer) best = { size, lines, lh: size * lh };
    }
    return best;
  }
  const initials = (name) => { const w = String(name || '').replace(/\(.*?\)/g, '').split(/\s+/).filter((x) => /^\p{L}/u.test(x) && !/\.$/.test(x)); return ((w[0] || '')[0] || '') + (w.length > 1 ? w[w.length - 1][0] : ''); };

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
  const WIDE = W / H > 1.3, TALL = H / W > 1.3;
  const headY = -H / 2 + (TALL ? 190 : 96) * u, top = headY + 96 * u, bot = H / 2 - (TALL ? 230 : 64) * u, mid = (top + bot) / 2, zoneH = bot - top;
  function header() {
    const lr0 = 56 * u, ts0 = 32 * u, ds0 = 42 * u, g0 = 28 * u, tot0 = 2 * lr0 + g0 + tagW(ts0) + g0 + SK.measure(FACTS.dateShort, HF(ds0, { wt: 400 })) + FACTS.dateShort.length * 2 * u;
    const k = Math.min(1, cw / tot0), lr = lr0 * k, ts = ts0 * k, ds = ds0 * k, g = g0 * k, x0 = -tot0 * k / 2;
    return { logo: [x0 + lr, headY, lr], tag: [x0 + 2 * lr + g + tagW(ts) / 2, headY, ts], date: [x0 + 2 * lr + 2 * g + tagW(ts), headY, ds] };
  }
  const BIG = FACTS.series || FACTS.host, heroY = 25 * u;
  const HERO = { logo: [0, heroY - 250 * u, 150 * u], tag: [0, heroY - 40 * u, 40 * u] };
  // the end card, measured once so it sits in the middle of the frame whatever it holds
  const lazy = (fn) => { let v; return () => v ?? (v = fn()); }; // type is measured once there is a canvas to measure on
  const END = lazy(() => {
    const T2 = setType(FACTS.title, Math.min(cw, 1400 * u), 250 * u, HF(1), (WIDE ? 78 : 70) * u, 1.14, 3), when = [FACTS.dateLong, FACTS.time].filter(Boolean).join('  ·  ');
    const lr = 112 * u, hT = T2.lines.length * T2.lh, hW = when ? 96 * u : 0, hB = 130 * u, hL = FACTS.link ? 86 * u : 0;
    const tot = 2 * lr + 54 * u + hT + hW + 44 * u + hB + hL, y0 = (TALL ? -60 * u : 0) - tot / 2;
    return { T2, when, lr, logoY: y0 + lr, titleY: y0 + 2 * lr + 54 * u, whenY: y0 + 2 * lr + 54 * u + hT + hW * .62, btnY: y0 + 2 * lr + 54 * u + hT + hW + 44 * u + hB / 2, linkY: y0 + tot - 22 * u };
  });

  function chrome(t) {
    const hd = header(), k1 = E.inOut(inv(T.title - .6, T.title + .05, t)), kL = E.inOut(inv(T.title - .95, T.title - .3, t)), k2 = E.inOut(inv(T.end - .15, T.end + .5, t));
    const mixP = (a, b, k) => a.map((v, i) => lerp(v, b[i], k));
    const L = mixP(mixP(HERO.logo, hd.logo, kL), [0, END().logoY, END().lr], k2);
    const la = clamp(.6 + .4 * E.out(inv(0, .7, t)));
    SK.alpha(la, () => logo(L[0], L[1], L[2] * (.8 + .2 * E.back(inv(0, .7, t)))));
    const tp = E.back(inv(T.live - .2, T.live + .25, t)), Tg = mixP(HERO.tag, hd.tag, k1);
    if (tp > 0) SK.alpha(1 - inv(T.end - .2, T.end + .05, t), () => SK.alpha(clamp(tp * 3), () => SK.at(Tg[0], Tg[1], 0, tp, () => tag(0, 0, Tg[2], t))));
    SK.label(FACTS.dateShort, hd.date[0], hd.date[1] + 2 * u, { ...HF(hd.date[2], { wt: 400 }), ls: 2 * u, col: COL.greenLt, align: 'left', alpha: k1 * (1 - inv(T.end - .25, T.end, t)) });
    // the opening card's words, gone as the header forms
    SK.alpha(1 - k1, () => {
      let [a, dy] = rise(t, T.series - .1);
      const B = setType(BIG, cw, 250 * u, HF(1), 124 * u, 1.08, 2);
      B.lines.forEach((ln, i) => SK.label(ln, 0, heroY + 96 * u + i * B.lh + dy, { ...HF(B.size), alpha: a }));
      const ry = heroY + 96 * u + (B.lines.length - 1) * B.lh + 84 * u;
      K.line([[-170 * u, ry], [170 * u, ry]], { col: COL.green, w: 6 * u, p: E.inOut(inv(T.series + .3, T.series + 1, t)), crisp: true });
      [a, dy] = rise(t, T.series + .6);
      SK.label(FACTS.dateLong.toUpperCase(), 0, ry + 66 * u + dy, { ...HF(52 * u, { wt: 400 }), ls: 3 * u, maxW: cw, col: COL.greenLt, alpha: a });
      [a, dy] = rise(t, T.host - .1);
      if (FACTS.series && FACTS.host) SK.label(FACTS.host, 0, ry + 150 * u + dy, { ...BF(38 * u), maxW: cw, col: COL.soft, alpha: a });
    });
  }

  function titlePage(t) { // the whole title stands at once, quiet; each line lights as it is said
    const f = HF(1), L = setType(FACTS.title, cw, zoneH * .8, f, (WIDE ? 210 : TALL ? 190 : 170) * u, 1.12, TALL ? 5 : 4), said = SK.line(1).words || [];
    const total = L.lines.reduce((s, l) => s + l.split(/\s+/).length, 0), span = Math.max(1, T.sp - T.title - 1.2);
    let wi = 0; const y0 = mid - L.lines.length * L.lh / 2 - 20 * u;
    L.lines.forEach((ln, i) => {
      const t0 = said.length === total ? said[wi].s - .12 : T.title + .1 + span * wi / total; wi += ln.split(/\s+/).length;
      const [a, dy] = rise(t, T.title - .1 + i * .08, .55), lit = E.out(clamp((t - t0) / .4));
      SK.label(ln, 0, y0 + (i + .5) * L.lh + dy * (1 + i * .4), { ...f, size: L.size, alpha: a * lerp(.3, 1, lit) });
    });
    const lw = Math.min(cw * .3, 280 * u), ry = y0 + L.lines.length * L.lh + 34 * u;
    K.line([[-lw / 2, ry], [lw / 2, ry]], { col: COL.green, w: 7 * u, p: E.inOut(inv(T.sp - 1.9, T.sp - 1.1, t)), crisp: true });
  }

  // a speaker's face: their photo in a ring, or their initials on the host's colour
  function face(s, x, y, r, a, p) {
    SK.alpha(a, () => {
      const c = SK.ctx();
      K.disc(x, y, r + 7 * u, { fill: '#ffffff' });
      if (s.photo && SK.IMG[s.photo]) {
        const im = SK.IMG[s.photo], k = Math.max(1, im.height / im.width);
        c.save(); c.beginPath(); c.arc(x, y, r, 0, SK.TAU); c.clip(); SK.image(s.photo, x, y + (k - 1) * r * .35, 2 * r * Math.max(1, im.width / im.height)); c.restore();
      } else {
        K.disc(x, y, r, { fill: COL.green }); K.disc(x, y, r * .86, { fill: mix(COL.green, COL.navyDk, .22) });
        SK.label(initials(s.name).toUpperCase(), x, y + r * .04, { ...HF(r * .82), ls: r * .04, col: '#ffffff' });
      }
      c.save(); c.strokeStyle = COL.greenLt; c.lineWidth = 6 * u; c.lineCap = 'round'; c.beginPath(); c.arc(x, y, r + 22 * u, -Math.PI / 2, -Math.PI / 2 + SK.TAU * clamp(p)); c.stroke(); c.restore();
    });
  }
  function speakerPage(t) {
    const sp = FACTS.speakers.slice(0, 3), n = sp.length; if (!n) return;
    const kick = (x, y, align) => { const [a, dy] = rise(t, T.sp - .1); SK.label(FACTS.words.presented, x, y + dy, { ...HF(36 * u, { wt: 400 }), ls: 6 * u, col: COL.greenLt, align, alpha: a }); };
    const tIn = (i) => (i ? T.name + i * .6 : T.name) - .15, tOrg = (i) => (i ? tIn(i) + .45 : T.org - .15);
    const sub = (s) => [s.creds, s.role].filter(Boolean).join(' · ');
    const sizes = (ns) => Math.max(34 * u, ns * .34);
    const nameSet = (s, ns, maxW) => setType(s.name, maxW, ns * 2.3, HF(1), ns, 1.1, 2, 1.25);
    // the words of one speaker, from y down: the name, a rule, credentials and role, the organisation
    function words(s, i, x, y, maxW, ns, align) {
      let [a, dy] = rise(t, tIn(i));
      const N = nameSet(s, ns, maxW), x0 = align === 'left' ? x : x - 60 * u, ss = sizes(ns);
      N.lines.forEach((ln, j) => SK.label(ln, x, y + (j + .5) * N.lh + dy, { ...HF(N.size), align, alpha: a }));
      y += N.lines.length * N.lh + ns * .16;
      K.line([[x0, y], [x0 + 120 * u, y]], { col: COL.green, w: 6 * u, p: E.inOut(inv(tIn(i) + .4, tIn(i) + 1, t)), crisp: true });
      y += ns * .2 + 30 * u;
      if (sub(s)) { SK.label(sub(s), x, y + dy, { ...BF(ss, { wt: 400 }), maxW, col: COL.soft, align, alpha: a }); y += ss * 1.55; }
      [a, dy] = rise(t, tOrg(i));
      if (s.org) SK.label(s.org, x, y + dy, { ...BF(ss * 1.12, { wt: 700 }), maxW, col: COL.greenLt, align, alpha: a });
    }
    const hgt = (s, ns, maxW) => { const N = nameSet(s, ns, maxW), ss = sizes(ns); return N.lines.length * N.lh + ns * .36 + 30 * u + (sub(s) ? ss * 1.55 : 0) + (s.org ? ss * 1.3 : 0); };
    const ring = (i) => E.inOut(inv(tIn(i) + .1, tIn(i) + 1.1, t));
    if (n === 1 && WIDE) { // one speaker, wide: the face beside the words
      const s = sp[0], r = 200 * u, g = 90 * u, ns = 132 * u, maxW = cw - 2 * r - g - 40 * u, N = nameSet(s, ns, maxW), ss = sizes(ns);
      const tw = Math.max(...N.lines.map((l) => SK.measure(l, HF(N.size))), Math.min(maxW, SK.measure(sub(s), BF(ss, { wt: 400 }))), Math.min(maxW, SK.measure(s.org || '', BF(ss * 1.12, { wt: 700 }))));
      const x0 = -(2 * r + g + tw) / 2, h = hgt(s, ns, maxW) + 70 * u, y0 = mid - h / 2;
      face(s, x0 + r, mid, r, rise(t, tIn(0))[0], ring(0));
      kick(x0 + 2 * r + g, y0 + 18 * u, 'left');
      words(s, 0, x0 + 2 * r + g, y0 + 70 * u, maxW, ns, 'left');
    } else if (WIDE || n === 1) { // columns (or one speaker in a narrow frame): the face over the words
      const colW = cw / n, maxW = colW - 50 * u, r = (n === 1 ? (TALL ? 210 : 150) : n === 2 ? 150 : 128) * u, ns = (n === 1 ? (TALL ? 112 : 96) : n === 2 ? 84 : 68) * u;
      const h = 70 * u + 2 * r + 60 * u + Math.max(...sp.map((s) => hgt(s, ns, maxW))), y0 = mid - h / 2;
      kick(0, y0 + 18 * u, 'center');
      sp.forEach((s, i) => { const cx = -cw / 2 + (i + .5) * colW; face(s, cx, y0 + 80 * u + r, r, rise(t, tIn(i))[0], ring(i)); words(s, i, cx, y0 + 80 * u + 2 * r + 56 * u, maxW, ns, 'center'); });
    } else { // several speakers in a narrow frame: rows, the face beside the words
      const r = (TALL ? 120 : 92) * u, g = 44 * u, ns = (TALL ? 70 : 58) * u, maxW = cw - 2 * r - g, gap = (TALL ? 70 : 36) * u;
      const hs = sp.map((s) => Math.max(2 * r + 40 * u, hgt(s, ns, maxW))), h = 70 * u + hs.reduce((a, b) => a + b, 0) + gap * (n - 1);
      let y = mid - h / 2; kick(-cw / 2, y + 18 * u, 'left'); y += 70 * u;
      sp.forEach((s, i) => { face(s, -cw / 2 + r, y + hs[i] / 2, r, rise(t, tIn(i))[0], ring(i)); words(s, i, -cw / 2 + 2 * r + g, y + (hs[i] - hgt(s, ns, maxW)) / 2, maxW, ns, 'left'); y += hs[i] + gap; });
    }
  }

  // a paragraph's lines, as many as it needs at its size, evened out (no last line of one word)
  const even = (text, maxW, f) => { const n = K.wrap(text, maxW, f).length, r = n > 1 ? setType(text, maxW, 1e9, f, f.size, 1, n, 1.0001) : null; return r && r.size > f.size * .999 ? r.lines : K.wrap(text, maxW, f); };
  function learnPage(t) { // the heading beside (or over) the points, each on its own card
    const items = FACTS.learn.slice(0, 4), n = items.length; if (!n) return;
    const side = WIDE, hw = side ? cw * .27 : cw, lx = side ? -cw / 2 + cw * .33 : -cw / 2, lw = side ? cw * .67 : cw, tw = lw - 168 * u, gap = 24 * u, pad = 30 * u;
    const HD = setType(FACTS.words.learn, hw, side ? 330 * u : 90 * u, HF(1), (side ? 132 : 64) * u, 1.08, side ? 2 : 1), headH = side ? 0 : HD.lh + 44 * u;
    let size = (TALL ? 60 : WIDE ? 60 : 46) * u, hs, ls;
    for (; size > 26 * u; size *= .95) { ls = items.map((it) => even(it, tw, BF(size))); hs = ls.map((l) => l.length * size * 1.28 + 2 * pad); if (headH + hs.reduce((s, h) => s + h, 0) + gap * (n - 1) <= zoneH * .96) break; }
    const listH = hs.reduce((s, h) => s + h, 0) + gap * (n - 1), y0 = mid - (headH + listH) / 2;
    let [a, dy] = rise(t, T.learn - .1);
    if (side) {
      const hy = mid - HD.lines.length * HD.lh / 2 - 20 * u, ry = hy + HD.lines.length * HD.lh + 30 * u;
      HD.lines.forEach((ln, i) => SK.label(ln, -cw / 2, hy + (i + .5) * HD.lh + dy, { ...HF(HD.size), col: '#ffffff', align: 'left', alpha: a }));
      K.line([[-cw / 2, ry], [-cw / 2 + 150 * u, ry]], { col: COL.green, w: 8 * u, p: E.inOut(inv(T.learn + .2, T.learn + .9, t)), crisp: true });
    } else SK.label(HD.lines.join(' '), -cw / 2, y0 + HD.lh / 2 + dy, { ...HF(HD.size, { wt: 400 }), ls: 6 * u, col: COL.greenLt, align: 'left', alpha: a });
    let y = y0 + headH;
    items.forEach((it, i) => {
      const t0 = Math.min((learnAt[i] ?? T.learn + .8 * i) - .2, i ? 99 : T.learn + .2), yy = y;
      [a, dy] = rise(t, t0);
      const d = dy;
      SK.alpha(a, () => { K.box(lx, yy + d, lw, hs[i], { r: 22 * u, fill: 'rgba(255,255,255,0.07)' }); K.box(lx, yy + d + 18 * u, 7 * u, hs[i] - 36 * u, { r: 3 * u, fill: COL.green }); });
      SK.check(lx + 78 * u, yy + hs[i] / 2 + d, 30 * u, clamp((t - t0 - .1) / .6), { fill: COL.green });
      ls[i].forEach((ln, j) => SK.label(ln, lx + 136 * u, yy + pad + (j + .5) * size * 1.28 + d, { ...BF(size), col: '#ffffff', align: 'left', alpha: a }));
      y += hs[i] + gap;
    });
  }

  function detailsPage(t) { // one centred column of facts: the date, the time, how long and what it costs
    const D = setType(FACTS.dateLong, cw, 330 * u, HF(1), (WIDE ? 150 : 124) * u, 1.1, 2), ts = (WIDE ? 104 : 92) * u, as = ts * .56;
    const chips = [[FACTS.length, T.length, null], [FACTS.price, T.free, COL.green]].filter((c) => c[0]);
    const hD = D.lines.length * D.lh, hT = FACTS.time ? ts * 1.5 : 0, hC = chips.length ? 150 * u : 0, tot = 120 * u + hD + 50 * u + hT + hC;
    let y = mid - tot / 2, [a, dy] = rise(t, Math.min(T.date - .15, T.when));
    const yi = y + 44 * u + dy;
    SK.alpha(a, () => { K.disc(0, yi, 46 * u, { fill: 'rgba(255,255,255,0.10)' }); SK.icon('calendar', 0, yi, 24 * u, { col: COL.greenLt, w: 4.5 * u }); });
    y += 120 * u;
    D.lines.forEach((ln, i) => SK.label(ln, 0, y + (i + .5) * D.lh + dy, { ...HF(D.size), alpha: a }));
    y += hD + 12 * u;
    K.line([[-110 * u, y], [110 * u, y]], { col: COL.green, w: 7 * u, p: E.inOut(inv(T.date + .3, T.date + 1, t)), crisp: true });
    y += 38 * u;
    if (FACTS.time) {
      [a, dy] = rise(t, T.time - .15);
      const f = HF(ts), fa = HF(as, { wt: 400 }), g = 34 * u, w0 = SK.measure(FACTS.time, f), wa = FACTS.timeAlt ? g * 2 + SK.measure(FACTS.timeAlt, fa) : 0, iw = ts * .78;
      const k = Math.min(1, cw / (iw + w0 + wa)), x0 = -(iw + w0 + wa) * k / 2, yy = y + ts * .7 + dy;
      SK.alpha(a, () => SK.icon('clock', x0 + ts * .26 * k, yy, ts * .26 * k, { col: COL.greenLt, w: 5 * u }));
      SK.label(FACTS.time, x0 + iw * k, yy, { ...f, size: ts * k, align: 'left', alpha: a });
      if (FACTS.timeAlt) {
        SK.alpha(a, () => K.box(x0 + (iw + w0 + g) * k - 2 * u, yy - ts * k * .3, 4 * u, ts * k * .6, { r: 2 * u, fill: COL.green }));
        SK.label(FACTS.timeAlt, x0 + (iw + w0 + g * 2) * k, yy + ts * k * .05, { ...fa, size: as * k, col: COL.soft, align: 'left', alpha: a });
      }
      y += hT;
    }
    const cf = HF(56 * u), cws = chips.map((c) => SK.measure(c[0], cf) + 80 * u), gap = 30 * u, cwT = cws.reduce((s, w) => s + w, 0) + gap * (chips.length - 1), kc = Math.min(1, cw / Math.max(1, cwT));
    let x = -cwT * kc / 2;
    chips.forEach((c, i) => {
      SK.pill(c[0], x + cws[i] * kc / 2, y + 86 * u, { ...cf, size: 56 * u * kc, padX: 40 * u * kc, fill: c[2] ?? 'rgba(255,255,255,0.08)', stroke: c[2] ? null : '#ffffff', strokeW: 3 * u, col: '#ffffff', in: { t: c[1] - .15, type: 'pop' } });
      x += (cws[i] + gap) * kc;
    });
  }

  function endPage(t) {
    const N = END(), L = N.T2;
    L.lines.forEach((ln, i) => { const [a, dy] = rise(t, T.end + .1 + i * .12); SK.label(ln, 0, N.titleY + (i + .5) * L.lh + dy, { ...HF(L.size), alpha: a }); });
    let [a, dy] = rise(t, T.end + .45);
    if (N.when) SK.label(N.when, 0, N.whenY + dy, { ...HF(46 * u, { wt: 400 }), ls: 2 * u, maxW: cw, col: COL.greenLt, alpha: a });
    const press = 1 + .06 * SK.bump(t, T.save + .9, .2);
    SK.at(0, N.btnY, 0, press, () => SK.pill(FACTS.cta, 0, 0, { ...HF(66 * u), ls: 2 * u, padX: 76 * u, padY: 28 * u, fill: COL.green, col: '#ffffff', in: { t: T.save - .1, type: 'grow' } }));
    [a, dy] = rise(t, T.save + .35);
    if (FACTS.link) SK.label(FACTS.link, 0, N.linkY + dy, { ...BF(38 * u), maxW: cw, col: '#ffffff', alpha: a * .92 });
  }

  const HAS_LEARN = FACTS.learn.length > 0, spEnd = HAS_LEARN ? T.learn - .1 : T.when - .1;
  SK.film({
    duration: 30,
    camera: SK.camera([[0, [0, 0, 1]]]),
    draw(t) {
      backdrop(t);
      page(t, T.title - .35, T.sp - .1, () => titlePage(t));
      page(t, T.sp - .1, spEnd, () => speakerPage(t));
      if (HAS_LEARN) page(t, T.learn - .1, T.when - .1, () => learnPage(t));
      page(t, T.when - .1, T.end - .1, () => detailsPage(t));
      page(t, T.end - .1, 99, () => endPage(t));
      chrome(t);
    },
  });
})();
