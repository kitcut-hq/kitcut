// For: the birthday child's friends and their grown-ups; sunny, splashy, silly and irresistible
/* A birthday pool-party invitation (30 s, crayon on the blush ground), narrated by a bubbly kids'-TV
   host. One sunny backyard pool seen side-on (like an aquarium), the camera sliding left to right
   through two stops, then the invitation card rising out of the water.

   Everything that belongs to one party is SK.DATA.content (content.json): child (name, age, photo),
   when (date, time), where (place, address: either may be ""), copy (the film's words: the card's
   title is a pattern, {name} and {age} filled from child) and palette. Nothing of a particular
   party is written in this file, and anything long is fitted, never cut (fit() below).

   The clock hangs off the narration (vo.json, six lines; audio/vo/timeline.json is its recording).
   Every cue is w(line, word, fallbackSeconds): that word's start in the recording, or the fallback
   when the line does not say it. The words that name the party are worked out from the content
   (SAY below); the others are the narration's own words -- when a rewritten line drops a cue's
   word, point the cue at the word that now carries the beat.
     line 0  the greeting; who is turning <age>  stop 1, the diving board: the child waves on the
                                                 board, copy.hello writes on, the big age number
                                                 pops at the age word
     line 1  the name; the party at the 'pool'   the photo in a life ring pops at the name; the
                                                 theme title (rainbow letters) at 'pool'
     line 2  swimsuit, goggles, "... splash!"    bubbles with a swimsuit and goggles at 'swimsuit'
                                                 and 'goggles'; the board bounces harder from
                                                 'grab'; the jump leaves .72 s before 'splash' and
                                                 the cannonball lands on it (SPLASH!)
             (between lines 2 and 3)             S0..S1: the child bobs up in the donut float and
                                                 the camera paddles right to stop 2
     line 3  floaties, beach balls, cake         stop 2: the flamingo float pops up at 'floaties',
                                                 beach balls drop at 'beach' (one BONKs the child
                                                 .45 s later), the cake raft slides in at 'giant'
                                                 (the age on the cake), CAKE! at 'cake'
     line 4  'come' ...; the date (<day> ...);   C0 = .45 s before this line: the camera slides to
             the time (<hour> ...)               the card (C0..C1), which rises out of the water
                                                 between two splashes while the child paddles up
                                                 beside it; the title spells on, copy.line writes
                                                 on at 'come', the date at the weekday, the time at
                                                 the hour, the place lines just after the time
     line 5  'invited'; 'see' you there          the ribbon on top of the card and confetti at
                                                 'invited', two more bursts at 'see'; the camera
                                                 holds on the card to 30 s
   The music (score.json) and the effects (sfx.json, in seconds on the recorded narration) are
   files beside this one. */
(function () {
  'use strict';
  const { S, E, clamp, lerp, tw, TAU, rnd, P, inv } = SK;
  const w = (li, word, fb, n = 0) => SK.w(li, word, fb, 's', n);
  SK.setStyle('crayon');
  SK.setGround('blush');
  const C = SK.C, KID = SK.cast.kid, F = 'Balsamiq Sans';
  // ---------------------------------------------------------------- the party (content.json)
  const D = (SK.DATA && SK.DATA.content) || {};
  const CHILD = D.child || {}, WHEN = D.when || {}, WHERE = D.where || {}, COPY = D.copy || {}, PALS = D.palette || {};
  const NAME = String(CHILD.name ?? ''), AGE = String(CHILD.age ?? ''), PHOTO = CHILD.photo;
  const DATE = String(WHEN.date ?? ''), TIME = String(WHEN.time ?? '');
  const fill = (s) => String(s ?? '').replace(/\{name\}/g, NAME).replace(/\{age\}/g, AGE);
  const HELLO = fill(COPY.hello), THEME = fill(COPY.theme), LINE = fill(COPY.line), INVITED = fill(COPY.invited);
  const PLACE = [WHERE.place, WHERE.address].map((s) => String(s ?? '').trim()).filter(Boolean); // 0, 1 or 2 lines on the card
  const PAL = PALS.party || ['#ff5fa2', '#ffb52e', '#36c5f0', '#8fdc5a', '#a98bff', '#ff7a45'];
  const [PINK, SUN, AQUA, LIME, PURP, ORNG] = PAL;
  const LINE_COL = PALS.card_line || '#1a95c4', TIME_COL = PALS.card_time || '#e8457a';
  // the words of the narration that name the party, as it says them: the name's first word, the
  // age as a word, the date's first word (the weekday) and the start time's hour as a word. For a
  // narration that says them otherwise (a nickname, another language), write its words in here.
  const NUM = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve',
    'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty'];
  const HOUR = parseInt((TIME.match(/\d+/) || ['0'])[0], 10);
  const SAY = { name: NAME.split(/\s+/)[0], age: NUM[+AGE] ?? AGE, day: DATE.split(/\s+/)[0], hour: NUM[HOUR] ?? String(HOUR) };
  const WL = 200, DECK = 130, POOLX = -520, CX = 3000; // water line, deck, the pool's left wall, the card's x

  // ---------------------------------------------------------------- the clock (see the header)
  const tAge = w(0, SAY.age, 2.74), tName = w(1, SAY.name, 4.45), tPool = w(1, 'pool', 7.03);
  const tGrab = w(2, 'grab', 8.92), tSuit = w(2, 'swimsuit', 9.36), tGog = w(2, 'goggles', 10.26), tSplash = w(2, 'splash', 12.12);
  const tFloat = w(3, 'floaties', 14.41), tBeach = w(3, 'beach', 15.65), tGiant = w(3, 'giant', 16.67), tCake = w(3, 'cake', 17.81);
  const tCome = w(4, 'come', 19.48), tDay = w(4, SAY.day, 21.3), tHour = w(4, SAY.hour, 23.36), tInv = w(5, 'invited', 26.19), tSee = w(5, 'see', 27.17);
  // the jump, the float coming up (tUp), the slide to stop 2 (S0..S1) and to the card (C0..C1), the bonk
  const tLaunch = tSplash - .72, tUp = tSplash + .6, S0 = tUp + .15, S1 = S0 + 1.35, C0 = SK.line(4).start - .45, C1 = C0 + 1.1, tBonk = tBeach + .45;

  const camera = SK.camera([[0, [-80, -40, 1]], [tLaunch, [-50, -50, 1.04]], [tSplash + .3, [20, -30, 1]], [S0, [40, -30, 1]], [S1, [1300, -40, 1]],
    [C0, [1340, -40, 1.03]], [C1, [CX, -60, 1]], [30, [CX, -60, 1.04], E.sine]], [{ t: tSplash + .05, w: .16, amp: 10 }]);
  const FL = { F: [150, -205], B: [-150, -205] };
  const POSES = [[0, 'wave'], [tAge - .1, 'cheer'], [tName - .1, 'point'], [tPool - .1, 'cheer'], [tGrab, 'wide'], [tLaunch, 'cheer'], [tUp, FL], [tFloat, 'point'],
    [tBonk, 'uhoh'], [tGiant, FL], [tCake - .1, 'cheer'], [C0, FL], [C1 + .2, 'wave'], [tInv, 'cheer'], [tSee + .2, 'wave']];
  const floatX = (t) => SK.kf(t, [[S0, -100], [S1 + .2, 1050], [C0, 1050], [C1 + .3, 2215]]);
  const floatBob = (t) => 6 * Math.sin(t * 2.4) - 50 * Math.sin(Math.PI * inv(tUp, tUp + .45, t));

  // ---------------------------------------------------------------- little helpers
  // the type size that keeps str within maxW, never larger than size: long names and dates shrink
  function fit(str, size, maxW, font = F, wt = 700) {
    const ctx = SK.ctx(), f0 = ctx.font; ctx.font = `${wt} ${size}px "${font}"`;
    const wd = [...String(str)].reduce((a, c) => a + ctx.measureText(c).width, 0); ctx.font = f0;
    return wd > maxW ? size * maxW / wd : size;
  }
  function sticker(str, x, y, size, col, k, o = {}) { // chunky printed word: ink shadow, ink outline, colour
    if (k <= 0) return;
    SK.at(x, y, o.rot ?? 0, k >= 1 ? 1 : E.back(k), () => {
      SK.txt(str, 6, 7, { size, font: F, wt: 700, col: C.ink, stroke: size * .1, seed: o.seed ?? 5 });
      SK.txt(str, 0, 0, { size, font: F, wt: 700, col, stroke: size * .1, strokeCol: C.ink, seed: o.seed ?? 5 });
    });
  }
  function rainbowWord(str, x, y, size, t0, t, wob = 4, maxW = Infinity) { // letters pop on one by one, each a sticker
    size = fit(str, size, maxW);
    const ctx = SK.ctx(); ctx.font = `700 ${size}px "${F}"`;
    const ch = [...str], ws = ch.map((c) => ctx.measureText(c).width), tot = ws.reduce((a, b) => a + b, 0);
    let cx = x - tot / 2;
    ch.forEach((c, i) => { if (c !== ' ') sticker(c, cx + ws[i] / 2, y + Math.sin(t * 4 + i) * wob, size, PAL[i % 6], inv(t0 + i * .05, t0 + i * .05 + .35, t), { seed: 10 + i }); cx += ws[i]; });
  }
  const outIn = (t, a, b) => clamp(Math.min(inv(a, a + .35, t), 1 - inv(b, b + .3, t))); // pops in at a, out at b
  function balloons(x, y, t, seed) {
    for (let i = 0; i < 5; i++) {
      const bx = x + (i - 2) * 56 + (rnd(seed + i) - .5) * 20, by = y - 70 - (i % 2) * 64 - rnd(seed + 9 + i) * 26 + 6 * Math.sin(t * 1.7 + i);
      SK.ink(S.line(x, y + 110, bx, by + 50, 10), { w: 2.5, seed: seed + i, dbl: false, col: C.inkSoft });
      SK.wash(S.ellC(bx, by, 44, 52), PAL[(i + seed) % 6], { seed: seed + 10 + i, dx: 2, dy: 2 });
      SK.ink(S.ell(bx, by, 44, 52), { w: 4.5, seed: seed + 20 + i });
      SK.ink(S.arc(bx - 14, by - 16, 18, 3.5, 4.4), { w: 5, col: 'rgba(255,255,255,.8)', seed: seed + 30 + i, dbl: false });
    }
  }
  // ---------------------------------------------------------------- the backyard
  function yard(t, cx, cy, vis) {
    SK.sky('#4fc3f2', '#d6f4ff');
    P.sun(cx - 820, cy - 330, { r: 60, face: 'happy', rot: t * .3 });
    for (let k = -1; k <= 5; k++) { const x = k * 1000 + cx * .55 + 200; if (vis(x - 250, -600, x + 250, -300)) P.cloud(x, -360 + (k & 1) * 70, { s: .8, seed: 1500 + k * 3 }); }
    SK.band(-250, '#4fae5f', { edge: 'hills', amp: 35, len: 380, seed: 4 }); // the trees behind the fence
    const v = SK.view, x0 = Math.floor(v.x0 / 64) * 64, x1 = v.x1 + 64, top = [];
    for (let x = x0; x <= x1; x += 64) top.push([x, -205], [x + 32, -232]);
    SK.wash([...top, [x1, DECK], [x0, DECK]], '#eab07a', { seed: 8 }); SK.ink(top, { w: 4.5, seed: 9 });
    for (let x = x0; x <= x1; x += 64) SK.ink(S.line(x, -205, x, DECK), { w: 3, seed: 10 + ((x / 64) & 7), dbl: false, alpha: .55 });
    SK.ink(S.line(x0, -110, x1, -110), { w: 3, seed: 19, dbl: false, alpha: .45 });
    for (const [bx, by, sd] of [[-700, -250, 1], [-230, -250, 2], [1850, -250, 3], [CX - 640, -390, 4], [CX + 640, -390, 5]]) if (vis(bx - 200, by - 260, bx + 200, by + 120)) balloons(bx, by, t, sd);
    const sp = 760; // bunting across the top
    for (let k = Math.floor(v.x0 / sp); k <= Math.ceil(v.x1 / sp); k++) {
      const xa = k * sp; SK.ink(S.path([['M', xa, -545], ['Q', xa + sp / 2, -455, xa + sp, -545]]), { w: 3, seed: 20 + (k & 7), dbl: false });
      for (let i = 1; i < 10; i++) {
        const u = i / 10, fx = xa + sp * u, fy = -545 + 180 * u * (1 - u) + 2, fl = S.poly([[fx - 26, fy], [fx + 26, fy], [fx + 4 * Math.sin(t * 3 + i + k), fy + 56]], true);
        SK.wash(fl, PAL[((i + k) % 6 + 6) % 6], { seed: 30 + i, dx: 0, dy: 0 }); SK.ink(fl, { w: 3, seed: 40 + i, dbl: false });
      }
    }
    SK.band(DECK, '#f6e3bd', { edge: 'flat', seed: 5 });
  }
  function poolBack() { // the pool's far wall, and the ground beside it
    const v = SK.view, xa = Math.max(POOLX, v.x0 - 50), y1 = v.y1 + 60;
    if (POOLX > v.x0) SK.wash(S.poly([[v.x0 - 50, DECK], [POOLX, DECK], [POOLX, y1], [v.x0 - 50, y1]], true), '#e7c993', { seed: 50 });
    SK.wash(S.poly([[xa, DECK + 10], [v.x1 + 50, DECK + 10], [v.x1 + 50, y1], [xa, y1]], true), '#c9f1fb', { seed: 51, dx: 0, dy: 0 });
    for (let x = Math.ceil(xa / 70) * 70; x < v.x1; x += 70) SK.ink(S.line(x, DECK + 12, x, y1), { w: 2.5, col: '#8fd6e8', seed: 52, dbl: false, jit: .4 });
    for (let y = DECK + 80; y < y1; y += 70) SK.ink(S.line(xa, y, v.x1 + 50, y), { w: 2.5, col: '#8fd6e8', seed: 53, dbl: false, jit: .4 });
    SK.ink(S.line(xa, DECK + 10, v.x1 + 50, DECK + 10), { w: 5, seed: 54 });
    if (POOLX > v.x0) SK.ink(S.line(POOLX, DECK, POOLX, y1), { w: 5, seed: 55 });
  }
  function water(t) {
    const v = SK.view, xa = Math.max(POOLX, v.x0 - 50), xb = v.x1 + 50, top = [];
    for (let x = xa; x <= xb; x += 14) top.push([x, WL + 7 * Math.sin((x - t * 60) / 90) + 3 * Math.sin(x / 37 + t * 2)]);
    SK.wash([...top, [xb, v.y1 + 60], [xa, v.y1 + 60]], '#22b8e8', { seed: 56, alpha: .72, dx: 0, dy: 0 });
    SK.ink(top, { w: 4.5, seed: 57, col: '#0f7fb0' });
    for (let k = Math.floor(xa / 300); k * 300 < xb; k++) { const gx = k * 300 + 40 * Math.sin(t + k) + 120, gy = WL + 70 + (k & 1) * 110; if (gx > xa + 20) SK.ink(S.line(gx, gy, gx + 70, gy - 4), { w: 4, col: 'rgba(255,255,255,.65)', seed: 58 + (k & 3), dbl: false }); }
  }
  function splash(x, t0, t, big = 1) { // a crown of water, flying drops and ripples
    const a = t - t0; if (a < 0 || a > 1.5) return;
    const u = clamp(a / .8), h = 300 * big * Math.sin(Math.PI * u), wd = (80 + 130 * u) * big;
    if (u < 1) {
      const pts = [];
      for (let i = 0; i <= 12; i++) { const env = 1 - ((i - 6) / 7) ** 2; pts.push([x - wd + i * wd / 6, WL - h * env * (i % 2 ? 1 : .4)]); }
      const sh = S.poly([...pts, [x + wd, WL + 10], [x - wd, WL + 10]], true);
      SK.wash(sh, '#d9f6ff', { seed: 60, dx: 0, dy: 0, alpha: .92 }); SK.ink(S.poly(pts), { w: 4.5, col: '#0f7fb0', seed: 61 });
    }
    for (let i = 0; i < 16; i++) {
      const vx = (rnd(i + 3) - .5) * 900 * big, vy = (700 + rnd(i + 7) * 700) * big, px = x + vx * a, py = WL - 20 - vy * a + 1300 * a * a, r = 9 + rnd(i) * 9;
      if (py < WL + 10) { SK.wash(S.ellC(px, py, r, r * 1.2), '#bfefff', { dx: 0, dy: 0, tex: false }); SK.ink(S.ell(px, py, r, r * 1.2), { w: 3, col: '#0f7fb0', seed: 62 + (i & 3), dbl: false }); }
    }
    for (let k = 0; k < 3; k++) { const q = clamp(a / 1.2 - k * .15); if (q > 0 && q < 1) SK.ink(S.ell(x, WL + 6, (90 + 260 * q) * big, (14 + 22 * q) * big), { w: 4, col: '#ffffff', alpha: 1 - q, seed: 66 + k, dbl: false }); }
  }
  // ---------------------------------------------------------------- the floaties
  function donut(x, y, s) {
    SK.at(x, y, 0, s, () => {
      SK.wash(S.ellC(0, 0, 135, 48), '#ffd59a', { seed: 70 });
      const wav = []; for (let i = 0; i <= 24; i++) wav.push([132 - i * 11, 6 + 9 * Math.sin(i * 1.3)]);
      SK.wash([...S.arc(0, 0, 132, Math.PI, TAU, 46), ...wav], PINK, { seed: 71, dx: 0, dy: 0 });
      for (let i = 0; i < 9; i++) { const sx = -96 + i * 24, sy = -14 - 18 * rnd(i + 2), a = rnd(i + 5) * 3; SK.ink(S.line(sx, sy, sx + 12 * Math.cos(a), sy + 12 * Math.sin(a)), { w: 5, col: PAL[(i + 1) % 6 === 0 ? 2 : (i + 1) % 6], seed: 72 + i, dbl: false, taper: false }); }
      SK.ink(S.ell(0, 0, 135, 48), { w: 5, seed: 81 }); SK.ink(wav, { w: 3.5, seed: 82, dbl: false });
      SK.ink(S.arc(-30, -4, 80, Math.PI * 1.15, Math.PI * 1.42, 34), { w: 6, col: 'rgba(255,255,255,.8)', seed: 83, dbl: false });
    });
  }
  function ring(x, y, r, s, t, seed) { // the child's photo (child.photo: a cut-out, face centred) in a red-and-white life ring
    if (s <= 0) return;
    const ctx = SK.ctx(), R = r * 1.28;
    SK.at(x, y, .04 * Math.sin(t * 1.4 + seed), s, () => {
      for (let i = 0; i < 8; i++) { const a0 = i * TAU / 8 + .4, a1 = a0 + TAU / 8; ctx.fillStyle = i % 2 ? '#ffffff' : '#ff4f5e'; ctx.beginPath(); ctx.arc(0, 0, R, a0, a1); ctx.arc(0, 0, r * .96, a1, a0, true); ctx.closePath(); ctx.fill(); }
      ctx.save(); ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.clip(); ctx.fillStyle = '#fff3b8'; ctx.fillRect(-r, -r, 2 * r, 2 * r);
      SK.image(PHOTO, 0, r * .12, r * 2.15); ctx.restore();
      SK.ink(S.ell(0, 0, R, R), { w: 6, seed: 90 + seed }); SK.ink(S.ell(0, 0, r, r), { w: 5, seed: 91 + seed });
      SK.ink(S.arc(0, 0, r * 1.14, Math.PI * 1.1, Math.PI * 1.4), { w: 8, col: 'rgba(255,255,255,.75)', seed: 92 + seed, dbl: false });
    });
  }
  function ball(x, y, r, rot) {
    const ctx = SK.ctx(), cols = ['#ff4f5e', '#ffffff', SUN, '#ffffff', '#2f8fe0', '#ffffff'];
    SK.at(x, y, rot, 1, () => { for (let i = 0; i < 6; i++) { ctx.fillStyle = cols[i]; ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, r, i * TAU / 6, (i + 1) * TAU / 6); ctx.closePath(); ctx.fill(); } });
    SK.ink(S.ell(x, y, r, r), { w: 5, seed: 95 }); SK.ink(S.arc(x - r * .1, y - r * .1, r * .62, 3.5, 4.4), { w: 6, col: 'rgba(255,255,255,.85)', seed: 96, dbl: false });
  }
  function flamingo(x, y, s, t) {
    SK.at(x, y, .05 * Math.sin(t * 1.8), s, () => {
      const pk = '#ff8cc0', body = S.path([['M', -120, 0], ['Q', -130, -70, -30, -72], ['Q', 60, -74, 112, -40], ['L', 158, -84], ['Q', 150, -6, 100, 12], ['Q', 0, 32, -120, 0]]);
      SK.wash(body, pk, { seed: 100 }); SK.ink(body, { w: 5, seed: 101 });
      SK.ink(S.path([['M', -20, -36], ['Q', 30, -62, 70, -26]]), { w: 4, seed: 102, dbl: false });
      const neck = S.path([['M', -80, -50], ['Q', -160, -130, -100, -190], ['Q', -50, -240, -100, -262]]);
      SK.ink(neck, { w: 36, seed: 103, taper: false, dbl: false }); SK.ink(neck, { w: 27, col: pk, seed: 103, taper: false, dbl: false });
      const beak = S.poly([[-130, -282], [-178, -250], [-136, -262]], true); SK.wash(beak, '#ffffff', { seed: 104, dx: 0, dy: 0 }); SK.ink(beak, { w: 4, seed: 105, dbl: false });
      SK.wash(S.ellC(-108, -276, 32, 26), pk, { seed: 106, dx: 0, dy: 0 }); SK.ink(S.ell(-108, -276, 32, 26), { w: 4.5, seed: 107 });
      SK.wash(S.ellC(-102, -284, 5, 6), C.ink, { dx: 0, dy: 0, tex: false });
    });
  }
  function cakeRaft(x, y, s, t) {
    SK.at(x, y, .03 * Math.sin(t * 2), s, () => {
      const raft = S.rrect(-190, -34, 380, 64, 32); SK.wash(raft, SUN, { seed: 110 }); SK.ink(raft, { w: 5, seed: 111 });
      for (const xx of [-95, 0, 95]) SK.ink(S.line(xx, -30, xx, 26), { w: 3.5, seed: 112, dbl: false });
      for (const [x0, y0, ww, hh, col, i] of [[-130, -164, 260, 130, PINK, 0], [-90, -269, 180, 105, AQUA, 1]]) {
        const tier = S.rrect(x0, y0, ww, hh, 16); SK.wash(tier, col, { seed: 113 + i }); SK.ink(tier, { w: 5, seed: 115 + i });
        const ic = [[x0 + 4, y0 + 2], [x0 + ww - 4, y0 + 2]]; for (let k = 0; k <= 10; k++) ic.push([x0 + ww - k * ww / 10, y0 + 18 + (k % 3 === 1 ? 20 : 4)]);
        SK.wash(S.poly(ic, true), '#ffffff', { seed: 117 + i, dx: 0, dy: 0, tex: false }); SK.ink(S.poly(ic.slice(2)), { w: 3.5, seed: 119 + i, dbl: false });
        for (let k = 0; k < 6; k++) SK.wash(S.ellC(x0 + 26 + k * (ww - 52) / 5, y0 + hh * .66, 6, 6), PAL[(k + 1 + i) % 6], { dx: 0, dy: 0, tex: false });
      }
      sticker(AGE, 0, -312, fit(AGE, 96, 150), SUN, 1, { seed: 121 }); // the age, under the candle
      const fs = 1 + .15 * Math.sin(t * 17), fl = S.path([['M', 0, -362], ['Q', -16 * fs, -378, 0, -410 * fs + 0], ['Q', 16 * fs, -378, 0, -362]]);
      SK.wash(fl, ORNG, { seed: 122, dx: 0, dy: 0, tex: false }); SK.ink(fl, { w: 3.5, seed: 123, dbl: false });
    });
  }
  function icon(x, y, k, t, kind) { // a swimsuit or goggles in a bubble
    if (k <= 0) return;
    SK.at(x, y + 8 * Math.sin(t * 2.5 + x), 0, E.back(k), () => {
      SK.wash(S.ellC(0, 0, 105, 105), '#ffffff', { seed: 130, alpha: .9, dx: 0, dy: 0, tex: false }); SK.ink(S.ell(0, 0, 105, 105), { w: 5, seed: 131 });
      if (kind === 'suit') {
        const tr = S.poly([[-62, -42], [62, -42], [68, 44], [12, 44], [0, 14], [-12, 44], [-68, 44]], true);
        SK.wash(tr, ORNG, { seed: 132 }); SK.ink(tr, { w: 5, seed: 133 }); SK.ink(S.line(-62, -26, 62, -26), { w: 4, seed: 134, dbl: false });
        for (const sx of [-40, 40]) SK.ink(S.line(sx, -18, sx + (sx > 0 ? 8 : -8), 30), { w: 7, col: '#ffffff', seed: 135, dbl: false });
      } else {
        SK.ink(S.line(-80, -4, 80, -4), { w: 12, col: PINK, seed: 136, dbl: false, taper: false });
        for (const sx of [-36, 36]) { SK.wash(S.ellC(sx, 0, 32, 26), AQUA, { seed: 137 + sx, dx: 0, dy: 0, alpha: .9 }); SK.ink(S.ell(sx, 0, 32, 26), { w: 6, seed: 138 + sx }); SK.ink(S.arc(sx - 8, -6, 14, 3.6, 4.6), { w: 4, col: '#ffffff', seed: 139, dbl: false }); }
      }
    });
  }
  // ---------------------------------------------------------------- the card
  // its rows, [y, type size], beside the photo ring (text centred at x 228, at most CW wide): with
  // no place line as in the sample; with one or two (where.place, where.address) the rows close up
  const CW = 760, TW = 720; // a text row and the title (its letters carry a shadow) at most this wide
  const ROWS = [
    { title: [-140, 92], line: [-28, 72], date: [96, 78], time: [204, 86], place: [] },
    { title: [-165, 80], line: [-80, 60], date: [28, 66], time: [112, 72], place: [[196, 48]] },
    { title: [-170, 78], line: [-92, 56], date: [10, 62], time: [92, 66], place: [[168, 46], [222, 38]] },
  ][PLACE.length];
  function card(t) {
    const rise = SK.kf(t, [[C0 + .45, 780], [C1 + .25, 0, E.back]]);
    if (t < C0 + .45) return;
    SK.at(CX, -165 + rise, 0, 1, () => {
      const outer = S.rrect(-670, -315, 1340, 630, 40), inner = S.rrect(-646, -291, 1292, 582, 30);
      SK.wash(outer, AQUA, { seed: 140, dx: 8, dy: 8 }); SK.wash(inner, '#ffffff', { seed: 141, dx: 0, dy: 0, tex: false });
      SK.ink(outer, { w: 6, seed: 142 }); SK.dashes(S.rrect(-622, -267, 1244, 534, 24), { col: AQUA, w: 4, on: 3, off: 4 });
      for (let i = 0; i < 9; i++) { const fx = -150 + i * 95, fl = S.poly([[fx - 28, -262], [fx + 28, -262], [fx, -212]], true); SK.wash(fl, PAL[i % 6], { seed: 143 + i, dx: 0, dy: 0 }); SK.ink(fl, { w: 3, seed: 150 + i, dbl: false }); }
      SK.ink(S.line(-200, -262, 640, -262), { w: 3, seed: 160, dbl: false });
      ring(-405, 15, 172, 1, t, 3);
      const R = ROWS, title = fill(COPY.title);
      rainbowWord(title, 232, R.title[0], R.title[1], C1 - .35, t, 2, TW); // spells on as the card lands
      const show = (a) => clamp(inv(Math.max(a, C1 - .1), Math.max(a, C1 - .1) + .7, t)); // writes on at a, never before the card has landed
      const ls = fit(LINE, R.line[1], CW), k = ls / 72, wy = R.line[0] + 62 * k; // the wavy underline follows the line's size
      SK.txt(LINE, 228, R.line[0], { size: ls, font: F, wt: 700, col: LINE_COL, p: show(tCome), seed: 161 });
      SK.ink(S.path([['M', 228 - 288 * k, wy], ['Q', 228 - 144 * k, wy - 18 * k, 228, wy], ['Q', 228 + 144 * k, wy + 18 * k, 228 + 288 * k, wy]]), { w: 4, col: SUN, seed: 162, p: show(tCome + .3), dbl: false });
      SK.txt(DATE, 228, R.date[0], { size: fit(DATE, R.date[1], CW), font: F, wt: 700, col: C.ink, p: show(tDay - .05), seed: 163 });
      SK.txt(TIME, 228, R.time[0], { size: fit(TIME, R.time[1], CW), font: F, wt: 700, col: TIME_COL, p: show(tHour - .05), seed: 164 });
      PLACE.forEach((s, i) => { // the place in bold, the address under it in the soft ink
        const [y, size] = R.place[i];
        SK.txt(s, 228, y, { size: fit(s, size, CW, F, i ? 400 : 700), font: F, wt: i ? 400 : 700, col: i ? C.inkSoft : C.ink, p: show(tHour + .45 + .3 * i), seed: 175 + i });
      });
      const rk = inv(tInv - .1, tInv + .3, t);
      if (rk > 0) SK.at(0, -325, -.02, E.back(rk), () => { // the ribbon over the card's top edge
        const rb = S.path([['M', -330, -52], ['L', 330, -52], ['L', 300, 0], ['L', 330, 52], ['L', -330, 52], ['L', -300, 0], ['Z']]);
        SK.wash(rb, PINK, { seed: 165 }); SK.ink(rb, { w: 5, seed: 166 });
        SK.txt(INVITED, 0, 2, { size: fit(INVITED, 70, 520), font: F, wt: 700, col: '#ffffff', stroke: 7, strokeCol: C.ink, seed: 167 });
      });
    });
  }

  SK.film({
    duration: 30,
    camera,
    draw(t, vis) {
      const [cx, cy] = camera.at(t);
      yard(t, cx, cy, vis);
      poolBack();
      // ---- stop 1 (lines 0-2): the board, the greeting, the age, the photo ring, the theme title, the bubbles
      const A = lerp(14, 120, inv(tGrab - .4, tLaunch, t)), jumpB = t < tLaunch ? A * Math.abs(Math.sin(Math.PI * 1.6 * (t - tLaunch))) : 0;
      const la = t - tLaunch, d = t < tLaunch ? 22 * (1 - clamp(jumpB / 30)) * clamp(A / 40) : 22 * Math.exp(-5 * la) * Math.cos(22 * la);
      if (vis(-900, -600, 900, 300)) {
        const st = S.poly([[-860, DECK], [-840, 82], [-740, 82], [-720, DECK]], true); SK.wash(st, '#9aa7b8', { seed: 170 }); SK.ink(st, { w: 4.5, seed: 171 });
        const pl = S.path([['M', -880, 72], ['Q', -640, 72, -400, 72 + d]]);
        SK.ink(pl, { w: 30, seed: 172, taper: false, dbl: false }); SK.ink(pl, { w: 22, col: AQUA, seed: 172, taper: false, dbl: false });
        SK.txt(HELLO, 250, -390, { size: fit(HELLO, 124, 1100, SK.FONT_HAND), col: '#ffffff', stroke: 10, strokeCol: C.ink, p: clamp(.25 + .75 * inv(.5, 1.4, t)) * (1 - tw(t, tPool - .4, tPool - .1)), seed: 173 });
        if (t > tPool - .2 && t < tSplash) SK.alpha(1 - tw(t, tLaunch, tLaunch + .3), () => rainbowWord(THEME, 250, -395, 116, tPool - .15, t, 4, 1100));
        sticker(AGE, 570, -120, fit(AGE, 360, 330), ORNG, outIn(t, tAge - .05, tGrab - .2), { rot: .06 * Math.sin(t * 2.2), seed: 174 });
        ring(130, -110, 148, E.back(outIn(t, tName - .1, tGrab - .2)), t, 0);
        icon(170, -170, outIn(t, tSuit - .1, tLaunch - .1), t, 'suit'); icon(500, -170, outIn(t, tGog - .1, tLaunch - .1), t, 'goggles');
      }
      card(t);
      // ---- stop 2 (line 3): the floaties
      const fy = 220 * (1 - E.back(inv(tFloat - .15, tFloat + .3, t)));
      if (vis(1250, -400, 1800, 500)) flamingo(1500, WL + 12 + fy, .9, t);
      if (vis(1700, -500, 2700, 400)) cakeRaft(SK.kf(t, [[tGiant - .3, 2550], [tCake - .1, 1960, E.out], [C0, 1960], [C1, 1800]]), WL + 4, .92, t);
      // ---- the child: on the board, in the air, under water, then in the donut float
      const bob = floatBob(t), dx = t < tUp ? -100 : floatX(t);
      let lx, ly, s = .8, jump = 0, lean = 0;
      if (t < tLaunch) { lx = -440; ly = 57 + .8 * d; jump = jumpB; }
      else if (t < tSplash) { const u = inv(tLaunch, tSplash, t); lx = lerp(-440, -100, u); ly = lerp(57, 300, u) - 4 * 330 * u * (1 - u); lean = .35 * Math.sin(Math.PI * u); }
      else if (t < tUp) { lx = -100; ly = SK.kf(t, [[tSplash, 300], [tSplash + .3, 560, E.out], [tUp, WL + 98 + bob]]); s = lerp(.8, .7, inv(tSplash, tUp, t)); }
      else { lx = dx; ly = WL + 98 + bob; s = .7; }
      const kb = t - tBonk, sq = kb > 0 ? .1 * Math.exp(-4 * kb) * Math.sin(kb * 20) : 0;
      const waving = t < tAge - .1 || (t > C1 + .2 && t < tInv) || t > tSee + .2;
      const cheer = (t > tAge - .1 && t < tName - .1) || (t > tPool - .1 && t < tUp + .5) || (t > tCake - .1 && t < C0) || t > tInv;
      KID.draw(lx, ly, { s, t, arms: KID.poseAt(t, POSES), jump, lean, sq, mouth: kb > 0 && kb < .8 ? 'o' : cheer ? 'big' : 'smile', wave: waving ? t * 1.6 : undefined, age: AGE });
      donut(dx, WL + (t < tUp ? 6 * Math.sin(t * 2.4) + (t > tSplash ? 16 * Math.exp(-3 * (t - tSplash)) * Math.sin((t - tSplash) * 12) : 0) : bob), .72);
      water(t);
      // ---- on top of the water: wake, bubbles, splashes, beach balls, the words
      const vx = floatX(t + .05) - floatX(t);
      if (t > tUp && vx > 3) for (let k = 1; k <= 3; k++) SK.ink(S.arc(dx - 90 - k * 40, WL + 6, 30 + k * 14, Math.PI * .6, Math.PI * 1.4, 10 + k * 3), { w: 4, col: '#ffffff', seed: 180 + k, dbl: false, alpha: clamp(vx / 20) * (1 - k * .25) });
      if (t > tSplash && t < tSplash + 1.6) for (let i = 0; i < 8; i++) { const a = t - tSplash - i * .06, by = 520 - a * 380 - i * 10; if (a > 0 && by > WL + 15) SK.ink(S.ell(-100 + 40 * Math.sin(i * 2.3 + a * 5), by, 9 + i % 3 * 4, 9 + i % 3 * 4), { w: 3, col: '#ffffff', seed: 185 + i, dbl: false }); }
      splash(-100, tSplash, t, 1); splash(CX - 460, C0 + .62, t, .7); splash(CX + 460, C0 + .66, t, .7);
      sticker('SPLASH!', 330, -320, 150, AQUA, inv(tSplash + .05, tSplash + .45, t) * (1 - tw(t, S0 + .3, S0 + .7)), { rot: -.06 + .03 * Math.sin(t * 5), seed: 190 });
      if (t > tBeach - .2) {
        const ua = inv(tBonk, tBonk + .9, t), ay = t < tBonk ? lerp(-700, -60, E.in(inv(tBeach - .05, tBonk, t))) : lerp(-60, WL - 30, ua) - 4 * 280 * ua * (1 - ua) + (ua >= 1 ? 5 * Math.sin(t * 2.6) : 0);
        ball(t < tBonk ? 1055 : lerp(1055, 1290, ua) + (ua >= 1 ? 12 * Math.sin(t * .8) : 0), ay, 48, t * 3);
        for (const [bx, t0, sd] of [[690, tBeach + .1, 1], [1720, tBeach + .3, 2]]) { const a = t - t0; if (a > -.5) { const y = a < 0 ? lerp(-700, WL - 32, E.in(clamp(1 + a / .5))) : WL - 32 - 90 * Math.abs(Math.sin(a * 5)) * Math.exp(-3 * a) + 5 * Math.sin(t * 2.4 + sd); ball(bx, y, 44, t * (1 + sd)); } }
        sticker('BONK!', 1240, -230, 96, SUN, inv(tBonk, tBonk + .35, t) * (1 - tw(t, tBonk + 1.4, tBonk + 1.7)), { rot: .1, seed: 191 });
        if (kb > 0 && kb < 1.4) for (let i = 0; i < 4; i++) { const a = t * 5 + i * TAU / 4; SK.sparkle(1050 + Math.cos(a) * 80, -10 + Math.sin(a) * 22, 14, 1 - kb / 1.4, 192 + i, SUN); }
      }
      sticker('CAKE!', 1960, -300, 120, PINK, inv(tCake, tCake + .4, t) * (1 - tw(t, C0 + .1, C0 + .4)), { rot: -.05 + .03 * Math.sin(t * 4), seed: 196 });
      for (const [t0, bx, by, sd] of [[tInv, CX, -300, 3], [tSee + .3, CX - 450, -350, 5], [tSee + .45, CX + 450, -350, 7]]) if (t > t0 && t < t0 + 2.2) P.confetti(bx, by, t - t0, { n: 60, seed: sd, cols: PAL, life: 2 });
    },
  });
})();
