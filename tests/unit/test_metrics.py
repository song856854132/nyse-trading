"""Unit tests for performance metrics module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.metrics import (
    annual_turnover,
    cagr,
    cost_drag,
    ic_ir,
    information_coefficient,
    max_drawdown,
    sharpe_ratio,
)

# ── Sharpe ratio ─────────────────────────────────────────────────────────────


class TestSharpeRatio:
    def test_positive_returns(self):
        """Constant daily return => Sharpe = mean/std * sqrt(252), std=0 => 0."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.01, 1000))
        sr, diag = sharpe_ratio(returns)
        assert sr > 0, "Positive mean returns should give positive Sharpe"
        assert not diag.has_errors

    def test_zero_std_returns_zero(self):
        """Constant returns (zero variance) should return 0."""
        returns = pd.Series([0.001] * 100)
        sr, _ = sharpe_ratio(returns)
        assert sr == 0.0

    def test_known_value(self):
        """Hand-calculated Sharpe for known inputs."""
        returns = pd.Series([0.01, -0.01] * 126)
        sr, _ = sharpe_ratio(returns)
        # Mean is 0, so Sharpe should be ~0
        assert abs(sr) < 0.1

    def test_empty_returns_zero(self):
        sr, diag = sharpe_ratio(pd.Series(dtype=float))
        assert sr == 0.0
        assert diag.has_warnings

    def test_handles_nan(self):
        returns = pd.Series([0.01, np.nan, 0.02, 0.01])
        sr, _ = sharpe_ratio(returns)
        assert np.isfinite(sr)


# ── CAGR ─────────────────────────────────────────────────────────────────────


class TestCAGR:
    def test_positive_returns(self):
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.01, 504))
        c, diag = cagr(returns)
        assert c > 0, "Positive-mean returns should have positive CAGR"
        assert not diag.has_errors

    def test_known_flat_return(self):
        """252 days of 0.1% daily return => ~28.6% CAGR."""
        returns = pd.Series([0.001] * 252)
        c, _ = cagr(returns)
        expected = (1.001**252) ** (1.0) - 1.0  # 1 year
        assert abs(c - expected) < 0.001

    def test_empty_returns_zero(self):
        c, diag = cagr(pd.Series(dtype=float))
        assert c == 0.0
        assert diag.has_warnings


# ── Max drawdown ─────────────────────────────────────────────────────────────


class TestMaxDrawdown:
    def test_returns_negative(self):
        """Max drawdown should always be <= 0."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.0, 0.02, 500))
        mdd, _ = max_drawdown(returns)
        assert mdd <= 0.0

    def test_known_drawdown(self):
        """Engineer a 50% drawdown: go up 100% then down 50%."""
        returns = pd.Series([1.0, -0.5])
        mdd, _ = max_drawdown(returns)
        assert abs(mdd - (-0.5)) < 1e-10, f"Expected -0.50, got {mdd}"

    def test_monotonic_up_zero_dd(self):
        """Monotonically increasing equity has 0 drawdown."""
        returns = pd.Series([0.01] * 100)
        mdd, _ = max_drawdown(returns)
        assert mdd == 0.0

    def test_empty_returns_zero(self):
        mdd, diag = max_drawdown(pd.Series(dtype=float))
        assert mdd == 0.0
        assert diag.has_warnings


# ── Annual turnover ─────────────────────────────────────────────────────────


class TestAnnualTurnover:
    def test_no_turnover(self):
        """Static weights => zero turnover."""
        dates = pd.bdate_range("2020-01-01", periods=50)
        weights = pd.DataFrame({"A": [0.5] * 50, "B": [0.5] * 50}, index=dates)
        at, _ = annual_turnover(weights)
        assert at == pytest.approx(0.0, abs=1e-10)

    def test_full_turnover(self):
        """Alternating weights should produce high turnover."""
        dates = pd.bdate_range("2020-01-01", periods=100)
        w = np.tile([[1.0, 0.0], [0.0, 1.0]], (50, 1))
        weights = pd.DataFrame(w, index=dates, columns=["A", "B"])
        at, _ = annual_turnover(weights)
        # Each day flips 2.0 in absolute changes, avg = 2.0
        assert at > 100, f"Full turnover should be very high, got {at}"

    def test_single_row_zero(self):
        weights = pd.DataFrame({"A": [0.5]}, index=[pd.Timestamp("2020-01-01")])
        at, _ = annual_turnover(weights)
        assert at == 0.0


# ── Information coefficient ──────────────────────────────────────────────────


class TestInformationCoefficient:
    def test_perfect_positive(self):
        """Monotonically increasing scores & returns => IC = 1.0."""
        scores = pd.Series([1, 2, 3, 4, 5], dtype=float)
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
        ic, _ = information_coefficient(scores, returns)
        assert ic == pytest.approx(1.0, abs=1e-10)

    def test_perfect_negative(self):
        scores = pd.Series([5, 4, 3, 2, 1], dtype=float)
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
        ic, _ = information_coefficient(scores, returns)
        assert ic == pytest.approx(-1.0, abs=1e-10)

    def test_handles_nan(self):
        scores = pd.Series([1, np.nan, 3, 4, 5], dtype=float)
        returns = pd.Series([0.01, 0.02, np.nan, 0.04, 0.05])
        ic, _ = information_coefficient(scores, returns)
        assert np.isfinite(ic)

    def test_too_few_returns_zero(self):
        scores = pd.Series([1.0, 2.0])
        returns = pd.Series([np.nan, np.nan])
        ic, diag = information_coefficient(scores, returns)
        assert ic == 0.0
        assert diag.has_warnings

    def test_with_ties(self):
        """Spearman should handle ties gracefully."""
        scores = pd.Series([1, 1, 2, 3, 3], dtype=float)
        returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
        ic, _ = information_coefficient(scores, returns)
        assert -1.0 <= ic <= 1.0


# ── IC IR ────────────────────────────────────────────────────────────────────


class TestICIR:
    def test_positive_ic_ir(self):
        ic_series = pd.Series([0.05, 0.04, 0.06, 0.05, 0.03])
        result, _ = ic_ir(ic_series)
        assert result > 0

    def test_zero_std(self):
        ic_series = pd.Series([0.05] * 10)
        result, _ = ic_ir(ic_series)
        assert result == 0.0

    def test_known_value(self):
        s = pd.Series([0.1, 0.2, 0.3])
        expected = s.mean() / s.std(ddof=1)
        result, _ = ic_ir(s)
        assert result == pytest.approx(expected, rel=1e-10)


# ── Cost drag ────────────────────────────────────────────────────────────────


class TestCostDrag:
    def test_zero_costs(self):
        returns = pd.Series([0.001] * 252)
        costs = pd.Series([0.0] * 252)
        cd, _ = cost_drag(returns, costs)
        assert cd == pytest.approx(0.0, abs=1e-10)

    def test_positive_costs(self):
        returns = pd.Series([0.001] * 252)
        costs = pd.Series([0.0001] * 252)
        cd, _ = cost_drag(returns, costs)
        # 0.0001 * 252 = 0.0252
        assert cd == pytest.approx(0.0252, rel=1e-3)
