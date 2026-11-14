# Study guide for Brandon: two Isolation Forests, scoring, relationship graph

Read with [section-ml.md](section-ml.md). Your stage beats are in [the demo script](../pitch/demo-script.md): the Spread card at 1:05 and the limits at 2:45. You also own the deck, which needs the wording changes in [FIX-INSTRUCTIONS.md](../review/FIX-INSTRUCTIONS.md) (H3-H6).

## Your files, in depth

**`_py/model_anomaly.py`**

*Isolation Forest #1, `filter_train`.* Returns a keep-mask over the training rows. It fits one forest per label with 3% contamination, so each label's strangest 3% are dropped (25 of 735 training rows). Fitting per label matters: a single forest over everything would throw away the attack rows for being unlike clean ones. Labels with under 20 rows are left alone. It records which rows it saw so a test can prove it never touched test data.

*Isolation Forest #2, `fit_baseline`.* Fitted on clean training rows only (429). Inputs are first scaled with the median and a robust spread (interquartile range), so one extreme column cannot dominate. `anomaly(row)` converts the forest's raw score to 0-1 with a two-part line: the clean median maps to 0, the clean 99th percentile to 0.35, and it climbs faster above that until it clips at 1. The two-part shape exists because raw Isolation Forest scores bunch up near the top; a single straight line would never reach 1.

*`project`.* The dot position. Direction comes from a 2-component PCA fitted on the same clean rows. Distance from the centre is the PCA distance plus a push of up to 0.30 from the anomaly score. The push is needed because `touched_decoy` is always 0 on clean data, so PCA gives it no weight, yet an agent that touches a decoy must visibly leave the cluster.

On held-out rows the median anomaly is 0.02 for clean, 1.00 for prompt injection, 0.81 for privilege escalation, 0.64 for data exfiltration and 0.52 for tool misuse.

**`_py/score.py`**

`risk = round(max(0.65*S + 0.35*A, 0.85*S, 0.8*A, 0.9*P))`

- `0.65*S + 0.35*A`: the normal case, trusting the classifier more because it learned from labels.
- `0.85*S`: a confident classifier can reach quarantine alone, for a known attack that looks ordinary to the anomaly model.
- `0.8*A`: the anomaly model can reach quarantine alone, for something the classifier does not recognise.
- `0.9*P`: an injection-like message can reach quarantine alone, before behaviour changes.
- None of the single terms reaches 95, so "terminate" needs the two behaviour models together.

Attack type: `clean` under 40. At 40+, the classifier's label if it is confident; `prompt_injection` if Prompt Guard is what lifted the score; otherwise `unknown`.

The reason sentence picks the two features furthest above the clean baseline, in multiples of normal, with a decoy touch always first. The classifier's top two contributions get a 1.5x boost in that ranking. The sentence is therefore driven by deviation from normal, not directly by SHAP.

The fallback (`fallback_score`) adds fixed points per red flag: decoy +40, message burst +25, out-of-scope +20, and so on, capped at 100. It runs when model files are missing and sets `components.fallback = true`.

`python score.py --report` trains on the training runs and scores the test runs.

**`_py/graph.py`** — a thread-safe list of (time, from, to) for the last 5 minutes. `related(agent, risks)` returns everyone that agent messaged, most messages first, each marked `likely_infected` when it received 10 or more messages **and** its own risk is 40 or more. `edges()` returns the counts for the map.

## Your numbers (blended, held out by run, synthetic)

| What | Result |
|---|---|
| Attack windows at 40+ | 107 / 107 |
| Attack windows at 75+ | 101 / 107 |
| Clean windows at 75+ | 0 / 151 |
| Clean windows at 40+ | 5 / 151, highest 64 |
| Per type, precision / recall | prompt injection 0.78 / 0.78 · tool misuse 1.00 / 1.00 · data exfiltration 0.68 / 0.74 · privilege escalation 1.00 / 0.97 |
| Counting rule alone | 85 / 107 at 40+, 33 / 107 at 75+ |
| Speed | about 4 ms per row |

## What you must know cold

1. **The novel-attack result is not what the deck says.** With tool misuse hidden from the classifier, 20 of 20 windows were flagged, and all 20 reached 75+. But none was labelled `unknown`: the classifier called them prompt injection (12) or privilege escalation (8) at about 98% confidence, while the anomaly model's median was only 52. Hiding each of the other types gives 25/27, 23/23 and 36/37 flagged, again almost never as `unknown`. So say: "flagged, under the wrong name." Do not say the anomaly model caught them.
2. **"0 false alarms in 688"** is 688 agent-ticks from one 3-minute clean run that you reported on the board. It is not in the repo. The reproducible number is 0 of 151 at quarantine level, with 5 of 151 amber.
3. **"3 models"** on slide 5 lists four boxes, and Isolation Forest #1 never contributes to a score.
4. **29 minutes vs 1 second** compares a human intruder's breakout time in a real network with detecting a scripted agent. The overseer ticks every 2 seconds. Present 29 minutes as context.
5. The graph's "now" is the newest message time, so once messages stop the edges stop ageing out.

## The whole system in 60 seconds

"Sentinel is an overseer for a team of AI agents. Eight scripted agents run in Docker and report every action to one service. Every two seconds that service boils each agent's last minute down to ten numbers and scores it with three detectors: a classifier trained on four known attack types, an anomaly model that knows what normal looks like, and a small text model that reads messages for injection attempts. The three are blended into one risk score from 0 to 100 with a reason in plain words. The first agent to cross 75 is named patient zero, and a message graph shows which teammates it flooded and whether they have changed behaviour too. The dashboard shows all of that and gives a person four buttons per agent: quarantine, terminate, dismiss, and release to undo. Nothing happens without that click, and every click is written to an append-only audit log."

## The three questions you are most likely to get

**1. "Why those weights? 0.65, 0.35, 0.85, 0.8?"**
"They were chosen by hand, not tuned, with one rule in mind: any single detector can raise a quarantine recommendation, and none can raise a terminate recommendation alone. The classifier gets more weight because it learned from labelled attacks. We checked the result on held-out runs: every attack window flagged, no clean window at quarantine level."

**2. "How do you decide a teammate is infected and not just a victim of spam?"**
"Two conditions together: it received ten or more messages from the flagged agent in five minutes, and its own behaviour scores 40 or more. Messages alone never mark an agent. In the demo, agent 6 receives a message and stays clean."

**3. "What happens with an attack you've never seen?"**
"We tested it by hiding one attack type during training. It was still flagged in 20 of 20 windows, because bad behaviour shares features: failed calls, out-of-role access. But it was given the wrong name each time. For something that shares nothing with known attacks, the anomaly model can still raise a quarantine recommendation by itself, capped at 80."
