"""who.py: who is on screen and who is speaking, from the probe's report and the narration."""

import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import who  # noqa: E402

bad = []


def check(ok, what):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        bad.append(what)


check(
    who.runs([0.0, 0.25, 0.5, 2.0, 2.25, 9.0], 0.25) == [[0.0, 0.75], [2.0, 2.5]],
    "moments make stretches; a lone flicker is dropped",
)
check(who.runs([0.0, 0.25, 0.75], 0.25) == [[0.0, 1.0]], "a short gap does not split a stretch")

rep = {
    "step": 0.25,
    "keys": ["rusty.stand", "graypaw.sit", "forest.draw", "rusty.blink"],
    "frames": [
        {
            "t": 0.0,
            "s": [
                [0, 100, 200, 300, 600, 9, 1, 1, 0, 0, 1, 0, -1],
                [2, 0, 0, 1000, 1000, 9, 1, 1, 0, 0, 1, 0, -1],
            ],
        },
        {
            "t": 0.25,
            "s": [
                [0, 100, 200, 300, 600, 9, 1, 1, 0, 0, 1, 0, -1],
                [1, 1200, 200, 1400, 600, 9, 1, 1, 0, 0, 1, 0, -1],
            ],
        },
        {
            "t": 0.5,
            "s": [
                [3, 100, 200, 300, 600, 9, 1, 1, 0, 0, 1, 0, -1],
                [1, 600, 200, 800, 600, 9, 1, 1, 0, 0, 0.1, 0, -1],
            ],
        },
        {
            "t": 0.75,
            "s": [
                [1, 600, 200, 800, 600, 9, 1, 1, 0, 0, 1, 0, -1],
                [1, 0, 0, 50, 50, 9, 1, 1, 0, 0, 1, 1, -1],
            ],
        },
        {"t": 1.0, "s": [[1, 600, 200, 800, 600, 9, 1, 1, 0, 0, 1, 0, -1]]},
    ],
}
on = who.on_screen(rep, {"rusty", "graypaw", "forest"}, {"forest"})
check(
    on == {"rusty": [[0.0, 0.75]], "graypaw": [[0.75, 1.25]]},
    "on screen: any of a member's drawings, on the frame and seen; not a scene, not off the frame, "
    "not faded, not the overlay (%s)" % on,
)


class F:
    def __init__(self):
        self.dir = tempfile.mkdtemp()

    def path(self, *p):
        return os.path.join(self.dir, *p)


f = F()
os.makedirs(f.path("audio", "vo"))
json.dump(
    {"lines": [{"i": 0, "start": 1, "end": 2}, {"i": 1, "start": 3, "end": 4.5}]},
    open(f.path("audio", "vo", "timeline.json"), "w"),
)
json.dump(
    {"lines": [{"who": "rusty", "text": "Wait."}, {"text": "The woods were dark."}]},
    open(f.path("vo.json"), "w"),
)
check(
    who.speakers(f) == [[1.0, 2.0, "rusty"], [3.0, 4.5, None]],
    "who says each line; none: the narrator",
)

print("\n%s" % ("ALL OK" if not bad else "%d FAILED" % len(bad)))
sys.exit(1 if bad else 0)
