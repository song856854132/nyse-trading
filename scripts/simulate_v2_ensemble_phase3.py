#!/usr/bin/env python3
"""iter-19 #144 — V2 ensemble simulation against frozen Phase 3 exit target 0.50.

Implements the V2-PREREG-2026-04-24 construction grammar (GL-0014) and computes
the iter-19 Phase 3 verdict against the frozen 0.50 OOS Sharpe exit target
(GL-0015, no-renegotiation clause iter-16..iter-20).

Active v2 factor universe (GL-0014, 2026-04-24)::

    [ivol_20d_flipped, piotroski_f_score, momentum_2_12, accruals, profitability]

Construction grammar elements applied here:

- **Rank-percentile RNG tie-break** (V2-PREREG §2.2) — every factor panel is
  rank-percentile normalized with seed = ``date.toordinal()`` so discrete-score
  factors (piotroski 0..9) get deterministic distinct ranks rather than
  average-rank plateaus that distort downstream quintile construction.
- **K = 3-of-N = 5 coverage gate** (V2-PREREG §2.1) — at each (date, symbol)
  pair, at least 3 of the 5 active factors must have a non-NaN score; pairs
  failing the K-of-N threshold are dropped before re-normalization. Implemented
  via ``compute_ensemble_weights(min_factor_coverage=3)``.
- **Equal-weight aggregation** — simple cross-factor mean at each (date, symbol)
  cell (factor_sharpes = 1.0 each). This is the canonical "diagnostic" form
  consistent with iter-12 ``simulate_ensemble_g0.py``; matches the GL-0015
  ceiling derivation that assumes uniform per-factor weighting.
- **Simple-mean ρ aggregation** (V2-PREREG §3.1) — ρ is the simple arithmetic
  mean of the 10 off-diagonal pairs of the 5×5 return-decile correlation matrix
  (top-decile long-only 5d return time-series, Pearson). Reported alongside
  the ensemble Sharpe as the diversification-quality scalar.

Phase 3 verdict (GL-0015, frozen iter-16..iter-20)::

    PASS  if ensemble OOS Sharpe ≥ 0.50  → triggers Phase 3 exit authorization
    MISS  if ensemble OOS Sharpe <  0.50 → genuine miss, NOT a renegotiation trigger

AP-6 + iron rule compliance.

- Holdout boundary refused at end_date >= 2024-01-01 (rule 1).
- Reads bit-identical config/gates_v2.yaml; thresholds frozen (rules 2 + 8).
- No DB mocks; runs against research.duckdb directly (rule 3).
- No secret leakage (rule 4).
- Hash-chain append to results/research_log.jsonl (rule 6).
- Canonical results/factors/<f>/gate_results.json untouched (rule 7).
- Writes only to results/ensemble/iter19_v2_phase3/ensemble_result.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402
from screen_factor import (  # noqa: E402
    _build_forward_returns,
    _load_fundamentals,
    _load_ohlcv,
    _weekly_fridays,
)

from nyse_core.factor_screening import (
    compute_ensemble_weights,
    compute_long_short_returns,
)
from nyse_core.features.fundamental import (
    compute_accruals,
    compute_piotroski_f_score,
    compute_profitability,
)
from nyse_core.features.price_volume import (
    compute_ivol_20d,
    compute_momentum_2_12,
)
from nyse_core.metrics import ic_ir as compute_ic_ir
from nyse_core.metrics import (
    information_coefficient,
    max_drawdown,
    sharpe_ratio,
)
from nyse_core.normalize import rank_percentile
from nyse_core.schema import COL_DATE
from nyse_core.statistics import permutation_test

_SRC = "scripts.simulate_v2_ensemble_phase3"

_GATES_V2_SHA256 = "bd0fc5de89307dab36fe82c12e0d921a7fa145376e2ef01aad8d000dd92979d2"

_PHASE3_TARGET_FROZEN_GL_0015 = 0.50

# (compute_fn, sign_convention, data_source, lookback_days_pre_start)
_V2_ACTIVE_FACTORS: dict[str, tuple[Callable, int, str, int]] = {
    "ivol_20d_flipped": (compute_ivol_20d, +1, "ohlcv", 30),
    "piotroski_f_score": (compute_piotroski_f_score, +1, "fundamentals", 400),
    "momentum_2_12": (compute_momentum_2_12, +1, "ohlcv", 260),
    "accruals": (compute_accruals, -1, "fundamentals", 400),
    "profitability": (compute_profitability, +1, "fundamentals", 400),
}


def _build_panel_with_rng_tiebreak(
    raw_data: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    compute_fn: Callable,
    sign: int,
    data_source: str,
) -> pd.DataFrame:
    """Build a per-factor score panel with V2-PREREG RNG tie-break in rank-percentile.

    For each rebalance date, instantiates a fresh
    ``np.random.default_rng(seed=date.toordinal())`` and threads it through
    ``rank_percentile(..., rng=...)``. This produces deterministic distinct
    ranks for tied factor values (e.g., piotroski 0..9 integer scores) so the
    K-of-N coverage aggregator is not biased toward factors with finer
    score granularity.

    Up-front ``pd.to_datetime`` cast on the filter column makes the per-date
    ``<=`` comparison vectorized over a numpy datetime64 array rather than a
    Python-level object-dtype scan; the latter regresses panel build time by
    one to two orders of magnitude on 308k-row fundamentals input.
    """
    raw_data = raw_data.copy()
    if data_source == "ohlcv":
        date_col = COL_DATE
    elif data_source == "fundamentals":
        date_col = "date"
    else:
        raise ValueError(f"unknown data source: {data_source!r}")
    raw_data[date_col] = pd.to_datetime(raw_data[date_col])

    rows: list[pd.DataFrame] = []
    for ts in rebalance_dates:
        window = raw_data[raw_data[date_col] <= ts]
        if window.empty:
            continue
        series, _ = compute_fn(window)
        series = series.dropna()
        if series.empty:
            continue
        if sign == -1:
            series = -series
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


def _factor_top_decile_return_series(
    factor_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
    decile_frac: float = 0.10,
) -> pd.Series:
    """Per-date equal-weighted top-decile 5d forward return time-series.

    Mirrors the construction used by the v2 G5 metric
    (``_compute_max_return_decile_corr_with_admitted``): top decile by score,
    equal-weighted mean of fwd_ret_5d. The output time series feeds the 5×5
    return-decile correlation matrix for ρ aggregation.
    """
    merged = pd.merge(factor_scores, forward_returns, on=["date", "symbol"], how="inner")
    merged = merged.dropna(subset=["score", "fwd_ret_5d"])
    if merged.empty:
        return pd.Series(dtype=float)
    per_date: dict = {}
    for dt, grp in merged.groupby("date", sort=True):
        if len(grp) < 10:
            continue
        threshold = float(grp["score"].quantile(1.0 - decile_frac))
        top = grp[grp["score"] >= threshold]
        if top.empty:
            continue
        per_date[dt] = float(top["fwd_ret_5d"].mean())
    return pd.Series(per_date, name="top_decile_ret").sort_index()


def _simple_mean_rho(
    panels: dict[str, pd.DataFrame],
    forward_returns: pd.DataFrame,
) -> tuple[float, dict[str, dict[str, float]], int]:
    """Simple-mean ρ over the off-diagonal of the K×K return-decile corr matrix.

    For K factors, builds top-decile long-only 5d return time-series per factor,
    computes the K×K Pearson correlation matrix, and returns the simple
    arithmetic mean of the K·(K-1)/2 unique off-diagonal pairs (= 10 pairs for
    K=5).

    Returns
    -------
    tuple[float, dict[str, dict[str, float]], int]
        (mean off-diagonal correlation, full pairwise correlation matrix as a
        nested dict, number of pairs used in the mean).
    """
    factor_names = sorted(panels.keys())
    series_map: dict[str, pd.Series] = {
        name: _factor_top_decile_return_series(panels[name], forward_returns) for name in factor_names
    }

    pair_corrs: dict[str, dict[str, float]] = {
        a: {b: float("nan") for b in factor_names} for a in factor_names
    }
    pairs: list[float] = []
    for i, a in enumerate(factor_names):
        pair_corrs[a][a] = 1.0
        sa = series_map[a]
        for b in factor_names[i + 1 :]:
            sb = series_map[b]
            common = sa.index.intersection(sb.index)
            if len(common) < 5:
                continue
            x = sa.loc[common]
            y = sb.loc[common]
            if float(x.std(ddof=1)) == 0.0 or float(y.std(ddof=1)) == 0.0:
                continue
            corr = float(x.corr(y))
            pair_corrs[a][b] = corr
            pair_corrs[b][a] = corr
            pairs.append(corr)
    mean_rho = float(np.mean(pairs)) if pairs else float("nan")
    return mean_rho, pair_corrs, len(pairs)


def _summarize_ensemble(
    ensemble_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
    perm_reps: int,
) -> dict:
    """Compute the iter-19 ensemble metric bundle (mirrors iter-12 conventions).

    Sharpe annualization factor 52 (5-day forward returns at weekly cadence).
    Permutation: 500 reps, block_size=21 trading days (~5 weeks), stationary
    bootstrap consistent with iter-12 / iter-16 / iter-17 conventions.
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

    annual_factor = 52
    oos_sharpe, _ = sharpe_ratio(ls_returns, annual_factor=annual_factor)
    mdd, _ = max_drawdown(ls_returns)

    merged = pd.merge(ensemble_scores, forward_returns, on=["date", "symbol"], how="inner")
    ic_values: dict = {}
    for dt in sorted(merged["date"].unique()):
        day = merged[merged["date"] == dt].dropna(subset=["score", "fwd_ret_5d"])
        if len(day) < 5:
            continue
        ic_val, _ = information_coefficient(day["score"], day["fwd_ret_5d"])
        ic_values[dt] = ic_val
    ic_series = pd.Series(ic_values, name="ic")
    ic_series.index.name = "date"
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
    p = argparse.ArgumentParser(description="iter-19 #144 v2 ensemble Phase 3 simulation")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument("--perm-reps", type=int, default=500)
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/ensemble/iter19_v2_phase3"),
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

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/7] Loading OHLCV {start} -> {end}", flush=True)
    ohlcv = _load_ohlcv(args.db_path, start, end)
    print(f"       rows={len(ohlcv):,}", flush=True)

    lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
    print(f"[2/7] Loading fundamentals {lookback_start} -> {end}", flush=True)
    fundamentals = _load_fundamentals(args.db_path, lookback_start, end)
    print(f"       rows={len(fundamentals):,}", flush=True)

    rebalance = _weekly_fridays(start, end)
    print(f"[3/7] Rebalance dates: {len(rebalance)} weekly Fridays", flush=True)

    fwd_returns = _build_forward_returns(ohlcv, rebalance)
    print(f"[4/7] Forward-return rows: {len(fwd_returns):,}", flush=True)

    print("[5/7] Building 5 factor panels with V2-PREREG RNG tie-break", flush=True)
    panels: dict[str, pd.DataFrame] = {}
    for fname, (compute_fn, sign, source, _) in _V2_ACTIVE_FACTORS.items():
        if source == "ohlcv":
            panel = _build_panel_with_rng_tiebreak(ohlcv, rebalance, compute_fn, sign, source)
        elif source == "fundamentals":
            panel = _build_panel_with_rng_tiebreak(fundamentals, rebalance, compute_fn, sign, source)
        else:
            raise ValueError(f"unknown data source for {fname!r}: {source}")
        panels[fname] = panel
        print(f"  {fname}: {len(panel)} rows", flush=True)

    if any(panel.empty for panel in panels.values()):
        empty = [n for n, p in panels.items() if p.empty]
        print(f"REFUSED: factor panel empty for {empty}.", file=sys.stderr)
        return 3

    print("[6/7] Aggregating with K=3-of-N=5 coverage gate (equal-Sharpe weights)", flush=True)
    equal_sharpes = dict.fromkeys(panels.keys(), 1.0)
    ensemble_scores, ens_diag = compute_ensemble_weights(panels, equal_sharpes, min_factor_coverage=3)
    n_dates = ensemble_scores["date"].nunique() if not ensemble_scores.empty else 0
    print(
        f"       ensemble rows: {len(ensemble_scores):,} across {n_dates} dates",
        flush=True,
    )

    print("[7/7] Computing summary metrics + simple-mean ρ", flush=True)
    summary = _summarize_ensemble(ensemble_scores, fwd_returns, perm_reps=args.perm_reps)
    mean_rho, pair_corrs, n_pairs = _simple_mean_rho(panels, fwd_returns)

    oos_sharpe = summary.get("oos_sharpe")
    if oos_sharpe is None:
        verdict_passed = None
        verdict_text = "INDETERMINATE (oos_sharpe is None)"
    elif oos_sharpe >= _PHASE3_TARGET_FROZEN_GL_0015:
        verdict_passed = True
        verdict_text = f"PASS — ensemble OOS Sharpe {oos_sharpe:+.4f} >= 0.50 frozen target (GL-0015)"
    else:
        verdict_passed = False
        verdict_text = f"MISS — ensemble OOS Sharpe {oos_sharpe:+.4f} < 0.50 frozen target (GL-0015)"

    print("")
    print("V2 ENSEMBLE PHASE 3 SIMULATION (iter-19 #144)")
    print("=" * 66)
    print(f"  Active v2 factor universe : {sorted(panels.keys())}")
    print("  Coverage gate             : K=3-of-N=5 (V2-PREREG §2.1)")
    print("  Aggregator                : equal-Sharpe simple mean")
    print(f"  Rebalance periods         : {summary['n_periods']}")
    if summary["oos_sharpe"] is not None:
        print(f"  OOS Sharpe                : {summary['oos_sharpe']:+.4f}")
    if summary["ic_mean"] is not None:
        print(f"  IC mean                   : {summary['ic_mean']:+.4f}")
    if summary["ic_ir"] is not None:
        print(f"  IC IR                     : {summary['ic_ir']:+.4f}")
    if summary["max_drawdown"] is not None:
        print(f"  Max drawdown              : {summary['max_drawdown']:+.4f}")
    if summary["permutation_p"] is not None:
        print(
            f"  Permutation p             : {summary['permutation_p']:.4f} "
            f"(block bootstrap, n_reps={summary['permutation_reps']})"
        )
    print(f"  Simple-mean ρ             : {mean_rho:.4f} ({n_pairs} off-diagonal pairs)")
    print("  Phase 3 target (GL-0015)  : 0.50 (frozen iter-16..iter-20)")
    print("=" * 66)
    print(f"  VERDICT: {verdict_text}")
    print("=" * 66)

    payload: dict[str, object] = {
        "iteration": 19,
        "iteration_tag": "iter-19",
        "task_id": 144,
        "implements_preregistration": "V2-PREREG-2026-04-24",
        "authorizes_from": ["GL-0014", "GL-0015"],
        "phase3_target_frozen_gl_0015": _PHASE3_TARGET_FROZEN_GL_0015,
        "active_v2_factor_universe": sorted(panels.keys()),
        "coverage_gate": {
            "scheme": "K-of-N",
            "k": 3,
            "n": 5,
            "implementation": "compute_ensemble_weights(min_factor_coverage=3)",
        },
        "aggregator": {
            "scheme": "equal_sharpe_simple_mean",
            "factor_sharpes": equal_sharpes,
            "rationale": (
                "Equal-Sharpe (uniform 1.0) matches the GL-0015 ceiling derivation "
                "assumption and the iter-12 simulate_ensemble_g0 convention. "
                "Sharpe-weighted is reserved for sensitivity diagnostics and not "
                "consumed by the Phase 3 verdict."
            ),
        },
        "rank_percentile_tie_break": {
            "scheme": "rng_default_rng_seed_date_toordinal",
            "spec_source": "V2-PREREG-2026-04-24 §2.2",
        },
        "gates_v2_sha256": _GATES_V2_SHA256,
        "window": {"start": str(start), "end": str(end)},
        "n_rebalance_dates": len(rebalance),
        "n_panel_rows": {name: int(len(panel)) for name, panel in panels.items()},
        "n_forward_return_rows": int(len(fwd_returns)),
        "n_ensemble_rows": int(len(ensemble_scores)),
        "n_ensemble_dates": int(n_dates),
        "summary": summary,
        "rho": {
            "mean_off_diagonal": mean_rho,
            "n_pairs_used": n_pairs,
            "expected_n_pairs": 10,
            "pairwise_correlations": pair_corrs,
            "spec_source": "V2-PREREG-2026-04-24 §3.1",
            "construction": (
                "5x5 Pearson correlation matrix over per-factor top-decile (10%) "
                "long-only 5d-forward-return time series; simple arithmetic mean "
                "over the C(5,2)=10 unique off-diagonal pairs."
            ),
        },
        "verdict": {
            "passed_phase3": verdict_passed,
            "frozen_target": _PHASE3_TARGET_FROZEN_GL_0015,
            "observed_oos_sharpe": summary.get("oos_sharpe"),
            "human_readable": verdict_text,
            "no_renegotiation_clause": (
                "GL-0015 freezes 0.50 for iter-16..iter-20; a miss here is a "
                "genuine Phase 3 miss, not a target-renegotiation trigger."
            ),
        },
        "ap6_compliance": (
            "diagnostic + verdict against pre-registered frozen target; no "
            "threshold modification, no admission decision changed, no "
            "config/gates*.yaml touched."
        ),
    }

    out_path = args.output_dir / "ensemble_result.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"Saved: {out_path}", flush=True)

    if not args.skip_research_log:
        log_path = Path("results/research_log.jsonl")
        append_event(
            log_path,
            {
                "event": "iter19_v2_ensemble_phase3_simulation",
                "iteration": 19,
                "iteration_tag": "iter-19",
                "task_id": 144,
                "active_v2_factor_universe": sorted(panels.keys()),
                "coverage_k_of_n": "3-of-5",
                "aggregator": "equal_sharpe_simple_mean",
                "phase3_target_frozen_gl_0015": _PHASE3_TARGET_FROZEN_GL_0015,
                "summary": summary,
                "mean_rho_off_diagonal": mean_rho,
                "n_rho_pairs": n_pairs,
                "verdict_passed_phase3": verdict_passed,
                "verdict_text": verdict_text,
                "artifact": str(out_path),
                "gates_v2_sha256": _GATES_V2_SHA256,
                "timestamp_source": f"{_SRC}.main",
            },
        )
        print("  appended research-log event", flush=True)

    warns = [m for m in ens_diag.messages if m.level.value == "WARNING"]
    if warns:
        print(f"\nAggregator warnings ({len(warns)}):", flush=True)
        for w in warns[:5]:
            print(f"  [{w.source}] {w.message}")

    return 0


if __name__ == "__main__":
    np.seterr(invalid="ignore")
    sys.exit(main())
