#!/usr/bin/env bash
# reproduce.sh — one-shot reproducibility driver for the NYSE ATS research record.
#
# What it does (in order):
#   1. Environment sanity: Python ≥ 3.11, editable install, DuckDB present
#   2. Data acquisition (optional — skipped if research.duckdb already populated)
#   3. Data-quality validation
#   4. Factor screening: ivol_20d, high_52w, momentum_2_12
#   5. Research-log hash-chain verification
#   6. Reproduction manifest: every reported number → its source artifact
#
# Invariants:
#   - End date NEVER crosses 2023-12-31 (holdout is one-shot; screen_factor.py enforces)
#   - Idempotent: re-runs skip completed steps unless --force is passed
#   - Fails fast (set -euo pipefail) and surfaces tool exit codes
#
# Usage:
#   scripts/reproduce.sh              # default: research period 2016-2023
#   scripts/reproduce.sh --force      # re-download and re-screen from scratch
#   scripts/reproduce.sh --no-download # require DB to already exist
#
# Exit codes:
#   0 = reproduced cleanly
#   1 = environment failure
#   2 = data step failed
#   3 = screening step failed
#   4 = chain verification failed
#   5 = manifest generation failed

set -euo pipefail

# ── Parse args ───────────────────────────────────────────────────────────────
FORCE=0
NO_DOWNLOAD=0
START_DATE="2016-01-01"
END_DATE="2023-12-31"

for arg in "$@"; do
  case "$arg" in
    --force)        FORCE=1 ;;
    --no-download)  NO_DOWNLOAD=1 ;;
    -h|--help)
      sed -n '2,28p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

log() { printf '\n\033[1;34m[reproduce]\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m[reproduce WARN]\033[0m %s\n' "$*" >&2; }
fail() { printf '\n\033[1;31m[reproduce FAIL]\033[0m %s\n' "$*" >&2; exit "${2:-1}"; }

# ── Step 1: Environment sanity ───────────────────────────────────────────────
log "Step 1/6 — Environment sanity"

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null) \
  || fail "python3 not found on PATH" 1

PY_MAJOR=${PY_VERSION%%.*}
PY_MINOR=${PY_VERSION##*.}
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ) ]]; then
  fail "Python ≥ 3.11 required (found $PY_VERSION)" 1
fi
echo "  python:   $PY_VERSION"

python3 -c 'import nyse_core, nyse_ats' 2>/dev/null \
  || fail "nyse_core / nyse_ats not importable. Run: pip install -e ." 1
echo "  packages: nyse_core, nyse_ats importable"

python3 -c 'import duckdb, pandas, numpy, scipy, sklearn' 2>/dev/null \
  || fail "Missing runtime deps (duckdb/pandas/numpy/scipy/sklearn)" 1
echo "  runtime:  duckdb, pandas, numpy, scipy, sklearn present"

# ── Step 2: Data acquisition (idempotent) ────────────────────────────────────
log "Step 2/6 — Data acquisition"

DB_PATH="research.duckdb"

db_has_data() {
  [[ -f "$DB_PATH" ]] && python3 - <<'PY' 2>/dev/null
import duckdb, sys
try:
    c = duckdb.connect("research.duckdb", read_only=True)
    n = c.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
    c.close()
    sys.exit(0 if n > 0 else 1)
except Exception:
    sys.exit(1)
PY
}

if [[ "$FORCE" -eq 1 ]]; then
  log "  --force: removing existing $DB_PATH"
  rm -f "$DB_PATH"
fi

if db_has_data; then
  echo "  SKIP: $DB_PATH already populated (pass --force to re-download)"
elif [[ "$NO_DOWNLOAD" -eq 1 ]]; then
  fail "--no-download set but $DB_PATH is empty or missing" 2
else
  log "  Downloading OHLCV $START_DATE → $END_DATE (this may take hours)"
  if [[ -z "${FINMIND_API_TOKEN:-}" && ! -f "$HOME/.config/finmind/token" ]]; then
    warn "FINMIND_API_TOKEN not set and no token file found"
    warn "Free tier will rate-limit heavily. Abort with Ctrl-C or continue."
    sleep 3
  fi
  python3 scripts/download_data.py \
    --start-date "$START_DATE" --end-date "$END_DATE" --source all \
    || fail "download_data.py failed" 2
fi

# ── Step 3: Data-quality validation ──────────────────────────────────────────
log "Step 3/6 — Data-quality validation"
python3 scripts/validate_data.py --db-path "$DB_PATH" \
  || fail "validate_data.py failed" 2

# ── Step 4: Factor screening (three pre-registered factors) ──────────────────
log "Step 4/6 — Factor screening"

FACTORS=("ivol_20d" "high_52w" "momentum_2_12")
for f in "${FACTORS[@]}"; do
  out="results/factors/$f/gate_results.json"
  if [[ "$FORCE" -eq 0 && -f "$out" ]]; then
    echo "  SKIP $f (already screened → $out)"
    continue
  fi
  log "  Screening $f"
  python3 scripts/screen_factor.py \
    --factor "$f" \
    --db-path "$DB_PATH" \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    || fail "screen_factor.py --factor $f failed" 3
done

# ── Step 5: Research-log hash-chain verification ─────────────────────────────
log "Step 5/6 — Verify research-log hash chain"
python3 scripts/verify_research_log.py --log-path results/research_log.jsonl \
  || fail "Research log chain is BROKEN. Do NOT trust downstream artifacts." 4

# ── Step 6: Reproduction manifest ────────────────────────────────────────────
log "Step 6/6 — Reproduction manifest"

MANIFEST="results/reproduction_manifest.txt"
mkdir -p results

python3 - <<'PY' > "$MANIFEST" || exit 5
"""Emit reproduction manifest: every reported number → its source artifact.

Rule: a number cited in NYSE_ALPHA_RESEARCH_RECORD.md or OUTCOME_VS_FORECAST.md
must appear here paired with the JSON key it was read from. If a reader can't
find the number's origin in under a minute, the manifest failed.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(p: Path) -> str:
    if not p.exists():
        return "MISSING"
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def chain_tip() -> str:
    log = Path("results/research_log.jsonl")
    if not log.exists():
        return "NO_LOG"
    last_hash = "0" * 64
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if isinstance(rec, dict) and "hash" in rec and isinstance(rec["hash"], str):
                if len(rec["hash"]) == 64:
                    last_hash = rec["hash"]
        except json.JSONDecodeError:
            pass
    return last_hash


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "NOT_A_GIT_REPO"


def load_factor(name: str) -> dict:
    p = Path(f"results/factors/{name}/gate_results.json")
    if not p.exists():
        return {}
    return json.loads(p.read_text())


ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
print(f"REPRODUCTION MANIFEST — {ts}")
print("=" * 78)
print()
print("This manifest pairs every reported metric with the artifact it was read")
print("from, so a reviewer can verify every number in the research record.")
print()
print("1. ENVIRONMENT")
print("-" * 78)
print(f"  git commit:  {git_commit()}")
print(f"  chain tip:   {chain_tip()}")
print()

print("2. FACTOR SCREENING RESULTS (research period 2016-2023)")
print("-" * 78)
for factor in ("ivol_20d", "high_52w", "momentum_2_12"):
    data = load_factor(factor)
    if not data:
        print(f"  {factor}: NOT SCREENED")
        continue
    gm = data.get("gate_metrics", {})
    gr = data.get("gate_results", {})
    passed = data.get("passed_all", False)
    print(f"  {factor}: passed_all={passed}")
    print(f"    G0 oos_sharpe          = {gm.get('G0_value', 'NA'):>12}   "
          f"(results/factors/{factor}/gate_results.json → gate_metrics.G0_value)")
    print(f"    G1 permutation_p       = {gm.get('G1_value', 'NA'):>12}   "
          f"(gate_metrics.G1_value)")
    print(f"    G2 ic_mean             = {gm.get('G2_value', 'NA'):>12}   "
          f"(gate_metrics.G2_value)")
    print(f"    G3 ic_ir               = {gm.get('G3_value', 'NA'):>12}   "
          f"(gate_metrics.G3_value)")
    print(f"    G4 max_drawdown        = {gm.get('G4_value', 'NA'):>12}   "
          f"(gate_metrics.G4_value)")
    print(f"    G5 marginal_contrib    = {gm.get('G5_value', 'NA'):>12}   "
          f"(gate_metrics.G5_value)")
    print(f"    gates passed: {sum(1 for v in gr.values() if v)}/6")
    print()

print("3. ARTIFACT HASHES (SHA-256 of committed evidence)")
print("-" * 78)
artifacts = [
    "results/factors/ivol_20d/gate_results.json",
    "results/factors/ivol_20d/screening_metrics.json",
    "results/factors/high_52w/gate_results.json",
    "results/factors/high_52w/screening_metrics.json",
    "results/factors/momentum_2_12/gate_results.json",
    "results/factors/momentum_2_12/screening_metrics.json",
    "results/research_log.jsonl",
    "config/strategy_params.yaml",
    "config/gates.yaml",
    "config/falsification_triggers.yaml",
]
for a in artifacts:
    print(f"  {sha256(Path(a))[:16]}…  {a}")

print()
print("4. WHAT THIS MANIFEST DOES NOT COVER")
print("-" * 78)
print("  - Holdout backtest (2024-2025): intentionally not executed")
print("  - Paper trading results: pre-trade phase only")
print("  - Live fills, slippage, reconciliation: no live deployment yet")
print("  - Piotroski / accruals / profitability: blocked on EDGAR adapter")
print("  - Short interest factors: blocked on FINRA adapter")
print()
print("5. NEXT REPRODUCIBILITY MILESTONE")
print("-" * 78)
print("  TODO-3 (EDGAR + FINRA adapters) → 5 fundamental factors screenable")
print("  TODO-9 (RSP cap-weight benchmark) → OUTCOME_VS_FORECAST rebased on RSP")
print("  Paper-trade start → live.duckdb + fill reconciliation manifest")
print()
print("=" * 78)
print("END MANIFEST")
PY

echo "  wrote: $MANIFEST"

# ── Summary ──────────────────────────────────────────────────────────────────
log "REPRODUCED"
echo ""
echo "  manifest: $MANIFEST"
echo "  To replay from scratch: scripts/reproduce.sh --force"
echo "  To verify only (no downloads): scripts/reproduce.sh --no-download"
echo ""
