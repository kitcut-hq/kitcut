/* The mojito example: "Made with KitCut", 10 seconds. A hurricane glass fills from a pour, ice
   and mint and lime drop in and float, two paper straws fall against the rim, a lime wheel
   lands on it -- every splash, bob and clink simulated (sketch/drink.js) -- and the KitCut
   lockup settles under the glass. Copy the folder to projects/<id>/ before running anything.

   Two cuts from one film: "vars": {"text": false} in the manifest leaves the lockup out (the
   clean glass, for B-roll). Drops are [{t, kind: ice|mint|lime|straw, at: [x, z]}]: world units,
   the glass's rim is 0.39 across, y is up. */
(function () {
  'use strict';
  SK.setStyle('clean', { grain: 0.12, vignette: 0.06, handheld: 0 });
  SK.C.paper = '#e6e5df';
  const VARS = SK.VARS || {};

  const drops = [
    { t: 4.3, kind: 'ice', at: [0.04, -0.02] },
    { t: 4.62, kind: 'ice', at: [-0.1, 0.06] },
    { t: 4.9, kind: 'mint', at: [0.08, 0.1] },
    { t: 4.98, kind: 'ice', at: [0.1, 0.1] },
    { t: 5.28, kind: 'ice', at: [-0.05, -0.12] },
    { t: 5.42, kind: 'mint', at: [-0.12, 0.0] },
    { t: 5.58, kind: 'ice', at: [0.0, 0.08] },
    { t: 5.85, kind: 'lime', at: [-0.08, 0.05] },
    // straws go in as people drop them, nearly upright; they tip against the rim on their own
    // where a straw ends up leaning is the physics' call; these two were measured (a sweep of
    // drop points) to lean left, away from the lime wheel, as the straws do in the logo
    { t: 6.3, kind: 'straw', at: [-0.06, -0.05], tilt: 10, yaw: 0.2, spin: 0.3, height: 0.12 },
    { t: 6.62, kind: 'straw', at: [-0.06, 0.06], tilt: 10, yaw: 2.9, spin: 0.3, height: 0.12 },
  ];
  const glass = SK.drink.glass({ drops, rimLime: { t: 7.05, angle: 28, size: 0.19 } });

  const LOCK = 7.6;
  function lockup(t) {
    if (VARS.text === false) return;
    const a = Math.max(0, Math.min(1, (t - LOCK) / 0.7)), e = a * a * (3 - 2 * a);
    if (e <= 0) return;
    const ctx = SK.ctx();
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = e;
    // the logo spans both lines; MADE WITH sits over KitCut, both to its right, the group centred
    const cx = SK.W / 2, base = 1022 + (1 - e) * 14;
    ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
    ctx.font = '700 64px Inter';
    const word = 'KitCut', ww = ctx.measureText(word).width, lh = 104, lw = lh * (300 / 428), gap = 18, total = lw + gap + ww;
    const x0 = cx - total / 2;
    SK.image('logo', x0 + lw / 2, base - 40, lw, lh, { alpha: 1 });
    ctx.fillStyle = '#1f2a1c';
    ctx.fillText(word, x0 + lw + gap, base);
    ctx.font = '600 15px Inter'; ctx.letterSpacing = '5px'; ctx.fillStyle = '#6f6a62';
    ctx.fillText('MADE WITH', x0 + lw + gap + 3, base - 60);
    ctx.letterSpacing = '0px';
    ctx.restore();
  }

  SK.film({
    duration: 10,
    camera: SK.camera([[0, [0, 0, 1]]]),
    handheld: false,
    speedLines: false,
    fadeOut: 0, // an end card holds: no fade to paper, so it can be cut in anywhere
    draw(t) { glass.draw(t); },
    overlay(t) { lockup(t); },
    sounds: () => glass.sounds(),
  });
})();
