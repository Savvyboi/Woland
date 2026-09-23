"""Command line: python -m woland <command>

  collect   daily collection (rolling window + automatic catch-up back to the start date)
  poll      hourly read of short-lived feeds (TASS, Gazeta.ru, Zvezda, Kremlin)
  backfill  collect an explicit date range
  translate add missing English headline translations
  build     build the static website into _site/
  probe     try one outlet on one day and print what Woland would store
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

from .config import load_outlets
from .util import today_msk


def _outlets(arg: str | None, include_disabled: bool = False):
    outlets = load_outlets(include_disabled=include_disabled)
    if not arg:
        return outlets
    wanted = [a.strip() for a in arg.split(",") if a.strip()]
    unknown = set(wanted) - {o.id for o in outlets}
    if unknown:
        sys.exit(f"unknown outlet(s): {', '.join(sorted(unknown))}")
    return [o for o in outlets if o.id in wanted]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="woland", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--outlets", help="comma-separated outlet ids (default: all enabled)")
        p.add_argument("--limit", type=int, help="at most N new articles per outlet (testing)")
        p.add_argument("--no-translate", action="store_true")
        p.add_argument("--workers", type=int, default=24, help="outlets processed at the same time")
        p.add_argument("--budget", type=float, help="stop fetching after this many minutes")
        p.add_argument("--dry-run", action="store_true", help="do not write anything")

    p = sub.add_parser("collect")
    common(p)
    p.add_argument("--catch-up", type=int, default=45, help="how many days back to repair gaps")
    p = sub.add_parser("poll")
    common(p)
    p = sub.add_parser("backfill")
    common(p)
    p.add_argument("start", type=date.fromisoformat)
    p.add_argument("end", type=date.fromisoformat, nargs="?")
    p.add_argument("--wayback", action="store_true", help="also ask the Internet Archive for URLs")
    p = sub.add_parser("translate")
    p.add_argument("--days", type=int, default=7, help="look this many days back for missing translations")
    p.add_argument("--budget", type=float, help="stop after this many minutes")
    p = sub.add_parser("build")
    p.add_argument("--out", default="_site")
    p.add_argument("--base-url", default="", help="public URL of the site, for citations")
    p = sub.add_parser("probe")
    p.add_argument("outlet")
    p.add_argument("--date", type=date.fromisoformat)
    p.add_argument("-n", type=int, default=3)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for noisy in ("urllib3", "trafilatura", "htmldate", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if a.cmd in ("collect", "poll", "backfill"):
        from . import collect
        kw = dict(limit=a.limit, translate=not a.no_translate, workers=a.workers,
                  budget_minutes=a.budget, dry_run=a.dry_run)
        outlets = _outlets(a.outlets)
        if a.cmd == "collect":
            summary = collect.daily(outlets, catch_up_days=a.catch_up, **kw)
        elif a.cmd == "poll":
            summary = collect.poll(outlets, **kw)
        else:
            summary = collect.backfill(a.start, a.end or a.start, outlets,
                                       backfill=True if a.wayback else None, **kw)
        new = sum(v.get("new", 0) for v in summary["outlets"].values())
        print(f"{a.cmd}: {new} new articles in {summary['seconds']}s")
        for oid, v in sorted(summary["outlets"].items()):
            flag = " ⚠ " + (v.get("aborted") or "; ".join(v.get("errors", [])) or v.get("error", "")) \
                if (v.get("errors") or v.get("aborted") or v.get("error")) else ""
            print(f"  {oid:11} {v.get('new', 0):6} new{flag}")
        return 0

    if a.cmd == "translate":
        from .collect import Budget, translate_records
        from .store import merge_day, read_day
        budget = Budget(a.budget)
        today = today_msk()
        n = 0
        ru = [o for o in load_outlets() if o.lang == "ru"]
        for i in range(a.days):  # newest days first
            d = today - timedelta(days=i)
            for o in ru:
                if budget.exceeded():
                    print(f"time budget spent; translated headlines in {n} files")
                    return 0
                recs = read_day(d, o.id)
                if recs and translate_records(recs):
                    merge_day(d, o.id, recs)
                    n += 1
        print(f"translated missing headlines in {n} files")
        return 0

    if a.cmd == "build":
        from .build import build
        build(out_dir=a.out, base_url=a.base_url)
        return 0

    if a.cmd == "probe":
        from .collect import build_record
        from .config import load_lexicon
        from .discover import discover
        from .extract import extract
        from .lexicon import Lexicon
        from .net import Fetcher
        o = _outlets(a.outlet, include_disabled=True)[0]
        day = a.date or today_msk() - timedelta(days=1)
        f = Fetcher(gap=o.rate)
        cands, errors = discover(f, o, day, day)
        arts = [c for c in cands if o.is_article(c.url)]
        print(f"{o.id}: {len(cands)} candidates, {len(arts)} look like articles; errors: {errors or 'none'}")
        lex = Lexicon(load_lexicon())
        for c in arts[: a.n]:
            info = None
            if o.fetch:
                r = f.get(c.url)
                print(f"\n{c.url}\n  HTTP {r.status} {len(r.content)} bytes{' (bot check!)' if r.challenged() else ''}")
                if not r.ok:
                    continue
                info = extract(r.text, c.url)
            built = build_record(o, c, info)
            if not built:
                print("  (incomplete)")
                continue
            rec, body = built
            head, kb = lex.tag(rec["t"], rec.get("d", ""), body, o.lang)
            rec["head"] = sorted(head)
            rec["kb"] = kb
            print(json.dumps(rec, ensure_ascii=False, indent=1))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
