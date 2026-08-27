#!/usr/bin/env python
"""Recover the edit from a finished video: where it cuts, and which angle each
shot was taken on.

This is the reader half of the multicam round-trip test. Given a programme that
somebody else cut out of several cameras, it answers the two questions you need
in order to rebuild the raw tapes it came from: at which FRAME does the picture
change, and which shots are the same camera as each other.

Three measurements, one decode pass:

  cut       a spike in frame-to-frame difference that is also a local maximum
            AND far above the local median. The last two conditions are what
            separates a cut from a fade: a fade is a sustained moderate
            difference with no peak, and this video ends on one.
  angle     shots cluster by their MEDIAN fingerprint, not their mean. The
            speaker moves; the room behind them does not, and the median is the
            room. Complete linkage, so two angles never chain together through
            a shot that happens to sit between them.
  re-split  a shot whose two halves have different medians was never one shot --
            the cut detector missed it because the angles look alike. Candidate
            split points are the sub-threshold peaks only, so a speaker standing
            up mid-shot (a real change, but a gradual one) cannot be mistaken
            for a cut.

Everything is in FRAME INDICES on the source's own grid. Seconds are derived
and never stored as the truth: at 24000/1001 a rounded second is a third of a
frame out, and the round-trip test scores joins to the frame.

  --list    print the threshold sweep and the shot table, write nothing
  --sheets  one contact sheet per detected angle, to eyeball the clustering
  (none)    write projects/<id>/<id>.shots.json

Invoke as:  python scripts/shot-detect.py --src projects/<id>/temp/program.mp4
"""
import sys, os, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from importlib import import_module  # noqa: E402

import numpy as np  # noqa: E402
import cv2  # noqa: E402

import _project  # noqa: E402

_thumbs = import_module("chapter-thumbs")   # hyphen: not importable by name

ROOT = _env.ROOT
ENV = _env.ENV

# Analysis resolution. Wide enough that two close-ups of different people in
# different corners of the room differ, small enough to stream a whole film.
AW = 128
SIG = 16

SEPARATION_FAILED = (
    "the fingerprints do not separate these angles: a shot resembles a "
    "DIFFERENT angle more than it resembles its own. No threshold fixes that, "
    "because the signal is not there.\n"
    "     What it usually means: every camera shares a background. This method "
    "reads the room behind the speaker, so a studio shooting four people "
    "against one black backdrop gives it nothing to read -- measured on two "
    "hour-long interviews, same-angle distance ran 0.44x the between-angle "
    "distance, where a usable margin is several times ABOVE 1.0. Masking the "
    "lower third and normalising contrast were both tried and neither helped.\n"
    "     Burned-in lower-third name cards do the same thing on a smaller "
    "scale: the same camera fingerprints as a new angle for as long as the "
    "card is up.\n"
    "     Look at --sheets and believe your eyes over the numbers. Telling "
    "these angles apart needs person identity, not appearance -- which this "
    "script does not do.")

PERSON_SEPARATION_FAILED = (
    "face identity does not separate these angles either: some shot's face "
    "sits closer to ANOTHER person's centroid than to its own. That usually "
    "means two genuinely similar faces, heavy occlusion, or a film whose "
    "'angles' are not people at all. Look at --sheets; if the clusters look "
    "right to your eyes, --force writes them and the numbers are recorded "
    "for the record.")

DEFAULT_FACE = {
    "detector": "models/face/face_detection_yunet_2023mar.onnx",
    "recognizer": "models/face/face_recognition_sface_2021dec.onnx",
    "samples": 5,          # frames sampled per shot; majority decides the count
    "width": 640,          # decode width for detection
    "score": 0.7,          # YuNet confidence floor
    "alike_face": 0.5,     # same person within this cosine distance. Measured:
                           # same-person max 0.24, different-person min 0.72,
                           # SFace's published match threshold ~0.64. 0.5 sits
                           # in the gap with margin on both sides.
    "layout_split": 0.06,  # same people, but framed differently: mean abs
                           # difference of the sorted (centre, width) face
                           # layout that splits one pairing into two cameras.
                           # Only honoured where the split is decisive.
    "min_id_face": 0.085,  # a face narrower than this fraction of the frame is
                           # too small to IDENTIFY and stays anonymous: on the
                           # wide of a four-person studio, per-face identities
                           # were noise and split one wide camera six ways.
    "face_second": 0.64,   # SFace's published same-person bar. A single-shot
                           # "person" inside it of a real person's centroid is
                           # that person mid-gesture -- an outstretched arm and
                           # a thrown-back head each cost a phantom camera --
                           # not a new face at the table.
    "cast_share": 0.03,    # a person on screen this much of the film is IN the
                           # show. A camera in a shoot films the people in that
                           # shoot, so an angle showing nobody from the cast is
                           # an insert however often it recurs -- which is how
                           # Queen and Joy Division stopped being cameras.
}

DEFAULT_DETECT = {
    "threshold": 0.055,   # mean abs frame difference, 0..1 grey
    "ratio": 4.0,         # ... and this many times the local median
    "window": 4,          # ... and the largest within +/- this many frames
    "median_win": 60,     # frames either side for the local median
    "alike": 0.055,       # two shots this close are the same angle
    "split": 0.070,       # ... and one shot whose halves differ by this is two
    "min_shot": 8,        # frames; shorter than this is a flash, not a shot
}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          env=ENV, **kw)


def hhmmss(t):
    return "%d:%05.2f" % (int(t) // 60, t % 60)


def probe(src):
    """Dimensions and the frame rate as an exact ratio.

    r_frame_rate, not avg_frame_rate: a slightly variable file averages to
    something that is not the grid it was shot on, and every frame index here
    is meant to land on that grid.
    """
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate",
               "-of", "json", src]).stdout
    s = json.loads(out)["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return {"width": int(s["width"]), "height": int(s["height"]),
            "fps_num": num, "fps_den": den, "fps": num / float(den)}


def scan(src, w, h, hwaccel=True):
    """One sequential decode. Returns (diff, sigs) with one row per frame.

    Streaming on purpose: an hour of film is 86k frames, and holding them all
    at analysis resolution is 800 MB. Only the 16x16 fingerprints are kept.
    """
    ah = int(round(AW * h / float(w))) // 2 * 2
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if hwaccel:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", src, "-vf", "scale=%d:%d" % (AW, ah),
            "-fps_mode", "passthrough", "-an",
            "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=ENV)
    nbytes = AW * ah
    diff, sigs, prev = [], [], None
    while True:
        buf = p.stdout.read(nbytes)
        if len(buf) < nbytes:
            break
        f = np.frombuffer(buf, np.uint8).reshape(ah, AW).astype(np.float32) / 255.0
        diff.append(0.0 if prev is None else float(np.abs(f - prev).mean()))
        sigs.append(cv2.resize(f, (SIG, SIG), interpolation=cv2.INTER_AREA))
        prev = f
    p.stdout.close()
    if p.wait() != 0 and hwaccel:
        return scan(src, w, h, hwaccel=False)     # no CUDA decoder for this codec
    return np.array(diff, dtype=np.float32), np.array(sigs, dtype=np.float32)


def local_median(diff, half):
    """Median of |frame difference| around each frame, as a motion floor."""
    n = len(diff)
    out = np.empty(n, dtype=np.float32)
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        out[i] = np.median(diff[lo:hi])
    return out


def peaks(diff, window):
    """Frames that are the strictly largest difference within +/- window."""
    n = len(diff)
    out = []
    for i in range(1, n):
        lo, hi = max(1, i - window), min(n, i + window + 1)
        if diff[i] >= diff[lo:hi].max() and diff[i] > 0:
            out.append(i)
    return out


def find_cuts(diff, d):
    """Frame indices where a new shot STARTS."""
    floor = local_median(diff, d["median_win"])
    cuts = []
    for i in peaks(diff, d["window"]):
        if diff[i] >= d["threshold"] and diff[i] >= d["ratio"] * max(floor[i], 1e-4):
            if not cuts or i - cuts[-1] >= d["min_shot"]:
                cuts.append(i)
    return cuts


def med_sig(sigs, a, b, trim=2):
    """The median fingerprint of a span, ignoring the frames next to its edges.

    A frame either side of a cut can be a blend, and one blended frame in a
    short shot drags the median towards the neighbouring angle.
    """
    lo, hi = a + trim, b - trim
    if hi - lo < 1:
        lo, hi = a, b
    return np.median(sigs[lo:hi], axis=0)


def distance(a, b):
    return float(np.abs(a - b).mean())


def resplit(sigs, diff, a, b, d):
    """Split [a, b) wherever it is really two angles, recursively.

    The candidate split points are the difference peaks that did NOT clear the
    cut threshold. That is the whole trick: a missed cut is still a sharp
    frame, just not a sharp enough one, whereas a speaker leaning out of frame
    changes the median without any sharp frame at all.
    """
    if b - a < 2 * d["min_shot"]:
        return [(a, b)]
    cand = [i for i in peaks(diff[a:b], d["window"])
            if d["min_shot"] <= i <= (b - a) - d["min_shot"]]
    best, best_at = 0.0, None
    for i in sorted(cand, key=lambda i: -diff[a + i])[:16]:
        s = distance(med_sig(sigs, a, a + i), med_sig(sigs, a + i, b))
        if s > best:
            best, best_at = s, a + i
    if best_at is None or best < d["split"]:
        return [(a, b)]
    return resplit(sigs, diff, a, best_at, d) + resplit(sigs, diff, best_at, b, d)


def cluster(shot_sigs, alike):
    """Group shots into angles. Complete linkage: merge only when EVERY pair
    across the two groups is alike, so a borderline shot cannot chain two
    distinct angles into one."""
    groups = [[i] for i in range(len(shot_sigs))]
    dist = {}
    for i in range(len(shot_sigs)):
        for j in range(i + 1, len(shot_sigs)):
            dist[(i, j)] = distance(shot_sigs[i], shot_sigs[j])

    def link(g, h):
        return max(dist[(min(x, y), max(x, y))] for x in g for y in h)

    while len(groups) > 1:
        pair, best = None, None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                v = link(groups[i], groups[j])
                if best is None or v < best:
                    pair, best = (i, j), v
        if best is None or best >= alike:
            break
        i, j = pair
        groups[i] = groups[i] + groups[j]
        groups.pop(j)
    # name the angles in order of first appearance
    groups.sort(key=lambda g: min(g))
    out = [None] * len(shot_sigs)
    for k, g in enumerate(groups):
        for i in g:
            out[i] = "cam%d" % (k + 1)
    return out, groups


def separation(shot_sigs, names):
    """Worst distance inside an angle vs best distance between two angles.

    One number that says whether the clustering was a decision or a coin toss:
    if the widest within-angle gap is larger than the closest between-angle
    gap, the fingerprints do not actually separate these cameras.
    """
    within, between = 0.0, None
    for i in range(len(shot_sigs)):
        for j in range(i + 1, len(shot_sigs)):
            v = distance(shot_sigs[i], shot_sigs[j])
            if names[i] == names[j]:
                within = max(within, v)
            elif between is None or v < between:
                between = v
    return within, between


def collect_frames(src, targets, w, h_src, w_src, hwaccel=True):
    """One streaming decode, yielding (frame_index, bgr) for each target.

    The same one-pass discipline as scan(): a thousand seeks into an hour of
    AV1 cost more than reading it once, and NVDEC reads it fast.
    """
    ah = int(round(w * h_src / float(w_src))) // 2 * 2
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if hwaccel:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", src, "-vf", "scale=%d:%d" % (w, ah),
            "-fps_mode", "passthrough", "-an",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=ENV)
    nbytes = w * ah * 3
    want = set(int(t) for t in targets)
    last = max(want) if want else -1
    got_any, i = False, 0
    while True:
        buf = p.stdout.read(nbytes)
        if len(buf) < nbytes or i > last:
            break
        if i in want:
            got_any = True
            yield i, np.frombuffer(buf, np.uint8).reshape(ah, w, 3).copy()
        i += 1
    p.stdout.close()
    p.kill()
    p.wait()
    if not got_any and hwaccel:
        for out in collect_frames(src, targets, w, h_src, w_src, hwaccel=False):
            yield out


def person_angles(src, spans, sigs, info, d, fc):
    """Cluster shots into angles by WHO is in frame, not what is behind them.

    This exists because the frame-fingerprint method reads the background, and
    a studio that puts every camera against the same black backdrop gives it
    nothing to read -- measured at 0.44x separation, where a usable margin is
    well above 1x. Detecting the person instead makes that the easy case: the
    less background there is, the more the frame IS the person.

    Instruments matter more than features here, and both cheap attempts were
    measured and rejected: Haar cascades missed one of four people in five of
    five samples, and a colour-torso fingerprint reached only 1.11x. YuNet
    detects 5/5 on every shot of the same film, and SFace identity embeddings
    separate at 3.0x (same-person max 0.24, different-person min 0.72) -- and
    corrected two hand-labelled shots in the process.

    Shots split into families by MAJORITY face count over sampled frames.

    ONE face -> cluster by face identity, AVERAGE linkage: pose stretches a
    person's own embeddings (an outstretched arm and a thrown-back head each
    earned themselves a phantom camera under complete linkage), and averaging
    absorbs the stretch the same way it absorbs a shouted word in the voice
    clustering. Within a person, a further frame-sig split is accepted only
    when it separates decisively -- the same person filmed by two cameras
    against different walls.

    TWO OR MORE faces -> cluster by WHICH PEOPLE are in the shot: every face
    is embedded and matched to the person centroids the one-face family just
    established, and shots group by their identity set, then split by face
    layout only where that is decisive. Clustered by frame fingerprint at
    first, and the same black backdrop that broke the close-ups shattered the
    two-shots into fifteen phantom angles of the same pairing.

    ZERO faces -> the shared `xtra` bin, and so does any angle showing nobody
    from the CAST -- the people who hold `cast_share` of the film between them.
    A camera in a shoot films the people in that shoot, so archive footage and
    music videos are inserts however often the editor returns to them: a
    culture show cut back to the same Queen clip repeatedly, and to vinyl
    animations, and to Joy Division, each about to become its own hour-long
    synthetic tape. The bin sits outside the separation guard because its
    members are not supposed to look alike, or like anyone.
    """
    det_path, rec_path = rel_model(fc["detector"]), rel_model(fc["recognizer"])
    for pth in (det_path, rec_path):
        if not os.path.exists(pth):
            sys.exit("no face model at %s -- see the video-multicam-switch "
                     "skill for the two curl commands" % _project.norm(pth))
    det = cv2.FaceDetectorYN_create(det_path, "", (fc["width"], fc["width"]),
                                    fc["score"])
    rec = cv2.FaceRecognizerSF_create(rec_path, "")

    k = int(fc["samples"])
    frame_shots, per_shot = {}, {i: [] for i in range(len(spans))}
    for i, (a, b) in enumerate(spans):
        lo, hi = a + 2, max(a + 2, b - 3)
        for t in sorted(set(np.linspace(lo, hi, k).astype(int).tolist())):
            frame_shots.setdefault(int(t), []).append(i)

    # Detections cache: the face pass is deterministic per (file, params), and
    # re-decoding an hour of AV1 to re-ask the same questions cost ten minutes
    # per grouping-logic iteration before this existed.
    import hashlib
    ck = "%s|%d|%d|%.3f" % (os.path.abspath(src), k, fc["width"], fc["score"])
    cpath = os.path.join(ROOT, "temp", "shot-detect-faces-%s.npz"
                         % hashlib.md5(ck.encode("utf-8")).hexdigest()[:12])
    cache = {}
    if os.path.exists(cpath) and os.path.getmtime(cpath) > os.path.getmtime(src):
        try:
            z = np.load(cpath, allow_pickle=True)
            if str(z["key"]) == ck:
                cache = z["faces"].item()
        except Exception:
            cache = {}
    missing = {t: s for t, s in frame_shots.items() if t not in cache}
    for idx, img in collect_frames(src, missing, fc["width"],
                                   info["height"], info["width"]):
        det.setInputSize((img.shape[1], img.shape[0]))
        _, faces = det.detect(img)
        found = []
        if faces is not None:
            for f in faces:
                e = rec.feature(rec.alignCrop(img, f)).ravel()
                nz = float(np.linalg.norm(e)) or 1.0
                found.append((float(f[0] + f[2] / 2) / img.shape[1],
                              float(f[2]) / img.shape[1], e / nz))
        cache[idx] = found
    if missing:
        os.makedirs(os.path.dirname(cpath), exist_ok=True)
        np.savez_compressed(cpath, key=ck,
                            faces=np.array(cache, dtype=object))
    for idx, shots_here in frame_shots.items():
        found = cache.get(idx, [])
        for i in shots_here:
            per_shot[i].append(found)

    majority, face_sig = {}, {}
    for i in range(len(spans)):
        counts = [len(fs) for fs in per_shot[i]] or [0]
        majority[i] = int(np.median(counts))
        embs = [fs[0][2] for fs in per_shot[i] if len(fs) == 1]
        if majority[i] == 1 and embs:
            s = np.median(np.array(embs), axis=0)
            face_sig[i] = s / (float(np.linalg.norm(s)) or 1.0)

    names = [None] * len(spans)
    order, next_id = {}, [0]

    def name_for(key, first_shot):
        if key not in order:
            order[key] = (min(first_shot), len(order))
        return key

    # one-face shots: identity clustering, average linkage
    persons = group_by_identity(face_sig, fc["alike_face"])

    def centroid(g):
        c = np.mean([face_sig[i] for i in g], axis=0)
        return c / (float(np.linalg.norm(c)) or 1.0)

    # second chance for pose outliers: a single-shot "person" within SFace's
    # published same-person bar of a real person is that person mid-gesture
    settled = [g for g in persons if len(g) > 1]
    if settled:
        cs = [centroid(g) for g in settled]
        rest = []
        for g in persons:
            if len(g) == 1:
                ds = [1.0 - float(face_sig[g[0]] @ c) for c in cs]
                j = int(np.argmin(ds))
                if ds[j] < fc["face_second"]:
                    settled[j].append(g[0])
                    continue
            if len(g) == 1:
                rest.append(g)
        persons = settled + rest
    cents = [centroid(g) for g in persons]
    # ...split a person across two cameras only if the frame sigs
    # separate decisively on their own
    cams, cam_person = [], []
    for pi, g in enumerate(persons):
        if len(g) >= 2:
            sub, _ = cluster([sigs_of(sigs, spans, i) for i in g], d["alike"])
            groups = {}
            for i, nm in zip(g, sub):
                groups.setdefault(nm, []).append(i)
            if len(groups) > 1:
                w_, b_ = _family_sep([sigs_of(sigs, spans, i) for i in g], sub)
                if b_ is not None and b_ > 2.0 * max(w_, 1e-6):
                    for sg in groups.values():
                        cams.append(sg)
                        cam_person.append(pi)
                    continue
        cams.append(g)
        cam_person.append(pi)
    for g in cams:
        key = ("p", min(g))
        for i in g:
            names[i] = key
        name_for(key, g)

    # multi-face shots: which people, then how they are framed
    def idset_and_layout(i):
        fam = majority[i]
        sets, lays = [], []
        for fs in per_shot[i]:
            if len(fs) != fam:
                continue
            byx = sorted(fs, key=lambda f: f[0])
            ids = []
            for cx, w, e in byx:
                if w < fc["min_id_face"]:
                    ids.append(-2)      # too small to identify: anonymous
                    continue
                ds = [1.0 - float(e @ c) for c in cents]
                j = int(np.argmin(ds)) if ds else -1
                ids.append(j if ds and ds[j] < fc["alike_face"] else -1)
            sets.append(tuple(sorted(ids)))
            lays.append([v for f in byx for v in (f[0], f[1])])
        if not sets:
            return None, None
        best = max(set(sets), key=sets.count)
        lay = np.median(np.array([l for s, l in zip(sets, lays)
                                  if s == best and len(l) == 2 * fam]), axis=0)
        return best, lay

    multis = {}
    for i in range(len(spans)):
        if majority[i] >= 2 and names[i] is None:
            ids, lay = idset_and_layout(i)
            if ids is not None:
                multis.setdefault((majority[i], ids), []).append((i, lay))
    for (fam, ids), members in sorted(multis.items()):
        # same people; split by framing only where framing is decisive
        lays = [l for _, l in members]
        subgroups = [[m for m, _ in members]]
        if len(members) >= 2:
            D = np.array([[float(np.abs(a - b).mean()) for b in lays]
                          for a in lays])
            groups = _agg_threshold(D, fc["layout_split"])
            if len(groups) > 1:
                w_ = max((D[np.ix_(g, g)].max() for g in groups if len(g) > 1),
                         default=0.0)
                b_ = min(D[np.ix_(g, h)].min()
                         for x, g in enumerate(groups)
                         for h in groups[x + 1:])
                if b_ > 2.0 * max(w_, 1e-6):
                    subgroups = [[members[m][0] for m in g] for g in groups]
        for g in subgroups:
            key = ("m%d" % fam, ids, min(g))
            for i in g:
                names[i] = key
            name_for(key, g)

    # no-face shots join the xtra bin outright
    for i in range(len(spans)):
        if majority[i] == 0 and names[i] is None:
            names[i] = ("xtra",)

    # leftovers (majority 1 but no clean embedding): nearest person by frame sig
    for i in range(len(spans)):
        if names[i] is None:
            done = [j for j in range(len(spans)) if names[j] is not None]
            j = min(done, key=lambda j: distance(sigs_of(sigs, spans, i),
                                                sigs_of(sigs, spans, j)))
            names[i] = names[j]

    # The b-roll bin: an angle showing nobody from the CAST. A camera in a
    # shoot films the people in that shoot, so archive footage and music
    # videos are inserts however often the editor returns to them -- a culture
    # show cut back to the same Queen clip repeatedly, which no rarity rule
    # could catch. Rarity WAS tried first and dropped: it binned a legitimate
    # wide the editor happened to use once, and rare is not the same as
    # inserted.
    n_total = spans[-1][1] if spans else 1

    # Screen time per PERSON, summed over however many cameras filmed them --
    # a person split across two cameras is still one member of the cast.
    seen = {}
    for gi, g in enumerate(cams):
        pi = cam_person[gi]
        seen[pi] = seen.get(pi, 0) + sum(spans[i][1] - spans[i][0] for i in g)
    cast = {pi for pi, fr in seen.items() if fr >= fc["cast_share"] * n_total}
    person_of = {("p", min(g)): cam_person[gi]
                 for gi, g in enumerate(cams) if g}
    for i in range(len(spans)):
        key = names[i]
        if key == ("xtra",):
            continue
        if key[0] == "p":
            if person_of.get(key) not in cast:
                names[i] = ("xtra",)
        elif key[0].startswith("m"):
            if not (set(key[1]) & cast):
                names[i] = ("xtra",)
    binned = {i for i in range(len(spans)) if names[i] == ("xtra",)}
    if binned:
        name_for(("xtra",), sorted(binned))

    ranked = sorted((k_ for k_ in order if any(n == k_ for n in names)),
                    key=lambda k_: order[k_])
    final = {k_: "cam%d" % (n + 1) for n, k_ in enumerate(ranked)}
    out = [final[k_] for k_ in names]

    # Identity separation, centroid-based: is every shot closer to its OWN
    # person than to any other? Pairwise was the first metric here and it was
    # wrong for this clustering: absorbing a mid-gesture outlier is the
    # correct move, and pairwise then reports the outlier's distance to its
    # farthest team-mate as "within", failing a clustering that is actually
    # unambiguous. What the decision uses is distance to centroids, so that
    # is what the guard measures. The bin is left out on both sides: its
    # members are not supposed to look alike, or like anyone.
    live_cams = [[i for i in g if i not in binned] for g in cams]
    group_cents = [centroid(g) for g in live_cams if g]
    own = {}
    gi = 0
    for g in live_cams:
        if not g:
            continue
        for i in g:
            own[i] = gi
        gi += 1
    within, between = 0.0, None
    for i, e in face_sig.items():
        if i in binned or i not in own:
            continue
        for gj, c in enumerate(group_cents):
            v = 1.0 - float(e @ c)
            if gj == own[i]:
                within = max(within, v)
            else:
                between = v if between is None else min(between, v)
    return out, majority, within, between


def _agg_threshold(D, thr):
    """Average-linkage agglomerative merge until nothing is closer than thr.

    Lance-Williams row update, same as auto-switch's voice clustering and for
    the same reason: each merge costs a row rewrite, not a recomputation.
    Returns groups of row indices, sorted by their smallest member.
    """
    m = len(D)
    if m == 0:
        return []
    D = D.astype(np.float64).copy()
    np.fill_diagonal(D, np.inf)
    size = np.ones(m)
    members = [[i] for i in range(m)]
    while True:
        f = int(np.argmin(D))
        i, j = divmod(f, m)
        if not np.isfinite(D[i, j]) or D[i, j] >= thr:
            break
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
        members[i] += members[j]
        members[j] = []
    return sorted((g for g in members if g), key=min)


def group_by_identity(face_sig, alike):
    """Average-linkage identity clustering on cosine distance.

    Average, not complete: pose stretches a person's own embeddings -- across
    229 shots of one film the same person reached 0.46 from himself while the
    closest two DIFFERENT people sat at 0.467, and under complete linkage an
    outstretched arm and a thrown-back head each earned a phantom camera.
    Averaging absorbs the stretch; two people merging would need their whole
    clusters to be near, which the 3.0x centroid margin rules out."""
    keys = sorted(face_sig)
    if not keys:
        return []
    E = np.array([face_sig[k] for k in keys])
    D = 1.0 - E @ E.T
    return [[keys[i] for i in g] for g in _agg_threshold(D, alike)]


def _family_sep(shot_sigs, names):
    within, between = 0.0, None
    for i in range(len(shot_sigs)):
        for j in range(i + 1, len(shot_sigs)):
            v = distance(shot_sigs[i], shot_sigs[j])
            if names[i] == names[j]:
                within = max(within, v)
            elif between is None or v < between:
                between = v
    return within, between


def sigs_of(sigs, spans, i):
    a, b = spans[i]
    return med_sig(sigs, a, b)


def rel_model(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def frame_png(src, idx, fps_num, fps_den, path, width=320):
    """One frame by index, addressed at the midpoint of its display slot."""
    t = (idx + 0.5) * fps_den / float(fps_num)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
         "-ss", "%.4f" % t, "-i", src, "-frames:v", "1",
         "-vf", "scale=%d:-2" % width, "-y", path])
    return path


def build_shots(diff, sigs, d):
    cuts = find_cuts(diff, d)
    bounds = [0] + cuts + [len(diff)]
    spans = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a >= d["min_shot"]:
            spans.extend(resplit(sigs, diff, a, b, d))
        elif spans:
            spans[-1] = (spans[-1][0], b)          # a flash belongs to its host
        else:
            spans.append((a, b))
    shot_sigs = [med_sig(sigs, a, b) for a, b in spans]
    names, _ = cluster(shot_sigs, d["alike"])
    return spans, shot_sigs, names


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True, help="the finished video to read")
    ap.add_argument("--id", help="project id; default: the folder under projects/")
    ap.add_argument("--out", help="default projects/<id>/<id>.shots.json")
    ap.add_argument("--list", action="store_true",
                    help="print the sweep and the shot table, write nothing")
    ap.add_argument("--sheets", action="store_true",
                    help="write one contact sheet per angle into temp/")
    ap.add_argument("--json", action="store_true", help="print the document")
    ap.add_argument("--force", action="store_true",
                    help="write the shot list even if the angles do not separate")
    ap.add_argument("--angle-by", choices=("frame", "person", "auto"),
                    default="auto",
                    help="how angles are identified: frame fingerprints, face "
                         "identity, or frame-first-then-person (default)")
    for k, v in DEFAULT_DETECT.items():
        ap.add_argument("--" + k.replace("_", "-"), type=type(v), default=None,
                        help="default %s" % v)
    args = ap.parse_args()

    d = dict(DEFAULT_DETECT)
    for k in DEFAULT_DETECT:
        v = getattr(args, k, None)
        if v is not None:
            d[k] = v

    src = args.src if os.path.isabs(args.src) else os.path.join(ROOT, args.src)
    if not os.path.exists(src):
        sys.exit("no such file: %s" % args.src)
    pdir = _project.find_project_dir(src)
    pid = args.id or (os.path.basename(pdir) if pdir else
                      os.path.splitext(os.path.basename(src))[0])

    info = probe(src)
    diff, sigs = scan(src, info["width"], info["height"])
    n = len(diff)
    if n < 2:
        sys.exit("decoded %d frames from %s" % (n, args.src))
    fps = info["fps"]

    spans, shot_sigs, names = build_shots(diff, sigs, d)
    within, between = separation(shot_sigs, names)
    frame_failed = between is not None and within >= between

    angle_by = "frame"
    majority = None
    if args.angle_by == "person" or (args.angle_by == "auto" and frame_failed):
        if args.angle_by == "auto":
            print("frame fingerprints do not separate these angles (within "
                  "%.4f >= between %.4f) -- switching to face identity"
                  % (within, between))
        names, majority, within, between = person_angles(
            src, spans, sigs, info, d, DEFAULT_FACE)
        angle_by = "person"
        print("angles by face identity: %d angles; identity separation "
              "within %.3f, between %s"
              % (len(set(names)), within,
                 "n/a" if between is None else "%.3f" % between))
    failed = between is not None and within >= between

    if args.list:
        print("%s  %d frames  %.4f fps (%d/%d)  %s"
              % (args.src, n, fps, info["fps_num"], info["fps_den"],
                 hhmmss(n / fps)))
        print("\nthreshold sweep (ratio %.1f, window %d) -- pick a plateau:"
              % (d["ratio"], d["window"]))
        print("  thresh   cuts  shots  angles")
        for t in (0.030, 0.040, 0.050, 0.055, 0.060, 0.070, 0.090, 0.120):
            dd = dict(d, threshold=t)
            sp, ss, nm = build_shots(diff, sigs, dd)
            print("  %6.3f  %5d  %5d  %6d%s"
                  % (t, len(find_cuts(diff, dd)), len(sp), len(set(nm)),
                     "   <- current" if abs(t - d["threshold"]) < 1e-9 else ""))
        print("\nangle separation (%s): worst within %.4f, closest between %s"
              % (angle_by, within,
                 "n/a" if between is None else "%.4f" % between))
        if failed:
            print("  !! " + SEPARATION_FAILED)

    print("\n  #  cam    start      end     len  frames        peak")
    for i, ((a, b), nm) in enumerate(zip(spans, names)):
        print("  %2d  %-5s %8s %8s %7.2f  %5d-%-5d  %8.4f"
              % (i, nm, hhmmss(a / fps), hhmmss(b / fps), (b - a) / fps,
                 a, b, diff[a] if a else 0.0))
    by = {}
    for (a, b), nm in zip(spans, names):
        e = by.setdefault(nm, [0, 0])
        e[0] += 1
        e[1] += b - a
    print("")
    for nm in sorted(by):
        print("  %-5s %2d shots  %6d frames  %7.2fs  %4.1f%%"
              % (nm, by[nm][0], by[nm][1], by[nm][1] / fps,
                 100.0 * by[nm][1] / n))

    doc = {
        "_comment": "Shots and angles read back off a finished video by "
                    "scripts/shot-detect.py. Frame indices on the source's "
                    "own grid; end is exclusive. seconds = frame*fps_den/fps_num.",
        "source": _project.norm(src),
        "width": info["width"], "height": info["height"],
        "fps_num": info["fps_num"], "fps_den": info["fps_den"], "fps": fps,
        "n_frames": n,
        "detect": d,
        "angle_by": angle_by,
        "face": DEFAULT_FACE if angle_by == "person" else None,
        "separation": {"method": angle_by, "within": round(within, 5),
                       "between": None if between is None else round(between, 5)},
        "cuts": [a for a, _ in spans[1:]],
        "shots": [{"start": a, "end": b, "camera": nm}
                  for (a, b), nm in zip(spans, names)],
        "cameras": [{"id": nm,
                     "n_shots": sum(1 for x in names if x == nm),
                     "frames": sum(b - a for (a, b), x in zip(spans, names)
                                   if x == nm)}
                    for nm in sorted(set(names))],
    }

    if args.sheets:
        tmp = os.path.join(ROOT, "temp", "shot-detect-%s" % pid)
        os.makedirs(tmp, exist_ok=True)
        from PIL import Image
        for nm in sorted(set(names)):
            imgs, labs = [], []
            for i, ((a, b), x) in enumerate(zip(spans, names)):
                if x != nm:
                    continue
                png = os.path.join(tmp, "%s-shot%02d.png" % (nm, i))
                frame_png(src, (a + b) // 2, info["fps_num"], info["fps_den"], png)
                imgs.append(Image.open(png).copy())
                labs.append("#%d %s %s" % (i, hhmmss(a / fps), hhmmss(b / fps)))
            out = _thumbs.contact_sheet(imgs, labs, os.path.join(tmp, "%s.png" % nm))
            print("sheet: %s" % _project.norm(out))

    if args.json:
        print(json.dumps(doc, indent=2))

    if args.list:
        return

    # Refuse to hand on a shot list whose angles do not separate. Downstream,
    # split-cameras.py builds one full-length tape per angle: on an hour-long
    # interview that mis-clustered into 55, this check is the difference
    # between a warning and fifty-five hours of encoding nobody wanted.
    if failed and not args.force:
        print("\n!! %s" % (PERSON_SEPARATION_FAILED if angle_by == "person"
                           else SEPARATION_FAILED))
        sys.exit("refusing to write a shot list with %d angles that do not "
                 "separate -- pass --force if you know better" % len(set(names)))

    out = args.out or (os.path.join(pdir, "%s.shots.json" % pid) if pdir
                       else os.path.join(ROOT, "temp", "%s.shots.json" % pid))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print("\nwrote %s -- %d shots, %d angles"
          % (_project.norm(out), len(spans), len(set(names))))
    _project.record(pid, "shot-detect", script=__file__, argv=sys.argv[1:],
                    note="%d shots, %d angles, %d cuts from %s"
                         % (len(spans), len(set(names)), len(doc["cuts"]),
                            _project.norm(src)))


if __name__ == "__main__":
    main()
