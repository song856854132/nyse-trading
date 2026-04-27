#!/usr/bin/env python3
"""Iron-rule-1 guard: reject commits that touch holdout data.

Invoked by pre-commit with staged filenames as arguments. Exits 0 if the staged
paths are safe, 1 if any path crosses the holdout boundary.

Boundary (mirrors docs/RALPH_LOOP_TASK.md iron rule 1):
  - No staged path may live under results/holdout/, EXCEPT for the four paths
    in ``ALLOWED_HOLDOUT_PATHS`` below. Those four filenames were originally
    pre-registered for Wave 7 (GL-0017 iter-26 ensemble holdout) and are
    REUSED bit-identically for Wave 9-D (GL-0025 long-short quintile holdout)
    under a different strategy class -- the guard is filename-scoped, not
    strategy-scoped, so the same allowlist serves both governance rows.
  - No staged path may contain a directory component equal to "2024" or "2025",
    except under tests/ or docs/ where we legitimately need to describe or test
    holdout-leakage detection.

The four allowlisted paths are HARDCODED, not a glob -- this is intentional.
A glob would silently expand if a future edit added new file names; an explicit
allowlist forces a guard edit (and therefore a sha256 cite refresh in BOTH
GL-0017 and GL-0025) for any new holdout artefact. The post-modification
sha256 of THIS file is cited in GL-0017 (Wave 7) and GL-0025 (Wave 9-D) so
that any later edit is tamper-evident under both governance rows.

If this guard ever rejects a path it should not, the answer is NOT --no-verify:
open a TODO, document the exception, and update the guard. If a NEW holdout
artefact needs to land (Wave 7, Wave 9-D, or any later wave), update
``ALLOWED_HOLDOUT_PATHS`` here AND the relevant governance row sha256 cite in
docs/GOVERNANCE_LOG.md in the SAME commit.
"""

from __future__ import annotations

import sys
from pathlib import PurePosixPath

FORBIDDEN_PREFIX = "results/holdout/"
# GL-0017 (Wave 6 pre-registration) + GL-0020 (Wave 7 holdout consumption)
# + GL-0025 (Wave 9-D long-short quintile pre-authorization, iter-34) reuse
# the same four filenames bit-identically. HARDCODED, not a glob.
ALLOWED_HOLDOUT_PATHS = frozenset(
    {
        "results/holdout/.holdout_in_progress",
        "results/holdout/.holdout_used",
        "results/holdout/holdout_result.json",
        "results/holdout/holdout_result.json.sha256",
    }
)
FORBIDDEN_DATE_COMPONENTS = frozenset({"2024", "2025"})
EXEMPT_PREFIXES = ("tests/", "docs/")


def violates(path: str) -> str | None:
    norm = PurePosixPath(path).as_posix()
    if norm.startswith(FORBIDDEN_PREFIX):
        if norm in ALLOWED_HOLDOUT_PATHS:
            return None
        return (
            f"touches holdout data ({FORBIDDEN_PREFIX}*) and is not in the "
            "GL-0017 (Wave 7) / GL-0025 (Wave 9-D) allowlist"
        )
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
        "Exception: the four holdout payload paths in ALLOWED_HOLDOUT_PATHS\n"
        "are pre-registered in docs/GOVERNANCE_LOG.md GL-0017 (Wave 7,\n"
        "ensemble holdout) and GL-0025 (Wave 9-D, long-short quintile holdout).\n"
        "If this guard is wrong for a legitimate case, file a TODO and update\n"
        "scripts/check_holdout_guard.py + the relevant GL row sha256 cite\n"
        "(GL-0017 and/or GL-0025) -- NEVER --no-verify.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
