"""At home and abroad: how the outlets that write for Russian readers and those that write for readers abroad
(`audience` in config/outlets.yaml) differ, week by week.

For each completed week, two cohorts: the domestic and the foreign outlets that were collected on every day of
it (an outlet with a day not collected at all would make its cohort's shares depend on the gap). Over the
articles of each cohort, machine-written items left out as everywhere else:

* the **divergence**: the Jensen–Shannon distance between the two cohorts' framing profiles (how the framing
  matches of each are spread over the framings), base 2, so 0 when the two are spread identically and 1 when
  they share no framing at all; None when a cohort has no framing match;
* the **silence gaps**: framings, topics and countries that take a clear share of one cohort's articles and
  little or none of the other's, the largest gap first.

The cohorts write in different languages and are matched by different word lists (the Russian and the English
patterns of each framing, the Russian and the English names of each country), so a gap can also be a
difference between the word lists: every item links to its articles.
"""
from __future__ import annotations

import math
from collections import Counter

GAP_MIN = 5          # articles the louder cohort must have for an item to be listed as a gap
GAP_RATIO = 4.0      # its share must be at least this many times the other cohort's (smoothed)
GAPS_SHOWN = 8       # per direction
SMOOTH = 0.5         # added to each count before the ratio, so that a zero does not make every ratio infinite


def js_distance(p: dict, q: dict) -> float | None:
    """Jensen–Shannon distance (base 2) between two distributions given as counts or weights by key: 0 for the
    same distribution, 1 for two with nothing in common. None when either is empty."""
    sp, sq = sum(p.values()), sum(q.values())
    if sp <= 0 or sq <= 0:
        return None
    div = 0.0
    for k in set(p) | set(q):
        a, b = p.get(k, 0) / sp, q.get(k, 0) / sq
        m = (a + b) / 2
        if a:
            div += a / 2 * math.log2(a / m)
        if b:
            div += b / 2 * math.log2(b / m)
    return round(math.sqrt(max(0.0, min(1.0, div))), 4)


def complete_outlets(codes: dict[str, str], day_index: dict, wdays: list) -> set[str]:
    """The outlets collected on every day of the week (coverage codes: m = not collected at all)."""
    out = set()
    for o, row in codes.items():
        if all(day_index.get(d) is not None and day_index[d] < len(row) and row[day_index[d]] != "m" for d in wdays):
            out.add(o)
    return out


def cohort(sums: list[dict], outlets: set[str]) -> dict:
    """Articles, framing and topic matches, and countries named, over the given outlets' records."""
    n, nar, ctry = 0, Counter(), Counter()
    for s in sums:
        n += sum(v for o, v in (s.get("totals") or {}).items() if o in outlets)
        for nid, by in (s.get("nar") or {}).items():
            nar[nid] += sum(v for o, v in by.items() if o in outlets)
        for code, by in (s.get("countries") or {}).items():
            ctry[code] += sum(v for o, v in by.items() if o in outlets)
    return {"n": n, "nar": +nar, "countries": +ctry}


def gaps(dom: dict, fgn: dict, items: list[tuple[str, str, int, int]]) -> dict:
    """items: (kind, key, domestic count, foreign count). The ones far louder on one side than on the other."""
    out = {"domestic": [], "foreign": []}
    if not dom["n"] or not fgn["n"]:
        return out
    for kind, key, kd, kf in items:
        sd, sf = (kd + SMOOTH) / dom["n"], (kf + SMOOTH) / fgn["n"]
        row = {"kind": kind, "id": key, "dn": kd, "fn": kf,
               "ds": round(kd / dom["n"], 5), "fs": round(kf / fgn["n"], 5)}
        if kd >= GAP_MIN and sd >= GAP_RATIO * sf:
            out["domestic"].append({**row, "x": round(sd / sf, 1)})
        elif kf >= GAP_MIN and sf >= GAP_RATIO * sd:
            out["foreign"].append({**row, "x": round(sf / sd, 1)})
    for side in out:
        out[side].sort(key=lambda r: (-r["x"], r["kind"], r["id"]))
        out[side] = out[side][:GAPS_SHOWN]
    return out


def week(sums: list[dict], audience: dict[str, str], complete: set[str], framings: set[str], topics: set[str]) -> dict:
    """One week's comparison. audience: outlet → domestic | foreign; complete: the outlets collected every day."""
    members = {side: sorted(o for o, a in audience.items() if a == side and o in complete) for side in ("domestic", "foreign")}
    left_out = sorted(o for o in audience if o not in complete and any((s.get("totals") or {}).get(o) for s in sums))
    dom, fgn = cohort(sums, set(members["domestic"])), cohort(sums, set(members["foreign"]))
    fd = {k: v for k, v in dom["nar"].items() if k in framings}
    ff = {k: v for k, v in fgn["nar"].items() if k in framings}
    items = [("framing" if nid in framings else "topic", nid, dom["nar"].get(nid, 0), fgn["nar"].get(nid, 0))
             for nid in sorted(framings | topics)]
    items += [("country", c, dom["countries"].get(c, 0), fgn["countries"].get(c, 0))
              for c in sorted(set(dom["countries"]) | set(fgn["countries"])) if c != "RU"]
    return {
        "outlets": members, "left_out": left_out,
        "n": {"domestic": dom["n"], "foreign": fgn["n"]},
        "framed": {"domestic": sum(fd.values()), "foreign": sum(ff.values())},
        "jsd": js_distance(fd, ff),
        "gaps": gaps(dom, fgn, items),
    }
