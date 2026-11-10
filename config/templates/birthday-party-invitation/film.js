// For: the birthday child's friends (preschool and up) and their grown-ups; bright, silly, bouncy and irresistible
/* A birthday party invitation (40 s, crayon on the blush ground), narrated by a bubbly kids'-TV
   party host. One wide slime world the camera slides through, left to right, with the star
   (content.star: the venue's mascot, cast/mascot.js, or the birthday child, cast/kid.js) surfing
   along on slime between five stops. Rainbow goo drips from the ceiling the whole way.

   This film is a template: every fact of the party -- the child's name, age and photo, the venue,
   its sign, city and address, the date and time, the greeting, headline and stamp, the colours --
   is content.json (SK.DATA.content). Another party is another content.json, another narration
   (vo.json) and, when the place is not a slime place, other middle scenes.

   The clock is the narration: eight lines, one per scene, every cue hung on a word (SK.w) and
   each slide between stops on a line's start. Times are the sample's, for orientation.
     line 0  0.5-3.6   stop 1 (x 0): "Hey, friends! Guess who's turning <age>?" -- the greeting writes
                       on, a "?" blob in a ring of pink slime, the big age number pops on the age word
     line 1  3.9-7.7   "It's <name>! Come to <their> super slimy party!" -- the blob becomes the
                       child's photo on the name, the name plate under it; the star jumps in on
                       'come', jiggles on 'slimy', confetti on 'party'
     slide 1           line 2's start -.7 .. +.1
     line 2  8.0-13.8  stop 2 (x 2200): "At <venue> in <city>, the squishiest place in town!" -- the
                       storefront: the sign's first line pops letter by letter on its first word, the
                       second line on its second word, the city plate on the city's first word, the
                       building jiggles on 'squishiest'
     slide 2           line 3's start -.85 .. -.1
     line 3  14.2-18.6 stop 3 (x 4400): "Squish it! Stretch it! Poke it! Pop it!" -- the slime bar:
                       the star kneads a lump of slime, a sticker word on each verb, a bubble pops
     line 4  18.9-23.0 "Make slime in every color of the rainbow." -- the jars fill on 'every', the
                       lump cycles colours, RAINBOW! on 'rainbow'
     slide 3           line 5's start -.3 .. +.4
     line 5  23.3-27.3 stop 4 (x 6600): "And watch out... you might get slimed!" -- the bucket
                       wobbles on 'watch' and tips on 'slimed', the star is slimed
     slide 4           line 6's start -.4 .. +.35
     line 6  27.6-32.2 stop 5 (x 8900): "So grab your grown-up and come celebrate <name>'s <nth>
                       birthday!" -- the photo again, the cake (a candle a year) on 'celebrate', the
                       headline on the name's possessive and 'birthday', then the venue, address,
                       date and time write on
     line 7  32.6-36.8 "You're invited! We can't wait to see you at <venue>!" -- the stamp lands on
                       'invited', confetti on the venue's first word; held to 40 s */
(function () {
  'use strict';
  const { S, E, clamp, lerp, tw, pop, TAU, rnd, mix, P } = SK;
  const w = (li, word, fb, n = 0) => SK.w(li, word, fb, 's', n);
  SK.setStyle('crayon');
  SK.setGround('blush');
  const C = SK.C, F = 'Balsamiq Sans', inv = SK.inv;

  // ---------------------------------------------------------------- the party (content.json)
  const D = (SK.DATA && SK.DATA.content) || {}, KID = D.child || {}, VEN = D.venue || {}, WHEN = D.when || {}, COPY = D.copy || {}, PAL = D.palette || {};
  const STAR = SK.cast[D.star] || SK.cast.mascot || SK.cast.kid;
  const NAME = String(KID.name || '').trim(), AGE = Math.max(1, Math.round(Number(KID.age) || 1)), PHOTO = KID.photo || null;
  const ordinal = (n) => n + ((n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'));
  const NTH = String(KID.nth || ordinal(AGE));
  const fill = (s) => String(s ?? '').replace(/\{name\}/g, NAME).replace(/\{nth\}/g, NTH).replace(/\{age\}/g, String(AGE));
  const SIGN = [].concat(VEN.sign || []).map(String).filter(Boolean).slice(0, 2);
  const CITY = String(VEN.city || '').toLocaleUpperCase(), ADDR = [].concat(VEN.address || []).map(String).slice(0, 2);
  const HELLO = fill(COPY.hello), HEAD = [].concat(COPY.headline || []).map(fill).slice(0, 2), INVITED = fill(COPY.invited);
  const GOO = Array.isArray(PAL.goo) && PAL.goo.length === 6 ? PAL.goo : ['#ff5fae', '#8fe05a', '#40cfe8', '#ffd23f', '#a98bff', '#ff9a3d'];
  const FRONT = PAL.front || '#ff3fa8', TRIM = PAL.trim || '#ff7cc4', DATE = PAL.date || '#e2367f';
  const [PINK, LIME, AQUA, YEL, PURP, ORNG] = GOO;
  const FLOOR = 300, X2 = 2200, X3 = 4400, X4 = 6600, X5 = 8900;

  // a word's width as SK.txt sets it (letter by letter), and the size at which it fits maxW
  function measure(str, size, o = {}) {
    const ctx = SK.ctx(), ls = o.ls ?? 0; ctx.font = `${o.wt ?? 700} ${size}px "${o.font ?? F}"`;
    return [...String(str)].reduce((a, c) => a + ctx.measureText(c).width + ls, 0) - ls;
  }
  function fit(str, size, maxW, o) {
    let s = size;
    for (let i = 0; i < 2; i++) { const wd = measure(str, s, o); if (wd <= maxW) break; s *= maxW / wd; }
    return s;
  }

  // ---------------------------------------------------------------- the clock (narration words)
  const first = (s) => String(s || '').trim().split(/\s+/)[0] || '';
  const last = (s) => String(s || '').trim().split(/\s+/).pop() || '';
  function said(li, words, fb) { // the first of these (a word, or a word's index) found in line li, else fb
    for (const x of words) {
      if (x === '' || x == null) continue;
      const t = SK.w(li, x, NaN);
      if (!Number.isNaN(t)) return t;
    }
    return fb;
  }
  const NUM = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];
  const ends0 = SK.line(0).words.length - 1; // the age is line 0's last word when it is said some other way
  const tHey = w(0, 'hey', .5), tAge = said(0, [NUM[AGE], String(AGE), ends0], 2.62);
  const tName = said(1, [first(NAME), first(NAME).split('-')[0], 1], 4.4), tCome = w(1, 'come', 5.24), tSlimy = w(1, 'slimy', 6.1), tParty = w(1, 'party', 6.92);
  const tSign = said(2, [first(SIGN[0]), first(VEN.name)], 8.35), tSign2 = said(2, [first(SIGN[1])], 9.21), tCity = said(2, [first(VEN.city)], 9.97), tSquishiest = w(2, 'squishiest', 11.25);
  const tSquish = w(3, 'squish', 14.16), tStretch = w(3, 'stretch', 15.88), tPoke = w(3, 'poke', 16.8), tPop = w(3, 'pop', 17.56);
  const tMake = w(4, 'make', 18.91), tEvery = w(4, 'every', 20.31), tRainbow = w(4, 'rainbow', 21.87);
  const tWatch = w(5, 'watch', 23.61), tSlimed = w(5, 'slimed', 26.03);
  const tCeleb = w(6, 'celebrate', 29.66), tNames = said(6, [last(NAME) + "'s", last(NAME), first(NAME)], 30.25), tBday = w(6, 'birthday', 31.11);
  const tInv = w(7, 'invited', 33.17), tVenue = said(7, [first(SIGN[0]), first(VEN.name)], 35.63);
  const L = (i) => SK.line(i).start;
  // the four slides between stops
  const M = [[L(2) - .7, L(2) + .1], [L(3) - .85, L(3) - .1], [L(5) - .3, L(5) + .4], [L(6) - .4, L(6) + .35]];
  const camera = SK.camera([[0, [0, -50, 1]], [M[0][0], [60, -60, 1.05]], [M[0][1], [X2, -50, 1]], [M[1][0], [X2 + 40, -60, 1.04]], [M[1][1], [X3, -50, 1]],
    [tMake, [X3, -40, 1.07]], [M[2][0], [X3, -50, 1.03]], [M[2][1], [X4, -50, 1]], [tSlimed, [X4, -60, 1.06]], [M[3][0], [X4, -50, 1.03]], [M[3][1], [X5, -50, 1]], [40, [X5, -60, 1.04], E.sine]],
    [{ t: tSlimed + .2, w: .15, amp: 9 }, { t: tInv, w: .12, amp: 9 }]);
  const starX = (t) => SK.kf(t, [[0, 700], [M[0][0], 700], [M[0][1], X2 - 560], [M[1][0], X2 - 560], [M[1][1], X3], [M[2][0], X3], [M[2][1], X4 - 40], [M[3][0], X4 - 40], [M[3][1], X5 + 660]]);
  const slide = (t) => Math.max(...M.map(([a, b]) => Math.sin(Math.PI * inv(a, b, t))));
  const HOLD3 = { F: [112, -200], B: [-112, -200] }, CT = 185; // the slime bar: the star's hands, the counter top
  const POSES = [[0, 'cheer'], [tParty - .2, 'wave'], [M[0][0], 'slide'], [M[0][1], 'point'], [tSquishiest, 'wide'], [tSquishiest + .9, 'point'], [M[1][0], 'slide'], [M[1][1] - .15, HOLD3],
    [tSquish, { F: [60, -235], B: [-60, -235] }], [tStretch, { F: [245, -205], B: [-245, -205] }], [tPoke, { F: [12, -250], B: [-112, -200] }], [tPop, HOLD3],
    [M[2][0], 'slide'], [M[2][1], 'rest'], [tWatch, 'uhoh'], [tSlimed + .3, 'cheer'], [M[3][0], 'slide'], [M[3][1], 'wave'], [tCeleb - .15, 'cake']];

  // ---------------------------------------------------------------- helpers
  function dripEdge(x0, x1, y, drips, wav = 0, ph = 0) { // a goo edge, left to right, with drips [[x, len, r]]
    const base = (x) => y + wav * Math.sin(x / 80 + ph), out = []; let x = x0;
    for (const [dx, Ln, r] of drips) {
      for (; x < dx - r; x += 14) out.push([x, base(x)]);
      const b = base(dx);
      out.push(...S.line(dx - r * .7, b, dx - r, b + Ln), ...S.arc(dx, b + Ln, r, Math.PI, 0).slice(1), ...S.line(dx + r, b + Ln, dx + r * .7, b).slice(1));
      x = dx + r + 6;
    }
    for (; x < x1; x += 14) out.push([x, base(x)]);
    out.push([x1, base(x1)]);
    return out;
  }
  function sticker(str, x, y, size, col, k, o = {}) { // chunky printed word: ink shadow, ink outline, colour
    if (k <= 0) return;
    SK.at(x, y, o.rot ?? 0, k >= 1 ? 1 : E.back(k), () => {
      SK.txt(str, 7, 8, { size, font: F, wt: 700, col: C.ink, stroke: size * .1, seed: o.seed ?? 5 });
      SK.txt(str, 0, 0, { size, font: F, wt: 700, col, stroke: size * .1, strokeCol: C.ink, seed: o.seed ?? 5 });
    });
  }
  function rainbowWord(str, x, y, size, t0, t) {
    const ctx = SK.ctx(); ctx.font = `700 ${size}px "${F}"`;
    const ch = [...str], ws = ch.map((c) => ctx.measureText(c).width), tot = ws.reduce((a, b) => a + b, 0);
    let cx = x - tot / 2;
    ch.forEach((c, i) => { sticker(c, cx + ws[i] / 2, y + Math.sin(t * 4 + i) * 5, size, GOO[i % 6], inv(t0 + i * .06, t0 + i * .06 + .4, t), { seed: 10 + i }); cx += ws[i]; });
  }
  function ceiling(t) { // rainbow goo dripping from the top of the room
    const v = SK.view, seg = 540;
    for (let k = Math.floor(v.x0 / seg) - 1; k <= Math.ceil(v.x1 / seg); k++) {
      const x0 = k * seg - 20, x1 = (k + 1) * seg + 20, r = SK.mulberry(k * 71 + 9), drips = [];
      for (let d = 0; d < 3; d++) drips.push([x0 + 80 + d * 150 + r() * 70, (20 + r() * 70) * (.85 + .15 * Math.sin(t * 1.2 + k * 2 + d)), 16 + r() * 10]);
      const edge = dripEdge(x0, x1, -462, drips, 7, k);
      SK.wash([...edge, [x1, v.y0 - 60], [x0, v.y0 - 60]], GOO[((k % 6) + 6) % 6], { seed: 60 + (k & 15), dx: 0, dy: 0 });
      SK.ink(edge, { w: 5, seed: 80 + (k & 15) });
      drips.forEach(([dx, Ln, rr], d) => SK.ink(S.arc(dx, -462 + Ln, rr * .6, Math.PI * 1.05, Math.PI * 1.4), { w: 4, col: 'rgba(255,255,255,.8)', seed: 90 + d, dbl: false }));
    }
  }
  function sprinkles() { // party sprinkles on the wall
    const v = SK.view, g = 150, ctx = SK.ctx();
    ctx.save(); ctx.lineCap = 'round'; ctx.lineWidth = 10; ctx.globalAlpha = .5;
    for (let i = Math.floor(v.x0 / g); i <= Math.ceil(v.x1 / g); i++) for (let j = -3; j <= 1; j++) {
      const r = SK.mulberry(i * 131 + j * 977 + 5);
      if (r() > .5) continue;
      const x = i * g + r() * g, y = j * g + r() * g + 40, c = GOO[Math.floor(r() * 6)], a = r() * TAU;
      if (y > FLOOR - 30 || y < -400) continue;
      ctx.strokeStyle = c; ctx.beginPath(); ctx.moveTo(x - Math.cos(a) * 13, y - Math.sin(a) * 13); ctx.lineTo(x + Math.cos(a) * 13, y + Math.sin(a) * 13); ctx.stroke();
    }
    ctx.restore();
  }
  function photo(x, y, r, t, s, reveal, seed) { // the child's photo in a ring of pink slime
    if (s <= 0) return;
    const ctx = SK.ctx(), b = .035 * Math.sin(t * 5) * (1 - reveal);
    SK.at(x, y, Math.sin(t * 1.3 + seed) * .03, [s * (1 + b), s * (1 - b)], () => {
      for (const [a, Ln, rr] of [[-.5, .42, .08], [.08, .55, .1], [.6, .36, .07]]) {
        const dx = a * r, top = Math.sqrt(1 - a * a) * r, len = Ln * r * (.9 + .1 * Math.sin(t * 2 + a * 5)), q = rr * r;
        const d = [...S.line(dx - q * .7, top, dx - q, top + len), ...S.arc(dx, top + len, q, Math.PI, 0).slice(1), ...S.line(dx + q, top + len, dx + q * .7, top).slice(1)];
        SK.wash(d, PINK, { seed: 310 + seed, dx: 0, dy: 0 }); SK.ink(d, { w: 5, seed: 311 + seed });
      }
      const ring = [];
      for (let i = 0; i < 90; i++) { const a = i / 90 * TAU; ring.push([Math.cos(a) * r * (1.14 + .025 * Math.sin(a * 5 + t * 2.2)), Math.sin(a) * r * (1.14 + .02 * Math.sin(a * 8 - t * 1.7))]); }
      SK.wash(ring, PINK, { seed: 300 + seed, dx: 0, dy: 0 }); SK.ink([...ring, ring[0]], { w: 6, seed: 301 + seed });
      if (reveal > 0) {
        ctx.save(); ctx.beginPath(); ctx.arc(0, 0, r * reveal, 0, TAU); ctx.clip();
        ctx.fillStyle = '#fff3b8'; ctx.fillRect(-r, -r, 2 * r, 2 * r);
        if (PHOTO) SK.image(PHOTO, 0, r * .12, r * 2.15); // the cut-out, head and shoulders filling the circle
        else if (NAME) sticker([...NAME][0].toLocaleUpperCase(), 0, 0, r * 1.1, PINK, 1, { seed: 304 + seed }); // no photo: the initial
        ctx.restore();
        SK.ink(S.ell(0, 0, r * reveal, r * reveal), { w: 6, seed: 302 + seed });
      }
      SK.ink(S.arc(0, 0, r * 1.07, Math.PI * 1.15, Math.PI * 1.4), { w: 9, col: 'rgba(255,255,255,.75)', seed: 303 + seed, dbl: false });
    });
  }
  function slimeShape(cx, cy, hw, th, o) { // a held lump of slime: squished, stretched, poked
    const n = 30, top = [], bot = [];
    for (let i = 0; i <= n; i++) {
      const u = i / n, sn = Math.sin(Math.PI * u), x = cx + (u * 2 - 1) * hw, y = cy + (o.sag ?? 0) * sn;
      const h = th * Math.sqrt(sn) * (1 - (o.pinch ?? 0) * Math.exp(-(((u - .5) / .2) ** 2)));
      top.push([x, y - h + (o.dent ?? 0) * Math.exp(-(((u - .5) / .08) ** 2))]); bot.push([x, y + h * 1.1]);
    }
    const pts = [...top, ...bot.reverse()];
    SK.wash(pts, o.col, { seed: 460, dx: 3, dy: 3 }); SK.ink([...pts, pts[0]], { w: 5, seed: 461 });
    const a = top[6], b = top[11];
    SK.ink(S.line(a[0], a[1] + 16, b[0], b[1] + 13), { w: 6, col: 'rgba(255,255,255,.8)', seed: 462, dbl: false });
    return top[15];
  }

  // ---------------------------------------------------------------- the stops
  // stop 1 (lines 0-1): the "?" blob that becomes the photo, the name plate, the greeting, the age
  function stop1(t) {
    const rv = E.out(inv(tName - .1, tName + .45, t));
    photo(-420, -40, 240, t, 1, rv, 0);
    if (rv < 1) SK.alpha(1 - rv, () => sticker('?', -420, -30, 300, '#ffffff', 1 - rv, { rot: .1 * Math.sin(t * 3), seed: 2 }));
    const rk = inv(tName + .2, tName + .6, t), PLATE = NAME.toLocaleUpperCase();
    if (rk > 0 && PLATE) SK.at(-420, 215, -.04, E.back(rk), () => { // the plate grows with the name, up to 620 wide
      const ns = fit(PLATE, 92, 520), pw = Math.max(340, measure(PLATE, ns) + 100);
      const rb = S.rrect(-pw / 2, -52, pw, 104, 22); SK.wash(rb, LIME, { seed: 320 }); SK.ink(rb, { w: 6, seed: 321 });
      sticker(PLATE, 0, 2, ns, '#ffffff', 1, { seed: 3 });
    });
    for (let i = 0; i < 5; i++) { const a = i * 1.26 + 1, k = tw(t, tName + .1 + i * .08, tName + .5 + i * .08); SK.sparkle(-420 + Math.cos(a) * 330, -40 + Math.sin(a) * 310, 22 * k * (.8 + .2 * Math.sin(t * 6 + i)), k, 330 + i, YEL); }
    if (HELLO) SK.txt(HELLO, 240, -250, { size: fit(HELLO, 110, 760, { font: SK.FONT_HAND }), p: clamp(.2 + .8 * inv(tHey, tHey + .9, t)), seed: 4 });
    const kj = t - tSlimy, j = kj > 0 ? .1 * Math.exp(-2.2 * kj) * Math.sin(kj * 17) : 0;
    SK.at(240, 40, 0, [1 + j, 1 - j], () => sticker(String(AGE), 0, 0, fit(String(AGE), 440, 520), LIME, inv(tAge - .05, tAge + .4, t), { rot: .06 * Math.sin(t * 2.2), seed: 6 }));
    const pk = tw(t, tCome - .35, tCome);
    if (pk > 0) { const pd = S.ellC(700, FLOOR + 8, 140 * pk, 24 * pk); SK.wash(pd, LIME, { seed: 340, dx: 0, dy: 0 }); SK.ink(pd, { w: 4.5, seed: 341 }); }
  }
  function palm(x, t) { // a palm beside the storefront: the sample city's touch -- swap it for the new city's
    const top = [x + 10, FLOOR - 520], sw = .05 * Math.sin(t * 1.6);
    const tr = S.path([['M', x, FLOOR], ['Q', x + 50, FLOOR - 260, top[0], top[1]]]);
    SK.ink(tr, { w: 40, seed: 250, taper: false, dbl: false }); SK.ink(tr, { w: 32, col: '#c98a4b', seed: 250, taper: false, dbl: false });
    for (let i = 0; i < 7; i++) {
      const a = -Math.PI / 2 + (i - 3) * .52 + sw, tip = [top[0] + Math.cos(a) * 175, top[1] + Math.sin(a) * 120 + 55], n = [-Math.sin(a) * 34, Math.cos(a) * 34];
      const mx = (top[0] + tip[0]) / 2, my = (top[1] + tip[1]) / 2 - 30;
      const lf = S.path([['M', top[0], top[1]], ['Q', mx + n[0], my + n[1], tip[0], tip[1]], ['Q', mx - n[0], my - n[1], top[0], top[1]]]);
      SK.wash(lf, '#58c46a', { seed: 260 + i, dx: 2, dy: 2 }); SK.ink(lf, { w: 4.5, seed: 270 + i });
    }
  }
  function whiteWord(str, x, y, size, t0, t) { // sign letters: white, popped in one by one
    const ctx = SK.ctx(); ctx.font = `700 ${size}px "${F}"`;
    const ch = [...str], ws = ch.map((c) => ctx.measureText(c).width), tot = ws.reduce((a, b) => a + b, 0);
    let cx = x - tot / 2;
    ch.forEach((c, i) => { sticker(c, cx + ws[i] / 2, y + Math.sin(t * 3 + i) * 3, size, '#ffffff', inv(t0 + i * .06, t0 + i * .06 + .4, t), { seed: 10 + i }); cx += ws[i]; });
  }
  function eyeDisc(x, y, r, t, seed) { // the mascot's target eye, as a wall medallion on the storefront
    const look = [Math.sin(t * .9 + seed) * r * .08, r * .05];
    for (const [rr, c, i] of [[1, '#f0467e', 0], [.8, '#ffe25a', 1]]) { const d = S.ellC(x, y, r * rr, r * rr); SK.wash(d, c, { seed: seed + i, dx: 0, dy: 0, tex: false }); }
    SK.ink(S.ell(x, y, r, r), { w: 5, seed: seed + 2 });
    SK.wash(S.ellC(x + look[0], y + look[1], r * .34, r * .34), '#2b2a3a', { seed: seed + 3, dx: 0, dy: 0, tex: false });
    SK.wash(S.ellC(x + look[0] - r * .1, y + look[1] - r * .12, r * .1, r * .08), '#ffffff', { seed: seed + 4, dx: 0, dy: 0, tex: false });
  }
  function archWin(x0, x1, y0, y1, seed) { // an arched window: dark glass, white muntins, a pale trim
    const r = (x1 - x0) / 2, cx = (x0 + x1) / 2;
    const pts = [[x0, y1], [x0, y0 + r], ...S.arc(cx, y0 + r, r, Math.PI, TAU, r).slice(1), [x1, y1]];
    SK.wash(pts, '#ff86c6', { seed, dx: 0, dy: 0, tex: false });
    const g = [[x0 + 12, y1 - 10], [x0 + 12, y0 + r], ...S.arc(cx, y0 + r, r - 12, Math.PI, TAU, r - 12).slice(1), [x1 - 12, y1 - 10]];
    SK.wash(g, '#3d5a8c', { seed: seed + 1, dx: 0, dy: 0 }); SK.ink([...pts, pts[0]], { w: 5, seed: seed + 2 });
    SK.ink(S.line(cx, y0 + 14, cx, y1 - 10), { w: 4, col: '#ffffff', seed: seed + 3, dbl: false });
    SK.ink(S.line(x0 + 12, y0 + r + 30, x1 - 12, y0 + r + 30), { w: 4, col: '#ffffff', seed: seed + 4, dbl: false });
    SK.ink(S.line(x0 + 24, y1 - 30, x0 + 44, y0 + r + 50), { w: 5, col: 'rgba(255,255,255,.45)', seed: seed + 5, dbl: false });
  }
  // stop 2 (line 2): the venue's storefront, drawn after the venue's own building -- redraw it for
  // another venue; the sign, the city plate and the colours (palette.front/trim) are content
  function stop2(t) {
    const ks = t - tSquishiest, jig = (ks > 0 ? .09 * Math.exp(-2.4 * ks) * Math.sin(ks * 16) : 0) + .012 * Math.sin(t * 2.4);
    SK.at(X2 + 150, FLOOR, 0, [1 + jig, 1 - jig], () => {
      const W = 900, H = 560, AR = 118, HOT = FRONT;
      // the facade, with the arched pediment in the middle of its roofline
      const body = [[-W / 2, 0], [-W / 2, -H], [-AR - 20, -H], ...S.arc(0, -H, AR + 20, Math.PI, TAU, AR + 20).slice(1), [W / 2, -H], [W / 2, 0]];
      SK.wash(body, HOT, { seed: 200 }); SK.ink([...body, body[0]], { w: 6, seed: 201 });
      SK.ink(S.line(-W / 2, -H + 26, -AR - 16, -H + 26), { w: 5, col: TRIM, seed: 202, dbl: false });
      SK.ink(S.line(AR + 16, -H + 26, W / 2, -H + 26), { w: 5, col: TRIM, seed: 203, dbl: false });
      archWin(-AR + 14, AR - 14, -H - AR + 26, -H + 10, 230);
      for (const sd of [-1, 1]) { // raised panels and the tall side windows
        archWin(sd < 0 ? -W / 2 + 40 : W / 2 - 170, sd < 0 ? -W / 2 + 170 : W / 2 - 40, -H + 60, -H + 230, 240 + sd * 10);
        for (const px of [-W / 2 + 20, W / 2 - 38]) SK.ink(S.line(px + 9, -H + 30, px + 9, -12), { w: 4, col: TRIM, seed: 262 + (px > 0 ? 1 : 0), dbl: false });
      }
      // the sign: its first line in big white letters popped one by one, its second line written on
      if (SIGN[0]) whiteWord(SIGN[0], 0, -H + 88, fit(SIGN[0], 116, 620), tSign - .15, t);
      if (SIGN[1]) SK.txt(SIGN[1], 0, -H + 168, { size: fit(SIGN[1], 54, 500, { ls: 10 }), font: F, wt: 700, ls: 10, col: '#ffffff', stroke: 6, strokeCol: C.ink, p: clamp(.25 + .75 * inv(tSign2, tSign2 + .5, t)), seed: 205 });
      const lk = inv(tCity - .05, tCity + .35, t);
      if (lk > 0 && CITY) SK.at(0, -H + 238, .03, E.back(lk), () => { // the city plate, as wide as the city needs
        const cs = fit(CITY, 40, 520, { ls: 3 }), pw = Math.max(350, measure(CITY, cs, { ls: 3 }) + 40);
        const pl = S.rrect(-pw / 2, -30, pw, 60, 30); SK.wash(pl, YEL, { seed: 206 }); SK.ink(pl, { w: 5, seed: 207 }); SK.txt(CITY, 0, 2, { size: cs, font: F, wt: 700, col: C.ink, ls: 3, seed: 208 });
      });
      eyeDisc(-345, -H + 300, 52, t, 270); eyeDisc(345, -H + 300, 52, t, 280);
      for (const sd of [-1, 1]) { // shop windows full of slime jars
        const wx = sd < 0 ? -420 : 190, gl = S.rrect(wx, -190, 230, 140, 14);
        SK.wash(gl, '#dff6ff', { seed: 210 + sd, dx: 0, dy: 0 }); SK.ink(gl, { w: 5, seed: 212 + sd });
        for (let i = 0; i < 3; i++) { const jx = wx + 45 + i * 70, jc = GOO[(i + (sd > 0 ? 3 : 0)) % 6], jb = S.rrect(jx - 24, -110, 48, 60, 10); SK.wash(jb, jc, { seed: 214 + i, dx: 0, dy: 0 }); SK.ink(jb, { w: 4, seed: 217 + i, dbl: false }); }
      }
      const door = [[-85, 0], [-85, -170], ...S.arc(0, -170, 85, Math.PI, TAU, 70).slice(1), [85, 0]];
      SK.wash(door, TRIM, { seed: 220 }); SK.ink([...door, door[0]], { w: 5.5, seed: 221 });
      SK.ink(S.line(0, -238, 0, 0), { w: 4, seed: 222, dbl: false });
      for (const sd of [-1, 1]) SK.ink(S.ell(sd * 22, -110, 10, 10), { w: 4, seed: 223 + sd, dbl: false });
    });
    palm(X2 + 780, t);
  }
  function jar(x, y, col, f, i) {
    const b = S.rrect(x - 44, y - 118, 88, 118, 18);
    SK.wash(b, '#f4fbff', { seed: 400 + i, dx: 0, dy: 0, alpha: .9 });
    if (f > 0) SK.wash(S.rrect(x - 40, y - 4 - 96 * f, 80, 96 * f, 14), col, { seed: 410 + i, dx: 0, dy: 0 });
    SK.ink(b, { w: 5, seed: 420 + i });
    const lid = S.rrect(x - 50, y - 136, 100, 24, 8); SK.wash(lid, col, { seed: 430 + i, dx: 0, dy: 0 }); SK.ink(lid, { w: 4.5, seed: 440 + i });
  }
  // stop 3 (lines 3-4): the slime bar -- the jars on the shelf, the counter, the lump the star kneads, the words
  function stop3back(t) {
    const pl = S.rrect(X3 - 480, -150, 960, 22, 8); SK.wash(pl, '#ffd6ea', { seed: 450 }); SK.ink(pl, { w: 5, seed: 451 });
    for (let i = 0; i < 6; i++) jar(X3 - 400 + i * 160, -150, GOO[i], tw(t, tEvery + i * .22, tEvery + i * .22 + .45, E.out), i);
  }
  function counter() {
    const x0 = X3 - 560, x1 = X3 + 560, fr = S.poly([[x0, CT + 20], [x1, CT + 20], [x1, FLOOR + 12], [x0, FLOOR + 12]], true), ctx = SK.ctx();
    SK.wash(fr, '#ff8cc6', { seed: 470 }); SK.ink(fr, { w: 5.5, seed: 471 });
    ctx.save(); ctx.fillStyle = 'rgba(255,255,255,.55)';
    for (let i = 0; i < 14; i++) for (let j = 0; j < 2; j++) { ctx.beginPath(); ctx.arc(x0 + 50 + i * 78 + j * 39, CT + 55 + j * 45, 10, 0, TAU); ctx.fill(); }
    ctx.restore();
    const top = S.rrect(x0 - 20, CT, x1 - x0 + 40, 30, 10); SK.wash(top, '#ffffff', { seed: 472 }); SK.ink(top, { w: 5, seed: 473 });
    for (const [bx, c, i] of [[X3 - 450, AQUA, 0], [X3 + 450, ORNG, 1]]) {
      const m = S.ellC(bx, CT - 14, 66, 28); SK.wash(m, c, { seed: 474 + i, dx: 0, dy: 0 }); SK.ink(m, { w: 4.5, seed: 476 + i });
      const bw = S.path([['M', bx - 80, CT - 20], ['Q', bx - 76, CT + 22, bx, CT + 24], ['Q', bx + 76, CT + 22, bx + 80, CT - 20], ['Z']]);
      SK.wash(bw, '#ffffff', { seed: 478 + i, dx: 0, dy: 0 }); SK.ink(bw, { w: 5, seed: 480 + i });
    }
  }
  function blob(t) {
    if (t < M[1][1] - .3) return;
    const K = SK.kf(t, [[tSquish - .1, [95, 62, 0, 0, -170]], [tSquish + .25, [140, 34, 0, 0, -160]], [tStretch - .1, [140, 34, 0, 0, -160]], [tStretch + .3, [208, 40, .75, 24, -178]],
      [tPoke - .1, [208, 40, .75, 24, -178]], [tPoke + .25, [95, 62, 0, 0, -170]], [M[2][0], [95, 62, 0, 0, -170]], [M[2][0] + .35, [115, 36, 0, 0, CT - 36 - FLOOR]]], E.back);
    let [hw, th, pinch, sag, cy] = K;
    const k = E.back(inv(M[1][1] - .3, M[1][1] + .1, t));
    if (t > tSquish && t < tStretch) th += 6 * Math.sin((t - tSquish) * 14);
    const u = (t - tEvery) * 2.2, col = t < tEvery ? LIME : mix(GOO[(Math.floor(u) + 1) % 6], GOO[(Math.floor(u) + 2) % 6], E.inOut(u % 1));
    const x = t < M[2][0] ? starX(t) : X3, dent = 26 * Math.sin(Math.PI * inv(tPoke + .05, tPoke + .6, t));
    const tp = slimeShape(x, FLOOR + cy, hw * k, th * k, { pinch, sag, dent, col });
    const bk = inv(tPop, tPop + .35, t);
    if (bk > 0 && t < tPop + .38) { const br = 44 * E.out(bk), bb = S.ellC(x, tp[1] - br * .8, br, br); SK.alpha(.85, () => SK.wash(bb, mix(col, '#ffffff', .45), { seed: 490, dx: 0, dy: 0, tex: false })); SK.ink(S.ell(x, tp[1] - br * .8, br, br), { w: 4, seed: 491 }); }
    if (t > tPop + .38) SK.alpha(1 - tw(t, tPop + .7, tPop + 1.1), () => SK.spark(x, tp[1] - 36, 80, { col: PURP, p: inv(tPop + .38, tPop + .6, t), w: 9 }));
    if (t > tPoke && t < tPoke + .8) for (let i = 1; i <= 2; i++) SK.ink(S.arc(x, tp[1] + 4, 30 + i * 22, Math.PI * 1.15, Math.PI * 1.85), { w: 4, seed: 495 + i, dbl: false, alpha: 1 - inv(tPoke, tPoke + .8, t) });
  }
  function words3(t) {
    SK.alpha(1 - tw(t, tMake, tMake + .5), () => {
      sticker('SQUISH!', X3 - 480, -40, 100, PINK, inv(tSquish, tSquish + .45, t), { rot: -.07, seed: 21 });
      sticker('STRETCH!', X3 + 500, -40, 100, AQUA, inv(tStretch, tStretch + .45, t), { rot: .06, seed: 22 });
      sticker('POKE!', X3 - 480, 72, 100, YEL, inv(tPoke, tPoke + .45, t), { rot: .05, seed: 23 });
      sticker('POP!', X3 + 500, 72, 110, PURP, inv(tPop, tPop + .45, t), { rot: -.06, seed: 24 });
    });
    SK.txt('every color', X3 + 490, 0, { size: 96, col: C.textSoft, p: tw(t, tEvery, tEvery + .8, E.lin), seed: 25 });
    rainbowWord('RAINBOW!', X3 - 470, 0, 100, tRainbow - .05, t);
  }
  // stop 4 (line 5): the SLIME ZONE sign and the bucket that tips over the star
  function stop4(t) {
    const sx = X4 - 540;
    SK.ink(S.line(sx, FLOOR, sx, -40), { w: 10, seed: 500 });
    SK.at(sx, -100, .05 * Math.sin(t * 2), 1, () => {
      const bd = S.rrect(-170, -75, 340, 150, 18); SK.wash(bd, YEL, { seed: 501 }); SK.ink(bd, { w: 6, seed: 502 });
      SK.txt('SLIME', 0, -24, { size: 60, font: F, wt: 700, col: C.ink, seed: 503 }); SK.txt('ZONE!', 0, 36, { size: 60, font: F, wt: 700, col: C.ink, seed: 504 });
    });
    SK.ink(S.line(X4, -620, X4, -250), { w: 7, col: '#8a6a4a', seed: 505 });
    const wob = t > tWatch && t < tSlimed - .3 ? .1 * Math.sin((t - tWatch) * 11) : 0, tip = -2.3 * E.back(inv(tSlimed - .3, tSlimed + .05, t));
    SK.at(X4, -250, wob + tip, 1, () => {
      const full = 1 - tw(t, tSlimed - .1, tSlimed + .2);
      if (full > 0) SK.alpha(full, () => { const s = S.ellC(0, -84, 128, 26); SK.wash(s, LIME, { seed: 506, dx: 0, dy: 0 }); SK.ink(s, { w: 4.5, seed: 507 }); });
      const b = S.poly([[-135, -80], [135, -80], [105, 85], [-105, 85]], true); SK.wash(b, PURP, { seed: 508 }); SK.ink(b, { w: 6, seed: 509 });
      if (full > 0) SK.alpha(full, () => { const d = dripEdge(-60, 20, -80, [[-40, 38, 12]]); SK.wash([...d, [20, -90], [-60, -90]], LIME, { seed: 510, dx: 0, dy: 0 }); SK.ink(d, { w: 4, seed: 511 }); });
      SK.txt('SLIME', 0, 12, { size: 58, font: F, wt: 700, col: '#ffffff', stroke: 7, strokeCol: C.ink, seed: 512 });
      SK.ink(S.ell(0, 0, 14, 14), { w: 5, seed: 513, dbl: false });
    });
    const a = inv(tSlimed - .08, tSlimed + .1, t), b2 = inv(tSlimed + .45, tSlimed + .8, t);
    if (a > 0 && b2 < 1) {
      const y0 = -197, y1 = -72, ya = lerp(y0, y1, E.in(b2)), yb = lerp(y0, y1, E.out(a));
      if (yb - ya > 6) { const col = S.line(X4 - 58, ya, X4 - 40, yb); SK.ink(col, { w: 64, seed: 514, taper: false, dbl: false }); SK.ink(col, { w: 56, col: LIME, seed: 514, taper: false, dbl: false }); }
    }
    const sa = t - tSlimed - .12;
    if (sa > 0 && sa < 1) for (let i = 0; i < 10; i++) {
      const an = -Math.PI / 2 + (i - 4.5) * .32, v = 380 + rnd(i + 3) * 260, px = X4 - 40 + Math.cos(an) * v * sa, py = -60 + Math.sin(an) * v * sa + 1000 * sa * sa, r = 12 + rnd(i + 9) * 9;
      SK.alpha(1 - sa, () => { SK.wash(S.ellC(px, py, r, r * 1.1), LIME, { seed: 520 + i, dx: 0, dy: 0, tex: false }); SK.ink(S.ell(px, py, r, r * 1.1), { w: 3.5, seed: 530 + i, dbl: false }); });
    }
    sticker('WATCH OUT!', X4 + 470, -170, 96, ORNG, inv(tWatch, tWatch + .45, t), { rot: .06 + (t < tSlimed ? .03 * Math.sin(t * 22) : 0), seed: 41 });
    sticker('SLIMED!', X4 + 470, 20, 130, LIME, inv(tSlimed + .12, tSlimed + .55, t), { rot: -.05, seed: 42 });
  }
  function cake(x, y, s, t) { // the cake the star holds up: a candle a year (up to 9)
    if (s <= 0) return;
    SK.at(x, y, 0, s, () => {
      const bd = S.rrect(-88, -80, 176, 80, 14); SK.wash(bd, '#fff1f7', { seed: 600 }); SK.ink(bd, { w: 5, seed: 601 });
      const e = dripEdge(-92, 92, -58, [[-55, 16, 10], [-5, 26, 11], [45, 12, 9]]);
      SK.wash([...e, [92, -86], [-92, -86]], PINK, { seed: 602, dx: 0, dy: 0 }); SK.ink(e, { w: 4.5, seed: 603 }); SK.ink(S.line(-92, -86, 92, -86), { w: 4.5, seed: 604 });
      const n = Math.min(AGE, 9), sp = n > 1 ? Math.min(36, 150 / (n - 1)) : 0;
      Array.from({ length: n }, (_, i) => (i - (n - 1) / 2) * sp).forEach((cx, i) => {
        const cd = S.rrect(cx - 7, -122, 14, 36, 4); SK.wash(cd, GOO[(i + 1) % 6], { seed: 605 + i, dx: 0, dy: 0, tex: false }); SK.ink(cd, { w: 3.5, seed: 610 + i, dbl: false });
        const fs = 1 + .18 * Math.sin(t * 19 + i * 2), fl = S.path([['M', cx, -126], ['Q', cx - 11 * fs, -134, cx, -150 * (1 + (fs - 1) * .3) + 0], ['Q', cx + 11 * fs, -134, cx, -126]]);
        SK.wash(fl, '#ffb830', { seed: 615 + i, dx: 0, dy: 0, tex: false }); SK.ink(fl, { w: 3, seed: 620 + i, dbl: false });
      });
    });
  }
  function headline() { // the two lines as written; when a long name would set the first much smaller,
    // its last words move down to the second line, at the split that keeps both lines biggest
    if (HEAD.length < 2 || fit(HEAD[0], 112, 800) >= 112 * .85) return HEAD;
    const ws = HEAD.join(' ').split(/\s+/);
    let best = HEAD, bs = Math.min(fit(HEAD[0], 112, 800), fit(HEAD[1], 112, 800));
    for (let k = 1; k < ws.length; k++) {
      const a = ws.slice(0, k).join(' '), b = ws.slice(k).join(' '), s = Math.min(fit(a, 112, 800), fit(b, 112, 800));
      if (s > bs) { best = [a, b]; bs = s; }
    }
    return best;
  }
  // stop 5 (lines 6-7): the invitation -- the photo again, the headline, the venue, address, date
  // and time in one column between the photo and the star (each line fitted to it), the stamp
  function stop5(t) {
    photo(X5 - 540, -60, 230, t, E.back(inv(M[3][0] + .1, M[3][0] + .6, t)), 1, 7);
    const [h0, h1] = headline();
    if (h0) sticker(h0, X5 + 220, -292, fit(h0, 112, 800), PINK, inv(tNames - .1, tNames + .35, t), { rot: -.04, seed: 31 });
    if (h1) sticker(h1, X5 + 220, -182, fit(h1, 112, 800), AQUA, inv(tBday - .05, tBday + .4, t), { rot: .03, seed: 32 });
    const line = (str, y, size, col, t0, t1, seed) => { if (str) SK.txt(str, X5 + 200, y, { size: fit(str, size, 640), font: F, wt: 700, col, p: tw(t, tBday + t0, tBday + t1, E.lin), seed }); };
    line(VEN.name, -98, 50, C.text, .5, 1.2, 33);
    const ad = ADDR.filter(Boolean);
    line(ad[0], -50, 34, C.textSoft, .8, 1.5, 36);
    line(ad[1], -12, 34, C.textSoft, 1.0, 1.6, 37);
    const up = 38 * (2 - ad.length); // fewer address lines: the date and time move up
    line(WHEN.date, 46 - up, 48, DATE, 1.2, 1.8, 34);
    line(WHEN.time, 100 - up, 48, DATE, 1.5, 2.1, 35);
    const sk = inv(tInv - .12, tInv + .06, t);
    if (sk > 0 && INVITED) { // the stamp grows with its words, up to 620 wide (the star stands just right of it)
      const is = fit(INVITED, 70, 606, { ls: 2 }), sw = Math.max(610, measure(INVITED, is, { ls: 2 }) + 14);
      P.stamp(X5 + 200, 202, -.05, lerp(1.7, 1, E.out(sk)), [{ t: INVITED, y: 3, size: is, font: F, wt: 700 }], DATE, { w: sw, h: 130, fill: '#ffffff', alpha: clamp(sk * 2) });
    }
  }

  const BURSTS = [[tParty, 240, -80, 3], [tInv, X5 + 200, 60, 5], [tVenue, X5 - 300, -200, 7], [tVenue + .15, X5 + 520, -200, 9], [37.7, X5 + 100, -300, 11]];

  SK.film({
    duration: 40,
    camera,
    draw(t, vis) {
      sprinkles();
      SK.band(FLOOR, '#bde8df', { edge: 'flat', seed: 3 });
      const v = SK.view;
      for (let i = Math.floor(v.x0 / 640); i <= Math.ceil(v.x1 / 640); i++) { // slime puddles on the floor
        const px = i * 640 + rnd(i * 7 + 1) * 300, py = 380 + rnd(i * 5 + 2) * 60, rx = 80 + rnd(i * 3 + 4) * 70, pd = S.ellC(px, py, rx, rx * .16);
        SK.wash(pd, GOO[((i % 6) + 6) % 6], { seed: 720 + (i & 7), dx: 0, dy: 0 }); SK.ink(pd, { w: 4, seed: 730 + (i & 7) });
        SK.ink(S.line(px - rx * .5, py - rx * .06, px - rx * .15, py - rx * .09), { w: 5, col: 'rgba(255,255,255,.8)', seed: 740 + (i & 7), dbl: false });
      }
      if (vis(-900, -500, 900, 400)) stop1(t);
      if (vis(1400, -500, 3200, 400)) stop2(t);
      if (vis(3700, -500, 5100, 400)) stop3back(t);
      if (vis(5800, -700, 7400, 400)) stop4(t);
      if (vis(7900, -500, 9900, 400)) stop5(t);
      // the star, surfing on slime between the stops
      const k = pop(t, tCome, .5), x = starX(t), sl = slide(t);
      if (sl > .02) SK.alpha(sl, () => { const pd = S.ellC(x, FLOOR + 6, 120, 18); SK.wash(pd, LIME, { seed: 700, dx: 0, dy: 0 }); SK.ink(pd, { w: 4, seed: 701 }); });
      const ks = t - tSlimed - .4, jump = 140 * Math.sin(Math.PI * inv(tCome, tCome + .55, t)) + (ks > 0 && t < M[3][0] ? 34 * Math.abs(Math.sin(ks * 9)) : 0) + (t > tVenue ? 20 * Math.abs(Math.sin((t - tVenue) * 7)) : 0);
      const mouth = (t > tWatch && t < tSlimed + .15) ? 'o' : (sl > .05 || t < M[0][0] || (t > tSlimed + .15 && t < M[3][0]) || t > tVenue) ? 'big' : 'smile';
      const hands = STAR.draw(x, FLOOR, { s: .85 * k, t, arms: STAR.poseAt(t, POSES), shirt: AGE, mouth, lean: .2 * sl, jump, slimed: tw(t, tSlimed + .05, tSlimed + .3), wave: (t > tParty - .2 && t < M[0][0]) || (t > M[3][1] && t < tCeleb) ? t * 1.6 : undefined });
      if (vis(3700, -500, 5100, 400)) { counter(); blob(t); words3(t); }
      if (hands && t > tCeleb - .2) cake((hands.handF[0] + hands.handB[0]) / 2, hands.handF[1] + 8, .7 * E.back(inv(tCeleb - .2, tCeleb + .2, t)), t);
      ceiling(t);
      for (const [t0, bx, by, sd] of BURSTS) if (t > t0 && t < t0 + 2.2) P.confetti(bx, by, t - t0, { n: 60, seed: sd, cols: GOO, life: 2 });
    },
  });
})();
