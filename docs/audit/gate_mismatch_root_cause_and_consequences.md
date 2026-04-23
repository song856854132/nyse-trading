# Gate-Mismatch Root Cause and Consequences Analysis

**Memo ID:** GCA-2026-04-23-supplemental
**Audit date:** 2026-04-23
**Wave:** 3 (gate calibration)
**Iteration:** 10 (supplemental — operator-requested)
**Status:** Findings only. No threshold/metric/direction/admission changed. AP-6-safe.
**Companion to:** `docs/audit/gate_calibration_audit.md` (GCA-2026-04-23)
**Prompted by operator question (2026-04-23):** *"A. But I want to investigate further why were both mismatch? And what will happen if we continue using the wrong/mismatch gate parameters?"*

---

## 0. Rationale

The primary audit (GCA-2026-04-23) established **what** diverged: every G0–G5 in
`config/gates.yaml` differs from the plan-of-record in metric identity, not just
threshold value. That memo stopped at the finding. The operator chose correction
path **A** (amend plan to match config) tentatively, conditional on:

- **(Q1)** Why did plan and config mismatch?
- **(Q2)** What happens if we continue using the in-force gate parameters going forward?

This supplemental memo answers both, in order. It changes nothing; it only
surfaces evidence so the operator can accept/reject path A with eyes open.

---

## 1. Executive summary

**Q1 (root cause):** Iter-1 code was authored **off-repo** between the plan's
creation (2026-04-15, commit `902cd41`) and the source-tree's first appearance in
git (2026-04-18, commit `339fa10`). During that window, the implementer rewrote
the G0–G5 gate family against a different design axis (signal quality / absolute
thresholds) rather than the plan's design axis (gatekeeping hygiene / delta
baselines), ran the six factor screens, wrote docs describing the failures — and
bundled the entire source tree into a commit whose message framed it as CI/CD
infrastructure. No plan cross-reference was performed, no GOVERNANCE_LOG row was
created to authorize the redesign, and the descriptive line in `config/gates.yaml`
itself gives it away: *"These gates are aligned with factor_screening.screen_factor()"*
— i.e. the config was written to match the **code**, not the **plan**.

**Q2 (consequences):** Continuing with the in-force gate family means:

- **Lost structural guards (4):** universe-coverage filter (G0 plan), redundancy
  filter (G2 plan), full-sample robustness check (G4 plan), data-hygiene date-gap
  (G5 plan). These are all pre-registered anti-overfit / anti-redundancy /
  anti-coverage-bias protections the plan reserved.
- **Retained signal-quality gates, some tighter:** oos_sharpe ≥ 0.3 (absent from
  plan), permutation_p < 0.05 (absent from plan), max_drawdown ≥ -0.30 (absent
  from plan), ic_ir ≥ 0.5 (plan had 0.02 — **25× looser**), marginal_contribution
  via delta-IC (plan had delta-Sharpe).
- **Concrete failure modes unblocked by the loss of plan-gates** include:
  redundant factor admission (two highly-correlated factors both passing the
  ensemble), coverage-biased factors (e.g. large-cap-only fundamentals passing
  with 40% universe coverage), and overfit factors whose OOS-vs-IS divergence
  would have been caught by G4-plan but is invisible to in-force gates.

**Net:** In-force gates are *stricter on signal quality* and *laxer on portfolio
hygiene*. Path A cements this trade-off. The next memo (iter-11, whichever path)
must be explicit about whether these four lost guards are (a) permanently
abandoned, (b) to be re-added later as supplementary gates (path C retrofit), or
(c) replaced by alternative hygiene mechanisms at the admission or ensemble
layer.

---

## 2. Root cause (Q1) — forensic timeline

### 2.1 Timeline of the iter-1 window

| Date | Commit | Role |
|---|---|---|
| 2026-04-15 | `902cd41` | Initial commit. Reference materials, `Lesson_Learn.md`, `docs/TODOS.md`, `docs/books/` chapters. **No `src/`, no `config/gates.yaml`, no plan.** |
| 2026-04-15 | — (off-repo) | Plan written to `~/.claude/plans/dreamy-riding-quasar.md` (49382 bytes, outside repo). |
| 2026-04-15 | — (off-repo) | GL-0001 freezes `config/falsification_triggers.yaml` (committed at 2026-04-15). **No analogous freeze row for `config/gates.yaml` was ever created.** |
| 2026-04-15 → 2026-04-18 | — (off-repo) | Source tree authored on disk. Six factor screens run: ivol_20d, high_52w, momentum_2_12, piotroski, accruals, profitability. All six FAIL. No commits in this window. |
| 2026-04-18 04:46 | `ad9ab14` | "docs: ship 5-deliverable post-ivol_20d documentation update." Describes ivol_20d FAIL outcome. `src/` still not in git. |
| 2026-04-18 14:18 | `588ffce` | "docs: sync documentation to 6/6 factor-failure state (2026-04-18)." Confirms all six screens complete. `src/` still not in git. |
| 2026-04-18 18:02 | `07d2bfa` | Closes TODO-1 / TODO-2 / TODO-24 citing `src/nyse_ats/monitoring/falsification.py:50-82` and `src/nyse_ats/execution/nautilus_bridge.py:99-157` as evidence — **but those files were not yet in git.** |
| 2026-04-18 20:35 | `339fa10` | "ci: land CI/CD workflow + source tree to close TODO-6." Lands `src/`, `tests/`, `config/`, `scripts/` in one commit. Body explicitly admits: *"Also lands the iter-1 source tree (src/, tests/, config/, scripts/, docs/) that was previously on disk but never committed. This is what the evidence citations in prior CLOSED markers (TODO-1, TODO-2, TODO-24) actually refer to — they can now be verified through git."* |

The ordering is the smoking gun: **documentation of factor-failure narrative
precedes the commit of the code that produced it.** The docs were not describing
a result computed against git-tracked code; they were describing a result
computed against disk-local code that the implementer then back-committed.

### 2.2 Why the redesign wasn't caught — six contributing factors

1. **Commit framing.** `339fa10`'s one-line message is *"ci: land CI/CD workflow
   + source tree to close TODO-6."* A reader scanning git history for
   gate-related changes would not flag this commit. The body buries the
   source-tree admission under CI/CD prose.

2. **No GOVERNANCE_LOG freeze row for `gates.yaml`.** `GL-0001` froze
   falsification triggers on 2026-04-15. No analogous row ever froze
   `config/gates.yaml`. The governance layer had no pre-registered copy of the
   gate family against which to diff the in-force file when it finally appeared.

3. **Config self-aligned to code, not plan.** `config/gates.yaml:5` states:
   *"These gates are aligned with factor_screening.screen_factor() which computes
   each metric from long-short quintile returns, IC series, and ensemble IC
   delta."* This is the smoking gun of the design order: code was written first,
   config was written second to match code, plan was never consulted.

4. **Pre-commit hooks are syntactic, not semantic.** The six pre-commit hooks
   (gitleaks, ruff check, ruff format, mypy, holdout-path guard, research-log
   chain verification) all pass on a gate redesign — they have no knowledge of
   the plan's intent.

5. **GL-0002..GL-0008 rationale column copied plan wording.** Each of the seven
   reject rows lists *"G0 (coverage ≥ 50%), G1 (IC_IR ≥ 0.02), G2 (corr < 0.50),
   G3 (OOS Sharpe delta > 0), G4 (full-sample Sharpe delta > 0), G5 (baseline
   date gap ≤ 30d)"* — the **plan's** gate wording. Yet the evidence column
   points to `results/factors/*/gate_results.json` files produced by the
   **in-force** gates. A reader checking the rationale against the evidence must
   inspect the JSON to see the discrepancy; the row itself reads coherent.

6. **Prior researcher almost flagged it, then reframed.**
   `docs/NYSE_ALPHA_RESEARCH_RECORD.md:373` contains: *"Threshold pre-registration
   review — only admissible if the plan's 0.02 in the text was the genuine
   original intent and 0.5 in gates.yaml was transcription error"*. The earlier
   reviewer noticed the G1 ic_ir numeric mismatch (0.02 vs 0.5) but framed it as
   a possible transcription typo on a single threshold — not as a family-level
   metric redesign. The semantic scope (every metric differs, not just one
   threshold) was not surfaced.

### 2.3 What the iter-1 implementer likely optimized for (hypothesis)

The in-force gate family has a coherent design philosophy of its own: **signal
magnitude + statistical significance + risk ceiling + ensemble delta**. Every
gate maps to a signal-quality test. Absent are the four plan-gates that test for
hygiene properties rather than signal strength (coverage, redundancy,
full-sample-robustness, data-hygiene). The implementer appears to have chosen a
"signal-focused" gate family — likely drawn from common quant screening
literature (Campbell-Harvey-Liu style: Sharpe + significance + robustness via
drawdown ceiling) — without reconciling against the plan's "hygiene-focused"
family.

Both families are defensible research designs. The problem is not that the
in-force family is wrong; the problem is that **the research plan pre-registered
a different family, the divergence was not authorized, and the governance log
rows reference a family that wasn't actually applied**.

---

## 3. Consequences (Q2) — what happens if we continue with in-force gates

### 3.1 Structural guards LOST by not having plan-gates

| Plan gate | What it protected against | In-force replacement | Unblocked failure mode |
|---|---|---|---|
| G0 `universe_coverage_pct ≥ 0.50` | Coverage bias (factor active on tiny subset of universe) | **None** (G0 in-force tests signal magnitude, not coverage) | Factor computable on 10% of universe passes admission; ensemble becomes large-cap-only without intent |
| G2 `max_corr_with_existing < 0.50` | Redundancy (two near-identical factors double-counted) | **None** (G2 in-force tests IC mean, not correlation) | momentum_2_12 + high_52w (typically ρ > 0.6) both admitted; ensemble IR inflated by correlated sources |
| G4 `full_sample_sharpe_delta > 0` | Overfitting (OOS ok by luck, IS contradicts) | `max_drawdown ≥ -0.30` (different property — bounds tail risk, not consistency) | Factor with OOS Sharpe 0.3 and IS Sharpe -0.1 (worked out-of-sample by chance, broken in-sample) passes in-force but would fail plan's G4 |
| G5 `baseline_date_gap_days ≤ 30` | Stale-baseline data hygiene | `marginal_contribution > 0` (tests ensemble-addition value, not data freshness) | Baseline computed 18 months before current data can feed admission; no alert |

### 3.2 What in-force gates PROVIDE that the plan did not

| In-force gate | Property tested | Plan equivalent | Net effect |
|---|---|---|---|
| G0 `oos_sharpe ≥ 0.30` | Standalone signal magnitude | None (plan tested delta, not level) | **Added bar:** factor must clear absolute 0.30 bar independently |
| G1 `permutation_p < 0.05` | Distinguishability from noise | None (plan tested ic_ir only) | **Added bar:** explicit significance test via block bootstrap |
| G2 `ic_mean ≥ 0.02` | Directional IC strength | G1 plan was 0.02 IC_IR; G2 in-force is 0.02 IC **mean** — different quantity | Mostly equivalent directional bar |
| G3 `ic_ir ≥ 0.50` | IC Information Ratio | G1 plan = 0.02 (25× looser) | **Tighter bar:** IC_IR bar raised 25× from plan's level |
| G4 `max_drawdown ≥ -0.30` | Drawdown ceiling | None (plan had no drawdown ceiling) | **Added bar:** explicit tail-risk filter |
| G5 `marginal_contribution > 0` | Ensemble delta-IC | G3 plan was delta-Sharpe (related but distinct) | Replaced one delta test with another |

### 3.3 Concrete failure-mode examples — what could slip through

1. **Redundant admission.** Suppose we later screen `momentum_6_12` and it passes
   the in-force family (reasonable — it's a close sibling of `momentum_2_12`
   which itself failed but with IC signs matching). In-force admission would
   allow both into the ensemble with, say, Spearman IC correlation 0.75 across
   rebalance dates. Plan's G2 would block this at `max_corr_with_existing ≥ 0.50`.
   In-force ensemble would double-count the underlying signal. Impact: inflated
   ensemble IC_IR without proportional Sharpe gain; cost drag per unit alpha
   rises.

2. **Coverage-biased admission.** EDGAR fundamentals have uneven historical
   coverage — a factor computed only from quarterly 10-Q fields common across
   all filers might be computable on 50% of the universe at date t=2016-01-04 but
   95% at date t=2023-12-29. Plan's G0 would require ≥50% universe coverage at
   every rebalance date (a consistency check). In-force has no such filter; a
   factor active on 20% of the universe in early years and 90% in late years
   passes so long as its 8-year-average OOS Sharpe clears 0.30. Impact:
   look-ahead-adjacent hazard — factor's "success" concentrated in later years
   with better coverage; attribution contaminated.

3. **Overfit passage.** A factor with OOS Sharpe 0.32 and IS Sharpe -0.15 would
   pass in-force G0 and likely G1 (permutation test sees the OOS outperformance
   as non-trivially non-random) but would fail plan's G4
   (`full_sample_sharpe_delta > 0`). Plan's G4 is the textbook anti-overfit
   consistency check — an IS/OOS disagreement is a red flag even when OOS is
   positive. In-force drops this check entirely.

4. **Stale-baseline admission.** Plan's G5 guards against comparing a factor's
   marginal contribution against a baseline ensemble computed from data
   months-stale. If the "existing ensemble" factor set was last re-fitted on
   data ending 2022-06-30 but the candidate is screened against 2023-12-31 data,
   plan's G5 flags the 18-month gap. In-force has no such alert; comparison
   against stale baselines is silent.

### 3.4 Severity ranking of the four lost guards

| Guard | Severity of loss | Reasoning |
|---|---|---|
| G2 redundancy | **HIGH** | Directly inflates ensemble IR estimates; primary anti-double-counting defence |
| G4 full-sample robustness | **MEDIUM-HIGH** | Classical anti-overfit; OOS alone is insufficient when training-period length is limited |
| G0 universe coverage | **MEDIUM** | Real risk on fundamentals factors; less of a risk on price/volume factors |
| G5 date-gap hygiene | **LOW-MEDIUM** | Procedural hygiene; in practice the re-fitting cadence limits exposure |

### 3.5 Net assessment

Continuing with the in-force family is **not catastrophic** — the signal-quality
side is measurably stricter than the plan in two places (oos_sharpe ≥ 0.3, ic_ir
≥ 0.5), and three additional checks absent from the plan (permutation test,
drawdown ceiling, signal-magnitude bar) add rigour of their own. But the loss of
the four hygiene guards is a **structural weakening** of the admission funnel,
and the program's posture should be explicit about it rather than silent.

---

## 4. Implications for the four correction paths

This memo does not advocate for a specific path. It provides the evidence base
for the operator's iter-11 decision. To reconnect to the four paths enumerated
in `gate_calibration_audit.md` §7:

| Path | How it handles the consequences | Residual hygiene-gap exposure |
|---|---|---|
| **A** (amend plan to match config) | Accepts the consequences; cements in-force family as the frozen truth going forward | High — all four plan-gates permanently absent unless re-added as supplementary later |
| **B** (amend config to match plan) | Fully restores plan hygiene; discards current evidence; overturns GL-0002..GL-0008 | None — plan becomes truth; new screens run under full plan family |
| **C** (hybrid reconciliation) | Adds the three missing structural gates (coverage + redundancy + date-gap) as supplementary G6/G7/G8 while keeping signal-quality bars | None for coverage/redundancy/date-gap; full-sample robustness still discretionary |
| **D** (operator-defined) | TBD | TBD |

**Path A mitigation recommendation (if operator confirms A):** even under A,
consider adding a standing TODO to re-evaluate redundancy at the ensemble layer
(e.g. ensemble-level orthogonality check at ensemble-construction time, not at
factor-admission time) so that the redundancy gap is not silently unbounded.
This is not a gate change — it is a forward-looking process note to avoid the
highest-severity consequence (redundant admission inflating ensemble IR).

This memo does **not** implement any such TODO; that is an iter-11 decision.

---

## 5. Evidence index

| Claim | Evidence |
|---|---|
| iter-1 source tree off-repo until 2026-04-18 | `git log --until="2026-04-18 23:59:59"` shows `902cd41` → `ad9ab14` → `588ffce` → `07d2bfa` → `339fa10`; `git show 339fa10` body admits "previously on disk but never committed" |
| six factor screens completed before source tree committed | `git show ad9ab14 --stat` + `git show 588ffce --stat` describe outcomes; `git show 339fa10 --stat` lands the code that produced them |
| `config/gates.yaml` aligned to code not plan | `config/gates.yaml:5` *"These gates are aligned with factor_screening.screen_factor()..."* |
| GL-0001 froze falsification; no analogous gate freeze | `docs/GOVERNANCE_LOG.md:70` (GL-0001 row); absence confirmed by full table scan — no row with "freeze" in Decision column references gates.yaml |
| GL-0002..GL-0008 rationale uses plan wording against in-force evidence | `docs/GOVERNANCE_LOG.md:71-78` Criteria column quotes plan family; Evidence column points to `results/factors/*/gate_results.json` which contain in-force family verdicts |
| prior researcher almost flagged, reframed as threshold typo | `docs/NYSE_ALPHA_RESEARCH_RECORD.md:373` |
| in-force config sha256 stable across iterations | `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4` (audit memo §1, verified unchanged at audit time 2026-04-23) |

---

## 6. Iron-rule compliance

| Rule | Status |
|---|---|
| No post-2023 dates in data loading | No data loading in this memo |
| No AP-6 threshold changes | `config/gates.yaml`, `config/falsification_triggers.yaml`, `src/nyse_core/gates.py`, `src/nyse_core/factor_screening.py`, `results/factors/*/gate_results.json`, `docs/GOVERNANCE_LOG.md` all untouched |
| No DB mocks in tests | No tests added or modified |
| No secret leakage | No adapter/network code touched |
| No `--no-verify` | Commit runs all six pre-commit hooks |
| Hash chain preserved | Supplemental event will append off iter-10 tip `677f39bf37926e4f540d5577ccebf297e3a96125ab5c88eef2dc09af97f814ab` |
| TODO-11 / TODO-23 untouched | Confirmed |
| iter-0 bit-exactness preserved | No code path touched; no diagnostic helper changed; screening outputs bit-identical to iter-9 |

---

## 7. What iter-11 still requires from the operator

This memo provides the root-cause narrative (Q1) and the consequences ledger
(Q2). iter-11 remains a one-way door. It still requires an explicit `correction`
authorization event naming:

1. The chosen correction path (A / B / C / D).
2. The scope of the correction (file set, whether screens re-run).
3. Whether any supplementary mitigation (e.g. a standing process note about
   redundancy) accompanies the path.

Until that authorization event is emitted, iter-11 does not proceed.

---

**Prepared by:** RALPH loop iter-10 supplemental (operator-requested forensics)
**Chain anchor:** appended off iter-10 tip `677f39bf37926e4f540d5577ccebf297e3a96125ab5c88eef2dc09af97f814ab`
**Related artefacts:** `docs/audit/gate_calibration_audit.md`, `results/research_log.jsonl` lines 63-64
**Next step:** operator reviews this memo and emits iter-11 authorization (or requests further investigation)
