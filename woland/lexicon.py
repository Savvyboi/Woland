"""Matching articles against the lexicon of narratives and topics."""
from __future__ import annotations

import re

from .config import Narrative
from .util import normalize

_WS = re.compile(r"\s+")


def norm_same_length(s: str) -> str:
    """normalize() applied character by character, so offsets stay valid in the original text."""
    out = []
    for ch in s:
        n = normalize(ch)
        out.append(n if len(n) == 1 else ch)
    return "".join(out)


def pattern_regex(pattern: str) -> str:
    words = normalize(pattern).split()
    parts = []
    for w in words:
        if w.endswith("*"):
            parts.append(re.escape(w[:-1]) + r"\w*")
        else:
            parts.append(re.escape(w))
    tail = "" if words[-1].endswith("*") else r"(?!\w)"
    return r"(?<!\w)" + r"[\s ]+".join(parts) + tail


class Lexicon:
    def __init__(self, narratives: list[Narrative]):
        self.narratives = narratives
        self.by_id = {n.id: n for n in narratives}
        self._rx: dict[str, list[tuple[str, re.Pattern]]] = {}
        for lang in ("ru", "en"):
            compiled = []
            for n in narratives:
                pats = n.patterns.get(lang) or []
                if pats:
                    compiled.append((n.id, re.compile("|".join(f"(?:{pattern_regex(p)})" for p in pats))))
            self._rx[lang] = compiled

    def find(self, text: str, lang: str) -> dict[str, tuple[int, int]]:
        """narrative id → span of its first occurrence in text."""
        if not text:
            return {}
        t = norm_same_length(text)
        hits = {}
        for nid, rx in self._rx.get(lang, []):
            m = rx.search(t)
            if m:
                hits[nid] = m.span()
        return hits

    def tag(self, title: str, lead: str, body: str, lang: str) -> tuple[set[str], dict[str, str]]:
        """Narratives found in headline/lead, and body-only matches with a context snippet."""
        head = set(self.find(title, lang)) | set(self.find(lead, lang))
        body_hits = {}
        for nid, span in self.find(body, lang).items():
            body_hits[nid] = snippet(body, *span)
        return head, body_hits

    def fingerprint(self) -> str:
        from .util import short_hash
        return short_hash(repr([(n.id, n.patterns) for n in self.narratives]), 8)


def snippet(text: str, start: int, end: int, width: int = 170) -> str:
    """A keyword-in-context excerpt of at most `width` characters around text[start:end]."""
    span = end - start
    room = max(0, width - span)
    left = max(0, start - room // 2)
    right = min(len(text), end + room - (start - left))
    left = max(0, min(left, right - width))
    if left > 0:
        sp = text.find(" ", left, start)
        left = sp + 1 if sp != -1 else left
    if right < len(text):
        sp = text.rfind(" ", end, right)
        right = sp if sp != -1 else right
    s = _WS.sub(" ", text[left:right]).strip()
    return ("…" if left > 0 else "") + s + ("…" if right < len(text) else "")
