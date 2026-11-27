"""Pack one quarter of the archive (data/articles/) into a release file, for a GitHub Release or a dataset
deposit (Zenodo), with checksums:

    python tools/export_quarter.py 2026-Q4 [--out dist]

writes dist/woland-articles-2026-Q4.tar.gz (the day files of the quarter's months, as they are in data/,
with config/lexicon.yaml, config/glossary.yaml and docs/lexicon-audit.md beside them) and
dist/woland-articles-2026-Q4.SHA256SUMS (one line per file in the archive, and one for the archive itself;
check with `sha256sum -c` after unpacking). The same files give the same archive, byte for byte. data/ is
only read."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BESIDE = ["config/lexicon.yaml", "config/glossary.yaml", "docs/lexicon-audit.md", "LICENSE"]


def quarter_months(quarter: str) -> list[str]:
    m = re.fullmatch(r"(\d{4})-Q([1-4])", quarter)
    if not m:
        raise ValueError(f"{quarter!r}: expected YYYY-Q1 … YYYY-Q4")
    year, q = int(m.group(1)), int(m.group(2))
    return [f"{year}/{month:02d}" for month in range(3 * q - 2, 3 * q + 1)]


def members(root: Path, quarter: str) -> list[tuple[str, Path]]:
    """(name in the archive, file) for the quarter's day files and the files that explain them."""
    files = []
    for month in quarter_months(quarter):
        for f in sorted((root / "data" / "articles" / month).rglob("*.jsonl")):
            files.append((f.relative_to(root).as_posix(), f))
    if not files:
        raise ValueError(f"{quarter}: no day files under data/articles/")
    return files + [(name, root / name) for name in BESIDE if (root / name).exists()]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export(quarter: str, out: Path, root: Path = ROOT) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    name = f"woland-articles-{quarter}"
    sums = []
    archive = out / f"{name}.tar.gz"
    # fixed times, owners and order, and no gzip timestamp: the same files make the same archive
    with open(archive, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for arcname, path in members(root, quarter):
            data = path.read_bytes()
            info = tarfile.TarInfo(f"{name}/{arcname}")
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
            sums.append(f"{sha256(data)}  {name}/{arcname}")
    digest = hashlib.sha256()
    with open(archive, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    sums.append(f"{digest.hexdigest()}  {archive.name}")
    listing = out / f"{name}.SHA256SUMS"
    listing.write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    return archive, listing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("quarter", help="YYYY-Q1 … YYYY-Q4")
    ap.add_argument("--out", default="dist", help="folder to write to (default: dist)")
    a = ap.parse_args(argv)
    try:
        archive, listing = export(a.quarter, Path(a.out))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"{archive} ({archive.stat().st_size / 1e6:,.1f} MB)\n{listing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
