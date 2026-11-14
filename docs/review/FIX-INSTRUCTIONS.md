# Fix instructions (from the audit)

For the agents and people who will implement the fixes in [AUDIT.md](AUDIT.md). Each task has the same id as its finding. The audit changed no code; nothing here is done yet.

Rules for every task:
- One task per branch and PR, title `sentinel: <what>`. Stage only the files listed. `pnpm check` before each commit, `pnpm build` before the PR, and `cd src/app/sentinel/_py && python -m pytest -q` if you touched Python.
- Edit only files you own (AGENTS.md section 4). The owner is named on each task; if it is not you, `REQ` them on #2.
- A human merges. Never invent a number: every figure must come from a command you ran, and the command goes in the PR body.
- The contracts are frozen. Additions only.

Order: the "Before presenting" block first (no code, 15 minutes), then B1, then the wording tasks (H3-H6, M2), then the rest if time allows.

---

## Before presenting (a person does these; no code)

1. **Bind the dashboard to localhost (B4).** Start it with:
   ```bash
   pnpm build && pnpm exec next start -H 127.0.0.1
   ```
   Check: `lsof -nP -iTCP:3000 -sTCP:LISTEN` shows `127.0.0.1:3000`, not `*:3000`.
2. **Use the current code (L10).** In the folder you present from: `git fetch && git status -sb`. It must not say "behind". The main checkout on Alex's laptop was 8 commits behind with local edits in `_tui/`.
3. **Prompt Guard in the overseer (B2).** A person runs the download (it fetches a public Hugging Face dataset with no declared licence; it stays local and git-ignored):
   ```bash
   cd src/app/sentinel/_py && python fetch/fetch_prompt_safety.py
   cd ../../../.. && docker compose -f docker/compose.yml up --build -d overseer && docker/reset.sh
   docker exec sentinel-overseer-1 ls artifacts          # must list prompt_guard.joblib
   ```
   Then `docker/trigger.sh agent-47`, wait 10 s, and check `curl -s localhost:8000/agents` shows a `"prompt"` value above 0 for agent-47. Run `docker/reset.sh` afterwards. If any step fails, do not claim three live models: say "two behaviour models live, the text model validated offline".
4. **Audit log and alert (B3, M7).** `curl -s localhost:3000/api/health` must return `"supabase":true,"demo":false`. Confirm both migrations are applied in the Supabase project (the `audit_log` table exists). Add `DISCORD_WEBHOOK_URL=` to `.env.local`, rebuild, do one rehearsal click and confirm a row appears in Supabase and a message in Discord. If there is no webhook, cut the alert beat from the script.
5. **Open the page as `http://localhost:3000/sentinel`**, never by IP address (the overseer's CORS rule allows localhost only).
6. **Have the Supabase table editor open on `audit_log` in a second tab.** The dashboard has no audit-log view; this tab is how you show the row.
7. **Rehearse once from `docker/reset.sh`**, wait 20 s for the baseline, and time it.

---

## B1 · Fill the Results card with numbers we can reproduce

Owner: Alex (`page.tsx`, `_data/*`), Stephen (`_components/results-panel.tsx`). About 45 minutes.

Problem: the dashboard shows "The validation runs have not been done yet."

Do this (option A, fast and honest):

1. Stephen: add a second, simpler shape to `results-panel.tsx`. Keep the existing `Validation` branch untouched. New optional prop `offline?: OfflineResults | null`, rendered when `results` is null and `offline` is set. Add the type to `_lib/contract.ts` (an addition, so allowed; `REQ` Alex):
   ```ts
   export type OfflineResults = {
     generated: string;                      // ISO date the commands were run
     rows: { label: string; value: string; source: DataSource; how: string }[];
   };
   ```
   Render a heading "What we measured", then one row per item: label, value, a small tag reading "synthetic" or "real", and the `how` text in `text-ink-3`. No new colours. If both props are null, keep today's sentence.
2. Alex: create `src/app/sentinel/_data/offline_results.json` with exactly these rows. Re-run each command first and use what **you** get; these are the audit's values:

   | label | value | source | how |
   |---|---|---|---|
   | Attack windows flagged (risk 40+) | 107 of 107 | synthetic | `score.py --report`, test runs never seen in training |
   | Attack windows at quarantine level (75+) | 101 of 107 | synthetic | V2 below |
   | Clean windows wrongly at quarantine level | 0 of 151 | synthetic | `score.py --report` |
   | Clean windows wrongly amber (40-74) | 5 of 151 | synthetic | V2 below |
   | An attack type hidden from the classifier | 20 of 20 flagged, all given the wrong name | synthetic | `score.py --report` |
   | Prompt Guard on InjecAgent | precision 0.996, recall 0.64 (2,108 attacks, 34 benign) | real | `prompt_guard.py`; only if you reproduced it |
   | Scoring speed | about 4 ms per agent | synthetic | `score.py --report` |

3. Alex: in `page.tsx`, import the JSON and pass `offline={offline}`. Leave `validation={null}` and its comment.
4. Check in the browser at 1280 px and 375 px, in live and demo mode.

Option B (the real fix, issue #29): write `_py/validate.py` as the plan describes (20 seeded runs per arm with `swarm.AgentSim` in simulated time, with / without / fallback-only), write `_data/validation.json` in the existing `Validation` shape, pass it in `page.tsx`. Only if there is time after everything else. Until then every with/without number stays **[TODO: run validate.py]**.

---

## V2 · Put the audit's extra checks into `score.py --report`

Owner: Brandon (`_py/score.py`, `_py/tests/test_score.py`). About 30 minutes. This turns the audit's one-off numbers into something anyone can reproduce, and answers M1 and H5.

In `report()` in `score.py`, after the existing summary line, also compute and print (and return in the dict):

1. `attack rows scored 75+: N/107` and `clean rows scored 40+: N/151 (highest R)`.
2. **First-tick check:** score a copy of every test row with `sec_since_normal` set to 0.0; print `with sec_since_normal forced to 0: attacks 40+ N/107, 75+ N/107; clean 75+ N/151`.
3. **Novel check, all four types:** loop `holdout` over the four attack types (today it only does `tool_misuse`). For each print flagged at 40+, at 75+, and a count of the labels given (`collections.Counter(o["attack_type"] ...)`).
4. **Fallback only:** `fallback_score(r)` over the test rows: attacks at 40+ and 75+, clean at 40+.

Expected values from the audit (same seed, same data): 101/107; 5/151, highest 64; 107/107 and 95/107 and 0/151; tool misuse 20/20 and 20/20 labelled prompt_injection 12 + privilege_escalation 8; prompt injection 25/27; data exfiltration 23/23; privilege escalation 36/37; fallback 85/107, 33/107, 0/151. If yours differ, report yours and say so on #2.

Add one test asserting the report dict has the new keys. Do not change the scoring formula.

---

## H3-H6 · Deck wording (Brandon, in Gamma; re-export PDF and PPTX to `docs/pitch/`)

| Slide | Now | Change to |
|---|---|---|
| 4 | "Anomaly Detection: Flags never-seen attacks" | "Anomaly Detection: scores anything unlike normal behaviour" |
| 5 | "3 models -> 1 score" over four boxes | "3 detectors -> 1 score": XGBoost, Isolation Forest, Prompt Guard. Move "Isolation Forest #1: cleans the training data" to a small "before training" note |
| 7 | Slack | Discord |
| 8 title | "29 min vs ~1 s. Attackers need 29 minutes. Sentinel needs about 1 second." | "Attackers move in 29 minutes. Sentinel scores every agent every 2 seconds." |
| 8 | "0 false alarms in 688" | "0 of 151 clean windows recommended for quarantine (5 went amber)" |
| 8 | "20/20 new attacks flagged" | "20 of 20 windows of an unseen attack type flagged" |
| 8 | "99.6% precision" | "Prompt Guard on real data: 99.6% precision, 64% recall" |
| 8 | "3 ms per score" | "about 4 ms per score" (or re-measure on the presenting laptop) |
| 8 footnote | as is | add "simulated agent team, synthetic telemetry, held out by run" |
| 9 | "Add real quarantine and termination" | "Enforce quarantine below the agent (container or network level), so a hijacked agent cannot refuse it" |

Also update `docs/pitch/README.md` "Before presenting" to match.

---

## M2 · README matches the product

Owner: Alex (`README.md`). About 20 minutes. Change only these passages:

1. Intro paragraph under "Run it": replace "asks a human to approve or dismiss. To act on an approval, a **person** runs: `docker/quarantine.sh ...`" with: "and shows what it recommends for each agent. A person clicks Quarantine, Terminate or Dismiss per agent; Release undoes it. `docker/quarantine.sh agent-47` is a second, harder stop: it pauses the container."
2. "Optional: audit log and alerts": "Approve and Dismiss are written" -> "Every Quarantine, Terminate, Release and Dismiss click is written". Add `DISCORD_WEBHOOK_URL` to the list of keys and to `.env.example` (L1; `.env.example` is Alex's).
3. "How it works" table, Known attacks row: "per-row feature contributions become the plain-language reason and the 'why flagged' bars" -> "per-row feature contributions feed the 'why flagged' bars; the plain-language reason names what is furthest above the agent's normal".
4. Results table: add the amber row (5 / 151), add tool misuse 1.00 / 1.00, change "about 3 ms" to what you measure, and replace the "5 x 10 min" live row with a figure that has a file or command behind it, or delete it.
5. "Not done yet": remove "Prompt Guard running inside the live overseer image"; add "it is in the image only when `fetch/fetch_prompt_safety.py` was run before the build".
6. Honest limits: change "is reported as `unknown`" to "may be flagged under the wrong name; in our hold-out test it always was". Add: "Quarantine here is a flag the simulated agent obeys. A real hijacked agent could ignore it, so real enforcement belongs below the agent."
7. Last line: remove the links to `ORCHESTRATION.md` and `REPO_STRUCTURE.md`, or fill those files (M3).
8. Commands: add "On macOS, native test runs need `brew install libomp`".

---

## M3 · Housekeeping (Alex)

- `src/app/sentinel/CHECKLIST.md`: tick only boxes with proof in the repo. With proof today: C1, C2, C3, C4, C5, C6, C7, C8, C9, C11, C15. Not yet: C10 (alert untested), C12 (no validation), C13 (script lives in `docs/pitch/demo-script.md`; link it), C14 (no video link).
- `docs/handoffs/HANDOFF.md`: replace the template text with five lines: what is done, what is left (this file), where the demo script is.
- `REPO_STRUCTURE.md`, `ORCHESTRATION.md`: delete, or write 10 lines each.
- `src/lib/tracks.ts`: set `ready: true` only when the checklist is complete.

## M5 · CI (whoever added the workflows)

`.github/workflows/ossfscorecard.yml` is not a workflow. Either delete it or replace it with the official Scorecard starter workflow. Fix or delete `code-scan.yml` until it passes on `main`.

---

## After the hackathon (do not start these before the demo)

| id | Owner | Change |
|---|---|---|
| B4 | Alex | In `actOnAgents` and `recordRecommendation`, return early unless `getUser()` is non-null when Supabase is configured. Change `demo` in `package.json` to `next build && next start -H 127.0.0.1` |
| H1 | Alex | Second named volume for `quarantine/` and `terminate/`, mounted `:ro` in agents and read-write in the overseer. `SENTINEL_ACTION_TOKEN` env on the overseer and the Next server, checked on `POST /agents/{id}/action`. Per-agent token on `POST /events` |
| H2 | Alex | New migration (never edit the old one): drop the two policies; `for insert to authenticated with check (decided_by = (select auth.uid())::text)`; `for select to authenticated`; `revoke update, delete, truncate on audit_log from anon, authenticated`; add `prev_hash` and `row_hash` columns filled by a trigger. Write Sentinel's own rows from the overseer |
| M4 | Stephen | In `Overseer.act`, set `self.containment` to `approved` on quarantine or terminate and `dismissed` on dismiss when nothing is left undecided |
| M6 | Noah + Brandon | One splitter in one module; both reports use it |
| M8, L2, L7 | Stephen, Alex | Delete `api.py`'s `_fallback_score`, import constants from `contract.py`, delete the dead components and `decide()` |
| L3 | Brandon | `Graph._counts` uses wall-clock time passed by the caller |
| L9 | Noah | Add InjecAgent's `LICENSE` text beside the parquet file |
