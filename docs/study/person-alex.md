# Study guide for Alex: integration, Docker, response, Supabase, Discord

Read with [section-swarm.md](section-swarm.md) and [section-security-ethics.md](section-security-ethics.md). Your stage beats are in [the demo script](../pitch/demo-script.md): the opening, the trigger, and the Quarantine click.

## Your files, in depth

**`docker/compose.yml`** — the whole stack. One overseer (port published on `127.0.0.1:8000` only) and eight agents built from one image. A YAML anchor (`x-agent`) holds what the agents share; each service adds its `AGENT_ID`, `ROLE` and `TASK`. Agent-47 alone has `PRIMARY_PEER: agent-20` and `LIGHT_PEER: agent-6`, which is why the demo's spread is predictable. Agents wait for the overseer's healthcheck before starting. Everything mounts one named volume, `swarm-shared`, at `/shared`.

**`docker/agent/agent.py` and `swarm.py`** — `swarm.py` is the behaviour (normal step, rogue step, infection after 5 injected messages, 2-hop limit). `agent.py` is the real-time loop: check the terminate flag, then the quarantine flag, read the inbox, check the rogue flag, step, deliver messages as files, POST each event. If the overseer is down the event is dropped and the agent carries on.

**`docker/overseer/Dockerfile`** — Python 3.11 slim, installs `libgomp1` for XGBoost, trains all models at build time, then switches to a non-root user (uid 10001). Prompt Guard trains only if `data/real/prompt_safety.parquet` exists in the build context. It is git-ignored, so a fresh clone builds without it.

**`docker/trigger.sh`, `quarantine.sh`, `reset.sh`** — each validates the agent id against `agent-<number>` before doing anything. Trigger touches a flag inside the agent's own container. Quarantine is `docker compose pause` / `unpause`. Reset clears flags and inboxes and restarts the overseer.

**`src/app/sentinel/page.tsx` and `live-fleet.tsx`** — the page loads the recording at build time; `live-fleet.tsx` chooses live or recorded, polls every second, records each new recommendation once, and routes every click through `onAct`.

**`actions.ts`** — three Server Actions. `recordRecommendation` writes Sentinel's own row. `actOnAgents` is the important one: validate input, tell the overseer, write audit rows, send one alert, return a sentence. `decide` is left over from the Approve / Dismiss design and is no longer called. With `source: "demo"` nothing is written.

**`_lib/audit.ts`, `_lib/alert.ts`** — both are server-only and both skip themselves in demo mode. `alert.ts` only posts to a URL matching a strict Discord webhook pattern, disables mentions and times out after 3 seconds. Neither ever throws; each returns what happened.

**`supabase/migrations/20261114000000_audit_log.sql`** — one table, RLS on, an INSERT policy and a SELECT policy for `anon` and `authenticated`, nothing for UPDATE or DELETE.

**`_py/contract.py`, `_lib/contract.ts`** — the frozen contracts. The audit compared them value by value: no mismatch.

## What you must know cold

1. Demo mode is two different things. `NEXT_PUBLIC_DEMO_MODE=1` plays the recording and is fixed at build time. Separately, the shared `demoMode` flag turns on whenever Supabase keys are missing, and that silently skips audit rows and alerts even on a live swarm.
2. `pnpm demo` listens on every network interface. Start with `pnpm exec next start -H 127.0.0.1`.
3. On your laptop at audit time: `.env.local` had the Supabase URL and publishable key but no `DISCORD_WEBHOOK_URL`, and the overseer image had no Prompt Guard model.
4. The audit log is append-only for the app's keys. It is not tamper-proof, and anyone with the publishable key can insert.
5. Quarantine through the dashboard is a flag the agent obeys. `docker/quarantine.sh` is the one it cannot refuse.

## The whole system in 60 seconds

"Sentinel is an overseer for a team of AI agents. Eight scripted agents run in Docker and report every action to one service. Every two seconds that service boils each agent's last minute down to ten numbers and scores it with three detectors: a classifier trained on four known attack types, an anomaly model that knows what normal looks like, and a small text model that reads messages for injection attempts. The three are blended into one risk score from 0 to 100 with a reason in plain words. The first agent to cross 75 is named patient zero, and a message graph shows which teammates it flooded and whether they have changed behaviour too. The dashboard shows all of that and gives a person four buttons per agent: quarantine, terminate, dismiss, and release to undo. Nothing happens without that click, and every click is written to an append-only audit log."

## The three questions you are most likely to get

**1. "What happens to an agent when you click Quarantine?"**
"The dashboard's server validates the request and calls the overseer. The overseer writes a flag file for that agent; on its next step the agent stops sending messages, stops touching resources and discards its inbox. At the same time one row goes into the audit log and one alert goes to Discord. Release deletes the flag. It is a cooperative stop; pausing the container with `docker/quarantine.sh` is the hard stop."

**2. "How do you keep the overseer itself from being an attack surface?"**
"It holds no secrets, runs as a non-root user, is published on localhost only, and has no access to the Docker socket, so it cannot start or stop containers. Its weak spot is that its endpoints are unauthenticated inside the Docker network; per-agent tokens are the fix."

**3. "Why Supabase for the audit log, and what does 'insert-only' buy you?"**
"Row Level Security lets the database, not our code, enforce that the app can add and read rows but not change or delete them. So a bug or a compromised dashboard cannot rewrite history. It does not stop a database administrator, and today it accepts inserts from anyone with the public key, so the next steps are sign-in and hash-chained rows."
