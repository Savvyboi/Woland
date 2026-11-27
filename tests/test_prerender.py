"""woland/prerender.py writes numbers and days as the Today page does in English (core.js) and picks the
same rising framings (today.js notable)."""
from __future__ import annotations

from woland.config import ROOT
from woland.prerender import en_strings, fmt_day, fmt_int, fmt_pct, fmt_small, notable, page_tags


def test_numbers_and_days_are_written_as_the_page_writes_them():
    assert fmt_int(7982) == "7,982" and fmt_int(None) == "0"
    assert fmt_pct(0.1129, 0) == "11%" and fmt_pct(0.0368) == "3.7%" and fmt_pct(0.0071) == "0.71%" and fmt_pct(None) == "–"
    assert fmt_small(0.4) == "<1" and fmt_small(0) == "0" and fmt_small(1.57) == "2"
    assert fmt_day("2026-11-26", True) == "Thursday 26 November 2026" and fmt_day("2026-11-26") == "26 Nov 2026"


def test_only_a_framing_far_above_its_usual_share_is_rising():
    assert notable({"n": 110, "base": 0.0071}, 7982)           # 57 expected
    assert not notable({"n": 9, "base": 0.0001}, 7982)         # too few articles to say
    assert not notable({"n": 300, "base": 0.036}, 7982)        # its usual share
    assert not notable({"n": 50, "base": None}, 7982)          # no history


def test_the_interface_strings_are_read_from_the_site():
    s = en_strings(ROOT / "site" / "assets" / "js" / "i18n.js")
    assert s["today.lede"].startswith("On {day}, Woland collected {total} articles") and s["noscript"]


def test_every_page_gets_one_set_of_preview_tags():
    html = ('<head><title>Woland — Archive</title><meta name="description" content="Search &amp; cite">'
            '<meta property="og:title" content="x">\n<meta property="og:description" content="y">\n</head>')
    out = page_tags(html, "archive.html", "https://example.org/w/")
    assert out.count("og:title") == 1 and 'content="Woland — Archive"' in out and 'content="Search &amp; cite"' in out
    assert '<meta property="og:url" content="https://example.org/w/archive.html">' in out
    assert '<meta property="og:image" content="https://example.org/w/assets/img/og-card.png">' in out
    assert 'og:url' not in page_tags(html, "archive.html", "")    # the site's address unknown (a local build)
