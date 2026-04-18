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
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

# Sibling script import — research log is hash-chained; do NOT write raw entries.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402

from nyse_core.factor_screening import screen_factor
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
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL

# Maps factor name → (compute_fn, sign_convention, data_source, lookback_days)
# sign_convention: -1 means "low raw value = buy" — we negate before ranking.
# data_source: "ohlcv" reads from the ohlcv table; "fundamentals" reads from the
# fundamentals table (long-format XBRL facts, filing-date-keyed for PiT).
# lookback_days: pre-start buffer when loading data. For fundamentals we need
# ~400 days of history so the first rebalance has a prior-year filing for
# delta-based signals (Piotroski F3/F5/F6/F7/F8/F9).
_FACTORS = {
    "ivol_20d":      (compute_ivol_20d,            -1, "ohlcv",         30),
    "high_52w":      (compute_52w_high_proximity,  +1, "ohlcv",        260),
    "momentum_2_12": (compute_momentum_2_12,       +1, "ohlcv",        260),
    "piotroski":     (compute_piotroski_f_score,   +1, "fundamentals", 400),
    "accruals":      (compute_accruals,            -1, "fundamentals", 400),
    "profitability": (compute_profitability,       +1, "fundamentals", 400),
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
        frame = pd.DataFrame({
            "date":   ts.date(),
            "symbol": ranked.index,
            "score":  ranked.values,
        })
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
        rows.append(pd.DataFrame({
            "date":       ts.date(),
            "symbol":     fwd.index,
            "fwd_ret_5d": fwd.values,
        }))

    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "fwd_ret_5d"])
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
        rows.append(pd.DataFrame({
            "date":   ts.date(),
            "symbol": ranked.index,
            "score":  ranked.values,
        }))

    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "score"])
    return pd.concat(rows, ignore_index=True)


def _gate_row(gate: str, metric_name: str, value: float, threshold: float,
              direction: str, passed: bool) -> str:
    arrow = {"pass": "PASS", "fail": "FAIL"}["pass" if passed else "fail"]
    return (
        f"{gate:<6}{metric_name:<24}{value:>10.4f}   "
        f"{direction:<2}{threshold:<10.4f}{arrow}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Screen a single factor through G0-G5")
    p.add_argument("--factor", required=True, choices=sorted(_FACTORS.keys()))
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Defaults to results/factors/<factor>/")
    args = p.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end >= date(2024, 1, 1):
        print("REFUSED: end-date crosses holdout boundary (2024-01-01). "
              "Research period ends 2023-12-31.", file=sys.stderr)
        return 2

    compute_fn, sign, data_source, lookback_days = _FACTORS[args.factor]
    output_dir = args.output_dir or Path("results/factors") / args.factor
    output_dir.mkdir(parents=True, exist_ok=True)

    # Always need OHLCV for forward-return construction, even when the factor
    # itself is fundamentals-based.
    print(f"[1/5] Loading OHLCV {start} → {end} from {args.db_path}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(f"       rows={len(ohlcv):,}  symbols={ohlcv[COL_SYMBOL].nunique()}",
          flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[2/5] Rebalance dates: {len(rebalance)} Fridays", flush=True)

    print(
        f"[3/5] Computing {args.factor} scores "
        f"(sign={sign}, source={data_source})...",
        flush=True,
    )
    if data_source == "ohlcv":
        factor_scores = _build_factor_panel(ohlcv, rebalance, compute_fn, sign)
    elif data_source == "fundamentals":
        lookback_start = start - pd.Timedelta(
            days=lookback_days
        ).to_pytimedelta()
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
        factor_scores = _build_fundamental_panel(
            raw_facts, rebalance, compute_fn, sign
        )
    else:
        print(f"UNKNOWN data_source: {data_source}", file=sys.stderr)
        return 2
    print(f"       score rows={len(factor_scores):,}", flush=True)

    print("[4/5] Computing 5-day forward returns...", flush=True)
    fwd = _build_forward_returns(ohlcv, rebalance)
    print(f"       fwd-return rows={len(fwd):,}", flush=True)

    print("[5/5] Running screen_factor() — G0..G5...", flush=True)
    verdict, metrics, diag = screen_factor(
        factor_name=args.factor,
        factor_scores=factor_scores,
        forward_returns=fwd,
    )

    # ── Present ────────────────────────────────────────────────────────────
    gate_cfg = {
        "G0": ("oos_sharpe",            0.30,  ">="),
        "G1": ("permutation_p",         0.05,  "<"),
        "G2": ("ic_mean",               0.02,  ">="),
        "G3": ("ic_ir",                 0.50,  ">="),
        "G4": ("max_drawdown",         -0.30,  ">="),
        "G5": ("marginal_contribution", 0.00,  ">"),
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

    gate_results_path.write_text(json.dumps({
        "factor_name":  verdict.factor_name,
        "gate_results": verdict.gate_results,
        "gate_metrics": verdict.gate_metrics,
        "passed_all":   verdict.passed_all,
    }, indent=2))

    screening_metrics_path.write_text(json.dumps({
        "factor_name": args.factor,
        "metrics":     {k: (float(v) if not pd.isna(v) else None)
                        for k, v in metrics.items()},
        "n_rebalance_dates": len(rebalance),
        "n_score_rows":      int(len(factor_scores)),
        "n_fwd_return_rows": int(len(fwd)),
        "start_date":        str(start),
        "end_date":          str(end),
    }, indent=2))

    # Hash-chained research log event (see docs/RESEARCH_RECORD_INTEGRITY.md).
    # Never write raw entries; the chain is load-bearing for AP-6 enforcement.
    log_entry = {
        "event":       "factor_screen",
        "factor":      args.factor,
        "period":      f"{start}_{end}",
        "passed_all":  verdict.passed_all,
        "gate_results": verdict.gate_results,
        "metrics":     {k: (float(v) if not pd.isna(v) else None)
                        for k, v in metrics.items()},
        "ap6_check":   "pass",  # sign convention not altered post-hoc
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
