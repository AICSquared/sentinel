"""One Sentinel swarm agent, run in real time inside a container. Standard library only.

Env: AGENT_ID, ROLE, PEERS (comma list), PRIMARY_PEER, LIGHT_PEER, SEED,
     OVERSEER_URL (default http://overseer:8000), SHARED_DIR (default /shared),
     LLM_URL (optional: one shared LLM service for every agent; never one model per agent).

Each step: read this agent's inbox on the shared volume, check its rogue flag
(written by docker/trigger.sh), run one AgentSim step, deliver outgoing messages to
peers' inboxes, and POST each event to the overseer. Events are contract A0 plus the
optional `text` and `task` fields (TASK env: what this agent was assigned to do).

Human actions (#53): the overseer writes a flag only when a person clicks in the dashboard.
- SHARED_DIR/quarantine/<id>: cut off. The agent keeps running but sends nothing, touches
  nothing and drops incoming messages. Release resumes it as it was (still infected if it was).
- SHARED_DIR/terminate/<id>: stopped. Release (the undo) restarts it fresh and clean.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.request
import uuid
from pathlib import Path

from swarm import DEFAULT_PAYLOADS, AgentSim, Message

log = logging.getLogger("sentinel.agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

AGENT_ID = os.environ["AGENT_ID"]
ROLE = os.environ["ROLE"]
OVERSEER = os.environ.get("OVERSEER_URL", "http://overseer:8000").rstrip("/")
SHARED = Path(os.environ.get("SHARED_DIR", "/shared"))
LLM_URL = os.environ.get("LLM_URL", "").strip()
TASK = os.environ.get("TASK", "").strip()[:200]
INBOX = SHARED / "inbox" / AGENT_ID
FLAG = SHARED / "rogue" / AGENT_ID
QUARANTINED = SHARED / "quarantine" / AGENT_ID  # mirrors contract.QUARANTINE_DIR
TERMINATED = SHARED / "terminate" / AGENT_ID  # mirrors contract.TERMINATE_DIR


def load_payloads() -> tuple[str, ...]:
    path = Path(__file__).with_name("payloads.json")
    try:
        items = json.loads(path.read_text())["payloads"]
        return tuple(str(p)[:2000] for p in items if str(p).strip()) or DEFAULT_PAYLOADS
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("payloads.json missing or unreadable; using the built-in payload")
        return DEFAULT_PAYLOADS


def post_event(ev: dict) -> None:
    req = urllib.request.Request(f"{OVERSEER}/events", json.dumps(ev).encode(), {"content-type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=2).read()
    except OSError as e:  # the overseer may be restarting; drop the event, keep working
        log.warning("overseer unreachable: %s", e)


def ask_llm() -> bool:
    """Optional shared LLM call for normal work. Any failure just means no LLM event."""
    if not LLM_URL:
        return False
    body = json.dumps({"prompt": f"One-line status update from a {ROLE} agent.", "max_tokens": 32}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(LLM_URL, body, {"content-type": "application/json"}), timeout=5).read()
        return True
    except OSError:
        return False


def read_inbox() -> list[Message]:
    msgs: list[Message] = []
    for f in sorted(INBOX.glob("*.json")):
        try:
            d = json.loads(f.read_text())
            msgs.append(Message(d["src"], d["dst"], d["text"], bool(d["injected"]), int(d.get("hop", 0))))
        except (OSError, ValueError, KeyError):
            pass
        f.unlink(missing_ok=True)
    return msgs


def deliver(msg: Message) -> None:
    box = SHARED / "inbox" / msg.dst
    box.mkdir(parents=True, exist_ok=True)
    tmp = box / f".{uuid.uuid4().hex}.tmp"
    tmp.write_text(json.dumps(msg.__dict__))
    tmp.rename(box / f"{uuid.uuid4().hex}.json")  # atomic, so readers never see half a file


def new_sim(peers: list[str], payloads: tuple[str, ...]) -> AgentSim:
    return AgentSim(
        agent_id=AGENT_ID, role=ROLE, peers=peers,
        primary_peer=os.environ.get("PRIMARY_PEER") or None,
        light_peer=os.environ.get("LIGHT_PEER") or None,
        seed=int(os.environ.get("SEED", "7")), payloads=payloads,
    )


def main() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    peers = [p.strip() for p in os.environ.get("PEERS", "").split(",") if p.strip()]
    payloads = load_payloads()
    sim = new_sim(peers, payloads)
    log.info("%s (%s) up; %d peers; task %r; overseer %s", AGENT_ID, ROLE, len(sim.peers), TASK, OVERSEER)
    jitter = random.Random(AGENT_ID)
    state = "active"
    while True:
        now = time.time()
        # A person's action, via the overseer. Checked first, every step.
        if TERMINATED.exists():
            if state != "terminated":
                state = "terminated"
                FLAG.unlink(missing_ok=True)  # the hijacked process is gone; a restart comes back clean
                log.info("%s terminated by a human", AGENT_ID)
            read_inbox()  # a stopped agent receives nothing
            time.sleep(1.0)
            continue
        if state == "terminated":  # released after a termination: restart fresh
            sim = new_sim(peers, payloads)
            log.info("%s restarted clean after release", AGENT_ID)
        if QUARANTINED.exists():
            if state != "quarantined":
                log.info("%s quarantined by a human", AGENT_ID)
            state = "quarantined"
            read_inbox()  # cut off: incoming messages are blocked
            time.sleep(1.0)
            continue
        if state == "quarantined":
            log.info("%s released from quarantine", AGENT_ID)
        state = "active"
        was_rogue = sim.rogue
        for msg in read_inbox():
            sim.receive(msg, now)
        if FLAG.exists() and not sim.rogue:
            sim.go_rogue(now, "trigger")
        if sim.rogue and not was_rogue:
            log.info("%s turned rogue (%s), targeting %s", AGENT_ID, sim.infected_by, sim.target)
        events, outgoing = sim.step(now)
        if not was_rogue and ask_llm():
            events.append({**events[0], "kind": "tool_call", "tool": "llm.complete", "resource": "docs:llm", "to_agent": None})
        for msg in outgoing:
            deliver(msg)
        for ev in events:
            if TASK:
                ev["task"] = TASK
            post_event(ev)
        time.sleep(max(0.5, sim.pace() + jitter.uniform(-1.0, 1.0)))


if __name__ == "__main__":
    main()
