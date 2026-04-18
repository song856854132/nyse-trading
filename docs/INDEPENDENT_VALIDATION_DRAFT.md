# Independent Model Validation — DRAFT

**NYSE Cross-Sectional Alpha | Draft v0.1 | 2026-04-18**

> **STATUS — DRAFT. NOT APPROVED. NOT A SUBSTITUTE FOR THIRD-PARTY REVIEW.**
>
> This document is authored by the model operator (who is also the developer).
> Under SR 11-7, "effective validation framework should include three core
> elements: (i) evaluation of conceptual soundness, (ii) ongoing monitoring,
> (iii) outcomes analysis" performed with *independence from development*.
> This draft fulfills the structural requirement of having an outcomes-focused
> audit artifact; it does **not** fulfill the independence requirement. Any
> real-money deployment must be preceded by a sign-off from a validator who
> did not develop the model. See §1 (Independence Statement) and §8
> (Reviewer Action Items) for the specific handoff checklist.

---

## 1. Independence Statement (SR 11-7 §V)

| Field | Value |
|---|---|
| Developer | Operator (solo) |
| Validator (this draft) | **Same person as developer** |
| Validator independence | **Partial — self-validation with compensating controls** |
| Draft date | 2026-04-18 |
| Compensating controls | (a) All gates/thresholds codified in `config/gates.yaml` + `config/falsification_triggers.yaml`, immutable post-freeze; (b) All tests in-repo and reproducible; (c) Research log is hash-chained (`scripts/verify_research_log.py`); (d) This draft blocks real-money deployment until a third-party reviewer signs §9. |
| Planned third-party review | **Required before Shadow→Min-Live graduation.** See `TODOS.md` TODO-13. |
| Scope limitation | This draft cannot opine on the developer's judgment where judgment is not codified (e.g., decision to include momentum despite TWSE failure). Those judgments are flagged in §8. |

Honesty note. A self-validation is an interim artifact. It catches *machine*
bugs (wrong config file loaded, sign convention flipped, purge gap
misconfigured). It does *not* catch *judgment* bugs (wrong factor chosen,
wrong regime conditioning, wrong deployment timing). The latter require an
external reviewer.

---

## 2. Conceptual Soundness Review

### 2.1 Economic thesis

Each factor family is admitted to the ensemble only if the developer has
stated a specific market friction it exploits (`FactorRegistry` requires a
non-empty `description` at register time). The validator's check: the
description must name a friction, not a statistical artifact.

| Family | Friction hypothesis | Status (validator check) |
|---|---|---|
| IVOL (idiosyncratic volatility) | Retail lottery demand + short-sale constraints | PASS — hypothesis is specific, citation is Ang-Hodrick-Xing-Zhang 2006 |
| Piotroski F-score | Underreaction to fundamental quality changes | PASS — hypothesis is specific, citation is Piotroski 2000 |
| Earnings surprise | Post-earnings announcement drift from anchoring | PASS — citation is Bernard-Thomas 1989 |
| 52-week high proximity | Reference-point anchoring / disposition effect | PASS — citation is George-Hwang 2004 |
| Momentum (2-12) | Slow information diffusion | PASS — citation is Jegadeesh-Titman 1993. **Judgment concern:** TWSE precedent failed; see §8 |
| Short interest | Informed bearish flow + costly shorting | PASS — citation is Boehmer-Huszar-Jordan 2010 |
| Accruals | Earnings quality mispricing | PASS — citation is Sloan 1996 |
| Profitability | Robust risk premium | PASS — citation is Novy-Marx 2013 |

### 2.2 Data lineage

| Asset | Source | Publication lag | PiT enforcement |
|---|---|---|---|
| OHLCV | FinMind (USStockPrice) | T+0 EOD | Enforced by `pit.py`; gap detection per symbol |
| Fundamentals | SEC EDGAR (10-Q / 10-K) | T+45 days | `max_age=90` days; feature becomes NaN past max_age |
| Short interest | FINRA | T+11 days | Mid-month + end-of-month settlement dates |
| Constituency | S&P 500 historical | T+0 | `universe.py` enforces membership at date |

Validator verdict: lineage is documented; lags are enforced in code; no
user-facing feature can reach a date earlier than its publication lag.
*Residual risk:* FinMind's US dataset has occasional missing symbols
(12/503 in the 2016-2023 pull — see research log 2026-04-17). Survivorship
bias is still present in the universe (current S&P list). See §8-1.

### 2.3 Model choice

Ridge (alpha=1.0) is the default. GBM and Neural alternatives exist but
require beating Ridge by ≥0.1 OOS Sharpe AND maintaining overfit ratio
< 3.0 to be promoted. Validator verdict: the gating is codified in
`strategy_registry.py:select_best()` — not a policy document. PASS.

---

## 3. Implementation Verification

### 3.1 Test coverage

- Unit tests: ~680 (factor computations, normalization, imputation, CV, gates, statistics).
- Integration tests: ~120 (end-to-end pipeline on synthetic data).
- Property tests: ~104 (Hypothesis-based invariants: PiT no-leakage, position caps, sector caps, normalization range, purge gap ≥ target horizon).
- Skipped: 30 (optional lightgbm/torch deps).

Validator spot-checks (2026-04-18):

| Claim | Check | Result |
|---|---|---|
| "Rank-percentile output ∈ [0,1]" | `tests/property/test_normalization_invariants.py` | PASS |
| "No future data in any feature" | `tests/property/test_pit_no_leakage.py` | PASS |
| "Purge gap ≥ target horizon" | `tests/property/test_purge_gap_horizon.py` | PASS |
| "Registry refuses double-dip (SIGNAL + RISK)" | `tests/unit/test_registry.py::test_double_dip_raises` | PASS |
| "FinMind adapter scrubs token from error messages" | `tests/unit/test_finmind_adapter.py` (per feedback memory 2026-04) | PASS |

### 3.2 Configuration integrity

- `config/gates.yaml` thresholds match defaults hard-coded in `src/nyse_core/factor_screening.py`. PASS.
- `config/falsification_triggers.yaml` has `frozen_date: 2026-04-15`; freeze-hash enforcement is still a TODO (see TODOS.md TODO-1). **Validator flag:** this is the single most important code-vs-policy gap. Until TODO-1 lands, a threshold edit is an undetectable act.

### 3.3 Reproducibility

- Git SHA recorded on each research event (implicitly via CI; explicit capture is TODO-16).
- Python version, lockfile hash: not yet captured. TODO.
- Config snapshots: `scripts/run_backtest.py` copies `strategy_params.yaml` + `gates.yaml` into the results directory on each run. PASS for backtests, missing for factor screens.

---

## 4. Outcomes Analysis

### 4.1 First real-data factor screen: `ivol_20d` (2026-04-17)

| Gate | Metric | Value | Threshold | Result |
|---|---|---:|---:|---:|
| G0 | OOS Sharpe (long-short quintile) | **-1.9156** | ≥ 0.30 | **FAIL** |
| G1 | Permutation p-value (500 reps) | **1.0000** | < 0.05 | **FAIL** |
| G2 | IC mean (Spearman, weekly) | **-0.0079** | ≥ 0.02 | **FAIL** |
| G3 | IC IR | **-0.0545** | ≥ 0.50 | **FAIL** |
| G4 | Max drawdown | **-0.5777** | ≥ -0.30 | **FAIL** |
| G5 | Marginal contribution | 1.0 (sentinel) | > 0 | PASS (first factor) |

Panel size: 197,524 score rows across 418 weekly rebalance dates on 491
S&P 500 symbols, 2016-2023. Forward return: close-to-close 5-day
approximation of Monday-open → Friday-close.

### 4.2 Sanity check — is this a code bug or a real signal?

Raw-IC sanity check (no sign inversion): `IC(raw_ivol_20d, fwd_ret_5d) =
+0.0213`, 51.7% positive weeks. This is weakly positive in the *inverted*
direction, meaning the textbook low-vol anomaly has flipped on this
research period. High-IVOL stocks beat low-IVOL stocks during 2016-2023.

Most-likely economic driver: the 2016-2023 period contains the post-GFC
growth/AI concentration era (FAANG+NVDA), the meme-stock Q1 2021 squeeze
(GME/AMC — high-IVOL names delivering +1000% single-day moves against
short positions), and COVID-era vol spikes correlated with recovery
returns. Each of these mechanisms breaks the "low-IVOL outperforms" thesis.
The -57.8% drawdown is most consistent with the Q1 2021 squeeze event.

Validator verdict. The FAIL is a legitimate signal-level failure, not a
code bug. The pipeline correctly screened and rejected a factor that does
not work on the chosen research period.

### 4.3 AP-6 check: was the sign convention re-negotiated to pass?

**No.** The developer logged the FAIL honestly. The registry's sign
convention for IVOL remains -1 (low raw value = buy), which is the
textbook orientation. Flipping to +1 to chase the observed inversion would
be post-hoc specification search and would invalidate downstream
statistical tests. A regime-conditional variant is being considered as a
separate factor (`ivol_20d_bear_only`), but that hypothesis must pass G0-G5
on its own merits before admission.

### 4.4 Synthetic backtest results (historical, pre-real-data)

The synthetic calibration suite (`synthetic_calibration.py`) plants known
signals into simulated data with realistic cross-sectional structure and
verifies the pipeline recovers them at SNR > 10x. These results validate
*methodology* only; they are **not** evidence of strategy profitability.
Any metric presented without "OOS on real data" in its caption is a
synthetic number.

### 4.5 Second screening wave (2026-04-17 to 2026-04-18): price/volume + fundamentals

After `ivol_20d` failed, five additional Tier-1 and Tier-2 factors were
screened on the same 2016-2023 research panel using real S&P 500 OHLCV
and SEC EDGAR XBRL fundamentals. All five failed at least one gate.
Aggregate table (all pre-ensemble, all 2016-2023 research period):

| Factor | G0 Sharpe | G1 perm-p | G2 IC | G3 IC_IR | G4 MaxDD | Passed |
|---|---:|---:|---:|---:|---:|:---:|
| ivol_20d | **-1.9156** | **1.0000** | **-0.0079** | **-0.0545** | **-0.578** | 1/6 (G5 only) |
| high_52w | **-1.2291** | **1.0000** | **-0.0055** | **-0.0234** | **-0.607** | 1/6 (G5 only) |
| momentum_2_12 | 0.5164 | 0.0020 | **0.0189** | **0.0777** | -0.283 | 4/6 |
| piotroski | **0.0385** | 0.0020 | **0.0090** | **0.0892** | -0.216 | 4/6 |
| accruals | 0.5765 | 0.0020 | **0.0080** | **0.0623** | -0.272 | 4/6 |
| profitability | 1.1477 | 0.0020 | **0.0158** | **0.1130** | -0.190 | 4/6 |

**Bold = failed gate.** `G5 = marginal_contribution > 0` is a sentinel
(1.0) for the first factor of each family and not a real test; no factor
cleared gates G0-G4 end-to-end.

**Failure pattern — three clusters:**

1. **Complete structural failure (2 factors):** `ivol_20d`, `high_52w`.
   Negative Sharpe, permutation p ≈ 1.0, negative IC, catastrophic
   drawdown. Both are price/volume momentum-flavored and both inverted
   on the 2016-2023 period (FAANG+meme-stock era). These factors are
   *wrong-signed on this period*, not weak.
2. **Weak-but-positive (3 fundamentals):** `accruals`, `profitability`,
   `piotroski` all have the correct sign (positive IC, positive Sharpe)
   but IC far below the G2 threshold (0.008-0.016 observed vs ≥ 0.02
   required) and IC_IR far below G3 (0.06-0.11 observed vs ≥ 0.50
   required). Fundamental quality effects exist in direction but at
   too small a magnitude to cross gates weekly.
3. **Momentum partial (1 factor):** `momentum_2_12` passed G0 Sharpe
   (+0.516), G1 permutation, G4 drawdown — but G2 IC (0.019) and G3
   IC_IR (0.078) are below thresholds. This is the opposite of the
   TWSE outcome (where momentum failed catastrophically). NYSE
   momentum has a real but low-information-ratio signal.

### 4.6 Threshold interpretation (plan doc vs `gates.yaml`)

The plan document (`docs/plan.md` — dreamy-riding-quasar) lists
"G3_walk_forward: oos_sharpe_delta > 0" as the G3 check. The
implementation in `config/gates.yaml` sets G3 as `ic_ir ≥ 0.50`
(marginal contribution to ensemble IC). These are two different
checks. The implementation is stricter (IC_IR ≥ 0.50 is a
Grinold-Kahn-caliber bar). **Validator note:** the current gate
configuration is *conservative* — it is possible that a factor
failing implementation-G3 (IC_IR < 0.50) could have passed the
plan-text version of G3. AP-6 forbids re-negotiation after results
are known; the `gates.yaml` thresholds are treated as frozen.
A separate decision record is required to argue that the plan text
should be the canonical gate (it should not, pre-result), or that
the thresholds were mis-pre-specified (evidence required).

### 4.7 Code-vs-signal diagnosis for the 6-factor wave

- **ivol_20d, high_52w:** Raw-IC sanity check confirms the textbook
  sign inverted on 2016-2023 (see §4.2 for ivol_20d; identical
  reasoning for high_52w — stocks at 52w-high extended into FAANG+
  AI concentration).
- **momentum_2_12:** Direction matches the Jegadeesh-Titman (1993)
  cross-sectional premium. IC_IR shortfall matches Asness et al.
  (2014) finding that U.S. long-only cross-sectional momentum has
  information ratios of 0.3-0.5 range, which is below the
  strict `gates.yaml` threshold of 0.50.
- **piotroski, accruals, profitability:** All three match
  academic signs (high F-score = buy, low accruals = buy, high
  gross-profits/assets = buy). Magnitudes are consistent with
  quarterly (not weekly) fundamental effects — a weekly rebalance
  captures limited incremental information between quarterly filings.

**Validator verdict:** All six failures are *legitimate signal-level
outcomes*, not code bugs. The pipeline screened honestly and
rejected all attempted factors.

### 4.8 Aggregate outcome

**0 of 6 Tier-1 + Tier-2 factors passed G0-G5 on the 2016-2023 research
period.** The `docs/OUTCOME_VS_FORECAST.md` tracker shows 7 out of 7
plan-doc predictions for research-period performance were incorrect
(see calibration summary in that document). This is informative: the
plan's prior on factor admission was calibrated to a TWSE-like hit
rate (~30%, corresponding to ~4 of 13 factors passing) and the
observed hit rate is 0%. Three non-exclusive paths forward:

- **A) Tier-3 factors.** Options flow, analyst revisions, NLP earnings
  — none yet attempted. Different data, different frictions, different
  failure modes. This is the only path that expands the hypothesis
  set without relaxing thresholds.
- **B) Regime-conditional variants.** Re-screen momentum and the
  three fundamentals in bear-regime-only slices (SPY < SMA200). This
  is compatible with AP-6 only if the regime split was pre-specified
  in the plan (it was — see `strategy_params.yaml: regime`); the
  variant is screened as a *new factor* with its own G0-G5 verdict.
- **C) Horizon change.** Re-screen fundamentals at 20-day forward
  horizon. Plan-text specifies 20-day as a secondary target; purge
  gap auto-adjusts. 20-day is more consistent with the quarterly
  frequency of fundamental updates. Must be registered as a new
  screen, not a re-interpretation of the 5-day outcome.

Threshold re-negotiation (path D) is forbidden by AP-6. Stopping the
NYSE cross-sectional thesis entirely (path E) is pre-specified in
`docs/ABANDONMENT_CRITERIA.md` — see that document for the explicit
stop-conditions.

### 4.9 What we do not yet know

- **Answered (partial):** whether *any* Tier-1 or Tier-2 factor passes
  G0-G5 on real NYSE data. Outcome: 0/6.
- **Still open:** whether any Tier-3 factor (options, NLP, analyst
  revisions) passes. Not yet attempted.
- **Still open:** whether any regime-conditional variant passes.
- **Still open:** whether any factor passes with 20-day forward horizon.
- **Still open (conditional):** ensemble G0-G5 on 2016-2023 — cannot be
  evaluated while zero factors are admitted.
- **Still open (one-shot):** whether the above transfers to the
  2024-2025 holdout. Holdout lockfile intact.

**SR 11-7 §V.2 requires outcomes evaluation. Six outcomes are
evaluated; roughly seven to ten remain to be evaluated before any
live-capital decision is defensible.**

---

## 5. Ongoing Monitoring Plan

Per SR 11-7 §V.1 and the plan's F1-F8 falsification triggers:

| Trigger | Cadence | Owner | Escalation path |
|---|---|---|---|
| F1 — signal death (rolling IC < 0.01 for 2 months) | Weekly | Operator | VETO: halt → paper mode |
| F2 — factor sign flips (3+ in 2 months) | Weekly | Operator | VETO |
| F3 — drawdown > -25% | Daily intraday | Operator | VETO |
| F4 — single stock > 15% weight | Per rebalance | Operator | WARNING: reduce to 60% exposure |
| F5 — monthly turnover > 200% | Monthly | Operator | WARNING |
| F6 — annual cost drag > 5% | Monthly | Operator | WARNING |
| F7 — benchmark split-adjust break | On corporate action | Operator | WARNING + forced recompute |
| F8 — feature staleness > 10 days | Daily | Operator | WARNING |

Implementation. `src/nyse_ats/monitoring/falsification.py` evaluates all
triggers before order submission and emits a `FalsificationCheckResult`
per trigger. Dashboard displays current value vs threshold.

Gap (validator flag). Triggers reference a YAML-level `frozen_date`
comment. A hash-lock implementation (TODO-1) is still pending. Until then
the post-freeze immutability is policy, not enforcement.

---

## 6. Limitations

1. **Self-validation.** §1 limitation. Cannot catch developer blind spots.
2. **No real-data ensemble test yet.** Six factors screened on real data; none admitted; ensemble is structurally unbuildable until at least one factor clears gates.
3. **Survivorship bias.** Universe is current S&P 500 membership, not PiT membership. Understated drawdowns during regime breakpoints.
4. **Holdout is precious.** 2024-2025 is reserved. Once consumed, the validation has no remaining out-of-sample data. The draft cannot be re-run.
5. **Frozen-triggers not code-enforced.** Policy-level freeze, not hash-lock. See TODO-1.
6. **Config snapshots missing on factor screens.** Only backtest runs snapshot configs; factor screens don't. Gap noted for TODO-16 (reproducibility pack).

---

## 7. Validator Recommendation

**Do NOT deploy real capital until:**

1. At least 3 factors pass G0-G5 on real data. (Current: **0 of 6 attempted** — ivol_20d, high_52w, momentum_2_12, piotroski, accruals, profitability all FAIL. See §4.5-4.8.)
2. Ensemble backtest passes G0-G5 on 2016-2023 research period.
3. Full statistical validation suite passes (permutation p < 0.05, Romano-Wolf adjusted p < 0.05, bootstrap CI > 0).
4. Parameter sensitivity ±20%.
5. TRUE HOLDOUT (2024-2025) Sharpe > 0 — **one shot, no iteration**.
6. Third-party review of this document signed in §9.
7. TODO-1 (freeze hash) complete.

Paper trading may begin after (1)-(4) and with a clear labeling that it is
not a substitute for the holdout.

---

## 8. Reviewer Action Items

For the eventual third-party reviewer. Each item is a concrete claim to
audit, not a vague "review the model."

1. **Universe bias.** Verify that using current S&P 500 membership for
   2016-2023 is either (a) benign on this universe or (b) appropriately
   flagged as a bias. Counterfactual: compare a PiT universe (TODO-11
   completion) vs current-list for the first 3 factors that pass gates.
2. **Momentum inclusion decision.** The developer included momentum
   despite the TWSE predecessor failing catastrophically (-0.278 Sharpe).
   The rationale is "NYSE has no daily price limits." Verify that this
   argument survives the real-data momentum screen. If momentum fails on
   NYSE too, the developer should document the outcome and either drop it
   or present a new hypothesis.
3. **ivol_20d disposition.** Given the 2026-04-17 FAIL, the developer has
   three paths: (a) drop the factor, (b) conditional variant (regime-
   gated), (c) re-test with 20-day forward horizon. Review the developer's
   chosen path and verify it was selected before seeing the outcome, not
   after.
4. **Cost model calibration.** ADV-scaled spread is a plausible model;
   verify the base spread (10 bps) and the 1/sqrt(ADV) scaling against
   any available historical bid-ask snapshots.
5. **Walk-forward purity.** Re-run a sample fold by hand. Confirm that
   features on the test date use only data available at that date, and
   that the purge gap eliminates label leakage across the train/test
   boundary.
6. **Label timing.** Confirm that forward returns are computed Monday-open
   to Friday-close (post-execution), not Friday-close to Friday-close
   (which would include Monday's execution move as part of the label).

---

## 9. Approval

| Role | Name | Signature / Date | Notes |
|---|---|---|---|
| Developer | Operator | Authored this draft 2026-04-18 | |
| Independent Validator | **TBD — required before live capital** | | See §8 |
| Risk Owner | Operator (self, pre-live) | 2026-04-18 | |
| Compliance Review | **TBD before paper→live** | | See SEC_FINRA_COMPLIANCE.md |

---

*See also: [MODEL_VALIDATION.md](MODEL_VALIDATION.md) (the developer's companion doc) | [NYSE_ALPHA_RESEARCH_RECORD.md](NYSE_ALPHA_RESEARCH_RECORD.md) (development log) | [TODOS.md](TODOS.md) TODO-13 (external review) | [OUTCOME_VS_FORECAST.md](OUTCOME_VS_FORECAST.md) (living prediction-error tracker).*
