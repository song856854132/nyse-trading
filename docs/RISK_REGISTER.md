# Risk Register

**Purpose:** Single canonical table of known risks to the NYSE ATS program.
Consolidates risks previously scattered across `MODEL_VALIDATION.md §3.4`,
`FRAMEWORK_AND_PIPELINE.md §1.2`, `CAPACITY_AND_LIQUIDITY.md §6`,
`AUDIT_TRAIL.md`, `RISK_LIMITS.md §6`, `RESEARCH_RECORD_INTEGRITY.md`,
and `ABANDONMENT_CRITERIA.md`.

**Audience:** Risk review, LP due diligence, regulatory exam (SR 11-7 §VI
"Risk Management"), internal training, and the operator's future self.

**Iron rule:** Numeric thresholds quoted in this register are **frozen**
as of the date in the "Frozen" column. Loosening a threshold after a
result has been observed is an AP-6 violation that invalidates the
statistical standing of the research. Tightening a threshold (making
a risk trigger earlier) requires a dated, signed amendment in §6
below.

**Review cadence:** Quarterly unless a material change is triggered
earlier by an F-trigger firing, an A-criterion firing, an incident, or
a threshold amendment.

---

## 1. Scoring rubric

| Axis | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| **Severity** | Negligible — no capital or reputational impact | Minor — single-day P&L hit < 1%, no client effect | Moderate — cumulative P&L hit 1-3%, internal review required | Major — P&L hit 3-10% or regulatory finding, external disclosure | Catastrophic — strategy wind-down, regulatory action, or > 10% loss |
| **Likelihood** | Rare — not expected to occur in a 5-year horizon | Unlikely — possible but < 10% annual probability | Possible — 10-30% annual probability | Likely — expected within any 12-month period (30-70%) | Expected — recurrent or continuous condition (> 70%) |

**Risk score = Severity × Likelihood (range 1-25).** Score ≥ 12 is a
material risk requiring active mitigation. Score ≥ 20 requires an
escalation path to the operator within 48 hours of any observation
change.

**Categories:** M = Model • D = Data • E = Execution • O = Operational
• G = Governance / Regulatory.

---

## 2. Canonical register

All rows below are either (a) pre-registered triggers/criteria with
frozen numeric thresholds, or (b) non-numeric risks whose mitigation
is a named control in the codebase or config. "Owner" defaults to
**Operator** because the program is currently single-operator; the
independent-validator row (R-G1) is the exception.

**Cross-reference keys:**
- `F1..F8` → `config/falsification_triggers.yaml` (post-live runtime, frozen 2026-04-15)
- `A1..A12` → `docs/ABANDONMENT_CRITERIA.md` (pre-live research, frozen 2026-04-18)

### 2.1 Post-live runtime triggers (F1-F8) — frozen 2026-04-15

| ID | Cat | Description | Threshold (frozen) | Sev | Lik | Score | Mitigation | Owner | Last review |
|---|:---:|---|---|:---:|:---:|:---:|---|---|---|
| R-F1 | M | Signal death: rolling 60-day IC below 0.01 for 2+ months | IC < 0.01, 2+ months | 5 | 3 | 15 | VETO halt; switch to paper; root-cause on factor-by-factor basis; `falsification.py` evaluates per rebalance | Operator | 2026-04-18 |
| R-F2 | M | Factor death: 3+ core factor Ridge weights flip sign within 2 months | ≥ 3 sign flips / 2 months | 5 | 2 | 10 | VETO halt; factor-weight audit via `/alpha-research weights`; adjust factor admission if systemic | Operator | 2026-04-18 |
| R-F3 | M | Excessive drawdown from portfolio peak | MaxDD < -25% | 5 | 2 | 10 | VETO halt; review regime overlay; Telegram alert; postmortem within 72h | Operator | 2026-04-18 |
| R-F4 | O | Concentration: single stock exceeds 15% of NAV | weight > 15% | 4 | 2 | 8 | WARNING — exposure to 60%; rebalance within 1 week; property test `test_position_caps_invariant` caps at 10% soft | Operator | 2026-04-18 |
| R-F5 | E | Turnover spike: monthly turnover above 200% | turnover > 200%/mo | 3 | 3 | 9 | WARNING — exposure to 60%; review allocator + sell-buffer; cost-drag audit | Operator | 2026-04-18 |
| R-F6 | E | Cost drag: annualized frictions exceed 5% of gross | cost > 5%/yr | 4 | 3 | 12 | WARNING — exposure to 60%; recalibrate `cost_model.py`; consider VWAP; renegotiate broker | Operator | 2026-04-18 |
| R-F7 | D | Regime anomaly: benchmark not split-adjusted | boolean | 3 | 2 | 6 | WARNING — exposure to 60%; check corporate-action stream on SPY; `corporate_actions.py` audit | Operator | 2026-04-18 |
| R-F8 | D | Data staleness: max feature age exceeds 10 days | age > 10 days | 3 | 3 | 9 | WARNING — exposure to 60%; `pit.py::enforce_lags` forces NaN; vendor escalation | Operator | 2026-04-18 |

### 2.2 Pre-live abandonment criteria (A1-A12) — frozen 2026-04-18

| ID | Cat | Description | Threshold (frozen) | Sev | Lik | Score | Mitigation | Owner | Last review |
|---|:---:|---|---|:---:|:---:|:---:|---|---|---|
| R-A1 | M | 10/13 plan-listed factors fail G0-G5 on 2016-2023 | ≥ 10/13 FAIL | 4 | 4 | 16 | PAUSE — halt outside-capital recruiting; continue research; see `ABANDONMENT_CRITERIA.md §3`. Current status: **6/13 FAIL** — 4 factors from trigger | Operator | 2026-04-18 |
| R-A2 | M | 13/13 factors fail G0-G5 on 2016-2023 | 13/13 FAIL | 5 | 2 | 10 | PIVOT — reset factor backlog; preserve infrastructure; rewrite research plan | Operator | 2026-04-18 |
| R-A3 | M | Ensemble OOS Sharpe on research period < 0.3 after 3 factors admitted | Sharpe < 0.3 | 4 | 3 | 12 | PAUSE — gap from Phase 3 exit target too large to close with tuning | Operator | 2026-04-18 |
| R-A4 | M | Ensemble OOS Sharpe on research period < 0.0 | Sharpe < 0.0 | 5 | 2 | 10 | PIVOT — negative Sharpe is qualitative failure, not calibration | Operator | 2026-04-18 |
| R-A5 | M | Permutation p-value ≥ 0.20 for best candidate ensemble | perm-p ≥ 0.20 | 5 | 2 | 10 | PIVOT — effect indistinguishable from noise at weak significance | Operator | 2026-04-18 |
| R-A6 | M | Romano-Wolf adjusted p-value ≥ 0.50 for best candidate ensemble | RW-adj-p ≥ 0.50 | 4 | 2 | 8 | PAUSE — multiple-testing correction destroys signal | Operator | 2026-04-18 |
| R-A7 | M | Parameter sensitivity Sharpe range > ±40% across ±1σ perturbations | > ±40% | 4 | 3 | 12 | PAUSE — overfitting signature on (top_n, sell_buffer, ridge_alpha) | Operator | 2026-04-18 |
| R-A8 | M | TRUE HOLDOUT 2024-2025 Sharpe < 0 | Sharpe < 0 | 5 | 3 | 15 | ABANDON — one-shot test, no iteration permitted; iron rule of alpha-research skill §4 | Operator | 2026-04-18 |
| R-A9 | M | TRUE HOLDOUT Sharpe in [0.0, 0.3] AND cost drag ≥ 3% | Sharpe ∈ [0,0.3] ∧ cost ≥ 3% | 4 | 3 | 12 | PAUSE — gross signal too weak to survive frictions | Operator | 2026-04-18 |
| R-A10 | M | Aggregate Brier score ≥ 0.55 at n ≥ 10 resolved forecasts | Brier ≥ 0.55 | 3 | 4 | 12 | PAUSE — researcher's prior miscalibrated by > 10% worse than no-skill; rewrite priors. Current: Brier 0.61 at n=7 (monitoring) | Operator | 2026-04-18 |
| R-A11 | G | Two consecutive research-plan revisions required to explain results | reviewer-flagged | 3 | 2 | 6 | PIVOT — motivated reasoning eating discipline; 72h cooldown + `/codex review` before action | Operator | 2026-04-18 |
| R-A12 | G | Independent validator (INDEPENDENT_VALIDATION_DRAFT §9) refuses to sign | refusal | 4 | 2 | 8 | PAUSE — SR 11-7 independence requirement unsatisfied; find different validator | Operator | 2026-04-18 |

### 2.3 Structural and residual risks

| ID | Cat | Description | Threshold / state | Sev | Lik | Score | Mitigation | Owner | Last review |
|---|:---:|---|---|:---:|:---:|:---:|---|---|---|
| R-M1 | M | Ridge assumes linear cross-section; non-linear factor interactions unmodeled | structural | 3 | 4 | 12 | Protocol-based `CombinationModel` admits GBM/Neural alternatives gated on +0.1 Sharpe OOS; see `src/nyse_core/signal_combination.py` | Operator | 2026-04-18 |
| R-M2 | M | Price-volume factors receive negative Ridge weight on real data (sign convention error or regime mismatch) | observed on synthetic, monitored on real | 3 | 3 | 9 | Post-screen WARNING via `FactorRegistry` sign-convention check; TODO-10 adds live-weight monitor; do not auto-flip | Operator | 2026-04-18 |
| R-D1 | D | FinMind single-vendor outage (no current failover for OHLCV) | structural | 4 | 2 | 8 | `tenacity` retry + sliding-window rate limiter; `F8` fires if staleness > 10 days; manual Polygon/Alpha Vantage failover procedure in `docs/vendors/finmind.md` (TODO-19) | Operator | 2026-04-18 |
| R-D2 | D | EDGAR XBRL publication-lag misestimate → PiT leakage | publication lag pinned in `pit.py` | 5 | 2 | 10 | `tests/property/test_pit_no_leakage.py` (TODO-12); `pit.py::enforce_lags`; `HoldoutLeakageError` (iron rule 1) | Operator | 2026-04-18 |
| R-D3 | D | Corporate-action stream incomplete → split/dividend mis-adjustment | structural; vendor-dependent | 4 | 3 | 12 | Event-sourced append-only CA log; `nautilus_bridge.pre_submit` cancels orders when CA detected between signal and execution; F7 fires if SPY benchmark not split-adjusted | Operator | 2026-04-18 |
| R-E1 | E | NautilusTrader broker connection loss mid-TWAP | structural | 3 | 3 | 9 | Retry + Telegram alert; partial-fill tolerated; `nautilus_bridge.reconcile` writes actual fill state to `live.duckdb`; reconciliation test covers partial fill path | Operator | 2026-04-18 |
| R-E2 | E | Reconciliation break: pipeline target vs actual position divergence > 0.5% | > 0.5% | 4 | 2 | 8 | `nautilus_bridge.reconcile` raises; > 5% halts all trading; frozen threshold (RISK_LIMITS 5.2, 2026-04-15) | Operator | 2026-04-18 |
| R-O1 | O | Kill switch not pre-checked at start-of-day | config flag | 5 | 2 | 10 | `nautilus_bridge.submit` checks `strategy_params.kill_switch` before every order; pre-trade attestation template (TODO-20) codifies daily operator check | Operator | 2026-04-18 |
| R-O2 | G | Research-log hash-chain corruption (silent history rewrite) | SHA-256 chain | 5 | 1 | 5 | `scripts/verify_research_log.py`; pre-commit hook + `tests/integration/test_research_log_chain.py` (TODO-7, CLOSED); only `scripts/append_research_log.py` may write | Operator | 2026-04-18 |
| R-G1 | G | Self-validation: developer == validator (SR 11-7 §V independence gap) | structural (currently true) | 4 | 5 | 20 | Acknowledged in `MODEL_VALIDATION.md §1.5` and `INDEPENDENT_VALIDATION_DRAFT.md §9`; target external-reviewer date TBD; disclosed in DDQ §9 | Operator (acting as validator) | 2026-04-18 |
| R-G2 | G | Frozen thresholds mutated after result observed (AP-6 violation) | configuration integrity | 5 | 1 | 5 | Runtime hash check on `config/falsification_triggers.yaml` (TODO-1 CLOSED); amendment log §6 of this register; code review + git history audit | Operator | 2026-04-18 |
| R-G3 | G | Holdout contamination: query or backtest touches dates > 2023-12-31 | iron rule 1 | 5 | 1 | 5 | `tests/property/test_no_holdout_leakage.py` (TODO-6/34 CLOSED); pre-commit `holdout-path-guard`; DB-level assertion `MAX(date) ≤ 2023-12-31` | Operator | 2026-04-18 |

---

## 3. Heat map

Risks grouped by score band. Scores on a 1-25 scale (severity × likelihood).

```
  EXTREME (20-25)  │  R-G1 (self-validation)
  ─────────────────┼──────────────────────────────────────────────
  HIGH    (12-19)  │  R-A1 (6/13 failed; trigger window shrinking)
                   │  R-F1 (signal death)
                   │  R-A8 (holdout Sharpe < 0 → ABANDON)
                   │  R-F6 (cost drag > 5%)
                   │  R-A3, R-A7, R-A9, R-A10 (ensemble/sensitivity/calibration)
                   │  R-M1 (Ridge linearity assumption)
                   │  R-D3 (corporate-action stream)
  ─────────────────┼──────────────────────────────────────────────
  MEDIUM  (6-11)   │  R-F2..F5, F7, F8
                   │  R-A2, A4, A5, A6, A11, A12
                   │  R-M2, R-D1, R-D2
                   │  R-E1, R-E2, R-O1
  ─────────────────┼──────────────────────────────────────────────
  LOW     (1-5)    │  R-O2 (chain corruption — high severity but low likelihood)
                   │  R-G2 (threshold mutation — gated by runtime hash check)
                   │  R-G3 (holdout contamination — gated by pre-commit + property test)
```

**Top-3 material risks** (score ≥ 15 **AND** currently live):
1. **R-G1** (score 20) — independence gap. Structural; requires external validator.
2. **R-A1** (score 16) — 6 of 13 factors have failed; 4 remaining screens determine PAUSE fate. Evaluated after each factor screen.
3. **R-F1 / R-A8** (score 15 each) — signal death / holdout failure. Pre-deployment and runtime gates are both armed; nothing further needed until a screen or holdout fires.

---

## 4. Control-to-risk traceability

| Control | Risks mitigated | Evidence |
|---|---|---|
| `config/falsification_triggers.yaml` runtime hash check | R-F1..F8, R-G2 | `falsification.py`; TODO-1 CLOSED |
| `tests/property/test_no_holdout_leakage.py` + `HoldoutLeakageError` | R-A8, R-G3 | TODO-6/TODO-34 CLOSED |
| `scripts/verify_research_log.py` + integration test + pre-commit hook | R-O2, R-G2 | TODO-7/TODO-35 CLOSED; `.pre-commit-config.yaml` |
| `src/nyse_core/risk.py` position + sector + beta caps with property tests | R-F4, R-E2 | `test_position_caps_invariant`, `test_sector_caps_invariant` |
| `src/nyse_core/cost_model.py` ADV-dependent spread model | R-F6 | `test_cost_model` unit tests |
| `src/nyse_core/pit.py::enforce_lags` | R-D2, R-F8 | `test_pit` unit tests; property-level PiT test planned (TODO-12) |
| `src/nyse_ats/execution/nautilus_bridge.py` pre-submit CA check + reconcile | R-D3, R-E1, R-E2, R-O1 | TODO-2 CLOSED (corporate-action guard) |
| `scripts/append_research_log.py` as only sanctioned writer | R-O2 | TODO-33; `pre-commit` chain check |
| CI (GitHub Actions) pytest + ruff + mypy + gitleaks | cross-cutting | TODO-6 CLOSED |
| `docs/ABANDONMENT_CRITERIA.md` pre-registered exit | R-A1..A12 | TODO-14 (this doc); cross-linked |
| `docs/MODEL_VALIDATION.md §1.5` independence statement | R-G1 | TODO-13 PARTIAL |

---

## 5. Out of scope (explicitly *not* tracked here)

To prevent register creep, the following are intentionally excluded:

1. **Execution venues other than NautilusTrader.** Venue-migration risk
   would be re-added if a second venue is introduced.
2. **Currency risk.** Strategy is USD-only. Reopens if international
   tickers ever enter the universe.
3. **Leverage risk.** Strategy is unlevered (gross ≤ 100% NAV).
4. **Counterparty / prime-broker risk.** No prime relationship exists
   pre-live; reopens at shadow graduation.
5. **Tax risk.** Taxable-vehicle selection decisions deferred to fund
   formation (not in program scope).

Each exclusion is intentional and should be revisited at deployment-ladder
graduation gates.

---

## 6. Amendment log

Any change to a threshold or to a row below must land here with a dated,
signed entry. **Tightening is allowed** (makes a risk trigger earlier).
**Loosening is forbidden** once a result has been observed.

| Date | Amendment | Signed by | Research-log hash |
|---|---|---|---|
| 2026-04-19 | Initial draft (iter-10 ralph loop); ingests F1-F8, A1-A12, and 11 structural/residual risks | Operator | *(appended with this commit — see `results/research_log.jsonl` tip)* |

---

*Related: [ABANDONMENT_CRITERIA.md](ABANDONMENT_CRITERIA.md) • [RISK_LIMITS.md](RISK_LIMITS.md) • [MODEL_VALIDATION.md](MODEL_VALIDATION.md) • [FRAMEWORK_AND_PIPELINE.md](FRAMEWORK_AND_PIPELINE.md) • [config/falsification_triggers.yaml](../config/falsification_triggers.yaml) • [TODOS.md](TODOS.md)*
