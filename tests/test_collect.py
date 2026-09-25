"""Collecting: what is kept, what is rejected, how progress is saved, and which days are planned."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pytest

from woland import collect, store
from woland.config import START_DATE, Outlet, load_lexicon
from woland.discover import Candidate
from woland.lexicon import Lexicon
from woland.util import MSK

LEX = Lexicon(load_lexicon())


def outlet(oid="t", fetch=True, sources=None):
    return Outlet(id=oid, name="T", name_ru="T", lang="ru", group="state", home="https://t.ru", about={},
                  article=re.compile(r"^https://t\.ru/a/\d+$"), sources=sources or [{"type": "rss", "url": "x"}],
                  fetch=fetch)


def page_info(day: date, n: int, title="Заголовок"):
    return {"title": f"{title} {n}", "lead": f"Лид статьи номер {n}, достаточно длинный.",
            "published": datetime(day.year, day.month, day.day, 10, n % 60, tzinfo=MSK), "modified": None,
            "section": "Политика", "tags": ["Россия"], "author": "", "body": "Текст статьи. " * 20}


@pytest.fixture
def fake_site(monkeypatch):
    """Discovery returns the given candidates; each page fetch looks its URL up in `pages`."""
    state = {"cands": [], "pages": {}, "errors": []}

    def discover(fetcher, o, start, end, **kw):
        return list(state["cands"]), list(state["errors"])

    def fetch_page(o, c, fetchers, local):
        v = state["pages"].get(c.url)
        if isinstance(v, int):
            return None, str(v), v, None
        return (v, None, 200, None) if v else (None, "unparsable", 200, None)

    monkeypatch.setattr(collect, "discover", discover)
    monkeypatch.setattr(collect, "_fetch_page", fetch_page)
    return state


D = date(2026, 9, 10)


def test_articles_from_other_days_are_kept_and_unwanted_ones_rejected(fake_site):
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}", hint=datetime(2026, 9, 10, 12, tzinfo=MSK)) for i in range(5)]
    fake_site["pages"] = {
        "https://t.ru/a/0": page_info(D, 0),                            # the day asked for
        "https://t.ru/a/1": page_info(D + timedelta(days=1), 1),        # another day of the chronicle: kept
        "https://t.ru/a/2": page_info(START_DATE - timedelta(days=5), 2),  # before the chronicle: rejected
        "https://t.ru/a/3": 404,                                        # gone: remembered, not retried
        "https://t.ru/a/4": 503,                                        # failed: will be retried
    }
    run = collect.collect_outlet(outlet(), D, D, LEX, known=set(), rejected_before={})
    assert sorted(r["u"] for r in run.records) == ["https://t.ru/a/0", "https://t.ru/a/1"]
    assert run.stats["other_day"] == 1 and run.stats["out_of_range"] == 1
    assert set(run.rejected) == {"https://t.ru/a/2", "https://t.ru/a/3"}


def test_known_and_previously_rejected_urls_are_not_fetched_again(fake_site):
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}") for i in range(3)]
    fake_site["pages"] = {"https://t.ru/a/2": page_info(D, 2)}
    run = collect.collect_outlet(outlet(), D, D, LEX, known={"https://t.ru/a/0": ("page", "2026-09-10")},
                                 rejected_before={"https://t.ru/a/1": "2026-09-20"})
    assert [r["u"] for r in run.records] == ["https://t.ru/a/2"]
    assert run.stats["known"] == 1 and run.stats["skipped"] == 1


def test_records_reach_the_sink_in_batches(fake_site):
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}") for i in range(25)]
    fake_site["pages"] = {f"https://t.ru/a/{i}": page_info(D, i) for i in range(25)}
    batches = []
    run = collect.collect_outlet(outlet(), D, D, LEX, set(), {}, sink=batches.append, flush_every=10)
    assert [len(b) for b in batches] == [10, 10, 5] and run.records == []
    assert run.stats["stored"] == 25


def test_an_outlet_that_only_fails_is_abandoned(fake_site):
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}") for i in range(100)]
    fake_site["pages"] = {f"https://t.ru/a/{i}": 403 for i in range(100)}
    run = collect.collect_outlet(outlet(), D, D, LEX, set(), {})
    assert run.aborted.startswith("unreachable") and run.stats["fail_403"] < 100


def test_an_outlet_that_starts_refusing_mid_run_is_abandoned_too(fake_site):
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}") for i in range(200)]
    fake_site["pages"] = {f"https://t.ru/a/{i}": page_info(D, i) if i < 32 else 401 for i in range(200)}
    run = collect.collect_outlet(outlet(), D, D, LEX, set(), {})
    assert run.aborted.startswith("refused after 32 pages") and run.stats["fail_401"] <= 16


def test_missing_pages_are_not_mistaken_for_a_block(fake_site):
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}") for i in range(60)]
    fake_site["pages"] = {f"https://t.ru/a/{i}": page_info(D, i) if i % 4 == 0 else 404 for i in range(60)}
    run = collect.collect_outlet(outlet(), D, D, LEX, set(), {})
    assert not run.aborted and run.stats["fail_404"] == 45 and len(run.records) == 15


# ── nothing found is thrown away: headline-only records, completed later ───────
def listed(i, day=D, hour=9):
    """A candidate as a sitemap or feed announces it: URL, time and headline."""
    return Candidate(url=f"https://t.ru/a/{i}", hint=datetime(day.year, day.month, day.day, hour, i % 60, tzinfo=MSK),
                     title=f"Заголовок из ленты {i}", lead="Лид из ленты." if i % 2 else "", via="sitemap")


def test_pages_refused_by_the_site_are_kept_as_what_the_listing_says(fake_site):
    # pages are tried newest first: the ten newest can be read, then the site starts refusing
    fake_site["cands"] = [listed(i) for i in range(40)]
    fake_site["pages"] = {**{f"https://t.ru/a/{i}": 429 for i in range(30)},
                          **{f"https://t.ru/a/{i}": page_info(D, i) for i in range(30, 40)}, "https://t.ru/a/20": 404}
    run = collect.collect_outlet(outlet(), D, D, LEX, set(), {})
    by_url = {r["u"]: r for r in run.records}
    assert run.aborted.startswith("refused after 10 pages") and len(by_url) == 39   # all but the 404
    assert by_url["https://t.ru/a/35"]["via"] == "page"
    headline_only = by_url["https://t.ru/a/3"]
    assert headline_only["via"] == "feed" and headline_only["w"] == 0 and headline_only["t"] == "Заголовок из ленты 3"
    assert headline_only["d"] == "Лид из ленты." and run.stats["listed"] == 29


def test_when_time_runs_out_the_rest_are_kept_from_the_listing(fake_site):
    fake_site["cands"] = [listed(i) for i in range(5)] + [Candidate(url="https://t.ru/a/99", hint=None, title="?")]
    budget = collect.Budget(1)
    budget.deadline -= 3600                                   # already spent
    run = collect.collect_outlet(outlet(), D, D, LEX, set(), {}, budget=budget)
    assert run.aborted == "time budget exhausted"
    assert sorted(r["u"] for r in run.records) == [f"https://t.ru/a/{i}" for i in range(5)]   # not the undated one
    assert all(r["via"] == "feed" for r in run.records)


def test_headline_only_records_are_completed_and_their_days_stay_open_until_then(fake_site, archive, monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 9, 24))
    fake_site["cands"] = [listed(1), listed(2)]
    fake_site["pages"] = {"https://t.ru/a/1": 429, "https://t.ru/a/2": 429}
    collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    assert [r["via"] for r in store.read_day(D, "t")] == ["feed", "feed"]
    assert store.load_coverage()["t"]["2026-09-10"]["status"] == "partial"
    # the next night the pages can be read; one of them the page dates three days later than the listing did
    later = page_info(D + timedelta(days=3), 2)
    later["published"] = datetime(2026, 9, 13, 0, 5, tzinfo=MSK)
    fake_site["pages"] = {"https://t.ru/a/1": page_info(D, 1), "https://t.ru/a/2": later}
    summary = collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    assert summary["outlets"]["t"]["new"] == 0 and summary["outlets"]["t"]["stats"]["upgraded"] == 2
    today, later_day = store.read_day(D, "t"), store.read_day(D + timedelta(days=3), "t")
    assert [(r["u"], r["via"]) for r in today] == [("https://t.ru/a/1", "page")]
    assert [(r["u"], r["via"]) for r in later_day] == [("https://t.ru/a/2", "page")]   # moved, not duplicated
    assert all(not k.startswith("_") for r in today + later_day for k in r)
    assert store.load_coverage()["t"]["2026-09-10"]["status"] == "complete"


def test_feed_only_outlets_store_what_the_feed_says(fake_site):
    fake_site["cands"] = [Candidate(url="https://t.ru/a/1", hint=datetime(2026, 9, 10, 9, tzinfo=MSK),
                                    title="Киевский режим готовит провокацию", lead="Коротко.", via="rss")]
    run = collect.collect_outlet(outlet(fetch=False), D, D, LEX, set(), {})
    rec = run.records[0]
    assert rec["via"] == "feed" and rec["w"] == 0 and rec["p"] == "2026-09-10T09:00:00+03:00"


def test_body_only_framings_carry_a_snippet(fake_site):
    info = page_info(D, 1)
    info["body"] = "Обычный текст. " * 30 + "Западные кураторы Киева снова молчат. " + "Ещё текст. " * 30
    fake_site["cands"] = [Candidate(url="https://t.ru/a/1")]
    fake_site["pages"] = {"https://t.ru/a/1": info}
    rec = collect.collect_outlet(outlet(), D, D, LEX, set(), {}).records[0]
    assert "кураторы" in rec["kb"]["collective-west"] and len(rec["kb"]["collective-west"]) <= 175


# ── a whole run: files, coverage, and state shared with other runs ─────────────
def test_run_collection_writes_days_and_coverage_and_keeps_other_runs_state(fake_site, archive, monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 9, 24))
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}") for i in range(4)]
    fake_site["pages"] = {"https://t.ru/a/0": page_info(D, 0), "https://t.ru/a/1": page_info(D, 1),
                          "https://t.ru/a/2": page_info(D + timedelta(days=1), 2), "https://t.ru/a/3": 404}
    # another run (the hourly feeds, say) has recorded coverage for another outlet meanwhile
    store.save_coverage({"other": {"2026-09-10": {"n": 7, "status": "feed"}}})
    summary = collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    assert summary["outlets"]["t"]["new"] == 3
    assert len(store.read_day(D, "t")) == 2 and len(store.read_day(D + timedelta(days=1), "t")) == 1
    cov = store.load_coverage()
    assert cov["other"]["2026-09-10"]["n"] == 7                        # not overwritten
    assert cov["t"]["2026-09-10"]["n"] == 2 and cov["t"]["2026-09-10"]["status"] == "complete"
    assert "https://t.ru/a/3" in store.load_seen()["t"]
    # a second run adds nothing and fetches nothing new
    summary = collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    stats = summary["outlets"]["t"]["stats"]
    assert summary["outlets"]["t"]["new"] == 0 and stats["known"] == 3 and stats["skipped"] == 1


@pytest.mark.parametrize("failure, status", [(404, "complete"), (503, "partial")])
def test_days_with_passing_failures_stay_open_for_a_retry(fake_site, archive, monkeypatch, failure, status):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 9, 24))
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{i}") for i in range(30)]
    fake_site["pages"] = {f"https://t.ru/a/{i}": page_info(D, i) if i < 20 else failure for i in range(30)}
    collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    assert store.load_coverage()["t"]["2026-09-10"]["status"] == status


def test_merge_day_keeps_existing_records_and_fills_missing_fields(archive):
    store.write_day(D, "t", [{"id": "t:1", "u": "https://t.ru/a/1", "p": "2026-09-10T10:00:00+03:00", "t": "A"}])
    n = store.merge_day(D, "t", [{"id": "t:1", "u": "https://t.ru/a/1", "p": "2026-09-10T10:00:00+03:00", "t": "B", "te": "A!"},
                                 {"id": "t:2", "u": "https://t.ru/a/2", "p": "2026-09-10T09:00:00+03:00", "t": "C"}])
    recs = store.read_day(D, "t")
    assert n == 2 and [r["t"] for r in recs] == ["C", "A"] and recs[1]["te"] == "A!"


# ── planning which days to collect ────────────────────────────────────────────
def test_plan_revisits_the_last_week_and_reaches_back_to_the_oldest_gap(monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 10, 20))
    days = [START_DATE + timedelta(days=k) for k in range((date(2026, 10, 20) - START_DATE).days)]
    cov = {"t": {d.isoformat(): {"status": "complete"} for d in days}}
    cov["t"]["2026-10-03"]["status"] = "partial"
    ranges = collect.plan([outlet()], cov, catch_up_days=45)
    assert ranges["t"] == (date(2026, 10, 3), date(2026, 10, 20))
    cov["t"]["2026-10-03"]["status"] = "complete"
    assert collect.plan([outlet()], cov, catch_up_days=45)["t"] == (date(2026, 10, 14), date(2026, 10, 20))
    # feed-only outlets cannot go back: only the rolling window
    assert collect.plan([outlet(fetch=False)], {}, catch_up_days=45)["t"] == (date(2026, 10, 14), date(2026, 10, 20))


def test_a_day_far_quieter_than_usual_is_looked_at_again(monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 10, 20))
    days = [START_DATE + timedelta(days=k) for k in range((date(2026, 10, 20) - START_DATE).days)]
    cov = {"t": {d.isoformat(): {"status": "complete", "n": 80} for d in days}}
    cov["t"]["2026-10-02"]["n"] = 0        # a listing that lagged: nothing was found that day
    assert collect.plan([outlet()], cov, catch_up_days=45)["t"][0] == date(2026, 10, 2)
    cov["t"]["2026-10-02"]["n"] = 35       # a quiet Sunday is not a hole
    assert collect.plan([outlet()], cov, catch_up_days=45)["t"][0] == date(2026, 10, 14)
    small = {"t": {d.isoformat(): {"status": "complete", "n": 4} for d in days}}
    small["t"]["2026-10-02"]["n"] = 0      # outlets that publish a few items a day may have none
    assert collect.plan([outlet()], small, catch_up_days=45)["t"][0] == date(2026, 10, 14)


def test_a_day_is_complete_once_it_is_over_in_moscow():
    at = datetime(2026, 9, 11, 4, 17, tzinfo=MSK)
    assert collect._day_complete(date(2026, 9, 10), at)
    assert not collect._day_complete(date(2026, 9, 11), at)
    assert not collect._day_complete(date(2026, 9, 10), datetime(2026, 9, 11, 1, 0, tzinfo=MSK))
