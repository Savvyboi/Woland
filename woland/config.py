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
    cookies: dict = field(default_factory=dict)  # cookies an anonymous visitor's browser holds for this site
    headline: str = "meta"  # where the headline is read: meta (og:title …) or h1
    note: dict = field(default_factory=dict)  # what readers should know about its coverage (en / fi / sv)
    budget: float | None = None  # the most minutes one run spends on this outlet (a slow site's cap)

    @property
    def host(self) -> str:
        return re.sub(r"^https?://", "", self.home).split("/")[0]

    @property
    def domain(self) -> str:
        """The site's domain without "www.", e.g. gazeta.ru (cookies are scoped to it)."""
        return re.sub(r"^www\.", "", self.host)

    def fetcher(self, **kw):
        from .net import Fetcher
        return Fetcher(gap=self.rate, cookies=self.cookies, cookie_domain=self.domain, **kw)

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
            "enabled": self.enabled, "note": self.note or None,
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
            feed_fulltext=bool(o.get("feed_fulltext", False)), cookies=dict(o.get("cookies") or {}),
            headline=o.get("headline", "meta"), note=o.get("note") or {},
            budget=float(o["budget"]) if o.get("budget") else None,
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
    # lang -> [pattern, ...]; an item is a pattern string, or a group
    # {"match": [patterns], "with": [context names], "not": [phrases], "ctx": [the context names' patterns]}
    patterns: dict = field(default_factory=dict)
    checked: dict = field(default_factory=dict)  # a random sample of matches, read: {n, fit, date} (docs/lexicon-audit.md)

    def public(self) -> dict:
        pats = {lang: [p if isinstance(p, str) else {k: v for k, v in p.items() if k != "ctx"} for p in ps]
                for lang, ps in self.patterns.items()}
        return {"id": self.id, "family": self.family, "label": self.label, "about": self.about,
                "patterns": pats, "checked": self.checked or None}


def _as_list(v) -> list:
    return [] if v is None else [v] if isinstance(v, str) else list(v)


def load_contexts(path: Path | None = None) -> dict:
    """Named word lists that a pattern group can require nearby (`with:` in lexicon.yaml): the lexicon's own
    `contexts`, and every topic under its id."""
    raw = yaml.safe_load((path or CONFIG_DIR / "lexicon.yaml").read_text(encoding="utf-8"))
    out = {}
    for t in raw.get("topics", []):
        out[t["id"]] = {"label": t["label"], "ru": list(t.get("ru", [])), "en": list(t.get("en", []))}
    for cid, c in (raw.get("contexts") or {}).items():
        if cid in out:
            raise ValueError(f"lexicon.yaml: context {cid!r} has the same id as a topic")
        out[cid] = {"label": c.get("label", {}), "ru": list(c.get("ru", [])), "en": list(c.get("en", []))}
    return out


def load_lexicon(path: Path | None = None) -> list[Narrative]:
    raw = yaml.safe_load((path or CONFIG_DIR / "lexicon.yaml").read_text(encoding="utf-8"))
    contexts = load_contexts(path)
    out = []
    for family, key in (("framing", "framings"), ("topic", "topics")):
        for n in raw.get(key, []):
            patterns = {}
            for lang in ("ru", "en"):
                items = []
                for p in n.get(lang, []) or []:
                    if isinstance(p, str):
                        items.append(p)
                        continue
                    names = _as_list(p.get("with"))
                    unknown = [c for c in names if c not in contexts]
                    if unknown or not _as_list(p.get("match")):
                        raise ValueError(f"lexicon.yaml, {n['id']}: bad pattern group {p!r} (unknown: {unknown})")
                    group = {"match": _as_list(p["match"])}
                    if names:
                        group["with"] = names
                        group["ctx"] = [w for c in names for w in contexts[c][lang]]
                    if p.get("not"):
                        group["not"] = _as_list(p["not"])
                    items.append(group)
                patterns[lang] = items
            out.append(Narrative(id=n["id"], family=family, label=n["label"], about=n.get("about", {}),
                                 patterns=patterns, checked=n.get("checked") or {}))
    ids = [n.id for n in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate narrative ids in lexicon.yaml")
    return out
