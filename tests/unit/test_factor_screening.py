"""Unit tests for the factor screening pipeline (G0-G5)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import GateVerdict
from nyse_core.factor_screening import compute_long_short_returns, screen_factor

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_factor_data(
    n_dates: int = 60,
    n_stocks: int = 100,
    signal_strength: float = 0.0,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate synthetic factor scores and forward returns.

    Parameters
    ----------
    n_dates : int
        Number of rebalance dates.
    n_stocks : int
        Stocks per date.
    signal_strength : float
        0.0 = pure noise, >0 = score explains some return variance.
    seed : int
        RNG seed for determinism.

    Returns
    -------
    (factor_scores, forward_returns) DataFrames.
    """
    rng = np.random.default_rng(seed)
    dates = pd.biz_day_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        noise = rng.standard_normal(n_stocks) * 0.02
        returns = signal_strength * scores * 0.02 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


def _make_strong_signal(
    n_dates: int = 80,
    n_stocks: int = 100,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate a factor with strong monotonic signal."""
    rng = np.random.default_rng(seed)
    dates = pd.biz_day_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        # Strong signal: returns strongly correlated with scores
        noise = rng.standard_normal(n_stocks) * 0.005
        returns = 0.5 * scores * 0.03 + 0.003 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


# Helper to generate business day ranges (pd doesn't expose biz_day_range)
def _biz_days(start: str, n: int) -> list:
    """Generate n business-day-spaced timestamps."""
    return pd.bdate_range(start, periods=n, freq="B").tolist()


# Patch the helper above into _make_factor_data and _make_strong_signal
def _make_factor_data_v2(
    n_dates: int = 60,
    n_stocks: int = 100,
    signal_strength: float = 0.0,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        noise = rng.standard_normal(n_stocks) * 0.02
        returns = signal_strength * scores * 0.02 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


def _make_strong_signal_v2(
    n_dates: int = 80,
    n_stocks: int = 100,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates, freq="5B")
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records_scores = []
    records_rets = []

    for dt in dates:
        scores = rng.standard_normal(n_stocks)
        noise = rng.standard_normal(n_stocks) * 0.005
        returns = 0.5 * scores * 0.03 + 0.003 + noise

        for i, sym in enumerate(symbols):
            records_scores.append({"date": dt, "symbol": sym, "score": scores[i]})
            records_rets.append({"date": dt, "symbol": sym, "fwd_ret_5d": returns[i]})

    return pd.DataFrame(records_scores), pd.DataFrame(records_rets)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestScreenFactorAllGatesPass:
    """Strong synthetic signal should pass all G0-G5 gates."""

    def test_screen_factor_all_gates_pass(self):
        factor_scores, forward_returns = _make_strong_signal_v2(n_dates=80, n_stocks=100, seed=42)
        verdict, metrics, diag = screen_factor(
            factor_name="strong_momentum",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
            existing_factors=None,
        )
        assert isinstance(verdict, GateVerdict)
        assert verdict.passed_all is True, (
            f"Expected all gates to pass. Results: {verdict.gate_results}, Metrics: {metrics}"
        )
        assert not diag.has_errors


class TestScreenFactorWeakSignalFails:
    """Random noise should fail at least one gate (likely G1 permutation)."""

    def test_screen_factor_weak_signal_fails(self):
        factor_scores, forward_returns = _make_factor_data_v2(
            n_dates=60, n_stocks=100, signal_strength=0.0, seed=42
        )
        verdict, metrics, diag = screen_factor(
            factor_name="noise_factor",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
            existing_factors=None,
        )
        assert isinstance(verdict, GateVerdict)
        # A pure noise factor should fail at least one gate
        assert verdict.passed_all is False, (
            f"Pure noise should fail. Results: {verdict.gate_results}, Metrics: {metrics}"
        )


class TestLongShortReturns:
    """Tests for the compute_long_short_returns helper."""

    def test_long_short_returns_shape(self):
        factor_scores, forward_returns = _make_factor_data_v2(
            n_dates=20, n_stocks=50, signal_strength=0.1, seed=42
        )
        ls_ret, diag = compute_long_short_returns(factor_scores, forward_returns)
        assert isinstance(ls_ret, pd.Series)
        # Should have at most n_dates entries
        assert len(ls_ret) <= 20
        assert len(ls_ret) > 0
        assert not diag.has_errors

    def test_long_short_top_quintile_positive(self):
        """With a planted monotonic signal, long-short returns should be positive on average."""
        factor_scores, forward_returns = _make_strong_signal_v2(n_dates=60, n_stocks=100, seed=42)
        ls_ret, diag = compute_long_short_returns(factor_scores, forward_returns)
        assert ls_ret.mean() > 0, (
            f"Expected positive mean LS return with strong signal, got {ls_ret.mean():.6f}"
        )


class TestMissingMetricFailsGate:
    """If a required metric cannot be computed, the gate should fail."""

    def test_missing_metric_fails_gate(self):
        # Provide empty data so metrics degenerate
        factor_scores = pd.DataFrame(columns=["date", "symbol", "score"])
        forward_returns = pd.DataFrame(columns=["date", "symbol", "fwd_ret_5d"])

        verdict, metrics, diag = screen_factor(
            factor_name="empty_factor",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
        )
        # With no data, OOS Sharpe = 0 (< 0.3 threshold) -> G0 fail
        assert verdict.passed_all is False


class TestG5MarginalAutoPassNoExisting:
    """G5 should auto-pass when no existing factors are provided."""

    def test_g5_marginal_auto_pass_no_existing(self):
        factor_scores, forward_returns = _make_strong_signal_v2(n_dates=80, n_stocks=100, seed=42)
        verdict, metrics, diag = screen_factor(
            factor_name="test_factor",
            factor_scores=factor_scores,
            forward_returns=forward_returns,
            existing_factors=None,  # No existing factors -> G5 auto-pass
        )
        # G5 should pass (auto-pass with sentinel = 1.0 > 0)
        assert verdict.gate_results.get("G5") is True, (
            f"G5 should auto-pass with no existing factors. "
            f"Results: {verdict.gate_results}, Metrics: {metrics}"
        )
