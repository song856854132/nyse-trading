#!/usr/bin/env python3
"""Wave 8 W8-A — orthogonal-discovery candidate screen under v2 G0-G5 + V_A7.

Pre-registered bars (GL-0021 + GL-0023, frozen iter-27..iter-32):

  G0  oos_sharpe                            >= 0.30   (gates_v2.yaml)
  G1  permutation_p                         <  0.05   (gates_v2.yaml)
  G2  ic_mean                               >= 0.005  (gates_v2.yaml)
  G3  ic_ir                                 >= 0.05   (gates_v2.yaml)
  G4  max_drawdown                          >= -0.30  (gates_v2.yaml)
  G5  max_return_decile_corr_with_admitted  <= 0.90   (gates_v2.yaml)
  V_A7 max(|corr(candidate_LS, v2_active_LS_i)|) for i in v2 active universe
                                            <  0.50   (GL-0021)

Restricted slate (GL-0023):

  iter-30: 52w_high_proximity (T1, OHLCV, sign=+1, friction: disposition effect /
           reference-point anchoring -> 52w-high continuation)
  iter-31: ewmac              (T3, OHLCV, sign=+1, friction: Carver
           cross-sectional EWMAC trend orthogonal to 12-month momentum)

V2 active universe (5 incumbents, used for V_A7 max-corr ceiling):
  ivol_20d_flipped, piotroski_f_score, momentum_2_12, accruals, profitability

Iron Rule compliance (1, 2, 3, 4, 6, 7, 8, 11, 12):
  1. Refuse end-date >= 2024-01-01 (holdout boundary).
  2. Assert config/gates_v2.yaml sha256 == frozen value.
  3. No DB mocks - runs against research.duckdb.
  4. No secrets leak.
  6. Hash-chain append to results/research_log.jsonl (caller's job).
  7. Writes ONLY to results/factors/<candidate>/gate_results_v2_wave8.json
     (parallel path; canonical results/factors/<f>/gate_results.json untouched).
  8. No threshold adjustments.
 11. Strategy-class isolation - W8-D evidence path
     (results/validation/wave8_d_single_factor/result.json) untouched.
 12. Even on PASS, no holdout consumption - Wave 9 governance row required.

Usage:

    python3 scripts/run_workstream_a_orthogonal_screen.py \\
        --candidate 52w_high_proximity \\
        --start-date 2016-01-01 --end-date 2023-12-31

Output: results/factors/<candidate>/gate_results_v2_wave8.json
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
    _build_factor_panel,
    _build_forward_returns,
    _build_fundamental_panel,
    _load_fundamentals,
    _load_ohlcv,
    _weekly_fridays,
)

from nyse_core.factor_screening import compute_long_short_returns, screen_factor
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
from nyse_core.features.sentiment import compute_ewmac

_SRC = "scripts.run_workstream_a_orthogonal_screen"

_GATES_V2_SHA256 = "bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2"

# V_A7 (GL-0021): max |Pearson corr| of candidate's L-S returns against any of
# the 5 v2 active universe factors' L-S returns. Threshold strict less-than.
_V_A7_THRESHOLD = 0.50

# v2 G0..G5 thresholds mirror config/gates_v2.yaml (sha256 verified).
_V2_GATE_CONFIG: dict[str, dict] = {
    "G0": {"metric": "oos_sharpe", "threshold": 0.30, "direction": ">="},
    "G1": {"metric": "permutation_p", "threshold": 0.05, "direction": "<"},
    "G2": {"metric": "ic_mean", "threshold": 0.005, "direction": ">="},
    "G3": {"metric": "ic_ir", "threshold": 0.05, "direction": ">="},
    "G4": {"metric": "max_drawdown", "threshold": -0.30, "direction": ">="},
    "G5": {
        "metric": "max_return_decile_corr_with_admitted",
        "threshold": 0.90,
        "direction": "<=",
    },
}

# V2 active universe (incumbents at iter-29). Used by V_A7 max-corr computation
# AND by G5 (max_return_decile_corr_with_admitted) via existing_factor_scores.
# Mirrors scripts/simulate_v2_ensemble_phase3.py:_V2_ACTIVE_FACTORS.
_V2_ACTIVE_FACTORS: dict[str, tuple] = {
    "ivol_20d_flipped": (compute_ivol_20d, +1, "ohlcv", 30),
    "piotroski_f_score": (compute_piotroski_f_score, +1, "fundamentals", 400),
    "momentum_2_12": (compute_momentum_2_12, +1, "ohlcv", 260),
    "accruals": (compute_accruals, -1, "fundamentals", 400),
    "profitability": (compute_profitability, +1, "fundamentals", 400),
}

# GL-0023 READY slate (iter-29). Each entry: (compute_fn, sign, data_source, lookback)
_W8A_CANDIDATES: dict[str, tuple] = {
    "52w_high_proximity": (compute_52w_high_proximity, +1, "ohlcv", 260),
    "ewmac": (compute_ewmac, +1, "ohlcv", 90),
}


def _assert_gates_v2_frozen(config_path: Path = Path("config/gates_v2.yaml")) -> None:
    """Iron Rule 2/8: gates_v2.yaml must be bit-identical to the frozen value."""
    actual = hashlib.sha256(config_path.read_bytes()).hexdigest()
    if actual != _GATES_V2_SHA256:
        raise RuntimeError(
            f"REFUSED: config/gates_v2.yaml sha256 {actual} != frozen "
            f"{_GATES_V2_SHA256}. Iron Rule 8 violation."
        )


def _build_panel(
    ohlcv: pd.DataFrame,
    fundamentals: pd.DataFrame,
    rebalance: list[pd.Timestamp],
    compute_fn,
    sign: int,
    data_source: str,
) -> pd.DataFrame:
    """Dispatch to the OHLCV or fundamentals panel builder by data_source."""
    if data_source == "ohlcv":
        return _build_factor_panel(ohlcv, rebalance, compute_fn, sign)
    if data_source == "fundamentals":
        return _build_fundamental_panel(fundamentals, rebalance, compute_fn, sign)
    raise ValueError(f"unknown data_source: {data_source!r}")


def _verdict(observed: float | None, threshold: float, direction: str) -> str:
    """Return PASS/FAIL/INDETERMINATE for an observed scalar vs. threshold."""
    if observed is None or (isinstance(observed, float) and np.isnan(observed)):
        return "INDETERMINATE"
    if direction == ">=":
        return "PASS" if observed >= threshold else "FAIL"
    if direction == "<":
        return "PASS" if observed < threshold else "FAIL"
    if direction == "<=":
        return "PASS" if observed <= threshold else "FAIL"
    if direction == ">":
        return "PASS" if observed > threshold else "FAIL"
    raise ValueError(f"unknown direction: {direction!r}")


def _compute_v_a7(
    candidate_panel: pd.DataFrame,
    active_panels: dict[str, pd.DataFrame],
    fwd_returns: pd.DataFrame,
) -> tuple[float | None, dict[str, float | None]]:
    """V_A7: max |Pearson corr| of candidate L-S against each v2 active L-S series.

    Returns (max_abs_corr, per_factor_corr_dict). max_abs_corr = None when any
    L-S series degenerates (insufficient non-NaN periods or zero std).
    """
    cand_ls, _ = compute_long_short_returns(candidate_panel, fwd_returns)
    if len(cand_ls) < 2 or float(cand_ls.std(ddof=1)) == 0.0:
        return None, dict.fromkeys(active_panels, None)

    corrs: dict[str, float | None] = {}
    abs_corrs: list[float] = []
    for fname, panel in active_panels.items():
        if panel.empty:
            corrs[fname] = None
            continue
        active_ls, _ = compute_long_short_returns(panel, fwd_returns)
        if len(active_ls) < 2 or float(active_ls.std(ddof=1)) == 0.0:
            corrs[fname] = None
            continue
        # Align on shared dates - both series have date-indexed values.
        aligned = pd.concat([cand_ls.rename("c"), active_ls.rename("a")], axis=1).dropna()
        if len(aligned) < 2 or aligned["c"].std(ddof=1) == 0.0 or aligned["a"].std(ddof=1) == 0.0:
            corrs[fname] = None
            continue
        rho = float(aligned["c"].corr(aligned["a"]))
        corrs[fname] = rho
        abs_corrs.append(abs(rho))

    if not abs_corrs:
        return None, corrs
    return float(max(abs_corrs)), corrs


def main() -> int:
    p = argparse.ArgumentParser(
        description="Wave 8 W8-A orthogonal candidate screen (v2 G0-G5 + V_A7)"
    )
    p.add_argument(
        "--candidate",
        required=True,
        choices=sorted(_W8A_CANDIDATES.keys()),
        help="GL-0023 READY candidate name",
    )
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to results/factors/<candidate>/",
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

    candidate = args.candidate
    cand_compute_fn, cand_sign, cand_source, cand_lookback = _W8A_CANDIDATES[candidate]

    output_dir = args.output_dir or Path("results/factors") / candidate
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/7] Loading OHLCV {start} -> {end} from {args.db_path}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[2/7] Rebalance dates: {len(rebalance)} weekly Fridays", flush=True)

    # Load fundamentals once - used by candidate (if fundamentals-based) AND
    # by the v2 active universe panels (piotroski/accruals/profitability).
    # Use 400-day pre-start lookback per simulate_v2_ensemble_phase3 convention.
    fund_lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(
        f"[3/7] Loading fundamentals {fund_lookback_start} -> {end}",
        flush=True,
    )
    fundamentals = _load_fundamentals(args.db_path, fund_lookback_start, end)
    print(
        f"       fact rows={len(fundamentals):,}  "
        f"symbols={fundamentals['symbol'].nunique() if not fundamentals.empty else 0}",
        flush=True,
    )

    print("[4/7] Computing 5-day forward returns", flush=True)
    fwd_returns = _build_forward_returns(ohlcv, rebalance)
    print(f"       fwd-return rows: {len(fwd_returns):,}", flush=True)

    print(
        f"[5/7] Building candidate '{candidate}' panel "
        f"(sign={cand_sign}, source={cand_source})",
        flush=True,
    )
    candidate_panel = _build_panel(
        ohlcv, fundamentals, rebalance, cand_compute_fn, cand_sign, cand_source
    )
    print(f"       candidate panel rows: {len(candidate_panel):,}", flush=True)
    if candidate_panel.empty:
        print(
            f"REFUSED: candidate '{candidate}' panel is empty.",
            file=sys.stderr,
        )
        return 3

    print("[6/7] Building v2 active universe panels (5 factors)", flush=True)
    active_panels: dict[str, pd.DataFrame] = {}
    for fname, (compute_fn, sign, source, _lookback) in _V2_ACTIVE_FACTORS.items():
        panel = _build_panel(ohlcv, fundamentals, rebalance, compute_fn, sign, source)
        active_panels[fname] = panel
        print(f"       {fname}: {len(panel):,} rows", flush=True)

    print("[7/7] Running v2 G0..G5 screen + V_A7 max-corr", flush=True)
    verdict, metrics, diag = screen_factor(
        factor_name=candidate,
        factor_scores=candidate_panel,
        forward_returns=fwd_returns,
        existing_factors=list(_V2_ACTIVE_FACTORS.keys()),
        existing_factor_scores=active_panels,
        gate_config=_V2_GATE_CONFIG,
    )

    v_a7_max, v_a7_per_factor = _compute_v_a7(candidate_panel, active_panels, fwd_returns)
    v_a7_verdict = _verdict(v_a7_max, _V_A7_THRESHOLD, "<")

    g_overall = bool(verdict.passed_all)
    w8_a_overall_verdict = "PASS" if (g_overall and v_a7_verdict == "PASS") else "FAIL"

    print("")
    print(f"WAVE 8 W8-A ORTHOGONAL SCREEN: {candidate}")
    print("=" * 72)
    print(f"  Window         : {start} -> {end}")
    print(f"  Rebalance      : {len(rebalance)} weekly Fridays")
    for gate, defn in _V2_GATE_CONFIG.items():
        metric_name = defn["metric"]
        thr = defn["threshold"]
        direction = defn["direction"]
        val = metrics.get(metric_name, float("nan"))
        passed = verdict.gate_results.get(gate, False)
        status = "PASS" if passed else "FAIL"
        try:
            val_str = f"{val:>10.4f}"
        except (TypeError, ValueError):
            val_str = f"{val!r:>10}"
        print(
            f"  {gate} {metric_name:<35} {val_str}  {direction} {thr:<6} -> {status}"
        )
    print(
        f"  V_A7 max|corr| {v_a7_max!r:>10}  <  {_V_A7_THRESHOLD}  -> {v_a7_verdict}"
    )
    print("  Per-factor pearson L-S correlations:")
    for fname, rho in v_a7_per_factor.items():
        rho_str = f"{rho:+.4f}" if isinstance(rho, float) else "n/a"
        print(f"    {fname:<24} {rho_str}")
    print(f"  W8-A OVERALL   : {w8_a_overall_verdict}")
    print("=" * 72)

    payload: dict = {
        "iteration": 30 if candidate == "52w_high_proximity" else 31,
        "iteration_tag": f"iter-{30 if candidate == '52w_high_proximity' else 31}",
        "task_id": 160 if candidate == "52w_high_proximity" else 161,
        "wave": "Wave 8 W8-A orthogonal-discovery screen",
        "implements_preregistration": (
            "GL-0021 (V_A7 frozen iter-27..iter-32) + GL-0023 (W8-A restricted slate)"
        ),
        "candidate": candidate,
        "candidate_compute_fn": cand_compute_fn.__module__ + "." + cand_compute_fn.__name__,
        "candidate_sign_convention": cand_sign,
        "candidate_data_source": cand_source,
        "v2_active_universe": list(_V2_ACTIVE_FACTORS.keys()),
        "construction": {
            "n_quantiles": 5,
            "weighting": "equal",
            "annual_factor": 52,
            "ensemble": False,
            "k_of_n_coverage": False,
            "rank_percentile_tiebreak": "default_pandas",
        },
        "window": {"start": str(start), "end": str(end)},
        "n_rebalance_dates": len(rebalance),
        "n_forward_return_rows": int(len(fwd_returns)),
        "n_candidate_panel_rows": int(len(candidate_panel)),
        "v2_g0_g5": {
            "gate_config_sha256_anchor": _GATES_V2_SHA256,
            "metrics": {
                k: (float(v) if isinstance(v, (int, float)) and not pd.isna(v) else None)
                for k, v in metrics.items()
            },
            "gate_results": dict(verdict.gate_results),
            "passed_all": bool(verdict.passed_all),
            "verdict": "PASS" if verdict.passed_all else "FAIL",
        },
        "v_a7": {
            "metric": "max_abs_pearson_corr_against_v2_active_ls",
            "observed": v_a7_max,
            "threshold": _V_A7_THRESHOLD,
            "direction": "<",
            "verdict": v_a7_verdict,
            "per_factor_correlations": v_a7_per_factor,
        },
        "w8_a_overall_verdict": w8_a_overall_verdict,
        "no_renegotiation_clause": (
            "GL-0021 (V_A7) + GL-0023 (slate) freeze for iter-27..iter-32. "
            "A FAIL here is genuine; iter-32 GL-0024 routes via Iron Rule 11 "
            "strategy-class isolation; no bar/slate renegotiation (Iron Rule 9)."
        ),
        "iron_rule_compliance": {
            "rule_1_no_post_2023_dates": "PASS - end-date <= 2023-12-31",
            "rule_2_ap6_thresholds": f"PASS - gates_v2.yaml sha256 = {_GATES_V2_SHA256}",
            "rule_3_no_db_mocks": "PASS - executed against research.duckdb",
            "rule_7_gl0011_invariance": (
                f"PASS - writes ONLY to results/factors/{candidate}/gate_results_v2_wave8.json; "
                "canonical gate_results.json untouched"
            ),
            "rule_8_gates_frozen_pre_screen": (
                "PASS - v2 G0-G5 thresholds and V_A7=0.50 unchanged"
            ),
            "rule_11_strategy_class_isolation": (
                "PASS - W8-D evidence path "
                "(results/validation/wave8_d_single_factor/result.json) untouched"
            ),
            "rule_12_holdout_re_authorization": (
                "PASS - PASS/FAIL verdict creates NO path to holdout; "
                "Wave 9 governance row required"
            ),
        },
        "ap6_compliance": (
            "validation outcome of pre-registered frozen v2 G0-G5 (gates_v2.yaml) "
            "+ V_A7 (GL-0021) + GL-0023 slate; no threshold modification, no "
            "admission decision changed, no config/gates*.yaml committed change."
        ),
        "timestamp_source": f"{_SRC}.main",
    }

    out_path = output_dir / "gate_results_v2_wave8.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"Saved: {out_path}", flush=True)

    warns = [m for m in diag.messages if m.level.value == "WARNING"]
    if warns:
        print(f"\nDiagnostics warnings ({len(warns)}):", flush=True)
        for w in warns[:5]:
            print(f"  [{w.source}] {w.message}")

    return 0


if __name__ == "__main__":
    np.seterr(invalid="ignore")
    raise SystemExit(main())
