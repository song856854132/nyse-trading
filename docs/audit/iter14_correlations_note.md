# iter-14 Stream 3 — Pairwise Factor & Return Correlations

> **Stream ID:** `iter14_stream3_correlations`
> **Charter ref:** `docs/audit/wave_d_diagnostic_charter.md` §2 Stream 3
> **AP-6 posture:** observational. No threshold, direction, metric, or admission
> decision is modified here.
> **Source artefacts:**
>   - `results/diagnostics/iter14_correlations/factor_corr_matrix.csv` (score-level 6×6)
>   - `results/diagnostics/iter14_correlations/forward_return_corr_matrix.csv` (top-decile return 6×6)
>   - `results/diagnostics/iter14_correlations/summary.json`

## 1. What this stream measures

Two 6×6 pairwise correlation matrices over the 6-factor panel:

1. **Score correlation.** For each `(date, symbol)` with both factors
   present, Pearson correlation of the two rank-percentile scores. One
   number per pair, pooled across all dates and symbols with shared
   coverage.
2. **Top-decile return correlation.** For each date, build the top-decile
   portfolio per factor (equal-weight among the top 10% of ranked scores
   with coverage on that date), compute its 5-day forward return. Pearson
   correlation of these two return time-series per pair.

These are diagnostic — not used in any gate or admission decision.

## 2. Score correlation matrix (off-diagonal)

```
                 52w     acc     ivol    mom     pio     pro
52w_high       [1.00]   0.005   0.336  +0.548   0.124   0.077
accruals        0.005  [1.00]  -0.077   0.016   0.211   0.348
ivol_20d        0.336  -0.077  [1.00]   0.041   0.064  -0.035
momentum_2_12  +0.548   0.016   0.041  [1.00]   0.163   0.133
piotroski       0.124   0.211   0.064   0.163  [1.00]   0.300
profitability   0.077   0.348  -0.035   0.133   0.300  [1.00]
```

Summary (off-diagonal):

| Statistic | Value | Pair |
|---|---|---|
| max score correlation | **+0.548** | 52w_high ↔ momentum_2_12 |
| typical off-diagonal | 0.0–0.35 | — |
| negative | 2 pairs (ivol↔accruals, ivol↔profitability) | — |

## 3. Top-decile forward-return correlation matrix (off-diagonal)

```
                 52w     acc     ivol    mom     pio     pro
52w_high       [1.00]   0.695   0.833   0.814   0.820   0.793
accruals        0.695  [1.00]   0.801   0.759   0.850   0.850
ivol_20d        0.833   0.801  [1.00]   0.799   0.922   0.862
momentum_2_12   0.814   0.759   0.799  [1.00]   0.879   0.821
piotroski       0.820   0.850   0.922   0.879  [1.00]   0.933
profitability   0.793   0.850   0.862   0.821   0.933  [1.00]
```

Summary (off-diagonal):

| Statistic | Value | Pair |
|---|---|---|
| max return correlation | **+0.933** | piotroski ↔ profitability |
| min return correlation | +0.695 | 52w_high ↔ accruals |
| all pairs ≥ +0.70 | yes | — |

## 4. Observational implications (not admission decisions)

1. **Score-level diversification is moderate.** Off-diagonal score correlations
   cluster 0.00–0.35, with one clear pair at 0.548 (52w_high ↔ momentum_2_12).
   The score panel is not pathologically collinear.
2. **Return-level diversification is weak.** Every pair of top-decile
   portfolios has forward-return correlation ≥ 0.70, with the
   piotroski↔profitability pair at 0.933. This means the top-decile
   *portfolios* are picking largely overlapping names — the apparent
   score diversity does not translate into return-stream diversity.
3. **The gap matters.** Score correlation can underestimate return-level
   overlap because rank-based scoring within a factor still picks from the
   same universe of "low-beta / high-quality / low-vol" names. Low-ivol
   stocks also tend to be high-piotroski and high-profitability.
4. **This is a known Tulchinsky pattern.** "Orthogonalization of scores
   does not orthogonalize the portfolios; correlation should be measured
   at the decision surface, not the feature surface." (paraphrased from
   *Finding Alphas*, Ch. Orthogonalization / Crossing Effect.)

## 5. What this stream does NOT establish

- This stream does **not** prescribe a return-correlation threshold for
  admission.
- This stream does **not** propose decorrelation transforms (residualization,
  PCA) as part of a v2 construction grammar. iter-15 will pre-register any
  such transform before re-screening.
- The computed correlations are full-sample, not OOS — they are diagnostic,
  not used for any forward-looking decision.
