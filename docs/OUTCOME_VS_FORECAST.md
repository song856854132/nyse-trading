# Outcome-vs-Forecast Tracker

**Purpose:** Compare every pre-registered forecast against the realized outcome. One row per
prediction. This is a living document — regenerated automatically by
`scripts/generate_outcome_tracker.py` from `research.duckdb` (pre-live) and `live.duckdb`
(post-live). Manual edits are preserved in the **Notes** column only; everything else is
overwritten on regeneration.

**Why this artifact exists:** Most backtesters never compare their pre-trade forecasts to
post-trade outcomes. The distinction between a researcher and an operator is whether you
can answer "was my prior calibrated?" without motivated reasoning. A live, auto-updated
tracker forces that question every week.

**Iron rule:** A forecast is only valid if it was pre-registered BEFORE the outcome was
measured. Any row whose `forecast_date` is on or after the `outcome_date` is retroactive
and inadmissible — the table will flag those as **INADMISSIBLE**.

---

## Schema

| Column | Meaning |
|--------|---------|
| `id` | Unique string (e.g., `factor-ivol_20d-2016_2023`) |
| `forecast_date` | ISO date when the forecast was committed (written to research log or TODOS before outcome data existed in-repo) |
| `prediction_target` | What is being predicted (e.g., "ivol_20d G0-G5 verdict on 2016-2023") |
| `forecast_value` | Numeric or categorical prediction (e.g., "PASS", "Sharpe ≥ 0.30", "IC mean ≥ 0.02") |
| `forecast_source` | Document / section where the forecast was written (e.g., "plan §Factor Priority Tier 1, 2026-04-15") |
| `outcome_date` | ISO date when the outcome was measured |
| `outcome_value` | Actual realized value |
| `outcome_source` | File / artifact containing the evidence (e.g., `results/factors/ivol_20d/gate_results.json`) |
| `calibration` | `HIT` / `MISS` / `PARTIAL` / `INADMISSIBLE` |
| `error_magnitude` | Numeric error where applicable (e.g., forecast Sharpe 0.50, actual -1.92 → error = -2.42) |
| `notes` | Manually editable — root-cause hypothesis, next action, cross-references |

---

## Live Forecasts

### Pre-live (Research-period predictions vs research-period outcomes)

| id | forecast_date | prediction_target | forecast_value | forecast_source | outcome_date | outcome_value | outcome_source | calibration | error_magnitude | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| factor-ivol_20d-2016_2023 | 2026-04-15 | ivol_20d G0-G5 verdict on 2016-2023 | PASS likely (TWSE prior: strong Tier 1 factor) | plan `Factor Priority List Tier 1`, 2026-04-15 | 2026-04-18 | FAIL (G0/G1/G2/G3/G4 FAIL) | results/factors/ivol_20d/gate_results.json | MISS | OOS Sharpe −1.916 vs G0 threshold ≥ 0.30 | First real-data falsification. Low-vol winter 2016-2019 + Q1 2021 meme squeeze are leading explanations. Raw IC = +0.0213 on pre-2020 subset (sanity check passes — not a code bug). See `docs/INDEPENDENT_VALIDATION_DRAFT.md` §4. AP-6 upheld: sign NOT flipped. |
| factor-high_52w-2016_2023 | 2026-04-15 | high_52w G0-G5 verdict on 2016-2023 | PASS likely | plan `Factor Priority List Tier 1` | 2026-04-18 | FAIL (G0/G1/G2/G3/G4 FAIL) | results/factors/high_52w/gate_results.json | MISS | OOS Sharpe −1.23 vs target ≥0.3 | Disposition-effect signal inverted on 2016-2023. IC mean (−0.0055) and IC_IR (−0.023) both negative — proximity-to-52w-high anti-predicts forward returns in this window. Hypotheses: AI/mega-cap concentration (2020-2023) made "stocks near high" correlate with late-stage momentum exhaustion; COVID whipsaw broke reference-point anchoring. AP-6: sign NOT flipped. |
| factor-momentum_2_12-2016_2023 | 2026-04-15 | momentum_2_12 G0-G5 verdict on 2016-2023 | UNCERTAIN (DEAD on TWSE; may work on NYSE) | plan `Factor Priority List Tier 2` | 2026-04-18 | FAIL (G2/G3 FAIL) | results/factors/momentum_2_12/gate_results.json | MISS | IC_mean 0.0189 vs ≥0.02 (miss by 1 bp); IC_IR 0.078 vs ≥0.5 | **Borderline positive.** OOS Sharpe 0.516 (PASS), perm p=0.0020 (PASS, strong), MaxDD −28% (PASS). Signal is directionally present but noisy — IC_IR 0.08 means 6x more noise than threshold. Literally single-basis-point miss on G2. AP-6 prohibits gate loosening. Implication: momentum survives post-hoc defenses (permutation test) but not the discipline gates. Do NOT admit. Candidate combination partner later if paired with a stabilizing signal. |
| factor-piotroski-2016_2023 | 2026-04-15 | piotroski G0-G5 verdict on 2016-2023 | PASS likely | plan `Factor Priority List Tier 1` | 2026-04-18 | FAIL (G0/G2/G3 FAIL) | results/factors/piotroski/gate_results.json | MISS | OOS Sharpe 0.04 vs ≥0.3; IC mean 0.009 vs ≥0.02; IC_IR 0.089 vs ≥0.5 | EDGAR companyfacts adapter rewritten + 308,660 fact rows ingested. Signal statistically real (perm p=0.002) but economically weak — half the admission-IC threshold. AP-6 upheld. |
| factor-accruals-2016_2023 | 2026-04-15 | accruals G0-G5 verdict on 2016-2023 | PASS plausible (Tier 2 — Sloan anomaly well-documented) | plan `Factor Priority List Tier 2` | 2026-04-18 | FAIL (G2/G3 FAIL) | results/factors/accruals/gate_results.json | MISS | OOS Sharpe 0.58 PASS; IC mean 0.008 vs ≥0.02; IC_IR 0.062 vs ≥0.5 | Long-short Sharpe clears G0 but per-name ranking signal weak. Pattern matches piotroski: real info, sub-threshold magnitude. Collins-Hribar OANCF-NI proxy used. |
| factor-profitability-2016_2023 | 2026-04-15 | profitability (Novy-Marx) G0-G5 verdict on 2016-2023 | PASS plausible (Tier 2) | plan `Factor Priority List Tier 2` | 2026-04-18 | FAIL (G2/G3 FAIL) | results/factors/profitability/gate_results.json | MISS | OOS Sharpe 1.15 PASS; IC mean 0.016 vs ≥0.02; IC_IR 0.113 vs ≥0.5 | Strongest of the six factors screened: long-short Sharpe 1.15, MaxDD only -19%, perm p=0.002. Still rejected under G2/G3. Gross-profits-to-assets proxy. |
| ensemble-oos_sharpe-2016_2023 | 2026-04-15 | Ensemble OOS Sharpe on research period | 0.5 - 0.8 (Phase 3 exit target) | plan Build Phase 3 target | 2026-04-18 | UNBUILDABLE (0/6 factors admitted) | — | MISS | n/a | 6 Tier 1+2 factors screened; 0 passed G0-G5. Ensemble cannot be constructed without admitted factors. See "Pattern observation" section below. Phase 3 target at risk. |
| ensemble-oos_sharpe-final | 2026-04-15 | Final ensemble OOS Sharpe after Phase 4 optimization | 0.8 - 1.2 | plan Build Phase 4 target | — | not yet run | — | PENDING | — | Blocked behind Phase 3 completion. |
| holdout-sharpe-2024_2025 | 2026-04-15 | Holdout Sharpe on 2024-2025 | > 0 (any positive OOS Sharpe admits to paper; < 0 STOPS) | plan Statistical Validation Suite step 8 | — | not yet run | — | PENDING | — | **DO NOT touch until all 8 preconditions pass.** See `results/holdout/.holdout_used` lockfile absence. |

### Predicted Sharpe Range vs Realized Sharpe — Per-Failed-Factor Summary (RALPH TODO-22)

> Source of predicted ranges: the NYSE ATS plan (`/home/song856854132/.claude/plans/dreamy-riding-quasar.md`
> §"Factor Priority List for NYSE" Tier 1 + Tier 2 priors) combined with the G0 admission
> threshold in `config/gates.yaml:10` (`oos_sharpe >= 0.30`) and the Phase 3 ensemble target
> (`OOS Sharpe 0.5 - 0.8`). "Realized Sharpe" is the long-short quintile OOS Sharpe loaded
> directly from `results/factors/<name>/gate_results.json` → `gate_metrics.G0_value`. All
> realized numbers are RESEARCH-period only (2016-2023); iron rule 1 holds (holdout untouched).
> AP-6 holds: no threshold in `config/gates.yaml` was edited after these results were observed.

| Factor | Tier / Prior | Predicted Sharpe range | Realized Sharpe | Delta vs lower bound | Calibration |
|---|---|---:|---:|---:|:---:|
| ivol_20d | Tier 1 — "PASS likely" (TWSE lottery-demand prior) | [0.30, 0.80] | −1.916 | −2.22 | MISS |
| high_52w | Tier 1 — "PASS likely" (disposition-effect prior) | [0.30, 0.80] | −1.229 | −1.53 | MISS |
| piotroski | Tier 1 — "PASS likely" (F-score underreaction prior) | [0.30, 0.80] | 0.039 | −0.26 | MISS |
| momentum_2_12 | Tier 2 — "UNCERTAIN" (DEAD on TWSE) | [−0.10, 0.50] | 0.516 | +0.62 | MISS (G2/G3) |
| accruals | Tier 2 — "PASS plausible" (Sloan anomaly) | [0.30, 0.50] | 0.577 | +0.28 | MISS (G2/G3) |
| profitability | Tier 2 — "PASS plausible" (Novy-Marx) | [0.30, 0.50] | 1.148 | +0.85 | MISS (G2/G3) |

**Reading the table.** Three factors (`ivol_20d`, `high_52w`, `piotroski`) failed G0 itself —
their long-short Sharpe came in *below* the admission threshold, sometimes by 2σ. Three
factors (`momentum_2_12`, `accruals`, `profitability`) cleared G0 — two by a substantial
margin — but still failed the ensemble because G2 (IC mean ≥ 0.02) or G3 (IC_IR ≥ 0.5)
fell short. This is the single most important pattern in the 6-of-6 result: **long-short
Sharpe alone is not a sufficient statistic for admission.** A factor can earn a respectable
portfolio Sharpe while having per-name ranking noise too high for stable ensemble
contribution. G2/G3 are the gates that caught it. AP-6 prohibits weakening either
threshold to rescue any of these three factors; any proposal to revisit belongs in a
pre-registered variant with a distinct friction hypothesis (see TODO-23 treatment of
regime-conditional ivol for the canonical example).

**Ensemble implication.** The Phase 3 target of OOS Sharpe 0.5-0.8 at the ensemble layer
is unreachable as long as 0 of 6 factors have been admitted. The
`ensemble-oos_sharpe-2016_2023` row in the Pre-live table above resolves `UNBUILDABLE`
against that target. No further factor screens run in this loop per iron rule 7.

---

### Live forecasts (post-paper / post-live)

**(empty — no paper or live trades have been submitted)**

Once paper trading begins, each weekly rebalance generates one forecast row per held
position: forecast 5-day return = Ridge-combined score × (OOS standard deviation),
outcome = realized 5-day return. These rows will be inserted automatically by
`scripts/generate_outcome_tracker.py --mode live`.

---

## Calibration Summary (auto-generated; overwritten on regeneration)

```
CALIBRATION SUMMARY — generated 2026-04-18 (fundamental factor screen)
═══════════════════════════════════════════════════════════
Pre-live predictions             9
  HIT                            0
  MISS                           7   (6 factors + 1 ensemble-unbuildable)
  PARTIAL                        0
  INADMISSIBLE                   0
  PENDING                        2   (Phase 4 target, holdout)

Live predictions                 0

Brier score (HIT/MISS only)      1.00  (7 MISS / 7 resolved)
═══════════════════════════════════════════════════════════
```

Brier score interpretation:
- 0.00 — every prediction exactly calibrated
- 0.25 — random guessing on binary predictions
- 1.00 — every prediction maximally wrong

7/7 MISS is **itself** an informative signal: the plan's priors about which factors would
pass were systematically too optimistic relative to what 2016-2023 NYSE actually delivers.
The plan was authored on the assumption that canonical factor anomalies port cleanly from
academic literature + TWSE priors to this window. They don't. This is calibration data,
not evidence of a bug. n=7 is not yet enough for a quantitative calibration curve; target
n ≥ 10 resolved predictions before fitting a forecaster-skill regression.

### Why two Brier numbers exist (methodology note)

Readers comparing this tracker's **1.00** against `CALIBRATION_TRACKER.md`'s **0.61** will
notice the gap. Both are correct — they answer different questions:

| Scoring rule | Where | Forecast encoding | Outcome encoding | Value |
|---|---|---|---|---|
| **Pure 0/1 (hard verdict)** | This file, auto-generated | forecast_i = 1 (any non-PENDING prediction is treated as "PASS asserted") | outcome_i ∈ {0, 1} | **1.00** |
| **Probability-bucketed (soft verdict)** | `CALIBRATION_TRACKER.md` | forecast_prob_i ∈ {0.25, 0.5, 0.65, 0.75} from `forecast_value` wording | outcome_i ∈ {0, 1} | **0.61** |

The pure-0/1 view answers *"of the predictions the forecaster committed to, how many
landed?"* — it is the strongest form of accountability and is what a lay reviewer
(e.g., LP DDQ row "did your last N factor calls pass?") expects. The probability-bucketed
view answers *"given the hedge words the forecaster actually used (`PASS likely`,
`PASS plausible`, `UNCERTAIN`), is the forecaster better than a maximum-entropy prior?"*
— it is the proper scoring rule for calibration-curve construction at n ≥ 10.

Both are preserved. Auto-regeneration overwrites the 1.00 figure only. The 0.61 figure is
hand-maintained in `CALIBRATION_TRACKER.md` and is the canonical input to
`ABANDONMENT_CRITERIA.md` A10 (which triggers at Brier ≥ 0.55 at n ≥ 10 under the
probability-bucketed rule, because that is the rule the researcher's priors were
originally stated in). Do **not** substitute one for the other in governance decisions —
the threshold is rule-specific.

---

## Notes on MISS: factor-ivol_20d-2016_2023 (2026-04-17)

**Forecast (pre-registered 2026-04-15):** ivol_20d would PASS G0-G5 on 2016-2023 with
IC_mean ≥ 0.02 and OOS Sharpe ≥ 0.30. Rationale: TWSE data (different market, different
period) had strong IVOL premium; academic literature (Ang-Hodrick-Xing-Zhang 2006)
confirms the cross-sectional anomaly on US equities for 1963-2000.

**Outcome (2026-04-17):** ivol_20d FAILED all of G0-G4. G5 passed but is a degenerate
"first factor in empty ensemble" sentinel, not evidence.

| Gate | Forecast | Actual | Δ |
|------|----------|--------|---|
| G0 OOS Sharpe ≥ 0.30 | expected ≥ 0.30 | -1.92 | -2.22 |
| G1 permutation p < 0.05 | expected < 0.05 | 1.00 | +0.95 |
| G2 IC mean ≥ 0.02 | expected ≥ 0.02 | -0.008 | -0.028 |
| G3 IC IR ≥ 0.50 | expected ≥ 0.50 | -0.055 | -0.555 |
| G4 MaxDD ≥ -0.30 | expected ≥ -0.30 | -0.578 | -0.278 |
| G5 Marginal contribution > 0 | expected > 0 | passes (sentinel) | n/a |

**Leading hypotheses (ordered by evidence):**

1. **Low-vol winter 2016-2019** — QE-driven risk-on, growth-led market; high-IVOL stocks
   (often high-beta growth) rallied. This reverses the sign on the anomaly during that
   window.
2. **Q1 2021 meme-stock squeeze** — GME, AMC, BBBY, etc. had extreme idiosyncratic
   vol AND extreme realized returns. In a long-IVOL-low-rank strategy, being
   underweight these would have driven large negative excess returns.
3. **Sample-specific drift** — the factor's 2020-2022 behavior may represent structural
   shift (retail options flow, passive-flows concentration) rather than a temporary
   regime.

**Sanity check (performed 2026-04-17):** Raw (unranked) IC on pre-2020 sub-sample =
**+0.0213** with 51.7% positive weekly IC — confirms the factor has directional signal
in quieter regimes. The full-period G0-G4 failure is a time-variation problem, not a
code or sign-convention bug.

**AP-6 compliance confirmed:** The sign in `scripts/screen_factor.py` was NOT flipped
after observing the inversion. The plan's sign convention (`IVOL sign = -1` → invert →
low raw IVOL = high rank = buy) remains unchanged.

**Next actions (cross-linked):**
- TODO-23 — evaluate a regime-conditional ivol variant (IVOL × SMA-200 indicator)
- Independent Validation §8 reviewer action item #3 — "ivol disposition: keep, variant, or drop"
- Continue screening high_52w + momentum_2_12 before deciding ensemble composition (TODO-24)

---

## Notes on investigation: ivol_20d regime stratification (2026-04-18)

**Investigation ID:** `ivol_20d_regime_stratified_ic`
**Artifact:** `results/investigations/ivol_regime_2026-04-18.json`
**Research log event:** `investigation_finding` (see chain tip at time of commit)

**Motivation.** Leading hypothesis #1 above claimed "low-vol winter 2016-2019" flipped the
sign on the anomaly. The investigation tests that claim by stratifying weekly IC on three
axes: (a) pre-2020 vs post-2020, (b) SMA-200 bull vs bear on the cap-weighted market
proxy, (c) year-by-year. **No new factor was created.** This is evidence-gathering for
the TODO-23 decision, not a post-hoc sign change.

**Key results (n = 412 weekly IC observations, 2016-01-01 → 2023-12-31):**

| Split | IC mean | n | % weeks positive |
|-------|--------:|--:|-----------------:|
| All weeks | -0.0079 | 412 | 48.3% |
| Pre-2020 | -0.0071 | 205 | 48.3% |
| Post-2020 | -0.0087 | 207 | 48.3% |
| **Bull regime (SMA-200 on)** | **-0.0010** | **296** | **51.0%** |
| **Bear regime (SMA-200 off)** | **-0.0342** | **104** | **47.1%** |

| Year | n | IC mean | % positive |
|-----:|--:|--------:|-----------:|
| 2016 | 49 | -0.0230 | 44.9% |
| 2017 | 52 | -0.0044 | 42.3% |
| 2018 | 52 | -0.0026 | 51.9% |
| 2019 | 52 | **+0.0007** | 53.8% |
| 2020 | 52 | **+0.0129** | 61.5% |
| 2021 | 53 | **+0.0030** | 52.8% |
| 2022 | 52 | -0.0229 | 48.1% |
| 2023 | 50 | -0.0287 | 44.0% |

**What the evidence actually says (and does not say):**

1. **The "low-vol winter" hypothesis is only partly right.** The 2019-2021 window has
   positive mean IC, consistent with the hypothesis. But 2016-2018 are strongly negative,
   not positive — so "2016-2019 as a single quiet regime" doesn't match. The real story
   is narrower: IVOL had a working window roughly 2019-2021.
2. **Pre-2020 vs post-2020 difference is ~zero** (-0.0071 vs -0.0087). The "structural
   break in 2020" framing in the original MISS notes is not supported by the data.
3. **Regime (SMA-200) is the strongest axis of variation.** Bull-regime IC ≈ 0 (no
   signal, not a reliable anti-signal), bear-regime IC = -0.0342 (strong anti-signal).
   Bear weeks destroy the factor's average IC disproportionately: 25% of the sample
   drives most of the negative mean.
4. **Year-level dispersion is wide.** Best year (2020: +0.0129) vs worst year (2023:
   -0.0287) is a 4-percentage-point swing in IC. Any variant built on this factor must
   survive strong year-over-year non-stationarity.

**Implications for TODO-23 (regime-conditional IVOL):**

- The regime story has a real signal in the data (bull IC ≈ 0 vs bear IC = -0.0342). A
  naïve "only trade IVOL when SMA-200 on SPY is bullish" variant would sit on IC ≈ 0
  during its active window — no premium, no anti-premium. That's not a viable factor.
- The more interesting variant is **inverting the sign in bear regimes** (long high-IVOL
  when market is in a drawdown), since bear-regime IC is strongly negative and therefore
  strongly tradeable with inverted sign. But that is essentially a crisis-period
  short-volatility exposure with a different risk profile than what was originally
  pre-registered as an IVOL anomaly strategy.
- **AP-6 constraint:** Any regime-conditional variant must be pre-registered as a FRESH
  forecast entry (new forecast ID, new pre-run entry in Live Forecasts table) before
  being screened. Re-screening the current factor with a regime filter and counting that
  as the same forecast would be a retroactive narrative fit — explicitly forbidden by
  AP-6.

**Decision logged, not taken:** the evidence is archived; the construct/reject decision
on the regime-conditional variant is deferred until at least two of (piotroski,
earnings_surprise, accruals, profitability) complete gate evaluation. This avoids
building around a price/volume factor while fundamental data is still pending.

---

## Notes on MISS: factor-high_52w-2016_2023 (2026-04-18)

**Forecast (pre-registered 2026-04-15):** high_52w would PASS on 2016-2023. Rationale:
disposition-effect + reference-point anchoring is one of the most robust cross-sectional
anomalies on US equities (George-Hwang 2004, well-documented across 40+ years).

**Outcome (2026-04-18):** FAILED G0-G4. Sign of signal has inverted.

| Gate | Forecast | Actual | Δ |
|------|----------|--------|---|
| G0 OOS Sharpe ≥ 0.30 | expected ≥ 0.30 | −1.23 | −1.53 |
| G1 permutation p < 0.05 | expected < 0.05 | 1.00 | +0.95 |
| G2 IC mean ≥ 0.02 | expected ≥ 0.02 | −0.0055 | −0.0255 |
| G3 IC IR ≥ 0.50 | expected ≥ 0.50 | −0.023 | −0.523 |
| G4 MaxDD ≥ −0.30 | expected ≥ −0.30 | −0.607 | −0.307 |

**Candidate explanations:**
1. Same regime story as ivol — 2020-2023 AI/mega-cap concentration era made "stocks
   near 52w high" a continuation-of-exhaustion signal, not a continuation-of-strength
   signal.
2. Passive flows mechanically lift index constituents toward highs regardless of
   fundamentals — the anchoring premise weakens when price is set by index rebalance.

**AP-6 upheld:** sign NOT flipped.

---

## Notes on MISS: factor-momentum_2_12-2016_2023 (2026-04-18)

**Forecast (pre-registered 2026-04-15):** UNCERTAIN — momentum was DEAD on TWSE but
plan hypothesized it might WORK on NYSE. No strong directional prior.

**Outcome (2026-04-18):** FAIL **but borderline.** Signal IS directionally present; gate
system correctly rejected because the IC is too noisy to be useful in an ensemble.

| Gate | Forecast | Actual | Δ |
|------|----------|--------|---|
| G0 OOS Sharpe ≥ 0.30 | — | **0.516** | PASS |
| G1 permutation p < 0.05 | — | **0.0020** | PASS (strong) |
| G2 IC mean ≥ 0.02 | — | 0.0189 | FAIL (by 0.0011 — 1 bp) |
| G3 IC IR ≥ 0.50 | — | 0.0777 | FAIL (6× below threshold) |
| G4 MaxDD ≥ −0.30 | — | −0.283 | PASS |

**Interpretation:** momentum has a small positive edge in this window, but the per-period
variance is so large that it cannot carry itself through G3. Any attempt to loosen G2 from
0.02 → 0.018 to "admit" momentum would (a) violate AP-6, (b) overfit to this specific
factor's miss-by-one-basis-point, (c) open the door to the same gate loosening for every
subsequent factor.

**Do NOT admit.** Candidate role for later: combination partner with a stabilizing signal
(e.g., earnings-quality factor, if piotroski passes) where the two can co-average noise.
This must be validated through the same G0-G5 pipeline applied to the combined signal,
not by implicit admission via ensembling.

**AP-6 upheld:** gates NOT loosened.

---

## Notes on MISS: factor-piotroski / accruals / profitability (2026-04-18, fundamental screen)

**Context.** After the EDGAR companyfacts adapter was rewritten and 308,660 XBRL fact rows
were ingested for all 503 S&P 500 current constituents (survivorship-biased; see
`universe._resolve_universe` docstring), three fundamental factors were screened through
G0-G5 in order: piotroski (F-score, 9 binary signals), accruals (Collins-Hribar style,
`OANCF - NI` excess proxy), profitability (Novy-Marx gross-profits-to-assets).

**Aggregate outcome.**

| Factor | OOS Sharpe (G0) | Perm p (G1) | IC mean (G2) | IC_IR (G3) | MaxDD (G4) | Verdict |
|---|---:|---:|---:|---:|---:|---|
| piotroski | 0.039 | 0.0020 | 0.0090 | 0.089 | -0.216 | FAIL |
| accruals | 0.577 | 0.0020 | 0.0080 | 0.062 | -0.272 | FAIL |
| profitability | **1.148** | 0.0020 | 0.0158 | 0.113 | -0.190 | FAIL |

All three share an identical gate-failure pattern: **G1 PASS + G2 FAIL + G3 FAIL**. The
signals are statistically distinguishable from noise (permutation p=0.002 on 500 reps is
near the minimum achievable at that rep count), but the cross-sectional IC is
approximately half the admission floor and the IC-IR is 4-8x below the G3 threshold of 0.5.

**What this means concretely.** The factors are not random garbage. On a long-short
equal-weight portfolio, profitability earns a Sharpe of 1.15 with a -19% max drawdown
over 8 years on 503 names. That is a real economic result. But:

1. The information is diffuse — most of the Sharpe comes from the tails of the cross-section
   (top and bottom deciles), while middle deciles carry noise. Per-name ranking IC is only
   0.01-0.02, meaning the signal is much closer to "I know which decile a stock is in" than
   "I know how to rank these 500 stocks."
2. In an ensemble constructed via cross-sectional Ridge on rank-percentile features, that
   diffuseness matters: the model needs per-name signal, not decile-level signal.
3. Transaction costs eat the portfolio-level edge in a weekly rebalance if IC is this low —
   the 1.15 long-short Sharpe is gross, not net of 15bps one-way.

**Gate threshold discrepancy (documented, not resolved).** The plan document at line
`gates.yaml G1_standalone` specifies `ic_ir >= 0.02`, but the live `config/gates.yaml`
file carries `ic_ir >= 0.5`. The 0.5 threshold is materially stricter than academic
norms (most production cross-sectional factors have IC-IR in 0.1-0.3 range; 0.5 is
elite-tier). **Per AP-6, the threshold is NOT changed post-hoc after observing failures.**
The discrepancy is documented here; any threshold change must be pre-registered with
a written rationale, signed with a new research-log entry, and dated before the next
re-screen. If the plan's 0.02 was the intended value and the gates.yaml 0.5 was a
transcription error, the correction itself is a pre-registration event and all re-screened
results must carry that provenance.

**Why this is not "relax the gates":** the current gates are working by design. A factor
system that admits IC 0.01 / IC-IR 0.1 signals into a weekly-rebalance ensemble will
produce a net-negative strategy after costs. The gates are correctly blocking that. If
the plan's thresholds were the intended binding values, there is still reason to
investigate **why these factors are so weak in this period** — the answer is the
pattern observation below.

**AP-6 compliance confirmed:** sign conventions NOT flipped; thresholds NOT altered.

---

## Pattern observation: 3/3 price-volume Tier-1 factors have failed the 2016-2023 research period (2026-04-18)

With ivol_20d, high_52w, and momentum_2_12 all failing (or borderline failing), the
2016-2023 research period is hostile to classic price-volume cross-sectional factors.
This is **not** a surprise relative to the broader literature:

- Multiple academic papers (2019+) document the "factor zoo" premia compressing or
  disappearing post-publication.
- The 2020-2023 window contains three regime-distorting events: COVID crash (Mar 2020),
  2020-2021 retail/meme squeeze, 2022 rates shock. All three disproportionately damage
  price-volume signals that rely on behavioral anchoring or low-frequency information
  diffusion.
- TWSE predecessor system had a different market-microstructure mix (retail-dominant, no
  passive flows at scale, no options on individual names) — premium strength is not
  portable by default.

**What this does NOT mean:**
- It does NOT mean "the factor is dead" — raw IC is positive on pre-2020 subsets for ivol
  and momentum, so signal exists; it is time-varying.
- It does NOT mean "relax the gates." The gates are working: they correctly identify
  that this research period is hostile and that blindly deploying these factors would
  hurt.

**Implication for Phase 3:**
- Fundamental signals (piotroski, accruals, profitability) are now the critical path.
  These have different exposures and different regime behavior; no presumption they will
  also fail.
- Until fundamental signals are screened, the ensemble-OOS-Sharpe forecast (0.5-0.8)
  is at risk; if fundamentals also fail, Phase 3 target needs renegotiation, not
  gate loosening.
- Regime-conditioning (TODO-23) should be explored as an explicit, pre-registered
  variant, not as a retroactive save for failing factors.

**Written 2026-04-18 after completing TODO-24 (high_52w + momentum_2_12 screens).**

---

## Pattern observation (update): 6/6 Tier-1+2 factors have failed 2016-2023 (2026-04-18, post-fundamental)

After screening piotroski, accruals, profitability through G0-G5 on real EDGAR data, the
research record now reads: **0 factors admitted out of 6 attempted** (ivol_20d, high_52w,
momentum_2_12, piotroski, accruals, profitability). The fundamental screen confirms what
the price-volume screen suggested: the 2016-2023 NYSE window is adversarial to canonical
cross-sectional factor strategies **and** the gates are correctly rejecting sub-floor signals.

**Three-way split of the failure modes:**

1. **Signal present but magnitude sub-floor (fundamentals)** — piotroski, accruals,
   profitability all show p=0.002 permutation significance and (for accruals/profitability)
   G0-passing long-short Sharpes, but cross-sectional IC is 0.008-0.016 vs 0.02 threshold.
   These are factors that "work a little" but not enough to carry their weight after costs.
2. **Signal directionally inverted (price-volume)** — ivol_20d and high_52w have negative
   OOS Sharpes; the posited behavioral anchoring stories inverted during this window.
3. **Signal present but too noisy to admit (momentum_2_12)** — positive Sharpe 0.52 and
   p=0.002 but IC-IR 0.08 vs 0.5 threshold. Borderline; correctly rejected.

**Implication for Phase 3 target (OOS Sharpe 0.5-0.8):** **unbuildable on current factor
set.** The plan's Phase 3 exit gate requires an ensemble; 0 admitted factors means no
ensemble exists to measure. This is a formal MISS on the Phase 3 forecast, now resolved
in the Live Forecasts table above.

**Paths forward (each requires pre-registration before re-screening):**

A. **Tier 3 factors not yet attempted.** Earnings surprise (requires I/B/E/S or proxy),
   short interest (FINRA adapter built but not screened), sentiment/options flow, NLP
   earnings transcripts. Any of these may carry the uncorrelated signal the current six
   lack. Estimated cost: 2-4 weeks of adapter + feature work per factor.

B. **Regime-conditional variants.** The ivol regime investigation (2026-04-18 above)
   showed bull-regime IC ≈ 0 vs bear-regime IC = -0.034. A regime-conditional IVOL
   sign-flip variant is economically plausible and AP-6-permissible if pre-registered
   as a fresh forecast. Same structural argument applies to momentum (2-12) sub-regimes.

C. **Longer horizons.** All screening ran on 5-day forward returns per plan primary target.
   The plan also specifies a secondary 20-day horizon target. Fundamental factors in
   particular often show stronger IC at quarterly/annual horizons — 5-day is the worst
   horizon for quality signals to express.

D. **Threshold pre-registration review.** If `gates.yaml G3=0.5` was a transcription error
   (plan doc says 0.02), a documented correction would move accruals/profitability from
   MISS to PASS. This is **only admissible** if the plan document's 0.02 was the genuine
   original intent; it must be pre-registered as a plan-level correction (new research
   log entry with "correction" event type, diff of the config change, and an explicit
   statement that no new screening results are being used to motivate the change).

E. **Renegotiate Phase 3 target.** If the research period is structurally hostile, the
   honest move is to lower the Phase 3 exit Sharpe target from 0.5-0.8 to "any factor
   passes G0-G5" and accept that this implies a longer timeline. This is not "giving up";
   it is calibrating to what the data actually supports.

**Recommended next action (not yet taken):** run path C (20-day forward-return re-screen
on the three fundamental factors). Cost: ~1 hour of compute. Decision gate: if
profitability's IC-IR at 20d exceeds 0.5, we have our first admitted factor. If it
doesn't, we know 5-day is not the reason fundamentals are failing.

**AP-6 posture:** all five paths above are pre-registration-requiring changes. None
permit re-screening on already-observed data without a logged fresh forecast.

**Written 2026-04-18 immediately after the fundamental screen.**

---

## How this document is generated

```
scripts/generate_outcome_tracker.py \
  --mode pre-live \
  --research-db research.duckdb \
  --results-dir results/ \
  --output docs/OUTCOME_VS_FORECAST.md
```

The generator:
1. Reads all pre-registered forecasts from `results/research_log.jsonl` (event type `forecast`).
2. Reads all outcome artifacts from `results/factors/*/gate_results.json`, `results/backtests/*/backtest_result.json`, `results/holdout/holdout_result.json`.
3. Cross-matches by `prediction_target`.
4. Re-emits the table above.
5. Preserves the `notes` column from any prior version of this file (matched by `id`).

Post-live, the generator also reads `live.duckdb` for per-position forecast/outcome pairs.

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Seed document. First resolved forecast: ivol_20d MISS. Six pre-live forecasts remain pending. |

---

**Document owner:** Operator
**Update cadence:** Auto-generated on every `/document-release` cycle; manual notes preserved.
**Related:** `docs/INDEPENDENT_VALIDATION_DRAFT.md` §4, `docs/NYSE_ALPHA_RESEARCH_RECORD.md` Phase 3, `docs/TODOS.md` TODO-23/24, `results/research_log.jsonl`.
