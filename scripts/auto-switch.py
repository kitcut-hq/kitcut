#!/usr/bin/env python
"""Decide which camera to be on, from the sound alone.

Stage 2 of the multicam round trip, and the part that is actually interesting:
stage 1 proved the machinery can replay an edit it was handed, this one has to
CHOOSE the edit. It gets the tapes and nothing else -- no shot list, no truth
sidecar, and above all no picture.

The picture is off limits on purpose. A synthetic tape holds a frozen frame
wherever the original editor was on another camera, so "which camera is moving"
IS the answer key, and any switcher that peeked at it would score beautifully
while editing nothing. Everything here is decided from one soundtrack.

How it decides:

  windows      1.5 s of audio every 0.5 s, silent ones dropped.
  embeddings   a speaker vector per window (sherpa-onnx, ONNX runtime, no
               torch and no gated model download).
  clustering   average-linkage agglomerative to K people, K declared -- how
               many were at the table is a fact about the shoot, not a guess.
               Sherpa's own clustering was tried first and merged two of the
               three speakers into one 33-second block; the embeddings were
               never the problem, so the clustering is done here instead.
  mapping      each cluster is bound to a camera by one hint per person: at
               this moment, the person speaking is the one on that camera.
               That is shoot metadata an editor has for free.
  grammar      be on the speaker's camera; never cut faster than `min_shot`;
               cut `lead` frames early, because an editor arrives on a face
               just before it starts talking; and optionally go wide where
               people talk over each other.

Why the wide is hard, and what is actually known about it. The editor's two
wide shots are the two densest patches of crosstalk in the film -- 11.7% and
18.0% of their length with more than one voice active, against a median of 0.0%
and a maximum of 6.9% across every close-up longer than three seconds. So the
wide plainly IS what a roundtable cuts to when several people talk at once, and
`wide_overlap_pct` implements exactly that.

It is nevertheless OFF by default, because knowing why the editor cut wide is
not the same as being able to predict it. Crosstalk is 4.5% of the film and the
wide is 14.2%; overlap is close to necessary but nowhere near sufficient, so a
threshold rule marks a lot of ground the editor stayed close on. Swept over 30
settings the best was 78.79% against 77.68% for plain speaker-following -- a
gain of one point, fitted to a film with two wide shots in it, which is not a
result. A different threshold matched far more of the human's cut TIMING (10 of
15 within a second, against 4) at slightly worse camera agreement, but it also
made 22 cuts against the human's 15, and `cuts_within_1s` does not penalise a
spurious cut -- so read that number with suspicion too.

Turn it on when a second film says it earns its place.

`--score` measures the result against the edit a human actually made. It reads
the answer, so it is the harness's mode, not the cutter's -- and knobs tuned
against one film are fitted to it. The honest number comes from the next film.

  --list    print the speaker track and the plan, decide nothing else
  --sweep   price several grammars at once, encoding nothing
  --score   compare the plan against a reference shot list (reads the answer)
  (none)    write projects/<id>/<id>.autoplan.json

Invoke as:  python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json
"""
import sys, os, json, argparse, subprocess, itertools

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _project  # noqa: E402

ROOT = _env.ROOT
ENV = _env.ENV
SR = 16000

DEFAULT_DIARIZE = {
    "model": "models/diarization/nemo_en_titanet_large.onnx",
    "segmentation":
        "models/diarization/sherpa-onnx-pyannote-segmentation-3-0/model.onnx",
    "window_s": 1.5, "hop_s": 0.5, "silence_rms": 0.005, "threads": 4,
    "paint": True,
}
DEFAULT_GRAMMAR = {
    "min_shot_s": 1.5,        # never cut faster than this
    "lead_s": 0.25,           # arrive on the face this early
    "wide_after_s": 0.0,      # 0 = never break a monologue with the wide
    "wide_dur_s": 4.0,
    "wide_overlap_pct": 0.0,  # 0 = off; see the docstring for why it is off
    "overlap_window_s": 10.0,
    "wide_between": 0,        # 1 = the film ALTERNATES close-up and wide; see
                              # alternating(). 0 = follow the speaker.
    "snap_s": 0.0,            # ... and land each cut in a pause within this
                              # many seconds of where the rhythm asks for it
}

# The grid --sweep walks unless the manifest names another, one entry per
# grammar knob. A knob left at a single value is held fixed and not printed,
# so a sweep stays readable however many axes exist.
DEFAULT_SWEEP = {
    "min_shot_s": [1.0, 1.5, 2.0, 3.0],
    "lead_s": [0.0, 0.25, 0.5],
    "wide_overlap_pct": [0.0, 3.0, 4.5, 6.0, 9.0, 14.0],
    "wide_after_s": [0.0],
    "wide_dur_s": [4.0],
    "wide_between": [0],
    "snap_s": [0.0],
}

WIDE = -2                     # a track value meaning "nobody in particular"
MAX_EMBED_S = 60.0            # the longest span handed to the speaker model in
                              # one go -- half its 122.88 s ceiling, see
                              # embed_span()
CLUSTER_CAP = 2000            # above this, cluster a sample -- see cluster()
MIN_VOICE_SHARE = 0.02        # a cluster smaller than this is a cough, not a
                              # person -- see cluster_people()


def rel(p):
    return _env.resolve(p)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def audio(path, start_s, dur_s):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
         "-ss", "%.6f" % start_s, "-t", "%.6f" % dur_s, "-i", path,
         "-vn", "-map", "0:a:0", "-f", "f32le", "-acodec", "pcm_f32le",
         "-ac", "1", "-ar", str(SR), "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV)
    if p.returncode != 0:
        sys.exit("no audio from %s:\n%s" % (path, (p.stderr or b"")[-1500:]))
    return np.frombuffer(p.stdout, dtype=np.float32)


def extractor(cfg):
    import sherpa_onnx
    model = rel(cfg["model"])
    if not os.path.exists(model):
        sys.exit("no speaker model at %s -- see the video-multicam-switch skill"
                 % _project.norm(model))
    return sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=model, num_threads=int(cfg["threads"])))


def embed_span(ex, chunk):
    """One unit-norm speaker vector for a span of any length.

    TitaNet's ONNX export has a hard ceiling that is not documented anywhere
    and is not a truncation: its mask is built for 12288 feature frames --
    122.88 s at the model's 10 ms hop -- and one frame more raises
    "Attempting to broadcast an axis by a dimension other than 1. 12288 by
    12298" from inside the encoder. Measured on this machine: 122.8 s embeds,
    123.0 s throws. The first four test films never held the floor that long
    without a pause the segmentation model would split on; a Ukrainian podcast
    answer ran 132 s and killed the run.

    So a long span is embedded in pieces and the unit vectors averaged, which
    is identical to the old behaviour for anything under the cap and keeps the
    WHOLE span represented -- taking the middle N seconds instead would throw
    away most of the evidence for exactly the segments that matter most.
    """
    step = int(MAX_EMBED_S * SR)
    vs = []
    for st in range(0, max(1, chunk.size), step):
        piece = chunk[st:st + step]
        if vs and piece.size < int(0.25 * SR):
            break                      # a scrap at the tail adds nothing
        s = ex.create_stream()
        s.accept_waveform(SR, piece)
        s.input_finished()
        v = np.array(ex.compute(s), dtype=np.float32)
        vs.append(v / (float(np.linalg.norm(v)) or 1.0))
    v = vs[0] if len(vs) == 1 else np.mean(vs, axis=0)
    return v / (float(np.linalg.norm(v)) or 1.0)


def embed(a, cfg, ex):
    """(times, unit-norm speaker vectors) for every window with sound in it."""
    w, hop = int(cfg["window_s"] * SR), int(cfg["hop_s"] * SR)
    ts, es = [], []
    for st in range(0, max(0, a.size - w), hop):
        chunk = a[st:st + w]
        if np.sqrt((chunk.astype(np.float64) ** 2).mean()) < cfg["silence_rms"]:
            continue
        es.append(embed_span(ex, chunk))
        ts.append((st + w / 2.0) / SR)
    if not es:
        sys.exit("no speech found: every window was below silence_rms")
    return np.array(ts), np.array(es)


def overlap_track(a, cfg, k, n_frames, fps):
    """Per frame: is more than one person talking right now?

    Windowed speaker embeddings cannot answer this. A window containing a
    speaker plus somebody's "yeah" embeds as the speaker, because the dominant
    voice dominates -- measured on the a16z clip, speaker churn inside the
    editor's wide shots was 0.015 changes per window, exactly the same as
    outside them. The segmentation model can: it is multi-label by design, so
    two of its segments overlapping in time IS overlapping speech.

    This matters because it is what the wide shot is FOR. The editor cut wide
    at the two moments of the film with the most crosstalk (11.7% and 18.0% of
    their length), and no close-up shot longer than three seconds had more than
    6.9%, with a median of 0.0%.
    """
    import sherpa_onnx
    seg = rel(cfg["segmentation"])
    if not os.path.exists(seg):
        return None
    c = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=seg)),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=rel(cfg["model"]), num_threads=int(cfg["threads"])),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=k),
        min_duration_on=0.2, min_duration_off=0.3)
    sd = sherpa_onnx.OfflineSpeakerDiarization(c)
    segs = [(s.start, s.end) for s in sd.process(a).sort_by_start_time()]
    n = np.zeros(n_frames, dtype=np.int16)
    for s, e in segs:
        lo = max(0, int(round(s * fps)))
        hi = min(n_frames, int(round(e * fps)))
        if hi > lo:
            n[lo:hi] += 1
    return segs, n


def paint(track, segs, a, ex, E, lab, fps, n_frames):
    """Overlay the segmentation model's exact boundaries onto the window track.

    The windows have one job left after this: voting the voice CENTROIDS into
    existence. Identity per moment comes from embedding each segment whole and
    taking the nearest centroid; timing comes from the segment's own edges.
    Both parts are load-bearing and were chosen from failures, not taste:

      * a 1.5 s window cannot resolve a 1.1 s interjection -- it embeds as a
        blend of two voices and lands on whichever dominates, which is how a
        two-line interjection cost 20 seconds of wrong camera on the second
        test film. A segment is exactly the speech it covers, nothing else.
      * the segmentation model's own speaker LABELS are not used at all --
        its clustering merged two of three speakers on the first test film.
        Boundaries good, identity bad; so take only the boundaries.

    Segments are painted in start order, so where two overlap, the later --
    the interjection -- wins the overlapped stretch. That is also what the
    editor does with it.
    """
    cents = {}
    for k in sorted(set(lab.tolist())):
        c = E[lab == k].mean(axis=0)
        cents[k] = c / (float(np.linalg.norm(c)) or 1.0)
    out = track.copy()
    for s, e in segs:
        lo, hi = int(s * SR), min(int(e * SR), a.size)
        if hi - lo < int(0.25 * SR):
            continue
        v = embed_span(ex, a[lo:hi])
        k = min(cents, key=lambda k_: 1.0 - float(v @ cents[k_]))
        fa, fb = max(0, int(round(s * fps))), min(n_frames, int(round(e * fps)))
        if fb > fa:
            out[fa:fb] = k
    return out


def contention(over, g, fps, n_frames):
    """Frames where crosstalk is dense enough to be worth going wide for."""
    if over is None or not g.get("wide_overlap_pct"):
        return np.zeros(n_frames, dtype=bool)
    w = max(1, int(round(g["overlap_window_s"] * fps)))
    hot = (over > 1).astype(np.float32)
    c = np.concatenate([[0.0], np.cumsum(hot)])
    out = np.zeros(n_frames, dtype=bool)
    for i in range(n_frames):
        lo, hi = max(0, i - w // 2), min(n_frames, i + w // 2)
        out[i] = (100.0 * (c[hi] - c[lo]) / max(1, hi - lo)) >= g["wide_overlap_pct"]
    return out


def cluster(E, k, cap=CLUSTER_CAP):
    """Average-linkage agglomerative on cosine distance, down to k groups.

    Average linkage, not complete: a speaker's own windows vary a lot with what
    they are saying, and complete linkage refuses to merge a group as soon as
    one shouted word sits far from one whispered one.

    Two things keep this affordable on a long film. The merge uses the
    Lance-Williams update -- the distance from a merged pair to everyone else
    is the size-weighted mean of the two rows it came from -- so each merge
    costs a row rewrite instead of recomputing every pair from its members. And
    above `cap` windows it clusters an evenly spaced SAMPLE and then assigns
    every window to its nearest centroid.

    Sampling evenly rather than randomly is deliberate: a voice that only
    appears in the last ten minutes must still be represented. An hour of film
    is ~7200 windows, where recomputing every pair per merge is upwards of
    10^11 operations and simply never returns; that is the wall this exists
    to clear, and it was hit on the first hour-long film put through.
    """
    n = len(E)
    idx = (np.arange(n) if n <= cap
           else np.unique(np.linspace(0, n - 1, cap).astype(int)))
    S = E[idx]
    m = len(S)
    D = (1.0 - S @ S.T).astype(np.float64)
    np.fill_diagonal(D, np.inf)
    size = np.ones(m)
    members = [[i] for i in range(m)]
    for _ in range(max(0, m - k)):
        f = int(np.argmin(D))
        i, j = divmod(f, m)
        if i > j:
            i, j = j, i
        ni, nj = size[i], size[j]
        row = (ni * D[i] + nj * D[j]) / (ni + nj)
        D[i] = row
        D[:, i] = row
        D[i, i] = np.inf
        D[j, :] = np.inf
        D[:, j] = np.inf
        size[i] = ni + nj
        members[i] = members[i] + members[j]
        members[j] = []
    groups = sorted((g for g in members if g), key=min)

    lab = np.empty(n, dtype=np.int32)
    if m == n:
        for k_, g in enumerate(groups):
            for i in g:
                lab[i] = k_
    else:
        cents = []
        for g in groups:
            c = S[g].mean(axis=0)
            cents.append(c / (float(np.linalg.norm(c)) or 1.0))
        lab = np.argmax(E @ np.array(cents).T, axis=1).astype(np.int32)
        groups = [np.nonzero(lab == k_)[0].tolist()
                  for k_ in range(len(groups))]
    return lab, groups


def cluster_people(E, K, min_share=MIN_VOICE_SHARE, headroom=8):
    """Cluster until K clusters are big enough to be PEOPLE, not until K exist.

    K is declared as a fact about the shoot -- how many were at the table --
    but agglomerative clustering does not spend its splits on people. It peels
    outliers first: a cough, a laugh, a clipped word, a moment of music. Asking
    it for exactly K groups therefore hands speaker slots to noise while two
    real speakers stay merged, and the merged pair is the expensive kind of
    wrong -- the film cuts to the wrong face for as long as that person talks.

    Measured on one podcast, both segments, same two hosts plus a third man
    behind the camera:

        fitted segment   K=3 -> 84.1 / 15.3 / 0.6     the third man is inside
                                                       the 84, unsplit
                         K=4 -> 47.1 / 37.5 / 14.9 / 0.4      split, correct
        held-out segment K=4 -> 82.4 / 17.5 / 0.1 / 0.1       still merged
                         K=8 -> 42.4 / 39.6 / 16.9 + 5 specks split, correct

    Declaring K=4 fixed the first and did nothing for the second. So raise k
    until K clusters clear `min_share`, and let the specks keep their own
    labels -- an unmapped voice already falls back to the wide, which is where
    an editor puts a sound with no face.
    """
    best = None
    for k in range(K, K + headroom + 1):
        lab, groups = cluster(E, k)
        big = sum(1 for g in groups if len(g) >= min_share * len(E))
        if best is None:
            best = (lab, groups, k, big)
        if big >= K:
            return lab, groups, k, big
    return best


def separation(E, lab, cap=CLUSTER_CAP):
    """Worst mean distance inside a voice vs the closest between two.

    Sampled above `cap` for the same reason clustering is: the full matrix for
    an hour of film is 7200x7200, and this number is a sanity check, not a
    measurement anything depends on.
    """
    n = len(E)
    idx = (np.arange(n) if n <= cap
           else np.unique(np.linspace(0, n - 1, cap).astype(int)))
    Es, ls = E[idx], lab[idx]
    D = 1.0 - Es @ Es.T
    within, between = 0.0, None
    ks = sorted(set(ls.tolist()))
    for a in ks:
        ia = np.nonzero(ls == a)[0]
        if not len(ia):
            continue
        within = max(within, float(D[np.ix_(ia, ia)].mean()))
        for b in ks:
            if b <= a:
                continue
            ib = np.nonzero(ls == b)[0]
            if not len(ib):
                continue
            v = float(D[np.ix_(ia, ib)].mean())
            between = v if between is None else min(between, v)
    return within, between


def speaker_per_frame(ts, lab, n_frames, fps):
    """The nearest window's cluster, for every frame, held through silence."""
    out = np.full(n_frames, -1, dtype=np.int32)
    if not len(ts):
        return out
    idx = 0
    for f in range(n_frames):
        t = f / fps
        while idx + 1 < len(ts) and abs(ts[idx + 1] - t) <= abs(ts[idx] - t):
            idx += 1
        out[f] = lab[idx]
    return out


def runs_of(track):
    out, start = [], 0
    for i in range(1, len(track)):
        if track[i] != track[i - 1]:
            out.append((start, i, int(track[start])))
            start = i
    out.append((start, len(track), int(track[start])))
    return out


def alternating(track, cam_of, wide, g, fps, n_frames, bounds=None):
    """A film that alternates close-up and room on a cadence, not on a speaker.

    Measured on the УТ-2 podcast, whose transition matrix leaves no doubt: a
    close-up is followed by the wide 97% and 92% of the time and by the other
    close-up 3%, every shot runs 11.6 s on average with a median of 11.0, and
    the wide holds 52% of the runtime. The room is the DEFAULT state there and
    the faces are the accents -- the exact inverse of the speaker-following
    grammar above, which on that film scored below simply sitting on the wide.

    So the speaker track answers a smaller question here: not *when* to cut,
    which the rhythm decides, but *whose* close-up the rhythm should punch in
    to. `snap_s` then moves each cut to the nearest gap between speech
    segments, because an editor cuts in a pause and a metronome does not.
    """
    face = max(1, int(round(g["wide_after_s"] * fps)))
    room = max(1, int(round(g["wide_dur_s"] * fps)))
    snap = int(round(g.get("snap_s", 0.0) * fps))
    plan, pos, on_wide = [], 0, False
    while pos < n_frames:
        end = min(n_frames, pos + (room if on_wide else face))
        if snap and bounds is not None and len(bounds) and end < n_frames:
            near = bounds[int(np.argmin(np.abs(bounds - end)))]
            if abs(int(near) - end) <= snap and int(near) > pos:
                end = min(n_frames, int(near))
        if on_wide:
            plan.append((wide, pos, end, "the room, between close-ups"))
        else:
            seen = track[pos:end]
            seen = seen[seen >= 0]
            if seen.size:
                s_ = int(np.bincount(seen).argmax())
                c = cam_of.get(s_) or wide
                why = "punch in: voice %d holds this beat -> %s" % (s_, c)
            else:
                c, why = wide, "nobody speaking on this beat -- stay wide"
            plan.append((c, pos, end, why))
        pos, on_wide = end, not on_wide
    out = []
    for c, a, b, why in plan:                 # a punch-in to the wide is no cut
        if out and out[-1][0] == c:
            out[-1] = (c, out[-1][1], b, out[-1][3])
        elif b > a:
            out.append((c, a, b, why))
    return out


def grammar(track, cam_of, wide, g, fps, n_frames, hot=None, bounds=None):
    """The speaker track, turned into an edit."""
    if g.get("wide_between") and wide and g.get("wide_after_s"):
        return alternating(track, cam_of, wide, g, fps, n_frames, bounds)

    lead = int(round(g["lead_s"] * fps))
    min_shot = max(1, int(round(g["min_shot_s"] * fps)))

    if hot is not None and hot.any() and wide:
        track = np.where(hot, WIDE, track)      # crosstalk wins over the speaker
    runs = runs_of(track)
    if lead:                                   # arrive early on the new face
        runs = [(max(0, a - lead) if i else 0, max(0, b - lead) if i + 1 < len(runs)
                 else n_frames, s) for i, (a, b, s) in enumerate(runs)]
        runs = [(a, b, s) for a, b, s in runs if b > a]

    merged = []                                # absorb anything too short
    for a, b, s in runs:
        if merged and (b - a) < min_shot:
            merged[-1] = (merged[-1][0], b, merged[-1][2])
        elif merged and merged[-1][2] == s:
            merged[-1] = (merged[-1][0], b, s)
        else:
            merged.append((a, b, s))
    while len(merged) > 1 and (merged[0][1] - merged[0][0]) < min_shot:
        merged[1] = (merged[0][0], merged[1][1], merged[1][2])
        merged.pop(0)

    plan = []
    for a, b, s in merged:
        c = cam_of.get(s)
        why = "voice %d is speaking -> %s" % (s, c)
        if s == WIDE:
            c = wide
            why = "several people talking at once -> the wide"
        elif c is None:
            c = wide or (plan[-1][0] if plan else None)
            why = "no camera bound to voice %d -- falling back to the wide" % s
        # Break a long run with the wide, and keep breaking it. One cutaway in
        # the middle of a 170-second answer is not how anyone cuts: the УТ-2
        # podcast spends 52% of its runtime on the wide with a mean shot of
        # 11.6 s, alternating face and room while ONE person talks, which no
        # speaker-following rule can reach. A rhythm is a property of a
        # channel's style, so it lives in the manifest -- wide_after_s stays 0
        # by default and every film cut before this one is unchanged.
        cut = int(round(g["wide_after_s"] * fps))
        hold = max(1, int(round(g["wide_dur_s"] * fps)))
        pos, first = a, True
        if wide and cut:
            # Only cut away while a whole shot's worth of face remains to come
            # back to, so the rhythm never leaves a two-frame stub behind.
            while b - pos > cut + hold + min_shot:
                on = pos + cut
                plan.append((c, pos, on,
                             why if first else "back to %s after the cutaway" % c))
                plan.append((wide, on, on + hold,
                             "cutaway: %s held the frame longer than %.0fs"
                             % (c, g["wide_after_s"])))
                pos, first = on + hold, False
        plan.append((c, pos, b,
                     why if first else "back to %s after the cutaway" % c))
    out = []
    for c, a, b, why in plan:
        if out and out[-1][0] == c:
            out[-1] = (c, out[-1][1], b, out[-1][3])
        elif b > a:
            out.append((c, a, b, why))
    return [(c, a, b, w) for c, a, b, w in out]


def score(plan, ref_shots, n_frames, fps):
    """Agreement with an edit a human made. Reads the answer; harness only.

    Cut timing is scored in BOTH directions on purpose. "How many of their
    cuts have one of mine within a second" alone rewards spraying cuts -- a
    setting that made 22 cuts against the human's 15 looked better on it while
    being a worse edit. "How many of mine sit near one of theirs" is the
    precision that catches it; quote the pair, never either alone.
    """
    mine = np.empty(n_frames, dtype=object)
    for c, a, b, _ in plan:
        mine[a:b] = c
    theirs = np.empty(n_frames, dtype=object)
    for s in ref_shots:
        theirs[s["start"]:min(s["end"], n_frames)] = s["camera"]
    same = int(sum(1 for x, y in zip(mine, theirs) if x is not None and x == y))
    per = {}
    for x, y in zip(mine, theirs):
        if y is None:
            continue
        e = per.setdefault(y, [0, 0])
        e[1] += 1
        if x == y:
            e[0] += 1
    mycuts = [a for _, a, _, _ in plan[1:]]
    refcuts = [s["start"] for s in ref_shots[1:]]
    one_s = max(1, int(round(fps)))
    near = [min(mycuts, key=lambda m: abs(m - r)) - r
            for r in refcuts if mycuts]
    back = [min(refcuts, key=lambda r: abs(r - m)) - m
            for m in mycuts if refcuts]
    return {"agreement_pct": round(100.0 * same / max(1, n_frames), 2),
            "per_camera": {k: [v[0], v[1], round(100.0 * v[0] / max(1, v[1]), 1)]
                           for k, v in sorted(per.items())},
            "my_cuts": len(mycuts), "reference_cuts": len(refcuts),
            "cut_offsets": near,
            "cuts_within_1s": sum(1 for d in near if abs(d) <= one_s),
            "my_cuts_near_theirs": sum(1 for d in back if abs(d) <= one_s)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--list", action="store_true",
                    help="print the speaker track and the plan, write nothing")
    ap.add_argument("--sweep", action="store_true",
                    help="price several grammars, write nothing")
    ap.add_argument("--score", metavar="SHOTS",
                    help="measure against a reference shot list (reads the answer)")
    ap.add_argument("--out", help="default projects/<id>/<id>.autoplan.json")
    for k, v in DEFAULT_GRAMMAR.items():
        ap.add_argument("--" + k.replace("_", "-"), type=float, default=None)
    args = ap.parse_args()

    with open(rel(args.manifest), encoding="utf-8") as f:
        m = json.load(f)
    pid = _project.project_id(m, rel(args.manifest))
    dcfg = dict(DEFAULT_DIARIZE, **(m.get("diarize") or {}))
    g = dict(DEFAULT_GRAMMAR, **(m.get("grammar") or {}))
    for k in DEFAULT_GRAMMAR:
        v = getattr(args, k, None)
        if v is not None:
            g[k] = v

    files = {c["id"]: rel(c["file"]) for c in m["cameras"]}
    anchor = m.get("anchor")
    if not isinstance(anchor, dict):
        sys.exit("this stage needs explicit `anchor` frames per camera: the "
                 "picture anchor is derived from a plan, and the plan is what "
                 "we are about to write")
    film = m.get("film") or {}
    n_frames = int(film.get("frames") or 0)
    if not n_frames:
        sys.exit("declare film.frames -- the in and out points are given, "
                 "because what is scored here is the switching, not the trim")
    src = m.get("audio_from") or m.get("reference") or list(files)[0]
    with open(rel(m["sync"]), encoding="utf-8") as f:
        fps = json.load(f)["fps"]

    hints = m.get("speakers") or []
    if not hints:
        sys.exit("declare `speakers`: one {camera, at} per person, naming a "
                 "moment when that person is talking")
    # People at the table with no close-up of their own -- a host off camera,
    # a guest the shoot never framed. Declaring them is shoot metadata, and it
    # matters: their voices then cluster separately instead of polluting a
    # framed speaker's cluster, and an unmapped voice falls back to the wide,
    # which is where an editor puts a voice with no face.
    K = len(hints) + int(m.get("off_camera_speakers") or 0)
    wide = m.get("wide")

    a = audio(files[src], anchor[src] / fps, n_frames / fps)
    print("%s: %.1f s of sound from %s" % (pid, a.size / float(SR), src))
    ex = extractor(dcfg)
    ts, E = embed(a, dcfg, ex)
    lab, groups, k_used, n_big = cluster_people(E, K)
    within, between = separation(E, lab)
    print("%d windows, %d voices (%d framed); cosine distance within %.3f, "
          "between %.3f"
          % (len(ts), K, len(hints), within,
             between if between is not None else -1))
    if k_used != K:
        print("  clustered to %d to get %d voices above %.0f%% -- the extra "
              "groups are specks, not people" % (k_used, n_big,
                                                 100 * MIN_VOICE_SHARE))
    if n_big < K:
        print("  !! only %d of %d declared voices clear %.0f%% even at k=%d -- "
              "either somebody barely speaks here, or two are still merged"
              % (n_big, K, 100 * MIN_VOICE_SHARE, k_used))
    if between is not None and between <= within:
        print("  !! the voices do not separate -- every cut after this is a "
              "guess. Try another model or fewer speakers.")

    cam_of = {}
    for hint in hints:
        t = float(hint["at"])
        i = int(np.argmin(np.abs(ts - t)))
        k = int(lab[i])
        if k in cam_of:
            print("  !! %s and %s both resolve to the same voice -- move a hint"
                  % (cam_of[k], hint["camera"]))
        cam_of[k] = hint["camera"]
    for k in sorted(set(lab.tolist())):
        n = int((lab == k).sum())
        print("  voice %d -> %-5s  %3d windows (%4.1f%%)"
              % (k, cam_of.get(k, "?"), n, 100.0 * n / len(lab)))

    track = speaker_per_frame(ts, lab, n_frames, fps)

    got = overlap_track(a, dcfg, max(K, 2), n_frames, fps)
    if got is None:
        over = None
        print("  no segmentation model -- boundaries stay window-blurred and "
              "crosstalk cannot be detected")
    else:
        segs, over = got
        pct = 100.0 * float((over > 1).mean())
        if dcfg.get("paint"):
            track = paint(track, segs, a, ex, E, lab, fps, n_frames)
            print("  %d speech segments painted over the window track; "
                  "crosstalk on %.1f%% of the film" % (len(segs), pct))
        else:
            print("  painting off by manifest; crosstalk on %.1f%% of the film"
                  % pct)

    # Where speech stops and starts, in frames -- the only places an editor
    # cuts. The alternating grammar snaps its beats to these; nothing else
    # uses them, and without the segmentation model there are none.
    bounds = np.array(sorted({int(round(x * fps)) for se in (segs if got else [])
                              for x in se}), dtype=np.int64) if got else None

    def build(gg):
        return grammar(track, cam_of, wide, gg, fps, n_frames,
                       contention(over, gg, fps, n_frames), bounds)

    ref = None
    if args.score:
        with open(rel(args.score), encoding="utf-8") as f:
            ref = json.load(f)["shots"]

    if args.sweep:
        # Which axes to walk is manifest data. The default grid is the one the
        # a16z films wanted; a channel that cuts on a rhythm rather than on the
        # speaker lives on wide_after_s, and pricing that must not need an edit
        # to this file.
        grid = dict(DEFAULT_SWEEP, **(m.get("sweep") or {}))
        axes = [k for k in DEFAULT_SWEEP if len(grid[k]) > 1] or ["min_shot_s"]
        print("\n  %s  cuts%s"
              % ("".join("%13s" % k for k in axes),
                 "  agree   theirs-hit  mine-near" if ref else ""))
        for combo in itertools.product(*[grid[k] for k in DEFAULT_SWEEP]):
            gg = dict(g, **dict(zip(DEFAULT_SWEEP, combo)))
            pl = build(gg)
            extra = ""
            if ref:
                sc = score(pl, ref, n_frames, fps)
                extra = ("  %5.1f%%   %5d/%-4d %5d/%-4d"
                         % (sc["agreement_pct"], sc["cuts_within_1s"],
                            sc["reference_cuts"],
                            sc["my_cuts_near_theirs"], sc["my_cuts"]))
            print("  %s  %4d%s"
                  % ("".join("%13.2f" % gg[k] for k in axes), len(pl), extra))
        return

    plan = build(g)
    print("\n   #  cam      start       end     len")
    for i, (c, x, y, w) in enumerate(plan):
        print("  %2d  %-5s %8s %9s %7.2f   %s"
              % (i, c, hhmmss(x / fps), hhmmss(y / fps), (y - x) / fps, w))
    print("\n%d shots, %d cuts, grammar %s"
          % (len(plan), len(plan) - 1,
             ", ".join("%s=%g" % (k, v) for k, v in sorted(g.items()))))

    sc = None
    if ref:
        sc = score(plan, ref, n_frames, fps)
        print("\nagainst the edit a human made:")
        print("  same camera on %.2f%% of the timeline" % sc["agreement_pct"])
        for c, (hit, tot, pct) in sorted(sc["per_camera"].items()):
            print("    %-5s %5d of %5d frames  %5.1f%%" % (c, hit, tot, pct))
        print("  %d cuts against their %d; %d of theirs matched within a second, "
              "%d of mine sit near one of theirs"
              % (sc["my_cuts"], sc["reference_cuts"], sc["cuts_within_1s"],
                 sc["my_cuts_near_theirs"]))

    if args.list:
        return

    doc = {"_comment": "A camera plan decided from the soundtrack alone by "
                       "scripts/auto-switch.py -- no shot list, no truth "
                       "sidecar, no picture. Same shape as a shots.json so "
                       "angle-cut.py can read it as plan_from.",
           "id": pid, "fps": fps, "n_frames": n_frames,
           "diarize": dcfg, "grammar": g,
           "speakers": {str(k): v for k, v in sorted(cam_of.items())},
           "separation": {"within": round(within, 4),
                          "between": None if between is None else round(between, 4)},
           "score": sc,
           "cuts": [a for _, a, _, _ in plan[1:]],
           "shots": [{"start": x, "end": y, "camera": c, "why": w}
                     for c, x, y, w in plan]}
    out = args.out or os.path.join(
        _project.find_project_dir(rel(args.manifest)) or os.path.join(ROOT, "temp"),
        "%s.autoplan.json" % pid)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print("\nwrote %s" % _project.norm(out))
    _project.record(pid, "auto-switch", script=__file__, argv=sys.argv[1:],
                    note="%d shots from the sound alone%s"
                         % (len(plan),
                            "" if not sc else ", %.1f%% agreement with the human edit"
                            % sc["agreement_pct"]))


if __name__ == "__main__":
    main()
