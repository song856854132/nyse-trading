# Reproducibility

> Status: stub (2026-04-18). Populated progressively as P1 infrastructure TODOs close.
> Full research-pack spec lives under TODO-16 / TODO-5. This file currently covers only
> the pre-commit install step (RALPH-TODO-4 / TODO-30).

## Python + tooling pin

- Python: 3.11 or 3.12 (CI matrix pins both — see `.github/workflows/ci.yml`).
- All runtime + dev deps live in `pyproject.toml`.
- Dependency lockfile (`uv.lock`) is tracked under TODO-5 and not yet committed.

## Local setup

```bash
# From repo root.
pip install -e ".[dev,research]"
pre-commit install
```

The `pre-commit install` step wires `.pre-commit-config.yaml` into `.git/hooks/pre-commit`
so every commit runs the same gates CI enforces plus two local-only guards:

| Hook                     | Checks                                                       |
|--------------------------|--------------------------------------------------------------|
| `gitleaks`               | Secret scan (matches the CI `secret-scan` job).              |
| `ruff-check`             | Lint on `src/` and `tests/` (matches CI `ruff check`).       |
| `ruff-format-check`      | Format drift on `src/` and `tests/` (matches CI).            |
| `mypy`                   | Type check on `src/` per `[tool.mypy]` in `pyproject.toml`.  |
| `holdout-path-guard`     | Iron rule 1: no commits touching `results/holdout/` or paths with a `2024`/`2025` component outside `tests/` or `docs/`. |
| `research-log-chain`     | Iron rule 6: recomputes the SHA-256 chain on every commit that changes `results/research_log.jsonl`. |

## Running the hooks manually

```bash
pre-commit run --all-files          # runs every hook against every tracked file
pre-commit run holdout-path-guard   # single hook, staged files only
pre-commit run --files results/research_log.jsonl
```

## Never skip hooks

Iron rule 5 of `docs/RALPH_LOOP_TASK.md` is absolute: **never commit with `--no-verify`.**
If a hook rejects a commit, fix the root cause. If the guard itself is wrong for a
legitimate case, open a TODO and update the hook — never bypass it silently.

## Pending sections

The full reproducibility pack (research-pack manifest, DuckDB snapshot hash, config
hashes, canonical rerun command) is tracked under TODO-16 and will be appended to this
document when RALPH-TODO-5 (`uv.lock`) and subsequent research-pack work closes.
