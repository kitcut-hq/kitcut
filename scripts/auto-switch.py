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
               just before it starts talking; and optionally break a long
               monologue with the wide.

`--score` measures the result against the edit a human actually made. It reads
the answer, so it is the harness's mode, not the cutter's -- and knobs tuned
against one film are fitted to it. The honest number comes from the next film.

  --list    print the speaker track and the plan, decide nothing else
  --sweep   price several grammars at once, encoding nothing
  --score   compare the plan against a reference shot list (reads the answer)
  (none)    write projects/<id>/<id>.autoplan.json

Invoke as:  python scripts/auto-switch.py --manifest projects/<id>/anglecut-auto.json
"""
import sys, os, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import numpy as np  # noqa: E402

import _project  # noqa: E402

ROOT = _env.ROOT
ENV = _env.ENV
SR = 16000

DEFAULT_DIARIZE = {
    "model": "models/diarization/nemo_en_titanet_large.onnx",
    "window_s": 1.5, "hop_s": 0.5, "silence_rms": 0.005, "threads": 4,
}
DEFAULT_GRAMMAR = {
    "min_shot_s": 1.5,     # never cut faster than this
    "lead_s": 0.25,        # arrive on the face this early
    "wide_after_s": 0.0,   # 0 = never break a monologue with the wide
    "wide_dur_s": 4.0,
}


def rel(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


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


def embed(a, cfg):
    """(times, unit-norm speaker vectors) for every window with sound in it."""
    import sherpa_onnx
    model = rel(cfg["model"])
    if not os.path.exists(model):
        sys.exit("no speaker model at %s -- see the video-multicam-switch skill"
                 % _project.norm(model))
    ex = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=model, num_threads=int(cfg["threads"])))
    w, hop = int(cfg["window_s"] * SR), int(cfg["hop_s"] * SR)
    ts, es = [], []
    for st in range(0, max(0, a.size - w), hop):
        chunk = a[st:st + w]
        if np.sqrt((chunk.astype(np.float64) ** 2).mean()) < cfg["silence_rms"]:
            continue
        s = ex.create_stream()
        s.accept_waveform(SR, chunk)
        s.input_finished()
        v = np.array(ex.compute(s), dtype=np.float32)
        n = float(np.linalg.norm(v)) or 1.0
        es.append(v / n)
        ts.append((st + w / 2.0) / SR)
    if not es:
        sys.exit("no speech found: every window was below silence_rms")
    return np.array(ts), np.array(es)


def cluster(E, k):
    """Average-linkage agglomerative on cosine distance, down to k groups.

    Average linkage, not complete: a speaker's own windows vary a lot with what
    they are saying, and complete linkage refuses to merge a group as soon as
    one shouted word sits far from one whispered one.
    """
    D = 1.0 - E @ E.T
    groups = [[i] for i in range(len(E))]
    while len(groups) > k:
        best = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                v = float(D[np.ix_(groups[i], groups[j])].mean())
                if best is None or v < best[0]:
                    best = (v, i, j)
        _, i, j = best
        groups[i] = groups[i] + groups[j]
        groups.pop(j)
    groups.sort(key=min)
    lab = np.empty(len(E), dtype=np.int32)
    for k_, g in enumerate(groups):
        for i in g:
            lab[i] = k_
    return lab, groups


def separation(E, lab):
    D = 1.0 - E @ E.T
    within, between = 0.0, None
    for a in sorted(set(lab.tolist())):
        ia = np.nonzero(lab == a)[0]
        within = max(within, float(D[np.ix_(ia, ia)].mean()))
        for b in sorted(set(lab.tolist())):
            if b <= a:
                continue
            ib = np.nonzero(lab == b)[0]
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


def grammar(track, cam_of, wide, g, fps, n_frames):
    """The speaker track, turned into an edit."""
    lead = int(round(g["lead_s"] * fps))
    min_shot = max(1, int(round(g["min_shot_s"] * fps)))

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
        if c is None:
            c = wide or (plan[-1][0] if plan else None)
        span = b - a
        cut = int(round(g["wide_after_s"] * fps))
        if wide and cut and span > cut:         # break a monologue with the wide
            hold = min(int(round(g["wide_dur_s"] * fps)), max(1, span // 3))
            mid = a + (span - hold) // 2
            plan.append((c, a, mid))
            plan.append((wide, mid, mid + hold))
            plan.append((c, mid + hold, b))
        else:
            plan.append((c, a, b))
    out = []
    for c, a, b in plan:
        if out and out[-1][0] == c:
            out[-1] = (c, out[-1][1], b)
        elif b > a:
            out.append((c, a, b))
    return out


def score(plan, ref_shots, n_frames):
    """Agreement with an edit a human made. Reads the answer; harness only."""
    mine = np.empty(n_frames, dtype=object)
    for c, a, b in plan:
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
    mycuts = [a for _, a, _ in plan[1:]]
    refcuts = [s["start"] for s in ref_shots[1:]]
    near = []
    for r in refcuts:
        if mycuts:
            d = min(mycuts, key=lambda m: abs(m - r)) - r
            near.append(d)
    return {"agreement_pct": round(100.0 * same / max(1, n_frames), 2),
            "per_camera": {k: [v[0], v[1], round(100.0 * v[0] / max(1, v[1]), 1)]
                           for k, v in sorted(per.items())},
            "my_cuts": len(mycuts), "reference_cuts": len(refcuts),
            "cut_offsets": near,
            "cuts_within_1s": sum(1 for d in near if abs(d) <= 24)}


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
    wide = m.get("wide")

    a = audio(files[src], anchor[src] / fps, n_frames / fps)
    print("%s: %.1f s of sound from %s" % (pid, a.size / float(SR), src))
    ts, E = embed(a, dcfg)
    lab, groups = cluster(E, len(hints))
    within, between = separation(E, lab)
    print("%d windows, %d speakers; cosine distance within %.3f, between %.3f"
          % (len(ts), len(hints), within, between if between is not None else -1))
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

    def build(gg):
        return grammar(track, cam_of, wide, gg, fps, n_frames)

    ref = None
    if args.score:
        with open(rel(args.score), encoding="utf-8") as f:
            ref = json.load(f)["shots"]

    if args.sweep:
        print("\n  min_shot   lead  wide_after  cuts%s" % ("  agree   cuts<1s" if ref else ""))
        for ms in (1.0, 1.5, 2.0, 3.0):
            for ld in (0.0, 0.25, 0.5):
                for wa in (0.0, 12.0):
                    gg = dict(g, min_shot_s=ms, lead_s=ld, wide_after_s=wa)
                    pl = build(gg)
                    extra = ""
                    if ref:
                        sc = score(pl, ref, n_frames)
                        extra = "  %5.1f%%   %2d/%d" % (sc["agreement_pct"],
                                                        sc["cuts_within_1s"],
                                                        sc["reference_cuts"])
                    print("  %8.2f %6.2f %11.1f  %4d%s" % (ms, ld, wa, len(pl), extra))
        return

    plan = build(g)
    print("\n   #  cam      start       end     len")
    for i, (c, x, y) in enumerate(plan):
        print("  %2d  %-5s %8s %9s %7.2f"
              % (i, c, hhmmss(x / fps), hhmmss(y / fps), (y - x) / fps))
    print("\n%d shots, %d cuts, grammar %s"
          % (len(plan), len(plan) - 1,
             ", ".join("%s=%g" % (k, v) for k, v in sorted(g.items()))))

    sc = None
    if ref:
        sc = score(plan, ref, n_frames)
        print("\nagainst the edit a human made:")
        print("  same camera on %.2f%% of the timeline" % sc["agreement_pct"])
        for c, (hit, tot, pct) in sorted(sc["per_camera"].items()):
            print("    %-5s %5d of %5d frames  %5.1f%%" % (c, hit, tot, pct))
        print("  %d cuts against their %d; %d of theirs matched within a second"
              % (sc["my_cuts"], sc["reference_cuts"], sc["cuts_within_1s"]))

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
           "cuts": [a for _, a, _ in plan[1:]],
           "shots": [{"start": x, "end": y, "camera": c} for c, x, y in plan]}
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
