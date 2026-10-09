"""Command line: python -m woland <command>

  collect   daily collection (rolling window + automatic catch-up back to the start date)
  poll      hourly read of short-lived feeds (TASS, Gazeta.ru, Zvezda, Kremlin)
  backfill  collect an explicit date range
  translate add missing English translations (headlines, leads, snippets of body matches)
  build     build the static website into _site/
  probe     try one outlet on one day and print what Woland would store
  check     can every outlet still be read? (discovery + a few article pages per outlet)
  mtcheck   what the translation glossary (config/glossary.yaml) corrects, and what it still misses
  reindex   rebuild the index of every URL stored (data/state/urls/) from the day files
  sample    a random sample of the articles counted under a framing, to read by hand (docs/lexicon-audit.md)
  merge     git's merge driver for the data files (see woland/merge.py and .gitattributes)
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
    p.add_argument("--min-gap", type=float, help="do nothing if the feeds were read less than this many minutes ago")
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
    p = sub.add_parser("check")
    p.add_argument("--outlets", help="comma-separated outlet ids (default: all, including disabled ones)")
    p.add_argument("--date", type=date.fromisoformat, help="day to look at (default: yesterday)")
    p.add_argument("--json", help="also keep the results, per outlet, in this file (data/state/check.json)")
    p = sub.add_parser("mtcheck")
    p.add_argument("--days", type=int, help="only the last N days (default: the whole archive)")
    p = sub.add_parser("reindex")
    p.add_argument("--outlets", help="comma-separated outlet ids (default: all, including disabled ones)")
    p = sub.add_parser("sample")
    p.add_argument("framing", help="a framing's (or topic's) id in config/lexicon.yaml")
    p.add_argument("-n", type=int, default=25, help="how many articles to draw")
    p.add_argument("--seed", type=int, default=1, help="a new seed draws a fresh sample")
    p.add_argument("--round", default="", help="written into the round column")
    p.add_argument("--csv", help="write the rows (the columns of docs/lexicon-audit-sample.csv) to this file")
    p = sub.add_parser("merge")
    for name in ("base", "ours", "theirs", "path"):  # git's %O %A %B %P
        p.add_argument(name)

    a = ap.parse_args(argv)
    if a.cmd == "merge":
        from .merge import main as merge_main
        return merge_main(a.base, a.ours, a.theirs, a.path)
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows, when the output is piped
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for noisy in ("urllib3", "trafilatura", "htmldate", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.ERROR)  # "discarding data" on every non-article page

    if a.cmd in ("collect", "poll", "backfill"):
        from . import collect
        kw = dict(limit=a.limit, translate=not a.no_translate, workers=a.workers,
                  budget_minutes=a.budget, dry_run=a.dry_run)
        outlets = _outlets(a.outlets)
        if a.cmd == "collect":
            summary = collect.daily(outlets, catch_up_days=a.catch_up, **kw)
        elif a.cmd == "poll":
            summary = collect.poll(outlets, min_gap=a.min_gap, **kw)
            if summary is None:
                print(f"poll: the feeds were read less than {a.min_gap:g} minutes ago; nothing to do")
                return 0
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
                    print(f"time budget spent; added missing translations to {n} files")
                    return 0
                recs = read_day(d, o.id)
                if recs and translate_records(recs):
                    merge_day(d, o.id, recs)
                    n += 1
        print(f"added missing translations to {n} files")
        return 0

    if a.cmd == "build":
        from .build import build
        build(out_dir=a.out, base_url=a.base_url)
        return 0

    if a.cmd == "check":
        from .check import main as check_main
        return check_main(_outlets(a.outlets, include_disabled=True), a.date or today_msk() - timedelta(days=1),
                          a.json)

    if a.cmd == "sample":
        from .audit import main as sample_main
        return sample_main(a.framing, a.n, a.seed, a.round, a.csv)

    if a.cmd == "reindex":
        from .store import rebuild_url_index
        for o in _outlets(a.outlets, include_disabled=True):
            print(f"  {o.id:11} {len(rebuild_url_index(o.id)):7} URLs")
        return 0

    if a.cmd == "mtcheck":
        from .glossary import report
        from .store import available_days, outlets_on, read_day
        days = available_days()
        if a.days:
            days = days[-a.days:]
        ru = {o.id for o in load_outlets(include_disabled=True) if o.lang == "ru"}
        print(report(r for d in days for o in outlets_on(d) if o in ru for r in read_day(d, o)))
        return 0

    if a.cmd == "probe":
        from .collect import build_record
        from .config import load_lexicon
        from .discover import discover
        from .extract import extract
        from .lexicon import Lexicon
        o = _outlets(a.outlet, include_disabled=True)[0]
        day = a.date or today_msk() - timedelta(days=1)
        f = o.fetcher()
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
                info = extract(r.text, c.url, o.headline)
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
