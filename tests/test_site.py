"""The website: build a small archive and search it with the site's own JavaScript; check the interface
strings exist in English, Finnish and Swedish."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from woland import build as buildmod
from woland import store
from woland.config import ROOT

SITE = ROOT / "site"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")

HEADLINES = [
    ("ria", "Киевский режим готовит провокацию в Донбассе", "The Kiev regime is preparing a provocation in Donbass"),
    ("ria", "Лавров обвинил Запад в провокациях", "Lavrov accused the West of provocations"),
    ("ria", "Синоптики пообещали тёплую погоду", "Forecasters promised warm weather"),
    ("rt", "Kiev regime staged a provocation, Moscow says", ""),
    ("rt", "Finland closes the border again", ""),
    ("ria", "Уиткофф прилетел в Москву", "Whitkoff arrived in Moscow"),   # the glossary corrects the name
]
# the nightly run that started at 04:17 Moscow time on 7 September gathered 6 September after it ended
RUNS = [{"at": "2026-09-07T01:17:00Z", "mode": "daily", "outlets": {"ria": {"range": ["2026-09-01", "2026-09-07"], "new": 3}}},
        {"at": "2026-09-08T10:43:00Z", "mode": "poll", "outlets": {"tass": {"range": ["2026-09-07", "2026-09-08"], "new": 0}}}]


@pytest.fixture(scope="module")
def built_site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("site")
    mp = pytest.MonkeyPatch()
    mp.setattr(store, "ART_DIR", tmp / "data" / "articles")
    mp.setattr(store, "STATE_DIR", tmp / "data" / "state")
    mp.setattr(buildmod, "CACHE", tmp / "cache")
    start = date(2026, 9, 1)
    for i in range(8):
        d = start + timedelta(days=i)
        for outlet in ("ria", "rt"):
            recs = []
            for j, (o, t, te) in enumerate(HEADLINES):
                if o != outlet:
                    continue
                host = "https://ria.ru/{:%Y%m%d}/a-{}.html" if o == "ria" else "https://www.rt.com/news/{1}-a{0:%d}/"
                rec = {"id": f"{o}:{i}{j}", "o": o, "u": host.format(d, 1000 + j), "p": f"{d}T1{j}:00:00+03:00",
                       "t": t, "w": 100, "h": "0" * 16, "r": "2026-09-24T00:00:00Z", "via": "page"}
                if "погоду" in t:  # a headline-only record: the page could not be read
                    rec.update(w=0, via="feed")
                if "staged" in t:  # read from the Internet Archive's copy: the outlet did not answer
                    rec["ar"] = f"{d:%Y%m%d}093000"
                if te:
                    rec["te"] = te
                recs.append(rec)
            store.write_day(d, outlet, recs)
    days = [(start + timedelta(days=i)).isoformat() for i in range(8)]
    store._save("runs.json", RUNS)
    store._save("coverage.json", {"ria": {d: {"n": 3, "status": "complete"} for d in days},
                                  "tass": {d: {"n": 0, "status": "feed"} for d in days}})  # its feed not read yet
    out = tmp / "_site"
    buildmod.build(out_dir=str(out))
    yield out
    mp.undo()


def search(site, *queries):
    res = subprocess.run([NODE, str(ROOT / "tests" / "js" / "search_harness.mjs"), str(site), json.dumps(list(queries))],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(res.stdout)


@needs_node
def test_search_finds_every_word_form(built_site):
    (r,) = search(built_site, {"q": "провокации"})           # the headlines say "провокацию", "провокациях"
    assert r["total"] == 16 and {h["o"] for h in r["hits"]} == {"ria"}
    assert "провокацию" in r["forms"] and "провокациях" in r["forms"]


@needs_node
def test_search_prefix_negation_or_and_filters(built_site):
    prefix, neg, either, english_only, one_day = search(
        built_site,
        {"q": "провокац*"},
        {"q": "провокац* -лавров"},
        {"q": "погоду OR finland"},
        {"q": "provocation", "lang": "en"},
        {"q": "провокац*", "from": "2026-09-03", "to": "2026-09-03"},
    )
    assert prefix["total"] == 16
    assert neg["total"] == 8 and all("Лавров" not in h["t"] for h in neg["hits"])
    assert either["total"] == 16
    assert english_only["total"] == 8 and {h["o"] for h in english_only["hits"]} == {"rt"}
    assert one_day["total"] == 2 and set(one_day["days"]) == {"2026-09-03"}


@needs_node
def test_english_queries_also_search_machine_translations(built_site):
    (r,) = search(built_site, {"q": "weather"})
    assert r["total"] == 8 and all(h["o"] == "ria" for h in r["hits"])
    assert all(h["f"] == 1 for h in r["hits"])            # shown as "headline only"


@needs_node
def test_search_by_framing_without_words(built_site):
    meta = json.loads((built_site / "data" / "meta.json").read_text(encoding="utf-8"))
    k = next(n["idx"] for n in meta["narratives"] if n["id"] == "kyiv-regime")
    (r,) = search(built_site, {"q": "", "narr": k})
    assert r["total"] == 16                                  # the Russian and the English headline, every day
    assert all(k in h["ks"] for h in r["hits"])


@needs_node
def test_word_forms_the_archive_has_never_seen(built_site):
    ru, en = search(built_site, {"q": "провокациями"}, {"q": "regimes"})
    assert ru["total"] == 16 and en["total"] == 16


@needs_node
def test_a_prefix_needs_four_letters(built_site):
    (r,) = search(built_site, {"q": "кие*"})
    assert r["error"] == "minchars"


@needs_node
def test_english_searches_find_either_spelling_and_corrected_translations(built_site):
    kyiv, kiev, witkoff = search(built_site, {"q": "kyiv"}, {"q": "kiev"}, {"q": "witkoff"})
    assert kyiv["total"] == kiev["total"] == 16                 # "Kiev" in RT's headline and in the translation
    assert witkoff["total"] == 8 and all(h["te"] == "Witkoff arrived in Moscow" for h in witkoff["hits"])


def cite(site, hits):
    res = subprocess.run([NODE, str(ROOT / "tests" / "js" / "cite_harness.mjs"), str(site), json.dumps(hits)],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(res.stdout)


@needs_node
def test_citations_have_unique_keys_and_the_records_fields(built_site):
    from woland.util import short_hash
    (day1,) = search(built_site, {"q": "", "from": "2026-09-01", "to": "2026-09-01"})
    assert day1["total"] == 6
    out = cite(built_site, [{"month": "2026-09", "i": i} for i in range(6)])
    keys = [x["key"] for x in out]
    assert len(set(keys)) == 6                                   # every record has the same fingerprint and day
    for x in out:
        r = x["record"]
        assert r["id"] == f"{r['outlet_id']}:{short_hash(r['url'])}"   # the id of the record in data/
        assert r["fingerprint"] == "0" * 16 and r["retrieved"] == "2026-09-24" and r["body_words"] in (0, 100)
        assert r["published"].startswith("2026-09-01T") and r["published"].endswith("+03:00")
    weather = next(x["record"] for x in out if x["record"]["title"].startswith("Синоптики"))
    assert weather["source"] == "headline only" and weather["body_words"] == 0
    staged = next(x for x in out if x["record"]["title"].startswith("Kiev regime staged"))
    assert staged["record"]["source"] == "article page as captured by the Internet Archive"
    assert staged["record"]["archive_capture_read"] == "20260901093000"
    assert staged["record"]["archive"] == f"https://web.archive.org/web/20260901093000/{staged['record']['url']}"
    assert "from the Internet Archive's copy of 2026-09-01" in staged["bib"]


def test_digest_examples_carry_what_a_citation_needs(built_site):
    dg = json.loads((built_site / "data" / "days" / "2026-09-03.json").read_text(encoding="utf-8"))
    ex = next(n for n in dg["narratives"] if n["id"] == "kyiv-regime")["ex"]
    assert ex and all(e["h"] == "0" * 16 and e["r"] == "2026-09-24" and e["w"] == 100 for e in ex)
    assert [e.get("ar") for e in ex if e["o"] == "rt"] == ["20260903093000"]    # read from the Archive's copy
    assert dg["spark_from"] == "2026-09-01" and len(dg["narratives"][0]["spark_n"]) == 3


def test_days_still_being_collected_and_outlets_not_collected(built_site):
    meta = json.loads((built_site / "data" / "meta.json").read_text(encoding="utf-8"))
    series = json.loads((built_site / "data" / "series.json").read_text(encoding="utf-8"))
    assert meta["complete_through"] == "2026-09-06"            # 7 and 8 September: not yet gathered by a nightly run
    assert [r["mode"] for r in meta["runs"]] == ["daily", "poll"]
    cov = series["cov"]
    assert cov["ria"] == "c" * 8                                # complete every day
    assert cov["rt"] == "p" * 8                                 # articles, but no coverage record: partial
    assert cov["tass"] == "m" * 8                               # feed-only and empty: its feed was not read
    assert cov["sputnik"] == "m" * 8                            # nothing at all
    assert meta["contexts"]["ukraine-war"]["ru"] and meta["narratives"][0]["checked"]["n"] == 25


def test_every_page_is_assembled_from_the_partials(built_site):
    pages = sorted(p.name for p in SITE.glob("*.html"))
    assert pages == ["archive.html", "index.html", "method.html", "narratives.html", "outlets.html"]
    for name in pages:
        html = (built_site / name).read_text(encoding="utf-8")
        assert "include:" not in html and 'class="masthead"' in html, name
    days = sorted(p.stem for p in (built_site / "data" / "days").glob("*.json"))
    assert days[0] == "2026-09-01" and days[-1] == "2026-09-08"


# ── interface strings ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def strings():
    if not NODE:
        pytest.skip("node is not installed")
    url = (SITE / "assets" / "js" / "i18n.js").as_uri()
    script = ("globalThis.location = {search: ''};"
              f"const m = await import('{url}'); console.log(JSON.stringify(m.STRINGS));")
    res = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(res.stdout)


def test_finnish_and_swedish_have_every_english_string(strings):
    en = set(strings["en"])
    for lang in ("fi", "sv"):
        assert set(strings[lang]) == en, (lang, sorted(en ^ set(strings[lang]))[:20])
        for key, value in strings[lang].items():
            # placeholders such as {n} and {day} must survive translation
            assert set(re.findall(r"\{\w+\}", value)) == set(re.findall(r"\{\w+\}", strings["en"][key])), (lang, key)


def test_every_string_the_pages_ask_for_exists(strings):
    used = set()
    for p in list(SITE.rglob("*.html")):
        text = p.read_text(encoding="utf-8")
        used |= set(re.findall(r'data-i18n="([^"]+)"', text))
        for pairs in re.findall(r'data-i18n-attr="([^"]+)"', text):
            used |= {pair.split(":", 1)[1].strip() for pair in pairs.split(";") if ":" in pair}
    for p in (SITE / "assets" / "js").glob("*.js"):
        used |= set(re.findall(r'\bt\("([a-z0-9_.]+)"', p.read_text(encoding="utf-8")))
    missing = sorted(k for k in used if k not in strings["en"])
    assert not missing, missing


@needs_node
@pytest.mark.parametrize("module", sorted(p.name for p in (SITE / "assets" / "js").glob("*.js")))
def test_javascript_modules_parse(module, tmp_path):
    copy = tmp_path / module.replace(".js", ".mjs")
    copy.write_text((SITE / "assets" / "js" / module).read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run([NODE, "--check", str(copy)], check=True, capture_output=True)
