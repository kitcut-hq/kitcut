"""A narration written word for word (scripts/_narration.py, validate.narration_script): vo.json
held to the person's script every time it is saved, without Claude and without recording:
python studio/test_verbatim.py

The Anthropic IPO pilot (2026-10-21) dropped one of its script's lines, and the full film split one
at the voice's 300-character limit; both shapes are here, with a pilot of the first lines (which
must pass) and a translation (which is another narration, not a broken one).
"""

import os
import sys
import json
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-verbatim-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402 -- imports _env first
import validate  # noqa: E402
from film import Film  # noqa: E402

SCRIPT = """# Running order

The narration is word for word.

## OPENING

- L01. *0.0 s: the strap and the headline band, "RESEARCH" at its left.*
  "Anthropic could file to go public as soon as Friday, at a price as high as two trillion."
- L02. *upload2 comes forward; underline "$16.3bn".*
  "Its draft filing shows sixteen point three billion dollars of revenue in six months."
- L03. *Three cards counting up.*
  "One of those numbers is not what it looks like. Another is bigger than it looks."

## 1 · THE PRICE

- **L04**: *Chart C1 builds.*
  "At two trillion dollars, it would be the eighth most valuable listed company on Earth."
- L05. *Chart C2 draws.*
  "In March of last year, investors valued it at sixty-one and a half billion dollars."

Stop there. The last two seconds: the small "Made with KitCut" mark.
"""
LINES = [
    "Anthropic could file to go public as soon as Friday, at a price as high as two trillion.",
    "Its draft filing shows sixteen point three billion dollars of revenue in six months.",
    "One of those numbers is not what it looks like. Another is bigger than it looks.",
    "At two trillion dollars, it would be the eighth most valuable listed company on Earth.",
    "In March of last year, investors valued it at sixty-one and a half billion dollars.",
]


def put_vo(film, lines):
    with open(film.path("vo.json"), "w", encoding="utf-8") as f:
        json.dump({"voice": validate.VOICES[0], "lines": [{"text": t} for t in lines]}, f)


def main():
    fails = []

    def check(ok, what, detail=""):
        print(("ok   " if ok else "FAIL ") + what + ("" if ok else "  " + str(detail)))
        if not ok:
            fails.append(what)

    script = validate.N.script_lines(SCRIPT)
    check([i for i, _ in script] == ["L01", "L02", "L03", "L04", "L05"], "five lines read", script)
    check(script[0][1] == LINES[0], "the spoken words, not the stage direction's quotes", script[0])
    check(script[4][1] == LINES[4], "a paragraph after the last line is not part of it", script[4])
    check(not validate.N.script_lines("L01 is a laptop model.\nNothing else."), "prose is not one")

    doc = os.path.join(HOME, "script.md")
    with open(doc, "w", encoding="utf-8") as f:
        f.write(SCRIPT)
    notes = os.path.join(HOME, "notes.md")
    with open(notes, "w", encoding="utf-8") as f:
        f.write("Facts: the filing is a draft.\n")
    film = Film.create(
        "A research film",
        60,
        "collage",
        client="u:alice",
        attachments=[agent.local_attachment(notes), agent.local_attachment(doc)],
    )
    got = validate.narration_script(film)
    check(got and got[0] == "Document 2", "the script is found among the documents", got)
    note = agent.attached_note(film)
    check("Document 2 is a narration written word for word: 5 lines, L01 to L05" in note, "said")
    plain = Film.create(
        "notes only", 60, "collage", client="u:alice", attachments=[agent.local_attachment(notes)]
    )
    check(validate.narration_script(plain) is None, "a film with no script has none")
    check("word for word" not in agent.attached_note(plain), "and is told nothing of one")

    put_vo(film, LINES)
    check(validate.problems(film, "vo.json") == [], "word for word passes")
    check(
        "all 5 lines" in validate.verbatim_note(film),
        "and is told so",
        validate.verbatim_note(film),
    )

    punct = [t.replace(",", "").replace("sixty-one", "sixty one").upper() for t in LINES]
    put_vo(film, punct)
    check(validate.problems(film, "vo.json") == [], "case, commas and dashes are the voice's")

    put_vo(film, LINES[:1] + LINES[2:])
    bad = validate.problems(film, "vo.json")
    check(any("L02 is missing" in b for b in bad), "a dropped line is named", bad)

    put_vo(film, LINES[:3] + [LINES[3].replace("eighth", "8th")] + LINES[4:])
    bad = validate.problems(film, "vo.json")
    check(any("L04 says" in b and '"8th"' in b for b in bad), "a reworded line is named", bad)

    put_vo(film, LINES[:2] + ["And that is huge.", *LINES[2:]])
    bad = validate.problems(film, "vo.json")
    check(any('adds "and that is huge"' in b for b in bad), "an added line is named", bad)

    put_vo(film, [LINES[0], LINES[1] + " " + LINES[2], *LINES[3:]])
    bad = validate.problems(film, "vo.json")
    check(any("joins L02 and L03" in b for b in bad), "two lines in one are named", bad)

    split = LINES[2].split(". ")
    put_vo(film, LINES[:2] + [split[0] + ".", split[1]] + LINES[3:])
    check(validate.problems(film, "vo.json") == [], "one line said as two passes")

    put_vo(film, LINES[:3])
    check(validate.problems(film, "vo.json") == [], "a pilot of the first lines passes")
    note = validate.verbatim_note(film)
    check("L01 to L03" in note and "L04, L05 are not in this film" in note, "and is told", note)

    put_vo(film, ["Anthropic може подати документи вже в пятницю.", "Ціна до двох трильйонів."])
    check(validate.problems(film, "vo.json") == [], "a translation is another narration")
    check("does not say Document 2" in validate.verbatim_note(film), "and is asked about")

    print("\n%d failed" % len(fails) if fails else "\nall passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
