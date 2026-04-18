# Quarterly LP Letter — Template

**Strategy:** NYSE Cross-Sectional Alpha
**Period:** {{Q{{Q}} {{YYYY}}}}
**Letter date:** {{YYYY-MM-DD}}
**Audience:** Limited Partners

---

## How to use this template

Every quarterly letter fills in `{{placeholder}}` fields and keeps the section structure
intact. Deviating from the structure without documented reason is a drift signal — LPs
rely on consistent structure to detect narrative shift. If a section genuinely does not
apply in a given quarter, write "Not applicable this quarter" rather than deleting the
section.

**Hard rules:**

1. Every number is traceable to either `live.duckdb`, `research.duckdb`, or a cited public
   source. No number appears without provenance.
2. Performance is reported gross AND net. Net includes all fees, slippage, and costs.
3. Benchmark is RSP (equal-weight S&P 500). SPY is reported as a secondary reference
   only — comparing an equal-weight strategy to a cap-weight benchmark is misleading.
4. Attribution is per `docs/ATTRIBUTION_METHODOLOGY.md`. Brinson allocation / selection /
   interaction are separated; factor contribution is reported alongside.
5. Every falsification trigger that fired in the quarter is disclosed, whether remediated
   or not. Concealing a trigger is a fireable breach of LP agreement.
6. Negative quarters get the same attention as positive quarters. Losing money is the
   easier time to explain process; don't shortchange it.
7. No forward-looking return forecasts. Scenario framing and positioning are allowed;
   numerical predictions are not.

---

## Letter Body

### Letter from the operator

{{1-2 paragraphs — plain English. What happened, what drove it, what the operator
expected vs what occurred. Write as if to a sophisticated but non-specialist reader.
No jargon without immediate definition.}}

---

### 1. Performance Summary

**Period returns (net of all fees and costs):**

| Metric | {{Q{{Q}} {{YYYY}}}} | YTD {{YYYY}} | Since inception ({{inception_date}}) |
|--------|:-------:|:-------:|:-------:|
| Fund (net) | {{x.xx%}} | {{x.xx%}} | {{x.xx%}} |
| Fund (gross) | {{x.xx%}} | {{x.xx%}} | {{x.xx%}} |
| RSP (primary benchmark) | {{x.xx%}} | {{x.xx%}} | {{x.xx%}} |
| SPY (cap-weight reference) | {{x.xx%}} | {{x.xx%}} | {{x.xx%}} |
| Net excess vs RSP | {{+/- x.xx pp}} | {{+/- x.xx pp}} | {{+/- x.xx pp}} |

**Risk-adjusted:**

| Metric | {{Q{{Q}} {{YYYY}}}} | Trailing 12M | Since inception |
|--------|:-------:|:-------:|:-------:|
| Realized Sharpe (net) | {{x.xx}} | {{x.xx}} | {{x.xx}} |
| Realized volatility (ann., net) | {{xx.x%}} | {{xx.x%}} | {{xx.x%}} |
| Max drawdown | {{-x.x%}} | {{-x.x%}} | {{-x.x%}} |
| Best month | {{+x.x%}} | {{+x.x%}} | {{+x.x%}} |
| Worst month | {{-x.x%}} | {{-x.x%}} | {{-x.x%}} |

{{1 paragraph: honest framing. If net < gross by more than X bps/quarter, call it out.
If net excess vs RSP is negative, say so plainly; don't bury it in a subsequent section.}}

---

### 2. Top Contributors and Detractors

**Top 3 contributors (by realized P&L contribution):**

| # | Ticker | Sector | Held (weeks) | Contribution (bps) | Rationale held |
|---|--------|--------|:----:|:----:|---|
| 1 | {{TICK}} | {{GICS}} | {{N}} | {{+xxx}} | {{one sentence: which factor ranked it, which gate it cleared, what worked}} |
| 2 | {{TICK}} | {{GICS}} | {{N}} | {{+xxx}} | {{…}} |
| 3 | {{TICK}} | {{GICS}} | {{N}} | {{+xxx}} | {{…}} |

**Top 3 detractors:**

| # | Ticker | Sector | Held (weeks) | Contribution (bps) | Rationale held | Post-mortem |
|---|--------|--------|:----:|:----:|---|---|
| 1 | {{TICK}} | {{GICS}} | {{N}} | {{-xxx}} | {{one sentence}} | {{did the factor predict it? was it held too long? did risk controls fire?}} |
| 2 | {{TICK}} | {{GICS}} | {{N}} | {{-xxx}} | {{…}} | {{…}} |
| 3 | {{TICK}} | {{GICS}} | {{N}} | {{-xxx}} | {{…}} | {{…}} |

**Attribution integrity note:** These are per-position contributions. The sum of top 3
contributors + top 3 detractors rarely equals total period P&L — the remainder is
explained by the other {{N-6}} positions held during the quarter.

---

### 3. Factor Attribution

Methodology: `docs/ATTRIBUTION_METHODOLOGY.md`.

| Factor | Weight in ensemble | IC (quarter) | Contribution to gross return (bps) |
|--------|:----:|:----:|:----:|
| {{factor_1}} | {{xx.x%}} | {{x.xxx}} | {{+/- xxx}} |
| {{factor_2}} | {{xx.x%}} | {{x.xxx}} | {{+/- xxx}} |
| {{factor_3}} | {{xx.x%}} | {{x.xxx}} | {{+/- xxx}} |
| {{factor_4}} | {{xx.x%}} | {{x.xxx}} | {{+/- xxx}} |
| {{factor_5}} | {{xx.x%}} | {{x.xxx}} | {{+/- xxx}} |
| **Ensemble interaction** | — | — | {{+/- xxx}} |
| **Residual (unexplained)** | — | — | {{+/- xxx}} |
| **Total** | 100% | — | {{xxx}} |

{{1 paragraph: which factors worked, which didn't, and whether realized IC was within
one standard deviation of research-period IC. Factors outside band → narrative.}}

---

### 4. Sector Attribution (Brinson)

| GICS sector | Fund avg weight | RSP avg weight | Allocation effect (bps) | Selection effect (bps) | Interaction (bps) | Total (bps) |
|-------------|:----:|:----:|:----:|:----:|:----:|:----:|
| Information Technology | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Financials | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Health Care | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Consumer Discretionary | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Communication Services | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Industrials | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Consumer Staples | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Energy | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Utilities | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Real Estate | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| Materials | {{xx.x%}} | {{xx.x%}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} | {{+/- xx}} |
| **Total** | 100% | 100% | {{+/- xxx}} | {{+/- xxx}} | {{+/- xxx}} | {{+/- xxx}} |

{{1 paragraph: where allocation helped vs hurt, where selection did. Note structural
vs tactical drivers.}}

---

### 5. Regime and Market Context

**Regime state this quarter:**

| Indicator | Start of period | End of period |
|-----------|:----:|:----:|
| SPY > SMA-200 (bull/bear) | {{bull/bear}} | {{bull/bear}} |
| Regime exposure (portfolio gross) | {{xx%}} | {{xx%}} |
| Cross-sectional return dispersion (σ of 60d returns) | {{xx bps}} | {{xx bps}} |
| Short-interest percentile (strategy universe) | {{xx}} | {{xx}} |

{{1-2 paragraphs: what regime was the market in, how did the regime overlay adjust
exposure, how did dispersion affect the thesis. Reference TWSE historical analogies only
when honestly applicable — not as reassurance.}}

---

### 6. Positioning Changes

**Turnover:**

| Metric | Value |
|--------|:----:|
| Weekly rebalance count | {{N}} |
| Names added (quarter) | {{N}} |
| Names removed (quarter) | {{N}} |
| Quarterly one-way turnover | {{xx%}} |
| Annualized turnover (projection) | {{xx%}} |
| Turnover F5 trigger threshold | 200%/month = 50% weekly |
| Sell-buffer activations | {{N events}} |

**Sector drift during the quarter:**

{{Narrative on GICS sector weight drift: which sectors gained exposure, which lost.
Call out any sector that hit the 30% cap (should be rare given risk overlay).}}

---

### 7. Risk Events and Falsification Triggers

**Triggers fired (F1-F8):**

| Trigger | Fired? | Detail | Remediation |
|---------|:--:|--------|-------------|
| F1 signal_death (IC < 0.01 for 2 months) | {{Y/N}} | {{if Y: what was rolling IC, how long below}} | {{halt / paper / continue}} |
| F2 factor_death (3+ sign flips 2 months) | {{Y/N}} | {{detail}} | {{…}} |
| F3 excessive_drawdown (MaxDD < -25%) | {{Y/N}} | {{detail}} | {{…}} |
| F4 concentration (single stock > 15%) | {{Y/N}} | {{detail}} | {{…}} |
| F5 turnover_spike (monthly > 200%) | {{Y/N}} | {{detail}} | {{…}} |
| F6 cost_drag (annual > 5% gross) | {{Y/N}} | {{detail}} | {{…}} |
| F7 regime_anomaly (benchmark stale) | {{Y/N}} | {{detail}} | {{…}} |
| F8 data_staleness (feature max_age > 10d) | {{Y/N}} | {{detail}} | {{…}} |

**Other operational events:**

{{List trade errors, broker rejections, reconciliation breaks, data-vendor outages.
If none, say "None this quarter." — do not omit the section.}}

---

### 8. Outlook and Positioning

{{1-2 paragraphs. What is the current regime state, current ensemble composition
(no new factor weights disclosed in detail — LP has those separately), what would cause
the strategy to halt. Avoid numerical return forecasts. Framing allowed, forecasting
not.}}

---

### 9. Operational and Governance Updates

{{Any of:
- Service provider changes (new FA, new auditor, new broker)
- Regulatory filings (Form ADV, PF, etc.)
- Key-person changes
- Advisory board updates
- Model validation or audit results
- Material changes to strategy parameters (must cross-reference research-log event)
- Material changes to configs (must cross-reference git commit)
If none: "No material changes this quarter."}}

---

### 10. Fees and Expenses

| Line item | Quarter | YTD |
|-----------|:----:|:----:|
| Management fee (accrued) | {{x.xx% annualized}} | {{x.xx%}} |
| Performance fee (crystallized) | {{x.xx% over HWM}} | {{x.xx%}} |
| Administration | {{$x,xxx}} | {{$x,xxx}} |
| Audit | {{$x,xxx}} | {{$x,xxx}} |
| Legal / compliance | {{$x,xxx}} | {{$x,xxx}} |
| Data vendors | {{$x,xxx}} | {{$x,xxx}} |
| Brokerage commissions | {{$x,xxx}} | {{$x,xxx}} |
| Slippage (vs decision price) | {{$x,xxx}} | {{$x,xxx}} |
| **Total expense ratio (net)** | **{{x.xx%}}** | **{{x.xx%}}** |

{{If TER > 3% annualized, call it out. Small-AUM expense ratio problem is not hidden.}}

---

### Appendix A — Reconciliation Summary

| Item | Count | Exceptions |
|------|:----:|:----:|
| Weekly rebalances | {{13}} | {{N}} |
| Trades submitted | {{xxx}} | {{N}} |
| Fills received | {{xxx}} | {{N}} |
| Position reconciliations | {{xxx}} | {{N rejected > 0.5%}} |
| NAV calculations (shadow vs FA) | {{13}} | {{N differences > $100}} |

---

### Appendix B — Research Pipeline Updates

{{Factors screened this quarter, factors added/removed from ensemble, gate failures,
investigations launched. Cross-reference `docs/OUTCOME_VS_FORECAST.md` and research-log
event hashes so LP can verify.}}

---

### Appendix C — Disclosures

Past performance is not indicative of future results. This letter is prepared for
limited partners of {{Fund Legal Name}} only and is not an offer to sell securities.
Performance data is unaudited at the time of this letter; audited financials are
delivered annually by {{Auditor Name}}. Benchmark selection (RSP) is operator's view;
SPY is included for reference consistency with industry practice. Fees and expenses
reflect actual charges for the quarter; annualized expense ratios are projections.

This letter is covered by the {{Fund LPA}} §{{§}} on reporting.

Every numerical claim in this letter is reproducible from the source data on file at
the operator's research host. Reproduction procedure: `scripts/reproduce.sh --period
{{QX_YYYY}}`. LPs or their DDQ teams may request a dry-run of this procedure under NDA.

---

### Appendix D — Contact and Inquiry

{{operator contact info}}

---

## Change Log

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-04-18 | Initial template draft. |

**Document owner:** Operator.
**Review cadence:** Every quarter before letter send; revise template only at calendar-year
boundary to preserve comparability.
