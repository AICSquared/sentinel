# Study guide: security and ethics

Files: `src/app/sentinel/actions.ts`, `_lib/audit.ts`, `_lib/alert.ts`, `_lib/response.ts`, `supabase/migrations/20261114000000_audit_log.sql`, `_py/api.py` (`Overseer.act`), `_components/limits-card.tsx`, `docker/compose.yml`. Evidence for every "confirmed" below is in [the audit, section 1c](../review/AUDIT.md#1c-security-and-privacy).

Ethics is the largest rubric item (25 of 100) and the deck says it is "integrated into all evaluation categories". Everyone on the team should be able to give this section.

## What it does

Makes sure a detection system with the power to stop agents stays under human control, explains itself, keeps a record, and tells the truth about what it cannot do.

## How it works

**1. A person decides, every time.** The only code that changes an agent is `Overseer.act` in `api.py`. It can be reached one way: a person clicks a button, the Server Action `actOnAgents` runs, and it calls `POST /agents/{id}/action`. The scoring loop never calls it. Sentinel on its own can do two things: change a number on a screen, and write "Sentinel recommends..." to the log and the alert channel.

**2. Proportional tiers.** Under 40 nothing; 40-74 "slow down?"; 75-94 "quarantine?"; 95+ "terminate?". No single detector can reach 95. A person can pick a milder action than the one recommended.

**3. Undo and appeal.** Release reverses a quarantine. Undoing a terminate restarts the agent clean and wipes its score history so old behaviour cannot re-flag it. Dismiss records that a person looked and disagreed. If a different agent is flagged after a decision, Sentinel raises a new recommendation instead of assuming the old approval covers it.

**4. The audit log.** One table. Row Level Security is on. There is a policy for INSERT and a policy for SELECT, and no policy for UPDATE or DELETE, so the app's keys cannot change or remove a row. Each row holds the agent, its risk and attack type, the action, the reason, who decided (a user id, or "sentinel" for a recommendation), and what the overseer answered.

**5. Fairness.** An agent is not flagged for receiving messages. "Likely infected" needs 10 or more messages from the flagged agent and the partner's own risk at 40 or more. "Normal" is judged per role: a coder is compared with coders. On held-out runs, 0 of 151 clean windows were recommended for quarantine and 5 went amber.

**6. Transparency.** Each score comes with a sentence in plain words with real numbers, the counted evidence, the three score components, and the classifier's top contributions as bars. The limits are printed on the dashboard itself.

**7. Privacy and data minimisation.** The behaviour models use counts and rates, never content. Message text is used once by Prompt Guard, kept at most 60 seconds in memory, and never logged, returned by the API, stored in the audit log or sent to Discord. Alerts never name the person who clicked. All training telemetry is synthetic. The only real data is a public benchmark with fictional personas.

**8. Least privilege and safe testing.** Confirmed in the audit: no secrets in the repository or its history; the browser only ever holds the publishable key; Sentinel never loads the secret key; agents hold no keys; the alert function only posts to a validated Discord webhook URL; the overseer listens on localhost only, runs as a non-root user and has no Docker socket. Every attack ran against our own simulated agents with planted decoys.

**9. Fail-safes.** A model failure switches scoring to a counting rule and says so. A failed scoring tick keeps the last good picture. A failed audit write is reported in the click's result.

## Key decisions and why

| Decision | Why |
|---|---|
| Recommend, never auto-contain | A false positive should cost a person a click, not shut down a working agent. It also means an attacker cannot trick Sentinel into attacking its own team |
| Reversible first | Quarantine keeps the agent and its state; termination is the last tier |
| Append-only log in a database, not a file the app owns | The system being audited should not be able to rewrite its own record |
| User id, not email, in the log | The table is readable with the publishable key |
| Limits card on the product page | Honesty that only appears on a slide can be skipped |

## Likely judge questions

**"What stops Sentinel itself from being the thing that goes wrong?"** "It has no power to act. Its outputs are a score and a recommendation. Every change to an agent starts with a person's click, and each click is logged."

**"What about an agent that is wrongly flagged?"** "Nothing happens to it without a person. If a person does quarantine it wrongly, Release restores it, and both clicks are on the record. On held-out data no clean agent reached the quarantine tier."

**"Is your audit log tamper-proof?"** "Append-only for the app, not tamper-proof. The app can add and read rows and has no permission to update or delete. A database administrator still could. Hash-chaining the rows would make tampering detectable."

**"Whose data are you reading?"** "Only our simulated agents'. For behaviour we use counts, not content. The one model that reads message text keeps nothing."

**"Does a human in the loop scale?"** "The model does the watching and the sorting; the person only sees agents above the line, with the reason attached. At eight agents that is seconds. At thousands you would auto-approve the mildest tier and keep people on the severe ones, which is a policy choice the tiers already support."

## Honest limits to state (and the fix for each)

These are real gaps the audit found. Know them; a security judge may find them first.

| Gap | Honest answer |
|---|---|
| Anyone who can reach the page can click, and `pnpm demo` listens on all interfaces | "We bind it to localhost for the demo. A sign-in check is next" |
| The audit log accepts inserts from anyone with the publishable key; rows without a sign-in say "presenter" | "It proves the append-only design. Production would require sign-in and tie each row to the user" |
| Quarantine is a flag the agent obeys; agents can write the folder that holds it | "Our agents are cooperative simulations. Real enforcement belongs below the agent: container or network" |
| Events are unauthenticated; an agent could report as another | "Each agent needs its own credential for reporting" |
| The anomaly model needs a clean baseline | "If the team is already compromised when it learns, it learns the attack as normal" |
| The classifier knows four attack shapes | "A new kind may be flagged under the wrong name" |
| Attribution stops at the agent and the system | "We never claim to know who was behind it" |
| Behaviour data is synthetic; Prompt Guard's training set has no declared licence | "We say which numbers are simulated. That dataset is kept local and never redistributed" |

How to frame them: "We found these ourselves and wrote them down. Each one is a reason the last word belongs to a person."
