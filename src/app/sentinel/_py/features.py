"""Contract A feature rows from contract A0 raw events (checklist C2).

``RowBuilder`` keeps a 60-second sliding window of each agent's events and turns
it into one feature row per agent (columns 1-13 of ``contract.FEATURE_COLUMNS``).
The overseer (``api.py``) calls ``add`` for every event and ``rows(now)`` every
2 seconds. ``make_dataset.py`` drives the same class over simulated events, so
the training data and the live overseer share one feature implementation.

``sec_since_normal`` depends on the previous score, which this module never
sees: rows carry 0.0 and ``api.py`` fills in the real value before scoring.

``load_dataset(path)`` reads ``data/actions.csv`` for training.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:  # imported as part of the _py package (tests, api.py)
    from . import contract as C
except ImportError:  # run as a script from _py/
    import contract as C  # type: ignore[no-redef]

log = logging.getLogger("sentinel.features")

HERE = Path(__file__).resolve().parent
BASELINES_PATH = HERE / "data" / "baselines.json"

ROW_COLUMNS: tuple[str, ...] = C.FEATURE_COLUMNS[:13]  # columns 1-13, no label
PER_MIN = 60.0 / C.WINDOW_S  # window counts -> per-minute rates (1.0 for a 60 s window)

# Used only when data/baselines.json is missing. make_dataset.py rewrites that
# file with the MEDIAN distinct tools per role on clean rows.
DEFAULT_BASELINES: dict[str, float] = {"researcher": 3.0, "emailer": 2.0, "coder": 3.0, "analyst": 3.0}


def load_baselines(path: Path | None = None) -> dict[str, float]:
    """Per-role MEDIAN distinct tools on clean data (column 6)."""
    p = path or BASELINES_PATH
    try:
        data = json.loads(p.read_text())
        return {**DEFAULT_BASELINES, **{str(k): float(v) for k, v in data.items()}}
    except (OSError, ValueError):
        return dict(DEFAULT_BASELINES)


def role_baselines(df: pd.DataFrame) -> dict[str, float]:
    """MEDIAN ``distinct_tools_used`` per role over the clean rows of ``df``."""
    clean = df[df[C.LABEL_COLUMN] == "clean"] if C.LABEL_COLUMN in df else df
    med = clean.groupby("role")["distinct_tools_used"].median()
    return {**DEFAULT_BASELINES, **{str(k): float(v) for k, v in med.items()}}


def window_row(agent_id: str, role: str, events: list[dict], now: float, baseline: float) -> dict:
    """One contract-A row (columns 1-13) from the events of one agent's window."""
    tools = {e.get("tool") for e in events if e.get("tool")}
    resources = [e.get("resource") for e in events if e.get("resource")]
    msgs = [e for e in events if e.get("kind") == "message"]
    peers = {e.get("to_agent") for e in msgs if e.get("to_agent")}
    return {
        "agent_id": agent_id,
        "role": role,
        "ts": float(now),
        "actions_per_min": len(events) * PER_MIN,
        "distinct_tools_used": len(tools),
        "distinct_tools_baseline": float(baseline),
        "failed_calls_per_min": sum(1 for e in events if not e.get("ok", True)) * PER_MIN,
        "touched_decoy": int(any(r.startswith(C.DECOY_PREFIX) for r in resources)),
        "out_of_scope_resource": int(any(not C.in_scope(role, r) for r in resources)),
        "msgs_to_agents_per_min": len(msgs) * PER_MIN,
        "distinct_peers": len(peers),
        "bytes_out_per_min": float(sum(int(e.get("bytes_out") or 0) for e in events)) * PER_MIN,
        "sec_since_normal": 0.0,
    }


class RowBuilder:
    """Sliding 60 s window of contract-A0 events per agent -> contract-A rows."""

    def __init__(self, baselines: dict[str, float] | None = None, window_s: float = C.WINDOW_S) -> None:
        self.window_s = float(window_s)
        self.baselines = dict(baselines) if baselines is not None else load_baselines()
        self._events: dict[str, deque[dict]] = defaultdict(deque)
        self._roles: dict[str, str] = {}

    def add(self, event: dict) -> None:
        """Record one raw event. Events must arrive in time order per agent."""
        agent_id = str(event["agent_id"])
        self._roles[agent_id] = str(event.get("role") or self._roles.get(agent_id, ""))
        self._events[agent_id].append(event)

    def rows(self, now: float) -> list[dict]:
        """One row per agent with at least one event in (now - window, now]."""
        out = []
        cutoff = now - self.window_s
        for agent_id, dq in self._events.items():
            while dq and float(dq[0]["ts"]) <= cutoff:
                dq.popleft()
            events = [e for e in dq if float(e["ts"]) <= now]
            if not events:
                continue
            role = self._roles[agent_id]
            base = self.baselines.get(role, float(np.median(list(DEFAULT_BASELINES.values()))))
            out.append(window_row(agent_id, role, events, now, base))
        return out


# --------------------------------------------------------------------------
# training data

NUMERIC_TYPES: dict[str, Any] = {
    "ts": float,
    "actions_per_min": float,
    "distinct_tools_used": float,  # int in the contract; float here so junk NaNs survive the read
    "distinct_tools_baseline": float,
    "failed_calls_per_min": float,
    "touched_decoy": float,
    "out_of_scope_resource": float,
    "msgs_to_agents_per_min": float,
    "distinct_peers": float,
    "bytes_out_per_min": float,
    "sec_since_normal": float,
}


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Read ``actions.csv``: contract-A columns (+ ``label``, ``run_id``), checked.

    Rows with a missing model input are dropped here (no model can score a NaN).
    Rows with impossible values (negative or absurd rates) are kept on purpose:
    removing them is IsoForest #1's job (``model_anomaly.filter_train``).
    """
    df = pd.read_csv(path, dtype={"agent_id": str, "role": str, C.LABEL_COLUMN: str, C.RUN_ID_COLUMN: str})
    missing = [c for c in ROW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing contract-A columns {missing}")
    for col, typ in NUMERIC_TYPES.items():
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(typ)
    bad = df[list(C.MODEL_INPUTS)].isna().any(axis=1)
    if bad.any():
        log.info("load_dataset dropped %d of %d rows with a missing model input", int(bad.sum()), len(df))
    df = df.loc[~bad].copy()
    for col in ("distinct_tools_used", "touched_decoy", "out_of_scope_resource", "distinct_peers"):
        df[col] = df[col].round().astype(int)
    order = [c for c in (*C.FEATURE_COLUMNS, C.RUN_ID_COLUMN) if c in df.columns]
    return df.loc[:, order].reset_index(drop=True)
