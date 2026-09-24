"""Health check: can every outlet still be read? `python -m woland check`

For each outlet: discover one day's articles through its everyday sources, then read a few of
them exactly as the collector would. Prints a table (and a Markdown summary on GitHub Actions)
and returns a non-zero exit code if an enabled outlet is broken.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date

from .config import Outlet, load_lexicon
from .discover import discover
from .extract import extract
from .lexicon import Lexicon
from .util import canonical_url, msk_day


@dataclass
class Health:
    outlet: Outlet
    found: int = 0          # article URLs discovered for the day
    on_day: int = 0         # … of which announced for that day
    read: int = 0           # sample articles read and parsed
    tried: int = 0
    sample: str = ""        # a headline, as proof of life
    problems: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.found > 0 and (self.tried == 0 or self.read > 0)


def check_outlet(o: Outlet, day: date, lex: Lexicon, n: int = 2) -> Health:
    from .collect import build_record
    h = Health(o)
    f = o.fetcher()
    try:
        cands, errors = discover(f, o, day, day)
    except Exception as exc:  # the check must report, not crash
        h.problems.append(f"discovery crashed: {type(exc).__name__}: {exc}"[:200])
        return h
    h.problems += [e[:200] for e in errors]
    arts = [c for c in cands if o.is_article(canonical_url(c.url))]
    h.found = len(arts)
    h.on_day = sum(1 for c in arts if c.hint and msk_day(c.hint) == day)
    arts.sort(key=lambda c: (c.hint is None or msk_day(c.hint) != day, c.url))
    for c in arts[:n]:
        info = None
        if o.fetch:
            h.tried += 1
            r = f.get(canonical_url(c.url))
            if not r.ok or r.challenged():
                h.problems.append(f"article page: {'bot check' if r.ok else (r.status or r.error)}"[:200])
                continue
            info = extract(r.text, c.url, o.headline)
            if not info:
                h.problems.append("article page could not be parsed")
                continue
        built = build_record(o, c, info)
        if not built:
            h.problems.append("no headline or date")
            continue
        if o.fetch:
            h.read += 1
        h.sample = h.sample or built[0]["t"]
    if not h.found and not h.problems:
        h.problems.append("no articles found for the day")
    return h


def run(outlets: list[Outlet], day: date) -> list[Health]:
    lex = Lexicon(load_lexicon())
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(lambda o: check_outlet(o, day, lex), outlets))


def report(results: list[Health], day: date) -> str:
    lines = [f"Outlet health for {day} (articles discovered · announced for that day · sample pages read)", ""]
    for h in results:
        state = "ok " if h.ok else ("off" if not h.outlet.enabled else "BAD")
        pages = f"{h.read}/{h.tried}" if h.tried else "feed"
        lines.append(f"  {state} {h.outlet.id:11} {h.found:5} {h.on_day:5}  {pages:5}  {h.sample[:70]}")
        for p in h.problems[:3]:
            lines.append(f"        ! {p}")
    return "\n".join(lines)


def markdown(results: list[Health], day: date) -> str:
    rows = ["| | Outlet | Found | That day | Pages read | Sample headline / problems |", "|---|---|---:|---:|---|---|"]
    for h in results:
        mark = "✅" if h.ok else ("⏸️" if not h.outlet.enabled else "❌")
        pages = f"{h.read}/{h.tried}" if h.tried else "feed"
        text = h.sample[:80] if h.ok else "; ".join(h.problems[:2])[:160]
        rows.append(f"| {mark} | {h.outlet.name} | {h.found} | {h.on_day} | {pages} | {text.replace('|', '/')} |")
    return f"### Outlet health, {day}\n\n" + "\n".join(rows) + "\n"


def main(outlets: list[Outlet], day: date) -> int:
    results = run(outlets, day)
    print(report(results, day))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(markdown(results, day))
    broken = [h.outlet.id for h in results if h.outlet.enabled and not h.ok]
    if broken:
        print(f"\nbroken: {', '.join(broken)}")
    return 1 if broken else 0
