/* sketch/captions.js -- the narration's words, a few at a time, as the film's captions.

   A module: a film opts in with "modules": [..., "captions-layer", "captions"] in its manifest
   (studio/film.py CAPS "captions"), and sketch-render loads it after engine.js and props.js. It
   needs nothing from the film: it reads the voice timeline the bundler injects (SK.VO) and cuts
   each line into short cards at its punctuation -- white type on a dark card, the word being said
   in yellow, or the project's brand colours when it has a brand or a style. The drawing is
   sketch/captions-layer.js, which the site's players use too.

   It draws nothing into the film: not its video, not its stills, strips or motion sheets, so the
   picture is composed as if there were no captions. They go beside the video as captions.json
   (SK.captionData, sketch-render ?captions), where the studio, having looked at the rendered
   video, puts each scene's cards at the foot of the frame or at its top (scripts/_captionplace.py);
   the site's players draw them live over the video, and scripts/captions-burn.py into a copy that
   leaves KitCut. A film made before 2026-10-31 has its own copy of the module that burned them in
   (engine/captions.js), and keeps it.

   Where a card sits, and how many words it holds, come from the frame's shape (geometry):

     tall   (9:16, a Short)  low in the frame, above what a phone's own buttons cover; or high
     square (1:1)            along the bottom, or the top
     wide   (16:9)           along the bottom, or the top

   SK.captionBox(at) answers the band a card stays inside, [x0, y0, x1, y1] in screen pixels, at
   the foot ("bottom", the default) or the top. A film may set SK.CAPTIONS before SK.film() to
   change a value: { card, ink, said, font, weight } for its look, { on: false } to start with
   them off.

   The table of cards is derived from SK.VO alone.
*/
(function () {
  'use strict';
  const SK = window.SK, K = window.KCCaptions;
  const W = SK.W, H = SK.H;
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

  /** The band a card stays inside, in screen pixels: two lines of type and their card, at the
   *  foot of the frame or (at "top") its top. */
  SK.captionBox = (at) => K.box(W, H, cfg(), at);

  let TABLE = null, TABLE_OF = null;
  function table(o) {
    if (TABLE && TABLE_OF === SK.VO) return TABLE;
    TABLE = K.cards(SK.VO, o); TABLE_OF = SK.VO;
    return TABLE;
  }
  /** The cards and their times, [{ s, e, text }]: what a test or a film's own check reads. */
  SK.captionCards = () => table(cfg()).map((r) => ({ s: r.s, e: r.e, text: r.words.map((w) => w.text).join(' ') }));

  /** The film's captions.json: its cards with their word times, the look they are drawn in, and
   *  its scenes' times when it is made in scenes (sketch-render writes it beside the video; the
   *  studio adds the faces it names, and where each card sits). */
  SK.captionData = function () {
    const o = cfg(), F = SK._film;
    const keep = ['on', 'y', 'top', 'size', 'w', 'words', 'chars', 'lh', 'padX', 'padY', 'radius', 'lead', 'hold', 'join', ...K.STYLE_KEYS, 'brand'];
    const style = {};
    for (const k of keep) if (o[k] !== undefined && typeof o[k] !== 'function') style[k] = o[k];
    return {
      v: 1,
      frame: [W, H],
      duration: F ? F.duration : SK.LENGTH,
      style,
      cards: table(o).map((r) => ({ s: r.s, e: r.e, words: r.words.map((w) => ({ text: w.text, s: w.s, e: w.e })) })),
      scenes: typeof SK.sceneTimes === 'function' ? SK.sceneTimes() : [],
    };
  };
})();
