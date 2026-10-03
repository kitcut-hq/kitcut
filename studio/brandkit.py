#!/usr/bin/env python
"""A project's brand: whatever the person has -- a zip of the brand folder, PDF guidelines, logos,
font files, slides -- read into a brand card every episode follows.

A project's Pictures are things to show; its brand is how everything looks and sounds: the
colours (drawings included), every typeface, the logo and its rules, the tone of voice. The look
(drawn, painted, collage) still decides the drawing style. One brand per project:

    <project library>/brand/                     (library.dir_of: never in git, never public)
        files/<fid>.json  files/<fid>.bin        what the person sent, as sent, kept: reading
                                                 again starts from them (sent in parts, add_file /
                                                 put_part / finish, because the site forwards at
                                                 most 4.4 MB a request)
        read/                                    what reading found (ingest):
            inventory.json                       every file, inside zips too: used for what, or
                                                 skipped and why
            pages/p001.jpg  pages/p001.t.jpg     each PDF page drawn (pdfium), and a thumbnail
            images/i001.png                      every picture, normalised to PNG (SVG drawn by the
                                                 browser, PSD flattened, slides' and PDFs' own)
            fonts/f001.ttf                       every font file, woff/woff2 unpacked to sfnt
            text.txt                             all the words found, page by page
        card.json                                the brand card: Claude's reading of all that
                                                 (read()), then the person's corrections (edit())
        assets/                                  what an episode gets (build_assets): the logos
                                                 trimmed (brand_logo*.png), fonts/ the faces in
                                                 use, brand.js, used.json
        standin/                                 free stand-ins fetched from Google Fonts
        preview/<look>.png                       three frames the film engine drew with the brand
        state.json                               {state, step, done, total, error, server, at,
                                                 cost_usd, reads}

The state is empty (nothing sent), files (sent, not read), reading, ready or failed. Reading:
ingest() (no Claude: unpack, draw, read, normalise), then one Claude call with no tools that sees
the pages that matter most and a sheet of the pictures and writes the card (ask), held to its
shape (clean_card), then the assets and the preview. An episode of the project gets the assets
(seed: fonts into its manifest, logos as SK.image names, brand.js before film.js) and a note
(note). Uploaded fonts are used only once the person ticked that they may be (fonts_consent);
until then every face is a free stand-in from Google Fonts, named as such on the card.

    python studio/brandkit.py --files a.zip b.pdf --out <dir> --plan   read, no Claude: what
                                                                       it found, what Claude sees
    python studio/brandkit.py --files ... --out <dir> [--look drawn]   read, ask, build, preview
    python studio/brandkit.py --out <dir> --again                      assets and preview again
"""

import os
import io
import re
import sys
import json
import time
import shutil
import asyncio
import zipfile
import hashlib
import secrets
import argparse
import importlib
import contextlib
import subprocess
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import locks  # noqa: E402
from film import KIT, _write_json  # noqa: E402


# ------------------------------------------------------------------ limits
PART = 4 * 1024 * 1024  # the most one part may carry (the site sends ~3.8 MB)
MAX_FILE = 200 * 1024 * 1024  # one file the person sends
MAX_TOTAL = 500 * 1024 * 1024  # everything a brand keeps
MAX_FILES = 60
MAX_ENTRIES = 4000  # files inside archives, all together
MAX_UNPACKED = 1500 * 1024 * 1024  # bytes unpacked from archives, all together
MAX_DEPTH = 3  # a zip in a zip in a zip
MAX_PAGES = 120  # pages drawn (PDFs, all together)
MAX_IMAGES = 240  # pictures kept
MAX_FONTS = 80
MAX_SVG = 40  # SVGs drawn by the browser (each is a browser start)
MAX_TEXT = 400_000  # characters of text kept
ASK_PAGES = 10  # pages Claude sees
SHEET_CELLS = 30  # pictures on the sheet Claude sees
PAGE_W = 1400  # a drawn page's width, px
READS_A_DAY = 12  # Claude reads of one brand in 24 h
STALE_S = 30 * 60  # a read with no progress this long is one nobody is doing any more

ROLES = ("primary", "secondary", "accent", "background", "text", "neutral")
LOGO_ROLES = ("primary", "on_dark", "on_light", "mark", "other")
TYPE_ROLES = ("headline", "body")
FID = re.compile(r"^b-[a-z2-7]{10}$")
HEX = re.compile(r"(?<![0-9A-Za-z&])#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})(?![0-9A-Za-z])")
RGB = re.compile(
    r"\bR(?:GB)?\s*[:=]?\s*(\d{1,3})\s*[,/ ]\s*G?\s*[:=]?\s*(\d{1,3})\s*[,/ ]\s*B?\s*[:=]?\s*"
    r"(\d{1,3})\b"
)
FAMILY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ]{0,39}$")  # a Google Fonts family name
JUNK = re.compile(r"(^|/)(__MACOSX|\.DS_Store|Thumbs\.db|desktop\.ini|\._[^/]*)(/|$)", re.I)
_B32 = "abcdefghijklmnopqrstuvwxyz234567"


class BrandError(Exception):
    """Why a brand request was refused: an HTTP status and words for a person."""

    def __init__(self, status, text):
        super().__init__(text)
        self.status, self.text = status, text


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _read_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------ where a brand lives
def dir_of(lib):
    import library  # noqa: PLC0415 -- library imports this module for seed and note

    return os.path.join(library.dir_of(lib), "brand")


@contextlib.contextmanager
def _lock(d):
    """The brand's own lock (two servers share the home during a ship), held only for the short
    writes: a read takes minutes, and says so in state.json instead."""
    os.makedirs(d, exist_ok=True)
    with locks.locked(os.path.join(d, ".lock")):
        yield


def state_of(d):
    st = _read_json(os.path.join(d, "state.json"), {}) or {}
    if not st.get("state"):
        st["state"] = "files" if _files(d) else "empty"
    return st


def _set_state(d, **fields):
    st = _read_json(os.path.join(d, "state.json"), {}) or {}
    st.update(fields, at=_now())
    _write_json(os.path.join(d, "state.json"), st)
    return st


# ------------------------------------------------------------------ what the person sends
def _files(d):
    out = []
    fd = os.path.join(d, "files")
    if not os.path.isdir(fd):
        return out
    for n in sorted(os.listdir(fd)):
        if n.endswith(".json"):
            m = _read_json(os.path.join(fd, n))
            if isinstance(m, dict) and FID.match(m.get("id", "")):
                out.append(m)
    return sorted(out, key=lambda m: m.get("added", ""))


def clean_name(name):
    """A file's name as the person called it, for the page: never a path."""
    name = os.path.basename(str(name or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    return name[-120:] or "file"


def add_file(d, name, size):
    """Start a file of `size` bytes: its id, for put_part."""
    if not isinstance(size, int) or size <= 0:
        raise BrandError(400, "Say how big the file is.")
    if size > MAX_FILE:
        raise BrandError(413, "That file is over %d MB." % (MAX_FILE // 1048576))
    with _lock(d):
        have = _files(d)
        if len(have) >= MAX_FILES:
            raise BrandError(409, "A brand takes up to %d files: zip some together." % MAX_FILES)
        if sum(m["size"] for m in have) + size > MAX_TOTAL:
            raise BrandError(413, "A brand takes up to %d MB in all." % (MAX_TOTAL // 1048576))
        fid = "b-" + "".join(secrets.choice(_B32) for _ in range(10))
        m = {"id": fid, "name": clean_name(name), "size": size, "got": 0, "done": False}
        m["added"] = _now()
        os.makedirs(os.path.join(d, "files"), exist_ok=True)
        open(os.path.join(d, "files", fid + ".bin"), "wb").close()
        _write_json(os.path.join(d, "files", fid + ".json"), m)
    return m


def put_part(d, fid, offset, data):
    """One part of a file, at its offset: parts come in order; a part sent again (the page
    retried after a lost answer) is taken as already there."""
    if not FID.match(fid or ""):
        raise BrandError(404, "No such file.")
    if len(data) > PART:
        raise BrandError(413, "A part is at most %d MB." % (PART // 1048576))
    meta_p = os.path.join(d, "files", fid + ".json")
    with _lock(d):
        m = _read_json(meta_p)
        if not m:
            raise BrandError(404, "No such file.")
        if m["done"]:
            raise BrandError(409, "That file is complete.")
        if offset + len(data) <= m["got"]:
            return m  # sent again
        if offset != m["got"]:
            raise BrandError(409, "Part out of order: the file has %d bytes." % m["got"])
        if m["got"] + len(data) > m["size"]:
            raise BrandError(413, "That is more than the file's size.")
        with open(os.path.join(d, "files", fid + ".bin"), "ab") as f:
            f.write(data)
        m["got"] += len(data)
        _write_json(meta_p, m)
    return m


def finish(d, fid):
    meta_p = os.path.join(d, "files", (fid or "") + ".json")
    with _lock(d):
        m = _read_json(meta_p) if FID.match(fid or "") else None
        if not m:
            raise BrandError(404, "No such file.")
        if m["got"] != m["size"]:
            raise BrandError(409, "The file has %d of its %d bytes." % (m["got"], m["size"]))
        m["done"] = True
        _write_json(meta_p, m)
        st = state_of(d)
        if st["state"] in ("empty", "ready", "failed"):
            _set_state(d, state="files", stale=st["state"] == "ready")
    return m


def remove_file(d, fid):
    with _lock(d):
        p = os.path.join(d, "files", (fid or "") + ".json")
        if not FID.match(fid or "") or not os.path.exists(p):
            return False
        for ext in (".json", ".bin"):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(d, "files", fid + ext))
        if state_of(d)["state"] == "ready":
            _set_state(d, stale=True)
    return True


def remove(d):
    """The whole brand: files, reading, card, assets."""
    with _lock(d):
        for n in os.listdir(d) if os.path.isdir(d) else []:
            if n == ".lock":
                continue
            p = os.path.join(d, n)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


# ------------------------------------------------------------------ what a file is
def sniff(head, name=""):
    """What a file is, from its first bytes (its name only breaks ties): a kind, or None."""
    low = name.lower()
    if head.startswith(b"%PDF"):
        return "pdf"  # an .ai saved with PDF compatibility too
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "zip"
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"BM", b"II*\x00", b"MM\x00*")):
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head.startswith(b"8BPS"):
        return "psd"
    if head[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"wOFF", b"wOF2", b"ttcf"):
        return "font"
    if head[:4] == b"\x00\x00\x01\x00" and low.endswith(".ico"):
        return "image"
    if head.startswith((b"%!PS", b"\xc5\xd0\xd3\xc6")):
        return "eps"
    if head[4:8] == b"ftyp" or head.startswith((b"\x1a\x45\xdf\xa3", b"OggS", b"ID3", b"RIFF")):
        return "media"
    if head.startswith(b"Rar!") or head.startswith(b"7z\xbc\xaf"):
        return "archive"
    try:
        text = head.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        try:
            text = head[: len(head) - 3].decode("utf-8-sig")
        except UnicodeDecodeError:
            return None
    if re.search(r"[\x00-\x08\x0e-\x1f]", text):
        return None
    if "<svg" in text[:4000].lower():
        return "svg"
    if low.endswith((".css", ".scss")):
        return "css"
    return "text"


SKIP_WHY = {
    "eps": "an EPS needs Illustrator: export it as PDF, SVG or PNG",
    "media": "a video or a recording: not part of a brand card",
    "archive": "a RAR or 7z archive: send a zip instead",
    None: "not a file this reads",
}


# ------------------------------------------------------------------ reading what was sent
class Ingest:
    """Everything found in the sent files, written into read/ (see the module doc)."""

    def __init__(self, out):
        self.out = out
        for sub in ("pages", "images", "fonts"):
            os.makedirs(os.path.join(out, sub), exist_ok=True)
        self.files, self.pages, self.images, self.fonts = [], [], [], []
        self.text, self.svgs, self.theme = [], [], {"colors": [], "fonts": []}
        self.entries = self.unpacked = 0
        self._seen = set()  # pictures already kept, by a hash of their pixels

    # every file, at any depth, comes through here
    def take(self, data, path, depth=0):
        if JUNK.search(path):
            return
        kind = sniff(data[:8192], path)
        row = {"path": path, "kind": kind or "unknown", "bytes": len(data)}
        self.files.append(row)
        try:
            if kind == "zip":
                row["used"] = self.zip(data, path, depth)
            elif kind == "pdf":
                row["used"] = self.pdf(data, path)
            elif kind in ("image", "psd"):
                row["used"] = self.image(data, path)
            elif kind == "svg":
                self.svgs.append((data, path, row))
                row["used"] = "drawn below"
            elif kind == "font":
                row["used"] = self.font(data, path)
            elif kind in ("text", "css"):
                row["used"] = self.words(data, path, kind)
            else:
                row["skipped"] = SKIP_WHY.get(kind, SKIP_WHY[None])
        except Exception as e:  # noqa: BLE001 -- one broken file never stops the others
            row["skipped"] = "could not be read (%s)" % (str(e)[:120] or type(e).__name__)
        if not row.get("used") and not row.get("skipped"):
            row["skipped"] = "nothing in it to use"

    def zip(self, data, path, depth):
        if depth >= MAX_DEPTH:
            return None
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
        office = "[Content_Types].xml" in names
        if office:
            self.office(zf, names, path)
        n = 0
        for info in zf.infolist():
            if info.is_dir() or JUNK.search(info.filename):
                continue
            if office and not info.filename.startswith(("word/media/", "ppt/media/", "xl/media/")):
                continue  # an office file's own parts were read by office()
            if self.entries >= MAX_ENTRIES or self.unpacked + info.file_size > MAX_UNPACKED:
                self.files.append(
                    {
                        "path": "%s/%s" % (path, info.filename),
                        "kind": "?",
                        "skipped": "past the limit",
                    }
                )
                break
            if info.compress_size and info.file_size / info.compress_size > 300:
                continue  # a zip bomb's entry, not a brand file
            self.entries += 1
            self.unpacked += info.file_size
            self.take(zf.read(info), "%s/%s" % (path, info.filename), depth + 1)
            n += 1
        return "%s, %d files" % ("an office file" if office else "unpacked", n)

    def office(self, zf, names, path):
        """A .pptx/.docx/.xlsx (or a Keynote's zip): its words, its theme's colours and fonts;
        its pictures come through take() like any other."""
        words = []
        for n in sorted(names):
            if re.match(r"(ppt/slides/slide\d+|word/document)\.xml$", n):
                xml = zf.read(n).decode("utf-8", "replace")
                runs = re.findall(r"<a:t>([^<]*)</a:t>|<w:t[^>]*>([^<]*)</w:t>", xml)
                words.append(" ".join(a or b for a, b in runs))
            if re.match(r"(ppt|word|xl)/theme/theme\d*\.xml$", n):
                xml = zf.read(n).decode("utf-8", "replace")
                scheme = re.search(r"<a:clrScheme.*?</a:clrScheme>", xml, re.S)
                for name, val in re.findall(
                    r"<a:(\w+)>\s*<a:(?:srgbClr val|sysClr [^>]*lastClr)=\"([0-9A-Fa-f]{6})\"",
                    scheme.group(0) if scheme else "",
                ):
                    self.theme["colors"].append({"hex": "#" + val.upper(), "slot": name})
                for role, face in re.findall(
                    r"<a:(majorFont|minorFont)>\s*<a:latin typeface=\"([^\"]+)\"", xml
                ):
                    self.theme["fonts"].append({"role": role, "family": face})
        text = "\n".join(w for w in words if w.strip())
        if text:
            self.text.append("== %s ==\n%s" % (path, text))

    def pdf(self, data, path):
        import pypdfium2 as pdfium  # noqa: PLC0415

        doc = pdfium.PdfDocument(data)
        n = len(doc)
        drawn = 0
        os.makedirs(os.path.join(self.out, "pdfs"), exist_ok=True)
        keep = "d%02d.pdf" % (len(os.listdir(os.path.join(self.out, "pdfs"))) + 1)
        with open(os.path.join(self.out, "pdfs", keep), "wb") as f:  # a logo's crop, drawn sharp
            f.write(data)
        for i in range(n):
            page = doc[i]
            words = page.get_textpage().get_text_range() or ""
            if len(self.pages) >= MAX_PAGES:
                if words.strip():
                    self.text.append("== %s page %d ==\n%s" % (path, i + 1, words))
                continue
            pid = "p%03d" % (len(self.pages) + 1)
            w, h = page.get_size()
            scale = min(PAGE_W / max(w, 1), 3000 / max(h, 1))
            im = page.render(scale=scale).to_pil().convert("RGB")
            im.save(os.path.join(self.out, "pages", pid + ".jpg"), quality=86)
            th = im.copy()
            th.thumbnail((480, 480))
            th.save(os.path.join(self.out, "pages", pid + ".t.jpg"), quality=82)
            self.pages.append(
                {
                    "id": pid,
                    "from": path,
                    "page": i + 1,
                    "of": n,
                    "pdf": keep,
                    "w": im.width,
                    "h": im.height,
                    "chars": len(words.strip()),
                }
            )
            if words.strip():
                self.text.append("== %s page %d (%s) ==\n%s" % (path, i + 1, pid, words))
            for obj in page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,), max_depth=3):
                with contextlib.suppress(Exception):
                    x0, y0, x1, y1 = obj.get_bounds()
                    if (x1 - x0) * (y1 - y0) > 0.8 * w * h:
                        continue  # the page itself as a picture (a scan, an exported slide)
                try:
                    pic = obj.get_bitmap(render=False).to_pil()
                except Exception:  # noqa: BLE001,S112 -- a mask or an odd colour space
                    continue
                if min(pic.size) >= 48:
                    self.keep(pic, "%s page %d" % (path, i + 1))
            drawn += 1
        doc.close()
        return "%d of %d pages drawn" % (drawn, n) if drawn < n else "%d pages" % n

    def image(self, data, path):
        im = Image.open(io.BytesIO(data))
        if getattr(im, "n_frames", 1) > 1 and im.format in ("ICO",):
            im = max((im.getimage(k) for k in range(im.n_frames)), key=lambda x: x.size[0])
        im.load()
        iid = self.keep(im, path)
        return "picture %s" % iid if iid else "a copy of a picture already kept"

    def keep(self, im, src):
        """A picture into images/, once: normalised to RGBA PNG at most 2000 px. Its id, or None
        for a duplicate, a sliver, or past the limit."""
        if len(self.images) >= MAX_IMAGES or min(im.size) < 16:
            return None
        if im.mode in ("P", "LA", "L", "1", "PA") or "transparency" in im.info:
            im = im.convert("RGBA")
        elif im.mode == "CMYK":
            im = im.convert("RGB")
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im.thumbnail((2000, 2000))
        small = im.convert("RGBA").resize((16, 16))
        key = hashlib.sha1(small.tobytes()).hexdigest()
        if key in self._seen:
            return None
        self._seen.add(key)
        iid = "i%03d" % (len(self.images) + 1)
        im.save(os.path.join(self.out, "images", iid + ".png"))
        alpha = im.mode == "RGBA" and im.getchannel("A").getextrema()[0] < 250
        self.images.append(
            {
                "id": iid,
                "from": src,
                "w": im.width,
                "h": im.height,
                "alpha": bool(alpha),
                "colours": dominant(im),
            }
        )
        return iid

    def font(self, data, path):
        from fontTools.ttLib import TTCollection, TTFont  # noqa: PLC0415

        fonts = (
            list(TTCollection(io.BytesIO(data)).fonts)
            if data[:4] == b"ttcf"
            else [TTFont(io.BytesIO(data))]
        )
        got = []
        for ft in fonts:
            if len(self.fonts) >= MAX_FONTS:
                break
            info = font_info(ft)
            if any(
                (f["family"], f["weight"], f["italic"])
                == (info["family"], info["weight"], info["italic"])
                for f in self.fonts
            ):
                continue
            fid = "f%03d" % (len(self.fonts) + 1)
            ft.flavor = None  # woff and woff2 unpacked: every browser and PIL read sfnt
            ext = "otf" if "CFF " in ft or "CFF2" in ft else "ttf"
            ft.save(os.path.join(self.out, "fonts", "%s.%s" % (fid, ext)))
            self.fonts.append({"id": fid, "file": "%s.%s" % (fid, ext), "from": path, **info})
            got.append("%s %s" % (info["family"], info["style"]))
        return ", ".join(got) or "a face already kept"

    def words(self, data, path, kind):
        text = data.decode("utf-8-sig", "replace")
        if kind == "css" or path.lower().endswith((".html", ".htm")):
            for fam in re.findall(r"font-family\s*:\s*([^;}{]+)", text):
                self.theme["fonts"].append(
                    {"role": "css", "family": fam.split(",")[0].strip(" '\"")}
                )
        self.text.append("== %s ==\n%s" % (path, text[:60000]))
        return "%d characters of text" % len(text)

    def draw_svgs(self, work):
        """The SVGs, each drawn by the browser (web-grab.svg_raster), into images/."""
        if not self.svgs:
            return
        wg = importlib.import_module("web-grab")
        for k, (data, path, row) in enumerate(self.svgs):
            if k >= MAX_SVG:
                row.update(used=None, skipped="past the %d SVGs drawn" % MAX_SVG)
                continue
            try:
                im = wg.svg_raster(data, 1200, work)
                iid = self.keep(im, path)
                row["used"] = "picture %s" % iid if iid else "a copy of a picture already kept"
            except Exception as e:  # noqa: BLE001
                row.update(used=None, skipped="the browser could not draw it (%s)" % str(e)[:80])

    def save(self):
        text = "\n\n".join(self.text)[:MAX_TEXT]
        with open(os.path.join(self.out, "text.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        inv = {
            "files": self.files,
            "pages": self.pages,
            "images": self.images,
            "fonts": self.fonts,
            "theme": self.theme,
            "colours": evidence_colours(text, self.theme),
            "chars": len(text),
        }
        _write_json(os.path.join(self.out, "inventory.json"), inv)
        return inv


def font_info(ft):
    """A face's family, style, weight, italic and what its licence bits allow (OS/2 fsType)."""
    name = ft["name"]

    def get(*ids):
        for i in ids:
            v = name.getDebugName(i)
            if v:
                return v.strip()
        return ""

    family = get(16, 1) or "Unnamed"
    style = get(17, 2) or "Regular"
    os2 = ft["OS/2"] if "OS/2" in ft else None
    weight = int(getattr(os2, "usWeightClass", 400) or 400) if os2 else 400
    weight = min(900, max(100, int(round(weight / 100.0)) * 100))
    italic = bool(os2 and os2.fsSelection & 1) or "italic" in style.lower()
    fs = int(getattr(os2, "fsType", 0) or 0) if os2 else 0
    embed = (
        "restricted"
        if fs & 0x0002
        else "preview only"
        if fs & 0x0004
        else "editable"
        if fs & 0x0008
        else "installable"
    )
    return {
        "family": family,
        "style": style,
        "weight": weight,
        "italic": italic,
        "embedding": embed,
    }


def dominant(im, n=4):
    """The few colours a picture is mostly made of, as #RRGGBB (transparent pixels left out)."""
    import numpy as np  # noqa: PLC0415

    rgba = im.convert("RGBA")
    rgba.thumbnail((96, 96))
    a = np.asarray(rgba).reshape(-1, 4)
    px = a[a[:, 3] > 200][:, :3]
    if not len(px):
        return []
    pal = Image.fromarray(px.reshape(1, -1, 3).astype("uint8"), "RGB")
    q = pal.quantize(colors=n + 2, method=Image.Quantize.MEDIANCUT)
    counts = sorted(q.getcolors(), reverse=True)
    colours = q.getpalette()
    out = []
    for c, idx in counts:
        if c / len(px) < 0.04:
            continue
        r, g, b = colours[idx * 3 : idx * 3 + 3]
        out.append("#%02X%02X%02X" % (r, g, b))
    return out[:n]


def evidence_colours(text, theme):
    """Colour codes written in the brand's own words (hex and RGB), most mentioned first, and its
    office theme's: what the card's palette is checked against."""
    c = Counter()
    for h in HEX.findall(text):
        h = h.upper()
        c["#" + (h if len(h) == 6 else "".join(ch * 2 for ch in h))] += 1
    for r, g, b in RGB.findall(text):
        if max(int(r), int(g), int(b)) <= 255:
            c["#%02X%02X%02X" % (int(r), int(g), int(b))] += 1
    for t in theme.get("colors") or []:
        c[t["hex"]] += 1
    return [{"hex": h, "count": n} for h, n in c.most_common(40)]


def ingest(src_dir_or_files, out, log=print):
    """Read every sent file into out/ (read/): the inventory. Takes a folder of files/<fid>.bin
    with their .json (a brand's own), or a list of paths (the command line)."""
    shutil.rmtree(out, ignore_errors=True)
    ing = Ingest(out)
    items = []
    if isinstance(src_dir_or_files, str):
        for m in _files(os.path.dirname(src_dir_or_files.rstrip("/\\"))):
            if m.get("done"):
                items.append((os.path.join(src_dir_or_files, m["id"] + ".bin"), m["name"]))
    else:
        items = [(p, os.path.basename(p)) for p in src_dir_or_files]
    for p, name in items:
        with open(p, "rb") as f:
            data = f.read()
        log("reading %s (%.1f MB)" % (name, len(data) / 1048576))
        ing.take(data, name)
    work = os.path.join(out, "_svg")
    os.makedirs(work, exist_ok=True)
    try:
        ing.draw_svgs(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return ing.save()


# ------------------------------------------------------------------ what Claude sees
KEYWORDS = {
    "colour": r"colou?r|palette|hex|#[0-9a-f]{6}|rgb|cmyk|pantone|pms",
    "type": r"typeface|typograph|font|heading|headline|body copy|weight",
    "logo": r"\blogo|logotype|wordmark|brandmark|clear ?space|exclusion|minimum size|misuse",
    "voice": r"tone of voice|\bvoice\b|personality|we are|messaging|tagline",
}


def choose_pages(inv, text, n=ASK_PAGES):
    """The pages Claude sees: the ones about colour, type, logo and voice first (by their words),
    each PDF's cover, then evenly spread; a brand book with no words is sampled evenly."""
    pages = inv["pages"]
    if len(pages) <= n:
        return [p["id"] for p in pages]
    words = {}
    for m in re.finditer(r"== .*?\((p\d{3})\) ==\n(.*?)(?=\n== |\Z)", text, re.S):
        words[m.group(1)] = m.group(2).lower()
    picked = []
    for rx in KEYWORDS.values():
        scored = sorted(
            ((len(re.findall(rx, words.get(p["id"], ""))), p["id"]) for p in pages), reverse=True
        )
        picked += [pid for s, pid in scored[:2] if s > 0]
    picked += [p["id"] for p in pages if p["page"] == 1]
    picked += [p["id"] for p in pages[:: max(1, len(pages) // n)]]
    out = []
    for pid in picked:
        if pid not in out:
            out.append(pid)
    return sorted(out[:n])


def _checker(w, h, cell=16):
    im = Image.new("RGB", (w, h), "#ffffff")
    dr = ImageDraw.Draw(im)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2:
                dr.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#e4e4e4")
    return im


def _font(size):
    for p in (os.path.join(KIT, "fonts", "Montserrat-Medium.ttf"), "arial.ttf"):
        with contextlib.suppress(OSError):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def sheet(inv, read_dir, cells=SHEET_CELLS):
    """The pictures on one numbered sheet (a checkerboard under transparency, so a white logo
    shows): JPEG bytes and the ids on it, logo-like ones first (transparent, few colours, small)."""
    imgs = sorted(
        inv["images"],
        key=lambda i: (
            not i["alpha"],
            len(i["colours"]) > 3,
            i["w"] * i["h"] > 1_500_000,
            i["id"],
        ),
    )[:cells]
    if not imgs:
        return None, []
    cols, cw, ch = 6, 260, 230
    rows = -(-len(imgs) // cols)
    out = Image.new("RGB", (cols * cw, rows * ch), "white")
    dr = ImageDraw.Draw(out)
    font = _font(18)
    check = _checker(cw - 20, ch - 50)
    for k, it in enumerate(imgs):
        x, y = (k % cols) * cw, (k // cols) * ch
        out.paste(check, (x + 10, y + 10))
        with Image.open(os.path.join(read_dir, "images", it["id"] + ".png")) as im:
            im = im.convert("RGBA")
            im.thumbnail((cw - 30, ch - 60))
            ox, oy = x + 10 + (cw - 20 - im.width) // 2, y + 10 + (ch - 50 - im.height) // 2
            out.paste(im, (ox, oy), im)
        label = "%s  %dx%d" % (it["id"], it["w"], it["h"])
        dr.text((x + 12, y + ch - 36), label, fill="#222222", font=font)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=85)
    return buf.getvalue(), [i["id"] for i in imgs]


def page_jpeg(read_dir, pid, width=1300):
    with Image.open(os.path.join(read_dir, "pages", pid + ".jpg")) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        if im.height > 1800:
            im = im.crop((0, 0, im.width, 1800))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return buf.getvalue()


WRITER = (
    "You read brand books. From what a company sent -- guideline pages, logos, fonts, slides, "
    "notes -- you write the brand card a video studio follows on every frame. You report what "
    "the brand says, not what you would choose; where it says nothing, you infer from its logos "
    "and pages and say so. Answer with one JSON object and nothing else."
)

CARD_SHAPE = """{"name": the brand's name,
 "summary": what the brand is and feels like, one sentence,
 "palette": [{"hex": "#RRGGBB", "name": its name in the book or a plain one, "role": one of
   ROLES}], 2-10 colours, the brand's own (codes written in the book over colours guessed from
   pictures; exactly one primary),
 "type": {"headline": {"family": the brand's headline face, "font": the id of a sent font file of
   that family or null, "weight": "400".."900", "stand_in": the closest free Google Fonts family},
   "body": the same for body text},
 "logos": [{"image": a picture id from the sheet, "role": one of LOGO_ROLES, "note": when to use
   it}] -- the brand's logo files; where a logo is only on a page, {"page": a page id, "box":
   [x0, y0, x1, y1] as fractions of that page, "role", "note"}, a tight box around ONE logo on a
   plain background. Primary first, at most 6,
 "logo_rules": the logo's rules (clear space, minimum size, what never to do), at most 6,
 "tone": a few words for the voice, at most 6,
 "voice": how the brand speaks, one or two sentences a narrator can follow,
 "do": at most 6 things to do on screen, "dont": at most 6 things never to do,
 "imagery": the style of its pictures and illustrations, one sentence,
 "taglines": its own taglines or key lines, word for word, at most 3,
 "pages": the ids of the pages that show the brand best, at most 6,
 "notes": what the files did not say and you inferred, one or two sentences}"""


def ask_text(inv, text, pages, sheet_ids):
    fonts = "\n".join(
        "- %s: %s %s (weight %s%s), from %s; licence bits: %s"
        % (
            f["id"],
            f["family"],
            f["style"],
            f["weight"],
            ", italic" if f["italic"] else "",
            f["from"],
            f["embedding"],
        )
        for f in inv["fonts"]
    )
    colours = ", ".join("%s x%d" % (c["hex"], c["count"]) for c in inv["colours"][:30])
    has_theme = inv["theme"]["colors"] or inv["theme"]["fonts"]
    files = "\n".join(
        "- %s: %s" % (f["path"], f.get("used") or "skipped: " + f.get("skipped", ""))
        for f in inv["files"][:120]
    )
    page_list = ", ".join(
        "%s (%s p.%d)" % (p["id"], p["from"], p["page"]) for p in inv["pages"] if p["id"] in pages
    )
    shape = CARD_SHAPE.replace("LOGO_ROLES", " | ".join(LOGO_ROLES)).replace(
        "ROLES", " | ".join(ROLES)
    )
    return "\n\n".join(
        [
            "What was sent:\n" + files,
            "Pages shown above, in order: %s." % (page_list or "(none)"),
            "The sheet of pictures shows: %s (each picture's id is under it)."
            % (", ".join(sheet_ids) or "(no pictures)"),
            "Font files sent:\n" + (fonts or "(none)"),
            "Colour codes written in the files, most mentioned first: " + (colours or "(none)"),
            "Office theme colours and fonts: "
            + (json.dumps(inv["theme"]) if has_theme else "(none)"),
            "The words in the files (page ids in brackets):\n<<<\n%s\n>>>"
            % (text[:40000] or "(no words)"),
            "Write the brand card:\n" + shape,
        ]
    )


def _img(jpg):
    import base64  # noqa: PLC0415

    data = base64.b64encode(jpg).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


async def ask(inv, read_dir, auth="login", model=None, effort="medium", log=print):
    """One Claude call with no tools: the pages, the sheet, the words -> (the card as Claude
    wrote it, cost in USD)."""
    from claude_agent_sdk import (  # noqa: PLC0415
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )

    import agent  # noqa: PLC0415

    with open(os.path.join(read_dir, "text.txt"), encoding="utf-8") as f:
        text = f.read()
    pages = choose_pages(inv, text)
    sheet_jpg, sheet_ids = sheet(inv, read_dir)
    content = []
    for pid in pages:
        content += [{"type": "text", "text": "Page %s:" % pid}, _img(page_jpeg(read_dir, pid))]
    if sheet_jpg:
        content += [{"type": "text", "text": "The sheet of pictures:"}, _img(sheet_jpg)]
    content.append({"type": "text", "text": ask_text(inv, text, pages, sheet_ids)})
    log("asking Claude: %d pages, %d pictures on the sheet" % (len(pages), len(sheet_ids)))

    async def prompt():
        yield {
            "type": "user",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
            "session_id": "brand",
        }

    opts = ClaudeAgentOptions(
        model=model or agent.MODEL,
        effort=effort,
        system_prompt=WRITER,
        tools=[],
        strict_mcp_config=True,
        setting_sources=[],
        max_turns=1,
        env=agent.claude_env(None, auth),
        **({"cli_path": agent.claude_cli()} if auth == "login" else {}),
    )
    said, cost, err = "", 0.0, None
    async for m in query(prompt=prompt(), options=opts):
        if isinstance(m, AssistantMessage):
            said += "".join(b.text for b in m.content if isinstance(b, TextBlock))
        elif isinstance(m, ResultMessage):
            cost = m.total_cost_usd or 0.0
            err = m.result if m.is_error else None
    j = re.search(r"\{.*\}", said, re.S)
    try:
        d = json.loads(j.group(0)) if j else None
    except ValueError:
        d = None
    if err or not isinstance(d, dict):
        raise BrandError(502, "Claude could not read the brand: %s" % (err or said[:200]))
    return d, cost


# ------------------------------------------------------------------ the card
def _t(v, n):
    """One line of at most n characters, cut at a word (with an ellipsis) when it is longer."""
    s = " ".join(str(v or "").split())
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.6 else cut).rstrip(",;:") + "…"


def _hex(v):
    m = re.fullmatch(r"#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})", str(v or "").strip())
    if not m:
        return None
    h = m.group(1).upper()
    return "#" + (h if len(h) == 6 else "".join(c * 2 for c in h))


def _list(v, n, size=160):
    return [x for x in (_t(s, size) for s in (v if isinstance(v, list) else [])) if x][:n]


def _box(b):
    if not (isinstance(b, list) and len(b) == 4):
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b):
        return None
    x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in b)
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        return None
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def clean_card(d, inv):
    """A card held to its shape: colours that are colours, faces and pictures that exist, one
    primary of each. Used on Claude's reading and on every edit the person makes."""
    d = d if isinstance(d, dict) else {}
    fonts = {f["id"]: f for f in inv.get("fonts") or []}
    images = {i["id"] for i in inv.get("images") or []}
    pages = {p["id"] for p in inv.get("pages") or []}
    palette, seen = [], set()
    for c in d.get("palette") if isinstance(d.get("palette"), list) else []:
        h = _hex(c.get("hex")) if isinstance(c, dict) else None
        if h and h not in seen:
            seen.add(h)
            role = c.get("role") if c.get("role") in ROLES else "neutral"
            palette.append({"hex": h, "name": _t(c.get("name"), 40) or h, "role": role})
    palette = palette[:10]
    if palette and not any(c["role"] == "primary" for c in palette):
        palette[0]["role"] = "primary"
    for c in [c for c in palette if c["role"] == "primary"][1:]:
        c["role"] = "secondary"
    types = {}
    src = d.get("type") if isinstance(d.get("type"), dict) else {}
    for role in TYPE_ROLES:
        t = src.get(role) if isinstance(src.get(role), dict) else {}
        font = t.get("font") if t.get("font") in fonts else None
        stand = _t(t.get("stand_in"), 40)
        weight = str(t.get("weight") or ("700" if role == "headline" else "400"))
        types[role] = {
            "family": _t(t.get("family"), 60) or (fonts[font]["family"] if font else "Inter"),
            "font": font,
            "weight": weight if re.fullmatch(r"[1-9]00", weight) else "400",
            "stand_in": stand if FAMILY.match(stand or "") else "Inter",
        }
    logos = []
    for g in d.get("logos") if isinstance(d.get("logos"), list) else []:
        if not isinstance(g, dict):
            continue
        item = {
            "role": g.get("role") if g.get("role") in LOGO_ROLES else "other",
            "note": _t(g.get("note"), 160),
        }
        if g.get("image") in images:
            item["image"] = g["image"]
        elif g.get("page") in pages and _box(g.get("box")):
            item.update(page=g["page"], box=_box(g["box"]))
        else:
            continue
        logos.append(item)
    logos = logos[:6]
    if logos and not any(g["role"] == "primary" for g in logos):
        logos[0]["role"] = "primary"
    for g in [g for g in logos if g["role"] == "primary"][1:]:
        g["role"] = "other"
    return {
        "name": _t(d.get("name"), 60) or "Brand",
        "summary": _t(d.get("summary"), 240),
        "palette": palette,
        "type": types,
        "logos": logos,
        "logo_rules": _list(d.get("logo_rules"), 6),
        "tone": _list(d.get("tone"), 6, 30),
        "voice": _t(d.get("voice"), 300),
        "do": _list(d.get("do"), 6),
        "dont": _list(d.get("dont"), 6),
        "imagery": _t(d.get("imagery"), 240),
        "taglines": _list(d.get("taglines"), 3, 120),
        "pages": [p for p in (d.get("pages") or []) if p in pages][:6]
        if isinstance(d.get("pages"), list)
        else [],
        "notes": _t(d.get("notes"), 300),
        "fonts_consent": bool(d.get("fonts_consent")),
    }


# ------------------------------------------------------------------ assets: what episodes get
def key_out(im):
    """A logo cut off its plain background: the background colour, sampled round the edge, made
    transparent where it touches the edge (a white letter inside a blue badge stays white).
    Returns RGBA; unchanged when the edge is not one colour."""
    import numpy as np  # noqa: PLC0415
    from scipy import ndimage  # noqa: PLC0415

    rgba = im.convert("RGBA")
    a = np.asarray(rgba).astype(np.int16)
    if a[..., 3].min() < 250:
        return rgba  # it has its own transparency
    edge = np.concatenate([a[0, :, :3], a[-1, :, :3], a[:, 0, :3], a[:, -1, :3]])
    bg = np.median(edge, axis=0)
    if (np.abs(edge - bg).max(axis=1) < 24).mean() < 0.9:
        return rgba  # a photo, or a logo on a pattern: left as it is
    dist = np.abs(a[..., :3] - bg).max(axis=2)
    near = dist < 40
    lab, _ = ndimage.label(near)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    outside = np.isin(lab, list(border))
    alpha = np.where(outside, np.clip((dist - 10) * 255 // 30, 0, 255), 255).astype(np.uint8)
    out = a.astype(np.uint8)
    out[..., 3] = alpha
    return Image.fromarray(out, "RGBA")


def trim(im, pad=6):
    box = (
        im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        if im.mode == "RGBA"
        else None
    )
    if not box:
        return im
    x0, y0, x1, y1 = box
    return im.crop(
        (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad))
    )


def logo_image(d, g):
    """One of the card's logos as a trimmed RGBA picture: a picture file, keyed off a plain
    background; or a box on a page, drawn again sharp from the PDF itself."""
    read = os.path.join(d, "read")
    if g.get("image"):
        with Image.open(os.path.join(read, "images", g["image"] + ".png")) as im:
            return trim(key_out(im))
    inv = _read_json(os.path.join(read, "inventory.json"), {})
    page = next((p for p in inv.get("pages", []) if p["id"] == g.get("page")), None)
    if not page:
        return None
    x0, y0, x1, y1 = g["box"]
    pdf = os.path.join(read, "pdfs", page["pdf"]) if page.get("pdf") else None
    if pdf and os.path.exists(pdf):
        import pypdfium2 as pdfium  # noqa: PLC0415

        with open(pdf, "rb") as f:  # from bytes: an open file would hold the folder on Windows
            doc = pdfium.PdfDocument(f.read())
        try:
            pg = doc[page["page"] - 1]
            w, h = pg.get_size()
            scale = min(8.0, 1600 / max(1.0, (x1 - x0) * w))
            # the points cut from the left, bottom, right and top
            crop = (x0 * w, (1 - y1) * h, (1 - x1) * w, y0 * h)
            im = pg.render(scale=scale, crop=crop).to_pil()
        finally:
            doc.close()
    else:
        with Image.open(os.path.join(read, "pages", page["id"] + ".jpg")) as full:
            im = full.crop((x0 * full.width, y0 * full.height, x1 * full.width, y1 * full.height))
            im.load()
    return trim(key_out(im))


def standin(d, family, weights, log=print):
    """A free stand-in face from Google Fonts, kept in standin/: [(file, weight)]; [] when it
    cannot be fetched (the films then write in Inter, the kit's own)."""
    sd = os.path.join(d, "standin")
    os.makedirs(sd, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9]+", "", family)
    have = [(os.path.join(sd, "%s-%d.ttf" % (stem, w)), w) for w in weights]
    if all(os.path.exists(p) for p, _ in have):
        return have
    if not FAMILY.match(family or ""):
        return []
    try:
        wg = importlib.import_module("web-grab")
        urls = wg.font_css(family, tuple(weights))
        out = []
        for w, url in sorted(urls.items()):
            data, _, _ = wg._web.fetch(url, max_bytes=8 * 1024 * 1024)  # noqa: SLF001
            p = os.path.join(sd, "%s-%d.ttf" % (stem, w))
            with open(p, "wb") as f:
                f.write(data)
            out.append((p, w))
        return out
    except Exception as e:  # noqa: BLE001 -- offline, or not a Google font
        log("stand-in %s not fetched: %s" % (family, e))
        return []


def build_assets(d, card, log=print):
    """assets/: the logos as trimmed PNGs, the faces in use (the sent ones only with the
    person's consent, else free stand-ins), fonts.json for an episode's manifest, and brand.js.
    Returns what an episode gets: {"logos": {role: name}, "fonts": {role: family}, ...}."""
    read = os.path.join(d, "read")
    inv = _read_json(os.path.join(read, "inventory.json"), {})
    out = os.path.join(d, "assets.new")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "fonts"))
    logos, inks, n_other, logo_files = {}, {}, 0, []
    for g in card["logos"]:
        try:
            im = logo_image(d, g)
        except Exception as e:  # noqa: BLE001
            log("logo %s: %s" % (g, e))
            im = None
        if im is None:
            logo_files.append(None)
            continue
        im.thumbnail((1600, 1600))
        role = g["role"]
        if role in ("other",) or role in logos:
            n_other += 1
            name = "brand_logo_%d" % (n_other + 1)
        else:
            name = {"primary": "brand_logo", "mark": "brand_mark"}.get(role, "brand_logo_" + role)
        im.save(os.path.join(out, name + ".png"))
        logos[role if role not in logos and role != "other" else name] = name
        inks[name] = (dominant(im, 1) or ["#000000"])[0]
        logo_files.append(name)
    faces, families = [], {}
    fonts = {f["id"]: f for f in inv.get("fonts") or []}
    for role in TYPE_ROLES:
        t = card["type"][role]
        sent = fonts.get(t.get("font"))
        if card.get("fonts_consent") and sent:
            fam = sent["family"]
            for f in fonts.values():
                if f["family"] == fam and len([x for x in faces if x["family"] == fam]) < 8:
                    dst = "fonts/" + f["file"]
                    if not any(x["file"] == dst for x in faces):
                        shutil.copyfile(
                            os.path.join(read, "fonts", f["file"]),
                            os.path.join(out, *dst.split("/")),
                        )
                        faces.append(
                            {
                                "file": dst,
                                "family": fam,
                                "weight": str(f["weight"]),
                                **({"style": "italic"} if f["italic"] else {}),
                            }
                        )
            families[role] = {"family": fam, "sent": True}
            continue
        fam = t["stand_in"]
        weights = sorted({400, 700, int(t["weight"])})
        got = standin(d, fam, weights, log)
        if not got:
            families[role] = {"family": "Inter", "sent": False, "missing": fam}
            continue
        for p, w in got:
            dst = "fonts/" + os.path.basename(p)
            if not any(x["file"] == dst for x in faces):
                shutil.copyfile(p, os.path.join(out, *dst.split("/")))
                faces.append({"file": dst, "family": fam, "weight": str(w)})
        families[role] = {"family": fam, "sent": False}
    colors = {}
    for c in card["palette"]:
        colors.setdefault(c["role"], c["hex"])
    brand = {
        "name": card["name"],
        "colors": colors,
        "palette": card["palette"],
        "fonts": {
            "headline": families["headline"]["family"],
            "headlineWeight": card["type"]["headline"]["weight"],
            "body": families["body"]["family"],
            "bodyWeight": card["type"]["body"]["weight"],
        },
        "logos": logos,
        "logoInk": inks,
        "tagline": (card.get("taglines") or [""])[0],
    }
    js = BRAND_JS % json.dumps(brand, ensure_ascii=False)
    with open(os.path.join(out, "brand.js"), "w", encoding="utf-8") as f:
        f.write(js)
    for role in TYPE_ROLES:  # each role's face set in itself, for the card
        fam, want = families[role]["family"], int(card["type"][role]["weight"])
        mine = [f for f in faces if f["family"] == fam]
        if mine:
            f = min(mine, key=lambda f: abs(int(f["weight"]) - want))
            specimen(
                os.path.join(out, *f["file"].split("/")),
                fam,
                os.path.join(out, "spec-%s.png" % role),
                "%s %s" % (fam, f["weight"]),
            )
    used = {
        "faces": faces,
        "families": families,
        "logos": logos,
        "logo_files": logo_files,
        "brand": brand,
    }
    _write_json(os.path.join(out, "used.json"), used)
    _swap(out, os.path.join(d, "assets"))
    return used


def _swap(new, old):
    """The folder `new` takes `old`'s place (a reader meanwhile sees one or the other whole)."""
    shutil.rmtree(old + ".old", ignore_errors=True)
    if os.path.isdir(old):
        try:
            os.replace(old, old + ".old")
        except OSError:  # Windows: a file in it is open somewhere; it goes all the same
            shutil.rmtree(old, ignore_errors=True)
    os.replace(new, old)
    shutil.rmtree(old + ".old", ignore_errors=True)


BRAND_JS = """// The project's brand (studio/brandkit.py): SK.BRAND, and the kit writing in its body face.
SK.BRAND = %s;
if (SK.KIT) SK.KIT.font = SK.BRAND.fonts.body;
/* The logo for a background: its on-dark or on-light version when the brand has one, else the
   primary -- on a plate when its own colour would vanish into the background. {logo, plate?}
   for SK.logo(name, x, y, {plate}) and SK.endCard({logo, plate}); null without a logo. */
SK.BRAND.logoFor = function (bg) {
  const L = SK.BRAND.logos, ink = SK.BRAND.logoInk || {};
  const con = (a, b) => (SK.contrast ? SK.contrast(a, b) : 21);
  const dark = con(bg, '#ffffff') > con(bg, '#14171f');
  const want = dark ? L.on_dark : L.on_light;
  if (want) return { logo: want };
  const name = L.primary || L.mark || Object.values(L)[0];
  if (!name) return null;
  if (!ink[name] || con(bg, ink[name]) >= 3) return { logo: name };
  return { logo: name, plate: dark ? '#ffffff' : '#14171f' };
};
"""


# ------------------------------------------------------------------ the preview
LOOK_STYLE = {"drawn": "crayon", "painted": "clean", "collage": "collage"}
PREVIEW_T = (0.97, 1.97, 2.97)  # the title, a content frame, the end card

PREVIEW_JS = """
SK.setStyle(%(style)s);
SK.setGround('white');
const B = SK.BRAND, C0 = B.colors;
const bg = C0.background || '#ffffff', prim = C0.primary || '#2f6fdb';
const P = SK.palette({ bg, accent: C0.accent || prim });
const H = { font: B.fonts.headline, wt: +B.fonts.headlineWeight || 700 };
const T = { font: B.fonts.body, wt: +B.fonts.bodyWeight || 400 };
const fill = (col) => SK.screen(() => { const c = SK.ctx(); c.fillStyle = col;
  c.fillRect(-SK.W / 2 - 4, -SK.H / 2 - 4, SK.W + 8, SK.H + 8); });
SK.film({ duration: 3, fadeOut: 0, handheld: false, camera: SK.camera([[0, [0, 0, 1]]]), draw(t) {
  const f = Math.min(2, Math.floor(t));
  if (f === 0) {
    fill(bg);
    SK.screen(() => {
      const lg = B.logoFor(bg);
      if (lg) SK.logo(lg.logo, -SK.W / 2 + 310, -SK.H / 2 + 140, { w: 340, h: 130, plate: lg.plate });
      SK.label(%(kicker)s, -SK.W / 2 + 160, -60, { ...T, size: 40, col: P.accentInk, align: 'left' });
      SK.label(%(title)s, -SK.W / 2 + 160, 50, { ...H, size: 118, col: P.ink, align: 'left', maxW: SK.W - 320 });
      const k = SK.ctx(); k.fillStyle = prim; k.fillRect(-SK.W / 2 + 160, 120, 240, 14);
      SK.para(%(sub)s, -SK.W / 2 + 160, 175, { ...T, size: 40, w: SK.W - 480, col: P.soft });
    });
  } else if (f === 1) {
    fill(bg);
    SK.screen(() => {
      SK.label(%(head2)s, -SK.W / 2 + 160, -300, { ...H, size: 72, col: P.ink, align: 'left', maxW: 1100 });
      SK.para(%(body)s, -SK.W / 2 + 160, -220, { ...T, size: 38, w: 900, col: P.soft });
      const sw = B.palette.slice(0, 6);
      sw.forEach((c, i) => { const x = 330 + (i %% 3) * 170, y = -250 + Math.floor(i / 3) * 190, k = SK.ctx();
        k.fillStyle = c.hex; k.beginPath(); k.arc(x, y, 62, 0, Math.PI * 2); k.fill();
        k.strokeStyle = 'rgba(0,0,0,.12)'; k.lineWidth = 2; k.stroke();
        SK.label(c.hex, x, y + 100, { ...T, size: 22, col: P.soft }); });
      SK.pill(%(pill)s, -SK.W / 2 + 160 + 150, 200, { ...T, size: 34, fill: prim, col: SK.readable(prim, ['#ffffff', '#14171f']) });
    });
    SK.lowerThird(%(person)s, %(role)s, { t: -5, ...T });
  } else {
    const lg = B.logoFor(prim) || {};
    SK.endCard({ t: 1.9, logo: lg.logo, plate: lg.plate, title: B.name, tagline: B.tagline || '',
      bg: prim, font: B.fonts.headline, accent: C0.accent || '#ffffff' });
  }
} });
"""


def _words(s, n):
    """At most n characters, cut at a word, with an ellipsis when cut."""
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: s.rfind(" ", 0, n - 1)].rstrip(",;:") + "…"


def preview_film(d, look, used, card):
    """A three-second film drawing the brand: a title, a content frame, the end card."""
    work = os.path.join(d, "preview", "work-" + look)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    assets = os.path.join(d, "assets")
    import film as films  # noqa: PLC0415

    recipe = films.RECIPES.get(look) or films.RECIPES["drawn"]
    caps = [c for c in recipe if c in films.CAPS]
    if "kit" not in caps:
        caps.append("kit")
    js = PREVIEW_JS % {
        "style": json.dumps(LOOK_STYLE.get(look, "crayon")),
        "kicker": json.dumps("Episode 1"),
        "title": json.dumps(card["name"]),
        "sub": json.dumps(_words((card.get("taglines") or [card.get("summary") or ""])[0], 150)),
        "head2": json.dumps("How it looks on screen"),
        "body": json.dumps(
            "Every title, caption and card in the project's films is set in these faces and "
            "these colours, with the logo where the brand allows it."
        ),
        "pill": json.dumps("Learn more"),
        "person": json.dumps("Alex Morgan"),
        "role": json.dumps("Course instructor"),
    }
    with open(os.path.join(work, "film.js"), "w", encoding="utf-8") as f:
        f.write(js)
    man = {
        "title": "brand preview",
        "fps": 30,
        "duration": 3.0,
        "film": "film.js",
        "modules": list(films.modules(tuple(caps))),
        "fonts": [dict(f, file=os.path.join(assets, *f["file"].split("/"))) for f in used["faces"]]
        + list(films.fonts(tuple(caps))),
        "images": {n: os.path.join(assets, n + ".png") for n in used["logos"].values()},
        "head": {"scripts": [os.path.join(assets, "brand.js")]},
    }
    _write_json(os.path.join(work, "sketch.json"), man)
    return os.path.join(work, "sketch.json")


def render_preview(d, look, used, card, log=print, timeout=300):
    """preview/<look>.png (the three frames side by side) and preview/<look>-<n>.jpg (each, for
    a closer look), drawn by the film engine with the brand's own assets."""
    man = preview_film(d, look, used, card)
    work = os.path.dirname(man)
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        os.path.join(KIT, "scripts", "sketch-render.py"),
        "--manifest",
        man,
        "--stills",
        ",".join("%g" % t for t in PREVIEW_T),
        "--into",
        "stills",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
    shots = [os.path.join(work, "stills", "%06.2f.png" % t) for t in PREVIEW_T]
    if r.returncode or not all(os.path.exists(p) for p in shots):
        raise BrandError(500, "The preview could not be drawn: %s" % (r.stderr or r.stdout)[-400:])
    pd = os.path.join(d, "preview")
    tiles = []
    for k, p in enumerate(shots, 1):
        with Image.open(p) as im:
            im = im.convert("RGB")
            big = im.copy()
            big.thumbnail((1280, 720))
            big.save(os.path.join(pd, "%s-%d.jpg" % (look, k)), quality=86)
            im.thumbnail((640, 360))
            tiles.append(im)
    strip = Image.new("RGB", (sum(t.width for t in tiles) + 16 * 2, tiles[0].height), "white")
    x = 0
    for t in tiles:
        strip.paste(t, (x, 0))
        x += t.width + 16
    strip.save(os.path.join(pd, look + ".png"))
    shutil.rmtree(work, ignore_errors=True)
    return os.path.join(pd, look + ".png")


def specimen(font_path, family, out, text=None):
    """A face set in itself, for the card (PIL: the page cannot load fonts from the studio)."""
    try:
        big, small = ImageFont.truetype(font_path, 64), ImageFont.truetype(font_path, 30)
    except OSError:
        return False
    im = Image.new("RGB", (900, 170), "white")
    dr = ImageDraw.Draw(im)
    dr.text((16, 8), text or family, fill="#14171f", font=big)
    dr.text((18, 104), "Aa Bb Cc 0123456789 — the quick brown fox", fill="#555555", font=small)
    im.save(out)
    return True


# ------------------------------------------------------------------ reading, as a job
TASKS = set()  # the reads and previews running here: kept, so none is collected half-way
_RENDER = None  # one preview drawn at a time on this server (each is a browser)


def _sem():
    global _RENDER
    if _RENDER is None:
        _RENDER = asyncio.Semaphore(1)
    return _RENDER


def in_flight():
    return [t for t in TASKS if not t.done()]


def _server():
    try:
        import peers  # noqa: PLC0415

        return peers.SERVER_ID
    except Exception:  # noqa: BLE001
        return "cli"


def _busy(st):
    """Is a read or a preview of this brand under way somewhere (and not one a dead server left)?"""
    if st.get("state") != "reading" and not st.get("step"):
        return False
    try:
        at = datetime.fromisoformat(st.get("at") or "")
    except ValueError:
        return False
    return (datetime.now() - at).total_seconds() < STALE_S


def _spawn(coro):
    t = asyncio.get_running_loop().create_task(coro)
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return t


def start(d, auth="login", look="drawn", log=print):
    """Begin reading the brand in the background: the state as it is now. Refuses while a read
    is under way, without files, or past READS_A_DAY reads in 24 h."""
    with _lock(d):
        st = state_of(d)
        if _busy(st):
            raise BrandError(409, "The brand is being read already.")
        if not any(m["done"] for m in _files(d)):
            raise BrandError(409, "Add the brand's files first.")
        now = time.time()
        reads = [r for r in st.get("reads") or [] if now - r < 86400]
        if len(reads) >= READS_A_DAY:
            raise BrandError(429, "A brand is read at most %d times a day." % READS_A_DAY)
        st = _set_state(
            d,
            state="reading",
            step="unpacking",
            error=None,
            server=_server(),
            look=look,
            reads=reads + [now],
            started=_now(),
        )
    _spawn(read(d, auth, look, log))
    return st


async def read(d, auth="login", look="drawn", log=print):
    """The read (start() runs it): ingest, ask, card, assets, preview. Never raises: a failure
    is the state's, in words."""
    try:
        new = os.path.join(d, "read.new")
        inv = await asyncio.to_thread(ingest, os.path.join(d, "files"), new, log)
        old = os.path.join(d, "read")
        _swap(new, old)
        for f in inv["fonts"]:
            await asyncio.to_thread(
                specimen,
                os.path.join(old, "fonts", f["file"]),
                f["family"],
                os.path.join(old, "fonts", f["id"] + ".png"),
                "%s %s" % (f["family"], f["style"]),
            )
        found = "%d pages, %d pictures, %d fonts" % (
            len(inv["pages"]),
            len(inv["images"]),
            len(inv["fonts"]),
        )
        _set_state(d, step="looking", found=found)
        if not (inv["pages"] or inv["images"] or inv["fonts"] or inv["chars"]):
            raise BrandError(422, "Nothing in these files could be read as a brand.")
        raw, cost = await ask(inv, old, auth, log=log)
        before = _read_json(os.path.join(d, "card.json"), {}) or {}
        card = clean_card({**raw, "fonts_consent": before.get("fonts_consent", False)}, inv)
        card["read_at"] = _now()
        _write_json(os.path.join(d, "card.json"), card)
        st = state_of(d)
        _set_state(d, step="assets", cost_usd=round((st.get("cost_usd") or 0) + cost, 4))
        used = await asyncio.to_thread(build_assets, d, card, log)
        await _preview(d, look, used, card, log)
        _set_state(d, state="ready", step=None, stale=False, read_at=card["read_at"])
    except Exception as e:  # noqa: BLE001 -- the page shows why
        why = e.text if isinstance(e, BrandError) else (str(e) or type(e).__name__)
        log("brand read failed: %s" % why)
        _set_state(d, state="failed", step=None, error=why[:300])


async def _preview(d, look, used, card, log=print):
    _set_state(d, step="preview")
    async with _sem():
        try:
            await asyncio.to_thread(render_preview, d, look, used, card, log)
            _set_state(d, preview_error=None, **{"preview_" + look: _now()})
        except Exception as e:  # noqa: BLE001 -- the card stands without its preview
            _set_state(d, preview_error=str(e)[:300])
    _set_state(d, step=None)


EDITABLE = (
    "name",
    "summary",
    "palette",
    "type",
    "logos",
    "logo_rules",
    "tone",
    "voice",
    "do",
    "dont",
    "imagery",
    "taglines",
    "fonts_consent",
)


def edit(d, patch, log=print):
    """The person's corrections: the card with these fields replaced, held to its shape, its
    assets made again (the server then draws the preview again: preview_again). The card."""
    if not isinstance(patch, dict):
        raise BrandError(400, "Send the fields to change.")
    with _lock(d):
        card = _read_json(os.path.join(d, "card.json"))
        if not card or state_of(d).get("state") == "reading":
            raise BrandError(409, "The brand is not read yet.")
        inv = _read_json(os.path.join(d, "read", "inventory.json"), {})
        merged = {**card, **{k: v for k, v in patch.items() if k in EDITABLE}}
        new = clean_card(merged, inv)
        new.update(read_at=card.get("read_at"), edited_at=_now())
        _write_json(os.path.join(d, "card.json"), new)
    build_assets(d, new, log)
    return new


def preview_again(d, look):
    """The preview in another look (the project's look changed), in the background."""
    card = _read_json(os.path.join(d, "card.json"))
    used = _read_json(os.path.join(d, "assets", "used.json"))
    if not card or not used:
        raise BrandError(409, "The brand is not read yet.")
    if _busy(state_of(d)):
        return state_of(d)
    _spawn(_preview(d, look, used, card))
    return _set_state(d, step="preview")


# ------------------------------------------------------------------ what the page sees
def public(d):
    st = state_of(d)
    if st.get("state") == "reading" and not _busy(st):
        st = _set_state(d, state="failed", step=None, error="The read was interrupted: read again.")
    elif st.get("step") and not _busy(st):
        st = _set_state(d, step=None)
    inv = _read_json(os.path.join(d, "read", "inventory.json"), {}) or {}
    used = _read_json(os.path.join(d, "assets", "used.json"), {}) or {}
    card = _read_json(os.path.join(d, "card.json"))
    pd = os.path.join(d, "preview")
    previews = {
        look: st.get("preview_" + look)
        for look in LOOK_STYLE
        if os.path.exists(os.path.join(pd, look + ".png"))
    }
    return {
        "state": st["state"],
        "step": st.get("step"),
        "found": st.get("found"),
        "error": st.get("error"),
        "stale": bool(st.get("stale")),
        "preview_error": st.get("preview_error"),
        "files": [{k: m[k] for k in ("id", "name", "size", "done", "added")} for m in _files(d)],
        "card": card,
        "found_files": [
            {k: f[k] for k in ("path", "kind", "used", "skipped") if f.get(k) is not None}
            for f in inv.get("files") or []
        ],
        "pages": [{k: p[k] for k in ("id", "from", "page")} for p in inv.get("pages") or []],
        "images": [{k: i[k] for k in ("id", "w", "h", "alpha")} for i in inv.get("images") or []],
        "fonts": [
            {k: f[k] for k in ("id", "family", "style", "weight", "italic", "embedding")}
            for f in inv.get("fonts") or []
        ],
        "in_use": {
            "fonts": used.get("families"),
            "logos": used.get("logos"),
            "logo_files": used.get("logo_files") or [],
        },
        "previews": previews,
        "read_at": st.get("read_at"),
    }


ASSET = re.compile(r"^(page|thumb|image|font|spec|logo|preview|frame)/([a-z0-9_\-]{1,40})$")


def asset(d, kind, name):
    """A file the page shows: (path, content type), or None."""
    if not ASSET.match("%s/%s" % (kind, name)):
        return None
    p, ct = {
        "page": (os.path.join(d, "read", "pages", name + ".jpg"), "image/jpeg"),
        "thumb": (os.path.join(d, "read", "pages", name + ".t.jpg"), "image/jpeg"),
        "image": (os.path.join(d, "read", "images", name + ".png"), "image/png"),
        "font": (os.path.join(d, "read", "fonts", name + ".png"), "image/png"),
        "logo": (os.path.join(d, "assets", name + ".png"), "image/png"),
        "spec": (os.path.join(d, "assets", "spec-%s.png" % name), "image/png"),
        "preview": (os.path.join(d, "preview", name + ".png"), "image/png"),
        "frame": (os.path.join(d, "preview", name + ".jpg"), "image/jpeg"),
    }[kind]
    return (p, ct) if os.path.exists(p) else None


# ------------------------------------------------------------------ an episode's brand
def seed(film, lib):
    """A ready brand into a new episode: its assets in brand/, its faces in the manifest's fonts,
    its logos as images (brand_logo...), brand.js before film.js. What it got, or None."""
    d = dir_of(lib)
    used = _read_json(os.path.join(d, "assets", "used.json"))
    card = _read_json(os.path.join(d, "card.json"))
    if not used or not card:  # a re-read under way: the last good brand meanwhile
        return None
    dst = film.path("brand")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(os.path.join(d, "assets"), dst, ignore=shutil.ignore_patterns("used.json"))
    with open(film.manifest, encoding="utf-8") as f:
        m = json.load(f)
    fonts = [f for f in m.get("fonts") or [] if not str(f.get("file", "")).startswith("brand/")]
    m["fonts"] = fonts + [dict(f, file="brand/" + f["file"]) for f in used["faces"]]
    images = {k: v for k, v in (m.get("images") or {}).items() if not k.startswith("brand_")}
    images.update({n: "brand/%s.png" % n for n in used["logos"].values()})
    m["images"] = images
    head = [s for s in (m.get("head") or {}).get("scripts", []) if s != "brand/brand.js"]
    m["head"] = {**(m.get("head") or {}), "scripts": ["brand/brand.js", *head]}
    _write_json(film.manifest, m)
    return {
        "name": card["name"],
        "logos": sorted(used["logos"].values()),
        "fonts": used["families"],
    }


def note(film, lib):
    """What an episode is told of its project's brand ("" without one)."""
    d = dir_of(lib)
    card = _read_json(os.path.join(d, "card.json"))
    used = _read_json(os.path.join(d, "assets", "used.json"))
    if not card or not used or not os.path.exists(film.path("brand", "brand.js")):
        return ""
    fam = used["families"]
    colours = "; ".join("%s %s (%s)" % (c["role"], c["hex"], c["name"]) for c in card["palette"])
    logos = "; ".join(
        "'%s' (%s%s)" % (n, r.replace("_", " "), "" if r in LOGO_ROLES else "")
        for r, n in used["logos"].items()
    )
    notes = {g["role"]: g["note"] for g in card["logos"] if g.get("note")}

    def face(role):
        f = fam[role]
        t = card["type"][role]
        sub = (
            ""
            if f.get("sent") or f["family"] == t["family"]
            else " (standing in for the brand's %s)" % t["family"]
        )
        return "'%s' weight %s%s" % (f["family"], t["weight"], sub)

    lines = [
        "This project has a brand: %s. %s" % (card["name"], card.get("summary") or ""),
        "Follow it on every frame. The look decides how things are drawn; the brand decides the "
        "colours (drawings included), every typeface and the logo. It is all in SK.BRAND "
        "(colors, palette, fonts, logos, tagline), loaded before film.js.",
        "- Colours: %s. Paint with these and their tints; bring in no new hues." % colours,
        "- Type: headlines in %s ({font: SK.BRAND.fonts.headline}), everything else in %s, "
        "which the kit already uses (SK.KIT.font). No other faces."
        % (face("headline"), face("body")),
    ]
    if logos:
        lines.append(
            "- Logos, drawn with SK.logo(name, x, y, {w, h, plate}) and never redrawn by hand: "
            "%s.%s On any background, SK.BRAND.logoFor(bg) -> {logo, plate} picks the version "
            "that shows, and a plate when none does: pass both on."
            % (logos, " " + " ".join("%s: %s." % (k, v) for k, v in notes.items()) if notes else "")
        )
    if card.get("logo_rules"):
        lines.append("- Logo rules: " + "; ".join(card["logo_rules"]) + ".")
    lines.append(
        "- The end card: SK.endCard({...SK.BRAND.logoFor(SK.BRAND.colors.primary), title, "
        "tagline, bg: SK.BRAND.colors.primary, font: SK.BRAND.fonts.headline}), unless the "
        "prompt or the brief says otherwise."
    )
    if card.get("tone") or card.get("voice"):
        lines.append(
            "- Voice (%s): %s The narration and the words on screen speak this way."
            % (", ".join(card.get("tone") or []), card.get("voice") or "")
        )
    if card.get("do"):
        lines.append("- Do: " + "; ".join(card["do"]) + ".")
    if card.get("dont"):
        lines.append("- Never: " + "; ".join(card["dont"]) + ".")
    if card.get("imagery"):
        lines.append("- Pictures and illustrations: " + card["imagery"])
    if card.get("taglines"):
        lines.append("- Its own lines, word for word if used: " + " / ".join(card["taglines"]))
    return "\n".join(lines)


# ------------------------------------------------------------------ the command line
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--files", nargs="+", help="what the person sent")
    ap.add_argument("--out", required=True, help="a folder to read into (a brand's own layout)")
    ap.add_argument("--plan", action="store_true", help="read only: what Claude would see; no call")
    ap.add_argument(
        "--again", action="store_true", help="the assets and preview again from card.json; no call"
    )
    ap.add_argument("--look", default="drawn", choices=sorted(LOOK_STYLE))
    ap.add_argument("--auth", default="login", choices=("login", "api"))
    a = ap.parse_args()
    d = os.path.abspath(a.out)
    os.makedirs(d, exist_ok=True)
    if a.again:
        card = _read_json(os.path.join(d, "card.json"))
        used = build_assets(d, card)
        print("preview:", render_preview(d, a.look, used, card))
        return
    if not a.files:
        ap.error("--files")
    t0 = time.time()
    inv = ingest(a.files, os.path.join(d, "read"))
    read_dir = os.path.join(d, "read")
    with open(os.path.join(read_dir, "text.txt"), encoding="utf-8") as f:
        text = f.read()
    for f in inv["files"]:
        print("  %-60s %s" % (f["path"][-60:], f.get("used") or "SKIPPED: " + f.get("skipped", "")))
    print(
        "found %d pages, %d pictures, %d fonts, %d characters, colours %s (%.1f s)"
        % (
            len(inv["pages"]),
            len(inv["images"]),
            len(inv["fonts"]),
            inv["chars"],
            " ".join(c["hex"] for c in inv["colours"][:8]),
            time.time() - t0,
        )
    )
    pages = choose_pages(inv, text)
    jpg, ids = sheet(inv, read_dir)
    if jpg:
        with open(os.path.join(d, "sheet.jpg"), "wb") as f:
            f.write(jpg)
    with open(os.path.join(d, "ask.txt"), "w", encoding="utf-8") as f:
        f.write(ask_text(inv, text, pages, ids))
    print(
        "Claude would see pages %s and %d pictures (sheet.jpg, ask.txt)"
        % (", ".join(pages), len(ids))
    )
    if a.plan:
        return
    t1 = time.time()
    raw, cost = asyncio.run(ask(inv, read_dir, a.auth))
    card = clean_card(raw, inv)
    _write_json(os.path.join(d, "card.json"), card)
    print(
        "card in %.0f s ($%.3f): %s" % (time.time() - t1, cost, json.dumps(card, indent=1)[:3000])
    )
    used = build_assets(d, card)
    os.makedirs(os.path.join(d, "preview"), exist_ok=True)
    print("preview:", render_preview(d, a.look, used, card))


if __name__ == "__main__":
    main()
