"""How big the built site is, against what GitHub Pages publishes: python -m woland budget _site

GitHub Pages refuses a site over 1 GB. The search index of each month (data/search/<month>/: documents,
word shards, framing postings) is most of the site, about 100 MB a month in autumn 2026, and the build keeps
WOLAND_SEARCH_MONTHS of them (18 by default), so the site grows by a month's index until that many months are
kept. This prints the size of every part of the site, and how many more months fit; above `warn` MB it warns
(a GitHub Actions annotation), above `fail` MB it fails, before Pages would.
"""
from __future__ import annotations

import os
from pathlib import Path

MB = 1_000_000
WARN_MB = 700
FAIL_MB = 920
PAGES_LIMIT_MB = 1000


def tree_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def parts(site: Path) -> list[tuple[str, int]]:
    """(part, bytes): each search month, the rest of data/ by folder, and the site's other folders and pages."""
    out = []
    search = site / "data" / "search"
    for month in sorted(p for p in search.iterdir() if p.is_dir()) if search.is_dir() else []:
        out.append((f"data/search/{month.name}", tree_size(month)))
    data = site / "data"
    for p in sorted(data.iterdir()) if data.is_dir() else []:
        if p.name != "search":
            out.append((f"data/{p.name}", tree_size(p)))
    for p in sorted(site.iterdir()):
        if p.name != "data":
            out.append((p.name, tree_size(p)))
    return out


def report(site: Path, warn_mb: float = WARN_MB, fail_mb: float = FAIL_MB) -> tuple[str, str]:
    """A Markdown table of the site's size, and the verdict: "ok", "warn" or "fail"."""
    rows = parts(site)
    total = sum(n for _, n in rows)
    months = [n for name, n in rows if name.startswith("data/search/")]
    keep = int(os.environ.get("WOLAND_SEARCH_MONTHS", "18"))
    lines = ["| Part | MB | Share |", "|---|---:|---:|"]
    for name, n in sorted(rows, key=lambda r: -r[1]):
        if n >= MB / 10 or name.startswith("data/search/"):
            lines.append(f"| `{name}` | {n / MB:,.1f} | {n / total:.0%} |" if total else f"| `{name}` | 0 | – |")
    lines.append(f"| **total** | **{total / MB:,.1f}** | |")
    verdict = "fail" if total > fail_mb * MB else "warn" if total > warn_mb * MB else "ok"
    note = f"Site: {total / MB:,.0f} MB of the {PAGES_LIMIT_MB:,} MB GitHub Pages publishes (warning above {warn_mb:g}, failure above {fail_mb:g})."
    if months:
        per = sum(months[-3:]) / len(months[-3:])
        room = (fail_mb * MB - total) / per if per else 0
        note += (f" A month's search index is about {per / MB:,.0f} MB; {len(months)} of up to {keep} months are kept"
                 + (f", so about {max(0, int(room))} more months fit below {fail_mb:g} MB." if len(months) < keep else "."))
    return "\n".join(lines) + "\n\n" + note + "\n", verdict


def main(site: str, warn_mb: float = WARN_MB, fail_mb: float = FAIL_MB) -> int:
    path = Path(site)
    if not path.is_dir():
        print(f"{site}: no such folder (build the site first)")
        return 2
    table, verdict = report(path, warn_mb, fail_mb)
    print(table)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write("### Site size\n\n" + table)
    last = table.strip().splitlines()[-1]
    if verdict == "fail":
        print(f"::error::{last} Keep fewer months searchable (WOLAND_SEARCH_MONTHS) or move older months out.")
        return 1
    if verdict == "warn":
        print(f"::warning::{last}")
    return 0
