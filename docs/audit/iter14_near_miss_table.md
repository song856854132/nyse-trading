# iter-14 Stream 1 — Per-Factor Near-Miss Table

> **Stream ID:** `iter14_stream1_near_miss`
> **Charter ref:** `docs/audit/wave_d_diagnostic_charter.md` §2 Stream 1
> **AP-6 posture:** observational under the in-force gate family
> (`config/gates.yaml` sha256 `521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4`).
> No threshold, direction, metric, or admission decision is modified here.
> **Source artefact:** `results/diagnostics/iter14_near_miss/per_factor_near_miss.json` (36 rows).

## 1. What this stream measures

For each of the 6 gate-screened factors (`accruals`, `high_52w`, `ivol_20d`,
`momentum_2_12`, `piotroski`, `profitability`), read the existing
`results/factors/<factor>/gate_results.json` payload, and for each of the 6
in-force gates compute `(metric_value, threshold, direction, gap, passes)`
plus a 3-valued `near_miss_tag`:

| Tag | Definition |
|---|---|
| `pass` | `passes == true` under the in-force direction |
| `near_miss_within_50bps_ic` | fails G2 or G3 by ≤ 0.005 (absolute) |
| `fail` | fails and is not within the near-miss band |

No aggregation, no ranking, no verdict change. The file is a denormalized
`(factor, gate) → (value, threshold, direction, gap, tag, passes)` table
suitable for downstream slicing.

## 2. Near-miss findings (2 of 36 rows)

Two rows are tagged `near_miss_within_50bps_ic` — both on **G2 IC mean**:

| Factor | Gate | Value | Threshold | Gap | Tag |
|---|---|---|---|---|---|
| `momentum_2_12` | G2_ic_mean | **+0.01889** | ≥ 0.02 | −0.00111 | `near_miss_within_50bps_ic` |
| `profitability` | G2_ic_mean | **+0.01579** | ≥ 0.02 | −0.00421 | `near_miss_within_50bps_ic` |

## 3. Gate-level pass/fail tally (observational)

Under the in-force family across the 6-factor panel:

| Gate | Passes | Fails | Of which near-miss |
|---|---|---|---|
| G0 (Sharpe ≥ 0.30) | 3 | 3 | 0 |
| G1 (perm_p < 0.05) | 5 | 1 | 0 |
| G2 (IC mean ≥ 0.02) | 0 | 6 | **2** |
| G3 (IC IR ≥ 0.50) | 0 | 6 | 0 |
| G4 (MDD ≥ −0.30) | 4 | 2 | 0 |
| G5 (marginal > 0) | 6 | 0 | 0 |

G5 is observationally degenerate on this panel (every factor marginal = 1.0
because the factor was screened in isolation — no competing factor set was
present at screening time). G3 is the hardest gate on this 6-factor panel
(0/6 pass; worst gap −0.554 at ivol_20d).

## 4. What this stream does NOT establish

- This stream does **not** propose any relaxation of G2 or G3.
- This stream does **not** change any of the 6 existing admission decisions
  (all 6 remain FAIL under the in-force family; see GL-0011 re-affirmation).
- The near-miss tag is a fixed observational label, not a gate criterion.

## 5. Dependencies for iter-15

The two G2 near-misses (`momentum_2_12`, `profitability`) are the only
factors on the 6-factor panel that are within one IC decimal place of
G2-admission under the in-force family. Any construction-grammar
modification in iter-15 that accidentally passes IC up through the pipeline
will risk admitting these two without a pre-registered v2 gate family — iter-15
must pre-register the v2 gate family **before** any re-screening under new
construction.
