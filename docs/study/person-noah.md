# Study guide for Noah: dataset, features, supervised XGBoost, Prompt Guard

Read with [section-ml.md](section-ml.md). Your stage beats are in [the demo script](../pitch/demo-script.md): explaining the dots at 0:25 and the results at 2:35.

## Your files, in depth

**`_py/make_dataset.py` -> `_py/data/actions.csv`** — 997 rows, seed 7, fully synthetic. It simulates 50 runs (10 clean, 10 per attack type), each with 8 agents for 90 seconds, at the raw-event level: the same JSON the Docker agents send. Events go through the real `RowBuilder`, one row per agent every 2 seconds from second 10, giving 16,228 rows. It then samples 590 clean, 170 prompt injection and 75 of each other type, and adds 12 junk rows.

How each attack looks in the data:
- **Prompt injection:** often a decoy touch first, then a burst of messages to 2-7 peers, plus a few risky tool calls. It can spread to a peer that received 4+ messages.
- **Tool misuse:** many unusual tools at high speed, about 45% failing.
- **Data exfiltration:** reads out-of-scope data and posts 15-150 KB chunks outward.
- **Privilege escalation:** repeated denied attempts to assume admin roles; rarely a decoy, no extra messages.

Attack strength is random (0.35 to 1.0), so some attacks are subtle. A row is labelled as an attack when its window contains at least one malicious event.

**`_py/features.py`** — `window_row` computes the ten inputs from a list of events. `RowBuilder` keeps a 60-second sliding window per agent and also attaches `prompt_risk`, the highest Prompt Guard probability among that window's messages (each message is scored once and cached). `load_dataset` reads the CSV, drops rows with a missing value (4 of 997) and deliberately keeps rows with impossible values for Isolation Forest #1 to remove. `baselines.json` holds each role's median tool count on clean data.

**`_py/model_supervised.py`** — `split` divides by `run_id`, stratified so every attack type has test runs. `train` asks Isolation Forest #1 for a keep-mask on the training split, then fits XGBoost (200 trees, depth 4, five classes). `predict` returns the label, `p_attack` = 1 minus P(clean), and the top three positive per-row contributions toward the most likely attack class (`pred_contribs=True`). `report` gives precision and recall per type.

**`_py/prompt_guard.py`** — TF-IDF on character 3-5-grams and word 1-2-grams, then logistic regression with balanced classes. Trained on the Hugging Face set `jayavibhav/prompt-injection-safety` (20,000 sampled rows; labels "injection" and "harmful request" both count as positive). Tested only on InjecAgent. `train` refuses to run if any training text also appears in InjecAgent or in the swarm's payloads.

**`_py/fetch/`** — seeded download scripts that record source, revision, licence and SHA-256 in `data/real/SOURCE.md`. Data without a redistribution licence is git-ignored.

## Your numbers

Classifier alone, `python model_supervised.py`, 319 rows from 15 held-out runs:

| Type | Precision | Recall |
|---|---|---|
| clean | 0.99 | 1.00 |
| prompt injection | 0.93 | 0.96 |
| tool misuse | 1.00 | 0.62 |
| data exfiltration | 0.81 | 0.81 |
| privilege escalation | 0.74 | 0.93 |
| any attack vs clean | 1.00 | 0.99 |

The README quotes different per-type numbers (prompt injection 0.78 / 0.78, and so on). Those are from `score.py --report`, which measures the blended output on a different split. On stage, quote the blended ones and say "held out by run". If asked why two sets exist, that is the reason.

Prompt Guard on InjecAgent: precision 0.996, recall 0.636. The test set is 2,108 attacks and 34 benign rows, so always give recall and the mix alongside precision. The audit could not reproduce this on Alex's laptop because the training file is not there; your Docker run on your PC is the evidence.

## What you must know cold

1. **Why synthetic.** No public dataset has per-agent action logs. You checked the Kaggle candidate against four tests; it failed two (no telemetry columns, no per-window labels). The write-up is `data/DATASET.md`.
2. **The feedback feature.** `sec_since_normal` is XGBoost's most important feature (0.30). In `actions.csv` it is above zero on 344 of 399 attack rows and on no clean row. Your generator delays and sometimes withholds it so it is not a perfect shortcut, and the audit's check shows the system does not depend on it: with it forced to zero, 107 of 107 attack windows are still flagged and 95 reach quarantine level.
3. **Which attack vs any attack.** The classifier is near-perfect at "attack or not" and much weaker at naming the type, especially tool misuse (recall 0.62 alone) and data exfiltration.
4. **Small test set.** About three held-out runs per attack type. Per-type numbers move between splits.
5. **Licence.** The Prompt Guard training set declares no licence. It is used locally and never redistributed. InjecAgent is MIT.

## The whole system in 60 seconds

"Sentinel is an overseer for a team of AI agents. Eight scripted agents run in Docker and report every action to one service. Every two seconds that service boils each agent's last minute down to ten numbers and scores it with three detectors: a classifier trained on four known attack types, an anomaly model that knows what normal looks like, and a small text model that reads messages for injection attempts. The three are blended into one risk score from 0 to 100 with a reason in plain words. The first agent to cross 75 is named patient zero, and a message graph shows which teammates it flooded and whether they have changed behaviour too. The dashboard shows all of that and gives a person four buttons per agent: quarantine, terminate, dismiss, and release to undo. Nothing happens without that click, and every click is written to an append-only audit log."

## The three questions you are most likely to get

**1. "Your data is synthetic. Why should we believe the results?"**
"Believe them for what they are: evidence that the pipeline separates the behaviours we defined, on runs it never saw. We generated events, not feature rows, and pushed them through the same code the live system uses, with random attack strength so some are subtle. What it cannot show is how real hijacked agents behave. The one part we could test on real data, the text model, we did."

**2. "How did you avoid leakage?"**
"Three ways. We split by run, because windows from one run overlap. The data cleaner is fitted on the training split only. And Prompt Guard's training refuses to start if any text overlaps its test set."

**3. "What are the ten features, and which matter?"**
"Rates and counts over one minute: actions, tools, failed calls, messages, peers, bytes out; two flags, decoy touched and out-of-role access; the role's normal tool count; and time since the agent last looked normal. The strongest are time since normal, the decoy, and out-of-role access. None of them reads message content."
