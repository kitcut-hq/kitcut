/* Model sheet for H3 references: the series' cast drawn alone, large, on a plain ground -- no car seat,
   no harness, no props that would travel with the character into every generated shot.
   t < 1: Leo standing, cheering and holding; 1 <= t < 2: the coupe side-on; t >= 2: Leo's street alone, a style reference with no character. */
(function () {
  'use strict';
  const { S } = SK;
  SK.setStyle('crayon');
  const LEO = SK.cast.leo, CAR = SK.cast.coupe;
  const camera = SK.camera([[0, [0, -160, 1.0]]]);
  SK.film({
    duration: 3,
    camera,
    draw(t) {
      SK.wash(S.poly([[-3000, -2000], [3000, -2000], [3000, 2000], [-3000, 2000]], true), '#f6f3ec', { seed: 1, dx: 0, dy: 0 });
      if (t < 1) {
        const o = { s: 1.45, feet: 'bare', blink: 0 };  // sunglasses over his eyes, as in ep 12's first minute
        LEO.draw(-560, 320, { ...o, arms: 'rest', mouth: 'smile' });
        LEO.draw(0, 320, { ...o, arms: 'cheer', mouth: 'big' });
        LEO.draw(560, 320, { ...o, arms: 'hold', mouth: 'smile', lookX: .3 });
      } else if (t < 2) {
        CAR.draw(0, 200, { s: 1.9, dir: 1 });
      } else {
        SK.cast.street.draw(-3330, 150, { t: 0 });
      }
    },
  });
})();
