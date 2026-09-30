// For: anyone learning talking heads in a sketch film; a worked example of the technique
// The Brothers Speak -- a 1903 front page whose two photographs talk: sketch/heads.js (the
// faces) on sketch/collage.js (the page). Each photo moves only its mouth, on its own voice.
SK.setStyle('collage');
SK.setGround('paper', { paper: '#d9cdb2' });
const INK = '#1d1a17', RED = '#b3372c';
const T = [0, 1, 2].map((i, k) => SK.line(i).start || [0.6, 3.3, 5.4][k]); // each line's start
const PHOTO = { wilbur: -420, orville: 420 }, PY = 120, FACE = 225;

/** a halftone photograph pinned to the page, its caption under it */
function photo(name, caption, t0) {
  const x = PHOTO[name];
  SK.layer({ x, y: PY, in: { t: t0, type: 'drop', dist: 60 } }, () => {
    const w = 430, h = 520;
    SK.card(-w / 2 - 10, -h / 2 - 10, w + 20, h + 20, { r: 2, fill: '#f3ecdc', shadow: { blur: 16, y: 6, col: 'rgba(40,28,14,.22)' } });
    // the photo's own face, in newspaper dots; only its mouth moves (and its eyes blink)
    SK.head(name, 0, -30, FACE, { style: 'photo', tone: 'news', crop: [-w / 2 / FACE, -h / 2 / FACE + .13, w / 2 / FACE, h / 2 / FACE + .13] });
    SK.headline(caption, 0, h / 2 + 44, { font: 'Old Standard TT', wt: 700, size: 30, ls: 4, col: INK });
  });
}

SK.film({
  duration: 9.5,
  // a slow push to whoever is speaking
  camera: SK.camera([
    [0, [0, 0, 1]],
    [T[0] + .2, [0, 0, 1]],
    [T[0] + 1.6, [PHOTO.wilbur * .35, 40, 1.12]],
    [T[1] - .1, [PHOTO.wilbur * .35, 40, 1.12]],
    [T[1] + 1.0, [PHOTO.orville * .35, 40, 1.12]],
    [T[2] - .1, [PHOTO.orville * .35, 40, 1.12]],
    [T[2] + 1.2, [PHOTO.wilbur * .3, 30, 1.08]],
    [9.5, [PHOTO.wilbur * .3, 30, 1.1]],
  ]),
  fadeOut: .4,
  draw(t) {
    SK.sheet(0, 0, 1880, 1060, { col: '#efe7d3', edges: 'tb', seed: 4, amp: 7, rim: 8, tex: 1.4 });
    SK.headline('The Evening Flyer', 0, -420, { font: 'UnifrakturMaguntia', size: 118, col: INK, distress: .2 });
    SK.rules(-860, 860, -355, { w: 4, col: INK });
    SK.headline('THURSDAY, DECEMBER 17, 1903  ·  KITTY HAWK, N.C.  ·  ONE CENT', 0, -318, { font: 'Old Standard TT', wt: 700, size: 24, ls: 3, col: INK });
    SK.rules(-860, 860, -292, { w: 2, col: INK });
    // the page opens set: its headline and photographs are already landing at frame 0
    SK.headline('BROTHERS FLY', 0, -215, { font: 'Abril Fatface', size: 104, col: INK, distress: .25, in: { t: -.12, type: 'slap' } });
    // a column of small type between the photographs
    SK.layer({ x: 0, y: PY + 20 }, () => {
      const c = SK.ctx(); c.save(); c.beginPath(); c.rect(-150, -290, 300, 600); c.clip();
      SK.newsprint({ w: 300, h: 600, cols: 1, size: 15, seed: 9, col: '#efe7d3', ink: 'rgba(40,30,20,.55)', headEvery: .08, heads: ['AIRSHIP NEWS', 'THE MACHINE', 'WITNESSES'], text: 'The machine rose from the level sand under its own power and flew forward against a stiff wind, landing without damage at a point a hundred and twenty feet from where it started. Five persons from the life-saving station watched it. The brothers, who build bicycles in Dayton, say they will try again.' });
      c.restore();
    });
    photo('wilbur', 'WILBUR WRIGHT', -.25);
    photo('orville', 'ORVILLE WRIGHT', -.05);
    // "Twelve seconds": the stamp lands on the word, over the corner of Orville's photograph
    SK.stamp(640, 330, { top: 'EXTRA', bottom: 'EDITION', text: '12 SEC', r: 88, col: RED, t: SK.w(2, 'seconds', 5.2, 'e') });
  },
});
