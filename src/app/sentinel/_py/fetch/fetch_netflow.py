"""UQ NetFlow v3 -> data/real/nf_<name>.parquet, 200k-row stratified samples (git-ignored).

NF-CSE-CIC-IDS2018-v3 (~20.1M flows) and NF-UNSW-NB15-v3 (~2.4M flows) are
downloaded in a browser from UQ RDM (agents can't script it), and their
licence must be read there. A human puts the CSV (or zip) files in
``data-cache/`` at the repo root; this script streams them in chunks (never
loading a multi-GB file at once) and writes a seeded sample per dataset.

Sampling: pass 1 counts rows per attack class; pass 2 keeps each row with
probability quota/count, where quota is the class's share of 200k but at least
500 (all rows if fewer), so rare classes such as Infiltration and Worms survive.
The meta file also records which source file(s) held the Infiltration class.

Cite: Luay et al., "Temporal Analysis of NetFlow Datasets for Network Intrusion
Detection Systems", arXiv:2503.04404, 2025.
"""

from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import common
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import common  # type: ignore[no-redef]

log = logging.getLogger("sentinel.fetch.netflow")

DATASETS: dict[str, dict[str, str]] = {
    "nf_cic2018": {
        "pattern": "NF-CSE-CIC-IDS2018-v3*",
        "url": "https://rdm.uq.edu.au/files/4ac221b1-6bd6-42b1-bdf7-03f4fc7efb22",
    },
    "nf_unsw": {
        "pattern": "NF-UNSW-NB15-v3*",
        "url": "https://rdm.uq.edu.au/files/abd2f5d8-e268-4ff0-84fb-f2f7b3ca3e8f",
    },
}
LICENCE = "see the UQ RDM download page (not machine-readable): do not redistribute until a human confirms"
SAMPLE_ROWS = 200_000
MIN_PER_CLASS = 500
CHUNK = 500_000
CLASS_NAMES = ("Attack", "attack", "Attack_type", "attack_cat")
LABEL_NAMES = ("Label", "label")


def find_files(pattern: str, cache_dir: Path | None = None) -> list[Path]:
    d = cache_dir or common.CACHE_DIR
    return sorted(p for p in d.glob(f"**/{pattern}") if p.suffix.lower() in (".csv", ".zip", ".gz"))


def _chunks(path: Path, usecols=None):
    return pd.read_csv(path, chunksize=CHUNK, usecols=usecols, low_memory=False)


def _class_col(path: Path) -> str:
    cols = list(pd.read_csv(path, nrows=0).columns)
    col = next((c for c in CLASS_NAMES if c in cols), None) or next((c for c in LABEL_NAMES if c in cols), None)
    if col is None:
        raise common.SkipFetch(f"{path.name}: no Attack/Label column in {cols[:12]}...")
    return col


def quotas(class_counts: Counter, n: int | None = None, floor: int | None = None) -> dict[str, float]:
    """Keep-probability per class: its share of n, at least ``floor`` rows (or all of them)."""
    n = SAMPLE_ROWS if n is None else n
    floor = MIN_PER_CLASS if floor is None else floor
    total = sum(class_counts.values())
    probs = {}
    for c, k in class_counts.items():
        want = max(min(k, floor), round(n * k / total))
        probs[str(c)] = min(1.0, want / k)
    return probs


def sample_files(files: list[Path], n: int | None = None, seed: int = common.SEED) -> tuple[pd.DataFrame, Counter, dict[str, Counter]]:
    """(sample, class counts over all files, class counts per file)."""
    n = SAMPLE_ROWS if n is None else n
    col = _class_col(files[0])
    per_file: dict[str, Counter] = {}
    for f in files:  # pass 1: count
        cnt: Counter = Counter()
        for ch in _chunks(f, usecols=[col]):
            cnt.update(ch[col].astype(str))
        per_file[f.name] = cnt
    total: Counter = sum(per_file.values(), Counter())
    keep_p = quotas(total, n)
    rng = np.random.default_rng(seed)
    parts = []
    for f in files:  # pass 2: Bernoulli keep, same RNG stream every run
        for ch in _chunks(f):
            u = rng.random(len(ch))
            p = ch[col].astype(str).map(keep_p).to_numpy(dtype=float)
            parts.append(ch.loc[u < p])
    out = pd.concat(parts, ignore_index=True)
    out.insert(0, "attack_class", out[col].astype(str))
    return out, total, per_file


def fetch_one(name: str, cache_dir: Path | None = None, out_dir: Path | None = None) -> dict:
    spec = DATASETS[name]
    files = find_files(spec["pattern"], cache_dir)
    if not files:
        raise common.SkipFetch(
            f"{name}: no {spec['pattern']} file in data-cache/. A human downloads it in a browser from {spec['url']} "
            "(read the licence there) and puts the CSV or zip in data-cache/."
        )
    df, total, per_file = sample_files(files)
    path, sha = common.write_parquet(df, name, out_dir)
    infil = {fn: int(c[k]) for fn, c in per_file.items() for k in c if "infil" in k.lower()}
    meta = {
        "source_url": spec["url"], "revision": ", ".join(f"{f.name} sha256 {common.sha256_file(f)[:16]}..." for f in files),
        "licence": LICENCE, "committed": False, "rows": len(df), "source_rows": int(sum(total.values())),
        "label_counts": common.counts(df["attack_class"]), "source_class_counts": {k: int(v) for k, v in sorted(total.items())},
        "infiltration_rows_by_file": infil, "file": path.name, "sha256": sha,
        "notes": f"Seeded Bernoulli sample, ~{SAMPLE_ROWS:,} rows, >= {MIN_PER_CLASS} per class. Cite arXiv:2503.04404.",
    }
    common.write_meta(name, meta, out_dir)
    log.info("%s: %d of %d rows -> %s; infiltration by file %s", name, len(df), meta["source_rows"], path, infil)
    return meta


def main(cache_dir: Path | None = None, out_dir: Path | None = None) -> dict:
    results = {}
    for name in DATASETS:
        try:
            results[name] = fetch_one(name, cache_dir, out_dir)
        except common.SkipFetch as exc:
            log.warning("skipped: %s", exc)
            results[name] = {"skipped": str(exc)}
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
