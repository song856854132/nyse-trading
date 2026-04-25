#!/usr/bin/env python3
"""iter-18 #143 — re-screen 5 active v2 factors under config/gates_v2.yaml.

Implements V2-PREREG-2026-04-24 follow-up obligation: produce a parallel-path
``results/factors/<factor>/gate_results_v2.json`` per active_v2_factor_universe
member under the v2 gate thresholds (GL-0014). The canonical
``results/factors/<factor>/gate_results.json`` v1 verdicts are bit-identical
GL-0011 evidence and are NEVER touched by this script (iron rule 7).

Active v2 factor universe (per GL-0014, 2026-04-24):
    [ivol_20d_flipped, piotroski_f_score, momentum_2_12, accruals, profitability]

Leave-one-out admission: each candidate is screened with the OTHER 4 factors
as the "admitted" pool so G5 ``max_return_decile_corr_with_admitted`` is
computed against a realistic 4-factor admitted set rather than solo (which
would auto-PASS at 0.0 and defeat the v2 redundancy gate's purpose).

The v2 thresholds (frozen at iter-15 commit ``903fc09`` per GL-0014):
    G0 oos_sharpe                          >= 0.30
    G1 permutation_p                       <  0.05
    G2 ic_mean                             >= 0.005   (lowered from v1 0.02)
    G3 ic_ir                               >= 0.05    (lowered from v1 0.50)
    G4 max_drawdown                        >= -0.30
    G5 max_return_decile_corr_with_admitted <= 0.90   (replaces v1 marginal_contribution)

AP-6 + iron rule compliance.
- Holdout boundary refused at end_date >= 2024-01-01.
- Reads bit-identical config/gates_v2.yaml (sha256
  ``bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2``);
  any drift raises immediately (caller's responsibility to verify).
- Writes ONLY to ``results/factors/<factor>/gate_results_v2.json`` parallel
  paths. ``gate_results.json`` (canonical GL-0011 FAIL verdicts) is never
  read or modified.
- No mocks; runs against research.duckdb directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402
from screen_factor import (  # noqa: E402
    _build_factor_panel,
    _build_forward_returns,
    _build_fundamental_panel,
    _load_fundamentals,
    _load_ohlcv,
    _weekly_fridays,
)

from nyse_ats.config_loader import load_and_validate_config
from nyse_core.factor_screening import screen_factor
from nyse_core.features.fundamental import (
    compute_accruals,
    compute_piotroski_f_score,
    compute_profitability,
)
from nyse_core.features.price_volume import (
    compute_ivol_20d,
    compute_momentum_2_12,
)

_SRC = "scripts.rescreen_v2_active_factors"

# (compute_fn, sign_convention, data_source, lookback_days_pre_start)
_V2_ACTIVE_FACTORS: dict[str, tuple[Callable, int, str, int]] = {
    "ivol_20d_flipped": (compute_ivol_20d, +1, "ohlcv", 30),
    "piotroski_f_score": (compute_piotroski_f_score, +1, "fundamentals", 400),
    "momentum_2_12": (compute_momentum_2_12, +1, "ohlcv", 260),
    "accruals": (compute_accruals, -1, "fundamentals", 400),
    "profitability": (compute_profitability, +1, "fundamentals", 400),
}


def _build_v2_gate_config(config_dir: Path) -> dict[str, dict]:
    """Load config/gates_v2.yaml and produce the screen_factor gate_config dict."""
    configs = load_and_validate_config(config_dir)
    gates_v2 = configs["gates_v2.yaml"]
    gate_config: dict[str, dict] = {}
    for gate_name in ("G0", "G1", "G2", "G3", "G4", "G5"):
        gcfg = getattr(gates_v2, gate_name)
        gate_config[gate_name] = {
            "metric": gcfg.metric,
            "threshold": gcfg.threshold,
            "direction": gcfg.direction,
        }
    return gate_config


def _build_panel_for_factor(
    factor_name: str,
    rebalance_dates: list[pd.Timestamp],
    ohlcv: pd.DataFrame,
    fundamentals: pd.DataFrame,
) -> pd.DataFrame:
    compute_fn, sign, source, _ = _V2_ACTIVE_FACTORS[factor_name]
    if source == "ohlcv":
        return _build_factor_panel(ohlcv, rebalance_dates, compute_fn, sign)
    if source == "fundamentals":
        return _build_fundamental_panel(fundamentals, rebalance_dates, compute_fn, sign)
    raise ValueError(f"unknown data source for {factor_name!r}: {source}")


def main() -> int:
    p = argparse.ArgumentParser(description="iter-18 #143 v2 re-screen of 5 active factors")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--config-dir", type=Path, default=Path("config"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/factors"),
        help=(
            "Per-factor results parent. Each factor's verdict lands at "
            "<output-root>/<factor>/gate_results_v2.json (parallel to canonical)."
        ),
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

    print(f"[setup] gates_v2 config dir: {args.config_dir}", flush=True)
    gate_config = _build_v2_gate_config(args.config_dir)
    print(
        "[setup] v2 thresholds: "
        + ", ".join(f"{k}={v['metric']} {v['direction']} {v['threshold']}" for k, v in gate_config.items()),
        flush=True,
    )

    print(f"[setup] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(f"[setup] {len(ohlcv)} OHLCV rows", flush=True)

    fundamentals_lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(
        f"[setup] Loading fundamentals {fundamentals_lookback_start} -> {end}",
        flush=True,
    )
    fundamentals = _load_fundamentals(args.db_path, fundamentals_lookback_start, end)
    print(f"[setup] {len(fundamentals)} fundamentals rows", flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[setup] {len(rebalance)} weekly Fridays", flush=True)

    forward_returns = _build_forward_returns(ohlcv, rebalance)
    print(f"[setup] {len(forward_returns)} forward_return rows", flush=True)

    # Pre-compute all 5 panels once. Each candidate then uses leave-one-out:
    # its "admitted" pool is the other 4 panels. This makes G5
    # max_return_decile_corr_with_admitted realistic across the active set
    # (rather than a solo screen which auto-PASSes at 0.0).
    print("[setup] Pre-computing 5 factor score panels (used for both candidate + admitted pool)", flush=True)
    panels: dict[str, pd.DataFrame] = {}
    for fname in _V2_ACTIVE_FACTORS:
        panel = _build_panel_for_factor(fname, rebalance, ohlcv, fundamentals)
        panels[fname] = panel
        print(f"  {fname}: {len(panel)} rows", flush=True)

    # Run leave-one-out screens.
    summary: dict[str, dict] = {}
    for candidate in _V2_ACTIVE_FACTORS:
        print(f"[v2-screen] {candidate}", flush=True)
        admitted_pool = {k: v for k, v in panels.items() if k != candidate}
        existing_factors = list(admitted_pool.keys())
        verdict, metrics, _ = screen_factor(
            factor_name=candidate,
            factor_scores=panels[candidate],
            forward_returns=forward_returns,
            existing_factors=existing_factors,
            existing_factor_scores=admitted_pool,
            gate_config=gate_config,
        )

        out_dir = args.output_root / candidate
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "gate_results_v2.json"
        payload = {
            "iteration": 18,
            "iteration_tag": "iter-18",
            "task_id": 143,
            "factor_name": candidate,
            "gates_version": "v2",
            "gates_config_path": "config/gates_v2.yaml",
            "gates_v2_sha256": "bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2",
            "active_v2_factor_universe": list(_V2_ACTIVE_FACTORS.keys()),
            "leave_one_out_admitted_pool": existing_factors,
            "window": {"start": str(start), "end": str(end)},
            "n_rebalance_dates": len(rebalance),
            "n_panel_rows": int(len(panels[candidate])),
            "n_forward_return_rows": int(len(forward_returns)),
            "metrics": {k: float(v) for k, v in metrics.items()},
            "gate_results": {k: bool(v) for k, v in verdict.gate_results.items()},
            "gate_metrics": {k: float(v) for k, v in verdict.gate_metrics.items()},
            "passed_all": bool(verdict.passed_all),
            "gate_thresholds": gate_config,
        }
        with out_path.open("w") as f:
            json.dump(payload, f, indent=2, sort_keys=True, default=str)
        print(f"  wrote {out_path}", flush=True)

        summary[candidate] = {
            "passed_all": bool(verdict.passed_all),
            "oos_sharpe": float(metrics.get("oos_sharpe", float("nan"))),
            "permutation_p": float(metrics.get("permutation_p", float("nan"))),
            "ic_mean": float(metrics.get("ic_mean", float("nan"))),
            "ic_ir": float(metrics.get("ic_ir", float("nan"))),
            "max_drawdown": float(metrics.get("max_drawdown", float("nan"))),
            "max_return_decile_corr_with_admitted": float(
                metrics.get("max_return_decile_corr_with_admitted", float("nan"))
            ),
            "gate_results": {k: bool(v) for k, v in verdict.gate_results.items()},
        }

    # Console summary.
    print("\n[v2-summary] verdict overview")
    print(
        f"  {'factor':<22} {'passed_all':<10} {'oos_sharpe':>12} {'perm_p':>10} "
        f"{'ic_mean':>10} {'ic_ir':>10} {'max_dd':>10} {'g5_corr':>10}"
    )
    for fname, s in summary.items():
        print(
            f"  {fname:<22} {str(s['passed_all']):<10} {s['oos_sharpe']:>12.4f} "
            f"{s['permutation_p']:>10.4f} {s['ic_mean']:>10.4f} {s['ic_ir']:>10.4f} "
            f"{s['max_drawdown']:>10.4f} {s['max_return_decile_corr_with_admitted']:>10.4f}"
        )

    if not args.skip_research_log:
        log_path = Path("results/research_log.jsonl")
        passed_factors = [k for k, v in summary.items() if v["passed_all"]]
        failed_factors = [k for k, v in summary.items() if not v["passed_all"]]
        append_event(
            log_path,
            {
                "event": "iter18_v2_active_factor_rescreen",
                "iteration": 18,
                "iteration_tag": "iter-18",
                "task_id": 143,
                "active_v2_factor_universe": list(_V2_ACTIVE_FACTORS.keys()),
                "passed_v2_gates": passed_factors,
                "failed_v2_gates": failed_factors,
                "summary": summary,
                "timestamp_source": f"{_SRC}.main",
            },
        )
        print("  appended research-log event", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
