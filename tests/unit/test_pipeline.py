"""Unit tests for nyse_ats.pipeline."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from nyse_ats.pipeline import TradingPipeline, _empty_result
from nyse_core.contracts import (
    BacktestResult,
    Diagnostics,
    PortfolioBuildResult,
)
from nyse_core.schema import COL_DATE, RegimeState, Side

# ── Helper factories ────────────────────────────────────────────────────────


def _make_strategy_params(kill_switch: bool = False) -> MagicMock:
    """Build a mock StrategyParams matching config_schema.py."""
    sp = MagicMock()
    sp.kill_switch = kill_switch

    sp.combination.model = "ridge"
    sp.combination.alpha = 1.0
    sp.combination.target_horizon_days = 5

    sp.allocator.top_n = 5
    sp.allocator.sell_buffer = 1.5

    sp.risk.max_position_pct = 0.10
    sp.risk.max_sector_pct = 0.30

    sp.rebalance.frequency = "weekly"
    sp.rebalance.day_of_week = "Monday"

    return sp


def _make_config(kill_switch: bool = False) -> dict:
    return {"strategy_params": _make_strategy_params(kill_switch)}


def _make_market_data(n_symbols: int = 10, nan_frac: float = 0.0) -> pd.DataFrame:
    """Generate a DataFrame with date + numeric feature columns."""
    symbols = [f"SYM{i}" for i in range(n_symbols)]
    data = {
        COL_DATE: [date(2024, 6, 1)] * n_symbols,
        "symbol": symbols,
        "momentum_20d": np.random.default_rng(42).random(n_symbols),
        "value_score": np.random.default_rng(43).random(n_symbols),
    }
    df = pd.DataFrame(data)

    if nan_frac > 0:
        rng = np.random.default_rng(44)
        for col in ["momentum_20d", "value_score"]:
            mask = rng.random(n_symbols) < nan_frac
            df.loc[mask, col] = np.nan

    return df


def _make_features(n_symbols: int = 10, nan_frac: float = 0.0) -> pd.DataFrame:
    """Features DataFrame (what FactorRegistry.compute_all returns)."""
    rng = np.random.default_rng(42)
    data = {
        "momentum_20d": rng.random(n_symbols),
        "value_score": rng.random(n_symbols),
    }
    df = pd.DataFrame(data)
    if nan_frac > 0:
        mask_rng = np.random.default_rng(44)
        for col in df.columns:
            mask = mask_rng.random(n_symbols) < nan_frac
            df.loc[mask, col] = np.nan
    return df


def _mock_adapter(data: pd.DataFrame | None = None) -> MagicMock:
    adapter = MagicMock()
    adapter.fetch.return_value = data if data is not None else _make_market_data()
    return adapter


def _mock_storage() -> MagicMock:
    return MagicMock()


def _mock_registry(features: pd.DataFrame | None = None) -> MagicMock:
    registry = MagicMock()
    feat = features if features is not None else _make_features()
    registry.compute_all.return_value = (feat, Diagnostics())
    return registry


def _mock_bridge() -> MagicMock:
    bridge = MagicMock()
    bridge.submit.return_value = ([], Diagnostics())
    bridge.reconcile.return_value = Diagnostics()
    return bridge


# ── Construction ────────────────────────────────────────────────────────────


class TestPipelineConstruction:
    def test_missing_strategy_params_raises(self) -> None:
        with pytest.raises(ValueError, match="strategy_params"):
            TradingPipeline(
                config={},
                data_adapters={},
                storage=_mock_storage(),
                factor_registry=_mock_registry(),
            )

    def test_valid_construction(self) -> None:
        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter()},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )
        assert pipeline is not None


# ── Kill switch ─────────────────────────────────────────────────────────────


class TestKillSwitch:
    def test_check_kill_switch_true(self) -> None:
        pipeline = TradingPipeline(
            config=_make_config(kill_switch=True),
            data_adapters={},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )
        assert pipeline.check_kill_switch() is True

    def test_check_kill_switch_false(self) -> None:
        pipeline = TradingPipeline(
            config=_make_config(kill_switch=False),
            data_adapters={},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )
        assert pipeline.check_kill_switch() is False

    def test_kill_switch_skips_rebalance(self) -> None:
        pipeline = TradingPipeline(
            config=_make_config(kill_switch=True),
            data_adapters={"ohlcv": _mock_adapter()},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )
        result, diag = pipeline.run_rebalance(date(2024, 6, 1))

        assert isinstance(result, PortfolioBuildResult)
        assert result.trade_plans == []
        assert result.skipped_reason == "kill_switch_active"
        assert diag.has_warnings


# ── Daily loss halt ─────────────────────────────────────────────────────────


class TestDailyLossHalt:
    def test_daily_loss_halts_rebalance(self) -> None:
        """Pipeline should abort rebalance when daily loss limit is breached."""
        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter()},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )
        pipeline._last_daily_return = -0.04  # -4%, below -3% limit
        result, diag = pipeline.run_rebalance(date(2024, 6, 1))

        assert result.trade_plans == []
        assert result.skipped_reason == "daily_loss_halt"
        assert diag.has_warnings

    def test_no_daily_return_proceeds_normally(self) -> None:
        """Without daily return set, pipeline should proceed normally."""
        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter()},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )
        # _last_daily_return not set — should not halt
        result, diag = pipeline.run_rebalance(
            date(2024, 6, 1),
            market_data=_make_features(nan_frac=0.0),
        )
        assert result.skipped_reason != "daily_loss_halt"


# ── Data-path detection ─────────────────────────────────────────────────────


class TestDataPathDetection:
    def _pipeline(self) -> TradingPipeline:
        return TradingPipeline(
            config=_make_config(),
            data_adapters={},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )

    def test_happy_path(self) -> None:
        p = self._pipeline()
        features = _make_features(nan_frac=0.0)
        assert p._detect_data_path(features) == "HAPPY"

    def test_nil_path(self) -> None:
        p = self._pipeline()
        # Build a deterministic features frame with exactly 30% NaN (6/20)
        features = pd.DataFrame(
            {
                "f1": [1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, np.nan, 9.0, 10.0],
                "f2": [1.0, np.nan, 3.0, 4.0, np.nan, 6.0, 7.0, 8.0, np.nan, 10.0],
            }
        )
        path = p._detect_data_path(features)
        assert path == "NIL"

    def test_error_path(self) -> None:
        p = self._pipeline()
        # Build a deterministic features frame with >50% NaN (12/20)
        features = pd.DataFrame(
            {
                "f1": [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 7.0, 8.0, 9.0, 10.0],
                "f2": [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 7.0, 8.0, 9.0, 10.0],
            }
        )
        path = p._detect_data_path(features)
        assert path == "ERROR"

    def test_empty_path_all_nan(self) -> None:
        p = self._pipeline()
        features = pd.DataFrame(
            {
                "f1": [np.nan] * 10,
                "f2": [np.nan] * 10,
            }
        )
        path = p._detect_data_path(features)
        assert path == "EMPTY"

    def test_empty_path_empty_dataframe(self) -> None:
        p = self._pipeline()
        features = pd.DataFrame()
        assert p._detect_data_path(features) == "EMPTY"


# ── Happy path rebalance ───────────────────────────────────────────────────


class TestHappyPathRebalance:
    @patch("nyse_ats.pipeline.build_portfolio")
    @patch("nyse_ats.pipeline.cross_sectional_impute")
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    @patch("nyse_ats.pipeline.create_model")
    def test_produces_portfolio_build_result(
        self,
        mock_create_model: MagicMock,
        mock_pit: MagicMock,
        mock_impute: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        market_data = _make_market_data()
        features = _make_features()
        registry = _mock_registry(features)

        # Mock PiT: pass through
        mock_pit.return_value = (market_data, Diagnostics())

        # Mock impute: add date column
        imputed = features.copy()
        imputed[COL_DATE] = date(2024, 6, 1)
        mock_impute.return_value = (imputed, Diagnostics())

        # Mock model
        mock_model = MagicMock()
        scores = pd.Series(
            np.random.default_rng(42).random(len(features)),
            index=range(len(features)),
        )
        mock_model.predict.return_value = (scores, Diagnostics())
        mock_create_model.return_value = (mock_model, Diagnostics())

        # Mock build_portfolio
        expected = PortfolioBuildResult(
            trade_plans=[],
            cost_estimate_usd=10.0,
            turnover_pct=0.05,
            regime_state=RegimeState.BULL,
            rebalance_date=date(2024, 6, 1),
            held_positions=5,
            new_entries=5,
            exits=0,
        )
        mock_build.return_value = (expected, Diagnostics())

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter(market_data)},
            storage=_mock_storage(),
            factor_registry=registry,
        )

        result, diag = pipeline.run_rebalance(
            date(2024, 6, 1),
            market_data=market_data,
        )

        assert isinstance(result, PortfolioBuildResult)
        assert result.rebalance_date == date(2024, 6, 1)
        assert not diag.has_errors

    @patch("nyse_ats.pipeline.build_portfolio")
    @patch("nyse_ats.pipeline.cross_sectional_impute")
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    @patch("nyse_ats.pipeline.create_model")
    def test_model_fit_called_before_predict(
        self,
        mock_create_model: MagicMock,
        mock_pit: MagicMock,
        mock_impute: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        """Model.fit() must be called before model.predict()."""
        market_data = _make_market_data()
        features = _make_features()
        registry = _mock_registry(features)

        mock_pit.return_value = (market_data, Diagnostics())

        imputed = features.copy()
        imputed[COL_DATE] = date(2024, 6, 1)
        mock_impute.return_value = (imputed, Diagnostics())

        # Track call order
        call_order: list[str] = []
        mock_model = MagicMock()
        mock_model.fit.side_effect = lambda *a, **kw: call_order.append("fit") or Diagnostics()
        scores = pd.Series(
            np.random.default_rng(42).random(len(features)),
            index=range(len(features)),
        )
        mock_model.predict.side_effect = lambda *a, **kw: (
            call_order.append("predict") or (scores, Diagnostics())
        )
        mock_create_model.return_value = (mock_model, Diagnostics())

        expected = PortfolioBuildResult(
            trade_plans=[],
            cost_estimate_usd=0.0,
            turnover_pct=0.0,
            regime_state=RegimeState.BULL,
            rebalance_date=date(2024, 6, 1),
            held_positions=0,
            new_entries=0,
            exits=0,
        )
        mock_build.return_value = (expected, Diagnostics())

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter(market_data)},
            storage=_mock_storage(),
            factor_registry=registry,
        )
        pipeline.run_rebalance(date(2024, 6, 1), market_data=market_data)

        assert "fit" in call_order, "model.fit() was never called"
        assert "predict" in call_order, "model.predict() was never called"
        assert call_order.index("fit") < call_order.index("predict"), (
            "model.fit() must be called before model.predict()"
        )


# ── NIL path ────────────────────────────────────────────────────────────────


class TestNilPath:
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    def test_nil_holds_positions_zero_trades(self, mock_pit: MagicMock) -> None:
        market_data = _make_market_data()
        mock_pit.return_value = (market_data, Diagnostics())

        # Deterministic 30% NaN (6/20 cells)
        nil_features = pd.DataFrame(
            {
                "f1": [1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, np.nan, 9.0, 10.0],
                "f2": [1.0, np.nan, 3.0, 4.0, np.nan, 6.0, 7.0, 8.0, np.nan, 10.0],
            }
        )
        registry = _mock_registry(nil_features)

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter(market_data)},
            storage=_mock_storage(),
            factor_registry=registry,
        )

        result, diag = pipeline.run_rebalance(
            date(2024, 6, 1),
            market_data=market_data,
        )

        assert result.trade_plans == []
        assert result.skipped_reason == "nil_universe"
        assert diag.has_warnings


# ── EMPTY path ──────────────────────────────────────────────────────────────


class TestEmptyPath:
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    def test_empty_skips_no_sells(self, mock_pit: MagicMock) -> None:
        market_data = _make_market_data()
        mock_pit.return_value = (market_data, Diagnostics())

        # All NaN features
        empty_features = pd.DataFrame(
            {
                "f1": [np.nan] * 10,
                "f2": [np.nan] * 10,
            }
        )
        registry = _mock_registry(empty_features)

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter(market_data)},
            storage=_mock_storage(),
            factor_registry=registry,
        )

        result, diag = pipeline.run_rebalance(
            date(2024, 6, 1),
            market_data=market_data,
        )

        assert result.trade_plans == []
        assert result.skipped_reason == "empty_features"
        # Crucially: no SELL orders generated for held positions
        sell_plans = [tp for tp in result.trade_plans if tp.side == Side.SELL]
        assert len(sell_plans) == 0


# ── ERROR path ──────────────────────────────────────────────────────────────


class TestErrorPath:
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    def test_error_skips_rebalance(self, mock_pit: MagicMock) -> None:
        market_data = _make_market_data()
        mock_pit.return_value = (market_data, Diagnostics())

        # Deterministic >50% NaN (12/20 cells)
        error_features = pd.DataFrame(
            {
                "f1": [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 7.0, 8.0, 9.0, 10.0],
                "f2": [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 7.0, 8.0, 9.0, 10.0],
            }
        )
        registry = _mock_registry(error_features)

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter(market_data)},
            storage=_mock_storage(),
            factor_registry=registry,
        )

        result, diag = pipeline.run_rebalance(
            date(2024, 6, 1),
            market_data=market_data,
        )

        assert result.trade_plans == []
        assert result.skipped_reason == "error_features"
        assert diag.has_errors


# ── Backtest ────────────────────────────────────────────────────────────────


class TestBacktest:
    def test_missing_data_returns_empty_result(self) -> None:
        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )
        result, diag = pipeline.run_backtest(
            start_date=date(2020, 1, 1),
            end_date=date(2024, 1, 1),
        )
        assert isinstance(result, BacktestResult)
        assert result.oos_sharpe == 0.0
        assert diag.has_errors


# ── Adapter fallback ────────────────────────────────────────────────────────


class TestAdapterFallback:
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    def test_all_adapters_fail_returns_error(self, mock_pit: MagicMock) -> None:
        failing_adapter = MagicMock()
        failing_adapter.fetch.side_effect = RuntimeError("connection failed")

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"bad": failing_adapter},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )

        result, diag = pipeline.run_rebalance(date(2024, 6, 1))

        assert result.skipped_reason == "data_load_error"
        assert diag.has_errors


# ── Empty result helper ────────────────────────────────────────────────────


class TestEmptyResult:
    def test_empty_result_has_correct_fields(self) -> None:
        r = _empty_result(date(2024, 6, 1), "test_reason")
        assert isinstance(r, PortfolioBuildResult)
        assert r.trade_plans == []
        assert r.skipped_reason == "test_reason"
        assert r.rebalance_date == date(2024, 6, 1)
        assert r.turnover_pct == 0.0


# ── Normalize features (Fix 1: winsorize + all-NaN drop) ──────────────────


class TestNormalizeFeatures:
    def _pipeline(self) -> TradingPipeline:
        return TradingPipeline(
            config=_make_config(),
            data_adapters={},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )

    def test_normalize_produces_values_in_unit_interval(self) -> None:
        """After winsorize + rank_percentile, all values should be in [0, 1]."""
        p = self._pipeline()
        features = pd.DataFrame(
            {
                "f1": [100.0, 200.0, 300.0, 400.0, 500.0],
                "f2": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )
        diag = Diagnostics()
        result = p._normalize_features(features, diag)

        for col in result.select_dtypes(include="number").columns:
            non_nan = result[col].dropna()
            assert (non_nan >= 0.0).all() and (non_nan <= 1.0).all(), (
                f"Column {col} has values outside [0, 1]"
            )

    def test_normalize_drops_all_nan_columns(self) -> None:
        """Columns that are entirely NaN after normalization get dropped."""
        p = self._pipeline()
        features = pd.DataFrame(
            {
                "good_f": [1.0, 2.0, 3.0],
                "nan_f": [np.nan, np.nan, np.nan],
            }
        )
        diag = Diagnostics()
        result = p._normalize_features(features, diag)

        assert "good_f" in result.columns
        assert "nan_f" not in result.columns
        assert diag.has_warnings  # Warning about dropped column


# ── Multi-dataset loading (Fix 2: _load_all_data) ─────────────────────────


class TestLoadAllData:
    def test_loads_from_multiple_adapters(self) -> None:
        """All adapters should be called and results keyed by name."""
        ohlcv_adapter = _mock_adapter(_make_market_data())
        fund_adapter = MagicMock()
        fund_adapter.fetch.return_value = pd.DataFrame({"roe": [0.1, 0.2]})

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": ohlcv_adapter, "fundamentals": fund_adapter},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )

        diag = Diagnostics()
        result = pipeline._load_all_data(date(2024, 6, 1), diag)

        assert "ohlcv" in result
        assert "fundamentals" in result
        assert not diag.has_errors

    def test_partial_failure_continues(self) -> None:
        """One adapter failing should not block others."""
        good_adapter = _mock_adapter(_make_market_data())
        bad_adapter = MagicMock()
        bad_adapter.fetch.side_effect = ConnectionError("timeout")

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": good_adapter, "broken": bad_adapter},
            storage=_mock_storage(),
            factor_registry=_mock_registry(),
        )

        diag = Diagnostics()
        result = pipeline._load_all_data(date(2024, 6, 1), diag)

        assert "ohlcv" in result
        assert "broken" not in result
        assert diag.has_warnings  # Warning about broken adapter
        assert not diag.has_errors  # Not a fatal error


# ── Price extraction (Issue 5: eliminate magic $50 default) ────────────────


class TestPriceExtraction:
    @patch("nyse_ats.pipeline.build_portfolio")
    @patch("nyse_ats.pipeline.cross_sectional_impute")
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    @patch("nyse_ats.pipeline.create_model")
    def test_prices_extracted_from_ohlcv_passed_to_portfolio(
        self,
        mock_create_model: MagicMock,
        mock_pit: MagicMock,
        mock_impute: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        """Pipeline should extract close prices from OHLCV and pass as
        portfolio_config['prices'] — not rely on the $50 default."""
        from nyse_core.schema import COL_CLOSE, COL_SYMBOL

        # Market data with known close prices per symbol
        market_data = pd.DataFrame(
            {
                COL_DATE: [date(2024, 6, 1)] * 3,
                COL_SYMBOL: ["AAPL", "MSFT", "GOOG"],
                COL_CLOSE: [180.0, 420.0, 175.0],
                "momentum_20d": [0.5, 0.6, 0.7],
            }
        )

        features = _make_features(n_symbols=3)
        registry = _mock_registry(features)

        mock_pit.return_value = (market_data, Diagnostics())

        imputed = features.copy()
        imputed[COL_DATE] = date(2024, 6, 1)
        mock_impute.return_value = (imputed, Diagnostics())

        mock_model = MagicMock()
        scores = pd.Series([0.9, 0.8, 0.7], index=range(3))
        mock_model.predict.return_value = (scores, Diagnostics())
        mock_create_model.return_value = (mock_model, Diagnostics())

        expected = PortfolioBuildResult(
            trade_plans=[],
            cost_estimate_usd=0.0,
            turnover_pct=0.0,
            regime_state=RegimeState.BULL,
            rebalance_date=date(2024, 6, 1),
            held_positions=0,
            new_entries=0,
            exits=0,
        )
        mock_build.return_value = (expected, Diagnostics())

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter(market_data)},
            storage=_mock_storage(),
            factor_registry=registry,
        )
        pipeline.run_rebalance(date(2024, 6, 1), market_data=market_data)

        # Verify build_portfolio received prices
        call_kwargs = mock_build.call_args
        config_arg = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        if config_arg is None:
            # Positional argument — config is the 6th arg
            config_arg = call_kwargs[0][5] if len(call_kwargs[0]) > 5 else {}

        assert "prices" in config_arg
        assert config_arg["prices"].get("AAPL") == 180.0
        assert config_arg["prices"].get("MSFT") == 420.0


# ── Provenance flow (Fix 6: pipeline → portfolio) ─────────────────────────


class TestProvenanceFlow:
    @patch("nyse_ats.pipeline.build_portfolio")
    @patch("nyse_ats.pipeline.cross_sectional_impute")
    @patch("nyse_ats.pipeline.enforce_pit_lags")
    @patch("nyse_ats.pipeline.create_model")
    def test_provenance_passed_in_portfolio_config(
        self,
        mock_create_model: MagicMock,
        mock_pit: MagicMock,
        mock_impute: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        """Pipeline must assemble provenance dict and pass via config."""
        market_data = _make_market_data()
        features = _make_features()
        registry = _mock_registry(features)

        mock_pit.return_value = (market_data, Diagnostics())

        imputed = features.copy()
        imputed[COL_DATE] = date(2024, 6, 1)
        mock_impute.return_value = (imputed, Diagnostics())

        mock_model = MagicMock()
        scores = pd.Series(
            np.random.default_rng(42).random(len(features)),
            index=range(len(features)),
        )
        mock_model.predict.return_value = (scores, Diagnostics())
        mock_create_model.return_value = (mock_model, Diagnostics())

        expected = PortfolioBuildResult(
            trade_plans=[],
            cost_estimate_usd=0.0,
            turnover_pct=0.0,
            regime_state=RegimeState.BULL,
            rebalance_date=date(2024, 6, 1),
            held_positions=0,
            new_entries=0,
            exits=0,
        )
        mock_build.return_value = (expected, Diagnostics())

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={"ohlcv": _mock_adapter(market_data)},
            storage=_mock_storage(),
            factor_registry=registry,
        )
        pipeline.run_rebalance(date(2024, 6, 1), market_data=market_data)

        call_kwargs = mock_build.call_args
        config_arg = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        if config_arg is None:
            config_arg = call_kwargs[0][5] if len(call_kwargs[0]) > 5 else {}

        assert "provenance" in config_arg
        prov = config_arg["provenance"]
        assert prov["model_type"] == "ridge"
        assert prov["data_path"] == "HAPPY"
        assert prov["rebalance_date"] == "2024-06-01"
        assert "n_features" in prov
        assert "n_stocks_scored" in prov


# ── Backtest pivoted returns (Fix 3) ──────────────────────────────────────


class TestBacktestPivotedReturns:
    def test_load_backtest_data_returns_per_stock_dataframe(self) -> None:
        """_load_backtest_data should return a returns DataFrame with
        per-stock columns, NOT a single market-average Series."""
        from nyse_core.schema import COL_CLOSE, COL_SYMBOL

        storage = MagicMock()
        features_df = pd.DataFrame(
            {
                COL_SYMBOL: ["AAPL", "MSFT", "AAPL", "MSFT"],
                "momentum": [0.5, 0.6, 0.7, 0.8],
            }
        )
        storage.load_features.return_value = (features_df, Diagnostics())

        ohlcv = pd.DataFrame(
            {
                COL_DATE: [
                    date(2024, 1, 1),
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 3),
                ],
                COL_SYMBOL: ["AAPL", "MSFT", "AAPL", "MSFT", "AAPL", "MSFT"],
                COL_CLOSE: [150.0, 400.0, 153.0, 404.0, 155.0, 408.0],
            }
        )
        storage.load_ohlcv.return_value = (ohlcv, Diagnostics())

        pipeline = TradingPipeline(
            config=_make_config(),
            data_adapters={},
            storage=storage,
            factor_registry=_mock_registry(),
        )

        diag = Diagnostics()
        feat, returns = pipeline._load_backtest_data(
            date(2024, 1, 1),
            date(2024, 1, 3),
            diag,
        )

        # Returns should be a DataFrame, not a Series
        assert isinstance(returns, pd.DataFrame)
        # Columns should be per-stock
        assert "AAPL" in returns.columns
        assert "MSFT" in returns.columns
        # Values should be pct_change (not averaged across stocks)
        assert not returns.empty
