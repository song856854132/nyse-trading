# MLOps Lifecycle

**NYSE ATS Framework | v0.4 | April 2026**

> **Status:** Research and development stages complete (Phases 0-4). Paper trading pipeline (Phase 5) not yet started.

---

## 1. Lifecycle Overview

```
+----------+    +-----------+    +------------+    +---------+
| Research |===>| Develop-  |===>| Validation |===>| Staging |
| (explore |    |  ment     |    | (gates +   |    | (paper  |
|  factors, |    | (implement|    |  stats)    |    |  trade) |
|  hypothe-|    |  pipeline)|    |            |    |         |
|  size)   |    |           |    |            |    |         |
+----------+    +-----------+    +------------+    +---------+
                                                       |
     +----------+    +------------+    +-----------+   |
     | Retrain  |<===| Monitoring |<===| Production|<==+
     | (walk-fwd|    | (drift,    |    | (shadow   |
     |  with new|    |  falsific.,|    |  -> live  |
     |  data)   |    |  dashboard)|    |  -> scale)|
     |          |===>| (triggers  |    |           |
     +----------+    |  feedback) |    +-----------+
                     +------------+
```

---

## 2. Lifecycle Stages

### 2.1 Research

| Aspect | Detail |
|---|---|
| **Entry Criteria** | Factor hypothesis with friction/behavioral rationale (TWSE lesson: every factor needs a friction hypothesis) |
| **Activities** | Literature review, factor computation, standalone IC analysis, cross-sectional correlation check, PCA deduplication |
| **Exit Criteria** | Factor passes G0 (coverage >=50%) and G1 (IC_IR >=0.02); not redundant with existing factors (G2: max corr <0.50) |
| **Artifacts** | Factor implementation in `features/*.py`, experiment log entry, screening report |
| **Responsible** | Researcher (system operator) |

### 2.2 Development

| Aspect | Detail |
|---|---|
| **Entry Criteria** | Factor passes initial screening (G0-G2) |
| **Activities** | Integration into `FactorRegistry` with sign convention and usage domain; normalization to [0,1] rank-percentile; imputation handling; unit tests; property tests |
| **Exit Criteria** | All existing tests pass (934+); new factor has unit test coverage; AP-3 (no double-dip) enforced; AP-8 ([0,1] range) enforced |
| **Artifacts** | Updated `features/*.py`, test files in `tests/`, updated `FactorRegistry` entries |
| **Responsible** | Developer (system operator) |

### 2.3 Validation

| Aspect | Detail |
|---|---|
| **Entry Criteria** | Factor integrated with passing tests |
| **Activities** | Walk-forward CV with purge/embargo (`cv.py`), permutation test (`statistics.py`, p<0.05), Romano-Wolf stepdown, block bootstrap CI, G3 (OOS Sharpe delta >0), G5 (marginal contribution >0) |
| **Exit Criteria** | All G0-G5 gates PASS; permutation p <0.05; bootstrap CI lower bound >0; overfit ratio <3.0 |
| **Artifacts** | `GateVerdict` in `research.duckdb`, `BacktestResult`, experiment log entry |
| **Responsible** | Researcher/Validator |

### 2.4 Staging (Paper Trading)

| Aspect | Detail |
|---|---|
| **Entry Criteria** | All G0-G5 pass; synthetic calibration passed; permutation p <0.05 |
| **Activities** | 90-day paper trading run with simulated $1M; weekly rebalance via pipeline orchestrator; monitor IC, cost drag, falsification triggers |
| **Exit Criteria** | No VETO trigger in 90 days; IC remains in target range; cost drag <5% |
| **Artifacts** | Paper trading logs in `live.duckdb`, drift reports, weekly summaries |
| **Responsible** | System operator |

### 2.5 Production

Production has three sub-stages per the deployment ladder (`config/deployment_ladder.yaml`):

| Sub-Stage | Capital | Duration | Key Criteria |
|---|---|---|---|
| **Shadow** | $0 (real prices, no orders) | 30 days | Simulated fills match real within 10 bps |
| **Minimum Live** | $100K real | 90 days | Realized Sharpe >0, fill rate >95% |
| **Scale** | $500K-$2M | 180 days | Slippage <15 bps, ADV impact <1% |

Shadow-to-live graduation requires ALL 7 criteria (from `deployment_ladder.yaml`):

```
1. min_trading_days >= 20
2. mean_slippage_bps < 20
3. rejection_rate < 5%
4. settlement_failures == 0
5. fill_rate > 95%
6. rolling_ic_20d > 0.02
7. cost_drag_pct < 5%
```

### 2.6 Monitoring

| Aspect | Detail |
|---|---|
| **Entry Criteria** | Model deployed in any production sub-stage |
| **Activities** | Drift detection (3 layers), falsification trigger checks (F1-F8), dashboard review, cost drag monitoring |
| **Exit Criteria** | N/A (continuous); triggers retrain or halt |
| **Artifacts** | `DriftReport`, `FalsificationCheckResult`, dashboard snapshots, Telegram alert archive |
| **Responsible** | System operator + automated alerts |

### 2.7 Retrain

| Aspect | Detail |
|---|---|
| **Entry Criteria** | Drift detected with urgency "medium" or "high"; or scheduled periodic retrain |
| **Activities** | Walk-forward CV with latest data; re-evaluate all gates; compare with current model |
| **Exit Criteria** | New model passes all G0-G5; outperforms or matches current model OOS; human approval |
| **Artifacts** | New model version, comparison report, experiment log entry |
| **Responsible** | System operator (human approval gate) |

---

## 3. Model Training Pipeline

```
Data Ingestion (FinMind/EDGAR/FINRA + rate_limiter, retry 3x)
        |
        v
PiT Enforcement (pit.py: OHLCV T+0, 10-Q T+45, Short Int. T+11)
        |
        v
Feature Engineering (13+ factors across 6 families, FactorRegistry)
        |
        v
Normalization + Imputation (rank_percentile [0,1], median if <30% NaN)
        |
        v
Cross-Validation (PurgedWalkForwardCV, expanding window, 2016-2023)
        |
        v
Model Fitting (Ridge default; GBM/Neural gated: +0.1 Sharpe, <3.0 overfit)
        |
        v
Evaluation (permutation_test, romano_wolf, bootstrap CI)
        |
        v
Gate Check (G0-G5 via ThresholdEvaluator)
        |                    |
   ALL PASS              ANY FAIL
        |                    |
        v                    v
   Promotion            Rejection
   (advance stage)      (log rationale)
```

---

## 4. Monitoring and Drift Detection

The drift detection system in `drift.py` operates in three layers, each detecting a different failure mode:

| Layer | Module Function | Detection Logic | Threshold | Escalation |
|---|---|---|---|---|
| **1: IC Drift** | `detect_ic_drift()` | Rolling 60-day mean IC per factor; drift if mean_ic < 0.015 AND slope negative | 0.015 (configurable) | Retrain recommended |
| **2: Sign Flips** | `detect_sign_flips()` | Count IC sign changes in trailing 2 months (~42 days); zeros excluded | >3 flips = F2 VETO risk | Immediate investigation |
| **3: Model Decay** | `detect_model_decay()` | Rolling R-squared of predicted vs actual returns over 60 days | R2 < 0.0 = worse than mean | Urgency elevation |

### Urgency Assessment (`assess_drift`)

| Condition | Urgency | Action |
|---|---|---|
| >50% factors drifting | High | Retrain urgently |
| >25% factors drifting | Medium | Schedule retrain |
| Any factor drifting | Low | Monitor closely |
| Sign flip VETO risk OR R2 < 0 | Elevated to at least Medium | Investigate + retrain |
| None | None | Continue normal operation |

**Auto-retrain trigger:** When `assess_drift` returns `retrain_recommended = True`, a Telegram alert is sent. Human operator must review and approve before any model replacement. No automatic model swap is permitted.

---

## 5. Retraining Protocol

### When to Retrain

| Trigger | Source | Urgency |
|---|---|---|
| IC decay below threshold for >50% of factors | `drift.py: assess_drift` | High |
| IC decay below threshold for >25% of factors | `drift.py: assess_drift` | Medium |
| Any single factor IC drift detected | `drift.py: assess_drift` | Low |
| F1 Signal Death VETO fires | `falsification_triggers.yaml` | Immediate (halt first) |
| Scheduled periodic retrain | Calendar (quarterly) | Routine |

### How to Retrain

1. **Data update:** Ingest latest OHLCV, fundamentals, and short interest data.
2. **Feature recomputation:** Run full feature pipeline with updated data, maintaining PiT enforcement.
3. **Walk-forward CV:** Run `PurgedWalkForwardCV` with expanded training window including new data. Research period extends but holdout remains untouched.
4. **Gate evaluation:** All G0-G5 gates must pass for the retrained model.
5. **Comparison:** Compare retrained model against current production model using the version comparison format (see `AUDIT_TRAIL.md` Section 2).
6. **Decision:** Human operator approves or rejects based on comparison.

### Validation Before Promotion

- Retrained model must achieve OOS Sharpe >= current model OOS Sharpe - 0.05 (allow small regression).
- Overfit ratio must remain <3.0.
- Permutation p-value must remain <0.05.
- All falsification trigger thresholds must still be satisfied.
- If retrained model underperforms, retain current model and investigate root cause.

### Rollback If New Model Underperforms

If a promoted retrained model underperforms within the first 20 trading days:

1. Activate kill switch (`kill_switch: true`).
2. Restore previous model version from archive.
3. Run abbreviated validation (permutation test + gate check on latest data).
4. Resume with previous model after human approval.
5. Log rollback event as experiment type `model_rollback`.

---

## 6. Infrastructure

### Storage

| Component | File | Purpose |
|---|---|---|
| Research database | `research.duckdb` | All research experiments, gate verdicts, backtest results, model parameters |
| Live database | `live.duckdb` | Trade execution records, position snapshots, rebalance summaries, live drift reports |
| Configuration | `config/*.yaml` (6 files) | All system parameters, Pydantic-validated at startup via `config_schema.py` |

### Execution Engine

NautilusTrader is the position source of truth for all live/shadow/paper positions:

```
research_pipeline.py --> TradePlan (frozen dataclass)
                              |
                              v
                    nautilus_bridge.py
                              |
                    +---------+---------+
                    |         |         |
                  Paper    Shadow     Live
                  (sim     (real      (real
                   $1M)    prices,    orders)
                           no orders)
```

### Scheduled Pipeline Execution

```
Weekly cycle (production):

Friday close    --> Signal generation
                    research_pipeline.py computes features,
                    fits model, generates TradePlan
                    
Saturday/Sunday --> Validation checks
                    Drift assessment, falsification trigger check,
                    gate re-evaluation on latest data

Monday open     --> Execution
                    nautilus_bridge.py submits TWAP orders
                    30-minute execution window
                    Max 5% ADV participation rate

Monday close    --> Reconciliation
                    Compare NautilusTrader positions vs TradePlan
                    Log execution results to live.duckdb
                    Dashboard refresh
                    Telegram summary
```

### Dependency Management

All dependencies are declared in `pyproject.toml`. Optional dependencies (LightGBM, PyTorch) are isolated behind `ImportError` guards in `models/gbm_model.py` and `models/neural_model.py`. Core pipeline runs on `pandas`, `numpy`, `scipy`, `sklearn`, and `pydantic` only.
