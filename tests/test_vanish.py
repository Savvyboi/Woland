"""Articles taken down (woland/vanish.py): a nightly re-check of a capped sample of the last week's pages."""
from __future__ import annotations

import re
from datetime import date

from woland import merge, rewrites, store, vanish
from woland.config import Outlet

TODAY = date(2026, 9, 12)
D = date(2026, 9, 10)


def outlet(fetch=True):
    return Outlet(id="t", name="T", name_ru="T", lang="ru", group="state", home="https://t.ru", about={},
                  article=re.compile(r"^https://t\.ru/a/\d+$"), sources=[{"type": "rss", "url": "x"}], fetch=fetch)


def rec(n, **kw):
    return {"id": f"t:{n}", "o": "t", "u": f"https://t.ru/a/{n}", "p": f"2026-09-10T10:{n:02d}:00+03:00",
            "t": f"Заголовок {n}", "te": f"Headline {n}", "via": "page", **kw}


class Answers:
    """A fetcher whose pages answer with the status given per URL (200 otherwise)."""

    def __init__(self, status: dict):
        self.status, self.calls = status, []

    def get(self, url, **kw):
        from woland.net import Response
        self.calls.append(url)
        return Response(self.status.get(url, 200), url, b"")


def night(o, pending, status, at, sample=100):
    return vanish.check_outlet(o, TODAY, pending, sample=sample, fetcher=Answers(status), now=lambda: at)


def test_one_missing_answer_is_not_enough_two_in_a_row_are(archive):
    store.write_day(D, "t", [rec(1), rec(2), rec(3)])
    o, pending = outlet(), {}
    gone = {"https://t.ru/a/1": 404, "https://t.ru/a/2": 410}
    res = night(o, pending, gone, "2026-09-12T01:30:00Z")
    assert res["gone"] == [] and res["missing"] == 2 and set(pending) == set(gone)
    # the next night: a/2 answers again (a passing fault), a/1 is still missing
    res = night(o, pending, {"https://t.ru/a/1": 404}, "2026-09-13T01:30:00Z")
    assert [(g["u"], g["at"], g["s"]) for g in res["gone"]] == [("https://t.ru/a/1", "2026-09-12T01:30:00Z", 404)]
    assert pending == {}
    assert vanish.mark_gone("t", res["gone"]) == 1
    marked = {r["u"]: r for r in store.read_day(D, "t")}
    assert marked["https://t.ru/a/1"]["va"] == "2026-09-12T01:30:00Z" and marked["https://t.ru/a/1"]["vs"] == 404
    assert "va" not in marked["https://t.ru/a/2"] and marked["https://t.ru/a/1"]["t"] == "Заголовок 1"
    # a page found gone is not asked for again
    fetcher = Answers({})
    vanish.check_outlet(o, TODAY, {}, fetcher=fetcher)
    assert "https://t.ru/a/1" not in fetcher.calls


def test_the_sample_is_capped_pending_pages_first_and_only_pages_woland_read_itself(archive):
    store.write_day(D, "t", [rec(n) for n in range(1, 40)] + [rec(41, via="feed"), rec(42, ar="20260910120000")])
    cands = vanish.candidates("t", TODAY)
    assert len(cands) == 39 and "https://t.ru/a/41" not in cands and "https://t.ru/a/42" not in cands
    pending = {"https://t.ru/a/7": {"at": "2026-09-11T01:30:00Z", "s": 404, "d": D.isoformat()}}
    picked = vanish.pick(cands, pending, 10, "t:2026-09-12")
    assert len(picked) == 10 and picked[0] == ("https://t.ru/a/7", D.isoformat())
    assert picked == vanish.pick(cands, pending, 10, "t:2026-09-12")  # the same draw for the same night
    # days older than the window are not sampled
    assert vanish.candidates("t", date(2026, 9, 20)) == {}


def test_an_outlet_that_slows_us_down_or_refuses_is_left_alone_and_a_server_error_changes_nothing(archive):
    store.write_day(D, "t", [rec(n) for n in range(1, 10)])
    pending = {"https://t.ru/a/1": {"at": "2026-09-11T01:30:00Z", "s": 404, "d": D.isoformat()}}
    res = night(outlet(), pending, {"https://t.ru/a/1": 503}, "2026-09-12T01:30:00Z", sample=3)
    assert "https://t.ru/a/1" in pending and res["gone"] == []  # still pending
    res = night(outlet(), {}, {f"https://t.ru/a/{n}": 429 for n in range(1, 10)}, "x")
    assert res["stopped"] == "the site asked to slow down" and res["asked"] == 1
    res = night(outlet(), {}, {f"https://t.ru/a/{n}": 403 for n in range(1, 10)}, "x")
    assert res["stopped"] == "the site refused its pages" and res["asked"] == vanish.REFUSED_LIMIT


def test_stale_pending_pages_are_dropped_and_feed_only_outlets_are_not_asked(archive, monkeypatch):
    store.write_day(D, "t", [rec(1)])
    pending = {"https://t.ru/a/1": {"at": "2026-09-01T01:30:00Z", "s": 404, "d": D.isoformat()}}
    res = night(outlet(), pending, {"https://t.ru/a/1": 404}, "2026-09-12T01:30:00Z")
    assert res["gone"] == [] and pending["https://t.ru/a/1"]["at"] == "2026-09-12T01:30:00Z"  # counted afresh
    monkeypatch.setattr(vanish, "today_msk", lambda: TODAY)
    summary = vanish.recheck([outlet(fetch=False)])
    assert summary["outlets"] == {}


def test_the_merge_driver_keeps_a_gone_mark_and_merges_pending_pages():
    a = rec(1, va="2026-09-12T01:30:00Z", vs=404)
    b = {**rec(1), "r": "2099"}  # the other side read it later, without the mark
    out = merge._record(None, a, b)
    assert out["va"] == "2026-09-12T01:30:00Z" and out["vs"] == 404
    base = '{"t": {}}'
    ours = '{"t": {"https://t.ru/a/1": {"at": "2026-09-12T01:30:00Z", "d": "2026-09-10", "s": 404}}}'
    theirs = '{"t": {"https://t.ru/a/2": {"at": "2026-09-12T01:40:00Z", "d": "2026-09-10", "s": 410}}}'
    merged = merge.merge_json("gone.json", base, ours, theirs)
    assert "a/1" in merged and "a/2" in merged


def test_gone_articles_are_listed_for_the_site(archive):
    store.write_day(D, "t", [rec(1, va="2026-09-12T01:30:00Z", vs=410), rec(2)])
    data = rewrites.gather([D], ["t"], lambda r: False)
    assert data["gone_total"] == 1 and data["gone"][0]["u"] == "https://t.ru/a/1"
    assert data["gone"][0]["s"] == 410 and data["gone"][0]["te"] == "Headline 1"
    assert data["outlets"]["t"] == {"rewritten": 0, "articles": 2, "gone": 1}
