/* sketch/heads.js -- talking heads made from photos (an engine module a film opts into:
   "modules": ["heads"], added by itself when the manifest names "heads").

   A rig (scripts/head-rig.py) is a photo measured once: the head cut out of it, the whole photo,
   and where the face is -- lips, jaw line, eyes, a mesh over the face. This module draws a rig
   and makes it talk to the voice-over as a pure function of t:
     * the mouth opens on the speaker's own voice: sketch-render gives every SK.VO line its
       speaker (`who`) and a mouth track measured from that line's audio (SK.talk);
     * the eyes blink on a clock seeded by the rig's name;
     * a head nods on the speaker's words (cut-outs and bobble-heads; a photo keeps still).

   SK.head(name, x, y, h, o) draws rig `name` with the middle of its face (halfway from the
   hairline to the chin) at x, y, the face h tall. o:
     style  'cutout'  the head alone, cut out, with a paper edge (default)
            'photo'   the whole photo (o.crop narrows it); only the face moves in it
            'bobble'  the cut-out head on a small drawn body, on a spring
     mouth  'warp'    the lips part and the jaw drops inside the face: a photo that talks
                      (default for 'photo')
            'chin'    the chin under the mouth drops like a puppet's (default otherwise)
            'dummy'   the same, with the two slits under the mouth corners drawn: a
                      ventriloquist's dummy
            'muppet'  the whole lower face drops, the mouth as wide as the face
            'flap'    the top of the head hinges up at the lips (cut-outs and bobble-heads)
            'none'
     who    the speaker whose lines move this mouth (default: the rig's name)
     tone   'color' | 'mono' | 'sepia' | 'news' (printed in halftone dots) (default 'color')
     edge   paper edge round a cut-out, in rig pixels (default 3% of the face; 0 for none);
            edgeCol its colour (default '#fdfbf6'); shadow (default true for cut-outs)
     jaw    how far the mouth opens, x the default (1); steps: mouth changes a second (0 =
            smooth; a collage film's own clock by default); blink (true, false, or a number
            0..1 to hold the lids there); nod (1 for cut-outs and bobble-heads, 0 for a photo);
            tilt (radians, added); flip (mirror); alpha
     crop   [x0, y0, x1, y1] for 'photo': the part of the photo shown, in face heights from the
            middle of the face (default: all of it)
     body   for 'bobble': {shirt, trousers, skin} colours and arms ('rest'|'wave'|'point')
   Returns {x, y, h, open}: where the face is this frame and how open its mouth is.

   SK.headBox(name, x, y, h) -> [x0, y0, x1, y1]: the whole cut-out head (hair included) for a
   face placed that way -- lay heads out with it. SK.talk(who, t) -> {open 0..1, wide -1..1,
   on} for any speaker; SK.speaker(t) -> who is speaking at t (or '').
   Rigs come in as SK.RIGS[name] with their pictures in SK.IMG ('rig:<name>:head',
   'rig:<name>:photo'); sketch-render inlines both from the manifest's "heads". */
(function () {
  'use strict';
  const SK = window.SK;
  const { clamp, lerp, E, rnd, TAU } = SK;
  SK.RIGS = SK.RIGS || {};

  /* ------------------------------------------------------------ the voice: who speaks, how open */
  let VOIDX = null, VOSRC = null;
  function voIndex() {
    if (VOSRC === SK.VO && VOIDX) return VOIDX;
    VOSRC = SK.VO; VOIDX = {};
    for (const L of (SK.VO && SK.VO.lines) || []) (VOIDX[L.who || ''] = VOIDX[L.who || ''] || []).push(L);
    for (const k in VOIDX) VOIDX[k].sort((a, b) => a.start - b.start);
    return VOIDX;
  }
  function track(L, key, t, dflt) {
    const m = L.mouth; if (!m || !m[key]) return dflt;
    const f = (t - L.start) * m.fps, i = Math.floor(f), a = m[key];
    if (i < 0 || i >= a.length) return dflt;
    return lerp(a[i], i + 1 < a.length ? a[i + 1] : dflt * 100, f - i) / 100;
  }
  /** the mouth of speaker `who` at t: open 0..1, wide -1..1 (spread +, pucker -), on (a line of
   *  theirs is playing) */
  SK.talk = function (who, t = SK.T) {
    for (const L of voIndex()[who || ''] || []) {
      if (t < L.start - .05) break;
      if (t <= L.end + .12) return { open: clamp(track(L, 'o', t, 0)), wide: clamp(track(L, 'w', t, .5) * 2 - 1, -1, 1), on: t >= L.start && t <= L.end };
    }
    return { open: 0, wide: 0, on: false };
  };
  /** who is speaking at t ('' when nobody is) */
  SK.speaker = function (t = SK.T) {
    for (const L of (SK.VO && SK.VO.lines) || []) if (t >= L.start && t <= L.end) return L.who || '';
    return '';
  };
  const WORDS = new Map();
  function wordsOf(who) {
    if (VOSRC !== SK.VO) WORDS.clear();
    if (!WORDS.has(who)) { const out = []; for (const L of voIndex()[who || ''] || []) for (const w of L.words || []) out.push(w.s); WORDS.set(who, out); }
    return WORDS.get(who);
  }

  /* ------------------------------------------------------------ canvases, made once per rig */
  const canvas = (w, h) => { const c = document.createElement('canvas'); c.width = Math.max(1, Math.ceil(w)); c.height = Math.max(1, Math.ceil(h)); return c; };
  const CACHE = new Map();
  const cached = (k, make) => { if (!CACHE.has(k)) CACHE.set(k, make()); return CACHE.get(k); };
  function rigOf(name) {
    const R = SK.RIGS[name];
    if (!R) throw new Error('SK.head: no rig named ' + JSON.stringify(name) + ' (the manifest\'s "heads": ' + Object.keys(SK.RIGS).join(', ') + ')');
    return R;
  }
  /** the picture in a tone. box: the face's box in the picture's pixels (its darks and lights
   *  set the levels, not a bright window behind it); fh: the face's height there (the size of
   *  the halftone screen follows the face, not the picture) */
  function toned(img, tone, key, box, fh, plain) {
    return cached(key + ':' + tone + (plain ? ':plain' : ''), () => {
      const c = canvas(img.width, img.height), g = c.getContext('2d');
      if (tone === 'mono' || tone === 'news') g.filter = 'grayscale(1)';
      else if (tone === 'sepia') g.filter = 'sepia(.85) contrast(1.05) brightness(1.02)';
      g.drawImage(img, 0, 0); g.filter = 'none';
      // a patch laid over a picture must match it pixel for pixel: no levels of its own
      if ((tone === 'mono' || tone === 'news') && !plain) levels(c, box);
      if (tone === 'news') halftone(c, fh);
      return c;
    });
  }
  /** stretch a grey picture's own darks and lights (2nd and 98th percentile, where it is
   *  opaque, inside box when given) to black and white: a backlit face prints like a lit one */
  function levels(c, box) {
    const g = c.getContext('2d'), im = g.getImageData(0, 0, c.width, c.height), d = im.data;
    const hist = new Uint32Array(256); let n = 0;
    const [bx0, by0, bx1, by1] = box || [0, 0, c.width, c.height];
    for (let y = Math.max(0, by0 | 0); y < Math.min(c.height, by1); y++) for (let x = Math.max(0, bx0 | 0); x < Math.min(c.width, bx1); x++) {
      const i = (y * c.width + x) * 4; if (d[i + 3] > 128) { hist[d[i]]++; n++; }
    }
    if (!n) return;
    let lo = 0, hi = 255, acc = 0;
    for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc >= n * .02) { lo = v; break; } }
    acc = 0;
    for (let v = 255; v >= 0; v--) { acc += hist[v]; if (acc >= n * .02) { hi = v; break; } }
    if (hi - lo < 16) return;
    const k = 255 / (hi - lo);
    for (let i = 0; i < d.length; i += 4) { const v = Math.max(0, Math.min(255, (d[i] - lo) * k)); d[i] = d[i + 1] = d[i + 2] = v; }
    g.putImageData(im, 0, 0);
  }
  /** newspaper dots: ink dots sized by the darkness, on a 45-degree screen, on newsprint */
  function halftone(c, fh) {
    const g = c.getContext('2d'), W = c.width, H = c.height;
    const src = g.getImageData(0, 0, W, H).data;
    const cell = Math.max(3, Math.round((fh || Math.max(W, H) / 2.7) / 55));
    const out = canvas(W, H), o = out.getContext('2d');
    o.fillStyle = '#ece6d6'; o.fillRect(0, 0, W, H);
    o.fillStyle = '#1d1b19';
    const ca = Math.SQRT1_2, R = Math.hypot(W, H);
    for (let v = -R; v < R; v += cell) for (let u = -R; u < R; u += cell) {
      const x = (u - v) * ca + W / 2, y = (u + v) * ca + H / 2;
      if (x < 0 || y < 0 || x >= W || y >= H) continue;
      const i = ((y | 0) * W + (x | 0)) * 4;
      if (src[i + 3] < 40) continue;
      const lum = src[i] / 255, r = cell * .66 * Math.sqrt(clamp(1 - lum * 1.04));
      if (r < .4) continue;
      o.beginPath(); o.arc(x, y, r, 0, TAU); o.fill();
    }
    o.globalCompositeOperation = 'destination-in'; o.drawImage(c, 0, 0);
    g.clearRect(0, 0, W, H); g.drawImage(out, 0, 0);
  }
  /** the picture with a paper edge round its silhouette (edge px of margin all round) */
  function edged(src, edge, col, key) {
    return cached(key + ':edge:' + edge + col, () => {
      const c = canvas(src.width + edge * 2, src.height + edge * 2), g = c.getContext('2d');
      if (edge > 0) {
        for (let i = 0; i < 28; i++) { const a = i / 28 * TAU; g.drawImage(src, edge + Math.cos(a) * edge, edge + Math.sin(a) * edge); }
        g.globalCompositeOperation = 'source-in'; g.fillStyle = col; g.fillRect(0, 0, c.width, c.height);
        g.globalCompositeOperation = 'source-over';
      }
      g.drawImage(src, edge, edge);
      return c;
    });
  }
  /** a soft dark silhouette of a canvas (its shadow), with pad px round it */
  function shade(src, blur, key) {
    return cached(key + ':shade:' + blur, () => {
      const pad = Math.ceil(blur * 2.5), c = canvas(src.width + pad * 2, src.height + pad * 2), g = c.getContext('2d');
      g.filter = 'blur(' + blur + 'px)'; g.drawImage(src, pad, pad); g.filter = 'none';
      g.globalCompositeOperation = 'source-in'; g.fillStyle = 'rgb(28,20,14)'; g.fillRect(0, 0, c.width, c.height);
      c.pad = pad;
      return c;
    });
  }
  const path = (g, pts, close = true) => { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); if (close) g.closePath(); };
  /** the part of a canvas inside (or outside) a polygon, same size */
  function piece(src, poly, inside, key) {
    return cached(key, () => {
      const c = canvas(src.width, src.height), g = c.getContext('2d');
      g.drawImage(src, 0, 0);
      g.globalCompositeOperation = inside ? 'destination-in' : 'destination-out';
      g.fillStyle = '#000'; path(g, poly); g.fill();
      return c;
    });
  }

  /* ------------------------------------------------------------ small geometry (rig pixels) */
  const add = (p, v, k = 1) => [p[0] + v[0] * k, p[1] + v[1] * k];
  function rot(p, c, a) { const s = Math.sin(a), co = Math.cos(a), x = p[0] - c[0], y = p[1] - c[1]; return [c[0] + x * co - y * s, c[1] + x * s + y * co]; }
  /** blink 0..1 at t on the rig's own seeded clock: one every 2.4-5.6 s, sometimes a double */
  const BLINKS = new Map();
  function blinkAt(name, t) {
    let list = BLINKS.get(name);
    if (!list) {
      list = []; let seed = 7; for (const ch of name) seed = (seed * 31 + ch.charCodeAt(0)) | 0;
      const r = SK.mulberry(seed); let x = .7 + r() * 1.6;
      while (x < 3600) { list.push(x); if (r() < .12) list.push(x + .34); x += 2.4 + r() * 3.2; }
      BLINKS.set(name, list);
    }
    let lo = 0, hi = list.length - 1;
    if (t < list[0]) return 0;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (list[m] <= t) lo = m; else hi = m - 1; }
    const d = t - list[lo];
    return d > .22 ? 0 : d < .07 ? E.out(d / .07) : d < .1 ? 1 : 1 - E.inOut((d - .1) / .12);
  }
  /** head motion on the speaker's words: a small nod and turn on each, decaying */
  function nodAt(who, t) {
    const ws = wordsOf(who); let a = 0, y = 0;
    for (let i = ws.length - 1; i >= 0; i--) {
      const d = t - ws[i]; if (d < 0) continue; if (d > 1.6) break;
      const k = Math.exp(-d / .32) * Math.sin(d * TAU / .62), sg = rnd(i * 7 + 3) < .5 ? -1 : 1;
      a += k * .022 * sg; y += k * .012;
    }
    return { a, y };
  }

  /* ------------------------------------------------------------ the inside of the mouth */
  const grey = (hex) => { const n = parseInt(hex.slice(1), 16), v = Math.round(.3 * (n >> 16) + .59 * (n >> 8 & 255) + .11 * (n & 255)); return '#' + ((1 << 24) | (v << 16) | (v << 8) | v).toString(16).slice(1); };
  /** the mouth's colours for a rig and a tone: teeth and tongue lit like the face they are in
   *  (a white band in a backlit face glows) */
  function palette(tone, R) {
    const skin = (R.col && R.col.skin) || '#c8a08a', lip = (R.col && R.col.lip) || '#a0605a';
    let p = { top: '#1e0706', bot: '#4a1512', tongue: SK.mix(lip, '#8e2f3a', .5), teeth: SK.mix(skin, '#f3eee4', .38) };
    if (tone === 'sepia') p = { top: '#1c1007', bot: '#40280f', tongue: '#94644a', teeth: SK.mix(grey(skin), '#efe3cc', .6) };
    if (tone === 'mono' || tone === 'news') p = { top: '#0e0e0e', bot: '#2e2e2e', tongue: grey(p.tongue), teeth: grey(p.teeth) };
    p.gum = SK.mix(p.teeth, p.bot, .45);
    return p;
  }
  /** the dark between an upper and a lower edge (each left to right), in the face's own
   *  down (dn); teeth hang from `lip` (the part of the upper edge that is lip) */
  function cavity(ctx, upper, lower, open, tone, R, dn, lip) {
    if (open <= .003) return;
    const F = R.face, pal = palette(tone, R), poly = [...upper, ...lower.slice().reverse()];
    let d0 = 1e9, d1 = -1e9;
    for (const p of poly) { const d = p[0] * dn[0] + p[1] * dn[1]; d0 = Math.min(d0, d); d1 = Math.max(d1, d); }
    const gap = d1 - d0;
    ctx.save(); path(ctx, poly); ctx.clip();
    const c = poly.reduce((s, p) => [s[0] + p[0] / poly.length, s[1] + p[1] / poly.length], [0, 0]);
    const g = ctx.createLinearGradient(c[0] - dn[0] * gap / 2, c[1] - dn[1] * gap / 2, c[0] + dn[0] * gap / 2, c[1] + dn[1] * gap / 2);
    g.addColorStop(0, pal.top); g.addColorStop(1, pal.bot);
    ctx.fillStyle = g; path(ctx, poly); ctx.fill();
    const lipPts = lip || upper, mw = Math.hypot(lipPts[lipPts.length - 1][0] - lipPts[0][0], lipPts[lipPts.length - 1][1] - lipPts[0][1]);
    if (gap > F.h * .035) {
      // the tongue: low in the mouth, in its shadow
      const lc = lower.reduce((s, p) => [s[0] + p[0] / lower.length, s[1] + p[1] / lower.length], [0, 0]);
      ctx.globalAlpha *= .75; ctx.fillStyle = SK.mix(pal.tongue, pal.bot, .45);
      ctx.beginPath(); ctx.ellipse(lc[0] + dn[0] * gap * .08, lc[1] + dn[1] * gap * .08, mw * .24, gap * .34, Math.atan2(-dn[0], dn[1]), 0, TAU); ctx.fill();
      ctx.globalAlpha /= .75;
      // upper teeth: a band hanging from the lip, tapering to nothing at the corners
      const th = Math.min(gap * .36, F.h * .03), n = lipPts.length;
      const edgeB = lipPts.map((p, i) => { const k = Math.pow(Math.sin(Math.PI * i / (n - 1)), .45); return add(p, dn, th * k); });
      const tg = ctx.createLinearGradient(c[0] - dn[0] * gap / 2, c[1] - dn[1] * gap / 2, c[0] - dn[0] * gap / 2 + dn[0] * th, c[1] - dn[1] * gap / 2 + dn[1] * th);
      tg.addColorStop(0, pal.teeth); tg.addColorStop(1, pal.gum);
      ctx.fillStyle = pal.teeth; path(ctx, [...lipPts, ...edgeB.slice().reverse()]); ctx.fill();
      ctx.globalAlpha *= .35; ctx.strokeStyle = pal.gum; ctx.lineWidth = Math.max(.6, th * .12);
      ctx.beginPath(); ctx.moveTo(edgeB[0][0], edgeB[0][1]); for (const p of edgeB) ctx.lineTo(p[0], p[1]); ctx.stroke();
    }
    ctx.restore();
  }

  /* ------------------------------------------------------------ the mesh warp */
  function affine(s0, s1, s2, d0, d1, d2) {
    const sx1 = s1[0] - s0[0], sy1 = s1[1] - s0[1], sx2 = s2[0] - s0[0], sy2 = s2[1] - s0[1];
    const dx1 = d1[0] - d0[0], dy1 = d1[1] - d0[1], dx2 = d2[0] - d0[0], dy2 = d2[1] - d0[1];
    const det = sx1 * sy2 - sx2 * sy1; if (Math.abs(det) < 1e-9) return null;
    const a = (dx1 * sy2 - dx2 * sy1) / det, c = (dx2 * sx1 - dx1 * sx2) / det;
    const b = (dy1 * sy2 - dy2 * sy1) / det, d = (dy2 * sx1 - dy1 * sx2) / det;
    return [a, b, c, d, d0[0] - a * s0[0] - c * s0[1], d0[1] - b * s0[0] - d * s0[1]];
  }
  /** textured triangles `tris` taken from rest points P to moved points Q; the texture sits at
   *  texO in rig pixels, texS rig pixels per texture pixel */
  function warp(ctx, tex, texO, texS, P, Q, tris) {
    for (const t of tris) {
      const a = P[t[0]], b = P[t[1]], c = P[t[2]], A = Q[t[0]], B = Q[t[1]], C = Q[t[2]];
      const m = affine(a, b, c, A, B, C); if (!m) continue;
      const cx = (A[0] + B[0] + C[0]) / 3, cy = (A[1] + B[1] + C[1]) / 3;
      const grow = (p) => { const dx = p[0] - cx, dy = p[1] - cy, L = Math.hypot(dx, dy) || 1; return [p[0] + dx / L * .8, p[1] + dy / L * .8]; };
      ctx.save();
      path(ctx, [grow(A), grow(B), grow(C)]); ctx.clip();
      ctx.transform(m[0], m[1], m[2], m[3], m[4], m[5]);
      const x0 = Math.min(a[0], b[0], c[0]) - 3, y0 = Math.min(a[1], b[1], c[1]) - 3;
      const x1 = Math.max(a[0], b[0], c[0]) + 3, y1 = Math.max(a[1], b[1], c[1]) + 3;
      const sx = Math.max(0, (x0 - texO[0]) / texS), sy = Math.max(0, (y0 - texO[1]) / texS);
      const sw = Math.min(tex.width, (x1 - texO[0]) / texS) - sx, sh = Math.min(tex.height, (y1 - texO[1]) / texS) - sy;
      if (sw > 0 && sh > 0) ctx.drawImage(tex, sx, sy, sw, sh, texO[0] + sx * texS, texO[1] + sy * texS, sw * texS, sh * texS);
      ctx.restore();
    }
  }
  function meshSets(R) {
    if (R._sets) return R._sets;
    const m = R.mesh, moving = (i) => m.wj[i] > .004 || m.wu[i] > .004 || Math.abs(m.wc[i]) > .004;
    const lid = (i) => m.b[i][0] !== 0 || m.b[i][1] !== 0;
    const jawT = [], eyeT = [];
    for (const t of m.t) { if (t.some(moving)) jawT.push(t); if (t.some(lid)) eyeT.push(t); }
    return (R._sets = { jawT, eyeT });
  }
  function moved(R, open, wide, blink, J) {
    const m = R.mesh, dn = R.face.down, rt = R.face.right, C = R.face.mouth_w * .09;
    return m.p.map((p, i) => {
      const j = J * open * (m.wj[i] - .22 * m.wu[i]), w = C * wide * m.wc[i];
      return [p[0] + dn[0] * j + rt[0] * w + m.b[i][0] * blink, p[1] + dn[1] * j + rt[1] * w + m.b[i][1] * blink];
    });
  }
  // the inner lip runs, by MediaPipe index (the first 468 mesh points are the landmarks)
  const LIP_IU = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308], LIP_IL = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308];

  /* ------------------------------------------------------------ the bobble-head's body */
  /** how much `who` has been talking over the last half second, 0..1: a gesture that follows
   *  it eases in and out instead of jumping when a line starts */
  function talkiness(who, t) {
    let s = 0;
    for (let i = 0; i < 6; i++) s += SK.talk(who, t - i * .09).on ? 1 : 0;
    return E.sine(s / 6);
  }
  /** a bobble-head doll's body, drawn at the neck (0, 0) under the chin in the film's own pen:
   *  a short neck the head springs on, a small body, and the doll's stand with a name plate */
  function body(R, o, fh, sway, talk, t) {
    const C = SK.C, b = o.body || {};
    const shirt = b.shirt || C.shirtA, trousers = b.trousers || '#4d5566', skin = b.skin || R.col.skin;
    const shoes = b.shoes || '#2a2521', w = fh * .64, hg = fh * .7, legH = fh * .42, baseY = hg + legH;
    if (b.base !== false) {
      // the stand: a disc on a short drum, the plate on its front
      const bw = w * .82, bh = fh * .17, top = fh * .05, col = b.base || '#3a3431';
      SK.card(-bw, baseY, bw * 2, bh, { r: bh * .45, fill: col, shadow: { blur: fh * .06, y: fh * .03, col: 'rgba(20,14,10,.3)' } });
      SK.wash(SK.S.ellC(0, baseY, bw, top), SK.mix(col, '#ffffff', .18), { seed: 58, dx: 0, dy: 0, tex: false });
      SK.ink(SK.S.ell(0, baseY, bw, top), { w: 3, seed: 59, dbl: false, alpha: .6 });
      if (b.name) {
        const pw = bw * 1.25, ph = bh * .62;
        SK.card(-pw / 2, baseY + bh * .26, pw, ph, { r: ph * .2, fill: b.plate || '#d6bf84', shadow: false });
        SK.txt(String(b.name).toUpperCase(), 0, baseY + bh * .26 + ph * .54, { size: ph * .78, wt: 700, col: '#3a2c18', ls: ph * .08, mode: 'type', wob: 0 });
      }
    }
    for (const s of [-1, 1]) {
      const leg = SK.S.rrect(s * w * .04 - (s < 0 ? w * .3 : 0), hg * .9, w * .3, legH * 1.02, w * .08);
      SK.wash(leg, trousers, { seed: 60 + s, dx: 0, dy: 0 }); SK.ink(leg, { w: 3.5, seed: 62 + s });
      const shoe = SK.S.ellC(s * w * .2, baseY - fh * .01, w * .22, fh * .045);
      SK.wash(shoe, shoes, { seed: 64 + s, dx: 0, dy: 0, tex: false }); SK.ink(shoe, { w: 3, seed: 66 + s });
    }
    const pose = b.arms || 'rest';
    // an arm: hanging at the side, or (the right one) up in front of the chest while talking
    const arm = (s) => {
      const sh = [s * w * .47, hg * .16];
      let hand;
      if (pose === 'wave' && s > 0) hand = [w * .95, -hg * .2 + Math.sin(t * 9) * hg * .07];
      else if (pose === 'point' && s > 0) hand = [w * 1.1, hg * .12];
      else if (s > 0) hand = [w * lerp(.6, .3, talk), hg * lerp(.76, .42, talk) + Math.sin(t * 4.6) * hg * .05 * talk];
      else hand = [-w * .6, hg * .76];
      const elbow = [sh[0] + s * w * (.22 + .12 * talk), (sh[1] + hand[1]) / 2 + hg * (.06 + .14 * talk)];
      const path = SK.S.path([['M', sh[0], sh[1]], ['Q', elbow[0], elbow[1], hand[0], hand[1]]]);
      SK.ink(path, { w: fh * .075, col: shirt, seed: 70 + s, taper: false, dbl: false, jit: .5 });
      SK.ink(path, { w: 3, seed: 72 + s, alpha: .45 });
      SK.wash(SK.S.ellC(hand[0], hand[1], fh * .045, fh * .048), skin, { seed: 74 + s, dx: 0, dy: 0, tex: false });
      SK.ink(SK.S.ell(hand[0], hand[1], fh * .045, fh * .048), { w: 3, seed: 76 + s, dbl: false });
    };
    const front = talk > .05 || pose !== 'rest'; // a gesture comes in front of the body
    arm(-1);
    if (!front) arm(1);
    // the torso: round shoulders, a collar the neck comes out of
    const torso = SK.S.path([['M', -w * .2, 0], ['Q', -w * .52, 0, -w * .52, hg * .24], ['L', -w * .48, hg * .92], ['Q', -w * .47, hg, -w * .38, hg], ['L', w * .38, hg], ['Q', w * .47, hg, w * .48, hg * .92], ['L', w * .52, hg * .24], ['Q', w * .52, 0, w * .2, 0], ['Z']]);
    SK.wash(torso, shirt, { seed: 80 }); SK.ink(torso, { w: 4.5, seed: 81 });
    const nx = sway * fh * .1;
    const neck = SK.S.path([['M', -w * .12, hg * .06], ['L', -w * .11 + nx, -fh * .08], ['L', w * .11 + nx, -fh * .08], ['L', w * .12, hg * .06]]);
    SK.wash(neck, skin, { seed: 82, dx: 0, dy: 0, tex: false }); SK.ink(neck, { w: 3, seed: 83, alpha: .6 });
    SK.ink(SK.S.arc(0, 0, w * .16, .15, Math.PI - .15, w * .07), { w: 3.5, seed: 84, alpha: .8 }); // the collar
    if (front) arm(1);
  }

  /* ------------------------------------------------------------ SK.head */
  const MOUTHS = { jaw: 'chin', chin: 'chin', dummy: 'dummy', muppet: 'muppet', flap: 'flap', warp: 'warp', swap: 'swap', none: 'none' };
  SK.headBox = function (name, x, y, h) {
    const R = rigOf(name), F = R.face, mid = [(R.lm.top[0] + R.lm.chin[0]) / 2, (R.lm.top[1] + R.lm.chin[1]) / 2], k = h / F.h;
    const H = R.head;
    return [x + (H.x - mid[0]) * k, y + (H.y - mid[1]) * k, x + (H.x + H.w * H.s - mid[0]) * k, y + (H.y + H.h * H.s - mid[1]) * k];
  };
  SK.head = function (name, x, y, h, o = {}) {
    const ctx = SK.ctx(), R = rigOf(name), t = o.t ?? SK.T;
    const style = o.style || 'cutout', tone = o.tone || 'color', cut = style !== 'photo';
    const toon = R.type === 'sprite'; // a drawn character: its own mouths, swapped
    let mouth = toon ? (o.mouth === 'none' ? 'none' : 'swap') : MOUTHS[o.mouth || (style === 'photo' ? 'warp' : 'chin')];
    if (!mouth) throw new Error('SK.head: mouth ' + JSON.stringify(o.mouth) + ' is not one of ' + Object.keys(MOUTHS).join(', '));
    if (mouth === 'flap' && !cut) mouth = 'chin';
    const who = o.who ?? name;
    // a collage film moves on its own clock (twos); the mouth keeps to it too
    // a collage film moves on its own clock; a drawn character's mouths change on twos, as
    // replacement mouths do in stop motion (a shape held for one frame reads as flicker)
    const steps = o.steps ?? (SK.style.steps && SK.step ? SK.stepFps(SK.style.steps) : toon ? (SK.stepFps ? SK.stepFps(12) : 12) : 0);
    const tt = steps ? Math.floor(t * steps + 1e-4) / steps : t;
    const tk = SK.talk(who, tt);
    let open = tk.open;
    if (mouth !== 'warp' && mouth !== 'swap') open = clamp((open - .14) / .86); // a rigid jaw: shut, not a slit, when nearly shut
    open *= o.jaw ?? 1;
    const wide = tk.wide;
    const blink = typeof o.blink === 'number' ? o.blink : o.blink === false ? 0 : blinkAt(name, t);
    const alpha = o.alpha ?? 1; if (alpha <= 0) return { x, y, h, open };
    const F = R.face, dn = F.down, mid = [(R.lm.top[0] + R.lm.chin[0]) / 2, (R.lm.top[1] + R.lm.chin[1]) / 2];
    const k = h / F.h; // world px per rig px
    const nodK = o.nod ?? (cut ? 1 : 0);
    const nd = nodK ? nodAt(who, t) : { a: 0, y: 0 };
    // how far a mouth at full open travels, in face heights: a photo's jaw as far as a jaw
    // goes; a puppet's further, so a cut-out reads from across the room
    const J = F.h * ({ warp: .11, muppet: .15, flap: 0 }[mouth] ?? .13);
    const imgHead = SK.IMG['rig:' + name + ':head'], imgPhoto = SK.IMG['rig:' + name + ':photo'] || imgHead;
    if (!imgHead || !imgPhoto) return { x, y, h, open };
    const nudge = SK.nudge ? SK.nudge(name.length * 131 + 7) : [0, 0, 0];
    ctx.save(); ctx.globalAlpha *= alpha;
    ctx.translate(nudge[0], nudge[1]);
    if (style === 'bobble') {
      // the head springs on its neck: a wobble on each of its speaker's words, an idle drift
      const neckY = y + h * .5, tl = talkiness(who, t);
      const sway = nd.a * 7 + Math.sin(t * 1.7 + name.length) * .02 + Math.sin(t * 6.1) * .018 * tl;
      SK.at(x, neckY + h * .02, 0, 1, () => body(R, o, h, sway, tl, t));
      ctx.translate(x, neckY); ctx.rotate(sway + (o.tilt || 0) + nudge[2]); ctx.translate(-x, -neckY);
      ctx.translate(0, nd.y * h * 2.5);
    } else if (nodK || o.tilt || nudge[2]) {
      ctx.translate(x, y + h * .45); ctx.rotate(nd.a * 1.4 * nodK + (o.tilt || 0) + nudge[2]); ctx.translate(-x, -(y + h * .45));
      ctx.translate(0, nd.y * h * nodK);
    }
    ctx.translate(x, y); if (o.flip) ctx.scale(-1, 1); ctx.scale(k, k); ctx.translate(-mid[0], -mid[1]);
    // the picture: the photo, or the head cut out of it with its paper edge
    const edge = cut ? Math.round(o.edge ?? F.h * .03) : 0;
    let tex, texO, texS;
    // the face's box, for a tone's levels: in the photo's pixels, and in the head's
    let fx0 = 1e9, fy0 = 1e9, fx1 = -1e9, fy1 = -1e9;
    for (const [px, py] of R.lm.oval) { fx0 = Math.min(fx0, px); fy0 = Math.min(fy0, py); fx1 = Math.max(fx1, px); fy1 = Math.max(fy1, py); }
    if (cut) {
      const hb = [(fx0 - R.head.x) / R.head.s, (fy0 - R.head.y) / R.head.s, (fx1 - R.head.x) / R.head.s, (fy1 - R.head.y) / R.head.s];
      const tn = toon && tone === 'news' ? 'mono' : tone; // a character's patches take its tone plain, so it does too
      tex = edged(toned(imgHead, tn, name + ':head', hb, F.h / R.head.s, toon), edge, o.edgeCol || '#fdfbf6', name + ':' + tone);
      texS = R.head.s; texO = [R.head.x - edge * texS, R.head.y - edge * texS];
    } else {
      tex = toned(imgPhoto, tone, name + ':photo', [fx0, fy0, fx1, fy1], F.h); texO = [0, 0]; texS = 1;
      if (o.crop) {
        const c = o.crop;
        ctx.beginPath(); ctx.rect(mid[0] + c[0] * F.h, mid[1] + c[1] * F.h, (c[2] - c[0]) * F.h, (c[3] - c[1]) * F.h); ctx.clip();
      }
    }
    const shadowOn = cut && o.shadow !== false, blur = Math.max(2, Math.round(F.h * .035 / texS));
    const sOff = [F.h * .014, F.h * .024];
    const draw = (img, key, noShadow) => {
      if (shadowOn && !noShadow) {
        const s = shade(img, blur, key);
        ctx.save(); ctx.globalAlpha *= .3;
        ctx.drawImage(s, texO[0] - s.pad * texS + sOff[0], texO[1] - s.pad * texS + sOff[1], s.width * texS, s.height * texS);
        ctx.restore();
      }
      ctx.drawImage(img, texO[0], texO[1], img.width * texS, img.height * texS);
    };
    const toTex = (p) => [(p[0] - texO[0]) / texS, (p[1] - texO[1]) / texS];
    const base = name + ':' + tone + ':' + edge;
    if (toon) {
      // the character, then the mouth shape the voice asks for, then the blink
      draw(tex, base);
      const PT = R.patches || {}, pick = mouth === 'none' || open < .15 ? null
        : PT.round && wide < -.3 ? 'round' : PT.small && open < .5 ? 'small' : PT.open ? 'open' : PT.small ? 'small' : null;
      const lay = (k) => {
        const pt = PT[k], im = SK.IMG['rig:' + name + ':' + k]; if (!pt || !im) return;
        ctx.drawImage(toned(im, tone === 'news' ? 'mono' : tone, name + ':' + k, null, null, true), pt.x, pt.y, pt.w, pt.h);
      };
      if (pick) lay(pick);
      if (blink > .5) lay('blink');
      ctx.restore();
      return { x, y, h, open };
    }
    if (mouth === 'none' || mouth === 'warp' || open <= .003) {
      draw(tex, base);
      if (mouth === 'warp' && (open > .003 || Math.abs(wide) > .02)) {
        const Q = moved(R, open, wide, 0, J);
        const up = LIP_IU.map(i => Q[i]), lo = LIP_IL.map(i => Q[i]);
        cavity(ctx, up, lo, open, tone, R, dn, up);
        warp(ctx, tex, texO, texS, R.mesh.p, Q, meshSets(R).jawT);
      }
    } else if (mouth === 'flap') {
      // the top of the head lifts off at the lips like a lid, tipping back a little
      const line = R.cut.flap.cut, far = F.h * 3, lift = F.h * .16 * open, ang = -open * .09;
      const pivot = line[line.length - 1], rt = F.right;
      // everything above the cut, out past both sides (a head is wider at the ears than at
      // the mouth, and what is left beside the lid would stay behind when it lifts)
      const L0 = add(line[0], rt, -far), L1 = add(pivot, rt, far);
      const upperPoly = [L0, ...line, L1, add(L1, dn, -far), add(L0, dn, -far)].map(toTex);
      const upP = piece(tex, upperPoly, true, base + ':flapU'), loP = piece(tex, upperPoly, false, base + ':flapL');
      const mv = (p) => add(rot(p, pivot, ang), dn, -lift);
      draw(loP, base + ':flapL');
      cavity(ctx, line.map(mv), line, open, tone, R, dn, line.slice(1, -1).map(mv));
      ctx.save(); ctx.translate(-dn[0] * lift, -dn[1] * lift);
      ctx.translate(pivot[0], pivot[1]); ctx.rotate(ang); ctx.translate(-pivot[0], -pivot[1]);
      draw(upP, base + ':flapU'); ctx.restore();
    } else {
      // a rigid jaw piece drops over the whole picture: for a cut-out everything under the cut
      // between its ends (the silhouette bounds it); in a photo the outline's own polygon, so
      // the neck stays put. The picture stays whole underneath, so the cut leaves no seam.
      const key = mouth === 'muppet' ? 'chin' : 'dummy', cutL = R.cut[key].cut, d = J * open, far = F.h * 2;
      let poly = R.cut[key].poly;
      if (cut) {
        const sl = R.cut.dummy.slits;
        poly = key === 'dummy' ? [...cutL, sl[1][1], add(sl[1][1], dn, far), add(sl[0][1], dn, far), sl[0][1]]
          : [...cutL, add(cutL[cutL.length - 1], dn, far), add(cutL[0], dn, far)];
      }
      const pk = base + ':' + key + (cut ? 'c' : 'p');
      const jawP = piece(tex, poly.map(toTex), true, pk + ':jaw');
      const lower = cutL.map(p => add(p, dn, d));
      draw(tex, base);
      cavity(ctx, cutL, lower, open, tone, R, dn, key === 'dummy' ? cutL : cutL.slice(1, -1));
      // the jaw is the same sheet as the face: no shadow of its own on it
      ctx.save(); ctx.translate(dn[0] * d, dn[1] * d); draw(jawP, pk + ':jaw', true); ctx.restore();
      if (mouth === 'dummy') {
        ctx.strokeStyle = 'rgba(25,16,12,.6)'; ctx.lineWidth = F.h * .006; ctx.lineCap = 'round';
        for (const s of R.cut.dummy.slits) { ctx.beginPath(); ctx.moveTo(s[0][0] + dn[0] * d, s[0][1] + dn[1] * d); ctx.lineTo(s[1][0] + dn[0] * d, s[1][1] + dn[1] * d); ctx.stroke(); }
      }
    }
    if (blink > .01) warp(ctx, tex, texO, texS, R.mesh.p, moved(R, 0, 0, blink, 0), meshSets(R).eyeT);
    ctx.restore();
    return { x, y, h, open };
  };
})();
