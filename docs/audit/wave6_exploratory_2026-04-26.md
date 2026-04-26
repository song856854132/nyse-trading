# Wave 6 Path D EXPLORATORY VERDICT — v2 Ensemble Archived

**Date:** 2026-04-26
**Iteration:** iter-25 (#155) — Wave 6 wrap (final)
**Wave:** Wave 6 — Path C statistical validation suite
**Governance row:** GL-0019 (Branch B — EXPLORATORY VERDICT, Codex Path D)
**Anchor:** GL-0017 (Wave 6 pre-registration; bars frozen iter-21..iter-25 per Iron Rule 9)
**Hash chain anchor:** iter-24 research-log tip `a33c9888cdd51dbbf09dbf34ee6de58a`
**Codex consult status:** OPTIONAL per GL-0017 Branch B map (Branch B is mechanical given any V_n FAIL); this audit memo is the canonical Branch B evidence.

---

## 1. Verdict Summary

| Bar | Threshold | Result | Verdict | Source file |
|-----|-----------|--------|---------|-------------|
| V1 (Romano-Wolf max adj_p)        | < 0.05  | 1.0000   | **FAIL** | `results/validation/iter22_romano_wolf/result.json`  |
| V2 (block bootstrap 95% CI lower) | ≥ 0.30  | 0.18166  | **FAIL** | `results/validation/iter23_bootstrap_ci/result.json` |
| V3 (max relative Sharpe deviation) | ≤ 20%   | 25.97%   | **FAIL** | `results/validation/iter24_robustness/summary.json`  |
| V4a (min LOO Sharpe)              | ≥ 0.30  | 0.3769   | PASS     | `results/validation/iter24_robustness/summary.json`  |
| V4b (max neg-side rel drop)       | ≤ 35%   | 32.08%   | PASS     | `results/validation/iter24_robustness/summary.json`  |
| V4 (V4a AND V4b)                  | both    | both     | **PASS** | (composite)                                          |
| Joint(V3 AND V4)                  | both    | V3 fails | **FAIL** | (composite)                                          |
| GL-0017 unanimity (V1∧V2∧V3∧V4)   | all PASS | 3 FAILs | **FAIL → Branch B** | (composite)                                |

**Branch routing (triple-confirmed):**

- V1 FAIL → routes to Branch B
- V2 FAIL → routes to Branch B
- V3 FAIL (joint with V4) → routes to Branch B

Branch B is **triple-redundantly confirmed**. Any one of V1/V2/V3 alone would have routed to Branch B; all three failing simultaneously eliminates any claim that the routing depends on a marginal interpretation of a single bar.

Per Iron Rule 9 anti-gaming clause (committed in GL-0017, ratified by Codex iter-21 P2-1): no Bonferroni-FDR substitution, weighted scorecard, conditional 3-of-4 tier, or unanimity relaxation may rescue this verdict. **V4 PASS is informational only** — it cannot satisfy V1∧V2∧V3∧V4 unanimity required for GL-0018 Branch A.

**Outcome:** v2 ensemble archived as exploratory-grade evidence. Holdout (2024-2025) PROTECTED. `results/holdout/.holdout_used` lockfile NOT created. Wave 7 (iter-26) WILL NOT START.

---

## 2. Per-Bar Driver Analysis

### 2.1 V1 — Romano-Wolf adjusted-p stepdown (n_reps=500)

**Source:** `src/nyse_core/statistics.py:161 romano_wolf_stepdown`
**Orchestrator:** `scripts/run_v1_romano_wolf.py` (sha256 `e8e7b512dff9846ccf8081aa6f3402921c934f5a40483978f103b0fecda598ce`)
**Result:** `max(adjusted_p) = 1.0000` → **FAIL** (bar: < 0.05)

**SOLE family-wise carrier: `piotroski_f_score` (adj_p = 1.0)**

| Factor              | adjusted_p | n_ls_periods | n_panel_rows |
|---------------------|------------|--------------|--------------|
| accruals            | **0.0000** | 413          | 70,178       |
| ivol_20d_flipped    | **0.0000** | 412          | 197,524      |
| momentum_2_12       | **0.0000** | 364          | 173,981      |
| **piotroski_f_score** | **1.0000** | 415          | 193,537      |
| profitability       | **0.0000** | 415          | 114,657      |

**Strategic interpretation.** This is **NOT a 5-factor failure**. Four of the five active v2 factors clear the family-wise stepdown at vanishing p-value (adj_p = 0.0 each). The V1 bar fails because of a single factor — `piotroski_f_score` — whose Romano-Wolf adjusted p-value is exactly 1.0.

This corroborates the GL-0014 admission note (preserved in GOVERNANCE_LOG §3) that `piotroski_f_score` "clipped G5 redundancy bound but remain[ed] in the active universe per V2-PREREG-2026-04-24 (verdict-invariant under K=3-of-N=5 ensemble construction)." `piotroski_f_score` survived solo-G5 redundancy by the thinnest margin and was retained in the active universe via the K=3-of-N=5 coverage gate. Its individual signal does not survive a stricter family-wise multiple-testing correction.

**Pattern label: multiple-testing carrier.** A factor that:

1. Clips a redundancy gate at its solo-G5 boundary (passes only barely);
2. Is retained in the active universe via a coverage rule (K-of-N gating);
3. Fails family-wise multiple-testing correction (Romano-Wolf adj_p = 1.0).

This is a structural anti-pattern. The factor exists in the ensemble for ensemble-construction reasons (coverage majority), not for marginal-information reasons. Any future v3/Wave-8 universe construction should treat "K-of-N retained but solo-G5 clipping" as a multiple-testing red flag and require either solo-G5 clearance or supplementary family-wise robustness evidence before admission.

### 2.2 V2 — Block bootstrap CI lower bound (n_reps=10000, block_size=63 trading days, alpha=0.05)

**Source:** `src/nyse_core/statistics.py:106 block_bootstrap_ci`
**Orchestrator:** `scripts/run_v2_bootstrap_ci.py` (sha256 `18d15317efd371ee650f43cb1eaaa1f3591843557c7598d79e68381006f20f04`)

| Quantity                | Value    |
|-------------------------|----------|
| Point estimate Sharpe   | 0.5549   |
| CI lower (95%)          | 0.18166  |
| CI upper (95%)          | 2.33330  |
| CI width                | 2.15164  |
| V2 bar                  | ≥ 0.30   |
| Verdict                 | **FAIL** (0.1817 < 0.30) |

**Strategic interpretation.** The V2 bar derivation memo (committed in GL-0017) triangulated 0.30 from three constraints: (a) cushion above `docs/ABANDONMENT_CRITERIA.md` A9 weak-signal floor [0, 0.3]; (b) ρ=0.834 effective-N shrinkage as the expected variance inflator; (c) precisely 60% of GL-0015's 0.50 Phase 3 frozen target.

The observed `ci_lower = 0.18166` lands cleanly inside the A9 weak-signal range [0, 0.3]. More striking is the `ci_upper = 2.33330` — the bootstrap 95% CI spans more than **2.15 absolute Sharpe units** (lower 0.18 → upper 2.33). This enormous distribution width is the diagnostic smoking gun: **ρ=0.834 effective-N shrinkage materializes as severe bootstrap variance inflation**, exactly as the V2 derivation memo predicted.

The point estimate +0.5549 is not nominally weak in isolation. It is the variance around it that fails V2 — the +0.5549 is a single realization within a bootstrap distribution wide enough that the 5th percentile dips into A9 weak-signal range. The strategy is too dependent on which 5d-fwd-return periods are sampled.

The bootstrap distribution width corroborates the V4 finding (§2.4 below): if `ivol_20d_flipped` carries the ensemble Sharpe (single-factor load-bearing carrier), then any sampling that under-weights `ivol_20d_flipped`-favorable periods drives the lower bound down toward A9, while sampling that over-weights such periods drives the upper bound up to 2.33. The 2.15-unit CI width is concentration risk in disguise.

### 2.3 V3 — Parameter sensitivity (4 perturbations, full 2×2 Cartesian)

**Source:** wraps `scripts/simulate_v2_ensemble_phase3.py`
**Orchestrator:** `scripts/run_robustness_suite.py` (sha256 `3c63b255b87bdf95ea72274e15b304dcc552be1322e03ae07bde288ea40534dd`)
**V3 bar:** max relative Sharpe deviation across the 4 perturbations ≤ 20%
**Result:** `max_relative_deviation = 0.25965` → **FAIL** (driven by K=2 cell)

| Run        | K_coverage | n_quantiles | Sharpe  | rel_dev | Cell verdict |
|------------|------------|-------------|---------|---------|--------------|
| baseline   | 3          | 5           | 0.5549  | —       | reference    |
| **V3-r1 (K=2)** | **2**  | 5           | **0.6990** | **25.97%** | **FAIL**  |
| V3-r2 (K=4)    | 4      | 5           | 0.5647  | 1.77%   | PASS         |
| V3-r3 (n_q=3)  | 3      | 3           | 0.6592  | 18.79%  | PASS         |
| V3-r4 (n_q=10) | 3      | 10          | 0.6475  | 16.69%  | PASS         |

**Strategic interpretation.** Three of four perturbations PASS individually (rel_devs 1.77%, 18.79%, 16.69% — all under the 20% bar). The single failing cell is **K=2** (relaxing the coverage threshold from K=3-of-N=5 to K=2-of-N=5), which amplifies Sharpe by 25.97% to 0.6990.

This pattern is diagnostic: the strategy is **K-coverage-sensitive on the loose side**. Tightening to K=4 stays close to baseline (1.77% deviation); n_quantiles changes are roughly symmetric (~17-19%). But relaxing K to 2 — admitting more name × date observations into the ensemble — adds non-trivial Sharpe that exceeds the V3 bar.

Two competing readings:

1. **Optimization frontier reading.** K=3 is on the optimization frontier, and the frozen +0.5549 was a local-but-fragile optimum. A future strategy should consider K=2 as the construction-grammar baseline.
2. **Gaming reading.** The loosened K=2 cell admits more low-coverage stocks; if those stocks are systematically higher-volatility low-quality names, the apparent Sharpe gain is a regime artifact, not a robust improvement.

Either way, the V3 FAIL is real — by the GL-0017 frozen bar, max_rel_dev > 20% trips the bar, and the strategy as constructed is not coverage-rule-stable. Further investigation (which reading is correct) belongs in a future Wave 8 (or analogous) charter, not in iter-25 wrap.

### 2.4 V4 — Leave-one-factor-out (5 LOO drops, K=2-of-N=4 coverage)

**Source:** wraps `scripts/simulate_v2_ensemble_phase3.py`
**Orchestrator:** same as V3
**V4 bar:** V4a `min(LOO Sharpe) ≥ 0.30` AND V4b `max negative-side relative drop ≤ 35%` (both must pass)

| Dropped factor          | Remaining 4         | LOO Sharpe | Direction      | neg_drop |
|-------------------------|---------------------|------------|----------------|----------|
| accruals                | 4 others            | 0.7907     | UP (+42.5%)    | n/a      |
| **ivol_20d_flipped**    | 4 others            | **0.3769** | **DOWN (-32.1%)** | **0.3208** |
| momentum_2_12           | 4 others            | 0.8639     | UP (+55.7%)    | n/a      |
| piotroski_f_score       | 4 others            | 0.6944     | UP (+25.1%)    | n/a      |
| profitability           | 4 others            | 0.5470     | DOWN (-1.4%)   | 0.0142   |

**V4a verdict:** min(LOO Sharpe) = 0.3769 (`ivol_20d_flipped` LOO) ≥ 0.30 → **PASS**
**V4b verdict:** max(neg_drop) = 0.3208 (`ivol_20d_flipped` LOO) ≤ 0.35 → **PASS** (4.2pp headroom)
**V4 verdict (V4a AND V4b):** **PASS**

**Strategic interpretation.** V4 is the single bar that PASSES Wave 6. But the result is **informationally striking, not validating**:

1. **Four of five LOO drops INCREASE Sharpe.** Dropping `accruals`, `momentum_2_12`, `piotroski_f_score`, or even `profitability` (modestly) makes the ensemble materially better in three cases (Sharpe 0.69 → 0.86) and marginally worse in one. On average, the v2 factors other than `ivol_20d_flipped` are *anti-diversifying noise* — they hurt the ensemble more than they help. Only `ivol_20d_flipped` is unambiguously load-bearing.

2. **Only `ivol_20d_flipped` LOO is structurally meaningful.** Dropping it halves the Sharpe (0.5549 → 0.3769). This is the single-factor-load-bearing carrier signature: the +0.5549 ensemble is, in effect, an `ivol_20d_flipped`-dominated bet wearing 4-factor camouflage.

3. **V4b headroom is razor-thin.** 32.08% vs 35.00% cap = 4.2 percentage points. A slightly less favorable sample period for `ivol_20d_flipped` and V4b would also have failed. The V4 PASS is fragile.

4. **V4 PASS does NOT contradict V1+V2+V3 FAILs.** V4 measures factor-set robustness (gradual degradation when one factor is removed). It does not measure multiple-testing significance (V1), bootstrap variance (V2), or knob-grammar robustness (V3). The four bars were designed to be diagnostically orthogonal — passing one does not rescue failures in the others. This orthogonality is exactly what the AND-construction enforces.

V4 **cannot rescue V3 under Iron Rule 9 anti-gaming**. The plan and GL-0017 commit explicitly forbid "we'll change the construction rule to V4 PASS = good enough" reasoning.

---

## 3. Combined Diagnosis

The v2 ensemble has **two structural weaknesses** confirmed jointly by Wave 6:

1. **Multiple-testing carrier (V1):** `piotroski_f_score` does not survive Romano-Wolf family-wise correction (adj_p = 1.0). It is in the active universe via K=3-of-N=5 coverage gating, not via marginal individual signal. Other factors carry the family-wise null rejection at adj_p = 0.0.

2. **Single-factor load-bearing carrier (V4 informational + V2 width corroboration):** `ivol_20d_flipped` carries the ensemble's Sharpe — dropping it halves Sharpe to 0.3769. The other four factors are, on average, anti-diversifying noise (4 of 5 LOO drops INCREASE Sharpe). Bootstrap variance (V2 ci_upper = 2.33, ci_width = 2.15) is consistent with this single-factor concentration.

3. **Coverage-rule fragility (V3):** the frozen K=3 baseline is unstable under K=2 perturbation (Sharpe 0.5549 → 0.6990, rel_dev 25.97%). The strategy's signal depends materially on the choice of K.

These are **not independent failure modes**. They share a common root: the v2 active universe was assembled through K-of-N coverage gating, which retained factors that would not pass solo G0-G5 individually under v2 thresholds (specifically `piotroski_f_score` and `profitability`, per the GL-0014 admission note and iter-18 #143 v2 re-screen). The ensemble survives in-sample as one strong factor (`ivol_20d_flipped`) plus accessories whose contribution is statistically marginal at best and anti-diversifying at worst.

**Wave 6 was designed to detect exactly this failure mode**, and it did. The plan's pre-registration of V4 as "the missing bar for the exact failure mode this whole Wave 6 was designed to address" (plan §V4 bar derivation memo) was prescient — V4 confirmed the single-factor carrier hypothesis informationally, while V1/V2/V3 supplied the formal failures.

**Path C correctly routed to Path D.** The +0.5549 in-sample point estimate would have produced an undefensible holdout outcome regardless of which side of zero it landed on. A strategy that depends on one factor surviving the 2024-2025 window, with bootstrap CI dipping into A9 weak-signal range and a multiple-testing carrier inflating the active universe count, does not deserve to consume the one-shot holdout resource.

---

## 4. Exploratory Archive Policy

Per GL-0017 Branch B language and Codex iter-21 P2 evidence-preservation guidance, the following raw evidence files are **CANONICAL** (not scratch):

- `results/validation/iter22_romano_wolf/result.json` — V1 evidence (FAIL)
- `results/validation/iter23_bootstrap_ci/result.json` — V2 evidence (FAIL)
- `results/validation/iter24_robustness/summary.json` — V3+V4 summary (V3 FAIL, V4 PASS)
- `results/validation/iter24_robustness/v3_perturbation_*.json` (×4) — V3 per-cell evidence
- `results/validation/iter24_robustness/v4_loo_drop_*.json` (×5) — V4 per-LOO evidence
- `results/ensemble/iter19_v2_phase3/ensemble_result.json` — Phase 3 baseline +0.5549 (untouched)

These files were produced under pre-registered bars per Iron Rule 9 and are NOT scratch. They are preserved as canonical evidence of the v2 ensemble's exploratory-grade status. No `--force` rewrites, no consolidation into a single archive file, no removal under future cleanup passes. Hash chain entries iter-22..iter-24 (`292f6feb...`, `8cd8d682...`, `a33c9888...`) anchor the evidence to the research log.

The v2 ensemble is **archived as exploratory**. It may be cited as evidence in future strategy designs (e.g., "single-factor `ivol_20d_flipped`-dominated strategies show promising in-sample Sharpe but fail family-wise correction") but may **NOT** be cited as a validated trading strategy. Any document or commit that cites the +0.5549 result must also cite GL-0019 to convey its exploratory status.

---

## 5. Holdout Status (Wave 7 dormancy)

Per GL-0017 Branch B language:

- `results/holdout/.holdout_used` — **NOT CREATED**
- `results/holdout/.holdout_in_progress` — **NOT CREATED**
- 2024-2025 holdout window — **PROTECTED**
- `scripts/run_holdout_once.py` — Iron Rule 10 prerequisite NOT triggered (no Branch A authorization)

Wave 7 (iter-26) **WILL NOT START**. Future re-entry into the validation queue requires:

1. A new strategy with stronger in-sample evidence — factors must pass v2 G0-G5 individually (not via K-of-N coverage gating), or the new strategy must adopt a v3 gate family that does not rely on coverage-gate retention as an admission path.
2. Pre-registered Wave 8 (or analogous) validation bars under a fresh GL-NNNN row, mirroring GL-0017's Iron Rule 9 freeze pattern.
3. An updated charter (analogous to `docs/audit/wave_d_diagnostic_charter.md`) justifying the new active universe and validation-bar derivations.

The holdout remains a one-shot resource. It was not consumed by Wave 6.

---

## 6. Iron Rule Compliance (iter-25 wrap)

| Rule | Compliance |
|------|------------|
| Rule 1 (no post-2023 dates)              | All Wave 6 computations used 2016-01-01..2023-12-31 only; holdout untouched. |
| Rule 2 (AP-6 frozen thresholds)          | `config/gates_v2.yaml` and `config/gates.yaml` sha256 bit-identical (`bd0fc5de...d92979d2`, `521b7571...f559af4`). |
| Rule 3 (no DB mocks)                     | All validations ran against `research.duckdb`. |
| Rule 4 (no secrets)                      | No tokens introduced. |
| Rule 6 (hash chain)                      | iter-25 chains off iter-24 tip `a33c9888cdd51dbbf09dbf34ee6de58a` (research-log event appended in this commit). |
| Rule 7 (GL-0011 invariance)              | `results/factors/*/gate_results.json` untouched. |
| Rule 8 (gates frozen pre-screen)         | No threshold adjustments. |
| Rule 9 (Wave 6 bars frozen + anti-gaming) | All 4 bars from GL-0017 applied verbatim; AND-construction binding; no Bonferroni-FDR substitution, no weighted scorecard, no conditional 3-of-4 tier, no unanimity relaxation. V4 PASS does NOT rescue V1+V2+V3 FAILs. |
| Rule 10 (Wave 7 holdout-runner pre-land) | Not triggered — Branch B does not authorize iter-26. `scripts/run_holdout_once.py` remains absent; this is the correct state under Branch B. |

---

## 7. Branch B Codex Consult Status

Per GL-0017 Codex consult map: Branch B Codex consult is **OPTIONAL** (mechanical given any V_n FAIL). This audit memo is the canonical Branch B evidence; further Codex consult is at operator discretion.

If the operator chooses to consult Codex on this Branch B decision in a future commit, suggested focus areas:

1. Confirm the multiple-testing carrier diagnosis for `piotroski_f_score` is the right reading — i.e., that adj_p = 1.0 reflects the factor's marginal contribution being absorbed by the family-wise correction, not a bug in the orchestrator's per-factor return reconstruction.
2. Whether the V4 PASS pattern (`ivol_20d_flipped` carrier hypothesis confirmed, 4-of-5 LOO drops INCREASE Sharpe) suggests a single-factor `ivol_20d_flipped` strategy might be worth re-validating in a future Wave 8 charter.
3. Whether the V3 K=2 perturbation outperformance (Sharpe 0.5549 → 0.6990) is a real effect (optimization frontier reading) or an artifact (low-coverage-name regime artifact).

These questions are out of scope for iter-25 wrap. They are recorded here for the operator's future planning.

---

## 8. Cross-References

- `docs/GOVERNANCE_LOG.md` GL-0017 (Wave 6 pre-registration, anchor for this memo)
- `docs/GOVERNANCE_LOG.md` GL-0019 (this Branch B EXPLORATORY VERDICT, committed alongside this memo)
- `docs/GOVERNANCE_LOG.md` GL-0014 (V2-PREREG-2026-04-24 active universe; root cause for piotroski_f_score multiple-testing carrier pattern)
- `docs/GOVERNANCE_LOG.md` GL-0016 (Phase 3 EXIT AUTHORIZED at +0.5549 — anchor for Wave 6 application)
- `docs/FRAMEWORK_AND_PIPELINE.md` §17.3 (Wave 6 pre-registration detail) and §17.4 (Wave 6 outcome — added in this commit)
- `docs/audit/iter15_v2_gate_family_preregistration.md` (V2-PREREG-2026-04-24 construction grammar)
- `docs/audit/wave_d_diagnostic_charter.md` (charter pattern for future Wave 8 if attempted)
- `docs/ABANDONMENT_CRITERIA.md` A9 weak-signal range [0, 0.3] (V2 lower bound 0.18 lands inside)
- `results/research_log.jsonl` iter-22..iter-25 events (hash-chained)
- Plan: `/home/song856854132/.claude/plans/dreamy-riding-quasar.md` Wave 6 + Wave 7 sections
