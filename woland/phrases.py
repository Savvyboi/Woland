"""Synchronized phrasing: rare word sequences that several outlets use within hours of each other.

A research aid for TASK-012 (looking for *temniki*, the editorial directives that hand outlets the same
wording), not a finding. Nearly every phrase this lists is ordinary coverage: outlets quoting the same
statement, rewording the same agency report, naming the same event. Read the articles before drawing
anything from it. `python -m woland phrases --day YYYY-MM-DD` prints a day's list for review.

How a phrase is found:
- the Russian outlets' headlines and leads are cut into words (lower case, ё → е, stop words, numbers and
  one-letter words left out) and each word to its Snowball stem, so that word forms count alike;
- every run of 3 to 5 such words is a phrase; a phrase that occurred, in 3 outlets or more, on more than
  BACKGROUND_MAX of the BACKGROUND_DAYS days before is common wording ("президент России Владимир Путин
  заявил") and left out;
- a phrase is listed when MIN_OUTLETS distinct outlets used it within WINDOW_HOURS of the first, in
  articles of at least MIN_STORIES different stories of the day (analysis.stories), unless most of them
  credit the same news agency (a reprint);
- of phrases found in the same articles, only the longest is kept.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from .textproc import is_stop, stem
from .util import normalize, parse_dt

NGRAMS = (3, 4, 5)
WINDOW_HOURS = 6
MIN_OUTLETS = 4
MIN_STORIES = 3
BACKGROUND_DAYS = 30
BACKGROUND_MAX = 1     # days of the background a rare phrase may have occurred on
BACKGROUND_OUTLETS = 3  # outlets a phrase must reach in a day to count as occurring in the background
_WORD = re.compile(r"[^\W_]+")
# a news agency an article credits: articles that mostly credit the same one are a reprint, not a choice
_AGENCY = re.compile(r"(?<![\w])(ТАСС|РИА Новости|Интерфакс|РБК|ПРАЙМ|Reuters|Bloomberg|AFP|AP)(?![\w])")


def words(text: str) -> list[tuple[str, int, int]]:
    """(stem, start, end) of the words that count, in `text`."""
    out = []
    for m in _WORD.finditer(text):
        form = normalize(m.group())
        if form.isdigit() or len(form) < 2 or is_stop(form):
            continue
        out.append((stem(form), m.start(), m.end()))
    return out


def text_of(rec: dict) -> str:
    return f"{rec['t']}. {rec.get('d', '')}" if rec.get("d") else rec["t"]


def grams(rec: dict) -> dict[tuple, tuple[int, int]]:
    """The record's phrases, each with where it first occurs in text_of(rec)."""
    ws = words(text_of(rec))
    out = {}
    for n in NGRAMS:
        for i in range(len(ws) - n + 1):
            g = tuple(w for w, _, _ in ws[i:i + n])
            if g not in out:
                out[g] = (ws[i][1], ws[i + n - 1][2])
    return out


def common(day_recs: list[dict]) -> set[tuple]:
    """A day's phrases used by BACKGROUND_OUTLETS outlets or more: the background for the days after."""
    by = defaultdict(set)
    for r in day_recs:
        for g in grams(r):
            by[g].add(r["o"])
    return {g for g, os in by.items() if len(os) >= BACKGROUND_OUTLETS}


def background(days_common: list[set[tuple]]) -> Counter:
    """How many of the earlier days each phrase occurred on."""
    c = Counter()
    for s in days_common:
        c.update(s)
    return c


def clusters(recs: list[dict], bg: Counter, story_of: dict[str, int] | None = None) -> list[dict]:
    """The listed phrases among `recs` (Russian records of one day, or of a day and the hours after it):
    {"phrase", "key", "first": {...}, "adopters": [{... "lag": minutes}], "outlets", "stories"}, the
    phrases most outlets used first."""
    occ = defaultdict(list)
    spans = {}
    for i, r in enumerate(recs):
        for g, span in grams(r).items():
            if bg.get(g, 0) <= BACKGROUND_MAX:
                occ[g].append((parse_dt(r["p"]).timestamp(), r["o"], i))
                spans[(g, i)] = span
    found = []
    for g, v in occ.items():
        if len({o for _, o, _ in v}) < MIN_OUTLETS:
            continue
        v.sort()
        for k, (t0, _, _) in enumerate(v):
            first: dict[str, tuple] = {}
            for x in v[k:]:
                if x[0] > t0 + WINDOW_HOURS * 3600:
                    break
                first.setdefault(x[1], x)
            if len(first) < MIN_OUTLETS:
                continue
            members = list(first.values())
            if story_of is not None and len({story_of.get(recs[i]["u"], -1 - i) for _, _, i in members}) < MIN_STORIES:
                break
            credited = Counter(m.group(1) for m in (_AGENCY.search(text_of(recs[i])) for _, _, i in members) if m)
            if credited and credited.most_common(1)[0][1] * 2 > len(members):
                break  # a reprint of one agency's report
            found.append((g, members))
            break
    # of phrases found in the same articles, the longest
    found.sort(key=lambda x: -len(x[0]))
    seen, out = set(), []
    for g, members in found:
        ids = frozenset(i for _, _, i in members)
        if any(ids <= s for s in seen):
            continue
        seen.add(ids)
        t0, o0, i0 = members[0]
        a, b = spans[(g, i0)]
        item = lambda m: {"o": recs[m[2]]["o"], "p": recs[m[2]]["p"], "u": recs[m[2]]["u"],  # noqa: E731
                          "id": recs[m[2]].get("id", ""), "t": recs[m[2]]["t"],
                          "phrase": text_of(recs[m[2]])[slice(*spans[(g, m[2])])]}
        out.append({"key": " ".join(g), "phrase": text_of(recs[i0])[a:b], "first": item(members[0]),
                    "adopters": [{**item(m), "lag": round((m[0] - t0) / 60)} for m in members[1:]],
                    "outlets": len(members),
                    "stories": len({story_of.get(recs[i]["u"]) for _, _, i in members}) if story_of else None})
    out.sort(key=lambda c: (-c["outlets"], c["first"]["p"]))
    return out


def day_report(day: date, outlets: list[str], read_day, is_machine=lambda r: False) -> list[dict]:
    """The listed phrases of `day`, against the BACKGROUND_DAYS before it (the archive read with
    `read_day(day, outlet)`); machine-written items are left out."""
    from .analysis import stories

    def recs_of(d):
        return [r for o in outlets for r in read_day(d, o) if not is_machine(r)]
    bg = background([common(recs_of(day - timedelta(days=k))) for k in range(1, BACKGROUND_DAYS + 1)])
    recs = recs_of(day)
    story_of = {}
    for n, g in enumerate(stories(recs, ["ru"] * len(recs))):
        for i in g:
            story_of[recs[i]["u"]] = n
    return clusters(recs, bg, story_of)


def markdown(day: date, found: list[dict], names: dict[str, str], limit: int = 40) -> str:
    lines = [f"# Synchronized phrasing, {day.isoformat()}", "",
             f"{len(found)} phrases that {MIN_OUTLETS}+ outlets used within {WINDOW_HOURS} hours, in {MIN_STORIES}+ "
             "stories, and that were rare in the 30 days before. Most are ordinary coverage; read the articles.", ""]
    for c in found[:limit]:
        f = c["first"]
        lines.append(f"## «{c['phrase']}» — {c['outlets']} outlets, {c['stories']} stories")
        lines.append(f"- {f['p'][11:16]} **{names.get(f['o'], f['o'])}** (first): [{f['t']}]({f['u']})")
        for a in c["adopters"]:
            lines.append(f"- {a['p'][11:16]} {names.get(a['o'], a['o'])} (+{a['lag']} min): [{a['t']}]({a['u']})")
        lines.append("")
    return "\n".join(lines)
