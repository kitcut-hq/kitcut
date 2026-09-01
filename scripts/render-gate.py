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

Invoke as:  python scripts/render-gate.py --manifest projects/<id>/screen.json
"""
import sys
import os
import json
import argparse
import subprocess
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


def gray_stream(path, w, h, fps):
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path,
         "-vf", f"fps={fps},scale={w}:{h}", "-pix_fmt", "gray",
         "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h
    i = 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield i / fps, np.frombuffer(buf, np.uint8).reshape(h, w)
        i += 1
    p.stdout.close()
    p.wait()


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


def canvas_to_source(p, cfg, x, y, w, h):
    """Canvas fractions -> source fractions, undoing the centred pad."""
    cw, ch = cfg["canvas"]
    f = min(cw / p["info"]["width"], ch / p["info"]["height"])
    vw = max(2, int(round(p["info"]["width"] * f)) // 2 * 2)
    vh = max(2, int(round(p["info"]["height"] * f)) // 2 * 2)
    ox, sx = (cw - vw) / 2.0 / cw, vw / float(cw)
    oy, sy = (ch - vh) / 2.0 / ch, vh / float(ch)
    return [(x - ox) / sx, (y - oy) / sy, w / sx, h / sy]


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
    tpl_by_geo = pools(tb, man, mpath, plans)
    all_tpls = [t for ts in tpl_by_geo.values() for t in ts]
    print(f"  pass A: {len(all_tpls)} template(s) from {len(tpl_by_geo)} geometr(y/ies), "
          f"NCC at {args.fps} fps")
    hits = []
    for t, fr in gray_stream(render, cw, ch, args.fps):
        fr_half = cv2.resize(fr, (cw // 2, ch // 2))
        for tpl in all_tpls:
            # the render is at proxy scale, so a secret at another size is
            # already its own template; the zoom-transition scales are not needed
            for x, y, w, h in tb.full_search(fr_half, fr, tpl, scales=(1.0,)):
                hits.append({"t": round(t, 2), "kind": tpl["kind"], "key": tpl["key"],
                             "text": tpl["text"], "via": "template",
                             "rect": [x / cw, y / ch, w / cw, h / ch]})
        if int(t) % 60 == 0 and t > 0:
            print(f"    ...{fmt(t)}  {len(hits)} hit(s)", file=sys.stderr)

    # ---- pass B: light OCR for what has no template
    if args.ocr_fps > 0:
        sp = load("scan-pii")
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

    # ---- map every hit back to its source
    for h in hits:
        p, st = locate(plans, h["t"])
        if p is None:
            h["source"], h["source_t"] = None, None
            continue
        h["source"] = os.path.basename(p["source_path"])
        h["source_t"] = round(st, 2)
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
        # One rect per (source, secret, ~6 s window): the hits are dense in
        # time and the manifest wants a few honest rects, not hundreds.
        added = 0
        for s in man["sources"]:
            base = os.path.basename(s["path"])
            mine = [h for h in hits if h["source"] == base and h.get("source_rect")]
            if not mine:
                continue
            extra = list(s.get("blur_extra") or [])
            groups = {}
            for h in mine:
                g = (h["key"], int(h["source_t"] // 6))
                groups.setdefault(g, []).append(h)
            for (key, _), hs in groups.items():
                xs = [h["source_rect"] for h in hs]
                x0 = max(0.0, min(r[0] for r in xs) - 0.006)
                y0 = max(0.0, min(r[1] for r in xs) - 0.010)
                x1 = min(1.0, max(r[0] + r[2] for r in xs) + 0.006)
                y1 = min(1.0, max(r[1] + r[3] for r in xs) + 0.010)
                t0 = min(h["source_t"] for h in hs) - 3.0
                t1 = max(h["source_t"] for h in hs) + 3.0
                extra.append({
                    "_why": f"render-gate: {key} still visible in the film at "
                            f"{fmt(min(h['t'] for h in hs))}; mapped back through "
                            f"the cut and the pad",
                    "rect": [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)],
                    "when": [round(max(0.0, t0), 1), round(t1, 1)]})
                added += 1
            s["blur_extra"] = extra
            s["blur"] = [b for b in (s.get("blur") or []) if b not in extra] + extra
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
        print(f"\n  --patch: {added} hand rect(s) appended to {args.manifest}; "
              f"re-render (cached pieces) and gate again")

    pid = os.path.basename(_project.find_project_dir(mpath) or "")
    if pid:
        _project.record(pid, "render-gate",
                        note=f"{len(hits)} hit(s), {len(keys)} secret(s) on "
                             f"{os.path.basename(render)}"
                             + (f"; patched {added} rect(s)" if args.patch and hits else ""))
    raise SystemExit(1 if hits else 0)


if __name__ == "__main__":
    main()
