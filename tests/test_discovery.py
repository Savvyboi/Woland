"""Discovering article URLs, against canned listings, feeds and Internet Archive answers (no network)."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

from woland.config import Outlet
from woland.discover import (discover, source_html_list, source_rss, source_sitemap_index, source_wayback)
from woland.net import Fetcher
from woland.util import MSK

DAY = date(2026, 9, 3)
# Listings may announce an article up to three hours before the day starts (sites that mislabel time
# zones) and up to a day after it ends (updates); the page itself decides the day.
EARLIEST = datetime(2026, 9, 2, 21, tzinfo=MSK)
LATEST = datetime(2026, 9, 5, tzinfo=MSK)


def in_window(c) -> bool:
    return EARLIEST <= c.hint < LATEST


def ts(d: date, hour: int, minute: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, hour, minute, tzinfo=MSK).timestamp())


# ── cursor listings (Gazeta.ru's "show more") ──────────────────────────────────
GAZETA_ITEM = (r'data-pub_time="(?P<ts>\d+)"[^>]*>\s*<div class="b_ear-textblock">\s*<a href="(?P<url>/[a-z_]+/news/'
               r'\d{4}/\d{2}/\d{2}/\d+\.shtml)" class="b_ear-title">(?P<title>[^<]+)')


def gazeta_page(items):
    return "".join(
        f'<div class="b_ear m_list" data-pub_time="{t}" data-id="{i}" data-essence="news">'
        f'<div class="b_ear-textblock"><a href="/politics/news/{datetime.fromtimestamp(t, MSK):%Y/%m/%d}/{i}.shtml" '
        f'class="b_ear-title">Заголовок&nbsp;{i}</a></div></div>' for t, i in items)


def test_cursor_listing_pages_back_until_the_range_is_passed(fake):
    # 30 items an hour apart, from 4 Sept 02:00 back to 3 Sept 21:00 … 2 Sept; 10 per page.
    items = [(ts(date(2026, 9, 4), 23) - 3600 * k, 1000 - k) for k in range(60)]

    def page(url):
        cursor = int(re.search(r"pub_time=(\d+)", url).group(1))
        older = [x for x in items if x[0] < cursor]
        return gazeta_page(older[:10])

    f = fake({re.compile(r"/news/\?p=page&pub_time="): page})
    src = {"type": "html_list", "url": "https://www.gazeta.ru/news/?p=page&pub_time={cursor}", "pages": 50,
           "item": GAZETA_ITEM}
    got = source_html_list(f, src, DAY, DAY)
    assert all(in_window(c) for c in got)                   # nothing from before the range
    assert sum(1 for c in got if c.hint.astimezone(MSK).date() == DAY) == 24
    assert got[0].title == "Заголовок 976" and got[0].url.startswith("https://www.gazeta.ru/politics/news/")
    # the first page starts from the end of the range, and paging stops once the range is passed
    assert f"pub_time={ts(DAY + timedelta(days=1), 0)}" in f.calls[0]
    assert len(f.calls) <= 6


def test_cursor_listing_stops_when_it_does_not_move(fake):
    stuck = gazeta_page([(ts(DAY, 12), 1)])
    f = fake({re.compile("pub_time"): stuck})
    got = source_html_list(f, {"url": "https://x.ru/news/?pub_time={cursor}", "pages": 50, "item": GAZETA_ITEM}, DAY, DAY)
    assert len(got) == 1 and len(f.calls) == 2


# ── numbered listings with dates (AiF's "load more") ──────────────────────────
AIF_ITEM = (r'<a href="(?P<url>https://aif\.ru/[^"]+)"><span class="item_text__title">(?P<title>[^<]+)</span></a>'
            r'\s*<span class="text_box__date">(?P<date>\d\d\.\d\d\.\d{4} \d\d:\d\d)</span>')


def test_numbered_listing_reads_through_newer_pages_and_stops_after_the_range(fake):
    def page(url):
        n = int(url.rsplit("=", 1)[1])
        start = datetime(2026, 9, 6, 0, 0, tzinfo=MSK) - timedelta(hours=6 * (n - 1))
        return "".join(
            f'<a href="https://aif.ru/politics/a-{n}-{k}"><span class="item_text__title">Статья {n}.{k}</span></a>'
            f'<span class="text_box__date">{start - timedelta(hours=2 * k):%d.%m.%Y %H:%M}</span>' for k in range(3))

    f = fake({re.compile(r"aif\.ru/news\?page=\d+"): page})
    got = source_html_list(f, {"url": "https://aif.ru/news?page={n}", "pages": 100, "item": AIF_ITEM}, DAY, DAY)
    assert got and all(in_window(c) for c in got)
    assert sum(1 for c in got if c.hint.astimezone(MSK).date() == DAY) == 12
    assert len(f.calls) < 20                                  # did not read all 100 pages


def test_per_day_listing_uses_links_and_follow_up_pages(fake):
    routes = {
        "https://lenta.ru/news/2026/09/03/": '<a href="/news/2026/09/03/a/">a</a><a href="/news/2026/09/02/old/">x</a>',
        "https://lenta.ru/news/2026/09/03/page/2/": '<a href="/news/2026/09/03/b/">b</a>',
        "https://lenta.ru/news/2026/09/03/page/3/": '<a href="/news/2026/09/03/b/">b</a>',   # nothing new: stop
    }
    f = fake(routes)
    src = {"type": "html_list", "per": "day", "url": "https://lenta.ru/news/{y}/{mm}/{dd}/",
           "next": "https://lenta.ru/news/{y}/{mm}/{dd}/page/{n}/", "pages": 25, "link": "/news/{y}/{mm}/{dd}/[^/\"?#]+/"}
    got = source_html_list(f, src, DAY, DAY)
    assert [c.url for c in got] == ["https://lenta.ru/news/2026/09/03/a/", "https://lenta.ru/news/2026/09/03/b/"]
    assert all(c.hint == datetime(2026, 9, 3, 12, tzinfo=MSK) for c in got)
    assert len(f.calls) == 3


def test_listing_that_cannot_be_read_is_an_error(fake):
    from woland.discover import SourceError
    with pytest.raises(SourceError):
        source_html_list(fake({}), {"url": "https://x.ru/news?page={n}", "item": AIF_ITEM}, DAY, DAY)


# ── paged feeds (the Kremlin's …/feed/page/{n}) ────────────────────────────────
def atom(entries):
    body = "".join(f"<entry><title>{t}</title><link href='{u}'/><published>{p}</published></entry>"
                   for t, u, p in entries)
    return f"<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>{body}</feed>"


def test_paged_feed_stops_at_the_first_page_older_than_the_range(fake):
    def page(url):
        n = int(url.rsplit("/", 1)[1])
        d = datetime(2026, 9, 6, 12, tzinfo=MSK) - timedelta(days=n - 2)
        return atom([(f"Событие {n}", f"http://kremlin.ru/events/president/news/{n}", d.isoformat())])

    f = fake({re.compile(r"/feed/page/\d+$"): page})
    got = source_rss(f, {"url": "http://kremlin.ru/events/all/feed/page/{n}", "first": 2, "pages": 80}, DAY, DAY)
    assert [c.url for c in got] == ["http://kremlin.ru/events/president/news/4", "http://kremlin.ru/events/president/news/5"]
    assert f.calls[-1].endswith("/page/6") and len(f.calls) == 5


# ── the Internet Archive ──────────────────────────────────────────────────────
def cdx(rows):
    return json.dumps([["original", "timestamp"]] + rows)


def stamp(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def test_wayback_walk_steps_down_through_id_blocks(fake):
    # ids grow ~1,000 a day: block 7150 ≈ 3 Sept, 7149 ≈ 2 Sept, 7148 ≈ 1 Sept, 7147 ≈ 31 Aug
    def captures(block):
        base = datetime(2026, 9, 3, 12, tzinfo=MSK) - timedelta(days=7150 - block)
        return [[f"http://www.kp.ru:80/online/news/{block}{k:03d}/", stamp(base + timedelta(seconds=k))] for k in range(0, 1000, 100)] \
            + [[f"https://www.kp.ru/online/news/{block}/", stamp(base)]]          # an old short id: ignored

    def cdx_answer(url):
        prefix = re.search(r"url=www\.kp\.ru%2Fonline%2Fnews%2F(\d+)", url).group(1)
        return cdx(captures(int(prefix)))

    routes = {"https://www.kp.ru/sitemap/news_02.xml": "<loc>https://www.kp.ru/online/news/7151500/</loc>"
                                                      "<loc>https://www.kp.ru/online/news/7150999/</loc>",
              re.compile(r"web\.archive\.org/cdx"): cdx_answer}
    f = fake(routes)
    src = {"type": "wayback", "prefix": "www.kp.ru/online/news/", "walk": "https://www.kp.ru/sitemap/news_02.xml",
           "block": 1000}
    got = source_wayback(f, src, DAY, DAY)
    urls = sorted(c.url for c in got)
    assert urls[0].startswith("https://www.kp.ru/online/news/7149") and urls[-1].startswith("https://www.kp.ru/online/news/7150")
    assert all(re.fullmatch(r"https://www\.kp\.ru/online/news/\d{7}/", u) for u in urls)
    blocks = [re.search(r"news%2F(\d+)", c).group(1) for c in f.calls if "cdx" in c]
    assert blocks == ["7150", "7149", "7148"]                  # stopped once a block predates the range


def test_wayback_prefix_with_date_placeholders(fake):
    rows = [["https://tvzvezda.ru/news/2026931200-aaaaa.html", stamp(datetime(2026, 9, 3, 13, tzinfo=MSK))],
            ["https://tvzvezda.ru/news/202691500-bbbbb.html", stamp(datetime(2026, 9, 1, 6, tzinfo=MSK))],   # too early
            ["https://tvzvezda.ru/news/2026931200-aaaaa.html?utm=x", stamp(datetime(2026, 9, 4, 1, tzinfo=MSK))]]
    f = fake({re.compile(r"cdx"): cdx(rows)})
    got = source_wayback(f, {"prefix": "tvzvezda.ru/news/{y}{m}", "per": "month"}, DAY, DAY)
    assert [c.url for c in got] == ["https://tvzvezda.ru/news/2026931200-aaaaa.html"]
    assert "url=tvzvezda.ru%2Fnews%2F20269" in f.calls[0]


# ── sitemap indexes ───────────────────────────────────────────────────────────
def test_sitemap_index_skips_stale_children_and_respects_max_children(fake):
    index = ("<sitemapindex>"
             "<sitemap><loc>https://v.ru/sitemap-article-1.xml</loc><lastmod>2026-09-10T00:00:00+00:00</lastmod></sitemap>"
             "<sitemap><loc>https://v.ru/sitemap-article-2.xml</loc><lastmod>2026-08-01T00:00:00+00:00</lastmod></sitemap>"
             "<sitemap><loc>https://v.ru/sitemap-tag-0.xml</loc><lastmod>2026-09-10T00:00:00+00:00</lastmod></sitemap>"
             "</sitemapindex>")
    child = ("<urlset><url><loc>https://v.ru/ns/a</loc><lastmod>2026-09-03T10:00:00+03:00</lastmod></url>"
             "<url><loc>https://v.ru/ns/b</loc><lastmod>2026-07-03T10:00:00+03:00</lastmod></url></urlset>")
    f = fake({"https://v.ru/sitemap.xml": index, "https://v.ru/sitemap-article-1.xml": child})
    got = source_sitemap_index(f, {"url": "https://v.ru/sitemap.xml", "child": r"sitemap-article-\d+\.xml$",
                                   "order": "lastmod", "max_children": 5}, DAY, DAY)
    assert [c.url for c in got] == ["https://v.ru/ns/a"]
    assert "https://v.ru/sitemap-article-2.xml" not in f.calls and "https://v.ru/sitemap-tag-0.xml" not in f.calls


# ── discover(): merging sources, errors, backfill-only sources ─────────────────
def outlet(sources):
    return Outlet(id="t", name="T", name_ru="T", lang="ru", group="state", home="https://t.ru", about={},
                  article=re.compile(r"^https://t\.ru/a/\d+$"), sources=sources)


def test_discover_merges_sources_and_keeps_going_after_a_failure(fake):
    feed = ("<rss><channel><item><title>Заголовок</title><link>https://t.ru/a/1</link>"
            "<description>Лид</description><pubDate>Thu, 03 Sep 2026 10:00:00 +0300</pubDate></item></channel></rss>")
    sm = "<urlset><url><loc>https://t.ru/a/1</loc><lastmod>2026-09-03T10:00:00+03:00</lastmod></url></urlset>"
    f = fake({"https://t.ru/rss": feed, "https://t.ru/sitemap.xml": sm})
    o = outlet([{"type": "sitemap", "per": "once", "url": "https://t.ru/sitemap.xml"},
                {"type": "rss", "url": "https://t.ru/rss"},
                {"type": "sitemap", "per": "once", "url": "https://t.ru/broken.xml"},
                {"type": "wayback", "prefix": "t.ru/a/"}])
    cands, errors = discover(f, o, DAY, DAY)
    assert len(cands) == 1 and cands[0].title == "Заголовок" and cands[0].lead == "Лид"
    assert len(errors) == 1 and "broken.xml" in errors[0]
    assert not any("archive.org" in c for c in f.calls)       # the wayback source is for backfills only


# ── cookies are scoped to the outlet's own site ───────────────────────────────
def test_fetcher_cookies_are_sent_only_to_their_site():
    f = Fetcher(cookies={"unity_pause_sso": "1"}, cookie_domain="gazeta.ru")
    jar = f.session.cookies
    own = requests.Request("GET", "https://www.gazeta.ru/news/").prepare()
    other = requests.Request("GET", "https://web.archive.org/").prepare()
    own.prepare_cookies(jar)
    other.prepare_cookies(jar)
    assert own.headers.get("Cookie") == "unity_pause_sso=1"
    assert "Cookie" not in other.headers
