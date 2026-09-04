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

Invoke as:  python scripts/build-captions-ass.py ...
"""

import sys
import os
import json
import argparse
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module

from fontTools.ttLib import TTFont

_outline = import_module("transcript-outline")  # shared words-envelope loader

BS = chr(92)  # dodge backslash-escaping pain, as shorts/bpo/captions.py does
SENT_END = ".!?…"


# ---------------------------------------------------------------- helpers
def fmt_cs(c):
    c = max(0, int(c))  # safety net: ASS cannot express negative time
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
    per glyph and do not accumulate linearly.
    """

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
        """Units -> pixels scale factor as libass actually applies it"""
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
        """Libass \\an5 centres the font's LINE box, not the cap box. The line box
        is exactly `size` px tall (that is what the win-metric scaling means), so
        solve for the \\pos y that puts the cap box centre where we want it.
        """
        baseline_from_top = self.win_asc * self.px
        # cap_center = (cy - size/2) + baseline_from_top - cap_px/2
        return cap_center_y + self.size / 2.0 - baseline_from_top + self.cap_px / 2.0

    def missing(self):
        return sorted(self._notdef)


def _cap_i(t, apo):
    """The English pronoun "I", however faster-whisper felt about it that second.

    Whisper's casing is per-segment and inconsistent: this repo's Lenny's
    Podcast transcript has 312 correctly capitalised "I" and 78 lowercase ones
    from the same speaker in the same recording. One of them landed in a caption
    card in a pitch deliverable -- "equally wrong and i'm" -- which reads as our
    sloppiness, not the ASR's.

    Deliberately narrow: the standalone pronoun and its contractions only, never
    sentence-initial capitalisation in general, which cannot be done from a word
    list without knowing where sentences start. Opt-in via `text.capitalize_i`
    because it is English-only and this repo also cuts Ukrainian.
    """
    core = t.rstrip(".,!?;:…\"')")
    if not core or core[0] != "i":
        return t
    rest = core[1:]
    if rest and not (rest[0] == apo and rest[1:].lower() in ("m", "ll", "ve", "d")):
        return t
    return "I" + t[1:]


# ---------------------------------------------------------------- ingest
# The punctuation-glue RULE lives in transcript-outline.py, next to the loader
# that applies it for every consumer (captions, phrase anchors, dub units).
# One definition; this module only re-exports it for its own backstop below.
glues_back = _outline.glues_back


def glue_suffixes(out, strip=""):
    """Backstop for word lists that never passed through _outline.load_words.

    The loader already glues, and gluing is idempotent (a glued list has no
    suffix tokens left), so on the normal path this is a no-op. It stays
    because sanitize() also receives lists built in memory -- fixtures, dub
    word envelopes assembled by other scripts -- and because the apostrophe
    variants have been normalised to cfg's apostrophe by the time we run,
    which the raw-envelope loader cannot know about. The merged word stays lit
    for as long as both tokens were spoken, which is what keeps the per-word
    spotlight on "60,000" honest.
    """
    merged = []
    for w in out:
        if merged and glues_back(w["text"], w.get("apo", "")):
            p = merged[-1]
            p["text"] += w["text"]
            p["raw"] = (p["raw"] + w["raw"]).strip()
            p["e"] = max(p["e"], w["e"])
            p["prob"] = min(p["prob"], w["prob"])
            continue
        merged.append(w)
    # strip_trailing is a per-token setting, so re-apply it to the word the
    # merge actually produced rather than to the halves it was made of.
    if strip:
        for w in merged:
            while w["text"] and w["text"][-1] in strip:
                w["text"] = w["text"][:-1]
        merged = [w for w in merged if w["text"]]
    return merged


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
        if tcfg.get("capitalize_i"):
            t = _cap_i(t, apo)
        if tcfg.get("uppercase"):
            t = t.upper()
        if not t:
            continue
        s_cs = int(round(w["start"] * 100))
        e_cs = int(round(w["end"] * 100))
        if e_cs <= s_cs:
            e_cs = s_cs + 1
        out.append(
            dict(
                text=t,
                raw=w["text"].strip(),
                s=s_cs,
                e=e_cs,
                prob=w.get("probability", 1.0),
                apo=apo,
            )
        )
    out = glue_suffixes(out, tcfg.get("strip_trailing", ""))
    # Words must not overlap, and the reason is not tidiness. A word whose end
    # equals its start gets the synthetic centisecond above -- and if the NEXT
    # word starts at that same instant, that centisecond is stolen from it: the
    # groups either side then overlap by exactly 1cs and selfcheck refuses the
    # whole file. Whisper emits such a word wherever it clips one at a segment
    # boundary; a dense 19-minute Ukrainian podcast produced one ("БІЛЬШЕ." at
    # 988.98 s, zero length, with the next word starting there too) and no
    # setting of min_active_ms or max_words could fix it, because neither was
    # the cause.
    #
    # Ordering by the previous END rather than the previous START is what makes
    # this a no-op on a well-formed transcript and a repair on a degenerate one.
    for i in range(1, len(out)):
        out[i]["s"] = max(out[i]["s"], out[i - 1]["e"])
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
    # grouping.wrap is a CHANNEL property, measured off their own graphics:
    # "allow" wraps freely (default -- existing presets byte-identical),
    # "no_orphan" wraps but never strands a single word on the last line
    # (layout() rebalances), and "none" -- a single-line-strap style like
    # Bloomberg's banner -- never wraps at all: grouping itself refuses any
    # group needing a second line, so long words simply carry fewer per card.
    # This replaces hand-sweeping max_words per clip, which is the
    # "hand-chosen number validated after the encode" failure docs/todo.md
    # diagnoses. max_words stays the cap; the words decide the rest.
    if g.get("wrap", "allow") == "none":
        max_lines = 1

    groups, cur = [], []
    for w in words:
        trial = cur + [w]
        too_wide = wrap_lines([x["text"] for x in trial], m, max_line, max_lines) is None
        if cur and (
            too_wide
            or len(trial) > maxw
            or w["s"] - cur[-1]["e"] > gap_cs
            or w["e"] - cur[0]["s"] > maxdur
        ):
            groups.append(cur)
            cur = [w]
        else:
            cur = trial
        if cur and g["break_on_sentence_end"] and cur[-1]["raw"].endswith(tuple(SENT_END)):
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
    # "no_orphan": greedy wrapping stuffs the first line and can strand a
    # single word on the last -- "the models are going / to", the shipped
    # Lenny defect. Classic widow fixing: pull one word down whenever the
    # rebalanced last line still fits. The group is untouched, so timing,
    # count and reading order are exactly what "allow" would give.
    if cfg["grouping"].get("wrap") == "no_orphan":
        while len(lines) >= 2 and len(lines[-1]) == 1 and len(lines[-2]) >= 2:
            cand = [lines[-2][-1]] + lines[-1]
            w = sum(m.width(texts[j]) for j in cand) + sp * (len(cand) - 1)
            if w > L["max_line_width_px"]:
                break
            lines[-1] = cand
            lines[-2] = lines[-2][:-1]
    lh = L["line_height_px"]
    n = len(lines)

    ink_h = (n - 1) * lh + m.cap_px
    pad_y, pad_x = cfg["card"]["pad_y_px"], cfg["card"]["pad_x_px"]
    card_h = ink_h + 2 * pad_y
    if bottom_margin is None:
        bottom_margin = L["bottom_margin_px"]
    card_bottom = cfg["canvas"]["play_res_y"] - bottom_margin - rule_below(cfg)
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
    g0 = max(0, g0)  # ASS has no negative timestamps
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
    # min_act can push the last word past the g1 clamp; g1 is re-raised to
    # match, DELIBERATELY creating a group overlap for selfcheck to catch.
    # Trimming here would silently drop a word's highlight instead -- the
    # downstream check keeps the failure visible and the fix (min_active_ms
    # vs max_words, a tuned pair) in the user's hands.
    g1 = max(g1, bounds[-1][1])
    return g0, g1, bounds


# ---------------------------------------------------------------- emit
def rounded_rect(w, h, r):
    r = max(0.0, min(r, min(w, h) / 2.0))

    def f(v):
        return ("%.1f" % v).rstrip("0").rstrip(".")

    return (
        "m %s 0 l %s 0 b %s 0 %s 0 %s %s "
        "l %s %s b %s %s %s %s %s %s "
        "l %s %s b 0 %s 0 %s 0 %s "
        "l 0 %s b 0 0 0 0 %s 0"
    ) % (
        f(r),
        f(w - r),
        f(w),
        f(w),
        f(w),
        f(r),
        f(w),
        f(h - r),
        f(w),
        f(h),
        f(w),
        f(h),
        f(w - r),
        f(h),
        f(r),
        f(h),
        f(h),
        f(h),
        f(h - r),
        f(r),
        f(r),
    )


def rule_below(cfg):
    """Height the card's rule adds BELOW the card -- 0 unless one is configured.

    `card.rule` draws a solid strip the full width of the card, which is how a
    broadcast lower third reads as itself: Bloomberg Tech's banner is a white
    slab with a 14 px mint strip under it, and without the strip the same white
    slab is just a white slab.

    `layout.bottom_margin_px` stays the distance from the frame bottom to the
    bottom of the WHOLE graphic, rule included -- otherwise adding a rule would
    silently push every caption up by its thickness, and a preset's margin would
    no longer mean what it says. A top rule sits above the card and so costs
    nothing here.
    """
    K = cfg.get("card") or {}
    if not K.get("enabled", True):
        return 0.0
    R = K.get("rule") or {}
    if R.get("side", "bottom") != "bottom":
        return 0.0
    return float(R.get("px", 0) or 0)


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
    if rise + settle > dur_ms:  # never overrun the event
        total = max(1.0, float(rise + settle))
        rise = int(rise * dur_ms / total)
        settle = int(settle * dur_ms / total)
    return "%sfscx100%sfscy100%st(0,%d,%sfscx%s%sfscy%s)%st(%d,%d,%sfscx100%sfscy100)" % (
        BS,
        BS,
        BS,
        rise,
        BS,
        _num(scale),
        BS,
        _num(scale),
        BS,
        rise,
        rise + settle,
        BS,
        BS,
    )


def build(words, cfg, m, overlays=None):
    C, S, T = cfg["canvas"], cfg["states"], cfg["timing"]
    base_c = ass_colour(S["base"]["colour"])
    act_c = ass_colour(S["active"]["colour"])
    card_c = ass_colour(cfg["card"]["colour"], cfg["card"].get("alpha", 0))
    RU = cfg["card"].get("rule") or {}
    rule_px = float(RU.get("px", 0) or 0)
    rule_side = RU.get("side", "bottom")
    rule_c = ass_colour(
        RU.get("colour", cfg["card"]["colour"]), RU.get("alpha", cfg["card"].get("alpha", 0))
    )
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
    ) % (
        C["play_res_x"],
        C["play_res_y"],
        fam,
        fsz,
        base_c,
        base_c,
        out_c,
        sha_c,
        bold,
        fsp,
        out_w,
        sha_w,
        fam,
        fsz,
        act_c,
        act_c,
        out_c,
        sha_c,
        bold,
        fsp,
        out_w,
        sha_w,
        fam,
        fsz,
        card_c,
        card_c,
        card_c,
    )

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
            % (fam, fsz, spoken_c, spoken_c, out_c, sha_c, bold, fsp, out_w, sha_w),
        )

    groups = group_words(words, cfg, m)
    ev, dbg = [], []
    for gi, grp in enumerate(groups):
        prev_end = dbg[-1]["g1"] if dbg else None
        nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else None
        g0, g1, bounds = state_windows(grp, cfg, prev_end, nxt)
        bm = lift_for_overlays(g0, g1, cfg, m, overlays)
        placed, (cx0, cy0, cw, ch) = layout(grp, cfg, m, bottom_margin=bm)

        if cfg["card"].get("enabled", True):
            ev.append(
                "Dialogue: 0,%s,%s,Card,,0,0,0,,{%san7%spos(%.1f,%.1f)%sbord0%sshad0%sfad(%d,%d)%s1c%s%sp1}%s{%sp0}"
                % (
                    fmt_cs(g0),
                    fmt_cs(g1),
                    BS,
                    BS,
                    cx0,
                    cy0,
                    BS,
                    BS,
                    BS,
                    fade,
                    fade,
                    BS,
                    card_c,
                    BS,
                    rounded_rect(cw, ch, cfg["card"]["corner_radius_px"]),
                    BS,
                )
            )
            if rule_px > 0:
                ry = cy0 + ch if rule_side == "bottom" else cy0 - rule_px
                ev.append(
                    "Dialogue: 0,%s,%s,Card,,0,0,0,,{%san7%spos(%.1f,%.1f)%sbord0%sshad0%sfad(%d,%d)%s1c%s%sp1}%s{%sp0}"
                    % (
                        fmt_cs(g0),
                        fmt_cs(g1),
                        BS,
                        BS,
                        cx0,
                        ry,
                        BS,
                        BS,
                        BS,
                        fade,
                        fade,
                        BS,
                        rule_c,
                        BS,
                        rounded_rect(cw, rule_px, 0),
                        BS,
                    )
                )

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
                ev.append(
                    "Dialogue: 1,%s,%s,Base,,0,0,0,,{%s%s}%s"
                    % (fmt_cs(g0), fmt_cs(a), pos, fd(g0, a), w["text"])
                )
            ev.append(
                "Dialogue: 1,%s,%s,Act,,0,0,0,,{%s%s%s}%s"
                % (
                    fmt_cs(a),
                    fmt_cs(b),
                    pos,
                    fd(a, b),
                    pop_tags(P, (b - a) * 10) if pop_on else "",
                    w["text"],
                )
            )
            if b < g1:
                ev.append(
                    "Dialogue: 1,%s,%s,%s,,0,0,0,,{%s%s}%s"
                    % (fmt_cs(b), fmt_cs(g1), spoken_style, pos, fd(b, g1), w["text"])
                )

        dbg.append(
            dict(
                gi=gi,
                g0=g0,
                g1=g1,
                card=[cx0, cy0, cw, ch],
                lifted=bm,
                rule=[rule_px, rule_side],
                words=[
                    dict(
                        t=grp[k]["text"],
                        cx=placed[k]["cx"],
                        cy=placed[k]["cy"],
                        w=m.width(grp[k]["text"]),
                        a=bounds[k][0],
                        b=bounds[k][1],
                    )
                    for k in range(len(grp))
                ],
            )
        )
    return header, ev, dbg, groups


def wrap_stats(dbg):
    """(cards that wrapped to >1 line, cards that orphaned a single word).

    Grouping failure is TYPOGRAPHIC: a group one word too wide for its line
    wraps, and the wrap strands that word alone on the second line -- "the
    models are going / to". selfcheck() cannot see it (nothing is mistimed,
    off-canvas or overlapping), so these two numbers exist to be swept against
    grouping.max_words x layout.max_line_width_px before an encode. Both
    channel presets in config/ originally shipped on the worst cell of their
    own sweep. A two-word card on two lines is not counted as an orphan: with
    one word per line there is no "own line" for either to be stranded on.
    """
    wrapped = orphan = 0
    for d in dbg:
        rows = {}
        for w in d["words"]:
            rows.setdefault(round(w["cy"]), []).append(w)
        if len(rows) > 1:
            wrapped += 1
            if len(d["words"]) > 2 and min(len(r) for r in rows.values()) == 1:
                orphan += 1
    return wrapped, orphan


def sweep_grouping(words, cfg, m):
    """Price grouping without an encode: max_words x line-width, on the words
    that will actually render. Both shipped presets sat on the worst cell of
    their own sweep until somebody ran one; this makes running one a flag.

    The width axis is swept around the style's post-scale value, so on a
    vertical canvas the whole column usually comes out identical -- that is
    the scale_style clamp (0.94*W minus the card pads) binding, and it is the
    table telling you width is a dead knob here: carry fewer words instead.
    """
    base_w = cfg["layout"]["max_line_width_px"]
    base_mw = cfg["grouping"]["max_words"]
    policy = cfg["grouping"].get("wrap", "allow")
    print(
        "%d words | wrap policy %r | style width %.0f px (post-scale)"
        % (len(words), policy, base_w)
    )
    print(
        "%6s %9s | %5s %7s %7s | %s"
        % ("words", "width", "cards", "wrapped", "orphans", "widest card")
    )
    for mw in (2, 3, 4, 5):
        for frac in (0.8, 1.0, 1.2):
            trial = json.loads(json.dumps(cfg))
            trial["grouping"]["max_words"] = mw
            trial["layout"]["max_line_width_px"] = base_w * frac
            groups = group_words(words, trial, m)
            dbg, widest = [], 0.0
            for grp in groups:
                placed, card = layout(grp, trial, m)
                dbg.append({"words": [{"cy": p["cy"]} for p in placed]})
                widest = max(widest, card[2])
            wr, orp = wrap_stats(dbg)
            mark = "  <-- style" if (mw == base_mw and frac == 1.0) else ""
            print(
                "%6d %9.0f | %5d %7d %7d | %6.0f%s"
                % (mw, base_w * frac, len(groups), wr, orp, widest, mark)
            )


def selfcheck(dbg, cfg):
    """Structural assertions. Proves the timing arithmetic is sound; says nothing
    about whether the timings match the audio (that is the frame probe's job).
    """
    errs = []
    px = cfg["canvas"]["play_res_x"]
    py = cfg["canvas"]["play_res_y"]
    for d in dbg:
        if d["g1"] <= d["g0"]:
            errs.append("group %d: non-positive duration" % d["gi"])
        for w in d["words"]:
            if w["b"] <= w["a"]:
                errs.append("group %d word %s: non-positive active window" % (d["gi"], w["t"]))
            # (no intra-group overlap check: state_windows() already forces
            # each start past the previous end, so it could never fire)
            if w["cx"] - w["w"] / 2 < 0 or w["cx"] + w["w"] / 2 > px:
                errs.append("group %d word %s: off-canvas" % (d["gi"], w["t"]))
        cx0, cy0, cw, ch = d["card"]
        if cx0 < 0 or cx0 + cw > px:
            errs.append("group %d: card off-canvas (x=%.0f w=%.0f)" % (d["gi"], cx0, cw))
        # A rule is drawn OUTSIDE the card box, so the card fitting the frame is
        # no longer proof that the graphic does. A rule half off the bottom edge
        # would render as a thinner rule and look like a styling choice.
        rpx, rside = d.get("rule") or [0, "bottom"]
        top = cy0 - (rpx if rside == "top" else 0)
        bot = cy0 + ch + (rpx if rside == "bottom" else 0)
        if top < 0 or bot > py:
            errs.append(
                "group %d: card+rule off-canvas vertically "
                "(top=%.0f bottom=%.0f, frame %d) -- lower "
                "layout.bottom_margin_px or the rule" % (d["gi"], top, bot, py)
            )
    for i in range(1, len(dbg)):
        if dbg[i]["g0"] < dbg[i - 1]["g1"]:
            errs.append(
                "group %d starts at %dcs, before group %d ends at %dcs "
                "(%dcs overlap) -- raise timing.min_active_ms or lower "
                "grouping.max_words; they are a tuned pair"
                % (i, dbg[i]["g0"], i - 1, dbg[i - 1]["g1"], dbg[i - 1]["g1"] - dbg[i]["g0"])
            )
    return errs


def scale_style(cfg, W, H):
    """Adapt a preset authored for one canvas (typically 1920x1080) to the actual
    video dimensions. Scales every pixel-denominated knob by the height ratio and
    re-centres the anchor. Exactly a no-op when dimensions already match, so the
    common case stays byte-identical to the hand-verified output.
    """
    C = cfg["canvas"]
    if (C["play_res_x"], C["play_res_y"]) == (W, H):
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
    L["max_line_width_px"] = min(L["max_line_width_px"] * f, 0.94 * W - 2 * _pad_x)
    K = cfg["card"]
    for k in ("corner_radius_px", "pad_x_px", "pad_y_px", "collision_gap_px"):
        if k in K:
            K[k] = K[k] * f
    if K.get("rule") and K["rule"].get("px"):
        K["rule"]["px"] = K["rule"]["px"] * f
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
    ap.add_argument("--out", default=None, help="output .ass (required unless --sweep)")
    ap.add_argument(
        "--sweep",
        action="store_true",
        help="price grouping instead of building: the max_words x "
        "line-width table of cards/wraps/orphans for these "
        "words under this style. Free -- writes nothing. A "
        "flat width column means the scale_style clamp is "
        "binding and width is a dead knob; carry fewer words.",
    )
    ap.add_argument("--debug-out", default=None)
    ap.add_argument(
        "--overlays",
        default=None,
        help="detect-overlays.py json; lifts cards clear of the "
        "source video's own lower-third graphics",
    )
    ap.add_argument("--range", nargs=2, type=float, default=None, metavar=("T0", "T1"))
    ap.add_argument("--time-offset", type=float, default=0.0)
    ap.add_argument(
        "--scale-to",
        nargs=2,
        type=int,
        default=None,
        metavar=("W", "H"),
        help="actual video dimensions; pixel-tuned style values are "
        "scaled from the preset's canvas to these. A PlayRes that "
        "mismatches the video makes libass silently rescale "
        "everything -- this makes the adjustment explicit instead.",
    )
    args = ap.parse_args()
    if not args.out and not args.sweep:
        ap.error("--out is required (or use --sweep to price grouping)")

    cfg = json.load(open(args.style, encoding="utf-8"))
    if args.scale_to:
        scale_style(cfg, *args.scale_to)

    F = cfg["font"]
    m = Metrics(
        F["file"],
        F.get("size"),
        F.get("spacing", 0),
        F.get("fudge", 1.0),
        cap_height_px=F.get("cap_height_px"),
    )
    if not F.get("size"):
        print(
            "font size %d derived from cap_height_px=%s (%s: cap %d, winAsc+winDesc %d)"
            % (m.size, F.get("cap_height_px"), m.family, m.cap, m.den)
        )
    if m.family != cfg["font"]["family"]:
        print(
            "WARNING: ASS Fontname '%s' != file family '%s' -- libass may substitute"
            % (cfg["font"]["family"], m.family)
        )

    # the shared loader takes the faster-whisper envelope OR a bare list, so
    # a hand-built transcript is no longer a TypeError three calls deep
    words = sanitize(_outline.load_words(args.words), cfg)
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

    if args.sweep:
        sweep_grouping(words, cfg, m)
        return

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
        sys.exit("SELFCHECK: %d problem(s) -- refusing to write %s" % (len(errs), args.out))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write(header + "\n".join(ev) + "\n")
    if args.debug_out:
        with open(args.debug_out, "w", encoding="utf-8") as f:
            json.dump(dbg, f, ensure_ascii=False)

    sizes = [len(g) for g in groups]
    print(
        "words %d | groups %d | events %d | %.2f MB"
        % (len(words), len(groups), len(ev), os.path.getsize(args.out) / 1e6)
    )
    print("words/group avg %.1f max %d" % (sum(sizes) / max(1, len(sizes)), max(sizes)))
    # Grouping is a tuned pair (max_words vs max_line_width_px) and the way it
    # goes wrong is TYPOGRAPHIC, not structural, so selfcheck cannot see it: a
    # group one word too wide for its line wraps, and the wrap orphans that word
    # onto a line of its own. "the models are going / to" passed every check
    # this repo had and still read as broken. These two numbers price a
    # grouping change without spending an encode -- sweep them, do not guess.
    wrapped, orphan = wrap_stats(dbg)
    print(
        "cards wrapping to >1 line %d/%d (%.0f%%) | of those, %d orphan a "
        "single word onto its own line"
        % (wrapped, len(dbg), 100.0 * wrapped / max(1, len(dbg)), orphan)
    )
    print("first card %.2fs, last ends %.2fs" % (dbg[0]["g0"] / 100.0, dbg[-1]["g1"] / 100.0))
    if overlays is not None:
        base_m = cfg["layout"]["bottom_margin_px"]
        lift = [d for d in dbg if d["lifted"] != base_m]
        print(
            "cards lifted clear of source graphics: %d of %d (%d overlay ranges)"
            % (len(lift), len(dbg), len(overlays))
        )
        if lift:
            print("  lift margins used: %s" % sorted(set(d["lifted"] for d in lift)))


if __name__ == "__main__":
    main()
