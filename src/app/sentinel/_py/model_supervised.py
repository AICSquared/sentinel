"""Supervised attack classifier: XGBoost on the ten contract-A model inputs (checklist C3).

Pipeline (``python model_supervised.py`` from ``_py/``):

1. ``load_dataset(data/actions.csv)``; generated first by ``make_dataset`` if missing.
2. ``split(df)``: train/test by ``run_id`` (never by row), stratified by each
   run's attack type so every type lands in the test split.
3. ``train(df_train)``: IsoForest #1 (``model_anomaly.filter_train``) cleans the
   TRAIN split only, then XGBoost learns ``clean`` + the 4 attack types.
4. ``report(df_test)``: precision and recall per attack type on held-out runs.
5. Saves ``artifacts/supervised.joblib``; ``predict(row)`` loads it lazily.

``predict(row)`` returns ``{"attack_type", "p_attack", "top_features"}``:
``p_attack`` = 1 - P(clean); ``top_features`` = this row's largest positive
XGBoost contributions (SHAP values, ``pred_contribs=True``) toward its most
likely attack type, as ``[(feature_name, contribution), ...]``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

try:  # imported as part of the _py package (tests, api.py, score.py)
    from . import contract as C
    from . import model_anomaly as MA
    from .features import load_dataset
except ImportError:  # run as a script from _py/
    import contract as C  # type: ignore[no-redef]
    import model_anomaly as MA  # type: ignore[no-redef]
    from features import load_dataset  # type: ignore[no-redef]

log = logging.getLogger("sentinel.supervised")

HERE = Path(__file__).resolve().parent
ARTIFACT_PATH = HERE / "artifacts" / "supervised.joblib"
DATA_PATH = HERE / "data" / "actions.csv"

MODEL_INPUTS: list[str] = list(C.MODEL_INPUTS)
SEED = 7
TEST_SHARE = 0.3
TOP_K = 3
XGB_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.1,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "tree_method": "hist",
    "random_state": SEED,
    "n_jobs": 2,
}

_state: dict[str, Any] | None = None


# --------------------------------------------------------------------------
# split


def run_types(df: pd.DataFrame) -> pd.Series:
    """Attack type of each run: its most common non-clean label, or ``clean``."""
    def kind(labels: pd.Series) -> str:
        attacks = labels[labels != "clean"]
        return str(attacks.mode().iloc[0]) if len(attacks) else "clean"

    return df.groupby(C.RUN_ID_COLUMN)[C.LABEL_COLUMN].agg(kind)


def split(df: pd.DataFrame, test_share: float = TEST_SHARE, seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(train, test) by ``run_id``: no run on both sides, every run type in test."""
    rng = np.random.default_rng(seed)
    test_runs: list[str] = []
    types = run_types(df)
    for _, runs in types.groupby(types):
        ids = sorted(runs.index)
        n = max(1, int(round(test_share * len(ids)))) if len(ids) > 1 else 0
        test_runs += list(rng.choice(ids, size=n, replace=False))
    is_test = df[C.RUN_ID_COLUMN].isin(test_runs)
    return df.loc[~is_test], df.loc[is_test]


# --------------------------------------------------------------------------
# train / save / load


def _matrix(X: Any) -> pd.DataFrame:
    """Model-input frame (n, 10), columns named, from a DataFrame, dict or list of dicts."""
    if isinstance(X, pd.DataFrame):
        return X.loc[:, MODEL_INPUTS].astype(float)
    if isinstance(X, Mapping):
        X = [X]
    return pd.DataFrame([[float(r[c]) for c in MODEL_INPUTS] for r in X], columns=MODEL_INPUTS)


def train(df_train: pd.DataFrame) -> dict[str, int]:
    """IsoForest #1 on the train split, then XGBoost on the rows it keeps."""
    global _state
    from xgboost import XGBClassifier

    y_all = df_train[C.LABEL_COLUMN].astype(str).to_numpy()
    if "unknown" in set(y_all):
        raise ValueError("`unknown` is never a training label")
    keep = MA.filter_train(df_train, y_all)
    X = _matrix(df_train.loc[keep])
    y = y_all[keep]
    classes = [c for c in C.TRAIN_LABELS if c in set(y)]
    if "clean" not in classes:
        raise ValueError("training data needs clean rows")
    clf = XGBClassifier(objective="multi:softprob", num_class=len(classes), **XGB_PARAMS)
    clf.fit(X, np.array([classes.index(v) for v in y]))
    _state = {"model": clf, "classes": classes, "inputs": MODEL_INPUTS}
    stats = {"train_rows": len(df_train), "dropped": int((~keep).sum()), "fit_rows": int(keep.sum())}
    log.info("XGBoost fit on %d rows (%d dropped by IsoForest #1), classes %s", stats["fit_rows"], stats["dropped"], classes)
    return stats


def save(path: Path | None = None) -> Path:
    p = path or ARTIFACT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(_ready(), p)
    return p


def load(path: Path | None = None) -> dict[str, Any]:
    global _state
    _state = joblib.load(path or ARTIFACT_PATH)
    if list(_state["inputs"]) != MODEL_INPUTS:
        raise ValueError("supervised artifact was trained on different MODEL_INPUTS; retrain")
    return _state


def reset() -> None:
    global _state
    _state = None


def _ready() -> dict[str, Any]:
    """The trained model; loads the artifact on first use (raises if it is missing)."""
    return _state if _state is not None else load()


# --------------------------------------------------------------------------
# predict / report


def predict_proba(X: Any) -> tuple[np.ndarray, list[str]]:
    s = _ready()
    return s["model"].predict_proba(_matrix(X)), list(s["classes"])


def predict(row: Mapping[str, Any]) -> dict:
    """One feature row (columns 1-13) -> attack_type, p_attack, top_features."""
    import xgboost as xgb

    s = _ready()
    x = _matrix(row)
    p = s["model"].predict_proba(x)[0]
    classes: list[str] = s["classes"]
    clean_i = classes.index("clean")
    attack_i = [i for i in range(len(classes)) if i != clean_i]
    target = max(attack_i, key=lambda i: p[i]) if attack_i else clean_i

    contribs = s["model"].get_booster().predict(xgb.DMatrix(x), pred_contribs=True)
    contribs = np.asarray(contribs)
    per_feat = contribs[0, target, :-1] if contribs.ndim == 3 else contribs[0, :-1]  # drop the bias column
    order = np.argsort(-per_feat)
    top = [(MODEL_INPUTS[i], round(float(per_feat[i]), 3)) for i in order if per_feat[i] > 0][:TOP_K]
    if not top:
        top = [(MODEL_INPUTS[i], round(float(per_feat[i]), 3)) for i in np.argsort(-np.abs(per_feat))[:TOP_K]]
    return {
        "attack_type": classes[int(p.argmax())],
        "p_attack": float(np.clip(1.0 - p[clean_i], 0.0, 1.0)),
        "top_features": top,
    }


def report(df_test: pd.DataFrame) -> dict:
    """Precision and recall per attack type (and clean) on held-out rows."""
    proba, classes = predict_proba(df_test)
    pred = np.array(classes)[proba.argmax(axis=1)]
    truth = df_test[C.LABEL_COLUMN].astype(str).to_numpy()
    per_type: dict[str, dict[str, float]] = {}
    for label in C.TRAIN_LABELS:
        tp = int(((truth == label) & (pred == label)).sum())
        fp = int(((truth != label) & (pred == label)).sum())
        fn = int(((truth == label) & (pred != label)).sum())
        per_type[label] = {
            "n": tp + fn,
            "precision": tp / (tp + fp) if tp + fp else float("nan"),
            "recall": tp / (tp + fn) if tp + fn else float("nan"),
        }
    is_attack, said_attack = truth != "clean", pred != "clean"
    return {
        "rows": int(len(truth)),
        "runs": int(df_test[C.RUN_ID_COLUMN].nunique()) if C.RUN_ID_COLUMN in df_test else None,
        "accuracy": float((truth == pred).mean()) if len(truth) else float("nan"),
        "attack_detection": {  # any attack type vs clean
            "precision": float((is_attack & said_attack).sum() / max(said_attack.sum(), 1)),
            "recall": float((is_attack & said_attack).sum() / max(is_attack.sum(), 1)),
        },
        "per_type": per_type,
    }


def format_report(rep: dict) -> str:
    lines = [f"{'attack_type':<22}{'n':>5}{'precision':>11}{'recall':>9}"]
    for label, m in rep["per_type"].items():
        lines.append(f"{label:<22}{m['n']:>5}{m['precision']:>11.2f}{m['recall']:>9.2f}")
    ad = rep["attack_detection"]
    lines.append(f"{'any attack vs clean':<22}{'':>5}{ad['precision']:>11.2f}{ad['recall']:>9.2f}")
    lines.append(f"accuracy {rep['accuracy']:.3f} on {rep['rows']} rows from {rep['runs']} held-out runs")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.perf_counter()
    if not DATA_PATH.exists():
        try:
            from . import make_dataset as MD  # type: ignore[attr-defined]
        except ImportError:
            import make_dataset as MD  # type: ignore[no-redef]
        df, _ = MD.make_dataset()
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATA_PATH, index=False)
    df = load_dataset(DATA_PATH)
    df_train, df_test = split(df)
    overlap = set(df_train[C.RUN_ID_COLUMN]) & set(df_test[C.RUN_ID_COLUMN])
    assert not overlap, f"run_id on both sides: {overlap}"
    stats = train(df_train)
    path = save()
    rep = report(df_test)
    print(f"data: {DATA_PATH} ({len(df)} rows); train {stats['train_rows']} rows "
          f"({df_train[C.RUN_ID_COLUMN].nunique()} runs), IsoForest #1 dropped {stats['dropped']}")
    print(format_report(rep))
    imp = sorted(zip(MODEL_INPUTS, _ready()["model"].feature_importances_), key=lambda t: -t[1])
    print("feature importance: " + ", ".join(f"{n} {v:.2f}" for n, v in imp[:5]))
    print(f"saved {path} in {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
