"""Cross-sectional normalization: rank-percentile, winsorize, z-score.

All functions return (result, Diagnostics) tuples.  The primary method is
rank-percentile mapping to [0, 1] which is used for the FeatureMatrix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics

_MOD = "normalize"


def rank_percentile(series: pd.Series) -> tuple[pd.Series, Diagnostics]:
    """Cross-sectional rank-percentile mapping to [0, 1].

    Ties are handled with the *average* method.  Special cases:

    - All NaN → return all NaN with a WARNING diagnostic.
    - Single non-NaN value → return 0.5 with an INFO diagnostic.
    - Output is guaranteed in [0, 1] for all non-NaN values.

    Parameters
    ----------
    series : pd.Series
        Raw feature values for a single cross-section.

    Returns
    -------
    (pd.Series, Diagnostics)
    """
    src = f"{_MOD}.rank_percentile"
    diag = Diagnostics()

    non_nan = series.dropna()

    if len(non_nan) == 0:
        diag.warning(src, "All values are NaN — returning all-NaN series")
        return pd.Series(np.nan, index=series.index, dtype=float), diag

    if len(non_nan) == 1:
        diag.info(src, "Single non-NaN value — returning 0.5")
        result = pd.Series(np.nan, index=series.index, dtype=float)
        result.loc[non_nan.index] = 0.5
        return result, diag

    # Rank using average tie-breaking, then scale to [0, 1]
    n = len(non_nan)
    ranks = non_nan.rank(method="average")
    # Map rank 1..n to (rank - 1) / (n - 1), giving exact 0.0 and 1.0
    scaled = (ranks - 1) / (n - 1)

    result = pd.Series(np.nan, index=series.index, dtype=float)
    result.loc[scaled.index] = scaled.values

    diag.info(src, f"Ranked {n} values to [0, 1]", n_ranked=n)
    return result, diag


def winsorize(
    series: pd.Series,
    lower: float = 0.01,
    upper: float = 0.99,
) -> tuple[pd.Series, Diagnostics]:
    """Clip values at the given quantile boundaries.

    Parameters
    ----------
    series : pd.Series
        Raw feature values.
    lower : float
        Lower quantile (default 1st percentile).
    upper : float
        Upper quantile (default 99th percentile).

    Returns
    -------
    (pd.Series, Diagnostics)
    """
    src = f"{_MOD}.winsorize"
    diag = Diagnostics()

    non_nan = series.dropna()
    if len(non_nan) == 0:
        diag.warning(src, "All values are NaN — returning unchanged")
        return series.copy(), diag

    low_val = float(non_nan.quantile(lower))
    high_val = float(non_nan.quantile(upper))

    result = series.copy()
    clipped_low = (result < low_val) & result.notna()
    clipped_high = (result > high_val) & result.notna()
    result = result.clip(lower=low_val, upper=high_val)

    n_clipped = int(clipped_low.sum() + clipped_high.sum())
    diag.info(
        src,
        f"Winsorized {n_clipped} values at [{lower}, {upper}] quantiles",
        n_clipped=n_clipped,
        low_val=low_val,
        high_val=high_val,
    )
    return result, diag


def normalize_cross_section(
    series: pd.Series,
    *,
    winsor_lower: float = 0.01,
    winsor_upper: float = 0.99,
) -> tuple[pd.Series, Diagnostics]:
    """Canonical cross-sectional normalization: winsorize → rank_percentile.

    This is the single entry point consumed by every normalizing caller
    in both the research pipeline (`nyse_core.research_pipeline`) and the
    live pipeline (`nyse_ats.pipeline`).  Two-stage chain:

      1. Winsorize at `[winsor_lower, winsor_upper]` quantiles to cap
         tail influence before ranking.
      2. Rank-percentile map to [0, 1] so the downstream model sees a
         uniform cross-sectional scale regardless of raw units.

    Diagnostics from both stages are merged and returned so the caller
    keeps a full audit trail without owning the stage sequencing.

    Parameters
    ----------
    series : pd.Series
        Raw cross-sectional feature values for a single date.
    winsor_lower, winsor_upper : float
        Quantile bounds passed to `winsorize`.  Defaults mirror the
        research pipeline (1st/99th percentile).

    Returns
    -------
    (pd.Series, Diagnostics)
        The rank-percentile result on [0, 1] (NaN preserved) plus a
        merged diagnostics bag covering both stages.
    """
    diag = Diagnostics()

    winsorized, w_diag = winsorize(series, lower=winsor_lower, upper=winsor_upper)
    diag.merge(w_diag)

    ranked, r_diag = rank_percentile(winsorized)
    diag.merge(r_diag)

    return ranked, diag


def z_score(series: pd.Series) -> tuple[pd.Series, Diagnostics]:
    """Cross-sectional z-score normalization (mean=0, std=1).

    Parameters
    ----------
    series : pd.Series
        Raw feature values.

    Returns
    -------
    (pd.Series, Diagnostics)
    """
    src = f"{_MOD}.z_score"
    diag = Diagnostics()

    non_nan = series.dropna()
    if len(non_nan) == 0:
        diag.warning(src, "All values are NaN — returning all-NaN series")
        return pd.Series(np.nan, index=series.index, dtype=float), diag

    mean = float(non_nan.mean())
    std = float(non_nan.std(ddof=1))

    if std == 0.0:
        diag.info(src, "Zero variance — returning all zeros for non-NaN values")
        result = pd.Series(np.nan, index=series.index, dtype=float)
        result.loc[non_nan.index] = 0.0
        return result, diag

    result = pd.Series(np.nan, index=series.index, dtype=float)
    z_vals = (non_nan - mean) / std
    result.loc[z_vals.index] = z_vals.values

    diag.info(src, f"Z-scored {len(non_nan)} values (mean={mean:.4f}, std={std:.4f})")
    return result, diag
