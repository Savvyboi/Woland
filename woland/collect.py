"""Collecting: discover → fetch → extract → tag → translate → store."""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .config import START_DATE, Outlet, load_lexicon, load_outlets
from .discover import Candidate, discover, parse_sitemap
from .extract import clean_lead, clean_title, extract, first_paragraph, published_from_url
from .lexicon import Lexicon
from .store import (append_run, drop_urls, headline_only, known_urls, load_coverage, load_runs, load_seen,
                    merge_day, read_day, save_coverage, save_seen)
from .translate import get_translator
from .util import (MSK, canonical_url, daterange, fingerprint, iso_msk, iso_utc, msk_day, now_utc, parse_dt,
                   short_hash, today_msk, truncate)

log = logging.getLogger("woland.collect")

BODY_FAMILIES = ("framing",)  # topics are matched on headline and lead only


@dataclass
class OutletRun:
    outlet: Outlet
    start: date
    end: date
    records: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)
    found_by_day: Counter = field(default_factory=Counter)
    published_by_day: dict = field(default_factory=dict)
    rejected: dict = field(default_factory=dict)
    aborted: str = ""
    seconds: float = 0.0
    requests: int = 0


class Budget:
    """A deadline in minutes from now; with `within`, never later than that budget's own deadline."""

    def __init__(self, minutes: float | None, within: Budget | None = None):
        self.deadline = time.monotonic() + minutes * 60 if minutes else None
        if within is not None and within.deadline is not None:
            self.deadline = within.deadline if self.deadline is None else min(self.deadline, within.deadline)

    def exceeded(self) -> bool:
        return self.deadline is not None and time.monotonic() > self.deadline


# how net.Fetcher reports a host that could not be reached at all
_NO_CONNECTION = re.compile(r"\b(NoConnection|ConnectTimeout|ConnectionError|SSLError)\b")


def _dedupe_lead(title: str, lead: str) -> str:
    """Drop a lead that merely repeats the headline; strip a repeated headline from its start."""
    if not lead:
        return ""
    nt, nl = title.strip().rstrip(".!?…").lower(), lead.strip().lower()
    if nl.rstrip(".!?…") == nt or nt.startswith(nl.rstrip(".!?…")):
        return ""
    if nl.startswith(nt):
        rest = lead.strip()[len(title.strip().rstrip(".!?…")):].lstrip(" .!?…:—-")
        return rest if len(rest) > 25 else ""
    return lead


def build_record(o: Outlet, c: Candidate, info: dict | None) -> tuple[dict, str] | None:
    info = info or {}
    title = info.get("title") or clean_title(c.title)
    lead = info.get("lead") or clean_lead(c.lead)
    published = info.get("published") or c.hint or published_from_url(c.url)
    if not title or not published:
        return None
    if o.tz_fix:
        published = published.replace(tzinfo=MSK)  # Moscow wall-clock time under a wrong offset label
    body = info.get("body") or c.body or ""
    lead = _dedupe_lead(title, lead) or _dedupe_lead(title, clean_lead(first_paragraph(body, title)))
    lead = truncate(lead, 240) if lead else ""
    rec = {"id": f"{o.id}:{short_hash(c.url)}", "o": o.id, "u": c.url, "p": iso_msk(published),
           "t": truncate(title, 300)}
    if info.get("modified") and info["modified"] > published:
        rec["m"] = iso_msk(info["modified"])
    if lead:
        rec["d"] = lead
    section = info.get("section") or c.section
    if section:
        rec["s"] = section[:60]
    if info.get("tags"):
        rec["g"] = info["tags"]
    author = info.get("author") or c.author
    if author:
        rec["a"] = author[:120]
    rec["w"] = len(body.split())
    rec["h"] = fingerprint(body or f"{title} {lead}")
    rec["r"] = iso_utc()
    rec["via"] = "page" if info else "feed"
    return rec, body


def _fetch_page(o: Outlet, c: Candidate, fetchers: list, local: threading.local):
    """Fetch and read one article page. Returns (info or None, failure reason or None, HTTP status, error)."""
    if not hasattr(local, "fetcher"):
        local.fetcher = o.fetcher()
        fetchers.append(local.fetcher)
    r = local.fetcher.get(c.url)  # (it slows down by itself when the site asks it to)
    if not r.ok or r.challenged():
        return None, ("bot-check" if r.ok else (str(r.status) if r.status else "network")), r.status, r.error
    info = extract(r.text, c.url, o.headline)
    return (info, None, r.status, None) if info else (None, "unparsable", r.status, None)


def collect_outlet(o: Outlet, start: date, end: date, lex: Lexicon, known: dict, rejected_before: dict, *,
                   feeds_only: bool = False, backfill: bool = False, limit: int | None = None,
                   budget: Budget | None = None, sink=None, flush_every: int = 300,
                   retry: list[dict] = ()) -> OutletRun:
    """Discover and read one outlet's articles for [start, end].

    known: URLs already stored → "page" or "feed" (headline only). Records go to `sink` in batches as they
    are read (so an interrupted run keeps its work), or, without a sink, to run.records.

    Nothing Woland has found is thrown away. An article that turns out to belong to another day of the
    chronicle is kept under that day. An article whose page could not be read — the site refused, asked
    us to slow down, or the time ran out — is kept as what the outlet's own listing or feed says about it
    (headline, lead if any, time; via "feed"), and later runs try its page again to complete the record:
    `retry` holds such stored records, tried even if no listing announces them again."""
    run = OutletRun(o, start, end)
    t0 = time.monotonic()
    budget = budget or Budget(None)
    fetcher = o.fetcher()
    fetchers = [fetcher]
    local = threading.local()
    today_d = today_msk()
    today = today_d.isoformat()
    pending: list[dict] = []

    def keep(rec):
        (pending if sink else run.records).append(rec)
        if sink and len(pending) >= flush_every:
            sink(pending[:])
            pending.clear()

    cands, run.errors = discover(fetcher, o, start, end, feeds_only=feeds_only, backfill=backfill)
    todo, upgrades, urls = [], [], set()
    unread = []  # new candidates whose pages were refused or not reached
    for c in cands:
        c.url = canonical_url(c.url)
        if c.url.startswith("http://") and o.home.startswith("https://"):
            c.url = "https://" + c.url[7:]
        if not o.is_article(c.url) or c.url in urls:
            run.stats["not_article" if c.url not in urls else "duplicate"] += 1
            continue
        urls.add(c.url)
        if c.hint and start <= msk_day(c.hint) <= end:
            run.found_by_day[msk_day(c.hint).isoformat()] += 1
        if c.url in known:
            if o.fetch and not feeds_only and known[c.url][0] == "feed" and c.url not in rejected_before:
                upgrades.append(c)  # stored from a listing only: try the page again
            else:
                run.stats["known"] += 1
        elif c.url in rejected_before:
            run.stats["skipped"] += 1
        else:
            todo.append(c)
    if o.fetch and not feeds_only:
        for r in retry:  # headline-only records no listing announced this time
            if r["u"] not in urls and r["u"] in known and r["u"] not in rejected_before:
                urls.add(r["u"])
                upgrades.append(Candidate(url=r["u"], hint=parse_dt(r["p"]), title=r["t"], lead=r.get("d", ""),
                                          via="stored"))
    if not cands and run.errors and all(_NO_CONNECTION.search(e) for e in run.errors):
        run.aborted = f"no connection to {o.host}"

    def priority(c):  # announced inside the range first, newest first; margin candidates last
        inside = c.hint is not None and start <= msk_day(c.hint) <= end
        return (not inside, -(c.hint.timestamp() if c.hint else 0))
    todo.sort(key=priority)
    if limit:
        todo = todo[:limit]
    new = set(id(c) for c in todo)
    todo += sorted(upgrades, key=priority)  # new articles first, then completing headline-only ones
    run.stats["to_fetch"] = len(todo)
    if upgrades:
        run.stats["to_upgrade"] = len(upgrades)
    log.info("%-10s %s..%s: %d candidates, %d new%s", o.id, start, end, len(urls), len(new),
             f", {len(upgrades)} to complete" if upgrades else "")

    ok = streak = 0  # pages read; pages refused in a row (a site that starts blocking mid-run)
    step = o.parallel * 8
    reached = 0  # candidates attempted so far
    for i in range(0, len(todo), step):
        if run.aborted:  # (no connection at all)
            break
        if budget.exceeded():
            run.aborted = "time budget exhausted"
            break
        chunk = todo[i:i + step]
        reached = i + len(chunk)
        if o.fetch:
            with ThreadPoolExecutor(max_workers=o.parallel) as pool:
                pages = list(pool.map(lambda c: _fetch_page(o, c, fetchers, local), chunk))
        else:
            pages = [(None, None, None, None)] * len(chunk)
        for c, (info, fail, status, error) in zip(chunk, pages):
            if fail:
                run.stats[f"fail_{fail}"] += 1
                if status in (404, 410) or error == "disallowed by robots.txt":
                    run.rejected[c.url] = today
                    if id(c) not in new:
                        run.stats["upgrade_gone"] += 1  # the headline is all there is left of it
                elif fail != "unparsable":
                    streak += 1
                    if id(c) in new:
                        unread.append(c)
                continue
            ok += 1
            streak = 0
            built = build_record(o, c, info)
            if built is None:
                run.stats["incomplete"] += 1
                continue
            rec, body = built
            day = date.fromisoformat(rec["p"][:10])
            if not START_DATE <= day <= today_d:
                run.rejected[c.url] = today
                run.stats["out_of_range"] += 1
                continue
            if not start <= day <= end:
                run.stats["other_day"] += 1
            head, body_hits = lex.tag(rec["t"], rec.get("d", ""), body, o.lang)
            kb = {nid: snip for nid, snip in body_hits.items()
                  if nid not in head and lex.by_id[nid].family in BODY_FAMILIES}
            if kb:
                rec["kb"] = kb
            if id(c) not in new:
                rec["_was"] = known[c.url][1]  # completes a headline-only record, filed under this day
                run.stats["upgraded"] += 1
            keep(rec)
            run.stats["stored"] += 1
        if streak >= (5 if feeds_only else 15):  # the site is refusing us (or down): stop; a later run tries again
            reasons = ", ".join(k[5:] for k in run.stats if k.startswith("fail_"))
            run.aborted = f"unreachable ({reasons})" if not ok else f"refused after {ok} pages ({reasons})"
            break
        if (i // step) % 20 == 19:
            log.info("%-10s %d/%d fetched", o.id, min(i + step, len(todo)), len(todo))
    unread += [c for c in todo[reached:] if id(c) in new]  # not reached: time ran out, or the site refused
    # Keep what the listing or feed says about pages that could not be read.
    if o.fetch and not limit:
        for c in unread:
            if not (c.title and c.hint and start <= msk_day(c.hint) <= end):
                continue
            built = build_record(o, c, None)
            if built is None:
                continue
            keep(built[0])
            run.stats["listed"] += 1
    if sink and pending:
        sink(pending[:])

    if o.coverage_sitemap and not feeds_only:
        r = fetcher.get(o.coverage_sitemap)
        if r.ok:
            _, entries = parse_sitemap(r.text)
            counts = Counter()
            for e in entries:
                dt = parse_dt(e["lastmod"])
                if dt and start <= msk_day(dt) <= end:
                    counts[msk_day(dt).isoformat()] += 1
            run.published_by_day = dict(counts)
    run.requests = sum(f.requests for f in fetchers)
    run.seconds = round(time.monotonic() - t0, 1)
    return run


def translate_records(records: list[dict]) -> int:
    todo = [r for r in records if r.get("t") and not r.get("te")]
    if not todo:
        return 0
    tr = get_translator()
    if tr is None:
        return 0
    for r, en in zip(todo, tr.translate([r["t"] for r in todo])):
        if en:
            r["te"] = en
    return len(todo)


def _day_complete(day: date, run_started_msk: datetime) -> bool:
    today = run_started_msk.date()
    return day <= today - timedelta(days=2) or (day == today - timedelta(days=1) and run_started_msk.hour >= 3)


KNOWN_DAYS = 45  # how far back already-stored URLs are looked up

# Every night the last WINDOW + 1 days are looked at again. Discovery is cheap (articles already stored
# are skipped), and several sources only list an article a day or two after it appeared.
WINDOW = 6


def typical_day(cov: dict, before: date, days: int = 28, through: date | None = None) -> float:
    """An outlet's usual number of articles a day: the median over the `days` days before `before` and,
    with `through`, the days from `before` to `through` too — a backfill from the first day has nothing
    earlier to compare with. Days not yet over do not count; 0 with fewer than five days to go on."""
    upper = min(through + timedelta(days=1) if through else before, today_msk()).isoformat()
    counts = sorted(v.get("n", 0) for k, v in cov.items()
                    if (before - timedelta(days=days)).isoformat() <= k < upper)
    return counts[len(counts) // 2] if len(counts) >= 5 else 0


def plan(outlets: list[Outlet], coverage: dict, catch_up_days: int, window: int = WINDOW) -> dict[str, tuple[date, date]]:
    """Date range per outlet: the rolling window plus the oldest day that is not yet complete, that holds
    far fewer articles than the outlet usually publishes, or whose articles are partly headline only."""
    today = today_msk()
    oldest = max(START_DATE, today - timedelta(days=catch_up_days))
    ranges = {}
    for o in outlets:
        start = today - timedelta(days=window)
        if o.can_backfill:
            cov = coverage.get(o.id, {})
            typical = typical_day(cov, today)
            d = oldest
            while d < start:
                e = cov.get(d.isoformat(), {})
                if e.get("status") != "complete" or (o.fetch and e.get("h")) \
                        or (typical >= 20 and e.get("n", 0) < 0.25 * typical):
                    start = d
                    break
                d += timedelta(days=1)
        ranges[o.id] = (max(start, START_DATE), today)
    return ranges


def run_collection(ranges: dict[str, tuple[date, date]], outlets: list[Outlet], *, mode: str = "daily",
                   feeds_only: bool = False, backfill: bool | None = None, limit: int | None = None,
                   translate: bool = True, workers: int = 8, budget_minutes: float | None = None,
                   dry_run: bool = False) -> dict:
    lex = Lexicon(load_lexicon())
    coverage = load_coverage()
    seen = load_seen()
    started = now_utc()
    started_msk = started.astimezone(MSK)
    budget = Budget(budget_minutes)
    summary = {"at": iso_utc(started), "mode": mode, "lexicon": lex.fingerprint(), "outlets": {}}
    translated: Counter = Counter()
    tr_lock = threading.Lock()  # one translation model, shared by the outlets' threads
    touched: dict[str, set[str]] = {}  # outlet → days whose files this run changed (some outside its range)

    def sink_for(o: Outlet):
        def sink(records: list[dict]):
            # Translation is skipped once the time budget is spent; `woland translate` fills gaps later.
            if translate and o.lang == "ru" and not budget.exceeded():
                with tr_lock:
                    translated[o.id] += translate_records(records)
            if dry_run:
                return
            by_day: dict[str, list] = {}
            moved: dict[str, set] = {}
            for r in records:
                was = r.pop("_was", None)  # a completed headline-only record that the page dates differently
                if was and was != r["p"][:10]:
                    moved.setdefault(was, set()).add(r["u"])
                by_day.setdefault(r["p"][:10], []).append(r)
            for key, recs in by_day.items():
                merge_day(date.fromisoformat(key), o.id, recs)
            for key, gone in moved.items():
                drop_urls(date.fromisoformat(key), o.id, gone)
            touched.setdefault(o.id, set()).update(by_day, moved)
        return sink

    def job(o):
        start, end = ranges[o.id]
        # Every article ever stored counts as known: sites re-date evergreen pages ("when the heating comes
        # on"), and one URL is filed once, under the day it first appeared. The last weeks' records say
        # besides which of them are headline only (to be completed) and where they are filed.
        known = known_urls(o.id, max(START_DATE, start - timedelta(days=KNOWN_DAYS)), end + timedelta(days=1))
        retry = headline_only(o.id, start, end) if o.fetch and not feeds_only else []
        # Backfill-only sources (the Internet Archive, deep feed pages, full sitemaps) are read only
        # when the range reaches back beyond the rolling window.
        deep = backfill if backfill is not None else (start < today_msk() - timedelta(days=WINDOW + 1))
        return collect_outlet(o, start, end, lex, known, seen.get(o.id, {}), feeds_only=feeds_only,
                              backfill=deep, limit=limit, budget=Budget(o.budget, within=budget),
                              sink=sink_for(o), retry=retry)

    active = [o for o in outlets if o.id in ranges]
    # what this run changed, per outlet: other runs (the hourly feeds beside a long backfill, say) may be
    # changing the rest of the state files at the same time
    owned_days: dict[str, set[str]] = {}
    owned_urls: dict[str, set[str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(job, o): o for o in active}
        for fut in as_completed(futures):
            o = futures[fut]
            try:
                run = fut.result()
            except Exception as exc:  # one outlet failing must not sink the run
                log.exception("%s failed", o.id)
                summary["outlets"][o.id] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
                continue
            seen.setdefault(o.id, {}).update(run.rejected)
            days = update_coverage(coverage.setdefault(o.id, {}), o, run, touched.get(o.id, set()), started_msk,
                                   gone=set(seen[o.id]), limit=limit, feeds_only=feeds_only, dry_run=dry_run)
            new = run.stats.get("stored", 0) - run.stats.get("upgraded", 0) + run.stats.get("listed", 0)
            summary["outlets"][o.id] = {
                "range": [run.start.isoformat(), run.end.isoformat()], "new": new,
                "translated": translated[o.id], "requests": run.requests, "seconds": run.seconds,
                "stats": dict(run.stats), "errors": run.errors[:5], "aborted": run.aborted,
            }
            log.info("%-10s done: %d new, %d requests, %.0fs%s%s", o.id, new, run.requests,
                     run.seconds, f", errors: {run.errors}" if run.errors else "",
                     f", aborted: {run.aborted}" if run.aborted else "")
            owned_days[o.id] = days
            owned_urls[o.id] = set(run.rejected)
            if not dry_run:  # persist progress as we go: a long run may be cut short
                save_coverage(coverage, only=owned_days)
                save_seen(seen, today_msk(), only=owned_urls)
    summary["seconds"] = round((now_utc() - started).total_seconds())
    if not dry_run:
        save_coverage(coverage, only=owned_days)
        save_seen(seen, today_msk(), only=owned_urls)
        append_run(summary)
    return summary


def update_coverage(cov: dict, o: Outlet, run: OutletRun, touched: set[str], started_msk: datetime, *,
                    gone: set[str] = frozenset(), limit=None, feeds_only=False, dry_run=False) -> set[str]:
    """Record what a run collected for an outlet: articles per day (the days of its range, and any other
    day it filed articles under), how many are headline only with a page still to read (`gone`: URLs
    whose pages have disappeared), and whether each day of the range is complete. Returns the days changed."""
    in_range = [d.isoformat() for d in daterange(run.start, run.end)]
    days = set(in_range) | touched
    at = iso_utc()
    for key in sorted(days):
        entry = cov.setdefault(key, {})
        if dry_run:
            entry.setdefault("n", 0)
        else:
            recs = read_day(date.fromisoformat(key), o.id)
            entry["n"] = len(recs)
            heads = sum(r.get("via") == "feed" and r["u"] not in gone for r in recs) if o.fetch else 0
            if heads:
                entry["h"] = heads  # the day is looked at again until their pages are read
            else:
                entry.pop("h", None)
        if key not in in_range:
            entry.setdefault("status", "partial" if o.can_backfill else "feed")
        entry["at"] = at
    # Pages that failed for passing reasons (network, "too many requests", 5xx) are retried by a later
    # run only if their days are not marked complete, so more than a few such failures keep them open.
    passing = sum(v for k, v in run.stats.items()
                  if k.startswith("fail_") and k not in ("fail_404", "fail_410", "fail_unparsable"))
    # Days holding headline-only records stay open too, so that their pages are tried again.
    clean_run = (not run.errors and not run.aborted and not limit and not feeds_only
                 and passing <= max(5, 0.01 * run.stats.get("to_fetch", 0))
                 and not run.stats.get("listed")
                 and run.stats.get("upgraded", 0) + run.stats.get("upgrade_gone", 0) >= run.stats.get("to_upgrade", 0))
    # the days around, this run's counts included (a backfill from the first day has no earlier ones)
    typical = typical_day(cov, run.start, through=run.end)
    for key in in_range:
        entry = cov[key]
        entry["found"] = max(entry.get("found", 0), run.found_by_day.get(key, 0))
        if key in run.published_by_day:
            entry["published"] = run.published_by_day[key]
        if not o.can_backfill:  # coverage limited to what the feed held at the time
            entry["status"] = "feed"
        elif entry.get("status") != "complete":
            # a day far quieter than usual has a hole in it (a listing that lags, say): keep it open
            thin = typical >= 20 and entry["n"] < 0.25 * typical
            complete = clean_run and not thin and _day_complete(date.fromisoformat(key), started_msk)
            entry["status"] = "complete" if complete else "partial"
    return days


def daily(outlets: list[Outlet] | None = None, catch_up_days: int = 45, **kw) -> dict:
    outlets = outlets or load_outlets()
    return run_collection(plan(outlets, load_coverage(), catch_up_days), outlets, mode="daily", **kw)


def last_feed_read() -> datetime | None:
    """When the latest run that read the feeds (a poll, or a nightly run) began."""
    starts = [parse_dt(r["at"]) for r in load_runs() if r.get("mode") in ("poll", "daily") and r.get("at")]
    return max(starts) if starts else None


def poll(outlets: list[Outlet] | None = None, min_gap: float | None = None, **kw) -> dict | None:
    """Read the feeds of outlets whose feeds only hold a few hours of news. With `min_gap`, do nothing if
    they were read less than that many minutes ago: GitHub starts scheduled jobs late or not at all, so
    the job is scheduled often and skips the turns it does not need."""
    if min_gap:
        last = last_feed_read()
        if last and now_utc() - last < timedelta(minutes=min_gap):
            return None
    outlets = [o for o in (outlets or load_outlets()) if o.poll]
    today = today_msk()
    ranges = {o.id: (today - timedelta(days=1), today) for o in outlets}
    return run_collection(ranges, outlets, mode="poll", feeds_only=True, backfill=False, **kw)


def backfill(start: date, end: date, outlets: list[Outlet] | None = None, **kw) -> dict:
    outlets = outlets or load_outlets()
    ranges = {o.id: (start, end) for o in outlets}
    return run_collection(ranges, outlets, mode="backfill", **kw)
