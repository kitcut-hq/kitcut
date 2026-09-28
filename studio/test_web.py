#!/usr/bin/env python
"""What a film may take from the web, checked offline: python studio/test_web.py

The address rules (_web.py) against the addresses that matter on the studio's machine -- the
cloud's metadata service, Azure's host address, the private network, loopback in every
spelling -- and a redirect from a "public" server to a private one, refused at connect time. Then
web-grab.py's own logic: telling a picture from a page by its bytes, what is stored as PNG and
what as JPEG, and that Google Fonts' stand-in for a family it does not have is not taken.
"""

import os
import io
import sys
import socket
import tempfile
import threading
import importlib
import http.server

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import

from PIL import Image  # noqa: E402

import _web  # noqa: E402

grab = importlib.import_module("web-grab")


def main():
    bad, n = [], [0]

    def expect(what, got, want):
        n[0] += 1
        if got != want:
            bad.append(what)
            print("FAIL  %s -> %r (want %r)" % (what, got, want))

    # ------------------------------------------------------------ addresses
    for a, want in [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("10.0.13.4", False),  # the studio VM's own network
        ("10.0.1.10", False),  # the VPN gateway beside it
        ("127.0.0.1", False),
        ("::1", False),
        ("169.254.169.254", False),  # the cloud's metadata service
        ("168.63.129.16", False),  # Azure's host address
        ("100.64.0.1", False),
        ("192.168.1.1", False),
        ("172.16.0.1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("::ffff:10.0.0.1", False),
        ("::ffff:8.8.8.8", True),
        ("fe80::1", False),
        ("fd00::1", False),
    ]:
        expect("public_ip(%s)" % a, _web.public_ip(a), want)

    real = socket.getaddrinfo

    def fake(host, port, *a, **k):
        table = {
            "rebind.test": ["93.184.216.34", "10.0.0.5"],  # one private address spoils the name
            "inside.test": ["10.1.2.3"],
            "outside.test": ["93.184.216.34"],
        }
        if host in table:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in table[host]]
        return real(host, port, *a, **k)

    socket.getaddrinfo = fake
    try:
        for url, want in [
            ("https://outside.test/logo.png", True),
            ("https://inside.test/", False),
            ("https://rebind.test/", False),
            ("http://127.0.0.1:8765/api/health", False),
            ("http://localhost/", False),
            ("ftp://outside.test/x", False),
            ("file:///etc/passwd", False),
            ("https://u:p@outside.test/", False),
            ("outside.test/logo.png", False),
            ("", False),
        ]:
            expect("public_url(%s)" % url, _web.public_url(url)[0], want)
    finally:
        socket.getaddrinfo = real

    # a page on a "public" server that redirects to a private address: the second connection
    # is refused when it is made, whatever the first one resolved to
    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/secret" % self.server.server_port)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    pub_addr, pub_url = _web.public_addr, _web.public_url
    _web.public_addr = lambda h, p: "127.0.0.1" if h == "pub.test" else pub_addr(h, p)
    _web.public_url = lambda u: (True, "") if "pub.test" in u else pub_url(u)
    try:
        try:
            _web.fetch("http://pub.test:%d/logo.png" % srv.server_port, timeout=5)
            got = "fetched"
        except _web.NotPublic as e:
            got = "refused" if "127.0.0.1" in str(e) else "refused, but: %s" % e
        expect("a redirect to 127.0.0.1", got, "refused")
    finally:
        _web.public_addr, _web.public_url = pub_addr, pub_url
        srv.shutdown()
    try:
        _web.fetch("http://127.0.0.1:1/")
        got = "fetched"
    except _web.NotPublic:
        got = "refused"
    expect("fetch of loopback", got, "refused")

    # ------------------------------------------------------------ web-grab.py
    def png(mode, size, colour):
        b = io.BytesIO()
        Image.new(mode, size, colour).save(b, "PNG")
        return b.getvalue()

    expect("kind: png", grab.kind_of(png("RGB", (4, 4), "red")), "png")
    expect("kind: svg", grab.kind_of(b'<?xml version="1.0"?>\n<svg xmlns="x"></svg>'), "svg")
    expect("kind: a page", grab.kind_of(b"<!DOCTYPE html><html><body>logo</body></html>"), "html")
    expect("kind: ico", grab.kind_of(b"\x00\x00\x01\x00" + b"\x00" * 20), "ico")
    expect("kind: junk", grab.kind_of(b"hello"), None)

    with tempfile.TemporaryDirectory() as d:
        logo = Image.new("RGBA", (600, 120), (0, 0, 0, 0))
        logo.paste((20, 60, 200, 255), (10, 10, 590, 110))
        path, w, h, alpha = grab.store(logo, os.path.join(d, "logo"))
        expect("a transparent logo stays PNG", (os.path.basename(path), alpha), ("logo.png", True))
        path, *_ = grab.store(Image.new("RGB", (1920, 1080), "white"), os.path.join(d, "logo"))
        expect("a large opaque picture is a JPEG", os.path.basename(path), "logo.jpg")
        expect("and the PNG of that name is gone", os.path.exists(os.path.join(d, "logo.png")), False)
        _, w, h, _ = grab.store(Image.new("RGB", (6000, 3000), "white"), os.path.join(d, "big"))
        expect("a huge picture is scaled down", (w, h), (grab.MAX_SIDE, grab.MAX_SIDE // 2))

    stand_in = (
        b"@font-face { font-family: 'Helvetica Neue'; font-weight: 400; "
        b"src: url(https://fonts.gstatic.com/l/font?kit=abc&v=v17) format('truetype'); }"
    )
    own = (
        b"@font-face { font-family: 'Inter'; font-weight: 700; "
        b"src: url(https://fonts.gstatic.com/s/inter/v20/abc.ttf) format('truetype'); }"
    )
    fetch = _web.fetch
    try:
        _web.fetch = lambda *a, **k: (stand_in, "text/css", a[0])
        expect("a family Google does not have", grab.font_css("Helvetica Neue", [400]), {})
        _web.fetch = lambda *a, **k: (own, "text/css", a[0])
        expect(
            "a Google font",
            grab.font_css("Inter", [700]),
            {700: "https://fonts.gstatic.com/s/inter/v20/abc.ttf"},
        )
    finally:
        _web.fetch = fetch

    print("%d cases, %d failed" % (n[0], len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
