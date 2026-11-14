# Sentinel: pitch outline, mapped to the judging rubric

Rubric source: the HackNCAT problem-statement deck (100 points: ethics 25, innovation 20, technical 20, problem 15, validation 10, communication 10). Every claim below is tied to something in the code or to a number in [the audit](../review/AUDIT.md#1f-numbers-you-can-quote-and-where-each-comes-from). Anything not measured is marked **[TODO: run validate.py]**; do not say it.

**Register as:** Mission 3, Operation Secret Vault (autonomous AI safety), **Architect** tier, Pathway A (working prototype). The deck's own Architect example for Mission 3 is called "Prompt Guard", which is one of our three detectors. The rubric says Architect projects earn points through technical complexity, so name the tier in the first minute.

The existing deck is `docs/pitch/sentinel-deck.pptx` (9 slides). This outline keeps its structure and lists what to change. Slides 5, 7, 8 and 9 need the edits in [FIX-INSTRUCTIONS.md](../review/FIX-INSTRUCTIONS.md) before it is shown.

---

## The 60-second arc (say this, in this order)

1. **Problem (15 s).** "Companies have stopped running one AI agent and started running teams of them: a researcher, a coder, an emailer, all messaging each other and all holding real access."
2. **Threat (15 s).** "Prompt injection means an agent can be hijacked by text it reads. In a team, a hijacked agent's messages are text its teammates read. So one compromised agent can pass the attack on."
3. **Gap (10 s).** "Today's AI security tools sit in front of one agent and filter what comes in from outside. They don't watch how the agents inside a team behave toward each other."
4. **Our answer (20 s).** "Sentinel is an overseer for the whole team. It scores every agent's behaviour every two seconds, finds the first one that turned, traces who it talked to, explains why, and recommends what to do. Then a person decides, and that decision is logged. It works like an immune system that reports to a doctor instead of acting alone."

Careful wording: say "in our simulation" when describing the spread. The infection is scripted (`docker/agent/swarm.py`); we simulate the scenario, we did not measure it in the wild.

---

## One slide per rubric item

### Ethics, safety and human impact (25 points) — spend the most time here

The deck's ethics slide lists six dimensions. Hit all six by name.

| Dimension the judges score | What to say | Where the demo proves it |
|---|---|---|
| Human oversight | "Nothing happens to an agent without a person's click. Sentinel has no code path that acts by itself." | The Quarantine click at 2:05. `api.py`: `Overseer.act` is only reachable from `POST /agents/{id}/action` |
| Review and appeal | "Every action can be undone. Release puts a quarantined agent back; undoing a terminate restarts it clean. A person can also dismiss an alert." | The Release button that appears after Quarantine |
| Transparency and accountability | "Each score comes with a plain sentence, the evidence behind it, and bars showing what pushed the model. Each click is a row in an audit log." | Agent detail card; Supabase `audit_log` tab |
| Fairness, unfair false positives | "Being messaged by a bad agent is not enough to be flagged. An agent is 'likely infected' only if it got 10 or more messages and its own behaviour changed. On held-out runs, 0 of 151 clean windows were recommended for quarantine." | Agent-6: one message, "likely clean" |
| Proportional safeguards | "Four tiers: watch, slow down, quarantine, terminate. The top tier needs both behaviour models to agree. We chose the reversible option on stage." | Tier colours; choosing Quarantine when Terminate is suggested |
| Privacy and data minimisation | "The behaviour models never read message content, only counts and rates. Message text is scored by one small model and then dropped: it is not stored, logged or sent anywhere. The audit log stores a user id, never an email. All training telemetry is synthetic." | `api.py:90-92`, `actions.ts:23-24` |
| Unintended consequences, fail-safes | "If a model fails to load, a simple counting rule takes over and the screen says so. If the overseer stops, the page keeps the last picture." | `score.py` fallback; `components.fallback` |

Mission 3's own safeguard line is "least privilege, auditability, safe containment, authorized testing". Say: "the overseer runs as a non-root user, is reachable from this laptop only, holds no secret keys, and never gets the Docker socket; every test ran on our own simulated agents with planted decoys, never on a real system."

### Innovation and originality (20 points)

- "The unit we protect is the team, not the single agent. The new parts are patient-zero detection and spread tracing across agent-to-agent messages."
- "Three detectors that fail differently, blended into one score: a classifier for known attack shapes, an anomaly model for anything unlike normal, and a text model for messages that read like injections."
- "Honeytoken credentials for agents: a decoy no honest agent touches."
- Proof: the Spread card and the patient-zero headline.
- Do not say "nobody does this" or name a vendor. Say "the tools we looked at guard one agent's inputs and outputs".

### Technical feasibility and validity (20 points)

- "It runs now, on one laptop, with no GPU and no AI model in the scoring loop: about 4 milliseconds per agent."
- "One Docker Compose file: eight agents and the overseer. One command starts an attack."
- "The training data and the live system use the same feature code, so the model sees live data in the shape it learned."
- "Data contracts are frozen and mirrored in Python and TypeScript; 154 automated tests pass."
- "Interoperability: an agent only has to send one small JSON event per action to one endpoint."
- Proof: the live run itself; `GET /health` shows `backend: modules`.

### Problem definition and impact (15 points)

- State the problem as in the 60-second arc.
- Context numbers (cite on the slide): AI-enabled adversary activity up 89% in a year and average breakout time of 29 minutes (CrowdStrike 2026 Global Threat Report); organisations using security AI extensively saved $1.93M per breach (IBM Cost of a Data Breach 2026).
- Measurable risk reduction we can show: "patient zero flagged within one 2-second scoring tick of its first bad action in our recorded run", and "the simple counting rule alone reached quarantine level on 33 of 107 attack windows; the full system reached it on 101".
- Spread with and without Sentinel: **[TODO: run validate.py]**. Do not claim a number.

### Validation and effectiveness (10 points)

Say where each number comes from in the same breath.

| Say | Number | Data |
|---|---|---|
| Attack windows flagged | 107 of 107 | synthetic, runs held out from training |
| At quarantine level | 101 of 107 | same |
| Clean windows recommended for quarantine | 0 of 151 | same |
| Clean windows that went amber | 5 of 151 | same |
| An attack type the classifier never saw | 20 of 20 flagged, under the wrong name | same |
| Prompt Guard on a public benchmark it never trained on | precision 99.6%, recall 64%; the test set is 2,108 attacks and 34 benign | real (InjecAgent) |
| Split | by run, never by row | |

Detection rate over 20 runs, time to contain, false-quarantine rate on full runs: **[TODO: run validate.py]**.

### Communication and presentation (10 points)

- One speaker per beat, four speakers, handoffs by name (see [demo-script.md](demo-script.md)).
- Plain words on every slide; each number carries its source.
- The limits slide is presented, not hidden. The rubric scores "transparent handling of limitations and Q&A" here.

---

## The honest-limits slide

Title: **"What Sentinel can't do, and why a person decides"**

1. **It needs a clean baseline.** If the team is already compromised when the anomaly model learns, it learns the attack as normal.
2. **The classifier knows four attack shapes.** A new kind of attack may be flagged, but under the wrong name.
3. **The behaviour data is simulated.** No public dataset has per-agent action logs, so we generated ours. Only the text model was tested on real data.
4. **It finds infrastructure, not people.** It can say which agent and which system, never who was behind it.
5. **Quarantine is cooperative today.** Our simulated agents obey a stop signal; a real hijacked agent might not. Real enforcement belongs below the agent.

Closing line: "Each of these is a reason the last step is a person and not the model. Sentinel's job is to make that person fast and well informed."

---

## Five hard questions

**1. "How is this different from commercial AI detection and response?"**
"Those tools sit at one agent's boundary and inspect its prompts and outputs. Sentinel sits above the team and looks at behaviour over time and at the messages between agents. The two fit together: our third detector is the same kind of text filter, and its result is one input to our score."

**2. "What about false positives?"**
"On held-out runs, no clean agent was recommended for quarantine, 0 of 151 windows. Five went amber, which only asks a person to watch. And a false positive here costs a click: nothing is stopped without a person, and Release undoes it."

**3. "Did you test on real attack data?"**
"Partly. The text model was trained on one public prompt-injection dataset and tested on a different one, InjecAgent: 99.6% precision, 64% recall, so it misses about a third. The behaviour models were trained and tested on telemetry we simulated, because no public dataset of per-agent action logs exists. We split by run so the test runs were never seen in training."

**4. "Your most important feature is 'seconds since normal', which comes from your own model's last score. Isn't that circular?"**
"It is a feedback feature, so we tested without it. With it forced to zero on every test row, which is what the model sees on the first tick of an attack, it still flagged 107 of 107 attack windows and put 95 at quarantine level. In the live run, agent 47 was flagged on the first tick, before that feature could be non-zero."

**5. "Can a hijacked agent just ignore your quarantine, or frame a teammate?"**
"In this prototype, yes to both. The agents obey a flag file and events are not signed. We built the detection and the human workflow first. The fix is to enforce below the agent, at the container or network, and to give each agent its own credential for reporting events. `docker/quarantine.sh` already pauses the container, which the agent cannot refuse."

Two more worth rehearsing:
- **"Who can press the button?"** "Whoever is at this laptop. The server only listens on localhost. In production it would require a signed-in operator; the audit log already has a field for their id."
- **"Is the audit log tamper-proof?"** "No. It is append-only for the app: the database gives it permission to insert and read, not to update or delete. A database administrator could still alter it. Hash-chaining the rows is the next step."
