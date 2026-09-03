#!/usr/bin/env python
"""Self-test for the shorts render path: the arithmetic a bad render would
otherwise have to find for you. No GPU, no encode, no network; runs in seconds.

Why it exists: the 2026-09-03 session shipped a caption card across two
speakers' mouths, and BOTH bugs in the guard built to catch it were guard rot
that only the next incident would have found -- a detector confidence floor of
0.7 that silently skipped the worst frame (it scored 0.67, because a face with
a card on it is an occluded face), and a checker that rebuilt caption geometry
from the bare preset while the render used a per-clip override, reporting
+319 px of clearance for a card position that was not on the video. A guard
nothing exercises decays into a guard that passes for the wrong reason, which
is worse than no guard. `check-dub.py`, `check-multicam.py` and
`check-screen.py` are the same idea for their pipelines; shorts had nothing.

What it covers, each against values frozen from real footage and real
incidents rather than invented ones (the `check-screen.py` convention):

  * crop window arithmetic -- the zoom/y pairs measured off Bloomberg Tech's
    own graphics, including the default crop that sliced their banner
  * resolve() -- pads meet speech halfway instead of eating a neighbouring word
  * the hook gate -- pass at 0.1 s, refuse at 6.9 s, refuse when undeclared
  * grouping typography -- the real 57-word span that produced
    "the models are going / to", swept bad vs good settings end to end
    through real font metrics
  * caption-space geometry -- gap sign on both sides of the face, the mouth
    BAND (the shipped 10 px near-miss must count), overlap fractions, and the
    floor relation (checker BELOW the detector's, the fail-open bug)
  * clip_style() -- per-clip layout overrides patch a copy, never the preset,
    and non-layout keys are refused by omission
  * capitalize_i -- the English pronoun, wherever whisper's casing wandered

The word fixture is one contiguous span of the Lenny's Podcast transcript
(1643.1-1656.7 s of zMvBMfj4cSQ): it contains the orphan-producing phrase, a
sentence boundary, a zero-gap word join and a lowercase "i'm" in fourteen
seconds, which is why it is THE fixture and not a synthetic list.

Invoke as:  python scripts/check-shorts.py
"""
import sys, os, json, shutil, argparse, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
from importlib import import_module

_cut = import_module("cut-clips")
_bca = import_module("build-captions-ass")
_cs = import_module("check-caption-space")
_sd = import_module("shot-detect")

FAILS = []


def check(name, got, want):
    if got == want:
        print("  OK   %s" % name)
    else:
        print("  FAIL %s\n       got  %r\n       want %r" % (name, got, want))
        FAILS.append(name)


def check_true(name, got):
    check(name, bool(got), True)


# One contiguous real span; see the module docstring for why this one.
WORDS = [dict(text=t, start=s, end=e) for t, s, e in [
    ("are", 1643.12, 1643.66), ("we", 1643.66, 1643.82),
    ("building", 1643.82, 1644.04), ("for", 1644.04, 1644.30),
    ("where", 1644.30, 1644.44), ("the", 1644.44, 1644.58),
    ("models", 1644.58, 1644.86), ("are", 1644.86, 1645.02),
    ("going", 1645.02, 1645.16), ("to", 1645.16, 1645.30),
    ("be", 1645.30, 1645.50), ("in", 1645.50, 1645.82),
    ("two", 1645.82, 1645.98), ("to", 1645.98, 1646.08),
    ("three", 1646.08, 1646.22), ("months?", 1646.22, 1646.50),
    ("You", 1646.74, 1647.26), ("fail", 1647.40, 1647.74),
    ("if", 1647.74, 1648.02), ("you", 1648.02, 1648.16),
    ("build", 1648.16, 1648.42), ("for", 1648.42, 1648.72),
    ("where", 1648.72, 1649.28), ("the", 1649.28, 1649.40),
    ("models", 1649.40, 1649.58), ("are", 1649.58, 1649.70),
    ("are", 1649.70, 1649.74), ("now", 1649.74, 1649.94),
    ("you", 1649.94, 1650.22), ("fail", 1650.22, 1650.62),
    ("if", 1650.62, 1650.82), ("you", 1650.82, 1650.94),
    ("build", 1650.94, 1651.14), ("for", 1651.14, 1651.32),
    ("where", 1651.32, 1651.62), ("you", 1651.62, 1651.84),
    ("think", 1651.84, 1652.14), ("the", 1652.14, 1652.32),
    ("models", 1652.32, 1652.54), ("will", 1652.54, 1652.64),
    ("be", 1652.64, 1652.80), ("in", 1652.80, 1652.94),
    ("a", 1652.94, 1653.04), ("year", 1653.04, 1653.34),
    ("like", 1653.34, 1653.72), ("both", 1653.72, 1654.02),
    ("outcomes", 1654.02, 1654.40), ("are", 1654.40, 1654.62),
    ("equally", 1654.62, 1654.78), ("wrong", 1654.78, 1655.16),
    ("and", 1655.16, 1655.40), ("i'm", 1655.40, 1655.50),
    ("sure", 1655.50, 1655.56), ("many", 1655.56, 1655.76),
    ("people", 1655.76, 1656.22), ("have", 1656.22, 1656.42),
    ("talked", 1656.42, 1656.74),
]]


def crop_window_arithmetic():
    print("== crop window arithmetic ==")
    # Measured off Bloomberg Tech's own frames: name card's mint edge at
    # source y=697, banner white at y=920. A window that keeps their graphics
    # out must END above those rows, and these zoom/y pairs are the ones the
    # real manifests carry.
    check("boxed shot: zoom 1.556 y 347 -> window y 0..694, under the card",
          _cut.crop_box({"crop_zoom": 1.556, "crop_y": 347},
                        1920, 1080, 1080, 1920), (390, 694, 764, 0))
    check("full-frame shot: zoom 1.179 y 458 -> window y 0..916, under the banner",
          _cut.crop_box({"crop_zoom": 1.179, "crop_y": 458},
                        1920, 1080, 1080, 1920), (514, 916, 702, 0))
    # The default crop keeps the full source height -- which is exactly the
    # render that shipped with 'ED TALKS FOR HUGGING' sliced across the bottom.
    cw, ch, cx, cy = _cut.crop_box({}, 1920, 1080, 1080, 1920)
    check("default crop keeps full height (slices a source banner)", ch, 1080)
    # crop_x clamps to the frame instead of panning past its edge
    cw, ch, cx, cy = _cut.crop_box({"crop_x": 5000}, 1920, 1080, 1080, 1920)
    check("crop_x past the right edge clamps", cx, 1920 - cw)


def resolve_pads():
    print("== resolve(): pads meet speech halfway ==")
    # Head: 'You' at 1646.74 with 'months?' ending 1646.50 -- a 0.24 s gap.
    # A 0.15 s pad reaches 1646.59, but the rule is never closer to the
    # previous word than halfway across the gap: (1646.50+1646.74)/2.
    clip = {"start_text": "You fail if you build", "end_text": "equally wrong"}
    s, e = _cut.resolve(clip, WORDS, 0.15, 0.35)
    check("head pad stops at the midpoint of a 0.24s gap", round(s, 2), 1646.62)
    # Tail: 'wrong' ends 1655.16 and 'and' starts there -- zero gap, so the
    # whole 0.35 s pad is surrendered.
    check("tail pad surrenders entirely at a zero gap", round(e, 2), 1655.16)
    # No neighbour at all -> the full pad is granted.
    clip2 = {"start_text": "are we building", "end_text": "two to three months"}
    s2, e2 = _cut.resolve(clip2, WORDS, 0.15, 0.35)
    check("head pad granted in full with no previous word", round(s2, 2), 1642.97)
    check("tail pad also midpointed against the next sentence", round(e2, 2), 1646.62)


def hook_gate():
    print("== hook gate ==")
    errs, warns = _cut.hook_gate(
        {"id": "x", "hook": "are we building for where the models"},
        WORDS, 1643.0)
    check("hook 0.1s in passes", (errs, warns), ([], []))
    errs, _ = _cut.hook_gate(
        {"id": "x", "hook": "you fail if you build for where you think"},
        WORDS, 1643.0)
    check_true("hook 6.9s in is refused", errs
               and "past the 3.0s limit" in errs[0])
    errs, _ = _cut.hook_gate({"id": "x"}, WORDS, 1643.0)
    check_true("undeclared hook is refused", errs
               and "no `hook` declared" in errs[0])
    errs, _ = _cut.hook_gate(
        {"id": "x", "hook": "are we building"}, WORDS, 1650.0)
    check_true("hook before the clip start is refused", errs
               and "BEFORE the clip starts" in errs[0])


def _cfg(max_words, max_line_width_px):
    """A 1080x1920 caption config in the shape the builder consumes -- the
    Lenny preset's numbers already scaled to the vertical canvas, so no
    scale_style() pass intervenes between the knobs and the measurement."""
    return {
        "canvas": {"play_res_x": 1080, "play_res_y": 1920},
        "text": {"apostrophe": "’", "uppercase": False,
                 "strip_trailing": "", "capitalize_i": True,
                 "word_gap_ratio": 1.0},
        "card": {"pad_x_px": 28.4, "pad_y_px": 32.0},
        "layout": {"anchor_x": 540, "bottom_margin_px": 602,
                   "max_line_width_px": max_line_width_px, "max_lines": 2,
                   "line_height_px": 67.6},
        "grouping": {"max_words": max_words, "gap_break_s": 0.45,
                     "break_on_sentence_end": True,
                     "max_group_duration_s": 2.5},
    }


def grouping_typography():
    print("== grouping typography: the orphan sweep ==")
    m = _bca.Metrics(os.path.join(_env.ROOT, "fonts", "Montserrat-Bold.ttf"),
                     cap_height_px=44.44)

    def stats(cfg):
        words = _bca.sanitize(WORDS_ENVELOPE, cfg)
        groups = _bca.group_words(words, cfg, m)
        dbg = []
        for grp in groups:
            placed, _card = _bca.layout(grp, cfg, m)
            dbg.append({"words": [{"cy": p["cy"]} for p in placed]})
        return _bca.wrap_stats(dbg)

    # sanitize() consumes start/end in seconds, keyed like the transcript
    global WORDS_ENVELOPE
    WORDS_ENVELOPE = [dict(text=w["text"], start=w["start"], end=w["end"])
                      for w in WORDS]
    bad_w, bad_o = stats(_cfg(5, 711.0))     # 5 x 400 on the authoring canvas
    good_w, good_o = stats(_cfg(4, 835.5))   # 4 x 470 -- the swept winner
    check_true("shipped setting orphans at least one word "
               "('the models are going / to')", bad_o >= 1)
    check("swept setting orphans nothing", good_o, 0)
    check_true("swept setting also wraps fewer cards", good_w < bad_w)
    # wrap_stats itself: a two-word card on two lines is wrapped, not orphaned
    check("two-word two-line card is not an orphan",
          _bca.wrap_stats([{"words": [{"cy": 100}, {"cy": 168}]}]), (1, 0))
    check("four-word card stranding one word IS an orphan",
          _bca.wrap_stats([{"words": [{"cy": 100}, {"cy": 100},
                                      {"cy": 100}, {"cy": 168}]}]), (1, 1))


def caption_space_geometry():
    print("== caption-space geometry ==")
    # gap(): positive means apart, whichever side of the face the card is on.
    # The first metric only understood 'below' and reported every legitimate
    # above-the-head card as a near miss.
    check("card above the face box: +50", _cs.gap((0, 100, 100, 50),
                                                  (0, 200, 100, 100)), 50)
    check("card below the face box: +50", _cs.gap((0, 350, 100, 50),
                                                  (0, 200, 100, 100)), 50)
    check("card overlapping: -50", _cs.gap((0, 250, 100, 50),
                                           (0, 200, 100, 100)), -50)
    # mouth_covered(): a BAND, not the landmark. The shipped defect: landmark
    # y 1163, card top 1173 -- a 10 px 'miss' a viewer reads as the mouth
    # being gone. It must count.
    check_true("the shipped 10px near-miss counts as covered",
               _cs.mouth_covered((0, 1173, 1080, 120), (540, 1163), 651))
    check_true("a direct hit counts",
               _cs.mouth_covered((0, 1195, 1080, 120), (540, 1196), 400))
    check("a card genuinely below a small face does not",
          _cs.mouth_covered((0, 1195, 1080, 120), (540, 1137), 300), False)
    check("a card beside the mouth in x does not",
          _cs.mouth_covered((600, 1173, 400, 120), (300, 1163), 651), False)
    check("overlap_frac: card swallowing the box",
          _cs.overlap_frac((0, 0, 200, 200), (50, 50, 100, 100)), 1.0)
    check("overlap_frac: disjoint",
          _cs.overlap_frac((0, 0, 50, 50), (100, 100, 50, 50)), 0.0)
    # The fail-open bug: the checker's floor must sit BELOW the detector's,
    # because the frames it exists to judge are occluded faces the detector
    # doubts. The worst shipped frame scored 0.67 against a 0.7 floor.
    check_true("checker's face floor sits below shot-detect's",
               _cs.DET_SCORE < _sd.DEFAULT_FACE["score"])


def clip_style_override():
    print("== clip_style(): per-clip layout override ==")
    tmp = tempfile.mkdtemp(prefix="check-shorts-")
    try:
        style = "config/presets/lennys-podcast-vertical.json"
        # no override -> the committed preset itself, untouched
        check("no override returns the preset path",
              _cut.clip_style({"style": style}, {"id": "t"}, tmp), style)
        # a layout override -> a PATCHED COPY under tmp, preset untouched
        out = _cut.clip_style({"style": style, "bottom_margin_px": 190,
                               "colour": "#123456"}, {"id": "t"}, tmp)
        check_true("override returns a temp copy, not the preset", out != style)
        with open(os.path.join(_env.ROOT, out), encoding="utf-8") as f:
            cfg = json.load(f)
        check("margin override lands in the copy",
              cfg["layout"]["bottom_margin_px"], 190)
        check("non-layout keys are ignored -- colour stays the preset's",
              cfg["card"]["colour"], "#000000")
        with open(os.path.join(_env.ROOT, style), encoding="utf-8") as f:
            check("the committed preset is untouched",
                  json.load(f)["layout"]["bottom_margin_px"], 339)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sidecar_merge():
    print("== auto-reframe merge: hand edits survive a regen ==")
    _ar = import_module("auto-reframe")
    fresh = {"a": {"keys": [[0, 100]], "pad": []},
             "b": {"keys": [[0, 200]], "pad": [[1, 2]]}}
    # entry-level marker protects that entry only
    old = {"a": {"keys": [[0, 999]], "pad": [[0, 5]],
                 "_pad_why": "letterboxed by hand"},
           "b": {"keys": [[0, 1]], "pad": [[3, 4]]}}
    merged, refused, warns = _ar.merge_sidecar(old, fresh, force=False)
    check("marked entry kept", merged["a"]["keys"], [[0, 999]])
    check("unmarked entry regenerated", merged["b"]["keys"], [[0, 200]])
    check_true("refusal names the marker",
               len(refused) == 1 and "letterboxed by hand" in refused[0])
    check_true("unmarked pad change still warns",
               len(warns) == 1 and "overwriting pad" in warns[0])
    # file-level marker protects every existing entry
    old2 = {"_comment": "HAND-EDITED after review",
            "b": {"keys": [[0, 1]], "pad": []}}
    merged2, refused2, _ = _ar.merge_sidecar(old2, fresh, force=False)
    check("file marker keeps the existing entry", merged2["b"]["keys"], [[0, 1]])
    check("file marker still admits NEW clips", merged2["a"]["keys"], [[0, 100]])
    check_true("file-level refusal cites the file comment",
               refused2 and "HAND-EDITED after review" in refused2[0])
    # --force-regen overrides everything
    merged3, refused3, _ = _ar.merge_sidecar(old, fresh, force=True)
    check("force-regen overwrites the marked entry",
          (merged3["a"]["keys"], refused3), ([[0, 100]], []))


def capitalize_i():
    print("== capitalize_i ==")
    apo = "’"
    check("i%sm -> I%sm" % (apo, apo), _bca._cap_i("i%sm" % apo, apo),
          "I%sm" % apo)
    check("bare i -> I", _bca._cap_i("i", apo), "I")
    check("i with trailing comma", _bca._cap_i("i,", apo), "I,")
    check("'in' untouched", _bca._cap_i("in", apo), "in")
    check("'it%ss' untouched" % apo, _bca._cap_i("it%ss" % apo, apo),
          "it%ss" % apo)
    # end to end through sanitize(): the fixture's ASCII "i'm" (whisper's own
    # casing and quoting) comes out as I + typographic apostrophe
    cfg = _cfg(4, 835.5)
    out = _bca.sanitize([dict(text="i'm", start=1.0, end=1.2)], cfg)
    check("sanitize: whisper's i'm -> I%sm" % apo, out[0]["text"],
          "I%sm" % apo)


def main():
    argparse.ArgumentParser(
        description="Shorts render-path self-test -- no GPU, no encode, "
                    "seconds. Runs every section; exit 1 lists the failures."
    ).parse_args()
    for fn in (crop_window_arithmetic, resolve_pads, hook_gate,
               grouping_typography, caption_space_geometry,
               clip_style_override, sidecar_merge, capitalize_i):
        fn()
        print()
    if FAILS:
        print("FAILED %d: %s" % (len(FAILS), ", ".join(FAILS)))
        sys.exit(1)
    print("shorts self-test OK")


if __name__ == "__main__":
    main()
