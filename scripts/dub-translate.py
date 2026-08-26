#!/usr/bin/env python
"""Translate a clip line by line, under a per-line time budget.

A dub fails in two different ways and this module exists to head off both.
Translate the whole clip as one block and you get good English that no longer
lines up with the mouth. Translate each fragment in isolation and you get
sentences that fit but read like a phrasebook, because the translator cannot see
what came before.

So the model is shown the whole passage for context and asked to return it
already split across the numbered slots, each with the number of seconds it has
to fit. Every slot also gets a `tight` variant -- a shorter paraphrase -- which
the fitter can fall back on when the natural line simply will not fit without
speeding the voice up past where it sounds human. Asking for both up front costs
nothing and avoids a second round trip.

Engines:
  claude  shells out to the Claude Code CLI. No API key, which is the point.
  openai  needs OPENAI_API_KEY.
  manual  reads a JSON array you (or an agent) wrote by hand.

    python scripts/dub-translate.py --plan outputs/dub/01.plan.json \
        --out outputs/dub/01.translation.json
"""
import sys, os, json, argparse, subprocess, re, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

ENV = _env.ENV
BATCH = 20          # slots per request: enough context, short enough to stay accurate

PROMPT = """You are dubbing a %(src)s video into %(dst)s.

Here is the whole passage, for context. Do not translate it as one block:

%(context)s

Now translate it into natural spoken %(dst)s, split across the numbered slots
below. Each slot is a fixed-length hole in the original audio. The %(dst)s for a
slot has to be comfortably sayable in that many seconds at a normal
conversational pace, because it will be spoken into exactly that gap.

The word count given for each slot is a target to hit, not a ceiling. A line
that comes in well under it leaves the dub silent while the speaker's mouth is
still moving, which looks worse than a line that is slightly too long. Use the
whole slot.

Rules:
- Keep the speaker's register: casual, first person, talking straight to camera.
- Keep each slot's meaning inside that slot. Do not move content between slots.
- Slots are spoken back to back. If a slot is a sentence fragment, leave it a
  fragment -- it will join up with its neighbours.
- Prefer short, common words. Use contractions; they buy you time.
- Numbers, brand names and place names stay as they are.
- No stage directions, no commentary, no surrounding quotation marks.
- "tight" is a shorter paraphrase of the same slot, roughly a quarter shorter,
  still natural and still complete on its own. It is the fallback when the
  main line runs long.

Slots:
%(slots)s

Reply with ONLY a JSON array, no prose and no code fence:
[{"i": 1, "text": "...", "tight": "..."}, ...]
"""


def build_prompt(units, context, src="Ukrainian", dst="English", wps=3.2):
    slots = []
    for u in units:
        slots.append('[%d] %.1fs (aim for about %d words): %s'
                     % (u["i"], u["dur"], max(2, int(round(u["dur"] * wps))), u["text"]))
    return PROMPT % {"src": src, "dst": dst, "context": context,
                     "slots": "\n".join(slots)}


def _extract_json(s):
    """Pull the JSON array out of a reply that may be fenced or chatty."""
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.M).strip()
    a, b = s.find("["), s.rfind("]")
    if a < 0 or b < a:
        raise ValueError("no JSON array in reply: %s" % s[:200])
    return json.loads(s[a:b + 1])


def _via_claude(prompt, model=None):
    exe = shutil.which("claude")
    if not exe:
        sys.exit("the claude CLI is not on PATH -- use --engine manual or openai")
    cmd = [exe, "-p"]
    if model:
        cmd += ["--model", model]
    # the prompt goes on stdin, not argv: Windows caps a command line at ~32k
    # characters and a long clip blows straight past that
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       encoding="utf-8", env=ENV)
    if r.returncode:
        sys.exit("claude CLI failed: %s" % (r.stderr or r.stdout)[:400])
    return _extract_json(r.stdout)


def _via_openai(prompt, model="gpt-4o"):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set -- use --engine claude or manual")
    import httpx
    r = httpx.post("https://api.openai.com/v1/chat/completions",
                   headers={"Authorization": "Bearer %s" % key},
                   json={"model": model, "temperature": 0.3,
                         "messages": [{"role": "user", "content": prompt}]},
                   timeout=180)
    r.raise_for_status()
    return _extract_json(r.json()["choices"][0]["message"]["content"])


def translate(units, context, engine="claude", src="Ukrainian", dst="English",
              wps=3.2, model=None, verbose=True):
    """Returns [{i, text, tight}] covering every unit, in order."""
    out = {}
    for k in range(0, len(units), BATCH):
        batch = units[k:k + BATCH]
        prompt = build_prompt(batch, context, src, dst, wps)
        if verbose:
            print("  translating slots %d-%d via %s ..."
                  % (batch[0]["i"], batch[-1]["i"], engine), flush=True)
        rows = _via_claude(prompt, model) if engine == "claude" else \
            _via_openai(prompt, model or "gpt-4o")
        for r in rows:
            try:
                i = int(r["i"])
            except (KeyError, TypeError, ValueError):
                continue
            out[i] = {"text": str(r.get("text", "")).strip(),
                      "tight": str(r.get("tight", "") or r.get("text", "")).strip()}
    missing = [u["i"] for u in units if not out.get(u["i"], {}).get("text")]
    if missing:
        sys.exit("translation is missing slots: %s" % missing)
    return [dict(out[u["i"]], i=u["i"]) for u in units]


RETUNE = """You are adjusting the length of individual lines in a %(dst)s dub.

Each line below was spoken aloud and timed. It has to fill a slot of a given
length. Rewrite ONLY these lines so they take the right amount of time.

Context -- this is the whole passage the lines come from, in %(dst)s, so you can
keep the voice consistent:

%(context)s

For each line you are told the slot length, how long the current wording
actually took when spoken, and the original %(src)s it has to convey.

- LONGER: the current wording leaves dead air under a talking face. Expand it to
  about the target word count using fuller, more natural phrasing, and restore
  any nuance from the %(src)s that the short version dropped. Do not invent facts
  that are not in the %(src)s.
- SHORTER: cut to about the target word count, keeping the meaning.

Keep the register casual and first person. Keep each line's meaning inside that
line. No commentary.

Lines:
%(slots)s

Reply with ONLY a JSON array, no prose and no code fence:
[{"i": 1, "text": "...", "tight": "..."}, ...]
"""


def retune(units, fits, rows, context, engine="claude", src="Ukrainian",
           dst="English", wps=3.2, model=None, short=0.85, verbose=True):
    """Re-ask for only the lines that measurement showed do not fit.

    Returns a new rows list. The first pass is a guess at how long a sentence
    takes to say; this is the correction after actually saying it.
    """
    by_i = {int(r["i"]): dict(r) for r in rows}
    todo = []
    for u, f in zip(units, fits):
        want = None
        if f["final"] > u["hard"] + 0.05:
            want = "SHORTER"
        elif f["final"] < u["dur"] * short:
            want = "LONGER"
        if want:
            todo.append((u, f, want))
    if not todo:
        return rows, 0

    slots = []
    for u, f, want in todo:
        target = max(2, int(round(u["dur"] * wps)))
        slots.append("[%d] %s -- slot %.1fs, spoken it took %.1fs, aim for about "
                     "%d words.\n     current: %s\n     %s: %s"
                     % (u["i"], want, u["dur"], f["final"], target,
                        by_i[u["i"]]["text"], src, u["text"]))
    prompt = RETUNE % {"src": src, "dst": dst, "context": context,
                       "slots": "\n".join(slots)}
    if verbose:
        print("  retuning %d slot(s): %s"
              % (len(todo), ", ".join(str(u["i"]) for u, _, _ in todo)), flush=True)
    fixed = _via_claude(prompt, model) if engine == "claude" else         _via_openai(prompt, model or "gpt-4o")
    n = 0
    for r in fixed:
        try:
            i = int(r["i"])
        except (KeyError, TypeError, ValueError):
            continue
        if i in by_i and str(r.get("text", "")).strip():
            by_i[i]["text"] = str(r["text"]).strip()
            by_i[i]["tight"] = str(r.get("tight") or r["text"]).strip()
            n += 1
    return [by_i[int(r["i"])] for r in rows], n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="dub plan json from dub-clips.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="claude", choices=["claude", "openai", "manual"])
    ap.add_argument("--model")
    ap.add_argument("--from-json", help="manual engine: the array to use")
    ap.add_argument("--print-prompt", action="store_true",
                    help="dump the prompt and exit, to paste somewhere else")
    ap.add_argument("--src-lang", default="Ukrainian")
    ap.add_argument("--dst-lang", default="English")
    ap.add_argument("--words-per-sec", type=float, default=3.2)
    args = ap.parse_args()

    plan = json.load(open(args.plan, encoding="utf-8"))
    units, context = plan["units"], plan["context"]

    if args.print_prompt:
        print(build_prompt(units, context, args.src_lang, args.dst_lang,
                           args.words_per_sec))
        return
    if args.engine == "manual":
        if not args.from_json:
            sys.exit("--engine manual needs --from-json")
        rows = json.load(open(args.from_json, encoding="utf-8"))
        by_i = {int(r["i"]): r for r in rows}
        result = [{"i": u["i"], "text": by_i[u["i"]]["text"].strip(),
                   "tight": (by_i[u["i"]].get("tight") or by_i[u["i"]]["text"]).strip()}
                  for u in units]
    else:
        result = translate(units, context, args.engine, args.src_lang,
                           args.dst_lang, args.words_per_sec, args.model)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(result, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("wrote %s (%d slots)" % (args.out, len(result)))


if __name__ == "__main__":
    main()
