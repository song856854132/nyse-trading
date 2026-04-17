# NYSE Cross-Sectional Alpha

**Version 0.4 | April 2026 | Pre-Paper-Trade**

---

## What Is It?

A systematic long-only equity strategy that ranks all S&P 500 stocks weekly using 13+ quantitative factors and buys the top 20 highest-scoring names at equal weight. The model identifies stocks that institutional flows, earnings quality, and microstructure signals suggest are undervalued relative to their cross-sectional peers. Weekly rebalance, fully automated, no discretionary override.

---

## Does It Work?

| Metric | Target | Basis |
|--------|:------:|:-----:|
| **Net Sharpe** | **0.8 -- 1.2** | TWSE predecessor achieved 1.186 |
| **CAGR** | **18 -- 28%** | TWSE achieved 23.22% |
| **Max Drawdown** | **-15% to -25%** | TWSE -16.7% with regime overlay |
| **Annual Turnover** | **< 50%** | Sell buffer saves ~1,644 bps on TWSE |
| **Cost Drag** | **< 3% of gross** | NYSE roundtrip ~12 bps (vs TWSE 68.5) |
| **Slippage Target** | **< 10 bps** | TWAP execution via NautilusTrader |

Research pipeline and walk-forward backtest are operational. Targets are pre-live estimates based on the TWSE predecessor system and NYSE cost advantages.

---

## The Edge

S&P 500 stocks are heavily covered, but cross-sectional factor premiums persist because no single institution can trade all of them simultaneously at weekly frequency without leaving alpha on the table. We exploit three structural frictions:

1. **Earnings quality mispricing.** Markets consistently underprice high-Piotroski, low-accrual companies relative to their peers. The signal decays slowly enough for weekly rebalancing to capture.
2. **Short interest information lag.** FINRA short interest data is published with an 11-day delay. By the time retail sees the data, institutional positioning has already moved. Our point-in-time pipeline respects this lag exactly.
3. **Volatility mean reversion.** Idiosyncratic volatility spikes create temporary dislocations. Stocks with falling IVOL revert to fair value faster than the market prices in, especially in the 5--20 day window our model targets.

---

## Risk Management

The system applies a 10-layer risk stack at every rebalance: regime overlay (bear market exposure cut to 40%), position caps (10% max per stock), sector caps (30% max per GICS sector), beta bounds, daily loss limits, earnings event caps, kill switch, position inertia, sell buffer hysteresis, and anti-double-dip enforcement.

Eight falsification triggers -- two VETO (halt trading), six WARNING (reduce exposure) -- are frozen before the first live trade. No retroactive threshold adjustment permitted.

---

## Status and Timeline

| Phase | Status | Key Milestone |
|-------|--------|---------------|
| Foundation + Core Pipeline | Complete | 934 tests passing, 0 failures |
| Data Infrastructure | Complete | FinMind, EDGAR, FINRA adapters live |
| Factor Research | Complete | 13+ factors across 6 families, gate-evaluated |
| Walk-Forward Optimization | Complete | Strict per-date feature recomputation |
| **Paper Trading** | **Next (May 2026)** | **3-month simulated $1M run** |
| Shadow + Live | Planned Q3--Q4 2026 | $100K minimum live, scaling to $500K--$2M |

![Equity Curve](figures/equity_curve.png)

---

*Technical Brief: [NYSE_ALPHA_TECHNICAL_BRIEF.md](NYSE_ALPHA_TECHNICAL_BRIEF.md) | Full Research Record: [NYSE_ALPHA_RESEARCH_RECORD.md](NYSE_ALPHA_RESEARCH_RECORD.md) | System Reference: [FRAMEWORK_AND_PIPELINE.md](FRAMEWORK_AND_PIPELINE.md) | Outcomes Tracker: [OUTCOME_VS_FORECAST.md](OUTCOME_VS_FORECAST.md) | Independent Validation (Draft): [INDEPENDENT_VALIDATION_DRAFT.md](INDEPENDENT_VALIDATION_DRAFT.md) | DDQ: [DDQ_AIMA_2025.md](DDQ_AIMA_2025.md)*
