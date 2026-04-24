#!/usr/bin/env python3
"""iter-14 diagnostic battery (Wave D, 5-stream, AP-6-safe observational).

Implements the charter at ``docs/audit/wave_d_diagnostic_charter.md`` §2 as a
single orchestrator with five pure, idempotent stream functions. Every stream
is **observational** under the in-force gate family: no threshold, metric
definition, direction, or admission decision changes. No
``results/factors/<factor>/gate_results.json`` is modified. No
``src/nyse_core/features/registry.py`` sign convention is amended.

Streams
-------
1. Per-factor near-miss table — derived from existing gate-results JSON only;
   no new metrics.
2. Coverage matrix (date × factor) — count / percentage of non-NaN rank-
   percentile scores per (date, factor); pairwise Jaccard overlap of per-date
   coverage between factors.
3. Pairwise factor score & return correlations — cross-sectional Spearman of
   factor scores (time-averaged) plus pairwise top-decile forward-return
   correlations.
4. One-factor sector residual on ``momentum_2_12`` ONLY — cross-sectional
   residual against GICS sector dummies per rebalance date; re-screen with the
   in-force gate family.
5. Sign-flip sanity check on ``ivol_20d`` and ``high_52w`` — re-compute all six
   in-force gate metrics with the score sign inverted; registry.py sign is
   unchanged.

AP-6 safety: this orchestrator ``import``s ``screen_factor`` from
``nyse_core.factor_screening`` which writes no files. All outputs land under
``results/diagnostics/iter14_*/`` — a directory that did not exist prior to
iter-14 and is disjoint from ``results/factors/*/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_research_log import append_event  # noqa: E402

# Re-use the iter-12 orchestrator's data-loading helpers so iter-14 operates on
# bit-identical inputs (same OHLCV slice, same fundamentals slice, same weekly
# rebalance schedule, same rank-percentile panel construction).
from simulate_ensemble_g0 import (  # noqa: E402
    _compute_forward_returns,
    _load_fundamentals,
    _load_ohlcv,
    _weekly_fridays,
    build_factor_score_panels,
)

from nyse_core.factor_screening import screen_factor
from nyse_core.features import FactorRegistry, register_all_factors
from nyse_core.sector_map_loader import load_gics_sectors

_SRC = "scripts.run_iter14_diagnostic_battery"


# In-force gate thresholds (pinned from config/gates.yaml sha256
# 521b7571c330a5a1e87642eb9e5c0869ae8dc23cba3a1a175baf21a42f559af4). Duplicated
# as a constant here so Stream 1 can emit explicit gap-to-threshold numbers
# without relying on a runtime config read; the config file itself is the
# source of truth and is not modified.
_IN_FORCE_THRESHOLDS: dict[str, tuple[float, str]] = {
    "G0_oos_sharpe": (0.30, ">="),
    "G1_permutation_p": (0.05, "<"),
    "G2_ic_mean": (0.02, ">="),
    "G3_ic_ir": (0.50, ">="),
    "G4_max_drawdown": (-0.30, ">="),
    "G5_marginal_contribution": (0.00, ">"),
}

_GATE_METRIC_KEYS: dict[str, str] = {
    "G0_oos_sharpe": "G0_value",
    "G1_permutation_p": "G1_value",
    "G2_ic_mean": "G2_value",
    "G3_ic_ir": "G3_value",
    "G4_max_drawdown": "G4_value",
    "G5_marginal_contribution": "G5_value",
}


# ─── Stream 1 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NearMissRow:
    factor: str
    gate: str
    metric_value: float
    threshold: float
    direction: str
    gap: float
    passes: bool
    near_miss_tag: str


def _near_miss_tag(gate: str, gap: float, passes: bool) -> str:
    """Categorize a gate outcome by magnitude of the gap from threshold."""
    if passes:
        return "pass"
    g = abs(gap)
    if gate == "G2_ic_mean" and g <= 0.0050:
        return "near_miss_within_50bps_ic"
    if gate == "G3_ic_ir" and g <= 0.25:
        return "near_miss_within_025_icir"
    if gate == "G0_oos_sharpe" and g <= 0.15:
        return "near_miss_within_015_sharpe"
    if gate == "G4_max_drawdown" and g <= 0.10:
        return "near_miss_within_10pct_mdd"
    return "fail"


def compute_per_factor_near_miss(
    gate_results_by_factor: dict[str, dict],
) -> list[NearMissRow]:
    """Stream 1: decompose each factor's gate outcomes into gap-to-threshold rows.

    For each (factor, gate) pair, extract the measured metric value from the
    existing ``gate_results.json`` payload, compute the signed gap from the
    in-force threshold, and categorize into a near-miss bucket. No gate
    threshold is changed; this is a pure presentation of existing evidence.
    """
    rows: list[NearMissRow] = []
    for factor_name in sorted(gate_results_by_factor.keys()):
        payload = gate_results_by_factor[factor_name]
        metrics = payload.get("gate_metrics", {})
        for gate, (threshold, direction) in _IN_FORCE_THRESHOLDS.items():
            metric_key = _GATE_METRIC_KEYS[gate]
            val = metrics.get(metric_key)
            if val is None:
                continue
            val = float(val)
            if direction == ">=":
                passes = val >= threshold
                gap = val - threshold
            elif direction == ">":
                passes = val > threshold
                gap = val - threshold
            elif direction == "<":
                passes = val < threshold
                gap = threshold - val
            else:
                raise ValueError(f"Unknown direction {direction!r} for gate {gate}")
            rows.append(
                NearMissRow(
                    factor=factor_name,
                    gate=gate,
                    metric_value=val,
                    threshold=threshold,
                    direction=direction,
                    gap=gap,
                    passes=passes,
                    near_miss_tag=_near_miss_tag(gate, gap, passes),
                )
            )
    return rows


# ─── Stream 2 ────────────────────────────────────────────────────────────────


def compute_coverage_matrix(
    panels: dict[str, pd.DataFrame],
    rebalance_dates: list[pd.Timestamp],
    universe_size_by_date: dict[pd.Timestamp, int],
) -> pd.DataFrame:
    """Stream 2 core: per-(date, factor) coverage count + percentage.

    Returns a long-format DataFrame with columns
    ``[date, factor, n_covered, universe_size, coverage_pct]``. ``n_covered``
    is the number of non-NaN rank-percentile scores produced by the factor on
    that rebalance date; ``universe_size`` is the number of symbols with at
    least one OHLCV row visible by that date (caller owns the definition);
    ``coverage_pct`` is ``n_covered / universe_size`` clipped to [0, 1].
    """
    rows: list[dict] = []
    date_set = {pd.Timestamp(d).normalize() for d in rebalance_dates}
    for factor_name in sorted(panels.keys()):
        panel = panels[factor_name]
        if panel.empty:
            continue
        by_date = panel.groupby("date")["symbol"].nunique()
        for date_key, n_covered in by_date.items():
            ts = pd.Timestamp(date_key).normalize()
            if ts not in date_set:
                continue
            universe_size = universe_size_by_date.get(ts, 0)
            coverage_pct = float(n_covered) / universe_size if universe_size > 0 else 0.0
            coverage_pct = min(max(coverage_pct, 0.0), 1.0)
            rows.append(
                {
                    "date": ts.date().isoformat(),
                    "factor": factor_name,
                    "n_covered": int(n_covered),
                    "universe_size": int(universe_size),
                    "coverage_pct": round(coverage_pct, 6),
                }
            )
    return pd.DataFrame(rows, columns=["date", "factor", "n_covered", "universe_size", "coverage_pct"])


def compute_pairwise_jaccard(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pair-wise Jaccard overlap of per-date covered-symbol sets, averaged over dates.

    Returns an N×N symmetric DataFrame indexed by factor name. Cell (i, j) is
    the mean over all rebalance dates where **both** factors observed at least
    one symbol of ``|A ∩ B| / |A ∪ B|`` where A / B are the covered-symbol
    sets on that date.
    """
    factors = sorted(panels.keys())
    n = len(factors)
    jaccard = np.full((n, n), np.nan, dtype=float)

    per_factor_date_sets: dict[str, dict[pd.Timestamp, set]] = {}
    for f in factors:
        panel = panels[f]
        if panel.empty:
            per_factor_date_sets[f] = {}
            continue
        d_grp: dict[pd.Timestamp, set] = {}
        for date_key, group in panel.groupby("date"):
            d_grp[pd.Timestamp(date_key).normalize()] = set(group["symbol"].unique())
        per_factor_date_sets[f] = d_grp

    for i, a in enumerate(factors):
        for j, b in enumerate(factors):
            if i == j:
                jaccard[i, j] = 1.0
                continue
            a_map = per_factor_date_sets[a]
            b_map = per_factor_date_sets[b]
            shared = set(a_map.keys()) & set(b_map.keys())
            if not shared:
                continue
            vals: list[float] = []
            for d_key in shared:
                inter = len(a_map[d_key] & b_map[d_key])
                union = len(a_map[d_key] | b_map[d_key])
                if union == 0:
                    continue
                vals.append(inter / union)
            jaccard[i, j] = float(np.mean(vals)) if vals else float("nan")

    return pd.DataFrame(jaccard, index=factors, columns=factors)


# ─── Stream 3 ────────────────────────────────────────────────────────────────


def compute_pairwise_score_correlation(
    panels: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Stream 3a: time-averaged cross-sectional Spearman correlation of factor scores.

    Per rebalance date, pivot the merged panels to a (symbol × factor) matrix
    and compute a Spearman correlation at that date. Return the mean of those
    date-level matrices across dates where both factors have >=10 overlapping
    symbols.
    """
    factors = sorted(panels.keys())
    if not factors:
        return pd.DataFrame(dtype=float)

    per_date_frames: dict[pd.Timestamp, pd.DataFrame] = {}
    for f in factors:
        panel = panels[f]
        if panel.empty:
            continue
        for date_key, group in panel.groupby("date"):
            ts = pd.Timestamp(date_key).normalize()
            frame = per_date_frames.setdefault(ts, pd.DataFrame())
            series = group.set_index("symbol")["score"].rename(f)
            per_date_frames[ts] = frame.join(series, how="outer") if not frame.empty else series.to_frame()

    accum = np.zeros((len(factors), len(factors)), dtype=float)
    counts = np.zeros((len(factors), len(factors)), dtype=int)
    idx = {f: i for i, f in enumerate(factors)}

    for _ts, frame in per_date_frames.items():
        if frame.empty:
            continue
        present = [c for c in factors if c in frame.columns]
        if len(present) < 2:
            continue
        sub = frame[present].dropna(how="all")
        if len(sub) < 10:
            continue
        corr = sub.corr(method="spearman", min_periods=10)
        for a in present:
            for b in present:
                val = corr.at[a, b] if (a in corr.index and b in corr.columns) else np.nan
                if pd.isna(val):
                    continue
                accum[idx[a], idx[b]] += float(val)
                counts[idx[a], idx[b]] += 1

    out = np.full((len(factors), len(factors)), np.nan, dtype=float)
    nz = counts > 0
    out[nz] = accum[nz] / counts[nz]
    return pd.DataFrame(out, index=factors, columns=factors)


def compute_top_decile_return_series(
    panel: pd.DataFrame,
    forward_returns: pd.DataFrame,
    quantile: float = 0.9,
) -> pd.Series:
    """Return a per-date equal-weight forward-return series for the top-quantile long leg."""
    if panel.empty or forward_returns.empty:
        return pd.Series(dtype=float, name="fwd_ret_top_decile")
    merged = pd.merge(panel, forward_returns, on=["date", "symbol"], how="inner")
    out: dict = {}
    for dt, group in merged.groupby("date"):
        scored = group.dropna(subset=["score", "fwd_ret_5d"])
        if len(scored) < 10:
            continue
        cutoff = scored["score"].quantile(quantile)
        top = scored[scored["score"] >= cutoff]
        if top.empty:
            continue
        out[pd.Timestamp(dt).normalize()] = float(top["fwd_ret_5d"].mean())
    return pd.Series(out, name="fwd_ret_top_decile").sort_index()


def compute_pairwise_return_correlation(
    panels: dict[str, pd.DataFrame],
    forward_returns: pd.DataFrame,
) -> pd.DataFrame:
    """Stream 3b: pairwise Pearson correlation of top-decile long-leg forward returns."""
    factors = sorted(panels.keys())
    if not factors:
        return pd.DataFrame(dtype=float)
    per_factor_ret: dict[str, pd.Series] = {}
    for f in factors:
        per_factor_ret[f] = compute_top_decile_return_series(panels[f], forward_returns)

    df = pd.DataFrame(per_factor_ret).dropna(how="all")
    if df.empty or df.shape[1] < 2:
        return pd.DataFrame(np.nan, index=factors, columns=factors)
    corr = df.corr(method="pearson", min_periods=10)
    # Ensure row/col order matches the factor list exactly (fill missing with NaN).
    corr = corr.reindex(index=factors, columns=factors)
    return corr


# ─── Stream 4 ────────────────────────────────────────────────────────────────


def sector_residualize_panel(
    panel: pd.DataFrame,
    sector_map: pd.Series,
) -> tuple[pd.DataFrame, dict]:
    """Per rebalance date, compute the residual of ``score`` against sector dummies.

    The return shape matches the input panel (``[date, symbol, score]``) with
    the score column replaced by the per-date OLS residual against a
    one-hot-encoded GICS sector indicator matrix (without an intercept, since
    the dummies span the column space; demean within sectors is equivalent).
    Symbols without a sector mapping are dropped.

    Returns (residualized_panel, diag_dict) where diag_dict captures per-date
    n_observations and n_sectors for sanity.
    """
    if panel.empty:
        return panel.copy(), {
            "dates_processed": 0,
            "rows_in": 0,
            "rows_out": 0,
            "symbols_dropped_no_sector": 0,
        }

    mapped_symbols = set(sector_map.index.astype(str))
    in_map = panel[panel["symbol"].astype(str).isin(mapped_symbols)].copy()
    rows_dropped = len(panel) - len(in_map)

    rows_out: list[pd.DataFrame] = []
    dates_processed = 0
    for date_key, group in in_map.groupby("date"):
        if len(group) < 5:
            continue
        sectors = group["symbol"].map(sector_map).astype(str)
        # One-hot encode sectors; use drop_first=False and no intercept — within-
        # sector demean is what residualization achieves.
        dummies = pd.get_dummies(sectors, prefix="gics").astype(float)
        if dummies.shape[1] == 0:
            continue
        X = dummies.to_numpy()
        y = group["score"].to_numpy(dtype=float)
        # Normal equation: beta = (X^T X)^{-1} X^T y with pinv for rank safety.
        try:
            beta = np.linalg.pinv(X.T @ X) @ (X.T @ y)
        except np.linalg.LinAlgError:
            continue
        residual = y - X @ beta
        rows_out.append(
            pd.DataFrame(
                {
                    "date": date_key,
                    "symbol": group["symbol"].values,
                    "score": residual,
                }
            )
        )
        dates_processed += 1

    out = (
        pd.concat(rows_out, ignore_index=True)
        if rows_out
        else pd.DataFrame(columns=["date", "symbol", "score"])
    )
    diag = {
        "dates_processed": dates_processed,
        "rows_in": int(len(panel)),
        "rows_out": int(len(out)),
        "symbols_dropped_no_sector": int(rows_dropped),
    }
    return out, diag


def run_sector_residual_screen(
    factor_name: str,
    panel: pd.DataFrame,
    forward_returns: pd.DataFrame,
    sector_map: pd.Series,
) -> dict:
    """Stream 4: residualize ``factor_name`` vs sector dummies then screen under in-force family.

    Returns a dict with the six in-force gate metrics plus diagnostics. Does
    not write to ``results/factors/<factor>/gate_results.json``; output lands
    only in the Stream 4 artefact.
    """
    residualized, resid_diag = sector_residualize_panel(panel, sector_map)
    if residualized.empty:
        return {
            "factor": factor_name,
            "residualization_diag": resid_diag,
            "metrics": {},
            "note": "residualization produced empty panel; screen skipped",
        }

    # Re-rank-percentile the residuals so the screen is on the same [0, 1] scale
    # as the in-force family expects for scores.
    from nyse_core.normalize import rank_percentile

    reranked_rows: list[pd.DataFrame] = []
    for date_key, group in residualized.groupby("date"):
        ranked, _ = rank_percentile(group.set_index("symbol")["score"])
        reranked_rows.append(pd.DataFrame({"date": date_key, "symbol": ranked.index, "score": ranked.values}))
    reranked = pd.concat(reranked_rows, ignore_index=True) if reranked_rows else residualized

    verdict, metrics, _ = screen_factor(
        factor_name=f"{factor_name}_sector_residualized",
        factor_scores=reranked,
        forward_returns=forward_returns,
        existing_factors=None,
        existing_factor_scores=None,
        gate_config=None,
    )
    return {
        "factor": factor_name,
        "variant": "sector_residualized",
        "residualization_diag": resid_diag,
        "metrics": {
            k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
            for k, v in metrics.items()
            if k != "factor_name"
        },
        "verdict_passed_all": bool(verdict.passed_all),
    }


# ─── Stream 5 ────────────────────────────────────────────────────────────────


def sign_flip_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Invert the score sign and re-rank-percentile per date.

    Because scores enter the panel already rank-percentile [0,1], sign-flipping
    means mapping ``p → 1 - p`` per (date, symbol). This is *not* a registry
    amendment; it is an observational re-computation of gate metrics as they
    would appear under the inverted convention.
    """
    if panel.empty:
        return panel.copy()
    out = panel.copy()
    out["score"] = 1.0 - out["score"].astype(float)
    return out


def run_sign_flip_screen(
    factor_name: str,
    panel: pd.DataFrame,
    forward_returns: pd.DataFrame,
) -> dict:
    """Stream 5: re-compute in-force gate metrics with the factor's sign inverted."""
    flipped = sign_flip_panel(panel)
    if flipped.empty:
        return {
            "factor": factor_name,
            "variant": "sign_flipped",
            "metrics": {},
            "note": "empty panel; screen skipped",
        }
    verdict, metrics, _ = screen_factor(
        factor_name=f"{factor_name}_sign_flipped",
        factor_scores=flipped,
        forward_returns=forward_returns,
        existing_factors=None,
        existing_factor_scores=None,
        gate_config=None,
    )
    return {
        "factor": factor_name,
        "variant": "sign_flipped",
        "metrics": {
            k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
            for k, v in metrics.items()
            if k != "factor_name"
        },
        "verdict_passed_all": bool(verdict.passed_all),
    }


# ─── Orchestration ───────────────────────────────────────────────────────────


def _load_gate_results_jsons(factors_dir: Path) -> dict[str, dict]:
    """Read every ``results/factors/<factor>/gate_results.json`` into a dict."""
    out: dict[str, dict] = {}
    if not factors_dir.exists():
        return out
    for sub in sorted(factors_dir.iterdir()):
        if not sub.is_dir():
            continue
        path = sub / "gate_results.json"
        if not path.exists():
            continue
        with path.open() as f:
            out[sub.name] = json.load(f)
    return out


def _universe_size_by_date(
    ohlcv: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
) -> dict[pd.Timestamp, int]:
    """Per rebalance date, count distinct symbols with at least one OHLCV row at/before that date."""
    ts_sorted = ohlcv.sort_values("date")
    out: dict[pd.Timestamp, int] = {}
    for ts in rebalance_dates:
        visible = ts_sorted[ts_sorted["date"] <= ts]
        out[pd.Timestamp(ts).normalize()] = int(visible["symbol"].nunique())
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="iter-14 diagnostic battery (AP-6-safe)")
    p.add_argument("--db-path", type=Path, default=Path("research.duckdb"))
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2023-12-31")
    p.add_argument(
        "--sector-csv",
        type=Path,
        default=Path("config/gics_sectors_sp500.csv"),
    )
    p.add_argument(
        "--factors-dir",
        type=Path,
        default=Path("results/factors"),
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/diagnostics"),
    )
    p.add_argument(
        "--streams",
        default="1,2,3,4,5",
        help="comma-separated stream ids to run",
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

    streams_to_run = {int(x.strip()) for x in args.streams.split(",") if x.strip()}
    if not streams_to_run.issubset({1, 2, 3, 4, 5}):
        print(f"REFUSED: --streams must be subset of 1,2,3,4,5; got {args.streams}", file=sys.stderr)
        return 2

    args.output_root.mkdir(parents=True, exist_ok=True)

    # ─── Stream 1 (no DuckDB access needed) ──────────────────────────────
    stream1_result: dict | None = None
    if 1 in streams_to_run:
        print("[Stream 1] Per-factor near-miss table (docs-derivable)", flush=True)
        gate_results_by_factor = _load_gate_results_jsons(args.factors_dir)
        near_miss_rows = compute_per_factor_near_miss(gate_results_by_factor)
        stream1_dir = args.output_root / "iter14_near_miss"
        stream1_dir.mkdir(parents=True, exist_ok=True)
        stream1_result = {
            "stream": 1,
            "n_factors": len(gate_results_by_factor),
            "n_rows": len(near_miss_rows),
            "rows": [asdict(r) for r in near_miss_rows],
            "thresholds": {
                k: {"threshold": v[0], "direction": v[1]} for k, v in _IN_FORCE_THRESHOLDS.items()
            },
        }
        with (stream1_dir / "per_factor_near_miss.json").open("w") as f:
            json.dump(stream1_result, f, indent=2, sort_keys=True)
        print(f"  wrote {stream1_dir}/per_factor_near_miss.json ({len(near_miss_rows)} rows)", flush=True)

    # ─── Streams 2-5 need factor score panels ─────────────────────────────
    panels: dict[str, pd.DataFrame] = {}
    forward_returns = pd.DataFrame()
    rebalance: list[pd.Timestamp] = []
    universe_sizes: dict[pd.Timestamp, int] = {}
    sector_map = pd.Series(dtype=str)

    needs_panels = bool(streams_to_run & {2, 3, 4, 5})
    if needs_panels:
        print(f"[setup] Loading OHLCV {start} → {end}", flush=True)
        ohlcv = _load_ohlcv(args.db_path, start, end)
        lookback_start = start - pd.Timedelta(days=400).to_pytimedelta()
        print(f"[setup] Loading fundamentals {lookback_start} → {end}", flush=True)
        fundamentals = _load_fundamentals(args.db_path, lookback_start, end)
        rebalance = _weekly_fridays(start, end)
        print(f"[setup] {len(rebalance)} weekly Fridays", flush=True)
        registry = FactorRegistry()
        register_all_factors(registry)
        panels, exclusions = build_factor_score_panels(registry, ohlcv, fundamentals, rebalance)
        print(
            f"[setup] panels: {sorted(panels.keys())}  excluded: {sorted(exclusions.keys())}",
            flush=True,
        )
        forward_returns = _compute_forward_returns(ohlcv, rebalance)
        universe_sizes = _universe_size_by_date(ohlcv, rebalance)

        if 4 in streams_to_run:
            sector_map, _ = load_gics_sectors(args.sector_csv)

    # ─── Stream 2 ─────────────────────────────────────────────────────────
    stream2_result: dict | None = None
    if 2 in streams_to_run:
        print("[Stream 2] Coverage matrix (date × factor)", flush=True)
        coverage = compute_coverage_matrix(panels, rebalance, universe_sizes)
        jaccard = compute_pairwise_jaccard(panels)
        stream2_dir = args.output_root / "iter14_coverage"
        stream2_dir.mkdir(parents=True, exist_ok=True)
        coverage.to_csv(stream2_dir / "coverage_matrix.csv", index=False)
        jaccard.to_csv(stream2_dir / "pairwise_jaccard.csv")
        stream2_result = {
            "stream": 2,
            "n_coverage_rows": int(len(coverage)),
            "per_factor_mean_coverage_pct": {
                f: float(coverage.loc[coverage["factor"] == f, "coverage_pct"].mean())
                for f in sorted(panels.keys())
                if len(coverage.loc[coverage["factor"] == f]) > 0
            },
            "jaccard_summary": {
                "min_off_diagonal": float(jaccard.where(~np.eye(len(jaccard), dtype=bool)).min().min())
                if len(jaccard) >= 2
                else None,
                "max_off_diagonal": float(jaccard.where(~np.eye(len(jaccard), dtype=bool)).max().max())
                if len(jaccard) >= 2
                else None,
            },
        }
        with (stream2_dir / "summary.json").open("w") as f:
            json.dump(stream2_result, f, indent=2, sort_keys=True)
        print(f"  wrote {stream2_dir}/coverage_matrix.csv ({len(coverage)} rows)", flush=True)

    # ─── Stream 3 ─────────────────────────────────────────────────────────
    stream3_result: dict | None = None
    if 3 in streams_to_run:
        print("[Stream 3] Pairwise score & return correlations", flush=True)
        score_corr = compute_pairwise_score_correlation(panels)
        ret_corr = compute_pairwise_return_correlation(panels, forward_returns)
        stream3_dir = args.output_root / "iter14_correlations"
        stream3_dir.mkdir(parents=True, exist_ok=True)
        score_corr.to_csv(stream3_dir / "factor_corr_matrix.csv")
        ret_corr.to_csv(stream3_dir / "forward_return_corr_matrix.csv")
        stream3_result = {
            "stream": 3,
            "factors": sorted(panels.keys()),
            "score_corr_summary": {
                "max_off_diagonal": float(
                    score_corr.where(~np.eye(len(score_corr), dtype=bool)).abs().max().max()
                )
                if len(score_corr) >= 2
                else None,
            },
            "return_corr_summary": {
                "max_off_diagonal": float(
                    ret_corr.where(~np.eye(len(ret_corr), dtype=bool)).abs().max().max()
                )
                if len(ret_corr) >= 2 and ret_corr.notna().any().any()
                else None,
            },
        }
        with (stream3_dir / "summary.json").open("w") as f:
            json.dump(stream3_result, f, indent=2, sort_keys=True)
        print(f"  wrote {stream3_dir}/factor_corr_matrix.csv + forward_return_corr_matrix.csv", flush=True)

    # ─── Stream 4 ─────────────────────────────────────────────────────────
    stream4_result: dict | None = None
    if 4 in streams_to_run:
        print("[Stream 4] Sector residual on momentum_2_12", flush=True)
        if "momentum_2_12" not in panels:
            stream4_result = {
                "stream": 4,
                "note": "momentum_2_12 panel not produced by registry; Stream 4 skipped",
            }
        elif sector_map.empty:
            stream4_result = {
                "stream": 4,
                "note": f"sector CSV at {args.sector_csv} empty or missing; Stream 4 skipped",
            }
        else:
            stream4_result = run_sector_residual_screen(
                "momentum_2_12",
                panels["momentum_2_12"],
                forward_returns,
                sector_map,
            )
            stream4_result["stream"] = 4
        stream4_dir = args.output_root / "iter14_sector_residual"
        stream4_dir.mkdir(parents=True, exist_ok=True)
        with (stream4_dir / "momentum_2_12_sector_residualized.json").open("w") as f:
            json.dump(stream4_result, f, indent=2, sort_keys=True, default=str)
        print(f"  wrote {stream4_dir}/momentum_2_12_sector_residualized.json", flush=True)

    # ─── Stream 5 ─────────────────────────────────────────────────────────
    stream5_result: dict | None = None
    if 5 in streams_to_run:
        print("[Stream 5] Sign-flip on ivol_20d and high_52w", flush=True)
        per_factor: dict[str, dict] = {}
        for fname in ("ivol_20d", "high_52w"):
            if fname not in panels:
                per_factor[fname] = {
                    "factor": fname,
                    "note": "panel not produced by registry; sign-flip skipped",
                }
                continue
            per_factor[fname] = run_sign_flip_screen(fname, panels[fname], forward_returns)
        stream5_result = {"stream": 5, "per_factor": per_factor}
        stream5_dir = args.output_root / "iter14_sign_flip"
        stream5_dir.mkdir(parents=True, exist_ok=True)
        with (stream5_dir / "sign_flip_diagnostic.json").open("w") as f:
            json.dump(stream5_result, f, indent=2, sort_keys=True, default=str)
        print(f"  wrote {stream5_dir}/sign_flip_diagnostic.json", flush=True)

    # ─── Research log event ───────────────────────────────────────────────
    if not args.skip_research_log:
        event = {
            "event": "iter14_diagnostic_battery_run",
            "iteration": 14,
            "iteration_tag": "iter-14",
            "wave": "D_multi_factor_admission_reform",
            "streams_run": sorted(streams_to_run),
            "artefacts_root": str(args.output_root),
            "summary": {
                "stream_1": (stream1_result.get("n_rows") if stream1_result else None),
                "stream_2_coverage_rows": (stream2_result.get("n_coverage_rows") if stream2_result else None),
                "stream_3_factors": (stream3_result.get("factors") if stream3_result else None),
                "stream_4_verdict_passed_all": (
                    stream4_result.get("verdict_passed_all") if stream4_result else None
                ),
                "stream_5_keys": (
                    list(stream5_result.get("per_factor", {}).keys()) if stream5_result else None
                ),
            },
            "note": (
                "observational only; no admission decisions cited; "
                "registry.py sign unchanged; gate_results.json unchanged"
            ),
        }
        log_path = Path("results/research_log.jsonl")
        if log_path.exists():
            append_event(log_path, event)
            print("  research-log event appended", flush=True)

    print("ITER-14 DIAGNOSTIC BATTERY COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
