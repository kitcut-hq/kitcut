/* sketch/thumb.js -- a YouTube thumbnail drawn by the film itself (scripts/_thumb.py).

   Run before the film's code (the manifest's `head`) for thumbnail stills only -- never in a
   film's own render. Four jobs:

   - The probe. Every SK.txt, SK.card and SK.image the film draws is noted -- and, on a collage
     film, every SK.headline, SK.tape and SK.cutout (collage.js sets its titles and labels with
     those, never with SK.txt): the fonts, weights, sizes, colours, outlines and case of its text,
     the fill, corners and outline of its cards, the colours of its label strips, the pictures it
     shows (a logo, a product, a clay character) and how large. With the palette (SK.C), the
     ground and the style (crayon or clean), SK.REPORT() returns it after the stills: the film's
     own design language, read off the film rather than guessed. _thumb.py picks the thumbnail's
     type and colours from it -- so a collage film in Oswald with an indigo outline gets an Oswald
     headline with that outline, not the handwriting it uses for asides.
   - The clean picture. A thumbnail carries one message, so the film's own words -- its titles,
     labels, stamps, annotation arrows -- are left out of the picture under it (`declutter` on an
     option; always on the 4000 pass). The pictures stay: characters, objects, cards, charts. Small
     print (under SK.THUMB.minWords px: an app's own screen) stays too, as texture. Where each
     picture landed on the 4000 pass is recorded (SK.REPORT().boxes): the subjects, exactly, on a
     film that shows cut-outs, where saliency has to guess on a drawn one.
   - The overlay. SK.THUMB.options, keyed by a still's time ("12.10"), says what to add, already
     laid out by _thumb.py with the same font files: lines of words (runs in the film's ink and
     its accent, in its outline), a card in the film's own card style or a strip like its labels, a
     panel of its paper with a rule of its accent, its logo as a badge, a soft glow of its paper
     behind words on a busy picture, the camera slid or pushed in. A still's time picks the pass:
         t          the film alone
         1000 + t   the thumbnail
         2000 + t   its letters, white on black (what the legibility and contrast checks read)
         3000 + t   everything it added, white on black (what may not cover the film's own words)
         4000 + t   the film with its own words left out, nothing added (what the layout reads)
         5000 + t   the stage: the film's ground and pages, nothing on them
   - The poster. A film that shows pictures is not given a frame of itself but a poster composed
     from them. With `stage` on an option the film draws only its stage (its ground, a sheet of
     paper as large as the frame's better part, the dots printed on it); on that, the option's
     `scene` -- pieces back to front, each drawn the way the film draws its own: a cut-out with
     the shadow paper casts, a print with a paper border, a starburst or a disc of paper -- then
     the words and the logo as above. Which pieces, where and how large is _thumb.py's template.

   Every frame stays a pure function of t: nothing here keeps state between stills but the probe's
   tally and the boxes, which only describe what was drawn.
*/
(function () {
  'use strict';
  const T = (SK.THUMB = SK.THUMB || { options: {} });
  T.options = T.options || {};
  T.minWords = T.minWords ?? 34; // px: film text this size and up is a word a viewer reads
  T.pageMin = T.pageMin ?? .45; // of the frame: a sheet of paper this large is a page, the film's stage
  const seen = { txt: {}, card: {}, img: {}, strip: {} };
  const boxes = {};
  let own = false; // the overlay's own drawing is not the film's
  let sheetN = {}; // how many sheets of each size and colour this frame has drawn so far
  let inside = 0; // inside one of the film's word-drawing calls (a ransom's letters are tapes)

  // ------------------------------------------------------------------ the pass and the option
  const cur = () => (T.mode && T.mode < 4 ? T.options[T.key] : null);
  const clean = () => !own && (T.mode === 4 || !!(cur() && cur().declutter));
  const staged = () => !own && hushed > 0 && (T.mode === 5 || !!(cur() && cur().stage));

  // Everything drawn on the frame's canvas inside fn is dropped; what fn works out (a width it
  // returns, the caches it fills) is not. Its own offscreen canvases are other contexts, so a
  // cached title still gets made -- it just never reaches the frame.
  const HUSH = ['fillText', 'strokeText', 'drawImage', 'fill', 'stroke', 'fillRect', 'strokeRect', 'putImageData'];
  let hushed = 0, had = null;
  const mute = (c) => { had = HUSH.map((k) => Object.getOwnPropertyDescriptor(c, k)); for (const k of HUSH) c[k] = () => {}; };
  const unmute = (c) => { HUSH.forEach((k, i) => { if (had[i]) Object.defineProperty(c, k, had[i]); else delete c[k]; }); };
  function hush(fn) {
    if (hushed) return fn();
    const c = SK.ctx();
    mute(c); hushed++;
    try { return fn(); } finally { hushed--; unmute(c); }
  }
  // inside a hush, fn draws after all: the stage under a poster (a page of paper, its printed dots)
  function loud(fn) {
    if (!hushed) return fn();
    const c = SK.ctx(), n = hushed;
    unmute(c); hushed = 0;
    try { return fn(); } finally { mute(c); hushed = n; }
  }
  // A film may draw one of its pictures itself (a print it frames by hand: c.drawImage(SK.IMG.x)),
  // past SK.image and SK.cutout: on the 4000 pass every picture of the film's that reaches the
  // frame's canvas outside those two is noted as well -- the probe's tally and where it landed.
  let inBoxed = 0;
  function rawImages() {
    const c = SK.ctx(), was = Object.getOwnPropertyDescriptor(c, 'drawImage'), d0 = c.drawImage;
    const names = new Map(Object.entries(SK.IMG || {}).map(([n, im]) => [im, n]));
    c.drawImage = function (im, ...a) {
      const name = inBoxed || own ? null : names.get(im);
      if (name) {
        let x, y, w, h;
        if (a.length >= 8) [, , , , x, y, w, h] = a;
        else if (a.length >= 4) [x, y, w, h] = a;
        else { [x, y] = a; w = im.width; h = im.height; }
        sawImage(name, w);
        note4({ name, box: onScreen(x, y, x + w, y + h) });
      }
      return d0.apply(c, [im, ...a]);
    };
    return () => { if (was) Object.defineProperty(c, 'drawImage', was); else delete c.drawImage; };
  }
  // where fn's drawImage calls land on the frame, as one box in canvas pixels (the 4000 pass)
  function boxed(name, fn) {
    if (T.mode !== 4 || own || hushed) return fn();
    inBoxed++;
    try { return boxed0(name, fn); } finally { inBoxed--; }
  }
  function boxed0(name, fn) {
    const c = SK.ctx(), had = Object.getOwnPropertyDescriptor(c, 'drawImage'), d0 = c.drawImage;
    let b = null;
    c.drawImage = function (im, ...a) {
      let x, y, w, h;
      if (a.length >= 8) [, , , , x, y, w, h] = a;
      else if (a.length >= 4) [x, y, w, h] = a;
      else { [x, y] = a; w = im.width; h = im.height; }
      const m = c.getTransform();
      for (const [px, py] of [[x, y], [x + w, y], [x, y + h], [x + w, y + h]]) {
        const X = m.a * px + m.c * py + m.e, Y = m.b * px + m.d * py + m.f;
        b = b ? [Math.min(b[0], X), Math.min(b[1], Y), Math.max(b[2], X), Math.max(b[3], Y)] : [X, Y, X, Y];
      }
      return d0.apply(c, [im, ...a]);
    };
    try { return fn(); } finally {
      if (had) Object.defineProperty(c, 'drawImage', had); else delete c.drawImage;
      if (b) (boxes[T.key] = boxes[T.key] || []).push({ name, box: b.map((v) => Math.round(v)) });
    }
  }

  // a local box (x0, y0, x1, y1) where the frame's canvas has it now, in canvas pixels
  function onScreen(x0, y0, x1, y1) {
    const m = SK.ctx().getTransform();
    let b = null;
    for (const [px, py] of [[x0, y0], [x1, y0], [x0, y1], [x1, y1]]) {
      const X = m.a * px + m.c * py + m.e, Y = m.b * px + m.d * py + m.f;
      b = b ? [Math.min(b[0], X), Math.min(b[1], Y), Math.max(b[2], X), Math.max(b[3], Y)] : [X, Y, X, Y];
    }
    return b.map((v) => Math.round(v));
  }
  const note4 = (e) => { (boxes[T.key] = boxes[T.key] || []).push(e); };
  // the id of a call, by its arguments: the same at the same t on every pass
  const idOf = (...a) => a.map((v) => (typeof v === 'number' ? Math.round(v * 10) / 10 : String(v ?? ''))).join('|');

  // ------------------------------------------------------------------ the probe
  const LETTER = /\p{L}/u, UPPER = /\p{Lu}/u;
  function note(kind, s, font, wt, size, col, stroke, ls) {
    if (own || inside || typeof col !== 'string') return;
    const k = [kind, font, wt, col, stroke ? stroke.col : ''].join('|');
    const e = seen.txt[k] || (seen.txt[k] = { kind, font, wt: String(wt), col, max: 0, n: 0, chars: 0, letters: 0, upper: 0, stroke: null, ls: 0 });
    e.max = Math.max(e.max, size); e.n++; e.chars += s.length;
    for (const ch of s) if (LETTER.test(ch)) { e.letters++; if (UPPER.test(ch)) e.upper++; }
    if (stroke) e.stroke = stroke;
    if (ls) e.ls = Math.max(e.ls, ls / size);
  }
  const face = (fam, wt, s) => (typeof SK.face === 'function' ? SK.face(fam, wt, s) : [fam, wt]);

  const txt0 = SK.txt, card0 = SK.card, image0 = SK.image;
  SK.txt = function (str, x, y, o = {}) {
    const s = String(str ?? '');
    const size = o.size ?? 60;
    if (s.trim()) {
      note('txt', s, o.font ?? SK.FONT_HAND, o.wt ?? 700, size, o.col ?? SK.C.text ?? SK.C.ink,
        o.stroke ? { w: o.stroke / size, col: o.strokeCol ?? SK.C.ink } : null, o.ls);
    }
    if (s.trim() && clean() && size >= T.minWords) {
      if (T.mode === 4 && !own && !hushed) note4({ name: '#words', box: onScreen(x - 1, y - 1, x + 1, y + 1) });
      return hush(() => txt0.apply(this, arguments));
    }
    return txt0.apply(this, arguments);
  };
  SK.card = function (x, y, w, h, o = {}) {
    if (!own && w > 60 && h > 30 && typeof (o.fill ?? '#ffffff') === 'string') {
      const fill = o.fill ?? '#ffffff', r = o.r ?? 18, shadow = o.shadow !== false;
      const k = [fill, r, o.stroke ?? '', shadow].join('|');
      const e = seen.card[k] || (seen.card[k] = { fill, r, stroke: o.stroke ?? null, strokeW: o.strokeW ?? 2, shadow, n: 0, area: 0 });
      e.n++; e.area += w * h;
    }
    if (!own && !hushed && w > 60 && h > 30) {
      const id = idOf(x, y, w, h, o.fill);
      const opt = cur();
      // a card that only carried words the clean picture leaves out: an empty slab (_thumb.py)
      if (opt && opt.hide && opt.hide.includes('card|' + id)) return hush(() => card0.apply(this, arguments));
      // a card the words over the picture should not cut across (an app's calendar, a letter)
      if (T.mode === 4 && (o.alpha ?? 1) > 0) note4({ name: '#card', id: 'card|' + id, box: onScreen(x, y, x + w, y + h) });
    }
    return card0.apply(this, arguments);
  };
  function sawImage(name, w) {
    if (own) return;
    const e = seen.img[name] || (seen.img[name] = { n: 0, w: 0 });
    e.n++; e.w = Math.max(e.w, w || 0);
  }
  SK.image = function (name, x, y, w, h, o = {}) {
    sawImage(name, w);
    return boxed(name, () => image0.apply(this, arguments));
  };

  // collage.js (a film's `modules`): loaded before this, so its functions are here to wrap
  if (typeof SK.headline === 'function') {
    const head0 = SK.headline;
    SK.headline = function (text, x, y, o = {}) {
      const s = String(text ?? ''), size = o.size ?? 90, [fam, wt] = face(o.font ?? 'Abril Fatface', o.wt ?? 400, s);
      if (s.trim()) note('headline', s.replace(/\n/g, ' '), fam, wt, size, o.col ?? '#1d1a17',
        o.stroke ? { w: (o.stroke.w ?? 0) / size, col: o.stroke.col ?? '#fff' } : null, o.ls);
      if (clean() && T.mode === 4 && !own && !hushed && s.trim()) note4({ name: '#words', box: onScreen(x - 1, y - 1, x + 1, y + 1) });
      return clean() ? hush(() => head0.apply(this, arguments)) : head0.apply(this, arguments);
    };
  }
  if (typeof SK.tape === 'function') {
    const tape0 = SK.tape;
    SK.tape = function (text, x, y, o = {}) {
      const s = String(text ?? ''), size = o.size ?? 36, [fam, wt] = face(o.font ?? 'Oswald', o.wt ?? 600, s);
      const col = o.col ?? '#f3ce4f', ink = o.ink ?? (SK.inkOn ? SK.inkOn(col) : '#1d1a17');
      if (s.trim() && !own && !inside && typeof col === 'string' && typeof ink === 'string') {
        note('tape', s.replace(/\n/g, ' '), fam, wt, size, ink, null, o.ls);
        const k = col + '|' + ink + '|' + fam + '|' + wt;
        const e = seen.strip[k] || (seen.strip[k] = { col, ink, font: fam, wt: String(wt), n: 0, chars: 0, max: 0 });
        e.n++; e.chars += s.length; e.max = Math.max(e.max, size);
      }
      return clean() ? hush(() => tape0.apply(this, arguments)) : tape0.apply(this, arguments);
    };
  }
  for (const name of ['ransom', 'stamp', 'arrow', 'mark']) { // words, and what points at them
    if (typeof SK[name] !== 'function') continue;
    const f0 = SK[name];
    SK[name] = function () {
      inside++;
      try { return clean() ? hush(() => f0.apply(this, arguments)) : f0.apply(this, arguments); } finally { inside--; }
    };
  }
  // A starburst or a paper disc is a backing: for a clay character (kept) or for a number or a
  // stamp the clean picture leaves out (then an empty paper circle). The 4000 pass notes each one,
  // by the arguments it was called with -- the same at the same t on every pass -- and where it
  // landed; _thumb.py names the ones with no picture on them in the option's `hide`.
  if (typeof SK.burst === 'function') {
    const burst0 = SK.burst;
    SK.burst = function (x, y, r, o = {}) {
      if (own || hushed) return burst0.apply(this, arguments);
      const id = idOf(x, y, r, o.seed, o.col), opt = cur();
      if (opt && opt.hide && opt.hide.includes(id)) return hush(() => burst0.apply(this, arguments));
      if (T.mode === 4) note4({ name: '#burst', id, box: onScreen(x - r, y - r, x + r, y + r) });
      return burst0.apply(this, arguments);
    };
  }
  // The stage: what a poster is set on. With `stage` on an option (and on the 5000 pass) the film
  // draws nothing but its ground and what lies flat on it -- a sheet of paper as large as the
  // frame's better part (a collage film's page), the dots printed on it, a newspaper under it all.
  // The 5000 pass notes each page: where it landed and its colour.
  for (const name of ['halftone', 'newsprint']) {
    if (typeof SK[name] !== 'function') continue;
    const f0 = SK[name];
    SK[name] = function () { return staged() ? loud(() => f0.apply(this, arguments)) : f0.apply(this, arguments); };
  }
  if (typeof SK.sheet === 'function') {
    const sheet0 = SK.sheet;
    SK.sheet = function (x, y, w, h, o = {}) {
      if (!staged()) {
        // A sheet smaller than a page is a card of paper (a list, a note) or a strip along an
        // edge: noted on the 4000 pass like SK.card's, and left out when an option's `hide`
        // names it (a card whose words are out is a blank slab). Its id is its size and colour
        // and which one of those it is in the frame's own drawing order -- the same on every
        // pass, where its place on screen is not (the camera's push moves it).
        if (own || hushed || w * h >= T.pageMin * SK.W * SK.H) return sheet0.apply(this, arguments);
        const key = idOf(w, h, o.col), n = (sheetN[key] = (sheetN[key] || 0) + 1), id = 'sheet|' + key + '#' + n;
        const opt = cur();
        if (opt && opt.hide && opt.hide.includes(id)) return hush(() => sheet0.apply(this, arguments));
        if (T.mode === 4 && (o.alpha ?? 1) > 0) note4({ name: '#card', id, box: onScreen(x - w / 2, y - h / 2, x + w / 2, y + h / 2) });
        return sheet0.apply(this, arguments);
      }
      const b = onScreen(x - w / 2, y - h / 2, x + w / 2, y + h / 2);
      const seen = Math.max(0, Math.min(SK.W, b[2]) - Math.max(0, b[0])) * Math.max(0, Math.min(SK.H, b[3]) - Math.max(0, b[1]));
      if (seen < T.pageMin * SK.W * SK.H) return sheet0.apply(this, arguments);
      if (T.mode === 5) (boxes['P' + T.key] = boxes['P' + T.key] || []).push({ name: '#page', box: b, col: o.col ?? '#e8dcc2' });
      return loud(() => sheet0.apply(this, arguments));
    };
  }
  if (typeof SK.cutout === 'function') {
    const cut0 = SK.cutout;
    SK.cutout = function (name, x, y, w, o = {}) {
      sawImage(name, w);
      return boxed(name, () => cut0.apply(this, arguments));
    };
  }

  SK.REPORT = () => ({
    C: Object.fromEntries(Object.entries(SK.C).filter(([, v]) => typeof v === 'string')),
    ground: SK.ground ? SK.ground.name : null,
    style: { boil: !!SK.style.boil, textMode: SK.style.textMode, paper: SK.style.paper, grain: SK.style.grain },
    hand: SK.FONT_HAND,
    txt: Object.values(seen.txt),
    card: Object.values(seen.card),
    strip: Object.values(seen.strip),
    img: seen.img,
    images: Object.keys(SK.IMG || {}),
    boxes,
  });

  // ------------------------------------------------------------------ the passes
  const render0 = SK.render;
  SK.render = function (t) {
    const mode = Math.floor(t / 1000), real = t - mode * 1000;
    T.mode = mode; T.key = real.toFixed(2);
    sheetN = {};
    if (mode === 4) boxes[T.key] = [];
    if (mode === 5) boxes['P' + T.key] = [];
    // the masks are exact white on black: no grain or vignette over them
    const st = SK.style, keep = { grain: st.grain, vignette: st.vignette };
    if (mode === 2 || mode === 3) { st.grain = 0; st.vignette = 0; }
    const unhook = mode === 4 ? rawImages() : null;
    try { return render0.call(this, real); } finally { if (unhook) unhook(); Object.assign(st, keep); T.mode = 0; }
  };
  const film0 = SK.film;
  SK.film = function (def) {
    film0.call(this, def);
    const F = SK._film;
    // a slide or a push of the camera: the film draws itself there, nothing is stretched
    const at0 = F.camera.at;
    F.camera = {
      ...F.camera,
      at(t) {
        const [x, y, z] = at0(t), o = cur();
        if (!o || !o.camera) return [x, y, z];
        const zz = z * (o.camera.zoom || 1), cx = o.camera.cx ?? SK.W / 2, cy = o.camera.cy ?? SK.H / 2;
        const k = 1 - 1 / (o.camera.zoom || 1); // a push keeps the point it pushes toward in place
        return [x + (cx - SK.W / 2) / z * k - (o.camera.shift || 0) / zz, y + (cy - SK.H / 2) / z * k, zz];
      },
    };
    const draw0 = F.draw;
    F.draw = function (t, vis) {
      const o = cur();
      return T.mode === 5 || (o && o.stage) ? hush(() => draw0.call(this, t, vis)) : draw0.call(this, t, vis);
    };
    const over0 = F.overlay;
    F.overlay = function (t) {
      const o = cur();
      if (over0 && T.mode !== 5 && !(o && o.stage)) over0(t);
      if (o) { own = true; try { draw(o, T.mode); } finally { own = false; } }
    };
  };

  // ------------------------------------------------------------------ the overlay
  const ctx = () => SK.ctx();
  const RTL = /[֐-ࣿיִ-﷿ﹰ-ﻼ]/;
  function lines(o, mode) {
    const c = ctx();
    for (const L of o.lines || []) {
      c.save();
      if (L.rot) { c.translate(L.cx, L.cy); c.rotate(L.rot); c.translate(-L.cx, -L.cy); }
      // a slant: the line sheared about its baseline, in every pass (the masks match the picture)
      if (L.skew) { c.translate(0, L.y); c.transform(1, 0, -Math.tan(L.skew), 1, 0, 0); c.translate(0, -L.y); }
      c.font = `${L.wt} ${L.size}px "${L.family}"`;
      c.letterSpacing = (L.ls || 0) + 'px';
      // held to the width _thumb.py planned with the same font file: a page that draws it wider
      // (its own kerning, a weight it synthesises) is trimmed to fit, so the words stay in their box
      const all = (L.runs || []).map((r) => r.text).join('');
      // a line in a script written right to left: its first word stands at the right, each run
      // to the left of the one before (a run's own letters the browser sets in their order)
      const rtl = RTL.test(all);
      c.direction = rtl ? 'rtl' : 'ltr';
      let drawn = c.measureText(all).width;
      if (L.w && drawn > L.w * 1.005) { c.font = `${L.wt} ${(L.size * L.w) / drawn}px "${L.family}"`; drawn = L.w; }
      c.textBaseline = 'alphabetic';
      c.textAlign = 'left';
      // drawn narrower than planned (letters that join, a kern): kept where its anchor put it
      const slack = Math.max(0, (L.w || drawn) - drawn);
      const x0 = L.x + (L.anchor === 'middle' ? slack / 2 : L.anchor === 'end' ? slack : 0);
      const at = [];
      let x = rtl ? x0 + drawn : x0;
      for (const r of L.runs) {
        const w = c.measureText(r.text).width;
        if (rtl) x -= w;
        at.push(x);
        if (!rtl) x += w;
      }
      if (mode === 1 && L.shadow) { // under everything: a soft dark, then the hard drop a cover's words stand on
        const s = L.shadow;
        if (s.blur) {
          c.save(); c.shadowColor = s.col; c.shadowBlur = s.blur; c.shadowOffsetX = s.dx * .5; c.shadowOffsetY = s.dy * .5;
          c.fillStyle = s.col;
          for (let k = 0; k < (s.passes || 1); k++) L.runs.forEach((r, i) => c.fillText(r.text, at[i], L.y));
          c.restore();
        }
        c.fillStyle = s.col;
        // a hard drop is the letters again, a step at a time down to the offset: no gap at a corner
        const n = Math.max(1, Math.ceil(Math.hypot(s.dx, s.dy) / 2));
        for (let k = 1; k <= n; k++) L.runs.forEach((r, i) => c.fillText(r.text, at[i] + s.dx * k / n, L.y + s.dy * k / n));
      }
      if (mode === 1 && L.stroke) { // the outline under every run first, so no run's edge cuts the next
        c.lineJoin = 'round'; c.lineWidth = L.stroke.w; c.strokeStyle = L.stroke.col;
        L.runs.forEach((r, i) => c.strokeText(r.text, at[i], L.y));
      }
      L.runs.forEach((r, i) => {
        let fill = r.col;
        if (mode === 1 && r.grad) { // top of the capitals to the baseline
          fill = c.createLinearGradient(0, L.y - (L.cap || L.size * .7), 0, L.y);
          fill.addColorStop(0, r.grad[0]); fill.addColorStop(1, r.grad[1]);
        }
        c.fillStyle = mode === 1 ? fill : '#ffffff';
        c.fillText(r.text, at[i], L.y);
      });
      c.restore();
    }
  }
  function glow(g) {
    const c = ctx();
    c.save();
    c.filter = `blur(${g.blur}px)`;
    c.globalAlpha = g.alpha;
    SK.rrPath(g.x, g.y, g.w, g.h, g.r);
    c.fillStyle = g.col;
    c.fill();
    c.restore();
  }
  // a strip like the film's own labels (collage.js's tape): cut paper, a slight tilt, a shadow
  function strip(k) {
    const c = ctx(), w = k.w, h = k.h;
    c.save();
    c.translate(k.x + w / 2, k.y + h / 2);
    if (k.rot) c.rotate(k.rot);
    const path = () => {
      c.beginPath();
      c.moveTo(-w / 2 + 1, -h / 2); c.lineTo(w / 2 - 2, -h / 2 + 2); c.lineTo(w / 2 - 1, h / 2); c.lineTo(-w / 2 + 2, h / 2 - 1);
      c.closePath();
    };
    c.save(); c.shadowColor = 'rgba(30,20,10,.32)'; c.shadowBlur = h * .08; c.shadowOffsetY = h * .035;
    path(); c.fillStyle = k.fill; c.fill(); c.restore();
    if (typeof SK.paperPattern === 'function') { c.save(); path(); c.clip(); c.fillStyle = SK.paperPattern(k.fill, .7); c.fillRect(-w, -h, 2 * w, 2 * h); c.restore(); }
    c.restore();
  }
  function card(k, mode) {
    const c = ctx();
    c.save();
    // a poster's strips lean as one stack: each turns about the stack's middle (k.cx, k.cy)
    const px = k.cx ?? k.x + k.w / 2, py = k.cy ?? k.y + k.h / 2;
    if (mode === 3) {
      if (k.rot) { c.translate(px, py); c.rotate(k.rot); c.translate(-px, -py); }
      SK.rrPath(k.x, k.y, k.w, k.h, k.r || 0); c.fillStyle = '#ffffff'; c.fill();
    } else if (k.strip && k.cx !== undefined) {
      if (k.rot) { c.translate(px, py); c.rotate(k.rot); c.translate(-px, -py); }
      strip({ ...k, rot: 0 });
    } else if (k.strip) strip(k);
    else {
      if (k.rot) { c.translate(k.x + k.w / 2, k.y + k.h / 2); c.rotate(k.rot); c.translate(-(k.x + k.w / 2), -(k.y + k.h / 2)); }
      SK.card(k.x, k.y, k.w, k.h, { r: k.r, fill: k.fill, stroke: k.sketch ? null : k.stroke, strokeW: k.strokeW, shadow: k.shadow ? undefined : false });
      if (k.sketch) SK.sketchRect(k.x, k.y, k.w, k.h, { seed: 7, col: k.stroke || SK.C.ink, w: k.strokeW || 3 });
    }
    c.restore();
  }
  // the logo: a round paper badge when it is a square picture (how a channel shows its face),
  // else as it is -- a wordmark with its own transparency needs no plate
  function logo(L, mode) {
    const c = ctx(), x = L.x, r = L.w / 2, cx = x + r, cy = L.y;
    if (mode === 3) {
      c.fillStyle = '#ffffff';
      if (L.round) { c.beginPath(); c.arc(cx, cy, r + (L.rim || 0), 0, Math.PI * 2); c.fill(); } else c.fillRect(x, L.y - L.h / 2, L.w, L.h);
      return;
    }
    if (!L.round) { SK.image(L.name, x, L.y, L.w, 0, { align: 'left' }); return; }
    const im = SK.IMG[L.name];
    if (!im) return;
    c.save();
    c.shadowColor = 'rgba(20,10,40,.35)'; c.shadowBlur = r * .18; c.shadowOffsetY = r * .06;
    c.beginPath(); c.arc(cx, cy, r + (L.rim || 0), 0, Math.PI * 2); c.fillStyle = L.rimCol || '#ffffff'; c.fill();
    c.restore();
    c.save();
    c.beginPath(); c.arc(cx, cy, r, 0, Math.PI * 2); c.clip();
    const s = Math.max(L.w / im.width, L.h / im.height); // cover the circle
    c.drawImage(im, cx - im.width * s / 2, cy - im.height * s / 2, im.width * s, im.height * s);
    c.restore();
  }
  // A poster's pieces, back to front, each drawn the way the film draws its own: a cut-out with
  // the shadow paper casts (SK.cutout), a starburst or a disc of paper behind it (SK.burst), dots.
  function star(L, col, r, shadow) {
    if (typeof SK.burst === 'function') {
      SK.burst(L.x, L.y, r, { col, spikes: L.spikes ?? 24, inner: L.inner ?? .8, seed: L.seed ?? 3, rot: L.rot || 0, nudge: 0, shadow: shadow ? undefined : false });
      return;
    }
    const c = ctx(), n = L.spikes ?? 24, inner = L.inner ?? .8;
    c.save(); c.translate(L.x, L.y); c.rotate(L.rot || 0); c.beginPath();
    for (let i = 0; i < 2 * n; i++) { const a = i / (2 * n) * Math.PI * 2, k = i % 2 ? inner : 1; c.lineTo(Math.cos(a) * r * k, Math.sin(a) * r * k); }
    c.closePath();
    if (shadow) { c.shadowColor = 'rgba(40,20,10,.3)'; c.shadowBlur = 16; c.shadowOffsetY = 7; }
    c.fillStyle = col; c.fill(); c.restore();
  }
  function piece(L) {
    const c = ctx();
    if (L.k === 'cut') {
      const im = SK.IMG[L.name];
      if (!im) return;
      if (typeof SK.cutout === 'function') { SK.cutout(L.name, L.x, L.y, L.w, { rot: L.rot || 0, flip: !!L.flip, nudge: 0 }); return; }
      const h = L.w * im.height / im.width, big = Math.max(L.w, h);
      c.save(); c.translate(L.x, L.y); c.rotate(L.rot || 0); if (L.flip) c.scale(-1, 1);
      c.shadowColor = 'rgba(28,18,8,.42)'; c.shadowBlur = big * .028; c.shadowOffsetX = big * .004; c.shadowOffsetY = big * .014;
      c.drawImage(im, -L.w / 2, -h / 2, L.w, h);
      c.restore();
    } else if (L.k === 'print') { // a picture with a ground of its own: a print with a paper border
      const im = SK.IMG[L.name];
      if (!im) return;
      const h = L.w * im.height / im.width, b = L.border || 0, big = Math.max(L.w, h);
      c.save(); c.translate(L.x, L.y); c.rotate(L.rot || 0);
      c.save();
      c.shadowColor = 'rgba(28,18,8,.42)'; c.shadowBlur = big * .028; c.shadowOffsetX = big * .004; c.shadowOffsetY = big * .014;
      c.fillStyle = L.col || '#ffffff'; c.fillRect(-L.w / 2 - b, -h / 2 - b, L.w + 2 * b, h + 2 * b);
      c.restore();
      // its middle, a little enlarged: a painted picture's edges are where it fades or frays
      const z = L.zoom || 1, sw = im.width / z, sh = im.height / z;
      c.drawImage(im, (im.width - sw) / 2, (im.height - sh) / 2, sw, sh, -L.w / 2, -h / 2, L.w, h);
      c.restore();
    } else if (L.k === 'burst') {
      if (L.rim) star(L, L.rim, L.r, true);
      star(L, L.col, L.rim ? L.r * (L.rimIn ?? .92) : L.r, !L.rim);
    } else if (L.k === 'dots' && typeof SK.halftone === 'function') {
      SK.halftone(L.x, L.y, L.w, L.h, { col: L.col, from: L.from || 'c', step: L.step || 20, nudge: 0 });
    }
  }
  // A cover's effects, in the order given: what makes words readable ON a picture, where a quiet
  // place used to be hunted for. Each is the film's own colour doing the work -- its dark as a
  // fade under the words, its accent as a box.
  function effect(e, mode) {
    const c = ctx(), W = SK.W, H = SK.H;
    if (e.k === 'grade') { // the picture a little richer: itself, drawn back through a filter
      if (mode !== 1) return;
      const cv = document.createElement('canvas'); cv.width = c.canvas.width; cv.height = c.canvas.height;
      cv.getContext('2d').drawImage(c.canvas, 0, 0);
      c.save(); c.filter = `saturate(${e.saturate ?? 1}) contrast(${e.contrast ?? 1}) brightness(${e.brightness ?? 1})`;
      c.drawImage(cv, 0, 0, W, H); c.restore();
    } else if (e.k === 'scrim') { // a fade of the film's dark from one side: dark under the words only
      if (mode !== 1) return;
      const s = e.size, v = e.side === 'top' || e.side === 'bottom';
      const g = e.side === 'bottom' ? c.createLinearGradient(0, H - s, 0, H) : e.side === 'top' ? c.createLinearGradient(0, s, 0, 0)
        : e.side === 'left' ? c.createLinearGradient(s, 0, 0, 0) : c.createLinearGradient(W - s, 0, W, 0);
      const [r, gg, b] = [1, 3, 5].map((i) => parseInt(e.col.slice(i, i + 2), 16));
      const at = (a) => `rgba(${r},${gg},${b},${a})`;
      g.addColorStop(0, at(0)); g.addColorStop(e.mid ?? .45, at(e.a * .62)); g.addColorStop(1, at(e.a));
      c.fillStyle = g;
      if (v) c.fillRect(0, e.side === 'bottom' ? H - s : 0, W, s); else c.fillRect(e.side === 'left' ? 0 : W - s, 0, s, H);
    } else if (e.k === 'shade') { // a soft dark behind a block of words set in the scene
      if (mode !== 1) return;
      c.save(); c.filter = `blur(${e.blur}px)`; c.globalAlpha = e.a;
      SK.rrPath(e.x, e.y, e.w, e.h, e.r || 0); c.fillStyle = e.col; c.fill(); c.restore();
    } else if (e.k === 'box') { // a straight solid box under a line (or a band across the frame)
      if (mode === 2) return;
      c.save();
      if (e.rot) { c.translate(e.cx, e.cy); c.rotate(e.rot); c.translate(-e.cx, -e.cy); }
      if (e.skew) { c.translate(0, e.y + e.h); c.transform(1, 0, -Math.tan(e.skew), 1, 0, 0); c.translate(0, -(e.y + e.h)); }
      if (mode === 1 && e.shadow) { c.shadowColor = e.shadow; c.shadowBlur = e.h * .12; c.shadowOffsetY = e.h * .06; }
      c.fillStyle = mode === 3 ? '#ffffff' : e.col; c.fillRect(e.x, e.y, e.w, e.h);
      c.restore();
    } else if (e.k === 'arrow') { // a block arrow, edged in the light colour, at what the words are about
      if (mode !== 1) return;
      const dx = e.x2 - e.x1, dy = e.y2 - e.y1, L = Math.hypot(dx, dy), a = Math.atan2(dy, dx), w = e.w, h = Math.min(L * .5, w * 2.2);
      c.save(); c.translate(e.x1, e.y1); c.rotate(a);
      c.beginPath();
      c.moveTo(0, -w / 2); c.lineTo(L - h, -w / 2); c.lineTo(L - h, -w * 1.25); c.lineTo(L, 0);
      c.lineTo(L - h, w * 1.25); c.lineTo(L - h, w / 2); c.lineTo(0, w / 2); c.closePath();
      c.lineJoin = 'round';
      if (e.rim) { c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = w * .5; c.shadowOffsetY = w * .2; c.lineWidth = w * .45; c.strokeStyle = e.rim; c.stroke(); }
      c.shadowColor = 'transparent'; c.fillStyle = e.col; c.fill();
      c.restore();
    }
  }
  function draw(o, mode) {
    const c = ctx();
    c.save();
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalAlpha = 1;
    if (mode >= 2) { c.fillStyle = '#000000'; c.fillRect(0, 0, SK.W, SK.H); }
    for (const e of o.fx || []) effect(e, mode);
    if (o.panel) {
      if (mode !== 2) { c.fillStyle = mode === 3 ? '#ffffff' : o.panel.fill; c.fillRect(o.panel.x, 0, o.panel.w, SK.H); }
      if (mode === 1 && o.panel.rule) { c.fillStyle = o.panel.rule.col; c.fillRect(o.panel.rule.x, 0, o.panel.rule.w, SK.H); }
    }
    if (mode === 1) for (const L of o.scene || []) piece(L);
    if (o.glow && mode === 1) glow(o.glow);
    if (o.glow && mode === 3) { SK.rrPath(o.glow.x, o.glow.y, o.glow.w, o.glow.h, o.glow.r); c.fillStyle = '#ffffff'; c.fill(); }
    for (const k of o.cards || []) if (mode !== 2) card(k, mode);
    if (o.logo && mode !== 2) logo(o.logo, mode);
    lines(o, mode);
    c.restore();
  }
})();
