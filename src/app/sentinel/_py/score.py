"""One row in, one contract-B verdict out (checklist C5).

Risk formula (both parts 0-100):

    S = 100 * p_attack            supervised XGBoost (model_supervised.predict)
    A = 100 * anomaly(row)        IsoForest #2 on the clean baseline (model_anomaly)
    P = 100 * prompt_risk         Prompt Guard: the highest injection probability
                                  over the window's messages (absent means 0)
    risk = round(max(0.65*S + 0.35*A, 0.85*S, 0.8*A, 0.9*P))

* The weighted blend trusts the classifier most, because it was trained on
  labelled attacks. The anomaly part lifts rows the classifier is unsure about.
* ``0.85*S`` lets a confident classifier reach quarantine (up to 85) for a
  known attack that barely moves the anomaly score (e.g. a quiet exfiltration).
* ``0.8*A`` lets the anomaly model alone reach quarantine (up to 80) for a
  pattern the classifier has never seen. Terminate (95+) needs both models.
* ``0.9*P`` lets Prompt Guard alone reach quarantine (up to 90) when an agent
  sends a message that reads like an injection but behaves normally so far.
  Terminate still needs the behaviour models.
* ``attack_type`` is ``clean`` below 40, ``unknown`` when risk is 40+ but the
  classifier says clean (p_attack < 0.5 or label ``clean``): a possible novel
  attack. Otherwise it is the classifier's label. When ``0.9*P`` is what lifts
  the risk to 40+ and the classifier says clean, it is ``prompt_injection``.
* ``components.prompt`` (0-100) is present only when the row has ``prompt_risk``,
  so consumers of rows without it see exactly the same keys and numbers.
* ``recommended_action`` comes from ``contract.action_for`` (the tier table).

If the model files or ``model_supervised`` can't load, ``score`` switches to
``fallback_score`` (a frequency count of red flags) and sets
``components.fallback = true``.

``python score.py --report`` prints per-attack-type precision and recall of the
blended output on a held-out split (by run_id), plus a novel-attack check.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Callable, Iterable, Protocol

try:
    from . import contract as C
    from . import model_anomaly as MA
except ImportError:  # run as a script from _py/
    import contract as C  # type: ignore[no-redef]
    import model_anomaly as MA  # type: ignore[no-redef]

log = logging.getLogger("sentinel.score")

W_SUPERVISED = 0.65
W_ANOMALY = 0.35
SUPERVISED_ALONE = 0.85
ANOMALY_ALONE = 0.8
PROMPT_ALONE = 0.9
PROMPT_FLAG_AT = 0.8  # fallback: a Prompt Guard probability this high is a red flag
PROMPT_REASON_AT = 0.5  # mention the message in the reason from this probability
RETRY_S = 30.0  # after a failed model load, try again at most this often

Predict = Callable[[dict], dict]


class GraphLike(Protocol):
    def related(self, agent_id: str, risks: dict[str, int]) -> list[dict]: ...


# Last risk per agent, so graph.related() can judge partners.
_risks: dict[str, int] = {}

_supervised: Predict | None = None
_supervised_injected = False
_load_failed_at: float | None = None


def set_supervised(predict: Predict | None) -> None:
    """Use this predict function instead of importing model_supervised (tests, the report)."""
    global _supervised, _supervised_injected, _load_failed_at
    _supervised, _supervised_injected, _load_failed_at = predict, predict is not None, None


def reload_models() -> None:
    """Forget loaded models; the next score() loads them again."""
    global _supervised, _load_failed_at
    MA.reset()
    if not _supervised_injected:
        _supervised = None
    _load_failed_at = None


def _models() -> Predict | None:
    """The supervised predict function once both models are loaded, else None."""
    global _supervised, _load_failed_at
    if _load_failed_at is not None and time.monotonic() - _load_failed_at < RETRY_S:
        return None
    try:
        MA._ready()
        if _supervised is None:
            try:
                from . import model_supervised as MS  # type: ignore[attr-defined]
            except ImportError:
                import model_supervised as MS  # type: ignore[no-redef]
            _supervised = MS.predict
        _load_failed_at = None
        return _supervised
    except Exception as exc:  # missing files, missing xgboost, bad pickle
        if _load_failed_at is None:
            log.warning("models unavailable, using the frequency-count fallback: %s", exc)
        _load_failed_at = time.monotonic()
        return None


def _prompt(row: dict) -> float | None:
    """The row's Prompt Guard probability (0-1), or None when the row has none."""
    v = row.get("prompt_risk")
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return None
    return min(1.0, max(0.0, v))


# --------------------------------------------------------------------------
# frequency-count fallback (no model files needed)

FALLBACK_NORMALS: dict[str, float] = {
    "actions_per_min": 12.0,
    "failed_calls_per_min": 0.3,
    "msgs_to_agents_per_min": 1.0,
    "distinct_peers": 1.0,
    "bytes_out_per_min": 2000.0,
    "sec_since_normal": 0.0,
}


def _flags(row: dict) -> list[tuple[int, str]]:
    """(points, name) for every red flag the row raises."""
    n = FALLBACK_NORMALS
    tools_normal = max(float(row["distinct_tools_baseline"]), 1.0)
    rules = [
        (40, "touched_decoy", row["touched_decoy"] >= 1),
        (20, "out_of_scope_resource", row["out_of_scope_resource"] >= 1),
        (25, "msgs_to_agents_per_min", row["msgs_to_agents_per_min"] >= 4 * n["msgs_to_agents_per_min"]),
        (15, "distinct_peers", row["distinct_peers"] >= 4),
        (15, "failed_calls_per_min", row["failed_calls_per_min"] >= 2.0),
        (20, "bytes_out_per_min", row["bytes_out_per_min"] >= 10 * n["bytes_out_per_min"]),
        (15, "distinct_tools_used", row["distinct_tools_used"] >= 2 * tools_normal),
        (10, "actions_per_min", row["actions_per_min"] >= 2.5 * n["actions_per_min"]),
        (10, "sec_since_normal", row["sec_since_normal"] >= 30),
        (40, "prompt_risk", (_prompt(row) or 0.0) >= PROMPT_FLAG_AT),
    ]
    return [(pts, name) for pts, name, hit in rules if hit]


def fallback_score(row: dict) -> int:
    """Frequency-count rule: add fixed points for each red flag, cap at 100.

    Decoy +40, out-of-scope +20, message burst (4x normal) +25, 4+ peers +15,
    2+ failed calls/min +15, 10x normal bytes out +20, 2x the role's tools +15,
    2.5x normal actions +10, abnormal for 30+ s +10, a message Prompt Guard
    scores ``prompt_risk >= 0.8`` +40. A decoy plus a message burst to 4+ peers
    is 80 (quarantine); a burst alone, or an injection-like message alone, is
    40 (throttle).
    """
    return min(100, sum(pts for pts, _ in _flags(row)))


def _fallback_type(row: dict, risk: int) -> str:
    if risk < C.THROTTLE_AT:
        return "clean"
    names = {name for _, name in _flags(row)}
    if names & {"prompt_risk", "msgs_to_agents_per_min", "distinct_peers"}:
        return "prompt_injection"
    if "bytes_out_per_min" in names:
        return "data_exfiltration"
    if "out_of_scope_resource" in names:
        return "privilege_escalation"
    if names & {"distinct_tools_used", "failed_calls_per_min", "actions_per_min"}:
        return "tool_misuse"
    return "unknown"


# --------------------------------------------------------------------------
# plain-language reason


def _num(v: float) -> str:
    v = float(v)
    return f"{v:.0f}" if abs(v) >= 10 or v == int(v) else f"{v:.1f}"


def _kb(v: float) -> str:
    return _num(v / 1000.0)


def _a(word: str) -> str:
    return ("an " if word[:1] in "aeiou" else "a ") + word


def _plural(v: float, word: str) -> str:
    return word if _num(v) == "1" else word + "s"


# feature -> (phrase builder, floor used when the normal value is ~0, weight)
_PHRASES: dict[str, tuple[Callable[[float, float, dict], str], float, float]] = {
    "touched_decoy": (lambda v, n, r: "touched a decoy credential", 1, 0),
    "out_of_scope_resource": (lambda v, n, r: f"reached a resource outside the {r.get('role', 'agent')} role", 1, 0),
    "msgs_to_agents_per_min": (
        lambda v, n, r: f"sent {_num(v)} {_plural(v, 'message')} to other agents in one minute (normal: {_num(n)})", 1, 1.0),
    "distinct_peers": (
        lambda v, n, r: f"messaged {_num(v)} other {_plural(v, 'agent')} in one minute (normal: {_num(n)})", 1, 1.0),
    "bytes_out_per_min": (
        lambda v, n, r: f"sent {_kb(v)} KB out in one minute (normal: {_kb(n)} KB)", 1000, 1.0),
    "failed_calls_per_min": (
        lambda v, n, r: f"had {_num(v)} failed {_plural(v, 'call')} in one minute (normal: {_num(n)})", 1, 1.0),
    "distinct_tools_used": (
        lambda v, n, r: f"used {_num(v)} different tools (normal for {_a(str(r.get('role', 'agent')))}: {_num(n)})", 1, 1.0),
    "actions_per_min": (
        lambda v, n, r: f"made {_num(v)} {_plural(v, 'action')} in one minute (normal: {_num(n)})", 1, 0.8),
    "sec_since_normal": (
        lambda v, n, r: f"has acted abnormally for {_num(v)} {_plural(v, 'second')}", 10, 0.3),
}
_FLAG_PRIORITY = {"touched_decoy": 100.0, "out_of_scope_resource": 50.0}


def _normal(name: str, row: dict, normals: dict[str, float]) -> float:
    if name == "distinct_tools_used":
        return float(row["distinct_tools_baseline"])
    return float(normals.get(name, FALLBACK_NORMALS.get(name, 0.0)))


def _top_deviations(row: dict, normals: dict[str, float], hints: Iterable[str] = ()) -> list[str]:
    """Features ranked by how far above normal they are (in multiples of the normal value)."""
    hinted = set(hints)
    ranked: list[tuple[float, str]] = []
    for name, (_, floor, weight) in _PHRASES.items():
        v = float(row[name])
        if name in _FLAG_PRIORITY:
            # A decoy is always out of scope too; saying both repeats ourselves.
            if name == "out_of_scope_resource" and row["touched_decoy"] >= 1:
                continue
            if v >= 1:
                ranked.append((_FLAG_PRIORITY[name], name))
            continue
        n = _normal(name, row, normals)
        dev = (v - n) / max(n, floor) * weight
        if dev > 1.0:  # at least double the normal value
            ranked.append((dev * (1.5 if name in hinted else 1.0), name))
    ranked.sort(reverse=True)
    names = [name for _, name in ranked]
    # Two phrases about messaging say the same thing; keep the stronger one.
    if "msgs_to_agents_per_min" in names and "distinct_peers" in names:
        names.remove(max(("msgs_to_agents_per_min", "distinct_peers"), key=names.index))
    return names[:2]


def _prompt_phrase(p: float) -> str:
    return f"sent a message that reads like a prompt injection ({round(100 * p)}% confidence)"


def reason(row: dict, risk: int, normals: dict[str, float], hints: Iterable[str] = (),
           prompt_leads: bool = False) -> str:
    """One plain sentence from the top 2 contributors, with real numbers and units.

    The contributors are the biggest behaviour deviations plus, when Prompt Guard
    is at least 50% sure, the injection-like message: first when it drives the
    risk (``prompt_leads``), otherwise second.
    """
    top = _top_deviations(row, normals, hints)
    parts = [_PHRASES[name][0](float(row[name]), _normal(name, row, normals), row) for name in top]
    p = _prompt(row)
    if p is not None and p >= PROMPT_REASON_AT:
        phrase = _prompt_phrase(p)
        parts = [phrase] + parts[:1] if prompt_leads else parts[:1] + [phrase]
    if not parts:
        a, n = float(row["actions_per_min"]), _normal("actions_per_min", row, normals)
        decoy = "touched a decoy" if row["touched_decoy"] >= 1 else "no decoys touched"
        lead = "Normal activity" if risk < C.THROTTLE_AT else "Unusual mix of activity"
        return f"{lead}: {_num(a)} {_plural(a, 'action')} in one minute (normal: {_num(n)}), {decoy}."
    text = " and ".join(parts)
    if risk < C.THROTTLE_AT:
        return f"Below the alert line, but {text}."
    return text[0].upper() + text[1:] + "."


# --------------------------------------------------------------------------
# score


def _round(x: float) -> int:
    return int(max(0, min(100, math.floor(x + 0.5))))


def blend(p_attack: float, anomaly: float, prompt_risk: float = 0.0) -> int:
    """The risk formula from the module docstring."""
    s, a, p = 100.0 * p_attack, 100.0 * anomaly, 100.0 * prompt_risk
    return _round(max(W_SUPERVISED * s + W_ANOMALY * a, SUPERVISED_ALONE * s, ANOMALY_ALONE * a, PROMPT_ALONE * p))


def _related(agent_id: str, graph: GraphLike | None) -> list[dict]:
    if graph is None:
        return []
    try:
        return list(graph.related(agent_id, _risks))
    except Exception as exc:  # never lose a verdict because of the graph
        log.warning("graph.related failed for %s: %s", agent_id, exc)
        return []


def score(row: dict, graph: GraphLike | None = None) -> dict:
    """A contract-B response for one feature row (columns 1-13)."""
    agent_id = str(row["agent_id"])
    predict = _models()
    sup_pct = anom_pct = 0
    prompt = _prompt(row)
    prompt_leads = False
    fallback = predict is None
    if not fallback:
        try:
            pred = predict(row)
            p_attack = float(pred["p_attack"])
            a = MA.anomaly(row)
            risk = blend(p_attack, a, prompt or 0.0)
            sup_pct, anom_pct = int(round(100 * p_attack)), int(round(100 * a))
            if prompt is not None:
                prompt_leads = _round(PROMPT_ALONE * 100.0 * prompt) > blend(p_attack, a)
            label = str(pred.get("attack_type", "clean"))
            says_clean = label == "clean" or label not in C.ATTACK_TYPES or p_attack < 0.5
            if risk < C.THROTTLE_AT:
                attack_type = "clean"
            elif says_clean and prompt_leads:
                attack_type = "prompt_injection"
            elif says_clean:
                attack_type = "unknown"
            else:
                attack_type = label
            hints = [str(f[0]) for f in pred.get("top_features", [])[:2]]
            normals = MA.baseline_normals()
        except Exception as exc:
            log.warning("model scoring failed for %s, using fallback: %s", agent_id, exc)
            fallback = True
    if fallback:
        risk = fallback_score(row)
        attack_type = _fallback_type(row, risk)
        hints, normals = [], FALLBACK_NORMALS
        flags = _flags(row)
        prompt_leads = any(n == "prompt_risk" for _, n in flags) and \
            sum(pts for pts, n in flags if n != "prompt_risk") < 40
    _risks[agent_id] = risk
    components: dict[str, Any] = {"supervised": sup_pct, "anomaly": anom_pct, "fallback": fallback}
    if prompt is not None:
        components["prompt"] = int(round(100 * prompt))
    return {
        "agent_id": agent_id,
        "ts": float(row["ts"]),
        "risk": risk,
        "attack_type": attack_type,
        "reason": reason(row, risk, normals, hints, prompt_leads),
        "related_agents": _related(agent_id, graph),
        "recommended_action": C.action_for(risk),
        "components": components,
    }


# --------------------------------------------------------------------------
# report: per-attack-type precision/recall of the blended output


def stand_in_supervised(df_train: Any) -> Predict:
    """XGBoost trained like model_supervised.train (after IsoForest #1), for the report and tests.

    Uses sklearn's HistGradientBoosting when the xgboost library can't load.
    Replaced by Noah's model_supervised.predict once it is on main.
    """
    import numpy as np

    y_all = df_train[C.LABEL_COLUMN].to_numpy()
    keep = MA.filter_train(df_train, y_all)
    X = df_train.loc[keep, list(C.MODEL_INPUTS)].to_numpy(dtype=float)
    y = y_all[keep]
    classes = sorted(set(y))
    yi = np.array([classes.index(v) for v in y])
    try:
        from xgboost import XGBClassifier

        clf: Any = XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.2, random_state=MA.SEED, n_jobs=1)
        clf.fit(X, yi)
        stand_in_supervised.engine = "xgboost"  # type: ignore[attr-defined]
    except Exception:
        from sklearn.ensemble import HistGradientBoostingClassifier

        clf = HistGradientBoostingClassifier(max_iter=40, max_depth=4, random_state=MA.SEED)
        clf.fit(X, yi)
        stand_in_supervised.engine = "sklearn HistGradientBoosting (xgboost unavailable)"  # type: ignore[attr-defined]
    clean_i = classes.index("clean") if "clean" in classes else None

    def predict(row: dict) -> dict:
        x = np.array([[float(row[c]) for c in C.MODEL_INPUTS]])
        p = clf.predict_proba(x)[0]
        best = int(p.argmax())
        p_attack = 1.0 - (float(p[clean_i]) if clean_i is not None else 0.0)
        return {"attack_type": classes[best], "p_attack": p_attack, "top_features": []}

    return predict


def _prf(truth: list[str], pred: list[str], label: str) -> tuple[float, float, int]:
    tp = sum(t == label and p == label for t, p in zip(truth, pred))
    fp = sum(t != label and p == label for t, p in zip(truth, pred))
    fn = sum(t == label and p != label for t, p in zip(truth, pred))
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    return prec, rec, tp + fn


def report(holdout: str = "tool_misuse") -> dict:
    """Fit both models on the train split, score the test split row by row, print a table."""
    df, source = MA.load_training_data()
    df_train, df_test = MA.split_by_run(df)
    MA.train(df_train)

    try:  # Noah's real model, trained on the same split
        try:
            from . import model_supervised as MS  # type: ignore[attr-defined]
        except ImportError:
            import model_supervised as MS  # type: ignore[no-redef]
        MS.train(df_train)
        supervised: Predict = MS.predict
        engine = "model_supervised (XGBoost)"
    except Exception:
        supervised = stand_in_supervised(df_train)
        engine = "stand-in " + stand_in_supervised.engine  # type: ignore[attr-defined]
    set_supervised(supervised)

    rows = df_test.to_dict("records")
    t0 = time.perf_counter()
    out = [score(r) for r in rows]
    ms = (time.perf_counter() - t0) * 1000 / max(len(rows), 1)
    t0 = time.perf_counter()
    for r in rows:
        MA.anomaly(r)
    ms_anom = (time.perf_counter() - t0) * 1000 / max(len(rows), 1)
    truth = [r[C.LABEL_COLUMN] for r in rows]
    pred = [o["attack_type"] for o in out]

    per_type = {}
    print(f"data: {source}; test rows: {len(rows)} (split by run_id); supervised: {engine}")
    print(f"{'attack_type':<22}{'n':>5}{'precision':>11}{'recall':>9}")
    for label in C.TRAIN_LABELS:
        p, r, n = _prf(truth, pred, label)
        per_type[label] = {"n": n, "precision": p, "recall": r}
        print(f"{label:<22}{n:>5}{p:>11.2f}{r:>9.2f}")
    attacks = [i for i, t in enumerate(truth) if t != "clean"]
    caught = sum(out[i]["risk"] >= C.THROTTLE_AT for i in attacks)
    clean_rows = [i for i, t in enumerate(truth) if t == "clean"]
    false_q = sum(out[i]["risk"] >= C.QUARANTINE_AT for i in clean_rows)
    print(f"attack rows scored 40+: {caught}/{len(attacks)}; clean rows scored 75+: {false_q}/{len(clean_rows)}")
    print(f"unknown verdicts: {pred.count('unknown')}; scoring time {ms:.2f} ms/row "
          f"(IsoForest #2 alone: {ms_anom:.2f} ms; the rest is mostly the supervised model)")

    # Novel-attack check: retrain the classifier without one attack type.
    novel = {}
    if holdout:
        set_supervised(stand_in_supervised(df_train[df_train[C.LABEL_COLUMN] != holdout]))
        held = [r for r in rows if r[C.LABEL_COLUMN] == holdout]
        res = [score(r) for r in held]
        flagged = sum(o["risk"] >= C.THROTTLE_AT for o in res)
        unknown = sum(o["attack_type"] == "unknown" for o in res)
        novel = {"held_out": holdout, "n": len(held), "scored_40_plus": flagged, "unknown": unknown}
        print(f"novel check ({holdout} hidden from the classifier): {flagged}/{len(held)} scored 40+, {unknown} labelled unknown")
    set_supervised(None)
    return {"per_type": per_type, "attacks_flagged": caught, "false_quarantine": false_q,
            "ms_per_row": ms, "ms_anomaly": ms_anom, "novel": novel, "engine": engine, "source": source}


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    if "--report" in sys.argv:
        report()
    else:
        print("usage: python score.py --report")
