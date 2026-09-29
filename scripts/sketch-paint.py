#!/usr/bin/env python
"""Paint a sketch film's scenes with an image model: the pictures a film animates.

Reads the `paint` block of the manifest (inline, or a file: "paint": "paint.json"):

    "paint": {"backend": "muse", "style": "warm watercolour children's-book illustration",
              "images": [{"name": "kitchen", "prompt": "a little girl at the kitchen sink ..."},
                         {"name": "table", "prompt": "...", "ref": "kitchen"}],
              "max_images": 12}

Every image becomes images/<name>.jpg (a cut-out: .webp) next to the manifest, and joins the
manifest's images (_sketch.load does that), so film.js draws it with SK.image(name, x, y, w) (a
cut-out with SK.cutout). The style line goes
in front of every prompt, so the scenes share one look; the text-free, border-free suffix goes
behind (an image model letters signs and frames pictures unless told not to). A contact sheet of
all of them, images/sheet.jpg, is what to look at before animating.

Backends:
    openrouter  any image model OpenRouter serves ("model": "bytedance-seed/seedream-5-0-lite"),
            through its Image API (OPENROUTER_API_KEY). What each model takes -- resolution,
            aspect ratio, output format, quality, reference pictures -- is read from OpenRouter's
            catalogue, so a model is only sent what it accepts: 16:9 or the nearest landscape
            ratio it has, 2K or the nearest below. The price comes back with each image.
    muse    the same backend with meta/muse-image as its model (the studio's default): 1920x1280
            whatever the aspect asked for, ~25 s and $0.01 an image. Muse is served but not in
            the catalogue, so it is sent what it always was, and it takes no reference.
    gemini  a Gemini image model on Vertex AI (GOOGLE_SERVICE_ACCOUNT_KEY), default
            gemini-3.1-flash-image: 1376x768, ~10 s.

A cut-out -- `"cutout": true` on an image, or `{"border": 0}` / `{"border": 16, "cut": "round"}`
-- is one subject alone, for a collage: it is asked for isolated, with a transparent background
where the model offers one (the block's `"cutouts": {"model", "quality", "border", "cut"}` names
that model; openai/gpt-image-2.5-flare, the default, returns real alpha), or keyed off its white
ground where it does not; stray specks are dropped, it is trimmed, and a paper border `border` px
wide (at 1024 px on the long side; 12 by default, 0 for none) is cut round it in straight
`scissor` snips or a `round` outline. It becomes images/<name>.webp, and film.js draws it with
SK.cutout(name, ...). "aspect" ("1:1", "2:3", "3:2", ...) shapes the canvas it is painted on.

"ref" names an image already painted, which goes in as a reference picture wherever the model
takes one (gemini, and the OpenRouter models whose catalogue entry lists input_references): the
way to keep a character the same from scene to scene. "quality" (low/medium/high) is sent to the
models that have the setting (OpenAI's). scripts/paint-compare.py paints one paint block with
several models side by side, to choose between them.

Images are cached by a fingerprint of backend, model, style, prompt and reference, so a rerun
paints only what changed. Each image painted appends its cost to images/spend.jsonl, and a run
refuses to paint past max_images for the film (the cap a caller such as Sketch Studio sets).

Invoke as:
    python scripts/sketch-paint.py --manifest projects/<id>/sketch.json
    python scripts/sketch-paint.py --manifest projects/<id>/sketch.json --only kitchen --retake
    python scripts/sketch-paint.py --manifest projects/<id>/sketch.json --plan
"""

import sys
import os
import io
import json
import time
import base64
import hashlib
import argparse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _project  # noqa: E402
import _sketch  # noqa: E402

MODELS = {
    "openrouter": "meta/muse-image",
    "muse": "meta/muse-image",
    "gemini": "gemini-3.1-flash-image",
}
OPENROUTER = "https://openrouter.ai/api/v1"
# what the muse backend always sent, for a model OpenRouter's catalogue does not describe
UNLISTED = {"resolution": "2K", "aspect_ratio": "16:9", "output_format": "png"}
KEEP_REF = "Keep the characters, their clothes and the drawing style exactly as in this picture. "
# the suffix sprinkles learned to send: any lettering, border or torn edge is a defect
NO_TEXT = (
    "Do not render any text in the image at all: no captions, signs, labels, packaging, "
    "signatures, initials or watermarks. Any lettering is a defect, even in the background. "
    "Fill the entire frame with the illustration: no border, frame, margin, drop shadow or "
    "torn-paper edge."
)
# the suffix for a cut-out: one subject alone, room round it, nothing behind it
CUTOUT_TEXT = (
    "A single isolated subject, centred, with the whole subject in frame and a generous margin "
    "round it. No background scenery, no ground, no cast shadow, no frame or border, and no text, "
    "lettering, labels or watermarks anywhere."
)
CUTOUT_ON_WHITE = " Set it on a plain, flat, pure white background."
CUTOUT_MODEL = "openai/gpt-image-2.5-flare"  # real alpha, 16 references, ~$0.014 at medium
PAPER_WHITE = (251, 249, 243)
# Gemini image models: USD per 1M output tokens where a list price is known (2.5 flash image:
# $30/M, ~1290 tokens a picture). Others are recorded by tokens with the cost left empty.
GEMINI_OUT_PRICE = {"gemini-2.5-flash-image": 30.0}


def cut_spec(spec, im):
    """An image's cut-out settings, {model, quality, border, cut}, or None for a scene."""
    c = im.get("cutout")
    if not c:
        return None
    base = dict(spec.get("cutouts") or {})
    out = {
        "model": base.get("model", CUTOUT_MODEL),
        "quality": base.get("quality", "medium"),
        "border": base.get("border", 12),
        "cut": base.get("cut", "scissor"),
    }
    if isinstance(c, dict):
        out.update({k: c[k] for k in ("border", "cut") if k in c})
    return out


def fingerprint(spec, im, ref_fp=None):
    parts = [spec.get("backend"), spec.get("model"), spec.get("style"), im["prompt"], ref_fp]
    if spec.get("quality"):  # only when set, so every painting made before it keeps its key
        parts.append(spec["quality"])
    cs = cut_spec(spec, im)
    if cs:  # only for cut-outs, so every scene painted before them keeps its key
        parts.append([cs, im.get("aspect")])
    key = json.dumps(parts, sort_keys=True)
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:10]


def full_prompt(spec, im, transparent=False):
    style = (spec.get("style") or "").strip()
    tail = NO_TEXT
    if cut_spec(spec, im):
        tail = CUTOUT_TEXT + ("" if transparent else CUTOUT_ON_WHITE)
    return ("%s.\n\n" % style.rstrip(".") if style else "") + im["prompt"].strip() + "\n\n" + tail


_CAPS = {}


def model_caps(model):
    """What OpenRouter serves `model` with: its first endpoint from the image catalogue
    ({"supported_parameters", "pricing", ...}), or None when the catalogue has none for it or
    cannot be reached. Public, no key; asked once per model per run."""
    if model not in _CAPS:
        import httpx

        try:
            r = httpx.get("%s/images/models/%s/endpoints" % (OPENROUTER, model), timeout=20)
            eps = r.json().get("endpoints") or []
        except Exception:  # noqa: BLE001 -- no catalogue: send what the muse backend always did
            eps = []
        _CAPS[model] = eps[0] if eps else None
    return _CAPS[model]


def _ratio(a):
    w, h = (float(x) for x in a.split(":"))
    return w / h


def pick_params(caps, quality=None, aspect="16:9", transparent=False):
    """The request's settings for a model: `aspect` (16:9, or the ratio nearest it), 2K (or the
    nearest below), jpeg where the model offers it (png for a transparent cut-out), and `quality`
    if the model has the setting. Anything the catalogue does not list is not sent."""
    if caps is None:
        return dict(UNLISTED)
    sp = caps.get("supported_parameters") or {}
    out = {}
    ars = [a for a in (sp.get("aspect_ratio") or {}).get("values") or [] if ":" in a]
    if aspect in ars:
        out["aspect_ratio"] = aspect
    elif ars:
        same = [a for a in ars if (_ratio(a) >= 1) == (_ratio(aspect) >= 1)] or ars
        out["aspect_ratio"] = min(same, key=lambda a: abs(_ratio(a) - _ratio(aspect)))
    if transparent:
        out["background"] = "transparent"
    res = (sp.get("resolution") or {}).get("values") or []
    if res:
        order = ["512", "1K", "2K", "4K"]
        below = [r for r in res if r in order and order.index(r) <= order.index("2K")]
        out["resolution"] = max(below, key=order.index) if below else res[0]
    fmts = (sp.get("output_format") or {}).get("values") or []
    if fmts:
        want = "png" if transparent else "jpeg"
        out["output_format"] = want if want in fmts else fmts[0]
    if quality and quality in ((sp.get("quality") or {}).get("values") or []):
        out["quality"] = quality
    return out


def gives_alpha(caps):
    """Whether the catalogue says the model paints on a transparent background."""
    bg = ((caps or {}).get("supported_parameters") or {}).get("background") or {}
    return "transparent" in (bg.get("values") or [])


def takes_refs(caps):
    """Whether the catalogue says the model takes a reference picture."""
    refs = ((caps or {}).get("supported_parameters") or {}).get("input_references") or {}
    return refs.get("max", 0) >= 1


def paint_openrouter(prompt, model, ref=None, quality=None, aspect="16:9", transparent=False):
    """One picture from an OpenRouter image model; `ref` (a JPEG, PNG or WebP path) goes in as a
    reference picture when the model takes one, and is dropped (as Muse always dropped it) when
    not. `transparent` asks for a transparent background (sent only where the model has it)."""
    import httpx

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env)")
    caps = model_caps(model)
    body = {"model": model, "prompt": prompt, **pick_params(caps, quality, aspect, transparent)}
    if ref and takes_refs(caps):
        kind = {".png": "png", ".webp": "webp"}.get(os.path.splitext(ref)[1].lower(), "jpeg")
        with open(ref, "rb") as f:
            url = "data:image/%s;base64," % kind + base64.b64encode(f.read()).decode()
        body["input_references"] = [{"type": "image_url", "image_url": {"url": url}}]
        body["prompt"] = KEEP_REF + prompt
    r = httpx.post(
        OPENROUTER + "/images",
        headers={"Authorization": "Bearer " + key, "X-Title": "kitcut"},
        json=body,
        timeout=240,
    )
    try:
        j = r.json()
    except ValueError:
        raise RuntimeError("openrouter %s: %s" % (r.status_code, r.text[:300])) from None
    if r.status_code != 200:
        raise RuntimeError("openrouter %s: %s" % (r.status_code, str(j.get("error", j))[:300]))
    d = j["data"][0]
    data = base64.b64decode(d["b64_json"]) if d.get("b64_json") else httpx.get(d["url"]).content
    u = j.get("usage") or {}
    return data, {"cost_usd": u.get("cost"), "tokens": u.get("completion_tokens")}


def paint_gemini(prompt, model, ref=None):
    from google import genai
    from google.genai import types
    from google.oauth2 import service_account

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_KEY is not set (put it in .env)")
    info = json.loads(base64.b64decode(raw) if not raw.startswith("{") else raw)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT") or info["project_id"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "global",
        credentials=creds,
    )
    contents = [prompt]
    if ref:
        with open(ref, "rb") as f:
            contents = [
                types.Part.from_bytes(data=f.read(), mime_type="image/jpeg"),
                "Keep the characters, their clothes and the drawing style exactly as in this "
                "picture. " + prompt,
            ]
    r = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio="16:9")
        ),
    )
    part = next(p for p in r.candidates[0].content.parts if p.inline_data)
    tok = r.usage_metadata.candidates_token_count or 0
    price = GEMINI_OUT_PRICE.get(model)
    return part.inline_data.data, {
        "cost_usd": round(tok * price / 1e6, 6) if price else None,
        "tokens": tok,
    }


def ext(spec, im):
    """The file an image becomes: .webp for a cut-out (it keeps its transparency), else .jpg."""
    return ".webp" if cut_spec(spec, im) else ".jpg"


def to_jpeg(data, path):
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.save(path, "JPEG", quality=90, optimize=True)
    return im.size


def matte_white(rgba):
    """Key a picture painted on white off its ground: the near-white region that reaches the edge
    of the picture becomes transparent. White inside the subject stays (a paper border covers any
    hole the key leaves where the subject's own white touches the ground)."""
    import numpy as np
    import cv2

    rgb = rgba[..., :3].astype(np.int16)
    near = ((255 - rgb.min(axis=2)) < 22).astype(np.uint8)
    _n, lab = cv2.connectedComponents(near, connectivity=4)
    edge = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    ground = np.isin(lab, edge[edge > 0]) & (near == 1)
    alpha = cv2.GaussianBlur(np.where(ground, 0, 255).astype(np.uint8), (3, 3), 0)
    out = rgba.copy()
    out[..., 3] = np.minimum(out[..., 3], alpha)
    return out


def cutout(data, border=12, cut="scissor", long_side=1024):
    """A cut-out from a painted picture: its subject on a transparent background (matted off
    white when the picture came back opaque), specks dropped, trimmed, scaled to `long_side`, with
    a paper border `border` px wide cut round it -- straight `scissor` snips that bridge the
    notches a pair of scissors would skip, or a `round` outline; 0 for none. A PIL RGBA image."""
    import numpy as np
    import cv2
    from PIL import Image

    a = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")).copy()
    if a[..., 3].min() > 250:
        a = matte_white(a)
    solid = (a[..., 3] > 40).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n > 1:  # keep the subject and the pieces that belong to it, not the model's stray specks
        big = stats[1:, cv2.CC_STAT_AREA].max()
        drop = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] < big * 0.015]
        if drop:
            gone = np.isin(lab, drop)
            a[gone, 3] = 0
            solid[gone] = 0
    ys, xs = np.nonzero(solid)
    if not len(xs):
        raise RuntimeError("the cut-out came back empty")
    a = a[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    k = long_side / max(a.shape[:2])
    if abs(k - 1) > 0.01:
        size = (max(1, round(a.shape[1] * k)), max(1, round(a.shape[0] * k)))
        a = np.asarray(Image.fromarray(a).resize(size, Image.LANCZOS))
    return paper_border(a, int(border), cut)


def paper_border(a, b, cut):
    """The subject `a` (an RGBA array) on a white paper backing b px wide, cut round it in
    straight snips (`scissor`) or following its outline (`round`); b <= 0 leaves it bare."""
    import numpy as np
    import cv2
    from PIL import Image

    if b <= 0:
        return Image.fromarray(a)
    p = 4 * b
    a = np.pad(a, ((p, p), (p, p), (0, 0)))
    m = (a[..., 3] > 60).astype(np.uint8) * 255
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * b + 1, 2 * b + 1))
    grown = cv2.dilate(m, disc)
    if cut == "scissor":
        wide = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5 * b + 1, 5 * b + 1))
        grown = cv2.morphologyEx(grown, cv2.MORPH_CLOSE, wide)
    cnts, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    back = np.zeros(grown.shape, np.uint8)
    for c in cnts:
        if cv2.contourArea(c) < grown.size * 0.002:
            continue
        poly = cv2.approxPolyDP(c, max(1.5, b * 0.5), True) if cut == "scissor" else c
        cv2.fillPoly(back, [poly], 255, lineType=cv2.LINE_AA)
    base = np.zeros_like(a)
    base[..., :3] = PAPER_WHITE
    base[..., 3] = back
    out = Image.alpha_composite(Image.fromarray(base), Image.fromarray(a))
    bb = out.getbbox()
    return out.crop((max(0, bb[0] - 2), max(0, bb[1] - 2), bb[2] + 2, bb[3] + 2)) if bb else out


def contact_sheet(files, out):
    """All the paintings on one page, labelled: what to look at before animating them."""
    from PIL import Image, ImageDraw

    tw, th, cols = 640, 360, 2 if len(files) <= 4 else 3
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 28)), (247, 242, 231))
    d = ImageDraw.Draw(sheet)
    for k, (name, p) in enumerate(files):
        im = Image.open(p)
        if im.mode == "RGBA":  # a cut-out: on a mid blue, so its edge and border show
            bg = Image.new("RGBA", im.size, (96, 150, 205, 255))
            bg.alpha_composite(im)
            im = bg
        im = im.convert("RGB")
        im.thumbnail((tw, th))
        x, y = (k % cols) * tw, (k // cols) * (th + 28)
        sheet.paste(im, (x + (tw - im.width) // 2, y))
        d.text((x + 8, y + th + 6), "%s  (%dx%d)" % (name, *Image.open(p).size), fill=(42, 37, 33))
    sheet.save(out, "JPEG", quality=85)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--plan", action="store_true", help="list what would be painted and stop")
    ap.add_argument("--only", help="comma list of image names to (re)paint")
    ap.add_argument("--retake", action="store_true", help="discard cached images for --only")
    args = ap.parse_args()

    m = _sketch.load(args.manifest)
    spec = dict(m.get("paint") or {})
    images = spec.get("images") or []
    if not images:
        sys.exit("no paint.images in %s" % m["_path"])
    names = [im.get("name", "") for im in images]
    bad = [n for n in names if not isinstance(n, str) or not _sketch.SAFE_NAME.match(n)]
    if bad or len(set(names)) != len(names):
        sys.exit(
            "paint.images need unique names of lowercase letters, digits, - and _ (got %s)" % names
        )
    backend = spec.get("backend", "muse")
    if backend not in MODELS:
        sys.exit("paint.backend must be one of %s" % ", ".join(MODELS))
    model = spec.get("model") or MODELS[backend]
    spec["model"] = model
    only = set(args.only.split(",")) if args.only else set(names)
    idir = os.path.join(m["_dir"], "images")
    os.makedirs(idir, exist_ok=True)
    spend_p = os.path.join(idir, "spend.jsonl")
    painted_before = 0
    if os.path.exists(spend_p):
        with open(spend_p, encoding="utf-8") as f:
            painted_before = sum(1 for x in f if x.strip())

    # which need painting: in order, so a "ref" is painted before the images that use it
    by_name = {im["name"]: im for im in images}
    fps, todo, discard = {}, [], []
    for im in images:
        ref = im.get("ref")
        if ref and ref not in by_name:
            sys.exit("image %s: ref %r is not one of the images" % (im["name"], ref))
        fps[im["name"]] = fingerprint(spec, im, fps.get(ref) if ref else None)
        cached = os.path.join(idir, "%s_%s%s" % (im["name"], fps[im["name"]], ext(spec, im)))
        retake = im["name"] in only and args.retake and os.path.exists(cached)
        if retake:
            discard.append(cached)  # only once the cap below allows the repaint
        if retake or not os.path.exists(cached):
            todo.append(im)
    print(
        "%s  %s (%s)  %d images, %d to paint, %d painted for this film so far"
        % (m["_id"], backend, model, len(images), len(todo), painted_before)
    )
    for im in images:
        print(
            "  %-12s %s%s" % (im["name"], "PAINT  " if im in todo else "cached ", im["prompt"][:90])
        )
    cap = spec.get("max_images")
    if cap is not None and painted_before + len(todo) > int(cap):
        sys.exit(
            "that would paint %d images for this film; the cap is %d (%d painted already): "
            "repaint fewer, or reuse the ones you have"
            % (painted_before + len(todo), cap, painted_before)
        )
    if args.plan:
        print("\n  --plan: nothing painted")
        return
    for p in discard:
        os.remove(p)

    with _sketch.Stages(m, "sketch-paint", ["paint", "sheet"], argv=sys.argv[1:]) as st:
        with st("paint"):

            def one(im):
                cs = cut_spec(spec, im)
                alpha = bool(cs) and gives_alpha(model_caps(cs["model"]))
                prompt = full_prompt(spec, im, transparent=alpha)
                r = im.get("ref")
                ref = os.path.join(idir, r + ext(spec, by_name[r])) if r else None
                t, err = time.time(), None
                for attempt in range(3):
                    try:
                        if cs:  # a cut-out: its own model, square unless told, alpha if it has it
                            shape = im.get("aspect", "1:1")
                            data, meta = paint_openrouter(
                                prompt, cs["model"], ref, cs["quality"], shape, alpha
                            )
                        elif backend == "gemini":
                            data, meta = paint_gemini(prompt, model, ref)
                        else:
                            data, meta = paint_openrouter(prompt, model, ref, spec.get("quality"))
                        break
                    except Exception as e:  # noqa: BLE001 -- image services drop requests; retry
                        err = e
                        time.sleep(2 * (attempt + 1))
                else:
                    raise RuntimeError("%s: %s" % (im["name"], err))
                path = os.path.join(idir, "%s_%s%s" % (im["name"], fps[im["name"]], ext(spec, im)))
                if cs:
                    pic = cutout(data, cs["border"], cs["cut"])
                    pic.save(path, "WEBP", quality=92, method=6)
                    w, h = pic.size
                    meta = {**meta, "model": cs["model"], "alpha": "model" if alpha else "matted"}
                else:
                    w, h = to_jpeg(data, path)
                return im["name"], path, w, h, meta, time.time() - t

            done, refs = [], [im for im in todo if not im.get("ref")]
            later = [im for im in todo if im.get("ref")]
            for batch in (refs, later):  # the references first: the others are painted from them
                with ThreadPoolExecutor(max_workers=4) as ex:
                    for name, path, w, h, meta, sec in ex.map(one, batch):
                        # the current version under its plain name, for the film to draw
                        with (
                            open(path, "rb") as a,
                            open(os.path.join(idir, name + ext(spec, by_name[name])), "wb") as b,
                        ):
                            b.write(a.read())
                        done.append(meta)
                        with open(spend_p, "a", encoding="utf-8") as f:
                            f.write(
                                json.dumps(
                                    {"name": name, "backend": backend, "model": model} | meta
                                )
                                + "\n"
                            )
                        print(
                            "  painted %-12s %dx%d in %.1fs  %s"
                            % (
                                name,
                                w,
                                h,
                                sec,
                                "$%.4f" % meta["cost_usd"]
                                if meta.get("cost_usd") is not None
                                else "%s tokens (unpriced)" % meta.get("tokens"),
                            )
                        )
            # a cached image may be the current one again (a retake undone): refresh plain names
            for im in images:
                e = ext(spec, im)
                src = os.path.join(idir, "%s_%s%s" % (im["name"], fps[im["name"]], e))
                dst = os.path.join(idir, im["name"] + e)
                if os.path.exists(src):
                    with open(src, "rb") as a, open(dst, "wb") as b:
                        b.write(a.read())
            spent = sum(x.get("cost_usd") or 0 for x in done)
            print("  painted %d this run, $%.4f" % (len(done), spent))
        with st("sheet"):
            files = [(n, os.path.join(idir, n + ext(spec, by_name[n]))) for n in names]
            sheet = os.path.join(idir, "sheet.jpg")
            contact_sheet([f for f in files if os.path.exists(f[1])], sheet)
            print("  %s" % os.path.relpath(sheet, _env.ROOT))

    _project.record(
        m["_id"],
        "sketch scenes painted",
        out=sheet,
        script=__file__,
        argv=sys.argv[1:],
        kind="paint-sheet",
        manifest=m["_path"],
    )


if __name__ == "__main__":
    main()
