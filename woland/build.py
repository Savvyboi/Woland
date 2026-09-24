"""Building the static website into _site/.

    _site/                       copy of site/ (HTML, CSS, JS)
    _site/data/meta.json         outlets, narratives, date range, run health
    _site/data/series.json       daily counts per outlet, and per narrative per outlet
    _site/data/coverage.json     collection status for every outlet and day
    _site/data/days/<date>.json  the daily digest: narratives, rising words, examples
    _site/data/search/…          a static full-text index, one folder per month (gzip files)

Months are cached in .cache/build/<YYYY-MM>/ and only rebuilt when their articles, the previous
month, the lexicon or this builder change: a daily build only redoes the current month.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shutil
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .config import ROOT, START_DATE, load_lexicon, load_outlets
from .lexicon import Lexicon
from .store import available_days, day_dir, load_coverage, load_runs, read_day
from .textproc import STOP_EN, STOP_RU, index_terms, is_stop, stem, tokens
from .util import iso_utc, parse_dt, truncate

log = logging.getLogger("woland.build")

BUILD_VERSION = "3"
NB = 128          # index buckets per month
BLOCK = 100       # documents per block file
BASELINE_DAYS = 28
RISING_BASELINE = 14
EXAMPLES = 6
SEARCH_LEAD = 180  # characters of the lead kept in search documents (the archive keeps up to 240)
# GitHub Pages sites must stay under 1 GB: publish the search index for the most recent months only.
# Older months remain in the repository's data/ folder.
SEARCH_MONTHS = int(os.environ.get("WOLAND_SEARCH_MONTHS", "18"))
CODES = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CACHE = ROOT / ".cache" / "build"


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


def delta_encode(nums: list[int]) -> list[int]:
    out, prev = [], 0
    for n in nums:
        out.append(n - prev)
        prev = n
    return out


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


class Builder:
    def __init__(self, out_dir: Path, base_url: str = ""):
        self.out = out_dir
        self.base_url = base_url.rstrip("/")
        self.outlets = load_outlets(include_disabled=True)
        self.oidx = {o.id: i for i, o in enumerate(self.outlets)}
        self.olang = {o.id: o.lang for o in self.outlets}
        self.ofetch = {o.id: o.fetch for o in self.outlets}
        self.narratives = load_lexicon()
        self.nidx = {n.id: i for i, n in enumerate(self.narratives)}
        self.lex = Lexicon(self.narratives)
        self.lex_fp = self.lex.fingerprint()

    # ── per-record work ───────────────────────────────────────────────────────
    def narratives_of(self, rec: dict) -> tuple[list[int], dict[int, str]]:
        lang = self.olang.get(rec["o"], "ru")
        ids = set(self.lex.find(rec.get("t", ""), lang)) | set(self.lex.find(rec.get("d", ""), lang))
        snippets = {}
        for nid, snip in (rec.get("kb") or {}).items():
            # Body matches were recorded with the lexicon of the day they were collected. Re-check the
            # snippet against today's patterns, so narrowing or removing a pattern cleans the archive.
            if nid in self.nidx and nid not in ids and nid in self.lex.find(snip, lang):
                snippets[self.nidx[nid]] = snip
        ks = sorted({self.nidx[i] for i in ids} | set(snippets))
        return ks, snippets

    # ── months ────────────────────────────────────────────────────────────────
    def month_key(self, month: str, days: list[date], prev_key: str) -> str:
        h = hashlib.sha1(f"{BUILD_VERSION}|{self.lex_fp}|{prev_key}|{[o.id for o in self.outlets]}".encode())
        for src in ("build.py", "lexicon.py", "textproc.py"):  # code changes invalidate the cache too
            h.update((Path(__file__).parent / src).read_bytes())
        for d in days:
            for p in sorted(day_dir(d).glob("*.jsonl")):
                h.update(p.name.encode())
                h.update(p.read_bytes())
        return h.hexdigest()[:16]

    def build_month(self, month: str, days: list[date], history: dict, cdir: Path) -> dict:
        """Search index + digests for one month. `history` holds earlier days' aggregates."""
        t0 = time.monotonic()
        if cdir.exists():
            shutil.rmtree(cdir)
        sdir = cdir / "search" / month
        idx = MonthIndex()
        summary = {}
        for d in days:
            recs = []
            for oid in sorted(p.stem for p in day_dir(d).glob("*.jsonl")):
                if oid in self.oidx:
                    recs.extend(read_day(d, oid))
            recs.sort(key=lambda r: (r["p"], r["o"], r["u"]))
            idx.day_starts.append([d.isoformat(), len(idx.docs)])
            summary[d.isoformat()] = self.day_aggregates(recs, idx)
        idx.write(sdir)
        for d in days:  # digests need the rolling history, including this month's earlier days
            key = d.isoformat()
            history[key] = summary[key]
            dump(cdir / "days" / f"{key}.json", self.digest(d, history))
        slim = {k: {kk: vv for kk, vv in v.items() if kk != "stem_ex"} for k, v in summary.items()}
        dump(cdir / "summary.json", slim)
        log.info("month %s: %d documents, %d stems, %.1fs", month, len(idx.docs), len(idx.postings),
                 time.monotonic() - t0)
        return slim

    def day_aggregates(self, recs: list[dict], idx: "MonthIndex") -> dict:
        totals = Counter()
        framed = 0
        nar = defaultdict(Counter)
        df = {"ru": Counter(), "en": Counter()}
        form_counts = {"ru": defaultdict(Counter), "en": defaultdict(Counter)}
        stem_ex = {"ru": {}, "en": {}}
        examples = defaultdict(list)
        for r in recs:
            o = r["o"]
            lang = self.olang.get(o, "ru")
            totals[o] += 1
            ks, snips = self.narratives_of(r)
            for k in ks:
                nar[self.narratives[k].id][o] += 1
            if any(self.narratives[k].family == "framing" for k in ks):
                framed += 1
            ts = int(parse_dt(r["p"]).timestamp())
            lead = r.get("d", "")
            doc = [self.oidx[o], ts, r["t"], r.get("te", ""), truncate(lead, SEARCH_LEAD), r["u"], ks,
                   {str(k): v for k, v in snips.items()}, r.get("h", ""), (r.get("r") or "")[:10], r.get("a", ""),
                   self.headline_only(r)]
            text = " ".join(x for x in (r["t"], r.get("d", ""), r.get("te", "")) if x)
            idx.add(doc, self.oidx[o], index_terms(text))
            # rising words: document frequency of stems in headlines
            seen = set()
            for t in tokens(r["t"]):
                if is_stop(t) or t.isdigit() or len(t) < 3:
                    continue
                st = stem(t)
                form_counts[lang][st][t] += 1
                if st in seen:
                    continue
                seen.add(st)
                df[lang][st] += 1
                if st not in stem_ex[lang] or (not stem_ex[lang][st].get("te") and r.get("te")):
                    stem_ex[lang][st] = self.example(r, None)
            for k in ks:  # narrative examples
                ex = examples[self.narratives[k].id]
                if len(ex) < 40:
                    ex.append(self.example(r, snips.get(k)))
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
        forms = {lang: {st: c.most_common(1)[0][0] for st, c in fc.items() if st in df[lang]}
                 for lang, fc in form_counts.items()}
        return {"totals": dict(totals), "framed": framed, "nar": {k: dict(v) for k, v in nar.items()},
                "df": {lang: dict(c) for lang, c in df.items()}, "forms": forms,
                "examples": chosen, "stem_ex": stem_ex}

    def headline_only(self, r: dict) -> int:
        """1 for an outlet whose pages Woland reads, when this article's page has not been read (yet)."""
        return int(r.get("via") == "feed" and self.ofetch.get(r["o"], False))

    def example(self, r: dict, snippet: str | None) -> dict:
        ex = {"o": r["o"], "t": r["t"], "u": r["u"], "p": r["p"][11:16], "id": r["id"]}
        if r.get("te"):
            ex["te"] = r["te"]
        if self.headline_only(r):
            ex["f"] = 1
        if snippet:
            ex["s"] = snippet
        return ex

    # ── digests ───────────────────────────────────────────────────────────────
    def digest(self, d: date, history: dict) -> dict:
        key = d.isoformat()
        today = history[key]
        total = sum(today["totals"].values())
        past = [history[k] for k in sorted(history) if k < key][-BASELINE_DAYS:]
        past_total = [sum(p["totals"].values()) for p in past]
        spark_days = [history[k] for k in sorted(history) if k <= key][-30:]

        def share(day, nid):
            t = sum(day["totals"].values())
            return (sum(day["nar"].get(nid, {}).values()) / t) if t else 0.0

        narratives = []
        for n in self.narratives:
            cnt = sum(today["nar"].get(n.id, {}).values())
            s = cnt / total if total else 0.0
            base = None
            if past and sum(past_total):
                base = sum(sum(p["nar"].get(n.id, {}).values()) for p in past) / sum(past_total)
            narratives.append({
                "id": n.id, "n": cnt, "share": round(s, 5),
                "base": None if base is None else round(base, 5),
                "by": today["nar"].get(n.id, {}),
                "spark": [round(share(x, n.id), 5) for x in spark_days],
                "ex": today["examples"].get(n.id, []),
            })
        return {"date": key, "total": total, "totals": today["totals"], "framed": today.get("framed", 0),
                "narratives": narratives, "rising": self.rising(d, history), "days": len(past) + 1}

    def rising(self, d: date, history: dict) -> dict:
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
            min_count = 6 if lang == "ru" else 3
            scored = []
            for st, c in today["df"][lang].items():
                if c < min_count:
                    continue
                base = sum(p["df"][lang].get(st, 0) for p in past) / len(past)
                score = ((c + 0.5) / n_today) / ((base + 0.5) / n_past)
                if score >= 2.0:
                    scored.append((score, c, base, st))
            scored.sort(reverse=True)
            items = []
            for score, c, base, st in scored[:15]:
                items.append({"w": today["forms"][lang].get(st, st), "n": c, "base": round(base, 2),
                              "x": round(score, 1), "ex": today["stem_ex"][lang].get(st)})
            out[lang] = items
        return out

    # ── assembly ──────────────────────────────────────────────────────────────
    def run(self):
        t0 = time.monotonic()
        days = [d for d in available_days() if d >= START_DATE]
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
            prev_key = key
            # keep only what later digests need
            keep = sorted(history)[-max(BASELINE_DAYS, RISING_BASELINE, 30) - 1:]
            history = {k: history[k] for k in keep} if month != month_list[-1] else history
        self.write_series(days)
        self.write_meta(days, month_list[-SEARCH_MONTHS:])
        log.info("site built in %.1fs → %s", time.monotonic() - t0, self.out)

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
            page.write_text(html, encoding="utf-8", newline="\n")
        (self.out / ".nojekyll").write_text("")

    def write_series(self, days: list[date]):
        ids = [o.id for o in self.outlets]
        totals = {o: [0] * len(days) for o in ids}
        nar = {n.id: {o: [0] * len(days) for o in ids} for n in self.narratives}
        for i, d in enumerate(days):
            summary = self._summary_for(d)
            for o, v in summary.get("totals", {}).items():
                if o in totals:
                    totals[o][i] = v
            for nid, by in summary.get("nar", {}).items():
                if nid in nar:
                    for o, v in by.items():
                        if o in nar[nid]:
                            nar[nid][o][i] = v
        # drop all-zero rows to keep the file small
        dump(self.out / "data" / "series.json", {
            "days": [d.isoformat() for d in days],
            "totals": {o: v for o, v in totals.items() if any(v)},
            "nar": {nid: {o: v for o, v in by.items() if any(v)} for nid, by in nar.items()},
        })

    def _summary_for(self, d: date) -> dict:
        month = f"{d:%Y-%m}"
        if not hasattr(self, "_summary_cache"):
            self._summary_cache = {}
        if month not in self._summary_cache:
            with open(CACHE / month / "summary.json", encoding="utf-8") as fh:
                self._summary_cache[month] = json.load(fh)
        return self._summary_cache[month].get(d.isoformat(), {})

    def write_meta(self, days: list[date], months: list[str]):
        cov = load_coverage()
        per_outlet = defaultdict(lambda: {"n": 0, "days": 0, "first": None, "last": None})
        for d in days:
            for o, v in self._summary_for(d).get("totals", {}).items():
                s = per_outlet[o]
                s["n"] += v
                s["days"] += 1
                s["first"] = s["first"] or d.isoformat()
                s["last"] = d.isoformat()
        outlets = []
        for o in self.outlets:
            info = o.public()
            info.update(per_outlet.get(o.id, {"n": 0, "days": 0, "first": None, "last": None}))
            outlets.append(info)
        compact_cov = {}
        for oid, by_day in cov.items():
            compact_cov[oid] = {d: [v.get("n", 0), v.get("found", 0), v.get("published"),
                                    {"complete": "c", "partial": "p", "feed": "f"}.get(v.get("status"), "p")]
                                for d, v in sorted(by_day.items())}
        dump(self.out / "data" / "coverage.json", compact_cov)
        runs = load_runs()[-12:]
        repo = os.environ.get("GITHUB_REPOSITORY")
        dump(self.out / "data" / "meta.json", {
            "generated": iso_utc(), "version": BUILD_VERSION, "base_url": self.base_url,
            "repo": f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}" if repo else None,
            "start": START_DATE.isoformat(),
            "first": days[0].isoformat() if days else None,
            "last": days[-1].isoformat() if days else None,
            "articles": sum(s["n"] for s in per_outlet.values()),
            "outlets": outlets,
            "narratives": [dict(n.public(), idx=i) for i, n in enumerate(self.narratives)],
            "search": {"months": months, "nb": NB, "block": BLOCK, "codes": CODES,
                       "stop": sorted(STOP_RU | STOP_EN)},
            "lexicon": self.lex_fp,
            "runs": [{"at": r.get("at"), "mode": r.get("mode"), "seconds": r.get("seconds"),
                      "new": sum(v.get("new", 0) for v in r.get("outlets", {}).values()),
                      "problems": {k: (v.get("aborted") or "; ".join(v.get("errors", [])) or v.get("error"))
                                   for k, v in r.get("outlets", {}).items()
                                   if v.get("aborted") or v.get("errors") or v.get("error")}}
                     for r in runs],
        })


def build(out_dir: str = "_site", base_url: str = "") -> None:
    Builder(Path(out_dir), base_url).run()
