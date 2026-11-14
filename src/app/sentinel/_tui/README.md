# Sentinel ops TUI

From this directory, run:

    python -m pip install -r requirements.txt
    python monitor.py

The monitor polls GET `/agents` every 0.5 seconds. Set `SENTINEL_API_URL` to override the default base URL of `http://localhost:8000`. If a poll fails, the monitor displays **offline · sample** and reads `../_data/live_sample.json`. It reconnects automatically. If the sample also fails, the last display stays visible with an offline notice.

The summary shows patient zero, origin time, related-agent verdicts and containment. Approve or dismiss recommendations in the dashboard. Press `q` to quit.
