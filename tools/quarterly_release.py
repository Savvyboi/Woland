"""Assemble a quarter's data release: what .github/workflows/quarterly-release.yml attaches to a GitHub Release
tagged `data-YYYY-Q#` (and Zenodo, once its GitHub integration is switched on, archives with a DOI).

    python tools/quarterly_release.py 2026-Q4 [--site _site] [--out dist]

writes into dist/:
  woland-articles-2026-Q4.tar.gz      the quarter's day files with the lexicon, glossary and audit
                                      (tools/export_quarter.py), reproducible byte for byte
  woland-2026-10.parquet …            the quarter's monthly Parquet snapshots, when the built site has them
                                      (data/parquet/, written by `python -m woland build`)
  SHA256SUMS                          one line per file above (`sha256sum -c SHA256SUMS`)
  RELEASE.md                          the release notes: what is in it, how to cite it, what it is not

A quarter is released only once it is over (Moscow time) and every one of its days has been collected in full
(`complete_through` in the built site's data/meta.json), unless --force: a release is a citation, and must
not change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_quarter  # noqa: E402

ROOT = export_quarter.ROOT
MSK = timezone(timedelta(hours=3))


def quarter_end(quarter: str) -> date:
    last = export_quarter.quarter_months(quarter)[-1]
    y, m = (int(x) for x in last.split("/"))
    return (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)


def previous_quarter(today: date) -> str:
    q = (today.month - 1) // 3 + 1
    return f"{today.year - 1}-Q4" if q == 1 else f"{today.year}-Q{q - 1}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_complete(quarter: str, site: Path | None, today: date) -> str | None:
    """Why the quarter cannot be released yet, or None."""
    end = quarter_end(quarter)
    if today <= end:
        return f"{quarter} is not over yet (it ends {end})"
    if site is None:
        return None
    meta = site / "data" / "meta.json"
    if not meta.exists():
        return f"{meta}: not found (build the site first, or pass --force)"
    through = json.loads(meta.read_text(encoding="utf-8")).get("complete_through")
    if not through or through < end.isoformat():
        return f"{quarter}: its days are collected in full only through {through} (it ends {end})"
    return None


def notes(quarter: str, files: list[tuple[str, int, str]], repo: str, articles: int, first: str, last: str,
          complete: bool = True) -> str:
    rows = "\n".join(f"| `{name}` | {size / 1e6:,.1f} MB | `{digest[:16]}…` |" for name, size, digest in files)
    return f"""# Woland data, {quarter}

The headlines, leads (≤ 240 characters) and framing snippets that Woland recorded from the Russian state and
pro-Kremlin press from {first} to {last}, with English machine translations: {articles:,} articles,
one JSON object per line, filed under the Moscow day each was published (`data/articles/YYYY/MM/DD/<outlet>.jsonl`;
the fields are documented in the README). {"Every day of the quarter was collected in full before this release."
if complete else "**Released before every day of the quarter was collected in full**: later collection may add articles."}

| file | size | SHA-256 |
|---|---|---|
{rows}

`sha256sum -c SHA256SUMS` checks the files; the archive's own `.SHA256SUMS` checks every file inside it.
The lexicon, the glossary and the audit of the framings the data was tagged with are inside the archive.

**Citing.** Woland, *Woland: a chronicle of the Russian state press*, data release {quarter}, {repo}/releases/tag/data-{quarter}
(once the release has a Zenodo DOI, cite the DOI instead).

**What it is not.** Framings are counts of word-pattern matches, not a reading of the articles; Woland does
not republish articles, and headlines and excerpts remain the property of their publishers. Woland's own data
(structure, translations, tagging) is released under CC BY 4.0; the code under MIT.
"""


def assemble(quarter: str, out: Path, site: Path | None, repo: str, root: Path = ROOT,
             complete: bool = True) -> list[Path]:
    if out.exists():
        shutil.rmtree(out)
    archive, inner = export_quarter.export(quarter, out, root)
    paths = [archive, inner]
    if site is not None:
        for month in export_quarter.quarter_months(quarter):
            src = site / "data" / "parquet" / f"woland-{month.replace('/', '-')}.parquet"
            if src.exists():
                paths.append(Path(shutil.copy2(src, out / src.name)))
    files = [(p.name, p.stat().st_size, sha256(p)) for p in paths]
    (out / "SHA256SUMS").write_text("".join(f"{d}  {n}\n" for n, _, d in files), encoding="utf-8", newline="\n")
    days = [f for _, f in export_quarter.members(root, quarter) if f.suffix == ".jsonl"]
    articles = sum(1 for f in days for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
    stamp = sorted("-".join(f.parent.relative_to(root / "data" / "articles").parts) for f in days)
    (out / "RELEASE.md").write_text(notes(quarter, files, repo, articles, stamp[0], stamp[-1], complete),
                                    encoding="utf-8", newline="\n")
    return paths + [out / "SHA256SUMS", out / "RELEASE.md"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("quarter", nargs="?", help="YYYY-Q1 … YYYY-Q4 (default: the quarter before today's, Moscow time)")
    ap.add_argument("--site", default=None, help="the built site, for its Parquet snapshots and meta.json")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--repo", default="https://github.com/Savvyboi/Woland")
    ap.add_argument("--force", action="store_true", help="release even if the quarter is not over or not complete")
    a = ap.parse_args(argv)
    today = datetime.now(MSK).date()
    quarter = a.quarter or previous_quarter(today)
    site = Path(a.site) if a.site else None
    try:
        export_quarter.quarter_months(quarter)
        why = None if a.force else check_complete(quarter, site, today)
        if why:
            print(why, file=sys.stderr)
            return 3
        paths = assemble(quarter, Path(a.out), site, a.repo,
                         complete=check_complete(quarter, site, today) is None if a.force else True)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    for p in paths:
        print(f"{p} ({p.stat().st_size / 1e6:,.1f} MB)")
    print(f"quarter={quarter}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
