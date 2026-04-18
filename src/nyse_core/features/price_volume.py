"""Price/Volume factor computations — cross-sectional IVOL, 52-week high, momentum.

All functions accept a MULTI-STOCK prices DataFrame with columns:
  date, symbol, open, high, low, close, volume
and return (pd.Series indexed by symbol, Diagnostics).

Sign conventions are documented but NOT applied here — the FactorRegistry
handles inversion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL

# ── Constants ────────────────────────────────────────────────────────────────
_IVOL_WINDOW: int = 20
_IVOL_MIN_DAYS: int = 15
_HIGH52W_WINDOW: int = 252
_HIGH52W_MIN_DAYS: int = 200
_MOM_TOTAL_WINDOW: int = 252
_MOM_SKIP_RECENT: int = 21  # ~1 month of trading days


def compute_ivol_20d(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Idiosyncratic volatility: std of market-model residuals over last 20 days.

    Uses cross-sectional equal-weighted market return as the market factor.
    Regresses each stock's daily returns on the market return via OLS, then
    computes the standard deviation of the residuals (epsilon).

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.

    Sign convention: NEGATIVE (low IVOL = buy signal).
    Registry will negate the output so higher = better.

    Requires >= 15 days of close prices per symbol; otherwise returns NaN.
    """
    diag = Diagnostics()
    source = "price_volume.compute_ivol_20d"

    results: dict[str, float] = {}
    insufficient_count = 0

    # Pivot to wide-format daily returns for market-model regression
    pivoted = data.pivot_table(
        index=COL_DATE,
        columns=COL_SYMBOL,
        values=COL_CLOSE,
        aggfunc="last",
    ).sort_index()
    all_returns = pivoted.pct_change(fill_method=None).dropna(how="all")

    # Equal-weighted cross-sectional market return
    market_return = all_returns.mean(axis=1)
    # Need >= 2 stocks for a meaningful market-model; otherwise fall back
    _use_market_model = all_returns.shape[1] >= 2

    for symbol in all_returns.columns:
        # Check close price availability (pct_change reduces count by 1)
        n_close = int(pivoted[symbol].dropna().shape[0])
        if n_close < _IVOL_MIN_DAYS:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        stock_ret = all_returns[symbol].dropna()
        tail = stock_ret.tail(_IVOL_WINDOW)

        if _use_market_model:
            mkt_tail = market_return.loc[tail.index]
            # Market-model OLS: r_i = alpha + beta * r_m + epsilon
            # IVOL = std(epsilon)
            X = np.column_stack([np.ones(len(mkt_tail)), mkt_tail.values])
            y_vec = tail.values
            try:
                coeffs, _, _, _ = np.linalg.lstsq(X, y_vec, rcond=None)
                residuals = y_vec - X @ coeffs
                ivol = float(np.std(residuals, ddof=1))
            except np.linalg.LinAlgError:
                ivol = float(tail.std())
                diag.warning(source, f"OLS failed for {symbol}, using plain std.")
        else:
            # Single stock: market model is degenerate, use plain std
            ivol = float(tail.std())

        results[symbol] = ivol

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient history "
            f"(< {_IVOL_MIN_DAYS} days) for IVOL; set to NaN.",
            insufficient_count=insufficient_count,
            min_required=_IVOL_MIN_DAYS,
        )

    series = pd.Series(results, name="ivol_20d")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional IVOL (market-model residual) computed.",
        window=_IVOL_WINDOW,
        n_symbols=len(results),
        n_valid=len(results) - insufficient_count,
    )
    return series, diag


def compute_52w_high_proximity(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Proximity to 52-week high: close / max(close over 252 days).

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.

    Sign convention: POSITIVE (near 52w high = buy signal).
    Requires >= 200 days of history per symbol.
    """
    diag = Diagnostics()
    source = "price_volume.compute_52w_high_proximity"

    results: dict[str, float] = {}
    insufficient_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        close = group_sorted[COL_CLOSE]
        n_days = len(close)

        if n_days < _HIGH52W_MIN_DAYS:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        window = close.tail(_HIGH52W_WINDOW)
        high_52w = window.max()
        current_close = close.iloc[-1]
        proximity = float(current_close / high_52w) if high_52w != 0 else np.nan
        results[symbol] = proximity

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient history "
            f"(< {_HIGH52W_MIN_DAYS} days) for 52w high; set to NaN.",
            insufficient_count=insufficient_count,
            min_required=_HIGH52W_MIN_DAYS,
        )

    series = pd.Series(results, name="52w_high_proximity")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional 52w high proximity computed.",
        n_symbols=len(results),
        n_valid=len(results) - insufficient_count,
    )
    return series, diag


def compute_momentum_2_12(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Momentum 2-12: return from 12 months ago to 1 month ago.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.

    Skips the most recent month (~21 trading days) to avoid short-term reversal.
    Requires >= 252 days of history per symbol.

    Sign convention: POSITIVE (high past returns = buy signal).
    """
    diag = Diagnostics()
    source = "price_volume.compute_momentum_2_12"

    results: dict[str, float] = {}
    insufficient_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        close = group_sorted[COL_CLOSE]
        n_days = len(close)

        if n_days < _MOM_TOTAL_WINDOW:
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        # Price 12 months ago (~252 trading days back)
        price_12m = close.iloc[-_MOM_TOTAL_WINDOW]
        # Price ~1 month ago (skip recent 21 trading days)
        price_2m = close.iloc[-_MOM_SKIP_RECENT - 1]

        momentum = float((price_2m - price_12m) / price_12m) if price_12m != 0 else np.nan
        results[symbol] = momentum

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient history "
            f"(< {_MOM_TOTAL_WINDOW} days) for momentum 2-12; set to NaN.",
            insufficient_count=insufficient_count,
            min_required=_MOM_TOTAL_WINDOW,
        )

    series = pd.Series(results, name="momentum_2_12")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional momentum 2-12 computed.",
        n_symbols=len(results),
        n_valid=len(results) - insufficient_count,
    )
    return series, diag
