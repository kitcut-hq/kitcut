/* Studio example 2 -- "The lever" (10 s, drawn, clean line art on the blueprint ground).
   Narration (vo.json):
     0 "A lever turns a small push into a big lift."
     1 "Push the long end down, and the rock rises."
   An explainer as a diagram: printed labels, measured arrows, one moving part, and the rule on a
   card at the end. On a dark ground a bare line takes col: C.text; outlines of filled shapes
   stay C.ink. */
(function () {
  'use strict';
  const { S, E, clamp, tw, pop } = SK;
  const w = (li, word, fb, n = 0) => SK.w(li, word, fb, 's', n);
  SK.setStyle('clean');
  SK.setGround('blueprint'); // a drafting grid comes with it
  const C = SK.C;
  const F = 'Balsamiq Sans';

  const tLever = w(0, 'lever', .4), tPush = w(1, 'push', 5.2), tRises = w(1, 'rises', 6.6);
  const PIV = [-160, 120];                              // the pivot, and the beam's two arms
  const beam = (t) => .2 * tw(t, tPush, tRises + .4, E.back); // the beam's turn: the long end goes down
  const end = (a, L) => [PIV[0] + Math.cos(a) * L, PIV[1] + Math.sin(a) * L];

  SK.film({
    duration: 10,
    camera: SK.camera([[0, [0, 0, 1.08]], [tPush, [0, 20, 1.02]], [10, [0, 20, 1.06], E.sine]]),
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
      const k = tw(t, tPush - .3, tPush + .3);
      SK.ink(S.line(R[0] - 10, R[1] - 260, R[0] - 10, R[1] - 40), { w: 6, col: C.text, seed: 9, p: k });
      SK.ink(S.poly([[R[0] - 34, R[1] - 70], [R[0] - 10, R[1] - 40], [R[0] + 14, R[1] - 70]]), { w: 6, col: C.text, seed: 11, p: clamp(k * 2 - 1) });
      SK.txt('small push', R[0] - 10, R[1] - 300, { size: 44, font: F, p: k });
      const up = tw(t, tRises - .1, tRises + .5);
      SK.ink(S.line(L[0] + 80, L[1] - 200, L[0] + 80, L[1] - 330), { w: 12, col: C.accentText, seed: 10, p: up });
      SK.ink(S.poly([[L[0] + 46, L[1] - 292], [L[0] + 80, L[1] - 334], [L[0] + 114, L[1] - 292]]), { w: 12, col: C.accentText, seed: 12, p: clamp(up * 2 - 1) });
      SK.txt('big lift', L[0] + 80, L[1] - 380, { size: 56, font: F, wt: 700, col: C.accentText, p: up });
      // the arms, measured under the beam
      SK.dashes(S.line(PIV[0], 330, PIV[0] + 700, 330), { alpha: .8 });
      SK.dashes(S.line(PIV[0] - 300, 330, PIV[0], 330), { alpha: .8, col: C.accentText });
      SK.txt('long arm', PIV[0] + 350, 375, { size: 40, font: F, col: C.textSoft, p: head(tLever, .5) });
      SK.txt('short arm', PIV[0] - 150, 375, { size: 40, font: F, col: C.textSoft, p: head(tLever, .5) });
      // the rule, on a card, as the rock settles
      const c = pop(t, tRises + 1.2);
      if (c > 0) SK.at(420, -330, 0, c, () => {
        SK.card(-310, -60, 620, 120, { fill: 'rgba(255,255,255,.12)', stroke: C.text, shadow: false });
        SK.txt('long × small = short × big', 0, 0, { size: 46, font: F, wt: 700 });
      });
    },
  });
})();
