"""features.RowBuilder, load_dataset, and the make_dataset output.

Run from src/app/sentinel: pytest _py/tests/test_features.py
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from _py import contract as C
from _py import features as F
from _py import make_dataset as MD

T = 1794636000.0
BASE = {"researcher": 3.0, "emailer": 3.0, "coder": 4.0, "analyst": 3.0}


def ev(agent="agent-47", role="coder", ts=T, kind="tool_call", tool=None, resource=None, to_agent=None, ok=True, bytes_out=0):
    return {"agent_id": agent, "role": role, "ts": ts, "kind": kind, "tool": tool,
            "resource": resource, "to_agent": to_agent, "ok": ok, "bytes_out": bytes_out}


def burst() -> F.RowBuilder:
    """agent-47 works normally, touches a decoy, then messages 3 peers 6 times."""
    b = F.RowBuilder(baselines=BASE)
    b.add(ev(ts=T + 1, tool="repo.read", resource="repo:payments", bytes_out=100))
    b.add(ev(ts=T + 2, tool="ci.run", resource="ci:main", ok=False, bytes_out=50))
    b.add(ev(ts=T + 3, kind="resource", resource="decoy:aws-key"))
    for i, peer in enumerate(["agent-20", "agent-20", "agent-20", "agent-6", "agent-9", "agent-20"]):
        b.add(ev(ts=T + 4 + i, kind="message", to_agent=peer, bytes_out=300))
    return b


def test_burst_sets_decoy_and_message_rate():
    rows = burst().rows(T + 20)
    assert len(rows) == 1
    r = rows[0]
    assert r["touched_decoy"] == 1
    assert r["msgs_to_agents_per_min"] == 6.0
    assert r["distinct_peers"] == 3
    assert r["out_of_scope_resource"] == 1  # every decoy is out of scope
    assert r["actions_per_min"] == 9.0
    assert r["failed_calls_per_min"] == 1.0
    assert r["distinct_tools_used"] == 2
    assert r["bytes_out_per_min"] == 100 + 50 + 6 * 300
    assert r["distinct_tools_baseline"] == 4.0  # coder median
    assert r["sec_since_normal"] == 0.0  # api.py fills this from the previous score


def test_row_has_contract_columns_in_order():
    r = burst().rows(T + 20)[0]
    assert tuple(r) == C.FEATURE_COLUMNS[:13]
    assert "label" not in r
    assert r["agent_id"] == "agent-47" and r["role"] == "coder" and r["ts"] == T + 20


def test_window_slides_and_quiet_agents_drop_out():
    b = burst()
    b.add(ev(agent="agent-6", role="researcher", ts=T + 50, tool="web.search", resource="web:news"))
    later = {r["agent_id"]: r for r in b.rows(T + 3 + C.WINDOW_S + 0.5)}  # decoy event now outside the window
    assert later["agent-47"]["touched_decoy"] == 0
    assert later["agent-47"]["msgs_to_agents_per_min"] == 6.0
    assert later["agent-6"]["out_of_scope_resource"] == 0
    assert set(r["agent_id"] for r in b.rows(T + 200)) == set()  # nothing left in any window


def test_events_after_now_are_not_counted():
    b = burst()
    assert b.rows(T + 3.5)[0]["touched_decoy"] == 1
    assert b.rows(T + 3.5)[0]["msgs_to_agents_per_min"] == 0.0


def test_in_scope_resources_are_not_flagged():
    b = F.RowBuilder(baselines=BASE)
    b.add(ev(agent="agent-3", role="analyst", ts=T + 1, tool="db.query", resource="db:metrics"))
    b.add(ev(agent="agent-3", role="analyst", ts=T + 2, tool="docs.read", resource="docs:wiki"))
    r = b.rows(T + 5)[0]
    assert r["out_of_scope_resource"] == 0 and r["touched_decoy"] == 0


def test_role_baselines_use_the_median_on_clean_rows():
    df = pd.DataFrame({
        "role": ["coder"] * 5 + ["coder"],
        "distinct_tools_used": [3, 3, 4, 4, 40, 99],
        "label": ["clean"] * 5 + ["tool_misuse"],
    })
    assert F.role_baselines(df)["coder"] == 4.0  # mean would be 10.8


def test_load_dataset_drops_nans_keeps_impossible_rows(tmp_path):
    row = {c: 0 for c in C.FEATURE_COLUMNS}
    row.update(agent_id="agent-1", role="coder", ts=T, label="clean")
    good = dict(row, run_id="run-000", actions_per_min=10.0)
    nan = dict(row, run_id="run-000", bytes_out_per_min=float("nan"))
    junk = dict(row, run_id="run-001", actions_per_min=-12.0)
    p = tmp_path / "a.csv"
    pd.DataFrame([good, nan, junk]).to_csv(p, index=False)
    df = F.load_dataset(p)
    assert len(df) == 2
    assert list(df.columns) == list(C.FEATURE_COLUMNS) + [C.RUN_ID_COLUMN]
    assert (df["actions_per_min"] < 0).sum() == 1  # left for IsoForest #1


def test_load_dataset_rejects_missing_columns(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"agent_id": ["a"], "role": ["coder"]}).to_csv(p, index=False)
    with pytest.raises(ValueError):
        F.load_dataset(p)


# --- make_dataset ------------------------------------------------------------


@pytest.fixture(scope="module")
def dataset():
    return MD.make_dataset(seed=MD.SEED)


def test_dataset_shape_and_columns(dataset):
    df, _ = dataset
    assert list(df.columns) == list(C.FEATURE_COLUMNS) + [C.RUN_ID_COLUMN]
    assert 900 <= len(df) <= 1100
    assert set(df["label"]) <= set(C.TRAIN_LABELS) and "unknown" not in set(df["label"])


def test_dataset_label_mix(dataset):
    df, _ = dataset
    share = df["label"].value_counts(normalize=True)
    assert 0.55 <= share["clean"] <= 0.65
    attacks = share.drop("clean")
    assert attacks.idxmax() == "prompt_injection"
    assert len(attacks) == 4


def test_dataset_has_junk_rows_for_isoforest(dataset):
    df, _ = dataset
    nums = df[list(C.MODEL_INPUTS)].astype(float)
    assert nums.isna().any(axis=1).sum() >= 1
    assert ((nums < 0).any(axis=1)).sum() >= 1
    assert (nums["actions_per_min"] > 1000).sum() >= 1


def test_clean_rows_stay_clean_for_the_baseline(dataset):
    df, _ = dataset
    clean = df[df["label"] == "clean"].dropna(subset=list(C.MODEL_INPUTS))
    clean = clean[(clean["actions_per_min"] >= 0) & (clean["actions_per_min"] < 1000)]
    assert int(clean["touched_decoy"].sum()) == 0
    assert float(clean["sec_since_normal"].abs().sum()) == 0.0


def test_baseline_column_is_the_role_median(dataset):
    df, baselines = dataset
    for role, med in baselines.items():
        assert (df.loc[df["role"] == role, "distinct_tools_baseline"] == med).all()


def test_prompt_injection_spreads_in_some_runs(dataset):
    df, _ = dataset
    per_run = df[df["label"] == "prompt_injection"].groupby(C.RUN_ID_COLUMN)["agent_id"].nunique()
    assert (per_run >= 2).any()


def test_dataset_is_reproducible(dataset):
    df, _ = dataset
    again, _ = MD.make_dataset(seed=MD.SEED)
    pd.testing.assert_frame_equal(df, again)
    other, _ = MD.make_dataset(seed=MD.SEED + 1)
    assert not math.isclose(float(df["bytes_out_per_min"].sum()), float(other["bytes_out_per_min"].sum()))
    assert np.isfinite(df["ts"]).all()
