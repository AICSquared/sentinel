"""Shared helpers for the real-data fetch scripts (issue #24, T3).

Every ``fetch_<name>.py`` follows the same steps:

1. download from a URL pinned to an exact revision, and check the raw file's
   SHA-256 against the pinned value (a changed upstream file is an error, not
   a silent new dataset);
2. take a seeded, stratified sample;
3. write ``_py/data/real/<name>.parquet`` plus ``<name>.meta.json`` (URL,
   licence, date, row counts, SHA-256);
4. rebuild ``_py/data/real/SOURCE.md`` from every ``*.meta.json``.

Nothing here handles credentials. Sources that need a login (Kaggle) or a
browser (UQ RDM) are fetched by a human; the script then skips with a message
saying what to do.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger("sentinel.fetch")

HERE = Path(__file__).resolve().parent
PY_DIR = HERE.parent
REAL_DIR = PY_DIR / "data" / "real"
REPO_ROOT = PY_DIR.parents[3] if len(PY_DIR.parents) > 3 else PY_DIR  # src/app/sentinel/_py -> repo root (shallow in a container)
CACHE_DIR = REPO_ROOT / "data-cache"  # big raw files; git-ignored, never in the image
SEED = 7
USER_AGENT = "sentinel-fetch/1.0"


class SkipFetch(Exception):
    """The source can't be fetched here (needs a login, a browser, or a human)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, expected_sha256: str | None = None, retries: int = 4, timeout: float = 120.0) -> bytes:
    """GET ``url`` with retries; raise if the bytes don't match ``expected_sha256``."""
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            break
        except OSError as exc:  # URLError, timeouts, resets
            last = exc
            log.warning("download failed (%d/%d) %s: %s", attempt, retries, url, exc)
            time.sleep(min(2 ** attempt, 15))
    else:
        raise RuntimeError(f"could not download {url}: {last}")
    got = sha256_bytes(data)
    if expected_sha256 and got != expected_sha256:
        raise RuntimeError(f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {got}")
    return data


def read_parquet_bytes(data: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(data))


def stratified_sample(df: pd.DataFrame, by: str | list[str], n: int, seed: int = SEED, min_per_group: int = 1) -> pd.DataFrame:
    """About ``n`` rows, each group in proportion to its size (at least ``min_per_group``)."""
    if n >= len(df):
        return df.reset_index(drop=True)
    rng = np.random.default_rng(seed)
    parts = []
    for _, g in df.groupby(by, sort=True):
        k = max(min_per_group, int(round(n * len(g) / len(df))))
        k = min(k, len(g))
        idx = rng.choice(len(g), size=k, replace=False)
        parts.append(g.iloc[np.sort(idx)])
    return pd.concat(parts).reset_index(drop=True)


def write_parquet(df: pd.DataFrame, name: str, out_dir: Path | None = None) -> tuple[Path, str]:
    """Write ``<name>.parquet`` deterministically (no index, fixed compression); return (path, sha256)."""
    d = out_dir or REAL_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.parquet"
    df.reset_index(drop=True).to_parquet(path, index=False, compression="zstd", engine="pyarrow")
    return path, sha256_file(path)


def write_meta(name: str, meta: dict[str, Any], out_dir: Path | None = None) -> Path:
    """``<name>.meta.json`` (sorted keys) and a refreshed SOURCE.md."""
    d = out_dir or REAL_DIR
    d.mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), **meta}
    path = d / f"{name}.meta.json"
    path.write_text(json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    write_source_md(d)
    return path


def write_source_md(out_dir: Path | None = None) -> Path:
    """Rebuild SOURCE.md: one section per ``*.meta.json``."""
    d = out_dir or REAL_DIR
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.meta.json"))]
    lines = [
        "# Real-data samples (`_py/data/real/`)",
        "",
        "Written by `_py/fetch/fetch_all.py`; do not edit by hand. Each sample is seeded and",
        "stratified, so a rerun gives the same SHA-256. Samples whose licence does not allow",
        "redistribution are git-ignored (see `.gitignore` here) and a human fetches them.",
        "",
    ]
    for m in metas:
        lines += [
            f"## {m['name']}",
            "",
            f"- **Source:** {m.get('source_url', '?')}",
            f"- **Revision:** {m.get('revision', '?')}",
            f"- **Licence:** {m.get('licence', '?')}",
            f"- **In git:** {'yes' if m.get('committed') else 'no (git-ignored; run the fetch)'}",
            f"- **Fetched:** {m.get('fetched_utc', '?')}",
            f"- **Rows:** {m.get('rows', '?')} sampled from {m.get('source_rows', '?')}",
            f"- **Label counts:** {m.get('label_counts', '?')}",
            f"- **File:** `{m.get('file', '?')}`, SHA-256 `{m.get('sha256', '?')}`",
        ]
        if m.get("notes"):
            lines.append(f"- **Notes:** {m['notes']}")
        lines.append("")
    path = d / "SOURCE.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def counts(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts().sort_index().items()}
