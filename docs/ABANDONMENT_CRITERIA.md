# Pre-Live Abandonment Criteria

**Purpose:** Define, in advance and in writing, the conditions under
which we will stop pursuing the NYSE cross-sectional equity alpha
thesis. This document is the *pre-live* complement to
`config/falsification_triggers.yaml` (which governs *post-live*
behavior via F1-F8). Live triggers answer "should we halt a running
strategy?"; abandonment criteria answer "should we ever deploy this
strategy at all?"

**Why this artifact exists:** Without pre-registered abandonment
thresholds, every failed result becomes a source of post-hoc
rationalization. With them, the decision is mechanical. This document
locks the researcher and the operator to the same exit points before
either of them has a stake in a specific outcome.

**Iron rule:** Thresholds in this document are frozen as of
**2026-04-18**. Loosening any threshold after a result has been
observed is a violation of AP-6 and invalidates the statistical
standing of the research. Tightening a threshold (making abandonment
easier) is permitted with a dated, signed amendment in §6 below.

**Audience:** The eventual third-party independent validator
(INDEPENDENT_VALIDATION_DRAFT.md §9), LP due-diligence teams
(AIMA DDQ §9.4 "What is your strategy-failure protocol?"), and the
operator's future self.

---

## 1. Scope

This document covers the **pre-live research and validation phase
only** — everything from factor screening through the TRUE HOLDOUT
evaluation. Once real capital is deployed, authority shifts to
`config/falsification_triggers.yaml` (F1-F8 runtime triggers).

Specifically:
- **In scope:** factor admission (G0-G5), ensemble backtest, statistical
  validation suite (permutation, Romano-Wolf, bootstrap), parameter
  sensitivity analysis, TRUE HOLDOUT one-shot test.
- **Out of scope:** anything post-paper-trading-start. Once paper
  mode begins, F1-F8 govern.

---

## 2. Severity levels

| Level | Meaning | Action |
|---|---|---|
| **PAUSE** | Research continues but no new capital commitment is sought | Halt recruiting outside investors; continue factor research; document pause decision |
| **PIVOT** | Current factor-set thesis is rejected; look for a different angle | Reset the factor backlog; rewrite the research plan; preserve the code infrastructure |
| **ABANDON** | Exit the NYSE cross-sectional equity domain entirely | Wind down; archive artifacts; redirect attention to a different market or instrument |

---

## 3. Abandonment criteria (pre-live)

Each row is a pre-registered condition. If the condition is met at the
listed evaluation point, the corresponding action is triggered.
Multiple conditions can fire simultaneously.

| # | Condition | Evaluation point | Severity | Rationale |
|---|---|---|---|---|
| A1 | 10 of 13 plan-listed factors (77%) fail G0-G5 on 2016-2023 | After 10th factor screen | PAUSE | Failure rate far exceeds TWSE precedent (44% pass rate). Suggests the 2016-2023 NYSE period is structurally hostile or the factor-family choices are wrong. |
| A2 | 13 of 13 plan-listed factors (100%) fail G0-G5 on 2016-2023 | After 13th factor screen | PIVOT | No admissible factor exists in the planned set. Equal-weight top-N cross-sectional strategy is unbuildable on this universe. |
| A3 | Ensemble OOS Sharpe on research period < 0.3 after 3 factors admitted | After first ensemble backtest | PAUSE | Phase 3 exit target (0.5-0.8) is >1.5x the observed result. Gap is too large to close with parameter tuning. |
| A4 | Ensemble OOS Sharpe < 0.0 on research period | After first ensemble backtest | PIVOT | Negative Sharpe is a qualitative failure, not a calibration problem. |
| A5 | Permutation p-value ≥ 0.20 for best candidate ensemble | After statistical validation | PIVOT | Effect is indistinguishable from randomly re-labeled data at weak significance levels. |
| A6 | Romano-Wolf adjusted p-value ≥ 0.50 for best candidate ensemble | After statistical validation | PAUSE | Multiple-testing correction destroys the signal. Either factor count is too high or individual p-values are too marginal. |
| A7 | Parameter sensitivity: Sharpe varies by > ±40% across ±1σ perturbations of top_n, sell_buffer, ridge_alpha | After sensitivity analysis | PAUSE | Overfitting signature; Sharpe is an artifact of specific parameter choices. |
| A8 | TRUE HOLDOUT 2024-2025 Sharpe < 0 | After one-shot holdout test | ABANDON | This is the single most consequential test. No iteration permitted (iron rule, alpha-research skill §4). |
| A9 | TRUE HOLDOUT Sharpe in [0.0, 0.3] AND cost-drag estimate ≥ 3% | After one-shot holdout test | PAUSE | Gross signal too weak to survive frictions. Do not deploy capital; consider instrument/vehicle change. |
| A10 | Aggregate Brier score after 10 resolved forecasts ≥ 0.55 | On any update to CALIBRATION_TRACKER.md | PAUSE | The researcher's prior is miscalibrated by >10% worse than no-skill. Rewrite the priors before screening further. |
| A11 | Two consecutive research-plan revisions required to "explain" results (post-hoc narrative drift) | Reviewer-flagged | PIVOT | Motivated reasoning is eating the discipline. |
| A12 | Independent validator (INDEPENDENT_VALIDATION_DRAFT §9) refuses to sign | Before any paper trading | PAUSE | SR 11-7 independence requirement is not satisfied. Must find a different validator before proceeding. |

---

## 4. Current standing (2026-04-18)

| # | Condition | Current value | Triggered? |
|---|---|---|---|
| A1 | ≥10/13 fail G0-G5 | **6/13 attempted, 6 FAIL** | No — 4 factors remain to screen |
| A2 | 13/13 fail | 6/6 failed so far | Contingent |
| A3 | Ensemble Sharpe < 0.3 | Ensemble unbuildable (0 admitted) | Not evaluable |
| A4 | Ensemble Sharpe < 0.0 | Not evaluable | Not evaluable |
| A5 | Perm p ≥ 0.20 | Not evaluable | Not evaluable |
| A6 | RW-adjusted p ≥ 0.50 | Not evaluable | Not evaluable |
| A7 | Param sensitivity > ±40% | Not run | Not evaluable |
| A8 | Holdout Sharpe < 0 | **Holdout intact — not run** | Not evaluable |
| A9 | Holdout Sharpe in [0, 0.3] AND cost ≥ 3% | Holdout intact | Not evaluable |
| A10 | Brier ≥ 0.55 at n ≥ 10 | **Current Brier 0.61 at n = 7** | Monitoring — will trigger at n = 10 if pattern holds |
| A11 | Post-hoc narrative drift | None observed | No |
| A12 | Validator refusal | Validator TBD | Not evaluable |

**Active signal:** The 6/6 factor-failure run brings A1 to within 4
factors of triggering PAUSE. If the next 4 factors (Tier-3 + regime
variants) also fail, A1 fires. If all 13 original factors fail, A2
fires (PIVOT).

**Pre-commitment:** The researcher commits to treating the next
factor-screening wave as informative for A1/A2, not as evidence that
the plan should be revised to allow more attempts.

---

## 5. What is NOT an abandonment criterion

To prevent criterion creep, the following are explicitly declared
*non-abandonment* conditions:

1. **Negative individual factor Sharpe.** Individual factors can fail
   while the thesis survives; A1/A2 aggregate multiple factor outcomes.
2. **Slow research pace.** Time spent is not an abandonment signal.
   Quality of outcomes is.
3. **Discovery of a code bug.** A bug is a fixable-in-place issue, not
   an abandonment signal. Fix the bug, re-run the screen, log both
   events in the research log.
4. **Unflattering external opinion.** Outside-voice review
   (`/codex`, `/plan-eng-review`) provides inputs; abandonment is
   governed by the mechanical thresholds above.
5. **Macro regime concern.** "Markets are unprecedented" is not a
   signal to abandon; it is a reason to be more disciplined with the
   existing thresholds.

---

## 6. Amendment log

Any tightening of the thresholds above (making abandonment *easier*)
is permitted with a dated, signed amendment here. Loosening (making
abandonment *harder*) is forbidden after results are observed.

| Date | Amendment | Signed by | Rationale |
|---|---|---|---|
| 2026-04-18 | Initial draft | Operator | Pre-registration baseline established after 6-factor wave |

---

## 7. Decision protocol

When a criterion fires:

1. **Log the event.** Append to `results/research_log.jsonl` with
   `event_type: "abandonment_criterion_triggered"` and the criterion
   number.
2. **Hash-chain the entry.** Use `scripts/append_research_log.py` so
   the event is cryptographically anchored.
3. **72-hour cooldown.** Do not take any corresponding action
   (halt / pivot / wind-down) for at least 72 hours after the trigger.
   This exists to prevent over-reaction to a single noisy signal.
4. **Second-opinion check.** Run `/codex review` or an equivalent
   independent review before committing to the action.
5. **Execute the action.** Do what the severity level requires.
6. **Document in INDEPENDENT_VALIDATION_DRAFT.md §7.** Update the
   validator recommendation with the triggered criterion and the
   action taken.

---

*Related: [OUTCOME_VS_FORECAST.md](OUTCOME_VS_FORECAST.md) (living ledger) | [CALIBRATION_TRACKER.md](CALIBRATION_TRACKER.md) (Brier scoring) | [INDEPENDENT_VALIDATION_DRAFT.md](INDEPENDENT_VALIDATION_DRAFT.md) §7 (validator recommendation) | [config/falsification_triggers.yaml](../config/falsification_triggers.yaml) (post-live F1-F8 triggers) | [TODOS.md](TODOS.md)*
