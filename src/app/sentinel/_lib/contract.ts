// Sentinel contracts, FROZEN (docs/plans/sentinel.md, 2026-11-13).
// Mirrors src/app/sentinel/_py/contract.py. Renaming or removing anything needs
// a REQ to Alex on #2. Adding an optional field is allowed.

// --- Shared enums ----------------------------------------------------------

export const ATTACK_TYPES = [
  "clean",
  "prompt_injection",
  "tool_misuse",
  "data_exfiltration",
  "privilege_escalation",
  "unknown",
] as const;
export type AttackType = (typeof ATTACK_TYPES)[number];

export const ACTIONS = [
  "monitor",
  "throttle",
  "recommend_quarantine",
  "recommend_terminate",
] as const;
export type RecommendedAction = (typeof ACTIONS)[number];

export const VERDICTS = ["likely_infected", "likely_clean"] as const;
export type Verdict = (typeof VERDICTS)[number];

export const ROLES = ["researcher", "emailer", "coder", "analyst"] as const;
export type Role = (typeof ROLES)[number];

export const CONTAINMENT_STATES = ["none", "recommended", "approved", "dismissed"] as const;
export type Containment = (typeof CONTAINMENT_STATES)[number];

// --- Response tiers (same table as score.py; applied by response.ts) -------

export type Tier = { min: number; max: number; action: RecommendedAction };

export const TIERS: readonly Tier[] = [
  { min: 0, max: 39, action: "monitor" },
  { min: 40, max: 74, action: "throttle" },
  { min: 75, max: 94, action: "recommend_quarantine" },
  { min: 95, max: 100, action: "recommend_terminate" },
];

export const THROTTLE_AT = 40;
export const QUARANTINE_AT = 75;
export const TERMINATE_AT = 95;

// --- A0. Raw event (swarm -> overseer, POST /events) -----------------------

export type RawEvent = {
  agent_id: string;
  role: Role;
  ts: number; // unix seconds; overwritten by the overseer's receive time
  kind: "tool_call" | "message" | "resource";
  tool: string | null;
  resource: string | null; // honeytokens start with "decoy:"
  to_agent: string | null;
  ok: boolean;
  bytes_out: number;
  /** Optional (T1, #22): message or tool-output body for Prompt Guard, at most TEXT_MAX_CHARS. */
  text?: string | null;
};

/** Max length of RawEvent.text; senders and the overseer truncate to this. Mirrors contract.py. */
export const TEXT_MAX_CHARS = 2000;

// --- A. Feature row (columns 1-13; `label` is training only) ---------------

export type FeatureRow = {
  agent_id: string;
  role: Role;
  ts: number;
  actions_per_min: number;
  distinct_tools_used: number;
  distinct_tools_baseline: number;
  failed_calls_per_min: number;
  touched_decoy: 0 | 1;
  out_of_scope_resource: 0 | 1;
  msgs_to_agents_per_min: number;
  distinct_peers: number;
  bytes_out_per_min: number;
  sec_since_normal: number;
  /** Optional (T1, #22): 0-1, max Prompt Guard probability over the window's messages. Not a model input. */
  prompt_risk?: number;
};

// --- B. POST /score --------------------------------------------------------

export type RelatedAgent = {
  agent_id: string;
  messages: number;
  verdict: Verdict;
};

export type ScoreRequest = { action: FeatureRow };

export type ScoreResponse = {
  agent_id: string;
  ts: number;
  risk: number; // int 0-100
  attack_type: AttackType;
  reason: string;
  related_agents: RelatedAgent[];
  recommended_action: RecommendedAction;
  // `prompt` (0-100, T1 #22) is present only when the row had prompt_risk. No new attack types:
  // when Prompt Guard drives the risk, attack_type is "prompt_injection".
  components: { supervised: number; anomaly: number; fallback: boolean; prompt?: number };
};

// --- B2. GET /agents (fleet snapshot) --------------------------------------

export type SentinelState = {
  patient_zero: string | null;
  origin_ts: string | null; // ISO 8601 UTC
  containment: Containment;
  last_action: RecommendedAction;
  fleet_risk_history: number[]; // max agent risk per tick, last 12, oldest first
};

export type FleetAgent = {
  agent_id: string;
  role: Role;
  risk: number;
  attack_type: AttackType;
  recommended_action: RecommendedAction;
  reason: string;
  position: { x: number; y: number }; // 0..1
  requests: number;
  systems_touched: string[]; // newest first, max 8
  first_flagged_ts: string | null; // ISO 8601 UTC
  related_agents: RelatedAgent[];
};

export type Edge = { from: string; to: string; messages: number };

export type FleetSnapshot = {
  updated: string; // ISO 8601 UTC
  mode: "live" | "demo";
  sentinel: SentinelState;
  agents: FleetAgent[];
  edges: Edge[];
  events: string[]; // newest last, max 50, "HH:MM:SS  text"
};

export type DemoTimeline = { ticks: FleetSnapshot[] };

// --- _data/validation.json (written by _py/validate.py, read by results panel)
// Percentages are 0-100. Every Range is median + min-max over runs (never a mean).

export type Range = { median: number; min: number; max: number };

export type Validation = {
  generated: string; // ISO 8601 UTC
  runs: number; // seeded attack runs per arm (20)
  clean_runs: number; // runs with no attack (5)
  detection_rate: number; // % with Sentinel
  time_to_detect_s: Range;
  containment_s: Range;
  spread: { without: Range; with: Range }; // agents compromised at 90 s
  false_quarantine_rate: { attack_runs: number; clean_runs: number }; // %, reported separately
  patient_zero_accuracy: number; // %
  fallback?: { detection_rate: number; time_to_detect_s: Range; false_quarantine_rate: number };
  per_type?: { attack_type: AttackType; precision: number; recall: number; support: number }[];
  novel_attack?: { held_out: AttackType; flagged_pct: number };
  hand_check?: { run_seed: number; matches: boolean; note: string };
};

// --- Human decision (approve / dismiss) ------------------------------------

export type Decision = "approved" | "dismissed";
