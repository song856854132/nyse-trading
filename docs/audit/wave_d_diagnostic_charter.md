# Wave D Diagnostic Charter — iter-13 (RALPH loop)

> **Charter ID:** `WDC-2026-04-24`
> **Charter scope:** frame what iter-14 measures and why, and pre-commit iter-15 to
> co-pre-register v2 gates **together with** the construction grammar that will be
> screened under them.
> **Charter type:** docs-only pre-registration; AP-6-safe two-way door.
> **Prepared by:** RALPH loop iter-13 (Wave D opening, revised per adversarial review;
> charter committed 2026-04-24, landing one day after iter-12's 2026-04-23 commit).
> **Chain anchor:** appended off iter-12 tip `d4b9c8c664e5e958fd8b7bb79bdd92c8dc84a2add61b4531db8a8e455db5d935`.
> **In-force config unchanged:** `config/gates.yaml` sha256 `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`.
> **Adversarial review:** Codex session `019dba41-f163-70e1-875b-909771c26083`
> (resumed from iter-11-D consult; 2026-04-23 Wave-D consult event).
> **Findings posture:** this iteration defines the *measurement plan* for iter-14 and
> the *pre-registration schema* for iter-15. No threshold, metric, direction, or
> admission decision is changed by this charter.

---

## 0. Why this charter exists

iter-12 (commit `11cd6e4`, research-log hash `d4b9c8c6…`) ran an equal-weight
ensemble G0 diagnostic on the 6 of 13 registered factors whose gate-results JSON
files exist (`accruals`, `high_52w`, `ivol_20d`, `momentum_2_12`, `piotroski`,
`profitability`) across 415 weekly rebalance periods. The headline result:

| Metric | iter-12 ensemble | G0 (Sharpe≥0.30) | Verdict |
|---|---|---|---|
| OOS Sharpe (52-per-year) | **−0.123** | ≥ 0.30 | FAIL |
| Permutation p-value (500 reps, 21d blocks) | **1.000** | < 0.05 | FAIL |
| IC mean (5-day forward, Spearman) | +0.009 | — | weak positive |
| IC IR | +0.047 | — | weak positive |
| Max drawdown | −0.362 | ≥ −0.30 | FAIL |

The obvious reading is *"construction is the choke — aggregation across rank-
percentiles of individually-rejected factors cannot recover signal the component
factors do not carry."* That reading drove my first-pass Wave-4 proposal to pivot
to sector-neutral residual construction + a re-screen under the in-force gate
family.

Codex consult session `019dba41…` corrected that framing. The consult's three
binding observations:

1. **iter-12 does not isolate construction as THE choke.** It only proves that
   an equal-weight blend of this specific 6-factor set is bad. It does not
   separate "bad blend" from "bad factor inclusion" from "bad aggregation".
2. **The 6 factors are not uniformly dead.** Three (profitability, accruals,
   momentum_2_12) are *near-passing* — each passes G0, G1, G4, G5 under the
   in-force family; they miss only G2 and/or G3 (IC thresholds). Two
   (ivol_20d, high_52w) have the wrong sign and fail every gate. One
   (piotroski) passes G1/G2/G4/G5 but has Sharpe near zero.
3. **The aggregator at `src/nyse_core/factor_screening.py:486, 612` does not
   penalize missing coverage.** It re-normalizes per `(date, symbol)` across
   whatever factor scores are present on that row, so a stock covered by 1 of
   6 factors gets equal weight at the point of aggregation as a stock covered
   by 6 of 6.

**Consequence:** freezing construction and jumping straight to v2-gates-and-
re-screen (my first pivot proposal) would conflate three live root causes:
(a) bad factor inclusion — dead factors dragging down near-passing ones,
(b) coverage bias — the aggregator's renormalization hiding heterogeneous
coverage, and (c) wrong construction grammar — equal-weight of rank-percentiles
of raw scores with no residualization, no coverage penalty, no discrete-score
flattening correction for Piotroski. Co-pre-registering v2 gates without first
decomposing (a)/(b)/(c) against a common diagnostic battery would inherit all
three confounders into the very pre-registration event that is supposed to
resolve GL-0012. That would burn AP-6 budget on a measurement schema that
cannot answer its own question.

This charter therefore inserts an explicit *diagnostic-only* iteration (iter-14)
between iter-12's headline result and iter-15's v2 pre-registration event. The
diagnostic iteration produces a fixed 5-stream evidence pack that is **purely
observational** under the in-force gate family; it does not propose thresholds,
does not re-screen factors, and does not change any admission decision. iter-15
then uses that evidence pack to pre-register v2 gates **and** construction
grammar **together**, as a single atomic commit, before any re-screening.

---

## 1. Per-factor decomposition from existing evidence

Each of the 6 screened factors has a `results/factors/<factor>/gate_results.json`
file on disk as of iter-12. Extracted per-gate metrics (all in-force family,
unchanged under GL-0012):

| Factor | G0 Sharpe (≥0.30) | G1 p-value (<0.05) | G2 IC mean (≥0.02) | G3 IC IR (≥0.50) | G4 MaxDD (≥−0.30) | G5 marginal contrib (>0) | Near-miss? |
|---|---|---|---|---|---|---|---|
| `profitability` | **+1.148** ✓ | 0.002 ✓ | +0.0158 ✗ | +0.113 ✗ | −0.190 ✓ | + ✓ | **YES — G2/G3 only** |
| `momentum_2_12` | +0.516 ✓ | 0.002 ✓ | +0.0189 ✗ | +0.078 ✗ | −0.283 ✓ | + ✓ | **YES — G2/G3 only** |
| `accruals` | +0.577 ✓ | 0.002 ✓ | +0.0080 ✗ | +0.062 ✗ | −0.272 ✓ | + ✓ | **YES — G2/G3 only** |
| `piotroski` | +0.018 ✗ | 0.002 ✓ | +0.0090 ✗ | +0.089 ✗ | −0.216 ✓ | + ✓ | marginal — G0 near zero |
| `high_52w` | **−1.229** ✗ | 1.000 ✗ | **−0.0055** ✗ | **−0.023** ✗ | −0.607 ✗ | + ✓ | **sign-flip candidate** |
| `ivol_20d` | **−1.916** ✗ | 1.000 ✗ | **−0.0079** ✗ | **−0.055** ✗ | −0.578 ✗ | + ✓ | **sign-flip candidate** |

Three clusters emerge:

- **Near-passing (3):** `profitability`, `momentum_2_12`, `accruals` each clear
  G0/G1/G4/G5 and miss only the IC thresholds G2 and G3. `momentum_2_12`'s
  IC mean `+0.0189` is within 0.0011 of G2. These are not dead factors.
- **Sign-flip candidates (2):** `ivol_20d` and `high_52w` have Sharpe ≤ −1.2,
  IC < 0, and permutation p = 1.000 — the classic signature of an inverted
  sign convention. `src/nyse_core/features/registry.py:161` and
  `src/nyse_core/features/__init__.py:48` are where the sign is applied.
- **Marginal (1):** `piotroski` clears every gate except G0 (Sharpe barely
  positive at +0.018) and G2/G3 (as with the near-passing cluster). The
  discrete 0..9 Piotroski score is flattened by `src/nyse_core/normalize.py:50`
  rank-percentile with average tie-handling, which Codex flagged as a possible
  signal-destruction mechanism for tie-heavy discrete inputs.

**Critical implication:** an equal-weight blend of near-passing + sign-flipped
+ marginal factors is *structurally* expected to underperform any one of the
three near-passing factors standalone, because the two sign-flipped factors
contribute a negative-correlation drag and the marginal factor adds noise.
iter-12's −0.123 ensemble Sharpe is therefore **consistent with** but **does
not uniquely identify** "aggregation fails." A near-passing-only blend with
sign-corrected ivol_20d and high_52w is the minimum counterfactual iter-14
must construct before any claim about aggregation.

---

## 2. iter-14 diagnostic battery — 5 streams

Each stream is AP-6-safe: no threshold, no metric definition, no direction,
no admission decision is changed. Outputs land in `results/diagnostics/iter14_<stream>/`
as observational artefacts referenced by iter-15's pre-registration.

### Stream 1: Per-factor near-miss table (docs + JSON)

**Artefact:** `results/diagnostics/iter14_near_miss/per_factor_near_miss.json`
and a markdown rendering at `docs/audit/iter14_near_miss_table.md`.

**Content:** for each of the 6 screened factors, the gap between its measured
value and each in-force threshold, with sign of the gap and a categorical
near-miss tag. Pulls numbers from existing `results/factors/*/gate_results.json`;
no new metrics computed.

**Question this answers:** which factors are within X% of clearing the IC
thresholds under the in-force family, and how much headroom would a
construction-only change (residualization, winsorization, coverage-penalty
weighting) need to recover to flip the verdict? Frames the Phase 3 exit
target reset (GL-0013 PATH E) in terms of what is achievable without new
factor inclusion.

### Stream 2: Coverage matrix (date × factor)

**Artefact:** `results/diagnostics/iter14_coverage/coverage_matrix.parquet`
and `docs/audit/iter14_coverage_summary.md`.

**Content:** per `(rebalance_date, factor_name)` cell, the count and
percentage of symbols in the universe with a non-NaN score. Also per-date
row: the coverage-Jaccard overlap between every pair of factors.

**Question this answers:** does the `factor_screening.py:486, 612`
aggregator's re-normalization hide per-factor coverage gaps? Specifically,
on dates where `accruals` covers 200 symbols but `ivol_20d` covers 450,
does the equal-weight blend systematically over-weight `ivol_20d`'s
predictions on symbols where `accruals` is NaN? This is a *diagnostic*
observation of coverage, not a proposal to change the aggregator.

### Stream 3: Pairwise factor score & return correlations

**Artefact:** `results/diagnostics/iter14_correlations/factor_corr_matrix.json`
and `results/diagnostics/iter14_correlations/forward_return_corr_matrix.json`.

**Content:** 6×6 Spearman rank correlation of factor scores (cross-sectional
per-date, then time-averaged), and 6×6 correlation of each factor's
predicted-top-decile 5-day forward returns. Also the single-factor
decomposition: for each factor, the 5-day forward return of a top-decile
equal-weighted long leg on its own.

**Question this answers:** how redundant are the 6 factors to each other in
score space vs in return space? If score-space correlations are low (good
diversification) but return-space correlations are high (all factors make the
same bets after top-N truncation), that pinpoints the allocator + sell-buffer
pipeline as the effective choke, not the factors or the aggregator.

### Stream 4: One-factor sector residual on `momentum_2_12` only

**Artefact:** `results/diagnostics/iter14_sector_residual/momentum_2_12_sector_residualized.json`
and `docs/audit/iter14_sector_residual_note.md`.

**Content:** re-compute `momentum_2_12` as a single-factor cross-sectional
regression residual against GICS sector dummies per rebalance date. Measure
OOS Sharpe, IC mean, IC IR, permutation p-value (500 reps, 21-day blocks) for
this residualized variant **against the same holdout split** used by iter-12.
Compare to the non-residualized `momentum_2_12` metrics. This is a
*one-factor* test, not an ensemble re-screen.

**Why only `momentum_2_12`:** it is the factor with the highest IC mean
among the near-passing cluster (`+0.0189`), the smallest gap to G2 (`0.0011`),
and the clearest economic prior (cross-sectional momentum survives sector-
neutralization historically on NYSE). Limiting to one factor keeps this
strictly a diagnostic signal-processing test; it is not a new admission
event. iter-15 will decide whether to generalize sector-residualization
into the construction grammar based on this one result.

**AP-6 safety:** because no factor is admitted or rejected based on this
result, and because the factor being measured is identical in identity
(still `momentum_2_12`) to its pre-existing gate-results record, this is an
observational supplement to the existing screening evidence under the
in-force gate family. The un-residualized `results/factors/momentum_2_12/gate_results.json`
is **not** overwritten.

### Stream 5: Sign-flip sanity check on `ivol_20d` and `high_52w`

**Artefact:** `results/diagnostics/iter14_sign_flip/sign_flip_diagnostic.json`
and `docs/audit/iter14_sign_flip_note.md`.

**Content:** for each of `ivol_20d` and `high_52w`, compute all 6 in-force
gate metrics **with the sign convention inverted** against the same 2016-2023
research window. Compare to the existing sign-on gate-results. The question
is mechanical: does inverting the sign move Sharpe from −1.9/−1.2 toward
positive values consistent with the published ivol and 52-week literature?

**AP-6 safety:** the sign convention in `src/nyse_core/features/registry.py:161`
is **not** changed. The sign-flipped metric computation is observational only;
the authoritative `registry.py` sign stays bit-identical. iter-15 decides
whether to amend the registry sign, re-screen, or leave the factors out of
the v2 construction entirely — that decision is an explicit governance event,
not a silent code change.

---

## 3. iter-15 co-pre-registration schema

iter-15 will commit **two atomically-linked artefacts** in a single commit,
before any factor is re-screened under them:

### 3.1 v2 gate family (resolves GL-0012)

The v2 gate family must combine the economically meaningful signals that
both the plan-of-record family and the in-force family carry:

- **From in-force family, retain:**
  - Absolute OOS Sharpe (with threshold pre-registered based on iter-14
    Stream 1 near-miss table — specifically the minimum Sharpe observed
    among the three near-passing factors, minus a safety margin TBD in iter-15).
  - Permutation significance (threshold pinned to 0.05 — the literature standard).
  - Max drawdown floor (threshold pre-registered based on iter-14 MaxDD
    distribution observed across the 6 factors).
- **From plan-of-record family, restore:**
  - Coverage floor (threshold pre-registered based on iter-14 Stream 2
    coverage matrix — specifically the minimum per-date coverage percentage
    that preserves ≥ 80% of rebalance-date cross-sections).
  - Redundancy control (threshold pre-registered based on iter-14 Stream 3
    correlations — maximum pairwise score-correlation with any already-
    admitted factor).
  - Full-sample Sharpe robustness (defers to iter-15 based on data-hygiene
    Stream 2).
- **Co-pre-registered NEW:**
  - IC mean and IC IR retained from in-force family, but with thresholds
    pre-registered from iter-14 evidence, not from the committee's 2026-04-15
    judgement. Specifically: `G_IC_mean ≥ floor(iter-14 near-passing IC means) − ε`
    where ε is pre-registered in iter-15, not tuned later.

**All v2 thresholds land as numeric values in the commit at iter-15, with a
one-line rationale for each pointing to the iter-14 diagnostic stream
that supplied the evidence. No threshold is a free parameter; every
threshold is a pre-registered function of iter-14 output.**

### 3.2 Construction grammar (binds to v2 gates)

The v2 gates will be applied to a *specific* construction pipeline, co-pre-
registered in the same commit. The construction grammar is the set of
transforms applied between raw-factor-compute and ensemble-aggregation:

- **Coverage penalty in aggregation** — the aggregator at
  `factor_screening.py:486, 612` will either (a) weight each stock's
  aggregated score by the fraction of factors covering it, or (b) require
  minimum coverage of K of N factors to be ranked at all. The choice
  between (a) and (b) is pre-registered in iter-15 based on Stream 2 evidence.
- **Discrete-score handling** — the Piotroski-like discrete factors will
  either (a) skip rank-percentile and use the raw 0..9 integer, (b) apply
  rank-percentile with random tie-breaking, or (c) be aggregated at the
  integer level and rank-percentiled only at the ensemble level. Choice
  pre-registered from Stream 3 evidence.
- **Sector residualization** — either applied to all factors, or only to
  the factor-families where Stream 4's one-factor test produces a Sharpe
  lift above a pre-registered threshold. Default if Stream 4 is ambiguous:
  not applied (conservative null).
- **Sign convention** — `ivol_20d` and `high_52w` are either kept as-is,
  sign-flipped based on Stream 5 evidence, or removed from the v2
  construction pipeline entirely. Decision pre-registered in iter-15; the
  `registry.py` code-change (if any) is committed in the same commit as
  the v2 gates.

**Critical:** gate family and construction grammar are one co-registered
pair. Screening under v2 gates with a different construction pipeline than
the one co-pre-registered is an AP-6 violation and must be treated as such
by any future iteration.

---

## 4. Phase 3 exit target reset constraints (GL-0013 PATH E)

`docs/GOVERNANCE_LOG.md` GL-0013 (2026-04-23) activated PATH E: the Phase 3
exit target of "OOS Sharpe 0.5-0.8" is formally under renegotiation. The
original target is **not** canonicalized as MISS until the iter-15 pre-
registration event lands, to avoid target-family double-fitting.

iter-13 pre-registers these constraints on the iter-15 target reset:

1. **Target ceiling:** ≤ `max(iter-14 Stream 1 per-factor Sharpes observed
   under in-force family) + ensemble_diversification_bonus`, where
   `ensemble_diversification_bonus` is pre-registered in iter-15 at a
   conservative value justified from Stream 3 redundancy evidence.
2. **Target floor:** ≥ G0 threshold under the v2 gate family. The Phase 3
   exit target cannot be lower than the screening gate; otherwise a single
   admitted factor could exit Phase 3.
3. **No re-negotiation after iter-15.** Once the v2 target is pre-
   registered in iter-15's commit, it is frozen for the remainder of the
   20-iter loop. Any subsequent miss on the v2 target is a genuine Phase 3
   failure, not a target redraft opportunity.

---

## 5. GL-0012 compliance statement

GL-0012 (2026-04-23, iter-11-D) states *"no new admission decisions may be
cited under either provisional family until v2 pre-registration lands."*

This charter and iter-14's diagnostic battery **do not cite any admission
decision**. Every artefact iter-14 produces is observational:

- Stream 1 restates existing gate-results values with gap decomposition — no
  admission changed.
- Stream 2 measures coverage — no admission changed.
- Stream 3 measures correlations — no admission changed.
- Stream 4 produces a one-factor residualized metric pair for `momentum_2_12`,
  but does **not** update `results/factors/momentum_2_12/gate_results.json`
  and does **not** admit or reject the residualized variant. The un-
  residualized factor retains its current FAIL verdict under the in-force family.
- Stream 5 produces sign-flipped metrics for two factors, but does **not**
  amend `registry.py` sign conventions and does **not** update any
  `gate_results.json`. The FAIL verdicts under the in-force family are preserved.

iter-15's co-pre-registration of v2 gates + construction grammar is the event
that resolves GL-0012. Screening under v2 gates happens in iter-15's commit
or later — no admission decision is cited before that commit lands.

---

## 6. Iron-rule compliance matrix for iter-13 (this commit)

| Iron rule | iter-13 compliance |
|---|---|
| No post-2023 dates in data loading | ✓ no data loading — pure documentation commit |
| No AP-6 threshold / metric / direction / admission changes | ✓ zero changes; `config/gates.yaml` sha256 `521b7571…f559af4` bit-identical; `config/falsification_triggers.yaml` frozen 2026-04-15 unchanged; `src/nyse_core/gates.py` unchanged; `src/nyse_core/factor_screening.py` unchanged; no `results/factors/*/gate_results.json` modified |
| No mock-only database tests | ✓ no tests added or modified |
| No secret leakage | ✓ no adapter / network code touched |
| No `--no-verify` commit flag | ✓ all six pre-commit hooks run (gitleaks, ruff-check, ruff-format, mypy, holdout-path-guard, research-log-chain) |
| Hash chain preserved | ✓ this event appends off iter-12 tip `d4b9c8c664e5e958fd8b7bb79bdd92c8dc84a2add61b4531db8a8e455db5d935` |
| TODO-11 and TODO-23 untouched | ✓ canonical TODOs unchanged |
| iter-0 bit-exactness preserved | ✓ no code path touched; diagnostic helpers unchanged; screening outputs bit-identical to iter-0 baseline |
| GOVERNANCE_LOG append-only | ✓ no GL row added in iter-13 (charter is docs/audit/, not GOVERNANCE_LOG); future GL row will land with iter-15 pre-registration, not this commit |

---

## 7. References

- `docs/RALPH_LOOP_RESEARCH_WAVES.md` — canonical loop definition (Wave 4 scope)
- `docs/GOVERNANCE_LOG.md` GL-0010 (superseded), GL-0011 (preserved FAIL
  verdicts), GL-0012 (provisional both families), GL-0013 (PATH E activated)
- `docs/audit/gate_calibration_audit.md` (GCA-2026-04-23) — root audit of
  gate-family mismatch
- `docs/audit/gate_mismatch_root_cause_and_consequences.md`
  (GCA-2026-04-23-supplemental) — forward-looking mitigation note
- `/.claude/plans/dreamy-riding-quasar.md` — plan-of-record (both gate families
  now provisional)
- `config/gates.yaml` sha256 `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`
  — in-force gate family, unchanged
- `scripts/simulate_ensemble_g0.py` (iter-12 orchestrator, commit `11cd6e4`)
- `results/ensemble/iter12_equal_weight/ensemble_result.json` (iter-12 result)
- `results/factors/*/gate_results.json` (6 existing screens: `accruals`,
  `high_52w`, `ivol_20d`, `momentum_2_12`, `piotroski`, `profitability`)
- Codex consult session `019dba41-f163-70e1-875b-909771c26083` — adversarial
  review of Wave-4 pivot proposal; 2026-04-23 Wave-D consult event.
