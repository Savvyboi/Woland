"""The archive on disk.

    data/articles/YYYY/MM/DD/<outlet>.jsonl   one article per line, sorted by publication time
    data/state/coverage.json                  what was collected for every outlet and day
    data/state/seen.json                      URLs recently rejected (out of range, 404 …)
    data/state/runs.json                      summaries of the latest runs
    data/state/urls/<outlet>.txt              every URL ever stored: "<url key> <day>" per line, appended to
                                              (a later line for the same key wins: the record moved)

Record fields (short names keep the archive small):
    id  stable id "<outlet>:<hash>"           o   outlet id
    u   URL                                   p   published, ISO 8601, Moscow time
    m   modified (if announced)               t   headline as published
    te  English machine translation           d   lead / summary (max 240 characters)
    s   section                               g   tags (max 8)
    a   author                                w   words in the body (0 = body not available)
    h   content fingerprint (sha256, 16 hex)  r   retrieved at (UTC)
    kb  narratives found only in the body text, with a short snippet as evidence
    via how the article was obtained: page (article page read) or feed (outlet's own feed)
    ar  when the page was read from the Internet Archive's copy (the outlet did not answer): the
        capture's time, YYYYMMDDhhmmss (UTC), as in https://web.archive.org/web/<ar>/<u>
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

from .config import DATA_DIR

ART_DIR = DATA_DIR / "articles"
STATE_DIR = DATA_DIR / "state"


def day_dir(day: date) -> Path:
    return ART_DIR / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"


def day_path(day: date, outlet: str) -> Path:
    return day_dir(day) / f"{outlet}.jsonl"


def read_day(day: date, outlet: str) -> list[dict]:
    p = day_path(day, outlet)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_day(day: date, outlet: str, records: list[dict]) -> None:
    p = day_path(day, outlet)
    uniq = {}
    for r in records:
        uniq[r["u"]] = {k: v for k, v in r.items() if not k.startswith("_")}  # "_…": run-time markers only
    rows = sorted(uniq.values(), key=lambda r: (r["p"], r["u"]))
    if not rows:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, p)


def merge_day(day: date, outlet: str, new: list[dict]) -> int:
    """Add records to a day file. Existing records win and missing fields are filled from the new ones,
    except that a record read from the article page replaces a headline-only one (via "feed") for the
    same URL: the translation is kept if the headline did not change."""
    existing = {r["u"]: r for r in read_day(day, outlet)}
    added = []
    for r in new:
        old = existing.get(r["u"])
        if old is None:
            existing[r["u"]] = r
            added.append(r["u"])
        elif old.get("via") == "feed" and r.get("via") == "page":
            if not r.get("te") and old.get("te") and old.get("t") == r.get("t"):
                r = {**r, "te": old["te"]}
            existing[r["u"]] = r
        else:
            for k, v in r.items():
                if v and not old.get(k):
                    old[k] = v
    write_day(day, outlet, list(existing.values()))
    if added:
        index_urls(outlet, day, added)
    return len(existing)


def drop_urls(day: date, outlet: str, urls: set[str]) -> int:
    """Remove records from a day file (an upgraded article that moved to a neighbouring day)."""
    recs = read_day(day, outlet)
    keep = [r for r in recs if r["u"] not in urls]
    if len(keep) != len(recs):
        if keep:
            write_day(day, outlet, keep)
        else:
            day_path(day, outlet).unlink()
    return len(recs) - len(keep)


class Known(dict):
    """URL → (how the stored record was read: "page", or "feed" for a headline-only record; its day), for
    the records filed under the days looked at. `in` also answers for every other article of the outlet
    ever stored (the URL index), so that one URL is filed once, however long after a site re-dates it."""

    def __init__(self, recent: dict, index: dict[str, str]):
        super().__init__(recent)
        self.index = index

    def __contains__(self, url) -> bool:
        return dict.__contains__(self, url) or url_key(url) in self.index

    def __getitem__(self, url):
        if dict.__contains__(self, url):
            return dict.__getitem__(self, url)
        return "page", self.index[url_key(url)]  # stored long ago: known, not to be read again


def known_urls(outlet: str, start: date, end: date) -> Known:
    urls: dict[str, tuple[str, str]] = {}
    d = start
    while d <= end:
        urls.update((r["u"], (r.get("via", "page"), d.isoformat())) for r in read_day(d, outlet))
        d += timedelta(days=1)
    return Known(urls, load_url_index(outlet))


def headline_only(outlet: str, start: date, end: date) -> list[dict]:
    """The records kept from a listing or feed only (via "feed") and filed under [start, end]: their pages
    are to be read again."""
    return [r for d in _days(start, end) for r in read_day(d, outlet) if r.get("via") == "feed"]


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ── The URL index: every article ever stored, per outlet ─────────────────────
def url_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _index_path(outlet: str) -> Path:
    return STATE_DIR / "urls" / f"{outlet}.txt"


def load_url_index(outlet: str) -> dict[str, str]:
    """URL key → the day its record is filed under, for every article of the outlet ever stored. Built from
    the day files the first time it is needed."""
    p = _index_path(outlet)
    if not p.exists():
        return rebuild_url_index(outlet)
    index = {}
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            key, _, day = line.strip().partition(" ")
            if key:
                index[key] = day
    return index


def rebuild_url_index(outlet: str) -> dict[str, str]:
    """Write an outlet's URL index afresh from its day files."""
    index = {url_key(r["u"]): d.isoformat() for d in available_days() for r in read_day(d, outlet)}
    rows = sorted((day, key) for key, day in index.items())
    p = _index_path(outlet)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.writelines(f"{key} {day}\n" for day, key in rows)
    os.replace(tmp, p)
    return index


def index_urls(outlet: str, day: date, urls) -> None:
    p = _index_path(outlet)
    if not p.exists():
        rebuild_url_index(outlet)  # the day file already holds the new records
        return
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.writelines(f"{url_key(u)} {day.isoformat()}\n" for u in urls)


def available_days() -> list[date]:
    days = []
    if not ART_DIR.exists():
        return days
    for y in sorted(ART_DIR.iterdir()):
        for m in sorted(y.iterdir()) if y.is_dir() else []:
            for d in sorted(m.iterdir()) if m.is_dir() else []:
                if d.is_dir() and any(d.glob("*.jsonl")):
                    days.append(date(int(y.name), int(m.name), int(d.name)))
    return days


def outlets_on(day: date) -> list[str]:
    return sorted(p.stem for p in day_dir(day).glob("*.jsonl"))


# ── State files ───────────────────────────────────────────────────────────────
def _load(name: str, default):
    p = STATE_DIR / name
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _save(name: str, data) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / name
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    for attempt in range(5):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:  # Windows: another process is reading the file right now
            time.sleep(0.2 * (attempt + 1))
    os.replace(tmp, p)


def _merged(name: str, data: dict, only) -> dict:
    """With `only`, write just part of `data` over what is on disk, so that several collection runs (the
    hourly feeds and a long backfill, say) can work side by side without undoing each other's work:
    `only` maps outlets to the keys (days, URLs) this run changed, or lists outlets whose entries it owns."""
    if only is None:
        return data
    merged = _load(name, {})
    for oid in only:
        if oid not in data:
            continue
        if isinstance(only, dict):
            entry = merged.setdefault(oid, {})
            entry.update((k, data[oid][k]) for k in only[oid] if k in data[oid])
        else:
            merged[oid] = data[oid]
    return merged


def load_coverage() -> dict:
    return _load("coverage.json", {})


def save_coverage(cov: dict, only=None) -> None:
    """`only`: {outlet: the days this run looked at} (or a list of outlets whose whole entry it owns)."""
    _save("coverage.json", _merged("coverage.json", cov, only))


def load_seen() -> dict:
    return _load("seen.json", {})


def save_seen(seen: dict, today: date, keep_days: int = 14, only=None) -> None:
    """`only`: {outlet: the URLs this run rejected}; others' rejections are kept."""
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    seen = _merged("seen.json", seen, only)
    pruned = {o: {u: d for u, d in urls.items() if d >= cutoff} for o, urls in seen.items()}
    _save("seen.json", {o: u for o, u in pruned.items() if u})


def append_run(summary: dict, keep: int = 40, keep_polls: int = 48) -> None:
    """The latest runs of each kind: frequent feed polls must not push out the nightly runs (the website
    works out from them which days are complete)."""
    runs = _load("runs.json", []) + [summary]
    polls = [r for r in runs if r.get("mode") == "poll"][-keep_polls:]
    other = [r for r in runs if r.get("mode") != "poll"][-keep:]
    kept = {id(r) for r in polls + other}
    _save("runs.json", [r for r in runs if id(r) in kept])


def load_runs() -> list:
    return _load("runs.json", [])
