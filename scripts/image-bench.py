#!/usr/bin/env python
"""Image-model bench: the same checkable prompts through several image models, scored per fact.

A bench spec (config/bench/*.json) lists models (OpenRouter image ids), one aspect, resolution
and quality, and prompts whose facts can be checked. Each prompt carries checks of three kinds:

    ocr_contains   the expected words are read off the picture by RapidOCR (normalised, exact
                   letters; spaces ignored, because OCR runs words together)
    ocr_none       OCR finds no text at all (for "no signs, letters or text" prompts)
    judge          one yes/no question for a judge (a Claude reader), asked blind: the judge
                   sees each prompt's pictures under shuffled letters, never the model names

Steps, each resumable (a picture, a reading or a verdict already on disk is reused):

    --plan       price the run from OpenRouter's image catalogue; makes nothing
    --run        make every missing picture; --cap (or the spec's cap_usd) stops starting new
                 ones once the spend the API reports plus the next estimate would pass it
    --ocr        read every picture with RapidOCR and settle the ocr checks
    --packets    write the blind judge packets (packets/<prompt>.json + a JPEG per letter) and
                 the letter key (packets/key.json); judges answer into verdicts/<prompt>.json
    --reconcile  merge two independent judges (verdicts_a/, verdicts_b/) into verdicts/: where
                 they agree, that answer; where they differ, a third judge's answer from
                 verdicts_c/ if present, else a fail. disputes.json lists every disagreement
                 with all three answers and whether it is settled; agreement.json has raw
                 agreement, Cohen's kappa, the dispute counts and OCR vs judge
    --score      join OCR, verdicts and the run log into scores.json, print the table, and
                 write labelled by-prompt grids for publishing (grids/<prompt>.jpg)

Writes under projects/<id>/temp/bench/: images/<model>/<prompt>.png, results.json (seconds,
cost_usd, size, error per picture), ocr.json, packets/, verdicts/, grids/, scores.json.

A verdict file is {"prompt": id, "answers": [{"label": "A", "check": "j-1", "answer": "yes"|"no",
"note": "..."}]}; any other answer counts as a fail and is listed.

Invoke as:
    python scripts/image-bench.py --spec config/bench/image-2026-10.json --plan
    python scripts/image-bench.py --spec config/bench/image-2026-10.json --run --cap 5
    python scripts/image-bench.py --spec config/bench/image-2026-10.json --ocr --packets
    python scripts/image-bench.py --spec config/bench/image-2026-10.json --reconcile --score
"""

import sys
import os
import json
import time
import random
import argparse
import statistics
import threading
import unicodedata
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _project  # noqa: E402

SP = import_module("sketch-paint")

# tokens a token-billed model spends on one ~1 MP picture (Gemini ~1120-1290, OpenAI medium
# ~1056): a round figure above both, so the estimate errs high
IMAGE_TOKENS = 1300
PICTURE_MP = 1.05


def slug(model):
    return model.replace("/", "__")


def load_spec(path):
    with open(_env.resolve(path), encoding="utf-8") as f:
        spec = json.load(f)
    spec["_path"] = path
    return spec


def bench_dir(spec):
    return os.path.join(_project.projects_dir(), spec["id"], "temp", "bench")


def params_for(caps, spec):
    """What one request asks for: the spec's aspect, resolution and quality where the model's
    catalogue entry lists them (nearest listed aspect otherwise), n=1; nothing unlisted.
    """
    if caps is None:
        return {}
    sp = caps.get("supported_parameters") or {}
    out = {}
    ars = [a for a in (sp.get("aspect_ratio") or {}).get("values") or [] if ":" in a]
    want = spec.get("aspect", "1:1")
    if want in ars:
        out["aspect_ratio"] = want
    elif ars:
        w, h = (float(x) for x in want.split(":"))
        out["aspect_ratio"] = min(ars, key=lambda a: abs(SP._ratio(a) - w / h))
    res = (sp.get("resolution") or {}).get("values") or []
    for cand in (spec.get("resolution", "1K"), "1K", "1k", "1024", "1024x1024"):
        if cand in res:
            out["resolution"] = cand
            break
    q = (sp.get("quality") or {}).get("values") or []
    if spec.get("quality") in q:
        out["quality"] = spec["quality"]
    if "n" in sp:
        out["n"] = 1
    return out


def estimate(model, spec):
    """USD for one picture from the catalogue's price list; None when it cannot say."""
    caps = SP.model_caps(model)
    if caps is None:
        return None
    res = (params_for(caps, spec).get("resolution") or "").lower()
    per_image = []
    for p in caps.get("pricing") or []:
        if p.get("billable") != "output_image":
            continue
        unit, usd = p.get("unit"), float(p.get("cost_usd") or 0)
        variant = (p.get("variant") or "").lower()
        if unit == "image":
            per_image.append((variant, usd))
        elif unit == "token":
            per_image.append(("", usd * IMAGE_TOKENS))
        elif unit == "megapixel":
            per_image.append(("", usd * PICTURE_MP))
    if not per_image:
        return None
    for variant, usd in per_image:
        if (
            variant
            and res
            and (variant == res or (variant in ("1k", "1024") and res in ("1k", "1024")))
        ):
            return usd
    plain = [u for v, u in per_image if not v]
    return plain[0] if plain else min(u for _, u in per_image)


def make_picture(model, prompt, spec):
    """One picture: (png bytes, {"cost_usd", "seconds"}); raises with the API's words on error."""
    import base64
    import httpx

    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (put it in .env)")
    body = {"model": model, "prompt": prompt, **params_for(SP.model_caps(model), spec)}
    t0 = time.time()
    r = httpx.post(
        SP.OPENROUTER + "/images",
        headers={"Authorization": "Bearer " + key, "X-Title": "kitcut-image-bench"},
        json=body,
        timeout=300,
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
    return data, {"cost_usd": u.get("cost"), "seconds": round(time.time() - t0, 2)}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def plan(spec):
    n = len(spec["prompts"])
    total = 0.0
    print("%-40s %10s %10s" % ("model", "$/picture", "$ x%d" % n))
    for m in spec["models"]:
        e = estimate(m, spec)
        total += (e or 0) * n
        print(
            "%-40s %10s %10s"
            % (m, "?" if e is None else "%.4f" % e, "?" if e is None else "%.2f" % (e * n))
        )
    print("%-40s %10s %10.2f   (cap %.2f)" % ("total", "", total, spec.get("cap_usd") or 0))


def run(spec, cap, workers):
    root = bench_dir(spec)
    res_path = os.path.join(root, "results.json")
    rows = load_json(res_path, {})
    lock = threading.Lock()
    spent = sum(r.get("cost_usd") or 0 for r in rows.values())
    reserved = [0.0]
    todo = []
    for m in spec["models"]:
        for p in spec["prompts"]:
            k = "%s|%s" % (m, p["id"])
            path = os.path.join(root, "images", slug(m), p["id"] + ".png")
            if os.path.exists(path) and k in rows and not rows[k].get("error"):
                continue
            todo.append((k, m, p, path))
    print("%d pictures to make, %.2f spent so far, cap %.2f" % (len(todo), spent, cap))

    def one(item):
        k, m, p, path = item
        est = estimate(m, spec) or 0.05
        with lock:
            if spent_now() + reserved[0] + est > cap:
                return "skipped (cap)"
            reserved[0] += est
        try:
            data, meta = make_picture(m, p["prompt"], spec)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            from PIL import Image

            with Image.open(path) as im:
                w, h = im.size
            row = {
                "model": m,
                "prompt": p["id"],
                "path": os.path.relpath(path, _env.ROOT),
                "seconds": meta["seconds"],
                "cost_usd": meta["cost_usd"],
                "estimate_usd": est,
                "width": w,
                "height": h,
                "bytes": len(data),
                "error": None,
            }
        except Exception as e:  # noqa: BLE001 -- recorded per picture, the run carries on
            row = {
                "model": m,
                "prompt": p["id"],
                "path": None,
                "seconds": None,
                "cost_usd": None,
                "estimate_usd": est,
                "error": str(e)[:400],
            }
        with lock:
            reserved[0] -= est
            rows[k] = row
            save_json(res_path, rows)
        tag = (
            "ERR " + row["error"][:80]
            if row["error"]
            else "$%s %ss" % (row["cost_usd"], row["seconds"])
        )
        print("  %-38s %-14s %s" % (m, p["id"], tag), flush=True)
        return tag

    def spent_now():
        return sum(r.get("cost_usd") or 0 for r in rows.values())

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))
    print("spent %.4f of cap %.2f" % (spent_now(), cap))
    return res_path


def norm(s):
    s = unicodedata.normalize("NFKC", s).upper()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split())


def ocr(spec):
    from rapidocr_onnxruntime import RapidOCR

    root = bench_dir(spec)
    out_path = os.path.join(root, "ocr.json")
    out = load_json(out_path, {})
    eng = RapidOCR()
    for m in spec["models"]:
        for p in spec["prompts"]:
            k = "%s|%s" % (m, p["id"])
            path = os.path.join(root, "images", slug(m), p["id"] + ".png")
            if k in out or not os.path.exists(path):
                continue
            result, _ = eng(path)
            lines = [{"text": t, "score": round(float(s), 3)} for _, t, s in (result or [])]
            out[k] = {
                "lines": lines,
                "joined": " ".join(x["text"] for x in lines if x["score"] >= 0.5),
            }
            save_json(out_path, out)
    print("ocr: %d pictures read -> %s" % (len(out), os.path.relpath(out_path, _env.ROOT)))
    return out


def ocr_verdict(check, reading):
    joined = norm(reading.get("joined", "")) if reading else ""
    if check["type"] == "ocr_contains":
        # spaces do not count: RapidOCR runs words together ("EVERYFRIDAY", "10AM") on lettering
        # that has the space, which was 10 of the 11 OCR fails in the October 2026 run; the
        # judge's spelling check reads the lettering itself
        return norm(check["expect"]).replace(" ", "") in joined.replace(" ", "")
    if check["type"] == "ocr_none":
        real = [
            x
            for x in (reading or {}).get("lines", [])
            if x["score"] >= 0.6 and len(norm(x["text"])) >= 2
        ]
        return not real
    return None


def packets(spec, seed=20261025):
    from PIL import Image

    root = bench_dir(spec)
    pdir = os.path.join(root, "packets")
    os.makedirs(pdir, exist_ok=True)
    rnd = random.Random(seed)
    key = {}
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for p in spec["prompts"]:
        models = [
            m
            for m in spec["models"]
            if os.path.exists(os.path.join(root, "images", slug(m), p["id"] + ".png"))
        ]
        rnd.shuffle(models)
        imgs = []
        key[p["id"]] = {}
        for i, m in enumerate(models):
            lab = letters[i]
            key[p["id"]][lab] = m
            src = os.path.join(root, "images", slug(m), p["id"] + ".png")
            dst = os.path.join(pdir, "%s-%s.jpg" % (p["id"], lab))
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((1024, 1024))
                im.save(dst, "JPEG", quality=90)
            imgs.append({"label": lab, "path": dst})
        checks = [{"id": c["id"], "q": c["q"]} for c in p["checks"] if c["type"] == "judge"]
        save_json(
            os.path.join(pdir, p["id"] + ".json"),
            {"prompt": p["id"], "text": p["prompt"], "checks": checks, "images": imgs},
        )
    save_json(os.path.join(pdir, "key.json"), key)
    print(
        "packets: %d prompts -> %s (key.json holds the letters)"
        % (len(spec["prompts"]), os.path.relpath(pdir, _env.ROOT))
    )


def grids(spec, root, labels):
    """One labelled grid per prompt (model names shown), for publishing."""
    from PIL import Image, ImageDraw, ImageFont

    gdir = os.path.join(root, "grids")
    os.makedirs(gdir, exist_ok=True)
    try:
        font = ImageFont.truetype(os.path.join(_env.ROOT, "fonts", "Inter-VF.ttf"), 26)
    except OSError:
        font = ImageFont.load_default()
    for p in spec["prompts"]:
        tiles = [
            (labels.get(m, m), os.path.join(root, "images", slug(m), p["id"] + ".png"))
            for m in spec["models"]
        ]
        tiles = [t for t in tiles if os.path.exists(t[1])]
        if not tiles:
            continue
        cols = 4 if len(tiles) in (7, 8) else (5 if len(tiles) > 8 else 3)
        cell, pad, cap = 384, 12, 40
        rows_n = (len(tiles) + cols - 1) // cols
        sheet = Image.new(
            "RGB", (cols * (cell + pad) + pad, rows_n * (cell + cap + pad) + pad), "white"
        )
        d = ImageDraw.Draw(sheet)
        for i, (lab, path) in enumerate(tiles):
            x = pad + (i % cols) * (cell + pad)
            y = pad + (i // cols) * (cell + cap + pad)
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((cell, cell))
                sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
            d.text((x, y + cell + 6), lab, fill=(20, 20, 20), font=font)
        sheet.save(os.path.join(gdir, p["id"] + ".jpg"), "JPEG", quality=88)


def kappa(pairs):
    """Cohen's kappa for two raters' yes/no answers [(a, b), ...]."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def reconcile(spec):
    root = bench_dir(spec)
    key = load_json(os.path.join(root, "packets", "key.json"), {})
    pairs, disputes = [], []
    for p in spec["prompts"]:
        va = load_json(os.path.join(root, "verdicts_a", p["id"] + ".json"), {"answers": []})
        vb = load_json(os.path.join(root, "verdicts_b", p["id"] + ".json"), {"answers": []})
        vc = load_json(os.path.join(root, "verdicts_c", p["id"] + ".json"), {"answers": []})
        if va.get("answers") and not vb.get("answers"):
            # only one judge finished this prompt: its answers stand, marked as single-judge
            ans = [dict(x, how="single judge") for x in va["answers"]]
            save_json(
                os.path.join(root, "verdicts", p["id"] + ".json"),
                {"prompt": p["id"], "answers": ans},
            )
            continue
        A = {(x.get("label"), x.get("check")): x for x in va.get("answers", [])}
        B = {(x.get("label"), x.get("check")): x for x in vb.get("answers", [])}
        C = {(x.get("label"), x.get("check")): x for x in vc.get("answers", [])}
        merged = []
        for k in sorted(set(A) | set(B)):
            a = str((A.get(k) or {}).get("answer", "")).strip().lower() == "yes"
            b = str((B.get(k) or {}).get("answer", "")).strip().lower() == "yes"
            if k in A and k in B:
                pairs.append((a, b))
            if k in A and k in B and a == b:
                merged.append(
                    {
                        "label": k[0],
                        "check": k[1],
                        "answer": "yes" if a else "no",
                        "note": (A[k].get("note") or B[k].get("note") or ""),
                        "how": "agreed",
                    }
                )
            elif k in C:
                merged.append(
                    {
                        "label": k[0],
                        "check": k[1],
                        "answer": C[k].get("answer", "no"),
                        "note": C[k].get("note", ""),
                        "how": "third judge",
                    }
                )
                disputes.append(
                    {
                        "prompt": p["id"],
                        "label": k[0],
                        "check": k[1],
                        "model": key.get(p["id"], {}).get(k[0]),
                        "a": (A.get(k) or {}).get("answer"),
                        "b": (B.get(k) or {}).get("answer"),
                        "c": C[k].get("answer"),
                        "a_note": (A.get(k) or {}).get("note"),
                        "b_note": (B.get(k) or {}).get("note"),
                        "c_note": C[k].get("note"),
                        "settled": True,
                    }
                )
            else:
                merged.append(
                    {
                        "label": k[0],
                        "check": k[1],
                        "answer": "no",
                        "how": "disputed",
                        "note": "a: %s / b: %s"
                        % ((A.get(k) or {}).get("note", ""), (B.get(k) or {}).get("note", "")),
                    }
                )
                disputes.append(
                    {
                        "prompt": p["id"],
                        "label": k[0],
                        "check": k[1],
                        "model": key.get(p["id"], {}).get(k[0]),
                        "a": (A.get(k) or {}).get("answer"),
                        "b": (B.get(k) or {}).get("answer"),
                        "a_note": (A.get(k) or {}).get("note"),
                        "b_note": (B.get(k) or {}).get("note"),
                        "settled": False,
                    }
                )
        save_json(
            os.path.join(root, "verdicts", p["id"] + ".json"),
            {"prompt": p["id"], "answers": merged},
        )
    # OCR vs judge on the same text fact: the checks that ask the judge about words OCR also reads
    readings = load_json(os.path.join(root, "ocr.json"), {})
    twins = {"p01-sign": [("ocr-1", "j-1"), ("ocr-2", "j-2")], "p10-product": [("ocr-1", "j-1")]}
    ocr_vs = []
    for pid, links in twins.items():
        prm = next(x for x in spec["prompts"] if x["id"] == pid)
        v = load_json(os.path.join(root, "verdicts", pid + ".json"), {"answers": []})
        J = {(x["label"], x["check"]): x["answer"] == "yes" for x in v["answers"]}
        for lab, m in key.get(pid, {}).items():
            for oc, jc in links:
                chk = next(c for c in prm["checks"] if c["id"] == oc)
                o = bool(ocr_verdict(chk, readings.get("%s|%s" % (m, pid))))
                if (lab, jc) in J:
                    ocr_vs.append((o, J[(lab, jc)]))
    ag = {
        "judge_pairs": len(pairs),
        "raw_agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else None,
        "kappa": kappa(pairs),
        "disputes": len(disputes),
        "settled_by_third_judge": sum(1 for d in disputes if d["settled"]),
        "open_disputes": sum(1 for d in disputes if not d["settled"]),
        "ocr_vs_judge_pairs": len(ocr_vs),
        "ocr_vs_judge_agreement": round(sum(a == b for a, b in ocr_vs) / len(ocr_vs), 4)
        if ocr_vs
        else None,
        "ocr_yes_judge_no": sum(1 for a, b in ocr_vs if a and not b),
        "ocr_no_judge_yes": sum(1 for a, b in ocr_vs if b and not a),
    }
    save_json(os.path.join(root, "agreement.json"), ag)
    save_json(os.path.join(root, "disputes.json"), disputes)
    print(
        "judges: %s pairs, agreement %s, kappa %s, %d disputes (%d settled by a third judge,"
        " %d open); OCR vs judge %s on %d text facts"
        % (
            ag["judge_pairs"],
            ag["raw_agreement"],
            ag["kappa"],
            len(disputes),
            ag["settled_by_third_judge"],
            ag["open_disputes"],
            ag["ocr_vs_judge_agreement"],
            ag["ocr_vs_judge_pairs"],
        )
    )
    return [d for d in disputes if not d["settled"]]


def score(spec):
    root = bench_dir(spec)
    rows = load_json(os.path.join(root, "results.json"), {})
    readings = load_json(os.path.join(root, "ocr.json"), {})
    key = load_json(os.path.join(root, "packets", "key.json"), {})
    verdicts = {}
    for p in spec["prompts"]:
        v = load_json(os.path.join(root, "verdicts", p["id"] + ".json"), None)
        if v:
            for a in v.get("answers", []):
                m = key.get(p["id"], {}).get(a.get("label"))
                if m:
                    verdicts[(m, p["id"], a.get("check"))] = a
    labels = spec.get("labels", {})
    out = {
        "models": {},
        "prompts": [p["id"] for p in spec["prompts"]],
        "unanswered": [],
        "checks": [],
    }
    for m in spec["models"]:
        per_prompt, per_ability, cost, secs, errors = {}, {}, [], [], 0
        for p in spec["prompts"]:
            r = rows.get("%s|%s" % (m, p["id"]))
            if not r or r.get("error"):
                errors += 1
                per_prompt[p["id"]] = 0.0
                for ab in p["ability"]:
                    per_ability.setdefault(ab, []).append(0.0)
                continue
            if r.get("cost_usd") is not None:
                cost.append(r["cost_usd"])
            if r.get("seconds") is not None:
                secs.append(r["seconds"])
            passed = []
            for c in p["checks"]:
                if c["type"] == "judge":
                    a = verdicts.get((m, p["id"], c["id"]))
                    ok = bool(a) and str(a.get("answer", "")).strip().lower() == "yes"
                    if not a:
                        out["unanswered"].append([m, p["id"], c["id"]])
                else:
                    ok = bool(ocr_verdict(c, readings.get("%s|%s" % (m, p["id"]))))
                passed.append(ok)
                out["checks"].append(
                    {
                        "model": m,
                        "prompt": p["id"],
                        "check": c["id"],
                        "type": c["type"],
                        "pass": ok,
                        "note": (verdicts.get((m, p["id"], c["id"])) or {}).get("note"),
                    }
                )
            frac = sum(passed) / len(passed) if passed else 0.0
            per_prompt[p["id"]] = round(frac, 4)
            for ab in p["ability"]:
                per_ability.setdefault(ab, []).append(frac)
        out["models"][m] = {
            "label": labels.get(m, m),
            "overall": round(sum(per_prompt.values()) / len(per_prompt), 4) if per_prompt else 0.0,
            "abilities": {k: round(sum(v) / len(v), 4) for k, v in per_ability.items()},
            "prompts": per_prompt,
            "cost_per_picture_usd": round(sum(cost) / len(cost), 4) if cost else None,
            "seconds_median": round(statistics.median(secs), 2) if secs else None,
            "errors": errors,
        }
    save_json(os.path.join(root, "scores.json"), out)
    grids(spec, root, labels)
    print("%-36s %8s %10s %8s  %s" % ("model", "overall", "$/picture", "sec p50", "abilities"))
    for _m, s in sorted(out["models"].items(), key=lambda kv: -kv[1]["overall"]):
        ab = " ".join("%s=%.0f%%" % (k, v * 100) for k, v in sorted(s["abilities"].items()))
        print(
            "%-36s %7.0f%% %10s %8s  %s"
            % (
                s["label"][:36],
                s["overall"] * 100,
                s["cost_per_picture_usd"],
                s["seconds_median"],
                ab,
            )
        )
    if out["unanswered"]:
        print("%d judge checks have no verdict yet" % len(out["unanswered"]))
    return os.path.join(root, "scores.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True, help="bench spec JSON (config/bench/*.json)")
    ap.add_argument("--plan", action="store_true", help="price the run; make nothing")
    ap.add_argument("--run", action="store_true", help="make the missing pictures")
    ap.add_argument(
        "--cap", type=float, default=None, help="USD cap for --run (default: the spec's cap_usd)"
    )
    ap.add_argument("--workers", type=int, default=6, help="pictures made at once")
    ap.add_argument("--ocr", action="store_true", help="read every picture with RapidOCR")
    ap.add_argument("--packets", action="store_true", help="write the blind judge packets")
    ap.add_argument(
        "--reconcile", action="store_true", help="merge two judges (and a third on disputes)"
    )
    ap.add_argument("--score", action="store_true", help="join everything into scores.json")
    a = ap.parse_args()
    spec = load_spec(a.spec)
    if a.plan:
        plan(spec)
    if a.run:
        cap = a.cap if a.cap is not None else float(spec.get("cap_usd") or 0)
        if cap <= 0:
            sys.exit("--run needs --cap or the spec's cap_usd")
        out = run(spec, cap, a.workers)
        _project.record(
            spec["id"],
            "image bench run: %d models x %d prompts" % (len(spec["models"]), len(spec["prompts"])),
            out=out,
            script=__file__,
            argv=sys.argv[1:],
            kind="image-bench",
            manifest=spec["_path"],
        )
    if a.ocr:
        ocr(spec)
    if a.packets:
        packets(spec)
    if a.reconcile:
        reconcile(spec)
    if a.score:
        out = score(spec)
        _project.record(
            spec["id"],
            "image bench scored",
            out=out,
            script=__file__,
            argv=sys.argv[1:],
            kind="image-bench",
            manifest=spec["_path"],
        )


if __name__ == "__main__":
    main()
