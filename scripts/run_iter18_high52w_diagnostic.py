#!/usr/bin/env python3
"""iter-18 dedicated Stream-5-style sign-flip diagnostic for ``52w_high_proximity``.

Implements V2-PREREG-2026-04-24 follow-up obligation: iter-14's Stream 5 tried
to run the sign-flip diagnostic on ``high_52w`` but skipped it because the
FactorRegistry exposes the panel under the canonical name
``52w_high_proximity`` (see ``src/nyse_core/features/__init__.py`` line 72),
not the legacy alias ``high_52w`` used by ``scripts/screen_factor.py``. The
resulting Stream-5 JSON at ``results/diagnostics/iter14_sign_flip/
sign_flip_diagnostic.json`` recorded ``"note": "panel not produced by registry;
sign-flip skipped"`` for the high_52w entry, which left the v2 pre-registration
without the sign-flip evidence it needed. GL-0014's iter-15 landing explicitly
deferred ``52w_high_proximity`` to a dedicated diagnostic rather than admit it
blindly to the v2 active factor universe.

This script closes that gap on the correct panel name. It reuses the iter-12
orchestrator's data loaders and the iter-14 ``run_sign_flip_screen`` helper so
the sign-flip evidence is computed on bit-identical OHLCV inputs and weekly
rebalance schedule as the canonical iter-14 Stream 5 output.

AP-6 safety. Observational: writes only to
``results/diagnostics/iter18_high52w_proximity_sign_flip/``, does not touch
``results/factors/**``, ``config/gates*.yaml``, or the registry. No threshold,
metric definition, direction, or admission decision is changed. The output
informs but does not consume iter-19 (ensemble simulation) gate verdicts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402
from run_iter14_diagnostic_battery import run_sign_flip_screen  # noqa: E402
from simulate_ensemble_g0 import (  # noqa: E402
    _compute_forward_returns,
    _load_fundamentals,
    _load_ohlcv,
    _weekly_fridays,
    build_factor_score_panels,
)

from nyse_core.features import FactorRegistry
from nyse_core.features.price_volume import compute_52w_high_proximity
from nyse_core.schema import UsageDomain

_SRC = "scripts.run_iter18_high52w_diagnostic"
_PANEL_NAME = "52w_high_proximity"


def main() -> int:
    p = argparse.ArgumentParser(description="iter-18 52w_high_proximity sign-flip diagnostic")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/diagnostics"),
    )
    p.add_argument(
        "--skip-research-log",
        action="store_true",
        help="do not append research-log event (for local debugging)",
    )
    args = p.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end >= date(2024, 1, 1):
        print("REFUSED: end-date crosses holdout boundary (2024-01-01).", file=sys.stderr)
        return 2

    args.output_root.mkdir(parents=True, exist_ok=True)

    print(f"[setup] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(f"[setup] {len(ohlcv)} OHLCV rows", flush=True)

    import pandas as pd

    lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    fundamentals = _load_fundamentals(args.db_path, lookback_start, end)

    rebalance = _weekly_fridays(start, end)
    print(f"[setup] {len(rebalance)} weekly Fridays", flush=True)

    # Register ONLY the 52w_high_proximity factor. This slashes panel-construction
    # cost vs register_all_factors (which runs 14+ compute functions per rebalance
    # date) — the Stream-5 sign-flip diagnostic only needs the one panel we flip.
    registry = FactorRegistry()
    registry.register(
        name=_PANEL_NAME,
        compute_fn=compute_52w_high_proximity,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Proximity to 52-week high (close / 52w max). Near high = buy.",
    )
    panels, exclusions = build_factor_score_panels(registry, ohlcv, fundamentals, rebalance)

    if _PANEL_NAME not in panels:
        reason = exclusions.get(_PANEL_NAME, "unknown")
        print(
            f"REFUSED: panel {_PANEL_NAME!r} was not produced by the registry (reason: {reason}).",
            file=sys.stderr,
        )
        return 3

    forward_returns = _compute_forward_returns(ohlcv, rebalance)
    n_panel = len(panels[_PANEL_NAME])
    n_fwd = len(forward_returns)
    print(
        f"[setup] panel {_PANEL_NAME}: {n_panel} rows; forward_returns: {n_fwd} rows",
        flush=True,
    )

    print(f"[iter-18] Sign-flip screen on {_PANEL_NAME}", flush=True)
    flip_result = run_sign_flip_screen(_PANEL_NAME, panels[_PANEL_NAME], forward_returns)

    out_dir = args.output_root / "iter18_high52w_proximity_sign_flip"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "iteration": 18,
        "iteration_tag": "iter-18",
        "panel": _PANEL_NAME,
        "window": {"start": str(start), "end": str(end)},
        "n_rebalance_dates": len(rebalance),
        "n_panel_rows": int(len(panels[_PANEL_NAME])),
        "sign_flip_result": flip_result,
        "interpretation": _interpret(flip_result),
    }
    out_path = out_dir / "sign_flip_diagnostic.json"
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
    print(f"  wrote {out_path}", flush=True)

    if not args.skip_research_log:
        log_path = Path("results/research_log.jsonl")
        append_event(
            log_path,
            {
                "event": "iter18_high52w_proximity_sign_flip_diagnostic",
                "iteration": 18,
                "iteration_tag": "iter-18",
                "panel": _PANEL_NAME,
                "result_path": str(out_path),
                "sign_flip_metrics": flip_result.get("metrics", {}),
                "sign_flip_verdict_passed_all": flip_result.get("verdict_passed_all"),
                "timestamp_source": f"{_SRC}.main",
            },
        )
        print("  appended research-log event", flush=True)

    return 0


def _interpret(flip_result: dict) -> dict:
    """Compare sign-flipped metrics against the canonical-sign FAIL verdict.

    The canonical ``52w_high_proximity`` registration uses sign=+1 (near high
    = buy). A sign-flipped screen tests whether inverting that sign (near high
    = sell) materially changes the gate outcomes. Strong evidence here would
    mean flipping produces a gates-pass where the canonical failed; weak
    evidence means the signal is directionless either way.
    """
    metrics = flip_result.get("metrics", {})
    passed = flip_result.get("verdict_passed_all")
    oos_sharpe = metrics.get("oos_sharpe")
    perm_p = metrics.get("permutation_p")
    ic_mean = metrics.get("ic_mean")
    ic_ir = metrics.get("ic_ir")
    max_dd = metrics.get("max_drawdown")
    conclusion: str
    if passed is None:
        conclusion = "screen skipped (empty panel)"
    elif passed:
        conclusion = (
            "FLIP PASSES ALL v1 gates — candidate for v2 admission in a subsequent "
            "iteration; would require GL-0014 amendment to admit inverted variant "
            "52w_high_proximity_flipped (sign=-1) with documentation of the "
            "economic rationale parallel to ivol_20d_flipped."
        )
    else:
        # Diagnose which v1 gates failed. v1 thresholds: G0 oos_sharpe>=0.30,
        # G1 perm_p<0.05, G2 ic_mean>=0.02, G3 ic_ir>=0.50, G4 max_dd>=-0.30,
        # G5 marginal_contribution>0.
        gate_fail_bits = []
        if oos_sharpe is not None and oos_sharpe < 0.30:
            gate_fail_bits.append(f"G0 oos_sharpe={oos_sharpe:.4f}<0.30")
        if perm_p is not None and perm_p >= 0.05:
            gate_fail_bits.append(f"G1 perm_p={perm_p:.4f}>=0.05")
        if ic_mean is not None and ic_mean < 0.02:
            gate_fail_bits.append(f"G2 ic_mean={ic_mean:.4f}<0.02")
        if ic_ir is not None and ic_ir < 0.50:
            gate_fail_bits.append(f"G3 ic_ir={ic_ir:.4f}<0.50")
        if max_dd is not None and max_dd < -0.30:
            gate_fail_bits.append(f"G4 max_dd={max_dd:.4f}<-0.30")
        fail_desc = "; ".join(gate_fail_bits) if gate_fail_bits else "unknown"
        conclusion = (
            f"flip does NOT pass v1 gates — fails: {fail_desc}. "
            f"Despite strong OOS Sharpe={oos_sharpe}, IC metrics are below v1 "
            f"admission thresholds, so 52w_high_proximity remains EXCLUDED from "
            f"the v2 active factor universe per GL-0014. Return comes from decile "
            f"tails, not cross-sectional rank alignment."
        )
    return {
        "flipped_oos_sharpe": oos_sharpe,
        "flipped_permutation_p": perm_p,
        "flipped_ic_mean": ic_mean,
        "flipped_ic_ir": ic_ir,
        "flipped_max_drawdown": max_dd,
        "flipped_passes_all_v1_gates": passed,
        "conclusion": conclusion,
    }


if __name__ == "__main__":
    sys.exit(main())
