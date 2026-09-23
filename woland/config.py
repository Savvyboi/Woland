"""Loading config/outlets.yaml and config/lexicon.yaml."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("WOLAND_CONFIG", ROOT / "config"))
DATA_DIR = Path(os.environ.get("WOLAND_DATA", ROOT / "data"))

# The chronicle starts on this Moscow date; the collector fills any gap back to it.
START_DATE = date.fromisoformat(os.environ.get("WOLAND_START", "2026-09-01"))

GROUPS = ("state", "official", "mass", "foreign", "hardline")


@dataclass
class Outlet:
    id: str
    name: str
    name_ru: str
    lang: str
    group: str
    home: str
    about: dict
    article: re.Pattern
    sources: list[dict]
    fetch: bool = True
    rate: float = 0.6
    poll: bool = False
    enabled: bool = True
    eu_blocked: bool = False
    coverage_sitemap: str | None = None
    tz_fix: bool = False  # the site writes Moscow wall-clock time under a wrong UTC offset
    parallel: int = 2     # article pages fetched at once (the per-host pause still applies)
    feed_fulltext: bool = False  # feed-only, but the feed carries complete texts

    @property
    def host(self) -> str:
        return re.sub(r"^https?://", "", self.home).split("/")[0]

    @property
    def can_backfill(self) -> bool:
        """Can older days be collected, or only what the feeds hold right now?"""
        return self.fetch or any(s["type"] != "rss" or s.get("backfill_only") for s in self.sources)

    @property
    def method(self) -> str:
        if self.fetch:
            return "page"
        return "feedtext" if self.feed_fulltext else "feed"

    def is_article(self, url: str) -> bool:
        return bool(self.article.search(url))

    def public(self) -> dict:
        """What the website is told about the outlet."""
        return {
            "id": self.id, "name": self.name, "name_ru": self.name_ru, "lang": self.lang,
            "group": self.group, "home": self.home, "about": self.about,
            "eu_blocked": self.eu_blocked, "method": self.method,
            "enabled": self.enabled,
        }


def load_outlets(path: Path | None = None, include_disabled: bool = False) -> list[Outlet]:
    raw = yaml.safe_load((path or CONFIG_DIR / "outlets.yaml").read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    outlets = []
    for o in raw["outlets"]:
        o = {**defaults, **o}
        if o["group"] not in GROUPS:
            raise ValueError(f"{o['id']}: unknown group {o['group']!r}")
        outlet = Outlet(
            id=o["id"], name=o["name"], name_ru=o.get("name_ru", o["name"]), lang=o["lang"],
            group=o["group"], home=o["home"], about=o.get("about", {}),
            article=re.compile(o["article"]), sources=o.get("sources", []),
            fetch=bool(o.get("fetch", True)), rate=float(o.get("rate", 0.6)),
            poll=bool(o.get("poll", False)), enabled=bool(o.get("enabled", True)),
            eu_blocked=bool(o.get("eu_blocked", False)), coverage_sitemap=o.get("coverage_sitemap"),
            tz_fix=bool(o.get("tz_fix", False)), parallel=max(1, int(o.get("parallel", 2))),
            feed_fulltext=bool(o.get("feed_fulltext", False)),
        )
        if outlet.enabled or include_disabled:
            outlets.append(outlet)
    ids = [o.id for o in outlets]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate outlet ids in outlets.yaml")
    return outlets


@dataclass
class Narrative:
    id: str
    family: str  # framing | topic
    label: dict
    about: dict
    patterns: dict = field(default_factory=dict)  # lang -> [pattern, ...]

    def public(self) -> dict:
        return {"id": self.id, "family": self.family, "label": self.label, "about": self.about,
                "patterns": self.patterns}


def load_lexicon(path: Path | None = None) -> list[Narrative]:
    raw = yaml.safe_load((path or CONFIG_DIR / "lexicon.yaml").read_text(encoding="utf-8"))
    out = []
    for family, key in (("framing", "framings"), ("topic", "topics")):
        for n in raw.get(key, []):
            out.append(Narrative(
                id=n["id"], family=family, label=n["label"], about=n.get("about", {}),
                patterns={lang: list(n.get(lang, [])) for lang in ("ru", "en")},
            ))
    ids = [n.id for n in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate narrative ids in lexicon.yaml")
    return out
