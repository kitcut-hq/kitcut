#!/usr/bin/env python
"""words.json + caption-style.json -> ASS with red info-card + per-word highlight.

Style replicates the info-cards used in youtu.be/egr4Y4oZgLM (solid #FF0000
rounded card, white bold uppercase Cyrillic, centred, lower third), extended
with a spotlight highlight on the word currently being spoken.

Technique: one Dialogue event per (word x state), each holding a SINGLE word
anchored with \\pos at a coordinate precomputed in Python. Layout is therefore
time-invariant and cannot reflow when a word changes colour. libass karaoke
(\\k) was rejected: it is monotonic two-state and cannot express a spotlight
that reverts previous words to the base colour.

All timing is in integer centiseconds, rounded exactly once at ingest, so
consecutive states share byte-identical boundaries and libass never shows a
one-frame gap between them.

Invoke as:  python -X utf8 -E scripts/build-captions-ass.py ...
"""
import sys, os, json, argparse, unicodedata

# Drop any site-packages that belongs to a DIFFERENT Python install. A stale
# machine-wide PYTHONPATH gets prepended to sys.path and shadows this
# interpreter's packages with incompatible ones (or, once that install is
# removed, with nothing at all). sys.path is frozen at startup so clearing
# os.environ in-process cannot help -- hence also `-E` at the call site.
import sysconfig as _sc, site as _site
def _norm(p):
    return os.path.normcase(os.path.abspath(p))
_own = {_norm(p) for p in (_sc.get_paths().get("purelib"),
                           _sc.get_paths().get("platlib")) if p}
for _getter in (lambda: [_site.getusersitepackages()], _site.getsitepackages):
    try:
        _own.update(_norm(p) for p in _getter())
    except Exception:
        pass          # user site is where Store Python puts pip installs
sys.path[:] = [p for p in sys.path
               if "site-packages" not in p.lower() or _norm(p) in _own]
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fontTools.ttLib import TTFont

BS = chr(92)          # dodge backslash-escaping pain, as shorts/bpo/captions.py does
SENT_END = ".!?…"


# ---------------------------------------------------------------- helpers
def fmt_cs(c):
    c = max(0, int(c))       # safety net: ASS cannot express negative time
    h, c = divmod(c, 360000)
    m, c = divmod(c, 6000)
    s, c = divmod(c, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, c)


def _num(v):
    """Format a number for ASS: keep ints int so output stays byte-stable."""
    f = float(v)
    return str(int(f)) if f == int(f) else ("%g" % f)


def ass_colour(hexstr, alpha=0):
    h = hexstr.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "&H%02X%02X%02X%02X" % (alpha, b, g, r)


class Metrics:
    """Width measurement via raw hmtx advances -- matches unhinted FreeType, which
    is what libass uses. PIL is deliberately NOT used: it has no HarfBuzz here
    (raqm False), so it returns hinted integer advances that drift up to 0.5px
    per glyph and do not accumulate linearly."""

    def __init__(self, path, size=None, spacing=0.0, fudge=1.0, cap_height_px=None):
        self.f = TTFont(path)
        self.upem = self.f["head"].unitsPerEm
        self.cmap = self.f.getBestCmap()
        self.hmtx = self.f["hmtx"]
        self.size, self.spacing, self.fudge = size, spacing, fudge
        os2 = self.f["OS/2"]
        self.cap = getattr(os2, "sCapHeight", 0) or int(0.7 * self.upem)
        self.win_asc = os2.usWinAscent
        self.win_desc = os2.usWinDescent
        # libass/VSFilter scale a nominal Fontsize so that the font's
        # usWinAscent+usWinDescent spans it -- NOT unitsPerEm. For Montserrat
        # that is 1562 units, so a nominal 43px renders at 43*1000/1562 = 0.64
        # of the size you would naively predict. Verified empirically against
        # rendered ink: predicted ratio 0.6402 vs measured 0.6412.
        self.den = (self.win_asc + self.win_desc) or self.upem
        self.family = self.f["name"].getDebugName(1)
        self._notdef = set()

        if size is None:
            if cap_height_px is None:
                raise ValueError("Metrics needs either size or cap_height_px")
            # Size the font by the visual quantity you can actually measure off a
            # reference frame. Solving through `den` (not upem) is what makes this
            # land correctly -- see the class docstring and docs/karaoke-captions.md
            size = cap_height_px * self.den / float(self.cap)
        self.size = int(round(size))

    @property
    def px(self):
        """units -> pixels scale factor as libass actually applies it"""
        return self.size / self.den

    def _adv(self, ch):
        gn = self.cmap.get(ord(ch))
        if gn is None:
            self._notdef.add(ch)
            gn = self.cmap.get(ord("?"))
        return self.hmtx[gn][0]

    def width(self, text):
        u = sum(self._adv(c) for c in text) * self.px
        return u * self.fudge + self.spacing * len(text)

    @property
    def space(self):
        return self.width(" ")

    @property
    def cap_px(self):
        return self.cap * self.px

    def cy_for_cap_center(self, cap_center_y):
        """libass \\an5 centres the font's LINE box, not the cap box. The line box
        is exactly `size` px tall (that is what the win-metric scaling means), so
        solve for the \\pos y that puts the cap box centre where we want it."""
        baseline_from_top = self.win_asc * self.px
        # cap_center = (cy - size/2) + baseline_from_top - cap_px/2
        return cap_center_y + self.size / 2.0 - baseline_from_top + self.cap_px / 2.0

    def missing(self):
        return sorted(self._notdef)


# ---------------------------------------------------------------- ingest
def sanitize(words, cfg):
    tcfg = cfg["text"]
    apo = tcfg["apostrophe"]
    out = []
    for w in words:
        t = unicodedata.normalize("NFC", w["text"]).strip()
        for bad in ("'", "ʼ", "’", "´", "`"):
            t = t.replace(bad, apo)
        strip = tcfg.get("strip_trailing", "")
        while strip and t and t[-1] in strip:
            t = t[:-1]
        if tcfg.get("uppercase"):
            t = t.upper()
        if not t:
            continue
        s_cs = int(round(w["start"] * 100))
        e_cs = int(round(w["end"] * 100))
        if e_cs <= s_cs:
            e_cs = s_cs + 1
        out.append(dict(text=t, raw=w["text"].strip(), s=s_cs, e=e_cs,
                        prob=w.get("probability", 1.0)))
    for i in range(1, len(out)):
        if out[i]["s"] < out[i - 1]["s"]:
            out[i]["s"] = out[i - 1]["s"]
        if out[i]["e"] <= out[i]["s"]:
            out[i]["e"] = out[i]["s"] + 1
    return out


# ---------------------------------------------------------------- wrapping
def wrap_lines(texts, m, max_w, max_lines):
    """Greedy wrap. Returns list of lists of indices, or None if it will not fit."""
    lines, cur = [], []
    sp = m.space
    for i in range(len(texts)):
        trial = cur + [i]
        w = sum(m.width(texts[j]) for j in trial) + sp * (len(trial) - 1)
        if cur and w > max_w:
            lines.append(cur)
            cur = [i]
            if len(lines) >= max_lines:
                return None
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines if len(lines) <= max_lines else None


# ---------------------------------------------------------------- grouping
def group_words(words, cfg, m):
    g = cfg["grouping"]
    gap_cs = int(g["gap_break_s"] * 100)
    maxdur = int(g["max_group_duration_s"] * 100)
    maxw = g["max_words"]
    max_line = cfg["layout"]["max_line_width_px"]
    max_lines = cfg["layout"]["max_lines"]

    groups, cur = [], []
    for w in words:
        trial = cur + [w]
        too_wide = wrap_lines([x["text"] for x in trial], m, max_line, max_lines) is None
        if cur and (too_wide
                    or len(trial) > maxw
                    or w["s"] - cur[-1]["e"] > gap_cs
                    or w["e"] - cur[0]["s"] > maxdur):
            groups.append(cur)
            cur = [w]
        else:
            cur = trial
        if cur and g["break_on_sentence_end"] and cur[-1]["raw"][-1:] in SENT_END:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


# ---------------------------------------------------------------- layout
def layout(group, cfg, m, bottom_margin=None):
    texts = [w["text"] for w in group]
    L = cfg["layout"]
    lines = wrap_lines(texts, m, L["max_line_width_px"], L["max_lines"])
    if lines is None:
        lines = [list(range(len(texts)))]
    sp = m.space * cfg["text"].get("word_gap_ratio", 1.0)
    lh = L["line_height_px"]
    n = len(lines)

    ink_h = (n - 1) * lh + m.cap_px
    pad_y, pad_x = cfg["card"]["pad_y_px"], cfg["card"]["pad_x_px"]
    card_h = ink_h + 2 * pad_y
    if bottom_margin is None:
        bottom_margin = L["bottom_margin_px"]
    card_bottom = cfg["canvas"]["play_res_y"] - bottom_margin
    card_top = card_bottom - card_h

    widths = [sum(m.width(texts[j]) for j in ln) + sp * (len(ln) - 1) for ln in lines]
    card_w = max(widths) + 2 * pad_x
    card_x = L["anchor_x"] - card_w / 2.0

    placed = []
    for li, ln in enumerate(lines):
        cap_center = card_top + pad_y + li * lh + m.cap_px / 2.0
        cy = m.cy_for_cap_center(cap_center)
        x = L["anchor_x"] - widths[li] / 2.0
        for j in ln:
            wpx = m.width(texts[j])
            placed.append(dict(i=j, cx=x + wpx / 2.0, cy=cy))
            x += wpx + sp
    placed.sort(key=lambda p: p["i"])
    return placed, (card_x, card_top, card_w, card_h)


# ---------------------------------------------------------------- timing
def state_windows(group, cfg, prev_end, next_start):
    T = cfg["timing"]
    lead = T["lead_in_ms"] // 10
    hold = T["hold_out_ms"] // 10
    min_act = T["min_active_ms"] // 10
    min_gap = T["min_gap_between_groups_ms"] // 10

    g0 = group[0]["s"] - lead
    if prev_end is not None:
        g0 = max(g0, prev_end + min_gap)
    g0 = min(g0, group[0]["s"])
    g0 = max(0, g0)          # ASS has no negative timestamps
    g1 = group[-1]["e"] + hold
    if next_start is not None:
        g1 = min(g1, next_start - min_gap)
    g1 = max(g1, group[-1]["e"])

    # active window of word i runs to word i+1's start, so the highlight moves
    # continuously instead of strobing through every inter-word micro-gap
    bounds = []
    for i, w in enumerate(group):
        a = w["s"]
        if T["active_extends_to_next_word"] and i + 1 < len(group):
            b = group[i + 1]["s"]
        else:
            b = w["e"]
        bounds.append([a, max(b, a + min_act)])

    for i in range(len(bounds)):
        bounds[i][0] = max(bounds[i][0], g0)
        if i:
            bounds[i][0] = max(bounds[i][0], bounds[i - 1][1])
        bounds[i][1] = max(bounds[i][1], bounds[i][0] + min_act)
    bounds[-1][1] = min(bounds[-1][1], g1)
    if bounds[-1][1] <= bounds[-1][0]:
        bounds[-1][1] = bounds[-1][0] + 1
    g1 = max(g1, bounds[-1][1])
    return g0, g1, bounds


# ---------------------------------------------------------------- emit
def rounded_rect(w, h, r):
    r = max(0.0, min(r, min(w, h) / 2.0))

    def f(v):
        return ("%.1f" % v).rstrip("0").rstrip(".")

    return ("m %s 0 l %s 0 b %s 0 %s 0 %s %s "
            "l %s %s b %s %s %s %s %s %s "
            "l %s %s b 0 %s 0 %s 0 %s "
            "l 0 %s b 0 0 0 0 %s 0") % (
        f(r), f(w - r), f(w), f(w), f(w), f(r),
        f(w), f(h - r), f(w), f(h), f(w), f(h), f(w - r), f(h),
        f(r), f(h), f(h), f(h), f(h - r),
        f(r), f(r))


def lift_for_overlays(g0_cs, g1_cs, cfg, m, overlays):
    """If the SOURCE already has its own graphic where this card would sit, lift
    the card clear of it. Returns an effective bottom margin (px).

    The lift is computed per group, so the card never moves mid-caption -- a
    jump partway through a line would read as a glitch rather than a choice.
    """
    L = cfg["layout"]
    base_margin = L["bottom_margin_px"]
    if not overlays:
        return base_margin
    gap = cfg["card"].get("collision_gap_px", 16)
    play_y = cfg["canvas"]["play_res_y"]
    card_bottom = play_y - base_margin

    t0, t1 = g0_cs / 100.0, g1_cs / 100.0
    need = base_margin
    for ov in overlays:
        if ov["end"] <= t0 or ov["start"] >= t1:
            continue
        # only a graphic that reaches ABOVE our card bottom can collide;
        # the full-width bars at y>=972 sit below it and are harmless
        if ov["top_y"] >= card_bottom:
            continue
        need = max(need, play_y - (ov["top_y"] - gap))
    return need


def pop_tags(P, dur_ms):
    """Scale-pop on the active word.

    Uses \\fscx/\\fscy, never \\fs: \\fs re-shapes the glyphs at a new pixel size so
    FreeType hinting snaps stems to a different grid each step and the word
    visibly wobbles. \\fscx is an affine transform of an already-shaped outline.

    Safe against reflow because every word is its own \\pos-anchored event, so
    scaling grows it about its own centre and cannot push its neighbours.
    The animation always settles back to 100 so there is no snap when the word
    hands over to the spoken state.
    """
    scale = P.get("scale", 112)
    rise = int(P.get("rise_ms", 70))
    settle = int(P.get("settle_ms", 110))
    if rise + settle > dur_ms:                       # never overrun the event
        total = max(1.0, float(rise + settle))
        rise = int(rise * dur_ms / total)
        settle = int(settle * dur_ms / total)
    return ("%sfscx100%sfscy100%st(0,%d,%sfscx%s%sfscy%s)%st(%d,%d,%sfscx100%sfscy100)"
            % (BS, BS, BS, rise, BS, _num(scale), BS, _num(scale),
               BS, rise, rise + settle, BS, BS))


def build(words, cfg, m, overlays=None):
    C, S, T = cfg["canvas"], cfg["states"], cfg["timing"]
    base_c = ass_colour(S["base"]["colour"])
    act_c = ass_colour(S["active"]["colour"])
    card_c = ass_colour(cfg["card"]["colour"], cfg["card"].get("alpha", 0))
    fade = T["fade_ms"]
    fam, fsz, fsp = cfg["font"]["family"], m.size, cfg["font"].get("spacing", 0)
    bold = cfg["font"].get("bold", 0)
    TX = cfg["text"]
    out_c = ass_colour(TX.get("outline_colour", "#000000"))
    sha_c = ass_colour(TX.get("shadow_colour", "#000000"))
    out_w = _num(TX.get("outline_px", 0))
    sha_w = _num(TX.get("shadow_px", 0))
    spoken_c = ass_colour(S.get("spoken", S["base"])["colour"])
    P = cfg.get("pop", {})
    pop_on = bool(P.get("enabled", False))

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\n"
        "PlayResY: %d\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Base,%s,%s,%s,%s,%s,%s,%d,0,0,0,100,100,%s,0,1,%s,%s,5,0,0,0,1\n"
        "Style: Act,%s,%s,%s,%s,%s,%s,%d,0,0,0,100,100,%s,0,1,%s,%s,5,0,0,0,1\n"
        "Style: Card,%s,%s,%s,%s,%s,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ) % (C["play_res_x"], C["play_res_y"],
         fam, fsz, base_c, base_c, out_c, sha_c, bold, fsp, out_w, sha_w,
         fam, fsz, act_c, act_c, out_c, sha_c, bold, fsp, out_w, sha_w,
         fam, fsz, card_c, card_c, card_c)

    # A distinct "already spoken" style is only needed when it differs from the
    # pending colour. spoken==base gives a moving spotlight; spoken==active gives
    # a progressive karaoke fill. Emitting it only when needed keeps the common
    # case byte-identical to the hand-verified output.
    spoken_style = "Base"
    if spoken_c != base_c:
        spoken_style = "Spok"
        header = header.replace(
            "\n[Events]",
            "\nStyle: Spok,%s,%s,%s,%s,%s,%s,%d,0,0,0,100,100,%s,0,1,%s,%s,5,0,0,0,1\n\n[Events]"
            % (fam, fsz, spoken_c, spoken_c, out_c, sha_c, bold, fsp, out_w, sha_w))

    groups = group_words(words, cfg, m)
    ev, dbg = [], []
    for gi, grp in enumerate(groups):
        prev_end = dbg[-1]["g1"] if dbg else None
        nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else None
        g0, g1, bounds = state_windows(grp, cfg, prev_end, nxt)
        bm = lift_for_overlays(g0, g1, cfg, m, overlays)
        placed, (cx0, cy0, cw, ch) = layout(grp, cfg, m, bottom_margin=bm)

        if cfg["card"].get("enabled", True):
            ev.append("Dialogue: 0,%s,%s,Card,,0,0,0,,{%san7%spos(%.1f,%.1f)%sbord0%sshad0%sfad(%d,%d)%s1c%s%sp1}%s{%sp0}"
                      % (fmt_cs(g0), fmt_cs(g1), BS, BS, cx0, cy0, BS, BS, BS, fade, fade,
                         BS, card_c, BS, rounded_rect(cw, ch, cfg["card"]["corner_radius_px"]), BS))

        for k, w in enumerate(grp):
            p = placed[k]
            pos = "%san5%spos(%.1f,%.1f)%sq2" % (BS, BS, p["cx"], p["cy"], BS)
            a, b = bounds[k]

            def fd(st, en):
                # fade only on group-boundary events, else the word strobes at
                # every single state change
                i_ = fade if st == g0 else 0
                o_ = fade if en == g1 else 0
                return ("%sfad(%d,%d)" % (BS, i_, o_)) if (i_ or o_) else ""

            if a > g0:
                ev.append("Dialogue: 1,%s,%s,Base,,0,0,0,,{%s%s}%s"
                          % (fmt_cs(g0), fmt_cs(a), pos, fd(g0, a), w["text"]))
            ev.append("Dialogue: 1,%s,%s,Act,,0,0,0,,{%s%s%s}%s"
                      % (fmt_cs(a), fmt_cs(b), pos, fd(a, b),
                         pop_tags(P, (b - a) * 10) if pop_on else "", w["text"]))
            if b < g1:
                ev.append("Dialogue: 1,%s,%s,%s,,0,0,0,,{%s%s}%s"
                          % (fmt_cs(b), fmt_cs(g1), spoken_style, pos, fd(b, g1), w["text"]))

        dbg.append(dict(gi=gi, g0=g0, g1=g1, card=[cx0, cy0, cw, ch], lifted=bm,
                        words=[dict(t=grp[k]["text"], cx=placed[k]["cx"], cy=placed[k]["cy"],
                                    w=m.width(grp[k]["text"]),
                                    a=bounds[k][0], b=bounds[k][1])
                               for k in range(len(grp))]))
    return header, ev, dbg, groups


def selfcheck(dbg, cfg):
    """Structural assertions. Proves the timing arithmetic is sound; says nothing
    about whether the timings match the audio (that is the frame probe's job)."""
    errs = []
    px = cfg["canvas"]["play_res_x"]
    for d in dbg:
        if d["g1"] <= d["g0"]:
            errs.append("group %d: non-positive duration" % d["gi"])
        prev = None
        for w in d["words"]:
            if w["b"] <= w["a"]:
                errs.append("group %d word %s: non-positive active window" % (d["gi"], w["t"]))
            if prev is not None and w["a"] < prev:
                errs.append("group %d word %s: active window overlaps previous" % (d["gi"], w["t"]))
            prev = w["b"]
            if w["cx"] - w["w"] / 2 < 0 or w["cx"] + w["w"] / 2 > px:
                errs.append("group %d word %s: off-canvas" % (d["gi"], w["t"]))
        cx0, cy0, cw, ch = d["card"]
        if cx0 < 0 or cx0 + cw > px:
            errs.append("group %d: card off-canvas (x=%.0f w=%.0f)" % (d["gi"], cx0, cw))
    for i in range(1, len(dbg)):
        if dbg[i]["g0"] < dbg[i - 1]["g1"]:
            errs.append("group %d overlaps group %d" % (i, i - 1))
    return errs


def scale_style(cfg, W, H):
    """Adapt a preset authored for one canvas (typically 1920x1080) to the actual
    video dimensions. Scales every pixel-denominated knob by the height ratio and
    re-centres the anchor. Exactly a no-op when dimensions already match, so the
    common case stays byte-identical to the hand-verified output."""
    C = cfg["canvas"]
    if (W, H) == (C["play_res_x"], C["play_res_y"]):
        return
    f = H / float(C["play_res_y"])
    F = cfg["font"]
    if F.get("size"):
        F["size"] = int(round(F["size"] * f))
    if F.get("cap_height_px"):
        F["cap_height_px"] = F["cap_height_px"] * f
    if F.get("spacing"):
        F["spacing"] = F["spacing"] * f
    L = cfg["layout"]
    centred = abs(L["anchor_x"] - C["play_res_x"] / 2.0) < 1.0
    L["anchor_x"] = W / 2.0 if centred else L["anchor_x"] * W / float(C["play_res_x"])
    L["bottom_margin_px"] = L["bottom_margin_px"] * f
    L["line_height_px"] = L["line_height_px"] * f
    # Scaled by height, then clamped to the frame. The clamp must budget for the
    # CARD, which is the text width plus horizontal padding on both sides --
    # clamping the text alone lets the card hang off the edge. Going landscape ->
    # vertical scales by x1.78 while the frame gets NARROWER, so this is exactly
    # where it bites.
    _pad_x = cfg["card"].get("pad_x_px", 0) * f
    L["max_line_width_px"] = min(L["max_line_width_px"] * f,
                                 0.94 * W - 2 * _pad_x)
    K = cfg["card"]
    for k in ("corner_radius_px", "pad_x_px", "pad_y_px", "collision_gap_px"):
        if k in K:
            K[k] = K[k] * f
    TX = cfg["text"]
    for k in ("outline_px", "shadow_px"):
        if k in TX:
            TX[k] = TX[k] * f
    C["play_res_x"], C["play_res_y"] = W, H
    print("style scaled x%.3f to canvas %dx%d" % (f, W, H))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", required=True)
    ap.add_argument("--style", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug-out", default=None)
    ap.add_argument("--overlays", default=None,
                    help="detect-overlays.py json; lifts cards clear of the "
                         "source video's own lower-third graphics")
    ap.add_argument("--range", nargs=2, type=float, default=None, metavar=("T0", "T1"))
    ap.add_argument("--time-offset", type=float, default=0.0)
    ap.add_argument("--scale-to", nargs=2, type=int, default=None, metavar=("W", "H"),
                    help="actual video dimensions; pixel-tuned style values are "
                         "scaled from the preset's canvas to these. A PlayRes that "
                         "mismatches the video makes libass silently rescale "
                         "everything -- this makes the adjustment explicit instead.")
    args = ap.parse_args()

    cfg = json.load(open(args.style, encoding="utf-8"))
    if args.scale_to:
        scale_style(cfg, *args.scale_to)
    data = json.load(open(args.words, encoding="utf-8"))
    F = cfg["font"]
    m = Metrics(F["file"], F.get("size"), F.get("spacing", 0), F.get("fudge", 1.0),
                cap_height_px=F.get("cap_height_px"))
    if not F.get("size"):
        print("font size %d derived from cap_height_px=%s (%s: cap %d, winAsc+winDesc %d)"
              % (m.size, F.get("cap_height_px"), m.family, m.cap, m.den))
    if m.family != cfg["font"]["family"]:
        print("WARNING: ASS Fontname '%s' != file family '%s' -- libass may substitute"
              % (cfg["font"]["family"], m.family))

    words = sanitize(data["words"], cfg)
    if args.range:
        t0, t1 = args.range
        words = [w for w in words if w["e"] / 100.0 >= t0 and w["s"] / 100.0 <= t1]
    if args.time_offset:
        off = int(round(args.time_offset * 100))
        for w in words:
            w["s"] -= off
            w["e"] -= off
        words = [w for w in words if w["e"] > 0]
        for w in words:
            w["s"] = max(0, w["s"])

    if not words:
        sys.exit("no words in range")

    overlays = None
    if args.overlays:
        overlays = json.load(open(args.overlays, encoding="utf-8"))
        if args.time_offset:
            # keep overlay windows on the same timeline as the shifted words
            for o in overlays:
                o["start"] -= args.time_offset
                o["end"] -= args.time_offset

    header, ev, dbg, groups = build(words, cfg, m, overlays=overlays)

    miss = m.missing()
    if miss:
        print("WARNING missing glyphs (would render as tofu):", miss)
    errs = selfcheck(dbg, cfg)
    for e in errs[:20]:
        print("SELFCHECK:", e)
    if errs:
        # Fatal, and BEFORE writing: an off-canvas card or an overlapping active
        # window is broken output. Printing a warning and rendering anyway wastes
        # a full encode and, worse, can ship a defect that looks deliberate.
        sys.exit("SELFCHECK: %d problem(s) -- refusing to write %s"
                 % (len(errs), args.out))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write(header + "\n".join(ev) + "\n")
    if args.debug_out:
        with open(args.debug_out, "w", encoding="utf-8") as f:
            json.dump(dbg, f, ensure_ascii=False)

    sizes = [len(g) for g in groups]
    print("words %d | groups %d | events %d | %.2f MB"
          % (len(words), len(groups), len(ev), os.path.getsize(args.out) / 1e6))
    print("words/group avg %.1f max %d" % (sum(sizes) / max(1, len(sizes)), max(sizes)))
    print("first card %.2fs, last ends %.2fs" % (dbg[0]["g0"] / 100.0, dbg[-1]["g1"] / 100.0))
    if overlays is not None:
        base_m = cfg["layout"]["bottom_margin_px"]
        lift = [d for d in dbg if d["lifted"] != base_m]
        print("cards lifted clear of source graphics: %d of %d (%d overlay ranges)"
              % (len(lift), len(dbg), len(overlays)))
        if lift:
            print("  lift margins used: %s"
                  % sorted(set(d["lifted"] for d in lift)))


if __name__ == "__main__":
    main()
