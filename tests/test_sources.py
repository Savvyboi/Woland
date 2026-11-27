"""Who is cited (woland/sources.py): a headline's speaker sorted into one of four buckets, and the citation
flows from one outlet or channel to another."""
from __future__ import annotations

import pytest

from woland.analysis import voice
from woland.sources import BUCKETS, classify, is_fringe_to_state, speakers

CASES = [
    # (headline, bucket, source key for a cited outlet)
    ("Песков: Кремль не комментирует слухи", "named_official", None),
    ("Лавров заявил о провокации Запада", "named_official", None),
    ("Захарова высмеяла Каллас", "named_official", None),
    ("Посол Небензя заявил о срыве переговоров", "named_official", None),
    ("Генерал Попов предупредил о наступлении", "named_official", None),
    ("Премьер Латвии заявила о новых мерах", "named_official", None),
    ("В Минобороны заявили об ударе по складам", "named_official", None),
    ("В Кремле ответили на слова Макрона", "named_official", None),
    ("Марочко рассказал о положении под Купянском", "named_other", None),
    ("Экс-советник Пентагона Макгрегор заявил о поражении Киева", "named_other", None),
    ("Военкор Поддубный сообщил о прорыве", "named_other", None),
    ("Источник: Киев готовит провокацию", "anonymous_expert", None),
    ("Источники рассказали о переговорах в Абу-Даби", "anonymous_expert", None),
    ("Эксперт объяснил рост цен на бензин", "anonymous_expert", None),
    ("Американский эксперт заявил о слабости НАТО", "anonymous_expert", None),
    ("Политолог предупредил Европу", "anonymous_expert", None),
    ("Аналитик назвал сроки окончания конфликта", "anonymous_expert", None),
    ("Врач назвала опасные продукты", "anonymous_expert", None),
    ("Депутат Госдумы призвал запретить мигрантам", "anonymous_expert", None),
    ("Bloomberg: США готовят новые санкции", "cited_outlet", "bloomberg"),
    ("СМИ сообщили о взрыве в Одессе", "anonymous_expert", None),          # media left unnamed
    ("ТАСС: в Москве открылся форум", "cited_outlet", "tass"),
    ("Readovka: в Курской области сбит беспилотник", "cited_outlet", "readovka"),
    ("SHOT: в Подмосковье загорелся склад", "cited_outlet", "shot"),
    ("Telegram-канал Mash сообщил о задержании", "cited_outlet", "mash"),
    ("Царьград: Запад готовит удар", "cited_outlet", "tsargrad"),
]


@pytest.mark.parametrize("title, bucket, key", CASES)
def test_a_speaker_falls_in_one_bucket(title, bucket, key):
    v = voice(title, "ru")
    assert v, title
    assert classify(title, v[0], v[1]) == (bucket, key)


@pytest.mark.parametrize("title, bucket", [
    ("Russia warns West – Lavrov", "named_official"),
    ("Energy Minister says output will grow", "named_official"),
    ("Kremlin Aide reveals the summit's agenda", "anonymous_expert"),
    ("Russian Diplomat says talks stalled", "anonymous_expert"),
    ("Scott Ritter says Kiev has lost", "named_other"),
])
def test_english_speakers(title, bucket):
    v = voice(title, "en")
    assert v and classify(title, v[0], v[1])[0] == bucket


def test_fringe_to_state_is_a_fringe_source_cited_by_a_state_outlet():
    sp = speakers()
    assert is_fringe_to_state("shot", "ria", sp) and is_fringe_to_state("tsargrad", "tass", sp)
    assert is_fringe_to_state("mash", "vesti", sp)
    assert not is_fringe_to_state("shot", "kp", sp)            # Komsomolskaya Pravda is not a state outlet
    assert not is_fringe_to_state("bloomberg", "ria", sp)      # a foreign outlet is not fringe
    assert set(BUCKETS) == {"named_official", "named_other", "anonymous_expert", "cited_outlet"}
