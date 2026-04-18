"""Rigorous walk-forward backtesting engine.

Orchestrates the full OOS backtest pipeline: for each CV fold, trains a model,
generates predictions, allocates weights, applies risk limits, computes net
returns, and aggregates across folds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nyse_core.contracts import BacktestResult, Diagnostics, reject_holdout_dates
from nyse_core.metrics import (
    cagr,
    cost_drag,
    max_drawdown,
    sharpe_ratio,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from nyse_core.cv import PurgedWalkForwardCV


def run_walk_forward_backtest(
    feature_matrix: pd.DataFrame,
    returns: pd.Series,
    cv: PurgedWalkForwardCV,
    model_factory: Callable,
    allocator_fn: Callable,
    risk_fn: Callable,
    cost_fn: Callable,
) -> tuple[BacktestResult, Diagnostics]:
    """Execute a rigorous walk-forward backtest.

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        Rows = dates, columns = features. Must be date-aligned with *returns*.
    returns : pd.Series
        Daily forward returns, same index as *feature_matrix*.
    cv : PurgedWalkForwardCV
        Cross-validator providing purged expanding-window folds.
    model_factory : Callable
        ``model_factory()`` returns a CombinationModel with ``.fit(X, y)``,
        ``.predict(X)``, and ``.get_feature_importance()`` methods.
    allocator_fn : Callable
        ``allocator_fn(predictions: np.ndarray) -> np.ndarray`` maps
        raw predictions to portfolio weights (summing to 1).
    risk_fn : Callable
        ``risk_fn(weights: np.ndarray) -> np.ndarray`` applies risk
        constraints to proposed weights.
    cost_fn : Callable
        ``cost_fn(weights_prev: np.ndarray, weights_new: np.ndarray) -> float``
        computes transaction cost for the weight change.

    Returns
    -------
    tuple[BacktestResult, Diagnostics]
        (backtest_result, diagnostics).
    """
    diag = Diagnostics()
    src = "backtest.run_walk_forward_backtest"

    dates = feature_matrix.index
    if not isinstance(dates, pd.DatetimeIndex):
        dates = pd.DatetimeIndex(dates)

    # Iron rule 1: walk-forward backtest must never touch holdout-era observations.
    reject_holdout_dates(dates, source=src)

    all_oos_returns: list[pd.Series] = []
    all_oos_costs: list[pd.Series] = []
    per_fold_sharpe: list[float] = []
    fold_count = 0
    last_model = None

    for fold_idx, (train_idx, test_idx) in enumerate(cv.split(dates)):
        X_train = feature_matrix.iloc[train_idx]
        y_train = returns.iloc[train_idx]
        X_test = feature_matrix.iloc[test_idx]
        y_test = returns.iloc[test_idx]
        test_dates = dates[test_idx]

        # Train — model.fit() returns Diagnostics
        model = model_factory()
        fit_diag = model.fit(X_train, y_train)
        diag.merge(fit_diag)
        if fit_diag.has_errors:
            diag.warning(
                src,
                f"Fold {fold_idx}: model fit had errors, skipping fold",
                fold=fold_idx,
            )
            continue

        # Predict — model.predict() returns (pd.Series, Diagnostics)
        predictions, pred_diag = model.predict(X_test)
        diag.merge(pred_diag)
        last_model = model
        fold_count += 1

        # Allocate + risk
        weights_prev: np.ndarray | None = None
        fold_returns: list[float] = []
        fold_costs: list[float] = []

        for t in range(len(predictions)):
            raw_weights = allocator_fn(predictions.values[t : t + 1])
            constrained_weights = risk_fn(raw_weights)
            if weights_prev is None:
                weights_prev = np.zeros_like(constrained_weights)

            cost = cost_fn(weights_prev, constrained_weights)
            net_ret = float(constrained_weights.sum() * y_test.values[t] - cost)

            fold_returns.append(net_ret)
            fold_costs.append(cost)
            weights_prev = constrained_weights

        fold_ret_series = pd.Series(fold_returns, index=test_dates, name="returns")
        fold_cost_series = pd.Series(fold_costs, index=test_dates, name="costs")

        all_oos_returns.append(fold_ret_series)
        all_oos_costs.append(fold_cost_series)
        fold_sharpe, _ = sharpe_ratio(fold_ret_series)
        per_fold_sharpe.append(fold_sharpe)

        diag.info(
            src,
            f"Fold {fold_idx}: train={len(train_idx)}, test={len(test_idx)}, "
            f"Sharpe={per_fold_sharpe[-1]:.3f}",
            fold=fold_idx,
        )

    if fold_count == 0:
        diag.error(src, "No valid folds produced by CV splitter.")
        empty_result = BacktestResult(
            daily_returns=pd.Series(dtype=float),
            oos_sharpe=0.0,
            oos_cagr=0.0,
            max_drawdown=0.0,
            annual_turnover=0.0,
            cost_drag_pct=0.0,
            per_fold_sharpe=[],
            per_factor_contribution={},
        )
        return empty_result, diag

    # Aggregate OOS results
    combined_returns = pd.concat(all_oos_returns).sort_index()
    combined_costs = pd.concat(all_oos_costs).sort_index()

    # Compute aggregate metrics
    oos_sharpe_val, _ = sharpe_ratio(combined_returns)
    oos_cagr_val, _ = cagr(combined_returns)
    oos_mdd, _ = max_drawdown(combined_returns)
    oos_cost_drag, _ = cost_drag(combined_returns + combined_costs, combined_costs)

    # Turnover approximation: use costs as proxy
    oos_turnover = float(combined_costs.abs().sum() / max(len(combined_returns) / 252, 1e-9))

    # Per-factor contribution via CombinationModel protocol method
    per_factor_contrib: dict[str, float] = {}
    if last_model is not None:
        per_factor_contrib = last_model.get_feature_importance()

    result = BacktestResult(
        daily_returns=combined_returns,
        oos_sharpe=oos_sharpe_val,
        oos_cagr=oos_cagr_val,
        max_drawdown=oos_mdd,
        annual_turnover=oos_turnover,
        cost_drag_pct=oos_cost_drag,
        per_fold_sharpe=per_fold_sharpe,
        per_factor_contribution=per_factor_contrib,
    )

    diag.info(
        src,
        f"Backtest complete: {fold_count} folds, OOS Sharpe={oos_sharpe_val:.3f}, "
        f"CAGR={oos_cagr_val:.4f}, MaxDD={oos_mdd:.4f}",
    )

    return result, diag
