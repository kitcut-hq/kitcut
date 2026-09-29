/* sketch/gl3d.js -- the shared base for 3D modules (WebGL2, no libraries): camera maths, a
   studio (floor, soft shadows, an environment of dark flags, a softbox and a strip light), render
   targets and the tone curve. A module lists it before itself: "modules": ["gl3d", "drink"].

   Everything is linear light in half-float targets until the last copy, which tone-maps (mid
   tones exact, highlights rolled off) -- so a floor asked for in sRGB lands on that sRGB. The
   studio and the camera are pure functions of t; what a module simulates is its own business.
   (sketch/jelly.js predates this file and keeps its own copies; a later move folds it in.)
*/
(function () {
  'use strict';
  const root = typeof window !== 'undefined' ? window : globalThis;
  const SK = (root.SK = root.SK || {});
  const G = (SK.gl3d = {});
  G.RENDERING = typeof location !== 'undefined' && /[?&](render|export|encode|stills)=/.test(location.search);

  /* ------------------------------------------------------------ vector and matrix maths (column-major) */
  const V = (G.v = {
    add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
    sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
    mul: (a, k) => [a[0] * k, a[1] * k, a[2] * k],
    dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
    cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
    len: (a) => Math.hypot(a[0], a[1], a[2]),
    norm: (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
  });
  G.lookAt = function (e, c, up) {
    const z = V.norm(V.sub(e, c)), x = V.norm(V.cross(up, z)), y = V.cross(z, x);
    return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -V.dot(x, e), -V.dot(y, e), -V.dot(z, e), 1];
  };
  /** perspective with a lens shift (NDC): slides the picture without changing the perspective */
  G.perspective = function (fovDeg, aspect, near, far, shift = [0, 0]) {
    const f = 1 / Math.tan((fovDeg * Math.PI) / 360);
    return [f / aspect, 0, 0, 0, 0, f, 0, 0, -shift[0], -shift[1], (far + near) / (near - far), -1, 0, 0, (2 * far * near) / (near - far), 0];
  };
  G.mul4 = function (a, b) {
    const o = new Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    return o;
  };
  G.invert4 = function (m) {
    const [a00, a01, a02, a03, a10, a11, a12, a13, a20, a21, a22, a23, a30, a31, a32, a33] = m;
    const b00 = a00 * a11 - a01 * a10, b01 = a00 * a12 - a02 * a10, b02 = a00 * a13 - a03 * a10, b03 = a01 * a12 - a02 * a11;
    const b04 = a01 * a13 - a03 * a11, b05 = a02 * a13 - a03 * a12, b06 = a20 * a31 - a21 * a30, b07 = a20 * a32 - a22 * a30;
    const b08 = a20 * a33 - a23 * a30, b09 = a21 * a32 - a22 * a31, b10 = a21 * a33 - a23 * a31, b11 = a22 * a33 - a23 * a32;
    const det = 1 / (b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06);
    return [
      (a11 * b11 - a12 * b10 + a13 * b09) * det, (a02 * b10 - a01 * b11 - a03 * b09) * det, (a31 * b05 - a32 * b04 + a33 * b03) * det, (a22 * b04 - a21 * b05 - a23 * b03) * det,
      (a12 * b08 - a10 * b11 - a13 * b07) * det, (a00 * b11 - a02 * b08 + a03 * b07) * det, (a32 * b02 - a30 * b05 - a33 * b01) * det, (a20 * b05 - a22 * b02 + a23 * b01) * det,
      (a10 * b10 - a11 * b08 + a13 * b06) * det, (a01 * b08 - a00 * b10 - a03 * b06) * det, (a30 * b04 - a31 * b02 + a33 * b00) * det, (a21 * b02 - a20 * b04 - a23 * b00) * det,
      (a11 * b07 - a10 * b09 - a12 * b06) * det, (a00 * b09 - a01 * b07 + a02 * b06) * det, (a31 * b01 - a30 * b03 - a32 * b00) * det, (a20 * b03 - a21 * b01 + a22 * b00) * det,
    ];
  };
  /** world point -> film pixels (SK.W x SK.H) */
  G.project = function (VP, p) {
    const x = VP[0] * p[0] + VP[4] * p[1] + VP[8] * p[2] + VP[12], y = VP[1] * p[0] + VP[5] * p[1] + VP[9] * p[2] + VP[13], w = VP[3] * p[0] + VP[7] * p[1] + VP[11] * p[2] + VP[15];
    return [((x / w) * 0.5 + 0.5) * SK.W, (1 - ((y / w) * 0.5 + 0.5)) * SK.H];
  };
  /** a rigid transform as a column-major mat4: rotation from a unit quaternion [x, y, z, w], then translation */
  G.quatMat = function (q, t) {
    const [x, y, z, w] = q, xx = x * x, yy = y * y, zz = z * z, xy = x * y, xz = x * z, yz = y * z, wx = w * x, wy = w * y, wz = w * z;
    return [1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy), 0, 2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx), 0, 2 * (xz + wy), 2 * (yz - wx), 1 - 2 * (xx + yy), 0, t[0], t[1], t[2], 1];
  };
  /** an orbiting camera: {target, dist, elev, azim, fov, orbit (deg over dur), push (dist change over dur), shift} */
  G.camera = function (c, t, dur) {
    const u = Math.min(1, Math.max(0, t / (dur || 10))), s = u * u * (3 - 2 * u);
    const az = ((c.azim + (c.orbit || 0) * s) * Math.PI) / 180, el = (c.elev * Math.PI) / 180, d = c.dist + (c.push || 0) * s;
    const tg = c.target;
    const eye = [tg[0] + Math.sin(az) * Math.cos(el) * d, tg[1] + Math.sin(el) * d, tg[2] + Math.cos(az) * Math.cos(el) * d];
    const near = 0.05, far = 80;
    const P = G.perspective(c.fov, SK.W / SK.H, near, far, c.shift || [0, 0]);
    return { eye, VP: G.mul4(P, G.lookAt(eye, tg, [0, 1, 0])), near, far };
  };

  /* ------------------------------------------------------------ GLSL shared by every 3D module */
  G.COMMON = `#version 300 es
precision highp float;
uniform vec3 uCam, uKey, uFill, uKeyCol, uFillCol, uAmb, uFloor, uRoom;
vec3 envMap(vec3 d) {
  // walls and ceiling at uRoom (x walls, y ceiling): dark for candy (a photographer's black flags
  // make highlights pop), light for glass (a light tent: dark flags turn a glass foot grey)
  vec3 room = mix(uFloor * 0.8, vec3(uRoom.x), smoothstep(-0.2, 0.25, d.y)); // below: the table itself
  room = mix(room, vec3(uRoom.y), smoothstep(0.3, 1.0, d.y));
  vec3 kx = normalize(cross(uKey, vec3(0.0, 1.0, 0.0))), ky = cross(kx, uKey);
  float c = dot(d, uKey);
  if (c > 0.0) { vec2 q = vec2(dot(d, kx), dot(d, ky)) / c; room += uKeyCol * (1.0 - smoothstep(0.0, 0.05, max(abs(q.x) - 0.5, abs(q.y) - 0.32))) * 9.0; }
  vec3 fx = normalize(cross(uFill, vec3(0.0, 1.0, 0.0))), fy = cross(fx, uFill);
  float cf = dot(d, uFill);
  if (cf > 0.0) { vec2 q = vec2(dot(d, fx), dot(d, fy)) / cf; room += uFillCol * (1.0 - smoothstep(0.0, 0.04, max(abs(q.x) - 0.08, abs(q.y) - 0.7))) * 4.0; }
  return room;
}
vec3 tone(vec3 c) {
  vec3 k = vec3(0.78);
  vec3 hi = k + (1.0 - k) * (1.0 - exp(-(c - k) / (1.0 - k)));
  return pow(clamp(mix(c, hi, step(k, c)), 0.0, 1.0), vec3(1.0 / 2.2));
}
float hash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vnoise(vec3 x) {
  vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x), mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
             mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x), mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float fbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s; }
float spec(vec3 N, vec3 V, vec3 L, float a2) { vec3 H = normalize(L + V); float nh = max(dot(N, H), 0.0), d = nh * nh * (a2 - 1.0) + 1.0; return a2 / (3.14159 * d * d); }
`;
  G.VS_QUAD = `#version 300 es
out vec2 vUv;
void main() { vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2); vUv = p; gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }`;
  const FS_BLUR = `#version 300 es
precision highp float;
in vec2 vUv; uniform sampler2D uTex; uniform vec2 uStep; out vec4 o;
void main() {
  float w[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  vec4 s = texture(uTex, vUv) * w[0];
  for (int i = 1; i < 5; i++) { s += texture(uTex, vUv + uStep * float(i)) * w[i]; s += texture(uTex, vUv - uStep * float(i)) * w[i]; }
  o = s;
}`;
  const FS_COPY = G.COMMON + `
in vec2 vUv; uniform sampler2D uTex; uniform float uTone; out vec4 o;
void main() { vec3 c = texture(uTex, vUv).rgb; o = vec4(uTone > 0.5 ? tone(c) : c, 1.0); }`;
  const FS_OVER = `#version 300 es
precision highp float;
in vec2 vUv; uniform sampler2D uTex; out vec4 o;
void main() { o = texture(uTex, vUv); }`;
  const VS_SHADOW = `#version 300 es
in vec3 aPos;
uniform mat4 uM; uniform vec4 uRect; uniform vec3 uDir;
out float vH;
void main() {
  vec3 p = (uM * vec4(aPos, 1.0)).xyz;
  vec2 q = p.xz - uDir.xz * (p.y / uDir.y);
  vH = p.y;
  gl_Position = vec4((q - uRect.xy) * uRect.zw * 2.0 - 1.0, 0.0, 1.0);
}`;
  const FS_SHADOW = `#version 300 es
precision highp float;
in float vH; uniform float uFall; uniform vec3 uTint; out vec4 o;
void main() { float v = exp(-max(vH, 0.0) * uFall); o = vec4(uTint * v, v); }`;
  // the studio: a sweep -- floor, a curve, a wall behind -- so a camera near the horizon sees paper, not void
  const VS_FLOOR = `#version 300 es
in vec3 aPos;
uniform mat4 uVP; uniform vec2 uC;
out vec3 vW;
void main() { vW = aPos + vec3(uC.x, 0.0, uC.y); gl_Position = uVP * vec4(vW, 1.0); }`;
  const FS_FLOOR = G.COMMON + `
in vec3 vW;
uniform sampler2D uContact, uCast; uniform vec4 uCRect, uSRect; uniform vec3 uPool; uniform float uAO, uCastK;
out vec4 o;
vec4 rect(sampler2D t, vec4 r, vec2 p) { vec2 uv = (p - r.xy) * r.zw; if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) return vec4(0.0); return texture(t, uv); }
void main() {
  float d = length(vW.xz - uPool.xy);
  vec3 c = uFloor * mix(0.84, 1.06, exp(-d * d * uPool.z));
  c *= 1.0 - uAO * rect(uContact, uCRect, vW.xz).a;
  // the cast shadow carries a tint (rgb, premultiplied): a coloured object throws coloured light
  vec4 s = rect(uCast, uSRect, vW.xz);
  vec3 tint = s.a > 1e-3 ? s.rgb / s.a : vec3(1.0);
  c *= mix(vec3(1.0), tint, clamp(s.a, 0.0, 1.0) * uCastK);
  c *= mix(1.0, 0.8, smoothstep(0.4, 5.0, vW.y)); // the sweep darkens as it rises away from the light
  o = vec4(c, 1.0);
}`;

  /* ------------------------------------------------------------ a stage: GL context, studio, targets */
  /**
   * new SK.gl3d.Stage({ ss, light: {key, fill, floor}, camera, dur })
   * .prog(vs, fs) -> {p, u}; .tex/.fbo/.buf; .targets: half-float scene targets sized to the frame
   * .shadows(draws, centre) -- draws: [{vao, count, M, tint}] -> contact + cast maps
   * .floor(fbo, cam, centre) -- the floor with those shadows into a target
   * .copy(srcTex, dstFbo, tone) ; .over(srcTex, dstFbo) (premultiplied alpha)
   * .present(tex) -- tone-map to the canvas, then draw the canvas into the 2D film
   */
  G.Stage = function (o) {
    const ss = (SK.LIVE && SK.LIVE.ss) || o.ss || (G.RENDERING ? 2 : 1);
    const W = Math.round(SK.W * ss), H = Math.round(SK.H * ss);
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const gl = cv.getContext('webgl2', { antialias: false, alpha: false, premultipliedAlpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    Object.assign(this, { o, ss, W, H, canvas: cv, gl, ok: !!gl });
    if (!gl) return;
    this.half = gl.getExtension('EXT_color_buffer_float') ? gl.RGBA16F : gl.RGBA8;
    this.halfType = this.half === gl.RGBA16F ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE;
    this.empty = gl.createVertexArray();
    this.P = {
      blur: this.prog(G.VS_QUAD, FS_BLUR), copy: this.prog(G.VS_QUAD, FS_COPY), over: this.prog(G.VS_QUAD, FS_OVER),
      shadow: this.prog(VS_SHADOW, FS_SHADOW), floor: this.prog(VS_FLOOR, FS_FLOOR),
    };
    this.sh = {};
    for (const [k, size] of [['contact', 512], ['cast', 256]]) {
      const a = this.tex(size, size, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, gl.LINEAR), b = this.tex(size, size, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, gl.LINEAR);
      this.sh[k] = { size, a, b, fa: this.fbo(a, null), fb: this.fbo(b, null) };
    }
    this.out = this.colorTarget(); // the last target before the tone curve
    // the sweep: floor from the camera side to z = -back, a quarter circle of radius R up, a wall
    const back = o.sweep?.back ?? 3.2, R = o.sweep?.radius ?? 2.5, prof = [[14, 0], [-back, 0]];
    for (let k = 1; k <= 16; k++) { const a = (k / 16) * Math.PI / 2; prof.push([-back - Math.sin(a) * R, R - Math.cos(a) * R]); }
    prof.push([-back - R, 30]);
    const sp = [], stri = [];
    prof.forEach(([z, y]) => sp.push(-60, y, z, 60, y, z));
    for (let k = 0; k < prof.length - 1; k++) { const a = k * 2; stri.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    this.sweep = gl.createVertexArray(); gl.bindVertexArray(this.sweep);
    this.buf(new Float32Array(sp)); gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    this.buf(new Uint32Array(stri), gl.ELEMENT_ARRAY_BUFFER); this.sweepCount = stri.length;
    gl.bindVertexArray(null);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  };
  const S = G.Stage.prototype;
  S.prog = function (vs, fs) {
    const gl = this.gl, p = gl.createProgram();
    for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
      const sh = gl.createShader(type); gl.shaderSource(sh, src); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error('gl3d shader: ' + gl.getShaderInfoLog(sh));
      gl.attachShader(p, sh);
    }
    ['aPos', 'aNrm', 'aAttr', 'aInst', 'aInst2'].forEach((n, i) => gl.bindAttribLocation(p, i, n));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error('gl3d program: ' + gl.getProgramInfoLog(p));
    const u = {}, nu = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < nu; i++) { const info = gl.getActiveUniform(p, i); u[info.name.replace(/\[0\]$/, '')] = gl.getUniformLocation(p, info.name); }
    return { p, u };
  };
  S.tex = function (w, h, ifmt, fmt, type, filter) {
    const gl = this.gl, t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, ifmt, w, h, 0, fmt, type, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter === gl.LINEAR_MIPMAP_LINEAR ? gl.LINEAR : filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  };
  S.fbo = function (color, depth) {
    const gl = this.gl, f = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    if (color) gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, color, 0);
    if (depth) gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, depth, 0);
    gl.drawBuffers(color ? [gl.COLOR_ATTACHMENT0] : [gl.NONE]); gl.readBuffer(gl.NONE);
    return f;
  };
  S.buf = function (data, target, usage) {
    const gl = this.gl, b = gl.createBuffer();
    gl.bindBuffer(target || gl.ARRAY_BUFFER, b); gl.bufferData(target || gl.ARRAY_BUFFER, data, usage || gl.STATIC_DRAW);
    return b;
  };
  /** a half-float colour texture (mipmapped when asked: a blurred lookup through thick glass) */
  S.colorTarget = function (mips) {
    const gl = this.gl;
    const t = this.tex(this.W, this.H, this.half, gl.RGBA, this.halfType, mips ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
    if (mips) gl.generateMipmap(gl.TEXTURE_2D);
    return t;
  };
  S.depthTarget = function () { const gl = this.gl; return this.tex(this.W, this.H, gl.DEPTH_COMPONENT24, gl.DEPTH_COMPONENT, gl.UNSIGNED_INT, gl.NEAREST); };
  S.mips = function (t) { const gl = this.gl; gl.bindTexture(gl.TEXTURE_2D, t); gl.generateMipmap(gl.TEXTURE_2D); gl.bindTexture(gl.TEXTURE_2D, null); };
  S.setCommon = function (u, cam) {
    const gl = this.gl, lt = this.o.light;
    gl.uniform3fv(u.uCam, cam.eye); gl.uniform3fv(u.uKey, V.norm(lt.key)); gl.uniform3fv(u.uFill, V.norm(lt.fill));
    gl.uniform3fv(u.uKeyCol, lt.keyCol || [1.0, 0.97, 0.93]); gl.uniform3fv(u.uFillCol, lt.fillCol || [0.9, 0.93, 1.0]);
    gl.uniform3fv(u.uAmb, lt.amb || [0.34, 0.33, 0.32]); gl.uniform3fv(u.uFloor, lt.floor);
    gl.uniform3fv(u.uRoom, [...(lt.room || [0.3, 0.22]), 0]);
    if (u.uVP) gl.uniformMatrix4fv(u.uVP, false, new Float32Array(cam.VP));
  };
  /** contact and cast shadow maps from a list of meshes: [{vao, count, M (mat4), tint [r,g,b]}] */
  S.shadows = function (draws, centre, opt = {}) {
    const gl = this.gl, P = this.P, key = V.norm(this.o.light.key);
    gl.disable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE); gl.enable(gl.BLEND); gl.blendEquation(gl.MAX); gl.blendFunc(gl.ONE, gl.ONE);
    const cr = opt.contact || 1.6, sr = opt.cast || 2.6;
    this.rects = { contact: [centre[0] - cr, centre[1] - cr, 1 / (2 * cr), 1 / (2 * cr)], cast: [centre[0] - sr, centre[1] - sr, 1 / (2 * sr), 1 / (2 * sr)] };
    for (const [k, dir, fall] of [['contact', [0, 1, 0], 1 / (opt.contactFall || 0.07)], ['cast', key, 1 / (opt.castFall || 1.6)]]) {
      const Sh = this.sh[k];
      gl.bindFramebuffer(gl.FRAMEBUFFER, Sh.fa); gl.viewport(0, 0, Sh.size, Sh.size); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(P.shadow.p);
      gl.uniform4fv(P.shadow.u.uRect, this.rects[k]); gl.uniform3fv(P.shadow.u.uDir, dir); gl.uniform1f(P.shadow.u.uFall, fall);
      for (const d of draws) {
        if (k === 'contact' && d.noContact) continue;
        gl.uniformMatrix4fv(P.shadow.u.uM, false, new Float32Array(d.M || IDENT));
        gl.uniform3fv(P.shadow.u.uTint, d.tint || [0.3, 0.3, 0.3]);
        gl.bindVertexArray(d.vao); gl.drawElements(gl.TRIANGLES, d.count, gl.UNSIGNED_INT, 0);
      }
    }
    gl.disable(gl.BLEND); gl.blendEquation(gl.FUNC_ADD);
    gl.useProgram(P.blur.p); gl.bindVertexArray(this.empty); gl.activeTexture(gl.TEXTURE0); gl.uniform1i(P.blur.u.uTex, 0);
    for (const [k, px, iters] of [['contact', opt.contactBlur || 1.6, 2], ['cast', opt.castBlur || 2.2, 3]]) {
      const Sh = this.sh[k];
      gl.viewport(0, 0, Sh.size, Sh.size);
      for (let i = 0; i < iters; i++) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, Sh.fb); gl.bindTexture(gl.TEXTURE_2D, Sh.a); gl.uniform2f(P.blur.u.uStep, px / Sh.size, 0); gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.bindFramebuffer(gl.FRAMEBUFFER, Sh.fa); gl.bindTexture(gl.TEXTURE_2D, Sh.b); gl.uniform2f(P.blur.u.uStep, 0, px / Sh.size); gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
    }
  };
  S.floor = function (fbo, cam, centre, opt = {}) {
    const gl = this.gl, P = this.P.floor, u = P.u;
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo); gl.viewport(0, 0, this.W, this.H);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.depthMask(true); gl.disable(gl.CULL_FACE);
    gl.clearColor(0, 0, 0, 1); gl.clearDepth(1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(P.p); this.setCommon(u, cam);
    gl.uniform2f(u.uC, centre[0], centre[1]);
    gl.uniform4fv(u.uCRect, this.rects.contact); gl.uniform4fv(u.uSRect, this.rects.cast);
    gl.uniform3fv(u.uPool, opt.pool || [centre[0] - 0.35, centre[1] - 0.25, 0.28]);
    gl.uniform1f(u.uAO, opt.ao ?? 0.72); gl.uniform1f(u.uCastK, opt.castK ?? 0.8);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.sh.contact.a); gl.uniform1i(u.uContact, 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.sh.cast.a); gl.uniform1i(u.uCast, 1);
    gl.bindVertexArray(this.sweep); gl.drawElements(gl.TRIANGLES, this.sweepCount, gl.UNSIGNED_INT, 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, null); gl.activeTexture(gl.TEXTURE0);
  };
  S.copy = function (src, dst, tone) {
    const gl = this.gl, P = this.P.copy;
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst); gl.viewport(0, 0, this.W, this.H);
    gl.disable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE); gl.disable(gl.BLEND); gl.depthMask(false);
    gl.useProgram(P.p); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, src); gl.uniform1i(P.u.uTex, 0); gl.uniform1f(P.u.uTone, tone ? 1 : 0);
    gl.bindVertexArray(this.empty); gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.depthMask(true);
  };
  /** composite a premultiplied layer over a target */
  S.over = function (src, dst) {
    const gl = this.gl, P = this.P.over;
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst); gl.viewport(0, 0, this.W, this.H);
    gl.disable(gl.DEPTH_TEST); gl.depthMask(false); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(P.p); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, src); gl.uniform1i(P.u.uTex, 0);
    gl.bindVertexArray(this.empty); gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.disable(gl.BLEND); gl.depthMask(true);
  };
  /** tone-map a linear target onto the canvas and draw it into the film's 2D context */
  S.present = function (src) {
    this.copy(src, null, true);
    const ctx = SK.ctx();
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(this.canvas, 0, 0, SK.W, SK.H);
    ctx.restore();
  };
  const IDENT = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  G.IDENT = IDENT;

  /* ------------------------------------------------------------ meshes */
  /** a closed surface of revolution from a profile [[r, y], ...] (axis at r = 0), normals out of
   *  the solid. attr(i) gives each profile point a scalar the shader reads (aAttr). */
  G.lathe = function (profile, segs, attr) {
    const n = profile.length, pos = [], nrm = [], at = [], tri = [];
    // 2D normals: perpendicular to the averaged tangent, pointing to the right of travel
    const n2 = profile.map((p, i) => {
      const a = profile[Math.max(0, i - 1)], b = profile[Math.min(n - 1, i + 1)];
      const tx = b[0] - a[0], ty = b[1] - a[1], l = Math.hypot(tx, ty) || 1;
      return [ty / l, -tx / l];
    });
    for (let s = 0; s <= segs; s++) {
      const a = (s / segs) * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a);
      for (let i = 0; i < n; i++) {
        const [r, y] = profile[i];
        pos.push(r * ca, y, r * sa);
        nrm.push(n2[i][0] * ca, n2[i][1], n2[i][0] * sa);
        at.push(attr ? attr(i, profile[i]) : 0);
      }
    }
    for (let s = 0; s < segs; s++) for (let i = 0; i < n - 1; i++) {
      const a = s * n + i, b = (s + 1) * n + i;
      tri.push(a, a + 1, b, b, a + 1, b + 1);
    }
    return { pos: new Float32Array(pos), nrm: new Float32Array(nrm), attr: new Float32Array(at), tri: new Uint32Array(tri) };
  };
  /** a UV sphere (for instanced droplets and bubbles) */
  G.sphere = function (rings, segs) {
    const pos = [], tri = [];
    for (let r = 0; r <= rings; r++) {
      const v = (r / rings) * Math.PI;
      for (let s = 0; s <= segs; s++) { const u = (s / segs) * Math.PI * 2; pos.push(Math.sin(v) * Math.cos(u), Math.cos(v), Math.sin(v) * Math.sin(u)); }
    }
    for (let r = 0; r < rings; r++) for (let s = 0; s < segs; s++) {
      const a = r * (segs + 1) + s, b = a + segs + 1;
      tri.push(a, a + 1, b, a + 1, b + 1, b); // y is the pole, which flips the handedness: this order faces out
    }
    return { pos: new Float32Array(pos), nrm: new Float32Array(pos), tri: new Uint32Array(tri) };
  };
  /** normals from triangles (area-weighted), for meshes that deform */
  G.normals = function (pos, tri, out) {
    out = out || new Float32Array(pos.length);
    out.fill(0);
    for (let q = 0; q < tri.length; q += 3) {
      const a = tri[q] * 3, b = tri[q + 1] * 3, c = tri[q + 2] * 3;
      const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
      const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      for (const k of [a, b, c]) { out[k] += nx; out[k + 1] += ny; out[k + 2] += nz; }
    }
    for (let v = 0; v < out.length; v += 3) { const l = Math.hypot(out[v], out[v + 1], out[v + 2]) || 1; out[v] /= l; out[v + 1] /= l; out[v + 2] /= l; }
    return out;
  };
})();
