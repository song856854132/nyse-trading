# Performance Attribution Report — `<PERIOD_LABEL>`

> **Template version 0.1 | Frozen layout | Last revised 2026-04-19**
> Methodology: `docs/ATTRIBUTION_METHODOLOGY.md` • Machine-fillable schema:
> `docs/templates/ATTRIBUTION_REPORT.schema.json`
> This is a **template**. The numbers below are **synthetic** (marked with ⬛)
> and exist only to demonstrate the layout. Real reports replace every ⬛ value
> with the programmatic output of `src/nyse_core/attribution.py` (Phase 4).

---

## 0. Header

| Field | Value |
|---|---|
| Report ID | `<ATTR-YYYY-MM>` |
| Strategy | NYSE cross-sectional equity, top-N long-only, weekly rebalance |
| Reporting period | `<YYYY-MM-DD>` through `<YYYY-MM-DD>` (`<N>` rebalances) |
| Benchmark | RSP (S&P 500 Equal-Weight) — see `docs/ATTRIBUTION_METHODOLOGY.md §3` |
| Secondary benchmark | SPY (cap-weight) — used only for regime overlay, not attribution |
| Report generated | `<YYYY-MM-DD HH:MM ET>` |
| Preparer | `<operator-name>` |
| Git commit (code) | `<sha>` |
| Config hash (strategy) | `<sha256 of strategy_params.yaml>` |
| Research-log anchor | `<last chained hash before report generation>` |
| Data snapshot | `<duckdb schema hash + row counts>` |
| Mode | **paper** ∣ **shadow** ∣ **live** (one only) |

---

## 1. Executive summary

One sentence describing how the portfolio performed against the benchmark.
One sentence naming the single largest contributor and detractor. One sentence
flagging any invariant that failed (or "all invariants passed"). No jargon
beyond "return" and "attribution" — the audience includes non-quant
stakeholders.

| | Portfolio (R_P) | Benchmark RSP (R_B) | Active (R_A = R_P − R_B) |
|---|:---:|:---:|:---:|
| Gross return | ⬛ +3.42% | ⬛ +2.10% | ⬛ +1.32% |
| Transaction costs | ⬛ −0.28% | (n/a) | (n/a) |
| Net return | ⬛ +3.14% | ⬛ +2.10% | ⬛ +1.04% |

Numbers are totals for the reporting period, geometrically compounded from
per-rebalance returns. Costs come from `src/nyse_core/cost_model.py` using
ADV-dependent spread + commissions + Monday/earnings-week multipliers.

---

## 2. Factor attribution

Per-factor contribution to **gross** return. Formulas in
`docs/ATTRIBUTION_METHODOLOGY.md §2`.

| Factor | β (avg Ridge weight) | C_j (contribution) | Realized IC (Spearman) | Sign check |
|---|:---:|:---:|:---:|:---:|
| ivol_20d | ⬛ +0.24 | ⬛ +0.51% | ⬛ +0.031 | PASS (both positive) |
| piotroski | ⬛ +0.18 | ⬛ +0.34% | ⬛ +0.018 | PASS |
| earnings_surprise | ⬛ +0.15 | ⬛ +0.27% | ⬛ +0.014 | PASS |
| high_52w | ⬛ +0.12 | ⬛ +0.19% | ⬛ +0.009 | PASS |
| momentum_2_12 | ⬛ +0.10 | ⬛ −0.06% | ⬛ −0.004 | PASS (both negative) |
| short_ratio | ⬛ +0.08 | ⬛ +0.14% | ⬛ +0.007 | PASS |
| accruals | ⬛ +0.07 | ⬛ +0.10% | ⬛ +0.006 | PASS |
| profitability | ⬛ +0.06 | ⬛ +0.09% | ⬛ +0.005 | PASS |
| **Sum of factor contributions** | | ⬛ **+1.58%** | | |
| Interaction term (top-N nonlinearity) | | ⬛ +0.23% | | |
| Residual (regime, sector caps, sell-buffer, execution) | | ⬛ −0.49% | | |
| **Total gross = sum of above** | | ⬛ **+1.32%** | | Matches R_A above ✓ |

**Sign-check rule:** realized IC and contribution C_j must have the same sign
for the factor to be "working as designed". A mismatch flags portfolio-
construction drag (top-N, risk caps) and is escalated if persistent over 3+
periods — see `docs/RISK_REGISTER.md:R-F2`.

---

## 3. Brinson sector attribution

Allocation / selection / interaction by GICS sector vs RSP. Formulas in
`docs/ATTRIBUTION_METHODOLOGY.md §1`.

| GICS Sector | Port wt (avg) | RSP wt (avg) | A_i (alloc) | S_i (select) | I_i (interact) | Total |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Information Technology | ⬛ 18.0% | ⬛ 13.5% | ⬛ +0.23% | ⬛ +0.31% | ⬛ +0.06% | ⬛ +0.60% |
| Health Care | ⬛ 15.0% | ⬛ 12.8% | ⬛ +0.04% | ⬛ +0.11% | ⬛ +0.02% | ⬛ +0.17% |
| Financials | ⬛ 13.0% | ⬛ 13.2% | ⬛ −0.01% | ⬛ +0.18% | ⬛ −0.00% | ⬛ +0.17% |
| Industrials | ⬛ 10.0% | ⬛ 9.5% | ⬛ +0.02% | ⬛ +0.07% | ⬛ +0.01% | ⬛ +0.10% |
| Consumer Discretionary | ⬛ 9.0% | ⬛ 10.0% | ⬛ −0.02% | ⬛ +0.06% | ⬛ −0.01% | ⬛ +0.03% |
| Consumer Staples | ⬛ 7.0% | ⬛ 8.2% | ⬛ +0.03% | ⬛ −0.04% | ⬛ −0.01% | ⬛ −0.02% |
| Energy | ⬛ 6.0% | ⬛ 5.5% | ⬛ +0.03% | ⬛ −0.09% | ⬛ −0.01% | ⬛ −0.07% |
| Utilities | ⬛ 6.0% | ⬛ 5.8% | ⬛ +0.00% | ⬛ +0.04% | ⬛ +0.00% | ⬛ +0.04% |
| Materials | ⬛ 5.0% | ⬛ 5.2% | ⬛ −0.00% | ⬛ +0.03% | ⬛ −0.00% | ⬛ +0.03% |
| Real Estate | ⬛ 5.0% | ⬛ 5.0% | ⬛ +0.00% | ⬛ +0.20% | ⬛ +0.00% | ⬛ +0.20% |
| Communication Services | ⬛ 6.0% | ⬛ 11.3% | ⬛ −0.12% | ⬛ +0.20% | ⬛ −0.01% | ⬛ +0.07% |
| Cash | ⬛ 0.0% | 0.0% | 0.00% | 0.00% | 0.00% | 0.00% |
| **Totals** | ⬛ 100.0% | 100.0% | ⬛ **+0.20%** | ⬛ **+1.07%** | ⬛ **+0.05%** | ⬛ **+1.32%** |

**Invariant:** `A + S + I = R_A` within 1 bp. ⬛ 0.20 + 1.07 + 0.05 = 1.32 ✓

**Interpretation rules** in `docs/ATTRIBUTION_METHODOLOGY.md §1.4`. For this
synthetic example: positive selection dominates, which is what a bottom-up
factor ensemble is designed to produce. Sector allocation is a side-effect of
factor ranking (no explicit sector view) and is near zero.

---

## 4. Top and bottom 10 names by contribution

| Rank | Symbol | Sector | Avg wt | Period return | P&L contrib | Dominant factor |
|---:|---|---|:---:|:---:|:---:|---|
| 1 | ⬛ AAPL | IT | ⬛ 5.2% | ⬛ +6.8% | ⬛ +35 bp | ⬛ ivol_20d |
| 2 | ⬛ UNH | HC | ⬛ 5.1% | ⬛ +5.4% | ⬛ +28 bp | ⬛ piotroski |
| 3 | ⬛ MSFT | IT | ⬛ 5.0% | ⬛ +5.1% | ⬛ +26 bp | ⬛ ivol_20d |
| 4 | ⬛ JPM | FIN | ⬛ 5.0% | ⬛ +4.9% | ⬛ +25 bp | ⬛ earnings_surprise |
| 5 | ⬛ … | … | … | … | … | … |
| … | | | | | | |
| N−4 | ⬛ … | … | … | … | … | … |
| N−3 | ⬛ TSLA | CD | ⬛ 5.0% | ⬛ −4.2% | ⬛ −21 bp | ⬛ high_52w |
| N−2 | ⬛ META | COMM | ⬛ 5.0% | ⬛ −5.1% | ⬛ −26 bp | ⬛ momentum_2_12 |
| N−1 | ⬛ XOM | ENG | ⬛ 5.0% | ⬛ −5.8% | ⬛ −29 bp | ⬛ short_ratio |
| N | ⬛ NEE | UTL | ⬛ 5.0% | ⬛ −6.5% | ⬛ −33 bp | ⬛ profitability |

"Dominant factor" is the factor whose per-stock contribution
`β_j(t) · f_j(t,s) · w(t,s) · r(t,s)` absolute-valued to the most across the
period. Tied factors are listed with "/" separator.

---

## 5. Cost breakdown

| Component | Value (bp) | Notes |
|---|:---:|---|
| Half-spread (ADV-dependent) | ⬛ 18 bp | Base 10 bp × √(mean ADV scaling) |
| Monday-open multiplier | ⬛ +3 bp | Applied to Monday fills only |
| Earnings-week multiplier | ⬛ +2 bp | Applied if within ±2 trading days |
| Commission (IB default) | ⬛ 5 bp | $0.005/share at typical prices |
| Realized slippage (fill vs TWAP target) | ⬛ 0 bp | Reported separately; target ≤ 10 bp |
| **Total cost drag** | ⬛ **28 bp** | Period-total; annualize for F6 check |
| Annualized cost drag | ⬛ 3.4% | **F6 threshold 5% (WARNING)** — within limit |

---

## 6. Invariant checks (must all pass)

| # | Invariant | Value | Status |
|---:|---|:---:|:---:|
| 1 | Factor contributions + interaction + residual = R_P gross (within 1 bp) | ⬛ |Δ| = 0.0 bp | PASS |
| 2 | Brinson A + S + I = R_P − R_B (within 1 bp) | ⬛ |Δ| = 0.0 bp | PASS |
| 3 | Sector weights sum to 100% (portfolio and benchmark) | ⬛ 100.0% / 100.0% | PASS |
| 4 | Every factor with C_j > 0 has realized IC > 0 (or equiv. for negative) | ⬛ 8/8 factors | PASS |
| 5 | No single stock contribution > 10% of gross (concentration sanity) | ⬛ max 2.7% | PASS |
| 6 | Cost drag ≤ F6 threshold (5%/yr) | ⬛ 3.4%/yr | PASS |
| 7 | Period reported is ≤ today and ≥ 2016-01-01 (research period) | ⬛ in-window | PASS |
| 8 | Research-log anchor hash is present and verifies against chain | ⬛ verified | PASS |

Any FAIL here gates publication of the report — attribution numbers must not
be circulated externally until invariants all pass.

---

## 7. Diagnostics (internal)

Populated from the `Diagnostics` tuple returned by
`src/nyse_core/attribution.py`. Typical entries: rebalance dates covered,
factor-NaN fractions, sector-map staleness, regime-state transitions during
the period.

```
INFO  attribution.brinson       Computed 11 sector rows from 13 rebalances
INFO  attribution.factor        Ridge weights averaged across 13 rebalances
WARN  attribution.sector_map    GICS reclassification for <TICKER> on <date>
INFO  attribution.invariants    All 8 invariants passed
```

---

## 8. Change log

| Date | Change |
|---|---|
| 2026-04-19 | Template 0.1 — frozen layout (TODO-15). Synthetic worked example. |

---

## 9. Footnotes

1. **"Synthetic" labels (⬛)** mark placeholder numbers. A real report contains
   no `⬛` markers.
2. **Attribution is pre-cost** unless otherwise stated. The §1 executive
   summary reports both gross and net; §2 and §3 decomposition tables are
   gross-of-cost so the sum matches R_A computed before fees.
3. **Brinson and factor attribution are orthogonal decompositions** —
   §2 and §3 do not sum to each other. See
   `docs/ATTRIBUTION_METHODOLOGY.md §3`.
4. **5-day forward-return label** underlies factor attribution; quarterly
   reports compound these without re-compounding adjustments
   (`ATTRIBUTION_METHODOLOGY.md §2.5`).
5. **No live performance** exists as of the template commit. Real paper-mode
   numbers are blocked on ≥3 factors clearing G0-G5 — see
   `docs/OUTCOME_VS_FORECAST.md` and `docs/ABANDONMENT_CRITERIA.md:R-A1`.

---

*Related: [ATTRIBUTION_METHODOLOGY.md](../ATTRIBUTION_METHODOLOGY.md) (formulas) • [QUARTERLY_LETTER_TEMPLATE.md](../QUARTERLY_LETTER_TEMPLATE.md) (LP-facing wrapper) • [RISK_REGISTER.md](../RISK_REGISTER.md) • [ATTRIBUTION_REPORT.schema.json](ATTRIBUTION_REPORT.schema.json) (machine-fill sidecar) • [TODOS.md](../TODOS.md)*
