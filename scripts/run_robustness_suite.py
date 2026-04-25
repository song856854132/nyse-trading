#!/usr/bin/env python3
"""Wave 6 / iter-24 — V3 parameter sensitivity + V4 leave-one-factor-out validation.

Combined orchestrator for the two robustness sub-tests in Wave 6:

V3 — Parameter sensitivity (PASS iff max relative Sharpe deviation <= 20%).
V4 — Leave-one-factor-out (PASS iff V4a AND V4b sub-bars both pass):
     - V4a: min(LOO Sharpe) >= 0.30 (absolute floor)
     - V4b: max relative drop <= 35% (relative floor; baseline +0.5549, threshold ~0.36)

Joint verdict (V3 PASS AND V4 PASS) is required for iter-25 Branch A
authorization. Any single bar FAIL (V3 / V4a / V4b) triggers Branch B
(EXPLORATORY VERDICT, GL-0019, holdout protected).

V3 GRID — IMPLEMENTATION NOTE.

The plan's nominal V3 grid (dreamy-riding-quasar.md) lists 5 parameters x
2 perturbations = 10 entries. Of those, 4 of the 5 parameter rows
(top_n, sell_buffer, ridge_alpha, bear_exposure) test knobs that are NOT
in the iter-19 #144 frozen ensemble construction:

- iter-19 uses ``compute_long_short_returns(n_quantiles=5)`` quintile L-S,
  NOT top-N selection (no top_n knob).
- iter-19 has no inertia/sell-buffer logic (no sell_buffer knob).
- iter-19 uses ``equal_sharpes = {f: 1.0 for f in panels}`` simple-mean
  aggregation, NOT a Ridge model (no ridge_alpha knob).
- iter-19 has no regime overlay; output is raw quintile L-S returns
  (no bear_exposure knob).

Per Codex P2 finding cited in the plan: "testing knobs not in the frozen
strategy is contamination." The plan acknowledges this explicitly for
bear_exposure ("if a future review confirms regime logic is NOT in the
iter-19 decision rule, drop this row from V3"). The same logic applies to
top_n, sell_buffer, ridge_alpha.

This implementation therefore perturbs ONLY iter-19-construction knobs:

V3 grid (4 perturbations):
- K coverage = 2 (baseline 3) -- ``compute_ensemble_weights(min_factor_coverage=K)``
- K coverage = 4 (baseline 3) -- ``compute_ensemble_weights(min_factor_coverage=K)``
- n_quantiles = 3 (baseline 5) -- ``compute_long_short_returns(n_quantiles=Q)``
  (more concentrated portfolio; analog to "top_n decreased")
- n_quantiles = 10 (baseline 5) -- ``compute_long_short_returns(n_quantiles=Q)``
  (deciles; analog to "top_n increased / smaller per-leg")

This deviation from the plan's nominal 10-entry grid is reflected in
GL-0017 at iter-21 governance commit BEFORE iter-24 executes (Iron Rule 9
no-renegotiation applies to the bar threshold, not to the implementation
detail of which iter-19-construction knobs are perturbed). Documented
explicitly in the V3 grid emitted by this script.

V4 GRID (5 perturbations) -- unchanged from plan:
For each f in active v2 universe, drop f, run ensemble on remaining 4
factors with K=2-of-N=4 coverage (preserves >=40% factor-coverage analog
to K=3-of-N=5).

Active v2 factor universe (GL-0014 frozen)::

    [ivol_20d_flipped, piotroski_f_score, momentum_2_12, accruals, profitability]

AP-6 + iron rule compliance:
- Refuses end_date >= 2024-01-01 (rule 1 -- holdout protected)
- Reads bit-identical config/gates_v2.yaml (rules 2 + 8)
- No DB mocks (rule 3)
- No secret leakage (rule 4)
- Hash-chain append to results/research_log.jsonl (rule 6 -- opt-in)
- Canonical results/factors/<f>/gate_results.json untouched (rule 7)
- Writes only to results/validation/iter24_robustness/{*.json, summary.json}
- GL-0017 V3+V4 bars frozen at iter-21; not renegotiated iter-22..iter-25 (rule 9)
- AP-6: strategy_params.yaml/gates_v2.yaml NEVER edited; perturbations are
  in-memory function arguments only.
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
    _PHASE3_TARGET_FROZEN_GL_0015,
    _V2_ACTIVE_FACTORS,
    _build_panel_with_rng_tiebreak,
)

from nyse_core.factor_screening import (
    compute_ensemble_weights,
    compute_long_short_returns,
)
from nyse_core.metrics import sharpe_ratio

_SRC = "scripts.run_robustness_suite"

# Baselines (iter-19 #144 frozen)
_BASELINE_SHARPE = 0.5549046499613932  # from results/ensemble/iter19_v2_phase3/ensemble_result.json
_BASELINE_K = 3
_BASELINE_N_QUANTILES = 5

# GL-0017 frozen bars
_V3_BAR_MAX_REL_DEVIATION = 0.20  # PASS iff max(|S_i - S_0| / S_0) <= 0.20
_V4A_BAR_MIN_LOO_SHARPE = 0.30  # PASS iff min(LOO Sharpe) >= 0.30
_V4B_BAR_MAX_REL_DROP = 0.35  # PASS iff max negative-side relative drop <= 0.35


def _build_panels_and_returns(
    db_path: Path,
    start: date,
    end: date,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict]:
    """Build the iter-19 #144 panels + forward returns (shared across V3 + V4)."""
    print(f"[1/3] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(f"[2/3] Loading fundamentals {lookback_start} -> {end}", flush=True)
    fundamentals = _load_fundamentals(db_path, lookback_start, end)
    print(f"       rows={len(fundamentals):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print("[3/3] Building 5 factor panels with V2-PREREG RNG tie-break", flush=True)
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

    setup_diag = {
        "n_rebalance_dates": len(rebalance),
        "n_forward_return_rows": int(len(fwd_returns)),
        "n_panel_rows": panel_rows,
    }
    return panels, fwd_returns, setup_diag


def _run_ensemble_sharpe(
    panels: dict[str, pd.DataFrame],
    fwd_returns: pd.DataFrame,
    min_factor_coverage: int,
    n_quantiles: int,
) -> tuple[float | None, dict]:
    """Run iter-19 ensemble construction with given K and n_quantiles, return OOS Sharpe.

    Mirrors simulate_v2_ensemble_phase3.py exactly except for the two perturbed knobs.
    Returns (sharpe, run_diag).
    """
    equal_sharpes = dict.fromkeys(panels.keys(), 1.0)
    ensemble_scores, _ = compute_ensemble_weights(
        panels, equal_sharpes, min_factor_coverage=min_factor_coverage
    )
    ls_returns, _ = compute_long_short_returns(ensemble_scores, fwd_returns, n_quantiles=n_quantiles)
    n_periods = int(len(ls_returns))
    if n_periods < 2:
        return None, {"n_periods": n_periods, "n_ensemble_rows": int(len(ensemble_scores))}
    sharpe, _ = sharpe_ratio(ls_returns, annual_factor=52)
    return (
        float(sharpe) if sharpe is not None else None,
        {
            "n_periods": n_periods,
            "n_ensemble_rows": int(len(ensemble_scores)),
            "n_ensemble_dates": int(ensemble_scores["date"].nunique()),
        },
    )


def _run_v3_grid(
    panels: dict[str, pd.DataFrame],
    fwd_returns: pd.DataFrame,
    output_dir: Path,
) -> dict:
    """V3 perturbation grid -- 4 perturbations on iter-19-construction knobs."""
    grid: list[tuple[str, str, dict]] = [
        ("K_coverage", "K=2", {"min_factor_coverage": 2, "n_quantiles": _BASELINE_N_QUANTILES}),
        ("K_coverage", "K=4", {"min_factor_coverage": 4, "n_quantiles": _BASELINE_N_QUANTILES}),
        ("n_quantiles", "n=3", {"min_factor_coverage": _BASELINE_K, "n_quantiles": 3}),
        ("n_quantiles", "n=10", {"min_factor_coverage": _BASELINE_K, "n_quantiles": 10}),
    ]
    runs: list[dict] = []
    for parameter, label, kwargs in grid:
        print(
            f"  [V3] {parameter}={label}: K={kwargs['min_factor_coverage']}, n_q={kwargs['n_quantiles']}",
            flush=True,
        )
        sharpe, run_diag = _run_ensemble_sharpe(panels, fwd_returns, **kwargs)
        rel_dev = float(abs(sharpe - _BASELINE_SHARPE) / _BASELINE_SHARPE) if sharpe is not None else None
        run_record: dict = {
            "parameter": parameter,
            "perturbation_label": label,
            "kwargs": kwargs,
            "sharpe": sharpe,
            "baseline_sharpe": _BASELINE_SHARPE,
            "relative_deviation": rel_dev,
            "diagnostics": run_diag,
        }
        runs.append(run_record)
        per_run_path = output_dir / f"v3_perturbation_{parameter}_{label.replace('=', '_')}.json"
        per_run_path.write_text(json.dumps(run_record, indent=2, sort_keys=True, default=str))
        print(f"       Sharpe={sharpe} rel_dev={rel_dev}  ->  {per_run_path.name}", flush=True)

    valid_devs = [r["relative_deviation"] for r in runs if r["relative_deviation"] is not None]
    max_rel_dev = float(max(valid_devs)) if valid_devs else None
    v3_passed = (
        max_rel_dev is not None
        and max_rel_dev <= _V3_BAR_MAX_REL_DEVIATION
        and all(r["sharpe"] is not None for r in runs)
    )
    return {
        "n_runs": len(runs),
        "runs": runs,
        "max_relative_deviation": max_rel_dev,
        "v3_bar_threshold": _V3_BAR_MAX_REL_DEVIATION,
        "v3_bar_direction": "<=",
        "v3_verdict": "PASS" if v3_passed else "FAIL",
        "implementation_note": (
            "V3 perturbs only iter-19-construction knobs (K coverage, n_quantiles); "
            "plan's top_n/sell_buffer/ridge_alpha/bear_exposure entries omitted per "
            "Codex P2 contamination warning -- those knobs are not in iter-19 frozen ensemble."
        ),
    }


def _run_v4_grid(
    panels: dict[str, pd.DataFrame],
    fwd_returns: pd.DataFrame,
    output_dir: Path,
) -> dict:
    """V4 leave-one-factor-out grid -- 5 LOO drops with K=2-of-N=4 coverage."""
    factor_names = sorted(panels.keys())
    runs: list[dict] = []

    for drop_factor in factor_names:
        loo_panels = {f: panels[f] for f in factor_names if f != drop_factor}
        loo_factors = sorted(loo_panels.keys())
        print(f"  [V4] drop={drop_factor}: remaining={loo_factors} (K=2-of-N=4)", flush=True)
        sharpe, run_diag = _run_ensemble_sharpe(
            loo_panels,
            fwd_returns,
            min_factor_coverage=2,  # K=2-of-N=4 preserves >=40% coverage analog
            n_quantiles=_BASELINE_N_QUANTILES,
        )
        rel_drop_negative_side = None
        if sharpe is not None and sharpe < _BASELINE_SHARPE:
            rel_drop_negative_side = float((_BASELINE_SHARPE - sharpe) / _BASELINE_SHARPE)
        run_record: dict = {
            "dropped_factor": drop_factor,
            "remaining_factors": loo_factors,
            "k_coverage": 2,
            "n_remaining_factors": 4,
            "sharpe": sharpe,
            "baseline_sharpe": _BASELINE_SHARPE,
            "negative_side_relative_drop": rel_drop_negative_side,
            "diagnostics": run_diag,
        }
        runs.append(run_record)
        per_run_path = output_dir / f"v4_loo_drop_{drop_factor}.json"
        per_run_path.write_text(json.dumps(run_record, indent=2, sort_keys=True, default=str))
        print(
            f"       Sharpe={sharpe} neg_drop={rel_drop_negative_side}  ->  {per_run_path.name}", flush=True
        )

    valid_sharpes = [r["sharpe"] for r in runs if r["sharpe"] is not None]
    min_loo_sharpe = float(min(valid_sharpes)) if valid_sharpes else None
    v4a_passed = (
        min_loo_sharpe is not None
        and min_loo_sharpe >= _V4A_BAR_MIN_LOO_SHARPE
        and all(r["sharpe"] is not None for r in runs)
    )

    valid_neg_drops = [
        r["negative_side_relative_drop"] for r in runs if r["negative_side_relative_drop"] is not None
    ]
    max_neg_drop = float(max(valid_neg_drops)) if valid_neg_drops else 0.0
    v4b_passed = max_neg_drop <= _V4B_BAR_MAX_REL_DROP and all(r["sharpe"] is not None for r in runs)

    v4_passed = v4a_passed and v4b_passed

    return {
        "n_runs": len(runs),
        "runs": runs,
        "min_loo_sharpe": min_loo_sharpe,
        "max_negative_side_relative_drop": max_neg_drop,
        "v4a_bar_threshold": _V4A_BAR_MIN_LOO_SHARPE,
        "v4a_bar_direction": ">=",
        "v4a_verdict": "PASS" if v4a_passed else "FAIL",
        "v4b_bar_threshold": _V4B_BAR_MAX_REL_DROP,
        "v4b_bar_direction": "<=",
        "v4b_verdict": "PASS" if v4b_passed else "FAIL",
        "v4_verdict": "PASS" if v4_passed else "FAIL",
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Wave 6 / iter-24 V3 + V4 robustness suite")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/validation/iter24_robustness"),
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

    panels, fwd_returns, setup_diag = _build_panels_and_returns(args.db_path, start, end)

    print("\n=== V3 PERTURBATION GRID (4 runs, iter-19-construction knobs only) ===", flush=True)
    v3_result = _run_v3_grid(panels, fwd_returns, args.output_dir)

    print("\n=== V4 LEAVE-ONE-FACTOR-OUT GRID (5 runs, K=2-of-N=4) ===", flush=True)
    v4_result = _run_v4_grid(panels, fwd_returns, args.output_dir)

    joint_passed = v3_result["v3_verdict"] == "PASS" and v4_result["v4_verdict"] == "PASS"
    joint_verdict = "PASS" if joint_passed else "FAIL"

    print("")
    print("V3 + V4 ROBUSTNESS SUITE (iter-24)")
    print("=" * 66)
    print(f"  Active v2 factor universe : {sorted(panels.keys())}")
    print(f"  Window                    : {start} -> {end}")
    print(f"  Baseline Sharpe (iter-19) : {_BASELINE_SHARPE:+.4f}")
    print("  --- V3 ---")
    print(f"  V3 perturbations          : {v3_result['n_runs']}")
    if v3_result["max_relative_deviation"] is not None:
        print(f"  Max relative deviation    : {v3_result['max_relative_deviation']:.4f}")
    print(f"  V3 bar (GL-0017)          : max_rel_dev <= {_V3_BAR_MAX_REL_DEVIATION}")
    print(f"  V3 verdict                : {v3_result['v3_verdict']}")
    print("  --- V4 ---")
    print(f"  V4 LOO drops              : {v4_result['n_runs']}")
    if v4_result["min_loo_sharpe"] is not None:
        print(f"  min(LOO Sharpe)           : {v4_result['min_loo_sharpe']:+.4f}")
    print(f"  max neg-side rel drop     : {v4_result['max_negative_side_relative_drop']:.4f}")
    print(f"  V4a bar (GL-0017)         : min_loo_sharpe >= {_V4A_BAR_MIN_LOO_SHARPE}")
    print(f"  V4b bar (GL-0017)         : max_neg_rel_drop <= {_V4B_BAR_MAX_REL_DROP}")
    print(f"  V4a verdict               : {v4_result['v4a_verdict']}")
    print(f"  V4b verdict               : {v4_result['v4b_verdict']}")
    print(f"  V4 verdict (V4a AND V4b)  : {v4_result['v4_verdict']}")
    print("=" * 66)
    print(f"  JOINT VERDICT (V3 AND V4) : {joint_verdict}")
    print("=" * 66)

    summary: dict[str, object] = {
        "iteration": 24,
        "iteration_tag": "iter-24",
        "task_id": 154,
        "wave": "Wave 6 -- Path C statistical validation",
        "validation_bars": ["V3", "V4a", "V4b"],
        "validation_bar_authorizing_row": "GL-0017",
        "implements_preregistration": "GL-0017 (Wave 6 V1/V2/V3/V4 frozen iter-21)",
        "active_v2_factor_universe": sorted(panels.keys()),
        "gates_v2_sha256": _GATES_V2_SHA256,
        "window": {"start": str(start), "end": str(end)},
        "baseline_sharpe_iter19": _BASELINE_SHARPE,
        "baseline_k_coverage": _BASELINE_K,
        "baseline_n_quantiles": _BASELINE_N_QUANTILES,
        "phase3_target_frozen_gl_0015": _PHASE3_TARGET_FROZEN_GL_0015,
        "setup_diagnostics": setup_diag,
        "v3": v3_result,
        "v4": v4_result,
        "v3_verdict": v3_result["v3_verdict"],
        "v4_verdict": v4_result["v4_verdict"],
        "v4a_verdict": v4_result["v4a_verdict"],
        "v4b_verdict": v4_result["v4b_verdict"],
        "joint_verdict": joint_verdict,
        "verdict": joint_verdict,
        "no_renegotiation_clause": (
            "GL-0017 freezes V3 (max_rel_dev <= 0.20), V4a (min_loo_sharpe >= 0.30), "
            "and V4b (max_neg_rel_drop <= 0.35) for iter-21..iter-25; FAIL here is "
            "genuine, not a bar-renegotiation trigger (Iron Rule 9)."
        ),
        "ap6_compliance": (
            "validation against pre-registered frozen V3/V4 bars (GL-0017); no "
            "threshold modification, no admission decision changed, no "
            "config/gates*.yaml or config/strategy_params.yaml committed change."
        ),
    }

    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))
    print(f"Saved: {summary_path}", flush=True)

    if not args.skip_research_log:
        log_path = Path("results/research_log.jsonl")
        v3_sharpes = {r["perturbation_label"]: r["sharpe"] for r in v3_result["runs"]}
        v4_sharpes = {r["dropped_factor"]: r["sharpe"] for r in v4_result["runs"]}
        append_event(
            log_path,
            {
                "event": "iter24_v3_v4_robustness_validation",
                "iteration": 24,
                "iteration_tag": "iter-24",
                "task_id": 154,
                "wave": "Wave 6",
                "validation_bars": ["V3", "V4a", "V4b"],
                "active_v2_factor_universe": sorted(panels.keys()),
                "baseline_sharpe": _BASELINE_SHARPE,
                "v3_sharpes": v3_sharpes,
                "v3_max_relative_deviation": v3_result["max_relative_deviation"],
                "v3_verdict": v3_result["v3_verdict"],
                "v4_loo_sharpes": v4_sharpes,
                "v4_min_loo_sharpe": v4_result["min_loo_sharpe"],
                "v4_max_negative_side_relative_drop": v4_result["max_negative_side_relative_drop"],
                "v4a_verdict": v4_result["v4a_verdict"],
                "v4b_verdict": v4_result["v4b_verdict"],
                "v4_verdict": v4_result["v4_verdict"],
                "joint_verdict": joint_verdict,
                "artifact": str(summary_path),
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
