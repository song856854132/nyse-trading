# Risk Limits (Consolidated)

**Version 0.1 | 2026-04-18**
**Authority:** This document is the single source of truth for risk limits. Config files
(`config/strategy_params.yaml`, `config/falsification_triggers.yaml`) are the enforcement
layer; this document is the business layer.
**Audience:** Risk review, LP due diligence, regulatory exam, internal training.

---

## How to read this document

Each row has four fields:

- **Value** — the numeric threshold
- **Enforcement** — which file + function checks it at runtime
- **Override** — who can change it (and whether a change is a material event)
- **Last change** — git commit hash + date of the last change to this value

Limits are grouped by layer: position-level, portfolio-level, trigger-level,
execution-level, and operational.

**Material-change protocol:** Any limit change requires (a) git commit with a description,
(b) research-log entry via `scripts/append_research_log.py` with event type `limit_change`,
(c) verification pass via `scripts/verify_research_log.py`. Post-live, LP notification
within 30 days.

---

## 1. Position-level limits

| # | Name | Value | Enforcement | Override | Last change |
|---|------|:----:|---|---|---|
| 1.1 | Max single-stock weight (soft) | 10% of portfolio NAV | `src/nyse_core/risk.py::apply_position_caps` → property test `tests/property/test_position_caps_invariant.py` | Operator; material | 2026-04-15 (plan lock) |
| 1.2 | Max single-stock weight (hard / F4) | 15% of portfolio NAV | `config/falsification_triggers.yaml F4` → WARNING halt protocol | Frozen pre-live | 2026-04-15 (frozen) |
| 1.3 | Min single-stock weight | ~5% (= 1/top_n = 1/20) | Structural from `allocator.weighting: equal` | Would require changing the strategy class | N/A |
| 1.4 | Earnings-event position cap | 5% if reporting within 2 trading days | `src/nyse_core/risk.py::apply_earnings_cap` via `config.risk.earnings_event_cap` | Operator; material | 2026-04-15 |
| 1.5 | Min stock price (universe filter) | $5.00 | `config.universe.min_price` | Operator | 2026-04-15 |
| 1.6 | Min 20-day ADV (universe filter) | $500,000 | `config.universe.min_adv_20d` | Operator | 2026-04-15 |

---

## 2. Portfolio-level limits

| # | Name | Value | Enforcement | Override | Last change |
|---|------|:----:|---|---|---|
| 2.1 | Max GICS sector weight | 30% of portfolio NAV | `src/nyse_core/risk.py::apply_sector_caps` → property test `tests/property/test_sector_caps_invariant.py` | Operator; material | 2026-04-15 |
| 2.2 | Ex-ante beta range (vs SPY) | [0.5, 1.5] | `config.risk.beta_cap_low` / `beta_cap_high`; risk.py rejects TradePlan outside range and re-balances | Operator; material | 2026-04-15 |
| 2.3 | Bull-regime gross exposure | 100% | `config.regime.bull_exposure` | Operator; material | 2026-04-15 |
| 2.4 | Bear-regime gross exposure | 40% | `config.regime.bear_exposure` | Operator; material | 2026-04-15 |
| 2.5 | Vol target (annualized) | 15% | `config.volatility_target.annual_pct` — scales gross if realized vol deviates persistently | Operator; material | 2026-04-15 |
| 2.6 | Daily loss limit | -3% portfolio NAV intraday | `config.risk.daily_loss_limit` + `nautilus_bridge.pre_submit` check | Operator; material | 2026-04-15 |
| 2.7 | Top-N portfolio size | 20 names | `config.allocator.top_n` | Operator; material | 2026-04-15 |
| 2.8 | Sell-buffer hysteresis | 1.5× | `config.allocator.sell_buffer` — hold until rank drops below 1.5× top-N cut-off | Operator; material | 2026-04-15 (TWSE Phase 63) |
| 2.9 | Position inertia threshold | 0.5pp absolute (≈ 10% relative for 5% target) | `config.risk.position_inertia_threshold` | Operator; material | 2026-04-15 |

---

## 3. Falsification triggers (F1-F8) — FROZEN

`config/falsification_triggers.yaml` contains these verbatim. Frozen date: **2026-04-15**.
No retroactive threshold adjustment permitted. Adding new triggers is allowed; weakening
existing thresholds is not. The hash of the triggers file is checked at runtime (TODO-1).

| # | Name | Metric | Threshold | Severity | Response |
|---|------|--------|:----:|:----:|---|
| F1 | signal_death | rolling 60-day IC | < 0.01 for 2+ months | VETO | Halt live; switch to paper; investigate; Telegram alert |
| F2 | factor_death | core factor sign flips | ≥ 3 in 2 months | VETO | Halt live; root-cause one factor at a time |
| F3 | excessive_drawdown | max drawdown from peak | < -25% | VETO | Halt live; review regime overlay; Telegram alert |
| F4 | concentration | max single-stock weight | > 15% | WARNING | Reduce exposure to 60%; position rebalance within 1 week |
| F5 | turnover_spike | monthly turnover | > 200% | WARNING | Reduce exposure to 60%; review allocator + sell-buffer |
| F6 | cost_drag | annualized cost drag | > 5% of gross | WARNING | Reduce exposure to 60%; recalibrate `cost_model.py`; consider VWAP |
| F7 | regime_anomaly | benchmark split-adjusted | false | WARNING | Reduce exposure to 60%; check data-vendor corporate-action stream |
| F8 | data_staleness | max feature age | > 10 days | WARNING | Reduce exposure to 60%; investigate data pipeline |

**VETO vs WARNING:**
- **VETO fires** → orders halted before next rebalance; written postmortem within 72 hours;
  re-entry requires operator + (if live) LP notification
- **WARNING fires** → exposure reduced to 60% gross; operator review within 1 week;
  re-normalization requires documenting root cause in research log

---

## 4. Execution-level limits

| # | Name | Value | Enforcement | Override | Last change |
|---|------|:----:|---|---|---|
| 4.1 | Max order size vs 20-day ADV | 5% | `config.execution.max_participation_rate` + `nautilus_bridge.pre_submit` | Operator; material | 2026-04-15 |
| 4.2 | TWAP duration | 30 minutes | `config.execution.twap_duration_minutes` | Operator; material | 2026-04-15 |
| 4.3 | TWAP start | Market open + 0 (09:30:00 ET) | `nautilus_bridge.submit` configures algo | Operator | 2026-04-15 |
| 4.4 | TWAP slippage budget | 10 bps target; 20 bps soft cap | Monitored post-fill; persistent > 20bps triggers F6 check | Operator | 2026-04-15 |
| 4.5 | Settlement | T+2 standard US equities | Exchange-enforced; not a strategy parameter | Regulator | N/A |
| 4.6 | Order rejection retry | Max 1 retry per order | `nautilus_bridge.handle_rejection` | Operator | 2026-04-15 |

---

## 5. Operational limits

| # | Name | Value | Enforcement | Override | Last change |
|---|------|:----:|---|---|---|
| 5.1 | Kill switch | Manual flag `kill_switch: true` in `config/strategy_params.yaml` | Checked before every order submission by `nautilus_bridge.submit` | Operator; any time; immediate | 2026-04-15 |
| 5.2 | Reconciliation break threshold | 0.5% position deviation | `nautilus_bridge.reconcile` raises; >5% halts all trading | Operator; material | 2026-04-15 |
| 5.3 | Max feature-NaN fraction per date | 50% (features) | `src/nyse_core/impute.py` + pipeline gate | Operator; material | 2026-04-15 |
| 5.4 | Per-factor NaN threshold | 30% (features dropped for that date) | `src/nyse_core/impute.py` | Operator; material | 2026-04-15 |
| 5.5 | Data freshness (from PiT) | 10 days max age (else NaN) | `src/nyse_core/pit.py::enforce_lags` | Operator; material | 2026-04-15 |
| 5.6 | Rate limiter (vendor API) | Per-vendor in `config/data_sources.yaml` | `src/nyse_ats/data/rate_limiter.py` | Operator | 2026-04-15 |

---

## 6. Limits NOT yet codified (gaps)

Transparency about what's missing:

- **Net exposure limit.** Strategy is long-only → net = gross. When long/short variant
  ships, a net exposure bound (e.g. [0%, 100%]) must be added.
- **Currency exposure limit.** USD-only at present. If international tickers ever enter
  the universe, a per-currency limit is required.
- **Factor crowding score.** No quantitative limit on "how much of the portfolio is
  driven by factors held by popular ETFs." Tracked qualitatively in quarterly letters
  pending a metric.
- **Correlation-to-other-strategies cap.** Single-strategy operation; no constraint.
  Required once `strategy_registry.py` [EXP-7] ships and multiple strategies run.
- **Consecutive loss limit.** No explicit halt after N losing weeks. Falsification
  triggers catch the statistical equivalent (F1 on rolling IC); a consecutive-week
  rule would be a blunter, less informative control.
- **Leverage limit.** Strategy is unlevered (gross ≤ 100% NAV). If a leveraged variant
  ships, a leverage cap (e.g. 1.5×) must be added.

Each missing limit is a TODO candidate when its triggering feature ships.

---

## 7. How limits are monitored

| Monitoring layer | Cadence | Owner |
|------------------|:----:|---|
| Pre-trade (TradePlan construction) | Every weekly rebalance | `nyse_core/risk.py` |
| Pre-submit (broker submission) | Every order | `nyse_ats/execution/nautilus_bridge.py::pre_submit` |
| Post-fill (reconciliation) | Within 1 hour of fill | `nyse_ats/execution/nautilus_bridge.py::reconcile` |
| Intraday (daily loss, position limits) | Every fill + EOD | `nyse_ats/monitoring/falsification.py` |
| Rolling (F1-F8 triggers) | Daily | `nyse_ats/monitoring/falsification.py` |
| Dashboard | Real-time | `nyse_ats/monitoring/dashboard.py` (Streamlit) |
| Quarterly | Per quarter | Operator via quarterly letter §7 |

---

## 8. Material change history

Any change to any limit in this document must be logged here with git commit + date +
rationale + research-log event hash.

| Date | Limit | From | To | Rationale | Research-log hash |
|------|-------|------|------|-----------|------------------|
| 2026-04-15 | (initial) | N/A | All limits set | Plan lock + trigger freeze | `c4d7a33aaa6b2f5b...` (forecast_factor_screen pre-run) |
| 2026-04-18 | — | — | — | (document created; no limits changed) | Deferred; appended with gap-closure commit |

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Initial consolidation from configs + plan + trigger file. |

**Document owner:** Operator.
**Review cadence:** Quarterly, or before any material limit change.
**Related documents:** `config/strategy_params.yaml`, `config/falsification_triggers.yaml`, `docs/STRESS_TEST_FRAMEWORK.md`, `docs/DDQ_AIMA_2025.md` §4, `docs/ODD_PACKAGE.md` §4.
