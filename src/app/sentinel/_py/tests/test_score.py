"""score(): contract B shape, tiers, blend, reasons, fallback, speed.

The supervised model is a stand-in (trained the same way as model_supervised)
until Noah's model is on main. Run from src/app/sentinel: pytest _py/tests/test_score.py
"""

from __future__ import annotations

import re
import time

import numpy as np
import pytest

from _py import contract as C
from _py import model_anomaly as MA
from _py import score as S

CONTRACT_B_KEYS = {
    "agent_id", "ts", "risk", "attack_type", "reason",
    "related_agents", "recommended_action", "components",
}


def clean_row(**kw) -> dict:
    row = {
        "agent_id": "agent-5", "role": "researcher", "ts": 1794636000.0,
        "actions_per_min": 12.0, "distinct_tools_used": 3, "distinct_tools_baseline": 3.0,
        "failed_calls_per_min": 0.2, "touched_decoy": 0, "out_of_scope_resource": 0,
        "msgs_to_agents_per_min": 1.0, "distinct_peers": 1, "bytes_out_per_min": 1800.0,
        "sec_since_normal": 0.0,
    }
    row.update(kw)
    return row


def decoy_burst_row(**kw) -> dict:
    attack = dict(
        agent_id="agent-47", role="coder", distinct_tools_used=4, distinct_tools_baseline=4.0,
        actions_per_min=22.0, touched_decoy=1, msgs_to_agents_per_min=10.0, distinct_peers=6,
        sec_since_normal=12.0,
    )
    attack.update(kw)
    return clean_row(**attack)


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    path = tmp_path_factory.mktemp("artifacts") / "anomaly.joblib"
    old = MA.ARTIFACT_PATH
    MA.ARTIFACT_PATH = path
    df = MA.synthetic_dataset(n=600, seed=3)
    df_train, df_test = MA.split_by_run(df)
    MA.train(df_train)
    MA.save()
    S.set_supervised(S.stand_in_supervised(df_train))
    yield df_test
    S.set_supervised(None)
    MA.reset()
    MA.ARTIFACT_PATH = old


class StubGraph:
    def __init__(self):
        self.calls = []

    def related(self, agent_id, risks):
        self.calls.append((agent_id, dict(risks)))
        return [{"agent_id": "agent-20", "messages": 37, "verdict": "likely_infected"}]


def test_output_has_exactly_contract_b_keys(models):
    out = S.score(clean_row(), StubGraph())
    assert set(out) == CONTRACT_B_KEYS
    assert set(out["components"]) == {"supervised", "anomaly", "fallback"}
    assert isinstance(out["risk"], int) and 0 <= out["risk"] <= 100
    assert out["attack_type"] in C.ATTACK_TYPES
    assert out["recommended_action"] in C.ACTIONS
    assert out["components"]["fallback"] is False


@pytest.mark.parametrize("risk,action", [
    (0, "monitor"), (39, "monitor"), (40, "throttle"), (74, "throttle"),
    (75, "recommend_quarantine"), (94, "recommend_quarantine"), (95, "recommend_terminate"),
    (100, "recommend_terminate"),
])
def test_tiers(models, monkeypatch, risk, action):
    monkeypatch.setattr(S, "blend", lambda p, a, pr=0.0: risk)
    assert S.score(decoy_burst_row())["recommended_action"] == action


def test_clean_row_below_40_and_decoy_burst_75_plus(models):
    clean = S.score(clean_row())
    attack = S.score(decoy_burst_row())
    assert clean["risk"] < 40 and clean["attack_type"] == "clean"
    assert attack["risk"] >= 75
    assert attack["attack_type"] == "prompt_injection"


def test_clean_never_sent_with_risk_40_plus(models):
    for row in models.to_dict("records"):
        out = S.score(row)
        assert not (out["attack_type"] == "clean" and out["risk"] >= 40)


def test_blend_formula():
    assert S.blend(0.0, 0.0) == 0
    assert S.blend(1.0, 1.0) == 100
    assert S.blend(0.9, 0.5) == 77  # max(0.65*90 + 0.35*50, 0.85*90, 0.8*50) = 76.5 rounds up
    assert S.blend(1.0, 0.2) == 85  # a confident classifier alone reaches quarantine
    assert S.blend(0.0, 1.0) == 80  # anomaly alone tops out at quarantine, never terminate


def test_unknown_when_anomaly_high_but_classifier_says_clean(models, monkeypatch):
    monkeypatch.setattr(S, "_supervised", lambda row: {"attack_type": "clean", "p_attack": 0.03, "top_features": []})
    weird = clean_row(actions_per_min=90.0, distinct_tools_used=14, failed_calls_per_min=9.0)
    out = S.score(weird)
    assert out["risk"] >= 40
    assert out["attack_type"] == "unknown"
    assert out["components"]["anomaly"] > out["components"]["supervised"]


SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")


def test_reason_reads_like_plain_english(models):
    out = S.score(decoy_burst_row())
    text = out["reason"]
    assert not SNAKE.search(text), text
    assert text[0].isupper() and text.endswith(".")
    assert "decoy" in text
    assert re.search(r"\d", text)
    assert "(normal: " in text


def test_reason_units_for_bytes(models):
    out = S.score(clean_row(bytes_out_per_min=240_000.0, out_of_scope_resource=1, sec_since_normal=30.0))
    assert "KB" in out["reason"] and not SNAKE.search(out["reason"])


def test_clean_reason(models):
    text = S.score(clean_row())["reason"]
    assert text.startswith("Normal activity") and not SNAKE.search(text)


def test_reason_grammar(models):
    text = S.score(clean_row(role="emailer", distinct_tools_used=11, distinct_tools_baseline=2.0,
                             failed_calls_per_min=5.0))["reason"]
    assert "an emailer" in text and "a emailer" not in text
    decoy = S.score(decoy_burst_row(out_of_scope_resource=1))["reason"]
    assert "outside the" not in decoy  # a decoy implies out of scope; don't say it twice


def test_graph_gets_current_risks(models):
    g = StubGraph()
    S.score(clean_row(agent_id="agent-20"), g)
    out = S.score(decoy_burst_row(), g)
    assert out["related_agents"][0]["agent_id"] == "agent-20"
    _, risks = g.calls[-1]
    assert risks["agent-47"] == out["risk"] and "agent-20" in risks


def test_scoring_one_row_under_20ms(models):
    row = decoy_burst_row()
    S.score(row)
    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        S.score(row)
        times.append((time.perf_counter() - t0) * 1000)
    assert np.median(times) < 20, f"median {np.median(times):.1f} ms"


# --- fallback --------------------------------------------------------------


def test_fallback_score_rule():
    assert S.fallback_score(clean_row()) < 40
    assert S.fallback_score(decoy_burst_row()) >= 75
    assert S.fallback_score(clean_row(touched_decoy=1)) == 40
    assert S.fallback_score(clean_row(msgs_to_agents_per_min=15.0, distinct_peers=5)) == 40


def test_model_files_deleted_still_returns_risk(models, monkeypatch):
    missing = MA.ARTIFACT_PATH.parent / "deleted.joblib"
    monkeypatch.setattr(MA, "ARTIFACT_PATH", missing)
    S.set_supervised(None)  # and no model_supervised module either
    S.reload_models()
    try:
        out = S.score(decoy_burst_row())
        assert set(out) == CONTRACT_B_KEYS
        assert out["components"]["fallback"] is True
        assert isinstance(out["risk"], int) and out["risk"] >= 75
        assert out["recommended_action"] == C.action_for(out["risk"])
        assert out["attack_type"] == "prompt_injection"
        assert not SNAKE.search(out["reason"])
        clean = S.score(clean_row())
        assert clean["risk"] < 40 and clean["attack_type"] == "clean"
    finally:
        monkeypatch.undo()
        df_train, _ = MA.split_by_run(MA.synthetic_dataset(n=600, seed=3))
        S.set_supervised(S.stand_in_supervised(df_train))
        S.reload_models()


def test_model_error_mid_score_falls_back(models, monkeypatch):
    def boom(row):
        raise RuntimeError("bad model")

    monkeypatch.setattr(S, "_supervised", boom)
    out = S.score(decoy_burst_row())
    assert out["components"]["fallback"] is True and out["risk"] >= 75


# --- Prompt Guard (prompt_risk) --------------------------------------------


def old_blend(p_attack: float, anomaly: float) -> int:
    """The formula before Prompt Guard, written out independently."""
    s, a = 100.0 * p_attack, 100.0 * anomaly
    x = max(0.65 * s + 0.35 * a, 0.85 * s, 0.8 * a)
    return int(max(0, min(100, np.floor(x + 0.5))))


def clean_supervised(row):
    return {"attack_type": "clean", "p_attack": 0.02, "top_features": []}


def test_blend_with_prompt():
    assert S.blend(0.0, 0.0, 0.97) == 87  # 0.9*97 = 87.3: quarantine, not terminate
    assert S.blend(0.0, 0.0, 1.0) == 90  # Prompt Guard alone tops out at 90
    assert S.blend(0.9, 0.5, 0.2) == 77  # behaviour still wins when it is higher
    assert S.blend(1.0, 1.0, 1.0) == 100
    for p in np.linspace(0, 1, 21):
        for a in np.linspace(0, 1, 21):
            assert S.blend(p, a) == S.blend(p, a, 0.0) == old_blend(p, a)


def test_rows_without_prompt_risk_score_exactly_as_before(models):
    predict = S._models()
    for row in models.to_dict("records")[:80] + [clean_row(), decoy_burst_row()]:
        row.pop("prompt_risk", None)
        out = S.score(row)
        assert set(out["components"]) == {"supervised", "anomaly", "fallback"}
        assert out["risk"] == old_blend(float(predict(row)["p_attack"]), MA.anomaly(row))
        assert "prompt injection (" not in out["reason"]
        # None or NaN means absent too: the same output, key for key.
        assert S.score({**row, "prompt_risk": None}) == out
        assert S.score({**row, "prompt_risk": float("nan")}) == out


def test_components_prompt_only_when_present(models):
    assert "prompt" not in S.score(clean_row())["components"]
    out = S.score(clean_row(prompt_risk=0.42))
    assert out["components"]["prompt"] == 42
    assert isinstance(out["components"]["prompt"], int)
    assert set(out["components"]) == {"supervised", "anomaly", "fallback", "prompt"}
    assert S.score(clean_row(prompt_risk=0.0))["components"]["prompt"] == 0


def test_prompt_guard_alone_quarantines_but_never_terminates(models, monkeypatch):
    monkeypatch.setattr(S, "_supervised", clean_supervised)
    out = S.score(clean_row(prompt_risk=0.97))
    assert 75 <= out["risk"] <= 90
    assert out["recommended_action"] == "recommend_quarantine"
    assert out["attack_type"] == "prompt_injection"
    assert out["components"]["prompt"] == 97
    top = S.score(clean_row(prompt_risk=1.0))
    assert top["risk"] < 95 and top["recommended_action"] != "recommend_terminate"


@pytest.mark.parametrize("prompt_risk,action,attack_type", [
    (0.10, "monitor", "clean"),
    (0.40, "monitor", "clean"),  # 36
    (0.50, "throttle", "prompt_injection"),  # 45
    (0.80, "throttle", "prompt_injection"),  # 72
    (0.85, "recommend_quarantine", "prompt_injection"),  # 77 (76.5 rounds up)
    (1.00, "recommend_quarantine", "prompt_injection"),  # 90
])
def test_prompt_tiers(models, monkeypatch, prompt_risk, action, attack_type):
    monkeypatch.setattr(S, "_supervised", clean_supervised)
    out = S.score(clean_row(prompt_risk=prompt_risk))
    assert out["recommended_action"] == action
    assert out["attack_type"] == attack_type


def test_known_attack_label_kept_when_behaviour_drives(models):
    out = S.score(decoy_burst_row(prompt_risk=0.6))
    assert out["risk"] >= 75
    assert out["attack_type"] == "prompt_injection"  # the classifier's own label
    assert out["reason"].startswith("Touched a decoy")  # behaviour leads, message second
    assert "reads like a prompt injection (60% confidence)" in out["reason"]


def test_confident_classifier_label_not_overridden(models, monkeypatch):
    monkeypatch.setattr(S, "_supervised",
                        lambda row: {"attack_type": "data_exfiltration", "p_attack": 0.7, "top_features": []})
    out = S.score(clean_row(prompt_risk=0.95))
    assert out["risk"] >= 75
    assert out["attack_type"] == "data_exfiltration"


def test_prompt_reason_plain_english(models, monkeypatch):
    monkeypatch.setattr(S, "_supervised", clean_supervised)
    text = S.score(clean_row(prompt_risk=0.97))["reason"]
    assert text.startswith("Sent a message that reads like a prompt injection (97% confidence)"), text
    assert text.endswith(".") and not SNAKE.search(text)
    low = S.score(clean_row(prompt_risk=0.3))["reason"]
    assert "prompt injection" not in low and not SNAKE.search(low)


def test_fallback_prompt_flag():
    assert S.fallback_score(clean_row(prompt_risk=0.8)) == 40
    assert S.fallback_score(clean_row(prompt_risk=0.79)) < 40
    assert S.fallback_score(clean_row(prompt_risk=0.97, touched_decoy=1)) == 80
    assert S.fallback_score(clean_row()) == S.fallback_score(clean_row(prompt_risk=None))


def test_fallback_path_with_prompt_risk(models, monkeypatch):
    missing = MA.ARTIFACT_PATH.parent / "deleted.joblib"
    monkeypatch.setattr(MA, "ARTIFACT_PATH", missing)
    S.set_supervised(None)
    S.reload_models()
    try:
        out = S.score(clean_row(prompt_risk=0.97))
        assert out["components"]["fallback"] is True
        assert out["components"]["prompt"] == 97
        assert out["risk"] == 40 and out["recommended_action"] == "throttle"
        assert out["attack_type"] == "prompt_injection"
        assert out["reason"].startswith("Sent a message that reads like a prompt injection (97% confidence)")
        assert not SNAKE.search(out["reason"])
        plain = S.score(clean_row())
        assert "prompt" not in plain["components"] and plain["risk"] < 40
    finally:
        monkeypatch.undo()
        df_train, _ = MA.split_by_run(MA.synthetic_dataset(n=600, seed=3))
        S.set_supervised(S.stand_in_supervised(df_train))
        S.reload_models()


# --- graph.py (related agents + edges) -------------------------------------

from _py.graph import Graph  # noqa: E402

T0 = 1794636000.0


def test_related_verdicts_and_order():
    g = Graph()
    for i in range(37):
        g.add_message("agent-47", "agent-20", T0 + i)
    g.add_message("agent-47", "agent-6", T0 + 5)
    for i in range(12):
        g.add_message("agent-47", "agent-31", T0 + i)
    risks = {"agent-20": 74, "agent-6": 90, "agent-31": 39}
    rel = g.related("agent-47", risks)
    assert rel == [
        {"agent_id": "agent-20", "messages": 37, "verdict": "likely_infected"},
        {"agent_id": "agent-31", "messages": 12, "verdict": "likely_clean"},  # risk 39 < 40
        {"agent_id": "agent-6", "messages": 1, "verdict": "likely_clean"},  # 1 message < 10
    ]


def test_infected_thresholds_are_inclusive():
    g = Graph()
    for i in range(10):
        g.add_message("a", "b", T0 + i)
    assert g.related("a", {"b": 40})[0]["verdict"] == "likely_infected"
    assert g.related("a", {"b": 39})[0]["verdict"] == "likely_clean"
    g9 = Graph()
    for i in range(9):
        g9.add_message("a", "b", T0 + i)
    assert g9.related("a", {"b": 100})[0]["verdict"] == "likely_clean"


def test_related_is_outbound_only_and_unknown_partner_is_clean():
    g = Graph()
    for i in range(15):
        g.add_message("agent-20", "agent-47", T0 + i)
    assert g.related("agent-47", {}) == []
    assert g.related("agent-20", {})[0]["verdict"] == "likely_clean"


def test_five_minute_window_uses_newest_message_time():
    g = Graph()
    for i in range(20):
        g.add_message("a", "b", T0 + i)  # old burst
    g.add_message("c", "d", T0 + 400)  # now = T0+400, window starts at T0+100
    assert g.related("a", {"b": 99}) == []
    assert g.edges() == [{"from": "c", "to": "d", "messages": 1}]


def test_edges_counts_and_shorter_window():
    g = Graph()
    for i in range(5):
        g.add_message("a", "b", T0 + i)
    g.add_message("b", "a", T0 + 1)
    g.add_message("a", "c", T0 + 250)
    g.add_message("a", "a", T0 + 250)  # self-message ignored
    g.add_message("a", None, T0 + 250)  # no recipient ignored
    assert g.edges() == [
        {"from": "a", "to": "b", "messages": 5},
        {"from": "a", "to": "c", "messages": 1},
        {"from": "b", "to": "a", "messages": 1},
    ]
    assert g.edges(window_s=60) == [{"from": "a", "to": "c", "messages": 1}]


def test_demo_story_end_to_end(models):
    """agent-47 is hijacked, floods agent-20, which turns rogue; agent-6 got one message."""
    g = Graph()
    for i in range(37):
        g.add_message("agent-47", "agent-20", T0 + i)
    g.add_message("agent-47", "agent-6", T0 + 3)
    S.score(clean_row(agent_id="agent-6"), g)
    S.score(decoy_burst_row(agent_id="agent-20", touched_decoy=0, distinct_peers=5), g)
    out = S.score(decoy_burst_row(), g)
    assert out["recommended_action"] in ("recommend_quarantine", "recommend_terminate")
    assert out["related_agents"][0] == {"agent_id": "agent-20", "messages": 37, "verdict": "likely_infected"}
    assert out["related_agents"][1] == {"agent_id": "agent-6", "messages": 1, "verdict": "likely_clean"}
