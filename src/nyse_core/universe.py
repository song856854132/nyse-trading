"""S&P 500 historical reconstitution with Point-in-Time enforcement.

Builds the index membership as of any target date by replaying
ADD / REMOVE changes forward from an initial member list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_DATE, COL_SYMBOL

if TYPE_CHECKING:
    from datetime import date

_SRC = "universe.get_universe_at_date"

_COL_ACTION = "action"
_ACTION_ADD = "ADD"
_ACTION_REMOVE = "REMOVE"


def get_universe_at_date(
    constituency_changes: pd.DataFrame,
    target_date: date,
    initial_members: list[str],
) -> tuple[list[str], Diagnostics]:
    """Return S&P 500 members as of *target_date*, PiT-enforced.

    Parameters
    ----------
    constituency_changes : pd.DataFrame
        Must contain columns ``date``, ``symbol``, ``action``.
        ``action`` is either ``"ADD"`` or ``"REMOVE"``.
    target_date : date
        The date for which to compute the membership.
    initial_members : list[str]
        Starting member list (e.g., the earliest known composition).

    Returns
    -------
    (list[str], Diagnostics)
        Sorted list of member symbols and diagnostics.
    """
    diag = Diagnostics()
    members: set[str] = set(initial_members)

    required_cols = {COL_DATE, COL_SYMBOL, _COL_ACTION}
    actual_cols = set(constituency_changes.columns)
    missing = required_cols - actual_cols
    if missing:
        diag.error(_SRC, f"Missing required columns: {missing}")
        return sorted(members), diag

    changes = constituency_changes.copy()
    changes[COL_DATE] = pd.to_datetime(changes[COL_DATE]).dt.date

    # PiT enforcement: only apply changes on or before target_date
    past_changes = changes[changes[COL_DATE] <= target_date].sort_values(COL_DATE)
    future_count = len(changes) - len(past_changes)
    if future_count > 0:
        diag.info(
            _SRC,
            f"Excluded {future_count} future changes after {target_date}",
            future_count=future_count,
        )

    adds = 0
    removes = 0
    for _, row in past_changes.iterrows():
        symbol = row[COL_SYMBOL]
        action = row[_COL_ACTION]

        if action == _ACTION_ADD:
            members.add(symbol)
            adds += 1
        elif action == _ACTION_REMOVE:
            members.discard(symbol)
            removes += 1
        else:
            diag.warning(
                _SRC,
                f"Unknown action '{action}' for symbol '{symbol}' — skipped",
                symbol=symbol,
                action=action,
            )

    diag.info(
        _SRC,
        f"Universe at {target_date}: {len(members)} members "
        f"(+{adds} adds, -{removes} removes from initial {len(initial_members)})",
        adds=adds,
        removes=removes,
        universe_size=len(members),
    )
    return sorted(members), diag
