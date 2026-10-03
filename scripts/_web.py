"""Fetching from the public web, and only the public web.

A studio film may take pictures, pages and facts from the internet (web-grab.py; the studio's
WebFetch goes through guard.py), and the prompt that asks for them is typed by a stranger. The
machine that fetches sits on a private network (the studio VM is on the WireGuard VNet, next to
other machines), so "fetch this URL" is also "reach whatever that name resolves to". This module
is the one answer to "may this be fetched":

    public_url(url)   (ok, why) for a URL: http(s), no credentials, a host whose every address
                      is on the public internet
    fetch(url)        the bytes, fetched with every connection -- the first and each redirect --
                      made to an address checked at connect time (a name that resolved to a
                      public address for the check and to 10.x for the fetch is refused)

Not public: private, loopback, link-local (169.254.169.254 is the cloud's metadata service),
shared (100.64/10), reserved, multicast, and Azure's host address 168.63.129.16, which is
routable from every Azure VM and answers it. Stdlib only.

Invoke as:  import _web; ok, why = _web.public_url(url); data, ctype, final = _web.fetch(url)
"""

import socket
import ipaddress
import http.client
import urllib.parse
import urllib.request

# the address every Azure VM reaches its host through (DHCP, DNS, the VM agent): public numbering,
# not a public service
BLOCKED = [ipaddress.ip_network("168.63.129.16/32")]
MAX_BYTES = 20 * 1024 * 1024
TIMEOUT = 20
# a plain browser's: some CDNs refuse urllib's own
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


class NotPublic(Exception):
    """The URL, or where it leads, is not on the public internet."""


def public_ip(a):
    """True for an address on the public internet."""
    ip = ipaddress.ip_address(a)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        return False
    return not any(ip in n for n in BLOCKED)


def addresses(host, port=443):
    """Every address `host` resolves to (a literal address is itself)."""
    try:
        return sorted({i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    except socket.gaierror as e:
        raise NotPublic("%s does not resolve (%s)" % (host, e)) from None


def public_addrs(host, port):
    """Every address of `host`, all public; NotPublic when any of them is not (a name with one
    private address among public ones is not trusted)."""
    addrs = addresses(host, port)
    bad = [a for a in addrs if not public_ip(a)]
    if bad or not addrs:
        raise NotPublic("%s is not on the public internet (%s)" % (host, ", ".join(bad or addrs)))
    return addrs


def public_addr(host, port):
    """One public address of `host` (public_addrs)."""
    return public_addrs(host, port)[0]


def _connect(host, port, timeout):
    """A socket to the first of `host`'s public addresses that answers: a network with no route
    for one family (IPv6 on a laptop's VPN, 2026-10-02: WinError 10051) still reaches the rest."""
    err = None
    for ip in public_addrs(host, port):
        try:
            return socket.create_connection((ip, port), timeout)
        except OSError as e:
            err = e
    raise err


def public_url(url):
    """(ok, why) for fetching `url`. Resolves the host; fetches nothing."""
    try:
        u = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError as e:
        return False, "not a URL (%s)" % e
    if u.scheme not in ("http", "https"):
        return False, "only http(s) URLs can be fetched, not %r" % (u.scheme or url)
    if not u.hostname:
        return False, "the URL has no host"
    if u.username or u.password:
        return False, "a URL with a user name or password is not fetched"
    try:
        port = u.port or (443 if u.scheme == "https" else 80)
    except ValueError as e:
        return False, "bad port (%s)" % e
    try:
        public_addr(u.hostname, port)
    except NotPublic as e:
        return False, str(e)
    return True, ""


class _HTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock = _connect(self.host, self.port, self.timeout)


class _HTTPS(http.client.HTTPSConnection):
    def connect(self):
        sock = _connect(self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_HTTP, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPS, req, context=self._context)


class _Redirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 8

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme not in ("http", "https"):
            raise NotPublic("redirected to a non-http URL: %s" % newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    """http and https only (build_opener would add ftp: and file:), each connection checked."""
    o = urllib.request.OpenerDirector()
    for h in (
        _HTTPHandler(),
        _HTTPSHandler(),
        _Redirect(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        o.add_handler(h)
    return o


def fetch(url, max_bytes=MAX_BYTES, timeout=TIMEOUT, accept="*/*", ua=UA):
    """(bytes, content type, final URL); ua: the User-Agent sent (a browser's by default).
    Raises NotPublic for a URL (or a redirect) off the public internet, ValueError for a body
    over max_bytes, OSError (urllib's URLError, HTTPError) for the rest."""
    ok, why = public_url(url)
    if not ok:
        raise NotPublic(why)
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": accept})
    with _opener().open(req, timeout=timeout) as r:
        n = r.headers.get("Content-Length")
        if n and n.isdigit() and int(n) > max_bytes:
            raise ValueError(
                "%s is %d MB, over the %d MB limit" % (url, int(n) >> 20, max_bytes >> 20)
            )
        data = r.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("%s is over the %d MB limit" % (url, max_bytes >> 20))
        return data, (r.headers.get("Content-Type") or "").split(";")[0].strip().lower(), r.url
