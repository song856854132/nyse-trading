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
| factor-ivol_20d-2016_2023 | 2026-04-15 | ivol_20d G0-G5 verdict on 2016-2023 | PASS likely (TWSE prior: strong Tier 1 factor) | plan `Factor Priority List Tier 1`, 2026-04-15; `docs/NYSE_ALPHA_RESEARCH_RECORD.md` Phase 3 table | 2026-04-17 | FAIL (G0/G1/G2/G3/G4 all FAIL; G5 sentinel PASS) | `results/factors/ivol_20d/gate_results.json` | MISS | Sharpe forecast ≥ 0.30 → actual -1.92 (Δ = -2.22). IC_mean forecast ≥ 0.02 → actual -0.008 (Δ = -0.028). | First real-data falsification. Low-vol winter 2016-2019 + Q1 2021 meme squeeze are leading explanations. Raw IC = +0.0213 on pre-2020 subset (sanity check passes — not a code bug). See `docs/INDEPENDENT_VALIDATION_DRAFT.md` §4. AP-6 upheld: sign NOT flipped. |
| factor-high_52w-2016_2023 | 2026-04-15 | high_52w G0-G5 verdict on 2016-2023 | PASS likely | plan `Factor Priority List Tier 1` | — | not yet run | — | PENDING | — | Scheduled next per TODO-24. Price-only so immediately runnable. |
| factor-momentum_2_12-2016_2023 | 2026-04-15 | momentum_2_12 G0-G5 verdict on 2016-2023 | UNCERTAIN (DEAD on TWSE; may work on NYSE) | plan `Factor Priority List Tier 2`, annotated "may WORK on NYSE" | — | not yet run | — | PENDING | — | Run after high_52w. |
| factor-piotroski-2016_2023 | 2026-04-15 | piotroski G0-G5 verdict on 2016-2023 | PASS likely | plan `Factor Priority List Tier 1` | — | not yet run (blocked on EDGAR ingestion) | — | PENDING | — | Blocked by TODO-3 (EDGAR adapter + FINRA adapter not yet wired). |
| ensemble-oos_sharpe-2016_2023 | 2026-04-15 | Ensemble OOS Sharpe on research period | 0.5 - 0.8 (Phase 3 exit target) | plan Build Phase 3 target | — | not yet run | — | PENDING | — | Requires ≥3 factors through G0-G5 first. |
| ensemble-oos_sharpe-final | 2026-04-15 | Final ensemble OOS Sharpe after Phase 4 optimization | 0.8 - 1.2 | plan Build Phase 4 target; `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md` | — | not yet run | — | PENDING | — | Blocked behind Phase 3 completion. |
| holdout-sharpe-2024_2025 | 2026-04-15 | Holdout Sharpe on 2024-2025 | > 0 (any positive OOS Sharpe admits to paper; < 0 STOPS) | plan Statistical Validation Suite step 8 | — | NOT YET RUN (holdout reserved; one-shot) | `results/holdout/` (empty) | PENDING | — | **DO NOT touch until all 8 preconditions pass.** See `results/holdout/.holdout_used` lockfile absence. |

### Live forecasts (post-paper / post-live)

**(empty — no paper or live trades have been submitted)**

Once paper trading begins, each weekly rebalance generates one forecast row per held
position: forecast 5-day return = Ridge-combined score × (OOS standard deviation),
outcome = realized 5-day return. These rows will be inserted automatically by
`scripts/generate_outcome_tracker.py --mode live`.

---

## Calibration Summary (auto-generated; overwritten on regeneration)

```
CALIBRATION SUMMARY — generated 2026-04-18
═══════════════════════════════════════════════════════════
Pre-live predictions             7
  HIT                            0
  MISS                           1  (factor-ivol_20d-2016_2023)
  PARTIAL                        0
  INADMISSIBLE                   0
  PENDING                        6

Live predictions                 0

Brier score (HIT/MISS only)      1.00  (1 MISS / 1 resolved)
═══════════════════════════════════════════════════════════
```

Brier score interpretation:
- 0.00 — every prediction exactly calibrated
- 0.25 — random guessing on binary predictions
- 1.00 — every prediction maximally wrong

With only 1 resolved prediction, this number is uninformative (n=1 is noise, not signal).
Target: revisit at n ≥ 10 resolved predictions.

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
