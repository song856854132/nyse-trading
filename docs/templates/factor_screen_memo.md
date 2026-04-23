# Factor Screen Memo — `<FACTOR_NAME>`

> **Template version 0.1 | Frozen layout 2026-04-19**
> One memo per factor per screen. Fill every `<field>` and every `⬛` row.
> A memo without a research-log anchor, commit SHA, and preparer signature
> is not a record — do not save incomplete memos.
>
> **Why this template exists.** Six factors (ivol_20d, piotroski,
> earnings_surprise, high_52w, momentum_2_12, short_ratio) were screened
> before the template existed. Their results were recorded piecemeal across
> `results/factors/`, `docs/OUTCOME_VS_FORECAST.md`, and `docs/GOVERNANCE_LOG.md`.
> That made cross-factor comparison and audit reconstruction harder than it
> should have been. Every screen from 2026-04-19 forward uses this single
> frozen layout so that a reviewer opening one memo knows where to find
> every piece of evidence.
>
> **What a complete memo proves.**
> 1. The hypothesis was written down **before** the screen ran (pre-registration).
> 2. The data window is disclosed and does not touch the 2024-2025 holdout.
> 3. Each of G0 through G5 has a verdict with a cited metric and threshold.
> 4. Statistical significance is reported at three layers: raw permutation,
>    multiple-testing-corrected, and block-bootstrap CI.
> 5. A final decision is cited against the gate evidence, not against a
>    narrative. ADMIT, REJECT, or HOLD — never "inconclusive."

---

## 0. Header

| Field | Value |
|---|---|
| Memo ID | `<FSM-YYYY-MM-DD-FACTOR>` |
| Factor name | `<factor_name>` (must match `src/nyse_core/features/registry.py` name) |
| Factor family | `price_volume` ∣ `fundamental` ∣ `earnings` ∣ `short_interest` ∣ `sentiment` ∣ `nlp` |
| Usage domain | `SIGNAL` ∣ `RISK` (one only — AP-3 double-dip forbidden) |
| Sign convention | `+1` (high score = buy) ∣ `-1` (inverted: low value = buy) |
| Screen run date | `<YYYY-MM-DD>` (must be ≤ today, timestamped before run) |
| Preparer | `<operator-name>` |
| Git commit (code) | `<sha-at-screen-start>` |
| Config hash (strategy) | `<sha256 of strategy_params.yaml>` |
| Config hash (gates) | `<sha256 of gates.yaml>` |
| Research-log anchor (pre) | `<chain hash BEFORE the screen was run>` |
| Research-log anchor (post) | `<chain hash AFTER the screen result was appended>` |
| Data snapshot | `<duckdb schema hash + row counts>` |
| Holdout untouched? | `YES` (required — must be `YES` for screen to be valid) |

---

## 1. Hypothesis — pre-registered, dated BEFORE the screen

One paragraph stating the friction hypothesis (Lesson_Learn Rule #7). Must
answer: *why should this factor have a premium on the NYSE?* Cite the
theoretical source (Fama-French, Piotroski 2000, Jegadeesh-Titman 1993,
etc.) and state the direction of the predicted cross-sectional return.

| Item | Value |
|---|---|
| Predicted sign of IC | `+` (high score = higher next-week return) ∣ `−` |
| Predicted OOS Sharpe range | `<low> to <high>` (must be a range, not a point) |
| Predicted IC mean range | `<low> to <high>` |
| Predicted max drawdown range | `<negative_low> to <negative_high>` |
| Forecast registered in OVF? | `YES` + cite `docs/OUTCOME_VS_FORECAST.md:<line>` |
| Forecast hash in research log | `<chain hash of the pre-screen forecast entry>` |

**Rule:** If this table is filled after the screen ran, the memo is invalid.
The forecast must chain to the research log **before** the screen completes.
A memo that backfills predictions is equivalent to p-hacking.

---

## 2. Data window

| Field | Value |
|---|---|
| Universe | `<S&P 500 / Russell 3000 / sector subset>` — PiT-enforced via `src/nyse_core/universe.py` |
| Start date | `<YYYY-MM-DD>` (research period) |
| End date | `<YYYY-MM-DD>` (must be ≤ `2023-12-31` — iron rule 1) |
| Number of rebalances | `<N>` (weekly cadence = ~52 × years) |
| Rebalance day | Friday close (signal) → Monday open (execution) |
| Forward return target | `fwd_5d` (primary) ∣ `fwd_20d` (secondary) |
| Purge gap | `<N>` trading days (must equal target horizon) |
| Embargo | `<N>` trading days |
| Cross-validation | PurgedWalkForwardCV — cite `src/nyse_core/cv.py:<line>` |
| Minimum history per symbol | `<N>` trading days |
| Survivorship bias controls | Historical S&P 500 membership reconstruction — cite constituency snapshot |
| Corporate-action adjustment | Event-sourced — cite `src/nyse_ats/storage/corporate_action_log.py` |
| NaN handling | Cross-sectional median within rebalance date; drop if >30% missing |

**Iron rule 1 attestation.** This memo attests that no query, join, or
backtest in this screen referenced any timestamp after `2023-12-31`. The
holdout-path-guard pre-commit hook + the `HoldoutLeakageError` test in
`tests/property/test_no_holdout_leakage.py` are the programmatic checks.

---

## 3. G0–G5 gate verdicts

Each gate row cites the metric, the observed value, the frozen threshold
from `config/gates.yaml`, the direction (≥, <, or >), and a one-line
interpretation. AP-6 is absolute: **thresholds are not edited after a
screen result is observed.**

**Amendment note (2026-04-23 iter-11-D — supersedes the iter-11 path-A amendment note).**
The gate family shown below (the in-force `config/gates.yaml` family, sha256
`521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`) is **PROVISIONAL
pending v2 pre-registration in iter-13+ of Wave 4**. iter-11 canonicalized this
family under `docs/GOVERNANCE_LOG.md` GL-0010 (correction path A); iter-11-D
reverses that canonicalization under GL-0012 in response to adversarial governance
review (via `/codex` consult, session `019dba41-f163-70e1-875b-909771c26083`) that
identified GL-0010 as establishing an AP-6-incompatible institutional precedent
("implementation beats plan-of-record when implementation happened to land first").
Memos instantiated from this template against the current (provisional) family are
**engineering outputs**, not canonical admission decisions. A fresh instantiation
under the v2 gate family (pending iter-13+) will be required before any new factor
admission is cited. See `docs/audit/gate_calibration_audit.md` (GCA-2026-04-23),
`docs/audit/gate_mismatch_root_cause_and_consequences.md` (GCA-2026-04-23-supplemental),
`docs/GOVERNANCE_LOG.md` GL-0010 (canonicalization, superseded), GL-0011 (preserved
FAIL verdicts re-affirmation), GL-0012 (reversal), and GL-0013 (Phase 3 exit
target renegotiation via PATH E) for full context.

| Gate | Name | Metric | Observed | Threshold | Direction | Verdict |
|---|---|---|---:|---:|:---:|:---:|
| G0 | OOS Sharpe | oos_sharpe | ⬛ | 0.30 | ≥ | PASS ∣ FAIL |
| G1 | Significance | permutation_p | ⬛ | 0.05 | < | PASS ∣ FAIL |
| G2 | IC mean | ic_mean | ⬛ | 0.02 | ≥ | PASS ∣ FAIL |
| G3 | IC_IR | ic_ir | ⬛ | 0.50 | ≥ | PASS ∣ FAIL |
| G4 | Max drawdown | max_drawdown | ⬛ | -0.30 | ≥ | PASS ∣ FAIL |
| G5 | Marginal contribution | marginal_contribution | ⬛ | 0.00 | > | PASS ∣ FAIL |

**Gate interpretation (3 sentences max per gate).** For each failing gate,
explain what the number means and what would need to change for it to pass
— without proposing that change. *Never* propose a threshold change in a
failure memo. A gate failure is information, not a negotiation.

---

## 4. Statistical significance

Three independent lenses, all frozen per AP-6. None of these can be
weakened after the number is observed.

### 4.1 Permutation test (raw)

| Field | Value |
|---|---|
| Block bootstrap | stationary, block length `<N>` trading days |
| Number of replications | 500 (frozen) |
| Null hypothesis | IC = 0 (no cross-sectional information) |
| Observed statistic | ⬛ |
| Raw p-value | ⬛ |
| Raw significance threshold | 0.05 |
| Raw verdict | PASS ∣ FAIL |

### 4.2 Romano-Wolf step-down (multiple-testing corrected)

**Why this matters.** At least `<M>` factors have been or will be tested
against the same research period. Without multiple-testing correction,
5% of null factors cross the raw threshold by chance. Romano-Wolf
controls family-wise error at α=0.05.

| Field | Value |
|---|---|
| Family size M | `<number of factors in the screening family>` |
| Adjustment method | Romano-Wolf step-down — cite `src/nyse_core/statistics.py:<line>` |
| Adjusted p-value | ⬛ |
| Adjusted significance threshold | 0.05 |
| Adjusted verdict | PASS ∣ FAIL |

### 4.3 Block bootstrap confidence interval

| Field | Value |
|---|---|
| Block length | 63 trading days (~ one quarter) |
| Number of replications | 10,000 |
| Bootstrap mean Sharpe | ⬛ |
| 95% CI lower bound | ⬛ |
| 95% CI upper bound | ⬛ |
| Lower-bound rule | must be `> 0` to pass |
| CI verdict | PASS ∣ FAIL |

**Rule.** A factor is statistically significant only when **all three**
lenses pass. Raw-only significance is insufficient (multiple-testing
illusion). Adjusted-only significance without CI lower bound > 0 is
insufficient (point estimate near zero). All three must agree.

---

## 5. Decision

Exactly one of:

- **ADMIT.** Factor passes all six gates and all three significance
  lenses. Cite a GOVERNANCE_LOG row for the admission authorization.
  Update `src/nyse_core/features/registry.py` to mark the factor active.
  Add a row to `docs/OUTCOME_VS_FORECAST.md` comparing forecast vs
  realized. Set `last_review_date` in the risk register.
- **REJECT.** Factor fails one or more gates or significance lenses.
  Cite which and why. Do **not** propose a rescue variant in this memo
  — that is a separate pre-registered screen. Append a rejection row
  to `docs/GOVERNANCE_LOG.md`. Update `docs/OUTCOME_VS_FORECAST.md`.
  Freeze the factor's sign/formula at the config level so future
  reruns with identical data yield identical verdicts.
- **HOLD.** Factor is not disqualified but the evidence base is not
  yet strong enough for admission. Permitted only when data coverage
  or purge gap mechanics blocked full evaluation (e.g., fundamentals
  factor with <2 years of filings available). State exactly what new
  evidence would reopen the decision, and do **not** return to HOLD a
  second time for the same factor without pre-registering the new
  screen.

| Field | Value |
|---|---|
| Decision | ADMIT ∣ REJECT ∣ HOLD |
| Cited gate failures (if REJECT/HOLD) | G`<n>` — `<one-line reason>` |
| GOVERNANCE_LOG row | `GL-NNNN` |
| OUTCOME_VS_FORECAST row | `docs/OUTCOME_VS_FORECAST.md:<line>` |
| If REJECT — next action | One sentence: "no further work on this factor" ∣ "pre-register a variant as `<new_name>`" |
| If HOLD — reopening condition | One sentence naming the specific new evidence |

---

## 6. Attestations and hashes

| Check | Operator | Timestamp | Signature (commit SHA) |
|---|---|---|---|
| Hypothesis registered before screen | `<operator>` | `<ISO 8601>` | `<pre-screen git SHA>` |
| Holdout untouched (2024-2025) | `<operator>` | `<ISO 8601>` | `<screen-run git SHA>` |
| Gate thresholds unchanged (AP-6) | `<operator>` | `<ISO 8601>` | `<screen-run git SHA>` |
| Research log appended | `<operator>` | `<ISO 8601>` | `<post-screen git SHA>` |
| Iron-rule compliance | `<operator>` | `<ISO 8601>` | `<commit SHA>` |

**Research-log anchor (post).** The final SHA-256 chain hash recorded in
`results/research_log.jsonl` after the screen result is appended. An
auditor can feed this hash into `scripts/verify_research_log.py` and
reproduce every event back to genesis.

`<chain-tip-hash>`

---

## 7. File pointers

| What | Where |
|---|---|
| Raw screen output | `results/factors/<factor_name>/<YYYY-MM-DD>/` |
| Gate metrics JSON | `results/factors/<factor_name>/<YYYY-MM-DD>/gates.json` |
| Permutation p-value series | `results/factors/<factor_name>/<YYYY-MM-DD>/permutation.json` |
| Bootstrap distribution | `results/factors/<factor_name>/<YYYY-MM-DD>/bootstrap.json` |
| Factor registry entry | `src/nyse_core/features/registry.py:<line>` |
| Screen script | `scripts/screen_factor.py --factor <factor_name>` |
| This memo | `docs/factors/<factor_name>/<YYYY-MM-DD>-screen-memo.md` |

---

## 8. Change protocol

Any edit to this template (adding a field, removing a section, changing a
threshold citation) requires a row in `docs/GOVERNANCE_LOG.md` under the
template-change authorization point. Minor wording edits are exempt,
but material changes (new gate, new statistical lens, removed field) are
not. A reviewer must be able to compare a 2026 memo against a 2028 memo
and know the layout is identical.
