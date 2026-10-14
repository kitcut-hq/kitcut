// For: a product walkthrough built from screenshots, with no screen recording at all
/* Two stills of an app (screens/app-1.png, app-2.png: the same window before and after) under a
   moving camera. Everything that looks like the app working is drawn here, on the voice's words:

     cover()   a patch of the page's own colour over part of a screenshot -- the LATER screenshot is
               shown from the start with its new parts covered, and each cover comes off on its cue
               (a file chip appears; a wipe along a line types the prompt)
     ring()    the blue outline round the thing being named
     cursor    SK.cursorPath + SK.cursor, clicking on the cue

   Positions are SCREENSHOT PIXELS, read straight off the picture and mapped by px()/py(), so the
   code and the picture agree without arithmetic. Rules that cost a re-render to learn:
   - every screenshot the same window size, and sharp: zoom z shows the picture at z * K, so past
     ~1.4 a 1920-wide shot goes soft (shoot at a device pixel ratio of 2);
   - a phone screenshot has 30-40 px side margins: do not zoom it at all, let it fill the frame;
   - a logo PNG is rarely centred in its own canvas -- crop it to its ink before putting it on a plate. */
SK.setStyle('clean', { grain: 0, vignette: 0, handheld: 0 });
SK.setGround('white', { paper: '#eef2f7', text: '#0b1730', textSoft: '#51607a', accent: '#2563eb', accentText: '#2563eb' });
SK.KIT.font = 'Inter';

const { clamp, inv, E } = SK;
const BLUE = '#2563eb';
const SW = 1600, SH = 900, K = 1760 / SW;                 // the screenshot, and how wide it lies in the world
const px = (x) => (x - SW / 2) * K, py = (y) => (y - SH / 2) * K;
const L = (i) => SK.line(i);
const T = SK.cues({ assistant: [0, 'assistant'], files: [0, 'files'], say: [1, 'say'], send: [2, 'send'] });
const SEND = T.send + .35;

const cam = (t, x, y, z) => [t, [px(x), py(y), z]];
const CAM = SK.camera([
  cam(0, 800, 450, 1), cam(T.assistant + .5, 800, 380, 1.1), cam(T.files - .6, 800, 380, 1.1),
  cam(T.files + .3, 950, 400, 1.45), cam(SEND, 990, 410, 1.5), cam(SEND + .9, 800, 450, 1),
]);

const ctx = () => SK.ctx();
function cover(x0, y0, x1, y1, col = '#ffffff') { const c = ctx(); c.fillStyle = col; c.fillRect(px(x0), py(y0), (x1 - x0) * K, (y1 - y0) * K); }
function ring(x0, y0, x1, y1, t0, t1, r = 12) {
  const t = SK.T, a = SK.win(t, t0, t1, .22, .22); if (a <= 0) return;
  const z = CAM.at(t)[2], pad = 8 + 14 * (1 - E.out(inv(t0, t0 + .3, t))), c = ctx();
  c.save(); c.globalAlpha *= a; SK.rrPath(px(x0) - pad, py(y0) - pad, (x1 - x0) * K + 2 * pad, (y1 - y0) * K + 2 * pad, r);
  c.lineWidth = 5 / z; c.strokeStyle = BLUE; c.stroke(); c.globalAlpha *= .1; c.fillStyle = BLUE; c.fill(); c.restore();
}

SK.film({
  duration: 9.5,
  camera: CAM,
  handheld: false,
  draw(t) {
    const c = ctx(), x = px(0), y = py(0), w = SW * K, h = SH * K;
    c.save(); c.shadowColor = 'rgba(15,30,60,.22)'; c.shadowBlur = 60; c.shadowOffsetY = 24; SK.rrPath(x, y, w, h, 14); c.fillStyle = '#fff'; c.fill(); c.restore();
    c.save(); SK.rrPath(x, y, w, h, 14); c.clip();
    const two = t >= T.files - .1;                         // the second screenshot, its new parts still covered
    SK.image(two ? 'a2' : 'a1', 0, 0, w, h);
    if (two) {
      if (t < T.files) cover(496, 316, 640, 354);          // chip 1
      if (t < T.files + .45) cover(640, 316, 766, 354);    // chip 2
      const p = clamp(inv(T.say, L(1).end - .1, t)), xr = 498 + p * 340;
      cover(xr, 358, 900, 392);                            // the prompt, wiped on as if typed
      if (p > 0 && p < 1 && Math.floor(t * 2.2) % 2 === 0) cover(xr + 2, 362, xr + 4, 388, '#111827');
    }
    c.restore();

    ring(356, 14, 469, 50, T.assistant - .1, T.files - .5, 22);
    ring(501, 320, 637, 350, T.files + .05, T.files + .45, 18);
    ring(645, 320, 761, 350, T.files + .5, T.say - .1, 18);
    ring(492, 358, 846, 392, T.say, L(1).end + .3);
    ring(1361, 441, 1401, 481, L(2).start, SEND + .15);

    const P = SK.cursorPath([[0, 1150, 700], [T.assistant - .7, 1150, 700], [T.assistant, 414, 36], [T.files - .9, 414, 36], [T.files - .25, 518, 418],
      [T.files - .1, 518, 462], [T.say, 640, 430], [L(2).start - .2, 700, 440], [SEND - .3, 1383, 464]].map(([tk, a, b]) => [tk, px(a), py(b)]));
    const [cx, cy] = P(t);
    SK.cursor(cx, cy, { s: 1.7 / Math.sqrt(CAM.at(t)[2]), click: [T.assistant + .15, T.files - .2, SEND], rippleCol: BLUE });
  },
});
