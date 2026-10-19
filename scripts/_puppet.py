"""Puppets: an actor drawn once in an A-pose, cut into parts on a skeleton and moved by its joints
(sketch/puppet.js). Not an entry script -- actor-pack.py builds a puppet (its "rig") and
sketch-render.py inlines one into a film's page.

A puppet is a folder: puppet.json (bones, parts as skinned meshes, the face patches, props) and its
atlas pages. A film names it in "puppets": {"enrique": "actors/enrique"}."""

import os
import sys
import json


def film_puppets(m, rel):
    """{name: (puppet dict, folder)} for a manifest's "puppets" ({"enrique": "actors/enrique"}, or
    {"enrique": {"pack": ...}}). One without its puppet.json is left out with a warning."""
    out = {}
    for name, spec in (m.get("puppets") or {}).items():
        d = rel(m, spec if isinstance(spec, str) else spec.get("pack") or "actors/" + name)
        p = os.path.join(d, "puppet.json")
        if not os.path.exists(p):
            print(
                "  WARNING puppet %r has no puppet.json (%s): actor-pack.py --spec <its spec> with "
                '"rig": true' % (name, p),
                file=sys.stderr,
            )
            continue
        with open(p, encoding="utf-8") as f:
            P = json.load(f)
        out[name] = (P, d)
        for vn, v in (P.get("views") or {}).items():  # its turned views: '<name>@<view>'
            vp = os.path.join(d, v["dir"], "puppet.json")
            if os.path.exists(vp):
                with open(vp, encoding="utf-8") as f:
                    out[name + "@" + vn] = (json.load(f), os.path.join(d, v["dir"]))
            else:
                print(
                    "  WARNING puppet %r: its view %r is missing (%s)" % (name, vn, vp),
                    file=sys.stderr,
                )
    return out


def film_script(m, rel):
    """The <script> that hands the puppets to sketch/puppet.js ("" for a film without)."""
    body = {n: P for n, (P, _) in film_puppets(m, rel).items()}
    if not body:
        return ""
    # "</" never reaches the page as written: an about's words could otherwise close the script
    text = json.dumps(body, separators=(",", ":")).replace("</", "<\\/")
    return "<script>\nSK.PUPPETS = Object.assign(SK.PUPPETS || {}, %s);\n</script>" % text


def film_images(m, rel):
    """{'puppet:<name>:<n>': atlas page path} for the page's image loader."""
    return {
        "puppet:%s:%d" % (n, i): os.path.join(d, pg)
        for n, (P, d) in film_puppets(m, rel).items()
        for i, pg in enumerate(P["pages"])
    }


# ------------------------------------------------------------------ building a rig
# Measured on Enrique (2026-10-18), each the reason for a number below:
#   * the arm's cut is the drawing's own sleeve seam: the darkest line through the armpit, searched
#     +-22 deg round the guess from the joints (a cut beside the seam left a sliver of sleeve on the
#     shirt that showed whenever the arm lifted);
#   * the shoulder turns about a point on that seam 14 % down from its top;
#   * a strip of shirt goes on under each sleeve with the drawing's own ink on its far edge: hidden
#     while the arm is down, the shirt's side when it lifts (without it the torso showed a knife cut;
#     with the ink on the near side, a black line showed beside every sleeve at rest);
#   * a rigid shoulder beat a sleeve blended into the chest: blending stretched the sleeve into a
#     white flap the moment the arm went past 60 deg (seam_blend 0.45 against 0, side by side);
#   * legs carry a third of a thigh of hidden shorts above their cut and are drawn behind the torso,
#     and the neck goes on under the head, so no joint opens a gap.
RIG = {
    "grid": 0.02,  # mesh cell, of the figure's height
    "elbow_band": 0.18,
    "wrist_band": 0.12,
    "knee_band": 0.14,
    "ankle_band": 0.10,
    "neck_band": 0.5,  # the head's bottom blends into the chest over half the neck's width
    "waist": 0.35,  # the chest bends at this height between hips and shoulders
    "waist_band": 0.12,
    "shoulder": 0.14,  # the shoulder's pivot on the seam, from its top
    "leg_stock": 0.35,  # hidden shorts above a leg's cut, of the thigh
    "seam_search": 22,  # degrees either side of the guess
}
POSE_MODEL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/"
    "float16/latest/pose_landmarker_heavy.task"
)
LANDMARKS = {
    0: "nose", 11: "l_sh", 12: "r_sh", 13: "l_el", 14: "r_el", 15: "l_wr", 16: "r_wr",
    23: "l_hip", 24: "r_hip", 25: "l_kn", 26: "r_kn", 27: "l_an", 28: "r_an", 31: "l_toe", 32: "r_toe",
}  # fmt: skip
ORDER = ["leg_r", "leg_l", "torso", "head", "arm_r", "arm_l"]  # back to front


def _np():
    import numpy as np  # noqa: PLC0415 -- the film helpers above are stdlib only
    import cv2  # noqa: PLC0415

    return np, cv2


def pose_model():
    """models/heads/pose_landmarker_heavy.task (beside head-rig's own MediaPipe models)."""
    import _env  # noqa: PLC0415

    return _env.resolve("models/heads/pose_landmarker_heavy.task")


def fetch_pose_model():
    import urllib.request  # noqa: PLC0415

    p = pose_model()
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        print("  fetch %s" % os.path.basename(p))
        urllib.request.urlretrieve(POSE_MODEL, p + ".part")
        os.replace(p + ".part", p)
    return p


def sane(J):
    """Whether a pose is a standing figure facing us: the joints in their order down the body, and
    each side on its own side of the picture. MediaPipe's pose comes back nonsense for some
    framings of the same drawing (a hip above the shoulders, 2026-10-18)."""
    y = lambda n: J[n][1]  # noqa: E731
    x = lambda n: J[n][0]  # noqa: E731
    for s in ("r", "l"):
        if not (y("nose") < y(s + "_sh") < y(s + "_hip") < y(s + "_kn") < y(s + "_an")):
            return False
        if not y(s + "_sh") < y(s + "_el") < y(s + "_wr"):
            return False
    return x("r_sh") < x("l_sh") and x("r_hip") < x("l_hip") and x("r_an") < x("l_an")


def joints(bgra):
    """MediaPipe's pose on the figure: {name: [x, y, visibility]}, sides the character's (r is on
    the picture's left). Tried in a few framings (the figure's box with a margin of each size), the
    first sane one kept. MediaPipe from head-rig's runtime (models/heads/py)."""
    np, cv2 = _np()
    from importlib import import_module  # noqa: PLC0415

    import _actor  # noqa: PLC0415

    hr = import_module("head-rig")
    mp, vision, base_options = hr._mediapipe()
    if not os.path.exists(pose_model()):
        sys.exit("missing %s: run actor-pack.py --fetch-models" % pose_model())
    det = vision.PoseLandmarker.create_from_options(
        vision.PoseLandmarkerOptions(
            base_options=base_options(model_asset_path=pose_model()),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
        )
    )
    ys, xs = np.nonzero(bgra[..., 3] > 8)
    ox, oy = int(xs.min()), int(ys.min())
    fig = _actor.on_white(bgra[oy : ys.max() + 1, ox : xs.max() + 1])
    h, w = fig.shape[:2]
    for margin, square in ((0.2, False), (0.12, False), (0.3, False), (0.1, True), (0.4, True)):
        m = int(margin * max(h, w))
        H, W = h + 2 * m, w + 2 * m
        if square:
            W = H = max(H, W)
        canvas = np.full((H, W, 3), 255, np.uint8)
        x0, y0 = (W - w) // 2, (H - h) // 2
        canvas[y0 : y0 + h, x0 : x0 + w] = fig
        r = det.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
        )
        if not r.pose_landmarks:
            continue
        L = r.pose_landmarks[0]
        J = {
            n: [L[i].x * W - x0 + ox, L[i].y * H - y0 + oy, round(float(L[i].visibility), 3)]
            for i, n in LANDMARKS.items()
        }
        if sane(J):
            return J
    raise ValueError(
        "no sane pose found in the figure: is it a full-length front view, arms apart?"
    )


def _P(J, n):
    np, _ = _np()
    return np.array(J[n][:2], float)


def _smooth(e0, e1, x):
    np, _ = _np()
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _run_at(row, x):
    if not row[int(x)]:
        return None
    x0 = x1 = int(x)
    while x0 > 0 and row[x0 - 1]:
        x0 -= 1
    while x1 < len(row) - 1 and row[x1 + 1]:
        x1 += 1
    return x0, x1


def _ray_exit(A, p, d, maxlen=4000):
    """The first point along p + t d that leaves the silhouette after being inside it."""
    np, _ = _np()
    d = d / np.linalg.norm(d)
    h, w = A.shape
    inside = False
    for t in np.arange(0, maxlen, 0.5):
        q = p + t * d
        x, y = int(round(q[0])), int(round(q[1]))
        if not (0 <= x < w and 0 <= y < h):
            return q
        if A[y, x]:
            inside = True
        elif inside:
            return q
    return p + maxlen * d


def _in_triangle(pts, a, b, c):
    def s(p1, p2, p3):
        return (p1[..., 0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[..., 1] - p3[1])

    d1, d2, d3 = s(pts, a, b), s(pts, b, c), s(pts, c, a)
    return ~(((d1 < 0) | (d2 < 0) | (d3 < 0)) & ((d1 > 0) | (d2 > 0) | (d3 > 0)))


def _component(mask, seeds):
    np, cv2 = _np()
    _, lab = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
    keep = {lab[int(round(s[1])), int(round(s[0]))] for s in seeds} - {0}
    return np.isin(lab, list(keep)) if keep else np.zeros_like(mask)


def _cut(mask, a, b, width=3):
    np, cv2 = _np()
    m = mask.astype(np.uint8).copy()
    cv2.line(m, tuple(int(round(v)) for v in a), tuple(int(round(v)) for v in b), 0, width)
    return m.astype(bool)


def segment(A, J, gray=None, opt=None):
    """The figure's silhouette A cut into head, torso, arm_r/l and leg_r/l: (masks, cuts, info).
    gray: the drawing in grey, to snap each armhole to its drawn seam."""
    np, _ = _np()
    o = {**RIG, **(opt or {})}
    h, w = A.shape
    ys, xs = np.mgrid[0:h, 0:w]
    pts = np.dstack([xs, ys]).astype(float)
    cuts = {}
    # the neck: the narrowest run between the nose and the shoulders, on the body's centre line
    sh_y = min(J["r_sh"][1], J["l_sh"][1])
    nose = _P(J, "nose")
    cx = (J["r_sh"][0] + J["l_sh"][0]) / 2
    best = None
    for y in range(int(nose[1] + 0.35 * (sh_y - nose[1])), int(sh_y)):
        r = _run_at(A[y], cx)
        if r and (best is None or r[1] - r[0] < best[2] - best[1]):
            best = (y, r[0], r[1])
    if best is None:
        raise ValueError("no neck found between the nose and the shoulders")
    ny, nx0, nx1 = best
    cuts["neck"] = [[nx0 - 3, ny], [nx1 + 3, ny]]
    work = A.copy()
    work[ny : ny + 2, nx0 - 3 : nx1 + 4] = False
    # the arms: from the armpit (the gap between arm and body nearest the shoulder) up the seam.
    # The cut stops at the neck: in a three-quarter view the near seam leans in, and a ray run to
    # the silhouette's edge went on up through the head and gave half of it to the torso
    body = A & (ys > ny)
    for s in ("r", "l"):
        SJ, EL, HIP = _P(J, s + "_sh"), _P(J, s + "_el"), _P(J, s + "_hip")
        gy, gx = np.nonzero(~A & _in_triangle(pts, SJ, EL, HIP))
        if not len(gx):
            raise ValueError("arm %s touches the body: the rig needs an A-pose" % s)
        k = np.argmin((gx - SJ[0]) ** 2 + (gy - SJ[1]) ** 2)
        pit = np.array([gx[k], gy[k]], float)
        out = _ray_exit(body, SJ, SJ - pit)
        if gray is not None:
            v0, top = out - pit, (-1.0, out)
            for th in np.arange(-o["seam_search"], o["seam_search"] + 0.1, 0.5):
                c, sn = np.cos(np.radians(th)), np.sin(np.radians(th))
                d = np.array([c * v0[0] - sn * v0[1], sn * v0[0] + c * v0[1]])
                e = _ray_exit(body, pit + d / np.linalg.norm(d) * 3, d)
                q = pit[None] + np.linspace(0.12, 0.85, 60)[:, None] * (e - pit)[None]
                xi, yi = q[:, 0].round().astype(int), q[:, 1].round().astype(int)
                ok = (xi >= 0) & (yi >= 0) & (xi < w) & (yi < h)
                long_enough = np.linalg.norm(e - pit) > 0.5 * np.linalg.norm(v0)
                score = (255 - gray[yi[ok], xi[ok]].astype(float)).mean() if ok.sum() > 20 else -1
                if long_enough and score > top[0]:
                    top = (score, e)
            out = top[1]
        cuts["arm_" + s] = [pit.tolist(), out.tolist()]
        work = _cut(work, pit - (SJ - pit) / np.linalg.norm(SJ - pit) * 2, out)
    # the legs: from the crotch (the top of the gap between the legs) outwards, square to each thigh
    hips, kn = [_P(J, "r_hip"), _P(J, "l_hip")], [_P(J, "r_kn"), _P(J, "l_kn")]
    quad = _in_triangle(pts, hips[0], hips[1], kn[1]) | _in_triangle(pts, hips[0], kn[1], kn[0])
    gy, gx = np.nonzero(~A & quad)
    if not len(gx):
        raise ValueError("no gap between the legs: the rig needs the feet a little apart")
    k = np.argmin(gy)
    crotch = np.array([gx[k], gy[k]], float)
    for s, i in (("r", 0), ("l", 1)):
        thigh = kn[i] - hips[i]
        n = np.array([-thigh[1], thigh[0]]) / np.linalg.norm(thigh)
        if np.dot(n, hips[i] - (hips[0] + hips[1]) / 2) < 0:
            n = -n
        cuts["leg_" + s] = [crotch.tolist(), _ray_exit(A, crotch + n * 2, n).tolist()]
        work = _cut(work, crotch - n * 2, cuts["leg_" + s][1])
    masks = {"head": _component(work & (ys < ny), [nose])}
    for s in ("r", "l"):
        masks["arm_" + s] = _component(work, [_P(J, s + "_el"), _P(J, s + "_wr")])
        masks["leg_" + s] = _component(work, [_P(J, s + "_kn"), _P(J, s + "_an")])
    taken = np.zeros_like(A)
    for m in masks.values():
        taken |= m
    masks["torso"] = A & ~taken
    # each leg goes on, hidden, a third of a thigh up under the shorts
    for s, i in (("r", 0), ("l", 1)):
        a, b = (np.array(v) for v in cuts["leg_" + s])
        ab = b - a
        nrm = np.array([-ab[1], ab[0]]) / np.linalg.norm(ab)
        if np.dot(nrm, hips[i] - a) < 0:
            nrm = -nrm
        d = (pts - a) @ nrm
        t = ((pts - a) @ ab) / (ab @ ab)
        stock = (d > -1) & (d < o["leg_stock"] * (kn[i][1] - hips[i][1])) & (t > -0.02) & (t < 1.02)
        masks["leg_" + s] |= masks["torso"] & stock
    return masks, cuts, {"neck": [ny, nx0, nx1], "crotch": crotch.tolist()}


def grid_mesh(mask, g, pad=3):
    """Vertices on a g-pixel grid over the mask's box, and triangles on every cell touching the
    mask (dilated by pad). The texture's own alpha draws the edge; the mesh only has to bend."""
    np, cv2 = _np()
    import math  # noqa: PLC0415

    m = cv2.dilate(mask.astype(np.uint8), np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)) > 0
    ys, xs = np.nonzero(m)
    x0, y0 = xs.min(), ys.min()
    nx = int(math.ceil((xs.max() + 1 - x0) / g)) + 1
    ny = int(math.ceil((ys.max() + 1 - y0) / g)) + 1
    idx = -np.ones((ny, nx), int)
    ii = cv2.integral(m.astype(np.uint8))
    verts, tris = [], []

    def any_in(cx0, cy0, cx1, cy1):
        cx0, cy0, cx1, cy1 = max(cx0, 0), max(cy0, 0), min(cx1, m.shape[1]), min(cy1, m.shape[0])
        if cx1 <= cx0 or cy1 <= cy0:
            return False
        return ii[cy1, cx1] - ii[cy0, cx1] - ii[cy1, cx0] + ii[cy0, cx0] > 0

    def vid(i, j):
        if idx[j, i] < 0:
            idx[j, i] = len(verts)
            verts.append((x0 + i * g, y0 + j * g))
        return idx[j, i]

    for j in range(ny - 1):
        for i in range(nx - 1):
            cx0, cy0 = int(x0 + i * g), int(y0 + j * g)
            if any_in(cx0, cy0, int(cx0 + g) + 1, int(cy0 + g) + 1):
                a, b, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
                tris += [(a, b, c), (a, c, d)]
    return np.array(verts, float), np.array(tris, int)


def _chain_param(v, chain):
    np, _ = _np()
    best_d, best_s, acc = np.full(len(v), np.inf), np.zeros(len(v)), 0.0
    for a, b in zip(chain[:-1], chain[1:]):
        ab = b - a
        L = np.linalg.norm(ab)
        t = np.clip(((v - a) @ ab) / (L * L), 0, 1)
        d = np.linalg.norm(v - (a + t[:, None] * ab), axis=1)
        better = d < best_d
        best_d[better], best_s[better] = d[better], acc + t[better] * L
        acc += L
    return best_s


def weights(part, V, J, info, opt=None):
    """Per vertex [[bone, weight], ...] (at most 4, summing to 1) for a part's mesh."""
    np, _ = _np()
    o = {**RIG, **(opt or {})}
    rows = []
    if part.startswith(("arm_", "leg_")):
        s = part[-1]
        if part.startswith("arm_"):
            names = ["arm_%s_up" % s, "arm_%s_lo" % s, "hand_%s" % s]
            chain = [
                _P(J, s + "_sh"),
                _P(J, s + "_el"),
                _P(J, s + "_wr"),
                np.array(info["tips"][s]),
            ]
            b1, b2 = o["elbow_band"], (0 if info.get("hands") else o["wrist_band"])
        else:
            names = ["leg_%s_up" % s, "leg_%s_lo" % s, "foot_%s" % s]
            chain = [_P(J, s + "_hip"), _P(J, s + "_kn"), _P(J, s + "_an"), _P(J, s + "_toe")]
            b1, b2 = o["knee_band"], o["ankle_band"]
        sv = _chain_param(V, chain)
        L1 = np.linalg.norm(chain[1] - chain[0])
        L2 = L1 + np.linalg.norm(chain[2] - chain[1])
        w_lo = _smooth(L1 - b1 * L1, L1 + b1 * L1, sv)
        w_end = (
            _smooth(L2 - b2 * (L2 - L1), L2 + b2 * (L2 - L1), sv) if b2 else (sv > L2 + 1e9) * 1.0
        )
        cols = [(names[0], 1 - w_lo), (names[1], w_lo - w_end), (names[2], w_end)]
    elif part == "head":
        ny, nx0, nx1 = info["neck"]
        w_head = _smooth(ny, ny - o["neck_band"] * (nx1 - nx0), V[:, 1])
        cols = [("head", w_head), ("chest", 1 - w_head)]
    else:
        hip_y = (J["r_hip"][1] + J["l_hip"][1]) / 2
        sh_y = (J["r_sh"][1] + J["l_sh"][1]) / 2
        wy, band = hip_y - o["waist"] * (hip_y - sh_y), o["waist_band"] * (hip_y - sh_y)
        w_chest = _smooth(wy + band, wy - band, V[:, 1])
        cols = [("chest", w_chest), ("pelvis", 1 - w_chest)]
    for k in range(len(V)):
        row = [(n, float(w[k])) for n, w in cols if w[k] > 1e-3]
        tot = sum(w for _, w in row) or 1.0
        rows.append([[n, round(w / tot, 4)] for n, w in row])
    return rows


def _crop(img, x0, y0, x1, y1):
    """img[y0:y1, x0:x1], transparent where the box leaves the picture."""
    np, _ = _np()
    h, w = img.shape[:2]
    out = np.zeros((y1 - y0, x1 - x0) + img.shape[2:], img.dtype)
    sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = img[sy0:sy1, sx0:sx1]
    return out


def ink(base, A, below):
    """The drawing's outline: its colour and its width in pixels (runs across rows below `below`,
    the neck, so hair does not count)."""
    np, _ = _np()
    rgb = base[..., :3].astype(int)
    line = A & (rgb.mean(2) < 120) & (rgb.max(2) - rgb.min(2) < 40)
    runs = []
    for y in range(int(below) + 20, A.shape[0] - 20, 7):
        r = np.diff(np.concatenate([[0], line[y].astype(int), [0]]))
        runs += list(np.nonzero(r < 0)[0] - np.nonzero(r > 0)[0])
    lw = float(np.clip(np.median(runs) + 1 if runs else 3, 2, 8))
    px = base[..., :3][line]
    col = np.median(px, 0) if len(px) else np.array([30, 27, 36])
    return [int(c) for c in col], lw


def build(base, J, faces, patches, props=None, opt=None, hands=None):
    """A puppet from an A-pose figure `base` (BGRA, the actor pack's base piece) and its joints J.
    faces: the pack's faces (patches placed in base pixels); patches: {piece id: BGRA}; props:
    {name: (BGRA, {"hand": "r", "length": 0.19, "grip": 0.18, "angle": 180})}; hands: {side: {shape:
    BGRA}}, each the whole figure redrawn with that hand, laid on the base (actor-pack.py's hand
    redraws): a hand becomes a piece of its own, cut at the wrist. Returns (puppet
    dict without "pages", {piece id: BGRA} to pack, a picture of the cuts for checking)."""
    np, cv2 = _np()
    import _actor  # noqa: PLC0415

    o = {**RIG, **(opt or {})}
    A = base[..., 3] > 8
    gray = cv2.cvtColor(_actor.on_white(base), cv2.COLOR_BGR2GRAY)
    masks, cuts, info = segment(A, J, gray, o)
    H = _actor.figure(base[..., 3])["height"]
    J = {k: list(v) for k, v in J.items()}
    for s in ("r", "l"):  # the shoulder turns about a point on its seam, a little below the top
        pit, top = (np.array(v) for v in cuts["arm_" + s])
        J[s + "_sh"] = (top + o["shoulder"] * (pit - top)).tolist() + [1.0]
    info["tips"] = {}
    for s in ("r", "l"):  # the finger tips: the arm's farthest pixel past the wrist
        WR, EL = _P(J, s + "_wr"), _P(J, s + "_el")
        d = (WR - EL) / np.linalg.norm(WR - EL)
        ys, xs = np.nonzero(masks["arm_" + s])
        info["tips"][s] = (WR + d * ((np.dstack([xs, ys])[0] - WR) @ d).max()).tolist()
    col, lw = ink(base, A, info["neck"][0])
    g = max(6, int(round(o["grid"] * H)))
    pieces, parts = {}, []
    yy, xx = np.mgrid[0 : A.shape[0], 0 : A.shape[1]]
    hand_out, sockets = {}, {}
    if hands is not None:
        # each hand a piece of its own, cut at the wrist: open, and every shape drawn
        info["hands"] = True
        for s in ("r", "l"):
            WR, EL = _P(J, s + "_wr"), _P(J, s + "_el")
            d = (WR - EL) / np.linalg.norm(WR - EL)
            t = (xx - WR[0]) * d[0] + (yy - WR[1]) * d[1]
            across = masks["arm_" + s] & (np.abs(t) < 1.5)
            ov = max(4.0, 0.3 * across.sum() / 3)  # the hand laps over the forearm's end
            r = 0.62 * np.linalg.norm(WR - EL)
            c = WR + 0.35 * (WR - EL)
            box = (np.abs(xx - c[0]) < r) & (np.abs(yy - c[1]) < r)
            shapes = {"open": base}
            shapes.update((hands or {}).get(s) or {})
            for sh, pic in shapes.items():
                m = (pic[..., 3] > 8) & (t > -ov) & box
                if sh == "open":
                    m &= masks["arm_" + s]
                m = (
                    _component(m, [WR + d * 2])
                    if m[int(WR[1] + d[1] * 2), int(WR[0] + d[0] * 2)]
                    else m
                )
                if m.sum() < 50:
                    continue
                ys, xs = np.nonzero(m)
                x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
                im = pic[y0:y1, x0:x1].copy()
                im[..., 3] = np.where(m[y0:y1, x0:x1], im[..., 3], 0)
                # the hand fades in over the overlap, so the two drawings' outlines blend at the
                # wrist (a hard edge left a step where the redrawn hand was a hair wider)
                fade = np.clip((t[y0:y1, x0:x1] + ov) / max(ov, 1.0), 0, 1)
                im[..., 3] = (im[..., 3] * fade * fade * (3 - 2 * fade)).astype(np.uint8)
                if sh == "grip":
                    # the model draws something in the gripping hand (a black stick): what is dark and
                    # thicker than the drawing's own outline is it. It takes the held prop's handle
                    # colour, inside its own outline, so a handle end shows out of the fist; the
                    # prop's handle runs on from it (removing it left a hole the sky showed through)
                    px = im[..., :3].astype(int)
                    dark = (
                        (px.mean(2) < 95) & (px.max(2) - px.min(2) < 40) & (im[..., 3] > 8)
                    ).astype(np.uint8)
                    kr = int(2 * lw + 3)
                    stick = cv2.morphologyEx(
                        dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kr, kr))
                    )
                    core = cv2.erode(stick, np.ones((int(lw) + 1, int(lw) + 1), np.uint8)) > 0
                    held = [v for v in (props or {}).values() if v[1].get("hand", "r") == s]
                    if held and core.any():
                        pim = held[0][0]
                        ys2, xs2 = np.nonzero(pim[..., 3] > 8)
                        tail = pim[ys2.max() - max(4, (ys2.max() - ys2.min()) // 8) : ys2.max(), :]
                        tc = np.median(tail[..., :3][tail[..., 3] > 128], 0)
                        im[..., :3][core] = tc.astype(np.uint8)
                    hole = np.nonzero(stick)
                    if len(hole[0]) > 20:
                        # the prop's handle starts where the stick does, at the wrist end
                        hy, hx = hole[0] + y0, hole[1] + x0
                        along = (hx - WR[0]) * d[0] + (hy - WR[1]) * d[1]
                        k = along <= np.percentile(along, 3)
                        sockets[s] = [float(hx[k].mean()), float(hy[k].mean())]
                pid = "hand:%s:%s" % (s, sh)
                pieces[pid] = im
                hand_out.setdefault(s, {})[sh] = {"piece": pid, "x": int(x0), "y": int(y0)}
            # the forearm runs on under the hand's faded edge, so its outline never breaks
            masks["arm_" + s] = masks["arm_" + s] & (t <= 0.6 * ov)
    for name in ORDER:
        src, mpart = base, masks[name]
        if name == "torso":
            # the neck goes on under the head; a strip of shirt under each sleeve, inked on its far
            # edge (hidden while the arm is down, the shirt's side when it lifts)
            src = base.copy()
            mpart = mpart | (masks["head"] & (yy >= info["neck"][0] - max(6, int(0.006 * H))))
            for s in ("r", "l"):
                pit, top = (np.array(v) for v in cuts["arm_" + s])
                ab = top - pit
                nrm = np.array([-ab[1], ab[0]]) / np.linalg.norm(ab)
                mid = (pit + top) / 2
                if masks["torso"][int(mid[1] + nrm[1] * 6), int(mid[0] + nrm[0] * 6)]:
                    nrm = -nrm
                d = (xx - pit[0]) * nrm[0] + (yy - pit[1]) * nrm[1]
                u = ((xx - pit[0]) * ab[0] + (yy - pit[1]) * ab[1]) / (ab @ ab)
                mpart = mpart | ((d >= -1) & (d <= lw + 1) & (u >= 0) & (u <= 1) & A)
                off = nrm * (lw / 2 + 0.5)
                cv2.line(
                    src,
                    tuple(int(round(v)) for v in (pit + off) * 4),
                    tuple(int(round(v)) for v in (top + off) * 4),
                    tuple(col) + (255,),
                    max(1, int(round(lw))),
                    cv2.LINE_AA,
                    shift=2,
                )
        V, T = grid_mesh(mpart, g)
        x0, y0 = int(np.floor(V[:, 0].min())) - 2, int(np.floor(V[:, 1].min())) - 2
        x1, y1 = int(np.ceil(V[:, 0].max())) + 3, int(np.ceil(V[:, 1].max())) + 3
        im = _crop(src, x0, y0, x1, y1)
        im[..., 3] = np.where(_crop(mpart.astype(np.uint8), x0, y0, x1, y1) > 0, im[..., 3], 0)
        pieces["part:" + name] = im
        parts.append(
            {"name": name, "box": [x0, y0], "V": V, "T": T, "W": weights(name, V, J, info, o)}
        )
    # the face patches stay on the head: nothing of them below the neck
    headm = cv2.dilate(masks["head"].astype(np.uint8), np.ones((5, 5), np.uint8))
    spots = {}
    for F in faces.values():
        for e in [F] + list((F.get("mouths") or {}).values()) + [F.get("blink") or {}]:
            if e.get("piece"):
                spots[e["piece"]] = (int(e["x"]), int(e["y"]))
    for pid, im in patches.items():
        im = im.copy()
        if pid in spots:
            x, y = spots[pid]
            hm = _crop(headm, x, y, x + im.shape[1], y + im.shape[0])
            im[..., 3] = np.where(hm > 0, im[..., 3], 0)
        pieces[pid] = im
    out_props = {}
    for name, (im, spec) in (props or {}).items():
        a = im[..., 3] > 8
        ys, xs = np.nonzero(a)
        im = im[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        k = float(spec.get("length", 0.19)) * H / im.shape[0]
        im = cv2.resize(
            im,
            (max(1, int(im.shape[1] * k)), max(1, int(im.shape[0] * k))),
            interpolation=cv2.INTER_AREA,
        )
        pieces["prop:" + name] = im
        side = spec.get("hand", "r")
        WR, TIP = _P(J, side + "_wr"), np.array(info["tips"][side])
        out_props[name] = {
            "bone": "hand_" + side,
            "at": sockets[side]  # through the grip's hole when it has one, else in the palm
            if side in sockets
            else (WR + float(spec.get("palm", 0.4)) * (TIP - WR)).round(1).tolist(),
            "grip": [im.shape[1] / 2, im.shape[0] * (1 - float(spec.get("grip", 0.18)))],
            "angle": float(spec.get("angle", 180)),
            "w": int(im.shape[1]),
            "h": int(im.shape[0]),
        }
    j2 = {k: [float(v[0]), float(v[1])] for k, v in J.items()}
    neck_c = [(info["neck"][1] + info["neck"][2]) / 2, info["neck"][0]]
    hips_c = (_P(J, "r_hip") + _P(J, "l_hip")) / 2
    waist = hips_c + o["waist"] * ((_P(J, "r_sh") + _P(J, "l_sh")) / 2 - hips_c)
    fig = _actor.figure(base[..., 3])
    bones = {
        "root": {"parent": None, "pivot": [float(fig["feet"][0]), float(fig["feet"][1])]},
        "pelvis": {"parent": "root", "pivot": hips_c.tolist()},
        "chest": {"parent": "pelvis", "pivot": waist.tolist()},
        "head": {"parent": "chest", "pivot": neck_c},
    }
    for s in ("r", "l"):
        for a, b, parent, p0, p1 in (
            ("arm", "up", "chest", "_sh", "_el"),
            ("arm", "lo", "arm_%s_up" % s, "_el", "_wr"),
            ("leg", "up", "pelvis", "_hip", "_kn"),
            ("leg", "lo", "leg_%s_up" % s, "_kn", "_an"),
        ):
            bones["%s_%s_%s" % (a, s, b)] = {
                "parent": parent,
                "pivot": j2[s + p0],
                "end": j2[s + p1],
            }
        bones["hand_" + s] = {
            "parent": "arm_%s_lo" % s,
            "pivot": j2[s + "_wr"],
            "end": info["tips"][s],
        }
        bones["foot_" + s] = {
            "parent": "leg_%s_lo" % s,
            "pivot": j2[s + "_an"],
            "end": j2[s + "_toe"],
        }
    over = _actor.on_white(base).copy()
    tints = [
        (60, 60, 230),
        (60, 200, 60),
        (230, 120, 40),
        (200, 40, 200),
        (40, 200, 230),
        (120, 120, 120),
    ]
    for c, name in zip(tints, ORDER):
        m = masks[name]
        over[m] = (0.6 * over[m] + 0.4 * np.array(c)).astype(np.uint8)
    for a, b in cuts.values():
        cv2.line(over, tuple(int(v) for v in a), tuple(int(v) for v in b), (0, 0, 0), 3)
    for x, y, *_ in J.values():
        cv2.circle(over, (int(x), int(y)), 6, (0, 0, 255), -1)
    # which way it faces: 0 the viewer, 1 the right of the picture, -1 the left. A turned figure's
    # nose sits off the middle of its shoulders (Enrique's three-quarter view: 0.14 of the
    # shoulders' width; his front view: 0.01). The player draws the far arm behind the body and
    # bends both knees the way it faces
    sh_w = abs(J["l_sh"][0] - J["r_sh"][0]) or 1.0
    off = (_P(J, "nose")[0] - (J["l_sh"][0] + J["r_sh"][0]) / 2) / sh_w
    facing = o.get("facing", 0 if abs(off) < 0.07 else (1 if off > 0 else -1))
    puppet = {
        "v": 1,
        "facing": facing,
        "figure": {"height": H, "feet": fig["feet"], "box": fig["box"]},
        "bones": bones,
        "parts": parts,
        "faces": faces,
        "props": out_props,
        "hands": hand_out,
        "joints": j2,
        "chin": [neck_c[0], neck_c[1] - 0.025 * H],
        "ink": col,
        "lw": lw,
    }
    return puppet, pieces, over


def finish(puppet, where, sizes):
    """puppet.json's own form: the parts' meshes with their atlas UVs, and every other piece's
    rectangle on its page."""
    np, _ = _np()
    parts = []
    for p in puppet["parts"]:
        wh = where["part:" + p["name"]]
        pw, ph = sizes[wh["p"]]
        V = p["V"]
        uv = np.stack(
            [(wh["sx"] + V[:, 0] - p["box"][0]) / pw, (wh["sy"] + V[:, 1] - p["box"][1]) / ph], 1
        )
        parts.append({
            "name": p["name"], "page": wh["p"],
            "v": V.round(2).flatten().tolist(), "uv": uv.round(6).flatten().tolist(),
            "t": p["T"].flatten().tolist(), "w": p["W"],
        })  # fmt: skip
    rects = {
        k: {
            **v,
            "u0": v["sx"] / sizes[v["p"]][0],
            "v0": v["sy"] / sizes[v["p"]][1],
            "u1": (v["sx"] + v["w"]) / sizes[v["p"]][0],
            "v1": (v["sy"] + v["h"]) / sizes[v["p"]][1],
        }
        for k, v in where.items()
        if not k.startswith("part:")
    }
    return {**puppet, "parts": parts, "rects": rects}
