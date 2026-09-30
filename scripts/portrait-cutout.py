#!/usr/bin/env python
"""Cut people out of their photos: one transparent image per portrait, all framed alike.

A speaker carousel, a line-up of faces, a headshot on a card: each wants the person on their own
over the film's colour, at the same size as the person beside them. Headshots arrive with any
background and any crop (a conference site's are 1000 px squares, some cut at the chin, some at
the waist). This mattes each person off with a local BiRefNet ONNX model -- nothing leaves the
machine -- and optionally:

  --frame   rescales and re-centres every cut-out so the eyes sit at the same point and the face
            is the same width (YuNet finds the face). The photo's own bottom edge -- where the
            photographer's crop cut the body -- is faded out, and a photo cropped so tight that
            the edge would land above --floor is scaled up until it does not, and says so.
  --tone    mono: a black-and-white person (the colour stays in the film's own ground);
            duo:#dark,#light: a duotone, the person's greys mapped between two brand colours.

Writes <out>/<name>.webp (RGBA, lossless alpha) per photo and <out>/sheet.jpg, every cut-out on a
flat colour so a bad edge shows. A film names them in its manifest's "images" and draws them with
SK.image(name, ...) inside a clip.

Models (models/matting/, gitignored; the download commands are printed when one is missing):
  birefnet-lite       224 MB  BiRefNet swin-tiny, general subjects (the default)
  birefnet-portrait   973 MB  BiRefNet trained on portraits: twice the time, no better on headshots
Both run on the CPU through onnxruntime; --plan prices the run before anything is loaded.

Invoke as:
    python scripts/portrait-cutout.py --src <photos> --out <cut> --plan
    python scripts/portrait-cutout.py --src <photos> --out <cut> --frame --tone mono
      (<photos>: projects/<id>/sources/speakers; <cut>: projects/<id>/images/speakers)
    python scripts/portrait-cutout.py --src a.jpg b.jpg --out temp/cut --model birefnet-portrait
"""

import sys
import os
import glob
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

# name: (release file, MB, seconds a photo). The seconds were measured on the studio laptop's CPU
# (2026-09-30, four 1000 px headshots): 10.5 s lite, 18.9 s portrait. On those four, cut to 800 px
# and laid on magenta and teal, the two could not be told apart at the hair -- so lite is default.
MODELS = {
    "birefnet-lite": ("BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx", 224, 10.5),
    "birefnet-portrait": ("BiRefNet-portrait-epoch_150.onnx", 973, 18.9),
}
RELEASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
FACE_MODEL = "models/face/face_detection_yunet_2023mar.onnx"
# a photo is shrunk to this side first: the cut-out is 800 px, and a conference's 9552 x 6368 original
# asked YuNet for 974 MB and failed the film it was in (the Slush bake-off, 2026-09-30)
MAX_SIDE = 2400
EXTS = (".jpg", ".jpeg", ".png", ".webp")


def model_path(name):
    """Where a model lives: models/matting/<name>.onnx under the tooling root."""
    return os.path.join(_env.ROOT, "models", "matting", name + ".onnx")


def photos(src):
    """The photos named: files as given, folders expanded to their images in name order."""
    out = []
    for s in src:
        p = _env.resolve(s)
        if os.path.isdir(p):
            out += sorted(f for f in glob.glob(os.path.join(p, "*")) if f.lower().endswith(EXTS))
        elif os.path.exists(p):
            out.append(p)
        else:
            sys.exit("no such photo or folder: %s" % s)
    return out


class Matter:
    """BiRefNet: 1024x1024 RGB, ImageNet-normalised, NCHW in; logits of the person out."""

    SIZE = 1024

    def __init__(self, path, threads):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads  # set here: onnxruntime ignores the env vars (KI-024)
        self.sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name

    def alpha(self, rgb):
        """The person's matte for an RGB uint8 image, float 0..1 at the image's own size."""
        from PIL import Image

        h, w = rgb.shape[:2]
        x = np.asarray(Image.fromarray(rgb).resize((self.SIZE, self.SIZE), Image.BICUBIC))
        x = (x.astype(np.float32) / 255.0 - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        logits = self.sess.run(None, {self.inp: x})[0][0, 0]
        a = 1.0 / (1.0 + np.exp(-logits))
        a = np.asarray(
            Image.fromarray((a * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
            dtype=np.float32,
        )
        return np.clip(a / 255.0, 0, 1)


def face(rgb):
    """(eye centre x, y, face width) of the largest face, or None. YuNet, as shot-detect uses."""
    import cv2

    h, w = rgb.shape[:2]
    det = cv2.FaceDetectorYN_create(os.path.join(_env.ROOT, FACE_MODEL), "", (w, h), 0.6, 0.3, 5000)
    _, faces = det.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if faces is None or not len(faces):
        return None
    f = max(faces, key=lambda r: r[2] * r[3])
    ex, ey = (f[4] + f[6]) / 2, (f[5] + f[7]) / 2  # right eye, left eye
    return float(ex), float(ey), float(f[2])


def tone(rgb, spec):
    """mono: luminance (Rec. 709), a touch of contrast; duo:#a,#b: that luminance mapped a -> b."""
    if not spec:
        return rgb
    y = rgb.astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32) / 255.0
    y = np.clip((y - 0.5) * 1.12 + 0.5, 0, 1)  # the flat studio greys read as mud on a colour
    if spec == "mono":
        return (np.repeat(y[..., None], 3, axis=2) * 255).astype(np.uint8)
    a, b = (
        np.array([int(c[i : i + 2], 16) for i in (1, 3, 5)], np.float32)
        for c in spec[4:].split(",")
    )
    return (a + (b - a) * y[..., None]).clip(0, 255).astype(np.uint8)


def fade_bottom(rgba, frac=0.06):
    """Fade the alpha out over the photo's last `frac` of height: the body there was cut by the
    photographer's crop, and a hard horizontal edge inside a circle reads as a mistake."""
    h = rgba.shape[0]
    n = max(2, int(h * frac))
    ramp = np.ones(h, np.float32)
    ramp[h - n :] = np.linspace(1, 0, n) ** 1.5
    out = rgba.copy()
    out[..., 3] = (out[..., 3] * ramp[:, None]).astype(np.uint8)
    return out


def frame(rgba, fc, px, face_frac, eye_y, floor):
    """Scale and shift so the eyes land at (px/2, eye_y*px) and the face is face_frac*px wide.
    Returns (image, scale, note). A photo whose own (faded) bottom edge would land above
    floor*px is scaled up, about the eyes, until it lands there."""
    from PIL import Image

    h = rgba.shape[0]
    ex, ey, fw = fc
    s = face_frac * px / fw
    note = ""
    bottom = eye_y * px + (h - ey) * s  # where the photo's bottom edge would land
    if bottom < floor * px:
        s2 = (floor - eye_y) * px / (h - ey)
        note = "scaled x%.2f so the photo's cut edge lands at %.2f" % (s2 / s, floor)
        s = s2
    # output pixel (u, v) <- source (ex + (u - px/2)/s, ey + (v - eye_y*px)/s)
    inv = (1 / s, 0, ex - px / 2 / s, 0, 1 / s, ey - eye_y * px / s)
    im = Image.fromarray(rgba, "RGBA").transform((px, px), Image.AFFINE, inv, Image.BICUBIC)
    return np.asarray(im), s, note


def sheet(paths, out, bg="#3b4a8c"):
    """Every cut-out on one flat colour, a line at the eye height, so a bad edge shows."""
    from PIL import Image, ImageDraw

    n, cols, cell = len(paths), 6, 220
    rows = (n + cols - 1) // cols
    S = Image.new("RGB", (cols * cell, rows * (cell + 18)), bg)
    d = ImageDraw.Draw(S)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGBA").resize((cell, cell), Image.LANCZOS)
        x, y = (i % cols) * cell, (i // cols) * (cell + 18)
        S.paste(im, (x, y), im)
        d.line([(x, y + cell * 0.42), (x + cell, y + cell * 0.42)], fill="#ffffff55")
        d.text((x + 4, y + cell + 2), os.path.splitext(os.path.basename(p))[0][:30], fill="white")
    S.save(out, quality=90)


def main():
    """Parse, price, cut."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", nargs="+", required=True, help="photos, or folders of them")
    ap.add_argument("--out", required=True, help="folder for <name>.webp and sheet.jpg")
    ap.add_argument("--model", default="birefnet-lite", choices=sorted(MODELS))
    ap.add_argument("--frame", action="store_true", help="same eye line and face width in all")
    ap.add_argument("--px", type=int, default=800, help="with --frame: the square side (800)")
    ap.add_argument(
        "--face", type=float, default=0.30, help="with --frame: face width / side (0.30)"
    )
    ap.add_argument("--eyes", type=float, default=0.42, help="with --frame: eye line / side (0.42)")
    ap.add_argument(
        "--floor",
        type=float,
        default=0.85,
        help="with --frame: the photo's cut edge may not land above this fraction (0.85): below "
        "it, whatever covers a portrait's foot (a name card, the circle's edge) hides it",
    )
    ap.add_argument("--tone", help="mono, or duo:#rrggbb,#rrggbb (dark to light)")
    ap.add_argument("--threads", type=int, default=0, help="onnxruntime threads (0: all cores)")
    ap.add_argument("--plan", action="store_true", help="list and price the run; load nothing")
    args = ap.parse_args()

    if (
        args.tone
        and args.tone != "mono"
        and not (args.tone.startswith("duo:") and len(args.tone) == 19 and args.tone[4] == "#")
    ):
        sys.exit("--tone: mono, or duo:#rrggbb,#rrggbb")
    files = photos(args.src)
    out = _env.resolve(args.out)
    fname, mb, secs = MODELS[args.model]
    mp = model_path(args.model)
    print("%d photos -> %s" % (len(files), os.path.relpath(out, _env.ROOT)))
    print(
        "  model   %s (%d MB)%s"
        % (args.model, mb, "" if os.path.exists(mp) else "  MISSING -- see below")
    )
    print(
        "  frame   %s"
        % (
            "%d px, face %.2f, eyes at %.2f" % (args.px, args.face, args.eyes)
            if args.frame
            else "as shot"
        )
    )
    print("  tone    %s" % (args.tone or "as shot"))
    print("  cost    ~%.0f s of CPU, free (local model)" % (len(files) * secs))
    if not os.path.exists(mp):
        print(
            "\n  download it once (gitignored):\n    curl -L -o %s %s%s"
            % (os.path.relpath(mp, _env.ROOT), RELEASE, fname)
        )
        if not args.plan:
            sys.exit(1)
    if args.plan:
        for f in files:
            print("    %s" % os.path.relpath(f, _env.ROOT))
        print("\n  --plan: nothing cut")
        return

    from PIL import Image

    os.makedirs(out, exist_ok=True)
    matter = Matter(mp, args.threads or os.cpu_count() or 4)
    done, t0 = [], time.time()
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        im = Image.open(f).convert("RGB")
        im.thumbnail(
            (MAX_SIDE, MAX_SIDE), Image.LANCZOS
        )  # a 61 MP original ran YuNet out of memory
        rgb = np.asarray(im)
        t = time.time()
        a = matter.alpha(rgb)
        rgba = np.dstack([tone(rgb, args.tone), (a * 255).astype(np.uint8)])
        note = ""
        if args.frame:
            fc = face(rgb)
            if fc is None:
                note = "no face found: left as shot"
            else:
                rgba, _, note = frame(
                    fade_bottom(rgba), fc, args.px, args.face, args.eyes, args.floor
                )
        p = os.path.join(out, name + ".webp")
        Image.fromarray(rgba, "RGBA").save(p, lossless=False, quality=92, alpha_quality=100)
        done.append(p)
        print("  %-28s %4.1fs  %s" % (name, time.time() - t, note), flush=True)
    sheet(done, os.path.join(out, "sheet.jpg"))
    print(
        "%d cut-outs in %.0fs -> %s (sheet.jpg beside them)"
        % (len(done), time.time() - t0, os.path.relpath(out, _env.ROOT))
    )


if __name__ == "__main__":
    main()
