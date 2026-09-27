"""Reading a framing's matches by hand (docs/lexicon-audit.md): a random sample of the articles the site
counts under a framing, with the words that matched marked [[like this]].

    python -m woland sample enemies-within --seed 3 --csv sample.csv

The rows have the columns of docs/lexicon-audit-sample.csv, with `fits` and `note` left for the reader.
"""
from __future__ import annotations

import csv
import random
import sys

from .config import load_lexicon, load_outlets
from .lexicon import Lexicon
from .store import available_days, outlets_on, read_day

COLUMNS = ["round", "counts", "framing", "n", "id", "outlet", "day", "where", "fits", "note", "headline", "excerpt"]


def marked(text: str, span: tuple[int, int]) -> str:
    a, b = span
    return f"{text[:a]}[[{text[a:b]}]]{text[b:]}"


def match_of(lex: Lexicon, rec: dict, nid: str, lang: str) -> tuple[str, str] | None:
    """Where the site counts the article under the framing, as the build does (woland/build.py:
    narratives_of): (headline | lead | text, the excerpt with the matched words marked)."""
    t, d = rec.get("t", ""), rec.get("d", "")
    for where, text, extra in (("headline", t, d), ("lead", d, t)):
        span = lex.find(text, lang, extra=extra).get(nid) if text else None
        if span:
            return where, marked(text, span)
    snip = (rec.get("kb") or {}).get(nid)
    span = lex.find(snip, lang, extra=f"{t} {d}").get(nid) if snip else None
    return ("text", marked(snip, span)) if span else None


def matches(nid: str, days=None, narratives=None) -> list[tuple[dict, str, str]]:
    """Every article counted under the framing: (record, where, excerpt). (A framing's matches do not
    depend on the others, so only its own patterns are compiled.)"""
    lex = Lexicon([n for n in (narratives or load_lexicon()) if n.id == nid])
    if nid not in lex.by_id:
        raise SystemExit(f"unknown framing or topic: {nid}")
    lang = {o.id: o.lang for o in load_outlets(include_disabled=True)}
    out = []
    for d in days or available_days():
        for oid in outlets_on(d):
            for rec in read_day(d, oid):
                m = match_of(lex, rec, nid, lang.get(oid, "ru"))
                if m:
                    out.append((rec, *m))
    return out


def sample(nid: str, n: int = 25, seed: int = 1, round_: str = "", days=None) -> tuple[int, list[dict]]:
    """How many articles are counted under the framing, and n of them drawn at random (the same seed
    over the same archive draws the same articles)."""
    found = matches(nid, days)
    found.sort(key=lambda m: m[0]["id"])  # a stable order before drawing
    picked = random.Random(seed).sample(found, min(n, len(found)))
    rows = [{"round": round_, "counts": "yes", "framing": nid, "n": i, "id": rec["id"], "outlet": rec["o"],
             "day": rec["p"][:10], "where": where, "fits": "", "note": "", "headline": rec["t"], "excerpt": excerpt}
            for i, (rec, where, excerpt) in enumerate(picked, 1)]
    return len(found), rows


def main(nid: str, n: int, seed: int, round_: str, csv_path: str | None) -> int:
    total, rows = sample(nid, n, seed, round_)
    print(f"{nid}: {total} articles counted; {len(rows)} drawn with seed {seed}", file=sys.stderr)
    if csv_path:
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
    else:
        for r in rows:
            print(f"{r['n']:3}. {r['outlet']} {r['day']} [{r['where']}] {r['excerpt']}")
    return 0
