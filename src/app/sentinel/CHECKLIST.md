# Sentinel track (Cisco, Mission 3)

State: active
Video:
Submitted: no

Plan and frozen contracts: [docs/plans/sentinel.md](../../../docs/plans/sentinel.md). Check a box only when the proof is in the repo (a merged PR or a file).

## Must-haves
- [ ] **C1** Contracts frozen in code: `_py/contract.py`, `_lib/contract.ts`, `_data/live_sample.json` + `_data/demo_timeline.json` match contract B2
- [ ] **C2** ~1,000 labeled agent actions in `_py/data/actions.csv`, with the dataset decision (Kaggle or our own) and its licence written down
- [ ] **C3** Supervised model: XGBoost trained after IsoForest #1 cleaning (train split only); per-attack-type precision/recall reported
- [ ] **C4** Anomaly model: IsoForest #2 on the clean baseline flags novel behaviour; 2-D positions for the scatter
- [ ] **C5** One blended 0-100 risk with a plain-language reason, the tier table, and a frequency-count fallback
- [ ] **C6** Relationship map: partners, message counts, likely_infected vs likely_clean
- [ ] **C7** API: `POST /events`, `POST /score`, `GET /agents` match the frozen contracts; fake mode works
- [ ] **C8** Docker swarm: 8 scripted agents + overseer from one compose file; `trigger.sh` starts one attack; runs on Podman too
- [ ] **C9** Dashboard: live scatter (rogue drifts out, turns red), patient-zero card (time of origin, requests, systems touched), related agents, reasons; only 3-5 numbers animate
- [ ] **C10** Human-gated response: approve/dismiss, Discord alert, every decision in the insert-only Supabase `audit_log`; no auto-enforcement
- [ ] **C11** Demo mode: `/sentinel` plays the timeline with no network and no keys (`pnpm demo`)
- [ ] **C12** Validation: detection rate, false-quarantine rate, containment speed, with vs without Sentinel, medians; one run hand-checked
- [ ] **C13** Problem statement, honest limits and the 3-minute script in `README.md`, rehearsed once
- [ ] **C14** Backup video recorded by 2:30pm Saturday and linked above
- [ ] **C15** Ops TUI reads `GET /agents` live and falls back to the sample file

## Nice-to-haves (only after every must-have is checked)
- [ ] Markov-chain next-step prediction
- [ ] Human-gated retraining queue (prevents data poisoning)
