/* sketch/bench.js -- benchmark films: a measured race replayed from its own timestamps.

   A module a film opts into ("modules": ["bench"]). It reads what scripts/llm-race.py writes
   (race.json: per model and task the median run's stream, every piece with the second it
   arrived) and draws the furniture every benchmark film needs, in one house look: a dark
   instrument panel, condensed headline type, tabular mono numbers. Every piece is a pure
   function of t, in SCREEN pixels (the film keeps its camera on [W/2, H/2, 1]).

   Data
     SK.bench.replay(lane)            a race.json lane's replay -> {at(rt): {phase, think, out,
                                      text, tokS}, done, first, tokens, think}; phase is 'wait' |
                                      'think' | 'write' | 'done'. Thinking tokens are spread over
                                      the thinking time by the thinking text's own pace where the
                                      model streams it, else evenly; the answer's by its characters.
                                      Both end on the measured totals.
     SK.bench.timeMap(keys)           [[filmT, raceT], ...] -> {race(t), rate(t)}: a race clock that
                                      runs at 1x, then faster (a time-lapse), eased at each change
   Look
     SK.bench.C, SK.bench.F           colours and faces; a film may Object.assign over them
     SK.bench.ground(t, o)            the panel: flat dark, a dot grid that drifts, a scan line
     SK.bench.text(s, x, y, o)        crisp text -> width. o: size, w (weight), f ('head'|'mono'|
                                      'body'), col, align, base, ls (tracking px), alpha, maxW, skew
     SK.bench.box(x, y, w, h, o)      a filled / stroked rectangle (o.fill, o.stroke, o.lw, o.r)
     SK.bench.stamp(s, x, y, t, t0, o)    a label that slams in at t0 (o: col, ink, size, rot, pad)
     SK.bench.chip(s, x, y, o)        a small filled tag -> width
     SK.bench.num(v, o)               thousands-separated, o.dec decimals
     SK.bench.secs(v)                 "7.7 s" under a minute, "5:16" over
     SK.bench.roll(v0, v1, t, t0, d)  a counted value (eased) between v0 and v1
     SK.bench.lane(x, y, w, h, o)     one racer: name, sub-line, the stream window (thinking counter
                                      or the answer's last lines), a live clock, its status; o.rp a
                                      replay, o.rt the race time, o.col, o.label, o.sub, o.rank,
                                      o.rankCol, o.textLines, o.fade
     SK.bench.wipe(t, t0, d)          0..1 for a reveal; SK.bench.clip(x, y, w, h, fn) clips
*/
(function () {
  'use strict';
  const SK = window.SK;
  const B = (SK.bench = {});
  const clamp = SK.clamp, lerp = SK.lerp, E = SK.E;
  const ctx = () => SK.ctx();

  B.C = {
    bg: '#0b0c0f', panel: '#14161b', panel2: '#1b1e25', line: '#2a2e36', grid: 'rgba(255,255,255,.055)',
    text: '#f3f1ea', soft: '#9aa0aa', dim: '#585e69', accent: '#c6ff3d', think: '#ffb224',
    pass: '#3ddc84', fail: '#ff5a45', best: '#b98bff', paper: '#f4f1e8', ink: '#16171a',
  };
  B.F = { head: '"Sofia Sans Condensed"', mono: '"IBM Plex Mono"', body: '"Inter"' };

  /* ------------------------------------------------------------ numbers */
  B.num = function (v, o = {}) {
    if (v === null || v === undefined || Number.isNaN(v)) return '-';
    const d = o.dec ?? 0;
    const s = Math.abs(v).toFixed(d).split('.');
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (v < 0 ? '-' : '') + s.join('.');
  };
  B.secs = function (v, o = {}) {
    if (v === null || v === undefined) return '-';
    if (v < 60) return v.toFixed(o.dec ?? 1) + (o.unit === false ? '' : ' s');
    const dd = o.minDec ?? 0, r = +v.toFixed(dd); // round first, or 299.8 s prints as 4:60
    const m = Math.floor(r / 60), s = r - m * 60;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(dd);
  };
  B.roll = (v0, v1, t, t0, d = .8, e = E.out) => lerp(v0, v1, e(clamp((t - t0) / d)));

  /* ------------------------------------------------------------ the race clock */
  B.timeMap = function (keys) {
    // piecewise linear film->race, with each corner rounded over `ease` film seconds so the clock
    // speeds up rather than jumping (rate is the slope; race(t) its integral, computed exactly)
    const K = keys.map(k => ({ t: k[0], r: k[1] }));
    const seg = [];
    for (let i = 1; i < K.length; i++) seg.push({ t0: K[i - 1].t, t1: K[i].t, r0: K[i - 1].r, rate: (K[i].r - K[i - 1].r) / (K[i].t - K[i - 1].t) });
    const raw = (t) => {
      if (t <= K[0].t) return K[0].r;
      for (const s of seg) if (t <= s.t1) return s.r0 + (t - s.t0) * s.rate;
      const s = seg[seg.length - 1]; return s.r0 + (s.t1 - s.t0) * s.rate;
    };
    const rate = (t) => {
      if (t <= K[0].t) return 0;
      for (const s of seg) if (t <= s.t1) return s.rate;
      return 0;
    };
    // smooth by averaging the raw clock over a short window (exact for linear stretches)
    const w = .35, N = 8;
    const race = (t) => { let a = 0; for (let i = 0; i < N; i++) a += raw(t - w / 2 + w * (i + .5) / N); return a / N; };
    const rateS = (t) => { let a = 0; for (let i = 0; i < N; i++) a += rate(t - w / 2 + w * (i + .5) / N); return a / N; };
    return { race, rate: rateS, raw };
  };

  /* ------------------------------------------------------------ a replay */
  B.replay = function (lane) {
    const rp = lane.replay || lane;
    const S = rp.stream || [];
    const done = rp.t_done, first = rp.t_first_answer ?? rp.t_first_token ?? 0;
    const total = rp.completion_tokens ?? rp.predicted_n ?? S.reduce((a, e) => a + (e[1] === 'c' ? 1 : 0), 0);
    const thinkTot = rp.reasoning_tokens ?? 0, outTot = Math.max(0, total - thinkTot);
    // thinking: from the first sign of life to the first answer piece
    const rEv = S.filter(e => e[1] === 'r');
    const t0r = rEv.length ? Math.min(rEv[0][0], first) : Math.min(.35, first);
    const t1r = first;
    const rChars = rEv.reduce((a, e) => a + e[3], 0);
    const rCum = []; { let a = 0; for (const e of rEv) { a += e[3]; rCum.push([e[0], a / (rChars || 1)]); } }
    const thinkFrac = (rt) => {
      if (rt <= t0r) return 0;
      if (rt >= t1r) return 1;
      if (rCum.length > 3) { // the model's own pace, blended with even so a summary's bursts do not jump
        let f = 0; for (const [tt, ff] of rCum) { if (tt <= rt) f = ff; else break; }
        return clamp(.5 * f + .5 * (rt - t0r) / (t1r - t0r));
      }
      return (rt - t0r) / (t1r - t0r);
    };
    // the answer: cumulative text by time
    const cEv = S.filter(e => e[1] === 'c');
    const cChars = cEv.reduce((a, e) => a + e[2].length, 0);
    const cum = []; { let a = 0, txt = ''; for (const e of cEv) { a += e[2].length; txt += e[2]; cum.push([e[0], a, txt]); } }
    const textAt = (rt) => {
      let lo = 0, hi = cum.length - 1, k = -1;
      while (lo <= hi) { const mid = (lo + hi) >> 1; if (cum[mid][0] <= rt) { k = mid; lo = mid + 1; } else hi = mid - 1; }
      return k < 0 ? ['', 0] : [cum[k][2], cum[k][1]];
    };
    const at = (rt) => {
      const [text, n] = textAt(rt);
      const tf = thinkFrac(rt);
      const think = Math.round(thinkTot * tf);
      const out = Math.round(outTot * (cChars ? n / cChars : 0));
      const phase = rt >= done ? 'done' : rt >= first ? 'write' : rt >= t0r ? 'think' : 'wait';
      return { phase, think, out, tokens: think + out, text, tf };
    };
    return { at, done, first, t0r, total, thinkTot, outTot, rp };
  };

  /* ------------------------------------------------------------ look */
  B.font = (o) => `${o.italic ? 'italic ' : ''}${o.w ?? 700} ${o.size ?? 32}px ${B.F[o.f ?? 'head'] || o.f}`;
  B.textW = function (s, o = {}) { const c = ctx(); c.save(); c.font = B.font(o); if (o.ls) c.letterSpacing = o.ls + 'px'; const w = c.measureText(s).width; c.restore(); return w; };
  B.text = function (s, x, y, o = {}) {
    const c = ctx(); s = String(s);
    const a = o.alpha ?? 1; if (a <= 0) return 0;
    c.save();
    c.globalAlpha *= a;
    let size = o.size ?? 32;
    c.font = B.font({ ...o, size });
    if (o.ls) c.letterSpacing = o.ls + 'px';
    let w = c.measureText(s).width;
    if (o.maxW && w > o.maxW) { size *= o.maxW / w; c.font = B.font({ ...o, size }); w = c.measureText(s).width; }
    c.textAlign = o.align ?? 'left';
    c.textBaseline = o.base ?? 'alphabetic';
    c.fillStyle = o.col ?? B.C.text;
    if (o.skew) { c.translate(x, y); c.transform(1, 0, -o.skew, 1, 0, 0); x = 0; y = 0; }
    if (o.stroke) { c.lineWidth = o.stroke; c.strokeStyle = o.strokeCol ?? B.C.bg; c.lineJoin = 'round'; c.strokeText(s, x, y); }
    c.fillText(s, x, y);
    c.restore();
    return w;
  };
  B.box = function (x, y, w, h, o = {}) {
    const c = ctx(); const a = o.alpha ?? 1; if (a <= 0 || w <= 0 || h <= 0) return;
    c.save(); c.globalAlpha *= a;
    c.beginPath();
    if (o.r) c.roundRect(x, y, w, h, o.r); else c.rect(x, y, w, h);
    if (o.fill) { c.fillStyle = o.fill; c.fill(); }
    if (o.stroke) { c.strokeStyle = o.stroke; c.lineWidth = o.lw ?? 2; c.stroke(); }
    c.restore();
  };
  B.line = function (x0, y0, x1, y1, o = {}) {
    const c = ctx(); c.save(); c.globalAlpha *= o.alpha ?? 1; c.strokeStyle = o.col ?? B.C.line; c.lineWidth = o.lw ?? 2;
    if (o.dash) c.setLineDash(o.dash);
    c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke(); c.restore();
  };
  B.clip = function (x, y, w, h, fn) { const c = ctx(); c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); try { fn(); } finally { c.restore(); } };
  B.wipe = (t, t0, d = .5, e = E.inOut) => e(clamp((t - t0) / d));

  B.ground = function (t, o = {}) {
    const c = ctx(), W = SK.W, H = SK.H;
    c.save();
    c.fillStyle = o.bg ?? B.C.bg; c.fillRect(0, 0, W, H);
    // dot grid, drifting slowly: the panel is never quite still
    const st = o.step ?? 32, ox = (t * (o.drift ?? 6)) % st, oy = (t * (o.drift ?? 6) * .5) % st;
    c.fillStyle = o.grid ?? B.C.grid;
    for (let y = -st + oy; y < H + st; y += st) for (let x = -st + ox; x < W + st; x += st) c.fillRect(x, y, 2, 2);
    // a faint horizontal scan band travelling down
    if (o.scan !== false) {
      const sy = ((t * 120) % (H + 400)) - 200;
      const g = c.createLinearGradient(0, sy - 160, 0, sy + 160);
      g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(.5, 'rgba(255,255,255,.025)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      c.fillStyle = g; c.fillRect(0, sy - 160, W, 320);
    }
    c.restore();
  };

  /** a label that slams in: big and faint to its size with a small overshoot, then holds */
  B.stamp = function (s, x, y, t, t0, o = {}) {
    if (t < t0) return;
    let k, a;
    if (o.ghost) { // the reference's ink hit: one faint frame a touch large, then it is down
      const f = 1 / (SK.FPS || 60);
      k = t - t0 < f ? 1.06 : 1; a = (t - t0 < f ? .3 : 1) * (o.alpha ?? 1);
    } else {
      const u = clamp((t - t0) / (o.d ?? .22));
      k = u < 1 ? lerp(1.9, 1, E.out(u)) - Math.sin(u * Math.PI) * .06 : 1;
      a = Math.min(1, u * 3) * (o.alpha ?? 1);
    }
    const size = o.size ?? 34, pad = o.pad ?? size * .38;
    const w = B.textW(s, { size, w: o.w ?? 800, f: o.f ?? 'head', ls: o.ls ?? 1 }) + pad * 2, h = size * 1.12 + pad * .5;
    const c = ctx(); c.save(); c.translate(x, y); c.rotate((o.rot ?? -2) * Math.PI / 180); c.scale(k, k); c.globalAlpha *= a;
    const ax = o.align === 'left' ? 0 : o.align === 'right' ? -w : -w / 2;
    if (o.outline) B.box(ax, -h / 2, w, h, { stroke: o.col ?? B.C.accent, lw: 4 });
    else B.box(ax, -h / 2, w, h, { fill: o.col ?? B.C.accent });
    B.text(s, ax + pad, size * .36, { size, w: o.w ?? 800, f: o.f ?? 'head', col: o.outline ? (o.col ?? B.C.accent) : (o.ink ?? B.C.ink), ls: o.ls ?? 1 });
    c.restore();
  };
  B.chip = function (s, x, y, o = {}) {
    const size = o.size ?? 18, pad = o.pad ?? 9;
    const w = B.textW(s, { size, w: o.w ?? 700, f: o.f ?? 'mono', ls: o.ls ?? 1 }) + pad * 2, h = size + pad * 1.1;
    const ax = o.align === 'right' ? x - w : x;
    B.box(ax, y - h / 2, w, h, { fill: o.fill ?? B.C.panel2, stroke: o.stroke, lw: o.lw ?? 2, alpha: o.alpha });
    B.text(s, ax + pad, y + size * .36, { size, w: o.w ?? 700, f: o.f ?? 'mono', col: o.col ?? B.C.text, ls: o.ls ?? 1, alpha: o.alpha });
    return w;
  };

  /** wrap mono text to n columns and keep the last `lines` lines */
  B.tail = function (text, cols, lines) {
    const out = [];
    for (const raw of String(text).replace(/\t/g, '  ').split('\n')) {
      let s = raw;
      if (!s.length) { out.push(''); continue; }
      while (s.length > cols) { out.push(s.slice(0, cols)); s = s.slice(cols); }
      out.push(s);
    }
    while (out.length && out[out.length - 1] === '') out.pop();
    return out.slice(-lines);
  };

  /** a tick step that gives about n ticks over 0..max seconds */
  B.tickStep = function (max, n = 6) {
    const steps = [.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200];
    for (const s of steps) if (max / s <= n) return s;
    return steps[steps.length - 1];
  };
  /** the round's shared time axis: ticks and labels over x..x+w for 0..max seconds */
  B.axis = function (x, y, w, max, o = {}) {
    const st = B.tickStep(max, o.n ?? 6);
    B.line(x, y, x + w, y, { col: C().line, lw: 2, alpha: o.alpha });
    for (let v = 0; v <= max + 1e-6; v += st) {
      const xx = x + w * v / max;
      B.line(xx, y - 8, xx, y, { col: C().soft, lw: 2, alpha: o.alpha });
      if (o.grid !== false) B.line(xx, y + 6, xx, y + (o.gridH ?? 0), { col: 'rgba(255,255,255,.06)', lw: 1, alpha: o.alpha });
      B.text(B.secs(v, { dec: st < 1 ? 1 : 0 }), xx, y - 16, { size: 17, w: 600, f: 'mono', col: C().soft, align: 'center', alpha: o.alpha });
    }
  };
  const C = () => B.C;

  /** one racer: its name, a bar growing along the shared time axis (amber while it thinks, its
      colour while it writes), the newest line of its answer under the bar, and a live clock */
  B.lane = function (x, y, w, h, o) {
    const rp = o.rp, rt = o.rt, st = rp.at(rt), col = o.col ?? B.C.accent;
    const fade = o.fade ?? 1, isDone = st.phase === 'done';
    const nameW = o.nameW ?? 440, clockW = o.clockW ?? 250;
    const tx = x + nameW, tw = w - nameW - clockW, max = o.axisMax;
    B.box(x, y, w, h, { fill: B.C.panel, alpha: fade });
    B.box(x, y, 8, h, { fill: col, alpha: fade });
    B.text(o.label, x + 34, y + 58, { size: o.nameSize ?? 46, w: 800, col: B.C.text, alpha: fade, maxW: nameW - 60, ls: .5 });
    if (o.sub) B.text(o.sub, x + 36, y + 92, { size: 16, w: 500, f: 'mono', col: B.C.soft, alpha: fade, maxW: nameW - 60 });
    // the track
    const by = y + 24, bh = 44, X = (v) => tx + tw * Math.min(v, max) / max;
    B.box(tx, by, tw, bh, { fill: '#0f1115', alpha: fade });
    const now = Math.min(rt, rp.done);
    if (now > 0) {
      const thinkEnd = Math.min(now, rp.first);
      if (rp.thinkTot > 0 || rp.first > .3) B.box(X(0), by, X(thinkEnd) - X(0), bh, { fill: B.C.think, alpha: fade * .85 });
      if (now > rp.first) B.box(X(rp.first), by, X(now) - X(rp.first), bh, { fill: col, alpha: fade });
      if (!isDone) { // the live head
        const hx = X(now);
        B.box(hx - 2, by - 6, 4, bh + 12, { fill: '#ffffff', alpha: fade * (.6 + .4 * Math.sin(rt * 20)) });
      }
      if (isDone && o.flag !== false) { // a finish tick
        const fx = X(rp.done);
        B.box(fx - 2, by - 8, 4, bh + 16, { fill: B.C.text, alpha: fade });
      }
    }
    // under the bar: thinking count, or the newest line of the answer
    const ly = y + h - 22;
    if (st.phase === 'think' || (st.out === 0 && !isDone && st.phase !== 'wait')) {
      B.text('THINKING  ' + B.num(st.think) + ' tokens', tx, ly, { size: 20, w: 700, f: 'mono', col: B.C.think, alpha: fade });
    } else if (st.phase === 'wait') {
      B.text('waiting for the first token', tx, ly, { size: 18, w: 500, f: 'mono', col: B.C.dim, alpha: fade });
    } else {
      const cols = Math.floor((tw - 260) / 10.9);
      const L = B.tail(st.text.replace(/^```.*$/gm, '').replace(/\n+$/, ''), cols, 1); // a code fence is no line to show
      if (L.length) B.text(L[0], tx, ly, { size: 18, w: 500, f: 'mono', col: isDone ? B.C.soft : B.C.text, alpha: fade });
      if (rp.thinkTot > 0) B.text(B.num(rp.thinkTot) + ' thinking tok', tx + tw, ly, { size: 17, w: 600, f: 'mono', col: B.C.think, align: 'right', alpha: fade * .95 });
    }
    // the big number: the lane's own clock, or (o.big 'tokens') its tokens so far while it runs --
    // five copies of one race clock say nothing; five token counts pull apart at once
    const shown = Math.min(rt, rp.done);
    if (o.big === 'tokens' && !isDone) {
      B.text(B.num(st.think + st.out), x + w - 84, y + 74, { size: 58, w: 700, f: 'mono', col: st.phase === 'think' ? B.C.think : B.C.text, align: 'right', alpha: fade });
      B.text('tok', x + w - 24, y + 74, { size: 24, w: 700, f: 'mono', col: B.C.soft, align: 'right', alpha: fade });
    } else {
      const big = shown < 60 ? shown.toFixed(shown < 10 ? 2 : 1) : B.secs(shown, { minDec: 1 });
      B.text(big, x + w - 54, y + 74, { size: 58, w: 700, f: 'mono', col: isDone ? col : B.C.text, align: 'right', alpha: fade });
      if (shown < 60) B.text('s', x + w - 24, y + 74, { size: 28, w: 700, f: 'mono', col: B.C.soft, align: 'right', alpha: fade });
    }
    return { st, X, tx, tw };
  };

  /** a scan wipe across the frame at each scene change (screen space: call from the film's
      overlay): a bright line sweeping left to right with a short trail. o: col, trail, d, lead */
  B.transitions = function (t, at, o = {}) {
    const W = SK.W, H = SK.H;
    for (const b of at) {
      const u = (t - (b - (o.lead ?? .18))) / (o.d ?? .42);
      if (u < 0 || u > 1) continue;
      const x = lerp(-300, W + 300, E.inOut(u));
      const c = ctx(); c.save();
      const g = c.createLinearGradient(x - 300, 0, x, 0);
      g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, o.trail ?? 'rgba(198,255,61,.20)');
      c.fillStyle = g; c.fillRect(x - 300, 0, 300, H);
      c.fillStyle = o.col ?? B.C.accent; c.fillRect(x - 3, 0, 6, H);
      c.restore();
    }
  };
  /** camera keys for a film drawn in screen pixels: each scene pushes in slowly from 1 to `zoom`
      and cuts back at the next, so a held board is never quite still */
  B.pushKeys = function (scenes, zoom = 1.03) {
    const W = SK.W, H = SK.H, keys = [];
    for (const [a, b] of scenes) { keys.push([a, [W / 2, H / 2, 1]]); keys.push([b - .001, [W / 2, H / 2, zoom], E.sine]); }
    return keys;
  };

  /** a score for a benchmark film, from its sections: [{from, to, kind}] in film seconds, kind
      'intro' | 'drive' | 'race' | 'break' | 'build' | 'outro' | 'tail'. One minor progression a bar
      (A minor: Am F C G unless o.roots/o.prog say otherwise), a sub under everything, a pumping
      synth bass when it drives, a square arpeggio when it races, drums by section; o.hits: film
      seconds for a full-band accent (a chord stab). Returns score.json's object. */
  B.music = function (sections, o = {}) {
    const bpm = o.bpm ?? 120, beat = 60 / bpm, bar = 4 * beat;
    const ROOT = o.roots ?? ['A', 'F', 'C', 'G'];
    const PROG = o.prog ?? [['A', 'C', 'E'], ['F', 'A', 'C'], ['C', 'E', 'G'], ['G', 'B', 'D']];
    const N = { sub: [], bass: [], pad: [], arp: [], stab: [] };
    const events = [];
    const KITS = {
      intro: { kick: 'x.......x.......', hat: '..x...x...x...x.' },
      drive: { kick: 'x...x...x...x...', clap: '....x.......x...', hat: '..x...x...x...x.' },
      race: { kick: 'x...x...x...x...', clap: '....x.......x...', hat: 'xoxoxoxoxoxoxoxo' },
      break: { hat: '..o...o...o...o.', rim: '......x.......x.' },
      build: { kick: 'x...x...x...x...', snare: '............xxxx', hat: 'x.x.x.x.x.x.x.x.' },
      outro: { kick: 'x.......x.......', clap: '....x.......x...', hat: '..x...x...x...x.' },
      tail: {},
    };
    for (const sec of sections) {
      const b0 = Math.round(sec.from / bar), b1 = Math.round(sec.to / bar);
      for (let b = b0; b < b1; b++) {
        const q = b * 4, k = ((b % 4) + 4) % 4, r = ROOT[k], ch = PROG[k];
        if (sec.kind === 'tail') continue;
        N.sub.push(q + ' ' + r + '1 4 .9');
        if (['drive', 'race', 'build', 'outro'].includes(sec.kind)) {
          for (let i = 0; i < 8; i++) N.bass.push((q + i * .5) + ' ' + r + (i % 2 ? 3 : 2) + ' .42 ' + (i % 2 ? .5 : .8));
        } else for (let i = 0; i < 4; i++) N.bass.push((q + i) + ' ' + r + '2 .9 .55');
        N.pad.push(q + ' ' + ch.map(n => n + '4').join('+') + ' 4 ' + (sec.kind === 'break' ? .8 : .55));
        if (['race', 'break', 'build'].includes(sec.kind)) {
          const seq = [0, 1, 2, 1];
          for (let i = 0; i < 16; i++) N.arp.push((q + i * .25) + ' ' + ch[seq[i % 4]] + (i % 8 < 4 ? 5 : 6) + ' .2 ' + (i % 4 === 0 ? .9 : .55));
        }
      }
      const kit = KITS[sec.kind] || {};
      if (Object.keys(kit).length && b1 > b0) events.push({ type: 'drums', from: b0 * 4, bars: b1 - b0, kit, vel: sec.kind === 'break' ? .6 : .85 });
    }
    for (const t of o.hits || []) {
      const b = Math.floor(t / bar), k = ((b % 4) + 4) % 4, q = t / beat;
      N.stab.push(q + ' ' + PROG[k].map(n => n + '3').join('+') + '+' + PROG[k][0] + '4 1.5 .9');
    }
    const inst = o.inst ?? { sub: 'sub_bass', bass: 'synth_bass_2', pad: 'pad_2_warm', arp: 'lead_1_square', stab: 'synth_brass_1' };
    const vel = { sub: .55, bass: .5, pad: .32, arp: .2, stab: .38, ...(o.vel || {}) };
    for (const [part, list] of Object.entries(N)) if (list.length) events.push({ inst: inst[part], vel: vel[part], notes: list.join('; '), humanize: part !== 'arp' });
    return {
      bpm, drum_gain: o.drum_gain ?? .5, events,
      instruments: {
        synth_bass_2: { g: .30, pan: 0, send: .05, rel: .12 },
        lead_1_square: { g: .11, pan: .22, send: .38, rel: .12 },
        pad_2_warm: { g: .16, pan: 0, send: .55, rel: 1.0 },
        synth_brass_1: { g: .20, pan: -.1, send: .45, rel: .5 },
        ...(o.instruments || {}),
      },
    };
  };

  /** start lights over a race: three go red one by one, then all turn `go` and fade as the clock
      starts at tGo. o: at (the first light, default tGo - 1.4), gap (.45), col (go colour) */
  B.startLights = function (t, tGo, cx, cy, o = {}) {
    const t0 = o.at ?? tGo - 1.4, gap = o.gap ?? .45;
    if (t < t0 - .2 || t > tGo + .5) return;
    const a = B.wipe(t, t0 - .2, .2) * (1 - B.wipe(t, tGo + .15, .3));
    const c = ctx(); c.save(); c.globalAlpha *= a;
    B.box(cx - 330, cy - 85, 660, 170, { fill: 'rgba(10,11,14,.92)', r: 14 });
    for (let i = 0; i < 3; i++) {
      const on = t > t0 + i * gap, go = t >= tGo, x = cx - 200 + i * 200;
      if (on && !go && SK.glow) SK.glow(x, cy, 120, '#ff3b2f', { alpha: .45 });
      B.box(x - 56, cy - 56, 112, 112, { fill: go ? (o.col ?? B.C.pass) : on ? '#ff3b2f' : '#2a2e36', r: 56 });
    }
    c.restore();
  };
  B.startLightTimes = (tGo, o = {}) => [0, 1, 2].map(i => (o.at ?? tGo - 1.4) + i * (o.gap ?? .45));

  /** the strobe cut (screen space, from the film's overlay): at each cut the next scene shows for
      one frame, then `blank` frames of plain ground, then it settles -- a projector's flicker, ~100 ms.
      Scenes cut by it should be composed on their first frame (no fade in). o: blank (3), col */
  B.strobe = function (t, cuts, o = {}) {
    const f = 1 / (SK.FPS || 60), n = o.blank ?? 3;
    for (const c of cuts) {
      if (t >= c + f * .5 && t < c + f * (n + .5)) {
        const c2 = ctx(); c2.save(); c2.fillStyle = o.col ?? B.C.bg; c2.fillRect(0, 0, SK.W, SK.H); c2.restore();
        return true;
      }
    }
    return false;
  };
  B.strobeTimes = (cuts, o = {}) => cuts.map(c => c + 1 / (SK.FPS || 60));

  /** a marker highlight behind a number: a hand-drawn blob whose edge is redrawn 12 times a second
      (the reference's "boil"), so a held frame still lives. x, y top-left; o: col, p (0..1 swipe) */
  B.highlight = function (x, y, w, h, t, o = {}) {
    const p = o.p ?? 1; if (p <= 0) return;
    const r = SK.mulberry(((o.seed ?? 7) * 977 + Math.floor(t * 12) * 131) | 0);
    const c = ctx(); c.save(); c.globalAlpha *= o.alpha ?? 1; c.fillStyle = o.col ?? B.C.accent;
    const ww = w * p, n = 9, j = h * .09;
    c.beginPath(); c.moveTo(x + (r() - .5) * j, y + (r() - .5) * j);
    for (let i = 1; i <= n; i++) c.lineTo(x + ww * i / n + (r() - .5) * j, y + (r() - .5) * j * 1.6);
    for (let i = n; i >= 0; i--) c.lineTo(x + ww * i / n + (r() - .5) * j, y + h + (r() - .5) * j * 1.6);
    c.closePath(); c.fill(); c.restore();
  };

  /** a run's dot that starts scattered and settles onto its value (the reference's chart):
      returns the y to draw it at. y0 its final y, seed picks the scatter, u 0..1 the settle */
  B.settle = (y0, u, seed, spread = 160) => lerp(y0 + (SK.rnd(seed) - .5) * 2 * spread, y0, E.out(clamp(u)));
})();
