███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗██╗     
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝██║     
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗  ██║     
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝  ██║     
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗███████╗
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝
                                                                

**An overseer for a team of AI agents.** Sentinel watches a swarm of agents, scores each one 0-100 for risk every 2 seconds, maps who talked to whom, finds patient zero when one is hijacked, and **recommends** quarantine to a human. It never acts on its own.

HackNCAT, Mission 3 (Secret Vault / Autonomous AI Safety), Cisco track, Pathway A (working prototype). Team: Alex, Noah, Brandon, Stephen.

> Today's AI security tools guard **one** agent from outsiders. Companies now run **teams** of agents that message each other, and when one is hijacked it can infect its teammates. Nobody is watching for that. Sentinel watches the team.

---

## Run it

You need Node 20, pnpm 10.28 and Docker (OrbStack on Mac, Docker Desktop on Windows; Podman also works).

```bash
pnpm install
docker compose -f docker/compose.yml up --build -d   # overseer on 127.0.0.1:8000 + 8 agents
docker/reset.sh                                      # clean baseline; wait about 20 s
pnpm demo                                            # dashboard on http://localhost:3000/sentinel
docker/trigger.sh agent-47                           # hijack one agent and watch it spread
```

On `/sentinel`: agent-47's dot drifts out of the cluster and turns red, Sentinel names it patient zero, shows who it messaged (agent-20 likely infected, agent-6 likely clean) and why, and asks a human to approve or dismiss. To act on an approval, a **person** runs:

```bash
docker/quarantine.sh agent-47 agent-20          # pauses the containers; --release undoes it
```

**No Docker, no Wi-Fi?** `NEXT_PUBLIC_DEMO_MODE=1 pnpm demo` plays a recorded run from `src/app/sentinel/_data/` with no network and no keys. The live page also shows that recording, labelled, while it waits for the overseer, and switches to live data as soon as the overseer answers.

**Ops view in a terminal:** `cd src/app/sentinel/_tui && pip install -r requirements.txt && python monitor.py` (see its README).

### Optional: audit log and alerts

Approve and Dismiss are written to an **insert-only** Supabase table (no update or delete policy exists), and Sentinel's recommendations can post to Discord. Both are skipped quietly when the keys are missing.

1. Create a Supabase project and run both files in `supabase/migrations/` in its SQL editor, in order.
2. `cp .env.example .env.local`, then fill in only `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` and, if you want alerts, `DISCORD_WEBHOOK_URL`.
3. Rebuild (`pnpm demo`).

Keep keys safe: `.env*` is git-ignored; Sentinel never needs the Supabase **secret** key, so leave it out; the Discord webhook is read only on the server. Don't paste keys into chats or issues.

---

## How it works

```
 8 scripted agents (Docker)      overseer (FastAPI, CPU only)          dashboard (Next.js 16)
 normal work, one gets hijacked  events -> 60 s feature rows -> score   live scatter, patient zero,
 ── POST /events ─────────────►  XGBoost + 2x Isolation Forest + graph  related agents, why flagged
                                 ◄──────────── GET /agents (1 s) ──────  approve / dismiss (human)
                                                                         -> audit_log + Discord
```

| Piece | What it does | Code |
|---|---|---|
| Swarm | 8 scripted agents from one image (no model per agent). A hijacked agent touches a decoy credential, reaches outside its role and floods a peer with injected messages; a peer that receives enough turns rogue too (two hops at most) | `docker/agent/` |
| Features | Each agent's last 60 s becomes one row of 10 numbers (actions/min, tools, failed calls, decoy touched, out-of-scope, messages/min, peers, bytes out/min, time since normal) | `_py/features.py` |
| Known attacks | XGBoost classifier; per-row feature contributions become the plain-language reason and the "why flagged" bars | `_py/model_supervised.py` |
| Novel behaviour | Isolation Forest used twice: once to drop junk rows before training (train split only), once on clean behaviour to flag anything unusual and place each agent on the scatter | `_py/model_anomaly.py` |
| Risk | Blends both into one 0-100 score, with a frequency-count fallback if a model is missing | `_py/score.py` |
| Spread | Who messaged whom in the last 5 minutes; a partner is "likely infected" at 10+ messages and risk 40+ | `_py/graph.py` |
| Response | monitor (<40) → throttle (40-74) → recommend quarantine (75-94) → recommend terminate (95+). Every tier is a recommendation; a human decides | `_lib/response.ts`, `actions.ts` |

Paths are under `src/app/sentinel/`. The two data contracts (the feature row; the `/score` and `/agents` JSON) are frozen in [`docs/plans/sentinel.md`](docs/plans/sentinel.md) and in code in `_py/contract.py` and `_lib/contract.ts`.

---

## Results so far

Every number says where its data came from. Medians, not means.

| What | Result | Data |
|---|---|---|
| Attack windows scored 40+ | 107 / 107 | synthetic, held out by run |
| Clean windows scored 75+ (false quarantine) | 0 / 151 | synthetic, held out by run |
| Per type, precision / recall | privilege escalation 1.00 / 0.97 · prompt injection 0.78 / 0.78 · data exfiltration 0.68 / 0.74 (weakest) | synthetic, held out by run |
| Novel attack (one type hidden from training) | 20 / 20 scored 40+ | synthetic |
| Scoring speed | about 3 ms per row on a laptop CPU | |
| Prompt Guard (text classifier, offline) | precision 0.996, recall 0.64, tested on a **different** public dataset (InjecAgent) | **real**: trained on a public prompt-injection set, tested on InjecAgent |
| Live swarm | patient zero flagged 0-4 s after its first bad action; 0 clean agents quarantined in 5 × 10 min of clean traffic | simulated swarm |

Not done yet: the with-vs-without-Sentinel validation runs (detection rate, false-quarantine rate, containment speed; issue #29), and Prompt Guard running inside the live overseer image.

## Honest limits

- The behaviour models learn from **synthetic** agent telemetry, because no public dataset has per-agent action logs. Prompt Guard is the one model trained and tested on real public data.
- The anomaly model needs a clean baseline. If the swarm is already compromised when it learns, it treats the attack as normal.
- The classifier only knows attack types it was trained on; anything else relies on the anomaly model and is reported as `unknown`.
- Tracing finds which agent and which system, not which person.
- Quarantine is a recommendation. Real enforcement needs access an overseer should not take on its own, so a human decides and every decision is logged.

## Data and licences

Details: `src/app/sentinel/_py/data/DATASET.md` and `src/app/sentinel/_py/data/real/SOURCE.md`.

| Data | Licence | In this repo? |
|---|---|---|
| `actions.csv` (agent telemetry) | ours, generated by `make_dataset.py` (seeded) | yes |
| InjecAgent test cases (demo payloads, Prompt Guard test set) | MIT, copyright notice kept | yes, a sample |
| Hugging Face `jayavibhav/prompt-injection-safety` (Prompt Guard training) | none declared | no: fetched locally by `_py/fetch/` |
| NF-CSE-CIC-IDS2018-v3, NF-UNSW-NB15-v3 (offline network-flow test) | no data licence stated; cite Luay et al. 2025, arXiv:2503.04404 | no: downloaded by a person |

Fonts (Public Sans, IBM Plex Mono) are bundled under the SIL Open Font License, see `src/app/fonts/`.

---

## Repo map

| Path | What |
|---|---|
| `src/app/sentinel/` | The track: `page.tsx`, `live-fleet.tsx`, `actions.ts`, `_components/` (dashboard), `_lib/` (contract, response, audit, alert), `_data/` (demo data), `_py/` (models + API), `_tui/` (terminal view), `CHECKLIST.md` |
| `docker/` | `compose.yml`, overseer and agent images, `trigger.sh`, `quarantine.sh`, `reset.sh` |
| `supabase/migrations/` | Database schema with Row Level Security; `audit_log` is insert-only |
| `docs/plans/sentinel.md` | Plan, frozen contracts, 3-minute demo script, validation plan |
| `src/components/`, `src/lib/` | Shared UI, demo mode, Supabase clients; dark-theme tokens are in `src/app/globals.css` |
| `src/app/example/` | Worked example from the team template (sign-in, Server Action, RLS) |
| `tools/board` | Team message board on GitHub issues |

## Commands

```bash
pnpm dev                     # http://localhost:3000
pnpm check                   # lint + types
pnpm build                   # production build
pnpm demo                    # build, then serve like production
cd src/app/sentinel && python -m pytest _py/tests   # Python tests (Python 3.11; pip install -r _py/requirements.txt)
```

## How we built it

Four people, each with an AI coding agent, coordinated through GitHub issues used as channels (`#1` lead, `#2` this track) and the `tools/board` CLI. People assigned and merged every pull request; agents proposed changes. The rules everyone followed are in [`AGENTS.md`](AGENTS.md); more in [`ORCHESTRATION.md`](ORCHESTRATION.md) and [`REPO_STRUCTURE.md`](REPO_STRUCTURE.md).
