"""Earnings factor computations — Standardized Unexpected Earnings (SUE).

Accepts a fundamentals DataFrame with columns:
  symbol, filing_date, period_end, operating_profitability
and returns (pd.Series indexed by symbol, Diagnostics).

Sign conventions are documented but NOT applied here — the FactorRegistry
handles inversion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_SYMBOL

_MIN_QUARTERS: int = 4


def compute_earnings_surprise(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Standardized Unexpected Earnings (SUE).

    Proxy: sequential quarterly change in operating_profitability, standardized
    by the rolling standard deviation of those changes.

    SUE = (current_q_profitability - prior_q_profitability) / std(changes)

    Requires >= 4 quarters of history per symbol; otherwise returns NaN.

    Sign convention: POSITIVE (positive surprise = buy signal).
    """
    diag = Diagnostics()
    source = "earnings.compute_earnings_surprise"

    results: dict[str, float] = {}
    insufficient_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values("period_end")
        profitability = group_sorted["operating_profitability"].values

        if len(profitability) < _MIN_QUARTERS:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        # Sequential quarter-over-quarter changes in profitability
        changes = np.diff(profitability)

        std_changes = np.std(changes, ddof=1)

        if std_changes == 0 or np.isnan(std_changes):
            results[symbol] = np.nan
            continue

        # Most recent change (last quarter vs prior quarter)
        most_recent_change = changes[-1]
        sue = float(most_recent_change / std_changes)
        results[symbol] = sue

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient quarters "
            f"(< {_MIN_QUARTERS}) for earnings surprise; set to NaN.",
            insufficient_count=insufficient_count,
            min_required=_MIN_QUARTERS,
        )

    series = pd.Series(results, name="earnings_surprise")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional earnings surprise (SUE) computed.",
        n_symbols=len(results),
        n_valid=len(results) - insufficient_count,
    )
    return series, diag
