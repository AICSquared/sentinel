# Sentinel ops TUI

From this directory, run:

    python -m pip install -r requirements.txt
    python monitor.py

The monitor polls GET `/agents` every 0.5 seconds. Set `SENTINEL_API_URL` to override the default base URL of `http://localhost:8000`. If a poll fails, the monitor displays **offline · sample** and reads `../_data/live_sample.json`. It reconnects automatically. If the sample also fails, the last display stays visible with an offline notice.

The summary shows patient zero, origin time, related-agent verdicts and containment. Approve or dismiss recommendations in the dashboard. Press `q` to quit.

## Two-terminal review demo

Open both terminals at the repository root with the same Python environment active. Leave port 8010 free at the start.

1. In Terminal 1, install the demo dependencies and start the monitor.

   ```bash
   python -m pip install -r src/app/sentinel/_tui/requirements.txt 'fastapi>=0.100' 'pydantic>=2' uvicorn
   SENTINEL_API_URL=http://127.0.0.1:8010 python src/app/sentinel/_tui/monitor.py
   ```

   Look for **offline · sample** and eight agents. The sample already shows agent-47 as patient zero.

2. In Terminal 2, start the fake API.

   ```bash
   cd src/app/sentinel/_py
   SENTINEL_FAKE=1 python -m uvicorn api:app --host 127.0.0.1 --port 8010
   ```

   Terminal 1 switches to **API connected**. The timeline starts with a clean fleet. Watch for agent-47 to appear as patient zero, then compare the verdicts for agent-20 and agent-6.

3. Press Ctrl+C in Terminal 2. Terminal 1 switches back to **offline · sample**. Press q in Terminal 1 to exit.
