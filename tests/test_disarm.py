"""DISARM: the mapping in config/lexicon.yaml and the Navigator and STIX 2.1 exports (woland/disarm.py)."""
import re
import uuid
from datetime import date, datetime

import pytest
import yaml

from woland import disarm
from woland.config import CONFIG_DIR, load_disarm, load_lexicon

STIX_ID = re.compile(r"^([a-z][a-z0-9-]*[a-z0-9])--([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
STIX_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def write_lexicon(tmp_path, entries):
    raw = yaml.safe_load((CONFIG_DIR / "lexicon.yaml").read_text(encoding="utf-8"))
    raw["framings"] = raw["framings"][:1]
    raw["topics"] = raw["topics"][:1]
    if entries is None:
        raw["framings"][0].pop("disarm", None)
    else:
        raw["framings"][0]["disarm"] = entries
    p = tmp_path / "lexicon.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return p


def test_every_mapping_names_a_listed_technique():
    cfg = load_disarm()
    framings = [n for n in load_lexicon() if n.family == "framing"]
    assert all(n.disarm for n in framings), "every framing is mapped"
    assert not any(n.disarm for n in load_lexicon() if n.family == "topic"), "topics are neutral: not mapped"
    used = {d["id"] for n in framings for d in n.disarm}
    assert used == set(cfg["techniques"]), "disarm.yaml lists exactly the techniques used"
    for n in framings:
        assert any(d["confidence"] == "direct" for d in n.disarm) or all(d["confidence"] == "partial" for d in n.disarm)
        for d in n.disarm:
            assert d["url"].endswith(f"/{d['id']}.md") and d["name"] == cfg["techniques"][d["id"]]["name"]
            assert d["tactic"] in cfg["tactics"]


def test_the_lexicon_loads_with_and_without_a_mapping(tmp_path):
    (n, _) = load_lexicon(write_lexicon(tmp_path, None))
    assert n.disarm == [] and "disarm" not in n.public()
    (n, _) = load_lexicon(write_lexicon(tmp_path, [{"id": "T0075", "confidence": "direct"}]))
    assert n.public()["disarm"][0] == {
        "id": "T0075", "confidence": "direct", "name": "Dismiss", "tactic": "TA02", "tactic_name": "Plan Objectives",
        "url": "https://github.com/DISARMFoundation/DISARMframeworks/blob/main/generated_pages/techniques/T0075.md"}


@pytest.mark.parametrize("entries", [
    [{"id": "T9999", "confidence": "direct"}],                                          # not in disarm.yaml
    [{"id": "T0075", "confidence": "strong"}],                                          # not direct or partial
    [{"id": "T0075"}],
    [{"id": "T0075", "confidence": "direct"}, {"id": "T0075", "confidence": "partial"}],  # twice
])
def test_a_bad_mapping_is_refused(tmp_path, entries):
    with pytest.raises(ValueError):
        load_lexicon(write_lexicon(tmp_path, entries))


# two days of summaries: 100 articles; 'svo' (T0076 direct, T0002 partial) matched 10, 'nazism' 4
SUMS = [{"totals": {"ria": 40, "rt": 20}, "nar": {"svo": {"ria": 6}, "nazism": {"rt": 2}},
         "dis": {"T0076": {"ria": 6}, "T0002": {"ria": 6}, "T0135.001": {"rt": 2}, "T0003": {"rt": 2}}},
        {"totals": {"ria": 30, "rt": 10}, "nar": {"svo": {"ria": 3, "rt": 1}, "nazism": {"ria": 2}},
         "dis": {"T0076": {"ria": 3, "rt": 1}, "T0002": {"ria": 3, "rt": 1}, "T0135.001": {"ria": 2}, "T0003": {"ria": 2}}}]


def test_tally_counts_articles_per_technique():
    t = disarm.tally(SUMS, load_lexicon())
    assert t["total"] == 100
    e = t["techniques"]["T0076"]
    assert e["n"] == 10 and e["outlets"] == {"ria": 9, "rt": 1}
    assert [(f["id"], f["confidence"], f["n"]) for f in e["framings"]] == [("svo", "direct", 10)]
    assert [(f["id"], f["confidence"]) for f in t["techniques"]["T0002"]["framings"]][0] == ("svo", "partial")


def test_navigator_layer():
    lay = disarm.navigator_layer(disarm.tally(SUMS, load_lexicon()), load_disarm(), date(2026, 9, 1), date(2026, 9, 2))
    assert lay["domain"] == "DISARM" and lay["versions"]["layer"] == "4.5"
    scores = {r["techniqueID"]: r["score"] for r in lay["techniques"]}
    assert scores == {"T0002": 10.0, "T0003": 4.0, "T0076": 10.0, "T0135.001": 4.0}
    assert all(isinstance(r["score"], (int, float)) and r["enabled"] for r in lay["techniques"])
    assert "not evidence" in lay["description"]


def check_stix(bundle):
    assert bundle["type"] == "bundle" and STIX_ID.match(bundle["id"]).group(1) == "bundle"
    ids = set()
    for o in bundle["objects"]:
        m = STIX_ID.match(o["id"])
        assert m and m.group(1) == o["type"], o["id"]
        assert uuid.UUID(m.group(2)).version in (4, 5)
        assert o["spec_version"] == "2.1"
        for k in ("created", "modified", "published"):
            if k in o:
                assert STIX_TIME.match(o[k]), (k, o[k])
                datetime.fromisoformat(o[k].replace("Z", "+00:00"))
        assert o["id"] not in ids
        ids.add(o["id"])
    for o in bundle["objects"]:
        for ref in o.get("object_refs", []) + o.get("object_marking_refs", []) + [o.get("created_by_ref")]:
            assert ref is None or ref in ids, ref
    return {o["type"]: o for o in bundle["objects"]}


def test_stix_bundle_is_valid_and_reproducible():
    cfg, lex = load_disarm(), load_lexicon()
    make = lambda: disarm.stix_bundle(disarm.tally(SUMS, lex), cfg, "2026-W36", date(2026, 8, 31), date(2026, 9, 6),  # noqa: E731
                                      "https://example.org/brief.html?w=2026-W36")
    b = make()
    assert b == make(), "the same week gives the same bundle"
    by = check_stix(b)
    assert by["identity"]["identity_class"] == "system"
    aps = [o for o in b["objects"] if o["type"] == "attack-pattern"]
    assert {a["external_references"][0]["external_id"] for a in aps} == {"T0002", "T0003", "T0076", "T0135.001"}
    assert all(a["x_woland_evidence_type"] == "textual_framing" and a["external_references"][0]["source_name"] == "DISARM"
               for a in aps)
    rep = by["report"]
    assert rep["published"] == "2026-09-06T20:59:59.999Z"   # the end of Sunday, Moscow time
    assert rep["x_woland_articles"] == 100 and "not evidence" in rep["description"]
    # an attack-pattern's id is the technique's, whatever the week
    other = disarm.stix_bundle(disarm.tally(SUMS[:1], lex), cfg, "2026-W37", date(2026, 9, 7), date(2026, 9, 13))
    assert {a["id"] for a in aps} >= {o["id"] for o in other["objects"] if o["type"] == "attack-pattern"}
    assert other["id"] != b["id"]
