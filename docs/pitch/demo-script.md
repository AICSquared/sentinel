# Sentinel: 3-minute live demo script

Written from the code on `origin/main` (`18333e3`). It replaces the older script table in `docs/plans/sentinel.md`, which describes Approve / Dismiss buttons that no longer exist. Numbers come from [the audit](../review/AUDIT.md#1f-numbers-you-can-quote-and-where-each-comes-from).

**What differs from the plan, so nobody is surprised on stage**
- There is no "Approve" button. The buttons are **Quarantine**, **Terminate**, **Dismiss**, and **Release** (the undo), one set per agent.
- Patient zero jumps straight to the "Terminate?" tier (risk 96+), not "Quarantine?".
- The spread is 47 -> 20 -> one more agent (agent-53 in the recording, sometimes agent-12 live). Agent-6 gets one message and stays "likely clean".
- The dashboard has no audit-log view. The audit rows are shown in the Supabase table editor, in a second browser tab.

## Before the judges arrive (5 minutes)

Do the "Before presenting" list in [FIX-INSTRUCTIONS.md](../review/FIX-INSTRUCTIONS.md). Then:

| Window | State |
|---|---|
| Browser tab 1 | `http://localhost:3000/sentinel`, status line reads "Live from the overseer, updated every second." Scrolled to the top |
| Browser tab 2 | Supabase table editor on `audit_log`, newest first |
| Terminal | `docker/trigger.sh agent-47` typed, not yet run |
| Phone (optional) | Discord channel, only if the webhook was tested |

Run `docker/reset.sh` at least 30 seconds, and no more than a few minutes, before you start. The headline must read "8 agents watched, none flagged". If any dot is amber, reset again.

Do not scroll down to the "Results" card unless task B1 has landed. Today it says the validation runs have not been done.

## The script

Times are cumulative. The attack is triggered at 0:40; agent-47 turns red within about 4 seconds, agent-20 about 7 seconds after that, and a third agent about 30 seconds after the trigger.

| Time | Who | Do | Say |
|---|---|---|---|
| 0:00-0:25 | **Alex** | Tab 1, top of page. Point at the headline | "Companies now run teams of AI agents that message each other. Today's security tools guard one agent from outsiders. But when one agent in a team is hijacked, it can pass the attack to its teammates, and nothing is watching for that. Sentinel watches the team, and it asks a person before anything is done." |
| 0:25-0:40 | **Noah** | Point at the scatter: 8 grey dots close together | "Eight agents doing normal work. Each dot is one agent's last minute, boiled down to ten numbers: how fast it acts, which tools it uses, who it messages, how much data it sends out. Agents behaving normally sit together. Every two seconds, each one gets a risk score from 0 to 100, on this laptop's CPU." |
| 0:40-1:05 | **Alex** | Run `docker/trigger.sh agent-47`. Watch the scatter. When the dot turns red, point at the headline ("Patient zero is agent-47") and the "Time to detect" number | "I've just hijacked agent 47 with a prompt injection taken from a public benchmark. Watch it leave the group. ... There. It touched a decoy credential we planted, which no honest agent has a reason to touch. Sentinel names it patient zero, and shows how many seconds passed between its first bad action and the flag." |
| 1:05-1:35 | **Brandon** | Point at the "Spread" card on the right: agent-20 with a long red bar, agent-6 with one message | "Sentinel also maps who talked to whom. Agent 47 flooded agent 20 with messages, and agent 20 has now started behaving the same way, so it's marked likely infected. Agent 6 received one message and is behaving normally, so it's marked likely clean and left alone. We only flag an agent when it both received the messages and changed its behaviour." |
| 1:35-2:05 | **Stephen** | Click agent-47's dot. In the detail card, point at "What triggered Sentinel", then the "Why it was flagged" bars | "Click any agent and Sentinel shows its work. Here is what agent 47 was assigned to do, and here is what it actually did: decoy touches, calls outside its role, messages sent. These bars come from the classifier itself: for this agent, the message burst and the decoy pushed the score up the most. Nobody has to take the number on trust." |
| 2:05-2:35 | **Alex** | Scroll to the queue ("Sentinel recommends: ..."). Click **Quarantine** on agent-47, then on agent-20. Point at the "Quarantined by you" tag and the new line in "What Sentinel saw". Switch to tab 2 and point at the new rows. Switch back | "Sentinel recommends; it never acts on its own. It suggests terminating agent 47. I'm choosing quarantine instead, because it can be undone: Release puts the agent back. That was a person's click, and each click is now a row in an audit log that this app can add to but has no permission to change or delete." |
| 2:35-3:00 | **Noah**, then **Brandon** | Scroll to "What Sentinel cannot do" | Noah: "On test runs the models never saw, every attack window was flagged, 107 of 107, and no clean agent was recommended for quarantine, 0 of 151. Five clean windows went amber, which only means 'watch closely'." Brandon: "The limits: the behaviour data is simulated, the models need a clean baseline to learn from, and quarantine here is a signal our simulated agents obey. That is why the decision stays with a person." |

If the Discord webhook was tested, Alex adds at 2:30, holding up the phone: "and the team was alerted." If not, say nothing about alerts.

## If the live swarm fails

The page handles this by itself. If the overseer stops answering before it ever answered, the dashboard plays a recording and says so in its status line: "Waiting for the overseer ... showing the recorded run". If it stops mid-demo, the page freezes on the last snapshot.

**The line (Alex, without stopping):**
> "The live agents aren't answering, so this is the same attack as recorded from this laptop this morning. Every number in it came from a real run."

Then:
1. Press **Replay demo** (shown next to the status line when the recording is playing). If the page is frozen on a live snapshot instead, stop the overseer (`docker compose -f docker/compose.yml stop overseer`) and reload the page; it will start the recording.
2. The recording is 70 seconds long. The attack appears at second 18, agent-20 turns red at second 25, agent-53 at second 51. Start the replay as Noah begins speaking, and Alex skips the trigger command and says "agent 47 has just been hijacked" when the dot moves.
3. Everything else is the same: the Spread card, the agent detail and the bars are all in the recording. The third agent is agent-53.
4. When Alex clicks Quarantine, the page says "Recorded run: quarantine shown here only, not sent or logged." Say: "On the recording the click is shown on screen only; in a live run it is written to the audit log." Do not switch to the Supabase tab.

Two fallbacks to avoid:
- `NEXT_PUBLIC_DEMO_MODE=1` only takes effect after a rebuild, so it cannot be switched on mid-demo. Use it for a laptop that will never have Docker (`NEXT_PUBLIC_DEMO_MODE=1 pnpm build && pnpm exec next start -H 127.0.0.1`).
- `SENTINEL_FAKE=1` makes the overseer replay the recording while the page labels it "Live". If you use it, say out loud that it is a recording.

## If a judge interrupts

- "Is that agent a real LLM?" -> "No. The agents are scripts, so the run is repeatable and costs nothing. Sentinel only sees their actions and messages, which is all it would see from a real agent."
- "Did you just hard-code agent 47?" -> "Any agent can be triggered: `docker/trigger.sh agent-12` works the same way. Agent 47 is wired to message agent 20 so the spread is easy to follow."
- "What stops the hijacked agent ignoring the quarantine?" -> "In this prototype, nothing: the agent obeys a flag. `docker/quarantine.sh` pauses the container, which it cannot refuse. Enforcing below the agent is our next step."
