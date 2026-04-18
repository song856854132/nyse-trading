# Capacity and Liquidity Analysis

**NYSE Cross-Sectional Alpha | v0.1 | April 2026**

> **Purpose.** Answer the first question any institutional allocator asks:
> how big can this strategy get, and how fast can it unwind without
> eating its own alpha? This document specifies the methodology and the
> trigger thresholds. Point estimates are placeholder-aware: real numbers
> populate after the first real-data walk-forward run (TODO-11).

---

## 1. Summary

| Dimension | Current assumption | Hard limit | Soft trigger |
|---|:---:|:---:|:---:|
| Per-stock max participation rate | 5% of 20-day ADV | 10% (circuit-breaker) | 3% (preferred operating point) |
| Single-stock portfolio weight | <= 10% | 10% (`risk.apply_position_caps`) | 7% (concentration warning) |
| GICS sector weight | <= 30% | 30% (`risk.apply_sector_caps`) | 25% (sector warning) |
| Weekly turnover | Target < 1% of AUM in notional | -- | 200% monthly (F5 falsification trigger) |
| Unwind horizon, 1 trading day | See Section 5 | -- | -- |
| Unwind horizon, 5 trading days | See Section 5 | -- | -- |

### Operating point

The strategy is designed to run at **$1M -- $20M AUM** during the paper and
minimum-live stages. Capacity beyond $20M requires re-calibration of the
cost model and is not sanctioned by this document.

---

## 2. Capacity Methodology

### 2.1 Per-stock capacity from ADV

The binding constraint is **participation rate** -- the fraction of a
stock's 20-day average daily volume (ADV) the strategy can trade before
price impact exceeds the cost budget. The framework enforces a ceiling of
5% ADV per stock (`config/strategy_params.yaml: execution.max_participation_rate = 0.05`).

Per-stock capacity at participation rate `p`:

```
capacity_per_stock($) = p * ADV_20d($) * target_weight_time_budget
```

Where `target_weight_time_budget` is 1.0 for a single-day entry or `k` for
spreading over `k` days. The current design uses a 30-minute TWAP on the
execution day (`twap_duration_minutes: 30`), which sits inside one trading
session; `k = 1` for capacity math.

### 2.2 Portfolio-level capacity

With `top_n = 20` equal-weighted holdings at 5% each, AUM capacity is
determined by the smallest stock in the portfolio:

```
AUM_capacity($) = min_i [ capacity_per_stock_i / 0.05 ]
                = min_i [ p * ADV_20d_i ]
                = 0.05 * min(ADV_20d) across the selected top-20
```

This assumes the top-20 basket is realized at each rebalance. In
practice, the sell buffer (`sell_buffer = 1.5`) holds existing names until
rank > 30, which reduces the number of names traded per cycle but does
not change the steady-state capacity ceiling.

### 2.3 Universe floor

`config/strategy_params.yaml: universe.min_adv_20d = $500,000` sets the
hard universe filter. Any stock with 20-day ADV below $500K is excluded
before factor computation. At a 5% participation rate, the minimum
per-stock capacity is therefore **$25,000 per trading day**. Twenty such
names in a top-20 portfolio would cap AUM at $500K -- acceptable for the
paper stage, tight for min-live.

In practice, the S&P 500 universe rarely hits this floor; the median
constituent ADV is far higher. The relevant capacity question is not
"can we trade the worst name?" but "what is the realized participation
distribution?"

---

## 3. Capacity Placeholders (To Populate)

These tables will be filled from the first real-data backtest
(TODO-11). Until then, the numbers are intentionally blank to avoid
citation as if they were measured.

### 3.1 Realized participation distribution

Computed over the research period (2016-2023) from actual trades in the
rigorous walk-forward backtest. Measures `trade_notional / (ADV_20d * 1)`
per trade, aggregated across all rebalances.

| Percentile | Participation rate at $1M AUM | Participation rate at $10M AUM | Participation rate at $50M AUM |
|---|:---:|:---:|:---:|
| p50 (median) | TBD | TBD | TBD |
| p90 | TBD | TBD | TBD |
| p95 | TBD | TBD | TBD |
| p99 | TBD | TBD | TBD |
| max | TBD | TBD | TBD |

**Gate:** p95 must remain < 5% at the target AUM. If p95 > 5%, capacity
is exceeded and AUM must be capped.

### 3.2 Per-stock capacity, worst-basket scenario

| AUM | Smallest ADV in top-20 (typical) | Max trade notional at 5% ADV | Shortfall vs required 5% weight |
|---|:---:|:---:|:---:|
| $1M | TBD | TBD | None expected |
| $10M | TBD | TBD | Possible |
| $50M | TBD | TBD | Likely |
| $100M | TBD | TBD | Likely binding |

---

## 4. Slippage Model

From `src/nyse_core/cost_model.py`:

```
spread_bps = BASE_SPREAD_BPS / sqrt(ADV / $50M) * M_monday * M_earnings
commission_bps = $0.005/share * 2 / price_per_share * 10000
```

With `BASE_SPREAD_BPS = 10`, `M_monday = 1.3`, `M_earnings = 1.5`.

### 4.1 Roundtrip cost examples (at 5% participation, $50 share)

| Scenario | ADV | Spread (bps) | Commission (bps) | Total roundtrip (bps) |
|---|:---:|:---:|:---:|:---:|
| Mega-cap, Tuesday | $500M | 3.2 | 2.0 | 5.2 |
| Large-cap, Tuesday | $50M | 10.0 | 2.0 | 12.0 |
| Large-cap, Monday | $50M | 13.0 | 2.0 | 15.0 |
| Mid-cap, earnings week | $10M | 33.5 | 2.0 | 35.5 |
| Small-cap, earnings Monday | $2M | 97.0 | 2.0 | 99.0 |
| Universe floor | $0.5M | 194.0 | 2.0 | 196.0 |

### 4.2 Known limits of this model

1. **Parametric, not calibrated.** The `BASE_SPREAD_BPS = 10` constant
   is derived from secondary-source NYSE roundtrip estimates, not from
   vendor tick data. Calibration is a Phase 5 dependency.
2. **No permanent-impact term.** The formula captures the per-trade
   spread cost but not the price drift induced by the cumulative trade
   sequence. Acceptable at participation rates <= 5% per Almgren-Chriss;
   breaks down above ~10%.
3. **No venue / dark-pool decomposition.** All trades are assumed to
   cross the quoted spread at a single lit venue. NautilusTrader's
   execution algo (TWAP over 30 minutes) partially mitigates this by
   spreading the order; the model does not credit the mitigation.

---

## 5. Unwind Scenarios

The strategy must be able to exit its entire book without triggering
cost thresholds. "Unwind" is defined as flattening every long position
to cash. Three reference scenarios:

### 5.1 Routine unwind (end of strategy run)

Participation rate: 3% (operating point). Applied simultaneously to
every holding.

```
unwind_days = ceil(max_i [ weight_i * AUM / (0.03 * ADV_i) ])
```

For a 20-stock equal-weight portfolio at AUM `A`:

```
unwind_days = ceil( (A / 20) / (0.03 * min(ADV_top20)) )
            = ceil( 1.667 * A / min(ADV_top20) )
```

### 5.2 Stress unwind (F3 drawdown trigger)

A VETO trigger (F3 max drawdown < -25% or F1 signal death) requires
halting live trading and switching to paper. The unwind runs at the
circuit-breaker ceiling of 10% ADV for maximum speed. Expected
completion: 1-2 trading days for AUM < $20M; longer if universe floor
binds.

### 5.3 Disaster unwind (black swan, 1-day liquidity event)

If overall market liquidity collapses (e.g., 2020-03-16 style), ADV
estimates are stale; the cost model will understate slippage by an
unknown margin. The strategy's response is:

1. Kill-switch engaged (`strategy_params.yaml: kill_switch: true`);
2. No new orders submitted;
3. Existing positions held until liquidity normalizes;
4. Telegram alert + dashboard banner.

This is a deliberate non-action. Forcing liquidation during a liquidity
crisis is how strategies die. Disaster-unwind capacity is **not** a
tunable dimension of this strategy.

### 5.4 Unwind horizon placeholder table (from real-data backtest)

| AUM | Routine (3% ADV) | Stress (10% ADV) | Disaster |
|---|:---:|:---:|:---:|
| $1M | TBD | TBD | Hold |
| $10M | TBD | TBD | Hold |
| $50M | TBD | TBD | Hold |
| $100M | TBD | TBD | Hold |

---

## 6. Liquidity Stress Scenarios

The strategy is expected to be reviewed against the following historical
regimes. Each regime exposes a distinct failure mode.

| Regime | Period | Primary failure mode | Mitigation in current design |
|---|---|---|---|
| GFC | 2008-09 to 2009-03 | Correlation spike; value factors underperform | Binary regime overlay -> 40% exposure when SPY < SMA(200) |
| Flash Crash | 2010-05-06 | Intraday liquidity vacuum | No intraday exposure; weekly cadence avoids |
| Aug 2015 ETF dislocation | 2015-08-24 | ETF bids detach from NAV | Universe is cash equities, not ETFs |
| Q4 2018 | 2018-10 to 2018-12 | Momentum crash | Ridge dampens; sell buffer slows rotation |
| COVID | 2020-02 to 2020-04 | Liquidity collapse + correlation 1.0 | Regime overlay; kill-switch option |
| Rate shock | 2022-Q1 to 2022-Q3 | Factor rotation (growth -> value) | Ridge re-fit at each fold boundary |
| Aug 2024 carry unwind | 2024-08-05 | Cross-asset spillover | Covered by 2024-2025 holdout (one-shot) |

### 6.1 Gaps

None of these scenarios have been formally stress-tested by running the
pipeline against the relevant sub-periods. The plan is to add a
`scripts/run_regime_stress.py` utility that reruns the backtest on each
named window and reports Sharpe, MaxDD, turnover, and cost drag
separately. Current status: not implemented; see TODOS.md for addition.

---

## 7. Capacity Monitoring in Production

### 7.1 Dashboard metrics (Streamlit, `dashboard.py`)

The dashboard surfaces the following per-rebalance:

1. **Realized participation rate per trade.** Flags any trade > 5% of ADV.
2. **Universe ADV floor breach count.** How many selected names are near
   the $500K minimum.
3. **Sector concentration.** Max GICS sector weight vs the 30% cap.
4. **Single-stock concentration.** Max single-stock weight vs the 10% cap.
5. **Turnover decomposition.** Name rotation vs weight adjustment (from
   TWSE monitoring priority stack, Section 13.3 of Lesson_Learn).

### 7.2 Automatic actions

| Trigger | Action |
|---|---|
| Any trade would exceed 10% ADV | `nautilus_bridge` downsizes to 5% ceiling, logs WARNING |
| Universe floor breach > 3 stocks | F8 WARNING (data staleness analog) |
| Monthly turnover > 200% | F5 WARNING, exposure -> 60% |
| Annual cost drag > 5% | F6 WARNING, exposure -> 60% |

---

## 8. Capacity Communication

When reporting AUM or capacity figures externally, use the following
canonical language:

> "Paper-tier capacity is estimated at up to $20M AUM with a 5% ADV
> participation ceiling. Estimates are preliminary and pending the first
> real-data walk-forward run. Capacity beyond $20M requires a new slippage
> calibration and is not currently sanctioned."

Avoid: "The strategy scales to $X" without naming the participation rate
and the slippage calibration vintage.

---

## 9. Known Limitations of This Document

1. **Parametric cost model.** Real slippage is unobserved; Section 4.2
   covers the specifics.
2. **No interaction with broker execution data.** Capacity estimates
   assume idealized TWAP fills; real fill distributions (queue position,
   cancel/replace behavior) are not modeled.
3. **Research period only.** All cited numbers (once populated) will
   reflect 2016-2023 market microstructure. Mid-2020s microstructure
   (decimalization 2.0, retail options flow, after-hours venues) is
   captured only by the 2024-2025 holdout, which is run once.
4. **Single-operator, single-account.** Cross-account or multi-strategy
   capacity (shared liquidity budget) is out of scope.
5. **Crisis behavior is disclosed, not measured.** Section 5.3 describes
   the design choice; it is not a claim about realized outcomes in a
   future disaster.

---

*Related: [NYSE_ALPHA_TECHNICAL_BRIEF.md](NYSE_ALPHA_TECHNICAL_BRIEF.md) (strategy) | [MODEL_VALIDATION.md](MODEL_VALIDATION.md) (validation) | [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) (operational response) | `src/nyse_core/cost_model.py` (slippage formula) | `config/strategy_params.yaml` (caps)*
