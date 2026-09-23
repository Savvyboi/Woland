"""Small shared helpers: Moscow-time dates, timestamp parsing, text normalisation."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# Russian media live on Moscow time (UTC+3, no daylight saving). Woland's "day" is a Moscow day.
MSK = timezone(timedelta(hours=3), "MSK")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_msk() -> date:
    return now_utc().astimezone(MSK).date()


def msk_day(dt: datetime) -> date:
    return dt.astimezone(MSK).date()


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


_RE_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?$")  # RIA: 20260923T0006
_RE_TZ_NOCOLON = re.compile(r"([+-]\d{2})(\d{2})$")


def parse_dt(value, default_tz=MSK) -> datetime | None:
    """Parse the many timestamp dialects found in Russian news markup. Returns an aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=default_tz)
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit() and len(s) in (10, 13):  # unix epoch (seconds or ms)
        ts = int(s) / (1000 if len(s) == 13 else 1)
        return datetime.fromtimestamp(ts, timezone.utc)
    m = _RE_COMPACT.match(s)
    if m:
        y, mo, d, h, mi, sec = m.groups()
        return datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec or 0), tzinfo=default_tz)
    iso = s.replace("Z", "+00:00").replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2}", s) else None
    if iso:
        iso = _RE_TZ_NOCOLON.sub(r"\1:\2", iso)
        iso = re.sub(r"(\.\d{1,6})\d*", r"\1", iso)  # trim sub-microsecond digits
        try:
            dt = datetime.fromisoformat(iso)
            return dt if dt.tzinfo else dt.replace(tzinfo=default_tz)
        except ValueError:
            try:
                return datetime.fromisoformat(iso[:10]).replace(tzinfo=default_tz)
            except ValueError:
                pass
    try:  # RFC 2822, as used by RSS <pubDate>
        dt = parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=default_tz)
    except (TypeError, ValueError, IndexError):
        pass
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", s)  # 23.09.2026 14:05
    if m:
        d, mo, y, h, mi = m.groups()
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), tzinfo=default_tz)
    return None


def iso_msk(dt: datetime) -> str:
    return dt.astimezone(MSK).isoformat(timespec="seconds")


def iso_utc(dt: datetime | None = None) -> str:
    return (dt or now_utc()).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


_WS = re.compile(r"\s+")


def clean(s: str | None) -> str:
    """Unescape entities, drop tags and collapse whitespace."""
    if not s:
        return ""
    s = html.unescape(html.unescape(str(s)))
    s = re.sub(r"<[^>]+>", " ", s)
    return _WS.sub(" ", s.replace(" ", " ")).strip()


def normalize(s: str) -> str:
    """Matching form of a text: lower case, ё → е, unified dashes and spaces."""
    s = s.lower().replace("ё", "е")
    s = s.replace(" ", " ").replace("‑", "-").replace("‐", "-")
    return s


def truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    cut = s[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" ,;:—-") + "…"


def short_hash(s: str, n: int = 10) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


def fingerprint(text: str) -> str:
    """Content fingerprint used in citations: sha256 over the normalised text, first 16 hex digits."""
    return hashlib.sha256(_WS.sub(" ", normalize(text)).strip().encode("utf-8")).hexdigest()[:16]


def canonical_url(url: str) -> str:
    """Strip tracking noise (fragments, utm_* parameters) so one article has one URL."""
    url = url.strip().split("#", 1)[0]
    if "?" in url:
        base, _, query = url.partition("?")
        keep = [p for p in query.split("&") if p and not p.lower().startswith(("utm_", "from=", "yclid", "rcmclid"))]
        url = base + ("?" + "&".join(keep) if keep else "")
    return url
