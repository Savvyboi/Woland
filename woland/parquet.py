"""Monthly Parquet snapshots of the archive, for SQL over months without reading thousands of JSONL files.

`data/parquet/woland-YYYY-MM.parquet` holds one row per stored article of that month (Moscow days): its headline
and metadata (leads stay in the JSONL files, which they would make two and a half times larger), with what the
build worked out for it: the framings and topics it matched, the countries it names, the speaker its headline
quotes, whether the outlet labels it machine-written. `data/parquet/manifest.json` lists the files with their row
counts and fingerprints. The site's Query Lab (lab.html) reads them with DuckDB-Wasm; they open as well in
DuckDB, pandas, polars or R (arrow). Built in woland/build.py with each month, and cached with it.

Values Woland does not know are null, never zero or an empty string: `words` is null when the page was not read,
`speaker` when the headline quotes nobody Woland recognises, `title_en` when a Russian headline has not been
translated yet. An English outlet's headline is its own English, so `title_en` repeats `title` there.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .util import parse_dt

# (column, arrow type name, meaning) — the README and the Query Lab show the same list
COLUMNS = [
    ("id", "string", "stable id, <outlet>:<hash of URL>"),
    ("outlet", "string", "outlet id (config/outlets.yaml)"),
    ("outlet_group", "string", "state | official | mass | foreign | hardline"),
    ("language", "string", "ru | en: the outlet's language"),
    ("published_at", "timestamp", "when the outlet says it was published (UTC)"),
    ("day", "date", "the Moscow day it is filed under"),
    ("collected_at", "timestamp", "when Woland retrieved it (UTC)"),
    ("title", "string", "the headline as published"),
    ("title_en", "string", "English: the machine translation of a Russian headline, or an English outlet's own"),
    ("section", "string", "the outlet's section"),
    ("tags", "list<string>", "the outlet's tags (at most 8)"),
    ("author", "string", "byline"),
    ("words", "int32", "words in the body text; null when the page was not read"),
    ("headline_only", "bool", "the page of an outlet Woland reads has not been read (yet): headline and lead from a listing"),
    ("via", "string", "page | feed"),
    ("machine", "bool", "the outlet itself labels the item machine-written: left out of every count on the site"),
    ("framings", "list<string>", "framings matched (config/lexicon.yaml): pattern matches, not a judgement"),
    ("topics", "list<string>", "neutral topics matched"),
    ("countries", "list<string>", "ISO codes of the countries the headline or lead names"),
    ("speaker", "string", "who the headline quotes, as Woland reads it (the Analysis page's speakers)"),
    ("speaker_kind", "string", "person | inst (an institution) | role (an unnamed expert, analyst, source …) | media"),
    ("url", "string", "the article"),
    ("archive_capture", "string", "the Internet Archive capture read, YYYYMMDDhhmmss, when the outlet did not answer: "
                                  "the copy is https://web.archive.org/web/<archive_capture>/<url>"),
    ("fingerprint", "string", "first 16 hex digits of SHA-256 over the normalised text"),
]


def row(rec: dict, outlet, framings: list[str], topics: list[str], countries: list[str],
        voice: tuple | None, machine: bool, headline_only: bool) -> dict:
    """One article's row: the record's own fields and what the build found in it."""
    en = outlet.lang == "en"
    ar = rec.get("ar") or None
    return {
        "id": rec["id"], "outlet": rec["o"], "outlet_group": outlet.group, "language": outlet.lang,
        "published_at": rec["p"], "collected_at": rec.get("r") or None,
        "title": rec.get("t") or None, "title_en": (rec.get("t") if en else rec.get("te")) or None,
        "section": rec.get("s") or None, "tags": list(rec.get("g") or []), "author": rec.get("a") or None,
        "words": rec.get("w") or None, "headline_only": bool(headline_only), "via": rec.get("via") or None,
        "machine": bool(machine), "framings": framings, "topics": topics, "countries": sorted(countries),
        "speaker": voice[0] if voice else None, "speaker_kind": voice[1] if voice else None,
        "url": rec["u"], "archive_capture": ar,
        "fingerprint": rec.get("h") or None,
    }


def _schema():
    import pyarrow as pa
    types = {"string": pa.string(), "int32": pa.int32(), "bool": pa.bool_(), "date": pa.date32(),
             "timestamp": pa.timestamp("s", tz="UTC"), "list<string>": pa.list_(pa.string())}
    return pa.schema([pa.field(name, types[t]) for name, t, _ in COLUMNS],
                     metadata={b"source": b"Woland", b"licence": b"CC BY 4.0 (Woland's data); headlines and excerpts belong to their publishers"})


def write_month(rows: list[dict], path: Path) -> dict:
    """Write one month's rows (sorted by time) and return its manifest entry."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from .util import MSK
    rows = sorted(rows, key=lambda r: (r["published_at"], r["outlet"], r["url"]))
    cols = {name: [] for name, _, _ in COLUMNS}
    for r in rows:
        p = parse_dt(r["published_at"])
        for name, _, _ in COLUMNS:
            if name == "published_at":
                cols[name].append(p)
            elif name == "day":
                cols[name].append(p.astimezone(MSK).date())
            elif name == "collected_at":
                cols[name].append(parse_dt(r[name]) if r[name] else None)
            else:
                cols[name].append(r[name])
    table = pa.table(cols, schema=_schema())
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd", compression_level=9, row_group_size=50_000,
                   use_dictionary=["outlet", "outlet_group", "language", "section", "via", "speaker_kind"])
    data = path.read_bytes()
    return {"file": path.name, "rows": table.num_rows, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def available() -> bool:
    try:
        import pyarrow  # noqa: F401
        import pyarrow.parquet  # noqa: F401
    except ImportError:
        return False
    return True
