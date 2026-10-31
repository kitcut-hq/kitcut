/* sketch/captions.js -- the narration's words, a few at a time, as the film's captions.

   A module: a film opts in with "modules": [..., "captions-layer", "captions"] in its manifest
   (studio/film.py CAPS "captions"), and sketch-render loads it after engine.js and props.js. It
   needs nothing from the film: it reads the voice timeline the bundler injects (SK.VO), cuts each
   line into short cards at its punctuation, and draws the card being spoken over everything the
   film draws -- white type on a dark card, the word being said in yellow, or the project's brand
   colours when it has a brand or a style -- so the words read on any picture. The drawing is
   sketch/captions-layer.js, which the site's players use too.

   The film's video is drawn WITHOUT them (a render: ?export or ?encode): the captions go beside it
   as captions.json (SK.captionData, sketch-render ?captions), and are drawn live over the video,
   or burned into a copy that leaves KitCut (scripts/captions-burn.py). Its stills, strips and
   motion sheets show them, so Claude sees where they fall. A film made before 2026-10-31 has its
   own copy of the module that burned them in (engine/captions.js), and keeps it.

   Where the card sits, and how many words it holds, come from the frame's shape (geometry):

     tall   (9:16, a Short)  low in the frame, but above what a phone's own buttons cover
     square (1:1)            along the bottom
     wide   (16:9)           along the bottom

   SK.captionBox() answers the band the card stays inside, [x0, y0, x1, y1] in screen pixels:
   studio/film.py caption_band tells the film's writer to keep it clear, so the two move together.
   A film may set SK.CAPTIONS before SK.film() to change a value: { card, ink, said, font, weight }
   for its look, { on: false } for none.

   Every frame is a pure function of t: the table of cards is derived from SK.VO alone.
*/
(function () {
  'use strict';
  const SK = window.SK, K = window.KCCaptions;
  const W = SK.W, H = SK.H;
  // a render of the video: the captions are drawn live over it instead (captions.json)
  const CLEAN = typeof location !== 'undefined' && /[?&](export|encode)=/.test(location.search);
  /** The heaviest loaded weight of a family on the page, 0 when none is. */
  function faces(family) {
    const want = String(family).replace(/['"]/g, '').trim().toLowerCase();
    let top = 0;
    for (const f of (typeof document !== 'undefined' && document.fonts) || []) {
      if (String(f.family).replace(/['"]/g, '').trim().toLowerCase() !== want || f.status === 'error') continue;
      const w = String(f.weight).split(/\s+/).map(Number).filter((n) => n > 0);
      top = Math.max(top, ...w);
    }
    return top;
  }
  const cfg = () => ({ on: true, frame: [W, H], ...K.geometry(W, H), ...K.LOOK, ...K.brandLook(SK.BRAND, SK.STYLE, faces), ...(SK.CAPTIONS || {}) });

  /** The band the card stays inside, in screen pixels: two lines of type and their card. */
  SK.captionBox = () => K.box(W, H, cfg());

  let TABLE = null, TABLE_OF = null;
  function table(o) {
    if (TABLE && TABLE_OF === SK.VO) return TABLE;
    TABLE = K.cards(SK.VO, o); TABLE_OF = SK.VO;
    return TABLE;
  }
  /** The cards and their times, [{ s, e, text }]: what a test or a film's own check reads. */
  SK.captionCards = () => table(cfg()).map((r) => ({ s: r.s, e: r.e, text: r.words.map((w) => w.text).join(' ') }));

  /** The film's captions.json: its cards with their word times, and the look they are drawn in
   *  (sketch-render writes it beside the video; the studio adds the faces it names). */
  SK.captionData = function () {
    const o = cfg(), F = SK._film;
    const keep = ['on', 'y', 'size', 'w', 'words', 'chars', 'lh', 'padX', 'padY', 'radius', 'lead', 'hold', 'join', ...K.STYLE_KEYS, 'brand'];
    const style = {};
    for (const k of keep) if (o[k] !== undefined && typeof o[k] !== 'function') style[k] = o[k];
    return {
      v: 1,
      frame: [W, H],
      duration: F ? F.duration : SK.LENGTH,
      style,
      cards: table(o).map((r) => ({ s: r.s, e: r.e, words: r.words.map((w) => ({ text: w.text, s: w.s, e: w.e })) })),
    };
  };

  function draw(t) {
    if (CLEAN) return;
    const o = cfg();
    if (!o.on) return;
    const F = SK._film;
    K.draw(SK.ctx(), table(o), t, o, 1, F ? F.duration : Infinity);
  }

  const film = SK.film;
  SK.film = function (def) {
    film(def);
    const F = SK._film, own = F.overlay;
    F.overlay = (t) => { if (own) own(t); draw(t); };
  };
})();
