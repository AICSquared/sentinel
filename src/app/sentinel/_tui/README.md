# Sentinel ops TUI

A terminal view of the agent swarm and Sentinel, for the team to watch during the demo.

## Run
    python -m pip install -r requirements.txt
    python monitor.py        # reads ../_data/live_sample.json

Press `q` to quit.

## Data source
For the demo it reads `../_data/live_sample.json`. To go live, replace the file read in
`refresh_data()` with an HTTP GET to the FastAPI service (`GET /agents`), keeping the same shape:
`{ sentinel: {...}, agents: [...], events: [...] }`. It degrades gracefully if the source is down.
