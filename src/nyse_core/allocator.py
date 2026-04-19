"""Top-N selection with sell buffer and equal-weight allocation.

Implements Carver's sell-buffer logic: existing holdings enjoy a wider
threshold before being dropped, reducing unnecessary turnover.
"""

from __future__ import annotations

import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import BEAR_EXPOSURE, BULL_EXPOSURE, DEFAULT_SELL_BUFFER, DEFAULT_TOP_N, RegimeState

_SRC = "allocator"


def select_top_n(
    scores: pd.Series,
    n: int = DEFAULT_TOP_N,
    current_holdings: set[str] | None = None,
    sell_buffer: float = DEFAULT_SELL_BUFFER,
) -> tuple[list[str], Diagnostics]:
    """Select top-N stocks with a sell buffer for existing holdings.

    Parameters
    ----------
    scores : pd.Series
        Index = symbol, values = composite score (higher is better).
    n : int
        Number of target positions.
    current_holdings : set[str] | None
        Symbols currently held (if any).
    sell_buffer : float
        Multiplier for exit threshold.  Existing holdings only exit
        if they fall below rank ``n * sell_buffer``.

    Returns
    -------
    tuple[list[str], Diagnostics]
        (selected symbols, diagnostics)
    """
    diag = Diagnostics()

    if scores.empty:
        diag.warning(_SRC, "empty scores series — returning empty selection")
        return [], diag

    if scores.isna().all():
        diag.warning(_SRC, "all scores are NaN — returning empty selection")
        return [], diag

    universe_size = len(scores)
    if n > universe_size:
        diag.warning(
            _SRC,
            "top_n exceeds universe size; selecting all available",
            top_n=n,
            universe_size=universe_size,
        )

    if current_holdings is None:
        current_holdings = set()

    # Rank: lower rank = better score.  Ties broken by:
    # 1. prefer currently held stocks (rank them higher)
    # 2. then alphabetical by symbol (deterministic)
    is_held = scores.index.isin(current_holdings).astype(int)
    # Build a sort frame: score descending, held descending, symbol ascending
    sort_frame = pd.DataFrame(
        {
            "score": scores,
            "held": is_held,
            "symbol": scores.index,
        }
    )
    sort_frame = sort_frame.sort_values(
        by=["score", "held", "symbol"],
        ascending=[False, False, True],
    )
    ranked_symbols = list(sort_frame["symbol"])

    # Exit threshold — existing holdings survive until this rank
    exit_rank = int(n * sell_buffer)

    selected: list[str] = []

    # Retain currently held stocks that are within exit_rank
    for sym in ranked_symbols[:exit_rank]:
        if sym in current_holdings and len(selected) < n:
            selected.append(sym)

    # Fill remaining slots from top-ranked non-held stocks
    for sym in ranked_symbols:
        if len(selected) >= n:
            break
        if sym not in selected:
            selected.append(sym)

    # Clamp to available universe
    selected = selected[: min(n, universe_size)]

    diag.info(
        _SRC,
        "selection complete",
        selected_count=len(selected),
        retained=len([s for s in selected if s in current_holdings]),
        new_entries=len([s for s in selected if s not in current_holdings]),
    )
    return selected, diag


def equal_weight(
    selected: list[str],
) -> tuple[dict[str, float], Diagnostics]:
    """Assign equal weight to each selected stock.

    Parameters
    ----------
    selected : list[str]
        List of selected symbols.

    Returns
    -------
    tuple[dict[str, float], Diagnostics]
        ({symbol: weight}, diagnostics)
    """
    diag = Diagnostics()

    if not selected:
        diag.warning(_SRC, "empty selection — returning empty weights")
        return {}, diag

    w = 1.0 / len(selected)
    weights = {sym: w for sym in selected}

    diag.info(_SRC, "equal weight assigned", count=len(selected), weight=round(w, 6))
    return weights, diag


def apply_regime_scaling(
    weights: dict[str, float],
    regime: RegimeState,
    bull_exposure: float = BULL_EXPOSURE,
    bear_exposure: float = BEAR_EXPOSURE,
) -> tuple[dict[str, float], Diagnostics]:
    """Scale a normalized weight dict by the regime's exposure cap.

    Companion to risk.apply_regime_overlay — that function operates on a scalar
    exposure given raw SPY/SMA200 inputs; this one operates on an already-computed
    weight dict given an already-classified RegimeState. Used by the portfolio
    construction path where weights are finalized before regime application.

    Relative proportions are preserved: every weight is multiplied by the same
    scaling factor (bull_exposure for BULL, bear_exposure for BEAR). All weights
    remain non-negative as long as inputs are non-negative.
    """
    diag = Diagnostics()

    target = bull_exposure if regime == RegimeState.BULL else bear_exposure
    scaled = {sym: w * target for sym, w in weights.items()}

    diag.info(
        _SRC,
        f"regime scaling applied: {regime.value}",
        regime=regime.value,
        target_exposure=round(target, 6),
        original_total=round(sum(weights.values()), 6),
        scaled_total=round(sum(scaled.values()), 6),
        n_positions=len(weights),
    )
    return scaled, diag
