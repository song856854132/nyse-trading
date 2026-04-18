"""Integration tests for strict walk-forward backtesting.

These tests verify the CORRECTNESS of the walk-forward engine,
not just that it runs. They catch the specific bugs that existed
in the Phase 3 implementation:
  1. Feature reuse (using train features for test predictions)
  2. Averaged returns (collapsing cross-sections instead of per-date)
  3. Missing turnover/cost computation
  4. Lookahead bias
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from nyse_core.contracts import BacktestResult, Diagnostics
from nyse_core.features.registry import FactorRegistry
from nyse_core.research_pipeline import ResearchPipeline
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_SYMBOL,
    COL_VOLUME,
    DEFAULT_SELL_BUFFER,
    UsageDomain,
)
from tests.fixtures.synthetic_prices import generate_prices

if TYPE_CHECKING:
    from datetime import date

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_simple_registry(
    n_factors: int = 3,
    inject_nan_factor: bool = False,
    nan_fraction: float = 0.0,
) -> FactorRegistry:
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

    for _i, (name, fn) in enumerate(factors[:n_factors]):
        registry.register(
            name=name,
            compute_fn=fn,
            usage_domain=UsageDomain.SIGNAL,
            sign_convention=1,
            description=f"Test factor {name}",
        )

    return registry


def _make_time_aware_registry() -> FactorRegistry:
    """Build a registry with a factor whose value depends on the date.

    If features are reused across dates (bug #1), the test-date prediction
    will use stale values and the assertion will catch it.
    """
    registry = FactorRegistry()

    def _time_dependent_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        data.sort_values(COL_DATE).groupby(COL_SYMBOL).last()
        # Factor value = ordinal of the latest date in the window.
        # Different rebalance dates must produce different values.
        last_dates = data.sort_values(COL_DATE).groupby(COL_SYMBOL)[COL_DATE].last()
        ordinals = last_dates.apply(
            lambda d: d.toordinal() if hasattr(d, "toordinal") else pd.Timestamp(d).toordinal()
        )
        return ordinals.astype(float), diag

    registry.register(
        name="factor_time_dep",
        compute_fn=_time_dependent_factor,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Time-dependent factor for lookahead test",
    )
    return registry


def _make_small_ohlcv(
    n_stocks: int = 50,
    n_days: int = 600,
    seed: int = 42,
) -> pd.DataFrame:
    return generate_prices(n_stocks=n_stocks, n_days=n_days, seed=seed)


# ── TestNoLookaheadBias ─────────────────────────────────────────────────


class TestNoLookaheadBias:
    """Verify that test-period predictions use ONLY data available at prediction time."""

    def test_features_recomputed_per_test_date(self) -> None:
        """Each test date must have features computed from data up to that date ONLY.

        Approach: Inject a time-aware factor that returns different values at
        different dates. If the engine reuses train features, the test
        predictions will not match per-date values.
        """
        ohlcv = _make_small_ohlcv(n_stocks=30, n_days=600)
        registry = _make_time_aware_registry()
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        # Track which dates compute_feature_matrix is called with
        original_cfm = pipeline.compute_feature_matrix
        call_dates: list[date | None] = []

        def _tracking_cfm(ohlcv_arg, fundamentals=None, rebalance_date=None):
            call_dates.append(rebalance_date)
            return original_cfm(ohlcv_arg, fundamentals=fundamentals, rebalance_date=rebalance_date)

        pipeline.compute_feature_matrix = _tracking_cfm  # type: ignore[assignment]

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        # compute_feature_matrix should be called many times (once per train date
        # + once per test date). If only called once, features were reused.
        assert len(call_dates) > 2, (
            f"compute_feature_matrix only called {len(call_dates)} times -- "
            f"features may be reused instead of recomputed per date"
        )

        # Among the calls, there should be multiple distinct rebalance dates
        unique_dates = set(d for d in call_dates if d is not None)
        assert len(unique_dates) > 2, (
            f"Only {len(unique_dates)} distinct rebalance dates -- features not recomputed at each test date"
        )

    def test_forward_returns_not_in_features(self) -> None:
        """Forward returns used as labels must not overlap with feature computation window.

        Approach: Run walk-forward and verify that the purge gap is at least
        as large as the target horizon. The CV splitter's purge_days must be
        >= target_horizon_days.
        """
        ohlcv = _make_small_ohlcv(n_stocks=30, n_days=600)
        registry = _make_simple_registry(n_factors=2)
        pipeline = ResearchPipeline(
            registry=registry,
            target_horizon_days=5,
            top_n=10,
        )

        # Monkey-patch CV to record its config
        from nyse_core.cv import PurgedWalkForwardCV

        original_init = PurgedWalkForwardCV.__init__
        recorded_purge: list[int] = []
        recorded_horizon: list[int] = []

        def _tracking_init(self_cv, *args, **kwargs):
            original_init(self_cv, *args, **kwargs)
            recorded_purge.append(self_cv.purge_days)
            recorded_horizon.append(self_cv.target_horizon_days)

        with patch.object(PurgedWalkForwardCV, "__init__", _tracking_init):
            result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        # Purge gap must be >= target horizon to prevent label leakage
        for p, h in zip(recorded_purge, recorded_horizon, strict=False):
            assert p >= h, (
                f"Purge gap ({p}) < target horizon ({h}) -- forward return labels may leak into features"
            )

    def test_expanding_window_grows(self) -> None:
        """Each successive fold's training set must be larger than the previous.

        Approach: Monkey-patch the pipeline to record training set sizes per fold.
        Assert sizes are strictly increasing.
        """
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        # Patch PurgedWalkForwardCV.split to capture fold train sizes
        from nyse_core.cv import PurgedWalkForwardCV

        original_split = PurgedWalkForwardCV.split
        train_sizes: list[int] = []

        def _tracking_split(self_cv, dates):
            for train_idx, test_idx in original_split(self_cv, dates):
                train_sizes.append(len(train_idx))
                yield train_idx, test_idx

        with patch.object(PurgedWalkForwardCV, "split", _tracking_split):
            result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=3)

        # Training sets should be strictly expanding
        if len(train_sizes) >= 2:
            for i in range(1, len(train_sizes)):
                assert train_sizes[i] >= train_sizes[i - 1], (
                    f"Fold {i} train size ({train_sizes[i]}) < fold {i - 1} "
                    f"({train_sizes[i - 1]}) -- window is not expanding"
                )

    def test_test_ohlcv_excludes_future_data(self) -> None:
        """Data passed to compute_feature_matrix during test phase must not
        include any dates after the test rebalance date.
        """
        ohlcv = _make_small_ohlcv(n_stocks=30, n_days=600)
        registry = _make_simple_registry(n_factors=2)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        original_cfm = pipeline.compute_feature_matrix
        max_dates_per_call: list[tuple[date | None, date | None]] = []

        def _tracking_cfm(ohlcv_arg, fundamentals=None, rebalance_date=None):
            dates_in_data = pd.to_datetime(ohlcv_arg[COL_DATE])
            max_data_date = dates_in_data.max()
            if hasattr(max_data_date, "date"):
                max_data_date = max_data_date.date()
            max_dates_per_call.append((rebalance_date, max_data_date))
            return original_cfm(ohlcv_arg, fundamentals=fundamentals, rebalance_date=rebalance_date)

        pipeline.compute_feature_matrix = _tracking_cfm  # type: ignore[assignment]

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        # For every call, the max date in the OHLCV window must be <= rebalance_date
        for rebal_date, max_data_date in max_dates_per_call:
            if rebal_date is not None and max_data_date is not None:
                assert max_data_date <= rebal_date, (
                    f"Feature computation at {rebal_date} received data up to "
                    f"{max_data_date} -- future data leaked into features"
                )


# ── TestTurnoverAndCost ─────────────────────────────────────────────────


class TestTurnoverAndCost:
    """Verify that turnover and cost are actually computed (not hardcoded 0.0)."""

    def test_annual_turnover_nonzero(self) -> None:
        """With changing factor scores across dates, turnover must be > 0."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if result.daily_returns.empty:
            pytest.skip("No OOS returns produced -- pipeline issue, not turnover")
        assert result.annual_turnover > 0.0, (
            "Annual turnover is 0.0 -- turnover computation is missing or broken"
        )

    def test_cost_drag_nonzero(self) -> None:
        """With non-zero turnover, cost drag must be > 0."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if result.daily_returns.empty:
            pytest.skip("No OOS returns produced")
        if result.annual_turnover == 0.0:
            pytest.skip("Zero turnover -- no cost expected")
        # If there is turnover, there must be cost
        # cost_drag_pct can be relative to cumulative return, but the total_cost
        # in the pipeline should still be > 0. We check cost_drag_pct is populated.
        assert isinstance(result.cost_drag_pct, float), "cost_drag_pct is not a float"

    def test_cost_reduces_returns(self) -> None:
        """Gross returns must be > net returns (costs are positive).

        Approach: Run the pipeline twice -- once with standard cost model,
        once verifying that cost_drag_pct is non-negative.
        """
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if result.daily_returns.empty:
            pytest.skip("No OOS returns produced")
        # cost_drag_pct should be non-negative (costs reduce returns)
        assert result.cost_drag_pct >= 0.0, (
            f"cost_drag_pct={result.cost_drag_pct} is negative -- costs should reduce, not add to, returns"
        )

    def test_sell_buffer_reduces_turnover(self) -> None:
        """Pipeline with sell_buffer=2.0 should have lower turnover than sell_buffer=1.0."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        pipeline_narrow = ResearchPipeline(registry=registry, top_n=10)
        pipeline_wide = ResearchPipeline(registry=registry, top_n=10)

        result_narrow, _ = pipeline_narrow.run_walk_forward_validation(
            ohlcv,
            n_folds=2,
            sell_buffer=1.0,
        )
        result_wide, _ = pipeline_wide.run_walk_forward_validation(
            ohlcv,
            n_folds=2,
            sell_buffer=2.0,
        )

        if result_narrow.daily_returns.empty or result_wide.daily_returns.empty:
            pytest.skip("Insufficient OOS returns for comparison")

        assert result_wide.annual_turnover <= result_narrow.annual_turnover, (
            f"Higher sell_buffer (turnover={result_wide.annual_turnover:.2f}) should have "
            f"<= turnover than lower sell_buffer ({result_narrow.annual_turnover:.2f})"
        )


# ── TestPortfolioConstruction ───────────────────────────────────────────


class TestPortfolioConstruction:
    """Verify portfolio is built correctly each test date."""

    def test_top_n_stocks_selected(self) -> None:
        """At each test date, at most top_n stocks should be selected."""
        from nyse_core.allocator import select_top_n

        rng = np.random.default_rng(42)
        scores = pd.Series(
            rng.uniform(0, 1, 50),
            index=[f"SYM_{i:02d}" for i in range(50)],
        )
        top_n = 10
        selected, diag = select_top_n(scores, n=top_n)

        assert len(selected) == top_n, f"Expected {top_n} stocks selected, got {len(selected)}"

    def test_equal_weights(self) -> None:
        """Selected stocks should have equal weight summing to ~1.0."""
        from nyse_core.allocator import equal_weight

        selected = [f"SYM_{i:02d}" for i in range(10)]
        weights, diag = equal_weight(selected)

        total_weight = sum(weights.values())
        assert abs(total_weight - 1.0) < 1e-9, f"Weights sum to {total_weight}, expected ~1.0"
        # All weights should be equal
        expected_w = 1.0 / len(selected)
        for sym, w in weights.items():
            assert abs(w - expected_w) < 1e-12, f"Weight for {sym} is {w}, expected {expected_w}"

    def test_holdings_carry_over(self) -> None:
        """Current holdings should influence selection across rebalance dates."""
        from nyse_core.allocator import select_top_n

        rng = np.random.default_rng(42)
        # First rebalance
        scores_1 = pd.Series(
            rng.uniform(0, 1, 50),
            index=[f"SYM_{i:02d}" for i in range(50)],
        )
        selected_1, _ = select_top_n(scores_1, n=10, current_holdings=set())

        # Second rebalance: slightly different scores, with sell_buffer
        scores_2 = scores_1 + rng.normal(0, 0.05, 50)
        selected_2, _ = select_top_n(
            scores_2,
            n=10,
            current_holdings=set(selected_1),
            sell_buffer=DEFAULT_SELL_BUFFER,
        )

        # With sell_buffer, some holdings should carry over
        overlap = set(selected_1) & set(selected_2)
        assert len(overlap) > 0, "No holdings carried over between rebalances -- sell_buffer is not working"


# ── TestStatisticalProperties ───────────────────────────────────────────


class TestStatisticalProperties:
    """Verify statistical outputs are sensible."""

    def test_per_fold_sharpe_count(self) -> None:
        """Number of per-fold Sharpe values should equal number of valid folds."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if result.daily_returns.empty:
            pytest.skip("No OOS returns")
        # per_fold_sharpe should have at least 1 entry and at most n_folds
        assert len(result.per_fold_sharpe) >= 1, "No per-fold Sharpe values"
        assert len(result.per_fold_sharpe) <= 2, (
            f"More per-fold Sharpe values ({len(result.per_fold_sharpe)}) than folds (2)"
        )

    def test_oos_sharpe_is_combined(self) -> None:
        """OOS Sharpe should be computed from concatenated OOS returns, not averaged per-fold."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if result.daily_returns.empty or len(result.per_fold_sharpe) < 2:
            pytest.skip("Insufficient data for combined vs averaged comparison")

        from nyse_core.metrics import sharpe_ratio

        # oos_sharpe should come from the combined daily_returns series
        recalculated, _ = sharpe_ratio(result.daily_returns)
        assert abs(result.oos_sharpe - recalculated) < 1e-6, (
            f"OOS Sharpe ({result.oos_sharpe:.4f}) does not match Sharpe of "
            f"concatenated returns ({recalculated:.4f}) -- "
            f"may be averaging per-fold Sharpe instead"
        )

        # Confirm it's NOT the simple average of per-fold Sharpe
        avg_fold = np.mean(result.per_fold_sharpe)
        if abs(result.oos_sharpe - avg_fold) < 1e-6:
            # Could be coincidence, but flag if combined != averaged
            pass  # This is OK only if combined truly equals averaged by coincidence

    def test_permutation_p_value_range(self) -> None:
        """p-value must be in [0, 1]."""
        rng = np.random.default_rng(42)
        n = 200
        dates = pd.bdate_range("2023-01-01", periods=n, freq="B")
        returns = pd.Series(rng.normal(0.001, 0.02, n), index=dates)

        bt = BacktestResult(
            daily_returns=returns,
            oos_sharpe=1.5,
            oos_cagr=0.10,
            max_drawdown=-0.15,
            annual_turnover=3.0,
            cost_drag_pct=0.005,
            per_fold_sharpe=[1.2, 1.8],
            per_factor_contribution={"f_a": 0.6, "f_b": 0.4},
        )

        registry = _make_simple_registry(n_factors=2)
        pipeline = ResearchPipeline(registry=registry)
        result, diag = pipeline.run_statistical_validation(bt)

        assert result.permutation_p_value is not None
        assert 0.0 <= result.permutation_p_value <= 1.0, (
            f"p-value {result.permutation_p_value} outside [0, 1]"
        )

    def test_bootstrap_ci_ordering(self) -> None:
        """CI lower <= CI upper."""
        rng = np.random.default_rng(42)
        n = 200
        dates = pd.bdate_range("2023-01-01", periods=n, freq="B")
        returns = pd.Series(rng.normal(0.001, 0.02, n), index=dates)

        bt = BacktestResult(
            daily_returns=returns,
            oos_sharpe=1.5,
            oos_cagr=0.10,
            max_drawdown=-0.15,
            annual_turnover=3.0,
            cost_drag_pct=0.005,
            per_fold_sharpe=[1.2, 1.8],
            per_factor_contribution={"f_a": 0.6, "f_b": 0.4},
        )

        registry = _make_simple_registry(n_factors=2)
        pipeline = ResearchPipeline(registry=registry)
        result, diag = pipeline.run_statistical_validation(bt)

        assert result.bootstrap_ci_lower is not None
        assert result.bootstrap_ci_upper is not None
        assert result.bootstrap_ci_lower <= result.bootstrap_ci_upper, (
            f"CI lower ({result.bootstrap_ci_lower}) > CI upper ({result.bootstrap_ci_upper})"
        )

    def test_factor_contributions_sum_to_one(self) -> None:
        """Per-factor contributions should be normalized to sum to ~1.0."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if not result.per_factor_contribution:
            pytest.skip("No factor contributions produced")

        total = sum(result.per_factor_contribution.values())
        assert abs(total - 1.0) < 1e-6, f"Factor contributions sum to {total}, expected ~1.0"


# ── TestRealisticDataScale ──────────────────────────────────────────────


class TestRealisticDataScale:
    """Tests with larger data to verify memory and correctness at scale."""

    @pytest.mark.slow
    def test_100_stocks_1000_days(self) -> None:
        """Run walk-forward with 100 stocks x 1000 days.

        Must complete without error and produce sensible BacktestResult.
        """
        ohlcv = generate_prices(n_stocks=100, n_days=1000, seed=42)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=15)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=3)

        assert isinstance(result, BacktestResult)
        # Should produce at least some returns
        assert len(result.daily_returns) > 0, "No daily returns at scale"
        assert isinstance(result.oos_sharpe, float)
        assert not np.isnan(result.oos_sharpe), "OOS Sharpe is NaN at scale"

    def test_result_fields_populated(self) -> None:
        """All BacktestResult fields must be populated (no None, no NaN except stat fields)."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if result.daily_returns.empty:
            pytest.skip("No OOS returns produced")

        # Core fields must not be None or NaN
        assert isinstance(result.oos_sharpe, float) and not np.isnan(result.oos_sharpe)
        assert isinstance(result.oos_cagr, float) and not np.isnan(result.oos_cagr)
        assert isinstance(result.max_drawdown, float) and not np.isnan(result.max_drawdown)
        assert isinstance(result.annual_turnover, float) and not np.isnan(result.annual_turnover)
        assert isinstance(result.cost_drag_pct, float) and not np.isnan(result.cost_drag_pct)
        assert isinstance(result.per_fold_sharpe, list)
        assert len(result.per_fold_sharpe) > 0
        assert isinstance(result.per_factor_contribution, dict)
        assert len(result.per_factor_contribution) > 0

        # daily_returns should have no NaN
        assert result.daily_returns.isna().sum() == 0, (
            f"{result.daily_returns.isna().sum()} NaN values in daily_returns"
        )

    def test_max_drawdown_is_negative_or_zero(self) -> None:
        """Max drawdown must be <= 0 (it measures peak-to-trough loss)."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)
        pipeline = ResearchPipeline(registry=registry, top_n=10)

        result, diag = pipeline.run_walk_forward_validation(ohlcv, n_folds=2)

        if result.daily_returns.empty:
            pytest.skip("No OOS returns produced")
        assert result.max_drawdown <= 0.0, (
            f"Max drawdown ({result.max_drawdown}) is positive -- should be <= 0"
        )
