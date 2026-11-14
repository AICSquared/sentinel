---
name: demo-trigger
description: Use when someone asks to trigger, hijack or turn rogue an agent in the live Sentinel demo, or to reset the demo. Runs tools/demo trigger or tools/demo reset.
disable-model-invocation: true
---

# Trigger the rogue agent

- `/demo-trigger` → `tools/demo trigger` (agent-47, the scripted patient zero).
- `/demo-trigger agent-12` → `tools/demo trigger agent-12` (any `agent-<n>` from the swarm: 5, 6, 12, 20, 31, 38, 47, 53).
- `/demo-trigger reset` → `tools/demo reset`; then say to wait about 20 s before triggering again.

Report the script's line with the time. Expect agent-47 red within about 4 s, agent-20 about 7 s later, a third agent around 30 s.
