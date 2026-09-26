/* Studio example 1 -- "Home" (12 s, drawn, crayon on the night ground). Narration (vo.json):
     0 "Every night, Pip walked home over the hills."
     1 "The moon came out to light the way."
     2 "And there was home."
   A place, not a page: a sky and stars that stay put, hills that scroll with the camera, a walker
   standing on them (hills(x) gives the ground's height), a house to arrive at, and a near strip of
   grass in front for depth. Far things (the moon) follow the camera most of the way. */
(function () {
  'use strict';
  const { S, E, clamp, tw, P } = SK;
  const w = (li, word, fb, n = 0) => SK.w(li, word, fb, 's', n);
  SK.setStyle('crayon');
  SK.setGround('night'); // the paper, the text colours and the grain, chosen together
  const C = SK.C;

  const tMoon = w(1, 'moon', 4.6), tHome = w(2, 'home', 9.4);
  const walkX = (t) => SK.kf(t, [[0, -760], [tHome - .3, 760]], E.sine);
  const camera = SK.camera([[0, [-520, -40, 1.12]], [tHome, [660, -60, 1]], [12, [700, -80, 1.05], E.sine]]);

  function lantern(x, y, t) {
    const glow = .8 + .2 * Math.sin(t * 7);
    SK.alpha(.3 * glow, () => SK.wash(S.ellC(x, y + 20, 70, 70), C.accent, { dx: 0, dy: 0, tex: false }));
    SK.ink(S.line(x, y - 16, x, y), { w: 3, seed: 40, dbl: false });
    SK.wash(S.rrect(x - 13, y, 26, 38, 6), C.yellow, { seed: 41 });
    SK.ink(S.rrect(x - 13, y, 26, 38, 6), { w: 4, seed: 42 });
  }

  SK.film({
    duration: 12,
    camera,
    draw(t, vis) {
      // backdrops first: each covers the whole view, whatever the camera does
      SK.sky('#141a33', '#35305a');
      SK.stars({ n: 70, seed: 4 });
      const cx = camera.at(t)[0];
      P.moon(cx * .85 + 700, -420, { phase: 'crescent', glow: tw(t, tMoon, tMoon + 1), p: clamp(.15 + E.out(SK.inv(tMoon, tMoon + .8, t))) });
      const hills = SK.band(230, '#2f4b40', { edge: 'hills', amp: 45, seed: 2 });
      if (vis(700, -500, 1500, 300)) P.house(1060, hills(1060) + 12, { w: 380, kind: 'bungalow', wall: '#e9dcc3', lit: tw(t, tHome - .2, tHome + .4) });
      const x = walkX(t), y = hills(x) + 8;
      P.kid({ x, y, s: .8, walk: t < tHome ? t * 1.7 : 0, hair: 'short', shirt: C.teal, mood: t > tHome ? 'happy' : 'open', mouth: 'smile', arms: P.KIDPOSE.hold });
      lantern(x + 78, y - 118, t);
      SK.band(420, '#233a31', { edge: 'grass', seed: 6 }); // the near grass, in front: depth
      SK.txt('home.', 1000, -250, { size: 120, col: C.accentText, p: tw(t, tHome, tHome + .6, E.lin) });
    },
  });
})();
