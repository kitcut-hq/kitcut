#!/usr/bin/env python
"""Design a card -- an end card, a stamp, a slate, a lower banner -- from a
spec, a layout template and a brand.

`image-overlay.py` will burn any PNG onto a film. This is the other half: where
that PNG comes from when nobody has one. A card is described as data

    {"template": "stacked-blocks", "brand": "instafill",
     "lines": [{"text": "INSTAFILL.AI", "style": "hero"}]}

and this turns it into an HTML page and then a transparent PNG. Nothing about
the design is in this script: the *shape* is a template under
`config/cards/templates/`, the *look* is a brand under `config/cards/brands/`,
and the *words* are the spec. Swap the brand and the same spec is another
company's card; swap the template and the same brand is another kind of card.

Why HTML at all, rather than more Pillow: type is the whole job here, and a
browser already does web-quality text -- tracking, real font files, gradients,
shadows, flexbox -- where Pillow would have each of those hand-rolled. The
browser is only ever asked for a still, so none of its unpredictability reaches
the render.

Templates use a very small mustache: `{{x}}` escaped, `{{{x}}}` raw,
`{{#x}}...{{/x}}` for a list (repeated) or a flag (shown), `{{^x}}...{{/x}}`
for the absence of one. That is deliberately not a real template language --
a card that needs logic is a card that wants a new template.

Invoke as:  python scripts/make-card.py --spec projects/<id>/cards/end.json --png
"""
import sys, os, re, json, argparse, html, importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _overlay

_html2img = importlib.import_module("html-to-image")   # hyphen: not importable

ENV = _env.ENV
ROOT = _overlay.ROOT

TEMPLATE_DIR = "config/cards/templates"
BRAND_DIR = "config/cards/brands"
DEFAULT_BRAND = "instafill"


# ---------------------------------------------------------------- templating


_TAG = re.compile(r"\{\{([#^/]?)\s*([\w.]+)\s*\}\}|\{\{\{\s*([\w.]+)\s*\}\}\}")


def _lookup(ctx, key):
    cur = ctx
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def render_template(tpl, ctx):
    """The little mustache. Sections first, then the plain substitutions."""
    # Sections, innermost-last: find a {{#k}}..{{/k}} or {{^k}}..{{/k}} pair and
    # expand it, repeatedly, until none are left.
    while True:
        m = re.search(r"\{\{([#^])\s*([\w.]+)\s*\}\}(.*?)\{\{/\s*\2\s*\}\}",
                      tpl, re.S)
        if not m:
            break
        kind, key, body = m.group(1), m.group(2), m.group(3)
        val = _lookup(ctx, key)
        if kind == "^":
            out = render_template(body, ctx) if not val else ""
        elif isinstance(val, list):
            out = "".join(
                render_template(body, dict(ctx, **(v if isinstance(v, dict)
                                                   else {".": v})))
                for v in val)
        elif val:
            out = render_template(
                body, dict(ctx, **val) if isinstance(val, dict) else ctx)
        else:
            out = ""
        tpl = tpl[:m.start()] + out + tpl[m.end():]

    def sub(m):
        if m.group(3) is not None:                       # {{{raw}}}
            v = _lookup(ctx, m.group(3))
            return "" if v is None else str(v)
        if m.group(1):                                   # a stray section tag
            return ""
        v = _lookup(ctx, m.group(2))
        return "" if v is None else html.escape(str(v))

    return _TAG.sub(sub, tpl)


# ---------------------------------------------------------------- pieces


def list_dir(rel, ext):
    d = _overlay.repo_path(rel)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(d)
                  if f.endswith(ext))


def load_brand(name):
    p = _overlay.repo_path(os.path.join(BRAND_DIR, "%s.json" % name)) \
        if not name.endswith(".json") else _overlay.repo_path(name)
    if not os.path.exists(p):
        sys.exit("no such brand: %s\n  have: %s"
                 % (name, ", ".join(list_dir(BRAND_DIR, ".json")) or "(none)"))
    return json.load(open(p, encoding="utf-8"))


def load_template(name):
    p = _overlay.repo_path(os.path.join(TEMPLATE_DIR, "%s.html" % name)) \
        if not name.endswith(".html") else _overlay.repo_path(name)
    if not os.path.exists(p):
        sys.exit("no such template: %s\n  have: %s"
                 % (name, ", ".join(list_dir(TEMPLATE_DIR, ".html")) or "(none)"))
    return open(p, encoding="utf-8").read()


def font_url(path):
    """Fonts go in as absolute file:/// URLs.

    The page is generated, not hand-kept, and it may be written to a temp dir
    at any depth, so a relative @font-face src would resolve differently
    depending on where the card happened to land. A hand-written page (see
    projects/claude-demo/assets/end-card.html) can and should use a relative
    one -- it lives at a known depth and is committed.
    """
    return "file:///" + _overlay.repo_path(path).replace("\\", "/")


def build_html(spec, brand=None, template=None):
    """spec (+ brand + template names it may carry) -> the finished HTML."""
    b = load_brand(brand or spec.get("brand") or DEFAULT_BRAND)
    tpl = load_template(template or spec.get("template") or "stacked-blocks")

    ctx = dict(b)
    for key in ("font_bold", "font_regular"):
        if b.get(key):
            ctx[key + "_url"] = font_url(b[key])
    ctx.update({k: v for k, v in spec.items()
                if k not in ("brand", "template")})

    # Line styling is data: a template offers named styles, and a line may
    # override any of them inline without the template growing a branch.
    lines = []
    for ln in spec.get("lines") or []:
        ln = dict(ln) if isinstance(ln, dict) else {"text": ln}
        css = []
        for key, prop in (("size_px", "font-size"), ("fill", "background"),
                          ("colour", "color"), ("color", "color"),
                          ("tracking_px", "letter-spacing")):
            if ln.get(key) is not None:
                v = ln[key]
                css.append("%s:%s" % (prop, "%gpx" % v
                                      if isinstance(v, (int, float)) else v))
        ln["inline"] = ";".join(css)
        ln.setdefault("style", "body")
        lines.append(ln)
    ctx["lines"] = lines
    return render_template(tpl, ctx)


# ---------------------------------------------------------------- cli


def main():
    ap = argparse.ArgumentParser(
        description="Design a card from a spec, a template and a brand.")
    ap.add_argument("--spec", help="JSON card spec")
    ap.add_argument("--out", help="output .html (default beside the spec)")
    ap.add_argument("--png", nargs="?", const=True, default=None,
                    help="also render a transparent PNG (optional path)")
    ap.add_argument("--template", help="override the spec's template")
    ap.add_argument("--brand", help="override the spec's brand")
    ap.add_argument("--text", action="append", default=[],
                    help="a line, as STYLE:TEXT -- builds a spec without a "
                         "file, e.g. --text hero:'ACME' --text accent:@acme")
    ap.add_argument("--viewport", default="1600,1000")
    ap.add_argument("--scale", type=float, default=2.0)
    ap.add_argument("--list", action="store_true",
                    help="show the templates, brands and line styles available "
                         "-- design nothing")
    args = ap.parse_args()

    if args.list:
        print("templates (config/cards/templates/):")
        for t in list_dir(TEMPLATE_DIR, ".html"):
            head = open(_overlay.repo_path(
                os.path.join(TEMPLATE_DIR, t + ".html")), encoding="utf-8"
            ).read()
            m = re.search(r"<!--\s*(.*?)\s*-->", head, re.S)
            first = (m.group(1).strip().splitlines()[0] if m else "")
            print("  %-18s %s" % (t, first))
        print("\nbrands (config/cards/brands/):")
        for b in list_dir(BRAND_DIR, ".json"):
            d = load_brand(b)
            print("  %-18s ink %s  paper %s  accent %s"
                  % (b, d.get("ink"), d.get("paper"), d.get("accent")))
        print("\nline styles: kicker, hero, accent, body, ghost")
        print("a line may override size_px / fill / colour / tracking_px")
        return

    if args.spec:
        spec = json.load(open(_overlay.repo_path(args.spec), encoding="utf-8"))
    elif args.text:
        spec = {"lines": []}
    else:
        sys.exit("give --spec <json> or --text STYLE:TEXT (or --list)")

    for item in args.text:
        style, _, text = item.partition(":")
        if not text:
            style, text = "body", style
        spec.setdefault("lines", []).append({"style": style, "text": text})
    if not spec.get("lines"):
        sys.exit("the card has no lines -- nothing to draw")

    doc = build_html(spec, args.brand, args.template)

    out = args.out or (os.path.splitext(_overlay.repo_path(args.spec))[0]
                       + ".html" if args.spec else "temp/card.html")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(out)

    if args.png:
        png = args.png if isinstance(args.png, str) \
            else os.path.splitext(out)[0] + ".png"
        vw, vh = (int(x) for x in args.viewport.replace("x", ",").split(","))
        w, h = _html2img.render(out, png, viewport=(vw, vh), scale=args.scale,
                                pad=int(spec.get("pad_px", 8)))
        print("%s  %dx%d" % (png, w, h))


if __name__ == "__main__":
    main()
