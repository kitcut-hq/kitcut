/* The engine's grounds and backdrops on one sheet: every ground for a second (0-10 s), then three
   places built from the backdrops and the scenery (10-16 s). Render stills at 0.5, 1.5 ... 15.5
   and look: text, marks and characters must read on every ground, and no backdrop may show an
   edge -- the last six seconds pan and zoom out to prove it.

   python scripts/sketch-render.py --manifest config/sketch/grounds/sketch.json --stills 0.5,1.5,... --sheet */
(function () {
  'use strict';
  const { S, E, clamp, P } = SK;
  const C = SK.C;
  const NAMES = Object.keys(SK.GROUNDS);  // paper white kraft sky mint butter blush night chalkboard blueprint
  const scene = (t) => t < 10 ? 'ground' : t < 12 ? 'night' : t < 14 ? 'day' : 'sunset';
  const ground = (t) => t < 10 ? NAMES[Math.min(NAMES.length - 1, Math.floor(t))] : { night: 'night', day: 'sky', sunset: 'butter' }[scene(t)];
  const style = (t) => ground(t) === 'blueprint' || ground(t) === 'white' ? 'clean' : 'crayon';

  function sheet(t) {
    const name = ground(t);
    SK.txt(name, 0, -400, { size: 110 });
    SK.txt('a word that matters', 0, -290, { size: 64, col: C.accentText });
    SK.txt('and a quieter line under it', 0, -215, { size: 44, col: C.textSoft, font: 'Balsamiq Sans' });
    P.kid({ x: -420, y: 330, s: 1, mood: 'happy', mouth: 'smile', arms: P.KIDPOSE.point });
    SK.dashes(S.line(-260, 60, 230, 60, -60));
    SK.ink(S.poly([[210, 40], [236, 60], [210, 82]]), { w: 5, col: C.text });
    P.lightbulb(420, 40, 1.3, 1);
    SK.spark(640, -120, 60, { col: C.accent });
    P.tree(720, 380, { s: .9 });
    P.cloud(-760, -300, { s: .7 });
    SK.card(-150, 200, 300, 110, { fill: C.accent });
    SK.txt('button', 0, 255, { size: 54, col: '#ffffff' });
  }

  function night(t) {
    SK.sky('#141a33', '#3a2f5a');
    SK.stars({ n: 80 });
    P.moon(620, -330, { phase: 'crescent', glow: 1 });
    const hills = SK.band(250, '#2d4a3e', { edge: 'hills', amp: 50, seed: 3 });
    for (let i = 0; i < 6; i++) P.building(-900 + i * 260, hills(-900 + i * 260) + 30, { w: 180 + (i % 3) * 30, h: 260 + (i * 67) % 200, col: '#4a4f6e', lit: .45, seed: 1700 + i, roof: i === 2 ? 'dome' : 'flat' });
    SK.band(420, '#1f3a30', { edge: 'grass', seed: 5 });
    SK.txt('a quiet night', 0, -420, { size: 96 });
  }

  function day(t) {
    SK.sky('#8ec5ea', '#e3f2fb');
    P.sun(-640, -330, { face: 'happy', rot: t * .3 });
    P.cloud(200 + t * 20, -360, { s: 1.1 });
    P.cloud(900 + t * 14, -250, { s: .8, seed: 1510 });
    P.mountain(700, 180, { w: 900, h: 600 });
    const hills = SK.band(180, '#9fcf8a', { edge: 'hills', amp: 40, seed: 9 });
    P.tree(-300, hills(-300) + 10, {});
    P.tree(-120, hills(-120) + 16, { kind: 'pine', s: .9 });
    P.bush(80, hills(80) + 20, { flowers: C.heart });
    SK.band(400, '#86bf72', { edge: 'grass', seed: 11 });
    P.kid({ x: 380, y: 470, s: .9, mood: 'happy', mouth: 'big', arms: P.KIDPOSE.wave, walk: t * 1.5 });
    SK.txt('a sunny day', 0, -440, { size: 96, col: C.accentText });
  }

  function sunset(t) {
    SK.sky('#f4a96b', '#ffe0b0', { mid: '#f6c38a' });
    P.sun(0, 120, { r: 120, rays: 0, col: '#ffcf5a' });
    P.mountain(-700, 150, { w: 800, h: 420, col: '#b98c8c', snow: false });
    SK.band(150, '#3f7fb0', { edge: 'waves', amp: 10, seed: 13 });
    SK.band(260, '#2f6c9e', { edge: 'waves', amp: 14, len: 220, seed: 17, speed: 60 });
    SK.band(470, '#e9c98f', { edge: 'hills', amp: 20, len: 1400, seed: 19 });
    SK.txt('the sea at sunset', 0, -420, { size: 96 });
  }

  SK.film({
    duration: 16,
    ground: (t) => { SK.setStyle(style(t)); return ground(t); },  // before the paper is laid
    camera: SK.camera([[0, [0, 0, 1]], [10, [0, 0, 1]], [10.01, [-300, 0, 1.05]], [16, [500, -60, .8], E.lin]]),
    speedLines: false,
    draw(t) {
      const s = scene(t);
      if (s === 'ground') sheet(t); else if (s === 'night') night(t); else if (s === 'day') day(t); else sunset(t);
    },
  });
})();
