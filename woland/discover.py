"""Discovering article URLs: sitemaps, sitemap indexes, feeds, listing pages, the Wayback Machine."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

from lxml import etree

from .net import Fetcher
from .util import MSK, clean, daterange, parse_dt

log = logging.getLogger("woland.discover")


@dataclass
class Candidate:
    url: str
    hint: datetime | None = None  # publication (or modification) time announced by the source
    title: str = ""
    lead: str = ""
    section: str = ""
    body: str = ""  # some feeds carry the full text
    author: str = ""
    via: str = ""


_PLACEHOLDER = re.compile(r"\{(y|m|mm|d|dd|ymd|msk_start|msk_end|n)\}")


def fill(template: str, day: date | None = None, n: int | None = None, escape: bool = False) -> str:
    """Expand {y} {m} {mm} {d} {dd} {ymd} {msk_start} {msk_end} {n} without touching regex braces."""
    def repl(m):
        k = m.group(1)
        if k == "n":
            return str(n) if n is not None else m.group(0)
        if day is None:
            return m.group(0)
        start = int(datetime(day.year, day.month, day.day, tzinfo=MSK).timestamp())
        v = {"y": day.year, "m": day.month, "mm": f"{day.month:02d}", "d": day.day, "dd": f"{day.day:02d}",
             "ymd": day.strftime("%Y%m%d"), "msk_start": start, "msk_end": start + 86400}[k]
        return re.escape(str(v)) if escape else str(v)
    return _PLACEHOLDER.sub(repl, template)


def periods(per: str, start: date, end: date) -> list[date]:
    days = list(daterange(start, end))
    if per == "day":
        return days
    if per == "month":
        return sorted({d.replace(day=1) for d in days})
    if per == "year":
        return sorted({d.replace(month=1, day=1) for d in days})
    return [end]  # once


# ── Parsers ───────────────────────────────────────────────────────────────────
_BLOCK = re.compile(r"<(url|sitemap)\b[^>]*>(.*?)</\1>", re.S | re.I)


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.S | re.I)
    if not m:
        return ""
    v = m.group(1).strip()
    if v.startswith("<![CDATA["):
        v = v[9:-3] if v.endswith("]]>") else v[9:]
    return v.strip()


def parse_sitemap(text: str) -> tuple[bool, list[dict]]:
    """Returns (is_index, entries). Entries: loc, lastmod, title (Google News sitemaps), pubdate."""
    is_index = "<sitemapindex" in text[:3000].lower()
    out = []
    for kind, block in _BLOCK.findall(text):
        loc = clean(_tag(block, "loc"))
        if not loc:
            continue
        out.append({
            "loc": loc,
            "lastmod": _tag(block, "lastmod"),
            "pubdate": _tag(block, "news:publication_date"),
            "title": clean(_tag(block, "news:title")),
        })
    return is_index, out


def _first(el, paths, ns):
    for p in paths:
        found = el.find(p, ns)
        if found is not None:
            if found.text and found.text.strip():
                return found.text
            if found.get("href"):
                return found.get("href")
    return ""


def parse_feed(content: bytes) -> list[dict]:
    """RSS 2.0 / RSS 1.0 / Atom → list of item dicts."""
    parser = etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(content, parser)
    except etree.XMLSyntaxError:
        return []
    if root is None:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/elements/1.1/",
          "content": "http://purl.org/rss/1.0/modules/content/", "yandex": "http://news.yandex.ru",
          "rss1": "http://purl.org/rss/1.0/"}
    items = root.findall(".//item") + root.findall(".//rss1:item", ns) + root.findall(".//atom:entry", ns)
    out = []
    for it in items:
        link = _first(it, ["link", "rss1:link", "atom:link"], ns)
        if not link:
            guid = it.find("guid")
            if guid is not None and (guid.text or "").startswith("http"):
                link = guid.text
        out.append({
            "link": (link or "").strip(),
            "title": clean(_first(it, ["title", "rss1:title", "atom:title"], ns)),
            "description": clean(_first(it, ["description", "rss1:description", "atom:summary"], ns)),
            "date": _first(it, ["pubDate", "dc:date", "atom:published", "atom:updated"], ns).strip(),
            "category": clean(_first(it, ["category"], ns)),
            "author": clean(_first(it, ["author", "dc:creator"], ns)),
            "full": clean(_first(it, ["yandex:full-text", "content:encoded", "atom:content"], ns)),
        })
    return out


# ── Sources ───────────────────────────────────────────────────────────────────
def _in_window(hint: datetime | None, start: date, end: date) -> bool:
    """Could an article announced with this timestamp have been published within [start, end]?

    Announced times are publication or later modification times, never earlier than publication:
    so nothing announced before the range can belong to it (3 hours of slack for sites that
    mislabel time zones), while anything up to a day after the range still might.
    """
    if hint is None:
        return True
    lower = datetime(start.year, start.month, start.day, tzinfo=MSK) - timedelta(hours=3)
    return hint >= lower and hint.astimezone(MSK).date() <= end + timedelta(days=1)


def _sitemap_candidates(fetcher: Fetcher, url: str, start: date, end: date, depth: int = 0) -> list[Candidate]:
    r = fetcher.get(url)
    if not r.ok:
        raise SourceError(f"{url}: {r.status or r.error}")
    is_index, entries = parse_sitemap(r.text)
    if is_index and depth == 0:
        out = []
        for e in entries[:12]:
            hint = parse_dt(e["lastmod"])
            if hint and hint.astimezone(MSK).date() < start - timedelta(days=1):
                continue
            out += _sitemap_candidates(fetcher, e["loc"], start, end, depth + 1)
        return out
    out = []
    for e in entries:
        hint = parse_dt(e["pubdate"]) or parse_dt(e["lastmod"])
        if _in_window(hint, start, end):
            out.append(Candidate(url=e["loc"], hint=hint, title=e["title"], via="sitemap"))
    return out


def _order_children(children: list[dict], order: str) -> list[dict]:
    def num(e):
        nums = re.findall(r"\d+", e["loc"].rsplit("/", 2)[-2] + e["loc"].rsplit("/", 1)[-1])
        return int(nums[-1]) if nums else None
    if order == "lastmod":
        return sorted(children, key=lambda e: e["lastmod"] or "", reverse=True)
    numeric = [e for e in children if num(e) is not None]
    other = [e for e in children if num(e) is None]
    numeric.sort(key=num, reverse=(order == "desc"))
    return other + numeric


def source_sitemap(fetcher, src, start, end):
    out = []
    for p in periods(src.get("per", "once"), start, end):
        out += _sitemap_candidates(fetcher, fill(src["url"], p), start, end)
    return out


def source_sitemap_index(fetcher, src, start, end):
    r = fetcher.get(src["url"])
    if not r.ok:
        raise SourceError(f"{src['url']}: {r.status or r.error}")
    _, children = parse_sitemap(r.text)
    years = sorted({d.year for d in daterange(start, end)}, reverse=True)
    pats = [re.compile(fill(src["child"], date(y, 1, 1), escape=True)) for y in years] \
        if "{y}" in src["child"] else [re.compile(src["child"])]
    picked = [c for c in children if any(p.search(c["loc"]) for p in pats)]
    order = src.get("order", "desc")
    out, fetched = [], 0
    for child in _order_children(picked, order):
        if fetched >= int(src.get("max_children", 3)):
            break
        lastmod = parse_dt(child["lastmod"])
        if lastmod and lastmod.astimezone(MSK).date() < start - timedelta(days=1):
            continue  # last changed before the range began: cannot contain it
        rc = fetcher.get(child["loc"])
        fetched += 1
        if not rc.ok:
            log.warning("sitemap child %s: %s", child["loc"], rc.status or rc.error)
            continue
        _, entries = parse_sitemap(rc.text)
        newest = None
        for e in entries:
            hint = parse_dt(e["pubdate"]) or parse_dt(e["lastmod"])
            if hint and (newest is None or hint > newest):
                newest = hint
            if _in_window(hint, start, end):
                out.append(Candidate(url=e["loc"], hint=hint, title=e["title"], via="sitemap"))
        if order in ("asc", "desc") and newest is not None \
                and newest.astimezone(MSK).date() < start - timedelta(days=1):
            break  # children are ordered newest first and this one is already too old
    return out


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """The range as Moscow datetimes: [start 00:00, the day after end 00:00)."""
    lower = datetime(start.year, start.month, start.day, tzinfo=MSK)
    return lower, datetime(end.year, end.month, end.day, tzinfo=MSK) + timedelta(days=1)


def _older_than_range(hints: list, start: date) -> bool:
    """Every dated entry on a page predates the range (with the same slack as _in_window)."""
    lower = _bounds(start, start)[0] - timedelta(hours=3)
    dated = [h for h in hints if h is not None]
    return bool(dated) and max(dated) < lower


def source_rss(fetcher, src, start, end):
    """One or more feeds. A URL containing {n} is a paged feed (…/feed/page/{n}): pages `first`..`pages`
    are read until a page holds nothing newer than the range."""
    urls = src["url"] if isinstance(src["url"], list) else [src["url"]]
    out, failures = [], []

    def read(u):
        r = fetcher.get(u, retry_403=2)
        if not r.ok:
            return None, f"{u}: {r.status or r.error}"
        items = [it for it in parse_feed(r.content) if it["link"]]
        for it in items:
            hint = parse_dt(it["date"])
            it["hint"] = hint
            if _in_window(hint, start, end):
                out.append(Candidate(url=it["link"], hint=hint, title=it["title"], lead=it["description"],
                                     section=it["category"], body=it["full"], author=it["author"], via="rss"))
        return items, None

    for u in urls:
        if "{n}" not in u:
            _, err = read(u)
            if err:
                failures.append(err)
            continue
        for n in range(int(src.get("first", 1)), int(src.get("pages", 10)) + 1):
            items, err = read(fill(u, None, n))
            if err and n == int(src.get("first", 1)):
                failures.append(err)
            if not items or _older_than_range([it["hint"] for it in items], start):
                break
    if failures and len(failures) == len(urls):
        raise SourceError("; ".join(failures))
    return out


def _item_hint(m: re.Match) -> datetime | None:
    g = m.groupdict()
    if g.get("ts"):
        return datetime.fromtimestamp(int(g["ts"]), MSK)
    return parse_dt(g["date"]) if g.get("date") else None


def source_html_list(fetcher, src, start, end):
    """Listing pages, in one of three shapes:

      per: day     one listing per day (…/news/2026/09/03/), continued by `next` (…/page/{n}/)
      {n}          numbered pages (…/news?page={n}), newest first
      {cursor}     pages that continue from the oldest item seen so far (…?pub_time={cursor});
                   the first page starts from the end of the range

    Links are taken from `item` (a pattern with the named groups url, and optionally title and
    ts — Unix time — or date) or else from every href matching `link`. Dated listings are read
    until they reach items older than the range, at most `pages` pages.
    """
    per = src.get("per", "once")
    pages = int(src.get("pages", 5))
    item_re = re.compile(src["item"]) if src.get("item") else None
    lower, upper = _bounds(start, end)
    out, failed = [], []
    plist = periods(per, start, end) if per == "day" else [None]
    for p in plist:
        link_re = re.compile(fill(src["link"], p, escape=True)) if src.get("link") else None
        seen = set()
        cursor = int(upper.timestamp())
        for n in range(1, pages + 1):
            if per == "day":
                url = fill(src["url"], p) if n == 1 else fill(src.get("next", ""), p, n)
                if not url:
                    break
            elif "{cursor}" in src["url"]:
                url = src["url"].replace("{cursor}", str(cursor))
            else:
                url = fill(src["url"], None, n)
            r = fetcher.get(url)
            if not r.ok:
                if n == 1:
                    failed.append(f"{url}: {r.status or r.error}")
                log.warning("listing %s: %s", url, r.status or r.error)
                break
            if item_re:
                entries = [(m.group("url"), clean(m.groupdict().get("title") or ""), _item_hint(m))
                           for m in item_re.finditer(r.text)]
            else:
                noon = datetime(p.year, p.month, p.day, 12, tzinfo=MSK) if p else None
                entries = [(h, "", noon) for h in re.findall(r'href=["\']([^"\'#?]+)', r.text) if link_re.search(h)]
            new = [(urljoin(url, u), t, h) for u, t, h in entries if urljoin(url, u) not in seen]
            if not new:
                break
            for u, title, hint in new:
                seen.add(u)
                if _in_window(hint, start, end):
                    out.append(Candidate(url=u, hint=hint, title=title, via="html"))
            hints = [h for _, _, h in new]
            if per != "day" and _older_than_range(hints, start):
                break
            if "{cursor}" in src["url"]:
                oldest = min((h for h in hints if h), default=None)
                if oldest is None or int(oldest.timestamp()) >= cursor:
                    break  # the listing did not move back in time
                cursor = int(oldest.timestamp())
    if failed and len(failed) == len(plist):
        raise SourceError("; ".join(failed[:3]))
    return out


CDX = "https://web.archive.org/cdx/search/cdx"


def _cdx(fetcher, **params) -> list[list[str]]:
    """Rows from the Internet Archive's capture index (the header row removed)."""
    import json
    from urllib.parse import urlencode
    params = {"output": "json", "fl": "original,timestamp", "filter": "statuscode:200", **params}
    r = fetcher.get(f"{CDX}?{urlencode(params)}", check_robots=False, gap=3.0, timeout=(20, 240))
    if not r.ok:
        raise SourceError(f"wayback {params.get('url')}: {r.status or r.error}")
    try:
        return json.loads(r.text or "[]")[1:]
    except ValueError:
        return []


def _first_captures(rows) -> dict[str, datetime]:
    """URL → time of its first capture (URLs normalised: https, no port, no query)."""
    first: dict[str, datetime] = {}
    for original, ts, *_ in rows:
        url = re.sub(r"^http://", "https://", original.split("?")[0].split("#")[0])
        url = re.sub(r"^(https://[^/]+):(?:80|443)/", r"\1/", url)
        try:
            t = datetime.strptime(ts[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if url not in first or t < first[url]:
            first[url] = t
    return first


def source_wayback(fetcher, src, start, end):
    """Backfill helper: article URLs the Internet Archive has captured. Only the URLs are used; the
    articles themselves are then read from the outlet like any other. Three ways to ask:

      prefix with placeholders   one query per period (per: month), for URLs that carry their date,
                                 e.g. tvzvezda.ru/news/{y}{m} → tvzvezda.ru/news/20269…
      walk                       for sequential numeric ids: start at the oldest id listed on the page
                                 `walk` (a live sitemap or feed) and step down in blocks of `block` ids
                                 until a block was captured before the range began
      plain prefix               captures made during the range (can be slow on large sites)

    A URL is kept if it was first captured between the day before the range and `late` days after it.
    """
    lower, upper = _bounds(start, end)
    earliest, latest = lower - timedelta(days=1), upper + timedelta(days=int(src.get("late", 5)))
    prefix = src["prefix"]
    first: dict[str, datetime] = {}
    if src.get("walk"):
        r = fetcher.get(src["walk"])
        if not r.ok:
            raise SourceError(f"walk anchor {src['walk']}: {r.status or r.error}")
        ids = [int(x) for x in re.findall(re.escape(prefix) + r"(\d{4,})", r.text)]
        if not ids:
            raise SourceError(f"walk anchor {src['walk']}: no ids under {prefix}")
        block, digits = int(src.get("block", 1000)), len(str(min(ids)))
        id_re = re.compile(re.escape(prefix) + r"(\d+)/?$")
        b, empty = min(ids) // block, 0
        for _ in range(int(src.get("max_blocks", 150))):
            got = {u: t for u, t in _first_captures(_cdx(fetcher, url=f"{prefix}{b}", matchType="prefix",
                                                          collapse="urlkey", limit=20000)).items()
                   if (m := id_re.search(u)) and len(m.group(1)) == digits and int(m.group(1)) // block == b}
            b -= 1
            if not got:
                empty += 1
                if empty >= 5:
                    break
                continue
            empty = 0
            first.update(got)
            times = sorted(got.values())
            if times[len(times) // 2] < earliest:
                break  # most of this block was captured before the range: older blocks are older still
    elif "{" in prefix:
        for p in periods(src.get("per", "month"), start, end):
            first.update(_first_captures(_cdx(fetcher, url=fill(prefix, p), matchType="prefix",
                                              collapse="urlkey", limit=50000)))
    else:
        first.update(_first_captures(_cdx(fetcher, url=prefix, matchType="prefix", collapse="urlkey",
                                          limit=50000, **{"from": f"{start:%Y%m%d}",
                                                          "to": f"{end + timedelta(days=2):%Y%m%d}"})))
    return [Candidate(url=u, hint=None, via="wayback") for u, t in first.items() if earliest <= t <= latest]


class SourceError(Exception):
    pass


HANDLERS = {
    "sitemap": source_sitemap,
    "sitemap_index": source_sitemap_index,
    "rss": source_rss,
    "html_list": source_html_list,
    "wayback": source_wayback,
}


def discover(fetcher: Fetcher, outlet, start: date, end: date, *, feeds_only: bool = False,
             backfill: bool = False) -> tuple[list[Candidate], list[str]]:
    """All candidates for the date range, merged by URL. Returns (candidates, error messages).

    backfill: also read sources that only make sense for older days (the Wayback Machine,
    deeper feed pages)."""
    merged: dict[str, Candidate] = {}
    errors = []
    for src in outlet.sources:
        kind = src["type"]
        if feeds_only and (kind != "rss" or src.get("backfill_only")):
            continue
        if (kind == "wayback" or src.get("backfill_only")) and not backfill:
            continue
        try:
            found = HANDLERS[kind](fetcher, src, start, end)
        except SourceError as exc:
            errors.append(f"{kind}: {exc}")
            continue
        except Exception as exc:  # a broken source must not stop the others
            log.exception("%s source %s failed", outlet.id, kind)
            errors.append(f"{kind}: {type(exc).__name__}: {exc}"[:300])
            continue
        for c in found:
            prev = merged.get(c.url)
            if prev is None:
                merged[c.url] = c
            else:  # keep the richest information from every source
                for f in ("title", "lead", "section", "body", "author"):
                    if not getattr(prev, f) and getattr(c, f):
                        setattr(prev, f, getattr(c, f))
                if prev.hint is None:
                    prev.hint = c.hint
                if c.via == "rss":
                    prev.via = "rss" if prev.via != "sitemap" else prev.via
    return list(merged.values()), errors
