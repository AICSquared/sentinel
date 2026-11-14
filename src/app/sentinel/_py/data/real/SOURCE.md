# Real-data samples (`_py/data/real/`)

Written by `_py/fetch/fetch_all.py`; do not edit by hand. Each sample is seeded and
stratified, so a rerun gives the same SHA-256. Samples whose licence does not allow
redistribution are git-ignored (see `.gitignore` here) and a human fetches them.

## injecagent

- **Source:** https://github.com/uiuc-kang-lab/InjecAgent
- **Revision:** f19c9f2c79a41046eb13c03c51a24c567a8ffa07
- **Licence:** MIT (Copyright (c) the InjecAgent authors; see LICENCE in the source repo)
- **In git:** yes
- **Fetched:** 2026-11-14 06:51 UTC
- **Rows:** 2142 sampled from 2142
- **Label counts:** {'0': 34, '1': 2108}
- **File:** `injecagent.parquet`, SHA-256 `68244fe919bf91681c2094317f4a3793eb69034a4c37cb1da21d4b4846fd4fe3`
- **Notes:** Test set only. label 1 = tool response with an injected attacker instruction (base + enhanced); label 0 = InjecAgent's benign user instructions and clean tool-response templates.

## prompt_safety

- **Source:** https://huggingface.co/datasets/jayavibhav/prompt-injection-safety
- **Revision:** c0f55c8817fb2d4da72ac7b06deba6033da6fad6
- **Licence:** none: the dataset card declares no licence, and the owner has not answered the open licence question (huggingface.co/datasets/jayavibhav/prompt-injection-safety/discussions/3, since 2026-07-03). Confirmed 2026-11-14: local training only, never redistributed
- **In git:** no (git-ignored; run the fetch)
- **Fetched:** 2026-11-14 07:21 UTC
- **Rows:** 20000 sampled from 59193
- **Label counts:** {'0': 9451, '1': 9130, '2': 1419}
- **File:** `prompt_safety.parquet`, SHA-256 `1eb88bc0b90bdc3e7bf930c915b6cea2b61bef3a153e96ae7205ba453fcd9705`
- **Notes:** Training data for Prompt Guard. Labels: 0 benign, 1 prompt injection, 2 harmful request. Exact-duplicate texts dropped before sampling; stratified by (split, label), seed 7.
