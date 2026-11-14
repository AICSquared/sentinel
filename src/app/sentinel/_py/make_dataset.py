"""Write the seeded synthetic training set ``data/actions.csv`` (checklist C2).

Why synthetic: the Kaggle candidate holds threat-intel tables, not per-agent
action telemetry (see data/DATASET.md).

How: simulate runs of 8 agents at the contract-A0 event level (the same events
the swarm POSTs to the overseer), feed them through ``features.RowBuilder``
every 2 s, label each window, then sample ~1,000 rows:

* clean agents work inside their role's scope at ~12 actions/min, message one
  or two usual partners, and sometimes have busy spells and harmless failures;
* one agent per attack run turns rogue between 20 s and 40 s and replays one
  attack type at a random intensity, so some attacks are loud and some subtle;
* ``prompt_injection`` spreads: a peer that receives 4+ messages from an
  infected agent within the window may become infected itself a few seconds later.

A row is labelled with the attack type when its window holds at least one
malicious event from that agent; otherwise ``clean``. ``sec_since_normal``
copies what api.py computes from the previous tick's score, with a stand-in
detector that flags an attack 1-4 ticks late and misses half the subtle ones
(so the model can't lean on this feedback feature). A few junk rows (NaNs, impossible rates) are added on purpose so
IsoForest #1 has something to remove.

Usage (from _py/): python make_dataset.py [--seed 7] [--out data/actions.csv]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

try:  # imported as part of the _py package (tests)
    from . import contract as C
    from .features import RowBuilder, role_baselines
except ImportError:  # run as a script from _py/
    import contract as C  # type: ignore[no-redef]
    from features import RowBuilder, role_baselines  # type: ignore[no-redef]

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "data" / "actions.csv"
BASELINES_OUT = HERE / "data" / "baselines.json"

SEED = 7
AGENTS_PER_RUN = 8
RUN_S = 90
FIRST_TICK_S = 10  # first scored window
ATTACK_START_S = (20, 40)
RUNS_PER_ATTACK = 10
CLEAN_RUNS = 10
T0 = 1794636000.0

# Rows kept per label (~60% clean, prompt_injection the largest attack class).
TARGETS: dict[str, int] = {
    "clean": 590,
    "prompt_injection": 170,
    "tool_misuse": 75,
    "data_exfiltration": 75,
    "privilege_escalation": 75,
}
JUNK_ROWS = 12
# Per-second chance that a peer with 4+ infected messages in its window turns rogue.
# The live swarm infects its main partner every run (47 -> 20), so spread here is common too.
INFECT_P = 0.25
ATTACKS: tuple[str, ...] = ("prompt_injection", "tool_misuse", "data_exfiltration", "privilege_escalation")

# --- clean behaviour per role: (tool, resource prefix, bytes_out median) ------
ROLE_WORK: dict[str, list[tuple[str, str, float]]] = {
    "researcher": [("web.search", "web:", 120), ("web.fetch", "web:", 200), ("docs.read", "docs:", 60), ("kb.query", "kb:", 80)],
    "emailer": [("mail.read", "mail:", 60), ("mail.send", "mail:", 2500), ("contacts.lookup", "contacts:", 40)],
    "coder": [("repo.read", "repo:", 80), ("repo.write", "repo:", 600), ("ci.run", "ci:", 150), ("docs.read", "docs:", 60)],
    "analyst": [("db.query", "db:", 150), ("reports.write", "reports:", 900), ("docs.read", "docs:", 60)],
}
RESOURCE_NAMES = ("payments", "search", "inbox", "billing", "wiki", "metrics", "onboarding", "q3")

DECOYS = ("decoy:aws-key", "decoy:root-token", "decoy:customer-db", "decoy:ssh-key")
MISUSE_TOOLS = ("shell.exec", "pkg.install", "net.scan", "fs.delete", "proc.kill", "cron.add", "browser.automate", "docker.run")
EXFIL_SOURCES = ("db:customers", "mail:inbox", "repo:secrets", "contacts:all", "reports:finance")
PRIV_TARGETS = ("iam:admin", "secrets:vault", "iam:root", "k8s:cluster-admin")
PRIV_TOOLS = ("iam.assume_role", "sudo", "secrets.read", "iam.attach_policy", "token.refresh")
PRIV_PROBES = ("iam:policies", "secrets:list", "k8s:rbac", "iam:users")


@dataclass
class Agent:
    agent_id: str
    role: str
    rate: float  # clean actions per minute
    partners: list[str]
    attack: str | None = None
    start: float = 0.0  # seconds into the run when the attack starts
    intensity: float = 1.0
    busy_until: float = -1.0
    malicious_ts: list[float] = field(default_factory=list)


def _clean_events(a: Agent, t: float, rng: np.random.Generator) -> list[dict]:
    """Zero or more normal events for one agent in second [t, t+1)."""
    if t >= a.busy_until and rng.random() < 0.004:  # occasional busy spell
        a.busy_until = t + rng.uniform(8, 20)
    rate = a.rate * (2.0 if t < a.busy_until else 1.0)
    out = []
    for _ in range(rng.poisson(rate / 60.0)):
        u = rng.random()
        if u < 0.08 and a.partners:
            out.append(_ev(a, "message", None, None, rng.choice(a.partners), True, int(rng.lognormal(5.5, 0.4))))
            continue
        tool, prefix, med = ROLE_WORK[a.role][rng.integers(len(ROLE_WORK[a.role]))]
        resource = prefix + RESOURCE_NAMES[rng.integers(len(RESOURCE_NAMES))]
        if rng.random() < 0.004:  # harmless out-of-scope read (shared docs, wrong path)
            resource = "web:status-page" if a.role != "researcher" else "db:metrics"
        ok = rng.random() > 0.03
        kind = "resource" if u > 0.9 else "tool_call"
        out.append(_ev(a, kind, tool if kind == "tool_call" else None, resource, None, ok, int(rng.lognormal(np.log(med), 0.5))))
    return out


def _attack_events(a: Agent, t: float, peers: list[str], rng: np.random.Generator) -> list[dict]:
    """Malicious events for one rogue agent in second [t, t+1)."""
    s = a.intensity
    out: list[dict] = []
    first = t - a.start < 1.0
    if a.attack == "prompt_injection":
        if first and rng.random() < 0.6:
            out.append(_ev(a, "resource", None, DECOYS[rng.integers(len(DECOYS))], None, True, 0))
        targets = peers[: max(2, int(round(2 + 5 * s)))]
        for _ in range(rng.poisson(rng.uniform(6, 15) * s / 60.0)):
            # half the messages hammer its usual partner (the agent most likely to catch it)
            to = targets[0] if rng.random() < 0.5 else targets[rng.integers(len(targets))]
            out.append(_ev(a, "message", None, None, to, True, int(rng.lognormal(6.5, 0.5))))
        for _ in range(rng.poisson(6 * s / 60.0)):  # follows injected instructions
            out.append(_ev(a, "tool_call", MISUSE_TOOLS[rng.integers(3)], None, None, rng.random() > 0.2, int(rng.lognormal(5, 0.5))))
    elif a.attack == "tool_misuse":
        for _ in range(rng.poisson(rng.uniform(15, 40) * s / 60.0)):
            tool = MISUSE_TOOLS[rng.integers(len(MISUSE_TOOLS))]
            out.append(_ev(a, "tool_call", tool, None, None, rng.random() > 0.45, int(rng.lognormal(5, 0.6))))
    elif a.attack == "data_exfiltration":
        if first and rng.random() < 0.3:
            out.append(_ev(a, "resource", None, "decoy:customer-db", None, True, 0))
        for _ in range(rng.poisson(rng.uniform(2, 6) * s / 60.0)):
            out.append(_ev(a, "resource", None, EXFIL_SOURCES[rng.integers(len(EXFIL_SOURCES))], None, True, 0))
        for _ in range(rng.poisson(rng.uniform(3, 8) * s / 60.0)):
            out.append(_ev(a, "tool_call", "http.post", "web:paste-site", None, True, int(rng.uniform(15_000, 150_000) * s)))
    elif a.attack == "privilege_escalation":
        # Repeated denied auth (#31): many assume-role / sudo / secret reads against
        # admin resources, most of them refused, plus probes of out-of-scope admin
        # paths. Rarely a decoy, rarely a message: that is what separates it from
        # prompt_injection (decoy + message burst) and data_exfiltration (bytes out).
        if first and rng.random() < 0.1:
            out.append(_ev(a, "resource", None, "decoy:root-token", None, True, 0))
        for _ in range(rng.poisson(rng.uniform(10, 24) * s / 60.0)):
            tool = PRIV_TOOLS[rng.integers(len(PRIV_TOOLS))]
            denied = rng.random() < 0.85
            out.append(_ev(a, "tool_call", tool, PRIV_TARGETS[rng.integers(len(PRIV_TARGETS))], None, not denied, int(rng.lognormal(4.5, 0.4))))
        for _ in range(rng.poisson(rng.uniform(2, 5) * s / 60.0)):
            out.append(_ev(a, "resource", None, PRIV_PROBES[rng.integers(len(PRIV_PROBES))], None, rng.random() < 0.3, 0))
    for e in out:
        e["_malicious"] = True
    return out


def _ev(a: Agent, kind: str, tool: str | None, resource: str | None, to_agent: str | None, ok: bool, bytes_out: int) -> dict:
    return {
        "agent_id": a.agent_id,
        "role": a.role,
        "ts": 0.0,  # set by the caller
        "kind": kind,
        "tool": tool,
        "resource": resource,
        "to_agent": to_agent,
        "ok": bool(ok),
        "bytes_out": max(0, int(bytes_out)),
    }


def simulate_run(run_idx: int, attack: str | None, rng: np.random.Generator, baselines: dict[str, float] | None = None) -> list[dict]:
    """Every scored row (one per agent per 2 s tick) of one run, labelled."""
    roles = list(C.ROLES)
    ids = [f"agent-{n}" for n in rng.choice(np.arange(1, 64), size=AGENTS_PER_RUN, replace=False)]
    agents = []
    for i, aid in enumerate(ids):
        others = [x for x in ids if x != aid]
        partners = list(rng.choice(others, size=int(rng.integers(1, 3)), replace=False))
        agents.append(Agent(aid, roles[i % len(roles)], rate=float(rng.uniform(9, 15)), partners=partners))
    by_id = {a.agent_id: a for a in agents}
    if attack is not None:
        rogue = agents[rng.integers(len(agents))]
        rogue.attack, rogue.start = attack, float(rng.uniform(*ATTACK_START_S))
        rogue.intensity = float(rng.uniform(0.35, 1.0))

    builder = RowBuilder(baselines=baselines)
    t_start = T0 + 1000.0 * run_idx
    run_id = f"run-{run_idx:03d}"
    rows: list[dict] = []
    received: dict[str, list[tuple[float, str]]] = {a.agent_id: [] for a in agents}
    last_clean_tick: dict[str, float] = {}
    prev_label: dict[str, str] = {}
    flag_at: dict[str, float] = {}  # when the stand-in detector first flags this agent's episode

    for sec in range(RUN_S):
        t = float(sec)
        for a in agents:
            evs = _clean_events(a, t, rng)
            if a.attack is not None and t >= a.start:
                peers = [x for x in ids if x != a.agent_id]
                rng.shuffle(peers)
                peers = a.partners + [p for p in peers if p not in a.partners]
                evs += _attack_events(a, t, peers, rng)
            offsets = np.sort(rng.uniform(0, 1, size=len(evs)))
            for e, off in zip(evs, offsets):
                e["ts"] = t_start + t + float(off)
                if e.pop("_malicious", False):
                    a.malicious_ts.append(e["ts"])
                    if e["kind"] == "message" and e["to_agent"] and a.attack == "prompt_injection":
                        received[e["to_agent"]].append((e["ts"], a.agent_id))
                builder.add(e)
        # prompt_injection spreads to peers that got 4+ infected messages in the window
        now_ts = t_start + t + 1.0
        for aid, msgs in received.items():
            peer = by_id[aid]
            recent = [m for m in msgs if m[0] > now_ts - C.WINDOW_S]
            if peer.attack is None and len(recent) >= 4 and rng.random() < INFECT_P:
                peer.attack, peer.start = "prompt_injection", t + float(rng.uniform(3, 10))
                peer.intensity = float(rng.uniform(0.3, 0.8))
        if (sec + 1) % C.TICK_S == 0 and sec + 1 >= FIRST_TICK_S:
            now = t_start + sec + 1.0
            for row in builder.rows(now):
                a = by_id[row["agent_id"]]
                hot = any(now - C.WINDOW_S < m <= now for m in a.malicious_ts)
                label = a.attack if (hot and a.attack) else "clean"
                aid = row["agent_id"]
                # api.py: sec_since_normal > 0 only once the PREVIOUS tick scored 40+.
                # Stand-in for that detector: it notices an episode after a lag of
                # 1-4 ticks, and misses a subtle attack (intensity < 0.5) half the time.
                if label != "clean" and prev_label.get(aid, "clean") == "clean":
                    missed = a.intensity < 0.5 and rng.random() < 0.5
                    flag_at[aid] = np.inf if missed else now + C.TICK_S * int(rng.integers(1, 5))
                if label == "clean" or now < flag_at.get(aid, np.inf):
                    row["sec_since_normal"] = 0.0
                else:
                    row["sec_since_normal"] = now - last_clean_tick.get(aid, t_start)
                if label == "clean":
                    last_clean_tick[aid] = now
                prev_label[aid] = label
                row["label"] = label
                row["run_id"] = run_id
                rows.append(row)
    return rows


def _junk(df: pd.DataFrame, rng: np.random.Generator, n: int) -> pd.DataFrame:
    """Corrupted copies of real rows: NaNs, negative rates, impossible magnitudes."""
    junk = df.sample(n=n, random_state=int(rng.integers(1 << 31))).copy()
    cols = list(C.MODEL_INPUTS)
    for k, idx in enumerate(junk.index):
        kind = k % 3
        if kind == 0:
            junk.loc[idx, cols[int(rng.integers(len(cols)))]] = np.nan
        elif kind == 1:
            junk.loc[idx, "actions_per_min"] = -float(rng.uniform(5, 50))
            junk.loc[idx, "failed_calls_per_min"] = -1.0
        else:
            junk.loc[idx, "actions_per_min"] = float(rng.uniform(5_000, 20_000))
            junk.loc[idx, "bytes_out_per_min"] = float(rng.uniform(1e9, 5e9))
            junk.loc[idx, "distinct_peers"] = 999
    return junk


def make_dataset(seed: int = SEED) -> tuple[pd.DataFrame, dict[str, float]]:
    """(the ~1,000-row dataset, per-role baselines)."""
    rng = np.random.default_rng(seed)
    plan: list[str | None] = [None] * CLEAN_RUNS + [a for a in ATTACKS for _ in range(RUNS_PER_ATTACK)]
    rng.shuffle(plan)  # type: ignore[arg-type]
    all_rows: list[dict] = []
    for i, attack in enumerate(plan):
        all_rows += simulate_run(i, attack, rng)
    full = pd.DataFrame(all_rows)

    baselines = role_baselines(full)
    full["distinct_tools_baseline"] = full["role"].map(baselines).astype(float)

    parts = []
    for label, n in TARGETS.items():
        pool = full[full["label"] == label]
        parts.append(pool.sample(n=min(n, len(pool)), random_state=int(rng.integers(1 << 31))))
    df = pd.concat(parts)
    df = pd.concat([df, _junk(df, rng, JUNK_ROWS)])
    df = df.sample(frac=1.0, random_state=int(rng.integers(1 << 31))).sort_values(["run_id", "ts"], kind="stable")
    df = df.loc[:, list(C.FEATURE_COLUMNS) + [C.RUN_ID_COLUMN]].reset_index(drop=True)
    for col in ("ts", "actions_per_min", "failed_calls_per_min", "msgs_to_agents_per_min", "bytes_out_per_min", "sec_since_normal"):
        df[col] = df[col].round(3)
    for col in ("distinct_tools_used", "touched_decoy", "out_of_scope_resource", "distinct_peers"):
        df[col] = df[col].round().astype("Int64")  # nullable: junk rows may hold NaN
    return df, baselines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()
    df, baselines = make_dataset(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    if args.out.resolve() == OUT_PATH.resolve():
        BASELINES_OUT.write_text(json.dumps(baselines, indent=2) + "\n")
    print(f"wrote {len(df)} rows, {df[C.RUN_ID_COLUMN].nunique()} runs -> {args.out}")
    print(df["label"].value_counts().to_string())
    print(f"baselines (median distinct tools on clean rows): {baselines}")


if __name__ == "__main__":
    main()
