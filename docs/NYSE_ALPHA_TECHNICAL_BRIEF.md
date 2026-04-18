# NYSE Cross-Sectional Alpha -- Technical Brief

**Version 0.4 | April 2026 | Pre-Paper-Trade**

---

## 1. Executive Summary

This document presents the statistical evidence and methodology behind a cross-sectional S&P 500 equity factor strategy. The system uses 13+ factors across 6 families, combined via Ridge regression, with weekly rebalancing and a 10-layer risk stack. The research pipeline is complete through Phase 4 with 934 tests passing. Walk-forward backtesting with strict per-date feature recomputation is operational.

**Key results (targets, pre-live):**

| Metric | Target Range | Derivation |
|--------|:------------:|:----------:|
| OOS Sharpe | 0.8 -- 1.2 | TWSE predecessor net Sharpe 1.186 |
| CAGR | 18 -- 28% | TWSE achieved 23.22% |
| MaxDD | -15% to -25% | TWSE -16.7% with regime overlay |
| Annual turnover | < 50% | Sell buffer + position inertia |
| Cost drag | < 3% of gross | NYSE roundtrip ~12 bps |
| Permutation test | p < 0.05 | Stationary block bootstrap, 200+ reps |
| Bootstrap CI (Sharpe) | lower > 0 | 63-day blocks, 10,000 reps |

**What is validated:** The walk-forward infrastructure, statistical test suite, gate system, and cost model are implemented and tested. Factor IC and gate evaluations are computed per-factor.

**What is not validated:** No true OOS holdout test has been run on 2024--2025 data. All targets are estimates derived from the TWSE predecessor and NYSE cost structure analysis. Live performance is unknown.

---

## 2. Economic Thesis

### Friction Hypotheses

Each factor family must articulate the structural friction or behavioral bias it exploits. Factors without a friction hypothesis are rejected regardless of IC.

| Factor Family | Friction / Inefficiency | Persistence Expectation |
|---------------|------------------------|------------------------|
| Price/Volume (IVOL, momentum, 52w high, EWMAC) | Volatility mean reversion; investors overreact to vol spikes. Low-IVOL anomaly documented across markets. | Durable -- structural risk preference |
| Fundamental (Piotroski, accruals, profitability) | Earnings quality mispricing. Accruals anomaly (Sloan 1996) reflects slow analyst adjustment to balance sheet signals. | Moderate -- well-known but persistent |
| Earnings (surprise, analyst revisions) | Post-earnings-announcement drift. Market underreacts to earnings surprises for 5--20 trading days. | Moderate -- decay is faster in large-cap |
| Short Interest (short ratio, days to cover, PCA) | Informed positioning signal. High short interest predicts negative returns (Desai et al. 2002). FINRA publication lag (T+11) delays retail response. | Moderate -- regulatory dependent |
| Sentiment (options flow, put/call, vol skew) | Options market leads equity market by 1--5 days. Informed traders use options for leverage. | Moderate -- capacity constrained |
| NLP Earnings (transcript sentiment) | Tone of earnings calls contains information not fully captured by reported numbers. CEO hedging language predicts negative surprises. | Experimental -- data quality dependent |

### Why Weekly Rebalance Works on NYSE

NYSE roundtrip cost (~12 bps) is 5.7x cheaper than TWSE (~68.5 bps). This cost advantage makes weekly rebalancing viable:

```
TWSE monthly:    68.5 bps x 12 = 822 bps/year (forced monthly by cost)
NYSE weekly:     12 bps x 52 x turnover_fraction = ~312 bps/year at 50% annual turnover
```

The TWSE system was constrained to monthly rebalancing because the 30 bps securities transaction tax alone exceeded weekly alpha. NYSE has no such tax.

---

## 3. Factor Universe

### Complete Factor Table

| # | Factor | Family | Sign | Friction Hypothesis | Expected IC | Expected IC_IR |
|---|--------|--------|:----:|---------------------|:-----------:|:--------------:|
| 1 | ivol_20d | Price/Volume | -1 | Low-IVOL anomaly: investors overpay for lottery-like stocks | >= 0.02 | >= 0.5 |
| 2 | 52w_high_proximity | Price/Volume | +1 | Anchoring bias to 52-week high (George-Hwang 2004) | >= 0.02 | >= 0.5 |
| 3 | momentum_2_12 | Price/Volume | +1 | 2-12 month momentum (Jegadeesh-Titman 1993), skip most recent month | >= 0.02 | >= 0.5 |
| 4 | ewmac | Price/Volume | +1 | Exponentially weighted moving average crossover as trend signal | >= 0.02 | >= 0.4 |
| 5 | piotroski_f_score | Fundamental | +1 | Financial strength predicts returns (Piotroski 2000) | >= 0.02 | >= 0.4 |
| 6 | accruals | Fundamental | -1 | High accruals predict negative returns (Sloan 1996) | >= 0.02 | >= 0.4 |
| 7 | profitability | Fundamental | +1 | Gross profitability premium (Novy-Marx 2013) | >= 0.02 | >= 0.4 |
| 8 | earnings_surprise | Earnings | +1 | Post-earnings-announcement drift, 5-20d half-life in large-cap | >= 0.03 | >= 0.5 |
| 9 | analyst_revisions | Earnings | +1 | Analyst herding and slow revision propagation | >= 0.02 | >= 0.4 |
| 10 | short_ratio | Short Interest | -1 | Informed short selling predicts negative returns | >= 0.02 | >= 0.4 |
| 11 | days_to_cover | Short Interest | +1 | Short squeeze potential for high days-to-cover stocks | >= 0.02 | >= 0.3 |
| 12 | short_pca_composite | Short Interest | +1 | PCA-compressed short interest composite captures latent dimension | >= 0.03 | >= 0.5 |
| 13 | options_flow | Sentiment | +1 | Informed options positioning leads equity by 1-5 days | >= 0.02 | >= 0.3 |

Additional factors (put_call_ratio, implied_vol_skew, transcript_sentiment) are implemented and gated but may not survive G3/G5 evaluation.

### Sign Convention (Codex #9)

ALL factors are oriented so HIGH score = BUY signal. Factors that are naturally inverse (IVOL, accruals, short_ratio) have `sign_convention=-1` in the FactorRegistry. The registry negates their output before normalization. No downstream module needs to know about sign inversion.

---

## 4. Normalization Methodology

### Rank-Percentile Mapping

All factor values are normalized to [0, 1] via cross-sectional rank-percentile:

$$
x_i^{\text{norm}} = \frac{\text{rank}(x_i) - 1}{N - 1}
$$

where $N$ is the number of non-NaN values in the cross-section.

**Properties:**
- Bounded: output is strictly in [0, 1]
- Robust: immune to outliers (a value 100x the mean gets rank 1.0, not a z-score of 50)
- Uniform marginals: guarantees the combination model sees uniformly distributed inputs
- Ordinal: preserves ranking but discards magnitude information

**Special cases:**

| Condition | Behavior |
|-----------|----------|
| All NaN | All NaN output + WARNING diagnostic |
| Single value | 0.5 |
| Constant series | 0.5 for all values |
| Tied values | Average rank method |
| NaN positions | Preserved (NaN in, NaN out) |

**Mathematical specification (`normalize.py`):**

```python
def rank_percentile(series: pd.Series) -> tuple[pd.Series, Diagnostics]:
    """Cross-sectional rank-percentile in [0, 1].

    rank(method='average') -> divide by (count - 1) -> clip to [0, 1].
    NaN positions are preserved.
    """
```

**Evidence for rank-percentile over z-score:** TWSE Phase 44 showed +0.109 Sharpe improvement when switching from z-score to rank-percentile normalization. The improvement came from better handling of heavy-tailed factor distributions.

### AP-8 Enforcement

`signal_combination._validate_feature_range()` asserts all feature values are in [0, 1] before any model receives them. Violation raises `ValueError("AP-8 violation")`. This is checked at every call to `fit()` and `predict()`.

---

## 5. Combination Model

### Ridge Regression (Default)

The default combination model is Ridge regression:

$$
\hat{y} = X\hat{\beta}, \quad \hat{\beta} = (X^TX + \alpha I)^{-1}X^Ty
$$

where:
- $X \in \mathbb{R}^{n \times p}$ is the feature matrix (rank-percentile normalized, $p$ = 13--16 factors)
- $y \in \mathbb{R}^n$ is the forward return vector
- $\alpha = 1.0$ is the L2 regularization strength (default)
- $I$ is the identity matrix

Feature importance is computed as normalized absolute coefficients:

$$
w_i = \frac{|\hat{\beta}_i|}{\sum_j |\hat{\beta}_j|}
$$

### CombinationModel Protocol

```python
class CombinationModel(Protocol):
    def fit(self, X: pd.DataFrame, y: pd.Series) -> Diagnostics: ...
    def predict(self, X: pd.DataFrame) -> tuple[pd.Series, Diagnostics]: ...
    def get_feature_importance(self) -> dict[str, float]: ...
```

### Alternative Models (Gated)

| Model | Implementation | Gating Criteria | TWSE Precedent |
|-------|---------------|-----------------|----------------|
| **GBM** (LightGBM) | Early stopping (80/20 holdout), `verbose=-1`, L2 reg | Must beat Ridge by > 0.1 OOS Sharpe AND overfit ratio < 3.0 | TWSE overfit ratio: 6.9x (FAIL) |
| **Neural** (PyTorch MLP) | 2-layer: Input->Linear->ReLU->Dropout->Linear->ReLU->Dropout->Linear(1), y standardized | Same gating criteria as GBM | Not tested on TWSE |

**Why Ridge wins by default:** With 13--16 factors and ~50 monthly cross-sections of ~500 stocks each, the parameter-to-observation ratio favors linear models. Ridge's L2 penalty constrains coefficient magnitudes, producing an overfit ratio of ~1.08x on the TWSE system. GBM's 6.9x overfit ratio on TWSE data was disqualifying.

---

## 6. Walk-Forward Cross-Validation

### Specification

```
Time ──────────────────────────────────────────────────────────────>

Fold 1:  [==========TRAIN==========][purge][=====TEST=====]
Fold 2:       [===========TRAIN===========][purge][=====TEST=====]
Fold 3:            [============TRAIN============][purge][=====TEST=====]

Properties:
  Window type:     EXPANDING (not rolling). Each fold trains from t=0.
  Min training:    2 years (504 trading days)
  Purge gap:       max(purge_days, target_horizon_days). Auto-adjusts.
  Embargo:         Equal to target horizon (5d or 20d)
  Test window:     ~6 months of weekly decision points
  Rebalance step:  5 trading days (weekly)
  Research period: 2016--2023 (all tuning)
  TRUE HOLDOUT:    2024--2025 (one-shot, no iteration after)
```

### Strict Per-Date Feature Recomputation (Phase 4)

The Phase 4 rewrite eliminated four fatal bugs in the walk-forward backtest:

1. **Feature averaging across dates:** Previously averaged forward returns across all train dates, collapsing the cross-sectional structure. Fixed by `_build_train_stack()`, which iterates weekly through train dates and computes features independently at each rebalance date using a trailing 252-day OHLCV window.

2. **Feature reuse between train and test:** Previously used features computed during training for test predictions (lookahead bias). Fixed by `_run_test_dates()`, which recomputes features at each test date using only trailing data.

3. **Hardcoded turnover and cost:** Previously `annual_turnover=0.0, cost_drag_pct=0.0` in all results. Fixed with dynamic per-rebalance computation.

4. **No memory management:** Previously accumulated all fold data in memory. Fixed with `gc.collect()` between folds and trailing window limits.

### Forward Return Target

$$
y_t = \frac{\text{close}_{t+5}}{\text{open}_{t+1}} - 1
$$

This captures the return actually available after execution delay (signal on Friday close, execution on Monday open).

**Dual horizon validation:**
- Primary (production): 5-day forward returns, 5-day purge gap
- Secondary (robustness): 20-day forward returns, 20-day purge gap
- Both must produce positive OOS Sharpe for factor admission

---

## 7. Statistical Validation Suite

### Test 1: Permutation Test

**Null hypothesis:** Strategy Sharpe ratio = 0.

**Method:** Circular block bootstrap (Politis-Romano) with block size = 63 trading days. Shuffle returns while preserving autocorrelation structure. Re-estimate Sharpe on each permutation.

**Specification:**
- Minimum replications: 200 (target: 500)
- Block size: 63 days (~3 months, captures quarterly effects)
- Rejection criterion: p < 0.05

**Implementation:** `statistics.permutation_test()` uses circular blocks that wrap around the series boundary:

```python
def _circular_block_resample(data, block_size, rng):
    """Blocks wrap around end→beginning, preserving autocorrelation."""
    n = len(data)
    n_blocks = int(np.ceil(n / block_size))
    starts = rng.integers(0, n, size=n_blocks)
    indices = np.concatenate([np.arange(s, s + block_size) % n for s in starts])[:n]
    return data[indices]
```

### Test 2: Block Bootstrap Confidence Interval

**Purpose:** Estimate 95% CI for the Sharpe ratio without distributional assumptions.

**Specification:**
- Block size: 63 days
- Replications: 10,000
- Parallelized via joblib
- Required: CI lower bound > 0

### Test 3: Romano-Wolf Stepdown

**Purpose:** Multiple testing correction across all factors simultaneously.

**Method:** Joint null distribution using the same block structure across all factors, preserving cross-factor correlation. Stepdown procedure adjusts p-values sequentially from the most significant to the least.

**Specification:**
- Replications: 500
- Same block structure as permutation test
- Required: adjusted p < 0.05 for each factor retained

### Application Order

```
1. Walk-forward backtest                 → OOS Sharpe, CAGR, MaxDD
2. Permutation test (200--500 reps)      → p-value for H0: Sharpe = 0
3. Romano-Wolf stepdown (500 reps)       → per-factor adjusted p-values
4. Block bootstrap CI (10,000 reps)      → 95% CI for Sharpe
5. TRUE HOLDOUT (2024--2025)             → one-shot, Sharpe > 0
```

---

## 8. Gate System (G0--G5)

Every factor candidate must pass all six gates before admission to the production ensemble.

### Gate Definitions

| Gate | Metric | Threshold | Direction | Purpose |
|------|--------|:---------:|:---------:|---------|
| **G0** | OOS Sharpe | 0.3 | >= | Minimum standalone profitability in walk-forward |
| **G1** | Permutation p-value | 0.05 | < | Statistical significance (not data-mined noise) |
| **G2** | IC mean | 0.02 | >= | Minimum predictive power (Spearman rank correlation) |
| **G3** | IC IR | 0.5 | >= | Signal consistency: mean(IC) / std(IC) |
| **G4** | Max drawdown | -0.30 | >= | Worst-case risk control (no worse than -30%) |
| **G5** | Marginal contribution | 0.0 | > | Must improve the existing ensemble (not just standalone) |

### Architecture

Gates and falsification triggers share the same `ThresholdEvaluator` engine (DRY principle):

```python
class ThresholdEvaluator:
    """Stateless comparator: value {>=, >, <, <=} threshold -> bool."""
    def evaluate(self, name, metric_name, value, threshold, direction) -> ThresholdCheck
```

### G5: The Critical Gate

A factor with strong standalone IC can still fail G5 if its prediction is already captured by existing factors. This was the TWSE operating_margin lesson: IC = 0.047 (strong standalone) but G5 = FAIL because Ridge coefficients barely moved when it was added. The marginal contribution was illusory.

**Enforcement:** G5 requires that the pre-computed `marginal_contribution` metric (change in ensemble OOS Sharpe when the candidate is added) be strictly positive.

---

## 9. Risk Framework (10 Layers)

Applied sequentially after allocation. Each layer modifies the portfolio in place.

| Layer | Rule | Implementation |
|-------|------|---------------|
| 1. **Regime overlay** | SPY > SMA(200) -> 100% exposure; SPY < SMA(200) -> 40% exposure | `risk.apply_regime_overlay()` |
| 2. **Position caps** | No single stock > 10% weight; excess redistributed pro-rata | `risk.apply_position_caps()` |
| 3. **Sector caps** | No GICS sector > 30%; excess redistributed pro-rata | `risk.apply_sector_caps()` |
| 4. **Beta cap** | Portfolio beta vs SPY in [0.5, 1.5]; triggers rebalance if outside | `risk.apply_beta_bounds()` |
| 5. **Daily loss limit** | -3% portfolio -> halt all new orders; VETO alert | `risk.apply_loss_limit()` |
| 6. **Earnings event cap** | Stock reporting within 2 days -> max 5% weight | `risk.apply_earnings_cap()` |
| 7. **Kill switch** | Manual halt via config flag; checked before every order | `risk.check_kill_switch()` |
| 8. **Position inertia** | Carver's 10% deviation threshold; suppress noise-driven trades | `cost_model.should_trade()` |
| 9. **Sell buffer** | Hysteresis: top_n=20, sell_buffer=1.5 -> retain until rank > 30 | `allocator.select_top_n()` |
| 10. **Anti-double-dip** | FactorRegistry.usage_domain prevents factor in both SIGNAL and RISK | `features/registry.py: DoubleDipError` |

### Falsification Triggers

| ID | Metric | Threshold | Severity | Response |
|----|--------|:---------:|:--------:|----------|
| F1 | rolling_ic_60d | < 0.01 for 2 months | **VETO** | Halt trading, switch to paper |
| F2 | core_factor_sign_flips | > 3 in 2 months | **VETO** | Halt trading, investigate |
| F3 | max_drawdown | < -25% | WARNING | Reduce exposure |
| F4 | max_single_stock_weight | > 15% | WARNING | Review allocation |
| F5 | monthly_turnover_pct | > 200% | WARNING | Review rebalance |
| F6 | annual_cost_drag_pct | > 5% | WARNING | Review cost model |
| F7 | benchmark_split_adjusted | false | WARNING | Check SPY data |
| F8 | max_feature_staleness_days | > 10 | WARNING | Check data feeds |

Thresholds are frozen before the first live trade. No retroactive adjustment permitted.

---

## 10. Cost Model

### Dynamic Spread Formula

$$
\text{spread\_bps} = \frac{\text{BASE\_SPREAD\_BPS}}{\sqrt{\text{ADV} / \$50\text{M}}} \times M_{\text{monday}} \times M_{\text{earnings}}
$$

where:
- BASE_SPREAD_BPS = 10.0
- $M_{\text{monday}}$ = 1.3 if Monday, 1.0 otherwise
- $M_{\text{earnings}}$ = 1.5 if earnings week, 1.0 otherwise

### Commission

$$
\text{commission\_bps} = \frac{\$0.005/\text{share} \times 2}{\$50/\text{share}} \times 10{,}000 = 2.0 \text{ bps}
$$

### Total Roundtrip Example

For a stock with $50M ADV on a normal Tuesday:
- Spread: 10.0 / sqrt(1.0) = 10.0 bps
- Commission: 2.0 bps
- **Total: 12.0 bps roundtrip**

### Position Inertia (Carver)

`should_trade()` suppresses rebalancing when the weight deviation is below the inertia threshold (10%). This prevents noise-driven turnover.

$$
\text{trade if } |w_{\text{target}} - w_{\text{current}}| > 0.10
$$

### TWSE vs NYSE Cost Comparison

| Component | TWSE | NYSE |
|-----------|:----:|:----:|
| Securities transaction tax | 15 bps | 0 bps |
| Commission | ~8.5 bps | ~2 bps |
| Spread | ~45 bps | ~10 bps |
| **Total roundtrip** | **~68.5 bps** | **~12 bps** |

---

## 11. Regime Overlay

### Specification

Binary SMA(200) filter on SPY:
- SPY close > SMA(200) -> BULL -> 100% equity exposure
- SPY close < SMA(200) -> BEAR -> 40% equity exposure

### Why Binary Beats Continuous

TWSE lesson: continuous volatility-scaling FAILED. The vol-target parameter was itself unstable across regimes, creating a "phantom parameter" problem. The SMA(200) binary gate reduced max drawdown by 8--12 percentage points with minimal Sharpe impact. No additional parameters to tune.

### Known Risk

SPY data must be split-adjusted. The TWSE system experienced a false bear-market signal when a 4:1 ETF split went unhandled. Falsification trigger F7 monitors benchmark data integrity.

---

## 12. Drift Detection (3-Layer)

### Layer 1: IC Drift

Rolling 60-day IC per factor. If `mean_ic < 0.015` AND slope is negative, drift is detected.

### Layer 2: Sign Flips

Count IC sign changes per factor in trailing 2 months. If > 3 flips, F2 VETO risk.

### Layer 3: Model Decay

Rolling R-squared between predicted and actual portfolio returns. If R-squared < 0, model is worse than constant baseline.

### Urgency Assessment

| Condition | Urgency | Action |
|-----------|:-------:|--------|
| > 50% factors drifting | HIGH | Retrain urgently |
| > 25% factors drifting | MEDIUM | Schedule retrain |
| Any factor drifting | LOW | Monitor |
| None | NONE | Routine |

---

## 13. Factor Deduplication (PCA)

### Methodology

1. Compute Spearman cross-sectional correlation matrix averaged across rebalance dates
2. PCA with cumulative variance threshold (default: 90%)
3. For each principal component, select the original factor with highest absolute loading
4. Rank representatives by IC for final factor set

### Constraint

From TWSE experience (Lesson_Learn Rule #14): performance peaked at 16 factors and degraded beyond. Target: 13--16 factors. Hard ceiling: 20 factors.

---

## 14. Known Limitations and Failure Modes

### Structural Limitations

1. **Linear model only.** Ridge assumes linear factor-return relationships. Interaction effects and nonlinear payoffs are invisible. GBM/Neural alternatives are implemented but gated because they overfit with available data.

2. **No intraday signals.** The weekly Friday-signal/Monday-execution cadence cannot capture intraday dislocations or overnight gaps.

3. **Equal weight ignores conviction.** The alpha surface within top-20 is intentionally treated as flat. If true conviction differences exist, equal weighting leaves money on the table.

4. **Regime overlay is binary.** No gradual exposure adjustment. Transition periods between bull and bear create whipsaw risk near the SMA(200) boundary.

### Expected Failure Modes

| Scenario | Impact | Mitigation |
|----------|--------|------------|
| Momentum-led rally (tech concentration) | Underperformance vs SPY. Value/quality factors suppress mega-cap tech. | Known structural cost. Monitor but do not override. |
| Rapid factor crowding | IC decay across multiple factors simultaneously | F1/F2 VETO triggers; drift detection layer |
| FINRA publication lag change | Short interest factors lose timing edge | F8 data staleness trigger |
| FinMind API discontinuation | No OHLCV data | Adapter abstraction allows vendor substitution |
| Extreme sector concentration | Macro shock amplified by sector overweight | Sector caps (30% max per GICS sector) |

### Data Dependencies

| Source | Critical? | Fallback |
|--------|:---------:|----------|
| FinMind (OHLCV) | Yes | Yahoo Finance adapter (not implemented) |
| SEC EDGAR (fundamentals) | Yes | Features go NaN; impute if < 30% missing |
| FINRA (short interest) | No | Short interest factors dropped from ensemble |

---

*One-Pager: [NYSE_ALPHA_ONE_PAGER.md](NYSE_ALPHA_ONE_PAGER.md) | Full Research Record: [NYSE_ALPHA_RESEARCH_RECORD.md](NYSE_ALPHA_RESEARCH_RECORD.md)*
