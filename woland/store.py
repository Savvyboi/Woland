"""The archive on disk.

    data/articles/YYYY/MM/DD/<outlet>.jsonl   one article per line, sorted by publication time
    data/state/coverage.json                  what was collected for every outlet and day
    data/state/seen.json                      URLs recently rejected (out of range, 404 …)
    data/state/runs.json                      summaries of the latest runs

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
"""
from __future__ import annotations

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
        uniq[r["u"]] = r
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
    """Add records to a day file. Existing records win; missing fields are filled from the new ones."""
    existing = {r["u"]: r for r in read_day(day, outlet)}
    for r in new:
        old = existing.get(r["u"])
        if old is None:
            existing[r["u"]] = r
        else:
            for k, v in r.items():
                if v and not old.get(k):
                    old[k] = v
    write_day(day, outlet, list(existing.values()))
    return len(existing)


def known_urls(outlet: str, start: date, end: date) -> set[str]:
    urls = set()
    d = start
    while d <= end:
        urls.update(r["u"] for r in read_day(d, outlet))
        d += timedelta(days=1)
    return urls


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
    """With `only`, replace just those outlets' entries in what is on disk: several collection runs
    (the hourly feeds and a long backfill, say) can then work side by side without undoing each other."""
    if only is None:
        return data
    merged = _load(name, {})
    for oid in only:
        if oid in data:
            merged[oid] = data[oid]
    return merged


def load_coverage() -> dict:
    return _load("coverage.json", {})


def save_coverage(cov: dict, only=None) -> None:
    _save("coverage.json", _merged("coverage.json", cov, only))


def load_seen() -> dict:
    return _load("seen.json", {})


def save_seen(seen: dict, today: date, keep_days: int = 14, only=None) -> None:
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    seen = _merged("seen.json", seen, only)
    pruned = {o: {u: d for u, d in urls.items() if d >= cutoff} for o, urls in seen.items()}
    _save("seen.json", {o: u for o, u in pruned.items() if u})


def append_run(summary: dict, keep: int = 150) -> None:
    runs = _load("runs.json", [])
    runs.append(summary)
    _save("runs.json", runs[-keep:])


def load_runs() -> list:
    return _load("runs.json", [])
