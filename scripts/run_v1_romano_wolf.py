#!/usr/bin/env python3
"""Wave 6 / iter-22 — V1 Romano-Wolf adjusted-p validation.

Replaces the placeholder ``scripts/run_permutation_test.py`` for Wave 6 use.
Loads real per-factor long-short return series for the 5 active v2 factors
(GL-0014 frozen universe), aligns them on the common research-period index
(2016-2023), and runs Romano-Wolf stepdown to produce family-wise
error-rate-controlled adjusted p-values.

Active v2 factor universe (GL-0014, frozen iter-15..iter-20+)::

    [ivol_20d_flipped, piotroski_f_score, momentum_2_12, accruals, profitability]

V1 PASS condition (GL-0017 frozen iter-21..iter-25 per Iron Rule 9)::

    max(adjusted_p) < 0.05

V1 FAIL handling: iter-23 + iter-24 still run (cheap, reproducible,
exploratory-archive useful); iter-25 wrap declares EXPLORATORY VERDICT
(Path D, holdout protected) per GL-0019.

Construction-grammar identity with iter-19 #144:
- Reuses ``_build_panel_with_rng_tiebreak`` (V2-PREREG §2.2 RNG tie-break)
- Reuses ``_V2_ACTIVE_FACTORS`` registry from iter-19
- Reuses ``compute_long_short_returns`` (long top-quintile, short bottom-quintile)
- Reuses ``_load_ohlcv`` / ``_load_fundamentals`` / ``_weekly_fridays`` /
  ``_build_forward_returns`` from screen_factor (iter-7+ canonical loaders)

AP-6 + iron rule compliance:
- Refuses end_date >= 2024-01-01 (rule 1 — holdout protected)
- Reads bit-identical config/gates_v2.yaml (rules 2 + 8 — thresholds frozen)
- No DB mocks (rule 3 — runs against research.duckdb directly)
- No secret leakage (rule 4)
- Hash-chain append to results/research_log.jsonl (rule 6 — opt-in)
- Canonical results/factors/<f>/gate_results.json untouched (rule 7)
- Writes only to results/validation/iter22_romano_wolf/result.json
- GL-0017 V1 bar frozen at iter-21; not renegotiated iter-22..iter-25 (rule 9)

Default ``--skip-research-log`` is intentionally OFF here to mirror iter-19
behavior; the iter-22 invocation appends, the P0-prep smoke-test should
pass ``--skip-research-log`` to avoid polluting the chain pre-iter-21.
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

from nyse_core.factor_screening import compute_long_short_returns
from nyse_core.statistics import romano_wolf_stepdown

_SRC = "scripts.run_v1_romano_wolf"

_V1_BAR_THRESHOLD = 0.05  # GL-0017 V1 bar: max adjusted_p < 0.05
_V1_BAR_DIRECTION = "<"
_V1_BAR_METRIC = "max_adjusted_p"


def _build_factor_returns(
    db_path: Path,
    start: date,
    end: date,
) -> tuple[dict[str, pd.Series], dict[str, dict]]:
    """Build per-factor long-short return Series for the 5 active v2 factors.

    Returns
    -------
    tuple[dict[str, pd.Series], dict[str, dict]]
        - factor_returns: name -> daily-indexed L-S return Series
        - factor_diagnostics: name -> {n_periods, n_panel_rows} for evidence file
    """
    print(f"[1/4] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(f"[2/4] Loading fundamentals {lookback_start} -> {end}", flush=True)
    fundamentals = _load_fundamentals(db_path, lookback_start, end)
    print(f"       rows={len(fundamentals):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print("[3/4] Building 5 factor panels + L-S return series", flush=True)
    fwd_returns = _build_forward_returns(ohlcv, rebalance)

    factor_returns: dict[str, pd.Series] = {}
    factor_diag: dict[str, dict] = {}
    for fname, (compute_fn, sign, source, _) in _V2_ACTIVE_FACTORS.items():
        if source == "ohlcv":
            panel = _build_panel_with_rng_tiebreak(ohlcv, rebalance, compute_fn, sign, source)
        elif source == "fundamentals":
            panel = _build_panel_with_rng_tiebreak(fundamentals, rebalance, compute_fn, sign, source)
        else:
            raise ValueError(f"unknown data source for {fname!r}: {source}")
        if panel.empty:
            raise RuntimeError(f"factor panel empty for {fname!r}")
        ls_returns, _ = compute_long_short_returns(panel, fwd_returns)
        factor_returns[fname] = ls_returns
        factor_diag[fname] = {
            "n_panel_rows": int(len(panel)),
            "n_ls_periods": int(len(ls_returns)),
        }
        print(
            f"  {fname}: panel={len(panel):,} L-S periods={len(ls_returns)}",
            flush=True,
        )

    return factor_returns, factor_diag


def main() -> int:
    p = argparse.ArgumentParser(description="Wave 6 / iter-22 V1 Romano-Wolf validation")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument("--n-reps", type=int, default=500, help="Romano-Wolf bootstrap reps (V1 bar default 500)")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/validation/iter22_romano_wolf"),
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

    factor_returns, factor_diag = _build_factor_returns(args.db_path, start, end)

    print(f"[4/4] Running Romano-Wolf stepdown (n_reps={args.n_reps})", flush=True)
    adjusted_p, rw_diag = romano_wolf_stepdown(factor_returns, n_reps=args.n_reps)

    if not adjusted_p:
        print("REFUSED: Romano-Wolf returned empty adjusted_p dict.", file=sys.stderr)
        return 3

    max_adj_p = float(max(adjusted_p.values()))
    v1_passed = max_adj_p < _V1_BAR_THRESHOLD
    verdict_text = (
        f"PASS — max(adjusted_p) {max_adj_p:.4f} < 0.05 V1 bar (GL-0017)"
        if v1_passed
        else f"FAIL — max(adjusted_p) {max_adj_p:.4f} >= 0.05 V1 bar (GL-0017)"
    )

    print("")
    print("V1 ROMANO-WOLF STEPDOWN (iter-22)")
    print("=" * 66)
    print("  Active v2 factor universe : ['accruals', 'ivol_20d_flipped',")
    print("                                'momentum_2_12', 'piotroski_f_score',")
    print("                                'profitability']")
    print(f"  n_reps                    : {args.n_reps}")
    print(f"  Window                    : {start} -> {end}")
    print("  Per-factor adjusted_p:")
    for name in sorted(adjusted_p.keys()):
        print(f"    {name:24s} : {adjusted_p[name]:.4f}")
    print(f"  max(adjusted_p)           : {max_adj_p:.4f}")
    print("  V1 bar (GL-0017)          : adjusted_p < 0.05 (frozen iter-21)")
    print("=" * 66)
    print(f"  VERDICT: {verdict_text}")
    print("=" * 66)

    payload: dict[str, object] = {
        "iteration": 22,
        "iteration_tag": "iter-22",
        "task_id": 152,
        "wave": "Wave 6 — Path C statistical validation",
        "validation_bar": "V1",
        "validation_bar_metric": _V1_BAR_METRIC,
        "validation_bar_threshold": _V1_BAR_THRESHOLD,
        "validation_bar_direction": _V1_BAR_DIRECTION,
        "validation_bar_authorizing_row": "GL-0017",
        "implements_preregistration": "GL-0017 (Wave 6 V1/V2/V3/V4 frozen iter-21)",
        "active_v2_factor_universe": sorted(_V2_ACTIVE_FACTORS.keys()),
        "gates_v2_sha256": _GATES_V2_SHA256,
        "window": {"start": str(start), "end": str(end)},
        "n_reps": int(args.n_reps),
        "factor_diagnostics": factor_diag,
        "adjusted_p_values": {k: float(v) for k, v in adjusted_p.items()},
        "max_adjusted_p": max_adj_p,
        "v1_verdict": "PASS" if v1_passed else "FAIL",
        "verdict": "PASS" if v1_passed else "FAIL",
        "verdict_text": verdict_text,
        "no_renegotiation_clause": (
            "GL-0017 freezes V1 bar at adjusted_p < 0.05 for iter-21..iter-25; "
            "FAIL here is genuine, not a bar-renegotiation trigger (Iron Rule 9)."
        ),
        "ap6_compliance": (
            "validation against pre-registered frozen V1 bar (GL-0017); no "
            "threshold modification, no admission decision changed, no "
            "config/gates*.yaml touched."
        ),
        "rw_diagnostics_messages": [
            {"level": m.level.value, "source": m.source, "message": m.message} for m in rw_diag.messages
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
                "event": "iter22_v1_romano_wolf_validation",
                "iteration": 22,
                "iteration_tag": "iter-22",
                "task_id": 152,
                "wave": "Wave 6",
                "validation_bar": "V1",
                "active_v2_factor_universe": sorted(_V2_ACTIVE_FACTORS.keys()),
                "n_reps": int(args.n_reps),
                "adjusted_p_values": {k: float(v) for k, v in adjusted_p.items()},
                "max_adjusted_p": max_adj_p,
                "v1_verdict": "PASS" if v1_passed else "FAIL",
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
