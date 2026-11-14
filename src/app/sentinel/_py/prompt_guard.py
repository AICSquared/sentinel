"""Prompt Guard: a real-data prompt-injection text classifier (issue #25, T4).

TF-IDF (character 3-5-grams + word 1-2-grams) and logistic regression, CPU only.

* **Train:** HF ``jayavibhav/prompt-injection-safety``, split ``train``
  (``data/real/prompt_safety.parquet``, from ``fetch/fetch_prompt_safety.py``),
  plus ``data/real/kaggle_prompts.parquet`` when a human has fetched it.
  Positive = label 1 (prompt injection) or 2 (harmful request): a hijacked
  agent forwards both kinds of instruction, and InjecAgent's attacker
  instructions read like plain harmful requests.
* **Test (cross-dataset):** InjecAgent only (``data/real/injecagent.parquet``),
  never seen in training. The training rows are checked for exact text overlap
  with InjecAgent and the swarm's payloads, and ``train`` refuses to fit if any
  is found.
* **Also reported:** the HF ``test`` split (in-domain) and the false-positive
  rate on the swarm's own clean messages (``BENIGN_TEXT`` in docker/agent/swarm.py).

``python prompt_guard.py`` trains, saves ``artifacts/prompt_guard.joblib`` and
prints the report (also written to ``artifacts/prompt_guard_report.json``).
Missing data is a warning and a skip, never a crash, so the overseer image
builds without ``data/real/``. ``predict`` raises ``FileNotFoundError`` when
the artifact is missing; callers fall back to no prompt score.
"""

from __future__ import annotations

import ast
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, precision_recall_fscore_support
from sklearn.pipeline import make_pipeline, make_union

log = logging.getLogger("sentinel.prompt_guard")

HERE = Path(__file__).resolve().parent
REAL_DIR = HERE / "data" / "real"
TRAIN_PATH = REAL_DIR / "prompt_safety.parquet"
EXTRA_TRAIN_PATH = REAL_DIR / "kaggle_prompts.parquet"
TEST_PATH = REAL_DIR / "injecagent.parquet"
PAYLOADS_PATH = REAL_DIR / "injecagent_payloads.json"
SWARM_PATH = HERE.parents[3] / "docker" / "agent" / "swarm.py"
ARTIFACT_PATH = HERE / "artifacts" / "prompt_guard.joblib"
REPORT_PATH = HERE / "artifacts" / "prompt_guard_report.json"

SEED = 7
POSITIVE_LABELS = frozenset({1, 2})  # HF: 1 prompt injection, 2 harmful request
THRESHOLD = 0.5
MAX_CHARS = 2000  # contract A0: text is truncated to 2,000 characters

_state: dict[str, Any] | None = None


class MissingData(Exception):
    """A training or test file is missing; the caller logs a warning and skips."""


# --------------------------------------------------------------------------
# data


def _norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def _clip(texts: Iterable[str]) -> list[str]:
    return [str(t)[:MAX_CHARS] for t in texts]


def load_train(path: Path | None = None, extra: Path | None = None) -> pd.DataFrame:
    """Training rows: ``text`` and binary ``y`` (HF train split + optional Kaggle rows)."""
    p = path or TRAIN_PATH
    if not p.exists():
        raise MissingData(f"{p} not found: run fetch/fetch_prompt_safety.py (no login needed)")
    df = pd.read_parquet(p)
    if "split" in df:
        df = df[df["split"] == "train"]
    out = pd.DataFrame({"text": df["text"].astype(str), "y": df["label"].astype(int).isin(POSITIVE_LABELS).astype(int)})
    e = extra or EXTRA_TRAIN_PATH
    if e.exists():
        k = pd.read_parquet(e)
        out = pd.concat([out, pd.DataFrame({"text": k["text"].astype(str), "y": (k["label"].astype(int) == 1).astype(int)})])
        log.info("added %d Kaggle rows", len(k))
    return out.drop_duplicates("text").reset_index(drop=True)


def load_holdout(path: Path | None = None) -> pd.DataFrame | None:
    """The HF ``test`` split (in-domain check), or None."""
    p = path or TRAIN_PATH
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "split" not in df:
        return None
    df = df[df["split"] == "test"]
    return pd.DataFrame({"text": df["text"].astype(str), "y": df["label"].astype(int).isin(POSITIVE_LABELS).astype(int)})


def load_injecagent(path: Path | None = None) -> pd.DataFrame:
    p = path or TEST_PATH
    if not p.exists():
        raise MissingData(f"{p} not found: run fetch/fetch_injecagent.py")
    df = pd.read_parquet(p)
    return df.assign(y=df["label"].astype(int))


def held_out_texts(injecagent: pd.DataFrame | None = None, payloads_path: Path | None = None) -> set[str]:
    """Normalised texts that must never be training rows: InjecAgent + swarm payloads."""
    out: set[str] = set()
    if injecagent is not None:
        out |= {_norm(t) for t in injecagent["text"]}
        if "attacker_instruction" in injecagent:
            out |= {_norm(t) for t in injecagent["attacker_instruction"] if str(t).strip()}
    p = payloads_path or PAYLOADS_PATH
    if p.exists():
        out |= {_norm(t) for t in json.loads(p.read_text(encoding="utf-8")).get("payloads", [])}
    return out


def swarm_benign_texts(path: Path | None = None) -> list[str]:
    """The swarm's clean message texts (``BENIGN_TEXT`` in docker/agent/swarm.py), read without importing it."""
    p = path or SWARM_PATH
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "BENIGN_TEXT" for t in node.targets):
            return [str(v) for v in ast.literal_eval(node.value)]
    return []


# --------------------------------------------------------------------------
# model


def _pipeline():
    vec = make_union(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, max_features=200_000),
        TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True),
    )
    return make_pipeline(vec, LogisticRegression(C=4.0, class_weight="balanced", max_iter=2000, random_state=SEED))


def check_no_overlap(train_texts: Iterable[str], forbidden: set[str]) -> None:
    hits = sorted({_norm(t) for t in train_texts} & forbidden)
    if hits:
        raise AssertionError(f"{len(hits)} training texts also appear in InjecAgent or the payloads, e.g. {hits[0][:80]!r}")


def train(df_train: pd.DataFrame | None = None, forbidden: set[str] | None = None) -> dict[str, int]:
    """Fit on ``df_train`` (``text``, ``y``); defaults to the fetched HF train split."""
    global _state
    df = df_train if df_train is not None else load_train()
    if forbidden is None:
        try:
            forbidden = held_out_texts(load_injecagent())
        except MissingData:
            forbidden = held_out_texts(None)
    check_no_overlap(df["text"], forbidden)
    model = _pipeline()
    model.fit(_clip(df["text"]), df["y"].astype(int).to_numpy())
    _state = {"model": model, "threshold": THRESHOLD, "positive_labels": sorted(POSITIVE_LABELS)}
    stats = {"rows": len(df), "positive": int(df["y"].sum())}
    log.info("Prompt Guard fit on %d rows (%d positive)", stats["rows"], stats["positive"])
    return stats


def save(path: Path | None = None) -> Path:
    p = path or ARTIFACT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(_ready(), p)
    return p


def load(path: Path | None = None) -> dict[str, Any]:
    global _state
    _state = joblib.load(path or ARTIFACT_PATH)
    return _state


def reset() -> None:
    global _state
    _state = None


def _ready() -> dict[str, Any]:
    return _state if _state is not None else load()


def predict_many(texts: Iterable[str]) -> np.ndarray:
    """Injection probability (0-1) per text; empty text scores 0."""
    texts = list(texts)
    out = np.zeros(len(texts))
    idx = [i for i, t in enumerate(texts) if t is not None and str(t).strip()]
    if idx:
        out[idx] = _ready()["model"].predict_proba(_clip(texts[i] for i in idx))[:, 1]
    return out


def predict(text: str | None) -> float:
    """Probability (0-1) that ``text`` is a prompt injection. 0.0 for empty text."""
    if text is None or not str(text).strip():
        return 0.0
    return float(predict_many([text])[0])


# --------------------------------------------------------------------------
# report


def _metrics(y: np.ndarray, p: np.ndarray, threshold: float = THRESHOLD) -> dict[str, float]:
    yhat = (p >= threshold).astype(int)
    prec, rec, f1, _ = precision_recall_fscore_support(y, yhat, average="binary", zero_division=0)
    neg = y == 0
    return {
        "precision": float(prec), "recall": float(rec), "f1": float(f1),
        "support": int(y.sum()), "negatives": int(neg.sum()),
        "false_positive_rate": float(yhat[neg].mean()) if neg.any() else float("nan"),
    }


def report(injecagent: pd.DataFrame | None = None, holdout: pd.DataFrame | None = None,
           swarm_texts: list[str] | None = None) -> dict:
    """Precision/recall on InjecAgent (cross-dataset), checked against sklearn's classification_report."""
    ia = injecagent if injecagent is not None else load_injecagent()
    y = ia["y"].to_numpy(dtype=int)
    t0 = time.perf_counter()
    p = predict_many(ia["text"])
    ms = 1000 * (time.perf_counter() - t0) / max(len(ia), 1)
    out: dict[str, Any] = {"dataset": "InjecAgent", "threshold": THRESHOLD, "injecagent": _metrics(y, p)}

    # second, independent check: sklearn's classification_report on the same predictions
    cr = classification_report(y, (p >= THRESHOLD).astype(int), output_dict=True, zero_division=0)
    second = cr.get("1", {})
    out["second_check"] = {"precision": float(second.get("precision", 0.0)), "recall": float(second.get("recall", 0.0))}
    assert abs(out["second_check"]["precision"] - out["injecagent"]["precision"]) < 1e-9
    assert abs(out["second_check"]["recall"] - out["injecagent"]["recall"]) < 1e-9

    if "variant" in ia:
        out["recall_by_variant"] = {
            str(v): float((p[(ia["variant"] == v).to_numpy() & (y == 1)] >= THRESHOLD).mean())
            for v in sorted(ia.loc[ia["y"] == 1, "variant"].unique())
        }
    if "kind" in ia:
        out["flagged_by_benign_kind"] = {
            str(k): f"{int((p[(ia['kind'] == k).to_numpy()] >= THRESHOLD).sum())}/{int((ia['kind'] == k).sum())}"
            for k in sorted(ia.loc[ia["y"] == 0, "kind"].unique())
        }
    out["ms_per_message_batch"] = round(ms, 3)
    t0 = time.perf_counter()
    for text in ia["text"].head(200):
        predict(text)
    out["ms_per_message"] = round(1000 * (time.perf_counter() - t0) / min(200, len(ia)), 3)

    ho = holdout if holdout is not None else load_holdout()
    if ho is not None and len(ho):
        out["hf_test_in_domain"] = _metrics(ho["y"].to_numpy(dtype=int), predict_many(ho["text"]))
    if PAYLOADS_PATH.exists():  # the attack texts the live swarm sends (a subset of InjecAgent)
        pl = json.loads(PAYLOADS_PATH.read_text(encoding="utf-8")).get("payloads", [])
        if pl:
            pp = predict_many(pl)
            out["swarm_payloads"] = {"n": len(pl), "flagged": int((pp >= THRESHOLD).sum()),
                                     "median_probability": round(float(np.median(pp)), 3)}
    sw = swarm_texts if swarm_texts is not None else swarm_benign_texts()
    if sw:
        ps = predict_many(sw)
        out["swarm_clean_messages"] = {
            "n": len(sw), "flagged": int((ps >= THRESHOLD).sum()),
            "false_positive_rate": float((ps >= THRESHOLD).mean()), "max_probability": round(float(ps.max()), 3),
        }
    return out


def format_report(rep: dict) -> str:
    m = rep["injecagent"]
    lines = [
        f"InjecAgent (cross-dataset, threshold {rep['threshold']}): precision {m['precision']:.3f}  recall {m['recall']:.3f}  "
        f"F1 {m['f1']:.3f}  ({m['support']} attacks, {m['negatives']} benign; benign flagged {m['false_positive_rate']:.0%})",
        f"  second check (sklearn classification_report): precision {rep['second_check']['precision']:.3f}  recall {rep['second_check']['recall']:.3f}",
    ]
    if "recall_by_variant" in rep:
        lines.append("  recall by variant: " + ", ".join(f"{k} {v:.2f}" for k, v in rep["recall_by_variant"].items()))
    if "flagged_by_benign_kind" in rep:
        lines.append("  benign flagged: " + ", ".join(f"{k} {v}" for k, v in rep["flagged_by_benign_kind"].items()))
    if "hf_test_in_domain" in rep:
        h = rep["hf_test_in_domain"]
        lines.append(f"HF test split (in-domain): precision {h['precision']:.3f}  recall {h['recall']:.3f}  benign flagged {h['false_positive_rate']:.1%}")
    if "swarm_clean_messages" in rep:
        s = rep["swarm_clean_messages"]
        lines.append(f"swarm clean messages: {s['flagged']}/{s['n']} flagged (max p {s['max_probability']})")
    if "swarm_payloads" in rep:
        s = rep["swarm_payloads"]
        lines.append(f"swarm attack payloads: {s['flagged']}/{s['n']} flagged (median p {s['median_probability']})")
    lines.append(f"speed: {rep['ms_per_message']} ms per message (one at a time), {rep['ms_per_message_batch']} ms in a batch")
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        t0 = time.perf_counter()
        train()
        path = save()
        rep = report()
    except MissingData as exc:
        log.warning("Prompt Guard skipped (the overseer runs without prompt scores): %s", exc)
        return 0
    REPORT_PATH.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    print(format_report(rep))
    print(f"saved {path} and {REPORT_PATH.name} in {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
