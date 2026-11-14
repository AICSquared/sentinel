"""HF jayavibhav/prompt-injection-safety -> data/real/prompt_safety.parquet (git-ignored).

Prompt Guard's TRAINING data. Public and ungated (no login), but the dataset
card declares no licence, so the sample is not committed: a human (or the
person building the overseer image) runs this once.

Labels as published: 0 benign, 1 prompt injection, 2 harmful request.
Output: a seeded sample stratified by (split, label) with columns
``text, label, split``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

try:
    from . import common
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import common  # type: ignore[no-redef]

log = logging.getLogger("sentinel.fetch.prompt_safety")

NAME = "prompt_safety"
DATASET = "jayavibhav/prompt-injection-safety"
REVISION = "c0f55c8817fb2d4da72ac7b06deba6033da6fad6"
BASE = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/data/"
LICENCE = ("none: the dataset card declares no licence, and the owner has not answered the open licence question "
           "(huggingface.co/datasets/jayavibhav/prompt-injection-safety/discussions/3, since 2026-07-03). "
           "Confirmed 2026-11-14: local training only, never redistributed")
FILES: dict[str, str] = {
    "train": "0dbcc5fa44b5acb71b7fe05f9b11a7c22333e7119044bd9048db13a2b2ad59ae",
    "test": "77ce0c42ce0be16a7a325813fad8ec249c48c026dc32fc16fae6c1f0eb930fa0",
}
SAMPLE_ROWS = 20_000


def build(raw: dict[str, bytes], n: int = SAMPLE_ROWS) -> tuple[pd.DataFrame, int]:
    parts = []
    for split, data in raw.items():
        df = common.read_parquet_bytes(data)[["text", "label"]]
        df["split"] = split
        parts.append(df)
    full = pd.concat(parts, ignore_index=True)
    full["text"] = full["text"].astype(str)
    full["label"] = full["label"].astype(int)
    full = full.drop_duplicates(subset=["text"]).reset_index(drop=True)
    sample = common.stratified_sample(full, ["split", "label"], n)
    return sample, len(full)


def main(out_dir: Path | None = None) -> dict:
    d = out_dir or common.REAL_DIR
    raw = {split: common.download(f"{BASE}{split}-00000-of-00001.parquet", sha, timeout=300) for split, sha in FILES.items()}
    df, source_rows = build(raw)
    path, sha = common.write_parquet(df, NAME, d)
    meta = {
        "source_url": f"https://huggingface.co/datasets/{DATASET}", "revision": REVISION, "licence": LICENCE,
        "committed": False, "rows": len(df), "source_rows": source_rows,
        "label_counts": common.counts(df["label"]), "file": path.name, "sha256": sha, "raw_sha256": FILES,
        "notes": "Training data for Prompt Guard. Labels: 0 benign, 1 prompt injection, 2 harmful request. "
                 "Exact-duplicate texts dropped before sampling; stratified by (split, label), seed 7.",
    }
    common.write_meta(NAME, meta, d)
    log.info("prompt_safety: %d of %d rows %s -> %s", len(df), source_rows, meta["label_counts"], path)
    return meta


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
