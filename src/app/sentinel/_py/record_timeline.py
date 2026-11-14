#!/usr/bin/env python3
"""Record a real run of the swarm as the demo timeline (issue #47).

Polls the overseer's `GET /agents` once a second during a scripted run and writes
`_data/demo_timeline.json` = {"ticks": [FleetSnapshot, ...]} with `mode: "demo"`:

    ~15 s normal baseline -> trigger agent-47 -> the attack spreads -> a human approve
    (`POST /decision`) about 20 s after the trigger -> a short tail.

The recording is real: every number, reason, position and `top_features` bar came from the live
overseer. Nothing here edits a snapshot except setting `mode` to "demo". Every tick is checked against
the B2 contract (names, enums, ranges) before anything is written, and the run itself is checked
(clean baseline, patient zero named, spread seen, bars present, approve landed).

Run it against a live stack. With Docker:
    docker compose -f docker/compose.yml up --build -d && docker/reset.sh
    python record_timeline.py                       # runs docker/trigger.sh agent-47 itself
Without Docker: start `uvicorn api:app` and the 8 agents natively, then
    python record_timeline.py --trigger "touch /path/to/shared/rogue/agent-47"

Standard library only; `contract.py` is the only import.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import contract as C  # noqa: E402

REPO_ROOT = HERE.parents[3]  # _py -> sentinel -> app -> src -> repo
DEFAULT_OUT = HERE.parent / "_data" / "demo_timeline.json"
DEFAULT_TRIGGER = "docker/trigger.sh agent-47"
ROGUE_LINE = re.compile(r"(agent-\d+) turned rogue")


def rogue_agents(log_text: str) -> set[str]:
    """Who really turned rogue, from the agents' own log lines ("agent-20 turned rogue (agent-47), ...").

    The first hop is fixed (agent-47 floods agent-20) but later hops are a random pick, so the ground truth
    comes from the logs of the run being recorded, never from an assumption about the chain.
    """
    return set(ROGUE_LINE.findall(log_text))


def read_agent_logs(logs_dir: Path | None, since_iso: str) -> str:
    """Agent log text for this run: every *.log in `logs_dir` (native), else `docker compose logs` since the start."""
    if logs_dir is not None:
        return "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in sorted(logs_dir.glob("*.log")))
    done = subprocess.run(
        ["docker", "compose", "-f", "docker/compose.yml", "logs", "--no-color", "--since", since_iso],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return done.stdout + done.stderr

B2_TOP = {"updated", "mode", "sentinel", "agents", "edges", "events"}
B2_SENTINEL = {"patient_zero", "origin_ts", "containment", "last_action", "fleet_risk_history"}
B2_AGENT = {
    "agent_id", "role", "risk", "attack_type", "recommended_action", "reason",
    "position", "requests", "systems_touched", "first_flagged_ts", "related_agents",
}
OPTIONAL_AGENT = set(C.OPTIONAL_AGENT_FIELDS)


# ---------------------------------------------------------------- contract check


def validate_tick(tick: dict) -> list[str]:
    """Problems with one snapshot against contract B2 (empty list = valid). Keys, enums and ranges only."""
    bad: list[str] = []
    if set(tick) != B2_TOP:
        bad.append(f"top-level keys {sorted(tick)} != {sorted(B2_TOP)}")
        return bad
    if tick["mode"] not in ("live", "demo"):
        bad.append(f"mode {tick['mode']!r}")
    s = tick["sentinel"]
    if not B2_SENTINEL <= set(s):
        bad.append(f"sentinel missing {sorted(B2_SENTINEL - set(s))}")
    else:
        if s["containment"] not in C.CONTAINMENT_STATES:
            bad.append(f"containment {s['containment']!r}")
        if s["last_action"] not in C.ACTIONS:
            bad.append(f"last_action {s['last_action']!r}")
        if len(s["fleet_risk_history"]) > 12:
            bad.append("fleet_risk_history longer than 12")
    for a in tick["agents"]:
        aid = a.get("agent_id", "?")
        missing = B2_AGENT - set(a)
        extra = set(a) - B2_AGENT - OPTIONAL_AGENT
        if missing or extra:
            bad.append(f"{aid}: missing {sorted(missing)} extra {sorted(extra)}")
            continue
        if a["role"] not in C.ROLES:
            bad.append(f"{aid}: role {a['role']!r}")
        if a["attack_type"] not in C.ATTACK_TYPES:
            bad.append(f"{aid}: attack_type {a['attack_type']!r}")
        if a["recommended_action"] not in C.ACTIONS:
            bad.append(f"{aid}: recommended_action {a['recommended_action']!r}")
        if not (isinstance(a["risk"], int) and 0 <= a["risk"] <= 100):
            bad.append(f"{aid}: risk {a['risk']!r}")
        if a["attack_type"] == "clean" and a["risk"] >= C.THROTTLE_AT:
            bad.append(f"{aid}: clean with risk {a['risk']}")
        pos = a["position"]
        if not (0 <= pos["x"] <= 1 and 0 <= pos["y"] <= 1):
            bad.append(f"{aid}: position {pos}")
        if len(a["systems_touched"]) > 8:
            bad.append(f"{aid}: more than 8 systems_touched")
        for r in a["related_agents"]:
            if r.get("verdict") not in C.VERDICTS:
                bad.append(f"{aid}: related verdict {r.get('verdict')!r}")
        tf = a.get("top_features")
        if tf is not None:
            if not 1 <= len(tf) <= C.TOP_FEATURES_MAX:
                bad.append(f"{aid}: top_features has {len(tf)} entries")
            elif any(set(f) != {"feature", "contribution"} for f in tf):
                bad.append(f"{aid}: top_features entry keys")
            elif [abs(f["contribution"]) for f in tf] != sorted((abs(f["contribution"]) for f in tf), reverse=True):
                bad.append(f"{aid}: top_features not largest-first")
    for e in tick["edges"]:
        if set(e) != {"from", "to", "messages"}:
            bad.append(f"edge keys {sorted(e)}")
    if len(tick["events"]) > 50:
        bad.append("more than 50 events")
    for line in tick["events"]:
        if not (len(line) > 10 and line[2] == ":" and line[8:10] == "  "):
            bad.append(f"event line not 'HH:MM:SS  text': {line!r}")
    return bad


def check_run(ticks: list[dict], trigger_tick: int, approve_tick: int | None, infected: set[str] | None = None) -> list[str]:
    """Problems with the run as a demo (empty list = usable). Separate from the per-tick contract check.

    `infected` is who really turned rogue (from the agent logs, see rogue_agents). When given, an
    agent outside it reaching risk 75+ is a FALSE quarantine and an infected one that never did is a miss.
    Either makes the recording unusable as a demo: it must not show an innocent agent accused.
    """
    bad: list[str] = []
    before, after = ticks[:trigger_tick], ticks[trigger_tick:]
    if any(t["sentinel"]["patient_zero"] for t in before):
        bad.append("patient zero named before the trigger: the swarm was not clean")
    if any(a["risk"] >= C.THROTTLE_AT for t in before for a in t["agents"]):
        bad.append("an agent was at risk 40+ before the trigger: reset the swarm and wait for a baseline")
    last = ticks[-1]
    pz = last["sentinel"]["patient_zero"]
    if not pz:
        bad.append("no patient zero by the end of the run")
    flagged = {a["agent_id"] for t in after for a in t["agents"] if a["risk"] >= C.QUARANTINE_AT}
    if len(flagged) < 2:
        bad.append(f"only {sorted(flagged)} reached risk {C.QUARANTINE_AT}+: no spread to show")
    seen_infected = {r["agent_id"] for t in after for a in t["agents"] for r in a["related_agents"] if r["verdict"] == "likely_infected"}
    if not seen_infected:
        bad.append("no related agent was ever likely_infected")
    if infected is not None:
        for aid in sorted(flagged - infected):
            hits = [i for i, t in enumerate(ticks) if any(a["agent_id"] == aid and a["risk"] >= C.QUARANTINE_AT for a in t["agents"])]
            bad.append(f"FALSE QUARANTINE: {aid} never turned rogue but reached risk {C.QUARANTINE_AT}+ at ticks {hits}")
        for aid in sorted(infected - flagged):
            bad.append(f"MISS: {aid} turned rogue but never reached risk {C.QUARANTINE_AT}+")
    if not any(a.get("top_features") for t in after for a in t["agents"] if a["risk"] >= C.QUARANTINE_AT):
        bad.append("no top_features on any flagged agent: the models were not loaded (backend should be 'modules')")
    if approve_tick is None or last["sentinel"]["containment"] != "approved":
        bad.append("the approve did not land (containment is not 'approved' at the end)")
    return bad


# ---------------------------------------------------------------- HTTP


def _request(url: str, data: dict | None = None, timeout: float = 3.0) -> Any:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"} if body else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------- the run


def record(api: str, trigger: str, baseline_s: int, approve_after_s: int, ticks_total: int, tick_s: float) -> tuple[list[dict], int, int | None]:
    health = _request(f"{api}/health")
    if health.get("mode") != "live":
        sys.exit(f"overseer is in {health.get('mode')!r} mode; record against the live overseer, not SENTINEL_FAKE")
    if health.get("backend") != "modules":
        sys.exit(f"overseer backend is {health.get('backend')!r}, not 'modules': the models are not loaded, so there would be no top_features")

    ticks: list[dict] = []
    trigger_tick = baseline_s
    approve_tick: int | None = None
    start = time.monotonic()
    for i in range(ticks_total):
        wait = start + i * tick_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        if i == trigger_tick:
            print(f"[{i:3d}] trigger: {trigger}", flush=True)
            done = subprocess.run(trigger, shell=True, cwd=REPO_ROOT, capture_output=True, text=True)
            if done.returncode != 0:
                sys.exit(f"trigger failed ({done.returncode}): {done.stderr.strip() or done.stdout.strip()}")
        snap = _request(f"{api}/agents")
        if i >= trigger_tick + approve_after_s and approve_tick is None and snap["sentinel"]["containment"] == "recommended":
            try:
                _request(f"{api}/decision", {"action": "approve"})
                approve_tick = i
                print(f"[{i:3d}] human approve (POST /decision)", flush=True)
                snap = _request(f"{api}/agents")  # the click shows on /agents immediately
            except urllib.error.HTTPError as exc:
                print(f"[{i:3d}] approve refused: {exc.code}", flush=True)
        snap["mode"] = "demo"
        ticks.append(snap)
        flagged = [a["agent_id"] for a in snap["agents"] if a["risk"] >= C.QUARANTINE_AT]
        print(f"[{i:3d}] peak {max((a['risk'] for a in snap['agents']), default=0):3d}  flagged {flagged}  {snap['sentinel']['containment']}", flush=True)
    return ticks, trigger_tick, approve_tick


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--api", default="http://127.0.0.1:8000", help="overseer base URL")
    p.add_argument("--trigger", default=DEFAULT_TRIGGER, help=f"shell command that turns agent-47 rogue (run from the repo root; default {DEFAULT_TRIGGER!r})")
    p.add_argument("--baseline", type=int, default=15, help="seconds of normal behaviour before the trigger")
    p.add_argument("--approve-after", type=int, default=20, help="seconds after the trigger to click approve")
    p.add_argument("--ticks", type=int, default=60, help="total ticks, one per second")
    p.add_argument("--tick-s", type=float, default=1.0, help="seconds between ticks (leave at 1: the dashboard plays one per second)")
    p.add_argument("--infected", default="auto", help="who really turns rogue; any other agent reaching risk 75+ is a false quarantine and blocks the write. 'auto' (default) reads the agents' logs; or a comma list; or 'any' to skip the check")
    p.add_argument("--logs-dir", type=Path, default=None, help="folder of agent *.log files (native runs); default is `docker compose logs`")
    p.add_argument("--raw-out", type=Path, default=None, help="also save the raw ticks here BEFORE any check, so a failed run is not lost (not for committing)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--dry-run", action="store_true", help="validate but do not write the file")
    args = p.parse_args()

    since_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ticks, trigger_tick, approve_tick = record(args.api, args.trigger, args.baseline, args.approve_after, args.ticks, args.tick_s)

    if args.raw_out:
        args.raw_out.write_text(json.dumps({"trigger_tick": trigger_tick, "approve_tick": approve_tick, "ticks": ticks}), encoding="utf-8")
    problems = [f"tick {i}: {m}" for i, t in enumerate(ticks) for m in validate_tick(t)]
    if args.infected == "any":
        infected = None
    elif args.infected == "auto":
        infected = rogue_agents(read_agent_logs(args.logs_dir, since_iso))
        if not infected:
            sys.exit("NOT WRITTEN: no 'turned rogue' lines in the agent logs, so who was infected can't be checked. Pass --logs-dir, --infected a,b,c, or --infected any")
        print(f"\ninfected per the agent logs: {sorted(infected)}")
    else:
        infected = {s.strip() for s in args.infected.split(",") if s.strip()}
    problems += check_run(ticks, trigger_tick, approve_tick, infected)
    if problems:
        print("\nNOT WRITTEN, the recording has problems:", file=sys.stderr)
        for line in problems[:30]:
            print("  -", line, file=sys.stderr)
        sys.exit(1)
    if args.dry_run:
        print(f"\nOK (dry run): {len(ticks)} ticks valid; nothing written")
        return
    args.out.write_text(json.dumps({"ticks": ticks}, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {len(ticks)} ticks to {args.out} (trigger at tick {trigger_tick}, approve at tick {approve_tick})")


if __name__ == "__main__":
    main()
