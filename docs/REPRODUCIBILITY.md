# Reproducibility

> Status: partial (2026-04-18). Populated progressively as P1 infrastructure TODOs close.
> Full research-pack spec (research-pack manifest, DuckDB snapshot hash, canonical rerun
> command) still lives under TODO-16 and will be appended here when that TODO closes.
> This file currently covers: Python pin, dependency lockfile (`uv.lock`), pre-commit
> install, and hash-chain verification.

## Python + tooling pin

- Python: 3.11 or 3.12 (CI matrix pins both — see `.github/workflows/ci.yml`).
- Resolution reference: `uv.lock` was resolved against Python >= 3.11 and is valid for
  both 3.11 and 3.12. CI installs via `uv sync` under each matrix Python.
- All runtime + optional deps live in `pyproject.toml`; exact versions pinned in `uv.lock`.

## Local setup

### Option A — uv (recommended; exact version pinning)

```bash
# From repo root. Installs uv if missing.
pip install --user uv            # or: pipx install uv
uv sync --extra dev --extra research
pre-commit install
```

`uv sync` installs the project in editable mode plus the named extras, honoring
`uv.lock` exactly. This is the reproducibility-grade install path — every machine
that runs `uv sync` against the same `uv.lock` gets bit-identical dependency
versions. Use this for any artifact that must be reproduced later (research
packs, audit retests, regulatory defense).

### Option B — pip (for environments without uv)

```bash
pip install -e ".[dev,research]"
pre-commit install
```

Pip resolves from `pyproject.toml` and will pick the latest versions satisfying the
declared ranges — it does **not** honor `uv.lock`. Use Option A whenever reproducibility
matters.

### Verifying the lockfile is current

```bash
uv lock --check        # exits non-zero if pyproject.toml changed without re-locking
```

CI runs `uv lock --check` on every build (see `.github/workflows/ci.yml`). PRs that
edit `pyproject.toml` without regenerating `uv.lock` will fail CI. CI itself still
installs via `pip install -e ".[dev,research]"` on each Python matrix cell — the
`uv lock --check` step guarantees that the committed lockfile would have produced
a consistent install, so downstream reproducibility consumers (research-pack audits,
regulators) can trust `uv sync` against the commit's `uv.lock`.

### Verifying the research-log hash chain

```bash
python3 scripts/verify_research_log.py
```

Exits 0 if every entry in `results/research_log.jsonl` hashes correctly against the
previous entry under canonical JSON serialization. Pre-commit runs this automatically
(see `.pre-commit-config.yaml`). Never hand-edit the log — all appends go through
`scripts/append_research_log.py`.

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
hashes, canonical rerun command, how to rebuild `research.duckdb` from raw vendor
pulls, how to rerun the six completed factor screens end to end) is tracked under
TODO-16 and will be appended to this document when that TODO closes.
