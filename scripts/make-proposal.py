#!/usr/bin/env python
"""Generate a proposal for a lead -- a campaign laid out on THEIR calendar -- as
a PDF they can read in two minutes.

A lead who has seen a demo does not need another description of the tool. They
need to see what would be published, on which day, relative to the dates they
already live by: thirty days to go, the agenda going up, the week of the event.
A plan typed into an email carries those dates as words, and the words drift
from the calendar the first time the plan is edited. So here the calendar is
*computed*: a post says `days_before: 30` or names a date, and the script puts
it on its day, names the weekday and counts the days to the event. Move the
event and the whole plan moves with it.

The calendar reads from top to bottom, one row for every date -- the empty
ones too, because the gaps are what a rhythm looks like -- and one column for
each size of the campaign, so "what do I get in B that A does not have" is
answered by looking across a row. A first version ran the weeks left to right
with a row per plan; nobody could read off it which plan to take.

A proposal is described the way a card or a document is: a *shape* (a template
under `config/proposals/templates/`), a *look* (a brand under
`config/proposals/brands/` -- ours, since it is our proposal) and *words* (a
spec, kept with the lead's project because a lead's name is not tooling). The
spec owns every string, so the language is the spec's, and its sections print
in the order the spec lists them.

`--plan` is the free mode: the calendar as text, every post with its resolved
date, weekday, days to go and the plans it belongs to, how many posts each plan
adds up to, and the problems a rendered page would hide -- a post outside the
dates shown, a post on a weekend, two posts of one plan on one day.

The output is checked, not assumed: one page per section, every page holding
its own title, and no face in the file but the brand's.

Invoke as:
  python scripts/make-proposal.py --list
  python scripts/make-proposal.py --spec config/proposals/example/devdays.json --plan
  python scripts/make-proposal.py --spec <spec.json> --html-out <page.html>
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

# The sections a template can draw. They print in the order the spec lists
# them, one page each, and the page count is asserted against that.
SECTIONS = ("cover", "ready", "audience", "loop", "options", "channels", "timeline", "process")

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

# The calendar is one page as tall as its rows, so the page size is computed.
# These are the template's own minimum heights (it reads them back as CSS
# variables, so the two cannot disagree); `chrome` is everything on that page
# that is not a row. A label that wraps past its row makes the page overflow
# into a second sheet, and the page count fails the print.
ROW = {"chrome": 475, "week": 40, "day": 30, "post": 42}
PAGE_W_IN = 13.333


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


def plans_of(post, ids, where):
    """The plans a post belongs to. `in` names the smallest plan that has it --
    every bigger one has it too, because the plans are sizes of one campaign --
    or lists the plans outright."""
    v = post.get("in", ids[0])
    if isinstance(v, list):
        bad = [x for x in v if x not in ids]
        if bad:
            sys.exit("%s: no such plan %s (have: %s)" % (where, ", ".join(bad), ", ".join(ids)))
        return [x for x in ids if x in v]
    if v not in ids:
        sys.exit("%s: no such plan %r (have: %s)" % (where, v, ", ".join(ids)))
    return ids[ids.index(v) :]


def build_timeline(spec):
    """The calendar: a row for every date, a column for every plan.

    Returns (context, rows, counts, problems). `rows` is the same calendar as
    flat records for --plan; `counts` is how many posts each plan adds up to;
    `problems` is what a rendered page would hide.
    """
    tl = spec["timeline"]
    lang = spec.get("lang", "en")
    strings = dict(DEFAULT_STRINGS, **(spec.get("strings") or {}))
    ev = spec.get("event") or {}
    if not ev.get("start"):
        sys.exit("the spec needs event.start: the calendar is counted from it")
    ev_start = day(ev["start"], "event.start")
    ev_end = day(ev.get("end") or ev["start"], "event.end")

    plans = tl.get("plans") or []
    if not plans:
        sys.exit("timeline.plans is empty: the calendar has a column for each plan")
    ids = [p["id"] for p in plans]
    rec = [bool(p.get("recommended")) for p in plans]

    posts, marks = [], []
    for i, post in enumerate(tl.get("posts") or []):
        where = "timeline.posts[%d] %r" % (i, post.get("label"))
        a, _ = resolve_item(post, ev_start, ev_end, where)
        posts.append((a, post, plans_of(post, ids, where)))
    for i, mark in enumerate(tl.get("marks") or []):
        a, b = resolve_item(mark, ev_start, ev_end, "timeline.marks[%d]" % i)
        marks.append((a, b, mark))
    if not posts:
        sys.exit("timeline.posts is empty")

    first = monday(day(tl["from"], "timeline.from") if tl.get("from") else min(p[0] for p in posts))
    last = max([p[0] for p in posts] + [m[1] for m in marks] + [ev_end])
    if tl.get("to"):
        last = day(tl["to"], "timeline.to")

    problems = []
    counts = dict.fromkeys(ids, 0)
    taken = {}
    by_day = {}
    rows = []
    for a, post, mine in sorted(posts, key=lambda x: x[0]):
        label = post.get("label", "")
        if a < first or a > last:
            problems.append(
                "%r is on %s, outside the dates shown (%s to %s)" % (label, a, first, last)
            )
            continue
        if a.weekday() >= 5:
            problems.append("%r lands on a %s (%s)" % (label, strings["weekdays"][a.weekday()], a))
        for pid in mine:
            counts[pid] += 1
            if (a, pid) in taken:
                problems.append(
                    "plan %s has two posts on %s: %r and %r" % (pid, a, taken[a, pid], label)
                )
            taken[a, pid] = label
        by_day.setdefault(a, []).append(
            {
                "label": label,
                "done": bool(post.get("done")),
                "done_label": strings["done"],
                "cells": [{"on": pid in mine, "rec": rec[i]} for i, pid in enumerate(ids)],
            }
        )
        rows.append({"date": a, "label": label, "plans": mine, "done": bool(post.get("done"))})
    for pid in ids:
        if not counts[pid]:
            problems.append("plan %s has no posts on the calendar" % pid)

    # One of their dates that lasts several days says its name and its range on
    # the first day and tints the days it covers; the event says its name on
    # each of its days.
    marks_by_day, span_days = {}, set()
    for a, b, mark in marks:
        whole = bool(mark.get("event"))
        d = a
        while d <= b:
            if whole or d == a:
                marks_by_day.setdefault(d, []).append(
                    {
                        "label": mark.get("label", ""),
                        "range": span_label(a, b) if a != b and not whole else "",
                        "main": whole,
                    }
                )
            if a != b and not whole:
                span_days.add(d)
            d += datetime.timedelta(days=1)

    weeks, height = [], ROW["chrome"]
    d = first
    while d <= last:
        wk_end = min(d + datetime.timedelta(days=6), last)
        on_event = d <= ev_end and wk_end >= ev_start
        to_go = (ev_start - d).days
        if on_event:
            sub = strings["event_days"]
        elif to_go < 0:
            sub = strings["after_event"]
        else:
            sub = "%d %s" % (to_go, plural(to_go, strings["days_to_go"], lang))
        days = []
        cur = d
        while cur <= wk_end:
            mine = by_day.get(cur, [])
            days.append(
                {
                    "wd": strings["weekdays"][cur.weekday()],
                    "dm": dm(cur),
                    "weekend": cur.weekday() >= 5,
                    "is_event": ev_start <= cur <= ev_end,
                    "marks": marks_by_day.get(cur, []),
                    "mark_span": cur in span_days,
                    "posts": mine,
                    "has_posts": bool(mine),
                    "blank": [{"rec": r} for r in rec],
                }
            )
            height += ROW["post"] * len(mine) if mine else ROW["day"]
            cur += datetime.timedelta(days=1)
        weeks.append(
            {
                "label": span_label(d, wk_end),
                "sub": sub,
                "is_event": on_event,
                "days": days,
                "blank": [{"rec": r} for r in rec],
            }
        )
        height += ROW["week"]
        d += datetime.timedelta(days=7)

    ctx = dict(tl)
    ctx.update(
        {
            "nplans": len(plans),
            "plans": [
                dict(p, recommended=bool(p.get("recommended")), flag=strings["recommended"])
                for p in plans
            ],
            "weeks": weeks,
            "page_h": height,
            "page_h_in": "%.3f" % (height / 96.0),
            "page_w_in": PAGE_W_IN,
            "h_week": ROW["week"],
            "h_day": ROW["day"],
            "h_post": ROW["post"],
        }
    )
    return ctx, rows, counts, problems


def print_plan(spec, rows, counts, problems):
    """The calendar as text -- what --plan shows before any browser starts."""
    ev = spec["event"]
    lang = spec.get("lang", "en")
    strings = dict(DEFAULT_STRINGS, **(spec.get("strings") or {}))
    start = day(ev["start"])
    print("%s: %s to %s\n" % (ev.get("name", "event"), ev["start"], ev.get("end") or ev["start"]))
    for r in rows:
        n = (start - r["date"]).days
        to_go = "%d %s" % (n, plural(n, strings["days_to_go"], lang)) if n > 0 else "-"
        print(
            "  %s %s   %-22s %-8s %s%s"
            % (
                strings["weekdays"][r["date"].weekday()],
                r["date"],
                to_go,
                " ".join(r["plans"]),
                r["label"],
                "  [ready]" if r["done"] else "",
            )
        )
    print("\nposts per plan: %s" % ", ".join("%s %d" % (k, v) for k, v in counts.items()))
    for p in problems:
        print("PROBLEM  %s" % p)
    if not problems:
        print("no problems: every post is inside the dates shown, on a weekday, alone in its plan")


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


def bars(items):
    """Bars drawn to scale: each one's width as a share of the longest. The
    smallest keeps a sliver so it can be seen at all -- when one number is a
    five-hundredth of another, that sliver IS the finding."""
    top = max([float(x.get("value") or 0) for x in items] or [0]) or 1.0
    out = []
    for x in items:
        bar = dict(x)
        bar["pct"] = "%.2f" % max(0.5, 100.0 * float(x.get("value") or 0) / top)
        bar.setdefault("note", "")
        out.append(bar)
    return out


def texts(items):
    """A list of strings as the mustache wants it: a list of {t}."""
    return [{"t": x} if not isinstance(x, dict) else x for x in (items or [])]


def build_context(spec, spec_path):
    """Spec + brand -> the context the template renders. Returns (context,
    page titles in order, plan rows, post counts, problems)."""
    spec_dir = os.path.dirname(os.path.abspath(spec_path))
    strings = dict(DEFAULT_STRINGS, **(spec.get("strings") or {}))
    present = [k for k in spec if k in SECTIONS and spec[k]]
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
    pages, rows, counts, problems = [], [], {}, []

    for n, name in enumerate(present, 1):
        sec = dict(spec[name])
        if name == "cover":
            sec["images"] = [
                {"url": picture(p, spec_dir, "cover.images"), "n": i + 1}
                for i, p in enumerate(sec.get("images") or [])
            ]
            title = sec.get("headline", "")
        elif name == "ready":
            items = []
            for it in sec.get("items") or []:
                card = dict(it)
                if card.get("image"):
                    card["image_url"] = picture(card["image"], spec_dir, "ready.items")
                card["has_image"] = bool(card.get("image"))
                card["url_text"] = card.get("url_text") or (card.get("url") or "").split("://")[-1]
                items.append(card)
            sec["items"] = items
            title = sec.get("title", "")
        elif name == "timeline":
            sec, rows, counts, problems = build_timeline(spec)
            title = sec.get("title", "")
        elif name == "loop":
            # four steps, drawn clockwise from the top of the ring
            steps = [dict(s, n=i + 1) for i, s in enumerate(texts(sec.get("steps")))]
            if len(steps) != 4:
                sys.exit("loop.steps needs exactly four steps: the ring has four places")
            sec["steps"] = steps
            cards = []
            for it in sec.get("examples") or []:
                card = dict(it)
                if card.get("image"):
                    card["image_url"] = picture(card["image"], spec_dir, "loop.examples")
                card["has_image"] = bool(card.get("image"))
                card["url_text"] = card.get("url_text") or (card.get("url") or "").split("://")[-1]
                card.setdefault("note", "")
                cards.append(card)
            sec["examples"] = cards
            title = sec.get("title", "")
        elif name == "audience":
            sec["bars"] = bars(sec.get("bars") or [])
            sec["proof"] = bars(sec.get("proof") or [])
            title = sec.get("title", "")
        elif name == "channels":
            table = []
            for row in sec.get("rows") or []:
                line = dict(row)
                for key in ("size", "format", "what", "est", "src"):
                    line.setdefault(key, "")
                table.append(line)
            sec["rows"] = table
            totals = []
            for tot in sec.get("totals") or []:
                tile = dict(tot)
                tile["recommended"] = bool(tile.get("recommended"))
                tile.setdefault("note", "")
                totals.append(tile)
            sec["totals"] = totals
            sec["has_totals"] = bool(totals)
            title = sec.get("title", "")
        elif name == "options":
            items = []
            for it in sec.get("items") or []:
                opt = dict(it)
                opt["points"] = texts(opt.get("points"))
                opt["recommended"] = bool(opt.get("recommended"))
                opt["recommended_label"] = strings["recommended"]
                # every key the card prints, so a missing one cannot fall
                # through to the same key of the section around it
                for key in ("tag", "count", "cadence", "price", "price_note"):
                    opt.setdefault(key, "")
                items.append(opt)
            sec["items"] = items
            title = sec.get("title", "")
        else:  # process
            blocks = []
            for block in sec.get("blocks") or []:
                blk = dict(block)
                blk["points"] = [dict(p, n=j + 1) for j, p in enumerate(texts(blk.get("points")))]
                blocks.append(blk)
            sec["blocks"] = blocks
            sec["has_next"] = bool(sec.get("next"))
            title = sec.get("title", "")
        sec["page_no"] = n
        # One list, in the spec's order: the template draws whichever section
        # each entry is, so the order of the pages is the order of the spec.
        pages.append({"is_" + name: True, name: sec})
        pages[-1].update({"is_" + other: False for other in SECTIONS if other != name})
        ctx[name] = sec
        ctx.setdefault("titles", []).append(title)
    ctx["pages"] = pages
    return ctx, ctx.pop("titles"), rows, counts, problems


def verify(out, titles, brand):
    """Pages, their titles, and the faces in the file -- read back from the PDF."""
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
    ap.add_argument("--html-out", help="where to leave the HTML (the page to look at first)")
    ap.add_argument("--out", help="write the PDF here instead of the spec's 'out'")
    ap.add_argument(
        "--plan",
        action="store_true",
        help="the calendar as text, with every post's date, days to go and plans -- no browser",
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
        _, rows, counts, problems = build_timeline(spec)
        print_plan(spec, rows, counts, problems)
        sys.exit(1 if problems else 0)

    ctx, titles, _, _, problems = build_context(spec, spec_path)
    if problems:
        sys.exit("the calendar has problems (see --plan):\n  " + "\n  ".join(problems))
    html = _card.render_template(load_template(spec.get("template", "campaign")), ctx)
    out = os.path.abspath(a.out) if a.out else spec_out(spec, spec_path)

    html_path = a.html_out or os.path.join(
        _env.resolve("temp"), "proposals", os.path.splitext(os.path.basename(out))[0] + ".html"
    )
    os.makedirs(os.path.dirname(os.path.abspath(html_path)) or ".", exist_ok=True)
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
