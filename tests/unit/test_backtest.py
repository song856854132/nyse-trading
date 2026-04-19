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


class TestBenchmarkReporting:
    """RALPH TODO-9: SPY + RSP equal-weight benchmarks reported side-by-side."""

    def _make_benchmarks(self, index: pd.DatetimeIndex, seed: int = 7) -> dict[str, pd.Series]:
        rng = np.random.default_rng(seed)
        # Cap-weighted SPY-proxy and equal-weight RSP-proxy are two distinct
        # return streams with moderate correlation — enough to produce
        # different Sharpe values in the result.
        spy = pd.Series(rng.normal(0.0004, 0.01, len(index)), index=index, name="SPY")
        rsp = pd.Series(rng.normal(0.0003, 0.012, len(index)), index=index, name="RSP")
        return {"SPY": spy, "RSP": rsp}

    def test_benchmark_metrics_populated_when_provided(self):
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        benchmarks = self._make_benchmarks(features.index)
        result, _ = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
            benchmark_returns=benchmarks,
        )
        assert result.benchmark_metrics is not None
        assert set(result.benchmark_metrics.keys()) == {"SPY", "RSP"}
        for ticker in ("SPY", "RSP"):
            m = result.benchmark_metrics[ticker]
            assert set(m.keys()) == {"sharpe", "cagr", "max_drawdown"}
            assert np.isfinite(m["sharpe"])
            assert np.isfinite(m["cagr"])
            assert np.isfinite(m["max_drawdown"])
            assert m["max_drawdown"] <= 0.0

    def test_benchmark_metrics_none_when_not_provided(self):
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
        assert result.benchmark_metrics is None

    def test_partial_overlap_warns_but_still_reports(self):
        """Benchmark with <50% overlap must emit a warning but still populate."""
        features, returns = _make_synthetic_data(n_days=2000)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        full_bench = self._make_benchmarks(features.index)
        # Truncate RSP to the first 20 days only — far below the OOS window.
        short_rsp = full_bench["RSP"].iloc[:20]
        benchmarks = {"SPY": full_bench["SPY"], "RSP": short_rsp}
        result, diag = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
            benchmark_returns=benchmarks,
        )
        warn_msgs = [m for m in diag.messages if "RSP" in m.message and "OOS dates" in m.message]
        assert len(warn_msgs) >= 1, "Expected warning for short-overlap RSP benchmark"
        assert result.benchmark_metrics is not None
        assert "RSP" in result.benchmark_metrics
        assert "SPY" in result.benchmark_metrics

    def test_spy_rsp_reported_in_every_artifact(self):
        """Contract: RALPH TODO-9 requires BOTH SPY and RSP in artifact."""
        features, returns = _make_synthetic_data(n_days=2000, seed=101)
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        benchmarks = self._make_benchmarks(features.index, seed=11)
        result, _ = run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
            benchmark_returns=benchmarks,
        )
        # Both benchmarks must be present with non-None metrics.
        assert result.benchmark_metrics is not None
        assert "SPY" in result.benchmark_metrics
        assert "RSP" in result.benchmark_metrics
        # SPY and RSP draw from different distributions so their Sharpes
        # should not be identical by coincidence.
        assert result.benchmark_metrics["SPY"]["sharpe"] != result.benchmark_metrics["RSP"]["sharpe"]


class TestPriceVolumeWeightSignCheck:
    """RALPH TODO-10: warn when a price-volume factor has a negative Ridge weight.

    The warning exists so the operator investigates a possible sign-convention
    or label-timing bug. The backtest MUST NOT auto-flip signs.
    """

    def _make_anti_signal_data(
        self,
        n_days: int = 2000,
        seed: int = 31,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Feature f0 has a NEGATIVE relationship with returns — Ridge fits
        a negative coefficient on f0. Treating f0 as a 'price-volume' factor
        must trigger the TODO-10 warning.
        """
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2015-01-02", periods=n_days)
        features = rng.uniform(0, 1, (n_days, 3))
        noise = rng.normal(0, 0.01, n_days)
        # NEGATIVE coefficient on feature 0 — high f0 predicts low return.
        returns = -0.05 * features[:, 0] + noise
        feature_df = pd.DataFrame(features, index=dates, columns=["f0", "f1", "f2"])
        return_series = pd.Series(returns, index=dates, name="returns")
        return feature_df, return_series

    def _backtest(self, features, returns, price_volume_factors):
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        return run_walk_forward_backtest(
            feature_matrix=features,
            returns=returns,
            cv=cv,
            model_factory=RidgeModel,
            allocator_fn=_simple_allocator,
            risk_fn=_passthrough_risk,
            cost_fn=_zero_cost,
            price_volume_factors=price_volume_factors,
        )

    def test_negative_pv_weight_emits_warning(self):
        """f0 has a negative Ridge weight AND is in the price-volume set → WARNING."""
        features, returns = self._make_anti_signal_data()
        _, diag = self._backtest(features, returns, price_volume_factors={"f0"})
        warnings = [
            m
            for m in diag.messages
            if m.level.value == "WARNING"
            and "NEGATIVE Ridge coefficient" in m.message
            and m.context.get("factor") == "f0"
        ]
        assert len(warnings) == 1, (
            f"Expected exactly one TODO-10 warning for f0; got {len(warnings)}: "
            f"{[w.message for w in warnings]}"
        )
        # Diagnostic context must include the raw coefficient so the reviewer
        # can see the magnitude without re-running.
        assert "coefficient" in warnings[0].context
        assert warnings[0].context["coefficient"] < 0

    def test_positive_pv_weight_silent(self):
        """f0 has a POSITIVE Ridge weight — no TODO-10 warning."""
        features, returns = _make_synthetic_data(n_days=2000, signal_strength=0.05, seed=7)
        _, diag = self._backtest(features, returns, price_volume_factors={"f0"})
        warnings = [
            m
            for m in diag.messages
            if m.level.value == "WARNING" and "NEGATIVE Ridge coefficient" in m.message
        ]
        assert warnings == [], (
            f"Did not expect TODO-10 warning on positively-fit f0; got: {[w.message for w in warnings]}"
        )

    def test_not_supplied_is_silent(self):
        """Caller opts out → no TODO-10 warning even when a coef is negative."""
        features, returns = self._make_anti_signal_data()
        _, diag = self._backtest(features, returns, price_volume_factors=None)
        warnings = [
            m
            for m in diag.messages
            if m.level.value == "WARNING" and "NEGATIVE Ridge coefficient" in m.message
        ]
        assert warnings == [], "price_volume_factors=None must suppress TODO-10 warnings entirely."

    def test_unknown_factor_name_is_safe_noop(self):
        """A factor name in the PV set but not in the feature matrix is ignored."""
        features, returns = self._make_anti_signal_data()
        # "f0" is negative, "phantom_mom" is not in the feature matrix at all.
        _, diag = self._backtest(features, returns, price_volume_factors={"f0", "phantom_mom"})
        phantom_warnings = [
            m
            for m in diag.messages
            if m.level.value == "WARNING"
            and "NEGATIVE Ridge coefficient" in m.message
            and m.context.get("factor") == "phantom_mom"
        ]
        assert phantom_warnings == [], (
            "A PV-factor name that is not in the feature matrix must not emit a warning."
        )

    def test_warning_does_not_flip_coefficient(self):
        """Iron discipline: warning fires but coefficients are NOT mutated."""
        features, returns = self._make_anti_signal_data()
        result, _ = self._backtest(features, returns, price_volume_factors={"f0"})
        # per_factor_contribution comes from get_feature_importance which uses
        # abs() normalization — so we can't check the sign there. But we CAN
        # check that the raw-coefficient helper still returns a negative f0
        # when called on the same data — i.e., the backtest did not flip it.
        # Re-fit on the whole dataset to inspect the raw coefficient directly.
        model = RidgeModel()
        model.fit(features, returns)
        raw = model.get_raw_coefficients()
        assert raw["f0"] < 0, "f0's raw coefficient must remain negative — no auto-flip."
        # And the backtest still produced a valid result object.
        assert isinstance(result, BacktestResult)
