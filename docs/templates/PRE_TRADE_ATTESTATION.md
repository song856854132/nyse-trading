# Pre-Trade Compliance Attestation — DAILY

> **Purpose.** Documented supervisory review required by **SEC Rule 15c3-5**
> (Market Access) and **FINRA Rule 3110** (Supervision). Completed **before**
> the first order of the trading day is submitted to NautilusTrader.
>
> **Status:** template (frozen 2026-04-19). Changing the checklist items or
> thresholds requires an append row in `docs/GOVERNANCE_LOG.md` citing the
> criterion change — AP-6 applies.
>
> **How this form is used.** For each trading day a new copy is produced at
> `results/attestations/pre_trade/<YYYY-MM-DD>.md`. Most fields auto-populate
> from `live.duckdb` via `scripts/run_pre_trade_check.py` (to be built);
> remaining fields are filled by the operator. File is committed to a
> retention-protected branch so the signed record is immutable.
>
> **Retention.** 6 years per `docs/SEC_FINRA_COMPLIANCE.md` §2.1 row 1
> ("Trade plans generated → FINRA 3110, 15c3-5 → 6 years").

---

## 1. Header

| Field | Value |
|---|---|
| Trading date (UTC) | `{{YYYY-MM-DD}}` |
| Stage | `paper` / `shadow` / `minimum_live` / `scale` (from `config/deployment_ladder.yaml`) |
| Rebalance cycle ID | `{{YYYY-MM-DD}}-W{{ISO_WEEK}}` |
| Attestation completed at (UTC) | `{{HH:MM:SS}}` |
| Attestation completed by | `{{operator_name}}` |
| Preparer (if different) | `{{system_or_operator}}` |
| Signed | `[ ] Yes / [ ] No (trading halts if unsigned)` |

---

## 2. Kill switch and VETO state

| # | Check | Source of truth | Expected | Observed | Pass? |
|---|---|---|---|---|---|
| 1 | Kill switch flag | `config/strategy_params.yaml:38` (`kill_switch`) | `false` | `{{value}}` | `[ ]` |
| 2 | No outstanding VETO trigger | `live.duckdb.falsification_checks` (last row, `severity` column; see `src/nyse_ats/storage/live_store.py:312` `record_falsification_check`) | no row with `severity='VETO'` and `resolved_at IS NULL` | `{{count}}` | `[ ]` |
| 3 | Falsification-trigger frozen-hash match | `src/nyse_ats/monitoring/falsification.py:50-82` `verify_frozen_hash` | stored hash == SHA256(`config/falsification_triggers.yaml`) | `{{match}}` | `[ ]` |

If any row in §2 fails: **do not submit orders.** File an incident note in
`docs/AUDIT_TRAIL.md` and append a decision row in `docs/GOVERNANCE_LOG.md`
before resuming.

---

## 3. Risk-limit pre-checks

| # | Check | Threshold source | Threshold | Observed | Pass? |
|---|---|---|---|---|---|
| 4 | Max single-stock weight in proposed TradePlan | `config/strategy_params.yaml:29` (`max_position_pct`) | ≤ 0.10 (10%) | `{{max_w}}` | `[ ]` |
| 5 | Max GICS-sector weight in proposed TradePlan | `config/strategy_params.yaml:30` (`max_sector_pct`) | ≤ 0.30 (30%) | `{{max_sector_w}}` | `[ ]` |
| 6 | Portfolio ex-ante beta vs SPY | `config/strategy_params.yaml:32-33` (`beta_cap_low`, `beta_cap_high`) | ∈ [0.5, 1.5] | `{{beta}}` | `[ ]` |
| 7 | Daily loss limit configured | `config/strategy_params.yaml:34` (`daily_loss_limit`) | = -0.03 (-3%) | `{{value}}` | `[ ]` |
| 8 | No held position > 5% with earnings within 2 trading days | `config/strategy_params.yaml:35-36` (`earnings_event_cap`, `earnings_event_days`) | 0 violations | `{{n_violations}}` | `[ ]` |

---

## 4. Data + corporate-action pre-checks

| # | Check | Source | Expected | Observed | Pass? |
|---|---|---|---|---|---|
| 9 | Max feature staleness across all sources | `config/falsification_triggers.yaml:52` (`F8` = 10 days) | ≤ 10 calendar days | `{{days}}` | `[ ]` |
| 10 | Corporate-action guard ran for all held symbols since signal | `src/nyse_ats/execution/nautilus_bridge.py:99-157` `pre_submit` | `detect_pending_actions` returned for every held symbol | `{{n_held}} checked, {{n_affected}} affected` | `[ ]` |
| 11 | Universe PiT rule holds (no stock entered/exited the universe between signal and execution) | `src/nyse_core/universe.py` | 0 mismatches | `{{n_mismatches}}` | `[ ]` |

If row 10 reports `n_affected > 0`: affected orders must be canceled and the
TradePlan regenerated with post-action prices **before** submission. Record
the regeneration event in `results/research_log.jsonl`.

---

## 5. Holdout and iron-rule compliance

| # | Check | Source | Expected | Observed | Pass? |
|---|---|---|---|---|---|
| 12 | No TradePlan timestamp > 2023-12-31 enters the live pipeline during research stage | iron rule 1, `docs/RALPH_LOOP_TASK.md:7` | N/A at paper or later stages | `{{stage}}` | `[ ]` (N/A at paper/shadow/live) |
| 13 | Research-log hash chain verifies end-to-end | `scripts/verify_research_log.py`; iron rule 6 | exit code 0 | `{{exit_code}}` | `[ ]` |
| 14 | Deployment-ladder stage-gate preconditions still satisfied | `config/deployment_ladder.yaml` `stages.<stage>.entry_gate` | all gates true | `{{gate_status}}` | `[ ]` |

---

## 6. Proposed TradePlan summary

| Field | Value |
|---|---|
| Number of orders | `{{n_orders}}` (buys `{{n_buys}}`, sells `{{n_sells}}`) |
| Notional (USD) | `{{notional}}` |
| Expected cost (bps) | `{{cost_bps}}` (source: `src/nyse_core/cost_model.py`) |
| Expected turnover (this cycle, %) | `{{turnover_pct}}` |
| Largest proposed position (symbol, %) | `{{symbol}}`, `{{weight_pct}}%` |
| TWAP duration (min) | `{{duration_min}}` (from `config/strategy_params.yaml:execution.twap_duration_minutes`) |
| Max ADV participation rate | `{{participation_pct}}%` (from `config/strategy_params.yaml:execution.max_participation_rate`) |

---

## 7. Operator sign-off

I have reviewed each check above. Rows marked `[ ]` with no tick are NOT
passing and I am therefore NOT authorized to submit orders today until they
are addressed and this form is re-signed.

- **All §2 VETO-class rows pass:** `[ ]`
- **All §3 risk-limit rows pass:** `[ ]`
- **All §4 data rows pass:** `[ ]`
- **All §5 iron-rule rows pass:** `[ ]`
- **TradePlan summary in §6 is within expected envelope for current stage:** `[ ]`

| Field | Value |
|---|---|
| Operator | `{{operator_name}}` |
| Signature (commit SHA of this file in retention branch) | `{{commit_sha}}` |
| Time (UTC) | `{{HH:MM:SS}}` |

---

## 8. Exceptions and escalations

If any check failed and orders were still submitted (not the default — requires
explicit written override):

| Field | Value |
|---|---|
| Failed check IDs | `{{ids}}` |
| Reason for override | `{{text}}` |
| Approver | `{{name}}` |
| Referenced authorization in GOVERNANCE_LOG.md | `{{GL-NNNN}}` |
| Rollback condition | `{{text}}` |

Overrides without a `GL-NNNN` governance-log reference are violations of
`docs/GOVERNANCE_LOG.md` §2 change protocol.
