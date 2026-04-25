#!/usr/bin/env python3
"""Wave 6 / iter-23 — V2 block bootstrap CI lower bound validation.

Replaces the placeholder ``scripts/run_permutation_test.py`` for Wave 6 use.
Reconstructs the iter-19 #144 v2 ensemble daily return series (5-factor active
universe under K=3-of-N=5 coverage with equal-Sharpe simple-mean aggregation),
then runs a circular block bootstrap to compute a 95% CI on the OOS Sharpe.

V2 PASS condition (GL-0017 frozen iter-21..iter-25 per Iron Rule 9)::

    bootstrap_ci_lower >= 0.30

V2 bar derivation (per plan, committed in GL-0017):
- 0.30 = 60% of the GL-0015 frozen Phase 3 target (0.50)
- Below 0.30: lower tail dips into ABANDONMENT_CRITERIA.md A9 weak-signal
  range [0, 0.3]
- ρ=0.834 means effective N << 5 — the bootstrap distribution is narrower
  than 5 orthogonal bets but its center matches the +0.5549 point estimate

V2 FAIL handling: iter-24 still runs (cheap, reproducible); iter-25 wrap
declares EXPLORATORY VERDICT (Path D, holdout protected) per GL-0019.

Construction-grammar identity with iter-19 #144:
- Reuses ``_build_panel_with_rng_tiebreak`` and ``_V2_ACTIVE_FACTORS``
- Reuses ``compute_ensemble_weights(min_factor_coverage=3)``
- Reuses ``compute_long_short_returns`` for the ensemble L-S return series
- Reuses ``_load_ohlcv`` / ``_load_fundamentals`` / ``_weekly_fridays`` /
  ``_build_forward_returns`` from screen_factor

Bootstrap parameters frozen in GL-0017:
- n_reps = 10000 (V2 spec)
- block_size = 63 (≈3 months of trading days; preserves time-series structure)
- alpha = 0.05 (95% CI)

AP-6 + iron rule compliance:
- Refuses end_date >= 2024-01-01 (rule 1 — holdout protected)
- Reads bit-identical config/gates_v2.yaml (rules 2 + 8)
- No DB mocks (rule 3)
- No secret leakage (rule 4)
- Hash-chain append to results/research_log.jsonl (rule 6 — opt-in)
- Canonical results/factors/<f>/gate_results.json untouched (rule 7)
- Writes only to results/validation/iter23_bootstrap_ci/result.json
- GL-0017 V2 bar frozen at iter-21; not renegotiated iter-22..iter-25 (rule 9)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402
from screen_factor import (  # noqa: E402
    _build_forward_returns,
    _load_fundamentals,
    _load_ohlcv,
    _weekly_fridays,
)
from simulate_v2_ensemble_phase3 import (  # noqa: E402
    _GATES_V2_SHA256,
    _V2_ACTIVE_FACTORS,
    _build_panel_with_rng_tiebreak,
)

from nyse_core.factor_screening import (
    compute_ensemble_weights,
    compute_long_short_returns,
)
from nyse_core.metrics import sharpe_ratio
from nyse_core.statistics import block_bootstrap_ci

_SRC = "scripts.run_v2_bootstrap_ci"

_V2_BAR_THRESHOLD = 0.30  # GL-0017 V2 bar: ci_lower >= 0.30
_V2_BAR_DIRECTION = ">="
_V2_BAR_METRIC = "bootstrap_ci_lower"


def _build_ensemble_returns(
    db_path: Path,
    start: date,
    end: date,
) -> tuple[pd.Series, dict]:
    """Reconstruct the iter-19 #144 v2 ensemble L-S daily return series.

    Returns
    -------
    tuple[pd.Series, dict]
        - ensemble_ls_returns: daily-indexed L-S return Series
        - construction_diag: panel/ensemble row counts for evidence file
    """
    print(f"[1/5] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(f"[2/5] Loading fundamentals {lookback_start} -> {end}", flush=True)
    fundamentals = _load_fundamentals(db_path, lookback_start, end)
    print(f"       rows={len(fundamentals):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print("[3/5] Building 5 factor panels with V2-PREREG RNG tie-break", flush=True)
    fwd_returns = _build_forward_returns(ohlcv, rebalance)

    panels: dict[str, pd.DataFrame] = {}
    panel_rows: dict[str, int] = {}
    for fname, (compute_fn, sign, source, _) in _V2_ACTIVE_FACTORS.items():
        if source == "ohlcv":
            panel = _build_panel_with_rng_tiebreak(ohlcv, rebalance, compute_fn, sign, source)
        elif source == "fundamentals":
            panel = _build_panel_with_rng_tiebreak(fundamentals, rebalance, compute_fn, sign, source)
        else:
            raise ValueError(f"unknown data source for {fname!r}: {source}")
        if panel.empty:
            raise RuntimeError(f"factor panel empty for {fname!r}")
        panels[fname] = panel
        panel_rows[fname] = int(len(panel))
        print(f"  {fname}: {len(panel):,} rows", flush=True)

    print("[4/5] Aggregating with K=3-of-N=5 coverage gate (equal-Sharpe weights)", flush=True)
    equal_sharpes = dict.fromkeys(panels.keys(), 1.0)
    ensemble_scores, _ = compute_ensemble_weights(panels, equal_sharpes, min_factor_coverage=3)
    n_dates = ensemble_scores["date"].nunique() if not ensemble_scores.empty else 0
    print(
        f"       ensemble rows: {len(ensemble_scores):,} across {n_dates} dates",
        flush=True,
    )

    print("[5/5] Computing ensemble L-S return series", flush=True)
    ensemble_ls_returns, _ = compute_long_short_returns(ensemble_scores, fwd_returns)

    diag = {
        "n_rebalance_dates": len(rebalance),
        "n_forward_return_rows": int(len(fwd_returns)),
        "n_panel_rows": panel_rows,
        "n_ensemble_rows": int(len(ensemble_scores)),
        "n_ensemble_dates": int(n_dates),
        "n_ls_periods": int(len(ensemble_ls_returns)),
    }
    return ensemble_ls_returns, diag


def main() -> int:
    p = argparse.ArgumentParser(description="Wave 6 / iter-23 V2 bootstrap CI validation")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument("--n-reps", type=int, default=10000, help="bootstrap reps (V2 bar default 10000)")
    p.add_argument("--block-size", type=int, default=63, help="block size in trading days (V2 default 63)")
    p.add_argument("--alpha", type=float, default=0.05, help="significance level (V2 default 0.05 = 95% CI)")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/validation/iter23_bootstrap_ci"),
    )
    p.add_argument(
        "--skip-research-log",
        action="store_true",
        help="do not append research-log event (use during P0 smoke-test pre-iter-21)",
    )
    args = p.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end >= date(2024, 1, 1):
        print("REFUSED: end-date crosses holdout boundary (2024-01-01).", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    ensemble_ls_returns, construction_diag = _build_ensemble_returns(args.db_path, start, end)

    if len(ensemble_ls_returns) == 0:
        print("REFUSED: ensemble L-S return series is empty.", file=sys.stderr)
        return 3

    annual_factor = 52  # iter-19 convention: 5-day fwd return at weekly cadence
    point_sharpe, _ = sharpe_ratio(ensemble_ls_returns, annual_factor=annual_factor)

    print(
        f"\nRunning block bootstrap CI (n_reps={args.n_reps}, "
        f"block_size={args.block_size}, alpha={args.alpha})",
        flush=True,
    )
    (ci_lower, ci_upper), bs_diag = block_bootstrap_ci(
        ensemble_ls_returns,
        n_reps=args.n_reps,
        block_size=args.block_size,
        alpha=args.alpha,
    )

    v2_passed = ci_lower >= _V2_BAR_THRESHOLD
    verdict_text = (
        f"PASS — bootstrap_ci_lower {ci_lower:.4f} >= 0.30 V2 bar (GL-0017)"
        if v2_passed
        else f"FAIL — bootstrap_ci_lower {ci_lower:.4f} < 0.30 V2 bar (GL-0017)"
    )

    print("")
    print("V2 BLOCK BOOTSTRAP CI (iter-23)")
    print("=" * 66)
    print("  Active v2 factor universe : ['accruals', 'ivol_20d_flipped',")
    print("                                'momentum_2_12', 'piotroski_f_score',")
    print("                                'profitability']")
    print(f"  n_reps                    : {args.n_reps}")
    print(f"  block_size                : {args.block_size}")
    print(f"  alpha                     : {args.alpha} ({(1 - args.alpha) * 100:.0f}% CI)")
    print(f"  Window                    : {start} -> {end}")
    print(f"  Point estimate Sharpe     : {float(point_sharpe):+.4f}")
    print(f"  Bootstrap CI lower        : {ci_lower:+.4f}")
    print(f"  Bootstrap CI upper        : {ci_upper:+.4f}")
    print("  V2 bar (GL-0017)          : ci_lower >= 0.30 (frozen iter-21)")
    print("=" * 66)
    print(f"  VERDICT: {verdict_text}")
    print("=" * 66)

    payload: dict[str, object] = {
        "iteration": 23,
        "iteration_tag": "iter-23",
        "task_id": 153,
        "wave": "Wave 6 — Path C statistical validation",
        "validation_bar": "V2",
        "validation_bar_metric": _V2_BAR_METRIC,
        "validation_bar_threshold": _V2_BAR_THRESHOLD,
        "validation_bar_direction": _V2_BAR_DIRECTION,
        "validation_bar_authorizing_row": "GL-0017",
        "implements_preregistration": "GL-0017 (Wave 6 V1/V2/V3/V4 frozen iter-21)",
        "active_v2_factor_universe": sorted(_V2_ACTIVE_FACTORS.keys()),
        "gates_v2_sha256": _GATES_V2_SHA256,
        "window": {"start": str(start), "end": str(end)},
        "n_reps": int(args.n_reps),
        "block_size": int(args.block_size),
        "alpha": float(args.alpha),
        "annualization_periods_per_year": annual_factor,
        "construction_diagnostics": construction_diag,
        "point_estimate_sharpe": float(point_sharpe) if point_sharpe is not None else None,
        "bootstrap_ci_lower": float(ci_lower),
        "bootstrap_ci_upper": float(ci_upper),
        "v2_verdict": "PASS" if v2_passed else "FAIL",
        "verdict": "PASS" if v2_passed else "FAIL",
        "verdict_text": verdict_text,
        "no_renegotiation_clause": (
            "GL-0017 freezes V2 bar at ci_lower >= 0.30 for iter-21..iter-25; "
            "FAIL here is genuine, not a bar-renegotiation trigger (Iron Rule 9)."
        ),
        "ap6_compliance": (
            "validation against pre-registered frozen V2 bar (GL-0017); no "
            "threshold modification, no admission decision changed, no "
            "config/gates*.yaml touched."
        ),
        "v2_bar_derivation_memo": (
            "0.30 = 60% of GL-0015 frozen Phase 3 target (0.50); below 0.30 the "
            "lower tail enters ABANDONMENT_CRITERIA.md A9 weak-signal range [0, 0.3]; "
            "ρ=0.834 narrows bootstrap distribution but does not move its center."
        ),
        "bs_diagnostics_messages": [
            {"level": m.level.value, "source": m.source, "message": m.message} for m in bs_diag.messages
        ],
    }

    out_path = args.output_dir / "result.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"Saved: {out_path}", flush=True)

    if not args.skip_research_log:
        log_path = Path("results/research_log.jsonl")
        append_event(
            log_path,
            {
                "event": "iter23_v2_bootstrap_ci_validation",
                "iteration": 23,
                "iteration_tag": "iter-23",
                "task_id": 153,
                "wave": "Wave 6",
                "validation_bar": "V2",
                "active_v2_factor_universe": sorted(_V2_ACTIVE_FACTORS.keys()),
                "n_reps": int(args.n_reps),
                "block_size": int(args.block_size),
                "alpha": float(args.alpha),
                "point_estimate_sharpe": float(point_sharpe) if point_sharpe is not None else None,
                "bootstrap_ci_lower": float(ci_lower),
                "bootstrap_ci_upper": float(ci_upper),
                "v2_verdict": "PASS" if v2_passed else "FAIL",
                "verdict_text": verdict_text,
                "artifact": str(out_path),
                "gates_v2_sha256": _GATES_V2_SHA256,
                "frozen_bar_authorizing_row": "GL-0017",
                "timestamp_source": f"{_SRC}.main",
            },
        )
        print("  appended research-log event", flush=True)

    return 0


if __name__ == "__main__":
    np.seterr(invalid="ignore")
    sys.exit(main())
