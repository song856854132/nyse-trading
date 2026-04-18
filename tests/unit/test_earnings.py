"""Unit tests for earnings factor computations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.features.earnings import compute_earnings_surprise
from nyse_core.schema import COL_SYMBOL

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_earnings_data(
    symbol: str,
    profitability_series: list[float],
) -> pd.DataFrame:
    """Build minimal quarterly fundamentals for earnings surprise testing."""
    n = len(profitability_series)
    quarter_ends = pd.date_range(end="2024-12-31", periods=n, freq="QE")
    return pd.DataFrame(
        {
            COL_SYMBOL: symbol,
            "filing_date": [(q + pd.Timedelta(days=45)).date() for q in quarter_ends],
            "period_end": [q.date() for q in quarter_ends],
            "operating_profitability": profitability_series,
        }
    )


# ── Earnings Surprise Tests ──────────────────────────────────────────────────


class TestEarningsSurprise:
    def test_earnings_surprise_positive_for_improving_stock(self) -> None:
        """Stock with consistently improving profitability should have positive SUE."""
        # Steadily improving profitability: each quarter higher than the last
        data = _make_earnings_data("IMPROVE", [0.10, 0.12, 0.14, 0.16, 0.20])
        result, diag = compute_earnings_surprise(data)

        assert isinstance(result, pd.Series)
        assert result["IMPROVE"] > 0  # positive surprise
        assert not diag.has_errors

    def test_earnings_surprise_negative_for_declining_stock(self) -> None:
        """Stock with declining profitability should have negative SUE."""
        # Steadily declining profitability
        data = _make_earnings_data("DECLINE", [0.20, 0.18, 0.16, 0.14, 0.10])
        result, diag = compute_earnings_surprise(data)

        assert result["DECLINE"] < 0  # negative surprise

    def test_insufficient_quarters_returns_nan(self) -> None:
        """Stock with < 4 quarters should get NaN."""
        data = _make_earnings_data("SHORT", [0.10, 0.12, 0.14])
        result, diag = compute_earnings_surprise(data)

        assert np.isnan(result["SHORT"])
        assert diag.has_warnings

    def test_cross_sectional(self) -> None:
        """Multiple stocks: improving stock has higher SUE than declining."""
        up = _make_earnings_data("UP", [0.10, 0.12, 0.14, 0.16, 0.20])
        dn = _make_earnings_data("DN", [0.20, 0.18, 0.16, 0.14, 0.10])
        data = pd.concat([up, dn], ignore_index=True)

        result, diag = compute_earnings_surprise(data)

        assert result["UP"] > result["DN"]
        assert result["UP"] > 0
        assert result["DN"] < 0

    def test_constant_profitability_returns_nan(self) -> None:
        """If profitability never changes, std=0 so SUE is NaN."""
        data = _make_earnings_data("FLAT", [0.15, 0.15, 0.15, 0.15, 0.15])
        result, diag = compute_earnings_surprise(data)

        assert np.isnan(result["FLAT"])

    def test_returns_diagnostics(self) -> None:
        """Verify Diagnostics object is always returned."""
        data = _make_earnings_data("TEST", [0.10, 0.12, 0.14, 0.16, 0.18])
        result, diag = compute_earnings_surprise(data)

        assert isinstance(diag, Diagnostics)
        assert len(diag.messages) > 0
