# TODOS — NYSE ATS Framework

> Eng review 2026-04-15. Items ordered by phase dependency.

## Phase 0

### TODO-4: Structured Logging Standard for nyse_ats
**What:** Configure structlog or stdlib logging with JSON output in nyse_ats.
**Why:** nyse_core uses diagnostic returns (no logging import), but nyse_ats has 10+ modules making API calls, DB writes, and order submissions. Without a logging standard, each module invents its own format, making production debugging painful.
**How to apply:** Create a logging config module. Log levels: DEBUG (API responses), INFO (rebalance events), WARNING (data gaps), ERROR (failures). All log entries include `rebalance_date` + `run_id` for traceability across a single pipeline run.
**Depends on:** Nothing. Phase 0 deliverable.

### TODO-5: Dependency Pinning Strategy
**What:** Choose uv or poetry with a lockfile. Pin major versions in pyproject.toml, exact versions in lockfile.
**Why:** 40-week project with ~15 dependencies. NautilusTrader has breaking API changes between minor versions. Without pinning, a `pip install` 6 months from now could break the entire system.
**How to apply:** Decide tool (uv recommended — fastest, lockfile built-in). Add `uv.lock` or `poetry.lock` to repo. CI tests against pinned versions.
**Depends on:** Nothing. Phase 0 deliverable.

## Phase 1

### TODO-3: VectorBT Version Strategy
**What:** Evaluate VectorBT open-source (v0.x) vs VectorBT PRO (commercial).
**Why:** VectorBT open-source and PRO have diverged. Open-source may not receive updates. PRO has licensing cost. The plan lists vectorbt as a dependency but doesn't specify which.
**How to apply:** During Phase 1, test both versions against the synthetic backtest. If PRO features are needed (portfolio optimization, advanced metrics), factor in licensing. Pin the chosen version in lockfile.
**Depends on:** TODO-5 (dependency pinning).

## Phase 2

### TODO-1: Falsification Trigger Frozen-Date Enforcement in Code
**What:** `falsification.py` should hash the triggers config at freeze time and refuse to evaluate if the hash changes.
**Why:** The frozen_date is currently a YAML comment — nothing prevents editing thresholds after the freeze date. Under drawdown pressure, the temptation to "adjust" thresholds is real. This is the same class of bug as the 0050 ETF split silently corrupting regime detection for months on TWSE.
**How to apply:** On first run after frozen_date, compute SHA-256 of falsification_triggers.yaml and store it in live.duckdb. On every subsequent run, recompute and compare. If mismatch → VETO + Telegram alert with diff. ~30 LOC in falsification.py.
**Depends on:** storage/live_store.py (Phase 2).

### TODO-2: Corporate Action Guard Between Signal and Execution
**What:** Before submitting TradePlan orders on Monday, check for corporate actions (splits, dividends) on held stocks that occurred between Friday close (signal generation) and Monday open (execution).
**Why:** A 4:1 split between signal and execution means the TradePlan has target_shares based on pre-split prices. Without a guard, you'd buy 4x the intended position. This is the EXACT bug class that corrupted TWSE regime detection for months (0050 ETF 4:1 split, Lesson_Learn Section 2.1).
**How to apply:** `nautilus_bridge.py` queries FinMind/data source for corporate actions on held symbols since TradePlan.decision_timestamp. If any found → cancel affected orders, re-run portfolio.build() with adjusted prices, regenerate TradePlan. ~50 LOC.
**Depends on:** nautilus_bridge.py (Phase 2), finmind_adapter.py (Phase 2).
