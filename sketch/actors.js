/* sketch/actors.js -- actors: characters an image model drew, cut into packs by
   scripts/actor-pack.py, animated by swapping pieces (an engine module a film opts into; added by
   itself when the manifest names "actors", with heads.js, whose SK.talk moves the mouths).

   A pack is the figure (front, full length), a patch for each face it pulls, a patch for each
   mouth shape on the faces that talk, a blink, and whole-figure poses, all on one or more atlas
   pages. Every frame is a pure function of t:
     * the mouth follows the speaker's own voice (SK.talk: how open, how wide), on twos;
     * the eyes blink on a clock seeded by the actor's name;
     * the figure bobs a little on its own voice.

   SK.actor(name, x, y, h, o) draws actor `name` standing with its feet at x, y and the figure h
   tall (every pose at the same scale). o:
     face   'neutral' (default) or one of the pack's faces ('happy', 'angry', 'shocked', ...)
     pose   null (the front figure) or one of its poses ('wave', 'point', 'turn_right', ...)
     mouth  'auto' (default: the voice moves it), 'none', or one to hold ('small' | 'open' |
            'round' | 'wide')
     who    the speaker whose lines move the mouth (default: the actor's name)
     blink  true (default), false, or 0..1 to hold the lids there
     steps  mouth changes a second (default 12: on twos; 0 = every frame)
     flip   mirror (to face the other way); tilt (radians, about the feet); squash (+ squashes,
            - stretches, about the feet); alpha; bob (x the default, 1)
     t      the time (default SK.T)
   A face other than 'neutral' on a pose is laid on where the pose still looks out of the picture
   (the pack says where its head is); a pose that has turned talks with mouths of its own.
   Returns {x, y, h, box, head, mouth}: where the figure and its head are on the page this frame
   (boxes [x0, y0, x1, y1]) and the mouth drawn.

   SK.actorBox(name, x, y, h, o) -> the box the actor fills, without drawing it.
   SK.actorHas(name) -> {faces: [...], poses: [...], talk: [...]}: what the pack holds.
   Packs come in as SK.ACTORS[name] with their atlas pages in SK.IMG ('actor:<name>:<n>');
   sketch-render inlines both from the manifest's "actors". */
(function () {
  'use strict';
  const SK = window.SK;
  SK.ACTORS = SK.ACTORS || {};

  function pack(name) {
    const P = SK.ACTORS[name];
    if (!P) throw new Error('SK.actor: no actor named ' + JSON.stringify(name) + ' (the manifest\'s "actors": ' + Object.keys(SK.ACTORS).join(', ') + ')');
    return P;
  }
  /** draw piece `id` of pack P with its top-left at x, y (pack pixels) */
  function blit(c, name, P, id, x, y) {
    const pc = P.pieces[id];
    if (!pc) return;
    const img = SK.IMG['actor:' + name + ':' + pc.p];
    if (!img) return;
    c.drawImage(img, pc.sx, pc.sy, pc.w, pc.h, x, y, pc.w, pc.h);
  }

  /* ------------------------------------------------------------ blinks: heads.js's clock, per actor */
  const BLINKS = new Map();
  function blinkAt(name, t) {
    let list = BLINKS.get(name);
    if (!list) {
      list = []; let seed = 11; for (const ch of name) seed = (seed * 31 + ch.charCodeAt(0)) | 0;
      const r = SK.mulberry(seed); let x = .5 + r() * 1.8;
      while (x < 3600) { list.push(x); if (r() < .12) list.push(x + .34); x += 2.4 + r() * 3.2; }
      BLINKS.set(name, list);
    }
    if (t < list[0]) return 0;
    let lo = 0, hi = list.length - 1;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (list[m] <= t) lo = m; else hi = m - 1; }
    const d = t - list[lo];
    return d > .2 ? 0 : 1;
  }

  /* ------------------------------------------------------------ the mouth from the voice */
  function mouthFor(mouths, v) {
    if (!mouths || v.open < .15) return null;
    if (mouths.round && v.wide < -.3) return 'round';
    if (mouths.wide && v.wide > .35 && v.open >= .3) return 'wide';
    if (mouths.small && v.open < .5) return 'small';
    return mouths.open ? 'open' : mouths.small ? 'small' : null;
  }

  /** where everything goes this frame: the piece, its feet, the face/mouth/blink patches */
  function layout(name, P, o, t) {
    const face = o.face || 'neutral', F = P.faces[face] || P.faces.neutral || {};
    const pose = o.pose && P.poses[o.pose] ? P.poses[o.pose] : null;
    const out = { piece: pose ? pose.piece : 'base', feet: pose ? pose.feet : P.figure.feet, w: pose ? pose.w : P.figure.w, h: pose ? pose.h : P.figure.h, layers: [] };
    const at = pose ? pose.face_at : [0, 0];
    // the face: on the front figure, or on a pose that still looks out of the picture
    if (at && face !== 'neutral' && F.piece) out.layers.push([F.piece, F.x + at[0], F.y + at[1]]);
    // the mouth: the face's own (front), or the pose's own (turned)
    const mouths = at ? F.mouths : pose.mouths;
    let m = null;
    if (o.mouth && o.mouth !== 'auto') m = o.mouth === 'none' ? null : o.mouth;
    else if (SK.talk) {
      const steps = o.steps ?? 12, tt = steps ? Math.floor(t * steps) / steps : t;
      m = mouthFor(mouths, SK.talk(o.who || name, tt));
    }
    if (m && mouths && mouths[m]) {
      const pt = mouths[m];
      out.layers.push(at ? [pt.piece, pt.x + at[0], pt.y + at[1]] : [pt.piece, pt.x, pt.y]);
    } else m = null;
    out.mouth = m;
    // the blink: the face's (front) or the pose's own
    const bl = at ? F.blink : pose && pose.blink;
    const b = o.blink === false ? 0 : typeof o.blink === 'number' ? o.blink : blinkAt(name, t);
    if (bl && b > .5) out.layers.push(at ? [bl.piece, bl.x + at[0], bl.y + at[1]] : [bl.piece, bl.x, bl.y]);
    return out;
  }

  function place(name, x, y, h, o, t) {
    const P = pack(name), L = layout(name, P, o, t);
    const k = h / P.figure.height;
    const v = SK.talk ? SK.talk(o.who || name, t) : { open: 0 };
    const bob = (o.bob ?? 1) * v.open * .006 * h;
    const tilt = (o.tilt || 0) + (o.bob ?? 1) * Math.sin(t * 8.5) * v.open * .012;
    return { P, L, k, bob, tilt };
  }

  SK.actor = function (name, x, y, h, o = {}) {
    const c = SK.ctx(), t = o.t ?? SK.T;
    const { P, L, k, bob, tilt } = place(name, x, y, h, o, t);
    const sq = o.squash || 0;
    c.save();
    if (o.alpha != null) c.globalAlpha *= o.alpha;
    c.translate(x, y - bob);
    if (o.flip) c.scale(-1, 1);
    if (tilt) c.rotate(tilt);
    c.scale(k * (1 - sq * .6), k * (1 + sq));
    const fx = -L.feet[0], fy = -L.feet[1];
    blit(c, name, P, L.piece, fx, fy);
    for (const [id, px, py] of L.layers) blit(c, name, P, id, fx + px, fy + py);
    c.restore();
    return Object.assign(SK.actorBox(name, x, y, h, o), { mouth: L.mouth });
  };

  SK.actorBox = function (name, x, y, h, o = {}) {
    const P = pack(name), t = o.t ?? SK.T;
    const pose = o.pose && P.poses[o.pose] ? P.poses[o.pose] : null;
    const k = h / P.figure.height, feet = pose ? pose.feet : P.figure.feet;
    const w = pose ? pose.w : P.figure.w, hh = pose ? pose.h : P.figure.h;
    const s = o.flip ? -1 : 1;
    const xs = [x - feet[0] * k * s, x + (w - feet[0]) * k * s].sort((a, b) => a - b);
    const box = [xs[0], y - feet[1] * k, xs[1], y + (hh - feet[1]) * k];
    const at = pose ? pose.face_at : [0, 0], hd = P.figure.head;
    let head = null;
    if (at) {
      const hx = [x + (hd[0] + at[0] - feet[0]) * k * s, x + (hd[2] + at[0] - feet[0]) * k * s].sort((a, b) => a - b);
      head = [hx[0], y + (hd[1] + at[1] - feet[1]) * k, hx[1], y + (hd[3] + at[1] - feet[1]) * k];
    }
    void t;
    return { x, y, h, box, head };
  };

  SK.actorHas = function (name) {
    const P = pack(name);
    return { faces: Object.keys(P.faces), poses: Object.keys(P.poses), talk: Object.keys(P.faces).filter((f) => Object.keys(P.faces[f].mouths || {}).length) };
  };
})();
