"""Factor screening pipeline — G0-G5 gate evaluation for a single factor candidate.

Orchestrates the computation of all metrics required by the gate framework:
  - Long-short quintile portfolio construction
  - IC series computation (cross-sectional Spearman)
  - OOS Sharpe, permutation p-value, IC mean, IC IR, max drawdown
  - Marginal contribution (optional, when existing factors provided)

All functions are pure — no I/O, no logging.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics, GateVerdict
from nyse_core.gates import evaluate_factor_gates
from nyse_core.metrics import (
    ic_ir as compute_ic_ir,
)
from nyse_core.metrics import (
    information_coefficient,
    max_drawdown,
    sharpe_ratio,
)
from nyse_core.statistics import permutation_test

_MOD = "factor_screening"


def compute_long_short_returns(
    factor_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
    n_quantiles: int = 5,
) -> tuple[pd.Series, Diagnostics]:
    """Construct equal-weighted long-short quintile portfolio returns.

    For each rebalance date:
      - Sort stocks by factor score
      - Long top quintile, short bottom quintile
      - Equal weight within each leg
      - Return: daily return = mean(long returns) - mean(short returns)

    Parameters
    ----------
    factor_scores : pd.DataFrame
        Columns: date, symbol, score.
    forward_returns : pd.DataFrame
        Columns: date, symbol, fwd_ret_5d.
    n_quantiles : int
        Number of quantile buckets (default 5 for quintiles).

    Returns
    -------
    tuple[pd.Series, Diagnostics]
        (long_short_returns indexed by date, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_long_short_returns"

    merged = pd.merge(factor_scores, forward_returns, on=["date", "symbol"], how="inner")

    if merged.empty:
        diag.warning(src, "No overlapping date/symbol pairs between scores and returns.")
        return pd.Series(dtype=float, name="ls_return"), diag

    dates = sorted(merged["date"].unique())
    ls_returns: dict = {}

    for dt in dates:
        day_data = merged[merged["date"] == dt].dropna(subset=["score", "fwd_ret_5d"])

        if len(day_data) < n_quantiles:
            diag.warning(
                src,
                f"Date {dt}: only {len(day_data)} stocks, need >= {n_quantiles}. Skipping.",
            )
            continue

        # Assign quantile labels (0 = lowest score, n_quantiles-1 = highest)
        day_data = day_data.copy()
        day_data["quantile"] = pd.qcut(day_data["score"], q=n_quantiles, labels=False, duplicates="drop")

        n_labels = day_data["quantile"].nunique()
        if n_labels < 2:
            diag.warning(src, f"Date {dt}: insufficient quantile spread. Skipping.")
            continue

        top_q = day_data["quantile"].max()
        bot_q = day_data["quantile"].min()

        long_ret = day_data.loc[day_data["quantile"] == top_q, "fwd_ret_5d"].mean()
        short_ret = day_data.loc[day_data["quantile"] == bot_q, "fwd_ret_5d"].mean()

        ls_returns[dt] = long_ret - short_ret

    if not ls_returns:
        diag.warning(src, "No valid dates produced long-short returns.")
        return pd.Series(dtype=float, name="ls_return"), diag

    result = pd.Series(ls_returns, name="ls_return")
    result.index.name = "date"

    diag.info(src, f"Computed long-short returns for {len(result)} dates.")
    return result, diag


def compute_long_short_weights(
    factor_scores: pd.DataFrame,
    n_quantiles: int = 5,
) -> tuple[pd.DataFrame, Diagnostics]:
    """Construct equal-weighted long-short quintile portfolio weights.

    Companion to ``compute_long_short_returns`` — mirrors the same quintile
    construction but emits per-(date, symbol) weights instead of collapsing to
    a single return per date. Brinson attribution (iter-3) and any later
    characteristic-matched benchmark (iter-4) both need the raw weights, so
    exposing them here avoids re-deriving the quintile logic downstream.

    For each rebalance date:
      - Top quintile stocks each receive weight ``+1 / n_top``
      - Bottom quintile stocks each receive weight ``-1 / n_bot``
      - Middle quintiles are excluded from the output entirely (weight=0 by
        absence) — keeping the DataFrame compact

    The output is dollar-neutral per date (sum of longs = +1, sum of shorts =
    -1). It is NOT dollar-sized; callers scaling to a target gross exposure
    should multiply by (gross_exposure / 2).

    Parameters
    ----------
    factor_scores : pd.DataFrame
        Columns: date, symbol, score.
    n_quantiles : int
        Number of quantile buckets (default 5 for quintiles).

    Returns
    -------
    tuple[pd.DataFrame, Diagnostics]
        (weights DataFrame with columns ``[date, symbol, weight]``, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_long_short_weights"

    if factor_scores.empty:
        diag.warning(src, "Empty factor_scores; returning empty weights DataFrame.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    dates = sorted(factor_scores["date"].unique())
    records: list[dict[str, object]] = []
    n_skipped = 0

    for dt in dates:
        day_data = factor_scores[factor_scores["date"] == dt].dropna(subset=["score"])
        if len(day_data) < n_quantiles:
            n_skipped += 1
            continue

        day_data = day_data.copy()
        day_data["quantile"] = pd.qcut(day_data["score"], q=n_quantiles, labels=False, duplicates="drop")

        n_labels = day_data["quantile"].nunique()
        if n_labels < 2:
            n_skipped += 1
            continue

        top_q = day_data["quantile"].max()
        bot_q = day_data["quantile"].min()

        top_mask = day_data["quantile"] == top_q
        bot_mask = day_data["quantile"] == bot_q
        n_top = int(top_mask.sum())
        n_bot = int(bot_mask.sum())

        if n_top == 0 or n_bot == 0:
            n_skipped += 1
            continue

        long_w = 1.0 / n_top
        short_w = -1.0 / n_bot
        for sym in day_data.loc[top_mask, "symbol"]:
            records.append({"date": dt, "symbol": sym, "weight": long_w})
        for sym in day_data.loc[bot_mask, "symbol"]:
            records.append({"date": dt, "symbol": sym, "weight": short_w})

    if n_skipped:
        diag.info(src, f"Skipped {n_skipped} date(s) with insufficient quantile spread.")

    if not records:
        diag.warning(src, "No valid dates produced long-short weights.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    result = pd.DataFrame(records)
    diag.info(src, f"Computed long-short weights for {result['date'].nunique()} dates, {len(result)} rows.")
    return result, diag


def _compute_ic_series(
    factor_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Compute IC (Spearman) per rebalance date.

    Parameters
    ----------
    factor_scores : pd.DataFrame
        Columns: date, symbol, score.
    forward_returns : pd.DataFrame
        Columns: date, symbol, fwd_ret_5d.

    Returns
    -------
    tuple[pd.Series, Diagnostics]
        (IC series indexed by date, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}._compute_ic_series"

    merged = pd.merge(factor_scores, forward_returns, on=["date", "symbol"], how="inner")

    if merged.empty:
        diag.warning(src, "No overlapping data for IC computation.")
        return pd.Series(dtype=float, name="ic"), diag

    dates = sorted(merged["date"].unique())
    ic_values: dict = {}

    for dt in dates:
        day_data = merged[merged["date"] == dt].dropna(subset=["score", "fwd_ret_5d"])
        if len(day_data) < 3:
            continue
        ic_val, _ = information_coefficient(day_data["score"], day_data["fwd_ret_5d"])
        ic_values[dt] = ic_val

    result = pd.Series(ic_values, name="ic")
    result.index.name = "date"
    diag.info(src, f"Computed IC for {len(result)} dates.")
    return result, diag


def _compute_ensemble_ic_delta(
    candidate_scores: pd.DataFrame,
    existing_factor_scores: dict[str, pd.DataFrame],
    forward_returns: pd.DataFrame,
) -> tuple[float, Diagnostics]:
    """Compute marginal IC contribution: ensemble IC with candidate minus without.

    Builds equal-weighted ensemble from existing factors, measures IC, then
    adds the candidate and re-measures. Returns the difference.
    """
    diag = Diagnostics()
    src = f"{_MOD}._compute_ensemble_ic_delta"

    all_dates = set(candidate_scores["date"].unique())
    for df in existing_factor_scores.values():
        all_dates &= set(df["date"].unique())
    all_dates &= set(forward_returns["date"].unique())

    if not all_dates:
        diag.warning(src, "No common dates across candidate, existing, and returns.")
        return 0.0, diag

    ic_without_vals: list[float] = []
    ic_with_vals: list[float] = []

    for dt in sorted(all_dates):
        fwd_at = forward_returns[forward_returns["date"] == dt].set_index("symbol")["fwd_ret_5d"]

        existing_at: list[pd.Series] = []
        for _name, df in existing_factor_scores.items():
            day_scores = df[df["date"] == dt].set_index("symbol")["score"]
            if not day_scores.empty:
                existing_at.append(day_scores)

        if not existing_at:
            continue

        ens_without = pd.concat(existing_at, axis=1).mean(axis=1)
        cand_at = candidate_scores[candidate_scores["date"] == dt].set_index("symbol")["score"]

        # IC without candidate
        common = ens_without.index.intersection(fwd_at.dropna().index)
        if len(common) < 5:
            continue
        ic_wo, _ = information_coefficient(ens_without.loc[common], fwd_at.loc[common])
        ic_without_vals.append(ic_wo)

        # IC with candidate
        if not cand_at.empty:
            ens_with = pd.concat(existing_at + [cand_at], axis=1).mean(axis=1)
            common_w = ens_with.index.intersection(fwd_at.dropna().index)
            if len(common_w) >= 5:
                ic_w, _ = information_coefficient(ens_with.loc[common_w], fwd_at.loc[common_w])
                ic_with_vals.append(ic_w)

    if not ic_without_vals or not ic_with_vals:
        diag.warning(src, "Insufficient data for ensemble IC delta computation.")
        return 0.0, diag

    mean_wo = float(np.mean(ic_without_vals))
    mean_w = float(np.mean(ic_with_vals))
    delta = mean_w - mean_wo
    diag.info(src, f"Ensemble IC: without={mean_wo:.4f}, with={mean_w:.4f}, delta={delta:.4f}.")
    return delta, diag


def screen_factor(
    factor_name: str,
    factor_scores: pd.DataFrame,
    forward_returns: pd.DataFrame,
    existing_factors: list[str] | None = None,
    existing_factor_scores: dict[str, pd.DataFrame] | None = None,
    gate_config: dict | None = None,
) -> tuple[GateVerdict, dict[str, float], Diagnostics]:
    """Run a factor candidate through the full G0-G5 admission gate funnel.

    Computes all required metrics internally:
      - G0: OOS Sharpe (from long-short quintile returns)
      - G1: Permutation p-value (from statistics.permutation_test)
      - G2: IC mean (from metrics.information_coefficient over all dates)
      - G3: IC IR (from metrics.ic_ir)
      - G4: Max drawdown (of long-short quintile portfolio)
      - G5: Marginal contribution (IC after adding to existing ensemble vs before)

    Parameters
    ----------
    factor_name : str
        Name of the candidate factor.
    factor_scores : pd.DataFrame
        Columns: date, symbol, score.
    forward_returns : pd.DataFrame
        Columns: date, symbol, fwd_ret_5d.
    existing_factors : list[str] | None
        Names of factors already in the portfolio (for G5 marginal test).
        If None, G5 auto-passes.
    existing_factor_scores : dict[str, pd.DataFrame] | None
        Actual score DataFrames for existing factors, keyed by factor name.
        Each DataFrame must have columns: date, symbol, score.
        When provided alongside existing_factors, G5 computes the real
        ensemble IC delta (IC_with - IC_without). Without this, G5 falls
        back to using IC mean as a proxy.
    gate_config : dict | None
        Custom gate config. Uses DEFAULT_GATE_CONFIG when None.

    Returns
    -------
    tuple[GateVerdict, dict[str, float], Diagnostics]
        (verdict, detailed_metrics_dict, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.screen_factor"
    metrics: dict[str, float] = {}

    # ── Long-short quintile returns ──────────────────────────────────────
    ls_returns, ls_diag = compute_long_short_returns(factor_scores, forward_returns)
    diag.merge(ls_diag)

    # G0: OOS Sharpe
    oos_sharpe = sharpe_ratio(ls_returns)[0] if len(ls_returns) > 0 else 0.0
    metrics["oos_sharpe"] = oos_sharpe

    # G1: Permutation p-value
    if len(ls_returns) > 1:
        perm_p, perm_diag = permutation_test(ls_returns, n_reps=500, block_size=21)
        diag.merge(perm_diag)
    else:
        perm_p = 1.0
        diag.warning(src, "Insufficient long-short returns for permutation test.")
    metrics["permutation_p"] = perm_p

    # ── IC series ────────────────────────────────────────────────────────
    ic_series, ic_diag = _compute_ic_series(factor_scores, forward_returns)
    diag.merge(ic_diag)

    # G2: IC mean
    ic_mean = float(ic_series.mean()) if len(ic_series) > 0 else 0.0
    metrics["ic_mean"] = ic_mean

    # G3: IC IR
    ic_ir_val = compute_ic_ir(ic_series)[0] if len(ic_series) > 1 else 0.0
    metrics["ic_ir"] = ic_ir_val

    # G4: Max drawdown
    mdd = max_drawdown(ls_returns)[0] if len(ls_returns) > 0 else 0.0
    metrics["max_drawdown"] = mdd

    # G5: Marginal contribution — actual ensemble IC delta when possible
    if existing_factors and existing_factor_scores:
        marginal, marg_diag = _compute_ensemble_ic_delta(
            factor_scores,
            existing_factor_scores,
            forward_returns,
        )
        diag.merge(marg_diag)
        diag.info(
            src,
            f"G5 marginal contribution (ensemble IC delta): {marginal:.4f} "
            f"against {len(existing_factors)} existing factors.",
        )
    elif existing_factors:
        # Have names but no score data — use IC mean as fallback proxy
        marginal = ic_mean
        diag.warning(
            src,
            "G5: No existing_factor_scores provided; using IC mean proxy. "
            "Pass score DataFrames for accurate marginal contribution.",
        )
    else:
        # No existing factors — auto-pass G5 with a positive sentinel
        marginal = 1.0
        diag.info(src, "No existing factors — G5 auto-pass.")
    metrics["marginal_contribution"] = marginal

    # Include factor_name in metrics for GateVerdict extraction
    metrics["factor_name"] = float("nan")  # sentinel — extracted as string below

    diag.info(
        src,
        f"Factor '{factor_name}' metrics: Sharpe={oos_sharpe:.4f}, "
        f"perm_p={perm_p:.4f}, IC={ic_mean:.4f}, ICIR={ic_ir_val:.4f}, "
        f"MDD={mdd:.4f}, marginal={marginal:.4f}",
    )

    # ── Evaluate gates ───────────────────────────────────────────────────
    # Build metrics dict with factor_name as string for GateVerdict
    gate_metrics = {k: v for k, v in metrics.items() if k != "factor_name"}
    gate_metrics["factor_name"] = factor_name

    verdict, gate_diag = evaluate_factor_gates(
        gate_metrics, gate_config=gate_config, existing_factors=existing_factors
    )
    diag.merge(gate_diag)

    # Remove the sentinel from returned metrics
    clean_metrics = {k: v for k, v in metrics.items() if k != "factor_name"}

    return verdict, clean_metrics, diag
