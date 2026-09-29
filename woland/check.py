"""Health check: can every outlet still be read? `python -m woland check`

For each outlet: discover one day's articles through its everyday sources, then read a few of them exactly
as the collector would (from the Internet Archive's copy when the outlet does not answer at all). For an
outlet read from its feeds only, it also tries what Woland does not use — an article page, robots.txt, the
sitemap — to see whether they still refuse. Prints a table (and a Markdown summary on GitHub Actions),
optionally keeps the results in a JSON file (data/state/check.json on GitHub), and returns a non-zero exit
code if an enabled outlet is broken.
"""
from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import Outlet, load_lexicon
from .discover import discover
from .lexicon import Lexicon
from .util import canonical_url, iso_utc, msk_day


@dataclass
class Health:
    outlet: Outlet
    found: int = 0          # article URLs discovered for the day
    on_day: int = 0         # … of which announced for that day
    read: int = 0           # sample articles read and parsed
    tried: int = 0
    archived: int = 0       # … of which read from the Internet Archive's copy (the outlet did not answer)
    sample: str = ""        # a headline, as proof of life
    problems: list = field(default_factory=list)
    probes: dict = field(default_factory=dict)  # feed-only outlets: how what Woland does not use answers

    @property
    def ok(self) -> bool:
        return self.found > 0 and (self.tried == 0 or self.read > 0)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "enabled": self.outlet.enabled, "found": self.found, "on_day": self.on_day,
                "read": self.read, "tried": self.tried, "archived": self.archived, "sample": self.sample,
                "problems": self.problems[:5], "probes": self.probes}


def _status(r) -> str:
    if r.ok:
        return "bot check" if r.challenged() else "200"
    return str(r.status) if r.status else (r.error or "no answer")[:80]


def check_outlet(o: Outlet, day: date, lex: Lexicon, n: int = 2) -> Health:
    from .collect import _fetch_page, build_record
    from .extract import extract
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
    local = threading.local()
    for c in arts[:n]:
        c.url = canonical_url(c.url)
        info = None
        if o.fetch:
            h.tried += 1
            info, fail, status, error = _fetch_page(o, c, [], local)
            if not info:
                h.problems.append(f"article page: {fail}: {status or error or ''}"[:200])
                continue
            h.archived += bool(info.get("capture"))
        built = build_record(o, c, info)
        if not built:
            h.problems.append("no headline or date")
            continue
        if o.fetch:
            h.read += 1
        h.sample = h.sample or built[0]["t"]
    if not o.fetch:
        if arts:
            h.probes["page"] = _status(f.get(canonical_url(arts[0].url)))
        h.probes["robots.txt"] = _status(f.get(f"{o.home}/robots.txt", check_robots=False))
        h.probes["sitemap"] = _status(f.get(f"{o.home}/sitemap.xml"))
    if not h.found and not h.problems:
        h.problems.append("no articles found for the day")
    return h


def run(outlets: list[Outlet], day: date) -> list[Health]:
    lex = Lexicon(load_lexicon())
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(lambda o: check_outlet(o, day, lex), outlets))


def _pages(h: Health) -> str:
    if not h.tried:
        return "feed"
    return f"{h.read}/{h.tried}" + (" (Archive)" if h.archived else "")


def _probes(h: Health) -> str:
    return " · ".join(f"{k} {v}" for k, v in h.probes.items())


def report(results: list[Health], day: date) -> str:
    lines = [f"Outlet health for {day} (articles discovered · announced for that day · sample pages read)", ""]
    for h in results:
        state = "ok " if h.ok else ("off" if not h.outlet.enabled else "BAD")
        lines.append(f"  {state} {h.outlet.id:11} {h.found:5} {h.on_day:5}  {_pages(h):13}  {h.sample[:70]}")
        if h.probes:
            lines.append(f"        · not used: {_probes(h)}")
        for p in h.problems[:3]:
            lines.append(f"        ! {p}")
    return "\n".join(lines)


def markdown(results: list[Health], day: date) -> str:
    rows = ["| | Outlet | Found | That day | Pages read | Sample headline / problems |", "|---|---|---:|---:|---|---|"]
    for h in results:
        mark = "✅" if h.ok else ("⏸️" if not h.outlet.enabled else "❌")
        text = h.sample[:80] if h.ok else "; ".join(h.problems[:2])[:160]
        if h.probes:
            text += f" (not used: {_probes(h)})"
        rows.append(f"| {mark} | {h.outlet.name} | {h.found} | {h.on_day} | {_pages(h)} | {text.replace('|', '/')} |")
    return f"### Outlet health, {day}\n\n" + "\n".join(rows) + "\n"


def save(results: list[Health], day: date, path: str) -> None:
    """Keep the results per outlet, over those of earlier checks (a check of a few outlets leaves the
    others' last results in place)."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    at = iso_utc()
    where = "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") else "elsewhere"
    for h in results:
        data[h.outlet.id] = {"at": at, "day": day.isoformat(), "from": where, **h.as_dict()}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                 newline="\n")


def main(outlets: list[Outlet], day: date, json_path: str | None = None) -> int:
    results = run(outlets, day)
    print(report(results, day))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(markdown(results, day))
    if json_path:
        save(results, day, json_path)
    broken = [h.outlet.id for h in results if h.outlet.enabled and not h.ok]
    if broken:
        print(f"\nbroken: {', '.join(broken)}")
    return 1 if broken else 0
