"""Building the static website into _site/.

    _site/                       copy of site/ (HTML, CSS, JS)
    _site/data/meta.json         outlets, narratives, date range, the last completed day, run health
    _site/data/series.json       daily counts per outlet and per narrative per outlet; collection status
    _site/data/coverage.json     collection details for every outlet and day
    _site/data/days/<date>.json  the daily digest: narratives, rising words; <date>.ex.json: its examples
    _site/data/examples/<id>.json  each narrative's examples of the last days (the Narratives page)
    _site/data/search/…          a static full-text index, one folder per month (gzip files)

Months are cached in .cache/build/<YYYY-MM>/ and only rebuilt when their articles, the previous
month, the lexicon, the translation glossary or this builder change: a daily build only redoes the
current month.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import math
import os
import re
import shutil
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path

from .config import ROOT, START_DATE, load_contexts, load_lexicon, load_outlets
from .glossary import Glossary
from .lexicon import Lexicon
from .store import available_days, day_dir, load_coverage, load_runs, read_day
from .textproc import STOP_EN, STOP_RU, headline_words, index_terms
from .util import MSK, iso_utc, parse_dt, today_msk, truncate

log = logging.getLogger("woland.build")

BUILD_VERSION = "6"
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
        self.narratives = load_lexicon()
        self.nidx = {n.id: i for i, n in enumerate(self.narratives)}
        self.lex = Lexicon(self.narratives)
        self.lex_fp = self.lex.fingerprint()
        self.glossary = Glossary()

    # ── per-record work ───────────────────────────────────────────────────────
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
        """The record with its machine translations run through the glossary (config/glossary.yaml)."""
        fixed = {}
        for field, src in (("te", "t"), ("de", "d")):
            if rec.get(field):
                en = self.glossary.fix(rec.get(src, ""), rec[field])
                if en != rec[field]:
                    fixed[field] = en
        if rec.get("kbe"):
            kbe = {nid: self.glossary.fix((rec.get("kb") or {}).get(nid, ""), en) for nid, en in rec["kbe"].items()}
            if kbe != rec["kbe"]:
                fixed["kbe"] = kbe
        return {**rec, **fixed} if fixed else rec

    # ── months ────────────────────────────────────────────────────────────────
    def month_key(self, month: str, days: list[date], prev_key: str) -> str:
        h = hashlib.sha1(f"{BUILD_VERSION}|{self.lex_fp}|{self.glossary.fingerprint()}|{prev_key}|"
                         f"{[o.id for o in self.outlets]}".encode())
        for src in ("build.py", "lexicon.py", "textproc.py", "glossary.py"):  # code changes invalidate the cache too
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
                    recs.extend(self.corrected(r) for r in read_day(d, oid))
            recs.sort(key=lambda r: (r["p"], r["o"], r["u"]))
            idx.day_starts.append([d.isoformat(), len(idx.docs)])
            summary[d.isoformat()] = self.day_aggregates(recs, idx)
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

    def day_aggregates(self, recs: list[dict], idx: "MonthIndex") -> dict:
        totals = Counter()
        listed = Counter()
        framed = 0
        nar = defaultdict(Counter)
        df = {"ru": Counter(), "en": Counter()}
        posts = {"ru": defaultdict(list), "en": defaultdict(list)}   # word → the day's headlines using it
        heads = {"ru": 0, "en": 0}
        form_counts = {"ru": defaultdict(Counter), "en": defaultdict(Counter)}
        stem_ex = {"ru": {}, "en": {}}
        examples = defaultdict(list)
        for r in recs:
            o = r["o"]
            lang = self.olang.get(o, "ru")
            totals[o] += 1
            listed[o] += self.headline_only(r)
            ks, snips = self.narratives_of(r)
            for k in ks:
                nar[self.narratives[k].id][o] += 1
            if any(self.narratives[k].family == "framing" for k in ks):
                framed += 1
            ts = int(parse_dt(r["p"]).timestamp())
            lead = r.get("d", "")
            kbe = r.get("kbe") or {}
            doc = [self.oidx[o], ts, r["t"], r.get("te", ""), truncate(lead, SEARCH_LEAD), r["u"], ks,
                   {str(k): v for k, v in snips.items()}, r.get("h", ""), (r.get("r") or "")[:10], r.get("a", ""),
                   self.headline_only(r), r.get("w", 0),
                   # then, where there are any: the Internet Archive's copy that was read, the lead's
                   # translation, the snippets' translations
                   r.get("ar", ""), truncate(r.get("de", ""), SEARCH_LEAD),
                   {str(k): kbe[self.narratives[k].id] for k in snips if self.narratives[k].id in kbe}]
            while len(doc) > 13 and not doc[-1]:
                doc.pop()
            text = " ".join(x for x in (r["t"], lead, r.get("te", ""), r.get("de", "")) if x)
            idx.add(doc, self.oidx[o], index_terms(text))
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
                    ex.append(self.example(r, snips.get(k), kbe.get(self.narratives[k].id)))
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
                "nar": {k: dict(v) for k, v in nar.items()},
                "df": {lang: dict(c) for lang, c in df.items()}, "forms": forms,
                "examples": chosen, "stem_ex": stem_ex,
                "posts": {lang: {k: v for k, v in p.items() if len(v) >= RISING_MIN[lang]} for lang, p in posts.items()}}

    def headline_only(self, r: dict) -> int:
        """1 for an outlet whose pages Woland reads, when this article's page has not been read (yet)."""
        return int(r.get("via") == "feed" and self.ofetch.get(r["o"], False))

    def example(self, r: dict, snippet: str | None, snippet_en: str | None = None) -> dict:
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
        return ex

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
            groups: list[list] = []
            for cand in scored[:40]:
                heads = set(posts.get(cand[3], ()))
                for g in groups:
                    lead = g[0][1]
                    if len(heads & lead) >= 0.6 * min(len(heads), len(lead)):
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
        cov = load_coverage()
        self.write_series(days, cov)
        self.write_examples(days)
        self.write_meta(days, month_list[-SEARCH_MONTHS:], cov)
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
            "cov": self.coverage_codes(days, totals, cov),
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
        return self._summary_cache[month].get(d.isoformat(), {})

    def write_meta(self, days: list[date], months: list[str], cov: dict):
        per_outlet = defaultdict(lambda: {"n": 0, "days": 0, "first": None, "last": None, "listed": 0})
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
        outlets = []
        for o in self.outlets:
            info = o.public()
            info.update(per_outlet.get(o.id, {"n": 0, "days": 0, "first": None, "last": None, "listed": 0}))
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


def build(out_dir: str = "_site", base_url: str = "") -> None:
    Builder(Path(out_dir), base_url).run()
