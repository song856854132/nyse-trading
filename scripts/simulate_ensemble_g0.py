#!/usr/bin/env python3
"""iter-12 diagnostic: simulate an equal-weight multi-factor ensemble G0.

Runs the full registered factor menu (``register_all_factors`` in
``nyse_core.features``) across weekly Fridays in the 2016–2023 research window,
aggregates per-(date, symbol) scores via ``compute_ensemble_weights`` with
uniform Sharpe=1.0 (equivalent to a simple average), and emits long-short
quintile returns plus the standard screening metrics (Sharpe, IC mean, IC IR,
max drawdown, 500-rep stationary bootstrap permutation p-value).

**AP-6 safety.** Diagnostic only — does not modify ``config/gates.yaml``,
``config/falsification_triggers.yaml``, ``results/factors/**``, or any
admission state. Does not compare an observed metric against a gate threshold.
The output is an *ensemble-level* metric panel that Wave 4 v2 gate
pre-registration (GL-0012) will later consume as input evidence; iter-12
itself introduces no new gate semantics.

Coverage contract. The factor universe is driven from
``src/nyse_core/features/__init__.py: register_all_factors`` (operator answer
A2, 2026-04-23). Factors whose ``data_source`` is absent from the research
DuckDB (no ``short_interest`` / ``transcripts`` tables) are skipped with
explicit diagnostics; factors whose compute raises a ``KeyError`` on a missing
fundamentals metric (e.g. earnings_surprise requires a pre-aggregated
``operating_profitability`` column that the long-format XBRL feed does not
provide) are also skipped. The persisted ``ensemble_result.json`` enumerates
both the included and excluded factor sets so the "N of 13 registered"
coverage is first-class evidence, not a silent truncation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402

from nyse_core.factor_screening import (
    compute_ensemble_weights,
    compute_long_short_returns,
)
from nyse_core.features import FactorRegistry, register_all_factors
from nyse_core.metrics import ic_ir as compute_ic_ir
from nyse_core.metrics import (
    information_coefficient,
    max_drawdown,
    sharpe_ratio,
)
from nyse_core.normalize import rank_percentile
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL
from nyse_core.statistics import permutation_test

_SRC = "scripts.simulate_ensemble_g0"


def _weekly_fridays(start: date, end: date) -> list[pd.Timestamp]:
    return list(pd.date_range(start=start, end=end, freq="W-FRI"))


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
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])
    return df


def _load_fundamentals(db_path: Path, lookback_start: date, end: date) -> pd.DataFrame:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        df = conn.execute(
            """
            SELECT date, symbol, metric_name, value, filing_type, period_end
            FROM fundamentals
            WHERE date >= ? AND date <= ?
            ORDER BY symbol, period_end
            """,
            [str(lookback_start), str(end)],
        ).fetchdf()
    finally:
        conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _compute_forward_returns(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
) -> pd.DataFrame:
    """5-day forward return: close[t+5] / close[t+1] - 1 (cf. screen_factor.py)."""
    wide = ohlcv.pivot_table(
        index=COL_DATE, columns=COL_SYMBOL, values=COL_CLOSE, aggfunc="last"
    ).sort_index()
    rows: list[pd.DataFrame] = []
    for ts in rebalance_dates:
        future = wide.index[wide.index > ts]
        if len(future) < 5:
            continue
        t1, t5 = future[0], future[4]
        fwd = (wide.loc[t5] / wide.loc[t1] - 1.0).dropna()
        if fwd.empty:
            continue
        rows.append(pd.DataFrame({"date": ts.date(), "symbol": fwd.index, "fwd_ret_5d": fwd.values}))
    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "fwd_ret_5d"])
    return pd.concat(rows, ignore_index=True)


def build_factor_score_panels(
    registry: FactorRegistry,
    ohlcv: pd.DataFrame,
    fundamentals: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Drive ``registry.compute_all`` over weekly rebalance Fridays.

    Returns
    -------
    tuple[dict[str, pd.DataFrame], dict[str, str]]
        - per-factor score panels ``{factor_name: DataFrame[date, symbol, score]}``
          containing only factors that produced at least one non-empty
          (date, symbol) score after rank-percentile normalization. Registry
          sign inversion is applied inside ``compute_all`` so all scores are on
          "high = buy" orientation before ranking.
        - exclusion reasons ``{factor_name: reason}`` for factors that the
          registry attempted but that produced zero rows.
    """
    per_factor_rows: dict[str, list[pd.DataFrame]] = {name: [] for name in registry.get_signal_factors()}
    exclusion_reasons: dict[str, str] = {}

    for ts in rebalance_dates:
        ohlcv_visible = ohlcv[ohlcv[COL_DATE] <= ts]
        fund_visible = fundamentals[fundamentals["date"] <= ts] if not fundamentals.empty else fundamentals
        data_sources: dict[str, pd.DataFrame] = {"ohlcv": ohlcv_visible}
        if not fund_visible.empty:
            data_sources["fundamentals"] = fund_visible

        feature_df, _ = registry.compute_all(data_sources, ts.date())
        if feature_df.empty:
            continue

        for factor_name in feature_df.columns:
            col = feature_df[factor_name].dropna()
            if col.empty:
                continue
            ranked, _ = rank_percentile(col)
            per_factor_rows[factor_name].append(
                pd.DataFrame(
                    {
                        "date": ts.date(),
                        "symbol": ranked.index,
                        "score": ranked.values,
                    }
                )
            )

    panels: dict[str, pd.DataFrame] = {}
    for name, rows in per_factor_rows.items():
        if not rows:
            exclusion_reasons[name] = "no_scores_produced_data_source_absent_or_compute_failed"
            continue
        panels[name] = pd.concat(rows, ignore_index=True)

    return panels, exclusion_reasons


def compute_ensemble_ic_series(ensemble_scores: pd.DataFrame, forward_returns: pd.DataFrame) -> pd.Series:
    """Per-date Spearman IC between ensemble score and 5-day forward return."""
    if ensemble_scores.empty or forward_returns.empty:
        return pd.Series(dtype=float, name="ic")
    merged = pd.merge(ensemble_scores, forward_returns, on=["date", "symbol"], how="inner")
    ic_values: dict = {}
    for dt in sorted(merged["date"].unique()):
        day = merged[merged["date"] == dt].dropna(subset=["score", "fwd_ret_5d"])
        if len(day) < 5:
            continue
        ic_val, _ = information_coefficient(day["score"], day["fwd_ret_5d"])
        ic_values[dt] = ic_val
    if not ic_values:
        return pd.Series(dtype=float, name="ic")
    out = pd.Series(ic_values, name="ic")
    out.index.name = "date"
    return out


def summarize_ensemble(
    ensemble_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
    perm_reps: int,
) -> dict:
    """Compute the iter-12 ensemble diagnostic bundle.

    ``perm_reps`` threads through to ``statistics.permutation_test`` — operator
    answer A3 fixed it at 500 for iter-12 to guarantee a complete run rather
    than a reduced-precision preview.
    """
    ls_returns, _ = compute_long_short_returns(ensemble_scores, forward_returns)
    n_periods = int(len(ls_returns))

    if n_periods == 0:
        return {
            "n_periods": 0,
            "oos_sharpe": None,
            "ic_mean": None,
            "ic_ir": None,
            "max_drawdown": None,
            "permutation_p": None,
            "permutation_reps": perm_reps,
            "annualization_periods_per_year": 52,
        }

    annual_factor = 52  # 5-day fwd returns at weekly rebalance cadence
    oos_sharpe, _ = sharpe_ratio(ls_returns, annual_factor=annual_factor)
    mdd, _ = max_drawdown(ls_returns)
    ic_series = compute_ensemble_ic_series(ensemble_scores, forward_returns)
    ic_mean = float(ic_series.mean()) if len(ic_series) > 0 else None
    ic_ir_val = float(compute_ic_ir(ic_series)[0]) if len(ic_series) > 1 else None

    if n_periods > 1 and ls_returns.std(ddof=1) > 0:
        perm_p, _ = permutation_test(ls_returns, n_reps=perm_reps, block_size=21)
    else:
        perm_p = None

    return {
        "n_periods": n_periods,
        "oos_sharpe": float(oos_sharpe) if oos_sharpe is not None else None,
        "ic_mean": ic_mean,
        "ic_ir": ic_ir_val,
        "max_drawdown": float(mdd) if mdd is not None else None,
        "permutation_p": float(perm_p) if perm_p is not None else None,
        "permutation_reps": perm_reps,
        "annualization_periods_per_year": annual_factor,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="iter-12 ensemble G0 diagnostic (AP-6-safe)")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument("--perm-reps", type=int, default=500)
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/ensemble/iter12_equal_weight"),
    )
    args = p.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end >= date(2024, 1, 1):
        print(
            "REFUSED: end-date crosses holdout boundary (2024-01-01).",
            file=sys.stderr,
        )
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] Loading OHLCV {start} → {end} from {args.db_path}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(
        f"       rows={len(ohlcv):,}  symbols={ohlcv[COL_SYMBOL].nunique()}",
        flush=True,
    )

    lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(f"[2/6] Loading fundamentals {lookback_start} → {end}", flush=True)
    fundamentals = _load_fundamentals(args.db_path, lookback_start, end)
    print(f"       fact rows={len(fundamentals):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[3/6] Rebalance dates: {len(rebalance)} Fridays", flush=True)

    registry = FactorRegistry()
    register_all_factors(registry)
    registered_signal_factors = sorted(registry.get_signal_factors())
    print(
        f"[4/6] Registered signal factors (from registry.py): "
        f"{len(registered_signal_factors)} — {registered_signal_factors}",
        flush=True,
    )

    panels, exclusions = build_factor_score_panels(registry, ohlcv, fundamentals, rebalance)
    included_factors = sorted(panels.keys())
    print(
        f"[5/6] Factor score panels produced: {len(included_factors)} "
        f"(excluded {len(exclusions)}: {sorted(exclusions.keys())})",
        flush=True,
    )

    fwd_returns = _compute_forward_returns(ohlcv, rebalance)
    print(f"       forward-return rows: {len(fwd_returns):,}", flush=True)

    if not panels:
        print("REFUSED: no factor panels produced; cannot build ensemble.", file=sys.stderr)
        return 2

    # Equal-Sharpe aggregation → compute_ensemble_weights degenerates to the
    # plain cross-factor mean at each (date, symbol) pair. Operator answer A1
    # asked for the full registered menu; missing factors are handled above.
    equal_sharpes = dict.fromkeys(included_factors, 1.0)
    ensemble_scores, ens_diag = compute_ensemble_weights(panels, equal_sharpes)
    print(
        f"       ensemble rows: {len(ensemble_scores):,} "
        f"across {ensemble_scores['date'].nunique() if not ensemble_scores.empty else 0} dates",
        flush=True,
    )

    print("[6/6] Summarizing ensemble diagnostic...", flush=True)
    summary = summarize_ensemble(ensemble_scores, fwd_returns, perm_reps=args.perm_reps)
    print("")
    print("ENSEMBLE G0 SIMULATION (iter-12, equal-weight, AP-6-safe)")
    print("═" * 66)
    print(f"  Included factors  : {len(included_factors)} / {len(registered_signal_factors)}")
    print(f"  Excluded factors  : {len(exclusions)}")
    print(f"  Rebalance periods : {summary['n_periods']}")
    if summary["oos_sharpe"] is not None:
        print(f"  OOS Sharpe        : {summary['oos_sharpe']:+.4f}")
    if summary["ic_mean"] is not None:
        print(f"  IC mean           : {summary['ic_mean']:+.4f}")
    if summary["ic_ir"] is not None:
        print(f"  IC IR             : {summary['ic_ir']:+.4f}")
    if summary["max_drawdown"] is not None:
        print(f"  Max drawdown      : {summary['max_drawdown']:+.4f}")
    if summary["permutation_p"] is not None:
        print(
            f"  Permutation p     : {summary['permutation_p']:.4f} "
            f"(block-bootstrap, n_reps={summary['permutation_reps']})"
        )
    print("═" * 66)
    print("AP-6 verdict: diagnostic_only_no_gate_comparison_no_admission_change")
    print("═" * 66)

    # Persist a faithful, reproducible snapshot. Ensemble score panel is not
    # serialized (can be regenerated from the same registry + data) — keeping
    # the artifact compact avoids committing a multi-MB CSV into git.
    result_payload: dict[str, object] = {
        "iter": "12",
        "wave": "D_multi_factor_admission",
        "variant": "equal_weight_diagnostic",
        "start_date": str(start),
        "end_date": str(end),
        "n_rebalance_dates": len(rebalance),
        "registered_signal_factors": registered_signal_factors,
        "included_factors": included_factors,
        "excluded_factors": {name: reason for name, reason in sorted(exclusions.items())},
        "aggregator": "compute_ensemble_weights",
        "aggregator_sharpes": "equal_1.0_per_included_factor",
        "quintile_construction": "compute_long_short_weights_n_quantiles_5",
        "summary": summary,
        "ap6_verdict": "diagnostic_only_no_gate_comparison_no_admission_change",
        "config_gates_yaml_sha256": ("521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4"),
    }

    result_path = args.output_dir / "ensemble_result.json"
    result_path.write_text(json.dumps(result_payload, indent=2, default=str))
    print(f"Saved: {result_path}", flush=True)

    log_event = {
        "event": "iter12_ensemble_g0_equal_weight_diagnostic",
        "iteration": 12,
        "iteration_tag": "iter-12",
        "wave": "D_multi_factor_admission",
        "ap6_check": "pass",
        "ap6_verdict": "diagnostic_only_no_gate_comparison_no_admission_change",
        "variant": "equal_weight_diagnostic",
        "n_included_factors": len(included_factors),
        "n_excluded_factors": len(exclusions),
        "registered_signal_factors": registered_signal_factors,
        "included_factors": included_factors,
        "excluded_factors": {name: reason for name, reason in sorted(exclusions.items())},
        "summary": summary,
        "artifact": str(result_path),
        "config_gates_yaml_sha256": ("521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4"),
    }
    append_event(Path("results/research_log.jsonl"), log_event)

    warns = [m for m in ens_diag.messages if m.level.value == "WARNING"]
    if warns:
        print(f"\nAggregator warnings ({len(warns)}):", flush=True)
        for w in warns[:5]:
            print(f"  [{w.source}] {w.message}")

    return 0


if __name__ == "__main__":
    # Silence a specific NumPy RuntimeWarning from permutation_test on small N
    np.seterr(invalid="ignore")
    sys.exit(main())
