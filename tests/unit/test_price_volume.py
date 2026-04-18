"""Unit tests for cross-sectional price/volume factor computations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.contracts import Diagnostics
from nyse_core.features.price_volume import (
    compute_52w_high_proximity,
    compute_ivol_20d,
    compute_momentum_2_12,
)
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL
from tests.fixtures.synthetic_prices import generate_prices

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_multi_stock_prices(
    n_stocks: int = 5,
    n_days: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate cross-sectional OHLCV for n_stocks over n_days."""
    return generate_prices(n_stocks=n_stocks, n_days=n_days, seed=seed)


def _make_single_symbol_df(
    symbol: str,
    n_days: int,
    start_price: float = 100.0,
    drift: float = 0.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a single-stock DataFrame matching multi-stock schema."""
    rng = np.random.RandomState(seed)
    returns = 1.0 + rng.normal(drift, 0.015, size=n_days)
    close = start_price * np.cumprod(returns)
    dates = pd.bdate_range("2022-01-03", periods=n_days, freq="B")
    return pd.DataFrame(
        {
            COL_DATE: [d.date() for d in dates],
            COL_SYMBOL: symbol,
            COL_CLOSE: close,
        }
    )


# ── IVOL Tests ───────────────────────────────────────────────────────────────


class TestIVOLCrossSectional:
    def test_ivol_cross_sectional(self) -> None:
        """5 stocks, 100 days: returns Series indexed by symbol."""
        data = _make_multi_stock_prices(n_stocks=5, n_days=100)
        result, diag = compute_ivol_20d(data)

        assert isinstance(result, pd.Series)
        assert result.index.name == COL_SYMBOL
        # At least some stocks should have sufficient history (100 > 15)
        valid = result.dropna()
        assert len(valid) > 0
        assert all(v > 0 for v in valid)
        assert not diag.has_errors

    def test_ivol_insufficient_history(self) -> None:
        """Stock with < 15 days should get NaN."""
        short = _make_single_symbol_df("SHORT", n_days=10)
        long_ = _make_single_symbol_df("LONG", n_days=50, seed=99)
        data = pd.concat([short, long_], ignore_index=True)

        result, diag = compute_ivol_20d(data)

        assert np.isnan(result["SHORT"])
        assert not np.isnan(result["LONG"])
        assert result["LONG"] > 0
        assert diag.has_warnings

    def test_ivol_exactly_15_days(self) -> None:
        """15 days is the minimum -- should compute successfully."""
        data = _make_single_symbol_df("TEST", n_days=15)
        result, diag = compute_ivol_20d(data)

        assert not np.isnan(result["TEST"])
        assert result["TEST"] > 0

    def test_ivol_constant_prices(self) -> None:
        """Constant prices yield zero volatility."""
        dates = pd.bdate_range("2022-01-03", periods=25, freq="B")
        data = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates],
                COL_SYMBOL: "FLAT",
                COL_CLOSE: [100.0] * 25,
            }
        )
        result, diag = compute_ivol_20d(data)

        assert result["FLAT"] == 0.0


# ── 52-Week High Proximity Tests ─────────────────────────────────────────────


class TestHigh52WCrossSectional:
    def test_52w_high_cross_sectional(self) -> None:
        """Multi-stock: values should be in (0, 1]."""
        data = _make_multi_stock_prices(n_stocks=5, n_days=300)
        result, diag = compute_52w_high_proximity(data)

        assert isinstance(result, pd.Series)
        valid = result.dropna()
        assert len(valid) > 0
        assert all(0 < v <= 1.0 for v in valid)
        assert not diag.has_errors

    def test_at_52w_high(self) -> None:
        """If current close is the 52w high, proximity should be 1.0."""
        dates = pd.bdate_range("2022-01-03", periods=260, freq="B")
        data = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates],
                COL_SYMBOL: "UP",
                COL_CLOSE: list(range(1, 261)),
            }
        )
        result, diag = compute_52w_high_proximity(data)

        assert result["UP"] == pytest.approx(1.0)

    def test_below_52w_high(self) -> None:
        """Proximity should be < 1.0 when not at the high."""
        dates = pd.bdate_range("2022-01-03", periods=260, freq="B")
        close = list(range(1, 258)) + [200, 150, 100]
        data = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates],
                COL_SYMBOL: "DOWN",
                COL_CLOSE: close,
            }
        )
        result, diag = compute_52w_high_proximity(data)

        assert result["DOWN"] < 1.0
        assert result["DOWN"] > 0.0

    def test_insufficient_history(self) -> None:
        """Stock with < 200 days should get NaN."""
        data = _make_single_symbol_df("YOUNG", n_days=100)
        result, diag = compute_52w_high_proximity(data)

        assert np.isnan(result["YOUNG"])
        assert diag.has_warnings


# ── Momentum 2-12 Tests ─────────────────────────────────────────────────────


class TestMomentumCrossSectional:
    def test_momentum_cross_sectional(self) -> None:
        """Stock that went up has positive momentum, down has negative."""
        # Uptrend stock
        dates_up = pd.bdate_range("2022-01-03", periods=260, freq="B")
        up_df = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates_up],
                COL_SYMBOL: "UP",
                COL_CLOSE: np.linspace(100, 200, 260),
            }
        )
        # Downtrend stock
        dates_dn = pd.bdate_range("2022-01-03", periods=260, freq="B")
        dn_df = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates_dn],
                COL_SYMBOL: "DOWN",
                COL_CLOSE: np.linspace(200, 100, 260),
            }
        )
        data = pd.concat([up_df, dn_df], ignore_index=True)

        result, diag = compute_momentum_2_12(data)

        assert result["UP"] > 0
        assert result["DOWN"] < 0
        assert not diag.has_errors

    def test_insufficient_history(self) -> None:
        """Stock with < 252 days should get NaN."""
        data = _make_single_symbol_df("YOUNG", n_days=200)
        result, diag = compute_momentum_2_12(data)

        assert np.isnan(result["YOUNG"])
        assert diag.has_warnings

    def test_skips_recent_month(self) -> None:
        """Verify momentum ignores the most recent ~21 trading days."""
        dates = pd.bdate_range("2022-01-03", periods=252, freq="B")
        # Rise for 11 months, crash in last month
        steady = np.linspace(100, 200, 252 - 21)
        crash = np.linspace(200, 50, 22)[1:]
        close = np.concatenate([steady, crash])
        data = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates],
                COL_SYMBOL: "CRASH",
                COL_CLOSE: close,
            }
        )
        result, diag = compute_momentum_2_12(data)

        # Momentum from 12m to 2m ago should still be positive
        assert result["CRASH"] > 0


# ── Diagnostics Tests ────────────────────────────────────────────────────────


class TestDiagnostics:
    def test_all_return_diagnostics(self) -> None:
        """All three functions return a Diagnostics object."""
        data = _make_multi_stock_prices(n_stocks=3, n_days=300)

        for compute_fn in [compute_ivol_20d, compute_52w_high_proximity, compute_momentum_2_12]:
            result, diag = compute_fn(data)
            assert isinstance(result, pd.Series)
            assert isinstance(diag, Diagnostics)
            assert len(diag.messages) > 0
