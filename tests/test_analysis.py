"""The Analysis page's measures (woland/analysis.py): who a headline quotes, which countries it names, and
which articles of a day tell the same story."""
from __future__ import annotations

import pytest

from woland import analysis
from woland.analysis import voice, voice_key


@pytest.mark.parametrize("title, lang, expected", [
    ("Песков: Россия открыта к диалогу", "ru", ("Песков", "person", ":", "quotes")),
    ("Лавров обвинил Запад в провокациях", "ru", ("Лавров", "person", "обвинил", "judges")),
    ("Мария Захарова высмеяла заявление Каллас", "ru", ("Мария Захарова", "person", "высмеял", "judges")),
    ("Глава МИД Венгрии Сийярто заявил о поддержке", "ru", ("Сийярто", "person", "заявил", "says")),
    ("В Кремле ответили на слова Мерца", "ru", ("Кремль", "inst", "ответил", "says")),
    ("В Белом доме назвали условия сделки", "ru", ("Белый дом", "inst", "назвал", "judges")),
    ("Эксперт раскрыл, где нельзя хранить пароли", "ru", ("Эксперт", "role", "раскрыл", "reveals")),
    ("Помощь Киеву закончится, заявил Песков", "ru", ("Песков", "person", "заявил", "says")),
    ("СМИ: США готовят новые санкции", "ru", ("СМИ", "media", ":", "quotes")),
    ("Bloomberg: Британия передаст Украине ракеты", "ru", ("Bloomberg", "media", ":", "quotes")),
    ("Putin says the West is losing", "en", ("Putin", "person", "says", "says")),
    ("West is waging war on Russia – Lavrov", "en", ("Lavrov", "person", ":", "quotes")),
    ("North Korea fires several missiles, Seoul says", "en", ("Seoul", "inst", "says", "says")),
])
def test_voices_found_in_headlines(title, lang, expected):
    assert voice(title, lang) == expected


@pytest.mark.parametrize("title, lang", [
    ("Россиянам рассказали о росте пенсий", "ru"),          # a dative: the people told, not the speaker
    ("«Это дебилизм!»: призер осудила невыдачу виз", "ru"),  # the verb belongs to a quotation's clause
    ("СМИ узнали, кто предложил замедлить Starlink", "ru"),  # "предложил" is not what the outlet did
    ("Видео: пожар на складе в Подмосковье", "ru"),          # a label, not a speaker
    ("Finland closes the border again", "en"),
])
def test_headlines_without_a_speaker(title, lang):
    v = voice(title, lang)
    assert v is None or (title.startswith("СМИ") and v[2] != "предложил")


def test_one_speaker_however_named():
    assert voice_key("Мария Захарова", "person") == voice_key("Захарова", "person") == "захарова"
    assert voice_key("Donald Trump", "person") == voice_key("Trump", "person") == "trump"
    assert voice_key("Премьер Латвии", "person") == "премьер латвии"       # an office: the whole name


def test_countries_in_every_form_and_case_rules():
    g = analysis.gazetteer()
    assert g.find("В Хельсинки заявили о закрытии границы с Россией", "ru") == {"FI", "RU"}
    assert g.find("Финский премьер и южнокорейский министр", "ru") == {"FI", "KR"}
    assert g.find("США и Южная Корея провели учения", "ru") == {"US", "KR"}
    assert g.find("Белый дом ответил", "ru") == {"US"} and g.find("белый дом у дороги", "ru") == set()
    assert g.find("Чад", "ru") == {"TD"} and g.find("чад от костра", "ru") == set()
    assert g.find("Tell us about the US", "en") == {"US"}                  # "us" is not the United States
    assert g.find("South Korea and Kyiv", "en") == {"KR", "UA"}


def rec(o, p, t, te=None, d=""):
    return {"o": o, "p": f"2026-10-15T{p}:00+03:00", "t": t, "te": te, "d": d, "u": f"https://{o}/{p}", "id": f"{o}:{p}"}


def test_stories_group_the_same_event_across_languages_and_keep_others_apart():
    recs = [
        rec("tass", "09:00", "В Ярославской области задержали участкового после пожара на заводе пиротехники",
            "In the Yaroslavl region, a precinct officer was detained after a fire at a fireworks factory"),
        rec("ria", "09:20", "Участкового задержали после пожара на заводе пиротехники",
            "Precinct officer detained after fire at fireworks factory"),
        rec("rt", "10:05", "Police officer detained over fire at Yaroslavl fireworks factory"),
        rec("vesti", "11:00", "Задержан участковый по делу о пожаре на заводе пиротехники",
            "Precinct officer detained in fireworks factory fire case"),
        rec("ria", "09:30", "Захарова поздравила Баскова с юбилеем", "Zakharova congratulated Baskov on his anniversary"),
        rec("mk", "12:00", "Захарова раскрыла неожиданную сторону Баскова", "Zakharova revealed the unexpected side of Baskov"),
    ] + [rec("lenta", f"{10 + i:02d}:{i:02d}", f"Новость {i}", f"Unrelated news item number {i} about {w}")
         for i, w in enumerate(["weather", "football", "pensions", "taxes", "schools", "roads", "prices", "music"])]
    langs = ["en" if r["o"] == "rt" else "ru" for r in recs]
    groups = analysis.stories(recs, langs)
    fire = next(g for g in groups if 0 in g)
    assert sorted(fire) == [0, 1, 2, 3]                       # Russian and English versions together, in time order
    assert fire == sorted(fire, key=lambda i: recs[i]["p"])
    assert not any(4 in g for g in groups if 0 in g)
