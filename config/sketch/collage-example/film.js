// For: curious adults scrolling YouTube and X; wry, brisk, polished newspaper-collage explainer
// A Brief History of Paperwork -- ten scenes, each a sheet of paper that slides over the last,
// every piece cued to the narrator's words. Built from sketch/collage.js.
SK.setStyle('collage');
SK.setGround('paper', { paper: '#e9e1cf' });
const { clamp, inv, E, S, TAU } = SK;
const w = (li, word, fb, n = 0) => SK.w(li, word, fb, 's', n);
const FB = [0.5, 5.1, 12.94, 20.4, 26.73, 33.43, 38.57, 42.65, 49.4, 53.22, 58.94];
const T = FB.map((f, i) => SK.line(i).start || f); // when each narration line starts
const DUR = 66;
const INK = '#1d1a17', RED = '#c63a32', CREAM = '#f6f1e4';

// the scenes: a start (its sheet begins to slide), the side it comes from, and its drawing
const at = (li) => T[li] - 0.15; // a sheet starts to slide just before its line
const SCENES = [];
const scene = (t0, from, draw) => SCENES.push({ t0, from, draw });

/* ---------------------------------------------------------------- shared pieces */
const SHEET = { x: 0, y: -30, w: 1840, h: 930 };
function page(col, o = {}) { SK.sheet(SHEET.x, SHEET.y, SHEET.w, SHEET.h, { col, seed: o.seed ?? 3, amp: 9, rim: 9, tex: 1.5, ...o }); }
// a page arrives composed: its chapter label, title and main picture ride in on the sheet, and
// only the details land later, on the words that name them
function chapter(n, t0, o = {}) {
  SK.tape('CHAPTER ' + n, o.x ?? -720, o.y ?? -415, { col: o.col ?? INK, size: 30 });
}
function title(text, t0, o = {}) {
  return SK.headline(text, o.x ?? -865, o.y ?? -318, { size: o.size ?? 124, col: o.col ?? INK, align: 'left', distress: .28, ...o });
}
const typed = (t, t0, n, cps = 14) => clamp((SK.step(t) - t0) / (n / cps));

/* ---------------------------------------------------------------- 0. the front page */
scene(0, null, (t) => {
  SK.rules(-880, 880, -498, { w: 5 });
  SK.headline('The Daily Form', 0, -405, { font: 'UnifrakturMaguntia', size: 158, distress: .22, in: { t: 0, type: 'rise', dist: 24 } });
  SK.headline('VOL. MMXXVI  ·  EST. 3100 B.C.  ·  PRICE: ONE SIGNATURE', 0, -318, { font: 'Old Standard TT', wt: 700, size: 27, ls: 3, in: { t: .25, type: 'fade' } });
  SK.rules(-880, 880, -290, { w: 4 });
  SK.halftone(640, 330, 640, 420, { col: '#e8577e', from: 'br', step: 17, in: { t: .6, type: 'fade' } });
  SK.burst(530, 40, 300, { col: '#ea5a82', spin: .08, in: { t: .9, type: 'pop' } });
  SK.cutout('papers', 530, 30, 330, { rot: .05, in: { t: 1.15, type: 'drop' } });
  SK.tape('SPECIAL REPORT', -640, -200, { col: INK, size: 36, in: { t: .6, type: 'slap' } });
  SK.headline('A Brief History of', -840, -108, { font: 'Playfair Display', italic: true, wt: 400, size: 70, align: 'left', in: { t: .85, type: 'rise' } });
  SK.tape('PAPERWORK', -380, 40, { font: 'Abril Fatface', wt: 400, size: 150, col: '#f3ce4f', ls: 3, padX: 36, padY: 6, distress: .3, rot: -.018, in: { t: 1.3, type: 'wipe', d: .45 } });
  SK.headline('From clay tablets to AI:\nfive thousand years of filling in the blanks.', -840, 215, { font: 'Old Standard TT', size: 38, align: 'left', lh: 1.25, in: { t: 2.2, type: 'rise' } });
  SK.stamp(215, 300, { top: 'SPECIAL', bottom: 'EDITION', text: 'EXTRA', r: 122, t: w(0, 'paperwork', 3.74) });
});

/* ---------------------------------------------------------------- I. Mesopotamia */
scene(at(1), 'l', (t, t0) => {
  page('#d6a960', { seed: 11 });
  chapter('I', t0);
  title('MESOPOTAMIA', t0);
  SK.stamp(735, -330, { top: 'CIRCA', text: '3100 BC', r: 112, t: w(1, 'thousand', 5.57) + .25, rot: .12 });
  SK.disc(-290, 20, 265, { col: '#f08a5d', seed: 21 });
  SK.cutout('tablet', -470, 150, 450, { rot: -.06 });
  const tr = w(1, 'receipts', 8.6);
  SK.layer({ x: -70, y: 350, rot: .025, in: { t: tr, type: 'drop', dist: 90 }, nudge: 1, w: 380, h: 110 }, () => {
    SK.sheet(0, 0, 380, 110, { col: '#fbf7ee', edges: '', shadow: { blur: 10, y: 4 } });
    SK.headline('THE FIRST RECEIPT', 0, -14, { font: 'Old Standard TT', wt: 700, size: 30, ls: 2, nudge: 0 });
    SK.headline('written in wet clay', 0, 26, { font: 'Old Standard TT', italic: true, size: 26, nudge: 0 });
  });
  SK.maskingTape(-230, 300, 120, { rot: -.5, in: { t: tr + .1, type: 'fade' } });
  SK.arrow(-60, 285, -230, 190, { in: { t: tr + .3, d: .35 }, bow: -40 });
  const tb = w(1, 'barley', 10.9), tbeer = w(1, 'beer', 11.8);
  SK.cutout('barley', 320, 50, 250, { rot: -.08, in: { t: tb, type: 'drop' } });
  SK.tape('BARLEY IN', 320, 270, { col: '#f3ce4f', size: 40, in: { t: tb + .15, type: 'slap' } });
  SK.cutout('jar', 660, 80, 250, { rot: .06, in: { t: tbeer, type: 'drop' } });
  SK.tape('BEER OUT', 660, 300, { col: '#e8577e', size: 40, in: { t: tbeer + .15, type: 'slap' } });
  SK.arrow(420, -90, 580, -80, { in: { t: w(1, 'out', 12.2), d: .3 }, bow: -34, w: 5 });
});

/* ---------------------------------------------------------------- II. Mainz, 1454 */
scene(at(2), 'r', (t, t0) => {
  page('#93cdb5', { seed: 12 });
  chapter('II', t0);
  title('MAINZ', t0);
  SK.stamp(-230, -330, { top: 'ANNO', bottom: 'DOMINI', text: '1454', r: 104, t: w(2, 'fifty-four', 14.21) + .15, rot: -.1 });
  SK.disc(-560, 150, 225, { col: '#e0463a', seed: 22 });
  SK.cutout('press', -575, 140, 440);
  const tf = w(2, 'forms', 16.4), tn = w(2, 'blanks', 18.7);
  SK.layer({ x: 250, y: 80, rot: -.02, in: { t: tf, type: 'drop', dist: 140 }, nudge: 1, w: 560, h: 660 }, () => {
    SK.sheet(0, 0, 560, 660, { col: '#f4ead2', edges: '', seed: 5, shadow: { blur: 16, y: 7 } });
    SK.headline('Litterae Indulgentiarum', 0, -250, { font: 'UnifrakturMaguntia', size: 46, col: '#2b2118', nudge: 0 });
    SK.headline('Universis Christifidelibus presentes\nlitteras inspecturis salutem in Domino.\nCum sanctissimus in Christo pater\nnoster dominus Nicolaus divina\nprovidentia papa quintus...', 0, -95, { font: 'Old Standard TT', italic: true, size: 25, lh: 1.3, col: 'rgba(43,33,24,.75)', nudge: 0 });
    for (const [lab, y] of [['Nomen', 110], ['Datum', 205]]) {
      SK.headline(lab + ':', -225, y, { font: 'Old Standard TT', wt: 700, size: 30, align: 'left', col: '#2b2118', nudge: 0 });
      SK.ctx().fillStyle = '#2b2118'; SK.ctx().fillRect(-95, y + 18, 310, 2.5);
    }
    SK.txt('Johannes', -80, 106, { font: 'Caveat', size: 58, col: '#1f3a8a', align: 'left', mode: 'type', p: typed(t, tn, 8, 18) });
    SK.txt('1454', -80, 203, { font: 'Caveat', size: 58, col: '#1f3a8a', align: 'left', mode: 'type', p: typed(t, tn + .55, 4, 14) });
  });
  SK.maskingTape(40, -245, 130, { rot: -.45, in: { t: tf + .2, type: 'fade' } });
  SK.maskingTape(470, -240, 130, { rot: .4, in: { t: tf + .25, type: 'fade' } });
  SK.cutout('printer', 740, 150, 320, { in: { t: w(2, 'printed', 15.56) + .1, type: 'pop' } });
  SK.tape('THE FIRST FILL-IN-THE-BLANK FORM', 250, -350, { col: INK, size: 30, in: { t: w(2, 'first', 16.0), type: 'slap' } });
  SK.mark(S.ell(95, 195, 205, 150, -2.2, .35, -.02), { in: { t: w(2, 'indulgences', 17.3), d: .5 }, w: 6 });
});

/* ---------------------------------------------------------------- III. the 1880s */
function copySheet(x, y, rot, col, lines, ink, o) {
  SK.layer({ x, y, rot, nudge: 1, w: 420, h: 540, ...o }, () => {
    SK.sheet(0, 0, 420, 540, { col, edges: '', seed: 7, shadow: { blur: 12, y: 5 } });
    lines.forEach((s, i) => SK.headline(s, -170, -200 + i * 44, { font: 'Courier Prime', wt: 700, size: 26, col: ink, align: 'left', nudge: 0 }));
    for (let i = 0; i < 6; i++) { SK.ctx().fillStyle = ink; SK.ctx().globalAlpha *= .35; SK.ctx().fillRect(-170, -40 + i * 44, 300 - (i % 3) * 50, 3); SK.ctx().globalAlpha /= .35; }
  });
}
scene(at(3), 't', (t, t0) => {
  page('#7eb1de', { seed: 13 });
  chapter('III', t0);
  title('THE 1880s', t0);
  SK.cutout('typewriter', -480, 140, 650);
  const tc = w(3, 'carbon', 23.0), t3 = w(3, 'one', 24.9);
  const fan = E.back(clamp((SK.step(t) - t3) / .45));
  copySheet(430 + 150 * fan, 110 + 10 * fan, .02 + .1 * fan, '#f6c1cf', ['FORM No. 3', 'TRIPLICATE'], '#4b3f8f', { in: { t: tc, type: 'none' } });
  copySheet(430 + 60 * fan, 100, .01 + .04 * fan, '#f7e7a1', ['FORM No. 2', 'DUPLICATE'], '#4b3f8f', { in: { t: tc, type: 'none' } });
  copySheet(430 - 50 * fan, 95, -.02 - .07 * fan, '#fbf8f0', ['FORM No. 1', 'ORIGINAL'], INK, { in: { t: tc, type: 'drop', dist: 120 } });
  SK.tape('CARBON COPY', 120, 350, { col: '#1d1a17', size: 34, in: { t: tc + .3, type: 'slap' } });
  SK.layer({ x: -40, y: -120, rot: -.04, in: { t: w(3, 'turned', 23.8), type: 'drop', dist: 80 }, nudge: 1, w: 330, h: 120 }, () => {
    SK.sheet(0, 0, 330, 120, { col: '#fbf8f0', edges: 'b', amp: 4, rim: 3, shadow: { blur: 8, y: 3 } });
    SK.headline(['one keystroke,', 'three copies.'].join('\n'), 0, 2, { font: 'Courier Prime', wt: 700, size: 30, lh: 1.15, nudge: 0 });
  });
  SK.maskingTape(-40, -178, 110, { rot: .08, in: { t: w(3, 'turned', 23.8) + .1, type: 'fade' } });
  SK.ransom('IN TRIPLICATE', 330, -330, { size: 62, in: { t: w(3, 'form', 25.2) }, stagger: .045 });
  SK.stamp(790, 300, { text: '1880s', top: 'THE', r: 98, t: w(3, 'eighteen-eighties', 20.8) + .5, rot: .14, col: '#2c4fa3' });
});

/* ---------------------------------------------------------------- IV. 1913 */
function form1040(t, t0, o) {
  SK.layer({ x: -420, y: 20, rot: -.012, nudge: 1, w: 820, h: 780, ...o }, () => {
    SK.sheet(0, 0, 820, 780, { col: '#fbf8f0', edges: '', seed: 9, shadow: { blur: 14, y: 6 } });
    SK.headline('FORM 1040', -370, -320, { size: 70, align: 'left', distress: .2, nudge: 0 });
    SK.headline('INCOME TAX', 360, -335, { font: 'Old Standard TT', wt: 700, size: 24, ls: 3, align: 'right', nudge: 0 });
    SK.headline('RETURN OF ANNUAL NET INCOME OF INDIVIDUALS', 0, -255, { font: 'Old Standard TT', wt: 700, size: 25, ls: 2, maxW: 740, nudge: 0 });
    const c = SK.ctx(); c.fillStyle = INK; c.fillRect(-380, -230, 760, 3); c.fillRect(-380, -222, 760, 1.2);
    const rows = ['1. Gross income', '2. General deductions', '3. Net income', '4. Dividends', '5. Amount of tax withheld', '6. Specific exemption'];
    rows.forEach((s, i) => {
      const y = -170 + i * 72;
      SK.headline(s, -370, y, { font: 'Old Standard TT', size: 27, align: 'left', nudge: 0 });
      c.fillStyle = 'rgba(29,26,23,.45)'; for (let x = 20; x < 250; x += 12) c.fillRect(x, y + 10, 5, 2);
      c.strokeStyle = INK; c.lineWidth = 2; c.strokeRect(265, y - 22, 110, 44);
    });
  });
}
scene(at(4), 'r', (t, t0) => {
  page('#efe7d6', { seed: 14 });
  const tf = w(4, 'Form', 28.95), t4 = w(4, 'four', 30.3);
  // the four pages: three more sheets slide out from under the first
  for (let k = 3; k >= 1; k--) SK.layer({ x: -420 + 26 * k, y: 20 + 20 * k, rot: -.012 + .012 * k, in: { t: t4 + .08 * (3 - k), type: 'slide', from: 'b', dist: 60, d: .3 } }, () => SK.sheet(0, 0, 820, 780, { col: '#f5f1e6', edges: '', seed: 20 + k, shadow: { blur: 12, y: 5 } }));
  form1040(t, t0, {});
  SK.sheet(540, -30, 760, 930, { col: '#ea5a84', edges: 'l', seed: 31, amp: 8, in: { t: t0 + .3, type: 'slide', from: 'r', dist: 900, d: .55 }, steps: 0 });
  chapter('IV', t0, { x: 300, col: '#fbf7ee' });
  SK.headline('1913', 540, -305, { size: 200, col: CREAM, distress: .25, in: { t: w(4, 'thirteen', 27.73), type: 'slap' } });
  SK.cutout('puzzled', 400, 165, 330, { in: { t: t0 + .55, type: 'pop' } });
  SK.cutout('spectacles', 740, 30, 250, { rot: .25, in: { t: t4 + .2, type: 'drop' } });
  SK.tape('4 PAGES', -560, 400, { col: '#f3ce4f', size: 44, in: { t: t4 + .3, type: 'slap' } });
  SK.mark(S.ell(-560, 400, 150, 58, -2.3, .3, -.03), { in: { t: t4 + .55, d: .4 } });
  SK.stamp(715, 345, { shape: 'rect', w: 340, h: 118, top: 'INSTRUCTIONS', text: 'INCLUDED', t: w(4, 'Instructions', 31.6) + .1, rot: -.08, col: INK });
});

/* ---------------------------------------------------------------- V. the fifties */
scene(at(5), 'l', (t, t0) => {
  page('#c9dfbd', { seed: 15 });
  SK.halftone(-640, -250, 620, 480, { col: '#6fae8f', from: 'tl', step: 18, in: { t: t0 + .5, type: 'fade' } });
  chapter('V', t0);
  title('THE FIFTIES', t0, { size: 112 });
  SK.cutout('cabinet', -650, 150, 330);
  SK.cutout('papers', -300, 205, 250, { rot: -.06, in: { t: w(5, 'offices', 34.81), type: 'drop' } });
  // three stamps, one per word, pressed by the rubber stamp itself
  const hits = [
    [w(6, 'Approved', 38.57) + .25, 80, 40, 'APPROVED', '#2e7d4f', -.1],
    [w(6, 'Denied', 40.09) + .2, 520, 170, 'DENIED', RED, .09],
    [w(6, 'Resubmit', 41.25) + .25, 210, 320, 'RESUBMIT', '#2c4fa3', -.05],
  ];
  // the ink is there the moment the stamp comes down; the stamp lifts off it and moves aside
  for (const [th, x, y, txt, col, rot] of hits) SK.stamp(x, y, { shape: 'rect', w: 420, h: 140, text: txt, col, rot, in: { t: th, type: 'fade', d: .04 } });
  const ts = w(5, 'rubber', 37.23);
  const keys = [[ts, [640, -170]]];
  for (const [th, hx, hy] of hits) {
    const last = keys[keys.length - 1][1];
    keys.push([th - .42, last], [th - .14, [hx + 25, hy - 265], E.inOut], [th, [hx + 25, hy - 192], E.in], [th + .1, [hx + 25, hy - 192]], [th + .42, [hx + 250, hy - 300], E.out]);
  }
  const [sx, sy] = SK.kf(SK.step(t), keys);
  SK.cutout('stamper', sx, sy, 220, { rot: .05, in: { t: ts, type: 'pop' } });
});

/* ---------------------------------------------------------------- VI. 1993, on screen */
function dialog(t, tt, o) {
  SK.place({ nudge: 1, ...o }, 700, 470, (c) => {
    c.save(); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 18; c.shadowOffsetY = 8;
    c.fillStyle = '#c3c3c3'; c.fillRect(-350, -235, 700, 470); c.restore();
    c.fillStyle = '#fff'; c.fillRect(-350, -235, 700, 3); c.fillRect(-350, -235, 3, 470);
    c.fillStyle = '#6d6d6d'; c.fillRect(-350, 232, 700, 3); c.fillRect(347, -235, 3, 470);
    const g = c.createLinearGradient(-344, 0, 344, 0); g.addColorStop(0, '#0a1f7a'); g.addColorStop(1, '#2f7fd0');
    c.fillStyle = g; c.fillRect(-342, -227, 684, 44);
    c.font = '700 24px "Courier Prime"'; c.fillStyle = '#fff'; c.textBaseline = 'middle'; c.fillText('form.pdf', -326, -205);
    for (let i = 0; i < 3; i++) { c.fillStyle = '#c3c3c3'; c.fillRect(252 + i * 30, -219, 24, 26); }
    const fields = [['Name:', 'JANE DOE', 0], ['Date:', '04/15/1996', .65], ['Tax ID:', '123-45-6789', 1.4]];
    fields.forEach(([lab, val, dt], i) => {
      const y = -110 + i * 105;
      c.font = '700 30px "Courier Prime"'; c.fillStyle = '#111'; c.fillText(lab, -310, y);
      c.fillStyle = '#fff'; c.fillRect(-120, y - 30, 420, 60);
      c.fillStyle = '#6d6d6d'; c.fillRect(-120, y - 30, 420, 3); c.fillRect(-120, y - 30, 3, 60);
      SK.txt(val, -104, y + 2, { font: 'Courier Prime', wt: 700, size: 32, col: '#111', align: 'left', mode: 'type', caret: true, p: typed(t, tt + dt, val.length, 16) });
    });
  });
}
scene(at(7), 'r', (t, t0) => {
  page('#3f9c9a', { seed: 16 });
  chapter('VI', t0, { col: CREAM });
  title('ON SCREEN', t0, { col: CREAM, size: 116 });
  SK.stamp(700, -330, { top: 'PORTABLE', bottom: 'DOCUMENT', text: '1993', r: 108, t: w(7, 'ninety-three', 43.86) + .3, col: '#f3ce4f', rot: .1, blend: 'source-over', alpha: .92 });
  SK.cutout('computer', -520, 150, 480);
  SK.cutout('floppy', -150, 300, 170, { rot: .3, in: { t: w(7, 'screens', 46.1) - .3, type: 'drop' } });
  dialog(t, w(7, 'Soon', 47.2), { x: 400, y: 70, rot: .015, in: { t: w(7, 'screens', 46.1) - .4, type: 'pop' } });
  SK.tape('TYPE IN THE BOXES', 400, 370, { col: '#f3ce4f', size: 34, in: { t: w(7, 'boxes', 48.5), type: 'slap' } });
});

/* ---------------------------------------------------------------- VII. 2000, no ink */
function signature(x0, y0, wd) {
  const pts = [], n = 320;
  for (let i = 0; i <= n; i++) {
    const u = i / n, k = u * TAU * 6.5;
    pts.push([x0 + u * wd + 24 * Math.cos(k + 1.3), y0 - (30 + 26 * Math.sin(u * 7)) * Math.sin(k) - 18 * Math.sin(u * TAU * 1.2)]);
  }
  for (let i = 1; i <= 40; i++) { const u = i / 40; pts.push([x0 + wd + 20 - u * (wd + 60), y0 + 40 + 16 * Math.sin(u * Math.PI)]); }
  return pts;
}
scene(at(8), 'l', (t, t0) => {
  page('#f2c94c', { seed: 17 });
  chapter('VII', t0);
  title('SIGN HERE', t0);
  SK.stamp(30, -325, { text: '2000', top: 'E-SIGN', r: 96, t: w(8, 'thousand', 50.16) + .2, rot: -.12 });
  SK.cutout('pda', -610, 150, 300, { rot: -.05 });
  SK.layer({ x: 250, y: 150, rot: .015, in: { t: w(8, 'signature', 50.74) - .35, type: 'drop', dist: 110 }, w: 860, h: 380 }, () => {
    SK.sheet(0, 0, 860, 380, { col: '#fbf8f0', edges: '', seed: 6, shadow: { blur: 14, y: 6 } });
    const c = SK.ctx(); c.fillStyle = INK; c.fillRect(-340, 90, 680, 3);
    SK.headline('X', -390, 55, { font: 'Old Standard TT', wt: 700, size: 60, nudge: 0 });
    SK.headline('Signature', -340, 125, { font: 'Old Standard TT', italic: true, size: 26, align: 'left', nudge: 0 });
  });
  SK.mark(signature(-60, 185, 560), { in: { t: w(8, 'signature', 50.74) + .1, d: 1.2 }, col: '#1f3a8a', w: 5, jit: .3 });
  SK.cutout('inkwell', 730, -120, 170, { rot: .08, in: { t: w(8, 'needed', 51.8) - .2, type: 'pop' } });
  const ti = w(8, 'ink', 52.3);
  SK.mark(S.line(650, -250, 810, 10), { in: { t: ti, d: .18 }, w: 12 });
  SK.mark(S.line(810, -250, 650, 10), { in: { t: ti + .18, d: .18 }, w: 12 });
});

/* ---------------------------------------------------------------- VIII. today */
const CHIPS = [
  ['NAME', -760, -190, '#8fc3ea'], ['DATE OF BIRTH', -40, -275, '#f3ce4f'], ['ADDRESS', -740, 345, '#7fcfb4'],
  ['TAX ID', 110, 360, '#b9a6dd'], ['SIGNATURE', 730, 350, '#e8577e'], ['EMAIL', 780, -150, '#f3ce4f'], ['POLICY No.', -360, 385, '#f6a86b'],
  ['INCOME', 800, 90, '#8fc3ea'], ['EMPLOYER', -790, 90, '#f3ce4f'],
];
scene(at(9), 'r', (t, t0) => {
  page('#f6f3ea', { seed: 18 });
  SK.halftone(-620, -260, 700, 460, { col: '#e8577e', from: 'tl', step: 17, in: { t: t0 + .5, type: 'fade' } });
  SK.halftone(640, 240, 640, 420, { col: '#7fcfb4', from: 'br', step: 17, in: { t: t0 + .6, type: 'fade' } });
  chapter('VIII', t0);
  SK.stamp(690, -350, { shape: 'rect', w: 390, h: 140, text: 'TODAY', t: w(9, 'Today', 53.22) + .15, rot: .05 });
  SK.cutout('laptop', -310, 70, 680);
  SK.cutout('robohand', 400, 100, 440, { in: { t: w(9, 'reads', 54.44) + .1, type: 'drop' } });
  SK.arrow(150, -40, 250, -10, { in: { t: w(9, 'form', 55.18), d: .3 }, bow: -30, w: 5 });
  const te = w(9, 'every', 56.2), tq = SK.step(t);
  CHIPS.forEach(([s, x, y, col], i) => {
    const tc = te - .35 + i * .13;
    const b = SK.tape(s, x, y, { col, size: 32, in: { t: tc, type: 'pop' } });
    if (tq > tc + .45) SK.check(x + b.w / 2 + 6, y - b.h / 2 + 4, 20, clamp((tq - tc - .45) / .3), { fill: '#2e9d57' });
  });
  SK.tape('IN SECONDS', 380, -210, { font: 'Abril Fatface', wt: 400, size: 64, col: INK, padX: 26, in: { t: w(9, 'seconds', 57.9) - .1, type: 'slap' } });
});

/* ---------------------------------------------------------------- the last page */
scene(at(10), 'l', (t, t0) => {
  SK.sheet(0, 0, 1990, 1130, { col: '#ece4d2', edges: 'r', seed: 19, amp: 9 });
  SK.rules(-880, 880, -498, { w: 5 });
  SK.headline('The Daily Form', 0, -405, { font: 'UnifrakturMaguntia', size: 158, distress: .22 });
  SK.headline('VOL. MMXXVI  ·  EST. 3100 B.C.  ·  PRICE: ONE SIGNATURE', 0, -318, { font: 'Old Standard TT', wt: 700, size: 27, ls: 3 });
  SK.rules(-880, 880, -290, { w: 4 });
  SK.disc(560, 90, 285, { col: '#7fcfb4', seed: 24 });
  SK.cutout('robohand', 560, 80, 380, { in: { t: t0 + .55, type: 'pop' } });
  SK.headline('5,000 years later...', -840, -175, { font: 'Playfair Display', italic: true, wt: 400, size: 60, align: 'left', in: { t: t0 + .6, type: 'rise' } });
  SK.headline('STILL PAPERWORK.', -840, -40, { size: 118, align: 'left', distress: .25, in: { t: w(10, 'still', 61.45), type: 'slap' } });
  SK.tape('JUST FASTER.', -470, 140, { font: 'Abril Fatface', wt: 400, size: 130, col: '#7fcfb4', ls: 2, padX: 34, padY: 4, distress: .3, rot: -.02, in: { t: w(10, 'Just', 62.9) - .05, type: 'wipe', d: .4 } });
  SK.stamp(720, 380, { shape: 'rect', w: 330, h: 120, text: 'THE END', t: 64.29, rot: -.07 }); // on the music's button
});

/* ---------------------------------------------------------------- the timeline along the bottom */
const YEARS = ['3100 BC', '1454', '1880s', '1913', '1950s', '1993', '2000', 'TODAY'];
const CH_T = [at(1), at(2), at(3), at(4), at(5), at(7), at(8), at(9)];
function ruler(t) {
  const tin = at(1) + .2, tout = at(10);
  if (t < tin || t > tout + .9) return;
  const up = E.out(clamp((t - tin) / .5)), down = E.in(clamp((t - tout) / .5));
  SK.layer({ x: 0, y: 150 * (1 - up) + 150 * down }, () => {
    SK.sheet(0, 494, 1900, 96, { col: '#f1ead9', edges: 't', seed: 41, amp: 4, rim: 4, shadow: { blur: 16, y: -2, col: 'rgba(40,25,10,.28)' } });
    const c = SK.ctx(), x0 = -780, dx = 1560 / 7;
    c.fillStyle = 'rgba(29,26,23,.6)';
    for (let x = -900; x <= 900; x += 1560 / 7 / 8) c.fillRect(x, 458, 2, Math.abs((x - x0) % dx) < 2 || Math.abs((x - x0) % dx - dx) < 2 ? 18 : 10);
    let k = 0; CH_T.forEach((ct, i) => { if (t >= ct + .45) k = i; });
    const mv = E.inOut(clamp((t - CH_T[k] - .45) / .5)); // the marker walks to the new year
    const mx = x0 + dx * (k === 0 ? 0 : SK.lerp(k - 1, k, mv));
    YEARS.forEach((s, i) => { c.font = `${i === k ? 700 : 500} 26px "Oswald"`; c.fillStyle = i === k && mv > .6 ? RED : 'rgba(29,26,23,.75)'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(s, x0 + dx * i, 505); });
    c.fillStyle = RED; c.beginPath(); c.moveTo(mx - 13, 446); c.lineTo(mx + 13, 446); c.lineTo(mx, 468); c.closePath(); c.fill();
  });
}

/* ---------------------------------------------------------------- the film */
SK.film({
  duration: DUR,
  camera: SK.camera([[0, [0, 0, 1]]]),
  fadeOut: .6,
  handheld: false,
  draw(t) {
    SK.newsprint({ heads: ['LOCAL NEWS', 'NOTICES', 'COMMERCE', 'LETTERS'], text: 'The clerk reports that the forms arrived in triplicate, as the regulation requires, and were filed in the green cabinet on the second floor. A notice is hereby given to all citizens that returns must be delivered before the fifteenth, signed in ink, with the receipt attached.' });
    SCENES.forEach((sc, i) => {
      const next = SCENES[i + 1], end = next ? next.t0 + .9 : DUR + 1;
      if (t < sc.t0 || t > end) return;
      if (!sc.from) return sc.draw(t, sc.t0);
      SK.layer({ in: { t: sc.t0, type: 'slide', from: sc.from, dist: sc.from === 't' ? 1150 : 2000, d: .7 }, steps: 0 }, () => sc.draw(t, sc.t0));
    });
    ruler(t);
  },
});
