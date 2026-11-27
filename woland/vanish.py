"""Articles the outlets took down after publishing: a nightly re-check of a capped sample of the last week's pages.

    python -m woland recheck [--outlets tass,ria] [--sample 100] [--budget 40]

Each night, for every outlet whose pages Woland reads, up to SAMPLE articles filed under the last DAYS Moscow
days are asked for again, one request each, with the outlet's usual pause between requests and robots.txt
obeyed. Only articles once read from their own page are asked for (not headline-only records, whose URL
may never have worked, nor pages read from the Internet Archive because the site refused them).

A page that answers 404 or 410 is put on a list of pending ones (data/state/gone.json) and asked for again the
next night, first of all; if it answers 404 or 410 again, its record gets "va" (the time it was first found
missing, UTC) and "vs" (the status), and it is not asked for again. A page that answers anything else in
between is taken off the list: one missing answer may be a passing fault of the site. A page the site moves
to its home page, or replaces with a page saying it is gone but answering 200, is not seen as gone.

An outlet is left alone for the rest of the night once it asks Woland to slow down even after the pause
net.Fetcher keeps, refuses three pages in a row, or stops answering.
"""
from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from .config import Outlet
from .store import load_gone, read_day, save_gone, write_day
from .util import iso_utc, today_msk

log = logging.getLogger("woland.vanish")

SAMPLE = 100        # pages asked for per outlet and night (pending ones first)
DAYS = 7            # how far back articles are sampled, in Moscow days before today
GONE = (404, 410)
PENDING_DAYS = 3    # a pending page not asked for again within this many days is dropped (no "consecutive")
REFUSED_LIMIT = 3   # refusals in a row that end an outlet's night


def eligible(rec: dict) -> bool:
    """A record whose page Woland once read from the site itself, and not yet found gone."""
    return rec.get("via") == "page" and not rec.get("ar") and "va" not in rec


def candidates(outlet: str, today: date, days: int = DAYS) -> dict[str, str]:
    """URL → the day it is filed under, for the outlet's eligible records of the `days` days before today."""
    out = {}
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        for rec in read_day(d, outlet):
            if eligible(rec):
                out[rec["u"]] = d.isoformat()
    return out


def pick(cands: dict[str, str], pending: dict[str, dict], n: int, seed: str) -> list[tuple[str, str]]:
    """(url, day) to ask for: the pending ones first, then a random draw (the same for the same seed)."""
    first = [(u, e["d"]) for u, e in sorted(pending.items(), key=lambda kv: kv[1]["at"])]
    taken = {u for u, _ in first}
    rest = sorted(u for u in cands if u not in taken)
    rng = random.Random(seed)
    draw = rng.sample(rest, min(len(rest), max(0, n - len(first))))
    return (first + [(u, cands[u]) for u in draw])[:max(n, len(first))]


def check_outlet(o: Outlet, today: date, pending: dict[str, dict], *, sample: int = SAMPLE, budget=None,
                 fetcher=None, now=iso_utc) -> dict:
    """Ask for a sample of the outlet's pages. Updates `pending` in place; returns the run's tallies and the
    pages confirmed gone ({"gone": [{"u", "d", "at", "s"}], ...})."""
    from . import net
    fetcher = fetcher or o.fetcher()
    cutoff = (today - timedelta(days=PENDING_DAYS)).isoformat()
    for u in [u for u, e in pending.items() if e["at"][:10] < cutoff]:
        del pending[u]  # not asked for again in time: its next answer would not follow the first
    todo = pick(candidates(o.id, today), pending, sample, f"{o.id}:{today.isoformat()}")
    out = {"asked": 0, "ok": 0, "missing": 0, "gone": [], "stopped": ""}
    refused = 0
    for url, day in todo:
        if budget is not None and budget.exceeded():
            out["stopped"] = "time budget exhausted"
            break
        if net.HEALTH.down(o.host):
            out["stopped"] = "the site stopped answering"
            break
        r = fetcher.get(url)
        if r.status is None:  # disallowed by robots.txt, or no answer: no check either way
            continue
        out["asked"] += 1
        if r.slow_down():
            out["stopped"] = "the site asked to slow down"
            break
        if r.status in (401, 403):
            refused += 1
            if refused >= REFUSED_LIMIT:
                out["stopped"] = "the site refused its pages"
                break
            continue
        refused = 0
        if r.status in GONE:
            first = pending.pop(url, None)
            if first:  # missing twice in a row
                out["gone"].append({"u": url, "d": first["d"], "at": first["at"], "s": r.status})
            else:
                pending[url] = {"at": now(), "s": r.status, "d": day}
                out["missing"] += 1
        elif r.status < 500:
            pending.pop(url, None)
            out["ok"] += 1
        # 5xx: the site's fault for now; a pending page stays pending
    return out


def mark_gone(outlet: str, gone: list[dict]) -> int:
    """Write "va" and "vs" into the records of the pages confirmed gone. Returns how many were marked."""
    by_day: dict[str, dict[str, dict]] = {}
    for g in gone:
        by_day.setdefault(g["d"], {})[g["u"]] = g
    n = 0
    for key, found in by_day.items():
        d = date.fromisoformat(key)
        records = read_day(d, outlet)
        changed = False
        for rec in records:
            g = found.get(rec["u"])
            if g and "va" not in rec:
                rec["va"], rec["vs"] = g["at"], g["s"]
                changed = True
                n += 1
        if changed:
            write_day(d, outlet, records)
    return n


def recheck(outlets: list[Outlet], *, sample: int = SAMPLE, budget_minutes: float | None = None,
            workers: int = 24, dry_run: bool = False) -> dict:
    """The night's re-check, for the outlets whose pages Woland reads. Returns per outlet what it found."""
    from .collect import Budget
    budget = Budget(budget_minutes)
    today = today_msk()
    state = load_gone()
    active = [o for o in outlets if o.fetch]
    summary: dict[str, dict] = {}
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(check_outlet, o, today, state.setdefault(o.id, {}), sample=sample,
                             budget=Budget(None, within=budget)): o for o in active}
        for fut in as_completed(futures):
            o = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # one outlet failing must not sink the rest
                log.exception("%s failed", o.id)
                summary[o.id] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
                continue
            marked = 0 if dry_run else mark_gone(o.id, res["gone"])
            summary[o.id] = {"asked": res["asked"], "ok": res["ok"], "missing": res["missing"],
                             "gone": marked if not dry_run else len(res["gone"]),
                             "pending": len(state.get(o.id, {})), "stopped": res["stopped"]}
            log.info("%-10s %d asked, %d missing once, %d gone%s", o.id, res["asked"], res["missing"],
                     len(res["gone"]), f" ({res['stopped']})" if res["stopped"] else "")
    if not dry_run:
        save_gone(state)
    return {"seconds": round(time.monotonic() - t0), "outlets": summary}
