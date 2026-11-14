"""Sentinel ops monitor — a terminal view of the agent swarm.

Run standalone (reads the sample file):
    python -m pip install textual
    python monitor.py

Later, point DATA_URL at the FastAPI service instead of the file.
It degrades gracefully: if the source is missing, it shows the last values and an 'offline' note.
"""
from __future__ import annotations
import json
import pathlib
from datetime import datetime

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

# For the demo this reads a file. Swap to an HTTP poll of GET /agents when the API exists.
DATA_FILE = pathlib.Path(__file__).parent.parent / "_data" / "live_sample.json"
REFRESH_SECONDS = 0.5


def risk_text(risk: int) -> Text:
    if risk >= 80:
        return Text(f"{risk:>3}", style="bold white on red")
    if risk >= 40:
        return Text(f"{risk:>3}", style="black on yellow")
    return Text(f"{risk:>3}", style="green")


def dot(risk: int) -> Text:
    if risk >= 80:
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
    #events { height: 10; padding: 0 2; border: round $panel; }
    DataTable { height: 1fr; }
    """
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Static(id="sentinel")
            yield DataTable(id="agents", zebra_stripes=True)
            yield Static(id="events")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#agents", DataTable)
        table.add_columns(" ", "agent", "role", "risk", "attack type", "recommended")
        self.set_interval(REFRESH_SECONDS, self.refresh_data)
        self.refresh_data()

    def refresh_data(self) -> None:
        try:
            data = json.loads(DATA_FILE.read_text())
            offline = ""
        except Exception:
            return  # keep last values on a bad read
        s = data.get("sentinel", {})
        spark = sparkline(s.get("fleet_risk_history", []))
        self.query_one("#sentinel", Static).update(
            Text.assemble(
                ("SENTINEL  ", "bold"),
                (f"patient-zero: {s.get('patient_zero','-')}   ", "red bold"),
                (f"containment: {s.get('containment','-')}   ", "yellow"),
                (f"last: {s.get('last_action','-')}\n", "white"),
                (f"fleet risk  {spark}", "cyan"),
            )
        )
        table = self.query_one("#agents", DataTable)
        table.clear()
        for a in data.get("agents", []):
            r = int(a.get("risk", 0))
            table.add_row(dot(r), a["agent_id"], a.get("role", "-"), risk_text(r),
                          a.get("attack_type", "-"), a.get("recommended_action", "-"))
        log = "\n".join(data.get("events", [])[-8:])
        self.query_one("#events", Static).update(Text(log or "(no events)", style="dim"))


if __name__ == "__main__":
    Sentinel().run()
