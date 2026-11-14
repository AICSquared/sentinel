# Study guide: the dashboard

Files: `src/app/sentinel/page.tsx`, `live-fleet.tsx`, `actions.ts`, `_components/*.tsx`, `_lib/response.ts`, `_data/demo_timeline.json`.

## What it does

One page, `/sentinel`, that shows the fleet, names patient zero, explains each flagged agent and gives a person the buttons. It is the only place a decision is made.

## How it works

`page.tsx` is a server component that loads the recorded timeline and hands it to `live-fleet.tsx`, a client component that owns everything else.

**What is on the page, top to bottom**

| Component | Shows |
|---|---|
| `fleet-headline.tsx` | One sentence ("8 agents watched, 2 flagged. Patient zero is agent-47.") and four numbers: agents watched, agents flagged, peak risk, time to detect. These are the only numbers that animate |
| `fleet-scatter.tsx` | One dot per agent, positioned by the anomaly model. Normal agents cluster; a rogue drifts out. Colour is the tier. Each dot is a button |
| `agent-detail.tsx` | The selected agent: its assigned task, what triggered Sentinel, counts (decoy touches, out-of-scope calls, failed calls, messages), systems touched, the bars, the buttons |
| `why-flagged.tsx` | Up to three bars: the features that pushed the classifier hardest for this agent, in plain names |
| `related-agents.tsx` | "Spread": who this agent messaged in 5 minutes, message counts, likely infected or likely clean |
| `agent-queue.tsx` | "Sentinel recommends: ...": one row per flagged agent with its reason and buttons; tick several to act on a group |
| `event-log.tsx` | "What Sentinel saw": the overseer's last 12 log lines, including "Human (presenter): quarantined agent-47" |
| `results-panel.tsx` | Results. Today it says the validation runs have not been done (audit finding B1) |
| `limits-card.tsx` | "What Sentinel cannot do" |

**Live versus recorded.** The page always starts on the recording. Unless `NEXT_PUBLIC_DEMO_MODE=1`, it also polls `GET /agents` every second with a 2-second timeout. The first time the overseer answers, the page clears anything clicked so far and switches to live. If the overseer goes quiet later, the page keeps the last snapshot and says so. The status line under the headline always states which of the three you are looking at. In demo mode the page makes no network calls at all.

**The bars.** `agents[].top_features` arrives with each snapshot as `[{feature, contribution}]`. The component maps column names to plain words ("Messages to other agents per minute") and scales each bar against the largest one for that agent. They come from XGBoost's own per-row contributions.

**The click.** A button calls `onAct` in `live-fleet.tsx`, which calls the Server Action `actOnAgents` in `actions.ts`. On the server it:
1. Checks every field of what the browser sent (agent id pattern, known enums, risk clamped to 0-100, reason trimmed).
2. Tells the overseer (`POST /agents/{id}/action`), which writes the flag the agent obeys.
3. Inserts one audit row per agent, including what the overseer answered.
4. Posts one Discord alert.
5. Returns a sentence the page shows, such as "Quarantined agent-47. Logged 1 row."

When the recording is playing, step 1 happens and nothing else: the change is shown on screen only, and the page says so.

Separately, the first time the page sees a new recommendation in a live run, it records it (`recordRecommendation`) as a row with `decided_by: "sentinel"`.

## Key decisions and why

| Decision | Why |
|---|---|
| Start on the recording, switch to live | A restart of the overseer on stage never leaves a blank page |
| Recorded clicks write nothing | Recorded data must never create audit rows that look like real decisions |
| Server Action, not a browser call to the overseer | The browser never needs the overseer's address for actions, and the audit write happens in the same trusted step |
| Per-agent buttons | A person can stop one agent and spare another; all-or-nothing approval was too blunt |
| Words next to every colour | Colour is never the only signal; every control is a real button at least 44 px tall |

## Likely judge questions

**"How does a person know why an agent was flagged?"** "Three ways on one card: a plain sentence, the counted evidence since its first bad action, and bars showing what moved the model."

**"Are those SHAP values?"** "They are XGBoost's per-row feature contributions, which is the TreeSHAP calculation. They explain the classifier, not the other two detectors."

**"What if the operator clicks the wrong agent?"** "Release undoes a quarantine. Undoing a terminate restarts the agent clean. Both are logged."

**"What does the page do with no internet?"** "The dashboard and overseer are both on this laptop. Only the audit log and the alert need the network, and the click reports plainly if either was skipped."

**"Who is allowed to click?"** "Today, whoever can reach the page, so we bind it to localhost. A sign-in check in the Server Action is the next change; the audit row already records a user id when someone is signed in."

## Honest limits to state

- There is no audit-log view in the dashboard; show the Supabase table.
- No sign-in is required to act, and `pnpm demo` listens on every network interface unless started with `-H 127.0.0.1`.
- The Results card is empty until validation numbers are wired in.
- The bars only ever show pushes toward "attack", although the caption mentions grey bars.
- Without Supabase keys the page reports "Demo mode: nothing written to the audit log", even on a live swarm.
- Leftover, unused files: `recommendation.tsx`, `patient-zero.tsx`, and `decide()` in `actions.ts`.
