#!/usr/bin/env python3
"""Write a page.json beside every page-NN/ folder of a converted comic.

page.json is the per-page record the animation stage reads: the kind of page,
how many panels it has, the scene files, whether its text was captured, and any
flags (panels still needing a redraw, caption-only panels, a free-text note).

Invoke as:
    python -I tools/comic-grok/pagejson.py <root_dir>

<root_dir> holds page-NN/ folders (e.g. "Downloads/Goofy Adventures 001 - grok").
Edit the ADS / COVER / REDO / CAPTION_ONLY / NOTES tables below for a given book;
they are deliberately data, not arguments, because they are decided per comic.
"""
import json
import re
import sys
import pathlib

# --- per-comic classification (edit for each book) ---------------------------
ADS = set()          # page numbers that are ads, e.g. {"07", "10"}
COVER = set()        # page numbers that are the cover, e.g. {"01"}
REDO = {}            # {"06": ["scene-02.jpg", ...]} panels still to recompose
CAPTION_ONLY = {}    # {"08": ["scene-01.jpg"]} blank/caption panels, no redraw
NOTES = {}           # {"18": "single full-page splash; 1 panel is correct."}
# -----------------------------------------------------------------------------

SCENE_RE = re.compile(r"^scene-\d+\.jpg$")  # excludes scene-NN_old.jpg backups


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: pagejson.py <root_dir>", file=sys.stderr)
        return 2
    root = pathlib.Path(sys.argv[1])
    for d in sorted(root.glob("page-*")):
        if not d.is_dir():
            continue
        num = d.name.split("-")[1]
        scenes = sorted(p.name for p in d.glob("scene-*.jpg") if SCENE_RE.match(p.name))
        tf = d / "text.txt"
        kind = "ad" if num in ADS else "cover" if num in COVER else "story"
        obj = {
            "page": int(num),
            "kind": kind,
            "panel_count": len(scenes),
            "scenes": scenes,
            "has_text": tf.exists(),
            "source_page": f"page-{num}.jpg",
            "needs_redraw": REDO.get(num, []),
            "caption_only": CAPTION_ONLY.get(num, []),
            "note": NOTES.get(num, ""),
        }
        (d / "page.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"page-{num}: {kind}, {len(scenes)}p")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
