"""Factor and sector return attribution (Brinson-style decomposition).

Decomposes portfolio returns into factor contributions and sector-level
allocation/selection effects relative to a benchmark.

All functions are pure -- no I/O, no logging.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from nyse_core.contracts import AttributionReport, Diagnostics

_MOD = "attribution"


def compute_attribution(
    portfolio_weights: pd.DataFrame,
    stock_returns: pd.DataFrame,
    factor_exposures: pd.DataFrame,
    sector_map: pd.Series,
    benchmark_weights: pd.DataFrame | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> tuple[AttributionReport, Diagnostics]:
    """Brinson-style factor + sector attribution.

    Factor attribution:
      For each factor f:
        contribution_f = sum over stocks of:
          (port_weight - bench_weight) * factor_exposure_f * return

    Sector attribution:
      For each GICS sector s:
        allocation_effect =
          (port_sector_weight - bench_sector_weight) * (sector_return - total_bench_return)
        selection_effect =
          bench_sector_weight * (port_sector_return - bench_sector_return)
        contribution_s = allocation_effect + selection_effect

    Parameters
    ----------
    portfolio_weights : pd.DataFrame
        Columns: date, symbol, weight.
    stock_returns : pd.DataFrame
        Columns: date, symbol, return.
    factor_exposures : pd.DataFrame
        Columns: date, symbol, factor_name, exposure.
    sector_map : pd.Series
        Index: symbol, Values: GICS sector string.
    benchmark_weights : pd.DataFrame | None
        Columns: date, symbol, weight. If None, equal-weight benchmark assumed.
    period_start : date | None
        Start of attribution window (inclusive). Uses earliest date if None.
    period_end : date | None
        End of attribution window (inclusive). Uses latest date if None.

    Returns
    -------
    tuple[AttributionReport, Diagnostics]
        (attribution_report, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_attribution"

    # ── Validate inputs ──────────────────────────────────────────────────
    if portfolio_weights.empty or stock_returns.empty:
        diag.warning(src, "Empty portfolio weights or stock returns.")
        p_start = period_start or date(2000, 1, 1)
        p_end = period_end or date(2000, 1, 1)
        report = AttributionReport(
            factor_contributions={},
            sector_contributions={},
            total_return=0.0,
            period_start=p_start,
            period_end=p_end,
        )
        return report, diag

    # ── Determine date range ─────────────────────────────────────────────
    all_dates = sorted(portfolio_weights["date"].unique())
    if period_start is not None:
        all_dates = [d for d in all_dates if d >= period_start]
    if period_end is not None:
        all_dates = [d for d in all_dates if d <= period_end]

    if not all_dates:
        diag.warning(src, "No dates in the specified period range.")
        p_start = period_start or date(2000, 1, 1)
        p_end = period_end or date(2000, 1, 1)
        report = AttributionReport(
            factor_contributions={},
            sector_contributions={},
            total_return=0.0,
            period_start=p_start,
            period_end=p_end,
        )
        return report, diag

    p_start = period_start or all_dates[0]
    p_end = period_end or all_dates[-1]

    # ── Build benchmark if not provided (equal-weight) ───────────────────
    if benchmark_weights is None:
        bench_records = []
        for dt in all_dates:
            day_symbols = stock_returns.loc[stock_returns["date"] == dt, "symbol"].unique()
            n_sym = len(day_symbols)
            if n_sym == 0:
                continue
            eq_w = 1.0 / n_sym
            for sym in day_symbols:
                bench_records.append({"date": dt, "symbol": sym, "weight": eq_w})
        benchmark_weights = pd.DataFrame(bench_records)
        diag.info(src, "Using equal-weight benchmark (no benchmark provided).")

    # ── Merge portfolio weights with returns ─────────────────────────────
    port_merged = pd.merge(portfolio_weights, stock_returns, on=["date", "symbol"], how="inner")
    bench_merged = pd.merge(benchmark_weights, stock_returns, on=["date", "symbol"], how="inner")

    # ── Total portfolio and benchmark returns ────────────────────────────
    total_port_return = 0.0
    total_bench_return = 0.0

    for dt in all_dates:
        port_day = port_merged[port_merged["date"] == dt]
        bench_day = bench_merged[bench_merged["date"] == dt]

        if not port_day.empty:
            total_port_return += (port_day["weight"] * port_day["return"]).sum()
        if not bench_day.empty:
            total_bench_return += (bench_day["weight"] * bench_day["return"]).sum()

    # ── Factor attribution ───────────────────────────────────────────────
    factor_contributions: dict[str, float] = {}

    if not factor_exposures.empty:
        factor_names = factor_exposures["factor_name"].unique()

        for f_name in factor_names:
            f_exposure = factor_exposures[factor_exposures["factor_name"] == f_name]
            contribution = 0.0

            for dt in all_dates:
                port_day = port_merged[port_merged["date"] == dt].set_index("symbol")
                bench_day = bench_merged[bench_merged["date"] == dt].set_index("symbol")
                exp_day = f_exposure[f_exposure["date"] == dt].set_index("symbol")

                all_symbols = set(port_day.index) | set(bench_day.index)
                if not all_symbols:
                    continue

                for sym in all_symbols:
                    pw = port_day.loc[sym, "weight"] if sym in port_day.index else 0.0
                    bw = bench_day.loc[sym, "weight"] if sym in bench_day.index else 0.0
                    exp = exp_day.loc[sym, "exposure"] if sym in exp_day.index else 0.0
                    ret = 0.0
                    if sym in port_day.index:
                        ret = port_day.loc[sym, "return"]
                    elif sym in bench_day.index:
                        ret = bench_day.loc[sym, "return"]

                    contribution += (pw - bw) * exp * ret

            factor_contributions[f_name] = float(contribution)

    diag.info(
        src,
        f"Factor attribution computed for {len(factor_contributions)} factors.",
    )

    # ── Sector attribution (Brinson) ─────────────────────────────────────
    sector_contributions: dict[str, float] = {}

    # Map symbols to sectors
    port_merged = port_merged.copy()
    bench_merged = bench_merged.copy()
    port_merged["sector"] = port_merged["symbol"].map(sector_map)
    bench_merged["sector"] = bench_merged["symbol"].map(sector_map)

    # Drop rows with unmapped sectors
    port_with_sector = port_merged.dropna(subset=["sector"])
    bench_with_sector = bench_merged.dropna(subset=["sector"])

    all_sectors = set()
    if not port_with_sector.empty:
        all_sectors |= set(port_with_sector["sector"].unique())
    if not bench_with_sector.empty:
        all_sectors |= set(bench_with_sector["sector"].unique())

    # Aggregate across all dates
    avg_total_bench_return = total_bench_return

    for sector in sorted(all_sectors):
        port_sector = port_with_sector[port_with_sector["sector"] == sector]
        bench_sector = bench_with_sector[bench_with_sector["sector"] == sector]

        # Portfolio sector weight and return
        port_sector_weight = port_sector["weight"].sum() if not port_sector.empty else 0.0
        port_sector_return = (
            (port_sector["weight"] * port_sector["return"]).sum() / port_sector_weight
            if port_sector_weight > 1e-15
            else 0.0
        )

        # Benchmark sector weight and return
        bench_sector_weight = bench_sector["weight"].sum() if not bench_sector.empty else 0.0
        bench_sector_return = (
            (bench_sector["weight"] * bench_sector["return"]).sum() / bench_sector_weight
            if bench_sector_weight > 1e-15
            else 0.0
        )

        # Brinson decomposition
        allocation_effect = (port_sector_weight - bench_sector_weight) * (
            bench_sector_return - avg_total_bench_return
        )
        selection_effect = bench_sector_weight * (port_sector_return - bench_sector_return)

        sector_contributions[sector] = float(allocation_effect + selection_effect)

    diag.info(
        src,
        f"Sector attribution computed for {len(sector_contributions)} sectors.",
    )

    report = AttributionReport(
        factor_contributions=factor_contributions,
        sector_contributions=sector_contributions,
        total_return=float(total_port_return),
        period_start=p_start,
        period_end=p_end,
    )

    return report, diag
