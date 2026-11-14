#!/usr/bin/env bash
# Clean slate between rehearsals: stop every agent (so nothing refills the inboxes), clear rogue
# flags and inboxes, restart the overseer so every risk starts from zero, then start the agents.
set -euo pipefail
cd "$(dirname "$0")"
agents=(agent-5 agent-6 agent-12 agent-20 agent-31 agent-38 agent-47 agent-53)
docker compose -f compose.yml unpause "${agents[@]}" >/dev/null 2>&1 || true
docker compose -f compose.yml stop "${agents[@]}" >/dev/null 2>&1
docker compose -f compose.yml run --rm --no-deps -T agent-5 \
  sh -c 'rm -f /shared/rogue/* /shared/quarantine/* /shared/terminate/* && find /shared/inbox -type f -delete' >/dev/null 2>&1
docker compose -f compose.yml restart overseer >/dev/null 2>&1
docker compose -f compose.yml start "${agents[@]}" >/dev/null 2>&1
echo "Reset: overseer restarted, 8 agents clean, no rogue agents. Give it ~20 s to build a normal baseline."
