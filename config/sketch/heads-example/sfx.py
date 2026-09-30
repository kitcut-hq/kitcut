"""Write sfx.json for the brothers' front page from the voice timeline, on the words film.js cues.

The page's pieces landing at the start get a paper rustle and soft landings; the stamp gets its
thunk on the end of "seconds", read from audio/vo/timeline.json, so a re-recorded line moves the
sound with the picture. Run after sketch-vo.py: python projects/<id>/sfx.py
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "audio", "vo", "timeline.json"), encoding="utf-8") as f:
        lines = json.load(f)["lines"]

    def norm(s):
        return re.sub(r"[^\w$]", "", s.lower().replace("'", ""))

    def word_end(li, word):
        return [x["e"] for x in lines[li]["words"] if norm(x["text"]) == norm(word)][0]

    cues = [
        {"t": 0.0, "fx": "crinkle", "db": -27, "args": {"sec": 0.3, "seed": 1}},
        # the headline slaps down (in at -0.12 s, 0.28 s long); the photographs drop (0.5 s)
        {"t": 0.16, "fx": "thunk", "db": -25, "args": {"sec": 0.3}},
        {"t": 0.25, "fx": "thunk", "db": -28, "pan": -0.3, "args": {"sec": 0.25}},
        {"t": 0.45, "fx": "thunk", "db": -28, "pan": 0.3, "args": {"sec": 0.25}},
    ]
    t = word_end(2, "seconds")
    cues += [
        {"t": round(t, 3), "fx": "thunk", "db": -18, "pan": 0.35, "args": {"sec": 0.35}},
        {
            "t": round(t, 3),
            "fx": "click",
            "db": -28,
            "pan": 0.35,
            "args": {"sec": 0.01, "lo": 900, "hi": 3000},
        },
    ]
    with open(os.path.join(HERE, "sfx.json"), "w", encoding="utf-8") as f:
        json.dump(cues, f, indent=1)
    print("sfx.json: %d cues, the stamp at %.2fs" % (len(cues), t))


if __name__ == "__main__":
    main()
