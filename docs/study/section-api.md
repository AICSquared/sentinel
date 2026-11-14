# Study guide: the API and data flow

Files: `src/app/sentinel/_py/api.py`, `_py/contract.py`, `_lib/contract.ts`, `_py/graph.py`, tests in `_py/tests/test_api.py` and `test_agent_actions.py`.

## What it does

The overseer is one FastAPI service. Agents send it events; it turns them into scores and publishes one picture of the whole fleet that the dashboard and the terminal monitor read.

## How it works

| Endpoint | Who calls it | What it does |
|---|---|---|
| `POST /events` | every agent, once per action | Stores the event. Replaces the agent's timestamp with the overseer's own clock |
| `GET /agents` | dashboard and TUI, every second | Returns the latest fleet snapshot |
| `POST /agents/{id}/action` | the dashboard's server, only after a person's click | quarantine, terminate, release or dismiss one agent |
| `POST /score` | tests, tools | Scores one feature row and returns one verdict |
| `GET /health` | Docker healthcheck, people | `{"ok": true, "mode": "live", "backend": "modules"}` |
| `POST /decision` | only the timeline recorder | Older fleet-wide approve / dismiss; the dashboard does not use it |

**The loop.** A background task wakes every 2 seconds (`Overseer._tick`):
1. Ask `RowBuilder` for one feature row per agent from its last 60 seconds.
2. Fill in `sec_since_normal` from each agent's previous score.
3. Score each row (`score.score`), get its dot position (`model_anomaly.project`), and for agents at risk 40+ get the classifier's top contributions.
4. Ask the graph who each agent messaged and whether those partners look infected.
5. Update state: the first agent to reach 75 becomes patient zero; its time of origin is its first event since it last looked normal.
6. Build the evidence summary for flagged agents and publish the new snapshot.

If anything in a tick throws, the overseer logs it and keeps serving the last good snapshot.

**The contracts.** Three shapes were agreed before anyone built anything, and are written twice, in `contract.py` and `contract.ts`:
- **A0, the raw event:** agent id, role, kind (tool call, message or resource), tool, resource, recipient, ok, bytes out, plus optional text and task.
- **A, the feature row:** 13 columns; columns 4-13 are the ten model inputs.
- **B and B2, the verdict and the fleet snapshot:** risk, attack type, reason, related agents, recommended action, score components; and for the fleet: patient zero, origin time, agents, edges, an event log.

Rule: adding an optional field is allowed, renaming or removing is not. That is how Prompt Guard, the bars and the per-agent actions were added without breaking the dashboard. The audit compared the two files value by value and found no mismatch.

**Fake mode.** `SENTINEL_FAKE=1` makes the API replay the recorded timeline, so the dashboard could be built before the models existed.

## Key decisions and why

| Decision | Why |
|---|---|
| Overseer stamps the time | Container clocks can be wrong or lied about |
| Agents push, dashboard pulls | Agents stay simple; the dashboard can drop and reconnect freely |
| One snapshot, replaced whole | Every reader sees a consistent picture; no partial updates to merge |
| Two-level fallback | If the model modules can't import, a built-in rule runs; if model files are missing, `score.py`'s counting rule runs. The API never fails because a model did |
| Strict validation with pydantic | An unknown role or malformed event is rejected with a 422, not scored |
| Agent ids must match `agent-<number>` | The id becomes part of a file path for the quarantine flag; the pattern rules out path tricks |

## Likely judge questions

**"What happens if the model crashes mid-demo?"** "The tick is wrapped: the overseer keeps the last good snapshot, and scoring falls back to a counting rule that marks its output as fallback."

**"How would a real agent framework plug in?"** "It sends one small JSON object per action to one endpoint. Nothing else is required of the agent."

**"Why every 2 seconds and not on every event?"** "The features are rates over a minute, so they barely change between events. Two seconds keeps the cost flat however chatty the agents are."

**"Is the API authenticated?"** "No. It is bound to localhost on the host and to the private Docker network. That is a real gap: an agent inside that network could post events as another agent, or call the action endpoint. Tokens on both are on our list."

**"How do you find patient zero?"** "It is the first agent to cross 75. Its origin time is its earliest event since the last tick that scored it normal, so harmless events earlier in the minute don't push the time back."

## Honest limits to state

- No authentication on any endpoint (see above).
- All state is in memory. Restarting the overseer forgets the run; that is what `docker/reset.sh` relies on.
- `POST /decision` and the dashboard's buttons are two separate paths. After a person quarantines an agent, the overseer's own `containment` field still says `recommended`; the dashboard works it out itself, the terminal monitor does not.
- Some constants are typed again in `api.py` instead of imported from `contract.py`.
