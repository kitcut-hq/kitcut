/* The jelly example: "Melon Jelly", a 12-second material study. A watermelon gummy is dropped,
   grabbed by the tip and stretched, pressed, lifted by the rind, nudged, and picked up and
   dropped -- every motion simulated (sketch/jelly.js), none keyframed. Copy the folder to
   projects/<id>/ before running anything; the manifest's "modules": ["jelly"] loads the engine.

   The hand is the `actions` list: each is a grab (a named point or [x, y, z] in the slice's own
   space, then a path of [seconds after the grab, [dx, dy, dz]] and an optional twist in degrees),
   a poke (press a point `depth` deep over `dur`) or a nudge (a kick). World units: the slice's
   radius is 1, y is up, the floor is y = 0. The type is drawn over the picture in screen space. */
(function () {
  'use strict';
  SK.setStyle('clean', { grain: 0.16, vignette: 0.08, handheld: 0 });
  SK.C.paper = '#dedad3';

  const ACTS = [
    { t: 1.35, grab: 'tip', path: [[0.55, [-0.3, 0.44, 0.16]], [0.95, [-0.36, 0.52, 0.2]]], twist: [[0.95, 16]], hint: 'Grab the tip — and pull.' },
    { t: 3.9, poke: 'flesh', depth: 0.12, dur: 0.75, hint: 'Press the flesh.' },
    { t: 5.1, grab: 'rind', radius: 0.2, path: [[0.6, [-0.18, 0.5, -0.3]], [1.05, [-0.24, 0.56, -0.38]]], hint: 'Lift the rind. Let go.' },
    { t: 7.55, nudge: 1.1, hint: 'Give it a nudge.' },
    { t: 8.9, grab: 'corner-left', radius: 0.22, path: [[0.5, [0.05, 0.62, 0.05]], [0.85, [0.08, 0.7, 0.06]]], twist: [[0.85, -22]], hint: 'Pick it up. Drop it.' },
  ];
  const melon = SK.jelly.specimen({
    preset: 'crimson',
    firmness: 0.4,
    damping: 0.32,
    bubbles: { n: 10, seed: 3 },
    pose: { at: [0, 0.28, 0], yaw: 35 },
    camera: { dist: 3.05, elev: 38, azim: 8, fov: 28, orbit: 6, shift: [0.1, -0.02] },
    actions: ACTS,
  });

  const INK = '#221e1b', SOFT = '#6f675e', RULE = 'rgba(34,30,27,.22)';
  const hintAt = (t) => {
    let h = 'Dropped from a little way up. It settles.';
    for (const a of ACTS) if (t >= a.t - 0.15) h = a.hint;
    return h;
  };
  function label(ctx, s, x, y, o = {}) {
    ctx.font = `${o.weight || 600} ${o.size || 15}px Inter`;
    ctx.letterSpacing = o.track || '2.6px';
    ctx.fillStyle = o.col || SOFT; ctx.textAlign = o.align || 'left';
    ctx.fillText(s, x, y);
    ctx.letterSpacing = '0px';
  }
  function type(t) {
    const ctx = SK.ctx();
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.textBaseline = 'alphabetic';
    // top left: the study
    label(ctx, 'MATERIAL STUDIES / NO. 009', 96, 104);
    ctx.fillStyle = INK; ctx.font = '400 168px "Instrument Serif Italic"';
    ctx.fillText('Melon', 88, 262); ctx.fillText('Jelly.', 150, 400);
    ctx.font = '400 29px "Instrument Serif"'; ctx.fillStyle = SOFT;
    ['A slice of summer.', 'A little wobble.', 'Too soft to share.'].forEach((s, i) => ctx.fillText(s, 98, 468 + i * 36));
    // top right: what it is
    ctx.fillStyle = '#3f8f4e'; ctx.beginPath(); ctx.arc(1629, 99, 5, 0, Math.PI * 2); ctx.fill();
    label(ctx, 'SOFT BODY · XPBD', 1824, 104, { align: 'right', size: 14 });
    // bottom left: the hand's instruction and the live readouts
    label(ctx, 'HANDLE', 96, 862, { size: 13 });
    ctx.font = '400 30px "Instrument Serif Italic"'; ctx.fillStyle = INK; ctx.fillText(hintAt(t), 182, 864);
    const st = melon.stats(t);
    const cells = [['MASS', '≈' + st.mass.toFixed(0), 'g'], ['VOLUME', (st.volume * 100).toFixed(1), '% of rest'], ['KINETIC', st.kinetic.toFixed(2), 'µJ']];
    cells.forEach(([k, v, u], i) => {
      const x = 96 + i * 190;
      if (i) { ctx.fillStyle = RULE; ctx.fillRect(x - 22, 902, 1, 74); }
      label(ctx, k, x, 922, { size: 12 });
      ctx.font = '500 34px Inter'; ctx.fillStyle = INK; ctx.textAlign = 'left'; ctx.fillText(v, x, 964);
      const w = ctx.measureText(v).width;
      ctx.font = '400 15px Inter'; ctx.fillStyle = SOFT; ctx.fillText(u, x + w + 6, 964);
    });
    ctx.font = '400 13px Inter'; ctx.fillStyle = SOFT;
    ctx.fillText('Illustrative scale: 1 sim unit = 6 cm, gummy at 1.3 g/cm³. Volume and energy are summed', 96, 1004);
    ctx.fillText('live over every tetrahedron and particle.', 96, 1022);
    // bottom right: how
    label(ctx, 'FINITE ELEMENTS · REFRACTED LIGHT · BAKED AT 60 FPS', 1824, 1010, { align: 'right', size: 12 });
    ctx.restore();
  }

  SK.film({
    duration: 12,
    camera: SK.camera([[0, [0, 0, 1]]]),
    handheld: false,
    speedLines: false,
    fadeOut: 0.5,
    draw(t) { melon.draw(t); },
    // the sound design comes off the simulation: a plop per landing, a squish per grab and poke
    sounds: () => melon.sounds(),
    overlay(t) { type(t); },
  });
})();
