# Disaster Recovery and Incident Response

**NYSE ATS Framework | v0.4 | April 2026**

> **Status:** Runbooks defined for 10 failure scenarios. Incident response procedures will be tested during paper trading (Phase 5).

---

## 1. Severity Classification

| Level | Description | Response Time | Notification | Examples |
|---|---|---|---|---|
| **SEV-1** | Trading halt required; potential capital loss | Immediate | Telegram VETO + email | F1/F2 VETO trigger, broker disconnect, kill switch |
| **SEV-2** | Degraded operation; positions safe but pipeline impaired | < 1 hour | Telegram WARNING | Data feed partial failure, model singular matrix |
| **SEV-3** | Non-urgent issue; no immediate trading impact | < 24 hours | Dashboard alert | Dashboard down, alert delivery delay, config warning |

---

## 2. Scenario Runbooks

### Scenario 1: VETO Trigger Fired (F1/F2/F3)

**Severity:** SEV-1

| Phase | Actions |
|---|---|
| **Detection** | `drift.py: assess_drift()` or falsification check detects threshold breach. Telegram VETO alert sent automatically. Dashboard shows red indicator. |
| **Assessment** | Identify which trigger fired: F1 (Signal Death: rolling_ic_60d < 0.01 for 2 months), F2 (Factor Death: >3 sign flips in 2 months), F3 (Excessive Drawdown: max_dd < -25%). Review `DriftReport` and `FalsificationCheckResult` in `live.duckdb`. |
| **Response** | 1. System automatically sets `kill_switch: true` and switches to paper mode. 2. All pending orders are cancelled via NautilusTrader. 3. No new orders submitted. 4. Current positions held (no forced liquidation unless F3 at extreme levels). |
| **Recovery** | 1. Investigate root cause using drift report and IC history. 2. If F1/F2: run full drift assessment to identify drifting factors. 3. Consider retraining with latest data (see `MLOPS_LIFECYCLE.md` Section 5). 4. If retrained model passes all gates, promote and resume. 5. Resume only after human approval and `kill_switch: false`. |
| **Post-Mortem** | Document in experiment log as type `incident`. Record timeline, root cause, IC values at trigger time, recovery actions, and prevention measures. |

### Scenario 2: Broker Connection Lost

**Severity:** SEV-1

| Phase | Actions |
|---|---|
| **Detection** | `nautilus_bridge.py` raises connection error. Retry mechanism activates (3 attempts with exponential backoff). Telegram alert sent after first failed retry. |
| **Assessment** | Check broker API status page. Verify network connectivity. Check if issue is credential expiration, rate limiting, or broker outage. |
| **Response** | 1. If during TWAP execution: partial fills are recorded in `live.duckdb`. 2. Remaining unfilled orders are held in pending state. 3. Do NOT resubmit orders until connection is verified stable. 4. If market close is approaching and orders are unfilled, accept partial portfolio. |
| **Recovery** | 1. Once connection restored, reconcile NautilusTrader positions vs `live.duckdb`. 2. Determine if remaining orders should be executed (check if prices have moved significantly). 3. If >24 hours elapsed, regenerate TradePlan with fresh data before executing. 4. Log position reconciliation results. |
| **Post-Mortem** | Document broker uptime, duration of outage, partial fill impact, slippage incurred from delayed execution. |

### Scenario 3: Data Feed Outage (FinMind)

**Severity:** SEV-2

| Phase | Actions |
|---|---|
| **Detection** | `finmind_adapter.py` returns error or empty data after 3 retry attempts. F8 (Data Staleness) WARNING may fire if staleness exceeds 10 days. |
| **Assessment** | Check FinMind API status. Verify API token is valid (`FINMIND_API_TOKEN` env var). Check if issue affects all symbols or specific ones. |
| **Response** | 1. If >20% of universe has missing OHLCV: HOLD all current positions, skip rebalance. 2. If <20% missing: proceed with available data; missing symbols excluded from universe. 3. Price/volume factors (ivol, momentum, 52w_high, ewmac) will be NaN for affected stocks. 4. Imputation handles partial NaN if <30% per factor; factor dropped if >=30%. |
| **Recovery** | 1. Once feed restored, backfill missing data. 2. Re-run feature computation for affected dates. 3. Verify PiT enforcement is maintained (no accidental future data). 4. Resume normal rebalance cycle. |
| **Post-Mortem** | Document data gap duration, number of affected symbols, impact on portfolio (was rebalance skipped?). |

### Scenario 4: Data Feed Outage (EDGAR)

**Severity:** SEV-2

| Phase | Actions |
|---|---|
| **Detection** | `edgar_adapter.py` returns XBRL parse failure or SEC rate limit exceeded. Fundamental factors go stale. |
| **Assessment** | Check SEC EDGAR system status. Verify `EDGAR_USER_AGENT` env var is set correctly (SEC requires contact info). Check if quarterly filing deadline has passed (data may not yet be available). |
| **Response** | 1. Fundamental factors (piotroski, accruals, profitability) become NaN via `pit.py` max_age enforcement. 2. If fundamental factors represent <30% of total features, imputation handles it. 3. If >50% of all features are NaN, skip rebalance entirely and hold positions. 4. F8 WARNING fires for stale features. |
| **Recovery** | 1. EDGAR filings have a T+45 publication lag -- data may simply not be available yet. 2. Once filings appear, ingest and recompute fundamentals. 3. Verify that no filings were missed (compare against SEC filing index). |
| **Post-Mortem** | Document which filings were missed, whether the pipeline correctly fell back to imputation, and whether any positions were affected. |

### Scenario 5: Model Singular Matrix

**Severity:** SEV-2

| Phase | Actions |
|---|---|
| **Detection** | `models/ridge_model.py` raises `numpy.linalg.LinAlgError` during `fit()`. Diagnostics capture the error with ERROR level. |
| **Assessment** | Check feature matrix for: (a) constant columns (zero variance), (b) perfectly correlated columns, (c) insufficient observations. Review normalization output for degenerate rank-percentile results. |
| **Response** | 1. Fall back to previous model weights (stored in `research.duckdb`). 2. Generate TradePlan using previous model. 3. Log fallback event in experiment log. 4. Dashboard shows WARNING indicator for model status. |
| **Recovery** | 1. Identify degenerate feature(s) causing singularity. 2. Check if imputation produced constant values (possible if >30% NaN in multiple factors simultaneously). 3. Fix root cause (drop degenerate factor or improve imputation). 4. Re-run model fit and validate. |
| **Post-Mortem** | Document which features caused singularity, the fallback model used, and any impact on portfolio. |

### Scenario 6: Execution Failure

**Severity:** SEV-2

| Phase | Actions |
|---|---|
| **Detection** | NautilusTrader reports: TWAP timeout (did not complete before market close), partial fills, or order rejection from broker. |
| **Assessment** | Check order rejection reason (insufficient buying power, halted stock, invalid quantity). Check TWAP progress (% filled vs target). Check if corporate action occurred between signal and execution. |
| **Response** | 1. **TWAP timeout:** Accept partial portfolio. Record actual fills in `live.duckdb`. Remaining unfilled orders are cancelled (not carried to next day). 2. **Partial fills:** Record actual shares filled. Portfolio operates with partial positions until next rebalance. 3. **Order rejection:** Cancel affected order. Investigate rejection reason. If corporate action, regenerate TradePlan via `nautilus_bridge.pre_submit`. |
| **Recovery** | 1. Next weekly rebalance will naturally correct positions (sell buffer provides tolerance). 2. If large positions were unfilled, consider mid-week manual execution (requires human approval). 3. Update execution slippage records in `live.duckdb`. |
| **Post-Mortem** | Document fill rate, slippage vs estimate, TWAP completion percentage, and any rejected orders with reasons. |

### Scenario 7: Database Corruption

**Severity:** SEV-2

| Phase | Actions |
|---|---|
| **Detection** | DuckDB raises I/O error or integrity check failure when reading `research.duckdb` or `live.duckdb`. Dashboard shows "DuckDB locked" retries exceeding threshold. |
| **Assessment** | Check file system for disk space issues. Check if concurrent writes caused corruption (DuckDB is single-writer). Check if OS crash left partial write. |
| **Response** | 1. Do NOT attempt to repair corrupted database file. 2. Activate kill switch if `live.duckdb` is affected. 3. Positions are safe -- NautilusTrader is the position source of truth, not DuckDB. 4. Research data loss is bounded by last backup. |
| **Recovery** | 1. Restore from most recent backup (daily backup schedule). 2. Replay any missing experiment logs from git history (config snapshots are in git). 3. For `live.duckdb`: reconcile positions from NautilusTrader state. 4. Validate restored database with integrity check before resuming. |
| **Post-Mortem** | Document corruption cause, data loss window, backup age, and whether backup frequency is sufficient. |

### Scenario 8: Configuration Error

**Severity:** SEV-3

| Phase | Actions |
|---|---|
| **Detection** | `config_schema.py` (Pydantic validation) raises `ValidationError` at system startup. Fail-fast: system does not proceed with invalid config. |
| **Assessment** | Read Pydantic error message to identify which field in which YAML file is invalid. Common causes: typo in field name, wrong type (string vs number), missing required field. |
| **Response** | 1. System does not start -- no trading impact if detected at startup. 2. If detected mid-operation (config reload), current positions are unaffected. 3. Fix the invalid YAML field. 4. Re-run Pydantic validation to confirm fix. |
| **Recovery** | 1. Compare current config against git history to identify what changed. 2. Restore previous config version if fix is unclear. 3. Run test suite to verify config fix does not affect pipeline behavior. |
| **Post-Mortem** | Document which config field was invalid, how it became invalid (manual edit? merge error?), and whether config validation should be added to CI. |

### Scenario 9: Corporate Action Missed

**Severity:** SEV-2

| Phase | Actions |
|---|---|
| **Detection** | `nautilus_bridge.pre_submit` detects that a stock in the TradePlan has had a split, reverse split, or special dividend since the signal was generated. Alternatively, `data_quality.py` detects abnormal price discontinuity. |
| **Assessment** | Identify which stocks are affected and what type of corporate action occurred. Check if `corporate_actions.py` adjustment was applied to historical data. |
| **Response** | 1. Cancel affected orders in TradePlan. 2. Regenerate TradePlan with corporate-action-adjusted prices. 3. Recompute features for affected stocks (split-adjusted OHLCV). 4. If corporate action affects >5 stocks in portfolio, consider skipping this rebalance. |
| **Recovery** | 1. Apply corporate action adjustments to historical OHLCV in `research.duckdb`. 2. Verify that `pit.py` timestamps are correct for adjusted data. 3. Resubmit corrected TradePlan orders. 4. Update position records in `live.duckdb`. |
| **Post-Mortem** | Document which corporate action was missed, whether the event-sourced log in `corporate_actions.py` captured it, and whether the data feed should include corporate action alerts. |

### Scenario 10: Kill Switch Activated

**Severity:** SEV-1

| Phase | Actions |
|---|---|
| **Detection** | `strategy_params.yaml: kill_switch` is set to `true`, either manually by operator or automatically by F1/F2 VETO trigger. All order submission is blocked. |
| **Assessment** | Determine if kill switch was manual (operator decision) or automatic (VETO trigger). If automatic, review the triggering falsification check. |
| **Response** | 1. All pending orders are cancelled. 2. No new orders are generated or submitted. 3. Current positions are held (no forced liquidation). 4. System continues to monitor positions and generate signals for information only. 5. Telegram notification sent confirming kill switch state. |
| **Recovery** | 1. Investigate root cause (if VETO-triggered). 2. If manual: operator documents rationale in experiment log. 3. Run system integrity checks (data feeds, model state, position reconciliation). 4. Set `kill_switch: false` only after human approval. 5. First post-resume rebalance should be monitored with elevated alerting. |
| **Post-Mortem** | Document duration of halt, any market moves during halt, portfolio impact of missed rebalances, and whether the halt was justified. |

---

## 3. Communication Protocol

### Notification Channels

| Channel | Used For | Latency |
|---|---|---|
| **Telegram** (primary) | All SEV-1 and SEV-2 alerts, VETO triggers, daily summaries | < 1 minute |
| **Streamlit Dashboard** | Real-time position and risk monitoring, factor health, falsification status | < 5 seconds (refresh) |
| **Email** (planned, GAP-4) | Backup for critical alerts if Telegram fails | < 5 minutes |

### Alert Format

```
[SEV-1] VETO TRIGGER: F1 Signal Death
Time: 2026-04-16 15:30:00 UTC
Metric: rolling_ic_60d = 0.008 (threshold: 0.01)
Duration: 2+ months below threshold
Action: Kill switch activated. All orders cancelled.
Required: Manual review before resuming.
```

### Escalation Chain

| Time Elapsed | Action |
|---|---|
| 0 min | Automated Telegram alert to operator |
| 15 min | Dashboard shows persistent red indicator |
| 1 hour | If SEV-1 unacknowledged, send repeat alert |
| 4 hours | If SEV-1 unacknowledged, system remains halted (no auto-resume) |

### Status Updates During Incidents

| Severity | Update Frequency |
|---|---|
| SEV-1 | Every 30 minutes until resolved |
| SEV-2 | Every 2 hours until resolved |
| SEV-3 | Daily until resolved |

---

## 4. Recovery Procedures

### 4.1 Restart from Clean State

```
1. Verify kill_switch is true (no orders during restart)
2. Validate all 6 config files via config_schema.py
3. Check research.duckdb and live.duckdb integrity
4. Reconcile positions: NautilusTrader state vs live.duckdb
   (NautilusTrader is SOURCE OF TRUTH for positions)
5. Run drift assessment on latest IC history
6. Check all 8 falsification triggers
7. If all checks pass: set kill_switch false, resume pipeline
8. If any check fails: investigate before resuming
```

### 4.2 Position Reconciliation After Outage

```
1. Export current positions from NautilusTrader
   (symbol, shares, avg_cost, current_value)
2. Compare against last known state in live.duckdb
3. For each discrepancy:
   a. If NautilusTrader has position, live.duckdb does not:
      --> Corporate action or manual trade? Investigate.
   b. If live.duckdb has position, NautilusTrader does not:
      --> Stop-loss triggered? Broker liquidation? Investigate.
   c. If share counts differ:
      --> Check for partial fills, splits, or rounding.
4. Update live.duckdb to match NautilusTrader state
5. Log reconciliation results as experiment type "reconciliation"
```

### 4.3 System Integrity Validation Before Resuming

| Check | Command/Module | Pass Criteria |
|---|---|---|
| Config validation | `config_schema.py` Pydantic models | All 6 YAML files parse without error |
| Database integrity | DuckDB `PRAGMA integrity_check` | No corruption detected |
| Data freshness | `pit.py` staleness check | No feature >10 days stale (F8) |
| Model state | Load model from `research.duckdb` | Model loads and produces predictions |
| Drift assessment | `drift.py: assess_drift()` | No "high" urgency drift |
| Falsification check | All F1-F8 triggers | No VETO trigger active |
| Position reconciliation | NautilusTrader vs `live.duckdb` | Positions match |
| Test suite | `pytest tests/` | 934+ tests pass, 0 failures |

---

## 5. Post-Mortem Template

```
INCIDENT POST-MORTEM
====================

Incident ID:    INC-2026-04-001
Severity:       SEV-1
Date:           2026-04-16
Duration:       2 hours 15 minutes
Operator:       [name]

TIMELINE
--------
15:30 UTC  - F1 Signal Death trigger fired (rolling_ic_60d = 0.008)
15:30 UTC  - Telegram VETO alert sent
15:31 UTC  - Kill switch activated automatically
15:32 UTC  - Pending TWAP orders cancelled (3 of 5 filled)
15:45 UTC  - Operator acknowledged alert
16:00 UTC  - Drift report reviewed: 4/8 factors showing IC decay
16:30 UTC  - Root cause identified: FinMind data gap caused stale features
17:00 UTC  - Data backfilled, features recomputed
17:30 UTC  - Full drift assessment shows urgency "low" with fresh data
17:45 UTC  - Kill switch deactivated, system resumed in paper mode

ROOT CAUSE
----------
[Description of underlying cause]

IMPACT
------
- Positions affected: [number]
- Estimated P&L impact: [amount]
- Rebalances missed: [number]
- Slippage from delayed execution: [bps]

REMEDIATION
-----------
[Actions taken to resolve the immediate issue]

PREVENTION
----------
[Changes to prevent recurrence]
- [ ] Action item 1
- [ ] Action item 2
- [ ] Action item 3

LESSONS LEARNED
---------------
[Key takeaways for future reference]
```
