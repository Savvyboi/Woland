"""Reading an article page: headline, lead, timestamps, section, tags, author and body text.

Only headline, lead, metadata and short keyword-in-context snippets are ever stored or published;
the body text is used in memory for narrative tagging and then discarded.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import lxml.html

from .util import clean, parse_dt

log = logging.getLogger("woland.extract")

try:
    import trafilatura
except ImportError:  # pragma: no cover
    trafilatura = None

ARTICLE_TYPES = {"newsarticle", "article", "reportagenewsarticle", "blogposting", "analysisnewsarticle",
                 "opinionnewsarticle", "backgroundnewsarticle", "report", "videoobject", "webpage"}

# Suffixes that sites glue onto titles and descriptions.
SITE_NAMES = ["РИА Новости", "РИА «Новости»", "ТАСС", "TASS", "RT на русском", "RT", "Известия", "iz.ru",
              "Российская газета", "rg.ru", "Вести.ру", "Вести", "vesti.ru", "Звезда", "Телеканал Звезда",
              "Президент России", "President of Russia", "Парламентская газета", "Комсомольская правда",
              "KP.RU", "kp.ru", "АиФ", "Аргументы и факты", "aif.ru", "МК", "Московский комсомолец", "mk.ru",
              "Лента.ру", "Lenta.ru", "Газета.Ru", "Life.ru", "Life", "Царьград", "Украина.ру", "ИноСМИ",
              "Sputnik Globe", "Sputnik", "Радио Sputnik", "TASS English"]
_names = "|".join(re.escape(n) for n in sorted(SITE_NAMES, key=len, reverse=True))
_TITLE_SUFFIX = re.compile(rf"\s+[|—–-]\s+(?:{_names})(?:\s+[\w.]+)?(?:,?\s*\d{{2}}\.\d{{2}}\.\d{{4}})?(?:\s*[|—–-].*)?$", re.I)
# "… РИА Новости Спорт, 23.09.2026" at the end of RIA-family descriptions
_LEAD_SUFFIX = re.compile(rf"\s*(?:{_names})(?:\s+[\w.]+){{0,2}},\s*\d{{2}}\.\d{{2}}\.\d{{4}}\.?\s*$", re.I)
_AUTHOR_IS_SITE = re.compile(rf"^(?:(?:{_names})(?:\s+[\w.]+){{0,2}}|[\w.-]+\.(?:ru|com|tv|su|net))$", re.I)
# Site-specific boilerplate: "… - Новости на Вести.ru", "Последние новости на сайте Вести: …"
_TITLE_TAIL = re.compile(r"\s+[-—–|]\s+(?:Новости на Вести\.?(?:ru)?|Вести\.?ru)\.?$", re.I)
_LEAD_HEAD = re.compile(r"^(?:Последние новости на сайте Вести:\s*)", re.I)
_LEAD_TAIL = re.compile(r"\s*(?:Актуальные события России и мира на сайте Вести\.?)$", re.I)


def _meta(doc) -> tuple[dict, list[str]]:
    meta, tags = {}, []
    for m in doc.iter("meta"):
        key = (m.get("property") or m.get("name") or m.get("itemprop") or "").strip().lower()
        val = m.get("content")
        if not key or val is None:
            continue
        if key == "article:tag":
            tags.append(clean(val))
        meta.setdefault(key, val)
    return meta, tags


def _jsonld(doc) -> dict:
    """First JSON-LD object that looks like an article."""
    found = []
    for s in doc.xpath('//script[@type="application/ld+json"]'):
        raw = (s.text or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw, strict=False)
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop(0)
            if isinstance(obj, list):
                stack.extend(obj)
                continue
            if not isinstance(obj, dict):
                continue
            if "@graph" in obj:
                stack.extend(obj["@graph"] if isinstance(obj["@graph"], list) else [obj["@graph"]])
            t = obj.get("@type")
            types = {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}
            if types & ARTICLE_TYPES:
                found.append((0 if types & {"newsarticle", "article", "reportagenewsarticle"} else 1, obj))
    if not found:
        return {}
    found.sort(key=lambda x: x[0])
    return found[0][1]


def _author(ld: dict, meta: dict) -> str:
    a = ld.get("author")
    names = []
    for x in (a if isinstance(a, list) else [a]):
        if isinstance(x, dict) and x.get("name"):
            names.append(clean(x["name"]))
        elif isinstance(x, str):
            names.append(clean(x))
    names = [n for n in names if n and not n.startswith("http") and not _AUTHOR_IS_SITE.match(n)]
    if not names and meta.get("author") and not meta["author"].startswith("http"):
        names = [clean(meta["author"])]
    return ", ".join(dict.fromkeys(names))[:120]


def clean_title(t: str) -> str:
    t = clean(t)
    t = _TITLE_TAIL.sub("", t)
    t = _TITLE_SUFFIX.sub("", t)
    return t.strip(" |—–-")


def clean_lead(d: str) -> str:
    d = _LEAD_HEAD.sub("", _LEAD_SUFFIX.sub("", clean(d))).strip()
    d = _LEAD_TAIL.sub("", d).strip()
    d = re.sub(r"(?:\.{3}|…)[.…]*$", "…", d)          # "…." / "...." → "…"
    d = re.sub(r"(?<!\.)\.\.(?!\.)", ".", d)          # stray double full stops
    return d


def body_text(html: str, url: str, ld: dict) -> str:
    text = ""
    if trafilatura is not None:
        try:
            text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False,
                                       favor_precision=True, deduplicate=True) or ""
        except Exception as exc:  # trafilatura can choke on odd markup
            log.debug("trafilatura failed on %s: %s", url, exc)
    if len(text) < 200 and isinstance(ld.get("articleBody"), str):
        text = clean(ld["articleBody"])
    return text


def extract(html: str, url: str, headline: str = "meta") -> dict:
    """Metadata and body text from an article page.

    headline: "meta" takes the headline from og:title / twitter:title / JSON-LD (the usual case);
    "h1" takes the page's visible <h1>, for sites whose meta titles are written for search engines."""
    try:
        doc = lxml.html.document_fromstring(html)
    except (lxml.etree.ParserError, ValueError):
        return {}
    meta, tags = _meta(doc)
    ld = _jsonld(doc)

    title = meta.get("og:title") or meta.get("twitter:title") or ld.get("headline") or ""
    if headline == "h1":
        h1 = [clean(h.text_content()) for h in doc.xpath("//h1")]
        title = next((h for h in h1 if h), title)
    if not title:
        h1 = doc.xpath("//h1")
        title = h1[0].text_content() if h1 else (doc.findtext(".//title") or "")
    lead = meta.get("og:description") or meta.get("description") or meta.get("twitter:description") \
        or ld.get("description") or ""

    published = None
    for cand in (meta.get("article:published_time"), ld.get("datePublished"), meta.get("datepublished"),
                 meta.get("mediator_published_time"), meta.get("pubdate"), meta.get("publish-date"),
                 meta.get("analytics:p_ts"), meta.get("dc.date")):
        published = parse_dt(cand)
        if published:
            break
    if not published:
        t = doc.xpath("//time[@datetime]")
        published = parse_dt(t[0].get("datetime")) if t else None
    modified = parse_dt(meta.get("article:modified_time") or ld.get("dateModified"))

    section = meta.get("article:section") or ld.get("articleSection") or meta.get("analytics:rubric") or ""
    if isinstance(section, list):
        section = section[0] if section else ""
    if not tags:
        kw = meta.get("news_keywords") or meta.get("keywords") or meta.get("analytics:tags") or ""
        if isinstance(ld.get("keywords"), list):
            tags = [clean(k) for k in ld["keywords"]]
        else:
            tags = [clean(k) for k in re.split(r"[,;]", kw)]
    tags = [t for t in dict.fromkeys(tags) if t and len(t) < 60][:8]

    return {
        "title": clean_title(title),
        "lead": clean_lead(lead),
        "published": published,
        "modified": modified,
        "section": clean(section)[:60],
        "tags": tags,
        "author": _author(ld, meta),
        "body": body_text(html, url, ld),
    }


def published_from_url(url: str) -> datetime | None:
    """Last resort: dates embedded in URLs (ria.ru/20260923/…, mk.ru/…/2026/09/23/…)."""
    m = re.search(r"/(20\d{2})(\d{2})(\d{2})/", url) or re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url)
    if m:
        return parse_dt(f"{m.group(1)}-{m.group(2)}-{m.group(3)}T12:00:00+03:00")
    return None
