---
name: demo-up
description: Use when someone asks to start, spin up or restart the live Sentinel demo (swarm, overseer and dashboard on localhost). Runs tools/demo up.
disable-model-invocation: true
---

# Start the live demo

1. Run `tools/demo up` from the repo root (add `--build` if the user asks for a rebuild, or if the script warns the checkout is behind origin/main and the user has pulled).
2. Report the script's last lines: the health line, and the URL `http://localhost:3000/sentinel`.
3. If it prints a WARNING (checkout behind origin/main, or `NEXT_PUBLIC_DEMO_MODE=1`), tell the user in one line. Don't pull or change `.env.local` yourself.
4. Remind them: wait about 20 s for a clean baseline before `/demo-trigger`.

If a step fails, run `tools/demo status` and report what it shows.
