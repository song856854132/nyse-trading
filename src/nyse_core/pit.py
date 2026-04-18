"""Point-in-Time enforcement for feature availability.

Prevents look-ahead bias by enforcing publication lags and maximum data age.
FINRA short interest has an 11-day publication lag by convention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics, reject_holdout_dates
from nyse_core.schema import COL_DATE

if TYPE_CHECKING:
    from datetime import date

_SRC = "pit.enforce_pit_lags"


def enforce_pit_lags(
    data: pd.DataFrame,
    publication_lags: dict[str, int],
    as_of_date: date,
    max_age_days: int,
) -> tuple[pd.DataFrame, Diagnostics]:
    """Filter features by point-in-time availability.

    For each feature column in *data*, two checks are applied:

    1. **Publication lag** — a feature filed on ``feature_date`` is only available
       ``publication_lags[col]`` calendar days later.  If ``as_of_date`` is before
       the publication date, the value is set to NaN.
    2. **Max age** — if the feature is older than *max_age_days* from *as_of_date*,
       it is considered stale and set to NaN.

    Parameters
    ----------
    data : pd.DataFrame
        Must contain a ``date`` column representing the feature filing / observation date.
        All other columns (except ``date``) are treated as feature columns.
    publication_lags : dict[str, int]
        Mapping of column name → publication lag in calendar days.  Columns not present
        in this dict are assumed to have a lag of 0 (immediately available).
    as_of_date : date
        The "now" date for the PiT check.
    max_age_days : int
        Maximum allowed age in calendar days.  Features older than this are NaN'd.

    Returns
    -------
    (pd.DataFrame, Diagnostics)
    """
    # Iron rule 1: refuse to stamp PiT against holdout dates.
    # Note: only `as_of_date` is guarded; filing dates in the `data` frame
    # may legitimately lie in the future relative to as_of_date — the whole
    # point of PiT is to NaN them out cleanly.
    reject_holdout_dates(as_of_date, source=_SRC)

    diag = Diagnostics()
    result = data.copy()

    if COL_DATE not in result.columns:
        diag.error(_SRC, "DataFrame missing required 'date' column")
        return result, diag

    feature_cols = [c for c in result.columns if c != COL_DATE]
    if not feature_cols:
        diag.info(_SRC, "No feature columns to enforce")
        return result, diag

    as_of = pd.Timestamp(as_of_date)
    feature_dates = pd.to_datetime(result[COL_DATE])

    for col in feature_cols:
        lag_days = publication_lags.get(col, 0)
        available_date = feature_dates + pd.Timedelta(days=lag_days)

        # Reject future-dated features (publication date after as_of)
        future_mask = available_date > as_of
        n_future = int(future_mask.sum())
        if n_future > 0:
            result.loc[future_mask, col] = np.nan
            diag.warning(
                _SRC,
                f"NaN'd {n_future} future-dated values in '{col}' (pub_lag={lag_days}d)",
                column=col,
                count=n_future,
                reason="publication_lag",
            )

        # Reject stale features (older than max_age_days)
        age = (as_of - feature_dates).dt.days
        stale_mask = age > max_age_days
        # Don't double-count rows already NaN'd by future check
        stale_only = stale_mask & ~future_mask
        n_stale = int(stale_only.sum())
        if n_stale > 0:
            result.loc[stale_only, col] = np.nan
            diag.warning(
                _SRC,
                f"NaN'd {n_stale} stale values in '{col}' (max_age={max_age_days}d)",
                column=col,
                count=n_stale,
                reason="max_age",
            )

    total_nan = int(result[feature_cols].isna().sum().sum() - data[feature_cols].isna().sum().sum())
    diag.info(
        _SRC,
        f"PiT enforcement complete: {total_nan} values NaN'd across "
        f"{len(feature_cols)} features as of {as_of_date}",
    )
    return result, diag
