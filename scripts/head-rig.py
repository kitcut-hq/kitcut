#!/usr/bin/env python
"""Turn a photo of a person into a talking-head rig for a sketch film (sketch/heads.js).

A rig is a photo measured once, so the film engine can make the face in it talk as a pure
function of t. It is a folder:

    rig.json    where everything is, in the photo's pixels: the face outline, the lips (inner
                and outer, upper and lower), the eyes and lids, the brows, the irises, the
                jaw piece each mouth style cuts, and a mesh over the face with what each point
                does when the jaw opens, the lips spread or pucker, and the eyes blink
    photo.jpg   the photo, at most 1600 px on its long side (the styles that keep the photo)
    head.png    the head alone -- hair and face, cut off at the jaw line, the background
                transparent (the cut-out and bobble-head styles)
    sheet.png   (--sheet) a proof: the cut-out on a check board, the jaw pieces, the mesh

Everything runs on the CPU and nothing leaves the machine: OpenCV's YuNet finds the face
(small faces in big frames too), MediaPipe's face landmarker puts 478 points on it, and
MediaPipe's multiclass selfie segmenter separates hair, face skin, body skin, clothes and
background. The head is hair + face skin (+ anything worn on the head), kept only where it
touches the face, cut at the jaw line, and its edge snapped to the photo's own edges.

Models (downloaded once by --fetch-models into models/heads/; YuNet is models/face/, the
same file shot-detect uses): face_landmarker.task (Apache-2.0) and
selfie_multiclass_256x256.tflite (Apache-2.0).

A manifest names its rigs in "heads": {"alex": {"photo": "sources/alex.png"}, ...}; the
rigs are built into rigs/<name>/ beside it and rebuilt only when the photo or this script's
RIG_VERSION changes. `--list` says which would be built without building anything.

Invoke as:
    python scripts/head-rig.py --fetch-models
    python scripts/head-rig.py --photo projects/<id>/sources/alex.png --name alex --out projects/<id>/rigs --sheet
    python scripts/head-rig.py --manifest projects/<id>/sketch.json --list
    python scripts/head-rig.py --manifest projects/<id>/sketch.json
"""

import sys
import os
import json
import time
import types
import hashlib
import argparse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402

RIG_VERSION = 1  # bump when the rig format or the geometry changes: every rig is rebuilt
MODELS = {
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task",
    "selfie_multiclass_256x256.tflite": "https://storage.googleapis.com/mediapipe-models/"
    "image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
}
YUNET = "models/face/face_detection_yunet_2023mar.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
    "face_detection_yunet_2023mar.onnx"
)
PHOTO_MAX = 1600  # the photo texture's long side
CROP_MAX = 1536  # the head is cut from a square crop at most this big (native pixels if fewer)

# MediaPipe face-mesh indices. "L"/"R" here are IMAGE sides: the subject's right eye is on the
# image's left. Every lip run goes from the image-left corner to the image-right corner.
OVAL = [
    10,
    338,
    297,
    332,
    284,
    251,
    389,
    356,
    454,
    323,
    361,
    288,
    397,
    365,
    379,
    378,
    400,
    377,
    152,
    148,
    176,
    149,
    150,
    136,
    172,
    58,
    132,
    93,
    234,
    127,
    162,
    21,
    54,
    103,
    67,
    109,
]
LIP_OU = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291]  # outer, upper
LIP_OL = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291]  # outer, lower
LIP_IU = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]  # inner, upper
LIP_IL = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]  # inner, lower
EYE_L_UP = [33, 246, 161, 160, 159, 158, 157, 173, 133]  # image-left eye, upper lid
EYE_L_LO = [33, 7, 163, 144, 145, 153, 154, 155, 133]
EYE_R_UP = [362, 398, 384, 385, 386, 387, 388, 466, 263]  # image-right eye
EYE_R_LO = [362, 382, 381, 380, 374, 373, 390, 249, 263]
BROW_L = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
BROW_R = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
IRIS_L, IRIS_R = [468, 469, 470, 471, 472], [473, 474, 475, 476, 477]
NOSE_TIP, TOP, CHIN = 1, 10, 152
# the jaw line from the image-left jaw angle round the chin to the image-right one
JAW_LINE = [132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361]
CHEEK_L, CHEEK_R = 234, 454
# segmenter classes
BG, HAIR, BODY, FACE, CLOTHES, OTHER = range(6)


# ------------------------------------------------------------------ models
def models_dir():
    return _env.resolve("models/heads")


def fetch_models():
    """Download the models that are missing; returns their paths."""
    os.makedirs(models_dir(), exist_ok=True)
    wanted = {os.path.join(models_dir(), k): u for k, u in MODELS.items()}
    wanted[_env.resolve(YUNET)] = YUNET_URL
    for path, url in wanted.items():
        if os.path.exists(path):
            print("  have  %s" % os.path.relpath(path, _env.ROOT))
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print("  fetch %s" % url)
        urllib.request.urlretrieve(url, path + ".part")
        os.replace(path + ".part", path)
    fetch_runtime()
    return wanted


# MediaPipe's wheel asks for opencv-contrib-python, which would fight the venv's opencv-python
# over the one cv2 package (and setup-python.ps1's pip-check repair would install it). So the
# runtime lives beside the models, installed --no-deps into models/heads/py by --fetch-models,
# and only this script puts it on sys.path; the venv and its pip check never see it.
MP_PINS = ["mediapipe==1.0.1", "absl-py==2.5.0", "flatbuffers==25.12.19"]


def runtime_dir():
    return os.path.join(models_dir(), "py")


def fetch_runtime():
    import subprocess

    if os.path.isdir(os.path.join(runtime_dir(), "mediapipe")):
        print("  have  %s" % os.path.relpath(runtime_dir(), _env.ROOT))
        return
    print("  install %s -> %s" % (" ".join(MP_PINS), os.path.relpath(runtime_dir(), _env.ROOT)))
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--no-deps",
        "--target",
        runtime_dir(),
    ]
    if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode:
        cmd = [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--python",
            sys.executable,
            "--target",
            runtime_dir(),
        ]
    subprocess.run(cmd + MP_PINS, check=True)


def _mediapipe():
    """MediaPipe's Tasks API, from models/heads/py. Its vision package imports matplotlib for
    drawing helpers this never calls; a missing matplotlib is stood in for."""
    if os.path.isdir(runtime_dir()) and runtime_dir() not in sys.path:
        sys.path.insert(0, runtime_dir())
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        for m in ("matplotlib", "matplotlib.pyplot"):
            sys.modules.setdefault(m, types.ModuleType(m))
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
    except ImportError as e:
        sys.exit("mediapipe is not installed (%s): run head-rig.py --fetch-models" % e)
    return mp, vision, BaseOptions


class Measurer:
    """The three models, loaded once for any number of photos."""

    def __init__(self):
        for k in MODELS:
            if not os.path.exists(os.path.join(models_dir(), k)):
                sys.exit("missing models/heads/%s: run head-rig.py --fetch-models" % k)
        if not os.path.exists(_env.resolve(YUNET)):
            sys.exit("missing %s: run head-rig.py --fetch-models" % YUNET)
        self.mp, vision, Base = _mediapipe()
        self.lm = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=Base(
                    model_asset_path=os.path.join(models_dir(), "face_landmarker.task")
                ),
                output_face_blendshapes=True,
                num_faces=1,
            )
        )
        self.seg = vision.ImageSegmenter.create_from_options(
            vision.ImageSegmenterOptions(
                base_options=Base(
                    model_asset_path=os.path.join(models_dir(), "selfie_multiclass_256x256.tflite")
                ),
                output_confidence_masks=True,
                output_category_mask=False,
            )
        )

    def close(self):
        """Close the MediaPipe tasks now: left to the interpreter's shutdown, their __del__
        runs after ctypes is gone and prints a TypeError per task."""
        for task in (self.lm, self.seg):
            try:
                task.close()
            except Exception:  # noqa: BLE001 -- best effort on the way out
                pass

    def image(self, rgb):
        return self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))

    def faces(self, rgb):
        """YuNet boxes [(x, y, w, h, score)], biggest first, in rgb's pixels."""
        h, w = rgb.shape[:2]
        k = min(1.0, 1280 / max(h, w))
        small = cv2.resize(rgb, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
        det = cv2.FaceDetectorYN_create(
            _env.resolve(YUNET), "", (small.shape[1], small.shape[0]), 0.6
        )
        _, found = det.detect(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
        boxes = [] if found is None else [tuple(f[:4] / k) + (float(f[14]),) for f in found]
        return sorted(boxes, key=lambda b: -b[2] * b[3])

    def landmarks(self, rgb):
        """478 points in rgb's pixels and the blendshape scores, or (None, None)."""
        r = self.lm.detect(self.image(rgb))
        if not r.face_landmarks:
            return None, None
        h, w = rgb.shape[:2]
        pts = np.array([[p.x * w, p.y * h] for p in r.face_landmarks[0]], np.float64)
        bs = {c.category_name: float(c.score) for c in r.face_blendshapes[0]}
        return pts, bs

    def classes(self, rgb):
        """(6, h, w) float32 class confidences."""
        r = self.seg.segment(self.image(rgb))
        return np.stack([m.numpy_view().astype(np.float32).squeeze() for m in r.confidence_masks])


# ------------------------------------------------------------------ image helpers
def load_photo(path):
    """RGBA uint8, EXIF orientation applied (a phone photo stands the right way up)."""
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(path))
    return np.array(im.convert("RGBA"))


def flatten(rgba, bg=(255, 255, 255)):
    """RGB with any transparency laid over bg (a cut-out still has a face to find)."""
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * a + np.array(bg, np.float32) * (1 - a)).astype(np.uint8)


def resize_max(img, n, interp=cv2.INTER_AREA):
    h, w = img.shape[:2]
    k = min(1.0, n / max(h, w))
    if k >= 1:
        return img, 1.0
    return cv2.resize(img, (round(w * k), round(h * k)), interpolation=interp), k


def guided(I, p, r, eps):
    """He et al.'s guided filter: p's edges moved onto I's (both float32, 0..1)."""
    box = lambda x: cv2.blur(x, (2 * r + 1, 2 * r + 1))  # noqa: E731
    mI, mp = box(I), box(p)
    a = (box(I * p) - mI * mp) / (box(I * I) - mI * mI + eps)
    b = mp - a * mI
    return box(a) * I + box(b)


def poly_mask(shape, pts, blur=0):
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 255)
    m = m.astype(np.float32) / 255
    if blur:
        m = cv2.GaussianBlur(m, (0, 0), blur)
    return m


def hexcol(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


def fingerprint(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read(), usedforsecurity=False).hexdigest()[:12]


# ------------------------------------------------------------------ geometry
def frame(P):
    """The face's own axes: origin between the lips, `right` along the mouth, `down` to the
    chin, and its width (cheek to cheek) and height (hairline to chin)."""
    o = (P[13] + P[14]) / 2
    right = P[291] - P[61]
    right /= np.linalg.norm(right)
    down = np.array([-right[1], right[0]])
    if np.dot(P[CHIN] - o, down) < 0:
        down = -down
    W = np.linalg.norm(P[CHEEK_R] - P[CHEEK_L])
    H = np.linalg.norm(P[CHIN] - P[TOP])
    return o, right, down, W, H


def ray_hit(o, d, poly):
    """First crossing of the ray o + s*d (s > 0) with an open polyline, else None."""
    best = None
    for a, b in zip(poly[:-1], poly[1:]):
        e = b - a
        m = np.array([[d[0], -e[0]], [d[1], -e[1]]])
        if abs(np.linalg.det(m)) < 1e-9:
            continue
        s, u = np.linalg.solve(m, a - o)
        if s > 0 and 0 <= u <= 1 and (best is None or s < best[0]):
            best = (s, o + s * d)
    return None if best is None else best[1]


def lower_oval(P, side):
    """The face outline from the cheek down to the chin, on one image side."""
    i0, i1 = OVAL.index(CHEEK_L if side < 0 else CHEEK_R), OVAL.index(CHIN)
    idx = OVAL[i1 : i0 + 1][::-1] if side < 0 else OVAL[i0 : i1 + 1]
    return P[idx]


def cuts(P, fr):
    """The jaw pieces the rigid mouth styles move, as closed polygons, plus the line each one
    is cut along (what the film fills with the mouth's dark when the piece moves).
      chin  -- the lower face below the lips, cut out along the marionette lines to the jaw
               outline: a puppet's jaw
      dummy -- two slits straight down from the mouth corners: a ventriloquist's dummy
      flap  -- the whole head split across at the lips (the cut runs past the face on both
               sides): the top of the head hinges up, South Park's Canadians"""
    o, right, down, W, H = fr
    out = {}
    lo_l, lo_r = lower_oval(P, -1), lower_oval(P, 1)
    # chin: from each outer corner, outwards and a little down, to the jaw outline
    ends = []
    for side, corner, oval in ((-1, P[61], lo_l), (1, P[291], lo_r)):
        d = side * right * np.cos(0.35) + down * np.sin(0.35)
        hit = ray_hit(corner, d, oval)
        ends.append(hit if hit is not None else corner + d * W * 0.3)
    top = np.vstack([ends[0], P[61], P[LIP_IL], P[291], ends[1]])

    # down the right side of the outline from the cut to the chin and up the left side
    def along(oval, p):
        k = int(np.argmin(np.linalg.norm(oval - p, axis=1)))
        return oval[k:]

    r_run = along(lo_r, ends[1])
    l_run = along(lo_l, ends[0])[::-1]
    out["chin"] = {"poly": np.vstack([top, r_run, l_run]), "cut": top}
    # dummy: straight down from the corners to the outline
    slits = []
    for side, corner, oval in ((-1, P[61], lo_l), (1, P[291], lo_r)):
        hit = ray_hit(corner + down * 1e-3, down + side * right * 0.12, oval)
        slits.append(hit if hit is not None else corner + down * H * 0.3)
    chin_run = [p for p in P[OVAL] if np.dot(p - o, down) > 0]  # the outline below the lips
    chin_run = np.array(sorted(chin_run, key=lambda p: np.dot(p - o, right)))
    inner = chin_run[
        (np.dot(chin_run - o, right) > np.dot(slits[0] - o, right))
        & (np.dot(chin_run - o, right) < np.dot(slits[1] - o, right))
    ]
    top_d = np.vstack([P[61], P[LIP_IL], P[291]])
    out["dummy"] = {
        "poly": np.vstack([top_d, slits[1], inner[::-1], slits[0]]),
        "cut": top_d,
        "slits": [np.vstack([P[61], slits[0]]), np.vstack([P[291], slits[1]])],
    }
    # flap: the lip line carried straight out past both sides of the head
    far = W * 1.4
    line = np.vstack([P[61] - right * far, P[61], P[LIP_IL], P[291], P[291] + right * far])
    out["flap"] = {"cut": line}
    return out


def mesh(P, fr, eye_gap):
    """A triangle mesh over the face and what each point does:
      wj  0..1   how far it follows the jaw (the lower lip and the chin all the way, the
                 cheeks less, nothing above the mouth line or at the edge of the face)
      wu  0..1   how far it follows the upper lip's small lift
      wc  -1..1  how far it moves along `right` when the lips spread (+) or pucker (-)
      b   [dx,dy] where it goes when the eye it belongs to shuts (photo pixels)
    The inner mouth is a hole (no triangle spans the lips), so the film can draw the dark of
    the mouth under the mesh; a ring of still points round the face ends the warp."""
    from scipy.spatial import Delaunay

    o, right, down, W, H = fr
    face = P[:468]
    ring = []
    c = (P[TOP] + P[CHIN]) / 2
    for a in np.linspace(0, 2 * np.pi, 40, endpoint=False):
        v = np.cos(a) * right * W * 0.78 + np.sin(a) * down * H * 0.72
        ring.append(c + v)
    pts = np.vstack([face, np.array(ring)])
    n_face = len(face)
    tri = Delaunay(pts).simplices
    rel = pts - o
    u = rel @ right / (W / 2)
    v = rel @ down / H
    um = np.linalg.norm(P[291] - P[61]) / W  # half the mouth, in the same units as u
    g = np.cos(np.clip(np.abs(u) / 0.95, 0, 1) * np.pi / 2) ** 2
    vcut = np.where(np.abs(u) < um, 0.0, (np.abs(u) - um) * 0.25)
    sig = 0.015 + 0.09 * np.clip((np.abs(u) - um) / (1 - um), 0, 1)
    s = np.clip((v - vcut) / (2 * sig) + 0.5, 0, 1)
    s = s * s * (3 - 2 * s)
    lower_lip = set(LIP_IL[1:-1]) | set(LIP_OL[1:-1])
    upper_lip = set(LIP_IU[1:-1]) | set(LIP_OU[1:-1])
    corners = {61, 291, 78, 308}
    for i in range(n_face):
        if i in lower_lip:
            s[i] = 1.0
        elif i in upper_lip:
            s[i] = 0.0
        elif i in corners:
            s[i] = 0.5
    # the mouth is a hole: no triangle may join a point that stays with the skull to one that
    # goes with the jaw between the mouth corners -- every lip ring counts, not just the inner
    # one (a triangle from the upper lip to the lower lip's middle ring smears lip across the
    # opening and hides the teeth); outside the corners the cheek is one skin and stretches
    upper, lower = set(LIP_IU[1:-1]), set(LIP_IL[1:-1])
    keep = []
    for t in tri:
        t = [int(i) for i in t]
        st = s[t]
        cu, cv = u[t].mean(), v[t].mean()
        if set(t) & upper and set(t) & lower:
            continue
        if st.min() < 0.25 and st.max() > 0.75 and abs(cu) < um * 1.05 and abs(cv) < 0.12:
            continue
        keep.append(t)
    wj = g * s
    wu = np.zeros(len(pts))
    for i in upper_lip:
        wu[i] = np.cos(np.clip(abs(u[i]) / um, 0, 1) * np.pi / 2) ** 2 * (
            1.0 if i in LIP_IU else 0.6
        )
    wc = np.sign(u) * np.exp(-(((np.abs(u) - um) / 0.16) ** 2)) * np.exp(-((v / 0.07) ** 2))
    b = np.zeros((len(pts), 2))
    for up, lo in ((EYE_L_UP, EYE_L_LO), (EYE_R_UP, EYE_R_LO)):
        lid = P[lo]
        for i in up[1:-1]:
            # straight down onto the lower lid, stopping a hair above it
            hit = ray_hit(P[i] - down * 1e-3, down, lid)
            if hit is None:
                hit = lid[int(np.argmin(np.linalg.norm(lid - P[i], axis=1)))]
            b[i] = (hit - P[i]) * 0.94
        # the skin above the lid follows it part of the way; the lower lid rises a little
        centre = P[up].mean(axis=0)
        span = np.linalg.norm(P[up[-1]] - P[up[0]])
        for i in range(n_face):
            if i in up or i in lo:
                continue
            d = pts[i] - centre
            if np.linalg.norm(d) > span * 0.9 or np.dot(d, down) > 0:
                continue
            j = up[1:-1][int(np.argmin(np.linalg.norm(P[up[1:-1]] - pts[i], axis=1)))]
            fall = max(0.0, 1 - np.linalg.norm(pts[i] - P[j]) / (span * 0.55))
            b[i] = b[j] * 0.45 * fall
        for i in lo[1:-1]:
            b[i] = -down * eye_gap * 0.08
    wj[n_face:] = wu[n_face:] = wc[n_face:] = 0
    b[n_face:] = 0
    return {"p": pts, "t": keep, "wj": wj, "wu": wu, "wc": wc, "b": b}


# ------------------------------------------------------------------ the rig
def build(ms, photo_path, name, out_dir, face_index=0):
    """Measure one photo and write its rig folder. Returns the rig dict."""
    t0 = time.time()
    rgba = load_photo(photo_path)
    rgba, _ = resize_max(rgba, max(PHOTO_MAX, CROP_MAX * 2))
    rgb = flatten(rgba)
    boxes = ms.faces(rgb)
    if not boxes:
        raise SystemExit("%s: no face found" % photo_path)
    if face_index >= len(boxes):
        raise SystemExit("%s: %d face(s), no index %d" % (photo_path, len(boxes), face_index))
    x, y, w, h, score = boxes[face_index]
    # a square crop round the face with room for hair: the segmenter works at 256 px, so the
    # head must fill a good part of what it sees
    side = int(round(max(w, h) * 3.1))
    cx, cy = x + w / 2, y + h / 2 - h * 0.12
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    pad = (
        (max(0, -y0), max(0, y0 + side - rgb.shape[0])),
        (max(0, -x0), max(0, x0 + side - rgb.shape[1])),
    )
    big = np.pad(rgba, pad + ((0, 0),), mode="edge")
    crop = big[y0 + pad[0][0] : y0 + pad[0][0] + side, x0 + pad[1][0] : x0 + pad[1][0] + side]
    S = min(side, CROP_MAX)
    crop = cv2.resize(crop, (S, S), interpolation=cv2.INTER_AREA if S < side else cv2.INTER_CUBIC)
    crop_rgb = flatten(crop)
    k = side / S  # photo px per crop px
    P_c, blend = ms.landmarks(crop_rgb)
    if P_c is None:
        raise SystemExit("%s: the landmarker found no face in the crop" % photo_path)
    cls = ms.classes(crop_rgb)
    # --- the head: hair + face skin + things worn, touching the face, above the jaw line
    fr_c = frame(P_c)
    o_c, right_c, down_c, W_c, H_c = fr_c
    oval_c = P_c[OVAL]
    face_poly = poly_mask(crop.shape, oval_c)
    # hair and things worn only where a head can be: an ellipse round the face (wide enough for
    # a bun or an afro), and beside the neck below it for long hair. A painted backdrop or a
    # grey studio wall the segmenter calls hair ends at its edge instead of joining the head.
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    mid_c = (P_c[TOP] + P_c[CHIN]) / 2
    uu = ((xx - mid_c[0]) * right_c[0] + (yy - mid_c[1]) * right_c[1]) / W_c
    vv = ((xx - mid_c[0]) * down_c[0] + (yy - mid_c[1]) * down_c[1]) / H_c
    ell = (uu / 1.02) ** 2 + ((vv + 0.12) / 0.98) ** 2
    prior = np.clip((1.18 - ell) / 0.18, 0, 1)
    prior = np.maximum(prior, ((vv > 0.25) & (vv < 1.25) & (np.abs(uu) < 1.0)).astype(np.float32))
    # "other" (a hat, a wig's curls, a headband) is kept anywhere inside the prior: tried only
    # next to hair and face, it took an engraved wig's curls off to drop a patch of backdrop
    # from one painting -- the worse trade
    prob = (cls[HAIR] + cls[OTHER] * 0.9) * prior + cls[FACE]
    prob = np.maximum(prob, face_poly)
    # nothing below the jaw line: the outline from one jaw angle round the chin to the other,
    # pushed a little down, then carried outwards and downwards (not level -- that would take
    # the ears off)
    jaw = P_c[JAW_LINE] + down_c * H_c * 0.012
    far = W_c * 3
    out_l = -right_c * 0.8 + down_c * 0.6
    out_r = right_c * 0.8 + down_c * 0.6
    below_poly = np.vstack(
        [
            jaw,
            jaw[-1] + out_r * far,
            jaw[-1] + out_r * far + down_c * far * 2,
            jaw[0] + out_l * far + down_c * far * 2,
            jaw[0] + out_l * far,
        ]
    )
    below = poly_mask(crop.shape, below_poly, blur=1.5)
    # long hair may hang below the jaw beside the neck; skin and clothes may not
    prob = prob * (1 - below) + cls[HAIR] * below
    if crop.shape[2] == 4:  # a cut-out already: its own alpha bounds the head
        prob = np.minimum(prob, crop[..., 3].astype(np.float32) / 255)
    m = (prob > 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    seed = lab[
        np.round(P_c[[1, 168, 13]]).astype(int)[:, 1].clip(0, S - 1),
        np.round(P_c[[1, 168, 13]]).astype(int)[:, 0].clip(0, S - 1),
    ]
    keep_labels = {int(s) for s in seed if s > 0}
    m = np.isin(lab, list(keep_labels)).astype(np.uint8) if keep_labels else m
    # close pinholes, fill holes (an eye the segmenter called background is still a face)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    inv = (1 - m).astype(np.uint8)
    n2, lab2, stats2, _ = cv2.connectedComponentsWithStats(inv, 4)
    for i in range(1, n2):
        x_, y_, w_, h_, a_ = stats2[i]
        if x_ > 0 and y_ > 0 and x_ + w_ < S and y_ + h_ < S and a_ < S * S * 0.02:
            m[lab2 == i] = 1
    gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    alpha = guided(gray, m.astype(np.float32), max(2, S // 170), 1e-3)
    alpha = np.clip((alpha - 0.5) * 1.6 + 0.5, 0, 1)
    alpha = alpha * (1 - below * (1 - cls[HAIR]))  # the jaw line stays a clean cut
    if crop.shape[2] == 4:
        alpha = np.minimum(alpha, crop[..., 3].astype(np.float32) / 255)
    # the flap cut: the lip line carried out from each mouth corner to the head's own edge
    flap_ends = []
    for side, corner in ((-1, P_c[61]), (1, P_c[291])):
        p, step = corner.copy(), side * right_c * max(1.0, S / 800)
        for _ in range(4 * S):
            q = p + step
            xi, yi = int(round(q[0])), int(round(q[1]))
            if not (0 <= xi < S and 0 <= yi < S) or alpha[yi, xi] < 0.35:
                break
            p = q
        flap_ends.append(p + side * right_c * W_c * 0.01)
    ys, xs = np.nonzero(alpha > 0.02)
    if not len(xs):
        raise SystemExit("%s: nothing left of the head after segmentation" % photo_path)
    mgn = int(S * 0.01)
    hx0, hy0 = max(0, xs.min() - mgn), max(0, ys.min() - mgn)
    hx1, hy1 = min(S, xs.max() + mgn + 1), min(S, ys.max() + mgn + 1)
    head = np.dstack([crop_rgb, (alpha * 255).astype(np.uint8)])[hy0:hy1, hx0:hx1]
    # --- the photo texture and every coordinate in its pixels
    photo, kp = resize_max(rgba, PHOTO_MAX)
    to_photo = lambda q: ((q * k) + [x0, y0]) * kp  # noqa: E731 -- crop px -> photo px
    P = to_photo(P_c)
    fr = frame(P)
    o, right, down, W, H = fr
    eye_gap = float(np.mean([np.linalg.norm(P[159] - P[145]), np.linalg.norm(P[386] - P[374])]))
    c = cuts(P, fr)
    # the flap's cut ends where the head does, so its mouth never opens past the silhouette
    fl, fr_end = to_photo(flap_ends[0]), to_photo(flap_ends[1])
    c["flap"]["cut"] = np.vstack([fl, P[61], P[LIP_IL], P[291], fr_end])
    ms_ = mesh(P, fr, eye_gap)

    # colours for what the film draws itself: the inside of the mouth, lids
    def sample(poly, img=photo):
        mm = poly_mask(img.shape, poly) > 0.5
        px = img[..., :3][mm]
        return np.median(px, axis=0) if len(px) else np.array([128, 100, 90])

    cheek = np.vstack([P[117], P[118], P[101], P[36], P[205], P[187]])
    cheek2 = np.vstack([P[346], P[347], P[330], P[266], P[425], P[411]])
    skin = (sample(cheek) + sample(cheek2)) / 2
    lip = sample(np.vstack([P[LIP_OL], P[LIP_IL][::-1]]))
    brow = sample(np.vstack([P[BROW_L]]))
    iris_l = np.append(P[IRIS_L[0]], np.linalg.norm(P[IRIS_L[1]] - P[IRIS_L[3]]) / 2)
    iris_r = np.append(P[IRIS_R[0]], np.linalg.norm(P[IRIS_R[1]] - P[IRIS_R[3]]) / 2)
    gap = float(np.mean(np.linalg.norm(P[LIP_IL] - P[LIP_IU], axis=1)))
    r2 = lambda a: np.round(np.asarray(a, np.float64), 1).tolist()  # noqa: E731
    rig = {
        "v": RIG_VERSION,
        "name": name,
        "src": os.path.relpath(_env.resolve(photo_path), out_dir).replace("\\", "/"),
        "fingerprint": fingerprint(_env.resolve(photo_path)),
        "photo": {"file": "photo.jpg", "w": photo.shape[1], "h": photo.shape[0]},
        # head.png's pixel (0,0) sits at (x, y) in the photo, s photo px per head px
        "head": {
            "file": "head.png",
            "w": head.shape[1],
            "h": head.shape[0],
            "x": round(float((x0 + hx0 * k) * kp), 2),
            "y": round(float((y0 + hy0 * k) * kp), 2),
            "s": round(float(k * kp), 5),
        },
        "face": {
            "o": r2(o),
            "right": np.round(right, 5).tolist(),
            "down": np.round(down, 5).tolist(),
            "w": round(float(W), 1),
            "h": round(float(H), 1),
            "roll": round(float(np.degrees(np.arctan2(right[1], right[0]))), 2),
            "mouth_w": round(float(np.linalg.norm(P[291] - P[61])), 1),
            "lip_gap": round(gap, 2),
            "eye_gap": round(eye_gap, 2),
            "score": round(float(score), 3),
        },
        "lm": {
            "oval": r2(P[OVAL]),
            "lipOU": r2(P[LIP_OU]),
            "lipOL": r2(P[LIP_OL]),
            "lipIU": r2(P[LIP_IU]),
            "lipIL": r2(P[LIP_IL]),
            "eyeL": {"up": r2(P[EYE_L_UP]), "lo": r2(P[EYE_L_LO])},
            "eyeR": {"up": r2(P[EYE_R_UP]), "lo": r2(P[EYE_R_LO])},
            "browL": r2(P[BROW_L]),
            "browR": r2(P[BROW_R]),
            "irisL": r2(iris_l),
            "irisR": r2(iris_r),
            "nose": r2(P[NOSE_TIP]),
            "top": r2(P[TOP]),
            "chin": r2(P[CHIN]),
        },
        "cut": {
            "chin": {"poly": r2(c["chin"]["poly"]), "cut": r2(c["chin"]["cut"])},
            "dummy": {
                "poly": r2(c["dummy"]["poly"]),
                "cut": r2(c["dummy"]["cut"]),
                "slits": [r2(s) for s in c["dummy"]["slits"]],
            },
            "flap": {"cut": r2(c["flap"]["cut"])},
        },
        "mesh": {
            "p": r2(ms_["p"]),
            "t": ms_["t"],
            "wj": np.round(ms_["wj"], 3).tolist(),
            "wu": np.round(ms_["wu"], 3).tolist(),
            "wc": np.round(ms_["wc"], 3).tolist(),
            "b": r2(ms_["b"]),
        },
        "rest": {
            k_: round(blend.get(k_, 0.0), 3)
            for k_ in (
                "jawOpen",
                "mouthClose",
                "mouthSmileLeft",
                "mouthSmileRight",
                "eyeBlinkLeft",
                "eyeBlinkRight",
            )
        },
        "col": {"skin": hexcol(skin), "lip": hexcol(lip), "brow": hexcol(brow)},
    }
    os.makedirs(out_dir, exist_ok=True)
    cv2.imwrite(
        os.path.join(out_dir, "photo.jpg"),
        cv2.cvtColor(flatten(photo), cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, 92],
    )
    cv2.imwrite(os.path.join(out_dir, "head.png"), cv2.cvtColor(head, cv2.COLOR_RGBA2BGRA))
    with open(os.path.join(out_dir, "rig.json"), "w", encoding="utf-8") as f:
        json.dump(rig, f, separators=(",", ":"))
    rig["_secs"] = round(time.time() - t0, 2)
    return rig


# ------------------------------------------------------------------ proof sheet
def sheet(rig, out_dir, path):
    """The cut-out on a check board beside the photo with the jaw pieces and the mesh drawn."""
    photo = cv2.imread(os.path.join(out_dir, "photo.jpg"))
    head = cv2.imread(os.path.join(out_dir, "head.png"), cv2.IMREAD_UNCHANGED)
    # zoom the photo on the face so the lines are readable
    f = rig["face"]
    o = np.array(f["o"])
    half = max(f["w"], f["h"]) * 0.95
    x0, y0 = int(max(0, o[0] - half)), int(max(0, o[1] - half * 1.25))
    x1, y1 = int(min(photo.shape[1], o[0] + half)), int(min(photo.shape[0], o[1] + half * 0.75))
    zoom = 900 / max(x1 - x0, y1 - y0)

    def pt(q):
        return (int(round((q[0] - x0) * zoom)), int(round((q[1] - y0) * zoom)))

    def panel(draw):
        im = cv2.resize(photo[y0:y1, x0:x1], None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
        draw(im)
        return im

    def lines(im):
        for key, col in (("chin", (0, 200, 255)), ("dummy", (255, 80, 200))):
            poly = np.array([pt(q) for q in rig["cut"][key]["poly"]], np.int32)
            cv2.polylines(im, [poly], True, col, 2, cv2.LINE_AA)
        flap = np.array([pt(q) for q in rig["cut"]["flap"]["cut"]], np.int32)
        cv2.polylines(im, [flap], False, (80, 255, 80), 1, cv2.LINE_AA)
        for key in ("lipIU", "lipIL"):
            cv2.polylines(
                im,
                [np.array([pt(q) for q in rig["lm"][key]], np.int32)],
                False,
                (0, 0, 255),
                1,
                cv2.LINE_AA,
            )
        for e in ("eyeL", "eyeR"):
            for lid in ("up", "lo"):
                cv2.polylines(
                    im,
                    [np.array([pt(q) for q in rig["lm"][e][lid]], np.int32)],
                    False,
                    (255, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

    def meshdraw(im):
        m = rig["mesh"]
        p = np.array(m["p"])
        wj = np.array(m["wj"])
        for t in m["t"]:
            q = np.array([pt(p[i]) for i in t], np.int32)
            w = wj[t].mean()
            col = (int(255 * (1 - w)), int(120 * (1 - w)), int(255 * w))
            cv2.polylines(im, [q], True, col, 1, cv2.LINE_AA)
        for i in range(len(p)):
            b = m["b"][i]
            if b[0] or b[1]:
                a = pt(p[i])
                cv2.arrowedLine(
                    im, a, pt(p[i] + np.array(b)), (0, 255, 0), 1, cv2.LINE_AA, tipLength=0.3
                )

    a = panel(lines)
    b = panel(meshdraw)
    # the cut-out on a checker board, scaled to the same height
    hh = a.shape[0]
    hk = hh / head.shape[0]
    hd = cv2.resize(head, (max(1, int(head.shape[1] * hk)), hh), interpolation=cv2.INTER_AREA)
    yy, xx = np.mgrid[: hd.shape[0], : hd.shape[1]]
    board = (
        np.where(((yy // 24 + xx // 24) % 2)[..., None] == 0, 210, 150)
        .astype(np.uint8)
        .repeat(3, 2)
    )
    al = hd[..., 3:4].astype(np.float32) / 255
    c = (hd[..., :3] * al + board * (1 - al)).astype(np.uint8)
    out = np.hstack([c, a, b])
    cv2.imwrite(path, out)
    return path


# ------------------------------------------------------------------ manifest mode
def manifest_heads(mpath):
    with open(_env.resolve(mpath), encoding="utf-8") as f:
        m = json.load(f)
    d = os.path.dirname(_env.resolve(mpath))
    heads = m.get("heads") or {}
    out = []
    for name, spec in heads.items():
        if isinstance(spec, str):
            spec = {"photo": spec}
        photo = spec["photo"] if os.path.isabs(spec["photo"]) else os.path.join(d, spec["photo"])
        rdir = os.path.join(d, spec.get("rig") or os.path.join("rigs", name))
        out.append((name, photo, rdir, int(spec.get("face", 0))))
    return out


def stale(photo, rdir):
    """Why a rig needs building, or '' when the one on disk is current."""
    p = os.path.join(rdir, "rig.json")
    if not os.path.exists(p):
        return "missing"
    try:
        with open(p, encoding="utf-8") as f:
            r = json.load(f)
    except (OSError, ValueError):
        return "unreadable"
    if r.get("v") != RIG_VERSION:
        return "rig format v%s -> v%d" % (r.get("v"), RIG_VERSION)
    if not os.path.exists(photo):
        return "photo missing: %s" % photo
    if r.get("fingerprint") != fingerprint(photo):
        return "photo changed"
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--photo", help="one photo to rig")
    ap.add_argument("--name", help="the rig's name (with --photo)")
    ap.add_argument("--out", help="folder the rig folder goes in (with --photo)")
    ap.add_argument("--face", type=int, default=0, help="which face, biggest first (default 0)")
    ap.add_argument("--manifest", help='a sketch manifest: build every rig its "heads" names')
    ap.add_argument("--list", action="store_true", help="say which rigs would be built; build none")
    ap.add_argument("--force", action="store_true", help="rebuild rigs that are current")
    ap.add_argument("--sheet", action="store_true", help="also write sheet.png, a proof of the cut")
    ap.add_argument("--fetch-models", action="store_true", help="download the models and stop")
    a = ap.parse_args()
    if a.fetch_models:
        fetch_models()
        return
    if a.manifest:
        jobs = manifest_heads(a.manifest)
    elif a.photo and a.name and a.out:
        jobs = [(a.name, _env.resolve(a.photo), os.path.join(_env.resolve(a.out), a.name), a.face)]
    else:
        ap.error("give --manifest, or --photo with --name and --out")
    todo = []
    for name, photo, rdir, face in jobs:
        why = "forced" if a.force else stale(photo, rdir)
        print("  %-12s %-28s %s" % (name, why or "current", os.path.relpath(photo, _env.ROOT)))
        if why:
            todo.append((name, photo, rdir, face))
    if a.list or not todo:
        if a.list:
            print("\n  --list: nothing built")
        return
    ms = Measurer()
    for name, photo, rdir, face in todo:
        rig = build(ms, photo, name, rdir, face)
        f = rig["face"]
        print(
            "  %-12s face %dx%d px, roll %+.1f deg, lips %s (gap %.1f px), %d mesh triangles, %.1fs"
            % (
                name,
                f["w"],
                f["h"],
                f["roll"],
                "open" if f["lip_gap"] > f["h"] * 0.02 else "closed",
                f["lip_gap"],
                len(rig["mesh"]["t"]),
                rig["_secs"],
            )
        )
        if a.sheet:
            print("    sheet %s" % sheet(rig, rdir, os.path.join(rdir, "sheet.png")))
    ms.close()


if __name__ == "__main__":
    main()
