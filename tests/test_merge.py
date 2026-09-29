"""The merge driver for data files (woland/merge.py): two runs that wrote at the same time must both keep
their work when the second one pushes."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from woland.config import ROOT
from woland.merge import merge_coverage, merge_index, merge_json, merge_records, merge_seen, merge_text


def rec(u, p="2026-09-29T10:00:00+03:00", **kw):
    r = {"id": f"x:{u}", "o": "x", "u": u, "p": p, "t": f"headline {u}", "w": 0, "h": "0" * 16,
         "r": "2026-09-29T07:00:00Z", "via": "feed"}
    r.update(kw)
    return r


def jsonl(*recs):
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n"
                   for r in sorted(recs, key=lambda r: (r["p"], r["u"])))


def urls(text):
    return [json.loads(line)["u"] for line in text.splitlines()]


def test_records_added_on_both_sides_are_all_kept_in_time_order():
    base = jsonl(rec("a", "2026-09-29T09:00:00+03:00"))
    ours = jsonl(rec("a", "2026-09-29T09:00:00+03:00"), rec("c", "2026-09-29T11:00:00+03:00"))
    theirs = jsonl(rec("a", "2026-09-29T09:00:00+03:00"), rec("b", "2026-09-29T10:00:00+03:00"))
    assert urls(merge_records(base, ours, theirs)) == ["a", "b", "c"]


def test_a_page_read_beats_a_headline_only_record_and_keeps_its_translation():
    base = jsonl(rec("a"))
    ours = jsonl(rec("a", te="translated"))  # the nightly run translated it
    theirs = jsonl(rec("a", via="page", w=300, d="the lead", r="2026-09-29T08:00:00Z"))  # a poll read the page
    (merged,) = [json.loads(line) for line in merge_records(base, ours, theirs).splitlines()]
    assert merged["via"] == "page" and merged["w"] == 300 and merged["te"] == "translated"


def test_a_translation_of_another_headline_is_not_lent():
    ours = jsonl(rec("a", t="old headline", te="old translation"))
    theirs = jsonl(rec("a", t="new headline", via="page"))
    (merged,) = [json.loads(line) for line in merge_records("", ours, theirs).splitlines()]
    assert merged["t"] == "new headline" and "te" not in merged


def test_an_archive_capture_is_never_lent_to_a_page_read_from_the_outlet():
    ours = jsonl(rec("a", via="page", ar="20260929070000", r="2026-09-29T07:00:00Z"))
    theirs = jsonl(rec("a", via="page", r="2026-09-29T09:00:00Z"))
    (merged,) = [json.loads(line) for line in merge_records("", ours, theirs).splitlines()]
    assert "ar" not in merged and merged["r"] == "2026-09-29T09:00:00Z"


def test_a_record_moved_to_another_day_stays_removed():
    base = jsonl(rec("a"), rec("b"))
    ours = jsonl(rec("a", te="translated"), rec("b"))  # changed here …
    theirs = jsonl(rec("b"))                           # … and moved to another day's file there
    assert urls(merge_records(base, ours, theirs)) == ["b"]


def test_coverage_merges_day_by_day_and_a_completed_day_stays_complete():
    base = {"ria": {"2026-09-28": {"n": 500, "status": "partial", "at": "2026-09-29T01:00:00Z"}}}
    ours = {"ria": {"2026-09-28": {"n": 520, "status": "complete", "at": "2026-09-29T07:00:00Z"}},
            "tass": {"2026-09-29": {"n": 300, "status": "feed", "at": "2026-09-29T07:00:00Z"}}}
    theirs = {"ria": {"2026-09-28": {"n": 510, "h": 3, "status": "partial", "at": "2026-09-29T08:00:00Z"},
                      "2026-09-29": {"n": 90, "status": "partial", "at": "2026-09-29T08:00:00Z"}}}
    merged = merge_coverage(base, ours, theirs)
    assert merged["ria"]["2026-09-28"] == {"n": 520, "h": 3, "status": "complete", "at": "2026-09-29T08:00:00Z"}
    assert merged["ria"]["2026-09-29"]["n"] == 90 and merged["tass"]["2026-09-29"]["n"] == 300


def test_rejected_urls_are_merged_and_pruning_is_kept():
    base = {"mk": {"u1": "2026-09-10", "u2": "2026-09-20"}}
    ours = {"mk": {"u2": "2026-09-20", "u3": "2026-09-29"}}  # u1 pruned as too old
    theirs = {"mk": {"u1": "2026-09-10", "u2": "2026-09-20", "u4": "2026-09-29"}}
    assert merge_seen(base, ours, theirs) == {"mk": {"u2": "2026-09-20", "u3": "2026-09-29", "u4": "2026-09-29"}}


def test_runs_from_both_sides_are_kept():
    base = [{"at": "2026-09-29T01:00:00Z", "mode": "poll"}]
    ours = base + [{"at": "2026-09-29T07:00:00Z", "mode": "poll"}]
    theirs = base + [{"at": "2026-09-29T06:54:00Z", "mode": "daily"}]
    merged = json.loads(merge_json("runs.json", json.dumps(base), json.dumps(ours), json.dumps(theirs)))
    assert sorted(r["at"] for r in merged) == ["2026-09-29T01:00:00Z", "2026-09-29T06:54:00Z", "2026-09-29T07:00:00Z"]


def test_the_url_index_keeps_both_sides_lines_and_a_later_line_wins():
    base = "k1 2026-09-28\n"
    ours = "k1 2026-09-28\nk2 2026-09-29\n"
    theirs = "k1 2026-09-28\nk3 2026-09-29\nk1 2026-09-27\n"  # k1's record moved to the 27th
    merged = merge_index(base, ours, theirs)
    index = dict(line.split(" ") for line in merged.splitlines())
    assert index == {"k1": "2026-09-27", "k2": "2026-09-29", "k3": "2026-09-29"}


def test_the_later_check_of_each_outlet_is_kept():
    ours = {"tass": {"at": "2026-09-28T13:00:00Z", "ok": True}, "mk": {"at": "2026-09-28T13:00:00Z", "ok": False}}
    theirs = {"tass": {"at": "2026-09-30T08:00:00Z", "ok": False}, "mk": ours["mk"]}
    merged = json.loads(merge_json("check.json", "", json.dumps(ours), json.dumps(theirs)))
    assert merged["tass"]["at"] == "2026-09-30T08:00:00Z" and merged["mk"] == ours["mk"]


def test_an_unknown_file_is_left_to_a_person():
    with pytest.raises(ValueError):
        merge_text("data/state/other.json", "{}", "{}", "{}")


def test_git_routes_the_data_files_to_the_driver():
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    paths = ["data/articles/2026/09/29/tass.jsonl", "data/state/coverage.json", "data/state/urls/tass.txt",
             "woland/merge.py"]
    out = subprocess.run(["git", "check-attr", "merge", "--", *paths], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    attrs = dict(line.rsplit(": ", 1) for line in out.splitlines())
    assert [attrs[f"{p}: merge"] for p in paths] == ["woland", "woland", "woland", "unspecified"]


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_a_rebase_merges_two_runs_that_wrote_the_same_files(tmp_path):
    """Two runs start from the same commit; the one that pushes second rebases onto the first, as the
    workflows do with `git pull --rebase`."""
    env = {**os.environ, "PYTHONPATH": str(ROOT), "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, env=env, capture_output=True, text=True, check=True).stdout

    day = tmp_path / "data" / "articles" / "2026" / "09" / "29" / "tass.jsonl"
    cov = tmp_path / "data" / "state" / "coverage.json"
    index = tmp_path / "data" / "state" / "urls" / "tass.txt"
    for p in (day, cov, index):
        p.parent.mkdir(parents=True, exist_ok=True)

    def write(records, coverage, lines):
        day.write_text(jsonl(*records), encoding="utf-8", newline="\n")
        cov.write_text(json.dumps(coverage, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        index.write_text("".join(f"{k} 2026-09-29\n" for k in lines), encoding="utf-8", newline="\n")

    git("init", "-q", "-b", "main")
    git("config", "core.autocrlf", "false")
    git("config", "merge.woland.driver", f'"{Path(sys.executable).as_posix()}" -m woland merge %O %A %B %P')
    (tmp_path / ".gitattributes").write_text((ROOT / ".gitattributes").read_text(encoding="utf-8"), encoding="utf-8")
    write([rec("a")], {"tass": {"2026-09-29": {"n": 1, "status": "feed", "at": "1"}}}, ["ka"])
    git("add", "-A")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "poll")
    write([rec("a"), rec("b", "2026-09-29T11:00:00+03:00")], {"tass": {"2026-09-29": {"n": 2, "status": "feed", "at": "2"}}},
          ["ka", "kb"])
    git("commit", "-qam", "poll")
    git("checkout", "-q", "main")
    write([rec("a", te="translated"), rec("c", "2026-09-29T12:00:00+03:00")],
          {"tass": {"2026-09-29": {"n": 2, "status": "feed", "at": "3"}}}, ["ka", "kc"])
    git("commit", "-qam", "nightly")
    git("rebase", "-q", "poll")  # the nightly run's commit replayed onto the poll's, as `git pull --rebase` does

    merged = [json.loads(line) for line in day.read_text(encoding="utf-8").splitlines()]
    assert [r["u"] for r in merged] == ["a", "b", "c"] and merged[0]["te"] == "translated"
    assert json.loads(cov.read_text(encoding="utf-8"))["tass"]["2026-09-29"]["n"] == 2
    assert sorted(index.read_text(encoding="utf-8").split()) == sorted(["ka", "kb", "kc"] + ["2026-09-29"] * 3)
    assert not git("status", "--porcelain")
