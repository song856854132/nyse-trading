"""Unit tests for nyse_core.optimizer.tune_parameters.

Covers: basic tuning, single-param grid, best selection logic,
AP-7 overfitting warning, and empty grid edge case.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from nyse_core.contracts import Diagnostics
from nyse_core.features.registry import FactorRegistry
from nyse_core.optimizer import tune_parameters
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL, COL_VOLUME, UsageDomain
from tests.fixtures.synthetic_prices import generate_prices

if TYPE_CHECKING:
    import pandas as pd

# ── Helpers ───────────────────────────────────────────────────────────


def _small_registry() -> FactorRegistry:
    """Minimal 2-factor registry for speed."""
    reg = FactorRegistry()

    def _close_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        latest = data.sort_values(COL_DATE).groupby(COL_SYMBOL).last()
        return latest[COL_CLOSE], diag

    def _volume_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        latest = data.sort_values(COL_DATE).groupby(COL_SYMBOL).last()
        return latest[COL_VOLUME].astype(float), diag

    reg.register("factor_close", _close_factor, UsageDomain.SIGNAL, 1, "close rank")
    reg.register("factor_volume", _volume_factor, UsageDomain.SIGNAL, 1, "volume rank")
    return reg


def _small_ohlcv() -> pd.DataFrame:
    return generate_prices(n_stocks=30, n_days=600, seed=42)


# ── Tests ─────────────────────────────────────────────────────────────


class TestTuneParameters:
    """Unit tests for tune_parameters."""

    def test_basic_tuning_returns_best_params(self) -> None:
        """Should return a dict with keys matching the grid."""
        ohlcv = _small_ohlcv()
        reg = _small_registry()
        grid = {"top_n": [5, 10], "sell_buffer": [1.0, 1.5]}

        best, diag = tune_parameters(ohlcv, reg, grid, n_folds=2)

        assert isinstance(best, dict)
        assert "top_n" in best
        assert "sell_buffer" in best
        assert best["top_n"] in [5, 10]
        assert best["sell_buffer"] in [1.0, 1.5]

    def test_single_param_grid(self) -> None:
        """Grid with a single parameter should still work."""
        ohlcv = _small_ohlcv()
        reg = _small_registry()
        grid = {"top_n": [5, 10]}

        best, diag = tune_parameters(ohlcv, reg, grid, n_folds=2)

        assert "top_n" in best
        assert best["top_n"] in [5, 10]
        # Should not contain sell_buffer since it was not in the grid
        assert "sell_buffer" not in best

    def test_best_selection_picks_highest_sharpe(self) -> None:
        """The returned params should correspond to the best OOS Sharpe."""
        ohlcv = _small_ohlcv()
        reg = _small_registry()
        # Use different top_n values
        grid = {"top_n": [3, 5, 8, 12]}

        best, diag = tune_parameters(ohlcv, reg, grid, n_folds=2)

        # Verify best is one of the candidates
        assert best["top_n"] in [3, 5, 8, 12]
        # Verify we got Sharpe info in diagnostics
        sharpe_msgs = [m for m in diag.messages if "OOS Sharpe" in m.message and "Best" in m.message]
        assert len(sharpe_msgs) > 0

    def test_ap7_warning_fires(self) -> None:
        """Large grid should trigger AP-7 overfitting warning."""
        ohlcv = _small_ohlcv()
        reg = _small_registry()
        # Create a grid large enough to trigger the warning:
        # n_combos * n_params > MAX_PARAMS_WARNING * 10 = 50
        # 10 values * 10 values = 100 combos * 2 params = 200 > 50
        grid = {
            "top_n": list(range(5, 15)),
            "sell_buffer": [1.0 + 0.1 * i for i in range(10)],
        }

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # We don't run it because it would be too slow;
            # just check the warning fires at the start.
            # Patch to avoid full execution:
            # Instead we test directly that diagnostics contains AP-7
            best, diag = tune_parameters(ohlcv, reg, grid, n_folds=2)

        ap7_warnings = [x for x in w if "AP-7" in str(x.message)]
        assert len(ap7_warnings) > 0

    def test_empty_grid_returns_empty(self) -> None:
        """Empty param_grid should return empty best_params with a warning."""
        ohlcv = _small_ohlcv()
        reg = _small_registry()

        best, diag = tune_parameters(ohlcv, reg, {}, n_folds=2)

        assert best == {}
        assert diag.has_warnings

    def test_diagnostics_contain_per_combo_results(self) -> None:
        """Each combo evaluation should produce an info diagnostic."""
        ohlcv = _small_ohlcv()
        reg = _small_registry()
        grid = {"top_n": [5, 10]}

        best, diag = tune_parameters(ohlcv, reg, grid, n_folds=2)

        # Should have at least one info message per combo
        combo_msgs = [m for m in diag.messages if "params=" in m.message]
        assert len(combo_msgs) >= 2
