/* studio/outro.js -- KitCut's closing and watermark, for films made on the Free plan.

   The studio appends this after the film's own code at the final render (the manifest's
   `tail`); the film knows nothing of it, and Claude's review stills never show it. SK.OUTRO, set
   just before this runs, may override the words: { line, url, secs }. The logo is SK.IMG.kitcut.

   - The watermark: "made with" over "kitcut.ai", bottom right, throughout the film, as far
     from the right edge as from the bottom (measured, not guessed). It gives way to the closing.
   - The closing, `secs` (3) after the film: the film's last frame turns into a tilted snapshot
     on the film's own ground, and beside it the logo, "Make your own film" and kitcut.ai. The
     film is held at its end underneath (every frame is a pure function of t, so holding it is
     drawing it at its end). Its sound (a chime, "Make yours at KitCut AI") is the tail's audio.
*/
(function () {
  'use strict';
  const F = SK._film; if (!F) return;
  const O = { line: 'Make your own film', url: 'kitcut.ai', secs: 3, ...(SK.OUTRO || {}) };
  const { S, E, clamp, tw, pop } = SK;
  const W = SK.W, H = SK.H, D = F.duration;
  const hold = (t) => Math.min(t, D - 1 / 120);
  const draw = F.draw, cam = F.camera, own = F.overlay;
  F.duration = D + O.secs;
  F.camera = { ...cam, at: (t) => cam.at(hold(t)), shake: (t) => cam.shake(hold(t)) };
  F.draw = (t, vis) => draw(hold(t), vis);
  F.fadeOut = 0; // the closing holds to the last frame: what a paused or finished video shows
  F.overlay = (t) => {
    if (own) own(hold(t));
    const u = t - D;
    const img = u >= 0 ? snapshot() : null; // the film's last frame, taken before the mark
    const leave = u < 0 ? 1 : 1 - clamp(u / .3);
    if (leave > 0) mark(leave);
    if (u >= 0) closing(u, img);
  };

  const ctx = () => SK.ctx();
  const logoW = (h) => { const im = SK.IMG.kitcut; return im ? h * im.width / im.height : 0; };
  const logo = (x, y, h, a = 1) => { if (SK.IMG.kitcut && a > 0) SK.image('kitcut', x, y, logoW(h), h, { alpha: a }); };
  let snap = null;
  function snapshot() {
    const c = ctx().canvas;
    snap ??= Object.assign(document.createElement('canvas'), { width: c.width, height: c.height });
    const g = snap.getContext('2d'); g.clearRect(0, 0, W, H); g.drawImage(c, 0, 0);
    return snap;
  }

  /* ---------------------------------------------------------------- the watermark */
  const GAP = 40, FONT = 'Balsamiq Sans';
  const LINES = [{ s: 'made with', size: 24, wt: 400, stroke: 5 }, { s: O.url, size: 36, wt: 700, stroke: 6 }];
  let box = null; // the mark's layout, measured once the fonts are in
  function layout() {
    const c = ctx(); c.save(); c.textBaseline = 'middle';
    const m = LINES.map((L) => {
      c.font = `${L.wt} ${L.size}px "${FONT}"`;
      // SK.txt lays the letters out by their advances around the centre: the ink ends at the
      // last letter's own right edge, a little short of its advance
      const chars = [...L.s], adv = chars.map((ch) => c.measureText(ch).width), last = c.measureText(chars[chars.length - 1]);
      const total = adv.reduce((a, b) => a + b, 0), r = c.measureText(L.s);
      const right = total / 2 - adv[adv.length - 1] + last.actualBoundingBoxRight + L.stroke / 2;
      return { ...L, right, up: r.actualBoundingBoxAscent + L.stroke / 2, down: r.actualBoundingBoxDescent + L.stroke / 2 };
    });
    c.restore();
    const cx = W - GAP - Math.max(...m.map((L) => L.right)); // the ink's right edge GAP from the frame's
    const y2 = H - GAP - m[1].down, y1 = y2 - m[1].up - 4 - m[0].down; // the address, and above it "made with"
    return { cx, ys: [y1, y2], lines: m };
  }
  function mark(a) {
    box ??= layout();
    const c = ctx(); c.save(); c.globalAlpha *= a;
    box.lines.forEach((L, i) => SK.txt(L.s, box.cx, box.ys[i], { size: L.size, font: FONT, wt: L.wt, col: '#ffffff', stroke: L.stroke, strokeCol: 'rgba(20,30,25,.72)', mode: 'rise', wob: 0 }));
    c.restore();
  }

  /* ---------------------------------------------------------------- the closing: a snapshot */
  function closing(u, img) {
    const C = SK.C, c = ctx(), k = E.inOut(clamp(u / .7));
    c.save(); c.fillStyle = C.paper; c.fillRect(0, 0, W, H); c.restore();
    const s = 1 - .52 * k, rot = -.07 * k, cx = W / 2 + (W * .29 - W / 2) * k, cy = H / 2 + 10 * k, b = 22 * k / s;
    c.save(); c.translate(cx, cy); c.rotate(rot); c.scale(s, s);
    c.shadowColor = 'rgba(0,0,0,.25)'; c.shadowBlur = 40 * k; c.shadowOffsetY = 14 * k;
    c.fillStyle = '#ffffff'; c.fillRect(-W / 2 - b, -H / 2 - b, W + 2 * b, H + 2 * b + 70 * k / s);
    c.shadowColor = 'transparent'; c.drawImage(img, -W / 2, -H / 2, W, H);
    c.restore();
    const x = W * .745, lp = pop(u, .6, .5);
    if (lp > 0) SK.at(x, H / 2 - 190, 0, lp, () => logo(0, 0, 230));
    SK.txt(O.line, x, H / 2 + 20, { size: 70, col: C.textSoft ?? C.inkSoft, p: tw(u, .9, 1.4, E.lin) });
    SK.txt(O.url, x, H / 2 + 135, { size: 128, col: C.accentText ?? C.orangeDk, p: tw(u, 1.2, 1.8, E.lin) });
    SK.ink(S.line(x - 200, H / 2 + 205, x + 200, H / 2 + 198, -6), { w: 8, col: C.accent ?? C.orange, seed: 78, p: tw(u, 1.75, 2.05) });
  }
})();
