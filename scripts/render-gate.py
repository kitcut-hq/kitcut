#!/usr/bin/env python
"""The acceptance gate: prove the finished film shows none of the secrets --
and when it does, patch the manifest so the next render will not.

Why this exists as its own tool, and why it is shaped like this:

  A gate that SAMPLES is not a gate. A scan at one frame every two seconds
  read "clean" while the card number sat in a Notepad window title on frames
  it never visited. Dense OCR then found it -- at 10-25 minutes a pass, four
  passes in one session.

  So pass A does not OCR. It takes every template the tracker knows (the
  secrets' own pixels, pooled across the session's recordings) and runs
  normalized cross-correlation against the RENDER at 1 fps. It is exact --
  a match on the output IS the secret on the output -- and it costs minutes,
  because NCC is cheap and there is nothing to skip. Pass B is a light OCR at
  0.25 fps for whatever has no template (a name, a field OCR read only here).

  A hit is reported in FILM time and canvas fractions, which is useless to a
  manifest that speaks SOURCE time and source fractions. Two transforms sit
  in between -- the cut (segments dropped, others run at 3x or 19x) and the
  pad (a 1818-wide frame centred in a 1920 canvas) -- and doing them by hand
  is how a patch lands a row off. --patch does both and appends a hand rect
  to the source it came from, with the reason, so the next render is one
  cached piece and the loop converges instead of being re-argued.

  Two things the first version got wrong, both found when a four-round loop
  patched the same three rects three times and the film did not change:

  - It sampled the render with the `fps` filter, which labels the SLOT, not
    the frame (KI-006, again). The frame it called 133.0 s was at 133.47 s,
    and the film runs at 19x there, so the label mapped to source 46.6 s
    while the sharp pixels were at 55.5 s -- 6 s outside every window it
    wrote. Sampling is scan-pii's `frames_of`: `select` + `showinfo`, the
    frame's own pts.
  - A hit is one sampled frame; the leak is a SPAN. So every template hit is
    refined at full rate over the interval between its neighbouring samples
    (60 frames, one template, sub-second), and the patch window is the span
    the secret was actually sharp for, mapped back through the cut, plus a
    second each side -- not ±3 s around a guess.

Invoke as:  python scripts/render-gate.py --manifest projects/<id>/screen.json
"""
import sys
import os
import json
import argparse
import subprocess
import time
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import _project  # noqa: E402

ROOT = _env.ROOT
HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load(name):
    """Import a hyphenated sibling script by path."""
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fmt(t):
    return f"{int(t) // 60}:{t % 60:04.1f}"


def build_plans(sc, man, mpath, cfg):
    """The same plan list screen-cut renders from, so film time maps back."""
    plans = []
    for s in man["sources"]:
        if s.get("skip"):
            continue
        p = sc.plan_source(s, cfg)
        chosen = _env.resolve(s["path"])
        if s.get("proxy") and os.path.exists(_env.resolve(s["proxy"])):
            chosen = _env.resolve(s["proxy"])
        p["path"] = chosen
        p["source_path"] = _env.resolve(s["path"])
        p["info"] = sc.probe(chosen)
        p["src_entry"] = s
        plans.append(p)
    return plans


def locate(plans, film_t):
    t = 0.0
    for p in plans:
        for seg in p["segments"]:
            if t <= film_t < t + seg["out"]:
                return p, seg["start"] + (film_t - t) * seg["speed"]
            t += seg["out"]
    return None, None


def is_cfr(path):
    """r_frame_rate == avg_frame_rate, which is what a `fps=`-closed graph
    muxed by NVENC produces; a stream-copied concat of such pieces keeps it."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate,avg_frame_rate", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip().split(",")
    def f(x):
        n, _, d = x.partition("/")
        return float(n) / float(d) if d and float(d) else 0.0
    return len(out) == 2 and abs(f(out[0]) - f(out[1])) < 1e-3


def speed_at(plans, film_t):
    t = 0.0
    for p in plans:
        for seg in p["segments"]:
            if t <= film_t < t + seg["out"]:
                return seg["speed"]
            t += seg["out"]
    return 1.0


def frames_around(render, fps, t0, t1, w, h):
    """Every frame of the render in [t0, t1), gray, with its own time.

    The render is our own output and CFR by construction (`fps=` closes every
    piece's graph), which the caller asserts rather than assumes: frame i
    after a seek to t0 is at t0 + i / fps only if the file really is
    constant-rate.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}",
         "-i", render, "-vf", f"scale={w}:{h}", "-pix_fmt", "gray",
         "-f", "rawvideo", "-"], stdout=subprocess.PIPE, check=True)
    n = w * h
    for i in range(len(r.stdout) // n):
        yield t0 + i / fps, np.frombuffer(r.stdout[i * n:(i + 1) * n],
                                          np.uint8).reshape(h, w)


def refine(hits, render, fps, tpl_by_key, cw, ch, half_window, tb):
    """Turn each sampled template hit into the film SPAN it is sharp for.

    A sample says "sharp at 133.47 s"; the manifest needs "sharp from
    133.40 to 133.83", because that is what the rect must cover after it is
    mapped through a 3x or 19x stretch. Search the one template in a padded
    window around its own hit, over the frames between the neighbouring
    samples. One template, sixty frames: well under a second per hit.
    """
    pad = 14
    for h in hits:
        if h["via"] != "template":
            continue
        x, y, w, hh = h["rect"]
        px, py, pw, ph = int(x * cw), int(y * ch), int(w * cw), int(hh * ch)
        tpls = tpl_by_key.get(h["key"], [])
        sharp = []
        for t, fr in frames_around(render, fps, max(0.0, h["t"] - half_window),
                                   h["t"] + half_window, cw, ch):
            win = fr[max(0, py - pad):py + ph + pad, max(0, px - pad):px + pw + pad]
            for tp in tpls:
                th, tw = tp["img"].shape[:2]
                if win.shape[0] < th or win.shape[1] < tw:
                    continue
                thr = tb.THR_SMALL if th * tw < tb.SMALL_TPL_AREA else tb.THR
                if cv2.matchTemplate(win, tp["img"], cv2.TM_CCOEFF_NORMED).max() >= thr:
                    sharp.append(t)
                    break
        if sharp:
            h["film_span"] = [round(min(sharp), 3), round(max(sharp), 3)]
        else:
            # cannot happen for a hit that came from a real frame, unless the
            # seek landed elsewhere; cover the whole unsampled interval
            h["film_span"] = [round(h["t"] - half_window, 3), round(h["t"] + half_window, 3)]
            h["refine"] = "no match on re-read; covering the interval"


def canvas_to_source(p, cfg, x, y, w, h):
    """Canvas fractions -> source fractions, undoing the centred pad."""
    cw, ch = cfg["canvas"]
    f = min(cw / p["info"]["width"], ch / p["info"]["height"])
    vw = max(2, int(round(p["info"]["width"] * f)) // 2 * 2)
    vh = max(2, int(round(p["info"]["height"] * f)) // 2 * 2)
    ox, sx = (cw - vw) / 2.0 / cw, vw / float(cw)
    oy, sy = (ch - vh) / 2.0 / ch, vh / float(ch)
    return [(x - ox) / sx, (y - oy) / sy, w / sx, h / sy]


def overlap(a, b):
    """Intersection over the smaller rect, both [x, y, w, h] fractions."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / max(1e-9, min(a[2] * a[3], b[2] * b[3]))


def union(a, b):
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)]


def pools(tb, man, mpath, plans):
    """Templates per geometry, pooled from every same-geometry scan."""
    pdir = os.path.dirname(mpath)
    benign = man.get("benign_text") or []
    by_geo = {}
    for p in plans:
        info = tb.probe(p["path"])
        geo = (info["w"], info["h"])
        base = os.path.splitext(os.path.basename(p["source_path"]))[0]
        pii = os.path.join(pdir, "temp", "pii", base + ".pii.json")
        if os.path.exists(pii):
            by_geo.setdefault(geo, {"src": p["path"], "info": info, "pii": []})["pii"].append(pii)
    out = {}
    for geo, d in by_geo.items():
        kinds = set(man.get("blur_kinds") or tb.KINDS)
        out[geo] = tb.collect_templates(d["src"], d["pii"], benign, kinds, d["info"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--render", help="default: the manifest's output")
    ap.add_argument("--fps", type=float, default=1.0, help="template pass rate")
    ap.add_argument("--ocr-fps", type=float, default=0.25,
                    help="OCR pass rate; 0 disables the OCR pass")
    ap.add_argument("--target", default=None,
                    help="the --target the film was rendered with, if any")
    ap.add_argument("--patch", action="store_true",
                    help="append a hand rect to the manifest for every hit")
    ap.add_argument("--out", help="default: <project>/temp/gate.json")
    args = ap.parse_args()

    sc = load("screen-cut")
    tb = load("track-blur")
    sp = load("scan-pii")
    mpath = _env.resolve(args.manifest)
    man = json.load(open(mpath, encoding="utf-8"))
    cfg = dict(sc.DEFAULTS)
    cfg.update(man.get("cut") or {})
    if args.target:
        cfg = sc.solve_target(man, cfg, sc.parse_hms(args.target))
    render = _env.resolve(args.render or man["output"])
    plans = build_plans(sc, man, mpath, cfg)
    cw, ch = cfg["canvas"]
    rinfo = sc.probe(render)
    print(f"gate: {os.path.basename(render)}  {fmt(rinfo['duration'])}  "
          f"{len(plans)} source(s)")

    # ---- pass A: the secrets' own pixels against the render
    clock = time.time()

    def lap(what):
        nonlocal clock
        print(f"  [{what} {fmt(time.time() - clock)}]", file=sys.stderr)
        clock = time.time()

    tpl_by_geo = pools(tb, man, mpath, plans)
    lap("templates")
    all_tpls = [t for ts in tpl_by_geo.values() for t in ts]
    print(f"  pass A: {len(all_tpls)} template(s) from {len(tpl_by_geo)} geometr(y/ies), "
          f"NCC at {args.fps} fps")
    tpl_by_key = {}
    for tp in all_tpls:
        tpl_by_key.setdefault(tp["key"], []).append(tp)
    hits = []
    # frames_of, not `fps=`: the frame's own pts (see the docstring)
    for t, img in sp.frames_of(render, args.fps, cw):
        fr = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if fr.shape != (ch, cw):
            fr = cv2.resize(fr, (cw, ch))
        fr_half = cv2.resize(fr, (cw // 2, ch // 2))
        found = {}
        for tpl in all_tpls:
            # the render is at proxy scale, so a secret at another size is
            # already its own template; the zoom-transition scales are not needed
            for x, y, w, h in tb.full_search(fr_half, fr, tpl, scales=(1.0,)):
                # one hit per secret per frame: several templates of the same
                # secret (sizes, renderings) land on the same pixels
                r = found.get(tpl["key"])
                if r:
                    x0, y0 = min(r[0], x), min(r[1], y)
                    x1, y1 = max(r[0] + r[2], x + w), max(r[1] + r[3], y + h)
                    found[tpl["key"]] = [x0, y0, x1 - x0, y1 - y0, r[4], r[5]]
                else:
                    found[tpl["key"]] = [x, y, w, h, tpl["kind"], tpl["text"]]
        for key, (x, y, w, h, kind, text) in found.items():
            hits.append({"t": round(t, 3), "kind": kind, "key": key, "text": text,
                         "via": "template", "rect": [x / cw, y / ch, w / cw, h / ch]})
        if int(t) % 60 == 0 and t > 0:
            print(f"    ...{fmt(t)}  {len(hits)} hit(s)", file=sys.stderr)
    lap("pass A")
    if not is_cfr(render):
        raise SystemExit("render is not CFR; cannot refine hits by frame index")
    refine(hits, render, rinfo["fps"], tpl_by_key, cw, ch, 1.0 / args.fps, tb)
    lap("refine")

    # ---- pass B: light OCR for what has no template
    if args.ocr_fps > 0:
        frames = sp.ocr_pass(render, args.ocr_fps, 1600, 0.004)
        benign = [b.replace(" ", "") for b in (man.get("benign_text") or [])]
        kinds = set(man.get("blur_kinds") or tb.KINDS)
        for h in sp.apply_rules(frames):
            if h["kind"] not in kinds:
                continue
            if any(b in h["text"].replace(" ", "") for b in benign):
                continue
            hits.append({"t": h["t"], "kind": h["kind"], "key": tb.norm_key(h["kind"], h["text"]),
                         "text": h["text"], "via": "ocr", "rect": h["rect"]})
        print(f"  pass B: OCR at {args.ocr_fps} fps -> "
              f"{sum(1 for h in hits if h['via'] == 'ocr')} hit(s)")
        lap("pass B")

    # ---- map every hit back to its source
    for h in hits:
        a, b = h.get("film_span") or [h["t"], h["t"]]
        p, st = locate(plans, a)
        if p is None:
            h["source"], h["source_t"] = None, None
            continue
        p1, st1 = locate(plans, b)
        if p1 is not p:
            # the span crosses a join between two sources; cover this source
            # to the end of its film time and let the next sample carry the rest
            st1 = st + (b - a) * speed_at(plans, a)
        if h["via"] != "template":
            # an OCR hit is one sampled frame with no template to refine by:
            # the secret can be anywhere in the interval between samples
            reach = speed_at(plans, a) / max(args.ocr_fps, 1e-6)
            st, st1 = st - reach, st1 + reach
        h["source"] = os.path.basename(p["source_path"])
        h["source_t"] = round(st, 2)
        h["source_t1"] = round(max(st, st1), 2)
        h["source_rect"] = [round(v, 4) for v in canvas_to_source(p, cfg, *h["rect"])]

    keys = sorted({h["key"] for h in hits})
    print(f"\n  {len(hits)} hit(s), {len(keys)} distinct secret(s)")
    by_src = {}
    for h in hits:
        by_src.setdefault(h["source"], []).append(h)
    for src, hs in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
        ks = sorted({x["key"] for x in hs})
        print(f"    {str(src):<34} {len(hs):>4} hit(s)  {', '.join(ks[:4])}"
              f"{' …' if len(ks) > 4 else ''}")
    for h in sorted(hits, key=lambda x: x["t"])[:12]:
        print(f"      {fmt(h['t']):>7}  {h['kind']:<7} {h['via']:<8} "
              f"-> {h['source']} @ {fmt(h['source_t']) if h['source_t'] is not None else '?'}")

    out = _env.resolve(args.out) if args.out else os.path.join(
        os.path.dirname(mpath), "temp", "gate.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"render": render, "hits": hits, "secrets": keys}, f,
                  ensure_ascii=False, indent=1)

    if args.patch and hits:
        # One rect per (source, secret, contiguous span). A rect that already
        # exists for the same secret and overlaps is EXTENDED, not duplicated:
        # the first loop appended the same rect three times and changed
        # nothing, because its window was wrong and never widened.
        added = extended = 0
        for s in man["sources"]:
            base = os.path.basename(s["path"])
            mine = [h for h in hits if h["source"] == base and h.get("source_rect")]
            if not mine:
                continue
            extra = list(s.get("blur_extra") or [])
            by_key = {}
            for h in mine:
                by_key.setdefault(h["key"], []).append(h)
            for key, hs in by_key.items():
                hs.sort(key=lambda h: h["source_t"])
                spans = []
                for h in hs:
                    t0, t1 = h["source_t"] - 1.0, h["source_t1"] + 1.0
                    if spans and t0 <= spans[-1]["t1"] + 0.5:
                        spans[-1]["t1"] = max(spans[-1]["t1"], t1)
                        spans[-1]["hs"].append(h)
                    else:
                        spans.append({"t0": t0, "t1": t1, "hs": [h]})
                for sp_ in spans:
                    xs = [h["source_rect"] for h in sp_["hs"]]
                    x0 = max(0.0, min(r[0] for r in xs) - 0.006)
                    y0 = max(0.0, min(r[1] for r in xs) - 0.010)
                    x1 = min(1.0, max(r[0] + r[2] for r in xs) + 0.006)
                    y1 = min(1.0, max(r[1] + r[3] for r in xs) + 0.010)
                    when = [round(max(0.0, sp_["t0"]), 1), round(sp_["t1"], 1)]
                    rect = [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)]
                    first = fmt(min(h["t"] for h in sp_["hs"]))
                    hit = None
                    for b in extra:
                        if key not in b.get("_why", "") or not b.get("when"):
                            continue
                        if overlap(b["rect"], rect) > 0.3 and \
                                b["when"][0] <= when[1] + 0.5 and when[0] <= b["when"][1] + 0.5:
                            hit = b
                            break
                    if hit:
                        hit["rect"] = union(hit["rect"], rect)
                        hit["when"] = [min(hit["when"][0], when[0]), max(hit["when"][1], when[1])]
                        hit["_why"] += f"; extended: still sharp at {first}"
                        extended += 1
                    else:
                        extra.append({
                            "_why": f"render-gate: {key} sharp in the film at {first}; "
                                    f"span mapped back through the cut and the pad",
                            "rect": rect, "when": when})
                        added += 1
            s["blur_extra"] = extra
            s["blur"] = [b for b in (s.get("blur") or []) if b not in extra] + extra
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
        print(f"\n  --patch: {added} hand rect(s) appended, {extended} extended, in "
              f"{args.manifest}; re-render (cached pieces) and gate again")

    pid = os.path.basename(_project.find_project_dir(mpath) or "")
    if pid:
        _project.record(pid, "render-gate",
                        note=f"{len(hits)} hit(s), {len(keys)} secret(s) on "
                             f"{os.path.basename(render)}"
                             + (f"; patched {added} rect(s)" if args.patch and hits else ""))
    raise SystemExit(1 if hits else 0)


if __name__ == "__main__":
    main()
