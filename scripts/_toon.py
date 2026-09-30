"""Toon rigs: a real person's photo redrawn as a character (a toy brick figure, a voxel game
character, a newspaper stipple portrait, a caricature, a clay puppet), made to talk by swapping
mouth shapes -- no video model, no warping of anyone's face.

An image model (config/heads/looks.json: OpenRouter, the photo as its reference picture) draws
the character from the photo, then draws it again with one change each: the mouth a little open,
open, rounded, and the eyes shut. The edits come back aligned to within a pixel, so only the
changed part of each is kept: the mouth (or the eyes) found by MediaPipe's landmarks on the
character, the change measured inside a window round it, grown and feathered into a patch. The
film draws the character and lays the right mouth patch over it on each frame (sketch/heads.js).

The photo leaves the machine: it goes to the image model through OpenRouter. Everything is
cached in the rig folder by the photo, the look's prompts and the model, so a rebuild is free
unless one of them changes; plan() prices a build before anything is spent.

Not an entry script: imported by head-rig.py after `_env`.
"""

import os
import json
import time
import base64
import hashlib
from importlib import import_module

import numpy as np
import cv2

import _env

LOOKS = "config/heads/looks.json"
TOON_VERSION = (
    2  # bump when the patches or the rig change: the pictures are reused, the rig rebuilt
)
USD_EACH = 0.022  # measured 2026-09-30: gpt-image-2.5-flare, 1024x1024, medium, one reference
MOUTHS = ("small", "open", "round")


def looks():
    with open(_env.resolve(LOOKS), encoding="utf-8") as f:
        return json.load(f)


def prompts(look, cfg=None):
    """{"base": ..., "small": ..., ...}: every picture a look's rig is drawn from."""
    cfg = cfg or looks()
    if look not in cfg["looks"]:
        raise SystemExit("look %r is not one of: %s" % (look, ", ".join(cfg["looks"])))
    out = {"base": cfg["looks"][look] + cfg["likeness"] + cfg["front"]}
    for k, change in cfg["variants"].items():
        out[k] = cfg["edit"].replace("{change}", change)
    return out


def key(photo_fp, look, cfg=None):
    """What a picture depends on: the photo, its prompt, the model."""
    cfg = cfg or looks()
    ps = prompts(look, cfg)
    return {
        k: hashlib.sha1(
            json.dumps([photo_fp, ps["base"], ps[k], cfg["model"], cfg["quality"]]).encode(),
            usedforsecurity=False,
        ).hexdigest()[:12]
        for k in ps
    }


def plan(photo_fp, look, rdir):
    """(pictures to draw, dollars) for a build; nothing is spent."""
    got = _state(rdir)
    want = key(photo_fp, look)
    todo = [k for k, h in want.items() if got.get(k) != h or not os.path.exists(_pic(rdir, k))]
    if "base" in todo:  # every variant is an edit of the base: a new base redraws them all
        todo = list(want)
    return todo, round(len(todo) * USD_EACH, 3)


def _pic(rdir, k):
    return os.path.join(rdir, "gen_%s.png" % k)


def _state(rdir):
    p = os.path.join(rdir, "toon.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("keys", {})
    return {}


def draw(prompt, ref, out):
    """One picture from the look's image model, `ref` (a PNG) as its reference. Returns cost."""
    import httpx

    cfg = looks()
    paint = import_module("sketch-paint")
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        raise SystemExit("OPENROUTER_API_KEY is not set (put it in .env)")
    caps = paint.model_caps(cfg["model"])
    body = {
        "model": cfg["model"],
        "prompt": prompt,
        **paint.pick_params(caps, cfg["quality"], "1:1", True),
    }
    with open(ref, "rb") as f:
        url = "data:image/png;base64," + base64.b64encode(f.read()).decode()
    body["input_references"] = [{"type": "image_url", "image_url": {"url": url}}]
    for attempt in range(4):
        try:
            r = httpx.post(
                paint.OPENROUTER + "/images",
                headers={"Authorization": "Bearer " + k, "X-Title": "kitcut"},
                json=body,
                timeout=300,
            )
        except httpx.HTTPError as e:  # a dropped or timed-out connection: try again
            if attempt == 3:
                raise SystemExit("image model unreachable: %s" % e) from None
            time.sleep(5 * (attempt + 1))
            continue
        # busy, or a refusal by the model's safety filter, which is not repeatable: the same
        # edit of the same character was refused once and drawn on the next try
        refused = r.status_code == 400 and "safety" in r.text.lower()
        if (r.status_code in (429, 500, 502, 503) or refused) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        break
    j = r.json()
    if r.status_code != 200:
        why = str(j.get("error", j))
        if "safety" in why.lower():  # the model's own filter: a famous face, a bare shoulder
            raise SystemExit(
                "the image model refused to draw %s (its safety filter)" % os.path.basename(out)
            )
        raise SystemExit("image model %s: %s" % (r.status_code, why[:300]))
    d = j["data"][0]
    data = base64.b64decode(d["b64_json"]) if d.get("b64_json") else httpx.get(d["url"]).content
    with open(out + ".part", "wb") as f:
        f.write(data)
    os.replace(out + ".part", out)
    return (j.get("usage") or {}).get("cost") or USD_EACH


def generate(ref_png, photo_fp, look, rdir, jobs=5):
    """Draw whatever plan() says is missing: the base first, then its edits at once."""
    from concurrent.futures import ThreadPoolExecutor

    todo, _ = plan(photo_fp, look, rdir)
    if not todo:
        return 0.0
    ps, want, spent = prompts(look), key(photo_fp, look), 0.0
    state = _state(rdir)
    if "base" in todo:
        spent += draw(ps["base"], ref_png, _pic(rdir, "base"))
        state["base"] = want["base"]
        todo = [k for k in todo if k != "base"]
    with ThreadPoolExecutor(max(1, min(jobs, len(todo) or 1))) as ex:
        costs = list(ex.map(lambda k: draw(ps[k], _pic(rdir, "base"), _pic(rdir, k)), todo))
    spent += sum(costs)
    for k in todo:
        state[k] = want[k]
    with open(os.path.join(rdir, "toon.json"), "w", encoding="utf-8") as f:
        json.dump({"look": look, "keys": state}, f, indent=1)
    return spent


# ------------------------------------------------------------------ patches
def _rgba(path):
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGRA)
    elif im.shape[2] == 3:
        im = np.dstack([im, np.full(im.shape[:2], 255, np.uint8)])
    return im


def landmarks(ms, rgba):
    """478 points on a drawn character, or None: tried as drawn, then softened (a stipple or a
    hatch portrait reads to the landmarker as noise until its dots are blurred into tones)."""
    rgb = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2RGB)
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = (rgb * a + 235 * (1 - a)).astype(np.uint8)
    for blur in (0, 3, 6):
        img = cv2.GaussianBlur(rgb, (0, 0), blur) if blur else rgb
        P, _ = ms.landmarks(img)
        if P is not None:
            return P
    return None


def patch(base, var, centre, size, down=(0.0, 1.0)):
    """The part of `var` that differs from `base` round `centre`: an ellipse `size` (rx, ry)
    grown to take in the change measured inside a window twice its size, feathered. Returns
    (x, y, RGBA patch) in the base's pixels."""
    H, W = base.shape[:2]
    rx, ry = size
    x0, x1 = int(max(0, centre[0] - 2 * rx)), int(min(W, centre[0] + 2 * rx))
    y0, y1 = int(max(0, centre[1] - 2 * ry)), int(min(H, centre[1] + 2.4 * ry))
    fa = base[y0:y1, x0:x1, :3].astype(np.float32)
    fb = var[y0:y1, x0:x1, :3].astype(np.float32)
    d = cv2.GaussianBlur(np.abs(fa - fb).mean(axis=2), (0, 0), max(1.5, rx / 10))
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    ell = (((xx - centre[0]) / rx) ** 2 + ((yy - centre[1]) / ry) ** 2) <= 1
    thr = max(14.0, float(np.percentile(d, 70)) * 1.8)
    ch = (d > thr).astype(np.uint8)
    n, lab, _st, _ = cv2.connectedComponentsWithStats(ch, 8)
    keep = np.zeros_like(ch)
    for i in range(1, n):  # the change that touches the mouth (or the eye), not a stray dot
        if (ell & (lab == i)).any():
            keep |= (lab == i).astype(np.uint8)
    m = (keep | ell.astype(np.uint8)).astype(np.uint8)
    g = max(5, int(rx * 0.35)) | 1
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (g, g)))
    m = np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), g / 4) * 1.25, 0, 1)
    m *= np.minimum(base[y0:y1, x0:x1, 3], var[y0:y1, x0:x1, 3]).astype(np.float32) / 255
    ys, xs = np.nonzero(m > 0.01)
    if not len(xs):
        return None
    a0, a1, b0, b1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    out = var[y0:y1, x0:x1].copy()
    out[..., 3] = (m * 255).astype(np.uint8)
    return int(x0 + b0), int(y0 + a0), out[a0:a1, b0:b1]


def cut(ms, rdir):
    """Measure the drawn character and cut its mouth and blink patches. Returns (landmarks in
    the base's pixels, {variant: {file, x, y, w, h}})."""
    rig = import_module("head-rig")
    base = _rgba(_pic(rdir, "base"))
    P = landmarks(ms, base)
    if P is None:
        raise SystemExit("%s: no face found on the drawn character" % rdir)
    mw = float(np.linalg.norm(P[291] - P[61]))
    mouth = (P[13] + P[14]) / 2
    out = {}
    for k in MOUTHS:
        if not os.path.exists(_pic(rdir, k)):
            continue
        got = patch(base, _rgba(_pic(rdir, k)), mouth + [0, mw * 0.18], (mw * 0.75, mw * 0.62))
        if got:
            x, y, p = got
            cv2.imwrite(os.path.join(rdir, "mouth_%s.png" % k), p)
            out[k] = {
                "file": "mouth_%s.png" % k,
                "x": int(x),
                "y": int(y),
                "w": p.shape[1],
                "h": p.shape[0],
            }
    if os.path.exists(_pic(rdir, "blink")):
        var = _rgba(_pic(rdir, "blink"))
        pieces = []
        for up in (rig.EYE_L_UP, rig.EYE_R_UP):
            c = P[up].mean(axis=0)
            ew = float(np.linalg.norm(P[up[-1]] - P[up[0]]))
            got = patch(base, var, c - [0, ew * 0.1], (ew * 0.8, ew * 0.55))
            if got:
                pieces.append(got)
        if pieces:  # both eyes in one patch, the space between them left as the base has it
            x0 = min(p[0] for p in pieces)
            y0 = min(p[1] for p in pieces)
            x1 = max(p[0] + p[2].shape[1] for p in pieces)
            y1 = max(p[1] + p[2].shape[0] for p in pieces)
            both = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
            for x, y, p in pieces:
                region = both[y - y0 : y - y0 + p.shape[0], x - x0 : x - x0 + p.shape[1]]
                take = p[..., 3:4] > region[..., 3:4]
                region[:] = np.where(take, p, region)
            cv2.imwrite(os.path.join(rdir, "blink.png"), both)
            out["blink"] = {
                "file": "blink.png",
                "x": int(x0),
                "y": int(y0),
                "w": int(x1 - x0),
                "h": int(y1 - y0),
            }
    return P, out
