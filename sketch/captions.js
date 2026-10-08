/* sketch/captions.js -- the narration's words burned into the picture, a few at a time.

   A module: a film opts in with "modules": [..., "captions"] in its manifest, and sketch-render
   loads it after engine.js and props.js. It needs nothing from the film: it reads the voice
   timeline the bundler injects (SK.VO), cuts each line into short cards at its punctuation, and
   draws the card being spoken over everything the film draws -- white type on a dark card, the
   word being said in yellow -- so the words read on any picture. A video site ignores the soft
   subtitle track an MP4 carries; these are in the pixels.

   Where the card sits, and how many words it holds, come from the frame's shape (GEOMETRY):

     tall   (9:16, a Short)  low in the frame, but above what a phone's own buttons cover
     square (1:1)            along the bottom
     wide   (16:9)           along the bottom

   SK.captionBox() answers the band the card stays inside, [x0, y0, x1, y1] in screen pixels:
   studio/film.py CAPTION_BAND tells the film's writer to keep it clear, so the two move together.
   A film may set SK.CAPTIONS before SK.film() to change a value ({ on: false } draws none).

   Every frame is a pure function of t: the table of cards is derived from SK.VO alone.
*/
(function () {
  'use strict';
  const SK = window.SK;
  const { clamp } = SK;
  const W = SK.W, H = SK.H;
  // y: the card's centre; size: the type; w: the widest a line may be; words, chars: a card's most
  const GEOMETRY = H > W
    ? { y: H * .745, size: W * .061, w: W * .74, words: 4, chars: 22 }
    : H === W
      ? { y: H * .86, size: W * .05, w: W * .8, words: 5, chars: 28 }
      : { y: H * .885, size: H * .046, w: W * .7, words: 8, chars: 46 };
  const LOOK = {
    font: "'Inter', 'Sofia Sans', sans-serif", weight: 800, lh: 1.2, padX: .42, padY: .26, radius: .32,
    card: 'rgba(17,17,21,.86)', ink: '#ffffff', said: '#ffe14d',
    lead: .05,  // a card is up this long before its first word, so the eye is there for it
    hold: .25,  // and stays this long after its last, when nothing follows at once
    join: .6,   // a pause shorter than this between two cards is bridged, not blinked
  };
  const cfg = () => ({ on: true, ...GEOMETRY, ...LOOK, ...(SK.CAPTIONS || {}) });

  /** The band the card stays inside, in screen pixels: two lines of type and their card. */
  SK.captionBox = function () {
    const o = cfg(), h = 2 * o.size * o.lh + 2 * o.size * o.padY;
    const w = o.w + 2 * o.size * o.padX;
    return [Math.round(W / 2 - w / 2), Math.round(o.y - h / 2), Math.round(W / 2 + w / 2), Math.round(o.y + h / 2)];
  };

  const ends = (s) => /[.!?…;:]["'»”)\]]*$/.test(s);
  /** One line's words -> cards of at most `words` words and `chars` characters, cut at punctuation;
   *  a last word is never left alone on a card when the one before can take it. */
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

  let TABLE = null, TABLE_OF = null;
  function table(o) {
    if (TABLE && TABLE_OF === SK.VO) return TABLE;
    const rows = [];
    for (const L of (SK.VO && SK.VO.lines) || []) {
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
    TABLE = rows; TABLE_OF = SK.VO;
    return rows;
  }
  /** The cards and their times, [{ s, e, text }]: what a test or a film's own check reads. */
  SK.captionCards = () => table(cfg()).map((r) => ({ s: r.s, e: r.e, text: r.words.map((w) => w.text).join(' ') }));

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

  function draw(t) {
    const o = cfg();
    if (!o.on) return;
    const F = SK._film;
    if (F && t >= F.duration) return;
    const rows = table(o);
    let r = null;
    for (const x of rows) { if (t >= x.s && t < x.e) { r = x; break; } if (x.s > t) break; }
    if (!r) return;
    const c = SK.ctx();
    c.save();
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.globalAlpha = 1; c.globalCompositeOperation = 'source-over'; c.filter = 'none';
    c.direction = 'ltr'; c.textAlign = 'left'; c.textBaseline = 'alphabetic';
    c.letterSpacing = '0px'; c.wordSpacing = '0px'; c.shadowColor = 'transparent';
    let size = o.size, L = layout(c, r.words, o, size);
    for (let i = 0; !L && i < 6; i++) { size *= .88; L = layout(c, r.words, o, size); }
    if (!L) L = { ...layout(c, r.words, { ...o, w: Infinity }, size) };
    const lh = size * o.lh, padX = size * o.padX, padY = size * o.padY;
    const bw = Math.max(...L.lines.map(([a, b]) => L.width(a, b))) + 2 * padX, bh = L.lines.length * lh + 2 * padY;
    const k = clamp((t - r.s) / .1), ease = 1 - (1 - k) * (1 - k);
    c.translate(W / 2, o.y); c.scale(.94 + .06 * ease, .94 + .06 * ease);
    c.globalAlpha = clamp((t - r.s) / .07);
    c.fillStyle = o.card;
    c.beginPath(); c.roundRect(-bw / 2, -bh / 2, bw, bh, size * o.radius); c.fill();
    let now = -1;
    r.words.forEach((w, i) => { if (t >= w.s) now = i; });
    if (now >= 0 && t > r.words[now].e + .35) now = -1; // a long pause: nothing is being said
    L.lines.forEach(([a, b], li) => {
      let x = -L.width(a, b) / 2;
      const y = -bh / 2 + padY + lh * li + lh * .5 + size * .35;
      for (let i = a; i < b; i++) {
        c.fillStyle = i === now ? o.said : o.ink;
        c.fillText(r.words[i].text, x, y);
        x += L.ws[i] + L.sp;
      }
    });
    c.restore();
  }

  const film = SK.film;
  SK.film = function (def) {
    film(def);
    const F = SK._film, own = F.overlay;
    F.overlay = (t) => { if (own) own(t); draw(t); };
  };
})();
