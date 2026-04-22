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


def compute_volatility_scaled_weights(
    factor_scores: pd.DataFrame,
    vol_panel: pd.DataFrame,
    n_quantiles: int = 5,
) -> tuple[pd.DataFrame, Diagnostics]:
    """Construct volatility-scaled long-short quintile portfolio weights.

    Companion to ``compute_long_short_weights``, but instead of equal-weighting
    within each leg it scales each stock's weight by ``1 / realized_volatility``
    so that (in expectation) each position contributes the same variance to the
    portfolio. This is Carver's vol-targeting applied at the **position level**:
    a stock three times more volatile than its leg-mates receives one third the
    dollar allocation.

    Per date:
      1. Quintile-sort by score (identical construction to
         ``compute_long_short_weights`` — same ``pd.qcut`` with
         ``duplicates="drop"`` so iter-0 bit-exactness of quantile membership is
         preserved).
      2. For each leg, merge with ``vol_panel`` on (date, symbol); exclude
         symbols whose vol is NaN or zero (one cannot divide by zero).
      3. Raw weights ``r_i = 1 / vol_i``. Long-leg weights ``w_i = +r_i /
         sum(r)`` (sum to +1). Short-leg weights ``w_i = -r_i / sum(r)`` (sum
         to -1). Middle quintiles remain excluded.
      4. If a leg has zero valid vols on a date, that leg is skipped for that
         date (the other leg still emits if valid) and a diagnostic info is
         recorded.

    Diagnostic-only. No gate (G0-G5) threshold, sign convention, or admission
    verdict is computed from this helper.

    Parameters
    ----------
    factor_scores : pd.DataFrame
        Columns: ``date``, ``symbol``, ``score``.
    vol_panel : pd.DataFrame
        Columns: ``date``, ``symbol``, ``vol``. Realized (e.g., 20d rolling
        std of daily returns) — caller owns the horizon choice.
    n_quantiles : int
        Number of quantile buckets (default 5 for quintiles, matching
        ``compute_long_short_weights``).

    Returns
    -------
    tuple[pd.DataFrame, Diagnostics]
        (weights DataFrame with columns ``[date, symbol, weight]``, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_volatility_scaled_weights"

    if factor_scores.empty:
        diag.warning(src, "Empty factor_scores; returning empty weights DataFrame.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    if vol_panel.empty:
        diag.warning(src, "Empty vol_panel; returning empty weights DataFrame.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    required_vol_cols = {"date", "symbol", "vol"}
    missing_vol_cols = required_vol_cols - set(vol_panel.columns)
    if missing_vol_cols:
        diag.warning(src, f"vol_panel missing columns {sorted(missing_vol_cols)}; returning empty.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    dates = sorted(factor_scores["date"].unique())
    records: list[dict[str, object]] = []
    n_skipped_insufficient = 0
    n_skipped_spread = 0
    n_leg_no_valid_vol = 0
    n_zero_vol_excluded = 0
    n_nan_vol_excluded = 0

    for dt in dates:
        day_data = factor_scores[factor_scores["date"] == dt].dropna(subset=["score"])
        if len(day_data) < n_quantiles:
            n_skipped_insufficient += 1
            continue

        day_data = day_data.copy()
        day_data["quantile"] = pd.qcut(day_data["score"], q=n_quantiles, labels=False, duplicates="drop")
        n_labels = day_data["quantile"].nunique()
        if n_labels < 2:
            n_skipped_spread += 1
            continue

        top_q = day_data["quantile"].max()
        bot_q = day_data["quantile"].min()

        day_vol = vol_panel[vol_panel["date"] == dt][["symbol", "vol"]]
        merged = day_data.merge(day_vol, on="symbol", how="left")

        for q_label, sign in ((top_q, +1.0), (bot_q, -1.0)):
            leg = merged[merged["quantile"] == q_label][["symbol", "vol"]].copy()
            if leg.empty:
                continue
            n_nan_vol_excluded += int(leg["vol"].isna().sum())
            leg = leg.dropna(subset=["vol"])
            n_zero_vol_excluded += int((leg["vol"] <= 0).sum())
            leg = leg[leg["vol"] > 0]
            if leg.empty:
                n_leg_no_valid_vol += 1
                continue
            raw = 1.0 / leg["vol"]
            total = float(raw.sum())
            if total <= 0:
                n_leg_no_valid_vol += 1
                continue
            w_leg = sign * raw / total
            for sym, w in zip(leg["symbol"], w_leg, strict=True):
                records.append({"date": dt, "symbol": sym, "weight": float(w)})

    if n_skipped_insufficient:
        diag.info(
            src,
            f"Skipped {n_skipped_insufficient} date(s) with fewer rows than n_quantiles.",
        )
    if n_skipped_spread:
        diag.info(src, f"Skipped {n_skipped_spread} date(s) with insufficient quantile spread.")
    if n_nan_vol_excluded:
        diag.info(src, f"Excluded {n_nan_vol_excluded} (date, symbol) pairs with NaN vol.")
    if n_zero_vol_excluded:
        diag.info(src, f"Excluded {n_zero_vol_excluded} (date, symbol) pairs with zero vol.")
    if n_leg_no_valid_vol:
        diag.info(src, f"Skipped {n_leg_no_valid_vol} leg(s) with no valid vols.")

    if not records:
        diag.warning(src, "No valid dates produced vol-scaled weights.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    result = pd.DataFrame(records)
    diag.info(
        src,
        f"Computed vol-scaled weights for {result['date'].nunique()} dates, {len(result)} rows.",
    )
    return result, diag


def compute_cap_tilted_weights(
    factor_scores: pd.DataFrame,
    size_panel: pd.DataFrame,
    n_quantiles: int = 5,
    tilt_exponent: float = 0.5,
) -> tuple[pd.DataFrame, Diagnostics]:
    """Construct market-cap-tilted long-short quintile portfolio weights.

    Diagnostic sibling to ``compute_long_short_weights`` and
    ``compute_volatility_scaled_weights``. Within each leg, weights are
    proportional to ``size ** tilt_exponent``:

      * ``tilt_exponent = 0`` → every stock gets the same weight (reduces
        mathematically to ``compute_long_short_weights``).
      * ``tilt_exponent = 1`` → pure cap-weighted within each leg.
      * ``tilt_exponent = 0.5`` → sqrt-cap tilt (default). Reduces the
        tiny-cap concentration that dominates equal-weight long-short
        portfolios in practice, while not over-weighting mega-caps.

    Quintile construction is identical to ``compute_long_short_weights`` (same
    ``pd.qcut`` with ``duplicates="drop"``) so iter-0 bit-exactness of
    quintile membership is preserved. Within each leg, stocks lacking size
    data (NaN) or with non-positive size are excluded. If a leg has zero
    valid sizes on a date, that leg is skipped for that date (the other leg
    still emits if valid).

    Parameters
    ----------
    factor_scores : pd.DataFrame
        Columns: ``date``, ``symbol``, ``score``.
    size_panel : pd.DataFrame
        Columns: ``date``, ``symbol``, ``size``. ``size`` can be any positive
        monotone market-cap proxy (shares-outstanding × price, dollar
        volume, etc.) — caller owns the proxy choice.
    n_quantiles : int
        Number of quantile buckets (default 5, matching
        ``compute_long_short_weights``).
    tilt_exponent : float
        Exponent applied to size. Must be finite and non-negative. Default
        0.5 (sqrt-cap tilt).

    Returns
    -------
    tuple[pd.DataFrame, Diagnostics]
        (weights DataFrame with columns ``[date, symbol, weight]``,
        diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_cap_tilted_weights"

    if factor_scores.empty:
        diag.warning(src, "Empty factor_scores; returning empty weights DataFrame.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    if size_panel.empty:
        diag.warning(src, "Empty size_panel; returning empty weights DataFrame.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    required_size_cols = {"date", "symbol", "size"}
    missing_size_cols = required_size_cols - set(size_panel.columns)
    if missing_size_cols:
        diag.warning(src, f"size_panel missing columns {sorted(missing_size_cols)}; returning empty.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    if not (tilt_exponent >= 0.0) or not pd.notna(tilt_exponent):
        diag.warning(src, f"tilt_exponent {tilt_exponent!r} must be finite and >= 0; returning empty.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    dates = sorted(factor_scores["date"].unique())
    records: list[dict[str, object]] = []
    n_skipped_insufficient = 0
    n_skipped_spread = 0
    n_leg_no_valid_size = 0
    n_nonpos_size_excluded = 0
    n_nan_size_excluded = 0

    for dt in dates:
        day_data = factor_scores[factor_scores["date"] == dt].dropna(subset=["score"])
        if len(day_data) < n_quantiles:
            n_skipped_insufficient += 1
            continue

        day_data = day_data.copy()
        day_data["quantile"] = pd.qcut(day_data["score"], q=n_quantiles, labels=False, duplicates="drop")
        n_labels = day_data["quantile"].nunique()
        if n_labels < 2:
            n_skipped_spread += 1
            continue

        top_q = day_data["quantile"].max()
        bot_q = day_data["quantile"].min()

        day_size = size_panel[size_panel["date"] == dt][["symbol", "size"]]
        merged = day_data.merge(day_size, on="symbol", how="left")

        for q_label, sign in ((top_q, +1.0), (bot_q, -1.0)):
            leg = merged[merged["quantile"] == q_label][["symbol", "size"]].copy()
            if leg.empty:
                continue
            n_nan_size_excluded += int(leg["size"].isna().sum())
            leg = leg.dropna(subset=["size"])
            n_nonpos_size_excluded += int((leg["size"] <= 0).sum())
            leg = leg[leg["size"] > 0]
            if leg.empty:
                n_leg_no_valid_size += 1
                continue
            raw = leg["size"].astype(float) ** float(tilt_exponent)
            total = float(raw.sum())
            if total <= 0:
                n_leg_no_valid_size += 1
                continue
            w_leg = sign * raw / total
            for sym, w in zip(leg["symbol"], w_leg, strict=True):
                records.append({"date": dt, "symbol": sym, "weight": float(w)})

    if n_skipped_insufficient:
        diag.info(
            src,
            f"Skipped {n_skipped_insufficient} date(s) with fewer rows than n_quantiles.",
        )
    if n_skipped_spread:
        diag.info(src, f"Skipped {n_skipped_spread} date(s) with insufficient quantile spread.")
    if n_nan_size_excluded:
        diag.info(src, f"Excluded {n_nan_size_excluded} (date, symbol) pairs with NaN size.")
    if n_nonpos_size_excluded:
        diag.info(src, f"Excluded {n_nonpos_size_excluded} (date, symbol) pairs with non-positive size.")
    if n_leg_no_valid_size:
        diag.info(src, f"Skipped {n_leg_no_valid_size} leg(s) with no valid sizes.")

    if not records:
        diag.warning(src, "No valid dates produced cap-tilted weights.")
        return pd.DataFrame(columns=["date", "symbol", "weight"]), diag

    result = pd.DataFrame(records)
    diag.info(
        src,
        f"Computed cap-tilted weights (tilt={tilt_exponent}) for "
        f"{result['date'].nunique()} dates, {len(result)} rows.",
    )
    return result, diag


def compute_ensemble_weights(
    factor_score_panels: dict[str, pd.DataFrame],
    factor_sharpes: dict[str, float],
) -> tuple[pd.DataFrame, Diagnostics]:
    """Aggregate per-factor score panels into a Sharpe-weighted ensemble score.

    Diagnostic-only multi-factor aggregator. Produces a single ensemble score
    panel ``[date, symbol, score]`` by taking the Sharpe-weighted mean of
    per-factor scores at each (date, symbol) pair. Factors with non-positive
    or non-finite Sharpe are excluded. Weights are normalized to sum to 1
    over the included factors. Per (date, symbol), the weights are further
    re-normalized across factors that actually observed that pair, so
    missing coverage does not penalize a stock.
    **AP-6 note:** this helper does not alter admission gates, factor sign
    conventions, or quintile construction. It is a pure side-by-side
    aggregation sibling to ``compute_long_short_weights``.

    Parameters
    ----------
    factor_score_panels : dict[str, pd.DataFrame]
        Mapping of factor name → score panel with columns
        ``[date, symbol, score]``. Scores are assumed to be on a common
        scale (e.g., rank-percentile in [0, 1]) — caller owns the
        normalization contract.
    factor_sharpes : dict[str, float]
        Mapping of factor name → annualized Sharpe ratio used as the
        weighting signal. Must cover every key in ``factor_score_panels``.
        Factors with Sharpe ≤ 0 or non-finite are silently excluded (with
        a diagnostic info).

    Returns
    -------
    tuple[pd.DataFrame, Diagnostics]
        (ensemble score DataFrame with columns ``[date, symbol, score]``,
        diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_ensemble_weights"

    if not factor_score_panels:
        diag.warning(src, "Empty factor_score_panels; returning empty ensemble.")
        return pd.DataFrame(columns=["date", "symbol", "score"]), diag

    missing_sharpe_keys = set(factor_score_panels.keys()) - set(factor_sharpes.keys())
    if missing_sharpe_keys:
        diag.warning(
            src,
            f"factor_sharpes missing keys for {sorted(missing_sharpe_keys)}; returning empty ensemble.",
        )
        return pd.DataFrame(columns=["date", "symbol", "score"]), diag

    required_cols = {"date", "symbol", "score"}
    n_excluded_nan_sharpe = 0
    n_excluded_nonpositive_sharpe = 0
    n_excluded_empty_panel = 0
    n_excluded_missing_columns = 0

    included: dict[str, tuple[pd.DataFrame, float]] = {}
    for factor_name, panel in factor_score_panels.items():
        raw_sharpe = factor_sharpes[factor_name]
        try:
            sharpe_val = float(raw_sharpe)
        except (TypeError, ValueError):
            n_excluded_nan_sharpe += 1
            diag.info(src, f"Factor '{factor_name}' excluded: non-numeric Sharpe.")
            continue
        if not np.isfinite(sharpe_val):
            n_excluded_nan_sharpe += 1
            diag.info(src, f"Factor '{factor_name}' excluded: non-finite Sharpe.")
            continue
        if sharpe_val <= 0.0:
            n_excluded_nonpositive_sharpe += 1
            diag.info(
                src,
                f"Factor '{factor_name}' excluded: non-positive Sharpe ({sharpe_val:.4f}).",
            )
            continue
        if panel.empty:
            n_excluded_empty_panel += 1
            diag.info(src, f"Factor '{factor_name}' excluded: empty score panel.")
            continue
        missing_cols = required_cols - set(panel.columns)
        if missing_cols:
            n_excluded_missing_columns += 1
            diag.warning(
                src,
                f"Factor '{factor_name}' excluded: panel missing columns {sorted(missing_cols)}.",
            )
            continue
        included[factor_name] = (panel, sharpe_val)

    if n_excluded_nan_sharpe:
        diag.info(src, f"Excluded {n_excluded_nan_sharpe} factor(s) with non-finite Sharpe.")
    if n_excluded_nonpositive_sharpe:
        diag.info(
            src,
            f"Excluded {n_excluded_nonpositive_sharpe} factor(s) with non-positive Sharpe.",
        )
    if n_excluded_empty_panel:
        diag.info(src, f"Excluded {n_excluded_empty_panel} factor(s) with empty panel.")
    if n_excluded_missing_columns:
        diag.info(
            src,
            f"Excluded {n_excluded_missing_columns} factor(s) with missing columns.",
        )

    if not included:
        diag.warning(src, "No factors survived inclusion filter; returning empty ensemble.")
        return pd.DataFrame(columns=["date", "symbol", "score"]), diag

    total_sharpe = sum(sh for _, sh in included.values())
    if total_sharpe <= 0.0 or not np.isfinite(total_sharpe):
        diag.warning(src, "Sum of included Sharpes is non-positive; returning empty ensemble.")
        return pd.DataFrame(columns=["date", "symbol", "score"]), diag

    stacked_frames: list[pd.DataFrame] = []
    for factor_name, (panel, sharpe_val) in included.items():
        normalized_weight = sharpe_val / total_sharpe
        slim = panel[["date", "symbol", "score"]].copy()
        slim = slim.dropna(subset=["score"])
        if slim.empty:
            diag.info(src, f"Factor '{factor_name}' has no non-NaN scores after drop.")
            continue
        slim["factor"] = factor_name
        slim["weight"] = normalized_weight
        stacked_frames.append(slim)

    if not stacked_frames:
        diag.warning(src, "No non-NaN scores across included factors; returning empty ensemble.")
        return pd.DataFrame(columns=["date", "symbol", "score"]), diag

    stacked = pd.concat(stacked_frames, ignore_index=True)
    stacked["weighted_score"] = stacked["score"].astype(float) * stacked["weight"].astype(float)

    grouped = stacked.groupby(["date", "symbol"], sort=False)
    numerator = grouped["weighted_score"].sum()
    denominator = grouped["weight"].sum()

    ensemble_score = (numerator / denominator).rename("score").reset_index()
    ensemble_score = ensemble_score.dropna(subset=["score"])

    if ensemble_score.empty:
        diag.warning(src, "Ensemble aggregation produced no rows; returning empty ensemble.")
        return pd.DataFrame(columns=["date", "symbol", "score"]), diag

    diag.info(
        src,
        f"Computed Sharpe-weighted ensemble across {len(included)} factor(s) "
        f"({ensemble_score['date'].nunique()} dates, {len(ensemble_score)} rows).",
    )
    return ensemble_score, diag


def compute_risk_parity_weights(
    factor_returns: dict[str, pd.Series],
    cov_matrix: pd.DataFrame | None = None,
    max_iter: int = 200,
    tol: float = 1e-8,
) -> tuple[pd.Series, Diagnostics]:
    """Allocate weights across factor legs so each contributes equal risk.

    Diagnostic-only risk-parity allocator. Given factor-leg return series,
    produces weights ``w = (w_1, ..., w_n)`` with ``sum(w) = 1`` and
    ``w_i > 0`` such that the risk contributions
    ``RC_i = w_i · (Σw)_i`` are equal across factors (Maillard, Roncalli &
    Teiletche, 2010). Solved via fixed-point iteration
    ``w ← (1 / Σw) / sum(1 / Σw)`` which converges to equal-risk-contribution
    under a positive semi-definite covariance matrix.

    **AP-6 note:** this helper does not alter admission gates, factor sign
    conventions, or quintile construction. It is a pure side-by-side
    allocator sibling to ``compute_long_short_weights`` and
    ``compute_ensemble_weights``.

    Parameters
    ----------
    factor_returns : dict[str, pd.Series]
        Mapping of factor name → per-date long-short return Series. Used to
        estimate covariance when ``cov_matrix`` is None. Factors with
        non-Series values or all-NaN series are excluded.
    cov_matrix : pd.DataFrame | None
        Optional pre-computed covariance matrix. Index must equal columns.
        When provided, only factors appearing in both
        ``factor_returns.keys()`` and ``cov_matrix.index`` are used.
    max_iter : int
        Maximum fixed-point iterations (default 200).
    tol : float
        Convergence tolerance on max absolute weight change per iteration
        (default 1e-8).

    Returns
    -------
    tuple[pd.Series, Diagnostics]
        (weights Series indexed by factor name summing to 1, diagnostics).
        Empty Series on degenerate paths with warnings.
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_risk_parity_weights"

    if not factor_returns:
        diag.warning(src, "Empty factor_returns; returning empty weights.")
        return pd.Series(dtype=float, name="weight"), diag

    kept: dict[str, pd.Series] = {}
    n_excluded_non_series = 0
    n_excluded_all_nan = 0
    for factor_name, series in factor_returns.items():
        if not isinstance(series, pd.Series):
            n_excluded_non_series += 1
            diag.info(src, f"Factor '{factor_name}' excluded: not a pd.Series.")
            continue
        if series.dropna().empty:
            n_excluded_all_nan += 1
            diag.info(src, f"Factor '{factor_name}' excluded: all-NaN series.")
            continue
        kept[factor_name] = series

    if n_excluded_non_series:
        diag.info(src, f"Excluded {n_excluded_non_series} factor(s) with non-Series values.")
    if n_excluded_all_nan:
        diag.info(src, f"Excluded {n_excluded_all_nan} factor(s) with all-NaN series.")

    if not kept:
        diag.warning(src, "No factors survived inclusion filter; returning empty weights.")
        return pd.Series(dtype=float, name="weight"), diag

    if cov_matrix is not None:
        if not cov_matrix.index.equals(cov_matrix.columns):
            diag.warning(src, "cov_matrix index != columns; returning empty weights.")
            return pd.Series(dtype=float, name="weight"), diag
        factors_in_cov = set(cov_matrix.index)
        factors = [f for f in kept if f in factors_in_cov]
        n_missing_cov = len(kept) - len(factors)
        if n_missing_cov:
            diag.info(src, f"Excluded {n_missing_cov} factor(s) missing from cov_matrix.")
        if not factors:
            diag.warning(
                src,
                "No overlap between factor_returns keys and cov_matrix index; returning empty weights.",
            )
            return pd.Series(dtype=float, name="weight"), diag
        cov = cov_matrix.loc[factors, factors].astype(float).to_numpy(copy=True)
    else:
        factors = list(kept.keys())
        if len(factors) == 1:
            diag.info(src, "Single factor input; returning weight = 1.0.")
            return pd.Series([1.0], index=factors, name="weight"), diag
        returns_df = pd.DataFrame({f: kept[f] for f in factors})
        cov_df = returns_df.cov()
        cov = cov_df.astype(float).to_numpy(copy=True)

    variance_floor = 1e-16
    diag_var = np.diag(cov)
    valid_idx = np.where(diag_var > variance_floor)[0]
    n_excluded_zero_var = len(factors) - len(valid_idx)
    if n_excluded_zero_var:
        diag.info(src, f"Excluded {n_excluded_zero_var} factor(s) with zero variance.")
        factors = [factors[i] for i in valid_idx]
        cov = cov[np.ix_(valid_idx, valid_idx)]

    if not factors:
        diag.warning(src, "No factors with positive variance; returning empty weights.")
        return pd.Series(dtype=float, name="weight"), diag

    n = len(factors)
    if n == 1:
        diag.info(src, "Single factor after filtering; returning weight = 1.0.")
        return pd.Series([1.0], index=factors, name="weight"), diag

    diag_cov = np.diag(cov).astype(float)
    w = np.full(n, 1.0 / n)
    converged = False
    last_change = float("nan")

    def _inv_vol_fallback() -> pd.Series:
        vol = np.sqrt(np.maximum(diag_cov, variance_floor))
        inv_vol = 1.0 / vol
        return pd.Series(inv_vol / inv_vol.sum(), index=factors, name="weight")

    for iteration in range(max_iter):
        w_prev = w.copy()
        sigma_p_sq = float(w @ cov @ w)
        if sigma_p_sq <= 0.0 or not np.isfinite(sigma_p_sq):
            diag.warning(
                src,
                "Non-positive portfolio variance; falling back to inverse-vol weights.",
            )
            return _inv_vol_fallback(), diag
        for i in range(n):
            sigma_ii = float(diag_cov[i])
            mc_i = float(cov[i] @ w)
            a_i = mc_i - sigma_ii * w[i]
            discriminant = a_i * a_i + 4.0 * sigma_ii * sigma_p_sq / n
            if not np.isfinite(discriminant) or discriminant < 0.0:
                diag.warning(
                    src,
                    f"Non-finite/negative discriminant for factor '{factors[i]}'; "
                    "falling back to inverse-vol weights.",
                )
                return _inv_vol_fallback(), diag
            w[i] = (-a_i + float(np.sqrt(discriminant))) / (2.0 * sigma_ii)
        total = float(w.sum())
        if total <= 0.0 or not np.isfinite(total):
            diag.warning(src, "Weights sum to non-positive; falling back to inverse-vol weights.")
            return _inv_vol_fallback(), diag
        w = w / total
        last_change = float(np.abs(w - w_prev).max())
        if last_change < tol:
            converged = True
            diag.info(
                src,
                f"Risk-parity converged in {iteration + 1} iterations (max_change={last_change:.3e}).",
            )
            break

    if not converged:
        diag.warning(
            src,
            f"Risk-parity did not converge in {max_iter} iterations (max_change={last_change:.3e}).",
        )

    portfolio_variance = float(w @ cov @ w)
    diag.info(
        src,
        f"Computed risk-parity weights across {n} factor(s); portfolio variance = {portfolio_variance:.6f}.",
    )
    return pd.Series(w, index=factors, name="weight"), diag


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
