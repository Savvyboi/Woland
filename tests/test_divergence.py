"""At home and abroad (woland/divergence.py): the outlets writing for Russian readers against those writing for
readers abroad, week by week."""
from __future__ import annotations

from datetime import date

import pytest

from woland import divergence as dv
from woland.config import AUDIENCES, load_outlets


def test_every_outlet_says_whom_it_writes_for():
    outlets = load_outlets(include_disabled=True)
    assert all(o.audience in AUDIENCES for o in outlets)
    by = {o.id: o.audience for o in outlets}
    assert by["rt"] == by["tass-en"] == by["kremlin-en"] == "foreign" and by["ria"] == by["inosmi"] == "domestic"
    # the archive links of the Week page rely on this: domestic outlets write in Russian, the others in English
    assert all((o.audience == "domestic") == (o.lang == "ru") for o in outlets)


def test_js_distance_is_zero_for_the_same_mix_and_one_for_none_in_common():
    assert dv.js_distance({"a": 3, "b": 1}, {"a": 30, "b": 10}) == 0.0      # same shares, any scale
    assert dv.js_distance({"a": 5}, {"b": 7}) == 1.0                        # nothing in common
    mid = dv.js_distance({"a": 1, "b": 1}, {"a": 1, "c": 1})
    assert 0 < mid < 1 and mid == dv.js_distance({"a": 1, "c": 1}, {"a": 1, "b": 1})   # symmetric
    assert dv.js_distance({}, {"a": 1}) is None and dv.js_distance({"a": 0}, {"a": 1}) is None


def summary(totals, nar, countries=None):
    return {"totals": totals, "nar": nar, "countries": countries or {}}


def test_a_week_compares_only_outlets_collected_every_day():
    """An outlet with a day not collected at all is left out of its side: otherwise the gap would lower its
    side's article total and raise every share."""
    days = [date(2026, 11, 2), date(2026, 11, 3)]
    idx = {d: i for i, d in enumerate(days)}
    codes = {"ria": "cc", "tass": "cm", "rt": "cf"}           # TASS was not collected on the second day
    complete = dv.complete_outlets(codes, idx, days)
    assert complete == {"ria", "rt"}
    sums = [summary({"ria": 10, "tass": 50, "rt": 10}, {"russophobia": {"ria": 5, "tass": 40, "rt": 0},
                                                         "kyiv-regime": {"ria": 5, "rt": 5}}, {"FI": {"rt": 6}}),
            summary({"ria": 10, "rt": 10}, {"russophobia": {"ria": 5}, "kyiv-regime": {"ria": 5, "rt": 5}}, {"FI": {"rt": 6}})]
    w = dv.week(sums, {"ria": "domestic", "tass": "domestic", "rt": "foreign"}, complete,
                {"russophobia", "kyiv-regime"}, set())
    assert w["outlets"] == {"domestic": ["ria"], "foreign": ["rt"]} and w["left_out"] == ["tass"]
    assert w["n"] == {"domestic": 20, "foreign": 20}                   # TASS's 50 articles are not in the total
    assert w["framed"] == {"domestic": 20, "foreign": 10}
    assert w["jsd"] == dv.js_distance({"russophobia": 10, "kyiv-regime": 10}, {"kyiv-regime": 10})
    home = {(g["kind"], g["id"]) for g in w["gaps"]["domestic"]}
    away = {(g["kind"], g["id"]) for g in w["gaps"]["foreign"]}
    assert home == {("framing", "russophobia")} and away == {("country", "FI")}
    fi = w["gaps"]["foreign"][0]
    assert (fi["dn"], fi["fn"], fi["ds"], fi["fs"]) == (0, 12, 0.0, 0.6)


def test_no_side_no_score():
    """A side with no outlet collected every day (or no framing match) has no divergence: None, never 0."""
    w = dv.week([summary({"ria": 10}, {"russophobia": {"ria": 5}})], {"ria": "domestic", "rt": "foreign"}, {"ria"},
                {"russophobia"}, set())
    assert w["jsd"] is None and w["n"]["foreign"] == 0 and w["gaps"] == {"domestic": [], "foreign": []}


@pytest.mark.parametrize("kd, kf, side", [(4, 0, None), (5, 0, "domestic"), (8, 2, None), (0, 5, "foreign")])
def test_a_gap_needs_enough_articles_and_a_clear_ratio(kd, kf, side):
    dom, fgn = {"n": 100}, {"n": 100}
    g = dv.gaps(dom, fgn, [("topic", "x", kd, kf)])
    assert [s for s in ("domestic", "foreign") if g[s]] == ([side] if side else [])
