"""Offline Russian → English machine translation of headlines.

Uses the open Argos Translate ru→en model (OPUS-trained Transformer) through CTranslate2 directly:
free, no API keys, runs on the GitHub runner's CPU. Quality is serviceable for headlines and
occasionally clumsy; the site labels these as machine translations.
"""
from __future__ import annotations

import logging
import os
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


class Translator:
    def __init__(self, model_dir: Path):
        import ctranslate2
        import sentencepiece

        threads = int(os.environ.get("WOLAND_MT_THREADS", os.cpu_count() or 2))
        self.translator = ctranslate2.Translator(str(model_dir / "model"), device="cpu", compute_type="int8",
                                                 inter_threads=1, intra_threads=threads)
        self.sp = sentencepiece.SentencePieceProcessor(model_file=str(model_dir / "sentencepiece.model"))

    def translate(self, texts: list[str], batch: int = 256) -> list[str]:
        unique = list(dict.fromkeys(t for t in texts if t and t.strip()))
        done: dict[str, str] = {}
        for i in range(0, len(unique), batch):
            chunk = unique[i:i + batch]
            pieces = [p[:220] for p in self.sp.encode(chunk, out_type=str)]
            results = self.translator.translate_batch(pieces, beam_size=2, max_batch_size=32,
                                                      max_decoding_length=180)
            for src, res in zip(chunk, results):
                done[src] = self.sp.decode(res.hypotheses[0]).strip()
        return [done.get(t, "") for t in texts]


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
