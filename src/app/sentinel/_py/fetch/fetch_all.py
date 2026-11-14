"""Run every real-data fetch and print a summary (issue #24, T3).

    python src/app/sentinel/_py/fetch/fetch_all.py

Needs network for InjecAgent and the HF safety set. Kaggle and NetFlow need a
human first (login / browser download into data-cache/); without that they
skip with instructions. A failure in one source never stops the others.
Never run during the Docker build: the build only reads data/real/.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

try:
    from . import common, fetch_injecagent, fetch_kaggle_prompts, fetch_netflow, fetch_prompt_safety
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import common  # type: ignore[no-redef]
    import fetch_injecagent  # type: ignore[no-redef]
    import fetch_kaggle_prompts  # type: ignore[no-redef]
    import fetch_netflow  # type: ignore[no-redef]
    import fetch_prompt_safety  # type: ignore[no-redef]

log = logging.getLogger("sentinel.fetch")

STEPS = (
    ("injecagent", fetch_injecagent.main),
    ("prompt_safety", fetch_prompt_safety.main),
    ("kaggle_prompts", fetch_kaggle_prompts.main),
    ("netflow", fetch_netflow.main),
)


def main() -> int:
    failed = 0
    for name, fn in STEPS:
        try:
            meta = fn()
            if name == "netflow":  # one result per NetFlow dataset
                for sub, m in meta.items():
                    print(f"{sub:<16} {'SKIPPED: ' + m['skipped'] if 'skipped' in m else str(m['rows']) + ' rows  ' + m['sha256'][:16]}")
            else:
                print(f"{name:<16} {meta['rows']} rows  {meta['sha256'][:16]}  labels {meta['label_counts']}")
        except common.SkipFetch as exc:
            print(f"{name:<16} SKIPPED: {exc}")
        except Exception as exc:  # report and carry on with the next source
            failed += 1
            log.exception("%s failed", name)
            print(f"{name:<16} FAILED: {exc}")
    common.write_source_md()
    print(f"SOURCE.md -> {common.REAL_DIR / 'SOURCE.md'}")
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
