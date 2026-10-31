/* captions-layer.js -- a film's captions, drawn: the narration's words a few at a time on a card,
   the word being said in its own colour.

   One file, byte for byte in three places, so the card looks the same wherever it is drawn:
     kitcut   sketch/captions-layer.js  the engine module "captions-layer": sketch/captions.js
                                         draws a film's stills with it, and writes the film's
                                         captions.json beside its video (SK.captionData)
     kitcut   scripts/captions-burn.py  draws it over a finished video's frames (a copy with
                                         captions: a download, YouTube, a chat's preview)
     kitcut.ai /captions-layer.js        the players draw it live over the <video> (attach)
   Change it in kitcut's sketch/ and copy it to the site (and the other way round).

   A film's video is drawn without its captions; captions.json holds its cards (cut from the
   voice timeline), their word times and their look. The look can change after the film is made
   (a preset, three colours, a font) without drawing the film again: style(data, over).

   Plain ES2020, no imports: it sets window.KCCaptions.
*/
(function (root) {
  'use strict';
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const FONT = "'Inter', 'Sofia Sans', sans-serif";

  /** Where the card sits and how much it holds, from the frame's shape. y: the card's centre;
   *  size: the type; w: the widest a line may be; words, chars: a card's most. studio/film.py
   *  caption_band works out the same band (studio/test_shorts.py holds the two equal). */
  function geometry(W, H) {
    return H > W
      ? { y: H * .745, size: W * .061, w: W * .74, words: 4, chars: 22 }  // tall: above a phone's buttons
      : H === W
        ? { y: H * .86, size: W * .05, w: W * .8, words: 5, chars: 28 }
        : { y: H * .885, size: H * .046, w: W * .7, words: 8, chars: 46 };
  }
  const LOOK = {
    font: FONT, weight: 800, lh: 1.2, padX: .42, padY: .26, radius: .32,
    card: 'rgba(17,17,21,.86)', ink: '#ffffff', said: '#ffe14d', shadow: '',
    lead: .05,  // a card is up this long before its first word, so the eye is there for it
    hold: .25,  // and stays this long after its last, when nothing follows at once
    join: .6,   // a pause shorter than this between two cards is bridged, not blinked
  };
  // What a style may change after the film is made (the rest is tied to the band faces are kept
  // out of, and to the cards' times)
  const STYLE_KEYS = ['card', 'ink', 'said', 'font', 'weight', 'shadow'];
  /** The looks a person picks from on a film's page. "brand" is the film's own (its project's
   *  colours and font when it has a brand or a style); the others are fixed. */
  const PRESETS = {
    classic: { card: LOOK.card, ink: LOOK.ink, said: LOOK.said, font: FONT, weight: 800, shadow: '' },
    plain: { card: 'rgba(0,0,0,0)', ink: '#ffffff', said: '#ffe14d', font: FONT, weight: 800, shadow: 'rgba(0,0,0,.9)' },
    light: { card: 'rgba(255,255,255,.92)', ink: '#16161a', said: '#c2410c', font: FONT, weight: 800, shadow: '' },
  };

  // ---------------------------------------------------------------- colour
  /** [r, g, b, a] of a CSS colour written as #rgb, #rrggbb(aa) or rgb(a)(); null otherwise. */
  function rgba(s) {
    s = String(s || '').trim();
    let m = /^#([0-9a-f]{3,8})$/i.exec(s);
    if (m) {
      let h = m[1];
      if (h.length === 3 || h.length === 4) h = h.split('').map((c) => c + c).join('');
      if (h.length !== 6 && h.length !== 8) return null;
      const n = (i) => parseInt(h.slice(i, i + 2), 16);
      return [n(0), n(2), n(4), h.length === 8 ? n(6) / 255 : 1];
    }
    m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/i.exec(s);
    if (!m) return null;
    const a = m[4] === undefined ? 1 : /%$/.test(m[4]) ? parseFloat(m[4]) / 100 : +m[4];
    return [+m[1], +m[2], +m[3], clamp(a)];
  }
  /** WCAG relative luminance of a colour (its alpha ignored). */
  function luminance(c) {
    const v = rgba(c);
    if (!v) return null;
    const lin = (x) => { x /= 255; return x <= .03928 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; };
    return .2126 * lin(v[0]) + .7152 * lin(v[1]) + .0722 * lin(v[2]);
  }
  /** WCAG contrast ratio of two colours, 1 to 21. */
  function contrast(a, b) {
    const la = luminance(a), lb = luminance(b);
    if (la === null || lb === null) return 1;
    return (Math.max(la, lb) + .05) / (Math.min(la, lb) + .05);
  }
  const hex2 = (n) => Math.round(n).toString(16).padStart(2, '0');
  const solid = (c) => { const v = rgba(c); return v ? '#' + hex2(v[0]) + hex2(v[1]) + hex2(v[2]) : null; };
  const withAlpha = (c, a) => { const v = rgba(c); return v ? `rgba(${v[0]},${v[1]},${v[2]},${a})` : null; };

  /** The captions' look from a project's brand (SK.BRAND, studio/brandkit.py) or, without one,
   *  its style (SK.STYLE, studio/stylekit.py); {} when it has neither, or nothing that reads.
   *  card: the darkest colour at 90%, when white reads on it; ink: white, or the brand's own light
   *  when it reads as well; said: the accent that reads on the card (4.5:1 at least), else the
   *  default yellow; font: the body face, when a weight of 600 or more of it is loaded
   *  (`faces(family)`: the heaviest loaded weight, or 0). */
  function brandLook(brand, style, faces) {
    const src = brand && brand.colors ? brand : style && (style.colors || style.palette) ? style : null;
    if (!src) return {};
    const named = src.colors || {};
    const all = [...Object.values(named), ...((src.palette || []).map((p) => p && p.hex))]
      .map(solid).filter(Boolean);
    if (!all.length) return {};
    const out = { brand: true };
    const dark = all.slice().sort((a, b) => luminance(a) - luminance(b))[0];
    if (contrast(dark, '#ffffff') >= 4.5) out.card = withAlpha(dark, .9);
    const card = solid(out.card || LOOK.card);
    const light = all.slice().sort((a, b) => luminance(b) - luminance(a))[0];
    out.ink = luminance(light) >= .75 && contrast(light, card) >= 7 ? light : '#ffffff';
    // the accent first, then the brand's other named colours, then its palette
    const order = [named.accent, named.secondary, named.primary, ...Object.values(named), ...all].map(solid).filter(Boolean);
    const said = order.find((c) => c !== card && contrast(c, card) >= 4.5 && contrast(c, out.ink) >= 1.25);
    out.said = said || LOOK.said;
    const f = (src.fonts || {}), fam = f.body;
    const w = fam && faces ? faces(fam) : 0;
    if (w >= 600) Object.assign(out, { font: `'${String(fam).replace(/'/g, '')}', ${FONT}`, weight: Math.min(800, w) });
    return out;
  }

  // ---------------------------------------------------------------- the cards
  const ends = (s) => /[.!?…;:]["'»”)\]]*$/.test(s);
  /** One line's words -> cards of at most `words` words and `chars` characters, cut at
   *  punctuation; a last word is never left alone on a card when the one before can take it. */
  function cut(words, o) {
    const out = [];
    let cur = [];
    const len = (a) => a.reduce((n, w) => n + w.text.length + 1, -1);
    const flush = () => { if (cur.length) out.push(cur); cur = []; };
    words.forEach((w, i) => {
      const full = cur.length >= o.words || (cur.length && len(cur) + 1 + w.text.length > o.chars);
      const last = i === words.length - 1 || ends(w.text);
      const fits = cur.length && len(cur) + 1 + w.text.length <= o.chars * 1.4 && cur.length <= o.words;
      if (full && !(last && fits)) flush();
      cur.push(w);
      if (ends(w.text) || (/,$/.test(w.text) && cur.length >= 2)) flush();
    });
    flush();
    return out;
  }
  /** A voice timeline ({lines: [{words: [{text, s, e}]}]}) -> its cards, [{s, e, words}], in
   *  order: each up a little before its first word, and a short pause between two bridged. */
  function cards(vo, o) {
    const rows = [];
    for (const L of (vo && vo.lines) || []) {
      const ws = (L.words || []).filter((w) => w && String(w.text || '').trim()).map((w) => ({ text: String(w.text).trim(), s: +w.s, e: +w.e }));
      for (const c of cut(ws, o)) rows.push({ words: c, s: c[0].s - o.lead, e: c[c.length - 1].e + o.hold });
    }
    rows.sort((a, b) => a.s - b.s);
    rows.forEach((r, i) => {
      const n = rows[i + 1];
      if (!n) return;
      const gap = n.s - (r.e - o.hold);
      r.e = gap < o.join ? n.s : Math.min(r.e, n.s);
    });
    return rows;
  }
  /** The band the card stays inside, [x0, y0, x1, y1] in the frame's pixels: two lines of type
   *  and their card. */
  function box(W, H, o) {
    const h = 2 * o.size * o.lh + 2 * o.size * o.padY, w = o.w + 2 * o.size * o.padX;
    return [Math.round(W / 2 - w / 2), Math.round(o.y - h / 2), Math.round(W / 2 + w / 2), Math.round(o.y + h / 2)];
  }
  /** The index of the card up at t, or -1. */
  function at(rows, t) {
    for (let i = 0; i < rows.length; i++) { const x = rows[i]; if (t >= x.s && t < x.e) return i; if (x.s > t) break; }
    return -1;
  }
  /** The word being said on card r at t, or -1 (a long pause: nothing is). */
  function saying(r, t) {
    let now = -1;
    r.words.forEach((w, i) => { if (t >= w.s) now = i; });
    if (now >= 0 && t > r.words[now].e + .35) now = -1;
    return now;
  }
  /** What is on screen at t, as a string: two times with the same key draw the same pixels
   *  (the burner draws each once). A card's first tenth of a second moves, so it is never shared. */
  function key(rows, t) {
    const i = at(rows, t);
    if (i < 0) return '';
    const r = rows[i];
    return t - r.s < .1 ? i + '@' + t.toFixed(4) : i + ':' + saying(r, t);
  }

  function layout(c, words, o, size) {
    c.font = `${o.weight} ${size}px ${o.font}`;
    const sp = c.measureText(' ').width, ws = words.map((w) => c.measureText(w.text).width);
    const width = (a, b) => ws.slice(a, b).reduce((n, x) => n + x, 0) + sp * Math.max(0, b - a - 1);
    if (width(0, ws.length) <= o.w) return { lines: [[0, ws.length]], ws, sp, width };
    let best = null; // two lines, as even as they can be
    for (let k = 1; k < ws.length; k++) {
      const m = Math.max(width(0, k), width(k, ws.length));
      if (!best || m < best.m) best = { k, m };
    }
    if (best && best.m <= o.w) return { lines: [[0, best.k], [best.k, ws.length]], ws, sp, width };
    return null; // too wide at this size
  }

  /** Draw the card up at t onto c, a canvas of the frame's size times k (1 in the film; the
   *  player's own size in a player). Nothing when no card is up, or past `end`. */
  function draw(c, rows, t, o, k = 1, end = Infinity) {
    if (!o || o.on === false || !(t < end)) return;
    const i = at(rows, t);
    if (i < 0) return;
    const r = rows[i];
    c.save();
    c.setTransform(k, 0, 0, k, 0, 0);
    c.globalAlpha = 1; c.globalCompositeOperation = 'source-over'; c.filter = 'none';
    c.direction = 'ltr'; c.textAlign = 'left'; c.textBaseline = 'alphabetic';
    c.letterSpacing = '0px'; c.wordSpacing = '0px'; c.shadowColor = 'transparent';
    let size = o.size, L = layout(c, r.words, o, size);
    for (let j = 0; !L && j < 6; j++) { size *= .88; L = layout(c, r.words, o, size); }
    if (!L) L = { ...layout(c, r.words, { ...o, w: Infinity }, size) };
    const lh = size * o.lh, padX = size * o.padX, padY = size * o.padY;
    const bw = Math.max(...L.lines.map(([a, b]) => L.width(a, b))) + 2 * padX, bh = L.lines.length * lh + 2 * padY;
    const p = clamp((t - r.s) / .1), ease = 1 - (1 - p) * (1 - p);
    const W = o.frame ? o.frame[0] : c.canvas.width / k;
    c.translate(W / 2, o.y); c.scale(.94 + .06 * ease, .94 + .06 * ease);
    c.globalAlpha = clamp((t - r.s) / .07);
    const card = rgba(o.card);
    if (!card || card[3] > 0) {
      c.fillStyle = o.card;
      c.beginPath();
      if (c.roundRect) c.roundRect(-bw / 2, -bh / 2, bw, bh, size * o.radius);
      else c.rect(-bw / 2, -bh / 2, bw, bh);
      c.fill();
    }
    if (o.shadow) { // no card: the words carry their own shade (a shadow is in the canvas's pixels, not the frame's)
      c.shadowColor = o.shadow; c.shadowBlur = size * .22 * k; c.shadowOffsetY = size * .05 * k;
    }
    const now = saying(r, t);
    L.lines.forEach(([a, b], li) => {
      let x = -L.width(a, b) / 2;
      const y = -bh / 2 + padY + lh * li + lh * .5 + size * .35;
      for (let j = a; j < b; j++) {
        c.fillStyle = j === now ? o.said : o.ink;
        c.fillText(r.words[j].text, x, y);
        x += L.ws[j] + L.sp;
      }
    });
    c.restore();
  }

  // ---------------------------------------------------------------- captions.json
  /** The look to draw a captions.json with: its own, then `over` -- {preset, card, ink, said,
   *  font, weight} as a person chose on the film's page. preset "brand" (or none) keeps the
   *  film's own colours; another preset replaces them before the three colours apply. */
  function style(data, over) {
    const own = (data && data.style) || {};
    const o = { ...LOOK, ...own, frame: data && data.frame };
    if (!over) return o;
    const pre = PRESETS[over.preset];
    if (pre) Object.assign(o, pre);
    for (const k of STYLE_KEYS) if (over[k] !== undefined && over[k] !== null && over[k] !== '') o[k] = over[k];
    if (over.font && !/,/.test(over.font)) o.font = `'${String(over.font).replace(/'/g, '')}', ${FONT}`;
    return o;
  }

  /** Draw a captions.json's cards over a <video>, on a canvas laid over the picture the video
   *  shows (object-fit: contain), kept in step with it. opts: {on, style}. Answers {set({on,
   *  style}), draw(), destroy()}. The video's parent holds the canvas: it is made a positioned
   *  box when it is not one. */
  function attach(video, data, opts = {}) {
    const doc = video.ownerDocument, win = doc.defaultView || root;
    const cv = doc.createElement('canvas');
    cv.className = 'kc-captions';
    cv.setAttribute('aria-hidden', 'true');
    Object.assign(cv.style, { position: 'absolute', pointerEvents: 'none', left: '0', top: '0', zIndex: '1' });
    const host = video.parentElement;
    if (win.getComputedStyle(host).position === 'static') host.style.position = 'relative';
    video.insertAdjacentElement('afterend', cv);
    const rows = (data && data.cards) || [];
    const [FW, FH] = (data && data.frame) || [1920, 1080];
    let on = opts.on !== false, o = style(data, opts.style), last = null, gone = false, k = 1;
    const fonts = loadFonts(doc, data);
    function place() {
      const vw = video.videoWidth || FW, vh = video.videoHeight || FH;
      const ew = video.clientWidth, eh = video.clientHeight;
      if (!ew || !eh) return false;
      const s = Math.min(ew / vw, eh / vh), cw = vw * s, ch = vh * s;
      const dpr = Math.min(3, win.devicePixelRatio || 1);
      cv.style.left = video.offsetLeft + (ew - cw) / 2 + 'px';
      cv.style.top = video.offsetTop + (eh - ch) / 2 + 'px';
      cv.style.width = cw + 'px'; cv.style.height = ch + 'px';
      const bw = Math.max(1, Math.round(cw * dpr)), bh = Math.max(1, Math.round(ch * dpr));
      if (cv.width !== bw || cv.height !== bh) { cv.width = bw; cv.height = bh; last = null; }
      k = bw / FW;
      return true;
    }
    function paint(t) {
      if (gone) return;
      const now = on ? key(rows, t) : '';
      if (now === last) return;
      last = now;
      const c = cv.getContext('2d');
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.clearRect(0, 0, cv.width, cv.height);
      if (on) draw(c, rows, t, o, k, data && data.duration ? data.duration : Infinity);
    }
    const redraw = () => { last = null; place(); paint(video.currentTime || 0); };
    let raf = 0;
    const tick = (now, meta) => {
      if (gone) return;
      paint(meta && meta.mediaTime !== undefined ? meta.mediaTime : video.currentTime || 0);
      if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(tick);
      else if (!video.paused) raf = win.requestAnimationFrame(tick);
    };
    const play = () => { if (!video.requestVideoFrameCallback) { win.cancelAnimationFrame(raf); raf = win.requestAnimationFrame(tick); } };
    if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(tick);
    // a player's own controls (paused, or under the pointer) cover the foot of the picture: the card
    // steps up above them while they show, as a video site's captions do
    let over = false;
    const lift = () => {
      const up = video.controls && (video.paused || over);
      cv.style.transform = up ? `translateY(-${Math.min(48, (parseFloat(cv.style.height) || 0) * .12)}px)` : '';
    };
    cv.style.transition = 'transform .2s';
    const evs = {
      play: () => { play(); lift(); }, pause: lift, seeked: redraw, timeupdate: () => paint(video.currentTime || 0),
      loadedmetadata: redraw, emptied: redraw,
      pointerenter: () => { over = true; lift(); }, pointerleave: () => { over = false; lift(); },
    };
    for (const [e, f] of Object.entries(evs)) video.addEventListener(e, f);
    const ro = win.ResizeObserver ? new win.ResizeObserver(redraw) : null;
    if (ro) ro.observe(video); else win.addEventListener('resize', redraw);
    fonts.then(redraw);
    redraw();
    lift();
    return {
      set(next = {}) {
        if (next.on !== undefined) on = !!next.on;
        if (next.style !== undefined) o = style(data, next.style);
        redraw();
      },
      draw: redraw,
      get on() { return on; },
      destroy() {
        gone = true;
        for (const [e, f] of Object.entries(evs)) video.removeEventListener(e, f);
        if (ro) ro.disconnect(); else win.removeEventListener('resize', redraw);
        win.cancelAnimationFrame(raf);
        cv.remove();
      },
    };
  }
  /** The faces a captions.json names ({family, weight, url}), loaded into the page. */
  function loadFonts(doc, data) {
    const F = doc.defaultView && doc.defaultView.FontFace;
    if (!F || !doc.fonts) return Promise.resolve();
    return Promise.all(((data && data.fonts) || []).filter((f) => f && f.url && f.family).map((f) => {
      try {
        const face = new F(f.family, `url(${JSON.stringify(f.url)})`, { weight: String(f.weight || '400'), style: f.style || 'normal' });
        doc.fonts.add(face);
        return face.load().catch(() => null);
      } catch (e) { return null; }
    }));
  }

  root.KCCaptions = {
    FONT, LOOK, PRESETS, STYLE_KEYS, geometry, brandLook, rgba, luminance, contrast,
    cut, cards, box, at, saying, key, draw, style, attach, loadFonts,
  };
})(typeof window !== 'undefined' ? window : globalThis);
