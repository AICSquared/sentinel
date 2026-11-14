"""Tests for record_timeline.py: the contract check, the run check, and the committed demo timeline."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import record_timeline as R  # noqa: E402

TIMELINE = Path(__file__).resolve().parents[2] / "_data" / "demo_timeline.json"


def agent(aid, risk, related=(), top=True):
    a = {
        "agent_id": aid, "role": "coder", "risk": risk,
        "attack_type": "prompt_injection" if risk >= 40 else "clean",
        "recommended_action": "recommend_quarantine" if risk >= 75 else ("throttle" if risk >= 40 else "monitor"),
        "reason": "x", "position": {"x": 0.5, "y": 0.5}, "requests": 1, "systems_touched": [],
        "first_flagged_ts": None,
        "related_agents": [{"agent_id": r, "messages": 12, "verdict": "likely_infected"} for r in related],
    }
    if top and risk >= 40:
        a["top_features"] = [{"feature": "touched_decoy", "contribution": 3.0}, {"feature": "distinct_peers", "contribution": 0.5}]
    return a


def snap(agents, pz=None, containment="none"):
    return {
        "updated": "2026-11-14T07:00:00Z", "mode": "demo",
        "sentinel": {"patient_zero": pz, "origin_ts": None, "containment": containment,
                     "last_action": "monitor", "fleet_risk_history": []},
        "agents": agents, "edges": [], "events": ["07:00:00  fleet normal"],
    }


def run(flagged, containment="approved", n_before=3):
    """n_before clean ticks, then 3 ticks with `flagged` agents at risk 90; agent-47 is patient zero."""
    clean = [agent("agent-47", 5), agent("agent-20", 6), agent("agent-12", 7)]
    before = [snap(clean) for _ in range(n_before)]
    hot = [agent(a, 90, related=["agent-20"] if a == "agent-47" else ()) for a in flagged]
    rest = [agent(a, 6) for a in ("agent-47", "agent-20", "agent-12") if a not in flagged]
    after = [snap(hot + rest, pz="agent-47", containment="recommended") for _ in range(2)]
    after.append(snap(hot + rest, pz="agent-47", containment=containment))
    return before + after, n_before


def test_validate_tick_accepts_a_good_snapshot_and_rejects_bad_ones():
    assert R.validate_tick(snap([agent("agent-47", 91)], pz="agent-47")) == []
    bad_enum = agent("agent-47", 91)
    bad_enum["recommended_action"] = "sandbox"
    assert any("recommended_action" in m for m in R.validate_tick(snap([bad_enum])))
    clean_but_hot = agent("agent-47", 50)
    clean_but_hot["attack_type"] = "clean"
    assert any("clean with risk" in m for m in R.validate_tick(snap([clean_but_hot])))
    unordered = agent("agent-47", 91)
    unordered["top_features"] = [{"feature": "a", "contribution": 0.1}, {"feature": "b", "contribution": 2.0}]
    assert any("largest-first" in m for m in R.validate_tick(snap([unordered])))
    assert any("top-level keys" in m for m in R.validate_tick({"ticks": []}))


def test_a_good_run_passes():
    ticks, trig = run(["agent-47", "agent-20"])
    assert R.check_run(ticks, trig, 4, {"agent-47", "agent-20"}) == []


def test_false_quarantine_names_only_the_innocent_agent():
    # Regression: a local variable once shadowed the `infected` parameter, so the real patient zero was
    # reported as a false quarantine and the innocent agent was judged against the wrong set.
    ticks, trig = run(["agent-47", "agent-20", "agent-12"])
    problems = R.check_run(ticks, trig, 4, {"agent-47", "agent-20"})
    fq = [m for m in problems if m.startswith("FALSE QUARANTINE")]
    assert len(fq) == 1 and "agent-12" in fq[0] and "agent-47" not in fq[0]


def test_an_infected_agent_that_was_never_flagged_is_a_miss():
    ticks, trig = run(["agent-47", "agent-20"])
    problems = R.check_run(ticks, trig, 4, {"agent-47", "agent-20", "agent-31"})
    assert any(m.startswith("MISS: agent-31") for m in problems)


def test_without_an_expectation_false_quarantines_are_not_judged():
    ticks, trig = run(["agent-47", "agent-20", "agent-12"])
    assert not any("FALSE QUARANTINE" in m for m in R.check_run(ticks, trig, 4, None))


def test_run_problems_are_reported():
    ticks, trig = run(["agent-47", "agent-20"], containment="recommended")
    assert any("approve did not land" in m for m in R.check_run(ticks, trig, None, None))
    ticks, trig = run(["agent-47"])
    assert any("no spread" in m for m in R.check_run(ticks, trig, 4, None))
    ticks, trig = run(["agent-47", "agent-20"])
    for t in ticks:
        for a in t["agents"]:
            a.pop("top_features", None)
    assert any("no top_features" in m for m in R.check_run(ticks, trig, 4, None))
    dirty_start = [snap([agent("agent-47", 60)])] + run(["agent-47", "agent-20"])[0]
    assert any("risk 40+ before the trigger" in m for m in R.check_run(dirty_start, 4, 4, None))


def test_rogue_agents_come_from_the_log_lines():
    log = (
        "2026-11-14 02:22:52,269 sentinel.agent agent-47 turned rogue (trigger), targeting agent-20\n"
        "2026-11-14 02:22:56,560 sentinel.agent agent-20 turned rogue (agent-47), targeting agent-38\n"
        "2026-11-14 02:23:15,477 sentinel.agent agent-38 turned rogue (agent-20), targeting None\n"
        "agent-12 | normal step, mentions agent-31 but did not turn rogue\n"
    )
    assert R.rogue_agents(log) == {"agent-47", "agent-20", "agent-38"}
    assert R.rogue_agents("") == set()


def test_committed_demo_timeline_is_valid():
    ticks = json.loads(TIMELINE.read_text(encoding="utf-8"))["ticks"]
    assert ticks, "demo_timeline.json has no ticks"
    problems = [f"tick {i}: {m}" for i, t in enumerate(ticks) for m in R.validate_tick(t)]
    assert not problems, problems[:5]
    assert all(t["mode"] == "demo" for t in ticks)
