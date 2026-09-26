#!/usr/bin/env python
"""Paint a sketch film's scenes with an image model: the pictures a film animates.

Reads the `paint` block of the manifest (inline, or a file: "paint": "paint.json"):

    "paint": {"backend": "muse", "style": "warm watercolour children's-book illustration",
              "images": [{"name": "kitchen", "prompt": "a little girl at the kitchen sink ..."},
                         {"name": "table", "prompt": "...", "ref": "kitchen"}],
              "max_images": 12}

Every image becomes images/<name>.jpg next to the manifest, and joins the manifest's images
(_sketch.load does that), so film.js draws it with SK.image(name, x, y, w). The style line goes
in front of every prompt, so the scenes share one look; the text-free, border-free suffix goes
behind (an image model letters signs and frames pictures unless told not to). A contact sheet of
all of them, images/sheet.jpg, is what to look at before animating.

Backends:
    muse    meta/muse-image through OpenRouter (OPENROUTER_API_KEY). 1920x1280 whatever the
            aspect asked for; ~25 s and $0.01 an image (the price comes back with each image).
    gemini  a Gemini image model on Vertex AI (GOOGLE_SERVICE_ACCOUNT_KEY), default
            gemini-3.1-flash-image: 1376x768, ~10 s. "ref" names an image already painted, which
            goes in as a reference: the way to keep a character the same from scene to scene.

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

MODELS = {"muse": "meta/muse-image", "gemini": "gemini-3.1-flash-image"}
# the suffix sprinkles learned to send: any lettering, border or torn edge is a defect
NO_TEXT = (
    "Do not render any text in the image at all: no captions, signs, labels, packaging, "
    "signatures, initials or watermarks. Any lettering is a defect, even in the background. "
    "Fill the entire frame with the illustration: no border, frame, margin, drop shadow or "
    "torn-paper edge."
)
# Gemini image models: USD per 1M output tokens where a list price is known (2.5 flash image:
# $30/M, ~1290 tokens a picture). Others are recorded by tokens with the cost left empty.
GEMINI_OUT_PRICE = {"gemini-2.5-flash-image": 30.0}


def fingerprint(spec, im, ref_fp=None):
    key = json.dumps(
        [spec.get("backend"), spec.get("model"), spec.get("style"), im["prompt"], ref_fp],
        sort_keys=True,
    )
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:10]


def full_prompt(spec, im):
    style = (spec.get("style") or "").strip()
    return (
        ("%s.\n\n" % style.rstrip(".") if style else "") + im["prompt"].strip() + "\n\n" + NO_TEXT
    )


def paint_muse(prompt, model):
    import httpx

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env)")
    r = httpx.post(
        "https://openrouter.ai/api/v1/images",
        headers={"Authorization": "Bearer " + key, "X-Title": "kitcut"},
        json={
            "model": model,
            "prompt": prompt,
            "resolution": "2K",
            "aspect_ratio": "16:9",
            "output_format": "png",
        },
        timeout=240,
    )
    j = r.json()
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


def to_jpeg(data, path):
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.save(path, "JPEG", quality=90, optimize=True)
    return im.size


def contact_sheet(files, out):
    """All the paintings on one page, labelled: what to look at before animating them."""
    from PIL import Image, ImageDraw

    tw, th, cols = 640, 360, 2 if len(files) <= 4 else 3
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 28)), (247, 242, 231))
    d = ImageDraw.Draw(sheet)
    for k, (name, p) in enumerate(files):
        im = Image.open(p).convert("RGB")
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
        cached = os.path.join(idir, "%s_%s.jpg" % (im["name"], fps[im["name"]]))
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
                prompt = full_prompt(spec, im)
                ref = os.path.join(idir, im["ref"] + ".jpg") if im.get("ref") else None
                t, err = time.time(), None
                for attempt in range(3):
                    try:
                        if backend == "muse":
                            data, meta = paint_muse(prompt, model)
                        else:
                            data, meta = paint_gemini(prompt, model, ref)
                        break
                    except Exception as e:  # noqa: BLE001 -- image services drop requests; retry
                        err = e
                        time.sleep(2 * (attempt + 1))
                else:
                    raise RuntimeError("%s: %s" % (im["name"], err))
                path = os.path.join(idir, "%s_%s.jpg" % (im["name"], fps[im["name"]]))
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
                            open(os.path.join(idir, name + ".jpg"), "wb") as b,
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
                src = os.path.join(idir, "%s_%s.jpg" % (im["name"], fps[im["name"]]))
                dst = os.path.join(idir, im["name"] + ".jpg")
                if os.path.exists(src):
                    with open(src, "rb") as a, open(dst, "wb") as b:
                        b.write(a.read())
            spent = sum(x.get("cost_usd") or 0 for x in done)
            print("  painted %d this run, $%.4f" % (len(done), spent))
        with st("sheet"):
            files = [(n, os.path.join(idir, n + ".jpg")) for n in names]
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
