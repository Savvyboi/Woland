"""Collecting: what is kept, what is rejected, how progress is saved, and which days are planned."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pytest

from woland import collect, store
from woland.config import START_DATE, Outlet, load_lexicon
from woland.discover import Candidate
from woland.lexicon import Lexicon
from woland.util import MSK, iso_utc, now_utc

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


# ── one URL, one record: the index of every URL stored ─────────────────────────
def stored(i, day=D, via="page"):
    return {"id": f"t:{i}", "o": "t", "u": f"https://t.ru/a/{i}", "p": f"{day.isoformat()}T10:00:00+03:00",
            "t": f"Заголовок {i}", "w": 0 if via == "feed" else 100, "h": "0" * 16, "r": "2026-09-10T08:00:00Z",
            "via": via}


def test_the_url_index_is_built_from_the_day_files_once_then_appended_to(archive):
    store.write_day(D, "t", [stored(1), stored(2)])                  # stored before the index existed
    store.merge_day(D + timedelta(days=1), "t", [stored(3, D + timedelta(days=1))])
    store.merge_day(D, "t", [stored(2), stored(4)])                  # 2 is already there: not listed twice
    index = store.load_url_index("t")
    assert index == {store.url_key(f"https://t.ru/a/{i}"): d for i, d in
                     [(1, "2026-09-10"), (2, "2026-09-10"), (3, "2026-09-11"), (4, "2026-09-10")]}
    assert store.rebuild_url_index("t") == index
    lines = (archive / "data" / "state" / "urls" / "t.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and all(len(line) == 27 for line in lines)


def test_one_url_is_filed_once_however_late_a_site_re_dates_it(fake_site, archive, monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 12, 20))
    store.merge_day(date(2026, 9, 3), "t", [stored(1, date(2026, 9, 3))])
    # in December the site re-dates the September page ("when the heating comes on"), long after the
    # weeks whose day files a run reads
    fake_site["cands"] = [listed(1, date(2026, 12, 18))]
    fake_site["pages"] = {"https://t.ru/a/1": page_info(date(2026, 12, 18), 1)}
    summary = collect.run_collection({"t": (date(2026, 12, 14), date(2026, 12, 20))}, [outlet()],
                                     mode="daily", translate=False)
    assert summary["outlets"]["t"]["stats"]["known"] == 1 and summary["outlets"]["t"]["new"] == 0
    assert store.read_day(date(2026, 12, 18), "t") == []


# ── state shared by runs that overlap ──────────────────────────────────────────
def test_two_runs_over_different_days_of_one_outlet_keep_each_others_coverage(archive):
    store.save_coverage({"t": {"2026-09-10": {"n": 5, "status": "partial"}}})
    # a long backfill read the coverage before that, and has since changed the 11th only
    mine = {"t": {"2026-09-10": {"n": 1, "status": "partial"}, "2026-09-11": {"n": 3, "status": "complete"}}}
    store.save_coverage(mine, only={"t": {"2026-09-11"}})
    cov = store.load_coverage()["t"]
    assert cov["2026-09-10"]["n"] == 5 and cov["2026-09-11"]["n"] == 3
    store.save_seen({"t": {"https://t.ru/a/1": "2026-09-20"}}, date(2026, 9, 24))
    store.save_seen({"t": {"https://t.ru/a/2": "2026-09-21"}}, date(2026, 9, 24), only={"t": {"https://t.ru/a/2"}})
    assert set(store.load_seen()["t"]) == {"https://t.ru/a/1", "https://t.ru/a/2"}


def test_frequent_polls_do_not_push_the_nightly_runs_out_of_the_log(archive):
    store.append_run({"at": "2026-09-02T01:17:00Z", "mode": "daily", "outlets": {}})
    for i in range(200):
        store.append_run({"at": f"2026-09-02T{i // 60:02d}:{i % 60:02d}:30Z", "mode": "poll", "outlets": {}})
    runs = store.load_runs()
    assert [r["mode"] for r in runs].count("daily") == 1 and len(runs) == 49


def test_polling_skips_turns_it_does_not_need(archive, monkeypatch):
    store.append_run({"at": iso_utc(now_utc() - timedelta(minutes=50)), "mode": "poll", "outlets": {}})
    assert collect.poll([outlet()], min_gap=40) is not None           # read 50 minutes ago: read again
    assert collect.poll([outlet()], min_gap=40) is None               # just read: nothing to do
    assert collect.poll([outlet()]) is not None                       # (unless asked)


# ── headline-only records: read again until their pages are read or gone ──────
def test_headline_only_records_on_a_complete_day_are_read_again(fake_site, archive, monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 10, 20))
    old = date(2026, 10, 2)
    # a feed reader filed a headline-only record under a day long marked complete
    store.merge_day(old, "t", [stored(7, old, via="feed")])
    days = [START_DATE + timedelta(days=k) for k in range((date(2026, 10, 20) - START_DATE).days)]
    cov = {"t": {d.isoformat(): {"status": "complete", "n": 80} for d in days}}
    cov["t"]["2026-10-02"]["h"] = 1
    assert collect.plan([outlet()], cov, catch_up_days=45)["t"][0] == old
    assert collect.plan([outlet(fetch=False, sources=[{"type": "sitemap", "url": "x"}])], cov, 45)["t"][0] > old
    # no listing announces it any more: its page is read all the same
    fake_site["cands"] = []
    fake_site["pages"] = {"https://t.ru/a/7": page_info(old, 7)}
    summary = collect.run_collection({"t": (old, old)}, [outlet()], mode="daily", translate=False)
    assert summary["outlets"]["t"]["stats"]["upgraded"] == 1
    assert [r["via"] for r in store.read_day(old, "t")] == ["page"]
    assert "h" not in store.load_coverage()["t"]["2026-10-02"]


def test_a_headline_whose_page_is_gone_does_not_hold_its_day_open(fake_site, archive, monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 9, 24))
    fake_site["cands"] = [listed(1), listed(2)]
    fake_site["pages"] = {"https://t.ru/a/1": page_info(D, 1), "https://t.ru/a/2": 429}
    collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    entry = store.load_coverage()["t"]["2026-09-10"]
    assert entry["status"] == "partial" and entry["h"] == 1
    fake_site["pages"]["https://t.ru/a/2"] = 404                     # the next night: taken down
    summary = collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    assert summary["outlets"]["t"]["stats"]["upgrade_gone"] == 1
    entry = store.load_coverage()["t"]["2026-09-10"]
    assert entry["status"] == "complete" and "h" not in entry
    assert sorted((r["u"][-1], r["via"]) for r in store.read_day(D, "t")) == [("1", "page"), ("2", "feed")]
    summary = collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    assert "upgrade_gone" not in summary["outlets"]["t"]["stats"]            # and not asked for again


# ── coverage ───────────────────────────────────────────────────────────────────
def test_coverage_is_counted_for_every_day_a_run_filed_articles_under(fake_site, archive, monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 9, 24))
    fake_site["cands"] = [Candidate(url="https://t.ru/a/1"), Candidate(url="https://t.ru/a/2")]
    fake_site["pages"] = {"https://t.ru/a/1": page_info(D, 1), "https://t.ru/a/2": page_info(D + timedelta(days=4), 2)}
    collect.run_collection({"t": (D, D)}, [outlet()], mode="backfill", translate=False)
    cov = store.load_coverage()["t"]
    assert cov["2026-09-10"] | {"at": ""} == {"n": 1, "found": 0, "status": "complete", "at": ""}
    assert cov["2026-09-14"]["n"] == 1 and cov["2026-09-14"]["status"] == "partial"   # counted, not judged


def test_an_empty_day_in_a_backfill_from_the_first_day_is_not_called_complete(fake_site, archive, monkeypatch):
    monkeypatch.setattr(collect, "today_msk", lambda: date(2026, 9, 24))
    start = START_DATE
    busy = [k for k in range(10) if k != 4]                  # 40 articles a day, none found on the fifth
    fake_site["cands"] = [Candidate(url=f"https://t.ru/a/{k * 100 + i}") for k in busy for i in range(40)]
    fake_site["pages"] = {f"https://t.ru/a/{k * 100 + i}": page_info(start + timedelta(days=k), i)
                          for k in busy for i in range(40)}
    collect.run_collection({"t": (start, start + timedelta(days=9))}, [outlet()], mode="backfill", translate=False)
    cov = store.load_coverage()["t"]
    assert cov["2026-09-05"]["n"] == 0 and cov["2026-09-05"]["status"] == "partial"
    assert cov["2026-09-04"]["status"] == "complete" and cov["2026-09-06"]["status"] == "complete"


# ── time and reach ─────────────────────────────────────────────────────────────
def test_a_slow_outlet_has_its_own_time_budget(fake_site, archive, monkeypatch):
    total = collect.Budget(270)
    assert collect.Budget(90, within=total).deadline < total.deadline
    assert collect.Budget(None, within=total).deadline == total.deadline == collect.Budget(500, within=total).deadline
    assert collect.Budget(None, within=collect.Budget(None)).deadline is None
    deadlines = {}
    real = collect.collect_outlet

    def spy(o, *a, budget=None, **kw):
        deadlines[o.id] = budget.deadline
        return real(o, *a, budget=budget, **kw)

    monkeypatch.setattr(collect, "collect_outlet", spy)
    slow = outlet("s")
    slow.budget = 90
    collect.run_collection({"t": (D, D), "s": (D, D)}, [outlet(), slow], mode="backfill", translate=False)
    assert deadlines["t"] is None and deadlines["s"] is not None


ARTICLE = """<html><head><meta property="og:title" content="Заголовок статьи">
<meta property="og:description" content="Лид статьи о событиях дня.">
<meta property="article:published_time" content="2026-09-10T10:00:00+03:00"></head>
<body><article><h1>Заголовок статьи</h1><p>Первый абзац статьи о событиях дня, достаточно длинный для текста.</p>
<p>Второй абзац с подробностями о том, что произошло.</p></article></body></html>"""


def test_a_page_is_read_from_the_archive_copy_while_the_outlet_does_not_answer(monkeypatch):
    import threading
    from woland import net
    health = net._HostHealth(limit=1, pause=900)
    monkeypatch.setattr(net, "HEALTH", health)
    asked, answer = [], [200]

    class Fetcher:
        requests = 0

        def get(self, url, gap=None, **kw):
            asked.append((url, gap))
            return net.Response(answer[0], url, ARTICLE.encode(), {"content-type": "text/html; charset=utf-8"})

    local = threading.local()
    local.fetcher = Fetcher()
    c = Candidate(url="https://t.ru/a/1", capture="20260910081500")
    info, fail, _, _ = collect._fetch_page(outlet(), c, [], local)          # the outlet answers: read it
    assert asked[-1] == ("https://t.ru/a/1", None) and not fail and "capture" not in info
    health.failed("t.ru")                                                     # it stops answering
    info, fail, _, _ = collect._fetch_page(outlet(), c, [], local)
    assert asked[-1] == ("https://web.archive.org/web/20260910081500id_/https://t.ru/a/1", 4.0)
    rec, _ = collect.build_record(outlet(), c, info)
    assert rec["ar"] == "20260910081500" and rec["via"] == "page" and rec["u"] == "https://t.ru/a/1"
    assert rec["t"] == "Заголовок статьи" and rec["w"] > 10
    answer[0] = 404                               # the Archive has no such copy: try again another time
    assert collect._fetch_page(outlet(), c, [], local)[1:3] == ("archive", None)
    n = len(asked)
    info, fail, _, _ = collect._fetch_page(outlet(), Candidate(url="https://t.ru/a/2"), [], local)
    assert fail == "down" and len(asked) == n                        # nothing captured: it waits for another run


def test_while_an_outlet_does_not_answer_pages_without_a_copy_wait_for_another_run(monkeypatch):
    from woland import net
    health = net._HostHealth(limit=1, pause=900)
    health.failed("t.ru")                                        # the outlet does not answer
    monkeypatch.setattr(net, "HEALTH", health)
    asked = []

    class Fetcher:
        requests = 0

        def get(self, url, gap=None, **kw):
            asked.append(url)
            return net.Response(200, url, ARTICLE.encode(), {"content-type": "text/html; charset=utf-8"})

    monkeypatch.setattr(Outlet, "fetcher", lambda self, **kw: Fetcher())
    copies = [Candidate(url=f"https://t.ru/a/{100 + i}", capture="20260910081500") for i in range(5)]
    monkeypatch.setattr(collect, "discover", lambda *a, **kw: (copies, ["sitemap: https://t.ru/s.xml: NoConnection"]))
    retry = [stored(i, via="feed") for i in range(20)]           # headline-only records the Archive never captured
    known = {r["u"]: ("feed", "2026-09-10") for r in retry}
    run = collect.collect_outlet(outlet(), D, D, LEX, known, {}, retry=retry)
    assert not run.aborted and run.stats["fail_down"] == 20 and run.stats["stored"] == 5
    assert len(asked) == 5 and all(u.startswith("https://web.archive.org/web/20260910081500id_/") for u in asked)


def test_an_outlet_that_cannot_be_reached_at_all_is_reported_as_such(fake_site):
    fake_site["errors"] = ["html_list: https://t.ru/news/: ConnectTimeout: HTTPSConnectionPool(host='t.ru')",
                           "sitemap_index: https://t.ru/s.xml: NoConnection: t.ru did not answer"]
    fake_site["pages"] = {"https://t.ru/a/7": page_info(D, 7)}
    run = collect.collect_outlet(outlet(), D, D, LEX, {"https://t.ru/a/7": ("feed", "2026-09-10")}, {},
                                 retry=[stored(7, via="feed")])
    assert run.aborted == "no connection to t.ru" and run.stats["to_upgrade"] == 1
    assert "upgraded" not in run.stats and not run.records                   # nothing else was tried
