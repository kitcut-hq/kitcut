#!/usr/bin/env python
"""Word-level transcription with faster-whisper (local, offline, GPU).

MUST be invoked as:  python scripts/transcribe-words.py ...

Why: this machine has a global PYTHONPATH pointing at another Python install's
site-packages, which gets prepended to this interpreter's sys.path and breaks
`import faster_whisper`. sys.path is frozen at interpreter startup, so scrubbing
os.environ in-process does NOT help. -E is the only invocation-level fix. But -E
also disables PYTHONUTF8/PYTHONIOENCODING, and this console is cp1252, so
-X utf8 is required too or any non-ASCII log line raises UnicodeEncodeError.

The header below makes the script survive a bare `python script.py` anyway.

Invoke as:  python scripts/transcribe-words.py <audio.wav> --out <id>.words.json
"""
import sys, os, json, argparse, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

# _env handles the poisoned path and UTF-8 stdio (layers 1 and 2).
# --- ctranslate2 bundles its own libiomp5md.dll
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

# --- CUDA DLLs. ctranslate2 bundles cudnn64_9.dll but NOT cuBLAS, so
# GPU inference dies with "Library cublas64_12.dll is not found". The pip
# nvidia-* wheels drop the DLLs under site-packages/nvidia/<pkg>/bin, and since
# Python 3.8 Windows does not search PATH for extension-module dependencies --
# each directory must be registered explicitly.
# Search EVERY package root, not just purelib: a Microsoft Store Python puts pip
# installs in the user site, so looking only at purelib finds nothing and CUDA
# degrades to CPU silently.
_own = _env.site_roots()
_dirs = []
for _root in sorted(_own):
    _nv = os.path.join(_root, "nvidia")
    if os.path.isdir(_nv):
        _dirs += [os.path.join(_nv, p, "bin") for p in sorted(os.listdir(_nv))]
_dirs = [d for d in _dirs if os.path.isdir(d)]
if _dirs:
    for _bin in _dirs:
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_bin)
            except OSError:
                pass
    # add_dll_directory alone is NOT sufficient: ctranslate2 loads cuBLAS lazily
    # at first encode via a plain LoadLibrary, which uses the standard search
    # order (PATH) and ignores directories registered for altered-search loads.
    os.environ["PATH"] = os.pathsep.join(_dirs) + os.pathsep + os.environ.get("PATH", "")

from faster_whisper import WhisperModel
import faster_whisper, ctranslate2

_fw = os.path.normcase(os.path.abspath(faster_whisper.__file__))
if not any(_fw.startswith(p) for p in _own):
    sys.exit("FATAL: faster_whisper resolved outside this interpreter's "
             "site-packages (%s) -- a stale PYTHONPATH is shadowing it. "
             "Invoke as: python" % _fw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw-out", default=None)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--compute-type", default="int8_float16")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--language", default=None,
                    help="ISO code; omit to autodetect. Do NOT default this to a "
                         "language -- a wrong forced language produces a fluent "
                         "transcript of the wrong words with no error anywhere.")
    ap.add_argument("--beam-size", type=int, default=5)
    args = ap.parse_args()

    print(f"faster-whisper {faster_whisper.__version__} / ctranslate2 {ctranslate2.__version__}")
    t0 = time.time()

    # Fallback ladder. CUDA failures are LAZY: model load can succeed and the
    # first encode still die (that is exactly how the missing-cublas failure
    # presented), so each rung must survive both load and full inference.
    ladder = [(args.device, args.compute_type)]
    if args.device == "cuda":
        if args.compute_type != "int8":
            ladder.append(("cuda", "int8"))
        ladder.append(("cpu", "int8"))

    last_err = None
    for device, ctype in ladder:
        try:
            print(f"loading {args.model} ({ctype}) on {device} ...", flush=True)
            model = WhisperModel(args.model, device=device, device_index=0,
                                 compute_type=ctype, local_files_only=True,
                                 cpu_threads=8, num_workers=1)
            print(f"  loaded in {time.time()-t0:.1f}s", flush=True)
            info, words, raw_segs = transcribe_once(model, args, t0)
            args.compute_type = ctype        # record what actually ran
            break
        except (RuntimeError, OSError) as e:
            msg = str(e).lower()
            if device != "cpu" and any(k in msg for k in
                                       ("cuda", "cublas", "cudnn", "out of memory", "library")):
                print(f"  {device}/{ctype} failed ({e}); falling back ...", flush=True)
                model = None                 # release VRAM before the next rung
                last_err = e
                continue
            raise
    else:
        sys.exit(f"FATAL: all backends failed; last error: {last_err}")

    write_output(args, info, words, raw_segs, t0)


def transcribe_once(model, args, t0):
    segments, info = model.transcribe(
        args.audio,
        language=args.language, task="transcribe",
        beam_size=args.beam_size, best_of=args.beam_size, patience=1.0,
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        # A 24-min monologue is the classic setup for a Whisper repetition loop.
        # Conditioning off caps the blast radius at one window.
        condition_on_previous_text=False,
        repetition_penalty=1.05,
        word_timestamps=True,
        hallucination_silence_threshold=2.0,
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.5,
            min_speech_duration_ms=100,
            # shipped defaults (2000ms silence / inf max) would make the whole
            # monologue ONE region: no resync points, unbounded DTW drift
            max_speech_duration_s=20,
            min_silence_duration_ms=500,
            speech_pad_ms=200,
        ),
    )

    print(f"detected: {info.language} p={info.language_probability:.3f}", flush=True)

    words, raw_segs = [], []
    last_report = 0.0
    for seg in segments:
        raw_segs.append(dict(id=seg.id, start=seg.start, end=seg.end, text=seg.text,
                             avg_logprob=seg.avg_logprob, no_speech_prob=seg.no_speech_prob,
                             compression_ratio=seg.compression_ratio, temperature=seg.temperature))
        for w in (seg.words or []):
            words.append(dict(text=w.word.strip(), start=float(w.start),
                              end=float(w.end), duration=float(w.end - w.start),
                              probability=float(w.probability)))
        if seg.end - last_report >= 60:
            last_report = seg.end
            print(f"  {seg.end/60:5.1f} min | {len(words)} words | {time.time()-t0:.0f}s elapsed", flush=True)
    return info, words, raw_segs


def write_output(args, info, words, raw_segs, t0):
    out = dict(file=args.audio, duration=float(info.duration), language=info.language,
               language_probability=float(info.language_probability),
               model=args.model, compute_type=args.compute_type,
               text=" ".join(w["text"] for w in words), words=words)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    if args.raw_out:
        with open(args.raw_out, "w", encoding="utf-8") as f:
            json.dump(dict(segments=raw_segs), f, ensure_ascii=False, indent=1)

    print(f"DONE {len(words)} words -> {args.out} in {time.time()-t0:.0f}s")
    if words:
        print(f"last word ends at {words[-1]['end']:.1f}s (audio {info.duration:.1f}s)")


if __name__ == "__main__":
    main()
