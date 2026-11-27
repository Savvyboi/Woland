"""tools/benchmark_mt.py: the sample it draws, and the table it writes (no model is run here)."""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta

from woland import store
from woland.config import ROOT, load_outlets

spec = importlib.util.spec_from_file_location("benchmark_mt", ROOT / "tools" / "benchmark_mt.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_the_sample_is_even_across_outlet_groups_and_a_third_short(archive):
    until = date(2026, 11, 20)
    by_group = {}
    for o in load_outlets():
        if o.lang == "ru" and o.group in bench.GROUPS:
            by_group.setdefault(o.group, o)
    for o in by_group.values():
        days = {}
        for i in range(30):
            d = until - timedelta(days=1 + i % 5)
            words = "Короткий заголовок" if i % 2 else "Длинный заголовок из более чем шести слов про события"
            days.setdefault(d, []).append({"id": f"{o.id}:{i}", "o": o.id, "u": f"https://example.org/{o.id}/{i}",
                                           "p": f"{d}T10:{i:02d}:00+03:00", "t": f"{words} {i}", "w": 0, "h": "0" * 16,
                                           "r": "2026-11-20T00:00:00Z", "via": "page"})
        for d, recs in days.items():
            store.write_day(d, o.id, recs)
    rows = bench.sample(20, days=10, seed=3, until=until)
    assert len(rows) == 20 and {g: sum(r["group"] == g for r in rows) for g in bench.GROUPS} == {g: 5 for g in bench.GROUPS}
    assert sum(len(r["t"].split()) <= bench.SHORT for r in rows) == 4          # 5 // 3 in each group
    assert rows == bench.sample(20, days=10, seed=3, until=until)               # the same seed, the same sample
    table = bench.markdown(rows, {"m": {"out": [f"EN {i}" for i in range(20)], "rate": 12.5, "peak": 9e8, "load": 1.0},
                                  "broken": {"error": "model unavailable"}}, seed=3, days=10)
    assert "| m | 12.5 | 900 | 1.0 |" in table and "| broken | model unavailable | | |" in table
    assert sum(line.startswith("| ") and line.split(" | ")[0][2:].isdigit() for line in table.splitlines()) == 20
    assert " | EN 0 |  |" in table
