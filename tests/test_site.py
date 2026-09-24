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
]


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
                if te:
                    rec["te"] = te
                recs.append(rec)
            store.write_day(d, outlet, recs)
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
