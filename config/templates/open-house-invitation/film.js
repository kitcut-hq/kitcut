// For: home shoppers who follow a builder or a local agent on social; bright, calm, upscale and inviting
(function () {
  'use strict';
  const { E, clamp, lerp, inv, tw } = SK;

  /* Every fact, colour and picture of the event: a remake changes this object alone. */
  const FACTS = SK.DATA.content;
  const K = FACTS.colors, FH = FACTS.fonts.head, FB = FACTS.fonts.body;
  SK.setStyle('clean');
  SK.setGround('sky', { paper: K.panel, text: K.ink, textSoft: K.soft, accent: K.blue, accentText: K.blue });

  const T = SK.cues({
    invite: [0, 'invited'], day: [1, 'Sunday'],
    bed: [2, 'bedrooms'], bath: [2, 'baths'], sqft: [2, 'thousand'], feet: [2, 'feet'],
    tour: [3, 'Tour'], find: [4, 'Find'], pin: [4, 'Northeast'], street: [4, 'Street'],
    bring: [5, 'Bring'],
  });

  // ---------------------------------------------------------------- what there is to show
  const W = SK.W, H = SK.H, U = Math.min(W, H) / 1080, wide = W / H > 1.25, tall = H / W > 1.25;
  const has = (f) => !!(f && f.img && SK.IMG[f.img]);
  let HERO = null, ROOMS = [], R1, R3, RK, starts = [], ready = false; // set once the pictures are in (ready())
  const LIST = (FACTS.facts || []).filter((f) => f && f.value).slice(0, 4);
  const WHEN = [FACTS.dayShort, FACTS.hours].filter(Boolean).join('  ·  ');
  const PLACE = [FACTS.street, FACTS.cityZip].filter(Boolean);
  const TOP = FACTS.street || FACTS.home || ''; // the caption's first line
  /* who hosts it: the agent, by name, with their own photo when there is one (people buy from people) */
  const AG = FACTS.agent && FACTS.agent.name ? FACTS.agent : null;
  const agentPhoto = () => (AG && AG.photo && SK.IMG[AG.photo.img] ? AG.photo : null);

  // ---------------------------------------------------------------- the one card: a picture over a caption strip
  const CW = W * .9, SH = (tall ? 380 : wide ? 200 : 220) * U, PH = (tall ? .7 : .86) * H - SH;
  const cropOf = (f) => { const im = SK.IMG[f.img]; return f.crop || [0, 0, im.width, im.height]; };
  const cardOf = (ph) => [-CW / 2, -(ph + SH) / 2, CW, ph + SH, ph];
  const PIN = wide ? [W * .14, H * .3] : tall ? [0, H * .2] : [0, H * .33];
  const MW = (wide ? 620 : tall ? 700 : 560) * U, MPH = MW * .52, MS = 150 * U;
  const R4 = [PIN[0] - MW / 2, PIN[1] - 150 * U - MPH - MS, MW, MPH + MS, MPH];
  const backAt = T.find - .5, landAt = T.pin + .2;
  /* the real map of the place (the map tool: SK.DATA.place); a place that is not on the map has none,
     and the card then stays large with the address under the picture */
  let MAP = null, MSC = 1;
  function setUp() {
    if (ready) return; ready = true;
    const P = SK.DATA.place;
    MAP = P && P.pin && SK.IMG[P.image] ? P : null;
    // the least scale at which the map fills the frame round the pin (the view runs 100 past each edge), and a little over
    if (MAP) MSC = 1.05 * Math.max((PIN[0] + W / 2 + 100) / (P.pin.u * P.w), (W / 2 + 100 - PIN[0]) / ((1 - P.pin.u) * P.w), (PIN[1] + H / 2 + 100) / (P.pin.v * P.h), (H / 2 + 100 - PIN[1]) / ((1 - P.pin.v) * P.h), .62);
    HERO = has(FACTS.hero) ? FACTS.hero : null;
    ROOMS = (FACTS.rooms || []).filter(has).slice(0, 3);
    // a panoramic strip is not blown up to fill a tall box: about a third of its width stays in view
    const heroH = HERO ? Math.min(PH, CW / (cropOf(HERO)[2] / cropOf(HERO)[3] * (tall ? .25 : .3))) : PH;
    R1 = cardOf(heroH); R3 = ROOMS.length ? cardOf(PH) : R1;
    RK = [[T.day - .35, R1], [T.tour - .45, R1], [T.tour, R3], [backAt, R3], [landAt, MAP ? R4 : R1]];
    const s1 = Math.max(T.tour + .5, T.find - .6);
    starts = ROOMS.map((_, i) => lerp(T.tour, s1, i / ROOMS.length));
  }
  const KEYS = [T.bed, T.bath, T.sqft, T.feet + .45];

  /* text: fitted to a width, wrapped onto two lines when shrinking would go too small */
  function fit(str, maxW, o) {
    const c = SK.ctx(); c.font = `${o.wt ?? 400} ${o.size}px "${o.font ?? FB}"`;
    const w = c.measureText(str).width + (o.ls ?? 0) * [...str].length;
    return w > maxW ? o.size * maxW / w : o.size;
  }
  function plan(str, maxW, o) { // one line, or two balanced ones when one would be too small
    let size = fit(str, maxW, o);
    if (o.one || size >= o.size * .72 || !str.includes(' ')) return { l: [str], size };
    const ws = str.split(' '); let best = 1, bd = 1e9;
    for (let i = 1; i < ws.length; i++) { const d = Math.abs(ws.slice(0, i).join(' ').length - ws.slice(i).join(' ').length); if (d < bd) { bd = d; best = i; } }
    const l = [ws.slice(0, best).join(' '), ws.slice(best).join(' ')];
    return { l, size: Math.min(o.size * .8, fit(l[0], maxW, o), fit(l[1], maxW, o)) };
  }
  function text(str, x, y, maxW, o) {
    if (!str) return 0;
    const q = plan(str, maxW, o), n = q.l.length;
    q.l.forEach((ln, i) => SK.txt(ln, x, y + (i - (n - 1) / 2) * q.size * 1.1, { ...o, size: q.size }));
    return q.size;
  }
  /* the height a row needs for a text that may take two lines */
  const rowH = (str, maxW, o, h1) => { if (!str) return h1; const q = plan(str, maxW, o); return q.l.length > 1 ? q.size * 2.2 : h1; };
  const ent = (t, t0, d = .5) => E.out(inv(t0, t0 + d, t));
  /* rows stacked about a centre: [height, draw(y)] or null; a missing row leaves no hole */
  function stack(rows, cy, gap) {
    const L = rows.filter(Boolean), tot = L.reduce((a, r) => a + r[0], 0) + gap * (L.length - 1);
    let y = cy - tot / 2;
    L.forEach((r, i) => { r[1](y + r[0] / 2, i); y += r[0] + gap; });
    return tot;
  }

  /* a picture cropped to cover a box (top-left x, y), pushed in by zoom toward fx, fy */
  function photo(f, x, y, w, h, zoom, fx) {
    const im = SK.IMG[f.img]; if (!im) return;
    const [cx, cy, cw, ch] = cropOf(f);
    const k = Math.max(w / cw, h / ch) * zoom, sw = w / k, sh = h / k;
    const c = SK.ctx(); c.save(); if (f.lift) c.filter = `brightness(${f.lift}) contrast(1.06) saturate(1.1)`;
    c.drawImage(im, cx + (cw - sw) * (fx ?? .5), cy + (ch - sh) * (f.fy ?? .5), sw, sh, x, y, w, h); c.restore();
  }
  /* a headshot in a circle: cropped to cover it, the face chosen by fx, fy (0 top .. 1 bottom) and zoom; a white rim and a thin ring */
  function face(f, cx, cy, r) {
    const im = SK.IMG[f.img], c = SK.ctx(), k = Math.max(2 * r / im.width, 2 * r / im.height) * (f.zoom ?? 1), sw = 2 * r / k;
    c.save(); c.beginPath(); c.arc(cx, cy, r, 0, SK.TAU); c.clip();
    c.drawImage(im, (im.width - sw) * (f.fx ?? .5), (im.height - sw) * (f.fy ?? .25), sw, sw, cx - r, cy - r, 2 * r, 2 * r);
    c.restore();
    c.lineWidth = r * .09; c.strokeStyle = K.white; c.beginPath(); c.arc(cx, cy, r, 0, SK.TAU); c.stroke();
    c.lineWidth = r * .04; c.strokeStyle = K.blue; c.beginPath(); c.arc(cx, cy, r + r * .075, 0, SK.TAU); c.stroke();
  }
  const pill = (str, x, y, o = {}) => SK.pill(str, x, y, { size: 34 * U, font: FB, fill: o.fill ?? K.white, col: o.col ?? K.ink, r: 30 * U, padX: 26 * U, align: o.align ?? 'left', ...o });

  /* beat 1: the yard sign swings in on its hooks, planted beside the words */
  const SG = (() => {
    const dated = !!(FACTS.day || FACTS.hours);
    // the agent's rider hangs under the board: the board gives up a little of its size for it where the frame is short
    const pw = wide ? Math.min(W * (AG ? .33 : .36), H * (AG ? .58 : .64)) : tall ? W * .64 : W * (AG ? .4 : .44);
    const rh = AG ? pw * .27 : 0, hang = AG ? rh + 16 * U : 0, below = wide ? Math.max(150 * U, hang + 56 * U) : 76 * U + hang;
    const ph = pw * (dated ? .9 : .6), armY = wide ? -(ph + below) / 2 - 10 * U : tall ? -H * .37 : -H * .44;
    const cx = wide ? -W * .22 : 30 * U, foot = armY + 34 * U + ph + below;
    return { pw, ph, armY, cx, foot, dated, rh };
  })();
  function sign(t) {
    const { pw, ph, armY, cx, foot, dated, rh } = SG, px = cx - pw / 2 - 64 * U, c = SK.ctx();
    const swing = .34 * Math.exp(-1.3 * t) * Math.cos(4.2 * t) + .015 * Math.sin(t * 1.4);
    c.fillStyle = 'rgba(29,58,99,.13)'; c.beginPath(); c.ellipse(px + 10 * U, foot, 120 * U, 13 * U, 0, 0, SK.TAU); c.fill();
    c.fillStyle = K.navy;
    c.fillRect(px - 11 * U, armY - 30 * U, 22 * U, foot - armY + 30 * U);
    c.fillRect(px - 30 * U, armY - 9 * U, pw + 124 * U, 18 * U);
    SK.at(cx, armY, swing, 1, () => {
      c.strokeStyle = K.navy; c.lineWidth = 4 * U;
      for (const sx of [-.36, .36]) { c.beginPath(); c.moveTo(sx * pw, 0); c.lineTo(sx * pw, 34 * U); c.stroke(); }
      const y0 = 34 * U, x0 = -pw / 2, k = pw / (560 * U);
      SK.card(x0, y0, pw, ph, { r: 10 * U, fill: K.white, shadow: { blur: 30, y: 18, col: 'rgba(29,58,99,.22)' } });
      if (dated) {
        SK.logo(FACTS.logo, 0, y0 + ph * .13, { w: pw * .66, h: ph * .215, pad: 0 });
        c.fillStyle = K.blue; c.fillRect(x0, y0 + ph * .26, pw, ph * .24);
        text(FACTS.kicker.toUpperCase(), 0, y0 + ph * .38, pw * .86, { size: 44 * U * k, font: FB, wt: 700, col: K.white, ls: 3 * U });
        const both = FACTS.day && FACTS.hours;
        text(FACTS.day, 0, y0 + ph * (both ? .64 : .74), pw * .86, { size: 60 * U * k, font: FH, wt: 400, col: K.ink });
        text(FACTS.hours, 0, y0 + ph * (both ? .82 : .74), pw * .8, { size: 64 * U * k, font: FB, wt: 500, col: K.blue });
      } else { // no day given: the sign carries the logo and the kind of event alone
        SK.logo(FACTS.logo, 0, y0 + ph * .23, { w: pw * .66, h: ph * .36, pad: 0 });
        c.fillStyle = K.blue; c.fillRect(x0, y0 + ph * .46, pw, ph * .42);
        text(FACTS.kicker.toUpperCase(), 0, y0 + ph * .67, pw * .86, { size: 50 * U * k, font: FB, wt: 700, col: K.white, ls: 3 * U });
      }
      if (AG) { // the rider: the agent's photo, name and number, hung from the board on two links
        const ry = y0 + ph + 16 * U, f = agentPhoto(), r = rh * .39, pad = rh * .13;
        c.strokeStyle = K.navy; c.lineWidth = 4 * U;
        for (const sx of [-.36, .36]) { c.beginPath(); c.moveTo(sx * pw, y0 + ph - 2 * U); c.lineTo(sx * pw, ry + 2 * U); c.stroke(); }
        SK.card(x0, ry, pw, rh, { r: 8 * U, fill: K.white, shadow: { blur: 24, y: 14, col: 'rgba(29,58,99,.2)' } });
        const cy = ry + rh / 2, tx = f ? x0 + pad + 2 * r + pad : 0, tw = f ? pw - (tx - x0) - pad : pw * .86, al = f ? 'left' : 'center';
        if (f) face(f, x0 + pad + r, cy, r);
        const two = !!AG.phone;
        text(AG.name, tx, cy - (two ? rh * .17 : 0), tw, { size: rh * .28, font: FB, wt: 700, col: K.ink, align: al, one: true });
        if (two) text(AG.phone, tx, cy + rh * .2, tw, { size: rh * .25, font: FB, wt: 500, col: K.blue, align: al, one: true });
      }
    });
  }
  function headline(t) {
    const al = wide ? 'left' : 'center', x = wide ? W * .04 : 0, mw = wide ? W * .41 : W * .86, k = tall ? 1.2 : 1;
    const cy = wide ? -6 * U : (SG.foot + 30 * U + H / 2 - 40 * U) / 2, t1 = T.invite + .25, t2 = T.invite + .9, c = SK.ctx();
    const o = (size, more) => ({ size: size * U * k, align: al, ...more });
    stack([
      [44 * U * k, (y) => text(FACTS.invite.toUpperCase(), x, y, mw, o(38, { font: FB, wt: 700, col: K.blue, ls: 5 * U, p: clamp(.6 + .4 * ent(t, 0, .5)) }))],
      [rowH(FACTS.home, mw, o(wide ? 156 : 124, { font: FH, wt: 300 }), (wide ? 170 : 124) * U * k), (y) => text(FACTS.home, x, y, mw, o(wide ? 156 : 124, { font: FH, wt: 300, col: K.ink, p: ent(t, t1, .7) }))],
      FACTS.homeSub ? [70 * U * k, (y) => text(FACTS.homeSub, x, y, mw, o(64, { font: FH, wt: 300, col: K.ink, p: ent(t, t2, .7) }))] : null,
      wide || tall ? [30 * U, (y) => { const rl = mw * .3 * ent(t, t2 + .3, .6); c.fillStyle = K.blue; c.fillRect(wide ? x : -rl / 2, y - 2 * U, rl, 4 * U); }] : null,
      FACTS.city ? [48 * U * k, (y) => text(FACTS.city, x, y, mw, o(42, { font: FB, wt: 500, col: K.soft, p: ent(t, t2 + .4, .5) }))] : null,
    ], cy, 16 * U * k);
  }

  /* what the card's picture is: the exterior, the rooms wiping over it, or the home's name in type */
  function picture(t, x, y, w, h) {
    const c = SK.ctx();
    if (HERO) photo(HERO, x, y, w, h, 1 + .07 * tw(t, T.day - .35, T.tour, E.lin), lerp(HERO.fx?.[0] ?? .5, HERO.fx?.[1] ?? .5, tw(t, T.day, T.tour, E.sine)));
    else {
      c.fillStyle = K.panel; c.fillRect(x, y, w, h);
      const ks = Math.min(34 * U, h * .07), ns = Math.min(150 * U, h * .24), ss = Math.min(56 * U, h * .1), mw = w * .84, no = { size: ns, font: FH, wt: 300 };
      stack([
        [ks * 1.3, (yy) => text(FACTS.kicker.toUpperCase(), x + w / 2, yy, mw, { size: ks, font: FB, wt: 700, col: K.blue, ls: ks * .14, one: true })],
        [rowH(FACTS.home, mw, no, ns * 1.15), (yy) => text(FACTS.home, x + w / 2, yy, mw, { ...no, col: K.ink })],
        FACTS.homeSub ? [ss * 1.3, (yy) => text(FACTS.homeSub, x + w / 2, yy, mw, { size: ss, font: FH, wt: 300, col: K.soft, one: true })] : null,
      ], y + h / 2, h * .035);
    }
    ROOMS.forEach((m, i) => {
      const u = E.inOut(inv(starts[i], starts[i] + .45, t)), out = t > backAt ? 1 - E.inOut(inv(backAt, backAt + .4, t)) : 1;
      if (u <= 0 || out <= 0) return;
      c.save(); c.beginPath(); c.rect(x + w * (1 - u), y, w * u, h); c.clip();
      SK.alpha(out, () => photo(m, x, y, w, h, 1 + .06 * inv(starts[i], starts[i] + 3, t), m.fx ?? .5));
      c.restore();
    });
    // a soft shade under the top edge, so the day's chip reads on any picture
    if (HERO && WHEN && t < T.tour) { const g = c.createLinearGradient(0, y, 0, y + 150 * U); g.addColorStop(0, 'rgba(0,0,0,.22)'); g.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = g; c.fillRect(x, y, w, 150 * U); }
  }

  /* the caption strip under the picture: the address; then the facts, each in its own place; then each room's name */
  function strip(t, x, y, w, h) {
    const c = SK.ctx(), pad = 46 * U, cy = y + h / 2;
    const aFacts = LIST.length ? SK.win(t, T.bed - .45, T.tour - .15, .3, .3) : 0;
    const aRoom = ROOMS.map((_, i) => SK.win(t, starts[i] + .15, ROOMS[i + 1] ? starts[i + 1] + .15 : backAt, .3, .25));
    const aAddr = clamp(1 - aFacts * 1.6 - Math.max(0, ...aRoom) * 1.6);
    if (aAddr > 0) SK.alpha(aAddr, () => {
      const p = ent(t, T.day - .25, 1), two = PLACE.length > 1 && FACTS.street;
      if (wide) {
        const rw = w * .34, lw = w - 2 * pad - rw - 40 * U;
        text(TOP, x + pad, cy - (two ? 24 : 0) * U, lw, { size: 66 * U, font: FH, wt: 400, col: K.ink, align: 'left', p });
        if (two) text(FACTS.cityZip, x + pad, cy + 44 * U, lw, { size: 34 * U, font: FB, wt: 500, col: K.soft, align: 'left', p });
        const q = ent(t, T.day + .1, .6), named = FACTS.street && FACTS.home && !FACTS.street.startsWith(FACTS.home);
        if (HERO || ROOMS.length) text(FACTS.kicker.toUpperCase(), x + w - pad, cy - (named ? 30 : 0) * U, rw, { size: 26 * U, font: FB, wt: 700, col: K.blue, ls: 4 * U, align: 'right', p: q, one: true });
        if (named && (HERO || ROOMS.length)) text(FACTS.home, x + w - pad, cy + 26 * U, rw, { size: 46 * U, font: FH, wt: 400, col: K.ink, align: 'right', p: q, one: true });
      } else stack([
        tall ? [34 * U, (yy) => text(FACTS.kicker.toUpperCase(), x + w / 2, yy, w - 2 * pad, { size: 28 * U, font: FB, wt: 700, col: K.blue, ls: 4 * U, p })] : null,
        [rowH(TOP, w - 2 * pad, { size: (tall ? 78 : 62) * U, font: FH, wt: 400 }, (tall ? 84 : 68) * U), (yy) => text(TOP, x + w / 2, yy, w - 2 * pad, { size: (tall ? 78 : 62) * U, font: FH, wt: 400, col: K.ink, p })],
        two ? [(tall ? 46 : 40) * U, (yy) => text(FACTS.cityZip, x + w / 2, yy, w - 2 * pad, { size: (tall ? 40 : 34) * U, font: FB, wt: 500, col: K.soft, p })] : null,
      ], cy, 14 * U);
    });
    if (aFacts > 0) SK.alpha(aFacts, () => {
      const n = LIST.length, cols = tall && n > 2 ? 2 : n, rows = Math.ceil(n / cols), ch = h / rows, avail = w - 2 * pad;
      const vs0 = Math.min(96 * U, ch * .5), ls0 = Math.min(28 * U, ch * .17), lab = (f) => (f.label || '').toUpperCase();
      // each column as wide as its words ask, every value at one size
      const nat = LIST.map((f) => Math.max(SK.measure(f.value, { size: vs0, font: FH, wt: 400 }), SK.measure(lab(f), { size: ls0, font: FB, wt: 700, ls: 3 * U })) + 72 * U);
      if (rows > 1) for (let i = 0; i < n; i++) nat[i] = Math.max(...nat.filter((_, j) => j % cols === i % cols));
      let k = 1; const rowW = [];
      for (let r = 0; r < rows; r++) { const sum = rows > 1 ? nat.slice(0, cols).reduce((p, q) => p + q, 0) : nat.reduce((p, q) => p + q, 0); rowW.push(sum); k = Math.min(k, avail / sum); }
      LIST.forEach((f, i) => {
        const r = Math.floor(i / cols), i0 = r * cols, inRow = rows > 1 ? cols : Math.min(cols, n - i0), spare = (avail - rowW[r] * k) / inRow;
        let cx = x + pad; for (let j = i0; j < i; j++) cx += nat[j] * k + spare;
        const cw = nat[i] * k + spare, yy = y + (r + .5) * ch, vs = vs0 * k; cx += cw / 2;
        if (i > i0) { c.fillStyle = K.line; c.fillRect(cx - cw / 2 - U, yy - ch * .3, 2 * U, ch * .6); }
        const t0 = KEYS[i] ?? KEYS[KEYS.length - 1] + .5 * (i - 3), u = ent(t, t0 - .15, .5); if (u <= 0) return;
        const bl = Math.min(cw * .34, 120 * U) * E.out(inv(t0 - .15, t0 + .45, t));
        c.fillStyle = K.blue; c.fillRect(cx - bl / 2, yy - ch / 2, bl, 5 * U); // the tick: a rule drawn on over the fact
        SK.alpha(u, () => {
          text(f.value, cx, yy - vs0 * .16 + (1 - u) * 26 * U, cw - 30 * U, { size: vs, font: FH, wt: 400, col: K.ink, one: true });
          text(lab(f), cx, yy + vs0 * .56, cw - 24 * U, { size: Math.max(ls0 * k, 19 * U), font: FB, wt: 700, col: K.soft, ls: 3 * U * k, one: true });
        });
      });
    });
    ROOMS.forEach((m, i) => {
      if (aRoom[i] <= 0) return;
      SK.alpha(aRoom[i], () => {
        const dots = (dx, dy) => { if (ROOMS.length < 2) return; ROOMS.forEach((_, j) => { c.fillStyle = j === i ? K.blue : K.line; c.beginPath(); c.arc(dx + (j - (ROOMS.length - 1) / 2) * 40 * U, dy, (j === i ? 11 : 8) * U, 0, SK.TAU); c.fill(); }); };
        const p = ent(t, starts[i] + .15, .7);
        if (wide) {
          text(m.label || '', x + pad, cy, w * .7, { size: 84 * U, font: FH, wt: 400, col: K.ink, align: 'left', p });
          dots(x + w - pad - ROOMS.length * 20 * U, cy);
        } else { const lo = { size: (tall ? 100 : 80) * U, font: FH, wt: 400 }; stack([[rowH(m.label || ' ', w - 2 * pad, lo, lo.size * 1.1), (yy) => text(m.label || '', x + w / 2, yy, w - 2 * pad, { ...lo, col: K.ink, p })], ROOMS.length > 1 ? [22 * U, (yy) => dots(x + w / 2, yy)] : null], cy, 18 * U); }
      });
    });
  }

  function cardScene(t) {
    if (t < T.day - .35 || t > T.bring + .2) return;
    const r = SK.kf(t, RK), m = MAP ? E.inOut(inv(backAt, landAt, t)) : 0, u = ent(t, T.day - .35, .5);
    const a = clamp(u * 1.4) * (1 - tw(t, T.bring - .3, T.bring + .2));
    SK.layer({ alpha: a, y: (1 - u) * 50 * U }, () => {
      const [x, y, w, h, ph] = r, sh = h - ph;
      SK.card(x, y, w, h, { r: lerp(22, 14, m) * U, fill: K.white, shadow: { blur: 44, y: 18, col: 'rgba(29,58,99,.2)' }, clip: () => picture(t, x, y, w, ph) });
      if (m < .4) SK.alpha(1 - m / .4, () => strip(t, x, y + ph, w, sh));
      if (m < .4 && WHEN && HERO) { const on = 1 - tw(t, T.tour - .3, T.tour); if (on > 0) SK.alpha(on * (1 - m / .4), () => pill(WHEN, x + 34 * U, y + 60 * U, { size: (tall ? 42 : 38) * U, fill: K.blue, col: K.white, wt: 700, in: { t: T.day, type: 'rise' } })); }
      if (m > .6) SK.alpha((m - .6) / .4, () => { // on the map the card is the pin's: where to arrive
        const l1 = FACTS.venue || FACTS.street || FACTS.home, l2 = (FACTS.venue ? PLACE : [FACTS.cityZip].filter(Boolean)).join(', ');
        text(l1, x + w / 2, y + ph + sh * (l2 ? .34 : .5), w * .88, { size: 42 * U, font: FB, wt: 700, col: K.ink, one: true });
        text(l2, x + w / 2, y + ph + sh * .7, w * .88, { size: 31 * U, font: FB, wt: 400, col: K.soft });
      });
    });
  }

  /* beat 5: the real map, the home's own street lit and named, the pin dropping under the card */
  /* where the street's name goes: a spot on its own street, clear of the card and the pin, inside the frame */
  function nameSpot(m) {
    const ln = (MAP.pin.lines || [])[0]; if (!ln || ln.length < 2) return m.street ? [m.street.x, m.street.y] : null;
    const pts = ln.map(([u, v]) => m.at(u, v)), mx = W / 2 - 240 * U, my = H / 2 - 150 * U;
    let best = null, bd = -1;
    for (let k = 0; k <= 80; k++) {
      const [x, y] = SK.S.at(pts, k / 80), dp = Math.hypot(x - PIN[0], y - PIN[1]);
      if (Math.abs(x) > mx || Math.abs(y) > my || dp < 210 * U || dp > 620 * U) continue;
      const inCard = x > R4[0] - 200 * U && x < R4[0] + R4[2] + 200 * U && y > R4[1] - 60 * U && y < R4[1] + R4[3] + 70 * U;
      if (inCard) continue;
      const d = -Math.abs(dp - 330 * U); // near the pin, not on it
      if (best === null || d > bd) { best = [x, y]; bd = d; }
    }
    return best;
  }
  function map(t) {
    if (!MAP) return;
    const a = SK.win(t, T.find - .6, T.bring + .4, .5, .6); if (a <= 0) return;
    SK.alpha(a, () => {
      const s = MSC * (1 + .07 * tw(t, T.find - .6, T.bring + .4, E.sine));
      const m = SK.map(PIN[0], PIN[1], { s, names: 10, nameSize: 27 * U, font: FB, nameCol: K.soft, namesT: landAt - .25, ownName: false, clear: [[R4[0], R4[1], R4[2], R4[3]], [PIN[0] - 56 * U, PIN[1] - 150 * U, 112 * U, 160 * U]], own: { col: K.blue, w: 15 * U, p: ent(t, T.find - .2, 1.1) } });
      if (!m) return;
      // its own street may leave no clear spot (a short lane running up under the card): the name stands beside the pin then
      const at = FACTS.mapStreet ? nameSpot(m) || [PIN[0] + (wide ? 250 : 230) * U, PIN[1] - 46 * U] : null, on = ent(t, T.street - .2, .5);
      if (at && on > 0) {
        const size = Math.min(40 * U, fit(FACTS.mapStreet, W * .5, { size: 40 * U, font: FB, wt: 700 }));
        SK.alpha(on, () => pill(FACTS.mapStreet, at[0], at[1] + (1 - on) * 20 * U, { size, fill: K.navy, col: K.white, wt: 700, align: 'center', stroke: K.white, strokeW: 4 * U }));
      }
      SK.mapPin(PIN[0], PIN[1], { t: T.pin, col: K.navy, s: U, pulse: { col: K.blue, r1: 110 * U } });
    });
  }

  /* beat 6: the end card, its rows stacked about the centre */
  function endCard(t) {
    const a = ent(t, T.bring - .4, .6); if (a <= 0) return;
    const v = SK.view, c = SK.ctx(), mw = W * .84, k = tall ? 1.4 : wide ? 1.12 : 1.06, s = (n) => n * U * k;
    SK.alpha(a * .96, () => { c.fillStyle = K.white; c.fillRect(v.x0 - 40, v.y0 - 40, v.x1 - v.x0 + 80, v.y1 - v.y0 + 80); });
    const t0 = T.bring - .2, p = (i) => ent(t, t0 + i * (AG ? .15 : .2), .55), im = SK.IMG[FACTS.logo];
    const lw = Math.min(W * .44, s(520)), lh = im ? Math.min(lw * im.height / im.width, s(AG && !tall ? 100 : AG ? 116 : 150)) : 0;
    // the agent: a photo beside the name, what they are and the number to call, set as one block about the centre;
    // in the tall frame the photo stands over them instead (the right edge there is under an app's buttons)
    const AGS = (() => {
      if (!AG) return null;
      const f = agentPhoto(), up = tall, d = f ? s(up ? 190 : 172) : 0, gap = f ? s(up ? 26 : 36) : 0, room = up ? mw * .8 : mw - d - gap;
      const ns = { size: s(52), font: FB, wt: 700 }, rs = { size: s(30), font: FB, wt: 400 }, psz = s(36);
      const nsz = Math.min(ns.size, fit(AG.name, room, ns)), rsz = AG.role ? Math.min(rs.size, fit(AG.role, room, rs)) : 0;
      const rows = [[nsz * 1.16, AG.name, { ...ns, size: nsz, col: K.ink }], AG.role ? [rsz * 1.5, AG.role, { ...rs, size: rsz, col: K.soft }] : null].filter(Boolean);
      const th = rows.reduce((q, r) => q + r[0], 0) + (AG.phone ? psz * 2.1 : 0);
      const tw = Math.max(SK.measure(AG.name, { ...ns, size: nsz }), AG.role ? SK.measure(AG.role, { ...rs, size: rsz }) : 0, AG.phone ? SK.measure(AG.phone, { size: psz, font: FB, wt: 700 }) + 2 * psz * .8 : 0);
      return { f, up, d, gap, room, rows, th, tw, psz, h: (up ? d + gap + th : Math.max(d, th)) + s(up ? 28 : 10) };
    })();
    const agentRow = (y, a) => {
      const { f, up, d, gap, room, rows, th, tw, psz } = AGS, side = f && !up, x0 = side ? -(d + gap + tw) / 2 : 0;
      const al = side ? 'left' : 'center', ax = side ? x0 + d + gap : 0, top = up ? y - (d + gap + th) / 2 : y - th / 2; let ty = up ? top + d + gap : top;
      SK.alpha(a, () => {
        if (f) face(f, side ? x0 + d / 2 : 0, (up ? top + d / 2 : y) + (1 - a) * 24 * U, d / 2);
        for (const [h, str, o] of rows) { text(str, ax, ty + h / 2, room, { ...o, align: al, one: true }); ty += h; }
        if (AG.phone) pill(AG.phone, ax, ty + psz * 1.2, { size: psz, fill: K.blue, col: K.white, wt: 700, align: al });
      });
    };
    const one = wide && PLACE.join(', ').length < 60;
    stack([
      im ? [lh, (y, i) => SK.alpha(p(i), () => SK.image(FACTS.logo, 0, y, null, lh))] : null,
      [s(52), (y, i) => text(FACTS.kicker.toUpperCase(), 0, y + s(10), mw, { size: s(36), font: FB, wt: 700, col: K.blue, ls: 5 * U, p: p(i) })],
      FACTS.day ? [s(124), (y, i) => text(FACTS.day, 0, y, mw, { size: s(116), font: FH, wt: 300, col: K.ink, p: p(i), one: true })] : null,
      FACTS.hours ? [s(78), (y, i) => text(FACTS.hours, 0, y, mw, { size: s(74), font: FB, wt: 500, col: K.blue, p: p(i), one: true })] : null,
      [s(20), (y, i) => { c.fillStyle = K.line; const rl = Math.min(mw, s(640)) * p(i); c.fillRect(-rl / 2, y, rl, 2 * U); }],
      FACTS.venue ? [s(50), (y, i) => text(FACTS.venue, 0, y, mw, { size: s(46), font: FB, wt: 700, col: K.ink, p: p(i) })] : null,
      one ? [s(46), (y, i) => text(PLACE.join(', '), 0, y, mw, { size: s(40), font: FB, wt: FACTS.venue ? 400 : 600, col: FACTS.venue ? K.soft : K.ink, p: p(i) })] : null,
      !one && FACTS.street ? [s(48), (y, i) => text(FACTS.street, 0, y, mw, { size: s(42), font: FB, wt: FACTS.venue ? 400 : 600, col: FACTS.venue ? K.soft : K.ink, p: p(i) })] : null,
      !one && FACTS.cityZip ? [s(44), (y, i) => text(FACTS.cityZip, 0, y, mw, { size: s(38), font: FB, wt: 400, col: K.soft, p: p(i) })] : null,
      AG ? [AGS.h, (y, i) => agentRow(y + s(6), p(i))] : FACTS.contact ? [s(96), (y) => { const size = Math.min(s(40), fit(FACTS.contact, mw - s(80), { size: s(40), font: FB, wt: 700 })); pill(FACTS.contact, 0, y + s(14), { size, fill: K.blue, col: K.white, wt: 700, align: 'center', in: { t: t0 + 1.4, type: 'rise' } }); }] : null,
    ], -H * (AG && !tall ? .035 : .01), s(tall ? 40 : AG ? 20 : 30)); // with the agent's block last, the stack sits a little higher: a player's bar and the captions take the frame's foot
  }

  const camera = SK.breath(SK.camera([[0, [0, 0, 1.02]], [T.day, [0, 0, 1]], [T.bring - .4, [0, 0, 1.01]], [30, [0, 0, 1.06], E.sine]]), { amp: 8, zoom: .015, period: 10 });
  SK.film({
    duration: 30,
    camera,
    fadeOut: .6,
    draw(t) {
      setUp();
      map(t);
      const out1 = 1 - tw(t, T.day - .65, T.day - .2);
      if (out1 > 0) SK.layer({ alpha: out1, y: -60 * U * (1 - out1) }, () => { sign(t); headline(t); });
      cardScene(t);
      endCard(t);
    },
  });
})();
