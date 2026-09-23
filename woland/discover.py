"""Discovering article URLs: sitemaps, sitemap indexes, feeds, listing pages, the Wayback Machine."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


def source_rss(fetcher, src, start, end):
    urls = src["url"] if isinstance(src["url"], list) else [src["url"]]
    out, failures = [], []
    for u in urls:
        r = fetcher.get(u, retry_403=2)
        if not r.ok:
            failures.append(f"{u}: {r.status or r.error}")
            continue
        for it in parse_feed(r.content):
            if not it["link"]:
                continue
            hint = parse_dt(it["date"])
            if _in_window(hint, start, end):
                out.append(Candidate(url=it["link"], hint=hint, title=it["title"], lead=it["description"],
                                     section=it["category"], body=it["full"], author=it["author"], via="rss"))
    if failures and len(failures) == len(urls):
        raise SourceError("; ".join(failures))
    return out


def source_html_list(fetcher, src, start, end):
    per = src.get("per", "once")
    pages = int(src.get("pages", 5))
    out = []
    for p in periods(per, start, end):
        link_re = re.compile(fill(src["link"], p if per == "day" else None, escape=True))
        seen = set()
        for n in range(1, pages + 1):
            if per == "day":
                url = fill(src["url"], p) if n == 1 else fill(src.get("next", ""), p, n)
                if not url:
                    break
            else:
                url = fill(src["url"], None, n)
            r = fetcher.get(url)
            if not r.ok:
                if n == 1:
                    log.warning("listing %s: %s", url, r.status or r.error)
                break
            found = [urljoin(url, h) for h in re.findall(r'href=["\']([^"\'#?]+)', r.text) if link_re.search(h)]
            new = [u for u in dict.fromkeys(found) if u not in seen]
            if not new:
                break
            seen.update(new)
            hint = datetime(p.year, p.month, p.day, 12, tzinfo=MSK) if per == "day" else None
            out += [Candidate(url=u, hint=hint, via="html") for u in new]
    return out


def source_wayback(fetcher, src, start, end):
    """Backfill helper: URLs the Internet Archive captured during the range."""
    r = fetcher.get(
        "https://web.archive.org/cdx/search/cdx?url=" + src["prefix"] + "*"
        + f"&from={start:%Y%m%d}&to={(end + timedelta(days=2)):%Y%m%d}"
        + "&output=json&fl=original,timestamp&filter=statuscode:200&collapse=urlkey&limit=50000",
        check_robots=False, gap=3.0)
    if not r.ok:
        raise SourceError(f"wayback: {r.status or r.error}")
    try:
        import json
        rows = json.loads(r.text or "[]")[1:]
    except ValueError:
        return []
    out = []
    for original, ts in rows:
        url = re.sub(r"^http://", "https://", original.split("?")[0])
        out.append(Candidate(url=url, hint=None, via="wayback"))
    return out


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
