# Reproducibility

> Status: research-pack spec landed 2026-04-19 (TODO-16 closed). This file now
> covers: Python pin, dependency lockfile (`uv.lock`), pre-commit install,
> hash-chain verification, and the research-pack manifest contract produced by
> `scripts/make_research_pack.py`.

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

## The research pack

Every material run (factor screen, permutation test, ensemble backtest, paper-trade
stretch) must be paired with a **research pack** — a self-contained directory under
`results/packs/<run_id>/` that captures everything a third party needs to recreate
the run's environment. The pack is the canonical audit artifact. A research-log
event that cites `manifest_sha256` is a tamper-evident anchor back to the run.

### Generating a pack

```bash
# Explicit run id + label
python3 scripts/make_research_pack.py \
    --run-id 2026-04-19_iter12_reproducibility_demo \
    --label "TODO-16 closure demo"

# Auto run id (UTC timestamp YYYYMMDDTHHMMSSZ)
python3 scripts/make_research_pack.py

# Point at a different DuckDB (e.g. a candidate rerun)
python3 scripts/make_research_pack.py --db-path /tmp/candidate.duckdb
```

Flags:

| Flag          | Default                      | Meaning                                           |
|---------------|------------------------------|---------------------------------------------------|
| `--run-id`    | UTC timestamp                | Becomes the pack directory name (must be unique). |
| `--label`     | none                         | Optional free-text tag for humans.                |
| `--db-path`   | `research.duckdb`            | DuckDB file to fingerprint.                       |
| `--log-path`  | `results/research_log.jsonl` | Research log whose tip is recorded.               |
| `--packs-dir` | `results/packs/`             | Parent directory for pack output.                 |

Collisions on `run_id` (pack directory already exists) fail fast with `FileExistsError`
and exit code 2 — the script never overwrites.

### Pack layout

```
results/packs/<run_id>/
├── manifest.json           # the audit artifact (see below)
├── pyproject.toml          # snapshot — exact deps declared
├── uv.lock                 # snapshot — exact deps resolved (if present)
└── configs/
    ├── data_sources.yaml
    ├── falsification_triggers.yaml
    ├── gates.yaml
    ├── market_params.yaml
    └── strategy_params.yaml
```

Snapshot files are verbatim copies of repo state at pack time. `manifest.json` is the
single machine-readable source of truth; the snapshot files are human-reviewable
copies so auditors don't need to hunt the git history.

### Manifest shape (enforced)

`manifest.json` keys — downstream tools read these exact names:

| Key                | Type              | Contents                                                                 |
|--------------------|-------------------|--------------------------------------------------------------------------|
| `run_id`           | string            | User-supplied or auto UTC timestamp.                                      |
| `run_label`        | string \| null    | Optional human label.                                                     |
| `generated_at`     | ISO 8601 UTC      | Timestamp (seconds precision).                                            |
| `git`              | object            | `sha`, `short`, `branch`, `dirty` (bool), `dirty_files_count`.            |
| `python`           | object            | `version`, `implementation`, `executable`.                                |
| `platform`         | object            | `system`, `release`, `machine`.                                           |
| `dependencies`     | object            | `pyproject_sha256`, `uv_lock_sha256`, `uv_lock_present`.                  |
| `configs`          | object            | Filename → SHA-256 for every file under `config/`.                        |
| `data_snapshot`    | object \| null    | `path`, `schema_hash`, `table_row_counts`; `null` if DB missing.          |
| `research_log_tip` | object \| null    | `hash`, `height`; `null` if log missing.                                  |
| `reproduction`     | object            | `env_setup_cmds`, `verify_chain_cmd`, `rerun_command`.                    |
| `manifest_sha256`  | 64-hex string     | Self-hash over the preceding keys (canonical JSON, excludes itself).      |

#### `data_snapshot` design note

The DuckDB fingerprint is **not** a hash of raw file bytes. DuckDB rewrites file-level
metadata on every re-open, so byte hashes would change spuriously. Instead the
fingerprint is a SHA-256 over the canonical JSON of `(table_name, column_name, data_type,
row_count)` tuples collected from `information_schema`. This catches the things a
reproducibility audit actually cares about — schema drift, row-count drift, new/missing
tables — while staying stable across re-opens.

#### `research_log_tip` design note

`height` is the number of valid hash-chained entries; `hash` is the SHA-256 at the tip.
Paired with `scripts/verify_research_log.py` this is enough for an auditor to prove the
log they hold is the log the pack was generated against — or to detect tampering.

#### `manifest_sha256` design note

The self-hash is computed over the canonical JSON of the manifest with the
`manifest_sha256` field itself omitted, then appended last. Any change to any other
field changes `manifest_sha256` — this is the one value you embed in a research-log
event to permanently anchor the pack.

### Anchoring a pack in the hash chain

After generating a pack, append a research-log event whose payload includes the pack's
`manifest_sha256`. That is the canonical tamper-evident pointer: given the log, an
auditor can verify the chain, pull the event, read `manifest_sha256`, and compare
against a freshly-hashed copy of `manifest.json`. Divergence means the pack was
edited after the fact.

```bash
# 1. Generate pack
python3 scripts/make_research_pack.py --run-id 2026-04-19_demo --label "demo"

# 2. Extract the self-hash
MSHA=$(python3 -c "import json; print(json.load(open('results/packs/2026-04-19_demo/manifest.json'))['manifest_sha256'])")

# 3. Write event payload and append
cat > /tmp/pack_event.json <<EOF
{"event":"research_pack_anchored","run_id":"2026-04-19_demo","manifest_sha256":"$MSHA"}
EOF
python3 scripts/append_research_log.py --event-file /tmp/pack_event.json
```

### Re-verifying a pack later

1. **Dependency drift:** diff `pyproject.toml` / `uv.lock` in the pack against today's
   repo copies. Exact matches mean an `uv sync` against the pack's lockfile reproduces
   the original environment byte-for-byte.
2. **Config drift:** recompute SHA-256 on each file under `config/` at the pack's git
   commit (`git show <sha>:config/<name>.yaml | sha256sum`) and diff against
   `manifest.configs`. Any mismatch means `config/` was edited after the pack was taken.
3. **Schema drift:** re-run `scripts/make_research_pack.py` against today's
   `research.duckdb` into a throwaway `--packs-dir` and diff the new
   `data_snapshot.schema_hash` against the pack's. Equal hashes mean schema + row counts
   match; unequal means data has mutated.
4. **Chain continuity:** `python3 scripts/verify_research_log.py` — exits 0 if the chain
   is intact up to current tip. Then confirm the pack's `research_log_tip.hash` is one
   of the hashes on the current chain (a `grep` against the log suffices).
5. **Self-integrity:** recompute `manifest_sha256` by loading the manifest, dropping the
   field, re-serializing with `json.dumps(obj, sort_keys=True, separators=(",", ":"))`,
   and hashing. Must equal the stored value.

### Rerunning a completed factor screen end to end

The six gate-closed factors (ivol_20d, mom_6_1, rev_1m, beta, amihud_illiquidity,
value_composite) are documented under `results/factors/<factor_name>/`. To rerun any
one against a fresh research pack's environment:

```bash
# A. Rebuild the environment to match the pack
uv sync --extra dev --extra research
pre-commit install

# B. Rebuild research.duckdb from raw vendor pulls (FinMind OHLCV, EDGAR fundamentals,
#    FINRA short interest). Vendor credentials live in env vars; see
#    config/data_sources.yaml for endpoints and `docs/vendors/` (TODO-18) for SLAs.
python3 scripts/download_data.py --start-date 2016-01-01 --end-date 2023-12-31 \
    --source all

# C. Validate the rebuilt DB passes all data-quality checks
python3 scripts/validate_data.py --db-path research.duckdb

# D. Re-run the factor screen (gates + permutation + bootstrap in one pass)
python3 scripts/screen_factor.py --factor ivol_20d
python3 scripts/run_permutation_test.py --factor ivol_20d --n-reps 500 --block-size 63

# E. Emit a new research pack and compare against the archival pack
python3 scripts/make_research_pack.py --label "rerun ivol_20d"
```

Strict reproducibility requires all five checks (dependency, config, schema, chain,
self-hash) to pass between the archival pack and the rerun pack. Any diff is a
reproducibility failure and must be written up in `docs/AUDIT_TRAIL.md`.

### Caller-side contract

- Research packs are **never** hash-chained by `make_research_pack.py` itself — the
  script is pure emission. Callers that want a permanent anchor append a research-log
  event whose payload includes `manifest_sha256`.
- Iron rule 6 forbids hand-editing `results/research_log.jsonl`; all appends go through
  `scripts/append_research_log.py`, which recomputes the chain.
- Iron rule 1 forbids holdout-data leakage: `--db-path` must never point at a database
  containing rows dated after 2023-12-31 unless the caller is explicitly running the
  one-shot holdout evaluation in Step 6 of `alpha-research`.
