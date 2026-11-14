"""IsoForest #1 (train cleaner) and IsoForest #2 + PCA (novelty, scatter position).

Built on 200 seeded fake contract-A rows, so it runs before data/actions.csv exists.
Run from src/app/sentinel: pytest _py/tests/test_anomaly.py
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from _py import contract as C
from _py import model_anomaly as MA


@pytest.fixture(scope="module")
def split():
    df = MA.synthetic_dataset(n=200, seed=11, rows_per_run=5)
    return MA.split_by_run(df)


@pytest.fixture()
def fitted(split, tmp_path, monkeypatch):
    monkeypatch.setattr(MA, "ARTIFACT_PATH", tmp_path / "anomaly.joblib")
    MA.reset()
    df_train, _ = split
    MA.train(df_train)
    yield split
    MA.reset()


def _radius(xy: tuple[float, float]) -> float:
    return math.hypot(xy[0] - 0.5, xy[1] - 0.5)


def _attack_row() -> dict:
    return {
        "agent_id": "agent-47", "role": "coder", "ts": 1794636002.0,
        "actions_per_min": 24.0, "distinct_tools_used": 4, "distinct_tools_baseline": 4.0,
        "failed_calls_per_min": 0.5, "touched_decoy": 1, "out_of_scope_resource": 1,
        "msgs_to_agents_per_min": 12.0, "distinct_peers": 6, "bytes_out_per_min": 2500.0,
        "sec_since_normal": 20.0,
    }


def test_split_is_by_run(split):
    df_train, df_test = split
    assert set(df_train[C.RUN_ID_COLUMN]).isdisjoint(df_test[C.RUN_ID_COLUMN])


def test_filter_train_never_sees_test_rows(split):
    df_train, df_test = split
    keep = MA.filter_train(df_train, df_train[C.LABEL_COLUMN])
    assert len(keep) == len(df_train) and keep.dtype == bool
    seen = MA.last_filter_index
    assert seen is not None
    assert seen.equals(df_train.index)
    assert set(seen).isdisjoint(df_test.index)


def test_filter_train_drops_a_few_rows_not_whole_attack_classes(split, caplog):
    df_train, _ = split
    y = df_train[C.LABEL_COLUMN].to_numpy()
    with caplog.at_level("INFO", logger="sentinel.anomaly"):
        keep = MA.filter_train(df_train, y)
    assert 0 < (~keep).sum() < 0.1 * len(df_train)
    assert "dropped" in caplog.text
    for label in set(y) - {"clean"}:
        assert keep[y == label].any(), f"every {label} row was dropped"


def test_filter_train_without_labels_accepts_arrays(split):
    df_train, _ = split
    X = df_train.loc[:, list(C.MODEL_INPUTS)].to_numpy()
    keep = MA.filter_train(X)
    assert keep.shape == (len(X),)


def test_baseline_fit_on_clean_rows_only(fitted):
    df_train, _ = fitted
    s = MA._ready()
    keep = MA.filter_train(df_train, df_train[C.LABEL_COLUMN])
    assert s["n_clean"] == int((keep & (df_train[C.LABEL_COLUMN] == "clean").to_numpy()).sum())


def test_clean_row_projects_inside_cluster_attack_outside(fitted):
    _, df_test = fitted
    clean = df_test[df_test[C.LABEL_COLUMN] == "clean"].to_dict("records")
    clean_r = [_radius(MA.project(r)) for r in clean]
    attack_r = _radius(MA.project(_attack_row()))
    assert np.median(clean_r) < 0.15
    assert attack_r > 0.3
    assert attack_r > max(np.percentile(clean_r, 90), 0.2)


def test_positions_are_clipped_to_unit_square(fitted):
    wild = dict(_attack_row(), bytes_out_per_min=9e9, actions_per_min=1e5, distinct_peers=500)
    x, y = MA.project(wild)
    assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def test_anomaly_low_for_clean_high_for_attack(fitted):
    _, df_test = fitted
    clean = df_test[df_test[C.LABEL_COLUMN] == "clean"]
    a_clean = MA.anomaly_many(clean)
    assert np.median(a_clean) < 0.2
    a_attack = MA.anomaly(_attack_row())
    assert 0.0 <= a_attack <= 1.0
    assert a_attack > 0.5 > np.median(a_clean)


def test_anomaly_accepts_dict_and_one_row_frame(fitted):
    row = _attack_row()
    assert MA.anomaly(row) == pytest.approx(MA.anomaly(pd.DataFrame([row])))


def test_save_and_reload(fitted):
    row = _attack_row()
    before = (MA.anomaly(row), MA.project(row))
    path = MA.save()
    assert path.exists()
    MA.reset()
    assert (MA.anomaly(row), MA.project(row)) == before


def test_missing_artifact_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(MA, "ARTIFACT_PATH", tmp_path / "nope.joblib")
    MA.reset()
    with pytest.raises(FileNotFoundError):
        MA.anomaly(_attack_row())
