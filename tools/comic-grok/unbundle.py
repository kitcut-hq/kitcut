#!/usr/bin/env python3
"""Split a .bundle (produced by the in-browser Grok grabber) into scene-NN.jpg.

The grabber concatenates each panel image as a header line "IMG <bytelen>\n"
followed by exactly that many raw JPEG bytes. This reverses it.

Invoke as:
    python -I tools/comic-grok/unbundle.py <src.bundle> <out_dir>

Writes <out_dir>/scene-01.jpg, scene-02.jpg, ... in order. Run with -I so a
planted module beside the (untrusted) download cannot be imported.
"""
import sys
import pathlib


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: unbundle.py <src.bundle> <out_dir>", file=sys.stderr)
        return 2
    src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    data, i, n = src.read_bytes(), 0, 0
    while i < len(data):
        nl = data.index(b"\n", i)
        tag, ln = data[i:nl].split()
        assert tag == b"IMG", f"bad tag {tag!r} at offset {i}"
        ln = int(ln)
        n += 1
        (out / f"scene-{n:02d}.jpg").write_bytes(data[nl + 1 : nl + 1 + ln])
        i = nl + 1 + ln
    print(n, "images ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
