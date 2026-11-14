# Sentinel floor plan

A clickable map of how Sentinel fits together: the website, the scoring server, the simulated agent team, and the outside services they use. Every file and web address has a plain-English name and one line on what it does. Three guided flows walk through the main jobs: spotting a hijacked agent, a person stopping an agent, and teaching the models.

**Open it:** download [`sentinel-map.html`](sentinel-map.html) and open it in any browser. It works offline and needs no install.

## What's here

| File | What it is |
|---|---|
| `sentinel-map.html` | The shareable map (no Ask bar, no machine paths). Built from main at `dfa943d`. |
| `architecture.json` | The parts of the system, the links the scanner can't see, the flows and the tour. Edit this to change the map. |
| `descriptions/*.json` | The name and one-line description of every file and web address. |

Everything else in this folder (the build cache, the local page with the Ask bar, the server scripts) is generated and git-ignored.

## Updating it

The map was made with the Floorplan plugin for Claude Code. After code changes, ask Claude Code to "update the floorplan": it re-reads only what changed, then export a fresh copy with `node floorplan/serve.mjs --export floorplan/sentinel-map.html`.
