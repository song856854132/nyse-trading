"""Benchmark-relative diagnostic metrics for cross-sectional factor portfolios.

Pure leaf — returns ``(result, Diagnostics)`` and imports nothing from ``nyse_ats``
(no I/O). The goal of this module is to answer "how much of the factor portfolio's
Sharpe is alpha vs benchmark beta?" without altering gate logic. These metrics are
diagnostic only — they do not participate in the G0-G5 admission verdict.

The arithmetic is the smallest honest thing that can be computed. For each benchmark
``b`` in the provided mapping, compute:

    excess_ret   = portfolio_ret - benchmark_ret                     (aligned on index)
    mean_excess  = mean(excess_ret)
    std_excess   = stdev(excess_ret, ddof=1)
    sharpe_excess= mean_excess / std_excess * sqrt(annual_factor)
    beta         = cov(portfolio_ret, benchmark_ret) / var(benchmark_ret)
    alpha_daily  = mean_portfolio - beta * mean_benchmark
    alpha_ann    = alpha_daily * annual_factor           (arithmetic-annualized)
    tracking_err = std(excess_ret) * sqrt(annual_factor)
    info_ratio   = (mean_excess * annual_factor) / tracking_err
                 = sharpe_excess * sqrt(annual_factor) / sqrt(annual_factor) *
                   sqrt(annual_factor) / sqrt(annual_factor)      [same as sharpe_excess]

The caller is responsible for ensuring ``portfolio_returns`` and every entry in
``benchmark_returns`` share the same sampling horizon (daily, weekly, 5-day, etc.)
and the same annualization factor. For the factor-screening pipeline the inputs are
5-day forward returns sampled on weekly rebalance Fridays and the default
``annual_factor=252`` mirrors ``nyse_core.metrics.sharpe_ratio`` so diagnostics are
on the same scale as G0's ``oos_sharpe``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import TRADING_DAYS_PER_YEAR

_SRC = "benchmark_metrics"


def compute_benchmark_relative_metrics(
    portfolio_returns: pd.Series,
    benchmark_returns: dict[str, pd.Series],
    annual_factor: int = TRADING_DAYS_PER_YEAR,
) -> tuple[dict[str, dict[str, float]], Diagnostics]:
    """Compute benchmark-relative diagnostic metrics for every supplied benchmark.

    Parameters
    ----------
    portfolio_returns
        Series of per-period portfolio returns, indexed by period-end date.
    benchmark_returns
        Mapping ticker → Series of same-period benchmark returns, indexed by
        period-end date. Only index values that intersect ``portfolio_returns``
        participate in the computation; non-overlapping dates are dropped.
    annual_factor
        Annualization factor. Caller must supply the correct value for the input
        sampling cadence — default is ``TRADING_DAYS_PER_YEAR`` to match
        ``nyse_core.metrics.sharpe_ratio``.

    Returns
    -------
    tuple[dict[str, dict[str, float]], Diagnostics]
        Outer dict keyed by ticker; inner dict carries
        ``{sharpe_excess, mean_excess_ann, tracking_error_ann,
        information_ratio, beta, alpha_ann, n_obs}``. Missing / degenerate
        inputs (empty overlap, zero variance) return ``float('nan')`` for the
        affected keys and emit a warning. A ticker whose series cannot be
        aligned at all still appears in the output with ``n_obs=0`` so the
        caller can surface the gap in downstream artifacts.
    """
    diag = Diagnostics()
    out: dict[str, dict[str, float]] = {}

    port = portfolio_returns.dropna()
    if port.empty:
        diag.warning(_SRC, "portfolio_returns is empty after dropna — all benchmarks degenerate")
        for ticker in benchmark_returns:
            out[ticker] = _nan_payload(0)
        return out, diag

    mean_port_raw = float(port.mean())

    for ticker, bench_series in benchmark_returns.items():
        bench = bench_series.dropna()
        if bench.empty:
            diag.warning(_SRC, f"benchmark '{ticker}' empty — returning NaN payload")
            out[ticker] = _nan_payload(0)
            continue

        aligned = pd.concat([port, bench], axis=1, join="inner").dropna()
        if aligned.empty:
            diag.warning(
                _SRC,
                f"benchmark '{ticker}' has no overlap with portfolio_returns",
                ticker=ticker,
            )
            out[ticker] = _nan_payload(0)
            continue

        # Give the two columns canonical names regardless of input naming.
        aligned.columns = ["portfolio", "benchmark"]
        p = aligned["portfolio"]
        b = aligned["benchmark"]
        n = len(aligned)

        if n < 2:
            diag.warning(
                _SRC,
                f"benchmark '{ticker}' has only {n} overlapping obs — cannot compute",
                ticker=ticker,
                n=n,
            )
            out[ticker] = _nan_payload(n)
            continue

        excess = p - b
        mean_excess = float(excess.mean())
        std_excess = float(excess.std(ddof=1))

        if std_excess < 1e-15:
            diag.warning(
                _SRC,
                f"benchmark '{ticker}' excess-return std near zero — metrics may be unstable",
                ticker=ticker,
                std=std_excess,
            )
            sharpe_excess = 0.0
            tracking_error_ann = 0.0
            info_ratio = float("nan")
        else:
            sharpe_excess = mean_excess / std_excess * float(np.sqrt(annual_factor))
            tracking_error_ann = std_excess * float(np.sqrt(annual_factor))
            info_ratio = (mean_excess * annual_factor) / tracking_error_ann

        var_b = float(b.var(ddof=1))
        if var_b < 1e-15:
            diag.warning(
                _SRC,
                f"benchmark '{ticker}' return variance near zero — beta undefined",
                ticker=ticker,
                var=var_b,
            )
            beta = float("nan")
            alpha_ann = float("nan")
        else:
            cov_pb = float(p.cov(b, ddof=1))
            beta = cov_pb / var_b
            # alpha uses portfolio's mean over the FULL input, not just overlap,
            # only when overlap covers the whole portfolio window; otherwise use
            # the aligned means so the relationship is self-consistent.
            alpha_ann = (float(p.mean()) - beta * float(b.mean())) * annual_factor

        out[ticker] = {
            "sharpe_excess": sharpe_excess,
            "mean_excess_ann": mean_excess * annual_factor,
            "tracking_error_ann": tracking_error_ann,
            "information_ratio": info_ratio,
            "beta": beta,
            "alpha_ann": alpha_ann,
            "n_obs": float(n),
        }

    diag.info(
        _SRC,
        "benchmark_relative_metrics computed",
        n_benchmarks=len(benchmark_returns),
        n_portfolio_obs=len(port),
        portfolio_mean=mean_port_raw,
    )
    return out, diag


def _nan_payload(n: int) -> dict[str, float]:
    return {
        "sharpe_excess": float("nan"),
        "mean_excess_ann": float("nan"),
        "tracking_error_ann": float("nan"),
        "information_ratio": float("nan"),
        "beta": float("nan"),
        "alpha_ann": float("nan"),
        "n_obs": float(n),
    }
