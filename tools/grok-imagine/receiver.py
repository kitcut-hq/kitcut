"""Local receiver for pictures made in Grok Imagine (grok.com/imagine), driven through the page DOM.

grok.com's content security policy refuses a fetch to http://127.0.0.1, and a site's repeated
downloads get blocked and freeze the tab. So the page opens this server's /recv.html in a small
popup once, and posts each picture to it with window.postMessage; the popup (same origin as this
server) POSTs the bytes here and answers the opener with {kind: 'still-film-saved', name, status}.
Each picture lands as <out>/<name>.<ext>; an existing file is kept as <name>_old.<ext> first.

The in-page half is imagine.js beside this file (see README.md).

Invoke as:
    python -I tools/grok-imagine/receiver.py --out projects/<id>/images            (serves on :8899)
    python -I tools/grok-imagine/receiver.py --out <dir> --port 8899 --dry-run      (prints, writes nothing)
"""

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

RECV_HTML = """<!doctype html><meta charset="utf-8"><title>still-film receiver</title>
<body style="font:13px system-ui;margin:8px">receiver ready<div id="log"></div>
<script>
const log = (t) => { const d = document.createElement('div'); d.textContent = t;
  document.getElementById('log').prepend(d); };
window.addEventListener('message', async (e) => {
  const m = e.data || {};
  if (m.kind === 'still-film-lib') {   // hand the opener imagine.js (grok.com cannot fetch us itself)
    const text = await (await fetch('/imagine.js')).text();
    (e.source || window.opener).postMessage({kind: 'still-film-lib', text}, '*');
    return;
  }
  if (m.kind === 'still-film-ref') {   // a reference picture from --refs, as a data: URL
    const r = await fetch('/ref/' + encodeURIComponent(m.name));
    const b = await r.blob();
    const url = r.ok ? await new Promise((res) => { const f = new FileReader(); f.onload = () => res(f.result); f.readAsDataURL(b); }) : null;
    (e.source || window.opener).postMessage({kind: 'still-film-ref', name: m.name, url, status: r.status}, '*');
    return;
  }
  if (m.kind !== 'still-film-save') return;
  let status;
  try {
    const r = await fetch('/save?name=' + encodeURIComponent(m.name),
      {method: 'POST', body: m.blob, headers: {'Content-Type': m.blob.type || 'image/jpeg'}});
    status = r.status + ' ' + (await r.text());
  } catch (err) { status = 'error ' + err; }
  log(m.name + ': ' + status);
  (e.source || window.opener).postMessage({kind: 'still-film-saved', name: m.name, status}, '*');
});
if (window.opener) window.opener.postMessage({kind: 'still-film-ready'}, '*');
</script>"""

EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}
NAME_OK = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def make_handler(out, dry, refs=None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            sys.stderr.write("[recv] " + (fmt % a) + "\n")

        def _send(self, code, body, ctype="text/plain; charset=utf-8"):
            b = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.end_headers()
            self.wfile.write(b)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.end_headers()

        def do_GET(self):
            p = urlparse(self.path).path
            if p in ("/", "/recv.html"):
                return self._send(200, RECV_HTML, "text/html; charset=utf-8")
            if p == "/imagine.js":
                with open(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "imagine.js"), "rb"
                ) as f:
                    return self._send(200, f.read(), "text/javascript; charset=utf-8")
            if p.startswith("/ref/") and refs:
                name = os.path.basename(p[5:])
                f = os.path.join(refs, name)
                if NAME_OK.match(name) and os.path.isfile(f):
                    ext = name.rsplit(".", 1)[-1].lower()
                    ctype = {
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "png": "image/png",
                        "webp": "image/webp",
                    }.get(ext)
                    if ctype:
                        with open(f, "rb") as fh:
                            return self._send(200, fh.read(), ctype)
                return self._send(404, "no such ref")
            if p == "/list":
                names = sorted(os.listdir(out)) if os.path.isdir(out) else []
                return self._send(200, json.dumps(names), "application/json")
            self._send(404, "not found")

        def do_POST(self):
            u = urlparse(self.path)
            if u.path != "/save":
                return self._send(404, "not found")
            name = (parse_qs(u.query).get("name") or [""])[0]
            if not NAME_OK.match(name):
                return self._send(400, "bad name")
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(n)
            ctype = (self.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
            ext = EXT.get(ctype)
            if not ext or len(data) < 1000:
                return self._send(400, "not a picture (%s, %d bytes)" % (ctype, len(data)))
            dest = os.path.join(out, "%s.%s" % (name, ext))
            if dry:
                return self._send(200, "dry-run %s %d" % (dest, len(data)))
            os.makedirs(out, exist_ok=True)
            for e in set(EXT.values()):  # one picture per name, whatever its type
                old = os.path.join(out, "%s.%s" % (name, e))
                if os.path.exists(old):
                    os.replace(old, os.path.join(out, "%s_old.%s" % (name, e)))
            with open(dest, "wb") as f:
                f.write(data)
            sys.stderr.write("[recv] saved %s (%d bytes)\n" % (dest, len(data)))
            self._send(200, "saved %d" % len(data))

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", required=True, help="folder the pictures are written to")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument(
        "--refs",
        help="folder of reference pictures the page may ask for (style sheet, cast line-up)",
    )
    ap.add_argument("--dry-run", action="store_true", help="accept and report, write nothing")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    refs = os.path.abspath(a.refs) if a.refs else None
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(out, a.dry_run, refs))
    print(
        "receiver on http://127.0.0.1:%d/recv.html -> %s%s"
        % (a.port, out, " (dry run)" if a.dry_run else "")
    )
    sys.stdout.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
