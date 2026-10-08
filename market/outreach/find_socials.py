"""Find each event's social accounts on the organiser's own pages.

An account is only worth tagging if it is the organiser's, and the surest proof
of that is their own website linking to it. This reads the pages named for each
lead (`local/sites.json`: `{"<lead id>": ["https://...", ...]}`; a lead with no
entry gets the domain of its first address), collects every link to X, Threads,
LinkedIn, Instagram, YouTube and Facebook, and keeps the one named most often.

    python market/outreach/find_socials.py --plan              # the pages it would read
    python market/outreach/find_socials.py                     # -> data/socials.json
    python market/outreach/find_socials.py --only <lead-id> --refresh
    python market/outreach/find_socials.py --threads           # then look for Threads

Few organisers link Threads. `--threads` opens threads.com/@<name> in a headless
browser for the Instagram and X names already found and records WHOSE profile
that is (its title) under `threads_guess`: a guess to be read by a person, never
written to `threads` by itself -- the same name is often somebody else there.
What the person settles goes in `local/socials-fixed.json`
(`{"<lead id>": {"threads": "https://...", "note": "..."}}`) and wins from then on.

    python market/outreach/find_socials.py --render --only <lead-id>   # a site built by scripts
    python market/outreach/find_socials.py --writes --versions data/versions.json

`--render` reads the pages with the headless browser, for a site whose links
only exist once its scripts have run. `--writes` also leaves the database
batches (`data/socials-writes-N.json`) that put `socials` and `socials_note` on
each lead of the pipeline page.

Pages are cached under `data/pages/` (`--refresh` reads again). A site that
refuses the request is listed under `refused` and left alone. Standard library
only; `--threads` and `--render` need Edge or Chrome installed.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = 50  # the most writes one database batch takes
AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)
# network -> (pattern with the account in group 1, names that are the network's own pages)
NETWORKS = {
    "x": (
        r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/(?:#!/)?@?([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_])",
        {"intent", "share", "home", "search", "hashtag", "i", "widgets", "privacy", "tos", "login"},
    ),
    "threads": (r"https?://(?:www\.)?threads\.(?:net|com)/@([A-Za-z0-9_.]+)", set()),
    "linkedin": (
        r"https?://(?:[a-z]+\.)?linkedin\.com/((?:company|showcase|school|groups)/[A-Za-z0-9_%\-.]+)",
        set(),
    ),
    "instagram": (
        r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)",
        {"p", "reel", "reels", "explore", "accounts", "stories", "tv"},
    ),
    "youtube": (
        r"https?://(?:www\.)?youtube\.com/(@[\w.\-]+|channel/[\w\-]+|c/[\w.\-]+|user/[\w.\-]+)",
        set(),
    ),
    "facebook": (
        r"https?://(?:www\.|m\.)?facebook\.com/([A-Za-z0-9.\-]+)",
        set(
            "sharer sharer.php tr plugins dialog share.php share login events groups media "
            "profile.php pages people watch photo.php help".split()
        ),
    ),
}
HOME = {
    "x": "https://x.com/{}",
    "threads": "https://www.threads.com/@{}",
    "linkedin": "https://www.linkedin.com/{}",
    "instagram": "https://www.instagram.com/{}",
    "youtube": "https://www.youtube.com/{}",
    "facebook": "https://www.facebook.com/{}",
}


def fetch(url: str) -> str:
    """Return a page's HTML, or raise OSError with the reason it could not be read."""
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=25) as r:  # noqa: S310 -- http(s) only, checked below
        return r.read(3_000_000).decode("utf-8", "replace")


def accounts(html: str) -> dict:
    """Return every account linked in a page, per network, with how often each is linked."""
    found = {}
    text = html.replace("\\/", "/")
    for net, (pattern, own) in NETWORKS.items():
        names = [m.rstrip("./") for m in re.findall(pattern, text, flags=re.IGNORECASE)]
        found[net] = Counter(n for n in names if n.lower() not in own)
    return found


def browser() -> str | None:
    """Return a Chromium browser that can run headless here, or None."""
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    for root in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        for tail in (
            "Microsoft/Edge/Application/msedge.exe",
            "Google/Chrome/Application/chrome.exe",
        ):
            path = Path(os.environ.get(root, "")) / tail
            if os.environ.get(root) and path.is_file():
                return str(path)
    return None


def rendered(exe: str, url: str) -> str:
    """Return a page's HTML after its scripts have run, read with a headless browser."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        try:
            return subprocess.run(  # noqa: S603 -- the browser found above, a fixed argument list
                [
                    exe,
                    "--headless=new",
                    "--disable-gpu",
                    f"--user-data-dir={profile}",
                    "--virtual-time-budget=12000",
                    "--dump-dom",
                    url,
                ],
                capture_output=True,
                timeout=60,
                check=False,
            ).stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired as e:
            # one page that never settles must not end the run
            msg = "the browser gave up after 60 s"
            raise OSError(msg) from e


def threads_title(exe: str, name: str) -> str:
    """Return whose Threads profile @name is ("Name (@name)"), or "" when there is none."""
    try:
        out = rendered(exe, f"https://www.threads.com/@{name}")
    except OSError:
        return ""
    m = re.search(r"<title[^>]*>([^<]*\(@[^)]+\))[^<]*Threads", out)
    return m.group(1).strip() if m else ""


def note_for(row: dict) -> str:
    """Return the line the page shows under a lead's accounts: their source, and what is missing."""
    if not row["pages"] and row["refused"]:
        said = ["Their site refuses automated reading, so nothing was looked up there."]
    elif not row["x"] and not row["threads"]:
        said = ["Their site links no X or Threads account."]
    elif not row["x"]:
        said = ["Their site links no X account."]
    elif not row["threads"]:
        said = ["From their own site. No Threads account found."]
    else:
        said = ["From their own site."]
    if "threads" in row["fixed"]:
        said.append("Threads: the profile under their Instagram name carries their name.")
    return " ".join([*said, row.get("note", "")]).strip()


def main() -> None:
    """Read each lead's pages, pick its accounts, and write data/socials.json."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--leads", type=Path, default=HERE / "data" / "leads")
    ap.add_argument("--sites", type=Path, default=HERE / "local" / "sites.json")
    ap.add_argument("--out", type=Path, default=HERE / "data" / "socials.json")
    ap.add_argument("--only", action="append", help="a lead id; repeat for several")
    ap.add_argument("--refresh", action="store_true", help="read pages again instead of the cache")
    ap.add_argument("--threads", action="store_true", help="look up Threads for the names found")
    ap.add_argument("--render", action="store_true", help="read pages with a headless browser")
    ap.add_argument("--fixed", type=Path, default=HERE / "local" / "socials-fixed.json")
    ap.add_argument("--writes", action="store_true", help="also write the page's database batches")
    ap.add_argument(
        "--versions", type=Path, help="{lead id: version on the page}; 1 when not named"
    )
    ap.add_argument("--plan", action="store_true", help="list the pages and stop")
    args = ap.parse_args()

    sites = json.loads(args.sites.read_text(encoding="utf-8")) if args.sites.is_file() else {}
    fixed = json.loads(args.fixed.read_text(encoding="utf-8")) if args.fixed.is_file() else {}
    leads = {
        p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(args.leads.glob("*.json"))
    }
    if not leads:
        sys.exit(f"No leads under {args.leads}: run leads_from_csv.py first.")
    todo = {k: v for k, v in leads.items() if not args.only or k in args.only}
    pages = {
        k: sites.get(k) or ([f"https://www.{v['org_key']}/"] if v.get("org_key") else [])
        for k, v in todo.items()
    }
    nowhere = [k for k, urls in pages.items() if not urls]
    print(f"{len(todo)} leads, {sum(len(u) for u in pages.values())} pages to read")
    if nowhere:
        print(f"  no page named for {len(nowhere)}: {', '.join(nowhere)}")
    if args.plan:
        for k, urls in pages.items():
            print(f"  {k}: {' '.join(urls) or '-'}")
        return

    result = json.loads(args.out.read_text(encoding="utf-8")) if args.out.is_file() else {}
    cache = args.out.parent / "pages"
    cache.mkdir(parents=True, exist_ok=True)
    exe = browser() if args.threads or args.render else None
    if (args.threads or args.render) and not exe:
        sys.exit("--threads and --render need Edge or Chrome, and neither was found.")
    for key, urls in pages.items():
        row = {"pages": [], "refused": [], "candidates": {}}
        totals = {net: Counter() for net in NETWORKS}
        for n, url in enumerate(urls):
            if not url.lower().startswith(("http://", "https://")):
                continue
            kept = cache / f"{key}-{n}{'-rendered' if args.render else ''}.html"
            try:
                if args.refresh or not kept.is_file():
                    kept.write_text(
                        rendered(exe, url) if args.render else fetch(url), encoding="utf-8"
                    )
                html = kept.read_text(encoding="utf-8")
            except (OSError, urllib.error.URLError, ValueError) as e:
                row["refused"].append(f"{url} ({e})")
                continue
            row["pages"].append(url)
            for net, counts in accounts(html).items():
                totals[net].update(counts)
        for net, counts in totals.items():
            ranked = [name for name, _ in counts.most_common()]
            row[net] = HOME[net].format(ranked[0]) if ranked else ""
            if len(ranked) > 1:
                row["candidates"][net] = ranked
        # what a person settled (local/socials-fixed.json) wins over what the pages suggest
        settled = fixed.get(key, {})
        row["fixed"] = sorted(n for n in settled if n in NETWORKS)
        row.update({n: settled[n] for n in row["fixed"]})
        row["note"] = settled.get("note", "")
        old = result.get(key, {})
        row["threads_guess"] = old.get("threads_guess", {})
        if args.threads and not row["threads"]:
            names = {
                u.rstrip("/").split("/")[-1].lstrip("@").lower()
                for u in (row["x"], row["instagram"])
                if u
            }
            row["threads_guess"] = {n: threads_title(exe, n) for n in sorted(names)}
        result[key] = row
        got = [net for net in NETWORKS if row[net]]
        guess = [f"@{n} = {t}" for n, t in row["threads_guess"].items() if t]
        print(
            f"  {key}: {', '.join(got) or 'nothing'}"
            + (f" | threads? {'; '.join(guess)}" if guess else "")
        )
        if row["refused"]:
            print(f"    refused: {'; '.join(row['refused'])}")
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")
    if args.writes:
        versions = json.loads(args.versions.read_text(encoding="utf-8")) if args.versions else {}
        writes = [
            {
                "op": "update",
                "collection": "leads",
                "doc_id": key,
                "if_version": versions.get(key, 1),
                "data": {
                    "socials": {net: row[net] for net in NETWORKS if row[net]},
                    "socials_note": note_for(row),
                },
            }
            for key, row in result.items()
            if key in todo
        ]
        for n in range(0, len(writes), BATCH):
            part = args.out.parent / f"socials-writes-{n // BATCH + 1}.json"
            part.write_text(json.dumps(writes[n : n + BATCH], ensure_ascii=False), encoding="utf-8")
            print(f"wrote {part}")


if __name__ == "__main__":
    main()
