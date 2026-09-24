"""Collecting: discover → fetch → extract → tag → translate → store."""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .config import START_DATE, Outlet, load_lexicon, load_outlets
from .discover import Candidate, discover, parse_sitemap
from .extract import clean_lead, clean_title, extract, published_from_url
from .lexicon import Lexicon
from .store import (append_run, known_urls, load_coverage, load_seen, merge_day, read_day, save_coverage,
                    save_seen)
from .translate import get_translator
from .util import (MSK, canonical_url, fingerprint, iso_msk, iso_utc, msk_day, now_utc, short_hash, today_msk,
                   truncate)

log = logging.getLogger("woland.collect")

BODY_FAMILIES = ("framing",)  # topics are matched on headline and lead only
RATE_LIMIT_WAITS = (15, 60)   # seconds to wait before retrying a page refused as "too many requests"


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
    def __init__(self, minutes: float | None):
        self.deadline = time.monotonic() + minutes * 60 if minutes else None

    def exceeded(self) -> bool:
        return self.deadline is not None and time.monotonic() > self.deadline


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
    lead = _dedupe_lead(title, lead)
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
    r = local.fetcher.get(c.url)
    for wait in RATE_LIMIT_WAITS:  # DDoS shields (Qrator, …) answer bursts with 401/429/503: slow down
        if r.status not in (401, 429, 503):
            break
        time.sleep(wait)
        r = local.fetcher.get(c.url)
    if not r.ok or r.challenged():
        return None, ("bot-check" if r.ok else (str(r.status) if r.status else "network")), r.status, r.error
    info = extract(r.text, c.url, o.headline)
    return (info, None, r.status, None) if info else (None, "unparsable", r.status, None)


def collect_outlet(o: Outlet, start: date, end: date, lex: Lexicon, known: set, rejected_before: dict, *,
                   feeds_only: bool = False, backfill: bool = False, limit: int | None = None,
                   budget: Budget | None = None, sink=None, flush_every: int = 300) -> OutletRun:
    """Discover and read one outlet's articles for [start, end].

    Records go to `sink` in batches as they are read (so an interrupted run keeps its work), or, without
    a sink, to run.records. An article that turns out to belong to another day of the chronicle is kept
    too: its page has been read already, and it may be the only chance to catch it."""
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
    todo, urls = [], set()
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
            run.stats["known"] += 1
        elif c.url in rejected_before:
            run.stats["skipped"] += 1
        else:
            todo.append(c)
    def priority(c):  # announced inside the range first, newest first; margin candidates last
        inside = c.hint is not None and start <= msk_day(c.hint) <= end
        return (not inside, -(c.hint.timestamp() if c.hint else 0))
    todo.sort(key=priority)
    if limit:
        todo = todo[:limit]
    run.stats["to_fetch"] = len(todo)
    log.info("%-10s %s..%s: %d candidates, %d new", o.id, start, end, len(urls), len(todo))

    ok = failed = 0
    step = o.parallel * 8
    for i in range(0, len(todo), step):
        if budget.exceeded():
            run.aborted = "time budget exhausted"
            break
        chunk = todo[i:i + step]
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
                if fail != "unparsable":
                    failed += 1
                continue
            ok += 1
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
            keep(rec)
            run.stats["stored"] += 1
        if ok == 0 and failed >= 15:  # nothing but failures: the site is blocking us or down
            run.aborted = f"unreachable ({', '.join(k[5:] for k in run.stats if k.startswith('fail_'))})"
            break
        if (i // step) % 20 == 19:
            log.info("%-10s %d/%d fetched", o.id, min(i + step, len(todo)), len(todo))
    if sink and pending:
        sink(pending[:])

    if o.coverage_sitemap and not feeds_only:
        r = fetcher.get(o.coverage_sitemap)
        if r.ok:
            _, entries = parse_sitemap(r.text)
            counts = Counter()
            for e in entries:
                from .util import parse_dt
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


# Every night the last WINDOW + 1 days are looked at again. Discovery is cheap (articles already stored
# are skipped), and several sources only list an article a day or two after it appeared.
WINDOW = 6


def plan(outlets: list[Outlet], coverage: dict, catch_up_days: int, window: int = WINDOW) -> dict[str, tuple[date, date]]:
    """Date range per outlet: the rolling window plus the oldest day that is not yet complete."""
    today = today_msk()
    oldest = max(START_DATE, today - timedelta(days=catch_up_days))
    ranges = {}
    for o in outlets:
        start = today - timedelta(days=window)
        if o.can_backfill:
            cov = coverage.get(o.id, {})
            d = oldest
            while d < start:
                if cov.get(d.isoformat(), {}).get("status") != "complete":
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

    def sink_for(o: Outlet):
        def sink(records: list[dict]):
            # Translation is skipped once the time budget is spent; `woland translate` fills gaps later.
            if translate and o.lang == "ru" and not budget.exceeded():
                with tr_lock:
                    translated[o.id] += translate_records(records)
            if dry_run:
                return
            by_day: dict[str, list] = {}
            for r in records:
                by_day.setdefault(r["p"][:10], []).append(r)
            for key, recs in by_day.items():
                merge_day(date.fromisoformat(key), o.id, recs)
        return sink

    def job(o):
        start, end = ranges[o.id]
        known = known_urls(o.id, start - timedelta(days=3), end + timedelta(days=1))
        # Backfill-only sources (the Internet Archive, deep feed pages, full sitemaps) are read only
        # when the range reaches back beyond the rolling window.
        deep = backfill if backfill is not None else (start < today_msk() - timedelta(days=WINDOW + 1))
        return collect_outlet(o, start, end, lex, known, seen.get(o.id, {}), feeds_only=feeds_only,
                              backfill=deep, limit=limit, budget=budget, sink=sink_for(o))

    active = [o for o in outlets if o.id in ranges]
    done: set[str] = set()  # outlets whose state this run has updated (other runs may update the rest)
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
            cov = coverage.setdefault(o.id, {})
            d = run.start
            while d <= run.end:
                key = d.isoformat()
                entry = cov.setdefault(key, {})
                entry["n"] = len(read_day(d, o.id)) if not dry_run else entry.get("n", 0)
                entry["found"] = max(entry.get("found", 0), run.found_by_day.get(key, 0))
                if key in run.published_by_day:
                    entry["published"] = run.published_by_day[key]
                if not o.can_backfill:  # coverage limited to what the feed held at the time
                    entry["status"] = "feed"
                elif entry.get("status") != "complete":
                    clean_run = not run.errors and not run.aborted and not limit and not feeds_only
                    entry["status"] = "complete" if clean_run and _day_complete(d, started_msk) else "partial"
                entry["at"] = iso_utc()
                d += timedelta(days=1)
            seen.setdefault(o.id, {}).update(run.rejected)
            new = run.stats.get("stored", 0)
            summary["outlets"][o.id] = {
                "range": [run.start.isoformat(), run.end.isoformat()], "new": new,
                "translated": translated[o.id], "requests": run.requests, "seconds": run.seconds,
                "stats": dict(run.stats), "errors": run.errors[:5], "aborted": run.aborted,
            }
            log.info("%-10s done: %d new, %d requests, %.0fs%s%s", o.id, new, run.requests,
                     run.seconds, f", errors: {run.errors}" if run.errors else "",
                     f", aborted: {run.aborted}" if run.aborted else "")
            done.add(o.id)
            if not dry_run:  # persist progress as we go: a long run may be cut short
                save_coverage(coverage, only=done)
                save_seen(seen, today_msk(), only=done)
    summary["seconds"] = round((now_utc() - started).total_seconds())
    if not dry_run:
        save_coverage(coverage, only=done)
        save_seen(seen, today_msk(), only=done)
        append_run(summary)
    return summary


def daily(outlets: list[Outlet] | None = None, catch_up_days: int = 45, **kw) -> dict:
    outlets = outlets or load_outlets()
    return run_collection(plan(outlets, load_coverage(), catch_up_days), outlets, mode="daily", **kw)


def poll(outlets: list[Outlet] | None = None, **kw) -> dict:
    """Hourly: read the feeds of outlets whose feeds only hold a few hours of news."""
    outlets = [o for o in (outlets or load_outlets()) if o.poll]
    today = today_msk()
    ranges = {o.id: (today - timedelta(days=1), today) for o in outlets}
    return run_collection(ranges, outlets, mode="poll", feeds_only=True, backfill=False, **kw)


def backfill(start: date, end: date, outlets: list[Outlet] | None = None, **kw) -> dict:
    outlets = outlets or load_outlets()
    ranges = {o.id: (start, end) for o in outlets}
    return run_collection(ranges, outlets, mode="backfill", **kw)
