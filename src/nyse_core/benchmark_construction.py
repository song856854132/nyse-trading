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

Characteristic-matched benchmark (iter-4)
-----------------------------------------
Given a per-(date, symbol) return panel, a characteristic (market-cap proxy,
book-to-market, 12-month momentum, etc.), and the factor portfolio's long-leg
weights, build a daily reference-return series whose style exposure matches
the long leg. Formally, for date *t*::

    ranks(t)       = qcut( characteristic(t, ·), n_buckets )          # 1..n
    bucket_mean(t, k) = mean_{sym in bucket k, ret(t, sym) not NaN}( ret(t, sym) )
    wbar(t)        = sum_{sym in long_leg(t)} w(t, sym) * bucket(t, sym)
                   / sum_{sym in long_leg(t)} w(t, sym)
    matched(t)     = clip( round(wbar(t)), 1, n_buckets )
    r_bench(t)     = bucket_mean(t, matched(t))

This removes style-composition tilt: a long leg concentrated in the top-size
bucket is compared against that bucket's equal-weight mean, so the
stock-selection alpha must justify itself *within* a matched style sleeve
rather than against a broad-universe benchmark that penalizes/rewards the
sleeve choice.

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


def compute_characteristic_matched_benchmark(
    daily_returns: pd.DataFrame,
    characteristic_panel: pd.DataFrame,
    long_leg_weights: pd.DataFrame,
    n_buckets: int = 5,
) -> tuple[pd.Series, Diagnostics]:
    """Build a style-matched reference-return series using quantile buckets.

    For each date, the universe is split into ``n_buckets`` quantile buckets by
    the characteristic. The long leg's weighted-mean bucket index is rounded to
    the nearest integer bucket, and that bucket's equal-weight return is used
    as the benchmark. See the module docstring for the full formula.

    Parameters
    ----------
    daily_returns
        Wide DataFrame with ``index`` = rebalance date and ``columns`` =
        symbols. Values are per-period returns (decimal). NaN cells are
        excluded from bucket means.
    characteristic_panel
        Long-form DataFrame with required columns ``date``, ``symbol``, and
        ``value``. One characteristic value per (date, symbol). Duplicate rows
        for the same (date, symbol) keep the first occurrence. Symbols with a
        NaN ``value`` on a given date are excluded from bucketing for that
        date.
    long_leg_weights
        Long-form DataFrame with required columns ``date``, ``symbol``, and
        ``weight``. Positive weights expected — callers matching a long-short
        portfolio should filter to ``weight > 0`` upstream. Symbols without a
        characteristic value on the matching date are excluded from the
        weighted-mean bucket calculation for that date.
    n_buckets
        Number of quantile buckets (>= 1). Ties in the characteristic are
        broken by ``rank(method="first")`` so bucket assignment is
        deterministic. ``n_buckets=1`` collapses to the universe mean.

    Returns
    -------
    tuple[pd.Series, Diagnostics]
        Series indexed like ``daily_returns.index`` (name ``char_matched``).
        Dates without a usable bucket match (missing characteristic, empty
        long-leg overlap, zero weight-sum, etc.) degrade to NaN rather than
        raising. Diagnostics carries per-degenerate-input warnings plus an
        info summary.
    """
    diag = Diagnostics()

    if n_buckets < 1:
        diag.warning(
            _SRC,
            f"n_buckets={n_buckets} must be >= 1 — returning empty series",
            n_buckets=int(n_buckets),
        )
        return pd.Series(dtype=float, name="char_matched"), diag

    if daily_returns.empty:
        diag.warning(_SRC, "daily_returns is empty — returning empty series")
        return pd.Series(dtype=float, name="char_matched"), diag

    def _nan_series() -> pd.Series:
        return pd.Series(
            np.full(len(daily_returns.index), np.nan),
            index=daily_returns.index,
            name="char_matched",
        )

    required_char_cols = {"date", "symbol", "value"}
    missing_char = required_char_cols - set(characteristic_panel.columns)
    if missing_char:
        diag.warning(
            _SRC,
            f"characteristic_panel missing required columns {sorted(missing_char)} — returning NaN series",
            missing_cols=sorted(missing_char),
        )
        return _nan_series(), diag

    required_w_cols = {"date", "symbol", "weight"}
    missing_w = required_w_cols - set(long_leg_weights.columns)
    if missing_w:
        diag.warning(
            _SRC,
            f"long_leg_weights missing required columns {sorted(missing_w)} — returning NaN series",
            missing_cols=sorted(missing_w),
        )
        return _nan_series(), diag

    if characteristic_panel.empty:
        diag.warning(
            _SRC,
            "characteristic_panel is empty — returning NaN series",
        )
        return _nan_series(), diag

    if long_leg_weights.empty:
        diag.warning(
            _SRC,
            "long_leg_weights is empty — returning NaN series",
        )
        return _nan_series(), diag

    char = characteristic_panel.loc[:, ["date", "symbol", "value"]].copy()
    char["date"] = pd.to_datetime(char["date"])
    char = char.dropna(subset=["value"])

    weights = long_leg_weights.loc[:, ["date", "symbol", "weight"]].copy()
    weights["date"] = pd.to_datetime(weights["date"])
    weights = weights.dropna(subset=["weight"])

    out = _nan_series()

    n_populated = 0
    n_date_no_char = 0
    n_date_no_overlap = 0
    n_date_no_weight = 0
    n_date_no_returns = 0

    panel_symbols = set(daily_returns.columns)

    for date_ix in daily_returns.index:
        date_ts = pd.Timestamp(date_ix)
        char_t = char[char["date"] == date_ts]
        if char_t.empty:
            n_date_no_char += 1
            continue

        char_t = char_t.drop_duplicates(subset="symbol", keep="first")
        overlap = panel_symbols & set(char_t["symbol"])
        if not overlap:
            n_date_no_overlap += 1
            continue

        char_t = char_t[char_t["symbol"].isin(overlap)].set_index("symbol")["value"]

        # Deterministic bucketing: rank-then-qcut breaks ties by first occurrence
        # so identical characteristic values do not silently land in the same
        # bucket (which would leave bucket-membership ambiguous).
        if n_buckets == 1 or char_t.nunique() < 2:
            buckets = pd.Series(
                np.ones(len(char_t), dtype=int),
                index=char_t.index,
                name="bucket",
            )
            effective_buckets = 1
        else:
            effective_buckets = min(n_buckets, char_t.nunique())
            try:
                ranked = char_t.rank(method="first")
                cut = pd.qcut(
                    ranked,
                    q=effective_buckets,
                    labels=list(range(1, effective_buckets + 1)),
                )
                buckets = pd.Series(
                    cut.astype(int).to_numpy(),
                    index=char_t.index,
                    name="bucket",
                )
            except ValueError:
                n_date_no_char += 1
                continue

        returns_row = daily_returns.loc[date_ix]
        returns_row = returns_row.reindex(buckets.index)
        bucket_frame = pd.DataFrame({"ret": returns_row, "bucket": buckets}).dropna(subset=["ret"])
        if bucket_frame.empty:
            n_date_no_returns += 1
            continue

        bucket_means = bucket_frame.groupby("bucket", observed=True)["ret"].mean()

        w_t = weights[weights["date"] == date_ts]
        if w_t.empty:
            n_date_no_weight += 1
            continue

        w_t = w_t.drop_duplicates(subset="symbol", keep="first")
        w_t = w_t[w_t["symbol"].isin(buckets.index)]
        if w_t.empty:
            n_date_no_weight += 1
            continue

        w_series = w_t.set_index("symbol")["weight"]
        w_sum = float(w_series.sum())
        if abs(w_sum) < 1e-15:
            n_date_no_weight += 1
            continue

        bucket_idx_for_long = buckets.loc[w_series.index].astype(float)
        weighted_mean_bucket = float((w_series * bucket_idx_for_long).sum() / w_sum)

        matched = int(round(weighted_mean_bucket))
        matched = max(1, min(effective_buckets, matched))

        if matched in bucket_means.index:
            out.loc[date_ix] = float(bucket_means.loc[matched])
        else:
            # Matched bucket has no non-NaN return this date — fall back to the
            # nearest observed bucket so we never silently drop the date when a
            # bucket-mean can still be approximated.
            available = sorted(int(k) for k in bucket_means.index)
            target: int = matched
            nearest = min(available, key=lambda b: abs(b - target))
            out.loc[date_ix] = float(bucket_means.loc[nearest])

        n_populated += 1

    diag.info(
        _SRC,
        "char_matched benchmark built",
        n_dates=int(len(out)),
        n_dates_populated=int(n_populated),
        n_dates_degenerate_no_char=int(n_date_no_char),
        n_dates_degenerate_no_overlap=int(n_date_no_overlap),
        n_dates_degenerate_no_weight=int(n_date_no_weight),
        n_dates_degenerate_no_returns=int(n_date_no_returns),
        n_buckets=int(n_buckets),
    )
    return out, diag
