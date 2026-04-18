"""Detailed OHLCV price generator for NYSE ATS test infrastructure.

Generates realistic synthetic price data with proper OHLCV relationships,
missing-day gaps, zero-volume days, and stocks with insufficient history.
Uses a trading calendar (weekdays only) and geometric random walks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_SYMBOL,
    COL_VOLUME,
)


def _generate_trading_dates(n_days: int, start_date: str = "2020-01-02") -> pd.DatetimeIndex:
    """Generate n_days of weekday-only trading dates starting from start_date."""
    # Generate enough business days to cover n_days
    dates = pd.bdate_range(start=start_date, periods=n_days, freq="B")
    return dates


def _generate_single_stock_prices(
    rng: np.random.Generator,
    dates: pd.DatetimeIndex,
    start_price: float,
    annual_drift: float,
    annual_vol: float,
) -> pd.DataFrame:
    """Generate OHLCV for a single stock using geometric Brownian motion.

    Ensures high >= max(open, close) and low <= min(open, close).
    """
    n = len(dates)
    dt = 1 / 252  # fraction of a trading year

    # Log returns with drift and volatility
    daily_drift = (annual_drift - 0.5 * annual_vol**2) * dt
    daily_vol = annual_vol * np.sqrt(dt)
    log_returns = rng.normal(daily_drift, daily_vol, n)

    # Generate close prices via cumulative returns
    close_prices = start_price * np.exp(np.cumsum(log_returns))

    # Open is close shifted by small noise (gap up/down from previous close)
    gap_noise = rng.normal(0, 0.002, n)  # small overnight gap
    open_prices = np.empty(n)
    open_prices[0] = start_price * (1 + gap_noise[0])
    open_prices[1:] = close_prices[:-1] * (1 + gap_noise[1:])

    # Intraday range: high and low extend beyond open/close
    intraday_range = rng.uniform(0.005, 0.03, n)  # 0.5% to 3% intraday range
    max_oc = np.maximum(open_prices, close_prices)
    min_oc = np.minimum(open_prices, close_prices)

    high_prices = max_oc * (1 + intraday_range * rng.uniform(0.3, 1.0, n))
    low_prices = min_oc * (1 - intraday_range * rng.uniform(0.3, 1.0, n))

    # Enforce constraints: low > 0
    low_prices = np.maximum(low_prices, 0.01)

    # Volume: log-normal with mean ~2M shares, correlated with absolute return
    base_volume = rng.lognormal(mean=14.5, sigma=0.5, size=n)  # ~2M shares
    abs_ret = np.abs(log_returns)
    vol_multiplier = 1 + 5 * abs_ret  # higher returns = more volume
    volume = (base_volume * vol_multiplier).astype(int)

    return pd.DataFrame(
        {
            COL_DATE: dates,
            COL_OPEN: np.round(open_prices, 2),
            COL_HIGH: np.round(high_prices, 2),
            COL_LOW: np.round(low_prices, 2),
            COL_CLOSE: np.round(close_prices, 2),
            COL_VOLUME: volume,
        }
    )


def generate_prices(
    n_stocks: int = 50,
    n_days: int = 600,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate realistic OHLCV data for multiple stocks.

    Features:
    - Proper OHLCV relationships: high >= max(open, close), low <= min(open, close)
    - Some stocks with missing days (gaps simulating halts/illiquidity)
    - A few stocks with zero-volume days
    - At least one stock with insufficient history (recently listed)
    - Trading calendar: weekdays only
    - Deterministic via seed

    Parameters
    ----------
    n_stocks : int
        Number of stocks to generate (default 50).
    n_days : int
        Number of trading days per stock (default 600).
    seed : int
        Random seed for reproducibility (default 42).

    Returns
    -------
    pd.DataFrame
        Columns: date, symbol, open, high, low, close, volume.
        Sorted by (date, symbol).
    """
    rng = np.random.default_rng(seed)
    dates = _generate_trading_dates(n_days)

    # Generate symbol names: AAAA, AABB, ... or simply SYM_00 .. SYM_49
    symbols = [f"SYM_{i:02d}" for i in range(n_stocks)]

    frames: list[pd.DataFrame] = []

    for i, sym in enumerate(symbols):
        # Vary starting price ($20-$200) and vol (15%-45% annual)
        start_price = rng.uniform(20, 200)
        annual_drift = rng.uniform(-0.05, 0.15)
        annual_vol = rng.uniform(0.15, 0.45)

        # Special case: last 3 stocks start recently (insufficient history)
        if i >= n_stocks - 3:
            # These stocks only have the last 60-120 days of data
            recent_days = rng.integers(60, 121)
            stock_dates = dates[-recent_days:]
        else:
            stock_dates = dates

        df = _generate_single_stock_prices(
            rng,
            stock_dates,
            start_price,
            annual_drift,
            annual_vol,
        )
        df[COL_SYMBOL] = sym

        # Introduce missing days (gaps) for ~20% of stocks
        if i % 5 == 0 and i < n_stocks - 3:
            n_gaps = rng.integers(3, 10)
            gap_indices = rng.choice(len(df), size=min(n_gaps, len(df) - 1), replace=False)
            df = df.drop(df.index[gap_indices]).reset_index(drop=True)

        # Introduce zero-volume days for ~10% of stocks
        if i % 10 == 0 and len(df) > 0:
            n_zero_vol = rng.integers(1, 4)
            zero_indices = rng.choice(len(df), size=min(n_zero_vol, len(df)), replace=False)
            df.loc[df.index[zero_indices], COL_VOLUME] = 0

        frames.append(df)

    result = pd.concat(frames, ignore_index=True)
    result[COL_DATE] = pd.to_datetime(result[COL_DATE]).dt.date
    result = result.sort_values([COL_DATE, COL_SYMBOL]).reset_index(drop=True)

    return result


def generate_spy_prices(n_days: int = 600, seed: int = 42) -> pd.DataFrame:
    """Generate SPY benchmark price series with SMA200 crossing events.

    Designed so that the SMA200 regime overlay produces both BULL and BEAR
    periods in the synthetic data for testing.

    Parameters
    ----------
    n_days : int
        Number of trading days (default 600).
    seed : int
        Random seed (default 42).

    Returns
    -------
    pd.DataFrame
        Columns: date, symbol (always 'SPY'), open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed + 1000)  # different seed from main prices
    dates = _generate_trading_dates(n_days)

    n = len(dates)
    # Start at ~$450, create a path that crosses SMA200 at least once
    # First half: uptrend, second third: downtrend, last sixth: recovery
    drift_segments = np.concatenate(
        [
            np.full(n // 2, 0.12 / 252),  # mild uptrend
            np.full(n // 3, -0.25 / 252),  # sharp downtrend to cross below SMA200
            np.full(n - n // 2 - n // 3, 0.20 / 252),  # recovery
        ]
    )

    daily_vol = 0.16 / np.sqrt(252)
    noise = rng.normal(0, daily_vol, n)
    log_returns = drift_segments + noise

    close_prices = 450.0 * np.exp(np.cumsum(log_returns))

    open_prices = np.empty(n)
    open_prices[0] = 450.0
    open_prices[1:] = close_prices[:-1] * (1 + rng.normal(0, 0.001, n - 1))

    intraday = rng.uniform(0.003, 0.015, n)
    high_prices = np.maximum(open_prices, close_prices) * (1 + intraday)
    low_prices = np.minimum(open_prices, close_prices) * (1 - intraday)
    low_prices = np.maximum(low_prices, 0.01)

    volume = rng.lognormal(mean=18.0, sigma=0.3, size=n).astype(int)

    df = pd.DataFrame(
        {
            COL_DATE: dates,
            COL_SYMBOL: "SPY",
            COL_OPEN: np.round(open_prices, 2),
            COL_HIGH: np.round(high_prices, 2),
            COL_LOW: np.round(low_prices, 2),
            COL_CLOSE: np.round(close_prices, 2),
            COL_VOLUME: volume,
        }
    )
    df[COL_DATE] = pd.to_datetime(df[COL_DATE]).dt.date

    return df
