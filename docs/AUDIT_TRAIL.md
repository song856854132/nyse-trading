# Audit Trail and Experiment Logging

**NYSE ATS Framework | v0.4 | April 2026**

> **Status:** Schema defined, storage in DuckDB (`research.duckdb` for research, `live.duckdb` for production). Append-only enforcement planned before paper trading.

---

## 1. Experiment Log Schema

Every backtest, factor evaluation, or parameter sweep is recorded as a structured experiment entry. The canonical schema:

```yaml
experiment_id: "EXP-2026-04-001"
timestamp: "2026-04-16T10:30:00Z"
researcher: "system"
type: "walk_forward_backtest"  # see type enum below
parameters:
  model: "ridge"
  alpha: 1.0
  target_horizon: 5
  top_n: 20
  sell_buffer: 1.5
  factors:
    - "ivol_20d"
    - "piotroski_f_score"
    - "momentum_2_12"
    - "52w_high_proximity"
    - "earnings_surprise"
    - "short_ratio"
    - "accruals"
    - "profitability"
  normalization: "rank_percentile"
  cv_folds: 4
  purge_days: 5
  embargo_days: 5
  research_period: "2016-01-01 to 2023-12-31"
results:
  oos_sharpe: 0.85
  oos_cagr: 0.21
  max_drawdown: -0.18
  annual_turnover: 0.42
  cost_drag_pct: 1.8
  ic_mean: 0.034
  ic_ir: 0.62
  permutation_p: 0.018
  bootstrap_ci: [0.31, 1.39]
  romano_wolf_p: {"ivol_20d": 0.012, "piotroski": 0.034}
  per_fold_sharpe: [0.72, 0.91, 0.88, 0.79]
  overfit_ratio: 1.08
status: "completed"  # completed | failed | aborted
gate_verdicts:
  G0: "PASS"
  G1: "PASS"
  G2: "PASS"
  G3: "PASS"
  G4: "PASS"
  G5: "PASS"
config_hash: "sha256:a1b2c3d4..."
diagnostics_count: {DEBUG: 142, INFO: 38, WARNING: 2, ERROR: 0}
notes: "First full run with 8 factors post-dedup"
```

### Experiment Types

| Type | Description | Trigger |
|---|---|---|
| `walk_forward_backtest` | Full purged walk-forward CV run | Manual or scheduled |
| `factor_screening` | Single-factor G0-G5 gate evaluation | Factor addition attempt |
| `parameter_sweep` | Walk-forward optimizer run (`optimizer.py`) | Manual |
| `model_comparison` | Ridge vs GBM vs Neural via `strategy_registry.py` | Manual |
| `synthetic_calibration` | 50-trial SNR calibration (`synthetic_calibration.py`) | Pre-paper-trading gate |
| `pca_deduplication` | Factor correlation + PCA decomposition | Factor set change |
| `drift_assessment` | 3-layer drift check (`drift.py`) | Scheduled (weekly) |
| `live_rebalance` | Production rebalance cycle | Weekly (Fri signal, Mon exec) |

### Experiment ID Format

```
EXP-{YYYY}-{MM}-{NNN}

  YYYY  = year
  MM    = month (zero-padded)
  NNN   = sequential counter within month (zero-padded, 3 digits)

Examples:
  EXP-2026-04-001   First experiment in April 2026
  EXP-2026-04-042   42nd experiment in April 2026
```

---

## 2. Model Version Tracking

### Version Numbering

```
v{MAJOR}.{MINOR}.{PATCH}-{STAGE}

  MAJOR  = architecture change (e.g., switch from Ridge to ensemble)
  MINOR  = factor set change or significant parameter update
  PATCH  = bug fix or config correction
  STAGE  = research | paper | shadow | live

Examples:
  v0.4.0-research    Current version, 8-factor Ridge
  v0.4.1-research    After adding a 9th factor
  v0.5.0-paper       Promoted to paper trading after all gates pass
  v1.0.0-live        First live deployment
```

### Promotion Criteria

A model version advances to the next stage only when ALL of the following hold:

| From | To | Required Gates |
|---|---|---|
| Research | Paper | All G0-G5 pass, permutation p<0.05, bootstrap CI lower >0, synthetic calibration passed |
| Paper | Shadow | 90 days paper with no VETO trigger, IC in target range, cost drag <5% |
| Shadow | Live (min) | 30 days shadow, fills match real within 10 bps, all 7 graduation criteria pass |
| Live (min) | Scale | 90 days min-live, realized Sharpe >0, fill rate >95%, slippage <15 bps |

### Rollback Procedure

1. Set `kill_switch: true` in `strategy_params.yaml` to halt all new orders.
2. Record rollback decision in experiment log with type `model_rollback`.
3. Restore previous model version from `research.duckdb` model archive.
4. Run validation suite on restored model (walk-forward CV, permutation test).
5. If validation passes, update config to reference previous model version.
6. Set `kill_switch: false` after human approval.
7. Monitor first 5 rebalance cycles with elevated alerting threshold.

### Version Comparison Format

```
+--------------------------------------------------+
| Model Comparison: v0.4.0 vs v0.4.1               |
+--------------------------------------------------+
| Metric             | v0.4.0  | v0.4.1  | Delta  |
|--------------------|---------|---------|--------|
| OOS Sharpe         | 0.85    | 0.91    | +0.06  |
| OOS CAGR           | 21.0%   | 22.4%   | +1.4%  |
| Max Drawdown       | -18.0%  | -16.5%  | +1.5%  |
| Annual Turnover    | 42%     | 39%     | -3%    |
| Cost Drag          | 1.8%    | 1.6%    | -0.2%  |
| Overfit Ratio      | 1.08    | 1.12    | +0.04  |
| Factors            | 8       | 9       | +1     |
| Permutation p      | 0.018   | 0.014   | -0.004 |
+--------------------------------------------------+
| Verdict: v0.4.1 ACCEPTED (G5 marginal > 0)       |
+--------------------------------------------------+
```

---

## 3. Parameter Change Log

Every parameter change is documented with the following format:

```yaml
change_id: "CHG-2026-04-003"
timestamp: "2026-04-16T14:00:00Z"
parameter: "strategy_params.yaml -> allocator.sell_buffer"
old_value: 1.3
new_value: 1.5
rationale: "TWSE Phase 63 evidence: sell_buffer=1.5 saved ~1644 bps and added +0.040 Sharpe"
phase_reference: "TWSE Lesson_Learn Phase 63"
impact_assessment:
  before:
    oos_sharpe: 0.81
    annual_turnover: 0.52
    cost_drag_pct: 2.1
  after:
    oos_sharpe: 0.85
    annual_turnover: 0.42
    cost_drag_pct: 1.8
approval: "researcher"
experiment_id: "EXP-2026-04-001"
config_hash_before: "sha256:aaaa..."
config_hash_after: "sha256:bbbb..."
```

### Change Categories

| Category | Examples | Approval Required |
|---|---|---|
| **Threshold** | Gate thresholds, falsification trigger levels | Requires re-validation; frozen thresholds CANNOT be changed |
| **Strategy** | top_n, sell_buffer, regime parameters | Walk-forward re-run required |
| **Infrastructure** | Rate limits, retry counts, TWAP duration | No re-validation needed |
| **Model** | Ridge alpha, GBM hyperparameters | Full gate re-evaluation (G0-G5) |
| **Data** | New data source, publication lag adjustment | Impact assessment + re-run |

---

## 4. Immutability Rules

### Rule 1: Experiment Logs Are Append-Only

Experiment log entries in `research.duckdb` and `live.duckdb` are insert-only. No UPDATE or DELETE operations are permitted on experiment tables. Corrections are recorded as new entries referencing the original `experiment_id` with a `correction_of` field.

### Rule 2: Falsification Triggers Are Frozen

The file `config/falsification_triggers.yaml` carries a `frozen_date: "2026-04-15"`. After this date:
- No threshold values may be changed.
- No triggers may be removed.
- New triggers may be added (append-only).
- The file's SHA-256 hash is verified at system startup (implementation: TODO-1 in `TODOS.md`).

### Rule 3: No Retroactive Threshold Adjustment

If a falsification trigger fires, the response is operational (halt trading, investigate), not to weaken the threshold. This rule prevents the "moving goalposts" anti-pattern where thresholds are relaxed to avoid halts.

### Rule 4: Config Hash Verification

Every experiment log entry records the SHA-256 hash of all 6 configuration files at the time of execution:

```
config/market_params.yaml
config/strategy_params.yaml
config/data_sources.yaml
config/gates.yaml
config/falsification_triggers.yaml
config/deployment_ladder.yaml
```

If the computed hash at runtime differs from the recorded hash, the experiment is flagged with a `CONFIG_DRIFT` warning in Diagnostics.

### Rule 5: Research Period Is Locked

The research period (2016-2023) is used for all model development and tuning. The holdout period (2024-2025) is for one-shot evaluation only. No iteration is permitted after holdout results are observed. This boundary is enforced by convention and documented in every experiment log entry.

---

## 5. Storage Architecture

```
research.duckdb                      live.duckdb
+----------------------------+       +----------------------------+
| experiments (append-only)  |       | trade_plans (append-only)  |
| gate_verdicts              |       | execution_records          |
| model_parameters           |       | falsification_events       |
| backtest_results           |       | drift_reports              |
| factor_screening_results   |       | position_snapshots         |
| parameter_change_log       |       | rebalance_summaries        |
| config_snapshots           |       | alert_history              |
| diagnostics_archive        |       | diagnostics_archive        |
+----------------------------+       +----------------------------+
         |                                      |
         v                                      v
    Git repository                    NautilusTrader position
    (config YAML files,               state (SOURCE OF TRUTH
     source code versions)             for live positions)
```

### Retention Policy

| Data Category | Retention | Rationale |
|---|---|---|
| Experiment logs | Indefinite | Research provenance; SR 11-7 requires model lifecycle records |
| Trade execution records | 6 years minimum | FINRA 3110 / SEC 17a-4 |
| Configuration snapshots | Life of model + 3 years | SR 11-7 |
| Diagnostics (DEBUG level) | 90 days rolling | Space management; INFO+ retained longer |
| Diagnostics (INFO/WARNING/ERROR) | 1 year | Operational troubleshooting |
| Falsification trigger events | 6 years minimum | Regulatory evidence |
