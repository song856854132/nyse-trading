# SEC/FINRA Regulatory Compliance Mapping

**NYSE ATS Framework | v0.4 | April 2026**

> **Status:** Research phase (pre-paper-trading). This document maps system components to applicable regulations and identifies compliance gaps for remediation before live deployment.

---

## 1. Regulatory Framework

### 1.1 SR 11-7: Model Risk Management (OCC/Fed 2011)

SR 11-7 requires firms using quantitative models for trading decisions to maintain model risk governance covering development, validation, and ongoing monitoring. Our system addresses each pillar:

| SR 11-7 Pillar | System Response |
|---|---|
| **Model Development** | Ridge regression as default combination model (`models/ridge_model.py`). GBM/Neural gated by overfit ratio <3.0 and +0.1 Sharpe OOS delta (`strategy_registry.py`). |
| **Model Validation** | Walk-forward CV with purge/embargo (`cv.py`), permutation test (`statistics.py`), Romano-Wolf stepdown for multiple testing, block bootstrap CI. |
| **Ongoing Monitoring** | 3-layer drift detection (`drift.py`): IC drift, sign flips, model decay. 8 falsification triggers (F1-F8) in `config/falsification_triggers.yaml`, frozen as of 2026-04-15. |
| **Model Inventory** | See Section 3 below. |
| **Documentation** | `FRAMEWORK_AND_PIPELINE.md` is the single source of truth. All config values document their derivation (AP-12). |

### 1.2 FINRA Rule 3110: Supervision

Rule 3110 requires a supervisory system for trading activities. Our controls:

| Requirement | Implementation |
|---|---|
| Written supervisory procedures | This document + `FRAMEWORK_AND_PIPELINE.md` + `AUDIT_TRAIL.md` |
| Review of trading activity | Weekly rebalance review via Streamlit dashboard; Telegram alerts for all trades |
| Exception reports | Falsification triggers F1-F8 generate automated alerts at WARNING/VETO severity |
| Annual review | Deployment ladder requires 3-month paper, 1-month shadow, 3-month min-live before scale |
| Supervisory approval | Kill switch (`strategy_params.yaml: kill_switch`) halts all order submission; human approval required to resume |

### 1.3 SEC Market Access Rule (15c3-5)

Rule 15c3-5 requires pre-trade risk controls for firms with market access. Our 10-layer risk stack in `risk.py` + `schema.py` provides:

| 15c3-5 Requirement | System Control | Config Reference |
|---|---|---|
| Pre-trade capital threshold | Daily loss limit: -3% portfolio halt | `schema.py: DAILY_LOSS_LIMIT = -0.03` |
| Single-security concentration | Position cap: 10% max per stock | `schema.py: MAX_POSITION_PCT = 0.10` |
| Aggregate exposure | Regime overlay: 40% in bear market | `schema.py: BEAR_EXPOSURE = 0.4` |
| Erroneous order prevention | Kill switch checked before every order | `strategy_params.yaml: kill_switch` |
| Credit/capital limits | ADV participation cap: 5% max | `strategy_params.yaml: max_participation_rate: 0.05` |
| Ability to halt trading | Kill switch (manual) + F1/F2 VETO (automatic) | Immediate halt, switch to paper mode |

### 1.4 FINRA 2026 Regulatory Priorities: AI/Algo Trading Oversight

FINRA's 2026 priorities emphasize algorithmic trading controls and AI model governance. Relevant items:

| Priority Area | System Response |
|---|---|
| Algorithm testing before deployment | 934 tests (680 unit, 120 integration, 104 property); walk-forward CV on 2016-2023 research period |
| Change management for algo updates | Falsification triggers frozen before first trade (`frozen_date: 2026-04-15`); no retroactive threshold adjustment |
| Kill switch capability | `kill_switch` config flag + F1/F2 automatic VETO |
| AI model explainability | Ridge regression: transparent linear coefficients; feature importance via normalized absolute coefficients |
| Ongoing surveillance | 3-layer drift detection; 8 falsification triggers; Telegram alerts |

---

## 2. Compliance Matrix

| # | Requirement | Regulation | System Component | Implementation | Evidence |
|---|---|---|---|---|---|
| C1 | Model documentation | SR 11-7 | `FRAMEWORK_AND_PIPELINE.md`, `contracts.py` | All models documented with assumptions, limitations, and derivation rationale | This document + framework doc |
| C2 | Model validation | SR 11-7 | `cv.py`, `statistics.py`, `gates.py` | Purged walk-forward CV, permutation test (p<0.05), Romano-Wolf stepdown, bootstrap CI | `tests/test_statistics.py` |
| C3 | Pre-trade risk controls | 15c3-5 | `risk.py` (6 layers) | Daily loss halt (-3%), position caps (10%), sector caps (30%), beta bounds [0.5, 1.5] | `tests/test_risk.py` |
| C4 | Kill switch | 15c3-5 | `strategy_params.yaml: kill_switch` | Boolean flag checked before every order submission | `tests/test_risk.py` |
| C5 | Audit trail | FINRA 3110 | `contracts.py: Diagnostics` + DuckDB | Every public function returns `(result, Diagnostics)` with severity levels | `contracts.py` |
| C6 | Algorithm testing | FINRA 15-09 | 934 tests, property tests, walk-forward | Hypothesis property tests, pytest, PurgedWalkForwardCV | `tests/` directory |
| C7 | Supervisory review | FINRA 3110 | Dashboard + Telegram alerts | Streamlit dashboard with falsification status; automated Telegram notifications | Dashboard module |
| C8 | Position concentration limits | 15c3-5 | `risk.py: apply_position_caps()` | Max 10% per stock; excess redistributed pro-rata | Property tests in `tests/` |
| C9 | Sector concentration limits | Internal best practice | `risk.py: apply_sector_caps()` | Max 30% per GICS sector; excess redistributed | Property tests in `tests/` |
| C10 | Data integrity | SR 11-7 | `pit.py`, `data_quality.py` | Point-in-time enforcement with publication lags; no lookahead bias | `tests/test_pit.py` |
| C11 | Model change control | SR 11-7 | `config/falsification_triggers.yaml` | Thresholds frozen at `frozen_date: 2026-04-15`; hash verification planned | Config file + `AUDIT_TRAIL.md` |
| C12 | Multiple testing correction | SR 11-7 | `statistics.py: romano_wolf_stepdown()` | Family-wise error rate controlled across all factors tested simultaneously | `tests/test_statistics.py` |
| C13 | Market impact controls | 15c3-5 | `strategy_params.yaml` | TWAP execution over 30 min; max 5% ADV participation rate | Execution config |
| C14 | Earnings event controls | Internal best practice | `risk.py: check_earnings_exposure()` | Stocks reporting within 2 days capped at 5% weight | `tests/test_risk.py` |
| C15 | Regime-aware exposure | Internal best practice | `risk.py: apply_regime_overlay()` | SPY < SMA200 reduces exposure to 40% | `tests/test_risk.py` |

---

## 3. Model Inventory

| Model ID | Model Name | Type | Module | Version | Purpose | Validation Status | Owner |
|---|---|---|---|---|---|---|---|
| M-001 | Ridge Regression | Linear (L2) | `models/ridge_model.py` | v0.4 | Default signal combination (alpha=1.0) | Walk-forward validated, OOS tested | System |
| M-002 | LightGBM | Gradient Boosting | `models/gbm_model.py` | v0.4 | Alternative combination (gated) | Implemented, gating criteria defined | System |
| M-003 | Neural MLP | 2-layer MLP (PyTorch) | `models/neural_model.py` | v0.4 | Alternative combination (gated) | Implemented, gating criteria defined | System |
| M-004 | Regime Overlay | Binary classifier | `risk.py: apply_regime_overlay()` | v0.4 | Bull/Bear via SPY vs SMA200 | Validated in TWSE (63 phases) | System |
| M-005 | Cost Model | ADV-dependent spread | `cost_model.py` | v0.4 | Transaction cost estimation | Calibrated to NYSE spreads | System |
| M-006 | Drift Detector | 3-layer monitoring | `drift.py` | v0.4 | IC/sign-flip/R2 drift detection | Unit tested (82 tests) | System |

**Model Selection Gating (M-002, M-003):** Alternatives must beat Ridge by >0.1 Sharpe OOS AND maintain overfit ratio <3.0. Tracked by `strategy_registry.py`.

---

## 4. Recordkeeping Requirements

| Record Type | Regulation | Retention Period | Storage Location | Format |
|---|---|---|---|---|
| All experiment logs | SR 11-7, FINRA 3110 | 6 years | `research.duckdb` | Structured (DuckDB tables) |
| Trade plans generated | FINRA 3110, 15c3-5 | 6 years | `live.duckdb` | `TradePlan` frozen dataclass |
| Order execution records | FINRA 3110 | 6 years | NautilusTrader logs + `live.duckdb` | TWAP execution records |
| Model parameters | SR 11-7 | Life of model + 3 years | `research.duckdb` + config YAML | Ridge coefficients, feature importance |
| Gate verdicts (G0-G5) | SR 11-7 | 6 years | `research.duckdb` | `GateVerdict` dataclass |
| Falsification trigger events | SR 11-7, FINRA 3110 | 6 years | `live.duckdb` + Telegram archive | `FalsificationCheckResult` dataclass |
| Diagnostics messages | Internal | 1 year (rolling) | `research.duckdb` / `live.duckdb` | `DiagMessage` with level/source/context |
| Configuration snapshots | SR 11-7 | Life of model + 3 years | Git repository + `research.duckdb` | YAML files, SHA-256 hashes |
| Drift reports | SR 11-7 | 3 years | `research.duckdb` | `DriftReport` dataclass |

**SEC Rule 17a-4 Note:** Electronic records must be stored in non-rewritable, non-erasable format (WORM). DuckDB does not natively support WORM compliance. See Section 5 for remediation.

---

## 5. Gaps and Remediation Plan

| Gap ID | Description | Regulation | Severity | Remediation | Target Date |
|---|---|---|---|---|---|
| GAP-1 | No WORM-compliant storage for trade records | SEC 17a-4 | High | Implement append-only export to S3 with Object Lock or dedicated WORM provider | Before shadow stage |
| GAP-2 | Config hash verification not yet implemented | SR 11-7 | Medium | Add SHA-256 hash check of `falsification_triggers.yaml` at startup (TODO-1 in TODOS.md) | Before paper trading |
| GAP-3 | No formal model approval workflow | SR 11-7 | Medium | Implement approval chain for model promotion (currently single-operator) | Before minimum live |
| GAP-4 | Telegram is single notification channel | FINRA 3110 | Low | Add email backup channel for critical alerts (VETO triggers) | Before shadow stage |
| GAP-5 | No automated regulatory reporting | FINRA 3110 | Low | Build quarterly compliance summary report generator | Before scale stage |
| GAP-6 | Broker-dealer registration not addressed | 15c3-5 | High | Determine if trading through registered broker-dealer satisfies requirement vs. self-registration | Before minimum live |
| GAP-7 | No independent model validation | SR 11-7 | Medium | Engage external quant reviewer for independent validation of Ridge model and walk-forward methodology | Before shadow stage |
| GAP-8 | Corporate action handling not fully automated | FINRA 3110 | Medium | Complete `corporate_actions.py` integration with live data feed; currently event-sourced but manual trigger | Before paper trading |

---

## 6. Vendor Due-Diligence Files

Third-party data governance is a recurring finding in algo-trading exams and is
explicit in FINRA 2026 priorities. Per-vendor due-diligence files document
endpoint, auth, rate limits, PiT publication lag, license/ToS summary, failover
plan, known data-quality issues, and append-only outage logs. These are the
primary artifacts a regulator or LP DDQ will request.

| Vendor | Role | DD file |
|---|---|---|
| FinMind | Primary OHLCV source | [`docs/vendors/FINMIND.md`](vendors/FINMIND.md) |
| SEC EDGAR | Primary fundamentals source (XBRL companyfacts) | [`docs/vendors/EDGAR.md`](vendors/EDGAR.md) |
| FINRA | Primary short-interest source (bi-monthly) | [`docs/vendors/FINRA.md`](vendors/FINRA.md) |

Change protocol: any endpoint / auth / rate-limit / publication-lag change
MUST update the DD file and `config/data_sources.yaml` in the same commit.
Outage-log rows are append-only.

---

## 7. Daily Compliance Attestation Templates

SEC Rule 15c3-5 requires pre-order risk checks; FINRA Rule 3110 requires
documented supervisory review. Two daily attestation templates implement both
obligations as signed, commit-anchored forms:

| Template | When | Purpose | File |
|---|---|---|---|
| Pre-trade attestation | Before first order of the day | 14 checks: kill-switch, VETO state, risk limits, data staleness, iron-rule compliance, TradePlan envelope | [`docs/templates/PRE_TRADE_ATTESTATION.md`](templates/PRE_TRADE_ATTESTATION.md) |
| Post-trade attestation | After EOD reconciliation | 19 checks: fills vs plan, slippage, rejections, daily P&L vs limit, concentration, F1-F8, corporate actions, iron-rule compliance | [`docs/templates/POST_TRADE_ATTESTATION.md`](templates/POST_TRADE_ATTESTATION.md) |

Both templates are **frozen as of 2026-04-19**. Changing any checklist item,
threshold citation, or signing protocol requires an append row in
`docs/GOVERNANCE_LOG.md` under the threshold-change authorization point
(AP-6 applies). Daily-produced copies live under
`results/attestations/{pre_trade,post_trade}/<YYYY-MM-DD>.md` and are retained
6 years per §2.1.

Override protocol: if any VETO-class row fails and trading continues, the
exception row in §8/§11 of the attestation MUST reference both a `GL-NNNN`
authorization row in `docs/GOVERNANCE_LOG.md` and an `AT-NNNN` incident row in
`docs/AUDIT_TRAIL.md`. Missing references are themselves supervisory
violations.

---

## Appendix: Applicable Regulations Reference

| Regulation | Full Title | Issuer | Year |
|---|---|---|---|
| SR 11-7 | Supervisory Guidance on Model Risk Management | OCC/Federal Reserve | 2011 |
| FINRA Rule 3110 | Supervision | FINRA | 2014 (amended) |
| SEC Rule 15c3-5 | Market Access Rule | SEC | 2010 |
| FINRA 15-09 | Equity Trading Initiatives: Supervision and Control Practices for Algorithmic Trading Strategies | FINRA | 2015 |
| SEC Rule 17a-4 | Records to be Preserved by Certain Exchange Members, Brokers, and Dealers | SEC | 2003 (amended) |
