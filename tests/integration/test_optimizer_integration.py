"""Integration tests for walk-forward parameter tuning.

Tests that the pipeline correctly explores a parameter grid (top_n, sell_buffer)
and selects the best configuration, including AP-7 overfitting warnings.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import numpy as np

from nyse_core.contracts import Diagnostics
from nyse_core.cv import PurgedWalkForwardCV
from nyse_core.features.registry import FactorRegistry
from nyse_core.research_pipeline import ResearchPipeline
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_SYMBOL,
    COL_VOLUME,
    MAX_PARAMS_WARNING,
    UsageDomain,
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


def _tune_parameter(
    ohlcv: pd.DataFrame,
    registry: FactorRegistry,
    param_name: str,
    param_grid: list,
    base_top_n: int = 10,
    base_sell_buffer: float = 1.5,
    n_folds: int = 2,
) -> tuple[dict, list[tuple]]:
    """Simple grid search over a single parameter.

    Returns (best_config, all_results) where each result is
    (param_value, oos_sharpe, BacktestResult).
    """
    results: list[tuple] = []

    for val in param_grid:
        top_n = val if param_name == "top_n" else base_top_n
        sell_buffer = val if param_name == "sell_buffer" else base_sell_buffer

        pipeline = ResearchPipeline(
            registry=registry,
            top_n=top_n,
        )
        bt_result, diag = pipeline.run_walk_forward_validation(
            ohlcv,
            n_folds=n_folds,
            sell_buffer=sell_buffer,
        )
        results.append((val, bt_result.oos_sharpe, bt_result))

    # Select best by OOS Sharpe
    best = max(results, key=lambda x: x[1] if np.isfinite(x[1]) else float("-inf"))
    best_config = {param_name: best[0], "oos_sharpe": best[1]}
    return best_config, results


def _tune_multi_params(
    ohlcv: pd.DataFrame,
    registry: FactorRegistry,
    top_n_grid: list[int],
    sell_buffer_grid: list[float],
    n_folds: int = 2,
) -> tuple[dict, list[tuple]]:
    """Grid search over top_n x sell_buffer."""
    results: list[tuple] = []

    for top_n in top_n_grid:
        for sell_buffer in sell_buffer_grid:
            pipeline = ResearchPipeline(
                registry=registry,
                top_n=top_n,
            )
            bt_result, diag = pipeline.run_walk_forward_validation(
                ohlcv,
                n_folds=n_folds,
                sell_buffer=sell_buffer,
            )
            results.append((top_n, sell_buffer, bt_result.oos_sharpe, bt_result))

    # Select best by OOS Sharpe
    best = max(
        results,
        key=lambda x: x[2] if np.isfinite(x[2]) else float("-inf"),
    )
    best_config = {
        "top_n": best[0],
        "sell_buffer": best[1],
        "oos_sharpe": best[2],
    }
    return best_config, results


# ── TestOptimizerIntegration ────────────────────────────────────────────


class TestOptimizerIntegration:
    """Tests for walk-forward parameter tuning."""

    def test_tune_top_n(self) -> None:
        """Tune top_n from grid [10, 15, 20]; should select one."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        best_config, all_results = _tune_parameter(
            ohlcv,
            registry,
            param_name="top_n",
            param_grid=[10, 15, 20],
        )

        assert "top_n" in best_config
        assert best_config["top_n"] in [10, 15, 20], f"Best top_n={best_config['top_n']} not in grid"
        assert len(all_results) == 3, f"Expected 3 results, got {len(all_results)}"

        # Each result should have a finite Sharpe (even if 0.0)
        for val, sharpe, _bt in all_results:
            assert isinstance(sharpe, float), f"Sharpe for top_n={val} is not float"

    def test_tune_sell_buffer(self) -> None:
        """Tune sell_buffer from grid [1.0, 1.5, 2.0]; should select one."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        best_config, all_results = _tune_parameter(
            ohlcv,
            registry,
            param_name="sell_buffer",
            param_grid=[1.0, 1.5, 2.0],
        )

        assert "sell_buffer" in best_config
        assert best_config["sell_buffer"] in [1.0, 1.5, 2.0], (
            f"Best sell_buffer={best_config['sell_buffer']} not in grid"
        )
        assert len(all_results) == 3

    def test_tune_multiple_params(self) -> None:
        """Tune top_n x sell_buffer grid; should return best combo."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600)
        registry = _make_simple_registry(n_factors=3)

        best_config, all_results = _tune_multi_params(
            ohlcv,
            registry,
            top_n_grid=[10, 15],
            sell_buffer_grid=[1.0, 1.5],
        )

        assert "top_n" in best_config
        assert "sell_buffer" in best_config
        assert best_config["top_n"] in [10, 15]
        assert best_config["sell_buffer"] in [1.0, 1.5]
        # 2 x 2 = 4 combos
        assert len(all_results) == 4, f"Expected 4 results, got {len(all_results)}"

    def test_ap7_warning_with_many_params(self) -> None:
        """Large grid should trigger AP-7 warning from PurgedWalkForwardCV.

        AP-7: warn if n_params > 5 with < 60 monthly observations.
        """
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=63,
            purge_days=5,
            embargo_days=5,
            target_horizon_days=5,
        )

        # 6 params with only ~24 monthly observations (504 days = 24 months)
        n_params = MAX_PARAMS_WARNING + 1  # 6 (exceeds threshold of 5)
        n_obs = 504

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            passed, _ = cv.max_params_check(n_params, n_obs)

            assert not passed, "AP-7 check should fail with many params and few obs"
            assert len(w) >= 1, "Expected at least one warning"
            assert any("AP-7" in str(warning.message) for warning in w), (
                f"Expected AP-7 warning, got: {[str(x.message) for x in w]}"
            )

    def test_ap7_no_warning_with_few_params(self) -> None:
        """Small grid should NOT trigger AP-7 warning."""
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=63,
            purge_days=5,
            embargo_days=5,
            target_horizon_days=5,
        )

        # 3 params with enough data -- should pass
        n_params = 3
        n_obs = 504

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            passed, _ = cv.max_params_check(n_params, n_obs)

            assert passed, "AP-7 check should pass with few params"
            ap7_warnings = [x for x in w if "AP-7" in str(x.message)]
            assert len(ap7_warnings) == 0, f"Unexpected AP-7 warning with {n_params} params"

    def test_grid_results_are_deterministic(self) -> None:
        """Running the same grid twice with the same seed should produce identical results."""
        ohlcv = _make_small_ohlcv(n_stocks=50, n_days=600, seed=42)
        registry = _make_simple_registry(n_factors=3)

        best_1, results_1 = _tune_parameter(
            ohlcv,
            registry,
            param_name="top_n",
            param_grid=[10, 15],
        )
        best_2, results_2 = _tune_parameter(
            ohlcv,
            registry,
            param_name="top_n",
            param_grid=[10, 15],
        )

        assert best_1["top_n"] == best_2["top_n"], (
            f"Non-deterministic: first run picked top_n={best_1['top_n']}, second picked {best_2['top_n']}"
        )
        for (v1, s1, _), (v2, s2, _) in zip(results_1, results_2, strict=False):
            assert v1 == v2
            assert abs(s1 - s2) < 1e-9, f"Non-deterministic Sharpe for top_n={v1}: {s1} vs {s2}"
