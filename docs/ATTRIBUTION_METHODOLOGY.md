# Performance Attribution Methodology

**Version 0.1 | 2026-04-18 | Pre-Paper-Trade**
**Audience:** LP performance analysts, independent validator, internal review
**Produces:** Attribution tables in `docs/QUARTERLY_LETTER_TEMPLATE.md` §3 and §4

---

## Scope

Attribution answers: "For a given period, how much of the excess return came from
**sector bets** (allocation), **stock selection** (selection), and **factor tilts**
(factor attribution)?" This document specifies the decomposition, the formulas, and the
implementation requirements.

Two decompositions are produced each period:

1. **Brinson sector attribution** — allocation vs selection vs interaction across GICS
   sectors, against the RSP (equal-weight S&P 500) benchmark.
2. **Factor attribution** — contribution of each factor in the ensemble to realized gross
   return, via IC × position × realized return decomposition.

Both are required. Neither replaces the other.

---

## 1. Brinson Sector Attribution

Reference: Brinson, Hood, Beebower 1986 ("Determinants of Portfolio Performance").
Implementation target: `src/nyse_core/attribution.py` (currently planned, not built).

### 1.1 Notation

Let i index GICS sectors (11 sectors in the S&P 500). For period [t_0, t_1]:

| Symbol | Meaning |
|--------|---------|
| w_P(i) | average portfolio weight in sector i over the period |
| w_B(i) | average benchmark (RSP) weight in sector i over the period |
| r_P(i) | realized return of portfolio's sector-i holdings |
| r_B(i) | realized return of benchmark's sector-i holdings |
| r_B | benchmark total return = Σᵢ w_B(i) · r_B(i) |

### 1.2 Three-factor decomposition

For each sector i:

- **Allocation effect (A_i)** — what we earned by over/underweighting sector i:
  ```
  A_i = (w_P(i) − w_B(i)) · (r_B(i) − r_B)
  ```

- **Selection effect (S_i)** — what we earned by picking better/worse names inside
  sector i, holding weight at benchmark:
  ```
  S_i = w_B(i) · (r_P(i) − r_B(i))
  ```

- **Interaction effect (I_i)** — cross term (over/underweighting good/bad selections):
  ```
  I_i = (w_P(i) − w_B(i)) · (r_P(i) − r_B(i))
  ```

Totals:
```
Total Allocation    = Σᵢ A_i
Total Selection     = Σᵢ S_i
Total Interaction   = Σᵢ I_i
Active Return (R_A) = Σᵢ (A_i + S_i + I_i) = R_P − R_B
```

The sum of the three effects must equal total active return within rounding — this is
an **invariant check** on implementation. `tests/unit/test_attribution.py` will verify
`|R_A − (A + S + I)| < 1bps` on synthetic inputs.

### 1.3 Weight calculation convention

Weights are **time-averaged** over the period, not start-of-period snapshots. For a
weekly rebalanced strategy over a 13-week quarter, this means each week's weight is
treated equally in the average. Alternative conventions (compounded average, Karnosky-
Singer for currency) are not used because the strategy is single-currency and the
rebalance is discrete.

### 1.4 Interpretation rules

- **Positive allocation + negative selection** means the strategy bet on the right sectors
  but picked the wrong names. Diagnostic: factor ensemble should be generating stock-level
  alpha, so persistent negative selection is a factor-signal problem, not an allocation
  problem.
- **Negative allocation + positive selection** means the strategy picked good stocks in
  bad sectors. Diagnostic: since the strategy has no sector view (it's bottom-up factor
  ranking), a persistent allocation drag means the factor ensemble is inadvertently
  concentrating in a sector that underperforms. Reference: sector cap (30%) in
  `config/strategy_params.yaml`.
- **Residual after A+S+I = 0 within tolerance** confirms the decomposition is
  arithmetically complete. Any non-zero residual is an implementation bug.

### 1.5 Edge cases

| Case | Treatment |
|------|-----------|
| Sector has no positions in portfolio and no positions in benchmark | Omit row |
| Portfolio position in new sector added mid-period (GICS reclassification) | Use time-weighted weight; flag in footnote |
| Single-stock sector that goes to zero | Standard formula; the return term handles it |
| Cash position | Not a sector; reported as separate row with w_B = 0 |
| Corporate action mid-period (split, spinoff) | Use total-return index reconstruction per `src/nyse_core/corporate_actions.py` |

---

## 2. Factor Attribution

Decomposes gross return into contributions from each factor in the ensemble. Conceptually:
"What portion of our alpha came from the IVOL bet, what portion from Piotroski, what
portion from interactions, and what is unexplained?"

### 2.1 Notation

Let j index factors in the ensemble. For each rebalance t and each stock s in the
portfolio:

| Symbol | Meaning |
|--------|---------|
| f_j(t, s) | factor-j rank-percentile score in [0, 1] |
| β_j(t) | Ridge weight for factor j at rebalance t (from `src/nyse_core/signal_combination.py`) |
| w(t, s) | portfolio weight of stock s at rebalance t |
| r(t, s) | realized 5-day forward return for stock s from rebalance t |

### 2.2 Contribution formula

Per rebalance t, the portfolio's composite score for stock s is:
```
score(t, s) = Σⱼ β_j(t) · f_j(t, s)
```

The factor-j contribution to the portfolio's realized return for period t is:
```
C_j(t) = Σₛ β_j(t) · f_j(t, s) · w(t, s) · r(t, s)
```

Summed over rebalances in a reporting period:
```
C_j(period) = Σₜ C_j(t)
```

Total gross return:
```
R_P(period) = Σⱼ C_j(period) + Interaction + Residual
```

### 2.3 Interaction and residual

- **Interaction term** captures the fact that top-N selection is nonlinear: removing one
  factor doesn't simply reduce the score by its β — it changes which 20 stocks get
  selected. Computed as:
  ```
  Interaction = R_P(actual ensemble) − R_P(sum of single-factor portfolios)
  ```
  In practice, the per-factor "if only this factor had weight β_j and all others zero"
  return is computed; the gap vs actual is the interaction.
- **Residual** is the remainder: sector caps, regime overlay, sell-buffer, position
  inertia, and execution slippage all produce returns not attributable to raw factor
  scoring. Residual should be small in absolute value (target < 20% of total) after the
  ensemble is stable.

### 2.4 IC-based sanity check

For each factor, compute the realized IC (Spearman rank correlation between ranked
factor scores and realized 5-day forward returns) over the period. Contribution C_j
should be positive when realized IC is positive (same-sign check).

If a factor has positive C_j but negative realized IC (or vice versa), the discrepancy
arises from the portfolio construction layer (top-N selection, risk caps) and is flagged.
Persistent IC-vs-C_j sign disagreement indicates the factor is contributing to P&L for
reasons unrelated to its ranking signal — a red flag for the factor's continued inclusion.

### 2.5 Known limitations

- **Factor correlation biases the attribution.** If two factors are 0.7 correlated, the
  contribution allocation between them is partly arbitrary. Gate G2 enforces max
  pairwise correlation < 0.5 to keep this bounded.
- **Ridge regularization smears contribution.** Regularization biases β toward zero;
  contributions are slightly under-estimated in absolute value. Accepted as a property of
  the ensemble choice.
- **5-day forward-return label.** Attribution matches the label horizon. Longer horizons
  (compounding weekly over a quarter) use the 5-day per-rebalance return without
  re-compounding adjustments — documented here rather than hidden.

---

## 3. Combining Brinson + Factor

Brinson and factor attribution **answer different questions**:

- Brinson: "Where did the return come from in terms of sectors and stock picks vs RSP?"
- Factor: "Where did the return come from in terms of our ensemble components?"

They are **not additive** — reporting them on the same page does not imply they sum to
the same number. Each independently decomposes total return.

Quarterly letters present both:
- §3 Factor Attribution: which factors worked, with IC-vs-contribution sanity check
- §4 Sector Attribution (Brinson): allocation / selection / interaction vs RSP

A footnote in the letter explains they are orthogonal decompositions.

---

## 4. Implementation Requirements

Target: `src/nyse_core/attribution.py` (Phase 4 deliverable).

### 4.1 Interface

```python
class AttributionReport(FrozenDataclass):
    period_start: date
    period_end: date
    brinson: BrinsonTable                # rows per sector, cols for A/S/I/total
    factor: FactorContributionTable      # rows per factor, cols for β, C, IC, check
    invariants: dict[str, bool]          # all validation checks

def compute_attribution(
    portfolio_weights: pd.DataFrame,     # (date, symbol) → weight
    benchmark_weights: pd.DataFrame,     # (date, symbol) → RSP weight
    realized_returns: pd.DataFrame,      # (date, symbol) → return
    factor_scores: dict[str, pd.DataFrame],  # factor → (date, symbol) → [0,1]
    ridge_weights: pd.DataFrame,         # (date, factor) → β
    sector_map: pd.DataFrame,            # (date, symbol) → GICS sector
) -> tuple[AttributionReport, Diagnostics]:
    ...
```

Must return `(result, Diagnostics)` — strict purity boundary per plan.

### 4.2 Invariant tests (property-based)

| Invariant | Test |
|-----------|------|
| Brinson A + S + I = R_P − R_B | `tests/property/test_brinson_invariant.py` |
| Factor contributions sum to composite-score-based return | `tests/property/test_factor_attribution_invariant.py` |
| Single-sector portfolio → Brinson interaction = 0 | Edge case in unit tests |
| Equal-weight portfolio matching RSP → all Brinson effects = 0 | Edge case |
| Single-factor ensemble (β_j = 1 for one factor, 0 elsewhere) → factor contribution equals portfolio return | Edge case |

### 4.3 Data sources at runtime

- Portfolio weights: `live.duckdb` `positions` table
- Benchmark weights: monthly RSP constituency + equal weights (1/N per name)
- Realized returns: `live.duckdb` `ohlcv` table
- Factor scores: `research.duckdb` or `live.duckdb` `factor_scores` table
- Ridge weights: `live.duckdb` `model_state` table (persisted at each retrain)
- Sector map: EDGAR GICS mapping, point-in-time

Pre-live, synthetic fixtures in `tests/fixtures/` produce deterministic attribution
numbers used in CI.

---

## 5. Worked example (template)

Once a real period is attributable, the quarterly letter uses the template structure
from `docs/QUARTERLY_LETTER_TEMPLATE.md` §3 (factor) and §4 (Brinson). No example table
is included here to avoid the risk of a stale demo number being misread as a real result.

Per AP-6, worked examples use only synthetic or documented historical periods.

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Initial methodology. |

**Document owner:** Operator.
**Review cadence:** Before first LP letter; upon material change to ensemble composition or benchmark definition.
**Related documents:** `docs/QUARTERLY_LETTER_TEMPLATE.md`, `docs/STRESS_TEST_FRAMEWORK.md`, `docs/NYSE_ALPHA_TECHNICAL_BRIEF.md`.
