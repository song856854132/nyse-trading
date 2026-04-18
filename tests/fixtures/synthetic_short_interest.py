"""Synthetic FINRA-style short interest data generator for NYSE ATS tests.

Generates bi-monthly short interest observations with realistic ranges
for short_interest, shares_outstanding, and avg_daily_volume.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_short_interest(
    symbols: list[str],
    n_periods: int = 24,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic FINRA-style short interest data.

    FINRA publishes short interest twice per month (bi-monthly).
    Each report has an ~11-day publication lag (handled by PiT upstream).

    Parameters
    ----------
    symbols : list[str]
        Stock symbols to generate data for.
    n_periods : int
        Number of bi-monthly observation periods (default 24 = 1 year).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Columns: symbol, date, short_interest, shares_outstanding, avg_daily_volume.
        Sorted by (symbol, date).
    """
    rng = np.random.default_rng(seed)

    # Generate bi-monthly settlement dates (1st and 15th of each month)
    # Going back from a recent date
    end_date = pd.Timestamp("2024-12-15")
    dates: list[pd.Timestamp] = []
    for i in range(n_periods):
        # Alternate between 15th and 1st, going backwards
        months_back = i // 2
        day = 15 if i % 2 == 0 else 1
        dt = end_date - pd.DateOffset(months=months_back)
        dt = dt.replace(day=day)
        dates.append(dt)
    dates = sorted(dates)

    records: list[dict] = []

    for sym in symbols:
        # Per-stock fundamentals (persistent characteristics)
        shares_outstanding = int(rng.uniform(50e6, 5e9))

        # avg_daily_volume correlates with shares_outstanding
        # Roughly 0.5%-2% of shares outstanding traded daily
        base_adv = shares_outstanding * rng.uniform(0.005, 0.02)

        # Base short interest: 1%-15% of shares outstanding
        base_si_pct = rng.uniform(0.01, 0.15)

        for report_date in dates:
            # Short interest drifts over time
            si_pct = base_si_pct + rng.normal(0, 0.01)
            si_pct = float(np.clip(si_pct, 0.005, 0.30))
            short_interest = int(shares_outstanding * si_pct)

            # ADV varies with some noise
            adv = int(base_adv * rng.uniform(0.7, 1.3))

            records.append(
                {
                    "symbol": sym,
                    "date": report_date.date(),
                    "short_interest": short_interest,
                    "shares_outstanding": shares_outstanding,
                    "avg_daily_volume": adv,
                }
            )

    df = pd.DataFrame(records)
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    return df
