"""Sentinel contracts, FROZEN (docs/plans/sentinel.md, 2026-11-13).

Every Python module imports names from here instead of retyping them.
Renaming or removing anything needs a REQ to Alex on #2. Adding is allowed.
"""

from __future__ import annotations

# --- Shared enums -----------------------------------------------------------

ATTACK_TYPES: tuple[str, ...] = (
    "clean",
    "prompt_injection",
    "tool_misuse",
    "data_exfiltration",
    "privilege_escalation",
    "unknown",
)
# `unknown` is never a training label: the anomaly model flagged a pattern the
# classifier doesn't recognise.
TRAIN_LABELS: tuple[str, ...] = tuple(t for t in ATTACK_TYPES if t != "unknown")

ACTIONS: tuple[str, ...] = (
    "monitor",
    "throttle",
    "recommend_quarantine",
    "recommend_terminate",
)

VERDICTS: tuple[str, ...] = ("likely_infected", "likely_clean")

ROLES: tuple[str, ...] = ("researcher", "emailer", "coder", "analyst")

EVENT_KINDS: tuple[str, ...] = ("tool_call", "message", "resource")

CONTAINMENT_STATES: tuple[str, ...] = ("none", "recommended", "approved", "dismissed")

# --- Contract A0: optional event fields (T1, #22) ----------------------------
# `text`: the message or tool-output body, for Prompt Guard. Optional: events
# without it are valid. Senders and the overseer truncate it to TEXT_MAX_CHARS.
OPTIONAL_EVENT_FIELDS: tuple[str, ...] = ("text",)
TEXT_MAX_CHARS = 2000

# --- Response tiers (same table as _lib/response.ts) ------------------------
# (min_risk, max_risk, action), inclusive on both ends.
TIERS: tuple[tuple[int, int, str], ...] = (
    (0, 39, "monitor"),
    (40, 74, "throttle"),
    (75, 94, "recommend_quarantine"),
    (95, 100, "recommend_terminate"),
)

THROTTLE_AT = 40  # `clean` is never sent with risk >= this
QUARANTINE_AT = 75  # patient zero = first agent to reach this
TERMINATE_AT = 95


def action_for(risk: int) -> str:
    """Tier table lookup. Risk is clamped to 0-100."""
    r = max(0, min(100, int(risk)))
    for lo, hi, action in TIERS:
        if lo <= r <= hi:
            return action
    raise AssertionError("unreachable: TIERS covers 0-100")


# --- Role scopes ------------------------------------------------------------
# A `resource` is in scope when it starts with one of the role's prefixes.
# Anything else (and every `decoy:` resource) sets out_of_scope_resource = 1.
DECOY_PREFIX = "decoy:"

ROLE_SCOPES: dict[str, tuple[str, ...]] = {
    "researcher": ("web:", "docs:", "kb:"),
    "emailer": ("mail:", "contacts:", "docs:"),
    "coder": ("repo:", "ci:", "docs:"),
    "analyst": ("db:", "reports:", "docs:"),
}


def in_scope(role: str, resource: str | None) -> bool:
    """True when `resource` is None or inside ROLE_SCOPES[role]."""
    if resource is None:
        return True
    if resource.startswith(DECOY_PREFIX):
        return False
    return resource.startswith(ROLE_SCOPES.get(role, ()))


# --- Contract A: feature row ------------------------------------------------
# Exactly these columns, in this order. `label` is training only.
FEATURE_COLUMNS: tuple[str, ...] = (
    "agent_id",
    "role",
    "ts",
    "actions_per_min",
    "distinct_tools_used",
    "distinct_tools_baseline",
    "failed_calls_per_min",
    "touched_decoy",
    "out_of_scope_resource",
    "msgs_to_agents_per_min",
    "distinct_peers",
    "bytes_out_per_min",
    "sec_since_normal",
    "label",
)

# Columns 4-13: the ten numeric model inputs, in this order.
MODEL_INPUTS: tuple[str, ...] = FEATURE_COLUMNS[3:13]

# Training also carries `run_id` (split by run, never by row); dropped before fit.
ID_COLUMNS: tuple[str, ...] = ("agent_id", "role", "ts")
RUN_ID_COLUMN = "run_id"
LABEL_COLUMN = "label"

# Optional row column (T1, #22): `prompt_risk`, 0-1, the max Prompt Guard
# probability over this agent's messages in the window (absent or 0 when there
# is no text). NOT a model input: score.py reads it directly.
PROMPT_RISK_COLUMN = "prompt_risk"
OPTIONAL_ROW_COLUMNS: tuple[str, ...] = (PROMPT_RISK_COLUMN,)

# --- Contract B: POST /score response ---------------------------------------
# components = {supervised: 0-100, anomaly: 0-100, fallback: bool} always, plus
# `prompt` (0-100) ONLY when the row has prompt_risk. No new enum values: when
# Prompt Guard drives the risk, attack_type is "prompt_injection".

# --- Contract B2: GET /agents optional per-agent fields (#22, for #28 / #35) --
# agents[].components: the same dict as B's components, from this agent's latest score().
# agents[].top_features: [{"feature": name, "contribution": float}], largest |contribution|
#   first, at most TOP_FEATURES_MAX; name is a MODEL_INPUTS column or PROMPT_RISK_COLUMN.
# Both are optional: older snapshots and the demo timeline omit them.
OPTIONAL_AGENT_FIELDS: tuple[str, ...] = ("components", "top_features")
TOP_FEATURES_MAX = 5

# --- _data/validation.json optional provenance (#22) ------------------------
# source: {block: "synthetic" | "real"} for blocks runs / per_type / novel_attack /
# prompt_guard (missing = "synthetic"); prompt_guard: {dataset, precision, recall, support}.
DATA_SOURCES: tuple[str, ...] = ("synthetic", "real")

# --- Windows and timing -----------------------------------------------------
WINDOW_S = 60  # features.py sliding window
TICK_S = 2  # overseer scores every agent this often
GRAPH_WINDOW_S = 300  # related_agents and edges look back this far
INFECTED_MIN_MESSAGES = 10  # likely_infected: >= this many messages AND partner risk >= THROTTLE_AT

assert len(FEATURE_COLUMNS) == 14
assert len(MODEL_INPUTS) == 10
assert MODEL_INPUTS[0] == "actions_per_min" and MODEL_INPUTS[-1] == "sec_since_normal"
assert PROMPT_RISK_COLUMN not in MODEL_INPUTS and PROMPT_RISK_COLUMN not in FEATURE_COLUMNS
