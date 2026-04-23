# NYSE Cross-Sectional Alpha: Research Record

**Phase-by-Phase Development History**

**Version 0.5 | April 2026 | Living Document**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Phase 0: Foundation](#2-phase-0-foundation)
3. [Phase 1: Core Pipeline](#3-phase-1-core-pipeline)
4. [Phase 2: Data Infrastructure](#4-phase-2-data-infrastructure)
5. [Phase 3: Factor Research](#5-phase-3-factor-research)
6. [Phase 4: Optimization and ML Alternatives](#6-phase-4-optimization-and-ml-alternatives)
7. [Phase 5: Paper Trading (Planned)](#7-phase-5-paper-trading-planned)
8. [Phase 6: Live Deployment (Planned)](#8-phase-6-live-deployment-planned)
9. [Cross-Cutting Lessons](#9-cross-cutting-lessons)

---

## 1. Project Overview

This project builds a cross-sectional S&P 500 equity factor strategy for NYSE, adapting lessons from a 63-phase TWSE predecessor that achieved Sharpe 1.186. The key architectural decisions were made before writing code, drawn from hard-won TWSE experience: Ridge over GBM by default, rank-percentile normalization, sell buffer hysteresis, binary regime overlay, expanding walk-forward windows, and pure-logic core modules with no I/O.

**Current state:** v0.5. Research pipeline complete (998 tests passing). **Factor admission on real 2016-2023 S&P 500 data: 0 of 6 Tier-1 / Tier-2 factors pass G0-G5.** Ivol_20d, high_52w, momentum_2_12 (price-volume, Phase 3 first wave, 2026-04-17/18); piotroski, accruals, profitability (fundamentals, post EDGAR-companyfacts adapter rewrite + 308,660 fact row ingestion, 2026-04-18). Ensemble is structurally unbuildable until at least one factor clears the gates. Phase 5 paper trading **not imminent** — blocked on ≥3 admitted factors or an abandonment-criteria decision. Pre-registered abandonment criteria A1-A12 frozen 2026-04-18 (`docs/ABANDONMENT_CRITERIA.md`); A1 (10/13 fail → PAUSE) is 4 factors away from firing. Holdout (2024-2025) intact — lockfile absent. Next: Tier-3 factor screens, regime-conditional variants, 20-day horizon re-screens — each requires a fresh pre-registration per AP-6.

**Repository structure:**

```
src/
  nyse_core/          26 pure-logic modules (no I/O, no logging)
    features/         6 factor family modules + registry
    models/           Ridge, GBM, Neural implementations
  nyse_ats/           Side-effect modules (data, storage, execution, monitoring)
    data/             FinMind, EDGAR, FINRA, constituency adapters
    storage/          DuckDB research + live stores
    execution/        NautilusTrader bridge
    monitoring/       Dashboard, drift monitor, alert bot
tests/
  unit/               ~40 test files
  integration/        ~16 test files
  property/           8 invariant test files
config/               6 YAML config files (Pydantic-validated)
scripts/              8 operational scripts
```

---

## 2. Phase 0: Foundation

**Objective:** Establish the architectural skeleton, data contracts, and core primitives that every subsequent module would build on. Get the purity boundary right from day one.

**Duration:** Initial build phase

### What Was Built

**schema.py (131 LOC)** -- Canonical column names, enums, and constants. Every module imports column names from here; no magic strings elsewhere. Defines `Side`, `Severity`, `UsageDomain`, `RegimeState`, `RebalanceFrequency`, `CombinationModelType`, `NormalizationMethod`. All risk limits, CV parameters, and cost model constants are centralized.

Key decision: `STRICT_CALENDAR = True` (AP-5) -- never forward-fill prices by default. This was a TWSE lesson where forward-filling created phantom trading days.

**contracts.py (207 LOC)** -- Frozen dataclass data contracts forming the pipeline's type spine:

```
UniverseSnapshot -> FeatureMatrix -> CompositeScore -> TradePlan
       |                |                                |
  GateVerdict     BacktestResult              PortfolioBuildResult
```

The `Diagnostics` class replaces all logging. Every public function in `nyse_core` returns `(result, Diagnostics)`. This was the single most impactful architectural decision from TWSE -- logging imports create hidden I/O dependencies that make unit testing fragile and function purity unverifiable.

**config_schema.py (~200 LOC)** -- Pydantic models for 6 YAML configs: `MarketParams`, `StrategyParams`, `GatesConfig`, etc. Every config value documents its derivation via `# Derived:` comments (AP-12).

**pit.py (~150 LOC)** -- Point-in-time enforcement. `enforce_lags()` applies publication lags (OHLCV: T+0, EDGAR 10-Q: T+45, FINRA short interest: T+11). `pit_filter()` ensures features only use data available at the rebalance date. If a feature's most recent data exceeds `max_age`, the value becomes NaN.

**normalize.py (144 LOC)** -- Three normalization methods: `rank_percentile()` (default), `winsorize()`, `z_score()`. Rank-percentile maps to [0, 1] with average rank for ties, NaN preservation, and special-case handling for constant series.

**universe.py (~180 LOC)** -- PiT-enforced S&P 500 reconstitution. `UniverseBuilder` filters by minimum price ($5), minimum 20-day ADV ($500K), and historical constituency membership.

**impute.py (~120 LOC)** -- Cross-sectional median imputation. If NaN fraction < 30%, fill with cross-sectional median. If >= 30%, drop the entire factor for that date with a WARNING diagnostic.

### Key Decisions Made

1. **Purity boundary:** `nyse_core/` imports nothing from `os`, `pathlib`, `requests`, or `logging`. Only `pandas`, `numpy`, `scipy`, `sklearn`, `torch`, `pydantic`, and `lightgbm` are permitted. This rule was established before any module was written.

2. **`(result, Diagnostics)` contract:** Every public function follows this return signature. Tests inspect diagnostic messages without mocking loggers. Callers aggregate diagnostics via `diag.merge()`.

3. **Rank-percentile as default:** Based on TWSE Phase 44 evidence (+0.109 Sharpe over z-score). Decision was pre-made, not discovered during this project.

4. **Anti-patterns codified as enforcement rules:** 13 anti-patterns (AP-1 through AP-13) were documented and enforced in code from the start. Each has a specific assertion or check, not just documentation.

### Test Results

~200 tests added. Coverage: schema enums, Diagnostics mutation/merge, PiT lag enforcement, normalization edge cases (all-NaN, single value, constant series, ties), imputation thresholds, config validation.

### Surprises

None. Phase 0 was the most predictable phase because every decision was derived from TWSE experience. The surprise was how smooth it went compared to the TWSE project's chaotic early phases.

---

## 3. Phase 1: Core Pipeline

**Objective:** Build the full alpha generation pipeline from factor registration through walk-forward backtesting, including the gate system, cost model, and statistical tests.

**Duration:** Second major build phase

### What Was Built

**features/registry.py (138 LOC)** -- `FactorRegistry` with three enforcement rules: (1) no duplicate factor names, (2) AP-3 anti-double-dip via `usage_domain` (raises `DoubleDipError` if a factor is registered for both SIGNAL and RISK), (3) sign inversion for negative-convention factors.

**cost_model.py (125 LOC)** -- ADV-dependent dynamic spread formula:

```
spread_bps = BASE_SPREAD_BPS / sqrt(ADV / $50M) x monday_mult x earnings_mult
commission_bps = $0.005/share x 2 / $50 x 10000 = 2.0 bps
```

Plus Carver's position inertia: `should_trade()` suppresses rebalancing when weight deviation < 10%.

**allocator.py (132 LOC)** -- `select_top_n()` with sell buffer hysteresis (buffer=1.5 means existing holdings survive until rank > 30 for top_n=20). `equal_weight()` assigns 1/N to each selected stock. Ties broken: prefer held stocks, then alphabetical.

**risk.py (332 LOC)** -- Six risk layers implemented: regime overlay (SPY > SMA200), position caps (10% max), sector caps (30% max GICS), beta bounds [0.5, 1.5], daily loss limit (-3%), earnings event cap (5% weight if reporting within 2 days). Each returns `(modified_portfolio, Diagnostics)`.

**cv.py (146 LOC)** -- `PurgedWalkForwardCV` with expanding windows, auto-adjusting purge gap to `max(purge_days, target_horizon_days)`, embargo equal to target horizon. Minimum training: 2 years (504 trading days).

**gates.py (177 LOC)** -- `ThresholdEvaluator` (stateless comparator shared with falsification triggers) and `evaluate_factor_gates()` orchestrating G0-G5. Default thresholds: G0 (OOS Sharpe >= 0.3), G1 (perm p < 0.05), G2 (IC mean >= 0.02), G3 (IC IR >= 0.5), G4 (MaxDD >= -0.30), G5 (marginal contribution > 0.0).

**signal_combination.py (96 LOC)** -- `CombinationModel` Protocol with `fit()`, `predict()`, `get_feature_importance()`. Factory function `create_model()` routes to Ridge/GBM/Neural. AP-8 validation (`_validate_feature_range()`) asserts [0, 1] range before model input.

**models/ridge_model.py (~150 LOC)** -- Default model. `sklearn.linear_model.Ridge(alpha=1.0)`. Feature importance via normalized absolute coefficients.

**backtest.py (~200 LOC)** -- `run_rigorous_backtest()` for validation mode. Integrates walk-forward CV with cost computation.

**metrics.py (175 LOC)** -- `sharpe_ratio()`, `cagr()`, `max_drawdown()`, `information_coefficient()`, `ic_information_ratio()`, and `turnover()`. All annualized using 252 trading days.

**statistics.py (247 LOC)** -- `permutation_test()` (circular block bootstrap, 200--500 reps), `block_bootstrap_ci()` (63-day blocks, 10,000 reps, joblib parallelized), `romano_wolf_stepdown()` (joint null, 500 reps).

### Key Decisions Made

1. **DRY between gates and falsification:** Both use `ThresholdEvaluator`. Same comparator, different thresholds and response protocols.

2. **Sell buffer = 1.5:** Pre-set from TWSE Phase 63 evidence (+0.040 Sharpe, ~1,644 bps saved). Not tuned during this project.

3. **Weekly rebalance step (5 trading days):** Made possible by NYSE's ~12 bps roundtrip cost vs TWSE's ~68.5 bps.

4. **Expanding windows over rolling:** More training data produces more stable Ridge coefficient estimates. Standard for walk-forward backtesting per de Prado (AFML).

### Test Results

~250 tests added. Key coverage: registry anti-double-dip enforcement, cost model edge cases (zero ADV, Monday multiplier, earnings week), allocator sell buffer behavior, risk layer cascading, CV purge gap auto-adjustment, gate pass/fail logic, statistical test convergence.

### Surprises

The `ThresholdEvaluator` refactor was not planned. It emerged when we noticed gates and falsification triggers had identical comparison logic. Extracting it reduced code by ~60 lines and eliminated a potential divergence bug.

---

## 4. Phase 2: Data Infrastructure

**Objective:** Build the side-effect layer: data adapters for external APIs, storage in DuckDB, NautilusTrader execution bridge, and operational tooling.

**Duration:** Third major build phase

### What Was Built

**nyse_ats/data/finmind_adapter.py** -- FinMind API adapter with retry (3x with backoff via tenacity), rate limiting, and atomic file writing. Fetches OHLCV data for the S&P 500 universe.

**nyse_ats/data/edgar_adapter.py** -- SEC EDGAR XBRL adapter for 10-Q/10-K fundamentals. Respects SEC rate limits via sliding window rate limiter. Handles XBRL parse failures gracefully (feature goes NaN).

**nyse_ats/data/finra_adapter.py** -- FINRA short interest adapter. Bi-monthly publication with T+11 lag enforced by PiT module.

**nyse_ats/data/constituency_adapter.py** -- Historical S&P 500 membership tracking. Used by `universe.py` for PiT-correct universe construction.

**nyse_ats/data/transcript_adapter.py** -- Earnings call transcript adapter for NLP sentiment analysis (EXP-6 experimental).

**nyse_ats/storage/** -- DuckDB-based storage with two databases: `research.duckdb` (backtest and research data) and `live.duckdb` (production state, position tracking). Corporate action event log for split/dividend adjustment.

**nyse_ats/execution/nautilus_bridge.py** -- NautilusTrader bridge. Consumes `TradePlan` frozen dataclasses and converts to NautilusTrader orders. Supports TWAP/VWAP execution algorithms. Paper/Shadow/Live mode switching. NautilusTrader is the position source of truth.

Key interface boundary: the research pipeline's job ends at producing a `TradePlan`. The execution engine's job starts at consuming it. No shared state crosses this boundary.

**nyse_ats/monitoring/** -- Rate limiter, data quality checks, alert bot (Telegram integration for VETO/WARNING notifications).

**scripts/** -- 8 operational scripts: `download_data.py`, `validate_data.py`, `run_backtest.py`, `run_permutation_test.py`, `evaluate_gates.py`, `run_paper_trade.py`, `run_live_trade.py`, `run_dashboard.py`.

### Key Decisions Made

1. **DuckDB over Parquet files:** The TWSE system used raw Parquet files, which made concurrent access and schema enforcement difficult. DuckDB provides SQL queries, ACID transactions, and columnar storage without a server process.

2. **NautilusTrader over custom execution:** Execution is a solved problem. NautilusTrader handles broker connectivity, order lifecycle, position management, and mode switching. Building custom execution would duplicate proven infrastructure.

3. **Atomic file writing:** All data writes go through an atomic writer that writes to a temp file and renames. Prevents corrupted files from partial writes during API timeouts.

4. **Rate limiter as a shared service:** All API adapters share a rate limiter that respects per-vendor limits (FinMind: 6,000 req/hr; SEC: 10 req/sec).

### Test Results

~130 tests added. Coverage: adapter retry logic, rate limiter window behavior, atomic write atomicity, DuckDB CRUD operations, nautilus bridge TradePlan conversion, data quality checks, alert bot message formatting.

### Surprises

The EDGAR adapter was harder than expected. SEC XBRL filings have inconsistent tag names across companies. Some use `us-gaap:Revenues`, others use `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`. The adapter maintains a tag mapping table, but coverage is imperfect. This means some companies will have NaN for fundamental factors even when filings exist. The imputation module handles this (median fill if < 30% missing), but it is an ongoing data quality concern.

---

## 5. Phase 3: Factor Research

**Objective:** Implement all 6 factor families, evaluate each factor through the G0-G5 gate system, and build factor correlation analysis and attribution infrastructure.

**Duration:** Fourth major build phase

### What Was Built

**features/price_volume.py (~200 LOC)** -- Four factors:
- `compute_ivol_20d()`: 20-day idiosyncratic volatility (sign=-1, low IVOL = buy)
- `compute_52w_high_proximity()`: Distance from 52-week high (George-Hwang 2004)
- `compute_momentum_2_12()`: 2-12 month momentum, skipping most recent month
- `compute_ewmac()`: Exponentially weighted moving average crossover

**features/fundamental.py (~200 LOC)** -- Three factors:
- `compute_piotroski()`: Piotroski F-score (9-point financial strength)
- `compute_accruals()`: Total accruals ratio (sign=-1, high accruals = sell)
- `compute_profitability()`: Gross profitability (Novy-Marx 2013)

**features/earnings.py (~150 LOC)** -- Two factors:
- `compute_earnings_surprise()`: Standardized unexpected earnings
- `compute_analyst_revisions()`: Net analyst revision ratio

**features/short_interest.py (~180 LOC)** -- Three factors:
- `compute_short_ratio()`: Short interest as fraction of float (sign=-1)
- `compute_days_to_cover()`: Short interest / average daily volume
- `compute_short_pca()`: PCA composite of short interest signals

**features/sentiment.py (~150 LOC)** -- Three factors:
- `compute_options_flow()`: Net options order flow imbalance
- `compute_put_call_ratio()`: Put/call volume ratio
- `compute_implied_vol_skew()`: 25-delta skew

**features/nlp_earnings.py (~200 LOC)** -- One factor:
- `compute_transcript_sentiment()`: Earnings call transcript tone analysis

**factor_screening.py (~150 LOC)** -- Factor-level screening utilities for rapid evaluation.

**factor_correlation.py (~200 LOC)** -- Spearman cross-sectional correlation matrix computation and PCA-based factor deduplication. Auto-selects the highest-IC representative per principal component.

**attribution.py (~150 LOC)** -- Per-factor and per-sector return contribution analysis. `compute_attribution()` decomposes portfolio returns into factor contributions using Ridge coefficient weights.

**synthetic_calibration.py (~200 LOC)** -- 50-trial calibration: plants known factors into simulated data with realistic cross-sectional structure, verifies the pipeline recovers them. Validates methodology, not signal magnitude.

### Factor Gate Evaluation Results

Each factor is evaluated through the full G0-G5 pipeline on the 2016-2023 research period. The gate system is the funnel; no factor enters the ensemble without passing all six gates on real data.

**Expected gate outcomes based on TWSE priors (pre-registered 2026-04-15):**

| Factor | G0 (OOS Sharpe) | G2 (IC) | G3 (IC IR) | G5 (Marginal) | Notes |
|--------|:---------------:|:-------:|:----------:|:--------------:|-------|
| ivol_20d | Likely PASS | >= 0.02 expected | >= 0.5 expected | TBD | Strongest TWSE factor; should transfer |
| piotroski | Likely PASS | >= 0.02 expected | >= 0.4 expected | TBD | Value factor; works across markets |
| earnings_surprise | Likely PASS | >= 0.03 expected | >= 0.5 expected | TBD | PEAD is well-documented on NYSE |
| momentum_2_12 | Uncertain | Variable | Variable | TBD | TWSE momentum FAILED (-0.278 Sharpe). NYSE momentum may work due to no price limits. |
| short_pca | Likely PASS | >= 0.02 expected | >= 0.4 expected | TBD | FINRA data unique to US market |
| options_flow | Uncertain | Variable | Variable | TBD | No TWSE precedent; NYSE-specific |
| transcript_sentiment | Uncertain | Variable | Variable | TBD | Experimental; data quality is the risk |

**Key lesson from TWSE:** A factor with IC = 0.047 (operating_margin) failed G5 because its signal was already captured by existing factors. Strong standalone IC does not guarantee ensemble improvement. G5 is the gate that matters.

#### First Real-Data Screen: ivol_20d FAIL (2026-04-17)

The first factor run on real FinMind OHLCV data **falsified the TWSE prior**. ivol_20d failed G0-G4 over the full 2016-2023 research period.

| Gate | Forecast (TWSE prior) | Actual (2016-2023) | Verdict |
|------|-----------------------|--------------------|---------|
| G0 OOS Sharpe | >= 0.30 | **-1.92** | FAIL |
| G1 Permutation p | < 0.05 | 1.00 | FAIL |
| G2 IC mean | >= 0.02 | -0.008 | FAIL |
| G3 IC IR | >= 0.50 | -0.055 | FAIL |
| G4 Max drawdown | >= -0.30 | -0.578 | FAIL |
| G5 Marginal contribution | > 0 | pass (sentinel: first factor in empty ensemble) | PASS |

**Evidence:** `results/factors/ivol_20d/gate_results.json`, `results/factors/ivol_20d/screening_metrics.json`, `results/research_log.jsonl` (hash-chained event, chain tip committed in this release).

**Sanity check performed before concluding:** raw (unranked) IC on a pre-2020 subsample is **+0.0213** with 51.7% positive weekly IC. The factor has directional signal in quieter regimes — the 2016-2023 failure is a **time-variation problem**, not a code or sign-convention bug.

**Leading hypotheses (under investigation):**

1. **Low-vol winter 2016-2019** — QE-driven risk-on, growth-led market; high-IVOL stocks (high-beta growth) rallied, inverting the classical anomaly.
2. **Q1 2021 meme-stock squeeze** — GME / AMC / BBBY had extreme IVOL AND extreme realized returns. Being underweight them drove large negative excess returns.
3. **Structural drift** — retail options flow and passive-flow concentration post-2020 may represent permanent regime change, not a temporary window.

**AP-6 upheld:** The sign convention in `scripts/screen_factor.py` was **not** flipped after observing the inversion. No post-hoc threshold adjustment. The plan's sign convention (IVOL sign = -1 → invert → low raw IVOL = high rank = buy) remains unchanged.

**Disposition:**

- `docs/INDEPENDENT_VALIDATION_DRAFT.md` §4 documents the full outcomes analysis for independent reviewer.
- `docs/OUTCOME_VS_FORECAST.md` records this as a MISS against the pre-registered "Likely PASS" forecast.
- Next: continue Phase 3 by screening `high_52w` + `momentum_2_12` (price-only, immediately runnable) before judging the ensemble. Do **not** make the ensemble composition decision from one factor's failure.
- A regime-conditional ivol variant (IVOL × SMA-200 gate) is captured as deferred research in TODOS.md.

**Why this matters:** The gate system worked. It detected a regime-shifted anomaly on the first run and refused admission. A system that had used relaxed thresholds or a "directional prior" override would have admitted ivol_20d anyway and absorbed the -1.92 Sharpe into the ensemble. The six-gate architecture is validated as working by virtue of FAILING here.

#### Second and Third Real-Data Screens: high_52w FAIL, momentum_2_12 BORDERLINE FAIL (2026-04-18)

Per TODO-24, the next two immediately-runnable price-volume factors were screened with the same (unchanged) pipeline, configs, and sign conventions. Both fail on 2016-2023.

| Factor | G0 OOS Sharpe | G1 perm p | G2 IC_mean | G3 IC_IR | G4 MaxDD | Verdict |
|--------|--------------:|----------:|-----------:|---------:|---------:|---------|
| ivol_20d | **-1.92** | 1.00 | -0.008 | -0.055 | -0.578 | FAIL (all) |
| high_52w | **-1.23** | 1.00 | -0.0055 | -0.023 | -0.607 | FAIL (all) |
| momentum_2_12 | **0.516** | **0.002** | 0.0189 | 0.078 | -0.283 | FAIL (G2/G3 only) |

**Evidence:** `results/factors/{high_52w,momentum_2_12}/gate_results.json`, `results/factors/{high_52w,momentum_2_12}/screening_metrics.json`, `results/research_log.jsonl` (hash-chained; chain tip updated; see `docs/RESEARCH_RECORD_INTEGRITY.md`).

**momentum_2_12 is borderline:** OOS Sharpe 0.516 passes G0; permutation p 0.002 passes G1 strongly; MaxDD -28.3% passes G4. But G2 misses by literally one basis point (0.0189 vs 0.02 threshold) and G3 misses by 6x (0.078 vs 0.5). **Interpretation:** momentum has a real, small, directional edge in this window — but the per-period noise is too high for the factor to pay for itself in an ensemble. The gate system is doing exactly what it was designed to do.

**AP-6 DISCIPLINE under pressure:** The momentum_2_12 "miss by 0.0011 on G2" is the first serious test of AP-6. The temptation to lower G2 from 0.02 → 0.018 to admit momentum is strong. We do not. Reasons:

1. Any post-hoc threshold change opens a regress: next factor fails by 0.0009, then by 0.0008, etc.
2. G3 IC_IR fails by 6x regardless of G2 — the factor is not rescued by moving one threshold.
3. AP-6 is load-bearing for the credibility of the entire research record. Its value is entirely in being inviolable.

**Pattern across three Tier-1 price-volume factors (2016-2023):**

- **ivol_20d:** FAIL. Signal exists pre-2020 (raw IC +0.0213) but inverts in the full window.
- **high_52w:** FAIL. Sign inverts — "stocks near high" anti-predicts forward returns in this period.
- **momentum_2_12:** FAIL (borderline). Signal is directionally present and statistically significant (p=0.002) but too noisy for G3.

This is not a coincidence. The 2020-2023 sub-window contains three regime-distorting events (COVID crash, retail-meme squeeze, rates shock) and a mega-cap / AI concentration era that disproportionately damages behavioral-anchoring and low-frequency-diffusion signals. It is consistent with the broader "factor zoo compression post-2015" literature. See `docs/OUTCOME_VS_FORECAST.md` §"Pattern observation: 3/3 price-volume Tier-1 factors have failed" for full analysis.

**Implication for the research record:**

- The Phase-3 exit target "OOS Sharpe 0.5-0.8" is now at risk unless fundamental factors carry the ensemble alone, or combine with residual momentum signal in a way that survives its own G0-G5 pipeline.
- Fundamental signals (piotroski, accruals, profitability) are now the critical path. Not yet screened — blocked on EDGAR + FINRA ingestion (see TODO-3, TODO-51).
- A regime-conditioned IVOL variant (TODO-23) remains a legitimate research path but must be **freshly pre-registered** before being screened. No retroactive save of a failing factor.
- Ensemble construction cannot proceed until we have ≥3 factors passing G0-G5. Currently 0/3.

**Chain-integrity incident (2026-04-18):** During this screening run, `scripts/screen_factor.py` was writing raw (non-hash-chained) entries to `results/research_log.jsonl` from a pre-chain code path. A subsequent `append_research_log.py` call read the trailing raw entry, found no `hash` field, defaulted to GENESIS, and started a fork chain. The incident was caught by `scripts/verify_research_log.py` within minutes. Repair: (a) backed up the broken tail to `results/research_log.jsonl.pre-repair-2026-04-18`; (b) hardened `_last_hash()` to scan for the last line carrying a hash field, chaining past any trailing legacy entries; (c) patched `screen_factor.py` to call `append_event()`; (d) appended a `chain_repair_note` event documenting the incident (hash `f7486997...4f48fde5`); (e) re-ran both screens with correct logging. No research findings were altered — only the transport of those findings into the chain was rebuilt. This is documented here so that future auditors reading `results/research_log.jsonl.pre-repair-2026-04-18` against the current log can reconcile the two.

#### Fourth, Fifth, and Sixth Real-Data Screens: Fundamental Factors All FAIL (2026-04-18)

After the EDGAR companyfacts adapter was rewritten to (a) correctly dereference XBRL tag variants across S&P 500 filers and (b) atomically ingest 308,660 fact rows for all 503 current constituents, three fundamental factors were screened through G0-G5 in order: piotroski (F-score, 9 binary financial-strength signals), accruals (Collins-Hribar `OANCF − NI` proxy), profitability (Novy-Marx gross-profits-to-assets).

| Factor | G0 OOS Sharpe | G1 perm p | G2 IC_mean | G3 IC_IR | G4 MaxDD | Verdict |
|--------|--------------:|----------:|-----------:|---------:|---------:|---------|
| piotroski | 0.039 | **0.002** | 0.0090 | 0.089 | −0.216 | FAIL (G0/G2/G3) |
| accruals | **0.577** | **0.002** | 0.0080 | 0.062 | −0.272 | FAIL (G2/G3) |
| profitability | **1.148** | **0.002** | 0.0158 | 0.113 | −0.190 | FAIL (G2/G3) |

**Evidence:** `results/factors/{piotroski,accruals,profitability}/gate_results.json`, `results/factors/{piotroski,accruals,profitability}/screening_metrics.json`, `results/research_log.jsonl` (hash-chained; verifier output: 18 chained entries, 0 broken as of 2026-04-18).

**Shared failure signature.** All three show the same three-gate pattern: **G1 PASS + G2 FAIL + G3 FAIL**. Permutation p-values (0.002 at 500 reps) hit the floor — the signals are statistically distinguishable from noise. But the cross-sectional IC (0.008–0.016) is roughly half the G2 admission floor, and the IC-IR (0.06–0.11) is 4–8× below the G3 threshold of 0.5.

**What this means economically.** Profitability's gross long-short Sharpe of 1.15 with a −19% MaxDD over 8 years on 503 names is a real result. But the edge is diffuse — most of the Sharpe lives in decile-tail differentiation, not per-name ranking. In a Ridge ensemble on rank-percentile features that needs per-name signal, and in a weekly-rebalance cost structure where 15 bps one-way eats 0.01-IC edges, the gates correctly block admission.

**Plan-vs-gate threshold discrepancy — RESOLVED 2026-04-23 via correction path A (see `docs/GOVERNANCE_LOG.md` GL-0010).** The original version of this paragraph flagged a single-threshold discrepancy (plan `ic_ir ≥ 0.02` vs in-force `ic_ir ≥ 0.5`) and recommended pre-registered correction. The iter-9 / iter-10 / iter-10-supplemental gate-calibration audit (`docs/audit/gate_calibration_audit.md` GCA-2026-04-23, commit `ead47d8`; `docs/audit/gate_mismatch_root_cause_and_consequences.md` GCA-2026-04-23-supplemental, commit `fdc5952`) demonstrated the divergence was **not** a single-threshold typo but a family-level semantic redesign: all six gates G0-G5 differ in metric identity between the plan and in-force config. Per operator authorization on 2026-04-23, path A (amend plan to match in-force config) was chosen. The in-force gate family (G0=oos_sharpe≥0.30, G1=permutation_p<0.05, G2=ic_mean≥0.02, G3=ic_ir≥0.50, G4=max_drawdown≥-0.30, G5=marginal_contribution>0.0, sha256 `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`) is now canonical. Plan `/home/song856854132/.claude/plans/dreamy-riding-quasar.md` §gates.yaml and `docs/templates/factor_screen_memo.md` §3 amended in the iter-11 commit. AP-6 preserved: no screen re-run, no threshold relaxation, no verdict overturn — all 6 FAIL verdicts (ivol_20d, high_52w, momentum_2_12, piotroski, accruals, profitability) are re-affirmed under the in-force family by GL-0011. The plan's redundancy (G2 max_corr), full-sample-robustness (G4 Sharpe delta), date-gap-hygiene (G5 baseline date gap), and universe-coverage (G0 coverage%) guards are NOT restored in this amendment; re-visitation deferred to Wave 4+ of the 20-iteration research loop if needed.

**Update 2026-04-23 (iter-11-D, same day as path-A resolution above).** The iter-11 path-A canonicalization was submitted for adversarial review via `/codex` consult (session `019dba41-f163-70e1-875b-909771c26083`, 68,078 tokens). Codex's verdict: path A "launders an unauthorized implementation into the constitution after the fact" and would establish an institutional precedent incompatible with AP-6 — *"implementation beats plan-of-record when implementation happened to land first."* Codex recommended path D (quarantine incident, canonicalize neither family, pre-register a v2 family prospectively) combined with path E (renegotiate Phase 3 exit target separately from the gate-family question). Operator accepted that recommendation. Iter-11-D appends **GL-0012** (reverses GL-0010's canonicalization claim; declares both the plan's pre-amendment family and the in-force family **provisional** pending a v2 gate family pre-registered prospectively in iter-13+ of Wave 4 before any new factor admission is cited) and **GL-0013** (activates PATH E — the Phase 3 exit target OOS Sharpe 0.5–0.8 is now explicitly under renegotiation; the new target will be pre-registered before the v2 gate family is finalized, to avoid target-family double-fitting). **No operational change:** `config/gates.yaml` sha256 `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4` unchanged; no test, screen, or admission verdict modified; GL-0011's re-affirmation of the 6 FAIL verdicts remains valid (each of ivol_20d / high_52w / momentum_2_12 / piotroski / accruals / profitability fails ≥3 of 6 gates under *either* family, so admission is invariant to the choice). Amendments land in four documentation artifacts — `docs/GOVERNANCE_LOG.md` (GL-0012 + GL-0013 appended; §3 gate-family row re-flagged PROVISIONAL; new Phase 3 exit target row added; §7 last-reviewed bumped); `/.claude/plans/dreamy-riding-quasar.md` §gates.yaml (heading changed to "provisional under GL-0012 (path-D reversal 2026-04-23 same day as path-A)"; amendment note rewritten to cite the Codex review and declare both families provisional) and §Phase 3 (target line annotated with PATH E renegotiation note); `docs/templates/factor_screen_memo.md` §3 (amendment note rewritten to mark current in-force family PROVISIONAL; future memos are "engineering outputs, not canonical admission decisions"); and this record (§357 above, path D/E/C footer below, §Eleventh Action closing narrative). Iron rule append-only preserved: GL-0010 and GL-0011 are *not* edited — GL-0012 supersedes GL-0010's canonicalization claim by appending a new row. Two-way door preserved: reversing this iteration would again be append a new GOVERNANCE_LOG row and re-amend plan + template + record. See `docs/GOVERNANCE_LOG.md` GL-0012 and GL-0013 for the authorization rows.

**AP-6 compliance confirmed across the wave.** No sign flips, no threshold adjustments, no retroactive admission. See `docs/OUTCOME_VS_FORECAST.md` §"Pattern observation (update): 6/6 Tier-1+2 factors have failed 2016-2023".

**Aggregate standing after six factor screens.**

- **Factor admission:** 0 of 6 attempted.
- **Calibration:** Brier score 0.61 at n=7 (7 MISS on forecasts set at "PASS likely" 0.75 / "PASS plausible" 0.65). Under the plan's implicit prior of p_hit ≈ 0.65, 7/7 MISS is significant at p ≈ 0.0006. See `docs/CALIBRATION_TRACKER.md`.
- **Abandonment criteria** (`docs/ABANDONMENT_CRITERIA.md`, frozen 2026-04-18): A1 (10/13 fail → PAUSE) is 4 factors away from firing. A2 (13/13 fail → PIVOT) is 7 factors away.
- **Phase 3 exit target** (OOS Sharpe 0.5–0.8): formally resolved as MISS — **unbuildable** with 0 admitted factors.

**Five paths forward (all require fresh pre-registration):**

A. Tier-3 factor screens — options flow, analyst revisions, NLP earnings transcripts, short interest (FINRA adapter built, not yet screened).
B. Regime-conditional variants — ivol_20d × SMA-200 gate; momentum_2_12 sub-regime splits. Must be freshly pre-registered, not retroactively re-admitted.
C. 20-day forward-return re-screens — plan's secondary target. Fundamentals in particular tend to express at longer horizons. Low-cost first experiment (≈1 hour of compute).
D. Threshold pre-registration review — ~~only admissible if the plan's 0.02 in the text was the genuine original intent and 0.5 in gates.yaml was transcription error; must be logged as a `correction` event diff dated before re-screening.~~ **UPDATED 2026-04-23 (iter-11-D):** initial path-A resolution (GL-0010, iter-11 commit `4a5ed89`) was reversed later the same day by GL-0012 following adversarial governance review via `/codex` consult (session `019dba41-f163-70e1-875b-909771c26083`). The gate-family divergence is **not** resolved — both the plan's pre-amendment family and the in-force family are now **provisional** pending a v2 gate family pre-registered prospectively in iter-13+ of Wave 4, before any new factor admission is cited under either. `config/gates.yaml` remains operationally in effect (sha256 `521b7571...f559af4` unchanged). See `docs/GOVERNANCE_LOG.md` GL-0012 and the iter-11-D update paragraph in §357 above.
E. Renegotiate Phase 3 exit target — "any factor passes G0-G5" rather than ensemble Sharpe 0.5–0.8. Calibrates the plan to what the data actually supports, not what the TWSE priors expected. **ACTIVATED 2026-04-23 via GL-0013 (iter-11-D).** The Phase 3 exit target (OOS Sharpe 0.5–0.8) is now explicitly under renegotiation. GL-0013 does not itself set a new target — it reserves the renegotiation for a separate pre-registered event, to be resolved before the v2 gate family (GL-0012) is finalized. This ordering avoids target-family double-fitting: setting the new target *after* seeing the v2 gate family would allow retroactive target calibration.

Path C is the recommended next action because (a) cheapest to run, (b) directly tests whether 5-day is the reason fundamentals are failing, (c) AP-6-compliant as a fresh forecast. (Path D's initial path-A resolution from iter-11 was reversed by GL-0012 in iter-11-D — see the §357 update paragraph; path E was activated via GL-0013 in iter-11-D. Both updates are docs-only / two-way door; neither changed `config/gates.yaml`, tests, or admission verdicts.)

#### Seventh Action: Full-Set Reproduction Verification (2026-04-21, iter-0 of the next research wave)

Before opening the next 20-iteration research wave (benchmark menu redesign → portfolio-construction alternatives → gate-calibration audit under pre-registration → multi-factor admission reform → regime-conditioning), all six Tier-1 / Tier-2 factors were re-screened through `scripts/screen_factor.py` against the same research database (`research.duckdb`, 960,072 OHLCV rows × 491 symbols × 2016-01-04 → 2023-12-29; 308,660 fundamentals fact rows × 492 symbols). Purpose: honest-broker reproducibility check that the 2026-04-18 admission verdicts are a property of the data + methodology rather than of a specific run.

| Factor | G0 Sharpe (Apr-18) | G0 Sharpe (Apr-21) | Δ | G2 ic_mean Apr-21 | G3 ic_ir Apr-21 | Verdict change |
|--------|---:|---:|---:|---:|---:|:---:|
| ivol_20d | −1.9156 | −1.9156 | 0.0000 | −0.0079 | −0.0545 | None (FAIL→FAIL) |
| high_52w | −1.2291 | −1.2291 | 0.0000 | −0.0055 | −0.0234 | None (FAIL→FAIL) |
| momentum_2_12 | +0.5164 | +0.5164 | 0.0000 | +0.0189 | +0.0777 | None (FAIL→FAIL) |
| accruals | +0.5765 | +0.5765 | 0.0000 | +0.0080 | +0.0623 | None (FAIL→FAIL) |
| profitability | +1.1477 | +1.1477 | 0.0000 | +0.0158 | +0.1130 | None (FAIL→FAIL) |
| **piotroski** | +0.0385 | **+0.0181** | **−0.0204** | +0.0090 | +0.0890 | None (FAIL→FAIL; G0 still < 0.30) |

**5/6 reproduce bit-exactly. Piotroski's G0 Sharpe drifted from 0.0385 → 0.0181 (−0.02 absolute, −53% relative) while its IC metrics (G2, G3) stayed essentially unchanged (G3 drifted by 0.0002).**

**Root cause (working hypothesis).** Piotroski F-score is a discrete integer 0-9. The long-short LS-return builder (`src/nyse_core/factor_screening.py::compute_long_short_returns`) constructs weekly quintile baskets via pandas rank/qcut on the score column. With only ~10 unique score values, every rebalance date has large tie groups (e.g., dozens of stocks tied at F=6). pandas resolves ties using the DataFrame's underlying row order, which is groupby-/merge-dependent and not deterministically stable across runs (especially when DuckDB returns rows in a query-plan-dependent order). Continuous-score factors (ivol_20d, momentum_2_12, accruals, profitability, high_52w) have essentially no ties and reproduce exactly. Consistent with the observation that G0 (LS Sharpe) is the only metric sensitive to quintile-assignment drift; G2/G3 compute cross-sectional IC via Spearman on raw scores, which is invariant to tie ordering.

**AP-6 compliance.** Both piotroski values (0.0385 and 0.0181) sit well below G0's 0.30 floor; verdict (FAIL) is unchanged. We do NOT silently "fix" the tie-breaking and re-run piotroski — that would constitute retroactive methodology change. The defect is documented; any fix must be pre-registered as a `correction` event dated before any re-screen. Captured as **TODO-36** in `docs/TODOS.md`.

**What this unlocks.** 5/6 bit-exact reproduction is strong evidence the 2026-04-18 admission result (0/6 all FAIL) is a property of the data, not of run-to-run noise. The 20-iteration research plan now starts from a reproducibility-verified baseline.

**Evidence:** `results/factors/{ivol_20d,high_52w,momentum_2_12,accruals,profitability,piotroski}/gate_results.json` (freshly overwritten 2026-04-21 — same numbers for 5 factors, drifted for piotroski); `results/factors/*/screening_metrics.json` likewise; research log entry chained from iter-31 PDF-regen tip. Rerun wall-clock: profitability 45 min, piotroski/accruals ≈ 45 min each, momentum/ivol/52w ≈ 4-5 min each — unoptimized but dominated by the 500-rep block-bootstrap permutation test, not by compute_* functions.

#### Eighth Action: Wave-1 benchmark & evaluation infrastructure (2026-04-21 / 2026-04-22, iter-1..iter-3)

All gate-irrelevant and diagnostic-only. Gates (G0-G5) and admission verdicts from iter-0 remain the sole admission truth.

**iter-1 — benchmark_relative_metrics (2026-04-21, commit `f3e340e`).** Migrated SPY and RSP OHLCV out of the main `ohlcv` table into an isolated `benchmark_ohlcv` table (2,012 rows × 2 symbols) to preserve iter-0's bit-exact 491-symbol factor universe (main ohlcv restored to 960,072 rows × 491 symbols). New pure leaf `src/nyse_core/benchmark_metrics.py::compute_benchmark_relative_metrics` returns `(result, Diagnostics)` with per-benchmark `sharpe_excess`, `mean_excess_ann`, `tracking_error_ann`, `information_ratio`, `beta`, `alpha_ann`, `n_obs` — handles empty portfolio / empty benchmark / no-overlap / zero-variance as NaN payloads with warnings. `scripts/screen_factor.py` now loads SPY+RSP from benchmark_ohlcv, builds 5-day forward returns, and persists the metrics under `screening_metrics.json`. 8 new tests pass; full suite 1,151 pass. **AP-6: diagnostic only** — no G0-G5 threshold compared against these metrics.

**iter-2 — sector_neutral benchmark helper (2026-04-21, commit `9a9378c`).** Shipped `compute_sector_neutral_returns(daily_returns, sector_map) -> (Series, Diagnostics)` in new module `src/nyse_core/benchmark_construction.py` as a pure leaf. Two-stage equal-weight mean: (1) per-date, equal-weight within sector (NaN returns dropped); (2) equal-weight across sectors that reported that day. Unclassified symbols excluded with info-level diagnostic. 10 new tests (two-stage-mean matches hand-computed values, unequal-sector-size equal-weight, NaN-drop within sector, unmapped exclusion, NaN sector labels, empty panel, empty sector_map, no-overlap, all-NaN day degrades to NaN, output index equals input). Real 491-symbol GICS map deferred to iter-3 because attribution.py (Brinson) ALSO needs the same sector_map, so sourcing once serves both. Module pre-announces characteristic-matched benchmark slot for iter-4.

**iter-3 — sector map + Brinson wiring (2026-04-22, commit `0a30f31`).** Three co-designed changes: (a) one-shot `scripts/fetch_gics_sectors.py` pulls the Wikipedia S&P 500 constituents table (fetched 2026-04-21T23:30:42+00:00) and writes `config/gics_sectors_sp500.csv` with an 8-line #-prefixed provenance header (source URL, fetched_at, n_rows, n_sectors, PiT caveat on Sep-2018 Communication Services creation) — 503 symbols × 11 sectors, 100% coverage of the 491-symbol iter-0 universe. (b) `src/nyse_core/sector_map_loader.py` is a new pure `(pd.Series, Diagnostics)` loader that reads the CSV (skipping comment lines), validates required columns, first-wins-deduplicates with warning, preserves NaN sectors; 7 new tests. (c) `src/nyse_core/factor_screening.py::compute_long_short_weights` mirrors `compute_long_short_returns`'s quintile logic EXACTLY (`pd.qcut(..., duplicates="drop")`, same cross-sectional rank) and emits dollar-neutral per-date weights (sum longs=+1, sum shorts=-1); 7 new tests. `scripts/screen_factor.py` now persists `benchmark_relative_metrics["sector_neutral"]` (via iter-2 helper) and `screening_metrics.json["brinson_attribution"]` (via `compute_attribution` on long-short weights × factor exposures × sector map) with graceful degradation (empty sector_map → skip Brinson, empty fwd → skip both). Static-CSV + commit-provenance pattern rationale: runtime Wikipedia fetch would produce a moving sector map between re-screens (AP-6 violation risk); the committed CSV freezes the map and forces any change through a pre-registered correction event. Tests: 14 new (iter-3 targeted pass 38/38); full suite 853 pass with 1 pre-existing pytest-timeout in `test_optimizer::test_ap7_warning_fires` that reproduces on base iter-2 commit (unrelated to iter-3). mypy and ruff clean on all modified/new files. **AP-6: diagnostic only** — sector_neutral and Brinson payloads never enter screen_factor's verdict logic; TODO-11 / TODO-23 untouched; hash chain preserved (iter-2 tip `2a030ef3...b4a42142` → iter-3 tip `2c0fe425...ea2620cd`).

**What this unlocks.** Wave-1 iter-4 (characteristic-matched benchmark) can now compare the factor portfolio against SPY, RSP, and a sector-neutral equal-weight baseline side-by-side, and attribute the long-short return into factor-selection vs sector-allocation components — diagnostic infrastructure that was the precondition for iter-5+ portfolio-construction alternatives.

#### Ninth Action: Wave-1 close — characteristic-matched benchmark (2026-04-22, iter-4)

**iter-4 — characteristic-matched benchmark (commit `28681d2`, chain tip `98fd0417...81034de0`).** Shipped `compute_characteristic_matched_benchmark(daily_returns, characteristic_panel, portfolio_weights, n_buckets=5) -> (pd.Series, Diagnostics)` as a pure leaf alongside iter-2's `compute_sector_neutral_returns` in `src/nyse_core/benchmark_construction.py`. Size characteristic proxy built from 20-day mean of `close × volume` via a new `_build_size_panel` helper (also reused by iter-6 for cap-tilted weights). For each date, stocks are bucketed into quintiles of the size characteristic; the long-leg's weighted-mean bucket index is rounded to the nearest integer bucket; the return of that bucket's equal-weight mean is returned. Empty / zero-overlap / unmapped symbols degrade to NaN with warning diagnostics. 18 new tests (hand-computed two-stage means, monotone characteristic, NaN handling, empty inputs, multi-bucket-tie boundaries, single-bucket degeneracy, unmapped-symbol exclusion, matched-vs-universe degenerates to universe-mean when long-leg is universe, per-date bucket imbalance). Wired into `scripts/screen_factor.py` as `benchmark_relative_metrics["char_matched_size"]` — diagnostic only, never compared against G0-G5. Same commit also hoisted `ls_weights` to module scope for iter-5+ reuse. **AP-6: diagnostic only**; no threshold, admission, or sign change.

**Wave-1 (A-benchmark) CLOSES with iter-4.** All four benchmark references (SPY, RSP, sector_neutral, char_matched_size) now flow through `compute_benchmark_relative_metrics` in `screen_factor.py`. Admission verdicts from iter-0 (0/6 FAIL) untouched. Hash chain: iter-3 `2c0fe425...ea2620cd` → iter-4 `98fd0417...81034de0`.

#### Tenth Action: Wave-2 portfolio construction alternatives (2026-04-22, iter-5..iter-8)

All four iterations are additive pure-logic siblings in `src/nyse_core/` with `screen_factor.py` persistence but no gate wiring. Admission verdicts unchanged throughout.

**iter-5 — volatility-scaled long-short weights (commit `9ba9767`, chain tip `c1fa28f0...e38b2bcb`).** `compute_volatility_scaled_weights(factor_scores, vol_panel)` returns per-date within-leg weights inversely proportional to trailing-20d realized volatility (Carver's position-level vol targeting). Degenerates to equal-weight when all vols equal. `_build_vol_panel` helper (20d trailing std of `pct_change`) added alongside. Persisted as `alternative_portfolios.{vol_scaled, equal_weight_baseline}` in `screening_metrics.json`. 13 new tests.

**iter-6 — cap-tilted long-short weights (commit `da221c9`, chain tip `ec098b5c...29e4fedd`).** `compute_cap_tilted_weights(factor_scores, size_panel, tilt=0.5)` emits within-leg weights proportional to `size**tilt` (default sqrt-cap); `tilt=0` reduces to equal-weight, `tilt=1` to pure cap-weight. Reuses iter-4's `_build_size_panel`. Persisted as `alternative_portfolios.cap_tilted_sqrt` alongside iter-5's equal-weight baseline. 16 new tests.

**iter-7 — Sharpe-weighted ensemble aggregator (commit `a339e77`, chain tip `440fd21c...9bb20448`).** `compute_ensemble_weights(factor_score_panels, factor_sharpes)` combines per-factor score panels via Sharpe-weighted mean with per-(date, symbol) re-normalization so coverage gaps don't penalize a stock. Non-finite / non-positive Sharpes and panels missing `{date, symbol, score}` silently excluded with diagnostic info. 17 tests (equal-Sharpe ↦ simple mean, single-factor passthrough, uniform-scaling invariance, orphan-row reweighting, and degeneracy paths). No `screen_factor.py` wiring — Wave-4 will gate its admission.

**iter-8 — risk-parity across factor legs (commit `1c82509`, chain tip `ed7cce93...ef2d92f0`).** `compute_risk_parity_weights(factor_returns, cov_matrix=None, max_iter=200, tol=1e-8)` implements Maillard-Roncalli-Teiletche cyclical coordinate descent with dynamic σ_p² target; closed-form inverse-volatility fallback when σ_p² ≤ 0 / discriminant non-finite / weight sum non-positive. 17 tests (equal-variance ↦ 1/n, diagonal distinct-variance ↦ inv-vol, analytical two-factor [2/3, 1/3], symmetric-correlated-pair shares weight, risk contributions equal at convergence within rtol 1e-5). No `screen_factor.py` wiring.

**Wave-2 (B-portfolio) CLOSES with iter-8.** All four portfolio-construction alternatives shipped as diagnostic-only pure helpers. **AP-6: all diagnostic** — no gate, threshold, sign, or admission change; TODO-11 / TODO-23 untouched.

#### Eleventh Action: Wave-3 gate calibration audit — in-force gate family canonicalized (2026-04-23, iter-9..iter-11)

**iter-9 — audit memo (commit `ead47d8`, chain tip `38c7bfa5...71c5bb18`).** `docs/audit/gate_calibration_audit.md` (GCA-2026-04-23, 256 lines, 11 sections) — structural AP-6 pre-registration compliance audit of `config/gates.yaml` (sha256 `521b7571...f559af4`) against plan-of-record `/.claude/plans/dreamy-riding-quasar.md` §gates.yaml. **Finding: in-force gate family is a semantic redesign, not calibration drift.** Every gate G0-G5 differs in metric identity (plan `coverage / ic_ir / max_corr / sharpe_delta / fullsample_delta / date_gap` vs in-force `oos_sharpe / permutation_p / ic_mean / ic_ir / max_drawdown / marginal_contribution`); no row matches on both metric and threshold. In-force family introduced at commit `339fa10` (2026-04-18 CI/CD infrastructure commit that did not mention gate redefinition); no GOVERNANCE_LOG authorization existed. GL-0002..GL-0008 cite the plan's family in the rationale column while evidence files were produced by the in-force family — a concrete reproducibility failure. AP-6 **technically compliant** (frozen before first screen), **procedurally non-compliant** (no plan cross-reference, no governance-log freeze row). Findings-only memo; no correction proposed.

**iter-10 — presentation event + halt (commit `63821f4`, chain tip `677f39bf...97f814ab`).** Emits the iter-9 audit findings as a research-log event and halts pending operator authorization. No threshold, admission, or code change. Presents three clean correction paths — A (amend plan to match config, two-way door), B (amend config to match plan, one-way, re-run screens), C (hybrid adding missing gates as pre-registered extensions) — plus space for an operator-defined path D. Recommended posture: path C preserves current evidence and restores plan's redundancy + data-hygiene guards; iter-10 itself takes no position. iter-11 would not proceed autonomously.

**iter-10-supplemental — root-cause + consequences memo (commit `fdc5952`, chain tip `061334bf...c26fd6b2`).** `docs/audit/gate_mismatch_root_cause_and_consequences.md` (GCA-2026-04-23-supplemental, 258 lines, 7 sections) prompted by operator follow-up with two questions. **Q1 root cause:** iter-1 source tree authored off-repo between initial commit `902cd41` (2026-04-15, plan+docs only) and bulk landing `339fa10` (2026-04-18 20:35, CI-framed commit whose body admits "lands the iter-1 source tree... previously on disk but never committed"). During that window, all six factor screens were run and docs were updated citing files not yet in git. Six contributing factors made the redesign invisible: `339fa10` CI framing; no GOVERNANCE_LOG freeze row for `gates.yaml` (unlike GL-0001 for `falsification_triggers.yaml`); **smoking gun** `config/gates.yaml:5` saying *"aligned with `factor_screening.screen_factor()`"* (config aligned to code, not plan); pre-commit hooks syntactic not semantic; GL-0002..GL-0008 rationale vs evidence column mismatch; and a prior researcher's near-flag at `NYSE_ALPHA_RESEARCH_RECORD.md:373` reframed as a single-threshold typo rather than family-level redesign. **Q2 consequences:** four structural guards LOST (universe-coverage HIGH-MEDIUM, max-correlation HIGH, full-sample-robustness MEDIUM-HIGH, date-gap LOW-MEDIUM), four signal-quality bars GAINED or TIGHTENED (oos_sharpe ≥ 0.30, permutation_p < 0.05, max_drawdown ≥ -0.30, ic_ir tightened 25× from plan's 0.02 to in-force 0.50). Net: not catastrophic (signal-quality stricter), but hygiene weakening should be explicit rather than silent.

**iter-11 — correction path A applied (commit `4a5ed89`, chain tip `ce0cdfb1...da009064`).** Operator authorized path A on 2026-04-23 with standing authorization to re-run `/ralph-loop` from iter-1 if needed (not needed — path A is docs-only / two-way door). Four documentation artifacts amended: (1) `docs/GOVERNANCE_LOG.md` — appends **GL-0010** (freeze in-force gate family as canonical; cites config sha256 `521b7571...f559af4` and audit memos `ead47d8` + `fdc5952`) and **GL-0011** (clarify GL-0002..GL-0008 evidence-vs-rationale mismatch by re-affirming all 7 reject decisions under the in-force family without editing those rows — each of ivol_20d / high_52w / momentum_2_12 / piotroski / accruals / profitability failed ≥3 of 6 in-force gates); §3 state table gains a gate-family-frozen row; §7 last-reviewed bumped to 2026-04-23. (2) `/.claude/plans/dreamy-riding-quasar.md` §gates.yaml — amended to in-force family with an amendment-history prose note linking to GL-0010 and the two audit memos; pre-amendment family (coverage / ic_ir@0.02 / max_corr / sharpe_delta / fullsample_delta / date_gap) documented for historical trace. (3) `docs/templates/factor_screen_memo.md` §3 — amendment note + verdict table rewritten to in-force family; future memos inherit the canonical family. (4) This record, §357 — discrepancy paragraph rewritten to mark RESOLVED via path A + GL-0010; path D struck-through with resolution marker; path E preserved as independent future option.

**Two-way-door posture.** `config/gates.yaml` sha256 `521b7571...f559af4` unchanged before/after; no tests added or modified; no code path touched; no screens re-run; all 6 FAIL verdicts re-affirmed under in-force family per GL-0011. AP-6 compliance flips from technically-but-not-procedurally compliant to **both technically and procedurally compliant** (plan + template match in-force config; governance log authorizes the freeze). GOVERNANCE_LOG iron-rule append-only preserved (GL-0002..GL-0008 NOT edited; superseded in interpretation by appended GL-0011 row).

**Not restored in path A.** The plan's four pre-amendment structural guards — G0-plan universe-coverage, G2-plan max-correlation, G4-plan full-sample-robustness, G5-plan date-gap — are **not** restored by path A. Re-visitation deferred to Wave 4+ per `docs/audit/gate_mismatch_root_cause_and_consequences.md` §4 forward-looking mitigation note (standing TODO to re-evaluate redundancy at the ensemble-construction layer bounds the highest-severity loss without changing the admission gate family).

**iter-11-D — PATH D governance correction (commit `7656537`, chain tip `2107dbb5...d613b76c`).** Following the iter-11 path-A application earlier the same day, the operator requested adversarial review of the path-A decision via `/codex` consult (session `019dba41-f163-70e1-875b-909771c26083`, 68,078 tokens). Codex's verdict was that path A was wrong — it would establish an AP-6-incompatible precedent that "implementation beats plan-of-record when implementation happened to land first" — and recommended PATH D (quarantine the incident, canonicalize neither family, pre-register a v2 family prospectively) combined with PATH E (renegotiate Phase 3 exit target as a separate pre-registered event to avoid target-family double-fitting). Operator accepted Codex's recommendation. Iter-11-D appends **GL-0012** (reverses GL-0010's canonicalization claim; declares both the plan's pre-amendment family and the in-force family **provisional** pending a v2 gate family pre-registered prospectively in iter-13+) and **GL-0013** (activates PATH E — Phase 3 exit target OOS Sharpe 0.5–0.8 under renegotiation; new target pre-registered before the v2 gate family is finalized). Four documentation artifacts amended: (1) `docs/GOVERNANCE_LOG.md` — GL-0012 + GL-0013 appended; §3 gate-family row re-flagged PROVISIONAL; new Phase 3 exit target row added; §7 last-reviewed bumped to iter-11-D. (2) `/.claude/plans/dreamy-riding-quasar.md` §gates.yaml heading + amendment note rewritten to iter-11-D (PROVISIONAL, both families); §Phase 3 target line annotated with PATH E renegotiation. (3) `docs/templates/factor_screen_memo.md` §3 amendment note rewritten; memos instantiated against current family are "engineering outputs, not canonical admission decisions". (4) This record: §357 update paragraph; path D/E strikethrough + activation annotations; path C recommendation footer re-phrased; this §Eleventh Action closing narrative. **DOCS-ONLY, TWO-WAY DOOR:** `config/gates.yaml` sha256 `521b7571...f559af4` unchanged; no test added or modified; no code path touched; no screens re-run; GL-0011's re-affirmation of the 6 FAIL verdicts (ivol_20d / high_52w / momentum_2_12 / piotroski / accruals / profitability) remains valid because each factor fails ≥3 of 6 gates under *either* family, so admission is invariant to the choice. Iron rule append-only preserved: GL-0010 and GL-0011 not edited — GL-0012 supersedes GL-0010's canonicalization claim by appending a new row. AP-6 posture: path A's "technically + procedurally compliant" claim is withdrawn; path D's posture is "technically compliant (config frozen before first screen), procedurally contested pending v2 pre-registration." V2 gate family will combine economically meaningful signals from both legacies (absolute OOS Sharpe + permutation significance + drawdown from in-force; redundancy control + full-sample robustness + data-hygiene guards from plan) before any new admission decision is cited. Chain transition: iter-11 tip `ce0cdfb1...da009064` → iter-11-D tip `2107dbb5...d613b76c`.

**Wave-3 (C-gate-calibration) CLOSES with iter-11-D follow-up.** Wave 4 (multi-factor admission reform) unlocks with the constraint that its iter-13 includes the v2 gate family pre-registration authorized by GL-0012, and a separate pre-registered Phase 3 exit target renegotiation authorized by GL-0013. iter-0 bit-exactness preserved; hash chain preserved end-to-end via `scripts/verify_research_log.py`; TODO-11 and TODO-23 untouched.

### Key Decisions Made

1. **PCA deduplication before ensemble:** From TWSE Phases 48-50, where 7 short-interest variants collapsed to 1.91 effective dimensions. The short_pca_composite factor captures the same information with less multicollinearity.

2. **13-16 factor target, hard ceiling at 20:** TWSE Rule #14 -- performance peaked at 16 factors. Beyond that, Ridge regularization fights noise rather than capturing new signals.

3. **Momentum included despite TWSE failure:** TWSE momentum failed because of daily price limits (+-10%) creating forced mean reversion. NYSE has no such limits. Momentum should work on NYSE, but this is a hypothesis to be validated, not an assumption.

### Test Results

~210 tests added. Coverage: every factor computation (edge cases, NaN handling, sign convention), factor registry anti-double-dip, correlation matrix computation, PCA decomposition, attribution decomposition, synthetic calibration recovery rate.

### Surprises

1. **Momentum uncertainty:** The TWSE project's most dramatic failure was momentum (-0.278 Sharpe). Whether NYSE momentum works is the single biggest open question in this project. The factor is implemented and will be gated, but we have no strong prior.

2. **NLP earnings data quality:** Transcript sentiment analysis requires clean text parsing of SEC EDGAR 8-K filings. The quality varies dramatically across companies. Some filings are well-structured HTML; others are scanned PDFs. This factor is classified as experimental (EXP-6).

3. **Short interest PCA compression:** Even before seeing NYSE data, the architectural decision to include a PCA composite was validated. The three raw short interest factors (short_ratio, days_to_cover, short_pca) capture overlapping information. PCA should extract the informative dimension.

---

## 6. Phase 4: Optimization and ML Alternatives

**Objective:** Add GBM and Neural model alternatives, fix the walk-forward backtest to be truly strict, build drift detection, and add monitoring infrastructure. This was the largest and most impactful phase.

**Duration:** Fifth major build phase. Executed with 5 parallel agents, zero cross-agent file conflicts.

### What Was Built

**Agent 1: Research Pipeline Rewrite (Critical)**

`research_pipeline.py` (501 LOC) was fully rewritten. This was the most impactful change in the project -- it fixed four fatal bugs in the walk-forward backtest:

**Bug 1 -- Feature averaging across dates:**
```
BEFORE: Averaged forward returns across ALL train dates, losing the
        cross-sectional structure. One giant average per stock.

AFTER:  _build_train_stack() iterates weekly through train dates,
        computing features independently at each rebalance date using
        a trailing 252-day OHLCV window. Stacks cross-sections into
        a MultiIndex (rebal_date, symbol) DataFrame for training.
```

**Bug 2 -- Feature reuse between train and test:**
```
BEFORE: Used features computed during training for test predictions.
        This is lookahead bias: test features should reflect only
        information available at the test date.

AFTER:  _run_test_dates() recomputes features at each test date
        using only the trailing 252-day OHLCV window up to that date.
        No feature sharing between train and test.
```

**Bug 3 -- Hardcoded turnover and cost:**
```
BEFORE: annual_turnover=0.0, cost_drag_pct=0.0 hardcoded in results.
        Made every backtest look free.

AFTER:  Dynamic computation at each test rebalance:
        - Turnover = sum(|new_weight - old_weight|) for all stocks
        - Cost = sum(estimate_cost_bps(ADV) x trade_weight) per stock
        - Annualized turnover = avg_turnover x (252 / rebal_step)
```

**Bug 4 -- No memory management:**
```
BEFORE: Accumulated all fold data in memory. 8-year dataset with
        500 stocks would exhaust RAM.

AFTER:  gc.collect() between folds. Trailing windows limit OHLCV
        to 252 x 1.5 = 378 calendar days per feature computation.
        Train/test data deleted after each fold.
```

19 integration tests in `test_strict_backtest.py` validate the rewrite.

**Agent 2: ML Alternatives**

**models/gbm_model.py (~165 LOC)** -- LightGBM with early stopping (80/20 internal holdout), `verbose=-1`, L2 regularization (`reg_lambda=1.0`). Graceful degradation: if `lightgbm` is not installed, import raises `ImportError` caught by the factory.

**models/neural_model.py (~200 LOC)** -- PyTorch 2-layer MLP: Input -> Linear -> ReLU -> Dropout -> Linear -> ReLU -> Dropout -> Linear(1). Target y is standardized before training and unstandardized after prediction. Early stopping on validation loss.

**strategy_registry.py (~280 LOC)** -- `StrategyRegistry` manages multiple model configurations and their backtest results. `select_best()` enforces two guardrails: (1) must beat Ridge by >= 0.1 OOS Sharpe, (2) overfit ratio < 3.0. From TWSE: Ridge overfit ratio was 1.08x; LightGBM was 6.9x.

41 unit tests validate model implementations and registry logic.

**Agent 3: Optimization + PCA**

**optimizer.py (119 LOC)** -- Walk-forward parameter tuning. `tune_parameters()` evaluates parameter grid while respecting AP-7 (max 5 parameters with < 60 monthly observations).

**factor_correlation.py (~200 LOC)** -- PCA factor deduplication. `pca_factor_decomposition()` with auto-selection by cumulative variance threshold (default: 90%). Selects highest-IC representative per principal component.

20 tests covering optimizer convergence, PCA variance thresholds, and factor selection.

**Agent 4: Monitoring + Dashboard**

**drift.py (357 LOC)** -- 3-layer drift detection:
- Layer 1: Rolling 60-day IC per factor (threshold: 0.015, negative slope)
- Layer 2: IC sign flips per factor in trailing 2 months (threshold: > 3 flips)
- Layer 3: Rolling R-squared between predicted and actual portfolio returns

`DriftReport` dataclass aggregates assessment with urgency levels (NONE / LOW / MEDIUM / HIGH).

**nyse_ats/monitoring/dashboard.py** -- Streamlit dashboard with `DashboardState` protocol. Displays portfolio, risk metrics, factor health, attribution, falsification triggers, and alerts. Cost drag displayed ABOVE Sharpe (TWSE lesson #13.3: monitor cost before performance).

**Enhanced falsification monitoring** -- All 8 triggers (F1-F8) with automated response protocol. VETO triggers halt trading immediately; WARNING triggers reduce exposure to 60%.

82 tests covering drift detection edge cases, dashboard state management, and trigger evaluation.

**Agent 5: Property Test Fix**

Fixed z-score Hypothesis property test: relaxed tolerance from 1e-8 to 1e-6 for the near-zero variance edge case. When input variance is < 1e-10, floating point error in z-score computation exceeds 1e-8 tolerance. The relaxed tolerance is correct for this edge case.

### Key Metrics

| Metric | Value |
|--------|:-----:|
| Tests before Phase 4 | 792 |
| Tests after Phase 4 | **934** (+142) |
| Tests passing | 934 |
| Tests failing | 0 |
| Tests skipped | 30 (optional deps: lightgbm, torch) |
| Parallel agents | 5 |
| Cross-agent conflicts | 0 |

### Key Decisions Made

1. **Ridge remains default.** GBM and Neural are available but gated. The gating criteria (beat Ridge by > 0.1 OOS Sharpe AND overfit ratio < 3.0) are deliberately strict because the TWSE experience showed GBM overfitting 6.9x.

2. **Per-date feature recomputation is non-negotiable.** The Phase 4 rewrite makes the backtest ~3x slower but eliminates lookahead bias. In production, features are always computed from the latest available data. The backtest must simulate this exactly.

3. **Cost drag as primary monitoring metric.** The dashboard displays cost drag above Sharpe. From TWSE lesson: a strategy with positive gross Sharpe and negative net Sharpe looks profitable until you check the cost.

### Surprises

1. **The four walk-forward bugs were present from Phase 1.** They were not caught earlier because (a) feature averaging across dates still produces reasonable-looking Sharpe ratios -- just inflated ones, and (b) hardcoded zero turnover and cost makes every strategy look good. These are exactly the "silent infrastructure lies" the TWSE project warned about.

2. **Memory management mattered sooner than expected.** With 500 stocks, 8 years of data, and weekly rebalancing, a single walk-forward backtest without `gc.collect()` consumed 12+ GB of RAM. The trailing window limit (378 calendar days) reduced peak memory to ~3 GB.

3. **Zero cross-agent conflicts with 5 parallel agents.** The module boundary design (pure core vs side-effect shell) meant each agent could work independently. Agent 1 touched `research_pipeline.py` and its tests. Agent 2 touched `models/` and `strategy_registry.py`. No overlapping files.

---

## 7. Phase 5: Paper Trading (Planned)

**Objective:** Run a 3-month simulated $1M paper trade using the complete pipeline.

**Status:** Not started. Next phase.

### Plan

1. **Pipeline orchestrator:** Build end-to-end weekly execution: download data -> PiT enforce -> compute features -> normalize -> impute -> Ridge combine -> allocate -> risk stack -> generate TradePlan -> paper-execute -> record results.

2. **3-month paper run (target: May-July 2026):** Simulated $1M capital. Weekly rebalance every Friday signal / Monday execution. All 8 falsification triggers active.

3. **Exit criteria for paper trade:**
   - IC within expected range (rolling 60-day mean IC > 0.015)
   - No VETO trigger fired
   - Cost drag < 5% annual
   - Fill rate simulation > 95%

4. **TRUE HOLDOUT test:** One-shot evaluation on 2024-2025 data. No iteration permitted after this test. Required: OOS Sharpe > 0.

### Dependencies

- All Phase 4 modules operational (complete)
- FinMind API access configured (complete)
- EDGAR adapter tested against live filings (complete)
- FINRA data pipeline validated (complete)
- NautilusTrader paper mode tested (not started -- critical path)

---

## 8. Phase 6: Live Deployment (Planned)

**Objective:** Graduate from paper to live trading through a deployment ladder.

**Status:** Not started.

### Deployment Ladder

| Stage | Capital | Duration | Entry Gate | Exit Criteria |
|-------|---------|----------|------------|---------------|
| Paper | Simulated $1M | 3 months | Synthetic calibration + permutation p < 0.05 | IC in range, no VETO |
| Shadow | Real prices, no orders | 1 month | Paper gates passed | Fills match real within 10 bps |
| Min Live | $100K real | 3 months | Shadow gates passed | Realized Sharpe > 0, fill rate > 95% |
| Scale | $500K-$2M | 6 months | Min live gates passed | Slippage < 15 bps, ADV impact < 1% |

### Shadow-to-Live Graduation (ALL 7 must pass)

1. `min_trading_days >= 20`
2. `mean_slippage_bps < 20`
3. `rejection_rate < 5%`
4. `settlement_failures == 0`
5. `fill_rate > 95%`
6. `rolling_ic_20d > 0.02`
7. `cost_drag_pct < 5%`

---

## 9. Cross-Cutting Lessons

### From the TWSE Predecessor (Inherited)

These lessons were applied before writing code. Every one was learned by failing first on the TWSE project.

1. **Every major Sharpe improvement came from fixing infrastructure, not finding better signals.** The walk-forward rewrite (this project's Phase 4) was a bigger improvement than any factor addition. Same pattern as TWSE.

2. **Turnover is the silent killer.** Cost drag is monitored ABOVE Sharpe on the dashboard. A strategy that trades too much can have positive gross Sharpe and negative net Sharpe.

3. **Ridge beats trees.** With 13-16 factors, Ridge's regularization is honest about what the data supports. GBM overfits 6.9x on TWSE.

4. **Sell buffer is free money.** 1.5x sell buffer saved ~1,644 bps on TWSE and added +0.040 Sharpe. Pure turnover reduction.

5. **Binary regime beats continuous vol-scaling.** SMA(200) binary gate is simpler and works better. Continuous vol-targeting failed because the vol-target parameter was itself unstable.

6. **Point-in-time enforcement is non-negotiable.** Every data point must have a publication lag. Features that "look back" to the future are the most common source of inflated backtest results.

7. **Every factor needs a friction hypothesis.** If you cannot explain WHY a factor works (what market friction or behavioral bias it exploits), it is probably curve-fitting.

8. **The Diagnostics pattern replaces logging.** `(result, Diagnostics)` tuples provide full traceability without any I/O side effects in the core computation modules.

### Discovered During This Project

9. **Module boundaries prevent parallel agent conflicts.** The pure core / side-effect shell architecture enabled 5 parallel agents with zero file conflicts in Phase 4. The architecture that makes testing easy also makes parallelism easy.

10. **Silent infrastructure bugs reproduce across projects.** The same class of bug (hardcoded zeros for turnover/cost, feature reuse between train/test) appeared in both the TWSE and NYSE projects despite explicit warnings. The fix is automated tests, not documentation.

11. **TWSE factors do not transfer blindly to NYSE.** Momentum failed catastrophically on TWSE (-0.278 Sharpe) but may work on NYSE (no daily price limits). Market structure is not a detail -- it determines which factors are viable. Every factor must be validated on the target market.

12. **DuckDB is a better foundation than flat files.** The TWSE system's Parquet-file storage made concurrent access and schema enforcement difficult. DuckDB provides SQL, ACID, and columnar storage without a server.

---

*One-Pager: [NYSE_ALPHA_ONE_PAGER.md](NYSE_ALPHA_ONE_PAGER.md) | Technical Brief: [NYSE_ALPHA_TECHNICAL_BRIEF.md](NYSE_ALPHA_TECHNICAL_BRIEF.md) | System Reference: [FRAMEWORK_AND_PIPELINE.md](FRAMEWORK_AND_PIPELINE.md) | Outcomes: [OUTCOME_VS_FORECAST.md](OUTCOME_VS_FORECAST.md) | Validation: [INDEPENDENT_VALIDATION_DRAFT.md](INDEPENDENT_VALIDATION_DRAFT.md) | DDQ: [DDQ_AIMA_2025.md](DDQ_AIMA_2025.md) | Integrity: [RESEARCH_RECORD_INTEGRITY.md](RESEARCH_RECORD_INTEGRITY.md)*
