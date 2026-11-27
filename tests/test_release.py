"""The quarterly data release (tools/quarterly_release.py, .github/workflows/quarterly-release.yml) and
Zenodo's metadata (.zenodo.json)."""
import hashlib
import json
import sys
import tarfile
from datetime import date

import pytest
import yaml

from woland.config import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import quarterly_release as qr  # noqa: E402

# Zenodo's deposit metadata (developers.zenodo.org, "Deposit metadata"): the fields used here and their values
UPLOAD_TYPES = {"publication", "poster", "presentation", "dataset", "image", "video", "software", "lesson",
                "physicalobject", "other"}
RELATIONS = {"isCitedBy", "cites", "isSupplementTo", "isSupplementedBy", "isContinuedBy", "continues",
             "isDescribedBy", "describes", "hasMetadata", "isMetadataFor", "isNewVersionOf",
             "isPreviousVersionOf", "isPartOf", "hasPart", "isReferencedBy", "references", "isDocumentedBy",
             "documents", "isCompiledBy", "compiles", "isVariantFormOf", "isOriginalFormof", "isIdenticalTo",
             "isAlternateIdentifier", "isReviewedBy", "reviews", "isDerivedFrom", "isSourceOf", "requires",
             "isRequiredBy", "isObsoletedBy", "obsoletes"}
KNOWN = {"upload_type", "title", "description", "creators", "access_right", "license", "keywords",
         "related_identifiers", "notes", "language", "contributors", "communities", "version", "publication_date"}


def test_zenodo_metadata_is_strict_json_zenodo_accepts():
    raw = (ROOT / ".zenodo.json").read_text(encoding="utf-8")
    meta = json.loads(raw)                                   # strict JSON: no comments, no trailing commas
    assert set(meta) <= KNOWN, set(meta) - KNOWN
    assert meta["upload_type"] in UPLOAD_TYPES and meta["upload_type"] == "dataset"
    assert meta["title"] and meta["description"] and meta["access_right"] == "open"
    assert meta["license"] == "cc-by-4.0"
    assert meta["creators"] and all(c.get("name") for c in meta["creators"])
    assert {"OSINT", "Russian state media", "disinformation", "propaganda", "dataset"} <= set(meta["keywords"])
    for r in meta["related_identifiers"]:
        assert r["relation"] in RELATIONS and r["identifier"].startswith("https://")
    assert "@" not in raw                                    # no e-mail addresses


def test_the_workflow_can_be_dry_run():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "quarterly-release.yml").read_text(encoding="utf-8"))
    on = wf[True]                                            # (YAML 1.1 reads the key `on` as true)
    assert on["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
    assert on["schedule"][0]["cron"].split()[2:4] == ["2", "1,4,7,10"]
    steps = wf["jobs"]["release"]["steps"]
    publish = next(s for s in steps if s.get("name") == "Publish the release")
    keep = next(s for s in steps if s.get("name") == "Keep the files (dry run)")
    assert "inputs.dry_run" in publish["if"] and "inputs.dry_run" in keep["if"]
    assert "already released" in publish["run"]          # a release is never replaced


def test_quarters():
    assert qr.previous_quarter(date(2027, 1, 2)) == "2026-Q4"
    assert qr.previous_quarter(date(2026, 10, 2)) == "2026-Q3"
    assert qr.quarter_end("2026-Q4") == date(2026, 12, 31) and qr.quarter_end("2027-Q1") == date(2027, 3, 31)


def fake_repo(tmp_path):
    """A repository with two days of one outlet in October 2026, one in November, and one in January 2027."""
    for day, n in (("2026/10/01", 2), ("2026/11/15", 3), ("2027/01/01", 1)):
        d = tmp_path / "data" / "articles" / day
        d.mkdir(parents=True)
        (d / "ria.jsonl").write_text("".join(json.dumps({"id": f"ria:{day}{i}"}) + "\n" for i in range(n)), encoding="utf-8")
    for name in ("config/lexicon.yaml", "config/glossary.yaml", "docs/lexicon-audit.md", "LICENSE"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(name, encoding="utf-8")
    site = tmp_path / "_site"
    (site / "data" / "parquet").mkdir(parents=True)
    (site / "data" / "parquet" / "woland-2026-10.parquet").write_bytes(b"PAR1 october PAR1")
    (site / "data" / "parquet" / "woland-2027-01.parquet").write_bytes(b"PAR1 january PAR1")
    (site / "data" / "meta.json").write_text(json.dumps({"complete_through": "2027-01-01"}), encoding="utf-8")
    return site


def test_a_release_holds_the_quarter_and_checks_out(tmp_path):
    site = fake_repo(tmp_path)
    out = tmp_path / "dist"
    paths = qr.assemble("2026-Q4", out, site, "https://github.com/Savvyboi/Woland", root=tmp_path)
    names = sorted(p.name for p in paths)
    assert names == ["RELEASE.md", "SHA256SUMS", "woland-2026-10.parquet", "woland-articles-2026-Q4.SHA256SUMS",
                     "woland-articles-2026-Q4.tar.gz"]
    for line in (out / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    with tarfile.open(out / "woland-articles-2026-Q4.tar.gz") as tar:
        inside = tar.getnames()
    assert "woland-articles-2026-Q4/data/articles/2026/10/01/ria.jsonl" in inside
    assert not any("2027" in n for n in inside) and "woland-articles-2026-Q4/config/lexicon.yaml" in inside
    notes = (out / "RELEASE.md").read_text(encoding="utf-8")
    assert "5 articles" in notes and "data-2026-Q4" in notes and "pattern matches" in notes
    assert "from 2026-10-01 to 2026-11-15" in notes and "collected in full before" in notes
    again = qr.assemble("2026-Q4", tmp_path / "dist2", site, "https://github.com/Savvyboi/Woland", root=tmp_path)
    assert [p.read_bytes() for p in again if p.suffix == ".gz"] == [p.read_bytes() for p in paths if p.suffix == ".gz"]


@pytest.mark.parametrize("today, through, ok", [
    (date(2026, 12, 31), "2026-12-30", False),   # the quarter is not over
    (date(2027, 1, 2), "2026-12-30", False),     # its last day is not collected in full
    (date(2027, 1, 2), "2026-12-31", True),
])
def test_only_a_finished_complete_quarter_is_released(tmp_path, today, through, ok):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "meta.json").write_text(json.dumps({"complete_through": through}), encoding="utf-8")
    assert (qr.check_complete("2026-Q4", tmp_path, today) is None) == ok
