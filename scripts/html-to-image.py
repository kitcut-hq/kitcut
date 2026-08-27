#!/usr/bin/env python
"""Render an HTML page to a PNG with a transparent background.

This is the half of the image-overlay pipeline that lets a graphic be *written*
rather than *found*. An end card, a stat card, a quote slate -- anything whose
design is type and boxes -- is far easier to author as HTML and CSS than to
assemble with Pillow calls, and the browser already has web fonts, flexbox,
gradients and text shadows. So: write the page, screenshot it, hand the PNG to
`image-overlay.py`, which knows nothing about where it came from.

The transparency is the whole point, and it takes two things:

  * `--default-background-color=00000000`, which is what makes the browser
    composite onto nothing instead of onto white. Chromium's headless default
    is opaque white and there is no CSS that undoes it.
  * a page that never paints its own background. `body { background: #fff }`
    beats the flag every time, so the alpha channel is CHECKED after the
    screenshot rather than assumed -- a fully opaque PNG fails here, with the
    reason, instead of becoming a white slab sitting on the film.

The screenshot is then cropped to its own alpha bbox. A page is a rectangle of
some declared viewport size and the artwork inside it almost never fills that
rectangle; cropping to the ink means `image-overlay.py`'s corner anchoring and
`width_frac` scaling talk about the graphic instead of about the empty margin
around it.

Invoke as:  python scripts/html-to-image.py --html page.html --out card.png
"""
import sys, os, argparse, subprocess, shutil, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import Image
import _overlay

ENV = _env.ENV
ROOT = _overlay.ROOT

# Edge first: it ships on every Windows box this repo is used from, so the
# no-install path is the default one. Both are Chromium and take identical
# flags, so which one answers changes nothing downstream.
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browsers():
    """Every Chromium we can see, in preference order, deduplicated."""
    got, seen = [], set()
    for cand in ([os.environ["HTML2IMG_BROWSER"]]
                 if os.environ.get("HTML2IMG_BROWSER") else []) + BROWSERS:
        if cand and os.path.exists(cand) and cand.lower() not in seen:
            seen.add(cand.lower())
            got.append(cand)
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        p = shutil.which(name)
        if p and p.lower() not in seen:
            seen.add(p.lower())
            got.append(p)
    return got


def browser_version(path):
    """Version read off the install directory, NOT by running the browser.

    `msedge --version` on Windows does not print a version -- it hands the
    argument to the already-running instance and OPENS A WINDOW, then exits 0.
    Chrome's just hangs. A --check that pops a browser open is not a free check,
    so read the version-numbered folder Chromium installs beside its exe.
    """
    app = os.path.dirname(path)
    vers = []
    try:
        for name in os.listdir(app):
            head = name.split(".")[0]
            if head.isdigit() and os.path.isdir(os.path.join(app, name)):
                vers.append(name)
    except OSError:
        pass
    if not vers:
        return "version unknown"
    return max(vers, key=lambda v: [int(x) for x in v.split(".") if x.isdigit()])


def file_url(path):
    """file:/// URL for a local page, with the Windows separators flipped."""
    return "file:///" + os.path.abspath(path).replace("\\", "/")


def shoot(html, out, browser, viewport=(1600, 1000), scale=2, timeout=45,
          settle_ms=2000):
    """Screenshot `html` into `out`. Returns the browser that did it."""
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if os.path.exists(out):
        os.remove(out)                       # so a failed run cannot look fresh

    with tempfile.TemporaryDirectory(prefix="html2img-") as profile:
        base = [
            "--headless",
            "--screenshot=%s" % os.path.abspath(out),
            "--default-background-color=00000000",   # the transparency itself
            "--window-size=%d,%d" % viewport,        # a COMMA, not an x
            "--force-device-scale-factor=%g" % scale,
            "--hide-scrollbars",
            # Deterministic settling: renders virtual time forward until the
            # budget is spent, so web fonts and entry animations have finished
            # before the shutter. Without it the shot races the page and a
            # font-swap lands in some runs and not others.
            "--virtual-time-budget=%d" % settle_ms,
            "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--user-data-dir=%s" % profile,
            file_url(html),
        ]
        # Chromium 132 removed old headless, so on anything current `--headless`
        # IS the new one. Older builds need it spelled out; try that once rather
        # than making the caller know which vintage they have.
        for flags in (base, ["--headless=new"] + base[1:]):
            r = subprocess.run([browser] + flags, env=ENV,
                               capture_output=True, text=True, timeout=timeout)
            if os.path.exists(out) and os.path.getsize(out) > 0:
                return browser
        sys.exit("%s produced no screenshot for %s\n%s"
                 % (os.path.basename(browser), html,
                    (r.stderr or r.stdout or "").strip()[:800]))


def finish(out, crop=True, pad=0):
    """Check the shot really has alpha, then crop it to its own ink.

    Returns (width, height). Raises SystemExit with the cause when the page
    painted itself opaque, which is the one failure that would otherwise ship
    a white rectangle onto the film and look like a filter bug.
    """
    img = Image.open(out).convert("RGBA")
    alpha = img.split()[3]
    lo, _ = alpha.getextrema()
    if lo == 255:
        sys.exit("%s came back fully opaque -- the page painted a background.\n"
                 "  Give html/body no background (or `background: transparent`)"
                 " and let the card itself be the only thing with a fill."
                 % out)

    if crop:
        # The ALPHA channel's bbox, not the image's: Image.getbbox() counts any
        # non-zero pixel, so a coloured-but-transparent pixel would keep the
        # margin it is trying to remove.
        box = alpha.getbbox()
        if box:
            l, t, r, b = box
            img = img.crop((max(0, l - pad), max(0, t - pad),
                            min(img.width, r + pad), min(img.height, b + pad)))
    img.save(out)
    return img.size


def render(html, out, browser=None, viewport=(1600, 1000), scale=2,
           crop=True, pad=0, timeout=45, settle_ms=2000):
    """Render + verify + crop in one call. This is the importable entry point."""
    html = _overlay.repo_path(html)
    if not os.path.exists(html):
        sys.exit("no such HTML page: %s" % html)
    if browser is None:
        found = find_browsers()
        if not found:
            sys.exit("no Chromium browser found -- looked for Edge and Chrome "
                     "in Program Files and on PATH.\n  Set HTML2IMG_BROWSER to "
                     "one, or pass --browser.")
        browser = found[0]
    shoot(html, out, browser, viewport, scale, timeout, settle_ms)
    return finish(out, crop, pad)


def main():
    ap = argparse.ArgumentParser(
        description="Render an HTML page to a transparent PNG.")
    ap.add_argument("--html", help="the page to shoot")
    ap.add_argument("--out", help="output PNG; default <html>.png")
    ap.add_argument("--viewport", default="1600,1000",
                    help="browser window, W,H (default 1600,1000)")
    ap.add_argument("--scale", type=float, default=2.0,
                    help="device pixel ratio; 2 keeps type crisp when the card "
                         "is scaled up onto a 1080p frame")
    ap.add_argument("--pad", type=int, default=0,
                    help="transparent pixels to keep around the ink")
    ap.add_argument("--no-crop", action="store_true",
                    help="keep the full viewport instead of cropping to alpha")
    ap.add_argument("--settle-ms", type=int, default=2000,
                    help="virtual time to run before the shutter")
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--browser", help="path to Edge/Chrome; overrides discovery")
    ap.add_argument("--check", action="store_true",
                    help="name the browsers this machine can render with, and "
                         "render nothing")
    args = ap.parse_args()

    if args.check:
        found = find_browsers()
        if not found:
            sys.exit("no Chromium browser found -- install Edge or Chrome, or "
                     "set HTML2IMG_BROWSER")
        for i, p in enumerate(found):
            print("%s %-24s %s" % ("*" if i == 0 else " ",
                                   browser_version(p), p))
        print("\n* is the one that would be used.")
        return

    if not args.html:
        sys.exit("give --html (or --check)")
    out = args.out or os.path.splitext(_overlay.repo_path(args.html))[0] + ".png"
    try:
        vw, vh = (int(x) for x in args.viewport.replace("x", ",").split(","))
    except ValueError:
        sys.exit("--viewport wants W,H -- e.g. 1600,1000")

    w, h = render(args.html, out, args.browser, (vw, vh), args.scale,
                  not args.no_crop, args.pad, args.timeout, args.settle_ms)
    print("%s  %dx%d  %.0f KB" % (out, w, h, os.path.getsize(out) / 1e3))


if __name__ == "__main__":
    main()
