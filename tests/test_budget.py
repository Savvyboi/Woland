"""The site's size against GitHub Pages' limit (woland/budget.py), and the quarterly release archive
(tools/export_quarter.py)."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import tarfile

import pytest

from woland import budget
from woland.config import ROOT


def site(tmp_path, months: dict[str, int], other: int = 1000):
    for month, size in months.items():
        d = tmp_path / "data" / "search" / month / "d"
        d.mkdir(parents=True)
        (d / "0.json.gz").write_bytes(b"x" * size)
    (tmp_path / "data" / "days").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "days" / "2026-11-01.json").write_bytes(b"x" * other)
    (tmp_path / "index.html").write_text("<!doctype html>")
    return tmp_path


def test_a_small_site_passes_and_says_how_many_months_still_fit(tmp_path):
    table, verdict = budget.report(site(tmp_path, {"2026-09": 100_000_000, "2026-10": 100_000_000}))
    assert verdict == "ok"
    assert "| `data/search/2026-09` | 100.0 |" in table and "| **total** | **200.0** |" in table
    assert "about 7 more months fit below 920 MB" in table


def test_a_site_near_the_limit_warns_and_one_over_it_fails(tmp_path, capsys):
    big = site(tmp_path, {f"2026-{m:02d}": 100_000_000 for m in range(1, 9)})   # 800 MB
    assert budget.report(big)[1] == "warn"
    assert budget.main(str(big)) == 0 and "::warning::" in capsys.readouterr().out
    assert budget.report(big, fail_mb=750)[1] == "fail"
    assert budget.main(str(big), fail_mb=750) == 1 and "::error::" in capsys.readouterr().out


def test_the_table_goes_to_the_run_summary_on_github(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    budget.main(str(site(tmp_path / "s", {"2026-11": 5_000_000})))
    assert summary.read_text(encoding="utf-8").startswith("### Site size")


@pytest.fixture
def export_quarter():
    spec = importlib.util.spec_from_file_location("export_quarter", ROOT / "tools" / "export_quarter.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_quarter_is_packed_with_checksums_and_the_same_files_give_the_same_archive(tmp_path, export_quarter):
    root = tmp_path / "repo"
    for month, day in (("10", "01"), ("12", "31"), ("09", "30")):   # September belongs to Q3
        f = root / "data" / "articles" / "2026" / month / day / "ria.jsonl"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"u": f"https://ria.ru/{month}{day}"}) + "\n", encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "lexicon.yaml").write_text("narratives: []\n", encoding="utf-8")
    archive, sums = export_quarter.export("2026-Q4", tmp_path / "a", root)
    again, _ = export_quarter.export("2026-Q4", tmp_path / "b", root)
    assert archive.read_bytes() == again.read_bytes()
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert names == ["woland-articles-2026-Q4/data/articles/2026/10/01/ria.jsonl",
                         "woland-articles-2026-Q4/data/articles/2026/12/31/ria.jsonl",
                         "woland-articles-2026-Q4/config/lexicon.yaml"]
        first = tar.extractfile(names[0]).read()
    lines = sums.read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"{hashlib.sha256(first).hexdigest()}  {names[0]}"
    assert lines[-1] == f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  woland-articles-2026-Q4.tar.gz"
    assert gzip.open(archive).read(10)                                  # a plain .tar.gz
    with pytest.raises(ValueError):
        export_quarter.export("2026-Q1", tmp_path / "c", root)          # nothing collected then
    with pytest.raises(ValueError):
        export_quarter.quarter_months("2026-5")
