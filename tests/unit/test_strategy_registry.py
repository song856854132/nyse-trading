"""Unit tests for multi-strategy registry."""

from __future__ import annotations

from nyse_core.strategy_registry import (
    StrategyConfig,
    StrategyRegistry,
    StrategyResult,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _ridge_config() -> StrategyConfig:
    return StrategyConfig(
        name="ridge_default",
        model_type="ridge",
        model_kwargs={"alpha": 1.0},
        top_n=20,
        sell_buffer=1.5,
        description="Default Ridge baseline",
    )


def _gbm_config() -> StrategyConfig:
    return StrategyConfig(
        name="gbm_tuned",
        model_type="gbm",
        model_kwargs={"n_estimators": 100, "max_depth": 3},
        top_n=20,
        sell_buffer=1.5,
        description="Tuned GBM alternative",
    )


def _neural_config() -> StrategyConfig:
    return StrategyConfig(
        name="neural_v1",
        model_type="neural",
        model_kwargs={"hidden_size": 64, "epochs": 50},
        top_n=20,
        sell_buffer=1.5,
        description="Neural network v1",
    )


def _make_result(config: StrategyConfig, sharpe: float, overfit: float) -> StrategyResult:
    return StrategyResult(
        config=config,
        oos_sharpe=sharpe,
        oos_cagr=0.10,
        max_drawdown=-0.15,
        annual_turnover=2.0,
        cost_drag_pct=0.005,
        overfit_ratio=overfit,
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestRegisterAndGet:
    """Register and retrieve strategies."""

    def test_register_and_get(self):
        reg = StrategyRegistry()
        config = _ridge_config()
        diag = reg.register(config)

        assert not diag.has_errors
        all_strats = reg.get_all()
        assert "ridge_default" in all_strats
        assert all_strats["ridge_default"].model_type == "ridge"


class TestRecordResult:
    """Record backtest results."""

    def test_record_result(self):
        reg = StrategyRegistry()
        config = _ridge_config()
        reg.register(config)

        result = _make_result(config, sharpe=1.0, overfit=1.5)
        diag = reg.record_result("ridge_default", result)

        assert not diag.has_errors

    def test_record_result_unregistered(self):
        reg = StrategyRegistry()
        config = _ridge_config()
        result = _make_result(config, sharpe=1.0, overfit=1.5)
        diag = reg.record_result("nonexistent", result)

        assert diag.has_errors


class TestCompareReturnsSortedDataFrame:
    """Comparison should return a DataFrame sorted by OOS Sharpe."""

    def test_compare_returns_sorted_dataframe(self):
        reg = StrategyRegistry()

        ridge = _ridge_config()
        gbm = _gbm_config()
        reg.register(ridge)
        reg.register(gbm)

        reg.record_result("ridge_default", _make_result(ridge, sharpe=0.8, overfit=1.2))
        reg.record_result("gbm_tuned", _make_result(gbm, sharpe=1.1, overfit=1.8))

        df, diag = reg.compare()

        assert not diag.has_errors
        assert len(df) == 2
        assert df.iloc[0]["name"] == "gbm_tuned"  # highest Sharpe first
        assert df.iloc[1]["name"] == "ridge_default"
        assert "oos_sharpe" in df.columns
        assert "overfit_ratio" in df.columns
        assert "turnover" in df.columns
        assert "cost_drag" in df.columns
        assert "max_dd" in df.columns


class TestSelectBestRidgeWins:
    """No alternative beats baseline -> returns None."""

    def test_select_best_ridge_wins(self):
        reg = StrategyRegistry()

        ridge = _ridge_config()
        gbm = _gbm_config()
        reg.register(ridge)
        reg.register(gbm)

        reg.record_result("ridge_default", _make_result(ridge, sharpe=1.0, overfit=1.2))
        # GBM only 0.05 better -> below 0.1 improvement threshold
        reg.record_result("gbm_tuned", _make_result(gbm, sharpe=1.05, overfit=1.5))

        best, diag = reg.select_best(baseline="ridge_default")

        assert best is None, "Ridge should win when GBM doesn't improve enough"
        assert not diag.has_errors


class TestSelectBestGBMWins:
    """GBM beats Ridge by >0.1 Sharpe -> selected."""

    def test_select_best_gbm_wins(self):
        reg = StrategyRegistry()

        ridge = _ridge_config()
        gbm = _gbm_config()
        reg.register(ridge)
        reg.register(gbm)

        reg.record_result("ridge_default", _make_result(ridge, sharpe=0.8, overfit=1.2))
        reg.record_result("gbm_tuned", _make_result(gbm, sharpe=1.1, overfit=1.5))

        best, diag = reg.select_best(baseline="ridge_default")

        assert best == "gbm_tuned"
        assert not diag.has_errors


class TestSelectBestOverfitRejection:
    """High overfit ratio disqualifies a strategy."""

    def test_select_best_overfit_rejection(self):
        reg = StrategyRegistry()

        ridge = _ridge_config()
        gbm = _gbm_config()
        reg.register(ridge)
        reg.register(gbm)

        reg.record_result("ridge_default", _make_result(ridge, sharpe=0.8, overfit=1.2))
        # GBM has great Sharpe but horrible overfit
        reg.record_result("gbm_tuned", _make_result(gbm, sharpe=1.5, overfit=4.0))

        best, diag = reg.select_best(baseline="ridge_default", max_overfit_ratio=3.0)

        assert best is None, "Overfit strategy should be rejected"


class TestDuplicateRegistrationWarning:
    """Re-registering same name should warn."""

    def test_duplicate_registration_warning(self):
        reg = StrategyRegistry()
        config = _ridge_config()
        reg.register(config)
        diag = reg.register(config)  # duplicate

        assert diag.has_warnings


class TestEmptyRegistry:
    """Empty registry should handle gracefully."""

    def test_empty_registry_compare(self):
        reg = StrategyRegistry()
        df, diag = reg.compare()

        assert len(df) == 0
        assert diag.has_warnings

    def test_empty_registry_get_all(self):
        reg = StrategyRegistry()
        assert reg.get_all() == {}


class TestCompareWithNoResults:
    """Registered strategies but no results."""

    def test_compare_with_no_results(self):
        reg = StrategyRegistry()
        reg.register(_ridge_config())
        df, diag = reg.compare()

        assert len(df) == 0
        assert diag.has_warnings


class TestSelectBestNoBaseline:
    """No baseline results -> picks best passing overfit."""

    def test_select_best_no_baseline(self):
        reg = StrategyRegistry()

        gbm = _gbm_config()
        reg.register(gbm)
        reg.record_result("gbm_tuned", _make_result(gbm, sharpe=1.1, overfit=1.5))

        best, diag = reg.select_best(baseline="ridge_default")

        # No baseline -> should pick gbm_tuned as it passes overfit check
        assert best == "gbm_tuned"
        assert diag.has_warnings  # warns about missing baseline
