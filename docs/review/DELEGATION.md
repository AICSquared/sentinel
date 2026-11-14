# Audit fix delegation plan

Source: [AUDIT.md](AUDIT.md) + [FIX-INSTRUCTIONS.md](FIX-INSTRUCTIONS.md) (PR #68), audited at `18333e3`, which is still `origin/main` as of 2026-11-14. Every finding is still open.

**Goal:** clear the 4 blockers and the deck NO-GO in about 1 hour of wall-clock, with 5 lanes running in parallel. Each lane owns its own files, so no two lanes edit the same file.

## Step 0: merge order (Alex, 5 min, before any lane opens a PR)

1. **Merge #68** (docs only). Every lane works from FIX-INSTRUCTIONS on main.
2. **Merge #57**, or have lanes A and C rebase on it. #57 touches `package.json` and `src/app/sentinel/page.tsx`, and B4 and B1 edit both of those files. Merging #57 first avoids a conflict. The rest of the website stack (#60 > #64 > #66, plus #61 and #62) has no overlap and can merge whenever it is ready.

## Lanes (start all at once)

| Lane | Who | Tasks (audit ids) | Files | Depends on | Time |
|---|---|---|---|---|---|
| **H** | Alex (human, no code) | "Before presenting" 1-7: bind to 127.0.0.1 (B4), fetch Prompt Guard data + rebuild the overseer (B2), Discord webhook + Supabase health (B3, M7), present from an up-to-date checkout (L10), rehearse | laptop only | nothing | 20 min |
| **A** | Alex's Claude (integrator) | B4 `package.json` `demo` -> `next start -H 127.0.0.1`; M2 README (8 edits); L1 `.env.example`; L8 libomp note; M3 checklist, HANDOFF, delete the two empty docs; **then** B1 part 2: `_data/offline_results.json` + `page.tsx` passes `offline=` | `package.json`, `README.md`, `.env.example`, `CHECKLIST.md`, `docs/handoffs/HANDOFF.md`, `REPO_STRUCTURE.md`, `ORCHESTRATION.md`, `page.tsx`, `_data/offline_results.json` | B1 part 2 needs lane B's V2 numbers + lane C's prop | 60 min |
| **B** | Brandon's Claude | **V2 first:** extend `score.py --report` (75+, amber, first-tick ablation, novel check across all 4 types, fallback only) + 1 test. Post the numbers on #2: lane A needs them | `_py/score.py`, `_py/tests/test_score.py` | nothing | 30 min |
| **B'** | Brandon (human, in Gamma) | H3-H6 deck rewording (slides 4, 5, 7, 8, 9 per the FIX table), re-export PDF + PPTX, update `docs/pitch/README.md` | `docs/pitch/*` | slide 8 numbers: use V2's output | 30 min |
| **C** | Stephen's Claude | B1 part 1: `OfflineResults` type in `_lib/contract.ts` (an addition; Alex OKs it in this plan) + `offline` branch in `results-panel.tsx`; L5 remove the "toward normal" promise in `why-flagged.tsx`; L6 log the swallowed audit error in `live-fleet.tsx` | `_lib/contract.ts`, `_components/results-panel.tsx`, `_components/why-flagged.tsx`, `live-fleet.tsx` | nothing (the type is spelled out in FIX B1) | 40 min |
| **D** | Noah's Claude | Reproduce Prompt Guard on InjecAgent (`prompt_guard.py`) and post precision, recall and the test mix with the command on #2 (feeds the B1 row + slide 8); L9 add InjecAgent `LICENSE` next to the parquet; stand by to help lane H with B2 if the laptop rebuild fails | `_py/data/real/LICENSE-injecagent` | nothing | 20 min |
| **E** | Codex | M5: delete `ossfscorecard.yml` (it's a fragment, not a workflow); fix `code-scan.yml` until it is green on main, or delete it | `.github/workflows/*` | Alex OK (shared files) | 20 min |
| **R** | Gemini | Second, independent check of every number in `offline_results.json` and on slide 8 (AGENTS rule 8); check IBM's 65-day figure against the IBM PDF; `REVIEW` every lane PR | none | lane PRs | ongoing |

### Critical path

`B (V2, 30m)` + `C (panel, 40m)` -> `A: B1 part 2 (15m)` -> Gemini check -> merge. About 60 min. Everything else fits inside that window.

Lane A runs its README and housekeeping edits while B and C work, then does B1 part 2 last, rebased on C's branch. If V2 slips, use the audit's own values, marked "audit check", and correct them when V2 lands.

### Fallback if B1 is not merged in time

Present without scrolling to the Results card (the audit allows this). The demo script in PR #68 already skips it.

## Covered by wording only (no task: say it, using `docs/pitch/demo-script.md` and `docs/study/*`)

H1 (containment is cooperative; `quarantine.sh` is the hard stop), H2 ("the app can only add rows"), M1 (the ablation answer, made reproducible by V2), M6 (quote the blended report only), M8, M9, M10 ("in our simulation").

## After the hackathon (do not start before the demo)

| id | Owner | |
|---|---|---|
| B4 (auth) | Alex's Claude | `getUser()` check in `actOnAgents` / `recordRecommendation` |
| H1 | Alex's Claude | read-only flag volume for agents, action token, per-agent event token |
| H2 | Alex's Claude | new migration: authenticated-only insert, revokes, hash chain; Sentinel rows written by the overseer |
| M4 | Stephen's Claude | `Overseer.act` updates containment |
| M6 | Noah + Brandon | one shared train/test splitter |
| M8, L2, L7 | Stephen + Alex | delete the duplicate fallback, import constants, remove dead code |
| L3, L11, L12 | Brandon | graph clock; fake-mode `/score`; role scopes imported |
| B1 option B | Alex's Claude | `validate.py` + `validation.json` (issue #29) |

## Board posts to send (copy as is)

```
[Alex's Claude] REQ @btowns1041 (Brandon's Claude): audit V2 now: extend score.py --report per docs/review/FIX-INSTRUCTIONS.md#v2, then post the numbers on #2. Lane A's Results card is waiting on them. Brandon: deck H3-H6 in Gamma, using V2's numbers. Plan: docs/review/DELEGATION.md
[Alex's Claude] REQ @Stvn-nn (Stephen's Claude): audit B1 part 1 (OfflineResults type in _lib/contract.ts, Alex OK'd; offline branch in results-panel.tsx), then L5 + L6. PR within 40 min. Plan: docs/review/DELEGATION.md
[Alex's Claude] REQ @KG8-Projects (Noah's Claude): reproduce Prompt Guard on InjecAgent; post P/R, test mix and the command on #2. Then L9 (InjecAgent LICENSE). Stand by for B2 on Alex's laptop.
[Alex's Claude] REQ Alex's Codex: audit M5: delete .github/workflows/ossfscorecard.yml; get code-scan.yml green on main or delete it.
[Alex's Claude] REQ Gemini: independent second check of every number in _data/offline_results.json and on deck slide 8; check IBM's 65-day figure against the IBM PDF; REVIEW the audit-fix PRs.
```
