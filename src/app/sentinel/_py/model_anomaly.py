"""Anomaly models for Sentinel (checklist C4).

Two separate Isolation Forests, never the same object:

* IsoForest #1, ``filter_train(X_train)``: cleans the TRAINING split before
  XGBoost sees it. It is fit on the rows it is given and nothing else, so
  callers must pass the train split only (never test). When labels are passed it
  fits one forest per label, so attack rows are judged against their own kind
  and are not thrown away just for being attacks.
* IsoForest #2, ``fit_baseline(X_clean)``: fit on clean baseline rows only.
  ``anomaly(row)`` turns its score into 0-1, and ``project(row)`` places the
  agent on the 2-D scatter (PCA fitted on the same clean rows).

Run ``python model_anomaly.py`` to fit and save ``artifacts/anomaly.joblib``.
It reads ``data/actions.csv`` when it exists, otherwise a seeded synthetic
contract-A dataset (``synthetic_dataset``) so the pipeline works end to end.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import GroupShuffleSplit

try:  # imported as part of the _py package (tests, api.py)
    from . import contract as C
except ImportError:  # run as a script from _py/
    import contract as C  # type: ignore[no-redef]

log = logging.getLogger("sentinel.anomaly")

HERE = Path(__file__).resolve().parent
ARTIFACT_PATH = HERE / "artifacts" / "anomaly.joblib"
DATA_PATH = HERE / "data" / "actions.csv"

MODEL_INPUTS: tuple[str, ...] = tuple(C.MODEL_INPUTS)
SEED = 7

# IsoForest #1: share of each label's training rows treated as glitches.
FILTER_CONTAMINATION = 0.03
# IsoForest #2 size. 100 trees keeps one-row scoring well under 20 ms.
BASELINE_TREES = 100

# anomaly(): the clean median maps to 0 and the clean 99th percentile to 0.35;
# past p99 it climbs faster and reaches 1 at p99 + SATURATE * (p99 - median).
# (IsoForest scores bunch up near the top, so one straight line never reaches 1.)
P99_ANOMALY = 0.35
SATURATE = 0.6
# project(): radius (0..0.5 space) a clean row at the 99th-percentile PCA
# distance reaches, and the extra radius a fully anomalous row adds on top.
CLEAN_RADIUS = 0.14
ANOMALY_PUSH = 0.30
MAX_RADIUS = 0.48

# Fitted state for IsoForest #1, kept so tests can prove it never saw test rows.
last_filter_index: pd.Index | None = None

_state: dict[str, Any] | None = None


# --------------------------------------------------------------------------
# helpers


def _matrix(X: Any) -> np.ndarray:
    """Model-input matrix (n, 10) from a DataFrame, dict, list of dicts or array."""
    if isinstance(X, pd.DataFrame):
        return X.loc[:, list(MODEL_INPUTS)].to_numpy(dtype=float)
    if isinstance(X, Mapping):
        return np.array([[float(X[c]) for c in MODEL_INPUTS]], dtype=float)
    if isinstance(X, list) and X and isinstance(X[0], Mapping):
        return np.array([[float(r[c]) for c in MODEL_INPUTS] for r in X], dtype=float)
    arr = np.asarray(X, dtype=float)
    return arr.reshape(1, -1) if arr.ndim == 1 else arr


def _robust_scale(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Median and a robust spread per column (IQR/1.349, floored so flags never divide by 0)."""
    med = np.median(M, axis=0)
    q75, q25 = np.percentile(M, [75, 25], axis=0)
    spread = (q75 - q25) / 1.349
    floor = np.maximum(0.1 * np.abs(med), 0.5)
    return med, np.maximum(spread, floor)


# --------------------------------------------------------------------------
# IsoForest #1: training-data cleaner


def filter_train(X_train: Any, y: Any = None, contamination: float = FILTER_CONTAMINATION) -> np.ndarray:
    """IsoForest #1. Returns a bool keep-mask over the rows of ``X_train``.

    Fit ONLY on ``X_train`` (pass the train split, never test). With ``y`` the
    forest is fit per label, so a rare attack class is not dropped wholesale for
    looking different from clean traffic. Logs how many rows it drops.
    """
    global last_filter_index
    if isinstance(X_train, pd.DataFrame):
        last_filter_index = X_train.index.copy()
    else:
        last_filter_index = pd.RangeIndex(len(X_train))
    M = _matrix(X_train)
    keep = np.ones(len(M), dtype=bool)
    groups = np.zeros(len(M), dtype=object) if y is None else np.asarray(y, dtype=object)
    for g in pd.unique(groups):
        idx = np.flatnonzero(groups == g)
        if len(idx) < 20:  # too few rows to call any of them an outlier
            continue
        iso = IsolationForest(n_estimators=100, contamination=contamination, random_state=SEED)
        keep[idx] = iso.fit_predict(M[idx]) == 1
    dropped = int((~keep).sum())
    log.info("IsoForest #1 dropped %d of %d training rows (%.1f%%)", dropped, len(M), 100 * dropped / max(len(M), 1))
    return keep


# --------------------------------------------------------------------------
# IsoForest #2 + PCA: novelty score and scatter position


def fit_baseline(X_clean: Any) -> None:
    """IsoForest #2 + 2-D PCA, both fit on clean baseline rows only."""
    global _state
    M = _matrix(X_clean)
    med, spread = _robust_scale(M)
    Z = (M - med) / spread

    iso = IsolationForest(n_estimators=BASELINE_TREES, random_state=SEED)
    iso.fit(Z)
    raw = -iso.score_samples(Z)  # higher = more anomalous
    raw_med, raw_p99 = float(np.median(raw)), float(np.percentile(raw, 99))

    pca = PCA(n_components=2, random_state=SEED).fit(Z)
    P = pca.transform(Z)
    center = np.median(P, axis=0)
    r99 = float(np.percentile(np.linalg.norm(P - center, axis=1), 99)) or 1.0

    _state = {
        "version": 1,
        "inputs": MODEL_INPUTS,
        "median": med,
        "spread": spread,
        "iso": iso,
        "raw_med": raw_med,
        "raw_p99": max(raw_p99, raw_med + 1e-6),
        "pca": pca,
        "center": center,
        "r99": r99,
        "n_clean": len(M),
    }


def save(path: Path | None = None) -> Path:
    path = path or ARTIFACT_PATH
    if _state is None:
        raise RuntimeError("fit_baseline() first")
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(_state, path)
    return path


def load(path: Path | None = None) -> dict[str, Any]:
    """Load the saved baseline. Raises FileNotFoundError when it is missing."""
    global _state
    path = path or ARTIFACT_PATH
    state = joblib.load(path)
    if tuple(state.get("inputs", ())) != MODEL_INPUTS:
        raise ValueError("anomaly.joblib was built for different MODEL_INPUTS; rerun model_anomaly.py")
    _state = state
    return state


def reset() -> None:
    """Forget the in-memory baseline (tests use this to force a reload)."""
    global _state
    _state = None


def _ready() -> dict[str, Any]:
    return _state if _state is not None else load()


def baseline_normals() -> dict[str, float]:
    """Clean-baseline median of each model input (used by score.py's reasons)."""
    s = _ready()
    return {c: float(v) for c, v in zip(MODEL_INPUTS, s["median"])}


def _z(row: Any, s: dict[str, Any]) -> np.ndarray:
    return (_matrix(row) - s["median"]) / s["spread"]


def _anomaly_from_raw(raw: np.ndarray, s: dict[str, Any]) -> np.ndarray:
    unit = (raw - s["raw_med"]) / (s["raw_p99"] - s["raw_med"])  # 0 at median, 1 at p99
    a = np.where(unit <= 1.0, unit * P99_ANOMALY, P99_ANOMALY + (unit - 1.0) / SATURATE * (1.0 - P99_ANOMALY))
    return np.clip(a, 0.0, 1.0)


def anomaly(row: Any) -> float:
    """IsoForest #2 novelty in 0..1 (0 = typical clean row, 1 = far outside the baseline).

    Calibrated on the clean baseline: its median scores 0, its 99th percentile
    scores 0.35, and the value climbs faster beyond that until it clips at 1.
    """
    s = _ready()
    raw = -s["iso"].score_samples(_z(row, s))
    return float(_anomaly_from_raw(raw, s)[0])


def anomaly_many(X: Any) -> np.ndarray:
    s = _ready()
    return _anomaly_from_raw(-s["iso"].score_samples(_z(X, s)), s)


def _range_excess(z: np.ndarray) -> np.ndarray:
    """How far (in robust spreads) each row sits beyond the clean range, worst column."""
    return np.clip(np.abs(z) - 3.0, 0.0, None).max(axis=1)


def project(row: Any) -> tuple[float, float]:
    """Scatter position (x, y), both clipped to 0..1.

    Direction comes from the clean-baseline PCA. Radius = PCA distance scaled so
    the clean 99th percentile sits at 0.14 from the centre, plus up to 0.30 more
    from ``anomaly(row)``. The push matters because a feature that never moves
    on clean data (touched_decoy is always 0) carries no PCA weight, yet a row
    that sets it must still drift away from the herd.
    """
    s = _ready()
    z = _z(row, s)
    v = s["pca"].transform(z)[0] - s["center"]
    dist = float(np.linalg.norm(v))
    a = float(_anomaly_from_raw(-s["iso"].score_samples(z), s)[0])
    a = max(a, min(1.0, float(_range_excess(z)[0]) / 6.0))
    radius = min(MAX_RADIUS, CLEAN_RADIUS * dist / s["r99"] + ANOMALY_PUSH * a)
    if dist < 1e-9:
        ux, uy = math.cos(math.pi / 4), math.sin(math.pi / 4)
    else:
        ux, uy = v[0] / dist, v[1] / dist
    x = min(1.0, max(0.0, 0.5 + radius * ux))
    y = min(1.0, max(0.0, 0.5 + radius * uy))
    return (round(x, 4), round(y, 4))


# --------------------------------------------------------------------------
# data: the real dataset when Noah's file exists, else a seeded synthetic one


_ROLE_TOOLS = {"researcher": 3, "emailer": 2, "coder": 4, "analyst": 3}


def synthetic_dataset(n: int = 1000, seed: int = SEED, rows_per_run: int = 10) -> pd.DataFrame:
    """Seeded fake contract-A rows (+ label, run_id). Stand-in until data/actions.csv lands.

    About 60% clean and 10% of each attack type, shaped by the plan's attack
    descriptions (prompt_injection = message burst to many peers, often a decoy).
    """
    rng = np.random.default_rng(seed)
    roles = list(C.ROLES)
    labels = rng.choice(
        list(C.TRAIN_LABELS), size=n, p=[0.6, 0.1, 0.1, 0.1, 0.1]
    )
    rows = []
    for i, lab in enumerate(labels):
        role = roles[i % len(roles)]
        base_tools = _ROLE_TOOLS[role]
        r = {
            "agent_id": f"agent-{i % 50 + 1}",
            "role": role,
            "ts": 1794636000.0 + 2 * i,
            "actions_per_min": max(1.0, rng.normal(12, 3)),
            "distinct_tools_used": int(max(1, rng.poisson(base_tools))),
            "distinct_tools_baseline": float(base_tools),
            "failed_calls_per_min": abs(rng.normal(0.3, 0.3)),
            "touched_decoy": 0,
            "out_of_scope_resource": int(rng.random() < 0.01),
            "msgs_to_agents_per_min": float(rng.poisson(1)),
            "distinct_peers": 0,
            "bytes_out_per_min": float(rng.lognormal(7.5, 0.5)),
            "sec_since_normal": 0.0,
            "label": lab,
            "run_id": f"run-{i // rows_per_run}",
        }
        if lab == "prompt_injection":
            r["msgs_to_agents_per_min"] = float(rng.integers(6, 16))
            r["distinct_peers"] = int(rng.integers(4, 8))
            r["touched_decoy"] = int(rng.random() < 0.6)
            r["actions_per_min"] += rng.normal(8, 3)
        elif lab == "tool_misuse":
            r["distinct_tools_used"] = int(rng.integers(8, 13))
            r["failed_calls_per_min"] = rng.uniform(3, 8)
            r["actions_per_min"] = rng.uniform(30, 60)
        elif lab == "data_exfiltration":
            r["bytes_out_per_min"] = float(rng.uniform(50_000, 500_000))
            r["out_of_scope_resource"] = int(rng.random() < 0.5)
            r["touched_decoy"] = int(rng.random() < 0.3)
        elif lab == "privilege_escalation":
            r["out_of_scope_resource"] = 1
            r["failed_calls_per_min"] = rng.uniform(2, 6)
            r["touched_decoy"] = int(rng.random() < 0.4)
        if lab != "clean":
            r["sec_since_normal"] = float(rng.uniform(4, 60))
        if r["distinct_peers"] == 0 and r["msgs_to_agents_per_min"] > 0:
            r["distinct_peers"] = int(min(r["msgs_to_agents_per_min"], rng.integers(1, 3)))
        rows.append(r)
    return pd.DataFrame(rows, columns=list(C.FEATURE_COLUMNS) + [C.RUN_ID_COLUMN])


def load_training_data() -> tuple[pd.DataFrame, str]:
    """(dataframe, source). Prefers Noah's data/actions.csv."""
    if DATA_PATH.exists():
        try:
            try:
                from .features import load_dataset  # type: ignore[attr-defined]
            except ImportError:
                from features import load_dataset  # type: ignore[no-redef]
            return load_dataset(DATA_PATH), str(DATA_PATH)
        except ImportError:
            return pd.read_csv(DATA_PATH), str(DATA_PATH)
    return synthetic_dataset(), "synthetic (data/actions.csv not found)"


def split_by_run(df: pd.DataFrame, test_size: float = 0.25, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train/test split by run_id, so windows from one run never land on both sides."""
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    tr, te = next(gss.split(df, groups=df[C.RUN_ID_COLUMN]))
    return df.iloc[tr], df.iloc[te]


def train(df_train: pd.DataFrame) -> dict[str, int]:
    """Clean the train split (IsoForest #1), then fit IsoForest #2 + PCA on its clean rows."""
    y = df_train[C.LABEL_COLUMN].to_numpy()
    keep = filter_train(df_train, y)
    clean = df_train[keep & (y == "clean")]
    fit_baseline(clean)
    return {"train_rows": len(df_train), "dropped": int((~keep).sum()), "baseline_rows": len(clean)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df, source = load_training_data()
    df_train, df_test = split_by_run(df)
    stats = train(df_train)
    path = save()
    a = anomaly_many(df_test)
    lab = df_test[C.LABEL_COLUMN].to_numpy()
    print(f"data: {source}")
    print(f"train {stats['train_rows']} rows, IsoForest #1 dropped {stats['dropped']}, baseline {stats['baseline_rows']} clean rows")
    print(f"saved {path}")
    for t in C.TRAIN_LABELS:
        m = lab == t
        if m.any():
            print(f"  test {t:<22} n={int(m.sum()):>3}  median anomaly {np.median(a[m]):.2f}")


if __name__ == "__main__":
    main()
