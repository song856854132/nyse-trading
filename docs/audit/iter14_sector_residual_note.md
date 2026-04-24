# iter-14 Stream 4 — Sector-Residualized `momentum_2_12` Re-Screen

> **Stream ID:** `iter14_stream4_sector_residual`
> **Charter ref:** `docs/audit/wave_d_diagnostic_charter.md` §2 Stream 4
> **AP-6 posture:** observational single-factor diagnostic under the in-force
> gate family. No threshold, direction, metric, or admission decision is
> modified. The factor's canonical admission record at
> `results/factors/momentum_2_12/gate_results.json` is **unchanged**; this
> stream produces a *variant* re-screen at a separate path for comparison.
> **Source artefact:** `results/diagnostics/iter14_sector_residual/momentum_2_12_sector_residualized.json`

## 1. What this stream measures

Re-screen `momentum_2_12` under the in-force gate family (G0–G5), but first
replace its raw rank-percentile score with the residual from a per-date
OLS regression on GICS sector dummies:

```
for each date d:
    y = momentum_2_12 raw rank-percentile scores on date d
    X = one-hot GICS sector dummies on date d
    residual = y - X @ (pinv(X.T @ X) @ (X.T @ y))
    res_score(d, :) = rank_percentile(residual)
screen_factor(factor_name="momentum_2_12", factor_scores=res_score, ...)
```

This isolates the within-sector cross-sectional momentum signal from
between-sector sector-level drift. The purpose is to answer **one specific
question**: "is the raw momentum_2_12 signal driven by stock selection
within sectors, or by sector selection?" It does not modify the factor's
canonical screening record, nor is it proposed as a new factor.

## 2. Panel-level residualization diagnostic

| Field | Value |
|---|---|
| `dates_processed` | 366 |
| `rows_in` | 173981 |
| `rows_out` | 173981 |
| `symbols_dropped_no_sector` | 0 |

The residualization preserved every row (every symbol in the panel has a
GICS sector assignment), so no ambiguity from coverage loss.

## 3. In-force gate metrics, sector-residualized vs raw

Raw metrics come from `results/factors/momentum_2_12/gate_results.json`
(the canonical screening record). Residualized metrics come from this
stream's JSON artefact.

| Metric | Raw (`gate_results.json`) | Sector-residualized | Direction of change |
|---|---|---|---|
| G0 OOS Sharpe | **+0.5164** | **+0.1808** | ↓ (reduced by 65%) |
| G1 perm p | 0.00200 | 0.00200 | unchanged |
| G2 IC mean | +0.01889 | +0.01553 | ↓ (reduced by 18%) |
| G3 IC IR | +0.07769 | +0.08074 | ↑ (trivial) |
| G4 max drawdown | −0.2827 | −0.2956 | ↓ (closer to the −0.30 floor) |
| G5 marginal contribution | 1.00 | 1.00 | unchanged (single-factor screen) |
| `verdict_passed_all` | false (canonical) | false | unchanged |

## 4. Observational implications (not admission decisions)

1. **Sector risk explains most of the raw momentum Sharpe.** The raw
   momentum_2_12 Sharpe of +0.52 collapses to +0.18 after sector
   residualization. A factor that crossed G0 under the in-force family on
   its raw rank-percentiles does **not** cross G0 (+0.18 < +0.30) after
   sector residualization.
2. **IC survives, IR is stable.** The reduction in IC mean is modest (18%)
   relative to the Sharpe reduction (65%). IC IR is essentially unchanged.
   This means the within-sector signal is still there, but the sector-
   attributable portion of the volatility-adjusted return was doing most
   of the heavy lifting.
3. **Drawdown worsens marginally.** MDD moves from −0.28 to −0.30 — the
   residualized variant sits at the G4 threshold boundary. Not a near-miss
   (G4 is still passed as `≥ −0.30` with the raw value); the residualized
   variant is at −0.296, still above the floor.
4. **iter-12's ensemble verdict is consistent.** The iter-12 equal-weight
   ensemble produced OOS Sharpe −0.12. If most of the individual-factor
   Sharpe on `momentum_2_12` is sector-attributable, and other factors
   (52w_high in particular, score-correlated at 0.548 with momentum)
   likely carry the same sector exposure, then equal-weighting without
   sector residualization aggregates sector risk with no guarantee that
   the idiosyncratic residual signal survives the blend.

## 5. What this stream does NOT establish

- This stream does **not** propose sector residualization as the v2
  construction grammar. iter-15 will make that decision explicitly.
- This stream runs only on `momentum_2_12`. Other factors' sector
  exposure is not measured in this iteration (charter §2 Stream 4 scope
  limited to a single demonstrative factor to keep AP-6 surface minimal).
- No change is made to `results/factors/momentum_2_12/gate_results.json`
  or to any admission record. The residualized metrics live at a separate
  path with a `variant: "sector_residualized"` tag.
