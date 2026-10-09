"""Corrections to the machine translation of names and recurring terms (config/glossary.yaml).

Applied when the site is built, so that a new entry corrects the whole archive; data/ keeps the model's
own output. `python -m woland mtcheck` reports what every entry does to the archive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import CONFIG_DIR


@dataclass
class Entry:
    ru: re.Pattern
    wrong: re.Pattern
    en: str
    not_ru: re.Pattern | None = None
    right: re.Pattern | None = None

    def applies(self, ru: str) -> bool:
        return bool(self.ru.search(ru)) and not (self.not_ru and self.not_ru.search(ru))

    def fix(self, en: str) -> str:
        def repl(m: re.Match) -> str:
            out = self.en
            if m.group(0)[:1].isupper() and out[:1].islower():  # "Moon park" at the start → "Amusement park"
                out = out[0].upper() + out[1:]
            return out
        return self.wrong.sub(repl, en)


def load_glossary(path: Path | None = None) -> list[Entry]:
    p = path or CONFIG_DIR / "glossary.yaml"
    if not p.exists():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for e in raw.get("entries") or []:
        wrong = "|".join(f"(?:{w})" for w in e["wrong"])
        out.append(Entry(ru=re.compile(e["ru"]), wrong=re.compile(rf"(?<!\w)(?:{wrong})(?!\w)"), en=e["en"],
                         not_ru=re.compile(e["not"]) if e.get("not") else None,
                         right=re.compile(rf"(?<!\w){re.escape(e['en'])}(?!\w)", re.I)))
    return out


# Page furniture the model sometimes writes at the start of a sentence instead of its first words
# ("Сальдо: Киеву все тяжелее…" → "Previous articleKiev is increasingly…": 113 headlines and 32 leads
# in October 2026). It is left out.
_FURNITURE = re.compile(r"(?:^|(?<=[.!?…] ))Previous article\s*")


class Glossary:
    def __init__(self, entries: list[Entry] | None = None):
        self.entries = load_glossary() if entries is None else entries

    def fix(self, ru: str, en: str) -> str:
        """The translation `en` of the Russian text `ru`, corrected."""
        if not en:
            return en
        en = _FURNITURE.sub("", en)
        for e in self.entries:
            if e.applies(ru):
                en = e.fix(en)
        return en

    def fingerprint(self) -> str:
        from .util import short_hash
        return short_hash(repr([(e.ru.pattern, e.wrong.pattern, e.en, e.not_ru and e.not_ru.pattern)
                                for e in self.entries]), 8)


def report(records) -> str:
    """For every entry: Russian headlines and leads it concerns, translations it corrects, and translations
    that still lack the right rendering afterwards (with a few examples, to find new mistakes)."""
    entries = load_glossary()
    stats = [[0, 0, []] for _ in entries]
    for r in records:
        for ru, en in ((r.get("t", ""), r.get("te", "")), (r.get("d", ""), r.get("de", ""))):
            if not en:
                continue
            for i, e in enumerate(entries):
                if not e.applies(ru):
                    continue
                s = stats[i]
                s[0] += 1
                fixed = e.fix(en)
                s[1] += fixed != en
                if not e.right.search(fixed) and len(s[2]) < 3:
                    s[2].append(f"{ru[:70]} | {fixed[:70]}")
    lines = [f"{'Russian':34} {'texts':>9} {'corrected':>9}  → English"]
    for e, (n, fixed, missing) in zip(entries, stats):
        lines.append(f"{e.ru.pattern[:34]:34} {n:9} {fixed:9}  → {e.en}")
        lines += [f"{'':36}still without it: {m}" for m in missing]
    return "\n".join(lines)
