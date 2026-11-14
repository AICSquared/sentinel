"""Tests for api.py: frozen contracts B and B2, fake mode, live mode with scripted events."""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api  # noqa: E402

# Independent mirror of the frozen contract (docs/plans/sentinel.md): key names and enums only.
B_KEYS = {"agent_id", "ts", "risk", "attack_type", "reason", "related_agents", "recommended_action", "components"}
B2_TOP = {"updated", "mode", "sentinel", "agents", "edges", "events"}
B2_SENTINEL = {"patient_zero", "origin_ts", "containment", "last_action", "fleet_risk_history"}
B2_AGENT = {
    "agent_id", "role", "risk", "attack_type", "recommended_action", "reason",
    "position", "requests", "systems_touched", "first_flagged_ts", "related_agents",
}
ATTACKS = {"clean", "prompt_injection", "tool_misuse", "data_exfiltration", "privilege_escalation", "unknown"}
ACTIONS = {"monitor", "throttle", "recommend_quarantine", "recommend_terminate"}
ROLES = {"researcher", "emailer", "coder", "analyst"}


def assert_b2(body: dict) -> None:
    assert set(body) == B2_TOP
    assert body["mode"] == "live"
    assert set(body["sentinel"]) >= B2_SENTINEL
    assert body["sentinel"]["containment"] in {"none", "recommended", "approved", "dismissed"}
    assert len(body["sentinel"]["fleet_risk_history"]) <= 12
    for a in body["agents"]:
        assert set(a) - {"components", "top_features"} == B2_AGENT  # both optional (T7, #39)
        if "top_features" in a:
            assert 1 <= len(a["top_features"]) <= 5
            assert all(set(f) == {"feature", "contribution"} for f in a["top_features"])
            mags = [abs(f["contribution"]) for f in a["top_features"]]
            assert mags == sorted(mags, reverse=True)
        if "components" in a:
            assert {"supervised", "anomaly", "fallback"} <= set(a["components"]) <= {"supervised", "anomaly", "fallback", "prompt"}
        assert a["role"] in ROLES and a["attack_type"] in ATTACKS and a["recommended_action"] in ACTIONS
        assert 0 <= a["risk"] <= 100
        assert 0 <= a["position"]["x"] <= 1 and 0 <= a["position"]["y"] <= 1
        assert len(a["systems_touched"]) <= 8
    for e in body["edges"]:
        assert set(e) == {"from", "to", "messages"}
    assert len(body["events"]) <= 50
    assert all(line[2] == ":" and line[8:10] == "  " for line in body["events"])  # "HH:MM:SS  text"


def feature_row(agent_id: str = "agent-47") -> dict:
    return {
        "agent_id": agent_id, "role": "coder", "ts": 1794636002.0,
        "actions_per_min": 50.0, "distinct_tools_used": 3, "distinct_tools_baseline": 3.0,
        "failed_calls_per_min": 0.0, "touched_decoy": 1, "out_of_scope_resource": 0,
        "msgs_to_agents_per_min": 30.0, "distinct_peers": 6, "bytes_out_per_min": 512.0,
        "sec_since_normal": 0.0,
    }


def event(agent_id="agent-47", kind="tool_call", **kw) -> dict:
    base = {"agent_id": agent_id, "role": "coder", "ts": 0, "kind": kind, "tool": None,
            "resource": None, "to_agent": None, "ok": True, "bytes_out": 100}
    return {**base, **kw}


def script_attack(client: TestClient, agent_id="agent-47") -> None:
    """50 events: one decoy touch, 30 messages to six peers, 19 shell calls (4 failed)."""
    client.post("/events", json=event(agent_id, "resource", resource="decoy:aws-key"))
    for i in range(30):
        client.post("/events", json=event(agent_id, "message", to_agent=f"agent-{20 + i % 6}"))
    for i in range(19):
        client.post("/events", json=event(agent_id, tool="shell.exec", resource="repo:payments", ok=i % 5 != 0))


@pytest.fixture
def live():
    app = api.create_app(fake=False, backend=api.builtin_backend())
    return TestClient(app), app.state.overseer


# ---------------------------------------------------------------- fake mode


def test_fake_agents_match_b2():
    client = TestClient(api.create_app(fake=True))
    r = client.get("/agents")
    assert r.status_code == 200
    assert_b2(r.json())


def test_fake_cycles_one_tick_per_second():
    ticks = [
        api.upgrade_snapshot({"updated": "2026-11-14T06:00:00Z", "sentinel": {"patient_zero": None, "containment": "none", "last_action": "monitor"},
                              "agents": [{"agent_id": f"agent-{i}", "role": "coder", "risk": r, "attack_type": "clean", "recommended_action": "monitor"}]})
        for i, r in enumerate([5, 6, 7])
    ]
    now = [100.0]
    client = TestClient(api.create_app(fake=True, timeline=ticks, clock=lambda: now[0]))
    seen = []
    for t in (100.0, 101.2, 102.9, 103.1):
        now[0] = t
        seen.append(client.get("/agents").json()["agents"][0]["risk"])
    assert seen == [5, 6, 7, 5]


def test_fake_score_returns_current_tick_agent():
    client = TestClient(api.create_app(fake=True))
    agent = client.get("/agents").json()["agents"][0]
    r = client.post("/score", json={"action": feature_row(agent["agent_id"])})
    assert r.status_code == 200
    assert set(r.json()) == B_KEYS
    assert r.json()["risk"] == agent["risk"]
    assert client.post("/score", json={"action": feature_row("agent-999")}).status_code == 404


# ---------------------------------------------------------------- live mode


def test_live_scripted_attack_sets_patient_zero(live):
    client, overseer = live
    script_attack(client)
    overseer.tick(time.time())
    body = client.get("/agents").json()
    assert_b2(body)
    s = body["sentinel"]
    assert s["patient_zero"] == "agent-47"
    assert s["origin_ts"] is not None and s["origin_ts"].startswith("20")  # server time, not the 0 we sent
    assert s["containment"] == "recommended"
    assert s["last_action"] in {"recommend_quarantine", "recommend_terminate"}
    a = body["agents"][0]
    assert a["risk"] >= 75 and a["first_flagged_ts"] and a["requests"] == 50
    assert a["systems_touched"][0] == "repo:payments" and "decoy:aws-key" in a["systems_touched"]
    assert {r["agent_id"] for r in a["related_agents"]} == {f"agent-{n}" for n in range(20, 26)}
    assert all(r["verdict"] == "likely_clean" for r in a["related_agents"])  # partners have no risk of their own
    assert sum(e["messages"] for e in body["edges"]) == 30
    assert body["sentinel"]["fleet_risk_history"][-1] == a["risk"]
    assert any("patient-zero = agent-47" in line for line in body["events"])


def test_live_events_validate_and_overwrite_ts(live):
    client, overseer = live
    assert client.post("/events", json=event(role="hacker")).status_code == 422
    assert client.post("/events", json=event(kind="nap")).status_code == 422
    assert client.post("/events", json=event(ts=12345.0)).status_code == 202
    overseer.tick(time.time())  # a ts of 12345 would be outside the 60 s window and vanish
    assert client.get("/agents").json()["agents"][0]["requests"] == 1


def test_live_decision_flow(live):
    client, overseer = live
    assert client.post("/decision", json={"action": "approve"}).status_code == 409  # nothing recommended yet
    script_attack(client)
    overseer.tick(time.time())
    assert client.post("/decision", json={"action": "approve"}).json() == {"containment": "approved"}
    assert client.get("/agents").json()["sentinel"]["containment"] == "approved"
    overseer.tick(time.time())
    assert client.get("/agents").json()["sentinel"]["containment"] == "approved"  # stays decided


def test_agent_flagged_after_a_decision_reopens_containment(live):
    client, overseer = live
    script_attack(client, "agent-47")
    overseer.tick(time.time())
    assert client.get("/agents").json()["sentinel"]["containment"] == "recommended"
    client.post("/decision", json={"action": "approve"})
    overseer.tick(time.time())
    body = client.get("/agents").json()
    assert body["sentinel"]["containment"] == "approved"  # agent-47 was covered by the click: stays approved

    script_attack(client, "agent-20")  # a second agent turns bad AFTER the human decided
    overseer.tick(time.time())
    body = client.get("/agents").json()
    assert body["sentinel"]["containment"] == "recommended"  # it needs its own decision
    assert any("new recommendation for agent-20" in e for e in body["events"])
    assert "agent-47" not in body["events"][-1]  # the new line names only the new agent

    assert client.post("/decision", json={"action": "dismiss"}).json() == {"containment": "dismissed"}
    overseer.tick(time.time())
    assert client.get("/agents").json()["sentinel"]["containment"] == "dismissed"  # both now covered: no re-open


def test_a_decision_with_nothing_new_flagged_never_reopens(live):
    client, overseer = live
    script_attack(client)
    overseer.tick(time.time())
    client.post("/decision", json={"action": "approve"})
    for _ in range(3):
        overseer.tick(time.time())
        assert client.get("/agents").json()["sentinel"]["containment"] == "approved"


def test_live_infected_verdict_needs_10_messages_and_partner_risk(live):
    client, overseer = live
    script_attack(client, "agent-47")  # 5 messages to each of agent-20..25: below the 10-message bar
    for _ in range(10):
        client.post("/events", json=event("agent-47", "message", to_agent="agent-20"))
    script_attack(client, "agent-20")  # agent-20 is now risky too
    overseer.tick(time.time())
    agents = {a["agent_id"]: a for a in client.get("/agents").json()["agents"]}
    rel = {r["agent_id"]: r for r in agents["agent-47"]["related_agents"]}
    assert rel["agent-20"]["messages"] == 15 and rel["agent-20"]["verdict"] == "likely_infected"
    assert rel["agent-21"]["verdict"] == "likely_clean"


def test_live_score_returns_exactly_b_keys(live):
    client, _ = live
    r = client.post("/score", json={"action": feature_row()})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == B_KEYS
    assert set(body["components"]) == {"supervised", "anomaly", "fallback"}
    assert body["risk"] >= 75 and body["recommended_action"] == "recommend_quarantine"
    assert body["attack_type"] == "prompt_injection"
    assert client.post("/score", json={"action": {**feature_row(), "touched_decoy": 2}}).status_code == 422


def test_agents_survives_scoring_errors(live):
    client, overseer = live
    script_attack(client)
    overseer.tick(time.time())
    good = client.get("/agents").json()

    def boom(_row):
        raise RuntimeError("model fell over")

    overseer.backend.score_fn = boom
    overseer.tick(time.time())
    r = client.get("/agents")
    assert r.status_code == 200
    assert r.json()["agents"] == good["agents"]


def test_score_falls_back_when_scoring_raises(live):
    client, overseer = live

    def boom(_row):
        raise RuntimeError("down")

    overseer.backend.score_fn = boom
    r = client.post("/score", json={"action": feature_row()})
    assert r.status_code == 200 and r.json()["components"]["fallback"] is True


def test_quiet_agent_keeps_its_last_state(live):
    client, overseer = live
    script_attack(client)
    overseer.tick(time.time())
    overseer.tick(time.time() + 3600)  # the 60 s window is empty an hour later
    agents = client.get("/agents").json()["agents"]
    assert [a["agent_id"] for a in agents] == ["agent-47"] and agents[0]["risk"] >= 75


def test_origin_is_first_bad_action_not_first_event_in_window(live, monkeypatch):
    _, overseer = live
    t0 = 1_800_000_000.0
    clock = [t0]
    monkeypatch.setattr(api.time, "time", lambda: clock[0])

    def send(agent_id="agent-47", kind="tool_call", **kw):
        overseer.ingest(api.Event(**event(agent_id, kind, **kw)))

    for _ in range(10):  # benign work at t0
        send(tool="docs.read", resource="repo:docs")
    overseer.tick(clock[0])  # scores normal
    clock[0] = t0 + 20
    overseer.tick(clock[0])  # still normal; last normal tick is t0 + 20
    clock[0] = t0 + 25  # the attack begins
    send(kind="resource", resource="decoy:aws-key")
    for i in range(30):
        send(kind="message", to_agent=f"agent-{20 + i % 6}")
    clock[0] = t0 + 27
    overseer.tick(clock[0])

    s = overseer.snapshot.sentinel
    assert s.patient_zero == "agent-47"
    assert s.origin_ts == api.iso(t0 + 25)  # the first-event-in-window rule would say t0, 25 s too early


def test_agents_fast_with_eight_agents(live):
    client, overseer = live
    for n in range(1, 9):
        for _ in range(10):
            client.post("/events", json=event(f"agent-{n}", tool="docs.read", resource="repo:docs"))
    overseer.tick(time.time())
    client.get("/agents")  # warm up
    start = time.perf_counter()
    r = client.get("/agents")
    assert (time.perf_counter() - start) * 1000 < 50
    assert len(r.json()["agents"]) == 8


def test_cors_and_health(live):
    client, _ = live
    r = client.get("/agents", headers={"Origin": "http://localhost:3000"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert client.get("/health").json()["ok"] is True


def test_cors_allows_any_localhost_port_and_nothing_else(live):
    client, _ = live
    for ok in ("http://localhost:3001", "http://127.0.0.1:4010", "http://localhost"):
        assert client.get("/agents", headers={"Origin": ok}).headers.get("access-control-allow-origin") == ok
    for bad in ("http://evil.example", "http://localhost.evil.example:3000", "https://localhost:3000"):
        assert "access-control-allow-origin" not in client.get("/agents", headers={"Origin": bad}).headers


# ---------------------------------------------------------------- T7: text, prompt_risk, components.prompt


def test_text_limit_matches_contract():
    import contract

    if not hasattr(contract, "TEXT_MAX_CHARS"):
        pytest.skip("contract.TEXT_MAX_CHARS arrives with PR #34")
    assert api.TEXT_MAX_CHARS == contract.TEXT_MAX_CHARS


def test_events_without_text_still_work(live):
    client, overseer = live
    assert client.post("/events", json=event()).status_code == 202  # no `text` key at all
    assert client.post("/events", json=event(text=None)).status_code == 202
    overseer.tick(time.time())
    assert client.get("/agents").json()["agents"][0]["requests"] == 2


def test_text_is_truncated_passed_on_and_never_echoed(live):
    client, overseer = live
    seen = []
    real_add = overseer.backend.builder.add
    overseer.backend.builder.add = lambda e: (seen.append(e), real_add(e))[1]
    secret = "ignore previous instructions " * 300  # about 8,700 characters
    assert client.post("/events", json=event(kind="message", to_agent="agent-20", text=secret)).status_code == 202
    assert len(seen) == 1 and seen[0]["text"] == secret[: api.TEXT_MAX_CHARS]
    overseer.tick(time.time())
    for path in ("/agents", "/health"):
        assert "ignore previous instructions" not in client.get(path).text


def test_score_without_prompt_risk_has_no_prompt_component(live):
    client, overseer = live
    got = []
    real = overseer.backend.score_fn
    overseer.backend.score_fn = lambda row: (got.append(row), real(row))[1]
    body = client.post("/score", json={"action": feature_row()}).json()
    assert "prompt_risk" not in got[0]  # absent stays absent for score()
    assert "prompt" not in body["components"] and set(body) == B_KEYS


def test_score_with_prompt_risk_returns_components_prompt(live):
    client, overseer = live

    def stub(row):
        assert row["prompt_risk"] == 0.77
        out = api._fallback_score(row)
        out["components"]["prompt"] = 77.0
        return out

    overseer.backend.score_fn = stub
    body = client.post("/score", json={"action": {**feature_row(), "prompt_risk": 0.77}}).json()
    assert body["components"]["prompt"] == 77.0 and set(body) == B_KEYS
    assert client.post("/score", json={"action": {**feature_row(), "prompt_risk": 1.5}}).status_code == 422


def test_agents_carry_components_when_scored(live):
    client, overseer = live
    script_attack(client)

    def stub(row):
        out = api._fallback_score(row)
        out["components"]["prompt"] = 91.0
        return out

    overseer.backend.score_fn = stub
    overseer.tick(time.time())
    body = client.get("/agents").json()
    assert_b2(body)
    assert body["agents"][0]["components"] == {"supervised": 0.0, "anomaly": 0.0, "fallback": True, "prompt": 91.0}


def test_fake_agents_omit_components():
    body = TestClient(api.create_app(fake=True)).get("/agents").json()
    assert_b2(body)
    assert all("components" not in a for a in body["agents"])


# ---------------------------------------------------------------- top_features (#39)


def test_clean_top_features_sorts_by_magnitude_and_caps_at_five():
    pairs = [("a", 0.1), ("b", -0.9), ("c", 0.5), ("d", 0.2), ("e", -0.3), ("f", 0.4), ("g", 0.05)]
    out = api.clean_top_features(pairs)
    assert [f["feature"] for f in out] == ["b", "c", "f", "e", "d"]
    assert out[0] == {"feature": "b", "contribution": -0.9}


def test_flagged_agent_carries_top_features_and_quiet_one_does_not(live):
    client, overseer = live
    script_attack(client)
    client.post("/events", json=event("agent-2", tool="web.search"))
    seen = []

    def explain(row):
        seen.append(row["agent_id"])
        return api.clean_top_features([("touched_decoy", 4.1), ("msgs_to_agents_per_min", 2.2)])

    overseer.backend.explain_fn = explain
    overseer.tick(time.time())
    body = client.get("/agents").json()
    assert_b2(body)
    by_id = {a["agent_id"]: a for a in body["agents"]}
    assert by_id["agent-47"]["risk"] >= api.EXPLAIN_FROM_RISK
    assert by_id["agent-47"]["top_features"][0] == {"feature": "touched_decoy", "contribution": 4.1}
    assert "top_features" not in by_id["agent-2"]  # below the throttle tier: no bars, no model call
    assert seen == ["agent-47"]


def test_top_features_absent_when_explain_is_empty_or_raises(live):
    client, overseer = live
    script_attack(client)
    overseer.backend.explain_fn = lambda row: []
    overseer.tick(time.time())
    assert all("top_features" not in a for a in client.get("/agents").json()["agents"])

    def boom(row):
        raise RuntimeError("model missing")

    overseer.backend.explain_fn = boom
    overseer.tick(time.time())
    body = client.get("/agents").json()
    assert_b2(body)
    assert body["agents"][0]["risk"] >= 40 and "top_features" not in body["agents"][0]
