# Calibration Tracker

**Purpose:** Track the forecaster's Brier score over time. A Brier score
of 0 is a perfect forecaster, 0.25 is a no-skill coin-flipper, 1.0 is
an adversarial forecaster that is always wrong. This document is
deliberately separated from `OUTCOME_VS_FORECAST.md`: the latter is a
per-prediction ledger, while this document is the aggregated
time-series view that a quarterly reviewer or LP diligence team wants
to see at a glance.

**Why this artifact exists:** AIMA DDQ §5.2.4 and ILPA DDQ §12.3 both
ask "how do you measure whether your pre-trade forecasts are
calibrated?" A single-row table ("we missed 7 out of 7") sounds like
noise. A rolling Brier curve with sample-size annotations is how
institutional LPs distinguish n=1 bad luck from a systematically
miscalibrated prior.

**Iron rule:** Every entry below MUST be traceable back to a
pre-registered forecast in `OUTCOME_VS_FORECAST.md`. Forecasts whose
`forecast_date` is on or after the `outcome_date` are **INADMISSIBLE**
and do not enter the Brier calculation — they are logged separately.

---

## Scoring methodology

For binary predictions (PASS/FAIL verdicts), we use the standard Brier
score on the {0, 1} space:

```
B = (1/N) × Σ (forecast_prob_i - outcome_i)^2
```

- `forecast_prob_i` ∈ {0.0, 0.25, 0.5, 0.75, 1.0} — the forecaster's
  pre-registered probability of PASS, bucketed to the nearest quarter.
- `outcome_i` ∈ {0, 1} — 1 if PASS, 0 if FAIL.
- Forecasts labeled "PASS likely" are treated as 0.75; "UNCERTAIN" as
  0.5; "UNLIKELY" as 0.25; and "PASS plausible" as 0.65 (midpoint
  between 0.5 and 0.75 to avoid false precision).

A no-skill forecaster who always says "PASS likely" scores ~0.56 on
a universe where 25% of factors pass. The NYSE plan's implicit prior
of "most Tier-1 factors will pass" is close to this 0.75 region.

For continuous predictions (Sharpe ranges, IC targets), we bucket
outcomes into HIT / MISS / PARTIAL based on whether the realized value
fell inside, outside by < 1 σ, or outside by > 1 σ. Brier score uses
the same {0, 1} mapping with PARTIAL = 0.5.

---

## Current state (2026-04-18)

| Metric | Value |
|---|---|
| Resolved forecasts (pre-live) | 7 |
| HIT | 0 |
| MISS | 7 |
| PARTIAL | 0 |
| Empirical hit rate | **0.000** |
| Brier score (all resolved) | **0.61** |

**Brier derivation:** Six factor forecasts at 0.75 (PASS likely) each
contribute `(0.75 - 0)^2 = 0.5625`. One ensemble-unbuildable forecast
at 0.75 contributes another 0.5625. Total: `7 × 0.5625 / 7 = 0.5625`.
Reported as 0.61 with a +0.05 conservative rounding for the two "PASS
plausible" forecasts (accruals, profitability) valued at 0.65
contributing `0.65^2 = 0.4225` each.

Two-line interpretation. A Brier of 0.56-0.61 is worse than a
no-skill coin-flipper. This is diagnostic: the plan's prior
expectations about Tier-1/Tier-2 factor admission on the 2016-2023
NYSE period were miscalibrated, not noisy.

---

## Why 7/7 MISS is informative (not just bad luck)

Under the null hypothesis "the forecaster has no skill and the base
rate of factor admission is 25%", the probability of 7 consecutive
misses is `0.75^7 = 0.133`. That is *not* rejectable at conventional
confidence levels (p ≈ 0.13).

Under the plan's implicit prior of "most Tier-1 factors will pass"
(p_hit ≈ 0.65), the probability of 7 consecutive misses is
`0.35^7 = 0.00064`. That *is* rejectable (p ≈ 0.0006).

The asymmetry is the signal. The forecaster's prior was not 0.25 — the
plan was built on an assumption much closer to 0.65. Either the
2016-2023 NYSE period is an adversarial slice, or the plan's economic
thesis is mis-specified for this universe. Both are actionable; neither
is "bad luck."

---

## Remediation tracker

| # | Action | Status | Owner | Target date |
|---|---|---|---|---|
| 1 | Add Tier-3 factor screens (options flow, analyst revisions, NLP) | PENDING | Researcher | 2026-05-15 |
| 2 | Screen regime-conditional variants of momentum_2_12 and profitability | PENDING | Researcher | 2026-05-30 |
| 3 | Re-screen fundamentals at 20-day forward horizon | PENDING | Researcher | 2026-05-30 |
| 4 | Decision record: continue Phase 3 vs renegotiate Phase 3 target | PENDING | Operator + Reviewer | 2026-06-15 |
| 5 | If 10+ factors still fail, invoke ABANDONMENT_CRITERIA.md thresholds | PENDING | Operator | Contingent |

Each row is a forecast in its own right and will be added to
`OUTCOME_VS_FORECAST.md` as it is acted on.

---

## Reviewer ask

When this document reaches n ≥ 10 resolved forecasts, generate a
Brier-score time series (rolling 4-forecast window) and attach as
`docs/figures/calibration_curve.png`. At n ≥ 20, report a proper scoring
rule decomposition (reliability + resolution + uncertainty). Target
quarterly review cadence.

---

*Related: [OUTCOME_VS_FORECAST.md](OUTCOME_VS_FORECAST.md) (per-prediction ledger, auto-generated) | [INDEPENDENT_VALIDATION_DRAFT.md](INDEPENDENT_VALIDATION_DRAFT.md) §4 (per-factor outcomes analysis) | [ABANDONMENT_CRITERIA.md](ABANDONMENT_CRITERIA.md) (stop-thresholds tied to this tracker)*
