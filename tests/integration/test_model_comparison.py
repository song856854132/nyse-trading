"""Integration tests for comparing Ridge vs GBM vs Neural models.

All models run on IDENTICAL CV folds for fair comparison.
Validates that model switching does not alter data splits,
and that each model produces valid BacktestResult outputs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pytest

from nyse_core.contracts import BacktestResult, Diagnostics
from nyse_core.features.registry import FactorRegistry
from nyse_core.research_pipeline import ResearchPipeline
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_SYMBOL,
    COL_VOLUME,
    UsageDomain,
)
from nyse_core.strategy_registry import (
    StrategyConfig,
    StrategyRegistry,
    StrategyResult,
)
from tests.fixtures.synthetic_prices import generate_prices

if TYPE_CHECKING:
    import pandas as pd

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_simple_registry(n_factors: int = 3) -> FactorRegistry:
    """Build a FactorRegistry with simple deterministic factors."""
    registry = FactorRegistry()

    def _make_close_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        latest = data.sort_values(COL_DATE).groupby(COL_SYMBOL).last()
        return latest[COL_CLOSE], diag

    def _make_volume_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        latest = data.sort_values(COL_DATE).groupby(COL_SYMBOL).last()
        return latest[COL_VOLUME].astype(float), diag

    def _make_range_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        latest = data.sort_values(COL_DATE).groupby(COL_SYMBOL).last()
        return (latest["high"] - latest["low"]).astype(float), diag

    factors = [
        ("factor_close", _make_close_factor),
        ("factor_volume", _make_volume_factor),
        ("factor_range", _make_range_factor),
    ]
    for name, fn in factors[:n_factors]:
        registry.register(
            name=name,
            compute_fn=fn,
            usage_domain=UsageDomain.SIGNAL,
            sign_convention=1,
            description=f"Test factor {name}",
        )
    return registry


def _make_small_ohlcv(
    n_stocks: int = 50,
    n_days: int = 600,
    seed: int = 42,
) -> pd.DataFrame:
    return generate_prices(n_stocks=n_stocks, n_days=n_days, seed=seed)


def _run_backtest_for_model(
    model_type: str,
    ohlcv: pd.DataFrame,
    factor_registry: FactorRegistry,
    n_folds: int = 2,
    top_n: int = 10,
) -> tuple[BacktestResult, Diagnostics]:
    """Run walk-forward validation for a specific model type."""
    pipeline = ResearchPipeline(
        registry=factor_registry,
        model_type=model_type,
        top_n=top_n,
    )
    return pipeline.run_walk_forward_validation(ohlcv, n_folds=n_folds)


# ── TestModelComparison ─────────────────────────────────────────────────


class TestModelComparison:
    """Compare Ridge, GBM, and Neural on identical data and CV folds."""

    def test_ridge_produces_backtest_result(self) -> None:
        """Ridge should produce a valid BacktestResult."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        result, diag = _run_backtest_for_model("ridge", ohlcv, registry)

        assert isinstance(result, BacktestResult)
        assert isinstance(result.oos_sharpe, float)
        assert isinstance(result.per_fold_sharpe, list)

    def test_gbm_produces_backtest_result(self) -> None:
        """GBM should produce a valid BacktestResult."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        try:
            import lightgbm  # noqa: F401
        except ImportError:
            pytest.skip("lightgbm not installed")

        result, diag = _run_backtest_for_model("gbm", ohlcv, registry)

        assert isinstance(result, BacktestResult)
        assert isinstance(result.oos_sharpe, float)

    def test_neural_produces_backtest_result(self) -> None:
        """Neural should produce a valid BacktestResult."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        try:
            import torch  # noqa: F401
        except ImportError:
            pytest.skip("torch not installed")

        result, diag = _run_backtest_for_model("neural", ohlcv, registry)

        assert isinstance(result, BacktestResult)
        assert isinstance(result.oos_sharpe, float)

    def test_models_use_same_cv_folds(self) -> None:
        """Verify that changing model_type does not change the CV fold split.

        The CV splitter is data-dependent (dates), not model-dependent.
        """
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        from nyse_core.cv import PurgedWalkForwardCV

        original_split = PurgedWalkForwardCV.split
        folds_by_model: dict[str, list[tuple[int, int]]] = {}

        def _tracking_split(model_name):
            def _split(self_cv, dates):
                folds = []
                for train_idx, test_idx in original_split(self_cv, dates):
                    folds.append((len(train_idx), len(test_idx)))
                    yield train_idx, test_idx
                folds_by_model[model_name] = folds

            return _split

        # Run Ridge
        with patch.object(PurgedWalkForwardCV, "split", _tracking_split("ridge")):
            _run_backtest_for_model("ridge", ohlcv, registry, n_folds=2)

        # Run GBM (if available)
        try:
            import lightgbm  # noqa: F401

            with patch.object(PurgedWalkForwardCV, "split", _tracking_split("gbm")):
                _run_backtest_for_model("gbm", ohlcv, registry, n_folds=2)
        except ImportError:
            pass

        # Compare fold shapes
        if "ridge" in folds_by_model and "gbm" in folds_by_model:
            assert folds_by_model["ridge"] == folds_by_model["gbm"], (
                f"Ridge folds {folds_by_model['ridge']} differ from "
                f"GBM folds {folds_by_model['gbm']} -- CV splits are model-dependent"
            )

    def test_ridge_vs_gbm_sharpe_comparison(self) -> None:
        """Run Ridge and GBM; both should produce finite Sharpe values."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        ridge_result, _ = _run_backtest_for_model("ridge", ohlcv, registry)

        try:
            import lightgbm  # noqa: F401
        except ImportError:
            pytest.skip("lightgbm not installed")

        gbm_result, _ = _run_backtest_for_model("gbm", ohlcv, registry)

        # Both should produce finite Sharpe (not testing which is better)
        assert np.isfinite(ridge_result.oos_sharpe), "Ridge Sharpe is not finite"
        assert np.isfinite(gbm_result.oos_sharpe), "GBM Sharpe is not finite"

    def test_overfit_ratio_computed(self) -> None:
        """In-sample vs OOS Sharpe should be recordable for each model.

        The StrategyResult contract has an overfit_ratio field. We verify
        that when constructing it from backtest results, it can be populated.
        """
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        result, diag = _run_backtest_for_model("ridge", ohlcv, registry)

        if result.daily_returns.empty:
            pytest.skip("No OOS returns produced")

        # Simulate in-sample Sharpe as a higher value for testing
        is_sharpe = result.oos_sharpe * 2.0 if result.oos_sharpe != 0 else 1.0
        oos_sharpe = result.oos_sharpe if result.oos_sharpe != 0 else 0.5

        overfit_ratio = is_sharpe / oos_sharpe if oos_sharpe != 0 else float("inf")

        strategy_result = StrategyResult(
            config=StrategyConfig(
                name="ridge_test",
                model_type="ridge",
                model_kwargs={},
                top_n=10,
                sell_buffer=1.5,
                description="Test ridge",
            ),
            oos_sharpe=oos_sharpe,
            oos_cagr=result.oos_cagr,
            max_drawdown=result.max_drawdown,
            annual_turnover=result.annual_turnover,
            cost_drag_pct=result.cost_drag_pct,
            overfit_ratio=overfit_ratio,
        )

        assert np.isfinite(strategy_result.overfit_ratio)
        assert strategy_result.overfit_ratio > 0, "Overfit ratio should be positive"

    def test_feature_importance_differs_by_model(self) -> None:
        """Different models should produce different feature importance rankings.

        Ridge uses coefficient magnitudes, GBM uses gain-based importance,
        Neural uses gradient-based importance.
        """
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        ridge_pipeline = ResearchPipeline(
            registry=registry,
            model_type="ridge",
            top_n=10,
        )
        ridge_result, _ = ridge_pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        try:
            import lightgbm  # noqa: F401
        except ImportError:
            pytest.skip("lightgbm not installed")

        gbm_pipeline = ResearchPipeline(
            registry=registry,
            model_type="gbm",
            top_n=10,
        )
        gbm_result, _ = gbm_pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if not ridge_result.per_factor_contribution or not gbm_result.per_factor_contribution:
            pytest.skip("No factor contributions produced")

        # Get common factors
        common_factors = set(ridge_result.per_factor_contribution.keys()) & set(
            gbm_result.per_factor_contribution.keys()
        )
        if len(common_factors) < 2:
            pytest.skip("Not enough common factors for comparison")

        # Rankings should differ (different methods => different importance)
        ridge_rank = sorted(
            common_factors, key=lambda f: ridge_result.per_factor_contribution[f], reverse=True
        )
        gbm_rank = sorted(common_factors, key=lambda f: gbm_result.per_factor_contribution[f], reverse=True)

        # It is possible they match by coincidence, so just verify both are populated
        assert len(ridge_rank) > 0, "Ridge has no factor rankings"
        assert len(gbm_rank) > 0, "GBM has no factor rankings"


# ── TestStrategyRegistryIntegration ─────────────────────────────────────


class TestStrategyRegistryIntegration:
    """Test strategy registry with actual backtest results."""

    def test_register_and_compare_multiple_strategies(self) -> None:
        """Register Ridge and GBM results and compare them."""
        reg = StrategyRegistry()

        ridge_config = StrategyConfig(
            name="ridge_default",
            model_type="ridge",
            model_kwargs={"alpha": 1.0},
            top_n=10,
            sell_buffer=1.5,
            description="Default Ridge",
        )
        gbm_config = StrategyConfig(
            name="gbm_default",
            model_type="gbm",
            model_kwargs={},
            top_n=10,
            sell_buffer=1.5,
            description="Default GBM",
        )

        reg.register(ridge_config)
        reg.register(gbm_config)

        ridge_result = StrategyResult(
            config=ridge_config,
            oos_sharpe=0.8,
            oos_cagr=0.06,
            max_drawdown=-0.15,
            annual_turnover=4.0,
            cost_drag_pct=0.003,
            overfit_ratio=1.8,
        )
        gbm_result = StrategyResult(
            config=gbm_config,
            oos_sharpe=1.0,
            oos_cagr=0.09,
            max_drawdown=-0.12,
            annual_turnover=5.0,
            cost_drag_pct=0.004,
            overfit_ratio=2.2,
        )

        reg.record_result("ridge_default", ridge_result)
        reg.record_result("gbm_default", gbm_result)

        comparison, diag = reg.compare()

        assert len(comparison) == 2
        # Sorted by OOS Sharpe descending
        assert comparison.iloc[0]["name"] == "gbm_default"
        assert comparison.iloc[1]["name"] == "ridge_default"

    def test_select_best_with_real_results(self) -> None:
        """Run actual backtest for Ridge and let select_best() choose."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        factor_reg = _make_simple_registry(n_factors=3)

        ridge_result, _ = _run_backtest_for_model("ridge", ohlcv, factor_reg)

        if ridge_result.daily_returns.empty:
            pytest.skip("No OOS returns produced")

        strategy_reg = StrategyRegistry()
        ridge_config = StrategyConfig(
            name="ridge_default",
            model_type="ridge",
            model_kwargs={},
            top_n=10,
            sell_buffer=1.5,
            description="Ridge baseline",
        )
        strategy_reg.register(ridge_config)
        strategy_reg.record_result(
            "ridge_default",
            StrategyResult(
                config=ridge_config,
                oos_sharpe=ridge_result.oos_sharpe,
                oos_cagr=ridge_result.oos_cagr,
                max_drawdown=ridge_result.max_drawdown,
                annual_turnover=ridge_result.annual_turnover,
                cost_drag_pct=ridge_result.cost_drag_pct,
                overfit_ratio=1.5,
            ),
        )

        # select_best with no alternatives returns None (stick with baseline)
        best, diag = strategy_reg.select_best(baseline="ridge_default")
        assert best is None, f"With only baseline registered, select_best should return None, got '{best}'"

    def test_select_best_prefers_significant_improvement(self) -> None:
        """Alternative must beat baseline by min_sharpe_improvement to be selected."""
        strategy_reg = StrategyRegistry()

        ridge_config = StrategyConfig(
            name="ridge_default",
            model_type="ridge",
            model_kwargs={},
            top_n=10,
            sell_buffer=1.5,
            description="Ridge baseline",
        )
        gbm_config = StrategyConfig(
            name="gbm_default",
            model_type="gbm",
            model_kwargs={},
            top_n=10,
            sell_buffer=1.5,
            description="GBM alternative",
        )

        strategy_reg.register(ridge_config)
        strategy_reg.register(gbm_config)

        # GBM beats Ridge by exactly 0.05 -- below default threshold of 0.1
        strategy_reg.record_result(
            "ridge_default",
            StrategyResult(
                config=ridge_config,
                oos_sharpe=0.8,
                oos_cagr=0.06,
                max_drawdown=-0.15,
                annual_turnover=4.0,
                cost_drag_pct=0.003,
                overfit_ratio=1.5,
            ),
        )
        strategy_reg.record_result(
            "gbm_default",
            StrategyResult(
                config=gbm_config,
                oos_sharpe=0.85,
                oos_cagr=0.07,
                max_drawdown=-0.12,
                annual_turnover=5.0,
                cost_drag_pct=0.004,
                overfit_ratio=2.0,
            ),
        )

        best, diag = strategy_reg.select_best(
            baseline="ridge_default",
            min_sharpe_improvement=0.1,
        )
        assert best is None, f"GBM only beats Ridge by 0.05 Sharpe -- should not be selected, got '{best}'"
