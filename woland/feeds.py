"""Atom feeds: the newest articles of every framing and topic, outlet and country, and of the saved searches in
config/feeds.yaml; and the weekly brief. Written into _site/feeds/ by the site builder (woland/build.py), so
that readers can follow Woland in a feed reader instead of visiting it.

Each article entry links to the article itself and to the Internet Archive's copy (most of these sites are
blocked in the EU), and carries its English machine translation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import yaml

from .config import CONFIG_DIR
from .textproc import index_terms

ATOM_NS = "http://www.w3.org/2005/Atom"


@dataclass
class SavedSearch:
    id: str
    label: dict
    any: list[list[str]]  # phrases, each the word stems it needs

    def matches(self, stems: set[str]) -> bool:
        return any(all(s in stems for s in phrase) for phrase in self.any)


def load_searches(path: Path | None = None) -> list[SavedSearch]:
    p = path or CONFIG_DIR / "feeds.yaml"
    if not p.exists():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = []
    for s in raw.get("searches") or []:
        phrases = [[st for _, st in index_terms(str(q))] for q in s["any"]]
        if not all(phrases):
            raise ValueError(f"feeds.yaml: {s['id']}: a phrase made only of stop words")
        out.append(SavedSearch(id=s["id"], label=s["label"], any=phrases))
    ids = [s.id for s in out]
    if len(ids) != len(set(ids)):
        raise ValueError("feeds.yaml: duplicate search ids")
    return out


def wayback(url: str, when: str) -> str:
    """The Internet Archive's copy nearest to the time of publication."""
    return f"https://web.archive.org/web/{when[:10].replace('-', '')}/{url}"


def _link(href: str, rel: str = "alternate", **attrs) -> str:
    extra = "".join(f" {k}={quoteattr(v)}" for k, v in attrs.items())
    return f"<link rel={quoteattr(rel)} href={quoteattr(href)}{extra}/>"


def article_entry(item: dict, outlet_name: str, labels: list[str]) -> str:
    """An Atom entry for one article (a feed item written by Builder.feed_item)."""
    parts = []
    if item.get("te"):
        parts.append(f"[EN, machine translation] {item['te']}")
    if item.get("d"):
        parts.append(item["d"])
    if item.get("de"):
        parts.append(f"[EN, machine translation] {item['de']}")
    if labels:
        parts.append("Woland: " + ", ".join(labels))
    summary = "\n\n".join(parts)
    title = item["t"] if not item.get("te") else f"{item['t']} — {item['te']}"
    return (
        "<entry>"
        f"<id>urn:woland:{escape(item['id'])}</id>"
        f"<title>{escape(title)}</title>"
        f"<updated>{escape(item['p'])}</updated><published>{escape(item['p'])}</published>"
        f"<author><name>{escape(outlet_name)}</name></author>"
        + _link(item["u"])
        + _link(item.get("ar") and f"https://web.archive.org/web/{item['ar']}/{item['u']}" or wayback(item["u"], item["p"]),
                "related", title="Internet Archive")
        + (f"<summary type=\"text\">{escape(summary)}</summary>" if summary else "")
        + "</entry>"
    )


def text_entry(entry_id: str, title: str, updated: str, href: str, text: str) -> str:
    return (f"<entry><id>{escape(entry_id)}</id><title>{escape(title)}</title><updated>{escape(updated)}</updated>"
            + _link(href) + f"<summary type=\"text\">{escape(text)}</summary></entry>")


def write_feed(path: Path, feed_id: str, title: str, subtitle: str, self_href: str, page_href: str,
               updated: str, entries: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        f"<feed xmlns=\"{ATOM_NS}\">"
        f"<id>{escape(feed_id)}</id><title>{escape(title)}</title><subtitle>{escape(subtitle)}</subtitle>"
        f"<updated>{escape(updated)}</updated><generator>Woland</generator>"
        f"<author><name>Woland</name></author>"
        + _link(self_href, "self", type="application/atom+xml") + _link(page_href, type="text/html")
        + "".join(entries) + "</feed>\n"
    )
    path.write_text(xml, encoding="utf-8")
