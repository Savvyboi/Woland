"""Unit and smoke tests. Run with: python -m pytest -q"""
from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest

from woland import build as buildmod
from woland import store
from woland.config import ROOT, Narrative, load_lexicon, load_outlets
from woland.discover import fill, parse_feed, parse_sitemap
from woland.extract import clean_lead, clean_title, extract
from woland.lexicon import Lexicon, snippet
from woland.textproc import index_terms, stem, tokens
from woland.util import MSK, canonical_url, parse_dt


# ── dates ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw, expected", [
    ("20260923T0006", datetime(2026, 9, 23, 0, 6, tzinfo=MSK)),                       # RIA
    ("2026-09-24T00:09:42+0300", datetime(2026, 9, 24, 0, 9, 42, tzinfo=MSK)),         # MK
    ("2026-09-23T20:55:03.000Z", datetime(2026, 9, 23, 20, 55, 3, tzinfo=timezone.utc)),
    ("Wed, 23 Sep 2026 21:16:00 +0300", datetime(2026, 9, 23, 21, 16, tzinfo=MSK)),    # RSS
    ("1790111169", datetime.fromtimestamp(1790111169, timezone.utc)),                  # epoch
    ("23.09.2026 14:05", datetime(2026, 9, 23, 14, 5, tzinfo=MSK)),
])
def test_parse_dt(raw, expected):
    assert parse_dt(raw) == expected


def test_canonical_url():
    assert canonical_url("https://x.ru/a?utm_source=tg&id=5#top") == "https://x.ru/a?id=5"
    assert canonical_url("https://x.ru/a?utm_medium=rss") == "https://x.ru/a"


# ── lexicon ───────────────────────────────────────────────────────────────────
def lex_of(**patterns):
    return Lexicon([Narrative(id="n", family="framing", label={}, about={}, patterns=patterns)])


def test_prefix_exact_and_phrase_patterns():
    lex = lex_of(ru=["нацист*", "сво", "киевск* режим*"], en=["nazi*", "kiev* regime*"])
    assert lex.find("Бойцы уничтожили неонацистов", "ru") == {}          # prefix must start the word
    assert "n" in lex.find("Действия нацистов осуждены", "ru")
    assert "n" in lex.find("В зоне СВО", "ru")
    assert lex.find("Он вернулся к своим", "ru") == {}                   # "сво" is an exact word
    assert "n" in lex.find("преступления Киевского   режима", "ru")      # phrase, any endings, spacing
    assert "n" in lex.find("The Kiev regime's forces", "en")
    assert "n" in lex.find("Ёлки: НАЦИСТЫ", "ru")


def test_lexicon_file_compiles_and_tags():
    lex = Lexicon(load_lexicon())
    head, body = lex.tag("Лавров: киевский режим готовит провокацию", "",
                         "Текст статьи. Западные кураторы Киева молчат о неонацистах.", "ru")
    assert {"kyiv-regime", "provocation"} <= head
    assert "collective-west" in body and "кураторы" in body["collective-west"]


def test_snippet_is_short_and_centred():
    text = "слово " * 100 + "ЦЕЛЬ" + " слово" * 100
    i = text.index("ЦЕЛЬ")
    s = snippet(text, i, i + 4)
    assert "ЦЕЛЬ" in s and len(s) <= 175 and s.startswith("…") and s.endswith("…")


# ── extraction ────────────────────────────────────────────────────────────────
PAGE = """<html><head>
<meta property="og:title" content="Лавров начинает визит в Нью-Йорк - РИА Новости, 23.09.2026">
<meta property="og:description" content="Министр посетит Нью-Йорк. РИА Новости, 23.09.2026">
<meta property="article:published_time" content="20260923T0006">
<meta property="article:tag" content="США"><meta property="article:tag" content="ООН">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"NewsArticle",
 "headline":"x","author":{"@type":"Person","name":"Иван Петров"},"articleSection":"В мире"}</script>
</head><body><article><h1>Лавров</h1><p>Первый абзац статьи о визите министра в Нью-Йорк.</p>
<p>Второй абзац статьи, где говорится о переговорах и о ситуации вокруг Украины и НАТО.</p></article></body></html>"""


def test_extract_page():
    info = extract(PAGE, "https://ria.ru/20260923/lavrov-1.html")
    assert info["title"] == "Лавров начинает визит в Нью-Йорк"
    assert info["lead"] == "Министр посетит Нью-Йорк."
    assert info["published"] == datetime(2026, 9, 23, 0, 6, tzinfo=MSK)
    assert info["tags"] == ["США", "ООН"] and info["author"] == "Иван Петров"
    assert info["section"] == "В мире"


def test_cleaners():
    assert clean_title("Оппозиция Армении: вывод базы - Новости на Вести.ru") == "Оппозиция Армении: вывод базы"
    assert clean_lead("Последние новости на сайте Вести: Текст новости..") == "Текст новости."
    assert clean_lead("Текст... РИА Новости Спорт, 23.09.2026") == "Текст…"


# ── discovery ─────────────────────────────────────────────────────────────────
def test_fill_keeps_regex_braces():
    d = date(2026, 9, 3)
    assert fill("https://x/{y}/{mm}/{dd}/page/{n}/", d, 2) == "https://x/2026/09/03/page/2/"
    assert fill(r"^https://ria\.ru/\d{8}/", d) == r"^https://ria\.ru/\d{8}/"
    assert fill("{msk_start}", d) == str(int(datetime(2026, 9, 3, tzinfo=MSK).timestamp()))


def test_parse_sitemap_and_feed():
    sm = """<?xml version="1.0"?><urlset xmlns:news="n"><url><loc>https://a/1</loc>
      <lastmod>2026-09-23T10:00:00+03:00</lastmod><news:news><news:publication_date>2026-09-23T09:00:00+03:00
      </news:publication_date><news:title><![CDATA[Заголовок &amp; Ко]]></news:title></news:news></url></urlset>"""
    is_index, entries = parse_sitemap(sm)
    assert not is_index and entries[0]["loc"] == "https://a/1" and entries[0]["title"] == "Заголовок & Ко"
    feed = b"""<?xml version="1.0" encoding="utf-8"?><rss><channel><item><title>T</title>
      <link>https://a/2</link><description><![CDATA[<p>Lead</p>]]></description>
      <pubDate>Wed, 23 Sep 2026 21:16:00 +0300</pubDate></item></channel></rss>"""
    items = parse_feed(feed)
    assert items[0]["link"] == "https://a/2" and items[0]["description"] == "Lead"


def test_outlets_config_is_valid():
    outlets = load_outlets(include_disabled=True)
    assert len(outlets) >= 20
    for o in outlets:
        assert o.sources, o.id
        assert o.lang in ("ru", "en")


# ── the browser and the builder must agree on tokens and shards ───────────────
WORDS = ["Зеленский", "нацистов", "ЁЛКИ", "Trump's", "СВО", "2026", "a", "Санкт-Петербург", "ВСУ", "Finland"]


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    url = (ROOT / "site" / "assets" / "js" / "textkit.js").as_uri()
    out = subprocess.run([node, "--input-type=module", "-e", f"import * as k from '{url}';\n{script}"],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_tokenizer_parity_with_browser():
    js = _node(f"console.log(JSON.stringify({json.dumps(WORDS, ensure_ascii=False)}.map(w => k.tokenize(w))))")
    assert js == [tokens(w) for w in WORDS]


def test_bucket_parity_with_browser():
    forms = ["зеленский", "зеленск", "нат", "trump", "сво", "ёж", "петербург", "ukraine"]
    js = _node(f"console.log(JSON.stringify({json.dumps(forms, ensure_ascii=False)}.map(w => k.bucket(w, {buildmod.NB}))))")
    assert js == [buildmod.bucket(w) for w in forms]


def test_index_terms_drop_stopwords_and_keep_acronyms():
    terms = dict(index_terms("Бойцы СВО вернулись к своим семьям, заявил Зеленский"))
    assert "своим" not in terms and "заявил" not in terms
    assert terms["сво"] == "сво" and terms["зеленский"] == stem("зеленский")


# ── an end-to-end build on a tiny synthetic archive ───────────────────────────
def test_build_smoke(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ART_DIR", tmp_path / "data" / "articles")
    monkeypatch.setattr(store, "STATE_DIR", tmp_path / "data" / "state")
    monkeypatch.setattr(buildmod, "CACHE", tmp_path / "cache")
    start = date(2026, 9, 1)
    for i in range(10):
        d = start + timedelta(days=i)
        recs = [{"id": f"ria:{i}{j}", "o": "ria", "u": f"https://ria.ru/{d:%Y%m%d}/a-{j}.html",
                 "p": f"{d.isoformat()}T1{j}:00:00+03:00",
                 "t": "Киевский режим готовит провокацию" if j == 0 else f"Новость номер {j} о погоде",
                 "te": "The Kiev regime is preparing a provocation" if j == 0 else "", "w": 100, "h": "x", "r": "2026-09-24"}
                for j in range(3)]
        store.write_day(d, "ria", recs)
    out = tmp_path / "site"
    buildmod.build(out_dir=str(out))
    meta = json.loads((out / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["first"] == "2026-09-01" and meta["last"] == "2026-09-10" and meta["articles"] == 30
    digest = json.loads((out / "data" / "days" / "2026-09-10.json").read_text(encoding="utf-8"))
    row = next(n for n in digest["narratives"] if n["id"] == "kyiv-regime")
    assert row["n"] == 1 and row["ex"][0]["t"].startswith("Киевский режим")
    # the index can find the word form through its stem
    st = stem("режим")
    shard = json.loads(gzip.decompress((out / "data" / "search" / "2026-09" / "i" /
                                        f"{buildmod.bucket(st)}.json.gz").read_bytes()))
    assert len(shard["p"][st]) == 10
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "include:" not in html and 'class="masthead"' in html


# ── leads that say nothing are replaced by the article's opening paragraph ─────
STUB_PAGE = """<html><head>
<meta property="og:title" content="В Ростове машина перевернулась на крышу">
<meta name="twitter:description" content="Подробнее на сайте">
<meta property="article:published_time" content="2026-09-19T21:10:00+03:00">
</head><body><article><h1>В Ростове машина перевернулась на крышу</h1>
<p>В Ростове вечером 19 сентября автомобиль перевернулся на крышу после столкновения с препятствием на улице Советской.</p>
<p>Кадры с места происшествия опубликовали очевидцы. Пострадавших, по предварительным данным, нет, сообщили в ГИБДД.</p>
<p>Движение на участке было затруднено около часа, пока эвакуатор не убрал машину с проезжей части.</p>
</article></body></html>"""


def test_a_read_more_stub_is_not_a_lead():
    info = extract(STUB_PAGE, "https://tsargrad.tv/news/x_1")
    assert info["lead"].startswith("В Ростове вечером 19 сентября автомобиль перевернулся")
    assert clean_lead("Подробнее на сайте") == "" and clean_lead("Читайте также") == ""
    assert clean_lead("Подробнее о том, как изменится транспорт, рассказал мэр.").startswith("Подробнее о том")


def test_a_template_that_repeats_the_headline_is_not_a_lead():
    page = STUB_PAGE.replace('<meta name="twitter:description" content="Подробнее на сайте">',
                             '<meta property="og:description" content="Парламентская газета. Новости: Общество. '
                             'В Ростове машина перевернулась на крышу. Дата публикации: 19.09.2026.">')
    assert extract(page, "https://www.pnp.ru/social/x.html")["lead"].startswith("В Ростове вечером 19 сентября")
