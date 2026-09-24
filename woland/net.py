"""HTTP access: polite, identifiable, robots.txt-respecting.

* One requests.Session per worker (cookies survive the cookie handshakes some sites use).
* A process-wide throttle guarantees a minimum gap between requests to the same host.
* robots.txt is honoured with a Google-compatible parser (protego).
* Woland identifies itself honestly in the User-Agent and never tries to solve JavaScript
  bot checks or CAPTCHAs; pages protected that way are simply reported as unavailable.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import socket
import threading
import time
import urllib.request
from urllib.parse import urlsplit

import certifi
import requests
from protego import Protego
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("woland.net")

MAX_BYTES = 80 * 1024 * 1024


def user_agent() -> str:
    if os.environ.get("WOLAND_UA"):
        return os.environ["WOLAND_UA"]
    repo = os.environ.get("GITHUB_REPOSITORY")
    home = f"https://github.com/{repo}" if repo else "https://github.com/"
    return f"Mozilla/5.0 (compatible; WolandMonitor/1.0; +{home})"


# ── Optional DNS-over-HTTPS resolution ────────────────────────────────────────
# Some networks (e.g. EU ISPs implementing the sanctions broadcasting ban) block these domains
# at the DNS level. For local development set WOLAND_DOH=1 to resolve through Cloudflare's
# DNS-over-HTTPS instead. GitHub's runners do not need this.
_doh_cache: dict[str, str | None] = {}
_doh_lock = threading.Lock()
_orig_getaddrinfo = socket.getaddrinfo


def _doh_lookup(host: str) -> str | None:
    with _doh_lock:
        if host in _doh_cache:
            return _doh_cache[host]
    ip = None
    try:
        req = urllib.request.Request(f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
                                     headers={"accept": "application/dns-json"})
        data = json.load(urllib.request.urlopen(req, timeout=10))
        ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
        ip = ips[0] if ips else None
    except Exception as exc:  # fall back to the system resolver
        log.debug("DoH lookup failed for %s: %s", host, exc)
    with _doh_lock:
        _doh_cache[host] = ip
    return ip


def _patched_getaddrinfo(host, port, *args, **kwargs):
    if isinstance(host, str) and host and not host.endswith("cloudflare-dns.com") \
            and not re.match(r"^[\d.:]+$", host) and host != "localhost":
        ip = _doh_lookup(host)
        if ip:
            return _orig_getaddrinfo(ip, port, *args, **kwargs)
    return _orig_getaddrinfo(host, port, *args, **kwargs)


if os.environ.get("WOLAND_DOH") == "1":
    socket.getaddrinfo = _patched_getaddrinfo


# ── Throttle ──────────────────────────────────────────────────────────────────
class _HostThrottle:
    """A minimum gap between requests to one host, widened when the host says "too many requests"
    and narrowed again, step by step, as requests succeed."""

    def __init__(self):
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}
        self._slow: dict[str, float] = {}  # host → the widened gap

    def wait(self, host: str, gap: float):
        with self._lock:
            now = time.monotonic()
            at = max(now, self._next.get(host, 0.0))
            self._next[host] = at + max(gap, self._slow.get(host, 0.0))
        if at > now:
            time.sleep(at - now)

    def penalise(self, host: str, retry_after: str | None = None) -> float:
        """Widen the host's gap; returns how long to pause before trying again."""
        with self._lock:
            slow = min(30.0, max(2.0, self._slow.get(host, 0.0) * 2))
            self._slow[host] = slow
        try:
            return min(120.0, float(retry_after))
        except (TypeError, ValueError):
            return slow * 5

    def relax(self, host: str):
        with self._lock:
            if host in self._slow:
                self._slow[host] *= 0.97
                if self._slow[host] < 0.3:
                    del self._slow[host]

    def gap(self, host: str) -> float:
        return self._slow.get(host, 0.0)


THROTTLE = _HostThrottle()

_robots: dict[str, Protego | None] = {}
_robots_lock = threading.Lock()


class Response:
    __slots__ = ("status", "url", "content", "headers", "error")

    def __init__(self, status, url, content=b"", headers=None, error=None):
        self.status, self.url, self.content = status, url, content
        self.headers, self.error = headers or {}, error

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error

    @property
    def text(self) -> str:
        ctype = self.headers.get("content-type", "")
        m = re.search(r"charset=([\w-]+)", ctype, re.I)
        enc = m.group(1) if m else None
        if not enc:
            head = self.content[:600]
            m = re.search(rb'encoding=["\']([\w-]+)["\']', head) or re.search(rb'charset=["\']?([\w-]+)', head)
            enc = m.group(1).decode() if m else "utf-8"
        try:
            return self.content.decode(enc, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def challenged(self) -> bool:
        """True if the page is a JavaScript bot check rather than content."""
        if len(self.content) > 20000:
            return False
        t = self.content[:20000].lower()
        return any(k in t for k in (b"servicepipe", b"js-challenge", b"captcha", b"ddos-guard", b"qrator"))


class Fetcher:
    def __init__(self, gap: float = 0.6, timeout: tuple = (15, 45), cookies: dict | None = None,
                 cookie_domain: str | None = None):
        self.gap = gap
        self.timeout = timeout
        # Cookies an ordinary visitor's browser would hold (see `cookies` in outlets.yaml), scoped to one site.
        self.cookies = dict(cookies or {})
        self.cookie_domain = cookie_domain
        self.session = self._new_session()
        self.requests = 0

    def _new_session(self) -> requests.Session:
        s = requests.Session()
        s.verify = certifi.where()
        s.headers.update({
            "User-Agent": user_agent(),
            "Accept-Language": "ru,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        for name, value in self.cookies.items():
            s.cookies.set(name, str(value), domain=f".{self.cookie_domain}" if self.cookie_domain else "", path="/")
        # 429 is handled in get(), where it can slow down every later request to the host too.
        retry = Retry(total=3, connect=3, read=2, backoff_factor=1.5,
                      status_forcelist=(500, 502, 503, 504), respect_retry_after_header=True,
                      allowed_methods=("GET", "HEAD"))
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        with _robots_lock:
            known = base in _robots
            rp = _robots.get(base)
        if not known:
            rp = None
            try:
                THROTTLE.wait(parts.netloc, self.gap)
                r = self.session.get(base + "/robots.txt", timeout=self.timeout)
                if r.status_code == 200 and "html" not in r.headers.get("content-type", ""):
                    rp = Protego.parse(r.text)
            except requests.RequestException:
                rp = None
            with _robots_lock:
                _robots[base] = rp
        return True if rp is None else rp.can_fetch(url, "WolandMonitor")

    def get(self, url: str, *, check_robots: bool = True, gap: float | None = None,
            retry_403: int = 0, timeout: tuple | None = None) -> Response:
        if check_robots and not self.allowed(url):
            return Response(None, url, error="disallowed by robots.txt")
        r = self._get(url, gap, timeout)
        host = urlsplit(url).netloc
        for _ in range(4):  # "too many requests": slow down for this host, pause, try again
            if r.status != 429:
                break
            pause = THROTTLE.penalise(host, r.headers.get("retry-after"))
            log.info("%s: too many requests; pausing %.0fs, then one request every %.1fs", host, pause,
                     THROTTLE.gap(host))
            time.sleep(pause)
            r = self._get(url, gap, timeout)
        if r.ok:
            THROTTLE.relax(host)
        for attempt in range(retry_403):
            # Some feeds (TASS) intermittently refuse a connection; reconnect after a pause.
            if r.status != 403:
                break
            time.sleep(5 * (attempt + 1))
            self.session.close()
            self.session = self._new_session()
            r = self._get(url, gap, timeout)
        return r

    def _get(self, url: str, gap: float | None, timeout: tuple | None = None) -> Response:
        host = urlsplit(url).netloc
        THROTTLE.wait(host, self.gap if gap is None else gap)
        self.requests += 1
        try:
            with self.session.get(url, timeout=timeout or self.timeout, stream=True) as r:
                chunks, size = [], 0
                for chunk in r.iter_content(65536):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_BYTES:
                        return Response(r.status_code, r.url, error="response too large")
                body = b"".join(chunks)
                if body[:2] == b"\x1f\x8b":
                    try:
                        body = gzip.decompress(body)
                    except OSError:
                        pass
                return Response(r.status_code, r.url, body, {k.lower(): v for k, v in r.headers.items()})
        except requests.RequestException as exc:
            return Response(None, url, error=f"{type(exc).__name__}: {exc}"[:300])
