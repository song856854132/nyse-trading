# Lessons Learned: TWSE Quantitative Trading Project

> Extracted from 63 research phases, 155 commits, 39 memory files, 200+ factor trials,
> and 6 months of iterative development (2026-02-03 to 2026-04-12).
> For use in bootstrapping the NYSE-trading project.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Hardest Lessons (Paid in Blood)](#2-the-hardest-lessons-paid-in-blood)
3. [Is Carver's Framework Suitable?](#3-is-carvers-framework-suitable)
4. [Is Alpha Mining the Right Way to Outperform?](#4-is-alpha-mining-the-right-way-to-outperform)
5. [Research Methodology](#5-research-methodology)
6. [Statistical Validation](#6-statistical-validation)
7. [Factor / Signal Research](#7-factor--signal-research)
8. [Portfolio Construction](#8-portfolio-construction)
9. [Data & Infrastructure](#9-data--infrastructure)
10. [Code Architecture](#10-code-architecture)
11. [Performance Numbers That Matter](#11-performance-numbers-that-matter)
12. [TWSE-to-NYSE Translation Guide](#12-twse-to-nyse-translation-guide)
13. [Operational & Deployment](#13-operational--deployment)
14. [Anti-Patterns (Never Do This)](#14-anti-patterns-never-do-this)
15. [What to Keep vs Redesign](#15-what-to-keep-vs-redesign)
16. [Top 20 Transferable Rules](#16-top-20-transferable-rules)

---

## 1. Executive Summary

This project evolved from single-stock RSI/ADX strategies to a 16-factor cross-sectional
Ridge regression model with monthly rebalancing, achieving an honest Net Sharpe of 1.186
(CAGR 23.22%) over 2021-2025 on TWSE mid-caps.

The journey's defining narrative is **progressive removal of lies**: claimed Sharpe fell
from 0.962 (full-sample) to 0.335 (first honest OOS), then was rebuilt to 1.186 through
genuine improvements. Every major leap came from fixing infrastructure or methodology,
not from finding better signals.

**Key statistics:**
- 200+ factor candidates tested across 4 mass sweeps
- 16 factors survived all gates (from a peak of 25)
- 3 alpha factory iterations attempted, ALL failed (data leakage)
- Permutation test: p=0.022 (alpha is real)
- LOT_SIZE=1000 bug corrupted 8+ phases of benchmarks
- 0050 ETF 4:1 split broke regime detection for months
- 9+ look-ahead bias fixes (the most persistent bug class)

---

## 2. The Hardest Lessons (Paid in Blood)

### 2.1 Your Infrastructure Can Lie to You Silently

**LOT_SIZE=1000** (TWSE's traditional round lot) created an artificial cash buffer that
made weak models appear defensive. The 28f model's "defensive advantage" (MaxDD -16%)
was entirely cash drag -- honest LOT_SIZE=1 showed MaxDD -28%. This single bug
invalidated ALL benchmarks from Phases 31-38. It produced no error messages, no
warnings. It confirmed our priors instead of challenging them.

**The 0050 ETF 4:1 split** (2025-06-18) caused raw prices to drop from ~194 to ~48.
The SMA200 regime module classified a bull market as bear for 135 days. This was found
by the human operator, not by any automated check. It corrupted all 2025 regime results
before Phase 41.

**Rule:** Silent measurement corruption is the most dangerous class of bug. Automated
data quality checks must cover benchmark data, not just factor data. Any corporate
action in a benchmark instrument is a P0 incident.

### 2.2 Full-Sample Sharpe Is a Mirage

Phase 34 was the measurement shock: full-sample Sharpe 0.962 collapsed to 0.335 in
honest walk-forward OOS evaluation. The overfitting gap was 0.627. This means 65% of
the apparent alpha was data-fitting artifacts.

**Rule:** NEVER use full-sample numbers for decisions. The only Sharpe that matters is
the walk-forward OOS number with purged/embargoed cross-validation.

### 2.3 Honesty Kills Most Sharpes

The Sharpe trajectory tells the whole story:

| Phase | Sharpe | What Changed |
|-------|--------|-------------|
| P34 full-sample | 0.962 | Mirage |
| P34 honest OOS | 0.335 | First real number |
| P38 LOT_SIZE=1 | 0.798 | Infrastructure fix |
| P41 + 0050 fix + regime | 0.917 | Corporate action + regime gate |
| P44 rank-transform | 1.026 | Normalization improvement |
| P49 dedup | 1.110 | Factor deduplication |
| P63 sell_buffer=1.5 | 1.186 | Cost reduction |

Every major jump came from removing a source of dishonesty or reducing costs -- not
from finding a better signal.

### 2.4 The v2.0 Catastrophe

The foundational failure that drove all subsequent architecture: v2.0 had CAGR -7.9%,
Sharpe -0.69, annual turnover ~27,000%, and cost drag 27.6%. Root cause: memoryless
daily rebalance paying 0.3% TWSE transaction tax on rank noise. Weight rebalancing
(not name rotation) was 80-86% of turnover.

**Rule:** Turnover is the silent killer. Cost drag should be the PRIMARY monitoring
metric, checked before Sharpe.

---

## 3. Is Carver's Framework Suitable?

### Verdict: Useful Scaffolding, But Requires Deep Adaptation

Robert Carver's *Systematic Trading* framework was designed for time-series momentum
across futures. This project remapped it to cross-sectional equity factor ranking:

| Carver Concept | TWSE Adaptation | Worked? |
|---------------|-----------------|---------|
| Trading rules (variations) | 16 factor families | Yes |
| Forecast combination weights | Ridge regression (learned, not hand-set) | Yes |
| Forecast mapping [-20,+20] | Rank-percentile [0,1] | Yes |
| Volatility targeting | Binary SMA200 regime (100%/40%) | Partially |
| Position inertia | Sell buffer 1.5x | **Best single optimization** |
| IDM (Instrument Diversification Multiplier) | Algebraically irrelevant under constraints | No -- phantom parameter |

### What Transferred Well

- **Position inertia (sell buffer)** was the final winning optimization: +0.040 Sharpe,
  saving ~1,644 bps over the backtest period. Directly from Carver.
- **Conceptual layering** (signal -> combination -> sizing -> risk overlay) structured
  research cleanly and prevented ad-hoc changes.
- **Evaluate through the full pipeline** is native to Carver's approach and was the
  single most important research principle.

### What Failed

- **Volatility targeting catastrophically failed** (Sharpe -0.451). `ivol_20d` was
  already a model factor; using it again for vol-targeting double-dipped, creating 30%
  single-stock concentration.
- **IDM was a phantom parameter** -- algebraically irrelevant under capital constraint
  + proportional scaling. It cancels out.
- **Continuous volatility scaling** doesn't work on TWSE (median vol=15.6%, mean=19.9%).
  Vol-targeting chronically scales down exposure. Binary regime gate (100%/40%) won.
- **Carver's 34-position spread** was beaten by a simple 15-position equal-weight
  allocator. Concentration won over diversification at this scale.

### Recommendation for NYSE

Keep Carver's architecture as a conceptual framework:
- Separate signal, combination, sizing, and risk layers
- Use position inertia (sell buffer) from day one
- But don't adopt his specific prescriptions (vol-targeting, IDM, forecast scaling)
  without empirical validation on YOUR market
- Use learned combination weights (Ridge), not hand-set weights

---

## 4. Is Alpha Mining the Right Way to Outperform?

### Verdict: Necessary But Insufficient -- Theory Must Come First

The project went through a clear evolution:

**Phase 1 (Data-First):** Sweep 139 factors, let gates decide. This was the single
biggest performance improvement (IC_IR 0.145 -> 0.685, a 4.7x jump). But a senior
quant reviewer called it "mid-tier quant team" methodology.

**Phase 2 (Theory-First):** Every factor must have a structural hypothesis about WHY
the mispricing exists, WHO loses money, and WHAT friction preserves it. Factor grounding
in a friction (retail dominance, short constraints, information asymmetry) produces
models that degrade gracefully. Purely statistical patterns vanish overnight.

**What the project actually found:**
- The mass sweep (Phase 36) found the factors. Without it, the project would still be
  at Sharpe 0.335.
- But the deflated Sharpe test yielded p=0.84 (not significant) -- the 200+ trials
  created a massive multiple-testing concern.
- The permutation test (p=0.022) rescued the finding by testing data directly.
- 3 alpha factory iterations all failed due to data leakage. Automated factor
  discovery pipelines are extremely dangerous.
- The strongest factors all had clear economic stories: margin capitulation (forced
  selling), revenue surprise (information asymmetry), idiosyncratic volatility (lottery
  demand avoidance).

### The Mature Position

1. Factor candidates CAN be discovered through broad sweeps
2. Each MUST have a stated economic hypothesis and failure mode BEFORE coding
3. Evaluation MUST be through the full allocator, not standalone IC
4. The permutation test is the ultimate gate, not deflated Sharpe
5. Causal/structural models degrade gracefully; purely statistical patterns vanish
6. **Combination over selection**: Portfolio Sharpe comes from orthogonal factor
   combinations, not from stacking the loudest signals

### The "Combination over Selection" Doctrine

This became the project's core research principle. Proof points:

- Greedy IC_IR-based factor selection: Sharpe 0.416
- Human-curated ensemble with orthogonality: Sharpe 0.798
- Individual factor quality is ANTI-CORRELATED with ensemble quality
- Effective dimensionality of 25-factor ensemble = 3.3 (most factors are redundant)
- The Fundamental Law of Active Management: IR ≈ IC × sqrt(Breadth)
- 7 short-interest factors were really 1 factor (PC1=70.6%)

**Rule:** For NYSE, start with 5-8 orthogonal factor families based on structural
hypotheses. Use Ridge regression to combine. Don't add factors for marginal IC
improvement -- add them only if they span a genuinely new dimension of mispricing.

---

## 5. Research Methodology

### 5.1 What Worked

**Tree-structured planning with pre-specified conditional branches.** Phase 42-50
introduced a master plan created by 5 detailer + 5 critic agents. Gates explicitly
determined which branch to take. This eliminated wasted work.

**Pre-registered predictions before paper trade.** Date-stamped expected IC, turnover,
Sharpe range, and 8 falsification triggers (3 VETO, 5 WARNING). Impossible to
rationalize poor performance after the fact.

**External critique is non-negotiable.** Three corrections from outside the AI's
reasoning changed the project trajectory: the user identifying the 0050 split, the
user correcting LOT_SIZE assumptions, and critic agents catching caching bugs.

**One question discipline.** Each phase answers one question. Can the report say "is
this profitable?" in the first two lines? This prevented research sprawl.

### 5.2 What Failed

**Alpha factory pipeline (all 3 iterations).** Factor selection saw ALL data while
walk-forward OOS periods were inside that range. Lesson: never build a parallel pipeline
for factor discovery that diverges from the production evaluation pipeline.

**Sequential research without synthesis.** The "run phase, see result, plan next"
approach wasted months on dead ends (model ensembles, HMM regimes, confidence sizing)
before the foundation was solid.

**Human stepwise factor selection.** Phase 40: no factor reached 3/5 majority across
CV folds. The Sharpe surface on short inner-validation windows (37-201 dates) was too
noisy.

### 5.3 The Correct Research Sequence

1. Fix infrastructure bugs (lot size, data quality, corporate actions)
2. Optimize allocator params (top_n, sell_buffer, regime gate)
3. Validate signal layer (walk-forward, permutation test)
4. Improve signals cautiously (one factor family at a time, through the allocator)
5. Add regime/sizing LAST (and test for double-dipping)

Each phase should change ONE layer, measure impact, then decide next step.

### 5.4 The Quant Council Pattern

The user convened 4 AI models simultaneously with identical briefs to propose factors.
Cross-examination surfaced edge cases no single model would find. The "winner" (Momentum-
Guarded) was selected by vote. ChatGPT's "contrarian" proposal (Retail Capitulation)
became the project's strongest behavioral signal.

**Recommendation:** Use multi-model critique for hypothesis generation, but validate
everything through the pipeline.

---

## 6. Statistical Validation

### 6.1 Mandatory Tests

| Test | Purpose | Project Result |
|------|---------|---------------|
| Permutation test (stationary bootstrap, 500 reps) | Is alpha real? | p=0.022 PASS |
| Cross-sectional rank permutation | Factor alignment genuine? | p≈0 PASS |
| Deflated Sharpe (Bailey-Lopez de Prado) | Multiple testing adjustment | p=0.84 FAIL (misleading) |
| Block bootstrap CI (63-day blocks, 10k reps) | Sharpe confidence interval | [0.12, 2.32] |
| Synthetic calibration (50 trials) | Can pipeline detect planted signal? | 100% recovery, SNR=13.5x |

### 6.2 The Permutation Test vs Deflated Sharpe

The deflated Sharpe test assumed 225 independent trials. But many trials were correlated
(same factor families, same pipeline). Effective independent trials << 225. The
permutation test captures the actual correlation structure by shuffling dates and running
the full pipeline 500x. It makes no independence assumption.

**Rule:** Use permutation testing as the primary gate. Deflated Sharpe is misleading
when trials are correlated (they almost always are in factor research).

### 6.3 Gate System (G0-G5)

| Gate | What It Tests | Threshold |
|------|--------------|-----------|
| G0 | Coverage | >= 50% universe |
| G1 | Standalone IC_IR | >= 0.02 |
| G2 | Redundancy (max correlation with existing) | < 0.50 |
| G3 | Walk-forward ensemble improvement | OOS Sharpe improves |
| G4 | Full-sample persistence | Full-sample Sharpe also improves |
| G5 | Date alignment | Baseline and integrated start within 30 days |

G3 is the ONLY gate that directly measures portfolio improvement. G0-G2 are
computational filters. G4-G5 catch subtle biases.

### 6.4 Key Statistical Insight

**Signal significance ≠ portfolio significance.** The permutation test validates that
factors predict returns. It does NOT validate the portfolio Sharpe ratio. Portfolio
performance depends on allocator parameters, transaction costs, position sizing, and
regime overlay -- none of which are tested by the permutation procedure.

### 6.5 n_eff Is Much Smaller Than n

Effective number of independent monthly observations ~ 16 (power ~26%). Five years of
monthly data provides extremely limited degrees of freedom. The Phase 42-50 plan pruned
experiment branches from 16 to 5 specifically because of this constraint.

**Rule:** Don't optimize more than 3-5 parameters with 5 years of monthly data.

---

## 7. Factor / Signal Research

### 7.1 What Worked on TWSE

| Factor | Why It Works | Transferable? |
|--------|-------------|---------------|
| `margin_capitulation` | Forced selling by retail margin accounts | Partially (US margin data less granular) |
| `revenue_surprise` | Information asymmetry, slow diffusion | Yes (quarterly earnings surprise) |
| `ivol_20d` (idiosyncratic vol) | Lottery demand avoidance | Yes (well-documented in US) |
| `piotroski_f_score` | Quality screens, sign ratio 1.000 | Yes (directly applicable) |
| `dist_to_52w_high` | Anchoring bias | Yes |
| `calendar context` (LNY, quarter-end, dividend) | Seasonal patterns | Market-specific |
| `short-interest PCA composite` | Behavioral stress (7 factors → 1 via PCA) | Partially |

### 7.2 What Failed / Was Killed

| Factor | What Happened | Lesson |
|--------|-------------|--------|
| Momentum (all timeframes) | IC_IR=0.039, G3 delta=-0.278 | Dead on TWSE (price limits, retail dominance). Market-structure dependent. |
| Friction proxies | PCA eigenvalues nearly uniform, negative tercile IC | High-friction stocks have LOWER factor IC, not higher |
| gap_persistence_20d | Negative IC_IR in ALL 5 years | Drop early, don't carry dead weight |
| Standalone IC traps (operating_margin, net_profit_margin) | IC_IR 0.5-0.7 standalone but G3 FAIL | Strong standalone ≠ ensemble improvement |
| Value factors | Kill TSMC exposure (rank pushed to 437/universe) | Creates structural underweight of largest stock |
| LightGBM | IC_IR 0.046 vs Ridge 0.735 | 6.9x train/test IC ratio. Massive overfitting. |
| Multi-frequency rebalancing | Only 1/16 factors had fast signal | Monthly (20d) is correct for this market |

### 7.3 The ivol Discovery

Phase 35 REJECTED `realized_vol_20d` (total stock volatility) as catastrophic for the
ensemble. Phase 36 ACCEPTED `ivol_20d` (idiosyncratic volatility -- removing the
market-wide component). Same academic concept, different operationalization. The market-
wide component caused scale mismatch that broke Ridge's single regularization parameter.

**Lesson:** Implementation details matter more than the academic hypothesis. A factor
can go from worst performer to best through proper operationalization.

### 7.4 Fewer Factors Beat More Factors

| Config | Net Sharpe |
|--------|-----------|
| 22f | 0.917 |
| 23f | 0.798 |
| 26f | 0.695 |
| 28f | 0.605 |
| 30f | 0.416 |

Signal dilution is the dominant effect past the sweet spot. More factors = more noise
for Ridge to fit = worse OOS performance. The 22→16f dedup (PCA on 7 correlated short
factors) further improved to 1.110.

### 7.5 Ridge vs LightGBM

| Model | OOS IC_IR | Backtest Sharpe | Overfit Ratio |
|-------|-----------|----------------|---------------|
| Ridge (22f) | 0.735 | 0.917 | ~1.3x |
| LightGBM | 0.046 | 0.505 | 6.9x |

Ridge wins decisively. Linear models are more robust than tree-based approaches when
you have ~20 factors and ~60 monthly cross-sections. LightGBM's IC_IR was essentially
zero but it still produced positive backtest Sharpe -- likely from nonlinear patterns
that aren't captured by rank IC. Not production-safe.

---

## 8. Portfolio Construction

### 8.1 The Correct Sequence

Optimize portfolio BEFORE signals. The v2.0 failure (-0.69 Sharpe, 27,000% turnover)
was entirely a portfolio construction problem. The signal was adequate; the allocator
destroyed it.

### 8.2 Position Sizing

- **top_n=15** is Sharpe-optimal for 1M NTD. Repeatedly validated across Phases 29, 44,
  and 63. Smaller (10, 12) hurts MaxDD. Larger (20) dilutes alpha.
- **Equal-weight beats signal-weighted sizing.** Ridge + rank-percentile compresses the
  alpha surface so flat that top-15 predicted returns have coefficient of variation of
  only 0.065. Signal-weighted sizing is effectively equal weight.
- **ivol-based sizing was catastrophic:** Sharpe -0.451, 30% single-stock concentration.
  Never double-dip a factor for both signal AND sizing.

### 8.3 Regime Overlay

| Regime Approach | Result |
|----------------|--------|
| SMA200 binary (100%/40%) | +0.115 Sharpe, -9pp MaxDD. **Winner.** |
| Continuous volatility targeting | Chronically scales down (TWSE vol too high) |
| Hurst/PCA/macro regime switching | Failed Gate B (too noisy at monthly granularity) |
| Position count reduction in bear | HURTS (concentrates risk) |

The regime's value is in **MaxDD reduction** (-20.6% vs -29.5%), not return enhancement.

### 8.4 Sell Buffer (Position Inertia)

sell_buffer=1.5 means: sell only when a stock's rank drops below top_n × 1.5. This
reduces churn from minor rank fluctuations. Final improvement: Sharpe 1.146 → 1.186
(+0.040). Every year improved or held (no regression). Saves ~1,644 bps over backtest
period.

**Rule:** Implement position inertia from day one. It's free alpha (cost reduction).

### 8.5 Transaction Cost Impact

- TWSE roundtrip cost: 68.5 bps (including 30 bps non-negotiable securities tax)
- Costs eat 26-34% of gross Sharpe
- Every 5 bps of additional slippage costs ~0.045 Sharpe and ~0.96pp CAGR
- The "cheapest alpha is cost reduction" -- sell_buffer optimization beats every signal
  improvement in the late phases

For NYSE, roundtrip costs are ~15-20 bps (much lower). This means:
- Higher-frequency rebalancing is viable (weekly may work)
- Cost drag is less dominant but still important
- Focus shifts more toward signal quality and less toward cost avoidance

---

## 9. Data & Infrastructure

### 9.1 Data Families Needed

A competitive quant system needs at minimum 6 data families:

| Family | TWSE Source | NYSE Equivalent | Notes |
|--------|-----------|-----------------|-------|
| Prices (OHLCV) | FinMind TaiwanStockPrice | Polygon, Alpha Vantage | Foundation of everything |
| Institutional flows | FinMind daily buy/sell | 13F (quarterly, 45-day lag) | **Biggest gap**: TWSE has daily, US has quarterly |
| Margin/short | FinMind daily margin | FINRA short interest (bi-monthly) | Much less granular on NYSE |
| Fundamentals | FinMind quarterly financials | SEC EDGAR XBRL | Comparable |
| Revenue/earnings | FinMind monthly revenue | SEC 10-Q quarterly only | **TWSE monthly revenue has no US equivalent** |
| Corporate actions | FinMind ex-dividend/split | Polygon corporate actions | Comparable |
| Valuation ratios | FinMind daily PE/PB | Self-calculate from earnings | US ratios not exchange-provided |

### 9.2 Critical Data Gaps for NYSE

1. **Monthly revenue does not exist for US stocks.** `rev_yoy` and `rev_accel` (among
   the strongest TWSE signals) must be replaced with quarterly earnings surprise,
   guidance revisions, or alternative data (credit card transactions, web traffic).
2. **Daily institutional flow does not exist.** 13F is quarterly with 45-day lag.
   Replacements: dark pool activity, short interest, options flow, ETF creation/redemption.
3. **Daily margin data per stock does not exist.** FINRA reports aggregate margin debt
   monthly. The `margin_capitulation` factor would need to be approximated from short
   interest + options put/call ratios.
4. **TDCC custody bracket data has no US equivalent.** Approximate from 13F aggregation
   or insider transactions.

### 9.3 Point-in-Time (PiT) Discipline

PiT is the most important data discipline. Key mechanisms:

- **Visibility timestamps:** Every feature records when its source data was actually
  published, not when the period ended.
- **Publication lag enforcement:** Monthly revenue uses TWSE's rule (published by 10th
  of month M+1). For US: 10-Q filings have ~45 day lag, 10-K has ~60 day lag.
- **asof-merge with max_age_days:** If source data is older than the cap, feature goes
  to NaN rather than stale data leaking forward.
- **Fill caps:** Price-derived features stale after 5 days. Revenue features after 45
  days. Fundamental features after 90 days.
- **T+1 execution shift:** Target returns use prices strictly AFTER the decision date.
  `side="right"` in searchsorted, plus `_validate_no_leakage()` that checks
  `execution_timestamp > decision_timestamp` for every row.

### 9.4 Operational Data Pipeline Patterns

1. **Atomic writes:** Always write to tempfile and rename. Prevents corruption from
   interrupted downloads.
2. **Merge-and-dedup on every write:** `drop_duplicates(subset=dedup_keys, keep="last")`
   after concatenation. Makes downloads idempotent.
3. **Provenance timestamps on every feature:** The only way to audit for look-ahead
   bias after the fact.
4. **Data quality as code:** 5 automated checks (row count, future-dated, null rate,
   staleness, price continuity). Should run in CI.
5. **Gap-threshold-aware incremental download:** Different cadences for daily (1 day),
   weekly (5), monthly (20), quarterly (45).
6. **Hybrid bulk+per-symbol strategy:** When bulk API lags behind per-symbol, use bulk
   for backfill and per-symbol for the recent tail.

### 9.5 API Rate Limiting

FinMind Supporter Plan: 6,000 req/hr. Key patterns:
- Sliding-window rate limiter (thread-safe with `threading.Lock`)
- Exponential backoff (5 retries, `min(2^attempt, 30)` seconds)
- HTTP 402 (quota exhaustion): immediate stop with partial data flush
- 90-day chunking for bulk fetches to avoid API timeouts

---

## 10. Code Architecture

### 10.1 What Works Well (Keep These Patterns)

1. **Frozen dataclasses for data contracts.** `@dataclass(frozen=True)` eliminates
   mutation bugs. Used for `TradePlan`, `PurgedSplit`, `PortfolioBuildResult`, etc.

2. **Pure function discipline in core modules.** Files marked "No I/O, no side effects"
   enforce separation of concerns. The production core is deliberately side-effect-free.

3. **Canonical schema module.** Single source of truth for column names, TypedDict
   schemas, and trading constants. Prevents magic strings.

4. **Flexible column resolution.** Case-insensitive candidate lists normalize vendor-
   specific column names. Essential for multi-vendor data.

5. **Pre-registered falsification triggers.** Scientific rigor encoded as code. 8
   triggers checked before deploying any new model version.

6. **Execution-purged walk-forward CV.** Checks for overlap between
   `[execution_timestamp, target_timestamp]` windows across train and test. Market-
   agnostic and eliminates a common source of overfitting.

7. **Factor mining template system.** Parameterized `compute_fn` allows sweeping factor
   variants efficiently.

8. **Rank-percentile normalization** instead of z-score. Simpler, more robust, better
   tail behavior. +0.109 Sharpe improvement.

### 10.2 What to Redesign

1. **Eliminate dual-layer architecture.** Don't have both `backtest/` and `src/core/`.
   Start with a single `src/nyse_core/` from day one. Multiple LOT_SIZE bugs were
   traced to importing from the wrong layer.

2. **Separate research from production scripts.** Create `research/experiments/` for
   phase-specific one-offs. Keep `scripts/` for production only (<15 files).

3. **Use proper Python packaging.** `pyproject.toml` with editable install (`pip install
   -e .`) eliminates all `sys.path` manipulation.

4. **Externalize cost model parameters.** Put slippage tiers, tax rates, and lot sizes
   in `config/market_params.yaml`, not in class bodies. Makes multi-market support
   trivial.

5. **Corporate actions as event-sourced log.** Not ad-hoc scripts (`fix_0050_splits.py`).
   Build an event log applied automatically during data loading.

6. **Replace flat-file state with SQLite/DuckDB.** JSON files in `state/v2/` work for
   single-strategy but won't scale.

7. **Default `strict=True` for calendar alignment.** Forward-filling Close on missing
   dates creates synthetic prices during suspensions. Require explicit opt-in.

8. **Build test infrastructure from day one.** 83 test files for 6,000+ source lines is
   too low. Create synthetic market data fixtures immediately.

### 10.3 Three-Layer Architecture (Recommended for NYSE)

```
src/nyse_core/         # Pure logic, no I/O. Allocator, cost model, features, risk.
src/nyse_ats/          # I/O + execution. Data feeds, order submission, persistence.
scripts/               # Production entry points only (<15 files).
research/experiments/  # Phase-specific one-offs. Never imported by production code.
```

---

## 11. Performance Numbers That Matter

### 11.1 The Honest Performance Table

| Configuration | Period | Net Sharpe | CAGR | MaxDD | Notes |
|--------------|--------|-----------|------|-------|-------|
| v2.0 baseline | 2021-2025 | -0.69 | -7.9% | -- | 27,000% turnover |
| P34 OOS (18f) | 2021-2025 | 0.335 | -- | -- | First honest number |
| P38 (23f, LOT_SIZE=1) | 2021-2025 | 0.798 | 16.4% | -22.6% | Infrastructure fix |
| P41 production (22f) | 2021-2025 | 0.917 | 19.0% | -20.6% | + 0050 fix + regime |
| P44 rank-transform | 2021-2025 | 1.026 | -- | -14.9% | Normalization |
| P49 dedup (16f) | 2021-2025 | 1.110 | 20.1% | -16.7% | Short PCA composite |
| P63 final config | 2021-2025 | 1.186 | 23.2% | -- | sell_buffer=1.5 |
| Core 2021-2024 only | 2021-2024 | 1.207 | 28.7% | -- | Excluding weak 2025 |

### 11.2 Per-Year Sharpe (Final 16f Config)

| Year | Sharpe |
|------|--------|
| 2021 | 3.04 |
| 2022 | 0.55 |
| 2023 | 1.60 |
| 2024 | 0.92 |
| 2025 | 1.23 |

2025 was the "monetization gap" -- initially near-zero (0.042 pre-rank-transform),
fixed to 1.23 by rank-percentile normalization. The gap was NOT signal decay but
allocator tail behavior.

### 11.3 Cost Structure

| Metric | Value |
|--------|-------|
| TWSE transaction tax | 0.3% on sells |
| Min broker fee | 20 NTD/trade |
| Roundtrip cost | 68.5 bps |
| Cost drag (base) | 2.8-5.5% of gross return |
| Cost drag (COVID stress) | 14.87% |
| Gross-to-net Sharpe erosion | 26-34% |

### 11.4 Statistical Validation

| Test | Result |
|------|--------|
| Permutation (stationary bootstrap, 500 reps) | p=0.022 (PASS) |
| Cross-sectional rank permutation | p≈0.000 (PASS) |
| Deflated Sharpe (225 trials) | p=0.84 (FAIL -- misleading) |
| Bootstrap CI (63-day blocks, 10k reps) | [0.12, 2.32] |
| p(Sharpe > 0) | 0.989 |
| Synthetic calibration (50 trials) | 100% recovery |

---

## 12. TWSE-to-NYSE Translation Guide

### 12.1 Market Structure Differences

| Dimension | TWSE | NYSE | Impact |
|-----------|------|------|--------|
| Daily price limits | +/-10% | None | Kills momentum on TWSE. Momentum may work on NYSE. |
| Retail participation | ~60% of volume | ~20% | Behavioral signals stronger on TWSE |
| Transaction tax | 0.3% on sells | 0 | Cost 4-5x higher on TWSE. Weekly rebalancing viable on NYSE. |
| Reporting cadence | Monthly revenue | Quarterly only | rev_yoy not available for NYSE. Use earnings surprise. |
| Institutional flow data | Daily | Quarterly (13F) | Biggest data gap. Need alternative flow proxies. |
| Market makers | Few/none for small caps | Active | Mean reversion may be weaker on NYSE |
| Odd-lot trading | Legal since Oct 2020 | Always legal | LOT_SIZE=1 from the start |

### 12.2 Factor Translation

| TWSE Factor | NYSE Replacement | Confidence |
|------------|-----------------|------------|
| `rev_yoy`, `rev_accel` | Quarterly earnings surprise, analyst estimate revisions | Medium |
| `margin_capitulation` | Short interest ratio, put/call ratio, options skew | Low |
| `inst_flow_20d` | 13F delta (quarterly), ETF flows, dark pool activity | Low |
| `ivol_20d` | IVOL (well-documented anomaly in US) | High |
| `piotroski_f_score` | Piotroski F-score (directly applicable) | High |
| `dist_to_52w_high` | 52-week high proximity (directly applicable) | High |
| `calendar context` | US-specific seasonality (January effect, earnings season) | Medium |
| `short PCA composite` | FINRA short interest + securities lending data | Medium |

### 12.3 What to Test First on NYSE

1. **IVOL anomaly** -- most documented, highest confidence of transfer
2. **Piotroski quality** -- fundamental, market-agnostic
3. **Earnings surprise** -- replaces TWSE monthly revenue
4. **52-week high anchoring** -- behavioral, likely universal
5. **Short interest** -- different data but similar behavioral story
6. **Momentum** -- DEAD on TWSE but may WORK on NYSE (no price limits)

---

## 13. Operational & Deployment

### 13.1 Deployment Ladder

| Stage | Capital | Duration | Gate |
|-------|---------|----------|------|
| Paper trade | Simulated | 3 months | IC within range, no falsification trigger |
| Shadow live | Minimum real capital | 1 month | Fills match simulation within 5 bps |
| Minimum live | Base real capital | 3 months | No trigger, realized Sharpe > 0 |
| Scale | 2-5x base | 6 months | Slippage < 10 bps, ADV validated |

### 13.2 Pre-Registered Falsification Triggers

8 triggers frozen in config BEFORE the first trade:
- F1: Signal death (IC < 0.01 for 2+ months) -- VETO
- F2: Factor death (3+ core factors flip sign for 2+ months) -- VETO
- F3: Excessive drawdown (> -25%) -- VETO
- F4-F8: Various WARNING triggers for concentration, turnover, cost drag

**Rule:** No retroactive threshold adjustment permitted. Define kill conditions before
you start.

### 13.3 Monitoring Priorities

1. **Cost drag** (PRIMARY alarm, check before Sharpe)
2. **Rolling IC and per-factor IC** (signal health)
3. **Turnover decomposition** (name rotation vs weight adjustment)
4. **Regime state** (is the benchmark correctly adjusted?)
5. **Data freshness** (is the pipeline delivering on time?)

### 13.4 Graduation Criteria for Shadow-to-Live

7 criteria, ALL must pass:
1. min_trading_days >= 20
2. mean_slippage_bps < 20
3. rejection_rate < 5%
4. settlement_failures == 0
5. fill_rate > 95%
6. rolling_ic_20d > 0.02
7. cost_drag_pct < 5%

### 13.5 Honest Self-Assessment

The user's own probability estimate for TWSE deployment:
- 60% chance system underperforms buy-and-hold over 5 years (if bull continues)
- 30% chance it outperforms (bear market + successful entries)
- 10% chance of behavioral failure (override signals, panic sell)

"The third risk is the one no backtest can model."

---

## 14. Anti-Patterns (Never Do This)

1. **Never use full-sample numbers for decisions.** Walk-forward OOS only.
2. **Never greedy-select factors by individual IC_IR.** Proven anti-correlated with
   portfolio Sharpe.
3. **Never double-dip a factor for both signal and sizing.** If it's in the model,
   don't use it again for position sizing.
4. **Never build a parallel pipeline for factor discovery.** It WILL diverge from
   production evaluation and introduce leakage.
5. **Never assume academic factor half-lives transfer to your market.** TWSE half-lives
   are 2-3x longer than QuantPedia estimates. Measure, don't assume.
6. **Never skip infrastructure validation before signal work.** LOT_SIZE, splits, and
   horizon misalignment were all silent corruptions.
7. **Never expand the experiment menu after looking at results.** Define variants,
   metrics, pass/fail rules, and stop criteria BEFORE execution.
8. **Scale mismatch kills ensembles (AP#9).** Ridge uses one regularization parameter.
   Mixing factors at different scales means Ridge cannot find one alpha that works for
   both. A factor with excellent standalone signal can sabotage the ensemble.
9. **Strong standalone IC does NOT mean ensemble improvement (AP#10).** operating_margin
   (IC_IR=0.515) had G3 delta of -0.009. Test integration FIRST.
10. **Never forward-fill prices by default.** Creates synthetic prices during
    suspensions and masks delistings. Default to strict mode.
11. **Never assume positive IC means monetizable alpha.** IC measures the full cross-
    section but the allocator holds only top-N. The "monetization gap" is real.
12. **Never let AI executors run without explicit gate verdicts.** Codex/AI will
    generate variants endlessly without synthesis. STOP points and numbered tasks are
    mandatory.

---

## 15. What to Keep vs Redesign

### Keep (Directly Portable to NYSE)

| Component | Why |
|-----------|-----|
| PurgedWalkForwardCV + ExecutionPurgedWalkForwardCV | Sophisticated CV that eliminates temporal leakage. Market-agnostic. |
| Frozen dataclass contracts | Eliminates mutation bugs. Pattern, not code. |
| Canonical schemas module | Single source of truth for column names and constants. |
| Falsification trigger framework | Scientific rigor as code. Pre-registered severity levels. |
| Factor mining template system | Parameterized compute_fn for efficient sweeps. |
| Rank-percentile normalization | Simpler and more robust than z-score. |
| Publication lag enforcement | Lag-spec pattern supporting both integer and rule-based lags. |
| Pure function discipline in core | "No I/O, no side effects" is the right doctrine. |
| Gate system (G0-G5) | Funnel prevents ad-hoc factor additions. |
| Config documents its own derivation | Every parameter records which phase derived it. |

### Redesign (Learned from Mistakes)

| Problem | TWSE Approach | NYSE Recommendation |
|---------|-------------|---------------------|
| Dual-layer code (backtest/ + src/) | Evolved organically | Single `src/nyse_core/` from day one |
| 97 scripts in one folder | Mixed research + production | Separate `scripts/` (production) and `research/` |
| sys.path manipulation | REPO_ROOT hacks | `pyproject.toml` with editable install |
| Hardcoded cost model | Class-body constants | `config/market_params.yaml` |
| Ad-hoc corporate action fixes | `fix_0050_splits.py` | Event-sourced corporate action log |
| Flat-file state management | JSON files in state/ | SQLite or DuckDB |
| 83 tests for 6000+ lines | Grew organically | Synthetic market data fixtures from day one |
| Calendar alignment default | `strict=False` (forward-fills) | `strict=True` by default |
| Custom constraint solver | 500-iteration water-fill loop | scipy.optimize or cvxpy |
| Data fetcher monolith | 730-line TWFetcher class | DataAdapter protocol + per-vendor registry |

---

## 16. Top 20 Transferable Rules

1. **Fix the portfolio layer before touching signals.** Infrastructure bugs and
   allocator mis-config waste months of signal research.

2. **Combination over selection.** Portfolio Sharpe comes from orthogonal factor
   combinations, not individual factor IC.

3. **Full-sample Sharpe is a mirage.** P34: 0.962 full-sample vs 0.335 OOS. NEVER use
   full-sample numbers for decisions.

4. **Permutation testing over deflated Sharpe.** When trials are correlated (they always
   are), deflated Sharpe massively overstates the multiple testing penalty.

5. **Corporate actions in benchmarks WILL corrupt your regime.** Automate adjustment
   checks on every data refresh.

6. **Position size constraints create phantom performance.** Always model actual
   execution constraints honestly.

7. **Theory-first, not data-first.** Every factor needs a structural friction story.
   Statistical regularities vanish; friction-based models degrade gracefully.

8. **Turnover is the silent killer.** Cost drag is the PRIMARY monitoring metric.

9. **Market structure is not a detail.** Academic results do not transfer across markets
   without empirical validation.

10. **Rank-transform inputs to linear models.** Eliminates scale mismatch, robust to
    outliers, fixes tail behavior. Free improvement.

11. **Pre-register everything.** Frozen config, falsification triggers, expected ranges.
    Makes rationalization of poor performance impossible.

12. **n_eff is much smaller than n.** 5 years of monthly data gives ~16 effective
    independent observations. Prune experiments accordingly.

13. **Implement position inertia from day one.** Sell buffer is free alpha.

14. **Fewer factors beat more.** 16f > 22f > 23f > 26f > 30f. Signal dilution dominates
    past the sweet spot.

15. **The "too good" alarm.** Any result 4-5x better than baseline should trigger
    investigation, not celebration.

16. **External critique is non-negotiable.** Three user corrections changed the project
    trajectory more than any model improvement.

17. **Evaluate through the allocator FIRST.** IC measures the full cross-section;
    the allocator holds top-N. These can move in opposite directions.

18. **Never double-dip.** If a factor is in the signal model, don't use it again for
    sizing or risk.

19. **Negative results are not wasted effort -- they ARE the knowledge.** The 13 dead
    hypotheses collectively define the boundary conditions of what works.

20. **The cheapest alpha is cost reduction.** In late-stage research, sell_buffer
    optimization beats every signal improvement.

---

*Extracted 2026-04-14 from twse-trading project (v2.5.0, 155 commits, 63 research phases).*
*For use in bootstrapping nyse-trading.*
