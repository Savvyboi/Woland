"""Compare machine-translation models on a sample of the archive's Russian headlines, for a person to judge:

    python tools/benchmark_mt.py --dry-run                     # draw the sample and show it; translate nothing
    python tools/benchmark_mt.py                               # Woland's own model (woland/translate.py)
    python tools/benchmark_mt.py --candidate opus-tc-big=marian:models/opus-mt-tc-big-ru-en \\
                                 --candidate nllb-1.3B=nllb:models/nllb-200-distilled-1.3B

writes docs/mt-benchmark-sample.md: each headline in Russian beside every model's English, and each model's
speed (headlines a second) and memory (peak resident size of the process that ran it). Not run by the tests or
the workflows: candidates are large downloads. The sample is drawn evenly from the outlet groups of
config/outlets.yaml (state wires, official, mass-market, hardline), a third of it short headlines (six words
or fewer, where models do worst), from the last `--days` days; the same seed draws the same sample.

A candidate is NAME=KIND:DIR, a CTranslate2 model directory made once with ctranslate2's converter
(pip install ctranslate2 transformers sentencepiece torch):

    ct2-transformers-converter --model Helsinki-NLP/opus-mt-tc-big-ru-en --output_dir models/opus-mt-tc-big-ru-en \\
        --quantization int8 --copy_files source.spm target.spm                                  # KIND marian
    ct2-transformers-converter --model facebook/nllb-200-distilled-1.3B --output_dir models/nllb-200-distilled-1.3B \\
        --quantization int8 --copy_files sentencepiece.bpe.model                                # KIND nllb
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from woland.config import load_outlets  # noqa: E402
from woland.store import read_day  # noqa: E402

OUT = ROOT / "docs" / "mt-benchmark-sample.md"
GROUPS = ("state", "official", "mass", "hardline")
SHORT = 6  # words


def sample(n: int = 100, days: int = 30, seed: int = 1, until: date | None = None) -> list[dict]:
    """n Russian headlines, evenly from the outlet groups, a third of them short; the stored translation kept."""
    outlets = [o for o in load_outlets() if o.lang == "ru"]
    until = until or date.today()
    pool: dict[tuple[str, bool], list[dict]] = {}
    for i in range(1, days + 1):
        d = until - timedelta(days=i)
        for o in outlets:
            if o.group not in GROUPS:
                continue
            for r in read_day(d, o.id):
                if r.get("t") and not o.is_machine(r):   # (an outlet's machine-written items are no test)
                    pool.setdefault((o.group, len(r["t"].split()) <= SHORT), []).append(
                        {"o": o.id, "group": o.group, "t": r["t"], "te": r.get("te", ""), "u": r["u"]})
    rng = random.Random(seed)
    for v in pool.values():
        v.sort(key=lambda r: r["u"])
        rng.shuffle(v)
    want = {g: n // len(GROUPS) + (i < n % len(GROUPS)) for i, g in enumerate(GROUPS)}
    out = []
    for g in GROUPS:
        short = min(len(pool.get((g, True), [])), want[g] // 3)
        out += pool.get((g, True), [])[:short] + pool.get((g, False), [])[:want[g] - short]
    return out


def _run(kind: str, path: str, texts: list[str], q) -> None:
    """In a process of its own, so that its peak memory is its own."""
    import resource
    t0 = time.perf_counter()
    if kind == "woland":
        from woland.translate import get_translator
        tr = get_translator()
        if tr is None:
            q.put({"error": "model unavailable"})
            return
        load = time.perf_counter() - t0
        t1 = time.perf_counter()
        out = tr.translate(texts)
    else:
        import ctranslate2
        import sentencepiece
        model = Path(path)
        translator = ctranslate2.Translator(str(model), device="cpu", compute_type="int8")
        if kind == "marian":
            src = sentencepiece.SentencePieceProcessor(model_file=str(model / "source.spm"))
            tgt = sentencepiece.SentencePieceProcessor(model_file=str(model / "target.spm"))
            pieces = [p + ["</s>"] for p in src.encode(texts, out_type=str)]
            prefix = None
        elif kind == "nllb":
            src = tgt = sentencepiece.SentencePieceProcessor(model_file=str(model / "sentencepiece.bpe.model"))
            pieces = [["rus_Cyrl"] + p + ["</s>"] for p in src.encode(texts, out_type=str)]
            prefix = [["eng_Latn"]] * len(texts)
        else:
            q.put({"error": f"unknown kind {kind!r}"})
            return
        load = time.perf_counter() - t0
        t1 = time.perf_counter()
        res = translator.translate_batch(pieces, target_prefix=prefix, beam_size=2, max_batch_size=32)
        hyps = [r.hypotheses[0][1:] if prefix else r.hypotheses[0] for r in res]
        out = [tgt.decode(h).strip() for h in hyps]
    took = time.perf_counter() - t1
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    q.put({"out": out, "rate": len(texts) / took if took else 0.0, "load": load, "peak": peak})


def run(kind: str, path: str, texts: list[str]) -> dict:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_run, args=(kind, path, texts, q))
    p.start()
    result = q.get()
    p.join()
    return result


def markdown(rows: list[dict], results: dict[str, dict], seed: int, days: int) -> str:
    names = list(results)
    out = ["# Machine translation: a sample to judge by hand", "",
           f"{len(rows)} Russian headlines from the last {days} days (seed {seed}), evenly from the outlet groups, "
           f"a third of six words or fewer: `python tools/benchmark_mt.py`. *Stored* is the translation the archive "
           "holds (with the glossary not yet applied).", "",
           "| Model | Headlines a second | Peak memory (MB) | Loading (s) |", "|---|---:|---:|---:|"]
    for name, r in results.items():
        if "error" in r:
            out.append(f"| {name} | {r['error']} | | |")
        else:
            out.append(f"| {name} | {r['rate']:.1f} | {r['peak'] / 1e6:,.0f} | {r['load']:.1f} |")
    out += ["", "| # | Outlet | Russian | Stored | " + " | ".join(names) + " |",
            "|---:|---|---|---|" + "---|" * len(names)]
    cell = lambda s: (s or "").replace("|", "\\|").replace("\n", " ")
    for i, row in enumerate(rows):
        mts = [cell(results[n]["out"][i]) if "out" in results[n] else "" for n in names]
        out.append(f"| {i + 1} | {row['o']} | [{cell(row['t'])}]({row['u']}) | {cell(row['te'])} | " + " | ".join(mts) + " |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=100, help="headlines (default 100)")
    ap.add_argument("--days", type=int, default=30, help="drawn from the last N days")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--candidate", action="append", default=[], metavar="NAME=KIND:DIR")
    ap.add_argument("--no-woland", action="store_true", help="leave out Woland's own model")
    ap.add_argument("--dry-run", action="store_true", help="draw and show the sample only")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    rows = sample(a.n, a.days, a.seed)
    by = {g: sum(r["group"] == g for r in rows) for g in GROUPS}
    short = sum(len(r["t"].split()) <= SHORT for r in rows)
    print(f"{len(rows)} headlines ({', '.join(f'{g} {k}' for g, k in by.items())}; {short} short)")
    if len(rows) < a.n:
        print(f"only {len(rows)} of {a.n}: some groups have too few headlines in the last {a.days} days")
    if a.dry_run:
        for r in rows[:10]:
            print(f"  {r['group']:9} {r['o']:9} {r['t']}")
        return 0 if rows else 1
    models = [] if a.no_woland else [("woland (argos ru→en 1.9)", "woland", "")]
    for spec in a.candidate:
        name, _, rest = spec.partition("=")
        kind, _, path = rest.partition(":")
        models.append((name, kind, path))
    texts = [r["t"] for r in rows]
    results = {}
    for name, kind, path in models:
        print(f"translating with {name} …")
        results[name] = run(kind, path, texts)
        if "error" in results[name]:
            print(f"  {results[name]['error']}")
    Path(a.out).write_text(markdown(rows, results, a.seed, a.days), encoding="utf-8", newline="\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
