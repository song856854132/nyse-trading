"""Market microstructure / sentiment factor computations.

All functions accept a multi-stock DataFrame and return
(pd.Series indexed by symbol, Diagnostics).

Sign conventions are documented but NOT applied here — the FactorRegistry
handles inversion.

References:
- EWMAC: Carver (2015), recommended 8/32 span pair for trend-following.
  Cross-sectional application for stock selection (not time-series portfolio).
- Put/call ratio: default bearish interpretation (contrarian view exists
  but not used as default).
- Volume momentum: captures unusual trading activity relative to baseline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL, COL_VOLUME

# ── Column Names (options data) ──────────────────────────────────────────────
COL_PUT_VOLUME: str = "put_volume"
COL_CALL_VOLUME: str = "call_volume"

# ── Constants ────────────────────────────────────────────────────────────────
_VOL_MOM_FAST: int = 5
_VOL_MOM_SLOW: int = 20

_EWMAC_FAST_SPAN: int = 8
_EWMAC_SLOW_SPAN: int = 32
_EWMAC_VOL_WINDOW: int = 20  # lookback for realized vol normalization


def compute_put_call_ratio(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Put/call volume ratio: put_volume / call_volume.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Takes the MOST RECENT observation per symbol.

    Sign convention: NEGATIVE (high put/call = bearish).
    Registry will negate so higher = buy.

    Handles: call_volume == 0 -> NaN (avoid division by zero).
             missing put_volume or call_volume -> NaN.
    """
    diag = Diagnostics()
    source = "sentiment.compute_put_call_ratio"

    required_cols = {COL_SYMBOL, COL_DATE, COL_PUT_VOLUME, COL_CALL_VOLUME}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="put_call_ratio"), diag

    results: dict[str, float] = {}
    zero_call_count = 0
    missing_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        latest = group_sorted.iloc[-1]

        put_vol = latest[COL_PUT_VOLUME]
        call_vol = latest[COL_CALL_VOLUME]

        if pd.isna(put_vol) or pd.isna(call_vol):
            results[symbol] = np.nan
            missing_count += 1
            continue

        if call_vol == 0:
            results[symbol] = np.nan
            zero_call_count += 1
            continue

        results[symbol] = float(put_vol / call_vol)

    if zero_call_count > 0:
        diag.warning(
            source,
            f"{zero_call_count} symbol(s) had zero call_volume; set to NaN.",
            zero_call_count=zero_call_count,
        )
    if missing_count > 0:
        diag.warning(
            source,
            f"{missing_count} symbol(s) had missing options data; set to NaN.",
            missing_count=missing_count,
        )

    series = pd.Series(results, name="put_call_ratio")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional put/call ratio computed.",
        n_symbols=len(results),
        n_valid=len(results) - zero_call_count - missing_count,
    )
    return series, diag


def compute_volume_momentum(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Volume momentum: ratio of 5-day avg volume to 20-day avg volume.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Captures unusual trading activity (breakout / institutional accumulation).

    Sign convention: POSITIVE (high volume momentum with price = continuation).
    Requires >= 20 days of volume data per symbol.

    Handles: insufficient data (< 20 days) -> NaN.
             zero 20-day avg volume -> NaN.
    """
    diag = Diagnostics()
    source = "sentiment.compute_volume_momentum"

    required_cols = {COL_SYMBOL, COL_DATE, COL_VOLUME}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="volume_momentum"), diag

    results: dict[str, float] = {}
    insufficient_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        vol = group_sorted[COL_VOLUME].astype(float)

        if len(vol) < _VOL_MOM_SLOW:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        avg_fast = vol.tail(_VOL_MOM_FAST).mean()
        avg_slow = vol.tail(_VOL_MOM_SLOW).mean()

        if avg_slow == 0:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        results[symbol] = float(avg_fast / avg_slow)

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient history "
            f"(< {_VOL_MOM_SLOW} days) or zero volume; set to NaN.",
            insufficient_count=insufficient_count,
            min_days=_VOL_MOM_SLOW,
        )

    series = pd.Series(results, name="volume_momentum")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional volume momentum computed.",
        fast_window=_VOL_MOM_FAST,
        slow_window=_VOL_MOM_SLOW,
        n_symbols=len(results),
        n_valid=len(results) - insufficient_count,
    )
    return series, diag


def compute_ewmac(
    data: pd.DataFrame,
    fast_span: int = _EWMAC_FAST_SPAN,
    slow_span: int = _EWMAC_SLOW_SPAN,
) -> tuple[pd.Series, Diagnostics]:
    """EWMAC: Carver's exponentially-weighted moving average crossover.

    EWMAC = EMA(close, fast_span) - EMA(close, slow_span),
    normalized by realized volatility (std of daily returns over vol_window).

    Cross-sectional: for each symbol, compute EWMAC at the last available date.
    Result is the raw EWMAC value per symbol (not percentile-ranked here;
    normalization is handled downstream by the pipeline).

    Sign convention: POSITIVE (positive trend = buy signal).

    Default spans: fast=8, slow=32 (Carver's recommended pair).
    Requires >= slow_span days of close prices per symbol; otherwise NaN.

    Handles: insufficient data (< slow_span) -> NaN.
             zero realized vol -> NaN.
    """
    diag = Diagnostics()
    source = "sentiment.compute_ewmac"

    required_cols = {COL_SYMBOL, COL_DATE, COL_CLOSE}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="ewmac"), diag

    results: dict[str, float] = {}
    insufficient_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        close = group_sorted[COL_CLOSE].astype(float)

        if len(close) < slow_span:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        ema_fast = close.ewm(span=fast_span, adjust=False).mean()
        ema_slow = close.ewm(span=slow_span, adjust=False).mean()

        raw_ewmac = ema_fast.iloc[-1] - ema_slow.iloc[-1]

        # Normalize by realized volatility (std of daily returns)
        daily_returns = close.pct_change().dropna()
        vol_window = min(_EWMAC_VOL_WINDOW, len(daily_returns))
        realized_vol = daily_returns.tail(vol_window).std()

        if realized_vol == 0 or pd.isna(realized_vol):
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        # Normalize: divide by (close_level * realized_vol) to make unitless
        last_close = close.iloc[-1]
        if last_close == 0:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        normalized_ewmac = raw_ewmac / (last_close * realized_vol)
        results[symbol] = float(normalized_ewmac)

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient history "
            f"(< {slow_span} days) or zero vol; set to NaN.",
            insufficient_count=insufficient_count,
            min_required=slow_span,
        )

    series = pd.Series(results, name="ewmac")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional EWMAC computed.",
        fast_span=fast_span,
        slow_span=slow_span,
        n_symbols=len(results),
        n_valid=len(results) - insufficient_count,
    )
    return series, diag
