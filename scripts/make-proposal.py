#!/usr/bin/env python
"""Generate a proposal for a lead -- a campaign laid out on THEIR calendar -- as
a PDF they can read in two minutes.

A lead who has seen a demo does not need another description of the tool. They
need to see what would be published, on which day, relative to the dates they
already live by: thirty days to go, the agenda going up, the week of the event.
A plan typed into an email carries those dates as words, and the words drift
from the calendar the first time the plan is edited. So here the calendar is
*computed*: an item says `days_before: 30` or names a date, and the script
places it in its week, names its weekday and counts the days to the event.
Move the event and the whole plan moves with it.

A proposal is described the way a card or a document is: a *shape* (a template
under `config/proposals/templates/`), a *look* (a brand under
`config/proposals/brands/` -- ours, since it is our proposal) and *words* (a
spec, kept with the lead's project because a lead's name and prices are not
tooling). The spec owns every string, so the language is the spec's.

`--plan` is the free mode: the calendar as text, every item with its resolved
date, weekday and days to go, and the problems a rendered page would hide --
an item outside the weeks shown, a weekend, two items of one lane on one day.

The output is checked, not assumed: the page count must match the sections the
spec carries, every page must hold its own title, and the brand's body font
must be embedded -- a machine that could not reach the web font prints the
same pages in a fallback face, and that is the difference between a designed
proposal and a default one.

Invoke as:
  python scripts/make-proposal.py --list
  python scripts/make-proposal.py --spec config/proposals/example/devdays.json --plan
  python scripts/make-proposal.py --spec <spec.json> --pdf --preview
"""

import sys
import os
import json
import argparse
import datetime
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

import _project

_html2img = importlib.import_module("html-to-image")  # hyphen: not importable
_card = importlib.import_module("make-card")  # its mustache, unchanged
_doc = importlib.import_module("make-doc")  # its Chromium print, unchanged

TEMPLATE_DIR = "config/proposals/templates"
BRAND_DIR = "config/proposals/brands"

# The sections a template may draw, in page order. A spec that leaves one out
# gets a shorter proposal, and the page count is asserted against this.
SECTIONS = ("cover", "ready", "timeline", "options", "process")

DEFAULT_STRINGS = {
    "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "days_to_go": ["day to go", "days to go", "days to go"],
    "event_days": "event days",
    "after_event": "after the event",
    "done": "ready",
    "recommended": "recommended",
}

# Languages whose plural has three forms (1 / 2-4 / 5+): the rule, not a table.
THREE_FORMS = ("uk", "pl", "cs", "sk", "hr", "sr", "bg")


def day(s, what="date"):
    try:
        return datetime.date.fromisoformat(s)
    except (TypeError, ValueError):
        sys.exit("%s is not a YYYY-MM-DD date: %r" % (what, s))


def plural(n, forms, lang):
    """`forms` is [one, few, many]; a two-form language uses one and few."""
    n = abs(n)
    if lang in THREE_FORMS:
        if n % 10 == 1 and n % 100 != 11:
            return forms[0]
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return forms[1]
        return forms[2]
    return forms[0] if n == 1 else forms[1]


def dm(d):
    return "%d.%02d" % (d.day, d.month)


def span_label(a, b):
    """One day, or a range that says the month once when both ends share it."""
    if a == b:
        return dm(a)
    if a.month == b.month:
        return "%d–%s" % (a.day, dm(b))
    return "%s–%s" % (dm(a), dm(b))


def monday(d):
    return d - datetime.timedelta(days=d.weekday())


def resolve_item(item, ev_start, ev_end, where):
    """An item's first and last day, from whichever way the spec names them."""
    if item.get("event"):
        return ev_start, ev_end
    if "days_before" in item:
        a = ev_start - datetime.timedelta(days=int(item["days_before"]))
        return a, a
    if "days_after" in item:
        a = ev_end + datetime.timedelta(days=int(item["days_after"]))
        return a, a
    start = item.get("date") or item.get("from")
    if not start:
        sys.exit("%s: an item needs date, from/to, days_before, days_after or event" % where)
    a = day(start, where)
    b = day(item["to"], where) if item.get("to") else a
    if b < a:
        sys.exit("%s: 'to' (%s) is before its start (%s)" % (where, b, a))
    return a, b


def build_timeline(spec):
    """The calendar: weeks as columns, lanes as rows, every item placed.

    Returns (context, rows, problems). `rows` is the same calendar as flat
    records for --plan; `problems` is what a rendered page would hide.
    """
    tl = spec["timeline"]
    lang = spec.get("lang", "en")
    strings = dict(DEFAULT_STRINGS, **(spec.get("strings") or {}))
    ev = spec.get("event") or {}
    if not ev.get("start"):
        sys.exit("the spec needs event.start: the calendar is counted from it")
    ev_start = day(ev["start"], "event.start")
    ev_end = day(ev.get("end") or ev["start"], "event.end")

    placed, problems = [], []
    for li, lane in enumerate(tl.get("lanes") or []):
        for ii, item in enumerate(lane.get("items") or []):
            a, b = resolve_item(item, ev_start, ev_end, "lane %r item %d" % (lane.get("label"), ii))
            placed.append((li, item, a, b))
    if not placed:
        sys.exit("timeline.lanes holds no items")

    first = monday(day(tl["from"], "timeline.from")) if tl.get("from") else None
    first = first or monday(min(a for _, _, a, _ in placed))
    last = monday(max(max(b for _, _, _, b in placed), ev_end))
    weeks = []
    w = first
    while w <= last:
        weeks.append(w)
        w += datetime.timedelta(days=7)
    if len(weeks) > 10:
        problems.append(
            "%d weeks is more than a page holds legibly (10): shorten the window" % len(weeks)
        )

    def col(d):
        return (monday(d) - first).days // 7

    ev_cols = set(range(col(ev_start), col(ev_end) + 1))
    week_ctx = []
    for i, w in enumerate(weeks):
        to_go = (ev_start - w).days
        if i in ev_cols:
            sub = strings["event_days"]
        elif to_go < 0:
            sub = strings["after_event"]
        else:
            sub = "%d %s" % (to_go, plural(to_go, strings["days_to_go"], lang))
        week_ctx.append(
            {
                "label": span_label(w, w + datetime.timedelta(days=6)),
                "sub": sub,
                "is_event": i in ev_cols,
            }
        )

    lanes_ctx, rows = [], []
    for li, lane in enumerate(tl.get("lanes") or []):
        kind = lane.get("kind", "plan")
        mine = sorted(((a, b, item) for l2, item, a, b in placed if l2 == li), key=lambda x: x[0])
        seen = {}
        cells = [{"is_event": i in ev_cols, "items": []} for i in range(len(weeks))]
        bands = []
        for a, b, item in mine:
            if a < first:
                problems.append(
                    "%s: %r starts %s, before the first week shown"
                    % (lane.get("label"), item.get("label"), a)
                )
                continue
            if kind == "bands":
                bands.append(
                    {
                        "col": col(a) + 1,
                        "span": col(b) - col(a) + 1,
                        "label": item.get("label", ""),
                        "dlabel": span_label(a, b),
                        "done": bool(item.get("done")),
                    }
                )
            else:
                wd = strings["weekdays"][a.weekday()]
                dlabel = "%s %s" % (wd, dm(a)) if a == b else span_label(a, b)
                cells[col(a)]["items"].append(
                    {
                        "dlabel": dlabel,
                        "label": item.get("label", ""),
                        "done": bool(item.get("done")),
                        "is_event_item": bool(item.get("event")),
                    }
                )
                if a == b and a.weekday() >= 5 and kind != "client":
                    problems.append(
                        "%s: %r lands on a %s (%s)" % (lane.get("label"), item.get("label"), wd, a)
                    )
                if kind != "client" and a == b:
                    if a in seen:
                        problems.append(
                            "%s: %r and %r share %s"
                            % (lane.get("label"), seen[a], item.get("label"), a)
                        )
                    seen[a] = item.get("label")
            rows.append(
                {
                    "lane": lane.get("label", ""),
                    "start": a,
                    "end": b,
                    "to_go": (ev_start - a).days,
                    "label": item.get("label", ""),
                    "done": bool(item.get("done")),
                }
            )
        lanes_ctx.append(
            {
                "label": lane.get("label", ""),
                "tag": lane.get("tag", ""),
                "kind": kind,
                "is_cells": kind != "bands",
                "is_bands": kind == "bands",
                "cells": cells,
                "bands": bands,
            }
        )

    ctx = {
        "title": tl.get("title", ""),
        "lead": tl.get("lead", ""),
        "note": tl.get("note", ""),
        "ncols": len(weeks),
        "weeks": week_ctx,
        "lanes": lanes_ctx,
        "key_client": tl.get("key_client", ""),
        "key_plan": tl.get("key_plan", ""),
        "key_done": tl.get("key_done", ""),
    }
    return ctx, rows, problems


def print_plan(spec, rows, problems):
    """The calendar as text -- what --plan shows before any browser starts."""
    ev = spec["event"]
    lang = spec.get("lang", "en")
    strings = dict(DEFAULT_STRINGS, **(spec.get("strings") or {}))
    print("%s: %s to %s" % (ev.get("name", "event"), ev["start"], ev.get("end") or ev["start"]))
    lane = None
    for r in rows:
        if r["lane"] != lane:
            lane = r["lane"]
            print("\n%s" % lane)
        when = (
            "%s %s" % (strings["weekdays"][r["start"].weekday()], r["start"])
            if r["start"] == r["end"]
            else "%s .. %s" % (r["start"], r["end"])
        )
        n = r["to_go"]
        to_go = "%d %s" % (n, plural(n, strings["days_to_go"], lang)) if n > 0 else "-"
        print("  %-26s %-22s %s%s" % (when, to_go, r["label"], "  [ready]" if r["done"] else ""))
    print()
    for p in problems:
        print("PROBLEM  %s" % p)
    if not problems:
        print("no problems: every item sits in a week shown, on a weekday, alone in its lane")


def load_json(path, what):
    if not os.path.exists(path):
        sys.exit("no such %s: %s" % (what, path))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_brand(name):
    path = _env.resolve(os.path.join(BRAND_DIR, name + ".json"))
    if not os.path.exists(path):
        sys.exit(
            "no such brand: %s\navailable: %s"
            % (name, ", ".join(_doc.list_dir(BRAND_DIR, ".json")) or "(none)")
        )
    brand = load_json(path, "brand")
    # Files a brand names live in the tooling; the page needs them as URLs.
    for key in ("logo", "font_body_file", "font_display_file"):
        if brand.get(key):
            p = _env.resolve(brand[key])
            if not os.path.exists(p):
                sys.exit("brand %s names a missing file: %s" % (name, brand[key]))
            brand[key + "_url"] = _html2img.file_url(p)
    return brand


def load_template(name):
    path = _env.resolve(os.path.join(TEMPLATE_DIR, name + ".html"))
    if not os.path.exists(path):
        sys.exit(
            "no such template: %s\navailable: %s"
            % (name, ", ".join(_doc.list_dir(TEMPLATE_DIR, ".html")) or "(none)")
        )
    with open(path, encoding="utf-8") as f:
        return f.read()


def picture(rel, spec_dir, where):
    """A spec's picture as a file URL; a missing one fails here, not as a gap."""
    p = _env.resolve(rel, base=spec_dir)
    if not os.path.exists(p):
        sys.exit("%s names a missing picture: %s" % (where, rel))
    return _html2img.file_url(p)


def texts(items):
    """A list of strings as the mustache wants it: a list of {t}."""
    return [{"t": x} if not isinstance(x, dict) else x for x in (items or [])]


def build_context(spec, spec_path):
    """Spec + brand -> the one context the template renders. Returns
    (context, page titles in order, plan rows, problems)."""
    spec_dir = os.path.dirname(os.path.abspath(spec_path))
    strings = dict(DEFAULT_STRINGS, **(spec.get("strings") or {}))
    present = [s for s in SECTIONS if spec.get(s)]
    if not present:
        sys.exit("%s carries none of: %s" % (spec_path, ", ".join(SECTIONS)))

    ctx = {
        "doc_title": spec.get("title", ""),
        "lang": spec.get("lang", "en"),
        "brand": load_brand(spec.get("brand", "kitcut")),
        "client": spec.get("client") or {},
        "event": spec.get("event") or {},
        "page_total": len(present),
    }
    titles, rows, problems = [], [], []

    for n, name in enumerate(present, 1):
        sec = dict(spec[name])
        sec["page_no"] = n
        if name == "cover":
            sec["images"] = [
                {"url": picture(p, spec_dir, "cover.images"), "n": i + 1}
                for i, p in enumerate(sec.get("images") or [])
            ]
            sec["has_images"] = bool(sec["images"])
            titles.append(sec.get("headline", ""))
        elif name == "ready":
            items = []
            for it in sec.get("items") or []:
                it = dict(it)
                if it.get("image"):
                    it["image_url"] = picture(it["image"], spec_dir, "ready.items")
                it["has_image"] = bool(it.get("image"))
                it["url_text"] = it.get("url_text") or (it.get("url") or "").split("://")[-1]
                items.append(it)
            sec["items"] = items
            titles.append(sec.get("title", ""))
        elif name == "timeline":
            tl, rows, problems = build_timeline(spec)
            sec = dict(tl, page_no=n)
            titles.append(sec.get("title", ""))
        elif name == "options":
            items = []
            for it in sec.get("items") or []:
                it = dict(it)
                it["points"] = texts(it.get("points"))
                it["recommended"] = bool(it.get("recommended"))
                it["recommended_label"] = strings["recommended"]
                items.append(it)
            sec["items"] = items
            sec["count"] = len(items)
            titles.append(sec.get("title", ""))
        elif name == "process":
            blocks = []
            for i, b in enumerate(sec.get("blocks") or []):
                b = dict(b)
                b["points"] = [dict(p, n=j + 1) for j, p in enumerate(texts(b.get("points")))]
                blocks.append(b)
            sec["blocks"] = blocks
            sec["has_next"] = bool(sec.get("next"))
            titles.append(sec.get("title", ""))
        ctx[name] = sec
    return ctx, titles, rows, problems


def verify(out, titles, brand):
    """Pages, their titles, and the brand's body font -- read back from the PDF."""
    pages = _doc.verify_pdf(out)
    from pypdf import PdfReader

    reader = PdfReader(out)
    if pages != len(titles):
        sys.exit(
            "%s has %d pages for %d sections: something overflowed its page"
            % (out, pages, len(titles))
        )

    def squash(s):
        return "".join(s.split()).lower()

    fonts = set()
    for i, (page, title) in enumerate(zip(reader.pages, titles), 1):
        text = squash(page.extract_text() or "")
        if title and squash(title) not in text:
            sys.exit("page %d of %s does not carry its title %r" % (i, out, title))
        res = page.get("/Resources") or {}
        for f in (res.get("/Font") or {}).values():
            fonts.add(str(f.get_object().get("/BaseFont", "")))
    # Chromium embeds a variable font as an unnamed Type 3 face and a static
    # one under its own name, so the brand's faces show up as "" or as their
    # family. Anything else named here is a fallback: a font file that did not
    # load, or a glyph the brand's face does not have.
    own = [(brand.get(k) or "").replace(" ", "").lower() for k in ("font_body", "font_display")]
    strays = sorted(f for f in fonts if f.strip("/") and not any(o and o in f.lower() for o in own))
    if strays:
        sys.exit(
            "%s is partly set in a fallback face (%s), not in %s -- a font did not load, "
            "or the text uses a glyph the brand's face lacks"
            % (out, ", ".join(strays), " / ".join(o for o in own if o))
        )
    return pages


def preview(out):
    """Each page as a PNG beside the PDF: look at it before it is sent."""
    import pypdfium2

    made = []
    pdf = pypdfium2.PdfDocument(out)
    try:
        for i in range(len(pdf)):
            png = "%s-p%d.png" % (os.path.splitext(out)[0], i + 1)
            pdf[i].render(scale=1.5).to_pil().save(png)
            made.append(png)
    finally:
        pdf.close()
    return made


def spec_out(spec, spec_path):
    """Where a spec's PDF lands: its `out`, beside the spec unless a project owns it."""
    out = spec.get("out")
    if not out:
        sys.exit("%s has no 'out'" % spec_path)
    if spec.get("project"):
        return os.path.join(_project.projects_dir(), spec["project"], out)
    return _env.resolve(out, base=os.path.dirname(os.path.abspath(spec_path)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", help="the proposal spec (JSON)")
    ap.add_argument("--pdf", action="store_true", help="print the PDF (otherwise HTML only)")
    ap.add_argument("--preview", action="store_true", help="with --pdf: each page as a PNG too")
    ap.add_argument("--html-out", help="where to leave the intermediate HTML")
    ap.add_argument("--out", help="write the PDF here instead of the spec's 'out'")
    ap.add_argument(
        "--plan",
        action="store_true",
        help="the calendar as text, with every item's date and days to go -- no browser",
    )
    ap.add_argument("--list", action="store_true", help="templates and brands -- no render")
    a = ap.parse_args()

    if a.list:
        print("templates: %s" % (", ".join(_doc.list_dir(TEMPLATE_DIR, ".html")) or "(none)"))
        print("brands:    %s" % (", ".join(_doc.list_dir(BRAND_DIR, ".json")) or "(none)"))
        if not a.spec:
            return
    if not a.spec:
        sys.exit("give --spec")

    spec_path = _env.resolve(a.spec)
    spec = load_json(spec_path, "spec")

    if a.plan or a.list:
        if not spec.get("timeline"):
            sys.exit("%s has no timeline to plan" % a.spec)
        _, rows, problems = build_timeline(spec)
        print_plan(spec, rows, problems)
        sys.exit(1 if problems else 0)

    ctx, titles, _, problems = build_context(spec, spec_path)
    if problems:
        sys.exit("the calendar has problems (see --plan):\n  " + "\n  ".join(problems))
    html = _card.render_template(load_template(spec.get("template", "campaign")), ctx)
    out = os.path.abspath(a.out) if a.out else spec_out(spec, spec_path)

    html_path = a.html_out or os.path.join(
        _env.resolve("temp"), "proposals", os.path.splitext(os.path.basename(out))[0] + ".html"
    )
    os.makedirs(os.path.dirname(html_path) or ".", exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    if not a.pdf:
        print("%s -> %s (HTML only)" % (os.path.basename(spec_path), _project.norm(html_path)))
        return

    got = _html2img.find_browsers()
    if not got:
        sys.exit("no Chromium found -- install Microsoft Edge or Google Chrome")
    _doc.print_pdf(html_path, out, got[0])
    pages = verify(out, titles, ctx["brand"])
    print(
        "%s -> %s  %d page%s, %.0f KB"
        % (
            os.path.basename(spec_path),
            _project.norm(out),
            pages,
            "" if pages == 1 else "s",
            os.path.getsize(out) / 1024.0,
        )
    )
    if a.preview:
        for png in preview(out):
            print("  preview %s" % _project.norm(png))
    if spec.get("project"):
        _project.record(
            spec["project"],
            "proposal",
            out=out,
            script="scripts/make-proposal.py",
            argv=sys.argv[1:],
            kind="proposal",
            manifest=spec_path,
            note="template %s, brand %s"
            % (spec.get("template", "campaign"), ctx["brand"].get("name")),
        )


if __name__ == "__main__":
    main()
