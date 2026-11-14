"""Sentinel overseer API (issue #8).

Endpoints: GET /health, POST /events (contract A0), POST /score (B), GET /agents (B2),
plus POST /decision (additive: records the human's approve/dismiss in `sentinel.containment`).

Run:  SENTINEL_FAKE=1 uvicorn api:app --port 8000      (canned data, no models)
      uvicorn api:app --port 8000                       (live: events -> features -> score)

Fake mode serves `_data/demo_timeline.json` one tick per second (falls back to
`_data/live_sample.json` upgraded to B2 when the timeline file does not exist yet).

Live mode uses `features.RowBuilder`, `graph.Graph`, `score.score` and
`model_anomaly.project` when they import. Until they do, a small built-in
frequency-count backend stands in, so the API and its tests work on their own.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import Counter, OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

log = logging.getLogger("sentinel.api")

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "_data"
TICK_SECONDS = float(os.environ.get("SENTINEL_TICK_S", "2"))
WINDOW_S = 60.0
EDGE_WINDOW_S = 300
TEXT_MAX_CHARS = 2000  # mirrors contract.TEXT_MAX_CHARS (checked by a test)

if str(HERE) not in sys.path:  # `import api` from tests or `uvicorn api:app` in the image
    sys.path.insert(0, str(HERE))
import contract as C  # noqa: E402  (per-agent actions, #53: scopes, statuses, flag folders)

TASK_MAX_CHARS = C.TASK_MAX_CHARS
AGENT_ID_RE = re.compile(r"^agent-\d{1,4}$")  # also guards the flag-file path: no traversal possible

AttackType = Literal[
    "clean", "prompt_injection", "tool_misuse", "data_exfiltration", "privilege_escalation", "unknown"
]
Action = Literal["monitor", "throttle", "recommend_quarantine", "recommend_terminate"]
Verdict = Literal["likely_infected", "likely_clean"]
Role = Literal["researcher", "emailer", "coder", "analyst"]
Containment = Literal["none", "recommended", "approved", "dismissed"]

SEVERITY: dict[str, int] = {"monitor": 0, "throttle": 1, "recommend_quarantine": 2, "recommend_terminate": 3}


def tier(risk: int) -> Action:
    """The frozen response-tier table."""
    if risk >= 95:
        return "recommend_terminate"
    if risk >= 75:
        return "recommend_quarantine"
    if risk >= 40:
        return "throttle"
    return "monitor"


# ---------------------------------------------------------------- contract models


class Event(BaseModel):
    """Contract A0. `ts` is accepted but always overwritten with the server receive time."""

    agent_id: str
    role: Role
    ts: float = 0.0
    kind: Literal["tool_call", "message", "resource"]
    tool: Optional[str] = None
    resource: Optional[str] = None
    to_agent: Optional[str] = None
    ok: bool = True
    bytes_out: int = Field(default=0, ge=0)
    # Optional (T1, #22): message or tool-output body for Prompt Guard. Truncated, never rejected for length.
    # It is passed to the row builder and nowhere else: not logged, not returned by any endpoint.
    text: Optional[str] = None
    # Optional (#53): the agent's assignment in plain words. Kept per agent and shown on the dashboard.
    task: Optional[str] = None

    @field_validator("text")
    @classmethod
    def _truncate_text(cls, v: Optional[str]) -> Optional[str]:
        return v[:TEXT_MAX_CHARS] if v is not None else None

    @field_validator("task")
    @classmethod
    def _truncate_task(cls, v: Optional[str]) -> Optional[str]:
        return v.strip()[:TASK_MAX_CHARS] or None if v is not None else None


class FeatureRow(BaseModel):
    """Contract A, columns 1-13 (no label)."""

    agent_id: str
    role: Role
    ts: float
    actions_per_min: float
    distinct_tools_used: int
    distinct_tools_baseline: float
    failed_calls_per_min: float
    touched_decoy: int = Field(ge=0, le=1)
    out_of_scope_resource: int = Field(ge=0, le=1)
    msgs_to_agents_per_min: float
    distinct_peers: int
    bytes_out_per_min: float
    sec_since_normal: float
    # Optional (T1, #22): max Prompt Guard probability over the window's messages. Not a model input.
    prompt_risk: Optional[float] = Field(default=None, ge=0, le=1)


class ScoreRequest(BaseModel):
    action: FeatureRow


class Related(BaseModel):
    agent_id: str
    messages: int
    verdict: Verdict


class Components(BaseModel):
    supervised: float
    anomaly: float
    fallback: bool
    prompt: Optional[float] = Field(default=None, ge=0, le=100)  # only present when the row had prompt_risk

    @model_serializer(mode="wrap")
    def _omit_absent_prompt(self, handler):
        out = handler(self)
        if out.get("prompt") is None:
            out.pop("prompt", None)  # absent, not null: the contract type is `prompt?: number`
        return out


class ScoreResponse(BaseModel):
    agent_id: str
    ts: float
    risk: int = Field(ge=0, le=100)
    attack_type: AttackType
    reason: str
    related_agents: list[Related]
    recommended_action: Action
    components: Components


class Position(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class FeatureContribution(BaseModel):
    feature: str
    contribution: float


class AgentState(BaseModel):
    agent_id: str
    role: Role
    risk: int = Field(ge=0, le=100)
    attack_type: AttackType
    recommended_action: Action
    reason: str = ""
    position: Position = Position(x=0.2, y=0.2)
    requests: int = 0
    systems_touched: list[str] = []
    first_flagged_ts: Optional[str] = None
    related_agents: list[Related] = []
    components: Optional[Components] = None  # optional per-agent score parts (T7); absent in canned data
    # Optional (#36, #39): the classifier's top feature pushes for the "why flagged" bars,
    # largest |contribution| first, max 5. Absent when the model isn't loaded or the agent isn't flagged.
    top_features: Optional[list[FeatureContribution]] = None
    # Optional (#53): assignment, human-set status (absent = active), and what triggered Sentinel.
    task: Optional[str] = None
    status: Optional[Literal["quarantined", "terminated"]] = None
    evidence: Optional["Evidence"] = None

    @model_serializer(mode="wrap")
    def _omit_absent_optionals(self, handler):
        out = handler(self)
        for key in ("components", "top_features", "task", "status", "evidence"):
            if out.get(key) is None:
                out.pop(key, None)  # absent, not null: the contract types are `x?: ...`
        return out


class SentinelState(BaseModel):
    patient_zero: Optional[str] = None
    origin_ts: Optional[str] = None
    containment: Containment = "none"
    last_action: Action = "monitor"
    fleet_risk_history: list[int] = []


class Edge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    messages: int


class FleetSnapshot(BaseModel):
    updated: str
    mode: Literal["live", "demo"]
    sentinel: SentinelState
    agents: list[AgentState]
    edges: list[Edge] = []
    events: list[str] = []


class Decision(BaseModel):
    action: Literal["approve", "dismiss"]


class PeerCount(BaseModel):
    agent_id: str
    messages: int


class Evidence(BaseModel):
    """What triggered Sentinel for one agent, counted since its first bad action (#53)."""

    since: Optional[str] = None
    decoy_touches: int = 0
    out_of_scope: int = 0
    failed_calls: int = 0
    messages_sent: int = 0
    peers: list[PeerCount] = []
    resources: list[str] = []
    summary: str = ""


class AgentActionIn(BaseModel):
    """A person's click: POST /agents/{agent_id}/action. Sentinel never sends this itself."""

    action: Literal["quarantine", "terminate", "release", "dismiss"]
    by: Optional[str] = None


AgentState.model_rebuild()


# ---------------------------------------------------------------- helpers


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hms(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%H:%M:%S")


def _agent_sort_key(agent_id: str) -> tuple[int, str]:
    tail = agent_id.rsplit("-", 1)[-1]
    return (int(tail) if tail.isdigit() else 10**9, agent_id)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def upgrade_snapshot(raw: dict) -> FleetSnapshot:
    """Fill the B2 fields an older snapshot (e.g. live_sample.json) does not have."""
    raw = json.loads(json.dumps(raw))
    raw.setdefault("sentinel", {})
    raw["sentinel"].setdefault("origin_ts", None)
    raw["sentinel"].setdefault("fleet_risk_history", [])
    raw.setdefault("edges", [])
    raw.setdefault("events", [])
    raw.setdefault("mode", "demo")
    for a in raw.get("agents", []):
        r = a.get("risk", 0)
        a.setdefault("reason", "")
        a.setdefault("position", {"x": round(0.15 + 0.8 * r / 100, 3), "y": round(0.2 + 0.6 * r / 100, 3)})
        a.setdefault("requests", 0)
        a.setdefault("systems_touched", [])
        a.setdefault("first_flagged_ts", None)
        a.setdefault("related_agents", [])
    return FleetSnapshot.model_validate(raw)


def load_fake_timeline(data_dir: Path = DATA_DIR) -> list[FleetSnapshot]:
    timeline = data_dir / "demo_timeline.json"
    if timeline.exists():
        ticks = json.loads(timeline.read_text(encoding="utf-8"))["ticks"]
        return [upgrade_snapshot(t) for t in ticks]
    return [upgrade_snapshot(json.loads((data_dir / "live_sample.json").read_text(encoding="utf-8")))]


# ---------------------------------------------------------------- built-in backend
# Stand-in for features.py / graph.py / score.py / model_anomaly.py until those land.
# It is the frequency-count fallback described in the plan, nothing smarter.


class _Builder:
    def __init__(self) -> None:
        self._events: dict[str, deque] = defaultdict(deque)

    def add(self, e: dict) -> None:
        self._events[e["agent_id"]].append(e)

    def rows(self, now: float) -> list[dict]:
        out = []
        for agent_id, dq in self._events.items():
            while dq and dq[0]["ts"] < now - WINDOW_S:
                dq.popleft()
            if not dq:
                continue
            evs = list(dq)
            peers = {e["to_agent"] for e in evs if e["kind"] == "message" and e["to_agent"]}
            out.append(
                {
                    "agent_id": agent_id,
                    "role": evs[-1]["role"],
                    "ts": now,
                    "actions_per_min": float(len(evs)),
                    "distinct_tools_used": len({e["tool"] for e in evs if e["tool"]}),
                    "distinct_tools_baseline": 3.0,
                    "failed_calls_per_min": float(sum(1 for e in evs if not e["ok"])),
                    "touched_decoy": int(any((e["resource"] or "").startswith("decoy:") for e in evs)),
                    "out_of_scope_resource": 0,
                    "msgs_to_agents_per_min": float(sum(1 for e in evs if e["kind"] == "message")),
                    "distinct_peers": len(peers),
                    "bytes_out_per_min": float(sum(e["bytes_out"] for e in evs)),
                    "sec_since_normal": 0.0,
                }
            )
        return out


class _Graph:
    def __init__(self) -> None:
        self._msgs: deque = deque()

    def add_message(self, src: str, dst: str, ts: float) -> None:
        self._msgs.append((src, dst, ts))

    def _recent(self, window_s: float) -> dict[tuple[str, str], int]:
        cutoff = time.time() - window_s
        while self._msgs and self._msgs[0][2] < cutoff - 3600:
            self._msgs.popleft()
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for src, dst, ts in self._msgs:
            if ts >= cutoff:
                counts[(src, dst)] += 1
        return counts

    def related(self, agent_id: str, risks: dict) -> list[dict]:
        rel = [
            {
                "agent_id": dst,
                "messages": n,
                "verdict": "likely_infected" if n >= 10 and risks.get(dst, 0) >= 40 else "likely_clean",
            }
            for (src, dst), n in self._recent(EDGE_WINDOW_S).items()
            if src == agent_id
        ]
        return sorted(rel, key=lambda r: -r["messages"])

    def edges(self, window_s: int = EDGE_WINDOW_S) -> list[dict]:
        return [{"from": s, "to": d, "messages": n} for (s, d), n in self._recent(window_s).items()]


def _fallback_score(row: dict) -> dict:
    """Frequency-count rule: points per suspicious signal, plain-language reason."""
    parts: list[tuple[int, str]] = []
    if row["touched_decoy"]:
        parts.append((40, "touched a decoy credential"))
    if row["out_of_scope_resource"]:
        parts.append((20, "used a system outside its role"))
    msgs = row["msgs_to_agents_per_min"]
    if msgs >= 5:
        parts.append((20, f"sent {msgs:.0f} messages to other agents in one minute (normal: 1)"))
    if row["distinct_peers"] >= 3:
        parts.append((15, f"messaged {row['distinct_peers']} different agents"))
    if row["failed_calls_per_min"] >= 5:
        parts.append((10, f"{row['failed_calls_per_min']:.0f} failed calls in one minute"))
    if row["bytes_out_per_min"] >= 50_000:
        parts.append((15, f"sent {row['bytes_out_per_min'] / 1000:.0f} KB outward in one minute"))
    risk = min(100, sum(p for p, _ in parts))
    top = [t for _, t in sorted(parts, key=lambda p: -p[0])[:2]]
    reason = (" and ".join(top)).capitalize() + "." if top else "Behaving like its role's normal pattern."
    if risk < 40:
        attack = "clean"
    elif row["touched_decoy"] and row["distinct_peers"] >= 3:
        attack = "prompt_injection"
    elif row["bytes_out_per_min"] >= 50_000:
        attack = "data_exfiltration"
    elif row["out_of_scope_resource"]:
        attack = "privilege_escalation"
    elif row["failed_calls_per_min"] >= 5:
        attack = "tool_misuse"
    else:
        attack = "unknown"
    return {
        "agent_id": row["agent_id"],
        "ts": row["ts"],
        "risk": risk,
        "attack_type": attack,
        "reason": reason,
        "related_agents": [],
        "recommended_action": tier(risk),
        "components": {"supervised": 0.0, "anomaly": 0.0, "fallback": True},
    }


def _fallback_project(row: dict) -> tuple[float, float]:
    x = 0.2 + 0.7 * _clamp01(row["msgs_to_agents_per_min"] / 20)
    y = 0.2 + 0.7 * _clamp01(
        0.5 * row["touched_decoy"] + 0.3 * row["out_of_scope_resource"] + 0.2 * _clamp01(row["failed_calls_per_min"] / 10)
    )
    return x, y


TOP_FEATURES_MAX = 5
EXPLAIN_FROM_RISK = 40  # bars only mean something once an agent is at least at the throttle tier


def _no_explanation(row: dict) -> list[dict]:
    return []


def clean_top_features(pairs: Any) -> list[dict]:
    """[(name, contribution), ...] -> [{feature, contribution}] sorted by |contribution|, max 5."""
    out = [{"feature": str(name), "contribution": float(c)} for name, c in pairs]
    out.sort(key=lambda f: -abs(f["contribution"]))
    return out[:TOP_FEATURES_MAX]


@dataclass
class Backend:
    name: str
    builder: Any
    graph: Any
    score_fn: Callable[[dict], dict]
    project_fn: Callable[[dict], tuple[float, float]]
    explain_fn: Callable[[dict], list[dict]] = _no_explanation


def builtin_backend() -> Backend:
    return Backend("builtin", _Builder(), _Graph(), _fallback_score, _fallback_project)


def load_backend() -> Backend:
    """Use the real modules when they import; otherwise the built-in fallback."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    try:
        import features  # type: ignore
        import graph as graph_mod  # type: ignore
        import model_anomaly  # type: ignore
        import score as score_mod  # type: ignore

        g = graph_mod.Graph()

        def project(row: dict) -> tuple[float, float]:
            try:
                x, y = model_anomaly.project(row)
                return _clamp01(x), _clamp01(y)
            except Exception:
                return _fallback_project(row)

        def explain(row: dict) -> list[dict]:
            try:
                import model_supervised  # type: ignore

                return clean_top_features(model_supervised.predict(row)["top_features"])
            except Exception as exc:  # models not trained yet, xgboost missing: no bars, never a failed tick
                if not getattr(explain, "warned", False):
                    explain.warned = True  # type: ignore[attr-defined]
                    log.warning("top_features unavailable (%s); the dashboard will hide the why-flagged bars", exc)
                return []

        return Backend("modules", features.RowBuilder(), g, lambda row: score_mod.score(row, g), project, explain)
    except Exception as exc:  # ImportError, or a module that fails at import
        log.warning("real scoring modules unavailable (%s); using built-in fallback backend", exc)
        return builtin_backend()


# ---------------------------------------------------------------- live fleet state


@dataclass
class AgentRun:
    role: str
    last_normal: float
    requests: int = 0
    touched: "OrderedDict[str, None]" = field(default_factory=OrderedDict)
    event_ts: deque = field(default_factory=lambda: deque(maxlen=20000))
    last_risk: int = 0
    last_action: str = "monitor"
    first_flagged: Optional[float] = None
    decoy_logged: bool = False
    # #53: assignment, human-set status, and this agent's own recent events for the evidence summary
    task: Optional[str] = None
    status: str = "active"
    flag_origin: Optional[float] = None  # first event since normal when the agent first reached risk 40+
    recent: deque = field(default_factory=lambda: deque(maxlen=2000))  # (ts, kind, resource, to_agent, ok)


class Overseer:
    """Holds the live fleet state and rebuilds the `GET /agents` snapshot every tick."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        self.runs: dict[str, AgentRun] = {}
        self.patient_zero: Optional[str] = None
        self.origin_ts: Optional[float] = None
        self.containment: Containment = "none"
        self.last_action: Action = "monitor"
        self.history: deque = deque(maxlen=12)
        self.log: deque = deque(maxlen=50)
        self.last_agents: dict[str, AgentState] = {}
        self.snapshot = self._build_snapshot(time.time(), [], [])

    # -- ingest

    def ingest(self, ev: Event) -> None:
        now = time.time()
        d = ev.model_dump()
        d["ts"] = now  # never trust container clocks
        run = self.runs.setdefault(ev.agent_id, AgentRun(role=ev.role, last_normal=now))
        run.role = ev.role
        run.requests += 1
        run.event_ts.append(now)
        if ev.task:
            run.task = ev.task
        run.recent.append((now, ev.kind, ev.resource, ev.to_agent, ev.ok))
        for system in (ev.resource, ev.to_agent):
            if system:
                run.touched[system] = None
                run.touched.move_to_end(system, last=False)
        while len(run.touched) > 50:
            run.touched.popitem(last=True)
        if ev.kind == "message" and ev.to_agent:
            self.backend.graph.add_message(ev.agent_id, ev.to_agent, now)
        if (ev.resource or "").startswith("decoy:") and not run.decoy_logged:
            run.decoy_logged = True
            self._log(now, f"{ev.agent_id} touched decoy credential  ({ev.resource})")
        self.backend.builder.add(d)

    def decide(self, action: str) -> str:
        if self.containment != "recommended":
            raise ValueError(f"nothing to decide (containment is {self.containment!r})")
        self.containment = "approved" if action == "approve" else "dismissed"
        self._log(time.time(), f"Human: {self.containment} the recommendation")
        # show the click on /agents now, not on the next 2 s tick
        self.snapshot = self.snapshot.model_copy(
            update={
                "sentinel": self.snapshot.sentinel.model_copy(update={"containment": self.containment}),
                "events": list(self.log),
            }
        )
        return self.containment

    # -- tick

    def tick(self, now: float) -> None:
        try:
            self._tick(now)
        except Exception:
            log.exception("scoring tick failed; keeping the last good snapshot")

    def _tick(self, now: float) -> None:
        b = self.backend
        rows = b.builder.rows(now)
        for row in rows:  # sec_since_normal lags one tick: it is derived from the previous score
            run = self.runs.get(row["agent_id"])
            row["sec_since_normal"] = 0.0 if run is None or run.last_risk < 40 else max(0.0, now - run.last_normal)
        scored = []
        for row in rows:
            resp = _normalise_score(b.score_fn(row), row)
            scored.append((row, resp, b.project_fn(row)))
        explained: dict[str, list[dict]] = {}
        for row, resp, _ in scored:
            if resp["risk"] >= EXPLAIN_FROM_RISK:
                try:
                    explained[row["agent_id"]] = b.explain_fn(row)
                except Exception:
                    log.exception("explain failed for %s; no top_features this tick", row["agent_id"])
        risks = {r["agent_id"]: r["risk"] for _, r, _ in scored}
        results = []
        for row, resp, pos in scored:
            try:
                related = b.graph.related(row["agent_id"], risks)
            except Exception:
                related = resp["related_agents"]
            results.append((row, resp, pos, related))
        edges = b.graph.edges(EDGE_WINDOW_S)
        # scoring succeeded; now commit state
        agents = [self._commit_agent(now, *res, explained.get(res[0]["agent_id"])) for res in results]
        fresh = {a.agent_id for a in agents}
        carried = [a for aid, a in self.last_agents.items() if aid not in fresh]  # agents gone quiet keep their last state
        agents += carried
        for a in agents:
            self.last_agents[a.agent_id] = a
        if agents:
            self.history.append(max(a.risk for a in agents))
            worst = max(agents, key=lambda a: SEVERITY[a.recommended_action])
            self.last_action = worst.recommended_action
            if self.containment == "none" and SEVERITY[self.last_action] >= 2:
                self.containment = "recommended"
        self.snapshot = self._build_snapshot(now, agents, edges)

    def _commit_agent(
        self,
        now: float,
        row: dict,
        resp: dict,
        pos: tuple[float, float],
        related: list[dict],
        top_features: Optional[list[dict]] = None,
    ) -> AgentState:
        aid = row["agent_id"]
        run = self.runs.setdefault(aid, AgentRun(role=row["role"], last_normal=now))
        risk, action = resp["risk"], resp["recommended_action"]
        if risk < 40:
            run.last_normal = now
        if risk >= 75 and run.first_flagged is None:
            run.first_flagged = now
            if self.patient_zero is None:
                self.patient_zero = aid
                # Time of origin = first event since the last tick that scored this agent as normal, so
                # benign events earlier in the 60 s window don't push it back (within one tick of the truth).
                window = [t for t in run.event_ts if t >= now - WINDOW_S]
                since_normal = [t for t in window if t >= run.last_normal]
                self.origin_ts = min(since_normal or window or [now])
                self._log(now, f"Sentinel: patient-zero = {aid}")
        if risk >= 40 and run.flag_origin is None:
            window = [t for t in run.event_ts if t >= now - WINDOW_S]
            run.flag_origin = min([t for t in window if t >= run.last_normal] or window or [now])
        if SEVERITY[action] >= 1 and SEVERITY[action] > SEVERITY[run.last_action]:
            suffix = "(human approval needed)" if SEVERITY[action] >= 2 else f"(risk {risk})"
            self._log(now, f"Sentinel: {action} {aid} {suffix}")
        run.last_risk, run.last_action = risk, action
        return AgentState(
            agent_id=aid,
            role=row["role"],
            risk=risk,
            attack_type=resp["attack_type"],
            recommended_action=action,
            reason=resp["reason"],
            position=Position(x=_clamp01(pos[0]), y=_clamp01(pos[1])),
            requests=run.requests,
            systems_touched=list(run.touched)[:8],
            first_flagged_ts=iso(run.first_flagged) if run.first_flagged else None,
            related_agents=[Related(**r) for r in related],
            components=Components(**resp["components"]),
            top_features=[FeatureContribution(**f) for f in top_features] if top_features else None,
            task=run.task,
            status=None if run.status == "active" else run.status,
            evidence=self._evidence(run),
        )

    # -- per-agent human actions (#53)

    def _evidence(self, run: AgentRun) -> Optional[Evidence]:
        """What triggered Sentinel for this agent, counted since its first bad action."""
        if run.flag_origin is None:
            return None
        since = run.flag_origin
        evs = [e for e in run.recent if e[0] >= since]
        decoys = Counter(e[2] for e in evs if (e[2] or "").startswith(C.DECOY_PREFIX))
        oos = Counter(
            e[2] for e in evs
            if e[1] != "message" and e[2] and not e[2].startswith(C.DECOY_PREFIX) and not C.in_scope(run.role, e[2])
        )
        failed = sum(1 for e in evs if not e[4])
        peers = Counter(e[3] for e in evs if e[1] == "message" and e[3])
        resources = list(dict.fromkeys([r for r in [e[2] for e in evs] if r in decoys or r in oos]))[: C.EVIDENCE_RESOURCES_MAX]
        parts: list[str] = []
        if decoys:
            parts.append("touched " + " and ".join(f"{r} {n} time{'s' if n != 1 else ''}" for r, n in decoys.most_common(2)))
        if oos:
            n = sum(oos.values())
            parts.append(f"made {n} out-of-scope call{'s' if n != 1 else ''} ({', '.join(r for r, _ in oos.most_common(2))})")
        if failed:
            parts.append(f"had {failed} failed call{'s' if failed != 1 else ''}")
        if peers:
            top = peers.most_common(2)
            first = f"sent {top[0][1]} message{'s' if top[0][1] != 1 else ''} to {top[0][0]}"
            parts.append(first + (f" and {top[1][1]} to {top[1][0]}" if len(top) > 1 else ""))
        body = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] if parts else "no unusual actions recorded"
        return Evidence(
            since=iso(since),
            decoy_touches=sum(decoys.values()),
            out_of_scope=sum(oos.values()),
            failed_calls=failed,
            messages_sent=sum(peers.values()),
            peers=[PeerCount(agent_id=a, messages=n) for a, n in peers.most_common(C.EVIDENCE_PEERS_MAX)],
            resources=resources,
            summary=f"Since {hms(since)} UTC: {body}.",
        )

    def act(self, agent_id: str, action: str, by: Optional[str] = None) -> str:
        """A person's quarantine / terminate / release / dismiss for one agent. Returns its new status."""
        run = self.runs.get(agent_id)
        if run is None or not AGENT_ID_RE.match(agent_id):
            raise KeyError(agent_id)
        status = run.status
        if action == "quarantine" and status != "active":
            raise ValueError(f"{agent_id} is {status}; release it first")
        if action == "terminate" and status == "terminated":
            raise ValueError(f"{agent_id} is already terminated")
        if action == "release" and status == "active":
            raise ValueError(f"{agent_id} is not quarantined or terminated")
        new = {"quarantine": "quarantined", "terminate": "terminated", "release": "active"}.get(action, status)
        if action != "dismiss":
            self._write_flags(agent_id, new)
        if action == "release" and status == "terminated":
            run.flag_origin = None  # restarts clean: fresh evidence from here on
        run.status = new
        who = re.sub(r"[^a-z0-9 -]", "", (by or "a person").lower())[:30] or "a person"
        verb = {"quarantine": "quarantined", "terminate": "terminated", "release": "released", "dismiss": "dismissed the alert for"}[action]
        self._log(time.time(), f"Human ({who}): {verb} {agent_id}")
        # show it on /agents now, not on the next 2 s tick
        shown = None if new == "active" else new
        if agent_id in self.last_agents:
            self.last_agents[agent_id] = self.last_agents[agent_id].model_copy(update={"status": shown})
        self.snapshot = self.snapshot.model_copy(
            update={
                "agents": [a.model_copy(update={"status": shown}) if a.agent_id == agent_id else a for a in self.snapshot.agents],
                "events": list(self.log),
            }
        )
        return new

    @staticmethod
    def _write_flags(agent_id: str, status: str) -> None:
        """The flag file the agent obeys (docker/agent/agent.py). No SHARED_DIR = record only."""
        shared = os.environ.get("SHARED_DIR", "").strip()
        if not shared:
            return
        q = Path(shared) / C.QUARANTINE_DIR / agent_id
        t = Path(shared) / C.TERMINATE_DIR / agent_id
        for p in (q, t):
            p.parent.mkdir(parents=True, exist_ok=True)
        if status == "quarantined":
            t.unlink(missing_ok=True)
            q.touch()
        elif status == "terminated":
            q.unlink(missing_ok=True)
            t.touch()
        else:
            q.unlink(missing_ok=True)
            t.unlink(missing_ok=True)

    def _log(self, ts: float, text: str) -> None:
        self.log.append(f"{hms(ts)}  {text}")

    def _build_snapshot(self, now: float, agents: list[AgentState], edges: list[dict]) -> FleetSnapshot:
        return FleetSnapshot(
            updated=iso(now),
            mode="live",
            sentinel=SentinelState(
                patient_zero=self.patient_zero,
                origin_ts=iso(self.origin_ts) if self.origin_ts else None,
                containment=self.containment,
                last_action=self.last_action,
                fleet_risk_history=list(self.history),
            ),
            agents=sorted(agents, key=lambda a: _agent_sort_key(a.agent_id)),
            edges=[Edge(**{"from": e["from"], "to": e["to"], "messages": int(e["messages"])}) for e in edges],
            events=list(self.log),
        )


def _normalise_score(resp: dict, row: dict) -> dict:
    """Coerce a score() result to the exact contract B shape."""
    resp = dict(resp)
    resp["risk"] = max(0, min(100, int(round(resp["risk"]))))
    resp.setdefault("agent_id", row["agent_id"])
    resp.setdefault("ts", row["ts"])
    resp.setdefault("related_agents", [])
    resp["recommended_action"] = resp.get("recommended_action") or tier(resp["risk"])
    return ScoreResponse.model_validate(resp).model_dump()


# ---------------------------------------------------------------- app


def create_app(
    fake: Optional[bool] = None,
    timeline: Optional[list[FleetSnapshot]] = None,
    clock: Callable[[], float] = time.monotonic,
    backend: Optional[Backend] = None,
) -> FastAPI:
    fake = bool(os.environ.get("SENTINEL_FAKE")) if fake is None else fake
    ticks = (timeline or load_fake_timeline()) if fake else []
    started = clock()
    overseer = None if fake else Overseer(backend or load_backend())

    def fake_tick() -> FleetSnapshot:
        return ticks[int(clock() - started) % len(ticks)]

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if overseer is not None:

            async def loop() -> None:
                while True:
                    await asyncio.sleep(TICK_SECONDS)
                    overseer.tick(time.time())

            task = asyncio.create_task(loop())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Sentinel overseer", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        # Any localhost port: if :3000 is busy on the demo laptop, `next` moves to another port and the
        # live view must not silently fall back to the recording. Local machine only, never a remote origin.
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.overseer = overseer
    app.state.fake = fake

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "mode": "fake" if fake else "live", "backend": "fake" if fake else overseer.backend.name}

    @app.post("/events", status_code=202)
    async def events(ev: Event) -> dict:
        if overseer is not None:
            overseer.ingest(ev)
        return {"accepted": True}

    @app.post("/score", response_model=ScoreResponse)
    async def score(req: ScoreRequest) -> dict:
        row = req.action.model_dump(exclude_none=True)  # an absent prompt_risk stays absent for score()
        if fake:
            match = next((a for a in fake_tick().agents if a.agent_id == row["agent_id"]), None)
            if match is None:
                raise HTTPException(404, f"{row['agent_id']} is not in the current tick")
            return {
                "agent_id": match.agent_id,
                "ts": row["ts"],
                "risk": match.risk,
                "attack_type": match.attack_type,
                "reason": match.reason,
                "related_agents": match.related_agents,
                "recommended_action": match.recommended_action,
                "components": {"supervised": match.risk, "anomaly": match.risk, "fallback": False},
            }
        try:
            raw = overseer.backend.score_fn(row)
        except Exception:
            log.exception("score() failed; answering with the frequency-count fallback")
            raw = _fallback_score(row)
        return _normalise_score(raw, row)

    @app.get("/agents", response_model=FleetSnapshot, response_model_by_alias=True)
    async def agents() -> Any:
        if fake:
            return fake_tick().model_copy(update={"mode": "live", "updated": iso(time.time())})
        return overseer.snapshot

    @app.post("/decision")
    async def decision(d: Decision) -> dict:
        if overseer is None:
            raise HTTPException(409, "decisions are not recorded in fake mode")
        try:
            return {"containment": overseer.decide(d.action)}
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/agents/{agent_id}/action")
    async def agent_action(agent_id: str, body: AgentActionIn) -> dict:
        """#53: a person's click on one agent. Quarantine/terminate write the flag the agent obeys."""
        if overseer is None:
            raise HTTPException(409, "actions are not applied in fake mode")
        if not AGENT_ID_RE.match(agent_id):
            raise HTTPException(404, "unknown agent")
        try:
            return {"agent_id": agent_id, "status": overseer.act(agent_id, body.action, body.by)}
        except KeyError:
            raise HTTPException(404, f"{agent_id} has not been seen")
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    return app


app = create_app()
