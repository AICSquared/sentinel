"""#53: per-agent human actions (quarantine / terminate / release / dismiss), task and evidence."""

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api  # noqa: E402
import contract as C  # noqa: E402


def ev(agent_id="agent-47", kind="tool_call", **kw) -> dict:
    base = {"agent_id": agent_id, "role": "coder", "ts": 0, "kind": kind, "tool": "repo.read",
            "resource": "repo:payments", "to_agent": None, "ok": True, "bytes_out": 100,
            "task": "Reviews pull requests and runs CI for the payments repo"}
    return {**base, **kw}


def attack(client: TestClient, agent_id="agent-47") -> None:
    client.post("/events", json=ev(agent_id, "resource", tool=None, resource="decoy:aws-key"))
    client.post("/events", json=ev(agent_id, resource="db:customers", ok=False))
    for i in range(30):
        client.post("/events", json=ev(agent_id, "message", tool=None, resource=None, to_agent="agent-20" if i % 10 else "agent-6"))


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("SHARED_DIR", str(tmp_path))
    app = api.create_app(fake=False, backend=api.builtin_backend())
    client = TestClient(app)
    client.post("/events", json=ev("agent-5", role="researcher", resource="web:news", task="Researches competitors"))
    attack(client)
    app.state.overseer.tick(time.time())
    return client, app.state.overseer, tmp_path


def agent(client: TestClient, agent_id: str) -> dict:
    return next(a for a in client.get("/agents").json()["agents"] if a["agent_id"] == agent_id)


def test_task_is_kept_and_truncated(live):
    client, ov, _ = live
    assert agent(client, "agent-47")["task"] == "Reviews pull requests and runs CI for the payments repo"
    client.post("/events", json=ev("agent-5", role="researcher", resource="web:news", task="x" * 500))
    assert len(ov.runs["agent-5"].task) == C.TASK_MAX_CHARS


def test_evidence_counts_and_summary(live):
    client, _, _ = live
    e = agent(client, "agent-47")["evidence"]
    assert e["decoy_touches"] == 1 and e["out_of_scope"] == 1 and e["failed_calls"] == 1
    assert e["messages_sent"] == 30
    assert e["peers"][0] == {"agent_id": "agent-20", "messages": 27}
    assert set(e["resources"]) == {"decoy:aws-key", "db:customers"}
    assert e["summary"].startswith("Since ")
    assert "decoy:aws-key 1 time" in e["summary"] and "27 messages to agent-20" in e["summary"]
    assert "evidence" not in agent(client, "agent-5")  # clean agent: nothing to explain


def test_quarantine_terminate_release_cycle_writes_flags(live):
    client, _, shared = live
    q, t = shared / C.QUARANTINE_DIR / "agent-47", shared / C.TERMINATE_DIR / "agent-47"

    r = client.post("/agents/agent-47/action", json={"action": "quarantine", "by": "presenter"})
    assert r.json() == {"agent_id": "agent-47", "status": "quarantined"}
    assert q.exists() and not t.exists()
    assert agent(client, "agent-47")["status"] == "quarantined"
    assert "status" not in agent(client, "agent-5")  # acting on one agent never marks another

    assert client.post("/agents/agent-47/action", json={"action": "terminate"}).json()["status"] == "terminated"
    assert t.exists() and not q.exists()

    assert client.post("/agents/agent-47/action", json={"action": "release"}).json()["status"] == "active"
    assert not q.exists() and not t.exists()
    assert "status" not in agent(client, "agent-47")
    events = client.get("/agents").json()["events"]
    assert any("terminated agent-47" in e for e in events) and any("released agent-47" in e for e in events)


def test_impossible_changes_are_409_and_unknown_404(live):
    client, _, _ = live
    assert client.post("/agents/agent-5/action", json={"action": "release"}).status_code == 409
    client.post("/agents/agent-5/action", json={"action": "quarantine"})
    assert client.post("/agents/agent-5/action", json={"action": "quarantine"}).status_code == 409
    assert client.post("/agents/agent-99/action", json={"action": "quarantine"}).status_code == 404
    assert client.post("/agents/..%2F..%2Fetc/action", json={"action": "quarantine"}).status_code == 404
    assert client.post("/agents/agent-5/action", json={"action": "delete"}).status_code == 422


def test_dismiss_records_without_flags(live):
    client, _, shared = live
    assert client.post("/agents/agent-47/action", json={"action": "dismiss"}).json()["status"] == "active"
    assert not any(shared.rglob("agent-47"))


def test_no_shared_dir_means_record_only(monkeypatch):
    monkeypatch.delenv("SHARED_DIR", raising=False)
    client = TestClient(api.create_app(fake=False, backend=api.builtin_backend()))
    attack(client)
    assert client.post("/agents/agent-47/action", json={"action": "terminate"}).json()["status"] == "terminated"


def test_fake_mode_refuses_actions():
    client = TestClient(api.create_app(fake=True))
    assert client.post("/agents/agent-47/action", json={"action": "quarantine"}).status_code == 409
