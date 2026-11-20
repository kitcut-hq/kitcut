#!/usr/bin/env python3
"""The laptop end of tools/actor-web: one actor-pack.py --external folder, served to a model's web
app open in a signed-in browser, and its answers written back.

    python3 -I tools/actor-web/receiver.py <folder> [--port 8899]

<folder> is what actor-pack.py --external wrote: jobs.json and refs/<key>.png. The page cannot
reach 127.0.0.1 itself (its CSP), so it opens this server's /recv.html in a small popup once and
talks to it with postMessage; the popup, on this server's origin, fetches and posts for it:

    {kind: 'aw-lib'}                   -> {kind: 'aw-lib', text}          the runner (gemini.js)
    {kind: 'aw-jobs'}                  -> {kind: 'aw-jobs', jobs}         <folder>/jobs.json
    {kind: 'aw-ref', name}             -> {kind: 'aw-ref', name, url}     refs/<name> as a data: URL
    {kind: 'aw-save', name, blob}      -> {kind: 'aw-saved', name, status} out/<name>.<jpg|png|webp>

A picture already in out/ is kept as <name>_old.<ext>. Standard library only, so it skips the
scripts/ conventions (_env, check-script) on purpose.
"""

import os
import re
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
NAME_OK = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}

RECV_HTML = """<!doctype html><meta charset=utf-8><title>actor-web receiver</title>
<body style="font:12px sans-serif"><div id=log>ready</div><script>
const log = (t) => { const d = document.createElement('div'); d.textContent = t;
  document.getElementById('log').prepend(d); };
const answer = (e, m) => (e.source || window.opener).postMessage(m, '*');
window.addEventListener('message', async (e) => {
  const m = e.data || {};
  if (m.kind === 'aw-lib') {
    return answer(e, {kind: 'aw-lib', text: await (await fetch('/gemini.js')).text()});
  }
  if (m.kind === 'aw-jobs') {
    return answer(e, {kind: 'aw-jobs', jobs: await (await fetch('/jobs.json')).json()});
  }
  if (m.kind === 'aw-ref') {
    const r = await fetch('/ref/' + encodeURIComponent(m.name));
    const b = await r.blob();
    const url = r.ok ? await new Promise((res) => { const f = new FileReader();
      f.onload = () => res(f.result); f.readAsDataURL(b); }) : null;
    return answer(e, {kind: 'aw-ref', name: m.name, url, status: r.status});
  }
  if (m.kind !== 'aw-save') return;
  let status;
  try {
    const r = await fetch('/save?name=' + encodeURIComponent(m.name),
      {method: 'POST', body: m.blob, headers: {'Content-Type': m.blob.type || 'image/jpeg'}});
    status = r.status;
  } catch (err) { status = 'error ' + err; }
  log(m.name + ': ' + status);
  answer(e, {kind: 'aw-saved', name: m.name, status});
});
</script>"""


def make_handler(folder):
    out = os.path.join(folder, "out")
    refs = os.path.join(folder, "refs")

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            pass

        def _send(self, code, body, ctype="text/plain; charset=utf-8"):
            body = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = urlparse(self.path).path
            if p in ("/", "/recv.html"):
                return self._send(200, RECV_HTML, "text/html; charset=utf-8")
            if p == "/gemini.js":
                with open(os.path.join(HERE, "gemini.js"), "rb") as f:
                    return self._send(200, f.read(), "text/javascript; charset=utf-8")
            if p == "/jobs.json":
                with open(os.path.join(folder, "jobs.json"), "rb") as f:
                    return self._send(200, f.read(), "application/json")
            if p.startswith("/ref/"):
                name = os.path.basename(p[5:])
                f = os.path.join(refs, name)
                ctype = TYPES.get(name.rsplit(".", 1)[-1].lower())
                if NAME_OK.match(name) and ctype and os.path.isfile(f):
                    with open(f, "rb") as fh:
                        return self._send(200, fh.read(), ctype)
                return self._send(404, "no such ref")
            self._send(404, "not found")

        def do_POST(self):
            u = urlparse(self.path)
            name = (parse_qs(u.query).get("name") or [""])[0]
            ext = EXT.get((self.headers.get("Content-Type") or "").split(";")[0].strip())
            if u.path != "/save" or not NAME_OK.match(name) or not ext:
                return self._send(400, "bad save")
            data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            os.makedirs(out, exist_ok=True)
            for e in EXT.values():  # one picture per name: an earlier one is kept aside
                old = os.path.join(out, "%s.%s" % (name, e))
                if os.path.exists(old):
                    os.replace(old, os.path.join(out, "%s_old.%s" % (name, e)))
            with open(os.path.join(out, "%s.%s" % (name, ext)), "wb") as f:
                f.write(data)
            print("saved %s.%s (%d bytes)" % (name, ext, len(data)), flush=True)
            self._send(200, "ok")

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", help="actor-pack.py --external's folder")
    ap.add_argument("--port", type=int, default=8899)
    a = ap.parse_args()
    folder = os.path.abspath(a.folder)
    if not os.path.isfile(os.path.join(folder, "jobs.json")):
        raise SystemExit("%s has no jobs.json: run actor-pack.py --external first" % folder)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(folder))
    print("receiver on http://127.0.0.1:%d/recv.html -> %s" % (a.port, folder), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
