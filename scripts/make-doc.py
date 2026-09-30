#!/usr/bin/env python
"""Generate a synthetic source document -- the paperwork a form gets filled
FROM -- as a printable PDF.

Every "how to fill out form X" video needs two things: the blank form, and the
documents a real person would already be holding when they sit down to fill it.
The blank form we obtain. The documents we have to invent, because real ones
carry real names, real account numbers and a real client's business. Inventing
them by hand is how the BPO project spent a day, and it left nothing behind.

So a document here is described the same way a card is: a *shape* (a template
under `config/docs/templates/`), a *look* (an issuer under
`config/docs/issuers/` -- a carrier's declarations page and a Secretary of
State certificate must not look like the same office typed both), and *words*
(a spec under `projects/<id>/docs/`). Swap the issuer and the same loss run is
another carrier's; swap the template and the same issuer files something else.

Why a browser and not reportlab: these have to look like documents, which means
rules, shaded table headers, small caps, two-column blocks and a footer that
repeats -- all of which CSS already does and none of which is worth hand-laying
out in drawing calls. Chromium prints the page; `@page` in the template owns
the paper size and margins.

The output is checked, not assumed: a file that is not a PDF, or that has no
pages, fails here with the reason rather than reaching a recording session as a
blank tab.

Templates use the same tiny mustache as `make-card.py` -- `{{x}}`, `{{{x}}}`,
`{{#x}}...{{/x}}`, `{{^x}}...{{/x}}` -- and for the same reason: a document
that needs logic wants its own template, not a branch.

Invoke as:
  python scripts/make-doc.py --list
  python scripts/make-doc.py --project acord-commercial --list
  python scripts/make-doc.py --spec projects/<id>/docs/dec.json --pdf
  python scripts/make-doc.py --project acord-commercial --all --pdf
"""

import sys
import os
import json
import glob
import argparse
import importlib
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _project

_html2img = importlib.import_module("html-to-image")  # hyphen: not importable
_card = importlib.import_module("make-card")  # its mustache, unchanged

ENV = _env.ENV
ROOT = _env.ROOT

TEMPLATE_DIR = "config/docs/templates"
ISSUER_DIR = "config/docs/issuers"

# Reserved top-level keys: everything else in a spec is data for the template.
RESERVED = ("template", "issuer", "out", "project", "_comment")


def list_dir(rel, ext):
    d = _env.resolve(rel)
    return sorted(
        os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(d, "*" + ext))
    )


def load_json(path, what):
    if not os.path.exists(path):
        sys.exit("no such %s: %s" % (what, path))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_issuer(name):
    return load_json(_env.resolve(os.path.join(ISSUER_DIR, name + ".json")), "issuer")


def load_template(name):
    path = _env.resolve(os.path.join(TEMPLATE_DIR, name + ".html"))
    if not os.path.exists(path):
        sys.exit(
            "no such template: %s\navailable: %s"
            % (name, ", ".join(list_dir(TEMPLATE_DIR, ".html")) or "(none)")
        )
    with open(path, encoding="utf-8") as f:
        return f.read()


def flags(ctx):
    """Presence flags for the template.

    The mustache cannot wrap a repeated section in a conditional of the same
    name -- its section regex backreferences the key, so `{{#kv}}` inside
    `{{#kv}}` matches the wrong closing tag. Rather than teach the template
    language to branch, the caller is told *whether* each block exists, and the
    template stays a layout. `has_x` is computed here so no spec has to carry
    it by hand and then disagree with itself.
    """
    ctx["has_meta"] = bool(ctx.get("meta"))
    ctx["has_signature"] = bool(ctx.get("signature"))
    for sec in ctx.get("sections") or []:
        if isinstance(sec, dict):
            sec["has_kv"] = bool(sec.get("kv"))
    return ctx


def build_html(spec):
    """Spec + issuer -> one HTML page. Issuer tokens land under `issuer.`."""
    tpl = load_template(spec["template"])
    ctx = {k: v for k, v in spec.items() if k not in RESERVED}
    ctx["issuer"] = load_issuer(spec["issuer"]) if spec.get("issuer") else {}
    return _card.render_template(tpl, flags(ctx))


def print_pdf(html_path, out, browser, timeout=90):
    """Chromium prints `html_path` to `out`. Returns the page count."""
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if os.path.exists(out):
        os.remove(out)  # so a failed run cannot leave yesterday's file looking fresh

    with tempfile.TemporaryDirectory(prefix="make-doc-") as profile:
        base = [
            "--headless",
            "--print-to-pdf=%s" % os.path.abspath(out),
            # Chromium's own header/footer prints the file:// URL and a date
            # across every page. On a document meant to pass as a carrier's
            # own paper that is the one detail that gives it away.
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            "--virtual-time-budget=3000",  # web fonts settled before the print
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--user-data-dir=%s" % profile,
            _html2img.file_url(html_path),
        ]
        # Same vintage dance as html-to-image: on Chromium 132+ `--headless`
        # already IS the new one, older builds need it spelled out.
        for flags in (base, ["--headless=new"] + base[1:]):
            r = subprocess.run(
                [browser] + flags, env=ENV, capture_output=True, text=True, timeout=timeout
            )
            if os.path.exists(out) and os.path.getsize(out) > 0:
                return verify_pdf(out)
        sys.exit(
            "%s printed no PDF for %s\n%s"
            % (os.path.basename(browser), html_path, (r.stderr or r.stdout or "").strip()[:800])
        )


def verify_pdf(out):
    """A PDF with pages, or an error naming what came back instead."""
    with open(out, "rb") as f:
        head = f.read(5)
    if head != b"%PDF-":
        sys.exit("%s is not a PDF (starts %r)" % (out, head))
    from pypdf import PdfReader

    n = len(PdfReader(out).pages)
    if n < 1:
        sys.exit("%s has no pages" % out)
    return n


def spec_out(spec, spec_path):
    """Where a spec's PDF lands: its `out`, resolved against the project."""
    out = spec.get("out")
    if not out:
        sys.exit("%s has no 'out'" % spec_path)
    if spec.get("project"):
        return os.path.join(_project.projects_dir(), spec["project"], out)
    return _env.resolve(out, base=os.path.dirname(spec_path))


def find_specs(project):
    d = os.path.join(_project.projects_dir(), project, "docs")
    return sorted(glob.glob(os.path.join(d, "*.json")))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", help="one document spec (JSON)")
    ap.add_argument("--project", help="project id -- with --all, every spec in its docs/")
    ap.add_argument("--all", action="store_true", help="every spec of --project")
    ap.add_argument("--pdf", action="store_true", help="print the PDF (otherwise HTML only)")
    ap.add_argument("--html-out", help="where to leave the intermediate HTML")
    ap.add_argument(
        "--list",
        action="store_true",
        help="templates, issuers and what each spec would write -- no browser, no render",
    )
    a = ap.parse_args()

    specs = []
    if a.spec:
        specs = [_env.resolve(a.spec)]
    elif a.project and (a.all or a.list):
        specs = find_specs(a.project)

    if a.list:
        print("templates: %s" % (", ".join(list_dir(TEMPLATE_DIR, ".html")) or "(none)"))
        print("issuers:   %s" % (", ".join(list_dir(ISSUER_DIR, ".json")) or "(none)"))
        if not specs:
            return
        print("\n%-28s %-18s %-16s %s" % ("spec", "template", "issuer", "writes"))
        for p in specs:
            s = load_json(p, "spec")
            print(
                "%-28s %-18s %-16s %s"
                % (
                    os.path.basename(p),
                    s.get("template", "?"),
                    s.get("issuer", "-"),
                    _project.norm(spec_out(s, p)),
                )
            )
        return

    if not specs:
        sys.exit("give --spec, or --project <id> --all")

    browser = None
    if a.pdf:
        got = _html2img.find_browsers()
        if not got:
            sys.exit("no Chromium found -- install Microsoft Edge or Google Chrome")
        browser = got[0]

    for p in specs:
        spec = load_json(p, "spec")
        html = build_html(spec)
        out = spec_out(spec, p)

        html_path = a.html_out or os.path.join(
            _env.resolve("temp"), "docs", os.path.splitext(os.path.basename(out))[0] + ".html"
        )
        os.makedirs(os.path.dirname(html_path) or ".", exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        if not a.pdf:
            print("%s -> %s (HTML only)" % (os.path.basename(p), _project.norm(html_path)))
            continue

        pages = print_pdf(html_path, out, browser)
        print(
            "%s -> %s  %d page%s, %.0f KB"
            % (
                os.path.basename(p),
                _project.norm(out),
                pages,
                "" if pages == 1 else "s",
                os.path.getsize(out) / 1024.0,
            )
        )
        if spec.get("project"):
            _project.record(
                spec["project"],
                "document",
                out=out,
                script="scripts/make-doc.py",
                argv=sys.argv[1:],
                kind="source-document",
                manifest=p,
                note="synthetic: template %s, issuer %s"
                % (spec.get("template"), spec.get("issuer") or "-"),
            )


if __name__ == "__main__":
    main()
