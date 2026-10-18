"""What the Analysis page shows beyond framing counts, worked out at build time from headlines and leads:

- **voices**: who a headline quotes, and with which verb. "Песков: …", "Лавров заявил…", "В Кремле ответили…",
  "Putin says…", "… – Lavrov". A speaker is a person, an institution or place speaking for one ("В Кремле",
  "Пентагон", "Kremlin"), an unnamed role ("Эксперт", "Врач", "analyst") or a news outlet quoted ("СМИ",
  "Bloomberg"). Headline patterns, not reading: a quoted name in the middle of a headline is not found.
- **countries**: which countries a headline and lead name (config/countries.yaml).
- **stories**: the same story in several outlets on one Moscow day, found by comparing headlines and leads in
  their English form (the machine translations of Russian ones), so that English and Russian versions meet:
  who published it first, and how long the others took.
- **tags**: the outlets' own tags and sections, as stored (`g`, `s`).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from functools import lru_cache

import yaml

from .config import CONFIG_DIR
from .textproc import _analyzer, is_stop, lemma, stem, tokens
from .util import normalize

# ── voices ────────────────────────────────────────────────────────────────────
# Speech verbs in the masculine past ("заявил"); the feminine, neuter and plural forms are made from them. Each
# belongs to a kind: says (neutral), judges (an evaluation of someone), warns (a warning, threat, demand or
# promise), reveals ("раскрыл", the clickbait verb of advice and explainer pieces), advises. Verbs that as often
# mean something else are left out ("отметил" a jubilee, "разгромил" a rival team).
VERBS_RU = {
    "says": "заявил сообщил рассказал ответил объяснил уточнил напомнил прокомментировал высказался "
            "подчеркнул признал заметил сказал пояснил добавил констатировал признался",
    "judges": "назвал оценил раскритиковал обвинил осудил высмеял упрекнул похвалил усомнился возмутился "
              "отверг опроверг унизил",
    "warns": "предупредил пригрозил призвал потребовал пообещал допустил предсказал спрогнозировал предложил",
    "reveals": "раскрыл рассекретил",
    "advises": "посоветовал порекомендовал",
}
VERBS_EN = {
    "says": "says said tells told claims claimed insists explains notes admits confirms",
    "judges": "slams blasts mocks accuses calls condemns denies praises dismisses ridicules rejects criticizes "
              "criticises lambasts",
    "warns": "warns threatens urges demands vows predicts proposes suggests",
    "reveals": "reveals",
    "advises": "advises recommends",
}


def _ru_forms(word: str) -> list[str]:
    if word.endswith("ся"):
        base = word[:-2]  # высказал(ся)
        return [f"{base}ся", f"{base}ась", f"{base}ось", f"{base}ись"]
    return [word, f"{word}а", f"{word}о", f"{word}и"]


VERB_KIND: dict[str, str] = {}   # form → kind
VERB_BASE: dict[str, str] = {}   # form → the masculine form shown
for _kind, _words in VERBS_RU.items():
    for _w in _words.split():
        for _f in _ru_forms(_w):
            VERB_KIND[_f], VERB_BASE[_f] = _kind, _w
for _kind, _words in VERBS_EN.items():
    for _w in _words.split():
        VERB_KIND[_w], VERB_BASE[_w] = _kind, _w
PLURAL_RU = {f for f in VERB_KIND if f.endswith(("и", "ись")) and re.search(r"[а-я]", f)}
KINDS = ("quotes", "says", "judges", "warns", "reveals", "advises")  # quotes: "Name: «…»"
SPEAKERS = ("person", "inst", "role", "media")

MEDIA = {normalize(m) for m in """
СМИ Bloomberg FT Reuters Politico Axios CNN NYT WSJ AP AFP BBC Guardian Telegraph Times Spiegel Bild Welt
Economist Newsweek Forbes NBC CBS ABC Haaretz Yle Strana Страна.ua Политико Би-би-си Блумберг Рейтер Синьхуа
Xinhua Nikkei Yonhap ТАСС РИА Известия Life Mash Baza Shot SHOT Readovka TV
""".split()} | {"the telegraph", "the times", "the guardian", "financial times", "new york times", "the new york times",
               "wall street journal", "washington post", "the washington post", "daily mail", "fox news",
               "al jazeera", "global times", "le monde", "le figaro", "риа новости", "the economist",
               "national interest", "the national interest", "responsible statecraft", "the american conservative"}
# opening words that are not a speaker: "Видео: …", "Опрос: …", "LIVE: …"
COLON_STOP = {normalize(w) for w in """
видео фото онлайн опрос тест итоги прогноз мнение эксклюзив срочно молния главное подробности хроника карта обзор
инфографика рецепт гороскоп live update updates watch video photos poll exclusive breaking analysis opinion op-ed
explainer quiz factbox трансляция расписание новости важное колонка интервью репортаж мнения
""".split()}
COLON_STOP |= {"in brief", "in-brief"}
# institutions the dictionary does not tag as such, and one name it takes for a common noun
INST_RU = {"кремль", "запад", "пентагон", "госдума", "совфед", "минфин", "минобороны", "минздрав", "киев",
           "вашингтон", "брюссель", "пекин", "лондон", "париж", "берлин", "офис президента", "белый дом"}
PERSON_RU = {"мадьяр"}
INST_ALIAS = {"мид рф": "МИД России", "гд": "Госдума", "госдума рф": "Госдума", "совфеде": "Совфед",
              "сф": "Совфед", "совфед рф": "Совфед", "рф": "Россия", "минобороны рф": "Минобороны России",
              "минобороны": "Минобороны России", "мо рф": "Минобороны России", "мид": "МИД России",
              "кремле": "Кремль", "оп": "Офис президента Украины", "офис президента": "Офис президента Украины",
              "сша": "США", "ес": "ЕС"}
ROLE_SUFFIX = ("эксперт", "аналитик", "политолог", "экономист", "историк", "врач", "психолог", "депутат",
               "дипломат", "советник", "чиновник")
ROLE_EN = set("""analyst analysts expert experts official officials source sources envoy diplomat diplomats
lawmaker lawmakers senator spokesman spokeswoman spokesperson minister general commander scientist
scientists economist economists doctor doctors journalist journalists veteran politician politicians insider
insiders ambassador mayor governor deputy mp mps mep meps ceo director head chief""".split())
NOT_SPEAKER_EN = set("""reports report study survey poll data statement source sources media analysis video photos
watch""".split())
INST_EN_LAST = set("""bank ministry office department service committee council parliament government embassy army
forces fund agency commission""".split())
INST_EN = set("""kremlin moscow kiev kyiv washington pentagon nato eu brussels un beijing london paris berlin
tehran tokyo warsaw riga tallinn vilnius helsinki stockholm minsk ankara seoul pyongyang delhi baku yerevan
tbilisi chisinau budapest belgrade rome madrid mod russia ukraine china us usa uk
iran israel germany france poland finland sweden japan india turkey hamas hezbollah iaea who""".split())

_NAME_EN = r"[A-Z][\w.'’-]*"
_SUFFIX_EN = re.compile(rf"\s[–—-]\s*({_NAME_EN}(?:\s+{_NAME_EN}){{0,3}})\s*$")
_COLON = re.compile(r"^([^:«»\"“”!?()]{2,60}?):\s+\S")
_WORDS = re.compile(r"[^\s«»\"“”,;:!?()]+")
_TROUBLE = re.compile(r"[—–«»\"“”:()]")   # before a speech verb: the verb belongs to a quotation or a clause


def _parses(word: str):
    return _analyzer().parse(word)


def _known(word: str, *tags: str) -> bool:
    return any(p.is_known and any(t in p.tag for t in tags) for p in _parses(word))


def _nominative(word: str) -> bool:
    ps = _parses(word)
    return not any(p.is_known for p in ps) or any("nomn" in p.tag or "Fixd" in p.tag for p in ps)


def _a_name(word: str) -> bool:
    """A surname or name, or a word the dictionary does not know (most foreign names) — not "Латвии"."""
    ps = _parses(word)
    return not any(p.is_known for p in ps) or _known(word, "Surn", "Name") or \
        any(p.is_known and "nomn" in p.tag and "sing" in p.tag and "Geox" not in p.tag for p in ps)


def _abbr(word: str) -> bool:
    return len(word) >= 2 and word.upper() == word and any(c.isalpha() for c in word)


def _is_role_ru(word: str) -> bool:
    """A common noun for a person: эксперт, врач, учёные, военэксперт — not a name."""
    f = normalize(word)
    if len(f) < 3 or f in PERSON_RU:
        return False
    if f.endswith(ROLE_SUFFIX):
        return True
    return not _known(word, "Name", "Surn", "Patr") and \
        any(p.is_known and "NOUN" in p.tag and "anim" in p.tag for p in _parses(word))


def _is_inst_ru(word: str) -> bool:
    return _abbr(word) or normalize(word) in INST_RU or _known(word, "Orgn", "Geox")


def _role_lemma(word: str) -> str:
    for p in _parses(word):
        if p.is_known and "NOUN" in p.tag and "anim" in p.tag:
            return normalize(p.normal_form)
    return normalize(word)


def _inst_name(name: str) -> str:
    return INST_ALIAS.get(normalize(name), name)


def _place_ru(words: list[str]) -> str:
    """"Кремле" → "Кремль", "Белом доме" → "Белый дом", "МИД России" → "МИД России": the words up to the first
    noun in their dictionary form, the rest as written."""
    words = [w for w in words if w[:1].isupper() or not is_stop(normalize(w))]
    out, done = [], False
    for w in words:
        if done:
            out.append(w)
            continue
        p = next((p for p in _parses(w) if p.is_known), None)
        if p is None or "Fixd" in p.tag or _abbr(w):
            out.append(w)
            done = p is None or "NOUN" in p.tag or _abbr(w)
            continue
        nf = p.normal_form
        out.append(nf[:1].upper() + nf[1:] if w[:1].isupper() else nf)
        done = "NOUN" in p.tag
    s = " ".join(out)
    return _inst_name(s[:1].upper() + s[1:])


def _speaker_ru(words: list[str]) -> tuple[str, str] | None:
    """(name, kind) of the speaker named by the words before a speech verb or a colon, or None."""
    if not words or len(words) > 5 or not words[0][:1].isupper() or normalize(words[0]) in COLON_STOP:
        return None
    phrase = " ".join(words)
    if normalize(words[0]) in MEDIA and normalize(phrase) not in MEDIA:
        return words[0], "media"            # "СМИ узнали, кто…"
    if normalize(phrase) in MEDIA or (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9 .&'’-]*", phrase) and len(words) <= 4):
        return phrase, "media"
    if normalize(phrase) in INST_RU or normalize(phrase) in INST_ALIAS:
        return _inst_name(phrase), "inst"
    last = words[-1]
    if not _nominative(last):
        # the last word depends on an earlier one: "МИД Китая", "Премьер Латвии"
        if len(words) > 3 or not _nominative(words[0]):
            return None
        if _is_inst_ru(words[0]):
            return _inst_name(phrase), "inst"
        if _is_role_ru(words[0]):
            return phrase, "person"   # an office, held by someone: "Премьер Латвии"
        return None
    # a name at the end: "Мария Захарова", "Глава МИД Венгрии Сийярто", "Экс-советник Пентагона Макгрегор"
    run: list[str] = []
    for w in reversed(words):
        if not w[:1].isupper() or _abbr(w) or normalize(w) in INST_RU:
            break
        if run and not _nominative(w):
            break
        if _known(w, "Orgn", "Geox") and not _known(w, "Name", "Surn"):
            break
        if _is_role_ru(w):
            break
        run.insert(0, w)
        if len(run) == 3:
            break
    if run:
        return " ".join(run), "person"
    if _is_role_ru(last):
        return _role_lemma(last).capitalize(), "role"
    if _is_inst_ru(last):
        return _inst_name(phrase if len(words) <= 3 else last), "inst"
    return None


def voice_ru(title: str) -> tuple[str, str, str, str] | None:
    """(speaker, kind of speaker, verb, kind of verb) for a Russian headline, or None."""
    m = _COLON.match(title)
    if m and not re.search(r"\d", m.group(1)) and len(m.group(1).split()) <= 4:
        sp = _speaker_ru(_WORDS.findall(m.group(1)))
        if sp:
            return sp[0], sp[1], ":", "quotes"
    for m in re.finditer(r"[^\W\d_]+", title[:120]):
        f = normalize(m.group())
        if f not in VERB_KIND or not re.search(r"[а-я]", f):
            continue
        prefix = title[:m.start()].rstrip()
        if prefix.endswith((",", "—", "–", "-")):
            # "…, заявил Песков": the speaker follows the verb
            after = _WORDS.findall(title[m.end():])[:3]
            sp = _speaker_ru(after) if after and after[0][:1].isupper() else None
            if sp is None and after and _is_role_ru(after[0]):
                sp = (_role_lemma(after[0]).capitalize(), "role")
            return (sp[0], sp[1], VERB_BASE[f], VERB_KIND[f]) if sp else None
        if _TROUBLE.search(prefix) or "," in prefix:
            return None
        before = _WORDS.findall(prefix)
        if f in PLURAL_RU and before and normalize(before[0]) in ("в", "во", "на") and 1 < len(before) <= 4:
            return _place_ru(before[1:]), "inst", VERB_BASE[f], VERB_KIND[f]
        sp = _speaker_ru(before)
        return (sp[0], sp[1], VERB_BASE[f], VERB_KIND[f]) if sp else None
    return None


def _speaker_en(words: list[str]) -> tuple[str, str] | None:
    words = [w for w in words if not re.search(r"['’]s$", w)] or words  # "Russia's Lavrov" → "Lavrov"
    if not words or len(words) > 7 or normalize(words[-1]) in NOT_SPEAKER_EN:
        return None
    phrase = " ".join(words)
    if normalize(phrase) in COLON_STOP:
        return None
    if normalize(phrase) in MEDIA or normalize(words[-1]) in MEDIA:
        return phrase, "media"
    run: list[str] = []
    for w in reversed(words):
        if not w[:1].isupper():
            break
        run.insert(0, w)
        if len(run) == 3:
            break
    if run:
        name = " ".join(run)
        last = normalize(run[-1])
        if last in ROLE_EN:
            return (name, "person") if len(run) > 1 else (run[-1].capitalize() if not _abbr(run[-1]) else run[-1], "role")
        if normalize(name) in INST_EN or last in INST_EN or last in INST_EN_LAST or _abbr(run[-1]):
            return name, "inst"
        return name, "person"
    if normalize(words[-1]) in INST_EN_LAST:
        return " ".join(words[-3:]).capitalize(), "inst"
    if normalize(words[-1]) in ROLE_EN:
        return words[-1].capitalize(), "role"
    return None


def voice_en(title: str) -> tuple[str, str, str, str] | None:
    m = _SUFFIX_EN.search(title)
    if m:
        sp = _speaker_en(m.group(1).split())
        if sp:
            return sp[0], sp[1], ":", "quotes"
    m = _COLON.match(title)
    if m and not re.search(r"\d", m.group(1)) and len(m.group(1).split()) <= 4:
        sp = _speaker_en(m.group(1).split())
        if sp:
            return sp[0], sp[1], ":", "quotes"
    words = title.split()
    for i, w in enumerate(words[:9]):
        f = normalize(w.strip(",.;"))
        if f in VERB_KIND and re.search(r"[a-z]", f) and i:
            if _TROUBLE.search(" ".join(words[:i])):
                return None
            sp = _speaker_en(words[:i])
            return (sp[0], sp[1], VERB_BASE[f], VERB_KIND[f]) if sp else None
    return None


def voice(title: str, lang: str) -> tuple[str, str, str, str] | None:
    return voice_en(title) if lang == "en" else voice_ru(title)


def voice_key(name: str, kind: str) -> str:
    """One speaker under one key, however named: a person by the last word of the name ("Мария Захарова",
    "Министр Захарова" and "Захарова" → "захарова"; "Donald Trump" and "Trump" → "trump"); an office ("Премьер
    Латвии"), an institution, a role or an outlet by the whole name."""
    words = name.split()
    if kind == "role":
        return normalize(name)
    if kind == "person" and len(words) > 1 and normalize(words[-1]) not in ROLE_EN and \
            (re.search(r"[A-Za-z]", words[-1]) or _a_name(words[-1])):
        return normalize(words[-1])
    return normalize(name)


# ── countries ─────────────────────────────────────────────────────────────────
class Gazetteer:
    """config/countries.yaml, ready for matching."""

    def __init__(self, path=None):
        data = yaml.safe_load(open(path or CONFIG_DIR / "countries.yaml", encoding="utf-8")) or {}
        self.codes = sorted(data)
        self.names = {code: (names.get("en") or [code])[0] for code, names in data.items()}  # for searching
        self.ru: dict[tuple, list] = {}   # lemmas → [(code, case rule per word)]
        self.en: dict[tuple, list] = {}
        self.longest = 1
        self.ru_prefixes: set[tuple] = set()   # every beginning of a name, to stop looking early
        self.ru_stems: set[str] = set()        # the Snowball stems of every word of a name
        self.en_prefixes: set[tuple] = set()
        for code, names in data.items():
            for name in names.get("ru") or []:
                words = re.findall(r"[^\W_]+", name)
                key = tuple(self._ru_key(w, w[:1].isupper()) for w in words)
                for w in words:
                    self.ru_stems.add(stem(normalize(w)))
                    for p in _parses(w)[:3]:     # and of all its forms: "Китай" → "кита", "Китае" → "кит"
                        self.ru_stems.update(stem(normalize(f.word)) for f in p.lexeme)
                self.ru.setdefault(key, []).append((code, [self._rule(w) for w in words]))
                self.longest = max(self.longest, len(key))
                self.ru_prefixes.update(key[:i] for i in range(1, len(key) + 1))
            for name in names.get("en") or []:
                words = re.findall(r"[^\W_]+", name)
                key = tuple(normalize(w) for w in words)
                self.en.setdefault(key, []).append((code, [self._rule(w) for w in words]))
                self.longest = max(self.longest, len(key))
                self.en_prefixes.update(key[:i] for i in range(1, len(key) + 1))

    @staticmethod
    def _rule(w: str) -> str:
        return "upper" if len(w) > 1 and w.isupper() else "cap" if w[:1].isupper() else "any"

    @staticmethod
    def _ru_key(w: str, cap: bool) -> str:
        f = normalize(w)
        return lemma(f, cap) if re.search(r"[а-я]", f) and not (len(w) > 1 and w.isupper()) else f

    @staticmethod
    def _fits(word: str, rule: str) -> bool:
        return rule == "any" or (rule == "cap" and word[:1].isupper()) or (rule == "upper" and word.isupper())

    def find(self, text: str, lang: str) -> set[str]:
        words = re.findall(r"[^\W_]+", text)
        if lang == "ru":
            keys = []
            for w in words:
                if stem(normalize(w)) not in self.ru_stems:   # (the dictionary is slow: ask it only when it may help)
                    keys.append(set())
                    continue
                cap = w[:1].isupper()
                k = {self._ru_key(w, cap)}
                if cap:
                    k.add(self._ru_key(w, False))   # "Финский" at the start of a headline
                keys.append(k)
            table, prefixes = self.ru, self.ru_prefixes
        else:
            keys = [{normalize(w)} for w in words]
            table, prefixes = self.en, self.en_prefixes
        found = set()
        for i in range(len(words)):
            paths = [(k,) for k in keys[i] if (k,) in prefixes]
            while paths:
                longer = []
                for path in paths:
                    n = len(path)
                    for code, rules in table.get(path, ()):
                        if all(self._fits(w, r) for w, r in zip(words[i:i + n], rules)):
                            found.add(code)
                    if i + n < len(words):
                        longer += [path + (k,) for k in keys[i + n] if path + (k,) in prefixes]
                paths = longer
        return found


# ── stories ───────────────────────────────────────────────────────────────────
STORY_SIM = 0.3       # how alike (cosine, tf-idf) an article must be to a story's articles on average
STORY_COMMON = 0.05   # words in more than this share of the day's articles say nothing about the story


def story_terms(rec: dict, lang: str) -> Counter:
    """The words a story is recognised by: the English headline (counted twice) and the start of the lead."""
    if lang == "en":
        head, lead = rec.get("t", ""), rec.get("d", "")
    else:
        head, lead = rec.get("te") or rec.get("t", ""), rec.get("de") or rec.get("d", "")
    words = lambda s: [stem(x) for x in tokens(s) if not is_stop(x) and not x.isdigit()]  # noqa: E731
    c = Counter(words(lead[:200]))
    for w in words(head):
        c[w] += 2
    return c


def stories(recs: list[dict], langs: list[str]) -> list[list[int]]:
    """Group a day's articles into stories: lists of indices into `recs`, each in order of publication.

    Articles are taken in order of publication; each joins the story whose articles it resembles most on
    average (cosine similarity of tf-idf vectors, at least STORY_SIM), or starts one. Comparing with the average
    rather than the nearest article keeps one story from chaining into the next."""
    n = len(recs)
    bags = [story_terms(r, lang) for r, lang in zip(recs, langs)]
    df = Counter()
    for b in bags:
        df.update(b.keys())
    vecs = []
    for b in bags:
        v = {w: (1 + math.log(c)) * math.log(n / df[w]) for w, c in b.items() if 2 <= df[w] < max(n * STORY_COMMON, 5)}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({w: x / norm for w, x in v.items()})
    postings = defaultdict(list)
    for i, v in enumerate(vecs):
        for w, x in v.items():
            postings[w].append((i, x))
    order = sorted(range(n), key=lambda i: (recs[i]["p"], i))
    groups: list[list[int]] = []
    group_of: dict[int, int] = {}
    for i in order:
        sims = Counter()
        for w, x in vecs[i].items():
            for j, y in postings[w]:
                if j in group_of:
                    sims[j] += x * y
        score = Counter()
        for j, s in sims.items():
            score[group_of[j]] += s
        best, best_s = None, 0.0
        for g, s in score.items():
            s /= len(groups[g])
            if s > best_s:
                best, best_s = g, s
        if best is not None and best_s >= STORY_SIM:
            groups[best].append(i)
            group_of[i] = best
        else:
            group_of[i] = len(groups)
            groups.append([i])
    return groups


@lru_cache(maxsize=1)
def gazetteer() -> Gazetteer:
    return Gazetteer()
