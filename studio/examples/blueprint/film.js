/* Studio example 2 -- "The lever" (10 s, drawn, clean line art on the blueprint ground).
   Narration (vo.json):
     0 "A lever turns a small push into a big lift."
     1 "Push the long end down, and the rock rises."
   An explainer as a diagram: printed labels, measured arrows, one moving part, and the rule on a
   card at the end -- the arrows, the measures and the card from the kit, the lever drawn by hand.
   On a dark ground a bare line takes col: C.text; outlines of filled shapes stay C.ink. */
(function () {
  'use strict';
  const { S, E, clamp, tw } = SK;
  SK.setStyle('clean');
  SK.setGround('blueprint'); // a drafting grid comes with it
  const C = SK.C;
  const F = 'Balsamiq Sans';

  // every cue at once (the fallbacks only because this example is shown without its recording)
  const T = SK.cues({ lever: [0, 'lever'], push: [1, 'push'], rises: [1, 'rises'] },
    { fallback: { lever: .4, push: 5.2, rises: 6.6 } });
  const PIV = [-160, 120];                              // the pivot, and the beam's two arms
  const beam = (t) => .2 * tw(t, T.push, T.rises + .4, E.back); // the beam's turn: the long end goes down
  const end = (a, L) => [PIV[0] + Math.cos(a) * L, PIV[1] + Math.sin(a) * L];

  SK.film({
    duration: 10,
    camera: SK.camera([[0, [0, 0, 1.08]], [T.push, [0, 20, 1.02]], [10, [0, 20, 1.06], E.sine]]),
    draw(t) {
      const head = (a, d) => clamp(.2 + .8 * E.out(SK.inv(a, a + d, t)));
      SK.txt('The lever', -600, -400, { size: 84, font: F, wt: 700, align: 'left', p: head(0, .6) });
      const a = beam(t), L = end(a + Math.PI, 300), R = end(a, 700);
      // the pivot, the beam, the rock on its short end
      const piv = S.poly([[PIV[0] - 60, PIV[1] + 90], [PIV[0], PIV[1] + 8], [PIV[0] + 60, PIV[1] + 90]], true);
      SK.wash(piv, C.accent, { seed: 3 }); SK.ink(piv, { w: 5, seed: 4, p: head(.1, .6) });
      SK.at(PIV[0], PIV[1], a, 1, () => {
        const b = S.rrect(-300, -14, 1000, 28, 8);
        SK.wash(b, '#dfe9f7', { seed: 5 }); SK.ink(b, { w: 5, seed: 6, p: head(.2, .8) });
        const rock = S.poly([[-290, -14], [-300, -110], [-230, -170], [-150, -150], [-120, -60], [-140, -14]], true);
        SK.wash(rock, '#9aa3ad', { seed: 7, alpha: head(.4, .6) }); SK.ink(rock, { w: 5, seed: 8, p: head(.4, .6) });
      });
      // the arrows and their labels: the push (long, small) and the lift (short, big)
      SK.arrow(R[0] - 10, R[1] - 260, R[0] - 10, R[1] - 40, { col: C.text, w: 6, bow: 0, in: { t: T.push - .3, d: .6 } });
      SK.txt('small push', R[0] - 10, R[1] - 300, { size: 44, font: F, p: tw(t, T.push - .3, T.push + .3) });
      SK.arrow(L[0] + 80, L[1] - 200, L[0] + 80, L[1] - 330, { col: C.accentText, w: 12, bow: 0, head: 34, in: { t: T.rises - .1, d: .6 } });
      SK.txt('big lift', L[0] + 80, L[1] - 380, { size: 56, font: F, wt: 700, col: C.accentText, p: tw(t, T.rises - .1, T.rises + .5) });
      // the arms, measured under the beam
      SK.dimension(PIV[0], 330, PIV[0] + 700, 330, 'long arm', { t: T.lever, col: C.textSoft, side: 1, gap: 45, size: 40, font: F });
      SK.dimension(PIV[0] - 300, 330, PIV[0], 330, 'short arm', { t: T.lever, col: C.accentText, side: 1, gap: 45, size: 40, font: F });
      // the rule, on a card, as the rock settles
      SK.pill('long × small = short × big', 420, -330, { size: 46, font: F, r: 16, fill: 'rgba(255,255,255,.12)', col: C.text, stroke: C.text, in: { t: T.rises + 1.2, type: 'pop' } });
    },
  });
})();
