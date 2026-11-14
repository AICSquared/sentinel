"""Who messaged whom (checklist C6).

``Graph`` keeps agent-to-agent messages for the last 5 minutes
(``contract.GRAPH_WINDOW_S``). "Now" is the newest message timestamp it has
seen, i.e. the overseer's receive clock, never a container clock.

* ``related(agent_id, risks)``: everyone ``agent_id`` messaged in the window,
  most messages first. ``likely_infected`` = 10+ messages from this agent AND
  the partner's own risk is 40+; anything else is ``likely_clean``.
* ``edges()``: message counts per (from, to) pair over the window, for the map.
"""

from __future__ import annotations

import threading
from collections import Counter, deque
from typing import Mapping

try:
    from . import contract as C
except ImportError:  # run as a script from _py/
    import contract as C  # type: ignore[no-redef]


class Graph:
    def __init__(self, window_s: float = C.GRAPH_WINDOW_S) -> None:
        self.window_s = float(window_s)
        self._msgs: deque[tuple[float, str, str]] = deque()
        self._now = float("-inf")
        self._lock = threading.Lock()

    def add_message(self, src: str, dst: str | None, ts: float) -> None:
        """Record one message. Self-messages and messages with no recipient are ignored."""
        if not dst or src == dst:
            return
        with self._lock:
            self._now = max(self._now, float(ts))
            self._msgs.append((float(ts), str(src), str(dst)))
            self._prune()

    def _prune(self) -> None:
        cutoff = self._now - self.window_s
        while self._msgs and self._msgs[0][0] < cutoff:
            self._msgs.popleft()

    def _counts(self, window_s: float, now: float | None) -> Counter[tuple[str, str]]:
        end = self._now if now is None else float(now)
        start = end - min(float(window_s), self.window_s)
        with self._lock:
            return Counter((s, d) for ts, s, d in self._msgs if start <= ts <= end)

    def related(self, agent_id: str, risks: Mapping[str, int], now: float | None = None) -> list[dict]:
        """Partners ``agent_id`` messaged in the window, most messages first (contract B)."""
        counts = self._counts(self.window_s, now)
        out = []
        for (src, dst), n in counts.items():
            if src != agent_id:
                continue
            infected = n >= C.INFECTED_MIN_MESSAGES and risks.get(dst, 0) >= C.THROTTLE_AT
            out.append({"agent_id": dst, "messages": n, "verdict": "likely_infected" if infected else "likely_clean"})
        out.sort(key=lambda r: (-r["messages"], r["agent_id"]))
        return out

    def edges(self, window_s: float = C.GRAPH_WINDOW_S, now: float | None = None) -> list[dict]:
        """``[{"from", "to", "messages"}]`` over the window, busiest first (contract B2)."""
        counts = self._counts(window_s, now)
        rows = [{"from": s, "to": d, "messages": n} for (s, d), n in counts.items()]
        rows.sort(key=lambda r: (-r["messages"], r["from"], r["to"]))
        return rows
