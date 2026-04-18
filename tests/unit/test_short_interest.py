"""Unit tests for short interest factors (cross-sectional).

Tests verify:
  - Cross-sectional output: one value per symbol
  - Correct ranking of heavily shorted vs lightly shorted stocks
  - Value ranges
  - Missing / zero data -> NaN
  - Change detection
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.features.short_interest import (
    compute_short_interest_change,
    compute_short_interest_pct,
    compute_short_ratio,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_short_data(
    symbols: list[str],
    short_interests: list[int],
    shares_outstanding: list[int],
    avg_daily_volumes: list[int],
) -> pd.DataFrame:
    """Build a single-period short interest DataFrame."""
    return pd.DataFrame(
        {
            "symbol": symbols,
            "date": pd.Timestamp("2024-12-15").date(),
            "short_interest": short_interests,
            "shares_outstanding": shares_outstanding,
            "avg_daily_volume": avg_daily_volumes,
        }
    )


def _make_multi_period_data(
    symbol: str,
    short_interests: list[int],
    dates: list,
) -> pd.DataFrame:
    """Build a multi-period short interest DataFrame for one symbol."""
    n = len(short_interests)
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "date": dates,
            "short_interest": short_interests,
            "shares_outstanding": [100_000_000] * n,
            "avg_daily_volume": [2_000_000] * n,
        }
    )


# ── compute_short_ratio ─────────────────────────────────────────────────────


class TestComputeShortRatio:
    """Tests for compute_short_ratio."""

    def test_short_ratio_cross_sectional(self) -> None:
        """Multiple symbols produce a Series indexed by symbol."""
        data = _make_short_data(
            symbols=["AAPL", "GOOG", "MSFT"],
            short_interests=[5_000_000, 3_000_000, 8_000_000],
            shares_outstanding=[1_000_000_000, 500_000_000, 800_000_000],
            avg_daily_volumes=[10_000_000, 5_000_000, 15_000_000],
        )
        series, diag = compute_short_ratio(data)

        assert isinstance(series, pd.Series)
        assert series.index.name == "symbol"
        assert len(series) == 3
        assert set(series.index) == {"AAPL", "GOOG", "MSFT"}
        assert not diag.has_errors

    def test_short_ratio_high_for_heavily_shorted(self) -> None:
        """Stock with more short interest relative to volume has higher ratio."""
        data = _make_short_data(
            symbols=["HEAVY", "LIGHT"],
            short_interests=[20_000_000, 1_000_000],
            shares_outstanding=[200_000_000, 200_000_000],
            avg_daily_volumes=[2_000_000, 2_000_000],
        )
        series, _ = compute_short_ratio(data)

        # HEAVY: 20M/2M = 10 days to cover
        # LIGHT: 1M/2M = 0.5 days to cover
        assert series["HEAVY"] > series["LIGHT"]
        assert series["HEAVY"] == pytest.approx(10.0)
        assert series["LIGHT"] == pytest.approx(0.5)

    def test_zero_volume_returns_nan(self) -> None:
        """Zero avg_daily_volume produces NaN (avoids division by zero)."""
        data = _make_short_data(
            symbols=["ZERO_VOL"],
            short_interests=[5_000_000],
            shares_outstanding=[100_000_000],
            avg_daily_volumes=[0],
        )
        series, diag = compute_short_ratio(data)

        assert np.isnan(series["ZERO_VOL"])
        assert diag.has_warnings

    def test_missing_data_returns_nan(self) -> None:
        """Missing short_interest produces NaN."""
        data = pd.DataFrame(
            {
                "symbol": ["MISSING"],
                "date": [pd.Timestamp("2024-12-15").date()],
                "short_interest": [np.nan],
                "shares_outstanding": [100_000_000],
                "avg_daily_volume": [2_000_000],
            }
        )
        series, diag = compute_short_ratio(data)

        assert np.isnan(series["MISSING"])
        assert diag.has_warnings

    def test_takes_most_recent_observation(self) -> None:
        """With multiple dates, uses the most recent row per symbol."""
        # Dates < 11 days apart so FINRA publication lag filter does NOT activate.
        data = pd.DataFrame(
            {
                "symbol": ["SYM", "SYM"],
                "date": [
                    pd.Timestamp("2024-12-10").date(),
                    pd.Timestamp("2024-12-15").date(),
                ],
                "short_interest": [1_000_000, 5_000_000],
                "shares_outstanding": [100_000_000, 100_000_000],
                "avg_daily_volume": [1_000_000, 1_000_000],
            }
        )
        series, _ = compute_short_ratio(data)

        # Most recent (Dec 15): 5M/1M = 5.0
        assert series["SYM"] == pytest.approx(5.0)


# ── compute_short_interest_pct ───────────────────────────────────────────────


class TestComputeShortInterestPct:
    """Tests for compute_short_interest_pct."""

    def test_short_interest_pct_range(self) -> None:
        """Values should be between 0 and 1 for realistic data."""
        rng = np.random.default_rng(42)
        symbols = [f"SYM_{i}" for i in range(20)]
        shares = [int(rng.uniform(50e6, 5e9)) for _ in symbols]
        si = [int(s * rng.uniform(0.01, 0.15)) for s in shares]
        adv = [int(s * 0.01) for s in shares]

        data = _make_short_data(symbols, si, shares, adv)
        series, diag = compute_short_interest_pct(data)

        assert not diag.has_errors
        valid = series.dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_cross_sectional_indexed_by_symbol(self) -> None:
        """Output is indexed by symbol with correct length."""
        data = _make_short_data(
            symbols=["A", "B", "C"],
            short_interests=[1_000_000, 2_000_000, 3_000_000],
            shares_outstanding=[100_000_000, 100_000_000, 100_000_000],
            avg_daily_volumes=[1_000_000, 1_000_000, 1_000_000],
        )
        series, _ = compute_short_interest_pct(data)

        assert series.index.name == "symbol"
        assert len(series) == 3
        # A: 1M/100M = 0.01, B: 2M/100M = 0.02, C: 3M/100M = 0.03
        assert series["A"] == pytest.approx(0.01)
        assert series["C"] == pytest.approx(0.03)


# ── compute_short_interest_change ────────────────────────────────────────────


class TestComputeShortInterestChange:
    """Tests for compute_short_interest_change."""

    def test_short_interest_change_detects_increase(self) -> None:
        """Increasing short interest yields a positive change value."""
        # Dates < 11 days apart so FINRA publication lag filter does NOT activate.
        data = _make_multi_period_data(
            symbol="RISING",
            short_interests=[5_000_000, 7_000_000],
            dates=[
                pd.Timestamp("2024-12-01").date(),
                pd.Timestamp("2024-12-05").date(),
            ],
        )
        series, diag = compute_short_interest_change(data)

        # (7M - 5M) / 5M = 0.4
        assert series["RISING"] == pytest.approx(0.4)
        assert not diag.has_errors

    def test_short_interest_change_detects_decrease(self) -> None:
        """Decreasing short interest yields a negative change value."""
        # Dates < 11 days apart so FINRA publication lag filter does NOT activate.
        data = _make_multi_period_data(
            symbol="FALLING",
            short_interests=[10_000_000, 6_000_000],
            dates=[
                pd.Timestamp("2024-12-01").date(),
                pd.Timestamp("2024-12-05").date(),
            ],
        )
        series, _ = compute_short_interest_change(data)

        # (6M - 10M) / 10M = -0.4
        assert series["FALLING"] == pytest.approx(-0.4)

    def test_insufficient_data_returns_nan(self) -> None:
        """Single period (< 2 required) produces NaN."""
        data = _make_short_data(
            symbols=["SINGLE"],
            short_interests=[5_000_000],
            shares_outstanding=[100_000_000],
            avg_daily_volumes=[2_000_000],
        )
        series, diag = compute_short_interest_change(data)

        assert np.isnan(series["SINGLE"])
        assert diag.has_warnings

    def test_missing_data_returns_nan(self) -> None:
        """NaN in short_interest produces NaN for change."""
        data = pd.DataFrame(
            {
                "symbol": ["BAD", "BAD"],
                "date": [
                    pd.Timestamp("2024-11-15").date(),
                    pd.Timestamp("2024-12-15").date(),
                ],
                "short_interest": [5_000_000, np.nan],
                "shares_outstanding": [100_000_000, 100_000_000],
                "avg_daily_volume": [2_000_000, 2_000_000],
            }
        )
        series, diag = compute_short_interest_change(data)

        assert np.isnan(series["BAD"])

    def test_cross_sectional_multiple_symbols(self) -> None:
        """Multiple symbols each get their own change value."""
        # Dates < 11 days apart so FINRA publication lag filter does NOT activate.
        data = pd.concat(
            [
                _make_multi_period_data(
                    "UP",
                    [5_000_000, 10_000_000],
                    [pd.Timestamp("2024-12-01").date(), pd.Timestamp("2024-12-05").date()],
                ),
                _make_multi_period_data(
                    "DOWN",
                    [10_000_000, 5_000_000],
                    [pd.Timestamp("2024-12-01").date(), pd.Timestamp("2024-12-05").date()],
                ),
            ],
            ignore_index=True,
        )

        series, _ = compute_short_interest_change(data)

        assert len(series) == 2
        assert series["UP"] == pytest.approx(1.0)  # doubled
        assert series["DOWN"] == pytest.approx(-0.5)  # halved


# ── FINRA Publication Lag Filter ───────────────────────────────────────────


class TestFinraPublicationLag:
    """Tests for the FINRA ~11-day publication lag PiT enforcement."""

    def test_lag_filter_activates_for_wide_date_span(self) -> None:
        """When date span >= 11 days, recent observations are excluded."""
        # 3 periods spanning 30 days — filter activates, Dec 15 excluded.
        data = pd.DataFrame(
            {
                "symbol": ["SYM"] * 3,
                "date": [
                    pd.Timestamp("2024-11-15").date(),
                    pd.Timestamp("2024-12-01").date(),
                    pd.Timestamp("2024-12-15").date(),
                ],
                "short_interest": [1_000_000, 3_000_000, 99_000_000],
                "shares_outstanding": [100_000_000] * 3,
                "avg_daily_volume": [1_000_000] * 3,
            }
        )
        series, _ = compute_short_ratio(data)

        # cutoff = Dec 15 - 11d = Dec 4. Only Nov 15 and Dec 1 pass.
        # Most recent passing: Dec 1 → 3M/1M = 3.0 (NOT 99.0 from Dec 15)
        assert series["SYM"] == pytest.approx(3.0)

    def test_lag_filter_does_not_activate_for_narrow_span(self) -> None:
        """When date span < 11 days, all observations are kept."""
        data = pd.DataFrame(
            {
                "symbol": ["SYM"] * 2,
                "date": [
                    pd.Timestamp("2024-12-10").date(),
                    pd.Timestamp("2024-12-15").date(),
                ],
                "short_interest": [1_000_000, 5_000_000],
                "shares_outstanding": [100_000_000] * 2,
                "avg_daily_volume": [1_000_000] * 2,
            }
        )
        series, _ = compute_short_ratio(data)

        # 5-day span < 11 → no filter. Most recent = Dec 15: 5M/1M = 5.0
        assert series["SYM"] == pytest.approx(5.0)

    def test_lag_filter_change_needs_two_surviving_periods(self) -> None:
        """Change computation requires >= 2 periods AFTER the lag filter."""
        # 3 periods: Nov 1, Nov 20, Dec 15 (span=44 days). Cutoff = Dec 4.
        # Nov 1 and Nov 20 survive; Dec 15 excluded. 2 periods → change computed.
        data = pd.DataFrame(
            {
                "symbol": ["SYM"] * 3,
                "date": [
                    pd.Timestamp("2024-11-01").date(),
                    pd.Timestamp("2024-11-20").date(),
                    pd.Timestamp("2024-12-15").date(),
                ],
                "short_interest": [5_000_000, 7_000_000, 99_000_000],
                "shares_outstanding": [100_000_000] * 3,
                "avg_daily_volume": [2_000_000] * 3,
            }
        )
        series, diag = compute_short_interest_change(data)

        # (7M - 5M) / 5M = 0.4 (using Nov 1 and Nov 20, Dec 15 excluded)
        assert series["SYM"] == pytest.approx(0.4)
        assert not diag.has_errors
