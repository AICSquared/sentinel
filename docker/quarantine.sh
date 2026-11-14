#!/usr/bin/env bash
# The HUMAN's action after approving Sentinel's recommendation: pause the named agents' containers.
# Sentinel only recommends; this script is how a person acts on it. Reversible with --release.
# Usage: docker/quarantine.sh agent-47 agent-20
#        docker/quarantine.sh --release agent-47 agent-20
set -euo pipefail
cd "$(dirname "$0")"
action=pause
if [[ "${1:-}" == "--release" ]]; then action=unpause; shift; fi
[[ $# -gt 0 ]] || { echo "usage: docker/quarantine.sh [--release] agent-<n> ..." >&2; exit 2; }
for a in "$@"; do
  [[ "$a" =~ ^agent-[0-9]{1,4}$ ]] || { echo "not an agent id: $a" >&2; exit 2; }
done
docker compose -f compose.yml "$action" "$@"
if [[ "$action" == pause ]]; then echo "Quarantined (paused): $*. Undo: docker/quarantine.sh --release $*"
else echo "Released: $*"; fi
