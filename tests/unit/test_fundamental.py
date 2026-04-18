"""Unit tests for fundamental factor computations.

All three compute functions now consume long-format raw XBRL facts (matching
``EdgarAdapter.fetch`` output). Tests use narrowly-scoped fixtures built with
``_long_facts`` for formula-accuracy assertions, plus the full synthetic
generator for cross-sectional smoke tests.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nyse_core.features.fundamental import (
    compute_accruals,
    compute_piotroski_f_score,
    compute_profitability,
)
from nyse_core.schema import COL_SYMBOL
from tests.fixtures.synthetic_fundamentals import generate_fundamentals

# ── Helpers ──────────────────────────────────────────────────────────────────


def _long_facts(
    symbol: str,
    period_end: str,
    filing_date: str,
    filing_type: str = "10-Q",
    **metrics: float,
) -> list[dict]:
    """Build long-format XBRL fact rows for one (symbol, period_end) filing."""
    pe = pd.Timestamp(period_end).date()
    fd = pd.Timestamp(filing_date).date()
    return [
        {
            "date": fd,
            "symbol": symbol,
            "metric_name": name,
            "value": float(value),
            "filing_type": filing_type,
            "period_end": pe,
        }
        for name, value in metrics.items()
    ]


def _make_fundamentals(
    symbols: list[str] | None = None,
    n_quarters: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    if symbols is None:
        symbols = [f"SYM_{i:02d}" for i in range(5)]
    return generate_fundamentals(
        symbols=symbols,
        n_quarters=n_quarters,
        seed=seed,
    )


# ── Piotroski F-Score ────────────────────────────────────────────────────────


class TestPiotroskiFScore:
    def test_score_integer_in_range_on_synthetic(self) -> None:
        data = _make_fundamentals()
        result, diag = compute_piotroski_f_score(data)

        assert isinstance(result, pd.Series)
        for val in result.dropna():
            assert 0 <= val <= 9
            assert val == int(val)
        assert not diag.has_errors

    def test_cross_sectional_one_value_per_symbol(self) -> None:
        data = _make_fundamentals(symbols=["AAA", "BBB", "CCC"])
        result, _ = compute_piotroski_f_score(data)

        assert len(result) == 3
        assert set(result.index) == {"AAA", "BBB", "CCC"}

    def test_uses_latest_period_end(self) -> None:
        """Current filing = row with latest period_end."""
        rows = []
        rows += _long_facts(
            "A",
            "2023-12-31",
            "2024-02-14",
            filing_type="10-K",
            net_income=50,
            total_assets=500,
            operating_cash_flow=40,
            long_term_debt=200,
            current_assets=100,
            current_liabilities=80,
            shares_outstanding=1e8,
            revenue=300,
            gross_profit=100,
        )
        rows += _long_facts(
            "A",
            "2024-12-31",
            "2025-02-14",
            filing_type="10-K",
            net_income=100,
            total_assets=520,
            operating_cash_flow=120,
            long_term_debt=180,
            current_assets=140,
            current_liabilities=70,
            shares_outstanding=1e8,
            revenue=400,
            gross_profit=160,
        )
        df = pd.DataFrame(rows)
        result, _ = compute_piotroski_f_score(df)

        # All nine signals should pass for 2024 vs 2023:
        #   F1 ROA=.192 > 0
        #   F2 CFO=120 > 0
        #   F3 ROA .192 > .1
        #   F4 CFO 120 > NI 100
        #   F5 Lev .346 < .4
        #   F6 CR 2.0 > 1.25
        #   F7 shares equal
        #   F8 GM .4 > .333
        #   F9 Turnover .769 > .6
        assert result["A"] == 9.0

    def test_all_nine_signals_pass(self) -> None:
        """Construct a filing pair that should yield F-score = 9."""
        rows = []
        rows += _long_facts(
            "GOOD",
            "2023-03-31",
            "2023-05-15",
            net_income=100,
            total_assets=1000,
            operating_cash_flow=90,
            long_term_debt=300,
            current_assets=200,
            current_liabilities=150,
            shares_outstanding=1e8,
            revenue=800,
            gross_profit=240,
        )
        rows += _long_facts(
            "GOOD",
            "2024-03-31",
            "2024-05-15",
            net_income=200,
            total_assets=1100,
            operating_cash_flow=250,
            long_term_debt=280,
            current_assets=300,
            current_liabilities=150,
            shares_outstanding=1e8,
            revenue=1000,
            gross_profit=400,
        )
        df = pd.DataFrame(rows)
        result, _ = compute_piotroski_f_score(df)
        assert result["GOOD"] == 9.0

    def test_nan_when_no_prior_year_filing(self) -> None:
        """Five of nine signals require prior year; missing prior → NaN."""
        rows = _long_facts(
            "ONLY",
            "2024-03-31",
            "2024-05-15",
            net_income=100,
            total_assets=1000,
            operating_cash_flow=80,
            long_term_debt=300,
            current_assets=200,
            current_liabilities=150,
            shares_outstanding=1e8,
            revenue=1000,
            gross_profit=400,
        )
        df = pd.DataFrame(rows)
        result, _ = compute_piotroski_f_score(df)
        assert pd.isna(result["ONLY"])

    def test_deteriorating_signals_lower_score(self) -> None:
        """A strictly worse current year should score lower than a strictly better one."""
        better = pd.DataFrame(
            _long_facts(
                "B",
                "2023-03-31",
                "2023-05-15",
                net_income=100,
                total_assets=1000,
                operating_cash_flow=90,
                long_term_debt=300,
                current_assets=200,
                current_liabilities=150,
                shares_outstanding=1e8,
                revenue=800,
                gross_profit=240,
            )
            + _long_facts(
                "B",
                "2024-03-31",
                "2024-05-15",
                net_income=200,
                total_assets=1100,
                operating_cash_flow=250,
                long_term_debt=280,
                current_assets=300,
                current_liabilities=150,
                shares_outstanding=1e8,
                revenue=1000,
                gross_profit=400,
            )
        )
        worse = pd.DataFrame(
            _long_facts(
                "W",
                "2023-03-31",
                "2023-05-15",
                net_income=200,
                total_assets=1000,
                operating_cash_flow=250,
                long_term_debt=200,
                current_assets=300,
                current_liabilities=100,
                shares_outstanding=1e8,
                revenue=1000,
                gross_profit=400,
            )
            + _long_facts(
                "W",
                "2024-03-31",
                "2024-05-15",
                net_income=50,
                total_assets=1100,
                operating_cash_flow=30,
                long_term_debt=500,
                current_assets=150,
                current_liabilities=200,
                shares_outstanding=2e8,
                revenue=700,
                gross_profit=140,
            )
        )

        b_score, _ = compute_piotroski_f_score(better)
        w_score, _ = compute_piotroski_f_score(worse)
        assert b_score["B"] > w_score["W"]


# ── Accruals (Collins–Hribar) ────────────────────────────────────────────────


class TestAccruals:
    def test_formula_with_avg_assets(self) -> None:
        """(NI - CFO) / ((TA_curr + TA_prior) / 2)."""
        rows = _long_facts(
            "A",
            "2023-03-31",
            "2023-05-15",
            net_income=100,
            operating_cash_flow=80,
            total_assets=1000,
        ) + _long_facts(
            "A",
            "2024-03-31",
            "2024-05-15",
            net_income=200,
            operating_cash_flow=150,
            total_assets=1200,
        )
        result, _ = compute_accruals(pd.DataFrame(rows))
        # (200 - 150) / ((1200 + 1000) / 2) = 50 / 1100
        assert result["A"] == pytest.approx(50 / 1100)

    def test_falls_back_to_current_assets_when_prior_missing(self) -> None:
        rows = _long_facts(
            "A",
            "2024-03-31",
            "2024-05-15",
            net_income=200,
            operating_cash_flow=150,
            total_assets=1200,
        )
        result, _ = compute_accruals(pd.DataFrame(rows))
        # (200 - 150) / 1200
        assert result["A"] == pytest.approx(50 / 1200)

    def test_nan_when_ni_missing(self) -> None:
        rows = _long_facts(
            "A",
            "2024-03-31",
            "2024-05-15",
            operating_cash_flow=150,
            total_assets=1200,
        )
        result, _ = compute_accruals(pd.DataFrame(rows))
        assert pd.isna(result["A"])

    def test_cross_sectional_one_value_per_symbol(self) -> None:
        data = _make_fundamentals(symbols=["X", "Y", "Z"])
        result, _ = compute_accruals(data)
        assert len(result) == 3
        assert set(result.index) == {"X", "Y", "Z"}


# ── Gross Profitability (Novy-Marx) ──────────────────────────────────────────


class TestProfitability:
    def test_formula_direct_gross_profit(self) -> None:
        rows = _long_facts(
            "A",
            "2024-03-31",
            "2024-05-15",
            gross_profit=400,
            total_assets=1000,
        )
        result, _ = compute_profitability(pd.DataFrame(rows))
        assert result["A"] == pytest.approx(0.4)

    def test_gross_profit_derived_from_revenue_minus_cost(self) -> None:
        rows = _long_facts(
            "A",
            "2024-03-31",
            "2024-05-15",
            revenue=1000,
            cost_of_revenue=600,
            total_assets=2000,
        )
        result, _ = compute_profitability(pd.DataFrame(rows))
        # (1000 - 600) / 2000
        assert result["A"] == pytest.approx(0.2)

    def test_nan_when_assets_missing(self) -> None:
        rows = _long_facts(
            "A",
            "2024-03-31",
            "2024-05-15",
            revenue=1000,
            cost_of_revenue=600,
        )
        result, _ = compute_profitability(pd.DataFrame(rows))
        assert pd.isna(result["A"])

    def test_majority_positive_on_synthetic(self) -> None:
        """Synthetic generator produces positive gross profits by design."""
        data = _make_fundamentals(n_quarters=20)
        result, _ = compute_profitability(data)
        valid = result.dropna()
        assert len(valid) > 0
        assert (valid > 0).mean() > 0.8


# ── Empty / Degenerate Inputs ────────────────────────────────────────────────


class TestInsufficientData:
    def test_empty_dataframe_returns_empty_series(self) -> None:
        empty = pd.DataFrame(
            columns=[
                "date",
                COL_SYMBOL,
                "metric_name",
                "value",
                "filing_type",
                "period_end",
            ]
        )
        for fn in (
            compute_piotroski_f_score,
            compute_accruals,
            compute_profitability,
        ):
            result, diag = fn(empty)
            assert len(result) == 0
            # Empty input is expected, not an error — just a warning
            assert not diag.has_errors

    def test_symbol_with_no_facts_absent_from_output(self) -> None:
        rows = _long_facts(
            "A",
            "2024-03-31",
            "2024-05-15",
            gross_profit=400,
            total_assets=1000,
        )
        result, _ = compute_profitability(pd.DataFrame(rows))
        assert "Z" not in result.index
        assert "A" in result.index
