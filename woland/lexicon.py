"""Matching articles against the lexicon of narratives and topics.

A narrative's patterns come in groups. A plain pattern counts wherever it appears. A group may also say
`with`: it counts only when the same text also contains a word from one of the named context lists (for
the full text: within CONTEXT_WINDOW characters of the match, so that the stored snippet shows it, or in
the headline and lead); and `not`: a match that is part of one of these phrases does not count.
site/assets/js/lexicon.js does the same in the browser, to show which words matched.
"""
from __future__ import annotations

import re

from .config import Narrative
from .util import normalize

_WS = re.compile(r"\s+")
CONTEXT_WINDOW = 50  # characters either side of a full-text match in which a `with` word must appear


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
    return r"(?<!\w)" + r"[\s ]+".join(parts) + tail


def _alternation(patterns: list[str]) -> re.Pattern | None:
    return re.compile("|".join(f"(?:{pattern_regex(p)})" for p in patterns)) if patterns else None


class _Group:
    """Patterns sharing the same conditions."""

    def __init__(self, match: list[str], ctx: list[str] = (), exclude: list[str] = ()):
        self.rx = _alternation(match)
        self.ctx = _alternation(list(ctx))
        self.exclude = _alternation(list(exclude))

    def first(self, t: str, extra: str, window: int | None) -> tuple[int, int] | None:
        """The first match in t (normalised) that satisfies the group's conditions."""
        spans_not = [m.span() for m in self.exclude.finditer(t)] if self.exclude else ()
        for m in self.rx.finditer(t):
            a, b = m.span()
            if any(c <= a and b <= d for c, d in spans_not):
                continue
            if self.ctx:
                # the word itself does not count as its own context
                around = t[:a] + " " * (b - a) + t[b:]
                if window is not None:
                    around = around[_window(t, a - window, a, left=True):_window(t, b + window, b, left=False)]
                if not (self.ctx.search(around) or (extra and self.ctx.search(extra))):
                    continue
            return a, b
        return None


def _window(t: str, i: int, limit: int, left: bool) -> int:
    """A window edge at i, moved towards `limit` until it no longer cuts a word in two."""
    i = max(0, min(len(t), i))
    if left:
        while 0 < i < limit and (t[i - 1].isalnum() or t[i - 1] == "_"):
            i += 1
    else:
        while limit < i < len(t) and (t[i].isalnum() or t[i] == "_"):
            i -= 1
    return i


class Lexicon:
    def __init__(self, narratives: list[Narrative]):
        self.narratives = narratives
        self.by_id = {n.id: n for n in narratives}
        self._groups: dict[str, list[tuple[str, list[_Group]]]] = {}
        for lang in ("ru", "en"):
            compiled = []
            for n in narratives:
                pats = n.patterns.get(lang) or []
                plain = [p for p in pats if isinstance(p, str)]
                groups = [_Group(plain)] if plain else []
                groups += [_Group(p["match"], p.get("ctx", ()), p.get("not", ())) for p in pats if not isinstance(p, str)]
                if groups:
                    compiled.append((n.id, groups))
            self._groups[lang] = compiled

    def find(self, text: str, lang: str, extra: str = "", window: int | None = None) -> dict[str, tuple[int, int]]:
        """narrative id → span of its first counted occurrence in text. `extra` is text that may supply the
        context a `with` group needs (the headline for the lead, and so on); `window` limits where in `text`
        that context may be found (for full texts)."""
        if not text:
            return {}
        t = norm_same_length(text)
        e = normalize(extra) if extra else ""
        hits = {}
        for nid, groups in self._groups.get(lang, []):
            best = None
            for g in groups:
                span = g.first(t, e, window)
                if span and (best is None or span[0] < best[0]):
                    best = span
            if best:
                hits[nid] = best
        return hits

    def tag(self, title: str, lead: str, body: str, lang: str) -> tuple[set[str], dict[str, str]]:
        """Narratives found in headline/lead, and body-only matches with a context snippet."""
        head = set(self.find(title, lang, extra=lead)) | set(self.find(lead, lang, extra=title))
        body_hits = {}
        for nid, span in self.find(body, lang, extra=f"{title} {lead}", window=CONTEXT_WINDOW).items():
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
