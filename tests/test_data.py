"""The archive itself (data/): every stored record must be well-formed and filed under the right day.

Runs over whatever is in data/ — in CI after every collection commit, locally before pushing."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime

import pytest

from woland.config import START_DATE, load_lexicon, load_outlets
from woland.store import ART_DIR, STATE_DIR
from woland.util import MSK, short_hash

FILES = sorted(ART_DIR.glob("*/*/*/*.jsonl")) if ART_DIR.exists() else []
pytestmark = pytest.mark.skipif(not FILES, reason="no collected articles in data/")

OUTLETS = {o.id: o for o in load_outlets(include_disabled=True)}
NARRATIVES = {n.id for n in load_lexicon()}
HEX16 = re.compile(r"^[0-9a-f]{16}$")
UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
FIELDS = {"id", "o", "u", "p", "m", "t", "te", "d", "s", "g", "a", "w", "h", "r", "kb", "via"}


def problems_in(path) -> list[str]:
    out = []
    oid = path.stem
    day = date(int(path.parts[-4]), int(path.parts[-3]), int(path.parts[-2]))
    o = OUTLETS.get(oid)
    if o is None:
        return [f"{path}: unknown outlet {oid}"]
    if day < START_DATE:
        out.append(f"{path}: before the start date")
    urls, prev = set(), None
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        where = f"{oid} {day} line {n}"
        try:
            r = json.loads(line)
        except ValueError:
            out.append(f"{where}: not JSON")
            continue
        if extra := set(r) - FIELDS:
            out.append(f"{where}: unexpected fields {sorted(extra)}")
        for k in ("id", "o", "u", "p", "t", "w", "h", "r", "via"):
            if k not in r:
                out.append(f"{where}: missing {k}")
        if out and out[-1].startswith(where):
            continue
        if r["o"] != oid:
            out.append(f"{where}: outlet {r['o']} in {oid}'s file")
        if r["id"] != f"{oid}:{short_hash(r['u'])}":
            out.append(f"{where}: id does not match the URL")
        if not o.is_article(r["u"]):
            out.append(f"{where}: {r['u']} does not look like one of {oid}'s articles")
        if r["u"] in urls:
            out.append(f"{where}: duplicate {r['u']}")
        urls.add(r["u"])
        try:
            p = datetime.fromisoformat(r["p"])
        except ValueError:
            out.append(f"{where}: bad time {r['p']}")
            continue
        if p.utcoffset() is None or p.astimezone(MSK).date() != day or r["p"][:10] != day.isoformat():
            out.append(f"{where}: published {r['p']} but filed under {day}")
        if prev and (r["p"], r["u"]) < prev:
            out.append(f"{where}: not in time order")
        prev = (r["p"], r["u"])
        if "m" in r and datetime.fromisoformat(r["m"]) <= p:
            out.append(f"{where}: modified before it was published")
        if not r["t"].strip() or len(r["t"]) > 301:
            out.append(f"{where}: headline empty or too long")
        if len(r.get("d", "")) > 241 or ("d" in r and not r["d"].strip()):
            out.append(f"{where}: lead empty or longer than 240 characters")
        if "te" in r and (o.lang != "ru" or not r["te"].strip()):
            out.append(f"{where}: translation where none belongs")
        if len(r.get("s", "")) > 60 or len(r.get("a", "")) > 120:
            out.append(f"{where}: section or author too long")
        g = r.get("g", [])
        if not isinstance(g, list) or len(g) > 8 or not all(isinstance(x, str) and x for x in g):
            out.append(f"{where}: bad tags")
        if not isinstance(r["w"], int) or r["w"] < 0:
            out.append(f"{where}: bad word count")
        if not HEX16.match(r["h"]) or not UTC.match(r["r"]):
            out.append(f"{where}: bad fingerprint or retrieval time")
        if r["via"] not in ("page", "feed"):
            out.append(f"{where}: via {r['via']}")
        for nid, snip in (r.get("kb") or {}).items():
            if nid not in NARRATIVES:
                out.append(f"{where}: body match for unknown framing {nid}")
            if not snip or len(snip) > 175:
                out.append(f"{where}: body snippet empty or longer than 175 characters")
    return out


def test_every_record_is_well_formed_and_filed_under_its_day():
    problems = [p for f in FILES for p in problems_in(f)]
    assert not problems, f"{len(problems)} problems, e.g.:\n" + "\n".join(problems[:25])


def test_no_article_is_filed_twice():
    seen, twice = {}, []
    for f in FILES:
        for line in f.read_text(encoding="utf-8").splitlines():
            u = json.loads(line)["u"]
            if u in seen:
                twice.append(f"{u}: {seen[u]} and {f.parent.name}")
            seen[u] = f"{f.parts[-3]}-{f.parent.name}"
    assert not twice, f"{len(twice)} articles filed under two days, e.g.:\n" + "\n".join(twice[:10])


def test_bodies_were_read_for_page_outlets():
    """Articles whose pages Woland read should mostly have body texts (w > 0): if not, extraction broke.
    (Headline-only records, via "feed", have none by definition.)"""
    words = defaultdict(lambda: [0, 0])
    for f in FILES:
        if OUTLETS[f.stem].fetch:
            for line in f.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                if r["via"] == "page":
                    words[f.stem][0] += 1
                    words[f.stem][1] += r["w"] > 0
    empty = {o: f"{have}/{n}" for o, (n, have) in words.items() if n >= 50 and have < 0.8 * n}
    assert not empty, f"too few body texts: {empty}"


def test_coverage_state_is_consistent():
    path = STATE_DIR / "coverage.json"
    if not path.exists():
        pytest.skip("no coverage.json")
    cov = json.loads(path.read_text(encoding="utf-8"))
    for oid, days in cov.items():
        assert oid in OUTLETS, oid
        for d, v in days.items():
            date.fromisoformat(d)
            assert v.get("status") in ("complete", "partial", "feed"), (oid, d, v)
            assert isinstance(v.get("n"), int) and v["n"] >= 0, (oid, d, v)
