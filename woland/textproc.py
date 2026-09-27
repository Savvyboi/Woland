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


# ── "Rising words" ────────────────────────────────────────────────────────────
# Words that fill headlines every day without saying what the day was about, and the outlets' own names
# ("ТАСС: …"). Only "rising words" leaves them out; the search index keeps them.
RISING_STOP = set("""
part parts start starts started begin begins began set sets take takes took taking make makes made making
see sees seen show shows showed shown discuss discusses discussed hold holds held get gets got give gives
gave keep keeps come comes came go goes going went put puts bring brings need needs want wants plan plans
planned ready possible likely due key major main top high low big old next latest former level issue issues
side sides case cases way ways number numbers point points place places move moves step steps work works
working use uses used using help helps helped continue continues continued remain remains remained become
becomes became return returns returned receive receives received offer offers offered consider considers
considered expect expects expected note notes noted stress stresses stressed confirm confirms confirmed
reveal reveals revealed warn warns warned urge urges urged name names named ask asks asked tell meet meets
met calls call called let lets run runs time times today yesterday tomorrow country countries world
region regions city cities head chief official officials leader leaders president minister ministry
тасс риа иносми царьград tass ria inosmi tsargrad sputnik lenta известия izvestia
""".split())

_WORD = re.compile(r"[^\W_]+")
_NAMEY = frozenset({"Surn", "Name", "Patr", "Geox", "Orgn", "Trad"})
_morph = None


def _analyzer():
    global _morph
    if _morph is None:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


@lru_cache(maxsize=400_000)
def lemma(form: str, capitalised: bool) -> str:
    """Dictionary form of a Russian word (pymorphy3). A capitalised word prefers a name's reading
    (Козлова → козлов, the surname), a lower-case one any other (козлов → козел, the goat); a word the
    dictionary does not know falls back to its Snowball stem, which treats all its forms alike."""
    parses = _analyzer().parse(form)
    preferred = [p for p in parses if bool(_NAMEY & p.tag.grammemes) == capitalised]
    p = (preferred or parses)[0]
    return normalize(p.normal_form) if p.is_known else stem(form)


def headline_words(title: str) -> list[tuple[int, str, str]]:
    """(position, surface form, key) for the words of a headline that "rising words" counts: the lemma of
    a Russian word, the Snowball stem of any other; numbers, short and stop words, outlets' names left out.
    Positions count every word of the headline, so that neighbours can be recognised."""
    out = []
    for i, m in enumerate(_WORD.finditer(title)):
        surface = m.group()
        form = normalize(surface)
        if form.isdigit() or len(form) < 3 or is_stop(form) or form in RISING_STOP:
            continue
        if _CYR.search(form):
            key = lemma(form, surface[:1].isupper() and not surface.isupper())
        else:
            key = stem(form)
        if key not in RISING_STOP:
            out.append((i, surface, key))
    return out
