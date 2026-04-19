# Governance / Decision Log

> Status: canonical (2026-04-19). This file is the **authorization register** for
> the NYSE ATS program. It records *who approved what, when, against what
> criteria, with what evidence, and with what dissent* — the audit artifact a
> regulator, LP, or internal Model Risk Committee would ask for.
>
> Distinct from `docs/AUDIT_TRAIL.md`, which records *what ran* (experiments,
> backtests, code changes). This file records *what was sanctioned*.
>
> SR 11-7 §VII ("Governance, Policies, and Controls") reference.

## 1. Scope

This log records authorizations for:

| Category | Examples |
|---|---|
| Deployment-ladder graduations | paper → shadow, shadow → minimum_live, minimum_live → scale |
| Pre-registration freezes | Falsification-trigger freeze, gate-threshold freeze, abandonment-criteria freeze |
| Factor lifecycle decisions | Factor admission (G0-G5 PASS), factor rejection, factor re-screen, deferral |
| Model lifecycle decisions | Model swap (Ridge ↔ GBM ↔ Neural), hyper-parameter change, retraining authorization |
| Kill-switch actions | Kill-switch activation, daily-loss-limit halt, manual VETO override |
| Threshold changes | Any change to `config/gates.yaml`, `config/falsification_triggers.yaml`, `config/strategy_params.yaml:risk` |

## 2. Change protocol — iron rules for this file

1. **Append-only.** Rows are added, never edited, never reordered. If a prior
   decision was wrong, append a *new* row reversing or superseding it and
   cross-reference the original `decision_id`. Never mutate history.
2. **Every row must cite evidence.** The `evidence` column must point to at
   least one of: (a) a `results/research_log.jsonl` hash, (b) a git commit SHA,
   (c) a file path with line range. Decisions without evidence are not
   decisions — they are opinions.
3. **Every row must name an approver.** "The operator" is acceptable for a
   sole-operator program, but the operator name must appear. Future rotations
   append the operator's successor.
4. **Every row must record dissent.** Even if dissent = "none recorded", the
   field is mandatory. The goal is to force the approver to pause and ask
   "what did I not hear?" A silent unanimous approval is more suspicious than a
   recorded objection.
5. **Criteria cited must already exist in a frozen artifact.** You cannot
   invent the graduation criteria during the graduation. Criteria live in
   `config/deployment_ladder.yaml`, `config/falsification_triggers.yaml`,
   `config/gates.yaml` — and the decision cites the file:line range that
   defined them *before* the decision was made. This is AP-6 enforcement at
   the governance layer.
6. **Every row must reference the commit that lands it.** Added in a
   follow-up amendment row if the commit SHA is not known at authoring time.

## 3. Current program state (as of 2026-04-19)

| Dimension | State |
|---|---|
| Lifecycle stage | **Research** (pre-paper) |
| Live capital deployed | $0 |
| Paper capital simulated | $0 (paper-trade script exists but has not been run per iron rule 7) |
| Factors admitted to ensemble | **0 of 6** screened so far |
| Factors rejected on real data | 6: ivol_20d, high_52w, momentum_2_12, piotroski, accruals, profitability |
| Falsification triggers | Frozen 2026-04-15 (`config/falsification_triggers.yaml:5`) |
| Holdout window | 2024-2025 — **untouched** (iron rule 1) |
| Next authorization-relevant milestone | First factor that clears G0-G5 on real data (currently 0/6) |

## 4. Authorization log (append-only)

Schema: `decision_id | date (UTC) | decision | approver(s) | criteria cited | evidence | dissent`

| ID | Date | Decision | Approver(s) | Criteria cited | Evidence | Dissent |
|---|---|---|---|---|---|---|
| GL-0001 | 2026-04-15 | **Freeze falsification triggers** F1–F8 with the 8 thresholds defined in `config/falsification_triggers.yaml`. No retroactive threshold edits permitted under AP-6. | Operator (solo) | AP-6 (plan §anti-patterns); Carver §risk rules; Lesson_Learn §63 | `config/falsification_triggers.yaml:5` `frozen_date: "2026-04-15"`; plan `/home/song856854132/.claude/plans/dreamy-riding-quasar.md` §falsification_triggers.yaml | None recorded. |
| GL-0002 | 2026-04-18 | **Reject factor `ivol_20d`** after G0-G5 screen on real FinMind + EDGAR + FINRA data. Framework-side decision: do not admit to ensemble. | Operator (solo) | `config/gates.yaml` G0 (coverage ≥ 50%), G1 (IC_IR ≥ 0.02), G2 (corr < 0.50), G3 (OOS Sharpe delta > 0), G4 (full-sample Sharpe delta > 0), G5 (baseline date gap ≤ 30d) | `results/factors/ivol_20d/gate_results.json` (`passed_all=False`); research-log line 1 (`[legacy]`, `factor_screen`, `ivol_20d`); research-log line 3; `docs/OUTCOME_VS_FORECAST.md` ivol row | None recorded. |
| GL-0003 | 2026-04-18 | **Defer regime-conditional `ivol_20d` variant** (bull-only TODO-23). Pre/post-2020 IC = -0.007 / -0.009; bull-regime IC = -0.001; bear-regime IC = -0.034. Bull-only variant has no tradeable signal. Do not build. | Operator (solo) | AP-6 (no retroactive conditioning); iron rule 7 (strategy in research, do not expand scope) | `results/investigations/ivol_regime_2026-04-18.json`; research-log line 13 (`investigation_finding`, hash `cfbf5e618e85...`); `docs/TODOS.md` TODO-23 | None recorded. |
| GL-0004 | 2026-04-18 | **Reject factor `high_52w`** after G0-G5 screen. Framework-side decision: do not admit to ensemble. | Operator (solo) | `config/gates.yaml` G0-G5 | `results/factors/high_52w/gate_results.json` (`passed_all=False`); research-log line 11 (`factor_screen`, `high_52w`) | None recorded. |
| GL-0005 | 2026-04-18 | **Reject factor `momentum_2_12`** after G0-G5 screen. Framework-side decision: do not admit to ensemble. | Operator (solo) | `config/gates.yaml` G0-G5 | `results/factors/momentum_2_12/gate_results.json` (`passed_all=False`); research-log line 12 (`factor_screen`, `momentum_2_12`) | None recorded. |
| GL-0006 | 2026-04-18 | **Reject factor `piotroski`** after G0-G5 screen. Framework-side decision: do not admit to ensemble. | Operator (solo) | `config/gates.yaml` G0-G5 | `results/factors/piotroski/gate_results.json`; research-log line 15 + line 18 (`factor_screening`, `piotroski`, `verdict=FAIL`) | None recorded. |
| GL-0007 | 2026-04-18 | **Reject factor `accruals`** after G0-G5 screen. Framework-side decision: do not admit to ensemble. | Operator (solo) | `config/gates.yaml` G0-G5 | `results/factors/accruals/gate_results.json`; research-log line 16 + line 19 (`factor_screening`, `accruals`, `verdict=FAIL`) | None recorded. |
| GL-0008 | 2026-04-18 | **Reject factor `profitability`** after G0-G5 screen. Framework-side decision: do not admit to ensemble. | Operator (solo) | `config/gates.yaml` G0-G5 | `results/factors/profitability/gate_results.json`; research-log line 17 + line 20 (`factor_screening`, `profitability`, `verdict=FAIL`) | None recorded. |
| GL-0009 | 2026-04-18 | **Acknowledge 6-of-6 factor-failure state and pause factor-admission decisions**. Program remains in research. No paper trade authorization requested. Next step: methodology review (label timing, purge gap, universe construction) per `docs/TODOS.md` TODO-24 escalation note before admitting more factors. | Operator (solo) | Plan `/home/song856854132/.claude/plans/dreamy-riding-quasar.md` §verification; RALPH_LOOP_TASK iron rule 7 | research-log line 21 (`doc_gap_closure_v2`); commit `588ffce docs: sync documentation to 6/6 factor-failure state (2026-04-18)` | None recorded. |

## 5. Pending authorization points (criteria frozen; decisions not yet due)

Each row below is a **future** authorization point. Criteria are frozen at the
file:line reference shown. When the decision is triggered, append a new row in
§4 citing the criteria below — do **not** edit the criteria themselves.

| Trigger | Authorization needed | Criteria source | File:line |
|---|---|---|---|
| First factor clears G0-G5 on real data | Admit factor to ensemble | `config/gates.yaml` G0-G5; `docs/FRAMEWORK_AND_PIPELINE.md` §gate evaluation | `config/gates.yaml:1-20` |
| Ensemble Sharpe ≥ 0.5 on research period 2016-2023 | Advance to statistical validation suite | Plan §statistical validation (permutation p < 0.05; Romano-Wolf adjusted p < 0.05; bootstrap CI lower bound > 0) | plan `/home/song856854132/.claude/plans/dreamy-riding-quasar.md` |
| Statistical validation passes | Request parameter-sensitivity review | Plan §parameter sensitivity — Sharpe must stay within ±20% across perturbations | plan §Mode 6 |
| Parameter sensitivity within ±20% | Authorize one-shot holdout test on 2024-2025 | `docs/RALPH_LOOP_TASK.md` iron rule 1; `.claude/skills/alpha-research/` Mode 7 pre-checks | `docs/RALPH_LOOP_TASK.md:7` |
| Holdout Sharpe > 0 (one-shot) | Authorize paper-trade stage entry | `config/deployment_ladder.yaml` stages.paper.entry_gate | `config/deployment_ladder.yaml:7` |
| Paper-stage exit criteria met (90d, IC in range, no VETO) | Authorize shadow-stage entry | `config/deployment_ladder.yaml` stages.shadow.entry_gate | `config/deployment_ladder.yaml:15` |
| Shadow-stage exit criteria met (30d, fills match real ≤ 10bps) | Authorize minimum_live entry | `config/deployment_ladder.yaml` stages.minimum_live.entry_gate + `graduation_criteria` (all 7) | `config/deployment_ladder.yaml:22,35-43` |
| Minimum_live exit criteria met (90d, realized Sharpe > 0, fill_rate > 95%) | Authorize scale-stage entry with capital $500K–$2M | `config/deployment_ladder.yaml` stages.scale.entry_gate | `config/deployment_ladder.yaml:30` |
| VETO F1–F3 fires at any stage | Halt live trading, switch to paper, investigate | `config/falsification_triggers.yaml` F1-F3 severity=VETO | `config/falsification_triggers.yaml:8,16,23` |
| WARNING F4–F8 fires at any stage | Reduce exposure to 60%, review within 1 week | `config/falsification_triggers.yaml` F4-F8 severity=WARNING | `config/falsification_triggers.yaml:28,34,40,46,52` |
| Any change to a frozen threshold | Explicit operator authorization + justification row + post-decision retrospective within 30d | AP-6 (plan §anti-patterns); this file §2 change protocol | plan §AP-6 |
| Model swap (Ridge → GBM → Neural) | Alternative must beat Ridge OOS Sharpe by ≥ 0.10 on research period with identical PurgedWalkForwardCV | `config/strategy_params.yaml:combination.alternatives` gating rule in plan §4 Phase 4 | plan §Phase 4 |
| Kill-switch activation (`strategy_params.yaml:kill_switch=true`) | Operator sets flag; activation is an authorization in itself; reversal requires a post-activation retrospective | plan §risk layer 7 | plan §risk management |

## 6. Reversal / supersede protocol

If a decision must be reversed, append a new row with:
- `decision_id` = next sequential ID
- `decision` = "**Reverse GL-NNNN**: [one-line reason]" or "**Supersede GL-NNNN**: [new terms]"
- `criteria cited` = (a) original criteria that no longer hold, and (b) new criteria now being applied
- `evidence` = new research-log hash + commit SHA + reason the original evidence was insufficient or stale
- `dissent` = mandatory; if there was opposition at the original decision, repeat it here so the reversal is not the first place it appears

Do **not** edit the original row. The audit value is the visible reversal, not
a clean rewrite.

## 7. Owner & review cadence

| Item | Value |
|---|---|
| Owner | Operator (solo, as of 2026-04-19) |
| Review cadence | On every row append (live), plus quarterly sweep for stale pending authorization points |
| Last reviewed | 2026-04-19 (iter-15, TODO-19 close) |
| Next review due | 2026-07-19 or on next authorization event, whichever comes first |
| Escalation path | Operator → Model Risk Committee (not yet seated) → External validator (not yet contracted per `docs/MODEL_VALIDATION.md` §1.5) |

## 8. Cross-references

- `docs/AUDIT_TRAIL.md` — experiment + code-change log (what ran)
- `docs/RISK_REGISTER.md` — risk inventory with owner + review cadence
- `docs/MODEL_VALIDATION.md` §1.5 — independence statement (currently "partial", operator = developer = validator)
- `docs/SEC_FINRA_COMPLIANCE.md` — regulatory mapping for §SEC Rule 15c3-5 / FINRA Rule 3110
- `docs/RALPH_LOOP_TASK.md` — iron rules governing what decisions are even permitted during the current research phase
- `results/research_log.jsonl` — tamper-evident event chain; every row in §4 references at least one chained hash or legacy prologue line
- `config/deployment_ladder.yaml` — canonical source for stage-gate criteria referenced in §5
- `config/falsification_triggers.yaml` — frozen 2026-04-15 (see GL-0001)
