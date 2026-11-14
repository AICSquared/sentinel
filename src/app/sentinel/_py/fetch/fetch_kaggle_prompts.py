"""Kaggle prompt-injection CSV -> data/real/kaggle_prompts.parquet (git-ignored). Human-run.

File ``data/threat_intelligence/hf_prompt_injections.csv`` in
chuneeb/ai-agent-cybersecurity-dataset-2026 (CC BY 4.0 at dataset level; its
upstream Hugging Face source's licence is not named, so it is not committed).

Kaggle needs a login, and agents never handle credentials, so this script
does not download. A human either:
  1. runs ``kaggle datasets download -d chuneeb/ai-agent-cybersecurity-dataset-2026
     -f data/threat_intelligence/hf_prompt_injections.csv -p data-cache/kaggle --unzip``
     (with their own ~/.kaggle/kaggle.json), or
  2. downloads the file in a browser into ``data-cache/kaggle/``.
Then this script samples it. Per the plan it is used only if it has a usable
label column; otherwise it records that and skips.
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

log = logging.getLogger("sentinel.fetch.kaggle")

NAME = "kaggle_prompts"
SOURCE = "https://www.kaggle.com/datasets/chuneeb/ai-agent-cybersecurity-dataset-2026"
FILE = "hf_prompt_injections.csv"
LICENCE = "CC BY 4.0 (Kaggle dataset); upstream Hugging Face source licence not named: do not redistribute"
LABEL_NAMES = ("label", "is_injection", "injection", "class", "target")
TEXT_NAMES = ("text", "prompt", "content", "input")
SAMPLE_ROWS = 5_000


def _find(columns: list[str], names: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in columns}
    return next((lower[n] for n in names if n in lower), None)


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Columns ``text, label`` (0/1), or raise SkipFetch when there is no usable label."""
    text_col, label_col = _find(list(df.columns), TEXT_NAMES), _find(list(df.columns), LABEL_NAMES)
    if text_col is None or label_col is None:
        raise common.SkipFetch(f"{FILE}: no usable text/label columns (have {list(df.columns)}); not used, per plan")
    out = pd.DataFrame({"text": df[text_col].astype(str), "label": pd.to_numeric(df[label_col], errors="coerce")})
    out = out.dropna()
    out["label"] = out["label"].astype(int)
    if not set(out["label"]) <= {0, 1} or out["label"].nunique() < 2:
        raise common.SkipFetch(f"{FILE}: label column {label_col!r} is not a 0/1 label; not used, per plan")
    return common.stratified_sample(out.drop_duplicates("text"), "label", SAMPLE_ROWS)


def main(out_dir: Path | None = None, cache_dir: Path | None = None) -> dict:
    src = next((cache_dir or common.CACHE_DIR / "kaggle").glob(f"**/{FILE}"), None)
    if src is None:
        raise common.SkipFetch(f"{FILE} not in data-cache/kaggle/. Kaggle needs a login: a human downloads it (see this file's docstring)")
    raw_sha = common.sha256_file(src)
    df = build(pd.read_csv(src))
    path, sha = common.write_parquet(df, NAME, out_dir)
    meta = {
        "source_url": SOURCE, "revision": f"{FILE}, raw SHA-256 {raw_sha}", "licence": LICENCE, "committed": False,
        "rows": len(df), "source_rows": len(df), "label_counts": common.counts(df["label"]),
        "file": path.name, "sha256": sha, "notes": "Optional extra training rows for Prompt Guard (label 1 = injection).",
    }
    common.write_meta(NAME, meta, out_dir)
    return meta


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        main()
    except common.SkipFetch as exc:
        log.warning("skipped: %s", exc)
