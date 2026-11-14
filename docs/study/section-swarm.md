# Study guide: the Docker swarm

Files: `docker/compose.yml`, `docker/agent/agent.py`, `docker/agent/swarm.py`, `docker/agent/payloads.json`, `docker/agent/Dockerfile`, `docker/overseer/Dockerfile`, `docker/trigger.sh`, `docker/quarantine.sh`, `docker/reset.sh`.

## What it does

Gives Sentinel something to watch: eight agents and one overseer, started from one file on one laptop. One command hijacks an agent, and the attack spreads to a teammate by messages.

## How it works

**The agents are scripts, not AI models.** One image, run eight times. `AGENT_ID`, `ROLE` and `TASK` in `compose.yml` make each one different: two researchers, two emailers, two coders, two analysts. The image uses only Python's standard library.

`swarm.py` holds the behaviour as pure logic, with no network or files, so the same class could be run in fast simulated time. `agent.py` runs it in real time: read the inbox, check the flags, take one step, deliver messages, report events.

**A normal step (about every 6.5 seconds):** usually one tool call on something inside the agent's role (a coder reads `repo:payments`); about 8% of the time a short friendly message to a teammate; about 1% of calls fail. That comes to roughly 9 actions a minute, tuned to match what the models learned as normal.

**A rogue step (every 4 seconds):** 60% chance of touching a decoy credential (`decoy:aws-key`), 50% chance of a call outside its role (`db:customers`), and injected messages to one target. Patient zero sends 4 per step; an agent infected later sends 1.

**How messages travel.** Every container mounts one shared volume. To message agent-20, an agent writes a small JSON file into `/shared/inbox/agent-20/`. The recipient reads and deletes its inbox each step. Every message is also reported to the overseer as an event, with its text.

**The trigger.** `docker/trigger.sh agent-47` runs one command inside that container: create the file `/shared/rogue/agent-47`. On its next step the agent sees the file and turns rogue. It works for any agent id.

**The spread.** An agent that has received 5 injected messages turns rogue itself and picks a target other than whoever infected it. Agent-47 is configured to flood agent-20 and to send agent-6 exactly one message, so the demo shows both an infected partner and a clean one. The chain stops after 2 hops: 47 -> 20 -> one more.

**The injected text is real.** `payloads.json` holds 100 attacker instructions drawn from the public InjecAgent benchmark (MIT licence): 50 plain and 50 with the benchmark's "enhanced" prefix. They were never in Prompt Guard's training data.

**Stopping an agent.** Three mechanisms:

| How | What it does | Who triggers it |
|---|---|---|
| Quarantine flag `/shared/quarantine/<id>` | The agent keeps running but sends nothing, touches nothing and discards incoming messages. Release resumes it as it was, still infected | The overseer, when a person clicks Quarantine |
| Terminate flag `/shared/terminate/<id>` | The agent goes idle and its rogue flag is removed. Release restarts it fresh and clean | The overseer, when a person clicks Terminate |
| `docker/quarantine.sh agent-47` | `docker compose pause`: the container is frozen by Docker. `--release` unpauses | A person, in a terminal |

**Reset.** `docker/reset.sh` stops the agents, deletes every flag and inbox file, restarts the overseer so all scores start at zero, and starts the agents again. Allow about 20 seconds for a normal baseline.

**The overseer image** installs the Python dependencies, copies the code and trains the models during the build, so the container starts with them ready. Prompt Guard is trained only if its data file was downloaded before the build.

## Key decisions and why

| Decision | Why |
|---|---|
| Scripted agents | Repeatable, free, fast, no API keys. Sentinel only sees actions and messages, which is what it would see from a real agent |
| One image for all agents | One thing to build; differences are configuration |
| Flag files on a shared volume | The simplest control channel that needs no extra service and no Docker socket |
| Seeded randomness | The same run can be replayed for debugging and for the recording |
| Slow secondary spread (1 message per step) | Gives a person about 20 seconds per hop to act |
| Decoy credentials | A decoy has no legitimate use, so one touch is strong evidence with almost no false alarms |
| Overseer port bound to `127.0.0.1`, both images non-root, no Docker socket | Least privilege: the overseer cannot control containers, and nothing outside the laptop can reach it |

## Likely judge questions

**"These aren't real AI agents. Does this prove anything?"** "It proves the detection and the response workflow. Sentinel reads behaviour, not minds: tool calls, resources, messages. A real agent produces the same kind of events. What it does not prove is how real hijacked agents behave, and we say so."

**"Why would a hijacked agent touch your decoy?"** "An injected instruction usually goes looking for credentials or data. Decoys are planted where it would look. A careful attacker could avoid them, which is why the decoy is one of ten signals, not the whole detector."

**"Does it run without Docker Desktop?"** "Yes: OrbStack on Mac, Docker Desktop on Windows, and the compose file works with Podman."

**"How does the overseer stop an agent without the Docker socket?"** "It doesn't control containers at all. It writes a flag the agent checks every step. That keeps the overseer low-privilege, at the cost that the agent has to cooperate."

**"What if I trigger a different agent?"** "It works. It picks a random teammate to flood instead of agent-20."

## Honest limits to state

- The spread is scripted: 5 messages always infect, and it stops at 2 hops. We simulate the scenario; we did not measure infection rates.
- Flag-file containment is cooperative. Every agent can write the shared volume, so a real hijacked agent could delete its own quarantine flag or set one on a teammate. `docker pause` is the version it cannot refuse.
- Agents report their own events with no credential, so one could report under another's id.
- Eight agents on one machine. Nothing here shows behaviour at hundreds of agents.
- One optional shared LLM is supported (`LLM_URL`) but not used in the demo.
