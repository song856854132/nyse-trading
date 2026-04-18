"""Synthetic corporate actions generator for NYSE ATS test infrastructure.

Generates stock splits and dividends on random dates for a subset of symbols.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_corporate_actions(
    symbols: list[str],
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic corporate actions (splits and dividends).

    Produces:
    - A few stock splits (2:1, 3:1, 4:1) on random dates
    - A few dividend events with realistic ex-dates and amounts

    Parameters
    ----------
    symbols : list[str]
        List of stock symbols from which to sample.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Columns: date, symbol, action_type, split_ratio, dividend_amount.
        split_ratio is NaN for dividends; dividend_amount is NaN for splits.
        Sorted by date.
    """
    rng = np.random.default_rng(seed)

    # Generate dates across a ~2.5 year period
    date_range = pd.bdate_range(start="2022-06-01", end="2024-12-31", freq="B")

    records: list[dict] = []

    # Splits: pick ~8% of stocks, each gets 1-2 splits
    n_split_stocks = max(1, len(symbols) // 12)
    split_stocks = rng.choice(symbols, size=n_split_stocks, replace=False)
    split_ratios = [2, 3, 4]  # 2:1, 3:1, 4:1

    for sym in split_stocks:
        n_splits = rng.integers(1, 3)
        split_dates = rng.choice(date_range, size=n_splits, replace=False)
        for split_date in split_dates:
            ratio = rng.choice(split_ratios)
            records.append(
                {
                    "date": pd.Timestamp(split_date).date(),
                    "symbol": sym,
                    "action_type": "SPLIT",
                    "split_ratio": float(ratio),
                    "dividend_amount": float("nan"),
                }
            )

    # Dividends: pick ~40% of stocks (simulating S&P 500 dividend payers)
    n_div_stocks = max(1, len(symbols) * 2 // 5)
    div_stocks = rng.choice(symbols, size=n_div_stocks, replace=False)

    for sym in div_stocks:
        # Quarterly dividends: pick 4-8 ex-dates
        n_divs = rng.integers(4, 9)
        div_dates = sorted(rng.choice(date_range, size=n_divs, replace=False))
        base_div = rng.uniform(0.20, 1.50)  # base quarterly dividend per share

        for div_date in div_dates:
            # Small random variation in dividend amount
            amount = round(float(base_div * (1 + rng.normal(0, 0.05))), 2)
            amount = max(0.01, amount)
            records.append(
                {
                    "date": pd.Timestamp(div_date).date(),
                    "symbol": sym,
                    "action_type": "DIVIDEND",
                    "split_ratio": float("nan"),
                    "dividend_amount": amount,
                }
            )

    df = pd.DataFrame(records)
    if len(df) > 0:
        df = df.sort_values("date").reset_index(drop=True)

    return df
