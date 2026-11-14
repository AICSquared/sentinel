"""model_supervised: split by run, IsoForest #1 on train only, frozen predict keys, report.

Run from src/app/sentinel: pytest _py/tests/test_supervised.py
"""

from __future__ import annotations

import time

import pandas as pd
import pytest

from _py import contract as C
from _py import features as F
from _py import make_dataset as MD
from _py import model_anomaly as MA
from _py import model_supervised as MS


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    df, _ = MD.make_dataset(seed=MD.SEED)
    p = tmp_path_factory.mktemp("data") / "actions.csv"
    df.to_csv(p, index=False)
    return F.load_dataset(p)


@pytest.fixture(scope="module")
def trained(data):
    df_train, df_test = MS.split(data)
    t0 = time.perf_counter()
    stats = MS.train(df_train)
    seconds = time.perf_counter() - t0
    filter_index = MA.last_filter_index
    return df_train, df_test, stats, seconds, filter_index


def test_no_run_id_in_both_train_and_test(trained):
    df_train, df_test, *_ = trained
    assert not set(df_train[C.RUN_ID_COLUMN]) & set(df_test[C.RUN_ID_COLUMN])
    assert len(df_test) > 0 and len(df_train) > len(df_test)


def test_every_attack_type_is_in_the_test_split(trained):
    _, df_test, *_ = trained
    assert set(df_test[C.LABEL_COLUMN]) >= set(C.TRAIN_LABELS)


def test_isoforest_1_saw_the_train_split_only(trained):
    df_train, df_test, stats, _, filter_index = trained
    assert filter_index.equals(df_train.index)
    assert not set(filter_index) & set(df_test.index)
    assert stats["dropped"] > 0  # the junk rows give it something to remove


def test_predict_returns_the_frozen_keys(trained):
    _, df_test, *_ = trained
    out = MS.predict(df_test.iloc[0].to_dict())
    assert set(out) == {"attack_type", "p_attack", "top_features"}
    assert out["attack_type"] in C.TRAIN_LABELS
    assert isinstance(out["p_attack"], float) and 0.0 <= out["p_attack"] <= 1.0
    assert 1 <= len(out["top_features"]) <= MS.TOP_K
    for name, contribution in out["top_features"]:
        assert name in C.MODEL_INPUTS and isinstance(contribution, float)


def test_predict_ignores_ids_label_and_extra_keys(trained):
    _, df_test, *_ = trained
    row = df_test.iloc[0].to_dict()
    bare = {c: row[c] for c in C.MODEL_INPUTS}
    noisy = dict(row, label="tool_misuse", agent_id="agent-999", extra="x")
    assert MS.predict(bare)["p_attack"] == MS.predict(noisy)["p_attack"]


def test_obvious_prompt_injection_scores_high_and_clean_scores_low(trained):
    clean = {"actions_per_min": 11.0, "distinct_tools_used": 3, "distinct_tools_baseline": 3.0,
             "failed_calls_per_min": 0.0, "touched_decoy": 0, "out_of_scope_resource": 0,
             "msgs_to_agents_per_min": 1.0, "distinct_peers": 1, "bytes_out_per_min": 2500.0,
             "sec_since_normal": 0.0}
    rogue = dict(clean, actions_per_min=24.0, touched_decoy=1, out_of_scope_resource=1,
                 msgs_to_agents_per_min=12.0, distinct_peers=6, bytes_out_per_min=9000.0)
    assert MS.predict(clean)["p_attack"] < 0.2
    hit = MS.predict(rogue)
    assert hit["p_attack"] > 0.8 and hit["attack_type"] == "prompt_injection"
    assert hit["top_features"][0][1] > 0


def test_report_has_precision_and_recall_for_every_type(trained):
    _, df_test, *_ = trained
    rep = MS.report(df_test)
    assert set(rep["per_type"]) == set(C.TRAIN_LABELS)
    for label, m in rep["per_type"].items():
        assert m["n"] > 0, label
        assert 0.0 <= m["recall"] <= 1.0
        assert {"precision", "recall", "n"} <= set(m)
    assert rep["attack_detection"]["recall"] > 0.8
    assert "prompt_injection" in MS.format_report(rep)


def test_trains_on_cpu_in_under_60_s(trained):
    *_, seconds, _ = trained
    assert seconds < 60


def test_save_load_round_trip(trained, tmp_path, monkeypatch):
    _, df_test, *_ = trained
    row = df_test.iloc[1].to_dict()
    before = MS.predict(row)
    monkeypatch.setattr(MS, "ARTIFACT_PATH", tmp_path / "supervised.joblib")
    MS.save()
    MS.reset()
    assert MS.predict(row) == before  # loaded lazily from the artifact


def test_missing_artifact_raises_so_score_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(MS, "ARTIFACT_PATH", tmp_path / "nope.joblib")
    saved = MS._state
    MS.reset()
    try:
        with pytest.raises(FileNotFoundError):
            MS.predict({c: 0.0 for c in C.MODEL_INPUTS})
    finally:
        MS._state = saved


def test_unknown_is_never_a_training_label(data):
    bad = data.head(50).copy()
    bad.loc[bad.index[0], C.LABEL_COLUMN] = "unknown"
    saved = MS._state
    try:
        with pytest.raises(ValueError):
            MS.train(bad)
    finally:
        MS._state = saved


def test_run_types_name_each_run_by_its_attack(data):
    rt = MS.run_types(data)
    assert set(rt) == set(C.TRAIN_LABELS)
    assert isinstance(rt, pd.Series) and rt.index.name == C.RUN_ID_COLUMN
