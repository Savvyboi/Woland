"""Headlines rewritten after publication (store.revise_day) and articles taken down (vanish.py): the last
weeks' of both, for the site.

A rewrite is what a listing (feed, sitemap or section page) shows as an article's headline when that listing
showed it differently before. The stored headline stays as first published; `rv` holds the rewrites. This
module gathers the records that have any, with a word-by-word comparison of the headline before and after,
and the records whose page answered 404 or 410 twice in a row (`va`, `vs`).
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from datetime import date

from .store import day_path

DAYS = 30        # the period shown
SHOWN = 400      # rewrites (and, apart, articles gone) listed, newest first
_TOKEN = re.compile(r"\s+|[^\s]+")


def word_diff(a: str, b: str) -> list[list[str]]:
    """[op, text] runs turning `a` into `b`, word by word: "=" kept, "-" removed, "+" added. Spaces go with
    the run before them."""
    ta, tb = _TOKEN.findall(a), _TOKEN.findall(b)
    out: list[list[str]] = []

    def put(op, text):
        if not text:
            return
        if out and out[-1][0] == op:
            out[-1][1] += text
        else:
            out.append([op, text])
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag == "equal":
            put("=", "".join(ta[i1:i2]))
        else:
            put("-", "".join(ta[i1:i2]))
            put("+", "".join(tb[j1:j2]))
    return out


def before_rewrite(rec: dict, via: str) -> str:
    """The headline `via` showed before its first rewrite: its baseline, else the stored headline."""
    return (rec.get("ls") or {}).get(via) or rec["t"]


def gather(days: list[date], outlets: list[str], is_machine, fix=lambda ru, en: en, through: str | None = None,
           machine_outlets: frozenset = frozenset()) -> dict:
    """The rewrites of articles filed under `days`, and per outlet how many of its articles were rewritten,
    counted over the days through `through` only (later days are still being collected). `is_machine(rec)`:
    items the outlet labels machine-written (of `machine_outlets`), listed but not counted. `fix(ru, en)`: the glossary's
    corrections to a translation."""
    items, rewritten, articles = [], Counter(), Counter()
    gone, vanished = [], Counter()
    for d in days:
        counted = through is None or d.isoformat() <= through
        for o in outlets:
            p = day_path(d, o)
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                if '"rv":' not in line and '"va":' not in line and o not in machine_outlets:
                    articles[o] += counted
                    continue
                rec = json.loads(line)
                if rec.get("va"):
                    g = {"o": o, "u": rec["u"], "id": rec["id"], "p": rec["p"][:16], "at": rec["va"], "s": rec["vs"],
                         "t": (rec["rv"][-1]["t"] if rec.get("rv") else rec["t"])}
                    en = rec["rv"][-1].get("te", "") if rec.get("rv") else rec.get("te", "")
                    if en:
                        g["te"] = fix(g["t"], en)
                    if is_machine(rec):
                        g["m"] = 1
                    else:
                        vanished[o] += 1
                    gone.append(g)
                if not rec.get("rv"):
                    articles[o] += counted and not is_machine(rec)
                    continue
                machine = is_machine(rec)
                if counted and not machine:
                    articles[o] += 1
                    rewritten[o] += 1
                last = rec["rv"][-1]
                was = before_rewrite(rec, last["via"])
                # translations: the stored headline's, where the rewrite is compared with it
                te0 = fix(rec["t"], rec.get("te", "")) if was == rec["t"] else ""
                item = {"o": o, "u": rec["u"], "id": rec["id"], "p": rec["p"][:16], "at": last["at"], "via": last["via"],
                        "was": was, "now": last["t"], "n": len(rec["rv"]), "diff": word_diff(was, last["t"])}
                if te0:
                    item["te0"] = te0
                if last.get("te"):
                    item["te1"] = fix(last["t"], last["te"])
                if rec.get("ar"):
                    item["ar"] = rec["ar"]
                if machine:
                    item["m"] = 1
                items.append(item)
    items.sort(key=lambda x: (x["at"], x["u"]), reverse=True)
    gone.sort(key=lambda x: (x["at"], x["u"]), reverse=True)
    return {"days": [days[0].isoformat(), days[-1].isoformat()] if days else [], "through": through, "items": items[:SHOWN],
            "total": len(items), "gone": gone[:SHOWN], "gone_total": len(gone),
            "outlets": {o: {"rewritten": rewritten[o], "articles": articles[o], **({"gone": vanished[o]} if vanished[o] else {})}
                        for o in outlets if articles[o]}}
