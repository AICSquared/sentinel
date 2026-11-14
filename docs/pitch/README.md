# Sentinel pitch deck

9 slides, light "L3 Cloud" colours (the same scheme as the website).

| File | Use it for |
|---|---|
| [`sentinel-deck.pdf`](sentinel-deck.pdf) | Viewing or sharing; opens anywhere |
| [`sentinel-deck.pptx`](sentinel-deck.pptx) | Editing in PowerPoint, Keynote or Google Slides |

The live, editable version is in Gamma: https://gamma.app/docs/SENTINEL-2vyzvt4dq8ds67a (any teammate with the link can edit). These files are exports of it; re-export after changes there.

## Slides

1. Cover: one hijacked AI agent can infect its whole team
2. +89% AI-enabled attacks in one year (CrowdStrike 2026 Global Threat Report)
3. 29 min · $11.5M per breach in the US · 65 days (CrowdStrike 2026 · IBM Cost of a Data Breach 2026)
4. How we can help: continuous monitoring, anomaly detection, a human in the loop
5. 3 models → 1 score
6. Demo timeline (agent-47 → agent-20 → agent-53 → a person clicks Quarantine)
7. How it works (top-to-bottom diagram)
8. Attackers need 29 minutes, Sentinel needs about 1 second
9. Next steps

## Before presenting

- Where the numbers come from: 29 min, $11.5M, 65 days and +89% are from the cited reports. About 1 second, 0 false alarms in 688 and 20/20 come from our simulated agent team. 99.6% is Prompt Guard on InjecAgent, real public data.
- Slide 7 says alerts go to **Slack**. The code currently sends them to **Discord** (`src/app/sentinel/_lib/alert.ts`), so if a live alert is shown, it arrives in Discord.
