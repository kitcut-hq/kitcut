/* puppet.js (prototype) -- a rigged cut-out actor: one A-pose drawing cut into parts on a skeleton
   (puppet_pack.py), skinned on the CPU and drawn with WebGL, then laid on the film's canvas.

   SK.puppet(name, x, y, h, o)       draw it, feet at x, y, the figure h tall. o.pose: {bone: {r, sx,
                                     sy, dx, dy}} (degrees, canvas sense); o.face, o.mouth ('auto'),
                                     o.who, o.blink, o.flip, o.alpha, o.t
   SK.puppetAct(name, plan, t)        the pose and face at t for a plan of acts (below): pure in t
   SK.puppetPlay(name, x, y, h, plan) both: what a film calls */
(function () {
  'use strict';
  const SK = window.SK;
  SK.PUPPETS = SK.PUPPETS || {};
  const D2R = Math.PI / 180;

  // ------------------------------------------------------------------ affine 2D [a b c d e f]
  function mul(m, n) {
    return [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3],
      m[1] * n[2] + m[3] * n[3], m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
  }
  function about(px, py, deg, sx, sy, dx, dy) {  // T(p + d) R(deg) S T(-p)
    const r = deg * D2R, c = Math.cos(r), s = Math.sin(r);
    const a = c * sx, b = s * sx, cc = -s * sy, d = c * sy;
    return [a, b, cc, d, px + dx - (a * px + cc * py), py + dy - (b * px + d * py)];
  }
  function inv(m) {
    const det = m[0] * m[3] - m[1] * m[2];
    const a = m[3] / det, b = -m[1] / det, c = -m[2] / det, d = m[0] / det;
    return [a, b, c, d, -(a * m[4] + c * m[5]), -(b * m[4] + d * m[5])];
  }
  const ap = (m, x, y) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
  const ang = (v) => Math.atan2(v[1], v[0]) / D2R;
  const wrap = (a) => ((a + 540) % 360) - 180;

  // ------------------------------------------------------------------ the pack, made ready once
  const READY = new Map();
  function prep(name) {
    if (READY.has(name)) return READY.get(name);
    const P = SK.PUPPETS[name];
    if (!P) throw new Error('SK.puppet: no puppet named ' + JSON.stringify(name));
    const order = [], seen = new Set();
    const visit = (n) => { if (seen.has(n)) return; const p = P.bones[n].parent; if (p) visit(p); seen.add(n); order.push(n); };
    Object.keys(P.bones).forEach(visit);
    const idx = Object.fromEntries(order.map((n, i) => [n, i]));
    const parts = P.parts.map((p) => {
      const n = p.v.length / 2, wi = new Int16Array(n * 4).fill(-1), ww = new Float32Array(n * 4);
      p.w.forEach((row, i) => row.slice(0, 4).forEach(([b, w], k) => { wi[i * 4 + k] = idx[b]; ww[i * 4 + k] = w; }));
      return { name: p.name, page: p.page, n, v: Float32Array.from(p.v), uv: Float32Array.from(p.uv), t: Uint32Array.from(p.t), wi, ww };
    });
    const R = { P, order, idx, parts, byName: Object.fromEntries(parts.map((p) => [p.name, p])) };
    READY.set(name, R);
    return R;
  }

  function matrices(R, q) {
    const M = new Array(R.order.length);
    R.order.forEach((n, i) => {
      const b = R.P.bones[n], j = q[n] || {};
      const L = about(b.pivot[0], b.pivot[1], j.r || 0, j.sx ?? 1, j.sy ?? 1, j.dx || 0, j.dy || 0);
      M[i] = b.parent ? mul(M[R.idx[b.parent]], L) : L;
    });
    return M;
  }

  function skin(part, M) {
    const out = new Float32Array(part.n * 2);
    for (let i = 0; i < part.n; i++) {
      const x = part.v[2 * i], y = part.v[2 * i + 1];
      let X = 0, Y = 0, S = 0;
      for (let k = 0; k < 4; k++) {
        const b = part.wi[i * 4 + k]; if (b < 0) break;
        const w = part.ww[i * 4 + k], m = M[b];
        X += w * (m[0] * x + m[2] * y + m[4]); Y += w * (m[1] * x + m[3] * y + m[5]); S += w;
      }
      out[2 * i] = X / S; out[2 * i + 1] = Y / S;
    }
    return out;
  }

  // ------------------------------------------------------------------ WebGL: one canvas for all
  let G = null;
  const CAN = 2048;
  function gl() {
    if (G) return G;
    const cv = document.createElement('canvas'); cv.width = CAN; cv.height = CAN;
    const g = cv.getContext('webgl2', { premultipliedAlpha: true, alpha: true, antialias: true, preserveDrawingBuffer: true });
    if (!g) throw new Error('SK.puppet: no WebGL2 here');
    const sh = (type, src) => { const s = g.createShader(type); g.shaderSource(s, src); g.compileShader(s); if (!g.getShaderParameter(s, g.COMPILE_STATUS)) throw new Error(g.getShaderInfoLog(s)); return s; };
    const pr = g.createProgram();
    g.attachShader(pr, sh(g.VERTEX_SHADER, '#version 300 es\nin vec2 p; in vec2 uv; in float al; uniform vec4 box; out vec2 v; out float a;\nvoid main(){ vec2 q = (p - box.xy) / box.zw; gl_Position = vec4(q.x * 2.0 - 1.0, 1.0 - q.y * 2.0, 0.0, 1.0); v = uv; a = al; }'));
    g.attachShader(pr, sh(g.FRAGMENT_SHADER, '#version 300 es\nprecision highp float; in vec2 v; in float a; uniform sampler2D tex; out vec4 o;\nvoid main(){ o = texture(tex, v) * a; }'));
    g.linkProgram(pr);
    if (!g.getProgramParameter(pr, g.LINK_STATUS)) throw new Error(g.getProgramInfoLog(pr));
    const buf = g.createBuffer();
    G = { cv, g, pr, buf, aP: g.getAttribLocation(pr, 'p'), aU: g.getAttribLocation(pr, 'uv'), aA: g.getAttribLocation(pr, 'al'), uBox: g.getUniformLocation(pr, 'box'), tex: new Map() };
    return G;
  }
  function texture(img) {
    const { g, tex } = gl();
    if (tex.has(img)) return tex.get(img);
    const t = g.createTexture();
    g.bindTexture(g.TEXTURE_2D, t);
    g.pixelStorei(g.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    g.texImage2D(g.TEXTURE_2D, 0, g.RGBA, g.RGBA, g.UNSIGNED_BYTE, img);
    g.generateMipmap(g.TEXTURE_2D);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MIN_FILTER, g.LINEAR_MIPMAP_LINEAR);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MAG_FILTER, g.LINEAR);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_S, g.CLAMP_TO_EDGE);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_T, g.CLAMP_TO_EDGE);
    tex.set(img, t);
    return t;
  }

  // ------------------------------------------------------------------ the voice and the blink
  function mouthFor(mouths, v) {
    if (!mouths || v.open < 0.15) return null;
    if (mouths.round && v.wide < -0.3) return 'round';
    if (mouths.wide && v.wide > 0.35 && v.open >= 0.3) return 'wide';
    if (mouths.small && v.open < 0.5) return 'small';
    return mouths.open ? 'open' : mouths.small ? 'small' : null;
  }
  const BLINKS = new Map();
  function blinkAt(name, t) {
    let list = BLINKS.get(name);
    if (!list) {
      list = []; let seed = 11; for (const ch of name) seed = (seed * 31 + ch.charCodeAt(0)) | 0;
      const r = SK.mulberry(seed); let x = 0.5 + r() * 1.8;
      while (x < 3600) { list.push(x); if (r() < 0.12) list.push(x + 0.34); x += 2.4 + r() * 3.2; }
      BLINKS.set(name, list);
    }
    if (t < list[0]) return 0;
    let lo = 0, hi = list.length - 1;
    while (lo < hi) { const m = (lo + hi + 1) >> 1; if (list[m] <= t) lo = m; else hi = m - 1; }
    return t - list[lo] > 0.13 ? 0 : 1;
  }
  const talk = (who, t) => (SK.talk ? SK.talk(who, t) : { open: 0, wide: 0, on: false });

  // ------------------------------------------------------------------ drawing
  function quad(run, M, rect, x, y, w, h, extra, alpha = 1) {
    // a patch at base x, y (w x h) through matrix M (and an extra local matrix)
    const m = extra ? mul(M, extra) : M;
    const c = [ap(m, x, y), ap(m, x + w, y), ap(m, x + w, y + h), ap(m, x, y + h)];
    const u = [[rect.u0, rect.v0], [rect.u1, rect.v0], [rect.u1, rect.v1], [rect.u0, rect.v1]];
    for (const k of [0, 1, 2, 0, 2, 3]) run.push(c[k][0], c[k][1], u[k][0], u[k][1], alpha);
  }

  SK.puppet = function (name, x, y, h, o = {}) {
    const R = prep(name), P = R.P, c = SK.ctx(), t = o.t ?? SK.T;
    const M = matrices(R, o.pose || {});
    const head = M[R.idx.head];
    const runs = [];  // [page, [x, y, u, v ...]] in draw order
    const runFor = (page) => { let r = runs[runs.length - 1]; if (!r || r[0] !== page) { r = [page, []]; runs.push(r); } return r[1]; };
    const tri = (part, pos) => { const run = runFor(part.page); for (let i = 0; i < part.t.length; i++) { const k = part.t[i]; run.push(pos[2 * k], pos[2 * k + 1], part.uv[2 * k], part.uv[2 * k + 1], 1); } };
    const props = Object.entries(P.props || {});
    const drawProps = (layer) => {
      for (const [pn, pr] of props) {
        const want = (o.props && o.props[pn]) || {};
        const home = o.propsBack ? 'back' : (want.layer || pr.layer || 'hand_' + pr.bone.slice(-1));
        if (want.hide || home !== layer) continue;
        const rect = P.rects['prop:' + pn];
        const Mb = M[R.idx[want.bone || pr.bone]];
        const at = pr.at;
        const local = mul(about(at[0], at[1], pr.angle + (want.r || 0), 1, 1, 0, 0), [1, 0, 0, 1, at[0] - pr.grip[0], at[1] - pr.grip[1]]);
        quad(runFor(rect.p), Mb, rect, 0, 0, pr.w, pr.h, local);
      }
    };
    // face: the patch, then the mouth from the voice, then the blink
    const face = o.face || 'neutral', F = P.faces[face] || P.faces.neutral;
    const v = talk(o.who || name, t);
    let mouth = null;
    if (o.mouth && o.mouth !== 'auto') mouth = o.mouth === 'none' ? null : o.mouth;
    else { const st = o.steps ?? 12, tt = st ? Math.floor(t * st) / st : t; mouth = mouthFor(F.mouths, talk(o.who || name, tt)); }
    const blink = o.blink === false ? 0 : typeof o.blink === 'number' ? o.blink : (o.blinkNow ? 1 : blinkAt(o.who || name, t));
    // a figure turned to one side has a far arm, drawn behind its body and head
    const facing = (P.facing || 0) * (o.flip ? -1 : 1), far = P.facing === 1 ? 'l' : P.facing === -1 ? 'r' : null;
    const arm = (s) => {
      drawProps('behind_' + s);
      tri(R.byName['arm_' + s], skin(R.byName['arm_' + s], M));
      drawProps('hand_' + s);  // between the forearm and the hand: a fist closes over a handle
      const Hs = (P.hands || {})[s];
      if (Hs) {
        const want = (o.hands || {})[s] || {}, Mh = M[R.idx['hand_' + s]];
        const cur = Hs[want.shape] || Hs.open, prev = want.prev && Hs[want.prev];
        const mix = want.mix ?? 1;
        const put = (h, al) => { const rect = P.rects[h.piece]; if (rect && al > 0.004) quad(runFor(rect.p), Mh, rect, h.x, h.y, rect.w, rect.h, null, al); };
        if (prev && mix < 1) put(prev, 1 - mix);
        if (cur) put(cur, prev && mix < 1 ? mix : 1);
      }
      drawProps('front_' + s);
    };
    drawProps('back');  // a prop swung over the shoulder goes behind the head and the body
    if (far) arm(far);
    for (const pn of ['leg_r', 'leg_l', 'torso', 'head']) tri(R.byName[pn], skin(R.byName[pn], M));
    const patch = (pid, px, py, al = 1) => { const rect = P.rects[pid]; if (rect && al > 0.004) quad(runFor(rect.p), head, rect, px, py, rect.w, rect.h, null, al); };
    const mix = o.faceMix ?? 1, F0 = o.prevFace && P.faces[o.prevFace];
    if (F0 && mix < 1 && F0.piece) patch(F0.piece, F0.x, F0.y, F.piece ? 1 : 1 - mix);
    if (face !== 'neutral' && F.piece) patch(F.piece, F.x, F.y, F0 && mix < 1 ? mix : 1);
    if (mouth && F.mouths && F.mouths[mouth]) patch(F.mouths[mouth].piece, F.mouths[mouth].x, F.mouths[mouth].y); else mouth = null;
    if (blink > 0.5 && F.blink) patch(F.blink.piece, F.blink.x, F.blink.y);
    for (const s of ['r', 'l']) if (s !== far) arm(s);
    // the box it fills this frame, in base pixels
    let bx0 = 1e9, by0 = 1e9, bx1 = -1e9, by1 = -1e9;
    for (const [, d] of runs) for (let i = 0; i < d.length; i += 5) { const X = d[i], Y = d[i + 1]; if (X < bx0) bx0 = X; if (X > bx1) bx1 = X; if (Y < by0) by0 = Y; if (Y > by1) by1 = Y; }
    bx0 = Math.floor(bx0 - 2); by0 = Math.floor(by0 - 2); bx1 = Math.ceil(bx1 + 2); by1 = Math.ceil(by1 + 2);
    const k = h / P.figure.height, tr = c.getTransform();
    let dev = Math.hypot(tr.a, tr.b) * k * (o.res || 1);
    dev = Math.min(dev, CAN / (bx1 - bx0), CAN / (by1 - by0));
    const W = Math.max(1, Math.ceil((bx1 - bx0) * dev)), Hh = Math.max(1, Math.ceil((by1 - by0) * dev));
    const { g, cv, pr, buf, aP, aU, aA, uBox } = gl();
    g.viewport(0, 0, W, Hh);
    g.clearColor(0, 0, 0, 0); g.clear(g.COLOR_BUFFER_BIT);
    g.useProgram(pr);
    g.enable(g.BLEND); g.blendFunc(g.ONE, g.ONE_MINUS_SRC_ALPHA);
    g.uniform4f(uBox, bx0, by0, (bx1 - bx0), (by1 - by0));
    g.bindBuffer(g.ARRAY_BUFFER, buf);
    g.enableVertexAttribArray(aP); g.enableVertexAttribArray(aU); g.enableVertexAttribArray(aA);
    for (const [page, d] of runs) {
      g.bindTexture(g.TEXTURE_2D, texture(SK.IMG['puppet:' + name + ':' + page]));
      g.bufferData(g.ARRAY_BUFFER, new Float32Array(d), g.STREAM_DRAW);
      g.vertexAttribPointer(aP, 2, g.FLOAT, false, 20, 0);
      g.vertexAttribPointer(aU, 2, g.FLOAT, false, 20, 8);
      g.vertexAttribPointer(aA, 1, g.FLOAT, false, 20, 16);
      g.drawArrays(g.TRIANGLES, 0, d.length / 5);
    }
    c.save();
    if (o.alpha != null) c.globalAlpha *= o.alpha;
    c.translate(x, y); c.scale(k * (o.flip ? -1 : 1), k); c.translate(-P.figure.feet[0], -P.figure.feet[1]);
    c.drawImage(cv, 0, CAN - Hh, W, Hh, bx0, by0, bx1 - bx0, by1 - by0);
    c.restore();
    const hp = ap(head, P.bones.head.pivot[0], P.bones.head.pivot[1]);
    return { box: [bx0, by0, bx1, by1], mouth, k, headPivot: hp, facing };
  };

  // ------------------------------------------------------------------ acting: a plan -> a pose
  // limb angles are "out": away from the body's middle (an arm raised sideways is out +90). Sides
  // are the character's: r is on the picture's left (front view)
  const SIGN = { r: 1, l: -1 };
  const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
  const backOut = (x) => { if (x <= 0) return 0; if (x >= 1) return 1; const s = 1.4, u = x - 1; return 1 + (s + 1) * u * u * u + s * u * u; };
  const smooth = (x) => ease(x);
  // arriving: a little anticipation, a slow start, an overshoot that settles (easeInOutBack). The
  // first ease (backOut) left at 4.4x linear speed: every gesture leapt off its mark (motion.py)
  const arrive = (x) => {
    if (x <= 0) return 0; if (x >= 1) return 1;
    const c = 0.9 * 1.525;
    return x < 0.5 ? ((2 * x) ** 2 * ((c + 1) * 2 * x - c)) / 2 : ((2 * x - 2) ** 2 * ((c + 1) * (2 * x - 2) + c) + 2) / 2;
  };

  // gestures: (side, u: 0..1 through the hold, lt: seconds into it, o) -> {bone: out degrees}; bone
  // names use S for the side ('arm_S_up'), O for the other
  const GESTURES = {
    wave: (lt, o) => { const w = Math.sin(lt * 2 * Math.PI * (o.rate || 2.0)); return { arm_S_up: 102, arm_S_lo: 52 + 20 * w, hand_S: 8 * w, head: 4 }; },
    present: (lt) => ({ arm_S_up: 34, arm_S_lo: 52, hand_S: 26, head: 3 + 1.5 * Math.sin(lt * 2.1) }),
    point: () => ({ arm_S_up: 80, arm_S_lo: 6, hand_S: 2, head: 5 }),
    shrug: () => ({ arm_S_up: -16, arm_O_up: -16, arm_S_lo: 78, arm_O_lo: 78, hand_S: 34, hand_O: 34, raise: 22, head: -8 }),
    cheer: (lt) => ({ arm_S_up: 128 + 5 * Math.sin(lt * 8), arm_O_up: 126 + 5 * Math.sin(lt * 8 + 1), arm_S_lo: -8, arm_O_lo: -8, hand_S: 4, hand_O: 4, lean: -2, bounce: 1 }),
    think: () => ({ ik_S: 'chin', hand_S: 40, head: 6, lean: 1.5 }),
    me: () => ({ ik_S: 'chest', hand_S: 20, head: -3 }),  // a hand on the chest: "I", "me"
    nod: (lt) => ({ head: 5 * Math.sin(lt * 2 * Math.PI * 1.6) }),
    lean_in: () => ({ lean: 4, head: 2 }),
  };
  // a keyed gesture: poses at points through it (u, 0..1 of its dur), eased between
  function keyed(keys) {
    return (lt, o) => {
      const u = Math.max(0, Math.min(1, lt / (o.dur || 1)));
      let i = 0;
      while (i < keys.length - 2 && u > keys[i + 1][0]) i++;
      const [u0, A] = keys[i], [u1, B] = keys[i + 1];
      const k = smooth((u - u0) / Math.max(1e-6, u1 - u0));
      const out = {};
      for (const b of new Set([...Object.keys(A), ...Object.keys(B)])) out[b] = (A[b] ?? 0) + k * ((B[b] ?? 0) - (A[b] ?? 0));
      return out;
    };
  }
  // a forehand with what the hand holds: the backswing, the hit at u = 0.45, the follow-through
  GESTURES.swing = keyed([
    [0, { arm_S_up: -6, arm_S_lo: 0, hand_S: 0 }],
    [0.3, { arm_S_up: 72, arm_S_lo: 30, hand_S: 40, lean: -4, head: -3, twist: 1, shift: -1, sink: 0.5 }],
    [0.45, { arm_S_up: 18, arm_S_lo: 10, hand_S: 0, lean: 1, head: 0, twist: 0, shift: 0.4, sink: 1 }],
    [0.62, { arm_S_up: -88, arm_S_lo: -84, hand_S: 30, lean: 5, head: 4, twist: -0.8, shift: 1, sink: 0.6, prop_back: 1 }],
    [1, { arm_S_up: -80, arm_S_lo: -76, hand_S: 26, lean: 3, head: 3, twist: -0.5, shift: 0.8, sink: 0.4, prop_back: 1 }],
  ]);
  // a forehand seen from the side (a turned view: the figure faces where the ball goes), the racket
  // in the near hand. "Out" for the near arm is backwards here, so the backswing is positive and the
  // swing comes through low in front and finishes high across the body: contact at u = 0.45
  GESTURES.forehand = keyed([
    [0, { arm_S_up: -6, arm_S_lo: 0, hand_S: 0 }],
    [0.28, { arm_S_up: 64, arm_S_lo: 38, hand_S: 34, sink: 1.3, shift: -1, head: -2, squash: 0.15 }],
    [0.45, { arm_S_up: -22, arm_S_lo: -6, hand_S: -6, sink: 1.1, shift: 0.7, head: 1 }],
    [0.64, { arm_S_up: -118, arm_S_lo: -64, hand_S: -18, sink: 0.6, shift: 1.1, head: 2, squash: -0.1 }],
    [1, { arm_S_up: -70, arm_S_lo: -46, hand_S: -10, sink: 0.8, shift: 0.6, head: 1 }],
  ]);
  // a hop: down into the knees, up off both feet (stretched), the legs tucked in the air, and
  // down into the knees again (squashed). o.height in figure heights (0.12)
  GESTURES.hop = (lt, o) => {
    const d = o.dur || 0.9, u = lt / d;
    if (u <= 0 || u >= 1) return {};
    const c0 = 0.3, c1 = 0.72;  // take-off, landing
    if (u < c0) { const k = smooth(u / c0); return { sink: 1.6 * k, squash: 0.5 * k }; }
    if (u < c1) {
      const a = (u - c0) / (c1 - c0);
      return { hop: 4 * a * (1 - a) * (o.height ?? 0.12) / 0.12, tuck: Math.sin(Math.PI * a), squash: -0.7 * (1 - a) * (1 - a) };
    }
    const k = 1 - smooth((u - c1) / (1 - c1));
    return { sink: 1.4 * k, squash: 0.7 * k * k };
  };
  // dejected: shoulders and head down, the knees giving a little
  GESTURES.sag = (lt) => ({ sag: 1, head: 5 + 1.5 * Math.sin(lt * 1.7) });
  // ready: knees bent, feet a little wider, as before a ball
  GESTURES.ready = (lt) => ({ sink: 1 + 0.15 * Math.sin(lt * 5), stance: 1 });
  const KEYED = new Set(['swing', 'forehand']);
  // the hand each gesture uses (S: its side, O: the other); a hand that holds something keeps its grip
  const SHAPES = { wave: { S: 'palm' }, present: { S: 'palm' }, point: { S: 'point' }, shrug: { S: 'palm', O: 'palm' },
    cheer: { S: 'fist', O: 'fist' }, think: { S: 'fist' }, me: { S: 'palm' }, swing: { S: 'grip' }, forehand: { S: 'grip' } };
  SK.PUPPET_SHAPES = SHAPES;
  function handShapes(plan, t) {
    const out = {}, HF = 0.08;  // a hand changes shape in a short dissolve, while it moves
    for (const s of ['r', 'l']) {
      const rest = ((plan.hold || {})[s] || {}).shape || 'open';
      if (rest === 'grip') { out[s] = { shape: 'grip' }; continue; }
      const ch = [];
      for (const a of plan.acts || []) {
        const o = a[2] || {}, side = o.side || 'l', sh = SHAPES[a[1]];
        if (!sh) continue;
        const r = RAMP[a[1]] || [0.45, 0.5], rin = o.in ?? r[0], rout = o.out ?? r[1], dur = o.dur ?? 2;
        for (const [k, shape] of Object.entries(sh)) {
          if (o.one && k === 'O') continue;
          if ((k === 'S' ? side : (side === 'r' ? 'l' : 'r')) !== s) continue;
          ch.push([a[0] + 0.3 * rin, shape], [a[0] + dur + 0.6 * rout, rest]);
        }
      }
      ch.sort((x, y) => x[0] - y[0]);
      let shape = rest, prev = null, since = 99;
      for (const [tc, sh] of ch) if (tc <= t) { prev = shape; shape = sh; since = t - tc; }
      out[s] = since < HF ? { shape, prev, mix: smooth(since / HF) } : { shape };
    }
    return out;
  }
  SK.PUPPET_GESTURES = GESTURES;
  SK.puppetKeyed = keyed;

  // the rest a figure stands in: arms down by its sides, not the A-pose it was drawn in
  const STAND = { arm_r_up: -11, arm_l_up: -11, arm_r_lo: -5, arm_l_lo: -5, hand_r: -3, hand_l: -3 };

  function ik2(R, s, target, bend) {
    // two-bone IK in rest space for an arm: canvas degrees for arm_s_up and arm_s_lo
    const B = R.P.bones, S = B['arm_' + s + '_up'].pivot, E = B['arm_' + s + '_lo'].pivot, W = B['hand_' + s].pivot;
    const L1 = Math.hypot(E[0] - S[0], E[1] - S[1]), L2 = Math.hypot(W[0] - E[0], W[1] - E[1]);
    let dx = target[0] - S[0], dy = target[1] - S[1], d = Math.hypot(dx, dy);
    d = Math.max(Math.abs(L1 - L2) + 1, Math.min(L1 + L2 - 1, d));
    const a1 = Math.acos((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)) / D2R;
    const base = ang([dx, dy]);
    const up = base + bend * a1;
    const Ew = [S[0] + L1 * Math.cos(up * D2R), S[1] + L1 * Math.sin(up * D2R)];
    const lo = ang([target[0] - Ew[0], target[1] - Ew[1]]);
    const rUp = wrap(up - ang([E[0] - S[0], E[1] - S[1]]));
    const rLo = wrap(lo - ang([W[0] - E[0], W[1] - E[1]]) - rUp);
    return { up: rUp, lo: rLo };
  }

  function legTarget(R, s, M, target) {  // a target in the root's frame, in the pelvis' own
    const w = ap(M[R.idx.root], target[0], target[1]);
    return ap(inv(M[R.idx.pelvis]), w[0], w[1]);
  }
  function legIK(R, s, M, target, bend, sy = 1) {
    // the ankle to a target (root frame) under the pelvis as M places it: canvas degrees for the
    // leg's bones. bend +1 puts the knee to the left of the picture, -1 to the right; sy < 1 is a
    // leg shortened by that much (a knee coming towards us), solved for in the unshortened leg
    const B = R.P.bones, Hp = B['leg_' + s + '_up'].pivot, K = B['leg_' + s + '_lo'].pivot, A = B['foot_' + s].pivot;
    const t0 = legTarget(R, s, M, target), tgt = [t0[0], Hp[1] + (t0[1] - Hp[1]) / sy];
    const L1 = Math.hypot(K[0] - Hp[0], K[1] - Hp[1]), L2 = Math.hypot(A[0] - K[0], A[1] - K[1]);
    let dx = tgt[0] - Hp[0], dy = tgt[1] - Hp[1], d = Math.hypot(dx, dy);
    d = Math.max(Math.abs(L1 - L2) + 1, Math.min(L1 + L2 - 0.5, d));
    const a1 = Math.acos(Math.min(1, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d))) / D2R;
    const dr = Math.hypot(A[0] - Hp[0], A[1] - Hp[1]);
    const restA1 = Math.acos(Math.min(1, (L1 * L1 + dr * dr - L2 * L2) / (2 * L1 * dr))) / D2R;
    const base = ang([dx, dy]), restBase = ang([A[0] - Hp[0], A[1] - Hp[1]]);
    const rUp = wrap((base + bend * a1) - (restBase + bend * restA1));
    const c = Math.cos(rUp * D2R), sn = Math.sin(rUp * D2R), kx = K[0] - Hp[0], ky = K[1] - Hp[1];
    const Kn = [Hp[0] + c * kx - sn * ky, Hp[1] + sn * kx + c * ky];
    const rLo = wrap(ang([tgt[0] - Kn[0], tgt[1] - Kn[1]]) - ang([A[0] - K[0], A[1] - K[1]]) - rUp);
    return { up: rUp, lo: rLo };
  }

  // the feet: steps [[t, foot, dx, dur]] move a foot dx figure heights along the ground (+ to the
  // right of the picture) in an arc; SK.puppetWalk makes a list of them
  function feetAt(plan, t) {
    const off = { r: 0, l: 0 }, lift = { r: 0, l: 0 };
    for (const [t0, f, dx, dur = 0.36] of plan.steps || []) {
      if (t < t0) continue;
      const u = Math.min(1, (t - t0) / dur);
      off[f] += dx * smooth(u);
      if (u < 1) lift[f] = Math.max(lift[f], Math.sin(Math.PI * u));
    }
    return { off, lift };
  }
  // n steps that carry the figure dx figure heights, from t0, the lead foot first: the last brings
  // the feet together again
  SK.puppetWalk = function (t0, dx, n = 2, o = {}) {
    const dur = o.dur ?? 0.36, gap = o.gap ?? dur + 0.04;
    let f = o.lead || (dx > 0 ? 'l' : 'r');
    const at = { r: 0, l: 0 }, out = [];
    for (let k = 0; k < n; k++) {
      const to = dx * Math.min(1, (k + 1) / Math.max(1, n - 1));
      out.push([t0 + k * gap, f, to - at[f], dur]);
      at[f] = to;
      f = f === 'r' ? 'l' : 'r';
    }
    return out;
  };

  // views: the same actor drawn turned. SK.PUPPETS['<name>@<view>'] is another drawing of it (its
  // puppet.json's facing says which way it looks); a plan's views [[t, view], ...] say which it is
  // in from t ('front' is the name alone). A turn is a swap, as in cut-out animation, with the
  // body narrowing through it so the eye reads a turn rather than a cut
  const TURN = 0.1;
  function viewAt(name, plan, t) {
    let v = null, near = 99;
    for (const [tv, vn] of plan.views || []) { if (tv <= t) v = vn; near = Math.min(near, Math.abs(t - tv)); }
    const full = !v || v === 'front' ? name : name + '@' + v;
    if (!SK.PUPPETS[full]) throw new Error('SK.puppet: no view ' + JSON.stringify(full) + ' (puppets: ' + Object.keys(SK.PUPPETS).join(', ') + ')');
    return { name: full, turn: near < TURN ? 1 - near / TURN : 0 };
  }

  // how long a gesture takes to arrive and to leave: a bigger move takes longer (an arm thrown up
  // in 0.38 s was too fast for the eye to follow: measured, motion.py's pops at every big gesture)
  const RAMP = { swing: [0.12, 0.55], wave: [0.55, 0.42], present: [0.45, 0.45], point: [0.42, 0.42], shrug: [0.4, 0.42],
    think: [0.6, 0.45], cheer: [0.62, 0.45], nod: [0.12, 0.2], lean_in: [0.5, 0.5], forehand: [0.1, 0.5],
    hop: [0.04, 0.08], sag: [0.45, 0.5], ready: [0.35, 0.4], me: [0.45, 0.4] };
  // how far through a ramp in or out t is (0..1), or -1 outside both: an arm travelling bends at
  // the elbow and straightens again, so a big move goes in an arc (coming down from a cheer with
  // straight arms passed through a T, as a review said)
  function rampPhase(t, a) {
    const t0 = a[0], o = a[2] || {}, dur = o.dur ?? 2, r = RAMP[a[1]] || [0.45, 0.5];
    const rin = o.in ?? r[0], rout = o.out ?? r[1];
    if (t >= t0 && t < t0 + rin) return (t - t0) / rin;
    if (t > t0 + dur && t < t0 + dur + rout) return (t - t0 - dur) / rout;
    return -1;
  }
  function env(t, a) {
    const t0 = a[0], o = a[2] || {}, dur = o.dur ?? 2, r = RAMP[a[1]] || [0.45, 0.5];
    const rin = o.in ?? r[0], rout = o.out ?? r[1];
    if (t < t0 || t > t0 + dur + rout) return 0;
    if (t < t0 + rin) return (o.snap === false ? smooth : arrive)((t - t0) / rin);
    if (t <= t0 + dur) return 1;
    return 1 - smooth((t - t0 - dur) / rout);
  }

  function noise(seed, t) { return Math.sin(t * 1.3 + seed) * 0.5 + Math.sin(t * 2.7 + seed * 2.1) * 0.3 + Math.sin(t * 0.61 + seed * 3.7) * 0.2; }

  // the plan's pose at t, in canvas degrees per bone (before the lags)
  function rawPose(R, plan, t) {
    const out = {};
    const set = (b, v) => { out[b] = v; };
    Object.entries(STAND).forEach(([b, v]) => set(b, SIGN[b.includes('_r_') || b.endsWith('_r') ? 'r' : 'l'] * v));
    const extra = { head: 0, lean: 0, raise: 0, bounce: 0, twist: 0, shift: 0, sink: 0, prop_back: 0, hop: 0, tuck: 0, squash: 0, sag: 0, stance: 0 };
    const hold = plan.hold || {};
    for (const s of ['r', 'l']) if (hold[s]) Object.entries(hold[s]).forEach(([b, v]) => { if (typeof v === 'number') set(b.replace('S', s), SIGN[s] * v); });
    for (const a of plan.acts || []) {
      const e = env(t, a); if (e <= 0) continue;
      const G = GESTURES[a[1]]; if (!G) continue;
      const o = a[2] || {}, s = o.side || 'l', os = s === 'r' ? 'l' : 'r';
      const lt = Math.max(0, t - a[0]);
      const g = G(lt, o);
      for (const [k, v] of Object.entries(g)) {
        if (o.one && k.includes('_O')) continue;  // one-handed: the other hand is busy (holding something)
        if (k in extra) { extra[k] += e * v; continue; }
        if (k === 'ik_S') {
          const P = R.P, H = P.figure.height, sd = s === 'r' ? -1 : 1;
          const tg = v === 'chin' ? [P.chin[0] + sd * (o.tx ?? 0.05) * H, P.chin[1] + (o.ty ?? 0.075) * H]
            : v === 'chest' ? [P.chin[0] + sd * (o.tx ?? 0.02) * H, P.chin[1] + (o.ty ?? 0.12) * H] : v;
          const q = ik2(R, s, tg, s === 'r' ? 1 : -1);  // the elbow down, under the hand
          out['arm_' + s + '_up'] = out['arm_' + s + '_up'] + e * (q.up - out['arm_' + s + '_up']);
          out['arm_' + s + '_lo'] = out['arm_' + s + '_lo'] + e * (q.lo - out['arm_' + s + '_lo']);
          continue;
        }
        const b = k.replace('_S', '_' + s).replace('_O', '_' + os);
        const side = b.includes('_r') ? 'r' : 'l';
        const drift = (o.drift ?? 2.5) * noise(b.length * 1.7 + a[0], lt * 0.9);
        // fwd: the arm reaches the other way -- in a turned view, "out" for the near arm is behind
        const cv = SIGN[side] * ((o.fwd && /^(arm|hand)_/.test(b) ? -v : v) + drift);
        out[b] = (out[b] ?? 0) + e * (cv - (out[b] ?? 0));
      }
      const ph = rampPhase(t, a);  // the arc: the elbow folds while the arm travels
      if (ph >= 0 && !KEYED.has(a[1])) {
        for (const [k, v] of Object.entries(g)) {
          if (!/^arm_[SO]_up$/.test(k) || (o.one && k.includes('_O'))) continue;
          const sd = k.includes('_S') ? s : os, travel = Math.abs(v - (STAND['arm_' + sd + '_up'] / 1));
          out['arm_' + sd + '_lo'] += SIGN[sd] * Math.min(45, 0.4 * travel) * Math.sin(Math.PI * ph);
        }
      }
    }
    return { q: out, extra };
  }

  const LAG = { arm_r_lo: 0.05, arm_l_lo: 0.05, hand_r: 0.1, hand_l: 0.1, head: 0.06 };

  SK.puppetAct = function (name, plan, t) {
    const view = viewAt(name, plan, t);
    const R = prep(view.name), P = R.P, H = P.figure.height, facing = P.facing || 0;
    const now = rawPose(R, plan, t);
    const q = {};
    for (const b of Object.keys(now.q)) {
      const lag = LAG[b] || 0;
      const v = lag ? rawPose(R, plan, t - lag).q[b] : now.q[b];
      q[b] = { r: v };
    }
    const ex = now.extra, idle = plan.idle ?? 1;
    // idle: breath, a slow weight shift with the feet planted, the head's own small life
    const seed = (name.charCodeAt(0) || 1) * 0.37;
    const br = Math.sin(t * 2 * Math.PI / 3.6 + seed);
    const shift = Math.sin(t * 2 * Math.PI / 6.4 + seed * 2);
    const vt2 = talk(plan.who || name, t - 0.09);
    const beat = (vt2.open || 0) * 1.0;
    // the body: the feet where the steps put them, the pelvis over them; a hop lifts the lot
    const ft = feetAt(plan, t), mid = (ft.off.r + ft.off.l) / 2, lifted = Math.max(ft.lift.r, ft.lift.l);
    const sink = ex.sink + 0.5 * ex.sag;
    q.root = { dy: -ex.hop * 0.12 * H, sx: (1 + 0.05 * ex.squash) * (1 - 0.1 * view.turn), sy: 1 - 0.07 * ex.squash };
    q.pelvis = {
      r: idle * 0.5 * shift,
      dx: idle * 0.010 * H * shift + mid * H + ex.shift * 0.022 * H * (facing || 1),
      dy: idle * 0.004 * H * Math.abs(shift) - ex.bounce * 0.012 * H * Math.abs(Math.sin(t * 9)) + sink * 0.018 * H - 0.012 * H * lifted,
    };
    q.chest = { r: idle * (-0.9 * shift + 0.4 * noise(seed, t * 0.5)) + ex.lean, sy: (1 + idle * 0.013 * br) * (1 - 0.03 * ex.sag), sx: (1 + idle * 0.004 * br) * (1 - 0.07 * Math.abs(ex.twist)) };
    q.head = { r: (q.head ? q.head.r : 0) + idle * (1.0 * noise(seed + 5, t * 0.4) + 0.4 * shift) + ex.head + 2.2 * beat * Math.sin(t * 7.3), dy: -0.004 * H * beat + 0.012 * H * ex.sag };
    const free = plan.free || 'l';  // the hand that talks along (the other may hold something)
    let busy = 0;
    for (const a of plan.acts || []) if ((a[2] || {}).side === free || !(a[2] || {}).side) busy = Math.max(busy, a[1] === 'nod' || a[1] === 'hop' ? 0 : env(t, a));
    const talking = Math.max(0, vt2.open - 0.2);
    if (q['arm_' + free + '_lo']) q['arm_' + free + '_lo'].r += SIGN[free] * (1 - busy) * (plan.beats ?? 1) * 14 * talking;
    if (q['hand_' + free]) q['hand_' + free].r += SIGN[free] * (1 - busy) * (plan.beats ?? 1) * 8 * talking;
    for (const s of ['r', 'l']) {
      const b = 'arm_' + s + '_up';
      q[b] = q[b] || { r: 0 };
      q[b].dy = -ex.raise + 0.014 * H * ex.sag - idle * 0.0025 * H * br;
      q[b].r += idle * SIGN[s] * 0.8 * noise(seed + (s === 'r' ? 9 : 13), t * 0.6);
    }
    // the legs reach for the feet: knees out when it faces us, forward when it is turned
    const M = matrices(R, { root: q.root, pelvis: q.pelvis });
    const B = P.bones;
    for (const s of ['r', 'l']) {
      const A = B['foot_' + s].pivot, out = (s === 'r' ? -1 : 1) * ex.stance * 0.03 * H;
      const lift = 0.045 * H * ft.lift[s] + 0.07 * H * ex.tuck;
      const tg = [A[0] + ft.off[s] * H + out, A[1] - lift];
      // facing us, a bent knee comes towards the camera: most of the bend shows as a shorter leg,
      // the rest as the knee going out (a crouch drawn with the knees out alone read as bow legs)
      let sy = 1;
      if (!facing) {
        const Hp = B['leg_' + s + '_up'].pivot, pt = legTarget(R, s, M, tg);
        const d = Math.hypot(pt[0] - Hp[0], pt[1] - Hp[1]), d0 = Math.hypot(A[0] - Hp[0], A[1] - Hp[1]);
        sy = Math.min(1, 1 - 0.7 * (1 - d / d0));
      }
      const lg = legIK(R, s, M, tg, facing ? -facing : (s === 'r' ? 1 : -1), sy);
      q['leg_' + s + '_up'] = { r: lg.up, sy };
      q['leg_' + s + '_lo'] = { r: lg.lo };
      // the foot stays level with the ground and its own size; a lifted one points its toe down
      q['foot_' + s] = { r: -(q.pelvis.r + lg.up + lg.lo) + 16 * facing * Math.max(ft.lift[s], 0.6 * ex.tuck), sy: 1 / sy };
    }
    // the face: the last one asked for; a change happens behind a blink
    let face = 'neutral', prev = null, since = 99;
    for (const f of plan.faces || []) if (f[0] <= t) { prev = face; face = f[1]; since = t - f[0]; }
    const FADE = 0.12;  // an expression dissolves into the next: a swap read as a jump (motion.py)
    return { view: view.name, pose: q, face, prevFace: since < FADE ? prev : null, faceMix: since < FADE ? smooth(since / FADE) : 1, blinkNow: since < 0.1 && since > 0.0, hands: handShapes(plan, t), propsBack: ex.prop_back > 0.5 };
  };

  // where its parts are at t, on the page, without drawing it: {hand_r, hand_l, head, feet, props:
  // {name: centre}} -- a ball leaves the paddle from here
  SK.puppetAt = function (name, x, y, h, plan, t, o = {}) {
    const a = SK.puppetAct(name, plan, t), R = prep(a.view), P = R.P, M = matrices(R, a.pose);
    const k = h / P.figure.height, f = P.figure.feet, sx = o.flip ? -1 : 1;
    const page = (m, px, py) => { const q = ap(m, px, py); return [x + sx * k * (q[0] - f[0]), y + k * (q[1] - f[1])]; };
    const B = P.bones, tip = (b) => page(M[R.idx[b]], B[b].end[0], B[b].end[1]);
    const out = {
      view: a.view, hand_r: tip('hand_r'), hand_l: tip('hand_l'),
      head: page(M[R.idx.head], B.head.pivot[0], B.head.pivot[1] - 0.12 * P.figure.height),
      feet: page(M[R.idx.root], f[0] + 0, f[1]), foot_r: tip('foot_r'), foot_l: tip('foot_l'), props: {},
    };
    for (const [pn, pr] of Object.entries(P.props || {})) {
      const local = mul(about(pr.at[0], pr.at[1], pr.angle, 1, 1, 0, 0), [1, 0, 0, 1, pr.at[0] - pr.grip[0], pr.at[1] - pr.grip[1]]);
      const m = mul(M[R.idx[pr.bone]], local);
      out.props[pn] = page(m, pr.w / 2, pr.h * 0.3);  // the middle of its head
    }
    return out;
  };

  SK.puppetPlay = function (name, x, y, h, plan, o = {}) {
    const t = o.t ?? SK.T;
    const a = SK.puppetAct(name, plan, t);
    return SK.puppet(a.view, x, y, h, Object.assign({ pose: a.pose, face: a.face, prevFace: a.prevFace, faceMix: a.faceMix, blinkNow: a.blinkNow, hands: a.hands, propsBack: a.propsBack, who: plan.who || name }, o));
  };
})();
