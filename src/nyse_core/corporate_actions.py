"""Corporate action adjustments — stock splits and pending action detection.

Adjusts historical price/volume data for splits and flags held stocks
with upcoming corporate actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL, COL_VOLUME

if TYPE_CHECKING:
    from datetime import date

    import pandas as pd

_SRC = "corporate_actions"


def adjust_for_splits(
    prices: pd.DataFrame,
    splits: pd.DataFrame,
) -> tuple[pd.DataFrame, Diagnostics]:
    """Adjust historical prices and volumes for stock splits.

    Parameters
    ----------
    prices : pd.DataFrame
        Columns must include ``date``, ``symbol``, ``close``, ``volume``.
    splits : pd.DataFrame
        Columns: ``date``, ``symbol``, ``ratio`` (e.g. 4.0 for a 4:1 split).

    Returns
    -------
    tuple[pd.DataFrame, Diagnostics]
        (adjusted_prices, diagnostics)
    """
    diag = Diagnostics()

    if splits.empty:
        diag.info(_SRC, "no splits to adjust")
        return prices.copy(), diag

    adjusted = prices.copy()

    for _, split_row in splits.iterrows():
        sym = split_row[COL_SYMBOL]
        split_date = split_row[COL_DATE]
        ratio = split_row["ratio"]

        if ratio <= 0:
            diag.error(_SRC, f"invalid split ratio for {sym}", ratio=ratio)
            continue

        # Mask: rows for this symbol BEFORE the split date
        mask = (adjusted[COL_SYMBOL] == sym) & (adjusted[COL_DATE] < split_date)
        count = mask.sum()

        if count == 0:
            diag.info(_SRC, f"no historical rows to adjust for {sym} split")
            continue

        adjusted.loc[mask, COL_CLOSE] = adjusted.loc[mask, COL_CLOSE] / ratio
        adjusted.loc[mask, COL_VOLUME] = adjusted.loc[mask, COL_VOLUME] * ratio

        diag.info(
            _SRC,
            f"adjusted {sym} for {ratio}:1 split on {split_date}",
            rows_adjusted=int(count),
            ratio=ratio,
        )

    return adjusted, diag


def detect_pending_actions(
    held_symbols: list[str],
    actions: pd.DataFrame,
    since: date,
) -> tuple[list[dict], Diagnostics]:
    """Detect upcoming corporate actions for held stocks.

    Parameters
    ----------
    held_symbols : list[str]
        Symbols currently held in the portfolio.
    actions : pd.DataFrame
        Columns: ``date``, ``symbol``, ``action_type``, plus any extras.
        ``date`` is the effective date of the action.
    since : date
        Start of the look-ahead window (inclusive). Actions from ``since``
        through "today" are flagged.

    Returns
    -------
    tuple[list[dict], Diagnostics]
        (list of action dicts, diagnostics)
    """
    diag = Diagnostics()

    if actions.empty:
        diag.info(_SRC, "no corporate actions in calendar")
        return [], diag

    held_set = set(held_symbols)

    # Filter: symbol in held_symbols AND date >= since
    mask = actions[COL_SYMBOL].isin(held_set) & (actions[COL_DATE] >= since)
    pending = actions.loc[mask]

    result: list[dict] = []
    for _, row in pending.iterrows():
        entry = row.to_dict()
        result.append(entry)

    if result:
        diag.warning(
            _SRC,
            f"found {len(result)} pending corporate action(s) for held stocks",
            symbols=list(pending[COL_SYMBOL].unique()),
        )
    else:
        diag.info(_SRC, "no pending corporate actions for held stocks")

    return result, diag
