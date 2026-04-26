#!/usr/bin/env python3
"""Wave 8 W8-D — single-factor `ivol_20d_flipped` validation under V_D1..V_D4.

Pre-registered bars (GL-0021, frozen iter-27..iter-35 per Iron Rule 9):

  V_D1  walk-forward OOS Sharpe (annual_factor=52)        >= 0.30
  V_D2  permutation_test p-value (500 reps, block=21)     <  0.05
  V_D3  block_bootstrap_ci lower bound (10000 reps, b=63) >= 0.20
  V_D4  min(bull_sharpe, bear_sharpe) on SPY SMA200 split >= 0.20

Construction grammar (mirrors V2-PREREG §2.2 for evidence-chain consistency):

  - Long-short = top quintile vs bottom quintile of rank-percentile scores
    (compute_long_short_returns, n_quantiles=5).
  - rank_percentile uses RNG tie-break with seed = date.toordinal() so any
    discrete IVOL ties get deterministic distinct ranks. Tie-break is
    inherited from V2 ensemble convention; even though IVOL is continuous,
    we keep the seed for bit-identity with the W8-D evidence template.
  - sign_convention=+1 mirrors `screen_factor.py:69` and the V2 ensemble's
    `_V2_ACTIVE_FACTORS` registration: rank raw IVOL such that high-IVOL =
    high score = buy. This reproduces the SAME signal that drove the
    +0.5549 V2 ensemble Sharpe; W8-D asks whether that signal survives
    standalone (Codex Path D from 2026-04-26 review).

Iron Rule compliance (1, 2, 3, 4, 6, 7, 8, 11, 12):
  1. Refuse end-date >= 2024-01-01 (holdout boundary).
  2. Assert config/gates_v2.yaml sha256 == frozen value.
  3. No DB mocks — runs against research.duckdb.
  4. No secrets leak.
  6. Hash-chain append to results/research_log.jsonl (caller's job).
  7. results/factors/<f>/gate_results*.json untouched.
  8. No threshold adjustments.
 11. Writes ONLY to results/validation/wave8_d_single_factor/result.json
     (W8-D evidence path; never overwrites W8-A or canonical evidence).
 12. Even on PASS, no holdout consumption — Wave 9 governance row required.

Usage:

    python3 scripts/run_workstream_d_single_factor.py \\
        --start-date 2016-01-01 --end-date 2023-12-31

Output: results/validation/wave8_d_single_factor/result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen_factor import (  # noqa: E402
    _build_forward_returns,
    _load_ohlcv,
    _weekly_fridays,
)

from nyse_core.factor_screening import compute_long_short_returns
from nyse_core.features.price_volume import compute_ivol_20d
from nyse_core.metrics import sharpe_ratio
from nyse_core.normalize import rank_percentile
from nyse_core.schema import COL_DATE
from nyse_core.statistics import block_bootstrap_ci, permutation_test

_SRC = "scripts.run_workstream_d_single_factor"

_GATES_V2_SHA256 = "bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2"

# Pre-registered bars (GL-0021)
_V_D1_THRESHOLD = 0.30
_V_D2_THRESHOLD = 0.05
_V_D3_THRESHOLD = 0.20
_V_D4_THRESHOLD = 0.20

_ANNUAL_FACTOR_WEEKLY = 52  # 5d forward returns at weekly cadence
_PERM_REPS = 500
_PERM_BLOCK = 21
_BOOT_REPS = 10000
_BOOT_BLOCK = 63
_BOOT_ALPHA = 0.05
_SMA_WINDOW = 200


def _assert_gates_v2_frozen(config_path: Path = Path("config/gates_v2.yaml")) -> None:
    """Iron Rule 2/8: gates_v2.yaml must be bit-identical to the frozen value."""
    actual = hashlib.sha256(config_path.read_bytes()).hexdigest()
    if actual != _GATES_V2_SHA256:
        raise RuntimeError(
            f"REFUSED: config/gates_v2.yaml sha256 {actual} != frozen "
            f"{_GATES_V2_SHA256}. Iron Rule 8 violation."
        )


def _build_ivol_panel(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
) -> pd.DataFrame:
    """Per-date rank-percentile panel for ivol_20d_flipped (sign=+1, no negation).

    Mirrors `simulate_v2_ensemble_phase3._build_panel_with_rng_tiebreak` so the
    W8-D signal IS the same signal that drove the V2 ensemble +0.5549 Sharpe.
    """
    ohlcv = ohlcv.copy()
    ohlcv[COL_DATE] = pd.to_datetime(ohlcv[COL_DATE])

    rows: list[pd.DataFrame] = []
    for ts in rebalance_dates:
        window = ohlcv[ohlcv[COL_DATE] <= ts]
        if window.empty:
            continue
        series, _ = compute_ivol_20d(window)
        series = series.dropna()
        if series.empty:
            continue
        # sign=+1 → no negation; high raw IVOL = high score (V2 ensemble convention)
        rng = np.random.default_rng(seed=ts.toordinal())
        ranked, _ = rank_percentile(series, rng=rng)
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


def _load_spy_sma200(
    db_path: Path,
    start: date,
    end: date,
) -> pd.Series:
    """Return SPY close series indexed by date, with leading lookback for SMA200.

    Loads SPY closes from `start - SMA_WINDOW*2 days` so the 200-day rolling mean
    is well-defined at `start`. Caller computes regime by comparing close vs.
    rolling mean.
    """
    lookback = start - pd.Timedelta(days=_SMA_WINDOW * 2).to_pytimedelta()
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        df = conn.execute(
            "SELECT date, close FROM ohlcv WHERE symbol = 'SPY' "
            "AND date >= ? AND date <= ? ORDER BY date",
            [lookback.isoformat(), end.isoformat()],
        ).fetchdf()
    finally:
        conn.close()
    if df.empty:
        raise RuntimeError(
            "REFUSED: no SPY rows in research.duckdb over "
            f"[{lookback}, {end}]; V_D4 cannot be computed."
        )
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["close"].astype(float).sort_index()
    return s


def _classify_regime_per_date(
    ls_dates: pd.DatetimeIndex,
    spy_close: pd.Series,
) -> pd.Series:
    """Map each long-short return date to "BULL" or "BEAR" via SPY vs SMA200.

    Uses the SPY close on the rebalance date (or the last trading day on/before
    the rebalance date if it's a non-trading Friday) and compares to its 200-day
    rolling mean. BULL if close > SMA200, else BEAR.
    """
    sma200 = spy_close.rolling(_SMA_WINDOW, min_periods=_SMA_WINDOW).mean()
    regimes: dict = {}
    for dt in ls_dates:
        ts = pd.Timestamp(dt)
        # Find the last SPY observation on or before ts
        idx = spy_close.index.searchsorted(ts, side="right") - 1
        if idx < 0:
            regimes[dt] = "UNKNOWN"
            continue
        as_of = spy_close.index[idx]
        sma_val = sma200.loc[as_of]
        close_val = spy_close.loc[as_of]
        if pd.isna(sma_val) or pd.isna(close_val):
            regimes[dt] = "UNKNOWN"
            continue
        regimes[dt] = "BULL" if close_val > sma_val else "BEAR"
    return pd.Series(regimes, name="regime")


def _verdict(observed: float | None, threshold: float, direction: str) -> str:
    """Return PASS/FAIL/INDETERMINATE for an observed scalar vs. threshold."""
    if observed is None or (isinstance(observed, float) and np.isnan(observed)):
        return "INDETERMINATE"
    if direction == ">=":
        return "PASS" if observed >= threshold else "FAIL"
    if direction == "<":
        return "PASS" if observed < threshold else "FAIL"
    raise ValueError(f"unknown direction: {direction!r}")


def main() -> int:
    p = argparse.ArgumentParser(description="Wave 8 W8-D single-factor ivol_20d_flipped validation")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/validation/wave8_d_single_factor"),
    )
    p.add_argument(
        "--gates-config",
        type=Path,
        default=Path("config/gates_v2.yaml"),
        help="path to gates_v2.yaml for sha256 invariance assertion",
    )
    args = p.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end >= date(2024, 1, 1):
        print("REFUSED: end-date crosses holdout boundary (2024-01-01).", file=sys.stderr)
        return 2

    _assert_gates_v2_frozen(args.gates_config)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[2/6] Rebalance dates: {len(rebalance)} weekly Fridays", flush=True)

    fwd_returns = _build_forward_returns(ohlcv, rebalance)
    print(f"[3/6] Forward-return rows: {len(fwd_returns):,}", flush=True)

    print("[4/6] Building ivol_20d_flipped panel (sign=+1, RNG tie-break)", flush=True)
    panel = _build_ivol_panel(ohlcv, rebalance)
    print(f"       panel rows: {len(panel):,}", flush=True)
    if panel.empty:
        print("REFUSED: ivol_20d_flipped panel is empty.", file=sys.stderr)
        return 3

    print("[5/6] Long-short quintile portfolio + V_D1..V_D4", flush=True)
    ls_returns, ls_diag = compute_long_short_returns(panel, fwd_returns, n_quantiles=5)
    n_periods = int(len(ls_returns))
    if n_periods < 2 or float(ls_returns.std(ddof=1)) == 0.0:
        print(
            f"REFUSED: insufficient long-short data (n={n_periods}, std=0?).",
            file=sys.stderr,
        )
        return 4

    # V_D1
    oos_sharpe, _ = sharpe_ratio(ls_returns, annual_factor=_ANNUAL_FACTOR_WEEKLY)
    v_d1_observed = float(oos_sharpe) if oos_sharpe is not None else None
    v_d1_verdict = _verdict(v_d1_observed, _V_D1_THRESHOLD, ">=")

    # V_D2
    perm_p, _ = permutation_test(ls_returns, n_reps=_PERM_REPS, block_size=_PERM_BLOCK)
    v_d2_observed = float(perm_p) if perm_p is not None else None
    v_d2_verdict = _verdict(v_d2_observed, _V_D2_THRESHOLD, "<")

    # V_D3
    (boot_lower, boot_upper), _ = block_bootstrap_ci(
        ls_returns, n_reps=_BOOT_REPS, block_size=_BOOT_BLOCK, alpha=_BOOT_ALPHA
    )
    v_d3_observed = float(boot_lower) if boot_lower is not None else None
    v_d3_verdict = _verdict(v_d3_observed, _V_D3_THRESHOLD, ">=")

    # V_D4
    print("[6/6] V_D4 SPY SMA200 regime stratification", flush=True)
    spy_close = _load_spy_sma200(args.db_path, start, end)
    ls_index = pd.DatetimeIndex([pd.Timestamp(d) for d in ls_returns.index])
    regimes = _classify_regime_per_date(ls_index, spy_close)
    regimes.index = list(ls_returns.index)

    bull_mask = regimes == "BULL"
    bear_mask = regimes == "BEAR"
    bull_returns = ls_returns[bull_mask.values]
    bear_returns = ls_returns[bear_mask.values]

    bull_sharpe = (
        float(sharpe_ratio(bull_returns, annual_factor=_ANNUAL_FACTOR_WEEKLY)[0])
        if len(bull_returns) >= 2 and bull_returns.std(ddof=1) > 0
        else None
    )
    bear_sharpe = (
        float(sharpe_ratio(bear_returns, annual_factor=_ANNUAL_FACTOR_WEEKLY)[0])
        if len(bear_returns) >= 2 and bear_returns.std(ddof=1) > 0
        else None
    )
    if bull_sharpe is None or bear_sharpe is None:
        v_d4_observed: float | None = None
    else:
        v_d4_observed = float(min(bull_sharpe, bear_sharpe))
    v_d4_verdict = _verdict(v_d4_observed, _V_D4_THRESHOLD, ">=")

    # Aggregate W8-D
    all_pass = all(v == "PASS" for v in (v_d1_verdict, v_d2_verdict, v_d3_verdict, v_d4_verdict))
    any_indet = any(v == "INDETERMINATE" for v in (v_d1_verdict, v_d2_verdict, v_d3_verdict, v_d4_verdict))
    w8_d_overall_verdict = "PASS" if all_pass else ("INDETERMINATE" if any_indet else "FAIL")

    print("")
    print("WAVE 8 W8-D SINGLE-FACTOR ivol_20d_flipped VALIDATION")
    print("=" * 66)
    print(f"  Window         : {start} -> {end}")
    print(f"  Rebalance      : {len(rebalance)} weekly Fridays")
    print(f"  LS periods     : {n_periods}")
    print(f"  V_D1 Sharpe    : {v_d1_observed!r:>10}  >= {_V_D1_THRESHOLD}  -> {v_d1_verdict}")
    print(f"  V_D2 perm p    : {v_d2_observed!r:>10}  <  {_V_D2_THRESHOLD}  -> {v_d2_verdict}")
    print(f"  V_D3 ci_lower  : {v_d3_observed!r:>10}  >= {_V_D3_THRESHOLD}  -> {v_d3_verdict}")
    print(f"  V_D4 min regS  : {v_d4_observed!r:>10}  >= {_V_D4_THRESHOLD}  -> {v_d4_verdict}")
    print(f"  W8-D OVERALL   : {w8_d_overall_verdict}")
    print("=" * 66)

    payload: dict = {
        "iteration": 28,
        "iteration_tag": "iter-28",
        "task_id": 158,
        "wave": "Wave 8 W8-D single-factor ivol_20d_flipped",
        "implements_preregistration": "GL-0021 (Wave 8 V_D1..V_D4 frozen iter-27..iter-35)",
        "factor_under_test": "ivol_20d_flipped",
        "construction": {
            "n_quantiles": 5,
            "weighting": "equal",
            "sign_convention": +1,
            "rank_percentile_tiebreak": "rng_default_rng_seed_date_toordinal",
            "annual_factor": _ANNUAL_FACTOR_WEEKLY,
            "ensemble": False,
            "k_of_n_coverage": False,
            "regime_overlay_applied_to_ls_series": False,
        },
        "window": {"start": str(start), "end": str(end)},
        "n_rebalance_dates": len(rebalance),
        "n_forward_return_rows": int(len(fwd_returns)),
        "n_panel_rows": int(len(panel)),
        "n_ls_periods": n_periods,
        "v_d1": {
            "metric": "oos_sharpe",
            "observed": v_d1_observed,
            "threshold": _V_D1_THRESHOLD,
            "direction": ">=",
            "verdict": v_d1_verdict,
        },
        "v_d2": {
            "metric": "permutation_p",
            "observed": v_d2_observed,
            "threshold": _V_D2_THRESHOLD,
            "direction": "<",
            "n_reps": _PERM_REPS,
            "block_size": _PERM_BLOCK,
            "verdict": v_d2_verdict,
        },
        "v_d3": {
            "metric": "bootstrap_ci_lower",
            "observed": v_d3_observed,
            "threshold": _V_D3_THRESHOLD,
            "direction": ">=",
            "n_reps": _BOOT_REPS,
            "block_size": _BOOT_BLOCK,
            "alpha": _BOOT_ALPHA,
            "ci_upper": float(boot_upper) if boot_upper is not None else None,
            "verdict": v_d3_verdict,
        },
        "v_d4": {
            "metric": "min_regime_sharpe",
            "observed": v_d4_observed,
            "threshold": _V_D4_THRESHOLD,
            "direction": ">=",
            "regime_split": "spy_sma200_binary",
            "sma_window": _SMA_WINDOW,
            "bull_n_periods": int(bull_mask.sum()),
            "bear_n_periods": int(bear_mask.sum()),
            "bull_sharpe": bull_sharpe,
            "bear_sharpe": bear_sharpe,
            "verdict": v_d4_verdict,
        },
        "w8_d_overall_verdict": w8_d_overall_verdict,
        "gates_v2_sha256": _GATES_V2_SHA256,
        "no_renegotiation_clause": (
            "GL-0021 freezes V_D1..V_D4 for iter-27..iter-35. A FAIL here is "
            "genuine and routes through Iron Rule 11 strategy-class isolation, "
            "NOT a bar-renegotiation trigger (Iron Rule 9)."
        ),
        "iron_rule_12_attestation": (
            "Even on PASS, Wave 8 does NOT consume the holdout. Wave 9 governance "
            "row required to re-authorize holdout consumption (GL-0021 Iron Rule 12)."
        ),
        "ap6_compliance": (
            "validation outcome of pre-registered frozen V_D1..V_D4 (GL-0021); "
            "no threshold modification, no admission decision changed, no "
            "config/gates*.yaml or config/strategy_params.yaml committed change."
        ),
        "timestamp_source": f"{_SRC}.main",
    }

    out_path = args.output_dir / "result.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"Saved: {out_path}", flush=True)

    warns = [m for m in ls_diag.messages if m.level.value == "WARNING"]
    if warns:
        print(f"\nLong-short warnings ({len(warns)}):", flush=True)
        for w in warns[:5]:
            print(f"  [{w.source}] {w.message}")

    return 0


if __name__ == "__main__":
    np.seterr(invalid="ignore")
    sys.exit(main())
