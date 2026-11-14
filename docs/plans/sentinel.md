# Sentinel — plan

An immune system for a team of AI agents. One overseer watches a swarm, scores each agent 0-100 for risk, maps who talked to whom, and recommends (never enforces) quarantine or termination to a human.

Track: Mission 3 (Secret Vault / Autonomous AI Safety), Cisco. Pathway A (working prototype). Team of 4.

---

## The two contracts — freeze these in the first 30 minutes

Nothing else starts until these are agreed. Write them here, then everyone builds against them in parallel.

### A. The feature row (what the models consume)
One agent action = one row. Columns (starting set; Noah and Brandon tune together):

| column | type | meaning |
|---|---|---|
| agent_id | string | which agent |
| ts | float | unix seconds |
| actions_per_min | float | rate of actions this window |
| distinct_tools_used | int | tools called this session |
| distinct_tools_baseline | float | this agent's normal |
| touched_decoy | 0/1 | hit a planted honeytoken |
| out_of_scope_resource | 0/1 | reached something outside its role |
| msgs_to_agents_per_min | float | agent-to-agent message rate |
| sec_since_normal | float | time since last normal action |
| label | string | "clean" or attack type (training only) |

### B. The /score contract (what the dashboard renders)
```
POST /score
request:  { "action": { ...one feature row without label... } }
response: {
  "agent_id": "agent-47",
  "risk": 0-100,
  "attack_type": "tool_misuse" | "prompt_injection" | ... | "unknown" | "clean",
  "reason": "plain-language why, from feature importance",
  "related_agents": [
    { "agent_id": "agent-20", "messages": 37, "verdict": "likely_infected" },
    { "agent_id": "agent-6",  "messages": 1,  "verdict": "likely_clean" }
  ],
  "recommended_action": "monitor" | "throttle" | "recommend_quarantine" | "recommend_terminate"
}
```
Stephen builds the dashboard against a FAKE /score returning canned data, so he never waits on the models.

---

## Architecture

```
 Docker swarm (local)                 Python detector            Next.js dashboard
 ┌─────────────────────┐   events     ┌──────────────┐  /score   ┌────────────────┐
 │ agent-1 ... agent-N │ ───────────► │ FastAPI api  │ ◄──────── │ fleet graph    │
 │ (scripted processes)│              │  features    │           │ risk + reasons │
 │ + sentinel overseer │              │  XGBoost     │           │ human approve  │
 └─────────────────────┘              │  IsoForest   │           │ audit log      │
         │ one rogue                  │  risk 0-100  │           └──────┬─────────┘
         └── replays an attack        └──────────────┘                  │
                                                                 Supabase (audit log, RLS)
                                                                 Discord webhook (alerts)
```

- **Swarm:** a few lightweight agent *processes* in Docker containers. Agents are scripted to emit actions/messages (replay dataset behaviors); at most one shared LLM call, never one model per agent. One container is the Sentinel overseer. Build with Docker; images also run on Podman (what Cisco uses). No Kubernetes.
- **Detector (Python, CPU, no GPU, no LLM at inference):** XGBoost/LightGBM (known attacks, feature-importance explainability) + Isolation Forest (novel behavior), combined into one 0-100 risk. Frequency-count detector kept as a guaranteed fallback.
- **Dashboard:** Next.js template, src/app/sentinel/. Live Isolation-Forest-style scatter: agents as dots, the rogue drifting out and turning red. Patient-zero call-out, time of origin, requests made, systems touched.
- **Response (tiered, human-gated):** monitor → throttle → recommend_quarantine → recommend_terminate. Always a recommendation to a human. Discord alert. Full audit log to Supabase. No auto-enforcement, no counterattacks. (A Cisco mentor validated recommend-only as "responsible" since real quarantine needs kernel access.)

---

## Who owns what

| Member | Role | Files owned |
|---|---|---|
| Alex (CS) | Integrator + orchestrator | src/app/sentinel/page.tsx, docker/ swarm setup, src/app/sentinel/_lib/response.ts (tiered policy + human approval), Discord alert |
| Noah (AI) | Supervised detection | src/app/sentinel/_py/features.py, _py/model_supervised.py |
| Brandon (AI) | Anomaly detection + scoring | src/app/sentinel/_py/model_anomaly.py, _py/score.py |
| Stephen (CS) | API + dashboard | src/app/sentinel/_py/api.py, src/app/sentinel/_components/*.tsx |

Dataset (~1,000 labeled actions, LLM-generated) is a shared first-hour task; Noah owns keeping it clean. Supabase audit table + RLS: Alex.

---

## 3-minute demo script

1. **(20s) The problem.** "Cisco runs 7 internal multi-agent systems. Banks run them. The average company runs 12 agents and half of these projects fail. When one agent is hijacked, it infects the others. Nobody protects the team from itself."
2. **(30s) Normal.** Show the swarm running green on the dashboard. Agents clustered in the Isolation Forest scatter. Audit log ticking.
3. **(40s) Attack.** Trigger the rogue agent (replays one attack method). On screen: its dot drifts out and turns red. Risk climbs past 80. "Patient zero detected: agent-47."
4. **(40s) Trace + recommend.** Show related agents: "agent-47 messaged agent-20 37 times (likely infected) and agent-6 once (likely clean)." Sentinel recommends quarantine of 47 and 20, with reasons. A human clicks approve.
5. **(30s) Numbers + honesty.** "Detection rate X%, false-quarantine rate Y%, contained in Z seconds. Limits: Isolation Forest needs a clean baseline; the classifier only knows attacks we trained on; attribution finds infrastructure, not people. That's why a human always decides."

---

## Validation plan

Run the swarm with and without Sentinel, N trials each:
- **Detection rate:** % of attacks flagged before they complete.
- **False-quarantine rate:** % of clean agents recommended for quarantine (report this honestly — it's the ethics-critical number).
- **Containment speed:** seconds from first malicious action to recommendation.
- **Per-attack-type precision/recall**, not just overall accuracy.
Report medians, not means (ignore outliers).

---

## Scope guardrails

- **Core demo = ONE attack method spreading across the swarm.** Everything above is the must-have.
- **Stretch (only if time):** Markov-chain next-step prediction; human-gated retraining (unmatched behavior → pending queue a human approves before training, which prevents data poisoning).
- **Fallbacks:** frequency-count detector if XGBoost misbehaves; demo mode (reads _data/, no network) if Docker or Supabase breaks; backup video recorded by 2:30pm Saturday.
- **Dropped:** Vercel, Render, Raspberry Pis, Kubernetes.

---

## Stack

Next.js 16 dashboard (run locally, `pnpm demo`) · Python + FastAPI · scikit-learn + XGBoost/LightGBM · Docker (OrbStack on Mac) · SQLite/JSON logs · Supabase for the audit log only (RLS on; demo mode works without it) · Discord webhook for alerts.
