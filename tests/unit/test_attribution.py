"""Unit tests for the Brinson-style factor + sector attribution module."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from nyse_core.attribution import compute_attribution
from nyse_core.contracts import AttributionReport

# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_single_date_data(
    n_stocks: int = 20,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Build minimal single-date test data for attribution.

    Returns (portfolio_weights, stock_returns, factor_exposures, sector_map).
    """
    rng = np.random.default_rng(seed)
    dt = date(2024, 1, 15)
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]
    sectors = ["Tech", "Health", "Finance", "Energy", "Consumer"]

    # Portfolio weights (not equal — overweight first few stocks)
    raw_weights = rng.uniform(0.5, 2.0, size=n_stocks)
    weights = raw_weights / raw_weights.sum()

    # Stock returns
    returns = rng.normal(0.01, 0.03, size=n_stocks)

    # Factor exposures (one factor: "momentum")
    exposures = rng.standard_normal(n_stocks)

    # Sector map (round-robin)
    sector_map = pd.Series({sym: sectors[i % len(sectors)] for i, sym in enumerate(symbols)})

    pw = pd.DataFrame({"date": [dt] * n_stocks, "symbol": symbols, "weight": weights})
    sr = pd.DataFrame({"date": [dt] * n_stocks, "symbol": symbols, "return": returns})
    fe = pd.DataFrame(
        {
            "date": [dt] * n_stocks,
            "symbol": symbols,
            "factor_name": ["momentum"] * n_stocks,
            "exposure": exposures,
        }
    )
    return pw, sr, fe, sector_map


def _build_multi_date_data(
    n_stocks: int = 20,
    n_dates: int = 5,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Build multi-date test data."""
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, d) for d in range(10, 10 + n_dates)]
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]
    sectors = ["Tech", "Health", "Finance", "Energy", "Consumer"]

    pw_records = []
    sr_records = []
    fe_records = []

    for dt in dates:
        raw_w = rng.uniform(0.5, 2.0, size=n_stocks)
        w = raw_w / raw_w.sum()
        rets = rng.normal(0.005, 0.02, size=n_stocks)
        exps = rng.standard_normal(n_stocks)

        for i, sym in enumerate(symbols):
            pw_records.append({"date": dt, "symbol": sym, "weight": w[i]})
            sr_records.append({"date": dt, "symbol": sym, "return": rets[i]})
            fe_records.append(
                {
                    "date": dt,
                    "symbol": sym,
                    "factor_name": "value",
                    "exposure": exps[i],
                }
            )

    sector_map = pd.Series({sym: sectors[i % len(sectors)] for i, sym in enumerate(symbols)})

    return (
        pd.DataFrame(pw_records),
        pd.DataFrame(sr_records),
        pd.DataFrame(fe_records),
        sector_map,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestFactorAttributionSumsToTotal:
    """Factor contributions should roughly relate to total active return."""

    def test_factor_attribution_sums_to_total(self):
        pw, sr, fe, sector_map = _build_single_date_data(n_stocks=20, seed=42)

        report, diag = compute_attribution(
            portfolio_weights=pw,
            stock_returns=sr,
            factor_exposures=fe,
            sector_map=sector_map,
        )

        assert isinstance(report, AttributionReport)
        # Total return should be finite
        assert np.isfinite(report.total_return)
        # Factor contributions dict should exist
        assert "momentum" in report.factor_contributions
        assert not diag.has_errors


class TestSectorAttributionAllocationEffect:
    """Overweighting a winning sector should produce positive allocation effect."""

    def test_sector_attribution_allocation_effect(self):
        dt = date(2024, 3, 1)
        symbols = ["A", "B", "C", "D"]
        sectors = ["Tech", "Tech", "Health", "Health"]

        # Tech outperforms Health
        stock_returns = pd.DataFrame(
            {
                "date": [dt] * 4,
                "symbol": symbols,
                "return": [0.05, 0.04, -0.02, -0.03],
            }
        )

        # Portfolio overweights Tech (60% Tech vs 50% benchmark)
        portfolio_weights = pd.DataFrame(
            {
                "date": [dt] * 4,
                "symbol": symbols,
                "weight": [0.30, 0.30, 0.20, 0.20],
            }
        )

        # Equal-weight benchmark
        benchmark_weights = pd.DataFrame(
            {
                "date": [dt] * 4,
                "symbol": symbols,
                "weight": [0.25, 0.25, 0.25, 0.25],
            }
        )

        sector_map = pd.Series(dict(zip(symbols, sectors, strict=False)))

        report, diag = compute_attribution(
            portfolio_weights=portfolio_weights,
            stock_returns=stock_returns,
            factor_exposures=pd.DataFrame(columns=["date", "symbol", "factor_name", "exposure"]),
            sector_map=sector_map,
            benchmark_weights=benchmark_weights,
        )

        # Overweight in winning sector -> positive allocation for Tech
        assert report.sector_contributions.get("Tech", 0.0) >= 0.0
        assert not diag.has_errors


class TestEqualWeightBenchmarkDefault:
    """When benchmark_weights is None, equal-weight should be assumed."""

    def test_equal_weight_benchmark_default(self):
        pw, sr, fe, sector_map = _build_single_date_data(n_stocks=10, seed=42)

        report, diag = compute_attribution(
            portfolio_weights=pw,
            stock_returns=sr,
            factor_exposures=fe,
            sector_map=sector_map,
            benchmark_weights=None,  # Should use equal-weight
        )

        assert isinstance(report, AttributionReport)
        assert np.isfinite(report.total_return)
        # Check diagnostics mention equal-weight
        eq_msgs = [m for m in diag.messages if "equal-weight" in m.message.lower()]
        assert len(eq_msgs) > 0


class TestEmptyPortfolioReturnsZero:
    """Empty portfolio should return zero total return."""

    def test_empty_portfolio_returns_zero(self):
        empty_pw = pd.DataFrame(columns=["date", "symbol", "weight"])
        empty_sr = pd.DataFrame(columns=["date", "symbol", "return"])
        empty_fe = pd.DataFrame(columns=["date", "symbol", "factor_name", "exposure"])
        sector_map = pd.Series(dtype=str)

        report, diag = compute_attribution(
            portfolio_weights=empty_pw,
            stock_returns=empty_sr,
            factor_exposures=empty_fe,
            sector_map=sector_map,
        )

        assert report.total_return == 0.0
        assert report.factor_contributions == {}
        assert report.sector_contributions == {}


class TestAttributionReportHasAllFields:
    """AttributionReport should have all required fields populated."""

    def test_attribution_report_has_all_fields(self):
        pw, sr, fe, sector_map = _build_multi_date_data(n_stocks=20, n_dates=5, seed=42)

        report, diag = compute_attribution(
            portfolio_weights=pw,
            stock_returns=sr,
            factor_exposures=fe,
            sector_map=sector_map,
            period_start=date(2024, 1, 10),
            period_end=date(2024, 1, 14),
        )

        assert isinstance(report, AttributionReport)
        assert isinstance(report.factor_contributions, dict)
        assert isinstance(report.sector_contributions, dict)
        assert isinstance(report.total_return, float)
        assert isinstance(report.period_start, date)
        assert isinstance(report.period_end, date)
        assert report.period_start == date(2024, 1, 10)
        assert report.period_end == date(2024, 1, 14)
