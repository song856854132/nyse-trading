"""Synthetic XBRL fact generator matching EDGAR adapter output.

Emits long-format raw facts identical in shape to
``nyse_ats.data.edgar_adapter.EdgarAdapter.fetch()``:

    date, symbol, metric_name, value, filing_type, period_end

One row per (symbol, period_end, metric_name). The emitted metric set covers
everything the fundamental factor compute functions consume:

    revenue, gross_profit, cost_of_revenue, net_income,
    operating_cash_flow, total_assets, current_assets,
    current_liabilities, long_term_debt, shares_outstanding

Filing dates lag period_end by a realistic 40–55 days. Filings alternate
between 10-K (Q4 period_end) and 10-Q otherwise.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

_METRIC_SCHEMA_COLS = [
    "date",
    "symbol",
    "metric_name",
    "value",
    "filing_type",
    "period_end",
]

_METRICS_EMITTED = (
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "net_income",
    "operating_cash_flow",
    "total_assets",
    "current_assets",
    "current_liabilities",
    "long_term_debt",
    "shares_outstanding",
)


def generate_fundamentals(
    symbols: list[str],
    n_quarters: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic quarterly XBRL facts in EDGAR long-format.

    Each stock is assigned a persistent business-quality profile (revenue
    scale, gross-margin ratio, asset leverage, etc.) that drifts slowly
    quarter-over-quarter. For each quarter we emit one row per metric in
    ``_METRICS_EMITTED``, so a 5-stock x 20-quarter x 10-metric generation
    yields 1,000 rows.

    Parameters
    ----------
    symbols : list[str]
        Symbols to generate facts for.
    n_quarters : int
        Quarters of history (default 20 = 5 years).
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Columns: date, symbol, metric_name, value, filing_type, period_end.
        Sorted by (symbol, period_end, metric_name).
    """
    rng = np.random.default_rng(seed)

    quarter_ends = pd.date_range(
        end="2024-12-31",
        periods=n_quarters,
        freq="QE",
    )

    records: list[dict] = []

    for sym in symbols:
        # Per-stock baseline profile
        revenue = rng.uniform(5e8, 5e9)  # $500M – $5B
        base_gm_ratio = rng.uniform(0.30, 0.55)  # gross margin
        base_ni_ratio = rng.uniform(0.05, 0.15)  # net margin
        base_ta_ratio = rng.uniform(2.0, 4.0)  # assets / revenue
        base_ca_ratio = rng.uniform(0.25, 0.40)  # CA / TA
        base_cl_ratio = rng.uniform(0.15, 0.30)  # CL / TA
        base_ltd_ratio = rng.uniform(0.15, 0.35)  # LTD / TA
        base_cfo_premium = rng.uniform(0.95, 1.15)  # CFO / NI
        shares = rng.uniform(1e8, 5e8)  # 100M – 500M

        for q_end in quarter_ends:
            # Slow growth + noise
            revenue *= 1 + rng.normal(0.01, 0.03)
            gm_ratio = max(0.05, base_gm_ratio + rng.normal(0, 0.02))
            ni_ratio = base_ni_ratio + rng.normal(0, 0.015)
            ta_ratio = max(1.0, base_ta_ratio + rng.normal(0, 0.1))
            ca_ratio = max(0.05, base_ca_ratio + rng.normal(0, 0.02))
            cl_ratio = max(0.05, base_cl_ratio + rng.normal(0, 0.02))
            ltd_ratio = max(0.0, base_ltd_ratio + rng.normal(0, 0.02))
            cfo_premium = base_cfo_premium + rng.normal(0, 0.05)
            # Shares drift slightly downward (buybacks) w/ tiny noise
            shares *= 1 - rng.uniform(0, 0.005)

            gross_profit_val = revenue * gm_ratio
            cost_of_rev = revenue - gross_profit_val
            net_income = revenue * ni_ratio
            total_assets = revenue * ta_ratio
            current_assets = total_assets * ca_ratio
            current_liab = total_assets * cl_ratio
            long_term_debt = total_assets * ltd_ratio
            operating_cf = net_income * cfo_premium

            is_q4 = q_end.month == 12
            filing_type = "10-K" if is_q4 else "10-Q"
            lag_days = int(rng.integers(40, 56))
            filing_date = (q_end + timedelta(days=lag_days)).date()
            period_end_d = q_end.date()

            values = {
                "revenue": revenue,
                "gross_profit": gross_profit_val,
                "cost_of_revenue": cost_of_rev,
                "net_income": net_income,
                "operating_cash_flow": operating_cf,
                "total_assets": total_assets,
                "current_assets": current_assets,
                "current_liabilities": current_liab,
                "long_term_debt": long_term_debt,
                "shares_outstanding": shares,
            }
            for metric_name, value in values.items():
                records.append(
                    {
                        "date": filing_date,
                        "symbol": sym,
                        "metric_name": metric_name,
                        "value": float(value),
                        "filing_type": filing_type,
                        "period_end": period_end_d,
                    }
                )

    df = pd.DataFrame(records, columns=_METRIC_SCHEMA_COLS)
    df = df.sort_values(["symbol", "period_end", "metric_name"]).reset_index(drop=True)
    return df
