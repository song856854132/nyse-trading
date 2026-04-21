"""Benchmark construction helpers (pure leaves — no I/O).

This module builds *reference-portfolio return series* that the factor-screening
pipeline can feed to ``benchmark_metrics.compute_benchmark_relative_metrics``.
These references are diagnostic only — they never feed G0-G5 admission logic.

Sector-neutral benchmark (iter-2)
---------------------------------
Given a per-(date, symbol) return panel and a static symbol→sector map, build a
daily return series equal to the equal-weight mean of equal-weight-within-sector
returns. Formally, for date *t* with sectors *S* non-empty that day::

    r_sector(t, s) = mean_{sym in s with return at t}( r(t, sym) )
    r_bench(t)     = mean_{s in S(t)}( r_sector(t, s) )

This removes sector-composition tilt: a 20-stock factor-portfolio concentrated
in one sector should NOT beat this benchmark simply because that sector
outperformed — the comparison forces the stock-selection alpha to justify
itself above the *sector-neutral* return.

Characteristic-matched benchmark (iter-4 — not yet implemented)
---------------------------------------------------------------
Will land under this same module so iter-1/2/4 all hang off one import path.

Conventions
-----------
* Pure — no I/O, no logging, imports only pandas/numpy.
* Every public function returns ``(result, Diagnostics)`` so the caller can
  trace degenerate inputs without swallowing warnings into stdout.
* Missing symbols, NaN returns, and unmapped-sector stocks degrade gracefully
  to a shorter series rather than raising — the screening pipeline should
  surface the gap via Diagnostics, not die on a missing ticker.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics

_SRC = "benchmark_construction"


def compute_sector_neutral_returns(
    daily_returns: pd.DataFrame,
    sector_map: pd.Series,
) -> tuple[pd.Series, Diagnostics]:
    """Build an equal-sector-weight, equal-within-sector benchmark return series.

    Parameters
    ----------
    daily_returns
        Wide DataFrame of per-symbol returns. ``index`` is the date stamp,
        ``columns`` are symbols, values are per-period returns (decimal, not
        percent). NaN cells are treated as "no observation for that symbol on
        that date" and excluded from the sector mean.
    sector_map
        Series mapping symbol → sector string. Index are symbols, values are
        GICS (or equivalent) sector labels. Symbols present in
        ``daily_returns`` but absent from or NaN-valued in ``sector_map`` are
        treated as unclassified and excluded from the benchmark.

    Returns
    -------
    tuple[pd.Series, Diagnostics]
        First element: Series indexed by date (same index as ``daily_returns``)
        carrying the sector-neutral daily return. Dates with zero eligible
        sectors degrade to NaN rather than raising.
        Second element: Diagnostics carrying info/warning messages about
        degenerate inputs (empty panel, empty sector map, all-unclassified
        universe, etc.).
    """
    diag = Diagnostics()

    if daily_returns.empty:
        diag.warning(_SRC, "daily_returns is empty — returning empty Series")
        return pd.Series(dtype=float, name="sector_neutral"), diag

    if sector_map.empty:
        diag.warning(
            _SRC,
            "sector_map is empty — cannot build sector-neutral benchmark; returning NaN series",
        )
        nan_series = pd.Series(
            np.full(len(daily_returns.index), np.nan),
            index=daily_returns.index,
            name="sector_neutral",
        )
        return nan_series, diag

    # Drop NaN sector labels before indexing — unclassified symbols are ignored.
    clean_map = sector_map.dropna()

    # Restrict to symbols that appear both in the panel and in the sector map.
    panel_symbols = set(daily_returns.columns)
    mapped_symbols = set(clean_map.index)
    overlap = panel_symbols & mapped_symbols
    unmapped = panel_symbols - mapped_symbols

    if unmapped:
        diag.info(
            _SRC,
            f"{len(unmapped)}/{len(panel_symbols)} symbols have no sector assignment; excluded",
            n_unmapped=len(unmapped),
            n_total=len(panel_symbols),
        )
    if not overlap:
        diag.warning(
            _SRC,
            "no overlap between daily_returns columns and sector_map index — returning NaN series",
        )
        nan_series = pd.Series(
            np.full(len(daily_returns.index), np.nan),
            index=daily_returns.index,
            name="sector_neutral",
        )
        return nan_series, diag

    panel = daily_returns[sorted(overlap)]

    # Long-format (date, symbol, ret) joined with sector, then groupby(date,sector).mean().
    # We reshape in long form exactly once so the per-date / per-sector means ignore
    # NaN cells for free via pandas mean() semantics (skipna=True by default).
    long = panel.stack(future_stack=True).rename("ret").reset_index()
    long.columns = ["date", "symbol", "ret"]
    long["sector"] = long["symbol"].map(clean_map)
    long = long.dropna(subset=["ret", "sector"])

    if long.empty:
        diag.warning(
            _SRC,
            "after dropping NaN returns and unmapped sectors, no observations remain — returning NaN series",
        )
        nan_series = pd.Series(
            np.full(len(daily_returns.index), np.nan),
            index=daily_returns.index,
            name="sector_neutral",
        )
        return nan_series, diag

    sector_day = long.groupby(["date", "sector"], sort=True)["ret"].mean()
    bench = sector_day.groupby("date").mean()
    bench.name = "sector_neutral"

    # Reindex to the original panel index so downstream benchmark_metrics sees
    # a canonical date axis (NaN on days where every sector was unobserved).
    bench = bench.reindex(daily_returns.index)

    n_valid = int(bench.notna().sum())
    n_total = int(len(bench))
    diag.info(
        _SRC,
        "sector_neutral benchmark built",
        n_dates=n_total,
        n_dates_non_nan=n_valid,
        n_sectors=int(clean_map.nunique()),
        n_symbols=len(overlap),
    )

    return bench, diag
