"""woland/lexicon.py (what is counted) and site/assets/js/lexicon.js (what is highlighted) must agree.

Both run on the texts of tests/fixtures/lexicon_parity.json, ordinary headlines and adversarial ones (soft
hyphens, zero-width characters, unusual spaces, ё, guillemets, dashes, characters outside the Basic
Multilingual Plane, `with` and `not` groups); the framings found and the characters of every match must be
the same. A case's `has` and `lacks` say what both must find, so that the two breaking alike is caught too.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from woland.config import load_contexts, load_lexicon
from woland.lexicon import CONTEXT_WINDOW, Lexicon

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests" / "fixtures" / "lexicon_parity.json").read_text(encoding="utf-8"))["cases"]


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


def _python(lex: Lexicon, case: dict) -> dict:
    lang, text, extra = case["lang"], case["text"], case.get("extra", "")
    spans = {}
    for nid, _ in lex._groups.get(lang, []):
        found = lex.spans(text, lang, nid, extra)
        if found:
            spans[nid] = [list(s) for s in found]
    return {"find": {k: list(v) for k, v in lex.find(text, lang, extra=extra).items()},
            "window": {k: list(v) for k, v in lex.find(text, lang, extra=extra, window=CONTEXT_WINDOW).items()},
            "spans": spans}


@pytest.fixture(scope="module")
def browser(lexicon):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    payload = {"narratives": [n.public() for n in lexicon], "contexts": load_contexts(), "cases": CASES}
    out = subprocess.run([node, str(ROOT / "tests" / "js" / "lexicon_harness.mjs")], input=json.dumps(payload),
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_the_fixtures_cover_what_they_should():
    assert len(CASES) >= 30
    text = "".join(c["text"] for c in CASES)
    for ch in ("­", "​", "﻿", " ", "ё", "«", "—", "\U0001f525"):
        assert ch in text, repr(ch)
    assert any("extra" in c for c in CASES) and any(c.get("lacks") for c in CASES)


@pytest.mark.parametrize("i", range(len(CASES)), ids=[c["text"][:40] for c in CASES])
def test_python_finds_what_the_fixture_expects(lexicon, i):
    case = CASES[i]
    found = set(Lexicon(lexicon).find(case["text"], case["lang"], extra=case.get("extra", "")))
    assert set(case.get("has", ())) <= found
    assert not set(case.get("lacks", ())) & found


def test_python_and_browser_match_the_same_characters(lexicon, browser):
    lex = Lexicon(lexicon)
    for case, js in zip(CASES, browser, strict=True):
        py = _python(lex, case)
        assert js == py, case["text"]
        for nid, (a, b) in py["find"].items():  # a span is a stretch of the original text, not an empty one
            assert 0 <= a < b <= len(case["text"]), (case["text"], nid)
