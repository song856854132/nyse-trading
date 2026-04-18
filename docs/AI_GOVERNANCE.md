# AI / ML Governance Policy

**Version:** v0.1 (initial draft)
**Effective date:** 2026-04-18
**Owner:** Operator (single-principal fund; no separate compliance officer until
stage "Minimum Live")
**Next review:** 2026-07-18 (quarterly cadence) and on any material model change

**Purpose.** Establish, in writing, how the NYSE ATS framework selects, deploys,
retrains, and retires machine-learning artifacts; what decisions those artifacts
are permitted to make autonomously; where a human stays in the loop; and what
records are preserved. This policy is the single-page companion to
[`MODEL_VALIDATION.md`](MODEL_VALIDATION.md) (SR 11-7 validation) and
[`MLOPS_LIFECYCLE.md`](MLOPS_LIFECYCLE.md) (operational lifecycle). It exists so
that (a) the researcher can be held to a mechanical standard rather than to
narrative judgment after results arrive, and (b) an LP, auditor, or regulator
has one document that answers "how is AI governed here?" in under five minutes.

**Iron rule.** This policy freezes the AI governance baseline. Loosening any
control (making AI use easier, removing a human-in-loop gate, widening scope
without approval) after a result has been observed is a violation of AP-6 and
invalidates the standing of any model change that benefits from the loosening.
Tightening is permitted at any time with a dated, signed amendment in §12.

---

## 1. Applicable Regulation (snapshot, 2026-04-18)

| Regulation | Effective | Scope relevance to this fund |
|---|---|---|
| **Colorado AI Act (SB 24-205)** | 2026-06-30 | Covers "high-risk AI systems" making consequential decisions about consumers. Single-principal trading is **out of scope** — no consumer decision is automated by this system. Policy still applied as voluntary baseline. |
| **Texas Responsible AI Governance Act (HB 149)** | 2026-01-01 | Prohibits AI use for unlawful discrimination, requires disclosure for consumer-facing AI. **Out of scope** — no consumer interface. Applied voluntarily. |
| **Federal Reserve SR 11-7 (Model Risk Management)** | 2011 (in force) | Applies to bank-affiliated model users. Not directly binding, but industry-standard. See [`MODEL_VALIDATION.md`](MODEL_VALIDATION.md). |
| **SEC Reg BI + Investment Advisers Act §206(4)-7** | In force | Compliance program requirement if/when advisory capacity arises. Not yet triggered (no external investors). |
| **EU AI Act** | Staged 2026-2027 | No EU presence; monitored. |
| **NYSE Rule 2090 / 2111** | In force | Suitability and know-your-customer — not triggered by single-principal trading for own account. |

**Interpretation:** None of the listed statutes currently **binds** this project
at the single-principal / own-account stage. The policy applies them as a
voluntary floor so that the capital-ladder graduation from paper → shadow →
live with external capital does not require a retroactive governance build-out
when stakes are highest.

---

## 2. Models in Scope

Every ML or statistical-learning artifact used anywhere in the pipeline.
Authoritative inventory: [`MODEL_VALIDATION.md` §2 Model Inventory](MODEL_VALIDATION.md).
Quick reference:

| Artifact | Role | Autonomy level | Consequential? |
|---|---|---|---|
| `models/ridge_model.py` | Default combination model (signal blending) | Autonomous within gates | Yes — drives trade decisions |
| `models/gbm_model.py` | Alternative combination model (gated, not deployed) | Gated, not autonomous | Yes — if ever deployed |
| `models/neural_model.py` | Alternative combination model (gated, not deployed) | Gated, not autonomous | Yes — if ever deployed |
| `features/nlp_earnings.py` | Transcript-sentiment extraction | Autonomous feature computation | Partial — one of ≥13 features |
| `drift.py` (3-layer) | Drift detector | Autonomous monitor | No — emits diagnostic only |
| `optimizer.py` | Walk-forward parameter tuner | Autonomous within AP-7 bounds | No — tuning is off-line |
| PCA / correlation deduplication | Feature selection | Autonomous within G2 | No — runs during factor admission |

**Explicitly not in scope.** LLM-based code generation used by the operator
during development (e.g., Claude Code, Codex) — that is a tool for the
*operator*, not a model deployed *in* the trading system. No LLM output is ever
passed to the order router.

---

## 3. Autonomy Ladder (what AI can decide without a human)

This is the core control. Every AI decision is classified into one of five
tiers and each tier has a specific human-in-loop requirement.

| Tier | Description | Example | Human-in-loop |
|---|---|---|---|
| **A0 — advisory only** | Model output is read by the operator; no downstream effect without operator action | `drift.py` warnings, dashboard scores | None — operator reads and acts |
| **A1 — autonomous within gate** | Model runs unattended but subject to a pre-registered gate (G0-G5, F1-F8, A1-A12) | Ridge combination scores feeding `allocator.py` | Gates must fire correctly; operator reviews weekly |
| **A2 — autonomous within kill-switch** | Model issues orders but `risk.py` kill-switch and `falsification.py` can halt | `pipeline.py` weekly rebalance → `nautilus_bridge.py` | Operator on-call; dashboard alerts; Telegram bot |
| **A3 — policy change** | Model would alter its own policy (retrain, reweight, add factor) | Drift-triggered retrain of Ridge | **Human approval required** (see §5) |
| **A4 — out of scope** | No model in the system is permitted here | Autonomous capital allocation, third-party trades, consumer-facing decisions | N/A — forbidden |

All present-day components sit in **A0 – A2**. No A3 retrain has fired.
A4 is reserved — we do not build into it.

---

## 4. Decisions Made by AI and Who They Affect

| Decision | Who it affects | Reversible? |
|---|---|---|
| Weekly portfolio composition (top-N selection) | Single principal (operator's own account) | Yes — next rebalance |
| Exposure level (100% bull / 40% bear) | Single principal | Yes — next rebalance |
| Per-stock weight | Single principal | Yes — within cost tolerance |
| Order slicing (TWAP) | Single principal | No (once submitted) — but bounded by position-size caps |
| Factor admission (G0-G5 outcome) | Research decision | Yes — can re-run on new data |
| Falsification trigger fire (F1-F8) | Halts trading | Yes — can resume after investigation |

**No AI output is consumer-facing, credit-related, employment-related, or
insurance-related.** This is the single most important scope statement in this
document, and it is what places the system outside the core of CO / TX AI Act
scope. Should that ever change (e.g., accepting external investors, publishing
a signal feed), this policy must be re-scoped before the change goes live.

---

## 5. Retraining and Policy-Change Approval Gate

Any event that moves a model across tier A2 → A3 requires a written approval
before the change is applied to the live pipeline. Four classes of change are
recognized:

1. **Model coefficients refit on updated data (same structure).** Permitted
   automatically on a scheduled cadence (weekly Ridge refit within
   walk-forward CV). No approval required; logged to research log.
2. **Model structure change** (e.g., Ridge → GBM, add/remove features).
   Requires:
   - (i) Pre-registered in `OUTCOME_VS_FORECAST.md` with forecast, before
     running the comparison backtest.
   - (ii) PurgedWalkForwardCV evidence that the challenger beats the champion
     by ≥ 0.1 OOS Sharpe AND overfit ratio < 3.0 (see Decision 2 in
     [`FRAMEWORK_AND_PIPELINE.md`](FRAMEWORK_AND_PIPELINE.md) §11).
   - (iii) Operator sign-off in the research log (`event_type:
     "model_structure_change_approved"`).
3. **Gate-threshold change** (G0-G5 or F1-F8). **Forbidden after a result has
   been observed** (AP-6). Only tightening is permitted before a result; any
   loosening requires a new research plan with the new thresholds registered
   in advance.
4. **Sign-convention flip for any factor.** **Forbidden after a result has
   been observed** (AP-6; see OUTCOME_VS_FORECAST.md ivol_20d note for the
   policed precedent).

---

## 6. Bias, Harm, and Discrimination Monitoring

The trading system makes decisions about **stocks**, not about people. CO / TX
AI-Act-style bias monitoring does not map cleanly. The relevant analogs are:

| Concern | Control |
|---|---|
| Factor leakage producing look-ahead (systemic advantage from future data) | `pit.py`, `cv.py` ExecutionPurgedCV, property tests `test_pit_no_leakage.py` |
| Hidden concentration on a single issuer / sector | `risk.py` position cap 10% + sector cap 30%; property tests |
| Over-fitting to an issuer class (e.g., mega-caps only) | G2 IC requirement; regime-conditional investigation (`OUTCOME_VS_FORECAST.md` ivol stratification) |
| Short-bias on low-liquidity names (market-impact harm) | ADV-dependent cost model; `config: min_adv_20d = $500K` |
| Post-earnings window concentration | Earnings-event cap (no position > 5% within 2 days of report) |

**No protected-class or demographic data is ingested or inferred.** If any
future factor would require such data (none planned), it would trigger an A3
review AND a policy amendment here.

---

## 7. Third-Party AI Components

| Component | Provider | Data shared out | Substitutability |
|---|---|---|---|
| FinMind | FinMind (Taiwan) | Ticker universe only; no strategy state | Alternate: Polygon, IEX Cloud |
| SEC EDGAR | U.S. Government | None (read-only public filings) | No alternate; statute of record |
| FINRA short interest | FINRA | None (bi-monthly public dataset) | No alternate |
| Claude Code / Codex (LLM tools) | Anthropic / OpenAI | Development prompts only; **never strategy state, positions, forecasts, P&L** | Substitutable; used only during development |

**Strict rule:** No third-party AI receives live positions, forecasts, P&L, or
trading timestamps. Any future integration that would must clear an A3
review. The memory system at
`~/.claude/projects/-home-song856854132--openclaw-workspace-nyse-trading/memory/`
may contain *research context* (e.g., "user is a quant trader") but **must not**
contain *live strategy state*.

---

## 8. Transparency and Disclosure

At the single-principal stage there is no required disclosure. The following
disclosures become required at graduation:

| Stage | Disclosure |
|---|---|
| Paper (current) | None external; full internal log in research log |
| Shadow | Continue internal log |
| Minimum Live (first external capital) | Provide DDQ pack including this document, `MODEL_VALIDATION.md`, `ODD_PACKAGE.md`, `DDQ_AIMA_2025.md` |
| Scale (multi-LP) | Quarterly investor letter with AI-specific addendum; annual third-party model review |

---

## 9. Record Retention

| Artifact | Retention | Medium |
|---|---|---|
| Research log (`results/research_log.jsonl`) | Permanent, hash-chained (SHA-256), OTS-anchored | Git + OpenTimestamps |
| Model coefficients per rebalance | ≥ 7 years (SEC/FINRA industry norm) | `results/backtests/*/` + `live.duckdb` |
| Gate / falsification-trigger decisions | ≥ 7 years | `results/factors/*/`, `live.duckdb` |
| Config snapshots per run | ≥ 7 years | `results/backtests/*/config_snapshot.yaml` |
| Outcome vs forecast ledger | Permanent | `docs/OUTCOME_VS_FORECAST.md` |
| Abandonment-criteria standing | Permanent | `docs/ABANDONMENT_CRITERIA.md` |
| Calibration tracker | Permanent | `docs/CALIBRATION_TRACKER.md` |
| Operator governance decisions (this document) | Permanent | `docs/AI_GOVERNANCE.md` |

Retention medium: git repository with tamper-evident OpenTimestamps anchoring
on the research log. `scripts/verify_research_log.py` performs chain integrity
checks and is invoked by pre-commit hook (see `scripts/reproduce.sh`).

---

## 10. Incident Response

When an AI-related control fires (F1-F8 VETO, A1-A12 criterion, drift HIGH,
gate mis-fire, data contamination event):

1. **Halt.** `kill_switch: true` in `config/strategy_params.yaml` before any
   investigation. Paper-mode continues for diagnostic purposes only.
2. **Log.** Append a `research_log.jsonl` event with `event_type:
   "ai_control_fired"` and the trigger ID.
3. **Notify.** Telegram alert (operator) + dashboard banner.
4. **Root-cause.** 72-hour cooldown before any mitigation action (see
   `ABANDONMENT_CRITERIA.md` §7 decision protocol).
5. **Document.** Update `OUTCOME_VS_FORECAST.md` Notes column and
   `INDEPENDENT_VALIDATION_DRAFT.md` §7 reviewer recommendation.
6. **Resume only after independent-voice review** (`/codex review` or
   third-party validator signature in `INDEPENDENT_VALIDATION_DRAFT.md` §9).

---

## 11. Known Limitations

- **Single-operator governance.** Until Minimum Live, there is no separate
  compliance officer. All tiers A0 – A3 are approved by the same person. This
  concentrates risk; the 72-hour cooldown in §10 and the outside-voice rule in
  [`INDEPENDENT_VALIDATION_DRAFT.md`](INDEPENDENT_VALIDATION_DRAFT.md) are the
  compensating controls.
- **No automated bias test for stock selection.** Fairness concepts from
  consumer AI do not map; no test is planned.
- **LLM development-tool audit trail is partial.** Conversations with Claude
  Code / Codex are not archived in the research log. The commit history and
  the research log capture the *results* of those conversations, not the
  conversations themselves. This is adequate for code-authorship purposes but
  would not satisfy an EU-AI-Act-style provenance audit.
- **No red-team of the combination model.** Adversarial inputs (e.g.,
  manipulated FinMind feeds) are addressed by `data_quality.py` but have not
  been independently pen-tested.

---

## 12. Amendment Log

| Date | Amendment | Signed by | Rationale |
|---|---|---|---|
| 2026-04-18 | Initial draft | Operator | Pre-registration baseline ahead of CO AI Act effective date 2026-06-30 |

---

*Related: [MODEL_VALIDATION.md](MODEL_VALIDATION.md) (SR 11-7 validation) |
[MLOPS_LIFECYCLE.md](MLOPS_LIFECYCLE.md) (ops lifecycle) |
[ODD_PACKAGE.md](ODD_PACKAGE.md) (operational DD) |
[ABANDONMENT_CRITERIA.md](ABANDONMENT_CRITERIA.md) (pre-live stop thresholds) |
[INDEPENDENT_VALIDATION_DRAFT.md](INDEPENDENT_VALIDATION_DRAFT.md) (independent voice) |
[TODOS.md](TODOS.md)*
