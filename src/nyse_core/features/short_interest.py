"""Short interest factor computations — cross-sectional FINRA-style signals.

All functions accept a multi-stock DataFrame with FINRA short interest fields
and return (pd.Series indexed by symbol, Diagnostics).

Sign conventions are documented but NOT applied here — the FactorRegistry
handles inversion.

Reference: Short interest is one of the 5 robust factors surviving
post-publication (Asquith et al., 2005; Dechow et al., 2001).
FINRA reports bi-monthly with ~11-day publication lag.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_DATE, COL_SYMBOL

# ── Column Names (FINRA short interest data) ────────────────────────────────
COL_SHORT_INTEREST: str = "short_interest"
COL_SHARES_OUTSTANDING: str = "shares_outstanding"
COL_AVG_DAILY_VOLUME: str = "avg_daily_volume"

# ── Constants ────────────────────────────────────────────────────────────────
_MIN_PERIODS_FOR_CHANGE: int = 2
_FINRA_PUBLICATION_LAG: int = 11  # calendar days; FINRA publishes ~11 days after settlement


def compute_short_ratio(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Short ratio (days to cover): short_interest / avg_daily_volume.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Takes the MOST RECENT observation per symbol.

    Sign convention: NEGATIVE (high short ratio = bearish = sell signal).
    Registry will negate so higher = buy.

    Handles: missing short_interest or avg_daily_volume -> NaN.
             avg_daily_volume == 0 -> NaN (avoid division by zero).
    """
    diag = Diagnostics()
    source = "short_interest.compute_short_ratio"

    required_cols = {COL_SYMBOL, COL_DATE, COL_SHORT_INTEREST, COL_AVG_DAILY_VOLUME}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="short_ratio"), diag

    # PiT: enforce FINRA publication lag (~11 calendar days).
    # Only apply when data spans enough time; single-period data is assumed
    # to have been pre-filtered for PiT by the caller.
    dates_ts = pd.to_datetime(data[COL_DATE])
    date_span = (dates_ts.max() - dates_ts.min()).days
    if date_span >= _FINRA_PUBLICATION_LAG:
        cutoff = dates_ts.max() - pd.Timedelta(days=_FINRA_PUBLICATION_LAG)
        pit_data = data[dates_ts <= cutoff]
        if pit_data.empty:
            diag.warning(source, "No published observations after FINRA lag filter.")
            return pd.Series(dtype=float, name="short_ratio"), diag
    else:
        pit_data = data

    results: dict[str, float] = {}
    missing_count = 0
    zero_vol_count = 0

    for symbol, group in pit_data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        latest = group_sorted.iloc[-1]

        si = latest[COL_SHORT_INTEREST]
        adv = latest[COL_AVG_DAILY_VOLUME]

        if pd.isna(si) or pd.isna(adv):
            results[symbol] = np.nan
            missing_count += 1
            continue

        if adv == 0:
            results[symbol] = np.nan
            zero_vol_count += 1
            continue

        results[symbol] = float(si / adv)

    if missing_count > 0:
        diag.warning(
            source,
            f"{missing_count} symbol(s) had missing short_interest or avg_daily_volume; set to NaN.",
            missing_count=missing_count,
        )
    if zero_vol_count > 0:
        diag.warning(
            source,
            f"{zero_vol_count} symbol(s) had zero avg_daily_volume; set to NaN.",
            zero_vol_count=zero_vol_count,
        )

    series = pd.Series(results, name="short_ratio")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional short ratio computed.",
        n_symbols=len(results),
        n_valid=len(results) - missing_count - zero_vol_count,
    )
    return series, diag


def compute_short_interest_pct(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Short interest as percentage of shares outstanding.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Takes the MOST RECENT observation per symbol.

    Sign convention: NEGATIVE (high short % = bearish).
    Registry will negate so higher = buy.

    Handles: missing short_interest or shares_outstanding -> NaN.
             shares_outstanding == 0 -> NaN (avoid division by zero).
    """
    diag = Diagnostics()
    source = "short_interest.compute_short_interest_pct"

    required_cols = {COL_SYMBOL, COL_DATE, COL_SHORT_INTEREST, COL_SHARES_OUTSTANDING}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="short_interest_pct"), diag

    # PiT: enforce FINRA publication lag (~11 calendar days).
    dates_ts = pd.to_datetime(data[COL_DATE])
    date_span = (dates_ts.max() - dates_ts.min()).days
    if date_span >= _FINRA_PUBLICATION_LAG:
        cutoff = dates_ts.max() - pd.Timedelta(days=_FINRA_PUBLICATION_LAG)
        pit_data = data[dates_ts <= cutoff]
        if pit_data.empty:
            diag.warning(source, "No published observations after FINRA lag filter.")
            return pd.Series(dtype=float, name="short_interest_pct"), diag
    else:
        pit_data = data

    results: dict[str, float] = {}
    missing_count = 0

    for symbol, group in pit_data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        latest = group_sorted.iloc[-1]

        si = latest[COL_SHORT_INTEREST]
        so = latest[COL_SHARES_OUTSTANDING]

        if pd.isna(si) or pd.isna(so) or so == 0:
            results[symbol] = np.nan
            missing_count += 1
            continue

        results[symbol] = float(si / so)

    if missing_count > 0:
        diag.warning(
            source,
            f"{missing_count} symbol(s) had missing or zero shares_outstanding; set to NaN.",
            missing_count=missing_count,
        )

    series = pd.Series(results, name="short_interest_pct")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional short interest % computed.",
        n_symbols=len(results),
        n_valid=len(results) - missing_count,
    )
    return series, diag


def compute_short_interest_change(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Change in short interest from prior period: (current - previous) / previous.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Requires at least 2 periods of data per symbol.

    Sign convention: NEGATIVE (increasing short interest = bearish).
    Registry will negate so higher = buy.

    Handles: insufficient data (< 2 periods) -> NaN.
             previous short_interest == 0 -> NaN (avoid division by zero).
    """
    diag = Diagnostics()
    source = "short_interest.compute_short_interest_change"

    required_cols = {COL_SYMBOL, COL_DATE, COL_SHORT_INTEREST}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="short_interest_change"), diag

    # PiT: enforce FINRA publication lag (~11 calendar days).
    dates_ts = pd.to_datetime(data[COL_DATE])
    date_span = (dates_ts.max() - dates_ts.min()).days
    if date_span >= _FINRA_PUBLICATION_LAG:
        cutoff = dates_ts.max() - pd.Timedelta(days=_FINRA_PUBLICATION_LAG)
        pit_data = data[dates_ts <= cutoff]
        if pit_data.empty:
            diag.warning(source, "No published observations after FINRA lag filter.")
            return pd.Series(dtype=float, name="short_interest_change"), diag
    else:
        pit_data = data

    results: dict[str, float] = {}
    insufficient_count = 0

    for symbol, group in pit_data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)

        if len(group_sorted) < _MIN_PERIODS_FOR_CHANGE:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        current_si = group_sorted[COL_SHORT_INTEREST].iloc[-1]
        previous_si = group_sorted[COL_SHORT_INTEREST].iloc[-2]

        if pd.isna(current_si) or pd.isna(previous_si) or previous_si == 0:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        results[symbol] = float((current_si - previous_si) / previous_si)

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient data "
            f"(< {_MIN_PERIODS_FOR_CHANGE} periods) or missing values; set to NaN.",
            insufficient_count=insufficient_count,
            min_periods=_MIN_PERIODS_FOR_CHANGE,
        )

    series = pd.Series(results, name="short_interest_change")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional short interest change computed.",
        n_symbols=len(results),
        n_valid=len(results) - insufficient_count,
    )
    return series, diag
