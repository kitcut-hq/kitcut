#!/usr/bin/env python
"""Show every redaction before a single frame is encoded -- and stop.

The most expensive mistake of the first silent-screencast edit was not a
bug. The full film was rendered five times with a look the user had never
seen -- black boxes, then pixelated panels, then two sources cut -- and the
user had asked for a blur. About an hour and a half of a six-hour session
went to encoding a decision that was never theirs to lose.

So this is a gate. It writes ONE sheet, `temp/review/redaction-sheet.jpg`:
for every secret the tracker follows, its first appearance in each source,
before | after with the real blur applied through the real mask; every
hand-measured rect the same way; and the numbers that matter -- secrets,
templates, hand rects, how much of the frame the blur covers. Then it exits
non-zero. `--approve` records the approval in project.json together with a
fingerprint of what was approved, so the pipeline can tell an approved look
from a changed one, and a render cannot start on a look nobody has seen.

The "after" tile is computed in numpy the way the render's filtergraph does
it (downscale, gaussian, upscale, shown through the mask), so what the sheet
shows is what the film will do, not an approximation of it.

Invoke as:  python scripts/redaction-review.py --manifest projects/<id>/screen.json
"""
import sys
import os
import json
import time
import hashlib
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import _project  # noqa: E402

ROOT = _env.ROOT

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TILE_W, TILE_H = 440, 150      # one before/after crop
PAD = 10


def frame_at(path, t):
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", path,
         "-frames:v", "1", "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
        capture_output=True).stdout
    info = probe(path)
    n = info["w"] * info["h"] * 3
    if len(out) < n:
        return None
    return np.frombuffer(out[:n], np.uint8).reshape(info["h"], info["w"], 3)


_probe_cache = {}


def probe(path):
    if path in _probe_cache:
        return _probe_cache[path]
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate",
         "-show_entries", "format=duration", "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    st = (d.get("streams") or [{}])[0]
    num, _, den = (st.get("avg_frame_rate") or "0/1").partition("/")
    r = {"w": int(st["width"]), "h": int(st["height"]),
         "fps": float(num) / float(den) if float(den or 0) else 30.0,
         "dur": float((d.get("format") or {}).get("duration") or 0.0)}
    _probe_cache[path] = r
    return r


def blur_like_render(img, cfg):
    """The render's blur: scale down, gaussian, scale back up."""
    d = int(cfg.get("blur_downscale", 8))
    sigma = float(cfg.get("blur_sigma", 3.0))
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(2, w // d), max(2, h // d)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


def composite(frame, mask, cfg):
    """Frame shown through a 0..255 mask: blurred where the mask is white."""
    bl = blur_like_render(frame, cfg)
    a = (mask.astype(np.float32) / 255.0)[..., None]
    return (frame * (1 - a) + bl * a).astype(np.uint8)


def crop_around(img, box, out_w=TILE_W, out_h=TILE_H):
    """A tile centred on the box, wide enough to show context."""
    x0, y0, x1, y1 = box
    H, W = img.shape[:2]
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    cw, ch = max(bw * 3, out_w), max(bh * 4, out_h)
    # keep the tile's aspect
    if cw / ch > out_w / out_h:
        ch = int(cw * out_h / out_w)
    else:
        cw = int(ch * out_w / out_h)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    sx, sy = max(0, min(W - cw, cx - cw // 2)), max(0, min(H - ch, cy - ch // 2))
    tile = img[sy:sy + ch, sx:sx + cw]
    return cv2.resize(tile, (out_w, out_h), interpolation=cv2.INTER_AREA)


def label(canvas, text, x, y, color=(235, 235, 235), scale=0.5):
    cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def mask_for_frame(tdir, runs, frame_idx, size):
    """The mask PNG of the run containing this frame."""
    for n, (f0, f1, _boxes) in enumerate(runs):
        if f0 <= frame_idx <= f1:
            p = os.path.join(tdir, f"mask_{n:06d}.png")
            m = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if m is not None:
                return m
            break
    return np.zeros((size[1], size[0]), np.uint8)


def hand_mask(rect, size):
    m = np.zeros((size[1], size[0]), np.uint8)
    x, y, w, h = rect
    x0, y0 = int(x * size[0]), int(y * size[1])
    x1, y1 = int((x + w) * size[0]), int((y + h) * size[1])
    m[y0:y1, x0:x1] = 255
    return cv2.GaussianBlur(m, (9, 9), 0)


def redact_secret(key, kind):
    """Show the reviewer WHICH secret without printing it: first 3, last 2."""
    digits = key.split(":", 1)[-1]
    if len(digits) > 6:
        return f"{kind} {digits[:3]}…{digits[-2:]}"
    return f"{kind} {digits}"


def collect(man, mpath, cfg):
    """Every tile the sheet needs: (title, source, t, before, after, area%)."""
    tiles = []
    stats = {"secrets": set(), "templates": 0, "hand": 0, "coverage": [],
             "sources_tracked": 0, "sources_hand": 0}
    pdir = os.path.dirname(mpath)
    for s in man["sources"]:
        if s.get("skip"):
            continue
        src = _env.resolve(s.get("proxy") or s["path"])
        base = os.path.splitext(os.path.basename(s["path"]))[0]
        info = probe(src)
        size = (info["w"], info["h"])
        tdir = _env.resolve(s["track"]) if s.get("track") else None
        tj = os.path.join(tdir, "track.json") if tdir else None
        if tj and os.path.exists(tj):
            d = json.load(open(tj, encoding="utf-8"))
            runs = d.get("runs") or []
            keys = d.get("keys") or {}
            stats["sources_tracked"] += 1
            stats["templates"] += int(d.get("templates") or 0)
            fps = float(d.get("fps") or info["fps"])
            # coverage, duration-weighted
            tot_f = 0
            for n, (f0, f1, boxes) in enumerate(runs):
                area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1, *_ in boxes)
                stats["coverage"].append((area / float(size[0] * size[1]), f1 - f0 + 1))
                tot_f += f1 - f0 + 1
            first = {}
            for f0, f1, boxes in runs:
                for x0, y0, x1, y1, key in boxes:
                    if key not in first:
                        first[key] = (f0, (x0, y0, x1, y1))
            for key, (f0, box) in sorted(first.items(), key=lambda kv: kv[1][0]):
                stats["secrets"].add(key)
                t = f0 / fps
                fr = frame_at(src, t)
                if fr is None:
                    continue
                m = mask_for_frame(tdir, runs, f0, size)
                after = composite(fr, m, cfg)
                kind = (keys.get(key) or {}).get("kind", key.split(":")[0])
                tiles.append((redact_secret(key, kind), base, t,
                              crop_around(fr, box), crop_around(after, box)))
        for b in s.get("blur") or []:
            stats["hand"] += 1
            stats["sources_hand"] += 1
            w = b.get("when") or [0.0, info["dur"]]
            t = (w[0] + w[1]) / 2.0
            fr = frame_at(src, t)
            if fr is None:
                continue
            m = hand_mask(b["rect"], size)
            after = composite(fr, m, cfg)
            x, y, bw, bh = b["rect"]
            box = (int(x * size[0]), int(y * size[1]),
                   int((x + bw) * size[0]), int((y + bh) * size[1]))
            tiles.append((("hand: " + (b.get("_why") or ""))[:44], base, t,
                          crop_around(fr, box), crop_around(after, box)))
    return tiles, stats


def film_mask(boxes, size, dilate=6):
    """The mask `film-redact.py --blur` will paint for one state's boxes.
    Same dilation and same 9x9 feather, so the tile is the render."""
    W, H = size
    m = np.zeros((H, W), np.uint8)
    dx, dy = dilate / float(W), dilate / float(H)
    for b in boxes:
        x, y, w, h = b["rect"]
        x0, y0 = max(0, int(round((x - dx) * W))), max(0, int(round((y - dy) * H)))
        x1, y1 = min(W, int(round((x + w + dx) * W))), min(H, int(round((y + h + dy) * H)))
        if x1 > x0 and y1 > y0:
            m[y0:y1, x0:x1] = 255
    return cv2.GaussianBlur(m, (9, 9), 0) if boxes else m


def hand_tiles(states, reps, cfg, hand, fps):
    """One tile per manifest `film_blur` rect, on the first state its window
    covers. A hand rect exists because a person saw what the detector could
    not, so it belongs on the sheet beside the detections, not below them."""
    tiles = []
    for b in hand or []:
        w = b.get("when") or [0.0, 1e9]
        hit = next((n for n, s in enumerate(states)
                    if s["i1"] / fps >= float(w[0]) and s["i0"] / fps < float(w[1])),
                   None)
        if hit is None:
            continue
        img = cv2.imread(os.path.join(reps, f"rep_{hit:05d}.png"), cv2.IMREAD_COLOR)
        if img is None:
            continue
        H, W = img.shape[:2]
        one = [{"rect": b["rect"]}]
        after = composite(img, film_mask(one, (W, H)), cfg)
        x, y, bw, bh = b["rect"]
        box = (int(x * W), int(y * H), int((x + bw) * W), int((y + bh) * H))
        tiles.append((("hand: " + (b.get("why") or ""))[:44], f"state {hit}",
                      float(states[hit].get("t") or 0),
                      crop_around(img, box), crop_around(after, box)))
    return tiles


def collect_states(pdir, cfg, per_kind=8, hand=None):
    """The same tiles, for the FILM-time redaction: states.json + detect.json.

    The source-time sheet asks "does this secret's own template look right".
    This one asks the only question left once detection happens on the film:
    "on this screen, is the right side what should go out?" -- and it asks it
    per KIND, not per appearance, because the answer is the same for all
    thirty-four phone numbers and a reviewer should be asked once.
    """
    fd = os.path.join(pdir, "temp", "film")
    sj, dj = os.path.join(fd, "states.json"), os.path.join(fd, "detect.json")
    for p in (sj, dj):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}; run film-redact.py --states --detect first")
    doc = json.load(open(sj, encoding="utf-8"))
    states, reps = doc["states"], os.path.join(fd, "reps")
    per = json.load(open(dj, encoding="utf-8"))["per_state"]
    tiles = []
    stats = {"secrets": set(), "templates": 0, "hand": 0, "coverage": [],
             "sources_tracked": 1, "sources_hand": 0,
             "states": len(states), "states_hit": len(per), "film_s": 0.0}
    seen = {}
    for key in sorted(per, key=int):
        n = int(key)
        boxes = per[key]
        s = states[n]
        stats["film_s"] += float(s.get("dur") or 0)
        for b in boxes:
            stats["secrets"].add(f"{b['kind']}:{b.get('text', '')[:24]}")
        img = None
        for b in boxes:
            kind = b["kind"]
            if seen.get(kind, 0) >= per_kind:
                continue
            if img is None:
                img = cv2.imread(os.path.join(reps, f"rep_{n:05d}.png"),
                                 cv2.IMREAD_COLOR)
                if img is None:
                    break
                H, W = img.shape[:2]
                mask = film_mask(boxes, (W, H))
                after = composite(img, mask, cfg)
                area = sum((bb["rect"][2] * bb["rect"][3]) for bb in boxes)
                stats["coverage"].append((area, max(1, s["i1"] - s["i0"] + 1)))
            seen[kind] = seen.get(kind, 0) + 1
            x, y, w, h = b["rect"]
            box = (int(x * W), int(y * H), int((x + w) * W), int((y + h) * H))
            tiles.append((f"{kind} ({b.get('via', '?')})", f"state {n}",
                          float(s.get("t") or 0),
                          crop_around(img, box), crop_around(after, box)))
        if img is None and boxes:
            # the rep is gone but the state still carries boxes: count its
            # coverage anyway, so the numbers on the sheet stay honest
            area = sum((bb["rect"][2] * bb["rect"][3]) for bb in boxes)
            stats["coverage"].append((area, max(1, s["i1"] - s["i0"] + 1)))
    ht = hand_tiles(states, reps, cfg, hand, float(doc.get("fps") or 30.0))
    stats["hand"] = len(ht)
    return tiles + ht, stats


def fingerprint_states(pdir, man):
    """What is being approved: the detections, and the hand rects beside them.
    Adding a `film_blur` rect changes the look, so it must un-approve it."""
    dj = os.path.join(pdir, "temp", "film", "detect.json")
    h = hashlib.sha1()
    with open(dj, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    h.update(json.dumps(man.get("film_blur") or [], sort_keys=True,
                        ensure_ascii=False).encode("utf-8"))
    return "film-" + h.hexdigest()[:11]


def render_sheet(tiles, stats, cfg, out):
    cols = 2                              # two secrets per row, each before|after
    cell_w = TILE_W * 2 + PAD * 3
    cell_h = TILE_H + 44
    rows = (len(tiles) + cols - 1) // cols
    head = 96
    W = cols * cell_w + PAD
    H = head + rows * cell_h + PAD
    canvas = np.full((H, W, 3), 24, np.uint8)
    cov = stats["coverage"]
    cov_mean = (sum(a * n for a, n in cov) / max(1, sum(n for _, n in cov))) * 100
    cov_max = max((a for a, _ in cov), default=0.0) * 100
    label(canvas, "REDACTION REVIEW -- nothing renders until this is approved",
          PAD, 30, (120, 200, 255), 0.7)
    label(canvas, f"{len(stats['secrets'])} secret(s), {stats['templates']} template(s), "
                  f"{stats['hand']} hand rect(s)   mode: {cfg.get('blur_mode', 'blur')}   "
                  f"blur covers {cov_mean:.1f}% of the frame on average, {cov_max:.1f}% at most",
          PAD, 58, (200, 200, 200), 0.5)
    label(canvas, "left: as recorded   right: as it will render   "
                  "approve with:  redaction-review.py --manifest <screen.json> --approve",
          PAD, 82, (160, 160, 160), 0.45)
    for i, (title, base, t, before, after) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = PAD + c * cell_w
        y = head + r * cell_h
        canvas[y + 30:y + 30 + TILE_H, x:x + TILE_W] = before
        canvas[y + 30:y + 30 + TILE_H, x + TILE_W + PAD:x + TILE_W * 2 + PAD] = after
        label(canvas, f"{title}   {base}  @ {int(t) // 60}:{t % 60:04.1f}", x, y + 20)
    cv2.imwrite(out, canvas, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return cov_mean, cov_max


def group_for_page(tiles):
    """As few images as possible: one representative per KIND of secret,
    plus one per hand rect. The question is the same for all of them --
    "is the right side how it should look?" -- and a person answers it once
    per kind, not thirty-four times per appearance."""
    groups = {}
    for title, base, t, before, after in tiles:
        kind = title.split(" ", 1)[0].rstrip(":")
        key = title if kind == "hand" else kind
        g = groups.setdefault(key, {"kind": kind, "label": title, "examples": []})
        g["examples"].append((base, t, before, after))
    return list(groups.values())


def write_html(groups, stats, cfg, out, fp):
    """A self-contained local page: one image at a time, yes/no, remembered.

    Local on purpose: the tiles carry the real phone numbers and the card,
    so this must never become a hosted page. Images are embedded as data
    URIs so the file opens from anywhere; answers persist in localStorage
    under the look's fingerprint, and come back as JSON -- copied, or
    downloaded as decisions.json.
    """
    import base64
    cards = []
    for g in groups:
        base, t, before, after = g["examples"][0]
        def b64(img):
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
        cards.append({"id": g["label"], "kind": g["kind"], "n": len(g["examples"]),
                      "where": f"{base} @ {int(t) // 60}:{t % 60:04.1f}",
                      "before": b64(before), "after": b64(after)})
    payload = json.dumps(cards, ensure_ascii=False)
    html = """<!doctype html><html><head><meta charset="utf-8">
<title>Redaction review</title>
<style>
 body{margin:0;background:#141416;color:#eee;font:15px/1.4 system-ui,sans-serif}
 .wrap{max-width:960px;margin:0 auto;padding:24px}
 h1{font-size:18px;margin:0 0 4px;color:#9cf}
 .sub{color:#aaa;margin-bottom:18px}
 .card{background:#1e1e22;border-radius:10px;padding:18px}
 .q{font-size:20px;margin:0 0 12px}
 .imgs{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .imgs figure{margin:0}.imgs img{width:100%;border-radius:6px;display:block}
 figcaption{color:#aaa;font-size:13px;margin-top:6px}
 .where{color:#888;font-size:13px;margin:10px 0}
 .btns{display:flex;gap:10px;margin-top:16px;flex-wrap:wrap}
 button{font:inherit;padding:12px 22px;border:0;border-radius:8px;cursor:pointer}
 .yes{background:#2e7d32;color:#fff}.no{background:#c62828;color:#fff}
 .nav{background:#333;color:#ddd}
 textarea{width:100%;box-sizing:border-box;margin-top:10px;background:#111;color:#eee;border:1px solid #444;border-radius:6px;padding:8px;font:inherit}
 .prog{color:#aaa;font-size:13px;margin-bottom:8px}
 .done pre{background:#111;padding:12px;border-radius:6px;white-space:pre-wrap;word-break:break-all}
 .kbd{color:#888;font-size:12px;margin-top:10px}
</style></head><body><div class="wrap">
<h1>Redaction review</h1>
<div class="sub">One question per kind of secret. Left: as recorded. Right: as it will render. Answers are kept in this browser and never leave this machine.</div>
<div id="app"></div></div>
<script>
const FP=__FP__, CARDS=__CARDS__;
const KEY="redaction-review:"+FP;
let st={}; try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){st={}}
let i=0; while(i<CARDS.length && st[CARDS[i].id]) i++;
function save(){try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
function render(){
 const app=document.getElementById("app");
 if(i>=CARDS.length){
  const out=JSON.stringify({fingerprint:FP,decisions:st},null,1);
  app.innerHTML=`<div class="card done"><p class="q">Done — ${Object.keys(st).length} answer(s).</p>
   <pre id="out">${out.replace(/</g,"&lt;")}</pre>
   <div class="btns"><button class="yes" onclick="navigator.clipboard.writeText(document.getElementById('out').textContent).then(()=>alert('copied'))">Copy JSON</button>
   <button class="nav" onclick="dl()">Download decisions.json</button>
   <button class="nav" onclick="i=0;render()">Review again</button>
   <button class="nav" onclick="st={};save();i=0;render()">Clear answers</button></div>
   <div class="kbd">Paste the JSON back, or save decisions.json into the project's temp/review folder.</div></div>`;
  return;
 }
 const c=CARDS[i];
 app.innerHTML=`<div class="card"><div class="prog">${i+1} of ${CARDS.length} · ${c.kind} · ${c.n} appearance(s) in the film</div>
  <p class="q">Is the right side blurred the way you want it?</p>
  <div class="imgs"><figure><img src="${c.before}"><figcaption>as recorded</figcaption></figure>
  <figure><img src="${c.after}"><figcaption>as it will render</figcaption></figure></div>
  <div class="where">${c.where}</div>
  <div class="btns"><button class="yes" onclick="ans(true)">Yes (Y)</button><button class="no" onclick="ans(false)">No (N)</button>
  <button class="nav" onclick="i=Math.max(0,i-1);render()">← Back</button></div>
  <textarea id="note" rows="2" placeholder="If no: what should change? (optional)"></textarea>
  <div class="kbd">Keys: Y = yes, N = no, ← = back</div></div>`;
}
function ans(ok){const c=CARDS[i];st[c.id]={ok:ok,note:document.getElementById("note").value||"",kind:c.kind,where:c.where};save();i++;render()}
function dl(){const b=new Blob([JSON.stringify({fingerprint:FP,decisions:st},null,1)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="decisions.json";a.click()}
document.addEventListener("keydown",e=>{if(i>=CARDS.length)return;if(e.key==="y"||e.key==="Y")ans(true);else if(e.key==="n"||e.key==="N")ans(false);else if(e.key==="ArrowLeft"){i=Math.max(0,i-1);render()}});
render();
</script></body></html>"""
    # str.replace, never %-formatting or .format(): the template is full of
    # CSS percentages and JS braces, and both formatters choke on them
    html = html.replace("__FP__", json.dumps(fp)).replace("__CARDS__", payload)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return len(cards)


def fingerprint(man, mpath):
    """What exactly is being approved: the manifest's redaction, and the
    track files' identities."""
    h = hashlib.sha1()
    keep = {"cut": man.get("cut"), "sources": [
        {"path": s["path"], "blur": s.get("blur"), "track": s.get("track"),
         "skip": s.get("skip")} for s in man.get("sources", [])]}
    h.update(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for s in man.get("sources", []):
        if s.get("track"):
            tj = os.path.join(_env.resolve(s["track"]), "track.json")
            try:
                st = os.stat(tj)
                h.update(f"{tj}:{st.st_size}:{int(st.st_mtime)}".encode())
            except OSError:
                h.update(f"{tj}:missing".encode())
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", help="default: <project>/temp/review/redaction-sheet.jpg")
    ap.add_argument("--approve", action="store_true",
                    help="record approval of the CURRENT look in project.json")
    ap.add_argument("--check", action="store_true",
                    help="exit 0 if the current look is already approved, else 3")
    ap.add_argument("--states", action="store_true",
                    help="review the FILM-time redaction (temp/film/detect.json) "
                         "instead of the source-time tracker; this is the "
                         "acceptance test between film-redact --detect and --blur")
    ap.add_argument("--html", action="store_true",
                    help="also write temp/review/review.html: one image at a time, "
                         "yes/no, as few images as possible, answers remembered "
                         "locally and handed back as JSON")
    args = ap.parse_args()

    mpath = _env.resolve(args.manifest)
    man = json.load(open(mpath, encoding="utf-8"))
    cfg = man.get("cut") or {}
    pdir = _project.find_project_dir(mpath) or os.path.dirname(mpath)
    pid = os.path.basename(pdir)
    fp = fingerprint_states(pdir, man) if args.states else fingerprint(man, mpath)
    doc = _project.load(pid) or {}
    approved = (doc.get("review") or {}).get("fingerprint")

    if args.check:
        ok = approved == fp
        print(f"review: {'approved' if ok else 'NOT approved'} for the current look ({fp})")
        raise SystemExit(0 if ok else 3)

    sheet_name = "film-redaction-sheet.jpg" if args.states else "redaction-sheet.jpg"

    if args.approve:
        doc.setdefault("review", {})
        doc["review"] = {"fingerprint": fp,
                         "approved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "sheet": _project.norm(args.out or os.path.join(
                             pdir, "temp", "review", sheet_name))}
        with open(_project.path_for(pid), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        _project.record(pid, "redaction-review", note=f"redaction look approved ({fp})")
        print(f"approved the current redaction look ({fp}); recorded in project.json")
        return

    out = _env.resolve(args.out) if args.out else os.path.join(pdir, "temp", "review",
                                                               sheet_name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if args.states:
        tiles, stats = collect_states(pdir, cfg, hand=man.get("film_blur"))
        if not tiles:
            raise SystemExit("nothing to review: detect.json found no secret on "
                             "any state -- that is a result to check, not to approve")
    else:
        tiles, stats = collect(man, mpath, cfg)
        if not tiles:
            raise SystemExit("nothing to review: no track dirs with track.json and no hand rects")
    cov_mean, cov_max = render_sheet(tiles, stats, cfg, out)
    if args.html:
        page = os.path.join(os.path.dirname(out),
                            "film-review.html" if args.states else "review.html")
        n = write_html(group_for_page(tiles), stats, cfg, page, fp)
        print(f"page  -> {page}   ({n} question(s), one image each)")
    if args.states:
        print(f"{len(stats['secrets'])} distinct secret(s) on "
              f"{stats['states_hit']} of {stats['states']} state(s) "
              f"({stats['film_s']:.0f}s of film), {stats['hand']} hand rect(s); "
              f"blur covers {cov_mean:.1f}% of the frame on average, "
              f"{cov_max:.1f}% at most")
    else:
        print(f"{len(stats['secrets'])} secret(s), {stats['templates']} template(s), "
              f"{stats['hand']} hand rect(s); blur covers {cov_mean:.1f}% of the frame "
              f"on average, {cov_max:.1f}% at most")
    print(f"sheet -> {out}")
    if approved == fp:
        print(f"this exact look is already approved ({fp})")
        return
    print(f"\nSTOP: review the sheet, then approve with\n"
          f"  python scripts/redaction-review.py --manifest {args.manifest}"
          + (" --states" if args.states else "") + " --approve")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
