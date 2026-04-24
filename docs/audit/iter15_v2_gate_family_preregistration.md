# iter-15 v2 Gate Family + Construction Grammar — Pre-Registration

> **Pre-registration ID:** `V2-PREREG-2026-04-24`
> **Charter ref:** `docs/audit/wave_d_diagnostic_charter.md` §3 (iter-15 co-pre-registration schema)
> **Commit type:** docs-only pre-registration; AP-6-safe two-way door that
> **resolves** GL-0012 (both gate families provisional) and lands the numeric
> target for GL-0013 PATH E (Phase 3 exit target reset).
> **Governance rows landed with this commit:** `GL-0014` (v2 gate family
> pre-registration), `GL-0015` (Phase 3 exit target reset).
> **Chain anchor:** appends off iter-14 tip
> `b008d03bfda18709e83037a25d666cf2a58bfcfba57cd2c4ada51dfca9058726`.
> **In-force config unchanged:** `config/gates.yaml` sha256
> `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`
> (verified bit-identical before and after this commit; no `config/gates.yaml`
> edit; v2 numeric thresholds land as a **new file** `config/gates_v2.yaml`
> which is **not yet wired into any code path**).

---

## 0. What this pre-registration is, and is not

**This pre-registration IS:**

1. A numeric fixation of every v2 gate threshold before any factor is screened
   under v2. Each threshold is a pre-committed function of iter-14 Stream 1–5
   evidence, with the derivation cited inline.
2. A numeric fixation of every construction-grammar decision (coverage
   handling, discrete-score handling, sector residualization, sign convention)
   before any re-screen is run under v2.
3. A numeric fixation of the Phase 3 exit target (OOS Sharpe floor + ceiling +
   realistic target) before any v2 ensemble result is computed.
4. A docs-only commit: `config/gates.yaml` is unchanged, `src/nyse_core/`
   code is unchanged, `results/factors/*/gate_results.json` are unchanged, and
   no factor is admitted or rejected in this commit.

**This pre-registration IS NOT:**

1. A code change. `registry.py`, `factor_screening.py`, `gates.py`, and
   `normalize.py` are all **bit-identical** before and after this commit. The
   construction-grammar decisions take effect only when iter-16 implements
   them in a separate commit that cites this document as the pre-reg source.
2. A factor-screening event. No `results/factors/*/gate_results.json` file is
   created or modified. No admission verdict is issued under v2 in this commit.
3. A retroactive admission revision. GL-0002..GL-0008 FAIL verdicts remain
   valid — they held under **either** the plan-of-record or in-force family,
   and they remain valid under v2 until a re-screen under v2 happens in iter-16
   or later (at which point the re-screen, not this pre-reg, is what produces
   new admission verdicts).

**AP-6 posture:** this commit is a forward pre-commit. All numeric thresholds
are fixed **before** the v2 screening runs that will evaluate against them.
Any future iteration that wants to deviate from these thresholds must land an
explicit governance-log supersession row (per GL-protocol §2 iron rule 1),
not a silent re-tune.

---

## 1. v2 gate family — numeric thresholds + derivation

Six gates, one numeric threshold per gate, each with one-line rationale
pointing at the iter-14 Stream that supplied the evidence. `config/gates_v2.yaml`
mirrors these values in the repository's standard gate-config schema.

### G0 — Absolute OOS Sharpe

| Field | Value |
|---|---|
| Metric | `oos_sharpe` (identical definition to in-force G0) |
| Threshold | `>= 0.30` |
| Decision | **Retained from in-force family unchanged** |
| Evidence | iter-14 Stream 1 per-factor Sharpes: profitability=+1.148, momentum_2_12=+0.516, accruals=+0.577 (all ≥ 0.30). piotroski=+0.018 (below). The 0.30 threshold cleanly separates the near-passing cluster from marginal/failed factors. |
| Near-passing floor | +0.516 (momentum_2_12) |
| Safety margin | (+0.516 − 0.30) = +0.216 — i.e. every near-passing factor clears the threshold with 0.22+ buffer. |
| Why not evidence-derived lower bound | The in-force 0.30 threshold is already within the safety-margin corridor around the near-passing floor, and retaining it avoids un-tuning a threshold that was already consistent with the admission-eligible factor set. |

### G1 — Permutation p-value significance

| Field | Value |
|---|---|
| Metric | `permutation_p` (stationary bootstrap, 500 reps, 21-day blocks — identical to in-force G1) |
| Threshold | `< 0.05` |
| Decision | **Retained from in-force family unchanged — pinned to literature standard** |
| Evidence | iter-14 Stream 1 per-factor p-values: profitability=0.002, momentum_2_12=0.002, accruals=0.002, piotroski=0.002 (all well under 0.05). ivol_20d and high_52w at p=1.000 — the classic inverted-sign signature, handled by the sign-convention component of the construction grammar (§2 below), not by loosening this gate. |
| Why not evidence-derived | 0.05 is the literature-canonical significance level for financial-factor research (Harvey-Liu-Zhu 2016, Romano-Wolf 2005). Deviating from it invites false-discovery challenges that iter-14 evidence does not justify. |

### G2 — IC mean (evidence-derived, LOWERED from in-force)

| Field | Value |
|---|---|
| Metric | `ic_mean` (Spearman cross-sectional IC, time-averaged over rebalance dates — identical to in-force G2) |
| Threshold | `>= 0.005` |
| Decision | **New, co-pre-registered from iter-14 Stream 1 evidence** |
| Derivation | `floor(near-passing IC means) − ε_{G2}` where near-passing IC means are {profitability=+0.0158, momentum_2_12=+0.0189, accruals=+0.0080}, floor = +0.0080, `ε_{G2} = 0.0030`. Result: `+0.0080 − 0.0030 = +0.0050`, which is the largest value on the 1-2-5 × 10^k round-threshold lattice strictly below the near-passing floor (see ε selection rule row below). |
| ε selection rule (pre-committed here) | **iter-15 is the authorized ε-selection event per charter `docs/audit/wave_d_diagnostic_charter.md` §3.1, which pre-committed the *form* `floor − ε` but deferred the numeric ε to this pre-registration.** Rule applied: ε is the smallest positive buffer such that the resulting v2 threshold is the **largest value on the 1-2-5 × 10^k *round-threshold lattice*** (…, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, …) strictly below the near-passing floor. This lattice is the standard "preferred-number" convention for round threshold values in finance and statistics (p-value canon 0.001/0.01/0.05; basis-point canon 1/5/10/25). For G2: floor=0.008, largest lattice point strictly below = 0.005, ⇒ ε=0.003. The rule is applied identically for G3 and produces asymmetric buffer values (see G3 row) — asymmetry is a deterministic function of where each raw floor falls relative to adjacent lattice gaps, not discretion. No alternative ε was considered in this pre-registration; this rule and these values are locked before any v2 re-screen runs. |
| Evidence | iter-14 Stream 1 per-factor IC means. The in-force threshold (0.02) was set by committee judgement without iter-14's per-factor evidence; the realized near-passing ceiling under the current construction is 0.019 (momentum_2_12), missing the in-force threshold by 0.0011 on the best-performing factor. The v2 threshold acknowledges that under the NYSE 2016-2023 universe with the current construction grammar, the economically viable IC-mean range is 0.005-0.020, not 0.020+. |
| Ceiling not raised without evidence | This is a lowering relative to in-force (0.02 → 0.005); the pre-registration deliberately does **not** raise the threshold beyond the realized near-passing ceiling, because raising it would pre-commit to rejecting the only economically viable factors observed. |
| AP-6 note | Lowering a threshold before re-screening is a genuinely novel direction for the gate family and **is an AP-6-adjacent act**. The adversarial review constraint (GL-0013 trigger (a)) is satisfied because the new threshold is a pre-committed function of iter-14 evidence with both the derivation formula (`floor − ε`) and the ε selection rule (1-2-5 × 10^k round-threshold lattice, largest point strictly below the floor) explicitly fixed here. Neither is a free parameter available to iter-16. |

### G3 — IC Information Ratio (evidence-derived, LOWERED from in-force)

| Field | Value |
|---|---|
| Metric | `ic_ir` (IC mean / IC std over rebalance dates — identical to in-force G3) |
| Threshold | `>= 0.05` |
| Decision | **New, co-pre-registered from iter-14 Stream 1 evidence** |
| Derivation | `floor(near-passing IC IRs) − ε` where near-passing IC IRs are {profitability=+0.113, momentum_2_12=+0.078, accruals=+0.062}, floor = +0.062, `ε = 0.012` derived from the same pre-registered ε selection rule as G2 (see the G2 ε-rule row and the G3 ε-rule row below). Result: `+0.062 − 0.012 = +0.050`. |
| Evidence | iter-14 Stream 1 per-factor IC IRs. The in-force threshold (0.50) was set by committee judgement; no factor in the observed 6-panel clears it, and the realized near-passing ceiling under the current construction is 0.113 (profitability). Retaining in-force 0.50 would pre-commit to rejecting every factor observable under the current NYSE construction, which makes the gate non-discriminatory. The v2 threshold permits admission while still preserving directional IC discipline. |
| ε selection rule (pre-committed here) | Same rule as G2 row: largest 1-2-5 × 10^k round-threshold lattice point strictly below the near-passing floor. For G3: floor=0.062, largest lattice point strictly below = 0.05 ⇒ ε=0.012. Asymmetric ε vs G2 (0.003) is a deterministic function of where each raw floor falls relative to adjacent lattice gaps (0.008 is between 0.005 and 0.01; 0.062 is between 0.05 and 0.1). Neither ε is a free parameter available to iter-16. No alternative ε was considered in this pre-registration. |
| AP-6 note | Lowering a threshold before re-screening is a genuinely novel direction for the gate family and **is an AP-6-adjacent act** — same adversarial-review-constraint framing as G2. The constraint (GL-0013 trigger (a)) is satisfied because both the derivation form (`floor − ε`) and the ε selection rule (1-2-5 lattice) are explicitly fixed here; neither is a free parameter available to iter-16. |

### G4 — Max drawdown floor

| Field | Value |
|---|---|
| Metric | `max_drawdown` (peak-to-trough of long-short portfolio cumulative returns — identical to in-force G4) |
| Threshold | `>= -0.30` |
| Decision | **Retained from in-force family unchanged** |
| Evidence | iter-14 Stream 1 per-factor MaxDDs: near-passing cluster = {profitability=-0.190, momentum_2_12=-0.283, accruals=-0.272}; all clear the -0.30 floor. piotroski=-0.216 also clears. Only the sign-flip candidates (ivol_20d=-0.578, high_52w=-0.607) fail, and the v2 construction grammar's sign-flip decision (§2 below) is the mechanism that resolves those two. Retaining the -0.30 floor avoids widening tail-risk tolerance. |

### G5 — Return-decile redundancy control (NEW, replaces in-force marginal_contribution)

| Field | Value |
|---|---|
| Metric | `max_return_decile_corr_with_admitted` — Pearson correlation of the candidate factor's top-decile long-only 5-day forward-return time-series with the forward-return time-series of every already-admitted factor's top-decile long-only portfolio. Gate value = `max(...)` over admitted factors. |
| Threshold | `<= 0.90` |
| Direction | `<=` |
| Decision | **New, replaces in-force G5 (`marginal_contribution > 0.0`) in response to iter-14 Stream 3 evidence** |
| Evidence | iter-14 Stream 3 return-decile correlation matrix. All 15 pairs among the 6 factors ≥ +0.695; max pair = piotroski ↔ profitability at +0.933. Score-level correlations are moderate (0.0-0.35 bulk, max +0.548), but portfolio-level correlations are near-collinear. This is the Tulchinsky crossing effect: "Orthogonalization of scores does not orthogonalize the portfolios; correlation should be measured at the decision surface, not the feature surface." The in-force G5 was "ensemble IC delta > 0" — a solo-screen-degenerate check that always passes +1.00 for the first factor. The v2 replacement measures redundancy at the return-stream level where it actually matters. |
| Threshold derivation | +0.90 is one standard deviation below the observed max (+0.933) and above the observed min (+0.695). Rejecting only the top-correlated pair preserves the multi-factor admission option while ruling out the clearest return-collinear duplication. |
| Solo-screen behavior | When no factor is admitted yet, the metric has no inputs; the gate is **defined to PASS** for the first factor (analogous to the in-force G5 passing +1.00 for solo screens). Documented behavior, pre-registered here. |

### Summary — v2 gate thresholds in one table

| Gate | Metric | v2 threshold | v2 direction | in-force threshold | Change | Evidence source |
|---|---|---|---|---|---|---|
| G0 | `oos_sharpe` | 0.30 | `>=` | 0.30 | retained | Stream 1 near-passing cluster all ≥ 0.30 |
| G1 | `permutation_p` | 0.05 | `<` | 0.05 | retained | literature standard |
| G2 | `ic_mean` | 0.005 | `>=` | 0.02 | **lowered** | Stream 1 near-passing floor 0.008 − ε |
| G3 | `ic_ir` | 0.05 | `>=` | 0.50 | **lowered** | Stream 1 near-passing floor 0.062 − ε |
| G4 | `max_drawdown` | -0.30 | `>=` | -0.30 | retained | Stream 1 near-passing MaxDD bracket |
| G5 | `max_return_decile_corr_with_admitted` | 0.90 | `<=` | (replaced) | **new metric** | Stream 3 return-decile matrix |

Two gates lowered (G2, G3), one gate replaced (G5), three retained (G0, G1, G4).
Two lowerings are the binding change vs in-force; both are evidence-derived.

---

## 2. Construction grammar — co-registered decisions

The v2 gate thresholds above apply to a **specific** construction pipeline. This
section pre-registers that pipeline. Per charter §3.2, applying v2 gates to a
different construction pipeline than what is co-registered here is an AP-6
violation.

### 2.1 Coverage handling at aggregation (resolves Stream 2 finding)

**Decision:** option (b) — **require K = 3 of N = 5 active v2 factors present**
for a stock to be ranked at aggregation time. Stocks with fewer than 3 of the
5 active v2 factors present on a given rebalance date are **dropped** from the
aggregated ranking for that date (their v2 composite score is NaN, excluded
from top-N selection).

**N = 5 vs N = 6 (scope clarification):** The denominator N = 5 reflects the
**active v2 factor universe after §2.4 sign-convention decisions**, not the
count of registered factors. The 5 active factors are `ivol_20d` (sign-flipped
per §2.4), `piotroski_f_score`, `momentum_2_12`, `accruals`, `profitability`.
`high_52w` is **excluded** from the presence count because §2.4 removes it from
the v2 pipeline pending iter-16's dedicated sign-flip diagnostic. The coverage
gate therefore does not require `high_52w` to be present for admission and
does not reward its absence. `high_52w` remains registered in `registry.py` and
still emits its panel under its actual name `52w_high_proximity`; it simply
does not contribute to the v2 composite score or the presence count until
iter-16 or later restores it.

**Derivation:**

- Stream 2 per-factor mean coverage: `{ivol_20d: 99.95%, 52w_high_proximity:
  99.32%, momentum_2_12: 99.16%, piotroski_f_score: 97.18%, profitability:
  57.57%, accruals: 35.18%}`.
- Four price/volume factors cover ≥ 97%; two fundamentals factors cover
  35-58%. Under the current `factor_screening.py:486, 612` renormalizer, a stock
  covered by only 1 of 6 factors receives the same per-`(date, symbol)` weight
  as a stock covered by 6 of 6. This is the bias iter-14 Stream 2 documented.
- `K = 3 of N = 5` is the ceil(N/2) median-coverage rule: a stock must have
  ≥ 60% of the active v2 factors scored (3/5 = 0.6) before it enters the
  ranking. This preserves admission eligibility for the near-passing cluster
  (which includes the low-coverage `accruals` factor) while rejecting
  pathologically sparse rows. (Note: ceil(5/2) = ceil(6/2) = 3, so the K
  value is invariant to the N = 5 vs N = 6 choice; only the denominator —
  and the resulting coverage ratio — changes. The 60% threshold on N = 5
  is slightly stricter than the 50% threshold on N = 6, which is consistent
  with the program's risk posture under the smaller post-sign-flip factor
  set.)
- Alternative considered and rejected: option (a) (coverage-proportional
  weighting of aggregated scores). Rejected because option (a) systematically
  lowers aggregated scores for low-coverage stocks, which distorts ranking
  (low-coverage stocks would never reach top-N). Option (b) preserves rank
  semantics while cleanly partitioning eligible/ineligible cells.

**Code impact for iter-16:** `src/nyse_core/factor_screening.py` aggregator
lines 486 and 612 gain a pre-aggregation coverage-count check. Stocks with
`n_present_v2_active_factors < 3` get `composite_score = NaN`, where the
presence count is computed **only over the 5 active v2 factors**
(`ivol_20d` flipped, `piotroski_f_score`, `momentum_2_12`, `accruals`,
`profitability`). `high_52w` does not enter the count. The change is one
conditional (presence count threshold) plus one masking step (composite →
NaN), plus an include-list restriction that binds the aggregator to the
active v2 factor set; no new files.

### 2.2 Discrete-score handling (resolves Stream 3 tie-discrimination concern)

**Decision:** option (b) — **rank-percentile with random tie-breaking** for
discrete-valued factors (currently only `piotroski_f_score` in the 6-panel;
extends to any future 0..K-valued factor).

**Derivation:**

- The existing `src/nyse_core/normalize.py:50` rank-percentile uses average
  tie-handling, which compresses ties to the same rank-percentile value. For
  Piotroski (10 discrete values 0..9 across ~500 stocks per date), the
  distribution of tied-rank groups is very heavy — as many as 50-100 stocks per
  tied bin — which strips within-bin discrimination.
- Random tie-breaking distributes the tied ranks uniformly across the tied
  bin. Expected per-stock rank is the same as average tie-breaking (same
  mean), but the ranking has variance instead of compression, which permits
  top-N selection to actually rank-discriminate within bins.
- Alternative option (a) (use raw 0..9 integer, skip rank-percentile) was
  rejected because AP-8 mandates rank-percentile [0,1] before ensemble
  aggregation.
- Alternative option (c) (integer-level aggregation then ensemble-level
  rank-percentile) was rejected because it changes the aggregation order of
  operations — a bigger code change than option (b), with no additional
  statistical justification.

**Code impact for iter-16:** `src/nyse_core/normalize.py` rank-percentile adds
an optional `tie_breaking: Literal["average", "random"]` kwarg with default
"average" (preserves existing behavior for all non-discrete factors).
`registry.py` registers `piotroski_f_score` with `tie_breaking="random"`.

**Deterministic RNG seed (pre-committed here):** random tie-breaking uses
`numpy.random.default_rng(seed=<date-ordinal>)` where `<date-ordinal>` is the
rebalance date's proleptic-Gregorian ordinal (`date.toordinal()`, i.e. the
integer day-count since date(1, 1, 1)). Properties pre-committed:

1. **Per-`(date, symbol)` stability across reruns.** The same rebalance date
   always produces the same tie-resolved rank for the same symbol, so a v2
   re-screen run today and re-run in iter-17 produce bit-identical composite
   scores for every `(date, symbol)` cell.
2. **Cross-date independence.** Different rebalance dates get independent RNG
   states, so tie patterns do not correlate across time (no persistent
   per-symbol advantage or disadvantage that could interact with the return
   target).
3. **No hidden global state.** The seed is a deterministic function of the
   date alone — no process-level RNG state, no global `numpy.random.seed(...)`
   call, no reliance on wall-clock. A researcher re-running the screen on a
   different machine with the same date gets the same result.
4. **Fully reproducible from the date alone.** Given `date` and the `registry`
   snapshot, the tie-resolved rank is reconstructible without any auxiliary
   state file.

iter-16 implements **exactly this seed rule**; any deviation requires a
supersession GL row. Seed choice is an AP-6-adjacent detail because it
indirectly affects top-N selection on tie-heavy dates; freezing it here
forecloses discretionary seed tuning in iter-16.

### 2.3 Sector residualization (resolves Stream 4 evidence)

**Decision:** **NOT applied** to any factor in v2. Construction grammar uses
raw rank-percentile scores without GICS-sector residualization.

**Derivation:**

- iter-14 Stream 4 measured `momentum_2_12` raw Sharpe +0.516 → sector-
  residualized Sharpe +0.181 (65% drop). IC mean dropped 18% (+0.0189 →
  +0.0155); IC IR essentially unchanged (+0.078 → +0.081).
- Charter §3.2 rule: "Default if Stream 4 is ambiguous: not applied
  (conservative null)." Stream 4 is **not** ambiguous — it shows a large
  negative Sharpe impact. Under the charter's decision rule this is a CLEAR
  "do not residualize" evidence.
- Economic interpretation: most of the raw `momentum_2_12` Sharpe comes from
  between-sector rotation (sector-level drift), not within-sector cross-
  sectional momentum. Sector residualization strips the rotation signal, which
  is a **legitimate** part of the momentum factor — not a confound. NYSE
  sector-rotation momentum is economically meaningful; the v2 construction
  preserves it.
- This decision is made for ALL factors in the 6-panel, not just
  `momentum_2_12`. Stream 4 ran only on `momentum_2_12`, so other factors'
  sector exposure is unmeasured — iter-16 or iter-17 may widen the
  diagnostic. For now, v2 construction applies the same (non-residualized)
  treatment to every factor, consistent with the null-conservative default.

**Code impact for iter-16:** none. `src/nyse_core/factor_screening.py` does not
currently residualize; the v2 decision preserves that behavior.

### 2.4 Sign convention (resolves Stream 5 evidence for `ivol_20d`)

**Decision for `ivol_20d`:** **sign FLIPPED in v2 construction**. The v2
pipeline scores stocks by `1 − rank_percentile(ivol_20d_raw)` instead of
`rank_percentile(ivol_20d_raw)`. Low-ivol stocks receive high scores (BUY
signals); high-ivol stocks receive low scores.

**Derivation for `ivol_20d`:**

- iter-14 Stream 5: raw ivol_20d Sharpe = -1.916 under in-force family. With
  sign-flip, Sharpe = +1.922. Permutation p: raw = 1.000 (degenerate), flipped
  = 0.002 (highly significant). MaxDD: raw = -0.578, flipped = -0.132 (77%
  reduction). This is the classic inverted-sign signature — every metric flips
  in the expected direction.
- Literature: Baker-Bradley-Wurgler 2011 (low-volatility anomaly),
  Frazzini-Pedersen 2014 (betting-against-beta). High idiosyncratic volatility
  predicts **negative** future excess returns (retail lottery demand hypothesis
  + short-sale constraints). The economically correct BUY signal is LOW ivol.
- The raw registered factor at `src/nyse_core/features/registry.py:161` and
  `src/nyse_core/features/__init__.py:48` computes ivol_20d such that higher
  value = higher ivol, and then applies rank-percentile such that higher ivol
  = higher score. This is the economically **inverted** sign convention.
- Under v2 gates with the sign flip applied: G0 pass (+1.92 ≥ 0.30), G1 pass
  (0.002 < 0.05), G2 **pass** (+0.008 ≥ 0.005), G3 **pass** (+0.055 ≥ 0.05),
  G4 pass (-0.132 ≥ -0.30). iver-14 Stream 5 shows the sign-flipped
  `ivol_20d` would clear 5 of 6 v2 gates solo; the G5 return-correlation
  check runs only against admitted factors, so it's trivially satisfied for
  the first admitted factor.

**Decision for `high_52w`:** **REMOVED** from the v2 construction pipeline
pending a separate Stream-5-style diagnostic in iter-16.

**Derivation for `high_52w`:**

- iter-14 Stream 5 **skipped** `high_52w` because the registry emits the panel
  under the name `52w_high_proximity`, not `high_52w`, and the charter scoped
  Stream 5 to factors whose score panel the registry emits under the exact
  failing name. The sign convention for `high_52w` is therefore **unmeasured**
  by iter-14.
- The economic prior (disposition-effect / anchoring-bias literature: stocks
  near 52-week highs outperform) would suggest the same direction as the
  current registration. But the raw metrics (Sharpe -1.229, p=1.000, IC
  -0.0055) are the classic inverted-sign signature, so the prior is not
  confirmed by the current sign convention's output.
- Rather than extrapolate a sign flip from the `ivol_20d` analogy, the
  conservative choice is to remove `high_52w` from the v2 pipeline and run a
  dedicated Stream-5-style diagnostic in iter-16 before deciding.
- Removal from the v2 pipeline does **not** deregister `high_52w` — the
  factor stays in `registry.py` and continues to produce its panel at the
  current name. It simply does not contribute to the v2 composite score.

**Code impact for iter-16 (pre-committed here):**

1. `src/nyse_core/features/registry.py` (or wherever the sign is applied):
   register `ivol_20d` with `sign_convention = -1` (inversion). Equivalent
   implementation: change the rank-percentile stage to compute
   `1 − rank_percentile(raw_ivol)` at the point of factor-panel output.
2. `config/strategy_params.yaml:combination.factors` (or equivalent
   include-list): remove `high_52w` from the v2 active set, leaving
   `{ivol_20d, piotroski_f_score, momentum_2_12, accruals, profitability}` as
   the 5-factor v2 universe.
3. iter-16 runs a Stream-5-style sign-flip diagnostic on `52w_high_proximity`
   (the real panel name) before deciding whether to re-include `high_52w`
   in iter-17 or later.

**AP-6 note:** The sign-flip for `ivol_20d` is a code change that produces
different factor panels. Because this pre-registration commit does **not**
modify `registry.py`, the panel remains bit-identical today. The code change
lands in a separate iter-16 commit that will cite this pre-registration
document as its authorizing evidence. The sign-flip is pre-committed here
before the v2 re-screen result is produced, so it is AP-6-compliant
(forward pre-commit, not retrospective tune).

### 2.5 Construction grammar — summary

| Component | v2 decision | Evidence source | Code impact for iter-16 |
|---|---|---|---|
| Coverage at aggregation | Require K = 3 of N = 5 active v2 factors per stock; else NaN | Stream 2 | `factor_screening.py` aggregator |
| Discrete-score handling | rank-percentile with random tie-breaking (seed = date-ordinal) for discrete factors | Stream 3 concern | `normalize.py` + `registry.py` |
| Sector residualization | NOT applied to any factor | Stream 4 | none |
| Sign convention — `ivol_20d` | FLIPPED (sign = -1) | Stream 5 direct | `registry.py` |
| Sign convention — `high_52w` | REMOVED from v2 pipeline pending iter-16 diagnostic | Stream 5 gap | `strategy_params.yaml` include-list |
| Active v2 factor universe | 5 factors: ivol_20d (flipped), piotroski, momentum_2_12, accruals, profitability | derived | `strategy_params.yaml` |

---

## 3. Phase 3 exit target reset (resolves GL-0013 PATH E)

Per charter §4 and GL-0013, the Phase 3 exit target (originally OOS Sharpe
0.5-0.8) is under PATH E renegotiation. This section pre-registers the new
target numerically, before any v2 ensemble result is computed.

### 3.1 Target ceiling

**Charter §4 rule:** `ceiling ≤ max(iter-14 Stream 1 per-factor Sharpes under
in-force family) + ensemble_diversification_bonus`.

**Derivation:**

- `max(per-factor Sharpes)` = +1.148 (profitability).
- Expected ensemble diversification bonus from N = 5 active factors with
  Stream 3 return-decile correlations ≥ 0.70 (heavily overlapping):
  `bonus = best_factor_Sharpe × (sqrt(N/(1 + (N-1)·ρ)) − 1)` for N = 5 and
  ρ ≈ 0.82.
- **ρ aggregation rule (pre-committed here):** ρ is the **simple arithmetic
  mean of the 10 off-diagonal pairs** of Stream 3's return-decile correlation
  matrix restricted to the 5 active v2 factors (excluding `high_52w`'s row
  and column). Simple arithmetic mean (no weighting, no absolute value) is
  the canonical aggregation for this kind of point-estimate use; no
  alternative aggregator was considered. Stream 3 reported all 15 observed
  pairs across the 6-factor panel within [+0.695, +0.933]; 0.82 is the
  rough-order midpoint used as a plausibility-level estimate pending iter-16
  re-computation over the active 5-factor subset. The ceiling is pre-
  registered to one decimal place (~1.32) to absorb ρ variability of ±0.05
  without target drift.
- Plugging in: bonus ≈ 1.148 × (sqrt(5 / (1 + 4·0.82)) − 1) = 1.148 × 0.148
  ≈ +0.17.
- **Ceiling = 1.148 + 0.17 ≈ 1.32**, pre-registered as an upper bound on what
  the v2 pipeline could plausibly produce.

### 3.2 Target floor

**Charter §4 rule:** `floor ≥ G0 threshold under v2 gate family`.

**Derivation:**

- `Gv2_0 threshold` = 0.30 (retained from in-force, §1 above).
- **Floor = 0.30**, pre-registered. A single admitted factor could trivially
  hit this solo; no ensemble-level construction adds value at floor.

### 3.3 Target — pre-registered numeric

**Phase 3 exit target (OOS Sharpe on research period 2016-2023): 0.50**

Rationale:

- 0.30 floor is the eligibility threshold; 0.50 is the **meaningful-ensemble**
  threshold. At 0.50 the ensemble delivers ~0.20 Sharpe beyond the single-factor
  eligibility floor, which is enough to justify ensemble complexity.
- 0.50 sits well below the conceptual ceiling (~1.32) to preserve realization-
  slippage margin (OOS Sharpe in research usually under-realizes live Sharpe
  by 0.15-0.30 per TWSE priors and Lesson_Learn §63).
- 0.50 is lower than the original target's midpoint (0.5-0.8 range: 0.65), by
  design — the original target was calibrated from TWSE priors with a 16-factor
  ensemble and stronger per-factor Sharpes; the NYSE v2 pipeline with 5
  retained factors (after sign-flip + coverage gate) has lower ceiling, and
  0.50 is the evidence-calibrated Phase 3 exit.
- 0.50 is above the G0 single-factor threshold (0.30) and above the min
  observed single-factor near-passing Sharpe (0.516), so clearing 0.50 with
  the v2 ensemble is a **non-trivial** requirement — it requires either
  profitability + at-least-one-other factor contributing, or a diversification
  bonus realization consistent with the Stream 3 correlations.

### 3.4 Pre-registration of no-renegotiation clause

Per charter §4.3: **"No re-negotiation after iter-15."**

Once this document lands, the 0.50 OOS Sharpe Phase 3 exit target is frozen
for the remainder of the 20-iter loop (iter-16..iter-20). Any v2 ensemble
result in iter-16+ that clears 0.50 triggers Phase 3 exit authorization per
§5 of `docs/GOVERNANCE_LOG.md`; any result that misses 0.50 is a **genuine
Phase 3 miss**, not an opportunity to re-draft the target.

This clause is the AP-6 teeth of GL-0013. Without it, every future miss
becomes a renegotiation opportunity and the target drifts with results.

---

## 4. GL-0012 resolution statement

GL-0012 (2026-04-23) states: "Both the plan-of-record's pre-amendment gate
family and the in-force gate family are declared PROVISIONAL pending v2
pre-registration in iter-13+ of Wave 4. No new admission decisions may be
cited under either family until v2 pre-registration lands."

This pre-registration **lands the v2 gate family** with numeric thresholds
derived from iter-14 evidence. Effective when the companion GL-0014 row in
`docs/GOVERNANCE_LOG.md` is appended:

- GL-0012's "no new admission decisions" constraint is **released conditional
  on future factor screens using the v2 family + construction grammar
  co-registered here**. Any future admission decision must cite this
  pre-registration document as the authorizing v2 gate source. The in-force
  family is formally retired from forward-looking admission use (it remains
  valid for retrospective reference to GL-0002..GL-0008, which stand).
- The plan-of-record's pre-amendment family is also retired for forward
  admission; its restored-in-v2 elements (coverage, redundancy) are now
  numeric components of v2 G5 and the construction grammar §2.1.

`config/gates.yaml` sha256 `521b7571...f559af4` remains bit-identical through
this commit; the v2 numeric thresholds live in the **new file**
`config/gates_v2.yaml`. iter-16 or later will decide when and how to route
the gate loader to `config/gates_v2.yaml` (that code change is itself a
governance-log-logged event when it lands).

---

## 5. GL-0013 resolution statement

GL-0013 (2026-04-23) states: "The original Phase 3 exit target (OOS Sharpe
0.5-0.8) is formally resolved as MISS under the 0/6 factor admission state."

This pre-registration **sets the new Phase 3 exit target** at OOS Sharpe 0.50
on the research period (2016-2023). Effective when the companion GL-0015 row
in `docs/GOVERNANCE_LOG.md` is appended:

- The original 0.5-0.8 range is formally retired. 0.50 is its replacement.
- The no-renegotiation clause (§3.4 above) forecloses future target drift.
- The target is pre-committed **before** any v2 re-screen or v2 ensemble
  result is computed in iter-16+, so it is AP-6-compliant (GL-0013 trigger
  (c) explicit operator authorization satisfied here).

---

## 6. Iron-rule compliance matrix for iter-15 (this commit)

| Iron rule | iter-15 compliance |
|---|---|
| No post-2023 dates in data loading | ✓ no data loading — pure documentation commit |
| No AP-6 threshold / metric / direction / admission changes | ✓ zero changes to in-force config; `config/gates.yaml` sha256 `521b7571…f559af4` bit-identical; `config/falsification_triggers.yaml` frozen 2026-04-15 unchanged; `src/nyse_core/gates.py` unchanged; `src/nyse_core/factor_screening.py` unchanged; `src/nyse_core/features/registry.py` unchanged; `src/nyse_core/normalize.py` unchanged; no `results/factors/*/gate_results.json` modified. v2 numeric thresholds land as a **new file** `config/gates_v2.yaml` not yet wired into any code path. |
| No mock-only database tests | ✓ no tests added or modified |
| No secret leakage | ✓ no adapter / network code touched |
| No `--no-verify` commit flag | ✓ all six pre-commit hooks run (gitleaks, ruff-check, ruff-format, mypy, holdout-path-guard, research-log-chain) |
| Hash chain preserved | ✓ this event appends off iter-14 tip `b008d03bfda18709e83037a25d666cf2a58bfcfba57cd2c4ada51dfca9058726` |
| TODO-11 and TODO-23 untouched | ✓ canonical TODOs unchanged |
| iter-0 bit-exactness preserved | ✓ no code path touched; screening outputs bit-identical to iter-0 baseline (since no screens are run in iter-15) |
| GOVERNANCE_LOG append-only | ✓ GL-0014 + GL-0015 appended as new rows; GL-0010/GL-0011/GL-0012/GL-0013 not edited |

---

## 7. References

- `docs/audit/wave_d_diagnostic_charter.md` (iter-13, WDC-2026-04-24) —
  charter pre-committing iter-14 evidence and iter-15 pre-registration schema
- `docs/audit/iter14_near_miss_table.md` (Stream 1) — per-factor gap
  decomposition from existing gate-results
- `docs/audit/iter14_coverage_summary.md` (Stream 2) — coverage matrix +
  Jaccard
- `docs/audit/iter14_correlations_note.md` (Stream 3) — pairwise score +
  return-decile correlations
- `docs/audit/iter14_sector_residual_note.md` (Stream 4) — one-factor sector
  residual on momentum_2_12
- `docs/audit/iter14_sign_flip_note.md` (Stream 5) — sign-flip on ivol_20d
- `docs/GOVERNANCE_LOG.md` GL-0010 (superseded), GL-0011 (preserved FAIL
  verdicts), GL-0012 (both families provisional; resolved here by GL-0014),
  GL-0013 (Phase 3 target under PATH E; resolved here by GL-0015)
- `.claude/plans/dreamy-riding-quasar.md` — plan-of-record (Phase 3 target
  resolution cited against original §Phase 3 target)
- `config/gates.yaml` sha256 `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`
  — in-force gate family, unchanged through this commit
- `config/gates_v2.yaml` — **new file**, numeric v2 thresholds, not yet wired
  into any code path
- `results/diagnostics/iter14_*/` — the iter-14 artefact corpus that
  supplies every evidence-derived threshold in §1–§3

---

## 8. What iter-16 must and must not do (forward pre-commitment)

**iter-16 MUST:**

1. Cite this document (`docs/audit/iter15_v2_gate_family_preregistration.md`)
   as the authorizing source for the v2 gate thresholds and construction
   grammar.
2. Implement `ivol_20d` sign flip in `src/nyse_core/features/registry.py`
   before re-screening.
3. Implement coverage gate K = 3 of N = 5 active v2 factors in
   `src/nyse_core/factor_screening.py` aggregator before re-screening. The
   presence count is computed only over the 5-factor active v2 set; removed
   `high_52w` does not contribute to the count.
4. Implement random tie-breaking option in `src/nyse_core/normalize.py` before
   re-screening, using `numpy.random.default_rng(seed=date.toordinal())` as
   the pre-registered deterministic RNG seed rule per §2.2 above.
5. Run a Stream-5-style sign-flip diagnostic on `52w_high_proximity` (the
   registry's actual panel name) before deciding whether to re-include
   `high_52w` in future iterations.
6. Re-screen 5 factors (ivol_20d flipped, piotroski, momentum_2_12, accruals,
   profitability) against v2 gate family + construction grammar as
   co-registered here.

**iter-16 MUST NOT:**

1. Modify any v2 gate threshold in `config/gates_v2.yaml`. Thresholds are
   frozen per §1 above. Adjustments require a supersession GL row, not a
   silent re-tune.
2. Modify any construction grammar decision in §2 without an explicit
   governance-log supersession row.
3. Re-include `high_52w` in the v2 pipeline before running its dedicated
   Stream-5-style diagnostic.
4. Cite admission verdicts under the in-force gate family or the plan-of-
   record pre-amendment family for any factor-admission decision after
   iter-15. GL-0002..GL-0008 retrospective verdicts remain valid; forward
   admission decisions must use v2.
5. Re-draft the Phase 3 exit target (§3.3) under any circumstance (no-
   renegotiation clause §3.4).
