# Gate Calibration Audit — G0 through G5

> **Audit ID:** `GCA-2026-04-23`
> **Audit scope:** `config/gates.yaml` vs plan-of-record
> **Audit type:** structural calibration (AP-6 pre-registration compliance check)
> **Prepared by:** RALPH loop iter-9 (Wave 3 gate calibration audit)
> **Audit commit:** at preparation time, chain tip `ed7cce93a65a8aa4376850e2b38f3d261f9dcd3baf86b4be60422231ef2d92f0` (iter-8)
> **Findings posture:** this iteration PRESENTS findings only. No threshold, metric, direction, or admission is changed by this memo. Any correction is a separate operator-authorized event (iter-11 conditional one-way door).

---

## 0. Why this audit exists

`docs/RALPH_LOOP_RESEARCH_WAVES.md` line 67 mandates Wave 3 (iter 9-11) to reconcile `config/gates.yaml` against the plan-of-record before any further factor admission. AP-6 ("Never expand or redefine evaluation criteria after results are observed") requires that the frozen gate definitions match what was written into the plan **before** the first factor screen ran. Any divergence is a pre-registration violation and must be logged as a finding — even if the divergence is "an improvement" the plan did not anticipate.

**Plan-of-record sources audited here:**

1. `/.claude/plans/dreamy-riding-quasar.md` §`gates.yaml (G0-G5)` — the accepted plan from the CEO + engineering review on 2026-04-15.
2. `docs/templates/factor_screen_memo.md` §3 "G0–G5 gate verdicts" (frozen layout 2026-04-19) — independently restates the plan's gate family.
3. `docs/GOVERNANCE_LOG.md` row GL-0002 (2026-04-18) — cites the plan's gate family as if it were in force.

**Authoritative-in-force sources audited here:**

1. `config/gates.yaml` (sha256 `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`) — the YAML consumed by the screening script.
2. `src/nyse_core/gates.py:DEFAULT_GATE_CONFIG` — the Python constant used when gate_config is None.
3. `src/nyse_core/factor_screening.py:screen_factor` lines 927-932 — the docstring enumerating the six gates the function actually evaluates.
4. `results/factors/*/gate_results.json` — the JSON evidence files produced by six prior screens (ivol_20d, high_52w, momentum_2_12, piotroski, accruals, profitability).

---

## 1. Executive summary of finding

The six gates as implemented in code + config are a **different gate family** from the six gates enumerated in the plan. Every gate differs in **metric identity** — not just threshold value, not just direction. This is a gate-semantic redesign, not a calibration drift. The redesign was introduced at commit `339fa10` (2026-04-18) with message *"ci: land CI/CD workflow + source tree to close TODO-6"* — a commit whose stated purpose is CI/CD infrastructure, not gate redefinition.

| | Plan-of-record gate family | In-force gate family |
|---|---|---|
| G0 | Coverage: `universe_coverage_pct` ≥ 0.50 | OOS Sharpe: `oos_sharpe` ≥ 0.30 |
| G1 | Standalone quality: `ic_ir` ≥ 0.02 | Permutation significance: `permutation_p` < 0.05 |
| G2 | Redundancy: `max_corr_with_existing` < 0.50 | Directional strength: `ic_mean` ≥ 0.02 |
| G3 | Walk-forward improvement: `oos_sharpe_delta_vs_baseline` > 0.00 | IC information ratio: `ic_ir` ≥ 0.50 |
| G4 | Full-sample improvement: `full_sample_sharpe_delta` > 0.00 | Drawdown ceiling: `max_drawdown` ≥ −0.30 |
| G5 | Date alignment: `baseline_date_gap_days` ≤ 30 | Marginal ensemble contribution: `marginal_contribution` > 0.00 |

**No row matches on both metric identity and threshold.** Two rows share a threshold value (0.02 and 0.50) but attached to different metrics in different rows.

**GL-0002 through GL-0008** in `docs/GOVERNANCE_LOG.md` (reject rows for six screened factors) cite the **plan's gate family** in their "Rationale / Criteria" column ("*G0 (coverage ≥ 50%), G1 (IC_IR ≥ 0.02), G2 (corr < 0.50), G3 (OOS Sharpe delta > 0), G4 (full-sample Sharpe delta > 0), G5 (baseline date gap ≤ 30d)*") but the corresponding `results/factors/*/gate_results.json` evidence files were produced by the **in-force gate family** (see §3 for the ivol_20d cross-walk). Neither the screens nor the governance-log rows cross-reference the other family. There is **no governance log row authorizing the gate semantics redesign**.

---

## 2. Per-gate audit table

Each row cites: the plan-of-record specification (with line number), the in-force specification (with file and line), and the commit that introduced the in-force value. **No correction is proposed**. The "Discrepancy class" field categorizes each divergence for iter-10 triage.

### G0

| Field | Value |
|---|---|
| Plan spec | `universe_coverage_pct` ≥ 0.50 — plan line in `dreamy-riding-quasar.md` §gates.yaml |
| Template spec | `universe_coverage_pct` ≥ 0.50 — `docs/templates/factor_screen_memo.md:105` |
| GOVERNANCE_LOG cite | "coverage ≥ 50%" — `docs/GOVERNANCE_LOG.md:71` (GL-0002) |
| In-force metric | `oos_sharpe` |
| In-force threshold | 0.30 |
| In-force direction | ≥ |
| In-force file:line | `config/gates.yaml:8-12`; `src/nyse_core/gates.py:86`; `src/nyse_core/factor_screening.py:967-970` |
| Commit introducing in-force | `339fa10` (2026-04-18, *"ci: land CI/CD workflow + source tree to close TODO-6"*) |
| Discrepancy class | **Metric redefinition**: in-force measures signal magnitude (Sharpe of long-short quintile portfolio), plan measures universe coverage (what fraction of the investable universe has the factor computable). These are not comparable quantities. |

### G1

| Field | Value |
|---|---|
| Plan spec | `ic_ir` ≥ 0.02 — plan line in `dreamy-riding-quasar.md` §gates.yaml |
| Template spec | `ic_ir` ≥ 0.02 — `docs/templates/factor_screen_memo.md:106` |
| GOVERNANCE_LOG cite | "IC_IR ≥ 0.02" — `docs/GOVERNANCE_LOG.md:71` (GL-0002) |
| In-force metric | `permutation_p` |
| In-force threshold | 0.05 |
| In-force direction | < |
| In-force file:line | `config/gates.yaml:14-18`; `src/nyse_core/gates.py:87`; `src/nyse_core/factor_screening.py:971-982` |
| Commit introducing in-force | `339fa10` (2026-04-18) |
| Discrepancy class | **Metric redefinition + threshold numeric coincidence**: the plan wanted a standalone quality gate (IC_IR ≥ 0.02 is the Lesson_Learn threshold for "tradeable without an ensemble"). The in-force gate is a statistical-significance gate (block-bootstrap permutation p < 0.05). These answer different questions (effect size vs effect distinguishability from noise). IC_IR is not absent from the in-force family — it moved to G3 at threshold 0.50, a **25× tighter** threshold than the plan's 0.02. |

### G2

| Field | Value |
|---|---|
| Plan spec | `max_corr_with_existing` < 0.50 — plan line in `dreamy-riding-quasar.md` §gates.yaml |
| Template spec | `max_corr_with_existing` < 0.50 — `docs/templates/factor_screen_memo.md:107` |
| GOVERNANCE_LOG cite | "corr < 0.50" — `docs/GOVERNANCE_LOG.md:71` (GL-0002) |
| In-force metric | `ic_mean` |
| In-force threshold | 0.02 |
| In-force direction | ≥ |
| In-force file:line | `config/gates.yaml:20-24`; `src/nyse_core/gates.py:88`; `src/nyse_core/factor_screening.py:984-987` |
| Commit introducing in-force | `339fa10` (2026-04-18) |
| Discrepancy class | **Metric redefinition + semantic swap**: the plan's G2 is a redundancy gate (no admission if the candidate correlates > 0.50 with an already-admitted factor). The in-force G2 is a directional-strength gate (mean Spearman IC across rebalance dates). Redundancy checking is **absent from the in-force gate family** — there is no `max_corr_with_existing` metric in `evaluate_factor_gates`. The Lesson_Learn-era redundancy control is structurally missing. |

### G3

| Field | Value |
|---|---|
| Plan spec | `oos_sharpe_delta_vs_baseline` > 0.00 — plan line in `dreamy-riding-quasar.md` §gates.yaml |
| Template spec | `oos_sharpe_delta_vs_baseline` > 0.00 — `docs/templates/factor_screen_memo.md:108` |
| GOVERNANCE_LOG cite | "OOS Sharpe delta > 0" — `docs/GOVERNANCE_LOG.md:71` (GL-0002) |
| In-force metric | `ic_ir` |
| In-force threshold | 0.50 |
| In-force direction | ≥ |
| In-force file:line | `config/gates.yaml:26-30`; `src/nyse_core/gates.py:89`; `src/nyse_core/factor_screening.py:988-991` |
| Commit introducing in-force | `339fa10` (2026-04-18) |
| Discrepancy class | **Metric redefinition**: the plan asks "does this factor add OOS Sharpe on top of the current ensemble's baseline?" (a delta-Sharpe test against an existing benchmark). The in-force asks "is this factor's standalone IC-IR ≥ 0.50?" (a standalone-quality test against an absolute bar). The plan's delta-vs-baseline test is **absent from the in-force gate family**. It re-appears partially in G5 (`marginal_contribution`, the IC delta from ensemble addition), but as an IC delta not a Sharpe delta, and without the walk-forward framing the plan required. |

### G4

| Field | Value |
|---|---|
| Plan spec | `full_sample_sharpe_delta` > 0.00 — plan line in `dreamy-riding-quasar.md` §gates.yaml |
| Template spec | `full_sample_sharpe_delta` > 0.00 — `docs/templates/factor_screen_memo.md:109` |
| GOVERNANCE_LOG cite | "full-sample Sharpe delta > 0" — `docs/GOVERNANCE_LOG.md:71` (GL-0002) |
| In-force metric | `max_drawdown` |
| In-force threshold | −0.30 |
| In-force direction | ≥ (i.e. no worse than) |
| In-force file:line | `config/gates.yaml:32-36`; `src/nyse_core/gates.py:90`; `src/nyse_core/factor_screening.py:992-995` |
| Commit introducing in-force | `339fa10` (2026-04-18) |
| Discrepancy class | **Metric redefinition**: the plan's G4 is the OOS-vs-IS robustness check ("does the improvement persist on full-sample?"). The in-force G4 is a drawdown-ceiling filter. These answer entirely different questions — the plan's is a consistency / anti-overfit check, the in-force is a risk-tolerance filter. Full-sample robustness testing is **absent from the in-force gate family**. |

### G5

| Field | Value |
|---|---|
| Plan spec | `baseline_date_gap_days` ≤ 30 — plan line in `dreamy-riding-quasar.md` §gates.yaml |
| Template spec | `baseline_date_gap_days` ≤ 30 — `docs/templates/factor_screen_memo.md:110` |
| GOVERNANCE_LOG cite | "baseline date gap ≤ 30d" — `docs/GOVERNANCE_LOG.md:71` (GL-0002) |
| In-force metric | `marginal_contribution` |
| In-force threshold | 0.00 |
| In-force direction | > |
| In-force file:line | `config/gates.yaml:38-42`; `src/nyse_core/gates.py:91`; `src/nyse_core/factor_screening.py:996-1020` |
| Commit introducing in-force | `339fa10` (2026-04-18) |
| Discrepancy class | **Metric redefinition + semantic swap**: the plan's G5 is a data-hygiene gate (candidate's evaluation window must end within 30 days of the baseline ensemble's, to prevent a stale-data comparison). The in-force G5 is the delta-IC-from-ensemble-addition test (a genuine anti-redundancy contribution gate). Both are defensible screening concepts — but they answer different questions, and the plan's data-hygiene gate is **absent from the in-force gate family**. |

---

## 3. Cross-walk: ivol_20d gate_results.json vs GL-0002

`results/factors/ivol_20d/gate_results.json` (produced 2026-04-18 by `screen_factor`):

```
G0  (oos_sharpe)              = -1.9156   threshold ≥ 0.30    → FAIL
G1  (permutation_p)           =  1.0000   threshold < 0.05    → FAIL
G2  (ic_mean)                 = -0.0079   threshold ≥ 0.02    → FAIL
G3  (ic_ir)                   = -0.0545   threshold ≥ 0.50    → FAIL
G4  (max_drawdown)            = -0.5777   threshold ≥ -0.30   → FAIL
G5  (marginal_contribution)   =  1.0000   threshold > 0.00    → PASS
passed_all = false
```

`docs/GOVERNANCE_LOG.md:71` cites this verdict as evidence for GL-0002 (reject ivol_20d) but describes the gates as:

> `config/gates.yaml` G0 (coverage ≥ 50%), G1 (IC_IR ≥ 0.02), G2 (corr < 0.50), G3 (OOS Sharpe delta > 0), G4 (full-sample Sharpe delta > 0), G5 (baseline date gap ≤ 30d)

The governance row names the plan's gate family. The evidence file reports the in-force gate family. A reader of GL-0002 cannot reproduce the rejection from the governance row alone — they must inspect the JSON to learn which gates actually fired and under which thresholds. **This is the concrete audit failure mode**: the pre-registered record does not match the recorded evidence.

Identical mismatches apply to GL-0003 (earnings_surprise, `docs/GOVERNANCE_LOG.md:72`), GL-0004 (high_52w, :73), GL-0005 (momentum_2_12, :74), GL-0006 (piotroski, :75), GL-0007 (accruals, :76), and GL-0008 (profitability, :77).

---

## 4. Commit trail

Every in-force gate value traces to a single commit:

| Commit | Date | Message | Files affecting gates |
|---|---|---|---|
| `339fa10` | 2026-04-18 | *"ci: land CI/CD workflow + source tree to close TODO-6"* | `config/gates.yaml` (new), `src/nyse_core/gates.py` (new), `src/nyse_core/factor_screening.py` (new) |

`git log --all --oneline -- config/gates.yaml` returns exactly one commit, `339fa10`. The YAML has not been edited since. The in-force gate family therefore has one origin point and has not drifted since landing.

**Commit title discrepancy.** The commit is titled *"CI/CD workflow + source tree to close TODO-6"*. Its body describes ruff, mypy, gitleaks, pytest configuration. It does not mention gate definitions. The gate redefinition rode along with an infrastructure commit and was not individually reviewed. No `GOVERNANCE_LOG.md` row authorizes commit `339fa10` as a gate-semantics freeze.

**Freeze-row inventory.** `docs/GOVERNANCE_LOG.md:70` (GL-0001) freezes `config/falsification_triggers.yaml` on 2026-04-15. No analogous row freezes `config/gates.yaml`. The governance log §88 ("First factor clears G0-G5 on real data") presumes a frozen gate family exists and cites `config/gates.yaml:1-20` as the freeze anchor, but the file was introduced three days after GL-0001 (on 2026-04-18) and the governance log was never updated with a GL row to record that freeze.

---

## 5. What is absent from the in-force gate family

Tabulated for iter-10 triage. Each row names a concept the plan required that the in-force family does not implement.

| Missing concept (from plan) | Nearest in-force approximation | Gap |
|---|---|---|
| Universe coverage gate (≥ 50%) | none | No minimum-coverage check in `evaluate_factor_gates`. A factor computable on only 10% of the universe still passes the coverage dimension implicitly. |
| Redundancy gate (corr < 0.50 vs existing admitted factors) | G5 `marginal_contribution` > 0.00 (post-ensemble IC delta test) | Marginal IC contribution is related but not equivalent to max-pairwise-correlation. A factor can have positive marginal IC yet still correlate > 0.50 with an existing factor; a factor can correlate < 0.50 yet have zero marginal contribution. The plan wanted both; in-force gives only the contribution side. |
| Walk-forward Sharpe delta gate | G3 `ic_ir` ≥ 0.50 (standalone IR) | Not a delta test. The in-force gate asks "is standalone IR strong?", not "does adding the factor raise the ensemble's OOS Sharpe?" |
| Full-sample Sharpe delta gate | none | No full-sample-vs-OOS robustness check. |
| Date-alignment hygiene gate (≤ 30d baseline gap) | none | No baseline-date gap check in `evaluate_factor_gates`. A factor with an evaluation window ending 6 months before the baseline's could still be admitted. |

Conversely, three in-force gates have **no plan-of-record counterpart**:

| In-force gate without plan counterpart | What it checks |
|---|---|
| G0 `oos_sharpe` ≥ 0.30 | Standalone long-short quintile OOS Sharpe. Pure level check, not a delta. |
| G1 `permutation_p` < 0.05 | Block-bootstrap permutation significance (raw, not Romano-Wolf adjusted). |
| G4 `max_drawdown` ≥ −0.30 | Drawdown ceiling. Risk-tolerance filter, not statistical. |

These three concepts are operationally sensible for factor screening but were not in the plan. Their introduction at commit `339fa10` has no governance-log authorization.

---

## 6. AP-6 posture

AP-6 states: *"Never expand experiment menu after results. phaseNN_plan.md written BEFORE code."* (plan §anti-patterns.) The in-force gate family was written into code at 2026-04-18 (`339fa10`). Six factor screens then ran against it on 2026-04-18 (GL-0002 through GL-0008). This is **technically** compliant with AP-6 in the sense that the in-force gates froze before any factor was screened against them — but it is **procedurally** non-compliant because the freeze was not recorded in the governance log, was not cross-referenced against the plan, and was documented only implicitly through the commit message of an unrelated CI infrastructure PR.

**The AP-6 test is not "did the gates freeze before screens ran?" It is "did the gates that ran match the gates the plan registered?"** On the latter test, the in-force family fails — the plan registered a different family, and `docs/templates/factor_screen_memo.md` (frozen 2026-04-19, after the screens) recorded the plan's family as canonical even though the screens that had already run used the in-force family.

---

## 7. Iron-rule compliance of this audit

This memo itself complies with every iron rule documented in `.claude/ralph-loop.local.md` and `docs/RALPH_LOOP_RESEARCH_WAVES.md`:

1. **No post-2023 dates:** this audit references only static plan, config, and commit artifacts — no market-data load.
2. **No AP-6 threshold changes:** no threshold, metric, or direction in `config/gates.yaml`, `config/falsification_triggers.yaml`, or `config/strategy_params.yaml` is modified. The memo is pure documentation.
3. **No DB mocks:** no tests added.
4. **No secret leakage:** no adapter or network code touched.
5. **No --no-verify:** commit will run all six pre-commit hooks (gitleaks, ruff check, ruff format, mypy, holdout path guard, research-log chain verification).
6. **Hash chain preserved:** this iteration's research-log event appends off iter-8 tip `ed7cce93a65a8aa4376850e2b38f3d261f9dcd3baf86b4be60422231ef2d92f0`.
7. **TODO-11 and TODO-23 untouched.**
8. **iter-0 bit-exactness preserved:** no code path is modified; every prior screen's `gate_results.json` would be regenerated identically if re-run today.

---

## 8. What this audit does NOT do

Per `docs/RALPH_LOOP_RESEARCH_WAVES.md` line 71-73 iter-10 / iter-11 protocol:

- **Does not propose a correction.** Any threshold, metric, or direction change is iter-11 territory and requires explicit operator authorization. This memo presents findings only.
- **Does not re-run any factor screen.** The seven `results/factors/*/gate_results.json` files remain the authoritative evidence. A re-screen against a corrected family is iter-11 post-authorization work.
- **Does not retroactively relabel GL-0002 through GL-0008.** Those governance rows remain as written. Any correction to them is iter-11 authorized work with its own GL row.
- **Does not choose between "plan was wrong" and "config was wrong".** Either the plan or the config (or both) must change for the audit to close. That choice is the operator's, not this memo's.

---

## 9. iter-10 handoff

iter-10 will:

1. Present this memo to the operator via the RALPH loop's scope-announcement protocol.
2. Append a `gate_calibration_audit_findings` event to `results/research_log.jsonl` with severity `CRITICAL` (the pre-registered ground-truth gate family does not match the in-force family) and halt further RALPH loop iteration until the operator responds.
3. Not modify any threshold, metric, direction, or admission verdict.

iter-11 (conditional one-way door) will **only** proceed if the operator has authorized a specific correction path (update plan to match config, update config to match plan, or a third synthesized reconciliation). iter-11 will apply the authorized correction, re-screen all six factors against the corrected family, write an updated governance-log row for each re-screen, and record the new verdicts. iter-11 will not run without explicit authorization.

---

## 10. Research-log anchor (this memo)

Appended as a `gate_calibration_audit_memo` event in iter-9's commit. Chain tip after append will be recorded in the commit body. An auditor can feed the tip hash into `scripts/verify_research_log.py` to reproduce every event back to genesis.

**Chain anchor before append:** `ed7cce93a65a8aa4376850e2b38f3d261f9dcd3baf86b4be60422231ef2d92f0` (iter-8, 2026-04-23).

**Chain anchor after append:** recorded in iter-9 commit body and in `docs/RALPH_LOOP_RESEARCH_WAVES.md` after this memo lands.
