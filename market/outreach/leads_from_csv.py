"""Turn a list of conferences into the pipeline page's lead records.

The pipeline page (`conference-pipeline.html`, published as a private Artifact
with a database) keeps one record per event. This reads the contact list -- a
CSV with the columns `Event`, `When / Where`, `Email` (several separated by
`;`), `Notes`, and optionally `Organiser` -- and writes one JSON document per
event, plus the batches of database writes that put them on the page.

    python market/outreach/leads_from_csv.py --plan              # count, write nothing
    python market/outreach/leads_from_csv.py                     # local/contacts.csv -> data/
    python market/outreach/leads_from_csv.py --csv <list.csv> --have data/on-page.txt

`--have` names a file of lead ids already on the page (one per line, from a
listing of its `leads` collection): those events are left out, so a longer list
adds its new events and never resets one that has been worked.

The list and everything made from it stay local (`local/` and `data/` are
gitignored): it is other people's addresses. Standard library only.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
BATCH = 50  # the most writes one database batch takes
NO_ADDRESS = "Find a person and an address"


def slug(event: str) -> str:
    """Return the lead id for an event: its name in lower case, words joined by dashes."""
    return re.sub(r"[^a-z0-9]+", "-", event.lower()).strip("-")


def date_sort(text: str) -> str | None:
    """Return the first day named in a free-text date ("27 Sep-1 Oct 2027") as yyyy-mm-dd."""
    day = re.search(r"(\d{1,2})(?:\s*[–-]\s*\d{1,2})?\s+(" + "|".join(MONTHS) + r")", text)
    year = re.search(r"(20\d{2})", text)
    if not (day and year):
        return None
    return f"{year.group(1)}-{MONTHS[day.group(2)]:02d}-{int(day.group(1)):02d}"


def lead(row: dict) -> dict:
    """Return the page's record for one row of the list."""
    emails = [e.strip() for e in (row.get("Email") or "").split(";") if e.strip()]
    notes = (row.get("Notes") or "").strip()
    when = (row.get("When / Where") or "").strip()
    return {
        "event": row["Event"].strip(),
        "org": (row.get("Organiser") or "").strip(),
        # one organiser, several events: the same inbox must not get one email per event
        "org_key": emails[0].split("@")[-1].lower() if emails else "",
        "when": when,
        "date_sort": date_sort(when),
        "emails": emails,
        "audience": notes if emails else "",
        "access_note": "" if emails else notes,
        "stage": "new" if emails else "blocked",
        "next_step": "Check the line-up, pick the film" if emails else NO_ADDRESS,
        "decision": "",
        "owner_note": "",
        "log": [],
    }


def main() -> None:
    """Read the list, say what it holds, and write the records unless --plan."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", type=Path, default=HERE / "local" / "contacts.csv")
    ap.add_argument("--out", type=Path, default=HERE / "data")
    ap.add_argument("--have", type=Path, help="lead ids already on the page, one per line")
    ap.add_argument("--plan", action="store_true", help="count what would be written and stop")
    args = ap.parse_args()

    if not args.csv.is_file():
        sys.exit(f"No list at {args.csv}: put the CSV there or pass --csv.")
    have = set(args.have.read_text(encoding="utf-8").split()) if args.have else set()
    with args.csv.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("Event") or "").strip()]
    leads = {slug(r["Event"]): lead(r) for r in rows}
    if len(leads) != len(rows):
        sys.exit("Two events share a name: every event needs its own.")
    new = {k: v for k, v in leads.items() if k not in have}

    with_email = [v for v in new.values() if v["emails"]]
    orgs = len({v["org_key"] for v in with_email})
    print(f"{len(rows)} events in the list, {len(rows) - len(new)} already on the page")
    print(f"{len(new)} to add:")
    print(f"  {len(with_email)} with an address ({orgs} organisers)")
    print(f"  {len(new) - len(with_email)} with a form or a phone number only")
    print(f"  {-(-len(new) // BATCH)} database batch(es) of up to {BATCH}")
    if args.plan or not new:
        return

    docs = args.out / "leads"
    docs.mkdir(parents=True, exist_ok=True)
    writes = []
    for key, doc in new.items():
        path = docs / f"{key}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        writes.append({"op": "set", "collection": "leads", "doc_id": key, "file_path": str(path)})
    for n in range(0, len(writes), BATCH):
        part = args.out / f"writes-{n // BATCH + 1}.json"
        part.write_text(json.dumps(writes[n : n + BATCH], indent=1), encoding="utf-8")
        print(f"wrote {part}")


if __name__ == "__main__":
    main()
