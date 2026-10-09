"""Unit and smoke tests. Run with: python -m pytest -q"""
from __future__ import annotations

import gzip
import json
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest

from woland import build as buildmod
from woland import store
from woland.config import ROOT, Narrative, load_lexicon, load_outlets
from woland.discover import fill, parse_feed, parse_sitemap
from woland.extract import clean_lead, clean_title, extract, first_paragraph
from woland.lexicon import Lexicon, snippet
from woland.textproc import index_terms, stem, tokens
from woland.util import MSK, canonical_url, clean, parse_dt


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


def test_a_group_needs_its_context_and_skips_excluded_phrases():
    contexts = ["украин*", "всу"]
    lex = Lexicon([Narrative(id="n", family="framing", label={}, about={}, patterns={"ru": [
        {"match": ["теракт*"], "with": ["x"], "ctx": contexts},
        {"match": ["вброс*"], "not": ["вброс* бюллетен*"]},
    ]})])
    assert lex.find("В Дагестане боевик получил срок за подготовку теракта", "ru") == {}
    assert "n" in lex.find("СК завел дело о теракте после атаки ВСУ", "ru")
    assert "n" in lex.find("СК завел дело о теракте", "ru", extra="Беспилотник ВСУ атаковал город")
    assert lex.find("Памфилова прокомментировала вброс бюллетеней", "ru") == {}
    assert "n" in lex.find("Вброс бюллетеней и вбросы о мобилизации", "ru")      # the second one counts
    # in a full text the context must be close enough to appear in the snippet
    far = "Теракт. " + "Слово " * 40 + "ВСУ"
    assert lex.find(far, "ru", window=50) == {} and "n" in lex.find(far, "ru")
    head, body = lex.tag("Заголовок", "", far.replace("Теракт.", "Про ВСУ и теракт."), "ru")
    assert "ВСУ" in body["n"]


def test_a_gap_stands_for_up_to_three_words_and_a_quotation_mark():
    lex = lex_of(ru=[{"match": ["иноагент*"], "not": ["внесен* ~ в реестр ~ иноагент*"]},
                     {"match": ["новороссия"], "not": ["трасс* ~ новороссия"]}])
    assert lex.find("Дудь (внесен Минюстом России в реестр иноагентов) дал интервью", "ru") == {}
    assert lex.find("Внесён в реестр лиц, выполняющих функции иноагента", "ru") == {}
    assert "n" in lex.find("Минюст внес в реестр иноагентов пятерых журналистов", "ru")   # news: active voice
    assert "n" in lex.find("Законопроект внесен в Госдуму: реестр для иноагентов расширят", "ru")
    assert lex.find("ДТП на трассе Р-280 «Новороссия»", "ru") == {}
    assert lex.find('Пробка на трассе "Новороссия"', "ru") == {}
    assert "n" in lex.find("Новороссия и Малороссия в учебниках", "ru")
    with pytest.raises(ValueError):
        lex_of(ru=["~ иноагент*"])


def test_the_lexicon_file_resolves_contexts_and_topics():
    narratives = {n.id: n for n in load_lexicon()}
    groups = [p for p in narratives["terrorism"].patterns["ru"] if not isinstance(p, str)]
    assert groups and "всу" in groups[0]["ctx"]
    public = narratives["terrorism"].public()["patterns"]["ru"]
    assert all(isinstance(p, str) or "ctx" not in p for p in public)     # the site gets names, not lists
    lex = Lexicon(list(narratives.values()))
    assert "terrorism" not in lex.find("ЦРУ рассекретило сводки о подготовке к терактам 11 сентября", "ru")
    assert "liberation" in lex.find("После воссоединения с Россией жители Херсонской области голосуют", "ru")
    assert "liberation" not in lex.find("Россия и Украина готовят воссоединение семей", "ru")


LEXICON_TEXTS = [
    ("ru", "Киевский режим готовит провокацию в Донбассе", ""),
    ("ru", "В Дагестане боевик получил 15 лет за подготовку теракта", ""),
    ("ru", "СК завел дело о теракте после атак ВСУ на Нижнекамск", ""),
    ("ru", "Захарова прокомментировала теракты против членов избиркомов", "Удары украинских дронов"),
    ("ru", "472 квартиры повреждены при атаке БПЛА на Новороссийск", ""),
    ("ru", "Жители Донбасса и Новороссии впервые после воссоединения с Россией выбирают депутатов", ""),
    ("ru", "Памфилова прокомментировала вброс бюллетеней на участке в Коми", ""),
    ("ru", "Путин: вбросы о мобилизации – задуманная информационная операция", ""),
    ("ru", "ФСБ рассекретила документы о злодеяниях немецких фашистов под Сталинградом", ""),
    ("ru", "Россия должна разгромить нацистскую Украину, чтобы избежать столкновения с Западом", ""),
    ("ru", "Победа над фашизмом в Европе: ветераны вспоминают", ""),
    ("ru", "Депутат Аксаков предупредил о фейковом аккаунте от его имени", ""),
    ("ru", "Памфилова: фейки о недопуске наблюдателей не подтвердились", ""),
    ("ru", "Нелегитимный президент Украины Владимир Зеленский отстранил генпрокурора", ""),
    ("ru", "Росавиация назвала нелегитимным заявление Украины о воздушном пространстве", ""),
    ("ru", "Ёлки-палки: НАЦИСТЫ на Украине и неонацисты в Европе", ""),
    ("ru", "Лавров: устранение первопричин конфликта необходимо", ""),
    ("ru", "Однако первопричина проблем с иммунитетом — в питании", ""),
    ("ru", "Хохлы, хохлушка и Георгий Хохлов", ""),
    ("ru", "Washington Examiner: США нечего противопоставить ракете «Буревестник»", ""),
    ("ru", "Жильцы кооператива «Буревестник» просят защитить их дачи", ""),
    ("ru", "Спецоперация продолжается, заявил участник СВО", ""),
    ("ru", "Он вернулся к своим после смены политического курса", ""),
    ("ru", "Сменивший пол активист и смена пола в Европе", ""),
    ("ru", "Текст статьи. " + "Слово " * 30 + "теракт на рынке, " + "слово " * 30 + "атака ВСУ", ""),
    ("ru", "Рэпер Моргенштерн (внесен Минюстом РФ в реестр иноагентов) высказался о возвращении", ""),
    ("ru", "Ходорковский внесён Минюстом России в список лиц, выполняющих функции иноагента", ""),
    ("ru", "«Дождь» (признан иноагентом и нежелательной организацией в РФ) и Deutsche Welle", ""),
    ("ru", "Минюст признал иноагентом политолога и внёс в перечень нежелательных организаций НКО", ""),
    ("ru", "Авария на 19-м км автодороги Р-280 «Новороссия» и история Новороссии", ""),
    ("ru", "Никиты массово отказываются от исконно русского отчества; Одесса — исконно русский город", ""),
    ("ru", "Пенсионерка поверила создателям фейковой интернет-биржи; ВСУ снимают фейковые видео", ""),
    ("en", "Sarmat, Poseidon and Burevestnik missiles; the Boeing P·8 Poseidon anti·submarine aircraft", ""),
    ("en", "Kiev regime staged a provocation, Moscow says", ""),
    ("en", "Ukrainian troops staged 53 shelling attacks", ""),
    ("en", "Report proves the Bucha massacre was staged by Kiev", ""),
    ("en", "Germany forgets it lost WWII, still acting like Nazis", ""),
    ("en", "Europe's support for the Nazi regime in Kiev is a disgrace", ""),
    ("en", "Revolut hands data over after fake government requests", ""),
    ("en", "Terrorist attack in Pakistan kills 12", ""),
    ("en", "Kiev's terrorist attack on Bryansk condemned", ""),
]


def test_python_and_browser_match_the_same_words():
    """site/assets/js/lexicon.js must count exactly what woland/lexicon.py counts."""
    from woland.config import load_contexts
    narratives = load_lexicon()
    lex = Lexicon(narratives)
    meta = {"narratives": [n.public() for n in narratives], "contexts": load_contexts()}
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    url = (ROOT / "site" / "assets" / "js" / "lexicon.js").as_uri()
    script = (f"import * as L from '{url}';\n"
              "const [meta, texts] = JSON.parse(await new Response(process.stdin).text());\n"
              "const lex = L.compileLexicon(meta.narratives, meta.contexts);\n"
              "console.log(JSON.stringify(texts.map(([lang, t, e]) => [L.find(lex, t, lang, e), L.find(lex, t, lang, e, 50)])));")
    out = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps([meta, LEXICON_TEXTS]),
                         capture_output=True, text=True, encoding="utf-8", check=True)
    js = json.loads(out.stdout)
    for (lang, t, e), (whole, windowed) in zip(LEXICON_TEXTS, js):
        py = {k: list(v) for k, v in lex.find(t, lang, extra=e).items()}
        py50 = {k: list(v) for k, v in lex.find(t, lang, extra=e, window=50).items()}
        assert whole == py and windowed == py50, t


def test_a_framings_matches_can_be_sampled_for_reading(archive):
    from woland import audit
    day = date(2026, 9, 10)
    recs = [{"id": f"ria:{i}", "o": "ria", "u": f"https://ria.ru/20260910/{i}.html", "p": "2026-09-10T10:00:00+03:00",
             "t": f"Новость {i}", "w": 0, "h": "0" * 16, "r": "2026-09-10T08:00:00Z", "via": "page"} for i in range(40)]
    for i in range(0, 40, 4):
        recs[i]["t"] = f"Киевский режим готовит провокацию {i}"                      # counted from the headline
    recs[1]["d"] = "Лавров назвал действия киевского режима провокацией"               # from the lead
    recs[2]["kb"] = {"kyiv-regime": "…и снова киевский режим…"}                        # from the text
    recs[3]["kb"] = {"kyiv-regime": "…слово, которого нет в словаре…"}                 # no longer matches: not counted
    store.write_day(day, "ria", recs)
    total, rows = audit.sample("kyiv-regime", n=5, seed=3)
    assert total == 12 and len(rows) == 5 and rows == audit.sample("kyiv-regime", n=5, seed=3)[1]
    assert all("[[" in r["excerpt"] and r["fits"] == "" for r in rows)
    where = {r["id"]: r["where"] for r in audit.sample("kyiv-regime", n=12)[1]}
    assert where["ria:0"] == "headline" and where["ria:1"] == "lead" and where["ria:2"] == "text"


def test_the_glossary_corrects_names_only_where_the_russian_has_them():
    from woland.glossary import Glossary
    g = Glossary()
    assert g.fix("Уиткофф прилетел в Москву", "Whitkoff arrived in Moscow") == "Witkoff arrived in Moscow"
    assert g.fix("Трамп послал Зеленского к Маску", "Trump sent Zelensky to the Mask") == "Trump sent Zelensky to the Musk"
    assert g.fix("Маска для лица защитит от гриппа", "Mask for face will protect") == "Mask for face will protect"
    assert g.fix("Старейший луна-парк закрылся", "Moon park closed") == "Amusement park closed"
    assert g.fix("Раскрыто условие окончания СВО", "The end of the SBO") == "The end of the SVO"
    assert g.fix("Глава СВР и участники СВО", "SVR head and SVO participants") == "SVR head and SVO participants"
    assert g.fix("СК Великобритании", "UK police") == "UK police"                    # the United Kingdom
    assert g.fix("Сальдо торгового баланса выросло", "Balance of trade grew") == "Balance of trade grew"
    assert g.fix("Власти Запорожья", "Zaporizhzhzhia, Zaporizhzhia") == "Zaporizhzhia, Zaporizhzhia"
    assert g.fix("Удар по «Запорожстали» в Запорожье", "Strike on Zaporizhstal in Zaporozhye") == \
        "Strike on Zaporizhstal in Zaporizhzhia"                                       # the steelworks keep their name
    assert g.fix("Армия ударила по «Запорожстали»", "The army hit the Zaporizstal") == "The army hit the Zaporizhstal"
    assert g.fix("Мост открыл красный «Запорожец»", "A red Zaporozhets opened the bridge") == \
        "A red Zaporozhets opened the bridge"                                          # and so does the car
    assert g.fix("Погода в Москве", "Mask and SBO") == "Mask and SBO"               # nothing to correct
    # page furniture the model writes instead of a sentence's first words is left out
    assert g.fix("Сальдо: Киеву всё сложнее", "Previous articleKiev is increasingly difficult") == \
        "Kiev is increasingly difficult"
    assert g.fix("Лид. Второе.", "A lead. Previous article The second.") == "A lead. The second."
    assert g.fix("Это предыдущая статья", "This is the previous article") == "This is the previous article"
    assert g.fix("Матвиенко: СФ одобрил", "Matvienko: SF approved") == "Matvienko: Federation Council approved"


def test_rising_words_group_word_forms_by_lemma():
    from woland.textproc import headline_words
    keys = lambda t: [k for _, _, k in headline_words(t)]
    assert keys("Козлов заявил") == keys("Задержан Козлова")[1:] == ["козлов"]      # one surname, two cases
    assert "медведев" in keys("Медведев предупредил") and "медведь" in keys("Медведи вышли к селу")
    assert keys("ТАСС: часть рейсов задержана")[0] != "тасс"                      # outlets' names left out
    assert "part" not in keys("Lavrov to take part in talks")


def test_a_rising_word_must_be_more_than_chance(tmp_path):
    import math
    assert buildmod.poisson_tail(0, 3.0) == 1.0
    assert math.isclose(buildmod.poisson_tail(1, 1.0), 1 - math.exp(-1))
    assert math.isclose(buildmod.poisson_tail(5, 0.5), 1.7212e-4, rel_tol=1e-3)
    b = buildmod.Builder(tmp_path / "site")
    day = lambda df, n=200: {"totals": {"tass-en": n}, "df": {"ru": {}, "en": df}, "forms": {"ru": {}, "en": {}},
                             "posts": {"ru": {}, "en": {w: list(range(c)) for w, c in df.items()}},
                             "stem_ex": {"ru": {}, "en": {}}}
    history = {f"2026-09-{i:02d}": day({"near": 2, "lavrov": 4}) for i in range(1, 15)}
    history["2026-09-15"] = day({"near": 5, "rubio": 9, "lavrov": 5})
    rising = [r["k"] for r in b.rising(date(2026, 9, 15), history)["en"]]
    # a name never seen before rises; a common word used five times instead of twice is chance
    assert rising == ["rubio"]


def test_the_run_log_keeps_the_nightly_runs_among_frequent_polls():
    runs = [{"at": "2026-09-27T01:17:00Z", "mode": "daily"}] + \
        [{"at": f"2026-09-27T{h:02d}:30:00Z", "mode": "poll"} for h in range(2, 23)] + \
        [{"at": "2026-09-27T00:05:00Z", "mode": "backfill"}, {"mode": "poll"}]      # finished later; no time
    shown = buildmod.recent_runs(runs)
    assert [r["mode"] for r in shown] == ["backfill", "daily"] + ["poll"] * 9
    assert [r["at"] for r in shown] == sorted(r["at"] for r in shown)


def test_the_run_log_says_in_words_what_went_wrong():
    """The Outlets page words each problem in the reader's language; the messages themselves go along."""
    problems = buildmod.run_problems
    timeout = ("html_list: https://www.mk.ru/news/2026/9/1/: ConnectTimeout: HTTPSConnectionPool(host='www.mk.ru', "
               "port=443): Max retries exceeded with url: /news/2026/9/1/ (Caused by ConnectTimeoutError(…))")
    mk = problems({"aborted": "time budget exhausted", "errors": [timeout]})
    assert mk["c"] == ["budget", "noanswer"] and mk["t"].startswith("time budget exhausted; html_list:")
    assert len(mk["t"]) <= 300
    assert problems({"errors": ["rss: https://aif.ru/rss/news.php: 404", "sitemap_index: https://aif.ru/sitemap.xml: 404"]})["c"] \
        == ["http 404"]
    assert problems({"aborted": "unreachable (401)"})["c"] == ["refused"]
    assert problems({"errors": ["rss: https://tass.ru/rss/yandex.xml: no items; https://tass.ru/rss/v2.xml: bot check"]})["c"] \
        == ["refused"]
    assert problems({"errors": ["rss: https://tass.ru/rss/yandex.xml: no items"]})["c"] == ["empty"]
    assert problems({"aborted": "no connection to tass.ru"})["c"] == ["noanswer"]
    assert problems({"error": "KeyError: 'p'"})["c"] == ["failed"]
    assert problems({"errors": [], "aborted": ""}) is None


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


def test_izvestias_video_items_are_recognised():
    iz = next(o for o in load_outlets() if o.id == "iz")
    video = re.compile(iz.video)  # (the site compiles the same pattern in JavaScript)
    assert video.search("https://iz.ru/2158617/video/vladimir-putin-obratilsia-k-shkolnikam-i-studentam")
    assert not video.search("https://iz.ru/2158618/politika/video-s-mesta-sobytii")
    assert iz.public()["video"] == iz.video


def test_cleaners():
    assert clean_title("Оппозиция Армении: вывод базы - Новости на Вести.ru") == "Оппозиция Армении: вывод базы"
    assert clean_lead("Последние новости на сайте Вести: Текст новости..") == "Текст новости."
    assert clean_lead("Текст... РИА Новости Спорт, 23.09.2026") == "Текст…"
    assert clean("the 8<sup>th</sup> Russia&ndash;China <b>Forum</b>, 40 м<sup>2</sup>") == "the 8th Russia–China Forum , 40 м2"


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
    examples = json.loads((out / "data" / "days" / "2026-09-10.ex.json").read_text(encoding="utf-8"))
    assert row["n"] == 1 and examples["kyiv-regime"][0]["t"].startswith("Киевский режим")
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


def test_the_opening_paragraph_is_not_the_headline_repeated():
    title = "Эксперт Созонова: как выбрать художественную студию для ребёнка"
    body = f"{title}\nПри выборе художественной студии для ребёнка родителям следует смотреть не только на программу.\n"
    assert first_paragraph(body, title).startswith("При выборе художественной студии")
