"""DISARM exports: what Woland's framings, read as DISARM techniques (`disarm` in config/lexicon.yaml), add up to.

DISARM (https://www.disarm.foundation/) describes disinformation as tactics and techniques. Woland maps each
framing to the techniques it reads it as (config/disarm.yaml lists them); this module turns the day summaries'
counts into two files that FIMI and threat-intelligence tools read:

- a DISARM Navigator layer (`exports/disarm-layer-<n>d.json`): every technique, scored by the share of the
  period's articles that matched a framing mapped to it;
- a STIX 2.1 bundle for the latest completed week (`exports/weekly-stix.json`): Woland as an identity, one
  attack-pattern per technique seen, and one report that refers to them and carries the counts.

The counts are pattern matches and the mapping is Woland's own reading: both files say so. Identifiers are
UUIDv5 under a fixed namespace, and times come from the period itself, so that rebuilding gives the same file.
Standard library only.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time, timedelta, timezone

from .util import MSK

# all of Woland's STIX identifiers are UUIDv5 names under this namespace (uuid5(NAMESPACE_URL, "https://github.com/Savvyboi/Woland"))
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/Savvyboi/Woland")
# STIX 2.1's predefined TLP:WHITE marking (section 7.2.1.4): the data is public
TLP_WHITE = {"type": "marking-definition", "spec_version": "2.1",
             "id": "marking-definition--613f2e26-407d-48c7-9eca-b8e91df99dc9",
             "created": "2017-01-20T00:00:00.000Z", "definition_type": "tlp", "name": "TLP:WHITE",
             "definition": {"tlp": "white"}}
EPOCH = "2026-09-01T00:00:00.000Z"   # when Woland's record begins: its identity's creation time
NAVIGATOR = {"layer": "4.5", "navigator": "4.8.2", "attack": "1"}   # DISARM Navigator: domain "DISARM", version 1
CAVEAT = ("Woland's own reading of what its framings do, mapped to DISARM techniques; DISARM does not make this "
          "mapping. Counts are articles that matched a framing's word patterns in the Russian state and "
          "pro-Kremlin press: a pattern match, not evidence of a coordinated operation or of intent.")


def stix_id(kind: str, name: str) -> str:
    return f"{kind}--{uuid.uuid5(NAMESPACE, f'{kind}:{name}')}"


def stix_time(d: date, end: bool = False) -> str:
    """The start (or the end) of a Moscow day, in UTC, as STIX writes times."""
    t = datetime.combine(d + timedelta(days=1) if end else d, time(0), MSK)
    if end:
        t -= timedelta(milliseconds=1)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def techniques_of(narratives) -> dict[int, list[str]]:
    """Narrative index → the DISARM technique ids it is mapped to."""
    return {i: [d["id"] for d in n.disarm] for i, n in enumerate(narratives) if n.disarm}


def tally(sums: list[dict], narratives) -> dict:
    """The period's counts from day summaries: articles in all, and per technique the articles that matched
    any framing mapped to it (an article counts once per technique), by outlet, with each framing's own
    count beside it."""
    total = sum(sum(s.get("totals", {}).values()) for s in sums)
    tech: dict[str, dict] = {}
    for s in sums:
        for tid, by in (s.get("dis") or {}).items():
            e = tech.setdefault(tid, {"n": 0, "outlets": {}})
            for o, v in by.items():
                e["n"] += v
                e["outlets"][o] = e["outlets"].get(o, 0) + v
    for n in narratives:
        hits = sum(sum(s.get("nar", {}).get(n.id, {}).values()) for s in sums)
        for d in n.disarm:
            if d["id"] in tech and hits:
                tech[d["id"]].setdefault("framings", []).append(
                    {"id": n.id, "label": n.label.get("en", n.id), "confidence": d["confidence"], "n": hits})
    for e in tech.values():
        e["framings"] = sorted(e.get("framings", []), key=lambda f: (f["confidence"] != "direct", -f["n"]))
    return {"total": total, "techniques": tech}


def _shortname(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def navigator_layer(t: dict, disarm: dict, first: date, last: date, page: str = "") -> dict:
    """A DISARM Navigator layer: every mapped technique, scored by the percentage of the period's articles
    that matched one of its framings."""
    total = t["total"]
    rows, top = [], 0.0
    for tid, e in sorted(t["techniques"].items()):
        if not e["n"]:
            continue
        info = disarm["techniques"][tid]
        score = round(100 * e["n"] / total, 2) if total else 0
        top = max(top, score)
        frames = ", ".join(f"{f['id']} ({f['confidence']}, {f['n']})" for f in e["framings"])
        rows.append({
            "techniqueID": tid, "tactic": _shortname(disarm["tactics"][info["tactic"]]), "score": score,
            "comment": f"evidence_type=textual_framing | {e['n']} of {total} articles ({score}%) in "
                       f"{len(e['outlets'])} outlets | framings: {frames}",
            "enabled": True,
            "metadata": [{"name": "evidence_type", "value": "textual_framing"},
                         {"name": "articles", "value": str(e["n"])},
                         {"name": "outlets", "value": str(len(e["outlets"]))},
                         {"name": "framings", "value": ", ".join(f["id"] for f in e["framings"])}],
        })
    days = (last - first).days + 1
    return {
        "name": f"Woland: DISARM techniques in the Russian state press, {first.isoformat()} – {last.isoformat()}",
        "versions": NAVIGATOR, "domain": "DISARM",
        "description": f"{days} completed days, {total} articles. Score: the percentage of the period's articles "
                      f"that matched a framing mapped to the technique. {CAVEAT}",
        "sorting": 3, "hideDisabled": False,
        "gradient": {"colors": ["#f5f0e6", "#d9822b", "#8b1e1e"], "minValue": 0, "maxValue": max(1, round(top + 0.5))},
        "legendItems": [], "showTacticRowBackground": False, "selectTechniquesAcrossTactics": True,
        "selectSubtechniquesWithParent": False,
        "metadata": [{"name": "source", "value": "Woland"}, {"name": "from", "value": first.isoformat()},
                     {"name": "to", "value": last.isoformat()}, {"name": "articles", "value": str(total)}]
                    + ([{"name": "page", "value": page}] if page else []),
        "techniques": rows,
    }


def stix_bundle(t: dict, disarm: dict, week: str, first: date, last: date, page: str = "", repo: str = "") -> dict:
    """A STIX 2.1 bundle for one week: Woland, the techniques seen as attack-patterns, and a report."""
    marking = [TLP_WHITE["id"]]
    ident = {"type": "identity", "spec_version": "2.1", "id": stix_id("identity", "woland"),
             "created": EPOCH, "modified": EPOCH, "name": "Woland", "identity_class": "system",
             "description": "A daily, searchable chronicle of the Russian state and pro-Kremlin press since "
                            "1 September 2026.",
             "object_marking_refs": marking}
    if repo:
        ident["contact_information"] = repo
    captured = f"{disarm['captured']['date']}T00:00:00.000Z"
    patterns, counts = [], []
    for tid, e in sorted(t["techniques"].items()):
        if not e["n"]:
            continue
        info = disarm["techniques"][tid]
        ap = {"type": "attack-pattern", "spec_version": "2.1", "id": stix_id("attack-pattern", tid),
              "created_by_ref": ident["id"], "created": captured, "modified": captured,
              "name": info["name"],
              "kill_chain_phases": [{"kill_chain_name": "disarm",
                                     "phase_name": _shortname(disarm["tactics"][info["tactic"]])}],
              "external_references": [{"source_name": "DISARM", "external_id": tid,
                                       "url": disarm["technique_url"].format(id=tid)}],
              "object_marking_refs": marking,
              "x_woland_evidence_type": "textual_framing"}
        patterns.append(ap)
        counts.append({"technique": tid, "attack_pattern_ref": ap["id"], "articles": e["n"],
                       "share": round(e["n"] / t["total"], 5) if t["total"] else None,
                       "outlets": dict(sorted(e["outlets"].items(), key=lambda kv: -kv[1])),
                       "framings": [{"id": f["id"], "confidence": f["confidence"], "articles": f["n"]}
                                    for f in e["framings"]]})
    start, end = stix_time(first), stix_time(last, end=True)
    refs = [ident["id"]] + [p["id"] for p in patterns]
    seen = ", ".join(f"{c['technique']} ({c['articles']})" for c in sorted(counts, key=lambda c: -c["articles"]))
    report = {"type": "report", "spec_version": "2.1", "id": stix_id("report", f"week:{week}"),
              "created_by_ref": ident["id"], "created": end, "modified": end, "published": end,
              "name": f"Woland: DISARM techniques in the Russian state press, week {week}",
              "description": f"{first.isoformat()} – {last.isoformat()}: {t['total']} articles. Articles per "
                             f"technique: {seen or 'none'}. {CAVEAT}",
              "report_types": ["attack-pattern"], "object_refs": refs, "object_marking_refs": marking,
              "x_woland_period": {"from": first.isoformat(), "to": last.isoformat(), "start": start, "stop": end},
              "x_woland_articles": t["total"], "x_woland_counts": counts}
    if page:
        report["external_references"] = [{"source_name": "Woland", "url": page,
                                           "description": "The week's brief"}]
    objects = [TLP_WHITE, ident, *patterns, report]
    return {"type": "bundle", "id": stix_id("bundle", f"week:{week}:{len(patterns)}:{t['total']}"),
            "objects": objects}
