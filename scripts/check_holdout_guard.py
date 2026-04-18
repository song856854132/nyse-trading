#!/usr/bin/env python3
"""Iron-rule-1 guard: reject commits that touch holdout data.

Invoked by pre-commit with staged filenames as arguments. Exits 0 if the staged
paths are safe, 1 if any path crosses the holdout boundary.

Boundary (mirrors docs/RALPH_LOOP_TASK.md iron rule 1):
  - No staged path may live under results/holdout/.
  - No staged path may contain a directory component equal to "2024" or "2025",
    except under tests/ or docs/ where we legitimately need to describe or test
    holdout-leakage detection.

If this guard ever rejects a path it should not, the answer is NOT --no-verify:
open a TODO, document the exception, and update the guard.
"""

from __future__ import annotations

import sys
from pathlib import PurePosixPath

FORBIDDEN_PREFIX = "results/holdout/"
FORBIDDEN_DATE_COMPONENTS = frozenset({"2024", "2025"})
EXEMPT_PREFIXES = ("tests/", "docs/")


def violates(path: str) -> str | None:
    norm = PurePosixPath(path).as_posix()
    if norm.startswith(FORBIDDEN_PREFIX):
        return f"touches holdout data ({FORBIDDEN_PREFIX}*)"
    if norm.startswith(EXEMPT_PREFIXES):
        return None
    hit = set(PurePosixPath(norm).parts) & FORBIDDEN_DATE_COMPONENTS
    if hit:
        return f"path contains holdout-year component {sorted(hit)}"
    return None


def main(argv: list[str]) -> int:
    bad: list[tuple[str, str]] = []
    for p in argv:
        reason = violates(p)
        if reason:
            bad.append((p, reason))
    if not bad:
        return 0
    print("HOLDOUT GUARD: refusing to commit the following staged paths:", file=sys.stderr)
    for p, reason in bad:
        print(f"  {p} -- {reason}", file=sys.stderr)
    print(
        "\nIron rule 1: holdout data (2024-2025) is off-limits outside tests/ and docs/.\n"
        "If this guard is wrong for a legitimate case, file a TODO and update\n"
        "scripts/check_holdout_guard.py -- do NOT commit with --no-verify.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
