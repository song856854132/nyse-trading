# Stress Test Framework

**Version 0.1 | 2026-04-18 | Pre-Paper-Trade**
**Audience:** Risk-function readers (LP ODD, independent validator, regulatory exam)
**Supersedes:** Ad-hoc stress commentary scattered in `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`.

---

## Why this document exists

DDQ §4.5 refers to "block bootstrap CI + regime tests." That is a method description, not
a stress test. A stress test answers: **"Under a named historical scenario, what happens
to the portfolio, and why?"** LP risk teams expect named scenarios with expected behavior,
not bootstrap confidence intervals.

This document specifies (a) the methodology, (b) named scenarios we stress against, (c)
expected strategy behavior under each, and (d) what observed behavior would invalidate
our expectations.

**Important limitation:** As of 2026-04-18, no live or paper trading has occurred and the
factor ensemble has not cleared gate validation (3/3 Tier-1 price-volume factors failed,
fundamentals pending). Stress-test results are expectation statements grounded in
strategy design and historical market data. Actual scenario replays will be added after
fundamentals complete screening and the ensemble produces a walk-forward backtest.

---

## 1. Methodology

### 1.1 Three complementary approaches

| Method | What it tests | Limitation |
|--------|---------------|-----------|
| **Historical scenario replay** | Strategy P&L in a specific historical window | Path-dependent; each scenario runs once |
| **Block bootstrap** | Distribution of rolling-window returns under stationary resampling | Destroys serial correlation at block boundaries; tail may be under-represented |
| **Synthetic shock injection** | Strategy response to targeted factor-level shocks | Not reality; tests sensitivity to assumed shock, not to observed stress |

All three are maintained. None replaces the others.

### 1.2 Historical scenario replay

For each named scenario in §2:

1. Fetch OHLCV + fundamentals + short interest for the scenario window into a
   scenario-specific DuckDB (never `research.duckdb`, which is immutable for
   research-period validity).
2. Run the live-configured ensemble on the scenario window using `scripts/run_backtest.py`
   with the current `config/strategy_params.yaml` snapshot hash logged.
3. Record: cumulative return, max drawdown, daily volatility, turnover, cost drag, which
   F1-F8 triggers fired, and time-to-trigger for each.
4. Append result to `results/stress_tests/<scenario>_<run_date>.json` plus research-log
   event `stress_test_run` via `scripts/append_research_log.py`.

### 1.3 Block bootstrap

Stationary block bootstrap (Politis-Romano 1994) on daily strategy returns with block
size 63 trading days (≈ 3 months) and 10,000 reps. Reports: 2.5th / 50th / 97.5th
percentile Sharpe, MaxDD, cumulative return. Used to characterize tail behavior of the
strategy's own return distribution, not to re-run history.

### 1.4 Synthetic shock injection

Three families:

| Family | Shock | Where applied | Question answered |
|--------|-------|---------------|-------------------|
| Factor death | Set one factor's IC to 0 for a rolling 60-day window | `statistics.py` simulation layer | Does F1 trigger on time? |
| Sign flip | Invert one factor's score for a rolling window | Pre-combination | Does F2 trigger after 3 flips? |
| Vol shock | Multiply all realized returns ×3 for a single day | Post-construction | Do position caps hold under extreme realized slippage? |

These are synthetic. They test the monitoring and risk-control plumbing, not market
behavior.

---

## 2. Named Historical Scenarios

Each scenario has: window, market-level statistics, expected strategy behavior, and
falsification conditions. Expected behaviors are derived from strategy construction
(risk overlay rules, position caps, trigger thresholds), not from a backtest on these
windows. Backtest results will be added to this document once they are produced.

### Scenario A — 2008 Global Financial Crisis

**Window:** 2008-09-01 to 2009-03-31 (7 months; Lehman collapse → March 2009 low).
**Market statistics (public):**
- SPY peak-to-trough: -54.9% (Oct 2007 to Mar 2009)
- In-window SPY: -42.8%
- Realized daily vol: 3.1% (5.5x long-run average)
- SMA-200 on SPY: crossed below in Dec 2007, stayed below through Apr 2009

**Expected strategy behavior:**
- Regime overlay flips to bear (100% → 40% gross) within 1 week of SMA-200 cross, limiting
  absolute-dollar drawdown even if factor signal fails
- F3 (MaxDD < -25%) likely fires; strategy halts to paper mode
- F1 (rolling IC below 0.01) likely fires — most cross-sectional anomalies were dominated
  by liquidity and margin-call flows, not fundamentals
- Expected absolute drawdown with regime overlay: -15% to -25% (40% of -42% = -17%, plus
  factor alpha dispersion in either direction)
- Expected behavior WITHOUT regime overlay: -30% to -45% — quantifies the regime overlay's
  contribution

**Falsification condition:** MaxDD worse than -30% on this scenario invalidates the regime
overlay's protective role and triggers the design to be re-examined.

**2026-04-18 status:** Scenario data not yet collected; will be pulled into
`stress.duckdb` post-fundamentals-screening.

### Scenario B — 2020-Q1 COVID Crash

**Window:** 2020-02-19 to 2020-04-30 (10 weeks; peak to recovery start).
**Market statistics (public):**
- SPY peak-to-trough: -33.9% (Feb 19 to Mar 23, 2020)
- Realized daily vol: 5.8% (fastest bear in history)
- SMA-200 cross: Mar 9, 2020 (broke below) — overlay lags 14 sessions
- Sharpe of cap-weight = strongly negative; equal-weight worse

**Expected strategy behavior:**
- Regime overlay does NOT flip fast enough — SMA-200 is a slow indicator. Strategy takes
  the first ~2 weeks of the drawdown at full exposure
- Once flipped to bear (40% gross), captures the rapid April recovery at only 40% — so the
  strategy underperforms SPY in the rebound even if it protected capital on the way down
- F3 (MaxDD < -25%) may fire; if so, strategy halts through the recovery — this is a known
  weakness
- **Ivol behavior (from 2026-04-18 regime study):** bear-regime IC = -0.0342 (strongly
  negative for our sign convention). Ivol would have been an anti-signal during this
  window — the factor's failure mode manifests here

**Falsification condition:** If bear-regime IVOL behavior during 2020-Q1 is MORE negative
than the 2016-2023 average of -0.0342, it suggests COVID-specific dynamics drove the
factor's failure and the regime-conditional inversion hypothesis (TODO-23) deserves
evidence.

**Known limitation:** Regime overlay is demonstrably too slow for this scenario. A
documented weakness, not a solvable one — faster indicators (VIX cross, short-term MA)
create whipsaw risk that historically costs more than it saves. Disclosed in DDQ §4.8.

### Scenario C — 2022 Rate Shock

**Window:** 2022-01-03 to 2022-10-14 (9 months; peak to October low).
**Market statistics (public):**
- SPY peak-to-trough: -25.4%
- Slow grind, not a crash. Realized daily vol: 1.4% (elevated but not extreme)
- SMA-200 on SPY: crossed below Feb 2022, stayed below through Nov 2022
- Value outperformed growth by ~20pp — factor strategies sensitive to style loadings

**Expected strategy behavior:**
- Regime overlay flips to bear in Feb → reduced exposure for most of drawdown
- Piotroski/profitability factors (value-tilted) likely contribute positively — offsets
  the -60% growth-equity drawdown
- Momentum likely flat-to-negative during the grind; IVOL negative
- Expected absolute drawdown with regime overlay: -10% to -15%
- F3 does NOT fire (MaxDD stays above -25%)
- F5 turnover spike may fire if rotation from growth to value forces unusually high
  weekly rebalance turnover — expected peak monthly turnover ~80%, below the 200% trigger

**Falsification condition:** If F5 fires during 2022 or monthly turnover exceeds 150%,
the allocator's sell-buffer hysteresis needs revisiting.

### Scenario D — 2018-Q4

**Window:** 2018-10-01 to 2018-12-31 (3 months).
**Market statistics (public):**
- SPY peak-to-trough: -19.8%
- Sudden; caused by Fed tightening surprise
- SMA-200 cross: late Oct — regime overlay reacts fast
- Strong year-end recovery began late December

**Expected strategy behavior:**
- Regime overlay flips to bear within 2-3 weeks. Captures most of decline at bull exposure,
  then reduced exposure for final leg
- F3 unlikely to fire (strategy MaxDD expected ~ -12% to -16%)
- Quick recovery after year-end: regime overlay takes 2+ months to reverse (SMA-200 is
  slow coming back up), so Q1 2019 return is captured at 40% exposure — a cost
- Expected Q4 net return: -8% to -12%; expected Q1 2019 follow-on: underperformance vs
  SPY by 3-6pp due to the overlay drag

**Falsification condition:** If Q1 2019 underperformance exceeds 10pp, the regime
overlay's reversal lag is too long and the strategy is systematically giving up the
post-drawdown rally.

### Scenario E — 2021-Q1 Meme-Stock Squeeze

**Window:** 2021-01-19 to 2021-03-05 (7 weeks).
**Market statistics (public):**
- GME, AMC, BBBY had 5-10x returns in the window
- High-IVOL names dominated the top of the cross-sectional return distribution
- SMA-200 regime: bull throughout; overlay did not reduce exposure
- SPY return: +3.2% — benign index-level

**Expected strategy behavior:**
- Ivol-20d strategy is **short high-IVOL by construction** (sign = -1, low IVOL → high rank
  → buy). During this window, being underweight the meme stocks would have caused a large
  negative excess return in the IVOL factor leg
- Momentum-2-12 might accidentally catch GME mid-squeeze if the 2-month return was strong
  enough for it to enter the universe — creates concentration risk at the single-name
  level
- F4 (single stock > 15%) protects against the worst case; caps enforce 10%
- Expected ensemble drag: 2-4 weeks of ~-2% weekly underperformance vs RSP, then
  reversion as squeeze collapses

**Falsification condition:** If single-name concentration exceeds 12% at any point, F4
should have fired and didn't — check `src/nyse_core/risk.py` enforcement.

**Known weakness:** The strategy does not have a "no-IVOL in squeeze regimes" override.
Such overrides would require a squeeze-regime indicator, which would itself need research
validation and pre-registration.

### Scenario F — 2015-08 Flash Crash

**Window:** 2015-08-17 to 2015-08-28 (2 weeks).
**Market statistics:**
- SPY intraday low: -11% on Aug 24, 2015; closed -5% that day
- Algorithmic / liquidity-driven; no fundamental trigger
- Recovery within 2 months

**Expected strategy behavior:**
- Weekly rebalance shields the strategy from intraday chaos — the Friday rebalance on
  Aug 21 prices in the pre-crash state; Monday Aug 24 TWAP execution catches the crash
- If TWAP executes during the flash crash window, slippage could exceed 50bps per leg
  vs normal ~5bps
- F6 cost-drag may fire retrospectively (rolling annual cost drag spikes briefly)
- Strategy recovers within 2 subsequent rebalances
- SMA-200 does not cross; regime overlay stays bull throughout

**Falsification condition:** If simulated slippage exceeds 100bps per leg on Aug 24, the
TWAP duration (30 minutes) may be too short to avoid the crash window — consider extending
to 60 minutes, which is tested in sensitivity analysis.

---

## 3. Stress-test schedule

| Frequency | Stress | Done by | Reported in |
|-----------|--------|---------|-------------|
| Pre-paper | All 6 named scenarios, once, historical replay | Operator | `docs/STRESS_TEST_FRAMEWORK.md` (this file, appendix) |
| Quarterly during paper + live | Block bootstrap on live returns | Automated | Quarterly letter §7 |
| Annually during live | All 6 named scenarios replayed on current ensemble config | Operator | Annual LP letter + `results/stress_tests/` |
| On model retrain | Synthetic shock injection | Automated (CI) | Research log `model_retrain` event |
| On material parameter change | Full scenario set rerun | Operator | Pre-change review + research log `config_change` event |

---

## 4. What these scenarios do NOT cover

Honesty about limitations is more valuable than expansive claims.

- **Regime transitions that haven't happened yet.** A 1970s stagflation repeat, a true
  currency crisis, sustained negative real rates for a decade — none of these are in the
  2015-2025 calibration window.
- **Microstructure changes.** Decimalization, Reg NMS, the disappearance of AMEX
  specialists — all preceded our data window. A future microstructure change (24h trading,
  direct-to-consumer disintermediation) would invalidate the execution model.
- **Counterparty failure.** Scenario set is market-driven. Broker/prime failure is covered
  in `docs/ODD_PACKAGE.md` §5 and `docs/DISASTER_RECOVERY.md`.
- **Single-stock tail events.** An individual security going to zero (Enron, Lehman
  single-name exposure). Position cap (10%) limits damage to a survivable level but does
  not eliminate it.

---

## 5. When stress test results disagree with forecasts

Per `docs/OUTCOME_VS_FORECAST.md` and AP-6, post-hoc adjustment of forecasts or scenarios
after observing results is forbidden. If a scenario replay produces a result materially
different from the expected behavior in §2:

1. **Record the observation** as a `stress_test_run` event in the hash-chained research log
2. **Do not adjust the expected-behavior text** retroactively. Add a new dated subsection
   ("Observed 2026-XX-XX: expected -15%, actual -22%") below the expectation
3. **Trigger a design review** if drawdown exceeds expectation by >1.5×, if any VETO
   trigger fires unexpectedly, or if expected trigger fails to fire
4. **Document design changes** (if any) in a new research-log `design_change` event with
   rationale before implementing

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Initial framework. Named scenarios A-F with expected behavior. No backtest numbers — pending fundamental-factor screening. |

**Document owner:** Operator.
**Review cadence:** Annually; post-material design change; after each scenario replay.
**Related documents:** `docs/DDQ_AIMA_2025.md` §4.5, `docs/RISK_LIMITS.md`, `docs/OUTCOME_VS_FORECAST.md`, `config/falsification_triggers.yaml`.
