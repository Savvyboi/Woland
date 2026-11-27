"""Who is cited: the speakers that headlines name (woland/analysis.voice), sorted into four buckets
(config/speakers.yaml), and which outlets cite which other outlets and Telegram channels.

Per outlet, the **anonymous authority ratio**: of its headlines that name a speaker, the share that rely on one
left unnamed ("эксперт", "источник", "врач", "sources"). Per pair, the **citation flow**: how often a source
(another outlet, an agency, a Telegram channel) is named as the speaker of a citing outlet's headline. A flow
from a fringe source (a Telegram channel, or an outlet Woland calls hardline) to a state outlet (RIA Novosti,
TASS and the other outlets of the state group) is marked: the way a claim made on the margins reaches the state
press. An outlet naming itself ("ТАСС: …" in TASS) is its own reporting, and not counted.

Only headlines are read: a source named in the lead or the text is not counted, so the ratios describe how
headlines attribute, not how articles source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from .analysis import ROLE_EN, voice_key
from .config import CONFIG_DIR, load_outlets
from .util import normalize

BUCKETS = ("named_official", "named_other", "anonymous_expert", "cited_outlet")
# a speaker left unnamed, by the first word: "Источник в Минобороны", "Собеседник агентства", "Sources"
ANON_STEMS = ("источник", "собеседник", "инсайдер", "осведомлен", "осведомлён", "эксперт", "аналитик", "наблюдател",
              "source", "insider", "expert", "analyst", "observer")
# offices one person holds at a time, so that "Премьер Латвии" names someone; "Депутат Госдумы" does not
UNIQUE_OFFICES = ("президент", "премьер", "премьер-министр", "глава", "министр", "генсек", "канцлер", "спикер", "мэр",
                  "губернатор", "пресс-секретарь", "король", "постпред", "полпред", "командующий", "генпрокурор",
                  "president", "prime", "premier", "chancellor", "speaker", "mayor", "governor", "minister", "ceo",
                  "head", "chief", "secretary", "spokesman", "spokeswoman", "spokesperson")
UNNAMED_MEDIA = {"сми", "media", "сmi", "местные сми", "западные сми", "американские сми"}
FORMER = re.compile(r"(^|[\s-])(экс|бывш\w*|ex|former)([\s-]|$)", re.I)
CHANNEL = re.compile(r"^(telegram|телеграм)[- ]?(канал|channel)\s+|^(канал|channel)\s+", re.I)


@dataclass
class Speakers:
    officials: set[str]
    offices: set[str]
    telegram: set[str]
    fringe: set[str]          # keys of fringe sources: Telegram channels, hardline outlets and the listed ones
    wires: set[str]           # the outlets citations into which are flagged: the state group (outlets.yaml)
    own: dict[str, str] = field(default_factory=dict)   # an outlet's name (normalized) → its id


@lru_cache(maxsize=1)
def speakers() -> Speakers:
    raw = yaml.safe_load((CONFIG_DIR / "speakers.yaml").read_text(encoding="utf-8"))
    low = lambda xs: {normalize(str(x)) for x in xs or []}  # noqa: E731
    outlets = load_outlets(include_disabled=True)
    own = {}
    for o in outlets:
        if o.group == "official":       # "Кремль" speaking is the institution, not Kremlin.ru
            continue
        for name in {o.name, o.name_ru, o.id}:
            own[normalize(name)] = o.id
    own |= {"риа": "ria", "тасс": "tass", "известия": "iz", "russia today": "rt"}
    fringe = low(raw.get("fringe")) | low(raw.get("telegram")) | {o.id for o in outlets if o.group == "hardline"}
    return Speakers(officials=low(raw.get("officials")), offices=low(raw.get("offices")),
                    telegram=low(raw.get("telegram")), fringe=fringe,
                    wires={o.id for o in outlets if o.group == "state"}, own=own)


def classify(title: str, name: str, kind: str, sp: Speakers | None = None) -> tuple[str, str | None]:
    """(bucket, source key) for a headline's speaker (analysis.voice: name and kind). The key is given for a
    cited outlet only: an observed outlet's id, otherwise the source's name in lower case."""
    sp = sp or speakers()
    channel = CHANNEL.search(name)
    bare = CHANNEL.sub("", name).strip() if channel else name
    n = normalize(bare)
    if n in UNNAMED_MEDIA:       # "СМИ сообщили": reports left unnamed
        return "anonymous_expert", None
    if kind == "media" or channel or n in sp.telegram or n in sp.fringe or (n in sp.own and kind != "inst"):
        return "cited_outlet", sp.own.get(n, n)
    words = [normalize(w) for w in name.split()]
    first = words[0] if words else ""
    if kind == "role" or first.startswith(ANON_STEMS):
        return "anonymous_expert", None
    if kind == "inst":
        return "named_official", None
    # an office rather than a name: "Премьер Латвии", "Депутат Госдумы", "Energy Minister", "Kremlin Aide". One
    # held by one person at a time names someone; one held by many ("депутат", "diplomat") does not
    if len(words) > 1 and (first in sp.offices or words[-1] in ROLE_EN or words[-1] in sp.offices):
        if not FORMER.search(name) and any(w in UNIQUE_OFFICES for w in words):
            return "named_official", None
        return "anonymous_expert", None
    if voice_key(name, kind) in sp.officials:
        return "named_official", None
    i = title.find(name)
    before = title[:i] if i > 0 else ""
    if before and not FORMER.search(before):
        if any(normalize(w) in sp.offices for w in re.findall(r"[\w-]+", before)[-4:]):
            return "named_official", None
    return "named_other", None


def is_fringe_to_state(source: str, citing: str, sp: Speakers | None = None) -> bool:
    sp = sp or speakers()
    return source in sp.fringe and citing in sp.wires
