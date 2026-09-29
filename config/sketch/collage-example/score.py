"""Write score.json for the paperwork film: a light office-jazz groove from a chord chart.

112 bpm in F, a swung ride and soft kick/rim, a walking bass, piano stabs on 2 and 4, a vibraphone
on each bar's first beat, and a button ending on the downbeat of bar 30 (64.29 s), where the
THE END stamp lands. Run it after changing the chart: python projects/collage-paperwork/score.py
"""

import json
import os

BPM = 112
BARS = 31  # 31 bars of 4/4 at 112 bpm = 66.4 s; the film is 66 s and the button is bar 30
CHART = [  # (chord, piano right hand, walking bass for the bar)
    ("F6", "A3+C4+D4+F4", "F2 A2 C3 D3"),
    ("Dm9", "F3+A3+C4+E4", "D2 F2 A2 C3"),
    ("Gm7", "Bb3+D4+F4+G4", "G2 Bb2 D3 F3"),
    ("C7", "Bb3+C4+E4+G4", "C3 Bb2 G2 E2"),
    ("Am7", "G3+C4+E4+A4", "A2 C3 E3 G2"),
    ("D7", "C4+F#4+A4+D5", "D2 F#2 A2 C3"),
    ("Gm7-C7", "Bb3+D4+F4|Bb3+E4+G4", "G2 D3 C3 E2"),
    ("F6", "A3+C4+D4+F4", "F2 C3 A2 C2"),
]


def main():
    piano, bass, vib = [], [], []
    for bar in range(BARS - 1):
        _, rh, walk = CHART[bar % len(CHART)]
        b0 = bar * 4
        halves = rh.split("|")
        # piano: stabs on 2 and 4 (the second half-bar takes the second chord if there is one)
        piano.append("%g %s .45 .30" % (b0 + 1, halves[0]))
        piano.append("%g %s .45 .26" % (b0 + 3, halves[-1]))
        if bar % 2 == 1:  # a swung pickup stab now and then
            piano.append("%g %s .25 .18" % (b0 + 3.67, halves[-1]))
        for i, n in enumerate(walk.split()):
            bass.append("%g %s .9 %.2f" % (b0 + i, n, 0.5 if i == 0 else 0.4))
        top = halves[0].split("+")[-1]
        vib.append("%g %s 2 .22" % (b0, top.replace("4", "5") if top.endswith("4") else top))
    end = (BARS - 1) * 4  # the button
    piano.append("%g F2+C3+A3+C4+D4+F4 3 .45" % end)
    bass.append("%g F1 3 .6" % end)
    vib.append("%g A5+C6+F6 3 .3" % end)
    score = {
        "bpm": BPM,
        "drum_gain": 0.34,
        "events": [
            {"inst": "acoustic_grand_piano", "vel": 0.55, "notes": "; ".join(piano)},
            {"inst": "acoustic_bass", "vel": 0.8, "notes": "; ".join(bass)},
            {"inst": "vibraphone", "vel": 0.5, "notes": "; ".join(vib)},
            {"inst": "clarinet", "vel": 0.34, "notes": "0.5 C5 .5; 1 D5 .5; 1.5 F5 1; 3 A5 .5; 3.67 G5 .33; 4 F5 1.5"},
            {"type": "drums", "from": 0, "bars": BARS - 1, "steps": 12, "vel": 0.8,
             "kit": {"hat": "x..x.xx..x.x", "kick": "o.....o.....", "rim": "...o.....o.."}},
            {"type": "drums", "from": end, "bars": 1, "steps": 12, "vel": 1.0,
             "kit": {"kick": "X...........", "openhat": "x..........."}},
        ],
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "score.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(score, f, indent=1)
    print("score.json: %d bars at %d bpm, button at %.2f s" % (BARS, BPM, end * 60 / BPM))


if __name__ == "__main__":
    main()
