# iter-14 Stream 2 — Coverage Matrix & Pairwise Jaccard

> **Stream ID:** `iter14_stream2_coverage`
> **Charter ref:** `docs/audit/wave_d_diagnostic_charter.md` §2 Stream 2
> **AP-6 posture:** observational. No threshold, direction, metric, or admission
> decision is modified here.
> **Source artefacts:**
>   - `results/diagnostics/iter14_coverage/coverage_matrix.csv` (2407 `(date, factor)` rows)
>   - `results/diagnostics/iter14_coverage/pairwise_jaccard.csv` (6×6 matrix)
>   - `results/diagnostics/iter14_coverage/summary.json`

## 1. What this stream measures

For each rebalance date `d` and each factor `f`, count the S&P 500-universe
symbols that have a non-NaN factor score on `d`. Divide by the universe size
on `d`. This produces a `(date, factor, n_covered, universe_size, coverage_pct)`
long-format panel — the **coverage matrix**.

For each pair `(f₁, f₂)` compute a **Jaccard index** on the set of
`(date, symbol)` cells where both factors are non-NaN, normalized by the
union. This produces a symmetric 6×6 matrix.

No metric is recomputed, no factor is re-screened. This stream measures
the overlap structure of the existing score panels.

## 2. Per-factor mean coverage

Mean `coverage_pct` across 415 rebalance dates:

| Factor | Mean coverage | Tier |
|---|---|---|
| `ivol_20d` | **99.95%** | high |
| `52w_high_proximity` | **99.32%** | high |
| `momentum_2_12` | **99.16%** | high |
| `piotroski_f_score` | **97.18%** | high |
| `profitability` | **57.57%** | low |
| `accruals` | **35.18%** | low |

Coverage bifurcates cleanly: four price/volume-derived factors cover
≥97% of the universe; two fundamentals-derived factors cover 35–58%.

## 3. Pairwise Jaccard index (off-diagonal)

```
                 52w     acc     ivol    mom     pio     pro
52w_high       [1.00]   0.350   0.994   0.998   0.957   0.569
accruals        0.350  [1.00]   0.346   0.356   0.362   0.281
ivol_20d        0.994   0.346  [1.00]   0.992   0.952   0.563
momentum_2_12   0.998   0.356   0.992  [1.00]   0.956   0.569
piotroski       0.957   0.362   0.952   0.956  [1.00]   0.593
profitability   0.569   0.281   0.563   0.569   0.593  [1.00]
```

Summary (off-diagonal):

| Statistic | Value |
|---|---|
| max Jaccard | **0.998** (52w_high ↔ momentum_2_12) |
| min Jaccard | **0.281** (accruals ↔ profitability) |

## 4. Observational implications (not admission decisions)

1. **Two coverage clusters.** The four price/volume factors form a near-
   identity coverage cluster (pairwise Jaccard 0.95–0.998). The two
   fundamentals-derived factors (accruals, profitability) pair with the
   price cluster at Jaccard 0.28–0.59 and with each other at 0.281.
2. **Renormalization bias is load-bearing.** The aggregator at
   `src/nyse_core/factor_screening.py` (per-`(date, symbol)` renormalization
   across present scores) will assign heterogeneous effective weights: a
   stock with only ivol present receives the same per-`(date,symbol)`
   weight as a stock with all 6 present. The ~65% of `(date, symbol)` cells
   without accruals coverage and ~42% of cells without profitability
   coverage are renormalized away rather than down-weighted.
3. **Coverage is dated.** Mean coverage is a cross-date statistic; the
   coverage matrix preserves the per-date values for iter-15 to use in
   construction-grammar design (e.g. a coverage-weighted aggregator).

## 5. What this stream does NOT establish

- This stream does **not** propose a coverage threshold (e.g. "drop factors
  below 50% coverage"). That would be an admission-style decision and is
  outside Wave D scope.
- This stream does **not** propose a coverage-weighted aggregator. iter-15
  will pre-register whatever construction grammar it chooses before any
  re-screening.
- Jaccard at the `(date, symbol)` level is not a direct substitute for IC
  correlation — see iter-14 Stream 3 for that.
