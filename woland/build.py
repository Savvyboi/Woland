"""Building the static website into _site/.

    _site/                       copy of site/ (HTML, CSS, JS)
    _site/data/meta.json         outlets, narratives, date range, the last completed day, run health
    _site/data/series.json       daily counts per outlet and per narrative per outlet; collection status
    _site/data/coverage.json     collection details for every outlet and day
    _site/data/days/<date>.json  the daily digest: narratives, rising words; <date>.ex.json: its examples
    _site/data/examples/<id>.json  each narrative's examples of the last days (the Narratives page)
    _site/data/search/…          a static full-text index, one folder per month (gzip files)
    _site/data/analysis/…        the Analysis page: voices, stories, countries and tags over the last 7 and 30
                                 completed days and all of them (<kind>/<window>.json); each day's stories
                                 (stories/day/<date>.json.gz)

Months are cached in .cache/build/<YYYY-MM>/ and only rebuilt when their articles, the previous
month, the lexicon, the translation glossary or this builder change: a daily build only redoes the
current month. Within it, each day's own results are cached in .cache/build/days/ for the current and the
previous month, so only the days whose articles changed are worked out again, shared among JOBS processes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import math
import multiprocessing
import os
import pickle
import re
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path

from . import analysis, feeds
from .config import CONFIG_DIR, ROOT, START_DATE, load_contexts, load_lexicon, load_outlets
from .glossary import Glossary
from .lexicon import Lexicon
from .store import available_days, day_dir, load_coverage, load_runs, read_day
from .textproc import STOP_EN, STOP_RU, headline_words, index_terms
from .util import MSK, iso_utc, normalize, parse_dt, today_msk, truncate

log = logging.getLogger("woland.build")

BUILD_VERSION = "8"
# A search downloads one index shard per month and one block per result it shows (20 at a time, mostly in
# different blocks): with 256 shards and 25 documents a block, a search for "Finland" over September and
# October 2026 needed ~160 KB of blocks instead of ~520 KB with 100, at four times as many files.
NB = 256          # index buckets per month
BLOCK = 25        # documents per block file
BASELINE_DAYS = 28
RISING_BASELINE = 14
RISING_MIN = {"ru": 6, "en": 5}  # headlines a word needs on the day to be considered "rising"
# ... and how unlikely its count must be by chance, given its usual rate (a Poisson test). This is what
# thins out the English list, drawn from only ~200 headlines a day, where five headlines with a word that
# usually has two are no news; for Russian's thousands of headlines the ratio alone decides.
RISING_P = 1e-3
RISING_SHOWN = 12                 # events listed per language
EXAMPLES = 6
FEED_DAYS = 7            # the feeds hold the newest articles of the last days collected (still being collected too)
FEED_ENTRIES = 40        # entries per feed
BRIEF_BASE_WEEKS = 4     # the weekly brief compares a week with the weeks before it
BRIEF_MIN = 20           # articles a framing needs in a week to be listed as rising or falling
BRIEF_SHOWN = 8          # items per list in the brief
WINDOWS = {"7": 7, "30": 30, "all": None}   # the Analysis page's periods, in completed days
VOICES_SHOWN = 60        # speakers listed per language and kind of speaker
STORY_OUTLETS = 4        # a story counts when this many outlets publish it on the same day
STORIES_SHOWN = 60       # stories listed per day
TAGS_SHOWN = 40
SECTIONS_SHOWN = 15
SEARCH_LEAD = 180  # characters of the lead kept in search documents (the archive keeps up to 240)
# GitHub Pages sites must stay under 1 GB: publish the search index for the most recent months only.
# Older months remain in the repository's data/ folder.
SEARCH_MONTHS = int(os.environ.get("WOLAND_SEARCH_MONTHS", "18"))
CODES = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CACHE = ROOT / ".cache" / "build"
# Each day's own work (aggregates, stories, search documents) depends on nothing but that day's articles and
# the code: it is cached per day too, so the nightly build, whose collection rewrites only the last week, redoes
# those days alone instead of the whole month (13 minutes on 25 November 2026, most of it the month's days).
DAY_CACHE_MONTHS = 2   # the current month and the one before; older months are cached whole
# Days to work out are shared among this many processes (GitHub's runners have four processors).
JOBS = int(os.environ.get("WOLAND_BUILD_JOBS", "0")) or min(4, os.cpu_count() or 1)


def bucket(s: str) -> int:
    """Shard of a word: hash of its first four characters (mirrored in site/assets/js/search.js)."""
    h = 0
    for ch in s[:4]:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % NB


def dump_gz(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))


def dump(path: Path, obj, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=None if pretty else (",", ":"),
                  indent=1 if pretty else None)


def poisson_tail(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam): how likely a count of k or more is by chance."""
    if k <= 0:
        return 1.0
    term = math.exp(k * math.log(lam) - lam - math.lgamma(k + 1))  # P(X = k)
    total, i = 0.0, k
    while term > 0 and i < k + 10000:
        total += term
        i += 1
        term *= lam / i
        if term < total * 1e-12:
            break
    return min(1.0, total)


def recent_runs(runs: list[dict], polls: int = 9, other: int = 3) -> list[dict]:
    """The runs the Outlets page lists, by start time (runs.json is appended to as runs finish, and runs
    overlap): the latest feed polls, and the latest nightly runs and backfills, which polls every hour or
    so would otherwise push out of the list within hours."""
    runs = sorted((r for r in runs if r.get("at")), key=lambda r: r["at"])
    keep = [r for r in runs if r.get("mode") == "poll"][-polls:] + [r for r in runs if r.get("mode") != "poll"][-other:]
    return sorted(keep, key=lambda r: r["at"])


_NO_ANSWER = re.compile(r"^no connection|\b(NoConnection|ConnectTimeout|ConnectionError|SSLError|ReadTimeout)\b")
_STATUS = re.compile(r": (\d{3})$|too many (\d{3}) error responses|\((\d{3})\)$")


def run_problems(v: dict) -> dict | None:
    """What went wrong for one outlet in one run, for the run log on the Outlets page: codes the site words in
    each language — noanswer (the site did not answer), refused (it refused the pages, or showed a bot check),
    "http <status>" (a listing or feed answered with an error), empty (a feed held nothing), budget (the run's
    time for the outlet ran out), failed (anything else) — and the messages themselves."""
    messages = [m for m in [v.get("aborted"), *v.get("errors", []), v.get("error")] if m]
    if not messages:
        return None
    codes = []
    for m in messages:
        status = _STATUS.search(m)
        if m.startswith("time budget"):
            code = "budget"
        elif _NO_ANSWER.search(m):
            code = "noanswer"
        elif m.startswith(("unreachable", "refused")) or m.endswith("bot check"):
            code = "refused"
        elif m.endswith("no items"):
            code = "empty"
        elif status:
            code = f"http {next(g for g in status.groups() if g)}"
        else:
            code = "failed"
        if code not in codes:
            codes.append(code)
    return {"c": codes, "t": "; ".join(messages)[:300]}


def silences(times: list[datetime], minutes: float) -> list[tuple[datetime, datetime]]:
    """The stretches longer than `minutes` between two consecutive times (sorted)."""
    return [(a, b) for a, b in zip(times, times[1:]) if (b - a).total_seconds() > minutes * 60]


def by_moscow_day(stretches) -> dict[str, list[list[str]]]:
    """Stretches of time as {day: [["HH:MM", "HH:MM"], …]} in Moscow time, one crossing midnight split in two."""
    out = defaultdict(list)
    for a, b in stretches:
        a, b = a.astimezone(MSK), b.astimezone(MSK)
        while a.date() < b.date():
            out[a.date().isoformat()].append([a.strftime("%H:%M"), "24:00"])
            a = datetime.combine(a.date() + timedelta(days=1), dtime(0), MSK)
        if a < b:
            out[a.date().isoformat()].append([a.strftime("%H:%M"), b.strftime("%H:%M")])
    return dict(out)


def delta_encode(nums: list[int]) -> list[int]:
    out, prev = [], 0
    for n in nums:
        out.append(n - prev)
        prev = n
    return out


def utf16_spans(spans: list[list] | None, text: str) -> list[list]:
    """Glossary spans ([start, end, the model's words], in code points) as the site counts: in UTF-16 units,
    and only those wholly within `text` (which may be the translation cut short)."""
    if not spans or not text:
        return []
    def u(i: int) -> int:
        return i + sum(1 for c in text[:i] if ord(c) > 0xFFFF)
    return [[u(a), u(b), raw] for a, b, raw in spans if b <= len(text)]


def glossed(r: dict, te: str, se: str, nid: str | None) -> dict:
    """An example's glossary spans: {"te": …, "se": …} (Builder.corrected)."""
    g = r.get("_g") or {}
    out = {"te": utf16_spans(g.get("te"), te), "se": utf16_spans((g.get("kbe") or {}).get(nid) if nid else None, se)}
    return {k: v for k, v in out.items() if v}


class DayDocs:
    """A day's search documents, collected for MonthIndex.add in their order."""

    def __init__(self):
        self.items: list[tuple[list, int, list]] = []

    def add(self, doc: list, outlet_index: int, terms: list[tuple[str, str]]) -> None:
        self.items.append((doc, outlet_index, terms))


_WORKER: "Builder | None" = None   # the builder, as the forked worker processes inherit it


def _work_day(d: date) -> tuple[date, dict]:
    return d, _WORKER.compute_day(d)


class MonthIndex:
    """Documents of one month plus the inverted index over them."""

    def __init__(self):
        self.docs: list[list] = []
        self.codes: list[str] = []
        self.day_starts: list[list] = []
        self.postings: dict[str, list[int]] = defaultdict(list)
        self.forms: dict[str, str] = {}
        self.narr: dict[int, list[int]] = defaultdict(list)

    def add(self, doc: list, outlet_index: int, terms: list[tuple[str, str]]) -> None:
        i = len(self.docs)
        self.docs.append(doc)
        self.codes.append(CODES[outlet_index])
        for form, st in terms:
            if form != st:
                self.forms[form] = st
            p = self.postings[st]
            if not p or p[-1] != i:
                p.append(i)
        for k in doc[6]:
            self.narr[k].append(i)

    def write(self, sdir: Path) -> None:
        for b in range(0, len(self.docs), BLOCK):
            dump_gz(sdir / "d" / f"{b // BLOCK}.json.gz", self.docs[b:b + BLOCK])
        shards = [{"f": {}, "p": {}} for _ in range(NB)]
        for form, st in self.forms.items():
            shards[bucket(form)]["f"][form] = st
        for st, p in self.postings.items():
            shards[bucket(st)]["p"][st] = delta_encode(p)
        for b, shard in enumerate(shards):
            dump_gz(sdir / "i" / f"{b}.json.gz", shard)
        dump_gz(sdir / "k.json.gz", {str(k): delta_encode(v) for k, v in self.narr.items()})
        dump_gz(sdir / "m.json.gz", {"n": len(self.docs), "days": self.day_starts, "o": "".join(self.codes)})


def display_form(forms: Counter, key: str) -> str:
    """How to write a rising word: its dictionary form if the headlines used it, otherwise their
    commonest form; lower case unless nearly every use was capitalised (a name)."""
    same = Counter({f: c for f, c in forms.items() if f.lower().replace("ё", "е") == key})
    best = (same or forms).most_common(1)[0][0]
    capitalised = sum(c for f, c in forms.items() if f[:1].isupper())
    return best if capitalised >= 0.8 * sum(forms.values()) else best.lower()


class Builder:
    def __init__(self, out_dir: Path, base_url: str = ""):
        self.out = out_dir
        self.base_url = base_url.rstrip("/")
        self.outlets = load_outlets(include_disabled=True)
        self.oidx = {o.id: i for i, o in enumerate(self.outlets)}
        self.olang = {o.id: o.lang for o in self.outlets}
        self.ofetch = {o.id: o.fetch for o in self.outlets}
        self.omachine = {o.id: o for o in self.outlets if o.machine}
        self.narratives = load_lexicon()
        self.nidx = {n.id: i for i, n in enumerate(self.narratives)}
        self.lex = Lexicon(self.narratives)
        self.lex_fp = self.lex.fingerprint()
        self.glossary = Glossary()
        self.searches = feeds.load_searches()
        self.recent: set[date] = set()   # the days whose feed items the month builds keep (FEED_DAYS)
        self._day_keys: dict[date, str] = {}

    # ── per-record work ───────────────────────────────────────────────────────
    def is_machine(self, rec: dict) -> bool:
        """An item the outlet itself labels machine-written (`machine` in outlets.yaml): kept in the archive,
        marked, and left out of every count, share and analysis."""
        o = self.omachine.get(rec["o"])
        return bool(o and o.is_machine(rec))

    def narratives_of(self, rec: dict) -> tuple[list[int], dict[int, str]]:
        lang = self.olang.get(rec["o"], "ru")
        t, d = rec.get("t", ""), rec.get("d", "")
        ids = set(self.lex.find(t, lang, extra=d)) | set(self.lex.find(d, lang, extra=t))
        snippets = {}
        for nid, snip in (rec.get("kb") or {}).items():
            # Body matches were recorded with the lexicon of the day they were collected. Re-check the
            # snippet against today's patterns, so narrowing or removing a pattern cleans the archive.
            if nid in self.nidx and nid not in ids and nid in self.lex.find(snip, lang, extra=f"{t} {d}"):
                snippets[self.nidx[nid]] = snip
        ks = sorted({self.nidx[i] for i in ids} | set(snippets))
        return ks, snippets

    def corrected(self, rec: dict) -> dict:
        """The record with its machine translations run through the glossary (config/glossary.yaml). Where the
        glossary changed words, `_g` says where and what the model wrote ({"te"|"de": spans, "kbe": {id: spans}}),
        for the site to mark them."""
        fixed, where = {}, {}
        for field, src in (("te", "t"), ("de", "d")):
            if rec.get(field):
                en, spans = self.glossary.fix_spans(rec.get(src, ""), rec[field])
                if en != rec[field]:
                    fixed[field] = en
                if spans:
                    where[field] = spans
        if rec.get("kbe"):
            kbe, kspans = {}, {}
            for nid, en in rec["kbe"].items():
                kbe[nid], spans = self.glossary.fix_spans((rec.get("kb") or {}).get(nid, ""), en)
                if spans:
                    kspans[nid] = spans
            if kbe != rec["kbe"]:
                fixed["kbe"] = kbe
            if kspans:
                where["kbe"] = kspans
        if where:
            fixed["_g"] = where
        return {**rec, **fixed} if fixed else rec

    # ── months ────────────────────────────────────────────────────────────────
    def code_key(self) -> str:
        """What every day's and month's results depend on besides the articles: lexicon, glossary, outlets, code."""
        if not hasattr(self, "_code_key"):
            h = hashlib.sha1(f"{BUILD_VERSION}|{self.lex_fp}|{self.glossary.fingerprint()}|"
                             f"{[(o.id, o.machine) for o in self.outlets]}".encode())
            for src in ("build.py", "lexicon.py", "textproc.py", "glossary.py", "analysis.py", "feeds.py"):  # code too
                h.update((Path(__file__).parent / src).read_bytes())
            for cfg in ("countries.yaml", "feeds.yaml"):
                if (CONFIG_DIR / cfg).exists():
                    h.update((CONFIG_DIR / cfg).read_bytes())
            self._code_key = h.hexdigest()
        return self._code_key

    def day_key(self, d: date) -> str:
        if d not in self._day_keys:
            h = hashlib.sha1(self.code_key().encode())
            for p in sorted(day_dir(d).glob("*.jsonl")):
                h.update(p.name.encode())
                h.update(p.read_bytes())
            self._day_keys[d] = h.hexdigest()[:16]
        return self._day_keys[d]

    def month_key(self, month: str, days: list[date], prev_key: str) -> str:
        h = hashlib.sha1(f"{self.code_key()}|{prev_key}".encode())
        for d in days:
            h.update(self.day_key(d).encode())
        return h.hexdigest()[:16]

    def compute_day(self, d: date) -> dict:
        """One day's aggregates, stories, search documents and feed items: what depends on that day's articles
        alone (the feed items are kept whether or not the day is recent, so the cache does not depend on it)."""
        recs = []
        for oid in sorted(p.stem for p in day_dir(d).glob("*.jsonl")):
            if oid in self.oidx:
                recs.extend(self.corrected(r) for r in read_day(d, oid))
        recs.sort(key=lambda r: (r["p"], r["o"], r["u"]))
        docs, items = DayDocs(), []
        summary = self.day_aggregates(recs, docs, items)
        shown, stats = self.day_stories([r for r in recs if not self.is_machine(r)])
        summary["stories"] = stats
        return {"summary": summary, "shown": shown, "docs": docs.items, "feed": items}

    def day_results(self, days: list[date]) -> dict[date, dict]:
        """compute_day for each day, from the day cache where the day has not changed, the rest in parallel."""
        ddir = CACHE / "days"
        out, todo = {}, []
        for d in days:
            path = ddir / f"{d.isoformat()}.pkl.gz"
            if path.exists():
                try:
                    with gzip.open(path, "rb") as fh:
                        cached = pickle.load(fh)
                    if cached.get("key") == self.day_key(d):
                        out[d] = cached["result"]
                        continue
                except (OSError, EOFError, pickle.UnpicklingError, AttributeError):
                    pass
            todo.append(d)
        if todo:
            t0 = time.monotonic()
            jobs = min(JOBS, len(todo)) if "fork" in multiprocessing.get_all_start_methods() else 1
            if jobs > 1:  # (forked, the workers share the loaded lexicon, dictionaries and settings)
                global _WORKER
                _WORKER = self
                with ProcessPoolExecutor(max_workers=jobs, mp_context=multiprocessing.get_context("fork")) as pool:
                    fresh = dict(pool.map(_work_day, todo))
            else:
                fresh = {d: self.compute_day(d) for d in todo}
            log.info("%d of %d days worked out in %.1fs (%d processes)", len(todo), len(days),
                     time.monotonic() - t0, jobs)
            ddir.mkdir(parents=True, exist_ok=True)
            for d, result in fresh.items():
                with gzip.open(ddir / f"{d.isoformat()}.pkl.gz", "wb", compresslevel=1) as fh:
                    pickle.dump({"key": self.day_key(d), "result": result}, fh, protocol=pickle.HIGHEST_PROTOCOL)
            out.update(fresh)
        return out

    def prune_day_cache(self, months: list[str]) -> None:
        keep = set(months[-DAY_CACHE_MONTHS:])
        for path in (CACHE / "days").glob("*.pkl.gz"):
            if path.name[:7] not in keep:
                path.unlink()

    def build_month(self, month: str, days: list[date], history: dict, cdir: Path) -> dict:
        """Search index + digests for one month. `history` holds earlier days' aggregates."""
        t0 = time.monotonic()
        if cdir.exists():
            shutil.rmtree(cdir)
        sdir = cdir / "search" / month
        idx = MonthIndex()
        summary = {}
        results = self.day_results(days)
        for d in days:
            res = results.pop(d)
            idx.day_starts.append([d.isoformat(), len(idx.docs)])
            for doc, oi, terms in res["docs"]:
                idx.add(doc, oi, terms)
            summary[d.isoformat()] = res["summary"]
            if d in self.recent:
                dump_gz(cdir / "feed" / f"{d.isoformat()}.json.gz", res["feed"])
            dump_gz(cdir / "stories" / f"{d.isoformat()}.json.gz", res["shown"])
        idx.write(sdir)
        for d in days:  # digests need the rolling history, including this month's earlier days
            key = d.isoformat()
            history[key] = summary[key]
            dg = self.digest(d, history)
            # the examples behind each row, three quarters of a digest, apart: Today reads them when a row opens
            examples = {row["id"]: row.pop("ex") for row in dg["narratives"]}
            dump(cdir / "days" / f"{key}.ex.json", {nid: ex for nid, ex in examples.items() if ex})
            dump(cdir / "days" / f"{key}.json", dg)
        slim = {k: {kk: vv for kk, vv in v.items() if kk not in ("stem_ex", "posts")} for k, v in summary.items()}
        dump(cdir / "summary.json", slim)
        log.info("month %s: %d documents, %d stems, %.1fs", month, len(idx.docs), len(idx.postings),
                 time.monotonic() - t0)
        return slim

    def day_aggregates(self, recs: list[dict], idx: "MonthIndex", feed: list | None = None) -> dict:
        """The day's counts for digests, series and analyses; every record goes into the search index, and
        into `feed` (when given) as a feed item."""
        totals = Counter()
        listed = Counter()
        machine = Counter()
        framed = 0
        nar = defaultdict(Counter)
        df = {"ru": Counter(), "en": Counter()}
        posts = {"ru": defaultdict(list), "en": defaultdict(list)}   # word → the day's headlines using it
        heads = {"ru": 0, "en": 0}
        form_counts = {"ru": defaultdict(Counter), "en": defaultdict(Counter)}
        stem_ex = {"ru": {}, "en": {}}
        examples = defaultdict(list)
        voices = {"ru": {}, "en": {}}
        countries = defaultdict(Counter)
        tags, sections = defaultdict(Counter), defaultdict(Counter)
        gaz = analysis.gazetteer()
        for r in recs:
            o = r["o"]
            lang = self.olang.get(o, "ru")
            if self.is_machine(r):  # searchable, marked, and counted apart from everything else
                machine[o] += 1
                ks, snips = self.narratives_of(r)
                self.index_doc(idx, r, ks, snips, machine=True)
                continue
            totals[o] += 1
            v = analysis.voice(r["t"], lang)
            if v:
                name, kind, verb, _ = v
                e = voices[lang].setdefault(analysis.voice_key(name, kind),
                                            {"y": {}, "f": {}, "o": {}, "v": {}, "ex": self.example(r, None)})
                for field, val in (("y", kind), ("f", name), ("o", o), ("v", verb)):
                    e[field][val] = e[field].get(val, 0) + 1
            codes = gaz.find(f'{r["t"]} {r.get("d", "")}', lang)
            for code in codes:
                countries[code][o] += 1
            for tag in r.get("g") or []:
                tags[o][tag] += 1
            if r.get("s"):
                sections[o][r["s"]] += 1
            listed[o] += self.headline_only(r)
            ks, snips = self.narratives_of(r)
            for k in ks:
                nar[self.narratives[k].id][o] += 1
            if any(self.narratives[k].family == "framing" for k in ks):
                framed += 1
            kbe = r.get("kbe") or {}
            stems = self.index_doc(idx, r, ks, snips)
            if feed is not None:
                feed.append(self.feed_item(r, ks, codes, stems))
            # rising words: in how many of the day's headlines each word (lemma) occurs, and which
            n = heads[lang]
            heads[lang] += 1
            seen = set()
            for _, surface, key in headline_words(r["t"]):
                form_counts[lang][key][surface] += 1
                if key in seen:
                    continue
                seen.add(key)
                df[lang][key] += 1
                posts[lang][key].append(n)
                if key not in stem_ex[lang] or (not stem_ex[lang][key].get("te") and r.get("te")):
                    stem_ex[lang][key] = self.example(r, None)
            for k in ks:  # narrative examples
                ex = examples[self.narratives[k].id]
                if len(ex) < 40:
                    ex.append(self.example(r, snips.get(k), kbe.get(self.narratives[k].id), self.narratives[k].id))
        chosen = {}
        for nid, exs in examples.items():
            by_outlet, picked = set(), []
            for ex in sorted(exs, key=lambda e: e.get("s") is not None):  # visible matches first
                if ex["o"] not in by_outlet:
                    picked.append(ex)
                    by_outlet.add(ex["o"])
                if len(picked) >= EXAMPLES:
                    break
            chosen[nid] = picked
        forms = {lang: {k: display_form(c, k) for k, c in fc.items() if df[lang][k] >= RISING_MIN[lang]}
                 for lang, fc in form_counts.items()}
        return {"totals": dict(totals), "listed": {o: v for o, v in listed.items() if v}, "framed": framed,
                "machine": dict(machine),
                "nar": {k: dict(v) for k, v in nar.items()},
                "df": {lang: dict(c) for lang, c in df.items()}, "forms": forms,
                "examples": chosen, "stem_ex": stem_ex, "voices": voices,
                "countries": {k: dict(v) for k, v in countries.items()},
                "tags": {o: dict(c) for o, c in tags.items()}, "sections": {o: dict(c) for o, c in sections.items()},
                "posts": {lang: {k: v for k, v in p.items() if len(v) >= RISING_MIN[lang]} for lang, p in posts.items()}}

    def index_doc(self, idx: "MonthIndex", r: dict, ks: list[int], snips: dict[int, str], machine: bool = False):
        """Add one record to the month's search index."""
        o = r["o"]
        ts = int(parse_dt(r["p"]).timestamp())
        lead = r.get("d", "")
        kbe = r.get("kbe") or {}
        doc = [self.oidx[o], ts, r["t"], r.get("te", ""), truncate(lead, SEARCH_LEAD), r["u"], ks,
               {str(k): v for k, v in snips.items()}, r.get("h", ""), (r.get("r") or "")[:10], r.get("a", ""),
               self.headline_only(r), r.get("w", 0),
               # then, where there are any: the Internet Archive's copy that was read, the lead's
               # translation, the snippets' translations, and 1 for an item the outlet labels machine-written
               r.get("ar", ""), doc_de := truncate(r.get("de", ""), SEARCH_LEAD),
               {str(k): kbe[self.narratives[k].id] for k in snips if self.narratives[k].id in kbe},
               int(machine), self.glossed_doc(r, doc_de, snips)]
        while len(doc) > 13 and not doc[-1]:
            doc.pop()
        text = " ".join(x for x in (r["t"], lead, r.get("te", ""), r.get("de", "")) if x)
        terms = index_terms(text)
        idx.add(doc, self.oidx[o], terms)
        return {st for _, st in terms}

    def glossed_doc(self, r: dict, de: str, snips: dict[int, str]) -> dict:
        """Where the glossary changed the translations a search document carries: {"te"|"de": spans,
        "s": {narrative index: spans}} (glossed)."""
        if not r.get("_g"):
            return {}
        out = {f: sp for f, text in (("te", r.get("te", "")), ("de", de)) if (sp := utf16_spans(r["_g"].get(f), text))}
        s = {str(k): sp for k in snips
             if (sp := utf16_spans((r["_g"].get("kbe") or {}).get(self.narratives[k].id), (r.get("kbe") or {}).get(self.narratives[k].id, "")))}
        if s:
            out["s"] = s
        return out

    def feed_item(self, r: dict, ks: list[int], codes, stems: set[str]) -> dict:
        """What the feeds need of one article: its text, and which framings, countries and saved searches it is in."""
        item = {k: r[k] for k in ("id", "o", "p", "t", "u", "te", "d", "de", "ar") if r.get(k)}
        item["k"] = [self.narratives[k].id for k in ks]
        item["c"] = sorted(codes)
        item["q"] = [s.id for s in self.searches if s.matches(stems)]
        return item

    def headline_only(self, r: dict) -> int:
        """1 for an outlet whose pages Woland reads, when this article's page has not been read (yet)."""
        return int(r.get("via") == "feed" and self.ofetch.get(r["o"], False))

    def example(self, r: dict, snippet: str | None, snippet_en: str | None = None, nid: str | None = None) -> dict:
        ex = {"o": r["o"], "t": r["t"], "u": r["u"], "p": r["p"][11:16], "id": r["id"],
              "h": r.get("h", ""), "r": (r.get("r") or "")[:10], "w": r.get("w", 0)}
        if r.get("te"):
            ex["te"] = r["te"]
        if r.get("ar"):
            ex["ar"] = r["ar"]
        if self.headline_only(r):
            ex["f"] = 1
        if snippet:
            ex["s"] = snippet
            if snippet_en:
                ex["se"] = snippet_en
        g = glossed(r, ex.get("te", ""), ex.get("se", ""), nid)
        if g:
            ex["g"] = g
        return ex

    def day_stories(self, recs: list[dict]) -> tuple[list[dict], dict]:
        """The day's stories that STORY_OUTLETS or more outlets published (woland/analysis.py): the largest ones
        to show, each outlet's first article in order of publication; and for the period views, which outlet
        published each story first and how many minutes after it the others did."""
        groups = analysis.stories(recs, [self.olang.get(r["o"], "ru") for r in recs])
        shown, led, joined, lags, pairs = [], Counter(), Counter(), defaultdict(list), defaultdict(Counter)
        sizes = Counter()
        for g in groups:
            first: dict[str, dict] = {}
            for i in g:
                first.setdefault(recs[i]["o"], recs[i])
            if len(first) < STORY_OUTLETS:
                continue
            sizes[len(first)] += 1
            members = list(first.values())
            t0 = parse_dt(members[0]["p"])
            leader = members[0]["o"]
            led[leader] += 1
            for r in members:
                joined[r["o"]] += 1
                if r["o"] != leader:
                    lags[r["o"]].append(round((parse_dt(r["p"]) - t0).total_seconds() / 60))
                    pairs[leader][r["o"]] += 1
            shown.append({"n": len(first), "a": len(g), "m": [
                {k: v for k, v in (("o", r["o"]), ("p", r["p"][11:16]), ("t", r["t"]), ("te", r.get("te")),
                                   ("u", r["u"])) if v} for r in members]})
        shown.sort(key=lambda st: (-st["n"], st["m"][0]["p"]))
        stats = {"sizes": dict(sizes), "led": dict(led), "joined": dict(joined), "lags": dict(lags),
                 "pairs": {k: dict(v) for k, v in pairs.items()}}
        return shown[:STORIES_SHOWN], stats

    # ── the Analysis page ─────────────────────────────────────────────────────
    def write_analysis(self, days: list[date]):
        """voices, stories, countries and tags over each period (WINDOWS) of completed days."""
        through = self.complete_through(days)
        done = [d for d in days if through and d.isoformat() <= through]
        out = self.out / "data" / "analysis"
        for w, n in WINDOWS.items():
            wdays = done[-n:] if n else done
            prev = done[-2 * n:-n] if n and len(done) >= 2 * n else []
            sums = [self._summary_for(d) for d in wdays]
            psums = [self._summary_for(d) for d in prev]
            head = {"window": w, "days": [d.isoformat() for d in wdays],
                    "totals": {o: sum(s.get("totals", {}).get(o, 0) for s in sums) for o in self.oidx}}
            dump(out / "voices" / f"{w}.json", {**head, **self.voices_of(sums)})
            dump(out / "stories" / f"{w}.json", {**head, **self.stories_of(sums)})
            dump(out / "countries" / f"{w}.json", {**head, **self.countries_of(sums, psums)})
            dump(out / "tags" / f"{w}.json", {**head, **self.tags_of(sums, psums)})
        dump(out / "verbs.json", {"kinds": analysis.KINDS, "verbs": dict(sorted(
            {analysis.VERB_BASE[f]: k for f, k in analysis.VERB_KIND.items()}.items()))})

    def voices_of(self, sums: list[dict]) -> dict:
        out, kinds = {}, {}
        for lang in ("ru", "en"):
            agg: dict[str, dict] = {}
            for i, s in enumerate(sums):
                for key, e in (s.get("voices") or {}).get(lang, {}).items():
                    a = agg.setdefault(key, {"y": Counter(), "f": Counter(), "o": Counter(), "v": Counter(),
                                             "d": [0] * len(sums), "ex": e["ex"], "exd": i})
                    for field in ("y", "f", "o", "v"):
                        a[field].update(e[field])
                    a["d"][i] += sum(e["o"].values())
                    a["ex"], a["exd"] = e["ex"], i      # the latest example
            rows = []
            by_kind = defaultdict(list)
            for key, a in agg.items():
                n = sum(a["d"])
                by_kind[a["y"].most_common(1)[0][0]].append((n, key, a))
            kinds[lang] = {}
            for kind, items in by_kind.items():
                kinds[lang][kind] = sum(n for n, _, _ in items)
                for n, key, a in sorted(items, key=lambda x: (-x[0], x[1]))[:VOICES_SHOWN]:
                    rows.append({"k": key, "name": a["f"].most_common(1)[0][0], "y": kind, "n": n,
                                 "o": dict(a["o"].most_common(8)), "v": dict(a["v"].most_common(6)), "d": a["d"],
                                 "ex": {**{k: v for k, v in a["ex"].items() if k in ("o", "t", "te", "u", "p", "id", "h", "r", "w", "ar", "f", "g")},
                                        "d": self._day_of(sums, a["exd"])}})
            rows.sort(key=lambda r: -r["n"])
            out[lang] = rows
        # how many headlines name a speaker, per outlet and kind of speaker
        by_outlet = defaultdict(Counter)
        for s in sums:
            for lang, entries in (s.get("voices") or {}).items():
                for e in entries.values():
                    kind = max(e["y"], key=e["y"].get)
                    for o, c in e["o"].items():
                        by_outlet[o][kind] += c
        return {"voices": out, "kinds": kinds, "outlets": {o: dict(c) for o, c in by_outlet.items()}}

    @staticmethod
    def _day_of(sums: list[dict], i: int) -> str | None:
        return sums[i].get("_day") if i < len(sums) else None

    def stories_of(self, sums: list[dict]) -> dict:
        led, joined, pairs, lags = Counter(), Counter(), defaultdict(Counter), defaultdict(list)
        per_day = []
        for s in sums:
            st = s.get("stories") or {}
            per_day.append({int(k): v for k, v in (st.get("sizes") or {}).items()})
            led.update(st.get("led") or {})
            joined.update(st.get("joined") or {})
            for o, v in (st.get("lags") or {}).items():
                lags[o].extend(v)
            for a, by in (st.get("pairs") or {}).items():
                pairs[a].update(by)

        def quartiles(v: list[int]) -> list[int] | None:
            if not v:
                return None
            v = sorted(v)
            return [v[len(v) // 4], v[len(v) // 2], v[(3 * len(v)) // 4]]
        return {"per_day": [sum(d.values()) for d in per_day],
                "big": [sum(c for k, c in d.items() if k >= 8) for d in per_day],
                "outlets": {o: {"j": joined[o], "l": led[o], "lag": quartiles(lags[o])} for o in joined},
                "pairs": {a: dict(b) for a, b in pairs.items()}, "min": STORY_OUTLETS}

    def countries_of(self, sums: list[dict], psums: list[dict]) -> dict:
        agg: dict[str, dict] = {}
        for i, s in enumerate(sums):
            for code, by in (s.get("countries") or {}).items():
                a = agg.setdefault(code, {"o": Counter(), "d": [0] * len(sums), "prev": 0})
                a["o"].update(by)
                a["d"][i] += sum(by.values())
        for s in psums:
            for code, by in (s.get("countries") or {}).items():
                if code in agg:
                    agg[code]["prev"] += sum(by.values())
        names = analysis.gazetteer().names
        return {"countries": {code: {"n": sum(a["d"]), "o": dict(a["o"]), "d": a["d"],
                                     "prev": a["prev"] if psums else None} for code, a in agg.items()},
                "names": {code: names[code] for code in agg if code in names}}

    def tags_of(self, sums: list[dict], psums: list[dict]) -> dict:
        def gather(ss, field):
            out = defaultdict(lambda: defaultdict(Counter))   # outlet → key → spelling → n
            for s in ss:
                for o, by in (s.get(field) or {}).items():
                    for tag, c in by.items():
                        out[o][normalize(tag).strip()][tag] += c
            return out
        res = {}
        for field, shown in (("tags", TAGS_SHOWN), ("sections", SECTIONS_SHOWN)):
            now, before = gather(sums, field), gather(psums, field)
            for o, keys in now.items():
                ranked = sorted(keys.items(), key=lambda kv: -sum(kv[1].values()))[:shown]
                res.setdefault(o, {})[field] = [
                    [spell.most_common(1)[0][0], sum(spell.values()),
                     sum(before[o][k].values()) if psums else None] for k, spell in ranked]
                tagged = sum(sum(s.get(field, {}).get(o, {}).values()) for s in sums)
                res[o][f"{field}_n"] = tagged
        return {"outlets": res}

    # ── digests ───────────────────────────────────────────────────────────────
    def digest(self, d: date, history: dict) -> dict:
        key = d.isoformat()
        today = history[key]
        total = sum(today["totals"].values())
        past = [history[k] for k in sorted(history) if k < key][-BASELINE_DAYS:]
        past_total = [sum(p["totals"].values()) for p in past]
        spark_keys = [k for k in sorted(history) if k <= key][-30:]

        def count(day, nid):
            return sum(day["nar"].get(nid, {}).values())

        def share(day, nid):
            t = sum(day["totals"].values())
            return (count(day, nid) / t) if t else 0.0

        narratives = []
        for n in self.narratives:
            cnt = count(today, n.id)
            s = cnt / total if total else 0.0
            base = base_n = None
            if past and sum(past_total):
                hits = sum(count(p, n.id) for p in past)
                base = hits / sum(past_total)
                base_n = hits / len(past)
            narratives.append({
                "id": n.id, "n": cnt, "share": round(s, 5),
                "base": None if base is None else round(base, 5),
                "base_n": None if base_n is None else round(base_n, 1),
                "by": today["nar"].get(n.id, {}),
                "spark": [round(share(history[k], n.id), 5) for k in spark_keys],
                "spark_n": [count(history[k], n.id) for k in spark_keys],
                "ex": today["examples"].get(n.id, []),
            })
        return {"date": key, "total": total, "totals": today["totals"], "listed": today.get("listed", {}),
                "framed": today.get("framed", 0), "narratives": narratives, "spark_from": spark_keys[0],
                "rising": self.rising(d, history), "days": len(past) + 1}

    def rising(self, d: date, history: dict) -> dict:
        """Words far more common in the day's headlines than over the previous two weeks, grouped into
        events: words that appear in largely the same headlines ("Сьюзан" and "Сарандон"; "Домодедово",
        "обслуживает" and "согласованию") are shown together."""
        key = d.isoformat()
        today = history[key]
        past = [history[k] for k in sorted(history) if k < key][-RISING_BASELINE:]
        out = {}
        for lang in ("ru", "en"):
            n_today = sum(v for o, v in today["totals"].items() if self.olang.get(o) == lang)
            if len(past) < 3 or not n_today:  # too little history for a meaningful baseline
                out[lang] = []
                continue
            n_past = sum(sum(v for o, v in p["totals"].items() if self.olang.get(o) == lang) for p in past) / len(past)
            if not n_past:
                out[lang] = []
                continue
            scored = []
            for w, c in today["df"][lang].items():
                if c < RISING_MIN[lang]:
                    continue
                base = sum(p["df"][lang].get(w, 0) for p in past) / len(past)
                score = ((c + 0.5) / n_today) / ((base + 0.5) / n_past)
                if score >= 2.0 and poisson_tail(c, (base + 0.5) * n_today / n_past) < RISING_P:
                    scored.append((score, c, base, w))
            scored.sort(reverse=True)
            posts = today["posts"][lang]
            # the headline shown for a word: the first of the day to use it (with a translation, if any has one)
            example = lambda w: (today["stem_ex"][lang].get(w) or {}).get("u")  # noqa: E731
            groups: list[list] = []
            for cand in scored[:40]:
                heads = set(posts.get(cand[3], ()))
                for g in groups:
                    lead = g[0][1]
                    # most of the same headlines; or the same first headline ("монастырский" and "Устуу Хурээ" on
                    # 7 October 2026 shared 9 of 16 headlines, but both were first used in the same one)
                    if len(heads & lead) >= 0.6 * min(len(heads), len(lead)) or \
                            (example(cand[3]) and example(cand[3]) == example(g[0][0][3])):
                        g.append((cand, heads))
                        break
                else:
                    groups.append([(cand, heads)])
            out[lang] = [self.rising_item(g, today, lang) for g in groups[:RISING_SHOWN]]
        return out

    def rising_item(self, group: list, today: dict, lang: str) -> dict:
        (score, c, base, lead), lead_heads = group[0]
        ex = today["stem_ex"][lang].get(lead)
        union = set().union(*(h for _, h in group))
        pos = {}
        for i, _, k in headline_words(ex["t"]) if ex else ():
            pos.setdefault(k, i)
        members = sorted(group, key=lambda m: pos.get(m[0][3], 999))
        words = [today["forms"][lang].get(m[0][3], m[0][3]) for m in members]
        label = words[0]
        for (m, prev) in zip(members[1:], members):
            a, b = pos.get(prev[0][3]), pos.get(m[0][3])
            label += (" " if a is not None and b is not None and b == a + 1 else " · ") + today["forms"][lang].get(m[0][3], m[0][3])
        # the search behind the link: the words that nearly all the event's headlines share
        common = [today["forms"][lang].get(m[0][3], m[0][3]) for m in members if len(m[1]) >= 0.8 * len(union)]
        return {"w": label, "k": lead, "words": words, "q": " ".join(common) or words[0],
                "n": c, "base": round(base, 2), "x": round(score, 1), "ex": ex}

    # ── assembly ──────────────────────────────────────────────────────────────
    def run(self):
        t0 = time.monotonic()
        days = [d for d in available_days() if d >= START_DATE]
        self.recent = set(days[-FEED_DAYS:])
        data = self.out / "data"
        self.copy_site()
        months: dict[str, list[date]] = defaultdict(list)
        for d in days:
            months[f"{d:%Y-%m}"].append(d)
        history: dict = {}
        prev_key = ""
        month_list = sorted(months)
        for month in month_list:
            mdays = months[month]
            key = self.month_key(month, mdays, prev_key)
            cdir = CACHE / month
            kfile = cdir / "key.txt"
            if kfile.exists() and kfile.read_text() == key and (cdir / "summary.json").exists():
                with open(cdir / "summary.json", encoding="utf-8") as fh:
                    history.update(json.load(fh))
                log.info("month %s: cached", month)
            else:
                self.build_month(month, mdays, history, cdir)
                kfile.write_text(key)
            if month in month_list[-SEARCH_MONTHS:]:
                shutil.copytree(cdir / "search", data / "search", dirs_exist_ok=True)
            shutil.copytree(cdir / "days", data / "days", dirs_exist_ok=True)
            shutil.copytree(cdir / "stories", data / "analysis" / "stories" / "day", dirs_exist_ok=True)
            prev_key = key
            # keep only what later digests need
            keep = sorted(history)[-max(BASELINE_DAYS, RISING_BASELINE, 30) - 1:]
            history = {k: history[k] for k in keep} if month != month_list[-1] else history
        cov = load_coverage()
        self.write_series(days, cov)
        self.write_examples(days)
        self.write_analysis(days)
        self.write_brief(days)
        self.write_feeds(days)
        self.write_meta(days, month_list[-SEARCH_MONTHS:], cov)
        self.prune_day_cache(month_list)
        log.info("site built in %.1fs → %s", time.monotonic() - t0, self.out)

    # ── the weekly brief ──────────────────────────────────────────────────────
    def weeks(self, days: list[date]) -> list[list[date]]:
        """The completed Monday-to-Sunday weeks, oldest first (the first one may start after its Monday)."""
        through = self.complete_through(days)
        by: dict[tuple, list[date]] = defaultdict(list)
        for d in days:
            by[tuple(d.isocalendar())[:2]].append(d)
        out = []
        for (y, w), ds in sorted(by.items()):
            sunday = date.fromisocalendar(y, w, 7)
            if through and sunday.isoformat() <= through:
                out.append(ds)
        return out

    def write_brief(self, days: list[date]):
        """data/brief/<YYYY-Www>.json for every completed week, data/brief/index.json listing them, and
        feeds/brief.xml: what rose, the week's events and biggest stories, who spoke, which countries, and what
        was not collected. Built from the same day summaries, digests and stories as the other pages."""
        weeks = self.weeks(days)
        out = self.out / "data" / "brief"
        index, entries = [], []
        for i, wdays in enumerate(weeks):
            base_days = [d for w in weeks[max(0, i - BRIEF_BASE_WEEKS):i] for d in w]
            prev_days = weeks[i - 1] if i else []
            b = self.brief(wdays, prev_days, base_days, days)
            dump(out / f"{b['week']}.json", b)
            index.append({"week": b["week"], "from": b["from"], "to": b["to"]})
            entries.append(b)
        index.reverse()
        dump(out / "index.json", index)
        updated = iso_utc()
        feed_entries = [feeds.text_entry(f"urn:woland:brief:{b['week']}",
                                         f"The week in the Russian state press, {b['from']} – {b['to']}",
                                         f"{b['to']}T23:59:59+03:00", self.href(f"brief.html?w={b['week']}"),
                                         self.brief_text(b)) for b in reversed(entries[-12:])]
        feeds.write_feed(self.out / "feeds" / "brief.xml", "urn:woland:feed:brief", "Woland — the week in the Russian state press",
                         "Every Monday: the framings that rose, the week's events and biggest stories, who spoke, which "
                         "countries were named, and what was not collected.", self.href("feeds/brief.xml"),
                         self.href("brief.html"), updated, feed_entries)

    def brief(self, wdays: list[date], prev_days: list[date], base_days: list[date], days: list[date]) -> dict:
        y, w, _ = wdays[0].isocalendar()
        sums = [self._summary_for(d) for d in wdays]
        psums = [self._summary_for(d) for d in prev_days]
        bsums = [self._summary_for(d) for d in base_days]
        total = lambda ss: sum(sum(s.get("totals", {}).values()) for s in ss)  # noqa: E731
        count = lambda ss, nid: sum(sum(s.get("nar", {}).get(nid, {}).values()) for s in ss)  # noqa: E731
        n_week, n_base = total(sums), total(bsums)
        rows = []
        for n in self.narratives:
            c = count(sums, n.id)
            share = c / n_week if n_week else 0
            base = count(bsums, n.id) / n_base if n_base else None
            rows.append({"id": n.id, "family": n.family, "n": c, "share": round(share, 5),
                         "base": None if base is None else round(base, 5),
                         "x": round(share / base, 2) if base else None})
        movers = [r for r in rows if r["x"] is not None and r["n"] >= BRIEF_MIN]
        rising = sorted((r for r in movers if r["x"] >= 1.2), key=lambda r: -r["x"])[:BRIEF_SHOWN]
        falling = sorted((r for r in movers if r["x"] <= 1 / 1.2), key=lambda r: r["x"])[:BRIEF_SHOWN // 2]
        top = sorted((r for r in rows if r["family"] == "framing"), key=lambda r: -r["n"])[:BRIEF_SHOWN]
        # the week's events: the days' rising words, the largest first
        events = []
        for d in wdays:
            p = self.out / "data" / "days" / f"{d.isoformat()}.json"
            if p.exists():
                dg = json.loads(p.read_text(encoding="utf-8"))
                for lang, items in (dg.get("rising") or {}).items():
                    for it in items:
                        ex = it.get("ex") or {}
                        events.append({"w": it["w"], "q": it["q"], "n": it["n"], "x": it["x"], "lang": lang,
                                       "d": d.isoformat(), "ex": {k: ex[k] for k in ("o", "t", "te", "u") if ex.get(k)}})
        events.sort(key=lambda e: (-e["n"], e["d"]))
        # the stories the most outlets ran, on any day of the week
        stories = []
        for d in wdays:
            p = self.out / "data" / "analysis" / "stories" / "day" / f"{d.isoformat()}.json.gz"
            if p.exists():
                with gzip.open(p, "rt", encoding="utf-8") as fh:
                    for st in json.load(fh)[:10]:
                        first = st["m"][0]
                        stories.append({"n": st["n"], "d": d.isoformat(), "o": [m["o"] for m in st["m"]],
                                        "first": {k: first[k] for k in ("o", "p", "t", "te", "u") if first.get(k)}})
        stories.sort(key=lambda st: (-st["n"], st["d"], st["first"].get("p", "")))
        voices = self.voices_of(sums)
        pvoices = self.voices_of(psums) if psums else {"voices": {}}
        prev_n = {(lang, v["k"]): v["n"] for lang, vs in pvoices["voices"].items() for v in vs}
        speakers = {lang: [{"name": v["name"], "y": v["y"], "n": v["n"], "prev": prev_n.get((lang, v["k"])) if psums else None,
                            "v": next(iter(v["v"]), None), "k": v["k"]}
                           for v in vs[:BRIEF_SHOWN]] for lang, vs in voices["voices"].items()}
        ctry = self.countries_of(sums, psums)
        names = ctry["names"]
        countries = sorted(({"c": c, "name": names.get(c, c), "n": v["n"], "prev": v["prev"]}
                            for c, v in ctry["countries"].items() if c != "RU"), key=lambda r: -r["n"])
        rose = sorted((r for r in countries if r["prev"] and r["n"] >= BRIEF_MIN and r["n"] >= 1.5 * r["prev"]),
                      key=lambda r: -r["n"] / r["prev"])
        idx = {d: i for i, d in enumerate(days)}
        gaps = {}
        for o, codes in getattr(self, "_cov_codes", {}).items():
            missing = [d.isoformat() for d in wdays if d in idx and idx[d] < len(codes) and codes[idx[d]] == "m"]
            if missing and next(o2.enabled for o2 in self.outlets if o2.id == o):
                gaps[o] = missing
        return {
            "week": f"{y}-W{w:02d}", "from": wdays[0].isoformat(), "to": wdays[-1].isoformat(), "days": len(wdays),
            "total": n_week, "prev_total": total(psums) if psums else None, "prev_days": len(prev_days),
            "base_weeks": len({tuple(d.isocalendar())[:2] for d in base_days}),
            "machine": sum(sum(s.get("machine", {}).values()) for s in sums),
            "outlets": {o: sum(s.get("totals", {}).get(o, 0) for s in sums) for o in self.oidx
                        if any(s.get("totals", {}).get(o) for s in sums)},
            "framed": sum(s.get("framed", 0) for s in sums),
            "rising": rising, "falling": falling, "top": top,
            "events": events[:BRIEF_SHOWN + 4], "stories": stories[:BRIEF_SHOWN], "speakers": speakers,
            "countries": countries[:BRIEF_SHOWN], "countries_rose": rose[:BRIEF_SHOWN // 2], "gaps": gaps,
        }

    def brief_text(self, b: dict) -> str:
        """The weekly brief as plain text, for the feed."""
        label = {n.id: n.label.get("en", n.id) for n in self.narratives}
        oname = {o.id: o.name for o in self.outlets}
        lines = [f"{b['total']:,} articles from {len(b['outlets'])} outlets"
                 + (f" ({b['total'] / b['prev_total'] * 100 - 100:+.0f}% on the week before)." if b.get("prev_total") else ".")]
        if b["rising"]:
            lines.append("Rose against the previous weeks: " + "; ".join(
                f"{label[r['id']]} ×{r['x']:.1f} ({r['n']:,} articles)" for r in b["rising"]) + ".")
        if b["events"]:
            lines.append("Events: " + "; ".join(
                f"{e['w']} ({e['d'][5:]}, {e['n']} headlines){' — ' + e['ex']['te'] if e['ex'].get('te') else ''}"
                for e in b["events"][:6]) + ".")
        if b["stories"]:
            lines.append("Stories the most outlets ran: " + "; ".join(
                f"{s['first'].get('te') or s['first'].get('t')} ({s['n']} outlets, {oname.get(s['first']['o'], s['first']['o'])} first)"
                for s in b["stories"][:5]) + ".")
        sp = (b["speakers"].get("ru") or [])[:5]
        if sp:
            lines.append("Quoted most: " + ", ".join(f"{v['name']} ({v['n']})" for v in sp) + ".")
        if b["countries"]:
            lines.append("Countries named most: " + ", ".join(f"{c['name']} ({c['n']:,})" for c in b["countries"][:6]) + ".")
        if b["gaps"]:
            lines.append("Not collected: " + "; ".join(f"{oname.get(o, o)} ({len(ds)} days)" for o, ds in b["gaps"].items()) + ".")
        if b.get("machine"):
            lines.append(f"Left out: {b['machine']:,} machine-written items.")
        lines.append("Pattern matches, not a reading of every article: see the Method page.")
        return "\n\n".join(lines)

    # ── feeds ─────────────────────────────────────────────────────────────────
    def feed_items(self, d: date) -> list[dict]:
        """A day's feed items: written by its month's build (FEED_DAYS), or worked out here when that month
        came from the cache and was built before the day counted as recent."""
        p = CACHE / f"{d:%Y-%m}" / "feed" / f"{d.isoformat()}.json.gz"
        if p.exists():
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        return self.day_results([d])[d]["feed"]

    def href(self, path: str) -> str:
        return f"{self.base_url}/{path}" if self.base_url else path

    def write_feeds(self, days: list[date]):
        """Atom feeds (woland/feeds.py) of the newest articles of every framing and topic, outlet, country and
        saved search over the last FEED_DAYS days; and data/feeds.json, the list the website shows."""
        recent = days[-FEED_DAYS:]
        items = [it for d in recent for it in self.feed_items(d)]
        items.sort(key=lambda it: it["p"], reverse=True)
        buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
        counts: dict[tuple[str, str], int] = Counter()
        for it in items:
            keys = [("outlet", it["o"])] + [("framing", k) for k in it.get("k", [])] + \
                   [("country", c) for c in it.get("c", [])] + [("search", q) for q in it.get("q", [])]
            for key in keys:
                counts[key] += 1
                if len(buckets[key]) < FEED_ENTRIES:
                    buckets[key].append(it)
        names = {o.id: o.name for o in self.outlets}
        nlabel = {n.id: n.label.get("en", n.id) for n in self.narratives}
        cname = analysis.gazetteer().names
        slabel = {s.id: s.label.get("en", s.id) for s in self.searches}
        sfirst = {s.id: s.any[0][0] for s in self.searches}
        updated = iso_utc()
        span = f"{recent[0].isoformat()} – {recent[-1].isoformat()}" if recent else ""
        listing: dict[str, dict] = {"outlet": {}, "framing": {}, "country": {}, "search": {}}
        targets = (
            [("outlet", o.id, f"outlet: {o.name}", f"outlets.html#{o.id}") for o in self.outlets if o.enabled] +
            [("framing", n.id, f"{n.family}: {nlabel[n.id]}", f"narratives.html#{n.id}") for n in self.narratives] +
            [("country", c, f"country: {cname.get(c, c)}", f"archive.html?q={cname.get(c, c)}")
             for (kind, c) in sorted(counts) if kind == "country"] +
            [("search", s.id, f"saved search: {slabel[s.id]}", f"archive.html?q={sfirst[s.id]}") for s in self.searches])
        for kind, key, title, page in targets:
            path = f"feeds/{kind}/{key}.xml"
            entries = [feeds.article_entry(it, names.get(it["o"], it["o"]), [nlabel[k] for k in it.get("k", []) if k in nlabel])
                       for it in buckets.get((kind, key), [])]
            feeds.write_feed(self.out / path, f"urn:woland:feed:{kind}:{key}", f"Woland — {title}",
                             f"The newest of the Russian state press's headlines, with English machine translations, "
                             f"{span} (Moscow days); at most {FEED_ENTRIES}.", self.href(path), self.href(page),
                             updated, entries)
            listing[kind][key] = counts.get((kind, key), 0)
        dump(self.out / "data" / "feeds.json", {
            "days": [d.isoformat() for d in recent], "entries": FEED_ENTRIES, "feeds": listing,
            "searches": [{"id": s.id, "label": s.label} for s in self.searches],
            "countries": {c: cname.get(c, c) for c in listing["country"]}})

    def copy_site(self):
        """Copy site/ to the output, expanding <!-- include:name --> from site/partials/."""
        src = ROOT / "site"
        if self.out.exists():
            shutil.rmtree(self.out)
        shutil.copytree(src, self.out, ignore=shutil.ignore_patterns("partials"))
        partials = {p.stem: p.read_text(encoding="utf-8") for p in (src / "partials").glob("*.html")}
        for page in self.out.glob("*.html"):
            html = page.read_text(encoding="utf-8")
            for name, body in partials.items():
                html = html.replace(f"<!-- include:{name} -->", body.strip())
            html = html.replace("</head>", preload_links(page.name, html, src) + "</head>", 1)
            page.write_text(html, encoding="utf-8", newline="\n")
        (self.out / ".nojekyll").write_text("")

    def write_examples(self, days: list[date], last: int = 8):
        """Every framing's and topic's examples from the digests of the last days, newest day first, each with
        its day: the Narratives page shows a dozen of them, and read two or three whole digests for them."""
        by_nid = defaultdict(list)
        for d in reversed(days[-last:]):
            key = d.isoformat()
            with open(self.out / "data" / "days" / f"{key}.ex.json", encoding="utf-8") as fh:
                for nid, exs in json.load(fh).items():
                    by_nid[nid] += [{**ex, "d": key} for ex in exs]
        for n in self.narratives:
            dump(self.out / "data" / "examples" / f"{n.id}.json", by_nid.get(n.id, []))

    def write_series(self, days: list[date], cov: dict):
        ids = [o.id for o in self.outlets]
        totals = {o: [0] * len(days) for o in ids}
        machine = {o: [0] * len(days) for o in ids}
        nar = {n.id: {o: [0] * len(days) for o in ids} for n in self.narratives}
        for i, d in enumerate(days):
            summary = self._summary_for(d)
            for o, v in summary.get("totals", {}).items():
                if o in totals:
                    totals[o][i] = v
            for o, v in summary.get("machine", {}).items():
                if o in machine:
                    machine[o][i] = v
            for nid, by in summary.get("nar", {}).items():
                if nid in nar:
                    for o, v in by.items():
                        if o in nar[nid]:
                            nar[nid][o][i] = v
        # (a day of machine-written items only is collected, not a gap)
        self._cov_codes = self.coverage_codes(days, {o: [a + b for a, b in zip(totals[o], machine[o])] for o in ids}, cov)   # (the weekly brief lists the gaps)
        # drop all-zero rows to keep the file small
        dump(self.out / "data" / "series.json", {
            "days": [d.isoformat() for d in days],
            "totals": {o: v for o, v in totals.items() if any(v)},
            "machine": {o: v for o, v in machine.items() if any(v)},   # machine-written items, not in totals
            "nar": {nid: {o: v for o, v in by.items() if any(v)} for nid, by in nar.items()},
            "cov": self._cov_codes,
            "gaps": self.feed_gaps(days),
        })

    def feed_gaps(self, days: list[date]) -> dict[str, dict[str, list[list[str]]]]:
        """Hours not collected, for outlets whose feeds may roll over between two readings (`gaps` in
        outlets.yaml): the silences between their stored articles longer than the outlet ever falls silent
        when read in time. {outlet: {day: [["HH:MM", "HH:MM"], …]}}, Moscow time."""
        out = {}
        for o in self.outlets:
            if not o.gaps:
                continue
            skip = re.compile(o.gaps["skip"]) if o.gaps.get("skip") else None
            times = sorted(parse_dt(r["p"]) for d in days for r in read_day(d, o.id)
                           if not (skip and skip.search(r["u"])))
            gaps = by_moscow_day(silences(times, float(o.gaps.get("minutes", 45))))
            if gaps:
                out[o.id] = gaps
        return out

    def coverage_codes(self, days: list[date], totals: dict, cov: dict) -> dict[str, str]:
        """One letter per outlet and day: c complete, p partial, f read from the outlet's feed only,
        m not collected at all (as opposed to collected and empty). A feed-only day with no articles means
        the feed was not read in time (TASS's Russian service before hourly reading began)."""
        out = {}
        for o in self.outlets:
            by = cov.get(o.id, {})
            busy = sorted(v for v in totals[o.id] if v)
            typical = busy[len(busy) // 2] if busy else 0
            row = []
            for i, d in enumerate(days):
                e = by.get(d.isoformat())
                n = totals[o.id][i]
                if e is None:
                    row.append("p" if n else "m")
                elif not n and (e.get("status") == "feed" or typical >= 20):
                    # nothing at all from an outlet that usually publishes dozens a day is a gap in
                    # collection, whatever the state file says (a backfill from the first day had no
                    # earlier days to compare with)
                    row.append("m")
                else:
                    row.append({"complete": "c", "partial": "p", "feed": "f"}.get(e.get("status"), "p"))
            if o.enabled or any(totals[o.id]) or any(ch != "m" for ch in row):
                out[o.id] = "".join(row)
        return out

    def complete_through(self, days: list[date]) -> str | None:
        """The last day that a full collection run has gathered after the day was over (Moscow time).
        Later days are still being collected: the nightly run reads the previous day only after
        midnight. Without any record of such runs (a fresh copy), every day before today counts."""
        if not days:
            return None
        ends = []
        for r in load_runs():
            if r.get("mode") not in ("daily", "backfill") or not r.get("at"):
                continue
            started = parse_dt(r["at"]).astimezone(MSK).date()
            reach = [date.fromisoformat(v["range"][1]) for v in r.get("outlets", {}).values() if v.get("range")]
            if reach:
                ends.append(min(started - timedelta(days=1), max(reach)))
        done = max(ends) if ends else today_msk() - timedelta(days=1)
        return min(done, days[-1]).isoformat()

    def _summary_for(self, d: date) -> dict:
        month = f"{d:%Y-%m}"
        if not hasattr(self, "_summary_cache"):
            self._summary_cache = {}
        if month not in self._summary_cache:
            with open(CACHE / month / "summary.json", encoding="utf-8") as fh:
                self._summary_cache[month] = json.load(fh)
        return {**self._summary_cache[month].get(d.isoformat(), {}), "_day": d.isoformat()}

    def write_meta(self, days: list[date], months: list[str], cov: dict):
        per_outlet = defaultdict(lambda: {"n": 0, "days": 0, "first": None, "last": None, "listed": 0, "machine": 0})
        for d in days:
            summary = self._summary_for(d)
            for o, v in summary.get("totals", {}).items():
                s = per_outlet[o]
                s["n"] += v
                s["days"] += 1
                s["first"] = s["first"] or d.isoformat()
                s["last"] = d.isoformat()
            for o, v in summary.get("listed", {}).items():
                per_outlet[o]["listed"] += v
            for o, v in summary.get("machine", {}).items():
                per_outlet[o]["machine"] += v
        outlets = []
        for o in self.outlets:
            info = o.public()
            info.update(per_outlet.get(o.id, {"n": 0, "days": 0, "first": None, "last": None, "listed": 0, "machine": 0}))
            outlets.append(info)
        compact_cov = {}
        for oid, by_day in cov.items():
            compact_cov[oid] = {d: [v.get("n", 0), v.get("found", 0), v.get("published"),
                                    {"complete": "c", "partial": "p", "feed": "f"}.get(v.get("status"), "p")]
                                for d, v in sorted(by_day.items())}
        dump(self.out / "data" / "coverage.json", compact_cov)
        runs = recent_runs(load_runs())
        repo = os.environ.get("GITHUB_REPOSITORY")
        contexts = load_contexts()
        dump(self.out / "data" / "meta.json", {
            "generated": iso_utc(), "version": BUILD_VERSION, "base_url": self.base_url,
            "repo": f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}" if repo else None,
            "start": START_DATE.isoformat(),
            "first": days[0].isoformat() if days else None,
            "last": days[-1].isoformat() if days else None,
            "complete_through": self.complete_through(days),
            "articles": sum(s["n"] for s in per_outlet.values()),
            "outlets": outlets,
            "narratives": [dict(n.public(), idx=i) for i, n in enumerate(self.narratives)],
            "contexts": contexts,
            "search": {"months": months, "nb": NB, "block": BLOCK, "codes": CODES,
                       "stop": sorted(STOP_RU | STOP_EN)},
            "lexicon": self.lex_fp,
            "glossary": len(self.glossary.entries),
            "runs": [{"at": r.get("at"), "mode": r.get("mode"), "seconds": r.get("seconds"),
                      "outlets": sorted(r.get("outlets", {})),
                      "new": sum(v.get("new", 0) for v in r.get("outlets", {}).values()),
                      "problems": {k: p for k, v in r.get("outlets", {}).items() if (p := run_problems(v))}}
                     for r in runs],
        })


IMPORT_RE = re.compile(r'^\s*(?:import|export)\b[^;]*?\bfrom\s*"(\./[^"]+)"', re.M | re.S)
# Data every page reads before it can show anything (core.js loadMeta), and those that some pages read right
# after it: fetching them while the scripts load saves a round trip or two on every first visit.
PAGE_DATA = {"index.html": ["series.json"], "narratives.html": ["series.json"],
             "outlets.html": ["series.json", "coverage.json"]}


def module_graph(entry: str, js_dir: Path) -> list[str]:
    """Every module `entry` imports, directly or through others (static imports only), in discovery order."""
    seen, todo = [], [entry]
    while todo:
        name = todo.pop(0)
        path = js_dir / name
        if name in seen or not path.exists():
            continue
        seen.append(name)
        todo += [m[2:] for m in IMPORT_RE.findall(path.read_text(encoding="utf-8"))]
    return seen


def preload_links(page: str, html: str, src: Path) -> str:
    """<link> tags that let the browser fetch a page's whole module tree and its first data at once, instead
    of discovering each module only after the one importing it has arrived (four round trips on Today)."""
    m = re.search(r'<script type="module" src="assets/js/([^"]+)"', html)
    if not m:
        return ""
    links = [f'<link rel="modulepreload" href="assets/js/{name}">'
             for name in module_graph(m.group(1), src / "assets" / "js")[1:]]
    for f in ["meta.json"] + PAGE_DATA.get(page, []):
        links.append(f'<link rel="preload" href="data/{f}" as="fetch" crossorigin>')
    return "".join(f"{link}\n" for link in links)


def build(out_dir: str = "_site", base_url: str = "") -> None:
    Builder(Path(out_dir), base_url).run()
