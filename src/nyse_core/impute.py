"""Cross-sectional NaN imputation (Codex finding #6).

For each date cross-section:
  - Features with <max_missing_pct missing: impute with cross-sectional median.
  - Features with >=max_missing_pct missing: DROP (set entire column to NaN for that date).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_DATE

if TYPE_CHECKING:
    import pandas as pd

_SRC = "impute.cross_sectional_impute"


def cross_sectional_impute(
    features: pd.DataFrame,
    max_missing_pct: float = 0.30,
) -> tuple[pd.DataFrame, Diagnostics]:
    """Impute missing values cross-sectionally per date.

    Parameters
    ----------
    features : pd.DataFrame
        Must contain a ``date`` column.  All other columns are treated as features.
    max_missing_pct : float
        Threshold (inclusive) for dropping a feature on a given date.
        Features with missing fraction >= this value are set to NaN for
        that entire date cross-section rather than imputed.

    Returns
    -------
    (pd.DataFrame, Diagnostics)
    """
    diag = Diagnostics()
    result = features.copy()

    if COL_DATE not in result.columns:
        diag.error(_SRC, "DataFrame missing required 'date' column")
        return result, diag

    feature_cols = [c for c in result.columns if c != COL_DATE]
    if not feature_cols:
        diag.info(_SRC, "No feature columns to impute")
        return result, diag

    total_imputed = 0
    total_dropped: dict[str, int] = {}  # col -> count of dates dropped

    dates = result[COL_DATE].unique()
    for dt in dates:
        mask = result[COL_DATE] == dt
        cross_section = result.loc[mask, feature_cols]
        n_rows = len(cross_section)

        if n_rows == 0:
            continue

        for col in feature_cols:
            n_missing = int(cross_section[col].isna().sum())
            missing_pct = n_missing / n_rows

            if missing_pct >= max_missing_pct:
                # Too many missing — drop the feature for this date
                result.loc[mask, col] = np.nan
                total_dropped[col] = total_dropped.get(col, 0) + 1
            elif n_missing > 0:
                # Impute with cross-sectional median
                median_val = cross_section[col].median()
                fill_mask = mask & result[col].isna()
                result.loc[fill_mask, col] = median_val
                total_imputed += n_missing

    if total_dropped:
        for col, count in total_dropped.items():
            diag.warning(
                _SRC,
                f"Dropped feature '{col}' on {count} date(s) (>= {max_missing_pct:.0%} missing)",
                column=col,
                dates_dropped=count,
            )

    diag.info(
        _SRC,
        f"Imputed {total_imputed} values with cross-sectional median; "
        f"dropped {len(total_dropped)} feature(s) on some dates",
        total_imputed=total_imputed,
        features_dropped=list(total_dropped.keys()),
    )
    return result, diag
