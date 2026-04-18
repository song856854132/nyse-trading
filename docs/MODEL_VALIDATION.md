# Model Validation Report

**NYSE Cross-Sectional Alpha | v0.1 | April 2026**

> **Purpose.** Independent validation report aligned with the Federal Reserve's
> SR 11-7 model risk management framework. This document is distinct from
> `NYSE_ALPHA_RESEARCH_RECORD.md` (development log, by the developer) and
> `NYSE_ALPHA_TECHNICAL_BRIEF.md` (strategy description, for stakeholders).
> This document audits the model *as a model*: its soundness, its tests, its
> outcomes on data, and its limitations.
>
> **Status.** Pre-live. No real-money deployment. The validation is partial:
> infrastructure-level checks are complete; outcomes validation awaits the
> first full real-data walk-forward run (see `docs/TODOS.md` TODO-11).

---

## 1. Scope and Audience

### Scope

| In scope | Out of scope |
|---|---|
| Ridge default combination model | GBM / Neural alternatives (gated, not promoted) |
| Cross-sectional factor pipeline (13 factors, 6 families) | Intraday signals, overnight gap strategies |
| Weekly rebalance with Friday-signal / Monday-execution timing | Continuous or intraday rebalance |
| PurgedWalkForwardCV on 2016-2023 research period | 2024-2025 holdout (reserved, one-shot) |
| G0-G5 gate system and F1-F8 falsification triggers | Downstream allocator changes not yet in config |

### Intended audience

1. **System operator** (day-to-day validator before each promotion stage).
2. **External reviewer** (CEO/engineering review cadence per `REVIEW_CHECKLIST.md`).
3. **Future allocator** (if capital external to operator is ever raised).

### Audit posture

Validator independence is partial: the operator acts as both developer and
validator. This is an acknowledged limitation. The compensating control is
that every gate, trigger, and test is codified in configuration and tests --
the validator checks the machine, not the developer's judgment. See
Section 9 for the full limitations list.

A more detailed SR 11-7-aligned validation draft — including outcomes analysis
of the first real-data factor screen (ivol_20d) — is maintained separately at
[INDEPENDENT_VALIDATION_DRAFT.md](INDEPENDENT_VALIDATION_DRAFT.md). That draft
is explicitly labeled "NOT APPROVED" and is not a substitute for third-party
review before live capital deployment.

---

## 2. Model Inventory

| Component | Module | Pure / Side-effect | Role |
|---|---|---|---|
| Factor computation | `src/nyse_core/features/*.py` | Pure | 13 factors across 6 families |
| Registry + sign convention | `src/nyse_core/features/registry.py` | Pure | Enforces AP-3 (no double-dip) |
| Normalization | `src/nyse_core/normalize.py` | Pure | Rank-percentile to [0,1] |
| Imputation | `src/nyse_core/impute.py` | Pure | Cross-sectional median, 30% drop rule |
| Combination (default) | `src/nyse_core/models/ridge_model.py` | Pure | `sklearn.linear_model.Ridge(alpha=1.0)` |
| Walk-forward CV | `src/nyse_core/cv.py` | Pure | Expanding, purged, embargoed |
| Gate system | `src/nyse_core/gates.py` | Pure | G0-G5 via `ThresholdEvaluator` |
| Statistics | `src/nyse_core/statistics.py` | Pure | Permutation, bootstrap, Romano-Wolf |
| Risk stack | `src/nyse_core/risk.py` | Pure | 10 risk layers |
| Cost model | `src/nyse_core/cost_model.py` | Pure | ADV-scaled spread + commission |
| Research pipeline | `src/nyse_core/research_pipeline.py` | Pure | End-to-end orchestrator |
| Data adapters | `src/nyse_ats/data/*.py` | Side-effect | FinMind, EDGAR, FINRA, constituency |
| Storage | `src/nyse_ats/storage/*.py` | Side-effect | DuckDB research + live |
| Execution bridge | `src/nyse_ats/execution/nautilus_bridge.py` | Side-effect | NautilusTrader TWAP |
| Drift detection | `src/nyse_core/drift.py` | Pure | 3-layer: IC, sign flip, R^2 |
| Falsification | `src/nyse_ats/monitoring/falsification.py` | Side-effect | F1-F8 runtime evaluation |

Total: 26 pure-logic modules in `nyse_core/`, plus side-effect adapters in `nyse_ats/`.

### 2.1 SR 11-7 three-component mapping

Per Federal Reserve / OCC SR 11-7 (2011-04-04), every model is defined by
three components, each of which requires independent validation evidence.
The table below maps our system to those components. This section exists
to give a third-party reviewer (AIMA DDQ §5.3, ILPA §14) a single
entry-point to the Fed framework.

| SR 11-7 component | What it is | Where it lives in this system | Validation evidence |
|---|---|---|---|
| **(1) Information input** | All data that enters the model, including assumptions and overrides | FinMind OHLCV, SEC EDGAR XBRL fundamentals, FINRA short interest, S&P 500 constituency, config YAMLs, environment variables | §4 Data Quality Validation; `scripts/validate_data.py`; PiT enforcement in `src/nyse_core/pit.py`; config Pydantic schema in `src/nyse_core/config_schema.py` |
| **(2) Processing component** | The computational core that transforms input into output | `src/nyse_core/` (26 pure-logic modules): features → normalize → impute → Ridge/GBM/Neural → allocator → risk → portfolio | §3 Conceptual Soundness; §5 Implementation Testing; 90%+ test coverage target; AP-1..AP-13 invariants enforced in code |
| **(3) Reporting output** | How the model's outputs are produced, labeled, and communicated | `TradePlan` dataclass (contracts.py), backtest results JSON, `docs/backtest_metrics.json`, `docs/OUTCOME_VS_FORECAST.md` (prediction-error tracker), `docs/QUARTERLY_LETTER_TEMPLATE.md`, Streamlit dashboard, Telegram alerts | §6 Outcomes Analysis; §7.3 Performance attribution; `attribution.py`; outcome calibration in OUTCOME_VS_FORECAST |

Each component has its own failure surface. SR 11-7 §III.5 requires all
three to be validated; failure in any one invalidates the model. The
current state of the three components on 2026-04-18:

- **(1) Input.** Real S&P 500 OHLCV + EDGAR fundamentals confirmed loaded
  (research.duckdb, 503 symbols, 2016-2023). Survivorship bias
  acknowledged in §4.3. PiT enforcement tested.
- **(2) Processing.** All 26 modules present, test coverage >90%,
  invariant tests passing. Ridge is default; GBM/Neural implemented but
  not activated (strategy_registry gate not met).
- **(3) Output.** Six factor screens produced honest FAIL verdicts on
  2016-2023 research period. `OUTCOME_VS_FORECAST.md` tracks
  prediction-calibration. Quarterly letter template drafted. No live
  trading; dashboard / Telegram paths built but idle.

**Validator verdict (2026-04-18):** Components (1) and (2) are validated
at a draft level. Component (3) is functional but sparse — there are
no live outcomes yet because no factor has been admitted. A full SR
11-7 §V.2 outcomes-analysis requires at least one admitted factor on
real data; this bar is not yet met.

---

## 3. Conceptual Soundness

### 3.1 Economic thesis

Each factor family is admitted only with a stated friction or behavioral
hypothesis. This is codified in `FactorRegistry.register(..., description=)`
and mirrored in `NYSE_ALPHA_TECHNICAL_BRIEF.md` Section 2. The validator's
check: every factor in the registry has a non-empty `description` field, and
the description names a specific market friction, not a statistical pattern.

### 3.2 Pipeline invariants (enforced as code)

| Invariant | Enforcement | Test |
|---|---|---|
| AP-1 (no full-sample decisions) | Gate evaluation runs on OOS folds only | `test_gates.py` |
| AP-3 (no factor double-dip) | `UsageDomain` enum; `DoubleDipError` raised | `test_registry.py` |
| AP-5 (no forward-fill by default) | `schema.STRICT_CALENDAR = True` | `test_pit.py` |
| AP-7 (max 5 params with <60 obs) | `cv.max_params_check()` warns | `test_cv.py` |
| AP-8 (features in [0,1] before model) | `signal_combination._validate_feature_range()` raises | `test_signal_combination.py` |
| PiT correctness | `pit.enforce_lags()` applied before every feature compute | `test_pit_no_leakage.py` (property) |
| Purge gap >= target horizon | Auto-adjusted in `cv.PurgedWalkForwardCV` | `test_purge_gap_horizon.py` (property) |
| Sign convention (high = buy) | Registry negates inverted factors before normalization | `test_registry.py` |

### 3.3 Model-selection rationale

Ridge is the default. GBM and Neural alternatives are implemented (`models/`)
and gated behind the `strategy_registry.select_best()` rule: must beat Ridge
by >= 0.1 OOS Sharpe **and** overfit ratio must be < 3.0. TWSE precedent:
Ridge overfit ratio 1.08x, LightGBM 6.9x (disqualifying). This gate has not
yet been run on real NYSE data. Validator's check: `strategy_registry.py`
implements both conditions with AND semantics, not OR.

### 3.4 Known theoretical limits

1. **Linear model only.** Ridge cannot capture factor interactions or
   nonlinear payoffs. Documented in `NYSE_ALPHA_TECHNICAL_BRIEF.md` Section 14.
2. **Equal-weight top-N.** Alpha magnitude within the selected basket is
   treated as flat. Structural cap on upside during high-dispersion regimes.
3. **Binary regime overlay.** Whipsaw risk at the SMA(200) boundary; no
   gradual exposure interpolation.
4. **No cross-sectional beta neutralization.** Portfolio beta is bounded
   [0.5, 1.5] post-hoc rather than neutralized ex-ante.

---

## 4. Data Quality Validation

### 4.1 Sources and expected lags

| Source | Data | Publication lag (enforced by `pit.py`) |
|---|---|---|
| FinMind | OHLCV, universe constituents | T+0 (end-of-day) |
| SEC EDGAR | 10-Q / 10-K fundamentals | T+45 trading days |
| FINRA | Short interest | T+11 calendar days, bi-monthly |
| Third-party (optional) | Earnings call transcripts | T+1 to T+3 |

### 4.2 Automated checks (`scripts/validate_data.py` + `data_quality.py`)

1. Coverage: >= 95% of S&P 500 constituents have OHLCV per day.
2. Staleness: no factor's most recent data exceeds `max_age` in
   `pit.enforce_lags()`. Violation -> feature goes NaN (logged).
3. Schema: all OHLCV rows satisfy `close > 0, volume >= 0, high >= low`.
4. PiT: no feature value carries a timestamp > rebalance date. Enforced by
   `test_pit_no_leakage.py` (Hypothesis property test).
5. Corporate actions: splits/dividends applied from event-sourced log before
   any feature compute. Tested in `test_corporate_actions.py`.

### 4.3 Known data risks

1. **EDGAR XBRL tag drift.** Some issuers use non-standard tag names
   (`us-gaap:Revenues` vs `us-gaap:RevenueFromContractWith...`). Coverage
   is imperfect; missing fundamentals become NaN and are handled by
   `impute.py` if < 30% cross-sectional missing.
2. **FINRA publication schedule.** Bi-monthly with T+11 lag. Factor
   staleness trigger F8 fires if lag exceeds 10 days.
3. **FinMind discontinuity.** Vendor risk. `DataAdapter` protocol allows
   swap; no replacement adapter is currently implemented (deferred).

---

## 5. Implementation Testing

### 5.1 Test inventory

| Layer | Count | Location |
|---|---|---|
| Unit | ~680 | `tests/unit/` |
| Integration | ~120 | `tests/integration/` |
| Property (Hypothesis) | ~104 | `tests/property/` |
| Skipped (optional deps: lightgbm, torch) | 30 | -- |
| **Total passing** | **934** | -- |

### 5.2 Critical path coverage

| Path | Test file | Status |
|---|---|---|
| Walk-forward backtest strict-mode | `tests/integration/test_strict_backtest.py` | 19 tests, all pass |
| Ridge singular-matrix fallback | `tests/unit/test_ridge_model.py` | Covered |
| PiT no-leakage (property) | `tests/property/test_pit_no_leakage.py` | Hypothesis 100+ examples |
| Normalization [0,1] invariant (property) | `tests/property/test_normalization_invariants.py` | Hypothesis 100+ examples |
| Sector cap enforcement (property) | `tests/property/test_sector_caps_invariant.py` | Hypothesis 100+ examples |
| Sell buffer reduces turnover (property) | `tests/property/test_sell_buffer_turnover.py` | Hypothesis 100+ examples |
| Nautilus bridge reconciliation | `tests/integration/test_nautilus_bridge.py` | Partial fill, rejection, timeout |
| Falsification trigger frozen-hash | `tests/unit/test_falsification.py` | Tamper detection covered |

### 5.3 Gaps

1. Synthetic data only in CI. Real-data backtest not yet in continuous
   integration. Manual run required (TODO-11).
2. Execution-engine integration tests use a mocked NautilusTrader broker.
   First live broker contact (paper mode) is pending.
3. No chaos / fault-injection tests for API outages beyond single-call
   retry logic. Acceptable for research; must be added before live.

---

## 6. Outcomes Analysis

### 6.1 Latest backtest snapshot (`docs/backtest_metrics.json`, **synthetic data**)

> The following numbers come from a synthetic pipeline smoke test
> (`scripts/generate_figures.py`), not from real FinMind/EDGAR/FINRA data.
> `research.duckdb` does not yet exist on disk. Numbers are therefore
> **not evidence of strategy behavior** -- they are evidence that the
> pipeline produces *some* output end-to-end. See TODO-11.


| Metric | Value | Target | Verdict |
|---|---:|---:|:---:|
| OOS Sharpe | 0.17 | 0.8 -- 1.2 | **BELOW** |
| OOS CAGR | 0.8% | 18 -- 28% | **BELOW** |
| Max drawdown | -7.4% | -15% to -25% | Within band (low-exposure artifact) |
| Annual turnover | 480% | < 50% | **WELL ABOVE** |
| Cost drag | 19.5% | < 3% | **CATASTROPHIC** |
| Mean IC | -0.015 | >= 0.02 | **NEGATIVE** |
| IC IR | -0.12 | >= 0.5 | **NEGATIVE** |
| Per-fold Sharpe range | -10.9 to +12.1 | Stable | **UNSTABLE** |

### 6.2 Honest interpretation

This snapshot is **not a validated backtest**. It is the result of an early
pipeline dry run and should not be cited as evidence of strategy viability.
Specific observations the validator must flag:

1. **Negative mean IC.** The composite signal is currently anti-predictive
   on the sample used. A real strategy with this IC should not be deployed.
2. **Negative factor weight signs on price/volume factors.** Ridge
   coefficients for `momentum_2_12` (-0.0048), `52w_high` (-0.0033),
   `ewmac` (-0.00064), and `profitability` (-0.00080) are negative after
   sign convention inversion. This is the opposite of every prior in
   `NYSE_ALPHA_TECHNICAL_BRIEF.md` Section 3. Three possible causes:
   (a) the sample is dominated by regimes where these factors inverted;
   (b) a sign-convention bug in `registry.py`; (c) data quality defect.
   Documented as TODO-10; must be resolved before promotion.
3. **480% annual turnover.** 9.6x the target ceiling. Sell buffer
   (`sell_buffer=1.5`) is configured but its effect is being overwhelmed
   -- likely because the signal is too noisy to exceed the buffer
   consistently. The 19.5% cost drag is a direct consequence.
4. **OOS period runs through 2025-08-26 -- synthetic only.** The
   synthetic generator emits dates that overlap the reserved
   2024-2025 holdout, but no real holdout data was consumed (no
   real data exists yet). No holdout violation has occurred. Validator
   must ensure the first real-data run (TODO-11) stops at 2023-12-31
   and writes an entry to `results/research_log.jsonl` before any
   holdout-era query.

### 6.3 Required actions before any further promotion

| Action | Owner | Target |
|---|---|---|
| Rerun on research period only (2016-2023) with real data | Researcher | TODO-11 |
| Confirm holdout remains untouched (audit log + db reads) | Validator | Ongoing |
| Diagnose negative factor-weight signs (data, code, or sample) | Researcher | TODO-10 |
| Re-evaluate all G0-G5 gates on corrected backtest | Validator | After TODO-11 |
| Benchmark selection: SPY vs RSP rationale | Researcher | TODO-9 |

Until these are closed, the model is **NOT VALIDATED** for any downstream stage.

---

## 7. Ongoing Monitoring Plan

### 7.1 Drift detection (from `drift.py`)

| Layer | Metric | Threshold | Action |
|---|---|---|---|
| 1 | Rolling 60-day IC mean + negative slope | < 0.015 | Retrain recommended |
| 2 | IC sign flips in trailing 2 months | > 3 | F2 VETO risk |
| 3 | Rolling R^2 of predicted vs actual portfolio returns | < 0 | Urgency elevation |

### 7.2 Falsification triggers (frozen in `config/falsification_triggers.yaml`)

Eight triggers, F1-F8, pre-registered with frozen_date 2026-04-15. The file
hash is checked at runtime to prevent silent threshold adjustment. VETO
triggers halt trading; WARNING triggers reduce exposure to 60% and require
human review within one week.

### 7.3 Performance attribution (post-deployment)

`attribution.py` decomposes portfolio returns by factor contribution using
the current Ridge coefficients. Attribution snapshots are written to
`live.duckdb` per rebalance. Review cadence: weekly (automated dashboard)
and monthly (written report).

---

## 8. Governance and Change Control

### 8.1 What is frozen

| Artifact | Frozen? | Unfreeze procedure |
|---|---|---|
| `config/falsification_triggers.yaml` | Yes (2026-04-15) | Not permitted until next full validation cycle |
| `config/gates.yaml` thresholds | Yes during validation | Requires validator + reviewer sign-off |
| Holdout window 2024-2025 | Yes | One-shot; cannot be rerun after first use |
| Factor sign conventions (`registry.py`) | Yes | Requires code review + regression test |

### 8.2 Change log

All YAML configs live in git. Every production change must ship with:
(a) a diff snapshot in the pull request, (b) a corresponding entry in
`docs/AUDIT_TRAIL.md`, (c) a regression test if the change affects a
gated threshold.

### 8.3 Promotion ladder

Stage transitions (Paper -> Shadow -> Min Live -> Scale) require all 7
graduation criteria in `config/deployment_ladder.yaml` to be satisfied.
Transitions are human-gated; there is no automatic promotion.

---

## 9. Limitations (validator's honest list)

1. **Developer and validator are the same operator.** Independence is
   procedural, not organizational.
2. **TWSE priors bias factor selection.** Ridge, rank-percentile, sell
   buffer, and binary regime were all decided before writing a line of
   NYSE code. If TWSE priors are wrong for NYSE, the defaults inherit
   that bias.
3. **Synthetic calibration only validates the pipeline, not the signal.**
   A pipeline that perfectly recovers a planted signal proves
   no-lookahead-bias; it does not prove the real signal exists.
4. **No live broker contact yet.** Execution mechanics (fill quality,
   partial fills, order rejection) are entirely modeled, not measured.
5. **Research period 2016-2023 excludes recent regime (2024-2025).**
   Any regime-specific failure mode that only appears in the holdout
   will not be caught until the one-shot test.
6. **Cost model is parametric, not calibrated.** The ADV-scaled spread
   formula is an assumption; the true slippage surface is unobserved.

---

## 10. Validation sign-off checklist

Before the model is promoted from research to paper trading, every item
below must be checked and initialed by the validator.

- [ ] Real-data research-period backtest (2016-2023) executed and archived.
- [ ] Mean IC and IC IR positive across at least 4 of the last 5 folds.
- [ ] No factor weight sign contradicts the registered sign convention.
- [ ] Annual turnover < 50%, cost drag < 3% of gross.
- [ ] Permutation p-value < 0.05 (500 reps), bootstrap CI lower bound > 0.
- [ ] All G0-G5 gates PASS on final factor ensemble.
- [ ] 934+ tests pass, no skipped tests outside optional dependencies.
- [ ] Holdout window 2024-2025 demonstrably untouched
      (audit `results/research_log.jsonl`).
- [ ] Frozen config file hashes match `falsification_triggers.yaml` pre-freeze.
- [ ] `AUDIT_TRAIL.md` reflects the state this document describes.

---

*Related: [FRAMEWORK_AND_PIPELINE.md](FRAMEWORK_AND_PIPELINE.md) (architecture) | [NYSE_ALPHA_TECHNICAL_BRIEF.md](NYSE_ALPHA_TECHNICAL_BRIEF.md) (strategy) | [NYSE_ALPHA_RESEARCH_RECORD.md](NYSE_ALPHA_RESEARCH_RECORD.md) (development log) | [MLOPS_LIFECYCLE.md](MLOPS_LIFECYCLE.md) (ops) | [AUDIT_TRAIL.md](AUDIT_TRAIL.md) (change log)*
