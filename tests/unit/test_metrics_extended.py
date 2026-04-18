"""Extended unit tests for performance metrics module.

Tests edge cases and specific behaviors not covered by the base test_metrics.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.metrics import (
    cagr,
    cost_drag,
    ic_ir,
    information_coefficient,
    max_drawdown,
    sharpe_ratio,
)
from nyse_core.schema import TRADING_DAYS_PER_YEAR

# ── IC with perfect signal ──────────────────────────────────────────────────


class TestICWithPerfectSignal:
    """IC of identical series should be approximately 1.0."""

    def test_ic_with_perfect_signal(self) -> None:
        """Identical factor scores and forward returns -> IC ~= 1.0."""
        n = 50
        values = np.arange(1, n + 1, dtype=float)
        scores = pd.Series(values)
        returns = pd.Series(values * 0.01)  # Monotonic increasing

        ic, _ = information_coefficient(scores, returns)
        assert ic == pytest.approx(1.0, abs=1e-10), (
            f"IC of identical monotonic series should be ~1.0, got {ic}"
        )


# ── IC with inverse signal ──────────────────────────────────────────────────


class TestICWithInverseSignal:
    """IC of inverted series should be approximately -1.0."""

    def test_ic_with_inverse_signal(self) -> None:
        """Factor scores inversely related to returns -> IC ~= -1.0."""
        n = 50
        scores = pd.Series(np.arange(n, 0, -1, dtype=float))
        returns = pd.Series(np.arange(1, n + 1, dtype=float) * 0.01)

        ic, _ = information_coefficient(scores, returns)
        assert ic == pytest.approx(-1.0, abs=1e-10), (
            f"IC of inverse monotonic series should be ~-1.0, got {ic}"
        )


# ── IC with random noise ────────────────────────────────────────────────────


class TestICWithRandomNoise:
    """IC of unrelated random series should be near 0."""

    def test_ic_with_random_noise(self) -> None:
        """Uncorrelated random series should give IC near 0."""
        rng = np.random.default_rng(42)
        n = 500

        scores = pd.Series(rng.normal(0, 1, n))
        returns = pd.Series(rng.normal(0, 0.01, n))

        ic, _ = information_coefficient(scores, returns)
        assert abs(ic) < 0.15, f"IC of random noise should be near 0, got {ic}"


# ── IC IR with stable signal ────────────────────────────────────────────────


class TestICIRStableSignal:
    """Consistent IC series (low volatility) -> high IC_IR."""

    def test_ic_ir_stable_signal(self) -> None:
        """A consistently positive IC series should have high IC_IR."""
        # Stable around 0.05 with very low noise
        rng = np.random.default_rng(42)
        ic_series = pd.Series(rng.normal(0.05, 0.005, 50))

        result, _ = ic_ir(ic_series)
        assert result > 3.0, f"Stable IC series should have high IC_IR, got {result}"


# ── IC IR with noisy signal ─────────────────────────────────────────────────


class TestICIRNoisySignal:
    """Volatile IC series -> low IC_IR."""

    def test_ic_ir_noisy_signal(self) -> None:
        """A volatile IC series should have low IC_IR."""
        rng = np.random.default_rng(42)
        # High variance IC: mean ~ 0.02, std ~ 0.10
        ic_series = pd.Series(rng.normal(0.02, 0.10, 50))

        result, _ = ic_ir(ic_series)
        assert result < 1.0, f"Noisy IC series should have low IC_IR, got {result}"


# ── Sharpe with zero volatility ─────────────────────────────────────────────


class TestSharpeWithZeroVol:
    """Returns with zero variance -> Sharpe = 0.0."""

    def test_sharpe_with_zero_vol(self) -> None:
        """Constant returns (zero std) should return Sharpe = 0.0."""
        returns = pd.Series([0.001] * 252)
        result, _ = sharpe_ratio(returns)
        assert result == 0.0, f"Sharpe with zero vol should be 0.0, got {result}"


# ── CAGR with flat returns ──────────────────────────────────────────────────


class TestCAGRWithFlatReturns:
    """Zero returns throughout -> CAGR = 0.0."""

    def test_cagr_with_flat_returns(self) -> None:
        """All-zero daily returns should give CAGR = 0.0."""
        returns = pd.Series([0.0] * 252)
        result, _ = cagr(returns)
        assert result == pytest.approx(0.0, abs=1e-10), f"CAGR with zero returns should be 0.0, got {result}"


# ── Max drawdown with monotonic up ──────────────────────────────────────────


class TestMaxDrawdownMonotonicUp:
    """Monotonically increasing equity -> drawdown = 0.0."""

    def test_max_drawdown_with_monotonic_up(self) -> None:
        """All positive daily returns (never draws down) -> 0.0."""
        returns = pd.Series([0.01] * 100)
        result, _ = max_drawdown(returns)
        assert result == 0.0, f"Max drawdown with monotonic up should be 0.0, got {result}"


# ── Cost drag computation ───────────────────────────────────────────────────


class TestCostDragComputation:
    """Verify annual scaling in cost_drag computation."""

    def test_cost_drag_computation(self) -> None:
        """daily_cost_rate * 252 should equal annual cost drag."""
        n_days = 252
        returns = pd.Series([0.001] * n_days)
        daily_cost = 0.0001  # 1 bps per day
        costs = pd.Series([daily_cost] * n_days)

        result, _ = cost_drag(returns, costs)
        expected = daily_cost * TRADING_DAYS_PER_YEAR  # 0.0001 * 252 = 0.0252
        assert result == pytest.approx(expected, rel=1e-6), f"Cost drag should be {expected}, got {result}"

    def test_cost_drag_zero_costs(self) -> None:
        """Zero costs -> zero drag."""
        returns = pd.Series([0.001] * 100)
        costs = pd.Series([0.0] * 100)
        result, _ = cost_drag(returns, costs)
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_cost_drag_scaling(self) -> None:
        """Doubling daily costs should double annual drag."""
        n_days = 252
        returns = pd.Series([0.001] * n_days)

        costs_1x = pd.Series([0.0001] * n_days)
        costs_2x = pd.Series([0.0002] * n_days)

        drag_1x, _ = cost_drag(returns, costs_1x)
        drag_2x, _ = cost_drag(returns, costs_2x)

        assert drag_2x == pytest.approx(2 * drag_1x, rel=1e-6), (
            f"2x costs should give 2x drag: {drag_2x} vs 2*{drag_1x}"
        )
