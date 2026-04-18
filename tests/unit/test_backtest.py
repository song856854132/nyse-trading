"""Unit tests for walk-forward backtest engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.backtest import run_walk_forward_backtest
from nyse_core.contracts import BacktestResult
from nyse_core.cv import PurgedWalkForwardCV
from nyse_core.models.ridge_model import RidgeModel

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_synthetic_data(
    n_days: int = 2000,
    n_features: int = 3,
    signal_strength: float = 0.01,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.Series]:
    """Create synthetic feature matrix and returns with a planted signal.

    The first feature has predictive power; the rest are noise.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-02", periods=n_days)

    features = rng.uniform(0, 1, (n_days, n_features))
    noise = rng.normal(0, 0.02, n_days)
    # Returns = signal_strength * feature_0 + noise
    returns = signal_strength * features[:, 0] + noise

    feature_df = pd.DataFrame(
        features,
        index=dates,
        columns=[f"f{i}" for i in range(n_features)],
    )
    return_series = pd.Series(returns, index=dates, name="returns")
    return feature_df, return_series


def _simple_allocator(predictions: np.ndarray) -> np.ndarray:
    """Convert predictions to equal-signed weights."""
    if predictions.sum() == 0:
        return predictions
    w = np.sign(predictions).astype(float)
    total = np.abs(w).sum()
    if total > 0:
        w = w / total
    return w


def _passthrough_risk(weights: np.ndarray) -> np.ndarray:
    """No risk adjustment."""
    return weights


def _zero_cost(weights_prev: np.ndarray, weights_new: np.ndarray) -> float:
    """Zero transaction costs."""
    return 0.0


def _small_cost(weights_prev: np.ndarray, weights_new: np.ndarray) -> float:
    """Small proportional transaction cost."""
    return float(np.abs(weights_new - weights_prev).sum()) * 0.001


# ── Tests ────────────────────────────────────────────────────────────────────


class TestWalkForwardBacktest:
    def test_produces_backtest_result(self):
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        result, diag = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
        )
        assert isinstance(result, BacktestResult)
        assert not diag.has_errors
        assert len(result.daily_returns) > 0

    def test_per_fold_sharpe_populated(self):
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        result, _ = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
        )
        assert len(result.per_fold_sharpe) >= 1
        for s in result.per_fold_sharpe:
            assert np.isfinite(s)

    def test_metrics_are_finite(self):
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        result, _ = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
        )
        assert np.isfinite(result.oos_sharpe)
        assert np.isfinite(result.oos_cagr)
        assert np.isfinite(result.max_drawdown)
        assert result.max_drawdown <= 0.0

    def test_with_transaction_costs(self):
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        result, _ = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_small_cost,
        )
        # With costs, Sharpe should be lower than or equal to zero-cost version
        assert np.isfinite(result.oos_sharpe)

    def test_planted_signal_detected(self):
        """With a strong signal, the backtest should produce positive OOS Sharpe."""
        features, returns = _make_synthetic_data(n_days=2000, signal_strength=0.03, seed=123)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=200,
            purge_days=5,
            embargo_days=5,
        )
        result, _ = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
        )
        # Strong signal should yield positive OOS performance
        assert result.oos_sharpe > 0, (
            f"Strong planted signal should give positive OOS Sharpe, got {result.oos_sharpe:.3f}"
        )

    def test_factor_contribution_from_ridge(self):
        """Ridge model should populate per_factor_contribution via coef_."""
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        result, _ = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
        )
        assert len(result.per_factor_contribution) > 0
        assert "f0" in result.per_factor_contribution

    def test_diagnostics_have_fold_info(self):
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        _, diag = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
        )
        fold_msgs = [m for m in diag.messages if "Fold" in m.message]
        assert len(fold_msgs) >= 1
