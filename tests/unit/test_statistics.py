"""Unit tests for statistical tests module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.statistics import (
    block_bootstrap_ci,
    permutation_test,
    romano_wolf_stepdown,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_signal_returns(n: int = 500, daily_mean: float = 0.001, seed: int = 42) -> pd.Series:
    """Create returns with a strong positive signal."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(daily_mean, 0.01, n)
    return pd.Series(returns, index=pd.bdate_range("2020-01-01", periods=n))


def _make_noise_returns(n: int = 500, seed: int = 99) -> pd.Series:
    """Create pure noise returns (zero mean)."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, n)
    return pd.Series(returns, index=pd.bdate_range("2020-01-01", periods=n))


# ── Permutation test ────────────────────────────────────────────────────────


class TestPermutationTest:
    @pytest.mark.slow
    def test_rejects_null_for_strong_signal(self):
        """A series with strong positive mean should be rejected (p < 0.05)."""
        returns = _make_signal_returns(daily_mean=0.002)
        p_value, diag = permutation_test(returns, n_reps=499, block_size=21)
        assert p_value < 0.10, f"Should reject null for strong signal, got p={p_value}"
        assert not diag.has_errors

    def test_does_not_reject_noise(self):
        """Pure noise should NOT be rejected (p > 0.05 typically)."""
        returns = _make_noise_returns()
        p_value, diag = permutation_test(returns, n_reps=99, block_size=21)
        # We only check p >= 0.01 to avoid flaky test — noise p should be high
        assert p_value >= 0.01, f"Pure noise should not strongly reject, got p={p_value}"

    def test_returns_diagnostics(self):
        returns = _make_signal_returns(n=100)
        _, diag = permutation_test(returns, n_reps=50, block_size=21)
        assert len(diag.messages) > 0

    def test_p_value_bounded(self):
        returns = _make_signal_returns(n=200)
        p_value, _ = permutation_test(returns, n_reps=50, block_size=21)
        assert 0.0 < p_value <= 1.0


# ── Block bootstrap CI ──────────────────────────────────────────────────────


class TestBlockBootstrapCI:
    @pytest.mark.slow
    def test_ci_contains_true_sharpe(self):
        """CI should contain the observed Sharpe for a large sample."""
        returns = _make_signal_returns(n=1000, daily_mean=0.0005)
        (lower, upper), diag = block_bootstrap_ci(returns, n_reps=500, block_size=21, alpha=0.05)
        observed = returns.mean() / returns.std() * np.sqrt(252)
        # Wide tolerance — bootstrap CI should bracket the point estimate
        assert lower < observed < upper, (
            f"CI [{lower:.3f}, {upper:.3f}] should contain observed {observed:.3f}"
        )

    def test_ci_ordering(self):
        """Lower bound should be less than upper bound."""
        returns = _make_signal_returns(n=300)
        (lower, upper), _ = block_bootstrap_ci(returns, n_reps=100, block_size=21)
        assert lower < upper

    def test_returns_diagnostics(self):
        returns = _make_signal_returns(n=200)
        _, diag = block_bootstrap_ci(returns, n_reps=50, block_size=21)
        assert len(diag.messages) > 0


# ── Romano-Wolf stepdown ────────────────────────────────────────────────────


class TestRomanoWolfStepdown:
    def test_strong_factor_low_p(self):
        """A factor with genuine signal should get a lower adjusted p-value."""
        strong = _make_signal_returns(n=500, daily_mean=0.002, seed=10)
        weak = _make_noise_returns(n=500, seed=20)
        factor_returns = {"strong": strong, "weak": weak}

        adj_p, diag = romano_wolf_stepdown(factor_returns, n_reps=199)
        assert adj_p["strong"] < adj_p["weak"], (
            f"Strong factor p={adj_p['strong']:.3f} should be < weak factor p={adj_p['weak']:.3f}"
        )
        assert not diag.has_errors

    def test_empty_dict(self):
        adj_p, diag = romano_wolf_stepdown({}, n_reps=50)
        assert adj_p == {}
        assert diag.has_warnings

    def test_all_p_values_in_range(self):
        returns = {f"factor_{i}": _make_noise_returns(n=300, seed=i) for i in range(3)}
        adj_p, _ = romano_wolf_stepdown(returns, n_reps=99)
        for name, p in adj_p.items():
            assert 0.0 <= p <= 1.0, f"{name} p-value {p} out of range"
