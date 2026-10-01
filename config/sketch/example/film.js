/* The example sketch film: 12 seconds, crayon style, no branding.
   Copy the whole folder to projects/<id>/ before running anything -- the scripts write
   audio/, outputs/ and temp/ next to the manifest.

   It shows the working parts a new film reuses: a camera that travels between two places,
   props drawn on with the pen, a character, a flight path, and cues hung on spoken words
   (SK.w(line, "word")) so a re-recorded line moves its visuals with it. */
(function () {
  'use strict';
  const { S, E, clamp, tw, pop, P } = SK;
  // w(line, word, fallback seconds, n-th match): the fallback is where the cue sits with no voice-over
  const w = (li, word, fb, n = 0) => SK.w(li, word, fb, 's', n);
  SK.setStyle('crayon');
  const C = SK.C;

  // world: a desk on the left, a friend on the right
  const DESK = [0, 0], FRIEND = [2400, 0];
  const tFly = w(1, 'send', 3.2), tLand = w(1, 'friend', 5.2);
  const flight = SK.flightPath([[40, -60], [500, -560], [1200, -700], [1900, -450], [2340, -40]], [[0, 4, tFly, tLand]]);

  const camera = SK.camera([
    [0, [0, -40, 1.15]],
    [tFly, [60, -60, 1.05], E.sine],
    [tLand, [2400, -60, 1.0], E.inOut],
    [12, [2400, -80, 1.06], E.sine],
  ], [{ t: tLand + .05, w: .12, amp: 4 }]);

  function desk(t) {
    // open mid-stroke: a draw-on that starts from nothing reads as blank frames
    const head = (a, d) => clamp(.2 + .8 * E.out(SK.inv(a, a + d, t)));
    P.table(-420, 420, 160, 400, head(0, .8), 300);
    P.floor(-700, 700, 400, head(0, .8), 360);
    const k = head(.1, 1.1);
    if (t < tFly) P.ticket({ x: 0, y: -40, s: .9, p: k, title: 'INVITE', subtitle: 'one free week', mood: t > w(0, 'waiting', 1.5) ? 'sad' : 'open', mouth: 'smile', arms: [.3, .3] });
    SK.txt('An invite, unused.', 0, -330, { size: 84, p: tw(t, w(0, 'an', .5), w(0, 'waiting', 2) + .4, E.lin) });
  }
  function friend(t) {
    P.floor(-600, 800, 330 + FRIEND[1], 1, 370);
    P.table(FRIEND[0] - 20, FRIEND[0] + 540, 120, 330, 1, 310);
    P.laptop(FRIEND[0] + 230, -40, {});
    const cheer = t > tLand + .2;
    P.person({ x: FRIEND[0] - 140, y: 80, hair: 'spiky', mood: cheer ? 'happy' : 'open', mouth: cheer ? 'big' : 'smile', arms: P.poseAt(t, [[0, 'chin'], [tLand - .3, 'hold'], [tLand + .6, 'cheer']]) });
    const lb = pop(t, tLand + .3, .5);
    if (lb > 0) P.lightbulb(FRIEND[0] - 150, -330, lb, .6);
  }

  SK.film({
    duration: 12,
    camera,
    automation: { plane: { t0: flight.t0, t1: flight.t1, pos: flight.pos } },
    draw(t, vis) {
      if (vis(-800, -700, 800, 500)) desk(t);
      if (vis(1600, -700, 3200, 500)) friend(t);
      if (t >= tFly && t <= tLand) {
        const [x, y] = flight.pos(t), a = flight.angle(t);
        SK.dashes(flight.pts(flight.t0, t - .03, .01), { on: 3, off: 4, w: 6, col: C.orangeDk, alpha: .8 });
        P.plane(x, y, a, 2.2, { flip: Math.cos(a) < 0 ? -1 : 1 });
      }
      if (t > tLand && t < tLand + .6) SK.puff(FRIEND[0], 20, 50 + 80 * (t - tLand), 1 - (t - tLand) / .6, 3);
      SK.txt('Pass it on.', FRIEND[0] + 60, -420, { size: 96, col: C.orangeDk, p: tw(t, w(2, 'pass', 9), w(2, 'on', 10) + .5, E.lin) });
    },
  });
})();
