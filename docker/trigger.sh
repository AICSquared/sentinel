#!/usr/bin/env bash
# Turn one swarm agent rogue: it starts replaying prompt_injection and spreading to peers.
# Usage: docker/trigger.sh agent-47
set -euo pipefail
cd "$(dirname "$0")"
agent="${1:-}"
[[ "$agent" =~ ^agent-[0-9]{1,4}$ ]] || { echo "usage: docker/trigger.sh agent-<n>" >&2; exit 2; }
docker compose -f compose.yml exec -T "$agent" sh -c 'touch "/shared/rogue/$AGENT_ID"'
echo "$(date -u +%H:%M:%S)  $agent is now rogue (prompt_injection). Watch /sentinel."
