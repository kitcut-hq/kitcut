"""A film's cuts and its still stretches, from frames a few times a second: what a sheet of six
stills cannot show -- a scene that holds still for ten seconds, a cut that lands on an empty
stage. tools.motion() renders the frames; this reads them.

Measured on the films so far (2026-09-26): between frames a quarter of a second apart, a film in
motion changes 1-3% of its pixels (a small character moving is enough), a still one well under
1% (the crayon line's boil does not register at this size), and a cut or a crossfade changes
over 10% in a burst of a frame or two. A longer burst is a camera move, not a cut.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CHANGE = (
    12  # a pixel has changed when it moved by more than this (of 255), on a small blurred frame
)
STILL = 1.0  # % of pixels changing: less, and nothing on screen moves
CUT = 10.0  # % of pixels changing: more, in a short burst, and it is a cut or a transition
STILL_S = 4.0  # a still stretch this long is worth a word
CUT_MAX_S = 0.75  # a longer burst of change is a camera move
SHEET_CUTS, SHEET_STILLS = 6, 4  # how many of each the sheet shows (the text lists them all)
# The whole film at a frame a second (sheets()): what a glitch of half a second needs to be seen at
# all. Measured 2026-10-07 on three two-minute episodes that had shipped with 4-8 glitches each
# (a cat through a carrier's wall, a body flipped through a sliver, the same cat twice, an empty
# hand hanging ten seconds): the author had looked at 12 frames; laid out like this, six sheets,
# every one of them was plain.
SHEET_PER = 20  # frames to a sheet: 4 x 5 at 480 px for a 16:9 film reads; 157 px cells do not
SHEET_W = 1920
FONT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "fonts", "SofiaSansCondensed-VF.ttf"
)


def rate(length):
    """Frames a second to look at: every 0.25 s for a short film, fewer for a long one."""
    return 4 if length <= 45 else 3 if length <= 80 else 2


def times(length):
    fps = rate(length)
    return [round(i / fps, 3) for i in range(int(length * fps))]


def _frames(d):
    out = []
    for name in os.listdir(d):
        if name.endswith(".png"):
            try:
                out.append((float(name[:-4]), os.path.join(d, name)))
            except ValueError:
                continue
    return sorted(out)


def _font(size):
    """The repo's own caption font (arial.ttf is not on the VM, and the fallback bitmap font has no
    Cyrillic)."""
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def spoken(timeline_path):
    """[(start, end, word)] of the narration from audio/vo/timeline.json; [] when there is none."""
    import json  # noqa: PLC0415

    try:
        with open(timeline_path, encoding="utf-8") as f:
            lines = json.load(f).get("lines", [])
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for L in lines:
        ws = L.get("words") or []
        if not ws and L.get("text"):  # a line with no word times: all of it, over its span
            ws = [{"text": L["text"], "s": L.get("start", 0), "e": L.get("end", 0)}]
        out += [(float(w["s"]), float(w["e"]), str(w["text"])) for w in ws if "s" in w and "e" in w]
    return out


def _clock(t):
    return "%d:%02d" % (t // 60, t % 60) if t == int(t) else "%d:%05.2f" % (t // 60, t % 60)


def _fit(draw, text, font, width):
    """text cut to width with an ellipsis."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def tile(cells, path, cols=None, said=(), step=1.0, head=""):
    """One sheet of frames: cells is [(t, png path)], each drawn with its time and, under it, the
    words being said from t to t + step (said: spoken()'s list). The cell keeps the frame's own
    shape (a square or vertical film is not squeezed into 16:9). Returns path."""
    w0, h0 = Image.open(cells[0][1]).size
    if cols is None:
        cols = 4 if w0 / h0 >= 1.5 else 5 if w0 / h0 >= 0.9 else 7
    gap, band = 6, 50
    cw = (SHEET_W - gap * (cols - 1)) // cols
    ch = round(cw * h0 / w0)
    rows = -(-len(cells) // cols)
    top = 34 if head else 0
    sheet = Image.new("RGB", (SHEET_W, top + rows * (ch + band + gap)), "white")
    draw = ImageDraw.Draw(sheet)
    big, small = _font(24), _font(21)
    if head:
        draw.text((4, 3), head, fill="black", font=big)
    for i, (t, p) in enumerate(cells):
        x, y = (i % cols) * (cw + gap), top + (i // cols) * (ch + band + gap)
        sheet.paste(Image.open(p).convert("RGB").resize((cw, ch), Image.LANCZOS), (x, y))
        draw.text((x + 3, y + ch), _clock(t), fill=(200, 30, 30), font=big)
        words = " ".join(w for s, e, w in said if s < t + step and e > t)
        if words:
            lead = draw.textlength(_clock(t) + "  ", font=big)
            draw.text(
                (x + 3 + lead, y + ch + 2),
                _fit(draw, words, small, cw - lead - 6),
                fill="black",
                font=small,
            )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path, quality=82)
    return path


def sheets(d, out_dir, said=(), per=SHEET_PER, name="film", span=None):
    """The whole film a frame a second, from the frames in d (<t>.png, as tools.motion() renders
    them: every rate includes the whole seconds), on sheets of `per` in out_dir: film-01.jpg ...
    Each frame carries its time and the narration of that second, so a line that is said and not
    shown can be seen. span (a, b): only that stretch (a scene's pass). -> [paths]"""
    fs = [(t, p) for t, p in _frames(d) if abs(t - round(t)) < 1e-6]
    if span:
        fs = [(t, p) for t, p in fs if span[0] <= t <= span[1]]
    if not fs:
        return []
    for old in os.listdir(out_dir) if os.path.isdir(out_dir) else []:
        if old.startswith(name + "-") and old.endswith(".jpg"):
            os.remove(os.path.join(out_dir, old))
    out = []
    for n in range(0, len(fs), per):
        part = fs[n : n + per]
        head = "The film from %s to %s, a frame a second (sheet %d of %d)" % (
            _clock(part[0][0]),
            _clock(part[-1][0]),
            n // per + 1,
            -(-len(fs) // per),
        )
        out.append(
            tile(
                part,
                os.path.join(out_dir, "%s-%02d.jpg" % (name, n // per + 1)),
                said=said,
                head=head,
            )
        )
    return out


def strip(cells, path, said=(), at=None):
    """A close look at one moment: frames a tenth of a second apart on one row or two."""
    step = cells[1][0] - cells[0][0] if len(cells) > 1 else 0.1
    head = "Close-up around %s: a frame every %.2g s" % (
        _clock(round(at if at is not None else cells[0][0], 1)),
        step,
    )
    return tile(cells, path, cols=4, said=said, step=step, head=head)


def _runs(flags):
    """[(first, last)] index runs where flags is true."""
    runs, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def analyse(d, sheet_path, shown="outputs/review/motion.png"):
    """The frames in folder d (<t>.png) -> (text for Claude, whether a sheet was written at
    sheet_path, which Claude knows as `shown`)."""
    fs = _frames(d)
    if len(fs) < 3:
        return "Too few frames to judge the motion.", False
    ts = [t for t, _ in fs]
    small = [
        np.asarray(
            Image.open(p)
            .convert("L")
            .resize((192, 108), Image.BILINEAR)
            .filter(ImageFilter.GaussianBlur(1)),
            dtype=np.int16,
        )
        for _, p in fs
    ]
    # ch[i]: the % of pixels that changed from frame i-1 to frame i (ch[0] is not a change)
    ch = [0.0] + [
        100.0 * float(np.mean(np.abs(small[i] - small[i - 1]) > CHANGE))
        for i in range(1, len(small))
    ]
    step = ts[1] - ts[0]

    stills = []
    for a, b in _runs([i > 0 and c < STILL for i, c in enumerate(ch)]):
        t0, t1 = ts[a - 1], ts[b]  # the frames from a-1 to b are all alike
        if t1 - t0 >= STILL_S:
            stills.append((t0, t1))
    cuts = []
    for a, b in _runs([c > CUT for c in ch]):
        x, y = ts[a - 1], ts[b]  # the last frame before, the first after
        # not the opening draw-on, nor the fade at the end
        if (b - a + 1) * step <= CUT_MAX_S and x >= 0.5 and y < ts[-1] - 0.3:
            cuts.append((x, y))

    lines = ["Motion, from frames every %.2f s:" % step]
    if cuts:
        lines.append(
            "- Cuts or transitions at %s. For each, the sheet shows the frame before, the frame "
            "after and one a second later: see that something carries over from one scene to the "
            "next (a character, an object, the camera's move), and that the new scene has its "
            "subject in frame, not an empty stage waiting for it."
            % ", ".join("%.1f s" % ((x + y) / 2) for x, y in cuts)
        )
    else:
        lines.append("- No cuts: one continuous shot.")
    if stills:
        for t0, t1 in stills:
            lines.append(
                "- Still for %.1f s, from %.1f to %.1f s: nothing on screen moves. Give it motion "
                "(a slow camera drift or push, a character's small action, something drawing on)."
                % (t1 - t0, t0, t1)
            )
    else:
        lines.append("- Nothing holds still for %g s or more." % STILL_S)

    rows = [
        (
            "cut at %.1f s" % ((x + y) / 2),
            [(x, "before"), (y, "after"), (min(y + 1, ts[-1]), "+1 s")],
        )
        for x, y in cuts[:SHEET_CUTS]
    ] + [
        ("still %.1f-%.1f s" % (x, y), [(x, "start"), ((x + y) / 2, "middle"), (y, "end")])
        for x, y in stills[:SHEET_STILLS]
    ]
    if not rows:
        return "\n".join(lines), False
    near = lambda t: min(fs, key=lambda f: abs(f[0] - t))[1]  # noqa: E731
    w0, h0 = Image.open(fs[0][1]).size  # the film's own shape: a square film is not squeezed
    W, top = 480, 30
    H = round(W * h0 / w0)
    sheet = Image.new("RGB", (3 * W + 20, len(rows) * (H + top + 6)), "white")
    draw = ImageDraw.Draw(sheet)
    font = _font(22)
    for r, (label, cells) in enumerate(rows):
        y = r * (H + top + 6)
        for c, (t, what) in enumerate(cells):
            x = c * (W + 10)
            sheet.paste(Image.open(near(t)).convert("RGB").resize((W, H)), (x, y + top))
            draw.text(
                (x + 4, y + 5), "%s -- %s (%.2f s)" % (label, what, t), fill="black", font=font
            )
    os.makedirs(os.path.dirname(sheet_path), exist_ok=True)
    sheet.save(sheet_path)
    lines.append("Read %s to see them." % shown)
    return "\n".join(lines), True


# ------------------------------------------------------------------ what the drawing code says
# sketch/probe.js plays a film every tenth of a second without painting it and reports what each
# cast member's functions drew, where, under what transform and inside what clip. events() reads
# that for the moments a film breaks between two review stills. Nothing is asked of how a film is
# written: who is somebody is worked out from the drawing itself (a room fills the frame, a sofa
# never leaves its place in the world, a carrier has others drawn inside it; what is left moves).
# These only point: each becomes a sentence and a close-up to look at, never a verdict.
SEEN_ALPHA = 0.3  # fainter than this, a thing is fading in or out and is not counted
STATIC = 60  # world units: a thing that strays less than this all film long is furniture
BODY = 0.004  # of the frame: a pose's usual size on screen; smaller is a sparkle, not somebody
NEAR = 0.12  # of the frame: two boxes this close are one body changing pose, not two bodies
BRIEF_S = 1.0  # two poses that otherwise take turns, both on screen for at most this: a double
SQUASH, SLIVER = 0.6, 0.45  # the ratio of a body's two scales: under these, squashed / a sliver
SQUASH_MOVES = 0.25  # ... and changing by this much within the second: a held squash is a shadow
JUMP = 0.3  # of the view's width, in one step with no cut: a jump
# of a body, hidden by the clip it was drawn through, for this long. Measured on the bench: a cat
# inside her carrier loses 25% of her box to its opening and looks right; one too big for the
# opening she is coming out of loses 49-60%; the same scene with a taller carrier, 0%.
HIDDEN, HIDDEN_S = 0.3, 0.3
# a colour laid over the whole frame, and coming or going: its opacity moving this much within
# this long. An evening tint multiplied over a living room rose from 0 to 0.34 in two seconds
# ("the screen all changes the color like a filter is applied", said its owner). A textured
# background is a translucent fill over the frame too, but the same one all film long.
VEIL, VEIL_S = 0.08, 2.0
KINDS = ("double", "cut", "into", "sliver", "wash", "jump", "squash", "pop")  # most telling first


def _clock2(t):
    return "%d:%04.1f" % (t // 60, t % 60)


def _scopes(report):
    """[(t, cam, [scope])] from probe.js's report; a scope is a dict with the box in frame
    fractions, its centre in world units, and whether enough of it is on the frame to see."""
    keys, W, H = report["keys"], report["w"], report["h"]
    out = []
    for f in report["frames"]:
        cam, ss = f.get("cam"), []
        for k, x0, y0, x1, y1, ops, an_max, _an_min, cut, clipped, alpha, ov, parent in f["s"]:
            x0, y0, x1, y1 = x0 / 1000, y0 / 1000, x1 / 1000, y1 / 1000
            box = max(1e-9, (x1 - x0) * (y1 - y0))
            vis = max(0.0, min(1, x1) - max(0, x0)) * max(0.0, min(1, y1) - max(0, y0))
            cx, cy = (x0 + x1) / 2 * W, (y0 + y1) / 2 * H
            member, _, fn = keys[k].partition(".")
            ss.append(
                {
                    "key": keys[k],
                    "member": member,
                    "fn": fn,
                    "box": (x0, y0, x1, y1),
                    "on": alpha >= SEEN_ALPHA and not ov and (vis / box >= 0.15 or vis >= 0.01),
                    "inside": x0 >= 0.02 and x1 <= 0.98 and y0 >= 0.02 and y1 <= 0.98,
                    "world": ((cx - cam[1]) / cam[0], (cy - cam[2]) / cam[0]) if cam else (cx, cy),
                    "an": an_max,
                    "cut": cut,
                    "clipped": bool(clipped),
                    "ov": bool(ov),
                    "parent": keys[parent] if parent >= 0 else None,
                    "ops": ops,
                }
            )
        out.append((f["t"], cam, ss))
    return out


def _cam_cuts(frames, W):
    """Indices i where the camera cut between frame i-1 and i (a jump of the view, not a move)."""
    cuts = set()
    for i in range(1, len(frames)):
        a, b = frames[i - 1][1], frames[i][1]
        if not a or not b:
            continue
        xa, xb = (W / 2 - a[1]) / a[0], (W / 2 - b[1]) / b[0]
        ya, yb = -a[2] / a[0], -b[2] / b[0]
        view = W / max(a[0], b[0])
        zoom = max(a[0], b[0]) / max(1e-9, min(a[0], b[0]))
        if zoom > 1.25 or abs(xa - xb) > 0.3 * view or abs(ya - yb) > 0.3 * view:
            cuts.add(i)
    return cuts


def _index_runs(idx):
    """[(first, last)] runs of consecutive integers in idx."""
    idx = sorted(idx)
    runs, a = [], None
    for j, i in enumerate(idx):
        if a is None:
            a = i
        if j + 1 == len(idx) or idx[j + 1] != i + 1:
            runs.append((a, i))
            a = None
    return runs


def events(report, step=None):
    """probe.js's report -> [{t0, t1, kind, who, text}], most telling first. kind: double (the same
    character twice for a moment), cut (it is cut by the edge of the thing it is in), into (it goes
    into or out of something), sliver / squash (its whole body squashed through flat), jump (it
    moves across the frame in one step), pop (it appears or vanishes in the middle of the frame)."""
    if not report or not report.get("frames"):
        return []
    frames = _scopes(report)
    step = step or report.get("step") or 0.1
    n, W = len(frames), report["w"]
    cuts = _cam_cuts(frames, W)
    on = [[s for s in ss if s["on"]] for _, _, ss in frames]
    t_of = [t for t, _, _ in frames]
    near = NEAR + 0.6 * max(0.0, step - 0.1)  # a coarser look: more room for a pose to hand over
    seen, drawn, cover, where = {}, {}, {}, {}  # key -> frames on screen / drawn / shares / centres
    for i, (_, _, ss) in enumerate(frames):
        for s in ss:
            if s["ov"]:
                continue
            x0, y0, x1, y1 = s["box"]
            cover.setdefault(s["key"], []).append(
                max(0.0, min(1, x1) - max(0, x0)) * max(0.0, min(1, y1) - max(0, y0))
            )
            where.setdefault(s["key"], []).append(s["world"])
            drawn.setdefault(s["key"], set()).add(i)
            if s["on"]:
                seen.setdefault(s["key"], set()).add(i)
    mid = lambda v: sorted(v)[len(v) // 2]  # noqa: E731
    # Who can be somebody. Not a set (a room fills the frame). Not furniture: the sofa, the
    # portrait on the wall never leave their place in the world, and they are there from the
    # moment their set is, to the moment it goes -- the camera turns away from them, they do not
    # come and go. (A cat who walks in and then sits in one spot till the end has not left her
    # place either, but she arrived in the middle of the room's time: somebody.) Not a thing to
    # be in (what another cast call is drawn inside: a carrier, a picture frame). And big enough
    # (a sparkle or a crumb is drawn by the cast too).
    holds = {s["parent"] for _, _, ss in frames for s in ss if s["parent"]}
    sets = [k for k in drawn if mid(cover[k]) >= 0.9]
    edges = {0, n}  # the frames where a set comes or goes, and the film's two ends
    for a in sets:
        for i0, i1 in _index_runs(drawn[a]):
            edges |= {i0, i1 + 1}
    body = set()
    for k, fr in seen.items():
        if k in holds or k in sets or mid(cover[k]) < BODY:
            continue
        mx, my = mid([p[0] for p in where[k]]), mid([p[1] for p in where[k]])
        off = sorted(((x - mx) ** 2 + (y - my) ** 2) ** 0.5 for x, y in where[k])
        still = off[int(0.9 * (len(off) - 1))] < STATIC
        with_its_set = all(
            any(abs(e - i) <= 2 for e in edges)
            for i0, i1 in _index_runs(drawn[k])
            for i in (i0, i1 + 1)
        )
        if not (still and with_its_set):
            body.add(k)
    members = {}
    for k in sorted(body):
        members.setdefault(k.partition(".")[0], []).append(k)
    out = []

    def _far(a, b):
        """Two boxes in different places (not one pose handing over to the next where it is)."""
        ax, ay = (a["box"][0] + a["box"][2]) / 2, (a["box"][1] + a["box"][3]) / 2
        bx, by = (b["box"][0] + b["box"][2]) / 2, (b["box"][1] + b["box"][3]) / 2
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 > near

    def add(kind, i0, i1, who, text):
        out.append(
            {
                "t0": round(t_of[i0], 2),
                "t1": round(t_of[i1], 2),
                "kind": kind,
                "who": who,
                "text": text,
            }
        )

    # ---- double: two poses of one member that otherwise take turns, both on screen for a moment
    for member, ks in members.items():
        for a in range(len(ks)):
            for b in range(a, len(ks)):
                f, g = ks[a], ks[b]
                both = []
                for i in seen[f] & seen[g]:
                    fs = [s for s in on[i] if s["key"] == f]
                    gs = [s for s in on[i] if s["key"] == g]
                    if f == g:
                        fs, gs = fs[:1], fs[1:]
                    if any(
                        _far(x, y) and x["parent"] != y["key"] and y["parent"] != x["key"]
                        for x in fs
                        for y in gs
                    ):
                        both.append(i)
                meant = max(BRIEF_S, 0.05 * min(len(seen[f]), len(seen[g])) * step)
                if not both or len(both) * step > meant:
                    continue  # together for long: a mirror, a portrait, a twin -- meant
                for i0, i1 in _index_runs(both):
                    if (i1 - i0 + 1) * step <= BRIEF_S:
                        add(
                            "double",
                            i0,
                            i1,
                            member,
                            "%s is on screen twice from %s to %s (%s and %s, in two places)"
                            % (member, _clock2(t_of[i0]), _clock2(t_of[i1]), f, g),
                        )

    # ---- per member, frame to frame: into / out of a clip, a jump, appearing, vanishing
    for member, ks in members.items():
        prev = None
        for i in range(n):
            cur = [s for s in on[i] if s["key"] in ks]
            if prev is not None and i not in cuts:
                if prev and cur:
                    a, b = max(prev, key=lambda s: s["ops"]), max(cur, key=lambda s: s["ops"])
                    if a["clipped"] != b["clipped"] and not _far(a, b):
                        into = b["clipped"]
                        thing = ((b if into else a)["parent"] or "something").partition(".")[0]
                        add(
                            "into",
                            i - 1,
                            i,
                            member,
                            "%s goes %s %s at %s"
                            % (member, "into" if into else "out of", thing, _clock2(t_of[i])),
                        )
                    elif len(prev) == 1 and len(cur) == 1:
                        view = W / max(1e-9, (frames[i][1] or [1])[0])
                        dx, dy = a["world"][0] - b["world"][0], a["world"][1] - b["world"][1]
                        if (dx * dx + dy * dy) ** 0.5 > JUMP * view:
                            add(
                                "jump",
                                i - 1,
                                i,
                                member,
                                "%s jumps across the frame in one step at %s"
                                % (member, _clock2(t_of[i])),
                            )
                elif bool(prev) != bool(cur):
                    s = max(cur or prev, key=lambda s: s["ops"])
                    if s["inside"] and not s["clipped"]:
                        add(
                            "pop",
                            i - 1,
                            i,
                            member,
                            "%s %s in the middle of the frame at %s"
                            % (member, "appears" if cur else "vanishes", _clock2(t_of[i])),
                        )
            prev = cur

    # ---- wash: the film lays a colour over the whole frame, and it comes or goes mid-shot
    veil = [float(f.get("v") or 0) for f in report["frames"]]
    k = max(1, round(VEIL_S / step))
    moved = [
        i
        for i in range(k, n)
        if abs(veil[i] - veil[i - k]) >= VEIL
        and not any(j in cuts for j in range(i - k + 1, i + 1))
    ]
    for i0, i1 in _index_runs(moved):
        j0 = max(0, i0 - k)
        a, b = veil[j0], veil[i1]
        while j0 < i0 and abs(veil[j0 + 1] - a) <= 0.01:  # where it starts to move, not 2 s before
            j0 += 1
        add(
            "wash",
            j0,
            i1,
            "the film",
            "a colour is laid over the whole frame from %s to %s (its strength goes from %d%% to "
            "%d%%): it reads as a filter being switched %s"
            % (
                _clock2(t_of[j0]),
                _clock2(t_of[i1]),
                round(100 * a),
                round(100 * b),
                "on" if b > a else "off",
            ),
        )

    # ---- cut: a body drawn through a clip that hides a good part of it (the opening of a carrier
    # too small for the cat coming out of it: she stands half out, sliced by a line in mid-air)
    hid = {}
    for i, ss in enumerate(on):
        for s in ss:
            if s["key"] in body and s["clipped"] and s["cut"] >= HIDDEN:
                hid.setdefault(s["key"], {})[i] = max(s["cut"], hid.get(s["key"], {}).get(i, 0))
    for k, at in hid.items():
        for i0, i1 in _index_runs(at):
            if (i1 - i0 + 1) * step < HIDDEN_S:
                continue
            add(
                "cut",
                i0,
                i1,
                k.partition(".")[0],
                "%s is cut by the edge of what it is inside from %s to %s: up to %d%% of it is "
                "hidden" % (k, _clock2(t_of[i0]), _clock2(t_of[i1]), round(100 * max(at.values()))),
            )

    # ---- sliver / squash: a whole body squashed, and the squash changing
    low = {}
    for i, ss in enumerate(on):
        for s in ss:
            if s["key"] in body and s["an"] < SQUASH:
                low.setdefault(s["key"], {})[i] = min(s["an"], low.get(s["key"], {}).get(i, 1))
    for k, at in low.items():
        for i0, i1 in _index_runs(at):
            around = [
                s["an"]
                for i in range(max(0, i0 - 5), min(n, i1 + 6))
                for s in on[i]
                if s["key"] == k
            ]
            lo = min(at[i] for i in range(i0, i1 + 1))
            if max(around) - lo < SQUASH_MOVES:
                continue  # held like that: a shadow, a reflection
            kind = "sliver" if lo < SLIVER else "squash"
            add(
                kind,
                i0,
                i1,
                k.partition(".")[0],
                "%s is squashed to %d%% of its shape at %s%s"
                % (
                    k,
                    round(lo * 100),
                    _clock2(t_of[i0]),
                    " (flipped or spun through flat)" if kind == "sliver" else "",
                ),
            )
    # one event for one thing: a spin that passes through flat five times is one spin
    out.sort(key=lambda e: (e["kind"], e["who"], e["t0"]))
    merged = []
    for e in out:
        m = merged[-1] if merged else None
        if m and (m["kind"], m["who"]) == (e["kind"], e["who"]) and e["t0"] - m["t1"] <= 1.0:
            m["t1"] = max(m["t1"], e["t1"])
        else:
            merged.append(e)
    merged.sort(key=lambda e: (KINDS.index(e["kind"]), e["t0"]))
    return merged
