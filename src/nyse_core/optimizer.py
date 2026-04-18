"""Walk-forward parameter tuner for the ResearchPipeline.

Grid-searches over portfolio construction parameters (top_n, sell_buffer, etc.)
using walk-forward OOS Sharpe as the objective. Pure logic -- no I/O.
"""

from __future__ import annotations

import itertools
import warnings
from typing import TYPE_CHECKING, Any

from nyse_core.contracts import Diagnostics
from nyse_core.research_pipeline import ResearchPipeline
from nyse_core.schema import MAX_PARAMS_WARNING

if TYPE_CHECKING:
    import pandas as pd

    from nyse_core.features.registry import FactorRegistry

_SRC = "optimizer"


def tune_parameters(
    ohlcv: pd.DataFrame,
    registry: FactorRegistry,
    param_grid: dict[str, list[Any]],
    n_folds: int = 3,
    model_type: str = "ridge",
    model_kwargs: dict | None = None,
    fundamentals: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], Diagnostics]:
    """Grid-search walk-forward OOS Sharpe over parameter combinations.

    Parameters
    ----------
    ohlcv : pd.DataFrame
        OHLCV panel (date, symbol, open, high, low, close, volume).
    registry : FactorRegistry
        Factor registry to use for feature computation.
    param_grid : dict[str, list[Any]]
        Parameter name -> list of candidate values.
        Recognised keys: ``top_n``, ``sell_buffer``.
    n_folds : int
        Number of walk-forward CV folds per evaluation.
    model_type : str
        Combination model type (default ``"ridge"``).
    model_kwargs : dict | None
        Extra kwargs passed to the model constructor.
    fundamentals : pd.DataFrame | None
        Optional fundamentals data.

    Returns
    -------
    tuple[dict[str, Any], Diagnostics]
        (best_params dict, diagnostics).  If the grid is empty the returned
        params dict will also be empty.
    """
    diag = Diagnostics()
    src = f"{_SRC}.tune_parameters"

    if not param_grid:
        diag.warning(src, "Empty param_grid -- returning empty best_params.")
        return {}, diag

    # Enumerate all combinations
    keys = sorted(param_grid.keys())
    values = [param_grid[k] for k in keys]
    combos = list(itertools.product(*values))

    n_combos = len(combos)
    n_params = len(keys)

    # AP-7 check: warn if combinatorial explosion risk
    if n_combos * n_params > MAX_PARAMS_WARNING * 10:
        msg = (
            f"AP-7 warning: {n_combos} combinations x {n_params} params "
            f"= {n_combos * n_params} evaluations (threshold={MAX_PARAMS_WARNING * 10})."
        )
        warnings.warn(msg, UserWarning, stacklevel=2)
        diag.warning(src, msg)

    diag.info(
        src,
        f"Tuning {n_combos} parameter combinations over {n_folds} folds.",
        n_combos=n_combos,
        n_params=n_params,
    )

    best_sharpe = float("-inf")
    best_params: dict[str, Any] = {}

    for combo in combos:
        params = dict(zip(keys, combo, strict=False))

        top_n = params.get("top_n", 20)
        sell_buffer = params.get("sell_buffer", 1.5)

        pipeline = ResearchPipeline(
            registry=registry,
            model_type=model_type,
            model_kwargs=model_kwargs or {},
            top_n=top_n,
        )

        result, wf_diag = pipeline.run_walk_forward_validation(
            ohlcv,
            fundamentals=fundamentals,
            n_folds=n_folds,
            sell_buffer=sell_buffer,
        )
        diag.merge(wf_diag)

        oos = result.oos_sharpe
        diag.info(src, f"params={params} -> OOS Sharpe={oos:.4f}", **params)

        if oos > best_sharpe:
            best_sharpe = oos
            best_params = params

    diag.info(
        src,
        f"Best params: {best_params} with OOS Sharpe={best_sharpe:.4f}.",
        best_sharpe=best_sharpe,
    )
    return best_params, diag
