#!/usr/bin/env python
"""Does this short open on a settled face, or mid-word with the mouth half open?

The first frame is the first thing a viewer sees, and a clip that opens
mid-syllable -- mouth open, eyes down, hand frozen mid-gesture -- reads as a
botched cut. Nothing already in the pipeline catches it: caption-sync probes and
the duration assert both pass happily on such a clip, because nothing about it
is out of sync or the wrong length. It is simply ugly.

One hard check, two numbers and a picture, none of which cost an encode:

  * **a boundary inside a word** is flagged unconditionally -- no `open_ok`
    excuses it. A cut 0.06 s into a word shipped from here before this check
    existed: the picture looked fine and only the render's caption card, which
    opened on a word from the previous sentence, gave it away. (The epsilon is
    1 ms, which also keeps the deliberate stop-1-ms-early pattern -- used when
    two transcript words share an exact timestamp -- from being flagged.)

  * **lead-in silence, measured twice** -- once off the transcript, and once off
    the WAVEFORM, because the transcript is not evidence of silence.
    faster-whisper truncates word *ends*, so a "gap" between one word's end and
    the next word's start routinely contains speech. This shipped a bad opening
    once: the transcript reported a 0.48 s gap before a hook word while the
    audio ran at -12 dB RMS straight through it, and the clip opened mid-phrase
    with the lead-in reading a comfortable "ok". A transcript gap the audio
    disagrees with is now its own FLAG -- it is more dangerous than a short one,
    because it looks fine. Word *starts* line up with the audio well; it is the
    ends that drift. Note `cut-clips.resolve()` pads meet
    speech halfway, so a 0.24 s transcript gap yields only ~0.12 s of lead-in.
  * **tail-out silence** -- the same at the end.
  * **a contact sheet** of every frame inside the nearby pauses, so the start
    can be chosen by picture when the numbers cannot decide it.

That last one is not a fallback, it is the point. Some speakers never pause: on
the film this was written for, the largest gap in the 37 s around one clip was
0.28 s, so *no* boundary was clean on silence alone and every candidate had to
be looked at. A mouth also stays open across a short gap, so silence is not
evidence the picture is settled.

**A mouth-openness detector was tried here and rejected.** YuNet gives 5
landmarks -- eyes, nose, two mouth corners -- but no lip contour, so openness
has to be inferred from how dark the mouth region is. Measured against eight
frames already judged by eye, the score separated them cleanly and *backwards*:
the closed-mouth frames read darker (0.33-0.47) than the open ones (0.11-0.18),
because the speaker was looking down in the open ones and the score was reading
head pose and shadow, not lips. A number that sorts eight frames for the wrong
reason will not survive the next video, so this ships without an automatic
verdict on the picture. Fixing it needs a lip-contour model and a labelled set
across several films; until then the sheet is the honest tool.

A clip whose lead-in is short but whose frame you have looked at and accepted
carries `"open_ok": "<why>"` in the manifest, and stops being flagged. That is
the same bargain `checked_utc` strikes with the project doctor: the check keeps
its teeth, and a reviewed exception is recorded next to the thing it excuses
rather than remembered by whoever ran it.

Invoke as:  python scripts/check-openings.py --manifest projects/<id>/clips.json
            python scripts/check-openings.py --manifest ... --sheet
"""
import sys, os, json, argparse, importlib, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

_cut = importlib.import_module("cut-clips")      # hyphen: see CLAUDE.md
_outline = importlib.import_module("transcript-outline")

# Below this much silence before the cut, the clip is very likely to open on the
# tail of the previous word. Not a hard rule -- it is a prompt to go and look.
LEAD_MIN = 0.20
TAIL_MIN = 0.25
# How wide to hunt for a better boundary when one is flagged.
HUNT = 6.0
GAP_MIN = 0.15


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def words_of(m, manifest_path):
    wp = _env.resolve(m["words"])
    d = load(wp)
    return d["words"] if isinstance(d, dict) else d


def inside_word(words, t):
    """The word this time falls strictly inside, or None.

    A boundary in here is always wrong -- the audio opens or closes
    mid-syllable and the caption card carries a word the viewer never properly
    hears. It is also purely mechanical to detect, which is how a cut 0.06 s
    into a word shipped here before this check existed: the picture looked
    fine, and only the render's caption gave it away.
    """
    for w in words:
        if w["start"] + 1e-3 < t < w["end"] - 1e-3:
            return w
    return None


def audio_rms(src, t0, t1, hop=0.02, sr=16000):
    """20 ms RMS envelope of [t0,t1) in dBFS, straight off the decoder.

    Decoded to raw PCM rather than measured with volumedetect, because seeking
    a compressed source and asking for a fraction of a second gives back decoder
    priming garbage -- it reported -1.2 dB peaks inside a pause that is really
    at -40 dB.
    """
    import numpy as np
    t0 = max(0.0, t0)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "%.3f" % t0, "-i", src,
         "-t", "%.3f" % (t1 - t0), "-ac", "1", "-ar", str(sr),
         "-f", "s16le", "-"],
        capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    n = int(hop * sr)
    if len(a) < n:
        return np.array([]), np.array([])
    k = len(a) // n
    frames = a[:k * n].reshape(k, n)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return t0 + np.arange(k) * hop, 20.0 * np.log10(np.maximum(rms, 1e-6))


def audio_lead_in(src, cut, ref_a, ref_b, span=2.5):
    """Measure the opening against the WAVEFORM. Returns (in_silence, post, thr).

    THE TRANSCRIPT IS NOT EVIDENCE OF SILENCE. faster-whisper truncates word
    ENDS, so the gap between one word's end and the next word's start routinely
    contains speech. Measured here: it claimed 'є.' ended at 1003.44 and so
    reported a 0.48 s gap before the hook, while the waveform ran at -12 dB
    through the whole of it -- a cut placed by that number opens mid-phrase.
    Word STARTS line up with the audio well; it is the ends that drift.

    Two numbers, because they answer different questions. `in_silence` is
    whether the cut instant is itself quiet -- that is the one that decides
    "does this open mid-word". `post` is how long the quiet lasts after the cut
    before the first word arrives, which is what makes an opening feel unhurried
    rather than abrupt. A cut can sit only 0.02 s after the previous word yet
    still open beautifully, because half a second of air follows it.

    The threshold is relative to the clip's own speech, not absolute, so it
    survives a quiet talker and a loud one: silence is 25 dB under the 90th
    percentile of the clip's RMS, floored at -45 dB so a near-silent clip
    cannot make everything count as speech.
    """
    import numpy as np
    _, ref = audio_rms(src, ref_a, min(ref_b, ref_a + 60.0))
    if ref.size == 0:
        return None, None, None
    thr = max(float(np.percentile(ref, 90)) - 25.0, -45.0)
    ts, db = audio_rms(src, cut, cut + span)
    if db.size == 0:
        return None, None, thr
    in_silence = bool(db[0] < thr)
    post = 0.0
    for v in db:
        if v < thr:
            post += 0.02
        else:
            break
    return in_silence, post, thr


def silence_before(words, t):
    prev = [w["end"] for w in words if w["end"] <= t + 1e-6]
    return (t - max(prev)) if prev else float("inf")


def silence_after(words, t):
    nxt = [w["start"] for w in words if w["start"] >= t - 1e-6]
    return (min(nxt) - t) if nxt else float("inf")


def gaps_near(words, t, span=HUNT, gap_min=GAP_MIN):
    """Every pause of at least gap_min within +/- span of t, biggest first."""
    out, prev = [], None
    for w in words:
        if t - span <= w["start"] <= t + span:
            if prev is not None:
                g = w["start"] - prev["end"]
                if g >= gap_min:
                    out.append((g, prev["end"], w["start"], w.get("text", "")))
            prev = w
    return sorted(out, reverse=True)


def sheet(src, times, dst, crop=None, cols=4, tile=190):
    """Contact-sheet the given source times. Returns dst or None."""
    import numpy as np
    from PIL import Image
    tmp = os.path.join(os.path.dirname(dst), "_sheet_tmp")
    os.makedirs(tmp, exist_ok=True)
    vf = "scale=%d:-1" % tile
    if crop:
        vf = "crop=%d:%d:%d:%d,%s" % (crop[2], crop[3], crop[0], crop[1], vf)
    ims = []
    for i, t in enumerate(times):
        p = os.path.join(tmp, "t%02d.png" % i)
        subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", src,
                        "-frames:v", "1", "-vf", vf, "-y", p],
                       check=False)
        if os.path.exists(p):
            ims.append(Image.open(p).convert("RGB"))
    if not ims:
        return None
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (w * min(cols, len(ims)), h * rows), "black")
    for i, im in enumerate(ims):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    out.save(dst)
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--only", default=None, help="one clip id, or a comma list")
    ap.add_argument("--sheet", action="store_true",
                    help="write contact sheets of the candidate start frames")
    ap.add_argument("--lead-min", type=float, default=LEAD_MIN)
    ap.add_argument("--fps", type=float, default=None,
                    help="source fps; probed when omitted")
    ap.add_argument("--no-audio", action="store_true",
                    help="skip the waveform lead-in measurement (transcript only)")
    args = ap.parse_args()

    mp = _env.resolve(args.manifest)
    m = load(mp)
    words = words_of(m, mp)
    src = _env.resolve(m["source"])
    pad = m.get("pad", {})
    ph, pt = float(pad.get("head", 0.0)), float(pad.get("tail", 0.0))
    tmpdir = _env.resolve(m.get("tmp") or os.path.join(os.path.dirname(mp), "temp"))
    os.makedirs(tmpdir, exist_ok=True)
    fps = args.fps or _cut.probe_fps(src) or 25.0
    only = set((args.only or "").split(",")) if args.only else None

    print("source %s  @ %.3f fps" % (os.path.basename(src), fps))
    print("lead-in threshold %.2fs\n" % args.lead_min)

    flagged = 0
    for clip in m["clips"]:
        if only and clip["id"] not in only:
            continue
        cp = clip.get("pad", {})
        start, end = _cut.resolve(clip, words,
                                  float(cp.get("head", ph)),
                                  float(cp.get("tail", pt)))
        lead = silence_before(words, start)
        tail = silence_after(words, end)
        # A short lead-in is a suspicion, not a defect: a speaker who never
        # pauses has no clean gap anywhere, and the frame can still be settled.
        # `open_ok` is how that review is recorded, so a clip judged by eye stops
        # crying wolf on every later run -- the same idea as `checked_utc` on a
        # deliverable the doctor calls STALE for a non-material edit.
        seen = clip.get("open_ok")
        bad = lead < args.lead_min and not seen
        flagged += bad
        print("%-26s %8.2f -> %8.2f  %5.1fs" % (clip["id"], start, end, end - start))
        # A boundary inside a word is a defect, full stop -- no open_ok excuses
        # it, because unlike a short lead-in there is no judgement call to make.
        w = inside_word(words, start)
        if w:
            flagged += 1
            print("   FLAG -- start %.2f is INSIDE the word %r (%.2f..%.2f): "
                  "the audio opens mid-syllable. Move it into the gap before "
                  "%.2f or after %.2f."
                  % (start, w.get("text", "?"), w["start"], w["end"],
                     w["start"], w["end"]))
        w = inside_word(words, end)
        if w:
            flagged += 1
            print("   FLAG -- end %.2f is INSIDE the word %r (%.2f..%.2f): "
                  "the last word is chopped."
                  % (end, w.get("text", "?"), w["start"], w["end"]))
        if lead < args.lead_min and seen:
            print("   lead-in  %6.2fs  short, but reviewed: %s"
                  % (lead, seen if isinstance(seen, str) else "accepted"))
        else:
            print("   lead-in  %6.2fs  %s" % (lead, "FLAG -- likely opens mid-word"
                                              if bad else "ok"))
        # ...and now the same question asked of the waveform, which is the only
        # one of the two that cannot be wrong. A transcript gap the audio does
        # not agree with is worse than a short one, because it reads as "ok".
        if not args.no_audio:
            in_sil, post, thr = audio_lead_in(src, start, start, end)
            if in_sil is None:
                print("   audio    ------  could not decode; skipping")
            elif in_sil:
                print("   audio    frame 0 is SILENT, %.2fs of air before the first word "
                      "(silence < %.0f dBFS)" % (post, thr))
            elif seen:
                print("   audio    frame 0 lands in SPEECH -- reviewed and accepted: %s"
                      % (seen if isinstance(seen, str) else "accepted"))
            else:
                flagged += 1
                print("   FLAG -- frame 0 lands in SPEECH (RMS above %.0f dBFS), so this "
                      "opens mid-phrase, whatever the transcript says: it claims %.2fs of "
                      "lead-in here. whisper truncates word ENDS, so a transcript gap can "
                      "be speech. Place the cut on the waveform's local minimum and check "
                      "the frame." % (thr, lead))
        # end_before_text cuts flush against the next phrase on purpose, so a
        # zero tail there is the feature, not a thin edge.
        if "end_before_text" in clip:
            print("   tail-out %6.2fs  by design (end_before_text)" % tail)
        else:
            print("   tail-out %6.2fs  %s" % (tail, "thin" if tail < TAIL_MIN else "ok"))

        near = gaps_near(words, start)
        if bad or args.sheet:
            if near:
                print("   pauses within +/-%.0fs of the start, biggest first:" % HUNT)
                for g, a, b, txt in near[:4]:
                    print("     %.2fs  silence %.2f..%.2f" % (g, a, b))
            else:
                print("   no pause >= %.2fs anywhere near -- this speaker does "
                      "not stop; choose the frame by picture" % GAP_MIN)

        if args.sheet:
            # every frame inside the two best nearby pauses, plus the current cut
            times = []
            for g, a, b, _t in near[:2]:
                n = max(1, int(g * fps))
                times += [a + (i + 0.5) * (g / n) for i in range(min(n, 8))]
            times.append(start)
            times = sorted(set(round(t, 3) for t in times))
            dst = os.path.join(tmpdir, "open-%s.png" % clip["id"])
            got = sheet(src, times, dst)
            if got:
                print("   sheet %s" % got)
                print("     times: %s" % ", ".join("%.2f" % t for t in times))
                print("     (the LAST tile is the current cut)"
                      if abs(times[-1] - start) < 1e-6 else
                      "     (current cut = %.2f)" % start)

        # the render itself, when it exists: look at what shipped
        outdir = _env.resolve(m.get("outdir", ""))
        mp4 = os.path.join(outdir, "%s-%s.mp4" % (m.get("prefix", "clip"), clip["id"]))
        if args.sheet and os.path.exists(mp4):
            dst = os.path.join(tmpdir, "open-%s-render.png" % clip["id"])
            got = sheet(mp4, [i / fps for i in range(8)], dst)
            if got:
                print("   render sheet %s  (first 8 frames as shipped)" % got)
        print()

    print("%d clip(s) flagged" % flagged)
    if flagged:
        print("A flag is a prompt to LOOK, not a verdict: re-run with --sheet, "
              "open the png, and pick a frame where the mouth is closed and the "
              "face is settled. Then set the clip's pad.head so the cut lands "
              "there, or move start_text to a different phrase.")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
