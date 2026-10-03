// For: anyone with an offer worth one number -- a card, a discount, a free trial, a ticket, a pair of shoes
/* The offer ad: one big figure over the brand's own picture. 7 s, 60 fps, loops; 1:1 for a feed (1080 x 1080),
   9:16 for stories and reels, 16:9 for a page or a video ad -- one layout that re-measures itself per frame.

   Every word, picture and colour is in content.json (SK.DATA.content, read here as FACTS) and nothing of any
   one offer is in the code. The picture is a photo cover-fitted to the frame (or the brand's colour field when
   there is none), the words sit on one edge of it on a scrim that is MEASURED: the photo is sampled under the
   words and the scrim is only as dark as it takes for the text to reach 4.8:1, so a dark photo is left alone
   and a bright one is covered just enough.

   The clock (120 bpm, a beat is .5 s; the score and every sound are worked out from it, SK.film({sound})):
     0      the picture alone, already moving (it breathes in over the whole loop, so the end meets the start)
     .5     the product eases in; .75 the figure rises into place on beat 2
     1      the logo fades in
     2      the subline lands word by word; 3 the button pops (when there is one)
     6-6.8  everything leaves, the picture is alone again for the beat before the loop
   The length and the clock never change with the content. */
const FACTS = SK.DATA.content;
const W = SK.W, H = SK.H, E = SK.E, clamp = SK.clamp, lerp = SK.lerp, inv = SK.inv;
const DUR = 7.0, BPM = 120;
const FONT = "'Inter','Sofia Sans',system-ui,sans-serif";
const U = Math.min(W, H) / 1080; // one design unit: 1080 px of the short side
const WIDE = W > H * 1.2, TALL = H > W * 1.2;
const CLOCK = { prod: .5, fig: .75, logo: 1.0, sub: 2.0, legal: 2.3, cta: 3.0, out: 6.0 };

/* ------------------------------------------------------------------ the facts, read once */
const str = (v) => (v == null ? '' : String(v).trim());
const FIG = str(FACTS.figure);
const SUB = (Array.isArray(FACTS.subline) ? FACTS.subline : [FACTS.subline]).map(str).filter(Boolean).slice(0, 3);
const CTA = str(FACTS.cta), LEGAL = str(FACTS.legal);
const PHOTO = str(FACTS.photo);
const PRODUCT = FACTS.product && FACTS.product.image ? FACTS.product : null;
const LOGO = FACTS.logo && (FACTS.logo.image || FACTS.logo.light) ? FACTS.logo : null;
const BR = FACTS.brand || {};
const GROUND = /^#[0-9a-f]{6}$/i.test(BR.ground || '') ? BR.ground : '#10213F';
const ACCENT = /^#[0-9a-f]{6}$/i.test(BR.accent || '') ? BR.accent : '#E5484D';
const INK_IN = /^#[0-9a-f]{6}$/i.test(BR.ink || '') ? BR.ink : '#FFF8EC';
const NAME = str(BR.name);
const ANCHOR = FACTS.anchor === 'bottom' ? 'bottom' : 'top';
const FOCUS = Array.isArray(FACTS.focus) && FACTS.focus.length === 2 ? FACTS.focus.map((v) => clamp(+v || 0)) : [.5, .5];

/* ------------------------------------------------------------------ colour */
function rgbOf(hex) { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
const lin = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
const lumRGB = (r, g, b) => .2126 * lin(r) + .7152 * lin(g) + .0722 * lin(b);
const lumOf = (hex) => lumRGB(...rgbOf(hex));
const contrast = (a, b) => { const x = lumOf(a), y = lumOf(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
function mixHex(a, b, u) { const x = rgbOf(a), y = rgbOf(b); return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * u).toString(16).padStart(2, '0')).join(''); }
const rgba = (hex, a) => { const [r, g, b] = rgbOf(hex); return `rgba(${r},${g},${b},${a})`; };
const DARK = '#0E1220';

/* ------------------------------------------------------------------ the layout, measured once (fonts and pictures are loaded by the first frame) */
let L_ = null;
function layout() {
  if (L_) return L_;
  const c = SK.ctx();
  const photoIm = PHOTO ? SK.IMG[PHOTO] : null;
  const prodIm = PRODUCT ? SK.IMG[PRODUCT.image] : null;
  const logoIm = LOGO ? SK.IMG[LOGO.image] || SK.IMG[LOGO.light] : null;
  const hasPhoto = !!photoIm;
  const mw = (s, size, wt, ls = 0) => { c.font = `${wt} ${size}px ${FONT}`; c.letterSpacing = ls + 'px'; const w = c.measureText(s).width; c.letterSpacing = '0px'; return w; };
  c.font = `800 100px ${FONT}`;
  const CAPR = c.measureText('H').actualBoundingBoxAscent / 100 || .73;

  // the colours the words wear on this ground (with a photo they are settled after it is sampled: scrims())
  const field = hasPhoto ? mixHex(GROUND, '#000000', .7) : GROUND;
  let ink = INK_IN;
  if (!hasPhoto && contrast(GROUND, ink) < 7) ink = contrast(GROUND, DARK) > contrast(GROUND, ink) ? DARK : ink;
  const figCol = !hasPhoto && contrast(ACCENT, GROUND) >= 3 ? ACCENT : ink;
  const ctaFill = hasPhoto ? ACCENT : contrast(ACCENT, GROUND) >= 1.8 ? ACCENT : ink;
  const ctaInk = contrast(ctaFill, '#FFFFFF') > contrast(ctaFill, DARK) ? '#FFFFFF' : DARK;

  // the frame's own margins; a vertical frame keeps clear of the app's top bar and bottom controls
  const M = (WIDE ? 104 : 76) * U, topM = (TALL ? 240 : WIDE ? 84 : 80) * U, botM = (TALL ? 330 : WIDE ? 60 : 56) * U;
  const zoneMax = (hasPhoto ? (TALL ? 760 : WIDE ? 640 : 520) : TALL ? 1160 : WIDE ? 700 : 640) * U;
  const STACK = TALL && !!prodIm; // a vertical frame has the width for the figure, so the product sits above the words

  // the product
  let pw = 0, ph = 0;
  if (prodIm) {
    const asp = prodIm.width / prodIm.height;
    const mxW = STACK ? .5 * W : (WIDE ? 400 : 300) * U * (hasPhoto ? 1 : 1.1), mxH = STACK ? .3 * zoneMax : .84 * zoneMax;
    ph = Math.min(mxH, mxW / asp); pw = ph * asp;
  }
  const align = FACTS.align === 'center' && (!prodIm || STACK) ? 'center' : 'left';
  const gap = 56 * U;
  const x0 = M + (prodIm && !STACK ? pw + gap : 0);
  let rw = W - M - x0;
  if (WIDE && !prodIm) rw = Math.min(rw, W * .62);
  const tx = align === 'center' ? W / 2 : x0, ta = align === 'center' ? 'center' : 'left';

  // the figure: one line that fits, or two when a long one would shrink to nothing
  const capMax = (STACK ? .3 : hasPhoto ? .46 : .52) * zoneMax;
  const figSize = (lines) => {
    const wmax = Math.max(...lines.map((s) => mw(s, 100, 800, -3))), n = lines.length;
    return Math.min(rw / wmax * 100, capMax / (CAPR * n + .2 * (n - 1)));
  };
  let figLines = FIG ? FIG.split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 2) : [];
  if (figLines.length === 1) {
    const words = figLines[0].split(/\s+/);
    let best = { size: figSize(figLines), lines: figLines };
    for (let i = 1; i < words.length; i++) {
      const cand = [words.slice(0, i).join(' '), words.slice(i).join(' ')], size = figSize(cand);
      if (size > best.size * 1.25 && size > best.size) best = { size, lines: cand };
    }
    figLines = best.lines;
  }
  const FS = figLines.length ? figSize(figLines) : 0;
  const capH = CAPR * FS, figGap = .2 * FS;
  const figH = figLines.length ? capH * figLines.length + figGap * (figLines.length - 1) : 0;
  const figW = figLines.length ? Math.max(...figLines.map((s) => mw(s, FS, 800, -.03 * FS))) : 0;

  // the subline: words with a weight each; fitted to the column, wrapped only when fitting would make it small
  const parse = (s) => {
    const parts = s.split('*'), mark = parts.length > 1, ws = [];
    parts.forEach((seg, i) => seg.split(/\s+/).filter(Boolean).forEach((w) => ws.push({ w, bold: mark ? i % 2 === 1 : true })));
    return ws;
  };
  let subLines = SUB.map(parse);
  const SMAX = (hasPhoto ? 56 : 60) * U * (WIDE ? 1.15 : 1);
  const lineW = (ws, s) => ws.reduce((a, x) => a + mw(x.w, s, x.bold ? 700 : 300), 0) + mw(' ', s, 300) * Math.max(0, ws.length - 1);
  let SS = SMAX;
  if (subLines.length) {
    const wmax = Math.max(...subLines.map((ws) => lineW(ws, 100)));
    SS = Math.min(SMAX, rw / wmax * 100);
    if (SS < .55 * SMAX) { // wrap greedily at the floor size
      SS = .55 * SMAX;
      const out = [];
      subLines.forEach((ws) => {
        let cur = [];
        ws.forEach((x) => { if (cur.length && lineW(cur.concat(x), SS) > rw) { out.push(cur); cur = []; } cur.push(x); });
        if (cur.length) out.push(cur);
      });
      subLines = out.slice(0, 5);
    }
  }
  const pitch = SS * 1.26, subH = subLines.length ? pitch * subLines.length - (pitch - SS * .73) + SS * .26 : 0;
  const subW = subLines.length ? Math.max(...subLines.map((ws) => lineW(ws, SS))) : 0;
  const subGap = figLines.length && subLines.length ? Math.max(.17 * FS, 40 * U) : 0;

  // the button
  const cs = 30 * U, ctaW = CTA ? mw(CTA, cs, 700) + 76 * U : 0, ctaH = CTA ? 70 * U : 0;
  const ctaGap = CTA && (figLines.length || subLines.length) ? 40 * U : 0;
  const textH = figH + subGap + subH + ctaGap + ctaH;
  const textW = Math.max(figW, subW, ctaW);

  // the foot: the logo and the fine print, on the bottom edge (the logo moves up when the words are low)
  let lw = 0, lh = 0;
  if (logoIm) { const asp = logoIm.width / logoIm.height, mxW = (WIDE ? 230 : 200) * U, mxH = 84 * U; lh = Math.min(mxH, mxW / asp); lw = lh * asp; }
  else if (NAME) { lh = 40 * U; lw = mw(NAME, lh, 800); }
  const legalSize = (TALL ? 23 : 20) * U, legalMaxW = W - 2 * M - (lw && ANCHOR === 'top' ? lw + 44 * U : 0);
  let legalLines = [];
  if (LEGAL) {
    let cur = '';
    LEGAL.split(/\s+/).forEach((w) => { const t = cur ? cur + ' ' + w : w; if (cur && mw(t, legalSize, 400) > legalMaxW) { legalLines.push(cur); cur = w; } else cur = t; });
    if (cur) legalLines.push(cur);
    legalLines = legalLines.slice(0, 3);
  }
  const legalPitch = legalSize * 1.4, legalH = legalLines.length ? legalPitch * legalLines.length : 0;
  const footBottom = H - botM, footH = Math.max(legalH, ANCHOR === 'top' ? lh : 0);

  // where it all sits
  const zoneH = STACK ? ph + gap + textH : Math.max(ph, textH);
  let zoneTop;
  if (!hasPhoto) {
    const room = footBottom - (footH ? footH + 36 * U : 0);
    zoneTop = clamp((H - zoneH) / 2 - .02 * H, topM, Math.max(topM, room - zoneH));
  } else if (ANCHOR === 'top') zoneTop = topM;
  else zoneTop = footBottom - (legalH ? legalH + 36 * U : 0) - zoneH;
  const place = (h) => (hasPhoto && ANCHOR === 'top' ? zoneTop : zoneTop + (zoneH - h) / 2); // the shorter block centres on the taller
  const textTop = STACK ? zoneTop + ph + gap : place(textH), prodTop = STACK ? zoneTop : place(ph);
  const prodX = STACK && align === 'center' ? (W - pw) / 2 : M;
  const logoX = W - M - lw, logoY = ANCHOR === 'top' ? footBottom - lh : topM;
  const logoDarkVariant = !!LOGO && LOGO.image && LOGO.light && !hasPhoto && lumOf(GROUND) > .45;

  const Lay = {
    c, hasPhoto, photoIm, prodIm, logoIm, field, ink, figCol, ctaFill, ctaInk, M, topM, botM, pw, ph, tx, ta, rw, mw,
    figLines, FS, capH, figGap, figH, figW, subLines, SS, pitch, subH, subW, subGap, cs, ctaW, ctaH, ctaGap, textH, textW,
    lw, lh, legalSize, legalLines, legalPitch, legalH, footBottom, zoneTop, zoneH, textTop, prodTop, logoX, logoY, logoDarkVariant,
    prodX, round: PRODUCT ? Math.max(0, +PRODUCT.round || 0) * U : 0,
  };
  // the words' own box and the foot's, on the frame: where the photo is sampled for the scrim
  Lay.textBox = [ta === 'center' ? tx - textW / 2 : tx, textTop, textW, textH];
  Lay.footBox = [M, ANCHOR === 'top' ? footBottom - footH : footBottom - legalH, W - 2 * M, Math.max(footH, 1)];
  Lay.logoBox = [logoX, logoY, lw, lh];
  Lay.legalBox = [M, footBottom - legalH, W - 2 * M - (lw && ANCHOR === 'top' ? lw + 44 * U : 0), Math.max(legalH, 1)];
  if (hasPhoto) scrims(Lay);
  L_ = Lay;
  return Lay;
}

/* ------------------------------------------------------------------ the photo and its scrim */
function photoGeom(Lay) {
  const im = Lay.photoIm, s0 = Math.max(W / im.width, H / im.height);
  const pw = im.width * s0, ph = im.height * s0;
  return { s0, pw, ph, dx: -(pw - W) * FOCUS[0], dy: -(ph - H) * FOCUS[1], px: W * FOCUS[0], py: H * FOCUS[1] };
}
function scrims(Lay) {
  // the photo at its middle zoom, small, on an offscreen canvas: the pixels the words will sit on
  const k = 256 / Math.max(W, H), cw = Math.round(W * k), ch = Math.round(H * k);
  const cv = document.createElement('canvas'); cv.width = cw; cv.height = ch;
  const g = cv.getContext('2d', { willReadFrequently: true }), G = photoGeom(Lay), z = 1.025;
  g.scale(k, k); g.translate(G.px, G.py); g.scale(z, z); g.translate(-G.px, -G.py);
  g.drawImage(Lay.photoIm, G.dx, G.dy, G.pw, G.ph);
  const data = g.getImageData(0, 0, cw, ch).data;
  const pixels = (box) => {
    const x0 = clamp(Math.floor(box[0] * k), 0, cw - 1), x1 = clamp(Math.ceil((box[0] + box[2]) * k), x0 + 1, cw);
    const y0 = clamp(Math.floor(box[1] * k), 0, ch - 1), y1 = clamp(Math.ceil((box[1] + box[3]) * k), y0 + 1, ch);
    const px = [];
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const i = (y * cw + x) * 4; px.push([data[i], data[i + 1], data[i + 2]]); }
    return px;
  };
  // Two ways to make words legible on a picture: light words on a dark veil, or dark words on a light one.
  // Each is solved for the smallest veil under which the 94th-percentile worst pixel of the box meets the ratio;
  // the one that needs less veil wins (light words unless dark ones are clearly gentler on the picture).
  const lightInk = lumOf(INK_IN) > .5 ? INK_IN : '#FFF8EC';
  const veilDark = mixHex(GROUND, '#000000', .7), veilLight = mixHex(GROUND, '#FFFFFF', .94);
  const solve = (box, ratio, allowDark) => {
    const px = pixels(box);
    const lum = (a, v) => px.map(([r, gg, b]) => lumRGB(r * (1 - a) + v[0] * a, gg * (1 - a) + v[1] * a, b * (1 - a) + v[2] * a)).sort((p, q) => p - q);
    const hiPct = (a) => { const v = lum(a, rgbOf(veilDark)); return v[Math.min(v.length - 1, Math.floor(v.length * .94))]; };
    const loPct = (a) => { const v = lum(a, rgbOf(veilLight)); return v[Math.floor(v.length * .06)]; };
    const wantHi = (lumOf(lightInk) + .05) / ratio - .05, wantLo = (lumOf(DARK) + .05) * ratio - .05;
    let aL = .92, aD = allowDark ? .92 : 9;
    for (let a = 0; a <= .92; a += .02) if (hiPct(a) <= wantHi) { aL = a; break; }
    if (allowDark) for (let a = 0; a <= .92; a += .02) if (loPct(a) >= wantLo) { aD = a; break; }
    const dark = allowDark && aD < aL - .12;
    return dark ? { dark, a: Math.max(.08, aD), ink: DARK, veil: veilLight } : { dark, a: Math.max(.14, aL), ink: lightInk, veil: veilDark };
  };
  // the words; and the foot (the fine print needs 4.8:1, a logo alone 3:1; a logo that comes in one tone cannot flip)
  let tBox = Lay.textBox;
  if (ANCHOR === 'bottom' && Lay.legalLines.length) { // the fine print sits under the words on the same edge
    const lb = Lay.legalBox, y1 = Math.max(tBox[1] + tBox[3], lb[1] + lb[3]);
    tBox = [Math.min(tBox[0], lb[0]), tBox[1], Math.max(tBox[2], lb[2]), y1 - tBox[1]];
  }
  const ts = solve(tBox, 4.8, true);
  const footBox = ANCHOR === 'top' ? Lay.footBox : Lay.logoBox;
  const twoTone = !!(LOGO && LOGO.image && LOGO.light && LOGO.image !== LOGO.light);
  const fs = solve(footBox, Lay.legalLines.length ? 4.8 : 3.0, !LOGO || twoTone);
  Lay.ink = ts.ink; Lay.inkFoot = fs.ink; Lay.shadowT = ts.dark ? 'light' : 'dark'; Lay.shadowF = fs.dark ? 'light' : 'dark';
  Lay.figCol = Lay.ink; Lay.ctaFill = contrast(ACCENT, ts.veil) >= 1.8 ? ACCENT : Lay.ink;
  Lay.ctaInk = contrast(Lay.ctaFill, '#FFFFFF') > contrast(Lay.ctaFill, DARK) ? '#FFFFFF' : DARK;
  Lay.logoDarkVariant = fs.dark;
  Lay.scrimInfo = { text: ts, foot: fs };
  // each edge's veil: constant over the box it serves, then rolling off
  Lay.edges = ANCHOR === 'top'
    ? [{ edge: 'top', ...ts, to: tBox[1] + tBox[3] }, { edge: 'bottom', ...fs, to: H - footBox[1] }]
    : [{ edge: 'bottom', ...ts, to: H - tBox[1] }, { edge: 'top', ...fs, to: footBox[1] + footBox[3] }];
}

/* ------------------------------------------------------------------ drawing */
const ramp = (t, a, d, e = E.out) => e(inv(a, a + d, t));
const leave = (t, a, d = .45) => 1 - E.inOut(inv(a, a + d, t));
function drawScrim(Lay, t) {
  const c = Lay.c, sc = ramp(t, .05, 1.0) * leave(t, CLOCK.out + .1, .75);
  for (const e of Lay.edges) {
    const a = e.a * sc; if (a <= 0.003) continue;
    const roll = .2 * H, solid = Math.min(H, e.to + 24 * U), top = e.edge === 'top';
    const y0 = top ? 0 : H, y1 = top ? Math.min(H, solid + roll) : Math.max(0, H - solid - roll);
    const gr = c.createLinearGradient(0, y0, 0, y1), s = (solid) / Math.abs(y1 - y0);
    gr.addColorStop(0, rgba(e.veil, a)); gr.addColorStop(clamp(s), rgba(e.veil, a));
    gr.addColorStop(1, rgba(e.veil, 0));
    c.fillStyle = gr; c.fillRect(0, 0, W, H);
  }
}
function drawField(Lay, t) {
  const c = Lay.c, ph = Math.sin(t / DUR * Math.PI * 2), ph2 = Math.cos(t / DUR * Math.PI * 2);
  const g = c.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, mixHex(GROUND, '#FFFFFF', .06)); g.addColorStop(1, mixHex(GROUND, '#000000', .35));
  c.fillStyle = g; c.fillRect(0, 0, W, H);
  const R = Math.max(W, H);
  const glow = c.createRadialGradient(W * .78 + ph * 40 * U, H * .28 + ph2 * 30 * U, 0, W * .78, H * .28, R * .75);
  glow.addColorStop(0, rgba(ACCENT, .42)); glow.addColorStop(.55, rgba(ACCENT, .12)); glow.addColorStop(1, rgba(ACCENT, 0));
  c.fillStyle = glow; c.fillRect(0, 0, W, H);
  c.save(); c.strokeStyle = rgba(Lay.ink, .09); c.lineWidth = 2 * U;
  for (let i = 0; i < 3; i++) { c.beginPath(); c.arc(W * .1 - ph2 * 20 * U, H * .92 + ph * 14 * U, R * (.3 + i * .12), 0, Math.PI * 2); c.stroke(); }
  c.restore();
}
function drawPhoto(Lay, t) {
  const c = Lay.c, G = photoGeom(Lay), z = 1 + .05 * Math.pow(Math.sin(Math.PI * t / DUR), 2);
  c.save(); c.translate(G.px, G.py); c.scale(z, z); c.translate(-G.px, -G.py);
  c.drawImage(Lay.photoIm, G.dx, G.dy, G.pw, G.ph); c.restore();
}
function text(c, s, x, y, size, wt, col, alpha, o = {}) {
  if (alpha <= .002) return;
  c.save(); c.globalAlpha *= alpha; c.font = `${wt} ${size}px ${FONT}`; c.fillStyle = col; c.textBaseline = 'alphabetic';
  c.textAlign = o.align || 'left'; c.letterSpacing = (o.ls || 0) + 'px';
  if (o.shadow) { c.shadowColor = o.shadow === 'light' ? 'rgba(255,255,255,.35)' : 'rgba(0,0,0,.30)'; c.shadowBlur = 18 * U; c.shadowOffsetY = 3 * U; }
  c.fillText(s, x, y); c.restore();
}
function rr(c, x, y, w, h, r) { c.beginPath(); c.roundRect(x, y, w, h, Math.min(r, w / 2, h / 2)); }

function drawProduct(Lay, t) {
  if (!Lay.prodIm) return;
  const c = Lay.c, p = ramp(t, CLOCK.prod, .9), q = 1 - leave(t, CLOCK.out + .1);
  const a = clamp(p * 1.6) * (1 - q); if (a <= .002) return;
  const float = Math.sin((t - CLOCK.prod) / 4 * Math.PI * 2) * 5 * U * clamp(p);
  const s = (.94 + .06 * p) * (1 + .02 * q);
  const x = Lay.prodX + (1 - p) * -50 * U, y = Lay.prodTop + (1 - p) * 30 * U + float - q * 14 * U;
  const w = Lay.pw, h = Lay.ph;
  c.save(); c.globalAlpha *= a; c.translate(x + w / 2, y + h / 2); c.scale(s, s); c.translate(-w / 2, -h / 2);
  c.shadowColor = 'rgba(0,0,0,.38)'; c.shadowBlur = 44 * U; c.shadowOffsetY = 18 * U;
  if (Lay.round > 0) {
    rr(c, 1.5, 1.5, w - 3, h - 3, Lay.round); c.fillStyle = '#000'; c.fill();
    c.shadowColor = 'transparent'; c.save(); rr(c, 0, 0, w, h, Lay.round); c.clip(); c.drawImage(Lay.prodIm, 0, 0, w, h);
    // one slow sheen across the face, once, as the figure settles
    const sh = inv(2.1, 3.0, t);
    if (sh > 0 && sh < 1) {
      const sx = lerp(-w * .6, w * 1.4, E.inOut(sh)), g = c.createLinearGradient(sx - w * .18, 0, sx + w * .18, h * .35);
      g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(.5, 'rgba(255,255,255,.20)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      c.fillStyle = g; c.fillRect(0, 0, w, h);
    }
    c.restore();
  } else c.drawImage(Lay.prodIm, 0, 0, w, h);
  c.restore();
}

function drawWords(Lay, t) {
  const c = Lay.c, sh = Lay.hasPhoto && Lay.shadowT, x = Lay.tx, ta = Lay.ta;
  const out = (d) => 1 - leave(t, CLOCK.out + d, .4);
  // the figure: rises out of a mask on its baseline
  if (Lay.figLines.length) {
    const p = ramp(t, CLOCK.fig, .95), q = out(0), a = clamp(p * 2.2) * (1 - q);
    if (a > .002) Lay.figLines.forEach((s, i) => {
      const pi = ramp(t, CLOCK.fig + i * .09, .95), base = Lay.textTop + Lay.capH * (i + 1) + Lay.figGap * i;
      const dy = (1 - pi) * Lay.capH * .62 - q * 20 * U;
      c.save();
      const w = Lay.mw(s, Lay.FS, 800, -.03 * Lay.FS), cx = ta === 'center' ? x - w / 2 : x;
      c.beginPath(); c.rect(cx - 14 * U, base - Lay.capH * 1.12, w + 28 * U, Lay.capH * 1.12 + .3 * Lay.FS); c.clip();
      text(c, s, x, base + dy, Lay.FS, 800, Lay.figCol, clamp(pi * 2.2) * (1 - q), { align: ta, ls: -.03 * Lay.FS, shadow: sh });
      c.restore();
    });
  }
  // the subline: word by word, each rising a little
  let y = Lay.textTop + Lay.figH + Lay.subGap, k = 0;
  const sq = out(.05);
  Lay.subLines.forEach((ws, li) => {
    const base = y + li * Lay.pitch + Lay.SS * .73, sp = Lay.mw(' ', Lay.SS, 300);
    const wds = ws.map((w) => Lay.mw(w.w, Lay.SS, w.bold ? 700 : 300));
    const total = wds.reduce((s, v) => s + v, 0) + sp * (ws.length - 1);
    let cx = ta === 'center' ? x - total / 2 : x;
    ws.forEach((w, wi) => {
      const st = CLOCK.sub + k * .11, p = ramp(t, st, .55);
      text(c, w.w, cx, base + (1 - p) * 20 * U - (1 - leave(t, CLOCK.out + .05, .4)) * 10 * U, Lay.SS, w.bold ? 700 : 300, Lay.ink, p * (1 - (1 - leave(t, CLOCK.out + .05, .4))), { shadow: sh });
      cx += wds[wi] + sp; k++;
    });
  });
  // the button
  if (CTA) {
    const pp = SK.pop(t, CLOCK.cta, .5), a = clamp(inv(CLOCK.cta, CLOCK.cta + .2, t)) * leave(t, CLOCK.out + .1, .4);
    if (a > .002) {
      const bx = ta === 'center' ? x - Lay.ctaW / 2 : x, by = Lay.textTop + Lay.textH - Lay.ctaH, s = .82 + .18 * pp;
      c.save(); c.globalAlpha *= a; c.translate(bx + Lay.ctaW / 2, by + Lay.ctaH / 2); c.scale(s, s); c.translate(-Lay.ctaW / 2, -Lay.ctaH / 2);
      c.shadowColor = 'rgba(0,0,0,.28)'; c.shadowBlur = 24 * U; c.shadowOffsetY = 8 * U;
      rr(c, 0, 0, Lay.ctaW, Lay.ctaH, Lay.ctaH / 2); c.fillStyle = Lay.ctaFill; c.fill(); c.shadowColor = 'transparent';
      text(c, CTA, Lay.ctaW / 2, Lay.ctaH / 2 + Lay.cs * .36, Lay.cs, 700, Lay.ctaInk, 1, { align: 'center' });
      c.restore();
    }
  }
}

function drawFoot(Lay, t) {
  const c = Lay.c, sh = Lay.hasPhoto && Lay.shadowF;
  const la = ramp(t, CLOCK.logo, .8) * leave(t, CLOCK.out + .2, .45);
  if (Lay.lw && la > .002) {
    const y = Lay.logoY + (1 - ramp(t, CLOCK.logo, .8)) * 10 * U;
    const dark = Lay.logoDarkVariant || (LOGO && !Lay.hasPhoto && lumOf(GROUND) > .45);
    const key = LOGO ? (dark ? LOGO.image || LOGO.light : LOGO.light || LOGO.image) : null;
    if (Lay.logoIm) { c.save(); c.globalAlpha *= la; if (sh) { c.shadowColor = sh === 'light' ? 'rgba(255,255,255,.3)' : 'rgba(0,0,0,.30)'; c.shadowBlur = 14 * U; c.shadowOffsetY = 2 * U; } c.drawImage(SK.IMG[key] || Lay.logoIm, Lay.logoX, y, Lay.lw, Lay.lh); c.restore(); }
    else text(c, NAME, Lay.logoX, y + Lay.lh * .78, Lay.lh, 800, Lay.inkFoot || Lay.ink, la, { shadow: sh });
  }
  if (Lay.legalLines.length) {
    const a = ramp(t, CLOCK.legal, .6) * leave(t, CLOCK.out + .2, .45);
    Lay.legalLines.forEach((s, i) => text(c, s, Lay.M, Lay.footBottom - Lay.legalH + Lay.legalPitch * i + Lay.legalSize * 1.05, Lay.legalSize, 400, ANCHOR === 'top' ? Lay.inkFoot || Lay.ink : Lay.ink, a * .88, { shadow: ANCHOR === 'top' ? sh : Lay.hasPhoto && Lay.shadowT }));
  }
}

function draw(t) {
  const Lay = layout(), c = Lay.c;
  if (Lay.hasPhoto) { drawPhoto(Lay, t); drawScrim(Lay, t); } else drawField(Lay, t);
  drawProduct(Lay, t);
  drawWords(Lay, t);
  drawFoot(Lay, t);
}

/* ------------------------------------------------------------------ the sound
   Light, on a 120 bpm clock like the picture: a warm pad under four chords, a soft pluck line, a little
   shaker, a chime on the figure's beat and a tick for each word -- all of it ends on the last beat so the loop
   can start again. Written by the film so a different subline brings its own ticks. */
const beatOf = (t) => t * BPM / 60;
const gf = (x) => String(+x.toPrecision(6));
function scoreData() {
  const CH = [['C3+E3+G3+B3', 'C2'], ['A2+C3+E3+G3', 'A1'], ['F2+A2+C3+E3', 'F1'], ['G2+B2+D3+F3', 'G1']];
  const pad = [], bass = [], pluck = [], bell = [];
  CH.forEach(([chord, root], i) => {
    const b = i * 4, len = i === 3 ? 2.2 : 4;
    pad.push(`${gf(b)} ${chord} ${len} .5`);
    bass.push(`${gf(b)} ${root} 1.2 .55`);
    if (i < 3) bass.push(`${gf(b + 2)} ${root} .8 .4`);
  });
  const line = ['E5', 'G5', 'C6', 'G5', 'A5', 'C6', 'E6', 'C6', 'A5', 'F5', 'A5', 'C6', 'B5', 'D6'];
  for (let k = 0; k < 13; k++) if (k >= 4 && k % 1 === 0) pluck.push(`${gf(4 + (k - 4) * .5 + 0)} ${line[k]} .45 ${(k % 2 ? .3 : .42).toFixed(2)}`);
  bell.push(`${gf(beatOf(CLOCK.fig) + .3)} C5+E5+G5+C6 1.6 .5`);
  return {
    bpm: BPM, drum_gain: .4,
    instruments: {
      pad_2_warm: { g: .17, pan: 0, send: .55, rel: .9, soft_attack: true },
      acoustic_bass: { g: .3, pan: 0, send: .08, rel: .3 },
      marimba: { g: .22, pan: .3, send: .3, rel: .5 },
      glockenspiel: { g: .2, pan: .25, send: .4, rel: 1.2 },
    },
    events: [
      { inst: 'pad_2_warm', vel: .6, notes: pad.join('; ') },
      { inst: 'acoustic_bass', vel: .8, notes: bass.join('; '), humanize: false },
      { inst: 'marimba', vel: .8, notes: pluck.join('; ') },
      { inst: 'glockenspiel', vel: .8, notes: bell.join('; ') },
      { type: 'drums', from: 4, bars: 2, steps: 16, vel: .6, kit: { shaker: '.o.o.o.o.o.o.o.o' }, gains: { shaker: .22 } },
    ],
  };
}
function sfxData() {
  const cues = [], r = (x, n) => +x.toFixed(n);
  const add = (t, fx, db, args = {}, o = {}) => { const c = { t: r(Math.max(0, t), 3), fx, db }; if (o.pan) c.pan = r(o.pan, 2); if (o.send !== undefined) c.send = o.send; if (Object.keys(args).length) c.args = args; cues.push(c); return c; };
  if (PRODUCT) add(CLOCK.prod - .05, 'swoosh_soft', -24, { sec: .7 }, { pan: -.3 });
  if (FIG) { add(CLOCK.fig + .12, 'whoosh', -26, { sec: .5, f0: 400, f1: 2600 }); add(CLOCK.fig + .38, 'thunk', -19, { sec: .3 }); add(CLOCK.fig + .4, 'shimmer', -27, { sec: .8, f0: 1500, f1: 6000 }); }
  if (LOGO || NAME) add(CLOCK.logo + .1, 'blip', -30, { f: 1320, sec: .08 }, { pan: .4 });
  const words = SUB.join(' ').replace(/\*/g, '').split(/\s+/).filter(Boolean).length;
  if (words) { const tk = add(CLOCK.sub, 'tick', -29, {}, { pan: .1 }); tk.times = Array.from({ length: Math.min(words, 12) }, (_, i) => r(CLOCK.sub + i * .11, 3)); }
  if (CTA) { add(CLOCK.cta + .02, 'pop', -21, { f0: 620, f1: 210, sec: .1 }); add(CLOCK.cta + .1, 'blip', -27, { f: 1175, sec: .1 }); }
  add(CLOCK.out, 'swoosh_soft', -27, { sec: .6 }, { pan: .2 });
  return cues.sort((p, q) => p.t - q.t);
}

SK.film({
  duration: DUR,
  camera: SK.camera([[0, [W / 2, H / 2, 1]]]),
  handheld: false,
  speedLines: false,
  fadeOut: 0,
  draw,
  sound: { score: scoreData, sfx: sfxData },
});
