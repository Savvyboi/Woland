"""Offline Russian → English machine translation of headlines, leads and the snippets of body matches.

Uses the open Argos Translate ru→en model (OPUS-trained Transformer) through CTranslate2 directly:
free, no API keys, runs on the GitHub runner's CPU. Quality is serviceable and occasionally clumsy; the
site labels these as machine translations.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import requests

log = logging.getLogger("woland.translate")

MODEL_URL = os.environ.get("WOLAND_MT_URL", "https://argos-net.com/v1/translate-ru_en-1_9.argosmodel")
MODEL_NAME = "translate-ru_en-1_9"
MODEL_HOME = Path(os.environ.get("WOLAND_MODELS", Path.home() / ".cache" / "woland" / "models"))


def ensure_model() -> Path | None:
    target = MODEL_HOME / MODEL_NAME
    if (target / "model" / "model.bin").exists() and (target / "sentencepiece.model").exists():
        return target
    MODEL_HOME.mkdir(parents=True, exist_ok=True)
    log.info("downloading translation model from %s", MODEL_URL)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "model.zip"
            with requests.get(MODEL_URL, stream=True, timeout=(20, 300)) as r:
                r.raise_for_status()
                with open(zpath, "wb") as fh:
                    shutil.copyfileobj(r.raw, fh)
            with zipfile.ZipFile(zpath) as z:
                for info in z.infolist():
                    name = info.filename
                    if name.endswith("/") or "/stanza/" in name:
                        continue
                    rel = Path(*Path(name).parts[1:])  # drop the top-level folder
                    dest = target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
    except Exception as exc:
        log.warning("translation model unavailable: %s", exc)
        return None
    return target if (target / "model" / "model.bin").exists() else None


# A sentence ends at . ! ? or … followed by a space and a capital letter, a digit or an opening quotation
# mark (or by the quotation mark straight away: "заявил он.«Мы…") — unless the full stop closes an initial
# ("В. Путин") or a common abbreviation ("около 5 млн. Рублей").
_BREAK = re.compile(r"(?<=[.!?…])(?:\s+(?=[«„“\"(]?[A-ZА-ЯЁ0-9])|(?=[«„“][A-ZА-ЯЁ0-9]))")
_LAST_WORD = re.compile(r"([^\s.(«„“\"]+)\.$")
_ABBREV = frozenset("""г гг им ул пл пр просп корп стр др св ст руб коп долл млн млрд трлн тыс ок см рис ред прим
проф акад ген полк мин чел кв км обл пос дер зам нач англ нем фр лат""".split())
# Words that cannot end a sentence. Left dangling where a lead or a snippet was cut off ("компенсируют затраты
# на обучение ребенка в…"), they lead the model to finish the sentence itself ("… of educating a child in the
# United States"), so they are left out of the translation, which ends with an ellipsis like the original.
_DANGLING = frozenset("""и а но или да в во на по с со к ко о об обо от до для за из изо над под при про у без через
между перед что чтобы как когда где который которая которое которые которых если не ни же ли бы то его ее её их
этот эта это эти тот та те также том свой своя свою своей своих""".split())


def sentences(text: str) -> list[str]:
    """The sentences of a text, to be translated one by one: the model was trained on single sentences and
    tends to drop or run together the second of two."""
    out, start = [], 0
    for m in _BREAK.finditer(text):
        before = text[start:m.start()]
        last = _LAST_WORD.search(before)
        if last and (len(last.group(1)) == 1 or last.group(1).lower() in _ABBREV):
            continue
        out.append(before.strip())
        start = m.end()
    out.append(text[start:].strip())
    return [s for s in out if s]


def _cut_off(sentence: str) -> str:
    """A sentence that was cut off, without its ellipsis and the little words left dangling before it."""
    words = sentence.rstrip(" .…").split()
    while len(words) > 1 and words[-1].lower().strip(",;:—–-«»\"“”„") in _DANGLING:
        words.pop()
    return " ".join(words).rstrip(",;:—–- ")


def _pieces(text: str) -> tuple[list[str], bool, bool]:
    """A text as the sentences to translate, and whether it begins and ends in the middle of a sentence
    (a snippet "…of the body text…", a lead cut off at 240 characters)."""
    text = text.strip()
    head, tail = text.startswith("…"), text.endswith(("…", "..."))
    parts = sentences(text.lstrip("…").lstrip())
    if tail and parts:
        parts[-1] = _cut_off(parts[-1])
    return [p for p in parts if p], head, tail


class Translator:
    def __init__(self, model_dir: Path):
        import ctranslate2
        import sentencepiece

        threads = int(os.environ.get("WOLAND_MT_THREADS", os.cpu_count() or 2))
        # Batches side by side, two threads each: on 24 threads 47 leads a second, against 18 with one batch
        # at a time on all of them (October 2026).
        intra = 2 if threads >= 4 else threads
        self.translator = ctranslate2.Translator(str(model_dir / "model"), device="cpu", compute_type="int8",
                                                 inter_threads=max(1, threads // intra), intra_threads=intra)
        self.sp = sentencepiece.SentencePieceProcessor(model_file=str(model_dir / "sentencepiece.model"))

    def translate(self, texts: list[str], batch: int = 256) -> list[str]:
        """The English of each text ("" for an empty one), translated sentence by sentence; a text that
        begins or ends in the middle of a sentence does so in English too ("…")."""
        parts = {t: _pieces(t) for t in texts if t and t.strip()}
        unique = list(dict.fromkeys(s for ss, _, _ in parts.values() for s in ss))
        done: dict[str, str] = {}
        for i in range(0, len(unique), batch):
            chunk = unique[i:i + batch]
            pieces = [p[:220] for p in self.sp.encode(chunk, out_type=str)]
            results = self.translator.translate_batch(pieces, beam_size=2, max_batch_size=32,
                                                      max_decoding_length=180)
            for src, res in zip(chunk, results):
                done[src] = self.sp.decode(res.hypotheses[0]).strip()

        def english(t):
            ss, head, tail = parts[t]
            en = " ".join(done[s] for s in ss if done.get(s))
            if en and tail:
                en = en.rstrip(" .…") + "…"
            return f"…{en}" if en and head else en
        return [english(t) if t in parts else "" for t in texts]


_instance: Translator | None = None
_failed = False


def get_translator() -> Translator | None:
    global _instance, _failed
    if _instance is None and not _failed:
        path = ensure_model()
        if path is None:
            _failed = True
            return None
        try:
            _instance = Translator(path)
        except Exception as exc:
            log.warning("could not load translation model: %s", exc)
            _failed = True
    return _instance
