#!/usr/bin/env python
"""Paint one paint block with several image models, side by side: the painter bake-off.

Reads a sketch manifest's `paint` block (the one sketch-paint.py paints) and paints every image
with every model named in --models, into the project's temp/paint-compare/<model>/. A model is an
OpenRouter image model id (sketch-paint.py's openrouter backend: each is sent only the settings
its catalogue entry lists) or "gemini:<model>" for the Vertex backend. An image's "ref" is painted
from the same model's own painting of the image it names, so a model that cannot keep a character
from scene to scene shows it; a model that takes no reference paints from the words alone. An
image may carry its own "style", so one bake-off can mix scenes from several films.

Writes, under the project's temp/paint-compare/:
    <model>/<name>.jpg, <model>/sheet.jpg   every picture one model painted, on one page
    by-prompt/<name>.jpg                     one prompt across every model, labelled
    results.csv, results.json                model, image, ref, seconds, cost_usd, size, error

--plan prices the run from OpenRouter's catalogue and paints nothing. --cap stops starting new
pictures once the spend (as the API reports it) plus the next picture's estimate would pass it.
A picture already painted for the same model, style, prompt and reference is reused, so a rerun
pays only for what changed (--retake repaints).

Invoke as:
    python scripts/paint-compare.py --manifest projects/<id>/sketch.json --models a/b,c/d --plan
    python scripts/paint-compare.py --manifest projects/<id>/sketch.json --models a/b,c/d --cap 4
    python scripts/paint-compare.py --manifest projects/<id>/sketch.json --models a/b --only cat
"""

import sys
import os
import csv
import json
import time
import argparse
import threading
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _project  # noqa: E402
import _sketch  # noqa: E402

SP = import_module("sketch-paint")

# a model the catalogue does not price (Muse): what it cost when last seen, per picture
UNPRICED = {"meta/muse-image": 0.01}
# tokens an image model spends on one picture, for pricing the token-billed ones before a run:
# Gemini ~1290 at 1K, OpenAI ~1060 at 1536x1024 medium; a round figure above both
IMAGE_TOKENS = 1400
PICTURE_MP = 2.2  # megapixels of a 16:9 picture near 2K, for the ones billed by the megapixel


def slug(model):
    return model.replace(":", "_").replace("/", "__")


def estimate(model, has_ref, quality=None):
    """USD for one picture, from the catalogue's price list; None when it cannot say."""
    if model.startswith("gemini:"):
        return None
    caps = SP.model_caps(model)
    if caps is None:
        return UNPRICED.get(model)
    params = SP.pick_params(caps, quality)
    res = (params.get("resolution") or "").lower()
    out, extra = [], 0.0
    for p in caps.get("pricing") or []:
        bill, unit, usd = p.get("billable"), p.get("unit"), float(p.get("cost_usd") or 0)
        if bill == "output_image":
            if unit == "image":
                out.append((p.get("variant") or "", usd))
            elif unit == "megapixel":
                out.append(("", usd * PICTURE_MP))
            elif unit == "token":
                out.append(("", usd * IMAGE_TOKENS))
        elif has_ref and SP.takes_refs(caps) and bill in ("input_image", "input_reference"):
            extra += usd * (IMAGE_TOKENS if unit == "token" else 1)
    if not out:
        return None
    # the variant for the resolution asked for; else the plain price; else the dearest listed
    pick = [u for v, u in out if res and res in v.lower()] or [u for v, u in out if not v]
    return round((pick[0] if pick else max(u for _, u in out)) + extra, 4)


def by_prompt_sheet(name, tiles, out):
    """One prompt across every model: each picture labelled with its model, price and time."""
    from PIL import Image, ImageDraw

    tw, th, cols = 640, 360, 3
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 40)), (247, 242, 231))
    d = ImageDraw.Draw(sheet)
    for k, (label, path) in enumerate(tiles):
        x, y = (k % cols) * tw, (k // cols) * (th + 40)
        if path and os.path.exists(path):
            im = Image.open(path).convert("RGB")
            im.thumbnail((tw, th))
            sheet.paste(im, (x + (tw - im.width) // 2, y))
        else:
            d.rectangle((x + 8, y + 8, x + tw - 8, y + th - 8), outline=(179, 65, 46), width=3)
        d.text((x + 8, y + th + 6), label, fill=(42, 37, 33))
    d.text((8, sheet.height - 14), name, fill=(107, 98, 90))
    sheet.save(out, "JPEG", quality=85)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument(
        "--models", required=True, help="comma list: OpenRouter image model ids, gemini:<model>"
    )
    ap.add_argument("--only", help="comma list of image names")
    ap.add_argument("--plan", action="store_true", help="price the run, paint nothing")
    ap.add_argument("--cap", type=float, default=4.0, help="stop at this spend in USD (4)")
    ap.add_argument("--retake", action="store_true", help="repaint pictures already painted")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    m = _sketch.load(args.manifest)
    spec = dict(m.get("paint") or {})
    images = spec.get("images") or []
    if args.only:
        keep = set(args.only.split(","))
        need = keep | {im["ref"] for im in images if im["name"] in keep and im.get("ref")}
        images = [im for im in images if im["name"] in need]
    if not images:
        sys.exit("no paint.images in %s" % m["_path"])
    by_name = {}
    for im in images:
        _sketch.safe_name(im.get("name"), "paint image name")
        if im.get("ref") and im["ref"] not in {x["name"] for x in images}:
            sys.exit("image %s: ref %r is not one of the images" % (im["name"], im["ref"]))
        by_name[im["name"]] = im
    models = [x.strip() for x in args.models.split(",") if x.strip()]
    quality = spec.get("quality")

    print("%s  %d images x %d models, cap $%.2f" % (m["_id"], len(images), len(models), args.cap))
    total = 0.0
    est = {}
    for mo in models:
        caps = None if mo.startswith("gemini:") else SP.model_caps(mo)
        e1, e2 = estimate(mo, False, quality), estimate(mo, True, quality)
        est[mo] = (e1, e2)
        n_ref = sum(1 for im in images if im.get("ref"))
        cost = None if e1 is None else e1 * (len(images) - n_ref) + (e2 or e1) * n_ref
        total += cost or 0
        how = (
            "vertex"
            if mo.startswith("gemini:")
            else "unlisted: sent %s" % SP.UNLISTED
            if caps is None
            else "%s%s" % (SP.pick_params(caps, quality), "  +ref" if SP.takes_refs(caps) else "")
        )
        print(
            "  %-40s %s/picture  %s  %s"
            % (
                mo,
                "$%.3f" % e1 if e1 is not None else "  ?  ",
                "~$%.2f" % cost if cost else "",
                how,
            )
        )
    print("  estimated total: ~$%.2f (unpriced models not counted)" % total)
    if args.plan:
        print("\n  --plan: nothing painted")
        return

    root = os.path.join(m["_temp"], "paint-compare")
    lock = threading.Lock()
    spent = [0.0]
    rows = {}
    ledger = os.path.join(root, "log.jsonl")
    os.makedirs(root, exist_ok=True)
    seen = {}
    if os.path.exists(ledger):  # what earlier runs paid, so a reused picture keeps its figures
        with open(ledger, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    seen[(r["model"], r["file"])] = r

    def job(mo, im):
        spec_i = {**spec, "style": im.get("style", spec.get("style"))}
        spec_i["backend"], spec_i["model"] = (
            ("gemini", mo.split(":", 1)[1]) if mo.startswith("gemini:") else ("openrouter", mo)
        )
        d = os.path.join(root, slug(mo))
        os.makedirs(d, exist_ok=True)
        ref = os.path.join(d, im["ref"] + ".jpg") if im.get("ref") else None
        ref_fp = rows.get((mo, im.get("ref")), {}).get("fp") if ref else None
        fp = SP.fingerprint(spec_i, im, ref_fp)
        path = os.path.join(d, "%s_%s.jpg" % (im["name"], fp))
        row = {"model": mo, "image": im["name"], "ref": im.get("ref") or "", "fp": fp}
        if os.path.exists(path) and not args.retake:
            old = seen.get((mo, os.path.basename(path)), {})
            row.update({k: old.get(k) for k in ("seconds", "cost_usd", "width", "height")})
            row.update(cached=True, error="", path=path)
        elif ref and not os.path.exists(ref):
            row.update(error="its reference %s was not painted" % im["ref"], path="")
        else:
            e = est[mo][1 if ref else 0] or 0.0
            with lock:
                if spent[0] + e > args.cap:
                    row.update(error="skipped: the $%.2f cap" % args.cap, path="")
                    rows[(mo, im["name"])] = row
                    return row
                spent[0] += e  # held until the real figure comes back
            prompt = SP.full_prompt(spec_i, im)
            t = time.time()
            try:
                if spec_i["backend"] == "gemini":
                    data, meta = SP.paint_gemini(prompt, spec_i["model"], ref)
                else:
                    data, meta = SP.paint_openrouter(prompt, mo, ref, quality)
                w, h = SP.to_jpeg(data, path)
                row.update(
                    seconds=round(time.time() - t, 1),
                    cost_usd=meta.get("cost_usd"),
                    width=w,
                    height=h,
                    error="",
                    path=path,
                    cached=False,
                )
            except Exception as ex:  # noqa: BLE001 -- one model failing is a result, not a stop
                row.update(seconds=round(time.time() - t, 1), error=str(ex)[:300], path="")
            with lock:
                spent[0] += (row.get("cost_usd") or 0) - e
                with open(ledger, "a", encoding="utf-8") as f:
                    f.write(
                        json.dumps({**row, "file": os.path.basename(path), "at": time.time()})
                        + "\n"
                    )
            print(
                "  %-40s %-10s %s"
                % (
                    mo,
                    im["name"],
                    row["error"][:120]
                    if row["error"]
                    else "%dx%d %.1fs $%s" % (w, h, row["seconds"], row.get("cost_usd")),
                ),
                flush=True,
            )
        if not row.get("error") and path:  # the current picture under its plain name
            with open(os.path.join(d, im["name"] + ".jpg"), "wb") as b, open(path, "rb") as a:
                b.write(a.read())
        rows[(mo, im["name"])] = row
        return row

    with _sketch.Stages(m, "paint-compare", ["paint", "sheets"], argv=sys.argv[1:]) as st:
        with st("paint"):
            first = [(mo, im) for im in images if not im.get("ref") for mo in models]
            rest = [(mo, im) for im in images if im.get("ref") for mo in models]
            for wave in (first, rest):  # the references first: the others are painted from them
                with ThreadPoolExecutor(max_workers=args.workers) as ex:
                    list(ex.map(lambda a: job(*a), wave))
            print("  spent $%.3f this run" % spent[0])
        with st("sheets"):
            names = [im["name"] for im in images]
            for mo in models:
                d = os.path.join(root, slug(mo))
                files = [(n, os.path.join(d, n + ".jpg")) for n in names]
                files = [f for f in files if rows.get((mo, f[0]), {}).get("path")]
                if files:
                    SP.contact_sheet(files, os.path.join(d, "sheet.jpg"))
            bp = os.path.join(root, "by-prompt")
            os.makedirs(bp, exist_ok=True)
            for n in names:
                tiles = []
                for mo in models:
                    r = rows.get((mo, n), {})
                    label = "%s  %s" % (
                        mo,
                        "FAILED: " + r["error"][:40]
                        if r.get("error")
                        else "$%s  %ss  %sx%s"
                        % (r.get("cost_usd"), r.get("seconds"), r.get("width"), r.get("height")),
                    )
                    tiles.append((label, r.get("path")))
                by_prompt_sheet(n, tiles, os.path.join(bp, n + ".jpg"))
            table = [rows[k] for k in sorted(rows)]
            cols = ["model", "image", "ref", "seconds", "cost_usd", "width", "height", "error"]
            with open(os.path.join(root, "results.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(table)
            res = os.path.join(root, "results.json")
            with open(res, "w", encoding="utf-8") as f:
                json.dump({"models": models, "images": names, "rows": table}, f, indent=1)
            print("  %s" % os.path.relpath(root, _env.ROOT))

    _project.record(
        m["_id"],
        "painter bake-off: %d images x %d models" % (len(images), len(models)),
        out=res,
        script=__file__,
        argv=sys.argv[1:],
        kind="paint-compare",
        manifest=m["_path"],
        sidecars={"csv": os.path.join(root, "results.csv"), "sheets": bp},
    )


if __name__ == "__main__":
    main()
