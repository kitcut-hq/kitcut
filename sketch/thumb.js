/* sketch/thumb.js -- a YouTube thumbnail drawn by the film itself (scripts/_thumb.py).

   Run before the film's code (the manifest's `head`) for thumbnail stills only -- never in a
   film's own render. Two jobs:

   - The probe. Every SK.txt, SK.card and SK.image the film draws is noted: the fonts, weights,
     sizes and colours of its text, the fill, corners and outline of its cards, the pictures it
     shows (a logo, a product) and how large. With the palette (SK.C), the ground and the style
     (crayon or clean), SK.REPORT() returns it after the stills: the film's own design language,
     read off the film rather than guessed. _thumb.py picks the thumbnail's type and colours from
     it -- so an editorial film in Source Serif gets a Source Serif headline, not a stock one.
   - The overlay. SK.THUMB.options, keyed by a still's time ("12.10"), says what to add, already
     laid out by _thumb.py with the same font files: lines of words (runs in the film's ink and
     its accent), a card in the film's own card style, a panel of its paper with a rule of its
     accent, its logo, a soft glow of its paper behind words on a busy picture, the camera slid or
     pushed in. A still's time picks the pass:
         t          the film alone
         1000 + t   the thumbnail
         2000 + t   its letters, white on black (what the legibility and contrast checks read)
         3000 + t   everything it added, white on black (what may not cover the film's own words)

   Every frame stays a pure function of t: nothing here keeps state between stills but the probe's
   tally, which only describes what was drawn.
*/
(function () {
  'use strict';
  const T = (SK.THUMB = SK.THUMB || { options: {} });
  const seen = { txt: {}, card: {}, img: {} };
  let own = false; // the overlay's own drawing is not the film's

  // ------------------------------------------------------------------ the probe
  const txt0 = SK.txt, card0 = SK.card, image0 = SK.image;
  SK.txt = function (str, x, y, o = {}) {
    const s = String(str ?? '');
    if (!own && s.trim()) {
      const col = o.col ?? SK.C.text ?? SK.C.ink;
      if (typeof col === 'string') {
        const font = o.font ?? SK.FONT_HAND, wt = String(o.wt ?? 700), size = o.size ?? 60;
        const k = font + '|' + wt + '|' + col;
        const e = seen.txt[k] || (seen.txt[k] = { font, wt, col, max: 0, n: 0, chars: 0, stroke: null });
        e.max = Math.max(e.max, size); e.n++; e.chars += s.length;
        if (o.stroke) e.stroke = { w: o.stroke / size, col: o.strokeCol ?? SK.C.ink };
      }
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
    return card0.apply(this, arguments);
  };
  SK.image = function (name, x, y, w, h, o = {}) {
    if (!own) { const e = seen.img[name] || (seen.img[name] = { n: 0, w: 0 }); e.n++; e.w = Math.max(e.w, w || 0); }
    return image0.apply(this, arguments);
  };
  SK.REPORT = () => ({
    C: Object.fromEntries(Object.entries(SK.C).filter(([, v]) => typeof v === 'string')),
    ground: SK.ground ? SK.ground.name : null,
    style: { boil: !!SK.style.boil, textMode: SK.style.textMode, paper: SK.style.paper, grain: SK.style.grain },
    hand: SK.FONT_HAND,
    txt: Object.values(seen.txt),
    card: Object.values(seen.card),
    img: seen.img,
    images: Object.keys(SK.IMG || {}),
  });

  // ------------------------------------------------------------------ the passes
  const cur = () => (T.mode ? T.options[T.key] : null);
  const render0 = SK.render;
  SK.render = function (t) {
    const mode = Math.floor(t / 1000), real = t - mode * 1000;
    T.mode = mode; T.key = real.toFixed(2);
    // the masks are exact white on black: no grain or vignette over them
    const st = SK.style, keep = { grain: st.grain, vignette: st.vignette };
    if (mode >= 2) { st.grain = 0; st.vignette = 0; }
    try { return render0.call(this, real); } finally { Object.assign(st, keep); T.mode = 0; }
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
    const over0 = F.overlay;
    F.overlay = function (t) {
      if (over0) over0(t);
      const o = cur();
      if (o) { own = true; try { draw(o, T.mode); } finally { own = false; } }
    };
  };

  // ------------------------------------------------------------------ the overlay
  const ctx = () => SK.ctx();
  function lines(o, mode) {
    const c = ctx();
    for (const L of o.lines || []) {
      c.save();
      if (L.rot) { c.translate(L.cx, L.cy); c.rotate(L.rot); c.translate(-L.cx, -L.cy); }
      c.font = `${L.wt} ${L.size}px "${L.family}"`;
      // held to the width _thumb.py planned with the same font file: a page that draws it wider
      // (its own kerning, a weight it synthesises) is trimmed to fit, so the words stay in their box
      const all = (L.runs || []).map((r) => r.text).join('');
      const drawn = c.measureText(all).width;
      if (L.w && drawn > L.w * 1.005) c.font = `${L.wt} ${(L.size * L.w) / drawn}px "${L.family}"`;
      c.textBaseline = 'alphabetic';
      c.textAlign = 'left';
      let x = L.x;
      for (const r of L.runs) {
        if (mode === 1 && L.stroke) {
          c.lineJoin = 'round'; c.lineWidth = L.stroke.w; c.strokeStyle = L.stroke.col; c.strokeText(r.text, x, L.y);
        }
        c.fillStyle = mode === 1 ? r.col : '#ffffff';
        c.fillText(r.text, x, L.y);
        x += c.measureText(r.text).width;
      }
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
  function card(k, mode) {
    const c = ctx();
    c.save();
    if (k.rot) { c.translate(k.x + k.w / 2, k.y + k.h / 2); c.rotate(k.rot); c.translate(-(k.x + k.w / 2), -(k.y + k.h / 2)); }
    if (mode === 3) { SK.rrPath(k.x, k.y, k.w, k.h, k.r); c.fillStyle = '#ffffff'; c.fill(); }
    else {
      SK.card(k.x, k.y, k.w, k.h, { r: k.r, fill: k.fill, stroke: k.sketch ? null : k.stroke, strokeW: k.strokeW, shadow: k.shadow ? undefined : false });
      if (k.sketch) SK.sketchRect(k.x, k.y, k.w, k.h, { seed: 7, col: k.stroke || SK.C.ink, w: k.strokeW || 3 });
    }
    c.restore();
  }
  function draw(o, mode) {
    const c = ctx();
    c.save();
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalAlpha = 1;
    if (mode >= 2) { c.fillStyle = '#000000'; c.fillRect(0, 0, SK.W, SK.H); }
    if (o.panel) {
      if (mode !== 2) { c.fillStyle = mode === 3 ? '#ffffff' : o.panel.fill; c.fillRect(o.panel.x, 0, o.panel.w, SK.H); }
      if (mode === 1 && o.panel.rule) { c.fillStyle = o.panel.rule.col; c.fillRect(o.panel.rule.x, 0, o.panel.rule.w, SK.H); }
    }
    if (o.glow && mode === 1) glow(o.glow);
    if (o.glow && mode === 3) { SK.rrPath(o.glow.x, o.glow.y, o.glow.w, o.glow.h, o.glow.r); c.fillStyle = '#ffffff'; c.fill(); }
    for (const k of o.cards || []) if (mode !== 2) card(k, mode);
    if (o.logo && mode !== 2) {
      if (mode === 3) { c.fillStyle = '#ffffff'; c.fillRect(o.logo.x, o.logo.y - o.logo.h / 2, o.logo.w, o.logo.h); }
      else SK.image(o.logo.name, o.logo.x, o.logo.y, o.logo.w, 0, { align: 'left' });
    }
    lines(o, mode);
    c.restore();
  }
})();
