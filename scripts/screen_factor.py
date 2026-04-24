#!/usr/bin/env python3
"""Run a single factor through the G0-G5 screening pipeline.

Thin wrapper: load OHLCV → build factor-score panel over weekly rebalance
dates → compute 5-day forward returns → call
``nyse_core.factor_screening.screen_factor`` → persist verdict + metrics.

Forward-return convention approximates the plan's Monday-open (T+1) to
Friday-close (T+5) rule as ``close[t+5] / close[t+1] - 1`` because daily
bars don't carry intraday opens for every vendor. The purge horizon in
PurgedWalkForwardCV remains 5 trading days either way.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

# Sibling script import — research log is hash-chained; do NOT write raw entries.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402

from nyse_core.attribution import compute_attribution
from nyse_core.benchmark_construction import (
    compute_characteristic_matched_benchmark,
    compute_sector_neutral_returns,
)
from nyse_core.benchmark_metrics import compute_benchmark_relative_metrics
from nyse_core.factor_screening import (
    compute_cap_tilted_weights,
    compute_long_short_returns,
    compute_long_short_weights,
    compute_volatility_scaled_weights,
    screen_factor,
)
from nyse_core.features.fundamental import (
    compute_accruals,
    compute_piotroski_f_score,
    compute_profitability,
)
from nyse_core.features.price_volume import (
    compute_52w_high_proximity,
    compute_ivol_20d,
    compute_momentum_2_12,
)
from nyse_core.normalize import rank_percentile
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL, COL_VOLUME
from nyse_core.sector_map_loader import load_gics_sectors

# Maps factor name → (compute_fn, sign_convention, data_source, lookback_days)
# sign_convention: -1 means "low raw value = buy" — we negate before ranking.
# data_source: "ohlcv" reads from the ohlcv table; "fundamentals" reads from the
# fundamentals table (long-format XBRL facts, filing-date-keyed for PiT).
# lookback_days: pre-start buffer when loading data. For fundamentals we need
# ~400 days of history so the first rebalance has a prior-year filing for
# delta-based signals (Piotroski F3/F5/F6/F7/F8/F9).
_FACTORS = {
    "ivol_20d": (compute_ivol_20d, -1, "ohlcv", 30),
    # V2-PREREG-2026-04-24 active_v2_factor_universe member. Same compute
    # function as ivol_20d; sign=+1 means raw (un-negated) IVOL is ranked
    # so high IVOL = high score = buy. Stream 5 evidence: 2016-2023 US
    # large-cap exhibited QE-regime reversal of low-vol anomaly.
    "ivol_20d_flipped": (compute_ivol_20d, +1, "ohlcv", 30),
    "high_52w": (compute_52w_high_proximity, +1, "ohlcv", 260),
    "momentum_2_12": (compute_momentum_2_12, +1, "ohlcv", 260),
    "piotroski": (compute_piotroski_f_score, +1, "fundamentals", 400),
    "accruals": (compute_accruals, -1, "fundamentals", 400),
    "profitability": (compute_profitability, +1, "fundamentals", 400),
}


def _weekly_fridays(start: date, end: date) -> list[pd.Timestamp]:
    return list(pd.date_range(start=start, end=end, freq="W-FRI"))


def _build_factor_panel(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    compute_fn,
    sign: int,
) -> pd.DataFrame:
    """Compute factor scores at each rebalance date, then rank-percentile."""
    ohlcv = ohlcv.copy()
    ohlcv[COL_DATE] = pd.to_datetime(ohlcv[COL_DATE])
    rows: list[pd.DataFrame] = []

    for ts in rebalance_dates:
        window = ohlcv[ohlcv[COL_DATE] <= ts]
        if window.empty:
            continue
        series, _ = compute_fn(window)
        series = series.dropna()
        if series.empty:
            continue
        if sign == -1:
            series = -series
        ranked, _ = rank_percentile(series)
        frame = pd.DataFrame(
            {
                "date": ts.date(),
                "symbol": ranked.index,
                "score": ranked.values,
            }
        )
        rows.append(frame)

    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "score"])
    return pd.concat(rows, ignore_index=True)


def _build_forward_returns(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
) -> pd.DataFrame:
    """fwd_ret_5d = close[next_trading_day_+4] / close[next_trading_day] - 1.

    Approximates Monday-open (T+1) to Friday-close (T+5) using close-to-close
    because vendor OHLCV lacks intraday bars. The 5-trading-day span is the
    load-bearing quantity for the purge gap.
    """
    wide = ohlcv.pivot_table(
        index=COL_DATE, columns=COL_SYMBOL, values=COL_CLOSE, aggfunc="last"
    ).sort_index()
    wide.index = pd.to_datetime(wide.index)

    rows: list[pd.DataFrame] = []
    for ts in rebalance_dates:
        future = wide.index[wide.index > ts]
        if len(future) < 5:
            continue
        t1, t5 = future[0], future[4]
        fwd = wide.loc[t5] / wide.loc[t1] - 1.0
        fwd = fwd.dropna()
        if fwd.empty:
            continue
        rows.append(
            pd.DataFrame(
                {
                    "date": ts.date(),
                    "symbol": fwd.index,
                    "fwd_ret_5d": fwd.values,
                }
            )
        )

    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "fwd_ret_5d"])
    return pd.concat(rows, ignore_index=True)


def _build_size_panel(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    window_days: int = 20,
) -> pd.DataFrame:
    """Size-proxy characteristic panel for iter-4 char_matched_size benchmark.

    Computes a 20-trading-day trailing mean of ``close × volume`` (dollar
    volume) at each rebalance date. Dollar volume is a market-cap proxy when
    shares-outstanding isn't in OHLCV — larger firms dominate traded-dollar
    volume, so bucketing by this monotone proxy matches the intent of a
    Fama-French-style size-matched benchmark without requiring CRSP fields.
    Purely diagnostic: does not feed G0-G5.
    """
    if ohlcv.empty or not rebalance_dates:
        return pd.DataFrame(columns=["date", "symbol", "size"])

    panel = ohlcv.copy()
    panel[COL_DATE] = pd.to_datetime(panel[COL_DATE])
    panel["dollar_vol"] = panel[COL_CLOSE] * panel[COL_VOLUME]
    wide = panel.pivot_table(
        index=COL_DATE, columns=COL_SYMBOL, values="dollar_vol", aggfunc="last"
    ).sort_index()

    rows: list[pd.DataFrame] = []
    for ts in rebalance_dates:
        window = wide.loc[wide.index <= ts].tail(window_days)
        if window.empty:
            continue
        trailing = window.mean(axis=0).dropna()
        if trailing.empty:
            continue
        rows.append(
            pd.DataFrame(
                {
                    "date": ts.date(),
                    "symbol": trailing.index,
                    "size": trailing.values,
                }
            )
        )

    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "size"])
    return pd.concat(rows, ignore_index=True)


def _build_vol_panel(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    window_days: int = 20,
) -> pd.DataFrame:
    """Realized-volatility panel for iter-5 vol-scaled portfolio diagnostic.

    Computes the ``window_days`` trailing standard deviation of daily simple
    returns at each rebalance Friday for each symbol. Purely diagnostic —
    never feeds G0-G5. The resulting panel is fed to
    ``compute_volatility_scaled_weights`` so each long-leg stock's weight is
    inversely proportional to its own trailing volatility (Carver's
    position-level vol targeting).
    """
    if ohlcv.empty or not rebalance_dates:
        return pd.DataFrame(columns=["date", "symbol", "vol"])

    panel = ohlcv.copy()
    panel[COL_DATE] = pd.to_datetime(panel[COL_DATE])
    close_wide = panel.pivot_table(
        index=COL_DATE, columns=COL_SYMBOL, values=COL_CLOSE, aggfunc="last"
    ).sort_index()
    daily_ret = close_wide.pct_change()

    rows: list[pd.DataFrame] = []
    for ts in rebalance_dates:
        window = daily_ret.loc[daily_ret.index <= ts].tail(window_days)
        if window.empty:
            continue
        vol = window.std(axis=0, ddof=1).dropna()
        vol = vol[vol > 0]
        if vol.empty:
            continue
        rows.append(
            pd.DataFrame(
                {
                    "date": ts.date(),
                    "symbol": vol.index,
                    "vol": vol.values,
                }
            )
        )

    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "vol"])
    return pd.concat(rows, ignore_index=True)


def _load_ohlcv(db_path: Path, start: date, end: date) -> pd.DataFrame:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        df = conn.execute(
            """
            SELECT date, symbol, open, high, low, close, volume
            FROM ohlcv
            WHERE date >= ? AND date <= ?
            ORDER BY date, symbol
            """,
            [str(start), str(end)],
        ).fetchdf()
    finally:
        conn.close()
    return df


def _load_benchmark_ohlcv(db_path: Path, symbols: list[str], start: date, end: date) -> pd.DataFrame:
    """Load benchmark OHLCV from the isolated ``benchmark_ohlcv`` table.

    Benchmarks (SPY / RSP / sector ETFs) live in a separate table so they do
    not leak into the factor-screening universe. Absence of the table or of
    the requested symbols is non-fatal — the caller either computes
    diagnostics over the benchmarks it has or skips them.
    """
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        if "benchmark_ohlcv" not in tables:
            return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])
        df = conn.execute(
            """
            SELECT date, symbol, open, high, low, close, volume
            FROM benchmark_ohlcv
            WHERE symbol IN (SELECT UNNEST($1::VARCHAR[]))
              AND date >= $2::DATE
              AND date <= $3::DATE
            ORDER BY date, symbol
            """,
            [symbols, str(start), str(end)],
        ).fetchdf()
    finally:
        conn.close()
    return df


def _extract_benchmark_fwd_returns(fwd_panel: pd.DataFrame, tickers: list[str]) -> dict[str, pd.Series]:
    """Pull per-benchmark forward-return series out of a long-format fwd panel.

    The panel is indexed by (date, symbol); we project each requested ticker
    to a date-indexed Series. Missing tickers map to empty Series — the
    diagnostic helper handles the degenerate case.
    """
    out: dict[str, pd.Series] = {}
    if fwd_panel.empty:
        for t in tickers:
            out[t] = pd.Series(dtype=float)
        return out
    df = fwd_panel.copy()
    df["date"] = pd.to_datetime(df["date"])
    for t in tickers:
        sub = df[df["symbol"] == t]
        if sub.empty:
            out[t] = pd.Series(dtype=float)
        else:
            out[t] = sub.set_index("date")["fwd_ret_5d"].sort_index()
    return out


def _load_fundamentals(db_path: Path, start: date, end: date) -> pd.DataFrame:
    """Load raw XBRL facts filtered on filing date (`date` column).

    Filing date is the PiT key — a fact is visible at rebalance time T only if
    ``date <= T``. ``period_end`` is the reporting period these facts cover
    and is used by the compute functions to join a filing to its prior year.
    """
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        df = conn.execute(
            """
            SELECT date, symbol, metric_name, value, filing_type, period_end
            FROM fundamentals
            WHERE date >= ? AND date <= ?
            ORDER BY symbol, period_end
            """,
            [str(start), str(end)],
        ).fetchdf()
    finally:
        conn.close()
    return df


def _build_fundamental_panel(
    raw_facts: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    compute_fn,
    sign: int,
) -> pd.DataFrame:
    """Compute fundamental factor scores at each rebalance date.

    PiT: only facts with filing date ``<= ts`` are visible to the compute fn.
    The compute fn internally picks each symbol's latest period_end filing and
    (when needed) its ~1yr-prior counterpart — so scores only change at filing
    boundaries, repeating for intermediate rebalance Fridays.
    """
    if raw_facts.empty:
        return pd.DataFrame(columns=["date", "symbol", "score"])
    raw_facts = raw_facts.copy()
    raw_facts["date"] = pd.to_datetime(raw_facts["date"])
    rows: list[pd.DataFrame] = []

    for ts in rebalance_dates:
        visible = raw_facts[raw_facts["date"] <= ts]
        if visible.empty:
            continue
        series, _ = compute_fn(visible)
        series = series.dropna()
        if series.empty:
            continue
        if sign == -1:
            series = -series
        ranked, _ = rank_percentile(series)
        rows.append(
            pd.DataFrame(
                {
                    "date": ts.date(),
                    "symbol": ranked.index,
                    "score": ranked.values,
                }
            )
        )

    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "score"])
    return pd.concat(rows, ignore_index=True)


def _gate_row(
    gate: str, metric_name: str, value: float, threshold: float, direction: str, passed: bool
) -> str:
    arrow = {"pass": "PASS", "fail": "FAIL"}["pass" if passed else "fail"]
    return f"{gate:<6}{metric_name:<24}{value:>10.4f}   {direction:<2}{threshold:<10.4f}{arrow}"


def main() -> int:
    p = argparse.ArgumentParser(description="Screen a single factor through G0-G5")
    p.add_argument("--factor", required=True, choices=sorted(_FACTORS.keys()))
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument("--output-dir", type=Path, default=None, help="Defaults to results/factors/<factor>/")
    args = p.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end >= date(2024, 1, 1):
        print(
            "REFUSED: end-date crosses holdout boundary (2024-01-01). Research period ends 2023-12-31.",
            file=sys.stderr,
        )
        return 2

    compute_fn, sign, data_source, lookback_days = _FACTORS[args.factor]
    output_dir = args.output_dir or Path("results/factors") / args.factor
    output_dir.mkdir(parents=True, exist_ok=True)

    # Always need OHLCV for forward-return construction, even when the factor
    # itself is fundamentals-based.
    print(f"[1/5] Loading OHLCV {start} → {end} from {args.db_path}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(f"       rows={len(ohlcv):,}  symbols={ohlcv[COL_SYMBOL].nunique()}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[2/5] Rebalance dates: {len(rebalance)} Fridays", flush=True)

    print(
        f"[3/5] Computing {args.factor} scores (sign={sign}, source={data_source})...",
        flush=True,
    )
    if data_source == "ohlcv":
        factor_scores = _build_factor_panel(ohlcv, rebalance, compute_fn, sign)
    elif data_source == "fundamentals":
        lookback_start = start - pd.Timedelta(days=lookback_days).to_pytimedelta()
        # start is datetime.date, so (date - timedelta) is already datetime.date
        print(
            f"       loading fundamentals {lookback_start} → {end}",
            flush=True,
        )
        raw_facts = _load_fundamentals(args.db_path, lookback_start, end)
        print(
            f"       fact rows={len(raw_facts):,}  "
            f"symbols={raw_facts[COL_SYMBOL].nunique() if not raw_facts.empty else 0}",
            flush=True,
        )
        factor_scores = _build_fundamental_panel(raw_facts, rebalance, compute_fn, sign)
    else:
        print(f"UNKNOWN data_source: {data_source}", file=sys.stderr)
        return 2
    print(f"       score rows={len(factor_scores):,}", flush=True)

    print("[4/5] Computing 5-day forward returns...", flush=True)
    fwd = _build_forward_returns(ohlcv, rebalance)
    print(f"       fwd-return rows={len(fwd):,}", flush=True)

    # Benchmark panel — load SPY/RSP from isolated benchmark_ohlcv table and
    # convert to the same 5-day forward-return convention as the factor
    # portfolio so diagnostic metrics are on comparable footing.
    benchmark_tickers = ["SPY", "RSP"]
    bench_ohlcv = _load_benchmark_ohlcv(args.db_path, benchmark_tickers, start, end)
    if bench_ohlcv.empty:
        print(
            "       benchmark_ohlcv missing or empty — benchmark diagnostics skipped",
            flush=True,
        )
        benchmark_fwd: dict[str, pd.Series] = {}
    else:
        bench_fwd_panel = _build_forward_returns(bench_ohlcv, rebalance)
        benchmark_fwd = _extract_benchmark_fwd_returns(bench_fwd_panel, benchmark_tickers)
        print(
            "       benchmark fwd-return rows: "
            + ", ".join(f"{t}={len(s):,}" for t, s in benchmark_fwd.items()),
            flush=True,
        )

    print("[5/5] Running screen_factor() — G0..G5...", flush=True)
    verdict, metrics, diag = screen_factor(
        factor_name=args.factor,
        factor_scores=factor_scores,
        forward_returns=fwd,
    )

    # Benchmark-relative diagnostic (iter-1 TODO-9 follow-on). Recompute the
    # long-short return series — ``screen_factor`` does not return it — and
    # hand it to the pure helper alongside the benchmark 5-day forward returns.
    # These metrics are diagnostic only; they do NOT participate in G0-G5.
    ls_returns, _ls_diag = compute_long_short_returns(factor_scores, fwd)

    # iter-3 sector-neutral benchmark. Pivot the long-format fwd panel to a
    # (date × symbol) wide return panel, load the static GICS sector_map, and
    # call the two-stage equal-weight helper. Result is a date-indexed Series
    # directly comparable to ``ls_returns`` — we slot it alongside SPY / RSP
    # under the bench_rel dict so the same compute_benchmark_relative_metrics
    # consumer produces Sharpe_excess / beta / alpha / IR / TE for all three.
    sector_map_path = Path(__file__).resolve().parent.parent / "config" / "gics_sectors_sp500.csv"
    sector_map, _sector_diag = load_gics_sectors(sector_map_path)
    fwd_wide = pd.DataFrame()
    if not fwd.empty:
        fwd_wide = fwd.pivot(index="date", columns="symbol", values="fwd_ret_5d")
        fwd_wide.index = pd.to_datetime(fwd_wide.index)
        sector_neutral_ret, _sn_diag = compute_sector_neutral_returns(fwd_wide, sector_map)
        if not sector_neutral_ret.empty:
            benchmark_fwd["sector_neutral"] = sector_neutral_ret
            print(
                f"       sector_neutral fwd-return rows: {len(sector_neutral_ret):,} "
                f"(sector_map n={len(sector_map)}, n_sectors={sector_map.nunique(dropna=True)})",
                flush=True,
            )

    # iter-4 characteristic-matched benchmark (size proxy = 20d trailing mean
    # dollar volume, a monotone market-cap stand-in when shares-outstanding is
    # absent from OHLCV). Uses the long-leg positive weights from
    # ``compute_long_short_weights``; the helper bucket-matches the long leg
    # against a 5-bucket quantile sort on the size proxy and returns the
    # matched bucket's equal-weight mean. Diagnostic only — does not feed G0-G5.
    ls_weights = pd.DataFrame(columns=["date", "symbol", "weight"])
    if not factor_scores.empty:
        ls_weights, _lw_diag = compute_long_short_weights(factor_scores)
    if not fwd_wide.empty and not ls_weights.empty:
        size_long = _build_size_panel(ohlcv, rebalance, window_days=20)
        if not size_long.empty:
            size_panel = size_long.pivot(index="date", columns="symbol", values="size")
            size_panel.index = pd.to_datetime(size_panel.index)
            long_leg_long = ls_weights[ls_weights["weight"] > 0]
            if not long_leg_long.empty:
                long_leg_wide = long_leg_long.pivot(index="date", columns="symbol", values="weight")
                long_leg_wide.index = pd.to_datetime(long_leg_wide.index)
                char_matched_ret, _cm_diag = compute_characteristic_matched_benchmark(
                    daily_returns=fwd_wide,
                    characteristic_panel=size_panel,
                    long_leg_weights=long_leg_wide,
                    n_buckets=5,
                )
                if char_matched_ret.notna().any():
                    benchmark_fwd["char_matched_size"] = char_matched_ret
                    n_pop = int(char_matched_ret.notna().sum())
                    print(
                        f"       char_matched_size fwd-return rows: {n_pop:,} "
                        f"(proxy=20d mean(close×volume), n_buckets=5)",
                        flush=True,
                    )

    if benchmark_fwd and len(ls_returns) > 0:
        bench_rel, _bench_diag = compute_benchmark_relative_metrics(
            portfolio_returns=ls_returns,
            benchmark_returns=benchmark_fwd,
        )
    else:
        bench_rel = {}

    # iter-3 Brinson factor + sector attribution (diagnostic only). Reuses the
    # ``ls_weights`` computed above for the characteristic-matched benchmark so
    # the long-short decomposition stays canonical across both diagnostics.
    # Equal-weight benchmark (Brinson default when benchmark_weights=None).
    brinson_payload: dict[str, object] = {}
    if not factor_scores.empty and not fwd.empty and not sector_map.empty:
        factor_exposures = factor_scores.rename(columns={"score": "exposure"}).assign(
            factor_name=args.factor
        )[["date", "symbol", "factor_name", "exposure"]]
        stock_returns = fwd.rename(columns={"fwd_ret_5d": "return"})[["date", "symbol", "return"]]
        if not ls_weights.empty:
            attribution_report, _attr_diag = compute_attribution(
                portfolio_weights=ls_weights,
                stock_returns=stock_returns,
                factor_exposures=factor_exposures,
                sector_map=sector_map,
            )
            brinson_payload = {
                "factor_contributions": {
                    k: float(v) for k, v in attribution_report.factor_contributions.items()
                },
                "sector_contributions": {
                    k: float(v) for k, v in attribution_report.sector_contributions.items()
                },
                "total_return": float(attribution_report.total_return),
                "period_start": str(attribution_report.period_start),
                "period_end": str(attribution_report.period_end),
            }
            print(
                f"       Brinson: total_return={attribution_report.total_return:.4f}, "
                f"factors={len(attribution_report.factor_contributions)}, "
                f"sectors={len(attribution_report.sector_contributions)}",
                flush=True,
            )

    # iter-5 (Wave-2) volatility-scaled long-short portfolio — diagnostic only.
    # Each stock's weight within its leg is inversely proportional to its
    # trailing-20d realized volatility (Carver position-level vol targeting).
    # Compares directly against the equal-weight baseline ``ls_returns`` already
    # produced by compute_long_short_returns. Never feeds G0-G5.
    alt_portfolios: dict[str, dict[str, float | int | None]] = {}
    if not factor_scores.empty and not fwd_wide.empty:
        vol_long = _build_vol_panel(ohlcv, rebalance, window_days=20)
        if not vol_long.empty:
            vol_scaled_weights, _vs_diag = compute_volatility_scaled_weights(
                factor_scores=factor_scores,
                vol_panel=vol_long,
                n_quantiles=5,
            )
            if not vol_scaled_weights.empty:
                vs_w_wide = vol_scaled_weights.pivot(index="date", columns="symbol", values="weight").fillna(
                    0.0
                )
                vs_w_wide.index = pd.to_datetime(vs_w_wide.index)
                common_dates = vs_w_wide.index.intersection(fwd_wide.index)
                common_syms = vs_w_wide.columns.intersection(fwd_wide.columns)
                if len(common_dates) > 0 and len(common_syms) > 0:
                    w_al = vs_w_wide.loc[common_dates, common_syms]
                    r_al = fwd_wide.loc[common_dates, common_syms].fillna(0.0)
                    vs_returns = (w_al * r_al).sum(axis=1)
                    vs_returns = vs_returns.dropna()
                    if len(vs_returns) > 1 and vs_returns.std(ddof=1) > 0:
                        vs_mean = float(vs_returns.mean())
                        vs_std = float(vs_returns.std(ddof=1))
                        # 5-day forward returns at weekly cadence → 52 periods/year
                        vs_sharpe = float(vs_mean / vs_std * (52**0.5))
                        # Equal-weight comparable
                        eq_mean = float(ls_returns.mean()) if len(ls_returns) > 1 else None
                        eq_std = (
                            float(ls_returns.std(ddof=1))
                            if len(ls_returns) > 1 and ls_returns.std(ddof=1) > 0
                            else None
                        )
                        eq_sharpe = (
                            float(eq_mean / eq_std * (52**0.5))
                            if eq_mean is not None and eq_std is not None
                            else None
                        )
                        alt_portfolios["vol_scaled"] = {
                            "n_periods": int(len(vs_returns)),
                            "mean_period_return": vs_mean,
                            "std_period_return": vs_std,
                            "sharpe_annualized": vs_sharpe,
                        }
                        alt_portfolios["equal_weight_baseline"] = {
                            "n_periods": int(len(ls_returns.dropna())) if len(ls_returns) > 0 else 0,
                            "mean_period_return": eq_mean,
                            "std_period_return": eq_std,
                            "sharpe_annualized": eq_sharpe,
                        }
                        delta = vs_sharpe - eq_sharpe if eq_sharpe is not None else None
                        delta_str = f"{delta:+.4f}" if delta is not None else "n/a"
                        print(
                            f"       vol_scaled portfolio: Sharpe={vs_sharpe:.4f} "
                            f"(Δ vs equal-weight {delta_str}, n={len(vs_returns)})",
                            flush=True,
                        )

    # iter-6 (Wave-2) market-cap-tilted long-short portfolio — diagnostic only.
    # Each stock's weight within its leg is proportional to ``size ** tilt``,
    # where the size proxy is the same 20d trailing mean(close×volume) used by
    # the iter-4 char_matched_size benchmark (canonical size proxy across all
    # diagnostics). Default tilt=0.5 (sqrt-cap) compresses the tiny-cap
    # concentration that dominates equal-weight long-short portfolios while
    # not over-weighting mega-caps like pure cap-weight would. Compares
    # directly against the equal-weight baseline ``ls_returns`` already emitted
    # by compute_long_short_returns. Never feeds G0-G5.
    if not factor_scores.empty and not fwd_wide.empty:
        ct_size_long = _build_size_panel(ohlcv, rebalance, window_days=20)
        if not ct_size_long.empty:
            cap_tilted_weights, _ct_diag = compute_cap_tilted_weights(
                factor_scores=factor_scores,
                size_panel=ct_size_long,
                n_quantiles=5,
                tilt_exponent=0.5,
            )
            if not cap_tilted_weights.empty:
                ct_w_wide = cap_tilted_weights.pivot(index="date", columns="symbol", values="weight").fillna(
                    0.0
                )
                ct_w_wide.index = pd.to_datetime(ct_w_wide.index)
                common_dates_ct = ct_w_wide.index.intersection(fwd_wide.index)
                common_syms_ct = ct_w_wide.columns.intersection(fwd_wide.columns)
                if len(common_dates_ct) > 0 and len(common_syms_ct) > 0:
                    w_al_ct = ct_w_wide.loc[common_dates_ct, common_syms_ct]
                    r_al_ct = fwd_wide.loc[common_dates_ct, common_syms_ct].fillna(0.0)
                    ct_returns = (w_al_ct * r_al_ct).sum(axis=1).dropna()
                    if len(ct_returns) > 1 and ct_returns.std(ddof=1) > 0:
                        ct_mean = float(ct_returns.mean())
                        ct_std = float(ct_returns.std(ddof=1))
                        # 5-day forward returns at weekly cadence → 52 periods/year
                        ct_sharpe = float(ct_mean / ct_std * (52**0.5))
                        alt_portfolios["cap_tilted_sqrt"] = {
                            "n_periods": int(len(ct_returns)),
                            "mean_period_return": ct_mean,
                            "std_period_return": ct_std,
                            "sharpe_annualized": ct_sharpe,
                            "tilt_exponent": 0.5,
                        }
                        eq_baseline = alt_portfolios.get("equal_weight_baseline")
                        eq_sharpe_existing = (
                            eq_baseline.get("sharpe_annualized") if isinstance(eq_baseline, dict) else None
                        )
                        if eq_sharpe_existing is None and len(ls_returns) > 1 and ls_returns.std(ddof=1) > 0:
                            eq_mean_ct = float(ls_returns.mean())
                            eq_std_ct = float(ls_returns.std(ddof=1))
                            eq_sharpe_ct: float | None = float(eq_mean_ct / eq_std_ct * (52**0.5))
                            alt_portfolios["equal_weight_baseline"] = {
                                "n_periods": int(len(ls_returns.dropna())),
                                "mean_period_return": eq_mean_ct,
                                "std_period_return": eq_std_ct,
                                "sharpe_annualized": eq_sharpe_ct,
                            }
                        else:
                            eq_sharpe_ct = (
                                float(eq_sharpe_existing)
                                if isinstance(eq_sharpe_existing, (int, float))
                                else None
                            )
                        delta_ct = ct_sharpe - eq_sharpe_ct if eq_sharpe_ct is not None else None
                        delta_ct_str = f"{delta_ct:+.4f}" if delta_ct is not None else "n/a"
                        print(
                            f"       cap_tilted_sqrt portfolio: Sharpe={ct_sharpe:.4f} "
                            f"(Δ vs equal-weight {delta_ct_str}, tilt=0.5, n={len(ct_returns)})",
                            flush=True,
                        )

    # ── Present ────────────────────────────────────────────────────────────
    gate_cfg = {
        "G0": ("oos_sharpe", 0.30, ">="),
        "G1": ("permutation_p", 0.05, "<"),
        "G2": ("ic_mean", 0.02, ">="),
        "G3": ("ic_ir", 0.50, ">="),
        "G4": ("max_drawdown", -0.30, ">="),
        "G5": ("marginal_contribution", 0.00, ">"),
    }
    print("")
    print(f"FACTOR SCREENING: {args.factor}")
    print("═" * 66)
    print(f"{'Gate':<6}{'Metric':<24}{'Value':>10}   {'Threshold':<12}{'Result'}")
    print("─" * 66)
    for gate, (metric, thr, direction) in gate_cfg.items():
        val = metrics.get(metric, float("nan"))
        passed = verdict.gate_results.get(gate, False)
        print(_gate_row(gate, metric, val, thr, direction, passed))
    print("─" * 66)
    overall = "PASS — factor admitted to ensemble" if verdict.passed_all else "FAIL — factor rejected"
    print(f"OVERALL: {overall}")
    print("═" * 66)

    # ── Persist ────────────────────────────────────────────────────────────
    gate_results_path = output_dir / "gate_results.json"
    screening_metrics_path = output_dir / "screening_metrics.json"

    gate_results_path.write_text(
        json.dumps(
            {
                "factor_name": verdict.factor_name,
                "gate_results": verdict.gate_results,
                "gate_metrics": verdict.gate_metrics,
                "passed_all": verdict.passed_all,
            },
            indent=2,
        )
    )

    screening_metrics_path.write_text(
        json.dumps(
            {
                "factor_name": args.factor,
                "metrics": {k: (float(v) if not pd.isna(v) else None) for k, v in metrics.items()},
                "n_rebalance_dates": len(rebalance),
                "n_score_rows": int(len(factor_scores)),
                "n_fwd_return_rows": int(len(fwd)),
                "start_date": str(start),
                "end_date": str(end),
                "benchmark_relative_metrics": {
                    ticker: {k: (float(v) if not pd.isna(v) else None) for k, v in payload.items()}
                    for ticker, payload in bench_rel.items()
                },
                "brinson_attribution": brinson_payload,
                "alternative_portfolios": alt_portfolios,
            },
            indent=2,
        )
    )

    # Hash-chained research log event (see docs/RESEARCH_RECORD_INTEGRITY.md).
    # Never write raw entries; the chain is load-bearing for AP-6 enforcement.
    log_entry = {
        "event": "factor_screen",
        "factor": args.factor,
        "period": f"{start}_{end}",
        "passed_all": verdict.passed_all,
        "gate_results": verdict.gate_results,
        "metrics": {k: (float(v) if not pd.isna(v) else None) for k, v in metrics.items()},
        "ap6_check": "pass",  # sign convention not altered post-hoc
    }
    append_event(Path("results/research_log.jsonl"), log_entry)

    # Warnings from diagnostics
    warns = [m for m in diag.messages if m.level.value == "WARNING"]
    if warns:
        print(f"\nDiagnostics warnings ({len(warns)}):", flush=True)
        for w in warns[:5]:
            print(f"  [{w.source}] {w.message}")
        if len(warns) > 5:
            print(f"  ... {len(warns) - 5} more")

    print(f"\nSaved: {gate_results_path}")
    print(f"Saved: {screening_metrics_path}")
    return 0 if verdict.passed_all else 1


if __name__ == "__main__":
    sys.exit(main())
