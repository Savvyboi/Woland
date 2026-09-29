"""A git merge driver for Woland's data files, so that runs writing at the same time (the hourly feeds beside
the nightly collection, say) merge their work when they push instead of conflicting.

    git config merge.woland.name "Woland data files"
    git config merge.woland.driver "python -m woland merge %O %A %B %P"

`.gitattributes` sends the day files, the state files and the URL index here. Git gives the common ancestor
(%O), the current version (%A, which receives the result; during `git pull --rebase` it is what others have
pushed meanwhile) and the other version (%B: the commit being replayed, i.e. this run's work). Each file is
merged entry by entry: records by URL, coverage by outlet and day, rejected URLs by URL, runs by start time,
the URL index by key. An entry only one side changed is taken from that side, one side removed and the other
left alone is removed; where both changed the same entry they are combined as the collector would have:
a record read from its page beats a headline-only one, a completed day stays complete.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_MISSING = object()


def _three_way(base: dict, ours: dict, theirs: dict, both, removal_wins: bool = False) -> dict:
    """Merge three versions of a mapping key by key; `both(o, a, b)` settles keys both sides changed. A key
    one side removed and the other changed is kept, unless `removal_wins`."""
    out = {}
    for k in dict.fromkeys([*ours, *theirs]):
        o, a, b = base.get(k, _MISSING), ours.get(k, _MISSING), theirs.get(k, _MISSING)
        if a is _MISSING or b is _MISSING:
            one = b if a is _MISSING else a
            if o is not _MISSING and (one == o or removal_wins):
                continue  # the other side removed it
            out[k] = one  # added on one side (or changed on one side, removed on the other)
        elif a == b or b == o:
            out[k] = a
        elif a == o:
            out[k] = b
        else:
            out[k] = both(None if o is _MISSING else o, a, b)
    return out


# ── Day files: one record per URL ────────────────────────────────────────────
_FILL = ("te", "d", "s", "g", "a")  # what one version of a record may lend the other


def _record(o, a: dict, b: dict) -> dict:
    """Both sides changed the same article: keep the one read from its page, else the later retrieval, and
    fill in the descriptive fields it lacks from the other."""
    first, second = sorted((a, b), key=lambda r: (r.get("via") == "page", r.get("r", "")), reverse=True)
    out = dict(first)
    for k in _FILL:
        if k == "te" and first.get("t") != second.get("t"):
            continue  # a translation of another headline
        if second.get(k) and not out.get(k):
            out[k] = second[k]
    return out


def merge_records(base: str, ours: str, theirs: str) -> str:
    """A record removed on one side was moved to another day's file (a headline-only record whose page gave
    another date): it stays removed, or it would be filed twice."""
    def parse(text):
        return {r["u"]: r for r in (json.loads(line) for line in text.splitlines() if line.strip())}
    merged = _three_way(parse(base), parse(ours), parse(theirs), _record, removal_wins=True)
    rows = sorted(merged.values(), key=lambda r: (r["p"], r["u"]))
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows)


# ── State files ───────────────────────────────────────────────────────────────
_STATUS_RANK = {"partial": 0, "feed": 1, "complete": 2}


def _coverage_entry(o, a: dict, b: dict) -> dict:
    """Both sides recorded the same outlet and day. A day is never reopened once complete; counts take the
    larger figure (the next run recounts the day file), headline-only records too (so that the day is looked
    at again rather than forgotten)."""
    out = dict(a if a.get("at", "") >= b.get("at", "") else b)
    for k in ("n", "found"):
        if k in a or k in b:
            out[k] = max(a.get(k, 0), b.get(k, 0))
    if a.get("h") or b.get("h"):
        out["h"] = max(a.get("h", 0), b.get("h", 0))
    status = max((a.get("status"), b.get("status")), key=lambda s: _STATUS_RANK.get(s, -1))
    if status:
        out["status"] = status
    return out


def merge_coverage(base: dict, ours: dict, theirs: dict) -> dict:
    return _three_way(base, ours, theirs,
                      lambda o, a, b: _three_way(o or {}, a, b, _coverage_entry))


def merge_seen(base: dict, ours: dict, theirs: dict) -> dict:
    return _three_way(base, ours, theirs,
                      lambda o, a, b: _three_way(o or {}, a, b, lambda _o, x, y: max(x, y)))


def merge_runs(base: list, ours: list, theirs: list) -> list:
    from .store import trim_runs
    def key(r):
        return f"{r.get('at')}|{r.get('mode')}"
    merged = _three_way({key(r): r for r in base}, {key(r): r for r in ours}, {key(r): r for r in theirs},
                        lambda o, a, b: b)
    return trim_runs(list(merged.values()))


def merge_json(name: str, base: str, ours: str, theirs: str) -> str:
    empty = [] if name == "runs.json" else {}
    o, a, b = (json.loads(t) if t.strip() else empty for t in (base, ours, theirs))
    if name == "coverage.json":
        merged = merge_coverage(o, a, b)
    elif name == "seen.json":
        merged = merge_seen(o, a, b)
    elif name == "runs.json":
        merged = merge_runs(o, a, b)
    elif name == "check.json":  # per outlet, the later check
        merged = _three_way(o, a, b, lambda _o, x, y: max(x, y, key=lambda e: e.get("at", "")))
    else:
        raise ValueError(f"no merge rule for {name}")
    # as store._save writes them
    return json.dumps(merged, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def merge_index(base: str, ours: str, theirs: str) -> str:
    """data/state/urls/<outlet>.txt: "<key> <day>" lines, a later line for the same key winning. This side's
    lines are kept in their order and the other side's new ones appended."""
    def lines(text):
        return [tuple(line.split(" ", 1)) for line in text.splitlines() if " " in line]
    lo, la, lb = lines(base), lines(ours), lines(theirs)
    merged = _three_way(dict(lo), dict(la), dict(lb), lambda o, a, b: b)
    out, emitted = [], {}
    for key, day in la + lb:
        if merged.get(key) == day and emitted.get(key) != day:
            out.append(f"{key} {day}\n")
            emitted[key] = day
    return "".join(out)


def merge_text(path: str, base: str, ours: str, theirs: str) -> str:
    p = Path(path)
    if p.suffix == ".jsonl":
        return merge_records(base, ours, theirs)
    if p.parent.name == "urls" and p.suffix == ".txt":
        return merge_index(base, ours, theirs)
    if p.suffix == ".json":
        return merge_json(p.name, base, ours, theirs)
    raise ValueError(f"no merge rule for {path}")


def main(base: str, ours: str, theirs: str, path: str) -> int:
    """Git's entry point: merge into `ours` and return 0, or 1 to leave the conflict to a person."""
    def read(f):
        return Path(f).read_text(encoding="utf-8") if Path(f).exists() else ""
    try:
        result = merge_text(path, read(base), read(ours), read(theirs))
    except (ValueError, KeyError, TypeError) as exc:
        print(f"woland merge: {path}: {exc}", file=sys.stderr)
        return 1
    with open(ours, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(result)
    return 0
