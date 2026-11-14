"""One Sentinel swarm agent, run in real time inside a container. Standard library only.

Env: AGENT_ID, ROLE, PEERS (comma list), PRIMARY_PEER, LIGHT_PEER, SEED,
     OVERSEER_URL (default http://overseer:8000), SHARED_DIR (default /shared),
     LLM_URL (optional: one shared LLM service for every agent; never one model per agent).

Each step: read this agent's inbox on the shared volume, check its rogue flag
(written by docker/trigger.sh), run one AgentSim step, deliver outgoing messages to
peers' inboxes, and POST each event to the overseer. Events are contract A0 plus the
optional `text` field.
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

from swarm import DEFAULT_PAYLOADS, STEP_S, AgentSim, Message

log = logging.getLogger("sentinel.agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

AGENT_ID = os.environ["AGENT_ID"]
ROLE = os.environ["ROLE"]
OVERSEER = os.environ.get("OVERSEER_URL", "http://overseer:8000").rstrip("/")
SHARED = Path(os.environ.get("SHARED_DIR", "/shared"))
LLM_URL = os.environ.get("LLM_URL", "").strip()
INBOX = SHARED / "inbox" / AGENT_ID
FLAG = SHARED / "rogue" / AGENT_ID


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
            msgs.append(Message(d["src"], d["dst"], d["text"], bool(d["injected"])))
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


def main() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    peers = [p.strip() for p in os.environ.get("PEERS", "").split(",") if p.strip()]
    sim = AgentSim(
        agent_id=AGENT_ID, role=ROLE, peers=peers,
        primary_peer=os.environ.get("PRIMARY_PEER") or None,
        light_peer=os.environ.get("LIGHT_PEER") or None,
        seed=int(os.environ.get("SEED", "7")), payloads=load_payloads(),
    )
    log.info("%s (%s) up; %d peers; overseer %s", AGENT_ID, ROLE, len(sim.peers), OVERSEER)
    jitter = random.Random(AGENT_ID)
    while True:
        now = time.time()
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
            post_event(ev)
        time.sleep(max(0.5, STEP_S + jitter.uniform(-1.0, 1.0)))


if __name__ == "__main__":
    main()
