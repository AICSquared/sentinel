# Study guide: the machine learning

Files: `src/app/sentinel/_py/` — `make_dataset.py`, `features.py`, `model_anomaly.py`, `model_supervised.py`, `prompt_guard.py`, `score.py`. Numbers are from [the audit](../review/AUDIT.md#1f-numbers-you-can-quote-and-where-each-comes-from).

## What it does

Turns each agent's last 60 seconds into ten numbers, and turns those ten numbers into one risk score from 0 to 100, an attack name and a one-sentence reason. This happens for every agent every 2 seconds, on a CPU, in about 4 ms per agent.

## How it works

**1. The dataset (`make_dataset.py`, `data/actions.csv`).** 997 rows, fully synthetic, seed 7. We simulate 50 runs of 8 agents for 90 seconds each: 10 clean runs and 10 runs for each of four attack types. In an attack run, one agent turns rogue between 20 and 40 seconds in, at a random strength, so some attacks are loud and some subtle. Prompt injection can spread to a peer. Each row is one agent's 60-second window, labelled with the attack type if that window holds at least one malicious event. Twelve deliberately broken rows are mixed in.

**2. The features (`features.py`).** Ten numbers per window: actions per minute, different tools used, the normal tool count for the agent's role, failed calls per minute, touched a decoy (0/1), used something outside its role (0/1), messages to agents per minute, different agents messaged, bytes sent out per minute, and seconds since the agent last looked normal. The simulator and the live overseer call the same `RowBuilder` class.

**3. Two Isolation Forests, and why two (`model_anomaly.py`).** An Isolation Forest finds points that are easy to separate from the rest.
- **#1, `filter_train`, cleans the training data.** Fitted per label on the training split only, it drops the 3% strangest rows of each label (25 of 735). It exists so glitched rows don't teach the classifier nonsense. It never runs at scoring time.
- **#2, `fit_baseline`, is a detector.** Fitted only on clean rows (429 of them), it answers "how unlike normal is this window?" as 0 to 1. A PCA fitted on the same clean rows gives each dot its place on the scatter.
- They are separate objects because they answer different questions on different data. Using one forest for both would let attack rows into the definition of "normal".

**4. XGBoost (`model_supervised.py`).** A gradient-boosted tree classifier with five classes: clean and the four attacks. It outputs `p_attack` (1 minus the probability of clean), the most likely label, and for each row the features that pushed hardest toward that label (XGBoost's built-in per-row contributions, the same maths as TreeSHAP). Those feed the "why flagged" bars.

**5. Prompt Guard (`prompt_guard.py`).** A small text model (TF-IDF of character and word n-grams, then logistic regression) that gives each message a probability of being an injection. Trained on one public dataset, tested on a different one.

**6. The blend (`score.py`).** With S, A and P as the three scores on a 0-100 scale:

`risk = round(max(0.65*S + 0.35*A, 0.85*S, 0.8*A, 0.9*P))`

In words: normally a weighted mix that trusts the classifier most. But any one detector can raise the alarm alone, up to a cap: the classifier to 85, the anomaly model to 80, the text model to 90. Reaching 95 (terminate) needs both behaviour models to agree. Tiers: under 40 watch, 40-74 slow down, 75-94 quarantine, 95+ terminate.

**7. Split by run, and why it matters.** Windows overlap: one agent's window at second 40 and at second 42 share 58 seconds of events. If we split rows at random, near-copies of training rows would land in the test set and the scores would look far better than they are. So whole runs go to train or to test, never both. Isolation Forest #1 is also fitted on the training side only.

## Key decisions and why

| Decision | Why |
|---|---|
| Synthetic data | No public dataset has per-agent action logs. The Kaggle candidate was checked and holds threat-intel tables instead (`data/DATASET.md`) |
| Trees, not a neural net | 1,000 rows, ten features, CPU only, and we need per-row explanations |
| `max(...)` in the blend | Detectors fail differently. A quiet data theft barely moves the anomaly score; a brand-new attack may not move the classifier |
| Caps below 95 for a single detector | The harshest recommendation should never rest on one model |
| Medians for baselines | One busy agent shouldn't shift what "normal" means |

## Likely judge questions

**"Why two Isolation Forests?"** "One cleans the training data and is thrown away. The other learns what normal looks like and runs live. Different jobs, different data."

**"How do you know you didn't overfit?"** "We split by run, so no test window overlaps a training window. On those held-out runs: 107 of 107 attack windows flagged, 0 of 151 clean windows at quarantine level. Each attack type only has about three held-out runs, so the per-type numbers are rough."

**"What does the anomaly model add?"** "A second opinion that needs no labels. On its own it rates held-out prompt-injection windows at the maximum and clean windows near zero. It also places the dots."

**"Your top feature depends on your own previous score."** "Yes, so we tested with it zeroed: still 107 of 107 flagged and 95 at quarantine level."

**"How good is the text model?"** "On InjecAgent, which it never trained on: 99.6% precision and 64% recall. The test set is almost all attacks, 2,108 to 34, so precision flatters it; recall is the honest number. It misses about a third."

## Honest limits to state

- The behaviour data is simulated: the attack shapes are our assumptions.
- Per-type results are weak for two types: data exfiltration 0.68 / 0.74 and prompt injection 0.78 / 0.78 (blended, held out). The system is much better at "is this an attack" than "which attack".
- A hidden attack type was flagged 20 of 20 times but always under the wrong name, never as "unknown".
- The anomaly model needs a clean baseline.
- On the laptop audited, the overseer was built without the Prompt Guard file, so live `prompt` was 0. Check before claiming three live detectors.
