"""Actor packs: the measuring, cutting and packing half (no network, no image model).

A pack is one character drawn by an image model, cut so a film can animate it by swapping pieces:
the figure, a patch for each face it pulls, a patch for each mouth shape on the faces that talk,
a blink, and whole-figure poses. actor-pack.py draws the pictures; this module lays every redraw
back on the picture it was redrawn from, measures how far it strayed outside the head, cuts the
part that changed, finds the head in each pose, and packs every piece into one atlas.

Pictures are BGRA uint8 arrays throughout (OpenCV's order).

Not an entry script: imported by actor-pack.py and check-actors.py after `_env`.
"""

import cv2
import numpy as np

WHITE = (255, 255, 255)


# ---------------------------------------------------------------------------- pictures
def load_rgba(path, key_tol=26):
    """A picture as BGRA. One with real alpha keeps it; one without has its plain ground keyed out
    (a flood from the border, so a white shirt inside the outline stays)."""
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        return None
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.shape[2] == 4 and im[..., 3].min() < 250:
        return clean_alpha(im)
    bgr = im[..., :3]
    return np.dstack([bgr, key_out(bgr, key_tol)])


def key_out(bgr, tol=26):
    """Alpha for a subject on a plain ground: the ground is what a flood from the border reaches
    through pixels near the border's own colour; specks smaller than 1 % of the subject go too."""
    h, w = bgr.shape[:2]
    border = np.concatenate([bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]])
    ground = np.median(border, axis=0).astype(np.int16)
    near = (np.abs(bgr.astype(np.int16) - ground).max(axis=2) <= tol).astype(np.uint8)
    mask = np.zeros((h + 2, w + 2), np.uint8)
    seeds = [(x, 0) for x in range(0, w, 16)] + [(x, h - 1) for x in range(0, w, 16)]
    seeds += [(0, y) for y in range(0, h, 16)] + [(w - 1, y) for y in range(0, h, 16)]
    for x, y in seeds:
        if near[y, x] == 1:
            cv2.floodFill(near, mask, (x, y), 2)
    alpha = np.where(near == 2, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(drop_specks(alpha), (3, 3), 0.7)


def drop_specks(alpha, share=0.01):
    n, lab, st, _ = cv2.connectedComponentsWithStats((alpha > 127).astype(np.uint8), 8)
    if n <= 1:
        return alpha
    big = st[1:, cv2.CC_STAT_AREA].max()
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= share * big
    return np.where(
        keep[lab] | (alpha <= 127) & (alpha > 0) & dilate(keep[lab], 3), alpha, 0
    ).astype(np.uint8)


def clean_alpha(rgba):
    """A model's own alpha, with its stray semi-transparent specks dropped."""
    out = rgba.copy()
    out[..., 3] = drop_specks(rgba[..., 3])
    return out


def dilate(mask, r):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(mask.astype(np.uint8), k).astype(bool)


def on_white(rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * a + 255 * (1 - a)).astype(np.uint8)


def resize_to(rgba, shape):
    if rgba.shape[:2] == shape[:2]:
        return rgba
    return cv2.resize(rgba, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------- the figure
def figure(alpha, head_share=0.30, pad=24):
    """Where the figure is in its picture: {box (x0, y0, x1, y1) with a margin, feet (x, y), height,
    head (x0, y0, x1, y1)}. The head is the top `head_share` of the figure, as wide as the figure
    is there, grown by 4 % of its height; it is found from this picture alone, never from a
    redraw's change, so a model that redraws everything cannot widen its own allowance."""
    ys, xs = np.nonzero(alpha > 127)
    if not len(xs):
        return None
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    H, W = alpha.shape[:2]
    height = y1 - y0
    band = alpha[y0 : int(y0 + head_share * height)] > 127
    cols = np.nonzero(band.any(axis=0))[0]
    g = 0.04 * height
    head = [cols.min() - g, y0 - g, cols.max() + g, y0 + head_share * height + g]
    head = [int(max(0, head[0])), int(max(0, head[1])), int(min(W, head[2])), int(min(H, head[3]))]
    box = [max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad + 1), min(H, y1 + pad + 1)]
    bottom = np.nonzero(alpha[y1 - max(2, height // 60) : y1 + 1] > 127)[1]
    feet = [int((bottom.min() + bottom.max()) / 2), y1]
    return {
        "box": box,
        "feet": feet,
        "height": height,
        "head": head,
        "area": int((alpha > 127).sum()),
    }


def box_mask(shape, b):
    m = np.zeros(shape[:2], bool)
    m[b[1] : b[3], b[0] : b[2]] = True
    return m


# ---------------------------------------------------------------------------- registration
def changed(a, b):
    """Where two BGRA pictures of the same size differ, both laid on white: their alphas may come
    from different places (the model's own, or keyed off white), and comparing those would count
    an edge's antialiasing as a change. Blurred a little first so a line redrawn a pixel over is
    not a change."""
    d = np.abs(on_white(a).astype(np.float32) - on_white(b).astype(np.float32)).mean(axis=2)
    d = cv2.GaussianBlur(d, (0, 0), 2.0)
    m = (d > 28).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)


def fits(ref, var, ignore=None, width=768):
    """Every way to lay `var` on `ref`: a phase-correlation shift, and an affine (scale, a little
    rotation) refined from it by ECC on a `width`-px copy, fitted on everything but `ignore` (the
    head: the part an edit is allowed to change). Yields (aligned BGRA, {fit, shift, scale, sure})."""
    H, W = ref.shape[:2]
    k = width / W

    def small(im):
        g = cv2.cvtColor(on_white(im), cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, (width, int(H * k))).astype(np.float32) / 255
        return cv2.GaussianBlur(g, (0, 0), 1.2)

    a, b = small(ref), small(var)
    mask = None
    if ignore is not None:
        mask = np.full(a.shape, 255, np.uint8)
        x0, y0, x1, y1 = (int(v * k) for v in ignore)
        mask[max(0, y0) : y1, max(0, x0) : x1] = 0
    win = cv2.createHanningWindow(a.shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(a, b, win)
    shift = np.float32([[1, 0, dx], [0, 1, dy]])
    tries = [(shift, float(resp), "shift")]
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    try:
        cc, warp = cv2.findTransformECC(a, b, shift.copy(), cv2.MOTION_AFFINE, crit, mask, 5)
        tries.append((warp, float(cc), "affine"))
    except cv2.error:
        pass
    for warp, sure, how in tries:
        full = warp.copy()
        full[:, 2] /= k
        flags = cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP
        im = cv2.warpAffine(var, full, (W, H), flags=flags, borderValue=(255, 255, 255, 0))
        scale = float(np.sqrt(abs(np.linalg.det(full[:, :2]))))
        info = {"fit": how, "shift": [round(float(full[0, 2]), 1), round(float(full[1, 2]), 1)]}
        info.update(scale=round(scale, 4), sure=round(sure, 3))
        yield im, info


def register(ref, var, head, area):
    """`var` (a redraw of `ref` with its head changed) laid on `ref` by whichever fit leaves the
    least change outside the head. Returns (aligned, change mask, {fit..., changed, drift}):
    drift is the change outside the head as a share of the figure's area."""
    var = resize_to(var, ref.shape)
    near = box_mask(ref.shape, head)
    best = None
    for im, info in fits(ref, var, head):
        m = changed(ref, im)
        out = int((m & ~near).sum())
        if best is None or out < best[0]:
            best = (out, im, m, info)
    out, im, m, info = best
    info.update(changed=round(float(m.sum()) / area, 4), drift=round(out / area, 4))
    return im, m, info


# ---------------------------------------------------------------------------- cutting
def patch(var, mask, within, grow, feather):
    """The part of `var` under `mask` (inside the box `within`), grown by `grow` px with its holes
    closed and its edge feathered over `feather` px. Returns (x, y, BGRA) or None."""
    m = mask & box_mask(var.shape, within)
    if not m.any():
        return None
    m = dilate(m, grow).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    m &= box_mask(var.shape, within).astype(np.uint8)
    soft = np.clip(
        cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(1.0, feather / 2)) * 1.4, 0, 1
    )
    soft *= var[..., 3].astype(np.float32) / 255
    ys, xs = np.nonzero(soft > 0.01)
    if not len(xs):
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    out = var[y0:y1, x0:x1].copy()
    out[..., 3] = (soft[y0:y1, x0:x1] * 255).astype(np.uint8)
    return int(x0), int(y0), out


def over(dst, src, x, y):
    """Lay BGRA `src` on BGRA `dst` at (x, y), in place (straight alpha)."""
    h, w = src.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(dst.shape[1], x + w), min(dst.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return dst
    s = src[y0 - y : y1 - y, x0 - x : x1 - x].astype(np.float32)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    sa, da = s[..., 3:4] / 255, d[..., 3:4] / 255
    oa = sa + da * (1 - sa)
    rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    dst[y0:y1, x0:x1] = np.dstack([rgb, oa * 255]).clip(0, 255).astype(np.uint8)
    return dst


# ---------------------------------------------------------------------------- poses
def find_head(base, head, pose, scales=(0.8, 1.25, 19)):
    """Where the base's head is in a pose picture, at what scale: (scale, (x, y) of the head box's
    top-left in the pose, score 0..1). A score near 1 means the same face looking out of the
    picture, so the front mouths can be laid on it; a turned head scores low."""
    tpl = cv2.cvtColor(on_white(base[head[1] : head[3], head[0] : head[2]]), cv2.COLOR_BGR2GRAY)
    img = cv2.cvtColor(on_white(pose), cv2.COLOR_BGR2GRAY)
    best = (1.0, (0, 0), -1.0)
    for s in np.linspace(*scales):
        t = cv2.resize(tpl, (max(8, int(tpl.shape[1] * s)), max(8, int(tpl.shape[0] * s))))
        if t.shape[0] >= img.shape[0] or t.shape[1] >= img.shape[1]:
            continue
        r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        _, v, _, loc = cv2.minMaxLoc(r)
        if v > best[2]:
            best = (float(s), (int(loc[0]), int(loc[1])), float(v))
    return best


def same_character(base, pose):
    """How alike two figures' colours are (0..1): a cheap check that a pose is still the same
    character (a model that ignores its reference draws somebody else)."""
    hs = []
    for im in (base, pose):
        hsv = cv2.cvtColor(im[..., :3], cv2.COLOR_BGR2HSV)
        m = (im[..., 3] > 127).astype(np.uint8)
        h = cv2.calcHist([hsv], [0, 1], m, [24, 16], [0, 180, 0, 256])
        hs.append(cv2.normalize(h, h).flatten())
    return float(cv2.compareHist(hs[0], hs[1], cv2.HISTCMP_CORREL))


# ---------------------------------------------------------------------------- packing
def pack_atlas(pieces, page=4096, gap=4):
    """Shelf-pack {id: BGRA} into pages of `page` px. Returns ([page BGRA...], {id: {p, sx, sy,
    w, h}}). Tallest first; a piece wider or taller than a page is refused."""
    order = sorted(pieces, key=lambda k: (-pieces[k].shape[0], -pieces[k].shape[1]))
    pages, where, shelves = [], {}, []
    for k in order:
        h, w = pieces[k].shape[:2]
        if w + 2 * gap > page or h + 2 * gap > page:
            raise ValueError("piece %s (%dx%d) does not fit a %d px page" % (k, w, h, page))
        placed = None
        for sh in shelves:  # [page, y, height, x]
            if h + gap <= sh[2] and sh[3] + w + gap <= page:
                placed = (sh[0], sh[3], sh[1])
                sh[3] += w + gap
                break
        if placed is None:
            used = {}
            for sh in shelves:
                used[sh[0]] = max(used.get(sh[0], 0), sh[1] + sh[2])
            p = next((i for i in range(len(pages)) if used.get(i, 0) + h + gap <= page), None)
            if p is None:
                pages.append(None)
                p = len(pages) - 1
            y = used.get(p, gap)
            shelves.append([p, y, h + gap, gap + w + gap])
            placed = (p, gap, y)
        p, x, y = placed
        where[k] = {"p": p, "sx": int(x), "sy": int(y), "w": int(w), "h": int(h)}
    out = []
    for i in range(len(pages)):
        hh = max(v["sy"] + v["h"] for v in where.values() if v["p"] == i) + gap
        ww = max(v["sx"] + v["w"] for v in where.values() if v["p"] == i) + gap
        out.append(np.zeros((hh, ww, 4), np.uint8))
    for k, v in where.items():
        out[v["p"]][v["sy"] : v["sy"] + v["h"], v["sx"] : v["sx"] + v["w"]] = pieces[k]
    return out, where


# ---------------------------------------------------------------------------- films
def film_actors(m, rel):
    """{name: (pack dict, folder)} for a sketch manifest's "actors" -- {"enrique": "actors/enrique"}
    or {"enrique": {"pack": "actors/enrique"}}: each a folder actor-pack.py wrote. `rel` resolves
    a path against the manifest (_sketch.rel). One not packed yet is left out with a warning."""
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415
    import sys  # noqa: PLC0415

    out = {}
    for name, spec in (m.get("actors") or {}).items():
        d = rel(m, spec if isinstance(spec, str) else spec.get("pack") or "actors/" + name)
        p = os.path.join(d, "pack.json")
        if not os.path.exists(p):
            print(
                "  WARNING actor %r has no pack (%s): python scripts/actor-pack.py --spec <its spec>"
                % (name, p),
                file=sys.stderr,
            )
            continue
        with open(p, encoding="utf-8") as f:
            out[name] = (json.load(f), d)
    return out


def film_script(m, rel):
    """The <script> that hands the packs to sketch/actors.js ("" for a film without actors)."""
    import json  # noqa: PLC0415

    body = {n: P for n, (P, _) in film_actors(m, rel).items()}
    if not body:
        return ""
    return "<script>\nSK.ACTORS = %s;\n</script>" % json.dumps(body, separators=(",", ":"))


def film_images(m, rel):
    """{'actor:<name>:<n>': atlas page path} for the page's image loader."""
    import os  # noqa: PLC0415

    return {
        "actor:%s:%d" % (n, i): os.path.join(d, pg)
        for n, (P, d) in film_actors(m, rel).items()
        for i, pg in enumerate(P["pages"])
    }
