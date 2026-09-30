"""Talking heads for sketch films: the rigs a manifest names and the mouth each voice line moves.

A manifest's "heads" names photo rigs built by head-rig.py:

    "heads": {"alex": {"photo": "sources/alex.png"}, "ada": "sources/ada.jpg"}

sketch-render inlines each rig (SK.RIGS.<name>, its pictures as SK.IMG['rig:<name>:head'] and
'rig:<name>:photo') and the engine module sketch/heads.js, and gives every voice-over line its
speaker and a mouth track measured from that line's own audio:

    SK.VO.lines[i] = {start, end, words, who: "alex", mouth: {fps: 50, o: [0..100], w: [0..100]}}

`o` is how open the mouth is: the voice's loudness in the speech band, on a scale set by the
line's own loud parts, so a quiet voice opens its mouth as wide as a loud one; the mouth closes
where the voice stops, and on the m's, b's and p's, which are quiet in that band too. `w` is how
wide the lips are: the share of the voice above 1.8 kHz against the share under 900 Hz, around
the line's own middle (an "ee" spreads the lips, an "oo" rounds them). The track leads the sound
by LEAD seconds: a mouth that opens with its sound reads as late.

Not an entry script: imported by sketch-render.py after `_env`.
"""

import os
import json
import hashlib

import numpy as np

import _sketch

FPS = 50  # mouth samples a second
SR = 16000
# the track's knobs (mouth-bench.py --sweep prices them against a real mouth):
#   range_db  how many dB under the line's loud parts the mouth is still open at all
#   power     the curve from loudness to opening (over 1: shut sooner, wide only when loud)
#   attack, release   how much of the way to its target the mouth goes each 20 ms, opening
#             and closing (a mouth opens faster than it closes)
#   lead      seconds the mouth moves before its sound: measured on two phone takes of a man
#             talking to camera, a real mouth leads its sound by 80-140 ms (mouth-bench.py,
#             2026-09-30; the literature says 100-300); 40 ms, the first guess, was late
TRACK = {"range_db": 28.0, "power": 1.35, "attack": 0.75, "release": 0.4, "lead": 0.08}
LEAD = TRACK["lead"]


def specs(m):
    """[(name, photo path, rig folder)] for the manifest's "heads"."""
    out = []
    for name, spec in (m.get("heads") or {}).items():
        _sketch.safe_name(name, "head")
        if isinstance(spec, str):
            spec = {"photo": spec}
        rdir = _sketch.rel(m, spec.get("rig") or os.path.join("rigs", name))
        out.append((name, _sketch.rel(m, spec["photo"]) if spec.get("photo") else None, rdir))
    return out


def rigs(m):
    """{name: (rig dict, head.png path, photo.jpg path)}; exits naming a rig not built yet."""
    out = {}
    for name, _photo, rdir in specs(m):
        p = os.path.join(rdir, "rig.json")
        if not os.path.exists(p):
            raise SystemExit(
                "head %r has no rig: python scripts/head-rig.py --manifest %s"
                % (name, os.path.relpath(m["_path"]))
            )
        with open(p, encoding="utf-8") as f:
            rig = json.load(f)
        out[name] = (
            rig,
            os.path.join(rdir, rig["head"]["file"]),
            os.path.join(rdir, rig["photo"]["file"]),
        )
    return out


def rigs_script(m):
    """The <script> that hands the rigs to the engine ("" for a film without heads)."""
    if not m.get("heads"):
        return ""
    body = {n: r for n, (r, _, _) in rigs(m).items()}
    return "<script>\nSK.RIGS = %s;\n</script>" % json.dumps(body, separators=(",", ":"))


def images(m):
    """{'rig:<name>:head': path, 'rig:<name>:photo': path} for the page's image loader."""
    out = {}
    for n, (_r, head, photo) in rigs(m).items():
        out["rig:%s:head" % n] = head
        out["rig:%s:photo" % n] = photo
    return out


def _cache_path(m, path):
    with open(path, "rb") as f:
        h = hashlib.sha1(f.read(), usedforsecurity=False).hexdigest()[:12]
    d = os.path.join(m["_temp"], "mouth")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "%s_%d.json" % (h, FPS))


def mouth_track(x, sr=SR, fps=FPS, **knobs):
    """{fps, o, w} for one line's samples (mono float). See the module docstring; knobs
    override TRACK (mouth-bench.py --sweep)."""
    k_ = {**TRACK, **knobs}
    hop = sr // fps
    win = hop * 2
    n = max(1, int(np.ceil(len(x) / hop)))
    pad = np.concatenate([np.zeros(win // 2), x, np.zeros(win + hop)])
    w = np.hanning(win)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    band = (freqs >= 250) & (freqs <= 3500)
    lo = (freqs >= 250) & (freqs <= 900)
    hi = (freqs >= 1800) & (freqs <= 3500)
    e_all, e_lo, e_hi = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        s = pad[i * hop : i * hop + win]
        X = np.abs(np.fft.rfft(s * w)) ** 2
        e_all[i], e_lo[i], e_hi[i] = X[band].sum(), X[lo].sum(), X[hi].sum()
    db = 10 * np.log10(e_all + 1e-12)
    voiced = db > db.max() - 45
    peak = np.percentile(db[voiced], 92) if voiced.any() else db.max()
    floor = peak - k_["range_db"]
    target = np.clip((db - floor) / (peak - floor), 0, 1) ** k_["power"]
    o = np.zeros(n)
    cur = 0.0
    for i in range(n):  # a mouth opens faster than it closes
        k = k_["attack"] if target[i] > cur else k_["release"]
        cur += (target[i] - cur) * k
        o[i] = cur
    ratio = e_hi / (e_lo + e_hi + 1e-12)
    mid = np.median(ratio[target > 0.3]) if (target > 0.3).any() else 0.5
    wv = np.clip(0.5 + (ratio - mid) * 1.6, 0, 1) * (o > 0.05) + 0.5 * (o <= 0.05)
    lead = int(round(k_["lead"] * fps))
    o = np.concatenate([o[lead:], np.zeros(lead)])
    wv = np.concatenate([wv[lead:], np.full(lead, 0.5)])
    return {
        "fps": fps,
        "o": np.round(o * 100).astype(int).tolist(),
        "w": np.round(wv * 100).astype(int).tolist(),
    }


def line_mouth(m, path):
    """The mouth track of one line's audio file, cached by the file's content."""
    cp = _cache_path(m, path)
    if os.path.exists(cp):
        with open(cp, encoding="utf-8") as f:
            return json.load(f)
    tr = mouth_track(_sketch.decode(path, sr=SR))
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(tr, f, separators=(",", ":"))
    return tr


def voice_lines(m, timeline):
    """The page's SK.VO lines for a film with heads: each with its speaker and its mouth. The
    speaker is the timeline line's `who` (sketch-vo copies it from the script), else the script
    line's, else the only head when there is one."""
    vo_lines = (m.get("vo") or {}).get("lines") or []
    only = list(m.get("heads") or {})
    out = []
    for L in timeline["lines"]:
        i = L.get("i", len(out))
        who = L.get("who") or (vo_lines[i].get("who") if i < len(vo_lines) else None)
        if not who and len(only) == 1:
            who = only[0]
        row = {"start": L["start"], "end": L["end"], "words": L["words"], "who": who or ""}
        f = L.get("file")
        if f and os.path.exists(_sketch.rel(m, f)):
            row["mouth"] = line_mouth(m, _sketch.rel(m, f))
        out.append(row)
    return out
