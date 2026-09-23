"""Tokenising and stemming for the search index and for "rising words".

Stemming (Snowball) happens only here, at build time. The browser never stems: each index shard
ships a map from every word form seen in the corpus to its stem.
"""
from __future__ import annotations

import re
from functools import lru_cache

import snowballstemmer

from .util import normalize

_TOKEN = re.compile(r"[^\W_]+")
_CYR = re.compile(r"[а-яіїєґ]")
_LAT = re.compile(r"[a-z]")

_ru = snowballstemmer.stemmer("russian")
_en = snowballstemmer.stemmer("english")

STOP_RU = set("""
а без более больше будет будто бы был была были было быть в вам вас ведь весь во вот впрочем все всего всех всю вы
где да даже для до другой его ее ей ему если есть еще ж же за зачем здесь и из или им иногда их к как какая какой
когда конечно кто куда ли лучше между меня мне много может можно мой моя мы на над надо наконец нас не него нее ней
нельзя нет ни нибудь никогда ним них ничего но ну о об один он она они опять от перед по под после потом потому
почти при про раз разве с сам свою себе себя сейчас со совсем так также такой там тебя тем теперь то тогда того
тоже только том тот три тут ты у уж уже хорошо хоть чего чем через что чтоб чтобы чуть эти этого этой этом этот
эту это я который которая которые которых которой котором которым также ещё
свой своя свое свои своего своей своему своим своими своих свою своем

заявил заявила заявили заявляет рассказал рассказала рассказали назвал назвала назвали сообщил сообщила сообщили
сообщает стало известно раскрыл раскрыла раскрыли оценил оценила оценили ответил ответила ответили призвал призвала
призвали высказался высказалась высказались объяснил объяснила объяснили допустил допустила допустили пообещал
пообещала пообещали указал указала указали предупредил предупредила предупредили отметил отметила отметили
году года год лет время день дня дней человек человека людей глава главы
""".split())

STOP_EN = set("""
a an the and or but if of to in on at by for with from as is are was were be been being it its this that these
those he she they we you i his her their our your not no has have had will would can could should may might says
said say over after before into about up out than more most new also who what which when where how why all any
some just now amid via per over under against between during without within while since until again very can't
won't don't doesn't didn't isn't aren't wasn't weren't it's he's she's there here them him us me my mine yours
one two three first last year years day days week time people man woman told tells according report reports
reported claims claimed
""".split())


def tokens(text: str) -> list[str]:
    """Normalised word tokens (lower case, ё → е), numbers limited to 2–4 digits."""
    out = []
    for t in _TOKEN.findall(normalize(text)):
        if t.isdigit():
            if 2 <= len(t) <= 4:
                out.append(t)
        elif len(t) >= 2:
            out.append(t)
    return out


@lru_cache(maxsize=400_000)
def stem(token: str) -> str:
    if _CYR.search(token):
        return _ru.stemWord(token)
    if _LAT.search(token):
        return _en.stemWord(token)
    return token


def is_stop(token: str) -> bool:
    return token in STOP_RU or token in STOP_EN


def index_terms(text: str) -> list[tuple[str, str]]:
    """(surface form, stem) pairs for indexing, stop words removed."""
    return [(t, stem(t)) for t in tokens(text) if not is_stop(t)]
