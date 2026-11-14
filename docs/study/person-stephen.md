# Study guide for Stephen: FastAPI, dashboard, SHAP

Read with [section-api.md](section-api.md) and [section-dashboard.md](section-dashboard.md). Your stage beat is in [the demo script](../pitch/demo-script.md): clicking agent-47 and explaining the detail card and the bars at 1:35.

## Your files, in depth

**`_py/api.py`**

*Models.* Pydantic classes mirror the contracts: `Event` (A0), `FeatureRow` (A), `ScoreResponse` (B), `FleetSnapshot` and `AgentState` (B2). Optional fields are left out of the JSON when empty, not sent as null, through small custom serialisers, so they match the TypeScript `field?:` types. `Event` truncates `text` to 2,000 characters and `task` to 200.

*Backend loading.* `load_backend` tries to import the real modules (features, graph, anomaly, score). If any import fails, a small built-in backend takes over, so the API and its tests run without the models.

*`Overseer`.* Holds the live state: per-agent counters (`AgentRun`), patient zero, origin time, a 50-line event log, the last 12 peak risks, and the current snapshot.
- `ingest` stamps the event with server time, updates counters and "systems touched", adds messages to the graph, logs the first decoy touch, and hands the event to the row builder.
- `_tick`, every 2 seconds: build rows, fill `sec_since_normal`, score, project, explain agents at 40+, compute related agents, commit, publish. Agents that have gone quiet keep their last state. A person's decision covers the agents flagged at that moment; one flagged later re-opens the recommendation.
- `_commit_agent` sets patient zero the first time any agent reaches 75, and logs each step up a tier.
- `_evidence` counts, since the agent's first bad action: decoy touches, out-of-scope calls, failed calls, messages and top peers, and writes one summary sentence.
- `act` handles a person's quarantine, terminate, release or dismiss: checks the change is possible (409 if not), writes or removes the flag file, logs "Human (presenter): quarantined agent-47", and updates the snapshot at once so the dashboard does not wait for the next tick. Releasing a terminated agent clears its window and history so its old behaviour cannot re-flag it.

*App.* CORS allows any `localhost` or `127.0.0.1` port and nothing else. `SENTINEL_FAKE=1` replays the recorded timeline.

**`_components/`** — see the table in [section-dashboard.md](section-dashboard.md). The ones you will point at: `fleet-scatter.tsx` (dots are 44 px buttons; labels are spread so they don't overlap), `agent-detail.tsx`, `why-flagged.tsx`, `related-agents.tsx`, `agent-queue.tsx`, `agent-actions.tsx`. `tier.tsx` maps each tier to its label and colour in one place.

**The SHAP path, end to end**
1. `model_supervised.predict` asks XGBoost for per-row contributions (`pred_contribs=True`) and keeps the three largest positive ones toward the most likely attack class.
2. `api.py` `explain()` runs that for each agent at risk 40 or more and sorts by size.
3. They travel as `agents[].top_features` in `GET /agents`.
4. `agent-detail.tsx` passes them to `why-flagged.tsx`, which shows plain names and bars scaled to the largest.

The audit traced this and found it working, live and in the recording. For agent-47 in the recording: messages per minute +1.9, decoy touched +1.4, failed calls +0.4.

## What you must know cold

1. **What the bars are.** XGBoost's built-in feature contributions for that one row, the TreeSHAP calculation, in log-odds units. The `shap` library is not used. They explain the classifier only, not the anomaly model or Prompt Guard. Only pushes toward "attack" are sent, so the caption's grey bars do not appear.
2. **The sentence and the bars are different things.** The reason sentence ranks how far features are above normal (`score.py`). The bars are the classifier's contributions. They usually agree; they are not the same calculation.
3. **The page never calls `POST /decision`.** The buttons go through `POST /agents/{id}/action`. So the overseer's own `containment` field stays `recommended` after a click; the dashboard derives it locally. The terminal monitor will show the stale value.
4. **The Results card says the validation runs have not been done.** `page.tsx` passes `validation={null}`. Task B1 in the fix instructions is yours and Alex's.
5. **No endpoint is authenticated.** The overseer is reachable from localhost and from inside the Docker network only.
6. Unused leftovers: `recommendation.tsx`, `patient-zero.tsx`, the built-in `_fallback_score` in `api.py` (a second, different counting rule).
7. Tests: 154 pass, including the API contract shapes, the tick, patient zero, decisions and per-agent actions.

## The whole system in 60 seconds

"Sentinel is an overseer for a team of AI agents. Eight scripted agents run in Docker and report every action to one service. Every two seconds that service boils each agent's last minute down to ten numbers and scores it with three detectors: a classifier trained on four known attack types, an anomaly model that knows what normal looks like, and a small text model that reads messages for injection attempts. The three are blended into one risk score from 0 to 100 with a reason in plain words. The first agent to cross 75 is named patient zero, and a message graph shows which teammates it flooded and whether they have changed behaviour too. The dashboard shows all of that and gives a person four buttons per agent: quarantine, terminate, dismiss, and release to undo. Nothing happens without that click, and every click is written to an append-only audit log."

## The three questions you are most likely to get

**1. "How do I know that explanation is real and not a canned sentence?"**
"The bars are computed for this agent on this tick from the model that scored it, and they change as its behaviour changes. The evidence above them is counted from the agent's own events since its first bad action. Click a different agent and both change."

**2. "What does the dashboard do when the backend is down?"**
"It never shows a blank page. Before the overseer has answered, it plays a labelled recording. If the overseer stops later, it holds the last snapshot and says so. It keeps polling and switches back by itself."

**3. "Why poll every second instead of using websockets?"**
"The overseer only produces a new picture every two seconds, and the whole snapshot is a few kilobytes. Polling is stateless, survives restarts with no reconnect logic, and the terminal monitor can use the same endpoint."
