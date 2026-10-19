#!/usr/bin/env python
"""Draw a character with an image model and cut it into a pack a sketch film animates (an actor).

An actor is one character, every way a film needs to see it: the figure (front, full length), the
faces it pulls, the mouth shapes on the faces that talk, a blink, and whole-figure poses. The model
draws the figure once, then redraws that picture with one change at a time. Every redraw is laid
back on the picture it came from (a shift, or an affine fit on the body: some models hand back a
redraw a little larger or moved), measured, and cut down to what changed, so the film can swap a
mouth or a face without the hat, the paddle or the outline jumping. A redraw that changed more
than its head (config/actors/defaults.json "gate") is drawn again, up to `retakes` times, and the
steadiest kept. In each pose the base's head is looked for: where it is found looking out of the
picture, the front faces and mouths are laid on it; where the head has turned, the pose gets
mouths of its own. Everything ends in one atlas and pack.json, which sketch/actors.js draws:
SK.actor('enrique', x, y, h, {face, pose, ...}), the mouth moved by the voice.

A spec names the character and overrides any default (config/actors/defaults.json):

    {"name": "enrique", "project": "padel-history", "look": "explainer",
     "describe": "Enrique, a cheerful gentleman from Acapulco in 1969: ...",
     "faces": ["happy", "laugh", "angry", "shocked"], "talk": ["neutral", "happy"],
     "poses": ["wave", "point", "turn_right"], "pick": 2}

`faces`, `talk` and `poses` are lists of default names, or {name: "the change"} for new ones.
`style` replaces the look's words; `design` starts from a picture already made instead of drawing
candidates. The first run draws `candidates` figures (design/sheet.jpg) and stops: set `pick` to
the one to keep, and run again.

Writes beside the spec, in <name>/: design/, raw/ (every picture as drawn, every retake),
aligned/ (each redraw laid on the base), pack.json + atlas-<n>.webp (what a film loads),
check.jpg (every face, mouth, blink and pose, put together and labelled with its drift),
state.json (what each picture was drawn from, so a rerun draws only what changed) and
spend.jsonl. The OpenRouter key is OPENROUTER_API_KEY (.env).

Invoke as:
    python scripts/actor-pack.py --spec projects/<id>/actors/enrique.json --plan
    python scripts/actor-pack.py --spec projects/<id>/actors/enrique.json
    python scripts/actor-pack.py --spec projects/<id>/actors/enrique.json --cap 3 --jobs 6
    python scripts/actor-pack.py --spec projects/<id>/actors/enrique.json --retake face:angry
    python scripts/actor-pack.py --spec projects/<id>/actors/enrique.json --pack-only
"""

import sys
import os
import json
import time
import shutil
import hashlib
import argparse
import threading
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402
import cv2  # noqa: E402

import _actor  # noqa: E402
import _project  # noqa: E402

SP = import_module("sketch-paint")
PC = import_module("paint-compare")
DEFAULTS = "config/actors/defaults.json"
PACK_VERSION = 1  # bump when pack.json changes shape: sketch/actors.js reads it


# ---------------------------------------------------------------------------- the spec
def pick(names, table, what):
    """A spec's list of default names, or {name: change}, as {name: change}."""
    out = {}
    if isinstance(names, dict):
        for n, v in names.items():
            if isinstance(v, str):
                out[n] = v
            elif v is True and n in table:
                out[n] = table[n]
            elif v is True:
                sys.exit(
                    "%s %r is not one of: %s (give it a change instead of true)"
                    % (what, n, ", ".join(table))
                )
        return out
    for n in names:
        if n not in table:
            sys.exit("%s %r is not one of: %s" % (what, n, ", ".join(table)))
        out[n] = table[n]
    return out


def load_spec(path):
    with open(_env.resolve(DEFAULTS), encoding="utf-8") as f:
        d = json.load(f)
    path = _env.resolve(path)
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    for k in ("name", "describe"):
        if not s.get(k):
            sys.exit("%s: the spec needs %r" % (path, k))
    if not s["name"].replace("_", "").replace("-", "").isalnum() or not s["name"][0].isalpha():
        sys.exit("%s: name %r: letters, digits, - and _ only" % (path, s["name"]))
    a = {k: s.get(k, d[k]) for k in ("model", "quality", "aspect", "candidates", "jobs", "head")}
    a.update(name=s["name"], describe=s["describe"].strip(), path=path)
    a["style"] = s.get("style") or d["looks"][s.get("look", "explainer")]
    a["faces"] = pick(s.get("faces", list(d["faces"])), d["faces"], "face")
    a["talk"] = [f for f in s.get("talk", d["talk"]) if f == "neutral" or f in a["faces"]]
    a["mouths"] = pick(s.get("mouths", list(d["mouths"])), d["mouths"], "mouth")
    a["rig"] = s.get("rig") or False  # true, or {RIG overrides}: a puppet (scripts/_puppet.py)
    a["poses"] = pick(s.get("poses", [] if a["rig"] else list(d["poses"])), d["poses"], "pose")
    a["props"] = s.get("props") or {}
    shapes = [k for k in d["hands"] if not k.startswith("_")]
    a["hands"] = (s.get("hands") or {"r": shapes, "l": shapes}) if a["rig"] else {}
    a["hand_shapes"] = {k: v for k, v in d["hands"].items() if not k.startswith("_")}
    a["pose_mouths"] = [m for m in s.get("pose_mouths", d["pose_mouths"]) if m in a["mouths"]]
    a["blink"] = s.get("blink", d["blink"])
    a["gate"] = {**d["gate"], **(s.get("gate") or {})}
    a["pack"] = {**d["pack"], **(s.get("pack") or {})}
    a["prompts"] = {k: d[k] for k in ("base", "rig_base", "edit", "pose", "prop", "hand", "view")}
    a["pick"], a["design"] = s.get("pick"), s.get("design")
    a["out"] = _env.resolve(s.get("out") or os.path.join(os.path.dirname(path), s["name"]))
    a["project"] = _project.project_id(s, path)
    a["views"] = {}
    for vn, v in (s.get("views") or {}).items() if a["rig"] else {}.items():
        vs = v if isinstance(v, dict) else {}
        if not vs.get("turn") and vn not in d["views"]:
            sys.exit(
                '%s: view %r needs its "turn" (the defaults have %s)'
                % (path, vn, ", ".join(d["views"]))
            )
        a["views"][vn] = view_spec(a, vn, {**vs, "turn": vs.get("turn") or d["views"][vn]}, d)
    return a


def view_spec(a, name, v, d):
    """A rig actor's view: the same actor drawn turned, its own puppet in <out>/views/<name>/. It is
    drawn from the base on white (`view`), then given its own faces, mouths, blink and hands, as the
    front one is: a turned face cannot borrow the front's patches."""
    av = dict(a, views={}, poses={}, view=name, turn=v["turn"], pick=v.get("pick"))
    av["design"] = v.get("design")
    want = v.get("faces") or [f for f in a["talk"] if f != "neutral"] + (
        ["laugh"] if "laugh" in d["faces"] else []
    )
    av["faces"] = pick(want, {**d["faces"], **a["faces"]}, "face")
    av["talk"] = [f for f in v.get("talk", a["talk"]) if f == "neutral" or f in av["faces"]]
    av["hands"] = v.get("hands") or a["hands"]
    av["out"] = os.path.join(a["out"], "views", name)
    return av


# ---------------------------------------------------------------------------- what to draw
def jobs(a, front=None):
    """Every picture the pack needs: [(id, ref id or None, prompt, gate)], in the order they can be
    drawn (a ref is drawn before what is redrawn from it). `front` is {pose: bool} once the poses
    are drawn: a pose whose head has turned gets mouths of its own."""
    P = a["prompts"]
    edit = lambda change: P["edit"].format(change=change)  # noqa: E731
    out = [("base", None, None, None)]
    for f, ch in a["faces"].items():
        out.append(("face:" + f, "base", edit(ch), "face"))
    for f in a["talk"]:
        ref = "base" if f == "neutral" else "face:" + f
        for m, ch in a["mouths"].items():
            out.append(("mouth:%s:%s" % (f, m), ref, edit(ch), "mouth"))
        if a["blink"]:
            out.append(("blink:" + f, ref, edit(a["blink"]), "blink"))
    for side, shapes in a["hands"].items():  # a rig's hands: each shape drawn on its own hand
        for sh in shapes:
            prompt = P["hand"].format(
                side="right" if side == "r" else "left",
                where="left" if side == "r" else "right",
                shape=a["hand_shapes"][sh],
            )
            out.append(("hand:%s:%s" % (side, sh), "base", prompt, "hand"))
    for p, ch in a["poses"].items():
        out.append(("pose:" + p, "base", a["style"] + " " + P["pose"].format(change=ch), None))
    for p in a["poses"]:
        if front is not None and front.get(p) is False:
            for m in a["pose_mouths"]:
                out.append(("pmouth:%s:%s" % (p, m), "pose:" + p, edit(a["mouths"][m]), "mouth"))
            if a["blink"]:
                out.append(("pblink:" + p, "pose:" + p, edit(a["blink"]), "blink"))
    return out


def base_prompt(a):
    key = "rig_base" if a["rig"] else "base"  # a puppet is drawn in an A-pose, to be cut up
    return a["style"] + " " + a["prompts"][key].format(describe=a["describe"])


def fname(i):
    return i.replace(":", "__")


# ---------------------------------------------------------------------------- drawing
class Book:
    """state.json (what every picture was drawn from, its tries and their drift) and the spend."""

    def __init__(self, a, cap):
        self.a, self.cap, self.lock = a, cap, threading.Lock()
        self.path = os.path.join(a["out"], "state.json")
        self.s = json.load(open(self.path, encoding="utf-8")) if os.path.exists(self.path) else {}
        self.spent = 0.0

    def save(self):
        with self.lock, open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.s, f, indent=1)

    def charge(self, cost, what):
        with self.lock:
            self.spent += cost or 0.0
            with open(os.path.join(self.a["out"], "spend.jsonl"), "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "what": what,
                            "model": self.a["model"],
                            "usd": cost,
                        }
                    )
                    + "\n"
                )

    def over(self, est):
        with self.lock:
            return self.cap is not None and self.spent + est > self.cap


def fingerprint(a, prompt, ref_fp):
    h = hashlib.sha1(usedforsecurity=False)
    h.update(json.dumps([a["model"], a["quality"], a["aspect"], prompt, ref_fp]).encode())
    return h.hexdigest()[:12]


def draw_one(a, book, prompt, ref_path, out_path, what, transparent=False):
    """One picture from the model, saved as PNG. Only the base is asked for on a transparent
    background (where the model has one): measured 2026-10-17, gpt-image-2.5-sunburst's
    transparent redraws came back with a cloudy half-transparent halo round the figure in half of
    them (drift 40-160 %), while the same redraws on white keyed cleanly (drift ~1 %)."""
    caps = SP.model_caps(a["model"])
    alpha = transparent and SP.gives_alpha(caps)
    data, meta = SP.paint_openrouter(
        prompt, a["model"], ref_path, a["quality"], a["aspect"], transparent=alpha
    )
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise RuntimeError("the model sent something that is not a picture")
    cv2.imwrite(out_path, arr)
    book.charge(meta.get("cost_usd"), what)
    return meta.get("cost_usd")


def measure(ref_aligned, pic_path, fig):
    var = _actor.load_rgba(pic_path)
    im, mask, info = _actor.register(ref_aligned, var, fig["head"], fig["area"])
    return im, mask, info


def run_job(a, book, est, job, fig, aligned, retake):
    """Draw one redraw (and its retakes) unless state.json says it is drawn from the same prompt
    and reference already. Returns its state entry."""
    i, ref, prompt, gate = job
    ref_e = book.s.get(ref) or {}
    fp = fingerprint(a, prompt, ref_e.get("fp"))
    e = book.s.get(i)
    if (
        e
        and e.get("fp") == fp
        and i not in retake
        and os.path.exists(os.path.join(a["out"], e["file"]))
    ):
        return e
    tries = list(e.get("tries", [])) if e and e.get("fp") == fp else []
    limit = 1 + (a["gate"]["retakes"] if gate else 0)
    ref_path = os.path.join(a["out"], ref_e.get("white") or ref_e["file"])
    while len(tries) < limit + (1 if i in retake else 0):
        if book.over(est):
            print("  %-26s skipped: the $%.2f cap" % (i, book.cap))
            break
        rel = "raw/%s%s.png" % (fname(i), "" if not tries else ".r%d" % len(tries))
        t0 = time.time()
        try:
            cost = draw_one(a, book, prompt, ref_path, os.path.join(a["out"], rel), i)
        except Exception as ex:  # noqa: BLE001 -- one refused picture must not stop the pack
            print("  %-26s FAILED: %s" % (i, str(ex)[:160]))
            break
        row = {"file": rel, "usd": cost, "s": round(time.time() - t0, 1)}
        if gate:
            _, _, info = measure(aligned[ref], os.path.join(a["out"], rel), fig)
            row.update(drift=info["drift"], fit=info["fit"], scale=info["scale"])
        tries.append(row)
        note = (
            ""
            if not gate
            else "drift %.1f%%%s"
            % (
                100 * row["drift"],
                ""
                if row["drift"] <= a["gate"][gate]
                else "  over %.1f%%" % (100 * a["gate"][gate]),
            )
        )
        print("  %-26s %5.1fs  $%.3f  %s" % (i, row["s"], cost or 0, note))
        if not gate or row["drift"] <= a["gate"][gate]:
            break
    if not tries:
        return e
    best = min(tries, key=lambda r: r.get("drift", 0)) if gate else tries[-1]
    e = {"fp": fp, "file": best["file"], "tries": tries, "ref": ref}
    if gate:
        e["drift"] = best["drift"]
    with book.lock:
        book.s[i] = e
    book.save()
    return e


def design(a, book, est):
    """The base: a picture the spec names, or `candidates` drawn and one picked."""
    os.makedirs(os.path.join(a["out"], "design"), exist_ok=True)
    if a["design"]:
        src = _env.resolve(a["design"])
        h = hashlib.sha1(open(src, "rb").read(), usedforsecurity=False).hexdigest()[:12]
        rgba = _actor.load_rgba(src)
        cv2.imwrite(os.path.join(a["out"], "raw/base.png"), rgba)
        book.s["base"] = {
            "fp": "design-" + h,
            "file": "raw/base.png",
            "white": white(a, "raw/base.png"),
        }
        book.save()
        return True
    if a.get("view"):  # a view: the actor's own base, redrawn turned
        prompt = a["prompts"]["view"].format(turn=a["turn"])
        ref = os.path.join(os.path.dirname(os.path.dirname(a["out"])), "raw", "base.white.png")
        if not os.path.exists(ref):
            sys.exit("view %s: the actor's base is not drawn yet (%s)" % (a["view"], ref))
        ref_fp = hashlib.sha1(open(ref, "rb").read(), usedforsecurity=False).hexdigest()[:12]
    else:
        prompt, ref, ref_fp = base_prompt(a), None, None
    fp = fingerprint(a, prompt, ref_fp)
    have = book.s.get("design") or {}
    files = list(have.get("files", [])) if have.get("fp") == fp else []
    need = a["candidates"] - len(files)

    def one(n):
        rel = "design/c%d.png" % n
        if book.over(est):
            return None
        try:
            draw_one(
                a,
                book,
                prompt,
                ref,
                os.path.join(a["out"], rel),
                "design %d" % n,
                transparent=ref is None,
            )
        except Exception as ex:  # noqa: BLE001
            print("  design %d FAILED: %s" % (n, str(ex)[:160]))
            return None
        return rel

    if need > 0:
        with ThreadPoolExecutor(max_workers=a["jobs"]) as ex:
            files += [r for r in ex.map(one, range(len(files) + 1, a["candidates"] + 1)) if r]
        book.s["design"] = {"fp": fp, "files": files}
        book.save()
        sheet(
            [(os.path.join(a["out"], f), "c%d" % (k + 1)) for k, f in enumerate(files)],
            os.path.join(a["out"], "design/sheet.jpg"),
        )
    if not a["pick"]:
        print(
            '  %d candidates: design/sheet.jpg. Set "pick" in the spec to the one to keep, and run again.'
            % len(files)
        )
        return False
    if not 1 <= a["pick"] <= len(files):
        sys.exit("pick %r: there are %d candidates" % (a["pick"], len(files)))
    src = os.path.join(a["out"], files[a["pick"] - 1])
    shutil.copyfile(src, os.path.join(a["out"], "raw/base.png"))
    book.s["base"] = {
        "fp": "%s-c%d" % (fp, a["pick"]),
        "file": "raw/base.png",
        "white": white(a, "raw/base.png"),
    }
    book.save()
    return True


def white(a, rel):
    """The picture on white, beside it: what a redraw is drawn from (a redraw is asked for on
    white, so its reference is on white too)."""
    out = rel.replace(".png", ".white.png")
    rgba = _actor.load_rgba(os.path.join(a["out"], rel))
    cv2.imwrite(os.path.join(a["out"], out), _actor.on_white(rgba))
    return out


def sheet(items, out, h=520, cols=6):
    """A contact sheet of (picture path or BGRA, label) on light grey."""
    tiles = []
    for p, label in items:
        im = _actor.load_rgba(p) if isinstance(p, str) else p
        if im is None:
            continue
        f = _actor.figure(im[..., 3]) or {"box": [0, 0, im.shape[1], im.shape[0]]}
        b = f["box"]
        im = im[b[1] : b[3], b[0] : b[2]]
        k = (h - 40) / im.shape[0]
        im = cv2.resize(im, (max(1, int(im.shape[1] * k)), h - 40), interpolation=cv2.INTER_AREA)
        tile = np.full((h, max(im.shape[1], 260), 3), 238, np.uint8)
        a_ = im[..., 3:4].astype(np.float32) / 255
        x = (tile.shape[1] - im.shape[1]) // 2
        tile[:-40, x : x + im.shape[1]] = (
            im[..., :3] * a_ + tile[:-40, x : x + im.shape[1]] * (1 - a_)
        ).astype(np.uint8)
        cv2.putText(
            tile, label, (8, h - 13), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (40, 30, 30), 1, cv2.LINE_AA
        )
        tiles.append(tile)
    if not tiles:
        return
    W = max(sum(t.shape[1] for t in tiles[r : r + cols]) for r in range(0, len(tiles), cols))
    rows = []
    for r in range(0, len(tiles), cols):
        row = np.hstack(tiles[r : r + cols])
        rows.append(np.pad(row, ((0, 0), (0, W - row.shape[1]), (0, 0)), constant_values=255))
    cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])


# ---------------------------------------------------------------------------- cutting and packing
def pack(a, book):
    """Cut every drawn picture into pieces and pack them: pack.json, atlas pages, check.jpg."""
    out = a["out"]
    base = _actor.load_rgba(os.path.join(out, book.s["base"]["file"]))
    fig = _actor.figure(base[..., 3], a["head"])
    bx0, by0, bx1, by1 = fig["box"]
    k = min(1.0, a["pack"]["height"] / fig["height"])
    grow, feather = max(4, int(0.012 * fig["height"])), max(3, int(0.006 * fig["height"]))
    sc = lambda v: round(v * k)  # noqa: E731
    pieces, report = {}, {}

    def put(pid, im):
        pieces[pid] = (
            cv2.resize(
                im, (max(1, sc(im.shape[1])), max(1, sc(im.shape[0]))), interpolation=cv2.INTER_AREA
            )
            if k < 1
            else im
        )

    put("base", base[by0:by1, bx0:bx1])
    head = [
        sc(fig["head"][0] - bx0),
        sc(fig["head"][1] - by0),
        sc(fig["head"][2] - bx0),
        sc(fig["head"][3] - by0),
    ]
    P = {
        "v": PACK_VERSION,
        "name": a["name"],
        "model": a["model"],
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scale": round(k, 4),
        # who it is, for a film's writer (the studio tells an episode's Claude: library.note)
        "about": a.get("describe") or "",
    }
    P["figure"] = {
        "w": sc(bx1 - bx0),
        "h": sc(by1 - by0),
        "feet": [sc(fig["feet"][0] - bx0), sc(fig["feet"][1] - by0)],
        "height": sc(fig["height"]),
        "head": head,
    }
    faces, poses = {"neutral": {"mouths": {}}}, {}
    aligned = {"base": base}

    def cut(pid, ref, file, within, ox=bx0, oy=by0):
        """A patch: `file` laid on `ref` (both in the base's pixels), cut to what changed."""
        im, mask, info = _actor.register(
            ref, _actor.load_rgba(os.path.join(out, file)), fig["head"], fig["area"]
        )
        got = _actor.patch(im, mask, within, grow, feather)
        report[pid] = {k_: info[k_] for k_ in ("drift", "changed", "fit", "scale")}
        if got is None:
            return im, None
        x, y, p = got
        put(pid, p)
        return im, {"piece": pid, "x": sc(x - ox), "y": sc(y - oy)}

    for f in a["faces"]:
        e = book.s.get("face:" + f)
        if not e:
            continue
        im, pt = cut("face:" + f, base, e["file"], fig["head"])
        aligned["face:" + f] = im
        if pt:
            faces[f] = dict(pt, mouths={})
    for f in a["talk"]:
        ref = "base" if f == "neutral" else "face:" + f
        if ref not in aligned or f not in faces:
            continue
        for m in a["mouths"]:
            e = book.s.get("mouth:%s:%s" % (f, m))
            if e:
                _, pt = cut("mouth:%s:%s" % (f, m), aligned[ref], e["file"], fig["head"])
                if pt:
                    faces[f]["mouths"][m] = pt
        e = book.s.get("blink:" + f)
        if e:
            _, pt = cut("blink:" + f, aligned[ref], e["file"], fig["head"])
            if pt:
                faces[f]["blink"] = pt
    for p in a["poses"]:
        e = book.s.get("pose:" + p)
        if not e:
            continue
        pic = _actor.load_rgba(os.path.join(out, e["file"]))
        s, (hx, hy), score = _actor.find_head(base, fig["head"], pic)
        if score < 0.45 or not 0.6 < s < 1.6:  # no head found: keep the model's own scale
            s = 1.0
        pic = (
            cv2.resize(
                pic, (int(pic.shape[1] / s), int(pic.shape[0] / s)), interpolation=cv2.INTER_AREA
            )
            if abs(s - 1) > 0.01
            else pic
        )
        pf = _actor.figure(pic[..., 3], a["head"])
        if pf is None:
            continue
        px0, py0, px1, py1 = pf["box"]
        put("pose:" + p, pic[py0:py1, px0:px1])
        front = score >= a["gate"]["front"]
        same = _actor.same_character(base, pic)
        entry = {
            "piece": "pose:" + p,
            "w": sc(px1 - px0),
            "h": sc(py1 - py0),
            "feet": [sc(pf["feet"][0] - px0), sc(pf["feet"][1] - py0)],
            "mouths": {},
        }
        if front:  # the base's head, found looking out: the front faces and mouths go on it here
            entry["face_at"] = [
                sc(hx / s - px0) - sc(fig["head"][0] - bx0),
                sc(hy / s - py0) - sc(fig["head"][1] - by0),
            ]
        else:
            pshape = pic.shape
            phead = (
                [
                    int(hx / s),
                    int(hy / s),
                    int(hx / s + (fig["head"][2] - fig["head"][0])),
                    int(hy / s + (fig["head"][3] - fig["head"][1])),
                ]
                if score >= 0.45
                else pf["head"]
            )
            for m in a["pose_mouths"]:
                e2 = book.s.get("pmouth:%s:%s" % (p, m))
                if not e2:
                    continue
                var = _actor.load_rgba(os.path.join(out, e2["file"]))
                var = cv2.resize(var, (pshape[1], pshape[0]), interpolation=cv2.INTER_AREA)
                im, mask, info = _actor.register(pic, var, phead, pf["area"])
                got = _actor.patch(im, mask, phead, grow, feather)
                report["pmouth:%s:%s" % (p, m)] = {
                    k_: info[k_] for k_ in ("drift", "changed", "fit", "scale")
                }
                if got:
                    x, y, pp = got
                    put("pmouth:%s:%s" % (p, m), pp)
                    entry["mouths"][m] = {
                        "piece": "pmouth:%s:%s" % (p, m),
                        "x": sc(x - px0),
                        "y": sc(y - py0),
                    }
        report["pose:" + p] = {
            "head_score": round(score, 3),
            "scale": round(1 / s, 4),
            "front": front,
            "same": round(same, 3),
        }
        if same < a["gate"]["same"]:
            print(
                "  WARNING pose %s: colours unlike the base (%.2f): is it still the same character?"
                % (p, same)
            )
        if isinstance(a["poses"].get(p), str):  # what the pose is, in the spec's words
            entry["about"] = a["poses"][p]
        poses[p] = entry
    pages, where = _actor.pack_atlas(pieces, a["pack"]["page"])
    from PIL import Image  # noqa: PLC0415 -- pillow only for the WebP pages

    names = []
    for n, pg in enumerate(pages):
        name = "atlas-%d.%s" % (n, a["pack"]["format"])
        img = Image.fromarray(cv2.cvtColor(pg, cv2.COLOR_BGRA2RGBA))
        if a["pack"]["format"] == "webp":
            img.save(os.path.join(out, name), "WEBP", quality=a["pack"]["quality"], method=6)
        else:
            img.save(os.path.join(out, name), optimize=True)
        names.append(name)
    P.update(pages=names, pieces=where, faces=faces, poses=poses, report=report)
    with open(os.path.join(out, "pack.json"), "w", encoding="utf-8") as f:
        json.dump(P, f, indent=1)
    check_sheet(a, P, pieces)
    return P


def compose(P, pieces, face="neutral", mouth=None, blink=False, pose=None):
    """The actor as the player would draw it (BGRA, its own piece's pixels)."""
    if pose:
        po = P["poses"][pose]
        im = pieces[po["piece"]].copy()
        if mouth and mouth in po["mouths"]:
            pt = po["mouths"][mouth]
            _actor.over(im, pieces[pt["piece"]], pt["x"], pt["y"])
        elif po.get("face_at") and mouth:
            pt = P["faces"]["neutral"]["mouths"].get(mouth)
            if pt:
                _actor.over(
                    im, pieces[pt["piece"]], pt["x"] + po["face_at"][0], pt["y"] + po["face_at"][1]
                )
        return im
    im = pieces["base"].copy()
    F = P["faces"].get(face, {})
    if face != "neutral" and F.get("piece"):
        _actor.over(im, pieces[F["piece"]], F["x"], F["y"])
    if mouth and mouth in F.get("mouths", {}):
        pt = F["mouths"][mouth]
        _actor.over(im, pieces[pt["piece"]], pt["x"], pt["y"])
    if blink and F.get("blink"):
        pt = F["blink"]
        _actor.over(im, pieces[pt["piece"]], pt["x"], pt["y"])
    return im


def check_sheet(a, P, pieces):
    rep = P["report"]
    lab = lambda pid, t: "%s  %.1f%%" % (t, 100 * rep[pid]["drift"]) if pid in rep else t  # noqa: E731
    items = [(compose(P, pieces), "base")]
    items += [(compose(P, pieces, f), lab("face:" + f, f)) for f in P["faces"] if f != "neutral"]
    for f, F in P["faces"].items():
        items += [
            (compose(P, pieces, f, m), lab("mouth:%s:%s" % (f, m), "%s %s" % (f, m)))
            for m in F.get("mouths", {})
        ]
        if F.get("blink"):
            items.append((compose(P, pieces, f, blink=True), lab("blink:" + f, f + " blink")))
    for p, po in P["poses"].items():
        r = rep.get("pose:" + p, {})
        items.append(
            (compose(P, pieces, pose=p), "%s %s" % (p, "front" if r.get("front") else "turned"))
        )
        m = "open" if ("open" in po["mouths"] or po.get("face_at")) else None
        if m:
            items.append((compose(P, pieces, pose=p, mouth=m), "%s talking" % p))
    sheet(items, os.path.join(a["out"], "check.jpg"), h=420, cols=8)


# ---------------------------------------------------------------------------- the rig
def draw_props(a, book, est):
    """Each prop alone (the "prop" prompt), redrawn from the base so it is in the same hand: raw/
    prop__<name>.png. Drawn again only when its words or the base change."""
    ref = book.s["base"]
    for name, spec in a["props"].items():
        pid = "prop:" + name
        if spec.get("image"):  # a picture already made
            src = _env.resolve(spec["image"])
            book.s[pid] = {
                "fp": "image-" + fingerprint(a, src, None),
                "file": os.path.relpath(src, a["out"]),
            }
            continue
        prompt = a["prompts"]["prop"].format(prop=spec.get("describe") or name)
        fp = fingerprint(a, prompt, ref.get("fp"))
        e = book.s.get(pid) or {}
        if e.get("fp") == fp and os.path.exists(os.path.join(a["out"], e["file"])):
            continue
        if book.over(est):
            print("  %-26s skipped: the $%.2f cap" % (pid, book.cap))
            continue
        rel = "raw/%s.png" % fname(pid)
        draw_one(
            a,
            book,
            prompt,
            os.path.join(a["out"], ref.get("white") or ref["file"]),
            os.path.join(a["out"], rel),
            pid,
        )
        book.s[pid] = {"fp": fp, "file": rel}
        book.save()
        print("  %-26s drawn" % pid)


def base_joints(a, book):
    """MediaPipe's pose on the drawn base (raw/base.png), once per base: {name: [x, y, vis]}."""
    import _puppet  # noqa: PLC0415

    fp = book.s["base"]["fp"]
    have = book.s.get("pose_joints") or {}
    if have.get("fp") != fp or not _puppet.sane(have["J"]):
        base = _actor.load_rgba(os.path.join(a["out"], book.s["base"]["file"]))
        book.s["pose_joints"] = {"fp": fp, "J": _puppet.joints(base)}
        book.save()
    return book.s["pose_joints"]["J"]


def hand_box(J, side):
    """A box round a hand and its wrist, in the base's pixels: what a hand's redraw may change."""
    wr, el = np.array(J[side + "_wr"][:2]), np.array(J[side + "_el"][:2])
    c = wr + 0.35 * (wr - el)
    r = 0.62 * np.linalg.norm(wr - el)
    return [int(c[0] - r), int(c[1] - r), int(c[0] + r), int(c[1] + r)]


def rig(a, book, P):
    """The puppet: the pack's base cut into parts on a skeleton (scripts/_puppet.py), its faces,
    mouths and blinks laid on the head, its props in their hands. Writes puppet.json,
    puppet-<n>.webp and rig.jpg (the cuts and the joints, for a look). Free: nothing is drawn."""
    from PIL import Image  # noqa: PLC0415

    import _puppet  # noqa: PLC0415

    pages = [cv2.imread(os.path.join(a["out"], pg), cv2.IMREAD_UNCHANGED) for pg in P["pages"]]

    def piece(pid):
        pc = P["pieces"][pid]
        return pages[pc["p"]][pc["sy"] : pc["sy"] + pc["h"], pc["sx"] : pc["sx"] + pc["w"]].copy()

    base = piece("base")
    raw = _actor.load_rgba(os.path.join(a["out"], book.s["base"]["file"]))
    fig = _actor.figure(raw[..., 3], a["head"])
    bx0, by0, k = fig["box"][0], fig["box"][1], P["scale"]
    to_piece = lambda x, y: [(x - bx0) * k, (y - by0) * k]  # noqa: E731 -- the pack's own crop
    Jr = base_joints(a, book)
    J = {n: to_piece(v[0], v[1]) + [v[2]] for n, v in Jr.items()}
    hands = {}
    for side, shapes in a["hands"].items():  # each drawn hand, laid on the base as faces are
        for sh in shapes:
            e = book.s.get("hand:%s:%s" % (side, sh))
            if not e or not os.path.exists(os.path.join(a["out"], e["file"])):
                continue
            pic = _actor.load_rgba(os.path.join(a["out"], e["file"]))
            im, _, _ = _actor.register(raw, pic, hand_box(Jr, side), fig["area"])
            im = im[fig["box"][1] : fig["box"][3], fig["box"][0] : fig["box"][2]]
            if k < 1:
                im = cv2.resize(im, (base.shape[1], base.shape[0]), interpolation=cv2.INTER_AREA)
            hands.setdefault(side, {})[sh] = im
    patches = {k: piece(k) for k in P["pieces"] if k.startswith(("face:", "mouth:", "blink:"))}
    props = {}
    for name, spec in a["props"].items():
        e = book.s.get("prop:" + name) or {}
        f = (
            _env.resolve(spec["image"])
            if spec.get("image")
            else os.path.join(a["out"], e.get("file", "-"))
        )
        if os.path.exists(f):
            props[name] = (_actor.load_rgba(f), spec)
        else:
            print("  WARNING prop %s is not drawn yet: the puppet goes without it" % name)
    opt = a["rig"] if isinstance(a["rig"], dict) else {}
    puppet, pieces, over = _puppet.build(base, J, P["faces"], patches, props, opt, hands)
    atlas, where = _actor.pack_atlas(pieces, a["pack"]["page"], gap=8)
    names = []
    for n, pg in enumerate(atlas):
        name = "puppet-%d.webp" % n
        img = Image.fromarray(cv2.cvtColor(pg, cv2.COLOR_BGRA2RGBA))
        img.save(os.path.join(a["out"], name), "WEBP", quality=a["pack"]["quality"], method=6)
        names.append(name)
    out = _puppet.finish(puppet, where, [(pg.shape[1], pg.shape[0]) for pg in atlas])
    out.update(
        name=a["name"], about=a.get("describe") or "", model=a["model"], pages=names,
        built_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )  # fmt: skip
    with open(os.path.join(a["out"], "puppet.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    cv2.imwrite(os.path.join(a["out"], "rig.jpg"), over, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out


# ---------------------------------------------------------------------------- main
def price(a):
    est = PC.estimate(a["model"], True, a["quality"]) or 0.04
    first = PC.estimate(a["model"], False, a["quality"]) or est
    return first, est


def make(a, args, book, est, retake):
    """Draw what the pack (or one of its views) still needs, pack it, and rig it when it is a rig:
    pack.json's dict, or None when a design is waiting for its pick."""
    for d in ("raw", "design"):
        os.makedirs(os.path.join(a["out"], d), exist_ok=True)
    if not args.pack_only:
        if (book.s.get("base") is None or a["design"] or a["pick"]) and not design(a, book, est):
            return None
        base = _actor.load_rgba(os.path.join(a["out"], book.s["base"]["file"]))
        fig = _actor.figure(base[..., 3], a["head"])
        if fig is None:
            sys.exit("the base picture has no figure in it")
        aligned = {"base": base}
        draw_props(a, book, est)
        J0 = base_joints(a, book) if a["hands"] else None
        stages = [
            ("hands", lambda j: j[0].startswith("hand:")),
            ("faces", lambda j: j[0].startswith("face:")),
            ("mouths", lambda j: j[0].startswith(("mouth:", "blink:"))),
            ("poses", lambda j: j[0].startswith("pose:")),
        ]
        for stage, keep in stages:
            todo = [j for j in jobs(a) if keep(j)]
            print("[actor-pack] %s: %d pictures" % (stage, len(todo)))
            if (
                stage == "mouths"
            ):  # the talking faces, laid on the base: what their mouths are measured against
                for f in a["talk"]:
                    e = book.s.get("face:" + f)
                    if f != "neutral" and e:
                        aligned["face:" + f] = _actor.register(
                            base,
                            _actor.load_rgba(os.path.join(a["out"], e["file"])),
                            fig["head"],
                            fig["area"],
                        )[0]
            with ThreadPoolExecutor(max_workers=a["jobs"]) as ex:
                list(
                    ex.map(
                        lambda j: run_job(
                            a,
                            book,
                            est,
                            j,
                            dict(fig, head=hand_box(J0, j[0].split(":")[1]))
                            if j[0].startswith("hand:")
                            else fig,
                            aligned,
                            retake,
                        ),
                        [j for j in todo if j[1] in aligned or j[1] == "base"],
                    )
                )
        # the poses whose head has turned get mouths of their own
        front = {}
        for p in a["poses"]:
            e = book.s.get("pose:" + p)
            if e:
                front[p] = (
                    _actor.find_head(
                        base, fig["head"], _actor.load_rgba(os.path.join(a["out"], e["file"]))
                    )[2]
                    >= a["gate"]["front"]
                )
        extra = [j for j in jobs(a, front) if j[0].startswith(("pmouth:", "pblink:"))]
        if extra:
            print("[actor-pack] turned poses' mouths: %d pictures" % len(extra))
            for p in {j[1] for j in extra}:
                pic = _actor.load_rgba(os.path.join(a["out"], book.s[p]["file"]))
                pf = _actor.figure(pic[..., 3], a["head"])
                s, (hx, hy), score = _actor.find_head(base, fig["head"], pic)
                hb = (
                    [
                        hx,
                        hy,
                        hx + int((fig["head"][2] - fig["head"][0]) * s),
                        hy + int((fig["head"][3] - fig["head"][1]) * s),
                    ]
                    if score >= 0.45
                    else pf["head"]
                )
                aligned[p] = pic
                pfig = dict(pf, head=hb)
                with ThreadPoolExecutor(max_workers=a["jobs"]) as ex:
                    list(
                        ex.map(
                            lambda j, pfig=pfig: run_job(a, book, est, j, pfig, aligned, retake),
                            [j for j in extra if j[1] == p],
                        )
                    )
        print("  spent $%.3f this run" % book.spent)
    print("[actor-pack] pack ...")
    P = pack(a, book)
    worst = sorted(((v["drift"], k) for k, v in P["report"].items() if "drift" in v), reverse=True)[
        :3
    ]
    print(
        "  %d pieces on %d page(s); faces %s; poses %s"
        % (
            len(P["pieces"]),
            len(P["pages"]),
            ", ".join(P["faces"]),
            ", ".join(
                "%s%s" % (p, "" if P["report"]["pose:" + p]["front"] else " (turned)")
                for p in P["poses"]
            ),
        )
    )
    print("  most drift: %s" % ", ".join("%s %.1f%%" % (k, 100 * d) for d, k in worst))
    print("  %s" % os.path.relpath(os.path.join(a["out"], "check.jpg")))
    if a["rig"]:
        print("[actor-pack] rig ...")
        R = rig(a, book, P)
        print(
            "  puppet: %d parts, %d props; %s"
            % (len(R["parts"]), len(R["props"]), os.path.relpath(os.path.join(a["out"], "rig.jpg")))
        )
    return P


def link_views(a):
    """The front puppet.json names its views, so a film that loads the actor gets them all."""
    path = os.path.join(a["out"], "puppet.json")
    with open(path, encoding="utf-8") as f:
        P = json.load(f)
    P["views"] = {}
    for vn, av in a["views"].items():
        vp = os.path.join(av["out"], "puppet.json")
        if os.path.exists(vp):
            with open(vp, encoding="utf-8") as f:
                P["views"][vn] = {"dir": "views/" + vn, "facing": json.load(f).get("facing", 0)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(P, f, separators=(",", ":"))
    return P["views"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument(
        "--plan", action="store_true", help="what the pack needs and what it costs; draws nothing"
    )
    ap.add_argument(
        "--cap", type=float, default=None, help="stop starting pictures past this spend (USD)"
    )
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument(
        "--retake",
        default="",
        help="comma-separated ids to draw again (face:angry, pose:wave, ...)",
    )
    ap.add_argument(
        "--pack-only", action="store_true", help="re-cut and re-pack what is drawn: free"
    )
    ap.add_argument(
        "--rig-only", action="store_true", help='a "rig" actor: build the puppet again, free'
    )
    ap.add_argument(
        "--fetch-models", action="store_true", help="the pose model and MediaPipe, for a rig"
    )
    args = ap.parse_args()
    if args.fetch_models:
        import _puppet  # noqa: PLC0415

        import_module("head-rig").fetch_runtime()
        print("  %s" % os.path.relpath(_puppet.fetch_pose_model(), _env.ROOT))
        return
    a = load_spec(args.spec)
    if args.rig_only:
        if not a["rig"]:
            sys.exit('%s: not a rig ("rig": true in the spec)' % args.spec)
        for x in [a] + list(a["views"].values()):
            if not os.path.exists(os.path.join(x["out"], "pack.json")):
                print("  %s: not packed yet" % (x.get("view") or "front"))
                continue
            with open(os.path.join(x["out"], "pack.json"), encoding="utf-8") as f:
                R = rig(x, Book(x, None), json.load(f))
            print(
                "[actor-pack] %s puppet: %d parts, props %s, %s, facing %+d"
                % (
                    x.get("view") or "front",
                    len(R["parts"]),
                    list(R["props"]),
                    ", ".join(R["pages"]),
                    R["facing"],
                )
            )
        if a["views"]:
            link_views(a)
        return
    if args.jobs:
        a["jobs"] = args.jobs
    first, est = price(a)
    J = jobs(a, {p: False for p in a["poses"]})
    n_design = (0 if a["design"] else a["candidates"]) + sum(
        1 for p in a["props"].values() if not p.get("image")
    )
    n_main = (
        len(jobs(a))
        - 1
        + sum(
            (0 if av["design"] else av["candidates"]) + len(jobs(av)) - 1
            for av in a["views"].values()
        )
    )
    n_pose = len(J) - len(jobs(a))
    print("[actor-pack] %s  %s  look: %s" % (a["name"], a["model"], a["style"][:60] + "..."))
    for vn, av in a["views"].items():
        print(
            "  view %s: %d faces, %d talking, %d hands (in what follows)"
            % (vn, len(av["faces"]), len(av["talk"]), sum(len(v) for v in av["hands"].values()))
        )
    print(
        "  %d design candidates, %d faces, %d talking faces x %d mouths%s, %d poses (+ up to %d mouths for turned ones)"
        % (
            n_design,
            len(a["faces"]),
            len(a["talk"]),
            len(a["mouths"]),
            " + blink" if a["blink"] else "",
            len(a["poses"]),
            n_pose,
        )
    )
    lo = n_design * first + n_main * est
    print(
        "  about $%.2f (%d pictures), up to $%.2f with every turned pose and %d retakes on a quarter of the redraws"
        % (
            lo,
            n_design + n_main,
            lo + n_pose * est + 0.25 * n_main * a["gate"]["retakes"] * est,
            a["gate"]["retakes"],
        )
    )
    if args.plan:
        print("  --plan: nothing drawn")
        return
    book = Book(a, args.cap)
    retake = {x.strip() for x in args.retake.split(",") if x.strip()}
    t0 = time.time()
    P = make(a, args, book, est, retake)
    if P is None:
        return
    for vn, av in a["views"].items():
        print("[actor-pack] view %s ..." % vn)
        vb = Book(av, None if args.cap is None else max(0.0, args.cap - book.spent))
        done = make(av, args, vb, est, retake)
        book.spent += vb.spent
        if done is None:
            return
    if a["views"]:
        print(
            "  views: %s"
            % ", ".join("%s (facing %+d)" % (k, v["facing"]) for k, v in link_views(a).items())
        )
    print("[actor-pack] ran in %.0fs" % (time.time() - t0))
    _project.record(
        a["project"],
        "actor pack: %s (%d pieces, %s)" % (a["name"], len(P["pieces"]), a["model"]),
        out=os.path.join(a["out"], "pack.json"),
        script=__file__,
        argv=sys.argv[1:],
        kind="actor-pack",
        manifest=a["path"],
        sidecars={
            **{"atlas-%d" % n: os.path.join(a["out"], pg) for n, pg in enumerate(P["pages"])},
            "check": os.path.join(a["out"], "check.jpg"),
            **({"puppet": os.path.join(a["out"], "puppet.json")} if a["rig"] else {}),
            **{
                "view-" + vn: os.path.join(av["out"], "puppet.json")
                for vn, av in a["views"].items()
            },
        },
    )


if __name__ == "__main__":
    main()
