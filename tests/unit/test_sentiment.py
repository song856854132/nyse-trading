"""Unit tests for sentiment / microstructure factors (cross-sectional).

Tests verify:
  - Cross-sectional output: one value per symbol
  - Put/call ratio edge cases (zero calls -> NaN)
  - Volume momentum captures high activity
  - EWMAC positive/negative trend detection
  - Insufficient history -> NaN
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.features.sentiment import (
    compute_ewmac,
    compute_put_call_ratio,
    compute_volume_momentum,
)
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL, COL_VOLUME

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_options_data(
    symbols: list[str],
    put_volumes: list[float],
    call_volumes: list[float],
) -> pd.DataFrame:
    """Build single-period options DataFrame."""
    return pd.DataFrame(
        {
            COL_SYMBOL: symbols,
            COL_DATE: pd.Timestamp("2024-12-15").date(),
            "put_volume": put_volumes,
            "call_volume": call_volumes,
        }
    )


def _make_trending_stock(
    symbol: str,
    n_days: int,
    drift: float,
    start_price: float = 100.0,
    seed: int = 42,
    annual_vol: float = 0.02,
) -> pd.DataFrame:
    """Generate OHLCV data for a single stock with a specified drift.

    Positive drift = uptrend, negative drift = downtrend.
    Uses low vol by default so the trend signal dominates noise for test clarity.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start="2022-01-03", periods=n_days, freq="B")

    daily_drift = drift / 252
    daily_vol = annual_vol / np.sqrt(252)
    log_returns = rng.normal(daily_drift, daily_vol, n_days)
    close = start_price * np.exp(np.cumsum(log_returns))

    # Base volume with some variation
    volume = rng.lognormal(mean=14.5, sigma=0.3, size=n_days).astype(int)

    return pd.DataFrame(
        {
            COL_DATE: [d.date() for d in dates],
            COL_SYMBOL: symbol,
            COL_CLOSE: np.round(close, 2),
            COL_VOLUME: volume,
        }
    )


def _make_volume_spike_stock(
    symbol: str,
    n_days: int = 30,
    spike_factor: float = 3.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a stock with a volume spike in the last 5 days."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start="2022-01-03", periods=n_days, freq="B")
    close = 100.0 + rng.normal(0, 1, n_days).cumsum()

    base_volume = np.full(n_days, 1_000_000)
    # Spike the last 5 days
    base_volume[-5:] = int(1_000_000 * spike_factor)

    return pd.DataFrame(
        {
            COL_DATE: [d.date() for d in dates],
            COL_SYMBOL: symbol,
            COL_CLOSE: np.round(close, 2),
            COL_VOLUME: base_volume,
        }
    )


# ── compute_put_call_ratio ───────────────────────────────────────────────────


class TestComputePutCallRatio:
    """Tests for compute_put_call_ratio."""

    def test_put_call_ratio_cross_sectional(self) -> None:
        """Multiple symbols produce a Series indexed by symbol."""
        data = _make_options_data(
            symbols=["AAPL", "GOOG", "MSFT"],
            put_volumes=[50_000, 80_000, 30_000],
            call_volumes=[100_000, 40_000, 60_000],
        )
        series, diag = compute_put_call_ratio(data)

        assert isinstance(series, pd.Series)
        assert series.index.name == "symbol"
        assert len(series) == 3
        assert not diag.has_errors

        # AAPL: 50K/100K = 0.5, GOOG: 80K/40K = 2.0, MSFT: 30K/60K = 0.5
        assert series["AAPL"] == pytest.approx(0.5)
        assert series["GOOG"] == pytest.approx(2.0)
        assert series["MSFT"] == pytest.approx(0.5)

    def test_put_call_zero_calls_nan(self) -> None:
        """Zero call_volume produces NaN (avoid division by zero)."""
        data = _make_options_data(
            symbols=["ZERO_CALLS"],
            put_volumes=[50_000],
            call_volumes=[0],
        )
        series, diag = compute_put_call_ratio(data)

        assert np.isnan(series["ZERO_CALLS"])
        assert diag.has_warnings

    def test_put_call_missing_data_nan(self) -> None:
        """Missing put or call volume produces NaN."""
        data = pd.DataFrame(
            {
                COL_SYMBOL: ["MISSING"],
                COL_DATE: [pd.Timestamp("2024-12-15").date()],
                "put_volume": [np.nan],
                "call_volume": [100_000],
            }
        )
        series, diag = compute_put_call_ratio(data)

        assert np.isnan(series["MISSING"])


# ── compute_volume_momentum ──────────────────────────────────────────────────


class TestComputeVolumeMomentum:
    """Tests for compute_volume_momentum."""

    def test_volume_momentum_high_activity(self) -> None:
        """Stock with volume spike has volume momentum > 1."""
        data = _make_volume_spike_stock("SPIKE", n_days=30, spike_factor=3.0)
        series, diag = compute_volume_momentum(data)

        assert not diag.has_errors
        assert series["SPIKE"] > 1.0
        # 5-day avg = 3M, 20-day avg = (15*1M + 5*3M)/20 = 30M/20 = 1.5M
        # ratio = 3M/1.5M = 2.0
        assert series["SPIKE"] == pytest.approx(2.0)

    def test_volume_momentum_flat(self) -> None:
        """Stock with constant volume has momentum ~= 1.0."""
        np.random.default_rng(42)
        dates = pd.bdate_range(start="2022-01-03", periods=30, freq="B")
        data = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates],
                COL_SYMBOL: "FLAT",
                COL_CLOSE: 100.0,
                COL_VOLUME: 1_000_000,
            }
        )
        series, _ = compute_volume_momentum(data)

        assert series["FLAT"] == pytest.approx(1.0)

    def test_volume_momentum_insufficient_history(self) -> None:
        """Fewer than 20 days produces NaN."""
        dates = pd.bdate_range(start="2022-01-03", periods=10, freq="B")
        data = pd.DataFrame(
            {
                COL_DATE: [d.date() for d in dates],
                COL_SYMBOL: "SHORT",
                COL_CLOSE: 100.0,
                COL_VOLUME: 1_000_000,
            }
        )
        series, diag = compute_volume_momentum(data)

        assert np.isnan(series["SHORT"])
        assert diag.has_warnings

    def test_volume_momentum_cross_sectional(self) -> None:
        """Multiple symbols each get their own momentum value."""
        data = pd.concat(
            [
                _make_volume_spike_stock("SPIKE", n_days=30, spike_factor=3.0, seed=42),
                _make_volume_spike_stock("CALM", n_days=30, spike_factor=1.0, seed=99),
            ],
            ignore_index=True,
        )

        series, _ = compute_volume_momentum(data)

        assert len(series) == 2
        assert series["SPIKE"] > series["CALM"]


# ── compute_ewmac ────────────────────────────────────────────────────────────


class TestComputeEwmac:
    """Tests for compute_ewmac (Carver's trend-following rule)."""

    def test_ewmac_positive_trend(self) -> None:
        """Stock in strong uptrend has positive EWMAC."""
        data = _make_trending_stock("BULL", n_days=100, drift=0.50, seed=42)
        series, diag = compute_ewmac(data)

        assert not diag.has_errors
        assert series["BULL"] > 0, "Uptrending stock should have positive EWMAC"

    def test_ewmac_negative_trend(self) -> None:
        """Stock in strong downtrend has negative EWMAC."""
        data = _make_trending_stock("BEAR", n_days=100, drift=-0.50, seed=42)
        series, diag = compute_ewmac(data)

        assert not diag.has_errors
        assert series["BEAR"] < 0, "Downtrending stock should have negative EWMAC"

    def test_ewmac_insufficient_history_nan(self) -> None:
        """Fewer than slow_span (32) days produces NaN."""
        data = _make_trending_stock("YOUNG", n_days=20, drift=0.30, seed=42)
        series, diag = compute_ewmac(data)

        assert np.isnan(series["YOUNG"])
        assert diag.has_warnings

    def test_ewmac_cross_sectional(self) -> None:
        """Bull and bear stocks produce different EWMAC values."""
        data = pd.concat(
            [
                _make_trending_stock("BULL", n_days=100, drift=0.50, seed=42),
                _make_trending_stock("BEAR", n_days=100, drift=-0.50, seed=99),
            ],
            ignore_index=True,
        )

        series, diag = compute_ewmac(data)

        assert len(series) == 2
        assert series["BULL"] > series["BEAR"]
        assert not diag.has_errors

    def test_ewmac_custom_spans(self) -> None:
        """Custom fast/slow spans change the EWMAC result."""
        data = _make_trending_stock("TREND", n_days=100, drift=0.40, seed=42)

        series_default, _ = compute_ewmac(data, fast_span=8, slow_span=32)
        series_faster, _ = compute_ewmac(data, fast_span=4, slow_span=16)

        # Both should be positive for an uptrend
        assert series_default["TREND"] > 0
        assert series_faster["TREND"] > 0
        # Values should differ (faster pair reacts more quickly)
        assert series_default["TREND"] != series_faster["TREND"]

    def test_ewmac_returns_series_with_name(self) -> None:
        """Output series has correct name and index."""
        data = _make_trending_stock("SYM", n_days=50, drift=0.20, seed=42)
        series, _ = compute_ewmac(data)

        assert series.name == "ewmac"
        assert series.index.name == "symbol"
