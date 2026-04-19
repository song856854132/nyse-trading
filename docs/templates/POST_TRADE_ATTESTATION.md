# Post-Trade Compliance Attestation — DAILY EOD

> **Purpose.** Documented end-of-day reconciliation required by **SEC Rule 15c3-5**
> (Market Access — post-order risk monitoring) and **FINRA Rule 3110**
> (Supervision — evidence of daily review). Completed **after** the close and
> after all fills have been reconciled from NautilusTrader to `live.duckdb`.
>
> **Status:** template (frozen 2026-04-19). Changing the checklist items or
> thresholds requires an append row in `docs/GOVERNANCE_LOG.md` citing the
> criterion change — AP-6 applies.
>
> **How this form is used.** For each trading day a new copy is produced at
> `results/attestations/post_trade/<YYYY-MM-DD>.md`. Most fields auto-populate
> from `live.duckdb` via `scripts/run_post_trade_check.py` (to be built);
> remaining fields are filled by the operator. File is committed to a
> retention-protected branch so the signed record is immutable.
>
> **Retention.** 6 years per `docs/SEC_FINRA_COMPLIANCE.md` §2.1 row 2
> ("Fill records / reconciliation → FINRA 3110, 15c3-5 → 6 years").

---

## 1. Header

| Field | Value |
|---|---|
| Trading date (UTC) | `{{YYYY-MM-DD}}` |
| Stage | `paper` / `shadow` / `minimum_live` / `scale` (from `config/deployment_ladder.yaml`) |
| Attestation completed at (UTC) | `{{HH:MM:SS}}` |
| Attestation completed by | `{{operator_name}}` |
| Preparer (if different) | `{{system_or_operator}}` |
| Corresponding pre-trade attestation | `results/attestations/pre_trade/{{YYYY-MM-DD}}.md` @ `{{commit_sha}}` |
| Signed | `[ ] Yes / [ ] No (reconciliation incomplete until signed)` |

---

## 2. Fills vs TradePlan reconciliation

Source: `src/nyse_ats/storage/live_store.py:161-187` `record_fill`,
`src/nyse_ats/storage/live_store.py:191-215` `get_current_positions`.

| # | Metric | Source of truth | Expected | Observed | Pass? |
|---|---|---|---|---|---|
| 1 | Orders submitted | TradePlan in `live.duckdb.trade_plans` | `{{n_orders_planned}}` | `{{n_orders_planned}}` | `[ ]` |
| 2 | Orders filled (full or partial) | `live.duckdb.fills` count | `{{n_orders_planned}}` (ideal) | `{{n_orders_filled}}` | `[ ]` |
| 3 | Fill rate | filled / submitted | ≥ 95% (graduation gate `fill_rate_gt` in `config/deployment_ladder.yaml:40`) | `{{fill_rate_pct}}%` | `[ ]` |
| 4 | Rejection rate | rejected / submitted | < 5% (graduation gate `rejection_rate_lt` in `config/deployment_ladder.yaml:40`) | `{{rejection_rate_pct}}%` | `[ ]` |
| 5 | Mean slippage (bps) | mean of `fills.slippage_bps` for today | < 20 bps (graduation gate `mean_slippage_bps_lt` in `config/deployment_ladder.yaml:40`) | `{{mean_slip_bps}}` | `[ ]` |
| 6 | Settlement failures today | exception log from broker | = 0 (graduation gate `settlement_failures_eq` in `config/deployment_ladder.yaml:40`) | `{{n_settlement_failures}}` | `[ ]` |

If rows 3, 4, 5, or 6 fail and stage is `shadow` or later: stage-gate
preconditions for the next graduation are NOT met — a row must be appended to
`docs/GOVERNANCE_LOG.md` under the stage-graduation authorization point in §5.

---

## 3. Rejection and partial-fill detail

Complete this section only if row 2 or row 4 in §2 indicates rejections or
partials.

| Order ID | Symbol | Side | Planned shares | Filled shares | Rejection reason | Operator action |
|---|---|---|---|---|---|---|
| `{{oid}}` | `{{symbol}}` | `{{side}}` | `{{planned}}` | `{{filled}}` | `{{reason_code}}` | `{{action}}` |

Rejection reason codes follow NautilusTrader's `OrderRejected` enum. If the
reason is `RISK_EXCEEDED`, `INSUFFICIENT_CAPITAL`, or `MARKET_HALTED`, record
the incident in `docs/AUDIT_TRAIL.md` and append to `docs/GOVERNANCE_LOG.md` if
any override was applied.

---

## 4. Daily P&L vs risk limits

Source: `src/nyse_ats/storage/live_store.py:263-287` `record_daily_pnl`.

| # | Metric | Source | Threshold | Observed | Pass? |
|---|---|---|---|---|---|
| 7 | Gross daily return (%) | `daily_pnl.gross_return` | informational | `{{gross_pct}}%` | n/a |
| 8 | Net daily return (%) | `daily_pnl.net_return` | > `daily_loss_limit` = -3% (`config/strategy_params.yaml:34`) | `{{net_pct}}%` | `[ ]` |
| 9 | Cost incurred today (bps on notional) | `daily_pnl.cost / notional * 1e4` | ≤ `{{expected_cost_bps}}` from pre-trade §6 (cost envelope) | `{{cost_bps}}` | `[ ]` |
| 10 | Cumulative drawdown from peak equity | rolling max – current equity | > `F3` = -25% (`config/falsification_triggers.yaml:38`) | `{{dd_pct}}%` | `[ ]` |

If row 8 fails (daily loss > 3%): the kill switch SHOULD have triggered during
the session. Verify `config/strategy_params.yaml:38 kill_switch` was flipped to
`true` and that no additional orders were submitted after the breach. Record
the incident chain in `docs/AUDIT_TRAIL.md`.

If row 10 fails (drawdown past -25%): F3 VETO fires. Halt live trading, switch
to paper, investigate per `docs/RISK_REGISTER.md` row 6 response protocol.
Append a row in `docs/GOVERNANCE_LOG.md` citing the VETO authorization.

---

## 5. Realized concentration report

Source: `src/nyse_ats/storage/live_store.py:217-259` `get_position_weights`.

| # | Metric | Threshold source | Threshold | Observed | Pass? |
|---|---|---|---|---|---|
| 11 | Max realized single-stock weight | `config/strategy_params.yaml:29` (`max_position_pct`) | ≤ 0.10 | `{{max_w}}` | `[ ]` |
| 12 | Max realized GICS-sector weight | `config/strategy_params.yaml:30` (`max_sector_pct`) | ≤ 0.30 | `{{max_sector_w}}` | `[ ]` |
| 13 | Realized ex-post beta vs SPY (if ≥ 20 days of history) | `config/strategy_params.yaml:32-33` | ∈ [0.5, 1.5] | `{{beta}}` | `[ ]` |
| 14 | Positions > 5% with earnings within 2 trading days | `config/strategy_params.yaml:35-36` | 0 | `{{n_ern}}` | `[ ]` |

Row 11 > 0.15 triggers F4 WARNING. Row 11 > 0.10 but ≤ 0.15 is a controlled
exceedance (e.g., price drift) that the next rebalance must correct. If the
exceedance persists across two rebalance cycles, a GOVERNANCE_LOG row must
document the exception.

---

## 6. Falsification trigger check (F1-F8)

Source: `src/nyse_ats/storage/live_store.py:312-345` `record_falsification_check`,
rules at `config/falsification_triggers.yaml`.

| # | Trigger | Window | Threshold | Observed | Severity on fail | Pass? |
|---|---|---|---|---|---|---|
| F1 | Signal death (rolling 60d IC < 0.01 for 2 months) | rolling 60 × 2 | 0.01 | `{{F1_ic}}` | VETO | `[ ]` |
| F2 | Factor death (3 core-factor sign flips in 2 months) | 2 months | 3 | `{{F2_flips}}` | VETO | `[ ]` |
| F3 | Excessive drawdown | trailing cumulative | -25% | `{{F3_dd}}` | VETO | `[ ]` |
| F4 | Concentration breach | today | 15% | `{{F4_max_w}}` | WARNING | `[ ]` |
| F5 | Turnover spike | trailing month | 200% | `{{F5_turn}}` | WARNING | `[ ]` |
| F6 | Cost drag | trailing year | 5% | `{{F6_cost_drag}}` | WARNING | `[ ]` |
| F7 | Regime anomaly (benchmark unsplit-adjusted) | today | false | `{{F7_regime}}` | WARNING | `[ ]` |
| F8 | Data staleness | today | 10 days | `{{F8_days}}` | WARNING | `[ ]` |

Any VETO-severity row (F1, F2, F3) that fails: live trading halts. Switch to
paper mode, append row in `docs/GOVERNANCE_LOG.md` under the kill-switch
authorization point, record in `docs/AUDIT_TRAIL.md`.

Any WARNING-severity row (F4-F8) that fails: reduce exposure to 60%, review
within 1 week. Dashboard + Telegram alert should have fired during the session
(cross-check with `src/nyse_ats/monitoring/falsification.py`).

---

## 7. Cumulative cost drag and turnover

| # | Metric | Window | Threshold | Observed | Pass? |
|---|---|---|---|---|---|
| 15 | Cumulative cost drag (annualized %) | trailing 252 days | < F6 = 5% | `{{annual_cost_drag}}%` | `[ ]` |
| 16 | Monthly turnover (% of NAV) | trailing 21 days | < F5 = 200% | `{{monthly_turnover}}%` | `[ ]` |

Cost drag is the **primary** monitoring metric per `Lesson_Learn.md` — check
before Sharpe, before alpha decay. If row 15 trends toward 3%+, flag to the
investment committee even before F6 fires.

---

## 8. Corporate actions detected in window

| Symbol | Action type | Effective date | Adjustment applied? | Source |
|---|---|---|---|---|
| `{{symbol}}` | `{{split / dividend / merger / delist}}` | `{{YYYY-MM-DD}}` | `{{yes / no}}` | `src/nyse_ats/storage/corporate_action_log.py` |

If any row shows `Adjustment applied? = no`: affected positions must be
re-priced before the next rebalance. Append a row in `results/research_log.jsonl`
via `scripts/append_research_log.py` with event `corporate_action_adjustment_deferred`
and reason.

---

## 9. Iron-rule compliance (post-trade)

| # | Check | Source | Expected | Observed | Pass? |
|---|---|---|---|---|---|
| 17 | No fill timestamp > today + 2 trading days (T+2 settlement window) | `live.duckdb.fills.fill_timestamp` | n/a (forward-looking guard) | `{{max_ts}}` | `[ ]` |
| 18 | Research-log hash chain verifies end-to-end after today's appends | `scripts/verify_research_log.py` | exit code 0 | `{{exit_code}}` | `[ ]` |
| 19 | No post-2023 date injected into research pipeline (research stage only) | iron rule 1, `docs/RALPH_LOOP_TASK.md:7` | N/A at paper or later stages | `{{stage}}` | `[ ]` (N/A at paper/shadow/live) |

---

## 10. Operator sign-off

I have reviewed each section above. Rows marked `[ ]` with no tick are NOT
passing. If any §4, §6, or §9 row failed, a `GL-NNNN` authorization row in
`docs/GOVERNANCE_LOG.md` must exist before the next trading day begins.

- **All §2 reconciliation rows pass:** `[ ]`
- **All §4 P&L rows pass:** `[ ]`
- **All §5 concentration rows pass:** `[ ]`
- **All §6 falsification rows pass:** `[ ]`
- **All §7 drag/turnover rows pass:** `[ ]`
- **All §8 corporate-action rows applied:** `[ ]`
- **All §9 iron-rule rows pass:** `[ ]`

| Field | Value |
|---|---|
| Operator | `{{operator_name}}` |
| Signature (commit SHA of this file in retention branch) | `{{commit_sha}}` |
| Time (UTC) | `{{HH:MM:SS}}` |

---

## 11. Exceptions and escalations

If any check failed and the next trading day has not been halted (not the
default — requires explicit written override):

| Field | Value |
|---|---|
| Failed check IDs | `{{ids}}` |
| Reason for override | `{{text}}` |
| Approver | `{{name}}` |
| Referenced authorization in GOVERNANCE_LOG.md | `{{GL-NNNN}}` |
| Rollback condition | `{{text}}` |
| Incident row in AUDIT_TRAIL.md | `{{AT-NNNN}}` |

Overrides without both a `GL-NNNN` and an `AT-NNNN` reference are violations
of `docs/GOVERNANCE_LOG.md` §2 change protocol and `docs/AUDIT_TRAIL.md` §2
logging protocol.
