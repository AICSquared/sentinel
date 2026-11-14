# Sentinel — plan

An immune system for a team of AI agents. One overseer watches a swarm, scores each agent 0-100 for risk, maps who talked to whom, and recommends (never enforces) quarantine or termination to a human.

Track: Mission 3 (Secret Vault / Autonomous AI Safety), Cisco. Pathway A (working prototype). Team of 4. Board: everyone posts to **#2**; lead is #1. PR prefix: `sentinel:`.

**The gap.** Commercial AI detection-and-response protects ONE agent from outsiders. Almost nobody protects an agent TEAM from infecting itself: one hijacked agent messages its peers and the compromise spreads. Sentinel watches the team, finds patient zero, traces the spread, and hands a human a recommendation.

---

## The contracts — FROZEN

Frozen on 2026-11-13. Changing any name, type or enum below needs a `REQ` to Alex on #2 and a reply from every owner who consumes it. Adding an optional field is allowed; renaming or removing is not.

Machine-readable copies (Alex commits these first, in the integration issue):
- `src/app/sentinel/_py/contract.py`: `FEATURE_COLUMNS`, `MODEL_INPUTS`, `ATTACK_TYPES`, `ACTIONS`, `TIERS`, `ROLE_SCOPES`
- `src/app/sentinel/_lib/contract.ts`: TypeScript types `ScoreResponse`, `FleetSnapshot`

### Shared enums

| name | values |
|---|---|
| `attack_type` | `clean`, `prompt_injection`, `tool_misuse`, `data_exfiltration`, `privilege_escalation`, `unknown` |
| `recommended_action` | `monitor`, `throttle`, `recommend_quarantine`, `recommend_terminate` |
| `verdict` (related agents) | `likely_infected`, `likely_clean` |
| `role` | `researcher`, `emailer`, `coder`, `analyst` |

`unknown` means the anomaly model flagged the agent but the classifier doesn't recognise the pattern (a possible novel attack). `clean` is never sent with a risk of 40 or more. `unknown` is never a training label.

**Core demo attack:** `prompt_injection` that spreads through agent-to-agent messages. The other types exist in the training data so per-type precision/recall means something.

### Response tiers (one table, used by both `score.py` and `_lib/response.ts`)

| risk | recommended_action | what the human sees |
|---|---|---|
| 0-39 | `monitor` | nothing; the dot stays grey |
| 40-74 | `throttle` | amber: "slow this agent down?" |
| 75-94 | `recommend_quarantine` | red, with approve / dismiss |
| 95-100 | `recommend_terminate` | red with outline, approve / dismiss |

Every tier is a recommendation. Nothing happens without a human click, and the click is written to the audit log.

### A0. Raw event (swarm → overseer)

Each scripted agent POSTs one JSON object per action to the overseer at `POST /events`.

```json
{
  "agent_id": "agent-47",
  "role": "coder",
  "ts": 1794636002.13,
  "kind": "tool_call",
  "tool": "shell.exec",
  "resource": "repo:payments",
  "to_agent": null,
  "ok": true,
  "bytes_out": 512
}
```

| field | type | meaning |
|---|---|---|
| `agent_id` | string | `agent-<n>` |
| `role` | enum `role` | fixed at container start |
| `ts` | float | unix seconds. The overseer overwrites it with its own receive time (don't trust container clocks) |
| `kind` | `"tool_call"`, `"message"` or `"resource"` | what happened |
| `tool` | string or null | tool name for a `tool_call` |
| `resource` | string or null | what it touched. Honeytokens start with `decoy:` |
| `to_agent` | string or null | recipient of a `message` |
| `ok` | bool | the call succeeded |
| `bytes_out` | int | bytes sent outward by this action |
| `text` | string or null, **optional** (T1, #22) | message or tool-output body for Prompt Guard, truncated to 2,000 characters (`TEXT_MAX_CHARS`) |

### A. Feature row (what the models consume)

`features.py` turns a 60-second sliding window of one agent's events into one row. The overseer computes one row per agent every 2 seconds. The training dataset uses exactly these columns, in this order.

| # | column | type | meaning |
|---|---|---|---|
| 1 | `agent_id` | string | which agent (an id, never a model input) |
| 2 | `role` | string | the agent's role (an id, never a model input) |
| 3 | `ts` | float | unix seconds, end of the window |
| 4 | `actions_per_min` | float | events in the window, scaled to one minute |
| 5 | `distinct_tools_used` | int | distinct `tool` values in the window |
| 6 | `distinct_tools_baseline` | float | this role's MEDIAN distinct tools on clean data |
| 7 | `failed_calls_per_min` | float | events with `ok=false`, per minute |
| 8 | `touched_decoy` | 0/1 | any `resource` starting with `decoy:` |
| 9 | `out_of_scope_resource` | 0/1 | any `resource` outside `ROLE_SCOPES[role]` |
| 10 | `msgs_to_agents_per_min` | float | `message` events per minute |
| 11 | `distinct_peers` | int | distinct `to_agent` values in the window |
| 12 | `bytes_out_per_min` | float | sum of `bytes_out`, per minute |
| 13 | `sec_since_normal` | float | seconds since this agent's last window that scored `monitor` (0 if this one did) |
| 14 | `label` | string | an `attack_type` value except `unknown`. Training only; absent at inference |

Model inputs (`MODEL_INPUTS`) are columns 4-13: ten numeric features. Training also needs a `run_id` column so the train/test split is by run, not by row (see the validation plan); it is dropped before training.

**Optional column (T1, #22):** `prompt_risk`, float 0-1, the highest Prompt Guard probability over this agent's messages in the window (absent or 0 when no message carried `text`). It is NOT in `FEATURE_COLUMNS` or `MODEL_INPUTS`; `score.py` reads it directly.

### B. `POST /score` (one row in, one verdict out)

```
POST /score
request:  { "action": { <feature row, columns 1-13, no label> } }
```
```json
{
  "agent_id": "agent-47",
  "ts": 1794636002.0,
  "risk": 91,
  "attack_type": "prompt_injection",
  "reason": "Touched a decoy credential and messaged 6 other agents in one minute (normal: 1).",
  "related_agents": [
    { "agent_id": "agent-20", "messages": 37, "verdict": "likely_infected" },
    { "agent_id": "agent-6",  "messages": 1,  "verdict": "likely_clean" }
  ],
  "recommended_action": "recommend_quarantine",
  "components": { "supervised": 88, "anomaly": 91, "fallback": false }
}
```

- `risk`: int 0-100, blended by `score.py`. `components` shows the two parts so a judge can see why.
- `reason`: one plain sentence from the top 2 feature contributions, with real numbers and units. No jargon.
- `related_agents`: everyone this agent messaged in the last 5 minutes, most messages first. `likely_infected` means 10+ messages from this agent AND the partner's own risk is 40+. Otherwise `likely_clean`.
- `recommended_action`: from the tier table.
- `components.fallback`: true when the frequency-count fallback produced the risk (models missing or erroring).
- `components.prompt` (**optional**, T1 #22): 0-100, present only when the row had `prompt_risk`. No new `attack_type`: when Prompt Guard drives the risk, it is `prompt_injection`.

### B2. `GET /agents` (the whole fleet; the dashboard and TUI poll it every second)

A superset of `src/app/sentinel/_data/live_sample.json`: every key already in that file keeps its name and type, so the TUI keeps working.

```json
{
  "updated": "2026-11-14T06:00:05Z",
  "mode": "live",
  "sentinel": {
    "patient_zero": "agent-47",
    "origin_ts": "2026-11-14T06:00:02Z",
    "containment": "recommended",
    "last_action": "recommend_quarantine",
    "fleet_risk_history": [4, 5, 6, 9, 14, 22, 38, 61, 77, 83, 80, 79]
  },
  "agents": [
    {
      "agent_id": "agent-47",
      "role": "coder",
      "risk": 91,
      "attack_type": "prompt_injection",
      "recommended_action": "recommend_quarantine",
      "reason": "Touched a decoy credential and messaged 6 other agents in one minute (normal: 1).",
      "position": { "x": 0.92, "y": 0.81 },
      "requests": 214,
      "systems_touched": ["decoy:aws-key", "agent-20", "repo:payments"],
      "first_flagged_ts": "2026-11-14T06:00:02Z",
      "related_agents": [ { "agent_id": "agent-20", "messages": 37, "verdict": "likely_infected" } ]
    }
  ],
  "edges": [ { "from": "agent-47", "to": "agent-20", "messages": 37 } ],
  "events": [
    "06:00:02  agent-47 touched decoy credential  (+40 risk)",
    "06:00:04  Sentinel: patient-zero = agent-47"
  ]
}
```

| field | rule |
|---|---|
| `mode` | `"live"` from the API, `"demo"` when read from `_data/` |
| `sentinel.patient_zero` | the first agent to reach risk 75 in this run; null until one does |
| `sentinel.origin_ts` | `ts` of patient zero's first event since its last tick that scored `monitor` (the time of origin; within one 2 s tick of the first bad action, PR #20) |
| `sentinel.containment` | `"none"` → `"recommended"` → `"approved"` or `"dismissed"` (after the human clicks) |
| `sentinel.fleet_risk_history` | max agent risk per tick, last 12 ticks, oldest first |
| `agents[].position` | x, y in 0..1 for the scatter, from `model_anomaly.project(row)`: a 2-D PCA fitted on clean baseline rows, so normal agents cluster and a rogue drifts out |
| `agents[].requests` | total events from this agent this run |
| `agents[].systems_touched` | distinct `resource` and `to_agent` values this run, newest first, max 8 |
| `agents[].first_flagged_ts` | first time this agent reached risk 75; null if never |
| `agents[].components` | optional (#22): this agent's latest score breakdown, same shape as contract B's `components` |
| `agents[].top_features` | optional (#22): `[{feature, contribution}]`, the classifier's per-row contributions (TreeSHAP-equivalent), largest first, max 5; powers the "why flagged" bars |
| `edges` | agent-to-agent message counts over the last 5 minutes |
| `events` | newest last, max 50, each `"HH:MM:SS  text"` |

**Demo mode:** `_data/live_sample.json` (one snapshot, upgraded to B2) and `_data/demo_timeline.json` = `{ "ticks": [FleetSnapshot, ...] }` (about 40 ticks, one per second: normal → attack → recommendation). The dashboard plays the timeline when `demoMode` is on. No network, no keys.

### Python module interfaces (so Noah, Brandon and Stephen build in parallel)

All under `src/app/sentinel/_py/`. Trained models are saved to `_py/artifacts/` (git-ignored). Each model module trains when run directly: `python model_anomaly.py && python model_supervised.py`. The overseer image runs both at build time.

| module | owner | public interface |
|---|---|---|
| `contract.py` | Alex | the constants above |
| `make_dataset.py` | Noah | CLI: writes `_py/data/actions.csv` (~1,000 rows, contract A columns + `label` + `run_id`) |
| `features.py` | Noah | `class RowBuilder: add(event: dict) -> None; rows(now: float) -> list[dict]`; `load_dataset(path) -> pd.DataFrame` |
| `model_supervised.py` | Noah | `train(df_train) -> None` (calls `model_anomaly.filter_train` first); `predict(row) -> {"attack_type": str, "p_attack": float, "top_features": [(name, contribution), ...]}`; `report(df_test) -> dict` (per-type precision/recall) |
| `model_anomaly.py` | Brandon | `filter_train(X_train) -> np.ndarray` (bool keep-mask; IsoForest #1, fit on the train split only); `fit_baseline(X_clean) -> None` (IsoForest #2 + PCA); `anomaly(row) -> float` (0-1); `project(row) -> tuple[float, float]` |
| `graph.py` | Brandon | `class Graph: add_message(src, dst, ts); related(agent_id, risks: dict) -> list[dict]; edges(window_s=300) -> list[dict]` |
| `score.py` | Brandon | `score(row: dict, graph: Graph) -> dict` (a contract B response); `fallback_score(row) -> int` |
| `api.py` | Stephen | FastAPI app: `POST /events`, `POST /score`, `GET /agents`, `GET /health`. With `SENTINEL_FAKE=1` it serves canned `_data/` responses, so nobody waits on the models |

---

## Architecture

```
 Docker swarm (local)                  Overseer container           Next.js dashboard
 ┌─────────────────────┐ POST /events  ┌──────────────────┐ GET /agents ┌────────────────┐
 │ agent-1 ... agent-8 │ ────────────► │ api.py (FastAPI) │ ◄────────── │ fleet scatter  │
 │ (scripted processes)│               │  features.py     │             │ patient zero   │
 │  share one LLM_URL  │               │  score.py        │             │ approve/dismiss│
 └─────────────────────┘               │   XGBoost        │             └──────┬─────────┘
         │ docker/trigger.sh agent-47  │   IsoForest x2   │                    │ Server Action
         └── replays prompt_injection  │   graph.py       │     Supabase audit_log (INSERT-only)
                                       └──────────────────┘     Discord webhook (alert)
```

- **Swarm:** 8 lightweight scripted agent processes (one script, `docker/agent/agent.py`, run in many containers). They replay dataset behaviour; at most one shared LLM service via `LLM_URL`, never one model per agent. `docker/trigger.sh agent-47` turns one agent rogue through a flag file on a shared volume. Builds with Docker, runs on Podman (`podman compose`). No Kubernetes.
- **Overseer:** one container running `api.py`. Detection is CPU-only: no GPU, no LLM at inference.
- **Detection:** IsoForest #1 cleans the training data (fit on the train split only, never test) → XGBoost learns known attacks (feature importance → the reason). IsoForest #2 + PCA, fit on the clean baseline, flags novel behaviour (`unknown`) and places the dots on the scatter. `score.py` blends both into 0-100. A frequency-count rule is the guaranteed fallback.
- **Response:** `_lib/response.ts` applies the tier table and a human clicks approve or dismiss. A Server Action writes the decision to the Supabase `audit_log` table (insert-only: no update or delete policy) and posts a Discord alert. No auto-enforcement, no counterattacks.

---

## Who owns what

| Member | Role | Files owned (no file appears twice) |
|---|---|---|
| Alex (CS) | Integrator | `src/app/sentinel/page.tsx`, `actions.ts`, `README.md`, `CHECKLIST.md`, `_lib/*`, `_data/*`, `_py/contract.py`, `_py/requirements.txt`, `_py/validate.py`, `docker/*`, `src/lib/tracks.ts` |
| Noah (AI) | Supervised + dataset | `_py/make_dataset.py`, `_py/features.py`, `_py/model_supervised.py`, `_py/data/*`, `_py/tests/test_features.py`, `_py/tests/test_supervised.py` |
| Brandon (AI) | Anomaly + scoring + graph | `_py/model_anomaly.py`, `_py/score.py`, `_py/graph.py`, `_py/tests/test_anomaly.py`, `_py/tests/test_score.py` |
| Stephen (CS) | API + dashboard | `_py/api.py`, `_py/tests/test_api.py`, `_components/*.tsx` |
| Codex | Ops TUI | `_tui/*` only |
| Gemini | Research + reviews | no files; posts `FINDING` and `REVIEW` |

---

## 3-minute demo script

Before judges arrive: `docker compose -f docker/compose.yml up -d` (swarm + overseer), `pnpm demo` on the laptop, browser on `/sentinel`, the TUI in a second window, the Discord channel on a phone. If Docker or Wi-Fi fails, set `NEXT_PUBLIC_DEMO_MODE=1` and the same script plays from `_data/demo_timeline.json`.

| time | on screen | say |
|---|---|---|
| 0:00-0:20 | Title on `/sentinel` | "Companies now run teams of AI agents that message each other. Today's security tools guard one agent from outsiders. When one agent in the team is hijacked, it infects its teammates, and nobody is watching for that. Sentinel watches the team." |
| 0:20-0:50 | 8 grey dots clustered in the scatter; headline "8 agents, 0 flagged"; audit log ticking | "Eight agents doing normal work: a researcher, an emailer, coders, analysts. Each dot is one agent's last minute of behaviour, and normal agents cluster together. Sentinel scores every agent 0 to 100 every 2 seconds, on a laptop CPU, with no AI model in the loop." |
| 0:50-1:30 | Run `docker/trigger.sh agent-47`. Its dot drifts out and turns red; the risk number climbs past 75. Patient-zero card: "agent-47, first seen 06:00:02, 214 requests, touched decoy:aws-key, repo:payments" | "I've just injected a malicious prompt into agent 47. Watch it drift away from the herd. It touched a decoy credential we planted and started messaging its teammates. Patient zero: agent 47, at 06:00:02, and here is exactly what it touched." |
| 1:30-2:10 | Related-agents panel: agent-20 (37 messages, likely infected) turns amber then red; agent-6 (1 message, likely clean) stays grey. Card: "Recommend quarantine: agent-47, agent-20" with plain reasons. Click **Approve**. Discord alert arrives; an audit row appears | "Sentinel traced the spread: 47 sent agent 20 thirty-seven messages, and 20 now behaves the same way. Agent 6 got one message and looks clean, so we don't punish it. Sentinel recommends; it never acts on its own. A human approves, and that decision goes into an audit log nobody can edit or delete." |
| 2:10-2:40 | Results panel: detection rate, false-quarantine rate, median containment seconds, with vs without Sentinel | "Over 20 runs: we caught X% of attacks, wrongly flagged Y% of clean agents, and recommended containment in a median of Z seconds. Without Sentinel, the attack reached N of 8 agents." |
| 2:40-3:00 | Limits card | "Honest limits: the anomaly model needs a clean baseline to learn from. The classifier only knows attacks we trained it on, which is why a second model looks for anything unusual. Tracing finds infrastructure, not people. That's why a human always decides." |

X, Y, Z and N come from `_py/validate.py` and are checked a second way (a hand count of one run's event log) before they go on screen.

---

## Validation plan

Script: `src/app/sentinel/_py/validate.py` (Alex). Output: `src/app/sentinel/_data/validation.json`, shown on the results panel.

**Runs.** 20 seeded runs per arm, 8 agents, 90 seconds each. In each run one random agent turns rogue at a random time between 20 s and 40 s and replays `prompt_injection`, which spreads to the peers it messages. Plus 5 runs with no attack, to measure false alarms on a fully clean fleet.

**Arms.**
1. **Without Sentinel:** the swarm runs and nothing watches. Measures how many agents are compromised at 90 s (the spread baseline).
2. **With Sentinel:** the same seeds, overseer on. A simulated human approves each recommendation 5 s after it appears (a stand-in for a person; we say so on the slide).
3. **Fallback only:** the same seeds, frequency-count rule only. Shows what the ML adds.

**Metrics (medians with the min-max range, never means).**

| metric | definition | target |
|---|---|---|
| Detection rate | % of runs where patient zero reaches `recommend_quarantine` or higher before the run ends | ≥ 90% |
| Time to detect | seconds from the first malicious event to the first recommendation of quarantine or higher | median ≤ 10 s |
| Containment speed | seconds from the first malicious event to the human-approved quarantine | median ≤ 15 s |
| Spread | agents compromised at 90 s, without vs with Sentinel (with: an approved agent stops sending) | with < without |
| False-quarantine rate | clean agent-runs that got `recommend_quarantine` or higher ÷ all clean agent-runs; attack runs and clean-only runs reported separately | ≤ 5%, reported however bad |
| Patient-zero accuracy | % of runs where `sentinel.patient_zero` is the agent we triggered | ≥ 90% |
| Per-type precision/recall | `model_supervised.report()` on the held-out test split, one row per `attack_type` | reported, no target |
| Novel-attack check | hold one attack type out of XGBoost training; % of its rows the blend still scores 40+ (via IsoForest #2) | reported, no target |

**Second, independent check.** For one run, count by hand from the raw `/events` log: the first malicious event time, the first recommendation time, and which agents received messages. These must match `validate.py` to the second.

**Leakage guard.** Split train and test by `run_id`, not by row, so windows from the same run never land on both sides. IsoForest #1 is fit on the train split only.

---

## Scope guardrails

- **Core demo = ONE attack (`prompt_injection`) spreading across the swarm.** Everything above is the must-have.
- **Stretch (only if time):** Markov-chain next-step prediction; human-gated retraining (unmatched behaviour → a pending queue a human approves before training, which prevents data poisoning).
- **Fallbacks:** the frequency-count detector if XGBoost misbehaves; demo mode (reads `_data/`, no network) if Docker or Supabase breaks; a backup video recorded by 2:30pm Saturday.
- **Dropped:** Vercel, Render, Raspberry Pis, Kubernetes, GPUs, paid APIs at demo time.

## Honest limits (say these out loud)

- Isolation Forest needs a clean baseline. If the swarm is already compromised when we fit it, it learns the attack as normal.
- XGBoost only recognises attack types it was trained on. Novel attacks rely on the anomaly model and come out as `unknown`.
- Attribution finds infrastructure (which agent, which resource), not people.
- Quarantine is a recommendation. Real enforcement needs kernel- or orchestrator-level access, which a responsible overseer should not take on its own.
- The training data is synthetic (see the dataset decision in Noah's issue).

---

## Stack

Next.js 16 dashboard (local, `pnpm demo`) · Python 3.11 + FastAPI · scikit-learn + XGBoost · Docker (OrbStack on Mac, Docker Desktop on Windows; Podman compatible) · Supabase for the audit log only (RLS on; demo mode works without it) · Discord webhook for alerts.
