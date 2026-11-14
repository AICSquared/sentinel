"""Read-only Sentinel swarm monitor."""
from __future__ import annotations
import json
import os
import pathlib

import httpx

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Static

DATA_FILE = pathlib.Path(__file__).parent.parent / "_data" / "live_sample.json"
REFRESH_SECONDS = 0.5


def risk_text(risk: int) -> Text:
    if risk >= 75:
        return Text(f"{risk:>3}", style="bold white on red")
    if risk >= 40:
        return Text(f"{risk:>3}", style="black on yellow")
    return Text(f"{risk:>3}", style="green")


def dot(risk: int) -> Text:
    if risk >= 75:
        return Text("●", style="bold red")
    if risk >= 40:
        return Text("●", style="yellow")
    return Text("●", style="green")


def sparkline(values: list[int]) -> str:
    bars = "▁▂▃▄▅▆▇█"
    if not values:
        return ""
    hi = max(values) or 1
    return "".join(bars[min(len(bars) - 1, int(v / hi * (len(bars) - 1)))] for v in values)


class Sentinel(App):
    CSS = """
    Screen { background: $surface; }
    #sentinel { height: auto; padding: 1 2; border: round $accent; }
    #events { height: auto; max-height: 10; padding: 0 2; border: round $panel; }
    DataTable { height: 1fr; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Static("Connecting…", id="source")
            yield Static(id="sentinel")
            yield DataTable(id="agents", zebra_stripes=True)
            yield Static(id="events")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#agents", DataTable)
        self.source_label = self.query_one("#source", Static)
        self.summary_label = self.query_one("#sentinel", Static)
        self.event_log = self.query_one("#events", Static)
        self.table = table
        self.columns = table.add_columns(" ", "agent", "role", "risk", "attack type", "recommended")
        base = os.getenv("SENTINEL_API_URL") or "http://localhost:8000"
        self.url = base.rstrip("/") + "/agents"
        self.client = httpx.AsyncClient(timeout=0.4)
        self.previous = None
        self.set_interval(REFRESH_SECONDS, self.refresh_data)
        self.call_after_refresh(self.refresh_data)

    async def on_unmount(self) -> None:
        await self.client.aclose()

    async def refresh_data(self) -> None:
        try:
            response = await self.client.get(self.url)
            response.raise_for_status()
            snapshot = prepare(response.json())
            source = "API connected"
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, TypeError, KeyError, AttributeError):
            source = "offline · sample"
            try:
                snapshot = prepare(json.loads(DATA_FILE.read_text()))
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                self.source_label.update("offline · sample unavailable")
                return

        self.source_label.update(source)
        if snapshot == self.previous:
            return
        summary, rows, events = snapshot
        self.summary_label.update(Text(summary))
        table = self.table
        for key in set(table.rows) - rows.keys():
            table.remove_row(key)
        for key, cells in rows.items():
            if key in table.rows:
                for column, old, new in zip(self.columns, table.get_row(key), cells):
                    if old != new:
                        table.update_cell(key, column, new, update_width=True)
            else:
                table.add_row(*cells, key=key)
        self.event_log.update(Text(events, style="dim"))
        self.previous = snapshot


def prepare(data: dict) -> tuple:
    state = data["sentinel"]
    patient = state["patient_zero"]
    related = []
    rows = {}
    for agent in data["agents"]:
        key = agent["agent_id"]
        risk = int(agent["risk"])
        rows[key] = (dot(risk), key, agent["role"], risk_text(risk),
                     agent["attack_type"], agent["recommended_action"])
        if key == patient:
            related = [
                f"{peer['agent_id']} ({peer['messages']} messages, {peer['verdict']})"
                for peer in agent["related_agents"]
            ]
    summary = (
        f"Patient zero: {patient or '—'}   Origin: {state['origin_ts'] or '—'}\n"
        f"Containment: {state['containment']}   Last action: {state['last_action']}\n"
        f"Related: {', '.join(related) or '—'}\n"
        f"Fleet risk  {sparkline(state['fleet_risk_history'])}"
    )
    return summary, rows, "\n".join(data["events"][-8:]) or "(no events)"


if __name__ == "__main__":
    Sentinel().run()
